#!/usr/bin/env python3
"""keyd.py - zero-CPU remote control helper for Aceconn Pi+ STB.

Chromium 92 handles D-pad arrow navigation (--enable-spatial-navigation) and OK/Enter.
The remote's BACK key is captured here via /dev/input/event0 (blocking read, 0% CPU):
  - If in fullscreen, exit fullscreen.
  - If on YouTube TV sub-menu/video, send Escape to back out of menu.
  - If browser has history, history.back().
  - Otherwise, return to the launcher (file:///data/tv/www/index.html).

Keycodes handled:
  1 (ESC), 14 (BACKSPACE), 158 (KEY_BACK), 175
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdp  # noqa: E402

BACK_KEYS = {1, 14, 158, 175}
DEV = "/dev/input/event0"
EVSZ = struct.calcsize("llHHi")

JS = """(function(){
  if (document.fullscreenElement) {
    document.exitFullscreen();
    return 'exit_fs';
  }
  if (location.protocol === 'file:') {
    return 'at_home';
  }
  if (location.hostname.indexOf('youtube.com') !== -1 && location.hash && location.hash !== '#/') {
    var evt = new KeyboardEvent('keydown', {bubbles: true, cancelable: true, keyCode: 27, which: 27, key: 'Escape'});
    document.dispatchEvent(evt);
    return 'yt_esc';
  }
  if (window.history.length > 1) {
    window.history.back();
    return 'history_back';
  }
  window.location.href = 'file:///data/tv/www/index.html';
  return 'go_home';
})()"""


def main():
    while True:
        try:
            fd = os.open(DEV, os.O_RDONLY)
        except OSError:
            time.sleep(2)
            continue
        try:
            while True:
                buf = os.read(fd, EVSZ)
                if len(buf) < EVSZ:
                    continue
                _, _, etype, code, val = struct.unpack("llHHi", buf)
                if etype == 1 and val == 1 and code in BACK_KEYS:
                    try:
                        cdp.evaluate(JS)
                    except Exception:
                        pass
        except OSError:
            time.sleep(1)
        finally:
            os.close(fd)


if __name__ == "__main__":
    main()
