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

# ── 3b. 折扣窗口：catalog 与 SKILL 的 DISCOUNT_WINDOWS 必须对得上 ──
dw = d['walletPriority'].get('discountWindows')
chk(dw is not None, "catalog 缺 discountWindows")
if dw:
    cat_pools = {k for k in dw if not k.startswith('_') and k not in ('overlap', 'caveat')}
    sk_block = re.search(r"DISCOUNT_WINDOWS = \{(.*?)\n\}", S, re.S)
    chk(sk_block is not None, "SKILL 缺 DISCOUNT_WINDOWS")
    if sk_block:
        sk_pools = set(re.findall(r"^\s{2}'([a-z0-9\-]+)':", sk_block.group(1), re.M))
        chk(sk_pools == cat_pools, f"折扣池 SKILL={sorted(sk_pools)} catalog={sorted(cat_pools)}")
        for pool in cat_pools & sk_pools:
            want = set(dw[pool].get('models', []))
            seg = sk_block.group(1).split(f"'{pool}':")[1]
            got = set(re.findall(r"'([a-z0-9.\-]+)'", seg.split('}')[0]))
            got -= {'models', 'when'}
            chk(want <= got, f"{pool} 折扣模型 catalog={sorted(want)} SKILL 未全覆盖={sorted(want-got)}")
    chk('is_discounted_now' in S, "SKILL 缺 is_discounted_now()")
    # 🔴 折扣判断⛔不得出现在【选档位】那一段（2026-08-12 跨档下调的病根）
    sel = re.search(r"# ═══ 4\. 选模型.*?# ═══ 5\.", S, re.S)
    chk(sel is None or 'is_discounted_now' not in sel.group(0),
        "⛔ 折扣判断混进了【选档位】段落——2026-08-12 的 bug 正是这样跨档下调的。"
        "价格只许在【档位内选落点】那一步介入")
chk('jdcloud' not in re.search(r"'deepseek-v4-flash':.*?\],", S, re.S).group(0),
    "WALLET_PREF flash 不该含京东")

# ── 3c. 🔴 TIER_PEERS：SKILL ↔ catalog 一致，且每个 peer 必须带实测依据 ──
#    ⚠️ 0909 审查指出：靠注释约束「同档」防不住后来误加跨档 peer ⇒ 这里做成机器可校验。
m = re.search(r"TIER_PEERS\s*=\s*\{(.*?)\n\}", S, re.S)
chk(m is not None, "SKILL 里找不到 TIER_PEERS")
if m:
    sk_peers = {}
    for km in re.finditer(r"'([a-z0-9.\-]+)':\s*\[(.*?)\]", m.group(1), re.S):
        sk_peers[km.group(1)] = re.findall(r"\('([^']+)',\s*'([^']+)'\)", km.group(2))
    cat_tp = d.get('walletPriority', {}).get('tierPeers', {})
    cat_peers = {k: [(p['upstream'], p['modelId']) for p in v['peers']]
                 for k, v in cat_tp.items() if not k.startswith('_')}
    chk(sk_peers == cat_peers, f"TIER_PEERS SKILL≠catalog: SKILL={sk_peers} catalog={cat_peers}")
    ladder = set(re.findall(r"\('([a-z0-9.\-]+)',\s*[\d.]+\)",
                 re.search(r"LADDER\s*=\s*\[(.*?)\]", S, re.S).group(1)))
    for base, peers in sk_peers.items():
        chk(base in ladder, f"TIER_PEERS 的键 {base} ⛔ 不是阶梯模型")
        ent = cat_tp.get(base, {})
        chk(bool(ent.get('evidence')), f"⛔ {base} 的 tierPeers 缺 evidence —— 同档结论必须有实测依据")
        for up, mid in peers:
            # 🔴 peer ⛔ 不得是【另一个阶梯档位】的模型 —— 那是跨档，不是档内换落点
            chk(mid not in ladder,
                f"⛔ {base} 的 peer {mid} 本身就是阶梯模型 ⇒ 跨档，TIER_PEERS 只许档内换落点")
            # ⚠️ 0909 二审抓到：只允许豁免集会【误伤】白名单 provider 上的合法 peer。
            #    validate() 实际放行两条路径：upstream ∈ EXEMPT，或 upstream ∈ WHITELIST 且 model 在其清单内。
            #    ⛔ 补缺口时别把合法路径一起堵死（见 feedback-plugging-a-gap-blocks-valid-paths）。
            wl_ok = up in WL_PROVIDERS and mid in set(d['whitelist'][up])
            chk(up in cat or wl_ok,
                f"⛔ peer {up}/{mid} 既不在豁免集、也不在白名单清单内 ⇒ validate() 会拦掉它")

# ── 3d. 🔴 反残留：新设计上线后，⛔ 旧的相反陈述不得留在【当前规则三份】里 ──
#    ⚠️ 0909 四轮异构审查抓了 13 条同一形状的问题：改了权威定义，但速查/用例表/降级链没跟着改。
#    脚本只比结构化数据 ⇒ 散文漂移必须**单独钉**。⛔ CHANGELOG 是历史，不在检查范围。
C_RAW = (B/'model-catalog.json').read_text()
CUR = {'SKILL.md': S, 'model-routing.md': R, 'model-catalog.json': C_RAW}
#    ⚠️ 0909 第 5 轮审查抓到：只扫两份会漏掉 catalog 里的同类残留 ——
#       **补缺口时把范围也补全**，⛔ 别留第三份没扫。
HISTORICAL = re.compile(r'历史存档|已作废|已被 v|旧记|correction|计数已过期|历史快照|formerPreferred')
# ⚠️ needle 必须**同时**命中「主题」和「在断言路由角色」两个条件 ——
#    第一版只搜「官方 API」，把【价格对比】小节也报成残留（6 报里 2 个是误报）。
#    ⛔ 守卫误报多了就会被忽略（同 feedback-plugging-a-gap-blocks-valid-paths）。
ROLE = re.compile(r'兜底|降级链|fallback|顺位|拿不到才|最后一档|永远只做')
# ⚠️ **描述历史 bug 的句子⛔不是在立规则** —— 第一版没区分，17 报里 7 个是这类误报。
#    判据：句子里出现 is_night / 「那个 bug」/「旧写法」= 在讲过去，⛔ 不在规定现在。
DESCRIPTIVE = re.compile(r'is_night|那个 bug|旧写法|越过档位边界|换成【低档】|换成了低档|留下的空档'
                        # ⚠️ **否定语境**也不是在立规则：「⛔ 不参与『做砸就升档』那条路径」
                        #    是在说 LAST_RESORT【不走】质量路径 —— 它本身就已经限定清楚了。
                        r'|不参与|⛔ ?不走|不受此约束|不是阶梯的|⛔ ?不是 ?T5')
RESIDUE = [
  # (主题正则, 必须【同时出现】的限定语, 说明)
  # ⚠️ 第 7 轮又漏了一批同义写法（做砸才用 / 做砸后接手 / 做砸就升 / 做砸过一轮时进入…）。
  #    ⇒ ⛔ 别再逐条枚举，改成【做砸 + 动作词】的窗口匹配。
  (re.compile(r'唯一入口|才升 ?K3|做砸[^。\n]{0,12}(才|就|后)[^。\n]{0,6}(升|用|接手|进入|起步)'), ('质量/成本',),
   '「升档需做砸」⛔ 必须限定为【质量/成本升档】——可用性换档不受此约束'),
  (re.compile(r'模型固定|固定 ?`?github-copilot/gpt-5\.5|不受 P0 约束'), ('默认', '旧说法'),
   'review 的模型是**默认值**⛔不是「固定/不可覆盖」；选出的组合照样过 validate()，⛔ 不是「不受 P0 约束」'),
  (re.compile(r'四池 ?\+ ?同档替代|四池轮换 ?\+'), ('仅 T3',),
   '⛔ 别把「四池 + 同档替代」当通则：T2 四池【无】同档替代 · T1 三池 · T4 只有 cb · TIER_PEERS 仅 T3'),
  (re.compile(r'官方 ?API|deepseek/\*'), ('手动', '已不是自动兜底', '不在自动降级链'),
   '`deepseek/*` ⛔ 已不是自动兜底，⛔ 不许再写「永远兜底/前面拿不到才用」'),
]
for topic, musts, why in RESIDUE:
    musts = (musts,) if isinstance(musts, str) else musts
    for fn, txt in CUR.items():
        lines = txt.splitlines()
        for ln, line in enumerate(lines, 1):
            if not topic.search(line): continue
            if any(q in line for q in musts): continue
            if HISTORICAL.search(line): continue        # ⛔ 历史存档不算当前规则
            if DESCRIPTIVE.search(line): continue       # ⛔ 描述旧 bug ≠ 立规则
            if topic.pattern.startswith('官方') and not ROLE.search(line): continue   # ⛔ 价格对比不算
            # ⚠️ **JSON ⛔ 不给「相邻行补限定」的宽限** —— 每行是一个自洽字段，
            #    而 JSON 里字段挨得极密，旁边随便一行带上限定语就会把真残留放过去
            #    （0909 实测：把 dispatchNote 改成无限定写法，守卫竟然全绿）。
            #    markdown 才需要这个宽限（散文会折行）。
            scope = line if fn.endswith('.json') else '\n'.join(lines[ln-1:ln+2])
            chk(any(q in scope for q in musts),
                f"{fn}:{ln} 出现「{topic.pattern}」且在断言路由角色，但缺限定「{'/'.join(musts)}」—— {why}")

# ── 3e. 🔴 测评结果必须【按 model id 查得到数值】，⛔ 不能只躺在散文/轮次记录里 ──
#    ⚠️ 0909 漏过三处：qwen 那轮的分只在 tierPeers.evidence 的**字符串**里；5 个 Copilot 型号
#       连 models 条目都没有；h2h/jdVsVolc 用的是**臂标签**（v4flash / jd）⛔ 不是 model id。
#       ⇒ agent 扫 per-model 字段时**一个都看不到**。（同 feedback-change-the-data-not-the-prose-rule）
#    ⚠️ 六轮记录有**五种结构** ⇒ ⛔ 别假设只有一种，写 normalizer。
ALL_MODELS = dict(d.get('models', {})); ALL_MODELS.update(d.get('claudeModels', {}))

def round_totals(r):
    """六种结构归一成 {model_id: total}；⛔ 认不出就返回 {} 而不是猜。"""
    if not isinstance(r, dict): return {}
    a2m = r.get('_armToModel', {})
    def mid(k): return a2m.get(k, k)
    if isinstance(r.get('scores_120'), dict):
        return {mid(k): v for k, v in r['scores_120'].items() if isinstance(v, (int, float))}
    if isinstance(r.get('totals_120'), dict):
        return {mid(k): v for k, v in r['totals_120'].items() if isinstance(v, (int, float))}
    sc = r.get('scores')
    if isinstance(sc, dict) and all(isinstance(v, dict) and 'total' in v for v in sc.values()):
        return {mid(k): v['total'] for k, v in sc.items()}
    return {}

rounds = [k for k in d if isinstance(d[k], dict) and round_totals(d[k])]
chk(rounds, "catalog 里没有任何可解析的测评轮次记录")
for rk in rounds:
    for m_id, total in round_totals(d[rk]).items():
        ent = ALL_MODELS.get(m_id, {})   # ⚠️ ⛔ 别用 `e` —— 模块级 e 是错误列表（撞过）
        chk(bool(ent), f"⛔ {rk} 给 `{m_id}` 打了分，但 models/claudeModels 里没有这个条目")
        if not ent: continue
        byr = ent.get('blindEvalByRound', {})
        totals = {v.get('total') for v in byr.values() if isinstance(v, dict)}
        totals.add(ent.get('blindEval', {}).get('total'))
        chk(total in totals,
            f"⛔ `{m_id}` 在 {rk} 的分 {total} 在 per-model 数值字段里查不到"
            f"（现有 {sorted(x for x in totals if x is not None)}）—— 分不能只躺在轮次记录里")

# 🔴 屏蔽名单：SKILL 的 BLOCKED_MODELS 必须与 catalog.whitelist.blockedModels 逐条一致
m = re.search(r"BLOCKED_MODELS\s*=\s*\{(.*?)\n\}", S, re.S)
chk(m is not None, "SKILL 里找不到 BLOCKED_MODELS")
if m:
    sk_blk = {km.group(1): set(re.findall(r"'([A-Za-z0-9._\-]+)'", km.group(2)))
              for km in re.finditer(r"'([a-z0-9.\-]+)':\s*\{(.*?)\}", m.group(1), re.S)}
    cat_blk = {k: set(v) for k, v in d['whitelist'].get('blockedModels', {}).items()
               if not k.startswith('_')}
    chk(sk_blk == cat_blk,
        f"屏蔽名单 SKILL≠catalog: 仅SKILL={ {k: sorted(sk_blk.get(k,set())-cat_blk.get(k,set())) for k in sk_blk} } "
        f"仅catalog={ {k: sorted(cat_blk.get(k,set())-sk_blk.get(k,set())) for k in cat_blk} }")
    # ⛔ 被屏蔽的型号不得同时出现在「可用异族评审」清单里
    # ⚠️ 清单会**折行**（第二行以 `·` 开头）⇒ ⛔ 不能只锚第一行（0909 实测：把被屏蔽型号
    #    插到第二行，守卫全绿）。改成取【整块】：从「可用异族评审」到「已屏蔽」之间。
    L = S.splitlines()
    try:
        a = next(i for i, l in enumerate(L) if '可用异族评审' in l)
        b = next(i for i, l in enumerate(L[a:], a) if '已屏蔽' in l)
        review_block = '\n'.join(L[a:b])
    except StopIteration:
        review_block = ''; chk(False, "§3.2c 找不到「可用异族评审 … 已屏蔽」这一块")
    for mid in sk_blk.get('github-copilot', ()):
        chk(f'`{mid}`' not in review_block, f"⛔ 被屏蔽的 {mid} 仍列在可用异族评审清单里")

# 🔴 顶层 `pi` ⛔ 不得被当成豁免 provider —— 它是【宿主】，豁免它会让
#    `pi/jdcloud-joyagent/...` 整条绕过 upstream 校验（0909 第 6 轮审查；⚠️ 第一版守卫没覆盖，
#    是靠破坏场景实测发现漏检的 —— 「守卫通过」⛔ 不等于「守卫有用」）。
PI_EXEMPT = re.compile(r'(豁免|EXEMPT)[^\n]{0,40}\bpi\b|\bpi\b[^\n]{0,20}(豁免|EXEMPT)')
SAFE_PI   = re.compile(r'不是顶层|宿主|split_provider|⛔ ?不该在|不得|not in')
for fn, txt in CUR.items():
    for ln, line in enumerate(txt.splitlines(), 1):
        if PI_EXEMPT.search(line) and not SAFE_PI.search(line):
            chk(False, f"{fn}:{ln} 把顶层 `pi` 说成豁免 provider —— ⛔ pi 是宿主，"
                       f"豁免它会让 pi/<被禁 upstream>/* 绕过校验；校验对象必须是 split_provider() 后的 upstream")

# LAST_RESORT 三份口径一致
for fn, txt in list(CUR.items()):
    chk('claude-sonnet-5' in txt, f"{fn} ⛔ 没提 LAST_RESORT claude-sonnet-5")
lr = d.get('claudeModels', {}).get('claude-sonnet-5', {}).get('lastResort')
chk(bool(lr), "catalog 缺 claudeModels.claude-sonnet-5.lastResort")
if lr:
    chk(lr.get('thinking') == 'max', f"LAST_RESORT thinking 应为 max，实际 {lr.get('thinking')}")
    chk(lr.get('paseoProvider') == 'claude/claude-sonnet-5', "LAST_RESORT paseoProvider 不对")
    chk("LAST_RESORT = ('claude', 'claude-sonnet-5', 'max')" in S,
        "SKILL 的 LAST_RESORT 常量与 catalog 不一致")

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

# ── 6. providers map：⚠️ 这里查的是【归档映射仍在】，⛔ 不是「京东是首选」 ──
#    京东 2026-09-09 已停用，但 catalog 保留它的 provider 映射以便将来恢复（见 whitelist._jdcloudNote）。
#    ⛔ 与 §3 的「停用 provider 不得残留在 WHITELIST / WALLET_PREF」不矛盾：
#       那条管的是【会被派发选中的路径】，本条管的是【归档资料】。
chk('volcengine-coding' in d['models']['glm-5.3-flash']['providers'], "glm-5.3-flash.providers 缺火山")
chk('jdcloud-joyagent' in d['models']['deepseek-v4-pro']['providers'], "deepseek-v4-pro.providers 丢了京东的【归档】映射（⛔ 不是说它是首选）")

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
