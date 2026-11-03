#!/usr/bin/env python3
"""Run a shell command on the Aceconn Pi+ STB over telnet and print the output.

Usage:
    stb.py 'ps | head'                # runs on 192.168.2.35
    STB_HOST=fe80::...%en0 stb.py ... # override host (IPv6 link-local also works)
    stb.py -t 30 'long command'       # custom timeout (seconds)
    stb.py -f script.sh               # run a local script file on the box (via stdin heredoc-free upload)

Telnet login is root/root. Output ends when a unique end-marker is seen.
"""
import os
import socket
import sys
import time
import uuid

HOST = os.environ.get("STB_HOST", "192.168.2.35")
USER = os.environ.get("STB_USER", "root")
PASS = os.environ.get("STB_PASS", "root")


def _read_until(sock, marker, timeout):
    buf = b""
    end = time.time() + timeout
    sock.settimeout(0.3)
    while time.time() < end:
        try:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
            if marker in buf:
                break
        except socket.timeout:
            pass
    return buf


def run(cmd, timeout=15.0):
    fam = socket.AF_INET6 if ":" in HOST else socket.AF_INET
    addr = socket.getaddrinfo(HOST, 23, fam, socket.SOCK_STREAM)[0][4]
    s = socket.socket(fam, socket.SOCK_STREAM)
    s.settimeout(6)
    s.connect(addr)
    _read_until(s, b"login:", 6)
    s.sendall(USER.encode() + b"\r\n")
    _read_until(s, b"assword:", 6)
    s.sendall(PASS.encode() + b"\r\n")
    _read_until(s, b"# ", 6)
    mark = "__END_%s__" % uuid.uuid4().hex[:8]
    # Split the marker so the echoed command line doesn't match it.
    wrapped = "%s\r\necho __E''ND_%s__\r\n" % (cmd, mark[6:-2])
    s.sendall(wrapped.encode())
    want = ("__END_%s__" % mark[6:-2]).encode()
    out = _read_until(s, want, timeout)
    s.close()
    text = out.decode("utf-8", errors="replace").replace("\r", "")
    # Drop echoed command lines and the marker line.
    lines = [l for l in text.split("\n") if want.decode() not in l and "__E''ND_" not in l]
    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    timeout = 15.0
    if args and args[0] == "-t":
        timeout = float(args[1])
        args = args[2:]
    if args and args[0] == "-f":
        cmd = open(args[1]).read()
    else:
        cmd = " ".join(args)
    print(run(cmd, timeout))


if __name__ == "__main__":
    main()
