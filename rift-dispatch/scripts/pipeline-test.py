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
class PaseoUnlisted(Exception): pass        # 1002: Paseo 的 cb provider 清单里没有该型号 ⇒ 会静默降级成 hy3
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
        'user_input':        c.get('user_input', 'x'),   # 🔴 用例要能传标题（[验收] 反例靠它）
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
        # 🔴 2026-09-29 T0 改为 FREE_POOL 登记表驱动：⛔ 不再桩 free_blockers / promo_active ——
        #    阻断按【条目】判、窗口由条目的 freeUntil 推，两者在 §2 里都有真定义，桩掉就等于不测。
        #    ⇒ 只桩外部依赖：多模态判定 · 冷却记录 · 核价记录 · 时间解析。
        'needs_multimodal':  lambda *a: c.get('multimodal', False),
        # ⭐ free_off=True ⇒ 所有免费条目都在冷却中 = 「免费池整体不可用」（替代旧的 free_off=True）
        'cooldown_until':    lambda u, m: (DT(2099, 1, 1) if c.get('free_off')
                                           else c.get('cooldowns', {}).get(f'{u}/{m}')),
        'parse_local_time':  lambda s: DT.fromisoformat(s),
        # 🔴 ⛔ 不桩 t0_still_free 本身 —— 它现在在 §2 里有**真定义**，
        #    桩掉它就等于不测那段逻辑（含「核实记录必须够新」这一条）。
        #    ⇒ 只桩它的外部依赖。⚠️ 键是 'upstream/model'（免费条目按落点区分）
        'catalog_credit_record': lambda u, m: c.get('credit_records', {}).get(f'{u}/{m}'),
        # 🔴 ⛔ 不桩 review_due 本身 —— 「只有 exit 79 才算 due=no」这条 fail-open 规则
        #    就在它里面，桩掉它等于不测这条规则。⇒ 只桩子进程调用。
        #    默认 (1, '') = 模拟【已装 2.9.8 不认 --due】⇒ 必须放行。
        'run_capture':       lambda argv: c.get('due_probe', (1, '')),
        'parse_kv':          lambda out: dict(
            l.split('=', 1) for l in out.strip().splitlines() if '=' in l),
        'days_between':      lambda a, b: (b - __import__('datetime').datetime.fromisoformat(a)).days,
        # ⭐ 两参 + 记录探过谁（free_probes 断言「硬阻断必须在探活之前判」）
        'probe_ok':          lambda u, m: (FREE_PROBES.append(f'{u}/{m}') or (
                                 c.get('probe_ok', True) and f'{u}/{m}' not in set(c.get('probe_fail', ())))),
        # ⚠️ 桩要能表达「某些落点不可用」，否则 TIER_PEERS 兜底分支永远测不到
        'first_available':   lambda lst: (PROBES.extend(f'{u}/{m}' for u, m in lst) or next(
            ((u, m) for u, m in lst if f'{u}/{m}' not in set(c.get('unavailable', ()))), None)),
        'model_id_on':       lambda u, m: PROVIDER_ID.get(u, {}).get(m, m),
        # ⭐ review 默认模型（2026-10-06 起 codex）——codex_config_model() 读 ~/.codex/config.toml 的 model，
        #    测试里用 review_model 旋钮覆盖（默认桩成实测值 gpt-5.6-sol）
        'codex_config_model': lambda: c.get('review_model', 'gpt-5.6-sol'),
        # ⚠️ force_cli 是【测试专用】旋钮：review 改成顶层分支后，review 永远落 codex（CLI），
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
        'execute':           lambda *a: Result(),
        'save_memory':       lambda **k: None,
        'print_summary':     lambda: None,
        'warn':              lambda *a: None,
        'delegate':          lambda n: (_ for _ in ()).throw(Delegated(n)),
        'report_disabled_and_stop':         lambda: (_ for _ in ()).throw(Blocked('disabled')),
        'report_conflict_and_stop':         lambda: (_ for _ in ()).throw(Blocked('conflict')),
        'report_unknown_provider_and_stop': lambda: (_ for _ in ()).throw(Blocked('unknown')),
        'report_ladder_exhausted_and_stop': lambda: (_ for _ in ()).throw(Exhausted()),
        # ⭐ 记下「逐条为什么不行」—— --free 拿不到时必须把这张表报给用户（审查 09-29：原桩把参数丢了，测不出漏报）
        'report_free_unavailable_and_stop': lambda b=None: (
            FREE_REPORT.extend((f'{u}/{m}', sorted(r)) for u, m, r in (b or ()))
            or (_ for _ in ()).throw(FreeUnavailable())),
        'report_conflict_free_vs_review_and_stop': lambda: (_ for _ in ()).throw(ConflictFreeReview()),
        'report_review_provider_conflict_and_stop': lambda *a: (_ for _ in ()).throw(ReviewProviderConflict()),
        'report_no_landing_and_stop': lambda m=None: (_ for _ in ()).throw(NoLanding()),
        'report_blocked_model_and_stop': lambda *a: (_ for _ in ()).throw(BlockedModel()),
        # 🔴 2026-10-02 Paseo 的 cb provider 对「清单里没有的型号」静默跑默认型号 hy3（空 id / 假 id 实测两次，runtimeInfo.model=hy3）
        #    paseo_unlisted=… 表示「Paseo 的 list_models 里没有这些落点」
        #    三态：True=清单里有 / False=确实没登记 / None=拉清单本身失败（超时 / 报错），无法确认
        'paseo_lists_model': lambda u, m: (None if f'{u}/{m}' in set(c.get('paseo_list_error', ()))
                                           else f'{u}/{m}' not in set(c.get('paseo_unlisted', ()))),
        # ⭐ 记下停止时报给用户的是「确实没登记」还是「无法确认清单」（r7 审查：fail-closed 只写在散文里，§2 测不红）
        'report_paseo_unlisted_model_and_stop': lambda u, m, unconfirmed=False: (
            PASEO_REPORT.append((f'{u}/{m}', unconfirmed)) or (_ for _ in ()).throw(PaseoUnlisted())),
        # ⭐ 第 4 个参数是 free_skipped —— 显式 provider 的免费条目都不可用时，停的原因要先说清楚这一层（审查 r2）
        'report_provider_model_mismatch_and_stop': lambda *a: (
            FREE_REPORT.extend((f'{u}/{m}', sorted(r)) for u, m, r in (a[3] if len(a) > 3 else ()))
            or (_ for _ in ()).throw(Blocked('mismatch'))),
        'report_review_not_due_and_stop': lambda d: (_ for _ in ()).throw(Blocked('not_due')),
    }
    src = ("def _decide():\n" + textwrap.indent(BODY, '    ')
           + "\n    return dict(upstream=upstream, model=model, provider=provider,"
             " channel=channel, thinking=thinking,"
             " availability_escalations=availability_escalations,"
             " tier_substitutions=tier_substitutions,"
             " requires_output_validation=requires_output_validation,"
             " t0_free_unverified=t0_free_unverified,"
             " t0_now_billed=t0_now_billed,"
             " free_cautions=free_cautions)\n")
    ns = dict(stub)
    exec(compile(src, '<SKILL.md §2>', 'exec'), ns)     # 🔴 NameError 会在这里炸出来
    return ns['_decide']()

# ── 用例表：必须与 SKILL.md §3「派发路径用例」一致 ──
PROBES = []          # 🔴 记录 first_available 探过哪些落点（供 no_probe 断言）
FREE_PROBES = []     # 🔴 记录 T0 的 probe_ok 探过哪些免费落点（供 free_probes 断言）
FREE_REPORT = []     # 🔴 --free 拿不到时报给用户的逐条原因（供 free_report 断言）
PASEO_REPORT = []    # 🔴 Paseo 前置守卫停下时报给用户的 (落点, 是否「无法确认清单」)（供 paseo_report 断言）
# 🔴 T0 登记表化后已删除的旋钮 —— 用例里再出现就是**静默失效**（桩不读它，断言照样可能碰巧通过）⇒ 直接判错
REMOVED_KNOBS = {'blockers': "改用 free_off=True / cooldowns / multimodal / 条目自己的 avoidTaskTypes",
                 'promo_ok': "改用 when=<freeUntil 之后的时间>（窗口由条目 freeUntil 推）"}
SPACE_BUNNY = 'openrouter-free/stealth/space-bunny-alpha'
HY3, QFM = 'codebuddy-code/hy3', 'qoderclicn/qfmodel'
# 🔴 三个免费条目里**只有 hy3 有确定截止**（10-31 23:59，CodeBuddy 10-01 公告二次延期）；
#    Space Bunny（OpenRouter 预览期）与 qfmodel（Qoder CN 10-01 延期公告：「结束时间将提前在本页公告」）都是 freeUntil=None、永不过期。
#    ⇒ 凡是要测「过期分支」的用例，必须把另外两条冷却掉，否则它们会被选中、测不到 hy3 的过期逻辑。
AFTER_EXPIRY = DT(2026, 11, 2, 15)   # hy3 已过期（10-31 23:59 之后）
COOL_NON_HY3 = {SPACE_BUNNY: DT(2099, 1, 1), QFM: DT(2099, 1, 1)}   # 只留 hy3 参与 ⇒ 隔离出过期分支

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
 # 🔴 2026-10-06 copilot 全族进 BLOCKED_MODELS（凭据已删）⇒ 原「照常放行」两条反例反转成必拦
 dict(n='Copilot gpt-5.5 全族屏蔽必拦（2026-10-06 起）', provider='github-copilot', model='gpt-5.5',
      task_type='core', blocked_model=True),
 dict(n='Copilot grok-4.6 也在全族屏蔽里（2026-10-06 起整族拦）', provider='github-copilot', model='grok-4.6',
      task_type='core', blocked_model=True),
 # 放行类
 dict(n='火山显式放行且带 pi 前缀', provider='volcengine-coding', model='deepseek-v4-flash',
      task_type='core', want=dict(provider='pi/volcengine-coding', model='deepseek-v4-flash', channel='paseo')),
 # 阶梯类
 # 🔴 免费窗口已过但仍探活通过 ⇒ ⛔ 不当免费档用（费率未核），但**必须提示**
 #    实测背景：2026-09-11 记录的免费期已过，hy3 仍秒回 ⇒ 延期或已计费，两头都不能赌。
 # 🔴 2026-09-29 T0 登记表化：窗口由条目自己的 freeUntil 推（⛔ 不再桩 promo_active）⇒ 用 when 取到期之后；
 #    Space Bunny 截止未公布（freeUntil=None）永不过期 ⇒ 这组用例都要先把它冷却掉，才轮得到 hy3 / qfmodel。
 dict(n='免费窗口过期但仍探活通过 ⇒ 落 T1 且提示费率待核', task_type='core', when=AFTER_EXPIRY,
      cooldowns=COOL_NON_HY3,
      want=dict(upstream='volcengine-coding', model='deepseek-v4.1-flash',
                t0_free_unverified=['hy3'])),
 # ⭐ 窗口过后复核过费率（catalog 已更新）⇒ 照常当免费档用
 dict(n='费率已复核（窗口过后、3 天内）⇒ T0 照常可用', task_type='core', when=DT(2026, 11, 4, 15),
      cooldowns={SPACE_BUNNY: DT(2099, 1, 1)},
      credit_records={HY3: {'credit': 0.0, 'verifiedOn': '2026-11-01'}},
      want=dict(upstream='codebuddy-code', model='hy3', thinking='max', t0_free_unverified=[])),
 # 🔴 2026-09-29 新增：**窗口内核的记录⛔不算过期后的复核** —— 它只证明「促销价是 0」。
 #    ⚠️ 旧规则下构造得出事故：hy3 的 catalog 记录是 09-24 面板截图 0.00x，到 10-01 仍在 7 天内
 #    ⇒ 会把可能已开始计费的 hy3 当免费再用一天。
# 🔴 2026-10-02 修：这条用例在 10-01 的 hy3 延期提交里**悄悄失去了区分力** —— 当时只把 `when` 挪到新窗口之后、verifiedOn 仍是 09-24，
 #    可 09-24 距新窗口（10-31）已 37 天 > 7 天，「年龄闸门」单独就能拒掉它，⇒ 「窗口内核的不算」这条规则被拿掉也照样绿（注入验证抓出）。
 #    ⇒ 必须构造「**只有窗口规则能拒掉它**」的输入：verifiedOn 在窗口内（≤ 10-31）、且距 when ≤ 7 天（年龄闸门放行）。
 dict(n='窗口最后两天内核的 0.00x（10-30）⛔ 不算过期后复核 ⇒ 提示待核，落 T1', task_type='core',
      when=DT(2026, 11, 1, 15), cooldowns=COOL_NON_HY3,
      credit_records={HY3: {'credit': 0.0, 'verifiedOn': '2026-10-30'}},     # 距 when 仅 2 天 ⇒ 年龄闸门放行，只剩窗口规则
      want=dict(model='deepseek-v4.1-flash', t0_free_unverified=['hy3'])),
 # 🔴🔴 核实结果是「已计费」⇒ T0 **必须关闭** —— ⛔ 这是改名前那版的洞：
 #    原 rate_reverified 只判「核过且够新」，不判「结果仍为 0」⇒ 用户如实写下 0.5x 之后，
 #    闸门返回 True，把一个比 T1 贵 16 倍的模型当免费档用。
 #    ⭐ 最坏的是：这个后果由「用户做了正确的事（去核实）」触发。
 dict(n='核实结果=已计费 0.5x ⇒ T0 关闭并报告，⛔ 不当免费用', task_type='core', when=AFTER_EXPIRY,
      cooldowns=COOL_NON_HY3,
      credit_records={HY3: {'credit': 0.5, 'verifiedOn': '2026-11-01'}},
      want=dict(model='deepseek-v4.1-flash', t0_now_billed=[('hy3', 0.5)],
                t0_free_unverified=[])),
 # 🔴 反例：核实记录**太旧**（30 天前）⇒ ⛔ 不算复核 —— 这正是本次事故的形状：
 #    陈旧记录若算通过，已开始计费的型号会被当免费用（异构审 0911 #3 的「误开方向」）
 dict(n='核实记录过期（29 天前）⇒ ⛔ 不算复核，落 T1', task_type='core', when=DT(2026, 11, 30, 15),
      cooldowns=COOL_NON_HY3,
      credit_records={HY3: {'credit': 0.0, 'verifiedOn': '2026-11-01'}},
      want=dict(model='deepseek-v4.1-flash', t0_free_unverified=['hy3'])),
 # 🔴 反例：有 credit 但**没有 verifiedOn** ⇒ ⛔ 不算复核
 dict(n='credit 无 verifiedOn ⇒ ⛔ 不算复核', task_type='core', when=AFTER_EXPIRY,
      cooldowns=COOL_NON_HY3,
      credit_records={HY3: {'credit': 0.0}},
      want=dict(model='deepseek-v4.1-flash')),
 # ⭐ 反例：探活也不过 ⇒ ⛔ 不提示（没有「本可省钱」这回事）
 dict(n='窗口过期且探活不过 ⇒ ⛔ 不提示', task_type='core', when=AFTER_EXPIRY, probe_ok=False,
      cooldowns=COOL_NON_HY3,     # ⭐ 显式挡掉另两条（审查 r2：别只靠全局 probe_ok=False 顺带挡住它们）
      want=dict(model='deepseek-v4.1-flash', t0_free_unverified=[])),
 # 🔴 T0 碰墙（探活不过）⇒ 必须落**同 provider** 的 T1，⛔ 不跨钱包（用户 2026-09-10）
 #    hy4 的形态是「允许你用但派发后静默停」，Paseo 抓不到明确错误 ⇒ 归 availability，
 #    ⛔ 不是「做砸」⇒ ⛔ 不许走质量/成本升档去换模型族。
 # ⭐ 2026-09-29 免费池有三条 ⇒ hy3 反复无响应**只跳过它自己**，⛔ 不连带其它免费条目
 dict(n='hy3 连续无响应 2 次 ⇒ 只跳过 hy3，落下一个免费条目 qfmodel', task_type='core',
      cooldowns={SPACE_BUNNY: DT(2099, 1, 1)},
      extra_failures=[{'tier': None, 'upstream': 'codebuddy-code',
                       'model': 'hy3', 'shape': 'no_response', 'count': 2}],
      free_probes=[QFM],                         # 🔴 死落点⛔不许再探一次活
      want=dict(upstream='qoderclicn', model='qfmodel', provider='qoderclicn', thinking=None)),
 # ⏳ 2026-09-24 **待用户裁定**：affinity=cb 但 cb 已不在 v4.1-flash 池里 ⇒ 按「affinity 不改模型」
 #    的既有不变量回到轮换落火山 coding。⚠️ 与 09-10「⛔ 不要换 pi」字面冲突（见 SKILL §4 affinity 注释）。
 #    若用户选「留 cb 用 glm」，本条改断言 upstream='codebuddy-code', model='glm-5.3-flash'。
 dict(n='hy3 连续无响应 2 次 + 其它免费条目也不可用 ⇒ 转 T1（affinity=cb 在 T1 主池无作用点）',
      task_type='core', cooldowns={SPACE_BUNNY: DT(2099, 1, 1), QFM: DT(2099, 1, 1)},
      extra_failures=[{'tier': None, 'upstream': 'codebuddy-code',
                       'model': 'hy3', 'shape': 'no_response', 'count': 2}],
      want=dict(upstream='volcengine-coding', model='deepseek-v4.1-flash')),
 # 🔴🔴 缺省必须偏向【旧行为】：不带 shape 的历史失败**照样算做砸**
 #    ⛔ 否则「质量/成本升档唯一入口」会被整条清零（异构审 2026-09-10 #1）。
 dict(n='不带 shape 的旧失败 ⇒ 仍算做砸（缺省 bad_output）', task_type='core', free_off=True,
      extra_failures=[{'tier': 0}, {'tier': 1}],          # ⛔ 故意不给 shape
      want=dict(model='qwen3.8-max')),                     # 两次做砸 ⇒ T3
 # 🔴 同一落点反复无响应 ⇒ 该落点被排除，⛔ 不许原地无限重派
 dict(n='cb/v4.1 连续无响应 2 次 ⇒ 排除该落点，落同档 glm', task_type='core', free_off=True,
      extra_failures=[{'tier': None, 'upstream': 'codebuddy-code',
                       'model': 'deepseek-v4.1-flash', 'shape': 'no_response', 'count': 2}],
      unavailable={'volcengine-coding/deepseek-v4.1-flash',
                   'volcengine-agent-plan/deepseek-v4.1-flash',
                   'bailian-token-plan/deepseek-v4.1-flash'},   # 🔴 0915 T1 变三池，另两池也得堵上
      want=dict(model='glm-5.3-flash')),
 # ⭐ 反例：只无响应 1 次（未达 NO_RESPONSE_LIMIT）⇒ ⛔ 还不排除，照常落主落点
 # 🔴 2026-09-24 原用例拿 cb/v4.1 当例子，cb 已移出该池 ⇒ 换成**仍在池里**的火山 coding，保留原意图
 dict(n='无响应仅 1 次 ⇒ ⛔ 不排除，仍落该池', task_type='core', free_off=True,
      extra_failures=[{'tier': None, 'upstream': 'volcengine-coding',
                       'model': 'deepseek-v4.1-flash', 'shape': 'no_response', 'count': 1}],
      want=dict(upstream='volcengine-coding', model='deepseek-v4.1-flash')),
 # 🔴 免费期没开 ⇒ 压根没碰过 cb ⇒ ⛔ 不该有 affinity（同档替代回到轮换首位）
 dict(n='免费窗口已过 ⇒ 没让 cb 接过活 ⇒ ⛔ 无 affinity', task_type='core', when=AFTER_EXPIRY,
      cooldowns=COOL_NON_HY3,
      unavailable={'volcengine-coding/deepseek-v4.1-flash',
                   'volcengine-agent-plan/deepseek-v4.1-flash',
                   'bailian-token-plan/deepseek-v4.1-flash'},
      want=dict(upstream='volcengine-coding', model='glm-5.3-flash')),
 # 🔴 「没回复」⛔ 不算做砸 —— 两次 no_response 也不许把档位顶上去
 dict(n='no_response ⛔ 不计入做砸（仍停在 T1）', task_type='core', free_off=True,
      extra_failures=[{'tier': 0, 'shape': 'no_response'}, {'tier': 0, 'shape': 'no_response'}],
      want=dict(model='deepseek-v4.1-flash')),
 # ⭐ 对照：同样两条但是 bad_output ⇒ 该升到 T3
 dict(n='bad_output 两条 ⇒ 正常升到 T3', task_type='core', free_off=True,
      extra_failures=[{'tier': 0, 'shape': 'bad_output'}, {'tier': 1, 'shape': 'bad_output'}],
      want=dict(model='qwen3.8-max')),
 # 🔴 2026-09-24 原名「而 T1 本就在 cb」—— cb 已移出 v4.1-flash 的池，那个前提消失
 dict(n='T0 探活不过 → 仍落 T1（轮换首位火山 coding）', task_type='core', probe_ok=False,
      want=dict(upstream='volcengine-coding', model='deepseek-v4.1-flash')),
 # ⭐ affinity 必须一直作用到【同档替代】那一步：cb 的 v4.1 拿不到，但 cb 的 glm 可以
 #    ⇒ 落 cb/glm，⛔ 不是火山的 glm（那是池内轮换的首位）
 # ⭐ affinity 的证据是「cb **接了活然后静默**」（hy4 被派出去、然后唤不醒）
 #    ⇒ cb 主落点也拿不到时，同档替代仍优先落 **cb 的 glm**，⛔ 不跳火山
 dict(n='cb 接活后静默 ⇒ 同档替代仍留 cb（落 cb/glm，⛔ 不跳火山）', task_type='core', free_off=True,
      extra_failures=[{'tier': None, 'upstream': 'codebuddy-code',
                       'model': 'hy3', 'shape': 'no_response'}],   # count=1 ⇒ 未进死点
      unavailable={'volcengine-coding/deepseek-v4.1-flash',
                   'volcengine-agent-plan/deepseek-v4.1-flash',
                   'bailian-token-plan/deepseek-v4.1-flash'},
      want=dict(upstream='codebuddy-code', model='glm-5.3-flash')),
 # 🔴 反例：只是**探活排队**（probe_queued）⇒ cb 一个请求都没成功吞过 ⇒ ⛔ 无 affinity
 dict(n='仅探活排队 ⇒ ⛔ 无 affinity（回到轮换首位火山）', task_type='core', free_off=True,
      extra_failures=[{'tier': None, 'upstream': 'codebuddy-code',
                       'model': 'hy3', 'shape': 'probe_queued'}],
      unavailable={'volcengine-coding/deepseek-v4.1-flash',
                   'volcengine-agent-plan/deepseek-v4.1-flash',
                   'bailian-token-plan/deepseek-v4.1-flash'},
      want=dict(upstream='volcengine-coding', model='glm-5.3-flash')),
 # 🔴 反例：没试过 T0（能力类跳过 T0）⇒ ⛔ 不该有 affinity，池内回到正常轮换
 dict(n='未试 T0 ⇒ ⛔ 无 affinity，同档替代回到轮换首位（火山）', task_type='core',
      free_off=True, unavailable={'volcengine-coding/deepseek-v4.1-flash',
                   'volcengine-agent-plan/deepseek-v4.1-flash',
                   'bailian-token-plan/deepseek-v4.1-flash'},
      want=dict(upstream='volcengine-coding', model='glm-5.3-flash')),
 # ── T0 免费池（2026-09-29 登记表驱动）── 优先级：Space Bunny > hy3 > qfmodel（用户 09-29 定）
 dict(n='T0 默认落 priority 1：OpenRouter Space Bunny @high', task_type='core',
      free_probes=[SPACE_BUNNY],
      want=dict(upstream='openrouter-free', model='stealth/space-bunny-alpha', thinking='high',
                provider='pi/openrouter-free', channel='paseo', free_cautions=[])),
 dict(n='Space Bunny 冷却中 ⇒ 落 priority 2：cb/hy3 @max（⛔ 冷却中的⛔不探活）', task_type='core',
      cooldowns={SPACE_BUNNY: DT(2026, 9, 10, 18)},
      free_probes=[HY3],
      want=dict(upstream='codebuddy-code', model='hy3', thinking='max')),
 # ⭐ qfmodel 没有思考档 ⇒ thinking 必须是 None（⛔ 不许被收尾的 default_thinking 补成 xhigh）
 dict(n='Bunny + hy3 都冷却 ⇒ 落 priority 3：qcn/qfmodel，⛔ 不传 thinking', task_type='core',
      cooldowns={SPACE_BUNNY: DT(2099, 1, 1), HY3: DT(2099, 1, 1)},
      want=dict(upstream='qoderclicn', model='qfmodel', provider='qoderclicn', thinking=None)),
 dict(n='qfmodel + 显式 --thinking high ⇒ 仍⛔不传（该模型没有思考档）', task_type='core',
      thinking='high', cooldowns={SPACE_BUNNY: DT(2099, 1, 1), HY3: DT(2099, 1, 1)},
      want=dict(model='qfmodel', thinking=None)),
 # ⭐ 冷却记录**已过期** ⇒ ⛔ 不算阻断
 # 🔴 审查 A ❌2：T0 选中的落点 ⛔ 不在 §5 再探第二次（否则第二次失败会直接停，不试下一个免费条目）
 dict(n='T0 选中后 ⛔ 不再探第二次', task_type='core',
      unavailable={SPACE_BUNNY},              # 若 §5 再探就会 NoLanding —— 这条就是要证明它不会
      free_probes=[SPACE_BUNNY], probes=[],
      want=dict(model='stealth/space-bunny-alpha')),
 # 🔴 审查 A ❌1：显式 --model 给了免费 / 白名单型号但⛔没给 provider ⇒ 按白名单找它的 provider，⛔ 不落成 cb/<它>
 dict(n='显式 --model qfmodel（无 provider）⇒ 落 qcn，⛔ 不当 cb 型号', task_type='core', model='qfmodel',
      want=dict(upstream='qoderclicn', model='qfmodel', thinking=None)),
 dict(n='显式 --model stealth/space-bunny-alpha（无 provider）⇒ 落 OpenRouter @high', task_type='core',
      model='stealth/space-bunny-alpha',
      want=dict(upstream='openrouter-free', provider='pi/openrouter-free', thinking='high')),
 dict(n='显式 --model qmodel_38max（无 provider）⇒ 落 qcn（顺带修掉的旧同形）', task_type='core',
      model='qmodel_38max', want=dict(upstream='qoderclicn', model='qmodel_38max')),
 # ⭐ 反例：不在任何池、也不在任何白名单里的型号 ⇒ 仍合成 cb 落点 ⇒ 白名单拦（⛔ 不替用户猜 provider）
 dict(n='显式 --model 不在任何池/白名单（无 provider）⇒ 合成 cb ⇒ 白名单拦', task_type='core',
      model='grok-4.6', block='conflict'),
 dict(n='冷却已过期 ⇒ 照常落 Space Bunny', task_type='core',
      cooldowns={SPACE_BUNNY: DT(2026, 9, 10, 14)},
      want=dict(model='stealth/space-bunny-alpha')),
 dict(n='显式 --thinking low ⇒ Space Bunny 用 low（⛔ 不被条目默认 high 覆盖）', task_type='core',
      thinking='low', want=dict(model='stealth/space-bunny-alpha', thinking='low')),
 # 🔴 2026-10-01 CodeBuddy 二次延期：hy3 → 10-31 23:59；Space Bunny / qfmodel 截止都未公布（freeUntil=None，永不过期）
 #    ⇒ hy3 到期后免费池里仍有这两条；Bunny 排在最前，所以这里落 Bunny
 dict(n='11-01 起 hy3 已到期 ⇒ Space Bunny（截止未公布）仍可用', task_type='core', when=DT(2026, 11, 1, 15),
      want=dict(model='stealth/space-bunny-alpha', t0_free_unverified=[])),
 # ⭐ 正面回归：10-01 ~ 10-31 23:59（hy3 延期窗口内）⇒ hy3 仍正常当选，⛔ 不提前判过期
 #    这条直接验证「二次延期生效」——若 SKILL 的 freeUntil 没跟着改，这里会落 Space Bunny 而不是 hy3
 dict(n='10-15（hy3 在延期窗口内）⇒ 正常落 hy3（qfmodel 排在它后面，⛔ 不抢位）', task_type='core',
      when=DT(2026, 10, 15, 15), cooldowns={SPACE_BUNNY: DT(2099, 1, 1)},   # ⚠️ 必须挡掉优先级更高的 Bunny，否则测不到 hy3
      want=dict(upstream='codebuddy-code', model='hy3', thinking='max', t0_free_unverified=[])),
 # 🔴 2026-10-02 Qoder CN 官方公告：原定 09-30 的免费期延长，10-01 起继续免费，「结束时间将提前在本页公告」
 #    ⇒ qfmodel freeUntil=None（截止未公布，与 Space Bunny 同口径）。⭐ 实测原定 09-30 之后 total_credits 仍为 0。
 #    RED 依据：改前 qfmodel 按 09-30 过期 ⇒ 这里会落 T1，而不是 qfmodel。
 dict(n='qfmodel 截止未公布 ⇒ hy3 到期、Bunny 冷却后仍落 qfmodel（10-02 官方延期）', task_type='core',
      when=AFTER_EXPIRY, cooldowns={SPACE_BUNNY: DT(2099, 1, 1)},
      want=dict(upstream='qoderclicn', model='qfmodel', provider='qoderclicn', thinking=None,
                t0_free_unverified=['hy3'])),
 dict(n='qfmodel 不会因为日期老而过期（2027-06 仍可当选）', task_type='core', when=DT(2027, 6, 1, 15),
      cooldowns={SPACE_BUNNY: DT(2099, 1, 1)},
      want=dict(model='qfmodel', t0_free_unverified=['hy3'])),
 # 🔴 D3（用户 09-29）：Space Bunny 做并发实现类**只提醒不排除**（并发题 30.0，漏乘数量 / 字段风格不一致）
 dict(n='concurrency_impl ⇒ 仍落 Space Bunny，但必须带提醒', task_type='concurrency_impl',
      want=dict(model='stealth/space-bunny-alpha',
                free_cautions=[('stealth/space-bunny-alpha', 'concurrency_impl')])),
 # ⭐ 能力短板是【条目】的属性（avoidTaskTypes），⛔ 不再全局套在所有免费模型上 ——
 #    那张清单本来只对 hy3 有依据；Space Bunny 的 LRU 32.2 与 T1 同档
 dict(n='algorithm ⇒ Space Bunny 照常接（它没有 avoid）', task_type='algorithm',
      want=dict(model='stealth/space-bunny-alpha')),
 # qfmodel avoid perf：与 hy3 同一理由（perf 无任何模型的实测，按 algorithm 同类保守处理）；10-02 agent 推导所定，⛔ 非待决
 dict(n='perf + Bunny 冷却 ⇒ hy3/qfmodel 都 avoid ⇒ 付费 T2 起步', task_type='perf',
      cooldowns={SPACE_BUNNY: DT(2099, 1, 1)}, free_probes=[],
      want=dict(model='deepseek-v4-flash')),
 dict(n='algorithm + Bunny 冷却 ⇒ hy3/qfmodel 都 avoid ⇒ 付费 T2 起步', task_type='algorithm',
      cooldowns={SPACE_BUNNY: DT(2099, 1, 1)}, free_probes=[],
      want=dict(model='deepseek-v4-flash', upstream='volcengine-coding')),
 # ⭐ 多模态：Space Bunny 能免费接图（hy3 会被 cb 切到付费多模态模型）
 dict(n='多模态任务 ⇒ Space Bunny 可接', task_type='core', multimodal=True,
      want=dict(model='stealth/space-bunny-alpha')),
 dict(n='多模态 + Bunny 冷却 ⇒ hy3/qfmodel 物理不可用 ⇒ T1', task_type='core', multimodal=True,
      cooldowns={SPACE_BUNNY: DT(2099, 1, 1)}, free_probes=[],
      want=dict(model='deepseek-v4.1-flash')),
 # ⭐ 本任务里已在某免费落点做砸（有产出不合格）⇒ 只排除那一条
 dict(n='hy3 本任务已做砸 ⇒ 只跳过 hy3，落 qfmodel', task_type='core',
      cooldowns={SPACE_BUNNY: DT(2099, 1, 1)},
      extra_failures=[{'tier': None, 'upstream': 'codebuddy-code', 'model': 'hy3',
                       'shape': 'bad_output'}],
      free_probes=[QFM], want=dict(model='qfmodel')),
 # ⭐ 显式 provider ⇒ 只看同 provider 的免费条目（⛔ 不算冲突）
 dict(n='显式 --provider openrouter-free ⇒ Space Bunny', provider='openrouter-free', task_type='core',
      want=dict(upstream='openrouter-free', model='stealth/space-bunny-alpha')),
 dict(n='显式 --provider qoderclicn ⇒ 只看 qfmodel', provider='qoderclicn', task_type='core',
      free_probes=[QFM], want=dict(upstream='qoderclicn', model='qfmodel')),
 # 🔴 openrouter-free 是【白名单型】provider（只放这一个模型）⇒ 其它 id ⛔ 一律拦
 dict(n='--provider openrouter-free --model 其它 ⇒ 白名单拦', provider='openrouter-free',
      model='stealth/other-alpha', task_type='core', block='conflict'),
 dict(n='显式 openrouter-free + Bunny 冷却 ⇒ 付费档没有该 provider ⇒ 报错配并停',
      provider='openrouter-free', task_type='core', cooldowns={SPACE_BUNNY: DT(2099, 1, 1)},
      block='mismatch', free_report=[(SPACE_BUNNY, ['quota_cooldown'])]),
 # 🔴 2026-09-24 cb 移出 v4.1-flash 的池 ⇒ 自动派发落轮换首位火山 coding，且 Paseo 串带 pi/ 前缀
 dict(n='T1 起步（免费档被排除）', task_type='core', free_off=True,
      want=dict(upstream='volcengine-coding', model='deepseek-v4.1-flash',
                provider='pi/volcengine-coding')),
 dict(n='T3 落百炼 qwen3.8-max', task_type='core', free_off=True, failed=2,
      want=dict(upstream='bailian-token-plan', model='qwen3.8-max',
                provider='pi/bailian-token-plan')),
 # 🔴 产出校验要求必须是**决策结果的字段**，⛔ 不是散文
 dict(n='T1(v4.1-flash) 必须要求校验产出', task_type='core', free_off=True, failed=0,
      want=dict(model='deepseek-v4.1-flash', requires_output_validation=True)),
 dict(n='T2(v4-flash) ⛔ 不要求校验（无该失败形态）', task_type='core', free_off=True, failed=1,
      want=dict(model='deepseek-v4-flash', requires_output_validation=False)),
 # 🔴 2026-09-23 改走【可用性 peer】路径 —— 原先靠「火山上没有 T1 主落点」触发，
 #    但 coding 当天上了 v4.1-flash，那个前提消失了。落 glm 仍要测（它决定校验开关关不关）。
 dict(n='T1 三池全不可用 → 落同档 glm ⇒ ⛔ 不再要求校验', task_type='core', free_off=True,
      unavailable={'volcengine-coding/deepseek-v4.1-flash',
                   'volcengine-agent-plan/deepseek-v4.1-flash',
                   'bailian-token-plan/deepseek-v4.1-flash'},
      want=dict(model='glm-5.3-flash', requires_output_validation=False)),
 dict(n='T4 落 K3', task_type='core', free_off=True, failed=3,
      want=dict(model='kimi-k3-1')),
 dict(n='超 T4 必停', task_type='core', free_off=True, failed=4, exhausted=True),
 # ⚠️ 原名「algorithm 跳 T0 从 T2 起」—— 09-29 起 algorithm ⛔不再整档跳 T0（Space Bunny 可接），
 #    本条只测「免费池不可用时，algorithm 付费从 T2 起步」
 dict(n='algorithm + 免费池不可用 ⇒ 付费从 T2 起', task_type='algorithm', free_off=True,
      want=dict(model='deepseek-v4-flash', upstream='volcengine-coding')),
 # 审查类
 # 🔴 2026-10-06 起审查全走 CLI（默认 codex）—— Paseo codex provider out of credits、copilot 全族已死
 dict(n='大审查也走 CLI（codex，2026-10-06 起）', task_type='review', scope='large',
      want=dict(upstream='codex', model='gpt-5.6-sol', provider='codex', channel='cli')),
 # 🔴 review 硬例外⛔不许静默覆盖显式 --provider（0909 第 5 轮审查）
 # 🔴 review × 显式输入交叉矩阵（0909 第 6 轮审查：这些洞此前全部抓不住）
 dict(n='review + 显式非 codex provider → 报冲突', task_type='review', scope='small',
      provider='volcengine-coding', review_provider_conflict=True),
 dict(n='review + 显式 provider + 显式 model → 仍报冲突（⛔ 不许绕过）', task_type='review',
      scope='small', provider='volcengine-coding', model='deepseek-v4-flash',
      review_provider_conflict=True),
 dict(n='--free + review + 显式 model → 仍报 free×review 冲突', free=True, task_type='review',
      model='v4-pro', conflict_free_review=True),
 dict(n='review + 显式 model → 保留，provider 默认 codex（⛔ 不掉进普通阶梯）', task_type='review',
      scope='small', model='gpt-5.5',
      want=dict(upstream='codex', model='gpt-5.5', channel='cli')),
 # 🔴 2026-10-06：合法 review provider 只剩 codex，显式 copilot 也报 review 冲突（原「照常」反转）
 dict(n='review + 显式 copilot provider → 报冲突（copilot 全族已死）', task_type='review', scope='small',
      provider='github-copilot', review_provider_conflict=True),
 # ⭐ 显式 codex provider → 照常（review 分支的 assert 行要被走到 —— coverage 99.6%→100% 靠这条）
 dict(n='review + 显式 codex provider → 照常放行', task_type='review', scope='small',
      provider='codex',
      want=dict(upstream='codex', model='gpt-5.6-sol', provider='codex', channel='cli')),
 # ⚠️1 LAST_RESORT 的 provider 串也要断言（防未来把 claude 加进 PI_HOSTED 拼出 pi/claude）
 # ⚠️2 只给 provider、补出的默认 model 不可用 → 也要停
 # 🔴 换 T1 当场开出来的洞：新 T1 只在 cb，火山没有 ⇒ 显式火山 + 自动 model 会错配。
 #    ⚠️ 火山在 EXEMPT_PROVIDERS 里，validate() ⛔ 不校验 model ⇒ 只能靠这道专门的检查。
 # ⭐ 显式 provider 上没有本档主落点 ⇒ 在【同档】里换成该 provider 真有的那个，并留痕。
 # 🔴 2026-09-23 前提反转：火山 coding **已经有** v4.1-flash ⇒ 不再需要换落点，直接落它。
 #    ⚠️ 原用例断言的是「同档换成 glm 并留痕」—— 09-23 那条路径一度不可达（打过 pragma 豁免）；
 #    09-24 cb 移出池后**重新可达**，覆盖改由下方「显式 cb 无 model ⇒ 同档换落点」承担。
 dict(n='显式火山 coding + 自动 T1 ⇒ 直接落 v4.1-flash，⛔ 无需换落点',
      provider='volcengine-coding', task_type='core', free_off=True,
      want=dict(upstream='volcengine-coding', model='deepseek-v4.1-flash',
                tier_substitutions=[])),
 # 🔴 2026-10-06：copilot 移出豁免集 ⇒ 显式 copilot（非 review）落「未知 provider」被拦，⛔ 不再是错配
 dict(n='显式 copilot（非 review）→ 未知 provider 拦（已移出豁免集）',
      provider='github-copilot', task_type='core', free_off=True,
      block='unknown'),
 # ⭐ 原用例的意图（补出的默认 model 拿不到 ⇒ 停）保留，但要用**合法**的 provider×model 对
 # ⚠️ 走的是 T0 路径：hy3 过了 probe_ok 但最终落点探活失败 ⇒ 当场 NoLanding，⛔ 走不到 T1。
 #    （09-24 前这里还列了 cb/v4.1 —— 那条从来没被读到过，是死数据，已删。）
 # 🔴 2026-09-29 语义改了（审查 A ❌2）：T0 的探活就是那一次探活，§5 ⛔ 不再探第二次。
 #    原用例靠「probe_ok 过 + first_available 不过」这种自相矛盾的桩触发 NoLanding —— 多条目 T0 下那会让
 #    「选中后第二次探失败」直接停，而不是换下一个免费条目（违反 D4）。
 #    ⇒ 现在 hy3 拿不到就在 T0 里被跳过；显式 cb 进 T1 ⇒ 同档换落点 cb/glm。「换完仍不可用 ⇒ 停」见下面那条。
 dict(n='显式 cb 无 model + hy3 探活不过 ⇒ T1 同档换落点 cb/glm（⛔ 不跨 provider）',
      provider='codebuddy-code', task_type='core', probe_fail={HY3},
      want=dict(upstream='codebuddy-code', model='glm-5.3-flash')),
 # 🔴🔴 2026-09-24 「同档换落点」分支**重新可达** —— 这三条就是它的覆盖（原先靠 pragma 豁免）
 #    cb 移出 v4.1-flash 的池（涨到 0.11x > glm 0.06x），而 cb 仍是 TIER_PEERS 成员。
 dict(n='显式 cb 无 model，自动选出 T1 ⇒ 同档换落点 cb/glm 并留痕',
      provider='codebuddy-code', task_type='core', free_off=True,
      want=dict(upstream='codebuddy-code', model='glm-5.3-flash',
                requires_output_validation=False,
                tier_substitutions=[('deepseek-v4.1-flash', 'glm-5.3-flash',
                                     'codebuddy-code 上没有 deepseek-v4.1-flash')])),
 # ⛔ 换完落点仍要过「显式 provider ⛔ 不许被换掉」：cb/glm 也拿不到 ⇒ 停，⛔ 不跳火山
 dict(n='显式 cb 无 model，换到 cb/glm 也不可用 → 停止（⛔ 不跨 provider）',
      provider='codebuddy-code', task_type='core', free_off=True,
      unavailable={'codebuddy-code/glm-5.3-flash'},
      no_landing=True),
 # ⭐ 用户**点名** v4.1-flash 就照派 —— 白名单还在，⛔ 不因为「不再自动选它」就拦
 dict(n='显式 cb + 显式 v4.1-flash ⇒ 照派（价差用户自负）',
      provider='codebuddy-code', model='deepseek-v4.1-flash', task_type='core',
      want=dict(upstream='codebuddy-code', model='deepseek-v4.1-flash',
                requires_output_validation=True, tier_substitutions=[])),
 # ── 2026-10-02 cb 内置 `space-bunny`（付费 x0.03，折扣至 10-07）──
 #    ⛔ 只进白名单（显式可派），⛔ 不进任何自动池：cb 路由上没评测过（Qoder 版 Qwen3.8-Flash 与百炼版同名却显著更弱的前车之鉴）
 dict(n='显式 cb + space-bunny ⇒ 放行（白名单），Paseo 已登记时走 paseo', provider='codebuddy-code', model='space-bunny',
      task_type='core',
      want=dict(upstream='codebuddy-code', model='space-bunny', provider='codebuddy-code', channel='paseo',
                availability_escalations=[], tier_substitutions=[])),
 dict(n='只给 --model space-bunny（无 provider）⇒ 按白名单落 cb', model='space-bunny', task_type='core',
      want=dict(upstream='codebuddy-code', model='space-bunny', channel='paseo')),
 # 🔴 Paseo 的 cb provider 对清单里没有的型号**静默降级成 hy3**（10-02 实测 ×2：真 id space-bunny、假 id 都是 runtimeInfo.model=hy3）
 #    ⇒ 标题 / 账单 / 评测结论标的是 A，实际跑的是 B。必须在派发前拦下，⛔ 不能只靠「创建后核 runtimeInfo」（那条靠人记得）
 dict(n='Paseo 清单缺 space-bunny ⇒ 走 Paseo 的派发必须停（⛔ 否则静默跑成 hy3）', provider='codebuddy-code',
      model='space-bunny', task_type='core', paseo_unlisted={'codebuddy-code/space-bunny'}, paseo_stop=True,
      paseo_report=[('codebuddy-code/space-bunny', False)]),
 # 🔴 r7 审查：fail-closed（拉清单失败也要停）原先只写在 SKILL §3.1 的散文里，§2 伪代码与测试都没有对应 ⇒ 老毛病「规则只写在散文里」
 dict(n='Paseo 拉清单失败（超时 / 报错）⇒ 也必须停（fail-closed），且报告标「无法确认清单」而非「确实没登记」',
      provider='codebuddy-code', model='space-bunny', task_type='core', paseo_list_error={'codebuddy-code/space-bunny'},
      paseo_stop=True, paseo_report=[('codebuddy-code/space-bunny', True)]),
 dict(n='走 CLI 时不查 Paseo 清单 ⇒ 拉清单失败也不影响（作用域只在走 Paseo 且落 cb）',
      provider='codebuddy-code', model='space-bunny', task_type='core', force_cli=True, paseo_list_error={'codebuddy-code/space-bunny'},
      want=dict(upstream='codebuddy-code', model='space-bunny', channel='cli')),
 dict(n='Paseo 清单缺 space-bunny 但走 CLI ⇒ 放行（CLI 路径实测正常，钉死的 2.106.1 也正常）', provider='codebuddy-code',
      model='space-bunny', task_type='core', force_cli=True, paseo_unlisted={'codebuddy-code/space-bunny'},
      want=dict(upstream='codebuddy-code', model='space-bunny', channel='cli')),
 dict(n='T0 落 hy3 时 Paseo 清单也缺 hy3 ⇒ 同样必须停（守卫对 cb 落点一视同仁，⛔ 不只管 space-bunny）', task_type='core',
      cooldowns={SPACE_BUNNY: DT(2099, 1, 1)}, paseo_unlisted={HY3}, paseo_stop=True, paseo_report=[(HY3, False)]),
 dict(n='守卫只管 cb：火山显式落点即使「未登记」也不拦', provider='volcengine-coding', model='deepseek-v4-flash',
      task_type='core', paseo_unlisted={'volcengine-coding/deepseek-v4-flash'},
      want=dict(upstream='volcengine-coding', model='deepseek-v4-flash', channel='paseo')),
 # ⛔ 自动路径不选 space-bunny：显式 cb 不给 model ⇒ 仍是同档 glm（既有用例已钉；这里再钉「默认类任务」不会落到它）
 dict(n='默认任务（免费池不可用）⇒ 仍落 T1 火山 v4.1，⛔ 不落 cb/space-bunny', task_type='core', free_off=True,
      want=dict(upstream='volcengine-coding', model='deepseek-v4.1-flash')),
 # 🔴 审查时机门控（2026-09-11）—— 契约：exit 79 = 轮不到，其余一律 fail-open
 #    起因：0910 一条会话每修一小块就派一次全量审查，11 个 agent / ≥7 次全量全白烧
 #    （审查产物带 REVIEW_HEAD / REVIEW_DIFF_SHA256 锚点，代码一改就作废）。
 dict(n='审查时机 exit 79 ⇒ ⛔ 不派', task_type='review', scope='small',
      due_probe=(79, 'due=no\nreason=merge-only\nbranch=feat/x\n'
                     'review_mode=merge-only\nwhen=test master main\n'),
      block='not_due'),
 # 🔴🔴 fail-open 三连：⛔ 「问不出来」绝不能当成 due=no —— 那会把审查派发整体掐死
 dict(n='命令不存在(127) ⇒ 照派', task_type='review', scope='small',
      due_probe=(127, ''),
      want=dict(upstream='codex', model='gpt-5.6-sol')),
 dict(n='旧版不认 --due(exit 1) ⇒ 照派', task_type='review', scope='small',
      due_probe=(1, ''),
      want=dict(upstream='codex', model='gpt-5.6-sol')),
 dict(n='due=yes(exit 0) ⇒ 照派', task_type='review', scope='small',
      due_probe=(0, 'due=yes\nbranch=test\n'),
      want=dict(upstream='codex', model='gpt-5.6-sol')),
 # ⭐ 反例：CHECK 6 验收⛔不受本门控管（验收本来就该在改完之后跑）
 dict(n='[验收] 任务 ⇒ ⛔ 不被时机门控拦', task_type='review', scope='small',
      user_input='[验收] S3 官方 CHECK6 复核', due_probe=(79, 'due=no\n'),
      want=dict(upstream='codex', model='gpt-5.6-sol')),
 dict(n='短审查走 CLI（codex 默认）', task_type='review', scope='small',
      want=dict(upstream='codex', model='gpt-5.6-sol',
                provider='codex', channel='cli')),
 # 🔴 2026-10-06 review 默认模型可覆盖：RIFT_REVIEW_MODEL / codex config 换值 ⇒ 跟着走（⛔ 不写死 gpt-5.6-sol）
 dict(n='review 默认模型可覆盖（codex config 换值）', task_type='review', scope='small',
      review_model='gpt-5.6-luna',
      want=dict(upstream='codex', model='gpt-5.6-luna', channel='cli')),
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
 dict(n='高峰(周三15点) T2 走轮换首位火山', task_type='core', free_off=True, failed=1,
      when=DT(2026,9,9,15), want=dict(upstream='volcengine-coding', model='deepseek-v4-flash')),
 # 🔴 2026-09-10 换代连带：cb 退出 T2 池 ⇒ **cb 打折也影响不到 T2**（池里没它）。
 #    ⛔ 这两条原本断言「非高峰/周末 T2 落 cb」，换代后已被推翻 ⇒ 改成断言新不变量。
 dict(n='非高峰(周三19点) cb 打折也进不了 T2（池里没 cb）', task_type='core', free_off=True, failed=1,
      when=DT(2026,9,9,19), want=dict(upstream='volcengine-coding', model='deepseek-v4-flash')),
 # 🔴 2026-09-11 百炼移出 T2 池（`-0731` 是另一个模型，且百炼的裸 id 是 403）
 #    ⇒ T2 只剩火山两套餐，**深夜没有可切的打折池** ⇒ 落点不变。
 dict(n='深夜(周三23点) T2 只剩火山两池 ⇒ 落点不变', task_type='core', free_off=True, failed=1,
      when=DT(2026,9,9,23), want=dict(upstream='volcengine-coding', model='deepseek-v4-flash')),
 dict(n='周末白天 cb 全天打折，T2 仍不落 cb', task_type='core', free_off=True, failed=1,
      when=DT(2026,9,12,15), want=dict(upstream='volcengine-coding', model='deepseek-v4-flash')),
 # ⚠️ cb 的折扣集现在是**空的**（唯一成员 deepseek-v4-pro 已禁用）⇒ **cb 折扣对阶梯无作用点**。
 #    ⛔ 不要因此删掉 DISCOUNT_WINDOWS 的 cb 条目——`deepseek-v4.1-flash` 若确认继承折扣就会复活。
 # 🔴 原名「T1 单池 ⇒ 折扣不改落点」—— 09-15 起就不是单池了，那个名字早已过时；
 #    09-24 cb 又移出 ⇒ 池 = 火山两套餐 + 百炼。周末 15:00：cb 虽在折扣时段但不在池里，
 #    百炼的夜间窗口不覆盖下午 ⇒ 三池都原价 ⇒ 回轮换首位。
 dict(n='周末下午 T1 三池都原价 ⇒ 回轮换首位火山 coding', task_type='core',
      free_off=True, failed=0,
      when=DT(2026,9,12,15), want=dict(upstream='volcengine-coding', model='deepseek-v4.1-flash')),
 # 🔴 关键反例：任何时段都⛔不得把档位冲掉
 dict(n='深夜 T1 档位不被冲掉', task_type='core', free_off=True, failed=0,
      when=DT(2026,9,9,23), want=dict(model='deepseek-v4.1-flash')),
 dict(n='深夜免费档仍是 T0', task_type='core', when=DT(2026,9,9,23),
      want=dict(upstream='openrouter-free', model='stealth/space-bunny-alpha')),
 # --free 新语义（0909：不再委派，只影响选档）
 dict(n='--free 无排除 → T0', free=True, task_type='core',
      want=dict(upstream='openrouter-free', model='stealth/space-bunny-alpha')),
 # ⭐ --free 只放宽【能力类】：Bunny 冷却时 hy3 的 algorithm 短板被放宽 ⇒ hy3 接
 dict(n='--free 放宽能力类 → algorithm + Bunny 冷却 ⇒ hy3 接', free=True, task_type='algorithm',
      cooldowns={SPACE_BUNNY: DT(2099, 1, 1)},
      want=dict(upstream='codebuddy-code', model='hy3', thinking='max')),
 dict(n='--free 遇物理不可用（全池冷却）→ 停止', free=True, task_type='core',
      free_off=True, free_unavailable=True, free_probes=[]),
 # 🔴 --free ⛔ 不放宽物理不可用：多模态 + Bunny 冷却 ⇒ hy3/qfmodel 都接不了图 ⇒ 停（⛔ 不静默变付费）
 dict(n='--free + 多模态 + Bunny 冷却 → 停止（⛔ 能力放宽不含物理不可用）', free=True,
      task_type='algorithm', multimodal=True, cooldowns={SPACE_BUNNY: DT(2099, 1, 1)},
      free_unavailable=True, free_probes=[],
      free_report=[(SPACE_BUNNY, ['quota_cooldown']), (HY3, ['algorithm', 'multimodal']),
                   (QFM, ['algorithm', 'multimodal'])]),
 dict(n='--free + 全池探活不过 → 停止', free=True, task_type='core', probe_ok=False,
      free_unavailable=True, free_probes=[SPACE_BUNNY, HY3, QFM],
      free_report=[(SPACE_BUNNY, ['probe_failed']), (HY3, ['probe_failed']), (QFM, ['probe_failed'])]),
 dict(n='--free + review → 冲突停止', free=True, task_type='review', conflict_free_review=True),
 dict(n='--free --provider codebuddy-code → 不冲突走 T0', free=True,
      provider='codebuddy-code', task_type='core',
      want=dict(upstream='codebuddy-code', model='hy3')),
 # ⛔ 不带 --free 时能力类排除照旧生效（证明放宽只对 --free 生效）—— 与上面 --free 那条同一输入
 dict(n='无 --free 时 algorithm + Bunny 冷却 ⇒ hy3 仍被 avoid 挡住', task_type='algorithm',
      cooldowns={SPACE_BUNNY: DT(2099, 1, 1)},
      want=dict(model='deepseek-v4-flash')),
 # 🔴 2026-09-10：T3 从「v4-pro 四池 + qwen 同档替代」变成「qwen3.8-max 单池、无同档替代」
 #    ⇒ 原本那两条以「四池全不可用」为前提的用例前提已不存在，改成断言新形态。
 dict(n='T3 单池即主落点（⛔ 不再有四池轮换）', task_type='core', free_off=True, failed=2,
      want=dict(upstream='bailian-token-plan', model='qwen3.8-max',
                provider='pi/bailian-token-plan')),
 # 🔴 反例：主落点可用时⛔不许被同档替代插队
 dict(n='TIER_PEERS 已空 ⇒ T3 照常落主落点，⛔ 不因空表报错', task_type='core',
      free_off=True, failed=2,
      want=dict(upstream='bailian-token-plan', model='qwen3.8-max')),
 # 🔴 T3 主池+peer 全不可用 ⇒ 【可用性升档】到 T4，⛔ 不停在半路
 dict(n='T3 主池+peer 全不可用 → 升到 T4', task_type='core', free_off=True, failed=2,
      unavailable={'bailian-token-plan/qwen3.8-max'},
      want=dict(model='kimi-k3-1', availability_escalations=[('qwen3.8-max','kimi-k3-1','unavailable')])),
 # ⭐ 可用性升档（用户 2026-09-09 决定：允许【向上】换档 + 必须报告）
 # 🔴 反例保留：T1 全不可用时⛔不许掉进 T3 的 peer，只许升到【相邻】的 T2
 # ⭐ T1 主池（cb）拿不到但同档 peer（glm 三池）可用 ⇒ 落 peer 并**留痕**
 #    🔴 这条专测异构审查抓到的漏：§5 落到 TIER_PEERS 时原先**根本不 append**，
 #       导致【档内换落点】对用户完全不可见。
 dict(n='T1 主池不可用 → 落同档 glm 并留痕', task_type='core', free_off=True,
      unavailable={'volcengine-coding/deepseek-v4.1-flash',
                   'volcengine-agent-plan/deepseek-v4.1-flash',
                   'bailian-token-plan/deepseek-v4.1-flash'},
      want=dict(upstream='volcengine-coding', model='glm-5.3-flash',
                availability_escalations=[],
                tier_substitutions=[('deepseek-v4.1-flash', 'glm-5.3-flash', '本档所有池都拿不到')])),
 # ⭐ T1 池内逐级换池，⛔ 不该过早掉到同档替代
 # 🔴 2026-09-24 cb 移出后池序 = [火山 coding, 火山 agent-plan, 百炼]。原先三条是四池级联
 #    （cb → coding → agent-plan → 百炼），cb 那一级已不存在 ⇒ 收成两级，⛔ 不留假级联。
 dict(n='T1 coding 不可用 → 落 agent-plan（轮换第二位），⛔ 不掉 peer', task_type='core', free_off=True,
      unavailable={'volcengine-coding/deepseek-v4.1-flash'},
      want=dict(upstream='volcengine-agent-plan', model='deepseek-v4.1-flash',
                tier_substitutions=[])),
 dict(n='T1 火山两套餐都不可用 → 落百炼', task_type='core', free_off=True,
      unavailable={'volcengine-coding/deepseek-v4.1-flash',
                   'volcengine-agent-plan/deepseek-v4.1-flash'},
      want=dict(upstream='bailian-token-plan', model='deepseek-v4.1-flash')),
 # ⭐ 百炼这份带「限时夜间 5 折」⇒ 22:00-08:00 折扣排序把它提前
 dict(n='深夜 T1 百炼打折 ⇒ 排到池首', task_type='core', free_off=True,
      when=DT(2026,9,15,23), want=dict(upstream='bailian-token-plan', model='deepseek-v4.1-flash')),
 dict(n='白天 T1 无人打折 ⇒ 回轮换首位火山 coding', task_type='core', free_off=True,
      when=DT(2026,9,15,15), want=dict(upstream='volcengine-coding', model='deepseek-v4.1-flash')),
 dict(n='T1 全不可用 → 向上换档到 T2（⛔ 不是 T3 的 peer）', task_type='core', free_off=True,
      unavailable={'volcengine-coding/deepseek-v4.1-flash',
                   'volcengine-agent-plan/deepseek-v4.1-flash',
                   'bailian-token-plan/deepseek-v4.1-flash',
                   'volcengine-coding/glm-5.3-flash', 'volcengine-agent-plan/glm-5.3-flash',
                   'codebuddy-code/glm-5.3-flash'},
      want=dict(model='deepseek-v4-flash', upstream='volcengine-coding',
                availability_escalations=[('deepseek-v4.1-flash','deepseek-v4-flash','unavailable')])),
 dict(n='T1+T2 全不可用 → 一路升到 T3', task_type='core', free_off=True,
      unavailable={'volcengine-coding/deepseek-v4.1-flash',
                   'volcengine-agent-plan/deepseek-v4.1-flash',
                   'bailian-token-plan/deepseek-v4.1-flash',
                   'volcengine-coding/glm-5.3-flash', 'volcengine-agent-plan/glm-5.3-flash',
                   'codebuddy-code/glm-5.3-flash',
                   'volcengine-coding/deepseek-v4-flash', 'volcengine-agent-plan/deepseek-v4-flash',
                   'bailian-token-plan/deepseek-v4-flash-0731', 'codebuddy-code/deepseek-v4-flash'},
      want=dict(model='qwen3.8-max', upstream='bailian-token-plan',
                availability_escalations=[('deepseek-v4.1-flash','deepseek-v4-flash','unavailable'),
                                          ('deepseek-v4-flash','qwen3.8-max','unavailable')])),
 # 🔴 本档已无同档替代 ⇒ 唯一池拿不到就**只能升 T4**，⛔ 不得落到任何未测模型
 dict(n='T3 唯一池不可用 → 只能升 T4，⛔ 不落未测模型', task_type='core',
      free_off=True, failed=2,
      unavailable={'bailian-token-plan/qwen3.8-max'},
      want=dict(upstream='codebuddy-code', model='kimi-k3-1',
                availability_escalations=[('qwen3.8-max','kimi-k3-1','unavailable')])),
 # 🔴 阶梯到顶仍拿不到 ⇒ LAST_RESORT claude/claude-sonnet-5@max（⛔ 不停在半路）
 dict(n='T4 也拿不到 → 落 LAST_RESORT sonnet-5@max', task_type='core', free_off=True, failed=3,
      unavailable={'codebuddy-code/kimi-k3-1'},
      want=dict(upstream='claude', model='claude-sonnet-5', thinking='max',
                availability_escalations=[('kimi-k3-1','claude-sonnet-5','LAST_RESORT')])),
 dict(n='T3→T4 全不可用 → 一路到 LAST_RESORT（⛔ 不回落低档）', task_type='core',
      free_off=True, failed=2,
      unavailable={'bailian-token-plan/qwen3.8-max', 'codebuddy-code/kimi-k3-1'},
      want=dict(upstream='claude', model='claude-sonnet-5',
                availability_escalations=[('qwen3.8-max','kimi-k3-1','unavailable'),
                                          ('kimi-k3-1','claude-sonnet-5','LAST_RESORT')])),
 # 🔴 连 LAST_RESORT 都没有才停止
 dict(n='付费档全不可用 + claude 也不可用 → 停止', task_type='core', free_off=True,
      unavailable={'volcengine-coding/deepseek-v4.1-flash',
                   'volcengine-agent-plan/deepseek-v4.1-flash',
                   'bailian-token-plan/deepseek-v4.1-flash',
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
 dict(n='T3 全不可用 ⛔ 不许回落到更低档', task_type='core', free_off=True, failed=2,
      unavailable={'bailian-token-plan/qwen3.8-max'},
      want=dict(model='kimi-k3-1')),   # ⛔ ⛔ 绝不能是 glm-5.3-flash / deepseek-v4-flash
 # ⛔ 没有可用性问题时⛔不许无故升档
 dict(n='一切可用 → availability_escalations 必须为空', task_type='core', free_off=True,
      want=dict(model='deepseek-v4.1-flash', availability_escalations=[])),
 # ── 第 4 轮审查补 ──────────────────────────────────────────────
 # ❌1 LAST_RESORT ⛔ 不许覆盖用户显式 --thinking
 dict(n='LAST_RESORT ⛔ 不覆盖显式 --thinking', task_type='core', free_off=True,
      failed=3, thinking='low', unavailable={'codebuddy-code/kimi-k3-1'},
      want=dict(upstream='claude', model='claude-sonnet-5', thinking='low')),
 # ❌2 LAST_RESORT 要做 model 级探活，⛔ 不能只查 provider
 dict(n='claude 活着但 sonnet-5 拿不到 → 停止', task_type='core', free_off=True,
      failed=3, unavailable={'codebuddy-code/kimi-k3-1', 'claude/claude-sonnet-5'},
      no_landing=True),
 # ❌3 §6 的旧 downgrade() ⛔ 不许把档位降下去
 dict(n='⛔ 收尾 downgrade 不得降到更低档', task_type='core', free_off=True, failed=2,
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
      force_cli=True, free_off=True, failed=2,
      unavailable={'bailian-token-plan/qwen3.8-max', 'codebuddy-code/kimi-k3-1'},
      want=dict(upstream='claude', model='claude-sonnet-5', channel='paseo',
                provider='claude')),   # ⛔ 绝不能是 pi/claude
 dict(n='T4 落 cb kimi-k3-1（显式在 WALLET_PREF 里）', task_type='core',
      free_off=True, failed=3,
      want=dict(upstream='codebuddy-code', model='kimi-k3-1')),
]

fails = []
for c in CASES:
    PROBES.clear(); FREE_PROBES.clear(); FREE_REPORT.clear(); PASEO_REPORT.clear()
    _stale = sorted(set(c) & set(REMOVED_KNOBS))
    if _stale:
        fails.append(f"{c['n']}: 🔴 用了已删除的旋钮 {_stale} —— " + '；'.join(REMOVED_KNOBS[k] for k in _stale))
        continue
    try:
        got = run_case(c)
        if c.get('block'):     fails.append(f"{c['n']}: 期望被拦({c['block']})，实际放行 {got}"); continue
        if c.get('delegated'): fails.append(f"{c['n']}: 期望委派，实际 {got}"); continue
        if c.get('exhausted'): fails.append(f"{c['n']}: 期望阶梯到顶停止，实际 {got}"); continue
        if c.get('free_unavailable'): fails.append(f"{c['n']}: 期望 --free 不可用停止，实际 {got}"); continue
        if c.get('conflict_free_review'): fails.append(f"{c['n']}: 期望 free×review 冲突，实际 {got}"); continue
        if c.get('review_provider_conflict'): fails.append(f"{c['n']}: 期望 review provider 冲突，实际 {got}"); continue
        if c.get('blocked_model'): fails.append(f"{c['n']}: 期望被屏蔽，实际 {got}"); continue
        if c.get('paseo_stop'):
            fails.append(f"{c['n']}: 期望「Paseo 清单缺该型号 ⇒ 停止」，实际落到 {got.get('upstream')}/{got.get('model')} ({got.get('channel')})"); continue
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
    except PaseoUnlisted:
        if not c.get('paseo_stop'): fails.append(f"{c['n']}: 🔴 意外判为「Paseo 清单缺该型号」")
    except NoLanding:
        if not c.get('no_landing'): fails.append(f"{c['n']}: 🔴 意外报『无可用落点』——本档应当有落点")
    except BlockedModel:
        if not c.get('blocked_model'): fails.append(f"{c['n']}: 🔴 意外判为被屏蔽型号")
    except NameError as e:
        fails.append(f"{c['n']}: 🔴 伪代码里有未定义名 —— {e}")
    except Exception as e:
        fails.append(f"{c['n']}: {type(e).__name__}: {e}")
    # ⚠️ 放在 try 之外：被拦 / 停止的用例（如 --free 拿不到）同样要核「探过谁」
    if 'free_probes' in c and FREE_PROBES != c['free_probes']:
        fails.append(f"{c['n']}: T0 探活 期望 {c['free_probes']} 实际 {FREE_PROBES}")
    if 'probes' in c and PROBES != c['probes']:
        fails.append(f"{c['n']}: first_available 探活 期望 {c['probes']} 实际 {PROBES}")
    if 'paseo_report' in c and PASEO_REPORT != c['paseo_report']:
        fails.append(f"{c['n']}: Paseo 守卫报告 期望 {c['paseo_report']} 实际 {PASEO_REPORT}")
    if 'free_report' in c and FREE_REPORT != c['free_report']:
        fails.append(f"{c['n']}: --free 逐条原因 期望 {c['free_report']} 实际 {FREE_REPORT}")

print("=== §2 管线表驱动验证 ===")
print(f"用例 {len(CASES)} 条")
print("✅ 全部通过" if not fails else "\n".join("❌ " + f for f in fails))
sys.exit(1 if fails else 0)
