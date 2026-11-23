"""Shared test helpers for rift-session (offline: fake backend, temp dirs, no network)."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
ENGINE = SCRIPTS / "rift-session"
NOW = 1_800_000_000.0  # NOW % 30 == 0

PASSWORD = "PW-SECRET-1"
USER = "alice"
CODE = "123456"
SESSION_VALUE = "sess-VALUE-abcdef123456"
DEVICE_VALUE = "dev-VALUE-abcdef654321"


def load_engine():
    loader = importlib.machinery.SourceFileLoader("rift_session_engine", str(ENGINE))
    spec = importlib.util.spec_from_loader("rift_session_engine", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


rs = load_engine()


class FakeSite:
    """In-memory Backend simulating a login site (two-step or single page, optional 2FA)."""

    supports_cookies = True

    def __init__(self, *, two_step=True, require_2fa=False, host="app.example.com",
                 password=PASSWORD, code=CODE):
        self.two_step, self.require_2fa = two_step, require_2fa
        self.host, self.password, self.code = host, password, code
        self.cookies = {}
        self.page = "login"
        self.weird = False
        self.landing_host = None  # simulate redirect to another host
        self.calls, self.fills, self.clicks = [], [], []
        self.remember_checked = False
        self.opened = self.closed = False
        self._user = self._pw = self._code = None
        self.fail_restore = False

    # ---- helpers for tests ----
    def login_as(self, *, device=True, now=NOW):
        self.cookies["SID"] = dict(name="SID", value=SESSION_VALUE, domain=self.host, path="/",
                                   expires=-1, httpOnly=True, secure=True, session=True)
        if device:
            self.cookies["DEV_TOKEN"] = dict(name="DEV_TOKEN", value=DEVICE_VALUE, domain=self.host,
                                             path="/", expires=now + 20 * 86400, httpOnly=True,
                                             secure=True, session=False)
        self.page = "dashboard"

    def _title(self):
        if self.weird:
            return "Something odd"
        return {"login": "Login", "password": "Login", "dashboard": "Dashboard",
                "2fa": "Two-Factor Auth"}[self.page]

    def _state(self):
        return {"title": self._title(), "url": f"https://{self.landing_host or self.host}/x"}

    # ---- Backend API ----
    def open(self):
        self.opened = True
        self.calls.append(("open",))

    def close(self):
        self.closed = True
        self.calls.append(("close",))

    def goto(self, url):
        self.calls.append(("goto", url))
        if "SID" in self.cookies:
            self.page = "dashboard"
        elif self.page in ("password", "dashboard"):
            self.page = "login"
        return self._state()

    def page_state(self):
        self.calls.append(("page_state",))
        return self._state()

    def fill(self, selector, value, secret=False):
        self.calls.append(("fill", selector))
        self.fills.append((selector, value, secret))
        if selector == "#user":
            self._user = value
        elif selector == "#pw":
            self._pw = value
        elif selector == "#code":
            self._code = value

    def check(self, selector):
        self.calls.append(("check", selector))
        if selector == "#remember":
            self.remember_checked = True

    def click(self, selector):
        self.calls.append(("click", selector))
        self.clicks.append(selector)
        if selector == "#next" and self.page == "login":
            self.page = "password"
        elif selector == "#submit":
            if self._user == USER and self._pw == self.password:
                if self.require_2fa and "DEV_TOKEN" not in self.cookies:
                    self.page = "2fa"
                else:
                    self._grant()
        elif selector == "#code-submit" and self.page == "2fa":
            if self._code == self.code:
                self._grant()

    def _grant(self):
        self.cookies["SID"] = dict(name="SID", value=SESSION_VALUE, domain=self.host, path="/",
                                   expires=-1, httpOnly=True, secure=True, session=True)
        if self.remember_checked:
            self.cookies["DEV_TOKEN"] = dict(name="DEV_TOKEN", value=DEVICE_VALUE, domain=self.host,
                                             path="/", expires=NOW + 30 * 86400, httpOnly=True,
                                             secure=True, session=False)
        self.page = "dashboard"

    def exists(self, selector):
        self.calls.append(("exists", selector))
        return selector == "#dash-marker" and self.page == "dashboard"

    def page_text(self):
        self.calls.append(("page_text",))
        return "Welcome back" if self.page == "dashboard" else "Please sign in"

    def wait(self, ms):
        self.calls.append(("wait", ms))

    def get_cookies(self, urls):
        self.calls.append(("get_cookies",))
        return [dict(c) for c in self.cookies.values()]

    def set_cookies(self, cookies):
        self.calls.append(("set_cookies", [c["name"] for c in cookies]))
        if self.fail_restore:
            return
        for c in cookies:
            self.cookies[c["name"]] = dict(c)

    def delete_cookie(self, name, domain, path):
        self.calls.append(("delete_cookie", name))
        self.cookies.pop(name, None)

    def names(self, kind):
        return [c[0] for c in self.calls if c[0] == kind]


def site_config(tmp, **over):
    secrets = Path(tmp) / "creds.json"
    secrets.write_text(json.dumps({"user": USER, "pass": PASSWORD}))
    os.chmod(secrets, 0o600)
    cfg = {
        "base_url": "https://app.example.com/",
        "login_url": "https://app.example.com/login",
        "logged_in_check": {"title_regex": "Dashboard"},
        "login_page_check": {"title_regex": "Login"},
        "login_form": {"username": "#user", "next": "#next", "password": "#pw", "submit": "#submit"},
        "secret_refs": {"file": str(secrets), "format": "json", "user_key": "user", "password_key": "pass"},
        "session_cookie_names": ["SID"],
        "device_token_cookie_names": ["DEV_TOKEN"],
        "two_factor": {"type": "manual_code", "page_title_regex": "Two-Factor",
                       "code_input": "#code", "submit": "#code-submit", "remember": "#remember"},
        "keepalive": {"url": "https://app.example.com/", "interval_minutes": 10},
        "relogin_policy": {"max_per_hour": 1},
        "allowed_hosts": ["app.example.com"],
        "backend": "ego",
        "backend_host": "mac",
        "drill_allowed": True,
    }
    cfg.update(over)
    return cfg


class EngineTestCase(unittest.TestCase):
    """Sets RIFT_SESSION_* dirs under a temp dir; helpers to write site config and run the CLI."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "cfg"
        self.state = self.tmp / "state"
        self.secrets_dir = self.tmp / "agent-secrets"
        (self.home / "sites").mkdir(parents=True)
        os.chmod(self.home, 0o700)
        os.chmod(self.home / "sites", 0o700)
        p = mock.patch.dict(os.environ, {
            "RIFT_SESSION_HOME": str(self.home),
            "RIFT_SESSION_STATE": str(self.state),
            "RIFT_SESSION_SECRETS": str(self.secrets_dir),
        })
        p.start()
        self.addCleanup(p.stop)
        self.sleeps = []

    def write_site(self, name="demo", **over):
        cfg = site_config(self.tmp, **over)
        path = self.home / "sites" / f"{name}.json"
        path.write_text(json.dumps(cfg))
        os.chmod(path, 0o600)
        return cfg

    def run_cli(self, argv, site=None, now=NOW, platform="linux", **deps):
        d = rs.Deps(backend_factory=(lambda cfg: site), now=lambda: now,
                    sleep=self.sleeps.append, platform=platform, **deps)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = rs.main(list(argv), deps=d)
        return rc, out.getvalue(), err.getvalue()

    def log_text(self, name="demo"):
        p = self.state / f"{name}.log"
        return p.read_text() if p.exists() else ""

    def assertNoSecrets(self, *texts):
        for t in texts:
            for s in (PASSWORD, CODE, SESSION_VALUE, DEVICE_VALUE):
                self.assertNotIn(s, t)


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)
