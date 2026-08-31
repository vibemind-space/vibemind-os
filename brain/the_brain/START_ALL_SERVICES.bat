@echo off
REM ============================================================================
REM Tahlamus Complete System Startup Script
REM ============================================================================
REM This script starts all Tahlamus system components in the correct order
REM ============================================================================

echo.
echo ========================================================================
echo   TAHLAMUS - Complete Cognitive System Startup
echo ========================================================================
echo.

REM Check if virtual environment exists
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Please run: python -m venv .venv
    echo Then: .venv\Scripts\activate.bat
    echo Then: pip install -r requirements.txt
    pause
    exit /b 1
)

REM Activate virtual environment
echo [1/7] Activating virtual environment...
call .venv\Scripts\activate.bat

echo.
echo ========================================================================
echo   Starting Core Services
echo ========================================================================
echo.

REM 1. Production API Server (Port 5001)
echo [2/7] Starting Production API Server (Port 5001)...
start "Tahlamus API" cmd /k "cd /d %CD% && .venv\Scripts\activate.bat && python production/api_server.py"
timeout /t 3 /nobreak >nul

REM 2. Brain Dashboard (Port 5000)
echo [3/7] Starting Brain Dashboard (Port 5000)...
start "Brain Dashboard" cmd /k "cd /d %CD% && .venv\Scripts\activate.bat && python web/brain_dashboard_server.py"
timeout /t 3 /nobreak >nul

REM 3. Autonomous Swarm Server (Port 5002)
echo [4/7] Starting Autonomous Swarm Server (Port 5002)...
start "Swarm Server" cmd /k "cd /d %CD% && .venv\Scripts\activate.bat && python web/autonomous_swarm_server.py"
timeout /t 3 /nobreak >nul

echo.
echo ========================================================================
echo   Starting Optional Services
echo ========================================================================
echo.

REM 4. Memory API (Port 8001) - Optional
echo [5/7] Starting Memory API Service (Port 8001)...
if exist "memory_api\memory_service.py" (
    start "Memory API" cmd /k "cd /d %CD% && .venv\Scripts\activate.bat && python memory_api/memory_service.py"
    timeout /t 3 /nobreak >nul
) else (
    echo [SKIP] Memory API not found (optional)
)

REM 5. Unified Brain Service (Port varies) - Optional
echo [6/7] Starting Unified Brain Service...
if exist "production\unified_brain_service.py" (
    start "Unified Brain" cmd /k "cd /d %CD% && .venv\Scripts\activate.bat && python production/unified_brain_service.py"
    timeout /t 2 /nobreak >nul
) else (
    echo [SKIP] Unified Brain Service not found (optional)
)

REM 6. Brain Heartbeat (Background monitoring)
echo [7/7] Starting Brain Heartbeat Monitor...
if exist "production\brain_heartbeat.py" (
    start "Brain Heartbeat" cmd /k "cd /d %CD% && .venv\Scripts\activate.bat && python production/brain_heartbeat.py"
    timeout /t 2 /nobreak >nul
) else (
    echo [SKIP] Brain Heartbeat not found (optional)
)

echo.
echo ========================================================================
echo   System Status
echo ========================================================================
echo.
echo [CORE SERVICES]
echo   Production API:        http://localhost:5001
echo   Brain Dashboard:       http://localhost:5000
echo   Autonomous Swarm:      http://localhost:5002
echo.
echo [OPTIONAL SERVICES]
echo   Memory API:            http://localhost:8001 (if enabled)
echo   Unified Brain Service: Running in background
echo   Brain Heartbeat:       Running in background
echo.
echo ========================================================================
echo   All services started!
echo ========================================================================
echo.
echo Press Ctrl+C in each window to stop individual services
echo Or close all windows to stop everything
echo.
pause
