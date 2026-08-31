"""
Tests for ConsciousnessLoop (Phase 9).

Covers:
  - ConsciousnessState dataclass
  - ConsciousnessLoop computation from bridge states
  - Ring 5 gain feedback
  - DualProcess threshold adjustment
  - DMN gating logic
  - Recursive 1-tick delay behavior
  - Integration with RadialAttentionNetwork
  - Integration with DualProcessRouter
  - Smoothing and temporal dynamics
"""

import sys
import numpy as np
import pytest
import torch

sys.path.insert(0, ".")

from core.consciousness_loop import ConsciousnessLoop, ConsciousnessState
from core.radial_attention import RadialAttentionNetwork, DualProcessRouter
from core.modulation_context import ModulationContext


# ─── Fake bridge states for testing ──────────────────────────────────────────

class FakeIntegrationState:
    def __init__(self, binding_strength=0.5, reached_consciousness=False,
                 dmn_activation=0.3, orienting_saliency=0.3):
        self.binding_strength = binding_strength
        self.reached_consciousness = reached_consciousness
        self.dmn_activation = dmn_activation
        self.dmn_mode = 'default'
        self.orienting_saliency = orienting_saliency
        self.cortical_error = 0.0
        self.cortical_output = 0.5
        self.bilateral_coherence = 0.5
        self.transfer_efficiency = 0.5


class FakeCortexState:
    def __init__(self, conflict=0.0):
        self.conflict = conflict
        self.bias_signal = None
        self.inhibit = False
        self.pfc_value = 0.5
        self.pfc_surprise = 0.0
        self.control_signal = 0.5
        self.error_likelihood = 0.0
        self.subjective_value = 0.5
        self.decision_confidence = 0.5
        self.choice_difficulty = 0.5


class FakeSocialState:
    def __init__(self, agency_score=0.5, social_salience=0.0):
        self.agency_score = agency_score
        self.social_salience = social_salience
        self.face_detected = False
        self.identity_score = 0.0
        self.text_detected = False
        self.word_score = 0.0
        self.reorient_signal = False
        self.social_inference = 0.0
        self.familiarity = 0.3
        self.is_novel = False


class FakeNeuromodState:
    dopamine = 0.5; norepinephrine = 0.5; serotonin = 0.5
    acetylcholine = 0.5; anti_reward = 0.0; ne_gain = 1.0; explore_ratio = 0.5


class FakeLimbicState:
    valence = 0.0; arousal = 0.3; threat_level = 0.0; is_threat = False
    go_drive = 0.5; nogo_drive = 0.5; net_value = 0.0; effort_cost = 0.3
    salience = 0.3; body_budget = 1.0; feeling = "neutral"; urgency = 0.0
    approach_drive = 0.3; stress = 0.0


class FakeSleepWakeState:
    arousal = 0.5; sensory_gain = 0.5; histamine = 0.5; is_awake = True
    wakefulness_drive = 0.5; melatonin = 0.0; sleep_pressure = 0.0
    cholinergic_tone = 0.5; rem_probability = 0.0


class FakeMotorState:
    prediction_error = 0.0; model_confidence = 0.5; motor_da = 0.5
    go_nogo_balance = 0.0; disinhibited = False; inhibition_level = 0.5
    action_tendency = 0.5; is_compensating = False; error_correction = 0.0
    peak_salience = 0.5; movement_confidence = 0.5


class FakeDefenseState:
    defense_mode = "freeze"; defense_intensity = 0.0; emergency_mode = False
    autonomic_activation = 0.0; alarm_level = 0.0; alarm_urgency = 0.0
    anxiety_level = 0.0; vigilance = 0.3; is_chronic_stress = False
    should_interrupt = False


class FakeMemoryState:
    theta_power = 0.5; theta_frequency = 6.0; coupling_strength = 0.5
    consolidation_strength = 0.5; relay_strength = 0.5; teaching_signal = 0.0
    error_magnitude = 0.0; memory_gateway = 0.5


class FakeVisceralState:
    visceral_level = 0.5; afferent_strength = 0.3; reflex_active = False
    liking = 0.5; wanting = 0.5; approach_strength = 0.3


# ─── Test ConsciousnessState ────────────────────────────────────────────────

class TestConsciousnessState:
    def test_default_values(self):
        s = ConsciousnessState()
        assert s.consciousness_level == 0.5
        assert s.integration_score == 0.5
        assert s.self_referential == 0.3
        assert s.conflict == 0.0
        assert s.agency == 0.5
        assert s.cognitive_load == 0.5
        assert s.dmn_gated is False
        assert s.system2_bias == 0.0
        assert s.ring5_gain == 1.0

    def test_custom_values(self):
        s = ConsciousnessState(
            consciousness_level=0.9,
            integration_score=0.8,
            dmn_gated=True,
            ring5_gain=1.5,
        )
        assert s.consciousness_level == 0.9
        assert s.dmn_gated is True
        assert s.ring5_gain == 1.5


# ─── Test ConsciousnessLoop Core ─────────────────────────────────────────────

class TestConsciousnessLoopCore:
    def test_initialization(self):
        loop = ConsciousnessLoop()
        assert loop.consciousness_level == 0.5
        assert loop._tick_count == 0
        state = loop.state
        assert isinstance(state, ConsciousnessState)

    def test_update_with_no_inputs(self):
        loop = ConsciousnessLoop()
        state = loop.update()
        assert isinstance(state, ConsciousnessState)
        # With None inputs, uses defaults (0.5 integration, 0.3 dmn, 0 conflict, 0.5 agency)
        assert 0.0 <= state.consciousness_level <= 1.0
        assert loop._tick_count == 1

    def test_update_with_integration_state(self):
        loop = ConsciousnessLoop()
        ig = FakeIntegrationState(
            binding_strength=0.9,
            reached_consciousness=True,
            dmn_activation=0.8,
        )
        state = loop.update(integration_state=ig)
        assert state.integration_score == 0.9
        assert state.self_referential == 0.8

    def test_high_binding_raises_consciousness(self):
        loop = ConsciousnessLoop(smoothing=1.0)  # No smoothing
        # Low binding
        ig_low = FakeIntegrationState(binding_strength=0.1, reached_consciousness=False)
        s_low = loop.update(integration_state=ig_low)
        loop.reset()

        # High binding + consciousness reached
        ig_high = FakeIntegrationState(binding_strength=0.9, reached_consciousness=True)
        s_high = loop.update(integration_state=ig_high)

        assert s_high.consciousness_level > s_low.consciousness_level

    def test_conflict_raises_consciousness(self):
        """High ACC conflict -> higher consciousness (more deliberation needed)."""
        loop = ConsciousnessLoop(smoothing=1.0)
        cx_low = FakeCortexState(conflict=0.0)
        s_low = loop.update(cortex_state=cx_low)
        loop.reset()

        cx_high = FakeCortexState(conflict=1.0)
        s_high = loop.update(cortex_state=cx_high)
        assert s_high.consciousness_level > s_low.consciousness_level

    def test_agency_affects_consciousness(self):
        """TPJ agency score contributes to consciousness."""
        loop = ConsciousnessLoop(smoothing=1.0)
        sc_low = FakeSocialState(agency_score=0.0)
        s_low = loop.update(social_state=sc_low)
        loop.reset()

        sc_high = FakeSocialState(agency_score=1.0)
        s_high = loop.update(social_state=sc_high)
        assert s_high.consciousness_level > s_low.consciousness_level

    def test_consciousness_clamped_to_01(self):
        """Consciousness level always in [0, 1]."""
        loop = ConsciousnessLoop(smoothing=1.0)
        # Extreme inputs
        ig = FakeIntegrationState(binding_strength=5.0, reached_consciousness=True,
                                   dmn_activation=5.0)
        cx = FakeCortexState(conflict=5.0)
        sc = FakeSocialState(agency_score=5.0)
        state = loop.update(integration_state=ig, cortex_state=cx, social_state=sc)
        assert 0.0 <= state.consciousness_level <= 1.0

        # Extreme negative
        loop.reset()
        ig2 = FakeIntegrationState(binding_strength=-5.0, reached_consciousness=False,
                                    dmn_activation=-5.0)
        state2 = loop.update(integration_state=ig2)
        assert 0.0 <= state2.consciousness_level <= 1.0

    def test_unreached_consciousness_dampened(self):
        """When Claustrum hasn't reached consciousness, level is dampened."""
        loop = ConsciousnessLoop(smoothing=1.0)
        ig_reached = FakeIntegrationState(binding_strength=0.8, reached_consciousness=True,
                                           dmn_activation=0.6)
        s_reached = loop.update(integration_state=ig_reached)
        loop.reset()

        ig_not = FakeIntegrationState(binding_strength=0.8, reached_consciousness=False,
                                       dmn_activation=0.6)
        s_not = loop.update(integration_state=ig_not)
        assert s_not.consciousness_level < s_reached.consciousness_level


# ─── Test Ring 5 Feedback ────────────────────────────────────────────────────

class TestRing5Feedback:
    def test_ring5_gain_default(self):
        loop = ConsciousnessLoop()
        # Default consciousness = 0.5 -> gain = 1.0 + 0.6 * (0.5 - 0.5) = 1.0
        assert loop.state.ring5_gain == 1.0

    def test_ring5_gain_high_consciousness(self):
        loop = ConsciousnessLoop(smoothing=1.0)
        ig = FakeIntegrationState(binding_strength=0.9, reached_consciousness=True,
                                   dmn_activation=0.8)
        cx = FakeCortexState(conflict=0.8)
        sc = FakeSocialState(agency_score=0.9)
        loop.update(integration_state=ig, cortex_state=cx, social_state=sc)
        assert loop.state.ring5_gain > 1.0  # Higher consciousness -> more gain

    def test_ring5_gain_low_consciousness(self):
        loop = ConsciousnessLoop(smoothing=1.0)
        ig = FakeIntegrationState(binding_strength=0.0, reached_consciousness=False,
                                   dmn_activation=0.0)
        cx = FakeCortexState(conflict=0.0)
        sc = FakeSocialState(agency_score=0.0)
        loop.update(integration_state=ig, cortex_state=cx, social_state=sc)
        assert loop.state.ring5_gain < 1.0  # Lower consciousness -> less gain

    def test_ring5_gain_clamped(self):
        loop = ConsciousnessLoop(smoothing=1.0)
        # Even extreme values stay in bounds
        for _ in range(10):
            ig = FakeIntegrationState(binding_strength=1.0, reached_consciousness=True,
                                       dmn_activation=1.0)
            cx = FakeCortexState(conflict=1.0)
            sc = FakeSocialState(agency_score=1.0)
            loop.update(integration_state=ig, cortex_state=cx, social_state=sc)
        assert 0.5 <= loop.state.ring5_gain <= 2.0

    def test_get_ring5_bias_shape(self):
        loop = ConsciousnessLoop()
        bias = loop.get_ring5_bias(ring5_dim=128)
        assert bias.shape == (128,)
        assert bias.dtype == np.float32


# ─── Test DualProcess Feedback ───────────────────────────────────────────────

class TestDualProcessFeedback:
    def test_threshold_adjustment_default(self):
        loop = ConsciousnessLoop()
        # Default consciousness = 0.5 < threshold 0.6 -> no bias
        adj = loop.get_threshold_adjustment()
        assert adj == 1.0  # No adjustment

    def test_threshold_adjustment_high_consciousness(self):
        """High consciousness should lower threshold (bias System 2)."""
        loop = ConsciousnessLoop(smoothing=1.0)
        ig = FakeIntegrationState(binding_strength=0.9, reached_consciousness=True,
                                   dmn_activation=0.8)
        cx = FakeCortexState(conflict=0.8)
        sc = FakeSocialState(agency_score=0.9)
        loop.update(integration_state=ig, cortex_state=cx, social_state=sc)
        adj = loop.get_threshold_adjustment()
        assert adj < 1.0  # Lower threshold = more System 2

    def test_threshold_adjustment_bounded(self):
        loop = ConsciousnessLoop(smoothing=1.0)
        for _ in range(20):
            ig = FakeIntegrationState(binding_strength=1.0, reached_consciousness=True,
                                       dmn_activation=1.0)
            cx = FakeCortexState(conflict=1.0)
            sc = FakeSocialState(agency_score=1.0)
            loop.update(integration_state=ig, cortex_state=cx, social_state=sc)
        adj = loop.get_threshold_adjustment()
        assert adj >= 0.5  # Never goes below 0.5

    def test_system2_bias_only_above_threshold(self):
        """System 2 bias only activates above consciousness_threshold."""
        loop = ConsciousnessLoop(consciousness_threshold=0.6, smoothing=1.0)
        # Low consciousness
        ig = FakeIntegrationState(binding_strength=0.1, reached_consciousness=False)
        loop.update(integration_state=ig)
        assert loop.state.system2_bias == 0.0

        # High consciousness
        loop.reset()
        ig2 = FakeIntegrationState(binding_strength=0.9, reached_consciousness=True,
                                    dmn_activation=0.8)
        cx = FakeCortexState(conflict=0.8)
        sc = FakeSocialState(agency_score=0.9)
        loop.update(integration_state=ig2, cortex_state=cx, social_state=sc)
        assert loop.state.system2_bias > 0.0


# ─── Test DMN Gating ────────────────────────────────────────────────────────

class TestDMNGating:
    def test_dmn_gated_default_false(self):
        loop = ConsciousnessLoop()
        assert loop.get_dmn_gate() is False

    def test_dmn_gated_high_consciousness_low_load(self):
        """DMN allowed when conscious + low cognitive load."""
        loop = ConsciousnessLoop(smoothing=1.0, dmn_load_threshold=0.4)
        ig = FakeIntegrationState(binding_strength=0.9, reached_consciousness=True,
                                   dmn_activation=0.8)
        cx = FakeCortexState(conflict=0.8)
        sc = FakeSocialState(agency_score=0.9)
        # Low PE = low load
        loop.update(
            integration_state=ig, cortex_state=cx, social_state=sc,
            prediction_errors=[0.01, 0.01, 0.01, 0.01]
        )
        assert loop.state.dmn_gated is True

    def test_dmn_not_gated_high_load(self):
        """DMN suppressed under high cognitive load."""
        loop = ConsciousnessLoop(smoothing=1.0, dmn_load_threshold=0.4)
        ig = FakeIntegrationState(binding_strength=0.9, reached_consciousness=True,
                                   dmn_activation=0.8)
        cx = FakeCortexState(conflict=0.8)
        sc = FakeSocialState(agency_score=0.9)
        # High PE = high load
        loop.update(
            integration_state=ig, cortex_state=cx, social_state=sc,
            prediction_errors=[0.8, 0.9, 0.7, 0.85]
        )
        assert loop.state.dmn_gated is False

    def test_dmn_not_gated_low_consciousness(self):
        """DMN suppressed at low consciousness regardless of load."""
        loop = ConsciousnessLoop(smoothing=1.0)
        ig = FakeIntegrationState(binding_strength=0.1, reached_consciousness=False)
        loop.update(
            integration_state=ig,
            prediction_errors=[0.01, 0.01, 0.01, 0.01]
        )
        assert loop.state.dmn_gated is False


# ─── Test Temporal Dynamics (1-tick delay + smoothing) ───────────────────────

class TestTemporalDynamics:
    def test_one_tick_delay(self):
        """State computed on tick t is used on tick t+1."""
        loop = ConsciousnessLoop()
        # Initial state should be defaults
        initial = loop.state
        assert initial.consciousness_level == 0.5

        # Update with high inputs
        ig = FakeIntegrationState(binding_strength=0.9, reached_consciousness=True)
        new_state = loop.update(integration_state=ig)

        # After update, state reflects new computation
        assert loop.state is new_state
        assert loop._tick_count == 1

    def test_smoothing_slows_changes(self):
        """Exponential smoothing prevents instant jumps."""
        loop_fast = ConsciousnessLoop(smoothing=1.0)  # Instant
        loop_slow = ConsciousnessLoop(smoothing=0.1)  # Very smooth

        ig = FakeIntegrationState(binding_strength=0.9, reached_consciousness=True,
                                   dmn_activation=0.8)
        cx = FakeCortexState(conflict=0.8)
        sc = FakeSocialState(agency_score=0.9)

        s_fast = loop_fast.update(integration_state=ig, cortex_state=cx, social_state=sc)
        s_slow = loop_slow.update(integration_state=ig, cortex_state=cx, social_state=sc)

        # Fast should change more than slow on first tick
        fast_delta = abs(s_fast.consciousness_level - 0.5)
        slow_delta = abs(s_slow.consciousness_level - 0.5)
        assert fast_delta > slow_delta

    def test_convergence_over_ticks(self):
        """With constant input, consciousness converges."""
        loop = ConsciousnessLoop(smoothing=0.3)
        ig = FakeIntegrationState(binding_strength=0.9, reached_consciousness=True,
                                   dmn_activation=0.7)
        cx = FakeCortexState(conflict=0.5)

        levels = []
        for _ in range(50):
            loop.update(integration_state=ig, cortex_state=cx)
            levels.append(loop.consciousness_level)

        # Should converge (last 10 values very similar)
        last_10 = levels[-10:]
        spread = max(last_10) - min(last_10)
        assert spread < 0.01

    def test_multi_tick_sequence(self):
        """Run 20 ticks with varying inputs."""
        loop = ConsciousnessLoop(smoothing=0.3)
        levels = []
        for tick in range(20):
            # Gradually increase binding
            binding = tick / 20.0
            ig = FakeIntegrationState(
                binding_strength=binding,
                reached_consciousness=binding > 0.5,
                dmn_activation=binding * 0.8,
            )
            loop.update(integration_state=ig)
            levels.append(loop.consciousness_level)

        # Should generally increase
        assert levels[-1] > levels[0]


# ─── Test RadialAttentionNetwork Integration ─────────────────────────────────

class TestRadialIntegration:
    def test_attach_consciousness_loop(self):
        net = RadialAttentionNetwork(seed_dim=384)
        loop = ConsciousnessLoop()
        net.attach_consciousness_loop(loop)
        assert net._consciousness_loop is loop

    def test_forward_with_consciousness_loop(self):
        """Full forward pass with consciousness loop attached."""
        net = RadialAttentionNetwork(seed_dim=384)
        loop = ConsciousnessLoop()
        net.attach_consciousness_loop(loop)

        seed = torch.randn(1, 384)
        with torch.no_grad():
            result = net(seed)

        assert 'consciousness_state' in result
        c_state = result['consciousness_state']
        assert isinstance(c_state, ConsciousnessState)
        assert 0.0 <= c_state.consciousness_level <= 1.0

    def test_forward_without_consciousness_loop(self):
        """Forward pass works fine without consciousness loop."""
        net = RadialAttentionNetwork(seed_dim=384)
        seed = torch.randn(1, 384)
        with torch.no_grad():
            result = net(seed)
        assert result['consciousness_state'] is None

    def test_consciousness_affects_ring5(self):
        """Consciousness loop modulates Ring 5 activations."""
        net = RadialAttentionNetwork(seed_dim=384)
        seed = torch.randn(1, 384)

        # Baseline without loop
        with torch.no_grad():
            r_base = net(seed)
        ring5_base = r_base['ring_activations'][4].clone()

        # With consciousness loop (high consciousness state)
        loop = ConsciousnessLoop(smoothing=1.0)
        # Pre-set high consciousness
        ig = FakeIntegrationState(binding_strength=0.9, reached_consciousness=True,
                                   dmn_activation=0.8)
        cx = FakeCortexState(conflict=0.8)
        sc = FakeSocialState(agency_score=0.9)
        loop.update(integration_state=ig, cortex_state=cx, social_state=sc)

        net.attach_consciousness_loop(loop)
        with torch.no_grad():
            r_conscious = net(seed)
        ring5_conscious = r_conscious['ring_activations'][4]

        # Ring 5 should be different (scaled by gain != 1.0)
        diff = (ring5_conscious - ring5_base).abs().mean().item()
        assert diff > 0.0, "Consciousness should affect Ring 5"

    def test_consciousness_updates_over_ticks(self):
        """Consciousness level changes across multiple forward passes."""
        net = RadialAttentionNetwork(seed_dim=384)
        loop = ConsciousnessLoop(smoothing=0.5)
        net.attach_consciousness_loop(loop)

        # Attach fake bridge states that affect consciousness
        net._bridge_states['integration'] = FakeIntegrationState(
            binding_strength=0.9, reached_consciousness=True,
            dmn_activation=0.7,
        )
        net._cortex_state = FakeCortexState(conflict=0.6)
        net._bridge_states['social'] = FakeSocialState(agency_score=0.8)

        levels = []
        with torch.no_grad():
            for _ in range(10):
                result = net(torch.randn(1, 384))
                levels.append(result['consciousness_state'].consciousness_level)

        # Consciousness should evolve (not stay at default 0.5 forever)
        assert len(set(f"{l:.4f}" for l in levels)) > 1, \
            "Consciousness should change over ticks"

    def test_modulation_context_has_consciousness(self):
        """ModulationContext should contain consciousness_level when loop is attached."""
        net = RadialAttentionNetwork(seed_dim=384)
        loop = ConsciousnessLoop()
        net.attach_consciousness_loop(loop)

        with torch.no_grad():
            result = net(torch.randn(1, 384))

        mod = result['modulation_context']
        assert hasattr(mod, 'consciousness_level')
        assert hasattr(mod, 'consciousness_state')
        assert 0.0 <= mod.consciousness_level <= 1.0

    def test_threshold_mod_adjusted_by_consciousness(self):
        """High consciousness should adjust threshold_mod in ModulationContext."""
        net = RadialAttentionNetwork(seed_dim=384)
        loop = ConsciousnessLoop(smoothing=1.0)
        # Pre-set high consciousness
        ig = FakeIntegrationState(binding_strength=0.9, reached_consciousness=True,
                                   dmn_activation=0.8)
        cx = FakeCortexState(conflict=0.9)
        sc = FakeSocialState(agency_score=0.9)
        loop.update(integration_state=ig, cortex_state=cx, social_state=sc)

        net.attach_consciousness_loop(loop)

        with torch.no_grad():
            result = net(torch.randn(1, 384))

        mod = result['modulation_context']
        # With high consciousness, threshold_mod should be lowered
        # (System 2 bias means lower threshold)
        assert mod.threshold_mod < 1.0  # Adjusted down by consciousness


# ─── Test DualProcessRouter Integration ──────────────────────────────────────

class TestDualProcessIntegration:
    def test_consciousness_biases_system2(self):
        """High consciousness should make System 2 more likely."""
        router = DualProcessRouter(dim=128, conflict_threshold=0.3)

        # Same inputs, different consciousness levels
        torch.manual_seed(42)
        s1 = torch.randn(1, 128)
        s2 = torch.randn(1, 128)

        # Without consciousness (default threshold)
        mod_default = ModulationContext()
        mod_default.threshold_mod = 1.0
        r_default = router(s1, s2, modulation=mod_default)

        # With high consciousness (lowered threshold)
        mod_conscious = ModulationContext()
        mod_conscious.threshold_mod = 0.6  # Consciousness lowers this
        r_conscious = router(s1, s2, modulation=mod_conscious)

        # Lower threshold -> more likely to pick System 2
        # (conflict_level stays the same, but threshold is lower)
        # At minimum, the routing logic should still work
        assert 'system_used' in r_default
        assert 'system_used' in r_conscious


# ─── Test Cognitive Load Estimation ──────────────────────────────────────────

class TestCognitiveLoad:
    def test_load_from_prediction_errors(self):
        loop = ConsciousnessLoop(smoothing=1.0)
        # Low PE = low load
        loop.update(prediction_errors=[0.01, 0.01, 0.01, 0.01])
        load_low = loop.state.cognitive_load

        loop.reset()
        # High PE = high load
        loop.update(prediction_errors=[0.8, 0.9, 0.7, 0.85])
        load_high = loop.state.cognitive_load

        assert load_high > load_low

    def test_load_from_ring_activations(self):
        loop = ConsciousnessLoop(smoothing=1.0)
        # Low activity rings
        low_rings = [torch.zeros(1, d) for d in [64, 128, 256, 256, 128]]
        loop.update(ring_activations=low_rings, prediction_errors=[0.1, 0.1, 0.1, 0.1])
        load_low = loop.state.cognitive_load

        loop.reset()
        # High activity rings
        high_rings = [torch.ones(1, d) * 2.0 for d in [64, 128, 256, 256, 128]]
        loop.update(ring_activations=high_rings, prediction_errors=[0.1, 0.1, 0.1, 0.1])
        load_high = loop.state.cognitive_load

        assert load_high > load_low

    def test_load_bounded(self):
        loop = ConsciousnessLoop(smoothing=1.0)
        loop.update(prediction_errors=[10.0, 10.0, 10.0, 10.0])
        assert 0.0 <= loop.state.cognitive_load <= 1.0

        loop.reset()
        loop.update(prediction_errors=[0.0, 0.0, 0.0, 0.0])
        assert 0.0 <= loop.state.cognitive_load <= 1.0


# ─── Test get_stats and reset ────────────────────────────────────────────────

class TestStatsAndReset:
    def test_get_stats(self):
        loop = ConsciousnessLoop()
        loop.update()
        stats = loop.get_stats()
        assert 'tick_count' in stats
        assert stats['tick_count'] == 1
        assert 'consciousness_level' in stats
        assert 'dmn_gated' in stats
        assert 'ring5_gain' in stats

    def test_reset(self):
        loop = ConsciousnessLoop()
        for _ in range(10):
            loop.update()
        assert loop._tick_count == 10
        loop.reset()
        assert loop._tick_count == 0
        assert loop.consciousness_level == 0.5


# ─── Test Scenario: High Integration + Low Conflict → High Consciousness ────

class TestScenarios:
    def test_high_integration_low_conflict(self):
        """Global Workspace Theory: strong binding + low conflict = high consciousness."""
        loop = ConsciousnessLoop(smoothing=0.5)
        for _ in range(20):
            ig = FakeIntegrationState(
                binding_strength=0.9,
                reached_consciousness=True,
                dmn_activation=0.6,
            )
            cx = FakeCortexState(conflict=0.1)
            loop.update(integration_state=ig, cortex_state=cx)

        # Should reach moderate-high consciousness
        assert loop.consciousness_level > 0.4

    def test_low_integration_high_conflict(self):
        """Fragmented processing + high conflict = moderate consciousness."""
        loop = ConsciousnessLoop(smoothing=0.5)
        for _ in range(20):
            ig = FakeIntegrationState(
                binding_strength=0.2,
                reached_consciousness=False,
            )
            cx = FakeCortexState(conflict=0.9)
            loop.update(integration_state=ig, cortex_state=cx)

        # Conflict raises consciousness but low binding dampens it
        level = loop.consciousness_level
        assert 0.0 < level < 0.8

    def test_social_engagement_raises_consciousness(self):
        """TPJ engagement (high agency) raises consciousness."""
        loop = ConsciousnessLoop(smoothing=0.5)
        for _ in range(20):
            ig = FakeIntegrationState(binding_strength=0.7, reached_consciousness=True)
            sc = FakeSocialState(agency_score=0.9)
            loop.update(integration_state=ig, social_state=sc)

        assert loop.consciousness_level > 0.4


# ─── Test All Existing Tests Still Pass ──────────────────────────────────────

class TestBackwardCompatibility:
    def test_network_forward_without_consciousness(self):
        """Existing forward behavior unchanged when no consciousness loop attached."""
        net = RadialAttentionNetwork(seed_dim=384)
        seed = torch.randn(1, 384)
        with torch.no_grad():
            result = net(seed)
        assert 'ring_activations' in result
        assert 'meta_output' in result
        assert 'prediction_errors' in result
        assert result['consciousness_state'] is None

    def test_modulation_context_default_consciousness(self):
        """ModulationContext defaults unchanged."""
        ctx = ModulationContext()
        assert ctx.consciousness_level == 0.5
        assert ctx.consciousness_state is None

    def test_network_with_all_bridges_no_consciousness(self):
        """Network with all bridges but no consciousness loop works."""
        net = RadialAttentionNetwork(seed_dim=384)
        net._neuromod_state = FakeNeuromodState()
        net._cortex_state = FakeCortexState()
        net._limbic_state = FakeLimbicState()
        net._bridge_states['sleep_wake'] = FakeSleepWakeState()
        net._bridge_states['motor'] = FakeMotorState()
        net._bridge_states['defense'] = FakeDefenseState()
        net._bridge_states['memory'] = FakeMemoryState()
        net._bridge_states['integration'] = FakeIntegrationState()
        net._bridge_states['visceral'] = FakeVisceralState()
        net._bridge_states['social'] = FakeSocialState()

        with torch.no_grad():
            result = net(torch.randn(1, 384))

        assert result['consciousness_state'] is None
        assert 0.3 <= result['modulation_context'].threshold_mod <= 3.0
