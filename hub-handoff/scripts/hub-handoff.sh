#!/bin/bash
# hub-handoff.sh — Hub 交接自动化脚本
# 用法: hub-handoff.sh <subcommand> [args]
# 子命令:
#   check-ssh          — 检查 Hub SSH 连通性
#   check-dir <path>   — 检查 Hub 上目录是否存在
#   map-path <mac-path> — Mac 路径映射到 Hub 路径
#   check-git <mac-cwd> — 检查 Mac 项目的 git 信息
#   ensure-repo <hub-cwd> <remote-url> <branch> — Hub 上确保仓库存在并在正确分支
#   sync-workspace <mac-ws> <hub-ws> — 同步 workspace 配置（memory/rules/docs）
#   list-hub-agents [cwd] — 列出 Hub 上的 Paseo agents
#   create-hub-agent <cwd> <provider> <model> <mode> <title> <prompt> — 创建 Hub agent

set -uo pipefail
HUB_HOST="hub"
HUB_PASEO="100.65.188.103:6767"
CREDENTIALS_FILE="$HOME/wb/.ai/rules/credentials.md"

cmd="${1:-help}"
shift 2>/dev/null || true

case "$cmd" in

check-ssh)
  if ssh -o ConnectTimeout=5 "$HUB_HOST" "echo ok" >/dev/null 2>&1; then
    echo "OK"
  else
    echo "FAIL: Hub SSH 不通，检查 Tailscale"
    exit 1
  fi
  ;;

map-path)
  mac_path="$1"
  echo "$mac_path" | sed 's|/Users/mcdowell|/home/mcdowell|'
  ;;

check-dir)
  hub_path="$1"
  if ssh -o ConnectTimeout=5 "$HUB_HOST" "test -d '$hub_path'" 2>/dev/null; then
    echo "EXISTS"
  else
    echo "NOT_EXISTS"
  fi
  ;;

check-git)
  mac_cwd="$1"
  if [ -d "$mac_cwd/.git" ]; then
    cd "$mac_cwd"
    remote=$(git remote get-url origin 2>/dev/null || echo "")
    branch=$(git branch --show-current 2>/dev/null || echo "")
    dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    echo "HAS_GIT=true"
    echo "REMOTE=$remote"
    echo "BRANCH=$branch"
    echo "DIRTY_FILES=$dirty"
  else
    echo "HAS_GIT=false"
  fi
  ;;

ensure-repo)
  hub_cwd="$1"
  remote_url="$2"
  branch="$3"
  hub_parent=$(dirname "$hub_cwd")
  repo_name=$(basename "$hub_cwd")

  # 检查 Hub git 凭据
  has_cred=$(ssh -o ConnectTimeout=5 "$HUB_HOST" "test -f ~/.git-credentials && echo yes || echo no" 2>/dev/null)
  if [ "$has_cred" = "no" ]; then
    # 从 credentials.md 提取 GitLab token
    if [ -f "$CREDENTIALS_FILE" ]; then
      token=$(grep -A5 "GitLab" "$CREDENTIALS_FILE" | grep "PAT" | grep -oE 'glpat-[a-zA-Z0-9._-]+' | head -1)
      if [ -n "$token" ]; then
        host=$(echo "$remote_url" | sed -E 's|https?://([^/]+).*|\1|')
        user=$(grep -A5 "GitLab" "$CREDENTIALS_FILE" | grep "账号" | awk -F'|' '{print $3}' | tr -d ' ' | head -1)
        ssh "$HUB_HOST" "git config --global credential.helper store && echo 'https://${user}:${token}@${host}' > ~/.git-credentials && chmod 600 ~/.git-credentials" 2>/dev/null
        echo "GIT_CRED=configured"
      else
        echo "GIT_CRED=no_token"
        exit 1
      fi
    else
      echo "GIT_CRED=no_credentials_file"
      exit 1
    fi
  fi

  # clone 或 fetch
  dir_exists=$(ssh "$HUB_HOST" "test -d '$hub_cwd/.git' && echo yes || echo no" 2>/dev/null)
  if [ "$dir_exists" = "yes" ]; then
    ssh "$HUB_HOST" "cd '$hub_cwd' && git fetch origin && git checkout '$branch' 2>/dev/null || git checkout -b '$branch' origin/'$branch'" 2>&1 | tail -3
    echo "REPO=fetched"
  else
    ssh "$HUB_HOST" "mkdir -p '$hub_parent' && cd '$hub_parent' && git clone '$remote_url' '$repo_name'" 2>&1 | tail -3
    if [ -n "$branch" ] && [ "$branch" != "master" ] && [ "$branch" != "main" ]; then
      ssh "$HUB_HOST" "cd '$hub_cwd' && git checkout '$branch' 2>/dev/null || git checkout -b '$branch' origin/'$branch'" 2>&1 | tail -2
    fi
    echo "REPO=cloned"
  fi
  ;;

sync-workspace)
  mac_ws="$1"
  hub_ws="$2"
  ssh "$HUB_HOST" "mkdir -p '$hub_ws'" 2>/dev/null

  # 同步 memory
  if [ -d "$mac_ws/memory" ]; then
    rsync -az "$mac_ws/memory/" "$HUB_HOST:$hub_ws/memory/" 2>/dev/null
    echo "MEMORY=synced"
  fi

  # 同步规则
  for f in CLAUDE.md AGENTS.md; do
    [ -f "$mac_ws/$f" ] && scp -q "$mac_ws/$f" "$HUB_HOST:$hub_ws/$f" 2>/dev/null
  done
  if [ -d "$mac_ws/.ai/rules" ]; then
    rsync -az "$mac_ws/.ai/" "$HUB_HOST:$hub_ws/.ai/" 2>/dev/null
    echo "RULES=synced"
  fi

  # 同步 docs
  if [ -d "$mac_ws/docs" ]; then
    rsync -az "$mac_ws/docs/" "$HUB_HOST:$hub_ws/docs/" 2>/dev/null
    echo "DOCS=synced"
  fi
  echo "WORKSPACE=synced"
  ;;

list-hub-agents)
  cwd_filter="${1:-}"
  result=$(paseo agent ls --host "$HUB_PASEO" --json 2>&1 | grep -v "FATAL\|ERROR\|GPU\|helper app\|crashed\|terminated")
  if [ -n "$cwd_filter" ]; then
    echo "$result" | python3 -c "
import sys,json
try:
    agents = json.load(sys.stdin)
    for a in agents:
        if '$cwd_filter' in a.get('cwd',''):
            print(f\"{a['id'][:8]}  {a['status']:10}  {a.get('title','')}  ({a['cwd']})\")
except:
    pass
" 2>/dev/null
  else
    echo "$result" | python3 -c "
import sys,json
try:
    agents = json.load(sys.stdin)
    for a in agents:
        print(f\"{a['id'][:8]}  {a['status']:10}  {a.get('title','')}  ({a['cwd']})\")
except:
    pass
" 2>/dev/null
  fi
  ;;

create-hub-agent)
  hub_cwd="$1"
  provider="$2"
  model="$3"
  mode="$4"
  title="$5"
  prompt="$6"
  # 优先 Paseo --host 直连（v0.1.89+ 已验证）
  result=$(paseo run --host "$HUB_PASEO" --detach --cwd "$hub_cwd" --provider "$provider/$model" --mode "$mode" --title "$title" "$prompt" 2>&1 | grep -vE "FATAL|ERROR|GPU|helper|crashed|terminated|Network|content/")
  if echo "$result" | grep -q "AGENT ID\|created"; then
    echo "$result"
  else
    # 兜底：scp prompt 文件 + SSH（处理中文转义）
    local prompt_file="/tmp/hub-handoff-prompt-$$.txt"
    echo "$prompt" > "$prompt_file"
    scp -q "$prompt_file" "$HUB_HOST:/tmp/hub-handoff-prompt.txt" 2>/dev/null
    ssh -o ConnectTimeout=10 "$HUB_HOST" "paseo run --detach --cwd '$hub_cwd' --provider '$provider/$model' --mode '$mode' --title '$title' \"\$(cat /tmp/hub-handoff-prompt.txt)\"" 2>&1
    rm -f "$prompt_file"
  fi
  ;;

verify-paths)
  # 检查 prompt 中引用的所有路径在 Hub 上是否存在
  # 用法: hub-handoff.sh verify-paths <path1> <path2> ...
  echo "=== 路径验证（Hub 端）==="
  all_ok=true
  for p in "$@"; do
    hub_p=$(echo "$p" | sed 's|/Users/mcdowell|/home/mcdowell|')
    if ssh -o ConnectTimeout=5 "$HUB_HOST" "test -e '$hub_p'" 2>/dev/null; then
      echo "  ✅ $hub_p"
    else
      echo "  ❌ $hub_p (NOT FOUND)"
      all_ok=false
    fi
  done
  $all_ok && echo "ALL_PATHS_OK" || echo "PATHS_MISSING"
  ;;

sync-memory)
  # 同步 Claude Code project memory 到 Hub
  # Claude Code memory 路径是 CWD 编码的：~/.claude/projects/-Users-mcdowell-xxx/memory/
  # Hub 上对应：~/.claude/projects/-home-mcdowell-xxx/memory/
  mac_cwd_slug="$1"  # e.g., -Users-mcdowell-AgentWorkspace
  hub_cwd_slug=$(echo "$mac_cwd_slug" | sed 's|-Users-mcdowell|-home-mcdowell|')
  mac_memory_dir="$HOME/.claude/projects/$mac_cwd_slug/memory"
  hub_memory_dir="/home/mcdowell/.claude/projects/$hub_cwd_slug/memory"

  if [ -d "$mac_memory_dir" ]; then
    ssh "$HUB_HOST" "mkdir -p '$hub_memory_dir'" 2>/dev/null
    rsync -az "$mac_memory_dir/" "$HUB_HOST:$hub_memory_dir/" 2>/dev/null
    count=$(find "$mac_memory_dir" -type f | wc -l | tr -d ' ')
    echo "MEMORY_SYNCED=$count files → $hub_memory_dir"
  else
    echo "MEMORY_NOT_FOUND=$mac_memory_dir"
  fi

  # 也同步 workspace 级别的 memory
  mac_ws_memory="$2"  # e.g., ~/AgentWorkspace/memory
  if [ -n "$mac_ws_memory" ] && [ -d "$mac_ws_memory" ]; then
    hub_ws_memory=$(echo "$mac_ws_memory" | sed 's|/Users/mcdowell|/home/mcdowell|')
    rsync -az "$mac_ws_memory/" "$HUB_HOST:$hub_ws_memory/" 2>/dev/null
    echo "WS_MEMORY_SYNCED=$hub_ws_memory"
  fi
  ;;

verify-state)
  # 在 Hub 上验证实际状态，输出结构化报告
  # 用法: hub-handoff.sh verify-state <hub-cwd>
  hub_cwd="$1"
  echo "=== Hub 状态事实核查 ==="

  # Git 状态
  ssh -o ConnectTimeout=5 "$HUB_HOST" "
    if [ -d '$hub_cwd/.git' ]; then
      cd '$hub_cwd'
      echo 'GIT=true'
      echo \"BRANCH=\$(git branch --show-current)\"
      echo \"HEAD=\$(git log --oneline -1)\"
      echo \"DIRTY=\$(git status --porcelain | wc -l | tr -d ' ')\"
      echo \"UNCOMMITTED_FILES=\$(git status --porcelain | head -10)\"
    else
      echo 'GIT=false'
      echo 'REPO_MISSING=$hub_cwd'
    fi
  " 2>/dev/null

  # 版本文件
  ssh "$HUB_HOST" "
    [ -f ~/.agent-gates/.version ] && echo \"AGENT_GATES_VERSION=\$(cat ~/.agent-gates/.version)\" || echo 'AGENT_GATES_VERSION=not_installed'
    echo \"NODE=\$(node --version 2>/dev/null || echo missing)\"
    echo \"PYTHON=\$(python3 --version 2>/dev/null || echo missing)\"
  " 2>/dev/null

  # Memory 文件
  ssh "$HUB_HOST" "
    echo '=== Hub Memory Files ==='
    find /home/mcdowell/AgentWorkspace/memory -name '*.md' -type f 2>/dev/null | while read f; do
      echo \"  \$f (\$(stat -c '%Y' \"\$f\" 2>/dev/null || stat -f '%m' \"\$f\" 2>/dev/null))\"
    done
    find /home/mcdowell/wb/memory -name '*.md' -type f 2>/dev/null | while read f; do
      echo \"  \$f (\$(stat -c '%Y' \"\$f\" 2>/dev/null || stat -f '%m' \"\$f\" 2>/dev/null))\"
    done
  " 2>/dev/null
  ;;

precheck)
  # 一键全检：SSH + 路径 + Git + Memory + 状态
  # 用法: hub-handoff.sh precheck <mac-cwd> [paths...]
  mac_cwd="$1"
  shift
  hub_cwd=$(echo "$mac_cwd" | sed 's|/Users/mcdowell|/home/mcdowell|')

  echo "========== Hub Handoff Precheck =========="

  # 1. SSH
  echo "--- SSH ---"
  if ssh -o ConnectTimeout=5 "$HUB_HOST" "echo ok" >/dev/null 2>&1; then
    echo "  ✅ SSH OK"
  else
    echo "  ❌ SSH FAIL"
    exit 1
  fi

  # 2. 目标目录
  echo "--- Target Directory ---"
  if ssh "$HUB_HOST" "test -d '$hub_cwd'" 2>/dev/null; then
    echo "  ✅ $hub_cwd exists"
  else
    echo "  ❌ $hub_cwd NOT FOUND"
  fi

  # 3. Git
  echo "--- Git ---"
  if [ -d "$mac_cwd/.git" ]; then
    cd "$mac_cwd"
    mac_remote=$(git remote get-url origin 2>/dev/null || echo "")
    mac_branch=$(git branch --show-current 2>/dev/null || echo "")
    mac_head=$(git log --oneline -1 2>/dev/null || echo "")
    echo "  Mac: branch=$mac_branch head=$mac_head"

    hub_git=$(ssh "$HUB_HOST" "
      if [ -d '$hub_cwd/.git' ]; then
        cd '$hub_cwd'
        echo \"branch=\$(git branch --show-current) head=\$(git log --oneline -1)\"
      else
        echo 'REPO_MISSING'
      fi
    " 2>/dev/null)
    echo "  Hub: $hub_git"

    if echo "$hub_git" | grep -q "REPO_MISSING"; then
      echo "  ⚠️ Hub 上仓库不存在，需要 clone（remote: $mac_remote）"
    fi

    mac_dirty=$(git status --porcelain | wc -l | tr -d ' ')
    if [ "$mac_dirty" -gt 0 ]; then
      echo "  ⚠️ Mac 有 $mac_dirty 个未提交文件"
    fi
  else
    echo "  （非 Git 项目）"
  fi

  # 4. Memory
  echo "--- Memory ---"
  mac_cwd_slug=$(echo "$mac_cwd" | sed 's|^/||;s|/|-|g')
  mac_memory="$HOME/.claude/projects/$mac_cwd_slug/memory"
  hub_cwd_slug=$(echo "$mac_cwd_slug" | sed 's|Users-mcdowell|home-mcdowell|')
  hub_memory="/home/mcdowell/.claude/projects/$hub_cwd_slug/memory"

  if [ -d "$mac_memory" ]; then
    mac_count=$(find "$mac_memory" -type f | wc -l | tr -d ' ')
    hub_count=$(ssh "$HUB_HOST" "find '$hub_memory' -type f 2>/dev/null | wc -l | tr -d ' '" 2>/dev/null)
    echo "  Mac memory: $mac_count files"
    echo "  Hub memory: ${hub_count:-0} files"
    if [ "${hub_count:-0}" -lt "$mac_count" ]; then
      echo "  ⚠️ Hub memory 落后，需要同步"
    fi
  else
    echo "  Mac 无 project memory"
  fi

  # workspace memory
  ws_root=$(echo "$mac_cwd" | grep -oE '.*/wb|.*/AgentWorkspace' | head -1)
  if [ -d "$ws_root/memory" ]; then
    hub_ws_root=$(echo "$ws_root" | sed 's|/Users/mcdowell|/home/mcdowell|')
    echo "  WS memory: $ws_root/memory → $hub_ws_root/memory"
  fi

  # 5. 额外路径检查
  if [ $# -gt 0 ]; then
    echo "--- Extra Paths ---"
    for p in "$@"; do
      hub_p=$(echo "$p" | sed 's|/Users/mcdowell|/home/mcdowell|')
      if ssh "$HUB_HOST" "test -e '$hub_p'" 2>/dev/null; then
        echo "  ✅ $hub_p"
      else
        echo "  ❌ $hub_p MISSING"
      fi
    done
  fi

  echo "=========================================="
  ;;

help)
  echo "用法: hub-handoff.sh <子命令> [参数]"
  echo ""
  echo "子命令:"
  echo "  check-ssh                           检查 Hub SSH 连通性"
  echo "  map-path <mac-path>                 Mac 路径映射到 Hub 路径"
  echo "  check-dir <hub-path>                检查 Hub 上目录是否存在"
  echo "  check-git <mac-cwd>                 检查 Mac 项目的 git 信息"
  echo "  ensure-repo <hub-cwd> <url> <branch> Hub 上确保仓库存在"
  echo "  sync-workspace <mac-ws> <hub-ws>    同步 workspace 配置"
  echo "  sync-memory <cwd-slug> [ws-memory]  同步 Claude Code project memory"
  echo "  verify-paths <path1> [path2...]     验证路径在 Hub 上是否存在"
  echo "  verify-state <hub-cwd>              Hub 状态事实核查"
  echo "  precheck <mac-cwd> [extra-paths...] 一键全检（SSH+路径+Git+Memory+状态）"
  echo "  list-hub-agents [cwd]               列出 Hub 上的 Paseo agents"
  echo "  create-hub-agent <args...>          创建 Hub agent"
  ;;

*)
  echo "未知子命令: $cmd"
  exit 1
  ;;
esac
