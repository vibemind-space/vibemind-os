@echo off
REM Start Setup API Server (Must run as Administrator)

echo.
echo ========================================
echo   Desktop Client Setup API
echo ========================================
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Running as Administrator
) else (
    echo [WARNING] Not running as Administrator
    echo Some setup functions will be limited
)

echo.
echo Starting API server on http://localhost:3001
echo.
echo Press Ctrl+C to stop the server
echo.

cd /d "%~dp0"
node setup-api.js

pause
