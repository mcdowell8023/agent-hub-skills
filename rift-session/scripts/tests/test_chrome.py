"""Chrome-over-CDP backend + minimal websocket client, against a local fake CDP server (offline)."""
import ast
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_cdp import FakeCDP  # noqa: E402
from helpers import ENGINE, PASSWORD, EngineTestCase, rs, site_config  # noqa: E402


class WSClientTest(unittest.TestCase):
    def setUp(self):
        self.srv = FakeCDP()
        self.addCleanup(self.srv.stop)

    def client(self):
        c = rs.WSClient("ws://127.0.0.1:%d/devtools/page/0" % self.srv.port, timeout=5)
        c.connect()
        self.addCleanup(c.close)
        return c

    def test_roundtrip_ignores_events_and_ping(self):
        c = self.client()
        self.assertEqual(c.call("Test.echo", {"text": "hello"}), {"echo": "hello"})

    def test_large_payloads_use_extended_lengths_and_fragments(self):
        c = self.client()
        for n in (130, 70000):  # 126-byte and 127-byte length encodings, both directions
            text = "x" * n
            self.assertEqual(c.call("Test.echo", {"text": text})["echo"], text)

    def test_cdp_error_raises_backend_error(self):
        c = self.client()
        with self.assertRaises(rs.BackendError) as cm:
            c.call("Test.fail")
        self.assertIn("boom", str(cm.exception))

    def test_connect_refused_is_backend_error(self):
        port = self.srv.port
        self.srv.stop()
        with self.assertRaises(rs.BackendError):
            rs.WSClient("ws://127.0.0.1:%d/x" % port, timeout=2).connect()


class ChromeBackendTest(EngineTestCase):
    def setUp(self):
        super().setUp()
        self.srv = FakeCDP()
        self.addCleanup(self.srv.stop)
        self.cfg = site_config(self.tmp, backend="chrome", chrome_port=self.srv.port)
        self.cfg["name"] = "demo"

    def backend(self, cfg=None, **kw):
        b = rs.ChromeBackend(cfg or self.cfg, "demo", platform="linux", sleep=lambda s: None, **kw)
        b.open()
        self.addCleanup(b.close)
        return b

    def test_reuses_running_chrome_without_launching(self):
        launched = []
        self.backend(launcher=lambda argv: launched.append(argv))
        self.assertEqual(launched, [])
        self.assertEqual(self.srv.ws_connections, 1)

    def test_creates_tab_when_none(self):
        self.srv.pages = []
        self.backend()
        self.assertIn(("PUT", "/json/new?about:blank"), self.srv.http_log)

    def test_goto_waits_for_load_and_returns_state(self):
        def handler(expr):
            if expr == "document.readyState":
                return "complete"
            return json.dumps({"title": "Dashboard", "url": "https://app.example.com/"})
        self.srv.eval_handler = handler
        st = self.backend().goto("https://app.example.com/")
        self.assertEqual(st, {"title": "Dashboard", "url": "https://app.example.com/"})
        self.assertEqual([m["method"] for m in self.srv.messages][0], "Page.navigate")

    def test_navigation_error_raises(self):
        self.srv.nav_error = "net::ERR_NAME_NOT_RESOLVED"
        with self.assertRaises(rs.BackendError):
            self.backend().goto("https://app.example.com/")

    def test_fill_sends_value_over_cdp_and_missing_field_raises(self):
        self.srv.eval_handler = lambda expr: True
        b = self.backend()
        b.fill("#pw", PASSWORD, secret=True)
        sent = [m for m in self.srv.messages if m["method"] == "Runtime.evaluate"][-1]
        self.assertIn(json.dumps(PASSWORD), sent["params"]["expression"])
        self.srv.eval_handler = lambda expr: False
        with self.assertRaises(rs.BackendError):
            b.fill("#nope", "x")

    def test_exists_check_page_text_use_page_not_filesystem(self):
        self.srv.eval_handler = lambda expr: True if "__find" in expr else "Welcome"
        b = self.backend()
        self.assertTrue(b.exists("#u"))
        self.assertEqual(b.page_text(), "Welcome")

    def test_cookie_roundtrip_set_get_delete(self):
        b = self.backend()
        b.set_cookies([{"name": "SID", "value": "v1v1v1", "domain": "app.example.com", "path": "/",
                        "expires": -1, "session": True, "size": 9, "httpOnly": True}])
        sent = [m for m in self.srv.messages if m["method"] == "Network.setCookie"][0]["params"]
        self.assertNotIn("size", sent)
        self.assertNotIn("expires", sent)
        self.assertEqual(b.get_cookies(["https://app.example.com/"])[0]["value"], "v1v1v1")
        b.delete_cookie("SID", "app.example.com", "/")
        self.assertEqual(b.get_cookies(["https://app.example.com/"]), [])

    def test_launch_when_not_running(self):
        import socket
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
        s.close()
        launched, servers = [], []

        def launcher(argv):
            launched.append(argv)
            servers.append(FakeCDP(port=free))  # "Chrome" comes up on the requested port
            self.addCleanup(servers[0].stop)
            return type("P", (), {"pid": 4242})()
        cfg = dict(self.cfg)
        cfg.pop("chrome_port")
        b = rs.ChromeBackend(cfg, "demo", platform="linux", sleep=lambda s: None, launcher=launcher,
                             which=lambda n: "/usr/bin/google-chrome" if n == "google-chrome" else None,
                             env={"DISPLAY": ":0"}, pick_port=lambda: free)
        b.open()
        self.addCleanup(b.close)
        argv = launched[0]
        self.assertEqual(argv[0], "/usr/bin/google-chrome")
        self.assertIn("--remote-debugging-port=%d" % free, argv)
        self.assertIn("--remote-debugging-address=127.0.0.1", argv)
        prof = [a for a in argv if a.startswith("--user-data-dir=")][0].split("=", 1)[1]
        self.assertEqual(prof, str(self.state / "chrome-profile" / "demo"))
        self.assertEqual(os.stat(prof).st_mode & 0o777, 0o700)
        self.assertNotIn("--headless=new", argv)  # display present -> headful
        st = json.loads((self.state / "demo.chrome.json").read_text())
        self.assertEqual((st["port"], st["pid"]), (free, 4242))

    def test_headless_decision(self):
        self.assertTrue(rs.chrome_headless({}, "linux", {}))
        self.assertFalse(rs.chrome_headless({}, "linux", {"DISPLAY": ":0"}))
        self.assertFalse(rs.chrome_headless({}, "darwin", {}))
        self.assertTrue(rs.chrome_headless({"chrome_headless": True}, "darwin", {}))
        self.assertFalse(rs.chrome_headless({"chrome_headless": False}, "linux", {}))

    def test_launch_headless_without_display_and_no_chrome_is_unavailable(self):
        cfg = dict(self.cfg)
        cfg.pop("chrome_port")
        b = rs.ChromeBackend(cfg, "demo", platform="linux", sleep=lambda s: None, which=lambda n: None,
                             pick_port=lambda: 1)
        with self.assertRaises(rs.BackendUnavailable):
            b.open()

    def test_never_ready_raises_clear_error(self):
        cfg = dict(self.cfg)
        cfg["chrome_port"] = 1  # nothing listens
        b = rs.ChromeBackend(cfg, "demo", platform="linux", sleep=lambda s: None, launcher=lambda a: None,
                             which=lambda n: "/usr/bin/google-chrome", env={}, ready_polls=2)
        with self.assertRaises(rs.BackendError) as cm:
            b.open()
        self.assertIn("没就绪", str(cm.exception))

    def test_full_login_flow_through_cli_with_chrome_backend(self):
        # end-to-end: engine + ChromeBackend + fake CDP acting as a logged-in site
        self.write_site(backend="chrome", chrome_port=self.srv.port)
        self.srv.eval_handler = lambda expr: ("complete" if expr == "document.readyState"
                                               else json.dumps({"title": "Dashboard", "url": "https://app.example.com/"}))
        d = rs.Deps(backend_factory=lambda cfg: rs.ChromeBackend(cfg, "demo", platform="linux", sleep=lambda s: None),
                    now=lambda: 1.8e9, sleep=lambda s: None, platform="linux")
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = rs.main(["keepalive", "demo"], deps=d)
        self.assertEqual(rc, 0, out.getvalue())
        self.assertIn("state=LOGGED_IN", out.getvalue())


class PythonCompatTest(unittest.TestCase):
    """Engine must parse and run on Python 3.8 (macOS system python can be 3.9)."""

    def setUp(self):
        self.src = ENGINE.read_text(encoding="utf-8")

    def test_parses_as_python_38(self):
        ast.parse(self.src, feature_version=(3, 8))

    def test_shebang_is_env_python3(self):
        self.assertEqual(self.src.splitlines()[0], "#!/usr/bin/env python3")

    def test_no_post_38_constructs(self):
        tree = ast.parse(self.src)
        bad = []
        builtin_generics = {"list", "dict", "tuple", "set", "frozenset", "type"}
        annotations = []
        for n in ast.walk(tree):
            if isinstance(n, ast.arg) and n.annotation:
                annotations.append(n.annotation)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.returns:
                annotations.append(n.returns)
            elif isinstance(n, ast.AnnAssign):
                annotations.append(n.annotation)
            if type(n).__name__ in ("Match", "TryStar"):
                bad.append("%s at line %d" % (type(n).__name__, n.lineno))
            if isinstance(n, ast.Attribute) and n.attr in ("removeprefix", "removesuffix", "is_relative_to",
                                                            "readlink", "with_stem"):
                bad.append("3.9+ attribute .%s at line %d" % (n.attr, n.lineno))
            if isinstance(n, ast.ImportFrom) and n.module in ("zoneinfo", "graphlib"):
                bad.append("3.9+ import %s" % n.module)
        for a in annotations:
            for n in ast.walk(a):
                if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr):
                    bad.append("X | Y annotation at line %d" % n.lineno)
                if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id in builtin_generics:
                    bad.append("builtin generic %s[...] at line %d" % (n.value.id, n.lineno))
        # dict | dict and parenthesised multi-item `with (...)` are 3.9 / 3.10 syntax: scan dict-merge ops on Dict nodes
        for n in ast.walk(tree):
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr) and (
                    isinstance(n.left, ast.Dict) or isinstance(n.right, ast.Dict)):
                bad.append("dict | dict at line %d" % n.lineno)
        self.assertEqual(bad, [])

    def test_no_gnu_only_shell_commands(self):
        for needle in ("readlink -f", "sed -r", '"timeout"', "'timeout'", "timeout "):
            if needle == "timeout ":
                continue  # prose; subprocess timeout kwarg is fine
            self.assertNotIn(needle, self.src)

    def test_py_compile(self):
        import py_compile
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            py_compile.compile(str(ENGINE), cfile=os.path.join(d, "x.pyc"), doraise=True)

    def test_tests_helper_dirs_are_self_contained(self):
        for p in ENGINE.parent.rglob("*"):
            if p.suffix in (".py", "") and p.is_file() and p.name != "rift-session" and "tests" not in p.parts:
                self.fail("unexpected file in scripts/: %s" % p)
        # no relative references to sibling skills except the optional rift-mfa fallback lookup
        self.assertNotIn("agent-hub-private", self.src.replace("agent-hub-private/rift-browser/bin/cdp-helper.py", ""))


if __name__ == "__main__":
    unittest.main()
