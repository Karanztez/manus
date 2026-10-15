#!/bin/bash
# Setup MetaTrader 5 on Debian VPS via Wine
set -e

echo "[STEP 1] Preparing Wine 64-bit environment and Xvfb..."
export WINEARCH=win64
export WINEPREFIX="/root/.wine"
export DISPLAY=:99
export WINEDEBUG=-all

# Kill existing Xvfb lock if any
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 || true
Xvfb :99 -screen 0 1024x768x16 &
sleep 2

# Check or install Wine packages
dpkg --add-architecture i386 || true
apt-get update
apt-get install -y --no-install-recommends wine64 wine wine32:i386 xvfb wget curl ca-certificates

echo "[STEP 2] Initializing Wine prefix..."
wineboot --init || true
sleep 3

echo "[STEP 3] Downloading MetaTrader 5 Windows Installer..."
mkdir -p /root/mt5_installer
cd /root/mt5_installer
wget -O mt5setup.exe https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe

echo "[STEP 4] Installing MT5 Terminal silently..."
wine mt5setup.exe /auto
sleep 10

echo "[STEP 5] Checking MT5 installation directory..."
MT5_PATH="/root/.wine/drive_c/Program Files/MetaTrader 5"
if [ -d "$MT5_PATH" ]; then
    echo "[OK] MetaTrader 5 installed successfully at: $MT5_PATH"
else
    echo "[WARN] Searching for terminal64.exe in Wine drive_c..."
    find /root/.wine/drive_c -name "terminal64.exe"
fi

echo "[DONE] MT5 Setup complete."
