---
name: skill-loader
description: 没有 `skill` 工具的 agent（MiniMax Code 子 agent / 脚本化 runner）如何加载 skill 正文：按「skill 名 → 目录 → SKILL.md」的固定规律用 read/bash 直接打开。附跨 5 个 agent 目录的查找脚本 skill-path.sh。Triggers: '没有 skill 工具', '子 agent 加载 skill', 'skill 加载不了', '读取 SKILL.md', 'skill 正文在哪'.
---

# Skill Loader — 没有 skill 工具时怎么把 skill 正文读进来

**适用**：你的工具列表里**没有**名为 `skill` 的工具（MiniMax Code 的子 agent 就是这样：
`explore` / `worker` 只有 read/write/edit/bash/grep/glob/web_fetch 等，没有 `skill`），
但你的上下文里**有 `<available_skills>` 清单**（只有 name + description，没有路径）。

⛔ 别去反复试 `skill(...)` 调用，也别假设加载失败是 skill 坏了——**用 read 直接读正文就行**。

---

## 1. 路径规律（这就是全部）

```
<skill 名>  →  <某个 agent 的 skills 目录>/<skill 名>/SKILL.md
```

各 runtime 的 skills 目录（Mac 上固定这 5 个）：

| Runtime | 目录 |
|---|---|
| Claude Code | `~/.claude/skills/` |
| **MiniMax Code** | `~/.minimax/skills/` |
| Agents（通用） | `~/.agents/skills/` |
| Codex | `~/.codex/skills/` |
| CodeBuddy | `~/.codebuddy/skills/` |

这些目录里的绝大多数条目是**指向唯一源的软链**，所以路径稳定、内容一致。

---

## 2. 三步加载

### ① 先试最快的（多数情况一次中）

```bash
read ~/.claude/skills/<skill 名>/SKILL.md
```

`read` 工具直接给绝对路径即可；软链会跟着解析。

### ② 不确定在哪个目录，就用查找脚本

```bash
bash ~/.claude/skills/skill-loader/scripts/skill-path.sh <skill 名>
```

输出**正文绝对路径**，拿到后 `read` 它；加 `--cat` 直接打印正文。

### ③ 纯手工查找（脚本不可用时）

```bash
for d in ~/.claude/skills ~/.minimax/skills ~/.agents/skills ~/.codex/skills ~/.codebuddy/skills; do
  [ -f "$d/<skill 名>/SKILL.md" ] && echo "$d/<skill 名>/SKILL.md"
done
```

---

## 3. 为什么清单里没有路径

清单是运行时从各 skill 目录的 frontmatter 生成的，只带 `name` + `description`。
**路径规律是稳定的**（目录名 = skill 名），所以不需要运行时额外注入路径——
按规律找就行。

⚠️ **frontmatter 的 `name` 建议与目录名保持一致**：目录名就是查找键。
不一致时（例如目录 `foo-bar` 而 name 写 `foo_bar`），按目录名找更稳。

---

## 4. 装 skill 到哪些目录

改完 skill 后，**软链到所有 runtime 的 skills 目录**（唯一源只改一处，五处生效）：

```bash
bash ~/AgentWorkspace/projects/skills/agent-hub-skills/scripts/install-links.sh
```

它把仓内**全部** skill 软链到 5 个 runtime 目录（`~/.claude` `~/.minimax` `~/.agents`
`~/.codex` `~/.codebuddy`），并自动体检。

⛔ **别自己写 `rm -rf` 循环**：本机 `rm` 被 shim 成 `mavis-trash`，单次要好几秒，
批量执行会卡住；而且 `rm -rf` 有误删真源的风险。`install-links.sh` 的做法是
软链用 `ln -sfn` 直接替换、实体目录先 `mv` 备份（`.bak.<时间戳>`）。

```bash
bash ~/AgentWorkspace/projects/skills/agent-hub-skills/scripts/install-links.sh --check
# ✅ 全部为软链
```

⚠️ `~/.minimax/skills` 容易漏——旧版 README 的内联循环没覆盖它，
**漏装的表现就是「该 skill 在 MiniMax Code 里看不见」**。

---

## 5. 自检

```bash
bash ~/.claude/skills/skill-loader/scripts/skill-path.sh --list | head
# 应列出已安装的 skill 名 + 路径
```

如果某个 skill 在清单里但 `--list` 里找不到 → 它的目录没被软链到任何 runtime 目录，
按 §4 补装。
