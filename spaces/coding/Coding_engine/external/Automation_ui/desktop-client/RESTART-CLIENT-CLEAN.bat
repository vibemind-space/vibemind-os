@echo off
REM ===============================================
REM   ROBUSTES DESKTOP-CLIENT RESTART SCRIPT
REM   Beendet alte Prozesse, löscht Cache, startet neu
REM ===============================================
setlocal enabledelayedexpansion

title Desktop Stream Client - Robuster Restart
cd /d "%~dp0"

echo.
echo ==================================================
echo   Desktop Stream Client - Sauberer Neustart
echo ==================================================
echo.

REM 1. Alle bestehenden Python-Prozesse mit dem Client beenden
echo [1/5] Beende laufende Client-Prozesse...
tasklist /FI "IMAGENAME eq python.exe" 2>nul | find /I "python.exe" >nul
if %errorLevel% equ 0 (
    REM Versuche alle Python-Prozesse zu finden die den Client ausführen
    for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" /NH 2^>nul ^| findstr /I "python"') do (
        echo       Beende PID: %%i
        taskkill /PID %%i /F >nul 2>&1
    )
    timeout /t 2 >nul
    echo       [OK] Prozesse beendet
) else (
    echo       [OK] Keine laufenden Prozesse gefunden
)

REM 2. Python Cache löschen
echo [2/5] Lösche Python-Cache...
if exist "__pycache__" (
    rd /s /q "__pycache__" >nul 2>&1
    echo       [OK] __pycache__ gelöscht
) else (
    echo       [OK] Kein Cache vorhanden
)
if exist "*.pyc" (
    del /f /q *.pyc >nul 2>&1
    echo       [OK] .pyc Dateien gelöscht
)

REM 3. Python prüfen
echo [3/5] Prüfe Python-Installation...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo       [FEHLER] Python nicht gefunden!
    echo.
    echo       Bitte installiere Python von https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do (
    echo       [OK] Python %%v gefunden
)

REM 4. Dependencies prüfen und installieren
echo [4/5] Prüfe Abhängigkeiten...
python -c "import websockets, PIL, pyautogui, screeninfo" >nul 2>&1
if %errorLevel% neq 0 (
    echo       [INFO] Installiere fehlende Pakete...
    pip install -q websockets pillow pyautogui screeninfo
    if %errorLevel% neq 0 (
        echo       [FEHLER] Paket-Installation fehlgeschlagen
        pause
        exit /b 1
    )
    echo       [OK] Pakete installiert
) else (
    echo       [OK] Alle Abhängigkeiten vorhanden
)

REM 5. Client mit optimierten Parametern starten
echo [5/5] Starte Desktop-Client...
echo.
echo ==================================================
echo   Client wird gestartet - Drücke Ctrl+C zum Stoppen
echo ==================================================
echo.
echo   Konfiguration:
echo   - FPS: 4 (reduziert für Stabilität)
echo   - Qualität: 75%% 
echo   - Schwarzbild-Toleranz: Aktiviert
echo   - Auto-Reconnect: Aktiviert
echo.

:start_loop
python dual_screen_capture_client.py --fps 4 --quality 75

REM Bei Absturz oder Beendigung: Neustart nach 5 Sekunden
echo.
echo [WARNUNG] Client beendet. Automatischer Neustart in 5 Sekunden...
echo           Drücke Ctrl+C zum endgültigen Beenden
echo.
timeout /t 5 >nul
goto start_loop