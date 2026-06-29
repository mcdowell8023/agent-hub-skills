#!/bin/bash
# hub-return.sh — 从远端拉取 agent 上下文并在本地创建续接 agent
# 用法: hub-return.sh <remote-host> <remote-cwd> [--provider <p>] [--model <m>] [--cwd <local-cwd>] [--mode <mode>] [--title <title>]
#
# 流程:
#   1. 调 hub-harvest.sh 采集远端上下文
#   2. 路径映射（remote Hub 路径 → local Mac 路径）
#   3. 组装交接 prompt
#   4. 本地 paseo run --detach 创建续接 agent
#
# 退出码：0=成功，1=失败

set -uo pipefail

SSH_CMD="${SSH_CMD:-ssh}"
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
HARVEST_SH="$SCRIPTS_DIR/hub-harvest.sh"
HUB_HANDOFF_SH="$SCRIPTS_DIR/hub-handoff.sh"

# 默认值
PROVIDER="claude"
MODEL="opus"
MODE="auto"
TITLE="Hub Return Task"
LOCAL_CWD="$PWD"

usage() {
  cat <<'EOF'
用法: hub-return.sh <remote-host> <remote-cwd> [选项]

位置参数:
  remote-host    远端主机（SSH 别名或 IP）
  remote-cwd     远端工作目录（Hub 端绝对路径）

选项:
  --provider <p>   Provider（默认: claude）
  --model <m>      Model（默认: opus）
  --cwd <path>     本地目标 cwd（默认: 当前目录；自动从 remote-cwd 映射）
  --mode <m>       Paseo mode（默认: auto）
  --title <t>      Agent 标题（默认: Hub Return Task）
  -h, --help       显示本帮助

示例:
  hub-return.sh hub /home/mcdowell/wb
  hub-return.sh 100.65.188.103 /home/mcdowell/wb --provider codebuddy-code --model deepseek-v4-pro

输出：本地 agent ID
EOF
}

# ---------- 参数解析 ----------

if [ $# -lt 2 ]; then
  usage
  exit 1
fi

REMOTE_HOST="$1"
REMOTE_CWD="$2"
shift 2

while [ $# -gt 0 ]; do
  case "$1" in
    --provider) PROVIDER="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --cwd) LOCAL_CWD="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --title) TITLE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage; exit 1 ;;
  esac
done

# ---------- 路径映射（Hub → Mac）----------

# 反向 map-path：/home/mcdowell → /Users/mcdowell
map_path_to_local() {
  echo "$1" | sed 's|/home/mcdowell|/Users/mcdowell|'
}

# 如果用户没显式指定 --cwd，从 remote-cwd 反向映射
if [ "$LOCAL_CWD" = "$PWD" ]; then
  LOCAL_CWD=$(map_path_to_local "$REMOTE_CWD")
fi

# ---------- Step 1: 采集远端上下文 ----------

echo "→ 采集远端上下文: $REMOTE_HOST:$REMOTE_CWD" >&2

# 复用 hub-harvest.sh，注入 SSH_CMD 便于测试
HARVEST_OUTPUT=$(SSH_CMD="$SSH_CMD" bash "$HARVEST_SH" "$REMOTE_HOST" "$REMOTE_CWD" 2>&1)
harvest_exit=$?

if [ "$harvest_exit" -ne 0 ]; then
  echo "错误: 远端采集失败" >&2
  echo "$HARVEST_OUTPUT" >&2
  exit 1
fi

# ---------- Step 2: 路径映射（已对 cwd 处理，正文里所有 /home/mcdowell → /Users/mcdowell）----------

HARVEST_MAPPED=$(echo "$HARVEST_OUTPUT" | sed 's|/home/mcdowell|/Users/mcdowell|g')

# ---------- Step 3: 组装交接 prompt ----------

PROMPT=$(cat <<EOF
# Hub 上下文续接

从远端主机 $REMOTE_HOST 拉取的 agent 工作上下文摘要：

$HARVEST_MAPPED

---

## 本地续接任务

1. 阅读上面的 Hub 上下文报告，了解远端 agent 完成了什么、卡在哪里
2. 在本地 cwd \`$LOCAL_CWD\` 继续工作
3. 如果需要从 Hub 拉取额外产物（git pull、rsync memory、scp build），执行后开始

## 关键信息

- 远端主机: ${REMOTE_HOST}
- 远端 cwd: ${REMOTE_CWD}（本地对应: ${LOCAL_CWD}）
- Provider/Model: ${PROVIDER}/${MODEL}
- 模式: ${MODE}

## 重要路径映射

所有 \`/home/mcdowell/...\` 已映射为 \`/Users/mcdowell/...\`，报告里直接用 Mac 路径即可。
EOF
)

# ---------- Step 4: 本地创建续接 agent ----------

echo "→ 在本地创建续接 agent: $PROVIDER/$MODEL @ $LOCAL_CWD" >&2

# 写 prompt 到临时文件，避免命令行参数转义问题
PROMPT_FILE="/tmp/hub-return-prompt-$$.txt"
echo "$PROMPT" > "$PROMPT_FILE"

# 优先用 --prompt-file（如果 paseo 支持），否则命令行传
RESULT=$(paseo run --detach \
  --cwd "$LOCAL_CWD" \
  --provider "$PROVIDER/$MODEL" \
  --mode "$MODE" \
  --title "$TITLE" \
  --prompt-file "$PROMPT_FILE" 2>&1) || RESULT=$(paseo run --detach \
  --cwd "$LOCAL_CWD" \
  --provider "$PROVIDER/$MODEL" \
  --mode "$MODE" \
  --title "$TITLE" \
  "\$(cat $PROMPT_FILE)" 2>&1)

rm -f "$PROMPT_FILE"

if echo "$RESULT" | grep -qiE "AGENT ID|created|agent-id|agent_id"; then
  echo "$RESULT" | grep -iE "AGENT ID|created|agent-id|agent_id" | head -3
  echo "✓ 本地续接 agent 已创建" >&2
  exit 0
else
  echo "错误: 本地 agent 创建失败" >&2
  echo "$RESULT" >&2
  exit 1
fi
