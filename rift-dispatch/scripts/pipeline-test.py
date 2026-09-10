#!/usr/bin/env python3
"""表驱动验证 SKILL.md §2 的派发管线 —— 🔴 直接【执行】markdown 里的伪代码。

⚠️ 为什么不是查字符串：上一版 `consistency-check.py` 只断言标识符出现过，
审查者构造 5 个真实破坏场景（channel 写死 cli / ENTRY 改 0 / review 换模型 /
normalize_provider 去掉 pi 前缀 / 新增未赋值变量）全部假绿。
⇒ 本脚本把 §2 的 ```python 块抽出来包成函数、注入桩、跑用例表断言落点。
   markdown 是唯一真源，⛔ 改坏它这里必红。
"""
import re, sys, pathlib, textwrap
from datetime import datetime as DT

B = pathlib.Path(__file__).resolve().parent.parent
SRC = (B / 'SKILL.md').read_text()
BODY = re.search(r"## 2\. 决策流程.*?```python\n(.*?)\n```", SRC, re.S).group(1)

class Blocked(Exception): pass
class Delegated(Exception): pass
class Exhausted(Exception): pass
class FreeUnavailable(Exception): pass      # 0909: --free 但拿不到 T0
class ConflictFreeReview(Exception): pass   # 0909: --free 撞 review 硬例外
class ReviewProviderConflict(Exception): pass  # 0909 第 6 轮: review 的 provider 被显式改成非 Copilot
class NoLanding(Exception): pass            # 0909: 本档在所有池+同档替代里都没有可用落点
class BlockedModel(Exception): pass         # 0909: 用户点名屏蔽的型号
class Result:
    def __init__(s): s.agent_id, s.run_id = 'ag-1', 'run-1'

# provider 侧 modelId 可能与阶梯里的写法不同（京东曾是大写）。⚠️ 京东 2026-09-09 停用后
# 当前无此类差异，桩保留能力以便将来恢复时仍测得出大小写 bug。
PROVIDER_ID = {'jdcloud-joyagent': {'deepseek-v4-pro': 'DeepSeek-V4-pro',
                                    'deepseek-v4-flash': 'DeepSeek-V4-Flash'}}

def run_case(c):
    class A:
        model = c.get('model'); provider = c.get('provider')
        thinking = c.get('thinking'); free = c.get('free', False); worktree = None
    stub = {
        'parse_args':        lambda _: A,
        'user_input':        'x',
        'task_context':      None,
        'resolve_short_name': lambda m: {'v4-pro': 'deepseek-v4-pro'}.get(m, m),
        # ⚠️ 空串要原样透传 —— 空 --model 的校验靠 args.model 本身，⛔ 不靠 resolve 结果
        'classify':          lambda _: c['task_type'],
        'estimate_scope':    lambda *_: c.get('scope', 'small'),
        'resolve_worktree':  lambda _: '/tmp/wt',
        # 🔴 按【档 + 形态】给，⛔ 不是给个计数 —— 形态决定它算不算「做砸」
        'past_failures': lambda _: (
            [{'tier': i, 'shape': 'bad_output'} for i in range(c.get('failed', 0))]
            + list(c.get('extra_failures', []))),
        'free_blockers':     lambda tt, a: set(c.get('blockers', ())),
        'CAPABILITY_BLOCKERS': {'algorithm', 'perf', 'architecture'},
        'promo_active':      lambda m: c.get('promo_ok', True),
        # 🔴 ⛔ 不桩 rate_reverified 本身 —— 它现在在 §2 里有**真定义**，
        #    桩掉它就等于不测那段逻辑（含「核实记录必须够新」这一条）。
        #    ⇒ 只桩它的两个外部依赖。
        'catalog_credit_record': lambda m: c.get('credit_records', {}).get(m),
        'days_between':      lambda a, b: (b - __import__('datetime').datetime.fromisoformat(a)).days,
        'probe_ok':          lambda m: c.get('probe_ok', True),
        # ⚠️ 桩要能表达「某些落点不可用」，否则 TIER_PEERS 兜底分支永远测不到
        'first_available':   lambda lst: (PROBES.extend(f'{u}/{m}' for u, m in lst) or next(
            ((u, m) for u, m in lst if f'{u}/{m}' not in set(c.get('unavailable', ()))), None)),
        'model_id_on':       lambda u, m: PROVIDER_ID.get(u, {}).get(m, m),
        # ⚠️ force_cli 是【测试专用】旋钮：review 改成顶层分支后，review 永远落 copilot，
        #    自然路径下已没有「cli 规模的任务走到 LAST_RESORT」这条 —— 但那个 channel 守卫
        #    是**防御性**的（防将来改 is_dev_task），仍要测得到。
        'is_dev_task':       lambda tt: (not c.get('force_cli')) and tt not in ('review',),
        'is_large_review':   lambda sc: sc == 'large',
        'now':               lambda: c.get('when', __import__('datetime').datetime(2026,9,10,15,0)),
                             # ⚠️ 默认取【工作日 15:00】= 两家都原价，避免用例被折扣顺序影响
        # ⚠️ 0909 第 4 轮起，provider_available / downgrade 已【不在 §2 管线里】——
        #    可用性只有一套真源（§5 的 first_available）。桩保留只为兼容 §6 前置检查表。
        'provider_available': lambda u: u not in set(c.get('dead_providers', ())),
        # ⚠️ 桩要能表达「旧 downgrade() 换成低档模型」，否则 §6 的降档风险测不到
        'downgrade':         lambda u, m: c.get('downgrade_to', (u, m)),
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
        'report_free_unavailable_and_stop': lambda b=None: (_ for _ in ()).throw(FreeUnavailable()),
        'report_conflict_free_vs_review_and_stop': lambda: (_ for _ in ()).throw(ConflictFreeReview()),
        'report_review_provider_conflict_and_stop': lambda *a: (_ for _ in ()).throw(ReviewProviderConflict()),
        'report_no_landing_and_stop': lambda m=None: (_ for _ in ()).throw(NoLanding()),
        'report_blocked_model_and_stop': lambda *a: (_ for _ in ()).throw(BlockedModel()),
        'report_provider_model_mismatch_and_stop': lambda *a: (_ for _ in ()).throw(Blocked('mismatch')),
    }
    src = ("def _decide():\n" + textwrap.indent(BODY, '    ')
           + "\n    return dict(upstream=upstream, model=model, provider=provider,"
             " channel=channel, thinking=thinking,"
             " availability_escalations=availability_escalations,"
             " tier_substitutions=tier_substitutions,"
             " requires_output_validation=requires_output_validation,"
             " t0_free_unverified=t0_free_unverified)\n")
    ns = dict(stub)
    exec(compile(src, '<SKILL.md §2>', 'exec'), ns)     # 🔴 NameError 会在这里炸出来
    return ns['_decide']()

# ── 用例表：必须与 SKILL.md §3「派发路径用例」一致 ──
PROBES = []          # 🔴 记录 first_available 探过哪些落点（供 no_probe 断言）

CASES = [
 # 拦截类
 dict(n='cb 白名单外必拦', provider='codebuddy-code', model='GLM-5.2', task_type='core', block='conflict'),
 dict(n='已停用 provider 必拦', provider='deepseek', model='deepseek-v4-pro', task_type='core', block='disabled'),
 dict(n='未知 provider 必拦', provider='nosuch', model='x', task_type='core', block='unknown'),
 # ⛔ 京东 2026-09-09 停用 —— 已移出白名单与豁免集 ⇒ 现在应落「未知 provider」被拦
 dict(n='京东已停用必拦', provider='jdcloud-joyagent', model='DeepSeek-V4-pro',
      task_type='core', block='unknown'),
 dict(n='pi/京东同样必拦', provider='pi/jdcloud-joyagent', model='DeepSeek-V4-pro',
      task_type='core', block='unknown'),
 # 🔴 覆盖率发现的缺口：空 --model 是输入错误，⛔ 不是「没指定」
 dict(n='空 --model → 报冲突（⛔ 不当成没指定）', model='   ', task_type='core', block='conflict'),
 # 🔴 第 7 轮审查：review + 非 Copilot provider 必须报【review 冲突】，⛔ 不是 P0 的 disabled/whitelist
 dict(n='review + deepseek → 报 review 冲突（⛔ 不是 disabled）', task_type='review', scope='small',
      provider='deepseek', model='deepseek-v4-pro', review_provider_conflict=True),
 dict(n='review + cb → 报 review 冲突（⛔ 不是白名单冲突）', task_type='review', scope='small',
      provider='codebuddy-code', model='gpt-5.5', review_provider_conflict=True),
 # ⛔ 非 review 时 P0 照常先拦
 dict(n='非 review + deepseek 仍报 disabled', task_type='core',
      provider='deepseek', model='deepseek-v4-pro', block='disabled'),
 # 🔴 用户点名屏蔽的型号（2026-09-09）—— ⛔ 豁免 provider 也拦得住
 dict(n='火山 Doubao 必拦', provider='volcengine-coding', model='doubao-seed-2.1-turbo',
      task_type='core', blocked_model=True),
 dict(n='火山 ark-code-latest 必拦', provider='pi/volcengine-agent-plan', model='ark-code-latest',
      task_type='core', blocked_model=True),
 dict(n='Copilot gpt-5-mini 必拦', provider='github-copilot', model='gpt-5-mini',
      task_type='core', blocked_model=True),
 dict(n='Copilot mai-code-1-flash-picker 必拦', provider='github-copilot',
      model='mai-code-1-flash-picker', task_type='core', blocked_model=True),
 # 🔴 全局禁用型号（0910 异构审 gpt-5.5 连开两枪，两条都是真路径）
 #   ① provider-keyed 表结构上拦不住「没列过的 provider」
 dict(n='全局禁用：--provider github-copilot --model deepseek-v4-pro 必拦',
      provider='github-copilot', model='deepseek-v4-pro', task_type='core',
      blocked_model=True, no_probe=True),
 #   ② 只给 --model 不给 provider 时，§1 的 validate() 压根不执行
 #      ⇒ 这条不只要「被拦」，还要**拦在任何探活之前**（no_probe）
 dict(n='全局禁用：只给 --model deepseek-v4-pro（无 provider）必拦且⛔不探活',
      model='deepseek-v4-pro', task_type='core', blocked_model=True, no_probe=True),
 # ⛔ 反例：没被点名的⛔不许误伤
 dict(n='Copilot gpt-5.5 照常放行', provider='github-copilot', model='gpt-5.5',
      task_type='core', want=dict(upstream='github-copilot', model='gpt-5.5')),
 dict(n='待测的 grok-4.6 ⛔ 不在屏蔽名单里', provider='github-copilot', model='grok-4.6',
      task_type='core', want=dict(upstream='github-copilot', model='grok-4.6')),
 # 放行类
 dict(n='火山显式放行且带 pi 前缀', provider='volcengine-coding', model='deepseek-v4-flash',
      task_type='core', want=dict(provider='pi/volcengine-coding', model='deepseek-v4-flash', channel='paseo')),
 # 阶梯类
 # 🔴 免费窗口已过但仍探活通过 ⇒ ⛔ 不当免费档用（费率未核），但**必须提示**
 #    实测背景：2026-09-11 记录的免费期已过，hy4-preview 仍 7s 秒回 ⇒ 延期或已计费，两头都不能赌。
 dict(n='免费窗口过期但仍探活通过 ⇒ 落 T1 且提示费率待核', task_type='core', promo_ok=False,
      want=dict(upstream='codebuddy-code', model='deepseek-v4.1-flash',
                t0_free_unverified=['hy4-preview', 'hy3'])),
 # ⭐ 复核过费率（catalog 已更新）⇒ 照常当免费档用
 dict(n='费率已复核（3 天前）⇒ T0 照常可用', task_type='core', promo_ok=False,
      credit_records={'hy4-preview': {'credit': 0.0, 'verifiedOn': '2026-09-07'}},
      when=DT(2026,9,10,15),
      want=dict(upstream='codebuddy-code', model='hy4-preview', t0_free_unverified=[])),
 # 🔴 反例：核实记录**太旧**（30 天前）⇒ ⛔ 不算复核 —— 这正是本次事故的形状：
 #    陈旧记录若算通过，已开始计费的型号会被当免费用（异构审 0911 #3 的「误开方向」）
 dict(n='核实记录过期（30 天前）⇒ ⛔ 不算复核，落 T1', task_type='core', promo_ok=False,
      credit_records={'hy4-preview': {'credit': 0.0, 'verifiedOn': '2026-08-11'}},
      when=DT(2026,9,10,15),
      want=dict(model='deepseek-v4.1-flash', t0_free_unverified=['hy4-preview', 'hy3'])),
 # 🔴 反例：有 credit 但**没有 verifiedOn** ⇒ ⛔ 不算复核
 dict(n='credit 无 verifiedOn ⇒ ⛔ 不算复核', task_type='core', promo_ok=False,
      credit_records={'hy4-preview': {'credit': 0.0}},
      want=dict(model='deepseek-v4.1-flash')),
 # ⭐ 反例：探活也不过 ⇒ ⛔ 不提示（没有「本可省钱」这回事）
 dict(n='窗口过期且探活不过 ⇒ ⛔ 不提示', task_type='core', promo_ok=False, probe_ok=False,
      want=dict(model='deepseek-v4.1-flash', t0_free_unverified=[])),
 # 🔴 T0 碰墙（探活不过）⇒ 必须落**同 provider** 的 T1，⛔ 不跨钱包（用户 2026-09-10）
 #    hy4 的形态是「允许你用但派发后静默停」，Paseo 抓不到明确错误 ⇒ 归 availability，
 #    ⛔ 不是「做砸」⇒ ⛔ 不许走质量/成本升档去换模型族。
 # 🔴 hy4 自己反复无响应 ⇒ T0 跳过它、试下一个免费档（hy3），⛔ 不是直接掉付费
 dict(n='hy4 连续无响应 2 次 ⇒ T0 跳到 hy3', task_type='core',
      extra_failures=[{'tier': None, 'upstream': 'codebuddy-code',
                       'model': 'hy4-preview', 'shape': 'no_response', 'count': 2}],
      want=dict(upstream='codebuddy-code', model='hy3')),
 # 🔴🔴 缺省必须偏向【旧行为】：不带 shape 的历史失败**照样算做砸**
 #    ⛔ 否则「质量/成本升档唯一入口」会被整条清零（异构审 2026-09-10 #1）。
 dict(n='不带 shape 的旧失败 ⇒ 仍算做砸（缺省 bad_output）', task_type='core', blockers={'algorithm'},
      extra_failures=[{'tier': 0}, {'tier': 1}],          # ⛔ 故意不给 shape
      want=dict(model='qwen3.8-max')),                     # 两次做砸 ⇒ T3
 # 🔴 同一落点反复无响应 ⇒ 该落点被排除，⛔ 不许原地无限重派
 dict(n='cb/v4.1 连续无响应 2 次 ⇒ 排除该落点，落同档 glm', task_type='core', blockers={'algorithm'},
      extra_failures=[{'tier': None, 'upstream': 'codebuddy-code',
                       'model': 'deepseek-v4.1-flash', 'shape': 'no_response', 'count': 2}],
      want=dict(model='glm-5.3-flash')),
 # ⭐ 反例：只无响应 1 次（未达 NO_RESPONSE_LIMIT）⇒ ⛔ 还不排除，照常落主落点
 dict(n='无响应仅 1 次 ⇒ ⛔ 不排除，仍落 cb/v4.1', task_type='core', blockers={'algorithm'},
      extra_failures=[{'tier': None, 'upstream': 'codebuddy-code',
                       'model': 'deepseek-v4.1-flash', 'shape': 'no_response', 'count': 1}],
      want=dict(upstream='codebuddy-code', model='deepseek-v4.1-flash')),
 # 🔴 免费期没开 ⇒ 压根没碰过 cb ⇒ ⛔ 不该有 affinity（同档替代回到轮换首位）
 dict(n='promo 未开 ⇒ 没碰过 cb ⇒ ⛔ 无 affinity', task_type='core', promo_ok=False,
      unavailable={'codebuddy-code/deepseek-v4.1-flash'},
      want=dict(upstream='volcengine-coding', model='glm-5.3-flash')),
 # 🔴 「没回复」⛔ 不算做砸 —— 两次 no_response 也不许把档位顶上去
 dict(n='no_response ⛔ 不计入做砸（仍停在 T1）', task_type='core', blockers={'algorithm'},
      extra_failures=[{'tier': 0, 'shape': 'no_response'}, {'tier': 0, 'shape': 'no_response'}],
      want=dict(model='deepseek-v4.1-flash')),
 # ⭐ 对照：同样两条但是 bad_output ⇒ 该升到 T3
 dict(n='bad_output 两条 ⇒ 正常升到 T3', task_type='core', blockers={'algorithm'},
      extra_failures=[{'tier': 0, 'shape': 'bad_output'}, {'tier': 1, 'shape': 'bad_output'}],
      want=dict(model='qwen3.8-max')),
 dict(n='T0 探活不过 → 仍落 T1，而 T1 本就在 cb', task_type='core', probe_ok=False,
      want=dict(upstream='codebuddy-code', model='deepseek-v4.1-flash')),
 # ⭐ affinity 必须一直作用到【同档替代】那一步：cb 的 v4.1 拿不到，但 cb 的 glm 可以
 #    ⇒ 落 cb/glm，⛔ 不是火山的 glm（那是池内轮换的首位）
 # ⭐ affinity 的证据是「cb **接了活然后静默**」（hy4 被派出去、然后唤不醒）
 #    ⇒ cb 主落点也拿不到时，同档替代仍优先落 **cb 的 glm**，⛔ 不跳火山
 dict(n='cb 接活后静默 ⇒ 同档替代仍留 cb（落 cb/glm，⛔ 不跳火山）', task_type='core', blockers={'algorithm'},
      extra_failures=[{'tier': None, 'upstream': 'codebuddy-code',
                       'model': 'hy4-preview', 'shape': 'no_response'}],   # count=1 ⇒ 未进死点
      unavailable={'codebuddy-code/deepseek-v4.1-flash'},
      want=dict(upstream='codebuddy-code', model='glm-5.3-flash')),
 # 🔴 反例：只是**探活排队**（probe_queued）⇒ cb 一个请求都没成功吞过 ⇒ ⛔ 无 affinity
 dict(n='仅探活排队 ⇒ ⛔ 无 affinity（回到轮换首位火山）', task_type='core', blockers={'algorithm'},
      extra_failures=[{'tier': None, 'upstream': 'codebuddy-code',
                       'model': 'hy4-preview', 'shape': 'probe_queued'}],
      unavailable={'codebuddy-code/deepseek-v4.1-flash'},
      want=dict(upstream='volcengine-coding', model='glm-5.3-flash')),
 # 🔴 反例：没试过 T0（能力类跳过 T0）⇒ ⛔ 不该有 affinity，池内回到正常轮换
 dict(n='未试 T0 ⇒ ⛔ 无 affinity，同档替代回到轮换首位（火山）', task_type='core',
      blockers={'algorithm'}, unavailable={'codebuddy-code/deepseek-v4.1-flash'},
      want=dict(upstream='volcengine-coding', model='glm-5.3-flash')),
 dict(n='T0 免费档', task_type='core',
      want=dict(upstream='codebuddy-code', model='hy4-preview', thinking='high')),
 dict(n='T1 起步（免费档被排除）', task_type='core', blockers={'algorithm'},
      want=dict(upstream='codebuddy-code', model='deepseek-v4.1-flash',
                provider='codebuddy-code')),   # 🔴 0910 换 T1：v4.1-flash 只在 cb
 dict(n='T3 落百炼 qwen3.8-max', task_type='core', blockers={'algorithm'}, failed=2,
      want=dict(upstream='bailian-token-plan', model='qwen3.8-max',
                provider='pi/bailian-token-plan')),
 # 🔴 产出校验要求必须是**决策结果的字段**，⛔ 不是散文
 dict(n='T1(v4.1-flash) 必须要求校验产出', task_type='core', blockers={'algorithm'}, failed=0,
      want=dict(model='deepseek-v4.1-flash', requires_output_validation=True)),
 dict(n='T2(v4-flash) ⛔ 不要求校验（无该失败形态）', task_type='core', blockers={'algorithm'}, failed=1,
      want=dict(model='deepseek-v4-flash', requires_output_validation=False)),
 dict(n='T1 落到同档替代 glm ⇒ ⛔ 不再要求校验', provider='volcengine-coding',
      task_type='core', blockers={'algorithm'},
      want=dict(model='glm-5.3-flash', requires_output_validation=False)),
 dict(n='T4 落 K3', task_type='core', blockers={'algorithm'}, failed=3,
      want=dict(model='kimi-k3-1')),
 dict(n='超 T4 必停', task_type='core', blockers={'algorithm'}, failed=4, exhausted=True),
 dict(n='algorithm 跳 T0 从 T2 起', task_type='algorithm', blockers={'algorithm'},
      want=dict(model='deepseek-v4-flash', upstream='volcengine-coding')),
 # 审查类
 dict(n='大审查走 Paseo', task_type='review', scope='large',
      want=dict(upstream='github-copilot', model='gpt-5.5',
                provider='pi/github-copilot', channel='paseo')),
 # 🔴 review 硬例外⛔不许静默覆盖显式 --provider（0909 第 5 轮审查）
 # 🔴 review × 显式输入交叉矩阵（0909 第 6 轮审查：这些洞此前全部抓不住）
 dict(n='review + 显式非 copilot provider → 报冲突', task_type='review', scope='small',
      provider='volcengine-coding', review_provider_conflict=True),
 dict(n='review + 显式 provider + 显式 model → 仍报冲突（⛔ 不许绕过）', task_type='review',
      scope='small', provider='volcengine-coding', model='deepseek-v4-flash',
      review_provider_conflict=True),
 dict(n='--free + review + 显式 model → 仍报 free×review 冲突', free=True, task_type='review',
      model='v4-pro', conflict_free_review=True),
 dict(n='review + 显式 model=gpt-5.5 → 落 copilot（⛔ 不掉进 cb 合成池）', task_type='review',
      scope='small', model='gpt-5.5',
      want=dict(upstream='github-copilot', model='gpt-5.5', channel='cli')),
 dict(n='review + 显式 copilot provider → 照常', task_type='review', scope='small',
      provider='github-copilot',
      want=dict(upstream='github-copilot', model='gpt-5.5', channel='cli')),
 # ⚠️1 LAST_RESORT 的 provider 串也要断言（防未来把 claude 加进 PI_HOSTED 拼出 pi/claude）
 # ⚠️2 只给 provider、补出的默认 model 不可用 → 也要停
 # 🔴 换 T1 当场开出来的洞：新 T1 只在 cb，火山没有 ⇒ 显式火山 + 自动 model 会错配。
 #    ⚠️ 火山在 EXEMPT_PROVIDERS 里，validate() ⛔ 不校验 model ⇒ 只能靠这道专门的检查。
 # ⭐ 显式 provider 上没有本档主落点 ⇒ 在【同档】里换成该 provider 真有的那个，并留痕。
 dict(n='显式火山 + 自动 T1（只在 cb）→ 同档换成 glm 并留痕',
      provider='volcengine-coding', task_type='core', blockers={'algorithm'},
      want=dict(upstream='volcengine-coding', model='glm-5.3-flash',
                tier_substitutions=[('deepseek-v4.1-flash', 'glm-5.3-flash',
                                     'volcengine-coding 上没有 deepseek-v4.1-flash')])),
 # 🔴 反例：同档里也没有该 provider 的落点 ⇒ 必须报错配并停，⛔ 不许硬派
 dict(n='显式 copilot + 自动 T1 → 同档也没有 ⇒ 报错配并停',
      provider='github-copilot', task_type='core', blockers={'algorithm'},
      block='mismatch'),
 # ⭐ 原用例的意图（补出的默认 model 拿不到 ⇒ 停）保留，但要用**合法**的 provider×model 对
 dict(n='显式 cb 无 model，补出的默认 model 不可用 → 停止',
      provider='codebuddy-code', task_type='core',
      unavailable={'codebuddy-code/hy4-preview', 'codebuddy-code/hy3',
                   'codebuddy-code/deepseek-v4.1-flash'},
      no_landing=True),
 dict(n='短审查走 CLI', task_type='review', scope='small',
      want=dict(upstream='github-copilot', model='gpt-5.5',
                provider='github-copilot', channel='cli')),
 # 显式值不得被覆盖
 dict(n='只给 model 不被 T0/阶梯覆盖', model='v4-pro', task_type='core',
      # 🔴 2026-09-10 用户停用 deepseek-v4-pro ⇒ T3 落点换成 qwen3.8-max（唯一池：百炼）。
      #    validate() 走 report_blocked_model_and_stop —— 是**停**不是换落点：
      #    「不允许 agent 自己派发」意味着撞上就该停下回到用户，⛔ 不自己挑替代继续。
      blocked_model=True),
 dict(n='只给 provider 不被 T0 换成 cb', provider='volcengine-coding', task_type='core',
      want=dict(upstream='volcengine-coding')),
 # ⭐ 折扣窗口：🔴 只在【档位内选落点】起作用，⛔ 不得跨档下调
 #    DT(周三15:00)=两家都原价 · DT(周三19:00)=仅 cb 打折 · DT(周三23:00)=两家都打折
 dict(n='高峰(周三15点) T2 走轮换首位火山', task_type='core', blockers={'algorithm'}, failed=1,
      when=DT(2026,9,9,15), want=dict(upstream='volcengine-coding', model='deepseek-v4-flash')),
 # 🔴 2026-09-10 换代连带：cb 退出 T2 池 ⇒ **cb 打折也影响不到 T2**（池里没它）。
 #    ⛔ 这两条原本断言「非高峰/周末 T2 落 cb」，换代后已被推翻 ⇒ 改成断言新不变量。
 dict(n='非高峰(周三19点) cb 打折也进不了 T2（池里没 cb）', task_type='core', blockers={'algorithm'}, failed=1,
      when=DT(2026,9,9,19), want=dict(upstream='volcengine-coding', model='deepseek-v4-flash')),
 dict(n='深夜(周三23点) 两家都打折→回到轮换序', task_type='core', blockers={'algorithm'}, failed=1,
      when=DT(2026,9,9,23), want=dict(upstream='bailian-token-plan', model='deepseek-v4-flash-0731')),
 dict(n='周末白天 cb 全天打折，T2 仍不落 cb', task_type='core', blockers={'algorithm'}, failed=1,
      when=DT(2026,9,12,15), want=dict(upstream='volcengine-coding', model='deepseek-v4-flash')),
 # ⚠️ cb 的折扣集现在是**空的**（唯一成员 deepseek-v4-pro 已禁用）⇒ **cb 折扣对阶梯无作用点**。
 #    ⛔ 不要因此删掉 DISCOUNT_WINDOWS 的 cb 条目——`deepseek-v4.1-flash` 若确认继承折扣就会复活。
 # 🔴 0910 换 T1 后：T1 只有 cb 一个池 ⇒ 折扣**排不出顺序**（单池排序是恒等），
 #    而 cb 折扣集又是空的 ⇒ 双重意义上都不改落点。
 dict(n='T1 单池 ⇒ 折扣不改落点', task_type='core',
      blockers={'algorithm'}, failed=0,
      when=DT(2026,9,12,15), want=dict(upstream='codebuddy-code', model='deepseek-v4.1-flash')),
 # 🔴 关键反例：任何时段都⛔不得把档位冲掉
 dict(n='深夜 T1 档位不被冲掉', task_type='core', blockers={'algorithm'}, failed=0,
      when=DT(2026,9,9,23), want=dict(model='deepseek-v4.1-flash')),
 dict(n='深夜免费档仍是 T0', task_type='core', when=DT(2026,9,9,23),
      want=dict(upstream='codebuddy-code', model='hy4-preview')),
 # --free 新语义（0909：不再委派，只影响选档）
 dict(n='--free 无排除 → T0', free=True, task_type='core',
      want=dict(upstream='codebuddy-code', model='hy4-preview')),
 dict(n='--free 放宽能力类排除 → 仍走 T0', free=True, task_type='core',
      blockers={'algorithm', 'perf'},
      want=dict(upstream='codebuddy-code', model='hy4-preview')),
 dict(n='--free 遇物理不可用 → 停止', free=True, task_type='core',
      blockers={'quota_exhausted'}, free_unavailable=True),
 dict(n='--free 混合排除(含物理) → 停止', free=True, task_type='core',
      blockers={'algorithm', 'multimodal'}, free_unavailable=True),
 dict(n='--free + review → 冲突停止', free=True, task_type='review', conflict_free_review=True),
 dict(n='--free --provider codebuddy-code → 不冲突走 T0', free=True,
      provider='codebuddy-code', task_type='core',
      want=dict(upstream='codebuddy-code', model='hy4-preview')),
 # ⛔ 不带 --free 时能力类排除仍跳 T0（证明放宽只对 --free 生效）
 dict(n='无 --free 时能力类排除照旧跳 T0', task_type='core', blockers={'algorithm'},
      want=dict(model='deepseek-v4.1-flash')),
 # 🔴 2026-09-10：T3 从「v4-pro 四池 + qwen 同档替代」变成「qwen3.8-max 单池、无同档替代」
 #    ⇒ 原本那两条以「四池全不可用」为前提的用例前提已不存在，改成断言新形态。
 dict(n='T3 单池即主落点（⛔ 不再有四池轮换）', task_type='core', blockers={'algorithm'}, failed=2,
      want=dict(upstream='bailian-token-plan', model='qwen3.8-max',
                provider='pi/bailian-token-plan')),
 # 🔴 反例：主落点可用时⛔不许被同档替代插队
 dict(n='TIER_PEERS 已空 ⇒ T3 照常落主落点，⛔ 不因空表报错', task_type='core',
      blockers={'algorithm'}, failed=2,
      want=dict(upstream='bailian-token-plan', model='qwen3.8-max')),
 # 🔴 T3 主池+peer 全不可用 ⇒ 【可用性升档】到 T4，⛔ 不停在半路
 dict(n='T3 主池+peer 全不可用 → 升到 T4', task_type='core', blockers={'algorithm'}, failed=2,
      unavailable={'bailian-token-plan/qwen3.8-max'},
      want=dict(model='kimi-k3-1', availability_escalations=[('qwen3.8-max','kimi-k3-1','unavailable')])),
 # ⭐ 可用性升档（用户 2026-09-09 决定：允许【向上】换档 + 必须报告）
 # 🔴 反例保留：T1 全不可用时⛔不许掉进 T3 的 peer，只许升到【相邻】的 T2
 # ⭐ T1 主池（cb）拿不到但同档 peer（glm 三池）可用 ⇒ 落 peer 并**留痕**
 #    🔴 这条专测异构审查抓到的漏：§5 落到 TIER_PEERS 时原先**根本不 append**，
 #       导致【档内换落点】对用户完全不可见。
 dict(n='T1 主池不可用 → 落同档 glm 并留痕', task_type='core', blockers={'algorithm'},
      unavailable={'codebuddy-code/deepseek-v4.1-flash'},
      want=dict(upstream='volcengine-coding', model='glm-5.3-flash',
                availability_escalations=[],
                tier_substitutions=[('deepseek-v4.1-flash', 'glm-5.3-flash', '本档所有池都拿不到')])),
 dict(n='T1 全不可用 → 向上换档到 T2（⛔ 不是 T3 的 peer）', task_type='core', blockers={'algorithm'},
      unavailable={'codebuddy-code/deepseek-v4.1-flash',
                   'volcengine-coding/glm-5.3-flash', 'volcengine-agent-plan/glm-5.3-flash',
                   'codebuddy-code/glm-5.3-flash'},
      want=dict(model='deepseek-v4-flash', upstream='volcengine-coding',
                availability_escalations=[('deepseek-v4.1-flash','deepseek-v4-flash','unavailable')])),
 dict(n='T1+T2 全不可用 → 一路升到 T3', task_type='core', blockers={'algorithm'},
      unavailable={'codebuddy-code/deepseek-v4.1-flash',
                   'volcengine-coding/glm-5.3-flash', 'volcengine-agent-plan/glm-5.3-flash',
                   'codebuddy-code/glm-5.3-flash',
                   'volcengine-coding/deepseek-v4-flash', 'volcengine-agent-plan/deepseek-v4-flash',
                   'bailian-token-plan/deepseek-v4-flash-0731', 'codebuddy-code/deepseek-v4-flash'},
      want=dict(model='qwen3.8-max', upstream='bailian-token-plan',
                availability_escalations=[('deepseek-v4.1-flash','deepseek-v4-flash','unavailable'),
                                          ('deepseek-v4-flash','qwen3.8-max','unavailable')])),
 # 🔴 本档已无同档替代 ⇒ 唯一池拿不到就**只能升 T4**，⛔ 不得落到任何未测模型
 dict(n='T3 唯一池不可用 → 只能升 T4，⛔ 不落未测模型', task_type='core',
      blockers={'algorithm'}, failed=2,
      unavailable={'bailian-token-plan/qwen3.8-max'},
      want=dict(upstream='codebuddy-code', model='kimi-k3-1',
                availability_escalations=[('qwen3.8-max','kimi-k3-1','unavailable')])),
 # 🔴 阶梯到顶仍拿不到 ⇒ LAST_RESORT claude/claude-sonnet-5@max（⛔ 不停在半路）
 dict(n='T4 也拿不到 → 落 LAST_RESORT sonnet-5@max', task_type='core', blockers={'algorithm'}, failed=3,
      unavailable={'codebuddy-code/kimi-k3-1'},
      want=dict(upstream='claude', model='claude-sonnet-5', thinking='max',
                availability_escalations=[('kimi-k3-1','claude-sonnet-5','LAST_RESORT')])),
 dict(n='T3→T4 全不可用 → 一路到 LAST_RESORT（⛔ 不回落低档）', task_type='core',
      blockers={'algorithm'}, failed=2,
      unavailable={'bailian-token-plan/qwen3.8-max', 'codebuddy-code/kimi-k3-1'},
      want=dict(upstream='claude', model='claude-sonnet-5',
                availability_escalations=[('qwen3.8-max','kimi-k3-1','unavailable'),
                                          ('kimi-k3-1','claude-sonnet-5','LAST_RESORT')])),
 # 🔴 连 LAST_RESORT 都没有才停止
 dict(n='付费档全不可用 + claude 也不可用 → 停止', task_type='core', blockers={'algorithm'},
      unavailable={'codebuddy-code/deepseek-v4.1-flash',
                   'volcengine-coding/glm-5.3-flash', 'volcengine-agent-plan/glm-5.3-flash',
                   'codebuddy-code/glm-5.3-flash',
                   'volcengine-coding/deepseek-v4-flash', 'volcengine-agent-plan/deepseek-v4-flash',
                   'bailian-token-plan/deepseek-v4-flash-0731', 'codebuddy-code/deepseek-v4-flash',
                   'bailian-token-plan/qwen3.8-max', 'codebuddy-code/kimi-k3-1',
                   'claude/claude-sonnet-5'},
      no_landing=True),
      # ⚠️ 判据用 unavailable 而⛔不是 provider_available —— 0909 第 4 轮起 LAST_RESORT 做
      #    【model 级】探活（claude 活着但 sonnet-5 拿不到，也必须停）。
 # 🔴 反例：⛔ 任何情况都不许【向下】换档 —— T3 起步、全不可用，⛔ 不许回落 T1/T2
 dict(n='T3 全不可用 ⛔ 不许回落到更低档', task_type='core', blockers={'algorithm'}, failed=2,
      unavailable={'bailian-token-plan/qwen3.8-max'},
      want=dict(model='kimi-k3-1')),   # ⛔ ⛔ 绝不能是 glm-5.3-flash / deepseek-v4-flash
 # ⛔ 没有可用性问题时⛔不许无故升档
 dict(n='一切可用 → availability_escalations 必须为空', task_type='core', blockers={'algorithm'},
      want=dict(model='deepseek-v4.1-flash', availability_escalations=[])),
 # ── 第 4 轮审查补 ──────────────────────────────────────────────
 # ❌1 LAST_RESORT ⛔ 不许覆盖用户显式 --thinking
 dict(n='LAST_RESORT ⛔ 不覆盖显式 --thinking', task_type='core', blockers={'algorithm'},
      failed=3, thinking='low', unavailable={'codebuddy-code/kimi-k3-1'},
      want=dict(upstream='claude', model='claude-sonnet-5', thinking='low')),
 # ❌2 LAST_RESORT 要做 model 级探活，⛔ 不能只查 provider
 dict(n='claude 活着但 sonnet-5 拿不到 → 停止', task_type='core', blockers={'algorithm'},
      failed=3, unavailable={'codebuddy-code/kimi-k3-1', 'claude/claude-sonnet-5'},
      no_landing=True),
 # ❌3 §6 的旧 downgrade() ⛔ 不许把档位降下去
 dict(n='⛔ 收尾 downgrade 不得降到更低档', task_type='core', blockers={'algorithm'}, failed=2,
      dead_providers={'volcengine-coding'},
      downgrade_to=('codebuddy-code', 'glm-5.3-flash'),   # 破坏性桩：企图从 T3 降到 T1
      # 🔴 T3 现在是 qwen3.8-max。⛔ 绝不能变成 glm-5.3-flash —— 那是【跨档下调】。
      want=dict(model='qwen3.8-max')),
 # 🔴 第 4 轮删掉 §6 的 downgrade() 后留下的缺口：显式 provider 不可用时⛔不能静默派过去
 dict(n='显式 provider+model 不可用 → 停止（⛔ 不静默派死通道）',
      provider='volcengine-coding', model='deepseek-v4-flash', task_type='core',
      unavailable={'volcengine-coding/deepseek-v4-flash'}, no_landing=True),
 # ⛔ 反例：显式落点可用时⛔不许被换掉，也⛔不许误报停止
 dict(n='显式 provider+model 可用 → 照常放行', provider='volcengine-coding',
      model='deepseek-v4-flash', task_type='core',
      want=dict(upstream='volcengine-coding', model='deepseek-v4-flash',
                provider='pi/volcengine-coding', availability_escalations=[])),
 # ⚠️2 kimi-k3-1 进 WALLET_PREF 后，默认合成池⛔不该再掩盖它
 # ❌5 LAST_RESORT 固定走 Paseo —— provider 表里 claude 只有 create_agent 路径
 dict(n='LAST_RESORT 必须走 paseo（即使是 cli 规模）', task_type='core', scope='small',
      force_cli=True, blockers={'algorithm'}, failed=2,
      unavailable={'bailian-token-plan/qwen3.8-max', 'codebuddy-code/kimi-k3-1'},
      want=dict(upstream='claude', model='claude-sonnet-5', channel='paseo',
                provider='claude')),   # ⛔ 绝不能是 pi/claude
 dict(n='T4 落 cb kimi-k3-1（显式在 WALLET_PREF 里）', task_type='core',
      blockers={'algorithm'}, failed=3,
      want=dict(upstream='codebuddy-code', model='kimi-k3-1')),
]

fails = []
for c in CASES:
    PROBES.clear()
    try:
        got = run_case(c)
        if c.get('block'):     fails.append(f"{c['n']}: 期望被拦({c['block']})，实际放行 {got}"); continue
        if c.get('delegated'): fails.append(f"{c['n']}: 期望委派，实际 {got}"); continue
        if c.get('exhausted'): fails.append(f"{c['n']}: 期望阶梯到顶停止，实际 {got}"); continue
        if c.get('free_unavailable'): fails.append(f"{c['n']}: 期望 --free 不可用停止，实际 {got}"); continue
        if c.get('conflict_free_review'): fails.append(f"{c['n']}: 期望 free×review 冲突，实际 {got}"); continue
        if c.get('review_provider_conflict'): fails.append(f"{c['n']}: 期望 review provider 冲突，实际 {got}"); continue
        if c.get('blocked_model'): fails.append(f"{c['n']}: 期望被屏蔽，实际 {got}"); continue
        if c.get('no_landing'):
            fails.append(f"{c['n']}: 期望明确报「无可用落点」并停止，实际落到 {got.get('upstream')}/{got.get('model')}"); continue
        for k, v in c['want'].items():
            if got.get(k) != v:
                fails.append(f"{c['n']}: {k} 期望 {v!r} 实际 {got.get(k)!r}")
    except BlockedModel:
        if not c.get('blocked_model'): fails.append(f"{c['n']}: 🔴 意外判为被屏蔽型号")
        elif c.get('no_probe') and PROBES:
            fails.append(f"{c['n']}: 🔴 被禁型号在拦下之前已被探活 {PROBES}")
    except Blocked as e:
        if c.get('block') != str(e): fails.append(f"{c['n']}: 被拦于 {e}，期望 {c.get('block')}")
    except Delegated:
        if not c.get('delegated'): fails.append(f"{c['n']}: 意外委派")
    except Exhausted:
        if not c.get('exhausted'): fails.append(f"{c['n']}: 意外报阶梯到顶")
    except FreeUnavailable:
        if not c.get('free_unavailable'): fails.append(f"{c['n']}: 意外报 --free 不可用")
    except ConflictFreeReview:
        if not c.get('conflict_free_review'): fails.append(f"{c['n']}: 意外报 free×review 冲突")
    except ReviewProviderConflict:
        if not c.get('review_provider_conflict'): fails.append(f"{c['n']}: 意外报 review provider 冲突")
    except NoLanding:
        if not c.get('no_landing'): fails.append(f"{c['n']}: 🔴 意外报『无可用落点』——本档应当有落点")
    except BlockedModel:
        if not c.get('blocked_model'): fails.append(f"{c['n']}: 🔴 意外判为被屏蔽型号")
    except NameError as e:
        fails.append(f"{c['n']}: 🔴 伪代码里有未定义名 —— {e}")
    except Exception as e:
        fails.append(f"{c['n']}: {type(e).__name__}: {e}")

print("=== §2 管线表驱动验证 ===")
print(f"用例 {len(CASES)} 条")
print("✅ 全部通过" if not fails else "\n".join("❌ " + f for f in fails))
sys.exit(1 if fails else 0)
