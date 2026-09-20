#!/bin/bash
# Keeps a SOCKS5 tunnel to an egress relay host alive.
#
# The relay address is intentionally NOT baked in — supply it yourself:
#   RELAY_HOST='user@relay-host' bash keep_socks.sh
#
# Links to home/relay machines are often carried over a NAT-traversal relay
# (e.g. Tailscale DERP), so idle tunnels get dropped with
# "Timeout, server ... not responding" — hence the restart loop.

set -u

if [ -z "${RELAY_HOST:-}" ]; then
  echo "[keep_socks] ERROR: RELAY_HOST is required, e.g. RELAY_HOST='user@host'" >&2
  exit 2
fi

SOCKS_PORT="${SOCKS_PORT:-1080}"

echo "[keep_socks] relay=${RELAY_HOST} socks=127.0.0.1:${SOCKS_PORT}"
while true; do
  ssh -N -D "127.0.0.1:${SOCKS_PORT}" \
      -o ExitOnForwardFailure=yes \
      -o ServerAliveInterval=15 -o ServerAliveCountMax=8 \
      -o BatchMode=yes -o ConnectTimeout=15 \
      -o StrictHostKeyChecking=accept-new \
      "$RELAY_HOST"
  echo "[keep_socks] tunnel exited, restarting in 2s"
  sleep 2
done
