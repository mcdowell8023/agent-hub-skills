# Agent Hub Skills

Personal Agent Hub 的核心 skill 集合。提供跨设备 Agent 交接、浏览器工具链、模型调度、数据库连接等能力。

## Skills

| Skill | 用途 |
|---|---|
| [hub-handoff](hub-handoff/) | 跨设备 Agent 交接（push-to-hub / pull-from-hub / pull-from-mac / push-to-local） |
| [hub-comm](hub-comm/) | Mac ↔ Hub 双向 Paseo 通信参考 |
| [browser-preflight](browser-preflight/) | 浏览器工具链健康检查 + browser-harness/opencli 使用指南 |
| [smart-dispatch](smart-dispatch/) | 智能任务派发：任务类型分析 → 模型推荐 → Paseo 子会话 |
| [db-connect](db-connect/) | 数据库 CLI（MySQL + MongoDB），多环境切换，权限控制 |

## 安装

```bash
git clone https://github.com/mcdowell8023/agent-hub-skills.git

# 软链到 Claude Code skills 目录
for skill in hub-handoff hub-comm browser-preflight smart-dispatch db-connect; do
  ln -sfn "$(pwd)/agent-hub-skills/$skill" ~/.claude/skills/$skill
done
```

## 测试

```bash
bash hub-handoff/scripts/tests/test-harvest-return.sh   # 11 tests
bash hub-handoff/scripts/tests/test-push.sh             # 13 tests
bash db-connect/scripts/tests/test-db.sh                # 23 tests
```

## 配置

- `db-connect/databases.json` — 从 `.example` 复制，填入真实连接信息（不提交）
- `smart-dispatch/model-profiles.json` — 模型基准测试数据
