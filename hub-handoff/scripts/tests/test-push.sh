#!/bin/bash
# test-push.sh — hub-push.sh 的测试
#
# 用法: bash test-push.sh
#
# Mock 方式：创建临时 mock 脚本模拟 ssh、paseo 等命令，
# 通过 SSH_CMD / PASEO_CMD 环境变量注入到被测脚本。

set -uo pipefail

SCRIPTS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PUSH="$SCRIPTS_DIR/hub-push.sh"

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
  if echo "$haystack" | grep -qE "$needle" 2>/dev/null; then
    echo "  ✅ $name (matches: $needle)"
    PASS=$((PASS+1))
  elif echo "$haystack" | grep -qF "$needle" 2>/dev/null; then
    echo "  ✅ $name (contains: $needle)"
    PASS=$((PASS+1))
  else
    echo "  ❌ $name (missing pattern: $needle)"
    echo "     output (head): $(echo "$haystack" | head -10)"
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

cleanup_mock_bin() {
  if [ -n "${MOCK_BIN:-}" ] && [ -d "$MOCK_BIN" ]; then
    rm -rf "$MOCK_BIN"
  fi
}

# ---------- Mock 生成器 ----------

# 模拟本地 git 项目：分支 main，干净
setup_local_git_repo() {
  local dir="$1"
  mkdir -p "$dir"
  cd "$dir"
  git init -q
  git config user.email "test@test.com"
  git config user.name "test"
  echo "test" > README.md
  git add README.md
  git commit -q -m "init"
}

# 模拟 paseo run --host 创建远端 agent，写入哨兵记录所有参数
write_mock_paseo_record() {
  local sentinel="$1"
  cat > "$MOCK_BIN/paseo" <<EOF
#!/bin/bash
SENTINEL="$sentinel"
echo "ARGS: \$*" >> "\$SENTINEL"
echo "AGENT ID: mock-remote-agent-aaaa"
exit 0
EOF
  chmod +x "$MOCK_BIN/paseo"
}

# ---------- 测试用例 ----------

echo "=== T1: hub-push.sh 无参数 → usage + exit 1 ==="
setup_mock_bin
out=$(bash "$PUSH" 2>&1)
code=$?
assert_exit "exit code" "1" "$code"
assert_contains "contains usage" "用法|Usage|usage" "$out"
cleanup_mock_bin
echo ""

echo "=== T2: hub-push.sh 本地 cwd 不存在 → exit 1 ==="
setup_mock_bin
out=$(bash "$PUSH" "mac-host" "/nonexistent/path/xyz123" 2>&1)
code=$?
assert_exit "exit code" "1" "$code"
assert_contains "error mentions path" "路径|不存在|not exist|not found|不存在|cwd" "$out"
cleanup_mock_bin
echo ""

echo "=== T3: hub-push.sh 正常 → 调用 paseo run --host 创建远端 agent ==="
setup_mock_bin
TMP_WS="$(mktemp -d)"
SENTINEL="$TMP_WS/sentinel.txt"
LOCAL_CWD="$TMP_WS/my-project"
setup_local_git_repo "$LOCAL_CWD"
write_mock_paseo_record "$SENTINEL"

out=$(bash "$PUSH" "mac-host" "$LOCAL_CWD" --provider claude --model opus 2>&1)
code=$?
assert_exit "exit code" "0" "$code"
assert_contains "output mentions agent" "agent|AGENT|已创建|创建" "$out"

# 验证 mock paseo 被调用过
if [ -f "$SENTINEL" ] && grep -q "ARGS:" "$SENTINEL"; then
  # 验证传了 --host <mac-host>
  if grep -q -- "--host mac-host" "$SENTINEL"; then
    echo "  ✅ --host mac-host passed to paseo"
    PASS=$((PASS+1))
  else
    echo "  ❌ --host mac-host NOT in paseo args"
    echo "     args: $(cat "$SENTINEL")"
    FAIL=$((FAIL+1))
  fi
  # 验证传了 --detach
  if grep -q -- "--detach" "$SENTINEL"; then
    echo "  ✅ --detach passed to paseo"
    PASS=$((PASS+1))
  else
    echo "  ❌ --detach NOT in paseo args"
    FAIL=$((FAIL+1))
  fi
  # 验证传了 --provider claude/opus
  if grep -q -- "--provider claude/opus" "$SENTINEL"; then
    echo "  ✅ --provider claude/opus passed to paseo"
    PASS=$((PASS+1))
  else
    echo "  ❌ --provider NOT in paseo args"
    FAIL=$((FAIL+1))
  fi
else
  echo "  ❌ sentinel missing or empty (paseo not invoked)"
  FAIL=$((FAIL+1))
fi

rm -rf "$TMP_WS"
cleanup_mock_bin
echo ""

echo "=== T4: 路径映射 Mac→Hub（/Users/mcdowell → /home/mcdowell）==="
# 模拟在 Mac 上调用：cwd 包含 /Users/mcdowell 路径前缀，
# 期望传给远端 paseo 的 --cwd 是 /home/mcdowell/...（已映射）
setup_mock_bin
TMP_WS="$(mktemp -d)"
SENTINEL="$TMP_WS/sentinel.txt"
# 用一个"模拟 /Users/mcdowell" 的子目录做 cwd
MAC_CWD="$TMP_WS/Users/mcdowell/wb/projects/foo"
setup_local_git_repo "$MAC_CWD"
write_mock_paseo_record "$SENTINEL"

bash "$PUSH" "mac-host" "$MAC_CWD" --provider claude --model opus >/dev/null 2>&1
code=$?

assert_exit "T4 exit code" "0" "$code"

if [ -f "$SENTINEL" ]; then
  sentinel_content=$(cat "$SENTINEL")
  # 期望：传给 --cwd 的是 /home/mcdowell/wb/projects/foo
  if echo "$sentinel_content" | grep -qE -- "--cwd [^ ]*home/mcdowell/wb/projects/foo"; then
    echo "  ✅ Mac path /Users/mcdowell/... → Hub path /home/mcdowell/..."
    PASS=$((PASS+1))
  elif echo "$sentinel_content" | grep -qE -- "--cwd [^ ]*Users/mcdowell"; then
    echo "  ❌ Mac path leaked to remote (no mapping)"
    FAIL=$((FAIL+1))
  else
    echo "  ❌ unexpected cwd in args: $sentinel_content"
    FAIL=$((FAIL+1))
  fi
else
  echo "  ❌ sentinel missing"
  FAIL=$((FAIL+1))
fi

rm -rf "$TMP_WS"
cleanup_mock_bin
echo ""

echo "=== T5: 路径映射 Hub→Mac（/home/mcdowell → /Users/mcdowell）==="
# hub-push.sh 主要场景是"从 Hub 主动推送到 Mac"，所以 cwd 通常是 /home/mcdowell/...
# 此时远端是 Mac，应把 cwd 里的 /home/mcdowell 映射成 /Users/mcdowell/...
# 验证：传 --cwd 时如果有 /home/mcdowell 出现，传给远端 paseo 时应被替换
setup_mock_bin
TMP_WS="$(mktemp -d)"
SENTINEL="$TMP_WS/sentinel.txt"
# 模拟 Hub cwd: /home/mcdowell/...
HUB_CWD="$TMP_WS/home/mcdowell/wb/projects/bar"
setup_local_git_repo "$HUB_CWD"
write_mock_paseo_record "$SENTINEL"

bash "$PUSH" "mac-host" "$HUB_CWD" --provider claude --model opus >/dev/null 2>&1
code=$?

assert_exit "T5 exit code" "0" "$code"

if [ -f "$SENTINEL" ]; then
  sentinel_content=$(cat "$SENTINEL")
  # 期望：传给远端 Mac 的 --cwd 应该是 /Users/mcdowell/wb/projects/bar
  if echo "$sentinel_content" | grep -qE -- "--cwd [^ ]*Users/mcdowell/wb/projects/bar"; then
    echo "  ✅ Hub path /home/mcdowell/... → Mac path /Users/mcdowell/..."
    PASS=$((PASS+1))
  elif echo "$sentinel_content" | grep -qE -- "--cwd [^ ]*home/mcdowell/wb/projects/bar"; then
    echo "  ❌ Hub path leaked to Mac (no reverse mapping)"
    FAIL=$((FAIL+1))
  else
    echo "  ❌ unexpected cwd in args: $sentinel_content"
    FAIL=$((FAIL+1))
  fi
else
  echo "  ❌ sentinel missing"
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
