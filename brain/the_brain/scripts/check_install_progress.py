"""Quick check for Mamba installation progress."""
import time

print("Checking installation progress...\n")

# Check 1: causal-conv1d
try:
    from causal_conv1d import causal_conv1d_fn
    print("[OK] causal-conv1d: INSTALLED")
    causal_ok = True
except Exception as e:
    print(f"[  ] causal-conv1d: NOT YET ({type(e).__name__})")
    causal_ok = False

# Check 2: mamba-ssm
try:
    from mamba_ssm import Mamba
    print("[OK] mamba-ssm: INSTALLED")
    mamba_ok = True
except Exception as e:
    print(f"[  ] mamba-ssm: NOT YET ({type(e).__name__})")
    mamba_ok = False

print()
if causal_ok and mamba_ok:
    print("="*60)
    print("SUCCESS! Both packages installed!")
    print("="*60)
    print("\nYou can now run:")
    print("  python mamba_real_integration.py")
    print("  python ctm_use_cases.py")
elif causal_ok:
    print("Status: causal-conv1d done, waiting for mamba-ssm...")
else:
    print("Status: Still compiling causal-conv1d...")
    print("This can take 5-10 minutes. Please wait...")
