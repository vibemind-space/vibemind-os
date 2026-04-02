"""
Benchmark: Bridges-On vs Bridges-Off Performance.

Measures:
  1. Ring activation entropy (information richness)
  2. Prediction error convergence rate
  3. DualProcess routing accuracy (conflict detection)
  4. Forward pass latency with 0, 5, 10 bridges
  5. Stability (1000-tick coefficient of variation per ring)

Run: python tests/benchmark_bridges.py
"""

import sys
import time

import numpy as np
import torch

sys.path.insert(0, ".")

from dataclasses import dataclass
from typing import Optional

from core.radial_attention import DualProcessRouter, RadialAttentionNetwork


# ─── Fake bridge states (lightweight, no real modules) ────────────────────────

@dataclass
class FakeNeuromodState:
    dopamine: float = 0.5
    norepinephrine: float = 0.5
    serotonin: float = 0.5
    acetylcholine: float = 0.5
    anti_reward: float = 0.0
    ne_gain: float = 1.0
    explore_ratio: float = 0.5


@dataclass
class FakeCortexState:
    bias_signal: Optional[np.ndarray] = None
    inhibit: bool = False
    pfc_value: float = 0.5
    pfc_surprise: float = 0.0
    conflict: float = 0.0
    control_signal: float = 0.5
    error_likelihood: float = 0.0
    subjective_value: float = 0.5
    decision_confidence: float = 0.5
    choice_difficulty: float = 0.5


@dataclass
class FakeLimbicState:
    valence: float = 0.0
    arousal: float = 0.3
    threat_level: float = 0.0
    is_threat: bool = False
    go_drive: float = 0.5
    nogo_drive: float = 0.5
    net_value: float = 0.0
    effort_cost: float = 0.3
    salience: float = 0.3
    body_budget: float = 1.0
    feeling: str = "neutral"
    urgency: float = 0.0
    approach_drive: float = 0.3
    stress: float = 0.0


@dataclass
class FakeSleepWakeState:
    arousal: float = 0.5
    sensory_gain: float = 0.5
    histamine: float = 0.5
    is_awake: bool = True
    wakefulness_drive: float = 0.5
    melatonin: float = 0.0
    sleep_pressure: float = 0.0
    cholinergic_tone: float = 0.5
    rem_probability: float = 0.0


@dataclass
class FakeMotorState:
    prediction_error: float = 0.0
    model_confidence: float = 0.5
    motor_da: float = 0.5
    go_nogo_balance: float = 0.0
    disinhibited: bool = False
    inhibition_level: float = 0.5
    action_tendency: float = 0.5
    is_compensating: bool = False
    error_correction: float = 0.0
    peak_salience: float = 0.5
    movement_confidence: float = 0.5


@dataclass
class FakeDefenseState:
    defense_mode: str = "freeze"
    defense_intensity: float = 0.0
    emergency_mode: bool = False
    autonomic_activation: float = 0.0
    alarm_level: float = 0.0
    alarm_urgency: float = 0.0
    anxiety_level: float = 0.0
    vigilance: float = 0.3
    is_chronic_stress: bool = False
    should_interrupt: bool = False


@dataclass
class FakeMemoryState:
    theta_power: float = 0.5
    theta_frequency: float = 6.0
    coupling_strength: float = 0.5
    consolidation_strength: float = 0.5
    relay_strength: float = 0.5
    teaching_signal: float = 0.0
    error_magnitude: float = 0.0
    memory_gateway: float = 0.5


@dataclass
class FakeIntegrationState:
    binding_strength: float = 0.5
    reached_consciousness: bool = False
    dmn_activation: float = 0.3
    dmn_mode: str = "default"
    orienting_saliency: float = 0.3
    cortical_error: float = 0.0
    cortical_output: float = 0.5
    bilateral_coherence: float = 0.5
    transfer_efficiency: float = 0.5


@dataclass
class FakeVisceralState:
    visceral_level: float = 0.5
    afferent_strength: float = 0.3
    reflex_active: bool = False
    liking: float = 0.5
    wanting: float = 0.5
    approach_strength: float = 0.3


@dataclass
class FakeSocialState:
    face_detected: bool = False
    identity_score: float = 0.0
    text_detected: bool = False
    word_score: float = 0.0
    agency_score: float = 0.5
    reorient_signal: bool = False
    social_inference: float = 0.0
    social_salience: float = 0.0
    familiarity: float = 0.3
    is_novel: bool = False


ALL_BRIDGE_FACTORIES = {
    "neuromod": FakeNeuromodState,
    "cortex": FakeCortexState,
    "limbic": FakeLimbicState,
    "sleep_wake": FakeSleepWakeState,
    "motor": FakeMotorState,
    "defense": FakeDefenseState,
    "memory": FakeMemoryState,
    "integration": FakeIntegrationState,
    "visceral": FakeVisceralState,
    "social": FakeSocialState,
}

LEGACY_BRIDGES = {"neuromod", "cortex", "limbic"}
GENERIC_BRIDGES = {"sleep_wake", "motor", "defense", "memory",
                   "integration", "visceral", "social"}


def _make_network(bridge_names=None):
    """Create RadialAttentionNetwork with specified fake bridge states."""
    net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
    if bridge_names:
        for name in bridge_names:
            factory = ALL_BRIDGE_FACTORIES[name]
            state = factory()
            if name == "neuromod":
                net._neuromod_state = state
            elif name == "cortex":
                net._cortex_state = state
            elif name == "limbic":
                net._limbic_state = state
            else:
                net._bridge_states[name] = state
    return net


# ─── Utility functions ───────────────────────────────────────────────────────

def activation_entropy(tensor: torch.Tensor) -> float:
    """Shannon entropy of softmax-normalized activation magnitudes."""
    x = tensor.detach().abs().flatten()
    if x.sum() < 1e-12:
        return 0.0
    p = torch.softmax(x, dim=0)
    return -(p * torch.log(p + 1e-12)).sum().item()


def header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def metric(name, value, unit=""):
    print(f"    {name:40s}: {value:>10.4f} {unit}")


def metric_str(name, value):
    print(f"    {name:40s}: {value}")


# ─── Benchmark 1: Ring Activation Entropy ─────────────────────────────────────

def bench_entropy(ticks=100):
    """Compare ring activation entropy: bridges-off vs bridges-on."""
    header("1. RING ACTIVATION ENTROPY (information richness)")

    seeds = [torch.randn(1, 384) for _ in range(ticks)]

    for config_name, bridges in [
        ("No bridges", None),
        ("3 legacy (neuromod+cortex+limbic)", list(LEGACY_BRIDGES)),
        ("All 10 bridges", list(ALL_BRIDGE_FACTORIES.keys())),
    ]:
        net = _make_network(bridges)
        ring_entropies = [[] for _ in range(5)]

        with torch.no_grad():
            for seed in seeds:
                result = net(seed)
                for i, act in enumerate(result["ring_activations"]):
                    ring_entropies[i].append(activation_entropy(act))

        print(f"\n  Config: {config_name}")
        for i in range(5):
            avg = np.mean(ring_entropies[i])
            metric(f"Ring {i+1} avg entropy", avg, "nats")


# ─── Benchmark 2: Prediction Error Convergence ───────────────────────────────

def bench_pe_convergence(ticks=200):
    """Compare prediction error convergence rate."""
    header("2. PREDICTION ERROR CONVERGENCE")

    seeds = [torch.randn(1, 384) for _ in range(ticks)]

    for config_name, bridges in [
        ("No bridges", None),
        ("All 10 bridges", list(ALL_BRIDGE_FACTORIES.keys())),
    ]:
        net = _make_network(bridges)
        pe_series = []

        with torch.no_grad():
            for seed in seeds:
                result = net(seed)
                pe_series.append(np.mean(result["prediction_errors"]))

        first_50 = np.mean(pe_series[:50])
        last_50 = np.mean(pe_series[-50:])
        reduction = (first_50 - last_50) / (first_50 + 1e-12)

        print(f"\n  Config: {config_name}")
        metric("PE first 50 ticks", first_50)
        metric("PE last 50 ticks", last_50)
        metric("Relative reduction", reduction * 100, "%")


# ─── Benchmark 3: DualProcess Routing ─────────────────────────────────────────

def bench_dual_process(trials=200):
    """DualProcess routing with and without modulation context."""
    header("3. DUAL-PROCESS ROUTING")

    from core.modulation_context import ModulationContext

    router = DualProcessRouter(dim=128, conflict_threshold=0.3)

    for config_name, use_bridges in [
        ("No modulation", False),
        ("With modulation (all bridges)", True),
    ]:
        s1_count = 0
        s2_count = 0
        conflicts = []

        with torch.no_grad():
            for _ in range(trials):
                sys1 = torch.randn(1, 128)
                sys2 = torch.randn(1, 128)

                mod = None
                if use_bridges:
                    mod = ModulationContext()
                    mod.neuromod = FakeNeuromodState()
                    mod.cortex = FakeCortexState()
                    mod.limbic = FakeLimbicState()
                    mod.sleep_wake = FakeSleepWakeState()
                    mod.motor = FakeMotorState()
                    mod.defense = FakeDefenseState()
                    mod.memory = FakeMemoryState()
                    mod.integration = FakeIntegrationState()
                    mod.visceral = FakeVisceralState()
                    mod.social = FakeSocialState()
                    mod.compute()

                result = router(sys1, sys2, modulation=mod)
                if result["system_used"] == 1:
                    s1_count += 1
                else:
                    s2_count += 1
                conflicts.append(result["conflict_level"])

        print(f"\n  Config: {config_name}")
        metric("System 1 (fast)", s1_count, f"({100*s1_count/trials:.0f}%)")
        metric("System 2 (slow)", s2_count, f"({100*s2_count/trials:.0f}%)")
        metric("Avg conflict", np.mean(conflicts))
        metric("Conflict std", np.std(conflicts))


# ─── Benchmark 4: Latency ────────────────────────────────────────────────────

def bench_latency(warmup=10, trials=100):
    """Forward pass latency with 0, 5, 10 bridges."""
    header("4. FORWARD PASS LATENCY")

    five_bridges = ["neuromod", "cortex", "limbic", "sleep_wake", "motor"]
    all_bridges = list(ALL_BRIDGE_FACTORIES.keys())

    for config_name, bridges in [
        ("0 bridges", None),
        ("5 bridges", five_bridges),
        ("10 bridges", all_bridges),
    ]:
        net = _make_network(bridges)
        seed = torch.randn(1, 384)

        # Warmup
        with torch.no_grad():
            for _ in range(warmup):
                net(seed)

        # Timed
        times = []
        with torch.no_grad():
            for _ in range(trials):
                start = time.perf_counter()
                net(torch.randn(1, 384))
                elapsed = (time.perf_counter() - start) * 1000  # ms
                times.append(elapsed)

        avg_ms = np.mean(times)
        p50 = np.percentile(times, 50)
        p95 = np.percentile(times, 95)
        p99 = np.percentile(times, 99)

        print(f"\n  Config: {config_name}")
        metric("Mean latency", avg_ms, "ms")
        metric("P50 latency", p50, "ms")
        metric("P95 latency", p95, "ms")
        metric("P99 latency", p99, "ms")

        if avg_ms < 50:
            print(f"    {'[PASS]':>40s}  < 50ms target")
        else:
            print(f"    {'[WARN]':>40s}  > 50ms target ({avg_ms:.1f}ms)")


# ─── Benchmark 5: Stability (1000-tick CV) ────────────────────────────────────

def bench_stability(ticks=1000):
    """1000-tick coefficient of variation per ring."""
    header("5. STABILITY (1000-tick Coefficient of Variation)")

    for config_name, bridges in [
        ("No bridges", None),
        ("All 10 bridges", list(ALL_BRIDGE_FACTORIES.keys())),
    ]:
        net = _make_network(bridges)
        ring_norms = [[] for _ in range(5)]

        with torch.no_grad():
            for _ in range(ticks):
                result = net(torch.randn(1, 384))
                for i, act in enumerate(result["ring_activations"]):
                    ring_norms[i].append(act.norm().item())

        print(f"\n  Config: {config_name}")
        for i in range(5):
            norms = np.array(ring_norms[i])
            mean = norms.mean()
            std = norms.std()
            cv = std / (mean + 1e-12)
            metric(f"Ring {i+1} (mean={mean:.2f}, std={std:.2f})", cv, "CV")

        # Overall stability score (lower = more stable)
        all_cvs = []
        for i in range(5):
            norms = np.array(ring_norms[i])
            cv = norms.std() / (norms.mean() + 1e-12)
            all_cvs.append(cv)
        avg_cv = np.mean(all_cvs)
        metric("Overall avg CV", avg_cv)

        if avg_cv < 0.3:
            print(f"    {'[PASS]':>40s}  CV < 0.3 (stable)")
        elif avg_cv < 0.5:
            print(f"    {'[OK]':>40s}    CV < 0.5 (acceptable)")
        else:
            print(f"    {'[WARN]':>40s}  CV >= 0.5 (variable)")


# ─── Benchmark 6: Modulation Factor Ranges ───────────────────────────────────

def bench_modulation_ranges(ticks=200):
    """Track modulation factor ranges over time."""
    header("6. MODULATION FACTOR RANGES (200 ticks)")

    net = _make_network(list(ALL_BRIDGE_FACTORIES.keys()))
    factors = {"attention_gain": [], "precision_boost": [],
               "ffn_throughput": [], "threshold_mod": []}

    with torch.no_grad():
        for _ in range(ticks):
            result = net(torch.randn(1, 384))
            mod = result["modulation_context"]
            for key in factors:
                factors[key].append(getattr(mod, key))

    for name, vals in factors.items():
        vals = np.array(vals)
        print(f"\n  {name}:")
        metric("Mean", vals.mean())
        metric("Std", vals.std())
        metric("Min", vals.min())
        metric("Max", vals.max())


# ─── Summary Table ────────────────────────────────────────────────────────────

def summary_table():
    """Side-by-side comparison table."""
    header("SUMMARY: BRIDGES-ON vs BRIDGES-OFF")

    configs = [
        ("OFF (0 bridges)", None),
        ("ON  (10 bridges)", list(ALL_BRIDGE_FACTORIES.keys())),
    ]
    ticks = 200
    seeds = [torch.randn(1, 384) for _ in range(ticks)]

    results = {}
    for config_name, bridges in configs:
        net = _make_network(bridges)
        pe_all = []
        ring_entropies = [[] for _ in range(5)]
        ring_norms = [[] for _ in range(5)]
        times = []

        with torch.no_grad():
            for seed in seeds:
                start = time.perf_counter()
                result = net(seed)
                elapsed = (time.perf_counter() - start) * 1000
                times.append(elapsed)
                pe_all.append(np.mean(result["prediction_errors"]))
                for i, act in enumerate(result["ring_activations"]):
                    ring_entropies[i].append(activation_entropy(act))
                    ring_norms[i].append(act.norm().item())

        avg_entropy = np.mean([np.mean(e) for e in ring_entropies])
        avg_pe = np.mean(pe_all)
        pe_first = np.mean(pe_all[:50])
        pe_last = np.mean(pe_all[-50:])
        avg_cv = np.mean([
            np.std(ring_norms[i]) / (np.mean(ring_norms[i]) + 1e-12)
            for i in range(5)
        ])
        avg_latency = np.mean(times)

        results[config_name] = {
            "entropy": avg_entropy,
            "pe_avg": avg_pe,
            "pe_reduction": (pe_first - pe_last) / (pe_first + 1e-12) * 100,
            "cv": avg_cv,
            "latency_ms": avg_latency,
        }

    # Print table
    print()
    print(f"  {'Metric':<35s} {'OFF (0)':<15s} {'ON (10)':<15s} {'Delta':<12s}")
    print(f"  {'-'*35} {'-'*15} {'-'*15} {'-'*12}")

    off = results["OFF (0 bridges)"]
    on = results["ON  (10 bridges)"]

    for label, key, unit, better in [
        ("Avg ring entropy", "entropy", "nats", "higher"),
        ("Avg prediction error", "pe_avg", "", "lower"),
        ("PE reduction (first vs last)", "pe_reduction", "%", "higher"),
        ("Avg CV (stability)", "cv", "", "lower"),
        ("Avg latency", "latency_ms", "ms", "lower"),
    ]:
        v_off = off[key]
        v_on = on[key]
        delta = v_on - v_off
        sign = "+" if delta > 0 else ""
        print(f"  {label:<35s} {v_off:<15.4f} {v_on:<15.4f} {sign}{delta:<11.4f}")

    print()
    lat = on["latency_ms"]
    if lat < 50:
        print(f"  LATENCY TARGET: {lat:.1f}ms < 50ms [PASS]")
    else:
        print(f"  LATENCY TARGET: {lat:.1f}ms >= 50ms [WARN]")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  THE BRAIN — Bridge Benchmark Suite")
    print("=" * 70)

    bench_entropy()
    bench_pe_convergence()
    bench_dual_process()
    bench_latency()
    bench_stability()
    bench_modulation_ranges()
    summary_table()

    print("\n  Benchmark complete.\n")
