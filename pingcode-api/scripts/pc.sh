#!/usr/bin/env bash
# pc.sh — PingCode Open API 免登录访问（curl 封装）
#
# 用法:
#   pc.sh health                          # 探活（检查令牌是否可用）
#   pc.sh get <path> [k=v ...]            # 任意 GET 端点
#   pc.sh work_items [--identifier ID] [--keywords KW] [--page-size N] [--page-index N]
#
# 例:
#   pc.sh work_items --identifier RD-IT-4033
#   pc.sh get /v1/project/work_items project_id=69cfa488ff85507e68564f20 page_size=5
#
# 令牌解析顺序（不打印明文）：
#   1) 环境变量 PINGCODE_API_TOKEN
#   2) ~/wb/secrets/pingcode-token
#   3) ~/wb/projects/pingcode-tracker/.env 的 PINGCODE_API_TOKEN
#   4) macOS 钥匙串 pingcode-token
#   5) 兜底：client_credentials 换 token（需 CLIENT_ID/SECRET）
set -uo pipefail

API_BASE="${PINGCODE_API_BASE:-https://open.pingcode.com}"
SECRET_FILE="${PINGCODE_TOKEN_FILE:-$HOME/wb/secrets/pingcode-token}"
TRACKER_ENV="${PINGCODE_TRACKER_ENV:-$HOME/wb/projects/pingcode-tracker/.env}"
RAW=0

die() { echo "pc.sh: $*" >&2; exit 1; }

read_secret() {
  # 从 tracker 的 .env 取某个 key 的值
  [ -f "$TRACKER_ENV" ] || return 1
  python3 - "$TRACKER_ENV" "$1" <<'PY'
import re, sys
path, key = sys.argv[1], sys.argv[2]
try:
    t = open(path, encoding="utf-8").read()
except Exception:
    raise SystemExit(1)
m = re.search(rf"^{re.escape(key)}\s*=\s*(.+)$", t, re.M)
if not m:
    raise SystemExit(1)
v = m.group(1).strip().strip('"').strip("'")
print(v if v else "", end="")
PY
}

TOKEN_SRC="none"
# ⚠️ 本函数在 $( ) 子 shell 里执行 → 不能靠变量回传来源，
#    所以输出格式固定为 "<token>\t<source>"，由主 shell 拆。
resolve_token() {
  if [ -n "${PINGCODE_API_TOKEN:-}" ]; then printf '%s\tenv:PINGCODE_API_TOKEN' "$PINGCODE_API_TOKEN"; return 0; fi
  if [ -f "$SECRET_FILE" ]; then
    v="$(head -n 1 "$SECRET_FILE" 2>/dev/null | tr -d '\r\n')"
    if [ -n "$v" ]; then printf '%s\tfile:%s' "$v" "$SECRET_FILE"; return 0; fi
  fi
  v="$(read_secret PINGCODE_API_TOKEN 2>/dev/null)"
  if [ -n "$v" ]; then printf '%s\ttracker_env:PINGCODE_API_TOKEN' "$v"; return 0; fi
  if command -v security >/dev/null 2>&1; then
    v="$(security find-generic-password -s pingcode-token -w 2>/dev/null)"
    if [ -n "$v" ]; then printf '%s\tkeychain:pingcode-token' "$v"; return 0; fi
  fi
  return 1
}

# 兜底：client_credentials 换 token
oauth_token() {
  local cid csec
  cid="$(read_secret PINGCODE_CLIENT_ID 2>/dev/null)"
  csec="$(read_secret PINGCODE_CLIENT_SECRET 2>/dev/null)"
  [ -n "$cid" ] && [ -n "$csec" ] || return 1
  curl -sS -m 20 -G "$API_BASE/v1/auth/token" \
    --data-urlencode "grant_type=client_credentials" \
    --data-urlencode "client_id=$cid" \
    --data-urlencode "client_secret=$csec" 2>/dev/null \
  | python3 -c 'import json,sys
try: print(json.load(sys.stdin)["access_token"], end="")
except Exception: raise SystemExit(1)' 2>/dev/null
}

RESOLVED="$(resolve_token || true)"
TOKEN="${RESOLVED%%$'\t'*}"
TOKEN_SRC="${RESOLVED#*$'\t'}"
[ "$TOKEN_SRC" = "$RESOLVED" ] && TOKEN_SRC="none"
USED_FALLBACK=0
if [ -z "$TOKEN" ]; then
  TOKEN="$(oauth_token || true)"
  [ -n "$TOKEN" ] && { USED_FALLBACK=1; TOKEN_SRC="oauth_fallback"; }
fi
[ -n "$TOKEN" ] || die "找不到 PingCode 令牌。已尝试：环境变量 PINGCODE_API_TOKEN / $SECRET_FILE / tracker .env / 钥匙串 / client_credentials 兜底"

# 调一次；401 且用的是兜底 token 时不重试，用 PAT 时也不自动换（PAT 失效需人工重新生成）
do_get() {
  local path="$1"; shift
  local args=(-sS -m 30 -H "Authorization: Bearer $TOKEN" -w '\n__HTTP__%{http_code}')
  local k v
  for kv in "$@"; do
    k="${kv%%=*}"; v="${kv#*=}"
    args+=(-G --data-urlencode "$k=$v")
  done
  curl "${args[@]}" "$API_BASE$path"
}

split_code() {
  # 从输出末尾取 __HTTP__<code>
  printf '%s' "$1" | python3 -c '
import sys
t = sys.stdin.read()
i = t.rfind("__HTTP__")
print(t[i+8:].strip() if i >= 0 else "000")
'
}
split_body() {
  printf '%s' "$1" | python3 -c '
import sys
t = sys.stdin.read()
i = t.rfind("__HTTP__")
print(t[:i].rstrip("\n") if i >= 0 else t.rstrip("\n"))
'
}

FORMAT='import json,sys
raw = sys.stdin.read()
try:
    d = json.loads(raw)
except Exception:
    print(raw); raise SystemExit(0)
def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items() if v not in (None, "", [], {})}
    if isinstance(o, list):
        return [clean(x) for x in o]
    return o
print(json.dumps(clean(d), ensure_ascii=False, indent=2))
'

case "${1:-}" in
  health)
    out="$(do_get /v1/project/work_items "project_id=69cfa488ff85507e68564f20" "page_size=1")"
    code="$(split_code "$out")"
    body="$(split_body "$out")"
    if [ "$code" = "200" ]; then
      total="$(printf '%s' "$body" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("total"))
except Exception: print("?")' 2>/dev/null)"
      printf '{"ok": true, "http": %s, "project_total": %s, "token_source": "%s"}\n' \
        "$code" "${total:-null}" "$TOKEN_SRC"
      exit 0
    fi
    printf '{"ok": false, "http": %s, "token_source": "%s"}\n' "$code" "$TOKEN_SRC"
    [ "$code" = "401" ] && echo "pc.sh: 令牌已失效 → 到 https://wanbridge.pingcode.com/account/access-token 点「重新生成」" >&2
    exit 1 ;;
  get)
    [ $# -ge 2 ] || die "用法: pc.sh get <path> [k=v ...]"
    path="$2"; shift 2
    out="$(do_get "$path" "$@")"
    code="$(split_code "$out")"
    body="$(split_body "$out")"
    [ "$code" = "200" ] || { echo "pc.sh: HTTP $code" >&2; printf '%s\n' "$body" >&2; exit 1; }
    if [ "$RAW" = "1" ]; then printf '%s\n' "$body"; else printf '%s\n' "$body" | python3 -c "$FORMAT"; fi ;;
  work_items)
    path="/v1/project/work_items"; shift
    args=("project_id=69cfa488ff85507e68564f20")
    while [ $# -gt 0 ]; do
      case "$1" in
        --identifier) args+=("identifier=$2"); shift 2 ;;
        --keywords|--keyword) args+=("keywords=$2"); shift 2 ;;
        --assignee) args+=("assignee_ids=$2"); shift 2 ;;
        --page-size) args+=("page_size=$2"); shift 2 ;;
        --page-index) args+=("page_index=$2"); shift 2 ;;
        --project-id) args+=("project_id=$2"); shift 2 ;;
        --raw) RAW=1; shift ;;
        *) die "未知参数: $1" ;;
      esac
    done
    out="$(do_get "$path" "${args[@]}")"
    code="$(split_code "$out")"
    body="$(split_body "$out")"
    [ "$code" = "200" ] || { echo "pc.sh: HTTP $code" >&2; printf '%s\n' "$body" >&2; exit 1; }
    if [ "$RAW" = "1" ]; then printf '%s\n' "$body"; else printf '%s\n' "$body" | python3 -c "$FORMAT"; fi ;;
  *)
    sed -n '2,16p' "$0"; exit 2 ;;
esac
