"""免费条目「已计费」探测的字段判定（probe-models.sh 里 qcn / OpenRouter 两条探活共用）。

🔴 为什么单独一个模块：这是 freeUntil=None（截止未公布）条目**唯一**的失效证据，判定口径只能有一份——
   两处各写一遍，迟早一边认字符串、一边不认（r4 审查抓到的正是「只认 JSON number」）。

⭐ 三态，且 ⛔ fail-closed：
   free    恰好为 0         ⇒ 有证据证明现在免费
   billed  > 0              ⇒ 免费期已结束（模型照样答得动，只是开始扣费）
   unknown 缺失 / 非数字 / 布尔 / NaN / 负数 ⇒ 读不到证据 ⇒ 调用方必须按「无法确认免费」处理，⛔ 不许当免费
   代价：CLI / API 输出格式一变就少一个免费选项（回落付费 T1，便宜）；收益：不会静默扣费。
"""
import math


def num(v):
    """把计费字段规整成 float；认不出返回 None。数字字符串（"0.1"）认；布尔不认（True 会被 isinstance 当成 int）。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
    elif isinstance(v, str):
        try:
            x = float(v.strip())
        except ValueError:
            return None
    else:
        return None
    return None if math.isnan(x) else x


def classify(v):
    """⇒ ('free', 0.0) / ('billed', x) / ('unknown', None)"""
    x = num(v)
    if x is None or x < 0:
        return 'unknown', None
    return ('free', 0.0) if x == 0 else ('billed', x)
