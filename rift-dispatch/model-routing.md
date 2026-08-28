# Rift Dispatch — 模型路由规则

> **三文件分工**（改任何一处前先确认自己在改哪一层）
>
> | 文件 | 职责 | 什么时候改 |
> |---|---|---|
> | `SKILL.md` | **怎么做** —— 伪代码、命令、prompt 模板、自查表 | 执行方式变了 |
> | **本文件** | **选什么 + 为什么** —— 路由规则、门禁、证据 | 规则或依据变了 |
> | `model-catalog.json` | **数值** —— 费率、盲评分数、provider 映射、机器可读门禁字段 | 实测数据变了 |
> | `CHANGELOG.md` | **历史** —— 已废止规则、旧结论、决策过程 | 每次变更 |
>
> ⛔ 本文件只写**当前生效**的规则。已废止的内容不在这里存档，去 CHANGELOG 查。

---

## 0. 派发链（唯一真源，其它地方出现的链条都以此为准）

```
T0  免费档   cb/hy4-preview @high     0.00x   ⭐ 第一顺位（免费至 09-12）
             cb/hy3         @high     0.00x   次位（免费至 08-31）
              ↓ 命中 §2 排除清单，或免费期已过
T1  低价档   cb/glm-5.3-flash @xhigh  0.06x   付费档里最便宜
              ↓ 上一档在【本任务】做砸过一轮
T2  主力档   cb/deepseek-v4-flash @xhigh  0.17x   DeepSeek 族首选
              ↓ 上一档在【本任务】做砸过一轮
T3  升档     cb/deepseek-v4-pro   @xhigh  0.51x   ⛔ selectableByDefault=false
              ↓ 上一档在【本任务】做砸过一轮
T4  极致档   cb/kimi-k3-2         @xhigh  1.62x   🔴 红线，见 §3.3
```

**每一级向上的唯一入口都是「上一档已在本任务做砸过一轮」。**
⛔ 不做预防性升档——「任务难 / 重要 / 风险高」不是理由，两组实测（n=1、n=12）都推翻了它（§9.2）。
风险高该提的是 **thinking 档位**和**审查强度**，不是模型档位。

⚠️ 任何「换更便宜 provider」的替换**只作用于当前默认落点**，
⛔ 不得把已按需要升上去的档位降回来（2026-08-12 异构审抓到伪代码会无条件冲掉高档模型）。

### 免费档时间线

```
08-31  hy3 免费止   → hy4 顶上（本就是第一顺位）
09-12  hy4 免费止   → 免费档清零，默认落点变成 T1 的 glm-5.3-flash
```

⚠️ **09-12 后不要自动落回 `hy4-preview-x`**：它是 0.29x，比 T2 的 v4-flash 还贵。

### ⚠️ `-x` 后缀：同 label、两个 id、一免费一收费

| id | 费率 | |
|---|---|---|
| `hy4-preview` | **0.00x** | 免费至 09-12 |
| `hy4-preview-x` | **0.29x** | ⚠️ 同名收费版 |
| `hy3` / `hy3-x` | 0.00x / 0.05x | 同一模式 |

🔴 **派发认 id，⛔ 不认 label** —— 两个 id 的 label 都是「Hy4 preview」，按 label 匹配会选错。

---

## 1. Provider 白名单（P0，优先级最高于一切）

**白名单之外的 model id 一律禁止派发**，包括本文件其它表格里出现过的。冲突时以本表为准。

| Provider | model id | 费率 | 角色 |
|---|---|---|---|
| `codebuddy-code` | **`hy4-preview`** | **0.00x** | ⭐ T0 第一顺位（至 09-12） |
| `codebuddy-code` | `hy3` | 0.00x | T0 次位（至 08-31） |
| `codebuddy-code` | **`glm-5.3-flash`** | **0.06x** | T1 低价档（2026-08-28 开启） |
| `codebuddy-code` | `deepseek-v4-flash` | **0.17x** | T2 主力档，DeepSeek 族首选 |
| `codebuddy-code` | `deepseek-v4-pro` | **0.51x** | T3 升档，⛔ 非任何类型的默认落点 |
| `codebuddy-code` | `kimi-k3-2` | **🔴 1.62x** | T4 极致档，⛔ 见 §3.3 红线 |
| `qoderclicn` | `qmodel_38max` | 0.50x | cb 整体断供时的降级落点，不主动选 |

**⛔ cb 已关闭**：`minimax-m3` · `minimax-m3-pay` · `minimax-m2.7` · `glm-5.3` · `glm-5.2` · `glm-5.1`
· `glm-5v-turbo` · `kimi-k2.7` · `kimi-k2.6` · `hy4-preview-x` · `hy3-x`
**⛔ qcn 已关闭**：`qmodel_38max` 以外全部

**不受白名单约束的通道**（走别的钱包，不消耗 cb/qcn credits）：

| 通道 | 说明 |
|---|---|
| `pi/volcengine-coding/*` · `pi/volcengine-agent-plan/*` | 火山按月套餐，§7 |
| `pi -p --provider github-copilot` | 审查硬例外，§5 |
| `claude/*` | ⚠️ 可派但不推荐——消耗 Claude 订阅额度，建议留给主会话 |
| `codex/*` | Paseo 派发 provider，定位不变 |
| `opencode run --pure` | 🔻 兜底，无常规用途，§7 |
| ~~`deepseek/*`（官方 API）~~ | 🔴 2026-08-20 已加入 `disabled_providers`，不可用 |

---

## 2. 免费档排除清单（唯一真源）

命中任意一条 → 跳过 T0，直接从 T1 起步。

| 条件 | 代号 | 依据 |
|---|---|---|
| 图像 / 视频 / 多模态 | — | 官方 0802 公告：会切多模态模型并**正常计费**，免费不成立 |
| 当日免费额度耗尽 / 探活未秒回（排队） | — | 官方 0802 公告：繁忙进排队，长任务会卡住 |
| 算法 / 精细数据结构实现 | `algorithm` | hy3 盲评 LRU **22 分**，唯一明显短板 |
| 性能优化 / 大数据量 | `perf` | hy3 无 perf 类实测支撑 |
| 架构深度设计（选型 / 拓扑 / 一致性方案） | `architecture` | catalog `avoidFor: architecture-deep` |
| 免费档已在本任务做砸过一轮 | — | 同升档逻辑 |

⛔ **本表与 §6 任务分类表中标 ⛔ 的行必须一一对应**，改一边要同步另一边。
2026-08-12 异构审抓到过一次漏判：表里写着不适用、清单里查不到，实际派了出去。

### ⚠️ 这份清单是给 Hy3 定的，对 Hy4 未验证

Hy4 的 LRU 拿了 **35 分**（hy3 只有 23），说明「algorithm 是短板」这条对它**很可能不成立**。
在补测之前 Hy4 沿用本清单属于保守处理，可能低估了它。

### ⚠️ 反过来讲，不要因为免费就绕开它

**Hy3 的 bug 诊断盲评 36.5**（07-20 轮），当时是白名单内最高。
`core` / `test` / `batch` / `robust` / `doc` / `kb` / bugfix 这些类型不要因为它挂 B 级就跳过。

🔴 ⚠️ **但这个 36.5 已经被自家同题数据打折**：08-21 逐字同题复测里 hy3 并发只拿 **29**，
是三臂最低（hy4 34 · glm 32）。两个数都是单次，⛔ 按本文件的跨轮纪律不能直接相减，
但也**不能再把 36.5 当 standing 事实给规则承重**。⇒ 现在的处理是：
免费档在 bugfix 类仍可先试（做砸会升档兜底，代价可控），⛔ 但不再宣称它「最强」。

派长任务前**先发一条极短 prompt 探活**——免费额度当日耗尽会进排队，且 Paseo 侧未必立刻可见。

---

## 3. 付费档与升档纪律

### 3.1 T1/T2 的分工：便宜优先，DeepSeek 仍是族偏好

**用户决策（2026-08-16）：DeepSeek 系列是默认工作模型族，族内优先 `deepseek-v4-flash`。**
派发时先问「这活 DeepSeek 能不能做」。

⚠️ 这条决策成立时 `deepseek-v4-flash` 是 **0.05x**，「又强又便宜」两头都占。
2026-08-21 它涨到 **0.17x**，便宜这一头没了——`glm-5.3-flash` 是 0.06x，便宜它 **2.8 倍**。

2026-08-28 头对头补测（§9.1）回答了「那还强不强」：**同口径两题 66 vs 67，打平**。
⇒ **T1 落 `glm-5.3-flash`，T2 落 `deepseek-v4-flash`**。
DeepSeek 的族偏好现在体现为「T1 做砸就升 T2、不跳去别的族」，
⛔ 不再体现为「一上来就用 DeepSeek」。

⚠️ 打平是**总分层面**的，分项**反向分化**——算法/并发 v4-flash 领先，架构 glm 领先 5 分。
所以入口档按任务类型分开定（§6），⛔ 不是一刀切。

⛔ **不要用「总分 ÷ 费率」跨轮算性价比来给模型排序。** 各轮的 prompt 批次与 thinking 档位不同，
分数不同源。唯一可靠的比较是同口径头对头。

### 3.2 🔴 v4-pro 使用门禁

用户 2026-08-21 反馈：**「很多 agent 还是喜欢用 v4-pro，消耗太快」**。
规则早已写在十几处仍拦不住——根因不是规则不够，是**数据在反着劝**：

```
blindEval        v4-flash 96  >  v4-pro 86      ← 支持 flash
sameRoundEval    v4-pro  96  >  v4-flash 89     ← agent 抓这个当理由 ⚠️
```

分数是结构化数据、规则是散文，agent 扫一眼只抓分数。⇒ 改成机器可读门禁：

| catalog 字段 | 值 |
|---|---|
| `selectableByDefault` | **`false`** ← 布尔，比散文难绕过 |
| `dispatchRank` | 8（v4-flash 是 4、glm-5.3-flash 是 3，刻意拉开） |
| `requiresPrecondition` | 上一档已在**本任务**做砸过一轮；**派发理由必须写明哪一轮、砸在哪、为什么升档能解决**。写不出来 ⇒ 不许升 |
| `costMultiplier` | 3.0x vs v4-flash（0.51x vs 0.17x） |

⚠️ **`sameRoundEval` 那组分数的正确读法**：它说的是「**升档时该升 v4-pro，而不是跳 K3**」，
⛔ **不是**「该跳过 flash」。且 flash 在架构题反超（Kafka 34 vs 31）。

### 3.3 🔴 K3 红线

用户 2026-08-16 明确：**很贵很贵，不要随意使用**。

```
cb/kimi-k3-2 = 1.62x  ← 白名单内唯一 1.0x 以上
  vs deepseek-v4-flash 0.17x  → 贵 9.5 倍
  vs glm-5.3-flash     0.06x  → 贵 27 倍
```

⚠️ 旧记录写「性价比 110.5/1.62 = 68，全场最低」——那是**跨轮口径**（分子出自 07-20 轮），
⛔ 按 §3.1 末尾那条纪律不能用它给模型排序，保留仅作量级参照。
**不依赖任何分数也成立的部分是上面的价格倍数。**
它留在白名单里是因为「白名单内唯一 S 级」，⛔ 不是因为划算。

**⛔ 只有这两种情况可以派：**

| 允许 | 说明 |
|---|---|
| ① 用户显式 `--model k3` | 用户自己知道在花什么 |
| ② **v4-pro 也已在本任务做砸过一轮** | 升档的唯一入口 |

**⛔ 以下都不构成理由**（每条都被实测或成本算术否掉）：

- ❌「任务看起来很难 / 很重要 / 风险高」→ 模型档位不是质量关口（§9.2）
- ❌「这是 algorithm / architecture 类，K3 分最高」→ 这两类先走 T2，做砸才升
- ❌「反正只跑一次」→ 一次 K3 ≈ 9.5 次 v4-flash ≈ 27 次 glm-5.3-flash
- ❌「先用好的保险一点」→ 这就是「预防性升档」的原话，明令禁止

⚠️ **可靠性前科**：2026-07-23 实测出现反复空转（报进度就 idle、git 无产出）。
⇒ 派了 K3 **必须核 `git log` 是否真有 commit**，不能只看它报进度。
花 9.5 倍的钱还拿不到产出，是这个模型特有的失败模式。

⚠️ K3 撞限额**没有替代**（M3 已关闭），只能报告用户。这是白名单收窄后的单点。

---

## 4. thinking 档位

| 模型 | 档位 | 依据 |
|---|---|---|
| `hy4-preview` / `hy3` | **`high`** | max 已被两轮盲评证伪（91.5 → 85.5）；xhigh 从未在 Hy 系上测过 |
| 其余付费档 | **`xhigh`** | 2026-08-02 用户决策（原为 high） |

| thinking | 适用 |
|---|---|
| `minimal` / `low` | 单行 typo、配置修改——不建议开 agent，直接做 |
| `medium` | 简单功能、常规 bugfix、单文件改动 |
| `high` | 边界清晰的机械活、文档 |
| **`xhigh`** | **多文件功能、服务设计、写实现代码 —— 付费档默认** |
| `max` | 纯架构 / 方案设计，**不写实现代码** |

### ⛔ 写实现代码不要用 `max`

两组独立实测方向一致：

```
hy3    blindEvalAtThinking：high 91.5 → max 85.5（2 次复测均值）
       机制：LRU 题两次都过度设计并发原语，各引入一个不同 bug
flash  2026-08-02 五臂同题：max 引入【静默数据丢失】
       机制：聚合管道少了 $literal，$ 开头的值被当字段路径解析、键整个消失
```

共性是 max 会做出更有野心的设计，而野心带来的新失败面没有被相应的谨慎覆盖。
Kafka 架构题上 max 两次都高于 high（36、35 vs 33）——**架构/方案设计类确有正向收益**。

⚠️ **未测量**：thinking 档位不改变 credit 倍率，但会增加 output token 数。
`xhigh` 相对 `high` 的实际开销增幅**没有数据**，⛔ 不要声称「档位免费」。

⚠️ 各模型的盲评分数都是特定 thinking 档下的结果，**跨档比较无意义**。

---

## 5. 审查通道：约束是「异构」，不是「禁用某个模型」

**⛔ 硬约束（全局红线 #8）：评审模型族 ≠ 实施模型族。** 这是**不变量**，与具体是哪个模型无关。

当前在用的模型族：**Claude · DeepSeek · Hy(混元) · Kimi · GLM(智谱) · MiniMax · Qwen · 豆包 · GPT · Gemini**

| 本次实施用了 | 评审可以用（任选异族） | 评审不能用 |
|---|---|---|
| 🔴 **主会话自己动手（Claude）** | GPT / DeepSeek / GLM / Gemini / Kimi / Hy … | **Claude 全族** |
| `cb/hy4-preview` · `cb/hy3` | GPT / Claude / DeepSeek / GLM … | Hy 全族 |
| `cb/glm-5.3-flash` | GPT / Claude / DeepSeek / Kimi … | **GLM 全族** |
| `cb/deepseek-v4-flash` · `-pro` | GPT / Claude / GLM / Kimi … | **DeepSeek 全族** |
| `cb/kimi-k3-2` | GPT / Claude / DeepSeek / GLM … | Kimi 全族 |
| `qcn/qmodel_38max` | GPT / Claude / DeepSeek / GLM … | Qwen 全族 |
| `claude/*`（Paseo 派 Claude 子会话） | GPT / DeepSeek / GLM … | **Claude 全族** |

🔴 **第一行最容易被忽略却最常发生**：主会话就是 Claude，凡是**我自己写的代码/文档/配置**，
⛔ 不能派 `claude/*` 子会话来审——那是自审。同理 `github-copilot/claude-*` 也不行。

⇒ ⛔ **不要把它记成「DeepSeek 不许审查」**。实施是 Hy4 或 K3 时，DeepSeek 是完全合格的异构评审。
只因为付费主力档是 `deepseek-v4-flash`，**那一路**的评审才要排除 DeepSeek 族。

### ⭐ 当前审查通道

```bash
pi -p --provider github-copilot --model gpt-5.5 "<≤200 字符的 prompt>"
```

| 约束 | 说明 |
|---|---|
| 🔴 **prompt ≤200 字符** | 背景让模型自己读文件。实测非交互模式下 800 字让 GPT-5.5 挂 22 分钟，短 prompt 秒回 |
| ⛔ **撞超时不要收窄 prompt 重试** | 极小 prompt 也会超时的情况另有根因，换通道 |
| ⛔ **Copilot 仅审查，不做开发** | 用户 2026-08-20 明确。开发走 §7 火山通道 |
| ⛔ 不用 `codex/gpt-5.6-sol` | 实测该 workspace `out of credits` |

Copilot 侧可用的异族评审（以 `~/.pi/agent/models-store.json` 为准）：
`gpt-5.5`(⭐默认) · `gpt-5.6-sol` · `gpt-5.6-luna` · `gpt-5.6-terra` · `gpt-5.4` · `gpt-5.3-codex`
· `gpt-5.4-mini` · `gpt-5-mini` · `gemini-3.1-pro-preview` · `gemini-3.5-flash` · `gemini-3.6-flash`
⚠️ 同一 store 里还有 `claude-*` 全系——**属 Claude 族，审主会话产出时不可用**。

### 为什么审查不跟着「DeepSeek 优先」走

约束已把实施侧定成 DeepSeek，评审若也换成 `volcengine-*/deepseek-*`，
就是 **DeepSeek 审 DeepSeek**，异构审查直接失效。
2026-08-12 与 08-16 两轮异构审共抓到 13 处问题，**全部来自「换一个模型族去看」**。

⇒ 「opencode/pi 优先火山 DeepSeek」的适用范围是**实施类 / 问答类**；审查类是硬例外。

---

## 6. 任务分类 → 落点

链条读法：**T0 免费档先试 → 命中 §2 排除清单则跳过 T0 → 从下表的起步档进 → 做砸一轮才升下一档。**
标 ⛔ 的行是免费档明确不适用；⚠️ **它们的付费起步档不一样**，见下方拆分表。

| 代号 | 识别关键词 | 落点 |
|---|---|---|
| `core` | 实现/开发/写个/创建服务/迁移 | T0 → T1 |
| `robust` | 防御/容错/边界处理/校验/数据清洗 | T0 → T1 |
| `test` | 写测试/补测试/异常 case/TDD | T0 → T1 |
| `api` | API 设计/DTO/接口定义/给前端用 | T0 → T1 |
| `doc` | 写文档/更新文档/技术方案/调研报告 | T0 → T1 |
| `batch` | 批量改/所有文件/全部替换/10+ 文件 | T0 → T1 ⚠️ 大批量先探活，怕中途撞排队 |
| `bugfix` | 报错/坏了/排查/定位根因 | T0 → T1 ⚠️ hy3 的「并发诊断 36.5 最高」是 07-20 单次，08-21 同题只有 29，见 §2 |
| `kb` | 知识库/KB 整理/文档分类标签 | T0 → T1 |
| `concurrency_diag` | 并发**诊断**：排查竞态/超卖/幂等问题 | T0 → **T2**（⛔ 跳过 T1） |
| `concurrency_impl` | **写**并发原语/锁/事务实现 | T0 → **T2**（⛔ 跳过 T1） |
| ⛔ `perf` | 性能/优化/O(n)/大数据量 | **T2** 起步 |
| ⛔ `algorithm` | 算法/数据结构/精细编码 | **T2** 起步 |
| ⛔ `architecture` | 选型/拓扑/一致性方案/技术方案定稿 | **T1** 起步 ← 🔴 2026-08-28 改（原 T2） |
| `review` | review/审核/检查/交叉检查 | **硬例外**，不进本链、不受白名单约束。唯一约束是 §5 异构 |

### ⛔ 「跳过免费档」和「付费从哪档起步」是两件事

以前混成一件，导致 `architecture` 因为「免费档做不了」被一路推到 T2。拆开后：

| 代号 | 跳过 T0？ | 付费起步档 | 依据 |
|---|---|---|---|
| 默认 | 否 | **T1** glm-5.3-flash | — |
| `algorithm` | ✅ | **T2** v4-flash | hy3 LRU 22 ⇒ 跳 T0；⚠️ 付费起步档**无干净证据**（h2h 的 LRU 格口径不同），取并发题作代理：v4-flash 35 > glm 31 |
| `perf` | ✅ | **T2** v4-flash | ⚠️ 无 perf 实测，按 algorithm 同类保守处理 |
| `architecture` | ✅ | **T1** glm-5.3-flash | hy3 `avoidFor: architecture-deep` ⇒ 跳 T0；🔴 h2h Kafka **glm 36 > v4-flash 31** |
| `concurrency_diag` | 否 | **T2** v4-flash | h2h 并发题 v4-flash 35 > glm 31（同口径） |
| `concurrency_impl` | 否 | **T2** v4-flash | 同上；写实现比诊断更吃精细度 |

🔴 **`architecture` 这条 2026-08-28 改了。** 旧规则写「T2 起步，因为 v4-flash 重测 Kafka 34 反超 v4-pro 的 31」——
那句话说的是 **v4-flash 与 v4-pro** 的关系，⛔ 从头到尾没涉及 glm。
头对头实测后 glm 在这题反超 5 分，所以架构类没有理由跳过更便宜的 T1。

⚠️ **`concurrency` 必须先判子类**再进阶梯——伪代码里 `classify()` 产出的是
`concurrency_diag` / `concurrency_impl`，⛔ 不是裸的 `concurrency`（否则查表落空、退回 T1）。

**多标签冲突裁决**：实现动词（"开发""写"）> 领域关键词（"并发""API"）> 修饰词（"优化""清理"）。

⚠️ 主标签落在 ⛔ 行时，⛔ **不因为「免费档不要钱」而反悔**——那三行是有盲评数据支撑的排除项。
⚠️ 但也 ⛔ **不因为「这类任务 v4-pro 更强」而预先升档**——从 T2 起步，做砸才升。

---

## 7. 通道选择

**命令与参数见 `SKILL.md` §3（唯一真源）。** 本节只给选择判据。

| 任务性质 | 走哪条 | 为什么 |
|---|---|---|
| **开发实施类**（改代码/跑测试/提交） | ⭐ **Paseo `create_agent`** | 你要能看进度、能中途干预、能拿结构化状态 |
| **只读 / 短 / 分析类** | `pi -p` CLI + 火山 provider | 跑完即退，不堆 serve |
| **审查类** | `pi -p` + `github-copilot/gpt-5.5` | §5 异构 + 有额度 |
| **兜底** | `opencode` 🔻 | 无常规用途 |

🔴 **分通道的维度是「要不要看得见」，不是「用哪个工具」。**
pi 有两种启动方式（Paseo 派 pi / `pi -p` 直跑），**跑的是同一个 pi、同一套能力**，
区别只在能不能看见它。⛔ 开发任务不要走 `pi -p`——它不进 Paseo agent 列表，你看不见也打不断。

### 火山两个套餐、三个 provider

Agent Plan 额度不够，2026-08-20 另购 Coding Plan（Pro 套餐，包月至 2026-10-20，自动续费关）。
两个套餐**额度独立、API key 不同**。

| provider | 套餐 | baseURL | 模型数 | `--variant` |
|---|---|---|---|---|
| ⭐ **`volcengine-coding`** | **Coding Plan** | `…/api/coding/v3` | **7** | ✅ `off`/`on` |
| `volcengine-agent-plan` | Agent Plan | `…/api/plan/v3` | 12 | ❌ 静默失效 |
| `volcengine-chat` | Agent Plan（同额度同 key） | `…/api/plan/v3` | 3 | ✅ `off`/`on` |

**Coding Plan 7 个**：`deepseek-v4-flash` · `deepseek-v4-pro` · `glm-5.3` · `minimax-m3`
· `kimi-k2.7-code` · `doubao-seed-2.1-turbo` · `doubao-seed-2.0-lite`
**Agent Plan 独有 5 个**：`ark-code-latest` · `kimi-k3` · `doubao-seed-evolving` · `glm-latest` · `doubao-seed-2.0-mini`

🔴 **baseURL 别写错**：官方明确不要用 `https://ark.cn-beijing.volces.com/api/v3`——**会产生额外费用**。
⛔ Coding Plan 不支持 `auto` 模式（实测 `UnsupportedModel`）。

⚠️ 火山侧那 10 个非 DeepSeek 模型按「不主动选」处理。
其中 `glm-5.3` / `minimax-m3` / `kimi-k2.7-code` 在 cb 侧已被白名单关闭，
但火山是另一个钱包——**是否同样关闭未经用户确认**，在确认前不主动选、也不判违规。

### 🔻 opencode 排最后

用户 2026-08-20 定位卡死根因：**每次 `opencode run --pure` 拉起一个 serve，反复调用则 serve 堆叠吃穿内存**。
⇒ 单次偶发调用本身安全；⛔ **循环里反复 `opencode run` 是危险动作**，改用 `pi -p`。
review 已迁到 `pi -p` + Copilot，opencode 现在没有任何常规用途。

---

## 8. Provider 与降级链

| Provider | 调用方式 | Permission mode |
|---|---|---|
| `codebuddy-code` | Paseo `create_agent` | bypassPermissions |
| `qoderclicn` | Paseo `create_agent` | bypassPermissions |
| `pi/<火山 provider>/<model>` | Paseo `create_agent`（27 模型全暴露） | bypassPermissions |
| `pi -p --provider volcengine-coding` | CLI one-shot | — |
| `pi -p --provider github-copilot` | CLI one-shot | — ⭐ 审查主通道 |
| `claude` | Paseo `create_agent` | auto |
| `codex` | Paseo `create_agent` | auto |
| `opencode run --pure` | CLI 🔻 | — |

### 降级链

⛔ **降级目标必须仍在白名单内。** 缺替代时报告用户，不得擅自开白名单外的模型。

```
codebuddy 限额
  ├─ 免费档(hy4/hy3) → glm-5.3-flash
  │    ⚠️ 触发条件不止「限额」：额度耗尽 / 探活未秒回（排队）/ 命中 §2 清单，都走这条
  ├─ glm-5.3-flash → deepseek-v4-flash
  ├─ deepseek-v4-flash → ① qcn/qmodel_38max（0.50x，仍走订阅额度）
  │                      ② pi/volcengine-coding/deepseek-v4-flash（火山套餐，不动 cb credits）
  │                      ③ cb/deepseek-v4-pro（仅当是 flash 单模型异常而非 cb 整体限额）
  ├─ deepseek-v4-pro → pi/volcengine-coding/deepseek-v4-pro
  └─ kimi-k3-2 → 🔴 无替代（M3 已关闭），报告用户

qoderclicn 限额 / refresh timeout
  ├─ 先重试 1 次（等 5-10 秒）——`Timed out refreshing Qoder CLI CN after 60000ms`
  │  是 provider refresh timeout，不是模型推理超时
  └─ qmodel_38max → cb 免费档 或 cb/glm-5.3-flash
     ⛔ 不得降级到同 qcn 下其它型号（白名单只有 qmodel_38max）

cb + qcn 都限额
  └─ pi/volcengine-coding/deepseek-v4-flash → 仍不行才报告用户
```

降级时 title 前缀加 `[降级]`，向用户报告原因。
⚠️ 派发前若不确定某 provider 是否还有额度，**先发极短任务探活**——
曾因把长任务派进已断供通道，一天中断过 3 个 agent。

---

## 9. 数据

> 完整数值在 `model-catalog.json`。本节只留**能改变决策**的部分。

### 9.1 盲评（三题各 /40，合计 /120；评委 GPT-5.5）

⚠️ **跨轮分数不可横比** —— 不同轮次的 prompt 批次、thinking 档位可能不同。
只有**同轮内**的相对关系严格成立。

**2026-08-21 轮**（thinking=high，题库逐字复用 08-16 存档原题）：

| 题目 | hy4-preview | hy3 | glm-5.3-flash | deepseek-v4-flash |
|---|---|---|---|---|
| LRU（算法） | **35** | 23 | 26 | 见 catalog |
| 并发 Bug 诊断 | **34** | 29 | 32 | 见 catalog |
| Kafka 架构 | **34** | 32 | 33 | 见 catalog |
| **总分 /120** | **103** | 84 | 91 | 未参加 |
| 费率 | 0.00x | 0.00x | 0.06x | 0.17x |

**2026-08-28 头对头**（`glm-5.3-flash` vs `deepseek-v4-flash`，同题、同评委、三题在同一次评分中完成）：

| 题目 | `deepseek-v4-flash` 0.17x | `glm-5.3-flash` 0.06x | |
|---|---|---|---|
| LRU（算法） | **36** | 31 | ⚠️ 见下方口径警告 |
| 并发诊断 | **35** | 31 | 同口径 |
| Kafka 架构 | 31 | **36** | 同口径 |
| **同口径小计 /80** | 66 | **67** | 打平 |

⇒ **同口径打平，而 glm-5.3-flash 便宜 2.8 倍** ⇒ 它作为 T1 付费起点成立。
⇒ **分项反向分化**：算法/并发 v4-flash 强，架构 glm 强 5 分 ⇒ 入口档按类型分开定（§6）。

🔴 **LRU 这一格不是同口径，⛔ 不能当证据**：`deepseek-v4-flash` 在 agent 上下文里
**按 TDD 真建了工程**（352 行实现 + 344 行测试），自己跑了 30/30，还派了一轮交叉审；
另一臂是聊天内作答。这一格对 v4-flash 有利。
⚠️ 这个行为差异本身是有用信息——**派 v4-flash 做实现类任务是优点**，只是做 chat 式盲评时产物不可比。

✅ **方法论自校验**：hy3 本轮 LRU 23 分 vs 2026-07-20 原始盲评 22 分，同题复现一致。

**2026-08-16 轮**（v4-pro 正式版重测）：v4-pro 96 > v4-flash 89，
分项高度分化——**v4-pro 赢在算法/精细实现（LRU 33 vs 25），输在架构（Kafka 31 vs 34）**。
⇒ 正确用法是「升档时升它、不要跳 K3」，⛔ 不是「跳过 flash」。

**历史榜（口径不同，⛔ 仅供量级参照，不构成排名）**：
M3 114 · Sonnet5 112 · K3 110.5 · Qwen3.8-Max 101.5 · Opus4.6 97 · Sonnet4.6 77。

**⚠️ Claude 模型（可派发但不推荐——消耗订阅额度，建议留给主会话）**：

| 模型 | 总分 | 何时选 |
|---|---|---|
| Sonnet 5 | 112 | 用户显式要求 / 需要 Outbox 级架构深度 |
| Opus 4.6 | 97 | 用户显式要求 / 重文档 >500 行 |
| Sonnet 4.6 | 77 | Agent tool 并发编排（主会话内更合适） |

🔴 派 Claude 子会话时注意 §5：**主会话自己写的东西不得用 Claude 族审**。

### 9.2 「高风险 ⇒ 升模型档位」被两组实测推翻

**2026-08-02（n=1）** 五臂同题，任务命中「会自动修改业务数据」这条高风险条件：
`m3@high`（0.25x）与 `flash@high`（0.06x）**收敛到同一方案、零差异**（生产代码 44 vs 37 行）；
`flash@xhigh` 是五个里实现质量最高的；**免费的 hy3 抓到了 flash@max 踩的坑**。

**2026-08-06（n=12，同一天同一批任务）**：flash 做 8 件、m3 做 4 件，**质量看不出差异，m3 贵 4 倍**。
当天最有价值的两个产出都是 flash 做的。同期**十一条阻断全部由异构审抓到、测试零发现**，
且实施者用 flash 还是 m3 与被抓到的阻断数**没有相关性**。

⇒ **质量关口在「审」，不在「作者用什么模型」。**

⚠️ **五臂实测的区分度位置**：五个臂**全部**发现了任务里那条隐藏路径（25 分项满分）。
区分度不在「能不能发现问题」，在「写入机制对不对」。
⇒ 设计任务书时光靠「能不能发现隐藏难点」区分不出模型档次，要看落地质量。

### 9.2b ⛔ 两份证据并摆，不设死权重（2026-08-02 用户决策，仍生效）

> 用户原话：「实测记录到 skill 就好，交给模型自主决策。权重的事情，等数据完善完善再说。」

即：`realTaskEval` 是一份**证据**，盲评分数 + 费率是另一份**证据**，两者都摆出来，
**由派发时的模型自行判断该信哪个**。⛔ 不要写「实测优先于盲评」这类硬规则——实测样本仍是 n=1。

⚠️ 已知的一处冲突（供判断时参考，非结论）：盲评 114 分的 `m3` 与 96 分的 `flash`
在同一道实现题上收敛到同一方案、零差异；而盲评里没测过的 `xhigh` 档给出了最好的实现。
盲评 3 题里 1 题算法、1 题架构，与「日常多文件实现 + 改既有代码」的相关性**未经验证**。

### 9.3 ⭐ 更省的打法

```
低档模型【调查 + 出方案 + 实现】→ 异构模型【只读审查】→ 低档模型【按审查意见修】
```

2026-08-02 实测印证：异构审抓到「blocker 查询漏 trim」「读取侧未复用校验函数」，
并修正了一份验收报告的举证口径。

⚠️ **别只看盲评分数**：hy3 挂 B 级（91.5），但在上下文充分、任务边界清晰、
且要求「先出方案再实现」时，实测表现可以超过分数预期。**看它的中间推理质量再决定要不要换。**

---

## 附录：决策优先级（从高到低，不可跳级）

```
P0  ⛔ Provider 白名单（§1）        不在白名单的 model id 一律不派，先过这一关
P1  用户显式 --model / --provider    直接用（仍受 P0 约束）
P2  审查硬例外（§5）                 review → pi -p + github-copilot/gpt-5.5，不受 P0 约束
P3  ⚠️ Claude 模型可派不推荐         消耗订阅额度，建议留给主会话
P4  运行环境约束                     --hub 时确认 provider 在 Hub 可用
P5  免费档（§0 T0 + §2 排除清单）    hy4-preview → hy3
P6  任务类型 → 落点（§6）
P7  成本优化                         同模型多 provider 时选最便宜的
P8  Provider 降级（§8）
```

⛔ **没有 P「时段策略」这一档。** credits 制通道已无任何时段性折扣（qcn 限时1折 2026-08-16 结束），
派发链 24 小时不变。⚠️ 不要再写 `is_night()` 分支——它曾把按类型选出的高档模型无条件冲掉。
详情见 CHANGELOG v10.0。
