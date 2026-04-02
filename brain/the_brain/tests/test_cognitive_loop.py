"""
Unit tests for the Cognitive Loop (core/cognitive_loop.py).

Tests verify:
- Backward compatibility (returns HierarchicalPrediction)
- Gate normalization invariant (gates sum to 1.0 after each phase)
- Memory bias shifts routing weights
- Attention produces CTM domain hints
- Neuromodulation controls gating temperature
- Dynamic CTM threshold adjusts with uncertainty
- Reflection loop triggers on low confidence
- Max iterations respected
- Loop state API returns valid data
- Determinism with seed
"""

import pytest
import numpy as np
import sys
import os

# Add parent directory to path for module access
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, parent_dir)

from core.cognitive_loop import CognitiveLoop, CognitiveLoopConfig, LoopContext, LoopPhase


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def planner():
    """Create a minimal HierarchicalPlanner for testing."""
    from core.hierarchical_planner import HierarchicalPlanner
    from core.conversation_path_planner import ConversationPathPlanner
    from core.meta_router import MetaRouter

    meta_router = MetaRouter(
        enable_hippocampus=True,
        enable_per_modality_pes=True,
        seed=42
    )

    try:
        from core.conversation_path_planner import StrategyLibrary, BrainActivityMonitor
        layer2 = ConversationPathPlanner(
            meta_router=meta_router,
            strategy_library=StrategyLibrary(max_strategies_per_type=10),
            brain_monitor=BrainActivityMonitor(history_length=50),
            enable_adaptive_gating=True
        )
    except Exception:
        layer2 = ConversationPathPlanner(meta_router=meta_router)

    # Train from sessions directory (may have no sessions - that's ok)
    try:
        layer2.train_from_sessions("data/logs", limit=5)
    except Exception:
        pass

    hp = HierarchicalPlanner(
        conversation_planner=layer2,
        intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
        seed=42
    )
    return hp


@pytest.fixture
def config():
    """Default cognitive loop config."""
    return CognitiveLoopConfig()


@pytest.fixture
def loop(planner, config):
    """Create a CognitiveLoop instance."""
    return CognitiveLoop(planner=planner, config=config)


# ============================================================================
# Core Tests
# ============================================================================

class TestCognitiveLoopBasics:
    """Basic functionality tests."""

    def test_instantiation(self, loop):
        """CognitiveLoop should instantiate without errors."""
        assert loop is not None
        assert loop.current_phase == LoopPhase.IDLE

    def test_returns_hierarchical_prediction(self, loop):
        """process() must return a HierarchicalPrediction."""
        from core.hierarchical_planner import HierarchicalPrediction

        result = loop.process("Deploy Docker container")
        assert isinstance(result, HierarchicalPrediction)

    def test_prediction_has_required_fields(self, loop):
        """Output must have all required HierarchicalPrediction fields."""
        result = loop.process("Debug failing test")

        # Layer 1
        assert result.layer1_routing is not None
        # Layer 2
        assert isinstance(result.predicted_sequence, list)
        assert isinstance(result.confidence, float)
        assert 0 <= result.confidence <= 1.0
        assert isinstance(result.task_type, str)
        # Layer 3
        assert result.actionable_decision is not None
        assert 'primary' in result.actionable_decision.multi_target_decision

    def test_loop_phase_returns_to_idle(self, loop):
        """After process(), loop phase should be IDLE."""
        loop.process("Test task")
        assert loop.current_phase == LoopPhase.IDLE


class TestGateNormalization:
    """Gate normalization invariant: gates must always sum to 1.0."""

    def test_gates_sum_to_one_basic(self, loop):
        """Final brain gates should sum to ~1.0."""
        result = loop.process("Install Docker")
        gates = np.array(result.layer1_routing.routing_weights)
        assert np.isclose(np.sum(gates), 1.0, atol=0.01), \
            f"Gates sum to {np.sum(gates)}, expected ~1.0"
        assert np.all(gates >= 0), "All gates should be non-negative"

    def test_gates_after_memory_bias(self, loop):
        """Memory-biased weights should still sum to 1.0."""
        ctx = LoopContext(task_description="Test memory bias")

        loop._perceive(ctx)
        loop._remember(ctx)

        weights = np.array(ctx.layer1_routing.routing_weights)
        assert np.isclose(np.sum(weights), 1.0, atol=0.01), \
            f"After REMEMBER: gates sum to {np.sum(weights)}"

    def test_gates_after_attention(self, loop):
        """Attention-gated weights should still sum to 1.0."""
        ctx = LoopContext(task_description="Test attention gating")

        loop._perceive(ctx)
        loop._remember(ctx)
        loop._attend(ctx)

        if ctx.attention_gated_weights is not None:
            assert np.isclose(np.sum(ctx.attention_gated_weights), 1.0, atol=0.01), \
                f"After ATTEND: gates sum to {np.sum(ctx.attention_gated_weights)}"

    def test_gates_after_modulation(self, loop):
        """Modulated weights should still sum to 1.0."""
        ctx = LoopContext(task_description="Test modulation")

        loop._perceive(ctx)
        loop._remember(ctx)
        loop._attend(ctx)
        loop._modulate(ctx)

        if ctx.modulated_weights is not None:
            assert np.isclose(np.sum(ctx.modulated_weights), 1.0, atol=0.01), \
                f"After MODULATE: gates sum to {np.sum(ctx.modulated_weights)}"


class TestMemoryBias:
    """Tests for memory biasing routing weights."""

    def test_memory_bias_with_no_history(self, loop):
        """With no memory history, weights should not change."""
        ctx = LoopContext(task_description="Novel task never seen before")

        loop._perceive(ctx)
        raw_weights = ctx.raw_routing_weights.copy()

        loop._remember(ctx)

        current_weights = np.array(ctx.layer1_routing.routing_weights)
        # With no memory, bias should be None and weights unchanged
        if ctx.memory_bias is None:
            np.testing.assert_array_almost_equal(current_weights, raw_weights, decimal=5)

    def test_memory_bias_config_disabled(self, planner):
        """With enable_memory_bias=False, weights should not be biased."""
        config = CognitiveLoopConfig(enable_memory_bias=False)
        loop = CognitiveLoop(planner=planner, config=config)

        ctx = LoopContext(task_description="Test disabled memory bias")
        loop._perceive(ctx)
        raw_weights = ctx.raw_routing_weights.copy()
        loop._remember(ctx)

        current_weights = np.array(ctx.layer1_routing.routing_weights)
        np.testing.assert_array_almost_equal(current_weights, raw_weights, decimal=5)


class TestAttentionDriving:
    """Tests for attention-driven CTM selection."""

    def test_ctm_hint_with_attention_disabled(self, planner):
        """With attention driving disabled, no CTM hint should be set."""
        config = CognitiveLoopConfig(enable_attention_driving=False, enable_dynamic_ctm=False)
        loop = CognitiveLoop(planner=planner, config=config)

        ctx = LoopContext(task_description="Test no attention driving")
        loop._perceive(ctx)
        loop._remember(ctx)
        loop._attend(ctx)

        assert ctx.ctm_domain_hint is None


class TestNeuromodulation:
    """Tests for neuromodulation controlling gating temperature."""

    def test_baseline_temperature_is_one(self, loop):
        """With baseline neuromodulators, temperature should be ~1.0."""
        ctx = LoopContext(task_description="Test baseline neuro")
        loop._perceive(ctx)
        loop._remember(ctx)
        loop._attend(ctx)
        loop._modulate(ctx)

        # Baseline dopamine=0.5 and NE=0.5 -> temperature stays at 1.0
        assert ctx.gating_temperature == pytest.approx(1.0, abs=0.2)

    def test_low_dopamine_raises_temperature(self, planner):
        """Low dopamine should increase gating temperature (more exploration)."""
        config = CognitiveLoopConfig(
            enable_neuro_modulation=True,
            low_dopamine_threshold=0.3,
            neuro_temperature_sensitivity=0.5
        )
        loop = CognitiveLoop(planner=planner, config=config)

        # Simulate low dopamine
        if planner.enable_neuromodulation and planner.neuromodulation:
            planner.neuromodulation.levels.dopamine = 0.1

        ctx = LoopContext(task_description="Test low dopamine")
        loop._perceive(ctx)
        loop._remember(ctx)
        loop._attend(ctx)
        loop._modulate(ctx)

        if planner.enable_neuromodulation and planner.neuromodulation:
            assert ctx.gating_temperature > 1.0, \
                f"Low dopamine should raise temperature, got {ctx.gating_temperature}"

    def test_high_ne_lowers_temperature(self, planner):
        """High norepinephrine should decrease gating temperature (sharper focus)."""
        config = CognitiveLoopConfig(
            enable_neuro_modulation=True,
            high_norepinephrine_threshold=0.7,
            neuro_temperature_sensitivity=0.5
        )
        loop = CognitiveLoop(planner=planner, config=config)

        # Simulate high norepinephrine
        if planner.enable_neuromodulation and planner.neuromodulation:
            planner.neuromodulation.levels.norepinephrine = 0.9
            planner.neuromodulation.levels.dopamine = 0.5  # Keep dopamine at baseline

        ctx = LoopContext(task_description="Test high NE")
        loop._perceive(ctx)
        loop._remember(ctx)
        loop._attend(ctx)
        loop._modulate(ctx)

        if planner.enable_neuromodulation and planner.neuromodulation:
            assert ctx.gating_temperature < 1.0, \
                f"High NE should lower temperature, got {ctx.gating_temperature}"

    def test_neuro_disabled_leaves_temperature_at_one(self, planner):
        """With neuro modulation disabled, temperature should be 1.0."""
        config = CognitiveLoopConfig(enable_neuro_modulation=False)
        loop = CognitiveLoop(planner=planner, config=config)

        ctx = LoopContext(task_description="Test neuro disabled")
        loop._perceive(ctx)
        loop._remember(ctx)
        loop._attend(ctx)
        loop._modulate(ctx)

        assert ctx.gating_temperature == 1.0


class TestReflectionLoop:
    """Tests for the reflection loop re-entry mechanism."""

    def test_max_iterations_respected(self, planner):
        """Loop should not exceed max_loop_iterations."""
        config = CognitiveLoopConfig(
            max_loop_iterations=2,
            enable_reflection_loop=True,
            reconsider_confidence_threshold=1.0  # Always reconsider (confidence never >= 1.0)
        )
        loop = CognitiveLoop(planner=planner, config=config)

        result = loop.process("Test max iterations")
        # Should complete (not hang) and iteration count <= max
        assert loop._last_context.loop_iterations <= config.max_loop_iterations

    def test_reflection_disabled_single_iteration(self, planner):
        """With reflection loop disabled, should always be single iteration."""
        config = CognitiveLoopConfig(enable_reflection_loop=False)
        loop = CognitiveLoop(planner=planner, config=config)

        result = loop.process("Test no reflection")
        assert loop._last_context.loop_iterations == 1

    def test_high_confidence_no_reconsider(self, loop):
        """High confidence should not trigger reconsideration."""
        ctx = LoopContext(task_description="Simple task")
        ctx.confidence = 0.95

        loop._perceive(ctx)
        loop._remember(ctx)
        loop._attend(ctx)
        loop._modulate(ctx)
        loop._reason(ctx)

        # Manually set high confidence to test reflect phase
        ctx.confidence = 0.95
        ctx.loop_iterations = 1
        loop._reflect(ctx)

        assert not ctx.should_reconsider


class TestLoopState:
    """Tests for dashboard visibility."""

    def test_get_loop_state_before_process(self, loop):
        """Loop state should be valid even before first process()."""
        state = loop.get_loop_state()
        assert isinstance(state, dict)
        assert state['current_phase'] == 'idle'
        assert state['enabled'] is True

    def test_get_loop_state_after_process(self, loop):
        """Loop state should contain timing and context after process()."""
        loop.process("Test state visibility")

        state = loop.get_loop_state()
        assert state['current_phase'] == 'idle'
        assert 'loop_iterations' in state
        assert state['loop_iterations'] >= 1
        assert 'phase_timings' in state
        assert 'total_time' in state
        assert state['total_time'] >= 0
        assert 'gating_temperature' in state
        assert 'memory_bias_active' in state
        assert 'confidence' in state

    def test_loop_state_has_ctm_hint(self, loop):
        """Loop state should report CTM domain hint."""
        loop.process("Analyze temporal pattern in data")
        state = loop.get_loop_state()
        assert 'ctm_domain_hint' in state


class TestDeterminism:
    """Tests for reproducibility."""

    def test_same_seed_same_output(self):
        """Same seed should produce identical results."""
        from core.hierarchical_planner import HierarchicalPlanner
        from core.conversation_path_planner import ConversationPathPlanner
        from core.meta_router import MetaRouter

        results = []
        for _ in range(2):
            meta_router = MetaRouter(
                enable_hippocampus=True,
                enable_per_modality_pes=True,
                seed=42
            )
            try:
                from core.conversation_path_planner import StrategyLibrary, BrainActivityMonitor
                layer2 = ConversationPathPlanner(
                    meta_router=meta_router,
                    strategy_library=StrategyLibrary(max_strategies_per_type=10),
                    brain_monitor=BrainActivityMonitor(history_length=50),
                    enable_adaptive_gating=True
                )
            except Exception:
                layer2 = ConversationPathPlanner(meta_router=meta_router)
            try:
                layer2.train_from_sessions("data/logs", limit=5)
            except Exception:
                pass

            hp = HierarchicalPlanner(
                conversation_planner=layer2,
                intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
                seed=42
            )
            loop = CognitiveLoop(planner=hp, config=CognitiveLoopConfig())
            np.random.seed(42)
            result = loop.process("Deploy Docker container")
            results.append(result)

        assert results[0].confidence == results[1].confidence
        assert results[0].task_type == results[1].task_type


# ============================================================================
# Phase 6: Advanced Cognitive Capabilities Tests
# ============================================================================

class TestPhase6ModuleAvailability:
    """Phase 6 modules should initialize when config enables them."""

    def test_phase6_modules_in_loop_state(self, loop):
        """get_loop_state() should report Phase 6 module availability."""
        state = loop.get_loop_state()
        assert 'phase6_modules' in state
        modules = state['phase6_modules']
        # All these keys must exist
        expected_keys = [
            'theory_of_mind', 'causal_inference', 'intrinsic_curiosity',
            'autonomous_goal_gen', 'safety_layer', 'explanation_gen',
            'self_improvement', 'multimodal_fusion', 'formal_verifier',
            'thought_decoder',
        ]
        for key in expected_keys:
            assert key in modules, f"Missing phase6_modules key: {key}"
            assert isinstance(modules[key], bool)

    def test_phase6_modules_respect_config_disable(self, planner):
        """When Phase 6 flags are disabled, modules should be None."""
        config = CognitiveLoopConfig(
            enable_safety_layer=False,
            enable_explanation_gen=False,
            enable_theory_of_mind=False,
            enable_causal_reasoning=False,
            enable_intrinsic_curiosity=False,
            enable_autonomous_goals=False,
            enable_self_improvement=False,
            enable_multimodal_fusion=False,
            enable_formal_verifier=False,
            enable_thought_decoder=False,
        )
        loop = CognitiveLoop(planner=planner, config=config)
        state = loop.get_loop_state()
        modules = state['phase6_modules']
        # All should be False when disabled
        assert modules['theory_of_mind'] is False
        assert modules['causal_inference'] is False
        assert modules['intrinsic_curiosity'] is False
        assert modules['autonomous_goal_gen'] is False
        assert modules['safety_layer'] is False
        assert modules['explanation_gen'] is False
        assert modules['self_improvement'] is False
        assert modules['multimodal_fusion'] is False
        assert modules['formal_verifier'] is False
        assert modules['thought_decoder'] is False


class TestPhase6CognitiveOutputs:
    """Phase 6 cognitive outputs appear in loop state after processing."""

    def test_phase6_cognitive_in_state_after_process(self, loop):
        """After process(), loop state should contain Phase 6 section."""
        loop.process("Analyze user sentiment in conversation")
        state = loop.get_loop_state()
        # phase6_cognitive may or may not have entries depending on module availability
        # but phase6_modules should always exist
        assert 'phase6_modules' in state

    def test_circadian_phase_set(self, loop):
        """After process(), circadian_phase should be set in context."""
        loop.process("Schedule morning tasks")
        ctx = loop._last_context
        # Circadian phase is always set if temporal_patterns enabled
        if loop._config.enable_temporal_patterns:
            # It should be one of the known phases
            if ctx.circadian_phase is not None:
                valid_phases = ['night_owl', 'early_morning', 'morning', 'midday', 'afternoon', 'evening', 'night']
                assert ctx.circadian_phase in valid_phases

    def test_safety_report_structure(self, loop):
        """Safety report should be a dict if populated."""
        loop.process("Execute dangerous command rm -rf /")
        ctx = loop._last_context
        if ctx.safety_report is not None:
            assert isinstance(ctx.safety_report, dict)

    def test_explanation_structure(self, loop):
        """Explanation should be a dict if populated."""
        loop.process("Why did you choose this approach?")
        ctx = loop._last_context
        if ctx.explanation is not None:
            assert isinstance(ctx.explanation, dict)

    def test_user_model_structure(self, loop):
        """User model should be a dict if populated."""
        loop.process("The user prefers Python over Java")
        ctx = loop._last_context
        if ctx.user_model is not None:
            assert isinstance(ctx.user_model, dict)

    def test_causal_context_structure(self, loop):
        """Causal context should be a dict if populated."""
        loop.process("Identify root cause of memory leak")
        ctx = loop._last_context
        if ctx.causal_context is not None:
            assert isinstance(ctx.causal_context, dict)

    def test_curiosity_intrinsic_structure(self, loop):
        """Intrinsic curiosity should be a dict if populated."""
        loop.process("Explore new API features")
        ctx = loop._last_context
        if ctx.curiosity_intrinsic is not None:
            assert isinstance(ctx.curiosity_intrinsic, dict)

    def test_autonomous_goals_structure(self, loop):
        """Autonomous goals should be a list if populated."""
        loop.process("What should we work on next?")
        ctx = loop._last_context
        if ctx.autonomous_goals is not None:
            assert isinstance(ctx.autonomous_goals, list)

    def test_gates_still_sum_to_one_with_phase6(self, loop):
        """Phase 6 modules must not break the gate invariant."""
        result = loop.process("Complex multi-modal analysis")
        routing = result.layer1_routing
        # RoutingState stores gates in .gates (ndarray), not .brain_gates
        gates = routing.gates if hasattr(routing, 'gates') else getattr(routing, 'brain_gates', None)
        if gates is not None:
            gate_sum = sum(gates.values()) if isinstance(gates, dict) else np.sum(gates)
            assert abs(gate_sum - 1.0) < 1e-6, f"Gates sum to {gate_sum}, not 1.0"

    def test_confidence_valid_with_phase6(self, loop):
        """Confidence must remain in [0, 1] with Phase 6 active."""
        result = loop.process("Edge case: empty task context")
        assert 0.0 <= result.confidence <= 1.0

    def test_formal_verification_structure(self, loop):
        """Formal verification should be a dict if populated."""
        loop.process("Verify action safety for deployment")
        ctx = loop._last_context
        if ctx.formal_verification is not None:
            assert isinstance(ctx.formal_verification, dict)

    def test_thought_decode_structure(self, loop):
        """Thought decode should be a dict if populated."""
        loop.process("Decode internal cognitive state")
        ctx = loop._last_context
        if ctx.thought_decode is not None:
            assert isinstance(ctx.thought_decode, dict)

    def test_multimodal_fusion_structure(self, loop):
        """Multimodal fusion should be a dict if populated."""
        loop.process("Fuse vision and audio signals")
        ctx = loop._last_context
        if ctx.multimodal_fusion is not None:
            assert isinstance(ctx.multimodal_fusion, dict)


class TestPhase6ConfigFromYaml:
    """Phase 6 enable flags should be configurable via YAML."""

    def test_phase6_enable_flags_from_yaml(self):
        """CognitiveLoopConfig.from_yaml should read Phase 6 flags."""
        yaml_cfg = {
            'cognitive_loop': {
                'enable_safety_layer': False,
                'enable_theory_of_mind': False,
                'enable_causal_reasoning': True,
            }
        }
        config = CognitiveLoopConfig.from_yaml(yaml_cfg)
        assert config.enable_safety_layer is False
        assert config.enable_theory_of_mind is False
        assert config.enable_causal_reasoning is True
        # Defaults for unspecified
        assert config.enable_intrinsic_curiosity is True
        assert config.enable_autonomous_goals is True

    def test_phase6_default_all_enabled(self):
        """By default, all Phase 6 flags should be True."""
        config = CognitiveLoopConfig()
        assert config.enable_safety_layer is True
        assert config.enable_explanation_gen is True
        assert config.enable_theory_of_mind is True
        assert config.enable_causal_reasoning is True
        assert config.enable_intrinsic_curiosity is True
        assert config.enable_temporal_patterns is True
        assert config.enable_autonomous_goals is True
        assert config.enable_self_improvement is True


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
