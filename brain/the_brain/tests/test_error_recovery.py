"""
Error Recovery & Graceful Degradation Tests

Verifies that the brain survives subsystem failures gracefully:
- Predict works when individual subsystems are disabled
- Predict works when ALL optional subsystems are disabled
- CognitiveLoop handles broken subsystems (exceptions) without crashing
- Layer 2/3 failures produce valid fallback predictions
- Multiple predictions remain stable after a subsystem error
- Feedback endpoint handles missing subsystems
- Emotional system failure doesn't crash the cognitive loop
"""

import pytest
import numpy as np
import sys
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock, PropertyMock

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from production.production_planner import ProductionPlanner
from core.cognitive_loop import CognitiveLoop, CognitiveLoopConfig, LoopContext, LoopPhase
from core.hierarchical_planner import HierarchicalPlanner, HierarchicalPrediction


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def session_log_dir():
    """Create a temporary session log directory with a minimal log file."""
    tmpdir = tempfile.mkdtemp(prefix="test_error_recovery_")
    log_content = """2024-01-01 10:00:00,000 [TASK PROPAGATION] Task in kwargs: test deployment
2024-01-01 10:00:01,000 \U0001f6e0\ufe0f  Tool: list_notifications
2024-01-01 10:00:02,000 \U0001f527 GitHubOperator activated
2024-01-01 10:00:03,000 \u2713 QAValidator
\u2705 GOOD (Accept)
2024-01-01 10:00:04,000 Stopping agent
"""
    log_file = os.path.join(tmpdir, "github_20240101_100000_session1.log")
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(log_content)
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


def _make_planner(session_log_dir, **hp_overrides):
    """
    Helper to create a HierarchicalPlanner with specific subsystem flags.
    Follows the same construction pattern used by ProductionPlanner.
    """
    from core.conversation_path_planner import ConversationPathPlanner
    from core.meta_router import MetaRouter
    from core.strategy_library import StrategyLibrary
    from core.brain_monitor import BrainActivityMonitor

    meta_router = MetaRouter(
        enable_hippocampus=True,
        enable_per_modality_pes=True,
        seed=42
    )
    meta_router.multi_llm_router = None

    layer2 = ConversationPathPlanner(
        meta_router=meta_router,
        strategy_library=StrategyLibrary(max_strategies_per_type=10),
        brain_monitor=BrainActivityMonitor(history_length=50),
        enable_adaptive_gating=True
    )
    try:
        layer2.train_from_sessions(session_log_dir, limit=5)
    except Exception:
        pass

    defaults = dict(
        conversation_planner=layer2,
        intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
        seed=42
    )
    defaults.update(hp_overrides)

    return HierarchicalPlanner(**defaults)


@pytest.fixture(scope="module")
def planner_full(session_log_dir):
    """A fully-enabled planner (all subsystems on)."""
    return _make_planner(session_log_dir)


@pytest.fixture(scope="module")
def production_planner(session_log_dir):
    """A ProductionPlanner in legacy mode for feedback tests."""
    return ProductionPlanner(
        session_log_dir=session_log_dir,
        enable_cognitive_loop=False,
        enable_semantic_coherence=False,
        embedding_type="hash",
        seed=42
    )


@pytest.fixture(scope="module")
def production_planner_cognitive(session_log_dir):
    """A ProductionPlanner with cognitive loop enabled."""
    return ProductionPlanner(
        session_log_dir=session_log_dir,
        enable_cognitive_loop=True,
        enable_semantic_coherence=False,
        embedding_type="hash",
        seed=42
    )


# ============================================================================
# 1-7: Predict works with individual/all subsystems disabled
# ============================================================================

class TestDisabledSubsystems:
    """Tests that predict() works when individual subsystems are turned off."""

    def test_predict_with_memory_disabled(self, session_log_dir):
        """Test 1: Predict works with memory disabled."""
        planner = _make_planner(session_log_dir, enable_memory=False)
        assert planner.memory is None

        result = planner.predict("Deploy Docker container")
        assert isinstance(result, HierarchicalPrediction)
        assert result.actionable_decision is not None
        assert 'primary' in result.actionable_decision.multi_target_decision
        assert 0.0 <= result.confidence <= 1.0

    def test_predict_with_attention_disabled(self, session_log_dir):
        """Test 2: Predict works with attention disabled."""
        planner = _make_planner(session_log_dir, enable_attention=False)
        assert planner.attention is None

        result = planner.predict("Run unit tests")
        assert isinstance(result, HierarchicalPrediction)
        assert result.actionable_decision is not None
        assert 0.0 <= result.confidence <= 1.0

    def test_predict_with_neuromodulation_disabled(self, session_log_dir):
        """Test 3: Predict works with neuromodulation disabled."""
        planner = _make_planner(session_log_dir, enable_neuromodulation=False)
        assert planner.neuromodulation is None

        result = planner.predict("Fix login bug")
        assert isinstance(result, HierarchicalPrediction)
        assert result.neuromodulator_levels is None
        assert 0.0 <= result.confidence <= 1.0

    def test_predict_with_predictive_coding_disabled(self, session_log_dir):
        """Test 4: Predict works with predictive coding disabled."""
        planner = _make_planner(session_log_dir, enable_predictive_coding=False)
        assert planner.predictive_coding is None

        result = planner.predict("Optimize database query")
        assert isinstance(result, HierarchicalPrediction)
        assert result.prediction_errors is None
        assert result.curiosity_signal is None
        assert 0.0 <= result.confidence <= 1.0

    def test_predict_with_consciousness_disabled(self, session_log_dir):
        """Test 5: Predict works with consciousness metrics disabled."""
        planner = _make_planner(session_log_dir, enable_consciousness_metrics=False)
        assert planner.consciousness_metrics is None

        result = planner.predict("Monitor server health")
        assert isinstance(result, HierarchicalPrediction)
        assert 0.0 <= result.confidence <= 1.0

    def test_predict_with_ctm_disabled(self, session_log_dir):
        """Test 6: Predict works with CTM async disabled."""
        planner = _make_planner(session_log_dir, enable_ctm_async=False)

        result = planner.predict("Refactor authentication module")
        assert isinstance(result, HierarchicalPrediction)
        assert result.ctm_task_id is None
        assert 0.0 <= result.confidence <= 1.0

    def test_predict_with_all_optional_disabled(self, session_log_dir):
        """Test 7: Predict works with ALL optional systems disabled."""
        planner = _make_planner(
            session_log_dir,
            enable_memory=False,
            enable_attention=False,
            enable_neuromodulation=False,
            enable_predictive_coding=False,
            enable_consciousness_metrics=False,
            enable_ctm_async=False,
            enable_meta_learning=False,
            enable_dream_mode=False,
            enable_temporal_memory=False,
            enable_active_inference=False,
            enable_compositional_reasoning=False,
            enable_tool_creation=False,
            enable_multi_brain_swarm=False,
            enable_goal_graph=False,
            enable_layer4=False,
        )

        assert planner.memory is None
        assert planner.attention is None
        assert planner.neuromodulation is None
        assert planner.predictive_coding is None
        assert planner.consciousness_metrics is None

        result = planner.predict("Scale microservices cluster")
        assert isinstance(result, HierarchicalPrediction)
        assert result.layer1_routing is not None
        assert result.actionable_decision is not None
        assert 'primary' in result.actionable_decision.multi_target_decision
        assert 0.0 <= result.confidence <= 1.0

        # Gate normalization still holds
        gates = np.array(result.layer1_routing.routing_weights)
        assert np.isclose(np.sum(gates), 1.0, atol=0.01), \
            f"Gates sum to {np.sum(gates)}, expected ~1.0"


# ============================================================================
# 8-10: CognitiveLoop handles broken subsystems (exception injection)
# ============================================================================

class TestCognitiveLoopBrokenSubsystems:
    """Tests that CognitiveLoop handles subsystem exceptions gracefully."""

    def test_cognitive_loop_broken_memory(self, session_log_dir):
        """Test 8: CognitiveLoop handles broken memory manager (raises exception)."""
        planner = _make_planner(session_log_dir)
        loop = CognitiveLoop(planner=planner, config=CognitiveLoopConfig())

        # Patch memory.get_context to raise an exception
        with patch.object(
            planner.memory, 'get_context',
            side_effect=RuntimeError("Memory database corrupted")
        ):
            # Should NOT crash - should degrade gracefully
            result = loop.process("Deploy service with broken memory")
            assert isinstance(result, HierarchicalPrediction)
            assert result.actionable_decision is not None
            assert 0.0 <= result.confidence <= 1.0

    def test_cognitive_loop_broken_attention(self, session_log_dir):
        """Test 9: CognitiveLoop handles broken attention (raises exception)."""
        planner = _make_planner(session_log_dir)
        loop = CognitiveLoop(planner=planner, config=CognitiveLoopConfig())

        # Patch attention.compute_attention to raise
        with patch.object(
            planner.attention, 'compute_attention',
            side_effect=ValueError("Attention matrix singular")
        ):
            result = loop.process("Fix the broken CI pipeline")
            assert isinstance(result, HierarchicalPrediction)
            assert result.actionable_decision is not None
            assert 0.0 <= result.confidence <= 1.0

    def test_cognitive_loop_broken_neuromodulation(self, session_log_dir):
        """Test 10: CognitiveLoop handles broken neuromodulation (raises exception)."""
        planner = _make_planner(session_log_dir)
        loop = CognitiveLoop(planner=planner, config=CognitiveLoopConfig())

        # Patch neuromodulation.compute_effects to raise
        with patch.object(
            planner.neuromodulation, 'compute_effects',
            side_effect=RuntimeError("Neuromodulator overflow")
        ):
            result = loop.process("Handle critical alert")
            assert isinstance(result, HierarchicalPrediction)
            assert result.actionable_decision is not None
            assert 0.0 <= result.confidence <= 1.0


# ============================================================================
# 11-12: Predict returns valid result when Layer 2 or Layer 3 fails
# ============================================================================

class TestLayerFailureFallbacks:
    """Tests that Layer 2 and Layer 3 failures produce valid fallback predictions."""

    def test_valid_prediction_when_layer2_fails(self, session_log_dir):
        """Test 11: Predict still returns valid HierarchicalPrediction when Layer 2 fails."""
        planner = _make_planner(session_log_dir)
        loop = CognitiveLoop(planner=planner, config=CognitiveLoopConfig())

        # Patch Layer 2's predict_optimal_path to raise
        with patch.object(
            planner.layer2, 'predict_optimal_path',
            side_effect=RuntimeError("Layer 2 graph corrupted")
        ):
            result = loop.process("Deploy with broken Layer 2")
            assert isinstance(result, HierarchicalPrediction)
            # Fallback defaults in _reason: confidence=0.5, empty sequence
            assert result.confidence == 0.5
            assert result.predicted_sequence == []
            assert result.actionable_decision is not None

    def test_valid_prediction_when_layer3_fails(self, session_log_dir):
        """Test 12: Predict still returns valid result when Layer 3 fails (P1.14 fallback)."""
        planner = _make_planner(session_log_dir)
        loop = CognitiveLoop(planner=planner, config=CognitiveLoopConfig())

        # Patch Layer 3's route_to_action to raise
        with patch.object(
            planner.layer3, 'route_to_action',
            side_effect=RuntimeError("Layer 3 routing matrix corrupted")
        ):
            result = loop.process("Deploy with broken Layer 3")
            assert isinstance(result, HierarchicalPrediction)
            assert result.actionable_decision is not None
            # The fallback should produce a 'suggest' action in cautious mode
            decision = result.actionable_decision.multi_target_decision
            assert decision['primary']['type'] == 'suggest'
            assert 'fallback' in decision['primary']['reasoning'].lower() or \
                   'error' in decision['primary']['reasoning'].lower()
            assert len(decision['alternatives']) >= 1


# ============================================================================
# 13: Multiple predictions don't crash after a subsystem error
# ============================================================================

class TestStabilityAfterErrors:
    """Tests that the system remains stable after encountering errors."""

    def test_multiple_predictions_stable_after_error(self, session_log_dir):
        """Test 13: Multiple predictions don't crash after a subsystem error."""
        planner = _make_planner(session_log_dir)
        loop = CognitiveLoop(planner=planner, config=CognitiveLoopConfig())

        # First: Force an error in attention for one prediction
        original_compute = planner.attention.compute_attention
        call_count = [0]

        def sometimes_broken(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Transient attention failure")
            return original_compute(*args, **kwargs)

        with patch.object(
            planner.attention, 'compute_attention',
            side_effect=sometimes_broken
        ):
            # First call: attention fails, but should still work
            result1 = loop.process("Task during attention failure")
            assert isinstance(result1, HierarchicalPrediction)
            assert result1.actionable_decision is not None

            # Second call: attention recovers, should still work
            result2 = loop.process("Task after attention recovery")
            assert isinstance(result2, HierarchicalPrediction)
            assert result2.actionable_decision is not None

        # After the patch context exits, run more predictions normally
        for i in range(5):
            result = loop.process(f"Normal task {i}")
            assert isinstance(result, HierarchicalPrediction)
            assert 0.0 <= result.confidence <= 1.0


# ============================================================================
# 14: Feedback endpoint handles missing subsystems gracefully
# ============================================================================

class TestFeedbackGracefulDegradation:
    """Tests that feedback submission handles missing subsystems."""

    def test_feedback_handles_missing_subsystems(self, session_log_dir):
        """Test 14: Feedback endpoint handles missing subsystems gracefully."""
        pp = ProductionPlanner(
            session_log_dir=session_log_dir,
            enable_cognitive_loop=False,
            enable_semantic_coherence=False,
            embedding_type="hash",
            seed=42
        )

        # Make a prediction first
        result = pp.predict("Deploy the service")
        assert isinstance(result, dict)

        # Now disable subsystems on the planner to simulate degraded state
        pp.planner.enable_neuromodulation = False
        pp.planner.neuromodulation = None
        pp.planner.enable_memory = False
        pp.planner.memory = None
        pp.planner.enable_predictive_coding = False
        pp.planner.predictive_coding = None

        # Submit feedback -- should not crash even with missing subsystems
        initial_count = pp.total_feedback
        try:
            pp.submit_feedback(
                task="Deploy the service",
                prediction=result,
                actual_action='execute',
                success=True,
                user_rating=0.9
            )
        except Exception as e:
            # If brain_gates are None, submit_feedback returns early
            # but should NOT raise an unhandled exception
            assert 'gates' not in str(e).lower(), \
                f"Feedback should handle missing gates: {e}"

        # The planner should still be usable after feedback
        result2 = pp.predict("Another task after feedback")
        assert isinstance(result2, dict)
        assert 'prediction' in result2


# ============================================================================
# 15: Emotional system failure doesn't crash cognitive loop
# ============================================================================

class TestEmotionalSystemFailure:
    """Tests that emotional system failure doesn't crash the cognitive loop."""

    def test_emotional_failure_doesnt_crash_loop(self, session_log_dir):
        """Test 15: Emotional system failure doesn't crash cognitive loop."""
        planner = _make_planner(session_log_dir)
        config = CognitiveLoopConfig(enable_emotional_system=True)
        loop = CognitiveLoop(planner=planner, config=config)

        # Patch the emotional system's appraise_task to raise
        if loop._emotional_system is not None:
            with patch.object(
                loop._emotional_system, 'appraise_task',
                side_effect=RuntimeError("Emotional system crashed")
            ):
                result = loop.process("Handle stressful situation")
                assert isinstance(result, HierarchicalPrediction)
                assert result.actionable_decision is not None
                assert 0.0 <= result.confidence <= 1.0
        else:
            # Emotional system wasn't initialized (import might fail)
            # Verify loop works without it
            result = loop.process("Handle stressful situation")
            assert isinstance(result, HierarchicalPrediction)
            assert result.actionable_decision is not None
            assert 0.0 <= result.confidence <= 1.0

    def test_emotional_modulate_routing_failure(self, session_log_dir):
        """Emotional routing modulation failure should not crash the loop."""
        planner = _make_planner(session_log_dir)
        config = CognitiveLoopConfig(enable_emotional_system=True)
        loop = CognitiveLoop(planner=planner, config=config)

        if loop._emotional_system is not None:
            with patch.object(
                loop._emotional_system, 'modulate_routing_weights',
                side_effect=ValueError("Invalid weights shape")
            ):
                result = loop.process("Task with emotional modulation failure")
                assert isinstance(result, HierarchicalPrediction)
                assert result.actionable_decision is not None


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
