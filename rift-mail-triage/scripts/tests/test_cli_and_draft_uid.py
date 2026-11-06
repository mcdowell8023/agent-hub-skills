from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1]
RIFT_MAIL = SCRIPT_DIR / "rift-mail"
sys.path.insert(0, str(SCRIPT_DIR))

import save_draft  # noqa: E402
import send_draft  # noqa: E402


class RiftMailCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.log_path = self.root / "python-args.txt"

        security = self.bin_dir / "security"
        security.write_text("#!/bin/sh\nprintf '%s' 'offline-secret'\n", encoding="utf-8")
        security.chmod(0o755)

        python3 = self.bin_dir / "python3"
        python3.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$RIFT_MAIL_TEST_LOG\"\n",
            encoding="utf-8",
        )
        python3.chmod(0o755)

        self.env = dict(os.environ)
        self.env.update(
            {
                "MAIL_USER": "sender@example.test",
                "PATH": f"{self.bin_dir}:/usr/bin:/bin",
                "RIFT_MAIL_TEST_LOG": str(self.log_path),
            }
        )

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(RIFT_MAIL), *args],
            text=True,
            capture_output=True,
            env=self.env,
            check=False,
        )

    def test_send_routes_exact_uid_to_send_draft_and_defaults_to_dry_run(self):
        result = self.run_cli("send", "--uid", "456")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            [str(SCRIPT_DIR / "send_draft.py"), "--uid", "456"],
            self.log_path.read_text(encoding="utf-8").splitlines(),
        )

    def test_send_apply_is_forwarded_explicitly(self):
        result = self.run_cli("send", "--uid", "456", "--apply")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            [str(SCRIPT_DIR / "send_draft.py"), "--uid", "456", "--apply"],
            self.log_path.read_text(encoding="utf-8").splitlines(),
        )

    def test_help_states_send_is_dry_run_by_default(self):
        result = self.run_cli()

        self.assertEqual(1, result.returncode)
        self.assertIn("send --uid UID [--apply]", result.stdout)
        self.assertIn("默认 dry-run", result.stdout)


class SendDraftMainTest(unittest.TestCase):
    def test_main_defaults_to_dry_run_and_returns_run_send_exit_code(self):
        with patch.object(send_draft, "run_send", return_value=17) as run_send:
            result = send_draft.main(["--uid", "456"])

        self.assertEqual(17, result)
        run_send.assert_called_once_with("456", False)

    def test_main_forwards_apply_explicitly(self):
        with patch.object(send_draft, "run_send", return_value=0) as run_send:
            result = send_draft.main(["--uid", "456", "--apply"])

        self.assertEqual(0, result)
        run_send.assert_called_once_with("456", True)

    def test_script_help_documents_uid_and_apply_without_running_send(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "send_draft.py"), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--uid", result.stdout)
        self.assertIn("--apply", result.stdout)


class FakeDraftIMAP:
    def __init__(
        self,
        *,
        append_response: list[bytes],
        fallback_uids: tuple[str, ...] = (),
        matching_uids: tuple[str, ...] = (),
    ) -> None:
        self.append_response = append_response
        self.fallback_uids = fallback_uids
        self.matching_uids = set(matching_uids)
        self.appended_raw: bytes | None = None
        self.appended_message_id: str | None = None
        self.select_calls: list[tuple[str, bool]] = []
        self.uid_calls: list[tuple[str, tuple[object, ...]]] = []
        self.logout_calls = 0

    def list(self):
        return "OK", [b'(\\HasNoChildren \\Drafts) "/" "Drafts"']

    def select(self, folder, readonly=False):
        name = folder.decode() if isinstance(folder, bytes) else str(folder)
        self.select_calls.append((name.strip('"'), bool(readonly)))
        return "OK", [str(len(self.fallback_uids)).encode("ascii")]

    def search(self, charset, *criteria):
        # Existing same-subject detection runs before APPEND. It is not allowed
        # to supply the new draft UID, so keep it empty and audit UID calls below.
        return "OK", [b""]

    def append(self, folder, flags, internaldate, raw):
        self.appended_raw = bytes(raw)
        msg = BytesParser(policy=policy.default).parsebytes(self.appended_raw)
        self.appended_message_id = str(msg["Message-ID"])
        return "OK", self.append_response

    def uid(self, command, *args):
        operation = str(command).upper()
        self.uid_calls.append((operation, args))
        if operation == "SEARCH":
            return "OK", [" ".join(self.fallback_uids).encode("ascii")]
        if operation == "FETCH":
            uid = (
                args[0].decode("ascii")
                if isinstance(args[0], bytes)
                else str(args[0])
            )
            message_id = (
                self.appended_message_id
                if uid in self.matching_uids
                else f"<decoy-{uid}@example.test>"
            )
            # Same subject deliberately appears on every candidate. A subject-
            # based UID guess would be ambiguous or select the wrong message.
            raw = (
                f"Message-ID: {message_id}\r\n"
                "Subject: Same Subject\r\n"
                "\r\n"
            ).encode("ascii")
            return "OK", [
                (f"1 (UID {uid} BODY[HEADER] {{{len(raw)}}}".encode(), raw),
                b")",
            ]
        raise AssertionError(f"unexpected UID operation: {operation} {args!r}")

    def logout(self):
        self.logout_calls += 1
        return "BYE", [b""]


class SaveDraftUidTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.json_path = Path(self.tempdir.name) / "draft.json"
        self.json_path.write_text(
            json.dumps(
                {
                    "to": "target@example.test",
                    "subject": "Same Subject",
                    "body": "测试正文",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def invoke(self, imap: FakeDraftIMAP) -> str:
        stdout = io.StringIO()
        with (
            patch.object(
                save_draft,
                "get_credentials",
                return_value=("sender@example.test", "secret"),
            ),
            patch.object(save_draft, "imap_connect", return_value=imap),
            patch.object(sys, "argv", ["save_draft.py", "--json", str(self.json_path)]),
            redirect_stdout(stdout),
        ):
            save_draft.main()
        return stdout.getvalue()

    def test_appenduid_is_preferred_and_prints_exact_next_command(self):
        imap = FakeDraftIMAP(
            append_response=[b"[APPENDUID 38505 456] Append completed"]
        )

        output = self.invoke(imap)

        self.assertIn("[draft] uid=456", output)
        self.assertIn("[draft] next: rift-mail send --uid 456", output)
        self.assertEqual([], imap.uid_calls, "APPENDUID should avoid any fallback scan")
        self.assertEqual(1, imap.logout_calls)

    def test_missing_appenduid_scans_readonly_and_matches_only_message_id(self):
        imap = FakeDraftIMAP(
            append_response=[b"Append completed"],
            fallback_uids=("111", "222"),
            matching_uids=("222",),
        )

        output = self.invoke(imap)

        self.assertIn("[draft] uid=222", output)
        self.assertIn("[draft] next: rift-mail send --uid 222", output)
        self.assertTrue(imap.select_calls[-1][1], imap.select_calls)
        self.assertEqual("SEARCH", imap.uid_calls[0][0])
        self.assertEqual((None, "ALL"), imap.uid_calls[0][1])
        fetch_args = [args for operation, args in imap.uid_calls if operation == "FETCH"]
        self.assertTrue(fetch_args)
        self.assertTrue(
            all("MESSAGE-ID" in str(args[1]).upper() for args in fetch_args),
            fetch_args,
        )

    def test_missing_appenduid_rejects_non_unique_message_id_matches(self):
        for matching_uids in ((), ("111", "222")):
            with self.subTest(matching_uids=matching_uids):
                imap = FakeDraftIMAP(
                    append_response=[b"Append completed"],
                    fallback_uids=("111", "222"),
                    matching_uids=matching_uids,
                )
                stdout = io.StringIO()
                with self.assertRaises(SystemExit) as caught:
                    with (
                        patch.object(
                            save_draft,
                            "get_credentials",
                            return_value=("sender@example.test", "secret"),
                        ),
                        patch.object(save_draft, "imap_connect", return_value=imap),
                        patch.object(
                            sys,
                            "argv",
                            ["save_draft.py", "--json", str(self.json_path)],
                        ),
                        redirect_stdout(stdout),
                    ):
                        save_draft.main()

                self.assertIn("Message-ID", str(caught.exception))
                self.assertNotIn("[draft] uid=", stdout.getvalue())
                self.assertEqual(1, imap.logout_calls)


if __name__ == "__main__":
    unittest.main()
