@echo off
REM Setup script for ATM-R virtual environment (Windows)

echo ========================================
echo ATM-R Virtual Environment Setup
echo ========================================

REM Check if uv is installed
where uv >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: uv is not installed!
    echo Install it with: pip install uv
    exit /b 1
)

REM Create venv if it doesn't exist
if not exist ".venv" (
    echo Creating virtual environment with uv...
    uv venv .venv
)

REM Activate and install dependencies
echo.
echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo.
echo Installing base dependencies...
uv pip install -r requirements.txt

echo.
echo Installing ML frameworks and real-time deps...
uv pip install torch torchvision opencv-python sounddevice pybind11 numba

echo.
echo ========================================
echo Setup complete!
echo ========================================
echo.
echo To activate the environment, run:
echo   .venv\Scripts\activate.bat
echo.
echo To run tests:
echo   pytest tests/test_core.py -v
echo.
echo To run demo:
echo   python scripts/run_demo.py --adaptive --plot
