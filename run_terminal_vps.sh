#!/bin/bash
# Start MT5 Terminal on Debian Headless with Account Credentials
export WINEARCH=win64
export WINEPREFIX="/root/.wine"
export DISPLAY=:99
export WINEDEBUG=-all

# Ensure virtual display
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 || true
Xvfb :99 -screen 0 1024x768x16 &
sleep 2

MT5_DIR="/root/.wine/drive_c/Program Files/MetaTrader 5"
cd "$MT5_DIR"

echo "[STARTUP] Launching MT5 Terminal with login 108074548 on XMGlobal-MT5 5..."
wine terminal64.exe /login:108074548 "/password:9200Eazer." "/server:XMGlobal-MT5 5" &

echo "[OK] MT5 Terminal running in background under Wine."
