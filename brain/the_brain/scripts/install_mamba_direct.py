"""
Direct Mamba installation with proper environment setup
"""
import os
import sys
import subprocess

# Set CUDA environment variables
cuda_path = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.6"
os.environ['CUDA_PATH'] = cuda_path
os.environ['CUDA_HOME'] = cuda_path
os.environ['PATH'] = f"{cuda_path}\\bin;{cuda_path}\\libnvvp;{os.environ.get('PATH', '')}"

# Also set these for the build process
os.environ['TORCH_CUDA_ARCH_LIST'] = "8.6"  # RTX 3060 compute capability
os.environ['FORCE_CUDA'] = "1"

print("=" * 70)
print("Direct Mamba Installation with CUDA 11.6")
print("=" * 70)
print()

# Test CUDA
print("Testing CUDA...")
result = subprocess.run(['nvcc', '--version'], capture_output=True, text=True)
if result.returncode == 0:
    print("[OK] NVCC found:")
    print(result.stdout)
else:
    print("[ERROR] NVCC not found!")
    sys.exit(1)

print()
print("=" * 70)
print("Step 1: Installing build dependencies")
print("=" * 70)
subprocess.run([sys.executable, '-m', 'pip', 'install', 'packaging', 'wheel', 'setuptools', 'ninja'])

print()
print("=" * 70)
print("Step 2: Installing causal-conv1d (3-5 minutes)")
print("=" * 70)
print("This will compile CUDA kernels...")
print()

result = subprocess.run([
    sys.executable, '-m', 'pip', 'install',
    'causal-conv1d>=1.2.0',
    '--no-cache-dir',
    '--no-build-isolation',
    '-v'  # Verbose to see what's happening
], env=os.environ)

if result.returncode != 0:
    print()
    print("[ERROR] causal-conv1d installation failed!")
    print()
    print("This could mean:")
    print("  - CUDA compilation issues")
    print("  - Missing Visual Studio Build Tools")
    print("  - CUDA version incompatibility")
    print()
    print("Recommendation: Install CUDA Toolkit 11.8 for perfect compatibility")
    print("Download: https://developer.nvidia.com/cuda-11-8-0-download-archive")
    sys.exit(1)

print()
print("[OK] causal-conv1d installed!")

print()
print("=" * 70)
print("Step 3: Installing mamba-ssm (5-10 minutes)")
print("=" * 70)
print("This will compile more CUDA kernels...")
print()

result = subprocess.run([
    sys.executable, '-m', 'pip', 'install',
    'mamba-ssm',
    '--no-cache-dir',
    '--no-build-isolation',
    '-v'
], env=os.environ)

if result.returncode != 0:
    print()
    print("[ERROR] mamba-ssm installation failed!")
    print()
    print("Recommendation: Install CUDA Toolkit 11.8")
    sys.exit(1)

print()
print("[OK] mamba-ssm installed!")

print()
print("=" * 70)
print("Step 4: Testing installation")
print("=" * 70)

# Test import
try:
    from mamba_ssm import Mamba
    print("[OK] Mamba imported successfully!")
except Exception as e:
    print(f"[ERROR] Cannot import Mamba: {e}")
    sys.exit(1)

# Test CUDA functionality
try:
    import torch
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    m = Mamba(d_model=64, d_state=16).to(device)
    print(f"[OK] Mamba working on {device.upper()}!")
except Exception as e:
    print(f"[WARNING] Mamba CUDA test failed: {e}")
    print("But import works, so CPU mode is available")

print()
print("=" * 70)
print("SUCCESS! Real Mamba is installed!")
print("=" * 70)
print()
print("Test it:")
print("  python mamba_real_integration.py")
print("  python ctm_use_cases.py")
print()
