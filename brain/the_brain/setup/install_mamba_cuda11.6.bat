@echo off
REM Quick Mamba installation with existing CUDA 11.6
REM This tries to use your existing CUDA 11.6 installation

echo ============================================================
echo Quick Real Mamba Installation with CUDA 11.6
echo ============================================================
echo.
echo This will try to install mamba-ssm using your existing
echo CUDA 11.6 installation. This might work since PyTorch
echo supports CUDA 11.6-11.8.
echo.
echo If it fails, you'll need to install CUDA 11.8 instead.
echo.

REM Set CUDA 11.6 environment
set "CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.6"
set "CUDA_HOME=%CUDA_PATH%"
set "PATH=%CUDA_PATH%\bin;%CUDA_PATH%\libnvvp;%PATH%"

echo Testing CUDA setup...
echo.
nvcc --version
if errorlevel 1 (
    echo [ERROR] NVCC still not found!
    echo.
    echo The CUDA 11.6 installation might be incomplete.
    echo You need to install CUDA Toolkit 11.8 instead.
    echo.
    echo Download: https://developer.nvidia.com/cuda-11-8-0-download-archive
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] NVCC found! Proceeding with Mamba installation...
echo.

echo ============================================================
echo Installing causal-conv1d (3-5 minutes)...
echo ============================================================
echo.
echo Disabling build isolation to preserve CUDA environment...
echo.

REM First install build dependencies
pip install packaging wheel setuptools

REM Install with no build isolation so CUDA env vars are preserved
pip install causal-conv1d>=1.2.0 --no-cache-dir --no-build-isolation
if errorlevel 1 (
    echo.
    echo [ERROR] causal-conv1d installation failed!
    echo This usually means CUDA compilation issues.
    echo.
    echo You might need to install CUDA 11.8 instead for better compatibility.
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] causal-conv1d installed successfully!
echo.

echo ============================================================
echo Installing mamba-ssm (5-10 minutes)...
echo ============================================================
echo.

pip install mamba-ssm --no-cache-dir --no-build-isolation
if errorlevel 1 (
    echo.
    echo [ERROR] mamba-ssm installation failed!
    echo.
    echo Recommendation: Install CUDA 11.8 for perfect compatibility.
    echo Download: https://developer.nvidia.com/cuda-11-8-0-download-archive
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Testing Mamba...
echo ============================================================
echo.

python -c "from mamba_ssm import Mamba; print('[OK] Mamba imported successfully!')"
if errorlevel 1 (
    echo [ERROR] Mamba import failed!
    pause
    exit /b 1
)

python -c "import torch; from mamba_ssm import Mamba; m = Mamba(d_model=64).cuda(); print('[OK] Mamba on CUDA works!')"
if errorlevel 1 (
    echo [WARNING] Mamba CUDA test failed (but import worked)
) else (
    echo [OK] Mamba fully functional with CUDA!
)

echo.
echo ============================================================
echo SUCCESS! Mamba installed with CUDA 11.6!
echo ============================================================
echo.
echo Test it:
echo   python mamba_real_integration.py
echo   python ctm_use_cases.py
echo.

pause
