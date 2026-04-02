@echo off
chcp 65001 >nul
title TRAE Desktop Streaming Client

echo ============================================================
echo   TRAE Desktop Streaming Client - One-Click-Start
echo ============================================================
echo.

REM Stoppe alte Python-Prozesse die den Client blockieren könnten
echo [1/3] Stoppe alte Python-Prozesse...
taskkill /f /im python.exe >nul 2>&1
timeout /t 1 /nobreak >nul

REM Wechsle ins script-Verzeichnis
cd /d "%~dp0"

REM Prüfe ob Python verfügbar ist
echo [2/3] Prüfe Python-Installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python nicht gefunden! Bitte Python 3.11+ installieren.
    pause
    exit /b 1
)

echo [3/3] Starte Desktop Capture Client...
echo.
echo ========================================
echo   Client läuft - Fenster offen lassen!
echo   Zum Stoppen: Ctrl+C oder Fenster schließen
echo ========================================
echo.

REM Starte den robusten Client mit Auto-Start
python dual_screen_capture_client.py --fps 10 --quality 75 --scale 0.8

echo.
echo Client wurde beendet.
pause