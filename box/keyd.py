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

## Remote Keys:
# 1 (ESC), 14 (BACKSPACE), 158 (KEY_BACK), 175 (KEY_XFER)
BACK_KEYS = {1, 14, 158, 175}
# Direct Home / Exit Keys: 102 (KEY_HOME), 139 (KEY_MENU), 174 (KEY_EXIT), 398 (RED)
HOME_KEYS = {102, 139, 174, 398}
DEV = "/dev/input/event0"
EVSZ = struct.calcsize("llHHi")

MOVY_CSS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "movy_tv.css")
MOVY_CSS = ""
if os.path.exists(MOVY_CSS_FILE):
    try:
        with open(MOVY_CSS_FILE, "r", encoding="utf-8") as f:
            MOVY_CSS = f.read()
    except Exception:
        pass

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

  // 3. Screen dimensions & high quality video decoding capabilities
  try {
    Object.defineProperty(screen, 'width', { get: () => 1920 });
    Object.defineProperty(screen, 'height', { get: () => 1080 });
    Object.defineProperty(screen, 'availWidth', { get: () => 1920 });
    Object.defineProperty(screen, 'availHeight', { get: () => 1080 });
    Object.defineProperty(window, 'devicePixelRatio', { get: () => 1.0 });
  } catch(e) {}

  try {
    if (navigator.mediaCapabilities && navigator.mediaCapabilities.decodingInfo) {
      navigator.mediaCapabilities.decodingInfo = async function() {
        return { supported: true, smooth: true, powerEfficient: true };
      };
    }
  } catch(e) {}

  // 4. Inject Global TV Styles (Focus Outlines, SVG logo fix, Hide Banner Ads)
  function injectStyles() {
    if (document.getElementById('tv-booster-css')) return;
    // NEVER inject focus outlines on the local CleanYourTV launcher
    if (location.protocol === 'file:') return;

    const parent = document.head || document.documentElement || document.body;
    if (!parent) return;
    const style = document.createElement('style');
    style.id = 'tv-booster-css';
    style.textContent = `
      :focus, a:focus, button:focus, [tabindex]:focus, [role="button"]:focus {
        outline: 3px solid rgba(255, 255, 255, 0.8) !important;
        outline-offset: 2px !important;
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
      /* Comprehensive uBlock-style Ad Removal */\n      ytlr-thumbnail-details[bg*="googlesyndication"],
      ytlr-banner-renderer,
      .ytp-ad-overlay-container,
      .video-ads,
      .ad-showing .ytp-ad-text,
      .ad-interrupting,
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

  // 5. uBlock-Style In-Flight Player Ad Stripping (Intercept JSON & initial player state)
  try {
    const originalParse = JSON.parse;
    JSON.parse = function() {
      const data = originalParse.apply(this, arguments);
      if (data && typeof data === 'object') {
        if (data.adPlacements) data.adPlacements = [];
        if (data.playerAds) data.playerAds = [];
        if (data.adSlots) data.adSlots = [];
        if (data.adBreakParams) delete data.adBreakParams;
      }
      return data;
    };
  } catch(e) {}

  try {
    let initialResponse = window.ytInitialPlayerResponse;
    Object.defineProperty(window, 'ytInitialPlayerResponse', {
      get: function() { return initialResponse; },
      set: function(val) {
        if (val && typeof val === 'object') {
          if (val.adPlacements) val.adPlacements = [];
          if (val.playerAds) val.playerAds = [];
          if (val.adSlots) val.adSlots = [];
        }
        initialResponse = val;
      },
      configurable: true
    });
  } catch(e) {}

  // 6. Network Fetch Interception for YouTube & streaming player endpoints
  try {
    const origFetch = window.fetch;
    if (origFetch) {
      window.fetch = async function(...args) {
        const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
        if (url.includes('/api/stats/ads') || url.includes('/pagead/') || url.includes('doubleclick.net')) {
          return new Response(JSON.stringify({}), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
        const response = await origFetch.apply(this, args);
        if (url.includes('/youtubei/v1/player')) {
          try {
            const clone = response.clone();
            const data = await clone.json();
            if (data && typeof data === 'object') {
              if (data.adPlacements) data.adPlacements = [];
              if (data.playerAds) data.playerAds = [];
              if (data.adSlots) data.adSlots = [];
              return new Response(JSON.stringify(data), {
                status: response.status,
                statusText: response.statusText,
                headers: response.headers
              });
            }
          } catch(e) {}
        }
        return response;
      };
    }
  } catch(e) {}

  // 7. Remote OK / Enter key handler:
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

  // 8. Remote Media Controls for Video Playback (Cinejoy / Web Video)
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

  // 9. Cinejoy Helpers
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

  // 10. YouTube TV Helpers (HD Thumbnails & Instant Ad Skipper)
  function handleYouTube() {
    if (!location.hostname.includes('youtube.com')) return;
    document.querySelectorAll('ytlr-thumbnail-details').forEach(el => {
      const bg = el.style.backgroundImage || getComputedStyle(el).backgroundImage;
      if (bg && bg.includes('hqdefault.jpg?sqp=')) {
        el.style.backgroundImage = bg.replace(/hqdefault\\.jpg\\?sqp=[^"\\)]+/, 'hq720.jpg');
      }
    });
    const video = document.querySelector('video');
    const ad = document.querySelector('.ad-showing, .ad-interrupting, .video-ads, .ytp-ad-player-overlay');
    if (video && ad) {
      video.muted = true;
      video.playbackRate = 16.0;
      if (isFinite(video.duration) && video.duration > 0) {
        video.currentTime = video.duration;
      }
    }
    const skip = document.querySelector('.ytp-ad-skip-button, .ytp-ad-skip-button-modern, .ytp-skip-ad-button, .videoAdUiSkipButton');
    if (skip) skip.click();
  }

  // 11. Movy.sx TV Helpers
  function handleMovy() {
    if (!location.hostname.includes('movy.sx')) return;

    // A. Initial scroll position clamp to prevent jumping past hero banner
    if (location.pathname === '/' && window.scrollY > 0 && !window.__userNavigated) {
      window.scrollTo(0, 0);
    }

    // B. Inject Complete TV Stylesheet (Tailwind CSS v4 compatibility + TV layout + focus rings + ad suppression)
    if (!document.getElementById('tv-movy-css')) {
      const parent = document.head || document.documentElement || document.body;
      if (parent) {
        const style = document.createElement('style');
        style.id = 'tv-movy-css';
        style.textContent = __MOVY_CSS__;
        parent.appendChild(style);
      }
    }

    // C. Auto-focus Play / Resume / Watch button on detail pages or hero banner on home
    const playBtn = Array.from(document.querySelectorAll('button, a, [role="button"]'))
      .find(el => {
        const t = (el.innerText || el.textContent || '').trim().toLowerCase();
        return t === 'play' || t.startsWith('play') || t === 'resume' || t.startsWith('resume') || t === 'watch';
      });

    if (playBtn && document.activeElement !== playBtn) {
      const active = document.activeElement;
      if (!active || active === document.body || active.tagName === 'HTML') {
        playBtn.focus();
        if (location.pathname !== '/') {
          playBtn.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }
      }
    }

    // D. Make all cards, posters, and nav items focusable via D-Pad spatial navigation
    document.querySelectorAll('.media-card, [class*="movieCard"], article, nav a, nav button').forEach(el => {
      const a = (el.tagName === 'A' || el.tagName === 'BUTTON') ? el : el.querySelector('a, button');
      if (a) {
        if (!a.hasAttribute('tabindex')) a.setAttribute('tabindex', '0');
        if (el !== a && el.hasAttribute('tabindex')) el.removeAttribute('tabindex');
      }
    });

    // E. Edge-to-edge video playback when active
    const v = document.querySelector('video');
    if (v && (v.currentTime > 0 || !v.paused)) {
      if (v.style.position !== 'fixed') {
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

  window.addEventListener('focusin', function(e) {
    window.__userNavigated = true;
    const el = e.target;
    if (!el) return;
    if (el.closest && (el.closest('.media-card') || el.closest('[class*="movieCard"]'))) {
      el.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
    }
  }, true);

  setInterval(handleYouTube, 50);
  setInterval(function() {
    injectStyles();
    handleCinejoy();
    handleMovy();
  }, 500);

})();"""

BOOSTER_JS = BOOSTER_JS.replace("__MOVY_CSS__", json.dumps(MOVY_CSS))

BACK_JS = """(function(){
  if (location.hostname.includes('movy.sx')) {
    if (location.pathname.includes('/watch') || location.pathname.includes('/play') || document.querySelector('video')) {
      if (window.history.length > 1) {
        window.history.back();
        return 'movy_back';
      }
    }
  }
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
  return 'go_home';
})()"""


def navigate_home(ws):
    """Browser-level navigation to file:/// launcher to bypass page-level file:// security blocking."""
    try:
        if ws:
            ws.call("Page.navigate", {"url": "file:///data/tv/www/index.html"})
        else:
            cdp.nav("file:///data/tv/www/index.html")
    except Exception:
        try:
            cdp.nav("file:///data/tv/www/index.html")
        except Exception:
            pass


def setup_devtools():
    try:
        ws = cdp.page_ws()
        ws.call("Page.enable")
        try:
            ws.call("Network.enable")
            ws.call("Network.setBlockedURLs", {
                "urls": [
                    "*doubleclick.net*",
                    "*googleads.g.doubleclick.net*",
                    "*pagead2.googlesyndication.com*",
                    "*youtube.com/api/stats/ads*",
                    "*youtube.com/pagead/*",
                    "*youtube.com/youtubei/v1/att/*",
                    "*adservice.google.*",
                    "*adnxs.com*",
                    "*popads.net*",
                    "*popcash.net*",
                    "*histats.com*",
                    "*adsterra.com*",
                    "*monetag.com*",
                    "*clickadu.com*",
                    "*propellerads.com*",
                ]
            })
        except Exception:
            pass
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
                        # Direct Home / Exit Key: return immediately to CleanYourTV launcher
                        if code in HOME_KEYS:
                            navigate_home(ws)
                        # Back Key: intelligent history / fullscreen / home return
                        elif code in BACK_KEYS:
                            try:
                                res = cdp.evaluate(BACK_JS)
                                if res == "go_home":
                                    navigate_home(ws)
                            except Exception:
                                navigate_home(ws)
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
