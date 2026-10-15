@echo off
title ManusTrade One-Click Starter
color 0A

echo ========================================================
echo       ManusTrade Automated Launcher for Windows VPS
echo ========================================================
echo.

cd /d "%~dp0"

:: 1. ตรวจสอบ config.ini
if not exist config.ini (
    echo [WARN] config.ini not found! Creating from config.example.ini...
    copy config.example.ini config.ini
    echo [INFO] Please edit config.ini with your Gemini and MT5 credentials.
    notepad config.ini
)

:: 2. ตรวจสอบ Python dependencies
echo [1/3] Checking and installing Python dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Python installation failed. Make sure Python is installed and added to PATH.
    pause
    exit /b %errorlevel%
)

:: 3. ตรวจสอบ Node.js dependencies และ Build
echo.
echo [2/3] Checking Node.js dependencies and building dashboard...
cd web
call npm install
call npm run build
cd ..

:: 4. เปิดรันทั้งสองฝั่งในหน้าต่างแยก
echo.
echo [3/3] Starting ManusTrade services...
echo Starting Python MT5 Gateway...
start "ManusTrade Python Gateway" cmd /k "python -m src.web_gateway"

timeout /t 3 >nul

echo Starting Web Dashboard on Port 3000...
start "ManusTrade Web Dashboard" cmd /k "cd web && npm run start"

echo.
echo ========================================================
echo [OK] All services launched!
echo Open your browser at: http://localhost:3000
echo ========================================================
echo.
pause
