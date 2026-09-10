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
T0  免费档   cb/hy4-preview @high     0.00x   ⭐ 第一顺位（免费至 **09-10**，⚠️ 每日赠送额度）
             cb/hy3         @high     0.00x   次位（免费至 08-31）
              ↓ 命中 §2 排除清单，或免费期已过
T1  低价档   glm-5.3-flash        @xhigh          付费档起步
             ⭐ provider 由 §3.5 的 WALLET_PREF【轮换】+ 折扣窗口决定，⛔ 不是固定首选
             ⚠️ 2026-09-08 才发现火山也有它，此前只配了 cb
              ↓ 上一档在【本任务】做砸过一轮
T2  主力档   deepseek-v4-flash    @xhigh          DeepSeek 族首选
             ⭐ provider 由 §3.5 的 WALLET_PREF【轮换】+ 折扣窗口决定，⛔ 不是固定首选
              ↓ 上一档在【本任务】做砸过一轮
T3  升档     deepseek-v4-pro      @xhigh          ⛔ selectableByDefault=false
             ⭐ provider 同上轮换（⛔ 京东已停用）；四池全拿不到时 → 同档替代 qwen3.8-max（§9.1）
              ↓ 上一档在【本任务】做砸过一轮
T4  极致档   cb/kimi-k3-2         @xhigh  1.62x   🔴 红线，见 §3.3
```

**每一级【质量/成本升档】的唯一入口都是「上一档已在本任务做砸过一轮」。**
⚠️ 这条⛔**不管【可用性换档】**——模型在所有 provider 都拿不到时允许向上换档，但**必须报告**（§8）。
⛔ 不做预防性升档——「任务难 / 重要 / 风险高」不是理由，两组实测（n=1、n=12）都推翻了它（§9.2）。
风险高该提的是 **thinking 档位**和**审查强度**，不是模型档位。

⚠️ 任何「换更便宜 provider」的替换**只作用于当前默认落点**，
⛔ 不得把已按需要升上去的档位降回来（2026-08-12 异构审抓到伪代码会无条件冲掉高档模型）。

### 免费档时间线

```
08-31  hy3 免费止   → hy4 顶上（本就是第一顺位）
09-10  hy4 免费止   → 免费档清零，默认落点变成 T1 的 glm-5.3-flash
       🔴 2026-09-09 用户更正：原记「09-12」是**错的**，实际 08-28 ~ **09-10**
```

⚠️ **09-10 后不要自动落回 `hy4-preview-x`**：它是 0.29x，比 T2 的 v4-flash 还贵。

### ⚠️ `-x` 后缀：同 label、两个 id、一免费一收费

| id | 费率 | |
|---|---|---|
| `hy4-preview` | **0.00x** | 免费至 **09-10**（每日赠额） |
| `hy4-preview-x` | **0.29x** | ⚠️ 同名收费版 |
| `hy3` / `hy3-x` | 0.00x / 0.05x | 同一模式 |

🔴 **派发认 id，⛔ 不认 label** —— 两个 id 的 label 都是「Hy4 preview」，按 label 匹配会选错。

---

## 1. Provider 白名单（P0，优先级最高于一切）

**对【白名单 provider】（`codebuddy-code` / `qoderclicn`）：不在其清单里的 model id 一律禁止派发**，包括本文件其它表格里出现过的。冲突时以本表为准。
⚠️ **豁免 provider** 走**另一套**校验 —— 它们不消耗 cb/qcn 额度，⛔ 不受本表约束。
🔴 **校验对象是 `split_provider()` 之后的 upstream，⛔ 不是顶层 `pi`。**
⛔ `pi` 是**宿主**，把它当豁免会让 `pi/jdcloud-joyagent/...` 整条绕过 upstream 校验（0909 第 6 轮审查）。
⇒ 实际豁免集（`EXEMPT_PROVIDERS`）= 火山×3 · 百炼 · Copilot · claude · codex · opencode。
⇒ `LAST_RESORT` 的 `claude/claude-sonnet-5` 走豁免集，⛔ **不是违例**。

| Provider | model id | 费率 | 角色 |
|---|---|---|---|
| `codebuddy-code` | **`hy4-preview`** | **0.00x** | ⭐ T0 第一顺位（至 **09-10**） |
| `codebuddy-code` | `hy3` | 0.00x | T0 次位（至 08-31） |
| `codebuddy-code` | **`glm-5.3-flash`** | **0.06x** | T1 低价档（2026-08-28 开启） |
| `codebuddy-code` | `deepseek-v4-flash` | **0.17x** | T2 主力档，DeepSeek 族首选 |
| `codebuddy-code` | `deepseek-v4-pro` | **0.51x** | T3 升档，⛔ 非任何类型的默认落点 |
| `codebuddy-code` | `kimi-k3-2` | **🔴 1.62x** | T4 极致档，⛔ 见 §3.3 红线 |
| `qoderclicn` | `qmodel_38max` | 0.50x | cb 整体断供时的降级落点，不主动选 |
| ~~`jdcloud-joyagent`~~ | ~~两个 DeepSeek~~ | — | ⛔ **2026-09-09 停用**（额度用尽），配置已归档，见 §3.4 |

**⛔ cb 已关闭**：`minimax-m3` · `minimax-m3-pay` · `minimax-m2.7` · `glm-5.3` · `glm-5.2` · `glm-5.1`
· `glm-5v-turbo` · `kimi-k2.7` · `kimi-k2.6` · `hy4-preview-x` · `hy3-x`
**⛔ qcn 已关闭**：`qmodel_38max` 以外全部
**⛔ jd 不派发**：`GLM-5.2` · `GLM-5.1` · `Kimi-K2.6` · `MiniMax-M2.7` · `qwen3.6-27b` · `qwen3.6-35b-a3b` · `qwen3-vl-235` · `JoyAI-LLM-Flash` —— 这 8 个**已在 pi 配好且实跑通过**，⛔ 但用户 2026-09-08 明确「JD 云仍然只使用 DeepSeek」

**不受白名单约束的通道**（走别的钱包，不消耗 cb/qcn credits）：

| 通道 | 说明 |
|---|---|
| `pi/volcengine-coding/*` · `pi/volcengine-agent-plan/*` | 火山按月套餐，§7 |
| `pi -p --provider github-copilot` | 审查硬例外，§5 |
| `claude/*` | ⚠️ 可派但不推荐——消耗 Claude 订阅额度，建议留给主会话。⭐ **例外：`claude-sonnet-5` 作为 LAST_RESORT 自动可达**（§8） |
| `codex/*` | Paseo 派发 provider，定位不变 |
| ~~`jdcloud-joyagent/*`~~ | ⛔ **不在本表** —— 它虽是独立钱包，但同样受白名单约束（只准 DeepSeek），见上表与 §3.4 |
| `opencode run --pure` | 🔻 **执行适配器的兜底**（三条通道都不可用时才用），无常规用途，§7 ⚠️ ⛔ 与「可用性降级链的 `LAST_RESORT`」是两码事 |
| ~~`deepseek/*`（官方 API）~~ | 🔴 2026-08-20 已加入 `disabled_providers`。⛔ 不在自动降级链里，只能**手动**用（§3.5） |

---

## 1.b 🔴 屏蔽名单（`BLOCKED_MODELS`，用户 2026-09-09 点名）

⛔ **与白名单/豁免集正交** —— **豁免 provider 也拦得住**。
（否则 `--provider github-copilot --model gpt-5-mini` 会因为 copilot 在豁免集里而直接放行。）

| provider | 屏蔽的型号 |
|---|---|
| `volcengine-coding` | `doubao-seed-2.0-lite` · `doubao-seed-2.1-turbo` |
| `volcengine-agent-plan` | 上面两个 + `doubao-seed-2.0-mini` · `doubao-seed-evolving` · `ark-code-latest` |
| `github-copilot` | `gpt-5-mini` · `gpt-5.3-codex` · `gpt-5.4-mini` · `gemini-3.5-flash` · `gemini-3.6-flash` · `mai-code-1-flash-picker` |

### ⚠️ 两个 provider 的屏蔽手段**不一样**（2026-09-09 实测）

| | 从 `~/.pi/agent/models.json` 删条目 | 靠 skill 的 `BLOCKED_MODELS` |
|---|---|---|
| **火山两个 plan** | ✅ **有效**（只在 models.json 里定义，无 store 兜底）⇒ 已移除并归档 | ✅ 双保险 |
| **`github-copilot`** | ⛔ **无效** —— pi 回落 `models-store.json`（etag 自动刷新，改它会被冲掉）。实测删掉 `gpt-5-mini` 后**照样调得通** | ✅ **唯一有效手段** |

🔴 **顺带证伪一条旧记录**：skill 曾写「Claude 全族靠 models.json 覆盖 store 移除」——
实测 store 里 `claude-*` **8 个全在**，`pi --list-models` 也看得到，但真发请求返回
**400 `model_not_supported`** ⇒ **是 GitHub 服务端拦的，⛔ 不是我们配的**。
⚠️ 结论没错（调不到），**归因错了** —— 而归因错会让人照着它去屏蔽别的模型，做完还以为成了。

⛔ **判断屏蔽是否生效，判据是【真发一次请求返回什么】，⛔ 不是【`--list-models` 里有没有】。**

### ⚠️ 5 个待测型号（⛔ 有分之前别当默认用）

`grok-4.5` · `grok-4.6` · `mai-code-1.1-flash` · `gemini-3.7-flash` · `gemini-3.8-flash`
—— 用户 2026-09-09：「不清楚性能如何，可以做个参考进行评分测试」。已排入三题盲评。
⚠️ 本轮走 `pi -p`（⛔ 无 agent 系统提示），与既有 /120 榜**不同口径** ⇒ ⭐ 只在这 5 个之间可比。

📎 恢复路径：`~/.pi/agent/providers-disabled/blocked-models-20260909.json`（含 `_howToRestore`）。
⚠️ 恢复时**两处都要改**：`models.json` + skill 的 `BLOCKED_MODELS` / catalog `blockedModels`。

## 2. 免费档排除清单（唯一真源）

命中任意一条 → **跳过 T0**。⚠️ ⛔ 这只决定「跳不跳 T0」——**付费起步档另按 §6 / catalog `entryTier` 定**（`algorithm`/`perf` → T2，`architecture` → T1）。
`free_blockers(task_type, args)` 返回命中项代号的 `set()`，空集表示不排除。

### 2.a 物理不可用类 —— ⛔ `--free` 也不放宽

绕过去**也拿不到免费**，只会静默变成付费或死循环。

| 条件 | 代号 | 依据 |
|---|---|---|
| 图像 / 视频 / 多模态 | `multimodal` | 官方 0802 公告：会切多模态模型并**正常计费**，免费不成立 |
| 当日免费额度耗尽 | `quota_exhausted` | 免费档物理不可用 |
| 探活未秒回（排队） | `probe_queued` | 官方 0802 公告：繁忙进排队，长任务会卡住 |
| 免费档已在本任务做砸过一轮 | `failed_this_task` | 同升档逻辑；绕过会死循环 |

### 2.b 能力类 —— ✅ `--free` 可放宽（`CAPABILITY_BLOCKERS`）

是**能力短板**判断，用户显式 `--free` ⇒ 视为接受能力风险。

| 条件 | 代号 | 依据 |
|---|---|---|
| 算法 / 精细数据结构实现 | `algorithm` | hy3 盲评 LRU **22 分**，唯一明显短板 |
| 性能优化 / 大数据量 | `perf` | hy3 无 perf 类实测支撑 |
| 架构深度设计（选型 / 拓扑 / 一致性方案） | `architecture` | catalog `avoidFor: architecture-deep` |

### 2.c `--free` 的判定

```
blockers ⊆ CAPABILITY_BLOCKERS  ⇒ 放宽，走 T0
否则                            ⇒ 停止并报告，⛔ 不静默转付费
```

⚠️ T0 只跑在 `codebuddy-code` 上 ⇒ `--provider codebuddy-code` 与 `--free` **不冲突**。
⚠️ `--free` 与 review 硬例外（§5 固定 `gpt-5.5`）**冲突** ⇒ 报告让用户选，⛔ 不替他决定。

⛔ **本表与 §6 任务分类表中标 ⛔ 的行必须一一对应**，改一边要同步另一边。
2026-08-12 异构审抓到过一次漏判：表里写着不适用、清单里查不到，实际派了出去。

### ⚠️ 这份清单是给 Hy3 定的，对 Hy4 未验证

Hy4 的 LRU 拿了 **35 分**（hy3 只有 23），说明「algorithm 是短板」这条对它**很可能不成立**。
在补测之前 Hy4 沿用本清单属于保守处理，可能低估了它。

⚠️ **hy4 是「每日赠送额度」，⛔ 不是连续免费期**

⚠️ 当日额度用完会被限：**不回复 = 已被限**，⇒ 必须**主动换模型**，⛔ 不要干等。
这让「派长任务前先探活」这条纪律更重要——探活不秒回就直接落 T1。

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
DeepSeek 的族偏好现在体现为「【质量/成本升档】：T1 做砸过一轮才升 T2（⚠️ **可用性换档⛔不受此约束**（见 walletPriority.availabilityEscalation / routing §8）。）、不跳去别的族」，
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
| ② **v4-pro 也已在本任务做砸过一轮** | **质量/成本升档**的唯一入口（⛔ 可用性换档不受此约束） |

**⛔ 以下都不构成理由**（每条都被实测或成本算术否掉）：

- ❌「任务看起来很难 / 很重要 / 风险高」→ 模型档位不是质量关口（§9.2）
- ❌「这是 algorithm / architecture 类，K3 分最高」→ 这两类**起步档不同**：`algorithm` 从 **T2** `deepseek-v4-flash` 起、`architecture` 从 **T1** `glm-5.3-flash` 起；之后按 【质量/成本升档】（本任务做砸过一轮）逐级升，⛔ 不因分高预防性升档
- ❌「反正只跑一次」→ 一次 K3 ≈ 9.5 次 v4-flash ≈ 27 次 glm-5.3-flash
- ❌「先用好的保险一点」→ 这就是「预防性升档」的原话，明令禁止

⚠️ **可靠性前科**：2026-07-23 实测出现反复空转（报进度就 idle、git 无产出）。
⇒ 派了 K3 **必须核 `git log` 是否真有 commit**，不能只看它报进度。
花 9.5 倍的钱还拿不到产出，是这个模型特有的失败模式。

⚠️ K3 撞限额在**白名单内没有替代**（M3 已关闭）。
⇒ 🔴 **2026-09-09 起走 `LAST_RESORT = claude/claude-sonnet-5 @ max`**（§8），⛔ 不再是「只能报告用户」。连它也拿不到才停止。

---

### 3.4 ~~京东云 JoyAgent 通道~~ ⛔ **2026-09-09 已停用**

🔴 **停用原因**：用户 2026-09-09 —— **额度用尽，消耗太快不划算**。已从 `~/.pi/agent/models.json` 移除。
⚠️ **不排除以后再用** ⇒ provider 配置完整归档在 `~/.pi/agent/providers-disabled/jdcloud-joyagent.json`，
里面带恢复步骤和「恢复后要同步改哪些字段」的清单。⚠️ 长期不用建议去控制台吊销那把 key。
⚠️ 下面内容保留作为**恢复时的参考**，⛔ 当前不生效。

**⛔ 只用 DeepSeek**（用户 2026-09-08 明确）。平台上另有 GLM / Kimi / MiniMax / Qwen 共 8 个，
已在 `~/.pi/agent/models.json` 配好并逐个实跑通过，⛔ **但不派发**——留着是为了保住实测结论，不是为了用。

| model id | 实付 积分/百万（输入/输出/缓存） | 折扣 | 上下文 |
|---|---|---|---|
| `DeepSeek-V4-pro` | **8,400 / 16,800 / 700** | ⭐ **7 折**（原价 12,000 / 24,000 / 1,000） | 1,000,000 |
| `DeepSeek-V4-Flash` | **1,400 / 2,800 / 280** | 无（1,400 即挂牌价） | 1,000,000 |

⚠️ 7 折**没有标注截止日期**（`offlineTime: null`），金额敏感时派发前复核控制台。

**积分换算：1,000 积分 = ¥1。**
⚠️ 积分**有效期一年**，⛔ 不是永久额度——与 cb credits / 火山包月 / Copilot 订阅都不同。

即使打完 7 折，**V4-pro 仍是 V4-Flash 的 6 倍**（8,400 vs 1,400）⇒
⛔ 【质量/成本升档】纪律照旧：Flash 在本任务做砸过一轮才升 pro。⚠️ 可用性换档⛔不受此约束（§8）。

### 与 DeepSeek 官方 API 的价格对比

官方 `deepseek-v4-pro`（版本 **DeepSeek-V4-Pro-0813**，官方定价页 2026-09-08 实读）：

| 项 | 京东 7 折 | 官方空闲 | 官方高峰 |
|---|---|---|---|
| 输入（缓存未命中） | ¥8.4 | **¥4.5** | ¥9.0 |
| 输出 | ¥16.8 | **¥13.5** | ¥27.0 |
| 输入（缓存命中） | ¥0.7 | **¥0.15** | ¥0.30 |

⛔ **京东不是绝对最便宜** —— ¥8.4 落在官方空闲价与高峰价之间：比空闲贵 1.87 倍，比高峰便宜 7%。
🔴 **缓存命中差得最狠**：京东 ¥0.7 vs 官方空闲 ¥0.15，贵 **4.7 倍**
（官方缓存命中只要未命中价的 3.3%，京东是 8.3%）⇒ 长上下文反复问同一份材料时，官方优势被放大。

⚠️ 官方高峰时段 = 北京时间**周一至周五 9:00-12:00、14:00-18:00**，其余为空闲
⇒ **大部分时间官方单价更低**。

⇒ 所以选京东**不是因为单价最低**，而是因为**钱包优先级**（§3.5）：
官方 API 花的是现金，京东花的是已买入的积分。

**⚠️ 实测约束**：

- **并发 6 就撞 429**（`code 1051 请求过于频繁`）⇒ 批量调用串行 + sleep 3~4s
- **推理默认开，`reasoning_tokens` 计入 `max_tokens`** ⇒ ⛔ maxTokens 不能设小
  （实测 `max_tokens=32` 时 `content` 全空、`finish_reason=length`）
- `max_tokens` 上限 **393,216**
- ⛔ 该网关 `GET /v1/models` 返回 500，**不支持模型发现**

**⭐ 与火山那份 `deepseek-v4-pro` 同代，⛔ 不是 preview**（2026-09-08 实测）：

| 观测 | 结果 | 证据强度 |
|---|---|---|
| **同轮盲评 + 架构题** | 108 vs 104；🔴 京东架构题 **37**，而 06-28 那个疑似 preview 的旧版只有 **24** | ✅ **承重的就这一条** |
| `max_tokens` 上限 393,216 | 两侧一致 | 🔻 弱——官方页写明输出上限 384K，**全代通用** |
| tokenizer（`prompt_tokens` 51,729） | 两侧一字不差 | 🔻 弱——**同族本就同分词** |
| 60k 长上下文 3/3 | 两侧全中 | 🔻 弱——官方页写明上下文 1M，**全代通用** |

🔴 **⚠️ 自我修正**：我最初把这四条并列成「四条独立证据」，其实是
**一条真证据 + 三条同族规格**。任何 V4-Pro 快照都会给出后三条一样的结果，⛔ 它们不构成区分度。
结论仍成立，但支撑面比原先声称的窄。

⚠️ 官方当前版本号是 **`DeepSeek-V4-Pro-0813`**，与 catalog 时间线对得上
（06-28 测 86 分 → 08-16 重测 96 分「正式版」）。

> ⭐ **下次判断两个 endpoint 是不是同一代，先用这两个近乎零成本的探针**：
> ① 发 `max_tokens: 500000` 的极短请求 —— 网关在计费前拒绝并返回真实上限；
> ② 同一段输入比 `prompt_tokens` —— 同 tokenizer 才会一字不差。
> ⛔ 盲评贵且有噪声，它回答的是「谁更强」，不是「是不是同一代」。

---

### 3.6 阿里云百炼 Token Plan 通道（2026-09-09 接入）

| 项 | 值 |
|---|---|
| endpoint | `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` |
| 协议 | OpenAI 兼容 |
| pi provider | `bailian-token-plan` |
| 钱包 | **已付费套餐**（Token Plan），与火山/cb/Copilot 都不同 |

🔴 **endpoint ⛔ 不是通用的 `dashscope.aliyuncs.com`** —— Token Plan 有自己的域名，
由 `bl auth status --output json` 的 `base_url` 得到。照通用文档配会连不上。

**⛔ 只用这 4 个文本模型**（用户 2026-09-09 指定）：

| model id | ctx | maxOut | 夜间 5 折 | 派发中的位置 |
|---|---|---|---|---|
| `deepseek-v4-pro-0813` | 1,000,000 | 393,216 | ⭐ 是 | T3（钱包轮换的一个落点） |
| `deepseek-v4-flash-0731` | 1,000,000 | 393,216 | ⭐ 是 | T2（同上） |
| `qwen3.8-max` | 1,000,000 | 131,072 | ⭐ 是 | **T3 同档替代**（见 §9.1 换位盲评） |
| `qwen3.8-flash` | 1,000,000 | 131,072 | ⛔ 否 | ⛔ 未定档（无实测，显式 `--model` 才用得到） |

⚠️ **`deepseek-v4-pro-0813` 不在 `/models` 目录里，但可用**（2026-09-09 实测）
⇒ ⛔ 又一次印证：**目录里没有 ≠ 不能用**，判断可用性只能直接发请求。

⚠️ **id 都带 GA 快照后缀**：是 `deepseek-v4-flash-0731` / `deepseek-v4-pro-0813`，
⛔ 不是 `deepseek-v4-flash` / `deepseek-v4-pro`（后者百炼也有，但用户没选）。

🔴 `compat.supportsDeveloperRole: false` 是**实测得出**（传 `role=developer` 报
`developer is not one of ['system','assistant','user','tool','function']`），⛔ 不是照抄火山猜的。
⛔ 依然不要加 `thinkingFormat`。

**图像模型走 `bl`，⛔ 不进 pi**：用户另指定 `qwen-image-3.0-pro` · `wan2.7-image-pro` · `wan2.7-image`，
pi 是文本 agent 用不上 ⇒ 走 `bl image`（`bailian-gen` skill）。
⚠️ `qwen-image-3.0-pro` 不在目录里、未验证——验证要真出一张图产生费用，故未做。

**CLI**：`bl 1.22.0`（volta 管，pin node@26.7.0），9 个 `bailian-*` skill 已装。
⚠️ CLI 凭据在 `~/.bailian/config.json`，与 `~/.pi/agent/models.json` 是**两份**，换 key 要同时改。

---

### 3.5 🔴 钱包优先级（与档位阶梯正交）

**档位阶梯（§0）决定【用哪个模型】；本节决定【从哪个 provider 拿】。⛔ 别把两者混成一件事。**

用户 2026-09-08 定的钱包顺序 —— 先花已经付过钱的，最后才动现金：

| 顺位 | 钱包 | 性质 | 边际成本 |
|---|---|---|---|
| ① | **火山** · **阿里云百炼 Token Plan** · **codebuddy credits** | **已付费套餐** | ≈ 0 |
| ~~②~~ | ~~京东云积分~~ | ⛔ **2026-09-09 停用**（额度用尽、消耗太快） | — |
| ③ | ~~DeepSeek 官方 API~~ | 🔴 **现金，走个人账户** | **真金白银** ⇒ ⛔ 已改为**手动**路径，⛔ 不在自动降级链里 |

🔴 **①层内是【轮换】关系，⛔ 不是固定优先级**（用户 2026-09-09）：火山 / 百炼 / codebuddy 地位相同。
**加百炼正是因为火山与 cb 这个月量不够了。** ⇒ 用哪个由「哪个还有量」决定，撞限额换下一个，
⛔ 不要在文档里把先后钉死。

🔴 **官方 API ⛔ 已不在自动降级链里**（2026-09-09）：它还在 opencode 的 `disabled_providers` 里，
写成自动兜底等于给一条**假通道**（真走到会**失败**，⛔ 不是花钱）。
⇒ **手动路径**：需用户明确接受现金开销 + 解除 disabled 后，才可显式 `--provider deepseek`。
⭐ 自动路径的最后一站是 **`claude/claude-sonnet-5` @ `max`**（LAST_RESORT，§8）。

### ⚠️ 池额度状态（2026-09-10 实测，⛔ 会过期）

| 池 | 状态 |
|---|---|
| `volcengine-coding` | 🔴 **额度用尽**，重置 **2026-09-20 23:59:59 +0800** |
| `volcengine-agent-plan` | ✅ 有量 |
| `bailian-token-plan` | ✅ 有量 |
| `codebuddy-code` | ✅ 有量 |

🔴 **判据永远是实际探活，⛔ 不是读这张表** —— 它只为省一次盲探。
⚠️ 同日一小时前 `volcengine-coding/glm-5.3-flash` 还 OK ⇒ 额度是**刚**耗尽的，
说明这张表的时效性可能只有小时级。

⭐ **额度耗尽的报错签名**（`first_available` 的判据）：

```
429 {"code":"AccountQuotaExceeded","message":"You have exceeded the monthly usage quota.
     It will reset at 2026-09-20 23:59:59 +0800 CST. ..."}
```

⭐ **报错正文里带重置时间**，⛔ 别只记「429」就丢掉正文。

🔴 **2026-09-10 钱包轮换首次实战生效**：跑 v4.1-flash 定档盲评时 `volcengine-coding` 撞 429，
换 `volcengine-agent-plan`（同 model id、独立额度池）直接跑通。
⇒ 昨天把 agent-plan 加进 `WALLET_PREF` 的价值当天兑现。

### ⭐ 折扣窗口 —— 🔴 **两家的窗口不一样，⛔ 别只记住其中一个**

| 池 | 打折时段 | 折扣 | 适用模型 |
|---|---|---|---|
| **codebuddy** | ⛔ **工作日 09:00-12:00 / 14:00-18:00 是原价**，**其余全部**（含整个周末）5 折 | 积分 5 折 | `deepseek-v4-flash` · `deepseek-v4-pro` |
| **百炼** | 每天 **22:00 – 次日 08:00** | credits 5 折 | `deepseek-v4-pro-0813` · `deepseek-v4-flash-0731` · `qwen3.8-max`（⛔ 不含 `qwen3.8-flash`） |

⚠️ **codebuddy 的覆盖面远大于百炼** —— 一周 168 小时里只有 **20 小时**是原价。
⇒ ⛔ **别把规则记成「夜间优先百炼」**，多数时段其实是 codebuddy 在打折。

| 当前时段 | 谁在打折 | 轮换怎么排 |
|---|---|---|
| 22:00 – 08:00 | 两家都打 | 回到普通轮换（看谁有量） |
| 工作日 09-12 / 14-18 | 都不打 | 普通轮换 |
| 其余（工作日 08-09、12-14、18-22 + 整个周末） | 只有 codebuddy | ⭐ 优先 codebuddy |

**规则一句话：轮换时优先【当前正在打折】的那家。** 同为打折或同为原价时保持原轮换序。

🔴 **不变量是「⛔ 不得跨档下调」，⛔ 不是「折扣不许影响选模型」。** 分两步，价格在第二步才介入：

```
第 1 步  选档位      ← 任务类型 + 做砸过几档，⛔ 价格不参与
第 2 步  档位内选落点 ← ⭐ 这一步就是要挑便宜的（含时段折扣）
```

⇒ **价格参与是对的，只是⛔别搞错它作用在哪一层。** 有三层，⛔ 别混：

| 层 | 什么时候发生 | 价格参不参与 | 例子 |
|---|---|---|---|
| **定阶梯**（改 catalog 时） | 人做决策，⛔ 不在派发时 | ⭐ 参与 | `glm-5.3-flash` 与 `deepseek-v4-flash` 头对头 66 vs 67 **打平**且便宜 2.8× ⇒ 把 glm 定成**更低的入口档 T1** |
| **选档位**（第 1 步） | 每次派发 | ⛔ 不参与 | 按任务类型 + 做砸记录 |
| **档内选落点**（第 2 步） | 每次派发 | ⭐ 参与 | 同一型号的多个池，挑当前打折的那家 |

⚠️ `glm-5.3-flash`(T1) 与 `deepseek-v4-flash`(T2) 是**两个档**，⛔ 那个例子不叫「同档位内选便宜」——
它是**定阶梯时**的依据。⛔ 别拿它给「派发时降档」背书。

**2026-08-12 那个 bug 的错误是【跨档下调】**：把「做砸才升上去的高档模型」
换成了**低档**的便宜模型。错的⛔不是按价格选，是**越过档位边界往下选**。

⚠️ **跨钱包比价算不出来**（火山包月 / cb 积分倍率 / 百炼 credits，单位不可通约）
⇒ 只比「**同一型号**的多个池」，那一步才可算（同型号、一边打折一边不打）。

⇒ 守卫：`consistency-check.py` 断言折扣判断⛔不得出现在【选档位】段；
`pipeline-test.py` 有 4 个时段的用例 + 反例「深夜 T1 档位不被冲掉」。

⚠️ 两个优惠都未标注截止日期，金额敏感时先复核控制台。


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
| ~~`jdcloud-joyagent/DeepSeek-V4-*`~~ | ⛔ 已停用（2026-09-09） | ⚠️ 规律仍成立：**换钱包 ≠ 换族** |
| `cb/kimi-k3-2` | GPT / Claude / DeepSeek / GLM … | Kimi 全族 |
| `qcn/qmodel_38max` | GPT / Claude / DeepSeek / GLM … | Qwen 全族 |
| `claude/*`（Paseo 派 Claude 子会话） | GPT / DeepSeek / GLM … | **Claude 全族** |

🔴 **第一行最容易被忽略却最常发生**：主会话就是 Claude，凡是**我自己写的代码/文档/配置**，
⛔ 不能派 `claude/*` 子会话来审——那是自审。同理 `github-copilot/claude-*` 也不行。

⇒ ⛔ **不要把它记成「DeepSeek 不许审查」**。实施是 Hy4 或 K3 时，DeepSeek 是完全合格的异构评审。
只因为付费主力档是 `deepseek-v4-flash`，**那一路**的评审才要排除 DeepSeek 族。

### ⭐ 当前审查通道（模型为**默认值**⛔非不可覆盖，⚠️ **通道按规模分流**）

🔴 **模型 **未显式指定时**默认 `github-copilot/gpt-5.5`；通道按 §7 的规模判据选**，⛔ 别把两者写成一个原子。
⚠️ 「默认」⛔ 不等于「不可覆盖」：显式 `--model` 会被保留（异构族约束仍成立）；
显式 `--provider` 若不是 `github-copilot`，会报 **review 冲突**（⛔ 而不是 P0 的 disabled/白名单不匹配）。

```bash
# 大审查（多文件 / 读大量源 / 预计 20+ 工具调用）—— ⭐ 走 Paseo，可见可中止
create_agent(provider="pi/github-copilot/gpt-5.5", settings={"thinkingOptionId": "xhigh"})

# 短审查（单文件 / 明确问题）—— 走 CLI，跑完即退
pi -p --provider github-copilot --model gpt-5.5 "<≤200 字符的 prompt>"
```

⚠️ 实测：大审查走 `pi -p` 曾跑满 **35 分钟零输出、全程不可见只能盲杀**；
同期 Paseo 派的审查 agent 能看到它们各自在第 13 / 22 步撞 429。

| 约束 | 说明 |
|---|---|
| 🔴 **prompt ≤200 字符** | 背景让模型自己读文件。实测非交互模式下 800 字让 GPT-5.5 挂 22 分钟，短 prompt 秒回 |
| ⛔ **撞超时不要收窄 prompt 重试** | 极小 prompt 也会超时的情况另有根因，换通道 |
| ⛔ **Copilot 仅审查，不做开发** | 用户 2026-08-20 明确。开发走 §7 火山通道 |
| ⛔ 不用 `codex/gpt-5.6-sol` | 实测该 workspace `out of credits` |

Copilot 侧可用的异族评审（2026-09-08 实测 **17 个**，以 `~/.pi/agent/models.json` 为准）：
`gpt-5.5`(⭐审查默认) · `gpt-5.6-sol` · `gpt-5.6-luna` · `gpt-5.6-terra` · `gpt-6-astra` · `gpt-5.4` · `gpt-5.4-mini` · `gpt-5.3-codex` · `gpt-5-mini` · `gemini-3.5-flash` · `gemini-3.6-flash` · `gemini-3.7-flash` · `gemini-3.8-flash` · `grok-4.5` · `grok-4.6` · `mai-code-1-flash-picker` · `mai-code-1.1-flash`

🔴 **Claude 全族已于 2026-09-08 从 pi 的 Copilot 通道移除**（用户要求）——主会话就是 Claude，留着容易误用成自审。⚠️ 实现方式是在 `~/.pi/agent/models.json` 里显式定义 `github-copilot` provider 覆盖 `models-store.json`，⛔ 因为那个 store 会按 etag **自动刷新**，手改它会被冲掉。⚠️ 代价：Copilot 将来新增的模型**不会自动出现**，要手工补进 models.json。
⚠️ store 目录里另有 `gpt-5.4-nano` / `kimi-k3` / `kimi-k2.7-code`，但**本订阅实际不支持**
（API 返回 `model_not_supported`），⛔ 别按目录以为能用。

### 为什么审查不跟着「DeepSeek 优先」走

约束已把实施侧定成 DeepSeek，评审若也换成 `volcengine-*/deepseek-*`，
就是 **DeepSeek 审 DeepSeek**，异构审查直接失效。
2026-08-12 与 08-16 两轮异构审共抓到 13 处问题，**全部来自「换一个模型族去看」**。

⇒ 「opencode/pi 优先火山 DeepSeek」的适用范围是**实施类 / 问答类**；审查类是硬例外。

---

## 6. 任务分类 → 落点

链条读法：**T0 免费档先试 → 命中 §2 排除清单则跳过 T0 → 从下表的起步档进 → 按【质量/成本升档】（做砸一轮）才升下一档。**
⚠️ **可用性换档⛔不受此约束**：该档所有 provider 都拿不到时可向上换档（必须报告），见 §8。
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
⚠️ 但也 ⛔ **不因为「这类任务 v4-pro 更强」而预先升档**——从 T2 起步，按【质量/成本升档】（做砸过一轮）才升。

---

## 7. 通道选择

**命令与参数见 `SKILL.md` §3（唯一真源）。** 本节只给选择判据。

| 任务规模 | 走哪条 | 为什么 |
|---|---|---|
| **开发实施类**（改代码/跑测试/提交） | ⭐ **Paseo `create_agent`** | 要看进度、能中途干预、有结构化状态 |
| **大审查**（多文件 / 20+ 工具调用） | ⭐ **Paseo `create_agent`** | 🔴 它是长活，⛔ 不是 one-shot（见下方修正） |
| **短任务**（单文件 / 只读分析 / 短审查） | `pi -p` CLI | 跑完即退，不堆 serve |
| **执行适配器兜底** | `opencode` 🔻 | 无常规用途。⚠️ ⛔ 别与 `LAST_RESORT`（可用性降级链的最后一站，= `claude/claude-sonnet-5`）混为一谈——一个是**怎么跑**，一个是**跑哪个模型** |

🔴 **通道与模型正交**：通道由**要不要看得见**定，模型由 §5 **异构族约束**定。
⛔ 别把「审查类 → pi -p + gpt-5.5」写成一个原子——那会让「大审查」被迫走不可见通道。

⚠️ **2026-09-08 修正**：原表把「审查类」整类钉给 `pi -p`，理由是「审查不需要盯」。
实测推翻：`pi -p` + gpt-5.5 跑满 **35 分钟零输出**、全程不可见只能盲杀；
同期 Paseo 派的两个审查 agent 都能看到各自在第 13 / 22 步撞 429。

🔴 **分通道的维度是「要不要看得见」，不是「用哪个工具」。**
pi 有两种启动方式（Paseo 派 pi / `pi -p` 直跑），**跑的是同一个 pi、同一套能力**，
区别只在能不能看见它。⛔ 开发任务不要走 `pi -p`——它不进 Paseo agent 列表，你看不见也打不断。

### 火山两个套餐、三个 provider

Agent Plan 额度不够，2026-08-20 另购 Coding Plan（Pro 套餐，包月至 2026-10-20，自动续费关）。
两个套餐**额度独立、API key 不同**。

| provider | 套餐 | baseURL | 模型数 | opencode `--variant` | ⭐ pi `--thinking` |
|---|---|---|---|---|---|
| ⭐ **`volcengine-coding`** | **Coding Plan** | `…/api/coding/v3` | **8** | ✅ `off`/`on` | ✅ 生效 |
| ⭐ **`volcengine-agent-plan`** | **Agent Plan** | `…/api/plan/v3` | **13** | ❌ 静默失效 | ✅ **生效** |
| `volcengine-chat` | Agent Plan（同额度同 key） | `…/api/plan/v3` | 3 | ✅ `off`/`on` | ✅ 生效 |

🔴 **「agent-plan 控不了思考强度」这条只对 opencode 成立**（2026-09-09 实测更正）：
两个 endpoint 经 pi 传 `thinking.type` 都**真生效** —— coding `disabled/enabled` = `reasoning_tokens` **0 / 155**，
agent-plan = **0 / 165**。⛔ 那次失效的主语是**客户端**：opencode 走 `@ai-sdk/openai`（Responses API），
参数白名单把 `thinking` 丢了；pi 走 `openai-completions`，**两条路径不同**。
⇒ 走 pi 时 **agent-plan 与 coding 地位相同**，可放心进钱包轮换（`WALLET_PREF`）。

⭐ **两个套餐 = 两个独立额度池**（用户 2026-09-09：「额度相互轮换就行」）。
阶梯三档 `deepseek-v4-pro` / `deepseek-v4-flash` / `glm-5.3-flash` 在两边 **id 完全相同**
⇒ 撞限额直接换另一个 provider，⛔ 不用改 model 名。

**Coding Plan 8 个**：`deepseek-v4-flash` · `deepseek-v4-pro` · **`glm-5.3-flash`** · `glm-5.3`
· `minimax-m3` · `kimi-k2.7-code` · `doubao-seed-2.1-turbo` · `doubao-seed-2.0-lite`

⚠️ **`glm-5.3-flash` 是 2026-09-08 才补上的** —— 此前配置里漏了，一度以为火山没有。
实测两个套餐都支持，回显 `model: glm-5-3-flash`。

🔴 **火山的 model id 大量是别名，⛔ 不能按字面理解**（2026-09-08 实测回显）：

| 请求 | 实际回显 |
|---|---|
| `glm-5.2` · `glm-latest` | **都是 `glm-5.3`** |
| `deepseek-v4-flash` | `deepseek-v4-flash-**ga-260731**` |
| `deepseek-v4-flash-260425`（preview 快照） | **`deepseek-v4-flash-ga-260731`** ← 点名要 preview 也给 GA |
| `deepseek-v4-pro` / `-260425` / `-ga-260813` | 都只回显 `deepseek-v4-pro`，⛔ 不暴露快照 |

⇒ **火山上 0425 那个 preview 快照已被别名到 GA**，想跑旧版都跑不了。
⚠️ 京东侧⛔不认 ARK 的快照 id（`模型不存在`），也只回显请求名 ⇒ 这条路在京东侧用不了。

⭐ **查火山真实模型清单**：`GET <baseUrl>/models` 在 **Coding Plan 可用**（返回 130 个 ARK 原始 id），
⛔ Agent Plan 返回 404。⚠️ 但那 130 个是 **ARK 全量目录**，别名（如 `glm-5.3-flash`）不在里面
⇒ ⛔ 不能拿它判断某个 id 可不可用，**要判断只能直接发一次请求**。
**Agent Plan 独有 5 个**：`ark-code-latest` · `kimi-k3` · `doubao-seed-evolving` · `glm-latest` · `doubao-seed-2.0-mini`

🔴 **baseURL 别写错**：官方明确不要用 `https://ark.cn-beijing.volces.com/api/v3`——**会产生额外费用**。
⛔ Coding Plan 不支持 `auto` 模式（实测 `UnsupportedModel`）。

⚠️ 火山侧那 10 个非 DeepSeek 模型按「不主动选」处理。
其中 `glm-5.3` / `minimax-m3` / `kimi-k2.7-code` 在 cb 侧已被白名单关闭，
但火山是另一个钱包——**是否同样关闭未经用户确认**，在确认前不主动选、也不判违规。

### 🔻 opencode 排最后

用户 2026-08-20 定位卡死根因：**每次 `opencode run --pure` 拉起一个 serve，反复调用则 serve 堆叠吃穿内存**。
⇒ 单次偶发调用本身安全；⛔ **循环里反复 `opencode run` 是危险动作**，改用 `pi -p`。
review 已迁到 Copilot：开发实施类 + 大审查 → Paseo；短任务 / 短审查 → `pi -p`。opencode 现在没有任何常规用途。

---

## 8. Provider 与降级链

| Provider | 调用方式 | Permission mode |
|---|---|---|
| `codebuddy-code` | Paseo `create_agent` | bypassPermissions |
| `qoderclicn` | Paseo `create_agent` | bypassPermissions |
| `pi/<火山 provider>/<model>` | Paseo `create_agent` | ⚠️ **无 mode**：pi provider 在 Paseo 里 `availableModes` 为空，⛔ 传 `modeId` 会报 `Invalid mode` |
| `pi -p --provider volcengine-coding` | CLI one-shot | — |
| `pi/github-copilot/gpt-5.5` | Paseo `create_agent` | ⭐ **大审查**主通道（可见可中止） |
| `pi -p --provider github-copilot` | CLI one-shot | 🔸 **短审查**主通道 |
| ~~`pi/jdcloud-joyagent/<model>`~~ | — | ⛔ **2026-09-09 停用**，配置已归档（§3.4） |
| `claude` | Paseo `create_agent` | auto |
| `codex` | Paseo `create_agent` | auto |
| `opencode run --pure` | CLI 🔻 | — |

### 降级链

⛔ **降级目标必须在【白名单 或 豁免集】内。** ⛔ 不得擅自开这两者之外的模型。
⚠️ `LAST_RESORT` 的 `claude/claude-sonnet-5` 走的是**豁免集**（`claude` ∈ `EXEMPT_PROVIDERS`），
⛔ 不在 cb/qcn 白名单里 —— 这⛔不是违例。缺一切替代时才报告用户。

```
🔴 先分清是【哪种换档理由】—— 这决定允许做什么：

  ① 质量/成本换档   触发：本任务上一档【做砸过一轮】
                    允许：向上一档。⛔ 不得跨档【下调】
  ② 可用性换档      触发：该模型在【所有 provider】都拿不到（限额/断供/探活排队）
                    允许：⭐ 只许【向上】+ 必须报告。⛔ 永远不向下（向下 = 拿"拿不到"当借口做质量回退）

可用性换档的完整顺序（每一步拿不到才走下一步）：

  当前档模型
    ├─ ① 该模型的 `WALLET_PREF` 池轮换 ⚠️ **各档池子不一样**：
    │     T2/T3 四池（火山×2 + 百炼 + cb）· T1 **三池**（百炼无 glm-5.3-flash）· T4 **只有 cb**
    │     ⭐ 池内顺序 = 轮换序，当前正在打折的排前（§3.5 折扣窗口）
    ├─ ② 同档替代 `TIER_PEERS` ⚠️ **目前仅 T3 有**（→ bailian/qwen3.8-max），其余档⛔没有 ⇒ 直接进 ③
    │     ⭐ 优先于升档 —— 同档能落就⛔别涨价
    ├─ ③ 【可用性升档】tier + 1，回到 ①  ⚠️ 每升一档都要记进 availability_escalations
    └─ ④ 阶梯到顶（T4 kimi-k3-2）仍拿不到
          → 🔴 **LAST_RESORT `claude/claude-sonnet-5` @ `max`**（mode=auto）

🔴 **LAST_RESORT 的定位**（用户 2026-09-09）：
整套钱包体系存在的目的就是 **⛔ 不占用 Claude 套餐额度**（留给主会话）。
⛔ **但「不能不干活」优先于「省额度」** ⇒ 到顶了宁可用它，也⛔不要停在半路。
⚠️ 走到这里 = 正在烧掉这套体系本来要保护的东西 ⇒ **必须显著报告**，⛔ 不许静默。
⛔ 它⛔不是 T5，⛔ 不参与「做砸就升档」那条路径 —— **只有可用性耗尽才够得着**。

⛔ **连 claude 都不可用才停止并报告**（`report_no_landing_and_stop`）。

其它 provider 的专项处理：

  qoderclicn 限额 / refresh timeout
    ├─ 先重试 1 次（等 5-10 秒）——`Timed out refreshing Qoder CLI CN after 60000ms`
    │  是 provider refresh timeout，不是模型推理超时
    └─ ⛔ 不得降级到同 qcn 下其它型号（白名单只有 qmodel_38max）

  T0 免费档（hy4/hy3）拿不到
    ├─ **未显式 `--free`** → 落 T1 glm-5.3-flash（⭐ 这是可用性换档的一个实例，⛔ 不是特例）
    └─ 🔴 **显式 `--free`** → ⛔ **停止并报告**（`report_free_unavailable_and_stop`），⛔ 不静默转付费
    ⚠️ 触发条件不止「限额」：额度耗尽 / 探活未秒回（排队）/ 命中 §2 清单，都走这条

  🔴 `deepseek/*` 官方 API（**现金**）⛔ **已不是自动兜底**（用户 2026-09-09 决定）
    它仍在 opencode 的 `disabled_providers` 里 ⇒ 写成自动兜底等于给了一条**假通道**：
    真走到那一步会**失败**，⛔ 不是花钱。
    ⇒ 现在是**手动路径**：需用户明确接受现金开销并解除 disabled 后，才可显式 `--provider deepseek`。
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

**2026-09-09 换位盲评**（`qwen3.8-max`(百炼) vs `deepseek-v4-pro`(火山)，两臂 thinking=medium、prompt 逐字相同）：

| 题目 | `qwen3.8-max` | `deepseek-v4-pro` | 差 |
|---|---|---|---|
| LRU（代码实现） | 25.5 | **33.0** | v4-pro +7.5 |
| 并发诊断 | 36.5 | **38.0** | v4-pro +1.5 |
| Kafka 架构 | **37.5** | 31.0 | **qwen +6.5** |
| **总分 /120** | 99.5 | 102.0 | v4-pro +2.5 |

⇒ ⭐ **判【同档】**（T3）：差 2.5/120 ≈ 2%，⛔ 不构成谁更强——理由见下面的位置偏好。
⇒ ⚠️ **分项分化明显**，⛔ 但这条**只在这两者之间成立**（未与 `glm-5.3-flash` / `kimi-k3-2` 比过）。
⇒ 落地形式是 `TIER_PEERS`（SKILL.md §2）：**本档四个池全拿不到时**才换到 `qwen3.8-max`，
   ⛔ 主落点可用时不插队（它的 credits 倍率还没测，没有价格依据）。

🔴 **本轮方法升级：每题跑【两个朝向】，把评委的位置偏好测出来并抵消。**
实测 **A 位平均比 B 位高 2.5 分** —— 与两臂总分差同量级。
⇒ ⛔ **单朝向盲评的名次不可信**，尤其是差距在个位数时。
✅ 本轮三题的胜负方向**换位后全部保持**（lru/concurrency 归 v4-pro，kafka 归 qwen），方向是稳的。

⚠️ **回看 2026-09-08 那轮**（京东 vs 火山 v4-pro）：A 位 3 战全胜、京东占 A 位 2/3、总分只领先 4 分
⇒ 那 4 分很可能大部分是位置偏好。⛔ 不推翻其结论（原文已写明「4 分在噪声内，不能说 JD 更强」），
但现在知道了机制。**此后所有头对头都要换位重跑。**
📎 数据：`~/AgentWorkspace/tmp/qwen38max-vs-v4pro/scores.json`

⚠️ **反冗长护栏起了作用**：Kafka 题 qwen 写了 99KB、v4-pro 只有 17KB（5.8×）而 qwen 赢；
但 LRU 题 qwen 也更长（22KB vs 16KB）却**输了 7.5 分** ⇒ 评委⛔没有单纯奖励长度。

**历史榜（口径不同，⛔ 仅供量级参照，不构成排名）**：
M3 114 · Sonnet5 112 · K3 110.5 · Qwen3.8-Max 101.5 · Opus4.6 97 · Sonnet4.6 77。

⚠️ 榜上那个 `Qwen3.8-Max 101.5` 与本次实测 99.5 很接近，**⛔ 但这不是验证**——
两者轮次、评委、thinking、题目批次都不同，⛔ 跨轮分数本就不可横比（见本节开头）。
只能说「量级上不矛盾」，⛔ 不能说「互相印证」。

**⚠️ Claude 模型（可派发但不推荐——消耗订阅额度，建议留给主会话）**：

| 模型 | 总分 | 何时选 |
|---|---|---|
| Sonnet 5 | 112 | 用户显式要求 / 需要 Outbox 级架构深度 / 🔴 **LAST_RESORT**（阶梯到顶仍拿不到，§8） |
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
P0  ⛔ Provider 白名单（§1）        对【白名单 provider】：不在其清单的 model id 一律不派；
                                   其它 provider 必须在【豁免集】且⛔不在 DISABLED 里。先过这一关
P1  用户显式 --model / --provider    直接用（仍受 P0 约束）
P2  审查硬例外（§5）                 模型**默认** github-copilot/gpt-5.5（⛔ 非不可覆盖）；
                                   ⚠️ 显式非 Copilot provider 在 **P0 之前**就报 review 冲突；
                                   ⛔ 「不受 P0 约束」是**旧说法** —— 选出的组合照样过 validate()
     ⚠️ 通道按【规模】分：大审查 → Paseo pi/github-copilot/gpt-5.5；短审查 → pi -p
P3  ⚠️ Claude 模型可派不推荐         消耗订阅额度，建议留给主会话
P4  运行环境约束                     --hub 时确认 provider 在 Hub 可用
P5  免费档（§0 T0 + §2 排除清单）    hy4-preview → hy3
P6  任务类型 → 落点（§6）
P7  成本优化                         同模型多 provider 时选最便宜的
P8  Provider 降级（§8）
```

⛔ **没有 P「时段策略」这一档**——⚠️ 但这⛔不等于「派发链里没有时段判断」。

🔴 **2026-09-09 起时段判断回来了，但只活在 P7（成本优化）里面**：
`is_discounted_now()` 在【同一模型的多个池】之间挑当前打折的那家（§3.5 折扣窗口）。
⇒ 它⛔不是独立的一档，⛔ 不影响 P1–P6 任何一步选出来的**档位**。

⚠️ 2026-08-16 废止的是**那种写法**，⛔ 不是「时段判断」这个概念本身：
旧 `is_night()` 会把按类型选出（或做砸才升上去）的高档模型换成【低档】便宜模型，
**越过了档位边界往下选**。⇒ 不变量是 **⛔ 不得跨档下调**。详情见 CHANGELOG v10.0 与 v11.3。
