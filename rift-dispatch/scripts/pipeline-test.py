#!/usr/bin/env python3
"""表驱动验证 SKILL.md §2 的派发管线 —— 🔴 直接【执行】markdown 里的伪代码。

⚠️ 为什么不是查字符串：上一版 `consistency-check.py` 只断言标识符出现过，
审查者构造 5 个真实破坏场景（channel 写死 cli / ENTRY 改 0 / review 换模型 /
normalize_provider 去掉 pi 前缀 / 新增未赋值变量）全部假绿。
⇒ 本脚本把 §2 的 ```python 块抽出来包成函数、注入桩、跑用例表断言落点。
   markdown 是唯一真源，⛔ 改坏它这里必红。
"""
import re, sys, pathlib, textwrap

B = pathlib.Path(__file__).resolve().parent.parent
SRC = (B / 'SKILL.md').read_text()
BODY = re.search(r"## 2\. 决策流程.*?```python\n(.*?)\n```", SRC, re.S).group(1)

class Blocked(Exception): pass
class Delegated(Exception): pass
class Exhausted(Exception): pass
class Result:
    def __init__(s): s.agent_id, s.run_id = 'ag-1', 'run-1'

# 京东侧 model id 大小写不同 —— 桩要如实反映，否则测不出大小写 bug
JD_ID = {'deepseek-v4-pro': 'DeepSeek-V4-pro', 'deepseek-v4-flash': 'DeepSeek-V4-Flash'}

def run_case(c):
    class A:
        model = c.get('model'); provider = c.get('provider')
        thinking = c.get('thinking'); free = c.get('free', False); worktree = None
    stub = {
        'parse_args':        lambda _: A,
        'user_input':        'x',
        'task_context':      None,
        'resolve_short_name': lambda m: {'v4-pro': 'deepseek-v4-pro'}.get(m, m),
        'classify':          lambda _: c['task_type'],
        'estimate_scope':    lambda *_: c.get('scope', 'small'),
        'resolve_worktree':  lambda _: '/tmp/wt',
        'count_failed_paid_tiers': lambda _: c.get('failed', 0),
        'excluded_from_free': lambda tt, a: c.get('free_excluded', False),
        'promo_active':      lambda m: c.get('promo_ok', True),
        'probe_ok':          lambda m: c.get('probe_ok', True),
        'first_available':   lambda lst: lst[0],
        'model_id_on':       lambda u, m: JD_ID.get(m, m) if u == 'jdcloud-joyagent' else m,
        'is_dev_task':       lambda tt: tt not in ('review',),
        'is_large_review':   lambda sc: sc == 'large',
        'provider_available': lambda u: True,
        'downgrade':         lambda u, m: (u, m),
        'clamp_to_supported': lambda m, t: t,
        'default_thinking':  lambda m: 'high' if m.startswith('hy') else 'xhigh',
        'execute':           lambda *a: Result(),
        'save_memory':       lambda **k: None,
        'print_summary':     lambda: None,
        'warn':              lambda *a: None,
        'delegate':          lambda n: (_ for _ in ()).throw(Delegated(n)),
        'report_disabled_and_stop':         lambda: (_ for _ in ()).throw(Blocked('disabled')),
        'report_conflict_and_stop':         lambda: (_ for _ in ()).throw(Blocked('conflict')),
        'report_unknown_provider_and_stop': lambda: (_ for _ in ()).throw(Blocked('unknown')),
        'report_ladder_exhausted_and_stop': lambda: (_ for _ in ()).throw(Exhausted()),
    }
    src = ("def _decide():\n" + textwrap.indent(BODY, '    ')
           + "\n    return dict(upstream=upstream, model=model, provider=provider,"
             " channel=channel, thinking=thinking)\n")
    ns = dict(stub)
    exec(compile(src, '<SKILL.md §2>', 'exec'), ns)     # 🔴 NameError 会在这里炸出来
    return ns['_decide']()

# ── 用例表：必须与 SKILL.md §3「派发路径用例」一致 ──
CASES = [
 # 拦截类
 dict(n='JD+GLM 必拦', provider='jdcloud-joyagent', model='GLM-5.2', task_type='core', block='conflict'),
 dict(n='pi/JD+GLM 必拦', provider='pi/jdcloud-joyagent', model='GLM-5.2', task_type='core', block='conflict'),
 dict(n='已停用 provider 必拦', provider='deepseek', model='deepseek-v4-pro', task_type='core', block='disabled'),
 dict(n='未知 provider 必拦', provider='nosuch', model='x', task_type='core', block='unknown'),
 # 放行类
 dict(n='JD+pro 放行且带 pi 前缀', provider='pi/jdcloud-joyagent', model='DeepSeek-V4-pro',
      task_type='core', want=dict(provider='pi/jdcloud-joyagent', model='DeepSeek-V4-pro', channel='paseo')),
 dict(n='火山显式放行', provider='volcengine-coding', model='deepseek-v4-flash', task_type='core',
      want=dict(provider='pi/volcengine-coding', model='deepseek-v4-flash', channel='paseo')),
 # 阶梯类
 dict(n='T0 免费档', task_type='core',
      want=dict(upstream='codebuddy-code', model='hy4-preview', thinking='high')),
 dict(n='T1 起步（免费档被排除）', task_type='core', free_excluded=True,
      want=dict(upstream='volcengine-coding', model='glm-5.3-flash', provider='pi/volcengine-coding')),
 dict(n='T3 落京东且大写 id', task_type='core', free_excluded=True, failed=2,
      want=dict(upstream='jdcloud-joyagent', model='DeepSeek-V4-pro', provider='pi/jdcloud-joyagent')),
 dict(n='T4 落 K3', task_type='core', free_excluded=True, failed=3,
      want=dict(model='kimi-k3-2')),
 dict(n='超 T4 必停', task_type='core', free_excluded=True, failed=4, exhausted=True),
 dict(n='algorithm 跳 T0 从 T2 起', task_type='algorithm', free_excluded=True,
      want=dict(model='deepseek-v4-flash', upstream='volcengine-coding')),
 # 审查类
 dict(n='大审查走 Paseo', task_type='review', scope='large',
      want=dict(upstream='github-copilot', model='gpt-5.5',
                provider='pi/github-copilot', channel='paseo')),
 dict(n='短审查走 CLI', task_type='review', scope='small',
      want=dict(upstream='github-copilot', model='gpt-5.5',
                provider='github-copilot', channel='cli')),
 # 显式值不得被覆盖
 dict(n='只给 model 不被 T0/阶梯覆盖', model='v4-pro', task_type='core',
      want=dict(model='DeepSeek-V4-pro', upstream='jdcloud-joyagent')),
 dict(n='只给 provider 不被 T0 换成 cb', provider='volcengine-coding', task_type='core',
      want=dict(upstream='volcengine-coding')),
 # 委派
 dict(n='--free 委派', free=True, task_type='core', delegated=True),
]

fails = []
for c in CASES:
    try:
        got = run_case(c)
        if c.get('block'):     fails.append(f"{c['n']}: 期望被拦({c['block']})，实际放行 {got}"); continue
        if c.get('delegated'): fails.append(f"{c['n']}: 期望委派，实际 {got}"); continue
        if c.get('exhausted'): fails.append(f"{c['n']}: 期望阶梯到顶停止，实际 {got}"); continue
        for k, v in c['want'].items():
            if got.get(k) != v:
                fails.append(f"{c['n']}: {k} 期望 {v!r} 实际 {got.get(k)!r}")
    except Blocked as e:
        if c.get('block') != str(e): fails.append(f"{c['n']}: 被拦于 {e}，期望 {c.get('block')}")
    except Delegated:
        if not c.get('delegated'): fails.append(f"{c['n']}: 意外委派")
    except Exhausted:
        if not c.get('exhausted'): fails.append(f"{c['n']}: 意外报阶梯到顶")
    except NameError as e:
        fails.append(f"{c['n']}: 🔴 伪代码里有未定义名 —— {e}")
    except Exception as e:
        fails.append(f"{c['n']}: {type(e).__name__}: {e}")

print("=== §2 管线表驱动验证 ===")
print(f"用例 {len(CASES)} 条")
print("✅ 全部通过" if not fails else "\n".join("❌ " + f for f in fails))
sys.exit(1 if fails else 0)
