---
name: rift-dispatch
description: "Rift Dispatch: analyze task → recommend model → create Paseo sub-session or pi -p call. Triggers: 'rift-dispatch', 'rift dispatch', 'dispatch', '派任务', '派个子会话', '选模型', '用 codebuddy', '用 v4-pro', '用 GLM', 'model dispatch', '调度', 'dev sub-session'."
user-invocable: true
argument-hint: "[--model <name>] [--thinking <level>] [--hub] [--worktree <path>] [--free] <task description>"
---

# Rift Dispatch — 智能任务派发

> 🔗 **rift 家族**：**`/rift-dispatch`（派发）** · `/rift-reap`（回收）· `/rift-integration-qa`（测试验收）

分析任务 → 选模型 → 选 provider → 创建子会话（Paseo）或执行 `pi -p`。

**用户请求:** $ARGUMENTS

> **本文件 = 怎么做**（伪代码 · 命令 · prompt 模板 · 自查表）。
> **选什么 + 为什么** 在 `model-routing.md`；**数值**在 `model-catalog.json`；**历史**在 `CHANGELOG.md`。
> 同一条规则只在一处展开，本文件出现的规则以 routing 为准。

## ⛔ 开工前三条硬默认

| # | 规则 | 落点 |
|---|---|---|
| 1 | **便宜优先，逐级升档** | 免费档（`hy4-preview` → `hy3`，0.00x）先试 → 付费从 **`glm-5.3-flash`（0.06x）** 起步 → `deepseek-v4-flash`（0.17x）→ `deepseek-v4-pro`（0.51x）→ `kimi-k3-2`（1.62x）。⛔ **每一级【质量/成本升档】的唯一入口是「上一档已在本任务做砸过一轮」**，理由里要写明哪一轮、砸在哪。写不出来不许升。⚠️ 这条⛔**不管【可用性换档】**——模型在所有 provider 都拿不到时允许向上换档（必须报告），见 §2 第 5 段。⚠️ 例外：`algorithm` / `perf` / **并发诊断** / 并发实现 四类直接从 `deepseek-v4-flash` 起步（routing §6） |
| 2 | 🔴 **按「要不要看得见」分通道，不是按工具分** | 🔴 **开发实施类 + 大审查 → Paseo；短任务 / 短审查 → `pi -p`**。判据是**规模**不是任务类型——Paseo 能看进度、中途干预、拿结构化状态；`pi -p` 跑完即退不堆 serve。⛔ **开发任务和大审查都不要走 `pi -p`**：它不进 Paseo agent 列表，你看不见也打不断（实测大审查走 `pi -p` 跑满 35 分钟零输出） |
| 3 | 🔴 **审查的硬约束是「异构」** | ⛔ **评审模型族 ≠ 实施模型族**（全局红线 #8），是**不变量**，不是针对某个模型的禁令。🔴 **含主会话：主会话就是 Claude，我自己写的东西不得派 `claude/*` 去审**。族对照表见 routing §5。⭐ **未显式指定时**默认 **`github-copilot/gpt-5.5`**（⛔ 不是「不可覆盖」；显式换 provider 会报冲突）；⚠️ **通道另按规模定**：大审查走 Paseo `pi/github-copilot/gpt-5.5`，短审查走 `pi -p`（⛔ prompt ≤200 字符） |

🔴 **两种换档理由是正交的，⛔ 别混**：**质量/成本换档**只因「本任务做砸过一轮」，⛔ 不得跨档**下调**；
**可用性换档**（所有 provider 都拿不到）只许**向上**、必须**报告**，到顶仍拿不到 ⇒ `claude/claude-sonnet-5@max`
（🔴 **LAST_RESORT**：整套钱包体系就是为了省 Claude 额度，走到这里必须显著告知）。

⚠️ **派发认 model id，⛔ 不认 label**：`hy4-preview`(0.00x) 与 `hy4-preview-x`(**0.29x**) 的 label 完全相同。

⚠️ **免费档时间线**：`08-31 hy3 止` → **`09-10 hy4 止`**（🔴 2026-09-09 用户更正，⛔ 不是 09-12；且是**每日赠额**⛔非连续免费期，**不回复 = 当日已被限**须主动换）→ 免费档清零，默认落点变成 `glm-5.3-flash`。

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
| `--thinking <level>` | minimal / low / medium / high / xhigh / max | 按模型定：`hy4-preview`/`hy3`→`high`，付费档→`xhigh`（routing §4）。**三条通道都必须传** |
| `--hub` | 标记 | 否（本地） |
| `--worktree <path>` | 路径 | 当前目录 |
| `--provider <name>` | 强制指定 provider | 按 model 自动选 |
| `--free` | 强制优先 T0 免费档，并放宽**能力类**排除（routing §2 的 `algorithm`/`perf`/`architecture`）<br>⛔ 不放宽**物理不可用**类（多模态会正常计费 · 额度耗尽 · 探活排队 · 本任务已做砸）<br>🔴 T0 拿不到时**停止并报告**，⛔ 不静默转付费 | 否 |
| 其余文本 | 任务描述 | (必填) |

参数缺失处理：

- 任务描述缺失 → 要求用户补充，⛔ 不猜
- `--thinking` 非法值 → 回退到该模型默认档（`hy4-preview`/`hy3`→`high`，其余→`xhigh`）
- `--thinking` 合法但**目标模型没有该档** → 按 §3.2e 能力表**降到最近可用档**，⛔ 不得静默升档，且必须在输出里回显实际生效档位
- `--provider` 与 `--model` 不匹配 → 报告冲突，让用户选
- `--free` 与 `task_type == review` 同时成立 → **报告冲突，让用户选**（review 硬例外固定 `gpt-5.5` 是付费档；⛔ 不擅自替用户决定牺牲哪一边）
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
  'codebuddy-code':   ['hy4-preview', 'hy3', 'glm-5.3-flash',
                       'deepseek-v4-flash', 'deepseek-v4-pro', 'kimi-k3-2'],
  'qoderclicn':       ['qmodel_38max'],
}
# ⛔ jdcloud-joyagent 2026-09-09 停用（额度用尽、消耗太快）——已从 ~/.pi/agent/models.json 移除。
#    ⚠️ 配置完整归档在 ~/.pi/agent/providers-disabled/jdcloud-joyagent.json（含恢复清单）。
#    ⇒ 现在派它会落到「未知 provider」被拦，这是预期行为。
# 🔴 用户点名屏蔽的型号（2026-09-09）。⛔ 与 WHITELIST/EXEMPT 正交 ——
#    豁免 provider 也拦得住（否则 `--provider github-copilot --model gpt-5-mini` 会直接放行）。
BLOCKED_MODELS = {
  'volcengine-coding':    {'doubao-seed-2.0-lite', 'doubao-seed-2.1-turbo'},
  'volcengine-agent-plan': {'doubao-seed-2.0-lite', 'doubao-seed-2.0-mini', 'doubao-seed-2.1-turbo',
                            'doubao-seed-evolving', 'ark-code-latest'},
  'github-copilot':       {'gpt-5-mini', 'gpt-5.3-codex', 'gpt-5.4-mini',
                           'gemini-3.5-flash', 'gemini-3.6-flash', 'mai-code-1-flash-picker'},
}
# ⚠️ 屏蔽的是【型号】不是 provider ⇒ 同一 provider 的其它型号照常可用。
# ⚠️ ⛔ 别把它跟 DISABLED_PROVIDERS 合并 —— 那个是整个 provider 停用，措辞和出路都不同。

DISABLED_PROVIDERS = ['deepseek']               # 🔴 官方 API（现金）。⛔ 不是自动兜底，只能【手动】用
EXEMPT_PROVIDERS   = ['claude', 'codex', 'opencode', 'github-copilot',
                      'volcengine-coding', 'volcengine-agent-plan', 'volcengine-chat',
                      'bailian-token-plan']            # 阿里云百炼，2026-09-09 接入
# 🔴 `pi` ⛔ 不在豁免集 —— 它是【宿主】不是钱包。豁免顶层 pi 会让
#    pi/jdcloud-joyagent/GLM-5.2 绕过京东白名单。⚠️ 本清单必须与 catalog whitelist.exempt 一致。
PI_HOSTED = ('volcengine-coding', 'volcengine-agent-plan', 'volcengine-chat',
             'bailian-token-plan', 'github-copilot')   # ⛔ 京东已停用
LADDER = [('glm-5.3-flash', 0.06), ('deepseek-v4-flash', 0.17),
          ('deepseek-v4-pro', 0.51), ('kimi-k3-2', 1.62)]      # T1..T4
ENTRY  = {'algorithm': 1, 'perf': 1, 'concurrency_impl': 1, 'concurrency_diag': 1}
# routing §2 免费档排除清单分两类。free_blockers(task_type,args) ⇒ 命中项的 set()，
# 空集 = 不排除。⚠️ 只有【能力类】能被 --free 放宽：
CAPABILITY_BLOCKERS = {'algorithm', 'perf', 'architecture'}      # 能力短板，有实测依据
# ⛔ 物理不可用类（⛔ --free 也不放宽）：'multimodal'（会正常计费，免费不成立）
#    'quota_exhausted' · 'probe_queued'（探活未秒回）· 'failed_this_task'（绕过会死循环）
WALLET_PREF = {                                 # (upstream, 该 provider 上的真实 modelId)
  # 🔴 多池【轮换】，⛔ 不是固定优先级（用户 2026-09-09）——火山【两个套餐】/ 百炼 / cb 地位相同。
  #    加百炼正是因为火山与 cb 这个月量不够 ⇒ 用哪个由「哪个还有量」决定，撞限额换下一个。
  'deepseek-v4-pro':   [('volcengine-coding',    'deepseek-v4-pro'),
                        ('volcengine-agent-plan', 'deepseek-v4-pro'),        # ⭐ 另一份火山套餐
                        ('bailian-token-plan',    'deepseek-v4-pro-0813'),   # ⚠️ id 带 -0813
                        ('codebuddy-code',        'deepseek-v4-pro')],
  'deepseek-v4-flash': [('volcengine-coding',    'deepseek-v4-flash'),
                        ('volcengine-agent-plan', 'deepseek-v4-flash'),
                        ('bailian-token-plan',    'deepseek-v4-flash-0731'), # ⚠️ id 带 -0731
                        ('codebuddy-code',        'deepseek-v4-flash')],
  'glm-5.3-flash':     [('volcengine-coding',    'glm-5.3-flash'),
                        ('volcengine-agent-plan', 'glm-5.3-flash'),
                        ('codebuddy-code',        'glm-5.3-flash')],
                        # ⚠️ 百炼没有 glm-5.3-flash ⇒ 只在火山两套餐与 cb 之间轮换
  'kimi-k3-2':         [('codebuddy-code',        'kimi-k3-2')],
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
  'deepseek-v4-pro': [('bailian-token-plan', 'qwen3.8-max')],
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
     'models': {'deepseek-v4-pro-0813', 'deepseek-v4-flash-0731', 'qwen3.8-max'},
     'when':   lambda dt: dt.hour >= 22 or dt.hour < 8},
  'codebuddy-code': {                          # ⛔【工作日 09-12 / 14-18】之外都打折
     'models': {'deepseek-v4-flash', 'deepseek-v4-pro'},
     'when':   lambda dt: not (dt.weekday() < 5 and (9 <= dt.hour < 12 or 14 <= dt.hour < 18))},
}
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
    # 🔴 屏蔽名单**最先判** —— ⛔ 放在豁免判断之后就等于对豁免 provider 失效
    if model is not None and model in BLOCKED_MODELS.get(upstream, ()):
        report_blocked_model_and_stop(upstream, model)
    if upstream in DISABLED_PROVIDERS:      report_disabled_and_stop()
    elif upstream in WHITELIST:
        if model is not None and model not in WHITELIST[upstream]:
            report_conflict_and_stop()      # ⇒ pi/jdcloud-joyagent/GLM-5.2 在这里被拦
    elif upstream not in EXEMPT_PROVIDERS:  report_unknown_provider_and_stop()

# 🔴 显式值单独存，⛔ 后续阶段只读不写
explicit_upstream = split_provider(args.provider)[1] if args.provider else None
explicit_model    = resolve_short_name(args.model)   if args.model    else None
# 🔴 ⛔ 后面一律用 `is None` 判，⛔ 不许用 truthiness ——
#    `explicit_model or 'gpt-5.5'` 会把空串/解析成空值的非法输入【静默当成没指定】（0909 第 7 轮审查）。
if args.model is not None and not str(args.model).strip():
    report_conflict_and_stop()      # ⛔ 空 --model 是输入错误，不是「没指定」
explicit_thinking = args.thinking                                # 可为 None

task_type = classify(user_input)          # routing §6；⚠️ concurrency 要先判子类
scope     = estimate_scope(user_input, args)   # 文件数 / 预计工具调用数 —— 供 is_large_review
cwd       = resolve_worktree(args.worktree)
agent_id  = None                          # 🔴 只有 Paseo 派发才会被赋上，CLI 路径保持 None
failed_paid_tiers_in_this_task = count_failed_paid_tiers(task_context)
#   ⛔ 只数【付费阶梯内】做砸的档数：T0 免费档失败⛔不计、同一档重试⛔不计
#   ⚠️ 数不出来（无本任务历史）就是 0，⛔ 不要凭「任务看着难」估一个值
upstream, model, thinking = explicit_upstream, explicit_model, explicit_thinking
availability_escalations = []    # ⭐【可用性升档】留痕，⛔ 收尾必须报告（§7）

# ═══ 1. 显式 provider 先过 P0 ═══ 此时 model 可能仍是 None，validate 允许
# 🔴 ⛔ review 的 provider 冲突必须【抢在 P0 之前】判（0909 第 7 轮审查）——
#    否则 `review --provider deepseek` 报的是「provider 已停用」、
#    `review --provider codebuddy-code --model gpt-5.5` 报的是「白名单不匹配」，
#    **用户拿到的原因全是错的**（真实原因是「审查通道不能换 provider」）。
if task_type == 'review' and explicit_upstream not in (None, 'github-copilot'):
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
#      ② `review --model gpt-5.5` 掉进普通阶梯，去试【codebuddy-code/gpt-5.5】（cb 根本没有它）
#      ③ `review --provider 火山 --model X` 绕过 provider 冲突判断，直接派到实施族上
#    ⇒ 判断条件只能是 task_type，⛔ 不能再带 explicit_model。
if task_type == 'review':
    # ⛔ 用 args.free 而⛔不是 want_free —— want_free 自带 `and explicit_model is None`，
    #    在这里用它等于把洞 ① 留着。
    if args.free: report_conflict_free_vs_review_and_stop()   # ⛔ 不替用户决定牺牲哪边
    model = 'gpt-5.5' if explicit_model is None else explicit_model
    #                 ↑ ⛔ 用 `is None`，⛔ 不用 `or` —— 见第 1 段那条注释
    # 🔴 ⛔ 不许静默覆盖显式 --provider：本段职责是「未指定时给默认」，⛔ 不是「强行改成 copilot」。
    if explicit_upstream is None:
        upstream = 'github-copilot'          # ⭐ review 的默认 provider
    else:
        # 🔴 走到这里 explicit_upstream **必然是** 'github-copilot' —— 其它值在【第 1 段】
        #    （P0 之前那个 review 冲突检查）就被 report_review_provider_conflict_and_stop 拦掉了。
        # ⚠️ 这里原本重复写了一遍 elif + 报错，**覆盖率实测那几行从没被走到** ⇒ 是死代码。
        #    死代码在「当规范读」的伪代码里有害：读的人会以为拦截发生在这里。
        assert explicit_upstream == 'github-copilot'
    # ⚠️ 措辞校准：是「**未显式指定时**默认固定 gpt-5.5」，⛔ 不是「不可覆盖」——
    #    P1 显式优先仍然成立（routing 附录 P1 在 P2 之前）。
    # ⛔ 但显式指定同族模型时必须报冲突：评审族 ≠ 实施族（routing §5）是不变量。
    #    主会话是 Claude ⇒ ⛔ 不用 claude/*

# ═══ 4. 选模型：T0 免费档 → T1..T4 阶梯 ═══ ⛔ 只赋值，不 return
elif model is None:
    # --free 只放宽【能力类】排除（algorithm/perf/architecture）——用户显式接受能力风险；
    # ⛔ 不放宽【物理不可用】类（多模态计费/额度耗尽/探活排队/本任务已做砸）——
    #    那几条绕过去也拿不到免费，只会静默变成付费或死循环。判定见 routing §2。
    blockers = free_blockers(task_type, args)        # ⇒ set()，空集表示不排除
    # ⚠️ T0 只跑在 codebuddy-code 上 ⇒ 显式指定的正是它时【不算冲突】；
    #    原先一律要求 explicit_upstream is None，会让 `--free --provider codebuddy-code`
    #    直接掉进 report_free_unavailable_and_stop（0909 审查抓到）。
    t0_provider_ok = explicit_upstream in (None, 'codebuddy-code')
    if t0_provider_ok and (not blockers or
                           (want_free and blockers <= CAPABILITY_BLOCKERS)):
        for m in ('hy4-preview', 'hy3'):            # T0，顺位固定
            if promo_active(m) and probe_ok(m):     # ⚠️ 长任务必须探活，怕撞排队
                upstream, model, thinking = 'codebuddy-code', m, thinking or 'high'
                break
    if model is None and want_free:
        report_free_unavailable_and_stop(blockers)   # 🔴 显式要免费却拿不到 ⇒ 停
    if model is None:                                # T1..T4
        i = ENTRY.get(task_type, 0) + failed_paid_tiers_in_this_task
        # ⛔ failed_paid_tiers 只数【付费阶梯内】做砸的档数：T0 不计、同档重试不计
        if i > 3: report_ladder_exhausted_and_stop()  # ⛔ 不静默重派 K3
        if i == 3: warn('🔴 K3 1.62x，派完必须核 git log 有无 commit（0723 空转前科）')
        model = LADDER[i][0]
        thinking = thinking or 'xhigh'

# ═══ 5. 选 provider ═══ ⚠️ 显式 provider 存在时⛔不许被换掉
if upstream is None:
    # 🔴🔴 本段有【两个正交的换档理由】，⛔ 千万别混：
    #   ① 质量/成本换档（第 4 段做完了）：升档唯一入口是「本任务做砸过一轮」，⛔ 不得跨档【下调】
    #   ② 可用性换档（本段）：模型【拿不到】。只许【向上】，⛔ 永远不向下 —— 向下 = 质量回退
    tier = next((i for i, (m, _) in enumerate(LADDER) if m == model), None)
    while True:
        pool = WALLET_PREF.get(model, [('codebuddy-code', model)])
        # ⭐ 轮换时把【当前正在打折】的池排前（sorted 稳定 ⇒ 同为打折/同为原价时保持原轮换序）
        # 🔴 这里是【档位内选落点】，⛔ 不许换成别的档位。
        #    2026-08-12 那个 bug 的错误是 is_night() 把「做砸才升上去的高档模型」
        #    换成了【低档】的便宜模型，越过了档位边界往下选。
        # ⚠️ ⛔ 别跨钱包比价（火山包月 / cb credits 倍率 / 百炼积分，单位不可通约）——
        #    只比「同一型号的多个池」，那一步才可算（同型号，一边打折一边不打）。
        pool = sorted(pool, key=lambda x: not is_discounted_now(x[0], x[1]))
        landed = first_available(pool)
        if landed is None:
            # ⭐ 本档模型所有池都拿不到 ⇒ 先在【同档】里换落点（⛔ 优先于升档：同档能落就别涨价）
            # ⛔ 同档替代⛔不参与上面的折扣排序 —— 它没有价格依据，只是兜底。
            landed = first_available(TIER_PEERS.get(model, []))
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
    if explicit_model is None:
        model = model_id_on(upstream, model)   # 用户只给了 provider ⇒ 在该 provider 内取该模型的 id
    if first_available([(upstream, model)]) is None:
        # ⛔ 显式指定的落点拿不到 ⇒ **报告并停止**。
        # ⛔ 不许静默换 provider（违反「显式 provider ⛔ 不许被换掉」），
        # ⛔ 也不许走可用性升档 —— 用户点名要这个，换掉就不是他要的东西了。
        report_no_landing_and_stop(model)

# ═══ 6. 统一收尾 ═══ 🔴 所有路径都走到这里，⛔ 上面任何分支都不许自己返回结果
validate(upstream, model)                  # 🔴 自动选出的组合同样要过 P0
channel = 'paseo' if is_dev_task(task_type) or is_large_review(scope) else 'cli'
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
provider = normalize_provider(upstream, channel)
thinking = clamp_to_supported(model, thinking or default_thinking(model))  # §3.2e，⛔ 只降不升
result   = execute(channel, provider, model, thinking)    # §3
agent_id = result.agent_id if channel == 'paseo' else None
# ⚠️ `pi -p` 是一次性进程，⛔ 没有 agent_id —— 用 result.run_id 留痕
save_memory(agent_id=agent_id, run_id=(None if channel == 'paseo' else result.run_id),
            provider=provider, model=model, task_type=task_type,
            thinking=thinking, cwd=cwd)              # §8
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
| **大审查**（多文件 / 读大量源 / 预计 20+ 工具调用） | ⭐ **Paseo `create_agent`** | 🔴 同上——它是长活，⛔ 不是 one-shot |
| **短任务**（单文件、明确问题、只读分析、短审查） | `pi -p` CLI | 跑完看结论就行，省机器不堆 serve |
| **兜底** | `opencode` 🔻 | 无常规用途，仅前面都不可用时 |

⚠️ **本表 2026-09-08 修正**：原先把「审查类」整类钉给 `pi -p`，理由写的是「审查不需要盯」。
本轮实测推翻该前提——`pi -p` + gpt-5.5 跑满 **35 分钟零输出**，全程不可见、只能盲杀；
而同期 Paseo 派的两个审查 agent 都能看到它们各自在第 13 / 22 步撞 429。
⇒ **判据回归硬默认 #2 的「要不要看得见」，⛔ 不按任务类型一刀切。**

模型侧不变：审查⛔用同族；⭐ 默认 `github-copilot/gpt-5.5`（Paseo 串为 `pi/github-copilot/gpt-5.5`）。

### 📌 派发路径用例 —— 🔴 **这张表有可执行测试**

⛔ 别只照着人眼自查：`scripts/pipeline-test.py` 会**直接执行 §2 的伪代码**跑这些用例并断言落点。
改了 §2 就跑它（连同 `scripts/consistency-check.py`）。
✅ 已验证它能抓住 5 类真实破坏：channel 写死 · 入口档改错 · 审查换模型 · 丢 `pi/` 前缀 · 新增未赋值变量。


| 输入 | 期望结果 |
|---|---|
| `--provider jdcloud-joyagent --model GLM-5.2` | ⛔ **拦住**（JD 白名单只有两个 DeepSeek） |
| `--provider pi/jdcloud-joyagent --model GLM-5.2` | ⛔ **同样拦住** —— 先 `split_provider` 取 upstream 再校验 |
| `--provider pi/jdcloud-joyagent --model DeepSeek-V4-pro` | ⛔ **拦住** —— 京东 2026-09-09 停用，已移出白名单与豁免集 ⇒ 落「未知 provider」 |
| `--provider volcengine-coding --model deepseek-v4-flash` | ✅ 放行（豁免集） |
| `--provider github-copilot --model gpt-5.5` | ✅ 放行（豁免集） |
| `--provider deepseek --model deepseek-v4-pro` | ⛔ **拦住**（DISABLED_PROVIDERS） |
| 默认任务，**免费档可用** | → `codebuddy-code` + `hy4-preview`（T0，⛔ 还没进付费阶梯） |
| 默认任务，免费档被排除/探活失败，0 次付费档做砸 | → `pi/volcengine-coding` + `glm-5.3-flash`（T1，钱包①） |
| 默认任务，免费档已跳过，**2 次付费档**做砸（T1、T2 均失败） | → T3 `deepseek-v4-pro`，provider 按 `WALLET_PREF` 轮换 + 折扣窗口定（默认落 `pi/volcengine-coding`） |
| T3 且**四个池全拿不到** | → 同档替代 `pi/bailian-token-plan` + `qwen3.8-max`（`TIER_PEERS`，⛔ 不升档） |
| T3 且四个池与同档替代**都拿不到** | → **可用性升档**到 T4 `kimi-k3-2`（⛔ 只许向上），并在 §7 报告 |
| 一路到 T4 仍拿不到 | → 🔴 `claude/claude-sonnet-5` @ `max`（**LAST_RESORT**，§7 必须显著告知在烧 Claude 额度） |
| 连 `claude/claude-sonnet-5` 也拿不到 | ⛔ **停止并报告**（`report_no_landing_and_stop`），⛔ 不静默降档 |
| 显式 `--thinking low` + 落到 LAST_RESORT | thinking 保持 **`low`**，⛔ 不被 LAST_RESORT 的 `max` 覆盖 |
| `algorithm` 类，0 次付费档做砸 | → `pi/volcengine-coding` + `deepseek-v4-flash`（跳 T0，T2 起步） |
| 只给 `--provider volcengine-coding` 不给 model | ✅ P1 仍校验该 provider，再按默认档位补 model |
| 只给 `--model v4-pro` 不给 provider | ✅ 先按 WALLET_PREF 定 provider，再回 P0 校验 |
| 大审查（多文件 / 20+ 工具调用） | → Paseo `pi/github-copilot/gpt-5.5`，⛔ 不走 `pi -p` |
| 短审查（单文件） | → `pi -p --provider github-copilot --model gpt-5.5`，prompt ≤200 字符 |

### 3.1 Paseo 创建

```
create_agent({
  title: "[Dev] {task_short_title}",
  provider: "{provider}/{model}",
  relationship: { kind: "subagent" },
  workspace: { kind: "current" },
  initialPrompt: "{dispatch_prompt}",
  notifyOnFinish: true,
  settings: build_settings(provider, model, thinking),   // 🔴 见下，⛔ 不要无条件传 modeId
  
  labels: { "rift-dispatch": "true" }
})
```

#### 🔴 `settings` 必须按 provider 生成，⛔ 不能无条件传 `modeId`

```python
def build_settings(full_provider, model, thinking):
    # full_provider 形如 'pi/volcengine-coding' / 'codebuddy-code'；model 是该 provider 上的真实 id
    root = full_provider.split('/')[0]
    _, upstream = split_provider(full_provider)

    # 🔴 该模型的 thinkingOptions 为 null ⇒ ⛔ 一个档位字段都不能传
    if upstream.startswith('volcengine') and model == 'kimi-k2.7-code':
        return {}

    s = {'thinkingOptionId': thinking}
    if root == 'pi':
        return s                              # 🔴 pi provider 的 availableModes 为空，
                                              #    传 modeId 直接报 Invalid mode
    if root in ('codebuddy-code', 'qoderclicn'):
        s['modeId'] = 'bypassPermissions'
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
| **用在哪** | ⭐ **开发实施类 + 大审查** | **短任务 / 短审查 / 只读分析** |

⛔ **别把开发任务丢给 `pi -p`** —— 不是 pi 不行，是 CLI 这条路**你看不见**。
✅ 正确做法是 **Paseo 派 pi**：可观测性和 pi 的能力两样都要，本来就不冲突。

#### 3.2a 开发实施类 → Paseo 派 pi

⭐ Paseo 的 `pi` provider 把 `~/.pi/agent/models.json` 里的模型全暴露，带完整 thinking 档位。
⚠️ **具体数量以 `pi --list-models` 为准，⛔ 不要在文档里写死**（会过期）：

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
| ✅ **`claude-*` 已整族移除** | 2026-09-08 从 pi 的 Copilot 通道删掉——主会话就是 Claude，留着容易误用成自审 |

可用异族评审（**11 个**，= pi 配置 17 个 − 用户 2026-09-09 屏蔽的 6 个）：
`gpt-5.5`(⭐审查默认) · `gpt-5.6-sol` · `gpt-5.6-luna` · `gpt-5.6-terra` · `gpt-6-astra` · `gpt-5.4`
· `gemini-3.7-flash` · `gemini-3.8-flash` · `grok-4.5` · `grok-4.6` · `mai-code-1.1-flash`

🔴 **⛔ 已屏蔽（`BLOCKED_MODELS`，用户 2026-09-09 点名）**：
`gpt-5-mini` · `gpt-5.3-codex` · `gpt-5.4-mini` · `gemini-3.5-flash` · `gemini-3.6-flash` · `mai-code-1-flash-picker`
✅ **那 5 个未知型号已测**（2026-09-09 三题盲评，⭐ 详见 catalog `blindEval_copilot5_20260909`）：

| 档 | 模型 | /120 |
|---|---|---|
| ⭐ 第一 | `grok-4.5` ≈ `grok-4.6` | 109.5 · 106.0 |
| 🔸 第二 | `gemini-3.7-flash` ≈ `gemini-3.8-flash` | 97.0 · 93.0 |
| ⛔ 垫底 | `mai-code-1.1-flash` | 81.5 |

🔴 **⛔ 不可与既有 /120 榜横比** —— 本轮走 `pi -p`（**无 agent 系统提示**），旧榜是 Paseo agent。
⛔ **同档内不可分高下**：`grok-4.5` / `grok-4.6` 在 lru 与 kafka 两题**换位后第一名翻转**，
差 3.5 与实测位置偏好（A 位比 E 位高 **2.83**）同量级；gemini 两个同理。
⭐ 用户口径是「做个参考」⇒ **⛔ 未改派发阶梯**；审查默认仍是 `gpt-5.5`，
grok 两个可作**异族审查备选**，⛔ `mai-code-1.1-flash` 不建议。

🔴 **Copilot 通道调不到 Claude 族** —— 主会话就是 Claude，留着容易误用成自审。

⚠️ **2026-09-09 实测更正：这⛔不是我们配出来的，是 GitHub 服务端拦的。**
`models-store.json` 里 **`claude-*` 8 个全都还在**，`pi --list-models` 也看得到；
但真发请求会拿到 **400 `model_not_supported`**。
⇒ 旧记录说「实现方式是 models.json 覆盖 store」是**错的** —— 见下条。

🔴 **⛔ 从 `models.json` 删条目【屏蔽不了 Copilot 模型】**（2026-09-09 实测）：
pi 会**回落 `models-store.json`**。实测把 `gpt-5-mini` 从 models.json 删掉后，
`pi -p --provider github-copilot --model gpt-5-mini` **照样返回 OK**。
而 store 按 etag 自动刷新，改它也会被冲掉。
⇒ **Copilot 侧的屏蔽只能靠本 skill 的 `BLOCKED_MODELS`**（P0 `validate()` 里拦）。
⚠️ 对比：**火山两个 provider 删得掉** —— 它们只在 `models.json` 里定义，没有 store 兜底。
⇒ `doubao-*` / `ark-code-latest` 已从 models.json 移除（归档 `~/.pi/agent/providers-disabled/blocked-models-20260909.json`）。
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

| 模型 | **支持的档位**（读自 `~/.pi/agent/models.json` 的 `thinkingLevelMap`） | 实测过？ |
|---|---|---|
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
| `pi/volcengine-*/kimi-k2.7-code` | ⚠️ `thinkingOptions` 为 `null` | ⛔ 不要传 |
| ~~claude 系~~ | ⛔ 已从 pi 的 Copilot 通道移除（§3.2c）；Paseo 派 `claude/*` 时是 `low`/`medium`/`high`/`max` | — |

🔴 **读法**：`thinkingLevelMap` 里 **value 为 `null` 就是不支持该档**，⛔ 不要只看 key。
   （我第一版按 key 列，结果把 `grok-4.5` 写成支持 `xhigh`——实际它 `xhigh: null`。）
🔴 **「配置支持」≠「实测过」**：右列标 ⚠️ 的只是没端到端跑过，⛔ 不是档位未知。

**折算规则：只降不升。** `xhigh` → 查上表：该模型 `thinkingLevelMap['xhigh']` 为 `null` 就往下降到最近的非 null 档
（例：`grok-4.5` 无 `xhigh` ⇒ 落 `high`；`gpt-5-mini` 同理）。Paseo 派 `claude/*` 时落 `max`。
⚠️ `thinkingLevelMap` 为 `null` 的（gemini 全系、kimi 两个）⛔ 无依据可查，别猜，先实测。
⛔ **禁止静默升档**（会造成超预期 token 消耗）；降档必须在 §7 输出里回显，
memory 记 `effectiveThinking` 字段留痕。

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

- 代码 / 文档变更 → **未显式指定时**默认 `github-copilot/gpt-5.5`（⛔ 换族，见 routing §5；显式换 provider 会报 review 冲突），
  **通道**按规模分流：**大审查** → Paseo `pi/github-copilot/gpt-5.5`；**短审查** → `pi -p --provider github-copilot --model gpt-5.5`（§3 通道判据总表）
- 审查发现按 ❌/⚠️/💡 分级，❌ 必须修复

⛔ 真正的约束是 **评审族 ≠ 实施族**（routing §5）。实施是 DeepSeek 时评审才排除 DeepSeek 族；
实施是 Hy4/K3/GLM 时，DeepSeek 反而是合格的异构评审。

**Skill 完成定义**：子会话创建成功 + 输出已打印 + memory 已记录。
子会话的完成跟踪和审查是后续独立步骤，不阻塞本 skill 返回。
