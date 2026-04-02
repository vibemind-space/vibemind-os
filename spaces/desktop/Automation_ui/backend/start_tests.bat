@echo off
echo Starting TRAE Backend Tests...
echo.

REM Change to backend directory
cd /d "%~dp0"

REM Check if we're in the right directory
if not exist "run_tests.py" (
    echo Error: Cannot find run_tests.py in current directory
    echo Current directory: %CD%
    pause
    exit /b 1
)

echo Current directory: %CD%
echo.

REM Validate environment first
echo Validating test environment...
python run_tests.py --validate
if errorlevel 1 (
    echo Environment validation failed!
    pause
    exit /b 1
)

echo.
echo Environment validation passed!
echo.

REM Run quick tests first
echo Running quick tests...
python run_tests.py --quick

echo.
echo Quick tests completed!
echo.

REM Ask user if they want to run all tests
set /p choice="Run all tests? (y/n): "
if /i "%choice%"=="y" (
    echo Running all tests...
    python run_tests.py --all --verbose
)

echo.
echo Test execution completed!
pause 