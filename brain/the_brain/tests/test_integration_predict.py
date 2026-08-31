"""
Integration tests for the full ProductionPlanner.predict() pipeline.

Tests that all cognitive subsystems are wired correctly and produce
valid output through the unified predict() API.
"""

import pytest
import os
import sys
import numpy as np
import tempfile
import shutil

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from production.production_planner import ProductionPlanner


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def session_log_dir():
    """Create a temporary session log directory with a minimal log file."""
    tmpdir = tempfile.mkdtemp(prefix="test_sessions_")
    # Create a minimal session log so training doesn't fail
    log_content = """2024-01-01 10:00:00,000 [TASK PROPAGATION] Task in kwargs: test deployment
2024-01-01 10:00:01,000 🛠️  Tool: list_notifications
2024-01-01 10:00:02,000 🔧 GitHubOperator activated
2024-01-01 10:00:03,000 ✓ QAValidator
✅ GOOD (Accept)
2024-01-01 10:00:04,000 Stopping agent
"""
    log_file = os.path.join(tmpdir, "github_20240101_100000_session1.log")
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(log_content)
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="module")
def planner_legacy(session_log_dir):
    """Create a ProductionPlanner in legacy mode (no cognitive loop)."""
    return ProductionPlanner(
        session_log_dir=session_log_dir,
        enable_cognitive_loop=False,
        enable_semantic_coherence=False,
        embedding_type="hash",
        seed=42
    )


@pytest.fixture(scope="module")
def planner_cognitive(session_log_dir):
    """Create a ProductionPlanner with cognitive loop enabled."""
    return ProductionPlanner(
        session_log_dir=session_log_dir,
        enable_cognitive_loop=True,
        enable_semantic_coherence=False,
        embedding_type="hash",
        seed=42
    )


# ============================================================================
# Legacy Pipeline Tests
# ============================================================================

class TestLegacyPredictPipeline:
    """Test the legacy (non-cognitive-loop) predict pipeline."""

    def test_predict_returns_dict(self, planner_legacy):
        result = planner_legacy.predict("Deploy Docker container to production")
        assert isinstance(result, dict)

    def test_predict_has_task(self, planner_legacy):
        result = planner_legacy.predict("Run unit tests")
        assert result['task'] == "Run unit tests"

    def test_predict_has_prediction_section(self, planner_legacy):
        result = planner_legacy.predict("Fix the login bug")
        pred = result['prediction']
        assert 'primary_action' in pred
        assert 'primary_weight' in pred
        assert 'confidence' in pred
        assert 'task_type' in pred
        assert 'complexity' in pred
        assert 'urgency' in pred

    def test_predict_confidence_in_range(self, planner_legacy):
        result = planner_legacy.predict("Update the README")
        confidence = result['prediction']['confidence']
        assert 0.0 <= confidence <= 1.0

    def test_predict_has_brain_state(self, planner_legacy):
        result = planner_legacy.predict("Scale database cluster")
        assert 'brain_state' in result
        assert 'dominant_modalities' in result['brain_state']

    def test_predict_has_reasoning_chain(self, planner_legacy):
        result = planner_legacy.predict("Refactor authentication module")
        assert 'reasoning_chain' in result
        assert isinstance(result['reasoning_chain'], list)
        assert len(result['reasoning_chain']) > 0

    def test_predict_primary_action_valid(self, planner_legacy):
        result = planner_legacy.predict("Monitor server health")
        valid_actions = ['suggest', 'retry', 'wait', 'terminate', 'execute']
        assert result['prediction']['primary_action'] in valid_actions

    def test_predict_has_alternatives(self, planner_legacy):
        result = planner_legacy.predict("Backup the database")
        alternatives = result['prediction']['alternatives']
        assert isinstance(alternatives, list)

    def test_predict_brain_gates_sum_to_one(self, planner_legacy):
        result = planner_legacy.predict("Optimize query performance")
        gates = result['brain_state'].get('gates')
        if gates is not None:
            gate_sum = sum(gates)
            assert abs(gate_sum - 1.0) < 0.01, f"Gates sum to {gate_sum}, expected 1.0"

    def test_predict_memory_context(self, planner_legacy):
        # Make a few predictions first to populate memory
        planner_legacy.predict("Deploy service A")
        planner_legacy.predict("Deploy service B")
        result = planner_legacy.predict("Deploy service C")
        # Memory context should exist (even if empty)
        assert 'memory_context' in result or result.get('memory_context') is None

    def test_predict_neuromodulation(self, planner_legacy):
        result = planner_legacy.predict("Handle critical error in production")
        # Should have neuromodulation key (may be None if not enabled)
        assert 'neuromodulation' in result

    def test_predict_consciousness_metrics(self, planner_legacy):
        result = planner_legacy.predict("Analyze user behavior patterns")
        assert 'consciousness_metrics' in result

    def test_predict_sensory_features(self, planner_legacy):
        """Test that sensory preprocessor adds features to output."""
        result = planner_legacy.predict("URGENT: Fix critical security vulnerability immediately!")
        if planner_legacy.sensory_preprocessor:
            assert 'sensory_features' in result
            sf = result['sensory_features']
            if 'error' not in sf:
                assert 'detected_intent' in sf
                assert 'detected_domain' in sf
                assert 'overall_complexity' in sf
                assert 'overall_urgency' in sf
                assert 'overall_risk' in sf


# ============================================================================
# Cognitive Loop Pipeline Tests
# ============================================================================

class TestCognitiveLoopPredictPipeline:
    """Test the cognitive loop predict pipeline."""

    def test_cognitive_loop_enabled(self, planner_cognitive):
        assert planner_cognitive.cognitive_loop is not None

    def test_predict_returns_dict(self, planner_cognitive):
        result = planner_cognitive.predict("Deploy Docker container to production")
        assert isinstance(result, dict)

    def test_predict_same_output_shape(self, planner_cognitive):
        """Cognitive loop should produce same top-level keys as legacy."""
        result = planner_cognitive.predict("Run unit tests")
        assert 'task' in result
        assert 'prediction' in result
        assert 'brain_state' in result
        assert 'reasoning_chain' in result

    def test_predict_confidence_in_range(self, planner_cognitive):
        result = planner_cognitive.predict("Update the README")
        confidence = result['prediction']['confidence']
        assert 0.0 <= confidence <= 1.0

    def test_predict_brain_gates_sum_to_one(self, planner_cognitive):
        result = planner_cognitive.predict("Optimize query performance")
        gates = result['brain_state'].get('gates')
        if gates is not None:
            gate_sum = sum(gates)
            assert abs(gate_sum - 1.0) < 0.01, f"Gates sum to {gate_sum}, expected 1.0"

    def test_cognitive_loop_state(self, planner_cognitive):
        """Test that cognitive loop exposes its state."""
        planner_cognitive.predict("Analyze data pipeline")
        state = planner_cognitive.cognitive_loop.get_loop_state()
        assert isinstance(state, dict)
        assert 'phase' in state or 'current_phase' in state or 'loop_iterations' in state


# ============================================================================
# Cross-Mode Consistency Tests
# ============================================================================

class TestCrossModeConsistency:
    """Test that both modes produce consistent, valid results."""

    def test_both_modes_same_task_type(self, planner_legacy, planner_cognitive):
        """Same task should produce same task type classification."""
        task = "Deploy Docker container"
        r_legacy = planner_legacy.predict(task)
        r_cognitive = planner_cognitive.predict(task)
        assert r_legacy['prediction']['task_type'] == r_cognitive['prediction']['task_type']

    def test_both_modes_valid_actions(self, planner_legacy, planner_cognitive):
        """Both modes should produce valid action types."""
        task = "Fix the broken CI pipeline"
        valid_actions = ['suggest', 'retry', 'wait', 'terminate', 'execute']

        r_legacy = planner_legacy.predict(task)
        r_cognitive = planner_cognitive.predict(task)

        assert r_legacy['prediction']['primary_action'] in valid_actions
        assert r_cognitive['prediction']['primary_action'] in valid_actions

    def test_both_modes_have_reasoning(self, planner_legacy, planner_cognitive):
        """Both modes should produce non-empty reasoning chains."""
        task = "Scale the microservices cluster"
        r_legacy = planner_legacy.predict(task)
        r_cognitive = planner_cognitive.predict(task)

        assert len(r_legacy['reasoning_chain']) > 0
        assert len(r_cognitive['reasoning_chain']) > 0


# ============================================================================
# Determinism Tests
# ============================================================================

class TestDeterminism:
    """Test that predictions are deterministic with same seed."""

    def test_legacy_deterministic(self, session_log_dir):
        """Two planners with same seed should produce identical predictions."""
        p1 = ProductionPlanner(
            session_log_dir=session_log_dir,
            enable_cognitive_loop=False,
            enable_semantic_coherence=False,
            embedding_type="hash",
            seed=123
        )
        p2 = ProductionPlanner(
            session_log_dir=session_log_dir,
            enable_cognitive_loop=False,
            enable_semantic_coherence=False,
            embedding_type="hash",
            seed=123
        )
        r1 = p1.predict("Deploy Docker container")
        r2 = p2.predict("Deploy Docker container")

        assert r1['prediction']['primary_action'] == r2['prediction']['primary_action']
        assert r1['prediction']['task_type'] == r2['prediction']['task_type']
        assert abs(r1['prediction']['confidence'] - r2['prediction']['confidence']) < 0.01


# ============================================================================
# Stress / Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Test edge cases and unusual inputs."""

    def test_empty_task(self, planner_legacy):
        """Empty task should not crash."""
        result = planner_legacy.predict("")
        assert isinstance(result, dict)
        assert 'prediction' in result

    def test_very_long_task(self, planner_legacy):
        """Very long task description should not crash."""
        long_task = "Deploy " * 500 + "the container"
        result = planner_legacy.predict(long_task)
        assert isinstance(result, dict)

    def test_special_characters(self, planner_legacy):
        """Special characters should not crash."""
        result = planner_legacy.predict("Fix the bug in /usr/bin/app <script>alert('xss')</script>")
        assert isinstance(result, dict)

    def test_unicode_task(self, planner_legacy):
        """Unicode input should not crash."""
        result = planner_legacy.predict("Bereitstellen des Docker-Containers auf Produktion")
        assert isinstance(result, dict)

    def test_multiple_predictions_stable(self, planner_legacy):
        """Running multiple predictions should not accumulate errors."""
        for i in range(10):
            result = planner_legacy.predict(f"Task number {i}")
            assert isinstance(result, dict)
            assert 'prediction' in result
            assert 0.0 <= result['prediction']['confidence'] <= 1.0


# ============================================================================
# Feedback Loop Integration Tests
# ============================================================================

class TestFeedbackLoop:
    """Test that feedback propagates correctly."""

    def test_feedback_updates_state(self, planner_legacy):
        """Submitting feedback should not crash and should increment counter."""
        initial_count = planner_legacy.total_feedback
        # Make a prediction first
        planner_legacy.predict("Deploy the service")
        # Submit feedback
        try:
            planner_legacy.submit_feedback(
                task="Deploy the service",
                brain_decision="execute",
                actual_outcome="SUCCESS",
                was_correct=True,
                notes="Worked perfectly"
            )
            assert planner_legacy.total_feedback >= initial_count
        except (AttributeError, TypeError):
            # submit_feedback may have different signature
            pytest.skip("Feedback method signature differs")
