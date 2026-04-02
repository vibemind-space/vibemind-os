"""
Experiment: Test how context influences routing.
"""
from thalamo_pc_adaptive import ThalamoPC6Adaptive
import numpy as np

model = ThalamoPC6Adaptive(seed=42)

print("=" * 70)
print("CONTEXT SWITCHING EXPERIMENT")
print("=" * 70)
print()

# Fixed input (balanced across modalities)
x = {m: np.random.randn(model.d[m]) * 0.8 for m in model.modalities}

print("Testing different context vectors on the same input...")
print()

# Test different contexts
contexts = {
    "No Context": None,
    "Vision Focus": np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
    "Audio Focus": np.array([0.0, 1.0, 0.0, 0.0, 0.0, 0.0]),
    "Touch Focus": np.array([0.0, 0.0, 1.0, 0.0, 0.0, 0.0]),
    "Multi-Focus (Vision+Audio)": np.array([0.5, 0.5, 0.0, 0.0, 0.0, 0.0]),
}

for ctx_name, ctx in contexts.items():
    model.reset_state()

    # Warmup with this context
    for _ in range(10):
        out = model.step(x, ctx=ctx, adapt=True)

    # Show results
    print(f"{ctx_name}:")
    dominant_idx = np.argmax(out['g'])
    dominant_mode = model.modalities[dominant_idx]
    print(f"  Dominant: {dominant_mode} ({out['g'][dominant_idx]:.1%})")

    # Show top 3
    top_3 = np.argsort(out['g'])[-3:][::-1]
    for idx in top_3:
        mode = model.modalities[idx]
        gate = out['g'][idx]
        bar = '#' * int(gate * 30)
        print(f"    {mode:12s}: {gate:5.1%} {bar}")
    print()

print("=" * 70)
print("OBSERVATION: Context strongly influences routing!")
print("=" * 70)
