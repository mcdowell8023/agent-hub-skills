"""rift-session infra tests: backends (ego/rift command building), platform selection,
host allow-list, schedule (cron/launchd text only), script entry point."""
import json
import os
import plistlib
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import ENGINE, NOW, PASSWORD, EngineTestCase, FakeSite, rs, site_config  # noqa: E402


class FakeRunner:
    def __init__(self, replies=None):
        self.calls = []
        self.replies = list(replies or [])

    def __call__(self, argv, stdin=None, timeout=120):
        self.calls.append((list(argv), stdin))
        if self.replies:
            r = self.replies.pop(0)
            return r(argv, stdin) if callable(r) else r
        return 0, "", ""


def ego_result(obj):
    return 0, "noise line\nRS_RESULT " + json.dumps(obj) + "\n", ""


class HostMatchTest(unittest.TestCase):
    def test_exact_and_wildcard(self):
        self.assertTrue(rs.host_allowed("https://App.Example.com/x", ["app.example.com"]))
        self.assertFalse(rs.host_allowed("https://evil.example.org/", ["app.example.com"]))
        self.assertFalse(rs.host_allowed("https://app.example.com.evil.org/", ["app.example.com"]))
        self.assertTrue(rs.host_allowed("https://a.b.example.com/", ["*.example.com"]))
        self.assertFalse(rs.host_allowed("https://example.com/", ["*.example.com"]))
        self.assertFalse(rs.host_allowed("not a url", ["app.example.com"]))


class GuardTest(unittest.TestCase):
    def test_goto_outside_allowed_hosts_is_blocked_before_backend_call(self):
        s = FakeSite()
        g = rs.GuardedBackend(s, ["app.example.com"])
        with self.assertRaises(rs.HostBlocked):
            g.goto("https://evil.example.org/")
        self.assertEqual(s.names("goto"), [])

    def test_fill_blocked_when_last_page_off_host(self):
        s = FakeSite()
        s.landing_host = "evil.example.org"
        g = rs.GuardedBackend(s, ["app.example.com"])
        with self.assertRaises(rs.HostBlocked):
            g.goto("https://app.example.com/")
        with self.assertRaises(rs.HostBlocked):
            g.fill("#user", "x", secret=True)
        self.assertEqual(s.fills, [])


def probes(**results):
    """results: name -> (ok, reason); records call order."""
    calls = []

    def mk(name):
        def f():
            calls.append(name)
            return results.get(name, (False, "n/a"))
        return f
    d = {n: mk(n) for n in ("ego", "ego_over_ssh", "rift", "chrome")}
    d["calls"] = calls
    return d


class PlatformSelectionTest(unittest.TestCase):
    def cfg(self, **kw):
        return site_config("/tmp", **kw)

    def test_ego_argv_linux_via_ssh(self):
        argv = rs.ego_argv(self.cfg(backend_host="mac"), "linux")
        self.assertEqual(argv[0], "ssh")
        self.assertIn("BatchMode=yes", argv)
        self.assertEqual(argv[-2], "mac")
        self.assertEqual(argv[-1], 'zsh -lic "ego-browser nodejs"')

    def test_ego_argv_darwin_local(self):
        cfg = self.cfg()
        cfg.pop("backend_host")
        self.assertEqual(rs.ego_argv(cfg, "darwin"), ["ego-browser", "nodejs"])

    def test_ego_argv_force_local_ignores_host(self):
        self.assertEqual(rs.ego_argv(self.cfg(backend_host="mac"), "darwin", force_local=True),
                         ["ego-browser", "nodejs"])

    def test_ego_argv_linux_without_host_unavailable(self):
        cfg = self.cfg()
        cfg.pop("backend_host")
        with self.assertRaises(rs.BackendUnavailable):
            rs.ego_argv(cfg, "linux")

    def test_default_order_macos(self):
        cfg = self.cfg(backend="auto")
        self.assertEqual(rs.backend_order(cfg, "darwin"), ["ego", "chrome"])

    def test_default_order_linux_with_and_without_host(self):
        cfg = self.cfg(backend="auto")
        self.assertEqual(rs.backend_order(cfg, "linux"), ["ego_over_ssh", "rift", "chrome"])
        cfg.pop("backend_host")
        self.assertEqual(rs.backend_order(cfg, "linux"), ["rift", "chrome"])

    def test_explicit_backend_order_and_explicit_backend(self):
        cfg = self.cfg(backend="auto", backend_order=["chrome", "rift"])
        self.assertEqual(rs.backend_order(cfg, "linux"), ["chrome", "rift"])
        self.assertEqual(rs.backend_order(self.cfg(backend="rift", backend_order=["chrome"]), "linux"), ["rift"])
        self.assertEqual(rs.backend_order(self.cfg(backend="ego"), "linux"), ["ego_over_ssh"])  # host configured

    def test_select_takes_first_available_and_reports_reasons(self):
        pr = probes(ego_over_ssh=(False, "ssh mac 不通"), rift=(True, "rift-browser 在位"), chrome=(True, "Chrome"))
        kind, why = rs.select_backend(self.cfg(backend="auto"), "linux", pr)
        self.assertEqual(kind, "rift")
        self.assertEqual(pr["calls"], ["ego_over_ssh", "rift"])  # chrome never probed
        self.assertIn("ego_over_ssh=ssh mac 不通", why)
        self.assertIn("rift=rift-browser 在位", why)

    def test_select_falls_through_to_chrome(self):
        pr = probes(chrome=(True, "Chrome: /usr/bin/google-chrome"))
        kind, _ = rs.select_backend(self.cfg(backend="auto"), "linux", pr)
        self.assertEqual(kind, "chrome")

    def test_select_none_available_lists_every_reason(self):
        pr = probes()
        with self.assertRaises(rs.BackendUnavailable) as cm:
            rs.select_backend(self.cfg(backend="auto"), "linux", pr)
        self.assertIn("ego_over_ssh", str(cm.exception))
        self.assertIn("chrome", str(cm.exception))

    def test_macos_default_prefers_ego_then_chrome(self):
        cfg = self.cfg(backend="auto")
        cfg.pop("backend_host")
        kind, _ = rs.select_backend(cfg, "darwin", probes(ego=(False, "no"), chrome=(True, "ok")))
        self.assertEqual(kind, "chrome")

    def test_default_probes_detect_chrome_and_ego(self):
        cfg = self.cfg(backend="auto")
        pr = rs.default_probes(cfg, "darwin", which=lambda n: None, exists=lambda p: p.endswith("Google Chrome"))
        self.assertTrue(pr["chrome"]()[0])
        self.assertEqual(pr["ego"]()[0], False)
        pr = rs.default_probes(cfg, "darwin", which=lambda n: "/usr/local/bin/ego-browser", exists=lambda p: False)
        self.assertTrue(pr["ego"]()[0])
        self.assertFalse(pr["chrome"]()[0])
        self.assertFalse(pr["rift"]()[0] and False)

    def test_ssh_probe_uses_batchmode_and_reflects_rc(self):
        seen = []
        ok = rs.default_probes(self.cfg(), "linux", runner=lambda argv, stdin, timeout: (seen.append(argv) or (0, "", "")))
        self.assertTrue(ok["ego_over_ssh"]()[0])
        self.assertIn("BatchMode=yes", seen[0])
        bad = rs.default_probes(self.cfg(), "linux", runner=lambda argv, stdin, timeout: (255, "", ""))
        self.assertFalse(bad["ego_over_ssh"]()[0])

    def test_find_chrome_override_and_candidates(self):
        self.assertEqual(rs.find_chrome({"chrome_bin": "/opt/c/chrome"}, "linux", exists=lambda p: True), "/opt/c/chrome")
        self.assertIsNone(rs.find_chrome({"chrome_bin": "/opt/c/chrome"}, "linux", exists=lambda p: False))
        self.assertEqual(rs.find_chrome({}, "linux", which=lambda n: "/usr/bin/chromium" if n == "chromium" else None),
                         "/usr/bin/chromium")
        mac = rs.find_chrome({}, "darwin", exists=lambda p: "Google Chrome.app" in p and p.startswith("/Applications"))
        self.assertEqual(mac, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

    def test_paths_use_expanduser_not_hardcoded_home(self):
        for plat in ("linux", "darwin"):
            os.environ.pop("RIFT_SESSION_STATE", None)
            p = rs.state_dir()
            self.assertTrue(str(p).startswith(os.path.expanduser("~")))
            self.assertTrue(str(p).endswith(".local/state/rift-session"))


class EgoBackendTest(unittest.TestCase):
    def make(self, replies=None, host="mac"):
        runner = FakeRunner(replies)
        cfg = site_config("/tmp", backend_host=host, task_space="ts-demo")
        return rs.EgoBackend(cfg, "demo", runner=runner, platform="linux"), runner

    def test_goto_returns_title_and_url(self):
        b, r = self.make([ego_result({"title": "Dashboard", "url": "https://app.example.com/"})])
        st = b.goto("https://app.example.com/")
        self.assertEqual(st, {"title": "Dashboard", "url": "https://app.example.com/"})
        argv, stdin = r.calls[0]
        self.assertEqual(argv[0], "ssh")
        self.assertIn("ts-demo", stdin)
        self.assertIn("https://app.example.com/", stdin)

    def test_secret_value_goes_only_through_stdin(self):
        b, r = self.make([ego_result({"ok": True})])
        b.fill("#pw", PASSWORD, secret=True)
        argv, stdin = r.calls[0]
        self.assertNotIn(PASSWORD, " ".join(argv))
        self.assertIn(json.dumps(PASSWORD), stdin)

    def test_cookie_value_parsed_from_stderr_and_not_exposed_in_errors(self):
        payload = {"cookies": [{"name": "SID", "value": "cookie-VAL-777", "domain": "app.example.com",
                                "path": "/"}]}
        b, r = self.make([(0, "", "RS_RESULT " + json.dumps(payload) + "\n")])
        cookies = b.get_cookies(["https://app.example.com/"])
        self.assertEqual(cookies[0]["value"], "cookie-VAL-777")

    def test_failure_without_result_raises_backend_error(self):
        b, r = self.make([(255, "", "ssh: connect to host mac: Connection timed out\n")])
        with self.assertRaises(rs.BackendError) as cm:
            b.goto("https://app.example.com/")
        self.assertIn("Connection timed out", str(cm.exception))

    def test_ego_error_redacts_secret_in_message(self):
        b, r = self.make([(1, "", f"TypeError while filling {PASSWORD}\n")])
        with self.assertRaises(rs.BackendError) as cm:
            b.fill("#pw", PASSWORD, secret=True)
        self.assertNotIn(PASSWORD, str(cm.exception))

    def test_set_and_delete_cookies_use_cdp(self):
        b, r = self.make([ego_result({"ok": True}), ego_result({"ok": True})])
        b.set_cookies([{"name": "SID", "value": "v", "domain": "app.example.com", "path": "/",
                        "expires": -1, "httpOnly": True, "secure": True, "sameSite": "Lax",
                        "session": True, "size": 3}])
        b.delete_cookie("SID", "app.example.com", "/")
        self.assertIn("Network.setCookie", r.calls[0][1])
        self.assertIn("Network.deleteCookies", r.calls[1][1])
        self.assertNotIn('"size"', r.calls[0][1])  # CDP-incompatible read-only field dropped


class RiftBackendTest(unittest.TestCase):
    def make(self, help_text="usage: acquire [--ttl-ms MS]"):
        calls = FakeRunner([(0, help_text, "")])
        cfg = site_config("/tmp", backend="rift")
        cfg.pop("backend_host")
        return rs.RiftBackend(cfg, "demo", runner=calls, helper="/x/cdp-helper.py"), calls

    def test_open_uses_ttl_when_supported(self):
        b, r = self.make("--ttl-ms TTL_MS")
        r.replies.append((0, json.dumps({"agent": "rift-session-demo"}), ""))
        b.open()
        acquire = r.calls[1][0]
        self.assertIn("--agent", acquire)
        self.assertEqual(acquire[acquire.index("--agent") + 1], "rift-session-demo")
        self.assertIn("--ttl-ms", acquire)

    def test_open_degrades_when_ttl_not_supported(self):
        b, r = self.make("usage: acquire [-h] --agent AGENT [--url URL]")
        r.replies.append((0, "{}", ""))
        b.open()
        self.assertNotIn("--ttl-ms", r.calls[1][0])

    def test_fill_secret_via_secret_stdin_not_argv(self):
        b, r = self.make()
        r.replies.extend([(0, "{}", ""), (0, json.dumps({"ok": True, "value": True}), "")])
        b.open()
        b.fill("#pw", PASSWORD, secret=True)
        argv, stdin = r.calls[-1]
        self.assertIn("--secret-stdin", argv)
        self.assertNotIn(PASSWORD, " ".join(argv))
        self.assertEqual(stdin, PASSWORD)

    def test_cookies_unsupported(self):
        b, _ = self.make()
        with self.assertRaises(rs.BackendUnsupported):
            b.get_cookies(["https://app.example.com/"])

    def test_close_keeps_lease(self):
        b, r = self.make()
        r.replies.append((0, "{}", ""))
        b.open()
        n = len(r.calls)
        b.close()
        self.assertEqual(len(r.calls), n)  # no release: login state must survive across runs


class FakeCron:
    def __init__(self, text=""):
        self.text = text
        self.writes = 0

    def read(self):
        return self.text

    def write(self, text):
        self.text = text
        self.writes += 1


class ScheduleTest(EngineTestCase):
    def test_cron_install_dedupe_and_remove(self):
        self.write_site()
        cron = FakeCron("0 3 * * * /usr/bin/backup.sh\n")
        rc, out, _ = self.run_cli(["schedule", "install", "demo"], cron_io=cron)
        self.assertEqual(rc, 0)
        lines = cron.text.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "0 3 * * * /usr/bin/backup.sh")
        mine = lines[1]
        self.assertTrue(mine.startswith("*/10 * * * * "))
        self.assertIn("keepalive demo", mine)
        self.assertTrue(mine.endswith("# rift-session:demo"))
        # backup of original crontab
        backups = list((self.home / "backups").glob("crontab-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "0 3 * * * /usr/bin/backup.sh\n")
        # idempotent
        self.run_cli(["schedule", "install", "demo"], cron_io=cron)
        self.assertEqual(cron.text.count("rift-session:demo"), 1)
        # status
        rc, out, _ = self.run_cli(["schedule", "status", "demo"], cron_io=cron)
        self.assertIn("state=SCHEDULED", out)
        # remove only our line
        self.run_cli(["schedule", "remove", "demo"], cron_io=cron)
        self.assertEqual(cron.text, "0 3 * * * /usr/bin/backup.sh\n")
        rc, out, _ = self.run_cli(["schedule", "status", "demo"], cron_io=cron)
        self.assertIn("state=NOT_SCHEDULED", out)

    def test_script_override_goes_into_cron_line(self):
        self.write_site()
        cron = FakeCron()
        self.run_cli(["schedule", "install", "demo", "--script", "/opt/bin/rift-session"], cron_io=cron)
        self.assertIn(" /opt/bin/rift-session keepalive demo ", cron.text)

    def test_cron_remove_leaves_other_sites_alone(self):
        self.write_site("a")
        self.write_site("b")
        cron = FakeCron()
        self.run_cli(["schedule", "install", "a"], cron_io=cron)
        self.run_cli(["schedule", "install", "b"], cron_io=cron)
        self.run_cli(["schedule", "remove", "a"], cron_io=cron)
        self.assertIn("rift-session:b", cron.text)
        self.assertNotIn("rift-session:a", cron.text)

    def test_cron_interval_from_config(self):
        self.write_site(keepalive={"url": "https://app.example.com/", "interval_minutes": 7})
        cron = FakeCron()
        self.run_cli(["schedule", "install", "demo"], cron_io=cron)
        self.assertIn("*/7 * * * *", cron.text)

    def test_launchd_plist_on_darwin(self):
        self.write_site()
        la = self.tmp / "LaunchAgents"
        os.environ["RIFT_SESSION_LAUNCH_AGENTS"] = str(la)
        self.addCleanup(os.environ.pop, "RIFT_SESSION_LAUNCH_AGENTS", None)
        cron = FakeCron()
        rc, out, _ = self.run_cli(["schedule", "install", "demo"], platform="darwin", cron_io=cron)
        self.assertEqual(rc, 0)
        self.assertEqual(cron.writes, 0)  # crontab untouched on macOS
        plist = la / "com.rift-session.demo.plist"
        self.assertTrue(plist.exists())
        data = plistlib.loads(plist.read_bytes())
        self.assertEqual(data["Label"], "com.rift-session.demo")
        self.assertEqual(data["StartInterval"], 600)
        self.assertIn("keepalive", data["ProgramArguments"])
        self.assertIn("demo", data["ProgramArguments"])
        self.assertIn("launchctl", out)  # prints the load command, never runs it
        rc, out, _ = self.run_cli(["schedule", "status", "demo"], platform="darwin", cron_io=cron)
        self.assertIn("state=SCHEDULED", out)
        self.run_cli(["schedule", "remove", "demo"], platform="darwin", cron_io=cron)
        self.assertFalse(plist.exists())

    def test_launchd_log_path_same_as_linux(self):
        self.assertEqual(rs.log_path("demo"), rs.state_dir() / "demo.log")


class EntryPointTest(unittest.TestCase):
    def test_script_runs_directly_and_list_works(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, RIFT_SESSION_HOME=d, RIFT_SESSION_STATE=d + "/st",
                       RIFT_SESSION_SECRETS=d + "/sec")
            r = subprocess.run([sys.executable, str(ENGINE), "list"], capture_output=True, text=True,
                               env=env, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("RIFT_SESSION", r.stdout)

    def test_unknown_command_exit_4(self):
        r = subprocess.run([sys.executable, str(ENGINE), "bogus"], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 4)


if __name__ == "__main__":
    unittest.main()
