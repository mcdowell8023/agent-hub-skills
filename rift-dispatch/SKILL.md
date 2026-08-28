---
name: rift-dispatch
description: "Rift Dispatch: analyze task → recommend model → create Paseo sub-session or pi -p call. Triggers: 'rift-dispatch', 'rift dispatch', 'dispatch', '派任务', '派个子会话', '选模型', '用 codebuddy', '用 v4-pro', '用 GLM', 'model dispatch', '调度', 'dev sub-session'."
user-invocable: true
argument-hint: "[--model <name>] [--thinking <level>] [--hub] [--worktree <path>] [--free] <task description>"
---

# Rift Dispatch — 智能任务派发

> 🔗 **rift 家族**：**`/rift-dispatch`（派发）** · `/rift-free`（免费通道）· `/rift-integration-qa`（测试验收）

分析任务 → 选模型 → 选 provider → 创建子会话（Paseo）或执行 `pi -p`。

**用户请求:** $ARGUMENTS

> **本文件 = 怎么做**（伪代码 · 命令 · prompt 模板 · 自查表）。
> **选什么 + 为什么** 在 `model-routing.md`；**数值**在 `model-catalog.json`；**历史**在 `CHANGELOG.md`。
> 同一条规则只在一处展开，本文件出现的规则以 routing 为准。

## ⛔ 开工前三条硬默认

| # | 规则 | 落点 |
|---|---|---|
| 1 | **便宜优先，逐级升档** | 免费档（`hy4-preview` → `hy3`，0.00x）先试 → 付费从 **`glm-5.3-flash`（0.06x）** 起步 → `deepseek-v4-flash`（0.17x）→ `deepseek-v4-pro`（0.51x）→ `kimi-k3-2`（1.62x）。⛔ **每一级向上的唯一入口是「上一档已在本任务做砸过一轮」**，理由里要写明哪一轮、砸在哪。写不出来不许升。⚠️ 例外：`algorithm`/`perf`/并发实现 直接从 `deepseek-v4-flash` 起步（routing §6） |
| 2 | 🔴 **按「要不要看得见」分通道，不是按工具分** | **开发实施类 → Paseo `create_agent`**——能看进度、中途干预、拿结构化状态。**只读/短/审查类 → `pi -p` CLI**——跑完即退不堆 serve。⛔ **开发任务不要走 `pi -p`**：它不进 Paseo agent 列表，你看不见也打不断 |
| 3 | 🔴 **审查的硬约束是「异构」** | ⛔ **评审模型族 ≠ 实施模型族**（全局红线 #8），是**不变量**，不是针对某个模型的禁令。🔴 **含主会话：主会话就是 Claude，我自己写的东西不得派 `claude/*` 去审**。族对照表见 routing §5。⭐ 通道：**`pi -p --provider github-copilot --model gpt-5.5`**，⛔ **prompt ≤200 字符** |

⚠️ **派发认 model id，⛔ 不认 label**：`hy4-preview`(0.00x) 与 `hy4-preview-x`(**0.29x**) 的 label 完全相同。

⚠️ **免费档时间线**：`08-31 hy3 止` → `09-12 hy4 止` → 免费档清零，默认落点变成 `glm-5.3-flash`。

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
| `--thinking <level>` | minimal / low / medium / high / xhigh / max | 按模型定：`hy4-preview`/`hy3`→`high`，付费档→`xhigh`（routing §4）。**三条通道都必须传** |
| `--hub` | 标记 | 否（本地） |
| `--worktree <path>` | 路径 | 当前目录 |
| `--provider <name>` | 强制指定 provider | 按 model 自动选 |
| `--free` | 强制走免费通道（rift-free） | 否 |
| 其余文本 | 任务描述 | (必填) |

参数缺失处理：

- 任务描述缺失 → 要求用户补充，⛔ 不猜
- `--thinking` 非法值 → 回退到该模型默认档（`hy4-preview`/`hy3`→`high`，其余→`xhigh`）
- `--thinking` 合法但**目标模型没有该档** → 按 §3.2e 能力表**降到最近可用档**，⛔ 不得静默升档，且必须在输出里回显实际生效档位
- `--provider` 与 `--model` 不匹配 → 报告冲突，让用户选
- `--worktree` 路径不存在 → 报错

---

## 2. 决策流程（伪代码）

```python
parse_args(user_input)

# ── P0 白名单：一切选择先过这一关（routing §1）────────────────────────
WHITELIST = {
  'codebuddy-code': ['hy4-preview', 'hy3', 'glm-5.3-flash',
                     'deepseek-v4-flash', 'deepseek-v4-pro', 'kimi-k3-2'],
  'qoderclicn':     ['qmodel_38max'],
}
# ⚠️ 只约束【消耗 cb/qcn 额度】的两个 provider。以下走别的钱包，⛔ 不进白名单校验：
#     pi/volcengine-*/*  · pi -p --provider github-copilot  · claude/*  · codex/*
# ⛔ 认 id 不认 label：hy4-preview(0.00x) 与 hy4-preview-x(0.29x) 的 label 一模一样
DISABLED_PROVIDERS = ['deepseek']        # 🔴 官方 API，2026-08-20 用户已 disable
EXEMPT_PROVIDERS   = [                   # 走别的钱包，不校验模型（清单必须与 routing §8 provider 表一致）
  'pi', 'claude', 'codex', 'opencode',                          # Paseo/CLI 宿主
  'github-copilot',                                             # 审查通道
  'volcengine-coding', 'volcengine-agent-plan', 'volcengine-chat',   # 火山三套餐
]

# ── P1 用户显式指定 ────────────────────────────────────────────────
if args.model:
    model = resolve_short_name(args.model)
    # 🔴 三层依次判，⛔ 不能只写「provider 在白名单里才校验」——
    #    那样传一个不在 WHITELIST 键里的 provider（如 deepseek）会让整个校验静默跳过
    if provider in DISABLED_PROVIDERS:
        report_disabled_and_stop()          # ⛔ 已停用，不给降级建议之外的出路
    elif provider in WHITELIST:
        if model not in WHITELIST[provider]:
            report_conflict_and_stop()      # ⛔ 不擅自替换成相近模型
    elif provider not in EXEMPT_PROVIDERS:
        report_unknown_provider_and_stop()  # ⛔ 未知 provider 一律停，不放行
    use(model); goto EXECUTE

# ── P2 --free → 交给 rift-free skill ───────────────────────────────
if args.free: delegate('rift-free'); return

# ── P3 任务分类（routing §6）───────────────────────────────────────
task_type = classify(user_input)
# 多标签取主标签：实现动词 > 领域关键词 > 修饰词

# ── P4 硬例外（不进常规阶梯）───────────────────────────────────────
if task_type == 'review':
    # ⛔ 唯一约束是「评审族 ≠ 实施族」，不是钦定某模型（routing §5）
    #    主会话自己写的 ⇒ ⛔ 不得用 claude/* 或 github-copilot/claude-*
    channel = 'pi -p --provider github-copilot --model gpt-5.5'   # ⛔ prompt ≤200 字符
    goto EXECUTE
# ⚠️ claude/* 可派发但不推荐——消耗 Claude 订阅额度，建议留给主会话

# ── P5 选档位：T0 免费 → T1..T4 阶梯（routing §0）──────────────────
LADDER = [('glm-5.3-flash',    0.06),   # T1 付费起点
          ('deepseek-v4-flash', 0.17),  # T2 DeepSeek 族首选
          ('deepseek-v4-pro',   0.51),  # T3 ⛔ selectableByDefault=false
          ('kimi-k3-2',         1.62)]  # T4 🔴 红线

# T0 免费档：命中排除清单（routing §2 唯一真源）才跳过
if not excluded_from_free(task_type, args):
    for m in ('hy4-preview', 'hy3'):        # 顺位固定
        if promo_active(m) and probe_ok(m): # ⚠️ 长任务必须先探活，怕撞排队
            return (m, 'codebuddy-code', 'high')
# ⚠️ 排除清单是给 Hy3 定的，对 Hy4 未验证——Hy4 的 LRU 拿 35 分（hy3 仅 23），
#    「algorithm 是短板」这条对它很可能不成立。补测前按保守处理

# T1..T4：入口档由任务类型定（catalog dispatchDefaults.entryTier），⛔ 只能因「本任务做砸过」上移
# ⚠️ 「跳过免费档」和「付费从哪档起步」是两件事，别混（routing §6）：
#     algorithm / perf          → 跳 T0，付费 T2 起步（h2h 这两类 v4-flash 领先）
#     architecture              → 跳 T0，付费 **T1** 起步（🔴 08-28 改：h2h Kafka glm 36 > v4-flash 31）
#     concurrency 诊断          → 不跳 T0（hy3 盲评 36.5 白名单内最高）
#     concurrency 写实现        → 不跳 T0，付费 T2 起步
# ⚠️ concurrency 要先判子类：诊断 or 写实现（routing §6 同名两行）
if task_type == 'concurrency':
    task_type = 'concurrency_impl' if writes_concurrency_primitives(user_input) else 'concurrency_diag'

ENTRY = {'algorithm': 1, 'perf': 1,          # 付费从 T2 (deepseek-v4-flash) 起
         'concurrency_impl': 1, 'concurrency_diag': 1}
#   ⛔ concurrency 两个子类【付费起步档都是 T2】——差别只在跳不跳 T0：
#      诊断类不跳 T0（hy3 在这类上有数据），实现类也不跳 T0，但两者进付费后都从 T2 起
#   其余（含 architecture）= 0，从 T1 (glm-5.3-flash) 起

i = ENTRY.get(task_type, 0) + failed_paid_tiers_in_this_task
#   ⛔ failed_paid_tiers 只数【LADDER 内】做砸过的档数：
#      · T0 免费档做砸 ⛔ 不计入 —— 否则默认类会直接跳到 T2，绕过 T1 的 glm-5.3-flash
#      · 同一档重试 ⛔ 不计入 —— 否则同档重试两次会把任务一路顶到 K3

# 🔴 K3 守卫：⛔ 不要用 failed_rounds 的绝对值当条件——入口档不同，到 T4 需要的失败数也不同
#    （algorithm 从 i=1 起步，砸两轮就该到 T4；写成 failed>=3 会把它按回刚砸掉的 v4-pro，原地卡死）
#    正确判据是：i 能走到 3，本身就意味着 LADDER[2] (v4-pro) 已经砸过 —— 无需额外守卫。
if i > 3:
    # ⛔ T4 也做砸了 —— 阶梯到顶，⛔ 不要静默重派 K3（那是把 1.62x 再烧一遍）
    report_ladder_exhausted_and_stop()   # 报告用户：已到 K3 仍未解决，需要人介入
if i == 3:
    assert failed(LADDER[2][0])          # 兜底断言：能到 T4，v4-pro 必已砸过（routing §3.3）
    warn('🔴 K3 1.62x，派完必须核 git log 是否真有 commit（0723 空转前科）')
model, provider, thinking = LADDER[i][0], 'codebuddy-code', 'xhigh'
# ⛔ 这里没有 `or args.model == 'k3'` 分支 —— 用户显式指定在 P1 就 goto EXECUTE 了，走不到这。

# ⛔ 没有时段分支。credits 制通道已无任何时段性折扣，⛔ 不要再写 is_night()——
#    它曾把按类型选出的高档模型无条件冲掉（2026-08-12 异构审）。
#    仍然成立：任何「换更便宜 provider」只作用于当前落点，⛔ 不下调已升上去的档位。

# ── P6 Provider 降级（routing §8）─────────────────────────────────
if not provider_available(provider): model, provider = downgrade(model)

# ── P7 折算 thinking 实际档位（§3.2e 能力表）────────────────────────
# Paseo/Hub 通道用 thinkingOptionId，档位由 provider 侧解释，直接传；
# opencode 通道用 --variant，档位是 per-model 的，必须先折算。
thinking = clamp_to_supported(model, thinking)   # ⛔ 只降不升，降了必须回显

# ── EXECUTE 执行适配器（§通道判据总表 + §3）───────────────────────
# 🔴 先定「要不要看得见」，再定跑在哪
...

# ── 输出 + 记录 ───────────────────────────────────────────────────
print_summary()                                  # §5
save_memory(agent_id, model, task_type, cwd)     # §6
# ⚠️ 只有 Paseo/Hub 派发才有 agent_id；CLI（pi -p）是一次性进程，没有 agent_id
```

---

## 3. 执行适配器

### 📌 通道判据总表（唯一真源，三文件以此为准）

| 任务类型 | 走哪条 |
|---|---|
| **开发实施类**（改代码/跑测试/提交） | ⭐ **Paseo `create_agent`** — `provider: "pi/volcengine-coding/deepseek-v4-flash"` 或 `codebuddy-code/*`。可见 / 可干预 |
| **只读 / 短 / 分析类** | `pi -p --provider volcengine-coding --model deepseek-v4-flash` |
| **审查类** | `pi -p --provider github-copilot --model gpt-5.5` ⛔ Copilot 仅审查不做开发 |
| **兜底** | `opencode` 🔻 **无常规用途**，仅在上面三条都不可用时 |

### 3.1 Paseo 创建

```
create_agent({
  title: "[Dev] {task_short_title}",
  provider: "{provider}/{model}",
  relationship: { kind: "subagent" },
  workspace: { kind: "current" },
  initialPrompt: "{dispatch_prompt}",
  notifyOnFinish: true,
  settings: {
    modeId: "{permission_mode}",         // routing §8
    thinkingOptionId: "{thinking}"
  },
  labels: { "rift-dispatch": "true" }
})
```

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
🔴 白名单里 `kimi-k3-2` 与 `qmodel_38max` 都**没实测过 runtimeInfo**，派完务必核一次。

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
| **用在哪** | ⭐ **开发实施类** | **只读 / 短 / 审查类** |

⛔ **别把开发任务丢给 `pi -p`** —— 不是 pi 不行，是 CLI 这条路**你看不见**。
✅ 正确做法是 **Paseo 派 pi**：可观测性和 pi 的能力两样都要，本来就不冲突。

#### 3.2a 开发实施类 → Paseo 派 pi

⭐ Paseo 的 `pi` provider 已把 **27 个模型**全暴露（火山 19 + Copilot 8），带完整 thinking 档位：

```
create_agent({ provider: "pi/volcengine-coding/deepseek-v4-flash",
               settings: { thinkingOptionId: "xhigh" }, … })
```

| 用途 | provider 串 |
|---|---|
| ⭐ 默认 | `pi/volcengine-coding/deepseek-v4-flash` |
| 升档（上一档做砸过一轮） | `pi/volcengine-coding/deepseek-v4-pro` |
| Agent Plan 独有 5 个 | `pi/volcengine-agent-plan/{ark-code-latest,kimi-k3,doubao-seed-evolving,glm-latest,doubao-seed-2.0-mini}` |
| 原有通道（不变） | `codebuddy-code/*` · `qoderclicn/qmodel_38max` · `claude/*` · `codex/*` |

⚠️ `pi/volcengine-*/kimi-k2.7-code` 的 `thinkingOptions` 为 `null`（官方注明不支持 reasoning summaries），
派它时**不要传** `thinkingOptionId`。

**pi 的能力已对齐 codebuddy 子会话**（2026-08-20 实测，主会话独立核验、不采信自述）：
读文件 → 改代码 → 写测试 → `bash` 跑测试 → `git commit`（中文 commit message 合规）。
读 `~/.pi/agent/AGENTS.md` + 项目 `AGENTS.md`/`CLAUDE.md` + `~/.agents/skills/` 全部 skill。

#### 3.2b 只读 / 短 / 分析类 → `pi -p` 直跑

```bash
pi -p --provider volcengine-coding --model deepseek-v4-flash "{prompt}"
```

⚠️ 配置注意（`~/.pi/agent/models.json`）：必须有 `compat.supportsDeveloperRole: false`
（火山不认 OpenAI 的 `developer` role，不加则 reasoning 模型全部 400）；
⛔ **不要加** `compat.thinkingFormat`（填 `"zai"` 会让请求全部挂起跑满超时）。

#### 3.2c 审查通道 —— ⭐ pi + Copilot（⛔ 仅审查，不做开发）

```bash
pi -p --provider github-copilot --model gpt-5.5 "{≤200 字符的 review_prompt}"
```

| 约束 | 说明 |
|---|---|
| 🔴 **prompt ≤200 字符** | 背景让它自己读文件。实测 800 字让 GPT-5.5 挂 22 分钟，短 prompt 秒回 |
| ⛔ **撞超时不要收窄 prompt 重试** | 极小 prompt 也超时属另一种根因，换通道 |
| ⛔ **仅审查不做开发** | 用户 2026-08-20 明确。开发走 §3.2a 火山通道 |
| 🔴 **`claude-*` 属 Claude 族** | 主会话就是 Claude ⇒ 审我写的东西⛔不能用它 |

可用异族评审（以 `~/.pi/agent/models-store.json` 为准）：
`gpt-5.5`(⭐默认) · `gpt-5.6-sol` · `gpt-5.6-luna` · `gpt-5.6-terra` · `gpt-5.4` · `gpt-5.3-codex`
· `gpt-5.4-mini` · `gpt-5-mini` · `gemini-3.1-pro-preview` · `gemini-3.5-flash` · `gemini-3.6-flash`
⛔ 不用 `codex/gpt-5.6-sol`——实测该 workspace `out of credits`。

✅ **端到端计时**（2026-08-20 实测，含 bug 的 JS 文件 + 要求 `VERDICT:` 行）：

| 通道 | 耗时 | 峰值 RSS | 结果 |
|---|---|---|---|
| `github-copilot/gpt-5.5` | **29.9s** | 197MB | exit 0，VERDICT 合规 |
| `volcengine-coding/deepseek-v4-flash` | 12.7s | 216MB | exit 0，3/3 抓全 |
| `volcengine-coding/deepseek-v4-pro` | 17.7s | 199MB | exit 0，2/3 |

⇒ **跑完零残留进程** —— `pi` 是 one-shot，无 serve / daemon / port 子命令。
这正是它比 opencode 省机器的原因：opencode 每个 Paseo agent 起一个独立 serve
（实测 1–1.5GB，agent idle 后不回收），pi 处理完即退出。

#### 3.2d opencode（🔻 兜底，排最后）

**没有禁用**，但排在 pi 之后。卡死根因见 routing §7：
`opencode run --pure` 每次拉起一个 serve，反复调用则 **serve 堆叠**吃穿内存。
⇒ 单次偶发调用安全；⛔ **循环里反复 `opencode run` 是危险动作**，改用 `pi -p`。

### 3.2e thinking 档位能力表 + `clamp_to_supported()`

伪代码 P7 折算的依据。**本 skill 的默认档 `xhigh` 只在 gpt 系成立**，其余族压根没这一档。

| 模型 | 支持档位 |
|---|---|
| `gpt-5.5` · `gpt-5.4` · `gpt-5.4-mini` | `none` `low` `medium` `high` `xhigh` |
| `gpt-5.3-codex` | `low` `medium` `high` `xhigh` |
| `claude-sonnet-4.6` 等 claude 系 | `low` `medium` `high` `max` |
| `gemini-3.5-flash` | `minimal` `low` `medium` `high` |
| `gemini-3.1-pro-preview` · `gpt-5-mini` | `low` `medium` `high` |
| `pi/volcengine-*/kimi-k2.7-code` | ⚠️ `thinkingOptions` 为 `null`，⛔ 不要传 |

**折算规则：只降不升。** `xhigh` → claude 系落 `max`、gemini 系落 `high`。
⛔ **禁止静默升档**（会造成超预期 token 消耗）；降档必须在 §7 输出里回显，
memory 记 `effectiveThinking` 字段留痕。

⚠️ 火山通道（`volcengine-*`）只有 `off` / `on` / `auto` 三态，⛔ 不是六档；
且 `volcengine-agent-plan` 上 `--variant` **静默失效**（实测：`@ai-sdk/openai` 的参数白名单
把 `thinking` 丢掉了），要控思考强度得走 `volcengine-coding` 或 `volcengine-chat`。

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

⚠️ Hub `--cwd` 必须是 `/home/mcdowell/...`（不是 `/Users/mcdowell/...`）。
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
| **要派免费档？先探活**（发一条极短 prompt 看是否秒回） | 当日额度耗尽会**进排队**，长任务丢进去会卡住且 Paseo 侧未必立刻可见 |
| **要派免费档？先过排除清单**（routing §2） | 多模态任务派 Hy 系**照常计费**；algorithm/perf/architecture 有盲评数据支撑 |
| worktree 是否已建、有无 `node_modules` | 缺依赖时 `npx jest` **零输出**，agent 会把空跑当全绿 |
| 是否给了当前测试基线数字 | 没有基线，"全绿"无法证伪 |
| 是否写明已排除的错误方向 | 否则 agent 会顺着前任的错误假设做下去 |
| 改返回结构？→ 是否要求消费方自查 | 高频事故：后端改了前端没跟上 |
| 是否要求真实浏览器验证 | happy-dom 里 `getBoundingClientRect()` 恒 0×0，TDesign 浮层会被 `isHidden` guard 立刻关闭，导致"点不动"假阴性 |
| **permission_mode 传了吗** | 漏传导致整批任务卡在权限询问上不执行 |

### 收割时（⛔ 不能只看 agent 的报告）

| 检查 | 为什么 |
|---|---|
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
| 工作目录 | `--worktree` > 当前 worktree > 主仓 | 主仓时提醒用 worktree |

---

## 7. 输出

```
子会话已创建
  Agent:  {short_id} — {title}
  Model:  {provider}/{model} · thinking: {thinking}{降档时追加 " → {effective_thinking}（该模型无 {thinking} 档）"}
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

- 代码变更 → `pi -p --provider github-copilot --model gpt-5.5`（§3.2c）
- 文档变更 → 同样换族审查
- 审查发现按 ❌/⚠️/💡 分级，❌ 必须修复

⛔ 真正的约束是 **评审族 ≠ 实施族**（routing §5）。实施是 DeepSeek 时评审才排除 DeepSeek 族；
实施是 Hy4/K3/GLM 时，DeepSeek 反而是合格的异构评审。

**Skill 完成定义**：子会话创建成功 + 输出已打印 + memory 已记录。
子会话的完成跟踪和审查是后续独立步骤，不阻塞本 skill 返回。
