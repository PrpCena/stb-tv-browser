# Aceconn Pi+ 4K STB - Zero-Bloat TV Web Browser

Turn the **Aceconn $\pi+$ (Pi+) 4K Set-Top Box** into a smooth, responsive, zero-bloat web browsing device for your TV.

No virtual mouse cursors. No sluggish HUD button overlays. No background CPU-hogging polling daemons. Native 1080p60 display output with 57–60 FPS streaming on YouTube TV and native D-pad spatial navigation on websites.

---

## 1. Hardware & System Architecture

- **Hardware:** Aceconn $\pi+$ (Pi+) 4K STB
- **SoC:** HiSilicon Hi3798MV300 ("bigfish")
- **CPU:** Quad-Core ARM Cortex-A53 @ 1.6 GHz
- **GPU:** ARM Mali-450 MP (OpenGL ES 2.0 / EGL)
- **RAM:** 1 GB DDR3
- **OS:** Embedded Linux 4.4.35_hi3798mv300 (DefineOS / OpenATV foundation)
- **Browser:** Chromium 92.0.4515.162 with Ozone EGL backend (`/usr/share/netflix/bin`)
- **Remote Control:** IR Remote emitting on `/dev/input/event0` (KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_ENTER, KEY_BACK / 158)

---

## 2. Key Discoveries & Root Causes

### Why Previous Setups Were Glitchy & Slow
1. **CPU Exhaustion by Polling Overlays:** Previous streaming dashboard daemons periodically re-injected complex cursor DOM elements and red/yellow/blue/green button HUDs over CDP every 2.5 seconds. This threw `TrustedHTML` violations on modern sites, pegged CPU usage near 100%, and throttled YouTube TV down to ~14 FPS.
2. **Interlaced Video Mode:** The default display output was configured for `1080i50` (50Hz interlaced). Writing `fmt 1080p60` to `/proc/msp/disp1` switched output to clean progressive 60Hz.
3. **Dual Framebuffer Layers:** HiSilicon has two hardware framebuffer layers:
   - `hifb0` (`/dev/fb0`): Graphic layer used by Chromium's Ozone EGL.
   - `hifb1` (`/dev/fb1`): OSD layer used by the stock STB firmware (`bianbiang`). Hiding `hifb1` (`echo "hide" > /proc/msp/hifb1`) ensures stock TV menus never flash over the browser.
4. **Window Resolution:** Duplicate flags like `--content-shell-host-window-size=1280x720` restricted Chromium to a 720p box. Running `--content-shell-host-window-size=1920x1080` provides razor-sharp 1080p rendering.
5. **GPU Acceleration vs Software Raster:** Mali-450 on Linux 4.4 has full hardware acceleration for EGL, 2D Canvas, WebGL, and Skia compositor. However, GPU rasterization (`--enable-gpu-rasterization`) overloads Mali-450 tile memory on heavy DOMs; software rasterization with reduced motion (`--force-prefers-reduced-motion`) runs significantly faster and avoids crashes.

---

## 3. Remote Control Navigation Solution

Instead of clunky virtual mouse cursors that require frustrating D-pad steering:
- **Native Spatial Navigation:** Chromium runs with `--enable-spatial-navigation`. The browser natively finds the nearest link, button, or input in the direction of the arrow keys and highlights it.
- **High-Contrast Focus Outlines:** High-visibility `:focus` borders ensure you always see which element is active on the TV screen.
- **Zero-CPU BACK Key Helper (`keyd.py`):** 
  - Blocks on `read()` of `/dev/input/event0` (0% CPU while idle, no polling).
  - Handles BACK keycodes `158` (KEY_BACK), `1` (ESC), `14` (Backspace).
  - If a video is playing in fullscreen: exits fullscreen.
  - If on YouTube TV sub-menu: dispatches Escape to back out one level.
  - If browser has history: triggers `history.back()`.
  - If no history: returns to the local launcher (`file:///data/tv/www/index.html`).

---

## 4. Repository Structure

```
├── box/
│   ├── start.sh          # Lean STB startup supervisor (CPU, display, watchdog, browser)
│   ├── keyd.py           # Zero-CPU IR remote event listener for BACK key
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
From the development machine:
```bash
python3 tools/stb.py "mkdir -p /data/tv/www"
# Transfer files via local HTTP or stb.py
```

### Step 2: Configure System Boot Hook
The STB's stock firmware executes `/home/gx/local/user_script` at boot time via `/usr/bin/bianbiang.sh`:
```bash
cat << 'EOF' > /home/gx/local/user_script
#!/bin/sh
if [ -x /data/tv/start.sh ]; then
    exec /data/tv/start.sh
fi
EOF
chmod +x /home/gx/local/user_script
```

### Step 3: Block Annoying Ad Redirectors
Add known redirect/ad domains to `/etc/hosts`:
```bash
0.0.0.0 chiangness.com
0.0.0.0 www.chiangness.com
0.0.0.0 llvpn.com
0.0.0.0 a.wing.st
0.0.0.0 plausible.io
```

---

## 6. Chromium Production Flags

The browser is started with:
```bash
/usr/bin/netflix \
    --no-sandbox \
    --ozone-platform=egl \
    --enable-spatial-navigation \
    --ignore-certificate-errors \
    --autoplay-policy=no-user-gesture-required \
    --remote-debugging-port=9222 \
    --content-shell-host-window-size=1920x1080 \
    --disable-smooth-scrolling \
    --force-prefers-reduced-motion \
    --user-agent="Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/4.0 Chrome/76.0.3809.146 TV Safari/537.36" \
    "file:///data/tv/www/index.html"
```

---

## 7. Performance Benchmarks

| Configuration | YouTube TV FPS | Cinejoy DOM Ready | CPU Load at Rest |
|---|---|---|---|
| **Old Setup (with daemon & cursor)** | 14.4 FPS | Stalled / 100% CPU | ~98% (overloaded) |
| **New Setup (Zero-Bloat)** | **57.6 - 60.3 FPS** | Fast & Responsive | **7.0% (93% idle)** |
