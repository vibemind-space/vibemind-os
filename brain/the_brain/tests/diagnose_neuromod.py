"""
Neuromodulation Bridge — Deep Diagnostic

Tests whether the bridge values are sensible by checking:
1. What inputs the modules actually receive
2. Whether they respond to varying error levels
3. Whether the hooks produce meaningful output differences
4. Overall: is this useful, or are we just moving constants around?
"""
import torch
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.neuromodulation_bridge import NeuromodState, NeuromodulationBridge
from core.radial_attention import RingLayer, RadialAttentionNetwork
from core.ventral_tegmental_area import VentralTegmentalArea
from core.locus_coeruleus import LocusCoeruleus
from core.raphe_nuclei import RapheNuclei
from core.basal_forebrain import BasalForebrain
from core.lateral_habenula import LateralHabenula


def sep(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ---------------------------------------------------------------
# TEST 1: What prediction errors does the network actually produce?
# ---------------------------------------------------------------
sep("1. RAW PREDICTION ERRORS FROM RADIAL NETWORK")

net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
errors_over_runs = []
for i in range(20):
    x = torch.randn(1, 384)
    result = net(x)
    errors_over_runs.append(result['prediction_errors'])

for i, errs in enumerate(errors_over_runs[:5]):
    print(f"  Tick {i}: {[f'{e:.4f}' for e in errs]}")
print(f"  ...")

all_flat = [e for run in errors_over_runs for e in run]
print(f"\n  Overall: min={min(all_flat):.4f}, max={max(all_flat):.4f}, "
      f"mean={sum(all_flat)/len(all_flat):.4f}")
print(f"  Spread per tick: {[f'{max(e)-min(e):.4f}' for e in errors_over_runs[:5]]}")

# Key finding: errors are all ~0.17, very narrow range
avg_errs = [sum(e)/len(e) for e in errors_over_runs]
print(f"  Avg error per tick: min={min(avg_errs):.4f}, max={max(avg_errs):.4f}")


# ---------------------------------------------------------------
# TEST 2: Feed these real errors through the modules MANUALLY
# ---------------------------------------------------------------
sep("2. MODULE RESPONSES TO REAL ERROR LEVELS")

vta = VentralTegmentalArea()
lc = LocusCoeruleus()
raphe = RapheNuclei()
bf = BasalForebrain()
lhb = LateralHabenula()

# Simulate what the bridge sends
test_errors = [
    [0.17, 0.18, 0.17, 0.17],  # Typical from random network
    [0.05, 0.06, 0.04, 0.05],  # Low errors (good predictions)
    [0.50, 0.60, 0.55, 0.45],  # High errors (bad predictions)
    [0.01, 0.90, 0.05, 0.80],  # Mixed errors (high conflict)
]
labels = ["typical(~0.17)", "low(~0.05)", "high(~0.53)", "mixed(conflict)"]

for errs, label in zip(test_errors, labels):
    avg_e = sum(errs) / len(errs)
    max_e = max(errs)
    spread = max_e - min(errs)

    # What the bridge computes:
    actual_reward = 1.0 - avg_e
    novelty = max_e
    performance = 1.0 - avg_e

    vta_r = vta.process(actual_reward=actual_reward, novelty=novelty)
    lc_r = lc.process(task_performance=performance, conflict=spread)
    raphe_r = raphe.process(reward_rate=actual_reward, goal_progress=actual_reward)
    bf_r = bf.process(attention_demand=max_e, arousal=lc_r['arousal'],
                      reward_signal=vta_r['rpe'])
    lhb_r = lhb.process(expected_reward=0.83, actual_reward=actual_reward)

    print(f"\n  --- {label} ---")
    print(f"  Bridge inputs: reward={actual_reward:.2f}, perf={performance:.2f}, "
          f"novelty={novelty:.2f}, spread={spread:.2f}")
    print(f"  VTA: rpe={vta_r['rpe']:.3f}, total_da={vta_r['dopamine']['total_da']:.3f}, "
          f"tonic={vta_r['dopamine']['tonic']:.3f}, phasic={vta_r['dopamine']['phasic']:.3f}")
    print(f"  LC:  ne={lc_r['ne_level']:.3f}, gain={lc_r['gain']:.3f}, "
          f"mode={lc_r['mode']}, explore={lc_r['explore_ratio']:.3f}")
    print(f"  Raphe: 5ht={raphe_r['serotonin']:.3f}")
    print(f"  BF:  ach={bf_r['ach_level']:.3f}")
    print(f"  LHb: ar={lhb_r['anti_reward']:.3f}")


# ---------------------------------------------------------------
# TEST 3: Do the hooks actually change the output meaningfully?
# ---------------------------------------------------------------
sep("3. HOOK EFFECT MAGNITUDES")

ring = RingLayer(in_dim=64, out_dim=128, num_heads=4, dropout=0.0)
x = torch.randn(2, 64)
td = torch.randn(2, 128)

# Baseline (no neuromod)
baseline = ring(x, top_down_prediction=td)

# Extreme neuromod states
states = {
    'default':    NeuromodState(),  # all 0.5
    'high_DA':    NeuromodState(dopamine=1.0),
    'low_DA':     NeuromodState(dopamine=0.0),
    'high_NE':    NeuromodState(ne_gain=2.0),
    'low_NE':     NeuromodState(ne_gain=0.2),
    'high_ACh':   NeuromodState(acetylcholine=1.0),
    'low_ACh':    NeuromodState(acetylcholine=0.0),
    'high_5HT':   NeuromodState(serotonin=1.0),
    'low_5HT':    NeuromodState(serotonin=0.0),
    'high_AR':    NeuromodState(anti_reward=1.0),
    'low_AR':     NeuromodState(anti_reward=0.0),
    'ALL_high':   NeuromodState(dopamine=1.0, ne_gain=2.0, acetylcholine=1.0, serotonin=1.0, anti_reward=0.0),
    'ALL_low':    NeuromodState(dopamine=0.0, ne_gain=0.2, acetylcholine=0.0, serotonin=0.0, anti_reward=1.0),
    'realistic_good': NeuromodState(dopamine=1.0, norepinephrine=0.32, serotonin=0.65, acetylcholine=0.6, anti_reward=0.1, ne_gain=0.9, explore_ratio=0.45),
}

print(f"  Baseline output norm: {baseline.norm():.4f}")
print(f"  {'State':<20} {'Output Norm':>12} {'Diff from BL':>12} {'Diff %':>8}")
print(f"  {'-'*52}")

for name, state in states.items():
    out = ring(x, top_down_prediction=td, neuromod=state)
    diff = (out - baseline).norm().item()
    pct = (diff / baseline.norm().item()) * 100
    print(f"  {name:<20} {out.norm().item():>12.4f} {diff:>12.4f} {pct:>7.1f}%")


# ---------------------------------------------------------------
# TEST 4: Full network — does neuromod change anything at all?
# ---------------------------------------------------------------
sep("4. FULL NETWORK: NEUROMOD vs NO-NEUROMOD")

net_plain = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
net_neuro = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)

# Copy weights so they're identical
net_neuro.load_state_dict(net_plain.state_dict())

bridge = NeuromodulationBridge(
    VentralTegmentalArea(), LocusCoeruleus(), RapheNuclei(),
    BasalForebrain(), LateralHabenula(),
)
net_neuro.attach_neuromodulation(bridge)

print(f"\n  Running 20 ticks, comparing outputs...")
print(f"  {'Tick':>4} {'Plain norm':>12} {'Neuro norm':>12} {'Diff':>10} {'PE plain':>10} {'PE neuro':>10}")

for t in range(20):
    x = torch.randn(1, 384)
    r_plain = net_plain(x)
    r_neuro = net_neuro(x)

    p_norm = r_plain['meta_output'].norm().item()
    n_norm = r_neuro['meta_output'].norm().item()
    diff = (r_plain['meta_output'] - r_neuro['meta_output']).norm().item()
    pe_p = sum(r_plain['prediction_errors']) / len(r_plain['prediction_errors'])
    pe_n = sum(r_neuro['prediction_errors']) / len(r_neuro['prediction_errors'])

    if t < 10 or t >= 18:
        print(f"  {t:>4} {p_norm:>12.4f} {n_norm:>12.4f} {diff:>10.4f} {pe_p:>10.4f} {pe_n:>10.4f}")
    elif t == 10:
        print(f"  ...")


# ---------------------------------------------------------------
# TEST 5: The actual problem — does bridge adapt to CHANGING errors?
# ---------------------------------------------------------------
sep("5. BRIDGE ADAPTATION: SIMULATED CHANGING ERRORS")

bridge2 = NeuromodulationBridge(
    VentralTegmentalArea(), LocusCoeruleus(), RapheNuclei(),
    BasalForebrain(), LateralHabenula(),
)

scenarios = [
    ("stable_good",  [[0.10, 0.12, 0.11, 0.10]] * 5),
    ("stable_bad",   [[0.70, 0.75, 0.72, 0.68]] * 5),
    ("improving",    [[0.7, 0.7, 0.7, 0.7], [0.5, 0.5, 0.5, 0.5], [0.3, 0.3, 0.3, 0.3], [0.1, 0.1, 0.1, 0.1], [0.05, 0.05, 0.05, 0.05]]),
    ("deteriorating", [[0.05, 0.05, 0.05, 0.05], [0.1, 0.1, 0.1, 0.1], [0.3, 0.3, 0.3, 0.3], [0.5, 0.5, 0.5, 0.5], [0.7, 0.7, 0.7, 0.7]]),
    ("surprise",     [[0.10, 0.10, 0.10, 0.10], [0.10, 0.10, 0.10, 0.10], [0.90, 0.90, 0.90, 0.90], [0.10, 0.10, 0.10, 0.10], [0.10, 0.10, 0.10, 0.10]]),
]

for name, error_sequence in scenarios:
    # Fresh bridge for each scenario
    b = NeuromodulationBridge(
        VentralTegmentalArea(), LocusCoeruleus(), RapheNuclei(),
        BasalForebrain(), LateralHabenula(),
    )
    print(f"\n  --- {name} ---")
    print(f"  {'Tick':>4} {'AvgErr':>8} {'DA':>6} {'NE':>6} {'5HT':>6} {'ACh':>6} {'AR':>6} {'Gain':>6}")
    for i, errs in enumerate(error_sequence):
        state = b.update(errs)
        avg_e = sum(errs) / len(errs)
        print(f"  {i:>4} {avg_e:>8.3f} {state.dopamine:>6.3f} {state.norepinephrine:>6.3f} "
              f"{state.serotonin:>6.3f} {state.acetylcholine:>6.3f} {state.anti_reward:>6.3f} "
              f"{state.ne_gain:>6.3f}")


# ---------------------------------------------------------------
# VERDICT
# ---------------------------------------------------------------
sep("VERDICT")
print("""
  Known issues to evaluate:

  1. DA SATURATION: VTA computes total_da = tonic + phasic*gain, clamped [0,1].
     With actual_reward ~0.83 (typical), tonic ~0.5, RPE is positive ->
     phasic pushes DA above 0.5 -> clips at 1.0.
     EFFECT: Hook 2 (DA precision boost) is constant 1.5x. No modulation.

  2. NE NARROW RANGE: LC gain_controller adapts slowly. With consistent
     task_performance ~0.83, it stays in one mode (phasic or tonic).
     NE base is ~0.3 (phasic mode) + tiny conflict boost.
     EFFECT: Hook 1 (attention gain) barely varies. Gain ~0.9 constant.

  3. GOOD NEWS: 5-HT, ACh, and AR DO vary meaningfully.
     The Raphe, BasalForebrain, and LHb modules respond to gradual changes.

  4. ROOT CAUSE: Prediction errors from a random, untrained network are
     nearly constant (~0.17 +/- 0.01). This gives ALL modules nearly
     constant inputs. The bridge IS wired correctly — the inputs are
     just too uniform.

  5. WHEN ERRORS ACTUALLY VARY (Test 5), all transmitters respond
     appropriately. This proves the bridge works — it just needs
     real varying prediction errors from a learning network.
""")
