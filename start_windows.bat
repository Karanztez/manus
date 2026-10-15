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

:: 2. ค้นหา Python Executable
set "PYTHON_EXE=python"
python --version >nul 2>&1
if %errorlevel% neq 0 (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    if exist "C:\Python312\python.exe" set "PYTHON_EXE=C:\Python312\python.exe"
    if exist "C:\Python311\python.exe" set "PYTHON_EXE=C:\Python311\python.exe"
    if exist "C:\Python310\python.exe" set "PYTHON_EXE=C:\Python310\python.exe"
    if exist "C:\Program Files\Python312\python.exe" set "PYTHON_EXE=C:\Program Files\Python312\python.exe"
    if exist "C:\Program Files\Python311\python.exe" set "PYTHON_EXE=C:\Program Files\Python311\python.exe"
    if exist "C:\Program Files\Python310\python.exe" set "PYTHON_EXE=C:\Program Files\Python310\python.exe"
)

"%PYTHON_EXE%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found on this VPS!
    echo [INFO] Please install Python 3.10, 3.11, or 3.12 and tick 'Add python.exe to PATH'.
    echo [INFO] Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 3. ตรวจสอบ Python dependencies
echo [1/3] Checking and installing Python dependencies using "%PYTHON_EXE%"...
"%PYTHON_EXE%" -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Python dependencies installation failed.
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
start "ManusTrade Python Gateway" cmd /k ""%PYTHON_EXE%" -m src.web_gateway"

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
