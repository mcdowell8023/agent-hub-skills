#!/usr/bin/env python3
"""scripts/billing.py 的表驱动单元测试 —— 免费条目「已计费」探测的唯一判定口径（三态、fail-closed）。

⚠️ 为什么要单测：它是 freeUntil=None 条目唯一的失效证据；判错一个方向分别意味着
   · billed 判成 free  ⇒ 静默扣费（r4 审查抓到的「只认 JSON number」就是这一类）
   · free 判成 billed / unknown ⇒ 少一个免费选项（回落付费 T1，便宜）
   布尔值尤其危险：Python 里 True 是 int，不显式排除会被当成 1.0 ⇒ 误判已计费。
"""
import math, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from billing import classify, num

CASES = [
    # (输入, 期望三态, 期望数值)
    (None, 'unknown', None), ('', 'unknown', None), ('abc', 'unknown', None), ('n/a', 'unknown', None),
    (True, 'unknown', None), (False, 'unknown', None),                    # 布尔 ⛔ 不当数字
    ([], 'unknown', None), ({}, 'unknown', None), ([0], 'unknown', None),
    (float('nan'), 'unknown', None), ('nan', 'unknown', None),
    (-1, 'unknown', None), ('-0.5', 'unknown', None),                      # 负数读不出含义 ⇒ 不当免费
    (0, 'free', 0.0), (0.0, 'free', 0.0), ('0', 'free', 0.0), ('0.0', 'free', 0.0), (' 0 ', 'free', 0.0),
    (0.1, 'billed', 0.1), ('0.1', 'billed', 0.1), (' 0.002 ', 'billed', 0.002),
    (1e-9, 'billed', 1e-9),                                               # 再小也是在扣费
    (float('inf'), 'billed', float('inf')), ('inf', 'billed', float('inf')),
]
fails = []
for v, want_kind, want_x in CASES:
    kind, x = classify(v)
    if kind != want_kind:
        fails.append(f"classify({v!r}) 期望 {want_kind} 实际 {kind}")
    elif want_x is not None and not (x == want_x or (math.isinf(want_x) and math.isinf(x))):
        fails.append(f"classify({v!r}) 数值 期望 {want_x} 实际 {x}")
    elif want_kind == 'unknown' and x is not None:
        fails.append(f"classify({v!r}) unknown 时数值必须是 None，实际 {x}")
assert num(True) is None and num(False) is None, "num(布尔) 必须是 None"

print("=== billing.classify 表驱动单测 ===")
print(f"用例 {len(CASES)} 条")
print("✅ 全部通过" if not fails else "\n".join("❌ " + f for f in fails))
sys.exit(1 if fails else 0)
