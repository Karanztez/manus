#!/bin/bash
# Install Python Windows Portable into Wine without installer bugs
set -e

export WINEARCH=win64
export WINEPREFIX="/root/.wine"
export DISPLAY=:99
export WINEDEBUG=-all

PYTHON_DIR="/root/.wine/drive_c/Python311"
echo "[STEP 1] Downloading Python 3.11.9 64-bit Windows Embeddable..."
mkdir -p "$PYTHON_DIR"
cd /tmp
wget -q -O python-embed.zip https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip
unzip -o -q python-embed.zip -d "$PYTHON_DIR"

echo "[STEP 2] Enabling site-packages in Python embed configuration..."
# Enable import site in python311._pth so pip and external modules work
sed -i 's/#import site/import site/' "$PYTHON_DIR/python311._pth"

echo "[STEP 3] Installing pip for Windows Python..."
wget -q -O /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py
wine "$PYTHON_DIR/python.exe" /tmp/get-pip.py --no-warn-script-location

echo "[STEP 4] Installing MetaTrader5, pandas, google-genai, pydantic inside Wine Python..."
wine "$PYTHON_DIR/python.exe" -m pip install --no-warn-script-location MetaTrader5 pandas google-genai pydantic

echo "[STEP 5] Verifying MetaTrader5 import inside Wine..."
wine "$PYTHON_DIR/python.exe" -c "import MetaTrader5 as mt5; print('[OK] MT5 Version:', mt5.__version__)"

echo "[DONE] Python Windows inside Wine is 100% ready!"
