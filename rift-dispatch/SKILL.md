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
| 1 | **便宜优先，逐级升档** | 免费档（`hy4-preview` → `hy3`，0.00x）先试 → 付费从 **`deepseek-v4.1-flash`（0.03x）** 起步 → `deepseek-v4-flash`（0.17x）→ `qwen3.8-max` → `kimi-k3-1`（1.62x）。⛔ **每一级【质量/成本升档】的唯一入口是「上一档已在本任务做砸过一轮」**，理由里要写明哪一轮、砸在哪。写不出来不许升。⚠️ 这条⛔**不管【可用性换档】**——模型在所有 provider 都拿不到时允许向上换档（必须报告），见 §2 第 5 段。⚠️ 例外：`algorithm` / `perf` 两类从 `deepseek-v4-flash` 起步（⚠️ 依据比的是 v4-flash **对 glm**，⛔ 没比过现在的 T1 ⇒ **待补测**）。🔴 并发两类已改回 T1 起步 —— 4 臂拉丁方并发题 v4.1-flash 37.5 > v4-flash 30.5 |
| 2 | 🔴 **按「要不要看得见」分通道，不是按工具分** | 🔴 **开发实施类 + 大审查 → Paseo；短任务 / 短审查 → `pi -p`**。判据是**规模**不是任务类型——Paseo 能看进度、中途干预、拿结构化状态；`pi -p` 跑完即退不堆 serve。⛔ **开发任务和大审查都不要走 `pi -p`**：它不进 Paseo agent 列表，你看不见也打不断（实测大审查走 `pi -p` 跑满 35 分钟零输出） |
| 3 | 🔴 **先判失败形态，再决定换什么** | **有产出但不合格** = `bad_output` ⇒ 走【质量/成本升档】（可换模型族）。**没产出**（静默停 / 唤不醒 / 探活不过）= `no_response` ⇒ 走【可用性】：**留在同 provider 降到下一档**，⛔ 不算做砸、⛔ 不跨钱包。⚠️ hy4 经常「碰墙」——允许你用但派发后静默停，**Paseo 抓不到明确错误** ⇒ ⛔ 别把它当成模型能力问题 |
| 4 | 🔴 **审查的硬约束是「异构」** | ⛔ **评审模型族 ≠ 实施模型族**（全局红线 #8），是**不变量**，不是针对某个模型的禁令。🔴 **含主会话：主会话就是 Claude，我自己写的东西不得派 `claude/*` 去审**。族对照表见 routing §5。⭐ **未显式指定时**默认 **`github-copilot/gpt-5.5`**（⛔ 不是「不可覆盖」；显式换 provider 会报冲突）；⚠️ **通道另按规模定**：大审查走 Paseo `pi/github-copilot/gpt-5.5`，短审查走 `pi -p`（⛔ prompt ≤200 字符） |

🔴 **两种换档理由是正交的，⛔ 别混**：**质量/成本换档**只因「本任务做砸过一轮」，⛔ 不得跨档**下调**；
**可用性换档**（所有 provider 都拿不到）只许**向上**、必须**报告**，到顶仍拿不到 ⇒ `claude/claude-sonnet-5@max`
（🔴 **LAST_RESORT**：整套钱包体系就是为了省 Claude 额度，走到这里必须显著告知）。

⚠️ **派发认 model id，⛔ 不认 label**：`hy4-preview`(0.00x) 与 `hy4-preview-x`(**0.29x**) 的 label 完全相同。

⚠️ **免费档时间线**：`08-31 hy3 止` → **hy4 免费期 `08-28 ~ 09-10`，⭐ 含 09-10 当日**（🔴 2026-09-09 用户更正，⛔ 不是 09-12；且是**每日赠额**⛔非连续免费期，**不回复 = 当日赠额已用完**须主动换）→ **09-11 起**清零，默认落点变成 **`deepseek-v4.1-flash`**（T1，0.03x，🔴 派它必须校验产出）。
✅ **2026-09-10 实测三个免费 id 全部秒回**（`hy4-preview` 6s · `hy3` 8s · `hy3-x` 4s）⇒ 当日 T0 仍然可用。
🔴 **判据永远是探活，⛔ 不是面板上的 `x0.00`** —— 那是价格；赠额耗尽后价格仍显示 0，表现是**排队/不回复**而⛔不是报错。§2 的 T0 分支本来就先探活 ⇒ **会自愈**，⛔ 不必按日期硬改。

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
  'codebuddy-code':   ['hy4-preview', 'hy3', 'hy3-x', 'glm-5.3-flash',
                       'deepseek-v4.1-flash',    # ⭐ T1 主落点，**0.03x**（⚠️ 同日从 0.06x 降下来）
                       'kimi-k3-1'],
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
  'qoderclicn':       ['qmodel_38max'],
}
# ⛔ jdcloud-joyagent 2026-09-09 停用（额度用尽、消耗太快）——已从 ~/.pi/agent/models.json 移除。
#    ⚠️ 配置完整归档在 ~/.pi/agent/providers-disabled/jdcloud-joyagent.json（含恢复清单）。
#    ⇒ 现在派它会落到「未知 provider」被拦，这是预期行为。
# 🔴 用户点名屏蔽的型号（2026-09-09）。⛔ 与 WHITELIST/EXEMPT 正交 ——
#    豁免 provider 也拦得住（否则 `--provider github-copilot --model gpt-5-mini` 会直接放行）。
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
  'bailian-token-plan':   {'deepseek-v4-pro', 'deepseek-v4-pro-0813'},
  'volcengine-chat':      {'deepseek-v4-pro'},   # 🔴 0910 异构审抓到的漏口：
                          #    它在 EXEMPT_PROVIDERS 里 ⇒ 显式 --provider volcengine-chat
                          #    --model deepseek-v4-pro 本来能绕过 P0。
                          #    ⚠️ 上面注释曾写「四个 provider 全写」—— **数错了，是五个**。
                          #    ⇒ 已加 §3h 结构性守卫：屏蔽覆盖由 catalog 的 providers 表推，
                          #       ⛔ 不再靠人肉列举（同 §3g 的思路）。
  'github-copilot':       {'gpt-5-mini', 'gpt-5.3-codex', 'gpt-5.4-mini',
                           'gemini-3.5-flash', 'gemini-3.6-flash', 'mai-code-1-flash-picker'},
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
#         而 `--provider github-copilot --model deepseek-v4-pro` 这类**没列过的 provider**
#         结构上永远拦不住。
#      ② 只给 `--model` **不给 provider** 时，§1 的 `if explicit_upstream is not None: validate()`
#         **压根不执行** ⇒ 要到 §5 把池探活完、收尾 validate() 才拦 ⇒ 用户明令禁用的型号被真请求了一遍。
BLOCKED_MODELS_ANY_PROVIDER = {'deepseek-v4-pro'}   # 🔴 用户 2026-09-10：⛔ 不允许 agent 自己派发
# ⚠️ ⛔ 别把它跟 DISABLED_PROVIDERS 合并 —— 那个是整个 provider 停用，措辞和出路都不同。

DISABLED_PROVIDERS = ['deepseek']               # 🔴 官方 API（现金）。⛔ 不是自动兜底，只能【手动】用
EXEMPT_PROVIDERS   = ['claude', 'codex', 'opencode', 'github-copilot',
                      'volcengine-coding', 'volcengine-agent-plan', 'volcengine-chat',
                      'bailian-token-plan']            # 阿里云百炼，2026-09-09 接入
# 🔴 `pi` ⛔ 不在豁免集 —— 它是【宿主】不是钱包。豁免顶层 pi 会让
#    pi/jdcloud-joyagent/GLM-5.2 绕过京东白名单。⚠️ 本清单必须与 catalog whitelist.exempt 一致。
PI_HOSTED = ('volcengine-coding', 'volcengine-agent-plan', 'volcengine-chat',
             'bailian-token-plan', 'github-copilot')   # ⛔ 京东已停用
LADDER = [('deepseek-v4.1-flash', 0.03), ('deepseek-v4-flash', 0.17),
          ('qwen3.8-max', None),     ('kimi-k3-1', 1.62)]      # T1..T4
# 🔴 2026-09-10 T1 由 `glm-5.3-flash` 换成 `deepseek-v4.1-flash`（用户决定）。
#    ⭐ 依据：**0.03x —— glm 的一半价**（⚠️ 同日从 0.06x 降下来的，cb 倍率有时效）；
#       同渠道两臂拉丁方 34.2 vs 32.3，LRU 与并发两题 **4 个朝向全胜**。
#       ⇒ 折算 83% 有效率后等效 **0.036x**，仍比 glm 单发便宜约 40% ⇒ 价格上就已成立。
#    ⚠️ 我先前写的「首次产出有效率 1/3」是 **n=3 的坏运气**，⛔ 已作废 ——
#       实测 12 次 **10/12 = 83%**（并发 4/4 · Kafka 3/4 · LRU 3/4）⇒ 等效倍率 **0.072x**。
#    🔴 **代价一：T1 从三池变一池** —— v4.1-flash **只在 cb**。
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
# routing §2 免费档排除清单分两类。free_blockers(task_type,args) ⇒ 命中项的 set()，
# 空集 = 不排除。⚠️ 只有【能力类】能被 --free 放宽：
CAPABILITY_BLOCKERS = {'algorithm', 'perf', 'architecture'}      # 能力短板，有实测依据
# ⛔ 物理不可用类（⛔ --free 也不放宽）：'multimodal'（会正常计费，免费不成立）
#    'quota_exhausted' · 'probe_queued'（探活未秒回）· 'failed_this_task'（绕过会死循环）

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
                        # ⛔ v4-pro 的四池已整块移除（用户 2026-09-10 禁用）——
                        #    留着它就等于留着一条会被探活的路径。
  'deepseek-v4-flash': [('volcengine-coding',    'deepseek-v4-flash'),
                        ('volcengine-agent-plan', 'deepseek-v4-flash'),
                        ('bailian-token-plan',    'deepseek-v4-flash-0731')], # ⚠️ id 带 -0731
                        # 🔴 **⛔ 三池，不是四池** —— cb 已于 2026-09-10 换代：
                        #    `deepseek-v4-flash` ⛔ **不在账号权威清单里**（假 id 的 400 正文实测），
                        #    但派它仍返回 200 ⇒ 🔴 **实际跑的是哪套权重测不出来**。
                        #    ⚠️ echo 字段（requestModelId / providerData.model）是**请求回显**，
                        #    ⛔ 不是运行值 —— 本例已自证：它回显了服务端清单里没有的 id。
                        #    ⇒ ⛔ 不派旧 id（不确定跑的是谁，就不该派）。
                        #    ⚠️ 要用 cb 的新型号请显式 --model deepseek-v4.1-flash
                        #    （已定档：⛔ 不进阶梯，首次产出有效率仅 1/3，见 catalog v41FlashEval_20260910）。
  'deepseek-v4.1-flash': [('codebuddy-code',    'deepseek-v4.1-flash')],
                        # 🔴 **只有 cb 一家** —— 假 id 的 400 权威清单确认它不在火山/百炼。
                        #    ⇒ 撞 cb 额度时走 TIER_PEERS 落 glm-5.3-flash（同价、三池），
                        #      ⛔ 不升 T2。
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
  # ⭐ T1：v4.1-flash 单池（cb）⇒ glm-5.3-flash 作同档替代，把三池的可用性补回来。
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
     'models': {'deepseek-v4-pro-0813', 'deepseek-v4-flash-0731', 'qwen3.8-max'},
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
#    `explicit_model or 'gpt-5.5'` 会把空串/解析成空值的非法输入【静默当成没指定】（0909 第 7 轮审查）。
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
# 🔴 provider affinity 的**证据**：cb 接了活然后静默（⛔ 不是「碰过 cb」）
cb_accepted_then_silent = any(f.get('upstream') == 'codebuddy-code'
                              and f.get('shape') == 'no_response'
                              for f in past_failures(task_context))
#   ⛔ 同一档重试⛔不计 —— past_failures 按【档】去重，⛔ 不按次数
#   ⚠️ 数不出来（无本任务历史）就是 0，⛔ 不要凭「任务看着难」估一个值
upstream, model, thinking = explicit_upstream, explicit_model, explicit_thinking
availability_escalations = []    # ⭐【可用性升档】留痕，⛔ 收尾必须报告（§7）
provider_affinity = None     # 🔴 非空时，池内排序把该 provider 提到最前（⛔ 只重排，不换档不换模型）
tier_substitutions = []      # ⭐ (原model, 换成, 原因) —— 显式 provider 上没有本档主落点时的同档换落点
#   ⛔ 与 availability_escalations 分开记：那个是【跨档】向上，这个是【档内】换落点，§7 措辞不同。

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
            if not promo_active(m):
                continue                            # ⛔ 免费期没开/赠额已尽 ⇒ 压根没碰 cb
            if ('codebuddy-code', m) in dead_landings:
                continue                            # 🔴 本任务里它已经反复无响应
            if probe_ok(m):                         # ⚠️ 长任务必须探活，怕撞排队
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
        # 🔴 **cb 接过活然后静默 ⇒ 落点优先留在 cb**，⛔ 不跨钱包。
        #    ⚠️ 措辞按代码来：判据是「cb 吞下过请求」，⛔ 不限于 T0 那一档
        #    （异构审第 4 轮的非阻断观察：原措辞写「T0 失败」比代码窄）。
        #    用户 2026-09-10 明确：「hy4 失效 → cb 的 deepseek-v4.1-flash」，⛔ 不要换 pi。
        #    依据：T0 只跑在 cb 上，而 cb 通道**本身是活的**（它刚把 hy4 的请求吞了）
        #    ⇒ 换钱包是**没有依据**的动作，只是 agent 手边最熟的动作。
        #    ⚠️ 这只**重排池内顺序**，⛔ 不改档位、⛔ 不改模型 —— 池里没有 cb 时自然回到轮换。
        #    ⭐ 写成不变量而⛔不是靠巧合：现在 T1 恰好只在 cb，但将来 T1 换人就丢了这个性质。
        # 🔴 依据必须是「**cb 确实接了活然后静默**」，⛔ 不是「碰过 cb」。
        #    ⛔ 「进过 T0 分支」太宽（免费期没开压根没发请求）；
        #    ⛔ 「promo 有效」也太宽（探活全挂时 cb 一个请求都没成功吞过）
        #       —— 异构审连续两轮都把这两种写法抓成「无证据的偏好」。
        #    ⭐ 真正的证据形态就是用户报的那个：hy4 被允许使用、派发出去了、**然后静默停**
        #       ⇒ 本任务失败记录里有 cb 落点的 no_response ⇒ cb 通道是活的。
        if explicit_upstream is None and cb_accepted_then_silent:
            provider_affinity = 'codebuddy-code'

# 🔴 显式 provider ＋【自动选出】的 model ⇒ 这一对必须是**已知存在**的组合。
#    ⚠️ 火山 / 百炼 / copilot 等在 EXEMPT_PROVIDERS 里，`validate()` 对豁免 provider
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
        if _alt is not None:
            tier_substitutions.append((model, _alt[1], f'{explicit_upstream} 上没有 {model}'))
            model = _alt[1]
        else:
            report_provider_model_mismatch_and_stop(explicit_upstream, model, _pool)

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
        pool = WALLET_PREF.get(model, [('codebuddy-code', model)])
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
| 默认任务，免费档被排除/探活失败，0 次付费档做砸 | → `codebuddy-code` + `deepseek-v4.1-flash`（T1，⛔ 只此一池）🔴 **必须校验产出** |
| T1 那一池拿不到 | → 同档替代 `glm-5.3-flash`（火山两套餐 / cb 三池），⛔ 不升 T2 |
| 默认任务，免费档已跳过，**2 次付费档**做砸（T1、T2 均失败） | → T3 `qwen3.8-max` @ `pi/bailian-token-plan`（⚠️ 只此一池） |
| T3 那**一个池拿不到** | → **可用性升档**到 T4 `kimi-k3-1`（⛔ 只许向上），并在 §7 报告。⛔ 本档已无同档替代 |
| ⛔ 显式 `--model deepseek-v4-pro` | → **停止并报告**（`report_blocked_model_and_stop`）—— 用户 2026-09-10 禁用，⛔ agent 不得自行派发 |
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
| `[Dev] 修 CRM 登录三态 · 百炼-dspF4` | 百炼的 `deepseek-v4-flash-0731` |
| `[Dev] 拆 transport 插件 · 火山C-dspF4` | 火山 **coding** 套餐的 `deepseek-v4-flash` |
| `[Dev] 同上但换池 · 火山A-dspF4` | 火山 **agent-plan** 套餐 —— ⛔ 两个套餐是独立额度池，必须能分出来 |
| `[Review] 审 diff · Cop-gpt5.5` | Copilot 的 `gpt-5.5` |
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
create_agent({ provider: "codebuddy-code/deepseek-v4.1-flash",
               settings: { thinkingOptionId: "xhigh" }, … })
```

| 用途 | provider 串 |
|---|---|
| ⭐ 默认（T1） | `codebuddy-code/deepseek-v4.1-flash`（0.03x）🔴 **必须校验产出** |
| T1 同档替代（cb 撞额度时） | `pi/volcengine-coding/glm-5.3-flash` 或 `pi/volcengine-agent-plan/glm-5.3-flash` |
| 升档 T2（上一档做砸过一轮） | `pi/volcengine-coding/deepseek-v4-flash` |
| 升档 T3 | `pi/bailian-token-plan/qwen3.8-max` —— ⛔ **不是 `deepseek-v4-pro`**（已全局禁用，照写必撞 stop） |
| 升档 T4 | `codebuddy-code/kimi-k3-1` —— ⚠️ id 是 `kimi-k3-1`，⛔ 不是 `kimi-k3` / `kimi-k3-2` |
| Agent Plan 独有 | 🔴 **当前 0 个推荐可派**。⛔ `ark-code-latest` / `doubao-seed-evolving` / `doubao-seed-2.0-mini` 已进 `BLOCKED_MODELS`；⛔ `glm-latest` 是无版本别名不许直接派。⚠️ **`kimi-k3` 暂不推荐**：① 它缺点版本号（对比 cb 权威清单里的 `kimi-k3-1`）⇒ **疑似无版本别名**，与 `glm-latest` 同类风险；② 2026-09-10 用 `只输出:OK` 这种极小 prompt 探活**挂起 >8 分钟无响应**（⚠️ 极小 prompt 也挂 ⇒ 属另一种根因，⛔ 不是 prompt 问题）。⇒ 🔴 **待核实后再决定屏蔽还是保留**，⛔ 在此之前不作为推荐落点。⭐ 判据备忘：**同一族在别处存在更具体的 id ⇒ 较短那个就是别名**，这比「含 latest」更普适 —— §3g 守卫只认字面 `latest`，所以漏了它。 |
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

✅ 走 `pi -p` 的通道（火山/百炼/Copilot）**不受影响**——pi 是单条输出。

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
| `bailian-token-plan/deepseek-v4-flash-0731` | 🔴 走 pi 时**六档全空转**（见下方专条） | ✅ **已实测** |
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
| **要派免费档？先探活**（发一条极短 prompt 看是否秒回） | 当日额度耗尽会**进排队**，长任务丢进去会卡住且 Paseo 侧未必立刻可见 |
| **要派免费档？先过排除清单**（routing §2） | 多模态任务派 Hy 系**照常计费**；algorithm/perf/architecture 有盲评数据支撑 |
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
（cb 上就是 `deepseek-v4.1-flash`）。⚠️ hy4 的典型形态就是这个：允许你用，但 Paseo 抓不到任何明确错误 |
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
| 工作目录 | `--worktree` > 当前 worktree > 主仓 | 主仓时提醒用 worktree |

---

## 7. 输出

```
子会话已创建
  Agent:  {short_id} — {title}          # 🔴 title 必须已带 · {渠道}-{模型缩写}（§3.1 标题规范）
  Model:  {provider}/{model} · thinking: {thinking}{requires_output_validation 时追加 " · 🔴 必须校验产出"}{降档时追加 " → {effective_thinking}（该模型无 {thinking} 档）"}
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

- 代码 / 文档变更 → **未显式指定时**默认 `github-copilot/gpt-5.5`（⛔ 换族，见 routing §5；显式换 provider 会报 review 冲突），
  **通道**按规模分流：**大审查** → Paseo `pi/github-copilot/gpt-5.5`；**短审查** → `pi -p --provider github-copilot --model gpt-5.5`（§3 通道判据总表）
- 审查发现按 ❌/⚠️/💡 分级，❌ 必须修复

⛔ 真正的约束是 **评审族 ≠ 实施族**（routing §5）。实施是 DeepSeek 时评审才排除 DeepSeek 族；
实施是 Hy4/K3/GLM 时，DeepSeek 反而是合格的异构评审。

**Skill 完成定义**：子会话创建成功 + 输出已打印 + memory 已记录。
子会话的完成跟踪和审查是后续独立步骤，不阻塞本 skill 返回。
