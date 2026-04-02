"""
Experiment: Test different input combinations and see routing behavior.
"""
from thalamo_pc_adaptive import ThalamoPC6Adaptive
import numpy as np

model = ThalamoPC6Adaptive(seed=42)

# Define different scenarios
scenarios = [
    ("Strong Vision", {'vision': 2.0, 'audio': 0.1, 'touch': 0.1}),
    ("Strong Audio", {'vision': 0.1, 'audio': 2.0, 'touch': 0.1}),
    ("Balanced", {'vision': 1.0, 'audio': 1.0, 'touch': 1.0}),
    ("Vision + Audio", {'vision': 1.5, 'audio': 1.5, 'touch': 0.1}),
]

print("=" * 70)
print("ROUTING EXPERIMENT")
print("=" * 70)
print()

for name, strengths in scenarios:
    model.reset_state()

    # Create input
    x = {m: np.random.randn(model.d[m]) * strengths.get(m, 0.1)
         for m in model.modalities}

    # Warmup
    for _ in range(10):
        out = model.step(x, adapt=True)

    # Print results
    print(f"Scenario: {name}")
    for i, m in enumerate(model.modalities):
        bar = '#' * int(out['g'][i] * 50)
        print(f"  {m:12s}: {out['g'][i]:5.1%} {bar}")
    print()
