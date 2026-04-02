"""
Comprehensive ATM-R Validation Suite
Tests all critical functionality to ensure ATM-R is working correctly.
"""

import numpy as np
from thalamo_pc_adaptive import ThalamoPC6Adaptive
from thalamo_pc_live import ThalamoPC6
import sys

def print_test(name, passed, details=""):
    """Print test result."""
    status = "[OK]" if passed else "[FAIL]"
    print(f"{status} {name}")
    if details:
        print(f"    {details}")
    if not passed:
        print(f"    ^^^ THIS IS A PROBLEM! ^^^")
    return passed

print("="*70)
print("ATM-R COMPREHENSIVE VALIDATION")
print("="*70)

all_passed = True

# Test 1: Gate Normalization (CRITICAL)
print("\n[TEST 1] Gate Normalization")
print("-" * 70)
try:
    atmr = ThalamoPC6Adaptive(seed=42)
    x_t = {mod: np.random.randn(atmr.d[mod]) for mod in atmr.modalities}
    out = atmr.step(x_t)

    gate_sum = np.sum(out['g'])
    passed = np.isclose(gate_sum, 1.0, atol=1e-6)
    all_passed &= print_test(
        "Gates sum to 1.0",
        passed,
        f"Sum = {gate_sum:.10f}"
    )

    all_non_negative = np.all(out['g'] >= 0)
    all_passed &= print_test(
        "All gates non-negative",
        all_non_negative,
        f"Gates: {out['g']}"
    )

    has_positive = np.max(out['g']) > 0
    all_passed &= print_test(
        "At least one gate > 0",
        has_positive,
        f"Max gate: {np.max(out['g']):.3f}"
    )
except Exception as e:
    all_passed = False
    print(f"[FAIL] Test 1 crashed with error: {e}")

# Test 2: Input Magnitude Responsiveness
print("\n[TEST 2] Input Magnitude Responsiveness")
print("-" * 70)
try:
    atmr = ThalamoPC6Adaptive(seed=42)

    # Strong vision
    x_strong_vision = {mod: np.zeros(atmr.d[mod]) for mod in atmr.modalities}
    x_strong_vision['vision'] = np.random.randn(128) * 3.0
    out1 = atmr.step(x_strong_vision)
    vision_gate_1 = out1['g'][0]

    # Strong audio
    x_strong_audio = {mod: np.zeros(atmr.d[mod]) for mod in atmr.modalities}
    x_strong_audio['audio'] = np.random.randn(64) * 3.0
    out2 = atmr.step(x_strong_audio)
    audio_gate_2 = out2['g'][1]

    passed_vision = vision_gate_1 > 0.3
    all_passed &= print_test(
        "Strong vision input dominates",
        passed_vision,
        f"Vision gate: {vision_gate_1:.3f} (expected > 0.3)"
    )

    passed_audio = audio_gate_2 > 0.3
    all_passed &= print_test(
        "Strong audio input dominates",
        passed_audio,
        f"Audio gate: {audio_gate_2:.3f} (expected > 0.3)"
    )
except Exception as e:
    all_passed = False
    print(f"[FAIL] Test 2 crashed with error: {e}")

# Test 3: Context Override
print("\n[TEST 3] Context Override")
print("-" * 70)
try:
    atmr = ThalamoPC6Adaptive(seed=42)
    x_t = {mod: np.random.randn(atmr.d[mod]) * 0.5 for mod in atmr.modalities}

    # No context
    out_no_ctx = atmr.step(x_t)
    vision_no_ctx = out_no_ctx['g'][0]
    audio_no_ctx = out_no_ctx['g'][1]

    # Vision context
    ctx_vision = np.zeros(6)
    ctx_vision[0] = 1.0
    out_ctx_vision = atmr.step(x_t, ctx=ctx_vision)
    vision_with_ctx = out_ctx_vision['g'][0]

    # Audio context
    ctx_audio = np.zeros(6)
    ctx_audio[1] = 1.0
    out_ctx_audio = atmr.step(x_t, ctx=ctx_audio)
    audio_with_ctx = out_ctx_audio['g'][1]

    passed_vision = vision_with_ctx > vision_no_ctx
    all_passed &= print_test(
        "Vision context increases vision gate",
        passed_vision,
        f"No ctx: {vision_no_ctx:.3f}, With ctx: {vision_with_ctx:.3f}"
    )

    passed_audio = audio_with_ctx > audio_no_ctx
    all_passed &= print_test(
        "Audio context increases audio gate",
        passed_audio,
        f"No ctx: {audio_no_ctx:.3f}, With ctx: {audio_with_ctx:.3f}"
    )
except Exception as e:
    all_passed = False
    print(f"[FAIL] Test 3 crashed with error: {e}")

# Test 4: Threat Override (SAFETY CRITICAL)
print("\n[TEST 4] Threat Override (SAFETY CRITICAL)")
print("-" * 70)
try:
    atmr = ThalamoPC6Adaptive(seed=42)

    # Normal operation
    x_normal = {mod: np.random.randn(atmr.d[mod]) * 0.5 for mod in atmr.modalities}
    x_normal['vision'] = np.random.randn(128) * 2.0  # Strong vision
    x_normal['threat'] = np.zeros(8)
    out_normal = atmr.step(x_normal)
    threat_normal = out_normal['g'][5]

    # Threat detected
    x_threat = x_normal.copy()
    x_threat['threat'] = np.random.randn(8) * 3.0
    out_threat = atmr.step(x_threat, hazard={'threat': 1.0}, adapt=True)
    threat_alert = out_threat['g'][5]

    passed = threat_alert > threat_normal
    all_passed &= print_test(
        "Threat detection increases threat gate",
        passed,
        f"Normal: {threat_normal:.3f}, Alert: {threat_alert:.3f} (delta: {threat_alert-threat_normal:.3f})"
    )

    significant = threat_alert > 0.2
    all_passed &= print_test(
        "Threat gate significant when alerted",
        significant,
        f"Threat gate: {threat_alert:.3f} (expected > 0.2)"
    )
except Exception as e:
    all_passed = False
    print(f"[FAIL] Test 4 crashed with error: {e}")

# Test 5: Adaptive Learning
print("\n[TEST 5] Adaptive Learning")
print("-" * 70)
try:
    atmr = ThalamoPC6Adaptive(seed=42)
    x_t = {mod: np.random.randn(atmr.d[mod]) for mod in atmr.modalities}

    # Record initial prior
    initial_prior = atmr.priors['threat']

    # Apply hazard signal multiple times
    for _ in range(10):
        atmr.step(x_t, hazard={'threat': 1.0}, adapt=True)

    final_prior = atmr.priors['threat']

    passed = final_prior > initial_prior
    all_passed &= print_test(
        "Hazard signal increases prior",
        passed,
        f"Initial: {initial_prior:.4f}, Final: {final_prior:.4f} (delta: {final_prior-initial_prior:.4f})"
    )

    # Test reward
    initial_vision = atmr.priors['vision']
    x_t['vision'] = np.random.randn(128) * 2.0
    for _ in range(10):
        atmr.step(x_t, reward={'vision': 0.1}, adapt=True)

    final_vision = atmr.priors['vision']
    passed_reward = final_vision > initial_vision
    all_passed &= print_test(
        "Reward signal increases prior",
        passed_reward,
        f"Initial: {initial_vision:.4f}, Final: {final_vision:.4f} (delta: {final_vision-initial_vision:.4f})"
    )
except Exception as e:
    all_passed = False
    print(f"[FAIL] Test 5 crashed with error: {e}")

# Test 6: Consistency Over Time
print("\n[TEST 6] Consistency Over Time")
print("-" * 70)
try:
    atmr = ThalamoPC6Adaptive(seed=42)

    gate_sums = []
    gate_history = []

    for _ in range(50):
        x_t = {mod: np.random.randn(atmr.d[mod]) for mod in atmr.modalities}
        out = atmr.step(x_t, adapt=True)
        gate_sums.append(np.sum(out['g']))
        gate_history.append(out['g'].copy())

    gate_sums = np.array(gate_sums)
    all_close = np.allclose(gate_sums, 1.0, atol=1e-6)

    all_passed &= print_test(
        "Gates consistently sum to 1.0 over 50 steps",
        all_close,
        f"Mean: {np.mean(gate_sums):.10f}, Std: {np.std(gate_sums):.2e}"
    )

    # Check diversity
    gate_history = np.array(gate_history)
    mean_gates = np.mean(gate_history, axis=0)
    max_dominance = np.max(mean_gates)

    reasonable_diversity = max_dominance < 0.95
    all_passed &= print_test(
        "Reasonable gate diversity (no single agent > 95%)",
        reasonable_diversity,
        f"Max average gate: {max_dominance:.3f}"
    )

    print(f"\n    Average gates over 50 steps:")
    for i, mod in enumerate(atmr.modalities):
        bar = "#" * int(mean_gates[i] * 50)
        print(f"    {mod:12s}: {mean_gates[i]:.3f}  {bar}")

except Exception as e:
    all_passed = False
    print(f"[FAIL] Test 6 crashed with error: {e}")

# Test 7: No NaN/Inf Values
print("\n[TEST 7] No NaN/Inf Values")
print("-" * 70)
try:
    atmr = ThalamoPC6Adaptive(seed=42)

    # Try various scenarios
    scenarios = [
        "normal input",
        "zero input",
        "large input",
        "small input"
    ]

    has_nan_inf = False

    for scenario in scenarios:
        if scenario == "normal input":
            x_t = {mod: np.random.randn(atmr.d[mod]) for mod in atmr.modalities}
        elif scenario == "zero input":
            x_t = {mod: np.zeros(atmr.d[mod]) for mod in atmr.modalities}
        elif scenario == "large input":
            x_t = {mod: np.random.randn(atmr.d[mod]) * 10.0 for mod in atmr.modalities}
        elif scenario == "small input":
            x_t = {mod: np.random.randn(atmr.d[mod]) * 0.01 for mod in atmr.modalities}

        out = atmr.step(x_t)

        has_nan = np.any(np.isnan(out['g']))
        has_inf = np.any(np.isinf(out['g']))

        if has_nan or has_inf:
            has_nan_inf = True
            print(f"    [FAIL] {scenario}: NaN={has_nan}, Inf={has_inf}")
        else:
            print(f"    [OK] {scenario}: No NaN/Inf")

    all_passed &= print_test(
        "No NaN/Inf in any scenario",
        not has_nan_inf,
        ""
    )
except Exception as e:
    all_passed = False
    print(f"[FAIL] Test 7 crashed with error: {e}")

# Test 8: Determinism with Seed
print("\n[TEST 8] Determinism with Seed")
print("-" * 70)
try:
    # Run 1
    atmr1 = ThalamoPC6Adaptive(seed=42)
    x_t = {mod: np.random.randn(atmr1.d[mod]) for mod in atmr1.modalities}
    out1 = atmr1.step(x_t)

    # Run 2 (same seed)
    atmr2 = ThalamoPC6Adaptive(seed=42)
    out2 = atmr2.step(x_t)

    deterministic = np.allclose(out1['g'], out2['g'], atol=1e-10)
    all_passed &= print_test(
        "Deterministic with same seed",
        deterministic,
        f"Max difference: {np.max(np.abs(out1['g'] - out2['g'])):.2e}"
    )
except Exception as e:
    all_passed = False
    print(f"[FAIL] Test 8 crashed with error: {e}")

# Final Summary
print("\n" + "="*70)
if all_passed:
    print("[SUCCESS] ALL TESTS PASSED - ATM-R IS WORKING CORRECTLY!")
    print("="*70)
    print("\nATM-R is validated and safe to use in your multiagent system.")
    sys.exit(0)
else:
    print("[FAILURE] SOME TESTS FAILED - DO NOT USE ATM-R YET!")
    print("="*70)
    print("\n[WARNING] ATM-R has issues that need to be fixed!")
    print("Please review the failed tests above and debug before deployment.")
    sys.exit(1)
