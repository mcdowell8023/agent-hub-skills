#!/usr/bin/env python3
"""rift-reap 的覆盖面自检与归档结果验证。

两个模式：

  preflight —— 归档前，检查候选集是否可信
      python3 reap-verify.py preflight --me <agent-id> --snapshot <mcp-list.json>
      检查：① 我在不在列表里 ② 是不是顶层会话 ③ 返回条数有没有撞 limit 上限
      ⚠️ 不检查时间窗口 —— sinceHours 实测被后端忽略，覆盖面只取决于 limit

  verify    —— 归档后，验证只动了自己的
      python3 reap-verify.py verify --me <agent-id> \
          --before <归档前.json> --after <归档后.json> --reaped <清单.json>
      判据：① 我的子会话残留 0 ② 误伤 0 ③ 遗漏 0
      🔴 用 id 集合比对，不看数量差 —— 并发会让数量差对不上而集合仍然正确。

快照 JSON 接受 {"agents":[...]} 或裸数组。
"""
import argparse, json, sys
from datetime import datetime, timezone

PARENT_KEY = "paseo.parent-agent-id"
MCP_LIMIT = 200


def load(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("agents", d) if isinstance(d, dict) else d


def children_of(agents, me):
    return [a for a in agents if (a.get("labels") or {}).get(PARENT_KEY) == me]


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def preflight(args):
    agents = load(args.snapshot)
    ok = True

    me = next((a for a in agents if a.get("id") == args.me), None)
    if me is None:
        print(f"⚠️  我 ({args.me[:8]}) 不在这份快照里 —— 可能是 statuses 过滤掉了自己（running）")
        print("    这不算失败，但无法自检创建时间；请用一份含 running 的快照跑 preflight")
    else:
        labels = me.get("labels") or {}
        parent = labels.get(PARENT_KEY)
        print(f"🔍 我: {args.me[:8]}  title={me.get('title','?')[:40]!r}  status={me.get('status')}")
        print(f"    parent={'(顶层会话)' if not parent else parent[:8]}")
        created = parse_ts(me.get("createdAt"))
        if created:
            hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
            print(f"    我创建于 {me['createdAt']}  ≈ {hours:.0f}h 前")
            # 🔴 不检查 sinceHours 窗口 —— 2026-09-09 实测该参数被后端静默忽略
            #    (sinceHours=1 返回 149 条 updatedAt 超过 1 小时的记录，最早 28 天前)
            #    覆盖面的唯一风险是 limit 截断，见下方检查。

    n = len(agents)
    print(f"\n📊 快照条数: {n}")
    if n >= MCP_LIMIT:
        print(f"    🔴 撞到 limit 上限 {MCP_LIMIT} ⇒ 结果被截断，候选集不完整")
        print(f"       ⇒ 按 statuses 拆细，或加 cwd 参数缩小范围（⛔ sinceHours 无效，别指望它分段）")
        ok = False
    else:
        print(f"    ✅ < {MCP_LIMIT}，未截断")

    kids = children_of(agents, args.me)
    print(f"\n📋 我的子会话: {len(kids)}")
    by = {}
    for k in kids:
        key = (k.get("status"), (k.get("attentionReason") or "null"))
        by[key] = by.get(key, 0) + 1
    for (st, ar), cnt in sorted(by.items()):
        flag = "  ⚠️ 报错" if ar == "error" else ("  ⚠️ 非 closed" if st != "closed" else "")
        print(f"    status={st:<8} attentionReason={ar:<10} {cnt}{flag}")

    print("\n" + ("✅ preflight 通过" if ok else "🔴 preflight 未通过 —— 先解决上面的问题"))
    return 0 if ok else 1


def verify(args):
    before = {a["id"] for a in load(args.before)}
    after_agents = load(args.after)
    after = {a["id"] for a in after_agents}
    reaped = {a["id"] for a in load(args.reaped)}

    gone = before - after
    added = after - before
    residual = children_of(after_agents, args.me)

    hurt = gone - reaped      # 消失了但不在我的清单 = 误伤
    missed = reaped - gone    # 在我的清单但没消失 = 遗漏

    print(f"归档清单: {len(reaped)}")
    print(f"消失的  : {len(gone)}")
    print(f"新出现的: {len(added)}   ← 并发：期间别的会话也在结束")
    print(f"\n数量核对: {len(before)} - {len(gone)} + {len(added)} = {len(before)-len(gone)+len(added)}  (实测 {len(after)})")
    print(f"⚠️  数量差 {len(before)-len(after)} ≠ 归档数 {len(reaped)} 是正常的（并发），以下集合判据才是准的\n")

    checks = [
        ("① 我的子会话残留", len(residual), 0),
        ("② 误伤（消失但不在清单）", len(hurt), 0),
        ("③ 遗漏（清单里但没消失）", len(missed), 0),
    ]
    ok = True
    for name, got, want in checks:
        mark = "✅" if got == want else "🔴"
        if got != want:
            ok = False
        print(f"{mark} {name}: {got} (期望 {want})")

    for i in sorted(hurt):
        print(f"    🔴 误伤: {i}")
    for i in sorted(missed):
        print(f"    🔴 遗漏: {i}")
    for r in residual:
        print(f"    🔴 残留: {r['id'][:8]}  {r.get('title','')[:40]}")

    print("\n" + ("✅ 验证通过 —— 只动了自己的子会话" if ok else "🔴 验证未通过"))
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("preflight")
    a.add_argument("--me", required=True)
    a.add_argument("--snapshot", required=True)

    b = sub.add_parser("verify")
    b.add_argument("--me", required=True)
    b.add_argument("--before", required=True)
    b.add_argument("--after", required=True)
    b.add_argument("--reaped", required=True)

    args = p.parse_args()
    sys.exit(preflight(args) if args.cmd == "preflight" else verify(args))


if __name__ == "__main__":
    main()
