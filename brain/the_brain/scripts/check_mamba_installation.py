"""
Mamba Installation Status Checker

Prüft jeden Schritt der Installation und zeigt Fortschritt an.
"""

import sys
import subprocess
import os

def print_status(step, name, status, details=""):
    """Print installation step status."""
    symbols = {
        'pending': '[  ]',
        'ok': '[OK]',
        'fail': '[XX]',
        'wait': '[..]'
    }

    symbol = symbols.get(status, '[??]')
    print(f"{symbol} Step {step}: {name}")
    if details:
        print(f"     {details}")


def check_python():
    """Check Python version."""
    version = sys.version_info
    if version.major == 3 and version.minor >= 8:
        print_status(1, "Python Version", "ok", f"Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print_status(1, "Python Version", "fail", "Need Python 3.8+")
        return False


def check_pytorch():
    """Check PyTorch installation."""
    try:
        import torch
        print_status(2, "PyTorch", "ok", f"Version {torch.__version__}")
        return True
    except ImportError:
        print_status(2, "PyTorch", "fail", "Not installed")
        return False


def check_cuda_runtime():
    """Check CUDA Runtime."""
    try:
        import torch
        if torch.cuda.is_available():
            cuda_version = torch.version.cuda
            print_status(3, "CUDA Runtime", "ok", f"CUDA {cuda_version}")
            return True
        else:
            print_status(3, "CUDA Runtime", "fail", "CUDA not available")
            return False
    except (ImportError, RuntimeError, OSError):
        print_status(3, "CUDA Runtime", "fail", "Cannot check")
        return False


def check_gpu():
    """Check GPU."""
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print_status(4, "GPU", "ok", f"{gpu_name} ({gpu_mem:.1f} GB)")
            return True
        else:
            print_status(4, "GPU", "fail", "No GPU found")
            return False
    except (ImportError, RuntimeError, OSError):
        print_status(4, "GPU", "fail", "Cannot check")
        return False


def check_nvcc():
    """Check NVCC compiler."""
    try:
        result = subprocess.run(['nvcc', '--version'],
                              capture_output=True,
                              text=True,
                              timeout=5)
        if result.returncode == 0:
            # Parse version from output
            output = result.stdout
            if 'release 11.8' in output:
                print_status(5, "NVCC Compiler (CUDA Toolkit)", "ok", "CUDA 11.8 installed")
                return True
            else:
                version_line = [l for l in output.split('\n') if 'release' in l]
                version = version_line[0] if version_line else "Unknown"
                print_status(5, "NVCC Compiler (CUDA Toolkit)", "ok", version)
                return True
        else:
            print_status(5, "NVCC Compiler (CUDA Toolkit)", "fail", "nvcc found but error")
            return False
    except FileNotFoundError:
        print_status(5, "NVCC Compiler (CUDA Toolkit)", "pending", "Not installed - Download and install CUDA Toolkit 11.8")
        return False
    except Exception as e:
        print_status(5, "NVCC Compiler (CUDA Toolkit)", "fail", str(e))
        return False


def check_mamba_dependencies():
    """Check Mamba dependencies."""
    try:
        import packaging
        import ninja
        print_status(6, "Mamba Dependencies", "ok", "packaging, ninja")
        return True
    except ImportError as e:
        print_status(6, "Mamba Dependencies", "fail", f"Missing: {e}")
        return False


def check_causal_conv1d():
    """Check causal-conv1d."""
    try:
        import causal_conv1d
        print_status(7, "causal-conv1d", "ok", "Installed")
        return True
    except ImportError:
        print_status(7, "causal-conv1d", "pending", "pip install causal-conv1d>=1.2.0")
        return False


def check_mamba():
    """Check Mamba-SSM."""
    try:
        from mamba_ssm import Mamba
        print_status(8, "Mamba-SSM", "ok", "Installed!")
        return True
    except ImportError:
        print_status(8, "Mamba-SSM", "pending", "pip install mamba-ssm")
        return False


def check_mamba_cuda():
    """Check if Mamba works with CUDA."""
    try:
        import torch
        from mamba_ssm import Mamba

        # Try to create Mamba module on GPU
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        m = Mamba(d_model=64, d_state=16).to(device)

        # Test forward pass
        x = torch.randn(1, 10, 64).to(device)
        y = m(x)

        print_status(9, "Mamba CUDA Test", "ok", f"Working on {device.upper()}!")
        return True
    except ImportError:
        print_status(9, "Mamba CUDA Test", "pending", "Mamba not installed yet")
        return False
    except Exception as e:
        print_status(9, "Mamba CUDA Test", "fail", str(e))
        return False


def check_environment_variables():
    """Check CUDA environment variables."""
    cuda_path = os.environ.get('CUDA_PATH')
    cuda_path_v11_8 = os.environ.get('CUDA_PATH_V11_8')

    if cuda_path or cuda_path_v11_8:
        path = cuda_path or cuda_path_v11_8
        print_status(10, "CUDA Environment", "ok", f"CUDA_PATH: {path}")
        return True
    else:
        print_status(10, "CUDA Environment", "wait", "Set after CUDA Toolkit installation")
        return False


def main():
    print("="*80)
    print("MAMBA INSTALLATION STATUS CHECKER")
    print("="*80)
    print()

    results = []

    # Run all checks
    results.append(("Python", check_python()))
    results.append(("PyTorch", check_pytorch()))
    results.append(("CUDA Runtime", check_cuda_runtime()))
    results.append(("GPU", check_gpu()))
    results.append(("NVCC", check_nvcc()))
    results.append(("Dependencies", check_mamba_dependencies()))
    results.append(("causal-conv1d", check_causal_conv1d()))
    results.append(("Mamba-SSM", check_mamba()))

    # Only test Mamba CUDA if Mamba is installed
    if results[-1][1]:  # If Mamba check passed
        results.append(("Mamba CUDA", check_mamba_cuda()))

    results.append(("Environment", check_environment_variables()))

    # Summary
    print()
    print("="*80)
    print("SUMMARY")
    print("="*80)

    passed = sum(1 for _, status in results if status)
    total = len(results)
    progress = passed / total * 100

    print(f"Progress: {passed}/{total} steps completed ({progress:.0f}%)")
    print()

    # Next steps
    if not results[4][1]:  # NVCC not found
        print("NEXT STEP:")
        print("  1. Download CUDA Toolkit 11.8:")
        print("     https://developer.nvidia.com/cuda-11-8-0-download-archive")
        print("  2. Install (Express Installation)")
        print("  3. Reboot your system")
        print("  4. Run this script again")
    elif not results[6][1]:  # causal-conv1d not installed
        print("NEXT STEP:")
        print("  pip install causal-conv1d>=1.2.0")
    elif not results[7][1]:  # Mamba not installed
        print("NEXT STEP:")
        print("  pip install mamba-ssm")
    else:
        print("ALL STEPS COMPLETED! Mamba is ready to use!")
        print()
        print("Test it:")
        print("  python mamba_real_integration.py")

    print()
    print("="*80)


if __name__ == "__main__":
    main()
