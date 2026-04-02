"""
Test your custom configuration.
"""
import numpy as np
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_loader import create_model_from_config

print("=" * 70)
print("TESTING CUSTOM CONFIGURATION")
print("=" * 70)
print()

# Load your custom config
model = create_model_from_config('configs/my_custom.yaml', adaptive=True)

print("Configuration loaded:")
print(f"  Modalities: {model.modalities}")
print(f"  Dimensions: {model.d}")
print(f"  Gate temp: {model.gate_temp}")
print(f"  Priors: {model.priors}")
print()

# Test it
print("Running test scenario...")
x = {m: np.random.randn(model.d[m]) * 1.0 for m in model.modalities}

for step in range(20):
    out = model.step(x, adapt=True)

print("\nFinal gate distribution:")
for i, m in enumerate(model.modalities):
    bar = '#' * int(out['g'][i] * 50)
    print(f"  {m:12s}: {out['g'][i]:5.1%} {bar}")

print()
print("=" * 70)
print("SUCCESS! Your custom config works!")
print("=" * 70)
print()
print("Tips:")
print("  - Lower gate_temp (0.1-0.3) = sharper selection")
print("  - Higher gate_temp (0.8-1.5) = softer, more balanced")
print("  - Adjust priors to change baseline importance")
print("  - Adjust tau to change response speed")
