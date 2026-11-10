#!/usr/bin/env bash
# install-links.sh — 把本仓库的 skill 软链到各 agent runtime 的 skills 目录。
#
# 用法:
#   install-links.sh            # 安装/更新全部 skill 的软链
#   install-links.sh --check    # 只体检：哪些条目不是软链（应为空的即正常）
#   install-links.sh --list     # 列出本仓库提供的 skill
#
# 与 README 里内联循环的差别：
#   * 遇到**实体目录**先改名备份（.bak.<时间戳>），绝不 rm -rf 真实内容
#   * 覆盖 ~/.minimax/skills（README 旧循环漏了这个目录，
#     漏装的表现就是「该 skill 在 MiniMax Code 里看不见」）
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIRS=(
  "$HOME/.claude/skills"
  "$HOME/.minimax/skills"
  "$HOME/.agents/skills"
  "$HOME/.codex/skills"
  "$HOME/.codebuddy/skills"
)

skills_list() {
  for s in "$REPO"/*/; do
    [ -d "$s" ] || continue
    n="$(basename "$s")"
    [ "$n" = ".git" ] && continue
    [ -f "$s/SKILL.md" ] && echo "$n"
  done
}

case "${1:-}" in
  --list)
    skills_list
    exit 0 ;;
  --check)
    bad=0
    for s in $(skills_list); do
      for d in "${DIRS[@]}"; do
        [ -d "$d" ] || continue
        t="$d/$s"
        if [ ! -e "$t" ]; then
          echo "❌ 未安装: $t"; bad=1
        elif [ ! -L "$t" ]; then
          echo "🔴 实体副本（应为软链）: $t"; bad=1
        fi
      done
    done
    [ "$bad" = 0 ] && echo "✅ 全部为软链"
    exit "$bad" ;;
esac

for d in "${DIRS[@]}"; do mkdir -p "$d"; done

for s in $(skills_list); do
  for d in "${DIRS[@]}"; do
    t="$d/$s"
    if [ -L "$t" ]; then
      : # 软链：ln -sfn 直接替换，**不要用 rm**（本机 rm 被 shim 成 mavis-trash，单次要好几秒）
    elif [ -d "$t" ]; then
      mv "$t" "$t.bak.$(date +%s)"
      echo "⚠️ 实体副本已备份: $t.bak.*"
    fi
    ln -sfn "$REPO/$s" "$t"
  done
  echo "installed: $s"
done

echo "--- 完成，体检： ---"
"$0" --check
