@echo off
REM Tahlamus CTM-ATM-R Environment Setup
REM Creates a clean venv with all dependencies

echo ============================================================
echo Tahlamus CTM-ATM-R Environment Setup
echo ============================================================
echo.

REM Check if venv exists
if exist .venv-tahlamus (
    echo Found existing .venv-tahlamus
    choice /C YN /M "Delete and recreate"
    if errorlevel 2 goto :activate
    if errorlevel 1 (
        echo Removing old venv...
        rmdir /s /q .venv-tahlamus
    )
)

echo.
echo Creating new virtual environment with uv...
uv venv .venv-tahlamus --python 3.11

:activate
echo.
echo Activating virtual environment...
call .venv-tahlamus\Scripts\activate.bat

echo.
echo ============================================================
echo Installing Core Dependencies
echo ============================================================
echo.

REM Core packages
echo [1/6] Installing PyTorch with CUDA 11.8...
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

echo.
echo [2/6] Installing NumPy...
uv pip install numpy

echo.
echo [3/6] Installing Flask (for dashboards)...
uv pip install flask flask-cors

echo.
echo [4/6] Installing JAX (optional, for performance)...
uv pip install "jax[cpu]"

echo.
echo [5/6] Installing build tools...
uv pip install packaging ninja

echo.
echo [6/6] Installing matplotlib...
uv pip install matplotlib

echo.
echo ============================================================
echo Checking Installation
echo ============================================================
echo.

python -c "import torch; print(f'PyTorch: {torch.__version__}')"
python -c "import numpy; print(f'NumPy: {numpy.__version__}')"
python -c "import flask; print(f'Flask: {flask.__version__}')"
python -c "import jax; print(f'JAX: {jax.__version__}')"

echo.
echo ============================================================
echo Mamba Installation Options
echo ============================================================
echo.
echo You have 2 options for Mamba:
echo.
echo [A] Simulation Mode (NO CUDA Toolkit needed)
echo     - Works immediately
echo     - Use: mamba_integration.py (MambaSSMSimulator)
echo     - Good for: Development, Testing, Prototyping
echo.
echo [B] Real Mamba (Requires System CUDA Toolkit 11.8)
echo     - Needs: CUDA Toolkit installed on system
echo     - 100x faster
echo     - Good for: Production, Long sequences
echo.
choice /C AB /M "Which option do you want"

if errorlevel 2 goto :real_mamba
if errorlevel 1 goto :simulation

:simulation
echo.
echo ============================================================
echo Simulation Mode Selected
echo ============================================================
echo.
echo All required packages are installed!
echo Mamba simulation is ready to use.
echo.
echo Test it:
echo   python mamba_integration.py
echo   python ctm_use_cases.py
echo   python monitor_web_ctm.py
echo.
goto :end

:real_mamba
echo.
echo ============================================================
echo Real Mamba Installation
echo ============================================================
echo.
echo IMPORTANT: This requires CUDA Toolkit 11.8 on your system!
echo.
echo Checking for CUDA Toolkit...
where nvcc >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] CUDA Toolkit not found!
    echo.
    echo You need to install CUDA Toolkit 11.8 first:
    echo   1. Download: https://developer.nvidia.com/cuda-11-8-0-download-archive
    echo   2. Install (Express Installation)
    echo   3. Reboot system
    echo   4. Run this script again
    echo.
    goto :end
)

echo Found CUDA Toolkit!
nvcc --version
echo.

echo Installing causal-conv1d...
uv pip install "causal-conv1d>=1.2.0"

echo.
echo Installing mamba-ssm (this may take 5-10 minutes)...
uv pip install mamba-ssm --no-cache-dir

echo.
echo Testing Mamba installation...
python -c "from mamba_ssm import Mamba; print('SUCCESS: Real Mamba installed!')"

if errorlevel 1 (
    echo.
    echo [ERROR] Mamba installation failed!
    echo Falling back to simulation mode.
    echo.
) else (
    echo.
    echo ============================================================
    echo Real Mamba Successfully Installed!
    echo ============================================================
    echo.
    echo Test it:
    echo   python mamba_real_integration.py
    echo.
)

:end
echo.
echo ============================================================
echo Setup Complete!
echo ============================================================
echo.
echo Your virtual environment is ready at: .venv-tahlamus
echo.
echo To activate it in the future:
echo   .venv-tahlamus\Scripts\activate.bat
echo.
echo Your installed packages:
uv pip list
echo.
echo Next steps:
echo   - Run: python monitor_web_ctm.py (Dashboard)
echo   - Run: python ctm_use_cases.py (Use Cases Demo)
echo   - Run: python check_mamba_installation.py (Status Check)
echo.
pause
