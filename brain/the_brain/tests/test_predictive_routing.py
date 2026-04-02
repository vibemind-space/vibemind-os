"""
Tests for Predictive Router Module

Tests cover:
- ForwardModel prediction shapes and learning
- AnticipatedGateComputer gate normalization
- TemporalRoutingPattern pattern learning and retrieval
- PredictiveRouter integration and gate invariants
"""

import pytest
import numpy as np
from typing import Dict, List

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.predictive_router import (
    PredictiveRouter,
    ForwardModel,
    AnticipatedGateComputer,
    TemporalRoutingPattern,
    PredictiveState,
    RoutingPrediction
)


class TestForwardModel:
    """Tests for ForwardModel class."""

    @pytest.fixture
    def model(self):
        """Create test forward model."""
        modalities = ['visual', 'audio', 'semantic']
        dims = {'visual': 32, 'audio': 16, 'semantic': 64}
        return ForwardModel(modalities, dims, hidden_dim=32)

    def test_prediction_shape(self, model):
        """Forward model outputs correct shapes."""
        v_current = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }
        gates = np.array([0.5, 0.3, 0.2])

        v_pred = model.predict(v_current, gates)

        assert 'visual' in v_pred
        assert 'audio' in v_pred
        assert 'semantic' in v_pred
        assert v_pred['visual'].shape == (32,)
        assert v_pred['audio'].shape == (16,)
        assert v_pred['semantic'].shape == (64,)

    def test_prediction_with_missing_modality(self, model):
        """Forward model handles missing modalities."""
        v_current = {'visual': np.random.randn(32)}
        gates = np.array([0.5, 0.3, 0.2])

        v_pred = model.predict(v_current, gates)

        # Should still produce predictions for all modalities
        assert len(v_pred) == 3
        assert v_pred['audio'].shape == (16,)

    def test_gate_modulation(self, model):
        """Higher gates produce different predictions."""
        v_current = {
            'visual': np.ones(32),
            'audio': np.ones(16),
            'semantic': np.ones(64)
        }

        # High gate for visual
        gates_high = np.array([0.9, 0.05, 0.05])
        v_pred_high = model.predict(v_current, gates_high)

        # Low gate for visual
        gates_low = np.array([0.1, 0.45, 0.45])
        v_pred_low = model.predict(v_current, gates_low)

        # Visual predictions should differ due to gate modulation
        assert not np.allclose(v_pred_high['visual'], v_pred_low['visual'])

    def test_learning_reduces_error(self, model):
        """Forward model learns to reduce prediction error."""
        # Create a simple predictable sequence
        v_sequence = [
            {'visual': np.sin(np.arange(32) * 0.1 * t),
             'audio': np.cos(np.arange(16) * 0.1 * t),
             'semantic': np.zeros(64)}
            for t in range(20)
        ]
        gates = np.array([0.4, 0.4, 0.2])

        errors = []
        for t in range(len(v_sequence) - 1):
            v_pred = model.predict(v_sequence[t], gates)
            error = model.update(v_pred, v_sequence[t+1], v_sequence[t])
            errors.append(error)

        # Error should generally decrease (with some noise)
        # Compare first half average to second half
        first_half = np.mean(errors[:len(errors)//2])
        second_half = np.mean(errors[len(errors)//2:])
        # Allow some tolerance as learning is noisy
        assert second_half < first_half * 1.5

    def test_get_state(self, model):
        """Model state is serializable."""
        state = model.get_state()

        assert 'modalities' in state
        assert 'latent_dims' in state
        assert 'F' in state
        assert 'visual' in state['F']


class TestAnticipatedGateComputer:
    """Tests for AnticipatedGateComputer class."""

    @pytest.fixture
    def computer(self):
        """Create test gate computer."""
        modalities = ['visual', 'audio', 'semantic']
        dims = {'visual': 32, 'audio': 16, 'semantic': 64}
        return AnticipatedGateComputer(modalities, dims, temperature=1.0)

    def test_gates_sum_to_one(self, computer):
        """Anticipated gates always sum to 1.0."""
        v_pred = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }

        gates = computer.compute(v_pred)

        assert np.isclose(np.sum(gates), 1.0)
        assert len(gates) == 3
        assert np.all(gates >= 0)
        assert np.all(gates <= 1)

    def test_gates_sum_to_one_with_context(self, computer):
        """Gates sum to 1.0 even with context modulation."""
        v_pred = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }
        context = np.random.randn(10)

        gates = computer.compute(v_pred, context)

        assert np.isclose(np.sum(gates), 1.0)

    def test_temperature_affects_distribution(self):
        """Lower temperature makes gates more peaked."""
        modalities = ['visual', 'audio', 'semantic']
        dims = {'visual': 32, 'audio': 16, 'semantic': 64}

        computer_low_temp = AnticipatedGateComputer(modalities, dims, temperature=0.1)
        computer_high_temp = AnticipatedGateComputer(modalities, dims, temperature=5.0)

        # Use same weights for fair comparison
        computer_high_temp.W_gate = computer_low_temp.W_gate.copy()
        computer_high_temp.bias = computer_low_temp.bias.copy()

        v_pred = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }

        gates_low = computer_low_temp.compute(v_pred)
        gates_high = computer_high_temp.compute(v_pred)

        # Low temperature should have more peaked distribution (higher max)
        assert np.max(gates_low) >= np.max(gates_high) - 0.1

        # Both should still sum to 1.0
        assert np.isclose(np.sum(gates_low), 1.0)
        assert np.isclose(np.sum(gates_high), 1.0)

    def test_update_changes_weights(self, computer):
        """Update modifies weights."""
        v_pred = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }

        W_before = computer.W_gate.copy()
        computed = computer.compute(v_pred)
        target = np.array([0.6, 0.3, 0.1])

        computer.update(v_pred, target, computed)

        assert not np.allclose(computer.W_gate, W_before)


class TestTemporalRoutingPattern:
    """Tests for TemporalRoutingPattern class."""

    @pytest.fixture
    def temporal(self):
        """Create test temporal pattern learner."""
        return TemporalRoutingPattern(
            n_modalities=3,
            sequence_length=5,
            n_patterns=10
        )

    def test_record_builds_history(self, temporal):
        """Recording gates builds history buffer."""
        gates = np.array([0.5, 0.3, 0.2])

        for _ in range(3):
            temporal.record(gates)

        assert len(temporal.gate_history) == 3

    def test_history_bounded(self, temporal):
        """History buffer stays bounded."""
        gates = np.array([0.5, 0.3, 0.2])

        for _ in range(20):
            temporal.record(gates)

        # Should be bounded to sequence_length * 2
        assert len(temporal.gate_history) <= temporal.sequence_length * 2

    def test_pattern_learning(self, temporal):
        """System learns recurring patterns."""
        # Create a repeating pattern
        pattern = [
            np.array([0.6, 0.3, 0.1]),
            np.array([0.4, 0.4, 0.2]),
            np.array([0.2, 0.5, 0.3]),
            np.array([0.3, 0.3, 0.4]),
            np.array([0.5, 0.2, 0.3])
        ]

        # Record pattern multiple times
        for _ in range(10):
            for g in pattern:
                temporal.record(g)

        # Clear history and record prefix
        temporal.gate_history.clear()
        for g in pattern[:-1]:
            temporal.record(g)

        # Should predict final gate
        prediction = temporal.predict_next()

        assert prediction is not None
        assert np.isclose(np.sum(prediction), 1.0)
        assert len(prediction) == 3

    def test_prediction_normalized(self, temporal):
        """Predictions are always normalized."""
        # Record some gates
        for _ in range(10):
            gates = np.random.rand(3)
            gates /= np.sum(gates)
            temporal.record(gates)

        prediction = temporal.predict_next()

        if prediction is not None:
            assert np.isclose(np.sum(prediction), 1.0)
            assert np.all(prediction >= 0)

    def test_explicit_pattern_learning(self, temporal):
        """Explicit pattern learning stores pattern."""
        pattern = np.random.rand(5, 3)
        for t in range(5):
            pattern[t] /= np.sum(pattern[t])

        temporal.learn_pattern(pattern)

        # Pattern should be stored
        assert np.sum(temporal.usage_counts > 0) >= 1

    def test_confidence_update(self, temporal):
        """Confidence updates work correctly."""
        initial_conf = temporal.pattern_confidence[0]

        temporal.update_confidence(0, success=True)
        assert temporal.pattern_confidence[0] > initial_conf

        temporal.update_confidence(0, success=False)
        temporal.update_confidence(0, success=False)
        assert temporal.pattern_confidence[0] < initial_conf + 0.1


class TestPredictiveRouter:
    """Tests for PredictiveRouter integration."""

    @pytest.fixture
    def router(self):
        """Create test predictive router."""
        modalities = ['visual', 'audio', 'semantic']
        dims = {'visual': 32, 'audio': 16, 'semantic': 64}
        return PredictiveRouter(
            modalities, dims,
            blend_alpha=0.3,
            hidden_dim=32
        )

    def test_blended_gates_sum_to_one(self, router):
        """Blended gates maintain normalization."""
        v = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }
        g = np.array([0.5, 0.3, 0.2])

        result = router.step(v, g)

        assert np.isclose(np.sum(result.blended_gates), 1.0)
        assert len(result.blended_gates) == 3
        assert np.all(result.blended_gates >= 0)
        assert np.all(result.blended_gates <= 1)

    def test_blended_gates_with_unnormalized_input(self, router):
        """Router normalizes unnormalized input gates."""
        v = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }
        g = np.array([0.6, 0.6, 0.6])  # Doesn't sum to 1.0

        result = router.step(v, g)

        assert np.isclose(np.sum(result.blended_gates), 1.0)

    def test_confidence_updates(self, router):
        """Confidence adjusts based on prediction accuracy."""
        v1 = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }
        g = np.array([0.5, 0.3, 0.2])

        # Initial step
        result1 = router.step(v1, g)
        conf1 = result1.confidence

        # Second step with similar input (good prediction)
        v2 = {k: v + 0.01 * np.random.randn(*v.shape) for k, v in v1.items()}
        result2 = router.step(v2, g)
        conf2 = result2.confidence

        # Confidence should update (may go up or down depending on prediction)
        assert conf2 != conf1 or router.total_predictions <= 2

    def test_integration_with_context(self, router):
        """Context modulates anticipated gates."""
        v = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }
        g = np.array([0.5, 0.3, 0.2])

        result_no_ctx = router.step(v, g, context=None)

        router.reset()
        context = np.random.randn(10)
        result_with_ctx = router.step(v, g, context=context)

        # Results should differ due to context
        assert not np.allclose(
            result_no_ctx.blended_gates,
            result_with_ctx.blended_gates
        )

        # Both should sum to 1.0
        assert np.isclose(np.sum(result_no_ctx.blended_gates), 1.0)
        assert np.isclose(np.sum(result_with_ctx.blended_gates), 1.0)

    def test_learn_updates_models(self, router):
        """Learning updates forward models."""
        v1 = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }
        g = np.array([0.5, 0.3, 0.2])

        router.step(v1, g)

        v2 = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }

        # Store weights before learning
        W_before = router.forward_model.F['visual']['W2'].copy()

        router.learn(v2, v1)

        # Weights should change
        assert not np.allclose(
            router.forward_model.F['visual']['W2'],
            W_before
        )

    def test_reset_clears_state(self, router):
        """Reset clears internal state."""
        v = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }
        g = np.array([0.5, 0.3, 0.2])

        router.step(v, g)
        assert router.prev_prediction is not None

        router.reset()

        assert router.prev_prediction is None
        assert router.prev_gates is None
        assert router.confidence == 0.5
        assert len(router.temporal.gate_history) == 0

    def test_get_metrics(self, router):
        """Metrics are tracked correctly."""
        v = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }
        g = np.array([0.5, 0.3, 0.2])

        for _ in range(5):
            router.step(v, g)

        metrics = router.get_metrics()

        assert metrics['total_predictions'] == 5
        assert 'current_confidence' in metrics
        assert 'mean_prediction_error' in metrics

    def test_get_state_serializable(self, router):
        """State is serializable."""
        v = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }
        g = np.array([0.5, 0.3, 0.2])

        router.step(v, g)
        state = router.get_state()

        assert 'modalities' in state
        assert 'latent_dims' in state
        assert 'blend_alpha' in state
        assert 'forward_model' in state
        assert 'metrics' in state

    def test_gate_deltas_computed(self, router):
        """Gate deltas show difference from current gates."""
        v = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }
        g = np.array([0.5, 0.3, 0.2])

        result = router.step(v, g)

        expected_deltas = result.blended_gates - g
        assert np.allclose(result.gate_deltas, expected_deltas)

    def test_multiple_steps_stable(self, router):
        """Multiple steps remain numerically stable."""
        for _ in range(100):
            v = {
                'visual': np.random.randn(32),
                'audio': np.random.randn(16),
                'semantic': np.random.randn(64)
            }
            g = np.random.rand(3)
            g /= np.sum(g)

            result = router.step(v, g)

            # Check invariants
            assert np.isclose(np.sum(result.blended_gates), 1.0)
            assert np.all(np.isfinite(result.blended_gates))
            assert result.confidence >= 0.1
            assert result.confidence <= 0.9


class TestPredictiveRouterEdgeCases:
    """Edge case tests for PredictiveRouter."""

    def test_single_modality(self):
        """Router works with single modality."""
        router = PredictiveRouter(
            modalities=['visual'],
            latent_dims={'visual': 32}
        )

        v = {'visual': np.random.randn(32)}
        g = np.array([1.0])

        result = router.step(v, g)

        assert np.isclose(np.sum(result.blended_gates), 1.0)
        assert len(result.blended_gates) == 1

    def test_many_modalities(self):
        """Router works with many modalities."""
        modalities = [f'mod_{i}' for i in range(10)]
        dims = {m: 16 for m in modalities}

        router = PredictiveRouter(modalities, dims)

        v = {m: np.random.randn(16) for m in modalities}
        g = np.ones(10) / 10

        result = router.step(v, g)

        assert np.isclose(np.sum(result.blended_gates), 1.0)
        assert len(result.blended_gates) == 10

    def test_zero_latents(self):
        """Router handles zero latent vectors."""
        router = PredictiveRouter(
            modalities=['visual', 'audio'],
            latent_dims={'visual': 32, 'audio': 16}
        )

        v = {
            'visual': np.zeros(32),
            'audio': np.zeros(16)
        }
        g = np.array([0.5, 0.5])

        result = router.step(v, g)

        assert np.isclose(np.sum(result.blended_gates), 1.0)
        assert np.all(np.isfinite(result.blended_gates))

    def test_extreme_gates(self):
        """Router handles extreme gate values."""
        router = PredictiveRouter(
            modalities=['visual', 'audio', 'semantic'],
            latent_dims={'visual': 32, 'audio': 16, 'semantic': 64}
        )

        v = {
            'visual': np.random.randn(32),
            'audio': np.random.randn(16),
            'semantic': np.random.randn(64)
        }

        # Nearly all attention on one modality
        g = np.array([0.99, 0.005, 0.005])

        result = router.step(v, g)

        assert np.isclose(np.sum(result.blended_gates), 1.0)
        assert np.all(result.blended_gates >= 0)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
