---
name: rift-dispatch
description: "Rift Dispatch: analyze task → recommend model → create Paseo sub-session or opencode --pure call. Triggers: 'rift-dispatch', 'rift dispatch', 'dispatch', '派任务', '派个子会话', '选模型', '用 codebuddy', '用 v4-pro', '用 GLM', 'model dispatch', '调度', 'dev sub-session'."
user-invocable: true
argument-hint: "[--model <name>] [--thinking <level>] [--hub] [--worktree <path>] [--free] <task description>"
---

# Rift Dispatch — 智能任务派发

> 🔗 **rift 家族**：**`/rift-dispatch`（派发）** · `/rift-free`（免费通道）· `/rift-integration-qa`（测试验收）

分析任务 → 选模型 → 选 provider → 创建子会话（Paseo）或执行 opencode --pure。

**用户请求:** $ARGUMENTS

## ⛔ 开工前三条硬默认（看完这段再往下读）

| # | 规则 | 落点 |
|---|---|---|
| 1 | **DeepSeek 优先，族内认准 `deepseek-v4-flash`** | 默认 `deepseek-v4-flash`（0.05x）——**大部分场景够用**。🔴 `deepseek-v4-pro` 的 `selectableByDefault = false`：⛔ 唯一入口是「flash 已在**本任务**做砸过一轮」，**且派发理由里要写明哪一轮、砸在哪**；写不出来就不许升。它贵 **2.6 倍**，性价比只有 flash 的 42%。⚠️ 别拿 `sameRoundEval` 的「v4-pro 96 > flash 89」当理由——那组数据说的是**升档时该升谁**，不是该跳过 flash |
| 2 | 🔴 **按「要不要看得见」分通道，不是按工具分** | **开发实施类 → Paseo `create_agent`**（provider `pi/…` 或 `codebuddy-code/…`）——你能在 Paseo Desktop 看进度、中途干预、拿结构化状态。**只读/短/审查类 → `pi -p` CLI**——省机器、不堆 serve。⛔ **开发任务不要走 `pi -p`**：它是 CLI one-shot，**不进 Paseo agent 列表**，你看不见也打不断 |
| 3 | 🔴 **审查的硬约束是「异构」** | ⛔ **评审模型族 ≠ 实施模型族**（全局红线 #8）——是**不变量**，不是针对某个模型的禁令。🔴 **含主会话：主会话就是 Claude，我自己写的东西不得派 `claude/*` 去审**。实施 Hy3/K3 时 DeepSeek 可以审；实施 DeepSeek 时 GLM/MiniMax/Claude 可以审。族清单与对照表见 model-routing.md。⭐ 当前审查通道：**`pi -p --provider github-copilot --model gpt-5.5`**。⛔ **prompt ≤200 字符**，背景让它自己读文件（实测 800 字会挂 22 分钟）；⛔ Copilot 仅审查、不做开发|

Hy3（0.00x，限免至 2026-08-31）仍在 flash 之前，限免结束后 flash 自动接管第一顺位。
> ℹ️ opencode 的**全局默认模型**已于 2026-08-20 设为 `volcengine-coding/deepseek-v4-flash`，
> 与上表三条规则完全一致 ⇒ **不带 `-m` 直接跑 opencode 也自动符合策略**，无需每次显式指定。

完整规则见 model-routing.md 约束 4 / 6 / 7。

## Prerequisites

1. Read **model-routing.md**（同目录，模型选择 + provider 路由 + 降级链）。
2. Read **model-catalog.json**（同目录，模型结构化数据：费率/限免/盲评分数/provider 映射）。
3. Read the **paseo** skill（Paseo 创建子会话的具体 API）。
4. Read `~/.paseo/orchestration-preferences.json`（除非用户显式指定了 provider）。

---

## 1. 解析参数

| 参数 | 解析方式 | 默认 |
|---|---|---|
| `--model <name>` | 短名或完整 model ID（映射见 model-catalog.json `shortNames`） | 自动推荐 |
| `--thinking <level>` | minimal / low / medium / high / xhigh / max | 按模型定：`hy3`→`high`，`v4-flash`/`v4-pro`/`k3`→`xhigh`（见 model-routing.md 约束 4-4）。**三条通道都必须传**，opencode 通道的档位映射见 §3.2 |
| `--hub` | 标记 | 否（本地） |
| `--worktree <path>` | 路径 | 当前目录 |
| `--provider <name>` | 强制指定 provider | 按 model 自动选 |
| `--free` | 强制走免费通道（rift-free） | 否 |
| 其余文本 | 任务描述 | (必填) |

参数缺失处理：
- 任务描述缺失 → 要求用户补充，不猜
- `--thinking` 非法值 → 回退到该模型的默认档（`hy3`→`high`，其余→`xhigh`）
- `--thinking` 合法但**目标模型没有该档** → 按 §3.2 能力表**降到最近可用档**，⛔ 不得静默升档，且必须在输出里回显实际生效档位
- `--provider` 与 `--model` 不匹配 → 报告冲突，让用户选
- `--worktree` 路径不存在 → 报错

---

## 2. 决策流程（伪代码）

```
parse_args(user_input)

# 0. ⛔ Provider 白名单（model-routing.md 约束 6）—— 一切选择都先过这一关
WHITELIST = {
  'codebuddy-code': ['hy3', 'deepseek-v4-flash', 'deepseek-v4-pro', 'kimi-k3-2'],
  'qoderclicn':     ['qmodel_38max'],
}
# ⚠️ WHITELIST 只约束【消耗 cb/qcn 额度】的两个 provider。以下 provider 走别的钱包，⛔ 不进白名单校验：
EXEMPT_PROVIDERS = {
  'pi',                       # ⭐ 主力：Paseo 派 pi（开发）/ pi -p CLI（只读·审查）；模型见其 models.json 27 个
  'volcengine-coding',        # ⭐ 火山首选（Coding Plan，独立额度）
  'volcengine-agent-plan',    # 🔸 次选：只为 Coding Plan 没有的 5 个模型
  'volcengine-chat',          # 🔸 需消耗 Agent Plan 额度且要控思考强度时
  'github-copilot',           # ⭐ 审查通道 ⛔ 仅审查不做开发
  'claude',                   # ⚠️ 可派不推荐（消耗 Claude 订阅额度）
  'opencode',                 # 🔻 兜底，无常规用途
}
# ⛔ deepseek/*（官方 API）已被用户加入 disabled_providers，不可用

# 1. 用户显式指定
if args.model:
    entry    = resolve_shortname(args.model)        # → catalog 条目（对象）
    provider = args.provider ?? entry.preferredProvider
    # ⚠️ 白名单存的是【该 provider 下的 model id 字符串】，不是 catalog 的 key。
    #    必须取 entry.providers[provider].modelId 再比，⛔ 别拿对象或 catalog key 去比
    #    （2026-08-20 第六轮异构审抓到：直接用 entry 比会恒失败）
    # ⚠️ 先校验该模型确实在这个 provider 上有条目，否则取 .modelId 会直接崩
    #    （典型：--model hy3 --provider pi —— hy3 只在 codebuddy-code 上）
    if provider not in entry.providers:
        report_to_user_and_stop(
            f"{entry.label} 在 {provider} 上没有条目；可用: {list(entry.providers)}")
    model_id = entry.providers[provider].modelId    # 如 'deepseek-v4-flash' / 'qmodel_38max'
    # 🔴 先判豁免，再查白名单 —— 否则 WHITELIST['pi'] 会 KeyError/取空，
    #    把 pi、github-copilot 等合法通道误拦（第五轮异构审抓到）
    if provider not in EXEMPT_PROVIDERS:
        if model_id not in WHITELIST.get(provider, []):   # ⛔ 显式指定也不能突破 cb/qcn 白名单
            report_to_user_and_stop(f"{provider}/{model_id} 不在白名单，需你先确认是否开放")
    model = model_id
    # ⚠️ EXECUTE 依赖 task_type 判可见性，显式指定也必须先分类，⛔ 不能裸跳
    task_type = classify(args.description)
    goto EXECUTE

# 2. --free flag → 走 rift-free skill
if args.free:
    invoke rift-free skill with args
    return

# 3. 任务分类（见 model-routing.md §1）
task_type = classify(args.description)
# 多标签时取主标签：实现动词 > 领域关键词 > 修饰词

# 4. 硬例外（不进常规路由）
if task_type == "review":
    # ⛔ 硬约束是【评审模型族 ≠ 实施模型族】，不是「禁用 DeepSeek 审查」。
    #    reviewer = pick_review_model(implementer_family)   # 族不同即可
    #    当前默认实施族 = DeepSeek ⇒ 该路评审排除 DeepSeek；实施若是 Hy3/K3，DeepSeek 可以审。
    #    github-copilot/gpt-5.5 是当前满足约束且有额度的通道
    result = pi_run('github-copilot', 'gpt-5.5', args)   # ⛔ Copilot 仅审查，不做开发
    goto REPORT                                          # 统一走 §10 输出，⛔ 别直接 return
# ⚠️ Claude 模型（Opus/Sonnet）可派发但不推荐——消耗 Claude 订阅额度，建议留给主会话

# 5. 限免活动（P5，Hy3 优先，压过时段 —— model-routing.md 约束 4）
#    hy3_excluded() 命中排除清单任意一条即为 true（清单以 model-routing.md 约束 4-3 表为准）：
#      多模态 / 额度耗尽或探活未秒回 / algorithm / perf / architecture / 本任务 Hy3 已做砸过
if active_promo('hy3') and not hy3_excluded(task_type, args):
    model, provider, thinking = 'hy3', 'codebuddy-code', 'high'   # 0.00x，全天候第一顺位
else:
    model, provider = select_model(task_type)  # 按 §1-§2 映射，cb 侧默认落 deepseek-v4-flash
# ⚠️ K3 (1.62x S-tier) 仅在用户显式 --model k3 或任务需要极致质量时选用

# 6. ⛔ 时段优化（原 P6）2026-08-16 整步删除
#    qcn 限时1折结束、夜间折扣取消，credits 制通道已无任何时段性折扣。
#    ⚠️ 不要再写 is_night() 分支——它曾把按类型选出的高档模型无条件冲掉（2026-08-12 异构审）。
#    仍然成立的原则：任何"换更便宜 provider"的替换只作用于默认落点 flash，不下调已升上去的 K3。

# 7. Provider 降级（见 model-routing.md §4）
if not available(provider):
    model, provider = fallback(model, provider)

# 8. 选 thinking 强度（hy3 分支已在第 5 步定死 high，别覆盖掉）
thinking = args.thinking ?? thinking ?? model_default_thinking(model)  # hy3→high，其余→xhigh

# 8-1. 折算目标模型实际支持的档位（v10.3 新增；能力表与映射表见 §3.2）
#      Paseo/Hub 通道用 thinkingOptionId，档位由 provider 侧解释，直接传 thinking；
#      opencode 通道用 --variant，档位是 per-model 的，必须先折算。
effective_thinking = clamp_to_supported(model, thinking)   # ⛔ 只降不升
if effective_thinking != thinking:
    note_downgrade(thinking, effective_thinking)           # §5 输出里必须回显

EXECUTE:
# 9. 执行适配器（见 §通道判据总表 + §3）
#    🔴 先定「要不要看得见」，再定跑在哪 —— 这是通道判据总表的两个维度
needs_visibility = task_type not in ('review', 'readonly', 'qa')   # 开发实施类 ⇒ True

if args.hub and needs_visibility:
    # Hub 上的开发实施类：远程 Paseo 派发（Hub 侧同样可见）
    result = hub_remote_create(provider, model, thinking, args)
elif args.hub:
    # ⚠️ Hub 上的只读/审查类不必占一个远程 agent，仍走一次性 CLI
    result = hub_run_oneshot(provider, model, args)

elif needs_visibility:
    # ⭐ 开发实施类一律走 Paseo（可见 / 可干预 / get_agent_status）
    #    pi 也从这里派：provider 串写成 "pi/<pi内部provider>/<model>"
    if provider in ('volcengine-coding', 'volcengine-agent-plan', 'volcengine-chat', 'github-copilot'):
        result = paseo_create_agent(f"pi/{provider}/{model}", thinking, args)  # Paseo 的 pi provider
    else:                                   # codebuddy-code / qoderclicn / claude / codex
        result = paseo_create_agent(provider, model, thinking, args)

else:
    # 只读 / 短 / 审查类 —— 一次性 CLI，跑完看结论
    if provider in ('volcengine-coding', 'volcengine-agent-plan', 'volcengine-chat', 'github-copilot'):
        result = pi_run(provider, model, args)   # pi -p --provider <provider> --model <model>
    elif provider in ('opencode', 'openrouter'):
        result = opencode_run_pure(provider, model, effective_thinking, args)  # 🔻 兜底；档位必须用折算后的
    else:                                   # cb/qcn/claude/codex 没有 CLI 形态 ⇒ 仍走 Paseo
        result = paseo_create_agent(provider, model, thinking, args)

REPORT:
# 10. 输出 + 记录
#    ⚠️ 只有 Paseo/Hub 派发才有 agent_id；CLI（pi -p / opencode）是一次性进程，没有 agent_id
agent_id = result.agentId if result.kind in ('paseo', 'hub') else None   # Hub 也是 Paseo 派发，有 agent_id
cwd      = args.worktree ?? current_worktree() ?? repo_root()
print_dispatch_result(agent_id, model, provider, thinking, task_type)
if agent_id:
    save_memory(agent_id, model, task_type, cwd)     # 见 §6；CLI 无子会话可记，跳过
```

---

## 3. 执行适配器

### 3.1 Paseo 创建（codebuddy / qoderclicn / codex）

```
create_agent({
  title: "[Dev] {task_short_title}",
  provider: "{provider}/{model}",
  relationship: { kind: "subagent" },
  workspace: { kind: "current" },
  initialPrompt: "{dispatch_prompt}",
  notifyOnFinish: true,
  settings: {
    modeId: "{permission_mode}",         // 见 model-routing.md §4
    thinkingOptionId: "{thinking}"
  },
  labels: { "rift-dispatch": "true" }
})
```

#### ⛔ 创建后必须核实实际生效的模型（2026-08-02 栽过）

`list_models` 里存在某个 id **不代表派发它会生效**。静默回退有**两种模式**：

```
模式 1  id 不存在        → 请求被改写，顶层 model 字段就显示 hy3（可见）
模式 2  id 存在但服务不了 → 请求照录，运行时降级 ⚠️ 顶层 model 字段【看不出来】
```

模式 2 实例：派 `codebuddy-code/minimax-m3-pay`（该 id 在 `list_models` 里）→

```
get_agent_status:
  snapshot.model             = "minimax-m3-pay"   ← 请求值，照录
  snapshot.runtimeInfo.model = "hy3"              ← 实际在跑的
```

**创建后立刻做这个检查**：

```
mcp__paseo__get_agent_status({ agentId })
  核 snapshot.runtimeInfo.model            ← 唯一可信的「实际在跑什么」
  核 snapshot.runtimeInfo.thinkingOptionId
  核 snapshot.effectiveThinkingOptionId
```

⛔ **不要用 `list_agents` 的 `model` 字段验** —— 模式 2 下它是请求值不是运行值。

⚠️ 上面这个 M3 案例本身已随 2026-08-16 白名单关闭 M3 而失效，但**教训仍然适用**：
`list_models` 里有某个 id ≠ 派它会生效。当前白名单五个 id 中，`kimi-k3-2` 与 `qmodel_38max`
都**没有实测过 runtimeInfo**——派完务必核一次。
🔴 `qmodel_38max` 尤其要核：它是 2026-08-16 才发现的改名（旧 id `qmodel_preview` 已不存在）。

### 📌 通道判据总表（唯一真源，三文件以此为准）

| 任务类型 | 走哪条 |
|---|---|
| **开发实施类**（改代码/跑测试/提交） | ⭐ **Paseo MCP 派 pi** — `create_agent` + `provider: "pi/volcengine-coding/deepseek-v4-flash"`（或 `codebuddy-code/*` 等原有通道）。可见 / 可干预 |
| **只读 / 短 / 分析类** | `pi -p --provider volcengine-coding --model deepseek-v4-flash` |
| **审查类** | `pi -p --provider github-copilot --model gpt-5.5` ⛔ Copilot 仅审查不做开发 |
| **兜底** | `opencode` — 🔻 **无常规用途**，仅在上面三条都不可用时 |

### 3.2 pi 的两种启动方式 —— ⚠️ 不是「Paseo 还是 pi」的二选一

🔴 **两种都是 pi 这个 agent，跑的是同一套能力（同样读 AGENTS.md、同样 22 个 skill、同样 read/bash/edit/write）。**
唯一区别是**怎么把它启动起来**，进而决定你能不能看见它。

| | **Paseo MCP 派 pi**（`create_agent` + `provider: "pi/…"`） | **pi -p CLI 直跑** |
|---|---|---|
| 跑的是谁 | **pi** | **pi**（同一个） |
| 你能看见 / 能干预 | ✅ Paseo Desktop 里可见、可中止 | ❌ CLI one-shot，不进 agent 列表 |
| 结构化状态 | ✅ `get_agent_status` | ❌ 只有日志文件 |
| 开销 | 每 agent 一个 serve | 无，跑完即退 |
| **用在哪** | ⭐ **开发实施类**（要改代码/跑测试/提交，你可能想中途看一眼甚至叫停） | **只读 / 短 / 审查类**（跑完看结论就行，本来也不需要盯） |

⛔ **别把开发任务丢给 `pi -p`** —— 不是因为 pi 不行，而是因为 CLI 这条路**你看不见**。
你之前明确要求过「派发子任务走 paseo mcp，为的是能看进度、能干预」。
✅ **正确做法就是 Paseo MCP 派 pi** —— 可观测性和 pi 的能力两样都要，本来就不冲突。

#### 3.2a 开发实施类 → **Paseo MCP 派 pi**（`create_agent`）

⭐ **Paseo 的 `pi` provider 已把 27 个模型全暴露**（火山 19 + Copilot 8），且带完整 thinking 档位：

```
create_agent({ provider: "pi/volcengine-coding/deepseek-v4-flash",
               settings: { thinkingOptionId: "xhigh" }, … })
```

| 用途 | provider 串 |
|---|---|
| ⭐ 默认 | `pi/volcengine-coding/deepseek-v4-flash` |
| 升档（flash 做砸过一轮） | `pi/volcengine-coding/deepseek-v4-pro` |
| Agent Plan 独有 5 个 | `pi/volcengine-agent-plan/ark-code-latest` · `…/kimi-k3` · `…/doubao-seed-evolving` · `…/glm-latest` · `…/doubao-seed-2.0-mini` |
| 原有通道（不变） | `codebuddy-code/hy3` · `codebuddy-code/deepseek-v4-flash` · `qoderclicn/qmodel_38max` · `claude/*` · `codex/*` |

⚠️ `pi/volcengine-*/kimi-k2.7-code` 的 `thinkingOptions` 为 `null`（官方注明不支持 reasoning summaries），
派它时不要传 `thinkingOptionId`。

**pi 的能力已对齐 codebuddy 子会话**（2026-08-20 实测，主会话独立核验、不采信自述）：
读文件 → 改代码 → 写测试 → `bash` 跑测试 → `git commit`（中文 commit message 合规）。
读 `~/.pi/agent/AGENTS.md` + 项目 `AGENTS.md`/`CLAUDE.md` + `~/.agents/skills/` 全部 22 个 skill。

#### 3.2b 只读 / 短 / 审查类 → **pi -p CLI 直跑**（同一个 pi，只是不进 Paseo）

```bash
pi -p --provider volcengine-coding --model deepseek-v4-flash "{prompt}"
```

适合：审查、方案评估、只读分析、短问答——**这些你本来就不需要中途盯**，跑完看结论即可。
⚠️ `pi -p` 实测偏慢（简单请求也可能上百秒），留足超时。

⚠️ 配置注意（`~/.pi/agent/models.json`）：必须有 `compat.supportsDeveloperRole: false`
（火山不认 OpenAI 的 `developer` role）；⛔ 不要加 `compat.thinkingFormat`（填 `"zai"` 会让请求全部挂起）。

### 3.2c review 通道 —— ⭐ pi + Copilot（⛔ 仅审查，不做开发）

```bash
pi -p --provider github-copilot --model gpt-5.5 "{review_prompt}"
```

用户 2026-08-20 在 pi 里 `/login` 接入了 GitHub Copilot 订阅（`~/.pi/agent/auth.json` 已有 `github-copilot`），
**33 个模型可见**（`~/.pi/agent/models-store.json`，2026-08-20 拉取）。常用的 8 个：

| 模型 | context | 备注 |
|---|---|---|
| ⭐ `gpt-5.5` | 1M | **审查默认** —— 与历史审查同口径 |
| `gpt-5.5` | 1M | 历史盲评评委，需要更强时用 |
| `gpt-5.3-codex` · `gpt-5.5-mini` · `gpt-5-mini` | 1M / 400K / 264K | 备选 |
| `gemini-3.1-pro-preview` · `gemini-3.5-flash` | 1M / 200K | 异构族备选 |
| ⚠️ `claude-sonnet-4.6` | 1M | **Claude 族** —— 见下方红字 |

### ⛔ Copilot 这条通道**只做审查，不做开发**（用户 2026-08-20 明确）

开发/实施一律走 §3.2 的火山通道（`volcengine-coding/deepseek-v4-flash`）。
Copilot 额度留给审查这一件事，⛔ 不要拿它跑实现、重构、批量改。

🔴 **`github-copilot/claude-sonnet-4.6` 是 Claude 族** —— 主会话本身就是 Claude，
凡是**主会话自己写的东西**，⛔ 不得用它审（自审）。审我写的东西请用 `gpt-5.5` / `gpt-5.5` / `gemini-*`。

✅ **已端到端计时**（2026-08-20 实测，含 bug 的 JS 文件 + 要求 `VERDICT:` 行）：

| 通道 | 耗时 | 峰值 RSS | 结果 |
|---|---|---|---|
| `github-copilot/gpt-5.5` | **29.9s** | 197MB | exit 0，VERDICT 合规 |
| `volcengine-coding/deepseek-v4-flash` | 12.7s | 216MB | exit 0，3/3 抓全 |
| `volcengine-coding/deepseek-v4-pro` | 17.7s | 199MB | exit 0，2/3 |

⇒ 「可能上百秒」的担心不成立。**跑完零残留进程**——`pi` 是 one-shot，
无 serve / daemon / port 任何子命令，这正是它比 opencode 更省机器的原因：
opencode 每个 Paseo agent 起一个独立 serve（实测 1-1.5GB，agent idle 后不回收），
pi 处理完即退出。

#### 旧通道（仍可用，作对照）

```bash
opencode run --pure -m github-copilot/gpt-5.5 --variant xhigh "{review_prompt}"
```

⛔ 硬约束是 **评审模型族 ≠ 实施模型族**（全局红线 #8），**不是「DeepSeek 不许审查」**。
当前默认实施落点是 `deepseek-v4-flash` ⇒ **那一路**的评审才要排除 DeepSeek 族；
若本次实施用的是 Hy3 / K3 / GLM，DeepSeek 反而是合格的异构评审。
⛔ 也不能用 codex 默认的 `gpt-5.6-sol` —— 实测该 workspace `out of credits`。

### 3.2d opencode（🔻 兜底，排最后）

**没有禁用**，但排在 pi 之后。⚠️ 用之前先知道卡死的根因：

> 用户 2026-08-20 定位：**opencode 卡死电脑是「纯命令方式」造成的** ——
> 每次 `opencode run --pure` 都会拉起一个 serve，反复调用则 **serve 堆叠**，内存被吃穿。
> 这与既有记录一致（`oc-review` v1.13.0 就是靠「共享 serve + `--attach`」消掉 per-run serve 堆叠的）。

⇒ **单次、偶发调用本身是安全的**；⚠️ 但 **review 已于 2026-08-20 迁到 `pi -p` + Copilot（§3.2c）**，
opencode 现在**没有任何常规用途**，纯兜底。
⛔ **循环里反复 `opencode run` 是危险动作** —— 那种场景改用 `pi -p`，或复用共享 serve + `--attach`。

### 3.3 Hub 远程（--hub）

```bash
scp /tmp/prompt.txt hub:/tmp/
ssh hub "paseo run --detach \
  --provider {provider} --model {model} \
  --thinking {thinking} --mode '{permission_mode}' \
  --title '[Dev] {title}' \
  --cwd /home/mcdowell/{project_path} \
  \"\$(cat /tmp/prompt.txt)\""
```

Hub `--cwd` 必须是 `/home/mcdowell/...`（不是 `/Users/mcdowell/...`）。

### Dispatch Prompt 模板

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
- 遇到不确定的设计决策 → 停下来描述选项，不自行决定
- 不做任务范围外的修改，不放宽既有测试断言

## ⛔ 交付协议（2026-08-02 加：这一条被丢过两次）
- **不许在 commit + push + 报告写完之前结束这一轮。**
  ⚠️ 你跑的测试是**本会话前台命令**，跑完不会有任何异步通知——
  不要说「等自动通知」或「现在去跑 X」然后结束回复，那等于把活丢在半路。
- 测试结果**必须用 `--json --outputFile=<path>` 取计数**，⛔ 不许用 `| tail`
  （会把 jest 汇总截掉，只剩一行 PASS 却看不到失败数；退出码可能仍是 0）
- 跑测试用 `--runInBand`（并行会因多个 mongodb-memory-server 撞端口出假红）
- 报「全绿」前至少跑两次，单次结果不算
- ⚠️ 新建的测试文件是**未跟踪文件**，`git add -A` 时别漏

## 🔴 改动返回结构时必答（消费方自查）
若本任务改了 API 返回结构 / 数据契约 / 共享类型定义：
- [ ] grep 出**所有消费方**并逐一列出（含前端页面、导出、详情页、其它卡片、其它服务）
- [ ] 说明每个消费方是否需要同步改，不需要的说明理由
- [ ] 报告里写"已查无其它消费方"或列出清单——**不许省略这一节**
```

**总 prompt ≤ 2000 字。** 超过时提示拆分任务。

### 🔴 模型档位：**Hy3 能做的先给 Hy3 → 兜底 `cb/deepseek-v4-flash@xhigh`，不做预防性升档**

```
⛔ 白名单（约束 6）：cb 只有 hy3 / deepseek-v4-flash / deepseek-v4-pro / kimi-k3-2；qcn 只有 qmodel_38max

第一顺位  cb/hy3@high                  （0.00x 限免至 2026-08-31）← 先问「这活 Hy3 能不能做」
          ⛔ 排除清单（命中即跳下一档）：多模态 / 额度耗尽或排队 / algorithm / perf
             / architecture / 本任务 Hy3 已做砸过一轮。唯一真源见 model-routing.md 约束 4-3
默认落点  cb/deepseek-v4-flash@xhigh   （A 级 / 0.05x）← ⭐ **DeepSeek 系列首选**，Hy3 被排除时接手
                                        含高风险任务；性价比 1780 全场最高
                                        ⛔ algorithm / perf / architecture **全部先落这档**，不预先升 v4-pro
中间档    cb/deepseek-v4-pro@xhigh     （A 级 / 0.13x，仅贵 flash 2.6 倍）
          ⛔ **只在 flash 已于本任务做砸过一轮时进入，不预先选**（08-20 用户决策）
          ⭐ 但升档时**升它、别直接跳 K3**——08-16 同轮重测 LRU 33 vs flash 25、总分 96 vs 89，
             而它只贵 2.6 倍，K3 贵 32 倍
          ⚠️ 架构类即使升档收益也有限：重测 Kafka 31 < flash 34
🔴 极致档  cb/kimi-k3-2@xhigh           （S 级 110.5 / **1.62x 全场最贵**）⛔ **不得随意使用**
          只有两种情况可派：① 用户显式 `--model k3`  ② **v4-pro 也已做砸**（不再是 flash 做砸就上 K3——
             08-16 重测后中间多了 v4-pro 这一档，先走它）
          ⛔ 不构成理由：「任务难/重要/风险高」「是 algorithm/architecture 类」「反正只跑一次」
             「先用好的保险点」——最后一条就是「预防性升档」的原话，明令禁止
          🔴 贵 flash **32 倍**（M3 关闭后中间没档了）；性价比 68 全场最低
          ⚠️ 0723 有空转前科（报进度就 idle、git 无产出）——花 32 倍还可能拿不到产出，
             派完**必须核 `git log` 有无 commit**
          ⚠️ id 是 kimi-k3-2 不是 kimi-k3-1
          详见 model-routing.md 约束 6 §K3 使用红线
⛔ 上面「中间档 v4-pro」已取代此处原有的「备用/无推荐场景」写法（08-16 重测推翻旧结论）
⛔ 写实现代码不要用 max 档（见 model-routing.md §Thinking 强度建议 的两组实测）
⚠️ Hy3 固定 `high`：`xhigh` 从没在 Hy3 上测过，`max` 已被两轮盲评证伪（91.5 → 85.5）
```

⛔ **「任务高风险 ⇒ 升模型档位」这个推论没有实测支撑，两次实测都推翻它。**
风险高该提的是 **thinking 档位（用 xhigh）和审查强度（异构审）**，**不是模型档位**。

#### 实测依据（两次，方向一致）

**2026-08-02（n=1）**：五臂同题，那道题命中「会自动修改业务数据」这条高风险条件，
而 `m3@high` 与 `flash@high` **收敛到同一方案、零差异**；`flash@xhigh` 是五个里实现质量最高的。
全文 `~/wb/docs/technical/模型AB评测-v4flash与m3-20260802.md`。

**2026-08-06（n=12，同一天同一批任务）**：
```
flash（0.06x）8 件   P6 三修/四修 · P5 修 · 第五批验收 · 第八批部署验收
                    · Dialog 定性 · 第六批验收 · 补验收
m3（0.25x）  4 件   A.29 二修/三修 · acs-contract 评估 · session-auth 修
```
⇒ **质量看不出差异，m3 贵 4 倍**。且当天**最有价值的两个产出都是 flash 做的**：
「Dialog 定性推翻前轮错误归因」（12 格排他矩阵 + 读 TDesign 源码 + DB 实证）、
「第六批验收纠正了任务书里的错误前提」。

#### 下面这张表**只用来提高 thinking 档位和审查强度**，⛔ 不用来升模型档位

| 触发条件 | 该做什么 |
|---|---|
| **会自动修改业务数据** | thinking=xhigh · 任务书写死「不许丢掉的现有行为」清单 · 必须异构审 |
| **涉及权限 / 隔离 / 安全边界** | 同上 + 要求「权限等价性证据」（改前改后可见集合逐条相同） |
| **需要在多个方案间做架构取舍** | 先出方案 → 异构审方案 → 再实现 |
| **改动会渗透到多个消费方** | 任务书要求 grep 出所有消费方并逐一说明 |
| **前一轮已被 flash 做砸过** | ⇒ **这条才是升档的唯一入口** |

⚠️ 2026-08-06 的十一条阻断**全部由异构审抓到，测试零发现**，
而实施者用 flash 还是 m3 与被抓到的阻断数量**没有相关性**。
⇒ **质量关口在「审」，不在「作者用什么模型」。**

### ⭐ 更省的打法：低档做 + 异构审（实测有效）

```
低档模型【调查 + 出方案 + 实现】→ opencode 异构模型【只读审查】→ 低档模型【按审查意见修】
```

2026-08-02 实测印证：opencode/GPT-5.5 的异构审查抓到了
「blocker 查询漏 trim」「读取侧未复用校验函数」，并修正了一份验收报告的举证口径。
**质量关口靠「审」，不靠让作者用最贵的模型。**

**折中打法（推荐）**：低档模型做**调查 + 出方案**，方案交给 S 级或异构模型**审**，审过了再让低档模型按方案实现。既省额度又守住质量关口。

⚠️ **别只看盲评分数**：Hy3 是 B 级（91.5），但在有充分上下文、任务边界清晰、且要求"先出方案再实现"时，实测表现可以超过分数预期。**看它的中间推理质量再决定要不要换**，不要一见低档就杀。
这也是「Hy3 优先」（约束 4-2）成立的理由：它 0.00x，做砸了换 flash 重来的成本仍低于一开始就用 flash。
⛔ 但别把这条推到 `algorithm` / `architecture` 上——那两类是有盲评数据支撑的排除项（LRU 22、arch 33）。

### 派发前自查（主会话侧，逐条过）

| 检查 | 为什么 |
|---|---|
| **要派 Hy3？先探活**（发一条极短 prompt 看是否秒回） | 免费额度当日耗尽会**进排队**，长任务丢进去会卡住且 Paseo 侧未必立刻可见 |
| **要派 Hy3？先过一遍排除清单**（约束 4-3） | 多模态任务派 Hy3 **照常计费**；algorithm/perf/architecture 有盲评数据支撑的排除理由 |
| worktree 是否已建、是否有 `node_modules` | 缺依赖时 `npx jest` **零输出**，agent 会把空跑当全绿 |
| 是否给了当前测试基线数字 | 没有基线，"全绿"无法证伪 |
| 是否写明已排除的错误方向 | 否则 agent 会顺着前任的错误假设做下去 |
| 改返回结构？→ 是否要求消费方自查 | 高频事故：后端改了前端没跟上 |
| 是否要求真实浏览器验证 | happy-dom 里 `getBoundingClientRect()` 恒 0×0，TDesign 浮层会被 `isHidden` guard 立刻关闭，导致"点不动"假阴性 |

### 收割时必查（不能只看 agent 的报告）

| 检查 | 为什么 |
|---|---|
| `git log` 核对 HEAD **真的有新 commit** | 高频：agent 报"全绿"但改动全躺工作区没提交 |
| `git status` 有无未提交残留 | 同上 |
| 有无误提交的调试脚手架 | 出现过一次提交 13 个 debug spec |
| **合并后重跑全量**，不信单分支的绿 | 单分支各自绿 ≠ 合到一起绿 |
| 异构交叉审（不能同模型审自己） | 抓到过"修复引入新回退"，同模型审不出来 |

---

## 4. 前置检查

| 检查项 | 方法 | 失败处理 |
|---|---|---|
| Provider 可用 | `paseo list_providers` 或 `which opencode` | 走降级链 |
| 准备用 opencode？ | 先考虑 `pi -p` | opencode 已排最后（卡死根因见 §3.2d）。**review 也已改走 `pi -p` + Copilot**（§3.2c），opencode 仅剩兜底 |
| Agent-gates | `ls {cwd}/.agent-gates/` | 警告但不阻断 |
| 工作目录 | `--worktree` > 当前 worktree > 主仓 | 主仓时提醒用 worktree |

---

## 5. 输出

```
子会话已创建
  Agent:  {short_id} — {title}
  Model:  {provider}/{model} · thinking: {thinking}{降档时追加 " → {effective_thinking}（该模型无 {thinking} 档）"}
          {opencode 通道且 provider=volcengine-agent-plan 且用户指定了 --thinking 时追加："⚠️ 该 provider 的 --variant 静默失效，要控思考强度请改用 volcengine-chat/*，见 §3.2"}
  任务类型: {task_type}（{推荐理由}）
  CWD:    {cwd}
  Gates:  agent-gates ✓ / ⚠ 未安装

管理:
  进度: paseo agent logs {short_id}
  反馈: paseo send {short_id} "消息"
  中止: paseo agent archive {short_id}
```

---

## 6. Memory 记录

完成后立即写 memory（防上下文压缩丢失子会话 ID）。最小字段：

```json
{
  "agentId": "{short_id}",
  "model": "{provider}/{model}",
  "taskType": "{task_type}",
  "thinking": "{thinking}",
  "effectiveThinking": "{effective_thinking}",   // 与 thinking 不同即发生了降档

  "cwd": "{cwd}",
  "status": "dispatched",
  "dispatchedAt": "{ISO timestamp}",
  "title": "{task_short_title}"
}
```

---

## 7. 审查集成

子会话完成后，按 `agent-review-protocol` 的规则做交叉审查：

- 代码变更 → `pi -p --provider github-copilot --model gpt-5.5` 审查（§3.2b；opencode 通道降为兜底 §3.2c）
  ⛔ **不要改用 `volcengine-agent-plan/deepseek-*`**：实施侧已是 DeepSeek（约束 7-1），
  ⛔ 真正的约束是 **评审族 ≠ 实施族**；只有当本次实施就是 DeepSeek 时，评审才排除 DeepSeek
- 文档变更 → 同样用不同模型审查
- 审查发现按 ❌/⚠️/💡 分级，❌ 必须修复

**Skill 完成定义**：子会话创建成功 + 输出已打印 + memory 已记录。子会话的完成跟踪和审查是后续独立步骤，不阻塞本 skill 返回。
