---
name: rift-dispatch
description: "Rift Dispatch: analyze task → recommend model → create Paseo sub-session, or `pi -p` call, or `codex exec` review call. Triggers: 'rift-dispatch', 'rift dispatch', 'dispatch', '派任务', '派个子会话', '选模型', '用 codebuddy', '用 v4-pro', '用 GLM', 'model dispatch', '调度', 'dev sub-session'."
user-invocable: true
argument-hint: "[--model <name>] [--thinking <level>] [--hub] [--worktree <path>] [--free] <task description>"
---

# Rift Dispatch — 智能任务派发

> 🔗 **rift 家族**：**`/rift-dispatch`（派发）** · `/rift-reap`（回收）· `/rift-integration-qa`（测试验收）

分析任务 → 选模型 → 选 provider → 创建子会话（Paseo）或执行 `pi -p` / `codex exec`。

**用户请求:** $ARGUMENTS

> **本文件 = 怎么做**（伪代码 · 命令 · prompt 模板 · 自查表）。
> **选什么 + 为什么** 在 `model-routing.md`；**数值**在 `model-catalog.json`；**历史**在 `CHANGELOG.md`。
> 同一条规则只在一处展开，本文件出现的规则以 routing 为准。

## ⛔ 开工前三条硬默认

| # | 规则 | 落点 |
|---|---|---|
| 1 | **便宜优先，逐级升档** | 免费池（**`FREE_POOL` 登记表**：Space Bunny@high → hy3@max → qfmodel，逐条按条目判，09-29 起）先试 → 付费从 **`deepseek-v4.1-flash`**（火山两套餐 + 百炼；🔴 **cb 上改用同档 `glm-5.3-flash` 0.06x** —— 09-24 cb 的 v4.1 涨到 0.11x）起步 → `deepseek-v4-flash`（0.17x）→ `qwen3.8-max` → `kimi-k3-1`（1.62x）。⛔ **每一级【质量/成本升档】的唯一入口是「上一档已在本任务做砸过一轮」**，理由里要写明哪一轮、砸在哪。写不出来不许升。⚠️ 这条⛔**不管【可用性换档】**——模型在所有 provider 都拿不到时允许向上换档（必须报告），见 §2 第 5 段。⚠️ 例外：`algorithm` / `perf` 两类从 `deepseek-v4-flash` 起步（⚠️ 依据比的是 v4-flash **对 glm**，⛔ 没比过现在的 T1 ⇒ **待补测**）。🔴 并发两类已改回 T1 起步 —— 4 臂拉丁方并发题 v4.1-flash 37.5 > v4-flash 30.5 |
| 2 | 🔴 **按「要不要看得见」分通道，不是按工具分** | 🔴 **开发实施类 + 大审查 → Paseo；短任务 / 短审查 → `pi -p`；⭐ 审查（大/短审查）2026-10-06 起统一走 CLI `codex exec`（见 #4 与 §3.2c）**。判据是**规模**不是任务类型——Paseo 能看进度、中途干预、拿结构化状态；`pi -p` 跑完即退不堆 serve。⛔ **开发任务和大审查都不要走 `pi -p`**：它不进 Paseo agent 列表，你看不见也打不断（实测大审查走 `pi -p` 跑满 35 分钟零输出 ⚠️ 09-24 起**疑似 stdin 挂死**而非规模问题，见 §3.2b —— 当时未查 stdin，未复测） |
| 3 | 🔴 **先判失败形态，再决定换什么** | **有产出但不合格** = `bad_output` ⇒ 走【质量/成本升档】（可换模型族）。**没产出**（静默停 / 唤不醒 / 探活不过）= `no_response` ⇒ 走【可用性】：**留在同 provider 降到下一档**，⛔ 不算做砸、⛔ 不跨钱包。⚠️ hy4 经常「碰墙」——允许你用但派发后静默停，**Paseo 抓不到明确错误** ⇒ ⛔ 别把它当成模型能力问题 |
| 4 | 🔴 **审查的硬约束是「异构」** | ⛔ **评审模型族 ≠ 实施模型族**（全局红线 #8），是**不变量**，不是针对某个模型的禁令。🔴 **含主会话：主会话就是 Claude，我自己写的东西不得派 `claude/*` 去审**。族对照表见 routing §5。⭐ **未显式指定时**默认 **`codex`**（⭐ 2026-10-06 起；模型取 `~/.codex/config.toml` 的 `model`，实测 `gpt-5.6-sol`，可用 `RIFT_REVIEW_MODEL` 覆盖；⛔ 不是「不可覆盖」，显式换 provider 会报冲突）。⚠️ **通道统一走 CLI** `codex exec`（大/短审查同通道——Paseo 的 codex provider `out of credits`，⛔ copilot 全族 2026-10-06 已死）。🔴 codex 撞额度 ⇒ 按 §3.2c 降级阶梯换异族，**显式记录并告知用户** |

🔴 **两种换档理由是正交的，⛔ 别混**：**质量/成本换档**只因「本任务做砸过一轮」，⛔ 不得跨档**下调**；
**可用性换档**（所有 provider 都拿不到）只许**向上**、必须**报告**，到顶仍拿不到 ⇒ `claude/claude-sonnet-5@max`
（🔴 **LAST_RESORT**：整套钱包体系就是为了省 Claude 额度，走到这里必须显著告知）。

⚠️ **派发认 model id，⛔ 不认 label**：`hy3`(0.00x) 与 `hy3-x`(**0.05x**) 的 label 都是「Hy3」（09-24 面板）。

🔴 **`probe_ok(m)` 的可执行实现 —— ⛔ 不是抽象概念，是一条命令**（2026-09-17 补）：

```bash
S=~/.claude/skills/rift-dispatch/scripts
bash $S/probe-models.sh                              # 探当前阶梯默认落点（跨 provider）
bash $S/probe-models.sh codebuddy-code/hy3 …         # 指定 provider/model
bash $S/probe-models.sh --all                        # 全部已知落点
bash $S/cb-probe.sh hy3                              # 兼容 shim：只探 cb
```

⭐ **分流 —— 不同 provider 拿得到的证据强度不同，⛔ 别一套办法打天下**：

| provider | 手段 | 能拿到什么 |
|---|---|---|
| `codebuddy-code` | cb CLI | ⚠️ **也不给状态码**，只能判 stdout 是不是 JSON；但 429 正文**带重置时间** |
| `volcengine-*` / `bailian-*` | **直连端点** | ⭐ **真实 HTTP 状态码** ⇒ `429`(额度) / `403`(无权限) / `404`(不存在) **三态分得开** |
| `codex` | `codex exec` CLI | 🔴 报错走 **stderr + rc=1**（实测 `ERROR: Your workspace is out of credits.`），判 rc + stderr 即可，无需解析正文 JSON |
| `openrouter-free` | **直连端点**（key 按 pi 配置的 `!command` 从钥匙串取，⛔ 不打印） | ⭐ 真实状态码：`429`(额度，带 `X-RateLimit-Reset`) / `402`(余额为负) / `404`(模型下线) |
| `qoderclicn` | qcn CLI `-p -o json` | 判 `is_error` + 正文；🔴 **Paseo id ≠ CLI 名**：`qfmodel` 在 CLI 里是 `-m Qwen3.8-Flash` |

⭐ **撞额度自动写冷却**（`scripts/cooldown.sh`，§2 的 `cooldown_until()` 读它）：有重置时间用重置时间，否则 **+1h**（用户 09-29 定）；
冷却中的落点探活脚本**直接报「冷却中」、⛔ 不再探一次活**（`--force` 才强制探）。
手动记一笔：`bash $S/cooldown.sh set <upstream> <model> <HH:MM[:SS] | YYYY-MM-DDTHH:MM | +1h> "<原因>"`；
查看 / 清除：`cooldown.sh list` · `cooldown.sh clear <upstream> <model>`。
⚠️ 文件在 `~/.cache/rift-dispatch/cooldown.json`（**本机**）—— ⛔ 故意不放 syncthing 同步的目录（额度按账号 / key 算，两机互相覆盖只会添乱）。

🔴 **失败信号 → 动作**（免费落点为主，均来自实测；⚠️ 标「推测」的原文没在真实环境见过）：

| 信号 | 判定 | 动作 |
|---|---|---|
| cb「使用量已超出频率限制，将在 HH:MM:SS 重置」 | 额度 | 换下一个免费条目；冷却到该时刻 |
| 🔴 codex stderr `ERROR: Your workspace is out of credits.`（rc=1，2026-10-06 实测原文；同类签名 `usage limit` / 401 / 429，大小写不敏感） | 额度耗尽（⭐ **通道级**，codex 全家不可用，⛔ 不是模型级） | 按 §3.2c 降级阶梯换**异族**落点（qfmodel → hy3 → glm-5.3-flash），落点写冷却 +1h，**显式记录并告知用户**（⛔ 不许悄悄换）；⛔ 不许回落 claude 族（主会话）或 copilot 族（已死） |
| Paseo 下 cb 新会话零产出 / 唤不醒 | ⚠️ 先别定性 | **先 CLI 探活**（上面那条就是这样查出来的），⛔ 别直接归因 provider |
| OpenRouter `429` | 额度（20 次/分 · 50 次/天，北京 08:00 重置） | 换下一个；冷却到 `X-RateLimit-Reset`，没有就 +1h |
| OpenRouter `402` | 余额为负 | **停用这一条 24h 并报告用户**，继续试下一个免费条目（⛔ 不中止整个派发） |
| OpenRouter / 任一家 `404` | 模型下线（隐身预览模型随时可能） | 跳过；⚠️ 连续出现 ⇒ 报告用户删 FREE_POOL 条目 |
| OpenRouter `401` | key 缺失 / 格式错（**通道级**，⛔ 不是额度） | 跳过这一条、试下一个免费条目，并**报告用户**查钥匙串 `openrouter` 条目（⛔ 打印时只报「有没有 / 长度」）；⛔ 不写冷却（等不好）。⚠️ 旧写法「停」会让一把坏 key 卡死整个派发 |
| 探活脚本报 `SKIP`（pi 配置里没有该 provider） | 探不了 | 按**不可用**处理（⛔ 不是「全部可用」）；Hub 等没配 OpenRouter 的机器上属预期 |
| qcn `is_error` + 429 / 额度字样 | 额度（⚠️ 推测，原文未见过） | 换下一个；冷却 +1h |
| 🔴 qcn JSON `total_credits` > 0（仅免费条目）/ OpenRouter 响应 `usage.cost` > 0 | **免费期已结束**（⭐ 直接证据；⛔ 不是「答得动」——免费结束后模型照样答，只是开始扣费） | 模型级；冷却 24h；**报告用户**更新 FREE_POOL + catalog 该条目（写明确截止日或删条目）。⚠️ 探这一次本身会花 ~0.1 credits。cb 的 `rawUsage.credit` 是同类直接证据（10-02 实测 hy3=0），但探活脚本**尚未读取它** ⇒ cb 条目仍⛔不许写 None；hy3 靠 `freeUntil` + 复核 |
| 🔴 同上两个字段**读不到**（缺失 / 非数字 / 乱码，`scripts/billing.py` 判 unknown） | **无法确认免费**（⛔ fail-closed：这字段是 None 条目唯一的失效证据，读不到 = 没有证据） | 同样模型级 + 冷却 24h；报告用户核 CLI / API 输出格式是不是变了。代价是少一个免费选项（回落付费 T1，便宜） |
| 🔴 Paseo 创建的 cb agent，`runtimeInfo.model` ≠ 请求的型号（10-02 实测：未登记型号静默落 `hy3`） | 请求值 ≠ 运行值 | **立刻归档**，⛔ 不用其产出、⛔ 不按它标的型号记账 / 记评测；先查 `list_models` 里有没有该 id（§3.1） |
| ACP「Empty response」 | 客户端版本问题 | 先查 Paseo 的 provider 命令是不是钉了旧版本（09-28 qcn 钉在 1.0.30 就是这个形态） |
| `pi -p` 零 CPU、零连接、零输出 | stdin 挂死，⛔ 不是模型挂了 | 查有没有 `< /dev/null`（§3.2b） |

🔴 **退出码是三档，⛔ 不是二值**：

| exit | 含义 | 该做什么 |
|---|---|---|
| `0` | 全部可用 | 照常派 |
| `1` | **部分**不可用 | ⚠️ **这是正常状态** —— 换个模型/换个池即可，⛔ 别据此怀疑通道 |
| `2` | **全部**不可用（**且样本 ≥2**） | 才该怀疑通道 / 凭据 / 网络 |

⭐ **`2` 带样本量门槛**：只探了 1 个就失败 ⇒ 降级成 `1` 并明说「不足以判断通道」——
n=1 时「全部失败」就是「这一个失败」，⛔ 推不出通道有问题。
📌 与下方那条判据同源：**断言「X 类不可用」前必须测过该类里多个实例**。

🔴🔴 **为什么必须走 CLI 探活：Paseo 的 codebuddy provider ⛔ 不透传 HTTP 状态码。**
模型被 429 限流时，Paseo 侧只表现为 **「新会话零产出（`updateCount == 1`）」** 或
**「turn 到头唤不醒（`activeTurn: null`）」** —— 形态与 provider 稳定性故障**完全一样**，
而两者的处置**方向相反**：稳定性问题要换 provider，配额问题只要换模型或等重置。

⚠️ 实测代价（2026-09-17）：我把这两种形态误诊成「codebuddy 新会话建不起来」，
据此 kill 了两个**有产出**的 agent，换来两个零产出的。真因是 hy3 撞 429，
一条 `codebuddy -p --model hy3` 就能看见 —— 报错正文里**连重置时间都给了**（`18:43:13 UTC+8`）。

⇒ **固化**：派 codebuddy 前先探活；agent 出现「零产出 / 唤不醒」时，
**第一件事是探活那个模型，⛔ 不是直接归因到 provider 或重派**。
📌 同族判据在 MEMORY：「断言「X 类不可用」前必须测过该类里多个实例」。

⚠️ **免费档时间线**（🔴 **每条各有自己的窗口，⛔ 别混成一条**）：

| 型号 | 免费期 | 当前状态 |
|---|---|---|
| `stealth/space-bunny-alpha` | ⚠️ **截止未公布**（OpenRouter 09-23 上架的隐身预览模型，随时可能下线） | ✅ 2026-09-29 探活通过 |
| `hy3` | 🔴🔴 **二次延长至 `2026-10-31 23:59`**（CodeBuddy&混元官方 2026-09-30 公告，用户 10-01 转发截图；此前记的是「09-30 止」，09-15 之前更早记的是「08-31 止」） | ✅ 2026-10-01 探活通过 |
| `qfmodel` | ⚠️ **截止未公布**（Qoder CN 官方公告：原定 09-30 的免费期已延长，10-01 起继续免费，「结束时间将提前在本页公告」——⛔ agent 不会读那个页面，靠探活里的 `total_credits` 兜）。仅限个人用户，**企业订阅不适用**；高峰可能慢 | ✅ 2026-10-02 实测（原定 09-30 之后）`total_credits=0` |
| ~~`hy4-preview`~~ | `08-28 ~ 09-10` 已过期 | 🔴 **2026-09-15 用户弃用：不稳定** ⇒ ⛔ 已移出 T0，不再考虑 |
| ~~`hy3-x`~~ | ⛔ 本来就不是免费档（**0.05x**）。⚠️ 09-24 起它比 cb 上的 T1 落点 glm-5.3-flash(0.06x) 还便宜一点，但⛔**不同档**（同轮 08-21 盲评 hy3 84 < glm 91，差距远大于位置偏好 2.5）⇒ 先选档位再挑便宜，轮不到它 | 🔴 **无派发角色** ⇒ ⛔ 不考虑 |

⚠️ **cb 的 hy 系**是**每日赠额**⛔非连续免费期 —— **不回复 = 当日赠额已用完**，须主动换。
🔴 这条⛔**不适用于 Space Bunny**：它的额度耗尽是**明确的 429**（OpenRouter 20 次/分 · 50 次/天），而它**本来就慢**
（实测 150–400s/题）⇒ 「迟迟不回」⛔ 不能当成耗尽，先看有没有 429 / 探活。qfmodel 的额度报错形态⚠️ 未见过原文。
🔴 **判据永远是探活 + `promo_active`，⛔ 不是面板上的 `x0.00`** —— 那是价格；
赠额耗尽后价格仍显示 0，表现是**排队 / 不回复**而⛔不是报错。
⭐ **T0 是一张登记表（`FREE_POOL`，2026-09-29 起）**—— 新增 / 下线免费模型**⛔ 不改挑选逻辑**，改的都是数据：
SKILL §2 `FREE_POOL` + catalog `freePool` 条目（二者 consistency §3o 逐项比对）；若 provider 是**白名单型**（cb / qcn / openrouter-free）
还要把 id 加进 `WHITELIST`（⛔ 故意不让登记表自动绕过 P0 白名单）；再补标题缩写。漏了哪一项 §3o 都会报出来。
⚠️ `t0_still_free` / `t0_now_billed` 那套机制**按条目**生效：截止过后，只有**窗口之后**核过费率且仍为 0 的条目才继续用
（窗口内核的记录只证明促销价是 0）；复核途径写在 catalog 条目的 `verifyVia`。

🔴 **钱包优先级**（routing §3.5，与档位阶梯**正交**）：
① **已付费套餐**（边际成本≈0）→ ~~② 京东云积分~~（⛔ 2026-09-09 停用）→ ~~③ DeepSeek 官方 API~~（🔴 **⛔ 已不是自动兜底**，2026-09-09 改为**手动路径**：它还在 opencode `disabled_providers` 里，写成自动兜底 = 假通道；需用户明确接受现金开销 + 解除 disabled 后显式指定）。
⇒ ⭐ **自动路径的最后一站是 `claude/claude-sonnet-5` @ `max`（LAST_RESORT）**，⛔ 不是官方 API。
⇒ ①层内部是 🔴 **轮换，⛔ 不是固定优先级**：`volcengine-coding` · `volcengine-agent-plan` · `bailian-token-plan` · `codebuddy-code` 地位相同。
**具体落哪个由 `WALLET_PREF` + 当前折扣窗口决定**（§2 / routing §3.5），⛔ 本文件不再钉死先后。

⛔ **京东云通道 2026-09-09 已停用**（额度用尽、消耗太快）。配置归档在 `~/.pi/agent/providers-disabled/jdcloud-joyagent.json`，含恢复清单。⇒ 自动路径的钱包只剩 **① 已付费套餐**；③ 官方 API 已改为**手动**路径，⛔ 不在自动降级链里。

## Prerequisites

1. Read **model-routing.md**（模型选择 + provider 路由 + 降级链 + 门禁依据）。
2. Read **model-catalog.json**（费率 / 盲评分数 / provider 映射 / 机器可读门禁字段）。
3. Read the **paseo** skill（创建子会话的具体 API）。
4. Read `~/.paseo/orchestration-preferences.json`（除非用户显式指定了 provider）。

---

## 1. 解析参数

| 参数 | 解析方式 | 默认 |
|---|---|---|
| `--model <name>` | 短名或完整 model ID（映射见 catalog `shortNames`） | 自动推荐 |
| `--thinking <level>` | minimal / low / medium / high / xhigh / max | 按模型定：免费条目取 `FREE_POOL.thinking`（**Space Bunny→`high` · `hy3`→`max`** · `qfmodel` 无思考档 ⛔ 不传），付费档→`xhigh`（routing §4）。**有思考档的三条通道都必须传** |
| `--hub` | 标记 | 否（本地） |
| `--worktree <path>` | 路径 | 当前目录 |
| `--provider <name>` | 强制指定 provider | 按 model 自动选 |
| `--free` | 强制优先 T0 免费池，并放宽**能力类**排除（各条目的 `avoidTaskTypes`，routing §2.b）<br>⛔ 不放宽**物理不可用**（按条目判：该条目接不了多模态 · 冷却中 · 探活不过 · 本任务已做砸）—— ⚠️ 多模态只挡 `multimodal=false` 的条目，Space Bunny 能免费接图<br>🔴 整个免费池都拿不到时**停止并报告每条原因**，⛔ 不静默转付费 | 否 |
| 其余文本 | 任务描述 | (必填) |

参数缺失处理：

- 任务描述缺失 → 要求用户补充，⛔ 不猜
- `--thinking` 非法值 → 回退到该模型默认档（免费条目按 `FREE_POOL.thinking`，其余→`xhigh`）
- 目标模型**没有思考档**（`NO_THINKING_MODELS`：`qfmodel` · `kimi-k2.7-code`）→ ⛔ 不传，显式 `--thinking` 也作废，§7 回显「不适用」
- `--thinking` 合法但**目标模型没有该档** → 按 §3.2e 能力表**降到最近可用档**，⛔ 不得静默升档，且必须在输出里回显实际生效档位
- `--provider` 与 `--model` 不匹配 → 报告冲突，让用户选
- `--free` 与 `task_type == review` 同时成立 → **报告冲突，让用户选**（review 硬例外不进免费池：默认 codex 走订阅额度；⛔ 不擅自替用户决定牺牲哪一边）
- `--worktree` 路径不存在 → 报错

---

## 2. 决策流程（伪代码）

> 🔴 **这是一条单一线性管线**：⛔ 无 `goto`、⛔ 无「某分支自己算出落点就返回」、
> ⛔ **无任何顶层提前 return**。
> ⚠️ 2026-09-09 起连 `--free` 也不再是例外 —— 原先它 `delegate('rift-free'); return`，
> 是这条管线上仅存的破例；`rift-free` 删除后 `--free` 改为在第 4 段内**只影响选档**，
> 于是「无提前 return」从「有一个例外的规则」变成了真正的不变量。
> 变量在第 0 段**全部初始化**，⛔ 后面不许凭空冒出新变量；
> 用户显式给的值存进 `explicit_*`，**后续阶段只读不写**；
> 所有路径最后汇到同一个收尾（第 6 段）。
> ⚠️ 2026-09-08 重写 —— 原版有 goto 跳过初始化、T0 提前 return 绕过校验、显式值被覆盖，
> 三轮异构审查都栽在这上面，⛔ 补丁修不好，只能重写。

```python
# ═══ 0. 初始化 ═══ 所有变量在这里出现
args = parse_args(user_input)
want_free = False          # 第 2 段按 args.free/explicit_model 定值，⛔ 不在别处冒出

WHITELIST = {                                   # P0，routing §1
  'codebuddy-code':   ['hy4-preview', 'hy3', 'hy3-x', 'glm-5.3-flash',
                       'deepseek-v4.1-flash',    # ⚠️ 2026-09-24 起⛔不再是 cb 的 T1 自动落点——
                       # 涨到 **0.11x**（0.06x→0.03x→0.11x，用户截图实测），反超 glm-5.3-flash(0.06x)。
                       # 仍在白名单内⇒可显式 --model 派发，只是不再自动选中（见 WALLET_PREF 同名条目）。
                       'kimi-k3-1',
                       'space-bunny'],           # ⭐ 2026-10-02 cb 内置（付费 x0.03，折扣至 10-07）。⛔ 只进白名单（显式可派），不进任何自动池
  # 🔴 2026-09-10 用户停用 `deepseek-v4-pro`：⛔ agent 不得自行派发（见 BLOCKED_MODELS）。
  # 🔴 **2026-09-10 换代**：cb 上 `deepseek-v4-flash` → `deepseek-v4.1-flash`，
  #    `kimi-k3-2` → `kimi-k3-1`。⛔ 旧 id 已从白名单**移除**。
  # ⚠️ 旧 id 请求它们【不报错】—— 但那是**别名**，服务端静默解析到新型号。
  #    权威判据是【假 id 的 400 报错正文】：`400 model [x] service info not found`
  #    后面会附「Currently supported models for your account」的完整清单
  #    —— 那 15 个里**没有** deepseek-v4-flash / kimi-k3-2。⭐ 比 list_models 更硬。
  # 🔴🔴 **陈旧版本别名比无版本别名更危险**：它带着版本号，却指向**另一个版本** ⇒
  #    标题会写 `cb-dspF4` 而实际跑的是 `dspF4.1`，**标题在说谎**，
  #    正好击穿 §3.1 标题规范存在的意义。⇒ ⛔ 必须从白名单移除，不能只加注释。
  'qoderclicn':       ['qmodel_38max',
                       'qfmodel'],               # ⭐ 2026-09-29 T0 免费池 priority 3（Qwen3.8-Flash，免费，截止未公布）
  # ⭐ 2026-09-29 OpenRouter 免费隐身模型 —— 🔴 **白名单型**，⛔ 不进 EXEMPT。
  #    理由：OpenRouter 同一把 key 能调 347 个模型（大多收费），models.json 里这个 provider 虽只注册了它一个，
  #    ⇒ 派发侧仍要有「只许这一个」的硬闸，就是这张白名单。
  'openrouter-free':  ['stealth/space-bunny-alpha'],
}
# ⛔ jdcloud-joyagent 2026-09-09 停用（额度用尽、消耗太快）——已从 ~/.pi/agent/models.json 移除。
#    ⚠️ 配置完整归档在 ~/.pi/agent/providers-disabled/jdcloud-joyagent.json（含恢复清单）。
#    ⇒ 现在派它会落到「未知 provider」被拦，这是预期行为。
# 🔴 用户点名屏蔽的型号（2026-09-09）。⛔ 与 WHITELIST/EXEMPT 正交 ——
#    豁免 provider 也拦得住（否则 `--provider volcengine-chat --model deepseek-v4-pro` 会直接放行）。
BLOCKED_MODELS = {
  # 🔴 `glm-latest` 两边都列 —— ⛔ 它只在 agent-plan 上存在，但**万一将来 coding 也上**，
  #    漏一边就等于留了个口子。屏蔽名单宁可写重，⛔ 不要赌「那边没有」。
  # 🔴 2026-09-10 用户停用 `deepseek-v4-pro` ⇒ ⛔ agent 不得自行派发。
  #    它在**五个** provider 上都有（含 volcengine-chat），百炼那份 id 还带 -0813 后缀 ⇒ 五个 key 全写，
  #    漏一个就是一个绕过口（与 glm-latest 宁可写重同一个理由）。
  #    ⚠️ validate() 对屏蔽型号走 report_blocked_model_and_stop —— 是**停**不是换落点。
  #    这是刻意的：用户的要求是「不允许 agent 自己派发」，那么升档撞到 T3 就该**停下来
  #    回到用户**，⛔ 不该自己挑个替代悄悄继续。⛔ 因此本次**不动 LADDER** ——
  #    换档位要连带改 WALLET_PREF / TIER_PEERS / 一堆用例，且工作区里还压着别人未完成的
  #    kimi-k3 换代迁移（实测基线 pipeline-test 已有 37 条失败），进去只会把两件事缠在一起。
  'volcengine-coding':    {'doubao-seed-2.0-lite', 'doubao-seed-2.1-turbo', 'glm-latest',
                           'deepseek-v4-pro'},
  'volcengine-agent-plan': {'doubao-seed-2.0-lite', 'doubao-seed-2.0-mini', 'doubao-seed-2.1-turbo',
                            'doubao-seed-evolving', 'ark-code-latest', 'glm-latest',
                            'deepseek-v4-pro'},
  'codebuddy-code':       {'deepseek-v4-pro'},
  'bailian-token-plan':   {'deepseek-v4-pro', 'deepseek-v4-pro-0813', 'deepseek-v4-flash'},
                          # ⛔ `deepseek-v4-flash` 只在**百炼这一家**被屏蔽 —— 实测 403（账号无权限）
                          #    ⇒ 留着就是一条会被探活的死路径（与 v4-pro 那条同一个理由）。
                          #    🔴 它在**火山两套餐上照常是 T2 主力**，⛔ 不是全局禁用。
                          # 🔴 **两个都禁，但理由是「按能力档禁」，⛔ 不是「它俩是同一个模型」**
                          #    —— 后者已被 2026-09-11 实测证伪（同一句输入 token 数 8 vs 87）。
                          #    用户口径：v4-pro **这一档整体不要了**（v4.1-flash 同价 0.03x 更强）
                          #    ⇒ 该档的快照版一并禁用。⚠️ 用户 2026-09-11 明确确认。
                          # ⛔ `deepseek-v4-flash-0731` **不在此列** —— 它没被点名禁用，
                          #    只是【尚未定档】⇒ 显式 --model 可派，⛔ 不进任何档位的池。
  'volcengine-chat':      {'deepseek-v4-pro'},   # 🔴 0910 异构审抓到的漏口：
                          #    它在 EXEMPT_PROVIDERS 里 ⇒ 显式 --provider volcengine-chat
                          #    --model deepseek-v4-pro 本来能绕过 P0。
                          #    ⚠️ 上面注释曾写「四个 provider 全写」—— **数错了，是五个**。
                          #    ⇒ 已加 §3h 结构性守卫：屏蔽覆盖由 catalog 的 providers 表推，
                          #       ⛔ 不再靠人肉列举（同 §3g 的思路）。
  'github-copilot':       {'gpt-5-mini', 'gpt-5.3-codex', 'gpt-5.4-mini',
                           'gemini-3.5-flash', 'gemini-3.6-flash',
                           'mai-code-1-flash-picker', 'mai-code-1.1-flash',
                           'gpt-5.5', 'gpt-5.6-sol', 'gpt-5.6-luna', 'gpt-5.6-terra',
                           'gpt-6-astra', 'gpt-5.4',
                           'gemini-3.7-flash', 'gemini-3.8-flash',
                           'grok-4.5', 'grok-4.6'},
                          # 🔴🔴 2026-10-06 **整族屏蔽**（17 个 = 该 provider 已知全部型号）：
                          #    用户删除 pi Copilot 凭据（`~/.pi/agent/auth.json` = `{}`，
                          #    models.json / models-store.json 的 github-copilot 条目已抽走）⇒
                          #    实测再派任何 copilot 型号 → `[System Error] No API key found for github-copilot.`
                          #    ⇒ **全族不可用**，审查默认已迁 `codex`（CLI）。
                          #    📜 历史屏蔽（2026-09-09/09-15 用户点名，理由见 catalog blockedModels）：前 7 个。
                          #    ⚠️ `github-copilot` 同时已移出 EXEMPT_PROVIDERS ⇒ 不给 model 的
                          #       `--provider github-copilot` 落「未知 provider」被拦 —— 两层闸，⛔ 别只留一层。
                          # 📜 **屏蔽 ≠ 从 pi 清单里消失**（09-15 实测，当时清单是运行时从服务端拉的）；
                          #    2026-10-06 起凭据已删、清单入口已移除，本表保留是防 pi 配置将来被恢复。
}
# ⚠️ 屏蔽的是【型号】不是 provider ⇒ 同一 provider 的其它型号照常可用。

# 🔴 **产出必须校验的型号** —— ⛔ 这条以前只写在散文里，那**拦不住任何东西**
#    （同 `glm-latest` 那次的错：规则不落到会被执行的那一层就等于没写）。
#    判据：该型号有**「产出看着正常但其实是垃圾」**的已实证失败形态 ⇒ 收割时只看 exit 0 会收下垃圾。
OUTPUT_VALIDATION_REQUIRED = {
  'deepseek-v4.1-flash',   # 🔴 17% 概率产出 DSML 内部标记泄漏的短文（实测 10/12 有效）
}
# ⭐ 校验判据（多信号，⛔ 不要只判长度 —— 0910 守卫连错两版都是「判字面不判性质」）：
#    ① 过短（<5000 字）② 正文含 `<｜｜DSML｜｜` 等内部标记 ③ 开头是续接语
#    ④ **不足同批其他产出中位数的 35%** —— ⭐ 这一条不依赖预判「坏长什么样」
#    参考实现：~/AgentWorkspace/tmp/v41flash-bench-20260910/validate_cell.py

# 🔴 **全局禁用型号** —— ⛔ 与上面那张 provider-keyed 表【正交】。
#    上表回答「这个 provider 上不许用哪些」，本集回答「**这个型号哪儿都不许用**」。
#    ⛔ 为什么必须有这一层（0910 异构审 gpt-5.5 连开两枪）：
#      ① provider-keyed 表天生漏 —— 我写 v4-pro 时列了四个 provider、注释还写「四个全写」，
#         实际是**五个**（漏了 EXEMPT 里的 volcengine-chat，显式指定就能绕过）；
#         而 `--provider <未列过的 provider> --model deepseek-v4-pro` 这类**没列过的 provider**
#         结构上永远拦不住（⚠️ 原例写的是 github-copilot，该族 2026-10-06 已全量屏蔽 ⇒ 换成占位写法）。
#      ② 只给 `--model` **不给 provider** 时，§1 的 `if explicit_upstream is not None: validate()`
#         **压根不执行** ⇒ 要到 §5 把池探活完、收尾 validate() 才拦 ⇒ 用户明令禁用的型号被真请求了一遍。
BLOCKED_MODELS_ANY_PROVIDER = {'deepseek-v4-pro'}   # 🔴 用户 2026-09-10：⛔ 不允许 agent 自己派发
# ⚠️ ⛔ 别把它跟 DISABLED_PROVIDERS 合并 —— 那个是整个 provider 停用，措辞和出路都不同。

DISABLED_PROVIDERS = ['deepseek']               # 🔴 官方 API（现金）。⛔ 不是自动兜底，只能【手动】用
# 🔴 `github-copilot` 2026-10-06 起⛔不在豁免集：用户删除 Copilot 凭据 ⇒ 全族不可用，
#    不给 model 的显式 `--provider github-copilot` 落「未知 provider」被拦（型号级由 BLOCKED_MODELS 全族拦）。
EXEMPT_PROVIDERS   = ['claude', 'codex', 'opencode',
                      'volcengine-coding', 'volcengine-agent-plan', 'volcengine-chat',
                      'bailian-token-plan']            # 阿里云百炼，2026-09-09 接入
# 🔴 `pi` ⛔ 不在豁免集 —— 它是【宿主】不是钱包。豁免顶层 pi 会让
#    pi/jdcloud-joyagent/GLM-5.2 绕过京东白名单。⚠️ 本清单必须与 catalog whitelist.exempt 一致。
PI_HOSTED = ('volcengine-coding', 'volcengine-agent-plan', 'volcengine-chat',
             'bailian-token-plan',
             'openrouter-free')                      # ⛔ 京东已停用；⭐ 09-29 加 OpenRouter（Paseo 串 pi/openrouter-free/…）；🔴 10-06 移除 github-copilot（凭据已删）

# ⭐ review 默认落点（2026-10-06 起）—— provider 固定 codex（走 CLI `codex exec`，§3.2c）；
#    模型取 `~/.codex/config.toml` 的 `model`（实测 `gpt-5.6-sol`），环境变量 `RIFT_REVIEW_MODEL` 优先级更高。
#    ⛔ 这不是「不可覆盖」：显式 --model 保留、显式 --provider 非 codex 报 review 冲突（P0 之前）。
REVIEW_DEFAULT_PROVIDER = 'codex'
REVIEW_DEFAULT_MODEL    = codex_config_model()
# 🔴 codex 额度耗尽 ⇒ 按此阶梯依次换**异族**落点（§3.2c 有命令与实测）。
#    ⛔ 硬不变量：评审族 ≠ 实施族（routing §5）—— 若实施本身就是 Qwen / Hy / GLM 族，
#    同族的档⛔跳过，取下一档。⛔ 不许回落 claude 族（主会话）；⛔ 不许回落 copilot 族（全族已死）。
REVIEW_FALLBACK_LADDER  = [('qoderclicn', 'qfmodel'),            # 免费（截止未公布），Qwen 族
                           ('codebuddy-code', 'hy3'),            # 免费至 10-31，Hy(混元) 族
                           ('codebuddy-code', 'glm-5.3-flash')]  # ⚠️ **付费 0.06x**（⛔ 不是免费），GLM 族
CODEX_EXHAUSTED_RX      = r'out of credits|usage limit|HTTP 401|HTTP 429'  # 判 codex 额度耗尽的签名（大小写不敏感；2026-10-06 实测原文含 'out of credits'）
# 🔴 锚定纪律（2026-10-06 异构审 P1-2）：⛔ **不许写裸 `401|429`** —— codex 正常输出里就有
#    `tokens used: 14290` / `elapsed 4012ms` / `turn 1 completed (4290 tokens)`，裸数字必然命中 ⇒
#    会把**健康通道**判成额度耗尽（写 +1h 冷却 + 悄悄换评审族）。只匹配带上下文的形态。
# 🔴 **单一真源**：本行即真源。`scripts/probe-models.sh` 的 `probe_codex()` 在运行时用 sed 从本行提取
#    （提取不到才用它自己的 `CODEX_EXHAUSTED_RX_DEFAULT` 兜底），`consistency-check.py` 强制两边逐字一致。
LADDER = [('deepseek-v4.1-flash', 0.03), ('deepseek-v4-flash', 0.17),
          ('qwen3.8-max', None),     ('kimi-k3-1', 1.62)]      # T1..T4
# 🔴 2026-09-24 cb 上 v4.1-flash 涨到 **0.11x**（上面 0.03 是 09-10 定档时的 cb 价，⛔ 已过时）。
#    ⚠️ 这列**纯文档**（逻辑只读 LADDER[i][0]），⛔ 不驱动任何选择 —— 与 T2 的 0.17 同一处境
#    （T2 早已不落 cb，这个数也还留着作量级参照）。T1 本身不变：火山两套餐 + 百炼三池照常，
#    ⇒ 改的是【cb 这一池还要不要】，⛔ 不是档位。见 WALLET_PREF['deepseek-v4.1-flash']。
# 📜 **09-10 定档时的历史依据**（⚠️ 下面两条已失效，别当现行依据读：价格那条 09-24 失效——cb 涨到 0.11x；
#    「只在 cb」那条 09-15 起失效——现为火山两套餐 + 百炼三池。**档位决定本身仍成立**：能力依据未变。）
# 🔴 2026-09-10 T1 由 `glm-5.3-flash` 换成 `deepseek-v4.1-flash`（用户决定）。
#    ⭐ 依据：**0.03x —— glm 的一半价**〔⛔ 09-24 失效〕（⚠️ 同日从 0.06x 降下来的，cb 倍率有时效）；
#       同渠道两臂拉丁方 34.2 vs 32.3，LRU 与并发两题 **4 个朝向全胜**。
#       ⇒ 折算 83% 有效率后等效 **0.036x**，仍比 glm 单发便宜约 40% ⇒ 价格上就已成立。
#    ⚠️ 我先前写的「首次产出有效率 1/3」是 **n=3 的坏运气**，⛔ 已作废 ——
#       实测 12 次 **10/12 = 83%**（并发 4/4 · Kafka 3/4 · LRU 3/4）⇒ 等效倍率 **0.072x**。
#    🔴 **代价一：T1 从三池变一池** —— v4.1-flash **只在 cb**〔⛔ 09-15 起失效〕。
#       ⇒ 用 TIER_PEERS 兜：glm-5.3-flash（三池）降为本档【同档替代】，
#         glm 那三池正好补上可用性，⛔ 不必为撞额度就升到 T2(0.17x)。
#    🔴 **代价二：那 17% 的失败不是报错，是「看着像正常输出」的垃圾**
#       （实测一次 3988 字、正文带 `<｜｜DSML｜｜>` 内部标记）。
#       ⇒ 必须走 OUTPUT_VALIDATION_REQUIRED，⛔ 不能只看 exit 0。
# 🔴 2026-09-10 T3 由 `deepseek-v4-pro` 换成 `qwen3.8-max` —— 用户禁用了前者。
#    ⛔ 为什么不是「撞 T3 就停」：那会把 **T4 的 K3 永久掐断**（i 走不到 3），
#       升档链在 T2 之后就断了。⇒ 换落点，⛔ 不是砍档。
#    ⛔ 为什么不是「留着 v4-pro 靠 §6 拦」：§5 先 first_available(pool) 再 §6 validate()
#       ⇒ 会**真的探活五个池**才被拦（0910 异构审 #3 抓到）。
#    ⭐ 依据：换位盲评 qwen3.8-max 99.5 vs v4-pro 102.0（/120，差 2.5，而 A 位偏好本身 +2.5）
#       ⇒ 判定同档 ⇒ 它本就是 T3 的 TIER_PEERS，直接顶上不改档位定义。
#    ⚠️ 费率写 `None` 是**故意的**：百炼是 token 套餐、这个 id 的 credits 倍率⛔未测。
#       ⛔ 不许填个数字凑齐 —— 逻辑只读 LADDER[i][0]，这一列纯文档。
# ⚠️ T4 的 id 是 `kimi-k3-1`（cb 服务端权威清单）—— ⛔ 2026-09-10 前写的 `kimi-k3-2` 是别名。
# ⚠️ T2 的 `deepseek-v4-flash` 在**火山两套餐 + 百炼**上仍是真实型号；
#    ⛔ 只有 cb 那份变成了指向 v4.1 的别名 ⇒ 见 WALLET_PREF：T2 的池已去掉 cb。
ENTRY  = {'algorithm': 1, 'perf': 1}
# 🔴 2026-09-10 并发两类从 1 改回 **0（T1 起步）** —— 换 T1 后旧依据被**直接推翻**：
#    旧依据是「h2h 并发题 deepseek-v4-flash(T2) 35 > glm-5.3-flash(T1) 31」⇒ 所以跳过 T1。
#    但 T1 现在是 `deepseek-v4.1-flash`，而 4 臂拉丁方里**并发题它 37.5 > T2 的 30.5，
#    +7 分且 4 个朝向全胜** ⇒ 跳过 T1 等于既贵（0.17x vs 0.06x）又更差。
# ⚠️ `algorithm` / `perf` 暂**保留** 1，但依据**已不指向当前 T1** ——
#    那条依据比的是 v4-flash **对 glm**，⛔ 没比过 v4.1-flash。
#    已知：LRU 题 v4.1(33.5) > glm(29.0)，但**未与 v4-flash 比过**（那格取不到输出）。
#    ⇒ 🔴 **待补测**：v4.1-flash vs deepseek-v4-flash 的 LRU / perf 头对头。
#      补出来之前⛔不要当「已验证」用（同 feedback-scoped-comparison-overgeneralized）。
# routing §2 免费档排除分两类，🔴 2026-09-29 起**全部按条目判**（⛔ 不再全局套在所有免费模型上）：
#   · 能力类 = 条目的 avoidTaskTypes ⇒ ⭐ 只有 --free 能放宽（用户显式接受能力风险）
#   · 物理不可用 = 该落点本任务反复无响应 / 本任务已做砸 / 任务要多模态而它不能免费接 / 撞额度冷却中
#     ⇒ ⛔ --free 也不放宽（绕过去也拿不到免费，只会静默变成付费或死循环）
CAPABILITY_BLOCKERS = {'algorithm', 'perf', 'architecture'}      # 能力类的全部取值；avoidTaskTypes ⛔ 只许从这里取

# ⭐ **T0 免费档登记表**（用户 2026-09-29：按表挑，新增 / 下线免费模型**⛔ 不改挑选逻辑**，只改数据）
#    ⚠️ 「只改数据」≠「只改这一张表」：还要改 catalog `freePool`；白名单型 provider 要加 WHITELIST
#       （⛔ 故意不让登记表绕过 P0）；再补标题缩写 —— 漏哪项 consistency §3o 都会报。
#    按 priority 从小到大，取第一个【当前可用】的。⚠️ 与 catalog `freePool.entries` 逐项一致（consistency §3o）。
#    字段：freeUntil  免费截止，本地时间（Asia/Shanghai，⛔ 不带时区，与 now() 同口径）；None = 未公布
#          thinking   默认思考档；None = 该模型**没有思考档**（⛔ 不传，见 NO_THINKING_MODELS）
#          multimodal 能否【免费】接图片 / 视频输入 · avoidTaskTypes 能力短板 · cautionTaskTypes 只提醒不排除
#          retainsData 服务方是否可能留存 prompt（None = 未知）· allowInSensitiveWorkspace 能否用于 ~/wb 等公司目录
#    ⛔ 核价记录（creditRecord）与复核途径（verifyVia）**只在 catalog** —— 那是用户核完写进去的数据，⛔ 不双写。
FREE_POOL = [
  {'upstream': 'openrouter-free', 'model': 'stealth/space-bunny-alpha', 'priority': 1,
   'freeUntil': None, 'thinking': 'high', 'multimodal': True,
   'avoidTaskTypes': set(), 'cautionTaskTypes': {'concurrency_impl'},
   'retainsData': True, 'allowInSensitiveWorkspace': True},
   # ⭐ 09-29 第三轮 12 格同轮：均分 33.3 vs qwen3.8-max 34.5 / glm 34.4 / v4.1 33.7，与三个付费臂逐格都 6:6 ⇒ 与 T1 同档
   #    ⚠️ 三个对照臂**复用 09-24 的同一份答案**重新评审（⛔ 不是重新生成）；Bunny 是直连 API reasoning.effort=high
   # 🔴 D3（用户）：并发实现题 30.0 偏弱（扣余额漏乘数量、字段 snake/camel 不一致）⇒ **只提醒不排除**
   # 🔴 D2（用户）：服务方可能留存 prompt，用户知情并决定 ~/wb 下**也不跳过**
   # ⚠️ 预览期隐身模型，截止未公布、随时可能下线（404 ⇒ 按冷却 / 下线处理）；实测 150–400s/题，偏慢
   # 🔗 2026-10-02 CodeBuddy 内置了同名付费路由 `space-bunny`（x0.03，折扣至 10-07；大概率同一模型，tokenizer 指纹不可区分）：
   #    ⛔ 它**不是**免费条目、⛔ 不自动选（cb 路由没评测过）；只在 cb 白名单里供显式点名。OpenRouter 版下线时它大概率是同一模型的延续（⚠️ 权重同一性未证实，表现要先在 cb 路由评测；见 catalog spaceBunnyCb_20261002）
  {'upstream': 'codebuddy-code', 'model': 'hy3', 'priority': 2,
   'freeUntil': '2026-10-31T23:59', 'thinking': 'max', 'multimodal': False,
   'avoidTaskTypes': {'algorithm', 'perf', 'architecture'}, 'cautionTaskTypes': set(),
   'retainsData': False, 'allowInSensitiveWorkspace': True},
   # 🔴 2026-10-01 CodeBuddy&混元官方公告二次延期至 10-31 23:59（原 09-30）——
   #    同一公告里 hy4-preview 也改成「夜间 23:00-次日8:00 限免延至 10-31」的新结构，
   #    ⛔ 但 hy4-preview 09-15 被弃用的理由是【不稳定/碰墙】，与免费窗口无关 ⇒ 仍不纳入 FREE_POOL。
   # 🔴 用户 2026-09-15：「hy3 能用最高就用最高思考强度」⇒ `max`。
   # ⚠️ **`max` 只验证了「被接受」，⛔ 没验证「想得更多」** —— 同一道推理题实测
   #    `minimal` 1384 / `high` 1130 / `max` **653** reasoning_tokens，非单调（与 `-0731` 六档空转同形）。
   #    ⭐ 但它免费且不报错 ⇒ 按用户指示取最高档，代价为零。
   # ⚠️ avoid 三项就是旧的全局排除清单 —— 那张清单**本来就是给 hy3 定的**（07-20 / 08-21 盲评）
   # ⚠️ 多模态 ⇒ cb 会切到付费多模态模型，免费不成立
  {'upstream': 'qoderclicn', 'model': 'qfmodel', 'priority': 3,
   'freeUntil': None, 'thinking': None, 'multimodal': False,
   # 🔴 2026-10-02 Qoder CN 官方公告：原定 09-30 23:59:59 的免费期延长，10-01 起继续免费，「结束时间将提前在本页公告」
   #    ⇒ 截止未公布（与 Space Bunny 同口径）。⭐ 实测原定 09-30 之后 `total_credits` 仍为 0。
   #    ⚠️ None = 视为开着，⛔ 所以它必须自带失效条件：probe-models.sh 的 QCN 映射对它判 total_credits>0 ⇒ 已计费 ⇒ 冷却 24h
   #       （consistency §3o ⑬ 强制：freeUntil=None 的条目没有计费探测就报错）。
   'avoidTaskTypes': {'algorithm', 'perf'}, 'cautionTaskTypes': set(),
   'retainsData': None, 'allowInSensitiveWorkspace': True},
   # ⭐ Qoder 免费版 Qwen3.8-Flash（仅 Qoder CN 个人用户；企业订阅用户不适用）。🔴 **⛔ 不等于百炼直连版**：
   #    09-24 第二轮 Qoder×2 均分 28.3 / 30.5 vs 百炼版 34.5（11:1 p=0.006）——答案短、快 3–5 倍，疑似默认思考更低
   # avoid algorithm：按实测（LRU 19.5 / 23.2，其余臂 30–32）。
   # avoid perf：⭐ 2026-10-02 agent 自行定下（⛔ 非待决，改回只需删这一项）—— perf 无任何模型的实测；推导：付费阶梯对 perf 跳过 T1、
   #    从 T2 起步（见 ENTRY），比 T1 还弱的免费模型更不该接（审查 r2 也指出只挡 algorithm 会让 perf 落到它）；
   #    架构题（Kafka 34.0 / 35.5）与其余臂同档 ⇒ ⛔ 不扩大到 architecture
]
# 🔴 没有思考档的模型 ⇒ 收尾 thinking 置 None、build_settings ⛔ 不写 thinkingOptionId
#    （⛔ 否则收尾的 `thinking or default_thinking(model)` 会给它补一个 xhigh）
#    ⭐ 免费条目的那部分**由 FREE_POOL 推**（thinking=None 即无思考档）⇒ 新增免费模型⛔不用再改这里（审查 09-29）
NO_THINKING_MODELS = {'kimi-k2.7-code'} | {e['model'] for e in FREE_POOL if e['thinking'] is None}
def default_thinking(m):
    """没给 --thinking 时的默认档：免费条目取 FREE_POOL.thinking，其余 xhigh（routing §4）。"""
    return next((e['thinking'] for e in FREE_POOL if e['model'] == m and e['thinking'] is not None), 'xhigh')

# 🔴 **失败形态分类 —— 决定走哪条换档路径，⛔ 别让 agent 自己找叙事**（用户 2026-09-10 反馈）
#    hy4 经常「碰墙」：允许你用，但**派发后静默停 / 唤不醒**，Paseo 抓不到任何明确错误。
#    ⚠️ 这一类既不是 quota 报错、也不是探活排队（探活当时是过的）⇒ 原先三类都不沾，
#       于是 agent 把它当成「做砸了」，走了【质量/成本升档】那条（那条允许换模型族）⇒ **归类错**。
FAILURE_SHAPES = {
  # 形态 → 归哪条换档路径
  'no_response':     'availability',   # 🔴 派发后无明确错误的静默停 / 唤不醒（hy4 的典型形态）
  'quota_exhausted': 'availability',   # 429 等明确额度报错
  'probe_queued':    'availability',   # 探活未秒回
  'bad_output':      'quality',        # ⭐ **有产出但产出不合格** —— 只有这一类才算「做砸」
}
# ⚠️ **`failed_this_task` 故意不进本表** —— 它是本次改动之前就存在的旧标记，
#    注释原话是「绕过会死循环」⇒ 语义**含混**：既可能指「做砸了」也可能指「没产出」。
#    ⛔ 我无法从这里判定谁在写它、写的是哪种含义 ⇒ ⛔ 不给它假精确的归类。
#    ⇒ 它落到缺省（`bad_output` → quality），**保持旧行为不变**。
# 🔴 **已知迁移缺口**：若收割器按旧习惯用 `failed_this_task` 记「静默停」，
#    它会被算成做砸（顶档换族）**且不进 dead_landings** ⇒ 用户 0910 报的错归类可原样重放。
#    ⇒ 收割时**必须改用新形态名**（`no_response` / `bad_output`）。
#    ⚠️ 与「⛔ 没产出 ⇒ 永远是可用性」的张力来自**旧标记本身含混**，⛔ 不是新规则自相矛盾 ——
#       把它并到 availability 会让旧的真做砸记录停止计数，那是上一轮被抓过的「把升档入口清零」。
#       ⇒ 两害相权：保旧行为 ＋ 显式标缺口。
NO_RESPONSE_LIMIT = 2   # 🔴 同一落点连续无响应达到这个次数 ⇒ 该落点视为【不可用】
#    ⛔ 否则会在死通道上无限重派 —— 「不算做砸」若不配这条，就变成了「永远留在原地重试」。
#    ⚠️ 这正是旧 'failed_this_task' 存在的理由（注释原话：「绕过会死循环」）。
# 🔴 判据：**有没有产出**。⛔ 没产出 ⇒ 永远是可用性，⛔ 不是质量问题。
#    ⇒ `failed_paid_tiers` 只在 'bad_output' 时 +1；'no_response' ⛔ 不计
#      （否则「没回复」会一路把任务顶到 K3，而根因只是通道没响应）。
WALLET_PREF = {                                 # (upstream, 该 provider 上的真实 modelId)
  # 🔴 多池【轮换】，⛔ 不是固定优先级（用户 2026-09-09）——火山【两个套餐】/ 百炼 / cb 地位相同。
  #    加百炼正是因为火山与 cb 这个月量不够 ⇒ 用哪个由「哪个还有量」决定，撞限额换下一个。
  'qwen3.8-max':       [('bailian-token-plan',    'qwen3.8-max')],
                        # 🔴 T3 只有**一个池** —— ⚠️ 这是本次换档留下的**已知弱点**：
                        #    v4-pro 当年有四池轮换，qwen3.8-max 只在百炼。撞限额直接进
                        #    【可用性升档】到 T4（1.62x），⛔ 中间没有缓冲。
                        #    ⇒ 待办：测 qwen3.8-flash 或 minimax-m2.7(cb 0.19x) 能否补 T3 第二池。
                        #    ⭐ 2026-09-24：qwen3.8-flash 这条**补不了**——与 max 同在百炼一个钱包，撞额度一起没（火山也没有 Qwen）。
                        #       剩 minimax-m2.7 待测。见 catalog qwen38flashEval_20260924。
                        # ⛔ v4-pro 的四池已整块移除（用户 2026-09-10 禁用）——
                        #    留着它就等于留着一条会被探活的路径。
  'deepseek-v4-flash': [('volcengine-coding',    'deepseek-v4-flash'),
                        ('volcengine-agent-plan', 'deepseek-v4-flash')],
                        # 🔴 **2026-09-11 百炼被移出本池** —— 用户指出「`-0731` 与 `deepseek-v4-flash`
                        #    是两种模型」，实测坐实（直连百炼端点，同一句输入 `只输出:OK`）：
                        #      · `deepseek-v4-flash`      ⛔ **403 Access to model denied**（存在但账号无权限）
                        #      · `deepseek-v4-flash-0731` ✅ 200，回显 `deepseek-v4-flash-0731`
                        #      · 假 id                     ❌ 404 Model not exist
                        #    ⭐ **403 ≠ 404** ⇒ 裸 id 是**另一个真实模型**，⛔ 不是拼错。
                        #    ⇒ 百炼**根本没有可用的 deepseek-v4-flash** ⇒ ⛔ 它不能当本档的池成员。
                        #    ⇒ T2 只剩**火山两套餐**（原先写三池是错的）。
                        # ⚠️ `deepseek-v4-flash-0731` 是**独立模型，尚未定档** —— 见 catalog 同名条目。
                        # 🔴 **⛔ 现在是【两池】** —— 两次收缩，理由各不相同，⛔ 别混：
                        #    ① 2026-09-10 去掉 **cb**：cb 换代后 `deepseek-v4-flash`
                        #    ⛔ **不在账号权威清单里**（假 id 的 400 正文实测），
                        #    但派它仍返回 200 ⇒ 🔴 **实际跑的是哪套权重测不出来**。
                        #    ⚠️ echo 字段（requestModelId / providerData.model）是**请求回显**，
                        #    ⛔ 不是运行值 —— 本例已自证：它回显了服务端清单里没有的 id。
                        #    ⇒ ⛔ 不派旧 id（不确定跑的是谁，就不该派）。
                        #    ⚠️ 要用 cb 的新型号请显式 --model deepseek-v4.1-flash
                        #    （已定档：⛔ 不进阶梯，见 catalog v41FlashEval_20260910）。
                        #    ② 2026-09-11 去掉 **百炼**：它上面的裸 `deepseek-v4-flash` 实测 **403
                        #    （存在但账号无权限）**，而 `-0731` 是**另一个模型**（见 §BLOCKED / catalog）。
                        #    ⚠️ 措辞注意：⛔ 不是「原先写三池写错了」—— 删改前**确实是三池**，
                        #       错的是「把 `-0731` 当成同一模型的池成员」这个判断，⛔ 不是计数。
  'deepseek-v4.1-flash': [('volcengine-coding',     'deepseek-v4.1-flash'),
                          ('volcengine-agent-plan', 'deepseek-v4.1-flash'),
                          ('bailian-token-plan',    'deepseek-v4.1-flash')],
                        # 🔴 **2026-09-24 cb 移出本池 ⇒ 三池**（用户：cb 费率更新，v4.1-flash 涨价，cb 优先 glm-5.3-flash）。
                        #    cb 面板实测 v4.1-flash **0.11x** vs glm-5.3-flash **0.06x** ⇒ 同钱包里贵了 1.8 倍。
                        #    ⭐ 这是【同一钱包内】比价（都是 cb credits 倍率）⇒ 单位可通约，比较成立；
                        #       ⛔ 与「跨钱包比价算不出」不冲突（那条说的是火山包月 vs cb 倍率）。
                        #    ⭐ 两者**同档**（TIER_PEERS 的换位盲评依据）⇒ 同档里挑便宜的是正当的，
                        #       ⛔ 不是跨档下调（先选档位再挑便宜，见 MEMORY feedback-discount-picks-vendor-not-model）。
                        #    ⇒ 实现：cb 退出 v4.1-flash 的池，**glm-5.3-flash 经 TIER_PEERS 成为 cb 上的 T1 落点**：
                        #      · 自动派发（不指定 provider）⇒ 只在火山两套餐 + 百炼之间轮换，⛔ 不再落 cb
                        #      · 显式 `--provider codebuddy-code` ⇒ §4 的「同档换落点」分支把它换成 cb/glm 并留痕
                        #        （⭐ 该分支 09-23 起被标 unreachable-by-config，本次**重新可达**，豁免已按 §3m 撤掉）
                        #      · 显式 `--provider codebuddy-code --model deepseek-v4.1-flash` ⇒ 照派（白名单仍在，用户自负价差）
                        #    ⚠️ 价格历程 0.06x（09-10 早）→ 0.03x（09-10 晚）→ **0.11x（09-24）**—— cb 倍率有时效，
                        #       再降回来时把 cb 加回本池即可。⚠️ 届时 pipeline-test 的「显式 cb ⇒ 同档换落点 glm」
                        #       用例会红、coverage 那三行会掉 —— 那是**预期信号**：分支又不可达了，按 §3m 的办法重新标豁免。
                        # ⭐ 2026-09-23 **四池**（coding 套餐当天才上，09-15 时还是 404）。
                        # ⚠️ **回显格式因套餐而异，⛔ 不能只凭回显判同一性**：
                        #    coding 回显 `deepseek-v4-1-flash`（裸）、agent-plan 回显
                        #    `deepseek-v4-1-flash-260910`（带快照）—— 看着像两个模型。
                        # ✅ 判定同一模型的**两条硬依据**：
                        #    ① 同句输入 `prompt_tokens` 两家都是 **46**（v4-flash 两家都是 99，同样成对）
                        #    ② 显式点名 `deepseek-v4-1-flash-260910`，**两家都 200**，
                        #       coding 还把它**归一化回裸名** ⇒ 是同一 id 的两种写法
                        # ⛔ 与 `-0731` 那次**性质不同**：那次百炼裸 id 是 **403 无权限**（真的是另一个模型）。
                        #    ⇒ 判据是 **403/404 vs 200 + 指纹**，⛔ 不是「id 字符串长得像不像」。
                        # ⭐ **2026-09-15：三池了** —— 「T1 单池」那条已知弱点**关闭**。
                        #    两家都是当天新上的，各自实测（⛔ 不靠转述）：
                        #      · 火山 agent-plan：直连 200，回显 `deepseek-v4-1-flash`（点变横杠）
                        #        ⚠️ `volcengine-coding` 上**没有**（404 UnsupportedModel）⇒ ⛔ 别写进池
                        #      · 百炼：返回 **429（套餐本周额度耗尽）** 而⛔不是 403
                        #        ⇒ 模型**存在且有权限**，只是钱包当下没量。
                        #        ⭐ 对照同端点：`deepseek-v4-flash` 是 **403 无权限**、假 id 是 **404**
                        #        ⇒ **429 / 403 / 404 三态要分清**，⛔ 别一律当「不可用」。
                        #    ⚠️ 两家都是**裸 id**（⛔ 无快照后缀）⇒ 不触发 §3l 的快照规则。
  'glm-5.3-flash':     [('volcengine-coding',    'glm-5.3-flash'),
                        ('volcengine-agent-plan', 'glm-5.3-flash'),
                        ('codebuddy-code',        'glm-5.3-flash')],
                        # ⚠️ 百炼没有 glm-5.3-flash ⇒ 只在火山两套餐与 cb 之间轮换
  'kimi-k3-1':         [('codebuddy-code',        'kimi-k3-1')],
                        # ⚠️ 只有 cb 一家。⭐ 显式列出而⛔不靠默认合成池——
                        #    靠默认值会让「新加的阶梯模型忘了配 wallet」静默变成 cb 落点。
}
# ⭐ 火山【两个套餐】= 两个独立额度池，⛔ 不是同一个（用户 2026-09-09：「额度相互轮换就行」）
#    coding = …/api/coding/v3（8 模型）· agent-plan = …/api/plan/v3（13 模型）
#    阶梯三档在两边【id 完全相同】⇒ 撞限额直接换另一个，⛔ 不用改 model 名。

# ⭐ 同档替代：换位盲评实测【与本档同档】的其它模型。🔴 这是【档内换落点】，⛔ 不是升降档。
#    ⛔ 只在本档模型的所有池都拿不到时才用（**可用性**理由）；主落点可用时⛔不许插队。
#    ⚠️ 这跟【质量/成本升档】（做砸才升）是两条路，⛔ 别混。
TIER_PEERS = {
  # ⭐ T1：glm-5.3-flash 是 v4.1-flash 的同档替代，两个用途：
  #    ① 可用性：v4.1-flash 三池（火山两套餐 + 百炼）全拿不到时顶上
  #    ② 🔴 2026-09-24 起兼任 **cb 上的 T1 落点** —— cb 已移出 v4.1-flash 的池（涨到 0.11x > glm 0.06x），
  #       显式 `--provider codebuddy-code` 经 §4「同档换落点」落到本表的 cb/glm。
  #    ⚠️ 本表历史上写过「v4.1-flash 单池（cb）」—— 09-15 起就不是单池了，那句早已过时。
  #    依据：同渠道两臂 A/B 对调拉丁方 34.2 vs 32.3 —— **不弱于**即满足同档要求
  #    （v4.1 胜 LRU/并发两题各 2 朝向，glm 胜 Kafka）。⛔ 主落点可用时不许插队。
  'deepseek-v4.1-flash': [('volcengine-coding',     'glm-5.3-flash'),
                          ('volcengine-agent-plan', 'glm-5.3-flash'),
                          ('codebuddy-code',        'glm-5.3-flash')],
  # 🔴 2026-09-10 T3 那条已清空 —— 原本是 `deepseek-v4-pro` → `qwen3.8-max`。
  #    用户禁用 v4-pro 后 qwen3.8-max **升为 T3 主落点** ⇒ 本档不再有同档替代。
  #    ⇒ T3 唯一池拿不到时走【可用性升档】到 T4（那条路径已有用例覆盖）。
  #    ⛔ 不要为了「让表非空」把某个未测模型填进来 —— 同档替代的唯一依据是换位盲评。
}

# 🔴 最后兜底 —— ⛔ 只在【阶梯到顶仍拿不到】时才走（用户 2026-09-09 授权）
LAST_RESORT = ('claude', 'claude-sonnet-5', 'max')      # Paseo: claude/claude-sonnet-5 · mode=auto
# ⭐ **整套钱包体系存在的目的就是【不占用 Claude 套餐额度】**（留给主会话）。
#    ⛔ 但「不能不干活」优先于「省额度」⇒ 到顶了宁可用它，也⛔不要停在半路。
#    🔴 走到这里 = 正在烧掉这套体系本来要保护的东西 ⇒ **必须显著报告**，⛔ 不许静默。
#    ⛔ 它⛔不是阶梯的 T5，⛔ 不参与「做砸就升档」那条路径 —— 只有可用性耗尽才够得着。
# 依据（2026-09-09 换位盲评，判 gpt-5.5·medium，两臂 thinking 一致、prompt 逐字相同）：
#   总分 qwen3.8-max 99.5 vs deepseek-v4-pro 102.0（/120，差 2.5）——
#   而同一轮实测【A 位本身有 +2.5 分优势】⇒ ⛔ 这个差不构成谁更强，判定为【同档】。
# ⚠️ 分项分化明显，⛔ 但这条【只在这两者之间成立】——未与 glm-5.3-flash / kimi-k3-2 比过：
#      架构题 qwen 37.5 > v4-pro 31.0 ｜ 代码实现题 v4-pro 33.0 > qwen 25.5 ｜ 并发诊断基本平
#   ⇒ ⛔ 不要据此写「架构题走 qwen」——架构类的入口档是 T1，跟本表不在同一层。
# ⛔ 未测：qwen3.8-max 与 deepseek-v4-pro-0813 在百炼的 credits 倍率 ⇒ 【档内挑便宜】那步还没依据，
#    所以本表只当【兜底】排在最后，⛔ 不参与折扣排序。
# ⭐ 各池各有折扣窗口，⛔ 窗口不一样，别只记住其中一个
DISCOUNT_WINDOWS = {
  'bailian-token-plan': {                      # 每天 22:00 – 次日 08:00
     # ⭐ 2026-09-15 加 deepseek-v4.1-flash —— 控制台标「限时夜间5折」（用户截图确认）
     'models': {'deepseek-v4-pro-0813', 'deepseek-v4-flash-0731', 'qwen3.8-max',
                'deepseek-v4.1-flash', 'qwen3.8-flash'},   # 09-29 控制台：qwen3.8 两个都是「限时夜间4折」
     'when':   lambda dt: dt.hour >= 22 or dt.hour < 8},
  'codebuddy-code': {                          # ⛔【工作日 09-12 / 14-18】之外都打折
     # 🔴 2026-09-10 换代连带后果：cb 上**已无** deepseek-v4-flash ⇒ 从折扣集移除。
     # ⚠️ `deepseek-v4.1-flash` 是否继承这个峰谷折扣 **⛔ 未确认**（用户当时只说
     #    「Deepseek-V4-Flash、Deepseek-V4-Pro」）⇒ ⛔ 先不加，别拿推测当依据。
     # ⇒ 现在 T2（deepseek-v4-flash）**吃不到 cb 折扣了** —— 它的三个池里没有 cb。
     # 🔴 2026-09-10 再连带：唯一成员 deepseek-v4-pro 已被用户禁用 ⇒ 折扣集**空**
     #    ⇒ **cb 折扣目前对阶梯没有任何作用点**。⛔ 不要因此删掉本条目 ——
     #       `deepseek-v4.1-flash` 若确认继承峰谷折扣，它就会复活。
     'models': set(),
     'when':   lambda dt: not (dt.weekday() < 5 and (9 <= dt.hour < 12 or 14 <= dt.hour < 18))},
}
# 🔴 免费档窗口过期后的**唯一复核闸门** —— ⛔ 之前只写了调用、没写定义
#    （异构审 0911 #1 抓到）。定义必须严格，⛔ 不许靠模型自述或体感。
# 🔴🔴 **2026-09-11 改名 + 补条件**：原名 `rate_reverified` 只判「核实过且够新」，
#    ⛔ **没判「核实结果是不是仍为 0」** ⇒ 用户核出 hy4 已计费 0.5x 并如实写进 catalog 后，
#    这道闸门会返回 True ⇒ 把一个 **0.5x 的模型当免费档用**（比 T1 的 0.03x 贵 16 倍）。
#    ⭐ 最坏的是：这个后果由「用户做了正确的事（去核实）」触发。
#    ⇒ 名字必须说出真正的谓词：**t0_still_free**，⛔ 不是「有没有核过」。
RATE_RECHECK_MAX_AGE_DAYS = 7
def promo_active(e):
    """免费窗口是否仍开着。freeUntil 为 None = 截止未公布 ⇒ 视为开着（⚠️ 预览期随时可能下线，靠探活兜）。"""
    return e['freeUntil'] is None or now() <= parse_local_time(e['freeUntil'])

def t0_still_free(e, dt=now()):
    """🔴 判据 = catalog 里该条目的 creditRecord.credit **仍为 0**，且核实发生在**窗口之后**、日期**足够新**。
       ⛔ 不接受：模型自述（实测答「不知道」）· `--help`（只有型号清单）。
       ✅ 直接证据：cb `-p` JSON 的 `providerData.rawUsage.credit`（实扣，hy3 实测 0）· OpenRouter 响应 `usage.cost` · 用户给的 /model 面板读数。
       ⚠️ 09-11 起我记的「rawUsage 只有 token 数、费率 agent 拿不到」已被 2026-10-02 实测推翻（本机 2.160.0 与 Paseo 钉的 2.106.1 都带 credit）。
       ⇒ 复核按条目的 verifyVia 做（可由 agent 自己跑），结果写进 catalog 的 creditRecord。
       ⚠️ 只在 promo_active(e) 为假时调用 ⇒ 此处 freeUntil 必非 None。"""
    rec = catalog_credit_record(e['upstream'], e['model'])   # {'credit': float, 'verifiedOn': 'YYYY-MM-DD'} 或 None
    if not rec or rec.get('verifiedOn') is None:
        return False                        # 没核过
    if rec['verifiedOn'] <= e['freeUntil'][:10]:
        return False                        # 🔴 窗口内核的只证明「促销价是 0」，⛔ 不证明窗口后仍免费
        # ⚠️ 2026-09-29 加：条目带上 freeUntil 之后这个洞才构造得出来 —— hy3 的记录是 09-24 面板 0.00x，
        #    按旧规则到 10-01 仍在 7 天内 ⇒ 会把可能已开始计费的 hy3 当免费再用一天。
        #    ⚠️ 截止当天核的也不算：窗口到当天 23:59 才关（该条目的 freeUntil 是哪天就按哪天算，⛔ 不是写死 09-30）。
    if days_between(rec['verifiedOn'], dt) > RATE_RECHECK_MAX_AGE_DAYS:
        return False                        # 🔴 核实记录过期 —— 本次事故就是陈旧记录被实测证伪
        # ⚠️ 符号约定：`days_between(早, 晚)` 返回**正数天数**（= 晚 − 早）。
        #    ⛔ 若实现反了，这道闸门形同虚设。用例已钉住：08-11 对 09-10 ⇒ 30 天 ⇒ 判未复核。
    return rec.get('credit') == 0.0         # 🔴 核过且够新，但**已计费** ⇒ ⛔ 它不再是免费档

# 🔴 **审查时机门控**（2026-09-11 加）—— 派 CHECK 5 审查前先问 agent-gates 该不该审。
#    起因：0910 有条会话把任务拆小块并行开发，**每修完一小条就派一个 agent 跑全量审查**
#    ⇒ 11 个 agent + ≥7 次全量**全部白烧**：审查产物带锚点（REVIEW_HEAD / REVIEW_DIFF_SHA256），
#    代码一改锚点就作废；其中一份根本没看见后续 637+ 行改动（含它自己要求的修复）。
#    ⚠️ agent-gates 侧已有时机门控，但它**只拦走 `agent-gates-review` 的审查** ——
#       那 11 个是会话用 Paseo 直接派的，绕过了那条命令 ⇒ **必须在派发侧再拦一道**。

# ⛔ 它**不在 PATH 上**（`command -v agent-gates-review` 返回空）⇒ 必须走绝对路径，
#    否则 command not found。
AGENT_GATES_REVIEW = '${AGENT_GATES_DIR:-$HOME/.agent-gates}/bin/agent-gates-review'

# 🔴 「审查类」只指 **CHECK 5 的交叉 / 门禁 / 复审**（标题如 `[门禁审查A]` `[Review]` `[审]`）。
#    ⛔ 不含 `[验收]`（那是 CHECK 6 verify，验收本来就该在改完之后跑，拦它是错的）；
#    ⛔ 不含开发 / 修复任务。
VERIFY_MARKERS = ('[验收]', '验收', 'CHECK 6', 'check6')
def is_check5_review(task_type, text):
    return task_type == 'review' and not any(k in text for k in VERIFY_MARKERS)

def review_due(cwd):
    """问 agent-gates：现在该不该做交叉审查。

       契约（2026-09-11 实测）：
         exit 0  ⇒ 该审（due=yes）
         exit 79 ⇒ 轮不到（due=no）
         stdout 恒为 key=value 行：due / reason / branch / review_mode / when
       零成本：不需要 prompt 文件、不调模型、不写产物。

       🔴🔴 **只有 exit 79 才算 due=no** —— 0 / 1 / 127 / 命令不存在 一律**放行**（fail-open）。
       ⚠️ 已装的 2.9.8 还不认 `--due`，实测 `exit 1` + stderr `unknown arg: -C`。
          把「问不出来」当成 due=no 会**把审查派发整体掐死** —— 那比不拦还糟。
    """
    # ⚠️ 必须传**派发目标的实际 cwd/worktree**，⛔ 别随手传仓库根。
    #    理由不是「子目录判定会漂」—— 那是 agent-gates 的 bug，本次校验把它抓出来了
    #    （子目录里 `git rev-parse --git-common-dir` 返回相对路径 `../.git`，项目配置整份丢掉、
    #    静默回落成 strict），已在 **2.9.9** 修掉并加了回归用例，现在仓根/子目录判定一致。
    #    真正的理由是：**同一仓库的不同 worktree 可能在不同分支上**，判定按分支走 ⇒
    #    传错目录就是在问另一个上下文的时机。
    rc, out = run_capture(['bash', AGENT_GATES_REVIEW, '--due', '-C', cwd])
    if rc != 79:
        return None          # ⛔ 放行：问不出来 ⇒ 当作「该审」
    return parse_kv(out)     # {'due','reason','branch','review_mode','when'}

def is_discounted_now(upstream, model_id, dt=now()):
    w = DISCOUNT_WINDOWS.get(upstream)
    return bool(w) and model_id in w['models'] and w['when'](dt)
# ⚠️ codebuddy 的折扣面**远大于**百炼：它只在工作日两段高峰是原价，其余（含整个周末）都 5 折。
#    ⇒ ⛔ 别把规则记成「夜间优先百炼」——多数时段其实是 codebuddy 在打折。

def split_provider(s):
    """pi/jdcloud-joyagent/X → ('pi','jdcloud-joyagent')；codebuddy-code → (None,'codebuddy-code')"""
    parts = s.split('/')
    return ('pi', parts[1]) if parts[0] == 'pi' and len(parts) >= 2 else (None, parts[0])

def normalize_provider(upstream, channel):
    return f'pi/{upstream}' if (channel == 'paseo' and upstream in PI_HOSTED) else upstream

def validate(upstream, model):
    """🔴 P0。⛔ 三层依次判——只写「在白名单里才校验」会让未知 provider 静默跳过。
       ⚠️ model 为 None 时只校验 provider 本身。"""
    if upstream in DISABLED_PROVIDERS:
        report_disabled_and_stop()          # 🔴 provider 级停用**先报** —— 它比型号级更根本
    # 🔴 屏蔽名单必须在【白名单/豁免判断之前】—— ⛔ 放到豁免之后就对豁免 provider 失效。
    #    ⚠️ 但也⛔不能抢在 DISABLED 之前：`--provider deepseek --model <被禁型号>`
    #       的真实原因是**整个 provider 停用**，报成「型号被禁」是给了错原因（同 0909 R7 的教训）。
    if model is not None and (model in BLOCKED_MODELS_ANY_PROVIDER          # 🔴 全局，与 provider 无关
                              or model in BLOCKED_MODELS.get(upstream, ())):  # provider-keyed
        report_blocked_model_and_stop(upstream, model)
    if upstream in WHITELIST:
        if model is not None and model not in WHITELIST[upstream]:
            report_conflict_and_stop()      # ⇒ pi/jdcloud-joyagent/GLM-5.2 在这里被拦
    elif upstream not in EXEMPT_PROVIDERS:  report_unknown_provider_and_stop()

# 🔴 显式值单独存，⛔ 后续阶段只读不写
explicit_upstream = split_provider(args.provider)[1] if args.provider else None
explicit_model    = resolve_short_name(args.model)   if args.model    else None
# 🔴 ⛔ 后面一律用 `is None` 判，⛔ 不许用 truthiness ——
#    `explicit_model or REVIEW_DEFAULT_MODEL` 会把空串/解析成空值的非法输入【静默当成没指定】（0909 第 7 轮审查）。
if args.model is not None and not str(args.model).strip():
    report_conflict_and_stop()      # ⛔ 空 --model 是输入错误，不是「没指定」
explicit_thinking = args.thinking                                # 可为 None

task_type = classify(user_input)          # routing §6；⚠️ concurrency 要先判子类
scope     = estimate_scope(user_input, args)   # 文件数 / 预计工具调用数 —— 供 is_large_review
cwd       = resolve_worktree(args.worktree)
agent_id  = None                          # 🔴 只有 Paseo 派发才会被赋上，CLI 路径保持 None
# 🔴 只数 **'quality'** 那一类（= 有产出但产出不合格）—— 判据见 FAILURE_SHAPES。
#    ⛔ 「没回复 / 静默停」是 **availability**，⛔ 不计入 —— 否则通道没响应会把任务一路顶到 K3。
#    ⚠️ 这条以前只写在注释里，agent 只能自己找叙事 ⇒ 实测被误判成「做砸」（用户 2026-09-10 反馈）。
# 🔴 **缺省必须是 'bad_output'（质量类）** —— ⛔ 不能是 None、⛔ 不能是可用性类。
#    理由：`shape` 这个字段是**本次新加的**，历史/外部产生的失败条目**不带它**。
#    若缺省落到可用性类，计数恒 0 ⇒ 【质量/成本升档唯一入口】被**整条清零**，
#    真的做砸也升不了档 —— 那是把合法路径堵死（异构审 2026-09-10 #1 抓到）。
#    ⇒ 缺省取「保留旧行为」的那一侧；**只有显式标成 no_response 的才被排除**。
failed_paid_tiers_in_this_task = sum(
    1 for f in past_failures(task_context)
    if f.get('tier') is not None                              # T0 免费档失败⛔不计
    and FAILURE_SHAPES.get(f.get('shape', 'bad_output'), 'quality') == 'quality')
# 🔴 同一落点反复无响应 ⇒ 把它排除掉，⛔ 不许原地无限重派
dead_landings = {(f['upstream'], f['model']) for f in past_failures(task_context)
                 if f.get('shape') == 'no_response'
                 and f.get('count', 1) >= NO_RESPONSE_LIMIT
                 and f.get('upstream') and f.get('model')}
# 🔴 本任务里已在某个**免费落点**做砸（有产出但不合格）⇒ 只排除**那一条**，其余免费条目照常可试
#    ⚠️ 判据与 failed_paid_tiers 同一张 FAILURE_SHAPES 表、同一个缺省 —— ⛔ 别另起一套口径
#    ⚠️ 这里⛔不计入付费档的做砸数（T0 的失败 tier 为 None，上面那条本来就不数它）
free_failed_landings = {(f['upstream'], f['model']) for f in past_failures(task_context)
                        if f.get('tier') is None and f.get('upstream') and f.get('model')
                        and FAILURE_SHAPES.get(f.get('shape', 'bad_output'), 'quality') == 'quality'}
# 🔴 provider affinity 的**证据**：cb 接了活然后静默（⛔ 不是「碰过 cb」）
cb_accepted_then_silent = any(f.get('upstream') == 'codebuddy-code'
                              and f.get('shape') == 'no_response'
                              for f in past_failures(task_context))
#   ⛔ 同一档重试⛔不计 —— past_failures 按【档】去重，⛔ 不按次数
#   ⚠️ 数不出来（无本任务历史）就是 0，⛔ 不要凭「任务看着难」估一个值
upstream, model, thinking = explicit_upstream, explicit_model, explicit_thinking
availability_escalations = []    # ⭐【可用性升档】留痕，⛔ 收尾必须报告（§7）
provider_affinity = None     # 🔴 非空时，池内排序把该 provider 提到最前（⛔ 只重排，不换档不换模型）
t0_now_billed = []           # 🔴 (型号, 倍率) —— 核实过、确认**已开始计费** ⇒ T0 对它关闭
#   ⚠️ 它可能仍比 T1 便宜，但**那是定档问题** ⇒ 走盲评流程，⛔ 不因为「以前是免费档」就继续当 T0 用。
t0_free_unverified = []      # 🔴 免费窗口已过但**仍探活通过**的型号 ⇒ §7 必须提示「费率待核」
#   ⛔ 不静默丢掉 —— 若它其实还免费，跳过就是白付 T1 的钱。
tier_substitutions = []      # ⭐ (原model, 换成, 原因) —— 显式 provider 上没有本档主落点时的同档换落点
#   ⛔ 与 availability_escalations 分开记：那个是【跨档】向上，这个是【档内】换落点，§7 措辞不同。
free_cautions = []           # ⭐ (免费落点model, task_type) —— 命中条目的 cautionTaskTypes ⇒ §7 必须打出提醒
free_skipped  = []           # (upstream, model, 原因集合) —— 被跳过的免费条目；--free 拿不到时整张表报给用户
t0_probed = False            # 🔴 T0 已对选中的免费落点探过活 ⇒ §5 ⛔ 不再探第二次（第二次失败只会停，不会试下一个免费条目）

# ═══ 1. 显式 provider 先过 P0 ═══ 此时 model 可能仍是 None，validate 允许
# 🔴 ⛔ review 的 provider 冲突必须【抢在 P0 之前】判（0909 第 7 轮审查）——
#    否则 `review --provider deepseek` 报的是「provider 已停用」、
#    `review --provider codebuddy-code --model glm-5.3-flash` 报的是「白名单不匹配」，
#    **用户拿到的原因全是错的**（真实原因是「审查通道不能换 provider」）。
#    ⭐ 2026-10-06 起合法的 review provider 只有 `codex`（原 github-copilot 全族已死，
#    显式 copilot 在这里报 review 冲突 —— 拦截位置不变，理由字段随默认走）。
if task_type == 'review' and explicit_upstream not in (None, REVIEW_DEFAULT_PROVIDER):
    report_review_provider_conflict_and_stop(explicit_upstream)
if explicit_upstream is not None:
    validate(explicit_upstream, explicit_model)

# ═══ 2. --free 只置标志，⛔ 不提前退出（落点在第 4 段）═══
want_free = args.free and explicit_model is None

# ═══ 3. review 硬例外 ═══ 只定【模型 + 默认 provider】，⛔ 不在这里定通道（通道统一在第 6 段）
# 🔴🔴 ⛔ 这一段【不许】被 explicit_model 挡住（0909 第 6 轮审查）——
#    原先写的是 `if task_type == 'review' and explicit_model is None:`，于是
#    `--model X` 一加就整段绕过，三个洞同时开：
#      ① `--free × review` 冲突被【静默吞掉】（want_free 自己也带 explicit_model 门）
#      ② `review --model glm-5.3-flash` 掉进普通阶梯，去试【普通任务路径】（语义完全错）
#      ③ `review --provider 火山 --model X` 绕过 provider 冲突判断，直接派到实施族上
#    ⇒ 判断条件只能是 task_type，⛔ 不能再带 explicit_model。
if task_type == 'review':
    # ⛔ 用 args.free 而⛔不是 want_free —— want_free 自带 `and explicit_model is None`，
    #    在这里用它等于把洞 ① 留着。
    if args.free: report_conflict_free_vs_review_and_stop()   # ⛔ 不替用户决定牺牲哪边
    # 🔴 **派发前问时机** —— ⛔ 只拦 CHECK 5，⛔ 只在 exit 79 时拦（其余一律 fail-open）
    if is_check5_review(task_type, user_input):
        _due = review_due(cwd)
        if _due is not None:
            report_review_not_due_and_stop(_due)   # 输出须带 when= 与逃生门 --early
    model = REVIEW_DEFAULT_MODEL if explicit_model is None else explicit_model
    #                 ↑ ⛔ 用 `is None`，⛔ 不用 `or` —— 见第 1 段那条注释
    # 🔴 ⛔ 不许静默覆盖显式 --provider：本段职责是「未指定时给默认」，⛔ 不是「强行改成 codex」。
    if explicit_upstream is None:
        upstream = REVIEW_DEFAULT_PROVIDER   # ⭐ review 的默认 provider（2026-10-06 起 = codex）
    else:
        # 🔴 走到这里 explicit_upstream **必然是** REVIEW_DEFAULT_PROVIDER —— 其它值在【第 1 段】
        #    （P0 之前那个 review 冲突检查）就被 report_review_provider_conflict_and_stop 拦掉了。
        # ⚠️ 这里原本重复写了一遍 elif + 报错，**覆盖率实测那几行从没被走到** ⇒ 是死代码。
        #    死代码在「当规范读」的伪代码里有害：读的人会以为拦截发生在这里。
        assert explicit_upstream == REVIEW_DEFAULT_PROVIDER
    # ⚠️ 措辞校准：是「**未显式指定时**默认 REVIEW_DEFAULT_MODEL」，⛔ 不是「不可覆盖」——
    #    P1 显式优先仍然成立（routing 附录 P1 在 P2 之前）。
    # ⛔ 但显式指定同族模型时必须报冲突：评审族 ≠ 实施族（routing §5）是不变量。
    #    主会话是 Claude ⇒ ⛔ 不用 claude/*
    # 🔴 **codex 撞额度 ⇒ 走降级阶梯**（2026-10-06 异构审 P1-3：阶梯此前只有常量、没有可执行落点）：
    #    触发判据 = `probe-models.sh` 的 `probe_codex()` 报 FAILC（rc≠0 且命中 CODEX_EXHAUSTED_RX，
    #    通道级 —— 额度按 workspace 算，整个 codex provider 都不可用），或真派发时 stderr 命中同一签名。
    #    ⛔ 不许静默：换档必须写进派发记录（派给谁、为什么换）并**当轮告知用户**。
    #    ⛔ 不许回落 claude 族（主会话）/ copilot 族（全族已死）；同族档直接跳过（异构不变量）。
    #    阶梯全撞完 ⇒ `report_review_channel_unavailable_and_stop()`（当轮 review 未完成，⛔ 不拿同族凑数）。
    # 🔴 **codex 撞额度 ⇒ 走降级阶梯**（2026-10-06 异构审 P1-3：阶梯此前只有常量、没有可执行落点）：
    #    判据 = §3.2c 的 `codex_exhausted_report()` 返回非 None —— 即 probe 报 FAILC
    #    （rc≠0 且命中 CODEX_EXHAUSTED_RX，**通道级**：额度按 workspace 算，整个 codex provider 都不可用），
    #    或真派发时 stderr 命中同一签名。
    #    ⛔ 不许静默：换档必须 `warn()` 出来并**当轮告知用户**（派给谁、为什么换）。
    #    ⛔ 不许回落 claude 族（主会话）/ copilot 族（全族已死）；同族档直接跳过（异构不变量）。
    #    ⛔ 本段不许 return（统一收尾在 §6/§7）——这里只改 `upstream`/`model` 两个落点变量。
    _cx = codex_exhausted_report()
    if _cx is not None:
        _impl_family, _detail = _cx
        for _prov, _mid in REVIEW_FALLBACK_LADDER:   # ① qoderclicn/qfmodel ② codebuddy-code/hy3 ③ …/glm-5.3-flash
            if family_of(_prov, _mid) == _impl_family:
                continue                             # 🔴 评审族 ≠ 实施族
            if not family_is_alive(_prov):            # ⛔ 死族（copilot / 已停用 provider）直接跳
                continue
            if probe_model(_prov, _mid).ok:
                upstream, model = _prov, _mid         # 落点交给统一收尾去派发 + 记录
                warn(f'codex 额度耗尽（{_detail}）⇒ 审查降级 {_prov}/{_mid}')   # 🔴 显式记录
                break
        else:
            report_review_channel_unavailable_and_stop(_detail)   # 阶梯全撞完 ⇒ 停并报（⛔ 不拿同族凑数）

# ═══ 4. 选模型：T0 免费档 → T1..T4 阶梯 ═══ ⛔ 只赋值，不 return
elif model is None:
    # ⭐ **T0 = 按 FREE_POOL 的 priority 依次试，取第一个【当前可用】的**（2026-09-29 起登记表驱动）。
    #    📜 09-15 ~ 09-28 这里写死 `for m in ('hy3',)`：hy4-preview 不稳定被弃用、hy3-x 本来就收费（0.05x）
    #       ⇒ 当时 T0 只剩 hy3。09-29 用户加了 Space Bunny / qfmodel 并要求「以后新免费模型只改表」。
    # 🔴 阻断**全部按条目判**，⛔ 不连带其它条目 —— cb 撞 429 ⛔ 不该把 OpenRouter / Qoder 一起跳过
    #    （原先 quota_exhausted / probe_queued 是全局前置，只有一个免费成员时看不出问题）。
    needs_mm = needs_multimodal(user_input, args)
    for e in sorted(FREE_POOL, key=lambda e: e['priority']):
        u, m = e['upstream'], e['model']
        # ⚠️ 显式 provider ⇒ 只看同 provider 的免费条目，⛔ 不算冲突
        #    （原先一律要求 explicit_upstream is None，会让 `--free --provider codebuddy-code`
        #     直接掉进 report_free_unavailable_and_stop，0909 审查抓到）
        if explicit_upstream not in (None, u):
            continue
        assert set(e['avoidTaskTypes']) <= CAPABILITY_BLOCKERS   # ⛔ avoid 只许写能力类（--free 放宽的前提）
        # ── 硬阻断：⛔ --free 也不放宽。🔴 必须全部判在**任何探活之前** ——
        #    ⛔ 否则会对「本任务里已反复静默」的落点再探一次活，正是 dead_landings 当初要挡的超时路径（异构审 0911 #2）
        hard = set()
        if (u, m) in dead_landings:          hard.add('no_response')        # 本任务里反复无响应
        if (u, m) in free_failed_landings:   hard.add('failed_this_task')   # 本任务里已做砸
        if needs_mm and not e['multimodal']: hard.add('multimodal')         # 会被切到付费模型，免费不成立
        cd = cooldown_until(u, m)            # 撞额度的冷却记录（~/.cache/rift-dispatch/cooldown.json）；没撞过 ⇒ None
        if cd is not None and cd > now():    hard.add('quota_cooldown')     # ⛔ 不许拿 None 去比较
        # ── 能力短板：⭐ 只有 --free 能放宽
        soft = set(e['avoidTaskTypes']) & {task_type}
        if hard or (soft and not want_free):
            free_skipped.append((u, m, hard | soft))
            continue
        # 🔴 **窗口过期 ⛔ 不等于不能用** —— 2026-09-11 实测：记录的免费期已过，hy4-preview 当天照样
        #    **7s 秒回** ⇒ 要么延期了（cb 有前例）、要么**开始计费了**。⛔ 两头都不能赌：
        #      · 日期到了就直接跳过 ⇒ 白付 T1 的钱，而 0.00x 可能还在
        #      · 闭着眼继续用   ⇒ 若已计费，费率未知，可能比 T1 还贵
        #    ⇒ 过期后**要求费率复核**：窗口之后核过且仍为 0（t0_still_free）才用，
        #      否则跳过，并在 §7 提示「仍可用但费率未核，核实后可能更省」（复核途径见 catalog 条目的 verifyVia）。
        if not promo_active(e) and not t0_still_free(e):
            rec = catalog_credit_record(u, m)
            if rec and rec.get('credit') not in (None, 0.0):
                t0_now_billed.append((m, rec['credit']))   # 🔴 核过了，确认已计费
            elif probe_ok(u, m):
                t0_free_unverified.append(m)    # ⇒ §7 提示，⛔ 不静默丢掉这个机会
            free_skipped.append((u, m, {'expired'}))
            continue
            # ⚠️ `continue` 必须**在未复核这个分支里面** —— 写成无条件 continue
            #    会让「已复核」也照样跳过（第一版就是这个错，用例当场抓到）
        if probe_ok(u, m):                      # ⚠️ 长任务必须探活，怕撞排队 / 当日赠额耗尽
            upstream, model, t0_probed = u, m, True
            thinking = explicit_thinking if explicit_thinking is not None else e['thinking']
            #          ↑ ⛔ 用 `is not None`，⛔ 不用 `or`（见第 1 段）；条目 thinking 为 None ⇒ 该模型无思考档
            if task_type in e['cautionTaskTypes']:
                free_cautions.append((m, task_type))    # ⇒ §7 必须打出，⛔ 只提醒不排除
            break
        free_skipped.append((u, m, {'probe_failed'}))
    if model is None and want_free:
        report_free_unavailable_and_stop(free_skipped)   # 🔴 显式要免费却拿不到 ⇒ 停，并列出每条为什么不行
    if model is None:                                # T1..T4
        i = ENTRY.get(task_type, 0) + failed_paid_tiers_in_this_task
        # ⛔ failed_paid_tiers 只数【付费阶梯内】做砸的档数：T0 不计、同档重试不计
        if i > 3: report_ladder_exhausted_and_stop()  # ⛔ 不静默重派 K3
        if i == 3: warn('🔴 K3 1.62x，派完必须核 git log 有无 commit（0723 空转前科）')
        model = LADDER[i][0]
        thinking = thinking or 'xhigh'
        # 🔴 **cb 接过活然后静默 ⇒ 落点优先留在 cb**，⛔ 不跨钱包。
        #    ⚠️ 措辞按代码来：判据是「cb 吞下过请求」，⛔ 不限于 T0 那一档
        #    （异构审第 4 轮的非阻断观察：原措辞写「T0 失败」比代码窄）。
        #    用户 2026-09-10 明确：「hy4 失效 → cb 的 deepseek-v4.1-flash」，⛔ 不要换 pi。
        #    依据：cb 通道**本身是活的**（它刚把 hy4 的请求吞了）。📜 09-10 时 T0 只跑在 cb 上；09-29 起 T0 还有
        #    OpenRouter / Qoder，但判据本来就是「**cb** 接了活然后静默」，与 T0 有几家无关 ⇒ 本段逻辑不变
        #    ⇒ 换钱包是**没有依据**的动作，只是 agent 手边最熟的动作。
        #    ⚠️ 这只**重排池内顺序**，⛔ 不改档位、⛔ 不改模型 —— 池里没有 cb 时自然回到轮换。
        #    ⭐ 写成不变量而⛔不是靠巧合：现在 T1 恰好只在 cb，但将来 T1 换人就丢了这个性质。
        # 🔴 **2026-09-24 上面那句预言兑现了**：cb 移出 v4.1-flash 的池（涨价）⇒ affinity=cb 在 T1 主池
        #    **无作用点** ⇒ 按本段不变量「回到轮换」落火山 coding（pi）。
        #    ⚠️ 这与 09-10 那句「⛔ 不要换 pi」字面冲突 —— 当时留在 cb 恰好就能拿到最强的 T1，
        #       两个诉求重合；现在分叉成「留 cb 用 glm（弱一点、0.06x）」vs「换火山用 v4.1（强、包月）」。
        #    ⏳ **待用户裁定**。未裁定前按本段既有不变量执行（⛔ affinity 不改模型），
        #       ⛔ 不擅自把 affinity 扩成「顺带换同档 peer」。
        #    ⭐ 注意：v4.1 三池全挂时，§5 的同档替代那步 affinity **仍然生效** ⇒ 落 cb/glm（用例已覆盖）。
        # 🔴 依据必须是「**cb 确实接了活然后静默**」，⛔ 不是「碰过 cb」。
        #    ⛔ 「进过 T0 分支」太宽（免费期没开压根没发请求）；
        #    ⛔ 「promo 有效」也太宽（探活全挂时 cb 一个请求都没成功吞过）
        #       —— 异构审连续两轮都把这两种写法抓成「无证据的偏好」。
        #    ⭐ 真正的证据形态就是用户报的那个：hy4 被允许使用、派发出去了、**然后静默停**
        #       ⇒ 本任务失败记录里有 cb 落点的 no_response ⇒ cb 通道是活的。
        if explicit_upstream is None and cb_accepted_then_silent:
            provider_affinity = 'codebuddy-code'

# 🔴 显式 provider ＋【自动选出】的 model ⇒ 这一对必须是**已知存在**的组合。
#    ⚠️ 火山 / 百炼 / codex 等在 EXEMPT_PROVIDERS 里，`validate()` 对豁免 provider
#       ⛔ **不校验 model** ⇒ 它拦不住这种错配。
#    🔴 这个洞是 2026-09-10 换 T1 **当场开出来的**：旧 T1 `glm-5.3-flash` 火山有，
#       新 T1 `deepseek-v4.1-flash` **只在 cb** ⇒ `--provider volcengine-coding`（不给 model）
#       会把一个火山没有的型号派过去。⇒ 换阶梯成员时必须重扫「谁家有它」。
#    ⛔ 判据取 WALLET_PREF（该型号的真实池），⛔ 不是猜。pool 为空（如 T0 的 hy 系）⇒ 不管。
if explicit_upstream is not None and explicit_model is None:
    _pool = WALLET_PREF.get(model, [])
    if _pool and explicit_upstream not in {u for u, _ in _pool}:
        # ⭐ 先在【同档】里找这个 provider 真有的落点 —— 用户只指定了 provider，
        #    model 本来就是我们选的 ⇒ 换同档成员**正当**，⛔ 但必须报告（§7 打出来）。
        #    ⚠️ 这跟「⛔ 不擅自替换成相近模型」不冲突：那条针对用户**显式给了 model**
        #       的情况（explicit_model is not None，在 P1 就 validate 掉了）。
        _alt = next(((u, m) for u, m in TIER_PEERS.get(model, [])
                     if u == explicit_upstream), None)
        # ⭐ **2026-09-24 本分支重新可达**：cb 移出 v4.1-flash 的池（涨价），而 cb 仍是 TIER_PEERS 成员
        #    ⇒ `--provider codebuddy-code`（不给 model）在这里被换成 cb/glm-5.3-flash 并留痕。
        #    📜 09-23 ~ 09-24 它曾被标 `pragma: unreachable-by-config`（T1 四池时所有 peer 都在池里，构造不出来）。
        #       当时⛔没删代码、而是配了 consistency §3m 失效条件 —— 这次价格一变它就用上了，
        #       ⇒ 要是当时删了，cb 这条路径就会直接报错停，而不是换到同档的 glm。
        if _alt is not None:
            tier_substitutions.append((model, _alt[1], f'{explicit_upstream} 上没有 {model}'))
            model = _alt[1]
        else:
            report_provider_model_mismatch_and_stop(explicit_upstream, model, _pool, free_skipped)
            #  ⭐ 带上 free_skipped：`--provider openrouter-free` 这类**只有免费条目**的 provider，停的真实原因是
            #     「它的免费条目当前不可用」，⛔ 不只是「它没有 v4.1-flash」（审查 r2）

# ═══ 5. 选 provider ═══ ⚠️ 显式 provider 存在时⛔不许被换掉
if upstream is None:
    # 🔴🔴 本段有【两个正交的换档理由】，⛔ 千万别混：
    #   ① 质量/成本换档（第 4 段做完了）：升档唯一入口是「本任务做砸过一轮」，⛔ 不得跨档【下调】
    #   ② 可用性换档（本段）：模型【拿不到】。只许【向上】，⛔ 永远不向下 —— 向下 = 质量回退
    # 🔴 探活**之前**拦下全局禁用型号 —— 要求是「⛔ 不许真去请求它」，⛔ 不是「最先报错」。
    #    ⛔ 不能只靠本段收尾的 validate()：那在 first_available() 之后，池已经被逐个探过了
    #    （0910 异构审 #1）。⛔ 也不能放到 §1 —— 那会把 provider 停用 / review 冲突的
    #    真实原因盖掉（实测把三条既有用例判成了「型号被屏蔽」）。⇒ 位置就在这里。
    if model in BLOCKED_MODELS_ANY_PROVIDER:
        report_blocked_model_and_stop(explicit_upstream, model)
    tier = next((i for i, (m, _) in enumerate(LADDER) if m == model), None)
    while True:
        pool = (WALLET_PREF.get(model)
                or [(u, model) for u, ms in WHITELIST.items() if model in ms]   # 🔴 白名单型 provider 的型号（qfmodel / Bunny / qmodel_38max）
                or [('codebuddy-code', model)])
        #  ⚠️ 中间那项 2026-09-29 加（审查 A ❌1）：原先只有 WALLET_PREF 或 cb ⇒ `--model qfmodel` 不给 provider
        #     会落成 cb/qfmodel 并被白名单报「冲突」—— 报的原因是错的（`qmodel_38max` 早就是这个形态）
        # ⭐ 轮换时把【当前正在打折】的池排前（sorted 稳定 ⇒ 同为打折/同为原价时保持原轮换序）
        # 🔴 这里是【档位内选落点】，⛔ 不许换成别的档位。
        #    2026-08-12 那个 bug 的错误是 is_night() 把「做砸才升上去的高档模型」
        #    换成了【低档】的便宜模型，越过了档位边界往下选。
        # ⚠️ ⛔ 别跨钱包比价（火山包月 / cb credits 倍率 / 百炼积分，单位不可通约）——
        #    只比「同一型号的多个池」，那一步才可算（同型号，一边打折一边不打）。
        # 🔴 affinity 优先于折扣 —— ⚠️ 这是个**有意的取舍**：
        #    「留在已知活着的 provider」压过「省一点钱」。
        #    依据是用户 2026-09-10 的显式要求；⛔ 不要因为「折扣更便宜」把它翻回来。
        pool = sorted(pool, key=lambda x: (x[0] != provider_affinity,
                                           not is_discounted_now(x[0], x[1])))
        # 🔴 本任务里反复无响应的落点直接排除 —— ⛔ 不许原地无限重派
        pool = [x for x in pool if x not in dead_landings]
        landed = first_available(pool)
        if landed is None:
            # ⭐ 本档模型所有池都拿不到 ⇒ 先在【同档】里换落点（⛔ 优先于升档：同档能落就别涨价）
            # ⛔ 同档替代⛔不参与上面的折扣排序 —— 它没有价格依据，只是兜底。
            # ⚠️ affinity 同样作用于同档替代 —— 「留在已知活着的 provider」这个意图
            #    ⛔ 不该在换 peer 这一步丢掉（cb 上的 v4.1 拿不到，但 cb 上的 glm 可能可以）。
            peers = [x for x in TIER_PEERS.get(model, []) if x not in dead_landings]
            peers = sorted(peers, key=lambda x: x[0] != provider_affinity)
            landed = first_available(peers)
            # 🔴 落到同档替代**必须留痕** —— ⛔ 否则 §7 只打得出 availability_escalations，
            #    【档内换落点】对用户完全不可见（0910 异构审 gpt→deepseek 抓到：
            #    我在「显式 provider 错配」那条路径加了 append，**这条可用性路径漏了**）。
            #    ⚠️ 同一件事有两个入口，改一处忘一处 —— 与「rubric 改了但驱动 prompt 没改」同形。
            if landed is not None:
                tier_substitutions.append((model, landed[1], '本档所有池都拿不到'))
        if landed is not None:
            break
        # ⭐ 同档也没有 ⇒ 【可用性升档】：往上走一档（用户 2026-09-09 决定：允许向上 + 必须报告）
        # 🔴 ⛔ 只许 tier + 1。⛔ 任何 tier - 1 都是错的 —— 那是拿「拿不到」当借口做质量回退。
        if tier is None or tier >= len(LADDER) - 1:
            break                            # 到顶（或本就不在阶梯里）⇒ 交给下面的最后兜底
        prev = model
        tier += 1
        model = LADDER[tier][0]
        # ⛔ 记 (from, to, why) 三元组 —— 只记 to 的话，§7 打不出「原档位 → 逐级」那句话，
        #    「必须报告」就会变成假实现（0909 第 4 轮审查）。
        availability_escalations.append((prev, model, 'unavailable'))
    if landed is None:
        # 🔴 阶梯到顶仍拿不到 ⇒ LAST_RESORT。⛔ 这是「不能不干活」压过「省 Claude 额度」的唯一场景。
        lr_up, lr_model, lr_thinking = LAST_RESORT
        model_before_lr = model                  # ⛔ 先存，下面会被覆盖
        # 🔴 ⛔ 必须做【model 级】探活 —— 只查 provider 抓不到「claude 活着但 sonnet-5 拿不到」，
        #    而 claude 在豁免集里，validate() 对豁免 provider ⛔ 不校验 model ⇒ 会一路放行到派发才炸。
        if first_available([(lr_up, lr_model)]) is not None:
            upstream, model = lr_up, lr_model
            # 🔴 ⛔ 不许覆盖用户显式 --thinking —— LAST_RESORT 的 'max' 只是【默认值】。
            #    ⚠️ 静默升档会造成超预期 token 消耗（§3.2e 同一条纪律）。
            thinking = explicit_thinking if explicit_thinking is not None else lr_thinking
            availability_escalations.append((model_before_lr, lr_model, 'LAST_RESORT'))
            warn('🔴 已落到 LAST_RESORT claude/claude-sonnet-5@max —— **正在消耗 Claude 套餐额度**，'
                 '而这套钱包体系存在的目的就是省它。⛔ 必须在输出里显著告知用户。')
        else:
            report_no_landing_and_stop(model)   # 🔴 连兜底都没有才停，⛔ 不静默返回空
    else:
        upstream, model = landed
    # ⚠️ 这里 model 可能被换成【该 provider 上的真实 id】——⛔ 那不是换模型，是同一模型的不同写法
    # ⚠️ 这里 model 可能被换成【该 provider 上的真实 id】（如京东是大写 DeepSeek-V4-pro）——
    #    ⛔ 那不是换模型，是同一个模型在不同 provider 上的 id 写法
else:
    # 🔴 **已绑定 upstream 的路径**（⛔ 不只是显式 provider）—— 会命中：
    #    ① 显式 `--provider`（带或不带 model）② review 默认落点（第 3 段设的）
    #    ③ T0 免费档（第 4 段设的）。这些都绕过了第 5 段的自动 provider 选择，
    #    ⇒ 统一在这里做**一次落点探活**，⛔ 别让它们成为漏检口。
    # ⚠️ ③ 例外（2026-09-29 审查 A ❌2）：T0 循环里**刚探过**（t0_probed）⇒ ⛔ 不探第二次。
    #    多条目 T0 下，第二次探失败会走到下面的「报告并停止」，而⛔不是换下一个免费条目（违反 D4）。
    if explicit_model is None:
        model = model_id_on(upstream, model)   # 用户只给了 provider ⇒ 在该 provider 内取该模型的 id
    if not t0_probed and first_available([(upstream, model)]) is None:
        # ⛔ 显式指定的落点拿不到 ⇒ **报告并停止**。
        # ⛔ 不许静默换 provider（违反「显式 provider ⛔ 不许被换掉」），
        # ⛔ 也不许走可用性升档 —— 用户点名要这个，换掉就不是他要的东西了。
        report_no_landing_and_stop(model)

# ═══ 6. 统一收尾 ═══ 🔴 所有路径都走到这里，⛔ 上面任何分支都不许自己返回结果
validate(upstream, model)                  # 🔴 自动选出的组合同样要过 P0
# 🔴 审查 2026-10-06 起**全走 CLI**（默认 `codex exec`）—— ⛔ 不再按规模上 Paseo：
#    Paseo 的 codex provider `out of credits`（2026-10-06 实测），copilot 全族已死 ⇒ 没有可用的
#    Paseo 审查 provider。大审查的可见性用【后台跑 + 输出落文件】补偿（§3.2c），⛔ 不是没人盯。
channel = 'paseo' if (is_dev_task(task_type) or is_large_review(scope)) and task_type != 'review' else 'cli'
#   🔴 判据是「要不要看得见」（§3 通道判据总表）：开发实施类 + 大审查 → paseo；其余 → cli
if upstream == 'claude':
    channel = 'paseo'
    # 🔴 claude 在 provider 表里【只有 Paseo create_agent 一条路径】（mode=auto，§8）——
    #    ⛔ 没有 `claude -p` 这条 CLI 通道。短任务落 LAST_RESORT 时若按规模判成 cli，
    #    会拼出一个根本不存在的调用（0909 第 4 轮审查抓到）。
    #    ⭐ 顺带：LAST_RESORT 本来就该【看得见】—— 它在烧 Claude 额度。
# 🔴 这里【曾经】有第二套可用性机制：`if not provider_available(...): downgrade(...)`。
#    ⛔ 已删除（0909 第 4 轮审查抓到）—— 它不受「⛔ 不得跨档下调」约束，
#    能把 §5 刚升上去的档位又**降回低档**，还会绕开「显式 provider ⛔ 不许被换掉」，
#    且不写 availability_escalations ⇒ **静默质量回退**。
# ⭐ 现在可用性只有【一套】真源：§5 的 first_available + 同档替代 + 向上升档 + LAST_RESORT。
#    ⛔ 不要再在收尾里加第二套判断 —— 两套信号会互相矛盾。
# 🔴 Paseo 的 cb provider 对「它缓存的清单里没有的型号」**静默降级成默认型号 hy3**（2026-10-02 实测 ×2：真 id `space-bunny`、假 id 都是
#    snapshot.model=请求值、runtimeInfo.model=hy3，且不报错）⇒ 标题 / 账单 / 评测结论标的是 A、实际跑的是 B。
#    ⚠️ 根因在 Paseo 缓存的模型清单（本次比 cb 服务端少 1 个），⛔ 不在 cb CLI（钉死的 2.106.1 直接 `-p` 跑 space-bunny 完全正常）
#       ⇒ 只在【走 Paseo 且落在 cb】时判；CLI 通道不受影响。
#    ⭐ 这是「创建后核 runtimeInfo.model」（§3.1）的**前置版**：那条靠人记得，这条由代码拦。
_listed = paseo_lists_model(upstream, model) if (channel == 'paseo' and upstream == 'codebuddy-code') else True
#   三态：True=清单里有 / False=确实没登记 / None=拉清单本身失败（超时 / 报错），**无法确认**
if _listed is not True:                      # 🔴 fail-closed：False 与 None 都停（⛔ 不能写成 `_listed is False`，那样拉不到清单就放行了）
    report_paseo_unlisted_model_and_stop(upstream, model, unconfirmed=(_listed is None))
    #   ⚠️ unconfirmed=True ⇒ 报告必须写「无法确认 Paseo 清单」，⛔ 不要和「确实没登记」混成一句话（r7 审查）
    #   出路见 §3.1：走 CLI / 让用户刷新 Paseo，⛔ 不要硬派
provider = normalize_provider(upstream, channel)
thinking = (None if model in NO_THINKING_MODELS             # 🔴 没有思考档 ⇒ ⛔ 不传（显式 --thinking 也作废，§7 回显）
            else clamp_to_supported(model, thinking or default_thinking(model)))  # §3.2e，⛔ 只降不升
result   = execute(channel, provider, model, thinking)    # §3
agent_id = result.agent_id if channel == 'paseo' else None
# ⚠️ `pi -p` 是一次性进程，⛔ 没有 agent_id —— 用 result.run_id 留痕
save_memory(agent_id=agent_id, run_id=(None if channel == 'paseo' else result.run_id),
            provider=provider, model=model, task_type=task_type,
            thinking=thinking, cwd=cwd)              # §8
# 🔴 产出校验要求必须**算进决策结果**，⛔ 不能只在散文里写「记得校验」——
#    那正是 `glm-latest` 那次的错：规则不落到会被执行的那一层就等于没写。
#    ⇒ 它是派发结果的一个**字段**，§7 必须打出来，收割时按它做硬门控（§6 收割表）。
requires_output_validation = model in OUTPUT_VALIDATION_REQUIRED
if requires_output_validation:
    warn(f'🔴 {model} 约 17% 概率产出「看着像正常输出」的垃圾（DSML 内部标记泄漏）⇒ '
         f'⛔ 收割时**必须校验产出**（过短 / 内部标记 / 续接语 / 不足同批中位数 35%），'
         f'⛔ 不能只看 exit 0。参考 validate_cell.py')

print_summary()                                      # §7

# 🔴 时段判断【只出现在第 5 段（选 provider）】，⛔ 上面【选档位】那几段一律没有。
#    ⚠️ 被废止的⛔不是「时段判断」本身，而是 2026-08-12 那种写法——
#    `is_night()` 把做砸才升上去的高档模型换成【低档】便宜模型，越过了档位边界往下选。
#    ⇒ 不变量是【⛔ 不得跨档下调】。第 5 段的 is_discounted_now() 只在档内换池，合规。
```

---

## 3. 执行适配器

### 📌 通道判据总表（唯一真源，三文件以此为准）

🔴 **「走哪条通道」和「用哪个模型」是两件正交的事，⛔ 别写成一个原子。**
通道由**要不要看得见**决定；模型由**异构族约束**（§9 / routing §5）决定。

| 任务规模 | 走哪条通道 | 判据 |
|---|---|---|
| **开发实施类**（改代码/跑测试/提交） | ⭐ **Paseo `create_agent`** | 要看进度、要能中途叫停 |
| **大审查**（多文件 / 读大量源 / 预计 20+ 工具调用） | ⭐ **`codex exec` CLI（后台跑 + 输出落文件）** | 🔴 2026-10-06 起审查**全走 CLI**：Paseo 的 codex provider `out of credits`（实测）、copilot 全族已死 ⇒ 没有可用的 Paseo 审查 provider。可见性用后台 + 日志文件补偿 |
| **短任务**（单文件、明确问题、只读分析、短审查） | `pi -p` CLI（实施侧）/ `codex exec`（审查侧） | 跑完看结论就行，省机器不堆 serve |
| **兜底** | `opencode` 🔻 | 无常规用途，仅前面都不可用时 |

⚠️ **本表 2026-09-08 修正**：原先把「审查类」整类钉给 `pi -p`，理由写的是「审查不需要盯」。
本轮实测推翻该前提——`pi -p` + gpt-5.5 跑满 **35 分钟零输出**，全程不可见、只能盲杀（⚠️ 09-24 起**疑似其实是 stdin 挂死**，见 §3.2b，未复测）；
而同期 Paseo 派的两个审查 agent 都能看到它们各自在第 13 / 22 步撞 429。
⇒ **判据回归硬默认 #2 的「要不要看得见」，⛔ 不按任务类型一刀切。**
⚠️ **2026-10-06 再修正（审查侧）**：审查的可见性此前靠 Paseo（`pi/github-copilot/gpt-5.5`）解决；
copilot 凭据被删、Paseo codex provider 撞额度后，Paseo 侧没有可用落点 ⇒ 审查通道暂时只有 CLI，
可见性降级为「后台跑 + 输出落文件 + 完成后回读」。若将来 Paseo codex 恢复额度，再按「要不要看得见」把大审查升回 Paseo。

模型侧不变：审查⛔用同族；⭐ 默认 `codex`（CLI；模型取 `~/.codex/config.toml` 的 `model`，实测 `gpt-5.6-sol`，
`RIFT_REVIEW_MODEL` 可覆盖）。codex 撞额度 ⇒ §3.2c 降级阶梯（qfmodel → hy3 → glm-5.3-flash），显式告知用户。

### 📌 派发路径用例 —— 🔴 **这张表有可执行测试**

⛔ 别只照着人眼自查：`scripts/pipeline-test.py` 会**直接执行 §2 的伪代码**跑这些用例并断言落点。
🔴 **改了本 skill 任何一处，六项校验都要跑**（`S=scripts`）：`python3 $S/pipeline-test.py` · `python3 $S/coverage-check.py`（§2 每行都要被用例走到）·
`python3 $S/consistency-check.py`（SKILL ⇔ catalog ⇔ routing 结构性比对）· `bash $S/cooldown-test.sh` · `bash $S/probe-models-test.sh`（本地假端点，⛔ 不打真服务）·
`python3 $S/billing-test.py`。「绿」不等于「还在测目标规则」——改了测试夹具里的日期 / 阈值，要对该规则做一次注入验证（见 MEMORY feedback-prove-the-detector-detects）。
改了 §2 就跑它（连同 `scripts/consistency-check.py`）。
✅ 已验证它能抓住 5 类真实破坏：channel 写死 · 入口档改错 · 审查换模型 · 丢 `pi/` 前缀 · 新增未赋值变量。


| 输入 | 期望结果 |
|---|---|
| `--provider jdcloud-joyagent --model GLM-5.2` | ⛔ **拦住**（JD 白名单只有两个 DeepSeek） |
| `--provider pi/jdcloud-joyagent --model GLM-5.2` | ⛔ **同样拦住** —— 先 `split_provider` 取 upstream 再校验 |
| `--provider pi/jdcloud-joyagent --model DeepSeek-V4-pro` | ⛔ **拦住** —— 京东 2026-09-09 停用，已移出白名单与豁免集 ⇒ 落「未知 provider」 |
| `--provider volcengine-coding --model deepseek-v4-flash` | ✅ 放行（豁免集） |
| `--provider github-copilot --model gpt-5.5` | ⛔ **拦住**（copilot 全族 2026-10-06 进 `BLOCKED_MODELS`；凭据已删 ⇒ 全族不可用） |
| `--provider deepseek --model deepseek-v4-pro` | ⛔ **拦住**（DISABLED_PROVIDERS） |
| 默认任务，**免费池可用** | → `pi/openrouter-free` + **`stealth/space-bunny-alpha`** @ `high`（T0 priority 1，⛔ 还没进付费阶梯） |
| Space Bunny 冷却中 / 探活不过 | → `codebuddy-code` + **`hy3`** @ `max`（priority 2）；再不行 → `qoderclicn` + **`qfmodel`**（priority 3，⛔ 不传 thinking） |
| `concurrency_impl` 类，免费池可用 | → 仍落 Space Bunny，但 §7 **必须打出提醒**（用户 D3：只提醒不排除） |
| `algorithm` 类 + Space Bunny 不可用 | → hy3 / qfmodel 都 avoid ⇒ 付费 T2 `deepseek-v4-flash`；⭐ 带 `--free` 则放宽，落 hy3 |
| 多模态任务 + Space Bunny 不可用 | → hy3 / qfmodel 都接不了图（会被切到付费模型）⇒ 进付费阶梯；`--free` ⛔ 也不放宽 ⇒ 停止并报告 |
| 默认任务，免费池三条都拿不到，0 次付费档做砸 | → `pi/volcengine-coding` + `deepseek-v4.1-flash`（T1 三池轮换首位：火山 coding → agent-plan → 百炼）🔴 **必须校验产出** |
| T1 三池都拿不到 | → 同档替代 `glm-5.3-flash`（火山两套餐 / cb 三池），⛔ 不升 T2 |
| 🔴 显式 `--provider codebuddy-code`，不给 model，落到 T1 | → `codebuddy-code` + **`glm-5.3-flash`**（同档换落点，`tier_substitutions` 留痕）—— 09-24 cb 的 v4.1 涨到 0.11x，已移出其池 |
| 显式 `--provider codebuddy-code --model deepseek-v4.1-flash` | ✅ 照派（仍在白名单）—— 用户点名就尊重，价差用户自负 |
| ⭐ 显式 `--provider codebuddy-code --model space-bunny`（Paseo 清单已登记） | ✅ 放行（10-02 起在 cb 白名单）→ `codebuddy-code` + `space-bunny` @ `xhigh`。⛔ **不进任何自动池**：cb 路由没评测过、折扣 10-07 到期、折后价未知 |
| 同上，但 **Paseo 清单缺 `space-bunny`**（现状） | ⛔ **停止并报告**（`report_paseo_unlisted_model_and_stop`）—— 否则 Paseo 静默跑成 hy3。走 CLI（`codebuddy -p`）则放行 |
| cb 路径任何落点（含 T0 的 `hy3`）而 Paseo 清单缺它 | ⛔ 同样停 —— 守卫对 cb 落点一视同仁，⛔ 不只管 `space-bunny` |
| 走 Paseo 且落 cb，但**拉 Paseo 清单本身失败** | ⛔ 同样停（fail-closed），报告写「**无法确认清单**」；走 CLI 则不受影响（CLI 不查清单） |
| 默认任务，免费档已跳过，**2 次付费档**做砸（T1、T2 均失败） | → T3 `qwen3.8-max` @ `pi/bailian-token-plan`（⚠️ 只此一池） |
| T3 那**一个池拿不到** | → **可用性升档**到 T4 `kimi-k3-1`（⛔ 只许向上），并在 §7 报告。⛔ 本档已无同档替代 |
| ⛔ 显式 `--model deepseek-v4-pro` | → **停止并报告**（`report_blocked_model_and_stop`）—— 用户 2026-09-10 禁用，⛔ agent 不得自行派发 |
| 一路到 T4 仍拿不到 | → 🔴 `claude/claude-sonnet-5` @ `max`（**LAST_RESORT**，§7 必须显著告知在烧 Claude 额度） |
| 连 `claude/claude-sonnet-5` 也拿不到 | ⛔ **停止并报告**（`report_no_landing_and_stop`），⛔ 不静默降档 |
| 显式 `--thinking low` + 落到 LAST_RESORT | thinking 保持 **`low`**，⛔ 不被 LAST_RESORT 的 `max` 覆盖 |
| `algorithm` 类，免费池不可用，0 次付费档做砸 | → `pi/volcengine-coding` + `deepseek-v4-flash`（T2 起步）⚠️ 免费池可用时先落 Space Bunny（它没有 avoid） |
| 只给 `--provider volcengine-coding` 不给 model | ✅ P1 仍校验该 provider，再按默认档位补 model |
| 只给 `--model v4-pro` 不给 provider | ✅ 先按 WALLET_PREF 定 provider，再回 P0 校验 |
| 大审查（多文件 / 20+ 工具调用） | → `codex exec --skip-git-repo-check` CLI，后台跑 + 输出落文件（⛔ 不走 `pi -p`，也没有 Paseo 通道可用） |
| 短审查（单文件） | → `codex exec --skip-git-repo-check "{review_prompt}" < /dev/null`（模型取 codex config；长 prompt 不需要 pi 那套 ≤200 字符限制，§3.2c） |
| review + 显式非 codex provider（含 copilot） | → **报 review 冲突**（P0 之前拦；copilot 全族已死，显式指定也只报冲突） |
| review + 显式 `--model X` | → model 保留、provider 默认 `codex`（⛔ 不掉进普通阶梯） |
| review 时 codex 报 `out of credits` | → 降级阶梯第 ① 档 `qoderclicn/qfmodel`，**显式告知用户**；①也不行 → hy3 → glm-5.3-flash（⛔ 不落 claude / copilot 族） |

### 3.1 Paseo 创建

```
create_agent({
  title: "[Dev] {task_short_title} · {channel_abbr}-{model_abbr}",   // 🔴 见下「标题规范」
  provider: "{provider}/{model}",
  relationship: { kind: "subagent" },
  workspace: { kind: "current" },
  initialPrompt: "{dispatch_prompt}",
  notifyOnFinish: true,
  settings: build_settings(provider, model, thinking),   // 🔴 见下，⛔ 不要无条件传 modeId
  
  labels: { "rift-dispatch": "true" }
})
```

#### 🔴 标题规范：**必须**带「渠道-模型」后缀，且**必须带版本号**

```
{原标题} · {渠道}-{模型缩写}
```

| 例 | 说明 |
|---|---|
| `[Dev] 修 CRM 登录三态 · 百炼-dspF4@0731` | 百炼的 `deepseek-v4-flash-0731`。🔴 **⛔ 不能简写成 `dspF4`** —— 实测它与火山的 `deepseek-v4-flash` **不是同一个被服务的模型**（同一句输入 token 数差一个量级），共用缩写会让标题说谎 |
| `[Dev] 拆 transport 插件 · 火山C-dspF4` | 火山 **coding** 套餐的 `deepseek-v4-flash` |
| `[Dev] 同上但换池 · 火山A-dspF4` | 火山 **agent-plan** 套餐 —— ⛔ 两个套餐是独立额度池，必须能分出来 |
| `[Review] 审 diff · Cdx-gpt5.6sol` | codex CLI 的 `gpt-5.6-sol`（审查默认） |
| `[Dev] 兜底重跑 · Cld-son5` | LAST_RESORT |

🔴 **⛔ 缩写必须含版本号**：`dspF4` / `glmF5.3` / `k3.2` / `gpt5.5`。
⛔ 不许写 `dsp` / `glm` / `kimi` —— **未来上 `dspF4.1`，与 `dspF4` 差距很大**，
标题里看不出版本，回头翻 agent 列表就分不清哪个产出是哪代模型做的（用户 2026-09-10）。

⭐ **GA 快照后缀（`-0731` / `-0813`）故意不进缩写** —— 渠道前缀已经把它区分开了
（`百炼-dspF4` 就是 0731 那份，`火山C-dspF4` 是无后缀那份）。
🔴 ⚠️ **例外**：若某渠道**同时**暴露同一代的两个快照（如百炼同时有 `-0731` 和 `-0902`），
必须追加 `@快照` ⇒ `百炼-dspF4@0731`。⛔ 否则两个 agent 标题一模一样，分不出来。

🔴 **⛔ 无版本别名已进 `BLOCKED_MODELS`，由 P0 `validate()` 硬拦**（用户 2026-09-10）。
⚠️ 先前只在这里写了句「不许派」—— **那拦不住任何东西**，跟 cb 换代时我只加注释不移白名单
是同一个错。⇒ 规则必须落到**会被执行的那一层**。
`glm-latest` 派发前必须先解析成具体型号（火山 `glm-latest` / `glm-5.2` → **`glm-5.3`**）。
⚠️ 对比：`hy4-preview` **可以**派 —— `preview` 是它真实 id 的一部分，缩写 `hy4` 仍带版本。
⚠️ 两类别名都要拦，⛔ 别只想着无版本那种：
  · **无版本别名**（`glm-latest`）—— 一眼看出要解析
  · **陈旧版本别名**（cb 的 `deepseek-v4-flash` → v4.1）—— 🔴 **更危险**，带着版本号却指向另一版本，标题会说谎

📎 **完整缩写表**（渠道 10 · 模型 30）在 catalog `agentTitleConvention`。
✅ `consistency-check.py` §3f 守着四条：每个可派发落点都有缩写 · 缩写必须带数字 ·
无版本别名⛔不得有缩写 · **同渠道内⛔不许两个模型撞同一缩写**。

#### 🔴 `settings` 必须按 provider 生成，⛔ 不能无条件传 `modeId`

```python
def build_settings(full_provider, model, thinking):
    # full_provider 形如 'pi/volcengine-coding' / 'codebuddy-code'；model 是该 provider 上的真实 id
    root = full_provider.split('/')[0]

    # 🔴 没有思考档（§2 收尾按 NO_THINKING_MODELS 把 thinking 置成 None：qfmodel / kimi-k2.7-code）
    #    ⇒ ⛔ 不写 thinkingOptionId（原先只特判了火山的 kimi-k2.7-code，09-29 起统一由 thinking is None 表达）
    s = {} if thinking is None else {'thinkingOptionId': thinking}
    if root == 'pi':
        return s                              # 🔴 pi provider 的 availableModes 为空，
                                              #    传 modeId 直接报 Invalid mode
    if root == 'codebuddy-code':
        s['modeId'] = 'bypassPermissions'
    elif root == 'qoderclicn':
        s['modeId'] = 'yolo'    # 🔴 09-29 起 Paseo 改用原生 1.1.62 ACP，模式 id 变为 default/acceptEdits/auto/dontAsk/yolo
                                #    ⛔ 旧 'bypassPermissions' 报 Invalid mode；`yolo` = Bypass Permissions（dontAsk 是「拒绝」⛔ 别选）
    elif root in ('claude', 'codex'):
        s['modeId'] = 'auto'
    else:
        report_unknown_provider_and_stop()    # ⛔ 未知 root ⇒ 停，别静默返回只带 thinking 的 settings
    return s
```

⚠️ 这条踩过：派 `pi/jdcloud-joyagent/DeepSeek-V4-pro` 时带 `modeId: bypassPermissions`
直接被拒 —— `Invalid mode 'bypassPermissions' for provider 'pi'. Available modes: (none)`。
**默认开发通道正是 Paseo 派 pi**，⛔ 无条件传 modeId 会让火山/京东落点全部失败。

#### ⛔ 创建后必须核实实际生效的模型

`list_models` 里存在某个 id **不代表派发它会生效**。静默回退有**两种模式**：

```
模式 1  id 不存在        → 请求被改写，顶层 model 字段就显示回退目标（可见）
模式 2  id 存在但服务不了 → 请求照录，运行时降级 ⚠️ 顶层 model 字段【看不出来】
                            snapshot.model = 请求值 / snapshot.runtimeInfo.model = 实际值
```

**创建后立刻做这个检查**：

```
mcp__paseo__get_agent_status({ agentId })
  核 snapshot.runtimeInfo.model            ← 唯一可信的「实际在跑什么」
  核 snapshot.runtimeInfo.thinkingOptionId
  核 snapshot.effectiveThinkingOptionId
```

⛔ **不要用 `list_agents` 的 `model` 字段验** —— 模式 2 下它是请求值不是运行值。
🔴 白名单里 `kimi-k3-1` 与 `qmodel_38max` 都**没实测过 runtimeInfo**，派完务必核一次。

🔴🔴 **2026-10-02 实例（cb 的 `space-bunny`）：Paseo 对「它缓存的清单里没有的型号」静默跑 hy3，不报错。**
`create_agent codebuddy-code/space-bunny` → `snapshot.model='space-bunny'`、`runtimeInfo.model='hy3'`；换成假 id 同样落 hy3 ⇒ 通用机制。
根因是 **Paseo 缓存的清单比 cb 服务端少 1 个**（16 vs 17），⛔ 不在 cb CLI：钉死的 2.106.1 直接 `codebuddy -p --model space-bunny` 完全正常。
⇒ §2 第 6 段加了**前置守卫** `paseo_lists_model(upstream, model)`（只管「走 Paseo 且落在 cb」），没有就停。实现：
`mcp__paseo__list_models({provider:'codebuddy-code'})` 里有没有该 id。⚠️ 「没有」≠「账号不能用」——只表示 Paseo 会降级。
⚠️ **失败语义（fail-closed，§2 伪代码里就是 `_listed is not True`，pipeline-test 有用例钉着）**：`paseo_lists_model` 是三态——
`True` 清单里有 / `False` 确实没登记 / `None` 拉清单本身失败（超时 / 报错）。后两者都停，但 `None` 时报告里必须写明是**「无法确认 Paseo 清单」**，
⛔ 不要和「确实没登记」混成一句话，也⛔ 不要因为拉不到清单就放行（放行 = 赌它没被静默降级）。
出路：① 走 CLI（`codebuddy -p`，§3.2c-bis，实测正常）② 让用户刷新 Paseo（重启 daemon 刷新缓存；⚠️ 未验证）
③ `~/.paseo/config.json` 的 cb provider 有 `additionalModels` 字段，疑似可登记（⚠️ 未验证，且需重启 Paseo）。⛔ 不要硬派。

#### ⛔ 收割前先确认 `lastStatus`

```
lastStatus ∈ (idle, completed)  ← 才可以取产出
lastStatus == running           ⛔ 此时取到的是【中间态】，不是结论
```

2026-08-21 踩过：在 `running` 状态取最后一条 assistant 消息，拿到 7 字符的 `aborted`
（`status=incomplete`），据此判「模型有稳定性缺陷」并重派。复查发现 agent 随后自行重试成功，
诊断结论已撤回。⚠️ 产出**非空不等于有效**——护栏要判「长度 + 内容」，不能只判非空。

### 3.2 pi 的两种启动方式 —— ⚠️ 不是二选一

🔴 **两种都是 pi，跑的是同一套能力**（同样读 AGENTS.md、同样的 skill、同样 read/bash/edit/write）。
唯一区别是**怎么启动**，进而决定你能不能看见它。

| | **Paseo 派 pi**（`create_agent` + `provider: "pi/…"`） | **`pi -p` CLI 直跑** |
|---|---|---|
| 跑的是谁 | **pi** | **pi**（同一个） |
| 能看见 / 能干预 | ✅ Paseo Desktop 可见、可中止 | ❌ one-shot，不进 agent 列表 |
| 结构化状态 | ✅ `get_agent_status` | ❌ 只有日志文件 |
| 开销 | 每 agent 一个 serve | 无，跑完即退 |
| **用在哪** | ⭐ **开发实施类 + 大审查** | **短任务 / 短审查 / 只读分析** |

⛔ **别把开发任务丢给 `pi -p`** —— 不是 pi 不行，是 CLI 这条路**你看不见**。
✅ 正确做法是 **Paseo 派 pi**：可观测性和 pi 的能力两样都要，本来就不冲突。

#### 3.2a 开发实施类 → Paseo 派 pi

⭐ Paseo 的 `pi` provider 把 `~/.pi/agent/models.json` 里的模型全暴露，带完整 thinking 档位。
⚠️ **具体数量以 `pi --list-models` 为准，⛔ 不要在文档里写死**（会过期）：

```
create_agent({ provider: "pi/volcengine-coding/deepseek-v4.1-flash",
               settings: { thinkingOptionId: "xhigh" }, … })
```

| 用途 | provider 串 |
|---|---|
| ⭐ 默认（T1） | `pi/volcengine-coding/deepseek-v4.1-flash`（三池轮换：→ `pi/volcengine-agent-plan/…` → `pi/bailian-token-plan/…`）🔴 **必须校验产出** |
| T1 在 cb 上 | `codebuddy-code/glm-5.3-flash`（0.06x）—— 🔴 09-24 起 cb 的 v4.1 是 **0.11x**，⛔ 不再自动选它 |
| T1 同档替代（三池都撞额度时） | `pi/volcengine-coding/glm-5.3-flash` · `pi/volcengine-agent-plan/glm-5.3-flash` · `codebuddy-code/glm-5.3-flash` |
| 升档 T2（上一档做砸过一轮） | `pi/volcengine-coding/deepseek-v4-flash` |
| 升档 T3 | `pi/bailian-token-plan/qwen3.8-max` —— ⛔ **不是 `deepseek-v4-pro`**（已全局禁用，照写必撞 stop） |
| 升档 T4 | `codebuddy-code/kimi-k3-1` —— ⚠️ id 是 `kimi-k3-1`，⛔ 不是 `kimi-k3` / `kimi-k3-2` |
| Agent Plan 独有 | 🔴 **当前 0 个推荐可派**。⛔ `ark-code-latest` / `doubao-seed-evolving` / `doubao-seed-2.0-mini` 已进 `BLOCKED_MODELS`；⛔ `glm-latest` 是无版本别名不许直接派。⚠️ **`kimi-k3` 暂不推荐**：① 它缺点版本号（对比 cb 权威清单里的 `kimi-k3-1`）⇒ **疑似无版本别名**，与 `glm-latest` 同类风险；② 2026-09-10 用 `只输出:OK` 这种极小 prompt 探活**挂起 >8 分钟无响应**（⚠️ 极小 prompt 也挂 ⇒ 属另一种根因，⛔ 不是 prompt 问题）。⇒ 🔴 **待核实后再决定屏蔽还是保留**，⛔ 在此之前不作为推荐落点。⭐ 判据备忘：**同一族在别处存在更具体的 id ⇒ 较短那个就是别名**，这比「含 latest」更普适 —— §3g 守卫只认字面 `latest`，所以漏了它。 |
| ⭐ T0 免费池（09-29） | `pi/openrouter-free/stealth/space-bunny-alpha`（thinking `high`）· `codebuddy-code/hy3`（`max`）· `qoderclicn/qfmodel`（⛔ 不传 thinking，mode `yolo`） |
| 原有通道（不变） | `codebuddy-code/*` · `qoderclicn/qmodel_38max` · `claude/*` · `codex/*` |

⚠️ `pi/volcengine-*/kimi-k2.7-code` 的 `thinkingOptions` 为 `null`（官方注明不支持 reasoning summaries），
派它时**不要传** `thinkingOptionId`。

**pi 的能力已对齐 codebuddy 子会话**（2026-08-20 实测，主会话独立核验、不采信自述）：
读文件 → 改代码 → 写测试 → `bash` 跑测试 → `git commit`（中文 commit message 合规）。
读 `~/.pi/agent/AGENTS.md` + 项目 `AGENTS.md`/`CLAUDE.md` + `~/.agents/skills/` 全部 skill。

#### 3.2b 只读 / 短 / 分析类 → `pi -p` 直跑

```bash
pi -p --provider volcengine-coding --model deepseek-v4-flash "{prompt}" < /dev/null
# ⭐ T0 免费池的 CLI 形态（09-29）：
pi -p --provider openrouter-free --model stealth/space-bunny-alpha --thinking high "{prompt}" < /dev/null
#    ⚠️ id 里带 `/` ⇒ ⛔ 别写成 `--model openrouter-free/stealth/…`（pi 会按第一个 `/` 拆 provider），provider 单独给
codebuddy -p --output-format json --model hy3 --tools "" "{prompt}" < /dev/null          # 见 §3.2c-bis：必须 json
qoderclicn -p -m Qwen3.8-Flash --tools "" -o json "{prompt}" < /dev/null                 # 🔴 CLI 名 ≠ Paseo id（qfmodel）
```

🔴 **`< /dev/null` 必须带**（2026-09-24 A/B 实证）：`pi -p` 碰到**非 TTY 的 stdin** 会去读它，
继承来的管道若永不给 EOF ⇒ **永久阻塞、CPU≈0、零网络连接、零输出**。同模型同 prompt 两轮 A/B：
继承 stdin 两次都挂（>45s，CPU 0.00s），`< /dev/null` 两次都 3s 返回。
⚠️ 它**看起来像模型/通道挂了**（当天 grok-4.6 / grok-4.5 / gemini-3.8-flash / deepseek-v4-flash 全被误当成「挂了」），
判据是 **`ps -o time=` 累计 CPU 不涨 + 无 ESTABLISHED 连接** ⇒ 先查 stdin，⛔ 别先换模型。

⚠️ 配置注意（`~/.pi/agent/models.json`）：必须有 `compat.supportsDeveloperRole: false`
（火山不认 OpenAI 的 `developer` role，不加则 reasoning 模型全部 400）；
⛔ **不要加** `compat.thinkingFormat`（填 `"zai"` 会让请求全部挂起跑满超时）。

#### 3.2c 审查通道 —— ⭐ codex CLI（⛔ 仅审查，不做开发）

⭐ **2026-10-06 迁移**：原通道 `pi/github-copilot/gpt-5.5` 全族死亡（用户删除 Copilot 凭据：
`~/.pi/agent/auth.json` = `{}`、models.json / models-store.json 的 github-copilot 条目已抽走，
实测再派 → `[System Error] No API key found for github-copilot.`）。用户决定：「评审换成 codex，
限额度了就换个其他模型即可。」
⚠️ **codex 当前状态是「额度耗尽」不是「可用」**（2026-10-06 14:33 实测两次对照）：

```
$ codex exec --skip-git-repo-check '只回复两个字：OK'     # （用户当日早些时候跑过一次：rc=0、输出 OK、tokens used 23241）
$ codex exec --skip-git-repo-check "…review prompt…"      # 14:33:23 → 14:33:34
ERROR: Your workspace is out of credits. Ask your workspace owner to refill in order to continue.
ERROR: Your workspace is out of credits. Ask your workspace owner to refill in order to continue.
rc=1
```
⇒ 默认落点仍是 codex（用户要求），**撞额度就按下面的降级阶梯换异族**，⛔ 不许悄悄换。

```bash
codex exec --skip-git-repo-check "{review_prompt}" < /dev/null
# 模型取 ~/.codex/config.toml 的 model（实测 gpt-5.6-sol）；覆盖方式（优先级从高到低）：
#   ① 显式 --model（派发参数）→ ② RIFT_REVIEW_MODEL 环境变量 → ③ codex exec -m <model> → ④ config.toml
```

| 约束 | 说明 |
|---|---|
| 🔴 **`< /dev/null` 保留** | ⚠️ 与 pi 同类风险（2026-10-06 实测）：codex exec 在 stdin 非 TTY 时会读它（输出 `Reading additional input from stdin...`）；10s 不关闭的管道实测**拖住 10s**、EOF 后才发请求 ⇒ 继承永不 EOF 的管道会永久等。带上零成本 |
| ✅ **长 prompt 不需要 pi 的 ≤200 字符限制** | 用户 2026-10-06 实测长 review prompt 正常返回（tokens used 23241、rc=0）。⚠️ 该次成功发生在额度耗尽**之前**；耗尽后无法复测长 prompt 边界 ⇒ 恢复额度后建议复测一次并把耗时记回这里 |
| 🔴 **判额度耗尽看 rc + stderr** | `rc=1` + stderr 含 `out of credits`（实测原文 `ERROR: Your workspace is out of credits. Ask your workspace owner to refill in order to continue.`）⇒ 额度耗尽；同类签名 `usage limit` / `401` / `429`（大小写不敏感）。⛔ 与模型级失败分开：这是**通道级**，codex 全家不可用 |
| ⛔ **仅审查不做开发** | 沿用 2026-08-20 口径。开发走 §3.2a 火山通道 |
| 🔴 **大审查可见性补偿** | 审查全走 CLI 后没有 Paseo 进度条 ⇒ 后台跑（`run_in_background`）+ 输出落文件 + 完成后回读；⛔ 不是「扔后台不管」 |

**降级阶梯**（codex 额度耗尽 ⇒ 依次换**异族**；⛔ 硬不变量：评审族 ≠ 实施族——实施是 Qwen / Hy / GLM 族时，同族的档⛔跳过取下一档；⛔ 不许回落 claude 族（主会话）、⛔ 不许回落 copilot 族）：

| 顺位 | 落点 | 族 | 成本 | 通道命令 | 实测 |
|---|---|---|---|---|---|
| 默认 | `codex`（模型取 config.toml） | GPT | 订阅额度 | `codex exec --skip-git-repo-check "{prompt}" < /dev/null` | 🔴 2026-10-06 **out of credits**（rc=1，两次对照） |
| ① | `qoderclicn/qfmodel`（CLI 名 `-m Qwen3.8-Flash`） | Qwen | 免费（截止未公布） | `qoderclicn -p -m Qwen3.8-Flash --tools "" -o json "{prompt}" < /dev/null` | ✅ 2026-10-06 14:35 真实评审演练通过（30.3s，VERDICT 合规，`total_credits=0`） |
| ② | `codebuddy-code/hy3` | Hy(混元) | 免费（至 10-31） | `codebuddy -p --output-format json --model hy3 --tools "" "{prompt}" < /dev/null` | ✅ 2026-10-06 14:38 探活通过（~12s，PROBE_OK） |
| ③ | `codebuddy-code/glm-5.3-flash` | GLM | ⚠️ **付费 0.06x**（⛔ 不是免费） | 同上，`--model glm-5.3-flash` | ✅ 2026-10-06 14:38 探活通过（~5s，PROBE_OK） |

⭐ **降级动作必须显式**：换档时报告用户「codex 额度耗尽（附 stderr 签名）→ 已落到第 N 档 X/Y」，
落点写冷却记录（`cooldown.sh set codex <model> +1h "out of credits"`），
⛔ 不许静默换模型 —— 评审结论的来源必须可追溯。

⛔ **copilot 全族已进 `BLOCKED_MODELS`**（17 个 = 已知全部型号）且 `github-copilot` 已移出
`EXEMPT_PROVIDERS`（provider 级也拦）。理由：2026-10-06 用户删除 Copilot 凭据 ⇒ 全族不可用。
📜 历史记录（迁出前的通道形态，⛔ 不再是现行规则）：

- 旧通道命令 `pi -p --provider github-copilot --model gpt-5.5 "{≤200 字符 prompt}" < /dev/null`
  ——prompt ≤200 字符、800 字挂 22 分钟等约束是 **pi 通道的**，⛔ 别带到 codex 上。
- 旧端到端计时（2026-08-20 实测）：`github-copilot/gpt-5.5` 29.9s / 197MB / VERDICT 合规。
- 旧盲评 `blindEval_copilot5_20260909`（grok-4.5 109.5 等）—— 数据仍可查（catalog），⛔ 但通道已死。

#### 🔴 3.2c-bis codebuddy `-p` 采数据必须用 `--output-format json`

🔴 **`codebuddy -p` 的 text 模式只把【最后一条】assistant 写到 stdout。**
长输出被 cb 内部拆成多条 assistant 消息时，**前面的块全丢**。

⭐ **实测**（2026-09-10）：同一格用 json 抓 transcript 有 **2 条** assistant
（33721 + 13659 = 47380 字符），text 模式 stdout 只有后者 **13659** ⇒ **丢了 33721 字符**。
⚠️ 连带查出 `deepseek-v4-pro` 的 kafka 那格也被截过（10514 → 拼接后 **16128**）。

```bash
codebuddy -p --output-format json --model <m> --tools "" "<prompt>" > out.json
# 再把 transcript 里【所有】 role==assistant 的 text 按序拼接
```

⚠️ **差点归因错**：看到产出开头是「继续（接上一条…）」，我第一反应是
「这模型爱自行分块，是它的行为风险」—— **错了**，是 harness 丢数据。
⇒ 🔴 看到「续篇」先查 **transcript 有几条 assistant**，⛔ 别先怪模型。

✅ 走 `pi -p` 的通道（火山/百炼）**不受影响**——pi 是单条输出。⭐ 审查默认的 `codex exec` 也是单条 CLI 输出，同样不适用本条（它没有 transcript 续篇问题）。

#### 3.2d opencode（🔻 兜底，排最后）

**没有禁用**，但排在 pi 之后。卡死根因见 routing §7：
`opencode run --pure` 每次拉起一个 serve，反复调用则 **serve 堆叠**吃穿内存。
⇒ 单次偶发调用安全；⛔ **循环里反复 `opencode run` 是危险动作**，改用 `pi -p`。

### 3.2e thinking 档位能力表 + `clamp_to_supported()`

伪代码 P7 折算的依据。**本 skill 的默认档 `xhigh` 只在 gpt 系成立**，其余族压根没这一档。

| 模型 | **支持的档位**（📜 2026-10-06 前读自 `~/.pi/agent/models.json` 的 `thinkingLevelMap`；copilot 系各行自通道死亡后只是历史数据） | 实测过？ |
|---|---|---|
| 🔴 `codex` 通道（gpt-5.6-sol 等） | ⚠️ **不走 thinkingLevelMap**：codex CLI 的思考强度由 `~/.codex/config.toml` 的 `model_reasoning_effort`（实测 `medium`）控制，⛔ pi 的 clamp 表对它不适用；派发侧不传 thinkingOptionId | ✅ 10-06 实测生效 |
| `gemini-3.5-flash` | ⚠️ 无映射表（pi 按默认处理，⛔ 未验证） | ✅ |
| `gemini-3.6-flash` | ⚠️ 无映射表（pi 按默认处理，⛔ 未验证） | ⚠️ 未实测 |
| `gemini-3.7-flash` | ⚠️ 无映射表（pi 按默认处理，⛔ 未验证） | ⚠️ 未实测 |
| `gemini-3.8-flash` | ⚠️ 无映射表（pi 按默认处理，⛔ 未验证） | ⚠️ 未实测 |
| `gpt-5-mini` | `minimal` `low` `medium` `high`　⛔无 off xhigh max | ✅ |
| `gpt-5.3-codex` | `minimal` `low` `medium` `high` `xhigh`　⛔无 off max | ✅ |
| `gpt-5.4` | `minimal` `low` `medium` `high` `xhigh`　⛔无 off max | ✅ |
| `gpt-5.4-mini` | `minimal` `low` `medium` `high` `xhigh`　⛔无 off max | ⚠️ 未实测 |
| ⛔ `gpt-5.4-nano` | `minimal` `xhigh`　⛔无 off | ⛔ **unsupported**，⛔ 不作为可用审查模型 |
| `gpt-5.5` | `minimal` `low` `medium` `high` `xhigh`　⛔无 off max | ✅ |
| `gpt-5.6-luna` | `minimal` `low` `medium` `high` `xhigh` `max`　⛔无 off | ⚠️ 未实测 |
| `gpt-5.6-sol` | `minimal` `low` `medium` `high` `xhigh` `max`　⛔无 off | ⚠️ 未实测 |
| `gpt-5.6-terra` | `minimal` `low` `medium` `high` `xhigh` `max`　⛔无 off | ⚠️ 未实测 |
| `gpt-6-astra` | `low` `medium` `high` `xhigh` `max`　⛔无 off minimal | ⚠️ 未实测 |
| `grok-4.5` | `low` `medium` `high`　⛔无 off minimal xhigh max | ⚠️ 未实测 |
| `grok-4.6` | `low` `medium` `high` `xhigh`　⛔无 off minimal max | ⚠️ 未实测 |
| `kimi-k2.7-code` | ⚠️ 无映射表（pi 按默认处理，⛔ 未验证） | ⚠️ 未实测 |
| `kimi-k3` | ⚠️ 无映射表（pi 按默认处理，⛔ 未验证） | ⚠️ 未实测 |
| `mai-code-1-flash-picker` | `low` `medium` `high`　⛔无 off minimal xhigh max | ⚠️ 未实测 |
| `mai-code-1.1-flash` | `low` `medium` `high`　⛔无 off minimal xhigh max | ⚠️ 未实测 |
| `bailian-token-plan/deepseek-v4-flash-0731` | 🔴 走 pi 时**六档全空转**（见下方专条） | ✅ **已实测** |
| `pi/volcengine-*/kimi-k2.7-code` | ⚠️ `thinkingOptions` 为 `null` | ⛔ 不要传 |
| `openrouter-free/stealth/space-bunny-alpha` | ⚠️ 无映射表（pi 按默认处理，⛔ 未验证 pi 实际往请求里塞了什么）。服务端支持参数含 `reasoning` / `reasoning_effort`（OpenRouter 公开 models API） | ⚠️ 09-29 bench 是**直连 API** `reasoning.effort=high`，⛔ 不是经 pi |
| `qoderclicn/qfmodel` | ⛔ **无思考档**（`NO_THINKING_MODELS`）⇒ 一个档位字段都不传 | ✅ 09-24 bench |
| ~~claude 系~~ | ⛔ 已从 pi 的 Copilot 通道移除（§3.2c）；Paseo 派 `claude/*` 时是 `low`/`medium`/`high`/`max` | — |

🔴 **读法**：`thinkingLevelMap` 里 **value 为 `null` 就是不支持该档**，⛔ 不要只看 key。
   （我第一版按 key 列，结果把 `grok-4.5` 写成支持 `xhigh`——实际它 `xhigh: null`。）
🔴 **「配置支持」≠「实测过」**：右列标 ⚠️ 的只是没端到端跑过，⛔ 不是档位未知。

**折算规则：只降不升。** `xhigh` → 查上表：该模型 `thinkingLevelMap['xhigh']` 为 `null` 就往下降到最近的非 null 档
（例：`grok-4.5` 无 `xhigh` ⇒ 落 `high`；`gpt-5-mini` 同理）。Paseo 派 `claude/*` 时落 `max`。
⚠️ `thinkingLevelMap` 为 `null` 的（gemini 全系、kimi 两个）⛔ 无依据可查，别猜，先实测。
⛔ **禁止静默升档**（会造成超预期 token 消耗）；降档必须在 §7 输出里回显，
memory 记 `effectiveThinking` 字段留痕。

🔴 **`bailian-token-plan/deepseek-v4-flash-0731`：走 pi 时思考档位【整体空转】**（2026-09-10 实测）

它的 `thinkingLevelMap` 是空的 ⇒ pi 没有映射可用，**不往请求里塞任何思考参数**。实测结论：

| 侧 | 现象 | 证据 |
|---|---|---|
| **pi** | 8 种输入**全部接受**（不传 / `off` / `minimal` / `low` / `medium` / `high` / `xhigh` / `max`），非法值有清晰 warning | 逐个跑通 |
| **pi** | 🔴 `off` 与 `high` **表现相同** ⇒ pi ⛔ **没有**把 `off` 映射成关闭 | 同一道鸡兔同笼题，两档答案都对 **3/3** |
| **API 直连** | ⭐ **二态真生效**：`enable_thinking:false` 或 `thinking:{type:disabled}` ⇒ `reasoning_tokens` 变 `None` | 两种写法都复现 |
| **API 直连** | ⛔ `reasoning_effort` 三档**不生效** | n=4 均值 low **766** > high **426** > medium **392**，⛔ 不单调；而基线（不传）自身波动 **[315, 1151]** 就把三档差异全盖住了 |

⇒ **派发时传 `xhigh` 是安全的**（不报错），⛔ **但也没有任何额外效果** —— 传什么都一样。
⇒ 真要控这个模型的思考强度，只能**绕开 pi 直连 API**，用 `enable_thinking` / `thinking.type` 的**二态**。

⚠️ **⛔ 一般不要关它的思考**：API 侧关掉后，那道小学鸡兔同笼题直接做错（答 `6` / `24`，正确 `23`）。

⚠️ **证据强度**：pi 侧那条是**用答案对错反推**的（3/3 都对），⛔ 不是直接读到 `reasoning_tokens`
——`pi -p` 不暴露 usage。它与 API 侧「关掉就答错」两头对照才立得住，⛔ 单看 3/3 不够。

⚠️ 火山通道（`volcengine-*`）只有 `off` / `on` / `auto` 三态，⛔ 不是六档。

🔴 **旧警告「`volcengine-agent-plan` 上 `--variant` 静默失效」⛔ 不适用于 pi 通道**（2026-09-09 实测更正）：
两个 endpoint 经 pi 传 `thinking.type` 都**真生效** —— coding `disabled/enabled` = `reasoning_tokens` **0 / 155**，
agent-plan = **0 / 165**。⛔ 那条结论的主语是**客户端**不是 provider：opencode 走 `@ai-sdk/openai`
（Responses API），参数白名单把 `thinking` 丢了；pi 走 `openai-completions`，**两条路径不同**。
⇒ 走 pi 时两个套餐地位相同，都能控思考强度；只有走 opencode 才要绕开 agent-plan。

> 这条和「⛔ 创建后必须核实实际生效的模型」是同一类问题：**请求值 ≠ 运行值**。
> 那次是静默降级到别的模型，这次是档位不存在被静默忽略。

### 3.3 Hub 远程（`--hub`）

```bash
scp /tmp/prompt.txt hub:/tmp/
ssh hub "paseo run --detach \
  --provider {provider} --model {model} \
  --thinking {thinking} --mode '{permission_mode}' \
  --title '[Dev] {title}' \
  --cwd /home/mcdowell/{project_path} \
  \"\$(cat /tmp/prompt.txt)\""
```

⚠️ Hub `--cwd` 必须是 Hub 上的 Linux 家目录路径 `/home/<user>/...`，⛔ 不是 Mac 的 `/Users/<user>/...`。
⚠️ 中文 prompt 先 `scp` 成文件再 `$(cat …)`，⛔ 不要内联进 SSH 引号（转义会炸）。

---

## 4. Dispatch Prompt 模板

```
## 任务
{task_description}

## 项目上下文
- 工作目录: {cwd}（worktree 业务分支，不要改主仓）
- 分支: {branch}
- 技术栈: {tech_stack}
- 关键文件:
  - `{file}` — {说明}

## 已知证据（有就写，避免它重挖）
- {已定位的根因 / 已排除的错误方向 / 相关日志原文}

## 验收标准
- [ ] {来自任务描述的可验证条件}

## 约束
- 遵守项目 CLAUDE.md / AGENTS.md 规则
- 严格 TDD：先写失败测试 → **跑测试看到失败** → 最小实现 → 转绿
- 全量测试无回归，报告实际通过数（当前基线：{N} suites / {M} tests）
- 完成后 `git add -A && git commit`，中文 commit message
- **删除 TASK.md 和所有调试脚手架再提交**
- 遇到不确定的设计决策 → 停下来描述选项，⛔ 不自行决定
- ⛔ 不做任务范围外的修改，不放宽既有测试断言

## ⛔ 交付协议（这一条被丢过两次）
- **不许在 commit + 报告写完之前结束这一轮。**
  ⚠️ 你跑的测试是**本会话前台命令**，跑完不会有任何异步通知——
  ⛔ 不要说「等自动通知」或「现在去跑 X」然后结束回复，那等于把活丢在半路。
- 测试结果**必须用 `--json --outputFile=<path>` 取计数**，⛔ 不许用 `| tail`
  （会把 jest 汇总截掉，只剩一行 PASS 却看不到失败数；退出码可能仍是 0）
- 跑测试用 `--runInBand`（并行会因多个 mongodb-memory-server 撞端口出假红）
- 报「全绿」前至少跑两次，单次结果不算
- ⚠️ 新建的测试文件是**未跟踪文件**，`git add -A` 时别漏

## 🔴 改动返回结构时必答（消费方自查）
若本任务改了 API 返回结构 / 数据契约 / 共享类型定义：
- [ ] grep 出**所有消费方**并逐一列出（含前端页面、导出、详情页、其它卡片、其它服务）
- [ ] 说明每个消费方是否需要同步改，不需要的说明理由
- [ ] 报告里写"已查无其它消费方"或列出清单——⛔ 不许省略这一节
```

**总 prompt ≤ 2000 字。** 超过时提示拆分任务
（曾用 5700 字 prompt 耗尽子会话 budget，只拿回半成品）。

---

## 5. 派发前后自查

### 派发前（主会话侧，逐条过）

| 检查 | 为什么 |
|---|---|
| 🔴 **要派【审查类】？先问时机**：`bash ${AGENT_GATES_DIR:-$HOME/.agent-gates}/bin/agent-gates-review --due -C <目标仓>` | **exit 79 ⇒ 轮不到，⛔ 别派**；其余（0/1/127/命令不存在）**一律照派**。⛔ 命令不在 PATH 上，必须走绝对路径。⚠️ 只管 CHECK 5 交叉/门禁/复审，⛔ 不管 `[验收]`。<br>代价实证（0910）：每修一小块就派一次全量审查 ⇒ **11 个 agent + ≥7 次全量全白烧** —— 审查产物带 `REVIEW_HEAD`/`REVIEW_DIFF_SHA256` 锚点，代码一改就作废；其中一份**根本没看见后续 637+ 行改动**（含它自己要求的修复） |
| **要派免费档？先探活**（`probe-models.sh`，默认就从免费池三条探起） | 当日额度耗尽会**进排队**，长任务丢进去会卡住且 Paseo 侧未必立刻可见；撞额度脚本会自动写冷却 |
| **要派免费档？按条目过排除规则**（routing §2） | 多模态派 hy3 / qfmodel **照常计费**（Space Bunny 能免费接图）；各条目的能力短板写在 `avoidTaskTypes` |
| **落到 Space Bunny？** | 预览期隐身模型，**慢**（实测 150–400s/题）；做 `concurrency_impl` 要额外核：扣减是否乘了数量、字段风格是否一致（D3 的两处实测失误） |
| worktree 是否已建、有无 `node_modules` | 缺依赖时 `npx jest` **零输出**，agent 会把空跑当全绿 |
| 是否给了当前测试基线数字 | 没有基线，"全绿"无法证伪 |
| 是否写明已排除的错误方向 | 否则 agent 会顺着前任的错误假设做下去 |
| 改返回结构？→ 是否要求消费方自查 | 高频事故：后端改了前端没跟上 |
| 是否要求真实浏览器验证 | happy-dom 里 `getBoundingClientRect()` 恒 0×0，TDesign 浮层会被 `isHidden` guard 立刻关闭，导致"点不动"假阴性 |
| **permission_mode 传了吗** | 漏传导致整批任务卡在权限询问上不执行 |
| 🔴 **标题带「渠道-模型」后缀了吗？版本号在里面吗** | ⛔ 漏标 ⇒ 回头翻 agent 列表分不清哪个产出是哪代模型做的（`dspF4` vs 未来的 `dspF4.1` 差距很大）|

### 收割时（⛔ 不能只看 agent 的报告）

| 检查 | 为什么 |
|---|---|
| 🔴 **记录失败时必须带 `shape`** | ⛔ `FAILURE_SHAPES` 是**读**的一侧，写的一侧是**你**——
收割时把这次失败记成 `{tier, upstream, model, shape, count}`。⛔ 不带 `shape` 会走缺省 `bad_output`
（缺省有意偏向旧行为，⛔ 宁可多算一次做砸，也不要把升档入口清零）。
⚠️ 同一落点连续无响应记 `count`，达到 `NO_RESPONSE_LIMIT`(2) 后该落点被排除 |
| 🔴 **先判失败形态：有产出吗？** | ⛔ **没产出 = availability**。⚠️ **两种要分开记**：派发后静默停 / 唤不醒 → `no_response`（**会进 `dead_landings`**，同落点 2 次即排除）；派发前探活未秒回 → `probe_queued`（⛔ **不进** `dead_landings` —— 排队会自己散，本任务内永久排除一个可能已恢复的落点是过度反应）。
⛔ **不算「做砸」、⛔ 不许据此升档换模型族**。正确动作是**留在同 provider 降到下一档**
（⚠️ 09-24 起 cb 已不在 v4.1-flash 的池里 ⇒ 按现行不变量回到轮换落火山；是否改为「留 cb 用 glm」⏳ 待用户裁定，见 §2 affinity 注释）。⚠️ hy4 的典型形态就是这个：允许你用，但 Paseo 抓不到任何明确错误 |
| 🔴 **`requires_output_validation` 为真？→ 必须跑产出校验** | ⛔ 该型号有「看着像正常输出」的垃圾形态（实测 3988 字带 `<｜｜DSML｜｜>` 标记）⇒ **只看 exit 0 会收下垃圾**。判据：过短 / 内部标记 / 续接语 / **不足同批中位数 35%**。参考 `validate_cell.py` |
| **`lastStatus` 已是 idle/completed** | running 时取到的是中间态（§3.1） |
| `git log` 核对 HEAD **真的有新 commit** | 高频：agent 报"全绿"但改动全躺工作区没提交 |
| `git status` 有无未提交残留 | 同上 |
| 有无误提交的调试脚手架 | 出现过一次提交 13 个 debug spec |
| **合并后重跑全量**，⛔ 不信单分支的绿 | 单分支各自绿 ≠ 合到一起绿 |
| 异构交叉审（⛔ 不能同族审自己） | 抓到过"修复引入新回退"，同模型审不出来 |
| 派了 K3？**必须核 `git log`** | 0723 有空转前科：报进度就 idle、git 无产出 |

---

## 6. 前置检查

| 检查项 | 方法 | 失败处理 |
|---|---|---|
| Provider 可用 | `paseo list_providers` | 走降级链（routing §8） |
| 准备用 opencode？ | 先考虑 `pi -p` | opencode 已排最后（§3.2d） |
| Agent-gates | `ls {cwd}/.agent-gates/` | 警告但不阻断 |
| 🔴 **审查时机**（仅 CHECK 5） | `bash ${AGENT_GATES_DIR:-$HOME/.agent-gates}/bin/agent-gates-review --due -C {cwd}` | **exit 79 ⇒ 停止派发**并报告 `when=` 与逃生门 `--early`。<br>🔴 **其余一律 fail-open 照派** —— 已装 2.9.8 还不认 `--due`（实测 `exit 1` + `unknown arg: -C`）；把「问不出来」当成 `due=no` 会**把审查派发整体掐死**，比不拦更糟 |
| 工作目录 | `--worktree` > 当前 worktree > 主仓 | 主仓时提醒用 worktree |

---

## 7. 输出

```
⛔ **审查时机未到时⛔不创建子会话**，改为输出（`report_review_not_due_and_stop`）：

```
⛔ 本次不派审查 —— agent-gates 判定现在轮不到
  分支:     {branch}（review_mode={review_mode}）
  原因:     {reason}
  该审的时机: {when}          ← 🔴 必须带出来，⛔ 不能只说「现在不该审」
  逃生门:   确需现在审 → 加 --early
```

⭐ 为什么必须打 `when=`：只说「不该审」会让人**原地重试**或绕过门控直接派 Paseo ——
0910 那 11 个白烧的 agent 就是绕过去派的。⇒ 给出「什么时候该审」才是可执行的答复。

---

子会话已创建
  Agent:  {short_id} — {title}          # 🔴 title 必须已带 · {渠道}-{模型缩写}（§3.1 标题规范）
  Model:  {provider}/{model} · thinking: {thinking（为 None 时写「不适用（该模型无思考档）」；显式给过 --thinking 则追加「，已忽略 --thinking X」）}{requires_output_validation 时追加 " · 🔴 必须校验产出"}
{落在 T0 免费条目时追加一行 —— ⛔ 不许省略：
  ⭐ 免费档 priority {n}：{model}（{freeUntil 为 None ⇒ 「截止未公布，随时可能结束 / 下线」；否则「免费至 {freeUntil}」}）
     跳过的免费条目：{free_skipped 逐条「model（原因）」；为空就不写}}
{落点的 catalog `retainsData` 为 True 或未知（None）时，追加一行 —— ⛔ 不许省略（尤其显式点名匿名模型时）：
  ⚠️ 数据外发：该模型服务方可能留存 prompt。在公司目录（~/wb）下显式点名它之前，先确认这是你要的。}
{上一条成立【且】落点 upstream 是 `codebuddy-code` 时，再追加一行（⛔ 不是所有 cb 落点都加：hy3 的 retainsData 为 False，不触发）：
  ⚠️ 走 cb 时每次请求还会附带全局规则 + memory（实测约 5.5 万字符 ≈ 2.35 万 token，见 catalog spaceBunnyCb_20261002）。}
{free_cautions 非空时，整块加在这里 —— ⛔ 不许省略：
  ⚠️ {model} 做 {task_type} 有已知弱点（见 FREE_POOL 该条目注释）—— 只提醒不排除（用户 D3）。
     收割时重点核：扣减是否乘了数量、字段命名风格是否前后一致。}
{t0_now_billed 非空时，整块加在这里 —— ⛔ 不许省略：
  🔴 免费档 {列出型号与倍率} **已开始计费** ⇒ T0 对它关闭，本次走 T1。
     ⚠️ 若它的倍率**低于 cb 上 T1 落点的倍率**（当前 glm-5.3-flash，见 catalog 最新一期 cbCreditRates），那是【定档】问题 —— 需要同口径盲评，
        ⛔ 不因为「它以前是免费档」就继续当 T0 用。}
{t0_free_unverified 非空时，整块加在这里 —— ⛔ 不许省略：
  ⚠️ 免费档 {列出型号} **窗口已过但仍探活通过** —— 费率未核实。
     若它仍是 0，本次派发本可省下这一次 T1 的费用。
     ⇒ 请按 catalog `freePool` 该条目的 `verifyVia` 核（cb 读 `rawUsage.credit`；OpenRouter 读 `usage.cost` / 公开 models API；都是 agent 自己就能查的），
       把 `{'credit': x, 'verifiedOn': 'YYYY-MM-DD'}` 写进该条目的 `creditRecord`。
     ⚠️ 核实记录**超过 7 天即失效**，且⛔**窗口内核的不算**（只证明促销价是 0）。}{降档时追加 " → {effective_thinking}（该模型无 {thinking} 档）"}
{tier_substitutions 非空时，整块加在这里 —— ⛔ 不许省略：
  ⚠️ 档内换落点: {原model} → {换成} （原因：{原因}）
     ⛔ 这**不是升降档**，价格同档；只是本档主落点在该 provider 上不存在或拿不到。}
{availability_escalations 非空时，整块加在这里 —— ⛔ 不许省略：
  🔴 可用性升档: {原档位模型} → {逐级列出} （原因：所有 provider 都拿不到，⛔ 不是任务做砸）
     ⚠️ 这比原计划贵。若你更想等额度恢复，现在中止：paseo agent archive {short_id}
  ⭐ 落到 claude-sonnet-5(LAST_RESORT) 时【额外】显著提示：
  🔴🔴 已在消耗 **Claude 套餐额度** —— 这套钱包体系存在的目的就是省它。
       仅因「阶梯到顶仍拿不到，不能不干活」才走到这一步。}
  任务类型: {task_type}（{推荐理由}）
  CWD:    {cwd}
  Gates:  agent-gates ✓ / ⚠ 未安装

管理:
  进度: paseo agent logs {short_id}
  反馈: paseo send {short_id} "消息"
  中止: paseo agent archive {short_id}
```

---

## 8. Memory 记录

完成后立即写 memory（防上下文压缩丢失子会话 ID）。最小字段：

```json
{
  "agentId": "{short_id}",
  "model": "{provider}/{model}",
  "taskType": "{task_type}",
  "thinking": "{thinking}",
  "effectiveThinking": "{effective_thinking}",
  "cwd": "{cwd}",
  "status": "dispatched",
  "dispatchedAt": "{ISO timestamp}",
  "title": "{task_short_title}"
}
```

---

## 9. 审查集成

子会话完成后，按 `agent-review-protocol` 做交叉审查：

- 代码 / 文档变更 → **未显式指定时**默认 `codex`（⭐ 2026-10-06 起；模型取 `~/.codex/config.toml` 的 `model`，
  `RIFT_REVIEW_MODEL` 可覆盖；⛔ 换族，见 routing §5；显式换 provider 会报 review 冲突），
  **通道**统一 CLI：`codex exec --skip-git-repo-check "{review_prompt}" < /dev/null`（§3 通道判据总表）；
  codex 撞额度 ⇒ §3.2c 降级阶梯（qfmodel → hy3 → glm-5.3-flash），显式记录并告知用户
- 审查发现按 ❌/⚠️/💡 分级，❌ 必须修复

⛔ 真正的约束是 **评审族 ≠ 实施族**（routing §5）。实施是 DeepSeek 时评审才排除 DeepSeek 族；
实施是 Hy4/K3/GLM 时，DeepSeek 反而是合格的异构评审。

**Skill 完成定义**：子会话创建成功 + 输出已打印 + memory 已记录。
子会话的完成跟踪和审查是后续独立步骤，不阻塞本 skill 返回。
