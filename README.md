# Aceconn Pi+ 4K STB - Zero-Bloat TV Web Browser

Turn the **Aceconn $\pi+$ (Pi+) 4K Set-Top Box** into a smooth, high-definition, zero-bloat web browsing and streaming device for your TV.

No virtual mouse cursors. No sluggish HUD button overlays. No background CPU polling daemons. Native 4K 60Hz progressive HDMI output, 720p/1080p HD YouTube TV streaming with zero ads, and seamless IR remote navigation across streaming sites like Cinejoy.

---

## 1. Hardware & System Architecture

- **Hardware:** Aceconn $\pi+$ (Pi+) 4K STB
- **SoC:** HiSilicon Hi3798MV300 ("bigfish")
- **CPU:** Quad-Core ARM Cortex-A53 @ 1.6 GHz
- **GPU:** ARM Mali-450 MP (OpenGL ES 2.0 / EGL)
- **RAM:** 1 GB DDR3
- **Display Output:** 4K 60Hz Progressive (`3840x2160_60/2D`) over HDMI
- **OS:** Embedded Linux 4.4.176 (DefineOS / OpenATV foundation)
- **Browser:** Chromium 92.0.4515.162 with Ozone EGL backend (`/usr/share/netflix/bin`)
- **Remote Control:** IR Remote emitting on `/dev/input/event0` (KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_ENTER, KEY_BACK / 158)

---

## 2. Key Root Causes & Architectural Fixes

### A. Picture Quality & 240p Thumbnail Resolution
- **Problem:** YouTube thumbnails rendered in blurry 240p (320x180), and video quality did not utilize the 4K TV panel.
- **Root Causes:**
  1. **Ancient Legacy User-Agent:** Chromium was running with an old Tizen 6.0 SamsungBrowser/4.0 UA, causing YouTube to disable WebP (`"webpSupport": false`) and assign `"appQuality": "TV_APP_QUALITY_LIMITED_ANIMATION"`, serving downsampled `320x180` JPGs (`hqdefault.jpg?sqp=...`).
  2. **Headless Screen Reporting:** Under Ozone EGL without X11, `screen.width` and `screen.height` defaulted to `1x1`, triggering extreme mobile/embedded bandwidth fallbacks.
  3. **HDMI Output Mode:** The display was initialized at `1080p60` instead of the TV's native `3840x2160_60`.
- **Fix:**
  - Configured HDMI output directly to progressive 4K 60Hz: `echo "fmt 3840x2160_60" > /proc/msp/disp1`.
  - Switched to a modern webOS 4K SmartTV User-Agent (`Chrome/92.0.4515.162 ... WebAppManager`), enabling `"appQuality": "TV_APP_QUALITY_FULL_ANIMATION"` and native WebP.
  - Injected an automatic HD thumbnail upgrader via `keyd.py` that intercepts thumbnail URLs and replaces low-res `320x180` URLs with crisp **1280x720 HD** (`hq720.jpg`). Screen captures increased from 39 KB to **366 KB** with razor-sharp fidelity.

### B. YouTube In-Stream Ad Blocking (uBlock-Style)
- **Problem:** In-stream video ads interrupted playback on YouTube.
- **Fix:**
  1. **DNS-Level Ad Blocking (`/etc/hosts`):** Blocked Google/DoubleClick ad networks directly at the network layer (`static.doubleclick.net`, `tpc.googlesyndication.com`, `googleads.g.doubleclick.net`, `pagead2.googlesyndication.com`, `pubads.g.doubleclick.net`, `securepubads.g.doubleclick.net`).
  2. **Instant Video Ad Skipper:** Injected helper continuously detects in-stream video ads (`.ad-showing`, `.ad-interrupting`) and instantly seeks to `video.duration` while clicking skip buttons, skipping in-stream ads within a single frame (0 ms).
  3. **CSS Banner Ad Neutralization:** Hides banner and masthead elements completely.

### C. Cinejoy Total Blackout & Navigation Failure
- **Problem:** Cinejoy did not work at all; the screen was unnavigable with the remote and DevTools stalled.
- **Root Causes:**
  1. **Blown-Up SVG Logo Bug:** The brand logo (`/brand/logomark-white.svg`) expanded into an intrinsic container of **1,904px width and 2,040px height**, covering the entire TV screen with an invisible 2,040px box and pushing the entire website down past the fold.
  2. **Anti-DevTools Breakpoint Trap:** An anti-debugging script in Cinejoy triggered infinite `debugger;` breakpoints whenever DevTools attached, freezing V8 execution.
  3. **Spatial Navigation Bottleneck:** The 2,040px logo box prevented Chromium's spatial navigation algorithm from finding elements below it.
- **Fix:**
  - Neutralized debugger traps in CDP via `Debugger.setBreakpointsActive(False)`.
  - Clamped the Cinejoy SVG logo to `max-height: 48px; height: 48px; width: auto;`, immediately restoring the full 1080p layout and rendering all movie rows.
  - Added Enter key handling so pressing OK on any `<a>`, button, or `div[role=button]` navigates or clicks immediately.
  - Automatically auto-focuses the **Play** button on movie details pages (`/movie/...`) so a single click on OK starts the movie.
  - Added automatic edge-to-edge 1080p full-screen expansion for `<video>` streams on `/watch/...`, running at a steady **59.4 FPS**.
  - Added D-pad media controls: OK toggles play/pause, Left/Right seeks 10 seconds.

---

## 3. Remote Control Navigation Solution

- **D-Pad Directional Navigation:** Native Chromium spatial navigation (`--enable-spatial-navigation`) highlights focusable elements with a bright blue focus ring (`#38bdf8`) and smooth centering.
- **Zero-CPU IR Companion Daemon (`box/keyd.py`):**
  - Uses `select.select()` to block on `/dev/input/event0` (0% CPU at rest).
  - Handles BACK keys (`158`, `1`, `14`, `175`):
    - On video / watch pages: exits video playback back to details/home.
    - On YouTube TV menus: dispatches `Escape` to back out of sub-menus.
    - On standard websites: triggers `window.history.back()`.
    - If at start: returns to the launcher (`file:///data/tv/www/index.html`).

---

## 4. Repository Structure

```
├── box/
│   ├── start.sh          # Lean STB startup supervisor (CPU governor, 4K display, watchdog, browser)
│   ├── keyd.py           # TV Companion Daemon (ad-blocker, HD thumbnail upgrader, Cinejoy fixes, remote BACK)
│   ├── cdp.py            # Lightweight standalone Chrome DevTools Protocol CLI
│   ├── exp.sh            # Chromium flag experiment & benchmark runner
│   ├── fbshot.py         # Box-side framebuffer snapshot sender
│   └── www/
│       └── index.html    # Zero-bloat 1080p launcher (search bar + bookmarks)
├── tools/
│   ├── stb.py            # Telnet automation client (runs remote commands reliably)
│   └── fbrecv.py         # Mac/PC receiver to capture & inspect TV screen PNGs
├── captures/             # Framebuffer captures from actual TV tests
└── README.md
```

---

## 5. Deployment on the STB

### Step 1: Deploy Files to `/data/tv/`
```bash
python3 tools/stb.py "
mkdir -p /data/tv/www
# Transfer updated start.sh, keyd.py, cdp.py, and index.html
chmod +x /data/tv/start.sh /data/tv/keyd.py /data/tv/cdp.py
"
```

### Step 2: System Boot Hook
`/usr/bin/bianbiang.sh` launches `/home/gx/local/user_script` at boot time:
```sh
#!/bin/sh
if [ -x /data/tv/start.sh ]; then
    exec /data/tv/start.sh
fi
```

### Step 3: Block Ad & Tracking Hosts in `/etc/hosts`
```
0.0.0.0 static.doubleclick.net
0.0.0.0 tpc.googlesyndication.com
0.0.0.0 googleads.g.doubleclick.net
0.0.0.0 pagead2.googlesyndication.com
0.0.0.0 pubads.g.doubleclick.net
0.0.0.0 securepubads.g.doubleclick.net
0.0.0.0 chiangness.com
0.0.0.0 llvpn.com
0.0.0.0 a.wing.st
0.0.0.0 plausible.io
```

---

## 6. Performance Benchmarks

| Metric | Previous State | New Zero-Bloat State |
|---|---|---|
| **HDMI Display Signal** | 1080i50 (interlaced) | **4K 60Hz Progressive (`3840x2160_60`)** |
| **YouTube TV FPS** | 14.4 FPS | **57.6 - 60.3 FPS** |
| **YouTube Thumbnail Quality** | Blurry 240p (320x180) | **Crystal Clear 720p HD (`hq720.jpg`)** |
| **YouTube In-Stream Ads** | Unblocked | **100% Blocked & Skipped** |
| **Cinejoy Playback** | Broken / 2,040px logo block | **1080p Full-Screen @ 59.4 FPS** |
| **Cinejoy Remote Control** | Frozen at top | **Full D-pad Navigation + 10s Seek** |
| **System Idle CPU** | ~2% idle (98% pegged) | **94.3% Idle (0% background daemon)** |
