#!/usr/bin/env python3
"""Mac-side receiver for framebuffer captures sent from the STB.

    python3 tools/fbrecv.py            # listens on :8801, writes /tmp/stb_fb.png on each POST

The box side (box/fbshot.py) POSTs /dev/fb0 (raw ARGB8888) and this converts it to a PNG
(stdlib only, downscaled 2x) so you can *see* exactly what is on the TV.
"""
import http.server
import struct
import sys
import zlib

OUT = "/tmp/stb_fb.png"


def png(width, height, rows):
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(n)
        w = int(self.headers.get("X-W", 1920))
        h = int(self.headers.get("X-H", 1080))
        stride = int(self.headers.get("X-Stride", w * 4))
        order = self.headers.get("X-Order", "BGRA")  # little-endian ARGB8888 => bytes B,G,R,A
        rows = []
        for y in range(0, h, 2):
            line = data[y * stride:y * stride + w * 4]
            out = bytearray()
            for x in range(0, w, 2):
                p = line[x * 4:x * 4 + 4]
                if len(p) < 4:
                    break
                if order == "BGRA":
                    out += bytes((p[2], p[1], p[0]))
                else:
                    out += bytes((p[0], p[1], p[2]))
            rows.append(bytes(out))
        open(OUT, "wb").write(png(len(rows[0]) // 3, len(rows), rows))
        # numeric analysis: bbox of non-black pixels (full-res coords) + a few sampled colours
        minx, miny, maxx, maxy = w, h, -1, -1
        for y in range(0, h, 4):
            line = data[y * stride:y * stride + w * 4]
            for x in range(0, w, 4):
                p = line[x * 4:x * 4 + 4]
                if p[0] or p[1] or p[2]:
                    minx, maxx = min(minx, x), max(maxx, x)
                    miny, maxy = min(miny, y), max(maxy, y)

        def px(x, y):
            p = data[y * stride + x * 4:y * stride + x * 4 + 4]
            return tuple(p[:3][::-1]) if order == "BGRA" else tuple(p[:3])
        print("non-black bbox x:%d-%d y:%d-%d" % (minx, maxx, miny, maxy))
        print("samples TL=%s center=%s BR=%s" % (px(8, 8), px(w // 2, h // 2), px(w - 8, h - 8)))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
        print("saved", OUT, n, "bytes")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("0.0.0.0", 8801), H).serve_forever()
