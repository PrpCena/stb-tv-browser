#!/usr/bin/env python3
"""Box side: POST the raw framebuffer (/dev/fb0) to the Mac receiver (tools/fbrecv.py).
usage: fbshot.py [mac_ip] [fbdev]
"""
import sys
import urllib.request

mac = sys.argv[1] if len(sys.argv) > 1 else "192.168.2.50"
dev = sys.argv[2] if len(sys.argv) > 2 else "/dev/fb0"
page = int(sys.argv[3]) if len(sys.argv) > 3 else 0
W, H = 1920, 1080
f = open(dev, "rb")
f.seek(page * W * 4 * H)
data = f.read(W * 4 * H)
req = urllib.request.Request("http://%s:8801/" % mac, data=data, method="POST",
                             headers={"X-W": str(W), "X-H": str(H), "X-Stride": str(W * 4)})
print(urllib.request.urlopen(req, timeout=30).read())
