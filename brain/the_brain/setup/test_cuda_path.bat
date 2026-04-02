@echo off
REM Temporär CUDA 11.6 zu PATH hinzufügen und pip install versuchen

echo ====================================
echo Testing Mamba Installation with CUDA 11.6
echo ====================================
echo.

REM Set CUDA Path temporarily
set "CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.6"
set "PATH=%CUDA_PATH%\bin;%PATH%"

echo CUDA Path set to: %CUDA_PATH%
echo.

echo Testing nvcc:
nvcc --version
echo.

echo ====================================
echo Installing causal-conv1d...
echo ====================================
pip install causal-conv1d>=1.2.0
echo.

echo ====================================
echo Installing mamba-ssm...
echo ====================================
pip install mamba-ssm --no-cache-dir
echo.

echo ====================================
echo Testing Mamba import...
echo ====================================
python -c "from mamba_ssm import Mamba; print('SUCCESS: Mamba imported!')"
echo.

echo Done!
pause
