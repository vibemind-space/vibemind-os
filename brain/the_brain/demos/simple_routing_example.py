"""
EINFACHES BEISPIEL: ATM-R ist ein Router, kein Rechner!
"""
from thalamo_pc_adaptive import ThalamoPC6Adaptive
import numpy as np

print("=" * 70)
print("ATM-R = ROUTER, nicht RECHNER")
print("=" * 70)
print()

model = ThalamoPC6Adaptive(seed=42)

# Beispiel: Wir haben 3 "Rechner" (Funktionen)
def fast_calculator(a, b):
    """Schnell, aber ungenau."""
    return int(a + b)  # Kein Float

def accurate_calculator(a, b):
    """Langsam, aber genau."""
    import time
    time.sleep(0.01)  # Simuliere langsame Berechnung
    return a + b

def approximate_calculator(a, b):
    """Sehr schnell, sehr ungenau."""
    return round(a/10)*10 + round(b/10)*10

# ATM-R routet zwischen diesen Rechnern!
print("Wir haben 3 Rechner:")
print("  1. Fast Calculator (schnell, ungenau)")
print("  2. Accurate Calculator (langsam, genau)")
print("  3. Approximate Calculator (sehr schnell, sehr ungenau)")
print()

# Simulate different scenarios
scenarios = [
    ("Need speed, don't care about precision",
     {'vision': 0.1, 'audio': 0.1, 'touch': 2.0}),  # touch = fast

    ("Need accuracy, have time",
     {'vision': 2.0, 'audio': 0.1, 'touch': 0.1}),  # vision = accurate

    ("Need rough estimate only",
     {'vision': 0.1, 'audio': 0.1, 'taste': 2.0}),  # taste = approximate
]

calculators = {
    'touch': ('Fast Calculator', fast_calculator),
    'vision': ('Accurate Calculator', accurate_calculator),
    'taste': ('Approximate Calculator', approximate_calculator),
}

a, b = 15.7, 7.3

print(f"Problem: {a} + {b}")
print(f"Correct answer: {a + b}")
print()
print("-" * 70)
print()

for scenario_name, input_strengths in scenarios:
    print(f"Scenario: {scenario_name}")

    # Create input signal
    x = {m: np.random.randn(model.d[m]) * input_strengths.get(m, 0.1)
         for m in model.modalities}

    # ATM-R routes
    out = model.step(x, adapt=True)

    # Which calculator gets chosen?
    dominant_idx = np.argmax(out['g'])
    dominant_mode = model.modalities[dominant_idx]

    if dominant_mode in calculators:
        calc_name, calc_func = calculators[dominant_mode]
        result = calc_func(a, b)
        print(f"  -> ATM-R chose: {calc_name}")
        print(f"  -> Result: {result}")
    else:
        print(f"  -> ATM-R chose: {dominant_mode} (no calculator mapped)")

    print()

print("=" * 70)
print("FAZIT:")
print("=" * 70)
print("""
ATM-R hat NICHT gerechnet!
ATM-R hat nur ENTSCHIEDEN, welcher Rechner genutzt wird.

Das ist wie ein Dispatcher:
  - Du gibst ihm einen Job
  - Er entscheidet: "Nehme ich Worker A, B oder C?"
  - Der gewählte Worker macht die eigentliche Arbeit

ATM-R = Intelligenter Dispatcher/Router
Nicht = Rechner selbst
""")
