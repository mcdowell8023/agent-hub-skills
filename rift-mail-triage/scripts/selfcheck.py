# -*- coding: utf-8 -*-
"""
连通性自检：登录 IMAP、定位草稿箱、数一下近 7 天邮件量。
不改任何邮件状态，不发信，不写草稿。

用法: python selfcheck.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mail_lib import IMAP_HOST, IMAP_PORT, find_folder, imap_connect, since_date  # noqa: E402


def main():
    print(f"[selfcheck] 连接 {IMAP_HOST}:{IMAP_PORT} ...")
    try:
        M = imap_connect()
    except Exception as e:
        print(f"[selfcheck] 登录失败: {e}")
        print("  常见原因：1) 用了登录密码而非客户端授权码  2) 邮箱未开启 IMAP")
        return 1

    try:
        typ, data = M.select("INBOX", readonly=True)
        if typ != "OK":
            print(f"[selfcheck] SELECT INBOX 失败: {typ} {data}")
            if data and b"Unsafe Login" in (data[0] or b""):
                print("  -> 命中 Unsafe Login：部分服务商(如163/126)要求先发 ID 命令，"
                      "mail_lib 的 ID 命令没生效")
            return 2
        print(f"[selfcheck] INBOX OK，共 {int(data[0])} 封")

        typ, sdata = M.search(None, "SINCE", since_date(7))
        n = len(sdata[0].split()) if typ == "OK" else -1
        typ, udata = M.search(None, "UNSEEN")
        u = len(udata[0].split()) if typ == "OK" else -1
        print(f"[selfcheck] 近 7 天 {n} 封，未读 {u} 封")

        drafts = find_folder(M, "drafts")
        print(f"[selfcheck] 草稿箱定位为: {drafts}")
        typ, ddata = M.select(f'"{drafts}"', readonly=True)
        if typ != "OK":
            print(f"[selfcheck] 警告：草稿箱无法打开 ({typ})，草稿写入可能失败")
            return 3
        print(f"[selfcheck] 草稿箱可写入（当前 {int(ddata[0])} 封）")
        print("[selfcheck] 全部通过")
        return 0
    finally:
        try:
            M.close()
        except Exception:
            pass
        try:
            M.logout()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
