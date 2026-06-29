#!/bin/bash
# hub-harvest.sh — 从远端设备采集 agent 工作上下文
# 用法: hub-harvest.sh <remote-host> <remote-cwd> [--agent-id <id>]
#
# 输出：Markdown 格式的 harvest 报告到 stdout
# 退出码：0=成功，1=失败（参数错或 SSH 不通）
#
# 可测试性：所有 SSH 调用通过 ${SSH_CMD:-ssh} 注入，便于 mock。

set -uo pipefail

SSH_CMD="${SSH_CMD:-ssh}"
CONNECT_TIMEOUT=5

usage() {
  cat <<'EOF'
用法: hub-harvest.sh <remote-host> <remote-cwd> [--agent-id <id>]

参数:
  remote-host    远端主机（SSH 别名或 IP）
  remote-cwd     远端工作目录（绝对路径）
  --agent-id <id>  可选，指定要采集的 agent ID

示例:
  hub-harvest.sh hub /home/mcdowell/wb
  hub-harvest.sh 100.65.188.103 /home/mcdowell/wb --agent-id 7c47561

输出：Markdown 格式 harvest 报告到 stdout
EOF
}

# ---------- 参数校验 ----------

if [ $# -lt 2 ]; then
  usage
  exit 1
fi

REMOTE_HOST="$1"
REMOTE_CWD="$2"
shift 2

AGENT_ID=""
while [ $# -gt 0 ]; do
  case "$1" in
    --agent-id) AGENT_ID="$2"; shift 2 ;;
    --agent-id=*) AGENT_ID="${1#*=}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage; exit 1 ;;
  esac
done

# ---------- SSH 连通性检查 ----------

if ! $SSH_CMD -o ConnectTimeout=$CONNECT_TIMEOUT "$REMOTE_HOST" "echo ok" >/dev/null 2>&1; then
  echo "错误: SSH 连接到 $REMOTE_HOST 不通，请检查网络/SSH 配置" >&2
  exit 1
fi

# ---------- 远程采集（单一 SSH 会话减少开销）----------

# 通过 heredoc 一次 SSH 调用采集多项数据，字段以 KEY=VALUE 输出便于解析
RAW=$($SSH_CMD -o ConnectTimeout=$CONNECT_TIMEOUT "$REMOTE_HOST" bash -s -- "$REMOTE_CWD" "$AGENT_ID" <<'REMOTE_EOF' 2>/dev/null
set +e
CWD="$1"
AGENT_ID="$2"

echo "===PASEO_AGENTS==="
if [ -n "$AGENT_ID" ]; then
  echo "[{\"id\":\"$AGENT_ID\",\"status\":\"unknown\",\"provider\":\"unknown\",\"cwd\":\"$CWD\",\"title\":\"$AGENT_ID\"}]"
else
  # 真实场景：paseo agent ls --json
  # 失败兜底：返回空数组
  which paseo >/dev/null 2>&1 && paseo agent ls --json 2>/dev/null || echo "[]"
fi

echo "===GIT==="
if [ -d "$CWD/.git" ]; then
  cd "$CWD" 2>/dev/null
  echo "BRANCH=$(git branch --show-current 2>/dev/null)"
  echo "REMOTE=$(git remote get-url origin 2>/dev/null)"
  echo "HEAD=$(git log --oneline -1 2>/dev/null)"
  echo "DIRTY=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  echo "AHEAD=$(git log --oneline origin/HEAD..HEAD 2>/dev/null | head -20)"
  echo "WORKTREES=$(git worktree list 2>/dev/null | wc -l | tr -d ' ')"
else
  echo "HAS_GIT=false"
fi

echo "===MEMORY==="
find /home/mcdowell/AgentWorkspace/memory -name '*.md' -type f 2>/dev/null | head -20
find /home/mcdowell/wb/memory -name '*.md' -type f 2>/dev/null | head -20

echo "===DOCS==="
PARENT_WS=$(echo "$CWD" | grep -oE '/home/mcdowell/(wb|AgentWorkspace)' | head -1)
if [ -n "$PARENT_WS" ] && [ -d "$PARENT_WS/docs" ]; then
  find "$PARENT_WS/docs" -name '*.md' -type f -newer /tmp/.hub-harvest-baseline 2>/dev/null | head -10
  # 兜底：如果 -newer 失败（基准文件不存在），列全部
  find "$PARENT_WS/docs" -name '*.md' -type f 2>/dev/null | head -10
fi

echo "===BUILD==="
for d in "$CWD/dist" "$CWD/build" "$CWD/android/app/build/outputs/apk/debug" "$CWD/.next"; do
  if [ -d "$d" ]; then
    find "$d" -type f -name '*.apk' -o -name '*.ipa' -o -name '*.exe' 2>/dev/null | head -5
  fi
done

echo "===RUNTIMES==="
echo "NODE=$(node --version 2>/dev/null || echo missing)"
echo "PYTHON=$(python3 --version 2>/dev/null || echo missing)"

echo "===DEPS==="
for f in "$CWD/package.json" "$CWD/Cargo.toml" "$CWD/go.mod" "$CWD/pom.xml"; do
  if [ -f "$f" ]; then
    echo "FILE=$f"
    echo "MTIME=$(stat -c '%Y' "$f" 2>/dev/null || stat -f '%m' "$f" 2>/dev/null)"
  fi
done
REMOTE_EOF
)

if [ -z "$RAW" ]; then
  echo "错误: 远端采集无返回，请检查远端环境" >&2
  exit 1
fi

# ---------- 解析原始数据 ----------

section() {
  awk -v marker="===$1===" '
    $0 == marker { flag=1; next }
    /^===/ { flag=0 }
    flag { print }
  '
}

AGENTS_JSON=$(echo "$RAW" | section PASEO_AGENTS)
GIT_BLOCK=$(echo "$RAW" | section GIT)
MEMORY_FILES=$(echo "$RAW" | section MEMORY)
DOCS_FILES=$(echo "$RAW" | section DOCS)
BUILD_FILES=$(echo "$RAW" | section BUILD)
RUNTIMES=$(echo "$RAW" | section RUNTIMES)
DEPS=$(echo "$RAW" | section DEPS)

# ---------- 生成 Markdown 报告 ----------

PROJECT_NAME=$(basename "$REMOTE_CWD")
GENERATED=$(date '+%Y-%m-%d %H:%M')

cat <<EOF
# Hub Harvest Report — $PROJECT_NAME
Generated: $GENERATED

## Source
- Host: $REMOTE_HOST
- CWD: $REMOTE_CWD
- Agent ID Filter: ${AGENT_ID:-<all>}

## Agent
EOF

# Agent 列表
if [ -n "$AGENTS_JSON" ] && [ "$AGENTS_JSON" != "[]" ]; then
  echo "$AGENTS_JSON" | python3 -c "
import sys, json
try:
    agents = json.load(sys.stdin)
    if not isinstance(agents, list):
        agents = []
    for a in agents:
        aid = a.get('id', '?')[:8]
        st = a.get('status', '?')
        prov = a.get('provider', '?')
        cwd = a.get('cwd', '?')
        title = a.get('title', '')
        print(f'- ID: {aid} | Status: {st} | Provider: {prov}')
        print(f'  - Title: {title}')
        print(f'  - CWD: {cwd}')
except Exception as e:
    print(f'- (parse error: {e})')
" 2>/dev/null || echo "- (no agent info available)"
else
  echo "- (no agents found)"
fi

cat <<'EOF'

## Git
EOF

if echo "$GIT_BLOCK" | grep -q "HAS_GIT=false"; then
  echo "- (not a git repository)"
elif [ -z "$GIT_BLOCK" ]; then
  echo "- (no git info)"
else
  branch=$(echo "$GIT_BLOCK" | grep '^BRANCH=' | head -1 | cut -d= -f2-)
  remote=$(echo "$GIT_BLOCK" | grep '^REMOTE=' | head -1 | cut -d= -f2-)
  head=$(echo "$GIT_BLOCK" | grep '^HEAD=' | head -1 | cut -d= -f2-)
  dirty=$(echo "$GIT_BLOCK" | grep '^DIRTY=' | head -1 | cut -d= -f2-)
  worktrees=$(echo "$GIT_BLOCK" | grep '^WORKTREES=' | head -1 | cut -d= -f2-)
  ahead=$(echo "$GIT_BLOCK" | sed -n '/^AHEAD=/,/^[A-Z]/p' | sed '1d;/^[A-Z]/d' | head -10)

  echo "- Branch: ${branch:-unknown}"
  echo "- Remote: ${remote:-none}"
  echo "- HEAD: ${head:-unknown}"
  echo "- Uncommitted files: ${dirty:-0}"
  echo "- Worktrees: ${worktrees:-0}"
  if [ -n "$ahead" ]; then
    echo "- Ahead commits:"
    echo "$ahead" | sed 's/^/  - /'
  fi
fi

cat <<'EOF'

## Memory
EOF

if [ -z "$MEMORY_FILES" ]; then
  echo "- (no memory files found)"
else
  echo "$MEMORY_FILES" | head -20 | sed 's/^/- /'
  total=$(echo "$MEMORY_FILES" | wc -l | tr -d ' ')
  if [ "$total" -gt 20 ]; then
    echo "- ... and $((total-20)) more"
  fi
fi

cat <<'EOF'

## Documents
EOF

if [ -z "$DOCS_FILES" ]; then
  echo "- (no docs found)"
else
  echo "$DOCS_FILES" | head -10 | sed 's/^/- /'
fi

cat <<'EOF'

## Build
EOF

if [ -z "$BUILD_FILES" ]; then
  echo "- (no build artifacts found)"
else
  echo "$BUILD_FILES" | head -5 | sed 's/^/- /'
fi

cat <<'EOF'

## Runtimes
EOF

echo "$RUNTIMES" | sed 's/^/- /'

cat <<'EOF'

## Dependencies
EOF

if [ -z "$DEPS" ]; then
  echo "- (no dependency files found)"
else
  echo "$DEPS" | sed 's/^/- /'
fi

cat <<'EOF'

---
Report generated by hub-harvest.sh
EOF
