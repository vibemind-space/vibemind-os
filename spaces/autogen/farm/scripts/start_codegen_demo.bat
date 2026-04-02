@echo off
echo ============================================================
echo  AutoGen Security PoC - Code Injection
echo ============================================================
echo.
echo  Dieses Script startet 3 Docker Container:
echo    1. gRPC Host (kein TLS, keine Auth)
echo    2. Legitimes Team (GPT-4o CodeGen + Reviewer + Executor)
echo    3. Angreifer (Eavesdrop + 3 Code-Injection Payloads)
echo.
echo  Voraussetzung: Docker Desktop muss laufen!
echo.
pause

cd /d "%~dp0poc_codegen"
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
echo [2/2] Starting demo... (dauert ca. 90 Sekunden)
echo.
docker compose up

echo.
echo Demo beendet. Raeume auf...
docker compose down
echo.
echo Fertig! Druecke eine Taste zum Schliessen.
pause
