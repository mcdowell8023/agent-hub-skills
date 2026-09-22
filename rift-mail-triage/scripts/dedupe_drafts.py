# -*- coding: utf-8 -*-
"""
草稿箱同主题去重：每个主题只保留最新一封，删掉更早的。

用法:
  python dedupe_drafts.py            # 只列清单，不删（默认）
  python dedupe_drafts.py --apply    # 真的删

安全边界：
  * 只动草稿箱，绝不碰收件箱/已发送。
  * 只删「同主题且不是最新那封」的草稿，最新一封永远保留。
  * 主题不在本闭环生成范围内的（比如手工写的测试草稿）默认不动，
    除非用 --include-foreign 明确放开。
  * 删掉的草稿都能从本地 drafts/*.json（落盘目录见 config.json 的 output_root）
    重新生成，所以是可逆的。
"""
import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mail_lib import decode_mime, find_folder, imap_connect, parse_message  # noqa: E402


def norm(subject):
    s = (subject or "").strip().lower()
    while s.startswith("re:") or s.startswith("fw:") or s.startswith("fwd:"):
        s = s.split(":", 1)[1].strip()
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真的执行删除")
    ap.add_argument("--include-foreign", action="store_true",
                    help="连非本闭环生成的草稿也纳入去重")
    args = ap.parse_args()

    M = imap_connect()
    try:
        folder = find_folder(M, "drafts")
        quoted = folder if folder.startswith('"') else f'"{folder}"'
        typ, _ = M.select(quoted, readonly=not args.apply)
        if typ != "OK":
            raise SystemExit(f"[dedupe] 打开草稿箱失败: {typ}")

        # 必须走 UID 命令，不能用序号：expunge 会让序号整体重排，
        # 用序号删多封的话很容易删错（保留的被删、作废的留下）。
        typ, data = M.uid("SEARCH", None, "ALL")
        if typ != "OK" or not data or not data[0]:
            print("[dedupe] 草稿箱为空")
            return 0

        items = []
        for num in data[0].split():
            typ, md = M.uid("FETCH", num, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE TO)])")
            if typ != "OK" or not md or not md[0]:
                continue
            raw = md[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            msg = parse_message(raw)
            items.append({
                "uid": num,
                "subject": decode_mime(msg.get("Subject") or ""),
                "date": msg.get("Date") or "",
                "to": decode_mime(msg.get("To") or ""),
            })

        groups = defaultdict(list)
        for it in items:
            groups[norm(it["subject"])].append(it)

        # 本闭环生成的草稿，主题都以 Re: 开头且对应 drafts/*.json；
        # 明显的手工草稿（如带「测试草稿」字样）默认不碰。
        to_delete = []
        for key, grp in groups.items():
            if len(grp) < 2:
                continue
            if not args.include_foreign and "测试草稿" in grp[0]["subject"]:
                print(f"[dedupe] 跳过非本闭环草稿组: {grp[0]['subject'][:50]}")
                continue
            grp.sort(key=lambda x: int(x["uid"]))   # uid 递增 = 写入时间递增
            keep, drop = grp[-1], grp[:-1]
            print(f"\n主题: {keep['subject'][:70]}")
            print(f"  保留 uid={keep['uid'].decode()}  {keep['date']}")
            for it in drop:
                print(f"  删除 uid={it['uid'].decode()}  {it['date']}")
                to_delete.append(it)

        if not to_delete:
            print("\n[dedupe] 没有需要清理的重复草稿")
            return 0

        print(f"\n[dedupe] 共 {len(to_delete)} 封待删除")
        if not args.apply:
            print("[dedupe] 这是预演（dry-run）。确认无误后加 --apply 执行。")
            return 0

        for it in to_delete:
            typ, _ = M.uid("STORE", it["uid"], "+FLAGS", "(\\Deleted)")
            if typ != "OK":
                print(f"[dedupe] 标记失败 uid={it['uid']}，中止")
                return 1
        M.expunge()
        print(f"[dedupe] 已删除 {len(to_delete)} 封。"
              f"如需恢复，重跑 save_draft.py 即可从本地 JSON 重建。")
        return 0
    finally:
        try:
            M.close()
        except Exception:
            pass
        M.logout()


if __name__ == "__main__":
    sys.exit(main())
