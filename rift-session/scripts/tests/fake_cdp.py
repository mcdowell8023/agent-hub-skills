"""Tiny fake Chrome DevTools server (HTTP /json/* + RFC 6455 websocket) for offline tests."""
import base64
import hashlib
import json
import socket
import socketserver
import struct
import threading

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _recv_exact(sock, n, buf):
    while len(buf) < n:
        chunk = sock.recv(65536)
        if not chunk:
            raise EOFError
        buf += chunk
    return buf[:n], buf[n:]


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        srv = self.server.fake
        sock, buf = self.request, b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                return
            buf += chunk
        head, buf = buf.split(b"\r\n\r\n", 1)
        lines = head.decode().split("\r\n")
        method, path, _ = lines[0].split(" ", 2)
        hdrs = {l.split(":", 1)[0].lower(): l.split(":", 1)[1].strip() for l in lines[1:] if ":" in l}
        if hdrs.get("upgrade", "").lower() == "websocket":
            return self._ws(sock, hdrs, buf, srv)
        srv.http_log.append((method, path))
        if path == "/json/version":
            body = {"Browser": "FakeChrome/1"}
        elif path == "/json/list":
            body = list(srv.pages)
        elif path.startswith("/json/new"):
            page = {"type": "page", "webSocketDebuggerUrl": "ws://127.0.0.1:%d/devtools/page/1" % srv.port}
            srv.pages.append(page)
            body = page
        else:
            body = {}
        data = json.dumps(body).encode()
        sock.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n"
                     b"Connection: close\r\n\r\n" % len(data) + data)

    def _send(self, sock, opcode, payload):
        n = len(payload)
        h = bytes([0x80 | opcode])
        h += bytes([n]) if n < 126 else (bytes([126]) + struct.pack(">H", n) if n < 65536 else bytes([127]) + struct.pack(">Q", n))
        sock.sendall(h + payload)

    def _ws(self, sock, hdrs, buf, srv):
        srv.ws_connections += 1  # count before replying so tests never race the handshake
        key = hdrs["sec-websocket-key"]
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        sock.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      "Sec-WebSocket-Accept: %s\r\n\r\n" % accept).encode())
        while True:
            try:
                (b1, b2), buf = _recv_exact(sock, 2, buf)
                ln = b2 & 0x7F
                if ln == 126:
                    r, buf = _recv_exact(sock, 2, buf)
                    ln = struct.unpack(">H", r)[0]
                elif ln == 127:
                    r, buf = _recv_exact(sock, 8, buf)
                    ln = struct.unpack(">Q", r)[0]
                mask, buf = _recv_exact(sock, 4, buf)
                payload, buf = _recv_exact(sock, ln, buf)
            except (EOFError, OSError):
                return
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            opcode = b1 & 0x0F
            if opcode == 0x8:
                return
            if opcode != 0x1:
                continue
            msg = json.loads(payload.decode())
            srv.messages.append(msg)
            # noise: a CDP event and a ping before the real answer
            self._send(sock, 0x1, json.dumps({"method": "Page.frameNavigated", "params": {}}).encode())
            self._send(sock, 0x9, b"hi")
            reply = {"id": msg["id"], "result": srv.respond(msg["method"], msg.get("params", {}))}
            if isinstance(reply["result"], dict) and reply["result"].get("__error__"):
                reply = {"id": msg["id"], "error": {"message": reply["result"]["__error__"]}}
            data = json.dumps(reply).encode()
            # split big replies into two fragments to exercise continuation frames
            if len(data) > 200:
                half = len(data) // 2
                sock.sendall(bytes([0x01]) + (bytes([126]) + struct.pack(">H", half) if half < 65536 else bytes([127]) + struct.pack(">Q", half)) + data[:half])
                rest = data[half:]
                sock.sendall(bytes([0x80]) + (bytes([126]) + struct.pack(">H", len(rest)) if len(rest) < 65536 else bytes([127]) + struct.pack(">Q", len(rest))) + rest)
            else:
                self._send(sock, 0x1, data)


class FakeCDP:
    def __init__(self, port=0):
        self.messages, self.http_log, self.ws_connections = [], [], 0
        self.cookies = []
        self.eval_handler = lambda expr: None
        self.nav_error = None
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", port), _Handler)
        self.server.daemon_threads = True
        self.server.fake = self
        self.port = self.server.server_address[1]
        self.pages = [{"type": "page", "webSocketDebuggerUrl": "ws://127.0.0.1:%d/devtools/page/0" % self.port}]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def respond(self, method, params):
        if method == "Runtime.evaluate":
            return {"result": {"type": "string", "value": self.eval_handler(params["expression"])}}
        if method == "Page.navigate":
            return {"errorText": self.nav_error} if self.nav_error else {"frameId": "f"}
        if method == "Network.getCookies":
            return {"cookies": list(self.cookies)}
        if method == "Network.setCookie":
            self.cookies = [c for c in self.cookies if c["name"] != params["name"]] + [params]
            return {"success": True}
        if method == "Network.deleteCookies":
            self.cookies = [c for c in self.cookies if c["name"] != params["name"]]
            return {}
        if method == "Test.echo":
            return {"echo": params.get("text", "")}
        if method == "Test.fail":
            return {"__error__": "boom"}
        return {}

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
