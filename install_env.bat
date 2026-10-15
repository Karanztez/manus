@echo off
title ManusTrade Environment Installer (Python + Node.js)
color 0B

echo ========================================================
echo   ManusTrade Auto Environment Installer for Windows VPS
echo ========================================================
echo.

:: ตรวจสอบสิทธิ์ Administrator
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Requesting Administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

:: 1. ติดตั้ง Python 3.12 แบบ Silent + Add to PATH
echo [1/2] Installing Python 3.12 (Silently with PATH)...
set "PY_URL=https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
set "PY_FILE=%TEMP%\python_setup.exe"

powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('%PY_URL%', '%PY_FILE%')"
if exist "%PY_FILE%" (
    echo Downloading finished. Installing Python...
    "%PY_FILE%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
    del "%PY_FILE%" >nul 2>&1
    echo [OK] Python 3.12 installed successfully!
) else (
    echo [ERROR] Failed to download Python installer.
)

:: 2. ติดตั้ง Node.js v20 แบบ Silent
echo.
echo [2/2] Installing Node.js v20 (Silently)...
set "NODE_URL=https://nodejs.org/dist/v20.18.0/node-v20.18.0-x64.msi"
set "NODE_FILE=%TEMP%\nodejs_setup.msi"

powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('%NODE_URL%', '%NODE_FILE%')"
if exist "%NODE_FILE%" (
    echo Downloading finished. Installing Node.js...
    msiexec.exe /i "%NODE_FILE%" /quiet /norestart
    del "%NODE_FILE%" >nul 2>&1
    echo [OK] Node.js installed successfully!
) else (
    echo [ERROR] Failed to download Node.js installer.
)

echo.
echo ========================================================
echo [COMPLETED] Environment setup is done!
echo You can now close this window and double click: start_windows.bat
echo ========================================================
echo.
pause
