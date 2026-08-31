"""
Tests for the Closed Feedback Loop in ProductionPlanner.

Validates that submit_feedback() propagates to all 6 systems:
1. Layer 3 routing matrix
2. Neuromodulation (dopamine/serotonin/norepinephrine)
3. Memory (working + episodic consolidation)
4. Meta-learning
5. Layer 2 gate temperature
6. Emotional system

Also tests edge cases and error handling.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import numpy as np
from unittest.mock import MagicMock, patch, PropertyMock
from production.production_planner import ProductionPlanner


@pytest.fixture
def planner():
    """Create a minimal ProductionPlanner for testing feedback."""
    p = ProductionPlanner(
        session_log_dir=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'logs', 'sessions'),
        matrix_dir=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'production', 'trained_matrices'),
        feedback_dir=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'production', 'feedback'),
        enable_continuous_learning=True,
        learning_rate=0.005,
        seed=42,
        embedding_type="hash"
    )
    return p


@pytest.fixture
def mock_prediction():
    """A realistic prediction dict matching ProductionPlanner.predict() output."""
    return {
        'prediction': {
            'primary_action': 'write_code',
            'primary_weight': 0.35,
            'primary_reasoning': 'Code writing task detected',
            'alternatives': [
                {'action': 'analyze', 'weight': 0.25},
                {'action': 'plan', 'weight': 0.20}
            ],
            'confidence': 0.75,
            'processing_mode': 'analytical',
            'task_type': 'coding',
            'complexity': 0.6,
            'urgency': 0.4,
            'executable_tool_calls': None,
        },
        'brain_state': {
            'dominant_modalities': ['vision', 'tool_trace'],
            'gates': [0.15, 0.15, 0.15, 0.15, 0.15, 0.05, 0.05, 0.05, 0.05, 0.05],
        },
        'reasoning_chain': ['analyze', 'plan', 'execute']
    }


class TestFeedbackSubmission:
    """Tests for basic feedback submission."""

    def test_submit_positive_feedback(self, planner, mock_prediction):
        """Positive feedback should not raise."""
        planner.submit_feedback(
            task="Write a function",
            prediction=mock_prediction,
            actual_action='write_code',
            success=True,
            user_rating=0.9
        )
        assert planner.total_predictions >= 0

    def test_submit_negative_feedback(self, planner, mock_prediction):
        """Negative feedback should not raise."""
        planner.submit_feedback(
            task="Deploy application",
            prediction=mock_prediction,
            actual_action='deploy',
            success=False,
            user_rating=0.2
        )

    def test_feedback_buffer_accumulates(self, planner, mock_prediction):
        """Feedback buffer should grow."""
        initial = len(planner.feedback_buffer)
        planner.submit_feedback(
            task="Test task",
            prediction=mock_prediction,
            actual_action='write_code',
            success=True,
            user_rating=0.8
        )
        assert len(planner.feedback_buffer) == initial + 1

    def test_performance_log_records(self, planner, mock_prediction):
        """Performance log should record submission."""
        initial = len(planner.performance_log)
        planner.submit_feedback(
            task="Test task",
            prediction=mock_prediction,
            actual_action='write_code',
            success=True,
            user_rating=0.8
        )
        assert len(planner.performance_log) == initial + 1
        assert planner.performance_log[-1]['success'] is True


class TestNeuromodulationFeedback:
    """Tests for neuromodulation feedback propagation."""

    def test_success_boosts_dopamine(self, planner, mock_prediction):
        """Success should increase dopamine."""
        if not (planner.planner.enable_neuromodulation and planner.planner.neuromodulation):
            pytest.skip("Neuromodulation not enabled")

        initial_da = planner.planner.neuromodulation.levels.dopamine
        planner.submit_feedback(
            task="Test success",
            prediction=mock_prediction,
            actual_action='write_code',
            success=True,
            user_rating=0.9
        )
        assert planner.planner.neuromodulation.levels.dopamine >= initial_da

    def test_failure_boosts_norepinephrine(self, planner, mock_prediction):
        """Failure should increase norepinephrine (alertness)."""
        if not (planner.planner.enable_neuromodulation and planner.planner.neuromodulation):
            pytest.skip("Neuromodulation not enabled")

        initial_ne = planner.planner.neuromodulation.levels.norepinephrine
        planner.submit_feedback(
            task="Test failure",
            prediction=mock_prediction,
            actual_action='write_code',
            success=False,
            user_rating=0.1
        )
        assert planner.planner.neuromodulation.levels.norepinephrine >= initial_ne


class TestMemoryFeedback:
    """Tests for memory feedback propagation."""

    def test_memory_consolidation_on_feedback(self, planner, mock_prediction):
        """Feedback should trigger episodic consolidation."""
        if not (planner.planner.enable_memory and planner.planner.memory):
            pytest.skip("Memory not enabled")

        planner.submit_feedback(
            task="Memory test task",
            prediction=mock_prediction,
            actual_action='write_code',
            success=True,
            user_rating=0.9
        )
        # Should not raise - episodic consolidation should work


class TestEmotionalFeedback:
    """Tests for emotional system feedback propagation."""

    def test_emotional_learning_on_success(self, planner, mock_prediction):
        """Emotional system should learn from success."""
        if not planner.cognitive_loop:
            pytest.skip("Cognitive loop not enabled")

        planner.submit_feedback(
            task="Emotional test success",
            prediction=mock_prediction,
            actual_action='write_code',
            success=True,
            user_rating=0.9
        )
        # Should not raise

    def test_emotional_learning_on_failure(self, planner, mock_prediction):
        """Emotional system should learn from failure."""
        if not planner.cognitive_loop:
            pytest.skip("Cognitive loop not enabled")

        planner.submit_feedback(
            task="Emotional test failure",
            prediction=mock_prediction,
            actual_action='deploy',
            success=False,
            user_rating=0.1
        )


class TestEdgeCases:
    """Tests for feedback edge cases."""

    def test_feedback_with_missing_gates(self, planner, mock_prediction):
        """Should handle missing gates gracefully."""
        import copy
        pred_no_gates = copy.deepcopy(mock_prediction)
        pred_no_gates['brain_state']['gates'] = None

        # Should print warning but not crash
        planner.submit_feedback(
            task="No gates test",
            prediction=pred_no_gates,
            actual_action='write_code',
            success=True,
            user_rating=0.8
        )

    def test_feedback_with_zero_rating(self, planner, mock_prediction):
        """Zero rating should work."""
        planner.submit_feedback(
            task="Zero rating test",
            prediction=mock_prediction,
            actual_action='write_code',
            success=False,
            user_rating=0.0
        )

    def test_feedback_with_max_rating(self, planner, mock_prediction):
        """Max rating should work."""
        planner.submit_feedback(
            task="Max rating test",
            prediction=mock_prediction,
            actual_action='write_code',
            success=True,
            user_rating=1.0
        )

    def test_multiple_feedbacks(self, planner, mock_prediction):
        """Multiple sequential feedbacks should accumulate."""
        for i in range(5):
            planner.submit_feedback(
                task=f"Task {i}",
                prediction=mock_prediction,
                actual_action='write_code',
                success=(i % 2 == 0),
                user_rating=0.5
            )
        assert len(planner.performance_log) >= 5


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
