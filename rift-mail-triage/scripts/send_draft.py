# -*- coding: utf-8 -*-
"""Idempotently send one exact draft UID without writing to Sent."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import getaddresses
from pathlib import Path
from typing import Callable

from mail_lib import (
    SEND_RECEIPT_ROOT,
    SENT_POLL_INTERVAL_SECONDS,
    SENT_POLL_TIMEOUT_SECONDS,
    decode_mime,
    find_folder,
    get_credentials,
    imap_connect,
    parse_message,
    smtp_connect,
)


_MESSAGE_ID_RE = re.compile(r"^[^<>\s@]+@[^<>\s@]+$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_uid(uid: object) -> str:
    value = str(uid).strip()
    if not value.isdigit() or int(value) <= 0:
        raise ValueError("draft UID must be a positive integer")
    return value


def _normalize_message_id(value: object) -> str:
    inner = str(value or "").strip()
    if inner.startswith("<") and inner.endswith(">"):
        inner = inner[1:-1].strip()
    if not _MESSAGE_ID_RE.fullmatch(inner):
        raise ValueError("draft must contain one valid Message-ID")
    return f"<{inner.casefold()}>"


def _extract_raw(fetch_data: object) -> bytes | None:
    if not isinstance(fetch_data, (list, tuple)):
        return None
    for item in fetch_data:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        raw = item[1]
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)
    return None


def _fetch_meta(fetch_data: object) -> bytes:
    if not isinstance(fetch_data, (list, tuple)):
        return b""
    chunks = []
    for item in fetch_data:
        if isinstance(item, tuple) and item:
            meta = item[0]
            if isinstance(meta, bytes):
                chunks.append(meta)
            else:
                chunks.append(str(meta).encode("utf-8", "replace"))
    return b" ".join(chunks)


def _select(imap, folder: str, *, readonly: bool) -> None:
    quoted = folder if folder.startswith('"') else f'"{folder}"'
    typ, _ = imap.select(quoted, readonly=readonly)
    if typ != "OK":
        raise RuntimeError(f"cannot open IMAP folder: {folder}")


def _fetch_draft(imap, folder: str, uid: str, *, readonly: bool) -> bytes:
    _select(imap, folder, readonly=readonly)
    typ, data = imap.uid("FETCH", uid, "(BODY.PEEK[] FLAGS)")
    raw = _extract_raw(data)
    if typ != "OK" or raw is None:
        raise ValueError(f"draft UID not found: {uid}")
    if b"\\DRAFT" not in _fetch_meta(data).upper():
        raise ValueError(f"UID is not a draft: {uid}")
    return raw


def _addresses(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for _, address in getaddresses(values):
        normalized = address.strip().casefold()
        if not normalized or "@" not in normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _build_plan(raw: bytes, uid: str, mailbox: str, folder: str) -> dict:
    msg = parse_message(raw)
    message_id = _normalize_message_id(msg.get("Message-ID"))
    senders = _addresses(msg.get_all("From", []))
    if senders != [mailbox.casefold()]:
        raise ValueError("draft From must match the authenticated mailbox")

    recipients = _addresses(
        msg.get_all("To", []) + msg.get_all("Cc", []) + msg.get_all("Bcc", [])
    )
    if not recipients:
        raise ValueError("draft must contain at least one recipient")

    return {
        "message": msg,
        "draft_folder": folder,
        "draft_uid": uid,
        "message_id": message_id,
        "mime_sha256": hashlib.sha256(raw).hexdigest(),
        "subject": decode_mime(msg.get("Subject") or ""),
        "recipients": recipients,
    }


def _load_receipts(mailbox_dir: Path) -> list[tuple[Path, dict]]:
    receipts = []
    for path in sorted(mailbox_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"unreadable send receipt: {path}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"invalid send receipt: {path}")
        receipts.append((path, payload))
    return receipts


def _matching_receipt(
    receipts: list[tuple[Path, dict]], plan: dict
) -> tuple[Path, dict] | None:
    for path, receipt in receipts:
        try:
            receipt_message_id = _normalize_message_id(receipt.get("message_id"))
        except ValueError:
            receipt_message_id = ""
        if (
            receipt_message_id == plan["message_id"]
            or receipt.get("mime_sha256") == plan["mime_sha256"]
        ):
            return path, receipt
    return None


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            os.chmod(temp_name, 0o600)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def _write_receipt(path: Path, receipt: dict, **changes) -> dict:
    updated = dict(receipt)
    updated.update(changes)
    updated["updated_at"] = _now()
    _atomic_write(path, updated)
    return updated


def _new_receipt(plan: dict) -> dict:
    timestamp = _now()
    return {
        "version": 1,
        "status": "PREPARED",
        "draft_folder": plan["draft_folder"],
        "draft_uid": plan["draft_uid"],
        "message_id": plan["message_id"],
        "mime_sha256": plan["mime_sha256"],
        "subject": plan["subject"],
        "recipients": plan["recipients"],
        "created_at": timestamp,
        "updated_at": timestamp,
        "smtp_attempt_started_at": None,
        "smtp_accepted_at": None,
        "draft_consumed_at": None,
        "sent_seen_at": None,
        "last_error": None,
    }


def _consume_exact_draft(imap, plan: dict, receipt_path: Path, receipt: dict) -> dict:
    try:
        raw = _fetch_draft(
            imap,
            plan["draft_folder"],
            plan["draft_uid"],
            readonly=False,
        )
        if hashlib.sha256(raw).hexdigest() != plan["mime_sha256"]:
            raise RuntimeError("draft MIME changed after SMTP acceptance")
        current_message_id = _normalize_message_id(
            parse_message(raw).get("Message-ID")
        )
        if current_message_id != plan["message_id"]:
            raise RuntimeError("draft Message-ID changed after SMTP acceptance")

        typ, _ = imap.uid(
            "STORE", plan["draft_uid"], "+FLAGS.SILENT", "(\\Deleted)"
        )
        if typ != "OK":
            raise RuntimeError("failed to mark exact draft UID deleted")
        typ, _ = imap.uid("EXPUNGE", plan["draft_uid"])
        if typ != "OK":
            raise RuntimeError("failed to expunge exact draft UID")
        return _write_receipt(
            receipt_path,
            receipt,
            draft_consumed_at=_now(),
            last_error=None,
        )
    except Exception as exc:
        return _write_receipt(receipt_path, receipt, last_error=f"draft cleanup: {exc}")


def _sent_contains_message_id(imap, message_id: str) -> bool:
    typ, data = imap.uid("SEARCH", None, "HEADER", "Message-ID", message_id)
    if typ != "OK" or not data or not data[0]:
        return False
    for uid in data[0].split():
        typ, fetch_data = imap.uid(
            "FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])"
        )
        raw = _extract_raw(fetch_data)
        if typ != "OK" or raw is None:
            continue
        try:
            candidate = _normalize_message_id(
                parse_message(raw).get("Message-ID")
            )
        except ValueError:
            continue
        if candidate == message_id:
            return True
    return False


def _poll_sent(
    imap,
    message_id: str,
    receipt_path: Path,
    receipt: dict,
    *,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
    timeout: float,
    interval: float,
) -> dict:
    try:
        sent_folder = find_folder(imap, "sent")
        _select(imap, sent_folder, readonly=True)
        deadline = monotonic() + max(timeout, 0.0)
        while True:
            if _sent_contains_message_id(imap, message_id):
                return _write_receipt(
                    receipt_path,
                    receipt,
                    sent_seen_at=_now(),
                    last_error=None,
                )
            if monotonic() >= deadline:
                return receipt
            sleep(max(interval, 0.001))
    except Exception as exc:
        return _write_receipt(
            receipt_path, receipt, last_error=f"Sent reconciliation: {exc}"
        )


def _print_plan(plan: dict, *, apply: bool) -> None:
    mode = "apply" if apply else "dry-run"
    print(f"[send] mode={mode} uid={plan['draft_uid']}")
    print(f"[send] subject={plan['subject']}")
    print(f"[send] recipients={', '.join(plan['recipients'])}")
    print(f"[send] message_id={plan['message_id']}")
    print(f"[send] mime_sha256={plan['mime_sha256']}")


def run_send(
    uid,
    apply=False,
    *,
    imap_factory=None,
    smtp_factory=None,
    receipt_root=None,
    sleep=time.sleep,
    monotonic=time.monotonic,
    sent_poll_timeout=SENT_POLL_TIMEOUT_SECONDS,
    sent_poll_interval=SENT_POLL_INTERVAL_SECONDS,
) -> int:
    """Send one draft safely; return zero for accepted or already accepted."""
    try:
        draft_uid = _normalize_uid(uid)
        mailbox, _ = get_credentials()
    except (SystemExit, ValueError) as exc:
        print(f"[send] {exc}")
        return 2

    imap_factory = imap_factory or imap_connect
    smtp_factory = smtp_factory or smtp_connect
    imap = None
    try:
        imap = imap_factory()
        drafts_folder = find_folder(imap, "drafts")

        if not apply:
            raw = _fetch_draft(imap, drafts_folder, draft_uid, readonly=True)
            plan = _build_plan(raw, draft_uid, mailbox, drafts_folder)
            _print_plan(plan, apply=False)
            return 0

        root = Path(receipt_root or SEND_RECEIPT_ROOT).expanduser()
        mailbox_hash = hashlib.sha256(mailbox.casefold().encode("utf-8")).hexdigest()
        mailbox_dir = root / mailbox_hash
        mailbox_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_path = mailbox_dir / "send.lock"

        with lock_path.open("a+", encoding="utf-8") as lock_handle:
            os.chmod(lock_path, 0o600)
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            receipts = _load_receipts(mailbox_dir)

            for _, receipt in receipts:
                if str(receipt.get("draft_uid")) != draft_uid:
                    continue
                status = receipt.get("status")
                if status == "ACCEPTED":
                    print("[send] already accepted; SMTP was not called")
                    return 0
                if status == "UNKNOWN":
                    print("[send] prior SMTP result is UNKNOWN; manual review required")
                    return 2

            raw = _fetch_draft(imap, drafts_folder, draft_uid, readonly=True)
            plan = _build_plan(raw, draft_uid, mailbox, drafts_folder)
            _print_plan(plan, apply=True)
            match = _matching_receipt(receipts, plan)
            if match:
                receipt_path, receipt = match
                status = receipt.get("status")
                if status == "ACCEPTED":
                    print("[send] matching message already accepted; SMTP was not called")
                    return 0
                if status == "UNKNOWN":
                    print("[send] matching message is UNKNOWN; manual review required")
                    return 2
                if not (
                    status == "PREPARED"
                    and str(receipt.get("draft_uid")) == draft_uid
                    and receipt.get("mime_sha256") == plan["mime_sha256"]
                    and _normalize_message_id(receipt.get("message_id"))
                    == plan["message_id"]
                ):
                    print("[send] matching receipt is not resumable")
                    return 2
            else:
                receipt_path = mailbox_dir / f"{plan['mime_sha256']}.json"
                receipt = _new_receipt(plan)
                _atomic_write(receipt_path, receipt)

            receipt = _write_receipt(
                receipt_path,
                receipt,
                status="UNKNOWN",
                smtp_attempt_started_at=_now(),
                last_error=None,
            )

            smtp = None
            try:
                smtp = smtp_factory()
                refused = smtp.send_message(
                    plan["message"],
                    from_addr=mailbox,
                    to_addrs=plan["recipients"],
                )
                if refused:
                    receipt = _write_receipt(
                        receipt_path,
                        receipt,
                        last_error="partial recipient refusal",
                    )
                    print("[send] partial recipient refusal; status remains UNKNOWN")
                    return 2
            except Exception as exc:
                receipt = _write_receipt(
                    receipt_path,
                    receipt,
                    last_error=f"SMTP result unknown: {exc}",
                )
                print("[send] SMTP result is UNKNOWN; automatic retry is blocked")
                return 2
            finally:
                if smtp is not None:
                    try:
                        smtp.quit()
                    except Exception:
                        pass

            receipt = _write_receipt(
                receipt_path,
                receipt,
                status="ACCEPTED",
                smtp_accepted_at=_now(),
                last_error=None,
            )
            receipt = _consume_exact_draft(imap, plan, receipt_path, receipt)
            _poll_sent(
                imap,
                plan["message_id"],
                receipt_path,
                receipt,
                sleep=sleep,
                monotonic=monotonic,
                timeout=sent_poll_timeout,
                interval=sent_poll_interval,
            )
            return 0
    except (RuntimeError, ValueError) as exc:
        print(f"[send] {exc}")
        return 2
    finally:
        if imap is not None:
            try:
                imap.logout()
            except Exception:
                pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Idempotently send one exact draft UID."
    )
    parser.add_argument("--uid", required=True, help="exact draft UID")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="send the draft; without this flag the command is a dry-run",
    )
    args = parser.parse_args(argv)
    return run_send(args.uid, args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
