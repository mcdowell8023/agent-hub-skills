"""rift-session core flow tests: config, status/login/relogin/keepalive, backup/restore, drill."""
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import (CODE, DEVICE_VALUE, NOW, PASSWORD, SESSION_VALUE, USER, EngineTestCase,  # noqa: E402
                     FakeSite, mode, rs, site_config)


class ConfigValidationTest(EngineTestCase):
    def test_valid_config_has_no_errors(self):
        self.assertEqual(rs.validate_config(site_config(self.tmp)), [])

    def test_example_config_is_valid(self):
        ex = json.loads((rs.ENGINE_DIR / "examples" / "example-site.json").read_text())
        self.assertEqual(rs.validate_config(ex), [])

    def test_missing_required_fields_reported_by_name(self):
        cfg = site_config(self.tmp)
        for k in ("base_url", "login_form", "allowed_hosts", "secret_refs"):
            del cfg[k]
        errs = " ".join(rs.validate_config(cfg))
        for k in ("base_url", "login_form", "allowed_hosts", "secret_refs"):
            self.assertIn(k, errs)

    def test_bad_values_rejected(self):
        cases = [
            dict(backend="chrome"),
            dict(two_factor={"type": "sms"}),
            dict(logged_in_check={"title_regex": "("}),
            dict(logged_in_check={}),
            dict(session_cookie_names=[]),
            dict(relogin_policy={"max_per_hour": 0}),
            dict(login_form={"username": "#u", "submit": "#s"}),  # no password
        ]
        for over in cases:
            with self.subTest(over=over):
                self.assertTrue(rs.validate_config(site_config(self.tmp, **over)))

    def test_urls_must_be_within_allowed_hosts(self):
        errs = rs.validate_config(site_config(self.tmp, login_url="https://evil.example.org/login"))
        self.assertTrue(any("allowed_hosts" in e for e in errs))

    def test_totp_needs_entry_name(self):
        cfg = site_config(self.tmp, two_factor={"type": "totp:", "code_input": "#c", "submit": "#s",
                                                "page_title_regex": "x"})
        self.assertTrue(rs.validate_config(cfg))

    def test_cli_reports_validation_error_with_exit_4(self):
        self.write_site(allowed_hosts=[])
        rc, out, err = self.run_cli(["status", "demo"], FakeSite())
        self.assertEqual(rc, 4)
        self.assertIn("allowed_hosts", out + err)

    def test_cli_rejects_group_readable_config(self):
        self.write_site()
        os.chmod(self.home / "sites" / "demo.json", 0o644)
        rc, out, err = self.run_cli(["status", "demo"], FakeSite())
        self.assertEqual(rc, 4)
        self.assertIn("600", out + err)

    def test_unknown_site_exit_4(self):
        rc, out, err = self.run_cli(["status", "nope"], FakeSite())
        self.assertEqual(rc, 4)


class SecretRefsTest(EngineTestCase):
    def test_json_env_and_md_row_sources(self):
        j = self.tmp / "s.json"
        j.write_text(json.dumps({"u": "alice", "p": "pw1"}))
        self.assertEqual(rs.load_credentials({"file": str(j), "format": "json", "user_key": "u",
                                              "password_key": "p"}), ("alice", "pw1"))
        e = self.tmp / "s.env"
        e.write_text("USER_NAME=bob\nUSER_PASS='pw2'\n")
        self.assertEqual(rs.load_credentials({"file": str(e), "format": "env", "user_key": "USER_NAME",
                                              "password_key": "USER_PASS"}), ("bob", "pw2"))
        m = self.tmp / "c.md"
        m.write_text("| 其它 | `x` / `y` |\n| 后台账号 | `carol` / `pw3` | 备注 |\n")
        self.assertEqual(rs.load_credentials({"file": str(m), "format": "md_row",
                                              "row_match": "后台账号"}), ("carol", "pw3"))

    def test_missing_secret_is_config_error(self):
        with self.assertRaises(rs.ConfigError):
            rs.load_credentials({"file": str(self.tmp / "none.json"), "format": "json",
                                 "user_key": "u", "password_key": "p"})
        with self.assertRaises(rs.ConfigError) as cm:
            m = self.tmp / "c2.md"
            m.write_text("| a | `x` / `y` |\n")
            rs.load_credentials({"file": str(m), "format": "md_row", "row_match": "后台账号"})
        self.assertNotIn("`x`", str(cm.exception))


class DetectStateTest(EngineTestCase):
    def test_states(self):
        cfg = site_config(self.tmp)
        s = FakeSite()
        self.assertEqual(rs.detect_state(s, cfg, s.goto("https://app.example.com/")), "LOGIN_PAGE")
        s.login_as()
        self.assertEqual(rs.detect_state(s, cfg, s.page_state()), "LOGGED_IN")
        s.page = "2fa"
        self.assertEqual(rs.detect_state(s, cfg, s.page_state()), "TWO_FACTOR")
        s.weird = True
        self.assertEqual(rs.detect_state(s, cfg, s.page_state()), "UNKNOWN")

    def test_selector_and_text_checks(self):
        s = FakeSite()
        s.login_as()
        cfg = site_config(self.tmp, logged_in_check={"selector": "#dash-marker"})
        self.assertEqual(rs.detect_state(s, cfg, s.page_state()), "LOGGED_IN")
        cfg = site_config(self.tmp, logged_in_check={"text": "Welcome"})
        self.assertEqual(rs.detect_state(s, cfg, s.page_state()), "LOGGED_IN")
        s.page = "login"
        self.assertEqual(rs.detect_state(s, cfg, s.page_state()), "LOGIN_PAGE")


class StatusTest(EngineTestCase):
    def test_logged_in(self):
        self.write_site()
        s = FakeSite()
        s.login_as()
        rc, out, err = self.run_cli(["status", "demo"], s)
        self.assertEqual(rc, 0)
        self.assertIn("state=LOGGED_IN", out)
        self.assertIn("device_token_days=20", out)
        self.assertNoSecrets(out, err)
        self.assertEqual(len(out.strip().splitlines()), 2)  # machine line + human line

    def test_not_logged_in_exit_3(self):
        self.write_site()
        rc, out, _ = self.run_cli(["status", "demo"], FakeSite())
        self.assertEqual(rc, 3)
        self.assertIn("state=SESSION_LOST", out)


class LoginTest(EngineTestCase):
    def test_two_step_login_fills_secrets_and_ends_logged_in(self):
        self.write_site()
        s = FakeSite()
        rc, out, err = self.run_cli(["login", "demo"], s)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("state=LOGGED_IN", out)
        self.assertEqual(s.clicks, ["#next", "#submit"])
        pw_fills = [f for f in s.fills if f[0] == "#pw"]
        self.assertEqual(pw_fills, [("#pw", PASSWORD, True)])
        self.assertTrue(all(f[2] for f in s.fills))  # every fill is marked secret
        self.assertNoSecrets(out, err, self.log_text())

    def test_single_page_login(self):
        form = {"username": "#user", "password": "#pw", "submit": "#submit"}
        self.write_site(login_form=form)
        s = FakeSite(two_step=False)
        rc, out, _ = self.run_cli(["login", "demo"], s)
        self.assertEqual(rc, 0)
        self.assertEqual(s.clicks, ["#submit"])

    def test_already_logged_in_does_not_touch_form(self):
        self.write_site()
        s = FakeSite()
        s.login_as()
        rc, out, _ = self.run_cli(["login", "demo"], s)
        self.assertEqual(rc, 0)
        self.assertEqual(s.fills, [])

    def test_manual_code_stops_with_need_code_then_continues_with_code(self):
        self.write_site()
        s = FakeSite(require_2fa=True)
        rc, out, err = self.run_cli(["login", "demo"], s)
        self.assertEqual(rc, 2)
        self.assertIn("state=NEED_CODE", out)
        self.assertIn("--code", out)
        self.assertEqual(s.page, "2fa")
        self.assertNotIn("#code", [f[0] for f in s.fills])
        # second call continues in the same page: must not navigate away to the login url
        s.calls.clear()
        rc, out, err = self.run_cli(["login", "demo", "--code", CODE], s)
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(s.names("goto"), [])
        self.assertTrue(s.remember_checked)
        self.assertIn(("#code", CODE, True), s.fills)
        self.assertIn("DEV_TOKEN", s.cookies)
        self.assertNoSecrets(out, err, self.log_text())

    def test_wrong_code_fails_without_retry(self):
        self.write_site()
        s = FakeSite(require_2fa=True)
        self.run_cli(["login", "demo"], s)
        rc, out, _ = self.run_cli(["login", "demo", "--code", "000000"], s)
        self.assertEqual(rc, 3)
        self.assertEqual(len([f for f in s.fills if f[0] == "#code"]), 1)

    def test_code_without_2fa_page_is_refused(self):
        self.write_site()
        s = FakeSite()
        rc, out, _ = self.run_cli(["login", "demo", "--code", CODE], s)
        self.assertEqual(rc, 3)
        self.assertEqual(s.fills, [])

    def test_code_from_stdin_dash(self):
        self.write_site()
        s = FakeSite(require_2fa=True)
        self.run_cli(["login", "demo"], s)
        import io
        from unittest import mock
        with mock.patch("sys.stdin", io.StringIO(CODE + "\n")):
            rc, out, _ = self.run_cli(["login", "demo", "--code", "-"], s)
        self.assertEqual(rc, 0)

    def test_totp_waits_for_window_and_submits(self):
        mfa = self.tmp / "fake-mfa"
        mfa.write_text("#!/bin/sh\necho 123456\n")
        os.chmod(mfa, 0o755)
        os.environ["RIFT_MFA_BIN"] = str(mfa)
        self.addCleanup(os.environ.pop, "RIFT_MFA_BIN", None)
        tf = {"type": "totp:demo-entry", "page_title_regex": "Two-Factor", "code_input": "#code",
              "submit": "#code-submit", "remember": "#remember"}
        self.write_site(two_factor=tf)
        s = FakeSite(require_2fa=True)
        rc, out, err = self.run_cli(["login", "demo"], s, now=NOW + 20)  # 10s left in window
        self.assertEqual(rc, 0, out + err)
        self.assertTrue(self.sleeps and self.sleeps[0] >= 10)
        self.assertIn(("#code", CODE, True), s.fills)
        self.assertNoSecrets(out, err)

    def test_totp_no_wait_when_enough_time_left(self):
        mfa = self.tmp / "fake-mfa"
        mfa.write_text("#!/bin/sh\necho 123456\n")
        os.chmod(mfa, 0o755)
        os.environ["RIFT_MFA_BIN"] = str(mfa)
        self.addCleanup(os.environ.pop, "RIFT_MFA_BIN", None)
        tf = {"type": "totp:demo-entry", "page_title_regex": "Two-Factor", "code_input": "#code",
              "submit": "#code-submit"}
        self.write_site(two_factor=tf)
        s = FakeSite(require_2fa=True)
        rc, _, _ = self.run_cli(["login", "demo"], s, now=NOW + 5)
        self.assertEqual(rc, 0)
        self.assertEqual(self.sleeps, [])

    def test_wrong_password_fails_no_retry(self):
        self.write_site()
        s = FakeSite(password="other")
        rc, out, _ = self.run_cli(["login", "demo"], s)
        self.assertEqual(rc, 3)
        self.assertIn("LOGIN_FAILED", out)
        self.assertEqual(s.clicks.count("#submit"), 1)

    def test_host_redirect_outside_allowed_hosts_blocks_before_filling(self):
        self.write_site()
        s = FakeSite()
        s.landing_host = "evil.example.org"
        rc, out, err = self.run_cli(["login", "demo"], s)
        self.assertEqual(rc, 4)
        self.assertEqual(s.fills, [])
        self.assertIn("evil.example.org", out + err)

    def test_password_in_backend_error_is_scrubbed(self):
        self.write_site()
        s = FakeSite()

        def boom(selector, value, secret=False):
            if selector == "#pw":
                raise RuntimeError(f"cannot fill {value}")
        s.fill = boom
        rc, out, err = self.run_cli(["login", "demo"], s)
        self.assertNotEqual(rc, 0)
        self.assertNoSecrets(out, err, self.log_text())


class ReloginTest(EngineTestCase):
    def test_relogin_with_device_token_succeeds_without_code(self):
        self.write_site()
        s = FakeSite(require_2fa=True)
        s.login_as()
        del s.cookies["SID"]
        s.page = "login"
        rc, out, _ = self.run_cli(["relogin", "demo"], s)
        self.assertEqual(rc, 0)
        self.assertIn("state=LOGGED_IN", out)

    def test_relogin_stops_at_2fa_page_and_never_submits_code(self):
        self.write_site()
        s = FakeSite(require_2fa=True)
        rc, out, _ = self.run_cli(["relogin", "demo"], s)
        self.assertEqual(rc, 2)
        self.assertIn("NEED_CODE", out)
        self.assertNotIn("#code", [f[0] for f in s.fills])
        self.assertNotIn("#code-submit", s.clicks)

    def test_relogin_never_submits_code_even_with_totp_configured(self):
        tf = {"type": "totp:demo-entry", "page_title_regex": "Two-Factor", "code_input": "#code",
              "submit": "#code-submit", "remember": "#remember"}
        self.write_site(two_factor=tf)
        s = FakeSite(require_2fa=True)
        rc, out, _ = self.run_cli(["relogin", "demo"], s)
        self.assertEqual(rc, 2)
        self.assertNotIn("#code", [f[0] for f in s.fills])
        self.assertEqual(self.sleeps, [])

    def test_rate_limit_one_per_hour(self):
        self.write_site()
        s = FakeSite(require_2fa=True)
        rc1, _, _ = self.run_cli(["relogin", "demo"], s)
        s.fills.clear(), s.clicks.clear()
        rc2, out, _ = self.run_cli(["relogin", "demo"], s, now=NOW + 600)
        self.assertEqual((rc1, rc2), (2, 3))
        self.assertIn("RELOGIN_SKIPPED", out)
        self.assertEqual(s.fills, [])
        rc3, _, _ = self.run_cli(["relogin", "demo"], s, now=NOW + 3700)
        self.assertEqual(rc3, 2)

    def test_rate_limit_respects_policy_max(self):
        self.write_site(relogin_policy={"max_per_hour": 2})
        s = FakeSite(require_2fa=True)
        rcs = [self.run_cli(["relogin", "demo"], s, now=NOW + i * 60)[0] for i in range(3)]
        self.assertEqual(rcs, [2, 2, 3])


class KeepaliveTest(EngineTestCase):
    def test_logged_in(self):
        self.write_site()
        s = FakeSite()
        s.login_as()
        rc, out, _ = self.run_cli(["keepalive", "demo"], s)
        self.assertEqual(rc, 0)
        self.assertIn("state=LOGGED_IN", out)
        self.assertIn(" demo LOGGED_IN ", self.log_text())
        self.assertEqual(s.names("fill"), [])

    def test_session_lost_triggers_auto_relogin(self):
        self.write_site()
        s = FakeSite(require_2fa=True)
        s.login_as()
        del s.cookies["SID"]
        rc, out, _ = self.run_cli(["keepalive", "demo"], s)
        self.assertEqual(rc, 0)
        self.assertIn("state=LOGGED_IN", out)
        self.assertIn("via=relogin", out)
        self.assertIn("SESSION_LOST", self.log_text())

    def test_session_lost_and_2fa_needed_exit_2(self):
        self.write_site()
        s = FakeSite(require_2fa=True)
        rc, out, _ = self.run_cli(["keepalive", "demo"], s)
        self.assertEqual(rc, 2)
        self.assertIn("NEED_CODE", out)

    def test_auto_relogin_disabled_exit_3(self):
        self.write_site(keepalive={"url": "https://app.example.com/", "interval_minutes": 10,
                                   "auto_relogin": False})
        s = FakeSite()
        rc, out, _ = self.run_cli(["keepalive", "demo"], s)
        self.assertEqual(rc, 3)
        self.assertIn("state=SESSION_LOST", out)
        self.assertEqual(s.fills, [])

    def test_unknown_does_not_relogin(self):
        self.write_site()
        s = FakeSite()
        s.weird = True
        rc, out, _ = self.run_cli(["keepalive", "demo"], s)
        self.assertEqual(rc, 3)
        self.assertIn("state=UNKNOWN", out)
        self.assertEqual(s.fills, [])

    def test_keepalive_failure_is_rate_limited_like_relogin(self):
        self.write_site()
        s = FakeSite(password="other")
        r1 = self.run_cli(["keepalive", "demo"], s)[0]
        s.fills.clear()
        r2 = self.run_cli(["keepalive", "demo"], s, now=NOW + 600)[0]
        self.assertEqual((r1, r2), (3, 3))
        self.assertEqual(s.fills, [])

    def test_log_rotation_over_1mb(self):
        self.write_site()
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "demo.log").write_text("x" * (1024 * 1024 + 10))
        s = FakeSite()
        s.login_as()
        self.run_cli(["keepalive", "demo"], s)
        self.assertTrue((self.state / "demo.log.1").exists())
        self.assertLess((self.state / "demo.log").stat().st_size, 1000)


class BackupRestoreTest(EngineTestCase):
    def test_backup_writes_0600_and_never_prints_values(self):
        self.write_site()
        s = FakeSite()
        s.login_as()
        rc, out, err = self.run_cli(["backup", "demo"], s)
        self.assertEqual(rc, 0)
        f = self.secrets_dir / "rift-session-demo.json"
        self.assertTrue(f.exists())
        self.assertEqual(mode(f), 0o600)
        self.assertEqual(mode(self.secrets_dir), 0o700)
        data = json.loads(f.read_text())
        self.assertEqual({c["name"] for c in data["cookies"]}, {"SID", "DEV_TOKEN"})
        self.assertNoSecrets(out, err)

    def test_backup_refuses_when_not_logged_in(self):
        self.write_site()
        rc, out, _ = self.run_cli(["backup", "demo"], FakeSite())
        self.assertEqual(rc, 3)
        self.assertFalse((self.secrets_dir / "rift-session-demo.json").exists())

    def test_restore_brings_session_back_and_prints_no_values(self):
        self.write_site()
        s = FakeSite()
        s.login_as()
        self.run_cli(["backup", "demo"], s)
        s.cookies.clear()
        s.page = "login"
        rc, out, err = self.run_cli(["restore", "demo"], s)
        self.assertEqual(rc, 0)
        self.assertIn("SID", s.cookies)
        self.assertIn("state=LOGGED_IN", out)
        self.assertNoSecrets(out, err)

    def test_restore_without_backup_exit_4(self):
        self.write_site()
        rc, _, _ = self.run_cli(["restore", "demo"], FakeSite())
        self.assertEqual(rc, 4)

    def test_backend_without_cookie_support_exit_4(self):
        self.write_site()
        s = FakeSite()
        s.login_as()

        def unsupported(urls):
            raise rs.BackendUnsupported("cookies not supported")
        s.get_cookies = unsupported
        rc, out, err = self.run_cli(["backup", "demo"], s)
        self.assertEqual(rc, 4)

    def test_custom_backup_file_path(self):
        custom = self.tmp / "custom-session.json"
        self.write_site(backup_file=str(custom))
        s = FakeSite()
        s.login_as()
        self.run_cli(["backup", "demo"], s)
        self.assertTrue(custom.exists())
        self.assertEqual(mode(custom), 0o600)


class DrillTest(EngineTestCase):
    def _logged_in_site(self, **kw):
        s = FakeSite(**kw)
        s.login_as()
        return s

    def test_drill_passes_with_device_token_and_refreshes_backup(self):
        self.write_site()
        s = self._logged_in_site(require_2fa=True)
        rc, out, err = self.run_cli(["drill", "demo"], s)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("steps=A:ok,B:ok,C:ok", out)
        self.assertIn("state=DRILL_PASS", out)
        self.assertIn("SID", s.cookies)
        self.assertTrue((self.secrets_dir / "rift-session-demo.json").exists())
        self.assertNoSecrets(out, err, self.log_text())

    def test_drill_step_c_needs_code_means_fail_and_restore(self):
        self.write_site()
        s = self._logged_in_site(require_2fa=True)
        # device token not honoured by the site: relogin always lands on 2FA
        orig_click = s.click

        def click(sel):
            if sel == "#submit":
                s.clicks.append(sel)
                s.page = "2fa"
                return
            orig_click(sel)
        s.click = click
        rc, out, _ = self.run_cli(["drill", "demo"], s)
        self.assertEqual(rc, 3)
        self.assertIn("DRILL_FAIL", out)
        self.assertIn("C:fail", out)
        self.assertIn("SID", s.cookies)  # restored
        self.assertEqual(s.cookies["SID"]["value"], SESSION_VALUE)
        self.assertEqual(s.page, "dashboard")

    def test_drill_failure_in_b_restores_session(self):
        self.write_site()
        s = self._logged_in_site()
        calls = {"n": 0}
        orig = s.set_cookies

        def flaky(cookies):
            calls["n"] += 1
            if calls["n"] == 1:
                return  # step B restore silently does nothing
            orig(cookies)
        s.set_cookies = flaky
        rc, out, _ = self.run_cli(["drill", "demo"], s)
        self.assertEqual(rc, 3)
        self.assertIn("DRILL_FAIL", out)
        self.assertIn("SID", s.cookies)

    def test_drill_requires_drill_allowed(self):
        self.write_site(drill_allowed=False)
        s = self._logged_in_site()
        rc, out, err = self.run_cli(["drill", "demo"], s)
        self.assertEqual(rc, 4)
        self.assertIn("drill_allowed", out + err)
        self.assertEqual(s.names("delete_cookie"), [])

    def test_drill_requires_logged_in_start(self):
        self.write_site()
        s = FakeSite()
        rc, out, _ = self.run_cli(["drill", "demo"], s)
        self.assertEqual(rc, 3)
        self.assertEqual(s.names("delete_cookie"), [])

    def test_dry_run_prints_plan_and_touches_nothing(self):
        self.write_site()
        s = self._logged_in_site()
        rc, out, _ = self.run_cli(["drill", "demo", "--dry-run"], s)
        self.assertEqual(rc, 0)
        self.assertIn("DRY_RUN", out)
        self.assertEqual(s.calls, [])
        self.assertIn("delete", out.lower())


class ListTest(EngineTestCase):
    def test_list_shows_sites_and_cached_status(self):
        self.write_site("alpha")
        self.write_site("beta")
        s = FakeSite()
        s.login_as()
        self.run_cli(["keepalive", "alpha"], s)
        rc, out, err = self.run_cli(["list"], s)
        self.assertEqual(rc, 0)
        self.assertIn("alpha", out)
        self.assertIn("beta", out)
        self.assertIn("LOGGED_IN", out)
        self.assertNoSecrets(out, err)


if __name__ == "__main__":
    unittest.main()
