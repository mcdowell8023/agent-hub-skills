#!/usr/bin/env bash
# skill-path.sh — 在各 agent 的 skills 目录里定位某个 skill 的 SKILL.md 正文路径。
#
# 用法:
#   skill-path.sh <skill 名>          # 打印正文绝对路径（找不到则退出码 1）
#   skill-path.sh <skill 名> --cat    # 直接打印正文
#   skill-path.sh --list              # 列出所有可定位的 skill（名 + 路径）
set -uo pipefail

DIRS=(
  "$HOME/.claude/skills"
  "$HOME/.minimax/skills"
  "$HOME/.agents/skills"
  "$HOME/.codex/skills"
  "$HOME/.codebuddy/skills"
)

list_all() {
  for d in "${DIRS[@]}"; do
    [ -d "$d" ] || continue
    for f in "$d"/*/SKILL.md; do
      [ -f "$f" ] || continue
      printf '%-42s %s\n' "$(basename "$(dirname "$f")")" "$f"
    done
  done | sort -u
}

if [ $# -eq 0 ]; then
  sed -n '2,12p' "$0"
  exit 0
fi

if [ "$1" = "--list" ]; then
  list_all
  exit 0
fi

NAME="$1"; shift || true
WANT_CAT=0
[ "${1:-}" = "--cat" ] && WANT_CAT=1

FOUND=""
for d in "${DIRS[@]}"; do
  [ -d "$d" ] || continue
  if [ -f "$d/$NAME/SKILL.md" ]; then
    FOUND="$d/$NAME/SKILL.md"
    break
  fi
done

# 兜底：目录名与 skill 名不一致时，按 frontmatter 的 name 找
if [ -z "$FOUND" ]; then
  for d in "${DIRS[@]}"; do
    [ -d "$d" ] || continue
    for f in "$d"/*/SKILL.md; do
      [ -f "$f" ] || continue
      if grep -qE "^name:[[:space:]]*['\"]?${NAME}['\"]?[[:space:]]*$" "$f" 2>/dev/null; then
        FOUND="$f"
        break 2
      fi
    done
  done
fi

if [ -z "$FOUND" ]; then
  echo "skill-path: 找不到 '$NAME'（查过: ${DIRS[*]}）" >&2
  exit 1
fi

if [ "$WANT_CAT" = 1 ]; then
  cat "$FOUND"
else
  echo "$FOUND"
fi
