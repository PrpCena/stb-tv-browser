#!/usr/bin/env python3
"""keyd.py - Zero-CPU TV Companion & Remote Control Daemon for Aceconn Pi+ STB.

Features:
1. Connects to Chromium DevTools Protocol (port 9222) and automatically registers
   the TV Booster preload script via Page.addScriptToEvaluateOnNewDocument:
   - Upgrades YouTube TV thumbnails from 320x180 (240p) to razor-sharp 1280x720 HD (hq720.jpg).
   - In-stream YouTube video ad-skipper (seeks instantly to end of ads and clicks skip).
   - Clamps Cinejoy blown-up SVG logo (which was 2,040px tall and covered the whole screen).
   - Adds bright blue (#38bdf8) focus outlines and smooth scroll-into-view for TV navigation.
   - Enter/OK key handling for custom buttons and <a> links across all modern web frameworks.
   - Edge-to-edge 1080p full-screen video player for Cinejoy.
   - D-pad video playback controls: OK toggles play/pause, Left/Right seeks 10s.
   - Disables debugger breakpoints so anti-devtools scripts never freeze the browser.
2. Zero-CPU IR Remote BACK key handler on /dev/input/event0:
   - Blocks in select() with 0.0% CPU when idle.
   - Backs out of full-screen video, YouTube sub-menus, or browser history.
   - Returns cleanly to the launcher (file:///data/tv/www/index.html).
"""
import json
import os
import select
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdp  # noqa: E402

# Remote Keys:
# 1 (ESC), 14 (BACKSPACE), 158 (KEY_BACK), 174 (KEY_EXIT), 175 (KEY_XFER)
BACK_KEYS = {1, 14, 158, 174, 175}
# Direct Home Keys: 102 (KEY_HOME), 139 (KEY_MENU), 398 (RED)
HOME_KEYS = {102, 139, 398}
DEV = "/dev/input/event0"
EVSZ = struct.calcsize("llHHi")

BOOSTER_JS = """(function() {
  if (window.__TV_BOOSTER_ACTIVE) return;
  window.__TV_BOOSTER_ACTIVE = true;

  // 1. Block popup spam / ad redirects
  try {
    window.open = function() { console.log('Blocked window.open'); return null; };
  } catch(e) {}

  // 2. Pre-seed adblock, preferences & Cinejoy 4K server priority
  try {
    localStorage.setItem('addies', 'false');
    localStorage.setItem('adblock', 'true');
    const existing = JSON.parse(localStorage.getItem('cinejoy_settings') || '{}');
    if (!existing.serverOrder || existing.serverOrder[0] !== 'Lisbon') {
      existing.serverOrder = ['Lisbon', 'secret', 'Nebula', 'Solara', 'Athens'];
      localStorage.setItem('cinejoy_settings', JSON.stringify(existing));
    }
  } catch(e) {}

  // 3. 4K Ultra HD screen dimensions & high-DPI emulation
  try {
    Object.defineProperty(screen, 'width', { get: () => 3840 });
    Object.defineProperty(screen, 'height', { get: () => 2160 });
    Object.defineProperty(screen, 'availWidth', { get: () => 3840 });
    Object.defineProperty(screen, 'availHeight', { get: () => 2160 });
    Object.defineProperty(window, 'devicePixelRatio', { get: () => 2.0 });
  } catch(e) {}

  // 4. Inject Global TV Styles (Focus Outlines, SVG logo fix, Hide Banner Ads)
  function injectStyles() {
    if (document.getElementById('tv-booster-css')) return;
    const parent = document.head || document.documentElement || document.body;
    if (!parent) return;
    const style = document.createElement('style');
    style.id = 'tv-booster-css';
    style.textContent = `
      :focus, a:focus, button:focus, [tabindex]:focus, [role="button"]:focus {
        outline: 4px solid #38bdf8 !important;
        outline-offset: 2px !important;
        box-shadow: 0 0 16px rgba(56, 189, 248, 0.9) !important;
      }
      .brand-mark, img[src*="logomark"], .logo-legible {
        max-height: 48px !important;
        max-width: 48px !important;
        height: 48px !important;
        width: auto !important;
      }
      .app-shell > div:first-child {
        max-height: 72px !important;
      }
      /* Comprehensive uBlock-style Ad Removal */
      ytlr-thumbnail-details[bg*="googlesyndication"],
      ytlr-banner-renderer,
      .ytp-ad-overlay-container,
      .video-ads,
      .ad-showing .ytp-ad-text,
      iframe[src*="doubleclick"],
      iframe[src*="ad"],
      iframe[src*="googleads"],
      [id*="google_ads"],
      [class*="ad-banner"],
      [class*="adsbygoogle"],
      [id*="banner-ad"],
      [class*="sponsored"],
      [id*="popcash"],
      [id*="popads"],
      .ad-container,
      .native-ad,
      #ad-banner {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        pointer-events: none !important;
        height: 0 !important;
        width: 0 !important;
      }
    `;
    parent.appendChild(style);
  }

  // 5. Remote OK / Enter key handler:
  window.addEventListener('keydown', function(e) {
    if (e.keyCode === 13 || e.key === 'Enter') {
      const el = document.activeElement;
      if (!el || el === document.body) return;
      if (el.tagName === 'A' && el.href) {
        e.preventDefault();
        window.location.href = el.href;
      } else if (typeof el.click === 'function') {
        el.click();
      }
    }
  }, true);

  // 6. Remote Media Controls for Video Playback (Cinejoy / Web Video)
  window.addEventListener('keydown', function(e) {
    const video = document.querySelector('video');
    if (!video) return;
    if (location.href.includes('/watch') || video.duration > 0) {
      if (e.keyCode === 37) { // Left arrow: seek backward 10s
        video.currentTime = Math.max(0, video.currentTime - 10);
        e.preventDefault();
      } else if (e.keyCode === 39) { // Right arrow: seek forward 10s
        video.currentTime = Math.min(video.duration || 99999, video.currentTime + 10);
        e.preventDefault();
      } else if ((e.keyCode === 13 || e.keyCode === 32) && (location.href.includes('/watch') || document.activeElement === video)) {
        if (video.paused) video.play(); else video.pause();
        e.preventDefault();
      }
    }
  }, true);

  // 7. Cinejoy Helpers
  function handleCinejoy() {
    if (!location.hostname.includes('cinejoy')) return;
    const logo = document.querySelector('.brand-mark, img[src*="logomark"]');
    if (logo && logo.offsetHeight > 60) {
      logo.style.setProperty('max-height', '48px', 'important');
      logo.style.setProperty('height', '48px', 'important');
      logo.style.setProperty('width', 'auto', 'important');
    }
    if (location.pathname.startsWith('/movie/')) {
      const playBtn = Array.from(document.querySelectorAll('button, a')).find(b => b.innerText && (b.innerText.trim().startsWith('Play') || b.innerText.trim().startsWith('Resume')));
      if (playBtn && document.activeElement !== playBtn) {
        playBtn.focus();
        playBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
    }
    if (location.pathname.startsWith('/watch/')) {
      const v = document.querySelector('video');
      if (v && v.style.position !== 'fixed') {
        v.style.position = 'fixed';
        v.style.top = '0';
        v.style.left = '0';
        v.style.width = '100vw';
        v.style.height = '100vh';
        v.style.zIndex = '999999';
        v.style.background = '#000';
        v.style.objectFit = 'contain';
      }
    }
  }

  // 8. YouTube TV Helpers (HD Thumbnails & Ad Skipper)
  function handleYouTube() {
    if (!location.hostname.includes('youtube.com')) return;
    document.querySelectorAll('ytlr-thumbnail-details').forEach(el => {
      const bg = el.style.backgroundImage || getComputedStyle(el).backgroundImage;
      if (bg && bg.includes('hqdefault.jpg?sqp=')) {
        el.style.backgroundImage = bg.replace(/hqdefault\.jpg\?sqp=[^"\)]+/, 'hq720.jpg');
      }
    });
    const video = document.querySelector('video');
    const ad = document.querySelector('.ad-showing, .ad-interrupting, .video-ads');
    if (video && ad) {
      if (isFinite(video.duration) && video.duration > 0) {
        video.currentTime = video.duration;
      }
    }
    const skip = document.querySelector('.ytp-ad-skip-button, .ytp-ad-skip-button-modern, .ytp-skip-ad-button');
    if (skip) skip.click();
  }

  setInterval(function() {
    injectStyles();
    handleCinejoy();
    handleYouTube();
  }, 500);

})();"""

BACK_JS = """(function(){
  if (location.hostname.includes('cinejoy') && location.pathname.startsWith('/watch/')) {
    if (window.history.length > 1) { window.history.back(); return 'cinejoy_back'; }
    window.location.href = 'https://cinejoy.pk/';
    return 'cinejoy_home';
  }
  if (document.fullscreenElement) {
    document.exitFullscreen();
    return 'exit_fs';
  }
  if (location.protocol === 'file:') {
    return 'at_home';
  }
  if (location.hostname.includes('youtube.com') && location.hash && location.hash !== '#/') {
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


def setup_devtools():
    try:
        ws = cdp.page_ws()
        ws.call("Page.enable")
        ws.call("Debugger.enable")
        ws.call("Debugger.setBreakpointsActive", {"active": False})
        ws.call("Page.addScriptToEvaluateOnNewDocument", {"source": BOOSTER_JS})
        # Evaluate immediately on whatever page is currently loaded
        ws.call("Runtime.evaluate", {"expression": BOOSTER_JS})
        return ws
    except Exception as e:
        sys.stderr.write("DevTools setup error: %s\n" % e)
        return None


def main():
    # Wait for Chromium DevTools port 9222 to be available
    ws = None
    for _ in range(30):
        try:
            ws = setup_devtools()
            if ws:
                break
        except Exception:
            pass
        time.sleep(1)

    ev_fd = None
    while True:
        if ev_fd is None:
            try:
                ev_fd = os.open(DEV, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                time.sleep(2)
                continue

        rlist = [ev_fd]
        if ws and ws.s:
            rlist.append(ws.s)

        try:
            readable, _, _ = select.select(rlist, [], [], 2.0)
        except (OSError, select.error):
            time.sleep(1)
            continue

        if ws and ws.s in readable:
            try:
                # Read frame to keep connection buffer clear
                ws._read_frame()
            except Exception:
                try:
                    ws.close()
                except Exception:
                    pass
                ws = None

        if ev_fd in readable:
            try:
                buf = os.read(ev_fd, EVSZ)
                if len(buf) >= EVSZ:
                    _, _, etype, code, val = struct.unpack("llHHi", buf)
                    if etype == 1 and val == 1:
                        # Direct Home Key: return immediately to CleanYourTV launcher
                        if code in HOME_KEYS:
                            try:
                                cdp.evaluate("window.location.href = 'file:///data/tv/www/index.html';")
                            except Exception:
                                pass
                        # Back / Exit Key: intelligent history / fullscreen / home return
                        elif code in BACK_KEYS:
                            try:
                                cdp.evaluate(BACK_JS)
                            except Exception:
                                pass
            except OSError:
                try:
                    os.close(ev_fd)
                except Exception:
                    pass
                ev_fd = None
                time.sleep(1)

        # Periodic check to re-establish DevTools if lost
        if ws is None:
            ws = setup_devtools()


if __name__ == "__main__":
    main()
