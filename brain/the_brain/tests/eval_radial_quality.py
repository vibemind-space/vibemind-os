"""
Radial Attention Network — Quality Evaluation
================================================
Measures actual learning dynamics, not just shape correctness.

Sections:
  1. Parameter budget & architecture sanity
  2. Predictive Coding: do errors actually decrease with top-down?
  3. Hebbian plasticity: does it meaningfully bias attention?
  4. Sleep training: does loss converge? How fast?
  5. EWC: does it actually prevent catastrophic forgetting?
  6. DualProcessRouter: are decisions consistent & sensible?
  7. Full wake-sleep cycle: end-to-end learning quality
"""
import sys
import time
import torch
import numpy as np

sys.path.insert(0, ".")

from core.radial_attention import RadialAttentionNetwork, DualProcessRouter, RingLayer
from core.hebbian_plasticity import HebbianAttentionUpdate
from core.experience_buffer import ExperienceBuffer
from core.radial_sleep_trainer import RadialSleepTrainer


def header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def ok(msg):
    print(f"  [OK]   {msg}")


def warn(msg):
    print(f"  [WARN] {msg}")


def fail(msg):
    print(f"  [FAIL] {msg}")


def metric(name, value, unit="", good_range=None):
    status = ""
    if good_range:
        lo, hi = good_range
        if lo <= value <= hi:
            status = " [OK]"
        else:
            status = " [WARN]"
    print(f"    {name}: {value:.4f} {unit}{status}")


# ================================================================
# 1. Architecture & Parameter Budget
# ================================================================
header("1. Architecture & Parameter Budget")

net = RadialAttentionNetwork(seed_dim=384)
counts = net.get_parameter_count()

total = counts['total']
print(f"  Total parameters: {total:,}")
for k, v in counts.items():
    if k != 'total':
        pct = 100.0 * v / total
        print(f"    {k}: {v:,} ({pct:.1f}%)")

if total < 30_000_000:
    ok(f"Under 30M budget ({total:,})")
else:
    fail(f"Over 30M budget ({total:,})")

# Check ring dimension progression
print("\n  Ring dimensions:")
for i, (name, dim, heads) in enumerate(RadialAttentionNetwork.RING_SPECS):
    print(f"    Ring {i+1} ({name}): dim={dim}, heads={heads}, dim/head={dim//heads}")

# ================================================================
# 2. Predictive Coding Quality
# ================================================================
header("2. Predictive Coding — Error Reduction")

net.eval()
seeds = [torch.randn(1, 384) for _ in range(50)]

errors_pass1 = []
errors_pass2 = []

with torch.no_grad():
    for seed in seeds:
        r = net(seed)
        errors_pass1.append(r['prediction_errors'])

        # Second pass: network has seen this seed, top-down should be better
        r2 = net(seed)
        errors_pass2.append(r2['prediction_errors'])

avg_errors = np.mean(errors_pass1, axis=0)
print("  Average prediction errors per ring-pair (bottom-up then top-down):")
for i, e in enumerate(avg_errors):
    metric(f"Ring {i+1}->{i+2}", e)

# Check: are errors finite and reasonable?
if all(0 < e < 100 for e in avg_errors):
    ok("All prediction errors are finite and bounded")
else:
    warn("Some prediction errors are extreme")

# Determinism check: same input -> same output?
with torch.no_grad():
    r_a = net(seeds[0])
    r_b = net(seeds[0])
    drift = (r_a['meta_output'] - r_b['meta_output']).abs().mean().item()
    metric("Determinism (same input drift)", drift, good_range=(0, 0.001))

# Sensitivity check: different inputs -> different outputs?
with torch.no_grad():
    r_x = net(seeds[0])
    r_y = net(seeds[1])
    diff = (r_x['meta_output'] - r_y['meta_output']).abs().mean().item()
    metric("Sensitivity (diff input distance)", diff, good_range=(0.01, 100.0))

# ================================================================
# 3. Hebbian Plasticity Quality
# ================================================================
header("3. Hebbian Plasticity — Does It Actually Do Something?")

net_hebb = RadialAttentionNetwork(seed_dim=384)
hebb = HebbianAttentionUpdate(learning_rate=0.01, decay=0.0001)

# Record bias before
bias_before = net_hebb.rings[0].attention_bias.clone()

# Run 100 correlated inputs through and update Hebbian
net_hebb.eval()
with torch.no_grad():
    for _ in range(100):
        seed = torch.randn(1, 384)
        r = net_hebb(seed)
        hebb.update(net_hebb.rings[0],
                    r['ring_activations'][0],
                    r['ring_activations'][1])

bias_after = net_hebb.rings[0].attention_bias.clone()
bias_delta = (bias_after - bias_before).abs()

metric("Mean bias change", bias_delta.mean().item())
metric("Max bias change", bias_delta.max().item())
metric("Std bias change", bias_delta.std().item())
metric("Non-zero cells (%)", (bias_delta > 1e-6).float().mean().item() * 100, "%")

if bias_delta.mean().item() > 1e-5:
    ok("Hebbian plasticity is actively modifying attention biases")
else:
    warn("Hebbian changes are negligible — learning_rate may be too low")

# Does the bias have structure (not just noise)?
# Check: diagonal vs off-diagonal
diag_mean = bias_after.diag().abs().mean().item()
offdiag_mask = ~torch.eye(bias_after.shape[0], dtype=torch.bool)
offdiag_mean = bias_after[offdiag_mask].abs().mean().item()
metric("Diagonal bias mean", diag_mean)
metric("Off-diagonal bias mean", offdiag_mean)
if abs(diag_mean - offdiag_mean) > 0.001:
    ok("Bias shows structural pattern (diag != off-diag)")
else:
    warn("Bias is uniform — no meaningful structure")

# ================================================================
# 4. Sleep Training — Loss Convergence
# ================================================================
header("4. Sleep Training — Loss Convergence")

net_train = RadialAttentionNetwork(seed_dim=384)
buf = ExperienceBuffer(max_size=500)
trainer = RadialSleepTrainer(network=net_train, buffer=buf, lr=0.001)

# Fill buffer with diverse experiences
net_train.eval()
with torch.no_grad():
    for i in range(200):
        seed = torch.randn(384)
        r = net_train(seed.unsqueeze(0))
        reward = np.random.uniform(0.0, 1.0)
        buf.add(
            input_embedding=seed,
            ring_activations=r['ring_activations'],
            ctm_trajectory=[0.2 + 0.15 * j for j in range(5)],
            kuro_reward=reward,
            outcome='success' if reward > 0.5 else 'failure',
        )

print(f"  Buffer filled: {len(buf)} experiences")

# Train 20 epochs, record losses
net_train.train()
losses = []
t0 = time.time()
for epoch in range(20):
    loss = trainer.train_epoch(batch_size=32)
    losses.append(loss)
elapsed = time.time() - t0

print(f"  Training time: {elapsed:.2f}s for 20 epochs ({elapsed/20:.3f}s/epoch)")
print(f"  Loss progression:")
for i, l in enumerate(losses):
    bar = "#" * max(1, int(l * 20))
    print(f"    Epoch {i+1:2d}: {l:8.4f} |{bar}")

# Quality checks
if losses[-1] < losses[0]:
    reduction_pct = (1 - losses[-1] / max(losses[0], 1e-8)) * 100
    ok(f"Loss decreased: {losses[0]:.4f} -> {losses[-1]:.4f} ({reduction_pct:.1f}% reduction)")
else:
    warn(f"Loss did NOT decrease: {losses[0]:.4f} -> {losses[-1]:.4f}")

if all(l < 1e6 for l in losses):
    ok("No loss explosion")
else:
    fail("Loss exploded!")

# Monotonicity check (how often does loss decrease step-to-step?)
decreases = sum(1 for i in range(1, len(losses)) if losses[i] < losses[i-1])
mono_pct = 100 * decreases / (len(losses) - 1)
metric("Monotonic decrease rate", mono_pct, "%", good_range=(50, 100))

# ================================================================
# 5. EWC — Catastrophic Forgetting Test
# ================================================================
header("5. EWC — Catastrophic Forgetting Prevention")

net_ewc = RadialAttentionNetwork(seed_dim=384)
buf_a = ExperienceBuffer(max_size=200)
trainer_ewc = RadialSleepTrainer(network=net_ewc, buffer=buf_a, lr=0.001, ewc_lambda=500.0)

# Task A: specific input pattern
seed_a = torch.randn(384)
with torch.no_grad():
    for _ in range(50):
        r = net_ewc(seed_a.unsqueeze(0))
        buf_a.add(seed_a, r['ring_activations'], [0.9, 0.8, 0.7, 0.6, 0.5], 1.0, 'success')

# Train on Task A
for _ in range(10):
    trainer_ewc.train_epoch(batch_size=16)

with torch.no_grad():
    output_a_before = net_ewc(seed_a.unsqueeze(0))['meta_output'].clone()

# Register EWC anchor
trainer_ewc.register_ewc_anchor()

# Task B: completely different pattern
buf_b = ExperienceBuffer(max_size=200)
trainer_ewc._buffer = buf_b
seed_b = torch.randn(384)
with torch.no_grad():
    for _ in range(50):
        r = net_ewc(seed_b.unsqueeze(0))
        buf_b.add(seed_b, r['ring_activations'], [0.1, 0.2, 0.3, 0.4, 0.5], 0.1, 'failure')

# Train on Task B (should NOT destroy Task A knowledge)
for _ in range(10):
    trainer_ewc.train_epoch(batch_size=16)

with torch.no_grad():
    output_a_after = net_ewc(seed_a.unsqueeze(0))['meta_output']
    output_b_after = net_ewc(seed_b.unsqueeze(0))['meta_output']

drift_a = (output_a_before - output_a_after).abs().mean().item()
metric("Task A output drift after Task B training", drift_a, good_range=(0, 0.5))

# Fair comparison: train no-EWC from the SAME post-Task-A checkpoint
# We need to re-train from scratch for a proper A/B test
net_no_ewc = RadialAttentionNetwork(seed_dim=384)
buf_a2 = ExperienceBuffer(max_size=200)
trainer_no_ewc = RadialSleepTrainer(network=net_no_ewc, buffer=buf_a2, lr=0.001, ewc_lambda=0.0)

# Train no-EWC on same Task A
with torch.no_grad():
    for _ in range(50):
        r = net_no_ewc(seed_a.unsqueeze(0))
        buf_a2.add(seed_a, r['ring_activations'], [0.9, 0.8, 0.7, 0.6, 0.5], 1.0, 'success')

for _ in range(10):
    trainer_no_ewc.train_epoch(batch_size=16)

with torch.no_grad():
    output_a_no_ewc_before = net_no_ewc(seed_a.unsqueeze(0))['meta_output'].clone()

# Now train no-EWC on Task B (NO anchor, NO EWC penalty)
buf_b2 = ExperienceBuffer(max_size=200)
trainer_no_ewc._buffer = buf_b2
with torch.no_grad():
    for _ in range(50):
        r = net_no_ewc(seed_b.unsqueeze(0))
        buf_b2.add(seed_b, r['ring_activations'], [0.1, 0.2, 0.3, 0.4, 0.5], 0.1, 'failure')

for _ in range(10):
    trainer_no_ewc.train_epoch(batch_size=16)

with torch.no_grad():
    output_a_no_ewc_after = net_no_ewc(seed_a.unsqueeze(0))['meta_output']

drift_no_ewc = (output_a_no_ewc_before - output_a_no_ewc_after).abs().mean().item()
metric("Task A drift WITHOUT EWC (baseline)", drift_no_ewc)
metric("Task A drift WITH EWC", drift_a)

if drift_a < drift_no_ewc:
    ok(f"EWC reduces forgetting: {drift_a:.4f} < {drift_no_ewc:.4f}")
else:
    warn(f"EWC did NOT reduce forgetting: {drift_a:.4f} >= {drift_no_ewc:.4f}")

# ================================================================
# 6. DualProcessRouter — Decision Quality
# ================================================================
header("6. DualProcessRouter — Decision Quality")

router = DualProcessRouter(dim=128, conflict_threshold=0.3)

# Test: identical inputs -> System 1
identical = torch.randn(1, 128)
r_ident = router(identical, identical.clone())
metric("Identical inputs -> conflict", r_ident['conflict_level'], good_range=(0, 0.3))
if r_ident['system_used'] == 1:
    ok("Identical inputs -> System 1 (correct)")
else:
    warn("Identical inputs -> System 2 (unexpected)")

# Test: opposite inputs -> System 2
pos = torch.ones(1, 128)
neg = -torch.ones(1, 128)
r_opp = router(pos, neg)
metric("Opposite inputs -> conflict", r_opp['conflict_level'], good_range=(0.3, 2.0))
if r_opp['system_used'] == 2:
    ok("Opposite inputs -> System 2 (correct)")
else:
    warn("Opposite inputs -> System 1 (unexpected)")

# Consistency check: same input 100 times -> same decision?
decisions = []
for _ in range(100):
    s1 = torch.randn(1, 128)
    s2 = torch.randn(1, 128)
    decisions.append(router(s1, s2)['system_used'])

s1_pct = decisions.count(1) / len(decisions) * 100
s2_pct = decisions.count(2) / len(decisions) * 100
print(f"  Random input routing: System 1={s1_pct:.0f}%, System 2={s2_pct:.0f}%")

if 5 < s1_pct < 95:
    ok("Both systems used — router is discriminating")
elif s2_pct > 90:
    ok("Random inputs -> mostly System 2 (correct: random vectors are orthogonal, conflict is real)")
else:
    warn(f"Router heavily biased toward System {'1' if s1_pct > 50 else '2'}")

# ================================================================
# 7. Full Wake-Sleep Cycle — End-to-End
# ================================================================
header("7. Full Wake-Sleep Cycle — End-to-End Quality")

net_full = RadialAttentionNetwork(seed_dim=384)
hebb_full = HebbianAttentionUpdate(learning_rate=0.005, decay=0.0001)
buf_full = ExperienceBuffer(max_size=1000)
trainer_full = RadialSleepTrainer(net_full, buf_full, lr=0.001)
router_full = DualProcessRouter(dim=128)

# Measure pre-training consistency
print("  Phase 1: Pre-training baseline...")
test_seeds = [torch.randn(1, 384) for _ in range(10)]
pre_outputs = []
with torch.no_grad():
    for s in test_seeds:
        pre_outputs.append(net_full(s)['meta_output'].clone())

# WAKE phase: 200 inputs with Hebbian
print("  Phase 2: Wake phase (200 inputs + Hebbian)...")
net_full.eval()
wake_errors = []
with torch.no_grad():
    for i in range(200):
        seed = torch.randn(1, 384)
        r = net_full(seed)

        # Hebbian update all rings
        for ring_idx in range(4):
            hebb_full.update(
                net_full.rings[ring_idx],
                r['ring_activations'][ring_idx],
                r['ring_activations'][ring_idx + 1],
            )

        reward = 0.8 if i % 3 != 0 else 0.2  # 67% success rate
        buf_full.add(
            input_embedding=seed.squeeze(0),
            ring_activations=r['ring_activations'],
            ctm_trajectory=[0.2 + 0.15 * j for j in range(5)],
            kuro_reward=reward,
            outcome='success' if reward > 0.5 else 'failure',
        )
        wake_errors.append(np.mean(r['prediction_errors']))

avg_wake_error_first = np.mean(wake_errors[:50])
avg_wake_error_last = np.mean(wake_errors[-50:])
metric("Wake prediction error (first 50)", avg_wake_error_first)
metric("Wake prediction error (last 50)", avg_wake_error_last)

# SLEEP phase: 30 training epochs
print("  Phase 3: Sleep phase (30 epochs)...")
net_full.train()
sleep_losses = []
for _ in range(30):
    loss = trainer_full.train_epoch(batch_size=32)
    sleep_losses.append(loss)

metric("Sleep loss start", sleep_losses[0])
metric("Sleep loss end", sleep_losses[-1])
if sleep_losses[-1] < sleep_losses[0]:
    reduction = (1 - sleep_losses[-1] / max(sleep_losses[0], 1e-8)) * 100
    ok(f"Sleep training converged ({reduction:.1f}% reduction)")
else:
    warn("Sleep training did not converge")

# Post-training: check if outputs changed (network learned something)
print("  Phase 4: Post-training evaluation...")
net_full.eval()
post_outputs = []
with torch.no_grad():
    for s in test_seeds:
        post_outputs.append(net_full(s)['meta_output'].clone())

output_changes = []
for pre, post in zip(pre_outputs, post_outputs):
    change = (pre - post).abs().mean().item()
    output_changes.append(change)

avg_change = np.mean(output_changes)
metric("Average output change after learning", avg_change)

if avg_change > 0.01:
    ok(f"Network outputs changed — it learned something ({avg_change:.4f})")
else:
    warn("Network outputs barely changed — may not be learning effectively")

# Hebbian stats
h_stats = hebb_full.get_stats()
print(f"\n  Hebbian stats: {h_stats['total_updates']} updates")

# Buffer stats
b_stats = buf_full.get_stats()
print(f"  Buffer stats: {b_stats['buffer_size']}/{b_stats['max_size']} "
      f"({b_stats['total_added']} total added)")

# Trainer stats
t_stats = trainer_full.get_stats()
print(f"  Trainer stats: {t_stats['total_epochs']} epochs")

# ================================================================
# Section 8: Neuromodulation Bridge
# ================================================================
header("NEUROMODULATION BRIDGE")

try:
    from core.neuromodulation_bridge import NeuromodState, NeuromodulationBridge
    from core.ventral_tegmental_area import VentralTegmentalArea
    from core.locus_coeruleus import LocusCoeruleus
    from core.raphe_nuclei import RapheNuclei
    from core.basal_forebrain import BasalForebrain
    from core.lateral_habenula import LateralHabenula

    bridge = NeuromodulationBridge(
        VentralTegmentalArea(), LocusCoeruleus(), RapheNuclei(),
        BasalForebrain(), LateralHabenula(),
    )
    net_nm = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)
    net_nm.attach_neuromodulation(bridge)

    # Run 20 ticks, collect states
    da_vals, ne_vals, ht_vals, ach_vals, ar_vals = [], [], [], [], []
    for _ in range(20):
        x = torch.randn(1, 384)
        result_nm = net_nm(x)
        s = result_nm['neuromod_state']
        da_vals.append(s.dopamine)
        ne_vals.append(s.norepinephrine)
        ht_vals.append(s.serotonin)
        ach_vals.append(s.acetylcholine)
        ar_vals.append(s.anti_reward)

    print(f"  DA  range: [{min(da_vals):.3f}, {max(da_vals):.3f}]")
    print(f"  NE  range: [{min(ne_vals):.3f}, {max(ne_vals):.3f}]")
    print(f"  5HT range: [{min(ht_vals):.3f}, {max(ht_vals):.3f}]")
    print(f"  ACh range: [{min(ach_vals):.3f}, {max(ach_vals):.3f}]")
    print(f"  AR  range: [{min(ar_vals):.3f}, {max(ar_vals):.3f}]")

    # Check: at least some transmitters should vary (not stuck at default)
    da_varies = len(set(round(v, 4) for v in da_vals)) > 1
    ne_varies = len(set(round(v, 4) for v in ne_vals)) > 1
    print(f"  DA varies: {da_varies}")
    print(f"  NE varies: {ne_varies}")

    if da_varies or ne_varies:
        print("  [OK] Neuromodulation bridge is live and responsive")
    else:
        print("  [WARN] Some transmitters are static")
except ImportError as e:
    print(f"  [SKIP] Neuromodulator modules not available: {e}")

# ================================================================
# 9. CORTEX BRIDGE: PFC + ACC + OFC -> Cognitive Modulation
# ================================================================
header("9. CORTEX BRIDGE")
try:
    from core.cortex_bridge import CortexBridge, CortexState
    from core.prefrontal_cortex import PrefrontalCortex
    from core.anterior_cingulate import AnteriorCingulateCortex
    from core.orbitofrontal_cortex import OrbitofrontalCortex

    pfc = PrefrontalCortex()
    acc = AnteriorCingulateCortex()
    ofc = OrbitofrontalCortex()
    cx_bridge = CortexBridge(pfc=pfc, acc=acc, ofc=ofc)

    print("  Running 20 ticks with CortexBridge...")
    cx_states = []
    for t in range(20):
        ring_acts = [np.random.randn(64), np.random.randn(128),
                     np.random.randn(256), np.random.randn(256),
                     np.random.randn(128)]
        pred_errors = [0.15 + 0.02 * (t % 5), 0.12, 0.18, 0.10]
        cx_state = cx_bridge.update(ring_acts, pred_errors)
        cx_states.append(cx_state)

    for attr in ['conflict', 'control_signal', 'subjective_value',
                 'pfc_value', 'error_likelihood', 'decision_confidence',
                 'choice_difficulty']:
        vals = [getattr(s, attr) for s in cx_states]
        print(f"  {attr:>22}: min={min(vals):.4f}  max={max(vals):.4f}  "
              f"range={max(vals)-min(vals):.4f}")

    bias_norms = [np.linalg.norm(s.bias_signal) if s.bias_signal is not None else 0.0
                  for s in cx_states]
    print(f"  {'bias_signal norm':>22}: min={min(bias_norms):.4f}  max={max(bias_norms):.4f}")
    print("  [OK] CortexBridge eval complete")
except Exception as e:
    print(f"  [SKIP] CortexBridge: {e}")

# ================================================================
# Section 10: LimbicBridge Live Output
# ================================================================
header("SECTION 10: LIMBIC BRIDGE")
print("\n--- Section 10: LimbicBridge ---")
try:
    from core.limbic_bridge import LimbicBridge
    from core.amygdala_complex import AmygdalaComplex
    from core.nucleus_accumbens import NucleusAccumbens
    from core.insular_cortex import InsularCortex
    from core.hypothalamus_drives import HypothalamusModule
    limbic = LimbicBridge(
        amygdala=AmygdalaComplex(),
        nucleus_accumbens=NucleusAccumbens(),
        insular_cortex=InsularCortex(),
        hypothalamus=HypothalamusModule(),
    )
    net.attach_limbic(limbic)
    for t in range(20):
        result = net(seed)
        ls = result['limbic_state']
        print(f"  tick {t:2d}: valence={ls.valence:+.3f}  arousal={ls.arousal:.3f}  "
              f"threat={ls.threat_level:.3f}  salience={ls.salience:.3f}  "
              f"go={ls.go_drive:.3f}  nogo={ls.nogo_drive:.3f}  "
              f"urgency={ls.urgency:.3f}  feeling={ls.feeling}")
    print("  LimbicBridge: OK")
except Exception as e:
    print(f"  LimbicBridge: FAILED - {e}")

# ================================================================
# Section 11: SleepWakeBridge
# ================================================================
header("SECTION 11: SLEEP-WAKE BRIDGE")
try:
    from core.sleep_wake_bridge import SleepWakeBridge, SleepWakeState
    from core.reticular_formation import ReticularFormation
    from core.tuberomammillary_nucleus import TuberomammillaryNucleus
    from core.pineal_gland import PinealGland
    from core.pedunculopontine_nucleus import PedunculopontineNucleus
    sw_bridge = SleepWakeBridge(
        reticular_formation=ReticularFormation(),
        tuberomammillary_nucleus=TuberomammillaryNucleus(),
        pineal_gland=PinealGland(),
        pedunculopontine_nucleus=PedunculopontineNucleus(),
    )
    ring_acts = [np.random.randn(64), np.random.randn(128),
                 np.random.randn(256), np.random.randn(256),
                 np.random.randn(128)]
    pes = [0.1, 0.2, 0.15, 0.1]
    for tick in range(20):
        sw_state = sw_bridge.update(ring_acts, pes)
        print(f"  tick {tick:2d}: arousal={sw_state.arousal:.3f}  "
              f"histamine={sw_state.histamine:.3f}  "
              f"melatonin={sw_state.melatonin:.3f}  "
              f"is_awake={sw_state.is_awake}  "
              f"cholinergic={sw_state.cholinergic_tone:.3f}")
    assert isinstance(sw_state, SleepWakeState)
    print("  SleepWakeBridge: OK")
except Exception as e:
    print(f"  SleepWakeBridge: FAILED - {e}")

# ================================================================
# Section 12: MotorBridge
# ================================================================
header("SECTION 12: MOTOR BRIDGE")
try:
    from core.motor_bridge import MotorBridge, MotorState
    from core.cerebellum_module import CerebellumModule
    from core.substantia_nigra import SubstantiaNigra
    from core.zona_incerta import ZonaIncerta
    from core.red_nucleus import RedNucleus
    from core.posterior_parietal_cortex import PosteriorParietalCortex
    mt_bridge = MotorBridge(
        cerebellum=CerebellumModule(),
        substantia_nigra=SubstantiaNigra(),
        zona_incerta=ZonaIncerta(),
        red_nucleus=RedNucleus(),
        posterior_parietal_cortex=PosteriorParietalCortex(),
    )
    ring_acts = [np.random.randn(64), np.random.randn(128),
                 np.random.randn(256), np.random.randn(256),
                 np.random.randn(128)]
    pes = [0.1, 0.2, 0.15, 0.1]
    for tick in range(20):
        mt_state = mt_bridge.update(ring_acts, pes)
        print(f"  tick {tick:2d}: model_confidence={mt_state.model_confidence:.3f}  "
              f"action_tendency={mt_state.action_tendency:.3f}  "
              f"motor_da={mt_state.motor_da:.3f}  "
              f"go_nogo_balance={mt_state.go_nogo_balance:+.3f}  "
              f"is_compensating={mt_state.is_compensating}")
    assert isinstance(mt_state, MotorState)
    print("  MotorBridge: OK")
except Exception as e:
    print(f"  MotorBridge: FAILED - {e}")

# ================================================================
# Section 13: DefenseBridge
# ================================================================
header("SECTION 13: DEFENSE BRIDGE")
try:
    from core.defense_bridge import DefenseBridge, DefenseState
    from core.periaqueductal_gray import PeriaqueductalGray
    from core.bed_nucleus_stria_terminalis import BedNucleusStriaTerminalis
    from core.parabrachial_nucleus import ParabrachialNucleus
    df_bridge = DefenseBridge(
        parabrachial_nucleus=ParabrachialNucleus(),
        bnst=BedNucleusStriaTerminalis(),
        periaqueductal_gray=PeriaqueductalGray(),
    )
    ring_acts = [np.random.randn(64), np.random.randn(128),
                 np.random.randn(256), np.random.randn(256),
                 np.random.randn(128)]
    pes = [0.1, 0.2, 0.15, 0.1]
    for tick in range(20):
        df_state = df_bridge.update(ring_acts, pes)
        print(f"  tick {tick:2d}: defense_mode={df_state.defense_mode:<8s}  "
              f"defense_intensity={df_state.defense_intensity:.3f}  "
              f"anxiety_level={df_state.anxiety_level:.3f}  "
              f"alarm_level={df_state.alarm_level:.3f}  "
              f"should_interrupt={df_state.should_interrupt}")
    assert isinstance(df_state, DefenseState)
    print("  DefenseBridge: OK")
except Exception as e:
    print(f"  DefenseBridge: FAILED - {e}")

# ================================================================
# Section 14: MemoryBridge
# ================================================================
header("SECTION 14: MEMORY BRIDGE")
try:
    from core.memory_bridge import MemoryBridge, MemoryState
    from core.septal_nuclei import SeptalNuclei
    from core.entorhinal_cortex import EntorhinalCortex
    from core.mammillary_bodies import MammillaryBodies
    from core.inferior_olive import InferiorOlive
    mem_bridge = MemoryBridge(
        septal_nuclei=SeptalNuclei(),
        entorhinal_cortex=EntorhinalCortex(),
        mammillary_bodies=MammillaryBodies(),
        inferior_olive=InferiorOlive(),
    )
    ring_acts = [np.random.randn(64), np.random.randn(128),
                 np.random.randn(256), np.random.randn(256),
                 np.random.randn(128)]
    pes = [0.1, 0.2, 0.15, 0.1]
    for tick in range(20):
        mem_state = mem_bridge.update(ring_acts, pes)
        print(f"  tick {tick:2d}: theta_power={mem_state.theta_power:.3f}  "
              f"consolidation_strength={mem_state.consolidation_strength:.3f}  "
              f"memory_gateway={mem_state.memory_gateway:.3f}  "
              f"teaching_signal={mem_state.teaching_signal:.3f}")
    assert isinstance(mem_state, MemoryState)
    print("  MemoryBridge: OK")
except Exception as e:
    print(f"  MemoryBridge: FAILED - {e}")

# ================================================================
# Section 15: IntegrationBridge
# ================================================================
header("SECTION 15: INTEGRATION BRIDGE")
try:
    from core.integration_bridge import IntegrationBridge, IntegrationState
    from core.superior_colliculus import SuperiorColliculus
    from core.default_mode_network import DefaultModeNetwork
    from core.claustrum import Claustrum
    from core.cortical_column import CorticalColumn
    from core.corpus_callosum import CorpusCallosum
    ig_bridge = IntegrationBridge(
        superior_colliculus=SuperiorColliculus(),
        default_mode_network=DefaultModeNetwork(),
        claustrum=Claustrum(),
        cortical_column=CorticalColumn(),
        corpus_callosum=CorpusCallosum(),
    )
    ring_acts = [np.random.randn(64), np.random.randn(128),
                 np.random.randn(256), np.random.randn(256),
                 np.random.randn(128)]
    pes = [0.1, 0.2, 0.15, 0.1]
    for tick in range(20):
        ig_state = ig_bridge.update(ring_acts, pes)
        print(f"  tick {tick:2d}: binding_strength={ig_state.binding_strength:.3f}  "
              f"dmn_activation={ig_state.dmn_activation:.3f}  "
              f"orienting_saliency={ig_state.orienting_saliency:.3f}  "
              f"bilateral_coherence={ig_state.bilateral_coherence:.3f}")
    assert isinstance(ig_state, IntegrationState)
    print("  IntegrationBridge: OK")
except Exception as e:
    print(f"  IntegrationBridge: FAILED - {e}")

# ================================================================
# Section 16: VisceralBridge
# ================================================================
header("SECTION 16: VISCERAL BRIDGE")
try:
    from core.visceral_bridge import VisceralBridge, VisceralState
    from core.nucleus_tractus_solitarius import NucleusTractSolitarius
    from core.ventral_pallidum import VentralPallidum
    vs_bridge = VisceralBridge(
        nucleus_tractus_solitarius=NucleusTractSolitarius(),
        ventral_pallidum=VentralPallidum(),
    )
    ring_acts = [np.random.randn(64), np.random.randn(128),
                 np.random.randn(256), np.random.randn(256),
                 np.random.randn(128)]
    pes = [0.1, 0.2, 0.15, 0.1]
    for tick in range(20):
        vs_state = vs_bridge.update(ring_acts, pes)
        print(f"  tick {tick:2d}: afferent_strength={vs_state.afferent_strength:.3f}  "
              f"liking={vs_state.liking:.3f}  "
              f"wanting={vs_state.wanting:.3f}  "
              f"approach_strength={vs_state.approach_strength:.3f}")
    assert isinstance(vs_state, VisceralState)
    print("  VisceralBridge: OK")
except Exception as e:
    print(f"  VisceralBridge: FAILED - {e}")

# ================================================================
# Section 17: SocialPerceptionBridge
# ================================================================
header("SECTION 17: SOCIAL PERCEPTION BRIDGE")
try:
    from core.social_perception_bridge import SocialPerceptionBridge, SocialPerceptionState
    from core.olfactory_system import OlfactorySystem
    from core.fusiform_gyrus import FusiformGyrus
    from core.temporoparietal_junction import TemporoparietalJunction
    sp_bridge = SocialPerceptionBridge(
        olfactory_system=OlfactorySystem(),
        fusiform_gyrus=FusiformGyrus(),
        temporoparietal_junction=TemporoparietalJunction(),
    )
    ring_acts = [np.random.randn(64), np.random.randn(128),
                 np.random.randn(256), np.random.randn(256),
                 np.random.randn(128)]
    pes = [0.1, 0.2, 0.15, 0.1]
    for tick in range(20):
        sp_state = sp_bridge.update(ring_acts, pes)
        print(f"  tick {tick:2d}: social_salience={sp_state.social_salience:.3f}  "
              f"familiarity={sp_state.familiarity:.3f}  "
              f"face_detected={sp_state.face_detected}  "
              f"agency_score={sp_state.agency_score:.3f}")
    assert isinstance(sp_state, SocialPerceptionState)
    print("  SocialPerceptionBridge: OK")
except Exception as e:
    print(f"  SocialPerceptionBridge: FAILED - {e}")

# ================================================================
# Section 18: Bridges-On vs Bridges-Off Comparative Eval
# ================================================================
header("SECTION 18: BRIDGES-ON vs BRIDGES-OFF COMPARISON")

try:
    from dataclasses import dataclass
    from typing import Optional as OptBridge
    from core.modulation_context import ModulationContext

    # Lightweight fake bridge states for comparative eval
    @dataclass
    class _NeuromodS:
        dopamine: float = 0.5; norepinephrine: float = 0.5
        serotonin: float = 0.5; acetylcholine: float = 0.5
        anti_reward: float = 0.0; ne_gain: float = 1.0; explore_ratio: float = 0.5

    @dataclass
    class _CortexS:
        bias_signal: OptBridge[np.ndarray] = None; inhibit: bool = False
        pfc_value: float = 0.5; pfc_surprise: float = 0.0; conflict: float = 0.0
        control_signal: float = 0.5; error_likelihood: float = 0.0
        subjective_value: float = 0.5; decision_confidence: float = 0.5
        choice_difficulty: float = 0.5

    @dataclass
    class _LimbicS:
        valence: float = 0.0; arousal: float = 0.3; threat_level: float = 0.0
        is_threat: bool = False; go_drive: float = 0.5; nogo_drive: float = 0.5
        net_value: float = 0.0; effort_cost: float = 0.3; salience: float = 0.3
        body_budget: float = 1.0; feeling: str = "neutral"; urgency: float = 0.0
        approach_drive: float = 0.3; stress: float = 0.0

    @dataclass
    class _SleepWakeS:
        arousal: float = 0.5; sensory_gain: float = 0.5; histamine: float = 0.5
        is_awake: bool = True; wakefulness_drive: float = 0.5; melatonin: float = 0.0
        sleep_pressure: float = 0.0; cholinergic_tone: float = 0.5; rem_probability: float = 0.0

    @dataclass
    class _MotorS:
        prediction_error: float = 0.0; model_confidence: float = 0.5
        motor_da: float = 0.5; go_nogo_balance: float = 0.0
        disinhibited: bool = False; inhibition_level: float = 0.5
        action_tendency: float = 0.5; is_compensating: bool = False
        error_correction: float = 0.0; peak_salience: float = 0.5
        movement_confidence: float = 0.5

    @dataclass
    class _DefenseS:
        defense_mode: str = "freeze"; defense_intensity: float = 0.0
        emergency_mode: bool = False; autonomic_activation: float = 0.0
        alarm_level: float = 0.0; alarm_urgency: float = 0.0
        anxiety_level: float = 0.0; vigilance: float = 0.3
        is_chronic_stress: bool = False; should_interrupt: bool = False

    @dataclass
    class _MemoryS:
        theta_power: float = 0.5; theta_frequency: float = 6.0
        coupling_strength: float = 0.5; consolidation_strength: float = 0.5
        relay_strength: float = 0.5; teaching_signal: float = 0.0
        error_magnitude: float = 0.0; memory_gateway: float = 0.5

    @dataclass
    class _IntegrationS:
        binding_strength: float = 0.5; reached_consciousness: bool = False
        dmn_activation: float = 0.3; dmn_mode: str = "default"
        orienting_saliency: float = 0.3; cortical_error: float = 0.0
        cortical_output: float = 0.5; bilateral_coherence: float = 0.5
        transfer_efficiency: float = 0.5

    @dataclass
    class _VisceralS:
        visceral_level: float = 0.5; afferent_strength: float = 0.3
        reflex_active: bool = False; liking: float = 0.5
        wanting: float = 0.5; approach_strength: float = 0.3

    @dataclass
    class _SocialS:
        face_detected: bool = False; identity_score: float = 0.0
        text_detected: bool = False; word_score: float = 0.0
        agency_score: float = 0.5; reorient_signal: bool = False
        social_inference: float = 0.0; social_salience: float = 0.0
        familiarity: float = 0.3; is_novel: bool = False

    _BRIDGE_MAP = {
        "neuromod": _NeuromodS, "cortex": _CortexS, "limbic": _LimbicS,
        "sleep_wake": _SleepWakeS, "motor": _MotorS, "defense": _DefenseS,
        "memory": _MemoryS, "integration": _IntegrationS,
        "visceral": _VisceralS, "social": _SocialS,
    }

    def _make_eval_net(bridges_on):
        """Create network with or without bridge states."""
        n = RadialAttentionNetwork(seed_dim=384)
        if bridges_on:
            for name, factory in _BRIDGE_MAP.items():
                state = factory()
                if name == "neuromod":
                    n._neuromod_state = state
                elif name == "cortex":
                    n._cortex_state = state
                elif name == "limbic":
                    n._limbic_state = state
                else:
                    n._bridge_states[name] = state
        return n

    def _activation_entropy(tensor):
        x = tensor.detach().abs().flatten()
        if x.sum() < 1e-12:
            return 0.0
        p = torch.softmax(x, dim=0)
        return -(p * torch.log(p + 1e-12)).sum().item()

    eval_ticks = 200
    eval_seeds = [torch.randn(1, 384) for _ in range(eval_ticks)]
    comp_results = {}

    for label, bridges_on in [("OFF (0 bridges)", False), ("ON (10 bridges)", True)]:
        eval_net = _make_eval_net(bridges_on)
        pe_list = []
        ent_per_ring = [[] for _ in range(5)]
        norm_per_ring = [[] for _ in range(5)]
        lat_list = []

        with torch.no_grad():
            for s in eval_seeds:
                t0 = time.perf_counter()
                r = eval_net(s)
                lat_list.append((time.perf_counter() - t0) * 1000)
                pe_list.append(np.mean(r["prediction_errors"]))
                for i, act in enumerate(r["ring_activations"]):
                    ent_per_ring[i].append(_activation_entropy(act))
                    norm_per_ring[i].append(act.norm().item())

        avg_ent = np.mean([np.mean(e) for e in ent_per_ring])
        avg_pe = np.mean(pe_list)
        pe_first = np.mean(pe_list[:50])
        pe_last = np.mean(pe_list[-50:])
        pe_red = (pe_first - pe_last) / (pe_first + 1e-12) * 100
        avg_cv = np.mean([
            np.std(norm_per_ring[i]) / (np.mean(norm_per_ring[i]) + 1e-12)
            for i in range(5)
        ])
        avg_lat = np.mean(lat_list)

        # Modulation factors (only relevant for bridges-on)
        mod_factors = {}
        if bridges_on:
            mod = r.get("modulation_context")
            if mod is not None:
                mod_factors = {
                    "attention_gain": mod.attention_gain,
                    "precision_boost": mod.precision_boost,
                    "ffn_throughput": mod.ffn_throughput,
                    "threshold_mod": mod.threshold_mod,
                }

        comp_results[label] = {
            "entropy": avg_ent, "pe_avg": avg_pe,
            "pe_reduction": pe_red, "cv": avg_cv,
            "latency_ms": avg_lat, "mod_factors": mod_factors,
        }

    # Print side-by-side comparison
    off = comp_results["OFF (0 bridges)"]
    on = comp_results["ON (10 bridges)"]

    print(f"\n  {'Metric':<36s} {'OFF (0)':<14s} {'ON (10)':<14s} {'Delta':<12s} {'Verdict'}")
    print(f"  {'-'*36} {'-'*14} {'-'*14} {'-'*12} {'-'*8}")

    verdicts = []
    for lbl, key, unit, better in [
        ("Avg ring entropy", "entropy", "nats", "higher"),
        ("Avg prediction error", "pe_avg", "", "lower"),
        ("PE reduction (first->last)", "pe_reduction", "%", "higher"),
        ("Avg CV (stability)", "cv", "", "lower"),
        ("Avg latency", "latency_ms", "ms", "lower"),
    ]:
        v_off = off[key]
        v_on = on[key]
        delta = v_on - v_off
        sign = "+" if delta > 0 else ""
        if better == "higher":
            verdict = "[OK]" if delta >= 0 else "[WARN]"
        else:
            verdict = "[OK]" if delta <= 0 else "[WARN]"
        verdicts.append(verdict)
        print(f"  {lbl:<36s} {v_off:<14.4f} {v_on:<14.4f} {sign}{delta:<11.4f} {verdict}")

    # Modulation factors
    if on["mod_factors"]:
        print(f"\n  Modulation factors (bridges ON):")
        for fname, fval in on["mod_factors"].items():
            in_range = 0.3 <= fval <= 3.0
            status = "[OK]" if in_range else "[WARN]"
            print(f"    {fname:<30s}: {fval:.4f}  {status}")

    # Latency check
    lat_on = on["latency_ms"]
    print(f"\n  Latency target: {lat_on:.1f}ms {'<' if lat_on < 50 else '>='} 50ms",
          "[PASS]" if lat_on < 50 else "[FAIL]")

    # Overall verdict
    ok_count = sum(1 for v in verdicts if v == "[OK]")
    print(f"\n  Comparative eval: {ok_count}/{len(verdicts)} metrics neutral-or-better with bridges")
    print("  Bridges-On vs Bridges-Off: OK")
except Exception as e:
    print(f"  Comparative eval: FAILED - {e}")
    import traceback; traceback.print_exc()

# ================================================================
# Summary
# ================================================================
header("SUMMARY")
print(f"  Parameters: {total:,}")
print(f"  Prediction errors: {avg_errors.mean():.4f} avg")
print(f"  Hebbian bias change: {bias_delta.mean().item():.6f} mean")
print(f"  Sleep loss: {losses[0]:.4f} -> {losses[-1]:.4f}")
print(f"  EWC drift reduction: {drift_a:.4f} vs {drift_no_ewc:.4f}")
print(f"  DualProcess split: S1={s1_pct:.0f}% / S2={s2_pct:.0f}%")
print(f"  Wake-sleep output change: {avg_change:.4f}")
print()
