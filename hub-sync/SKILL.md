---
name: hub-sync
description: "Sync Mac agent configuration (rules, MCP, OMC/OMO/OMX) from dotfiles repo. Triggers: 'sync config', 'sync dotfiles', '拉取配置', 'pull dotfiles', 'hub-sync'."
user-invocable: true
argument-hint: "[--from <local|hub>]"
---

# hub-sync

同步 Mac 的 agent 配置（CLAUDE.md、规则模块、MCP 配置、OMC/OMO/OMX）到本机。

**与旧版 `dotfiles-sync` 区别**：本 skill 只管**配置同步**，**不再管 skill 同步**。Skill 维护已迁出 dotfiles 仓，参见 `~/Projects/agent-hub-skills/`。

## 触发词

"同步配置"、"sync config"、"sync dotfiles"、"拉取配置"、"pull dotfiles"、"hub-sync"

## 操作

```bash
cd ~/Projects/dotfiles && git pull 2>/dev/null; ./scripts/apply.sh
```

## 说明

- dotfiles 仓库由 Mac 端 fswatch 自动推送（手动 push，不在自动循环内）
- 本 skill 用于本机或 Hub agent 手动触发拉取
- apply.sh 会先备份当前配置到 `~/.dotfiles-backup/` 再覆盖
- apply.sh 还会**重建自建 skill 软链**（agent-hub-skills → cc-switch → 三个 agent 库）
- 如果 git pull 失败（无 remote），直接执行 apply.sh 用本地最新版本
- **不再**同步 skill 内容（claude-skills/、agents-skills/、opencode/skills/ 已在 dotfiles 仓删除）
