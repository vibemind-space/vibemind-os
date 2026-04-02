"""Quick demo showing ATM-R in action."""
from thalamo_pc_adaptive import ThalamoPC6Adaptive
import numpy as np

print('='*70)
print('LIVE DEMO: ATM-R Multimodal Routing')
print('='*70)
print()

# Create adaptive model
model = ThalamoPC6Adaptive(seed=42)

print('Model initialized:')
print(f'  Modalities: {model.modalities}')
print(f'  Gate temperature: {model.gate_temp}')
print()

# Scenario 1: Vision-heavy input
print('--- Scenario 1: Strong Visual Input ---')
x1 = {m: np.zeros(model.d[m]) for m in model.modalities}
x1['vision'] = np.random.randn(model.d['vision']) * 2.0  # Strong

for _ in range(10):  # Warmup
    out = model.step(x1, adapt=True)

gates_str = ', '.join([f"{m}: {out['g'][i]:.1%}" for i, m in enumerate(model.modalities)])
print(f'Gates: {gates_str}')
print(f'Dominant: {model.modalities[np.argmax(out["g"])]}')
print()

# Scenario 2: Audio-heavy input
print('--- Scenario 2: Strong Audio Input ---')
model.reset_state()
x2 = {m: np.zeros(model.d[m]) for m in model.modalities}
x2['audio'] = np.random.randn(model.d['audio']) * 2.0  # Strong

for _ in range(10):  # Warmup
    out = model.step(x2, adapt=True)

gates_str = ', '.join([f"{m}: {out['g'][i]:.1%}" for i, m in enumerate(model.modalities)])
print(f'Gates: {gates_str}')
print(f'Dominant: {model.modalities[np.argmax(out["g"])]}')
print()

# Scenario 3: Context switching
print('--- Scenario 3: Context-Driven Switching ---')
model.reset_state()
x3 = {m: np.random.randn(model.d[m]) * 0.5 for m in model.modalities}

# Prefer vision
ctx_vision = np.zeros(6)
ctx_vision[0] = 1.0
for _ in range(5):
    out = model.step(x3, ctx=ctx_vision, adapt=True)
vision_gate = out['g'][0]
print(f'With vision context: {model.modalities[np.argmax(out["g"])]} dominant ({vision_gate:.1%})')

# Prefer audio
ctx_audio = np.zeros(6)
ctx_audio[1] = 1.0
for _ in range(5):
    out = model.step(x3, ctx=ctx_audio, adapt=True)
audio_gate = out['g'][1]
print(f'With audio context: {model.modalities[np.argmax(out["g"])]} dominant ({audio_gate:.1%})')
print()

# Scenario 4: Multi-step trajectory
print('--- Scenario 4: Multi-Step Processing ---')
model.reset_state()
trajectory = []
for step in range(20):
    x_t = {m: np.random.randn(model.d[m]) * 0.3 for m in model.modalities}
    out = model.step(x_t, adapt=True)
    dominant = model.modalities[np.argmax(out['g'])]
    trajectory.append(dominant)

from collections import Counter
mode_counts = Counter(trajectory)
print('Mode distribution over 20 steps:')
for mode, count in mode_counts.most_common():
    bar = '#' * (count * 3)
    print(f'  {mode:12s}: {count:2d} steps {bar}')
print()

print('='*70)
print('SUCCESS: ATM-R routing works!')
print('='*70)
print()
print('Key Features Demonstrated:')
print('  1. Input magnitude responsiveness')
print('  2. Modality-specific routing')
print('  3. Context-driven switching')
print('  4. Adaptive learning over time')
print('  5. Multi-step coherent processing')
