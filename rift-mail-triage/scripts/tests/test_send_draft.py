from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from send_draft import run_send
except ImportError as exc:
    run_send = None
    SEND_DRAFT_IMPORT_ERROR = exc
else:
    SEND_DRAFT_IMPORT_ERROR = None


SENDER = "sender@example.test"
DEFAULT_MESSAGE_ID = "<one@example.test>"


def build_raw(
    message_id: str | None = DEFAULT_MESSAGE_ID,
    *,
    sender: str = SENDER,
    to: str = "target@example.test",
    cc: str | None = None,
    bcc: str | None = None,
) -> bytes:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    msg["Subject"] = "Idempotent send test"
    if message_id is not None:
        msg["Message-ID"] = message_id
    msg.set_content("test body")
    return msg.as_bytes()


def uid_bytes(uid: object) -> bytes:
    if isinstance(uid, bytes):
        return uid
    return str(uid).encode("ascii")


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(float(seconds), 0.001)


class FakeIMAP:
    """Small IMAP double with no APPEND or broad EXPUNGE API."""

    def __init__(
        self,
        drafts: dict[str, bytes] | None = None,
        *,
        sent_visible_after: int | None = 1,
        cleanup_failure: bool = False,
    ) -> None:
        self.drafts = dict(drafts or {"123": build_raw()})
        self.sent_visible_after = sent_visible_after
        self.cleanup_failure = cleanup_failure
        self.selected_folder: str | None = None
        self.select_calls: list[tuple[str, bool]] = []
        self.uid_calls: list[tuple[str, tuple[object, ...]]] = []
        self.mutations: list[tuple[str, bytes]] = []
        self.sent_search_count = 0
        self.logout_calls = 0

    @property
    def mutated_uids(self) -> list[bytes]:
        return [uid for _, uid in self.mutations]

    def list(self):
        return "OK", [
            b'(\\HasNoChildren \\Drafts) "/" "Drafts"',
            b'(\\HasNoChildren \\Sent) "/" "Sent"',
        ]

    def select(self, folder, readonly=False):
        name = folder.decode() if isinstance(folder, bytes) else str(folder)
        name = name.strip('"')
        self.selected_folder = name
        self.select_calls.append((name, bool(readonly)))
        count = len(self.drafts) if name == "Drafts" else 0
        return "OK", [str(count).encode("ascii")]

    def uid(self, command, *args):
        operation = command.decode() if isinstance(command, bytes) else str(command)
        operation = operation.upper()
        self.uid_calls.append((operation, args))

        if operation == "FETCH":
            uid = uid_bytes(args[0]).decode("ascii")
            if self.selected_folder == "Sent":
                if uid != "900" or not self._sent_is_visible():
                    return "OK", [None]
                raw = b"Message-ID: " + DEFAULT_MESSAGE_ID.encode("ascii") + b"\r\n\r\n"
                return "OK", [(b"900 (UID 900 BODY[HEADER.FIELDS] {42}", raw), b")"]

            raw = self.drafts.get(uid)
            if raw is None:
                return "OK", [None]
            meta = (
                f"{uid} (UID {uid} FLAGS (\\Draft) BODY[] {{{len(raw)}}}".encode(
                    "ascii"
                )
            )
            return "OK", [(meta, raw), b")"]

        if operation == "SEARCH":
            if self.selected_folder != "Sent":
                return "OK", [b""]
            self.sent_search_count += 1
            return "OK", [b"900" if self._sent_is_visible() else b""]

        if operation == "STORE":
            uid = uid_bytes(args[0])
            self.mutations.append(("STORE", uid))
            if self.cleanup_failure:
                return "NO", [b"STORE rejected"]
            return "OK", [b""]

        if operation == "EXPUNGE":
            uid = uid_bytes(args[0])
            self.mutations.append(("EXPUNGE", uid))
            if self.cleanup_failure:
                return "NO", [b"UID EXPUNGE rejected"]
            self.drafts.pop(uid.decode("ascii"), None)
            return "OK", [b""]

        raise AssertionError(f"unexpected IMAP UID command: {operation} {args!r}")

    def _sent_is_visible(self) -> bool:
        return (
            self.sent_visible_after is not None
            and self.sent_search_count >= self.sent_visible_after
        )

    def logout(self):
        self.logout_calls += 1
        return "BYE", [b""]


class FakeSMTP:
    def __init__(self, refused=None, error: Exception | None = None) -> None:
        self.refused = refused or {}
        self.error = error
        self.send_calls: list[tuple[EmailMessage, str | None, tuple[str, ...]]] = []
        self.quit_calls = 0

    def send_message(self, msg, from_addr=None, to_addrs=None):
        self.send_calls.append((msg, from_addr, tuple(to_addrs or [])))
        if self.error:
            raise self.error
        return self.refused

    def quit(self):
        self.quit_calls += 1


class SendSafetyTest(unittest.TestCase):
    def setUp(self) -> None:
        if run_send is None:
            self.fail(
                "expected send_draft.run_send API is unavailable: "
                f"{SEND_DRAFT_IMPORT_ERROR}"
            )

        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.receipt_root = Path(self.tempdir.name) / "receipts"
        self.imap = FakeIMAP()
        self.smtp = FakeSMTP()
        self.clock = FakeClock()
        self.env = patch.dict(
            os.environ,
            {"MAIL_USER": SENDER, "MAIL_PASS": "offline-test-secret"},
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def invoke(self, uid="123", *, apply=True, **kwargs):
        options = {
            "imap_factory": lambda: self.imap,
            "smtp_factory": lambda: self.smtp,
            "receipt_root": self.receipt_root,
            "sleep": self.clock.sleep,
            "monotonic": self.clock.monotonic,
        }
        options.update(kwargs)
        return run_send(uid, apply, **options)

    def receipt_files(self) -> list[Path]:
        return sorted(self.receipt_root.glob("**/*.json"))

    def read_only_receipt(self) -> dict:
        files = self.receipt_files()
        self.assertEqual(1, len(files), files)
        return json.loads(files[0].read_text(encoding="utf-8"))

    def write_receipt(
        self,
        *,
        status: str,
        raw: bytes | None = None,
        message_id: str = DEFAULT_MESSAGE_ID,
        mime_sha256: str | None = None,
        draft_uid: str = "123",
    ) -> Path:
        raw = raw if raw is not None else self.imap.drafts[draft_uid]
        actual_hash = hashlib.sha256(raw).hexdigest()
        receipt_hash = mime_sha256 or actual_hash
        mailbox_hash = hashlib.sha256(SENDER.encode("utf-8")).hexdigest()
        receipt_dir = self.receipt_root / mailbox_hash
        receipt_dir.mkdir(parents=True)
        path = receipt_dir / f"{receipt_hash}.json"
        payload = {
            "version": 1,
            "status": status,
            "draft_folder": "Drafts",
            "draft_uid": draft_uid,
            "message_id": message_id,
            "mime_sha256": receipt_hash,
            "subject": "Idempotent send test",
            "recipients": ["target@example.test"],
            "created_at": "2026-11-06T00:00:00Z",
            "updated_at": "2026-11-06T00:00:00Z",
            "smtp_attempt_started_at": None,
            "smtp_accepted_at": None,
            "draft_consumed_at": None,
            "sent_seen_at": None,
            "last_error": None,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def assert_rejected_before_smtp(self, uid="123") -> None:
        try:
            result = self.invoke(uid)
        except (SystemExit, ValueError):
            result = 1
        self.assertNotEqual(0, result)
        self.assertEqual([], self.smtp.send_calls)
        self.assertEqual([], self.receipt_files())

    def test_dry_run_has_zero_side_effects(self):
        result = self.invoke(apply=False)

        self.assertEqual(0, result)
        self.assertEqual([], self.smtp.send_calls)
        self.assertFalse(self.receipt_root.exists())
        self.assertEqual([], self.imap.mutations)

    def test_delayed_sent_archive_never_appends(self):
        self.imap.sent_visible_after = 3

        result = self.invoke()

        self.assertEqual(0, result)
        self.assertEqual(1, len(self.smtp.send_calls))
        self.assertGreaterEqual(self.imap.sent_search_count, 3)
        self.assertEqual("ACCEPTED", self.read_only_receipt()["status"])

    def test_second_apply_does_not_call_smtp_twice(self):
        self.assertEqual(0, self.invoke())

        self.assertEqual(0, self.invoke())
        self.assertEqual(1, len(self.smtp.send_calls))

    def test_unknown_receipt_blocks_retry(self):
        self.write_receipt(status="UNKNOWN")

        result = self.invoke()

        self.assertNotEqual(0, result)
        self.assertEqual([], self.smtp.send_calls)
        self.assertEqual("UNKNOWN", self.read_only_receipt()["status"])

    def test_accepted_consumes_exact_draft_uid_only(self):
        self.imap.drafts["124"] = build_raw("<other@example.test>")

        self.assertEqual(0, self.invoke("123"))

        self.assertEqual(
            [("STORE", b"123"), ("EXPUNGE", b"123")], self.imap.mutations
        )
        self.assertNotIn(b"124", self.imap.mutated_uids)
        self.assertIn("124", self.imap.drafts)

    def test_sent_poll_timeout_never_appends_or_resends(self):
        self.imap.sent_visible_after = None

        self.assertEqual(0, self.invoke())
        self.assertEqual(0, self.invoke())

        self.assertEqual(1, len(self.smtp.send_calls))
        receipt = self.read_only_receipt()
        self.assertEqual("ACCEPTED", receipt["status"])
        self.assertIsNone(receipt["sent_seen_at"])

    def test_smtp_exception_leaves_unknown_and_keeps_draft(self):
        self.smtp.error = OSError("connection lost after DATA")

        result = self.invoke()

        self.assertNotEqual(0, result)
        self.assertEqual(1, len(self.smtp.send_calls))
        self.assertIn("123", self.imap.drafts)
        self.assertEqual([], self.imap.mutations)
        self.assertEqual("UNKNOWN", self.read_only_receipt()["status"])

    def test_partial_recipient_refusal_leaves_unknown_and_keeps_draft(self):
        self.smtp.refused = {"target@example.test": (550, b"rejected")}

        result = self.invoke()

        self.assertNotEqual(0, result)
        self.assertEqual(1, len(self.smtp.send_calls))
        self.assertIn("123", self.imap.drafts)
        self.assertEqual([], self.imap.mutations)
        self.assertEqual("UNKNOWN", self.read_only_receipt()["status"])

    def test_same_message_id_on_new_uid_is_blocked(self):
        raw = build_raw("one@example.test")
        self.imap.drafts = {"124": raw}
        self.write_receipt(
            status="ACCEPTED",
            raw=raw,
            message_id="<one@example.test>",
            mime_sha256="0" * 64,
            draft_uid="123",
        )

        self.assertEqual(0, self.invoke("124"))
        self.assertEqual([], self.smtp.send_calls)

    def test_same_mime_hash_on_new_uid_is_blocked(self):
        raw = build_raw()
        self.imap.drafts = {"124": raw}
        self.write_receipt(
            status="ACCEPTED",
            raw=raw,
            message_id="<different@example.test>",
            draft_uid="123",
        )

        self.assertEqual(0, self.invoke("124"))
        self.assertEqual([], self.smtp.send_calls)

    def test_draft_cleanup_failure_keeps_accepted_and_blocks_resend(self):
        self.imap.cleanup_failure = True

        self.assertEqual(0, self.invoke())
        self.assertEqual("ACCEPTED", self.read_only_receipt()["status"])
        self.assertEqual(0, self.invoke())
        self.assertEqual(1, len(self.smtp.send_calls))
        self.assertIn("123", self.imap.drafts)

    def test_prepared_receipt_can_continue_before_any_smtp_attempt(self):
        self.write_receipt(status="PREPARED")

        self.assertEqual(0, self.invoke())

        self.assertEqual(1, len(self.smtp.send_calls))
        self.assertEqual("ACCEPTED", self.read_only_receipt()["status"])

    def test_missing_message_id_is_rejected_before_receipt_or_smtp(self):
        self.imap.drafts = {"123": build_raw(message_id=None)}

        self.assert_rejected_before_smtp()

    def test_from_must_match_authenticated_mailbox(self):
        self.imap.drafts = {"123": build_raw(sender="imposter@example.test")}

        self.assert_rejected_before_smtp()


if __name__ == "__main__":
    unittest.main()
