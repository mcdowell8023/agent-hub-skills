#!/usr/bin/env python3
"""pc.py — PingCode Open API 免登录访问（Python 封装）。

用个人访问令牌（PAT）直调 Open API，不登录、不换 token。

用法:
  pc.py health                       # 探活
  pc.py item <RD-IT-4033>            # 查单个工作项（按 identifier）
  pc.py mine [--keyword KW] [--user NAME]   # 查我的未关闭工作项
  pc.py list [--project-id ID] [--all]      # 列工作项；--all 自动翻页
  pc.py get <path> [k=v ...]         # 任意 GET 端点

令牌解析顺序:
  1) 环境变量 PINGCODE_API_TOKEN
  2) ~/wb/secrets/pingcode-token
  3) ~/wb/projects/pingcode-tracker/.env 的 PINGCODE_API_TOKEN
  4) macOS 钥匙串 pingcode-token
  5) 兜底 client_credentials 换 token
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

API_BASE = os.environ.get("PINGCODE_API_BASE", "https://open.pingcode.com")
SECRET_FILE = os.environ.get(
    "PINGCODE_TOKEN_FILE", os.path.expanduser("~/wb/secrets/pingcode-token")
)
TRACKER_ENV = os.environ.get(
    "PINGCODE_TRACKER_ENV", os.path.expanduser("~/wb/projects/pingcode-tracker/.env")
)
PROJECT_ID = os.environ.get("PINGCODE_PROJECT_ID", "69cfa488ff85507e68564f20")
DEFAULT_PROJECT = "69cfa488ff85507e68564f20"  # IT研发部 / RD-IT


def _from_env_file(key: str) -> str | None:
    if not os.path.isfile(TRACKER_ENV):
        return None
    try:
        text = open(TRACKER_ENV, encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(rf"^{re.escape(key)}\s*=\s*(.+)$", text, re.M)
    if not m:
        return None
    val = m.group(1).strip().strip('"').strip("'")
    return val or None


def _from_keychain() -> str | None:
    if not os.path.exists("/usr/bin/security"):
        return None
    try:
        out = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", "pingcode-token", "-w"],
            capture_output=True, text=True, timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    val = (out.stdout or "").strip()
    return val or None


def resolve_token() -> tuple[str | None, str]:
    """返回 (token, 来源)。"""
    env = os.environ.get("PINGCODE_API_TOKEN", "").strip()
    if env:
        return env, "env:PINGCODE_API_TOKEN"
    try:
        with open(SECRET_FILE, encoding="utf-8") as fh:
            val = fh.readline().strip()
        if val:
            return val, f"file:{SECRET_FILE}"
    except OSError:
        pass
    val = _from_env_file("PINGCODE_API_TOKEN")
    if val:
        return val, "tracker_env:PINGCODE_API_TOKEN"
    val = _from_keychain()
    if val:
        return val, "keychain:pingcode-token"
    return None, "none"


def oauth_token() -> str | None:
    """兜底：client_credentials 换 token。"""
    cid = _from_env_file("PINGCODE_CLIENT_ID") or os.environ.get("PINGCODE_CLIENT_ID")
    sec = _from_env_file("PINGCODE_CLIENT_SECRET") or os.environ.get("PINGCODE_CLIENT_SECRET")
    if not (cid and sec):
        return None
    qs = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "client_id": cid, "client_secret": sec}
    )
    try:
        with urllib.request.urlopen(f"{API_BASE}/v1/auth/token?{qs}", timeout=20) as r:
            return json.load(r).get("access_token")
    except Exception:
        return None


def api_get(path: str, params: dict | None = None, token: str | None = None) -> tuple[int, object]:
    url = f"{API_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items() if v not in (None, "", [], {})}
    if isinstance(o, list):
        return [clean(x) for x in o]
    return o


def resolve_user_id(name: str | None) -> str | None:
    """从 tracker 的 user_mapping.json 解析姓名 → pingcode 用户 id。

    ⚠️ 必须遍历**所有** candidate：git 的 user.name 常是登录名（mengxianchao）
       而映射表里是姓名（孟显超），单个不匹配不代表解析失败。
    """
    path = os.path.expanduser("~/wb/projects/pingcode-tracker/user_mapping.json")
    try:
        mapping = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    candidates = [
        name,
        os.environ.get("PINGCODE_USER"),
        _git("user.name"),
        _git("user.email"),
        _git("user.name", "~/.gitconfig-wb"),
        _git("user.email", "~/.gitconfig-wb"),
    ]
    for c in candidates:
        if not c:
            continue
        for key, v in mapping.items():
            hit = False
            if c == key:
                hit = True
            elif isinstance(v, dict):
                for field in ("email", "name", "display_name"):
                    fv = v.get(field)
                    if fv and str(fv).lower() == c.lower():
                        hit = True
                        break
            if hit and isinstance(v, dict) and v.get("pingcode_id"):
                return v["pingcode_id"]
    return None


def _git(key: str, file: str | None = None) -> str | None:
    cmd = ["git", "config"]
    if file:
        cmd += ["--file", os.path.expanduser(file)]
    cmd.append(key)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def print_json(obj) -> None:
    print(json.dumps(clean(obj), ensure_ascii=False, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description="PingCode Open API 免登录访问")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health")

    p_item = sub.add_parser("item")
    p_item.add_argument("identifier")

    p_mine = sub.add_parser("mine")
    p_mine.add_argument("--keyword")
    p_mine.add_argument("--user")
    p_mine.add_argument("--all", action="store_true", dest="fetch_all",
                        help="翻页拉全量（默认只取第一页）")
    p_mine.add_argument("--state", help="只保留该状态，如 '待计划'、'开发中'")
    p_mine.add_argument("--open", action="store_true",
                        help="只要未结束（排除 已完成/已挂起/已关闭/已驳回）")

    p_list = sub.add_parser("list")
    p_list.add_argument("--project-id", default=DEFAULT_PROJECT)
    p_list.add_argument("--identifier")
    p_list.add_argument("--keywords")
    p_list.add_argument("--page-size", type=int, default=100)
    p_list.add_argument("--all", action="store_true", dest="fetch_all")

    p_get = sub.add_parser("get")
    p_get.add_argument("path")
    p_get.add_argument("params", nargs="*")

    args = ap.parse_args()

    token, source = resolve_token()
    if not token:
        token = oauth_token()
        source = "oauth_fallback" if token else "none"
    if not token:
        print(json.dumps({
            "ok": False,
            "error": "找不到 PingCode 令牌",
            "tried": [
                "env:PINGCODE_API_TOKEN",
                f"file:{SECRET_FILE}",
                "tracker_env:PINGCODE_API_TOKEN",
                "keychain:pingcode-token",
                "oauth client_credentials",
            ],
        }, ensure_ascii=False, indent=2))
        return 1

    if args.cmd == "health":
        code, body = api_get("/v1/project/work_items",
                              {"project_id": DEFAULT_PROJECT, "page_size": 1}, token)
        total = body.get("total") if isinstance(body, dict) else None
        print(json.dumps({"ok": code == 200, "http": code, "project_total": total,
                          "token_source": source}, ensure_ascii=False))
        return 0 if code == 200 else 1

    if args.cmd == "item":
        code, body = api_get("/v1/project/work_items",
                              {"project_id": DEFAULT_PROJECT, "identifier": args.identifier}, token)
        if code != 200:
            print(json.dumps({"error": f"HTTP {code}", "body": body}, ensure_ascii=False, indent=2))
            return 1
        values = body.get("values") or []
        hits = [v for v in values if v.get("identifier") == args.identifier]
        if not hits:
            print(json.dumps({"found": False, "identifier": args.identifier}, ensure_ascii=False))
            return 1
        print_json(hits[0])
        return 0

    if args.cmd == "mine":
        uid = resolve_user_id(args.user)
        if not uid:
            print(json.dumps({"error": "CANNOT_RESOLVE_USER",
                              "hint": "用 --user <PingCode 姓名> 指定"}, ensure_ascii=False))
            return 4
        rows, page = [], 0
        while True:
            params = {"project_id": DEFAULT_PROJECT, "assignee_ids": uid,
                      "page_size": 100, "page_index": page}
            if args.keyword:
                params["keywords"] = args.keyword
            code, body = api_get("/v1/project/work_items", params, token)
            if code != 200:
                print(json.dumps({"error": f"HTTP {code}", "body": body}, ensure_ascii=False, indent=2))
                return 1
            vals = body.get("values") or []
            rows += vals
            if len(vals) < 100 or not args.fetch_all:
                break
            page += 1
        out = []
        for r in rows:
            state = r.get("state")
            state = state.get("name") if isinstance(state, dict) else state
            # 默认排除已关闭/已驳回（与 pingcode-item.py 的 STOP 口径一致）；
            # 已完成/已挂起仍列出但标注 —— 它们需要人确认，不该被当成"可提交"。
            if not args.fetch_all and state in ("已关闭", "已驳回"):
                continue
            if args.open and state in ("已完成", "已挂起", "已关闭", "已驳回"):
                continue
            if args.state and state != args.state:
                continue
            out.append({
                "identifier": r.get("identifier"),
                "state": state,
                "title": r.get("title"),
                "assignee": (r.get("assignee") or {}).get("name")
                if isinstance(r.get("assignee"), dict) else r.get("assignee"),
            })
        print_json(out)
        return 0

    if args.cmd == "list":
        page, rows = 0, []
        while True:
            params = {"project_id": args.project_id, "page_size": args.page_size,
                      "page_index": page}
            if args.identifier:
                params["identifier"] = args.identifier
            if args.keywords:
                params["keywords"] = args.keywords
            code, body = api_get("/v1/project/work_items", params, token)
            if code != 200:
                print(json.dumps({"error": f"HTTP {code}", "body": body}, ensure_ascii=False, indent=2))
                return 1
            vals = body.get("values") or []
            rows += vals
            if not args.fetch_all or len(vals) < args.page_size:
                break
            page += 1
        print_json({"count": len(rows), "values": [
            {"identifier": v.get("identifier"), "title": v.get("title"),
             "state": (v.get("state") or {}).get("name") if isinstance(v.get("state"), dict) else v.get("state")}
            for v in rows]})
        return 0

    if args.cmd == "get":
        params = {}
        for kv in args.params:
            k, _, v = kv.partition("=")
            params[k] = v
        code, body = api_get(args.path, params or None, token)
        if code != 200:
            print(json.dumps({"error": f"HTTP {code}", "body": body}, ensure_ascii=False, indent=2))
            return 1
        print_json(body)
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
