# -*- coding: utf-8 -*-
"""
IMAP/SMTP 公共库，默认适配网易企业邮(163/126同源)，其他服务商只需改配置。

凭据不落盘明文：`rift-mail setup` 把授权码存进 macOS 钥匙串，
运行时由 `rift-mail` 这个 shell 入口取出后经环境变量注入本进程：
  MAIL_USER  邮箱地址
  MAIL_PASS  客户端授权码（不是登录密码）

部分 IMAP 服务商(典型如网易 163/126/企业邮)的坑（务必保留 imap_connect 里的 ID 命令）：
  这些服务端要求客户端在 LOGIN 后上报 ID，
  否则任何 SELECT 都会返回 b'Unsafe Login. Please contact ...'。
  imaplib 默认不支持 ID 命令，需要手工注册进 Commands 表。
  如果你用的服务商没有这个限制，保留这段逻辑也无害（ID 失败会被忽略）。

配置优先级：环境变量 > 同目录 config.json > 内置默认值。
"""
import email
import imaplib
import json
import os
import re
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email import policy
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_SCRIPT_DIR, "config.json")

_DEFAULT_CONFIG = {
    "imap_host": "imap.qiye.163.com",
    "imap_port": 993,
    "smtp_host": "smtp.qiye.163.com",
    "smtp_port": 465,
    "client_id_contact": "you@example.com",
}


def load_config():
    """读同目录 config.json，缺失或坏文件时静默回退默认值（不影响脱敏发布版本可直接跑）。"""
    cfg = dict(_DEFAULT_CONFIG)
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            for k, v in user_cfg.items():
                if not k.startswith("_comment"):
                    cfg[k] = v
        except Exception as e:
            print(f"[mail_lib] config.json 读取失败，改用内置默认值: {e}")
    return cfg


_CFG = load_config()
IMAP_HOST = _CFG["imap_host"]
IMAP_PORT = int(_CFG["imap_port"])
SMTP_HOST = _CFG["smtp_host"]
SMTP_PORT = int(_CFG["smtp_port"])

# 注册 ID 命令：部分服务商(如网易系)反垃圾要求，缺了在这些服务商上必然 Unsafe Login
imaplib.Commands["ID"] = ("AUTH", "SELECTED")

_CLIENT_ID = ('("name" "RiftMailTriage" "version" "1.0"'
              ' "vendor" "claude-code" "contact" "%s")') % _CFG.get(
                  "client_id_contact", "you@example.com")


def get_credentials():
    user = os.environ.get("MAIL_USER", "").strip()
    pwd = os.environ.get("MAIL_PASS", "").strip()
    if not user or not pwd:
        raise SystemExit(
            "[mail_lib] 环境变量 MAIL_USER / MAIL_PASS 未注入。\n"
            "  这两个脚本不直接跑，一律通过 rift-mail 入口调用：\n"
            "    rift-mail setup <mailbox>   # 首次：录入邮箱 + 客户端授权码到 macOS 钥匙串\n"
            "    rift-mail selfcheck         # 之后：验证/日常使用\n"
        )
    return user, pwd


def imap_connect():
    """返回已登录并完成 ID 上报的 IMAP4_SSL 连接。"""
    user, pwd = get_credentials()
    ctx = ssl.create_default_context()
    M = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ctx)
    M.login(user, pwd)
    # 关键：部分服务商(如163/126)不发 ID 就会 Unsafe Login；其他服务商忽略此失败即可
    try:
        M._simple_command("ID", _CLIENT_ID)
        M._untagged_response("OK", [None], "ID")
    except Exception as e:
        print(f"[mail_lib] ID 命令失败（继续尝试）: {e}")
    return M


def smtp_connect():
    user, pwd = get_credentials()
    ctx = ssl.create_default_context()
    S = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx)
    S.login(user, pwd)
    return S


def decode_mime(value):
    """解码 =?utf-8?B?...?= 形式的邮件头，失败时原样返回。"""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def find_folder(M, kind):
    """
    定位特殊文件夹。kind: 'drafts' | 'sent'
    优先认 IMAP 特殊标志(\\Drafts)，退回名字匹配，
    再退回 modified UTF-7 的中文名（部分服务商如网易：草稿箱 = &g0l6P3ux-）。
    """
    flag = {"drafts": "\\\\Drafts", "sent": "\\\\Sent"}[kind]
    name_pat = {
        "drafts": ["drafts", "draft", "草稿箱", "草稿", "&g0l6P3ux-"],
        "sent": ["sent", "sent messages", "已发送", "&XfJT0ZAB-"],
    }[kind]

    typ, data = M.list()
    if typ != "OK":
        return "Drafts"

    candidates = []
    for raw in data:
        line = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else str(raw)
        m = re.match(r'\((?P<flags>[^)]*)\)\s+"(?P<delim>[^"]*)"\s+(?P<name>.+)$', line)
        if not m:
            continue
        flags = m.group("flags")
        name = m.group("name").strip().strip('"')
        candidates.append((flags, name))
        if re.search(flag, flags, re.IGNORECASE):
            return name

    for flags, name in candidates:
        decoded = name.encode("ascii", "ignore").decode("ascii").lower()
        if decoded in name_pat or name in name_pat:
            return name
        for pat in name_pat:
            if pat.lower() == decoded:
                return name
    return "Drafts"


def body_of(msg, limit=6000):
    """抽正文纯文本；无 text/plain 时用 html 退化剥标签。截断到 limit。"""
    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                try:
                    text += part.get_content()
                except Exception:
                    pass
        if not text.strip():
            for part in msg.walk():
                if part.get_content_type() == "text/html" and not part.get_filename():
                    try:
                        text += _strip_html(part.get_content())
                    except Exception:
                        pass
    else:
        try:
            text = msg.get_content()
        except Exception:
            text = ""
        if msg.get_content_type() == "text/html":
            text = _strip_html(text)

    text = _trim_boilerplate(text)
    if len(text) > limit:
        text = text[:limit] + f"\n...[正文已截断，原长 {len(text)} 字符]"
    return text.strip()


def _strip_html(html):
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</p>", "\n", html)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;", " ", html)
    html = re.sub(r"&amp;", "&", html)
    html = re.sub(r"&lt;", "<", html)
    html = re.sub(r"&gt;", ">", html)
    html = re.sub(r"[ \t]{2,}", " ", html)
    return re.sub(r"\n{3,}", "\n\n", html)


_BOILERPLATE = [
    r"CONFIDENTIAL: This e-mail, including its contents.*?(?=\n\n|\Z)",
    r"Although we routinely screen for viruses.*?(?=\n\n|\Z)",
    r"This e-mail message is intended for the above named recipient.*?(?=\n\n|\Z)",
    r"NOTE: This message is from an EXTERNAL SENDER.*?(?=\n\n|\Z)",
]


def _trim_boilerplate(text):
    """砍掉法务免责声明，避免它们吃掉正文预算。按需在这个列表里加你自己常见的模板。"""
    for pat in _BOILERPLATE:
        text = re.sub(pat, "", text, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"\n{3,}", "\n\n", text)


def attachments_of(msg):
    out = []
    for part in msg.walk():
        fn = part.get_filename()
        if fn:
            try:
                fn = decode_mime(fn)
            except Exception:
                pass
            # 内嵌签名图片是噪音，不算附件
            if re.match(r"(?i)^(image|Outlook-)[-\w]*\.(png|gif|jpg|jpeg)$", fn or ""):
                continue
            size = len(part.get_payload(decode=True) or b"")
            out.append({"filename": fn, "size": size})
    return out


def since_date(days):
    """IMAP SINCE 需要 DD-Mon-YYYY 格式（英文月份，跟本地 locale 无关）。"""
    d = datetime.now(timezone.utc) - timedelta(days=days)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{d.day:02d}-{months[d.month - 1]}-{d.year}"


def msg_datetime(msg):
    try:
        dt = parsedate_to_datetime(msg.get("Date"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def parse_message(raw_bytes):
    return email.message_from_bytes(raw_bytes, policy=policy.default)
