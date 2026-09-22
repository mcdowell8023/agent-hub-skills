# -*- coding: utf-8 -*-
"""
把回复草稿写进邮箱「草稿箱」(IMAP APPEND)，手机/网页版都能直接看到并发送。

用法:
  python save_draft.py --json drafts/2026-08-10_example.json

入参 JSON 结构:
{
  "to":          "a@x.com, b@y.com",
  "cc":          "c@z.com",              // 可选
  "subject":     "Re: ...",
  "body":        "纯文本正文（实际发送的内容）",
  "body_html":   "<html>...</html>",     // 可选，给了就发多部分(text/plain + text/html)
  "body_zh":     "中文版正文",            // body 是英文时必填，仅供本地查看
  "in_reply_to": "<原邮件 Message-ID>",   // 可选，挂线程用
  "references":  "<...> <...>"           // 可选
}

英文草稿会在 JSON 同目录导出 `<文件名>_中文版.md`（中英对照）供本地查看，
不参与发送。若正文判定为英文却没给 body_zh，会打印醒目告警——
中文版是硬要求，不能靠"记得写"来保证。

绝不发送。只写草稿箱，等人工过目后手动点发送。
"""
import argparse
import json
import os
import re
import sys

try:  # Windows 控制台默认 GBK，打印中文主题会 UnicodeEncodeError
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mail_lib import (decode_mime, find_folder, get_credentials,  # noqa: E402
                      imap_connect, parse_message)

import imaplib  # noqa: E402


def is_english(text):
    """CJK 字符占比低于 5% 视为英文正文。"""
    if not text:
        return False
    cjk = len(re.findall(r"[一-鿿]", text))
    letters = len(re.findall(r"[A-Za-z一-鿿]", text))
    if letters == 0:
        return False
    return (cjk / letters) < 0.05


def export_chinese(json_path, d):
    """
    导出中文阅读版 md（背景 + 来信翻译 + 回复中文 + 英文原文）。
    返回落盘路径，未导出返回 None。

    光有回复的中文版还不够——不了解来龙去脉就没法判断
    该不该发。所以上下文必须一起翻译进来。
    """
    if not is_english(d.get("body", "")):
        return None

    base = os.path.splitext(os.path.abspath(json_path))[0]
    out = base + "_中文版.md"

    MISSING = "> ⚠️ 生成草稿时没有提供本节内容，请补 `{}` 字段后重跑 save_draft.py。"

    zh = d.get("body_zh", "").strip() or MISSING.format("body_zh")
    ctx = d.get("context_zh", "").strip() or MISSING.format("context_zh")
    inc = d.get("incoming_zh", "").strip() or MISSING.format("incoming_zh")

    lines = [
        f"# {d['subject']}",
        "",
        "> **中文阅读版**，仅供本地查看。实际发送的是文末的英文原文。",
        "",
        f"**收件人：** {d['to']}",
        "",
    ]
    if d.get("cc"):
        lines += [f"**抄送：** {d['cc']}", ""]
    lines += [
        "---", "",
        "## 一、背景脉络", "",
        ctx, "",
        "---", "",
        "## 二、对方来信（中文）", "",
        inc, "",
        "---", "",
        "## 三、我方回复（中文）", "",
        zh, "",
        "---", "",
        "## 四、英文原文（实际发送内容）", "",
        d.get("body", ""),
    ]

    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out


def build_message(d, sender):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = d["to"]
    if d.get("cc"):
        msg["Cc"] = d["cc"]
    msg["Subject"] = d["subject"]
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])

    # 线程挂靠：缺了这两个头，草稿发出去会另起一个新会话
    if d.get("in_reply_to"):
        msg["In-Reply-To"] = d["in_reply_to"]
        refs = d.get("references") or ""
        msg["References"] = (refs + " " + d["in_reply_to"]).strip()
    elif d.get("references"):
        msg["References"] = d["references"]

    msg.set_content(d["body"], subtype="plain", charset="utf-8")
    # 有 HTML 版就发 multipart/alternative：纯文本兜底，富客户端看表格版
    if d.get("body_html"):
        msg.add_alternative(d["body_html"], subtype="html", charset="utf-8")
    return msg


def count_same_subject(M, quoted_folder, subject):
    """
    数一下草稿箱里有几封同主题草稿。
    部分服务商(如网易)的服务端 SEARCH SUBJECT 不可用（恒返回 0），只能拉回 uid 后本地比对。
    """
    try:
        typ, _ = M.select(quoted_folder, readonly=True)
        if typ != "OK":
            return 0
        typ, data = M.search(None, "ALL")
        if typ != "OK" or not data or not data[0]:
            return 0
        key = subject.strip().lower().lstrip("re:").strip()
        n = 0
        for num in data[0].split():
            typ, md = M.fetch(num, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
            if typ != "OK" or not md or not md[0]:
                continue
            raw = md[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            subj = decode_mime(parse_message(raw).get("Subject") or "")
            if subj.strip().lower().lstrip("re:").strip() == key:
                n += 1
        return n
    except Exception as e:
        print(f"[draft] 同主题检测跳过: {e}")
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, help="草稿定义 JSON 文件")
    args = ap.parse_args()

    with open(args.json, "r", encoding="utf-8") as f:
        d = json.load(f)

    for k in ("to", "subject", "body"):
        if not d.get(k):
            raise SystemExit(f"[draft] 缺字段: {k}")

    sender, _ = get_credentials()
    msg = build_message(d, sender)

    M = imap_connect()
    try:
        folder = find_folder(M, "drafts")
        quoted = folder if folder.startswith('"') else f'"{folder}"'

        # 同一线程连着几天各写一封，草稿箱会堆出好几封近似的信，很容易误发旧版。
        # 这里只告警不删除——删邮件是不可逆的，交给人决定。
        dup = count_same_subject(M, quoted, d["subject"])
        if dup:
            print(f"[draft] !! 草稿箱已有 {dup} 封同主题草稿：{d['subject'][:60]}")
            print("[draft]    新草稿仍会写入。请人工确认要发哪一封，并删掉作废的。")

        raw = msg.as_bytes()
        # \Draft 标志 + 当前时间；folder 名含非 ASCII 时要加引号
        typ, resp = M.append(quoted, "\\Draft",
                             imaplib.Time2Internaldate(time.time()), raw)
        if typ != "OK":
            raise SystemExit(f"[draft] APPEND 失败: {typ} {resp}")
        print(f"[draft] OK -> 草稿箱({folder}): {d['subject']}")
    finally:
        M.logout()

    # 英文草稿必须留中文阅读版在本地，否则用户看不懂自己要发什么、也不知道来龙去脉
    zh_path = export_chinese(args.json, d)
    if zh_path:
        missing = [k for k in ("body_zh", "context_zh", "incoming_zh")
                   if not d.get(k, "").strip()]
        if missing:
            print(f"[draft] !! 警告：正文是英文，但缺少 {', '.join(missing)}，"
                  f"中文阅读版对应章节是占位内容。请补齐后重跑。")
        print(f"[draft] 中文阅读版 -> {zh_path}")
    else:
        print("[draft] 正文非英文，跳过中文阅读版导出")


if __name__ == "__main__":
    main()
