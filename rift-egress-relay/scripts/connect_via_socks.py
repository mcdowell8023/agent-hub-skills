#!/usr/bin/env python3
"""HTTP CONNECT proxy that relays through an upstream SOCKS5 proxy.

Exists because AWS CLI v2 (botocore) only honours http:// proxies, while the
only working egress path is an `ssh -D` SOCKS5 tunnel.
"""
import socket, threading, select, sys

SOCKS = ("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 1080)
LISTEN = ("127.0.0.1", int(sys.argv[2]) if len(sys.argv) > 2 else 18888)


def socks5_connect(host, port):
    s = socket.create_connection(SOCKS, timeout=25)
    s.sendall(b"\x05\x01\x00")
    if s.recv(2) != b"\x05\x00":
        raise RuntimeError("socks5 greeting rejected")
    hb = host.encode()
    s.sendall(b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb + port.to_bytes(2, "big"))
    r = s.recv(4)
    if len(r) < 4 or r[1] != 0:
        raise RuntimeError("socks5 connect failed: %r" % (r,))
    atyp = r[3]
    if atyp == 1:
        s.recv(6)
    elif atyp == 3:
        s.recv(s.recv(1)[0] + 2)
    elif atyp == 4:
        s.recv(18)
    return s


def pipe(a, b):
    try:
        while True:
            ready, _, _ = select.select([a, b], [], [], 300)
            if not ready:
                return
            for x in ready:
                data = x.recv(65536)
                if not data:
                    return
                (b if x is a else a).sendall(data)
    except Exception:
        pass
    finally:
        for x in (a, b):
            try:
                x.close()
            except Exception:
                pass


def handle(c):
    up = None
    try:
        req = b""
        while b"\r\n\r\n" not in req:
            d = c.recv(4096)
            if not d:
                return
            req += d
        method, target, _ = req.split(b"\r\n")[0].decode().split(" ")
        if method != "CONNECT":
            c.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            return
        host, port = target.rsplit(":", 1)
        up = socks5_connect(host, int(port))
        c.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        pipe(c, up)
    except Exception as e:
        print("ERR %s" % (e,), flush=True)
        try:
            c.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            c.close()
        except Exception:
            pass


srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(LISTEN)
srv.listen(64)
print("CONNECT proxy %s:%d -> socks5 %s:%d" % (LISTEN + SOCKS), flush=True)
while True:
    conn, _ = srv.accept()
    threading.Thread(target=handle, args=(conn,), daemon=True).start()
