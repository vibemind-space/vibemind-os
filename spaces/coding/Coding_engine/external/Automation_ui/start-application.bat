@echo off
REM TRAE Unity AI Platform - Quick Start Batch File
REM This batch file provides easy startup options for the application

echo.
echo ========================================
echo  TRAE Unity AI Platform - Quick Start
echo ========================================
echo.

echo Choose startup option:
echo.
echo 1. Start with logs (recommended for development)
echo 2. Start in background (recommended for production)
echo 3. Start without desktop capture (frontend + websocket only)
echo 4. Exit
echo.

set /p choice="Enter your choice (1-4): "

if "%choice%"=="1" (
    echo.
    echo Starting with logs...
    powershell -ExecutionPolicy Bypass -File "%~dp0scripts\start-application.ps1" -ShowLogs
) else if "%choice%"=="2" (
    echo.
    echo Starting in background...
    powershell -ExecutionPolicy Bypass -File "%~dp0scripts\start-application.ps1"
) else if "%choice%"=="3" (
    echo.
    echo Starting without desktop capture...
    powershell -ExecutionPolicy Bypass -File "%~dp0scripts\start-application.ps1" -SkipDesktopClient
) else if "%choice%"=="4" (
    echo.
    echo Exiting...
    exit /b 0
) else (
    echo.
    echo Invalid choice. Please run the script again.
    pause
    exit /b 1
)

echo.
pause