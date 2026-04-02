@echo off
REM One-Click Desktop Client Setup
REM This batch file runs the permission setup script with administrator privileges

echo.
echo ========================================
echo   Desktop Client Setup
echo ========================================
echo.
echo This will:
echo   - Enable screen capture permissions
echo   - Configure power settings
echo   - Set up auto-start on login
echo   - Test screen capture
echo.
echo IMPORTANT: This requires Administrator privileges
echo.
pause

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo.
    echo [OK] Running as Administrator
    echo.
    powershell -ExecutionPolicy Bypass -File "%~dp0setup-permissions.ps1"
) else (
    echo.
    echo [ERROR] Not running as Administrator
    echo.
    echo Please right-click this file and select "Run as administrator"
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
pause
