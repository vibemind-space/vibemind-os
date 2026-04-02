@echo off
REM Start Desktop Capture Client Manually
REM Use this if you don't want auto-start or need to run it manually

echo.
echo ========================================
echo   Starting Desktop Capture Client
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Python not found!
    echo.
    echo Please install Python from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM Check if required packages are installed
echo Checking Python packages...
python -c "import mss, websocket, psutil" >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo [WARNING] Some Python packages are missing
    echo Installing required packages...
    echo.
    pip install -r "%~dp0requirements.txt"
    if %errorLevel% neq 0 (
        echo.
        echo [ERROR] Failed to install packages
        echo.
        pause
        exit /b 1
    )
)

echo.
echo [OK] Starting desktop client...
echo.
echo Press Ctrl+C to stop the client
echo.

REM Start the desktop client
cd /d "%~dp0"
python dual_screen_capture_client.py

echo.
echo Desktop client stopped.
pause
