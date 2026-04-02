@echo off
cd /d "c:\Users\User\Desktop\Coding_engine\dashboard-app"
echo Starting Electron...
"node_modules\_electron\dist\electron.exe" . 2>&1
echo Exit code: %errorlevel%
pause
