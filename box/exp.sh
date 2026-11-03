#!/bin/sh
# Experiment runner (on the STB): relaunch the browser with extra flags, load a URL, report fps + raster status.
# usage: exp.sh "<extra flags>" <url> [settle_seconds]
FLAGS="$1"
URL="${2:-https://cinejoy.pk/}"
SETTLE="${3:-15}"

# stop supervisors + browser
for p in $(ps | grep -E 'user_script|start.sh|tvloop' | grep -v grep | awk '{print $1}'); do kill -9 $p 2>/dev/null; done
killall -9 netflix bin 2>/dev/null
sleep 1
echo "hide" > /proc/msp/hifb1 2>/dev/null
export LD_LIBRARY_PATH=/usr/share/netflix/lib/hisi3798mv200/:/usr/share/netflix/lib/hisi3798mv200/nss:/usr/share/netflix/
/usr/share/netflix/prepare.sh 2>/dev/null
nohup /usr/bin/netflix --no-sandbox --ozone-platform=egl --enable-spatial-navigation \
  --ignore-certificate-errors --autoplay-policy=no-user-gesture-required \
  --remote-debugging-port=9222 --content-shell-host-window-size=1920x1080 \
  $FLAGS "$URL" >/tmp/exp_chromium.log 2>&1 &
sleep "$SETTLE"
echo "flags: $FLAGS"
python /data/cdp.py gpu | grep -E '"rasterization"|"video_decode"|"oop_raster'
python /data/cdp.py info
python /data/cdp.py fps 5
top -b -n 1 | head -n 9 | tail -n 3
