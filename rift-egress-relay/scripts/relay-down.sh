#!/bin/bash
# Tear the egress relay down, and verify it is really down.
#
# 🔴 Order matters: the supervisor must die BEFORE its ssh child, otherwise
# it respawns the tunnel two seconds later and the teardown looks flaky.
#
# ⛔ Deliberately does NOT use broad `pkill -f` patterns — those match by
# command line and can hit unrelated processes. PID files first, then
# port-scoped lookup, and every PID is printed before being signalled.
set -u

SOCKS_PORT="${SOCKS_PORT:-1080}"
CONNECT_PORT="${CONNECT_PORT:-18888}"
RUN_DIR="${RIFT_RELAY_RUN_DIR:-${TMPDIR:-/tmp}/rift-egress-relay}"

port_pid() { lsof -t -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null; }

kill_pid() {  # $1=pid  $2=label
  local pid="$1" label="$2"
  [ -n "$pid" ] || return 0
  kill -0 "$pid" 2>/dev/null || { echo "[relay-down] $label pid $pid 已不存在"; return 0; }
  echo "[relay-down] kill $label pid $pid"
  kill "$pid" 2>/dev/null
  for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || return 0; sleep 0.2; done
  echo "[relay-down] $label pid $pid 未退出，升级 KILL"
  kill -9 "$pid" 2>/dev/null
}

# 1) supervisor FIRST（否则它会把隧道重新拉起来）
if [ -f "$RUN_DIR/socks.pid" ]; then
  kill_pid "$(cat "$RUN_DIR/socks.pid")" "socks supervisor"
else
  found="$(pgrep -f "keep_socks.sh" 2>/dev/null || true)"
  if [ -n "$found" ]; then
    echo "[relay-down] 无 pid 文件，按脚本名定位到: $found"
    for p in $found; do kill_pid "$p" "socks supervisor"; done
  fi
fi

# 2) ssh 子进程（supervisor 已死，不会再被拉起）
for p in $(port_pid "$SOCKS_PORT"); do kill_pid "$p" "socks tunnel"; done

# 3) CONNECT 垫片
if [ -f "$RUN_DIR/connect.pid" ]; then
  kill_pid "$(cat "$RUN_DIR/connect.pid")" "connect shim"
fi
for p in $(port_pid "$CONNECT_PORT"); do kill_pid "$p" "connect shim"; done

rm -f "$RUN_DIR/socks.pid" "$RUN_DIR/connect.pid"

# 4) 判据：两个端口都必须释放，否则下次起不来
rc=0
for prt in "$SOCKS_PORT" "$CONNECT_PORT"; do
  left="$(port_pid "$prt")"
  if [ -n "$left" ]; then
    echo "[relay-down] 🔴 端口 $prt 仍被占用: $left"; rc=1
  else
    echo "[relay-down] ✅ 端口 $prt 已释放"
  fi
done

echo "[relay-down] ⚠️ 别忘了当前 shell 里的变量: unset HTTPS_PROXY"
exit $rc
