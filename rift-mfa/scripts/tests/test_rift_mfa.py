#!/usr/bin/env python3
"""rift-mfa TDD tests.

All tests use a temporary fake seed file (RIFT_MFA_SEEDS) and a fixed clock
(RIFT_MFA_NOW). No real seed/credential is ever read or printed.
Run: python3 rift-mfa/scripts/tests/test_rift_mfa.py
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
SCRIPTS = HERE.parent.parent
CLI = SCRIPTS / "rift-mfa"

# RFC 6238 Appendix B test secret: ASCII "12345678901234567890" in base32.
RFC_SECRET_B32 = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
# (unix_time, expected 8-digit RFC vector) -> 6-digit = vector % 1_000_000
RFC_VECTORS = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]


class RiftMfaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmpdir = Path(self.tmp.name)
        self.seed_file = self.tmpdir / "seeds.json"
        self.base_env = os.environ.copy()
        self.base_env.pop("RIFT_MFA_SEEDS", None)
        self.base_env.pop("RIFT_MFA_NOW", None)

    def write_seeds(self, mapping, mode=0o600):
        self.seed_file.write_text(json.dumps(mapping), encoding="utf-8")
        os.chmod(self.seed_file, mode)

    def run_cli(self, *args, now=None, seeds=None):
        env = self.base_env.copy()
        env["RIFT_MFA_SEEDS"] = str(seeds or self.seed_file)
        if now is not None:
            env["RIFT_MFA_NOW"] = str(now)
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            env=env, capture_output=True, text=True, timeout=10,
        )

    # ---- 1. RFC 6238 official vectors (SHA1/30s/6 digits) ----
    def test_01_rfc6238_vectors(self):
        self.write_seeds({"rfc": RFC_SECRET_B32})
        for t, vector8 in RFC_VECTORS:
            with self.subTest(t=t):
                want = str(int(vector8) % 1_000_000).zfill(6)
                r = self.run_cli("rfc", now=t)
                self.assertEqual(r.returncode, 0, f"t={t}: {r.stderr}")
                self.assertEqual(r.stdout.strip(), want)

    # ---- 2. otpauth:// URI form parses to same code ----
    def test_02_otpauth_uri(self):
        uri = "otpauth://totp/Test:rfc?secret=" + RFC_SECRET_B32 + "&issuer=Test&digits=6&period=30"
        self.write_seeds({"rfc": uri})
        r = self.run_cli("rfc", now=59)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "287082")

    # ---- 3. list shows keys only, never seed values ----
    def test_03_list_keys_only(self):
        self.write_seeds({"github-work": RFC_SECRET_B32, "aws-prod": "JBSWY3DPEHPK3PXP"})
        r = self.run_cli("list")
        self.assertEqual(r.returncode, 0)
        self.assertIn("github-work", r.stdout)
        self.assertIn("aws-prod", r.stdout)
        self.assertNotIn(RFC_SECRET_B32, r.stdout)
        self.assertNotIn("JBSWY3DPEHPK3PXP", r.stdout)
        self.assertNotIn("otpauth", r.stdout)

    # ---- 4. unsafe seed-file permission -> exit 4, no code ----
    def test_04_unsafe_permission_rejected(self):
        self.write_seeds({"rfc": RFC_SECRET_B32}, mode=0o644)
        r = self.run_cli("rfc", now=59)
        self.assertEqual(r.returncode, 4)
        self.assertEqual(r.stdout.strip(), "")

    # ---- 5. missing seed file -> exit 4 ----
    def test_05_missing_seed_file(self):
        missing = self.tmpdir / "nope.json"
        r = self.run_cli("rfc", now=59, seeds=missing)
        self.assertEqual(r.returncode, 4)
        self.assertEqual(r.stdout.strip(), "")

    # ---- 6. unknown entry -> exit 3 ----
    def test_06_unknown_entry(self):
        self.write_seeds({"rfc": RFC_SECRET_B32})
        r = self.run_cli("does-not-exist", now=59)
        self.assertEqual(r.returncode, 3)
        self.assertEqual(r.stdout.strip(), "")

    # ---- 7. ambiguous keyword -> exit 5 ----
    def test_07_ambiguous_keyword(self):
        self.write_seeds({"aws-prod": RFC_SECRET_B32, "aws-dev": "JBSWY3DPEHPK3PXP"})
        r = self.run_cli("aws", now=59)
        self.assertEqual(r.returncode, 5)
        self.assertEqual(r.stdout.strip(), "")

    # ---- 8. unique keyword resolves ----
    def test_08_unique_keyword(self):
        self.write_seeds({"github-work": RFC_SECRET_B32})
        r = self.run_cli("github", now=59)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "287082")

    # ---- 9. exact name wins over substring ----
    def test_09_exact_wins(self):
        self.write_seeds({"aws": RFC_SECRET_B32, "aws-prod": "JBSWY3DPEHPK3PXP"})
        r = self.run_cli("aws", now=59)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "287082")

    # ---- 10. window boundary: --ahead rolls into next window ----
    def test_10_ahead_window_boundary(self):
        self.write_seeds({"rfc": RFC_SECRET_B32})
        # code at start of window [90,120) with no ahead
        base = self.run_cli("rfc", now=90)
        self.assertEqual(base.returncode, 0)
        # 1s left in window [60,90) but --ahead 5 -> next window's code
        ahead = self.run_cli("rfc", "--ahead", "5", now=89)
        self.assertEqual(ahead.returncode, 0)
        self.assertEqual(ahead.stdout.strip(), base.stdout.strip())

    # ---- 11. no argument -> exit 2 ----
    def test_11_arg_error(self):
        self.write_seeds({"rfc": RFC_SECRET_B32})
        r = self.run_cli()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout.strip(), "")

    # ---- 12. stdout is exactly 6 digits, nothing else ----
    def test_13_stdout_clean_six_digits(self):
        self.write_seeds({"rfc": RFC_SECRET_B32})
        r = self.run_cli("rfc", now=59)
        self.assertRegex(r.stdout, r"^\d{6}\s*$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
