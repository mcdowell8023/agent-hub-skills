#!/usr/bin/env python3
"""rift-dispatch 跨文件一致性机械校验 —— 每次改路由规则后跑一遍。

⚠️ 正则字符类记得带 `_`（qmodel_38max 踩过），且别要求闭合括号紧跟。
⚠️ 本脚本报错时先判「是内容错还是脚本正则太窄」——本轮三条误报都是后者。
"""
import json, re, pathlib, sys
B=pathlib.Path('/Users/mcdowell/.claude/skills/rift-dispatch')
d=json.load(open(B/'model-catalog.json'))
S=(B/'SKILL.md').read_text(); R=(B/'model-routing.md').read_text(); C=(B/'CHANGELOG.md').read_text()
pi=json.load(open(pathlib.Path.home()/'.pi/agent/models.json'))
e=[]
def chk(cond,msg):
    if not cond: e.append(msg)

# 1. 豁免集三处一致，且 pi/jdcloud/deepseek 都不在里面
sk=set(re.findall(r"'([a-z0-9\-]+)'", re.search(r"EXEMPT_PROVIDERS\s*=\s*\[(.*?)\n\]", S, re.S).group(1)))
cat=set(k for k in d['whitelist']['exempt'] if not k.startswith('_'))
chk(sk==cat, f"豁免集 SKILL≠catalog: {sorted(sk^cat)}")
for bad in ('pi','jdcloud-joyagent','deepseek'):
    chk(bad not in sk, f"⛔ {bad} 不该在 SKILL EXEMPT")
    chk(bad not in cat, f"⛔ {bad} 不该在 catalog exempt")

# 2. 白名单三处一致
for prov in ('codebuddy-code','qoderclicn','jdcloud-joyagent'):
    w=set(d['whitelist'][prov])
    m=re.search(rf"'{re.escape(prov)}':\s*\[(.*?)\]", S, re.S)
    chk(m is not None, f"SKILL 缺 {prov} 白名单")
    if m: chk(w==set(re.findall(r"'([A-Za-z0-9._\-]+)'", m.group(1))), f"{prov} 白名单 SKILL≠catalog")

# 3. 钱包首选三处一致 + JD 用大写 modelId
wp=d['walletPriority']['modelProviderPreference']
wpref=re.search(r"WALLET_PREF = \{(.*?)\n\}", S, re.S).group(1)
for m,v in wp.items():
    seg=wpref.split(f"'{m}'")
    chk(len(seg)>1, f"SKILL WALLET_PREF 缺 {m}")
    if len(seg)>1:
        first=re.search(r"\('([a-z0-9._\-]+)'", seg[1])
        chk(first and first.group(1)==v['first'],
            f"{m} 首选 SKILL={first.group(1) if first else None} catalog={v['first']}")
chk("('jdcloud-joyagent',  'DeepSeek-V4-pro')" in S, "⛔ JD modelId 必须是大写 DeepSeek-V4-pro")
chk(wp['deepseek-v4-flash'].get('noJdcloud') is True, "flash 必须标 noJdcloud")
chk('jdcloud' not in re.search(r"'deepseek-v4-flash':.*?\],", S, re.S).group(0), "WALLET_PREF flash 不该含京东")

# 4. 伪代码关键函数齐全且被正确调用
for fn in ('split_provider','normalize_provider','build_settings'):
    chk(f'def {fn}' in S, f"缺 {fn}()")
chk('build_settings(provider, model, thinking)' in S, "模板调用签名与定义不符")
# ⚠️ 断言查【性质】，⛔ 别查具体实现字符串（改写法就假失败，本轮踩过）
chk('def validate(' in S, "缺统一的 validate()")
chk('upstream in WHITELIST' in S, "校验必须对 upstream 做")
chk(re.search(r'if args\.provider', S) is not None, "P1 必须单独处理只给 provider 的情况")
chk(S.count('validate(upstream, model)') >= 2, "validate 必须在 P1 与自动分支两处都调用")
chk(re.search(r'^channel = ', S, re.M) is not None, "channel 必须有赋值点（⛔ 不能是悬空变量）")
for dangling in ('pick_provider_for','default_model_for'):
    chk(dangling not in S, f"⛔ {dangling} 是悬空引用，无定义")

# 5. 审查按规模分流，无「审查整类 → pi -p」残留
chk('is_large_review' in S, "P4 未按规模分流")
for f,n in ((S,'SKILL'),(R,'routing')):
    chk('只读/短/审查类' not in f and '只读 / 短 / 审查类' not in f, f"{n} 仍写「审查类→pi -p」")
chk('审查=pi -p Copilot' not in json.dumps(d,ensure_ascii=False), "catalog matrix 仍写审查→pi -p")

# 6. providers map 已补齐首选
chk('volcengine-coding' in d['models']['glm-5.3-flash']['providers'], "glm-5.3-flash.providers 缺火山")
chk('jdcloud-joyagent' in d['models']['deepseek-v4-pro']['providers'], "deepseek-v4-pro.providers 缺京东")

# 7. pi 侧配置
cop=[m for m in pi['providers']['github-copilot']['models']]
chk(not any(m['id'].startswith('claude') for m in cop), "pi Copilot 仍有 claude")
chk(sorted(m['id'] for m in cop if m.get('unsupported'))==['gpt-5.4-nano','kimi-k2.7-code','kimi-k3'],
    "unsupported 标记不全")
for p_ in ('volcengine-coding','volcengine-agent-plan'):
    chk('glm-5.3-flash' in [m['id'] for m in pi['providers'][p_]['models']], f"pi {p_} 缺 glm-5.3-flash")

# 8. JSON 可解析（上面 load 成功即通过）
print("=== rift-dispatch 一致性校验 ===")
print("✅ 全部通过" if not e else "\n".join("❌ "+x for x in e))
sys.exit(1 if e else 0)
