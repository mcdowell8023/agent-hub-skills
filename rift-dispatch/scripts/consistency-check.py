#!/usr/bin/env python3
"""rift-dispatch 跨文件一致性机械校验 —— 每次改路由规则后跑一遍。

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

# ── 1. 豁免集三处一致，且 pi / jdcloud / deepseek 都不在里面 ──
sk  = set(re.findall(r"'([a-z0-9._\-]+)'",
      re.search(r"EXEMPT_PROVIDERS\s*=\s*\[(.*?)\]", S, re.S).group(1)))
cat = set(k for k in d['whitelist']['exempt'] if not k.startswith('_'))
chk(sk == cat, f"豁免集 SKILL≠catalog: {sorted(sk ^ cat)}")
for bad in ('pi', 'jdcloud-joyagent', 'deepseek'):
    chk(bad not in sk,  f"⛔ {bad} 不该在 SKILL EXEMPT")
    chk(bad not in cat, f"⛔ {bad} 不该在 catalog exempt")

# ── 2. 白名单三处一致 ──
for prov in ('codebuddy-code', 'qoderclicn', 'jdcloud-joyagent'):
    w = set(d['whitelist'][prov])
    m = re.search(rf"'{re.escape(prov)}':\s*\[(.*?)\]", S, re.S)
    chk(m is not None, f"SKILL 缺 {prov} 白名单")
    if m:
        chk(w == set(re.findall(r"'([A-Za-z0-9._\-]+)'", m.group(1))),
            f"{prov} 白名单 SKILL≠catalog")

# ── 3. 钱包首选三处一致 + JD 必须大写 modelId ──
wp = d['walletPriority']['modelProviderPreference']
wpref = re.search(r"WALLET_PREF = \{(.*?)\n\}", S, re.S).group(1)
for m, v in wp.items():
    seg = wpref.split(f"'{m}'")
    chk(len(seg) > 1, f"SKILL WALLET_PREF 缺 {m}")
    if len(seg) > 1:
        first = re.search(r"\('([a-z0-9._\-]+)'", seg[1])
        chk(first and first.group(1) == v['first'],
            f"{m} 首选 SKILL={first.group(1) if first else None} catalog={v['first']}")
chk("('jdcloud-joyagent',  'DeepSeek-V4-pro')" in S, "⛔ JD modelId 必须是大写 DeepSeek-V4-pro")
chk(wp['deepseek-v4-flash'].get('noJdcloud') is True, "flash 必须标 noJdcloud")
chk('jdcloud' not in re.search(r"'deepseek-v4-flash':.*?\],", S, re.S).group(0),
    "WALLET_PREF flash 不该含京东")

# ── 4. 🔴 伪代码结构：单一线性管线 ──
body = re.search(r"## 2\. 决策流程.*?```python\n(.*?)\n```", S, re.S).group(1)
for fn in ('split_provider', 'normalize_provider', 'validate', ):
    chk(f'def {fn}' in body, f"缺 {fn}()")
chk('goto' not in body, "⛔ 伪代码里不许有 goto（会跳过初始化）")
# 提前 return 只允许 helper 函数内 + 一处有标注的 --free 出口
def strip_comment(l):            # ⚠️ 必须剥注释：注释里写「⛔ 不 return」会被误判
    return l.split('#', 1)[0]
code = [strip_comment(l) for l in body.split('\n')]
in_fn = False; top_returns = []
for l in code:
    if re.match(r'^def ', l): in_fn = True; continue
    if l.strip() and not l.startswith((' ', '\t')): in_fn = False
    if in_fn: continue                                   # 函数体内的 return 合法
    if re.search(r'\breturn\b', l) and 'rift-free' not in l:
        top_returns.append(l.strip())
chk(not top_returns, f"⛔ 顶层提前 return（会绕过统一收尾）: {top_returns[:2]}")

# 🔴 「变量用了但没赋值点」—— 第三轮栽在 scope / channel 上
USED = set(re.findall(r"\b([a-z_][a-z0-9_]*)\b(?=\s*[),])", body))
for var in ('scope', 'channel', 'thinking', 'task_type', 'upstream', 'model'):
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
