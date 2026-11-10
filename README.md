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
| [rift-reap](rift-reap/) | 归档自己派出去的子会话（`rift-dispatch` 的反向）<br>⛔ 硬边界：只动 `parent-agent-id == 自己` 的，顶层会话与别人的子会话一律不碰 |
| [rift-integration-qa](rift-integration-qa/) | QA 统一入口：TDD · 三层一致(DB↔API↔FE) · 契约验证 · 假绿检测 · 真机回归 · 部署后验证 · 视觉验证<br>⚠️ 原 `integration-qa`，2026-08-27 更名 |
| [rift-egress-relay](rift-egress-relay/) | 本机到某个端点被网络层拦截时，借道另一台联网机器做 egress 中继<br>⭐ 既有工具链**不改代码**，导出 `HTTPS_PROXY` 即恢复；凭据与私钥不离开本机 |
| [rift-mail-triage](rift-mail-triage/) | IMAP 拉邮件 + HTML 草稿 + 按精确 UID 受控发送<br>默认只写草稿；用户明确授权后仅允许 `rift-mail send --uid UID --apply`。发送默认 dry-run，receipt 幂等阻止重复 SMTP，Sent 只读轮询且禁止 `IMAP APPEND`；凭据存 macOS 钥匙串 |
| [rift-remote-exec](rift-remote-exec/) | 在已注册的远端机器上执行命令，**不经 LLM、不消耗额度**<br>⭐ 用 paseo relay 通道直接开远端终端；附 `rx.sh` 封装（**复用已有终端**、四行协议判完成、**退出码判成败**、自动建/杀终端）与 Windows COMODO 文件锁、ego 脚本三大坑 |
| [pingcode-api](pingcode-api/) | **免登录**直调 PingCode Open API：用个人访问令牌（PAT）查工作项/工时，不登录、不换 token<br>附 `pc.sh`（curl 封装）与 `pc.py`（Python 封装，令牌自动解析 + 自动翻页）；令牌存 `~/wb/secrets/pingcode-token`（600，不入 git） |
| [skill-loader](skill-loader/) | **没有 `skill` 工具的 agent（MiniMax Code 子 agent）怎么加载 skill 正文**<br>路径规律 `skill 名 → 目录 → SKILL.md` + `skill-path.sh` 跨 5 个 runtime 目录查找 |

## 安装 —— 🔴 软链到本仓库，不要 cp

**本仓库是唯一源。** 各 agent 的 skills 目录全部软链过来，改一处五处生效，
且改动立刻出现在 `git status` 里，不会漏提交。

```bash
git clone https://github.com/mcdowell8023/agent-hub-skills.git \
  ~/AgentWorkspace/projects/skills/agent-hub-skills

# 推荐用脚本（会处理实体副本备份 + 幂等重建）
bash ~/AgentWorkspace/projects/skills/agent-hub-skills/scripts/install-links.sh

# 等价的内联版本（⚠️ 不要用 rm -rf：本机 rm 被 shim 成 mavis-trash，单次要好几秒）
REPO=~/AgentWorkspace/projects/skills/agent-hub-skills
for s in hub-handoff hub-comm browser-preflight db-connect \
         rift-dispatch rift-reap rift-integration-qa rift-egress-relay rift-mail-triage \
         rift-remote-exec skill-loader pingcode-api; do
  for d in ~/.claude/skills ~/.minimax/skills ~/.agents/skills ~/.codex/skills ~/.codebuddy/skills; do
    [ -d "$d" ] || continue
    [ -L "$d/$s" ] || { [ -d "$d/$s" ] && mv "$d/$s" "$d/$s.bak.$(date +%s)"; }
    ln -sfn "$REPO/$s" "$d/$s"
  done
done
```

⚠️ 实际入口以本机为准是 `~/.claude/skills` · `~/.minimax/skills` · `~/.agents/skills` ·
`~/.codex/skills` · `~/.codebuddy/skills` **五个**。
（2026-11-10 补上 `~/.minimax/skills`——此前循环漏了它，
漏装的表现就是「该 skill 在 MiniMax Code 的清单里根本不存在」。）

⛔ **不要用 `cp` 分发。** 2026-08-27 之前就是手工 cp 三份实体，结果本仓库落后本地
**近两个月**（`hub-comm` / `hub-handoff` 的 SKILL.md 在 git 里连 frontmatter 都没有，
`db_engine.py` 少 117 行）。改哪份、哪份生效、哪份是最新，全靠记忆。

### 一致性自查

```bash
bash ~/AgentWorkspace/projects/skills/agent-hub-skills/scripts/install-links.sh --check
```

输出为空 ⇒ 全部走软链。有输出 ⇒ 那份是游离副本（或没装），改了不会同步。

## 子 agent 没有 `skill` 工具时怎么加载 skill（2026-11-10）

**现象**：MiniMax Code 的**子 agent**（`explore` / `worker` / `verifier`）工具列表里
**没有**名为 `skill` 的工具，但上下文里**有** `<available_skills>` 清单
（只含 name + description，**没有路径**）——于是看得见 skill，却读不到正文。

⛔ 不要反复试 `skill(...)` 调用，那不是 skill 坏了，是**运行时没给这个工具**。

**解法**：按固定路径规律用 `read` / `bash` 直接打开正文：

```
<skill 名> → ~/.claude/skills/<skill 名>/SKILL.md
```

其它 runtime 目录同样规律：`~/.minimax/skills` · `~/.agents/skills` ·
`~/.codex/skills` · `~/.codebuddy/skills`。
不确定在哪个目录时用查找脚本：

```bash
bash ~/.claude/skills/skill-loader/scripts/skill-path.sh <skill 名>       # 打印正文路径
bash ~/.claude/skills/skill-loader/scripts/skill-path.sh <skill 名> --cat # 直接打印正文
```

细节与边界见 [skill-loader/SKILL.md](skill-loader/SKILL.md)。

## 测试

```bash
bash hub-handoff/scripts/tests/test-harvest-return.sh   # 11 tests
bash hub-handoff/scripts/tests/test-push.sh             # 13 tests
bash db-connect/scripts/tests/test-db.sh                # 23 tests
python3 -m unittest discover -s rift-mail-triage/scripts/tests -v  # rift-mail 发送安全与草稿 UID
```

`rift-mail-triage` 保留 `setup` / `selfcheck` / `fetch` / `draft` / `dedupe`，并提供受控 `send`：

```bash
rift-mail-triage/scripts/rift-mail send --uid 456          # 默认 dry-run，核对零副作用
rift-mail-triage/scripts/rift-mail send --uid 456 --apply  # 仅在用户明确授权当前邮件后执行一次
```

真实发送禁止临时拼 SMTP/IMAP 脚本。SMTP 后不得向 Sent `APPEND`；Sent 暂时不可见时只读等待或报告，
不补写、不重发。receipt 的 `PREPARED` 表示 SMTP 尚未开始，`UNKNOWN` 表示结果不确定且禁止自动重试，
`ACCEPTED` 表示全部 envelope recipients 已被 SMTP 接受。

## 配置

- `db-connect/databases.json` — 从 `.example` 复制，填入真实连接信息（不提交）
- `rift-mail-triage/scripts/config.json` — 从 `.example` 复制；凭据本身不进此文件，走 `rift-mail setup`（macOS 钥匙串）
- `rift-dispatch/model-catalog.json` — 模型结构化数据（费率 / 限免 / 盲评分数 / provider 映射）
- `rift-dispatch/model-routing.md` — 模型选择与 provider 路由规则
  > ⚠️ 旧的 `smart-dispatch/model-profiles.json` 已被这两个文件取代。
