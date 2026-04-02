"""
Experiment: Watch adaptive learning in action.
"""
from thalamo_pc_adaptive import ThalamoPC6Adaptive
import numpy as np
import matplotlib.pyplot as plt

model = ThalamoPC6Adaptive(seed=42)

# Track evolution over time
steps = 100
gate_history = []
prior_history = {m: [] for m in model.modalities}

print("=" * 70)
print("ADAPTIVE LEARNING EXPERIMENT")
print("=" * 70)
print("\nTraining for 100 steps with hazard signals on 'threat'...")
print()

# Simulate threat scenario
for step in range(steps):
    # Create input with occasional threat
    x = {m: np.random.randn(model.d[m]) * 0.5 for m in model.modalities}

    # Inject threat signal every 10 steps
    if step % 10 == 0:
        x['threat'] = np.random.randn(model.d['threat']) * 2.0
        hazard = {'threat': 1.0}
    else:
        hazard = None

    # Step with adaptation
    out = model.step(x, hazard=hazard, adapt=True)

    # Track
    gate_history.append(out['g'].copy())
    for i, m in enumerate(model.modalities):
        prior_history[m].append(model.priors[m])

    if step % 20 == 0:
        print(f"Step {step:3d} - Threat prior: {model.priors['threat']:.3f}, "
              f"Threat gate: {out['g'][model.modalities.index('threat')]:.1%}")

print()
print("=" * 70)
print("RESULTS")
print("=" * 70)
print("\nPrior evolution:")
for m in model.modalities:
    initial = prior_history[m][0]
    final = prior_history[m][-1]
    change = final - initial
    print(f"  {m:12s}: {initial:.3f} -> {final:.3f} (Δ{change:+.3f})")

print("\nFinal gate distribution:")
final_gates = gate_history[-1]
for i, m in enumerate(model.modalities):
    bar = '#' * int(final_gates[i] * 50)
    print(f"  {m:12s}: {final_gates[i]:5.1%} {bar}")
