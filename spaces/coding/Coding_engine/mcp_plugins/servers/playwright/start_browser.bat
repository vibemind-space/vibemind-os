@echo off
REM Start Microsoft Edge with Remote Debugging enabled
REM This allows Playwright to connect to an existing browser session

set DEBUG_PORT=9222
set USER_DATA_DIR=%USERPROFILE%\.edge-debug-profile

echo Starting Microsoft Edge with remote debugging on port %DEBUG_PORT%...
echo Profile directory: %USER_DATA_DIR%
echo.
echo Browser will stay open. Playwright agents can connect to it.
echo Press Ctrl+C to close this window (browser stays open).
echo.

start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" ^
    --remote-debugging-port=%DEBUG_PORT% ^
    --user-data-dir="%USER_DATA_DIR%" ^
    --no-first-run ^
    --no-default-browser-check

echo Edge started. Connect Playwright with --cdp-address=localhost:%DEBUG_PORT%
pause
