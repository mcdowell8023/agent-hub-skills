#!/usr/bin/env bash
# cb-probe.sh — 兼容 shim，实际逻辑在 probe-models.sh（2026-09-17 起支持全 provider）
# ⚠️ 保留此名是因为 SKILL.md 与既有笔记都引用它；新用法请直接调 probe-models.sh。
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ $# -eq 0 ]; then exec bash "$DIR/probe-models.sh" codebuddy-code/hy3 \
     codebuddy-code/deepseek-v4.1-flash codebuddy-code/glm-5.3-flash; fi
if [ "$1" = "--all" ]; then shift; exec bash "$DIR/probe-models.sh" --all "$@"; fi
args=(); for m in "$@"; do args+=("codebuddy-code/$m"); done
exec bash "$DIR/probe-models.sh" "${args[@]}"
