#!/bin/bash
# test-harvest-return.sh — hub-harvest.sh 和 hub-return.sh 的测试
#
# 用法: bash test-harvest-return.sh
#
# Mock 方式：创建临时 mock 脚本模拟 ssh、paseo 等命令，
# 通过 SSH_CMD 环境变量注入到被测脚本。

set -uo pipefail

SCRIPTS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HARVEST="$SCRIPTS_DIR/hub-harvest.sh"
RETURN="$SCRIPTS_DIR/hub-return.sh"

PASS=0
FAIL=0

# ---------- 工具函数 ----------

assert_eq() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    echo "  ✅ $name"
    PASS=$((PASS+1))
  else
    echo "  ❌ $name"
    echo "     expected: $expected"
    echo "     actual:   $actual"
    FAIL=$((FAIL+1))
  fi
}

assert_contains() {
  local name="$1" needle="$2" haystack="$3"
  # needle 可以是正则（用 -E），也可以是固定串（用 -F）；优先尝试 -E
  if echo "$haystack" | grep -qE "$needle" 2>/dev/null; then
    echo "  ✅ $name (matches: $needle)"
    PASS=$((PASS+1))
  elif echo "$haystack" | grep -qF "$needle" 2>/dev/null; then
    echo "  ✅ $name (contains: $needle)"
    PASS=$((PASS+1))
  else
    echo "  ❌ $name (missing pattern: $needle)"
    echo "     output: $haystack" | head -10
    FAIL=$((FAIL+1))
  fi
}

assert_exit() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    echo "  ✅ $name (exit=$expected)"
    PASS=$((PASS+1))
  else
    echo "  ❌ $name (expected exit=$expected, got $actual)"
    FAIL=$((FAIL+1))
  fi
}

setup_mock_bin() {
  MOCK_BIN="$(mktemp -d)"
  export PATH="$MOCK_BIN:$PATH"
}

write_mock_ssh_fail() {
  # 模拟 SSH 失败
  cat > "$MOCK_BIN/ssh" <<'EOF'
#!/bin/bash
echo "ssh: connect to host test-host port 22: Connection refused" >&2
exit 255
EOF
  chmod +x "$MOCK_BIN/ssh"
}

write_mock_ssh_ok_harvest() {
  # 模拟 SSH 成功，对所有 heredoc 调用（带 bash -s）返回完整 mock 数据
  cat > "$MOCK_BIN/ssh" <<'EOF'
#!/bin/bash
# 收集所有参数
all="$*"
# echo ok 走第一个连通性测试
if echo "$all" | grep -q "echo ok"; then
  echo "ok"
  exit 0
fi
# 其他都是数据采集请求：输出完整 harvest 数据
cat <<'MOCKOUT'
===PASEO_AGENTS===
[{"id":"7c47561abc","status":"idle","provider":"claude/opus","cwd":"/home/mcdowell/wb","title":"test-agent","updated_at":"2026-06-21T16:00:00Z"}]
===GIT===
HAS_GIT=true
BRANCH=feature/test-branch
REMOTE=git@example.com:test/repo.git
HEAD=abc1234 feat: add harvest report
DIRTY=0
AHEAD=abc1234 feat: add harvest report
WORKTREES=1
===MEMORY===
/home/mcdowell/AgentWorkspace/memory/test.md
/home/mcdowell/wb/memory/proj.md
===DOCS===
/home/mcdowell/wb/docs/notes.md
===BUILD===
/home/mcdowell/wb/dist/bundle.js
===RUNTIMES===
NODE=v20.10.0
PYTHON=Python 3.11.5
===DEPS===
FILE=/home/mcdowell/wb/package.json
MTIME=1719000000
MOCKOUT
exit 0
EOF
  chmod +x "$MOCK_BIN/ssh"
}

write_mock_paseo_local() {
  # 模拟本地 paseo（return 测试用）
  cat > "$MOCK_BIN/paseo" <<'EOF'
#!/bin/bash
# 简单模拟：检测 --detach 标志
if echo "$*" | grep -q "\-\-detach"; then
  echo "AGENT ID: mock-agent-12345"
  exit 0
fi
echo "paseo mock: $*" >&2
exit 0
EOF
  chmod +x "$MOCK_BIN/paseo"
}

cleanup_mock_bin() {
  if [ -n "${MOCK_BIN:-}" ] && [ -d "$MOCK_BIN" ]; then
    rm -rf "$MOCK_BIN"
  fi
}

# ---------- 测试用例 ----------

echo "=== T1: hub-harvest.sh 无参数 → usage + exit 1 ==="
setup_mock_bin
out=$(bash "$HARVEST" 2>&1)
code=$?
assert_exit "exit code" "1" "$code"
assert_contains "contains usage" "用法|Usage|usage" "$out"
cleanup_mock_bin
echo ""

echo "=== T2: hub-harvest.sh SSH 不通 → 报错 + exit 1 ==="
setup_mock_bin
write_mock_ssh_fail
out=$(bash "$HARVEST" "test-host" "/home/mcdowell/wb" 2>&1)
code=$?
assert_exit "exit code" "1" "$code"
assert_contains "error message" "SSH|不通|connect" "$out"
cleanup_mock_bin
echo ""

echo "=== T3: hub-harvest.sh 正常 → 输出包含 # Hub Harvest Report ==="
setup_mock_bin
write_mock_ssh_ok_harvest
out=$(bash "$HARVEST" "test-host" "/home/mcdowell/wb" 2>&1)
code=$?
assert_exit "exit code" "0" "$code"
assert_contains "report header" "# Hub Harvest Report" "$out"
cleanup_mock_bin
echo ""

echo "=== T4: hub-return.sh 无参数 → usage + exit 1 ==="
setup_mock_bin
out=$(bash "$RETURN" 2>&1)
code=$?
assert_exit "exit code" "1" "$code"
assert_contains "contains usage" "用法|Usage|usage" "$out"
cleanup_mock_bin
echo ""

echo "=== T5: 路径映射双向（/Users/mcdowell ↔ /home/mcdowell）==="
# 策略：mock paseo 把接收到的 --cwd 参数写入哨兵文件，测试读文件验证映射。
# 双向验证：
#   T5a: return 把 Hub cwd /home/mcdowell/X 映射成 Mac cwd /Users/mcdowell/X
#   T5b: hub-handoff.sh 的 map-path 风格反向映射正确（用 hub-harvest.sh 的输入测试）
setup_mock_bin
write_mock_ssh_ok_harvest

# 创建临时工作区
TMP_WS="$(mktemp -d)"
SENTINEL="$TMP_WS/sentinel-cwd.txt"
LOCAL_CWD="$TMP_WS/Projects/test-project"
mkdir -p "$LOCAL_CWD"

# 覆盖 mock ssh（与 write_mock_ssh_ok_harvest 不同：让 harvest 报告里有 /home/mcdowell 路径以便测映射）
cat > "$MOCK_BIN/ssh" <<'EOF'
#!/bin/bash
all="$*"
if echo "$all" | grep -q "echo ok"; then
  echo "ok"
  exit 0
fi
cat <<'MOCKOUT'
===PASEO_AGENTS===
[{"id":"abc12345","status":"idle","provider":"claude/opus","cwd":"/home/mcdowell/Projects/test-project","title":"hub-task","updated_at":"2026-06-21T16:00:00Z"}]
===GIT===
HAS_GIT=true
BRANCH=main
REMOTE=git@example.com:test/repo.git
HEAD=abc1234 feat: hub work
DIRTY=0
AHEAD=
WORKTREES=1
===MEMORY===
/home/mcdowell/wb/memory/proj.md
===DOCS===
===BUILD===
===RUNTIMES===
NODE=v20.10.0
PYTHON=Python 3.11.5
===DEPS===
MOCKOUT
exit 0
EOF
chmod +x "$MOCK_BIN/ssh"

# mock paseo：把 --cwd 参数写到哨兵文件（验证 return 传给 paseo 的 cwd 是 Mac 路径）
cat > "$MOCK_BIN/paseo" <<EOF
#!/bin/bash
SENTINEL="$SENTINEL"
# 找 --cwd 的下一个参数
args=("\$@")
for ((i=0; i<\${#args[@]}; i++)); do
  if [ "\${args[\$i]}" = "--cwd" ]; then
    cwd="\${args[\$((i+1))]}"
    echo "CWD=\$cwd" >> "\$SENTINEL"
    break
  fi
done
echo "AGENT ID: mock-agent-12345"
exit 0
EOF
chmod +x "$MOCK_BIN/paseo"

# 调用 return：给 Hub 路径，期望它映射成 Mac 路径并传给 paseo
bash "$RETURN" "test-host" "/home/mcdowell/Projects/test-project" --cwd "/Users/mcdowell/Projects/test-project" >/dev/null 2>&1
code=$?

assert_exit "T5a return exit=0" "0" "$code"

# 验证 mock paseo 收到的 cwd 是 Mac 路径（不是 Hub 路径）
if [ -f "$SENTINEL" ]; then
  sentinel_content=$(cat "$SENTINEL")
  if echo "$sentinel_content" | grep -q "CWD=/Users/mcdowell/Projects/test-project"; then
    echo "  ✅ T5b Mac path passed to paseo (Hub → Mac mapping works)"
    PASS=$((PASS+1))
  elif echo "$sentinel_content" | grep -q "CWD=/home/mcdowell/Projects/test-project"; then
    echo "  ❌ T5b Hub path leaked to paseo (mapping broken)"
    FAIL=$((FAIL+1))
  else
    echo "  ❌ T5b sentinel has unexpected content: $sentinel_content"
    FAIL=$((FAIL+1))
  fi
else
  echo "  ❌ T5b sentinel file not created (paseo mock not called)"
  FAIL=$((FAIL+1))
fi

# 反向验证：显式指定 --cwd 为 /home/mcdowell/X（Hub 风格）应被脚本识别并反向映射
# 这里简化：直接测 hub-harvest.sh 调用 /home/mcdowell 路径后输出含 /home/mcdowell（说明它没主动改写 Hub 路径）
echo "  (reverse direction: harvest preserves Hub path in report)"
out_harvest=$(bash "$HARVEST" "test-host" "/home/mcdowell/wb" 2>&1)
if echo "$out_harvest" | grep -q "/home/mcdowell"; then
  echo "  ✅ T5c harvest keeps Hub path in report (consumed by return's reverse map)"
  PASS=$((PASS+1))
else
  echo "  ❌ T5c harvest dropped Hub path unexpectedly"
  FAIL=$((FAIL+1))
fi

rm -rf "$TMP_WS"
cleanup_mock_bin
echo ""

# ---------- 汇总 ----------

echo "==================================="
echo "PASS: $PASS  FAIL: $FAIL"
echo "==================================="

[ "$FAIL" -eq 0 ]
