#!/usr/bin/env python3
"""rift-dispatch 跨文件一致性校验（**数据层**）—— 每次改路由规则后跑一遍。

🔴 **覆盖面如实说明**：本脚本比对的是 `SKILL.md` 与 `model-catalog.json` 的**结构化数据**
（豁免集 / 白名单 / 钱包顺序与 modelId / providers map / pi 侧配置）。
⛔ `model-routing.md` 只被用来**搜旧语残留**，⛔ 不做表格级比对 —— 别把注释里的
「三处一致」理解成三份都做了结构比对。

🔴 **§2 伪代码的行为正确性⛔不在本脚本** —— 那由 `scripts/pipeline-test.py` 负责：
   它直接【执行】markdown 里的伪代码并跑 17 条用例断言落点。两个都要跑。


⚠️ 三条自身教训（都踩过）：
1. 正则字符类记得带 `_`（`qmodel_38max` 的下划线漏了导致 3 条误报）
2. 断言查【性质】⛔ 别查实现字符串（查 `'args.model or args.provider' in S`，一重构就假失败）
3. ⛔ 别硬编码 `~/.claude/skills/...` —— 那是软链副本，换台机器 clone 就验错对象
"""
import json, re, sys, pathlib

B = pathlib.Path(__file__).resolve().parent.parent      # 🔴 相对自身定位，⛔ 不硬编码
d = json.load(open(B/'model-catalog.json'))
S = (B/'SKILL.md').read_text()
R = (B/'model-routing.md').read_text()
PI = pathlib.Path.home()/'.pi/agent/models.json'
pi = json.load(open(PI)) if PI.exists() else None

e = []
def chk(cond, msg):
    if not cond: e.append(msg)

# ── 1. 豁免集：SKILL 与 catalog 一致，且 pi / jdcloud / deepseek 都不在里面 ──
sk  = set(re.findall(r"'([a-z0-9._\-]+)'",
      re.search(r"EXEMPT_PROVIDERS\s*=\s*\[(.*?)\]", S, re.S).group(1)))
cat = set(k for k in d['whitelist']['exempt'] if not k.startswith('_'))
chk(sk == cat, f"豁免集 SKILL≠catalog: {sorted(sk ^ cat)}")
for bad in ('pi', 'jdcloud-joyagent', 'deepseek'):
    chk(bad not in sk,  f"⛔ {bad} 不该在 SKILL EXEMPT")
    chk(bad not in cat, f"⛔ {bad} 不该在 catalog exempt")

# ── 2. 白名单：SKILL 与 catalog 一致 ──
# ⚠️ 遍历 catalog 里实际存在的 provider 键，⛔ 别硬编码名字——
#    provider 会被停用（京东 2026-09-09），硬编码会让脚本自己 KeyError 崩掉
NON_PROVIDER = {'consequences'}          # ⚠️ whitelist 下的 list 不都是 provider
WL_PROVIDERS = [k for k, v in d['whitelist'].items()
                if not k.startswith('_') and isinstance(v, list) and k not in NON_PROVIDER]
chk(WL_PROVIDERS, "catalog whitelist 里一个 provider 都没有")
for prov in WL_PROVIDERS:
    w = set(d['whitelist'][prov])
    m = re.search(rf"'{re.escape(prov)}':\s*\[(.*?)\]", S, re.S)
    chk(m is not None, f"SKILL 缺 {prov} 白名单")
    if m:
        chk(w == set(re.findall(r"'([A-Za-z0-9._\-]+)'", m.group(1))),
            f"{prov} 白名单 SKILL≠catalog")

# ── 3. 钱包：SKILL 与 catalog 全序 + modelId 一致 + JD 必须大写 modelId ──
wp = d['walletPriority']['modelProviderPreference']
wpref = re.search(r"WALLET_PREF = \{(.*?)\n\}", S, re.S).group(1)
for m, v in wp.items():
    # ⚠️ 必须带冒号切 —— 键和元组里的 modelId 字面相同（'deepseek-v4-pro' 出现两次），
    #    不带冒号会切在 modelId 上，只截到第一个元组。本轮踩过（第三次栽在正则太朴素）。
    seg = wpref.split(f"'{m}':")
    chk(len(seg) > 1, f"SKILL WALLET_PREF 缺 {m}")
    if len(seg) > 1:
        # ⚠️ 比【全序 + 每个 provider 的真实 modelId】，⛔ 不只比 first
        #    （只比 first 会漏掉「首选没变、次选或 modelId 错」）
        block = seg[1].split('],')[0]
        pairs = re.findall(r"\('([a-z0-9._\-]+)',\s*'([A-Za-z0-9._\-]+)'\)", block)
        got_order = [u for u, _ in pairs]
        # ⚠️ 2026-09-09 结构改了：三池【轮换】⇒ 用 rotation 列表，⛔ 不再是 first/then
        want_order = list(v.get('rotation') or ([v['first']] + list(v.get('then', []))))
        chk(got_order == want_order,
            f"{m} provider 顺序 SKILL={got_order} catalog={want_order}")
        for u, mid in pairs:
            expect = d['models'].get(m, {}).get('providers', {}).get(u, {})
            if isinstance(expect, dict) and expect.get('modelId'):
                chk(mid == expect['modelId'],
                    f"{m}@{u} modelId SKILL={mid} catalog={expect['modelId']}")
# ⚠️ 原有「JD modelId 必须大写」断言随京东 2026-09-09 停用一并移除。
#    恢复京东时要连同这条断言一起加回（归档文件的恢复清单里有记）。
chk(wp['deepseek-v4-flash'].get('noJdcloud') is True, "flash 必须标 noJdcloud")

# ── 3b. 夜间折扣：catalog 与 SKILL 的 NIGHT_DISCOUNTED 必须对得上 ──
nd = d['walletPriority'].get('nightDiscount')
chk(nd is not None, "catalog 缺 nightDiscount")
if nd:
    sk_night = set(re.findall(r"'([a-z0-9._\-]+)'",
                   re.search(r"NIGHT_DISCOUNTED = \{(.*?)\}", S, re.S).group(1)))
    # catalog 记的是 provider 侧 id，SKILL 记的是阶梯模型名 ⇒ 用 bailianModelId 建映射再比
    want_night = {m for m, v in wp.items()
                  if v.get('bailianModelId') in set(nd.get('appliesTo', []))}
    chk(sk_night == want_night,
        f"夜间折扣集合 SKILL={sorted(sk_night)} 由 catalog 推得={sorted(want_night)}")
    chk('is_night_window' in S, "SKILL 缺夜间窗口判断")
    # 🔴 夜间判断⛔不得出现在【选模型】那一段（旧时段策略的病根）
    body_sel = re.search(r"# ═══ 4\. 选模型.*?# ═══ 5\.", S, re.S)
    chk(body_sel is None or 'is_night' not in body_sel.group(0),
        "⛔ 夜间判断混进了【选模型】段落——旧时段策略正是这样把档位冲掉的")
chk('jdcloud' not in re.search(r"'deepseek-v4-flash':.*?\],", S, re.S).group(0),
    "WALLET_PREF flash 不该含京东")

# ── 4. 🔴 伪代码结构：单一线性管线 ──
body = re.search(r"## 2\. 决策流程.*?```python\n(.*?)\n```", S, re.S).group(1)
for fn in ('split_provider', 'normalize_provider', 'validate', ):
    chk(f'def {fn}' in body, f"缺 {fn}()")
chk('goto' not in body, "⛔ 伪代码里不许有 goto（会跳过初始化）")
# 提前 return 只允许 helper 函数内。2026-09-09 起顶层【零例外】——
# 原先 --free 的 delegate 出口随 rift-free 一起删除了。
def strip_comment(l):            # ⚠️ 必须剥注释：注释里写「⛔ 不 return」会被误判
    return l.split('#', 1)[0]
code = [strip_comment(l) for l in body.split('\n')]
in_fn = False; top_returns = []
for l in code:
    if re.match(r'^def ', l): in_fn = True; continue
    if l.strip() and not l.startswith((' ', '\t')): in_fn = False
    if in_fn: continue                                   # 函数体内的 return 合法
    if re.search(r'\breturn\b', l):
        top_returns.append(l.strip())
chk(not top_returns, f"⛔ 顶层提前 return（会绕过统一收尾）: {top_returns[:2]}")

# 🔴 「变量用了但没赋值点」—— 第三轮栽在 scope / channel 上
USED = set(re.findall(r"\b([a-z_][a-z0-9_]*)\b(?=\s*[),])", body))
for var in ('scope', 'channel', 'thinking', 'task_type', 'upstream', 'model',
            'want_free', 'CAPABILITY_BLOCKERS'):   # 0909: --free 改造引入，别再漏检
    chk(re.search(rf"^\s*{var}\s*=|,\s*{var}\s*=|{var},.*=", body, re.M) is not None,
        f"⛔ 变量 `{var}` 被使用但找不到赋值点")
for dangling in ('pick_provider_for', 'default_model_for'):
    chk(dangling not in body, f"⛔ {dangling} 是悬空引用")
# 显式值只读不写
chk('explicit_model' in body and 'explicit_upstream' in body,
    "⛔ 必须用 explicit_* 保存用户显式值，否则会被阶梯覆盖")
chk(re.search(r"^\s*explicit_(model|upstream|thinking)\s*=", body, re.M) is not None,
    "explicit_* 必须有赋值点")
chk(len(re.findall(r"^\s*explicit_model\s*=", body, re.M)) == 1,
    "⛔ explicit_model 只能赋值一次（只读不写）")

# ── 5. 审查按规模分流，无「审查整类 → pi -p」残留 ──
chk('is_large_review' in body, "P4/收尾未按规模分流")
for f, n in ((S, 'SKILL'), (R, 'routing')):
    for pat in ('只读/短/审查类', '只读 / 短 / 审查类'):
        chk(pat not in f, f"{n} 仍写「审查类→pi -p」")
chk('审查=pi -p Copilot' not in json.dumps(d, ensure_ascii=False), "catalog matrix 仍写审查→pi -p")

# ── 6. providers map 已补齐首选 ──
chk('volcengine-coding' in d['models']['glm-5.3-flash']['providers'], "glm-5.3-flash.providers 缺火山")
chk('jdcloud-joyagent' in d['models']['deepseek-v4-pro']['providers'], "deepseek-v4-pro.providers 缺京东")

# ── 7. pi 侧配置（本机才查） ──
if pi:
    cop = pi['providers']['github-copilot']['models']
    chk(not any(m['id'].startswith('claude') for m in cop), "pi Copilot 仍有 claude")
    chk(sorted(m['id'] for m in cop if m.get('unsupported'))
        == ['gpt-5.4-nano', 'kimi-k2.7-code', 'kimi-k3'], "unsupported 标记不全")
    for p_ in ('volcengine-coding', 'volcengine-agent-plan'):
        chk('glm-5.3-flash' in [m['id'] for m in pi['providers'][p_]['models']],
            f"pi {p_} 缺 glm-5.3-flash")

print("=== rift-dispatch 一致性校验 ===")
print(f"仓库: {B}")
print("✅ 全部通过" if not e else "\n".join("❌ " + x for x in e))
sys.exit(1 if e else 0)
