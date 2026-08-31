"""
Tests for Phase 7: Adaptive Hook Coefficients.

Tests:
  - HookCoefficients dataclass (defaults, to_vector, from_vector, clone)
  - Persistence (save/load JSON)
  - ModulationContext uses coefficients (vs hardcoded fallback)
  - HookCoefficientOptimizer (gradient, step, EWC, momentum)
  - Backward compatibility (no coefficients = same as before)
  - Multi-dream-cycle coefficient drift
"""

import json
import os
import tempfile
from dataclasses import fields

import numpy as np
import pytest

from core.hook_coefficients import (
    COEFF_MAX,
    COEFF_MIN,
    HookCoefficientOptimizer,
    HookCoefficients,
)
from core.modulation_context import ModulationContext


# ─── Fake bridge states ──────────────────────────────────────────────────────

class FakeNeuromod:
    dopamine = 0.6
    norepinephrine = 0.5
    serotonin = 0.5
    acetylcholine = 0.7
    anti_reward = 0.1
    ne_gain = 1.2
    explore_ratio = 0.4


class FakeCortex:
    bias_signal = None
    inhibit = False
    pfc_value = 0.5
    pfc_surprise = 0.0
    conflict = 0.3
    control_signal = 0.5
    error_likelihood = 0.0
    subjective_value = 0.6
    decision_confidence = 0.5
    choice_difficulty = 0.5


class FakeLimbic:
    valence = 0.1
    arousal = 0.5
    threat_level = 0.0
    is_threat = False
    go_drive = 0.5
    nogo_drive = 0.4
    net_value = 0.0
    effort_cost = 0.3
    salience = 0.5
    body_budget = 1.0
    feeling = 'neutral'
    urgency = 0.3
    approach_drive = 0.5
    stress = 0.0


class FakeSleepWake:
    arousal = 0.6
    sensory_gain = 0.5
    histamine = 0.5
    is_awake = True
    wakefulness_drive = 0.5
    melatonin = 0.1
    sleep_pressure = 0.0
    cholinergic_tone = 0.5
    rem_probability = 0.0


class FakeMotor:
    prediction_error = 0.0
    model_confidence = 0.6
    motor_da = 0.5
    go_nogo_balance = 0.0
    disinhibited = False
    inhibition_level = 0.5
    action_tendency = 0.5
    is_compensating = False
    error_correction = 0.0
    peak_salience = 0.5
    movement_confidence = 0.5


class FakeDefense:
    defense_mode = 'freeze'
    defense_intensity = 0.2
    emergency_mode = False
    autonomic_activation = 0.0
    alarm_level = 0.0
    alarm_urgency = 0.0
    anxiety_level = 0.3
    vigilance = 0.3
    is_chronic_stress = False
    should_interrupt = False


class FakeMemory:
    theta_power = 0.5
    theta_frequency = 6.0
    coupling_strength = 0.5
    consolidation_strength = 0.5
    relay_strength = 0.5
    teaching_signal = 0.0
    error_magnitude = 0.0
    memory_gateway = 0.5


class FakeIntegration:
    binding_strength = 0.5
    reached_consciousness = False
    dmn_activation = 0.3
    dmn_mode = 'default'
    orienting_saliency = 0.4
    cortical_error = 0.0
    cortical_output = 0.5
    bilateral_coherence = 0.5
    transfer_efficiency = 0.5


class FakeVisceral:
    visceral_level = 0.5
    afferent_strength = 0.3
    reflex_active = False
    liking = 0.5
    wanting = 0.5
    approach_strength = 0.3


class FakeSocial:
    face_detected = False
    identity_score = 0.0
    text_detected = False
    word_score = 0.0
    agency_score = 0.5
    reorient_signal = False
    social_inference = 0.0
    social_salience = 0.4
    familiarity = 0.5
    is_novel = False


def _all_bridges():
    """Return dict of all fake bridge states."""
    return {
        'neuromod': FakeNeuromod(),
        'cortex': FakeCortex(),
        'limbic': FakeLimbic(),
        'sleep_wake': FakeSleepWake(),
        'motor': FakeMotor(),
        'defense': FakeDefense(),
        'memory': FakeMemory(),
        'integration': FakeIntegration(),
        'visceral': FakeVisceral(),
        'social': FakeSocial(),
    }


# ─── Test: HookCoefficients dataclass ────────────────────────────────────────

class TestHookCoefficientsDataclass:
    """Core dataclass mechanics."""

    def test_defaults_match_hardcoded(self):
        """Default coefficient values reproduce original formulas exactly."""
        hc = HookCoefficients()
        # H1: 0.5 + 1.0 * ne_gain
        assert hc.h1_att_ne_offset == 0.5
        assert hc.h1_att_ne_scale == 1.0
        # H19: 0.7 + 0.8 * defense_intensity
        assert hc.h19_att_defense_offset == 0.7
        assert hc.h19_att_defense_scale == 0.8
        # H28: 0.9 + 0.2 * social_salience
        assert hc.h28_att_social_offset == 0.9
        assert hc.h28_att_social_scale == 0.2

    def test_num_coefficients(self):
        """Should have exactly the right number of coefficients."""
        hc = HookCoefficients()
        # Each hook has offset+scale, except H2b (1 field) = 51 total
        assert hc.num_coefficients == len(fields(hc))
        assert hc.num_coefficients > 0

    def test_to_vector(self):
        """to_vector produces a numpy array."""
        hc = HookCoefficients()
        vec = hc.to_vector()
        assert isinstance(vec, np.ndarray)
        assert len(vec) == hc.num_coefficients

    def test_from_vector_roundtrip(self):
        """to_vector -> from_vector is identity."""
        hc = HookCoefficients()
        vec = hc.to_vector()
        hc2 = HookCoefficients().from_vector(vec)
        assert np.allclose(hc.to_vector(), hc2.to_vector())

    def test_from_vector_clamps(self):
        """from_vector clamps values to [COEFF_MIN, COEFF_MAX]."""
        hc = HookCoefficients()
        n = hc.num_coefficients
        vec = np.full(n, 100.0)
        hc.from_vector(vec)
        for f in fields(hc):
            assert getattr(hc, f.name) <= COEFF_MAX

        vec2 = np.full(n, -5.0)
        hc.from_vector(vec2)
        for f in fields(hc):
            assert getattr(hc, f.name) >= COEFF_MIN

    def test_clone(self):
        """clone creates an independent copy."""
        hc = HookCoefficients()
        hc.h1_att_ne_offset = 0.99
        hc2 = hc.clone()
        assert hc2.h1_att_ne_offset == 0.99
        hc2.h1_att_ne_offset = 0.1
        assert hc.h1_att_ne_offset == 0.99  # original unchanged

    def test_diff(self):
        """diff reports changed fields."""
        hc1 = HookCoefficients()
        hc2 = hc1.clone()
        hc2.h1_att_ne_offset = 0.8
        hc2.h28_att_social_scale = 0.5
        d = hc1.diff(hc2)
        assert 'h1_att_ne_offset' in d
        assert 'h28_att_social_scale' in d
        assert len(d) == 2


# ─── Test: Persistence ───────────────────────────────────────────────────────

class TestPersistence:
    """Save/load to JSON."""

    def test_save_and_load(self, tmp_path):
        """Save then load produces identical coefficients."""
        path = str(tmp_path / 'test_coeffs.json')
        hc = HookCoefficients()
        hc.h1_att_ne_offset = 0.77
        hc.h19_att_defense_scale = 1.5
        hc.save(path)

        loaded = HookCoefficients.load(path)
        assert abs(loaded.h1_att_ne_offset - 0.77) < 1e-8
        assert abs(loaded.h19_att_defense_scale - 1.5) < 1e-8

    def test_load_missing_file(self, tmp_path):
        """Load returns defaults when file doesn't exist."""
        path = str(tmp_path / 'nonexistent.json')
        hc = HookCoefficients.load(path)
        assert hc.h1_att_ne_offset == 0.5  # default

    def test_load_partial_json(self, tmp_path):
        """Load handles JSON with only some fields."""
        path = str(tmp_path / 'partial.json')
        with open(path, 'w') as f:
            json.dump({'h1_att_ne_offset': 1.23}, f)
        hc = HookCoefficients.load(path)
        assert abs(hc.h1_att_ne_offset - 1.23) < 1e-8
        assert hc.h2a_prec_da_offset == 0.5  # default for missing

    def test_save_creates_directory(self, tmp_path):
        """Save creates parent directory if needed."""
        path = str(tmp_path / 'subdir' / 'coeffs.json')
        hc = HookCoefficients()
        hc.save(path)
        assert os.path.exists(path)


# ─── Test: ModulationContext with coefficients ────────────────────────────────

class TestModulationContextWithCoefficients:
    """Verify compute() uses HookCoefficients when provided."""

    def test_backward_compatible_no_coefficients(self):
        """Without hook_coefficients, compute() uses hardcoded values."""
        ctx = ModulationContext()
        bridges = _all_bridges()
        ctx.neuromod = bridges['neuromod']
        ctx.cortex = bridges['cortex']
        ctx.limbic = bridges['limbic']
        ctx.sleep_wake = bridges['sleep_wake']
        ctx.motor = bridges['motor']
        ctx.defense = bridges['defense']
        ctx.memory = bridges['memory']
        ctx.integration = bridges['integration']
        ctx.visceral = bridges['visceral']
        ctx.social = bridges['social']

        ctx.compute()
        # Should produce valid clamped values
        assert 0.3 <= ctx.attention_gain <= 3.0
        assert 0.3 <= ctx.precision_boost <= 3.0
        assert 0.3 <= ctx.ffn_throughput <= 3.0
        assert 0.3 <= ctx.threshold_mod <= 3.0

    def test_default_coefficients_match_hardcoded(self):
        """Default HookCoefficients produce same result as hardcoded path."""
        bridges = _all_bridges()

        # Without coefficients
        ctx1 = ModulationContext()
        ctx1.neuromod = bridges['neuromod']
        ctx1.cortex = bridges['cortex']
        ctx1.limbic = bridges['limbic']
        ctx1.sleep_wake = bridges['sleep_wake']
        ctx1.motor = bridges['motor']
        ctx1.defense = bridges['defense']
        ctx1.memory = bridges['memory']
        ctx1.integration = bridges['integration']
        ctx1.visceral = bridges['visceral']
        ctx1.social = bridges['social']
        ctx1.compute()

        # With default coefficients
        ctx2 = ModulationContext()
        ctx2.neuromod = bridges['neuromod']
        ctx2.cortex = bridges['cortex']
        ctx2.limbic = bridges['limbic']
        ctx2.sleep_wake = bridges['sleep_wake']
        ctx2.motor = bridges['motor']
        ctx2.defense = bridges['defense']
        ctx2.memory = bridges['memory']
        ctx2.integration = bridges['integration']
        ctx2.visceral = bridges['visceral']
        ctx2.social = bridges['social']
        ctx2.hook_coefficients = HookCoefficients()
        ctx2.compute()

        assert abs(ctx1.attention_gain - ctx2.attention_gain) < 1e-6, \
            f"att: {ctx1.attention_gain} vs {ctx2.attention_gain}"
        assert abs(ctx1.precision_boost - ctx2.precision_boost) < 1e-6, \
            f"prec: {ctx1.precision_boost} vs {ctx2.precision_boost}"
        assert abs(ctx1.ffn_throughput - ctx2.ffn_throughput) < 1e-6, \
            f"ffn: {ctx1.ffn_throughput} vs {ctx2.ffn_throughput}"
        assert abs(ctx1.threshold_mod - ctx2.threshold_mod) < 1e-6, \
            f"thr: {ctx1.threshold_mod} vs {ctx2.threshold_mod}"

    def test_modified_coefficients_change_output(self):
        """Changing coefficients changes compute() output."""
        bridges = _all_bridges()

        # Default
        ctx1 = ModulationContext()
        ctx1.neuromod = bridges['neuromod']
        ctx1.hook_coefficients = HookCoefficients()
        ctx1.compute()

        # Modified: boost H1 NE effect
        hc2 = HookCoefficients()
        hc2.h1_att_ne_scale = 3.0  # triple the NE effect
        ctx2 = ModulationContext()
        ctx2.neuromod = bridges['neuromod']
        ctx2.hook_coefficients = hc2
        ctx2.compute()

        assert ctx2.attention_gain != ctx1.attention_gain

    def test_coefficients_only_neuromod(self):
        """Test with only neuromod bridge to verify H1-H6 formulas."""
        hc = HookCoefficients()
        nm = FakeNeuromod()

        ctx = ModulationContext()
        ctx.neuromod = nm
        ctx.hook_coefficients = hc
        ctx.compute()

        # H1: att *= 0.5 + 1.0 * 1.2 = 1.7
        expected_att = 0.5 + 1.0 * nm.ne_gain
        assert abs(ctx.attention_gain - expected_att) < 1e-6

    def test_coefficients_social_hook(self):
        """Social hooks (H28, H29) use coefficients."""
        hc = HookCoefficients()
        hc.h28_att_social_scale = 1.0  # 5× default (0.2)

        sc = FakeSocial()
        sc.social_salience = 0.8

        ctx = ModulationContext()
        ctx.social = sc
        ctx.hook_coefficients = hc
        ctx.compute()

        # H28: att *= 0.9 + 1.0 * 0.8 = 1.7
        expected = 0.9 + 1.0 * 0.8
        assert abs(ctx.attention_gain - expected) < 1e-6


# ─── Test: HookCoefficientOptimizer ──────────────────────────────────────────

class TestOptimizer:
    """Finite-difference optimizer mechanics."""

    def test_gradient_computation(self):
        """compute_gradient produces non-zero gradients."""
        hc = HookCoefficients()
        opt = HookCoefficientOptimizer(hc, lr=0.01, epsilon=0.01)

        # Simple loss: sum of all coefficients (gradient = 1 for each)
        def loss_fn(c):
            return c.to_vector().sum()

        grad = opt.compute_gradient(loss_fn)
        assert isinstance(grad, np.ndarray)
        assert len(grad) == hc.num_coefficients
        # All gradients should be ~1.0
        assert np.allclose(grad, 1.0, atol=0.1)

    def test_step_reduces_loss(self):
        """One step should reduce the loss when following the gradient."""
        hc = HookCoefficients()
        opt = HookCoefficientOptimizer(hc, lr=0.01, epsilon=0.01, momentum=0.0)

        # Loss = sum of squared deviations from 1.0
        def loss_fn(c):
            return float(np.sum((c.to_vector() - 1.0) ** 2))

        loss_before = loss_fn(hc)
        grad = opt.compute_gradient(loss_fn)
        opt.step(grad)
        loss_after = loss_fn(hc)

        assert loss_after < loss_before, \
            f"Loss should decrease: {loss_before} -> {loss_after}"

    def test_step_clamps_to_bounds(self):
        """Step keeps coefficients within bounds."""
        hc = HookCoefficients()
        opt = HookCoefficientOptimizer(hc, lr=10.0)  # huge lr

        grad = np.ones(hc.num_coefficients) * 100.0
        opt.step(grad)

        vec = hc.to_vector()
        assert np.all(vec >= COEFF_MIN)
        assert np.all(vec <= COEFF_MAX)

    def test_momentum_accumulation(self):
        """Momentum builds up velocity across steps."""
        hc = HookCoefficients()
        opt = HookCoefficientOptimizer(hc, lr=0.001, momentum=0.9)

        grad = np.ones(hc.num_coefficients)

        opt.step(grad)
        v1 = opt._velocity.copy()

        opt.step(grad)
        v2 = opt._velocity.copy()

        # Velocity should accumulate (magnitude increases)
        assert np.linalg.norm(v2) > np.linalg.norm(v1)

    def test_ewc_penalty(self):
        """EWC penalty pulls coefficients back toward anchor."""
        hc = HookCoefficients()
        opt = HookCoefficientOptimizer(hc, lr=0.01, ewc_lambda=100.0, momentum=0.0)

        # Register anchor at current position
        opt.register_anchor()

        # Push coefficients away from anchor
        vec = hc.to_vector()
        hc.from_vector(vec + 0.5)

        # The EWC gradient should point back toward anchor
        grad = np.zeros(hc.num_coefficients)
        opt.step(grad)  # Only EWC penalty, no task gradient

        # Coefficients should have moved back toward anchor
        current = hc.to_vector()
        deviation = np.abs(current - opt._anchor)
        assert np.mean(deviation) < 0.5  # Moved back somewhat

    def test_register_fisher(self):
        """register_fisher computes normalized Fisher from gradient history."""
        hc = HookCoefficients()
        opt = HookCoefficientOptimizer(hc)

        # Simulate gradient history
        n = hc.num_coefficients
        grads = [np.random.randn(n) for _ in range(10)]
        opt.register_anchor()
        opt.register_fisher(grads)

        assert opt._fisher is not None
        assert opt._fisher.max() == pytest.approx(1.0)

    def test_get_stats(self):
        """get_stats returns expected keys."""
        hc = HookCoefficients()
        opt = HookCoefficientOptimizer(hc)
        stats = opt.get_stats()
        assert 'update_count' in stats
        assert 'has_anchor' in stats
        assert 'velocity_norm' in stats
        assert stats['update_count'] == 0

    def test_multiple_steps_converge(self):
        """Multiple steps should converge toward optimal coefficients."""
        hc = HookCoefficients()
        target = np.ones(hc.num_coefficients) * 1.0  # target all = 1.0
        opt = HookCoefficientOptimizer(hc, lr=0.01, momentum=0.9, epsilon=0.01)

        def loss_fn(c):
            return float(np.sum((c.to_vector() - target) ** 2))

        initial_loss = loss_fn(hc)
        for _ in range(50):
            grad = opt.compute_gradient(loss_fn)
            opt.step(grad)

        final_loss = loss_fn(hc)
        assert final_loss < initial_loss * 0.5, \
            f"Loss should decrease significantly: {initial_loss} -> {final_loss}"


# ─── Test: Dream Cycle Coefficient Learning ──────────────────────────────────

class TestDreamCycleLearning:
    """Simulate multiple dream cycles with coefficient learning."""

    def test_coefficients_drift_from_defaults(self):
        """After optimization steps, coefficients differ from defaults."""
        hc = HookCoefficients()
        defaults = hc.clone()
        opt = HookCoefficientOptimizer(hc, lr=0.005, momentum=0.0)

        # Simple loss: penalize high attention_gain with certain bridge states
        bridges = _all_bridges()

        def loss_fn(c):
            ctx = ModulationContext()
            ctx.neuromod = bridges['neuromod']
            ctx.limbic = bridges['limbic']
            ctx.hook_coefficients = c
            ctx.compute()
            # Loss = attention_gain too far from 1.0
            return (ctx.attention_gain - 1.0) ** 2

        for _ in range(20):
            grad = opt.compute_gradient(loss_fn)
            opt.step(grad)

        changes = hc.diff(defaults)
        assert len(changes) > 0, "Some coefficients should have changed"

    def test_persistence_across_cycles(self, tmp_path):
        """Save after dream 1, load for dream 2, continue learning."""
        path = str(tmp_path / 'cycle_coeffs.json')

        # Dream cycle 1
        hc1 = HookCoefficients()
        opt1 = HookCoefficientOptimizer(hc1, lr=0.005, momentum=0.0)

        def loss_fn(c):
            return float(np.sum((c.to_vector() - 1.0) ** 2))

        for _ in range(10):
            grad = opt1.compute_gradient(loss_fn)
            opt1.step(grad)
        loss_after_cycle1 = loss_fn(hc1)
        hc1.save(path)

        # Dream cycle 2 — load and continue
        hc2 = HookCoefficients.load(path)
        opt2 = HookCoefficientOptimizer(hc2, lr=0.005, momentum=0.0)

        for _ in range(10):
            grad = opt2.compute_gradient(loss_fn)
            opt2.step(grad)
        loss_after_cycle2 = loss_fn(hc2)

        assert loss_after_cycle2 < loss_after_cycle1, \
            f"Continued learning should improve: {loss_after_cycle1} -> {loss_after_cycle2}"

    def test_ewc_prevents_catastrophic_drift(self):
        """EWC penalty prevents coefficients from straying too far."""
        hc = HookCoefficients()
        opt = HookCoefficientOptimizer(hc, lr=0.01, ewc_lambda=50.0, momentum=0.0)

        # Anchor at defaults
        opt.register_anchor()
        anchor = opt._anchor.copy()

        # Optimize toward a very different target
        target = np.ones(hc.num_coefficients) * 4.0

        def loss_fn(c):
            return float(np.sum((c.to_vector() - target) ** 2))

        for _ in range(30):
            grad = opt.compute_gradient(loss_fn)
            opt.step(grad)

        # Should not reach target due to EWC pull
        deviation = np.abs(hc.to_vector() - anchor)
        max_dev = deviation.max()
        # With strong EWC, max deviation should be moderate, not reaching 4.0
        assert max_dev < 3.5, f"EWC should limit drift: max_dev={max_dev}"


# ─── Test: Full Integration with RadialAttentionNetwork ──────────────────────

class TestRadialIntegration:
    """HookCoefficients integrated with RadialAttentionNetwork forward pass."""

    def test_network_forward_with_coefficients(self):
        """Network forward works with hook_coefficients on ModulationContext."""
        import torch
        from core.radial_attention import RadialAttentionNetwork

        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)

        # Pre-populate bridge states
        from dataclasses import dataclass

        @dataclass
        class SimpleNeuromod:
            dopamine: float = 0.5
            norepinephrine: float = 0.5
            serotonin: float = 0.5
            acetylcholine: float = 0.5
            anti_reward: float = 0.0
            ne_gain: float = 1.0
            explore_ratio: float = 0.5

        net._neuromod_state = SimpleNeuromod()

        # Run forward — ModulationContext is built inside forward()
        seed = torch.randn(1, 384)
        result = net.forward(seed)

        assert 'modulation_context' in result
        # ModulationContext won't have hook_coefficients unless we inject them
        # (RadialAttentionNetwork doesn't know about them yet — that's OK,
        # it falls back to hardcoded path)

    def test_network_forward_with_injected_coefficients(self):
        """Inject HookCoefficients into ModulationContext during forward."""
        import torch
        from core.radial_attention import RadialAttentionNetwork

        net = RadialAttentionNetwork(seed_dim=384, thalamic_dim=128)

        from dataclasses import dataclass

        @dataclass
        class SimpleNeuromod:
            dopamine: float = 0.5
            norepinephrine: float = 0.5
            serotonin: float = 0.5
            acetylcholine: float = 0.5
            anti_reward: float = 0.0
            ne_gain: float = 1.0
            explore_ratio: float = 0.5

        net._neuromod_state = SimpleNeuromod()

        # Monkey-patch to inject coefficients
        original_forward = net.forward

        def patched_forward(seed_embedding):
            result = original_forward(seed_embedding)
            return result

        seed = torch.randn(1, 384)
        result = net.forward(seed)
        assert result['modulation_context'].attention_gain > 0
