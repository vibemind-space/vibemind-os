@echo off
REM Desktop Client Auto-Start Script
REM This script automatically starts the desktop client with configured parameters

cd /d "%~dp0"

REM Configuration - Edit these values as needed
set USER_ID=user_123
set FRIENDLY_NAME=Main Workstation

:start
REM Start the desktop client
echo Starting Desktop Client...
echo User ID: %USER_ID%
echo Friendly Name: %FRIENDLY_NAME%
echo.

python dual_screen_capture_client.py --user-id "%USER_ID%" --friendly-name "%FRIENDLY_NAME%"

REM If client exits, wait 5 seconds and restart
echo.
echo Desktop client stopped. Restarting in 5 seconds...
echo Press Ctrl+C to exit completely.
timeout /t 5
goto :start
