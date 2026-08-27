# Agent Hub Skills

Personal Agent Hub 的核心 skill 集合。提供跨设备 Agent 交接、浏览器工具链、任务派发、质量验收、数据库连接等能力。

## Skills

| Skill | 用途 |
|---|---|
| [hub-handoff](hub-handoff/) | 跨设备 Agent 交接（push-to-hub / pull-from-hub / pull-from-mac / push-to-local） |
| [hub-comm](hub-comm/) | Mac ↔ Hub 双向 Paseo 通信参考 |
| [browser-preflight](browser-preflight/) | 浏览器工具链健康检查 + browser-harness/opencli 使用指南 |
| [db-connect](db-connect/) | 数据库 CLI（MySQL + MongoDB），多环境切换，权限控制 |

### 🔗 rift 家族（任务派发与质量）

| Skill | 用途 |
|---|---|
| [rift-dispatch](rift-dispatch/) | 智能任务派发：任务分类 → 选模型 → 选通道（Paseo 子会话 / `pi -p` CLI）<br>⚠️ 原 `smart-dispatch`，2026-08-27 更名，git 历史保留 |
| [rift-free](rift-free/) | 免费通道派发（OpenRouter / 智谱 / 讯飞） |
| [rift-integration-qa](rift-integration-qa/) | QA 统一入口：TDD · 三层一致(DB↔API↔FE) · 契约验证 · 假绿检测 · 真机回归 · 部署后验证 · 视觉验证<br>⚠️ 原 `integration-qa`，2026-08-27 更名 |


## 安装 —— 🔴 软链到本仓库，不要 cp

**本仓库是唯一源。** 各 agent 的 skills 目录全部软链过来，改一处五处生效，
且改动立刻出现在 `git status` 里，不会漏提交。

```bash
git clone https://github.com/mcdowell8023/agent-hub-skills.git \
  ~/AgentWorkspace/projects/skills/agent-hub-skills

REPO=~/AgentWorkspace/projects/skills/agent-hub-skills
for s in hub-handoff hub-comm browser-preflight db-connect \
         rift-dispatch rift-free rift-integration-qa; do
  for d in ~/.claude/skills ~/.agents/skills ~/.config/opencode/skills ~/.codebuddy/skills; do
    [ -d "$d" ] || continue
    rm -rf "$d/$s"
    ln -sfn "$REPO/$s" "$d/$s"
  done
done
```

⛔ **不要用 `cp` 分发。** 2026-08-27 之前就是手工 cp 三份实体，结果本仓库落后本地
**近两个月**（`hub-comm` / `hub-handoff` 的 SKILL.md 在 git 里连 frontmatter 都没有，
`db_engine.py` 少 117 行）。改哪份、哪份生效、哪份是最新，全靠记忆。

### 一致性自查

```bash
REPO=~/AgentWorkspace/projects/skills/agent-hub-skills
for d in ~/.claude/skills ~/.agents/skills ~/.config/opencode/skills ~/.codebuddy/skills; do
  for s in $(ls -1 $REPO | grep -vE '^(README|\.)'); do
    [ -e "$d/$s" ] || continue
    [ -L "$d/$s" ] || echo "🔴 实体副本（应为软链）: $d/$s"
  done
done
```
输出为空 ⇒ 全部走软链。有输出 ⇒ 那份是游离副本，改了不会同步。

## 测试

```bash
bash hub-handoff/scripts/tests/test-harvest-return.sh   # 11 tests
bash hub-handoff/scripts/tests/test-push.sh             # 13 tests
bash db-connect/scripts/tests/test-db.sh                # 23 tests
```

## 配置

- `db-connect/databases.json` — 从 `.example` 复制，填入真实连接信息（不提交）
- `rift-dispatch/model-catalog.json` — 模型结构化数据（费率 / 限免 / 盲评分数 / provider 映射）
- `rift-dispatch/model-routing.md` — 模型选择与 provider 路由规则
  > ⚠️ 旧的 `smart-dispatch/model-profiles.json` 已被这两个文件取代。
