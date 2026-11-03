#!/bin/sh
# Zero-Bloat TV Browser Startup Script for Aceconn Pi+ 4K STB
# HiSilicon Hi3798MV300 (bigfish) / ARM Mali-450 / 1080p60

# 1. Performance: bump CPU governor to maximum (1.6 GHz)
echo performance > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null

# 2. Display: force progressive 1080p60 on disp1 (HDMI)
echo "fmt 1080p60" > /proc/msp/disp1 2>/dev/null

# 3. Clean screen: hide stock OSD layer (hifb1) and zero framebuffer
echo "hide" > /proc/msp/hifb1 2>/dev/null
dd if=/dev/zero of=/dev/fb1 bs=65536 count=127 2>/dev/null

# 4. Stop legacy bloat daemons & kill old browser processes
killall -9 tv_daemon.py 2>/dev/null
ps -ef | grep "/data/tv-hub" | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null
killall -9 keyd.py 2>/dev/null
killall -9 netflix bin 2>/dev/null

# 5. Ensure system clock is at least 2026 before browser boots (prevents SSL notBefore failures)
if [ "$(date +%Y)" -lt 2026 ]; then
    date -s "2026-11-03 00:00:00" >/dev/null 2>&1
fi

# 6. Network configuration & time sync
ifconfig wlan0 192.168.2.35 netmask 255.255.255.0 up 2>/dev/null
route add default gw 192.168.2.1 2>/dev/null
cat << 'EOF' > /etc/resolv.conf
nameserver 192.168.2.1
nameserver 8.8.8.8
nameserver 1.1.1.1
EOF
/usr/sbin/ntpdate -u time.google.com >/dev/null 2>&1 &

# 7. Start zero-CPU IR remote helper for BACK key navigation
nohup python /data/tv/keyd.py >/tmp/keyd.log 2>&1 &

# 8. Background watchdog: keep hifb1 hidden and Wi-Fi alive
(
    while true; do
        echo "hide" > /proc/msp/hifb1 2>/dev/null
        if ! ifconfig wlan0 2>/dev/null | grep -q "192.168.2.35"; then
            ifconfig wlan0 192.168.2.35 netmask 255.255.255.0 up 2>/dev/null
        fi
        if ! ip route 2>/dev/null | grep -q "default"; then
            route add default gw 192.168.2.1 2>/dev/null
        fi
        sleep 5
    done
) >/dev/null 2>&1 &

# 9. Browser runtime preparation
/usr/share/netflix/prepare.sh 2>/dev/null
export LD_LIBRARY_PATH=/usr/share/netflix/lib/hisi3798mv200/:/usr/share/netflix/lib/hisi3798mv200/nss:/usr/share/netflix/

# 10. Chromium supervisor loop (restarts cleanly to launcher on exit)
(
    while true; do
        echo "hide" > /proc/msp/hifb1 2>/dev/null
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
            "file:///data/tv/www/index.html" >/tmp/tv_chromium.log 2>&1
        sleep 1
    done
) >/dev/null 2>&1 &
