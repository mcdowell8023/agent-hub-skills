# Rift Dispatch — 模型路由规则

> 本文件定义模型选择、provider 路由、降级链、时段策略。
> 模型结构化数据（费率/盲评分数/provider 映射）见 `model-catalog.json`。

---

### 🔴 v4-pro 使用门禁（2026-08-21 收紧）

用户反馈：**「很多 agent 还是喜欢用 v4-pro，消耗太快」**。规则早已写在十几处仍拦不住——
根因不是规则不够，是**数据在反着劝**：

```
blindEval        v4-flash 96  >  v4-pro 86      ← 支持 flash
sameRoundEval    v4-pro  96  >  v4-flash 89     ← agent 抓这个当理由 ⚠️
```

分数是结构化数据、规则是散文，agent 扫一眼只抓分数。⇒ 改成机器可读门禁：

| catalog 字段 | 值 |
|---|---|
| `selectableByDefault` | **`false`** ← 布尔，比散文难绕过 |
| `dispatchRank` | 8（flash 是 2，刻意拉开） |
| `requiresPrecondition` | flash 已在**本任务**做砸过一轮；**派发理由必须写明哪一轮、砸在哪、为什么升档能解决**。写不出来 ⇒ 不许升 |
| `costMultiplier` | 2.6x vs flash（0.13x vs 0.05x） |

⚠️ **`sameRoundEval` 那组分数的正确读法**：它说的是「**升档时该升 v4-pro 而不是跳 K3（32 倍）**」，
⛔ **不是**「该跳过 flash」。且 flash 在架构题反超（Kafka 34 vs 31）。
**大部分场景 flash 够用**（用户 2026-08-21 明确）。

---

## ⛔ 硬性约束 7（2026-08-16 用户决策）—— DeepSeek 优先 + opencode 走 volcengine

**1. DeepSeek 系列是默认工作模型族，族内优先 `deepseek-v4-flash`**（2026-08-20 用户明确）。
派发时先问「这活 DeepSeek 能不能做」，只有它明确不适合才考虑别的。
`deepseek-v4-pro` 是**升档档位**——⛔ 只在 flash 于本任务做砸过一轮时才用，不预先选。

**2. opencode 通道优先火山，首选 `volcengine-coding`**（Coding Plan，按月付费套餐，与 codebuddy credits 是**不同钱包**）。
⚠️ 2026-08-20 起首选从 `volcengine-agent-plan` 改为 `volcengine-coding`——后者额度独立且 `--variant` 可用，见下方 §火山有两个套餐、三个 provider。

```
opencode 侧 provider 优先级：
  ① volcengine-coding/deepseek-v4-flash                         ← ⭐ 默认。Coding Plan 独立额度，
                                                                   Chat API ⇒ --variant off/on 直接可用
  ①b volcengine-agent-plan/*                                    ← 需要 Coding Plan 没有的 5 个模型时
                                                                   （⚠️ 该 provider 上 --variant 静默失效）
  ①c volcengine-chat/deepseek-v4-*                              ← 要 Agent Plan 额度 + 控思考强度时
  ①d 上述任一 provider 的 /deepseek-v4-pro                       ← 仅 flash 答得不够时换
  ② ~~deepseek/deepseek-v4-*（官方 API）~~                      ← 🔴 2026-08-20 已 disable，不可用
  ③ 其余                                                        ← 不主动选
```

### 📦 火山有两个套餐、三个 provider（2026-08-20 起）

Agent Plan 额度不够，用户 2026-08-20 另购 **Coding Plan（Pro 套餐，包月，至 2026-10-20，自动续费关）**。
两个套餐**额度独立、API key 不同**。

| provider | 套餐 | baseURL | npm | 模型数 | `--variant` |
|---|---|---|---|---|---|
| ⭐ **`volcengine-coding`** | **Coding Plan** | `…/api/coding/v3` | `@ai-sdk/openai-compatible` | **7** | ✅ `off`/`on` |
| `volcengine-agent-plan` | Agent Plan | `…/api/plan/v3` | `@ai-sdk/openai` | 12 | ❌ 静默失效 |
| `volcengine-chat` | Agent Plan（同额度同 key） | `…/api/plan/v3` | `@ai-sdk/openai-compatible` | 3 | ✅ `off`/`on` |

**Coding Plan 7 个模型**（2026-08-20 逐个 curl 实测全部可用）：
`deepseek-v4-flash` · `deepseek-v4-pro` · `glm-5.3` · `minimax-m3` · `kimi-k2.7-code`
· `doubao-seed-2.1-turbo` · `doubao-seed-2.0-lite`

**Coding Plan 相对 Agent Plan 少的 5 个**：`ark-code-latest` · `kimi-k3` · `doubao-seed-evolving`
· `glm-latest` · `doubao-seed-2.0-mini` ⇒ 需要这几个才回 `volcengine-agent-plan`。

⛔ **`auto` 模式 Coding Plan 不支持**（实测报 `UnsupportedModel: does not support the coding plan feature`），故未配置。

🔴 **baseURL 千万别写错**：官方明确 **不要用 `https://ark.cn-beijing.volces.com/api/v3`——会产生额外费用**。
Coding Plan 必须是 `…/api/coding/v3`（OpenAI 协议）或 `…/api/coding`（Anthropic 协议）。

⚠️ **`volcengine-chat` 的定位被削弱了**：它原本是「Agent Plan + 思考强度可控」的唯一途径，
但 `volcengine-coding` 现在同时提供 deepseek 两兄弟 + 思考强度可控 + **独立额度**。
`volcengine-chat` 只在「必须消耗 Agent Plan 额度且要控思考强度」时才有意义。

---

### ⭐ 一次性调用 / 并发任务的通道：pi 首选（2026-08-20 用户决策）

🔴 **pi 有两种启动方式，⚠️ 不是「Paseo 还是 pi」的二选一** —— 两种跑的都是 pi，
区别只在能不能看见它。开发要可观测 ⇒ **用 Paseo MCP 派 pi**，两样都要，本来就不冲突。

```
① 开发实施类 → Paseo MCP 派 pi（create_agent）   ⭐ 可见 / 可干预 / get_agent_status
   provider: "pi/volcengine-coding/deepseek-v4-flash"   （Paseo 的 pi provider 暴露 27 个模型）
   或原有:   "codebuddy-code/hy3" / "codebuddy-code/deepseek-v4-flash" / "qoderclicn/qmodel_38max"
   ⛔ 别用 pi -p 派开发任务——不是 pi 不行，是 CLI 这条路你看不见
② 只读/短/审查 → pi -p CLI                 省机器、不堆 serve
   pi -p --provider volcengine-coding --model deepseek-v4-flash "…"
   （族内优先 v4-flash；v4-pro 仅在 flash 于本任务做砸过一轮时用）
③ 审查专用 → pi + Copilot                  ⛔ 仅审查，不做开发（用户 2026-08-20 明确）
   pi -p --provider github-copilot --model gpt-5.5 "…"
④ opencode                        🔻 兜底，排最后
⛔ codex + 火山 —— 该【一次性调用通道】已撤销，见下
   ⚠️ 但 codex 作为 **Paseo 派发 provider** 的原有定位不变（§4 Provider 表 · §3.1 · 伪代码分支）
```

**Copilot 通道（pi `/login` 接入，8 模型）**：`gpt-5.5`(⭐审查默认) · `gpt-5.5` · `gpt-5.3-codex`
· `gpt-5.5-mini` · `gpt-5-mini` · `gemini-3.1-pro-preview` · `gemini-3.5-flash` · ⚠️`claude-sonnet-4.6`

🔴 `claude-sonnet-4.6` 属 **Claude 族** —— 主会话就是 Claude，**主会话自己写的东西不得用它审**。
⛔ Copilot 额度只留给审查；开发一律走 ① 的火山通道。

**pi 的能力已对齐 Paseo 派发的 codebuddy 子会话**（2026-08-20 实测，主会话独立核验、不采信自述）：
读文件 → 改代码 → 写测试 → `bash` 跑测试 → `git commit`（中文 commit message 也合规）。

| 项 | 状态 |
|---|---|
| 全局规则 | ✅ `~/.pi/agent/AGENTS.md` = `~/.claude/CLAUDE.md` 整份复制（pi 不支持 `@import`，与 `~/.codex/AGENTS.md` 同样处理）|
| 项目规则 | ✅ 自 cwd 向上找 `AGENTS.md`/`CLAUDE.md`；`AGENTS.override.md` 可覆盖该目录 |
| Skills | ✅ 原生读 `~/.agents/skills/`，实测 20 个全加载 |
| 火山两套餐 | ✅ `volcengine-coding`(7) + `volcengine-agent-plan`(12)，19 模型逐个实跑通过 |

⚠️ 配置里**必须**有 `compat.supportsDeveloperRole: false`（火山不认 OpenAI 的 `developer` role）；
⛔ **不要**加 `compat.thinkingFormat`（实测 `"zai"` 让请求全部挂起）。

### 🔴 opencode 卡死电脑的根因（2026-08-20 用户定位）—— 不再禁用，但排最后

> **是「纯命令方式」造成的**：每次 `opencode run --pure` 拉起一个 serve，
> 反复调用则 **serve 堆叠**，内存被吃穿。这与既有记录一致——
> `oc-review` v1.13.0 正是靠「共享 serve + `--attach`」消掉 per-run serve 堆叠的。

⇒ **单次、偶发调用本身是安全的**；⚠️ 但 **review 已迁到 `pi -p` + Copilot**，
opencode 现在**没有任何常规用途**，纯兜底。
⛔ **循环里反复 `opencode run` 是危险动作** —— 改用 `pi -p`，或复用共享 serve + `--attach`。

### ⛔「codex + 火山」这条**一次性调用通道**已撤销（2026-08-20）

⚠️ **撤销的只是这条通道，不是 codex 本身。**
`codex` 作为 **Paseo 派发 provider** 的原有定位**完全不变** —— 见 §4 Provider 类型表
（`codex | Paseo create_agent | auto`）、§3.1 Paseo 创建、以及 SKILL.md 伪代码的
`if provider in [codebuddy-code, qoderclicn, claude, codex]` 分支。

撤销原因：codex 里 `model` 与 `model_provider` 是两个独立字段，**catalog entry 无 provider 字段**
（33 字段逐一确认）⇒ 一个 session 只能连一个 provider，界面 `/models` 无法跨 provider 切换。
用户选择保留原有 GPT，codex 配置已**逐字节还原**（`diff` 验证），
并删除 `~/.config/volcengine/env`（走 `trash`）与 `~/.zshenv` 引用。

⚠️ 附带事实：codex 默认的 `gpt-5.6-sol` 实测 `out of credits`，所以它当前也不适合当审查通道。

---

### 🔴 审查通道的真正约束是「异构」，不是「禁用某个模型」

**⛔ 硬约束（全局红线 #8）：评审模型族 ≠ 实施模型族。** 这是**不变量**，与具体是哪个模型无关。

当前在用的模型族：**Claude · DeepSeek · Hy3(混元) · Kimi · GLM(智谱) · MiniMax · Qwen · 豆包 · GPT**

| 本次实施用了 | 评审可以用（任选异族） | 评审不能用 |
|---|---|---|
| 🔴 **主会话自己动手（Claude）** | DeepSeek / GLM / MiniMax / Kimi / GPT / Hy3 … | **Claude 全族** |
| `cb/hy3` | Claude / DeepSeek / GLM / Kimi / GPT … | Hy3 |
| `cb/deepseek-v4-flash` · `-pro` | Claude / GLM / MiniMax / Kimi / GPT … | **DeepSeek 全族** |
| `cb/kimi-k3` · `kimi-k2.7-code` | Claude / DeepSeek / GLM / GPT … | Kimi 全族 |
| `qcn/qmodel_38max` | Claude / DeepSeek / GLM / Kimi / GPT … | Qwen 全族 |
| `claude/*`（Paseo 派 Claude 子会话） | DeepSeek / GLM / Kimi / GPT … | **Claude 全族** |

🔴 **第一行最容易被忽略，却最常发生**：主会话就是 Claude，凡是**我自己写的代码/文档/配置**，
评审都必须换族——⛔ 不能派 `claude/*` 子会话来审自己刚写的东西，那等于自审。

⚠️ Claude 族可以当评审（族不同就合规），但**消耗 Claude 订阅额度**，
按 P3「可派发但不推荐」建议留给主会话；有更省的异族可用时优先用它们。

⇒ **不要把它记成「DeepSeek 不许审查」** —— 实施是 Hy3 或 K3 时，DeepSeek 是完全合格的异构评审。
只因为当前 cb 默认落点是 `deepseek-v4-flash`，**那一路**的评审才要排除 DeepSeek 族。

`review` 类目前走 **`pi -p --provider github-copilot --model gpt-5.5`**（2026-08-20 起，实测 33s；opencode 那条降为兜底），
理由是它同时满足三条：族异于所有 cb 白名单模型 · 有额度 · 有历史盲评口径可对照。这不是遗漏，是有意保留：

> **异构审查要求「评审模型 ≠ 实施模型」**（全局红线 #8）。约束 7 第 1 条已经把实施侧定成 DeepSeek，
> 若评审也换成 `volcengine-agent-plan/deepseek-*`，就变成 **DeepSeek 审 DeepSeek —— 自己审自己**，
> 异构审查直接失效。2026-08-12 与 08-16 两轮异构审共抓到 13 处问题，全部来自「换一个模型族去看」。

⇒ 「opencode 优先 volcengine」的适用范围是**实施类 / 问答类**的 opencode 调用；
**审查类是硬例外**，与白名单例外同级。

### 📌 同一个 DeepSeek 模型现在有三条通道，别选错

🔻 **下表是「若确实要走 opencode」时的通道对照，⛔ 不代表 opencode 是默认。**
2026-08-20 起 opencode 已降为纯兜底，正常通道见上方 **§通道判据总表**（开发=Paseo 派 pi · 只读=pi -p 火山 · 审查=pi -p Copilot）。

| 通道 | 调用方式 | 计费 | 什么时候用 |
|---|---|---|---|
| `cb/deepseek-v4-*` | Paseo `create_agent` | codebuddy credits（0.05x / 0.13x） | **派发开发任务**——有完整 agent 会话、工具、worktree、git |
| **`volcengine-coding/deepseek-v4-*`** | `opencode run --pure [--variant off\|on]` | **Coding Plan 按月套餐**（独立额度） | 🔻 opencode 兜底时的首选模型：只读分析、问答、长上下文（1,024,000 context），思考强度可控 |
| `volcengine-agent-plan/deepseek-v4-*` | `opencode run --pure` | **按月套餐**（不动 cb credits） | **一次性调用**：只读分析、问答、长上下文（**1,024,000 context**） |
| `volcengine-chat/deepseek-v4-*` | `opencode run --pure --variant off\|on` | **同一按月套餐**（同 key） | 同上，**且需要控思考强度时**——`volcengine-agent-plan` 上 `--variant` 静默失效（v10.3 实测），本 provider 走 Chat API 可透传 |
| ~~`deepseek/deepseek-v4-*`~~ | ~~`opencode run --pure`~~ | ~~自费现金~~ | 🔴 **2026-08-20 用户已加入 `disabled_providers`**。套餐耗尽改用 `github-copilot/*` 或 `opencode/deepseek-v4-flash-free`（免费） |

⚠️ **这两条通道不可互换**：Paseo 子会话能改代码、跑测试、提交；`opencode --pure` 是一次性文本调用。
派开发任务不要因为「volcengine 不耗 credits」就改用 opencode ——拿不到 agent 能力。

**连带影响**：§3 那节「opencode 官方 DeepSeek 的峰谷定价」**实际用途大幅缩小**——
volcengine 套餐提供同样的 v4-flash/v4-pro 且不花现金，官方 API 只剩套餐耗尽时的兜底。

### ⚠️ 与「Hy3 优先」（约束 4-2）的关系：Hy3 暂时仍在 DeepSeek 之前

Hy3 是 **0.00x**（限免至 2026-08-31），比任何 DeepSeek 通道都便宜，且 08-12 有明确用户决策。
本约束**不推翻它**——顺序仍是 `hy3 → deepseek-v4-flash → deepseek-v4-pro → K3`。
**08-31 限免结束后，DeepSeek 自动接管第一顺位**，无需再改规则。
（若希望现在就让 DeepSeek 压过 Hy3，需用户明确指示——那等于放弃一个免费档。）

### ⚠️ 未决：volcengine 侧那 10 个非 DeepSeek 模型

`volcengine-agent-plan` 共 12 个模型，除两个 DeepSeek 外还有
`ark-code-latest` · `doubao-seed-evolving`(1M) · `doubao-seed-2.1-turbo` · `doubao-seed-2.0-lite` · `doubao-seed-2.0-mini`
· `glm-5.3` · `glm-latest` · `minimax-m3` · `kimi-k2.7-code` · `kimi-k3`。

按约束 7-1「DeepSeek 优先」，这 10 个**不主动选**。
⚠️ 但注意 `glm-5.3` / `minimax-m3` / `kimi-k2.7-code` **在 codebuddy 侧已被白名单关闭**（约束 6），
而它们在 volcengine 是另一个钱包——**是否同样关闭尚未经用户确认**。
在确认前按「不主动选、也不判违规」处理；用户显式指定时可用。

---

## ⛔ 硬性约束 6（2026-08-16 用户决策）—— **Provider 模型白名单，优先级最高**

**白名单之外的一切模型禁止派发，包括本文件下方表格里仍在推荐的。** 表格与白名单冲突时以本表为准。

| Provider | 允许的 model id | 实测费率 | 角色 |
|---|---|---|---|
| `codebuddy-code` | **`hy3`** | **0.00x** | ⚡ 第一顺位（限免至 2026-08-31） |
| `codebuddy-code` | **`deepseek-v4-flash`** | **0.05x** | ⭐ 默认落点 |
| `codebuddy-code` | `deepseek-v4-pro` | 0.13x | **仅升档档位**：flash 在本任务做砸过一轮才用。⛔ 不做预防性升档（08-20 用户决策） |
| `codebuddy-code` | **`kimi-k3-2`** | **🔴 1.62x（全场最贵）** | 极致档 / 唯一升档目标 —— **⛔ 不得随意使用**，见下方 §K3 使用红线 |
| `qoderclicn` | **`qmodel_38max`**（Qwen3.8-Max） | 0.50x | cb 断供时的降级备选 |

**⛔ 已关闭（cb）**：`minimax-m3` · `minimax-m2.7` · `glm-5.3` · `glm-5.2` · `glm-5.1` · `glm-5v-turbo` · `kimi-k2.7` · `kimi-k2.6`
**⛔ 已关闭（qcn）**：`qmodel_38max` 以外全部（`auto` / `qmodel_latest` / `qmodel` / `q36fmodel` / `dmodel` / `dfmodel` / `gmodel` / `gm51model` / `kmodel` / `mmodel`）

**不受本白名单约束的通道**（它们不走 codebuddy/qcn 额度）：
`opencode --pure -m github-copilot/gpt-5.5`（审查硬例外）· `claude`（⚠️ 可派不推荐）· ~~`deepseek/*` 官方 API~~（🔴 2026-08-20 已 disable）。

### 本次白名单带来的三个连锁后果

**1. `minimax-m3` 关闭 —— 中间档一度断掉，已由 v4-pro 补上（08-16 重测）。**

```
关闭 M3 当时:  hy3 0.00x → flash 0.05x → ────────── → K3 1.62x   ← 32 倍跳变
重测之后:      hy3 0.00x → flash 0.05x → v4-pro 0.13x → K3 1.62x   ← 中间档回来了
```
v4-pro 只贵 flash **2.6 倍**，而在算法/精细实现上高 **8 分**（详见 §V4-Pro 重测）。
⇒ **「⛔ 不做预防性升档」仍然成立**，升档条件不变（上一档已在这个任务上做砸过一轮）；
但升档的**落点从 K3 改为 v4-pro**，K3 退回真正的最后一档（要 **v4-pro 也做砸**才轮到它）。

**2. ✅ K3 恢复启用（用户 2026-08-16 决定），作为极致档——但带一条使用红线。**

### 🔴 K3 使用红线（用户 2026-08-16 明确要求：**很贵很贵，不要随意使用**）

```
cb/kimi-k3-2 = 1.62x     ← 全场最贵，且是白名单内唯一 1.0x 以上的模型
  vs cb/deepseek-v4-flash 0.05x   →  贵 32 倍
  vs cb/hy3 0.00x                 →  从免费变成付费
```

**性价比（盲评总分 ÷ 费率）：K3 = 110.5/1.62 = 68 —— 全场最低。**
它留在白名单里是因为「白名单内唯一的 S 级」，**不是因为划算**。

**⛔ 只有这两种情况可以派 K3，其余一律不派：**

| 允许 | 说明 |
|---|---|
| ① 用户显式 `--model k3` | 用户自己知道在花什么 |
| ② **v4-pro 也已经在这个任务上做砸过一轮** | 升档的唯一入口，⛔ 不做预防性升档。⚠️ 08-16 起收紧：flash 做砸先升 v4-pro(0.13x)，不是直接上 K3 |

**⛔ 以下都不构成派 K3 的理由**（每条都被实测或成本算术否掉）：

- ❌「任务看起来很难 / 很重要 / 风险高」→ 两组实测（n=1、n=12）都表明**模型档位不是质量关口**，
  该提的是 thinking 档位（xhigh）和审查强度（异构审），不是模型档位
- ❌「这是 algorithm / architecture 类，K3 分最高」→ 这两类各有更便宜的落点：
  `algorithm` / `architecture` 都先走 **flash**（0.05x），做砸了才升 v4-pro（0.13x）。
  K3 的分数差换 32 倍成本，要用户自己拍板
- ❌「反正只跑一次」→ 一次 K3 ≈ 32 次 flash ≈ 无限次 Hy3
- ❌「先用好的保险一点」→ 这就是「预防性升档」的原话，明令禁止

**⚠️ 加上它还有可靠性前科**：2026-07-23 实测出现反复空转（报进度就 idle、git 无产出），
用户 08-16 恢复启用时知悉此风险。⇒ **派了 K3 必须核 `git log` 是否真有 commit，不能只看它报进度。**
花了 32 倍的钱还拿不到产出，是这个模型特有的失败模式。

### 📊 V4-Pro 重测（2026-08-16，正式版发布后）—— 旧的「86 分被取代」记录已失效

用户告知 v4-pro 已是正式版、能力很强，遂重测。**同轮同题盲评，v4-pro 96 > v4-flash 89**：

| 题目 | v4-pro (0.13x) | v4-flash (0.05x) | 差 |
|---|---|---|---|
| LRU Cache（算法 / 精细实现） | **33** | 25 | **+8** |
| 并发 Bug 诊断 | **32** | 30 | +2 |
| Kafka 架构设计 | 31 | **34** | **-3** |
| 总分 /120 | **96** | 89 | +7 |

**分项高度分化，这才是可操作的部分**：v4-pro 赢在算法/精细实现，**输在架构设计**。

- ⇒ **v4-pro 是升档档位，不是任何任务类型的默认落点**（2026-08-20 用户决策）
- ⇒ `architecture` 走 flash（flash 在这题本就高 3 分，无争议）
- ⇒ **默认落点仍是 flash**：性价比 `flash 89/0.05 = 1780` vs `v4-pro 96/0.13 = 738`，flash 高 2.4 倍

> 🔴 **2026-08-20 修正：`algorithm` 的落点从 v4-pro 改回 flash。**
> v10.1 曾据本轮 LRU 数据（33 vs 25）把 `algorithm` 直接指向 v4-pro——那**违反了本文件自己的
> 「⛔ 不做预防性升档」原则**：还没让 flash 试过，就因为「这类任务 v4-pro 更强」而预先升档，
> 与「任务高风险 ⇒ 升模型档位」是同一个被两组实测（n=1、n=12）否掉的推论。
> 现在统一为：**所有类型都先 flash，做砸了才升 v4-pro**。
> 上表 +8 分的数据**依然有效**，它的正确用法是——**升档时该升到 v4-pro**（而不是直接跳 K3）。

⚠️ **效力边界，不要拿去和历史分数直接比**：历史只存档了并发题原题，LRU/Kafka 的 prompt 是
从旧 judge rubric **重建**的，所以绝对分与历史 86/96 不可比——**本轮只有同轮 A/B 的相对关系严格成立**。
n=1 单次运行、单评委（GPT-5.5），置信度与 `realTaskEval` 同级，低于多轮 blindEval。
（本次已把三题 prompt 全部存档，以后不会再有这个问题。）

全文与原始产出：`~/AgentWorkspace/tmp/v4pro-benchmark-20260816/REPORT.md`

> 本约束**吸收**了以下历史条目，它们不再需要单独判断：
> 07-28「qcn 只准派 Qwen3.8-Max」（id 已更新为 `qmodel_38max`）· 08-02「GLM-5.2 全面禁用」
> · 08-02「K2.6 走 cb 版」——这些模型现在都在关闭清单里。

---

## ⛔ 硬性约束 5（2026-08-16，qcn 限时1折结束 —— 时段策略整体废止）

**事实来源**：用户告知「qoder cli cn 没有夜间优惠了」+ `paseo list_models` 实测复核。✅ 已确认。

**1. qoderclicn 的「限时1折」活动已结束，费率回到基准价，夜间折扣一并取消。**

| 模型 | 旧记录（1折期） | 实测 2026-08-16 | 变化 |
|---|---|---|---|
| Qwen3.8-Max | 0.05x 日 / **0.01x 夜** | **0.50x**（无日夜之分） | 涨 10 倍 |
| Qwen3.7-Max `qmodel_latest` | 0.25x 日 / 0.10x 夜 | **0.50x** | 涨 2 倍 |
| Qwen3.7-Plus `qmodel` | 0.10x 日 / 0.04x 夜 | **0.10x** | 日间价不变，夜价没了 |

> 0.50 × 10% = 0.05 —— 「1折」本来就是打在 0.50x 基准价上的，活动结束即回到 0.50x。
> `list_models` 全表**已无任何日/夜费率区分**。

**2. ⛔ 时段策略（原 P6）整个废止。** 现在**没有任何模型有时段性折扣**，
派发链 24 小时不变，不再需要判断 `is_night()`：

```
⚡ cb/hy3@high (0.00x) → cb/deepseek-v4-flash@xhigh (0.05x) → cb/deepseek-v4-pro@xhigh (0.13x) → cb/kimi-k3-2@xhigh (1.62x)
```

连带作废：**约束 4 第 5 点**（夜间也先给 Hy3）—— 不用再说了，全天都是 Hy3 优先；
**约束 2 第 2 点**（夜间默认 qcn）—— 其唯一依据「夜间 0.01x 全场最低」已不成立。

**3. qoderclicn 降为「cb 断供时的降级备选」，不再主动选。**

白名单只留了 `qmodel_38max`（0.50x），而 cb 的 `deepseek-v4-flash` 是 **0.05x 且 A 级 96**——贵 10 倍。
性价比（盲评总分 ÷ 费率，flash 用其历史 96 分口径）：`flash 96/0.05 = 1920` · **`Qwen3.8-Max 101.5/0.50 = 203`** · `K3 110.5/1.62 = 68`。
（08-16 重测轮里 flash 得 89，对应 1780——两个数出自不同 prompt 批次，不要混用，见 §V4-Pro 重测。）
Qwen3.8-Max 比已被禁用的 GLM-5.2（128）好，但远不如 cb 主力，**没有主动派它的理由**。
它现在唯一的用途是 **cb 侧整体限额时的降级落点**（见 §4 降级链）。

**4. 🔴 `qmodel_preview` 这个 model id 已经不存在了** —— 现在是 **`qmodel_38max`**（label 从
`Qwen3.8-Max-Preview` 变成 `Qwen3.8-Max`，疑似 preview 转正）。
本文件此前所有 `qcn/qmodel_preview` 的派发指令**都会失败或静默降级**，已全文替换。
07-28 那条「qcn 只准派 Qwen3.8-Max」的白名单约束**继续有效**，只是 id 换成 `qmodel_38max`。

**5. 顺带实测更正的费率（同一次 `list_models`）**：
`cb/deepseek-v4-flash` **0.06x → 0.05x**（降价）；`qcn/kmodel` 的 label 已从 Kimi-K2.6 变成
**Kimi-K2.7-Code 0.30x**（catalog 里 K2.6 挂 `kmodel` 的映射是错的，已标注）。

---

## ⛔ 硬性约束 4（2026-08-12 用户决策，优先级最高，覆盖以下全部约束与表格）

**1. codebuddy 侧默认模型 = `deepseek-v4-flash`（实测 0.05x）。** cb 派发一律从 flash 起步，
⛔ 不做预防性升档（升档唯一条件仍是「上一档已在这个任务上做砸过一轮」，见 SKILL.md §模型档位）。
升档顺序：flash(0.05x) → **v4-pro(0.13x)** → K3(1.62x)。

**2. Hy3 能做的活优先派 Hy3。** 限免期内（至 2026-08-31）Hy3 是 **0.00x**，比 flash 的 0.05x 还省，
且 2026-08-02 五臂实测里免费的 hy3 恰好抓到了 flash@max 踩的坑。派发顺序：

```
⚡ cb/hy3@high (0.00x)              ← 先问「这活 Hy3 能不能做」
      ↓ 命中下方第 3 条清单
   cb/deepseek-v4-flash@xhigh (0.05x)   ← cb 默认落点
      ↓ flash 已在本任务做砸过一轮（⛔ 仅此一条，不预防性升）
   cb/deepseek-v4-pro@xhigh (0.13x)     ← 中间档（⛔ 只在 flash 做砸后进入，不预先选）
      ↓ v4-pro 也做砸了
   cb/kimi-k3-2@xhigh (1.62x)           ← 🔴 极致档，⛔ 不得随意使用
```

**3. 「Hy3 做不了」判定清单（本表是唯一真源；命中任意一条 → 直接跳 v4-flash，不要先试）**：

| 条件 | 对应 §1 代号 | 依据 |
|---|---|---|
| 任务涉及图像 / 视频 / 多模态 | — | 官方 0802 公告：会切多模态模型并**正常计费**，免费不成立（§3） |
| 当日免费额度耗尽 / 探活未秒回（排队） | — | 官方 0802 公告：繁忙进排队，长任务会卡住（§3） |
| 算法 / 精细数据结构实现 | `algorithm` | 盲评 LRU **22 分**，是 Hy3 唯一明显短板（§2 速查表） |
| 性能优化 / 大数据量 | `perf` | Hy3 无 perf 类实测支撑，不靠免费理由反悔 |
| 架构深度设计（选型 / 拓扑 / 一致性方案） | `architecture` | catalog `avoidFor: architecture-deep`；arch 33 分居中 |
| Hy3 已在这个任务上做砸过一轮 | — | 同 flash 的升档逻辑 |

⚠️ 命中后三类的落点（08-16 重测后已分化，⛔ 都不直接上 K3）：

| 代号 | 落点 | 依据 |
|---|---|---|
| `algorithm` | `deepseek-v4-flash`（0.05x） | ⛔ 不预防性升档（08-20 修正）。做砸了再升 v4-pro——重测 LRU 33 vs 25 说明**升档该升它**，不是说该跳过 flash |
| `perf` | `deepseek-v4-flash`（0.05x） | 无针对性数据，走默认落点 |
| `architecture` | `deepseek-v4-flash`（0.05x） | 重测 Kafka flash 34 > v4-pro 31 |

做砸了再按升档链往上走（flash → v4-pro → K3）。任务明确吃极致深度时可显式 `--model k3`。

⛔ **本表与 §1 表中标 ⛔ 的行必须一一对应**。改任一边都要同步另一边，否则会出现
「表里写着 Hy3 不适用、清单里查不到 → 实际派了 Hy3」的漏判（2026-08-12 异构审抓到过一次）。

⚠️ 反过来讲：**Hy3 的 bug 诊断盲评 36.5，白名单内最高**（K3 34.5、flash 32；原第一名 M3 的 38 已随 M3 关闭出局）。
`core` / `test` / `batch` / `robust` / `doc` / `kb` / bug-fix 这些类型，不要因为它挂 B 级就绕开。

**4. thinking 档位按模型分别定**：`hy3` 用 **`high`**（max 已被两轮盲评证伪；`xhigh` 从未在 Hy3 上测过，
不得当默认）；`deepseek-v4-flash` / `deepseek-v4-pro` / `kimi-k3-2` 用 **`xhigh`**（约束 3）。

~~**5. 本约束改写「硬性约束 2 第 2 点」的夜间规则**~~
⛔ **本条 2026-08-16 作废（约束 5）**：qcn 夜间折扣已取消，不存在「夜间该不该换 qcn」的判断了。
Hy3 优先是**全天候**的，不再分时段；Hy3 被排除时一律落 `cb/deepseek-v4-flash`（0.05x）。

> 保留一条仍然成立的教训：**任何"换更便宜 provider"的替换都只作用于默认落点 flash，
> 不得下调已按任务需要升上去的 K3**（2026-08-12 异构审抓到伪代码会无条件冲掉高档模型）。
> 这条原则与时段无关，将来若再出现新的低价 provider 同样适用。

---

## ⛔ 硬性约束 3（2026-08-02 用户决策，优先级最高）

**1. `xhigh` 是默认 thinking 档位。** 不再是 `high`。见 §2 Thinking 强度建议。

**2. 实测数据只作为记录供参考，不设死权重规则。**

> 用户 2026-08-02 决定：「实测记录到 skill 就好，交给模型自主决策。权重的事情，等数据完善完善再说。」

即：`§2 真实任务实测` 与 `model-catalog.json` 的 `realTaskEval` 是**证据**，
盲评分数 + 费率是另一份**证据**，两者都摆出来，**由派发时的模型自行判断**该信哪个。
⛔ 不要写「实测优先于盲评」这类硬规则 —— 当前实测样本 n=1，还不够支撑。

⚠️ 已知的一处冲突（供判断时参考，非结论）：盲评 114 分的 `m3` 与 96 分的 `flash`
在同一道实现题上收敛到同一方案、零差异；而盲评里没测过的 `xhigh` 档给出了最好的实现。
盲评 3 题里有 1 题算法、1 题架构，与「日常多文件实现 + 改既有代码」的相关性未经验证。

---

## 📎 历史约束（2026-07-28 / 08-02）—— **已被约束 6 白名单完全吸收，仅存档理由**

这三条曾是逐个模型的禁用令，现在白名单已经从正面圈定了可派范围，它们不再需要单独判断：

| 历史条目 | 现状 |
|---|---|
| 07-28「qcn 只准派 Qwen3.8-Max，其余全禁」 | ✅ 与白名单一致；id 已从 `qmodel_preview` 更新为 `qmodel_38max` |
| 08-02「`cb/glm-5.2` 全面禁用」 | ✅ GLM 全系（5.1/5.2/5.3/5v-turbo）都在关闭清单里 |
| 08-02「夜间优先 `qoderclicn`」 | ⛔ **作废**（约束 5）：夜间折扣已取消，前提不存在了 |

**存档理由（判断新模型该不该留时仍可复用这套算法）**：按「盲评总分 ÷ 费率」算性价比，
GLM-5.2 是 101/0.79 = **128**，当时全部可派模型里倒数第二；而 V4-Flash 是 96/0.05 = **1920**。
即一个模型若对比"更强的"和"更省的"两个方向都没有优势，就没有留存价值。
当前白名单内：`flash 1920` · `v4-pro 86/0.13 = 662` · `Qwen3.8-Max 203` · `K3 110.5/1.62 = 68`。
K3 的 68 是全场最低——它留下来是因为**它是白名单内唯一的 S 级**，不是因为划算。

---

## 1. 任务分类

> 链条读法（约束 4 + 6）：**⚡ Hy3 先试 → 命中「做不了清单」才落 V4-Flash → flash 做砸过才升 K3**。
> 标 ⛔ 的行是 Hy3 明确不适用，直接从 V4-Flash 起步。
> ⚠️ 白名单只有 4 个模型（hy3 / v4-flash / v4-pro / k3）+ qcn 的 Qwen3.8-Max，本表不出现其它。

| 代号 | 识别关键词 | 默认模型 |
|---|---|---|
| `core` | 实现/开发/写个/创建服务/迁移 | ⚡ **Hy3**（0.00x）→ V4-Flash（0.05x） |
| `robust` | 防御/容错/边界处理/校验/数据清洗 | ⚡ **Hy3** → V4-Flash（96 分，三题无短板） |
| `test` | 写测试/补测试/异常 case/TDD | ⚡ **Hy3** → V4-Flash |
| `api` | API 设计/DTO/接口定义/给前端用 | ⚡ **Hy3**（契约边界清晰时）→ V4-Flash |
| `doc` | 写文档/更新文档/技术方案/调研报告 | ⚡ **Hy3** → V4-Flash |
| `batch` | 批量改/所有文件/全部替换/10+ 文件 | ⚡ **Hy3** → V4-Flash ⚠️ 大批量先探活，怕中途撞排队 |
| `bugfix` | 报错/坏了/排查/定位根因 | ⚡ **Hy3**（并发诊断 36.5，白名单内最高）→ V4-Flash |
| `kb` | 知识库/KB 整理/文档分类标签 | ⚡ **Hy3** → V4-Flash |
| `review` | review/审核/检查/交叉检查 | 硬例外，不进 Hy3 链、不受白名单约束。⛔ 唯一约束是 **评审族 ≠ 实施族**；⭐ 当前通道：**`pi -p --provider github-copilot --model gpt-5.5`**（§审查通道）；opencode 那条降为兜底 |
| ⛔ `perf` | 性能/优化/O(n)/大数据量 | **V4-Flash** → 做砸升 V4-Pro → 再砸才 K3（Hy3 不适用） |
| ⛔ `algorithm` | 算法/数据结构/精细编码 | **V4-Flash** → 做砸升 V4-Pro（重测 LRU 33 vs 25，升档就升它）→ 再砸才 K3——Hy3 LRU 仅 22 禁用 |
| ⛔ `architecture` | 选型/拓扑/一致性方案/技术方案定稿 | **V4-Flash**（重测 Kafka **34，反超 v4-pro 的 31**）→ 做砸升 V4-Pro → 再砸才 K3——Hy3 `avoidFor: architecture-deep` |
| `concurrency` | 并发/锁/事务/竞态/超卖/幂等 | **诊断**可用 Hy3（36.5）；**写并发原语实现**走 V4-Flash（并发题 32，DB 内核机制到位） |

**多标签冲突裁决**：实现动词（"开发""写"）> 领域关键词（"并发""API"）> 修饰词（"优化""清理"）。取主标签对应的模型。
⚠️ 主标签落在 ⛔ 行时，**不因为「Hy3 免费」而反悔**——那几行是有盲评数据支撑的排除项。
⚠️ 但这三行也**不因为「这类任务 v4-pro 更强」而预先升档**——⛔ 全部先 flash，做砸才升（08-20 用户决策）。

> ⚠️ **⛔ 三行的落点 2026-08-16 从 M3 改成了 V4-Flash**（M3 已被白名单关闭）。
> 直接把它们指向 K3 会违反「不做预防性升档」——K3 是 flash 的 **32 倍**费率，
> 而两组实测（n=1 / n=12）都表明模型档位不是质量关口。
> 但要清楚**这三类确实存在分数差**（LRU：flash 32 vs K3 37；arch：flash 32 vs K3 39），
> 任务明确吃算法/架构深度时，直接 `--model k3` 是合理的，不必先让 flash 做砸一轮。

---

## 2. 模型选择（按优先级）

### 决策优先级（从高到低，不可跳级）

```
P0  ⛔ Provider 白名单（约束 6）          → 不在白名单的 model id 一律不派，先过这一关
     cb: hy3 / deepseek-v4-flash / deepseek-v4-pro / kimi-k3-2 ‖ qcn: qmodel_38max
P1  用户显式 --model/--provider         → 直接用，不覆盖（但仍受 P0 白名单约束）
P2  安全/审查硬例外                      → review → pi -p + github-copilot/gpt-5.5（不受 P0 约束）
     ⛔ Copilot 仅审查不做开发；约束是「评审族 ≠ 实施族」，不是钦定某模型
P3  ⚠️ Claude 模型可派发但不推荐         → 消耗订阅额度，建议留给主会话
P4  运行环境约束                         → --hub 时确认 provider 在 Hub 可用
P5  限免活动（Hy3 优先，约束 4）         → Hy3 0.00x 至 2026-08-31，能做的活一律先给它
     ⛔ 排除清单（唯一真源是约束 4 第 3 条表）：
       a) 图像/视频/多模态 → Hy3 会切多模态模型并【正常计费】，免费不成立
       b) 当日免费额度耗尽进排队 → 长任务先探活；撞排队按 §4 降级
       c) algorithm 算法 / 精细数据结构实现 → 盲评 LRU 仅 22 分
       d) perf 性能优化
       e) architecture 架构深度设计 → avoidFor: architecture-deep
       f) Hy3 已在这个任务上做砸过一轮
     ⇒ c/d/e 三条落 **V4-Flash**（不是直接 K3，见 §1 表下方说明）；a/b/f 也落 V4-Flash
P5.4 ✅ K3 已于 2026-08-16 恢复启用（用户决定），作为极致档 / 唯一升档目标。
     ⚠️ 0723 观察到的现象（反复空转、报进度就 idle、git 无产出）保留为**已知风险**：
     派 K3 后要核 git 产出，别只看它报进度。原「弃用、改派 M3」的结论已失效——M3 也已关闭
~~P6  时段策略~~                          ⛔ **2026-08-16 整条废止（约束 5）**：
     qcn 限时1折结束，全平台已无任何时段性折扣，派发链 24 小时不变，不再判断 is_night()
P7  任务类型 → 模型映射                  → 见 §1 表格
P8  成本优化                             → 同模型多 provider 时选最便宜的
P9  Provider 降级                        → 见 §4
```

### 可派发模型速查（盲评数据 + 费率）

> 盲评三道题：LRU Cache / 并发 Bug 诊断 / Kafka 架构设计（各 /40，合计 /120）。
> GPT-5.5 匿名盲评，2026-06-28（首轮 9 模型）/ 2026-07-20（补评 5 模型，统一 GPT-5.5 口径）。

#### ✅ 白名单内（这五个才是能派的）

| 模型 | Tier | 总分 | LRU | Bug | Kafka | model id | 费率 | 何时选 |
|---|---|---|---|---|---|---|---|---|
| ⚡ Hy3 | B | 91.5* | 22 | **36.5** | 33 | `cb/hy3` | **0.00x 限免至 2026-08-31** | **⭐ 第一顺位（约束 4）**：纯文本/代码 + 非算法 + 非架构。thinking 用 `high`，⛔ 不升 max。⚠️ LRU 22 是唯一明显短板 |
| **V4-Flash** | **A** | **96** | **32** | **32** | **32** | **`cb/deepseek-v4-flash`** | **0.05x** | **⭐ 默认落点（约束 4-1）**：Hy3 被排除/排队时接手。三题全 32 无短板。thinking 用 `xhigh` |
| K3 | **S** | **110.5** | **37** | 34.5 | **39** | `cb/kimi-k3-2` | **🔴 1.62x** | **⛔ 不得随意使用**（约束 6 §K3 使用红线）。只在「用户显式 `--model k3`」或「**v4-pro 也已做砸过一轮**」时派。性价比 68 全场最低，贵 flash **32 倍**；且有 0723 空转前科——派完必须核 `git log` |
| **V4-Pro** | **A** | **96**\*\* | **33**\*\* | 32\*\* | 31\*\* | `cb/deepseek-v4-pro` | 0.13x | **flash 与 K3 之间的唯一中间档**。08-16 重测同轮 96 > flash 89、LRU 领先 8 分 ⇒ **升档时升它，不要跳 K3**。⛔ 但不作任何类型的默认落点——先 flash，做砸才升（08-20 用户决策） |
| Qwen3.8-Max | A | 101.5 | 33 | 34 | 34.5 | `qcn/qmodel_38max` | **0.50x** | **仅作 cb 断供时的降级落点**。1折活动已结束（原 0.05x/0.01x夜），比 flash 贵 10 倍 |

> **\*\*** V4-Pro 这一行的分数**不是**历史 3 题盲评（那是 2026-06-28 旧版本的 86 分），
> 而是 **2026-08-16 正式版重测**的结果。⚠️ 该轮 LRU/Kafka 用的是**重建 prompt**（历史只存档了并发题），
> 所以这四个数字**只能与同轮的 flash（89 / 25 / 30 / 34）比，不能与本表其它模型的历史分横向比**。
> 详见上方 §V4-Pro 重测。同理，flash 那一行仍是它 07-30 的历史分（96），与本轮的 89 不是同一批 prompt。

不受白名单约束的两个通道：`opencode --pure -m github-copilot/gpt-5.5`（审查硬例外，走 copilot 订阅）、
`claude`（⚠️ 可派不推荐，消耗 Claude 订阅额度，建议留主会话）。

#### ⛔ 已关闭（保留盲评数据供将来重新开启时判断，**不得派发**）

| 模型 | Tier | 总分 | 原 provider | 原费率 | 关闭原因 |
|---|---|---|---|---|---|
| M3 | S | **114** | cb/minimax-m3 | 0.25x | 2026-08-16 白名单关闭。⚠️ 它是全场最高分且性价比 456，**关掉它等于升档链断了中间一档** |
| GLM-5.2 | A | 101 | cb + qcn | 0.79x | 08-02 禁用（性价比 128 倒数第二）→ 08-16 并入关闭清单 |
| K2.7-Code | B | 94 | cb/kimi-k2.7 | 0.57x | 08-16 白名单关闭 |
| Qwen3.7-Max | B | 90 | qcn/qmodel_latest | 0.50x | 07-28 起 qcn 白名单外 |
| K2.6 | B | 82 | cb/kimi-k2.6 | 0.52x | 08-16 白名单关闭 |
| Qwen3.7-Plus | C | 76 | qcn/qmodel | 0.10x | 07-28 起 qcn 白名单外 |
| Sonnet 4.6 | C | 77 | claude | 订阅制 | 未评测/不推荐派发（消耗 Claude 额度） |

> 未参加过盲评、本次一并关闭的新增型号：`cb/glm-5.3` `cb/glm-5.1` `cb/glm-5v-turbo` `cb/minimax-m2.7`
> `qcn/q36fmodel`(Qwen3.6-Flash) `qcn/dfmodel` `qcn/dmodel` `qcn/gmodel` `qcn/mmodel` `qcn/kmodel` `qcn/auto`。

> **\* Hy3 的 91.5 是在 `thinking=high` 下测的。2026-07-20 补测 `thinking=max`（同评委 GPT-5.5，LRU/Kafka 两题逐字同题，并发题因原 prompt 未存档改用重建版仅供方向参考），单次结果被质疑样本量不足后又复测一轮：**
>
> | thinking | LRU | 并发* | Kafka | 总分 |
> |---|---|---|---|---|
> | high（原始，单次） | 22 | 36.5 | 33 | **91.5** |
> | max Run1 | 16 | 31* | 36 | **83** |
> | max Run2 | 26 | 27* | 35 | **88** |
> | max 均值 | 21 | 29* | 35.5 | **85.5** |
>
> **结论：max 均值总分（85.5）仍低于 high（91.5），单次测的方向对但幅度有噪声（-8.5 → 均值 -6）。不建议默认给 Hy3 开 max。**
>
> 更细致的发现——**LRU 题两次都因过度设计并发原语翻车，但每次是不同的具体 bug**：Run1 是给声明为同步返回值的 API 套了 async Mutex，实际返回 Promise，类型不自洽、TS 编译不过；Run2 把整个 API 改成全 async（类型倒是自洽了），但容量淘汰路径里对同一个链表节点连续调用两次 detach（`popTail()` 内一次 + `removeEntry()` 内一次），把 LRU 链表状态搞坏。两次根因相同：JS 单线程 run-to-completion 本就让同步方法天然线程安全（历史上其它模型都是这么处理的），Hy3 在 max 下反而"想多了"主动加不必要的并发机制，两次都因这层复杂度出问题——**这是可复现的系统性弱点，不是运行波动**。
>
> Kafka 架构题两次都稳定高于 high（36、35 vs 33），说明 max 对**架构/方案设计类任务确有正向收益**。
>
> **实践结论**：默认保持 `thinking: high`；仅当任务明确是架构/方案设计（不涉及具体数据结构或并发原语实现）且用户能接受更高延迟时，可考虑 max；涉及数据结构实现、并发控制这类任务，max 反而更容易因过度设计而引入新 bug，不要升级。
> 同理，其它模型的盲评分数也都是特定 thinking 档下的结果，跨档比较无意义。

**⚠️ Claude 模型（可派发但不推荐，消耗订阅额度建议留给主会话）**：

| 模型 | Tier | 总分 | LRU | Bug | Kafka | 何时选 |
|---|---|---|---|---|---|---|
| ⚠️ Sonnet 5 | S | 112 | 36 | 36 | 40 | 用户显式要求 / 需要 Outbox 级架构深度 |
| ⚠️ Opus 4.6 | A | 97 | 34.5 | 28 | 34.5 | 用户显式要求 / 重文档 >500 行 |
| ⚠️ Sonnet 4.6 | C | 77 | 35 | 22 | 20 | Agent tool 并发编排（主会话内更合适） |

> 每次派发都消耗 Claude 团队订阅额度。优先用 codebuddy/qoderclicn 的模型，Claude 仅在用户明确要求时派发。

### Thinking 强度建议

⚠️ codebuddy 全系实际档位是 **7 档**：`minimal / low / medium / high / xhigh / max / enabled`。
本表 2026-08-02 前**漏了 `xhigh`**（用户指出），且当时所有 blindEval 分数都是 `high` 跑的。

| thinking | 适用场景 | 示例 |
|---|---|---|
| `minimal` / `low` | 单行 typo、配置修改 | 不建议开 agent，直接做 |
| `medium` | 简单功能、常规 bug fix | 单文件改动 |
| `high` | 边界清晰的机械活、文档 | 保守选择 |
| **`xhigh`** | **多文件功能、服务设计、写实现代码** | **默认**（见下方实测依据，⚠️ n=1） |
| `max` | **纯架构/方案设计，不写实现代码** | 重大决策、选型对比 |

⛔ **写实现代码不要用 `max`** —— 两组独立实测都显示它在实现类任务上更差：

```
hy3      catalog blindEvalAtThinking：high 91.5 → max 85.5（2 次复测均值）
         机制：lru 题两次都过度设计并发原语，各引入一个不同 bug
flash    2026-08-02 五臂同题实测：max 引入【静默数据丢失】
         机制：聚合管道少了 $literal，$ 开头的值被当字段路径解析、键整个消失
```

两次的**共性**是 max 会做出更有野心的设计，而野心带来的新失败面没有被相应的谨慎覆盖。
形式不同（一次是过度抽象，一次是 subtle API 误用 + 未核实前提），后果都是引入新缺陷。

⚠️ **未测量**：thinking 档位不改变 credit 倍率，但会增加 output token 数。
`xhigh` 相对 `high` 的实际 token 开销增幅**没有数据**，不要声称"档位免费"。

---

### 📊 真实任务实测（2026-08-02，n=1，与 3 题盲评不同源）

> 全文与原始证据：`~/wb/docs/technical/模型AB评测-v4flash与m3-20260802.md`
> ⚠️ **置信度低于 blindEval**：单任务、每格单次运行。blindEval 是 3 题、部分格子有复测。
> 用它调默认值可以，但**不要当成推翻盲评的依据**。

方法：同一道真实缺陷（CRM merge 丢 intake payload）派 5 个臂，隔离 worktree、
任务书逐字相同、互不知情。评判标准派发前写定。判据由主会话逐条实测，不采信 agent 自述。

| 臂 | 模型@档位 | credit | 写入机制 | 并发原子 | `$` 前缀值 | 回头客更新 |
|---|---|---|---|---|---|---|
| A | flash@high | 0.06 | filter 条件写入 | ✅ | ✅ | ❌ 整体不回填 |
| B | hy3@high | 0.00 | read-then-`$set` | ❌ | ✅ | ✅ |
| C | flash@**max** | 0.06 | 聚合管道裸对象 | ✅ | ❌ **静默丢键** | ⚠️ |
| D | m3@high | 0.25 | 同 A | ✅ | ✅ | ❌ |
| E | flash@**xhigh** | 0.06 | 管道 + **`$literal`** | ✅ | ✅ | ⚠️ |

**三条结论**：

1. **m3(0.25x) 的 4 倍成本买到零差异** —— D 与 A 收敛到同一方案（同策略、同 filter 写法、
   同参数扩展、同理由，连注释结构都相似；生产代码 44 vs 37 行）。
   ⇒ 主力开发从 `cb/minimax-m3` 改为 **`cb/deepseek-v4-flash@xhigh`**。
2. **xhigh 是三档里唯一同时拿到原子性与 `$` 安全的**（见上方 Thinking 强度建议）。
3. **免费的 hy3 抓到了 flash@max 踩的坑** —— B 主动避开管道并写了 `budget:'$1500'` 当探针。
   ⇒ 限免期内机械性、边界清晰的活优先 `cb/hy3`。

**难点区分度的位置**：五臂**全部**发现了任务里那条隐藏路径（25 分项满分）。
区分度不在「能不能发现问题」，在「写入机制对不对」。
⇒ 设计任务书时，光靠「能不能发现隐藏难点」可能区分不出模型档次，要看落地质量。

---

## 3. 时段策略 ⛔ **已废止（2026-08-16）**

**credits 制通道（codebuddy / qoderclicn）现在没有任何时段性折扣。** 派发链 24 小时不变：

```
⚡ cb/hy3@high (0.00x) → cb/deepseek-v4-flash@xhigh (0.05x) → cb/deepseek-v4-pro@xhigh (0.13x) → cb/kimi-k3-2@xhigh (1.62x)
```

qcn「限时1折」结束后费率回到 0.50x 基准价（原 0.05x 日 / 0.01x 夜），`is_night()` 判断已从决策树删除。
历史费率存档：Qwen3.8-Max 0.05x/0.01x夜 · Qwen3.7-Max 0.25x/0.10x夜 · Qwen3.7-Plus 0.10x/0.04x夜——
这三个现在都在白名单外或已回到基准价，仅供将来再出类似活动时对照。

**限免结束后（08-31 之后）**：cb 默认落点仍是 V4-Flash 0.05x；Hy3 恢复费率待定，届时按实际费率重新排序。

> ⚠️ **下面这一节讲的是 opencode 官方 DeepSeek 的峰谷定价，那是 DeepSeek 自己的 API 计价规则，
> 与 qcn 的时段折扣是两回事，仍然有效，不受本节废止影响。**

### ⚠️ opencode 官方 DeepSeek 的定位（自费 + 峰谷定价）

**这是两个不同的钱包，先分清**：

| 通道 | 计价 | 花谁的钱 |
|---|---|---|
| `cb/deepseek-v4-flash`（Paseo 派发） | **x0.05 credits** | codebuddy **订阅额度**（已付费，边际成本≈0） |
| ~~`deepseek/deepseek-v4-flash`~~（🔴 已 disable） | ~~官方 API 按 token~~ | ~~用户现金~~ |

**同一个模型、同样能力（96 分），但计费渠道完全不同。核心原则：先花已付费的订阅额度，再花现金。**

官方 API 价格（USD / 1M tokens，低谷价；高峰 ×2）：

| 模型 | Input(cache hit) | Input(cache miss) | Output |
|---|---|---|---|
| v4-flash | $0.0028 | $0.14 | $0.28 |
| v4-pro | $0.003625 | $0.435 | $0.87 |

**峰谷时段（北京时间）**：

```
高峰 ×2  ████████ 09:00-12:00      ████████████ 14:00-18:00
低谷 ×1  ─────────────── 18:00 ──→ 次日 09:00 ───────────────  +  12:00-14:00
```

**路由规则（按优先级）**：

1. **默认不走 opencode 官方 DeepSeek** —— 同模型的 `cb/deepseek-v4-flash` 只消耗订阅额度，不花现金，优先用它
   🔴 **2026-08-16 起本节整体降级**：`volcengine-agent-plan` 按月套餐提供同样的 v4-flash/v4-pro 且**不花现金**，
   官方 API 只剩「volcengine 套餐耗尽」时的兜底。下面的峰谷分析仍然正确，但用得上的场景已经很少（见约束 7）
2. **高峰时段（09-12 / 14-18）绝对避免** —— 2 倍价，此时用 `cb/hy3`（限免 0.00x）或 `cb/deepseek-v4-flash`
3. ~~**夜间 22:00-08:00 优先 qcn**~~ ⛔ **2026-08-16 作废**：qcn 夜间折扣取消、费率回到 0.50x，
   它已经不比官方 DeepSeek 划算，也不再是任何时段的首选。限免期内第一顺位始终是 **Hy3 0.00x**
4. **官方 DeepSeek 真正的价值窗口**（qcn 退场后**变宽了**）：
   - **18:00 – 次日 09:00 全段 + 12:00-14:00** —— DeepSeek 低谷价（×1）。原先 22:00 后要让位给
     qcn 的 0.01x，现在 qcn 是 0.50x，这段低谷全部归官方 DeepSeek
   - **codebuddy 额度耗尽时的兜底**（同模型无缝切换，只是换成花现金）
   - **需要 opencode --pure 链路的场景**（如 `agent-review-protocol` 的审查通道，但审查本身首选 GPT-5.5）
   ⚠️ 但顺序仍是「**先花订阅额度**」：只要 `cb/hy3`（0.00x）或 `cb/deepseek-v4-flash`（0.05x）还能派，就不要动现金
5. **cache hit 极便宜（$0.0028，比 miss 便宜 50 倍）** —— 若同一份大上下文要反复问，官方 API 的 prompt cache 反而比 credits 制更划算，这是它的第二个价值点

**反模式**：把 opencode 官方 DeepSeek 当默认派发目标——等于在 codebuddy 订阅额度没用完的情况下额外花现金，且高峰时段还要多付一倍。

### 限免活动

```
⚡ Hy3 限免期（07-06 至 2026-08-31）：
  model ID: hy3（hy3-preview 已下架）
  费率: 0.00x（完全免费）
  provider: codebuddy-code
  策略: 全天候第一顺位（约束 4-2），不消耗任何额度；命中「做不了清单」才降 v4-flash
  延期史: 原定 ~07-20 → 07-22 → 08-05 → 08-31（官方 08-02 公告，已连续延 3 次）
          2026-08-12 用户再次确认活动延续、截止仍为 08-31
          ⚠️ 已连延 3 次不代表会有第 4 次，08-31 前必须留好切换预案（落点：cb/deepseek-v4-flash 0.05x）

⛔ Qwen3.8-Max 限时1折（07-19 起）—— 2026-08-16 已确认结束：
  model ID: qmodel_38max（原 qmodel_preview 已不存在）
  费率: 0.05x日/0.01x夜  →  实测已回到 0.50x 基准价（无日夜之分）
  provider: qoderclicn
  策略: 降为 cb 断供时的降级落点，不再主动选（比 flash 贵 10 倍）

限免期结束后（Hy3 08-31）：
  cb 侧默认落点仍是 V4-Flash 0.05x；Hy3 恢复费率待定，届时按实际费率重新排序
```

#### ⚠️ Hy3 限免的两个附加条件（官方 2026-08-02 公告补充，直接影响派发决策）

**1. Hy3 不具备多模态能力 —— 图像/视频类任务免费不成立**

官方原文：Hy3 是大语言模型，暂不具备多模态能力；调用它执行视频、图像等生成任务时，
**会切换到相应多模态模型完成，因此按正常规则产生积分消耗**。

⇒ **「派 Hy3 = 零成本」只在纯文本 / 代码任务下成立。** 任务一旦涉及图像、视频、
多模态理解或生成，实际跑的是别的模型且照常计费，此时选 Hy3 既没有省钱、
也拿不到 Hy3 的能力特征——应当直接按任务需要选模型，不要因为"Hy3 免费"而派它。

**2. 每日免费额度有限 —— 高峰期会排队**

官方原文：因参与热度高，对每日免费额度做了合理分配；当日资源繁忙时会进入排队，
页面会提示重置时间。

⇒ 派发风险：**长任务派进排队通道可能卡住**，且 Paseo 侧未必立刻可见。
建议沿用 §4 的探活纪律——不确定当日额度状态时，先发一个极短任务确认能立即返回，
再派长任务。撞上排队时按 §4 降级链走 `cb/deepseek-v4-flash`（0.05x）。

**3. 官方推荐错峰窗口：每晚 23:00 – 次日 08:00 资源更充足**

这条**不是费率优惠，是排队概率**——Hy3 全天都是 0.00x，只是这个窗口内更不容易撞排队。
原先本节要和 qcn 的夜间折扣做权衡，qcn 折扣取消后**权衡消失了**，规则简化成一句：

| 时段 | 该派谁 |
|---|---|
| 23:00 – 08:00 | **Hy3**（官方称资源充足，排队风险最低，真 0 消耗） |
| 其余时段 | **Hy3**，但探活不秒回就直接落 `cb/deepseek-v4-flash`（0.05x） |

⛔ 落 flash 时**只替换默认落点**：`algorithm` / `perf` / `architecture` 若已按需要升到 K3，不得因为"换便宜的"把它降回来。

---

## 4. Provider 路由 + 降级

### Provider 类型

| Provider | 调用方式 | Permission mode |
|---|---|---|
| codebuddy-code (cb) | Paseo create_agent | bypassPermissions |
| qoderclicn (qcn) | Paseo create_agent | bypassPermissions |
| ⭐ **volcengine-coding** | `opencode run --pure -m "volcengine-coding/<model>" [--variant off\|on]` | — ⭐ **opencode 通道首选**（Coding Plan，独立额度，7 模型）|
| **volcengine-agent-plan** | `opencode run --pure -m "volcengine-agent-plan/<model>"` | — 次选：只为 Coding Plan 没有的 5 个模型（⚠️ `--variant` 静默失效）|
| **pi (github-copilot)** | `pi -p --provider github-copilot --model gpt-5.5` | — ⭐ **审查主通道**：满足「评审族 ≠ 实施族」，2026-08-20 实测 33s |
| opencode (github-copilot) | `opencode run --pure -m "github-copilot/gpt-5.5"` | — 🔻 同款模型的兜底通道 |
| ~~**deepseek**（opencode 内）~~ | ~~`opencode run --pure -m "deepseek/<model>"`~~ | 🔴 **2026-08-20 已 disable，不可用** |
| **volcengine-chat** | `opencode run --pure -m "volcengine-chat/<model>" --variant off\|on` | — 需要控思考强度时用（3 模型）|
| claude | Paseo create_agent | auto |
| codex | Paseo create_agent | auto |

> **⛔ scnet / xfyun 已于 2026-07-30 移除**（额度耗尽），opencode.json 中 provider 配置已删，Mac + Hub 双端同步。原走 scnet 的模型改走 cb 版本；MiMo-V2.5-Pro 为 scnet 独占，随之下架。
> **deepseek** 曾是 opencode 内置 provider（key 在 `~/.local/share/opencode/auth.json`）。🔴 **2026-08-20 用户已把它加入 `disabled_providers`，四个模型全部不可用**——它**不再是任何降级链的兜底**。套餐耗尽改用 `github-copilot/*` 或 `opencode/deepseek-v4-flash-free`（免费额度）。
> **三个火山 provider 均配置在 `~/.config/opencode/opencode.json`**（明文 key，该目录非 git 仓、不同步；dotfiles 模板用 `${VOLCENGINE_*_APIKEY}` 占位）。
> ⭐ **`volcengine-coding`（Coding Plan，7 模型）是 opencode 首选**——额度独立、`--variant off/on` 可用、deepseek 两兄弟同为 1,024,000 context。
> `volcengine-agent-plan`（12 模型）只在需要它独有的 5 个模型时用；`volcengine-chat`（3 模型）只在需消耗 Agent Plan 额度且要控思考强度时用。

### 白名单内的费率对比（实测 2026-08-16 `paseo list_models`）

| 模型 | cb 费率 | qcn 费率 | 官方 API | 选哪个 |
|---|---|---|---|---|
| **Hy3** | **0.00x** | — | — | ⚡ **第一顺位**（cb 独占，限免至 08-31）|
| **V4-Flash** | **0.05x** | ⛔ `dfmodel` 白名单外 | 自费（峰谷） | ⭐ **cb 默认落点**（订阅额度，不花现金）|
| **V4-Pro** | **0.13x** | ⛔ `dmodel` 白名单外 | 自费 | **升档档位**：flash 做砸才用，flash 与 K3 之间的唯一中间档 |
| **K3** | **1.62x** | — | — | 极致档，cb 独占（白名单内唯一 S 级）|
| Qwen3.8-Max | — | **0.50x** | — | qcn 独占，**仅作 cb 断供降级落点**（1折已结束）|

> cb 的 credits 与官方 API 的 token 计费不可直接比倍率——前者花订阅额度，后者花现金。见 §3 峰谷段。
> ⚠️ 同一个模型在 qcn 上通常更贵（V4-Flash: cb 0.05x vs qcn 0.10x），且 qcn 侧已被白名单关闭，不必比较。

> **qoderclicn** Credits 制。**2026-07-27 晚已更换新账号，恢复可用**（此前旧账号额度耗尽，报 `FORBIDDEN code:112` + pricing 链接）。
> **scnet** 2026-07-27 已耗尽，v8.2 起已从 provider 列表移除。**codebuddy Hy3** 限免 0.00x 仍可用，**thinking 用默认 `high`，不要开 max**（此处原写"必须开 max"，已被 v8.3/v8.4 两轮盲评证伪——见上方 §2 对比表：max 均值 85.5 < high 91.5，且 LRU 类实现题两轮都因过度加并发原语翻车）。
> ⚠️ 派发前若不确定某 provider 是否还有额度，先发一个极短任务探活，别把长任务派进已断供的通道——今天因此中断过 3 个 agent。

### 降级链

```
Provider 不可用或限额？按以下顺序降级：

⛔ 降级目标必须仍在白名单内（约束 6）。缺替代时报告用户，不得擅自开白名单外的模型。

codebuddy 限额
  ├─ Hy3 → cb/deepseek-v4-flash
  │        ⚠️ 触发条件不止「限额」：**免费额度耗尽 / 探活未秒回（排队）/ 命中约束 4-3 清单**
  │        都走这条。派长任务前先发一条极短 prompt 探活，别把长任务丢进排队通道
  ├─ V4-Flash → ① qcn/qmodel_38max（0.50x，仍走订阅额度，贵 10 倍但不花现金）
  │             ② volcengine-agent-plan/deepseek-v4-flash（同模型，走火山按月套餐，不花现金）
  │                ⚠️ 这是 opencode --pure 一次性文本调用，不是能改代码的 Paseo 子会话
  │                （原为 deepseek/* 官方 API 自费，2026-08-20 已 disable）
  │             ③ cb/deepseek-v4-pro（同族，若只是 flash 单模型异常而非 cb 整体限额）
  ├─ K3 → 无替代（白名单内唯一 S 级，M3 已关闭），报告用户
  │        ⚠️ 这是 M3 关闭后新出现的单点：以前 K3 撞限额还能退到 M3，现在退无可退
  └─ V4-Pro → volcengine-agent-plan/deepseek-v4-pro（火山套餐；同为 --pure 文本调用，非 Paseo）

qoderclicn 限额或 refresh timeout
  ├─ 先重试 1 次（等 5-10 秒）
  └─ Qwen3.8-Max → cb/hy3（限免期）或 cb/deepseek-v4-flash
     ⛔ 不得降级到同 qcn 下其他型号（白名单只有 qmodel_38max）

cb + qcn 都限额
  └─ volcengine-agent-plan/deepseek-v4-flash（火山套餐）→ 仍不行才报告用户建议 claude/sonnet（主会话内）
```

> qoderclicn 的 `Timed out refreshing Qoder CLI CN after 60000ms` 是 **provider refresh timeout**，不是模型推理超时。先重试再降级。
> 降级时 title 前缀加 `[降级]`，向用户报告原因。
