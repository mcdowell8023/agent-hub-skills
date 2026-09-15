# Rift Dispatch — 变更记录

## v11.5 (2026-09-10) — T1 换成 `deepseek-v4.1-flash`

**起因是用户的一个观察：「有的 agent 没优先用 4.1 flash，而是优先用了 glm 5.3 flash」。**
不是漏写优先级 —— 阶梯里写的就是 glm。但那个决定建立在一个**错数字**上。

### 🔴 作废 v11.4 的「首次有效率 1/3」—— 那是 n=3 的坏运气

补测 3 题 × 4 轮：

| | 有效 | 率 |
|---|---|---|
| concurrency | 4/4 | 100% |
| kafka | 3/4 | 75% |
| lru | 3/4 | 75% |
| **合计** | **10/12** | **83%** |

⇒ 等效倍率 `0.06 / 0.83` = **0.072x**（对照 glm 0.06x 单发 · T2 0.17x）。

p=0.83 时「3 次里 ≤1 次有效」的概率约 **7.7%** —— 不常见但会发生，而我拿它支撑了一个
**排他性结论**（⛔ 不进阶梯）。⭐ **n=3 不足以否掉一个同价更强的候选。**

### 🔴 T1: `glm-5.3-flash` → `deepseek-v4.1-flash`

依据：**同价 0.06x**，同渠道两臂完整拉丁方 34.2 vs 32.3，**LRU 与并发两题 4 个朝向全胜**
（Kafka 反向且翻转 ⇒ 该题不可分）。

⚠️ 我提了两点代价，用户确认后照做，**两点都用机制兜住**：

**代价一：T1 从三池变一池**（v4.1-flash 只在 cb，400 权威清单确认火山/百炼都没有）。
⇒ `glm-5.3-flash`（三池）降为 T1 的 **`TIER_PEERS`**。cb 撞额度时落 glm（同价 0.06x），
⛔ 不必升到 T2(0.17x)。glm 仍然是 T1 可用性的实际来源。

**代价二：17% 的失败不是报错，是「看着像正常输出」的垃圾**（实测一次 3988 字、正文带
`<｜｜DSML｜｜>` 内部标记）。⇒ 新增 `OUTPUT_VALIDATION_REQUIRED`，并且**算进决策结果**：

```python
requires_output_validation = model in OUTPUT_VALIDATION_REQUIRED
```

⛔ **不是只声明一个集合** —— 那是「规则只写在散文里」的变体，跟 `glm-latest` 那次同一个错。
现在它是派发结果的一个字段、§7 会打出来、§6 收割表有对应硬门控行；
§3j 守卫钉住「只声明不读取」这种写法（已做注入验证：把那行改成 `False` 立刻报警）。

### 🔴 换 T1 当场开出两个洞，都是校验抓到的

**① `--provider volcengine-coding`（不给 model）会把火山没有的型号派过去。**
火山在 `EXEMPT_PROVIDERS` 里 ⇒ `validate()` **对豁免 provider 不校验 model**，拦不住。
旧 T1 `glm-5.3-flash` 火山有，所以这个洞是**换 T1 那一刻才出现的**。
⇒ 新增 provider×model 错配检查，判据取 `WALLET_PREF`（该型号的真实池），⛔ 不是猜。
⭐ 而且不是直接报错：先在**同档**里找该 provider 真有的落点（⇒ 落 `glm-5.3-flash`），
记入 `tier_substitutions` 并在 §7 报告；同档也没有才停（如 `--provider github-copilot`）。
⚠️ 这跟「⛔ 不擅自替换成相近模型」不冲突 —— 那条针对用户**显式给了 model**的情况。

⭐ **教训：换阶梯成员时必须重扫「谁家有它」。** 池子数不是附属信息，它决定了
「显式指定 provider」这类既有用法还成不成立。

**② `ENTRY` 里并发两类「跳过 T1」的依据被直接推翻。**
旧依据是「并发题 v4-flash(T2) 35 > glm(T1) 31」⇒ 跳过 T1。
但 4 臂拉丁方里**并发题新 T1 是 37.5、T2 是 30.5，+7 分且 4 朝向全胜**
⇒ 跳过 T1 变成「既贵 2.8 倍又更差」。已改回 T1 起步。

⚠️ `algorithm` / `perf` **保留** T2 起步，但标注了依据**已不指向当前 T1**
（旧依据比的是 v4-flash 对 **glm**，⛔ 没比过 v4.1-flash）⇒ 待补测，
补出来之前⛔不当「已验证」用。

### 🔴 异构审查（`bailian/deepseek-v4-flash-0731`，234s）抓到三处，其中一处是同一个错的第二次

⚠️ Copilot 通道两个模型**先后挂死**（`gpt-5.5` 7 分钟、`gpt-5.6-sol` **37 分钟**零输出），
但极小 prompt 基线 4s / 19s 秒回 ⇒ **不是通道挂了**，差别在「带 tools 去读 1093 行的 SKILL.md」。
⇒ 换 DeepSeek 族（我是 Claude，它是合格异族）拿到结论。

**① 同档换落点「声明了但没落地」—— 第二处。** 我在「显式 provider 错配」那条路径加了
`tier_substitutions.append`，但 **§5 的可用性路径落到 `TIER_PEERS` 时根本不 append**
⇒ 换到 glm 时用户只看得见 `availability_escalations`，【档内换落点】完全不可见。
⚠️ **同一件事有两个入口，改一处忘一处** —— 与「rubric 改了但驱动 prompt 没改」同形。
⇒ 已补 append + §7 模板加 `tier_substitutions` 槽位 + 补用例；
⭐ `coverage-check` 正好把那一行报成「无用例走到」（§2:381），**工具自己钉住了这个漏**。

**② §3.2a 落点表整片过期。** ⭐默认还写着 `pi/volcengine-coding/deepseek-v4-flash`（照做会跳过新 T1）、
升档行写 `deepseek-v4-pro`（已全局禁用，照做必撞 `report_blocked_model_and_stop`）。已按新阶梯重写五行。

**③ 白名单注释还标 `0.06x`。** 已改 0.03x。

### ⚠️ 顺带暴露：火山 agent-plan 上那个 `kimi` 三代 id 疑似无版本别名

cb 的 400 权威清单里带点版本号，而 pi 给火山配的那个**没有**。

⭐ **判据比「含 `latest`」更普适：同一族在别处存在更具体的 id ⇒ 较短那个就是别名。**
§3g 守卫只认字面 `latest`，所以漏了它。

🔴 用 `只输出:OK` 这种极小 prompt 探活 **挂起 >8 分钟无响应**（⚠️ 极小 prompt 也挂 ⇒ 属另一种根因）。
⇒ **暂不作为推荐落点**，⛔ 但也不直接进 `BLOCKED_MODELS` —— 没证据就屏蔽会堵死可能合法的路径。

### ⚠️ 我这一轮踩的两个旧坑

**① `ps | grep` 把自己的 shell 杀了（exit 144，第四次）。** `[x]` 括号技巧只防「grep 匹配自己」，
防不住**我的命令行别处也含那个字符串**（补丁正文里到处是）。⇒ 正解是 **PID 白名单 + 把调用写进文件**。
顺带清掉一个跑了 **6.5 小时**的泄漏 `pi -p` one-shot。

**② emoji 开头的说明键混进数据表（第三次）。** 这次是 `blockedModelsAnyProvider` 放进了
`catalog.whitelist`，而那里**值为 list 的键会被解析成「某 provider 的允许清单」** ⇒ 已挪到顶层。

### 验证

`consistency-check` ✅（新增 §3i / §3j）· `pipeline-test` **72** 用例 ✅ · `coverage-check` §2 **154 行 100%** ✅
异构审查 `bailian/deepseek-v4-flash-0731` **VERDICT: PASS**（三处 ⚠️ 已全部修完）

---

## v11.10 (2026-09-15) — T0 只留 hy3 · T1 变三池 · 补屏蔽

### 🔴 T0 只留 `hy3`，思考档取 `max`

用户决定：`hy4-preview` **不稳定不用了**（它就是「碰墙」那个形态的来源）；
`hy3-x` ⛔ 本来就不是免费档（**0.05x**，比 T1 的 0.03x 还贵）⇒ 无派发角色。
⇒ **T0 存在的唯一理由就是薅 hy3 的免费额度**，⛔ 不再是「免费档序列」。

`hy3` 免费期**延长至 `2026-09-30 23:59`** —— 旧数据记「08-31 止」，
⇒ 今天 `promo_active('hy3')` 会返回 False、**白白跳过一个还免费的档**、多付 T1 的 0.03x。

⚠️ **`max` 只验证了「被接受」，⛔ 没验证「想得更多」**：同一道推理题实测
`minimal` 1384 / `high` 1130 / `max` **653** reasoning_tokens ——
**非单调，max 反而最少、最快**（10s vs 22s/31s，三档答案都对）。
与 `deepseek-v4-flash-0731` 六档空转同一形态。⛔ 别当成「更高=更深」；
⭐ 但它免费且不报错 ⇒ 按用户指示取最高档，代价为零。

⚠️ `t0_still_free` / `t0_now_billed` 那套**保留** —— 它是给 **hy3 自己 09-30 到期**用的，
⛔ 不是只为 hy4 写的。

### ⭐ T1 从单池变三池 —— 「T1 单池」已知弱点关闭

`deepseek-v4.1-flash` 现在：`codebuddy-code` + `volcengine-agent-plan` + `bailian-token-plan`。
两家都是 2026-09-15 当天新上，各自实测（⛔ 不靠转述）：

| provider | 结果 |
|---|---|
| `volcengine-agent-plan` | 直连 **200**，回显 `deepseek-v4-1-flash`（点变横杠） |
| `volcengine-coding` | **404 UnsupportedModel** ⇒ ⛔ 没有，别写进池 |
| `bailian-token-plan` | **429 套餐本周额度耗尽** ⇒ **存在且有权限**，只是钱包没量 |

🔴 **429 / 403 / 404 三态要分清** —— 同一个百炼端点上：`deepseek-v4-flash` 是 **403 无权限**、
假 id 是 **404 不存在**、本模型是 **429 额度**。⛔ 别一律当「不可用」。

百炼那份带**限时夜间 5 折**（22:00–08:00）⇒ 已进 `DISCOUNT_WINDOWS`，
用例钉住「深夜排到池首 / 白天回轮换首位 cb」。

### 🔴 百炼整套餐额度耗尽 ⇒ T3 当下没有落点

5 个模型同一条 `429 ... token-plan 1-week quota has been exhausted`，
**09-16 09:32 UTC（北京 17:32）重置** ⇒ 是**套餐级**不是单模型级。

⇒ **T3（`qwen3.8-max` 单池在百炼）现在升上去没有落点**，会直接跳 T4（1.62x）。
这正是 09-10 记下的那条单池风险，2026-09-15 真的咬到了。已进 `poolQuotaState`。

### 🔴 `mai-code-1.1-flash` 进屏蔽名单

⚠️ 它与名单里已有的 `mai-code-1-flash-picker` 是**两个 id** ——
⛔ 别以为屏蔽了 picker 就连带屏蔽了它。此前它只在散文里标着「不建议」（垫底 81.5 分），
⭐ **那拦不住任何东西**，跟 `glm-latest` 那次同一个教训。
⇒ 守卫当场抓到它还列在「可用异族评审」清单里，已同步移除（11 个 → 10 个）。

### ⚠️ 「屏蔽」≠「从 pi 清单里消失」

用户要求把 5 个 copilot 型号从 pi 清单去掉，**实测做不到**：
`models.json` 与 `models-store.json` **两个都删过**，`pi --list-models` 照样显示
⇒ copilot 的清单是**运行时从服务端拉的**（`pi update` 帮助里的 "model catalogs"）。

⭐ 对照：`volcengine-agent-plan/glm-latest` **删得干净**（火山无 store 兜底）
⇒ 🔴 **同一个动作在不同 provider 上效果不同**，⛔ 别一概而论。

⚠️ 我中途推断错过一次：看到清单里没有 store 独有的 `claude-*`，就断定「清单读 models.json」
⇒ 据此以为删得掉。**删完照样显示**才证伪。⭐ 判据得是**删了之后清单变没变**，
⛔ 不是「清单长得像哪个文件」。

### 验证

`consistency-check` ✅ · `pipeline-test` **98** 用例 ✅ · `coverage-check` §2 **210 行 100%** ✅
⚠️ 交叉审查按 §2.6 被拦：`--due` 返回 exit 79（`main` 在 merge-only 下不是集成分支）⇒ 合并进集成分支时审整批。

---

## v11.9 (2026-09-11) — 复核闸门漏判「核实结果」，改名 `t0_still_free`

**用户一句「hy4 好像开始收费了，需要调整吗」把昨天写的一个洞问出来了。**

先说没坏的那半：**决策逻辑今天已经是对的** —— 窗口过期（`08-28~09-10`）+ 未核实
⇒ T0 本来就被跳过、落 T1，⛔ 不会误用一个开始计费的模型。

### 🔴 坏的那半：闸门只判「核过没」，不判「核出来是多少」

```python
def rate_reverified(model_id, dt=now()):   # ← 旧名，旧逻辑
    ...
    return days_between(rec['verifiedOn'], dt) <= RATE_RECHECK_MAX_AGE_DAYS
```

⇒ 用户核出 hy4 已计费（比如 0.5x）并**如实写进 catalog** 后，这道闸门返回 `True`
⇒ 把一个比 T1(0.03x) **贵 16 倍**的模型当免费档用。

⭐ **最坏的是：这个后果由「用户做了正确的事（去核实）」触发。**

### ⇒ 改名 `t0_still_free`，名字说出真正的谓词

判据 = 核实日期够新 **且** `credit == 0.0`。⛔ 不是「有没有核过」。

⭐ 这个洞的根子是**名字与角色错位**：函数叫「费率复核过了吗」，
但它在决策里承担的角色是「**这个档还免费吗**」。名字只覆盖了前半句，代码就只写了前半句。

**核实结果为已计费**时进 `t0_now_billed`，§7 报告 T0 已关闭；
⚠️ 若它的倍率**低于 T1**，那是【定档】问题 —— 要走同口径盲评，
⛔ 不因为「它以前是免费档」就继续当 T0 用。

### 验证

`consistency-check` ✅ · `pipeline-test` **89** 用例 ✅ · `coverage-check` §2 **197 行 100%** ✅
⭐ 关键用例两个方向都验过：`credit=0.5` ⇒ 落 T1 + 报告已计费；改成 `credit=0.0` ⇒ 用 hy4。
（把 0.5 改成 0.0 用例立刻变红 ⇒ 证明它真在测这个条件，⛔ 不是空转。）

### ⏳ 等一个只有用户能给的数

hy4-preview / hy3 / hy3-x 在 cb `/model` 面板上**现在的倍率**。
⇒ 写成 `{'credit': x, 'verifiedOn': 'YYYY-MM-DD'}`；`credit≠0` 时 T0 自动关闭。
⚠️ 在此之前决策是安全的（走 T1），只是**每次派发多花 0.03x** —— 如果它其实还免费。

---

## v11.8 (2026-09-11) — 快照后缀 id ⛔ 不是基名模型

**用户指出**：「`deepseek-v4-flash-0731` 与 `deepseek-v4-flash` 是两种模型」，
「`deepseek-v4-pro-0813` 和 `deepseek-v4-pro` 也是两种」。
**实测坐实，而且 pi 自己的配置里早就写着这句话**，是我的 skill 跟它矛盾：

```json
{"id": "deepseek-v4-flash-0731", "note": "... ⚠️ id 带 GA 快照后缀 -0731，⛔ 不是 deepseek-v4-flash"}
```

### 直连百炼端点的三态判据

| id | 状态 | 回显 | 同一句输入的 `prompt_tokens` |
|---|---|---|---|
| `deepseek-v4-pro` | ✅ 200 | `deepseek-v4-pro` | **8** |
| `deepseek-v4-pro-0813` | ✅ 200 | `deepseek-v4-pro-0813` | **87** |
| `deepseek-v4-flash` | ⛔ **403** | `Access to model denied` | — |
| `deepseek-v4-flash-0731` | ✅ 200 | `deepseek-v4-flash-0731` | **87** |
| `zzz-not-real` | ❌ 404 | `Model not exist` | — |

⭐ **403 / 404 / 200 三态本身就是判据**：403 = 存在但账号无权限、404 = 不存在。
⇒ 裸 `deepseek-v4-flash` 是**另一个真实模型**，⛔ 不是拼错。

⭐ **最硬的一条：同一句输入，`deepseek-v4-pro` 算 8 个 token、`-0813` 算 87 个。**
同一端点、同一请求体，差一个量级 ⇒ ⛔ 不可能是同一套服务。
⇒ 这是条**廉价同一性探针**，比模型自述可靠得多 —— `-0731` 自称 `gpt-4.1-2025-04-14`，纯属胡说。

### 🔴 我错在哪

`WALLET_PREF` 的语义是「(upstream, **该模型在这个 provider 上的真实 id**)」。
我把 `('bailian-token-plan', 'deepseek-v4-flash-0731')` 写进 `deepseek-v4-flash` 的池，
等于声称「它俩是同一个模型」。⇒ **派 T2 轮换到百炼时会落到另一个模型上**，而标题还写着 `dspF4`。

⇒ **百炼移出 T2 池**（它上面根本没有可用的 `deepseek-v4-flash`，403）⇒ **T2 只剩火山两套餐**。
连带：深夜折扣用例改写（T2 已无可切的打折池）。

### 🔴 标题缩写也在说谎

`deepseek-v4-flash` 与 `-0731` **共用 `dspF4`**、`deepseek-v4-pro` 与 `-0813` 共用 `dspP4`。
⇒ 看到 `百炼-dspF4` 会以为跟 `火山C-dspF4` 是同一个模型只是换了钱包 —— **正是这套规范要防的东西**。
⇒ 改成 `dspF4@0731` / `dspP4@0813`。

### 新增守卫 §3l（两个分支都做过注入验证）

- 带快照后缀的 id（`X-NNNN`）⛔ 不得出现在 `WALLET_PREF` 里
- 快照 id ⛔ 不得与基名共用标题缩写

### ⚠️ `-0813` 继续禁用，但**理由换了**

原先是「它就是 v4-pro」—— 那条已被证伪。现在的理由是**按能力档禁**：
用户口径「v4-pro 这一档整体不要了」（v4.1-flash 同价 0.03x 更强）⇒ 该档的快照版一并禁用。
⚠️ 2026-09-11 用户确认。

⭐ 这个区别不是文字游戏：**理由错了，下次同类判断就会错**。
按「同一个模型」推，`-0731` 也该跟着 `deepseek-v4-flash` 走；按「按能力档」推则不会。

⛔ `deepseek-v4-flash-0731` **不在禁用之列** —— 未被点名，只是**尚未定档**：
显式 `--model` 可派，⛔ 不进任何档位的池（没有同口径盲评）。

### 验证

`consistency-check` ✅（+§3l）· `pipeline-test` **88** 用例 ✅ · `coverage-check` §2 **191 行 100%** ✅

---

## v11.7 (2026-09-11) — 免费档窗口过期 ⇒ 要求费率复核，⛔ 不直接跳过

**我昨天写的预测被证伪。** 记录里写「hy4 免费期 `08-28 ~ 09-10`，09-11 起清零」，
今天实测三个免费 id **照样秒回**：`hy4-preview` 7s · `hy3` 4s · `hy3-x` 3s。
⇒ 要么延期了（cb 有前例），要么**开始计费了**。

⚠️ **「答得动」⛔ 不等于「还免费」** —— 这两件事我昨天在同一句话里混过一次。

### 🔴 两头都不能赌

| 写法 | 后果 |
|---|---|
| 日期到了就跳过 T0 | 白付 T1 的 **0.03x**，而 0.00x 可能还在 |
| 闭着眼继续用 | 若已计费、**费率未知**，可能比 0.03x 还贵 |

⇒ 改成 **窗口过期后要求费率复核**：复核过（catalog 里该型号 credit 带当期日期）才当免费档用；
未复核则按 T1 起步，但把**仍探活通过**的型号记进 `t0_free_unverified`，
**§7 必须提示「本可省下 T1 的钱，请核一下面板」** —— ⛔ 不静默丢掉这个机会。

### ⛔ 费率这一项 agent 拿不到

试了三条路都不行：`codebuddy --help` 只给 15 个型号清单 · `providerData.rawUsage` 只有 token 计数 ·
问模型自己答「不知道」。（`codebuddy models` 不是子命令，会被当成 prompt，还顺手读了当前目录。）
⇒ 只在 cb 的 `/model` 面板里 ⇒ **这一项只能问用户**，已写进 catalog 免得下次再试一遍。

### ⚠️ 第一版逻辑写错，用例当场抓到

`continue` 写成了**无条件**的 ⇒ 「已复核」也照样跳过 T0。
⇒ `continue` 必须收进「未复核」那个分支里。

### 验证

`consistency-check` ✅ · `pipeline-test` **86** 用例 ✅ · `coverage-check` §2 **184 行 100%** ✅
⭐ 三条对照用例：窗口过期+探活通过 ⇒ **落 T1 且提示** / 费率已复核 ⇒ **T0 照常可用** /
窗口过期且探活也不过 ⇒ **⛔ 不提示**（没有「本可省钱」这回事）

---

## v11.6 (2026-09-10) — 失败形态分类 + T0 碰墙留在同 provider

**起因**：用户反馈 hy4 经常「碰墙」—— **允许你用，但派发后静默停 / 唤不醒，
Paseo 抓不到任何明确错误**。当时 agent 的动作是**换去 `pi/volcengine-agent-plan/glm-5.3-flash`**，
而用户要的是「基于 cb 换成 `deepseek-v4.1-flash`」。

### ⛔ 这不算特殊场景 —— 缺的是两条通用东西

**① 「无明确错误的无响应」这个失败形态没有被命名。**
原先只有 `quota_exhausted` / `probe_queued` / `failed_this_task` 三类，hy4 的形态**三者都不沾**
（探活当时是过的、也没有 quota 报错）⇒ agent 只能自己找叙事，把它当成「做砸了」，
走了【质量/成本升档】那条 —— 而那条**允许换模型族**，于是就换钱包了。

```python
FAILURE_SHAPES = {
  'no_response':     'availability',   # 🔴 派发后静默停 / 唤不醒（hy4 的典型形态）
  'quota_exhausted': 'availability',
  'probe_queued':    'availability',
  'bad_output':      'quality',        # ⭐ 有产出但不合格 —— 只有这一类才算「做砸」
}
```

🔴 **判据是「有没有产出」**。没产出 ⇒ 永远是可用性。
⭐ 并且**落到执行层**：`failed_paid_tiers` 直接按 `FAILURE_SHAPES.get(...) == 'quality'` 过滤，
⛔ 不是只写在注释里。反向验证把用户报的 bug 原样复现了 ——
去掉这个过滤后，**两次「没回复」直接把任务顶到 T3 `qwen3.8-max`**。

**② 「留在 cb」原先只是巧合，不是不变量。**
T0 只跑在 cb 上，而 cb 通道**本身是活的**（它刚把 hy4 的请求吞了）⇒ 换钱包**没有依据**，
只是 agent 手边最熟的动作。⇒ 新增 `provider_affinity`：T0 试过且失败 ⇒ 池内排序把 cb 提到最前，
**同档替代（peers）那一步也照样生效** —— cb 的 v4.1 拿不到但 cb 的 glm 可以时，落 cb 的 glm。

⚠️ **affinity 优先于折扣**，这是有意的取舍：「留在已知活着的 provider」压过「省一点钱」。
⚠️ 它只**重排池内顺序**，⛔ 不改档位、⛔ 不改模型；池里没有 cb 时自然回到轮换（已有反例用例）。

⭐ 写成不变量而⛔不是靠巧合 —— 现在 T1 恰好只在 cb，但**将来 T1 换人就丢了这个性质**，
而这正是本次要修的东西。⛔ 也没有为 hy4 写任何 `if`。

### ⚠️ 那次误判里，agent 侧也有一半

subagent 自己的复盘写得很准：「**用 skill 的通用阶梯覆盖了你的显式指令**。
skill 自己就写着 P1 显式优先——你已经给了降级目标，我不需要（也不该）按阶梯自己挑」。
⇒ 这一半不是 skill 缺规则。但把失败形态归对之后，它连「该升档」这个前提都不成立了。

### 新增

- 硬默认表加第 3 条：**先判失败形态，再决定换什么**
- §6 收割表加一行硬门控：**先判有没有产出**
- `consistency-check` §3k：失败形态表必须与 catalog 一致，**且必须被 `failed_paid_tiers` 读取**；
  `provider_affinity` 必须被池排序读取（两条都做过注入验证）

### 🔴 异构审查连开三轮 FAIL 才收敛 —— 每轮抓的都是**新的**东西

用 `bailian/deepseek-v4-flash-0731` 审 **diff 而不是整个文件**（Copilot 连续 3 次「带 tools 读 1093 行
SKILL.md」挂死：`gpt-5.5` 7 分钟 / `gpt-5.6-sol` **37 分钟** / deepseek **2h20m** 零输出，
而极小 prompt 基线 4s 秒回 ⇒ ⛔ 不是通道问题，是输入太大）。

**第 2 轮 FAIL ①：`FAILURE_SHAPES` 只读不写，而缺省会把升档入口清零。**
`shape` 是本次新加的字段，**历史/外部产生的失败条目不带它** ⇒ 缺省若落到可用性类，
`failed_paid_tiers` 恒 0 ⇒【质量/成本升档唯一入口】被**整条清零**，真做砸也升不了档。
⇒ 缺省改成 `'bad_output'`（**保留旧行为的那一侧**），只有显式标 `no_response` 的才排除。
⚠️ 我的 pipeline 桩产出 `shape`、所以 77 个用例全绿 —— **照自己的设计造 fake**，
正是 memory 里那条「fake 必须照真命令输出造」。已补用例：**不带 shape 的旧失败照样算做砸**。

**第 2 轮 FAIL ③：「不算做砸」如果不配封顶，就变成「原地无限重派」。**
⇒ 新增 `NO_RESPONSE_LIMIT = 2` + `dead_landings`：同落点连续无响应 2 次 ⇒ 该落点被排除，
T0 循环 / 主池 / 同档 peers **三处**都过滤。⚠️ 这正是旧 `failed_this_task` 存在的理由（「绕过会死循环」）。

**第 3 轮 FAIL ①：affinity 的依据我选错了。**
先写「进过 T0 分支」（太宽：免费期没开压根没发请求），再改「promo 有效」（还是太宽：
探活全挂时 cb 一个请求都没成功吞过）。⇒ 两版都被判「无证据的偏好」。
⭐ 真正的证据形态**就是用户报的那个**：hy4 被允许使用、派发出去、**然后静默停**
⇒ `cb_accepted_then_silent`（本任务失败记录里有 cb 落点的 `no_response`）。

**第 3 轮 FAIL ②：`failed_this_task → quality` 与新不变量打架。**
它是旧标记，注释原话「绕过会死循环」⇒ 语义含混，⛔ 我无法判定谁在写、写的哪种含义。
⇒ **故意不进 `FAILURE_SHAPES`**，落到缺省保持旧行为，并把含混性显式标成**已知迁移缺口**。
（并到 availability 会让旧的真做砸记录停止计数 —— 那正是第 2 轮被抓过的「清零」。）

**第 3 轮 FAIL ③：`probe_queued` 与 `no_response` 定义裂缝。**
⇒ 钉死：**派发前**探活未秒回 = `probe_queued`（⛔ **不进** `dead_landings`，排队会自己散）；
**派发后**静默停 / 唤不醒 = `no_response`（**进** `dead_landings`）。

### ⚠️ 我这轮的两个操作失误

**① 补丁脚本中途崩溃 = 全无落盘，但我照着 ✅ 打印以为落了两条。**
脚本的 `write_text` 在最后，中途 `TypeError` ⇒ 前面的 ✅ 只在内存里。
后一个脚本又删掉了 `t0_touched` 的赋值与声明、留着使用点 ⇒ NameError 炸出来才发现。
⇒ ⭐ **每个补丁脚本跑完必须 grep 落盘结果，⛔ 不能只看 ✅**。

**② 守卫硬匹配了一行字面。** §3k 原本断言 `"FAILURE_SHAPES.get(f['shape']) == 'quality'" in S`，
我把它改成 `f.get('shape', ...)` 之后守卫立刻**假红**。⇒ 改成判「赋值表达式里是否出现 FAILURE_SHAPES」，
并加了两条新断言（缺省必须是 `bad_output`、必须有 `NO_RESPONSE_LIMIT`/`dead_landings`）。

### 验证

`consistency-check` ✅（+§3k 三条）· `pipeline-test` **83** 用例 ✅ · `coverage-check` §2 **181 行 100%** ✅
异构审查 **VERDICT: PASS**（第 4 轮，仅剩 2 条非阻断观察，其中措辞不一致那条已改）

⭐ 关键对照用例（一个字段变化就测得出归类对不对）：
`no_response`×2 **停在 T1** / `bad_output`×2 **升到 T3** / **不带 shape 的旧失败照样算做砸** /
`no_response` 同落点 2 次 **该落点被排除** / 仅 1 次 **⛔ 不排除** /
cb 接活后静默 ⇒ 同档替代**留 cb** / 仅探活排队 ⇒ **⛔ 无 affinity**

⭐ 关键对照用例：`no_response`×2 **停在 T1** / `bad_output`×2 **升到 T3** —— 一个数字变化就能测出归类对不对。

---

## v11.5 (2026-09-10) — T1 换成 `deepseek-v4.1-flash`（0.03x）

**起因是用户的一个观察：「有的 agent 没优先用 4.1 flash，而是优先用了 glm 5.3 flash」。**
不是漏写优先级 —— 阶梯里写的就是 glm。但那个决定建立在**一个错数字**上，而且**价格也变了**。

### 🔴 两条依据同时被推翻

**① 「首次有效率 1/3」是 n=3 的坏运气。** 补测 3 题 × 4 轮：

| | 有效 | 率 |
|---|---|---|
| concurrency | 4/4 | 100% |
| kafka | 3/4 | 75% |
| lru | 3/4 | 75% |
| **合计** | **10/12** | **83%** |

p=0.83 时「3 次里 ≤1 次有效」的概率约 **7.7%** —— 不常见但会发生。
⭐ **n=3 不足以支撑排他性结论**，尤其当结论会否掉一个更便宜、能力不弱的候选。

**② 倍率同日从 0.06x 降到 0.03x。** 用户两张 `/model` 面板截图相隔约一小时，
`deepseek-v4.1-flash` 从 **0.06x → 0.03x**，面板里的**位置也上移了**（从最末移到 `hy3-x` 之后）。
⭐ **cb 倍率有时效，⛔ 快照不能当常量用** —— 定档前先重新看一眼面板。

⇒ 现在它是 **`glm-5.3-flash`(0.06x) 的一半价**；折算 83% 有效率后等效 **0.036x**，
仍比 glm 单发便宜约 **40%**。⇒ **T1 在价格上就已经成立**，⛔ 不必依赖能力那半边论证。

### 🔴 T1: `glm-5.3-flash` → `deepseek-v4.1-flash`

能力侧另有支撑：同渠道两臂完整拉丁方 34.2 vs 32.3，**LRU 与并发两题 4 个朝向全胜**
（Kafka 反向且翻转 ⇒ 该题不可分）。

⚠️ 我提了两点代价，用户确认后照做，**两点都用机制兜住**：

**代价一：T1 从三池变一池**（v4.1-flash 只在 cb，400 权威清单确认火山/百炼都没有）。
⇒ `glm-5.3-flash`（三池）降为 T1 的 **`TIER_PEERS`**。cb 撞额度时落 glm，⛔ 不必升 T2(0.17x)。
glm 仍然是 T1 可用性的实际来源。

**代价二：17% 的失败不是报错，是「看着像正常输出」的垃圾**（实测一次 3988 字、正文带
`<｜｜DSML｜｜>` 内部标记）。⇒ 新增 `OUTPUT_VALIDATION_REQUIRED`，并且**算进决策结果**：

```python
requires_output_validation = model in OUTPUT_VALIDATION_REQUIRED
```

⛔ **不是只声明一个集合** —— 那是「规则只写在散文里」的变体，跟 `glm-latest` 那次同一个错。
现在它是派发结果的一个字段、§7 会打出来、§6 收割表有对应硬门控行；
§3j 守卫钉住「只声明不读取」这种写法（已做注入验证：把那行改成 `False` 立刻报警）。

### 🔴 换 T1 当场开出两个洞，都是校验抓到的

**① `--provider volcengine-coding`（不给 model）会把火山没有的型号派过去。**
火山在 `EXEMPT_PROVIDERS` 里 ⇒ `validate()` **对豁免 provider 不校验 model**，拦不住。
旧 T1 `glm-5.3-flash` 火山有，所以这个洞是**换 T1 那一刻才出现的**。
⇒ 新增 provider×model 错配检查，判据取 `WALLET_PREF`（该型号的真实池），⛔ 不是猜。
⭐ 而且不是直接报错：先在**同档**里找该 provider 真有的落点（⇒ 落 `glm-5.3-flash`），
记入 `tier_substitutions` 并在 §7 报告；同档也没有才停（如 `--provider github-copilot`）。
⚠️ 这跟「⛔ 不擅自替换成相近模型」不冲突 —— 那条针对用户**显式给了 model**的情况。

⭐ **教训：换阶梯成员时必须重扫「谁家有它」。** 池子数不是附属信息，
它决定了「显式指定 provider」这类既有用法还成不成立。

**② `ENTRY` 里并发两类「跳过 T1」的依据被直接推翻。**
旧依据是「并发题 v4-flash(T2) 35 > glm(T1) 31」⇒ 跳过 T1。
但 4 臂拉丁方里**并发题新 T1 是 37.5、T2 是 30.5，+7 分且 4 朝向全胜**
⇒ 跳过 T1 变成「既贵 5.7 倍又更差」。已改回 T1 起步。

⚠️ `algorithm` / `perf` **保留** T2 起步，但标注了依据**已不指向当前 T1**
（旧依据比的是 v4-flash 对 **glm**，⛔ 没比过 v4.1-flash）⇒ 待补测。

### ✅ 免费档今天仍然活着 —— 规则没错，是措辞会被读错

用户观察「Hy4 preview 看起来今天仍然在免费」。实测三个免费 id **全部秒回**：
`hy4-preview` 6s · `hy3` 8s · `hy3-x` 4s。

这与记录**不矛盾**：hy4 免费期是 `08-28 ~ 09-10`，**含 09-10 当日**，今天正是最后一天。
旧措辞「`09-10 hy4 止`」容易被读成「今天已经没了」⇒ 已改成显式写出区间和「含当日」。

🔴 **判据永远是探活，⛔ 不是面板上的 `x0.00`** —— 那是**价格**；赠额耗尽后价格仍显示 0，
表现是**排队 / 不回复**而⛔不是报错。§2 的 T0 分支本来就先 `promo_active()` + `probe_ok()`
⇒ **09-11 会自愈**，⛔ 不必按日期硬改代码。

### 验证

`consistency-check` ✅（新增 §3j）· `pipeline-test` **71** 用例 ✅ · `coverage-check` §2 **152 行 100%** ✅

---

## v11.4 (2026-09-10) — `deepseek-v4.1-flash` 定档完成

**结论：⛔ 不进阶梯。拦住它的不是能力，是可靠性。**

| | v4.1-flash | glm-5.3-flash（T1 在位） |
|---|---|---|
| cb 倍率 | **0.06x** | **0.06x**（同价） |
| 三题均分（同渠道两臂拉丁方） | **34.2** | 32.3 |
| 逐题 | LRU 33.5 ✅ · 并发 35.0 ✅ · Kafka 34.0 🔴 | 29.0 · 32.5 · **35.5** |
| **首次产出即有效** | **1/3** | **3/3** |

同价、能力不弱（LRU 与并发两题 4 个朝向全胜），本来该顶掉 T1。
**是首次产出有效率 1/3 把它挡在阶梯外** —— 首次失败的形态是
`<｜｜DSML｜｜ calls>` 内部工具标记泄漏进正文、响应塌成几百字符。

⇒ 留在 cb 白名单，显式 `--model` 可派；🔴 **派它必须校验产出，⛔ 不能只看 exit 0。**

### 🔴 官方口径「超越 V4-Pro」⛔ 未被实测支持

4 臂拉丁方：v4.1-flash 36.0 / v4-pro(cb) 33.6 / v4-pro(火山) 33.4 / v4-flash(火山) 32.8。
但**两题的第一名在四个朝向里都翻转** ⇒ 四臂**互相不可分**，⛔ 那 2.4 分读不成「更强」。
「比 V4-Flash 便宜」是真的。⇒ 官方说法一半真、一半没证据。

### ⭐ 跨口径校正臂：同模型跨通道差 **0.2 分**

v4.1-flash 只在 cb、v4-flash 只在火山 ⇒ 比较**按构造必然跨通道**。
`deepseek-v4-pro` 在两边各跑一份当校正臂：cb 33.6 vs 火山 33.4。
⇒ harness 差异可忽略，跨通道比较是成立的。

### 🔴 位置偏好实测：4 臂 **5.2 分/40**，比臂间总差还大

拉丁方下每个位置的臂构成完全相同 ⇒ 各位置均值的偏离**就是纯位置效应**。

| | A | B | C | D |
|---|---|---|---|---|
| 4 臂 (n=8) | **36.8** | 34.4 | 33.0 | **31.6** |
| 2 臂 (n=6) | **34.5** | 32.0 | — | — |

两臂那 **+2.5** 与 09-08 独立测到的完全对上 ⇒ 不是噪声，是评委的稳定倾向。

🔴 **推论：历史上任何「单朝向」或「位置逐题轮换」的结论，差距小于 5 分的都该当「未测出」处理**
—— 包括 `h2hEval_20260828` 的 102 vs 98。「轮换」只分摊偏好，⛔ 不消除，也测不出幅度。

### ⛔ 4 臂只移 2 位是无效去偏

`{臂0,臂2}` 会共享位置集 `{A,C}`、`{臂1,臂3}` 共享 `{B,D}` ⇒ A 位红利整组送给前两臂。
**n 臂就得跑 n 个循环移位**，每臂在每个位置恰好一次。
（09-09 那次的坑是「逆序对奇数臂的正中间是恒等变换」，这次是它的同族问题。）

### 🔴 我这轮的三个错

**① 臂位分配跟错了目标。** 四臂里两臂给了同一个模型（v4-pro 两通道），
却**没给 T1 的 `glm-5.3-flash` 留位置** —— 而定档要回答的正是「能不能顶掉 T1/T2」。
臂位是照「控混淆」分的，⛔ 没照「要回答的问题」分。用户一问 glm 就得现补一臂。

**② 拿错了尺子。** 我说「两臂差 1.9 < 位置偏好 2.5，所以只能算不弱于」——**错**。
A/B 对调已把位置偏好从臂均值里**消掉**，它⛔不是该估计的噪声底。
该看配对差的离散度（sd≈4.4，几乎全来自 Kafka 那次 −6）。
⇒ 立得住的是**逐题方向一致性**，⛔ 不是总平均那 1.9 分。

**③ 同一件事有两处写死份数。** 改了 rubric 的「四份 / A.txt~D.txt」，
却漏了 `run-judge.sh` 里**驱动 prompt** 的同一句 ⇒ 两臂题里评委去找不存在的 C/D，
六格的 `why` 全在解释「文件不存在」。A/B 仍各自拿到真分数 ⇒ 数字可用，
但这是**我改一处、忘另一处**。已改成按目录实际文件数生成。

### 🔴 旧 id `deepseek-v4-flash` 在 cb 上：调得通，但跑的是谁**测不出来**

- ✅ 假 id 的 400 正文给出**服务端权威清单**（15 个），`deepseek-v4-flash` 与 `kimi-k3-2` 都**不在**其中
- ✅ 但 `--model deepseek-v4-flash` 仍返回 200 有正常输出
- 🔴 `requestModelId` / `providerData.model` / `requestModelName` 全回显 `deepseek-v4-flash`
  ⇒ **这三个字段是请求回显，⛔ 不是运行值** —— 本例自证：它们回显了服务端清单里没有的 id

⇒ ⛔ **不派旧 id**。不需要先解开「是别名还是仍在服役」，
**「不确定跑的是谁」本身就够构成不派的理由**。

⭐ 方法：**派一个假 model id，400 报错正文里直接附权威清单** —— 比 `list_models` / `--help` 都硬。
⚠️ 错误信息常比正常输出信息量大。

### 🔴 用户确认禁用 `deepseek-v4-pro`（2026-09-10）

用户依据：「Deepseek-V4.1-Flash 能力强于 v4 pro，价格还差很多，没有必要使用 v4 pro 了」。

⚠️ **能力那半句⛔未被本轮实测支持** —— 4 臂拉丁方里 v4.1-flash 36.0 vs v4-pro(cb) 33.6，
但两题的第一名在四个朝向里都翻转 ⇒ 两者**不可分**。
⭐ **价格那半句是硬的**：`0.06x` vs `0.51x` = **便宜 8.5 倍**。⇒ 决定成立，依据落在价格上。

**实现方式：进 `BLOCKED_MODELS` 四个 provider 全写，⛔ 不动 LADDER。**

`validate()` 撞屏蔽型号走 `report_blocked_model_and_stop()` —— 是**停下来回到用户**，
⛔ 不是自己挑个替代悄悄继续。这正对应用户「不允许 agent 自己派发」的字面要求。
（百炼那份 id 带 `-0813` 后缀 ⇒ 漏一个 key 就是一个绕过口，与 `glm-latest` 宁可写重同一个理由。）

⚠️ **连带后果**：cb 的折扣集现在只剩 `deepseek-v4-pro` ⇒ **cb 折扣对阶梯已无作用点**。
⛔ 不要因此删掉 `DISCOUNT_WINDOWS` 的 cb 条目 —— `deepseek-v4.1-flash` 若确认继承峰谷折扣就会复活。
pipeline 里两条「非高峰/周末 T2 落 cb」的用例已被换代推翻，改成断言新不变量
（**cb 打折也进不了 T2，因为池里没它**），并补一条「cb 折扣集不含 glm-5.3-flash ⇒ 不改 T1 落点」。

### 🔴 连带：T3 从 `deepseek-v4-pro` 换成 `qwen3.8-max`

禁用 v4-pro 后，把它留在 `LADDER` 里是**两个都不能选的坏选项**：

| 方案 | 为什么不行 |
|---|---|
| 留着 v4-pro，靠 §6 `validate()` 拦 | §5 **先** `first_available(pool)` **再** §6 `validate()` ⇒ 会真的**探活五个池**才被拦（异构审查 gpt-5.5 抓到） |
| 改成「撞 T3 就停」 | 会把 **T4 的 `kimi-k3-1` 永久掐断** —— `i` 走不到 3，升档链在 T2 之后断掉 |

⇒ 换落点，⛔ 不是砍档。`qwen3.8-max` **本来就是 T3 的 `TIER_PEERS`**
（换位盲评 99.5 vs 102.0 /120，差 2.5 < 同轮 A 位偏好 2.5 ⇒ 判同档），直接顶上，档位定义没动。

**连带改动**：`WALLET_PREF` 的 v4-pro 四池整块移除 · `TIER_PEERS` **清空**（主落点升上来了，本档不再有同档替代）
· cb 折扣集**清空**（唯一成员就是 v4-pro）· 速查表三行 · pipeline 6 条用例前提失效后重写。

🔴 **已知弱点（写下来，不藏）**：T3 从**四池轮换**降为**一池**（只有百炼）。撞限额直接升 T4（1.62x），
⛔ 中间没有缓冲。⇒ 待办：测 `qwen3.8-flash` 或 cb 的 `minimax-m2.7`(0.19x) 能否补 T3 第二池。

⚠️ `LADDER` 里它的费率列写 `None` 是**故意的** —— 百炼是 token 套餐、这个 id 的 credits 倍率⛔未测。
⛔ 不许填个数字凑齐（逻辑只读 `LADDER[i][0]`，费率列纯文档）。

### 🔴 新增一层 `BLOCKED_MODELS_ANY_PROVIDER`（全局型号禁用）

异构审查第二轮又开两枪，两条都是真路径：

| # | 路径 | 为什么 provider-keyed 表拦不住 |
|---|---|---|
| ① | `--provider github-copilot --model deepseek-v4-pro` | 屏蔽表按 provider 建键，**没列过的 provider 结构上永远拦不住** |
| ② | 只给 `--model deepseek-v4-pro`，**不给 provider** | §1 是 `if explicit_upstream is not None: validate(...)` ⇒ **P0 整段不执行** |

②的后果实测出来了：它要到 §5 `first_available()` **之后**才被收尾的 `validate()` 拦
⇒ **用户明令禁用的型号被真派到 cb 探活了一次**。反向验证拿到了证据：
移除新加的那道拦，断言立刻报 `🔴 被禁型号在拦下之前已被探活 ['codebuddy-code/deepseek-v4-pro']`。

⇒ 「不允许 agent 自己派发某型号」是**全局**陈述，就得落在**全局那一层**：

```python
BLOCKED_MODELS_ANY_PROVIDER = {'deepseek-v4-pro'}   # 与 provider-keyed 表【正交】
```

**位置试了三次才对**：

| 放哪 | 结果 |
|---|---|
| §1 最前 | ⛔ 把 `--provider deepseek` 的「provider 已停用」和 review 冲突的**真实原因盖掉**了（三条既有用例被判成「型号被屏蔽」） |
| 只在收尾 `validate()` | ⛔ 拦得住但**已经探活过了** |
| ⭐ `validate()` 里放在 DISABLED **之后**、白名单之前 + §5 探活**之前**再拦一道 | ✅ |

⇒ 要求是「**⛔ 不许真去请求它**」，⛔ 不是「最先报错」。这两件事被我混了一轮。

**测试侧**：桩给 `first_available` 加了探活记录，新增 `no_probe` 断言 ——
只断言「被拦了」测不出它拦在探活前还是探活后。用例 64 → **66 条**，§2 覆盖 135 行 **100%**。

⛔ §3i 守卫同时钉住：全局禁用的型号**不得留在** `LADDER` / `WALLET_PREF` / `TIER_PEERS` 里
（三条断言逐个做过注入验证，全部报警）。

⚠️ 同类坑第三次：那个键我先放进 `catalog.whitelist`，而 whitelist 里**值为 list 的键会被解析成
「某 provider 的允许清单」** ⇒ 报出「provider `blockedModelsAnyProvider` 没有渠道缩写」。
⇒ 挪到顶层。**说明键混进数据表**这个形状已经踩了三次（versionlessAliases / tierPeers / 这次）。

### 🔴 异构审查抓到一个真绕过口：`volcengine-chat`

我把 v4-pro 写进 `BLOCKED_MODELS` 时列了四个 provider，**注释还写着「四个 provider 全写」——数错了，是五个**。
`volcengine-chat` 在 `EXEMPT_PROVIDERS` 里 ⇒ 显式 `--provider volcengine-chat --model deepseek-v4-pro`
本来能直接绕过 P0。gpt-5.5 一轮就抓出来了。

⇒ 补了 **§3h 结构性守卫**：屏蔽覆盖面由 **catalog 的 `providers` 表**推出来，
⛔ 不再靠人肉列举（同 §3g 的思路）。已做反向验证：删掉 `volcengine-chat` → 两条断言同时报警；恢复 → 绿。

### ⚠️ 同一个坑踩第二次：emoji 开头的键漏过 `_` 前缀过滤器

`tierPeers` 加了个 `🔴 emptied_20260910` 说明键（值是 str），解析器按 `not k.startswith('_')` 过滤
⇒ 把它当成 peer 条目，`v['peers']` 直接 `TypeError`。**0909 在 `versionlessAliases` 上已经踩过一次**。

⇒ 两处都改成**判值的形状**（`isinstance(v, dict) and 'peers' in v`），
并把归档条目移出 `tierPeers`（历史值与生效值同表，会被解析成还在生效）。

⚠️ 顺带自查出一颗哑弹：`ladder` 集合的正则是 `\('([a-z0-9.\-]+)',\s*[\d.]+\)` ——
**要求费率是数字**，而我刚把 T3 写成 `None` ⇒ `qwen3.8-max` 整个漏出 `ladder`，
「TIER_PEERS 的键必须是阶梯模型」那条断言就空转了。已改成接受 `None`，并做了正反两向验证
（注入 `qwen3.8-max` 不报警 / 注入 `deepseek-v4-pro` 报警）。

### ⭐ cb 费率表全量核实（15 项，与 400 权威清单逐个对上）

| id | 倍率 | | id | 倍率 |
|---|---|---|---|---|
| `hy4-preview` | 0.00x | | `minimax-m3` | 0.25x |
| `hy3` | 0.00x | | `minimax-m2.7` | **0.19x** |
| `hy3-x` | **0.05x** | | `kimi-k3-1` | 1.62x |
| `glm-5.3` | 0.79x | | `kimi-k2.7` | 0.57x |
| `glm-5.3-flash` | **0.06x** | | `kimi-k2.6` | 0.52x |
| `glm-5.2` | 0.79x | | `deepseek-v4-pro` | 0.51x ⛔ 已禁用 |
| `glm-5.1` | 0.79x | | `deepseek-v4.1-flash` | **0.06x** |
| `glm-5v-turbo` | 0.71x | | | |

⚠️ **`hy3` 与 `hy3-x` 的 label 都是「Hy3」**，倍率却是 0.00x vs 0.05x ——
和 `hy4-preview` / `hy4-preview-x` 同形。🔴 **派发认 id，⛔ 不认 label。**

⚠️ `minimax-m2.7` 只要 **0.19x**，比 T2 的 `deepseek-v4-flash`(0.17x) 略贵、比 T3 便宜一大截
⇒ **若测出能力够，它是 T2/T3 之间的空档候选**。⛔ 但没实测不许进阶梯。

### ⚠️ 篇幅混淆没消掉，只是标注了

Kafka 那题 v4.1-flash 是 glm 的 **3.5 倍**篇幅（40850 vs 11616 字）。
rubric 里钉了「长度不是质量信号」一节，但⛔ 不能假定它生效 ——
读分时须核 `why` 讲的是不是具体技术点。这条仍是本轮结论的已知弱点。

---

## v11.3 (2026-09-09)

**京东云停用 → 阿里云百炼接入**，钱包①层从「固定顺序」改为**多池轮换**（火山两套餐 / 百炼 / codebuddy）。

### ⛔ 京东云停用（归档，不删）

用户：**额度用尽，消耗太快不划算**。⚠️ 但「不排除以后还会用」⇒ 整块 provider 配置归档到
`~/.pi/agent/providers-disabled/jdcloud-joyagent.json`（600 权限），里面带 `_howToRestore`：
怎么塞回 `models.json`，以及**恢复后必须同步改哪些字段**的清单。

⚠️ 连带处理：`deepseek-v4-pro` 的首选是京东，拿掉就**悬空**了。
先改回火山（把 pro 挪出 cb 的原始动机是「0.51x 烧 credits 太快」，火山按月套餐同样满足），
随后被本轮的三池轮换取代。

⚠️ 顺带修了两个校验脚本对 `jdcloud-joyagent` 的**硬编码**——provider 会停用，
硬编码会让脚本自己 `KeyError` 崩掉。改成遍历 catalog 里实际存在的键，并新增
「已停用 provider ⛔ 不得残留在 WHITELIST / WALLET_PREF」断言。

### ⭐ 阿里云百炼 Token Plan 接入

| 项 | 值 |
|---|---|
| endpoint | `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` |
| pi provider | `bailian-token-plan` |
| CLI | `bl 1.22.0` + 9 个 `bailian-*` skill |

🔴 **endpoint ⛔ 不是通用的 `dashscope.aliyuncs.com`** —— Token Plan 有独立域名，
由 `bl auth status --output json` 的 `base_url` 得到。照通用文档配会连不上。

**只用 4 个文本模型**（用户指定）：`deepseek-v4-pro-0813` · `deepseek-v4-flash-0731`
· `qwen3.8-max` · `qwen3.8-flash`。图像三个（`qwen-image-3.0-pro` · `wan2.7-image-pro`
· `wan2.7-image`）⛔ 不进 pi，走 `bl image`。

⚠️ **`deepseek-v4-pro-0813` 不在 `/models` 目录里但可用** —— 又一次印证
「目录里没有 ≠ 不能用」（上一次是火山的 `glm-5.3-flash`）。⇒ 判断可用性只能直接发请求。

🔴 `compat.supportsDeveloperRole: false` 是**实测得出**（传 `role=developer` 报
`not one of ['system','assistant','user','tool','function']`），⛔ 不是照抄火山猜的。

### 🔴 钱包①层：固定顺序 → 多池轮换

用户明确：**火山 / 百炼 / codebuddy 一样，就是轮换关系**；加百炼正是因为**火山与 cb 这个月量不够**。
⇒ catalog 的 `modelProviderPreference` 从 `{first, then}` 改为 `rotation` 列表，
文档不再把先后钉死，改成「用哪个由**哪个还有量**决定，撞限额换下一个」。

### ⭐⚠️ 折扣窗口 —— 时段策略回来了，但形态不同，而且**两家窗口不一样**

**百炼**：每晚 **22:00 – 次日 08:00**，`deepseek-v4-pro-0813` / `deepseek-v4-flash-0731`
/ `qwen3.8-max` credits 减半（⛔ `qwen3.8-flash` 不在内）。

**codebuddy**（用户补充后才知道）：`Deepseek-V4-Flash` / `Deepseek-V4-Pro`
**工作日 09:00-12:00 / 14:00-18:00 是高峰原价，其余全部时段 5 折**。

🔴 **我第一版把规则写成「夜间优先百炼」，是错的。** codebuddy 一周 168 小时里
**只有 20 小时原价**，覆盖面远大于百炼那 10 小时/天。
⇒ 正确规则：**轮换时优先【当前正在打折】的那家**；同为打折或同为原价则保持原轮换序。

🔴🔴 **这直接撞上 2026-08-16 废止的时段策略，必须说清区别。**
旧策略有害的原因是 `is_night()` 会**把按任务类型选出的高档模型无条件冲掉**。
本条 `discountWindows` ⛔**不碰模型选择**——档位由阶梯定完之后，
才用它在【**同一模型**的多个池】之间挑一个（⚠️ 更广义的「档内就该挑便宜」见下一节）：

```python
# ═══ 5. 选 provider ═══
pool = sorted(pool, key=lambda x: not is_discounted_now(x[0], x[1]))
#   🔴 这里是【选池】不是【选模型】—— model 上一段已定死，本段⛔不许碰
```

### 🔴 用户纠正：不变量是「⛔ 不跨档下调」，⛔ 不是「折扣不许影响选模型」

我写过一句总结：「折扣影响**从哪家买**，⛔ 不影响**买哪个**」。用户指出这是**过度概括**——
如果 `glm-5.3-flash` 与 `deepseek-v4-flash` 能力打平而前者更便宜，那当然该选便宜的。

⇒ 真正的形状是**两步**：
**第 1 步 选档位**（按任务类型 + 做砸记录，⛔ 价格不参与）→
**第 2 步 档内选落点**（⭐ 就是要挑便宜的）。
2026-08-12 那个 bug 的错误⛔不是「让价格参与了」，而是**跨过档位边界往【下】选**。

⚠️ 从事故提炼规则时最容易犯的错：把**肇事动作**（"价格参与了选择"）写成禁令，
而不是把**被违反的不变量**（"不得跨档下调"）写成禁令 —— 前者会顺手禁掉正当优化。

⇒ 加了两道守卫：`consistency-check.py` 断言**时段判断⛔不得出现在「选模型」段落**；
`pipeline-test.py` 加折扣用例，含关键反例「深夜 T1 档位不被冲掉」「深夜免费档仍是 T0」。

✅ **验证了守卫测得出坏**：构造 3 个违规（时段判断混进选模型段 / 折扣清单
与 catalog 不符 / 百炼 id 丢快照后缀），**3/3 全部抓住**。

### 🔴 hy4 免费期我记错了（用户更正）

原记「免费至 **09-12**」是错的：实际 **2026-08-28 ~ 09-10**，而且是**每日赠送免费额度**，
⛔ 不是一段连续免费期。⚠️ **当日额度用完会被限，表现是【不回复】** ⇒ 必须**主动换模型**，
⛔ 不要干等。这让「派长任务前先探活」从建议变成硬纪律。

### ⭐ 火山**两个套餐**也是轮换关系（用户 2026-09-09）

`volcengine-coding`（`…/api/coding/v3`，8 模型）与 `volcengine-agent-plan`
（`…/api/plan/v3`，13 模型）是**两个独立额度池**（不同 key、不同 baseURL）。
阶梯三档 `deepseek-v4-pro` / `deepseek-v4-flash` / `glm-5.3-flash` 在两边 **id 完全相同**
⇒ 撞限额直接换 provider，⛔ 不用改 model 名。两者都进 `WALLET_PREF` 轮换。

🔴 **顺带推翻一条躺了很久的警告**：skill 里写着
「`volcengine-agent-plan` 上 `--variant` 静默失效，要控思考强度得走 `volcengine-coding`」。
实测把范围钉死了 —— 经 pi 传 `thinking.type`，**两个 endpoint 都真生效**：
coding `disabled/enabled` = `reasoning_tokens` **0 / 155**，agent-plan = **0 / 165**。

⚠️ 那次失效的**主语是客户端，⛔ 不是 provider**：opencode 走 `@ai-sdk/openai`
（Responses API），参数白名单把 `thinking` 丢了；pi 走 `openai-completions`，两条路径不同。
`--variant` 本来就是 opencode 的 flag，警告里却只留下了 provider 名。
⇒ 已把这条限定到 opencode（SKILL §3.2e · routing §7 · catalog 四处）。

### 🔴 屏蔽名单 `BLOCKED_MODELS`（用户 2026-09-09 点名）

火山 Doubao 全系 + `ark-code-latest`；Copilot 的 `gpt-5-mini` / `gpt-5.3-codex` / `gpt-5.4-mini`
/ `gemini-3.5-flash` / `gemini-3.6-flash` / `mai-code-1-flash-picker`。

⛔ **与白名单/豁免集正交，放在 `validate()` 最前面** —— 放在豁免判断之后就对豁免 provider 失效了
（`github-copilot` 正好在豁免集里）。

### ⛔ 「从配置里删掉」≠「屏蔽」

我先把它们从 `~/.pi/agent/models.json` 删了，`pi --list-models` 也确实少了几个。**然后实测**：

```
pi -p --provider github-copilot --model gpt-5-mini '只输出：OK'   →  OK
```

**删了照样能调。** pi 会回落 `models-store.json`，而它按 etag **自动刷新**，改它也会被冲掉。
⇒ Copilot 侧**唯一有效的屏蔽是派发层的 `BLOCKED_MODELS`**；那 6 个条目已**还原**
（删了没用，反而丢掉 `thinkingLevelMap` 等元数据）。
⚠️ **火山两个 provider 删得掉** —— 它们只在 models.json 里定义、无 store 兜底 ⇒ 保留移除 + 归档。
**同一个动作在不同 provider 上效果完全不同**，⛔ 不能推广。

🔴 **顺带证伪一条躺了很久的记录**：「Claude 全族已从 Copilot 通道移除，**实现方式**是
models.json 覆盖 store」—— 实测 store 里 `claude-*` **8 个全在**，是 GitHub 服务端返回
**400 `model_not_supported`** 拦的。**结论没错（调不到），归因错了。**
⚠️ 归因错的代价是：我以为「照这个办法能屏蔽别的模型」，于是照做，做完还以为成了。
⇒ ⛔ **判据是「真发一次请求返回什么」，⛔ 不是「列表里有没有」。**

### 🔴 `glm-latest` 进 `BLOCKED_MODELS`（用户 2026-09-10）

用户：「`glm-latest` 这种就该屏蔽，不该使用」。

⚠️ 我先前只在 §3.1 散文里写了句「⛔ 无版本别名不许直接派」，还把它从缩写表移除了 ——
**那拦不住任何东西**。`validate()` 里没有它，派它照样放行。
🔴 **跟 cb 换代时我只加注释不移白名单，是同一个错**：规则必须落到**会被执行的那一层**。

⚠️ 豁免 provider（火山/百炼/Copilot/claude）⛔ **不能靠「从白名单删掉」来拦** ——
它们本来就不枚举模型 ⇒ 只能靠 `BLOCKED_MODELS`。

⭐ `glm-latest` 在 **两个火山 provider 都列**：它目前只存在于 `agent-plan`，
但**万一将来 coding 也上**，漏一边就是口子。⇒ 屏蔽名单宁可写重，⛔ 不要赌「那边没有」。

### 🔴 §3g 结构性守卫：⛔ 不靠人记得屏蔽

扫 `~/.pi/agent/models.json` 里**所有**以 `-latest` / `latest` 结尾的 id，逐个断言已进
`BLOCKED_MODELS` ⇒ **将来新上的别名会自动被抓**，⛔ 不依赖我下次还记得。
（当前全机只有一个：`volcengine-agent-plan/glm-latest`；cb 服务端 15 个里没有 `-latest`。）

⚠️ **两类别名都要拦，⛔ 别只想着无版本那种**：

| 类型 | 例 | 危险度 |
|---|---|---|
| 无版本别名 | `glm-latest` | 一眼看出要解析 |
| **陈旧版本别名** | cb 的 `deepseek-v4-flash` → v4.1 | 🔴 **更危险** —— 带着版本号却指向另一版本，**标题会说谎** |

### ⚠️ 加守卫时又踩了自己的过滤器

新加的说明键 `🔴 versionlessAliases` 是个 **str**，而既有的屏蔽名单比对守卫按
**`_` 前缀**过滤非 provider 键 ⇒ 那个 emoji 开头的键没被过滤掉，
`set(str)` 把它**拆成了一百多个单字**，报出一堆乱码差异。
⇒ 过滤判据改成**值的类型**（只有 `list` 才是 provider 清单），⛔ 不靠键名前缀约定。

✅ `pipeline-test` 70 → **73 条**；§3g 破坏场景验证通过。

### 🔴 cb 换代（2026-09-10）：`deepseek-v4-flash` → `deepseek-v4.1-flash`，`kimi-k3-2` → `kimi-k3-1`

用户指出 cb 已经**直接换代**。我先前记的「旧 id 实测仍可调 ⇒ legacy 保留」**归因是错的**。

**权威判据不是 `list_models`，是【假 id 的 400 报错正文】**：

```
400 model [zzz-fake-model-12345] service info not found
Currently supported models for your account:
  - hy4-preview … - deepseek-v4-pro - deepseek-v4.1-flash     （共 15 个）
```

那 15 个里**没有** `deepseek-v4-flash` / `kimi-k3-2`，而请求它们**不报错**
（真·假 id 会报上面那个 400）⇒ 它们是**别名**，服务端静默解析到新型号。

### 🔴🔴 `providerData.model` ⛔ 不是运行值 —— 我上一条记错了

我先前拿 `providerData.model` 回显请求值当成「没有静默回退」的证据，还写进了 memory。
**那是错的**：假 id 会被 400 拒绝（证明它不是**无脑**回显），
⛔ 但这并不证明它会**解析别名** —— 两个是不同性质，我把它们混成了一个。

⇒ 真结论：`providerData.model` 记的是**客户端请求值**，对别名不做解析。

### 🔴🔴 陈旧版本别名比无版本别名更危险

`glm-latest` 这种**没有**版本号，一眼能看出要先解析。
而 `deepseek-v4-flash`(cb) **带着版本号却指向 v4.1** ⇒ 标题会写 `cb-dspF4` 而**实际跑 dspF4.1**，
**标题在说谎** —— 正好击穿刚立的标题规范存在的意义。
⇒ ⛔ 这类别名必须从白名单**移除**，⛔ 不能像我第一版那样只加个注释了事。

### 连带改动（守卫一条条逼出来的）

| 改 | 内容 |
|---|---|
| cb 白名单 | 去 `deepseek-v4-flash` / `kimi-k3-2`，加 `deepseek-v4.1-flash` / `kimi-k3-1` / `hy3-x` |
| `LADDER` T4 | `kimi-k3-2` → **`kimi-k3-1`** |
| `WALLET_PREF` T2 | ⛔ **去掉 cb** ⇒ **只剩三池**（火山×2 + 百炼） |
| `WALLET_PREF` T4 | 键与落点都改 `kimi-k3-1` |
| ⚠️ **折扣窗口** | cb 折扣集去掉 `deepseek-v4-flash` ⇒ 🔴 **T2 从此吃不到 cb 峰谷折扣**（cb 上没这模型了）。`deepseek-v4.1-flash` 是否继承折扣 **⛔ 未确认**，⛔ 先不加 |
| 缩写表 | `kimi-k3-1` → `k3.1`；`deepseek-v4.1-flash` → `dspF4.1` |

⚠️ **「T2 吃不到 cb 折扣」这条是守卫逼出来的** —— 两条折扣用例突然变红，我才发现
改白名单会连带改掉折扣行为。⛔ 换代不是「换个 id」那么简单。

`pipeline-test.py` 63 → **70 条**；✅ 3 个破坏场景全抓
（别名加回白名单 / T4 退回旧 id / cb 加回 T2 池）。

### 🔴 子会话标题必须带「渠道-模型」后缀，且**必须带版本号**（用户 2026-09-10）

原话：**「未来会上 dspF4.1，差距会很大」** —— 标题里看不出版本，回头翻 agent 列表
就分不清哪个产出是哪代模型做的。

```
{原标题} · {渠道}-{模型缩写}
```

| 例 | 说明 |
|---|---|
| `[Dev] 修 CRM 登录三态 · 百炼-dspF4` | 百炼的 `deepseek-v4-flash-0731` |
| `[Dev] 拆 transport 插件 · 火山C-dspF4` | 火山 **coding** 套餐 |
| `[Dev] 同上换池 · 火山A-dspF4` | 火山 **agent-plan** 套餐 —— ⛔ 两个独立额度池必须能分出来 |
| `[Review] 审 diff · Cop-gpt5.5` · `[Dev] 兜底 · Cld-son5` | 审查 / LAST_RESORT |

⭐ **GA 快照后缀故意不进缩写** —— 渠道前缀已把它区分开（`百炼-dspF4` 就是 0731 那份）。
🔴 ⚠️ **例外**：某渠道**同时**暴露同代两个快照时必须追加 `@快照`（`百炼-dspF4@0731`），
⛔ 否则两个 agent 标题一模一样。

### 🔴 顺带禁掉「无版本别名」

守卫上线**即抓到一个真缺口**：`glm-latest` → `glmLatest` **缩写不出版本**。
根因不是缩写起得差 —— 是 **`glm-latest` 本身就是无版本别名**，按定义带不出版本。

⇒ 不是给它编个缩写，而是**禁止直接派它**：派发前必须先解析成具体型号
（火山 `glm-latest` / `glm-5.2` → **`glm-5.3`**）。
⚠️ 对比：`hy4-preview` **可以**派 —— `preview` 是它真实 id 的一部分，缩写 `hy4` 仍带版本。
⚠️ 连带更新「Agent Plan 独有 5 个」那行 —— 屏蔽 3 个 + 禁派 `glm-latest` 后，**只剩 `kimi-k3` 可派**。

### `consistency-check.py` §3f

标题是派发时才拼的，脚本查不到运行时标题 ⇒ 能查的是**缩写表有没有缺口**（缺一个，派发时就只能瞎编或漏标）。四条断言：
每个可派发落点都有缩写 · 缩写必须含数字 · 无版本别名⛔不得有缩写 ·
🔴 **同渠道内⛔不许两个模型撞同一缩写**（否则标题重名）。

✅ **5 个破坏场景全抓**（删模型缩写 / 缩写去版本号 / 无版本别名加回表 / 删渠道缩写 /
同渠道两模型撞缩写）。
✅ 已把现存 agent `f0319a69` 改名验证规范可落地：`… · 百炼-dspF4`。

### ✅ 决策树完整性：新增 `coverage-check.py`，§2 覆盖率 **100%**

`pipeline-test.py` 只保证「**跑过的**路径行为对」，⛔ 不保证「**所有**路径都跑过」。
新脚本用 `sys.settrace` 收 §2 伪代码被走到的行，实测揪出两处：

| 发现 | 处理 |
|---|---|
| 空 `--model` 的报错分支**从没被测过** | 补用例（空串是输入错误，⛔ 不是「没指定」） |
| `review` 分支里有一段**死代码** | 第 1 段的 pre-P0 检查已把非 Copilot provider 拦掉，那个 `elif` 永远为假 ⇒ 改成 `assert` 记录不变量 |

🔴 **死代码在「当规范读」的伪代码里有害** —— 读的人会以为拦截发生在那里。

⚠️ 写这个脚本第一版用**启发式**判续行（「上一行以逗号结尾」），被**行尾注释**骗过
（`('a','b'),   # 注释`）⇒ 5 行误报。改用 `code object` 的 **`co_lines()`** 取
「真正能产生 line 事件的行」，⛔ 不猜。

✅ 验证它测得出坏：塞**运行时不可达**分支 → 抓住；复现真实事故形状（前面拦过的条件后面又写一遍
`elif`）→ 抓住。⚠️ `if False:` 抓不住（会被常量折叠、`co_lines` 里根本没有）—— 那是 linter 的活。

⇒ 现在是**三个校验**：`consistency-check`（跨文件数据）· `pipeline-test`（行为）· `coverage-check`（完整性）。

### 🔴 查了一遍「测评结果都进 skill 了吗」—— 结果是**没有**

用户一问才发现三处漏：

| 漏的东西 | 后果 |
|---|---|
| `qwen3.8-max` 那轮的分**只写在散文里**（`tierPeers.evidence` 的字符串） | agent 扫 `blindEval` 字段时**一个数都看不到** |
| 5 个 Copilot 型号**连 `models` 条目都没有** | 分只躺在顶层轮次记录里，按 model id 查不到 |
| `h2hEval` / `jdVsVolcEval` 用的是**臂标签**（`v4flash` / `jd`）⛔ 不是 model id | 同上，按 model id 查不到 |

⇒ 全部补齐：per-model `blindEval` + `blindEvalByRound`、轮次记录加 `_armToModel`。
现在 **6 轮结构化分数 · 23 个模型有数值字段**，按 model id 全查得到。

⚠️ **`deepseek-v4-pro` 一个模型就有 4 轮分**（86 / 96 / 104 / 102，口径各不相同）
⇒ 加 `blindEvalByRound`，⛔ 别拿单个 `blindEval.total` 去对所有轮。

### 🔴 §3e 守卫：测评必须落成【按 model id 查得到的数值】

⛔ 只写进散文不算 —— 同 `feedback-change-the-data-not-the-prose-rule`：**数值字段权重远高于散文**。

⚠️ 写这个守卫踩了两个坑：
- **`e` 撞车**：模块级 `e` 是错误列表，我拿它当循环变量 ⇒ `AttributeError`。
- **假设只有一种结构**：六轮记录实际有**五种**（`scores_120` / `totals_120` /
  `scores:{model:{...total}}` / `scores:{task:{arm:n}}` / 臂标签）⇒ 改成写 `round_totals()` normalizer，
  **认不出就返回空，⛔ 不猜**。

✅ 用 4 个破坏场景验证测得出坏（删 per-model 字段 / total 对不上 / 删 `_armToModel` / 新轮次模型无条目）：**4/4 全抓**。

### ✅ 5 个未知 Copilot 型号已评分（用户口径「做个参考」⇒ ⛔ 未改阶梯）

| 档 | 模型 | /120 | LRU | 并发 | Kafka |
|---|---|---|---|---|---|
| ⭐ 第一 | `grok-4.5` | **109.5** | 33.5 | 37.5 | 38.5 |
| ⭐ 第一 | `grok-4.6` | **106.0** | 33.5 | 35.5 | 37.0 |
| 🔸 第二 | `gemini-3.7-flash` | 97.0 | 28.5 | 36.0 | 32.5 |
| 🔸 第二 | `gemini-3.8-flash` | 93.0 | 29.5 | 29.5 | 34.0 |
| ⛔ 垫底 | `mai-code-1.1-flash` | 81.5 | 27.5 | 23.0 | 31.0 |

🔴 **⛔ 不可与既有 /120 榜横比** —— 本轮走 `pi -p -nt -ns -nc`（**无 agent 系统提示**），
旧榜是 **Paseo agent** 跑的。⭐ 只在这 5 个之间成立。

⛔ **同档内不可分高下**：`grok-4.5` / `grok-4.6` 在 **lru 与 kafka 两题的第一名换位后翻转**，
总分差 3.5 与实测位置偏好（A 位比 E 位高 **2.83**）同量级。gemini 两个同理（差 4.0）。
✅ **垫底那条是稳的**：`mai-code-1.1-flash` 三题全负、落后 11.5 分。

### 🔴 多臂盲评的方法坑：**逆序去不掉正中间那个的偏**

两个朝向用了 `ABCDE` + `EDCBA`。但**逆序对奇数臂的中位是恒等变换** ——
`mai-code-1.1-flash` 两轮都坐 C，**它的分从头到尾没被去偏**。
（本轮它垫底 11.5 分、三题全负 ⇒ 结论仍成立；换个差距小的场景就会出错。）
⇒ **多臂盲评的朝向要用【循环移位】，⛔ 不要用逆序。**

⚠️ 顺带固化一条判据：**换位后各题第一名是否翻转** —— 翻转就是「不可分」，
⛔ 不管总分差了多少。只有「差距 > 位置偏好幅度 **且** 方向不翻」才敢排先后。

⚠️ 跑第一轮时 `grok-4.5` 只回了 54 字的「我打算怎么做」⇒ 三题都加了**统一输出指令**
（直接给答案、⛔ 不要计划/摘要/澄清问题），五个模型完全相同。

⚠️ 还踩了个老坑：`local model=$1 tkey=$2 o="$B/raw/${model}--${tkey}"` ——
**同一条 `local` 里后面的赋值看不到前面的**，15 个任务全写进同一个 `--.txt` 互相覆盖。
⇒ 拆成多条 + 加空参数断言。（同 `feedback-bash-integration-patterns` §声明顺序）

### 🔴 拆开两种「换档理由」+ 新增 LAST_RESORT（用户 2026-09-09 决策）

第 3 轮异构审查抓到一个**真实的语义冲突**（⛔ 不是文档漂移）：
`model-routing.md` §8 降级链允许 `glm-5.3-flash → deepseek-v4-flash`（T1→T2）、
`deepseek-v4-flash → cb/deepseek-v4-pro`（T2→T3）这样**因拿不到而换档**，
而我这轮给 T3 新加的分支却是「停止并报告」—— **同一条链里 T1/T2 升档、T3 停止**，前后不一致。

根因是**两种换档理由从来没被拆开写**：

| | 触发 | 允许 |
|---|---|---|
| **质量/成本换档** | 本任务上一档**做砸过一轮** | 向上一档。⛔ 不得跨档**下调** |
| **可用性换档** | 该模型在**所有 provider** 都拿不到 | ⭐ 只许**向上** + **必须报告**。⛔ 永远不向下 |

⇒ 不变量「⛔ 不得跨档下调」防的是**质量回退**，「升档需做砸」防的是**成本虚高**——
两条都在质量/成本轴上，⛔ 跟「拿不拿得到」是**正交**的。
向下换档在两个轴上都错：既是质量回退，又是拿「拿不到」当借口。

**新的完整顺序**：四池轮换 → 同档替代（`TIER_PEERS`，⭐ 优先于升档，同档能落就别涨价）
→ 可用性升档 `tier+1` 回到第一步 → 阶梯到顶（T4）仍拿不到 → **`LAST_RESORT`**。

### 🔴 `LAST_RESORT` = `claude/claude-sonnet-5` @ `max`

**第 4 轮异构审查在这块新逻辑上抓到 4 个真 bug**（⛔ 不是文档漂移）：

| # | 问题 | 根因 |
|---|---|---|
| 1 | LAST_RESORT **覆盖了用户显式 `--thinking`** | `thinking = lr_thinking` 无条件赋值 —— `'max'` 本该只是**默认值** |
| 2 | LAST_RESORT 只查 `provider_available('claude')`，⛔ 不查 model | `claude` 在**豁免集**里 ⇒ `validate()` 对它⛔不校验 model ⇒ 「claude 活着但 sonnet-5 拿不到」会一路放行到派发才炸 |
| 3 | §6 收尾还留着**第二套可用性机制** `if not provider_available(): downgrade()` | 它⛔不受「不得跨档下调」约束，能把 §5 刚升上去的档位**降回低档**，还绕开「显式 provider ⛔不许被换掉」，且不写 `availability_escalations` ⇒ **静默质量回退** |
| 4 | 短任务落 LAST_RESORT 会拼出 `cli + claude` | `claude` 在 provider 表里**只有 Paseo `create_agent` 一条路径**，⛔ 没有 `claude -p` |

⇒ ③ 的修法是**删掉**那套机制，⛔ 不是给它加约束：
**可用性从此只有一套真源**（§5 的 `first_available` → 同档替代 → `tier+1` → LAST_RESORT）。
⚠️ 两套可用性信号并存，本身就是 bug 的温床 —— 它们会互相矛盾。

另外把 `availability_escalations` 从「只记 to」改成 **`(from, to, why)` 三元组** ——
只记 to 的话 §7 打不出「原档位 → 逐级」那句话，「必须报告」会变成**假实现**。

### 🔴 反残留守卫（§3d）—— 别再靠人眼扫漂移

**第 5 轮：守卫自己被审出两个缺口，修完后它一次抓出 17 条**（人眼四轮才抓 13 条）：

| 缺口 | 后果 |
|---|---|
| 只扫 `SKILL.md` / `model-routing.md` | ⛔ **漏了第三份** `model-catalog.json` —— 补缺口时**范围也要补全** |
| 「唯一入口」之外的同义写法没覆盖 | `做砸才升` / `才升 K3` / `做砸过一轮才` 全漏 |

⚠️ 但 17 条里 **7 条是误报** —— 它把**描述 2026-08-12 那个旧 bug** 的句子
（"`is_night()` 把做砸才升上去的高档模型换成低档…"）当成了**在立规则**。
⇒ 加 `DESCRIPTIVE` 排除：句子里有 `is_night` / 「那个 bug」/「旧写法」= **在讲过去，⛔ 不在规定现在**。
收窄后正好 **10 条真残留**，全部修完。

🔴 **守卫收窄了两次，每次都要重新证明它还测得出坏** —— 已验证（2/2、4/4）。
⚠️ 收窄一个误报多的守卫，很容易顺手把真阳性也关掉。

### 第 6 轮：`review` 那道门把三个洞一起开着

第 3 段的条件写的是 `if task_type == 'review' and explicit_model is None:` ——
**`--model X` 一加，整段绕过**，三个洞同时开：

| 洞 | 后果 |
|---|---|
| `--free × review` 冲突被**静默吞掉** | `want_free` 自己也带 `and explicit_model is None` ⇒ 两道门同时失效 |
| `review --model gpt-5.5` **掉进普通阶梯** | 去试 `codebuddy-code/gpt-5.5` —— cb 根本没有它 ⇒ 报「白名单不匹配」，用户看到的原因完全不对 |
| `review --provider 火山 --model X` | **绕过 provider 冲突判断**，直接派到实施族上（⛔ 违反异构不变量） |

⇒ 条件收成**只看 `task_type`**；`--free` 判断改用 `args.free`（⛔ 不用带门的 `want_free`）；
显式 model 保留、显式非 Copilot provider 报**专用**冲突
（`report_review_provider_conflict_and_stop`）——
⛔ 复用 `report_conflict_and_stop` 会给出「白名单不匹配」的**错误解释**。

⚠️ **同一个 `and explicit_model is None` 门被复制到了三处**，这才是根因，⛔ 不是三个独立 bug。

### 第 6 轮其余

- 🔴 `model-routing.md` 把**顶层 `pi` 写进了豁免集** —— 它是**宿主**，豁免它等于让
  `pi/jdcloud-joyagent/...` **整条绕过 upstream 校验**。⇒ 改成「校验对象是 `split_provider()` 后的 upstream」。
- 附录 P0「不在白名单的 model id 一律不派」是**绝对句**，会误伤 `claude` LAST_RESORT 与 Copilot 审查
  ⇒ 限定为「对白名单 provider」。
- `toK3Condition` 补【质量/成本升档】限定（否则与「T3 全不可用可升 T4」直接打架）。
- §3d 守卫**再补一类同义写法**：`做砸一轮才升`（⛔ 无「过」字）此前漏检 —— 这是 reviewer
  指名的**具体盲区**，⛔ 不是泛泛建议。
- `kimi-k3-2` 补进 `modelProviderPreference`（只有 cb 一家，但**显式列出**）；
  `concurrency_diag` 补进「跳 T0 从 T2 起步」的四类清单。
- LAST_RESORT 的 `channel` 守卫现在是**防御性**的（review 改顶层后，自然路径已没有
  「cli 规模走到 LAST_RESORT」）⇒ 测试用 `force_cli` 旋钮保持可测。

`pipeline-test.py` 50 → **53 条**。

### 第 5 轮其余修复

- **`review` 硬例外静默覆盖显式 `--provider`**：注释写「只定模型」，代码却 `upstream, model = ...`。
  ⇒ 只在 `explicit_upstream is None` 时给默认；显式指定了别的 provider ⇒ **报冲突**。
  ⚠️ 它还会让后面的显式落点可用性检查**查错对象**（查 copilot 而非用户点名的那个）。
- **删掉 §6 `downgrade()` 留下的缺口**：显式 `--provider` 路径**完全没有可用性检查**了
  ⇒ 补 `first_available([(upstream, model)])`，拿不到就**停止**（⛔ 不静默换 provider、⛔ 不升档）。
- `architecture` 起步档在 routing §3.3 还写着 T2（真源是 **T1**）；
  「跳过 T0」被写成「直接从 T1 起步」（⛔ 两件事：跳 T0 是一回事，付费起步档按 `entryTier` 定）。
- 「T0 拿不到 → 落 T1」缺 `--free` 限定（显式 `--free` 拿不到必须**停止**，⛔ 不静默转付费）。
- **「兜底」一词撞车**：`opencode` 是**执行适配器**的兜底（怎么跑），`LAST_RESORT` 是**可用性降级链**
  的最后一站（跑哪个模型）—— 两个都叫「兜底」，已分别改名。
- 「白名单之外一律禁止」是**绝对句**，与 `claude` 走豁免集的 LAST_RESORT 打架 ⇒ 限定为「对白名单 provider」。

`pipeline-test.py` 45 → **50 条**。


四轮审查里 **13 条** 是同一形状：**改了权威定义，但速查表 / 用例表 / 降级链 / 历史段没跟着改**。
校验脚本只比**结构化数据**，markdown 表格和散文它一个都不看 ⇒ 漂移全积在那里。

⇒ `consistency-check.py` 新增 §3d：对**当前规则两份**（`SKILL.md` / `model-routing.md`）做
「主题命中 + 缺限定语」扫描，并断言 LAST_RESORT 四件套（provider 串 / thinking / 常量 / catalog）三份一致。

✅ **上线即抓到 6 条审查没列出的残留**（其中 2 条是**误报** —— 它把「与官方 API 的**价格对比**」
小节也算成了路由断言）。⇒ 收窄成「必须同时命中**主题**和**在断言路由角色**」才报。
⚠️ **守卫误报多了会被忽略**，跟漏报一样有害。
✅ 收窄后用 4 个破坏场景验证仍**测得出坏**（4/4）。



用户原话：**「我们本质是为了不占用 claude 套餐额度，但是不能不干活，所以 sonnet 5 max 作为最后兜底」**。

⇒ 这句话同时给出了**目的**和**它的边界**：
- 整套钱包体系（火山两套餐 / 百炼 / codebuddy 轮换、折扣窗口、阶梯）存在的**唯一目的**
  就是 ⛔ **不占用 Claude 套餐额度**（留给主会话）。
- ⛔ 但**「不能不干活」优先于「省额度」** ⇒ 到顶了宁可用它，也⛔不要停在半路。
- 🔴 走到这里 = **正在烧掉这套体系本来要保护的东西** ⇒ §7 输出**必须显著告知**，⛔ 不许静默。
- ⛔ 它⛔**不是 T5**，⛔ 不参与「做砸就升档」那条路径 —— **只有可用性耗尽才够得着**。

⛔ 连 `claude` 都不可用，才 `report_no_landing_and_stop`。

### ⛔ `deepseek/*` 官方 API 从「自动兜底」降为「手动路径」

它一直在 opencode 的 `disabled_providers` 里。写成自动兜底等于给了一条**假通道**——
真走到那一步会**失败**，⛔ 不是花钱。⇒ 改成：需用户明确接受现金开销 + 解除 disabled 后手动指定。

### 守卫

`pipeline-test.py` 33 → **40 条**，新增「向上换档」「不许向下」「同档替代优先于升档」
「到顶落 LAST_RESORT」「连 claude 都没有才停」「escalations 必须留痕」等用例。
✅ **6 个破坏场景全部抓住**（`tier -= 1` / 不记 escalations / LAST_RESORT 不查可用性 /
跳过同档替代 / 永不升档直接兜底 / LAST_RESORT thinking 降成 low）。

### ⭐ `qwen3.8-max` 定档：与 `deepseek-v4-pro` **同档**，落地为 `TIER_PEERS`

用户：「和其他模型一样啊，用来编码啊，qwen3.8-max 应该很强」（附 Arena 榜）。
⇒ 跑了一轮**换位盲评**（vs `deepseek-v4-pro`，两臂 thinking=medium、prompt 逐字相同）：

| 题目 | `qwen3.8-max` | `deepseek-v4-pro` |
|---|---|---|
| LRU（代码实现） | 25.5 | **33.0** |
| 并发诊断 | 36.5 | **38.0** |
| Kafka 架构 | **37.5** | 31.0 |
| **总分 /120** | 99.5 | 102.0 |

⇒ 差 2.5/120，**判同档（T3）**。新增 `TIER_PEERS`：**本档四个池全拿不到时**才换到它，
⛔ 主落点可用时不插队（credits 倍率还没测，没有价格依据）。
同时新增 `report_no_landing_and_stop()` —— 全拿不到就**明确停止**，
⛔ 不静默升档（升档唯一入口是做砸过）、⛔ 不静默降档。

🔴 **方法升级：每题跑两个朝向，把评委的位置偏好测出来。**
实测 **A 位平均比 B 位高 2.5 分**，与两臂总分差同量级 ⇒ ⛔ **单朝向盲评的名次不可信**。
✅ 本轮三题胜负方向换位后**全部保持**，方向是稳的。
⚠️ 回看 09-08 那轮（京东 vs 火山）：**A 位 3 战全胜**、京东占 A 位 2/3、只领先 4 分
⇒ 那 4 分很可能大部分是位置偏好。⛔ 不推翻其结论（原文已写明 4 分在噪声内），但机制清楚了。

⚠️ 评分表里加了**反冗长护栏**（本轮两份最大差 5.8×）。验证它有效：Kafka 题 qwen 写 99KB 赢了，
但 LRU 题 qwen 同样更长却**输 7.5 分** ⇒ 评委⛔没有单纯奖励长度。

⛔ **未测**：`qwen3.8-max` 与 `deepseek-v4-pro-0813` 在百炼的 credits 倍率
⇒ 【档内挑便宜】那一步还没依据。`qwen3.8-flash` 同样**未定档**（无实测）。

### 🔧 node 版本管理器被 PATH 屏蔽（本机修复，非 skill 改动）

`which node` 落到 homebrew 的 26.7.0 而非 volta。根因：`.zshenv` 已把 volta 放最前，
但 `.zprofile` / `.zshrc` 里的 `brew shellenv` 在其**之后**再次前置 homebrew，把 volta 挤到第 23 位。

⇒ ① 先 `volta install node@26.7.0` 让 volta 持有**同一版本**（⛔ 避免降到 volta 原 default 的 20.10.0）；
② 在两个文件末尾（`brew shellenv` 之后）加带标记的 `VOLTA_PATH_PRIORITY` 块重新前置；
③ `bl` 改由 volta 管（pin `node@26.7.0`），卸掉 homebrew 那份重复安装。
⚠️ homebrew 的 node 未卸（`brew uses --installed node` 为空，无依赖，但卸载属清理类操作需先 dry-run）。

catalog 6.1.0 → **6.20.0**。


## v11.2 (2026-09-08)

### ✅ 第四轮：重写生效，但校验脚本被证明是假绿 ⇒ 改成可执行测试

第四轮定向验证把 §3 用例表**逐条 trace** 了一遍，结论是**重写成功**：
显式 `--model` 不再被 T0/阶梯覆盖、显式 `--provider` 不再被换成 codebuddy、
`pi/jdcloud-joyagent + GLM-5.2` 在第 1 段被拦、review 按 `scope` 分流、T4/超 T4 行为正确。

但审查者做了一件我没做的事：**构造真实破坏场景去验证校验脚本本身**。
他复制一份改坏，跑我的 `consistency-check.py` —— **5 个场景全部 exit 0 假绿**：

| 破坏 | 为什么没抓住 |
|---|---|
| `channel = 'cli'` 写死 | 脚本只断言 `is_large_review` 这个**字符串**出现过，而注释里就有 |
| `ENTRY['algorithm']` 从 1 改 0 | 根本没校验入口档 |
| review 模型换成 `hy4-preview` | 根本没校验 review 赋值 |
| `normalize_provider` 直接 `return upstream` | 只检查函数名存在，⛔ 不看语义 |
| 新增一个未赋值变量 | 变量检查是硬编码小名单 |

🔴 **根因：查 markdown 里字符串存不存在，永远抓不住语义错误。**

⇒ 新增 `scripts/pipeline-test.py`：**直接把 §2 的 ```python 块抽出来、包成函数、注入桩、执行**，
跑 17 条用例断言落点（拦截 4 条 / 放行 2 条 / 阶梯 6 条 / 审查 2 条 / 显式值不被覆盖 2 条 / 委派 1 条）。
**markdown 成了唯一真源，改坏它测试必红。**

✅ **验证了检测器本身**：用审查者那 5 个破坏场景实测，**5/5 全部抓住**（原脚本 0/5）。
⚠️ 这一步不能省——「测试通过」不证明测试有用，得证明它**测得出坏**。

顺带补：`consistency-check.py` 的钱包比对从「只比首选」升级到**全序 + 每个 provider 的真实 modelId**；
覆盖面改为如实说明（它只比 SKILL 与 catalog 的结构化数据，`model-routing.md` 只搜旧语残留，
⛔ 别把「三处一致」当成三份都做了结构比对）。

⚠️ **写这个比对时我第三次栽在正则上**：`split("'deepseek-v4-pro'")` 会在**键**和
**元组里的 modelId** 上都切一刀（两者字面相同），只截到第一个元组。加冒号才消歧。
前两次是「字符类漏 `_`」和「断言查实现字符串」。⇒ 三条都固化进脚本 docstring。

另修第四轮的两个未赋值变量：`failed_paid_tiers_in_this_task`（决定 T1~T4 边界）、
`agent_id`/`cwd`（收尾用，且 CLI 路径本来就没有 agent_id ⇒ 改成接 `execute()` 返回值，
CLI 走 `run_id`）。并校准两处措辞：`--free` 是**唯一**有标注的提前退出（不变量改成「除它以外」）；
review 是「**未显式指定时**默认固定 gpt-5.5」而非不可覆盖。

### 🔴 第三轮复审仍 FAIL ⇒ 停止打补丁，重写 §2 伪代码

三轮的形状说明问题不在单个 bug：

| 轮次 | ❌ | 构成 |
|---|---|---|
| 1 | 9 | 原始问题 |
| 2 | 8 | 4 条上轮修剩 + **4 条我修复引入** |
| 3 | 8 | 3 条文档残留 + **5 条同一个结构性问题** |

第三轮的 ❌1~5 其实是**一件事**：`§2` 伪代码从来不是一条自洽的管线。
它有 `goto` 跳过初始化、T0 提前 `return` 绕过 validate/clamp/memory、
显式 `--model` 被阶梯覆盖、显式 `--provider` 被 T0 换成 codebuddy、`scope` 用了却没赋值点。

**逐点打补丁每次都在别处开新洞** —— 这就是每轮都有「修复引入的新 bug」的机制。⇒ 重写。

**新 §2 的四条硬结构**：

1. ⛔ 无 `goto`、⛔ 无提前 `return`（只保留 `--free` 一处有标注的整任务转交）
2. 变量在第 0 段**全部初始化**，⛔ 后面不许凭空冒出新变量
3. 用户显式值存 `explicit_*`，**后续阶段只读不写**（`explicit_model` 全文只允许赋值一次）
4. 所有路径汇到同一收尾：`validate → channel → 可用性 → normalize → clamp → EXECUTE → 输出/记录`

### ⭐ 校验脚本重写：从「查字符串」升级到「查结构」

审查者指出它是**双重假绿**——硬编码 `~/.claude/skills/rift-dispatch`（验的是软链副本，
换台机器 clone 就验错对象）、且只做字符串存在性检查（`scope` 未定义时照样通过）。

新版：路径改为相对 `__file__` 定位；新增结构断言 ——
伪代码里⛔无 `goto`、⛔无顶层提前 `return`（**剥掉注释后**再判，
⚠️ 否则注释里写「⛔ 只赋值，不 return」会被误判，本轮踩过）、
`scope`/`channel`/`thinking`/`task_type`/`upstream`/`model` **必须都能找到赋值点**、
悬空函数名不得出现、`explicit_model` 只能赋值一次。

⚠️ 脚本 docstring 里固化了它自己的三条教训：正则字符类带 `_`、断言查性质别查实现字符串、
⛔ 别硬编码软链路径。

### 🔴 自查：第二轮修复自己带了两个悬空引用

派第三轮复审的同时自己先查，结果两条都实锤——**都是第二轮修复引入的**：

| 位置 | 问题 |
|---|---|
| `SKILL.md` 两处调用 | **`channel` 变量从未被赋值**，却在 `normalize_provider(upstream, channel)` 里用 |
| `SKILL.md` 两处调用 | **`pick_provider_for()` / `default_model_for()` 无定义**，纯悬空 |

根因：为了修「显式路径没做前缀规范化」，我临时造了两个函数名就用上了，没定义。

⇒ 重构掉，⛔ 不再靠新造函数：抽一个 `validate(upstream, model)`（model 允许为 None，
此时只校验 provider），P1 里 provider 与 model **各自独立判断**，只给其一时⛔不在 P1 补另一半，
而是继续走正常流程、在 P5b 末尾再 `validate()` 一次。`channel` 在新的 `CHANNEL:` 段按
「要不要看得见」显式赋值。

**⚠️ 校验脚本也暴露了一个设计问题**：它断言 `'args.model or args.provider' in S` ——
查的是**实现字符串**而不是**不变量**。我一重构写法，它就假失败。
⇒ 断言改成查性质：`validate()` 有定义、`if args.provider` 分支存在、
`validate(upstream, model)` 至少被调两次、`channel` 有赋值点、两个悬空函数名不得出现。

### 🔴 第二轮复审又 FAIL —— 8 个 ❌，一半是我上轮「只修了被点名那一处」

复审分类很说明问题：

| 类别 | 条数 | 说明 |
|---|---|---|
| **上轮修了一半** | 4 | 改了 `SKILL.md`，⛔ **没改 catalog 的机器字段** |
| **修复自己引入的新 bug** | 4 | 新伪代码有问题 |

第一类正是我上一轮**刚写进 CHANGELOG 的那条教训**——写完转头又犯。
上轮审查者原话就写了「同步更新 routing 附录和 catalog」，我只改了被点名的行。

**新引入的四个**：P1 只判 `args.model`（只给 `--provider` 时该 provider 完全没过 P0 校验，
且 `provider` 可能未初始化）；显式指定路径没复用自动分支的 `pi/` 前缀规范化；
`build_settings` 定义签名与模板调用不一致、未知 provider 静默放行、
`kimi-k2.7-code`（`thinkingOptions: null`）例外没覆盖；用例表漏了「免费档前提」。

⇒ 抽出 `normalize_provider(upstream, channel)` 给 P1 与 P5b **共用**；
`build_settings(full_provider, model, thinking)` 三参对齐、未知 root 直接停。

**⚠️ 我还把审查者的一条建议用过头了**：它说 catalog exempt 应「只列 `pi/volcengine-*` 这类可豁免上游」，
我就给所有键加了 `pi/` 前缀——但 `split_provider()` 拆出的 `upstream` 是**不带前缀**的，
校验写作 `upstream in EXEMPT`，加前缀反而全对不上。真正该做的只是**移除顶层 `pi`**。
顺带查出 catalog exempt 里还混着 `deepseek`（它在 DISABLED，⛔ 两者互斥）、且漏了 `codex`。

### ⭐ 新增 `scripts/consistency-check.py`

这轮反复栽在「同一条规则散落四处、只改一处」上，⇒ 把它变成可复跑的机械校验，8 组断言：
豁免集三处一致且 `pi`/`jdcloud`/`deepseek` 都不在里面 · 白名单三处一致 ·
钱包首选三处一致且 JD 必须用大写 modelId · 伪代码三个关键函数齐全且调用签名对得上 ·
审查按规模分流无残留 · `providers` map 已补首选 · pi 侧配置（无 claude、unsupported 标记、glm-5.3-flash）· JSON 可解析。

⚠️ 脚本第一次跑报了 3 条，**全是它自己正则写窄了**（`qmodel_38max` 的下划线没进字符类）——
已在脚本 docstring 里写明「报错先判是内容错还是正则太窄」。

### 🔴 异构审查（`pi/github-copilot/gpt-5.5`）抓出 9 个 ❌，其中 3 个会让派发直接失败

**❌1 白名单可被 `pi/` 前缀绕过。** `pi` 整体在 `EXEMPT_PROVIDERS` 里，但京东的 Paseo 串是
`pi/jdcloud-joyagent/<model>` —— 按顶层 `pi` 解析就豁免了，`pi/jdcloud-joyagent/GLM-5.2` 会绕过 JD 白名单。
⇒ 加 `split_provider()` 先拆 host/upstream，校验一律对 **upstream** 做；`pi` ⛔ 移出豁免集
（它是**宿主**不是钱包）。⚠️ 这是「白名单缺口」的第四种形状，前三种见 v11.1。

**❌2 自动升档会拼出不存在的 model id。** 阶梯里是小写 `deepseek-v4-pro`，而京东的 id 是
**`DeepSeek-V4-pro`**（大小写不同，实测点名小写返回「模型不存在」）。原 `WALLET_PREF` 只映射
provider 名，升到 T3 必然拼错。⇒ 改成 `(upstream, 该 provider 上的真实 modelId)` 二元组，
并按 provider 决定要不要加 `pi/` 前缀。

**❌3 `create_agent` 模板无条件传 `modeId`。** 而 pi provider 的 `availableModes` 为空 ——
**我自己派京东那个 bench agent 时就撞过这个错**（`Invalid mode 'bypassPermissions' for provider 'pi'`），
改了文档却没改模板。默认开发通道正是 Paseo 派 pi ⇒ 火山/京东落点会全部失败。
⇒ 加 `build_settings(provider)`：`pi/` 开头只传 `thinkingOptionId`。

**❌4~❌9（一致性）**：审查通道刚改成「大审查走 Paseo」但伪代码 P4 仍钉死 `pi -p`；
`deepseek-v4-flash` 的兜底链一边写「京东 → 官方」一边写「flash 不走京东」（已统一为**硬规则不走京东**，
兜底直接跳官方 API）；catalog 多处 `preferredProvider`/`paseo` 仍焊死 `codebuddy-code`，与新的
`walletPriority` 打架（已 deprecate 并加 `providerSelectionSource` 指向唯一真源）；
catalog 的火山清单缺 `glm-5.3-flash`；`whitelist.exempt.github-copilot` 仍以已废弃的 store 为真源；
以及本条目自己「四条证据其实是一条」和后文「四条独立证据」并存（已消除）。

**⚠️ 我在修 ⚠️1 时又错了一次**：`thinkingLevelMap` 的 **value 为 `null` 表示不支持该档**，
我第一版按 key 全列，把 `grok-4.5` 写成支持 `xhigh`（实际 `xhigh: null`）。审查者的原始判断是对的。
⇒ 表已按 value 非空重建，并加了「配置支持 ≠ 实测过」两列区分。

**新增派发路径用例表**（SKILL.md §3）——11 条可照着自查的输入→期望落点，
包括 `pi/jdcloud-joyagent/GLM-5.2` 必拦、T3 必须落大写 `DeepSeek-V4-pro`、大审查必走 Paseo。

**教训**：这轮 3 个功能性 bug 有个共同形状 —— **我改了文档，没改与之配套的可执行部分**
（模板、伪代码、字段）。⇒ 改路由规则时，要把「散文 / 伪代码 / 模板 / catalog 字段」四处一起过。


新增**京东云 JoyAgent 通道**（积分制第三个钱包），并限定只用 DeepSeek。

### ⛔ JD 云只使用 DeepSeek 系列

用户明确要求。落地方式是**给它一份自己的白名单**，⛔ 不放进 `EXEMPT_PROVIDERS`：

```python
WHITELIST = {
  'codebuddy-code':   [...],
  'qoderclicn':       ['qmodel_38max'],
  'jdcloud-joyagent': ['DeepSeek-V4-pro', 'DeepSeek-V4-Flash'],   # 🔴 只准这两个
}
```

⚠️ 关键取舍：它是独立钱包，本来按 §1 的分类该进豁免集（豁免 = 不校验模型）。
但「只用 DeepSeek」是**模型级**约束，豁免集给不了 —— 所以它进 `WHITELIST` 而非 `EXEMPT`。
平台另有 GLM-5.2 / GLM-5.1 / Kimi-K2.6 / MiniMax-M2.7 / qwen3.6-27b / qwen3.6-35b-a3b /
qwen3-vl-235 / JoyAI-LLM-Flash 共 8 个，**已在 `~/.pi/agent/models.json` 配好且逐个实跑通过**，
标记为 ⛔ 不派发 —— 留着是为保住实测结论，不是为了用。

### ⛔ 从 pi 的 Copilot 通道移除 Claude 全族

用户要求。理由清楚：**主会话就是 Claude，把 Claude 留在审查通道里，等于给自审留了个口子**——
异构不变量（§5）本来就禁止它，删掉比靠纪律拦更可靠。

🔴 **实现方式不是改 `models-store.json`。** 那个 store 带 `etag`/`checkedAt`，
会**按 etag 自动刷新**（本轮读到的清单已经和几天前不同：多了 `gpt-6-astra`/`grok-4.6`，
少了 `gemini-3.1-pro-preview`）⇒ 手改必被冲掉。
正确做法是**在用户自己的 `~/.pi/agent/models.json` 里显式定义 `github-copilot` provider** 去覆盖它。

⚠️ **代价要说清**：这样一来 Copilot 将来新增的模型**不会自动出现**，需要手工补进 models.json。
这是「可控但要维护」换「自动但不可控」。

✅ 三项验证：`pi --list-models` 零 claude · 点名 `claude-opus-5` 返回 `model_not_supported`
· 审查通道 `gpt-5.5` 仍正常返回。

⚠️ 顺带查明：store 目录里的 `gpt-5.4-nano` / `kimi-k3` / `kimi-k2.7-code` **本订阅实际不支持**
（API 返回 `model_not_supported`）⇒ 可用的是 **17 个**，⛔ 别按目录数以为有 20 个。

⚠️ 教训（与本轮 glm-5.3-flash 漏配同源）：**目录里有 ≠ 能用，目录里没有 ≠ 不能用。**
前者是这三个模型，后者是 glm-5.3-flash（别名不进 `/models`）。⇒ 判断可用性只能直接发请求。

### ⭐ 补配 `glm-5.3-flash`：火山一直就有，是我漏了

用户问「火山应该支持了 glm-5.3-flash，怎么没见到」。查实：**火山两个套餐都支持**，
回显 `model: glm-5-3-flash`。是 `~/.pi/agent/models.json` 里漏配了，⛔ 不是火山没有。

影响不小 —— `glm-5.3-flash` 是 T1 付费起步档，此前只挂在 cb(0.06x) 上。
现在它同时在**已付费套餐**里，按钱包优先级 T1 的 provider 首选改为 **volcengine-coding**。
⚠️ 这条是按同一钱包规则**推得**（用户只对 deepseek 两个型号做了指定），已在文档里标明是推断。

### 🔴 火山的 model id 大量是别名，⛔ 不能按字面理解

顺着上面查出来的，实测 `model` 回显：

| 请求 | 实际回显 |
|---|---|
| `glm-5.2` · `glm-latest` | **都是 `glm-5.3`** |
| `deepseek-v4-flash` | `deepseek-v4-flash-**ga-260731**` |
| `deepseek-v4-flash-260425`（preview 快照） | **`deepseek-v4-flash-ga-260731`** |
| `deepseek-v4-pro` / `-260425` / `-ga-260813` | 都只回显 `deepseek-v4-pro` |

⭐ **火山上 0425 那个 preview 快照已被别名到 GA** —— 显式点名要 preview，拿到的也是 GA。

⚠️ **`GET <baseUrl>/models` 的坑**：Coding Plan 可用（返回 **130 个 ARK 原始 id**），Agent Plan 返回 404。
但那 130 个是 **ARK 全量目录**，**别名不在里面** —— `glm-5.3-flash` 就查不到，可它明明能用。
⇒ ⛔ **不能拿 `/models` 判断某个 id 可不可用，只能直接发一次请求试。**
这正是我一开始漏配它的原因：我按配置清单和印象判断，没去试。

⚠️ 京东侧⛔不认 ARK 快照 id（返回「模型不存在」），也只回显请求名
⇒ 这条查快照的路在京东侧用不了，preview 问题在京东侧仍只有盲评那一条证据。

### 🔴 新增「钱包优先级」——与档位阶梯正交

用户 2026-09-08 定：**先花已经付过钱的，最后才动现金**。

| 顺位 | 钱包 | 性质 | 边际成本 |
|---|---|---|---|
| ① | 火山 Coding/Agent Plan · codebuddy credits | **已付费套餐** | ≈ 0 |
| ② | 京东云积分 | 流量包购买有优惠 | 已买入的积分 |
| ③ | DeepSeek 官方 API | 🔴 **现金，个人账户** | ⛔ 永远只做兜底 |

**关键是把两件事拆开**：**档位阶梯（§0）决定用哪个模型，钱包规则（§3.5）决定从哪个 provider 拿。**
以前这两件事被 catalog 里的 `escalation.rule` 焊死成 `cb/deepseek-v4-pro` 一串，改不动 provider。

DeepSeek 两个型号的落点因此分开：

| 模型 | 🥇 首选 | 次选 | 理由 |
|---|---|---|---|
| `deepseek-v4-pro` | **京东** | cb(0.51x) · 火山 | 京东 pro 有 **7 折**；且 cb 的 0.51x 烧 credits 太快，挪走能护住 cb 额度 |
| `deepseek-v4-flash` | **火山** | codebuddy(0.17x) | 都是已付费套餐；⛔ flash 不走京东，把积分省给 pro |

⚠️ 其余模型按原顺序，本次只改 DeepSeek 两个型号。
⚠️ `deepseek/*` 官方 provider 仍在 opencode 的 `disabled_providers` 里 ⇒ **兜底这一环目前是断的**，真要用得先解除禁用。

### ⚠️ 与官方 API 的价格对比：京东并不是绝对最便宜

读了官方定价页（版本 **DeepSeek-V4-Pro-0813**）才把账算清：

| 项 | 京东 7 折 | 官方空闲 | 官方高峰 |
|---|---|---|---|
| 输入（缓存未命中） | ¥8.4 | **¥4.5** | ¥9.0 |
| 输出 | ¥16.8 | **¥13.5** | ¥27.0 |
| 输入（缓存命中） | ¥0.7 | **¥0.15** | ¥0.30 |

京东那 ¥8.4 落在官方**空闲与高峰之间**：比空闲贵 1.87 倍，只比高峰便宜 7%。
🔴 缓存命中差最狠——贵 **4.7 倍**（官方缓存命中只要未命中价的 3.3%，京东是 8.3%）。
而官方高峰只有工作日 9-12、14-18 两段，**大部分时间官方单价更低**。

⇒ **选京东不是因为单价最低，是因为钱包优先级**：官方花现金，京东花已买入的积分。
这条区分很重要——⛔ 别把「优先京东」误记成「京东最便宜」。

### 🔴 自我修正：之前那「四条证据」其实是一条

本条目最初声称有四条独立证据支持「京东那份不是 preview」（下方「已验证：与火山同代」一节）。
读官方定价页后发现**后三条站不住**：

| 原列证据 | 实际 |
|---|---|
| 同轮盲评 + 架构题 37 vs 旧版 24 | ✅ **承重的只有这条** |
| `max_tokens` 上限 393,216 两侧一致 | 🔻 官方页写明输出上限 384K，**V4 全代通用** |
| tokenizer 一致 | 🔻 **同族本就同分词** |
| 60k 长上下文 3/3 | 🔻 官方页写明上下文 1M，**全代通用** |

**任何 V4-Pro 快照都会给出后三条一样的结果，⛔ 它们没有区分度。**
结论仍成立，但支撑面比原先声称的窄。

⚠️ 教训：**「两个来源给出同一个值」只有在这个值可能不同的时候才是证据。**
我拿三个族级规格当成了三次独立验证，实际是同一句话说了三遍。

### ⭐ `DeepSeek-V4-pro` 当前 7 折

| model id | 实付 积分/百万（输入/输出/缓存） | 折扣 |
|---|---|---|
| `DeepSeek-V4-pro` | **8,400 / 16,800 / 700** | ⭐ **7 折**（原价 12,000 / 24,000 / 1,000） |
| `DeepSeek-V4-Flash` | 1,400 / 2,800 / 280 | 无 |

`1,000 积分 = ¥1`。⚠️ 7 折**没标截止日期**（`offlineTime: null`）；⚠️ 积分**有效期一年**，
⛔ 不是永久额度 —— 与 cb credits / 火山包月 / Copilot 订阅都不同。

⚠️ 即使 7 折后 V4-pro 仍是 Flash 的 **6 倍**（8,400 vs 1,400）⇒ 升档纪律不变。

### ✅ 已验证：与火山那份 `deepseek-v4-pro` 同代，不是 preview

用户从 publishDate（2026-04-28，早于我测到 86 分的那版）怀疑京东在服务 preview。方向合理，
但**上架日期 ≠ 权重版本**。

**⚠️ 结论是「一条承重证据 + 三条弱证据」，⛔ 不是四条独立证据**（见下方「自我修正」一节）：

| 观测 | 结果 | 证据强度 |
|---|---|---|
| **同轮盲评 + 架构题** | JD 108 vs 火山 104；🔴 JD 架构题 **37**，而 06-28 那个疑似 preview 的旧版只有 **24** | ✅ **承重的只有这条** |
| `max_tokens` 上限 393,216 | 两侧一致 | 🔻 弱：官方页写明输出上限 384K，**V4 全代通用** |
| tokenizer（`prompt_tokens` 51,729） | 两侧一字不差 | 🔻 弱：**同族本就同分词** |
| 60k 长上下文 3/3 | 两侧全中 | 🔻 弱：官方页写明上下文 1M，**全代通用** |

⛔ 4 分/120 在噪声内，这一格只用来证【同级】，⛔ 不用来排名。
⛔ 也证明不了字节级同一份权重 —— 但问的是版本代次。

### 🔴 方法论教训：问的是「同级吗」，我却去测了「谁更强」

我上来直接派 6 个 agent 跑三题盲评，花掉一小时，然后还在纠结那 4 分是不是噪声。
用户纠正后才回到正路——**真正对口的两个探针都近乎零成本**：

1. 发 `max_tokens: 500000` 的极短请求 —— 网关在**计费前**拒绝，错误信息里直接返回真实上限
2. 同一段输入比 `prompt_tokens` —— 同 tokenizer 才会一字不差

⇒ **「同级 / 同代」是能力上限问题，能被一个确定性边界值一击命中；
「谁更强」才是质量分布问题，只能靠有噪声的采样逼近。**
⛔ 判据是边界值却去做采样，是拿贵的、糊的手段回答清楚的问题。

⚠️ 另外两条试过但不成立的路（⛔ 别重做）：
- **temp=0 权重指纹** —— 自一致性对照显示两臂都不确定，cap 题**臂间相似度 0.698 反而高于臂内**（0.583/0.614）
- **自述版本号** —— n=5/臂，JD `{V3.2:2, V3:2, V4:1}`、火山 `{V3:4, V3.2:1}`，两侧自己都不稳

### ⚠️ 顺带修正三处既有记录

- **Paseo 的 `list_models` 缓存 ⛔ 不影响实际派发** —— 列表里看不到 `jdcloud-joyagent`，
  但 `create_agent(provider="pi/jdcloud-joyagent/DeepSeek-V4-pro")` 能正常起来，
  `runtimeInfo.model` 回显正确、无静默降级。原记「要重启 daemon 才能用」只对 UI 列表成立
- **pi provider 在 Paseo 里没有 mode** —— `availableModes` 为空，⛔ 传 `modeId` 报 `Invalid mode`
- **pi 的会话 transcript 是嵌套结构** —— `r['message']['role']` / `['content']`，
  content 块有 `text` / `thinking` 两种。照 codebuddy 格式写的提取器会采出 0 字符

catalog 升至 **5.9.0**（本轮多次迭代，中间版本见提交历史）。


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

> ⚠️ **已被 v11.3 更正**：hy4 免费实际是 **2026-08-28 ~ 09-10**，且是**每日赠额**⛔ 非连续免费期。本段的 09-12 是旧误记。
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

> ⚠️ **已被 v11.3 更正**：hy4 免费实际是 **2026-08-28 ~ 09-10**，且是**每日赠额**⛔ 非连续免费期。本段的 09-12 是旧误记。
| `hy4-preview-x` | **0.29x** | ⚠️ 同名收费版 |
| `hy3` / `hy3-x` | 0.00x / 0.05x | 同一模式 |

**同一个 label、两个 id、一免费一收费。** 🔴 派发必须认 id，按 label 匹配会选错。
⚠️ 附带风险：09-12 限免结束后若平台把 hy4-preview 直接切成收费，费率会从 0 跳到 **0.29x**，

> ⚠️ **已被 v11.3 更正**：hy4 免费实际是 **2026-08-28 ~ 09-10**，且是**每日赠额**⛔ 非连续免费期。本段的 09-12 是旧误记。
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
> ⚠️ **计数已过期**：🔴 v11.3（2026-09-09）起是 **coding 8 / agent-plan 13**（两边都补了 `glm-5.3-flash`）。当前值以 `oneshotChannels.pi.providers` 与 `pi --list-models` 为准。

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

> ⚠️ **计数已过期**：本段的火山模型数是当时快照。🔴 v11.3（2026-09-09）起是 **coding 8 / agent-plan 13**（两边都补了 `glm-5.3-flash`）。
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
  > 🔴 **2026-09-09（v11.3）已收窄这一条**：它是**当时针对 qcn 折扣结束**的结论。
  > 百炼与 codebuddy 各自有折扣窗口后，时段判断以**新形态**回归（只在【档内选落点】介入）。
  > 真正长期成立的不变量是 **⛔ 不得跨档下调**，⛔ 不是「不许有时段判断」。
  > 现行规则见 v11.3 与 `walletPriority.discountWindows`。
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
