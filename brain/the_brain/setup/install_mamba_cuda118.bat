@echo off
REM ============================================================
REM Mamba Installation with CUDA 11.8 (Force)
REM ============================================================

echo ============================================================
echo Mamba Installation - CUDA 11.8
echo ============================================================
echo.

REM Step 1: Set CUDA 11.8 Path FIRST
echo [1/5] Setting CUDA 11.8 environment...
set "CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8"
set "CUDA_HOME=%CUDA_PATH%"
set "PATH=%CUDA_PATH%\bin;%PATH%"

echo CUDA_PATH: %CUDA_PATH%
echo.

REM Verify CUDA 11.8
nvcc --version | findstr "11.8"
if %errorlevel% neq 0 (
    echo ERROR: CUDA 11.8 not found!
    pause
    exit /b 1
)
echo [OK] CUDA 11.8 active
echo.

REM Step 2: Activate Visual Studio 2022
echo [2/5] Activating Visual Studio 2022...
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Could not activate VS 2022
    pause
    exit /b 1
)
echo [OK] Visual Studio 2022 activated
echo.

REM Step 3: Set compiler flags
echo [3/5] Setting compiler flags...
set DISTUTILS_USE_SDK=1
set MSSdk=1
set TORCH_CUDA_ARCH_LIST=6.0;6.1;7.0;7.5;8.0;8.6
echo [OK] Compiler flags set
echo.

REM Step 4: Install causal-conv1d
echo [4/5] Installing causal-conv1d (5-10 min)...
echo This compiles CUDA code. Please be patient...
echo.
python -m pip install causal-conv1d>=1.2.0 --no-cache-dir --force-reinstall
if %errorlevel% neq 0 (
    echo.
    echo ERROR: causal-conv1d installation failed!
    echo.
    echo Trying pre-built wheel...
    python -m pip install causal-conv1d --no-build-isolation
    if %errorlevel% neq 0 (
        echo FAILED. See error above.
        pause
        exit /b 1
    )
)
echo [OK] causal-conv1d installed
echo.

REM Step 5: Install mamba-ssm
echo [5/5] Installing mamba-ssm (5-10 min)...
echo This also compiles CUDA code. Please wait...
echo.
python -m pip install mamba-ssm --no-cache-dir --force-reinstall
if %errorlevel% neq 0 (
    echo.
    echo ERROR: mamba-ssm installation failed!
    pause
    exit /b 1
)
echo [OK] mamba-ssm installed
echo.

REM Test installation
echo ============================================================
echo Testing installation...
echo ============================================================
python -c "from mamba_ssm import Mamba; print('SUCCESS: Mamba imported!')"
if %errorlevel% neq 0 (
    echo FAILED: Import test failed
    pause
    exit /b 1
)

python -c "import torch; from mamba_ssm import Mamba; m = Mamba(d_model=64); print('SUCCESS: Mamba works!')"
if %errorlevel% neq 0 (
    echo FAILED: Mamba test failed
    pause
    exit /b 1
)

echo.
echo ============================================================
echo INSTALLATION COMPLETE!
echo ============================================================
echo.
echo You can now use real Mamba:
echo   python mamba_real_integration.py
echo   python ctm_use_cases.py
echo.
pause
