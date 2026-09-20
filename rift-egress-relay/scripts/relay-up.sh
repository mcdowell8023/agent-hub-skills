#!/bin/bash
# Bring the egress relay up: SOCKS tunnel (auto-reconnect) + HTTP CONNECT shim.
#
#   RELAY_HOST='user@relay-host' bash relay-up.sh
#
# Idempotent: re-running while already up is a no-op, so it is safe to call
# again after a suspected drop.
set -u

SOCKS_PORT="${SOCKS_PORT:-1080}"
CONNECT_PORT="${CONNECT_PORT:-18888}"
RUN_DIR="${RIFT_RELAY_RUN_DIR:-${TMPDIR:-/tmp}/rift-egress-relay}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$RUN_DIR"

port_pid() { lsof -t -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | head -1; }

# --- CONNECT shim (local only, needs no relay host) ---
if [ -n "$(port_pid "$CONNECT_PORT")" ]; then
  echo "[relay-up] CONNECT shim already up on $CONNECT_PORT (pid $(port_pid "$CONNECT_PORT"))"
else
  nohup python3 "$HERE/connect_via_socks.py" "$SOCKS_PORT" "$CONNECT_PORT" \
        >"$RUN_DIR/connect.log" 2>&1 &
  echo $! >"$RUN_DIR/connect.pid"
  echo "[relay-up] CONNECT shim started (pid $(cat "$RUN_DIR/connect.pid"))"
fi

# --- SOCKS tunnel supervisor ---
if [ -n "$(port_pid "$SOCKS_PORT")" ]; then
  echo "[relay-up] SOCKS already up on $SOCKS_PORT (pid $(port_pid "$SOCKS_PORT"))"
else
  if [ -z "${RELAY_HOST:-}" ]; then
    echo "[relay-up] ERROR: RELAY_HOST is required, e.g. RELAY_HOST='user@host'" >&2
    exit 2
  fi
  RELAY_HOST="$RELAY_HOST" SOCKS_PORT="$SOCKS_PORT" \
    nohup bash "$HERE/keep_socks.sh" >"$RUN_DIR/socks.log" 2>&1 &
  echo $! >"$RUN_DIR/socks.pid"
  echo "[relay-up] SOCKS supervisor started (pid $(cat "$RUN_DIR/socks.pid"))"
fi

# --- wait for the tunnel to actually listen ---
for _ in $(seq 1 30); do
  [ -n "$(port_pid "$SOCKS_PORT")" ] && break
  sleep 0.5
done

if [ -z "$(port_pid "$SOCKS_PORT")" ]; then
  echo "[relay-up] 🔴 SOCKS did not come up; check $RUN_DIR/socks.log" >&2
  echo "           常见原因：中继机关机/休眠，或 RELAY_HOST 写错" >&2
  exit 1
fi

echo "[relay-up] ✅ up.  run dir: $RUN_DIR"
echo "           export HTTPS_PROXY=http://127.0.0.1:${CONNECT_PORT}"
echo "           自检: HTTPS_PROXY=http://127.0.0.1:${CONNECT_PORT} <你的认证过的 API 调用>"
