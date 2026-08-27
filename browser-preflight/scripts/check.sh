#!/bin/bash
# browser-preflight check — 浏览器工具链健康检查
# 用法: check.sh [--fix] [--hub] [--json]
#   --fix   尝试自动修复可修复的问题
#   --hub   同时检查 Hub 端
#   --json  输出 JSON 格式（供 agent 解析）

set -uo pipefail

FIX=false
CHECK_HUB=false
JSON_OUT=false
HUB_HOST="${HUB_SSH_HOST:-hub}"
HUB_CDP="${HUB_CDP_URL:-http://127.0.0.1:9222}"

for arg in "$@"; do
  case "$arg" in
    --fix) FIX=true ;;
    --hub) CHECK_HUB=true ;;
    --json) JSON_OUT=true ;;
  esac
done

PASS=0
FAIL=0
WARN=0
RESULTS=()

check() {
  local name="$1" status="$2" detail="$3" fixable="${4:-false}"
  RESULTS+=("{\"name\":\"$name\",\"status\":\"$status\",\"detail\":\"$detail\",\"fixable\":$fixable}")
  case "$status" in
    pass) PASS=$((PASS+1)); $JSON_OUT || echo "  ✅ $name" ;;
    fail) FAIL=$((FAIL+1)); $JSON_OUT || echo "  ❌ $name — $detail" ;;
    warn) WARN=$((WARN+1)); $JSON_OUT || echo "  ⚠️  $name — $detail" ;;
  esac
}

# ──────────── Mac 本地检查 ────────────

$JSON_OUT || echo "=== Mac 本地 ==="

# 1. browser-harness 安装
if command -v browser-harness >/dev/null 2>&1; then
  BH_VER=$(browser-harness --version 2>&1)
  check "browser-harness" "pass" "$BH_VER"
else
  check "browser-harness" "fail" "未安装。uv tool install browser-harness" true
  if $FIX; then
    echo "    → 修复: uv tool install browser-harness"
    uv tool install browser-harness 2>&1 | tail -1
  fi
fi

# 2. opencli 安装
if command -v opencli >/dev/null 2>&1; then
  OC_VER=$(opencli --version 2>&1)
  check "opencli" "pass" "v$OC_VER"
else
  check "opencli" "fail" "未安装。npm i -g @jackwener/opencli" true
  if $FIX; then
    echo "    → 修复: npm i -g @jackwener/opencli"
    npm i -g @jackwener/opencli 2>&1 | tail -1
  fi
fi

# 3. Chrome 运行
if pgrep -qf "Google Chrome|chrome" 2>/dev/null; then
  check "chrome-running" "pass" "Chrome 进程在跑"
else
  check "chrome-running" "fail" "Chrome 未运行" true
  if $FIX; then
    echo "    → 修复: open -a 'Google Chrome'"
    open -a "Google Chrome" 2>/dev/null
    sleep 3
  fi
fi

# 4. Chrome CDP 可达（DevToolsActivePort）
CDP_OK=false
# 检查 DevToolsActivePort 文件
for profile_dir in \
  "$HOME/Library/Application Support/Google/Chrome" \
  "$HOME/.config/google-chrome"; do
  if [ -f "$profile_dir/DevToolsActivePort" ]; then
    CDP_PORT=$(head -1 "$profile_dir/DevToolsActivePort" 2>/dev/null)
    if [ -n "$CDP_PORT" ] && curl -sf "http://127.0.0.1:$CDP_PORT/json/version" >/dev/null 2>&1; then
      CDP_OK=true
      check "chrome-cdp" "pass" "DevToolsActivePort 端口 $CDP_PORT"
      break
    fi
  fi
done
if ! $CDP_OK; then
  # 尝试 9222
  if curl -sf "http://127.0.0.1:9222/json/version" >/dev/null 2>&1; then
    CDP_OK=true
    check "chrome-cdp" "pass" "端口 9222"
  else
    check "chrome-cdp" "fail" "CDP 不可达" true
    if $FIX; then
      echo "    → 修复: 启动 Chrome-Debug（独立 profile + CDP 9222）..."
      case "$(uname -s)" in
        Darwin)
          "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
            --remote-debugging-port=9222 \
            --user-data-dir="$HOME/Library/Application Support/Google/Chrome-Debug" \
            --no-first-run about:blank >/dev/null 2>&1 &
          ;;
        Linux)
          WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/$(id -u) \
          DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus \
          google-chrome --remote-debugging-port=9222 --no-first-run \
            --ozone-platform=wayland \
            --user-data-dir="$HOME/.config/chrome-debug" \
            about:blank >/dev/null 2>&1 &
          ;;
      esac
      sleep 5
      if curl -sf "http://127.0.0.1:9222/json/version" >/dev/null 2>&1; then
        CDP_OK=true
        echo "    ✅ Chrome-Debug 已启动"
      else
        echo "    ❌ 启动失败。手动运行 Chrome-Debug 或检查 Wayland session"
      fi
    fi
  fi
fi

# 5. browser-harness daemon
if command -v browser-harness >/dev/null 2>&1; then
  DOCTOR=$(browser-harness --doctor 2>&1)
  if echo "$DOCTOR" | grep -q "\[ok  \] daemon alive"; then
    check "bh-daemon" "pass" "daemon 运行中"
  else
    check "bh-daemon" "fail" "daemon 未启动（需要 CDP 先通）" true
    if $FIX && $CDP_OK; then
      echo "    → 修复: 启动 daemon..."
      timeout 10 browser-harness -c "print('daemon started')" 2>/dev/null && check "bh-daemon-fix" "pass" "已修复"
    fi
  fi
fi

# 6. opencli Browser Bridge
if command -v opencli >/dev/null 2>&1; then
  OC_DOC=$(opencli doctor 2>&1)
  if echo "$OC_DOC" | grep -q "\[OK\] Extension: connected"; then
    EXT_VER=$(echo "$OC_DOC" | grep "Extension:" | grep -o "v[0-9.]*")
    check "opencli-bridge" "pass" "Extension connected $EXT_VER"
  elif echo "$OC_DOC" | grep -q "\[OK\] Daemon"; then
    check "opencli-bridge" "warn" "Daemon OK 但 Extension 未连接（Chrome 里有 OpenCLI 扩展吗？）" false
  else
    check "opencli-bridge" "fail" "Daemon 未运行" true
    if $FIX; then
      echo "    → 修复: opencli daemon restart"
      opencli daemon restart 2>&1 | tail -1
    fi
  fi
fi

# 7. Jina Reader API
JINA_OK=$(curl -sf -o /dev/null -w "%{http_code}" -H "Accept: text/markdown" "https://r.jina.ai/https://example.com" 2>&1)
if [ "$JINA_OK" = "200" ]; then
  check "jina-reader" "pass" "API 可达"
else
  # 变量名必须加 {}：紧跟中文全角括号时，bash 会把多字节字符首字节（0xEF）
  # 吞进变量名，配合 set -u 直接 unbound variable 崩溃
  check "jina-reader" "warn" "HTTP ${JINA_OK}（可能被限流或网络问题）" false
fi

# ──────────── Hub 检查 ────────────

if $CHECK_HUB; then
  $JSON_OUT || echo ""
  $JSON_OUT || echo "=== Hub ($HUB_HOST) ==="

  # Hub SSH 连通
  if ssh -o ConnectTimeout=5 "$HUB_HOST" "echo ok" >/dev/null 2>&1; then
    check "hub-ssh" "pass" "SSH 连通"
  else
    check "hub-ssh" "fail" "$HUB_HOST 不可达" false
    # 后续 hub 检查全跳过
    CHECK_HUB=false
  fi

  if $CHECK_HUB; then
    # Hub Chrome CDP
    HUB_CDP_STATUS=$(ssh -o ConnectTimeout=5 "$HUB_HOST" "curl -sf http://127.0.0.1:9222/json/version 2>&1" 2>/dev/null)
    if echo "$HUB_CDP_STATUS" | grep -q "Browser"; then
      HUB_CHROME_VER=$(echo "$HUB_CDP_STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('Browser','?'))" 2>/dev/null)
      check "hub-chrome-cdp" "pass" "$HUB_CHROME_VER"
    else
      check "hub-chrome-cdp" "fail" "Hub Chrome CDP 不可达（9222 端口）" true
      if $FIX; then
        echo "    → 修复: 启动 Hub Chrome..."
        ssh "$HUB_HOST" 'WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus nohup google-chrome --remote-debugging-port=9222 --no-first-run --ozone-platform=wayland --user-data-dir=$HOME/.config/chrome-debug about:blank > /tmp/chrome-preflight.log 2>&1 & sleep 5 && ss -tlnp | grep 9222 && echo "STARTED" || echo "FAILED"' 2>&1 | tail -2
      fi
    fi

    # Hub opencli
    HUB_OC=$(ssh -o ConnectTimeout=5 "$HUB_HOST" "opencli doctor 2>&1" 2>/dev/null)
    if echo "$HUB_OC" | grep -q "\[OK\] Connectivity"; then
      check "hub-opencli" "pass" "三绿"
    elif echo "$HUB_OC" | grep -q "\[OK\] Daemon"; then
      check "hub-opencli" "warn" "Daemon OK 但 Extension/Connectivity 有问题" false
    else
      check "hub-opencli" "fail" "opencli 不可用" false
    fi

    # Hub browser-harness
    HUB_BH=$(ssh -o ConnectTimeout=5 "$HUB_HOST" "browser-harness --version 2>&1" 2>/dev/null)
    if echo "$HUB_BH" | grep -q "^[0-9]"; then
      check "hub-browser-harness" "pass" "v$HUB_BH"
    else
      check "hub-browser-harness" "fail" "未安装或不可用" true
    fi
  fi
fi

# ──────────── 汇总 ────────────

$JSON_OUT || echo ""

if $JSON_OUT; then
  echo "{\"pass\":$PASS,\"fail\":$FAIL,\"warn\":$WARN,\"results\":[$(IFS=,; echo "${RESULTS[*]}")]}"
else
  TOTAL=$((PASS+FAIL+WARN))
  if [ $FAIL -eq 0 ]; then
    echo "🟢 全部通过 ($PASS pass, $WARN warn)"
  else
    echo "🔴 有 $FAIL 项失败 ($PASS pass, $WARN warn, $FAIL fail)"
    echo ""
    echo "快速修复: $0 --fix$([ "$CHECK_HUB" = "true" ] && echo " --hub")"
  fi
fi

exit $FAIL
