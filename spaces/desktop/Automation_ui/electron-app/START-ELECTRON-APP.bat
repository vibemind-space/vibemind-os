@echo off
echo ====================================
echo   Desktop Streaming Electron App
echo ====================================
echo.

cd /d "%~dp0"

REM Prüfe ob Node installiert ist
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo FEHLER: Node.js ist nicht installiert!
    echo Bitte installiere Node.js von https://nodejs.org/
    pause
    exit /b 1
)

REM Prüfe ob npm installiert ist
where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo FEHLER: npm ist nicht installiert!
    pause
    exit /b 1
)

REM Prüfe ob node_modules existiert
if not exist "node_modules" (
    echo Installiere Dependencies...
    call npm install
    if %errorlevel% neq 0 (
        echo FEHLER: npm install fehlgeschlagen!
        pause
        exit /b 1
    )
    echo.
)

echo Starte Electron App...
echo.
call npm start

pause