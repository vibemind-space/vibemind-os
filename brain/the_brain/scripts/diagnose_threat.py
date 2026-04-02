"""Diagnose why threat override isn't working."""

import numpy as np
from thalamo_pc_adaptive import ThalamoPC6Adaptive

print("="*70)
print("THREAT OVERRIDE DIAGNOSIS")
print("="*70)

atmr = ThalamoPC6Adaptive(seed=42)

# Scenario: Strong vision input with threat
print("\n[Scenario 1] Strong vision + weak threat")
x_t = {
    'vision': np.random.randn(128) * 2.0,   # Strong
    'audio': np.random.randn(64) * 0.5,
    'touch': np.zeros(32),
    'taste': np.zeros(16),
    'vestibular': np.zeros(16),
    'threat': np.random.randn(8) * 0.5      # Weak
}

out = atmr.step(x_t, hazard={'threat': 1.0}, adapt=True)

print(f"\nInput magnitudes:")
for mod in atmr.modalities:
    norm = np.linalg.norm(x_t[mod])
    print(f"  {mod:12s}: {norm:.3f}")

print(f"\nPrediction errors:")
for mod, pe in out['pe'].items():
    print(f"  {mod:12s}: {pe:.3f}")

print(f"\nPriors:")
for mod in atmr.modalities:
    print(f"  {mod:12s}: {atmr.priors[mod]:.3f}")

print(f"\nGates:")
for i, mod in enumerate(atmr.modalities):
    print(f"  {mod:12s}: {out['g'][i]:.3f}")

print(f"\n[Analysis] Vision dominates because input magnitude is much higher")

# Scenario 2: Increase threat magnitude
print("\n" + "="*70)
print("[Scenario 2] Strong vision + STRONG threat")
x_t2 = {
    'vision': np.random.randn(128) * 2.0,   # Strong
    'audio': np.random.randn(64) * 0.5,
    'touch': np.zeros(32),
    'taste': np.zeros(16),
    'vestibular': np.zeros(16),
    'threat': np.random.randn(8) * 5.0      # VERY STRONG
}

out2 = atmr.step(x_t2, hazard={'threat': 1.0}, adapt=True)

print(f"\nInput magnitudes:")
for mod in atmr.modalities:
    norm = np.linalg.norm(x_t2[mod])
    print(f"  {mod:12s}: {norm:.3f}")

print(f"\nGates:")
for i, mod in enumerate(atmr.modalities):
    print(f"  {mod:12s}: {out2['g'][i]:.3f}")

if out2['g'][5] > 0.2:
    print(f"\n[SUCCESS] Threat now gets attention! ({out2['g'][5]:.1%})")
else:
    print(f"\n[ISSUE] Threat still weak even with 5x magnitude ({out2['g'][5]:.1%})")

# Scenario 3: Use prior boost after multiple hazards
print("\n" + "="*70)
print("[Scenario 3] After multiple hazard signals (learning)")

# Apply many hazards to boost prior
for _ in range(20):
    atmr.step(x_t2, hazard={'threat': 1.0}, adapt=True)

print(f"\nThreat prior after 20 hazards: {atmr.priors['threat']:.3f}")

# Now test with original weak threat
out3 = atmr.step(x_t, hazard={'threat': 1.0}, adapt=True)

print(f"\nGates with boosted prior but weak threat input:")
for i, mod in enumerate(atmr.modalities):
    print(f"  {mod:12s}: {out3['g'][i]:.3f}")

if out3['g'][5] > 0.2:
    print(f"\n[SUCCESS] Learned prior helps! Threat at {out3['g'][5]:.1%}")
else:
    print(f"\n[ISSUE] Even high prior doesn't help much ({out3['g'][5]:.1%})")

# Scenario 4: Context to force threat
print("\n" + "="*70)
print("[Scenario 4] Force threat via context")

ctx = np.zeros(6)
ctx[5] = 5.0  # Strong context for threat

out4 = atmr.step(x_t, ctx=ctx)

print(f"\nGates with threat context:")
for i, mod in enumerate(atmr.modalities):
    print(f"  {mod:12s}: {out4['g'][i]:.3f}")

if out4['g'][5] > 0.2:
    print(f"\n[SUCCESS] Context forces threat attention! ({out4['g'][5]:.1%})")
else:
    print(f"\n[ISSUE] Even context doesn't help ({out4['g'][5]:.1%})")

print("\n" + "="*70)
print("DIAGNOSIS SUMMARY")
print("="*70)
print("""
The threat override issue is caused by:

1. INPUT MAGNITUDE DOMINANCE
   - Vision has 128 dims, threat has only 8 dims
   - ||vision|| >> ||threat|| even with same random scale
   - Threat signal needs to be MUCH stronger to compete

2. BETA WEIGHTS
   - Activity weight (0.3) favors high magnitude
   - Prior weight (0.2) is not enough to overcome magnitude difference

SOLUTIONS:
A. Amplify threat input (multiply by 5-10x)
B. Increase threat prior baseline (0.25 → 0.5)
C. Increase beta_prior weight (0.2 → 0.4)
D. Reduce threat dimension to match magnitude competition
E. Use context to force threat attention when needed
""")
