#!/usr/bin/env python3
"""Tiny Chrome DevTools Protocol CLI (stdlib only) that runs ON the STB.

    cdp.py tabs
    cdp.py nav <url>
    cdp.py eval '<js expression>'      # evaluates in the first page tab, prints the value
    cdp.py fps [seconds]               # measures rAF frame rate of the current page
    cdp.py back                        # history.back()

Event-driven, no polling. Used for diagnostics and by keyd.py for the Back key.
"""
import base64
import json
import os
import socket
import struct
import sys
import time
import urllib.request

PORT = 9222


def tabs():
    raw = urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=3).read().decode()
    return [t for t in json.loads(raw) if t.get("type") == "page"]


class WS:
    def __init__(self, ws_url, timeout=10):
        path = "/" + ws_url.split("/", 3)[3]
        self.s = socket.create_connection(("127.0.0.1", PORT), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((
            "GET %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"
            % (path, PORT, key)).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        self.rest = buf.split(b"\r\n\r\n", 1)[1]
        self.mid = 0

    def _recv_exact(self, n):
        while len(self.rest) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise EOFError("socket closed")
            self.rest += chunk
        out, self.rest = self.rest[:n], self.rest[n:]
        return out

    def _read_frame(self):
        b1, b2 = self._recv_exact(2)
        ln = b2 & 0x7F
        if ln == 126:
            ln = struct.unpack("!H", self._recv_exact(2))[0]
        elif ln == 127:
            ln = struct.unpack("!Q", self._recv_exact(8))[0]
        return self._recv_exact(ln)

    def call(self, method, params=None):
        self.mid += 1
        mid = self.mid
        payload = json.dumps({"id": mid, "method": method, "params": params or {}}).encode()
        mask = os.urandom(4)
        n = len(payload)
        hdr = bytearray([0x81])
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr += struct.pack("!H", n)
        else:
            hdr.append(0x80 | 127)
            hdr += struct.pack("!Q", n)
        masked = bytes(payload[i] ^ mask[i % 4] for i in range(n))
        self.s.sendall(bytes(hdr) + mask + masked)
        while True:
            msg = json.loads(self._read_frame().decode("utf-8", "replace"))
            if msg.get("id") == mid:
                return msg

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


def page_ws():
    t = tabs()
    if not t:
        raise SystemExit("no page tab")
    ws = WS(t[0]["webSocketDebuggerUrl"])
    try:
        ws.call("Debugger.enable")
        ws.call("Debugger.setBreakpointsActive", {"active": False})
    except Exception:
        pass
    return ws


def evaluate(expr, await_promise=False):
    ws = page_ws()
    try:
        r = ws.call("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                         "awaitPromise": await_promise})
    finally:
        ws.close()
    res = r.get("result", {})
    if "exceptionDetails" in res:
        return "EXC: " + json.dumps(res["exceptionDetails"].get("exception", {}).get("description"))
    return res.get("result", {}).get("value")


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    cmd = a[0]
    if cmd == "tabs":
        for t in tabs():
            print(t["id"], t["url"], "|", t["title"])
    elif cmd == "nav":
        ws = page_ws()
        print(ws.call("Page.navigate", {"url": a[1]}))
        ws.close()
    elif cmd == "eval":
        print(evaluate(a[1]))
    elif cmd == "gpu":
        raw = urllib.request.urlopen("http://127.0.0.1:%d/json/version" % PORT, timeout=3).read().decode()
        ws = WS(json.loads(raw)["webSocketDebuggerUrl"])
        r = ws.call("SystemInfo.getInfo")
        ws.close()
        g = r["result"]["gpu"]
        print("featureStatus:", json.dumps(g.get("featureStatus"), indent=1))
        print("devices:", g.get("devices"))
        print("aux:", json.dumps(g.get("auxAttributes"))[:600])
        print("problems:", g.get("driverBugWorkarounds"))
    elif cmd == "prof":
        secs = float(a[1]) if len(a) > 1 else 6
        ws = page_ws()
        ws.s.settimeout(40)
        ws.call("Profiler.enable")
        ws.call("Profiler.start")
        time.sleep(secs)
        r = ws.call("Profiler.stop")
        ws.close()
        prof = r["result"]["profile"]
        hits = {}
        for n in prof["nodes"]:
            cf = n["callFrame"]
            key = "%s  %s:%s" % (cf["functionName"] or "(anon)", cf["url"].split("/")[-1][:40], cf["lineNumber"])
            hits[key] = hits.get(key, 0) + n.get("hitCount", 0)
        total = sum(hits.values()) or 1
        for k, v in sorted(hits.items(), key=lambda kv: -kv[1])[:14]:
            print("%5.1f%%  %s" % (100.0 * v / total, k))
    elif cmd == "info":
        print(evaluate("JSON.stringify({t:document.title,rs:document.readyState,u:location.href,len:document.documentElement.outerHTML.length,imgs:document.images.length,vids:document.querySelectorAll('video').length,iframes:document.querySelectorAll('iframe').length})"))
    elif cmd == "back":
        print(evaluate("history.length>1 ? (history.back(),'back') : 'nohistory'"))
    elif cmd == "fps":
        secs = float(a[1]) if len(a) > 1 else 4
        js = ("new Promise(r=>{let n=0,t0=performance.now();function f(){n++;"
              "if(performance.now()-t0<%d)requestAnimationFrame(f);"
              "else r(Math.round(n/((performance.now()-t0)/1000)*10)/10)}requestAnimationFrame(f)})"
              % int(secs * 1000))
        print("fps:", evaluate(js, True))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
