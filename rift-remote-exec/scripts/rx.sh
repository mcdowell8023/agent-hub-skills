#!/usr/bin/env bash
# rx.sh — 在已注册的远端主机上执行一条命令，**不经 LLM、不消耗额度**。
#
# 原理：paseo CLI 用 relay 连接串直接开远端终端（terminal-worker 在目标机上跑），
#       本机负责敲命令 + 读输出，命令本身在目标机的 shell 里执行。
#
# 用法:
#   rx.sh --hosts                        列出已注册主机
#   rx.sh --list                         列出远端现有终端
#   rx.sh --host-label <LABEL> [--cwd <PATH>] [--workspace <ID>] [--timeout <SEC>] -- <命令>
#
# 示例:
#   rx.sh --host-label wb-hub --cwd 'C:\Users\LienwaiverWB\wb' -- whoami
#   rx.sh --host-label wb-hub --cwd 'C:\Users\LienwaiverWB\wb' --timeout 120 -- 'dir /b C:\Users'
#
# 协议（两行，避免终端折行把哨兵拆开导致计数歧义）:
#   第 1 行: <命令>
#   第 2 行: echo __RX_OK__ && echo __RX_RC__%ERRORLEVEL% $?
#     · __RX_OK__  = 完成哨兵（回显 1 次 + 输出 1 次 = 2 次）
#     · __RX_RC__ = 上一行的退出码（cmd 读 %ERRORLEVEL%，sh 读 $?）
#   第 2 行里哨兵用 && 连接：cmd 与 sh 都按顺序执行，不会乱序。
#
# 判定:
#   完成 = 哨兵出现 ≥ 2 次（只回显没输出 → 不算完成）
#   成功 = 完成 且 退出码为 0；退出码非 0 → 退出码 125（不静默假成功）
#   超时 = 退出码 124
set -uo pipefail

HOSTS_JSON="${PASEO_HOSTS_JSON:-$HOME/.paseo/hosts.json}"
MARK='__RX_OK__'
RCMARK='__RX_RC__'
# 起始标记带唯一后缀：复用终端时 capture 里可能有历史运行的同名标记，
# rfind 会命中错误的位置 → 每次运行必须用唯一标记。
RUN_ID="$$_$(date +%s)"
BEGMARK="__RX_BEGIN_${RUN_ID}__"
TIMEOUT=60
CWD=""
WORKSPACE=""
LABEL=""
CMD=""
CMD_RAW=""
MODE="run"
CREATE_RETRIES=3
MARK_JOIN="&"
REUSE=1
LOCK_WAIT=120
NO_LOCK=0

while [ $# -gt 0 ]; do
  case "$1" in
    --hosts) MODE="hosts"; shift ;;
    --list) MODE="list"; shift ;;
    --host-label) LABEL="$2"; shift 2 ;;
    --cwd) CWD="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --retries) CREATE_RETRIES="$2"; shift 2 ;;
    --lock-wait) LOCK_WAIT="$2"; shift 2 ;;
    --no-lock) NO_LOCK=1; shift ;;
    --no-reuse) REUSE=0; shift ;;
    --) shift; CMD="$*"; CMD_RAW="$*"; break ;;
    -h|--help) sed -n '2,35p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

die() { echo "rx.sh: $*" >&2; exit 1; }

command -v paseo >/dev/null 2>&1 || die "找不到 paseo CLI（PATH 里没有）"
[ -f "$HOSTS_JSON" ] || die "找不到 $HOSTS_JSON"

conn_for() {
  python3 - "$HOSTS_JSON" "$1" <<'PY'
import json, sys
path, label = sys.argv[1], sys.argv[2]
try:
    hosts = json.load(open(path, encoding="utf-8"))
except Exception as e:
    sys.exit(f"解析 {path} 失败: {e}")
hit = None
for h in hosts:
    if label and h.get("label") == label:
        hit = h
        break
if hit is None and not label:
    hit = hosts[0] if len(hosts) == 1 else None
if hit is None:
    sys.exit(f"hosts.json 里找不到 label={label!r}（可用: {[h.get('label') for h in hosts]}）")
c = hit.get("connection")
if not c:
    sys.exit(f"host {hit.get('label')} 没有 connection 字段（只有 targetDescription，不够用）")
print(c)
PY
}

case "$MODE" in
  hosts)
    python3 - "$HOSTS_JSON" <<'PY'
import json, sys
for h in json.load(open(sys.argv[1], encoding="utf-8")):
    print(f"{h.get('label'):<20} {h.get('serverId'):<22} {h.get('status'):<8} {h.get('targetDescription')}")
PY
    exit 0 ;;
  list)
    CONN="$(conn_for "$LABEL")" || die "取连接串失败"
    paseo terminal ls --host "$CONN"
    exit 0 ;;
esac

[ -n "$CMD" ] || die "没有给命令。用法见 --help"
# 命令尾部片段：用来识别终端折行产生的「回显续行」
# ⚠️ 终端按窗口宽度（约 80 列）折行。命令太长 → 回显被拆成多行，
#    回显与真实输出无法可靠分离（输出可能整段丢失）。
#    超过 ~60 字符就应该改用「脚本下发模式」（见 SKILL.md §3）。
if [ ${#CMD} -gt 60 ]; then
  echo "rx.sh: ⚠️ 命令长度 ${#CMD} 字符，可能超终端宽度导致折行、输出失真。" >&2
  echo "rx.sh:    建议改用脚本下发：把脚本放到 Mac HTTP 目录，让 hub curl 后执行。" >&2
fi

# 命令尾部片段：识别终端折行产生的「回显续行」。
# 取命令最后 ~24 字符，并额外存一份「去空白」版本（终端可能插入/折断空白）。
CMD_NS="$(printf '%s' "$CMD" | tr -d '[:space:]')"
CONN="$(conn_for "$LABEL")" || die "取连接串失败"

# ---- 并发互斥 ----
# ⛔ 同一台机器上并发跑多个 rx.sh 会互相踩：两条命令交错进同一个终端，
#    输出与退出码全串台（实测踩到）。必须串行化。
# 锁里存 PID：进程被杀（SIGKILL）时锁会残留 → 用 PID 存活检查识别陈旧锁。
LOCK_DIR="${TMPDIR:-/tmp}/rx-lock-$(printf '%s' "$LABEL" | tr -c 'A-Za-z0-9._-' '_')"
mkdir -p "$LOCK_DIR"
LOCK="$LOCK_DIR/lock"
LOCKED=0
release_lock() {
  [ "$LOCKED" = 1 ] || return 0
  # 锁目录里有 pid 文件 → 先删文件再 rmdir。
  # 用 unlink 而不是 rm：本机 rm 被 shim 成 mavis-trash，单次要好几秒。
  unlink "$LOCK/pid" 2>/dev/null || true
  rmdir "$LOCK" 2>/dev/null || true
  LOCKED=0
}
lock_holder_alive() {
  local pid
  pid="$(cat "$LOCK/pid" 2>/dev/null)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null
}
clear_stale_lock() {
  # 锁目录里有 pid 文件 → 先 unlink 再 rmdir（unlink 不走 mavis-trash shim）
  unlink "$LOCK/pid" 2>/dev/null || true
  rmdir "$LOCK" 2>/dev/null || true
  [ ! -d "$LOCK" ]
}
acquire_lock() {
  mkdir "$LOCK" 2>/dev/null || return 1
  echo $$ > "$LOCK/pid" 2>/dev/null || true
  LOCKED=1
  return 0
}
if [ "$NO_LOCK" != 1 ]; then
if acquire_lock; then
  :
else
  # 陈旧锁（持锁进程已死）→ 清掉重试
  if ! lock_holder_alive; then
    echo "rx.sh: 发现陈旧锁（持锁进程已退出），清理后重试" >&2
    clear_stale_lock && acquire_lock || true
  fi
fi
if [ "$LOCKED" != 1 ]; then
  echo "rx.sh: 另一个 rx.sh 正在用这台机器（锁 ${LOCK}），等待最多 ${LOCK_WAIT}s…" >&2
  got=0
  stale_tries=0
  for _ in $(seq 1 "$LOCK_WAIT"); do
    sleep 1
    if acquire_lock; then got=1; break; fi
    # 陈旧锁清理：最多试 3 次，失败就放弃等待（避免死循环）
    if [ "$stale_tries" -lt 3 ] && ! lock_holder_alive; then
      stale_tries=$((stale_tries + 1))
      echo "rx.sh: 陈旧锁，清理后重试（第 ${stale_tries} 次）" >&2
      if clear_stale_lock; then
        acquire_lock && { got=1; break; }
      else
        echo "rx.sh: 陈旧锁清理失败（可能仍被占用），继续等待" >&2
        stale_tries=3
      fi
    fi
  done
  [ "$got" = 1 ] || die "等待并发锁超时（${LOCK_WAIT}s），另一个 rx.sh 还没结束"
fi
# 立刻挂上解锁 trap：此后任何退出路径（含 die）都会释放锁
trap 'release_lock' EXIT INT TERM
fi

# ---- 取终端 ----
# 关键经验（实测）：hub 端 terminal-worker 在多 agent 并发时**新建终端会超时**
# （TERMINAL_CREATE_FAILED: createTerminal timed out），但**已存在的终端一直好用**。
# 而 agent 通道（paseo ls）此时完全正常 → 是 terminal-worker 拥塞，不是 relay 断。
# 所以策略：先复用（cwd 相同 > 任意），复用不了再新建。
TID=""
REUSED=0
# 注意：try_cwd 在 $( ) 子 shell 里跑，变量赋值传不回主 shell →
# 失败原因必须直接写 stderr，不能靠变量带出来。
try_cwd() {
  local cwd="$1" args out tid
  args=(terminal create --host "$CONN" --name "rx-$$")
  [ -n "$cwd" ] && args+=(--cwd "$cwd")
  [ -n "$WORKSPACE" ] && args+=(--workspace "$WORKSPACE")
  out="$(paseo "${args[@]}" --json 2>&1)"
  tid="$(printf '%s' "$out" | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin)["id"])
except Exception:
    sys.exit(1)' 2>/dev/null)"
  [ -n "$tid" ] && { printf '%s' "$tid"; return 0; }
  printf 'rx.sh: 建终端失败（cwd=%s）：%s\n' "${cwd:-<空>}" \
    "$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-220)" >&2
  return 1
}

# 复用已有终端：优先 cwd 完全相同的，其次任意一个（命令里 cd 过去）
find_reusable() {
  paseo terminal ls --all --host "$CONN" 2>/dev/null | tail -n +2 | python3 -c '
import sys
want = sys.argv[1].lower().rstrip("\\")
rows = []
for line in sys.stdin:
    p = line.split()
    if len(p) < 2:
        continue
    rows.append((p[0], p[1]))
if not rows:
    raise SystemExit(1)
exact = [t for t, cwd in rows if cwd.lower().rstrip("\\") == want]
if exact:
    print(exact[0]); raise SystemExit(0)
print(rows[0][0])
' "$CWD" 2>/dev/null
}

# 切目录的**独立步骤**（不与命令拼成一行）
# ⛔ 不要拼成 `cd ... && <命令>`：拼起来后整行过长，终端会折行，
#    回显被拆成多行，与真实输出混在一起无法区分。
CD_STEP=""
prefix_cd() {
  case "$1" in
    [A-Za-z]:*) CD_STEP="cd /d \"$1\"" ;;
    "")         CD_STEP="" ;;
    *)          CD_STEP="cd \"$1\"" ;;
  esac
}

if [ "${REUSE}" = "1" ]; then
  if TID="$(find_reusable)"; then
    REUSED=1
    echo "rx.sh: 复用已有终端 $TID" >&2
    [ -n "$CWD" ] && prefix_cd "$CWD"
  fi
fi

if [ -z "$TID" ]; then
  for attempt in $(seq 1 "$CREATE_RETRIES"); do
    if TID="$(try_cwd "$CWD")"; then break; fi
    echo "rx.sh: 建终端第 $attempt 次失败，重试中…" >&2
    sleep 5
  done
fi

if [ -z "$TID" ] && [ -n "$CWD" ]; then
  # 降级：改用父目录作 cwd，再在命令里 cd 回目标目录。
  # [X] 不能「去掉 --cwd 且不传 --workspace」——CLI 会把**本机** cwd
  #    (/Users/mcdowell/wb) 当默认值发给远端，远端报 Directory not found。
  PARENT="${CWD%\\*}"
  [ "$PARENT" = "$CWD" ] && PARENT="${CWD%/*}"
  echo "rx.sh: 带 cwd 建终端连续失败，降级为「父目录建 + 命令内 cd」" >&2
  for attempt in $(seq 1 2); do
    if TID="$(try_cwd "$PARENT")"; then break; fi
    echo "rx.sh: 降级建终端第 $attempt 次失败，重试中…" >&2
    sleep 5
  done
  if [ -n "$TID" ]; then
    prefix_cd "$CWD"
    echo "rx.sh: 已降级，先切目录到 $CWD 再执行命令" >&2
  fi
fi
[ -n "$TID" ] || die "建终端失败（重试 $CREATE_RETRIES 次，且降级也失败）"

cleanup() {
  # 复用的终端**不要杀**（可能是别人/上一轮留下的、还在被用的）；
  # 只有自己新建的才回收。
  [ "$REUSED" = "1" ] && return 0
  paseo terminal kill --host "$CONN" "$TID" >/dev/null 2>&1 || true
}
# ⛔ 这里原本会覆盖锁的 trap —— 必须把解锁动作一起带上，否则锁泄漏（下次永远等）
trap 'cleanup; release_lock' EXIT INT TERM

# ---- 终端可能已被远端回收（复用终端会莫名消失）→ 重建一次 ----
if ! paseo terminal capture --host "$CONN" "$TID" >/dev/null 2>&1; then
  echo "rx.sh: 终端 $TID 已失效，重建" >&2
  TID=""
  REUSED=0
  for attempt in $(seq 1 "$CREATE_RETRIES"); do
    if TID="$(try_cwd "$CWD")"; then break; fi
    sleep 5
  done
  [ -n "$TID" ] || die "终端已失效且重建失败"
fi

# ---- 基线：记下发送前的提示符（最后一行非空） ----
BASE="$(paseo terminal capture --host "$CONN" "$TID" 2>/dev/null)"
PROMPT="$(printf '%s\n' "$BASE" | grep -v '^[[:space:]]*$' | tail -n 1 | sed -e 's/[[:space:]]*$//')"
PROMPT_CLEAN="$(printf '%s' "$PROMPT" | tr -d '[:space:]')"

# ---- 敲三行：起始标记 + 命令 + 完成/退出码探针 ----
# ① 起始标记：用来精确切出「本次输出区间」，把命令回显行排除掉
# ② 命令
# ③ 探针：单独一行 → %ERRORLEVEL% 取的是**上一行（命令）**的退出码
#    （同一行内取不准：cmd 在解析整行时就展开了 %ERRORLEVEL%）
# send-keys 失败通常意味着终端被远端回收了 → 重建后重试一次
send() {
  paseo terminal send-keys --host "$CONN" "$TID" "$1" Enter >/dev/null 2>&1 && return 0
  echo "rx.sh: send-keys 失败（终端可能已被回收），重建后重试" >&2
  TID=""
  REUSED=0
  for attempt in $(seq 1 "$CREATE_RETRIES"); do
    if TID="$(try_cwd "$CWD")"; then break; fi
    sleep 5
  done
  [ -n "$TID" ] || die "终端已失效且重建失败"
  # 重建后基线变了 → 重新取基线，否则输出裁剪会错位
  BASE="$(paseo terminal capture --host "$CONN" "$TID" 2>/dev/null)"
  PROMPT="$(printf '%s\n' "$BASE" | grep -v '^[[:space:]]*$' | tail -n 1 | sed -e 's/[[:space:]]*$//')"
  PROMPT_CLEAN="$(printf '%s' "$PROMPT" | tr -d '[:space:]')"
  paseo terminal send-keys --host "$CONN" "$TID" "$1" Enter >/dev/null 2>&1 \
    || die "send-keys 失败（重建后仍失败）"
}

send "echo $BEGMARK"
sleep 1
if [ -n "$CD_STEP" ]; then
  send "$CD_STEP"
  sleep 1
fi
send "$CMD"
sleep 1
send "echo ${RCMARK}%ERRORLEVEL% \$?"
sleep 1
send "echo $MARK"

# ---- 轮询等完成 ----
# 基线行数：用于把「复用终端」的旧 scrollback 裁掉，只输出本次命令的结果
BASE_LINES="$(printf '%s\n' "$BASE" | wc -l | tr -d ' ')"
DEADLINE=$(( $(date +%s) + TIMEOUT ))
TEXT=""
DONE=0
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  TEXT="$(paseo terminal capture --host "$CONN" "$TID" 2>/dev/null)"
  FLAT="$(printf '%s' "$TEXT" | tr -d '[:space:]')"
  COUNT="$(printf '%s' "$FLAT" | grep -o "$MARK" | wc -l | tr -d ' ')"
  if [ "${COUNT:-0}" -ge 2 ]; then DONE=1; break; fi
  # 兜底：某些 shell 不回显命令行 → 只有 1 次（输出那次），此时靠提示符重现判定
  if [ "${COUNT:-0}" -ge 1 ] && [ -n "$PROMPT_CLEAN" ]; then
    LAST="$(printf '%s\n' "$TEXT" | grep -v '^[[:space:]]*$' | tail -n 1 | tr -d '[:space:]')"
    if [ "$LAST" = "$PROMPT_CLEAN" ]; then DONE=1; break; fi
  fi
  sleep 1
done

# 本次输出 = 全量 capture 去掉基线部分
# 不用行数裁剪：终端滚动会让 capture 的行数与基线对不上（复用终端时尤其明显）。
# 锚点裁剪在下面的 Python 里做（rfind(__RX_BEGIN__) 之后就是本次内容）。
OUT="$TEXT"

if [ "$DONE" != 1 ]; then
  printf '%s\n' "$OUT" | grep -v '^[[:space:]]*$' | tail -n 60
  echo "rx.sh: 等待完成标记超时（${TIMEOUT}s），上面是超时前的输出" >&2
  exit 124
fi

# ---- 解析：切出输出区间 + 取退出码 ----
# 用「起始标记 __RX_BEGIN__」定位本次输出区间：
#   标记行(回显) → 标记行(输出) → 命令行(回显) → 命令输出 → 探针行(回显) → 探针输出
# 取最后一个 __RX_BEGIN__ 之后、探针之前的内容，去掉回显行与提示符行。
PARSED="$(printf '%s\n' "$OUT" | RX_CMD_NS="$CMD_NS" python3 -c '
import os, re, sys
txt = sys.stdin.read()
BEG  = "'"$BEGMARK"'"
RC   = "'"$RCMARK"'"
MARK = "'"$MARK"'"
CMDNS = os.environ.get("RX_CMD_NS", "")

# ---- 定位输出区间 ----
# 终端实际结构（cmd）：
#   <提示符><命令>        ← 回显第 1 行（以提示符开头）
#   <命令后半段>          ← 回显续行（终端按宽度折行，**不含提示符**）
#   <命令的真实输出>
#   <空行>
#   <提示符>echo __RX_RC__...
# 锚点 __RX_BEGIN__ 的「输出」那次之后，才是本次内容。
i = txt.rfind(BEG)
if i >= 0:
    txt = txt[i + len(BEG):]

# 回显续行的特征：包含命令原文的尾部片段（取尾部若干字符）
# （命令自身完整出现时也能覆盖；提示符行另行过滤）
lines = txt.splitlines()
# 找到退出码探针行，之前的都是命令回显 + 输出
end = len(lines)
for idx, l in enumerate(lines):
    if RC in l:
        end = idx
        break
body_lines = lines[:end]

# 回显块 = 从第一行（提示符行）开始，直到遇到「空行」或「不含命令尾部片段的行」
clean = []
skipping_echo = True
for l in body_lines:
    s2 = l.strip()
    if not s2:
        skipping_echo = False
        continue
    if skipping_echo:
        # 提示符回显行
        if re.match(r"^[A-Za-z]:\\?[^>]*>", s2):
            continue
        # 回显续行：终端把长命令折行后，逐行回显。
        # 判据 = 该行（去空白）是命令（去空白）的**后缀**。
        # （回显第 1 行带提示符，由上面的正则过滤；续行不带提示符。）
        if CMDNS:
            ns = re.sub(r"\s+", "", s2)
            if ns and CMDNS.endswith(ns):
                continue
        # 不是回显 → 已经是输出
        skipping_echo = False
    if MARK in s2 or RC in s2 or BEG in s2:
        continue
    if re.match(r"^[A-Za-z]:\\?[^>]*>", s2):
        continue
    if re.match(r"^\S+@\S+:\S*[$#]\s", s2):
        continue
    clean.append(s2)

body = "\n".join(clean)

# ---- 退出码 ----
rc = ""
flat = re.sub(r"\s+", "", txt)
k2 = flat.find(RC)
if k2 >= 0:
    tail = flat[k2 + len(RC):]
    is_sh = "%ERRORLEVEL%" in flat
    tail = tail.replace("%ERRORLEVEL%", " ").replace("$?", " ")
    nums = re.findall(r"-?\d+", tail)
    if nums:
        rc = nums[-1] if is_sh else nums[0]

print("---SPLIT---")
for l in clean[-200:]:
    print(l)
print("---RC---")
print(rc)
')"

EXITCODE="$(printf '%s\n' "$PARSED" | sed -n '/^---RC---$/,$p' | tail -n +2 | head -n 1)"
printf '%s\n' "$PARSED" | sed -n '/^---SPLIT---$/,/^---RC---$/p' | sed -e '1d' -e '$d'

if [ -z "${EXITCODE}" ]; then
  echo "rx.sh: 未取到退出码（命令可能已执行完，但退出码探针没解析出来）" >&2
  exit 0
fi
if [ "${EXITCODE}" != "0" ]; then
  echo "rx.sh: 命令退出码 = ${EXITCODE}（非 0，命令未成功）" >&2
  exit 125
fi
exit 0
