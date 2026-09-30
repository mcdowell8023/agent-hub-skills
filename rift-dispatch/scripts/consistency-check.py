#!/usr/bin/env python3
"""rift-dispatch 跨文件一致性校验（**数据层**）—— 每次改路由规则后跑一遍。

🔴 **覆盖面如实说明**：本脚本比对的是 `SKILL.md` 与 `model-catalog.json` 的**结构化数据**
（豁免集 / 白名单 / 钱包顺序与 modelId / providers map / pi 侧配置）。
⚠️ `model-routing.md` 主要用来**搜旧语残留**；🔴 唯一的结构比对是 §3n（§0 派发链 ⇔ LADDER/T0，
2026-09-24 加）—— 其余表格⛔仍不比对，别把「三处一致」理解成三份都做了结构比对。

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

# 🔴 T0 免费池字面量（2026-09-29）：直接执行 SKILL 里那一段赋值取值 —— ⛔ 不用正则拆字段
#    （条目里有 set()、None、嵌套 ⇒ 正则一定会漏；只给 `set` 一个内建，别的名字一概不给）
_FP = re.search(r"^FREE_POOL = \[\n.*?^\]", S, re.S | re.M)
_ns = {}
if _FP: exec(_FP.group(0), {'__builtins__': {'set': set}}, _ns)
SK_FP = sorted(_ns.get('FREE_POOL', []), key=lambda x: x['priority'])

e = []
def chk(cond, msg):
    if not cond: e.append(msg)
w = []                                   # ⚠️ 只提醒、⛔ 不致失败（如免费条目截止已过：该清理了，但不是规则错）
def warn(cond, msg):
    if not cond: w.append(msg)

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
    wl_ids = set(d['whitelist'][prov])
    m = re.search(rf"'{re.escape(prov)}':\s*\[(.*?)\]", S, re.S)
    chk(m is not None, f"SKILL 缺 {prov} 白名单")
    if m:
        # ⚠️ 字符类必须带 `/` —— 2026-09-29 起有 `stealth/space-bunny-alpha` 这种带斜杠的 id
        chk(wl_ids == set(re.findall(r"'([A-Za-z0-9._/\-]+)'", m.group(1))),
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
    # ⚠️ ⛔ 别按 `_` 前缀过滤说明键 —— **emoji 开头的键漏得掉**（0909 在 versionlessAliases 上
    #    踩过一次，0910 又在 tierPeers 的 `🔴 emptied_20260910` 上踩了第二次）。
    #    ⇒ 判据用**值的形状**：必须是 dict 且含 'peers'。
    cat_peers = {k: [(p['upstream'], p['modelId']) for p in v['peers']]
                 for k, v in cat_tp.items() if isinstance(v, dict) and 'peers' in v}
    chk(sk_peers == cat_peers, f"TIER_PEERS SKILL≠catalog: SKILL={sk_peers} catalog={cat_peers}")
    # ⚠️ 费率列允许 `None`（0910：T3 的 qwen3.8-max 倍率未测，⛔ 不许填数字凑齐）
    #    ⛔ 只写 [\d.]+ 会让该档**整个漏出 ladder 集合**，下面那条断言就空转了。
    ladder = set(re.findall(r"\('([a-z0-9.\-]+)',\s*(?:[\d.]+|None)\)",
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
# 🔴 由 SKILL 实际执行的 LADDER + TIER_PEERS 推出「哪些档有同档替代」，供下面的反残留守卫用
_LADDER_IDS = re.findall(r"\('([a-z0-9._\-]+)',", re.search(r"LADDER\s*=\s*\[(.*?)\]", S, re.S).group(1))
_PEER_TIERS = sorted(f'T{_LADDER_IDS.index(k) + 1}' for k in (sk_peers if m else {}) if k in _LADDER_IDS)
_PEER_QUALIFIERS = tuple(f'仅 {t}' for t in _PEER_TIERS) or ('（无同档替代）',)
RESIDUE = [
  # (主题正则, 必须【同时出现】的限定语, 说明)
  # ⚠️ 第 7 轮又漏了一批同义写法（做砸才用 / 做砸后接手 / 做砸就升 / 做砸过一轮时进入…）。
  #    ⇒ ⛔ 别再逐条枚举，改成【做砸 + 动作词】的窗口匹配。
  (re.compile(r'唯一入口|才升 ?K3|做砸[^。\n]{0,12}(才|就|后)[^。\n]{0,6}(升|用|接手|进入|起步)'), ('质量/成本',),
   '「升档需做砸」⛔ 必须限定为【质量/成本升档】——可用性换档不受此约束'),
  (re.compile(r'模型固定|固定 ?`?github-copilot/gpt-5\.5|不受 P0 约束'), ('默认', '旧说法'),
   'review 的模型是**默认值**⛔不是「固定/不可覆盖」；选出的组合照样过 validate()，⛔ 不是「不受 P0 约束」'),
  # 🔴 限定语**由 SKILL 的 TIER_PEERS 推出**，⛔ 不写死 —— 09-29 实测：写死的「仅 T3」在 T3 清空、T1 有 peer 之后
  #    反过来拦截正确写法（守卫把当时的事实编成了常量，事实一变守卫就站到错的一边）。
  (re.compile(r'四池 ?\+ ?同档替代|四池轮换 ?\+'), _PEER_QUALIFIERS,
   f'⛔ 别把「四池 + 同档替代」当通则：同档替代目前只在 {"/".join(_PEER_TIERS) or "（无）"}（由 SKILL 的 TIER_PEERS 推出）'),
  # ⭐ 2026-09-29 T0 改成登记表：「T0 只有 hy3 / 唯一成员」是 09-15~09-28 的事实，现在只许以历史口吻出现
  (re.compile(r'T0[^。\n]{0,6}(唯一成员|只(有|剩|留)[^。\n]{0,4}hy3)'), ('📜', '当时', '09-15 ~ 09-28'),
   'T0 已是 FREE_POOL 登记表（三条），⛔ 别再写「T0 只有 hy3」—— 要讲历史就带上时间'),
  (re.compile(r'官方 ?API|deepseek/\*'), ('手动', '已不是自动兜底', '不在自动降级链'),
   '`deepseek/*` ⛔ 已不是自动兜底，⛔ 不许再写「永远兜底/前面拿不到才用」'),
  # ⭐ 2026-09-29 审查 r3：entryTier.skipFreeEntries 已改成 FREE_POOL.avoidTaskTypes 的只读镜像，
  #    ⛔ 不再是独立数据源 —— 「entryTier 是唯一真源」这句若不带限定，会让人以为改这里就能改免费池排除规则
  (re.compile(r'entryTier[^\n]{0,40}唯一真源|唯一真源[^\n]{0,40}entryTier'), ('分字段', '镜像', 'FREE_POOL'),
   'entryTier 的 paidEntry 仍是权威，但 skipFreeEntries 只是 FREE_POOL avoidTaskTypes 的镜像，⛔ 不要笼统写「唯一真源」'),
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

# ── 3f. 🔴 子会话标题缩写表：每个可派发落点都必须能拼出标题（用户 2026-09-10 要求）──
#    ⚠️ 标题是派发时才拼的，脚本查不到运行时标题 ⇒ 能查的是【缩写表有没有缺口】。
#       缺一个缩写，派发时就只能瞎编或漏标，规范当场失效。
ATC = d.get('agentTitleConvention', {})
chAbbr, mdAbbr = ATC.get('channelAbbr', {}), ATC.get('modelAbbr', {})
chk(bool(ATC), "catalog 缺 agentTitleConvention")

# ① 所有可派发 model 都要有缩写
dispatchable = set()
for _m, pool in re.findall(r"'([a-z0-9.\-]+)':\s*\[(.*?)\]",
                           re.search(r"WALLET_PREF\s*=\s*\{(.*?)\n\}", S, re.S).group(1), re.S):
    dispatchable |= {mid for _u, mid in re.findall(r"\('([^']+)',\s*'([^']+)'\)", pool)}
dispatchable |= set(re.findall(r"\('([a-z0-9.\-]+)',\s*[\d.]+\)",
                    re.search(r"LADDER\s*=\s*\[(.*?)\]", S, re.S).group(1), re.S))
dispatchable |= {mid for _u, mid in re.findall(r"\('([^']+)',\s*'([^']+)'\)",
                 re.search(r"TIER_PEERS\s*=\s*\{(.*?)\n\}", S, re.S).group(1))}
for prov in WL_PROVIDERS: dispatchable |= set(d['whitelist'][prov])
dispatchable |= {x['model'] for x in SK_FP}      # ⭐ T0 免费池（09-29）
lr = re.search(r"LAST_RESORT = \('([^']+)', '([^']+)'", S)
if lr: dispatchable.add(lr.group(2))
dispatchable.add('gpt-5.5')                       # review 默认
missing = sorted(m for m in dispatchable if m not in mdAbbr)
chk(not missing, f"⛔ 这些可派发模型没有标题缩写，派发时拼不出标题: {missing}")

# ② 缩写必须带版本号（⛔ 不许 dsp / glm 这种）—— 用户点名的核心要求
nover = sorted(m for m, a in mdAbbr.items() if not re.search(r'\d', a))
chk(not nover, f"⛔ 缩写必须含版本号，这些没有: {[(m, mdAbbr[m]) for m in nover]}")
# ②b 🔴 无版本别名（-latest）⛔ 不许出现在缩写表里 —— 它按定义带不出版本，
#      给它缩写等于给了一条「可以派无版本落点」的口子。必须先解析成具体型号。
alias = sorted(m for m in mdAbbr if m.endswith('-latest') or m == 'latest')
chk(not alias, f"⛔ 无版本别名不该有缩写（应先解析成具体型号再派）: {alias}")

# ③ 渠道缩写覆盖豁免集 + 白名单
for prov in sorted(set(cat) | set(WL_PROVIDERS)):
    if prov.startswith('_'): continue
    chk(prov in chAbbr, f"⛔ provider `{prov}` 没有渠道缩写，标题拼不出前缀")

# ④ 🔴 同一渠道内⛔不许两个模型撞同一个缩写 —— 否则两个 agent 标题一模一样，分不出来
wp_pairs = []
for m, pool in re.findall(r"'([a-z0-9.\-]+)':\s*\[(.*?)\]",
                          re.search(r"WALLET_PREF\s*=\s*\{(.*?)\n\}", S, re.S).group(1), re.S):
    wp_pairs += re.findall(r"\('([^']+)',\s*'([^']+)'\)", pool)
wp_pairs += [(x['upstream'], x['model']) for x in SK_FP]   # ⭐ 免费落点同样拼标题
byCh = {}
for up, mid in wp_pairs:
    byCh.setdefault(up, {}).setdefault(mdAbbr.get(mid, '?'), set()).add(mid)
for up, m in byCh.items():
    for abbr, mids in m.items():
        chk(len(mids) == 1,
            f"⛔ 渠道 {up} 上 {sorted(mids)} 撞同一缩写 `{abbr}` ⇒ 标题重名。"
            f"按 agentTitleConvention 的例外规则追加 @快照")

# 🔴 屏蔽名单：SKILL 的 BLOCKED_MODELS 必须与 catalog.whitelist.blockedModels 逐条一致
m = re.search(r"BLOCKED_MODELS\s*=\s*\{(.*?)\n\}", S, re.S)
chk(m is not None, "SKILL 里找不到 BLOCKED_MODELS")
if m:
    sk_blk = {km.group(1): set(re.findall(r"'([A-Za-z0-9._\-]+)'", km.group(2)))
              for km in re.finditer(r"'([a-z0-9.\-]+)':\s*\{(.*?)\}", m.group(1), re.S)}
    # ⚠️ ⛔ 别按 `_` 前缀过滤非 provider 键 —— 说明键可能以 emoji 开头（我刚踩到：
    #    `🔴 versionlessAliases` 是 str，被当成 list(str) 拆成了一堆单字）。
    #    ⇒ 判据用**值的类型**：只有 list 才是 provider 清单。
    cat_blk = {k: set(v) for k, v in d['whitelist'].get('blockedModels', {}).items()
               if isinstance(v, list)}
    chk(sk_blk == cat_blk,
        f"屏蔽名单 SKILL≠catalog: 仅SKILL={ {k: sorted(sk_blk.get(k,set())-cat_blk.get(k,set())) for k in sk_blk} } "
        f"仅catalog={ {k: sorted(cat_blk.get(k,set())-sk_blk.get(k,set())) for k in cat_blk} }")
    # 🔴 §3l 带快照后缀的 id（`X-NNNN`）⛔ 不得被当成基名模型 `X` 的同一物
    #    2026-09-11 实测：百炼上 `deepseek-v4-pro` 与 `-0813` 同一句输入 token 数 8 vs 87、
    #    `deepseek-v4-flash` 直接 403（账号无权限）而 `-0731` 200 ⇒ **不是同一个被服务的模型**。
    #    我原先把 `-0731` 当作「同一模型在百炼上的 id」写进 WALLET_PREF ⇒ 派 T2 会落到另一个模型上。
    snap = re.compile(r'^(?P<base>.+?)-(?P<snap>\d{4})$')
    for line in re.findall(r"\('([a-z0-9.\-]+)',\s*'([A-Za-z0-9.\-]+)'\)", wpref):
        up, mid = line
        m3 = snap.match(mid)
        if not m3:
            continue
        base = m3.group('base')
        chk(False,
            f"⛔ WALLET_PREF 里出现快照后缀 id `{mid}`（基名 `{base}`）—— "
            f"⛔ 带快照后缀的 id 与基名**不是同一个被服务的模型**（0911 实测：token 数差一个量级 / 裸 id 403）。"
            f"⇒ 它要么单独定档，要么别进池。")
    # 缩写也不许共用
    ab = d.get('agentTitleConvention', {}).get('modelAbbr', {})
    for mid, abbr in ab.items():
        m3 = snap.match(mid)
        if m3 and ab.get(m3.group('base')) == abbr:
            chk(False, f"⛔ `{mid}` 与基名 `{m3.group('base')}` 共用缩写 `{abbr}` ⇒ 标题分不出是哪个模型")

    # 🔴 §3m 「同档换落点」分支的**豁免失效条件**
    #    SKILL 里那三行打了 `# pragma: unreachable-by-config`，理由是：
    #    每个 TIER_PEERS 的 provider **都已在该模型的 WALLET_PREF 池里** ⇒ 分支构造不出来。
    #    这条一旦不成立（= 分支重新可达），必须**删掉豁免并补用例**，⛔ 不许让豁免静默留着。
    # ⚠️ 只认**挂在代码行上**的标记（行首第一个非空字符不是 `#`）⛔ 不认散文里的提及。
    #    2026-09-24 实测：豁免撤掉后，注释里一句「它曾被标 `pragma: …`」的历史说明
    #    就让本守卫误报「必须删掉 pragma」—— 判字面不判性质（与同会话 MEMORY 索引子串误判同形）。
    #    ⭐ 与 coverage-check 的口径在「可发射行」上一致：纯注释行本来就不参与覆盖率。
    _BODY = re.search(r"## 2\. 决策流程.*?```python\n(.*?)\n```", S, re.S).group(1)
    if re.search(r'^[ \t]*[^#\s][^\n]*#\s*pragma: unreachable-by-config', _BODY, re.M):
        _wp = re.search(r"WALLET_PREF = \{(.*?)\n\}", S, re.S).group(1)
        def _pairs(block):
            out = {}
            for mm in re.finditer(r"'([a-z0-9.\-]+)':\s*\[(.*?)\]", block, re.S):
                out[mm.group(1)] = re.findall(r"\('([^']+)',\s*'([^']+)'\)", mm.group(2))
            return out
        for _model, _peers in sk_peers.items():
            _pool_provs = {u2 for u2, _ in _pairs(_wp).get(_model, [])}
            _extra = sorted({u2 for u2, _ in _peers} - _pool_provs)
            chk(not _extra,
                f"⛔ `{_model}` 的 peer provider {_extra} 不在它的 WALLET_PREF 池里 ⇒ "
                f"「同档换落点」分支**重新可达** ⇒ 必须删掉 SKILL 里的 "
                f"`# pragma: unreachable-by-config` 并补用例")

    # 🔴 §3n routing §0「派发链唯一真源」必须与 SKILL 实际执行的 LADDER / T0 一致
    #    起因（2026-09-24 异构审 gpt-5.5 FAIL）：routing §0 停在 09-10 前整两周 —— T0 仍是 hy4-preview、
    #    T3 仍是已全局禁用的 deepseek-v4-pro、T4 仍是别名 kimi-k3-2，而 SKILL 开头写着「以 routing 为准」。
    #    ⇒ 本脚本原先对 routing 只搜旧语、⛔ 不比结构，于是漂了没人知道。
    # ⚠️ 只抽「带 @thinking 的型号行」：§0 里每个落点都写成 `model @档位`；没有 @ 的续行（说明、箭头）⛔ 不是落点，故意不抽
    # ⚠️ 2026-09-29 改：落点 token 取「@ 之前的整段非空白」—— model id 里可以有 `/`（stealth/space-bunny-alpha），
    #    旧正则 `(?:[a-z-]+/)?([a-z0-9…]+)` 会把它切成 `space-bunny-alpha`。前缀（cb/ · or/ · qcn/）比对时再剥。
    LEVELS = r'(minimal|low|medium|high|xhigh|max|none)'
    def routing_chain(text):
        blk = re.search(r"## 0\. 派发链.*?```\n(.*?)\n```", text, re.S)
        if not blk: return None
        out, tier = {}, None
        for line in blk.group(1).splitlines():
            mt = re.match(r'(T[0-4])\s', line)
            if mt: tier = mt.group(1)
            elif line[:1].strip(): tier = None          # 顶格非 T* 行（如「兜底」）⇒ 离开阶梯
            if tier is None: continue
            for mm in re.finditer(rf'(\S+)\s+@{LEVELS}\b', line):
                out.setdefault(tier, []).append((mm.group(1), mm.group(2)))
        return out
    def _strip(tok, known):
        return next((k for k in known if tok == k or tok.endswith('/' + k)), tok)
    _rc = routing_chain(R)
    chk(_rc is not None, "routing 找不到 §0 派发链代码块")
    if _rc:
        _ladder = re.findall(r"\('([a-z0-9._\-]+)',", re.search(r"LADDER\s*=\s*\[(.*?)\]", S, re.S).group(1))
        # 🔴 T0 由 FREE_POOL 推（⛔ 不再匹配 `for m in (...): # T0` —— 09-29 起没有那个循环了）
        chk(bool(SK_FP), "SKILL 里找不到 FREE_POOL 字面量（T0 免费池登记表）")
        # ⭐ 连 provider 前缀一起比（审查 r2：只比 model 时 `cb/stealth/space-bunny-alpha` 这种错前缀也会通过）
        _t0_want = [(chAbbr.get(x['upstream'], '?').lower(), x['model'], x['thinking'] or 'none') for x in SK_FP]
        _t0_got = []
        for t, lv in _rc.get('T0', []):
            mm_ = _strip(t, [x['model'] for x in SK_FP])
            _t0_got.append((t[:-len(mm_) - 1].lower() if t.endswith('/' + mm_) else '', mm_, lv))
        chk(_t0_got == _t0_want,
            f"⛔ routing §0 的 T0 {_t0_got} ≠ SKILL FREE_POOL（按 priority，含思考档）{_t0_want}")
        for i, m in enumerate(_ladder):
            got = [_strip(t, _ladder) for t, _ in _rc.get(f'T{i+1}', [])]
            chk(got == [m], f"⛔ routing §0 的 T{i+1} {got} ≠ SKILL LADDER 的 {m!r}")
        # 🔴 §0 每条免费落点后面那句「avoid 算法 / 性能 / …」是**散文**，⛔ 不在上面的结构比对范围内
        #    ——审查 r3 抓到：qfmodel 新加了 perf 之后，SKILL/catalog/§2.b/§6 都同步了，唯独这行没改。
        #    ⇒ 解析这句「avoid <中文项 / 中文项>」，把中文映射回 task_type，逐条目跟 FREE_POOL 的 avoidTaskTypes 比对。
        _ZH2TT = {'算法': 'algorithm', '性能': 'perf', '架构': 'architecture'}
        _blk = re.search(r"## 0\. 派发链.*?```\n(.*?)\n```", R, re.S).group(1)
        for x in SK_FP:
            _line = next((ln for ln in _blk.splitlines() if f"/{x['model']}" in ln or ln.strip().split()[0:1] == [x['model']]), None)
            chk(_line is not None, f"⛔ routing §0 里找不到免费条目 {x['model']} 所在的行")
            if _line is None: continue
            _m = re.search(r'avoid\s+([^；;]+)', _line)
            _got_zh = set(re.findall(r'算法|性能|架构', _m.group(1))) if _m else set()
            _got_tt = {_ZH2TT[z] for z in _got_zh}
            chk(_got_tt == set(x['avoidTaskTypes']),
                f"⛔ routing §0 里 {x['model']} 的 avoid 中文列表 {sorted(_got_zh)}（⇒{sorted(_got_tt)}）"
                f" ≠ FREE_POOL.avoidTaskTypes {sorted(x['avoidTaskTypes'])}")

    # 🔴 §3k 失败形态表必须与 catalog 一致，且**必须被真正读取**
    fm = re.search(r"FAILURE_SHAPES\s*=\s*\{(.*?)\n\}", S, re.S)
    chk(fm is not None, "SKILL 里找不到 FAILURE_SHAPES")
    if fm:
        sk_fs = dict(re.findall(r"'([a-z_]+)':\s*'([a-z]+)'", fm.group(1)))
        cat_fs = d.get('failureShapes', {}).get('shapes', {})
        chk(sk_fs == cat_fs, f"失败形态表 SKILL={sk_fs} ≠ catalog={cat_fs}")
        # ⚠️ ⛔ 别硬匹配某一行字面 —— 上一版守卫就是这样，改成 f.get(...) 后它立刻假红。
        #    判据：`failed_paid_tiers_in_this_task` 的赋值表达式里必须出现 FAILURE_SHAPES。
        m2 = re.search(r"failed_paid_tiers_in_this_task = (.*?)\n(?=\S)", S, re.S)
        chk(m2 is not None and 'FAILURE_SHAPES' in m2.group(1),
            "⛔ FAILURE_SHAPES 没被 failed_paid_tiers 的计算读取 ⇒ 等于只写在散文里")
        # 🔴 缺省必须偏向【质量类】—— 缺省落到可用性类会把升档入口整条清零
        chk(m2 is not None and "'bad_output'" in m2.group(1),
            "⛔ shape 缺省必须是 'bad_output'（保留旧行为）—— 否则不带 shape 的历史失败全被忽略")
        chk('NO_RESPONSE_LIMIT' in S and 'dead_landings' in S,
            "⛔ 缺 NO_RESPONSE_LIMIT / dead_landings ⇒ 「不算做砸」会变成「原地无限重派」")
        chk('provider_affinity' in S and S.count('provider_affinity') >= 4,
            "⛔ provider_affinity 缺失或未被池排序读取（T0 碰墙必须留在同 provider）")

    # 🔴 §3j 产出校验清单必须与 catalog 一致，且**必须在 §2 里被真正读取**
    #    ⛔ 只声明一个集合不算落地 —— 那就是「规则只写在散文里」的变体。
    om = re.search(r"OUTPUT_VALIDATION_REQUIRED\s*=\s*\{(.*?)\n\}", S, re.S)
    chk(om is not None, "SKILL 里找不到 OUTPUT_VALIDATION_REQUIRED")
    if om:
        sk_ov = set(re.findall(r"'([A-Za-z0-9._\-]+)'", om.group(1)))
        cat_ov = set(d.get('outputValidationRequired', {}).get('models', []))
        chk(sk_ov == cat_ov, f"产出校验清单 SKILL={sorted(sk_ov)} ≠ catalog={sorted(cat_ov)}")
        chk(S.count('OUTPUT_VALIDATION_REQUIRED') >= 3,
            "⛔ OUTPUT_VALIDATION_REQUIRED 只被声明、没被读取 ⇒ 等于只写在散文里")
        chk('requires_output_validation = model in OUTPUT_VALIDATION_REQUIRED' in S,
            "⛔ 缺 `requires_output_validation = model in OUTPUT_VALIDATION_REQUIRED` —— 校验要求必须算进决策结果")

    # 🔴 §3i 全局禁用集必须与 catalog 一致（0910 新增那一层）
    gm = re.search(r"BLOCKED_MODELS_ANY_PROVIDER\s*=\s*\{(.*?)\}", S, re.S)
    chk(gm is not None, "SKILL 里找不到 BLOCKED_MODELS_ANY_PROVIDER")
    if gm:
        sk_any = set(re.findall(r"'([A-Za-z0-9._\-]+)'", gm.group(1)))
        cat_any = set(d.get('blockedModelsAnyProvider', {}).get('models', []))
        chk(sk_any == cat_any, f"全局禁用集 SKILL={sorted(sk_any)} ≠ catalog={sorted(cat_any)}")
        # ⛔ 全局禁用的型号⛔不得同时留在 LADDER / WALLET_PREF / TIER_PEERS 里（否则自动链路会去探活它）
        for mid in sorted(sk_any):
            chk(mid not in ladder, f"⛔ `{mid}` 已全局禁用，却仍在 LADDER 里 ⇒ 自动升档会探活它")
            wp_keys = set(re.findall(r"^\s*'([a-z0-9.\-]+)':\s*\[", wpref, re.M))
            chk(mid not in wp_keys, f"⛔ `{mid}` 已全局禁用，却仍是 WALLET_PREF 的键 ⇒ 自动链路会探活它")
            chk(mid not in sk_peers, f"⛔ `{mid}` 已全局禁用，却仍是 TIER_PEERS 的键")

    # 🔴 §3h 屏蔽必须覆盖该型号【在 catalog 里挂过的所有可达 provider】—— ⛔ 不靠人记得写全
    #    2026-09-10 异构审查（gpt-5.5）抓到：deepseek-v4-pro 漏了 volcengine-chat，
    #    而它在 EXEMPT_PROVIDERS 里 ⇒ 显式指定就能绕过 P0；SKILL 注释当时还写着「四个 provider 全写」。
    #    ⇒ 覆盖面必须由 **catalog 的 providers 表**推出来，⛔ 不能人肉列举。
    wl = re.search(r"WHITELIST\s*=\s*\{(.*?)\n\}", S, re.S)
    sk_wl = ({km.group(1): set(re.findall(r"'([A-Za-z0-9._/\-]+)'", km.group(2)))
              for km in re.finditer(r"'([a-z0-9.\-]+)':\s*\[(.*?)\]", wl.group(1), re.S)}
             if wl else {})
    dm = re.search(r"DISABLED_PROVIDERS\s*=\s*\[(.*?)\]", S, re.S)
    dis = set(re.findall(r"'([a-z0-9.\-]+)'", dm.group(1))) if dm else set()
    ARCHIVED = {'jdcloud-joyagent'}          # 配置已归档、不在 pi 里 ⇒ 派不出去
    # 🔴 ⛔ 只对**全局禁用**的型号要求「所有 provider 都覆盖」——
    #    provider-keyed 表里也有**正当的按家屏蔽**（0911：`deepseek-v4-flash` 只在百炼屏蔽，
    #    因为百炼上它是 403 死路径，而它在火山两套餐上照常是 T2 主力）。
    #    ⚠️ 原先这里对所有被屏蔽 id 都要求全覆盖 ⇒ 会把这种正当用法判成漏口（假红）。
    for mid in sorted(cat_any):
        mdl = d.get('models', {}).get(mid)
        if not isinstance(mdl, dict):
            continue                          # 型号不在 models 表里（如 doubao-* / glm-latest）⇒ 无 providers 可推
        for prov in (k for k in (mdl.get('providers') or {}) if not k.startswith('_')):
            if prov in dis or prov in ARCHIVED:
                continue                      # provider 级已停用，屏蔽名单不必重复
            if prov in sk_wl and mid not in sk_wl[prov]:
                continue                      # 白名单本身就拦住了（⚠️ 这里是「不必再断言」，⛔ 不是「不许屏蔽」）
            chk(mid in cat_blk.get(prov, set()),
                f"⛔ 屏蔽漏口：`{mid}` 在 catalog 里挂着 provider `{prov}`，"
                f"但 blockedModels['{prov}'] 里没有它 ⇒ 显式 --provider {prov} --model {mid} 可绕过 P0")

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

# ── 3g. 🔴 pi 配置里的【无版本别名】必须已进 BLOCKED_MODELS（用户 2026-09-10）──
#    ⚠️ 这条是**结构性**的：⛔ 不靠人记得屏蔽，而是扫 ~/.pi/agent/models.json 里所有
#       以 -latest / latest 结尾的 id，逐个断言它已被拦。将来新上的别名会自动被抓。
#    ⚠️ 豁免 provider ⛔ 不能靠「从白名单删掉」来拦（它们本来就不枚举）⇒ 只能靠 BLOCKED_MODELS。
if pi:
    import re as _re
    sk_blk_all = {}
    _m = _re.search(r"BLOCKED_MODELS\s*=\s*\{(.*?)\n\}", S, _re.S)
    if _m:
        for km in _re.finditer(r"'([a-z0-9.\-]+)':\s*\{(.*?)\}", _m.group(1), _re.S):
            sk_blk_all[km.group(1)] = set(_re.findall(r"'([A-Za-z0-9._\-]+)'", km.group(2)))
    for pname, pconf in pi.get('providers', {}).items():
        ms = pconf.get('models')
        ids = list(ms) if isinstance(ms, dict) else [
            (x.get('id') if isinstance(x, dict) else x) for x in (ms or [])]
        for mid in ids:
            if isinstance(mid, str) and _re.search(r'(^|[-_])latest$', mid):
                chk(mid in sk_blk_all.get(pname, set()),
                    f"⛔ `{pname}/{mid}` 是**无版本别名**却没进 BLOCKED_MODELS —— "
                    f"豁免 provider 只能靠屏蔽名单拦，⛔ 光在文档里写「不许派」拦不住")

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

# ── 3o. 🔴 T0 免费池：SKILL FREE_POOL ⇔ catalog freePool.entries，且每一条都真能派出去（2026-09-29）──
#    ⚠️ 登记表的承诺是「以后只改表」⇒ 表里任何一条写错（白名单漏加 / 缩写漏配 / thinking 口径不一），
#       派发时就会在 validate() 或拼标题那一步才炸 ⇒ 必须在这里提前拦。
FP_SEL = ('upstream', 'model', 'priority', 'freeUntil', 'thinking', 'multimodal',
          'avoidTaskTypes', 'cautionTaskTypes', 'retainsData', 'allowInSensitiveWorkspace')
FP_CAT_ONLY = ('creditRecord', 'verifyVia', 'evalRef', 'note')     # ⛔ 只在 catalog（不双写）
def _fp_norm(x):
    return {k: (sorted(x[k]) if isinstance(x.get(k), (set, list, tuple)) else x.get(k)) for k in FP_SEL}
cat_fp = sorted(d.get('freePool', {}).get('entries', []), key=lambda x: x.get('priority', 0))
chk(bool(cat_fp), "catalog 缺 freePool.entries")
chk([_fp_norm(x) for x in SK_FP] == [_fp_norm(x) for x in cat_fp],
    f"FREE_POOL SKILL≠catalog: SKILL={[_fp_norm(x) for x in SK_FP]} catalog={[_fp_norm(x) for x in cat_fp]}")
for x in cat_fp:
    miss = [k for k in FP_SEL + FP_CAT_ONLY if k not in x]
    chk(not miss, f"freePool 条目 {x.get('upstream')}/{x.get('model')} 缺字段 {miss}")
    chk(bool(x.get('verifyVia')), f"freePool {x.get('model')} 的 verifyVia 为空 —— 窗口过期后用户无从复核")
_prios = [x['priority'] for x in SK_FP]
chk(len(_prios) == len(set(_prios)), f"⛔ FREE_POOL priority 重复 {_prios} ⇒ 挑选顺序不确定")
_cap = set(re.findall(r"'([a-z_]+)'", re.search(r"CAPABILITY_BLOCKERS\s*=\s*\{(.*?)\}", S).group(1)))
_nt_line = re.search(r"^NO_THINKING_MODELS\s*=\s*(.*)$", S, re.M).group(1)
_nothink_base = set(re.findall(r"'([^']+)'", re.search(r"\{(.*?)\}", _nt_line).group(1)))
# ⭐ 免费条目那部分由 FREE_POOL 推（thinking=None）⇒ 断言「确实是推出来的」，⛔ 不是又手写了一份
chk("for e in FREE_POOL if e['thinking'] is None" in _nt_line,
    "⛔ NO_THINKING_MODELS 不再由 FREE_POOL 推导 ⇒ 新增无思考档的免费模型会被收尾补成 xhigh")
_pihosted = set(re.findall(r"'([a-z0-9.\-]+)'", re.search(r"PI_HOSTED\s*=\s*\((.*?)\)", S, re.S).group(1)))
_wl_sk = {km.group(1): set(re.findall(r"'([A-Za-z0-9._/\-]+)'", km.group(2)))
          for km in re.finditer(r"'([a-z0-9.\-]+)':\s*\[(.*?)\]",
                                re.search(r"WHITELIST\s*=\s*\{(.*?)\n\}", S, re.S).group(1), re.S)}
_dis = set(re.findall(r"'([a-z0-9.\-]+)'", re.search(r"DISABLED_PROVIDERS\s*=\s*\[(.*?)\]", S, re.S).group(1)))
_blk_any = set(re.findall(r"'([A-Za-z0-9._/\-]+)'", re.search(r"BLOCKED_MODELS_ANY_PROVIDER\s*=\s*\{(.*?)\}", S).group(1)))
from datetime import datetime as _DT
_r2b = re.search(r"### 2\.b .*?(?=\n### )", R, re.S)
_r2b = _r2b.group(0) if _r2b else None
chk(_r2b is not None, "routing 找不到 §2.b 能力短板表")
# ⑨ evalRef 必须指向 catalog 里真实存在的测评记录（`a · b` 多个、`a → 子键` 取 a）
for x in cat_fp:
    for part in str(x.get('evalRef', '')).split(' · '):
        head = part.split(' → ')[0].strip()
        chk(head in d, f"⛔ freePool {x.get('model')} 的 evalRef `{head}` 在 catalog 里不存在")
# ⑩ probe-models.sh 的默认清单必须以免费池三条（按 priority）打头 —— 否则「派前先探活」探不到免费档
_P = (B / 'scripts/probe-models.sh').read_text()
_def = re.search(r"^DEFAULT=\((.*?)\)", _P, re.S | re.M)
_def_ids = re.findall(r"\S+", _def.group(1)) if _def else []
_want = [f"{x['upstream']}/{x['model']}" for x in SK_FP]
chk(_def_ids[:len(_want)] == _want,
    f"⛔ probe-models.sh DEFAULT 前 {len(_want)} 项 {_def_ids[:len(_want)]} ≠ FREE_POOL 按 priority {_want}")
# ⑪ catalog 里的旧免费链（审查 r2：反残留正则只拦散文，catalog 的数值 / 布尔字段拦不住）⇒ 结构性比对
_ladder_ids = re.findall(r"\('([a-z0-9._\-]+)',", re.search(r"LADDER\s*=\s*\[(.*?)\]", S, re.S).group(1))
_et = d.get('dispatchDefaults', {}).get('entryTier', {})
for k, v in _et.items():
    if not isinstance(v, dict): continue
    chk('skipFreeTier' not in v, f"⛔ entryTier.{k} 仍有 skipFreeTier（整档跳过）—— 09-29 起按条目：用 skipFreeEntries")
    if 'skipFreeEntries' in v:
        _want_skip = [x['model'] for x in SK_FP if k in x['avoidTaskTypes']]
        chk(v['skipFreeEntries'] == _want_skip,
            f"⛔ entryTier.{k}.skipFreeEntries {v['skipFreeEntries']} ≠ 由 FREE_POOL avoid 推出的 {_want_skip}")
_rule = d.get('dispatchDefaults', {}).get('escalation', {}).get('rule', '')
_pos = [_rule.find(x) for x in [x['model'] for x in SK_FP] + _ladder_ids]
chk(all(p >= 0 for p in _pos) and _pos == sorted(_pos),
    f"⛔ dispatchDefaults.escalation.rule 与 FREE_POOL + LADDER 的顺序不一致：{_rule[:120]}")
# ⚠️ 上面只查「型号按序出现」，光这样能让「LAST_RESORT 无条件可用」这类错误描述蒙混过关（审查 r3 指出）。
#    ⇒ 额外钉两条历史上真出过错的措辞（0909 曾把 LAST_RESORT 当 T5 自动纳入升档；09-29 前 T0 曾是单模型整档跳过）：
chk('仅可用性耗尽' in _rule or 'LAST_RESORT' not in _rule,
    "⛔ escalation.rule 提到 LAST_RESORT 却没有「仅可用性耗尽」这类限定 —— 会让人以为它是阶梯里普通一档")
chk('逐条按条目判' in _rule or 'FREE_POOL' not in _rule,
    "⛔ escalation.rule 提到 FREE_POOL 却没说明是逐条判 —— 会让人以为撞额度会跳过整个 T0")
# 🔴 `selectableByDefault=true` 的型号必须真在某条自动路径上（阶梯 / 池 / 同档替代 / 免费池），且⛔不许是被禁型号
#    —— hy4-preview 09-15 弃用后仍标 true + dispatchRank 1，agent 读数值字段会当它是第一顺位（审查 r2）
_auto = set(_ladder_ids) | {x['model'] for x in SK_FP}
_auto |= {mid for _u, mid in re.findall(r"\('([^']+)',\s*'([^']+)'\)", re.search(r"WALLET_PREF = \{(.*?)\n\}", S, re.S).group(1))}
_auto |= {mid for _u, mid in re.findall(r"\('([^']+)',\s*'([^']+)'\)", re.search(r"TIER_PEERS\s*=\s*\{(.*?)\n\}", S, re.S).group(1))}
for mid, ent in d.get('models', {}).items():
    if isinstance(ent, dict) and ent.get('selectableByDefault') is True:
        chk(mid in _auto, f"⛔ models['{mid}'].selectableByDefault=true，但它不在任何自动路径上（阶梯/池/同档/免费池）")
        chk(mid not in _blk_any, f"⛔ models['{mid}'] 已全局禁用却仍 selectableByDefault=true")
for x in SK_FP:
    u, m = x['upstream'], x['model']
    # ⑫ catalog-only 字段⛔不许在 SKILL 里双写（双写就会漂）
    _dup = [k for k in FP_CAT_ONLY + ('quota', 'userDecisions') if k in x]
    chk(not _dup, f"⛔ SKILL FREE_POOL 的 {m} 双写了 catalog-only 字段 {_dup}")
    # ① 能过 validate()：白名单型 provider 必须列了它；否则必须在豁免集；且⛔不在停用 / 全局禁用里
    chk(u not in _dis, f"⛔ 免费条目 {u}/{m} 的 provider 已停用")
    chk(m not in _blk_any, f"⛔ 免费条目 {m} 已全局禁用")
    chk((u in _wl_sk and m in _wl_sk[u]) or (u not in _wl_sk and u in sk),
        f"⛔ 免费条目 {u}/{m} 过不了 validate()：白名单没列它，provider 也不在豁免集")
    # ② avoid 只许写能力类 —— 否则 --free 放宽的语义就不成立（§2 里有同一条 assert）
    chk(set(x['avoidTaskTypes']) <= _cap,
        f"⛔ {m} 的 avoidTaskTypes {sorted(x['avoidTaskTypes'])} 超出能力类 {sorted(_cap)}")
    chk(not (set(x['avoidTaskTypes']) & set(x['cautionTaskTypes'])),
        f"⛔ {m} 同一任务类既 avoid 又 caution —— 自相矛盾")
    # ③ 手写的那部分⛔不许与条目矛盾：条目说有思考档，手写集合却把它列成无思考档 ⇒ 收尾会把档位置空
    chk(not (x['thinking'] is not None and m in _nothink_base),
        f"⛔ {m}: 条目 thinking={x['thinking']!r}，但被手写进 NO_THINKING_MODELS")
    # ④ 标题缩写（派发时拼 `· 渠道-模型`）
    chk(u in chAbbr and m in mdAbbr, f"⛔ 免费条目 {u}/{m} 缺渠道或模型缩写")
    # ⑤ 🔴 豁免自带失效条件：D2（用户 09-29）之后没有条目需要「敏感目录闸门」，所以**没写闸门代码**。
    #    一旦出现「会留存数据 且 不许进公司目录」的条目，这个前提就不成立 ⇒ 必须先实现闸门再加条目。
    chk(not (x['retainsData'] is True and not x['allowInSensitiveWorkspace']),
        f"⛔ {m} 标了 retainsData=True 且不允许敏感目录，但 §2 **没有**敏感目录闸门 —— 先实现闸门再加这条")
    # ⑥ pi 宿主的免费落点必须真在 pi 配置里注册了（否则 Paseo 串 pi/<u>/<m> 派不出去）
    if pi and u in _pihosted:
        _ids = [mm.get('id') for mm in pi.get('providers', {}).get(u, {}).get('models', [])]
        chk(m in _ids, f"⛔ 免费条目 {u}/{m} 不在 ~/.pi/agent/models.json 的 {u} 里")
    # ⑧ routing §2.b 的 avoid 表必须与条目一致（审查 09-29：只比了 SKILL⇔catalog，散文表会漂）
    _row = re.search(rf"^\| `{re.escape(m)}` \| ([^|]*)\|", _r2b, re.M) if _r2b else None
    chk(_row is not None, f"⛔ routing §2.b 表里没有 `{m}` 这一行")
    if _row:
        chk(set(re.findall(r"`([a-z_]+)`", _row.group(1))) == set(x['avoidTaskTypes']),
            f"⛔ routing §2.b `{m}` 的 avoid 列 {sorted(re.findall(r'`([a-z_]+)`', _row.group(1)))} ≠ 条目 {sorted(x['avoidTaskTypes'])}")
    # ⑦ 截止已过 ⇒ ⚠️ 只提醒（逻辑上会自动跳过 / 走复核），⛔ 不致失败
    if x['freeUntil']:
        warn(_DT.now() <= _DT.fromisoformat(x['freeUntil']),
             f"免费条目 {u}/{m} 已过 freeUntil={x['freeUntil']} —— 该延期就更新、该下线就删条目")

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
if w: print("\n".join("⚠️  " + x for x in w))
sys.exit(1 if e else 0)
