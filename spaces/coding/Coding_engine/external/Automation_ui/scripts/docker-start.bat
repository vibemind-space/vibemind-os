@echo off
REM =============================================================================
REM TRAE Desktop Streaming - Docker Start Script
REM =============================================================================
REM Startet alle Docker-Container und den Desktop-Client auf dem Host
REM =============================================================================

setlocal EnableDelayedExpansion

echo.
echo ========================================
echo  TRAE Desktop Streaming - Docker Setup
echo ========================================
echo.

REM Prüfe ob Docker läuft
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker ist nicht gestartet!
    echo         Bitte starten Sie Docker Desktop und versuchen Sie es erneut.
    pause
    exit /b 1
)

echo [OK] Docker laeuft

REM Wechsle ins Projektverzeichnis
cd /d "%~dp0\.."

REM Prüfe ob .env existiert, sonst kopiere .env.example
if not exist ".env" (
    if exist "docker\.env.example" (
        echo [SETUP] Kopiere docker\.env.example nach .env
        copy "docker\.env.example" ".env" >nul
    ) else (
        echo [WARN] Keine .env Datei gefunden. Standard-Werte werden verwendet.
    )
)

REM Parse Optionen
set "BUILD=false"
set "DESKTOP_CLIENT=true"
set "DETACH=true"

:parse_args
if "%~1"=="" goto :end_parse
if /i "%~1"=="--build" set "BUILD=true"
if /i "%~1"=="-b" set "BUILD=true"
if /i "%~1"=="--no-desktop" set "DESKTOP_CLIENT=false"
if /i "%~1"=="--attach" set "DETACH=false"
if /i "%~1"=="-a" set "DETACH=false"
shift
goto :parse_args
:end_parse

REM Starte Docker Container
echo.
echo [DOCKER] Starte Container...
echo.

if "%BUILD%"=="true" (
    echo [DOCKER] Baue Images neu...
    docker-compose build --no-cache
)

if "%DETACH%"=="true" (
    docker-compose up -d
) else (
    start "Docker Logs" cmd /k "docker-compose up"
    timeout /t 5 >nul
)

REM Warte auf Backend-Health
echo.
echo [WAIT] Warte auf Backend-Bereitschaft...
set "RETRIES=30"
set "COUNTER=0"

:wait_backend
set /a COUNTER+=1
if %COUNTER% gtr %RETRIES% (
    echo [ERROR] Backend ist nach %RETRIES% Versuchen nicht bereit!
    echo         Pruefen Sie die Logs: docker-compose logs backend
    goto :desktop_client
)

curl -s -f http://localhost:8007/api/health >nul 2>&1
if %errorlevel% neq 0 (
    echo         Warte auf Backend... (%COUNTER%/%RETRIES%)
    timeout /t 2 >nul
    goto :wait_backend
)

echo [OK] Backend ist bereit!

:desktop_client
REM Starte Desktop-Client auf dem Host
if "%DESKTOP_CLIENT%"=="true" (
    echo.
    echo [HOST] Starte Desktop Capture Client...
    echo        (Laeuft auf dem HOST fuer Zugriff auf physische Monitore)
    echo.
    
    REM Prüfe Python
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python ist nicht installiert oder nicht im PATH!
        echo         Bitte installieren Sie Python 3.8+ und fuegen Sie es zum PATH hinzu.
        goto :end
    )
    
    REM Prüfe Desktop-Client-Verzeichnis
    if not exist "desktop-client\dual_screen_capture_client.py" (
        echo [ERROR] Desktop-Client nicht gefunden: desktop-client\dual_screen_capture_client.py
        goto :end
    )
    
    REM Starte Desktop-Client in neuem Fenster
    start "TRAE Desktop Capture" cmd /k "cd /d %~dp0\..\desktop-client && python dual_screen_capture_client.py --server-url ws://localhost:8007/ws/live-desktop --backend-url http://localhost:8007/api/client"
    
    echo [OK] Desktop-Client gestartet
)

:end
echo.
echo ========================================
echo  TRAE Desktop Streaming - Bereit!
echo ========================================
echo.
echo  Frontend:       http://localhost:5173
echo  Backend API:    http://localhost:8007
echo  OCR Engine:     http://localhost:8008
echo  Qdrant:         http://localhost:6333
echo.
echo  Container-Logs: docker-compose logs -f
echo  Stoppen:        docker-compose down
echo.
echo ========================================
echo.

if "%DETACH%"=="true" (
    echo Druecken Sie eine beliebige Taste zum Beenden (Container laufen weiter)...
    pause >nul
)

endlocal