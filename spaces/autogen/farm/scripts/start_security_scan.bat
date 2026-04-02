@echo off
echo ============================================================
echo  Security Scanner - Distributed Agent System
echo ============================================================
echo.
echo  Dieses Script startet 2 Docker Container:
echo    1. gRPC Host (Koordinator)
echo    2. Scanner Worker (4 AI Agents: Orchestrator, Scanner, Analyzer, Reporter)
echo.
echo  Der Scanner prueft:
echo    - Offene Ports
echo    - Fehlende TLS-Verschluesselung
echo    - Unauthentifizierte gRPC-Endpoints
echo    - Exponierte Docker APIs
echo.
echo  Voraussetzung: Docker Desktop muss laufen!
echo.
pause

cd /d "%~dp0security_scanner"
echo.
echo [1/2] Building Docker images...
docker compose build
if errorlevel 1 (
    echo.
    echo FEHLER: Docker build fehlgeschlagen!
    echo Ist Docker Desktop gestartet?
    pause
    exit /b 1
)

echo.
echo [2/2] Starting security scan... (dauert ca. 60-120 Sekunden)
echo.
docker compose up
echo.
echo Scan beendet. Raeume auf...
docker compose down
echo.
echo Fertig! Druecke eine Taste zum Schliessen.
pause
