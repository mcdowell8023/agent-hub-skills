"""rift-mail 入口脚本跨平台凭据路径测试。

覆盖优先级：① env (MAIL_USER/MAIL_PASS) → ② macOS security 钥匙串 → ③ Linux 600 凭据文件。
测试通过 fake python3 捕获入口脚本注入的凭据环境变量，不回显真实凭据。
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
RIFT_MAIL = SCRIPT_DIR / "rift-mail"

FAKE_PYTHON3 = """#!/bin/sh
if [ "$1" = "-c" ]; then
  printf '%s\\n' 'sender@example.test'
  exit 0
fi
printf 'MAIL_USER=%s\\nMAIL_PASS=%s\\n' "$MAIL_USER" "$MAIL_PASS" > "$RIFT_MAIL_TEST_LOG"
"""

FAKE_SECURITY = """#!/bin/sh
printf '%s' 'keychain-secret'
"""


class RiftMailCredsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "creds.log"

        self._write_exec(self.bin / "python3", FAKE_PYTHON3)
        self._write_exec(self.bin / "security", FAKE_SECURITY)
        self.uname = self.bin / "uname"
        self._set_platform("Linux")

        self.env = dict(os.environ)
        self.env.update(
            {
                "HOME": str(self.home),
                "PATH": f"{self.bin}:/usr/bin:/bin",
                "RIFT_MAIL_TEST_LOG": str(self.log),
                # 测试夹具不依赖 config.json：默认给邮箱，专测 pass 的来源路径
                "MAIL_USER": "sender@example.test",
            }
        )
        # 移除可能从宿主继承的凭据变量，保证夹具纯净
        self.env.pop("MAIL_PASS", None)
        self.env.pop("RIFT_MAIL_CRED_FILE", None)

    def _write_exec(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    def _set_platform(self, name: str) -> None:
        self._write_exec(self.uname, f"#!/bin/sh\nprintf '%s\\n' '{name}'\n")

    def _write_cred_file(self, value: str, path: Path | None = None) -> Path:
        target = path or (self.home / ".local/share/rift-mail-triage/mail_credentials")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value + "\n", encoding="utf-8")
        target.chmod(0o600)
        return target

    def _creds(self) -> dict[str, str]:
        lines = self.log.read_text(encoding="utf-8").splitlines()
        return dict(line.split("=", 1) for line in lines if "=" in line)

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(RIFT_MAIL), *args],
            text=True,
            capture_output=True,
            env=self.env,
            check=False,
        )

    def test_env_creds_take_priority_over_keychain_and_file(self):
        # env 已设，即便钥匙串与凭据文件另有值，也必须用 env 且不被覆盖
        self._set_platform("Darwin")
        self._write_cred_file("filepass")
        self.env["MAIL_USER"] = "env@example.test"
        self.env["MAIL_PASS"] = "envpass"

        result = self.run_cli("selfcheck")

        self.assertEqual(0, result.returncode, result.stderr)
        creds = self._creds()
        self.assertEqual("env@example.test", creds["MAIL_USER"])
        self.assertEqual("envpass", creds["MAIL_PASS"])

    def test_macos_uses_security_keychain(self):
        self._set_platform("Darwin")

        result = self.run_cli("selfcheck")

        self.assertEqual(0, result.returncode, result.stderr)
        creds = self._creds()
        self.assertEqual("sender@example.test", creds["MAIL_USER"])
        self.assertEqual("keychain-secret", creds["MAIL_PASS"])

    def test_linux_falls_back_to_600_cred_file(self):
        self._set_platform("Linux")
        self._write_cred_file("filepass")

        result = self.run_cli("selfcheck")

        self.assertEqual(0, result.returncode, result.stderr)
        creds = self._creds()
        self.assertEqual("sender@example.test", creds["MAIL_USER"])
        self.assertEqual("filepass", creds["MAIL_PASS"])

    def test_linux_cred_file_override_env(self):
        self._set_platform("Linux")
        custom = self.root / "custom-creds"
        self._write_cred_file("custompass", custom)
        self.env["RIFT_MAIL_CRED_FILE"] = str(custom)

        result = self.run_cli("selfcheck")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("custompass", self._creds()["MAIL_PASS"])

    def test_linux_missing_cred_file_fails_cleanly(self):
        self._set_platform("Linux")

        result = self.run_cli("selfcheck")

        self.assertNotEqual(0, result.returncode)
        self.assertNotIn("keychain-secret", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
