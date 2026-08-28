# Rift Dispatch — 变更记录

## v11.1 (2026-08-28)

用户三条指令：**开启 `glm-5.3-flash`** + **优化决策树** + **补 CHANGELOG 与整体瘦身**。

### ⭐ `glm-5.3-flash` 开启，成为 T1 付费起点

它 08-21 就被发现（0.06x，新费率下最便宜的付费模型），但当时**没有与 `deepseek-v4-flash`
同轮比过** —— 它的 91 分出自 08-21 轮，flash 的 89 分出自 08-16 轮，⛔ 跨轮不可横比。
本轮补测：把 `deepseek-v4-flash` 三题一并跑一遍，与已存档的 glm 产出做**二臂头对头**
（同题、同 `thinking=high`、同评委 `gpt-5.5`、匿名 A/B 位置逐题轮换、三题在同一次评分中完成）。

| 题目 | `deepseek-v4-flash` 0.17x | `glm-5.3-flash` 0.06x | |
|---|---|---|---|
| LRU（算法） | **36** | 31 | ⚠️ 不同口径，见下 |
| 并发诊断 | **35** | 31 | 同口径 |
| Kafka 架构 | 31 | **36** | 同口径 |
| **同口径小计 /80** | 66 | **67** | 打平 |

⇒ **同口径打平，而 glm-5.3-flash 便宜 2.8 倍**，作为 T1 付费起点成立。

🔴 **LRU 那一格不能当证据**：`deepseek-v4-flash` 在 agent 上下文里**按 TDD 真建了工程**
（352 行实现 + 344 行测试），自己跑了 30/30，还派了一轮交叉审；另外三臂是聊天内作答。
这一格对它有利。⚠️ 但这个行为差异本身是有用信息——**派它做实现类任务是优点**，
只是做 chat 式盲评时产物形态不可比。已记进 catalog `models['deepseek-v4-flash'].behaviorNote`。

### 🔴 决策树：把「跳过免费档」和「付费从哪档起步」拆成两件事

这两件事以前混成一件，后果是 `architecture` 因为「免费档做不了」被一路推到 v4-flash。
拆开后按实测重定：

| 代号 | 跳过 T0？ | 付费起步档 | 依据 |
|---|---|---|---|
| 默认 | 否 | **T1** glm-5.3-flash | — |
| `algorithm` | ✅ | **T2** v4-flash | hy3 LRU 22 ⇒ 跳 T0；⚠️ 付费起步档**无干净证据**（LRU 那格不可用），取并发题作最近代理：同口径 v4-flash 35 > glm 31 |
| `perf` | ✅ | **T2** v4-flash | ⚠️ 从来没有 perf 类实测，按 algorithm 同类保守处理 |
| `architecture` | ✅ | **T1** glm-5.3-flash | 🔴 **改了**（原 T2）：头对头 Kafka **glm 36 > v4-flash 31** |
| `concurrency` | 否 | **T2** v4-flash | 诊断类 hy3 36.5 白名单内最高 ⇒ 不跳 T0；实现类头对头 v4-flash 35 > glm 31 |

🔴 **`architecture` 这条为什么之前是错的**：旧依据写「v4-flash 重测 Kafka 34，反超 v4-pro 的 31」——
那句话讲的是 **v4-flash 与 v4-pro** 的关系，⛔ 从头到尾没涉及 glm。
把一个「A 强于 B」的结论当成「A 强于所有更便宜的」用，是这次抓到的推理缺口。

派发链现在是 5 档：

```
T0 hy4-preview 0.00x → hy3 0.00x → T1 glm-5.3-flash 0.06x
   → T2 deepseek-v4-flash 0.17x → T3 deepseek-v4-pro 0.51x → T4 kimi-k3-2 1.62x
```

⛔ 每级上移的唯一入口不变：**上一档已在【本任务】做砸过一轮**。

### 🔴 自查抓到的伪代码 bug：K3 守卫用错了判据

重写阶梯时给 K3 加了守卫 `if i >= 3 and not (… or failed_rounds >= 3): i = 2`。
**用失败次数的绝对值当「v4-pro 也做砸了」的替身是错的**——入口档不同，走到 T4 需要的失败数也不同：

```
core 类       入口 i=0，砸 3 轮 → i=3 → K3      守卫放行 ✓
algorithm 类  入口 i=1，砸 2 轮 → i=3 → K3      守卫看 2>=3 为假 ⇒ 按回 i=2 = v4-pro ✗
                                                 而 v4-pro 正是刚砸掉的那档 ⇒ 原地卡死
```

修法不是把 3 改成别的数，是**去掉守卫**：`i = 入口档 + 砸过的档数`，
所以 **`i` 能走到 3 本身就意味着下面每一档都砸过了**，条件是冗余的。
改成 `min(i, 3)` + 一条兜底断言，并把「同一档重试不计数」写进注释
（否则同档重试两次会把任务一路顶到 K3）。

⚠️ 这个 bug 是**改完自己逐路径验算时**发现的，不是审查发现的——
加了入口档偏移之后，所有以「绝对失败次数」为条件的判断都要重新验，
不能只验默认路径。

### 异构审查抓到的两处（`github-copilot/gemini-3.1-pro-preview`，与实施侧 Claude 异族）

**❌ 白名单可以被绕过。** 伪代码写的是：

```python
if provider in WHITELIST and model not in WHITELIST[provider]:
    report_conflict_and_stop()
```

传一个**不在 `WHITELIST` 键里**的 provider（比如已被 disable 的 `deepseek`），
`provider in WHITELIST` 求值为假，⇒ **整个校验静默跳过、直接放行**。
改成三层依次判：`DISABLED_PROVIDERS` 先拦 → 在 `WHITELIST` 里就校验模型 →
既不在白名单也不在 `EXEMPT_PROVIDERS`（pi/claude/codex/opencode，走别的钱包）的未知 provider 一律停。

⚠️ 这是既有记录里「白名单缺口 = 绕过口」的第三种形状，前两种是「数参数≠检查内容」和「条件性显示=隐藏开关」。

**❌ catalog 自己违反了跨轮比分纪律。** `models['deepseek-v4-flash'].costEffectiveness` 写着
`已被 glm-5.3-flash（91/0.06 = 1517）反超`——flash 的 89 分出自 08-16 轮、glm 的 91 分出自 08-21 轮，
**这正是同一个文件在 glm 条目下严词警告过的做法**。审查者原话：「文件刚刚在 glm 的条目下严正警告
不要跨轮算性价比，却在 v4-flash 这里自己把两个不同源的分数除以费率并作比较」。

顺着这条排查，又找出三处仍在用**涨价前的 0.05x** 支撑当前结论：

| 位置 | 原文 | 现状 |
|---|---|---|
| `qwen3.8-max-preview.dispatchNote` | 「0.50x 是 flash(0.05x) 的 10 倍」 | 涨价后是 **2.9 倍** |
| `deepseek-v4-flash.sameRoundNote` | 「性价比 1780 仍是全场最高」 | 立论已不成立 |
| `deepseek-v4-flash.note` | 「保住默认落点靠的是性价比（1780 vs 738）」 | T2 定位改为靠同口径领先 |
| `sameRoundEval_20260816.costEffectiveness` | 旧费率算出的两个比值 | 加标注：历史存档，⛔ 不得用于当前 |

**教训**：改一个基础数值（费率）时，**派生结论散落在多个字段里不会跟着变**。
涨价那一轮只改了费率本身和几处显眼的表格，这些藏在 `note` / `dispatchNote` 里的比值全留在旧世界。
⇒ 改费率后要**按「这个数被谁引用过」逐字段扫**，不能只改费率字段。

### ⚠️ 一处差点自相矛盾

`algorithm` 的付费起步档最初写「依据：头对头 LRU v4-flash 36 > glm 31」——
**而同一份 CHANGELOG 上一段刚说过那一格口径不同、不能当证据。**
自查时抓到，改成诚实版本：**algorithm 的付费起步档没有干净证据**，
现有依据是并发题（同口径，v4-flash 35 > glm 31）作为「精细实现类」的最近代理。
真正对口的 LRU 数据要等一轮同口径补测。

⚠️ 这类矛盾很难自己看见——因为**两句话都是我写的、都在同一次编辑里**，
而它们的冲突要跨段落才显形。判据是：**一个数据我在 A 处标了「不可用」，
就要回头搜它在 B 处有没有被当依据引用。**

### ⚠️ 审查通道本身踩到的两件事

**`hy4-preview` 撞 429。** 派它做本次复审，transcript 显示它做了 13 次工具调用后返回
`429 too many requests`，`status=incomplete`，agent 随即 idle。
⚠️ **Paseo 的完成通知里只有它的开场白「I'll start by reading the brief.」**——
不看 transcript 会以为它答了一句就交差。这是「收割前先确认 lastStatus」之外的第二层：
`lastStatus=idle` 也可能是**被限流打断后的 idle**，得看最后一条消息的 `status`。

⇒ 这条正好现实印证了规则里「免费额度耗尽会进排队/限流，长任务派进去会卡住」——
派免费档做长任务前**先探活**不是纸面纪律。

**`pi -p` + `gpt-5.5` 跑满 17 分钟无输出。** prompt 只有 26 字符（背景全在 BRIEF 文件里，
符合「≤200 字符」纪律），但任务本身要读约 2000 行跨 4 个文件。进程活着、0% CPU、等网络。
⇒ 按既有纪律**没有收窄 prompt 重试，而是换通道**（gemini → hy4 → glm-5.3-flash）。
⚠️ 「prompt ≤200 字符」能防住 prompt 过长这一种成因，⛔ 防不住任务本身太大。

### 二轮异构审查：`glm-5.3-flash` 复审（VERDICT: FAIL，4 ❌ + 6 ⚠️）

首轮 gemini 的修复本身没被审过，所以做了第二轮——**审查人换成本轮刚开启的 `glm-5.3-flash`**，
既是异族复审（GLM ≠ Claude），也顺带实地验了一把新的 T1 默认档。
它跑了 26+ 次工具调用，逐条对照 `/tmp/rift-bak/`、`h2h-20260828.json`、`~/.pi/agent/models-store.json`
和三份运行时副本，独立复核了首轮三条修复，然后抓出 4 个新 ❌。

**❌1 修白名单缺口时把合法通道堵死了（回归）。**
`EXEMPT_PROVIDERS` 只写了 `['pi','claude','codex','opencode']`，
漏掉 `github-copilot` 和 `volcengine-coding`/`-agent-plan`/`-chat`。
后果：`--provider volcengine-coding`（§3.2b 只读通道的标准命令）和 `--provider github-copilot`
（审查主通道）会被第三层当「未知 provider」拦停——**而它上面两行的注释正写着这些不进白名单校验**。
bak 里的豁免集是完整的，是本轮重写丢的。

⚠️ **补缺口时把邻近的合法路径一起堵上，是「加校验」这个动作的固定失败形态。**
判据：新增一条拒绝分支后，要把**文档里列过的每一条合法调用**手动过一遍。

**❌2 两个机器可读字段对同一问题给出相反答案。**
`dispatchDefaults.escalation.entryTier` 说「architecture 从 T2 起步」，
而同一对象里新加的 `dispatchDefaults.entryTier.architecture.paidEntry` 是 `glm-5.3-flash`。
**是我自己造的**——先写了前者，拿到头对头数据后加了后者，没回头删前者。
v11.0 刚立下「数值字段的权重高于散文」，那么两个数值字段打架就比散文矛盾更危险。
已删除重复真源，并加 `entryTierSourceOfTruth` 指向唯一那份。
连带修 `codebuddyDefaultModel`（仍是 flash）、`modelFamilyPreference`（仍写「08-31 后 flash 接管第一顺位」）、
`timeOfDayPolicy.mustNotDowngrade`（模型名过期）。

**❌3 旧费率清扫没扫完。** 上一节刚写完「改费率后要按『这个数被谁引用过』逐字段扫」，
实际只扫了 4 处。复审又找出 5 处按现行口径陈述的旧值：
`escalation.toV4ProCondition`「只贵 2.6 倍 / K3 贵 32 倍」、`kimi-k3-1.notAReason` 两条
「0.05x / 0.13x / 一次 K3 ≈ 32 次 flash」、`deepseek-v4-pro.dispatchNote`、`channelDisambiguation`。
实锤是同一个模型条目内部打架：`kimi-k3-1.costWarning` 已是「9.5 倍（原 32 倍）」，
紧挨着的 `notAReason` 还停在 32 倍。

**❌4 `concurrency` 这条路径走不通。** 伪代码查 `ENTRY['concurrency_impl']`，
但 routing §6 代号列里只有 `concurrency`——`classify()` 根本产不出 `concurrency_impl`，
查表落空退回 T1，违反「写并发原语实现从 T2 起步」。
另外 `failed_rounds` 是否计入 T0 失败没定义，计了会让默认类跳过 T1 的 glm。
已把 §6 拆成 `concurrency_diag` / `concurrency_impl` 两行、伪代码加子类判定、
并把计数口径写死为「只数付费阶梯内做砸的档数，T0 不计、同档重试不计」。

**⚠️ 一条重要的：「hy3 并发诊断 36.5 白名单内最高」被自家数据推翻了。**
那是 07-20 轮的单次值，而 08-21 逐字同题复测里 hy3 并发只有 **29**，三臂最低（hy4 34 · glm 32）。
它当时还在给两条规则承重。⇒ 三处引用都补了口径，规则改为「仍可先试，⛔ 但不再宣称它最强」。
⚠️ 这与本轮的 architecture 是同一个病：**一个单次测量被当成 standing 事实，
之后所有引用都不再回头看它的出处**。

其余已修：`piCopilot.models` 的双 `gpt-5.5`（v11.1 声称修了，实际只修了 md 侧、漏了 catalog 这份）；
Copilot 清单三份互相矛盾 ⇒ 收敛为一份并注明以 `models-store.json` 为准；
K3 的「性价比 68 全场最低」与 hy4 的「S 级」都是跨轮口径 ⇒ 加限定语；
`clamp_to_supported()` 引用的「§3.2 能力表」在所有现行文件里都不存在（**bak 里也不存在**，
是既有悬挂引用）⇒ 从 CHANGELOG v10.3 取回数据、补成 §3.2e；
`args.model == 'k3'` 是死代码（P1 早就 goto EXECUTE 了）⇒ 删；
T4 也做砸时 `min(i,3)` 会静默重派 K3 ⇒ 改为报告用户。

复审判定 architecture→T1 的**证据成立**：h2h 原始 json 与文件陈述逐字段一致，
n=1 已如实标注，且「起步档」是可逆决策、有升档纪律兜底。

### 🔻 三文件职责重划 + 瘦身

`model-routing.md` 此前按时间轴倒序堆了 8 条「硬性约束」，同一条事实反复出现——
派发链写了 7 处、免费档排除清单 4 处、K3 红线 3 处、时段策略废止 3 处。
更根本的问题是**它在替 CHANGELOG 承担历史职责**（大段「已废止 / 旧记录已失效 / 存档理由」），
而这些内容 CHANGELOG 本来就有。

重划职责：

| 文件 | 职责 |
|---|---|
| `SKILL.md` | **怎么做** —— 伪代码 · 命令 · prompt 模板 · 自查表 |
| `model-routing.md` | **选什么 + 为什么** —— 路由规则 · 门禁 · 证据 |
| `model-catalog.json` | **数值** |
| `CHANGELOG.md` | **历史** |

按主题（而非时间）重组 routing，历史全部交回 CHANGELOG：

| 文件 | 前 | 后（交付实测） |
|---|---|---|
| `model-routing.md` | 895 行 | **541 行**（−40%） |
| `SKILL.md` | 601 行 | **512 行**（−15%） |

⚠️ 中途写过 500/453，那是首轮瘦身刚完成时的数——两轮审查的修复又补回了行数
（补回的都是**缺失内容**：thinking 档位能力表、Claude 模型「何时选」、约束 3-2、
concurrency 子类拆分）。以交付实测为准。

⛔ **删的只是重复与历史，规则一条没少**：白名单、排除清单、v4-pro 门禁、K3 红线、
thinking 两组反例、异构对照表、降级链、探活纪律、`-x` 陷阱全部保留。

### ⚠️ 顺带修掉的三个 sed 残留

上一轮 `gpt-5.4 → gpt-5.5` 全文替换是无差别的，撞坏了三处：

| 位置 | 坏成什么样 | 修 |
|---|---|---|
| Copilot 模型表 | `gpt-5.5` 出现两行，一行标「审查默认」一行标「历史盲评评委」 | 合成一行；按 `~/.pi/agent/models-store.json` 实测重列 |
| Copilot 模型清单 | `gpt-5.5-mini`（**不存在这个 id**） | 实际是 `gpt-5.4-mini` |
| 涨价对照表 | `deepseek-v4-pro \| 0.51x \| 0.51x`（08-16 列被一起改了，看不出涨了多少） | 该表随本次重构移出 routing，正确版本落在本文件 v11.0，08-16 列为 `0.13x` |

**教训**：全文替换一个版本号时，**被替换的旧值可能出现在「历史对照」语境里**——
那里的旧值是数据不是错字。改完要按语境抽查，不能只看替换计数。

### catalog 5.3.0

`whitelist.codebuddy-code` 加入 `glm-5.3-flash`（`closed` 移除）；新增 `models['glm-5.3-flash']`；
新增 `h2hEval_20260828`；新增 `dispatchDefaults.entryTier`（`skipFreeTier` / `paidEntry` 两个字段
把上面那件混淆的事拆开）；`escalation.rule` 改成 5 档链；`dispatchRank` 按阶梯重排
（hy4=1 · hy3=2 · glm-5.3-flash=3 · v4-flash=4 · v4-pro=8 · k3=9）。

二轮审查后追加：删除重复的 `escalation.entryTier`（与 `dispatchDefaults.entryTier` 矛盾）；
`entryTier` 拆出 `concurrency_diag` / `concurrency_impl` 并加 `_taskTypeCodes` / `_failedTierCounting` 口径说明；
`codebuddyDefaultModel` 改 `glm-5.3-flash`；`modelFamilyPreference` 按 5 档链重写；
`piCopilot.models` 去重并以 `models-store.json` 为唯一真源；
`glm-5.3-flash` / `hy4-preview` 补 `paseo` 块。

⚠️ `hy4-preview-x`(0.29x) 与 `hy3-x`(0.05x) **仍在 `closed`**，待用户裁定——
它们的 label 与免费版完全相同，开启前必须先确认派发侧按 id 匹配。


## v11.0 (2026-08-21)

三件事同时发生：**codebuddy 新增 Hy4 preview（免费）** + **🔴 全表涨价** + **v4-pro 门禁从散文改成机器可读字段**。

### 🏆 Hy4 preview 三题全胜，接替第一顺位

用户告知 codebuddy 新增 Hy4 preview，免费至 2026-09-12 00:00。同轮三臂盲评（题库逐字复用
08-16 存档原题，`thinking=high`，创建后核 `runtimeInfo` 确认无静默降级，匿名 A/B/C 且位置逐题轮换，
评委 `github-copilot/gpt-5.5`，prompt ≤200 字符）：

| 题目 | hy4-preview | hy3 | glm-5.3-flash |
|---|---|---|---|
| LRU（算法） | **★35** | 23 | 26 |
| 并发 Bug 诊断 | **★34** | 29 | 32 |
| Kafka 架构 | **★34** | 32 | 33 |
| **总分 /120** | **103** | 84 | 91 |
| 费率 | **0.00x** | 0.00x | 0.06x |

103 分放进历史榜属 **S 级区间**（M3 114 · Sonnet5 112 · K3 110.5），而它当前免费。
⇒ hy4-preview 接替 hy3 成为第一顺位；hy3 同为免费但三题全负，且免费期早 12 天结束。

✅ **方法论自校验**：hy3 本轮 LRU 23 分 vs 2026-07-20 原始盲评 22 分——同题复现一致，
说明题库与评分口径稳定，这一轮的分数可以和 08-16 轮内部比较结构做对照。

⚠️ **一处未验证**：Hy3 的「做不了清单」是否同样适用于 Hy4。Hy4 的 LRU 拿了 35 分（hy3 仅 23），
「algorithm 是短板」这条对它**很可能不成立**。在补测前 Hy4 沿用该清单属于保守处理，可能低估它。

### 🔴 全表涨价，默认落点的立论被动摇

`paseo list_models` 复核时发现远不止多了一个模型：

| 模型 | 08-16 | 08-21 | |
|---|---|---|---|
| `deepseek-v4-flash` | 0.05x | **0.17x** | 涨 3.4 倍 |
| `deepseek-v4-pro` | 0.13x | **0.51x** | 涨 3.9 倍 |

`deepseek-v4-flash` 的性价比从 **1780 掉到 524**。「DeepSeek 优先」（约束 7，2026-08-16）
成立时的前提是它**又强又便宜**，涨价后这个前提不再成立。
同时发现 `glm-5.3-flash` **0.06x**——新费率下最便宜的付费模型，本轮一并测评（91/120）。

K3 的倍数也跟着变了：贵 v4-flash 从 **32 倍**降到 **9.5 倍**。倍数虽降，
但性价比 110.5/1.62 = 68 仍是全场最低，红线不变。

### ⚠️ `-x` 后缀：新出现的命名陷阱

| id | 费率 | |
|---|---|---|
| `hy4-preview` | **0.00x** | 免费至 09-12 |
| `hy4-preview-x` | **0.29x** | ⚠️ 同名收费版 |
| `hy3` / `hy3-x` | 0.00x / 0.05x | 同一模式 |

**同一个 label、两个 id、一免费一收费。** 🔴 派发必须认 id，按 label 匹配会选错。
⚠️ 附带风险：09-12 限免结束后若平台把 hy4-preview 直接切成收费，费率会从 0 跳到 **0.29x**，
比当时的 v4-flash(0.17x) 还贵——⛔ 不能想当然地「免费结束就自动落回同名收费版」。

### 🔴 v4-pro 门禁：从散文改成机器可读字段

用户反馈**「很多 agent 还是喜欢用 v4-pro，消耗太快」**。规则早已写在十几处仍拦不住。
根因**不是规则不够，是数据在反着劝**：

```
blindEval        v4-flash 96  >  v4-pro 86      ← 支持 flash
sameRoundEval    v4-pro  96  >  v4-flash 89     ← agent 抓这个当理由 ⚠️
```

分数是结构化数据、规则是散文，agent 扫 catalog 时只抓分数。⇒ 改成机器可读门禁：

| catalog 字段 | 值 |
|---|---|
| `selectableByDefault` | **`false`** |
| `dispatchRank` | 8（刻意与默认落点拉开） |
| `requiresPrecondition` | 上一档已在**本任务**做砸过一轮，派发理由必须写明哪一轮、砸在哪 |
| `costMultiplier` | 3.0x vs v4-flash |
| `whyAgentsWronglyPickIt` | 把失效模式本身写进数据，钉在那组误导分数旁边 |

**教训**：规则写在散文里改十二处不如把数值字段改对一处。
数值字段的权重高于散文，警告要**钉在会误导的那个数字旁边**。

### ⚠️ 纠错：审查模型是 gpt-5.5，不是 gpt-5.4

用户指出审查通道写成了 `gpt-5.4`。**这个错犯了两次**，两次都由用户抓到。
全文 35 处替换为 `gpt-5.5`。同时重申两条既有约束：

- 🔴 **prompt ≤200 字符** —— 非交互模式下 800 字让 GPT-5.5 挂 22 分钟，短 prompt 秒回
- ⛔ **撞超时不要收窄 prompt 重试** —— 极小 prompt 也超时属另一种根因，换通道

### ⚠️ 过程纠错：`aborted` 是中间态，不是终态（诊断结论已撤回）

采集盲评产出时，`hy4-kafka` 与 `hy4-concurrency` 的最后一条 assistant 消息都是
**7 字符 `aborted`**（`status=incomplete`），我据此判为「中止、需重派」并重派了两个 agent。

**这个判断下早了。** 复查 transcript 逐条消息：

```
hy4 并发 首轮  assistant#1  status=incomplete      7 字符 'aborted'
              assistant#2  status=completed   24471 字符 完整答复   ← 自己重试成功了
```

⇒ 根因是**我在 `running` 状态下取了「当前最后一条消息」，把它当成了「最终产出」**。
✅ **诊断结论撤回**：没有证据表明 hy4-preview 有稳定性缺陷。

⚠️ 这个失败模式很危险：产出**非空**（7 字符），提取器若只判「非空」就会把 `aborted`
送去评分，得出「Hy4 得分极低」的错误结论。⇒ `collect.py` 已加护栏：
`len < 500` 或内容为 aborted/cancelled/interrupted 一律判无效。

**教训**：判定 agent 产出前必须先确认 `lastStatus` 已是 `idle`/`completed`。
与既有记录「请求返回 ≠ 产出有效」同类。

### catalog 5.0.0

新增 `models['hy4-preview']` · `hy4Eval_20260821`（含 `processNote` 记录上述撤回）；
`providerRateSnapshot` 全表刷新到 08-21；`promoFirst` 改指 hy4-preview；
`whitelist.closed` 新增 `hy4-preview-x` / `hy3-x` / `glm-5.3-flash` 三个待裁定 id。


## v10.8 (2026-08-20)

一次性调用 / 并发任务的通道换成 **pi**；opencode 不禁用、降为兜底；codex 那条撤销。

### pi 接入（`@earendil-works/pi-coding-agent` v0.84.2）

配置一个文件 `~/.pi/agent/models.json`（600 权限），两个火山套餐各一个 provider：
`volcengine-coding`(7 模型) + `volcengine-agent-plan`(12 模型)，**19 个逐个 `pi -p` 实跑通过**。

**pi 相对 codex 的关键优势**：模型条目自带 provider ⇒ 19 个能同时列出、界面直接切，
不像 codex 一个 session 锁死一个 provider。

### 能力对齐 codebuddy 子会话（实测，主会话独立核验）

建临时 git 仓 → 让 pi 修 bug + 写测试 + 跑测试 + 提交。**不采信自述**，逐项核：
`calc.py` 真改对、`test_calc.py` 真存在、`git rev-list --count` 真从 1 变 2、commit message 是中文。

| 项 | 状态 |
|---|---|
| 全局规则 | ✅ 新建 `~/.pi/agent/AGENTS.md` = `~/.claude/CLAUDE.md` 整份复制（pi 不支持 `@import`）|
| 项目规则 | ✅ 自 cwd 向上找 `AGENTS.md`/`CLAUDE.md` ⇒ `~/AgentWorkspace/CLAUDE.md` 自动生效 |
| Skills | ✅ **原生读 `~/.agents/skills/`**，实测 20 个全加载（含 rift-dispatch / Memory / agent-workflow-rules）|
| 规则实际生效 | ✅ 问它「回答语言」「红线第 5 条」，两条都答对 |

⇒ 已在 `~/.claude/rules/global/90-maintenance.md` 的同步目标表登记 pi（新增第 7 个入口）。

### 两个踩坑

- ⚠️ **必须 `compat.supportsDeveloperRole: false`** —— 火山不认 OpenAI 的 `developer` role，
  不加则 reasoning 模型全部 `400 InvalidParameter: messages.role`。
  首轮 6 个里只有 `kimi-k2.7-code` 通过，因为我给它设了 `reasoning:false` 恰好绕开
- ⛔ **不要加 `compat.thinkingFormat`** —— 我猜火山的 `thinking.type` 与智谱同构，填了 `"zai"`，
  结果**请求全部挂起**跑满 10 分钟超时。隔离测试证明 `supportsDeveloperRole` 一条**既必需也足够**。
  思考强度目前用 pi 默认，未做映射

### 🔴 opencode 卡死的根因（用户定位）—— 解除禁用，降为兜底

> **是「纯命令方式」造成的**：每次 `opencode run --pure` 拉起一个 serve，反复调用则 **serve 堆叠**吃穿内存。
> 与既有记录吻合——`oc-review` v1.13.0 就是靠「共享 serve + `--attach`」消掉 per-run 堆叠的。

⇒ **单次偶发调用安全**（review 正属此类，所以 review 留在 opencode 没问题）；
⛔ **循环里反复 `opencode run` 是危险动作**，改用 `pi -p` 或复用共享 serve。
v10.7 里「opencode 已降为最后手段/唯一保留 review」的表述已改成「排最后的兜底，但不禁用」。

### ⛔ codex 通道撤销

codex 的 `model` 与 `model_provider` 是独立字段、**catalog entry 无 provider 字段**（33 字段逐一确认）
⇒ 一个 session 只能连一个 provider，界面 `/models` 切不了跨 provider。用户选择保留原有 GPT。
codex 配置已**逐字节还原**（`diff` 验证），并删除 `~/.config/volcengine/env`（走 `trash`）与 `~/.zshenv` 引用。

catalog 升 **4.6.0**，新增 `oneshotChannels`（含 `pi` 详情、`opencodeCrashRootCause`、`codexReverted`）。

## v10.7 (2026-08-20)

用户确认，把 opencode 全局默认模型切到 Coding Plan，并重申「DeepSeek 优先 → 族内 v4-flash 优先」策略不变。

### 全局默认模型已切换

```
volcengine-agent-plan/ark-code-latest   →   volcengine-coding/deepseek-v4-flash
```

- `~/.config/opencode/opencode.json` 与 dotfiles 的 `opencode.json.template` **两处同步**
- 改前备份 `opencode.json.bak-20260820-*-before-default-switch`
- **实测验证**：`opencode run --pure "…"` 不带 `-m`，输出头显示 `> build · deepseek-v4-flash` ✅

### 这次切换让配置与策略首次完全自洽

新默认 `volcengine-coding/deepseek-v4-flash` 同时满足三条既有规则，不再有例外：

| 规则 | 来源 | 新默认是否满足 |
|---|---|---|
| DeepSeek 系列优先 | 约束 7-1 | ✅ 是 deepseek |
| 族内优先 `v4-flash`（`v4-pro` 仅升档用） | v10.5 用户决策 | ✅ 是 flash |
| opencode 通道优先火山，首选 Coding Plan | 约束 7-2 / v10.6 | ✅ 是 volcengine-coding |

⇒ 此前的矛盾点（默认指向 `ark-code-latest`——既不是 deepseek、又在额度紧张的 Agent Plan 上、
且 Coding Plan 根本没有这个模型）就此消除。

⚠️ 策略本身**无改动**——用户是重申，不是变更。派发链仍为
`hy3 0.00x → deepseek-v4-flash 0.05x → deepseek-v4-pro 0.13x → K3 1.62x`（cb 侧），
opencode 侧 `volcengine-coding/deepseek-v4-flash` 为首选。

## v10.6 (2026-08-20)

Agent Plan 额度不够，用户另购 **Coding Plan**，新增 provider `volcengine-coding` 并设为 opencode 默认。

### 套餐与配置

| 项 | 值 |
|---|---|
| 套餐 | Coding Plan · **Pro 套餐** · 包月 |
| 有效期 | 2026-08-20 07:10 → 2026-10-20 23:59（⚠️ **自动续费已关闭**） |
| baseURL | `https://ark.cn-beijing.volces.com/api/coding/v3`（OpenAI 协议，已支持 Responses API） |
| npm | `@ai-sdk/openai-compatible`（Chat API） |
| API key | 与 Agent Plan **不同**，两个套餐额度独立 |

🔴 **baseURL 有个坑**：官方明确 **⛔ 不要用 `https://ark.cn-beijing.volces.com/api/v3`——会产生额外费用**。
Anthropic 协议工具走 `…/api/coding`，OpenAI 协议走 `…/api/coding/v3`。

### 为什么选 Chat API 而不是 Responses API

Coding Plan 两种协议都通（curl 实测均 HTTP 200），但按 v10.3 的结论选了 Chat：

```
thinking {type:disabled} → reasoning_tokens=0    ✅ 真生效
thinking {type:enabled}  → reasoning_tokens=22
不带                     → reasoning_tokens=31
reasoning.effort=bogus   → HTTP 200, tokens=25   ⇒ OpenAI 的 effort 被静默忽略
```

⇒ 火山只认自己的 `thinking.type`，而 `@ai-sdk/openai`（Responses）会把 `thinking` 从参数白名单丢弃。
用 `@ai-sdk/openai-compatible` 才能让 `--variant off/on` 真正生效——**新 provider 一步到位，
不用像 Agent Plan 那样再补一个 `volcengine-chat` 兄弟**。

### 7 个模型（逐个 curl 实测全部可用）

`deepseek-v4-flash` · `deepseek-v4-pro` · `glm-5.3` · `minimax-m3` · `kimi-k2.7-code`
· `doubao-seed-2.1-turbo` · `doubao-seed-2.0-lite`

比 Agent Plan 少 5 个：`ark-code-latest` · `kimi-k3` · `doubao-seed-evolving` · `glm-latest` · `doubao-seed-2.0-mini`
⇒ 需要这几个才回 `volcengine-agent-plan`。

⛔ `auto` 不支持（实测 `UnsupportedModel: does not support the coding plan feature`），未配置。

### 优先级：Coding Plan 接替成为 opencode 默认

```
① volcengine-coding/deepseek-v4-flash      ← ⭐ 默认（独立额度 + --variant 可用）
①b volcengine-agent-plan/*                 ← 只为那 5 个 Coding Plan 没有的模型
①c volcengine-chat/deepseek-v4-*           ← 要 Agent Plan 额度 + 控思考强度
②  🔴 deepseek/* 官方 API                   ← 已 disable，不可用
```

⚠️ **`volcengine-chat` 的定位被削弱**：它原本是「Agent Plan + 思考强度可控」的唯一途径，
现在 `volcengine-coding` 同时给了 deepseek 两兄弟 + 思考强度可控 + **独立额度**。
只在「必须消耗 Agent Plan 额度」时才需要它。未删除。

### 脱敏与配置卫生

- 写入前备份 `~/.config/opencode/opencode.json.bak-20260820-100805`
- 已确认 `~/.config/opencode` **不是 git 仓、不被 syncthing 同步** ⇒ 明文 key 不外泄
- **dotfiles 的 `opencode.json.template` 同步加了 `volcengine-coding`**，用 `${VOLCENGINE_CODING_APIKEY}`
  占位符（复查 0 处明文），新装机器不会缺这个 provider

### ⚠️ 一处留给用户决定 → ✅ 已于 v10.7 确认并执行

opencode 的全局默认 `model` 当时仍是 `volcengine-agent-plan/ark-code-latest`（指向额度紧张的套餐，
且 `ark-code-latest` 在 Coding Plan 里没有）。v10.6 未擅自改，用户确认后已在 **v10.7** 改为
`volcengine-coding/deepseek-v4-flash`。

catalog 升 **4.4.0**。

## v10.5 (2026-08-20)

用户明确两条：**deepseek 系列内优先 `v4-flash`（Hy3 不动）** + **opencode 优先 volcengine**（重申）。
前者要求**撤销 v10.1 的一处改动**。

### 🔴 撤销：`algorithm` 落点从 v4-pro 改回 v4-flash

v10.1 依据同轮重测（LRU：v4-pro 33 vs flash 25，+8 分）把 `algorithm` 直接指向 v4-pro。
**那违反了本 skill 自己的「⛔ 不做预防性升档」**——还没让 flash 试过，就因为
「这类任务 v4-pro 更强」而预先升档，和被两组实测（n=1、n=12）否掉的
「任务高风险 ⇒ 升模型档位」是**同一个推论**。当时没察觉。

现在统一：**`algorithm` / `perf` / `architecture` 三类全部先落 flash，做砸了才升 v4-pro。**

⚠️ **重测数据本身依然有效，只是用法变了**：
+8 分说明的是「**升档时该升到 v4-pro，而不是直接跳 K3（32 倍）**」，
不是「该跳过 flash」。这句已写进 §V4-Pro 重测、§1 表、catalog 三处，防止后续 agent 再倒推回去。

- `deepseek-v4-pro` 角色改为**纯升档档位**：`bestFor` 清空、白名单表与费率表的「algorithm 定向升档」改为「升档档位」
- `catalog.dispatchDefaults.modelFamilyPreference` 新增 `primary: deepseek-v4-flash` / `secondary: v4-pro（仅升档）`
- Hy3 **不动**，仍在 flash 之前（0.00x 限免至 08-31），限免结束后 flash 自动接管第一顺位

### opencode 侧同步「族内优先 flash」

原写 `volcengine-agent-plan/deepseek-v4-pro`（或 -flash），现统一为
**首选 `deepseek-v4-flash`**，`-pro` 仅在 flash 答得不够时换。三文件已同步。

### 🔴 本轮自查发现：我用了 4 天前的探测数据，造成 3 处回归

写这条时我拿的是 08-16 的 `opencode models` 结果，而 v10.3/v10.4（08-19、08-20）
改过配置，我不知情。重新实测 `~/.config/opencode/opencode.json` 后修正：

| 我写错的 | 实际 |
|---|---|
| 「官方 `deepseek/*` 降为套餐耗尽兜底」 | 🔴 **已在 `disabled_providers`**（v10.4 用户操作），根本不可用。兜底应是 `github-copilot/*` 或 `opencode/deepseek-v4-flash-free` |
| catalog `opencodeProviders.priority` 的 ② 重新写回 `deepseek/*` 兜底 | **把 v10.4 修好的又改回去了**，已重修 |
| 前置检查写「不要退回自费的 `deepseek/*`」 | 措辞误导——不是「贵」，是「退不回去」 |

**顺带补 v10.4 的一处遗漏**：`volcengine-chat`（08-20 新增，3 模型，`--variant` 有效）
此前只写进 SKILL.md，**model-routing.md 与 catalog 里 0 处提及**。已补：
opencode 优先级链加 ①b、通道消歧表加一行、catalog 加 `opencodeProviders.volcengine-chat` 与 `exempt` 条目。

⚠️ 教训：**版本号撞了**——我一度把本条写成 `v10.3`，而 08-19 已有 v10.3、08-20 已有 v10.4。
写 CHANGELOG 前应先 `grep '^## v' CHANGELOG.md`，不能凭记忆接续。

catalog 升 **4.3.0**（非 4.2.0）。

### SKILL.md 开头新增「开工前三条硬默认」

volcengine 这条被重申了一次，说明原先埋在 model-routing.md 约束 7 里不够显眼。
现在提到 `$ARGUMENTS` 正下方，读 skill 的第一屏就能看到：

1. DeepSeek 优先，族内优先 `v4-flash`；`v4-pro` 只在 flash 做砸时用
2. opencode 通道优先 `volcengine-agent-plan`（按月套餐，1M context），官方 `deepseek/*` 降为兜底
3. 🔴 审查是例外，固定 `github-copilot/gpt-5.4` —— 同族审同族 = 自审

另在「派发前自查」表加一行：走 opencode 前先确认用的是 volcengine，
⛔ 不要默默退回自费的 `deepseek/*`。


## v10.4 (2026-08-20)

两件配置变更的联动更新，均为用户决策后执行。

### 1. 火山思考强度已可用 —— 但必须用新 provider `volcengine-chat`

按「并存」方案落地（用户选定）：原 `volcengine-agent-plan` 保持 Responses API 当默认**完全不动**，
另加 `volcengine-chat` 走 Chat API。同一个 Agent Plan 套餐、同一个 key。

| provider | npm | 模型数 | `--variant` |
|---|---|---|---|
| `volcengine-agent-plan` | `@ai-sdk/openai`（Responses） | 12 | ❌ 静默失效 |
| **`volcengine-chat`** | `@ai-sdk/openai-compatible`（Chat） | 3 | ✅ `off`/`on`（+`auto` 仅 ark-code-latest） |

`volcengine-chat` 只配了 `ark-code-latest` · `deepseek-v4-pro` · `deepseek-v4-flash`。
`auto` 只给 ark-code-latest —— 另两个未实测 auto 支持性，不配以免运行时报 `Unsupported thinking type`。

端到端实测：`--variant off` 6s / `on` 7s，均返回正确结果。

**两个踩坑（都已放弃相应尝试）**：
- `interleaved: "reasoning_content"` **字符串形式过不了运行时校验**（报 `Expected true | object | undefined`）。
  发布的 JSON Schema 里明明允许 string enum，但运行时 zod 更严格 —— schema 与运行时不一致。
- 改成 schema 允许的 object 形式 `{"field": "reasoning_content"}` 能过校验，但**让 opencode 挂死**
  （5 分钟无输出）。已移除。⇒ **推理过程不显示**（内容确实在 `reasoning_content` 字段，
  curl 实测 reasoning_tokens=67 有值），只是 opencode 不渲染。不影响答案正确性。

### 2. 🔴 `deepseek/*` 官方 API 已被用户 disable

用户 2026-08-20 把 `deepseek` 加入 `~/.config/opencode/opencode.json` 的 `disabled_providers`
（现为 `["deepseek", "openrouter"]`）。`deepseek/deepseek-chat` · `-reasoner` · `-v4-flash` · `-v4-pro`
四个模型全部不可用。

⚠️ **别和这三个搞混**（都保留可用）：`volcengine-agent-plan/deepseek-v4-*`（火山套餐）、
`volcengine-chat/deepseek-v4-*`（火山套餐 + thinking 可控）、`opencode/deepseek-v4-flash-free`（免费额度）。

⇒ 原先把 `deepseek/*` 当「volcengine 套餐耗尽兜底」的地方全部失效，共 9 处已更新：

| 文件 | 处数 | 改法 |
|---|---|---|
| SKILL.md | 2 | §2 注释、§3.2 provider 表标注已禁用 + 指向替代 |
| model-routing.md | 4 | §优先级链、§通道表、§不受白名单约束通道、§费率表 |
| model-routing.md 降级链路图 | 3 | **改指向 `volcengine-agent-plan/deepseek-v4-*`** |

降级链路那 3 处是实质改进：原本 cb 限额 → 降到自费官方 API 掏现金；现在 → 降到火山**同款模型**
（`deepseek-v4-flash` / `-pro` 火山套餐里都有），已付费不额外花钱。
⚠️ 保留了能力降级警告：这条是 `opencode --pure` 一次性文本调用，不是能改代码的 Paseo 子会话。


## v10.3 (2026-08-19)

修 **opencode --pure 通道漏传思考强度**。三条执行通道里只有它没有档位参数：

```
paseo_create_agent(provider, model, thinking, args)   ← 有
hub_remote_create(provider, model, thinking, args)    ← 有
opencode_run_pure(provider, model, args)              ← 漏了
```

§3.2 的命令也一直是 `opencode run --pure -m {model} "{prompt}"`，没有档位参数；§7 的审查命令
`opencode --pure -m github-copilot/gpt-5.4` 同样没有。也就是说走 opencode 的两个 provider
（实施/问答用 `volcengine-agent-plan/deepseek-v4-pro`、审查固定用 `github-copilot/gpt-5.4`）
**从来没吃到过 `--thinking`**，一直在跑各自的默认档。

### 参数名是 `--variant` 不是 `--thinking`

opencode 的思考强度参数叫 `--variant`（`opencode run --help`：*model variant, provider-specific
reasoning effort*）。`--thinking` 是 Paseo / Hub 那条 `paseo run` 的参数名，两者不通用。

### 档位在 opencode 侧是 per-model 的，不统一

2026-08-19 读 `opencode models --verbose github-copilot` 的 `variants` 字段实测（非文档推测）：

| 模型 | 支持档位 |
|---|---|
| `gpt-5.4` · `gpt-5.4-mini` · `gpt-5.5` | `none` `low` `medium` `high` `xhigh` |
| `gpt-5.3-codex` | `low` `medium` `high` `xhigh` |
| `claude-sonnet-4.6` | `low` `medium` `high` `max` |
| `gemini-3.5-flash` | `minimal` `low` `medium` `high` |
| `gemini-3.1-pro-preview` · `gpt-5-mini` | `low` `medium` `high` |

本 skill 的默认档 `xhigh`（约束 3）**只在 gpt 系成立** —— gemini 系压根没这档。故新增
第 8-1 步 `clamp_to_supported()` 折算，规则**只降不升**：`xhigh`→claude 系落 `max`、
gemini 系落 `high`。⛔ 禁止静默升档（会造成超预期 token 消耗），降档必须在 §5 输出回显，
memory 新增 `effectiveThinking` 字段留痕。

> 这条和「⛔ 创建后必须核实实际生效的模型」是同一类问题：**请求值 ≠ 运行值**。
> 派模型那次是静默降级到 hy3，这次是档位不存在被静默忽略。

### 🔴 火山通道当前传不进思考强度（实测确认，静默失效）

`volcengine-agent-plan/*` 加 `--variant` **不报错但完全无效**：

1. 火山只认自己的 `thinking.type`（`disabled`/`enabled`/`auto`），**不认** OpenAI 的
   `reasoning.effort` —— 传 `effort:"bogus"` 也返回 HTTP 200，且 `minimal` 的 reasoning_tokens
   可能比 `high` 更多（deepseek-v4-pro 实测 598 vs 524，反向），说明是静默忽略。
2. 当前该 provider 用 `npm: "@ai-sdk/openai"`（Responses API）。mock 抓包实测：**`thinking`
   被 ai-sdk 参数白名单丢弃**，请求体 0 次出现；同一份 variants 里的 `reasoningEffort` 却能
   正确转成 `reasoning:{effort}` 发出 —— 证明 variants 机制没坏，是这个 npm 包在过滤。
3. 换 `npm: "@ai-sdk/openai-compatible"`（Chat API）后 `thinking` **可完整透传**（同一 mock 实测）。
   端到端实测 `--variant off` 8s / `on` 7s / `auto` 17s / 不带 18s，off 比默认快一半。

⇒ 已在 §3.2 写明现状 + 启用方式 + 三态映射（火山只有 off/on/auto，不是六档）。
**改 opencode 全局 provider 配置这件事待用户决策，本次未执行。**

### 改动清单

| 位置 | 改动 |
|---|---|
| §1 参数表 | `--thinking` 标注「三条通道都必须传」+ 指向 §3.2 |
| §1 缺失处理 | 新增「合法但模型无该档 → 就近降级 + 回显」 |
| §2 伪代码 8-1 | 新增 `clamp_to_supported()` 折算 + `note_downgrade()` |
| §2 伪代码 4 | 审查硬例外分支补 `--variant xhigh`（原先漏传，交叉审查抓到） |
| §2 伪代码 9 | `opencode_run_pure` 补 `effective_thinking` 参数 |
| §3.2 | 命令加 `--variant`；新增档位能力表、映射表、火山通道说明 |
| §5 输出 | 降档回显 + 火山通道警告 |
| §6 Memory | 新增 `effectiveThinking` 字段 |
| §7 审查 | 审查命令补 `--variant xhigh` |


### 交叉审查发现的既有问题（本次未修，非本次引入）

deepseek-v4-pro 只读审查（实施侧是 Claude，不构成自审）除抓到上面那处漏传外，还提了三条
**既有**问题，都不在本次改动范围内，留待用户决定：

1. **Hy3 的 thinking 说法自相矛盾**：伪代码第 8 步 `args.thinking ?? ...` 允许用户
   `--thinking max` 覆盖 Hy3 的默认 `high`，但 §4 表写「Hy3 固定 `high`」、约束 4-4 写
   「max 已被两轮盲评证伪」。要么代码加 Hy3 分支拒绝覆盖，要么文档把「固定」改成「默认」。
   ⇒ 这是策略决策（该不该允许用户覆盖已被证伪的档位），需用户定。
2. **白名单检查对非 cb/qcn provider 会取到 undefined**：`WHITELIST` 只有 `codebuddy-code`
   和 `qoderclicn` 两个键，但 `if model not in WHITELIST[provider]` 在 provider 为
   `github-copilot` / `volcengine-agent-plan` 时取不到键。注释里写了这两个通道「不受白名单约束」，
   但代码没体现豁免分支。
3. `qoderclicn/qmodel_38max` 在 §2 thinking 档位表中完全缺失（白名单有它，但没有档位分配）。

## v10.2 (2026-08-16)

用户新增两条偏好：**调用者优先 DeepSeek 系列** + **opencode 优先 `volcengine-agent-plan`**。
落成「硬性约束 7」。⚠️ 其中一条与既有规则冲突，已显式豁免并写明理由。

### volcengine-agent-plan 盘点（按月付费套餐）

`opencode models` 实测 12 个，`deepseek-v4-pro` / `deepseek-v4-flash` 已发 prompt 验证可用：

| 类别 | model id | context / output |
|---|---|---|
| **DeepSeek**（首选） | `deepseek-v4-pro` · `deepseek-v4-flash` | **1,024,000** / 65,536 |
| 豆包 | `doubao-seed-evolving`(1M) · `doubao-seed-2.1-turbo` · `doubao-seed-2.0-lite` · `doubao-seed-2.0-mini` | 256K–1M |
| 代码 | `ark-code-latest` · `kimi-k2.7-code` | 256K / 32K |
| 其它 | `glm-5.3` · `glm-latest` · `minimax-m3` · `kimi-k3` | 1M / 64K |

### 🔴 冲突：review 通道**不**跟着换 volcengine

`review` 类仍固定 `opencode --pure -m github-copilot/gpt-5.4`，这是**有意保留**：

> 异构审查要求「评审模型 ≠ 实施模型」（全局红线 #8）。约束 7-1 已把实施侧定成 DeepSeek，
> 评审若也换成 `volcengine-agent-plan/deepseek-*`，就是 **DeepSeek 审 DeepSeek**——异构审查直接失效。
> 08-12 与 08-16 两轮异构审共抓到 13 处问题，全部来自「换一个模型族去看」。

⇒ 「opencode 优先 volcengine」的适用范围限定为**实施类 / 问答类**调用；审查类是硬例外。
已在 model-routing.md §1 表、SKILL.md 伪代码第 4 步、§3.2、§7 四处写死。

### 同一个 DeepSeek 现在有三条通道，写了消歧表

| 通道 | 计费 | 用途 |
|---|---|---|
| `cb/deepseek-v4-*`（Paseo） | codebuddy credits 0.05x/0.13x | **派发开发任务**——有 agent 会话、工具、worktree、git |
| `volcengine-agent-plan/deepseek-v4-*`（opencode） | **按月套餐**（不动 cb credits） | **一次性调用**：只读分析、问答、**长上下文 1M** |
| `deepseek/deepseek-v4-*`（opencode） | ⚠️ 自费现金 + 高峰 ×2 | ⛔ 仅套餐耗尽兜底 |

⚠️ **不可互换**：派开发任务别因为「volcengine 不耗 credits」就改用 opencode——那是一次性文本调用，拿不到 agent 能力。

**连带影响**：§3「opencode 官方 DeepSeek 峰谷定价」整节降级——volcengine 套餐提供同样模型且不花现金，
官方 API 只剩套餐耗尽时的兜底。该节分析仍正确，但适用场景已很少。

### ⚠️ 两处**没有**擅自决定、留给用户的

1. **Hy3 与 DeepSeek 的先后**：Hy3 是 0.00x（限免至 08-31）且有 08-12 明确用户决策，
   本次**不推翻**——链条仍是 `hy3 → deepseek-v4-flash → deepseek-v4-pro → K3`，
   **08-31 限免结束后 DeepSeek 自动接管第一顺位**。若要现在就让 DeepSeek 压过 Hy3，需用户明确指示（等于放弃一个免费档）。
2. **volcengine 侧 10 个非 DeepSeek 模型**：按 7-1「不主动选」。
   ⚠️ 其中 `glm-5.3` / `minimax-m3` / `kimi-k2.7-code` **在 codebuddy 侧已被白名单关闭**（约束 6），
   但 volcengine 是另一个钱包——**是否同样关闭尚未经用户确认**，暂按「不主动选、也不判违规」处理。

catalog 升 **4.1.0**：新增 `opencodeProviders`（含 12 模型清单、`reviewChannelException`、`channelDisambiguation`）
与 `dispatchDefaults.modelFamilyPreference`。

## v10.1 (2026-08-16)

两件事：**K3 成本红线** + **V4-Pro 正式版重测**。后者的结论改变了升档链。

### 一、K3：恢复启用但加使用红线（用户要求「很贵很贵，不要随意使用」）

`cb/kimi-k3-2` = **1.62x**，白名单内唯一超过 1.0x 的模型，性价比 110.5/1.62 = **68 全场最低**。
它留在白名单里是因为「唯一 S 级」，不是因为划算。落成三处硬约束：

- **只有两种情况可派**：① 用户显式 `--model k3` ② 上一档已经做砸过一轮
- **⛔ 四条不构成理由**（每条都被实测或成本算术否掉）：「任务难/重要/风险高」（两组实测表明模型档位不是质量关口）、
  「是 algorithm/architecture 类」（有各自更便宜的落点）、「反正只跑一次」（一次 K3 ≈ 32 次 flash）、
  「先用好的保险点」（这就是"预防性升档"的原话）
- ⚠️ 叠加可靠性前科：0723 实测反复空转（报进度就 idle、git 无产出）⇒ **派了必须核 `git log`**——
  花 32 倍的钱拿不到产出，是这个模型特有的失败模式
- catalog 加 `costWarning` / `allowedWhen`(2 条) / `notAReason`(4 条)

### 二、V4-Pro 正式版重测 —— 旧的「86 分被 flash 取代」已失效

用户告知 v4-pro 已是正式版、能力很强。**同轮同题盲评结果：v4-pro 96 > v4-flash 89**。

| 题目 | v4-pro (0.13x) | v4-flash (0.05x) | 差 |
|---|---|---|---|
| LRU Cache（算法/精细实现） | **33** | 25 | **+8** |
| 并发 Bug 诊断 | **32** | 30 | +2 |
| Kafka 架构设计 | 31 | **34** | **-3** |
| 总分 /120 | **96** | 89 | +7 |

**分项分化才是可操作的部分**：v4-pro 赢在算法/精细实现，**输在架构设计**。

**🔴 最有价值的推论——v4-pro 补上了 M3 关闭留下的空档**：

```
v10.0 关闭 M3 后:  flash 0.05x → ────────── → K3 1.62x   ← 32 倍跳变
本次重测之后:      flash 0.05x → v4-pro 0.13x → K3 1.62x   ← 中间档回来了
```

- `algorithm` 落点从 flash 改为 **v4-pro**（+8 分只贵 2.6 倍）
- `architecture` **保持 flash**（这题 flash 反而高 3 分）
- **默认落点仍是 flash**：性价比 `flash 1780` vs `v4-pro 738`，flash 高 2.4 倍
- **K3 的升档条件收紧**：从「flash 做砸即升」改为「**v4-pro 也做砸**才升」

**方法**：6 个 Paseo agent（3 题 × 2 模型）`thinking=high` 同口径；
每个创建后核 `runtimeInfo.model` 确认无静默降级；答复匿名为 modelA/B 且**位置逐题交错**以抵消位置偏差；
评委 `github-copilot/gpt-5.5` 只读；rubric 沿用历史口径 + v8.9 改进（给评委原题，要求逐条核对模型断言）。

**⚠️ 效力边界（已写进文件，不要被后续 agent 误用）**：
历史**只存档了并发题原题**，LRU/Kafka 的 prompt 是从旧 judge rubric **重建**的
⇒ 绝对分与历史 86/96 **不可直接比较**，本轮只有**同轮 A/B 的相对关系**严格成立。
n=1 单次、单评委，置信度与 `realTaskEval` 同级。
**本次已把三题 prompt 全部存档**（`prompts/`），修掉这个长期缺陷——以后重测可严格可比。

产出物：`~/AgentWorkspace/tmp/v4pro-benchmark-20260816/`（REPORT.md + prompts/ + raw/ + blind/ + scores/ + collect.py）
catalog 新增 `sameRoundEval_20260816`；v4-pro 去掉 `deprecated`、tier B→A、`dispatchRank` 8→3。

## v10.0 (2026-08-16)

两件事同时落地：**qcn 限时1折结束（时段策略整体废止）** + **Provider 模型白名单**。
`paseo list_models` 实测复核后发现问题比转述的大得多，连带修了 3 处会导致派发直接失败的过期数据。

### 一、qcn 夜间优惠取消 ⇒ 时段策略（原 P6）整条废止

用户告知「qoder cli cn 没有夜间优惠了」，实测复核后确认不止如此——**是限时1折活动整个结束**：

| 模型 | 1折期 | 实测 08-16 | |
|---|---|---|---|
| Qwen3.8-Max | 0.05x日 / **0.01x夜** | **0.50x**（无日夜之分） | 涨 10 倍 |
| Qwen3.7-Max | 0.25x / 0.10x夜 | 0.50x | 涨 2 倍 |
| Qwen3.7-Plus | 0.10x / 0.04x夜 | 0.10x | 日价不变，夜价没了 |

0.50 × 10% = 0.05——「1折」本就打在 0.50x 基准价上，活动结束即回到 0.50x。

- **新增「⛔ 硬性约束 5」**：credits 制通道已无任何时段性折扣，派发链 24 小时不变，
  决策树删除 `is_night()` 判断（SKILL.md 伪代码第 6 步整步移除）
- **连带作废两条**：08-12「约束 4-5 夜间也先给 Hy3」（不必再说，全天都是 Hy3）；
  08-02「约束 2-2 夜间默认 qcn」（唯一依据「夜间 0.01x 全场最低」已不成立）
- **qcn 降为「cb 断供时的降级备选」**，不再主动选：性价比 101.5/0.50 = **203**，
  远低于 flash 的 96/0.05 = **1920**
- **官方 DeepSeek 的价值窗口反而变宽**：原先 22:00 后要让位给 qcn 的 0.01x，
  现在 18:00–次日 09:00 整段低谷都归它（仍排在订阅额度之后）
- §3「时段策略」整节重写；**保留** opencode 官方 DeepSeek 的峰谷定价（09-12/14-18 ×2）
  ——那是 DeepSeek 自己的 API 计价规则，与 qcn 折扣是两回事

### 二、Provider 模型白名单（用户决策）

**新增「⛔ 硬性约束 6」，优先级最高**，并在伪代码里前置为 P0 关卡（显式 `--model` 也不能突破）：

| Provider | 允许 | 费率 | 角色 |
|---|---|---|---|
| cb | `hy3` | 0.00x | ⚡ 第一顺位（限免至 08-31） |
| cb | `deepseek-v4-flash` | 0.05x | ⭐ 默认落点 |
| cb | `deepseek-v4-pro` | 0.13x | 白名单内，无推荐场景 |
| cb | `kimi-k3-2` | 1.62x | 极致档 / 唯一升档目标 |
| qcn | `qmodel_38max` | 0.50x | cb 断供降级落点 |

关闭：cb 的 `minimax-m3` `minimax-m2.7` `glm-5.3/5.2/5.1` `glm-5v-turbo` `kimi-k2.7` `kimi-k2.6`；
qcn 除 `qmodel_38max` 外全部。不受约束：`gpt-5.4`（审查）· `claude`（⚠️不推荐）· `deepseek/*`（自费兜底）。

**三个连锁后果，都写进文件了**：

- 🔴 **M3 关闭 ⇒ 升档链断了中间一档**。`hy3 0.00x → flash 0.05x → ~~M3 0.25x~~ → K3 1.62x`，
  从 flash 升档变成**直接跳 32 倍**。「⛔ 不做预防性升档」的分量随之加重。
  M3 是盲评全场最高分（114）且性价比 456——关掉的代价在速查表里明确标出，没有淡化
- 🔴 **K3 撞限额时无替代**（白名单内唯一 S 级），只能报告用户。这是 M3 关闭后**新出现的单点**
- ⚠️ **`algorithm`/`perf`/`architecture` 三类的落点从 M3 改为 flash**，不是直接上 K3——
  直接上违反「不做预防性升档」。但文件里同时写明**这三类确实有分数差**
  （LRU: flash 32 vs K3 37；arch: flash 32 vs K3 39），明确吃深度时可直接 `--model k3`

**✅ K3 恢复启用**（用户 08-16 决定），上一轮标的「K3 状态未澄清」清除，P5.4 的 0723 弃用结论失效。
⚠️ 但 0723 观察到的现象（反复空转、报进度就 idle、git 无产出）**保留为已知风险**：派完必须核 git 有无 commit。

### 三、实测复核修掉的 3 处过期数据（都会导致派发失败或算错成本）

- 🔴 **`qcn/qmodel_preview` 这个 id 已经不存在**，现在是 **`qmodel_38max`**
  （label 从 `Qwen3.8-Max-Preview` 变 `Qwen3.8-Max`，疑似 preview 转正）。
  文件里此前所有指向旧 id 的派发指令**都会失败或静默降级**，已全文替换
- ⚠️ **`cb/deepseek-v4-flash` 降价 0.06x → 0.05x**，全文费率引用同步
- ⚠️ **`qcn/kmodel` 的 label 已从 Kimi-K2.6 变成 Kimi-K2.7-Code（0.30x）**，
  catalog 里 K2.6 挂 `kmodel` 的映射是错的（该模型已关闭，只标注不修）

### 四、结构整理

- **07-28 与 08-02 的三条逐模型禁用令收敛成一节「历史约束（已被约束 6 吸收）」**——
  白名单从正面圈定范围后，它们不再需要单独判断。保留了「盲评总分 ÷ 费率」这套判断算法作为存档
- §2 速查表拆成 **✅ 白名单内（5 个）** / **⛔ 已关闭（7 个 + 未评测的新型号）** 两张表，
  关闭的保留盲评数据供将来重新开启时判断
- catalog 升 **4.0.0**：新增顶层 `whitelist`（含 `closed` / `exempt` / `consequences`）
  与 `providerRateSnapshot`（实测费率快照 + 5 条 findings，用于对照 catalog 是否过期）；
  `dispatchDefaults.nightSubstitution` → `timeOfDayPolicy`（标废止，保留「不下调高档模型」的原则）；
  每个模型加 `whitelisted` 布尔与 `closedNote`
- ⚠️ **一处未复测的存疑项**：cb 侧 `list_models` 现在**只有 `minimax-m3-pay`，没有 `minimax-m3`**，
  与 08-02「要用旧 id `minimax-m3`，`-pay` 会静默降级到 hy3」的实测记录冲突。
  M3 已关闭故不影响派发，仅记录在 `providerRateSnapshot.findings` 备查

### 五、异构审查（`opencode --pure -m github-copilot/gpt-5.4`，只读）抓到 4 处残留，均已核源确认并修复

主决策链本身没问题（白名单闸门 + 降级链都已收敛到 5 个 id），4 条全是**字段级旧口径残留**：

- ❌ `deepseek-v4-flash.blindEvalAtThinking.max.note` 结尾写「V4-Flash 默认保持 `high`」，
  与三个文件里的 `xhigh` 默认档冲突。该句写于 08-02、当时只对比过 high/max 两档。
  已改为「⛔ 不要用 max；现行默认是 xhigh；xhigh 与 max 未做过同题对比」——**不假装 xhigh 被验证过**
- ⚠️ `hy3.avoidFor` 的 `perf` 条目仍写「沿用 §1 既有映射走 **M3**」（M3 已关闭）→ 改落 flash
- ⚠️ `glm-5.2.avoidFor` 仍写「需更强用 `cb/minimax-m3`」→ 改为 flash / K3
- ⚠️ `hy3.limitations.nightWindow` 仍在讲「与 qcn 夜间折扣窗口有 1 小时错位」→
  改为「这是排队概率不是费率优惠，qcn 折扣取消后该权衡消失」
- 另修 `SKILL.md` `--thinking` 参数表仍写 `v4-flash`/`m3`→xhigh → 改为 `v4-flash`/`v4-pro`/`k3`

## v9.0 (2026-08-12)

用户决策：**codebuddy 侧默认 v4-flash；Hy3 限免延续至 08-31，能做的活优先 Hy3**。新增「硬性约束 4」并落到全部表格。

**为什么是 breaking change**：此前 Hy3 只在 `core`/`test`/`batch`/`kb` 四类挂"限免期"字样，
且被「硬性约束 2 第 2 点：夜间默认 qcn」压住；本次把 Hy3 提为**全天候第一顺位**，
flash 退为**默认落点**（Hy3 被排除时接手）。派发链从「flash 起步」变成「Hy3 起步」。

- **新增 model-routing.md「⛔ 硬性约束 4」**（置顶，优先级最高）：五条——
  cb 默认 = `deepseek-v4-flash`；Hy3 优先；「Hy3 做不了」判定清单；thinking 按模型分开定；改写约束 2 的夜间规则
- **「Hy3 做不了清单」（五条，命中即跳 flash，不先试）**：多模态（会切多模态模型并**正常计费**）/
  额度耗尽或探活未秒回（排队）/ `algorithm`（盲评 LRU **22 分**，Hy3 唯一明显短板）/
  `architecture`（`avoidFor: architecture-deep`，arch 33）/ 本任务已做砸过一轮。
  每条都挂了依据，避免后续被当成"感觉 Hy3 不行"随意扩大
- **反向澄清**：Hy3 bug 诊断盲评 **36.5，全场第二（仅次于 M3 的 38）**，
  `core`/`test`/`batch`/`robust`/`doc`/`kb`/bugfix 不得因为它挂 B 级就绕开
- **§1 任务分类表重排**：8 类改为 Hy3 打头；新增 `bugfix` / `architecture` 两个代号；
  `perf`/`algorithm`/`architecture` 三行标 ⛔ 明确排除 Hy3；`concurrency` 拆开——诊断可用 Hy3、写并发原语实现走 flash
- **夜间规则改写（约束 2 第 2 点）**：限免期内夜间也先给 Hy3（**0.00x < qcn 的 0.01x**），
  Hy3 被排除时夜间才落 `qcn/qmodel_preview`。08-31 限免结束后该条自动恢复原效力，已就地标注
- **thinking 按模型分开定**：`hy3` 固定 `high`（`xhigh` **从没在 Hy3 上测过**不得当默认，`max` 已被 v8.3/v8.4 两轮盲评证伪 91.5→85.5）；
  `deepseek-v4-flash` / `minimax-m3` 保持 `xhigh`（约束 3）。
  顺带修掉 SKILL.md `--thinking` 参数表仍写"默认 high"、档位列表漏 `xhigh` 的历史遗留
- **Hy3 限免日期**：截止仍为 **2026-08-31**（08-02 官方公告已是此日期），本次记为
  `reconfirmedOn: 2026-08-12` 用户再次确认活动延续。⚠️ 连延 3 次不代表有第 4 次，08-31 前留切换预案
- **SKILL.md 模型档位块重写**：`第一顺位 cb/hy3@high → 默认落点 cb/deepseek-v4-flash@xhigh →
  升档 cb/minimax-m3@xhigh（唯一条件：flash 已做砸过）→ 极致 cb/kimi-k3-2@xhigh`。
  「⛔ 不做预防性升档」保持不变（v8.9 之前两次实测支撑）
- **派发前自查表新增两行**：派 Hy3 前先探活（额度耗尽会进排队，长任务卡住且 Paseo 侧未必可见）+ 先过五条排除
- **§4 降级链补触发条件**：`Hy3 → cb/deepseek-v4-flash` 此前只写"cb 限额"，
  实际还包括免费额度耗尽 / 排队 / 命中排除清单三种情形
- **顺带修一处旧矛盾**：§3「限免期结束后 Qwen3.8-Max 0.05x 接棒成为默认」与
  同节「限免结束后日间默认 V4-Flash」互斥，按约束 4-1 统一为 cb 侧回落 flash、夜间走 qcn
- catalog：新增顶层 **`dispatchDefaults`**（机器可读：`codebuddyDefaultModel` / `promoFirst.excludeWhen` /
  `escalation` / `supersedes`）；hy3 加 `dispatchRank:1` + `promo.reconfirmedOn`，`bestFor` 补
  robust/doc/kb/bugfix，`avoidFor` 补 algorithm/multimodal；flash 加 `dispatchRank:2`；
  两者 `paseo` 块写死各自 thinking。版本 3.8.0 → **3.9.0**
- 三处物理副本（`~/.claude/skills`、`~/.agents/skills`、`~/.config/opencode/skills`）已同步；
  `~/.codebuddy/skills` 是指向 `.claude` 的软链，自动跟随

**异构审查（`opencode run --pure -m github-copilot/gpt-5.4`，只读）抓到 2 条，均已核源确认并修复**

- ❌ **本次改动引入的真回归**：SKILL.md 伪代码 P6 写成
  `if is_night() and (not active_promo or hy3_excluded): model = qwen3.8` ——
  夜间会把上一步按类型选出的 **M3/K3 无条件冲掉**。改前 `not active_promo()` 在限免期恒假、分支根本不触发，
  是我把 `hy3_excluded` 加进条件后才让它变成活路径。
  修为 `if is_night() and model == 'deepseek-v4-flash'`：**夜间替换只作用于默认落点**。
  补充依据：`qwen3.8-max-preview` 自身 `avoidFor` 就含 `architecture-deep`，拿它顶架构任务是降档不是省钱
- ⚠️ **排除清单漏一类**：§1 表把 `perf` 标 ⛔（走 M3），但约束 4-3 的判定清单里没有 `perf` ——
  照清单实现会把性能任务误派给 Hy3。已补 `perf` 行，并在两处加「本表与 §1 标 ⛔ 的行必须一一对应」的维护约束
- 连带澄清一处我自己写错的话：原写「命中排除项时夜间落 qcn 而不是 flash」——
  对 `doc`/`batch` 成立，对 `algorithm`/`perf`/`architecture` 是错的（那三类夜间照走 M3/K3）。已改正
- 顺带修伪代码步骤号重复（两个 `# 6.`）+ `thinking` 在第 8 步会覆盖掉第 5 步给 hy3 定死的 `high`
- catalog 新增 `dispatchDefaults.nightSubstitution`（含 `mustNotDowngrade`）与
  `promoFirst.excludeFallbackNote`（排除后不是一律落 flash，三类走各自既有映射）

**复审（同评委第二轮）确认上述两条已修好，另报 1 条历史矛盾 + 1 条易误读**

- ⚠️ **K3 口径冲突（历史遗留，本次因新增 `architecture` 行被放大）**：
  P5.4 记「2026-07-23 用户实测后定弃用（反复空转、报进度就 idle、git 无产出），派发改 M3」，
  而 §2 速查表 / SKILL.md 极致档 / catalog `escalation` 仍把 `cb/kimi-k3-2`（1.62x）列为最高档。
  **本次不擅自裁定**——三处均标注「状态未澄清，待用户确认」，暂按**不自动派 K3**处理：
  `algorithm` / `architecture` 一律走 M3，K3 仅在用户显式 `--model k3` 时派。
  § 1 表两行的 "M3 / K3" 已改回单一 M3
- 💡 **§3 路由规则第 3 条「夜间 22:00-08:00 优先 qcn」易被读成「夜间第一顺位是 qcn」**：
  该条比较的其实是「opencode 官方 DeepSeek vs qcn」两个自费/订阅通道，与 Hy3 无关。
  已就地加注：限免期内先于 qcn 的是 Hy3 0.00x，且夜间换 qcn 只替换默认落点 flash

## v8.9 (2026-08-02)

V4-Flash 补测 thinking=max（回应用户质疑「别人测评它最高分，为啥我们不是？测过最强思考强度没？」）。

**结果：max 总分 89 < high 96，且三题方向不一致**

| 题目 | high | max | 差 |
|---|---|---|---|
| LRU Cache | 32 | **35** | +3 |
| 并发 Bug | 32 | **28** | -4 |
| Kafka 架构 | 32 | **26** | **-6** |
| 总分 | **96** | **89** | **-7** |

**降分根因统一：max 多产出的细节里有编造，且编造得很像真的**

- 并发题：虚构 bug「cancelOrder 引用未定义变量 `quantity` 致 NaN 退款」，原始代码实为 `price * order.quantity`（正确）。评委独立核对原始 prompt 后确认是幻觉。伤害扩散三处——针对不存在问题的测试 #6、错误代码注释、挤占真问题篇幅
- Kafka 题：`consumer.seekToEnd()` 被描述为「延迟未到期消息」（实际把分区 position 移到末尾**跳过消息造成丢失**）；`cleanup.policy=compact,delete` 用在 order 事件流且 key=orderId，声称支持「审计重放」（实际 compaction 销毁它要保留的事件历史）；`log.start.offset` 恢复 producer sequence 表述不准确；Saga 自相矛盾——happy path 是 Reserve→Charge，partial-failure 却写成 Payment→Reserve→failed，且库存失败时直接退款而按其自身流程当时尚未付款

**规律（与 Hy3 方向相反、机制相同）**：任务可验证性越低（架构设计、依赖领域知识的配置细节），max 编造风险越高；越是纯实现题（代码逻辑可直接 trace、编造无处藏），max 越可能真更好——这解释了唯独 LRU 涨分。Hy3 是过度设计导致实现题崩，V4-Flash 是编造细节导致设计题崩，共同点是**max 多出来那部分不可信**。

- catalog 新增 `deepseek-v4-flash.blindEvalAtThinking.max`（含完整降分归因），版本 3.7.0 → 3.8.0
- 方法论改进：本轮判分 prompt 额外提供**原始题目存档**（`ORIGINAL-PROMPT-concurrency.md`），要求评委逐条核对模型断言是否与原始代码相符——正是这一步抓出了 B6 幻觉。后续测评应沿用
- 产出物：`~/AgentWorkspace/tmp/v4flash-benchmark/`（3 份 max 输出 + 3 份评分 + 原题存档）


## v8.8 (2026-08-02)

同步 CodeBuddy 官方 Hy3 限免延期公告，并落地公告里两条此前没有的路由约束。

- **限免延期**：Hy3 免费期 `2026-08-05` → **`2026-08-31`**。全文日期引用同步更新（P5 优先级、速查表、§3 时段策略、§3 限免活动）
- **延期史记录**：原定 ~07-20 → 07-22 → 08-05 → 08-31，已连续延 3 次。catalog 里写明「不要假设会继续延，08-31 前留好切换预案」
- **🆕 约束一：Hy3 无多模态能力**。官方明确——调用 Hy3 执行视频/图像等生成任务时会切换到多模态模型完成，**按正常规则消耗积分**。即「派 Hy3 = 零成本」只在纯文本/代码任务下成立。已写入 P5 决策优先级的例外条款 + §3 详述：多模态任务不要因为"Hy3 免费"而派它，既没省钱也拿不到 Hy3 的能力特征
- **🆕 约束二：每日免费额度有限，繁忙会排队**。官方称当日资源紧张时进入排队并提示重置时间。风险是长任务派进排队通道会卡住，已写入 P5 例外 + §3：先发极短任务探活，撞排队按降级链走 `cb/deepseek-v4-flash`（0.06x）
- **官方错峰窗口**：每晚 **23:00–次日 08:00** 资源更充足。已在 §3 用对照表标明它与既有夜间策略的 **1 小时错位**——22:00–23:00 只有 qcn 已进夜间折扣、Hy3 仍可能排队。**顶部「硬性约束 2」的夜间默认走 `qcn/qmodel_preview` 保持不变**，本条只作为事实补充供判断（纯文本且 B 级够用时，23:00 后 Hy3 可做到真 0 消耗）
- catalog：`hy3.promo.end` 更新 + 新增 `hy3.limitations`（`noMultimodal` / `dailyQuota` / `nightWindow` 三条），版本 3.6.0 → 3.7.0

## v8.7 (2026-08-02)

GLM-5.2 全面禁用落实到所有表格（此前只写在顶部约束段，下方表格仍在推荐它，自相矛盾）。

- 用户反馈：**GLM-5.2 实际使用比较费，不推荐**
- 数据印证（盲评总分 ÷ cb 费率）：GLM-5.2 = 101/0.79 = **128**，全部可派模型**倒数第二**（仅优于 K3 的 68）；
  M3 = 114/0.25 = **456**（分数更高 114 vs 101，费率便宜 3 倍多）；V4-Flash = 96/0.06 = **1600**。
  对比"更强的"和"更省的"两个方向都无留存价值，禁用有充分依据
- **落实此前未同步的约束**：顶部「硬性约束 2」（08-02）已声明 cb/glm-5.2 禁用，但下方 6 处表格仍把它当推荐目标——
  §1 `robust`/`doc` 任务映射、P5.4 决策优先级、§2 速查表、§4 费率对比表、§4 降级链，全部改派 `cb/deepseek-v4-flash`（需更强时 `cb/minimax-m3`）
- **修一处过时矛盾**：§0（07-28 约束）原写"qcn 禁用后 GLM-5.2 改走 `cb/glm-5.2`"，而 cb 版现已一并禁用，
  该指引在指向已禁用目标，已就地标注失效并给出正确替代
- catalog：`glm-5.2` 加 `deprecated` 说明（含性价比数据）、tier 改 `A (禁用)`、两个 provider 均标 `disabled: true`、
  `bestFor` 清空、`avoidFor` 写明替代方案
- 版本 3.5.0 → 3.6.0

## v8.6 (2026-07-30)

新增 DeepSeek-V4-Flash 实测（96 分 / 0.06x，取代 V4-Pro）+ 修 2 个失效 model id + scnet/xfyun 下线 + opencode 官方 DeepSeek 定位。

**V4-Flash 盲评（GPT-5.5，thinking=high 同历史口径）**
- LRU 32 / 并发 32 / Kafka 32 = **总分 96，A 级**，三题完全均衡（全部已测模型中唯一无短板的）
- 费率 **x0.06 credits**，是 V4-Pro（0.13x）的一半
- **结论：V4-Flash 以 96 分 / 0.06x 全面取代 V4-Pro（86 分 / 0.13x）**——分数高 10 分、费率减半，V4-Pro 标记为不再推荐
- 亮点：并发题正确判断"JS 单线程无需加锁"（Hy3 在 max 下正是此处翻车）；提出 Postgres READ COMMITTED 的 **EvalPlanQual** 机制论证条件 UPDATE 可防超卖，评委复核确认该技术断言正确
- 决策树调整：core/test/batch/robust/doc/kb 的默认链插入 V4-Flash；新增 `concurrency` 任务类型指向 V4-Flash

**🔴 修复 2 个会导致派发直接失败的失效 model id**（对照 `paseo list_models` 实测）
- `minimax-m3` → **`minimax-m3-pay`**（M3 是 114 分最高分、决策树"质量优先"首选，旧 id 派发必失败）
- `kimi-k3-1` → **`kimi-k3-2`**
- V4-Pro cb 费率实测已从 0.16 降至 **0.13**，同步更正

**scnet / xfyun 下线（额度耗尽，用户指示）**
- Mac `opencode.json`：删除 scnet（7 模型）+ xfyun（1 模型）provider 配置
- **连带修复**：`oh-my-openagent.json` 有 26 处引用 scnet 模型（6 处是 agent/category 的**主 model**，删 provider 后会直接坏掉），全部替换为 github-copilot 等价物（订阅制边际成本 0，不动用自费 DeepSeek）；20 处 fallback 死项清除
- Hub 端同样清理（Hub 的 opencode.json 本就没配这两个 provider，但 OMO 里 26 处引用一直是失效的，本次一并修好）
- MiMo-V2.5-Pro 为 scnet 独占，随之从 catalog 下架

**opencode 官方 DeepSeek 的决策树定位（新增 §3 专段）**
- 明确"两个钱包"：`cb/deepseek-v4-flash` 花 codebuddy **订阅额度**；`deepseek/deepseek-v4-flash` 花**用户现金**且有峰谷 2 倍
- 官方定价存档（v4-flash $0.14/$0.28 per 1M，cache hit 仅 $0.0028）
- 峰谷：高峰 **09-12 / 14-18**（北京时间）×2；低谷 12-14 + 18-次日09
- 路由规则：默认不走官方 API → 高峰绝对避免 → 夜间 22-08 优先 qcn 0.01x → 官方 API 的真正价值窗口是 **18:00-22:00**（DeepSeek 已低谷但 qcn 夜间折扣未开始）、12:00-14:00、以及 cb/qcn 额度耗尽兜底、大上下文反复问时的 prompt cache（$0.0028 比 miss 便宜 50 倍）

产出物：`~/AgentWorkspace/tmp/v4flash-benchmark/`（3 份原始输出 + 3 份 GPT-5.5 评分 + 定价参考 + Hub 清理脚本）

## v8.5 (2026-07-30)

消除文件内自相矛盾：`model-routing.md` §Provider 笔记里"派 Hy3 必须开 max"与 §2 实测结论冲突，按评分数据统一为 high。
- 背景：2026-07-28 有外部写入往 `model-routing.md` provider 段追加了运维笔记，其中一句"**codebuddy Hy3** 限免 0.00x 仍可用，派它时**必须 `thinkingOptionId: max`**"把 v8.3 已删除的错误指引又加了回来
- 造成同一文件自相矛盾：第 86 行（v8.4 实测结论）写"不建议默认给 Hy3 开 max"，第 179 行写"必须开 max"
- 依据 v8.3/v8.4 两轮 GPT-5.5 盲评数据裁定：max 均值 85.5 < high 91.5，且 LRU 类实现题两轮都因过度引入并发原语翻车 → "必须开 max"是错的
- 修正 179 行为"thinking 用默认 `high`，不要开 max"，并在原地标注被证伪的依据（指向 §2 对比表），防止后续再被改回
- 保留同段真实运维信息：qoderclicn 2026-07-27 晚已换新账号恢复可用（旧账号 `FORBIDDEN code:112`）、派发前先探活避免长任务进断供通道
- scnet 补注"v8.2 起已从 provider 列表移除"，说明为何 provider 表里已无此项
- 三处物理副本（`~/.claude/skills`、`~/.agents/skills`、`~/.config/opencode/skills`）此前不一致（.claude 208 行 vs 两处副本 191 行），本次统一

## v8.4 (2026-07-20)

Hy3 thinking=max 复测（用户对 v8.3 单次结果提出样本量质疑），补第二轮验证结论。
- 用户原话质疑："你要在跑一次试试 Max 还不如 high?" —— 合理，N=1 不能下系统性结论
- 复测同样 3 题（LRU/Kafka 逐字同题，并发题仍用 v8.3 的重建版），结果：LRU 16→26、并发 31→27、Kafka 36→35，总分 83→88
- 均值：LRU 21 / 并发 29 / Kafka 35.5 / 总分 85.5，仍低于 high 的 91.5，但差距从单次的 -8.5 收窄到均值 -6
- **关键发现**：LRU 题两轮独立复现"过度设计并发原语导致 bug"这一模式，但两次是不同的具体 bug（Run1: 类型不自洽的 async Mutex 包装；Run2: 全 async API 类型自洽，但 capacity 淘汰路径对同一节点重复 detach 导致链表损坏）——同一根因（不必要地为本就线程安全的同步方法加锁）连续两次触发不同故障，判定为可复现的系统性弱点而非采样噪声
- Kafka 架构题两轮均稳定高于 high（36、35 vs 33），确认 max 对架构/方案设计类任务有正向收益
- 结论细化：不再是笼统"不建议开 max"，改为按任务类型区分——架构/方案设计类可考虑 max，数据结构实现/并发控制类保持 high
- model-catalog.json `blindEvalAtThinking.max` 改为 `runs` 数组 + `avg` 汇总，保留两轮原始数据不覆盖
- 派发与评分产出物：`~/AgentWorkspace/tmp/hy3-max-benchmark/`（`*-run2-*-raw.txt` + `gpt55-run2-*-score.txt`）

## v8.3 (2026-07-20)

Hy3 补测 thinking=max，纠正此前"限免期必开 max"的错误指引。
- 新增：`model-catalog.json` benchmark 元数据加 `thinkingLevel` 字段，明确历史所有 blindEval 分数默认口径为 thinking=high
- 新增：hy3 条目加 `blindEvalAtThinking.max`（LRU 16 / 并发 31* / Kafka 36，总分 83），GPT-5.5 同评委盲评，LRU/Kafka 逐字同题；并发题原 prompt 未存档，用其余模型诊断结果反推等价代码重建，标注为不完全可比
- **关键发现：thinking=max 总分（83）反而低于 thinking=high（91.5）**，根因是 LRU 任务下 max 模式引入了不必要的 async Mutex 包裹同步 API，导致 `get()`/`delete()` 声明返回同步值实际返回 Promise，TypeScript 编译不过（correctness 22→16）；Kafka 架构题 max 确有提升（33→36）但不足以抵消
- 修正：删除 model-routing.md 中此前"限免期派 Hy3 必须显式设 thinkingOptionId: max"的指引（该指引基于未经验证的假设，与本轮实测结果矛盾），改为默认保持 thinking=high
- 派发脚本与产出物：`~/AgentWorkspace/tmp/hy3-max-benchmark/`（3 份原始输出 + 3 份 GPT-5.5 评分 + 派发记录）

## v8.2 (2026-07-20)

移除 scnet provider（Token Plan 额度耗尽）+ 移除 qoderclicn 到期优先权重（用户要求，不再用"额度快过期"驱动模型选择）。
- 删除：scnet provider 及其所有引用（Provider 类型表、降级链、跨 provider 费率对比表 sc 列）
- 删除：MiMo-V2.5-Pro 模型（scnet 独占，无其他 provider，随 scnet 移除一并下架）
- 删除：GLM-5.2 / K2.7-Code / K2.6 的 scnet 分支（保留 codebuddy-code / qoderclicn 分支）
- 降级链调整：K2.7 codebuddy 限额时改为"无替代，报告用户"（原 scnet 备选已移除）；GLM-5.2、K2.6 降级链去掉 scnet 二级跳转
- 删除：P5.5「qoderclicn 额度到期紧迫」决策优先级、§3「qoderclicn 额度到期策略」整节、providerExpiry 中 qoderclicn 账号余额与到期日标注
- Qwen3.8-Max 相关文案去掉"消耗 qcn 到期额度"措辞，保留"限免后日间默认"等基于自身性价比的推荐理由
- model-catalog.json `providerExpiry` 清空为 `{}`
- 影响：qoderclicn 仍是正常可用 provider，只是不再被到期紧迫度驱动优先级；scnet 完全下线

## v8.1 (2026-07-21)

新增 Qwen3.8-Max-Preview + Hy3 延期 + qoderclicn 额度到期策略。
- 新增：Qwen3.8-Max-Preview（`qmodel_preview`）— A tier 101.5/120，0.05x 日间 / 0.01x 夜间（qoderclicn 限时1折）
- Hy3 限免再次延期：07-22 → 08-05
- qoderclicn 额度到期策略：账号1 639cr@07-25 / 账号2 1367cr@07-28，决策优先级插入 P5.5
- 任务分类 fallback 链调整：core/test/batch 的 Hy3 后备从 V4-Pro 改为 Qwen3.8-Max → V4-Pro
- 时段策略更新：夜间首选 Qwen3.8-Max 0.01x（A 级最低价）
- 降级链新增 Qwen3.8-Max → cb/hy3（限免期）或 cb/deepseek-v4-pro
- 费率表新增 Qwen3.8-Max qcn 独占

## v8.0 (2026-07-20)

新增 K3 模型 + 全量 GPT-5.5 盲评统一口径。
- 新增：Kimi-K3 (`kimi-k3-1`) — S tier 110.5/120，codebuddy 独占，1.62x credits（最贵）
- 盲评统一：Hy3/Opus 4.6/Sonnet 5/MiMo 从 GPT-5.4 重评为 GPT-5.5，全部 13 模型现为同一评委口径
- Hy3 限免延期：~07-20 → 07-22 23:59:59
- 费率更新：V4-Pro 0.25x→0.16x（降 36%），K2.7 0.59x→0.57x
- Tier 变动：Opus 4.6 从 B(92) 升 A(97)
- K3 稳定性注记：thinking=high 在复杂架构题偶发陷入长时间推理不输出（概率性，非必现）
- model-catalog.json 版本 3.0.0，所有 blindEval 数据统一为 GPT-5.5

## v7.0 (2026-07-08)

重构：拆分为 SKILL.md + model-routing.md + model-catalog.json + CHANGELOG.md。
- GPT-5.4 架构审查发现 6 个阻塞级问题（Claude 模型定位矛盾、V4-Pro provider 冲突、夜间规则不自洽、费率冲突、未定义降级目标、职责边界不清）
- SKILL.md 精简为纯派发流程 + 伪代码（~150 行）
- model-routing.md 统一所有模型选择/provider 路由/降级链（单一真源）
- 修复：Claude 模型明确为"⛔ 参考标杆·不派发"，从决策树移除
- 修复：V4-Pro 首选 provider 统一为 codebuddy（0.25x）
- 修复：夜间例外清单明确列出
- 修复：降级链移除不存在的 glm-4.7 目标
- 新增：决策优先级伪代码（9 级，P1-P9）
- 新增：多标签冲突裁决规则
- 新增：Memory 记录最小字段模板
- 新增：Skill 完成定义

## v6.1 (2026-07-08)

全文清理 hy3-preview 残留引用；短名映射加 `hy3`；
性价比排名、决策树、对照表、能力速查表统一更新为 Hy3 正式版 + 0.00x 限免。

## v6 (2026-07-06)

Hy3 正式版上线（model ID: `hy3`，`hy3-preview` 已下架）；
限免两周 0.00x（~07-06 至 ~07-20）；盲评 89 分 B tier（GPT-5.4）。

## v5.1 (2026-07-05)

Opus 4.6 + Sonnet 5 参加盲评（GPT-5.4 裁判）；
Sonnet 5: 112/S tier；Opus 4.6: 92/B tier；
MiMo-V2.5-Pro GPT 评分修正 100→82/B tier。排名扩展至 12 模型。

## v5 (2026-07-05)

新增 SCNet provider（中国科技云 Token Plan，截止 2026-07-30）；
新增 MiMo-V2.5-Pro（SCNet 独占）；降级链扩展为三级。

## v4 (2026-06-30)

Paseo list_models 实时费率替换旧数据；Hy3 降价 51%；GLM-5.2 降价 25%；
Qwen 夜间费率独立标注；每个分支标注 credit 费率。

## v3 (2026-06-28)

qoderclicn 限时免费优先策略。

## v2 (2026-06-28)

删除臆想的"配额优先"分支，改为错误触发降级。

## v1 (2026-06-28)

GPT-5.5 审查后优化：batch 拆调度/执行、test 三级、新增 algorithm 分支。9 模型盲评。
