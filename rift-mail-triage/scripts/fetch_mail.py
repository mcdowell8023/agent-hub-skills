# -*- coding: utf-8 -*-
"""
拉取收件箱近 N 天邮件 -> JSON，供后续处理（人工看/脚本处理/喂给 LLM 会话）读取。

用法:
  python fetch_mail.py --days 7 --out state/inbox_2026-08-10.json

设计取舍:
  * 只读 INBOX，不动任何邮件状态。**绝不把未读标成已读** ——
    用 BODY.PEEK[] 而非 RFC822，后者会隐式置 \\Seen，
    那样你打开邮箱会发现邮件莫名其妙全变已读。
  * 正文截断 + 剥离法务声明，控制产出体量。
  * 线程字段(message_id/in_reply_to/references)必须带出来，
    否则生成的草稿无法挂回原邮件线程。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mail_lib import (attachments_of, body_of, decode_mime, imap_connect,  # noqa: E402
                      msg_datetime, parse_message, since_date)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out", required=True)
    ap.add_argument("--body-limit", type=int, default=6000)
    ap.add_argument("--max-messages", type=int, default=200)
    args = ap.parse_args()

    M = imap_connect()
    try:
        typ, _ = M.select("INBOX", readonly=True)  # readonly 双保险
        if typ != "OK":
            raise SystemExit(f"[fetch] SELECT INBOX 失败: {typ}")

        typ, data = M.search(None, "SINCE", since_date(args.days))
        if typ != "OK":
            raise SystemExit(f"[fetch] SEARCH 失败: {typ}")
        ids = data[0].split()

        # 未读集合：用来标 unread，而不是靠 FETCH 回来的 FLAGS（peek 下不一定带回）
        typ, udata = M.search(None, "UNSEEN")
        unread = set(udata[0].split()) if typ == "OK" else set()

        if len(ids) > args.max_messages:
            print(f"[fetch] 窗口内 {len(ids)} 封，超出上限 {args.max_messages}，"
                  f"取最近 {args.max_messages} 封")
            ids = ids[-args.max_messages:]

        messages = []
        for num in ids:
            typ, mdata = M.fetch(num, "(BODY.PEEK[])")  # PEEK：不置已读
            if typ != "OK" or not mdata or not mdata[0]:
                continue
            raw = mdata[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            try:
                msg = parse_message(raw)
            except Exception as e:
                print(f"[fetch] 解析失败 uid={num}: {e}")
                continue

            dt = msg_datetime(msg)
            messages.append({
                "uid": num.decode(),
                "message_id": (msg.get("Message-ID") or "").strip(),
                "in_reply_to": (msg.get("In-Reply-To") or "").strip(),
                "references": (msg.get("References") or "").strip(),
                "from": decode_mime(msg.get("From")),
                "to": decode_mime(msg.get("To")),
                "cc": decode_mime(msg.get("Cc")),
                "subject": decode_mime(msg.get("Subject")),
                "date": dt.isoformat() if dt else (msg.get("Date") or ""),
                "unread": num in unread,
                "attachments": attachments_of(msg),
                "body": body_of(msg, limit=args.body_limit),
            })

        messages.sort(key=lambda m: m.get("date") or "", reverse=True)
        out = {
            "fetched_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "window_days": args.days,
            "total": len(messages),
            "unread_count": sum(1 for m in messages if m["unread"]),
            "messages": messages,
        }
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"[fetch] OK  {len(messages)} 封（未读 {out['unread_count']}）-> {args.out}")
    finally:
        try:
            M.close()
        except Exception:
            pass
        M.logout()


if __name__ == "__main__":
    main()
