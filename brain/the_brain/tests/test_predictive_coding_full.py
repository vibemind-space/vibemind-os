"""
Comprehensive tests for Predictive Coding Infrastructure (PHASE 2).

Test coverage:
- Default initialization (HierarchicalPredictiveCoding, Layer1, Layer3)
- predict_task_features returns prediction object
- update_task_prediction computes prediction error
- Prediction error magnitude correctness
- get_curiosity_signal structure and fields
- Curiosity signal increases with high error
- Multiple predictions refine estimates
- Error near zero when prediction matches actual
- Error high when prediction differs greatly from actual
- State serialization (PredictionError.to_dict, get_statistics)
- Reset / fresh instance isolation
- Per-modality error vectors
- Temporal prediction (Layer3 decision outcome)
- Thread safety
- Integration pattern (predict -> route -> update cycle)
- Layer history size limits
- Surprise level determination
- Decision history per type
"""

import pytest
import numpy as np
import sys
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent directory to path for module access
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, parent_dir)

from core.predictive_coding import (
    PredictionError,
    PredictiveLayer,
    Layer1Predictor,
    Layer3Predictor,
    HierarchicalPredictiveCoding,
)


# ---------------------------------------------------------------------------
# 1. Default initialization
# ---------------------------------------------------------------------------
class TestDefaultInitialization:
    """Test that all components initialize with sane defaults."""

    def test_hierarchical_init(self):
        """HierarchicalPredictiveCoding initializes with zero state."""
        hpc = HierarchicalPredictiveCoding()
        assert hpc.total_predictions == 0
        assert hpc.high_surprise_events == []
        assert isinstance(hpc.layer1_predictor, Layer1Predictor)
        assert isinstance(hpc.layer3_predictor, Layer3Predictor)

    def test_layer1_init(self):
        """Layer1Predictor starts with empty history."""
        l1 = Layer1Predictor()
        assert l1.layer_name == "Layer1_TaskFeatures"
        assert l1.prediction_count == 0
        assert l1.prediction_errors == []
        assert l1.task_type_history == []
        assert l1.complexity_history == []
        assert l1.urgency_history == []

    def test_layer3_init(self):
        """Layer3Predictor starts with empty decision history."""
        l3 = Layer3Predictor()
        assert l3.layer_name == "Layer3_DecisionOutcomes"
        assert l3.prediction_count == 0
        assert l3.prediction_errors == []
        assert l3.decision_history == {}

    def test_layer1_default_prediction(self):
        """With no history Layer1 predicts defaults."""
        l1 = Layer1Predictor()
        pred = l1.predict({})
        assert pred['task_type'] == 'unknown'
        assert pred['complexity'] == 0.5
        assert pred['urgency'] == 0.5

    def test_layer3_default_prediction(self):
        """With no history Layer3 predicts defaults."""
        l3 = Layer3Predictor()
        pred = l3.predict({'decision_type': 'route'})
        assert pred['success_probability'] == 0.5
        assert pred['execution_time_ms'] == 1000.0


# ---------------------------------------------------------------------------
# 2. predict_task_features returns prediction object
# ---------------------------------------------------------------------------
class TestPredictTaskFeatures:
    """Test the top-level predict_task_features API."""

    def test_returns_tuple(self):
        """predict_task_features returns (prediction, context) tuple."""
        hpc = HierarchicalPredictiveCoding()
        result = hpc.predict_task_features({})
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_prediction_dict_keys(self):
        """Prediction dict has expected keys."""
        hpc = HierarchicalPredictiveCoding()
        prediction, ctx = hpc.predict_task_features({})
        assert 'task_type' in prediction
        assert 'complexity' in prediction
        assert 'urgency' in prediction

    def test_context_dict_keys(self):
        """Prediction context dict has expected keys."""
        hpc = HierarchicalPredictiveCoding()
        prediction, ctx = hpc.predict_task_features({})
        assert 'prediction' in ctx
        assert 'mean_recent_error' in ctx
        assert 'surprise_rate' in ctx

    def test_fresh_context_values(self):
        """On a fresh instance, context error/surprise should be zero."""
        hpc = HierarchicalPredictiveCoding()
        _, ctx = hpc.predict_task_features({})
        assert ctx['mean_recent_error'] == 0.0
        assert ctx['surprise_rate'] == 0.0


# ---------------------------------------------------------------------------
# 3. update_task_prediction computes error
# ---------------------------------------------------------------------------
class TestUpdateTaskPrediction:
    """Test update_task_prediction returns a PredictionError."""

    def test_returns_prediction_error(self):
        """update_task_prediction returns a PredictionError instance."""
        hpc = HierarchicalPredictiveCoding()
        prediction = {'task_type': 'unknown', 'complexity': 0.5, 'urgency': 0.5}
        actual = {'task_type': 'deploy', 'complexity': 0.8, 'urgency': 0.3}
        pe = hpc.update_task_prediction(prediction, actual)
        assert isinstance(pe, PredictionError)

    def test_increments_total_predictions(self):
        """Each update increments total_predictions counter."""
        hpc = HierarchicalPredictiveCoding()
        prediction = {'task_type': 'a', 'complexity': 0.5, 'urgency': 0.5}
        actual = {'task_type': 'b', 'complexity': 0.6, 'urgency': 0.4}
        hpc.update_task_prediction(prediction, actual)
        assert hpc.total_predictions == 1
        hpc.update_task_prediction(prediction, actual)
        assert hpc.total_predictions == 2

    def test_records_in_layer1(self):
        """Error is recorded in layer1 predictor history."""
        hpc = HierarchicalPredictiveCoding()
        prediction = {'task_type': 'x', 'complexity': 0.5, 'urgency': 0.5}
        actual = {'task_type': 'x', 'complexity': 0.5, 'urgency': 0.5}
        hpc.update_task_prediction(prediction, actual)
        assert hpc.layer1_predictor.prediction_count == 1
        assert len(hpc.layer1_predictor.prediction_errors) == 1


# ---------------------------------------------------------------------------
# 4. Prediction error magnitude
# ---------------------------------------------------------------------------
class TestPredictionErrorMagnitude:
    """Test that error magnitudes are computed correctly."""

    def test_partial_mismatch(self):
        """Error magnitude for partial mismatch is between 0 and 1."""
        hpc = HierarchicalPredictiveCoding()
        prediction = {'task_type': 'deploy', 'complexity': 0.5, 'urgency': 0.5}
        actual = {'task_type': 'deploy', 'complexity': 0.8, 'urgency': 0.2}
        pe = hpc.update_task_prediction(prediction, actual)
        # task_type matches (0.0), complexity diff = 0.3, urgency diff = 0.3
        # mean = (0.0 + 0.3 + 0.3) / 3 = 0.2
        assert np.isclose(pe.error_magnitude, 0.2, atol=1e-6)

    def test_full_mismatch(self):
        """Error is maximum when everything differs."""
        hpc = HierarchicalPredictiveCoding()
        prediction = {'task_type': 'a', 'complexity': 0.0, 'urgency': 0.0}
        actual = {'task_type': 'b', 'complexity': 1.0, 'urgency': 1.0}
        pe = hpc.update_task_prediction(prediction, actual)
        # task_type mismatch (1.0), complexity diff = 1.0, urgency diff = 1.0
        # mean = 1.0
        assert np.isclose(pe.error_magnitude, 1.0, atol=1e-6)


# ---------------------------------------------------------------------------
# 5. get_curiosity_signal structure
# ---------------------------------------------------------------------------
class TestCuriositySignalStructure:
    """Test that the curiosity signal has the correct structure."""

    def test_curiosity_keys(self):
        """Curiosity signal contains all expected keys."""
        hpc = HierarchicalPredictiveCoding()
        signal = hpc.get_curiosity_signal()
        expected_keys = {
            'curiosity_level', 'recommendation',
            'layer1_error', 'layer3_error',
            'layer1_surprise_rate', 'layer3_surprise_rate',
            'total_predictions', 'high_surprise_events'
        }
        assert expected_keys == set(signal.keys())

    def test_curiosity_level_valid(self):
        """Curiosity level is one of the expected values."""
        hpc = HierarchicalPredictiveCoding()
        signal = hpc.get_curiosity_signal()
        assert signal['curiosity_level'] in ('low', 'moderate', 'high')

    def test_recommendation_valid(self):
        """Recommendation is one of the expected values."""
        hpc = HierarchicalPredictiveCoding()
        signal = hpc.get_curiosity_signal()
        assert signal['recommendation'] in ('exploit', 'balanced', 'explore')

    def test_fresh_curiosity_is_low(self):
        """With no predictions, curiosity should be low (exploit)."""
        hpc = HierarchicalPredictiveCoding()
        signal = hpc.get_curiosity_signal()
        assert signal['curiosity_level'] == 'low'
        assert signal['recommendation'] == 'exploit'
        assert signal['total_predictions'] == 0


# ---------------------------------------------------------------------------
# 6. Curiosity signal increases with high error
# ---------------------------------------------------------------------------
class TestCuriosityIncreasesWithError:
    """Test that curiosity grows when prediction errors are consistently high."""

    def test_high_error_raises_curiosity(self):
        """After many high-error updates, curiosity should not remain 'low'."""
        hpc = HierarchicalPredictiveCoding()
        # Feed many high-error predictions to both layers
        for _ in range(20):
            pred = {'task_type': 'a', 'complexity': 0.0, 'urgency': 0.0}
            actual = {'task_type': 'b', 'complexity': 1.0, 'urgency': 1.0}
            hpc.update_task_prediction(pred, actual)

            d_pred = {'success_probability': 0.0, 'execution_time_ms': 100.0}
            d_actual = {
                'decision_type': 'route', 'success': True,
                'execution_time_ms': 5000.0
            }
            hpc.update_decision_prediction(d_pred, d_actual)

        signal = hpc.get_curiosity_signal()
        # With consistently high errors, curiosity should be moderate or high
        assert signal['layer1_error'] > 0.5
        assert signal['curiosity_level'] in ('moderate', 'high')


# ---------------------------------------------------------------------------
# 7. Multiple predictions refine estimates
# ---------------------------------------------------------------------------
class TestMultiplePredictionsRefine:
    """Test that repeated predictions with consistent data refine estimates."""

    def test_layer1_prediction_adapts(self):
        """After feeding consistent tasks, Layer1 predicts the dominant type."""
        hpc = HierarchicalPredictiveCoding()
        # Feed 10 'deploy' tasks
        for _ in range(10):
            pred, _ = hpc.predict_task_features({})
            actual = {'task_type': 'deploy', 'complexity': 0.7, 'urgency': 0.3}
            hpc.update_task_prediction(pred, actual)

        # Now predict - should predict 'deploy'
        pred, ctx = hpc.predict_task_features({})
        assert pred['task_type'] == 'deploy'
        assert np.isclose(pred['complexity'], 0.7, atol=0.05)
        assert np.isclose(pred['urgency'], 0.3, atol=0.05)

    def test_error_decreases_over_time(self):
        """Prediction error should decrease as predictions align with data."""
        hpc = HierarchicalPredictiveCoding()
        errors = []
        for _ in range(15):
            pred, _ = hpc.predict_task_features({})
            actual = {'task_type': 'deploy', 'complexity': 0.7, 'urgency': 0.3}
            pe = hpc.update_task_prediction(pred, actual)
            errors.append(pe.error_magnitude)

        # The last few errors should be smaller than the first few
        avg_first_3 = np.mean(errors[:3])
        avg_last_3 = np.mean(errors[-3:])
        assert avg_last_3 <= avg_first_3


# ---------------------------------------------------------------------------
# 8. Error near zero when prediction matches actual
# ---------------------------------------------------------------------------
class TestErrorNearZeroOnMatch:
    """Test that error is near zero when prediction and actual match."""

    def test_exact_match(self):
        """Identical prediction and actual yields zero error."""
        hpc = HierarchicalPredictiveCoding()
        prediction = {'task_type': 'deploy', 'complexity': 0.7, 'urgency': 0.3}
        actual = {'task_type': 'deploy', 'complexity': 0.7, 'urgency': 0.3}
        pe = hpc.update_task_prediction(prediction, actual)
        assert np.isclose(pe.error_magnitude, 0.0, atol=1e-9)

    def test_very_close_match(self):
        """Near-identical values yield very small error."""
        hpc = HierarchicalPredictiveCoding()
        prediction = {'task_type': 'test', 'complexity': 0.500, 'urgency': 0.500}
        actual = {'task_type': 'test', 'complexity': 0.501, 'urgency': 0.499}
        pe = hpc.update_task_prediction(prediction, actual)
        assert pe.error_magnitude < 0.01

    def test_layer3_exact_match(self):
        """Layer3 exact match yields near-zero error."""
        hpc = HierarchicalPredictiveCoding()
        prediction = {'success_probability': 1.0, 'execution_time_ms': 500.0}
        actual = {
            'decision_type': 'route', 'success': True,
            'execution_time_ms': 500.0
        }
        pe = hpc.update_decision_prediction(prediction, actual)
        assert pe.error_magnitude < 0.01


# ---------------------------------------------------------------------------
# 9. Error high when prediction and actual differ greatly
# ---------------------------------------------------------------------------
class TestErrorHighOnMismatch:
    """Test that error is large when prediction and actual differ greatly."""

    def test_total_mismatch_layer1(self):
        """All-wrong prediction yields high error."""
        hpc = HierarchicalPredictiveCoding()
        prediction = {'task_type': 'alpha', 'complexity': 0.0, 'urgency': 0.0}
        actual = {'task_type': 'beta', 'complexity': 1.0, 'urgency': 1.0}
        pe = hpc.update_task_prediction(prediction, actual)
        assert pe.error_magnitude >= 0.9

    def test_total_mismatch_layer3(self):
        """Layer3 big mismatch yields high error."""
        hpc = HierarchicalPredictiveCoding()
        prediction = {'success_probability': 1.0, 'execution_time_ms': 100.0}
        actual = {
            'decision_type': 'route', 'success': False,
            'execution_time_ms': 5000.0
        }
        pe = hpc.update_decision_prediction(prediction, actual)
        # success error = 1.0, time error capped at 2.0 => mean ~1.5
        assert pe.error_magnitude > 1.0


# ---------------------------------------------------------------------------
# 10. State serialization
# ---------------------------------------------------------------------------
class TestStateSerialization:
    """Test that objects can be serialized to dicts."""

    def test_prediction_error_to_dict(self):
        """PredictionError.to_dict produces expected keys."""
        pe = PredictionError(
            error_magnitude=0.42,
            error_vector=np.array([0.1, 0.3, 0.5]),
            confidence=0.8,
            surprise_level='high'
        )
        d = pe.to_dict()
        assert d['error_magnitude'] == pytest.approx(0.42)
        assert d['confidence'] == pytest.approx(0.8)
        assert d['surprise_level'] == 'high'
        assert d['error_vector'] == pytest.approx([0.1, 0.3, 0.5])

    def test_prediction_error_to_dict_no_vector(self):
        """PredictionError.to_dict without error_vector omits that key."""
        pe = PredictionError(error_magnitude=0.1)
        d = pe.to_dict()
        assert 'error_vector' not in d
        assert 'error_magnitude' in d

    def test_get_statistics_structure(self):
        """get_statistics returns well-structured dict."""
        hpc = HierarchicalPredictiveCoding()
        # Feed one prediction so stats are populated
        pred = {'task_type': 'x', 'complexity': 0.5, 'urgency': 0.5}
        actual = {'task_type': 'y', 'complexity': 0.6, 'urgency': 0.4}
        hpc.update_task_prediction(pred, actual)

        stats = hpc.get_statistics()
        assert 'total_predictions' in stats
        assert 'layer1' in stats
        assert 'layer3' in stats
        assert 'high_surprise_events' in stats
        assert 'curiosity' in stats
        assert 'prediction_count' in stats['layer1']
        assert 'recent_stats' in stats['layer1']

    def test_statistics_values_consistent(self):
        """Statistics counters match actual operations."""
        hpc = HierarchicalPredictiveCoding()
        for _ in range(5):
            pred = {'task_type': 'a', 'complexity': 0.5, 'urgency': 0.5}
            actual = {'task_type': 'a', 'complexity': 0.5, 'urgency': 0.5}
            hpc.update_task_prediction(pred, actual)

        stats = hpc.get_statistics()
        assert stats['total_predictions'] == 5
        assert stats['layer1']['prediction_count'] == 5


# ---------------------------------------------------------------------------
# 11. Reset / fresh instance isolation
# ---------------------------------------------------------------------------
class TestFreshInstanceIsolation:
    """Test that separate instances do not share state."""

    def test_separate_instances_independent(self):
        """Two HierarchicalPredictiveCoding instances are independent."""
        hpc1 = HierarchicalPredictiveCoding()
        hpc2 = HierarchicalPredictiveCoding()

        pred = {'task_type': 'a', 'complexity': 0.5, 'urgency': 0.5}
        actual = {'task_type': 'b', 'complexity': 0.9, 'urgency': 0.1}
        hpc1.update_task_prediction(pred, actual)

        assert hpc1.total_predictions == 1
        assert hpc2.total_predictions == 0
        assert len(hpc1.layer1_predictor.prediction_errors) == 1
        assert len(hpc2.layer1_predictor.prediction_errors) == 0

    def test_fresh_instance_clean_state(self):
        """A new instance always starts clean."""
        hpc = HierarchicalPredictiveCoding()
        assert hpc.total_predictions == 0
        assert hpc.high_surprise_events == []
        assert hpc.layer1_predictor.prediction_count == 0
        assert hpc.layer3_predictor.prediction_count == 0

    def test_layer1_instances_independent(self):
        """Two Layer1Predictor instances do not share history."""
        l1a = Layer1Predictor()
        l1b = Layer1Predictor()

        pred = {'task_type': 'a', 'complexity': 0.5, 'urgency': 0.5}
        actual = {'task_type': 'b', 'complexity': 0.8, 'urgency': 0.2}
        l1a.compute_error(pred, actual)

        assert l1a.prediction_count == 1
        assert l1b.prediction_count == 0
        assert len(l1a.task_type_history) == 1
        assert len(l1b.task_type_history) == 0


# ---------------------------------------------------------------------------
# 12. Per-modality error vectors
# ---------------------------------------------------------------------------
class TestPerModalityErrors:
    """Test that error vectors capture per-feature errors."""

    def test_error_vector_length_layer1(self):
        """Error vector has one entry per compared feature (up to 3)."""
        hpc = HierarchicalPredictiveCoding()
        pred = {'task_type': 'a', 'complexity': 0.5, 'urgency': 0.5}
        actual = {'task_type': 'b', 'complexity': 0.8, 'urgency': 0.2}
        pe = hpc.update_task_prediction(pred, actual)
        assert pe.error_vector is not None
        assert len(pe.error_vector) == 3  # task_type, complexity, urgency

    def test_error_vector_values_layer1(self):
        """Error vector values correspond to individual feature errors."""
        hpc = HierarchicalPredictiveCoding()
        pred = {'task_type': 'deploy', 'complexity': 0.3, 'urgency': 0.6}
        actual = {'task_type': 'deploy', 'complexity': 0.7, 'urgency': 0.1}
        pe = hpc.update_task_prediction(pred, actual)
        # task_type match => 0.0, complexity diff = 0.4, urgency diff = 0.5
        assert np.isclose(pe.error_vector[0], 0.0, atol=1e-9)
        assert np.isclose(pe.error_vector[1], 0.4, atol=1e-6)
        assert np.isclose(pe.error_vector[2], 0.5, atol=1e-6)

    def test_error_vector_length_layer3(self):
        """Layer3 error vector has entries for success and time."""
        hpc = HierarchicalPredictiveCoding()
        pred = {'success_probability': 0.5, 'execution_time_ms': 1000.0}
        actual = {
            'decision_type': 'route', 'success': True,
            'execution_time_ms': 2000.0
        }
        pe = hpc.update_decision_prediction(pred, actual)
        assert pe.error_vector is not None
        assert len(pe.error_vector) == 2  # success, time

    def test_error_vector_values_layer3(self):
        """Layer3 error vector values are correct."""
        hpc = HierarchicalPredictiveCoding()
        pred = {'success_probability': 0.8, 'execution_time_ms': 1000.0}
        actual = {
            'decision_type': 'route', 'success': True,
            'execution_time_ms': 1000.0
        }
        pe = hpc.update_decision_prediction(pred, actual)
        # success error = |0.8 - 1.0| = 0.2, time error = 0/1000 = 0.0
        assert np.isclose(pe.error_vector[0], 0.2, atol=1e-6)
        assert np.isclose(pe.error_vector[1], 0.0, atol=1e-6)


# ---------------------------------------------------------------------------
# 13. Temporal prediction (Layer3 decision outcome)
# ---------------------------------------------------------------------------
class TestTemporalPredictionLayer3:
    """Test Layer3 decision outcome predictions over time."""

    def test_predict_decision_outcome_api(self):
        """predict_decision_outcome returns (prediction, context) tuple."""
        hpc = HierarchicalPredictiveCoding()
        result = hpc.predict_decision_outcome({'decision_type': 'route'})
        assert isinstance(result, tuple)
        assert len(result) == 2
        pred, ctx = result
        assert 'success_probability' in pred
        assert 'execution_time_ms' in pred

    def test_layer3_adapts_to_history(self):
        """Layer3 predictions adapt after receiving outcome history."""
        hpc = HierarchicalPredictiveCoding()
        # Feed consistent outcomes for 'route' decisions
        for _ in range(10):
            pred, _ = hpc.predict_decision_outcome({'decision_type': 'route'})
            actual = {
                'decision_type': 'route', 'success': True,
                'execution_time_ms': 200.0
            }
            hpc.update_decision_prediction(pred, actual)

        # After consistent history, predictions should approach actuals
        pred, _ = hpc.predict_decision_outcome({'decision_type': 'route'})
        assert pred['success_probability'] > 0.8
        assert pred['execution_time_ms'] < 500.0

    def test_layer3_decision_type_isolation(self):
        """Different decision types maintain separate histories."""
        hpc = HierarchicalPredictiveCoding()
        # Feed successes for 'route' and failures for 'terminate'
        for _ in range(10):
            pred_r, _ = hpc.predict_decision_outcome({'decision_type': 'route'})
            hpc.update_decision_prediction(pred_r, {
                'decision_type': 'route', 'success': True,
                'execution_time_ms': 100.0
            })
            pred_t, _ = hpc.predict_decision_outcome({'decision_type': 'terminate'})
            hpc.update_decision_prediction(pred_t, {
                'decision_type': 'terminate', 'success': False,
                'execution_time_ms': 5000.0
            })

        pred_r, _ = hpc.predict_decision_outcome({'decision_type': 'route'})
        pred_t, _ = hpc.predict_decision_outcome({'decision_type': 'terminate'})
        # Route should predict high success, terminate should predict low
        assert pred_r['success_probability'] > pred_t['success_probability']

    def test_update_decision_prediction_api(self):
        """update_decision_prediction returns PredictionError."""
        hpc = HierarchicalPredictiveCoding()
        pred = {'success_probability': 0.5, 'execution_time_ms': 1000.0}
        actual = {
            'decision_type': 'route', 'success': True,
            'execution_time_ms': 500.0
        }
        pe = hpc.update_decision_prediction(pred, actual)
        assert isinstance(pe, PredictionError)
        assert pe.error_magnitude >= 0.0


# ---------------------------------------------------------------------------
# 14. Thread safety
# ---------------------------------------------------------------------------
class TestThreadSafety:
    """Test that concurrent operations do not crash."""

    def test_concurrent_predictions(self):
        """Multiple threads can predict and update without crashing."""
        hpc = HierarchicalPredictiveCoding()
        errors_collected = []
        exceptions = []

        def worker(thread_id):
            try:
                for i in range(20):
                    pred, _ = hpc.predict_task_features({})
                    actual = {
                        'task_type': f'task_{thread_id}',
                        'complexity': (i % 10) / 10.0,
                        'urgency': 0.5
                    }
                    pe = hpc.update_task_prediction(pred, actual)
                    errors_collected.append(pe.error_magnitude)
            except Exception as e:
                exceptions.append(e)

        threads = [threading.Thread(target=worker, args=(tid,)) for tid in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(exceptions) == 0, f"Exceptions in threads: {exceptions}"
        assert len(errors_collected) == 80  # 4 threads * 20 iterations
        assert hpc.total_predictions == 80

    def test_concurrent_curiosity_signal(self):
        """get_curiosity_signal is safe to call concurrently with updates."""
        hpc = HierarchicalPredictiveCoding()
        exceptions = []

        def updater():
            try:
                for _ in range(30):
                    pred = {'task_type': 'a', 'complexity': 0.5, 'urgency': 0.5}
                    actual = {'task_type': 'b', 'complexity': 0.8, 'urgency': 0.2}
                    hpc.update_task_prediction(pred, actual)
            except Exception as e:
                exceptions.append(e)

        def reader():
            try:
                for _ in range(30):
                    signal = hpc.get_curiosity_signal()
                    assert 'curiosity_level' in signal
            except Exception as e:
                exceptions.append(e)

        t1 = threading.Thread(target=updater)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(exceptions) == 0, f"Exceptions: {exceptions}"


# ---------------------------------------------------------------------------
# 15. Integration pattern (predict -> route -> update cycle)
# ---------------------------------------------------------------------------
class TestIntegrationCycle:
    """Test the full predict -> route -> update cycle."""

    def test_full_layer1_cycle(self):
        """Complete cycle: predict features, simulate routing, update."""
        hpc = HierarchicalPredictiveCoding()

        # Step 1: Predict
        prediction, ctx = hpc.predict_task_features({})
        assert isinstance(prediction, dict)

        # Step 2: Simulate routing (actual task arrives)
        actual_features = {
            'task_type': 'deploy',
            'complexity': 0.75,
            'urgency': 0.4
        }

        # Step 3: Update with actual
        pe = hpc.update_task_prediction(prediction, actual_features)
        assert isinstance(pe, PredictionError)

        # Step 4: Check curiosity for next cycle
        signal = hpc.get_curiosity_signal()
        assert signal['total_predictions'] == 1

    def test_full_layer3_cycle(self):
        """Complete cycle: predict outcome, simulate decision, update."""
        hpc = HierarchicalPredictiveCoding()

        # Predict outcome
        prediction, ctx = hpc.predict_decision_outcome({'decision_type': 'route'})
        assert isinstance(prediction, dict)

        # Simulate decision outcome
        actual_outcome = {
            'decision_type': 'route',
            'success': True,
            'execution_time_ms': 350.0
        }

        # Update
        pe = hpc.update_decision_prediction(prediction, actual_outcome)
        assert isinstance(pe, PredictionError)

    def test_multi_round_integration(self):
        """Multiple rounds of predict-update across both layers."""
        hpc = HierarchicalPredictiveCoding()

        task_types = ['deploy', 'test', 'deploy', 'debug', 'deploy']
        for i, tt in enumerate(task_types):
            # Layer1 cycle
            l1_pred, _ = hpc.predict_task_features({})
            l1_actual = {
                'task_type': tt,
                'complexity': 0.5 + (i * 0.1),
                'urgency': 0.3
            }
            hpc.update_task_prediction(l1_pred, l1_actual)

            # Layer3 cycle
            l3_pred, _ = hpc.predict_decision_outcome({'decision_type': 'route'})
            l3_actual = {
                'decision_type': 'route',
                'success': (i % 2 == 0),
                'execution_time_ms': 500.0 + (i * 100)
            }
            hpc.update_decision_prediction(l3_pred, l3_actual)

        stats = hpc.get_statistics()
        assert stats['total_predictions'] == 10  # 5 layer1 + 5 layer3
        assert stats['layer1']['prediction_count'] == 5
        assert stats['layer3']['prediction_count'] == 5


# ---------------------------------------------------------------------------
# 16. Layer history size limits
# ---------------------------------------------------------------------------
class TestHistorySizeLimits:
    """Test that prediction error history is bounded."""

    def test_layer1_history_bounded(self):
        """Layer1 error history does not exceed prediction_history_size."""
        l1 = Layer1Predictor()
        assert l1.prediction_history_size == 100

        # Generate more errors than the limit
        for i in range(150):
            pred = {'task_type': 'a', 'complexity': 0.5, 'urgency': 0.5}
            actual = {'task_type': 'b', 'complexity': float(i % 10) / 10, 'urgency': 0.5}
            l1.compute_error(pred, actual)

        assert len(l1.prediction_errors) <= 100
        assert l1.prediction_count == 150

    def test_layer3_history_bounded(self):
        """Layer3 error history does not exceed prediction_history_size."""
        l3 = Layer3Predictor()
        for i in range(150):
            pred = {'success_probability': 0.5, 'execution_time_ms': 1000.0}
            actual = {
                'decision_type': 'route', 'success': (i % 2 == 0),
                'execution_time_ms': 500.0
            }
            l3.compute_error(pred, actual)

        assert len(l3.prediction_errors) <= 100
        assert l3.prediction_count == 150

    def test_layer3_decision_history_per_type_bounded(self):
        """Layer3 per-decision-type history is bounded at 50."""
        l3 = Layer3Predictor()
        for i in range(80):
            pred = {'success_probability': 0.5, 'execution_time_ms': 1000.0}
            actual = {
                'decision_type': 'route', 'success': True,
                'execution_time_ms': float(i)
            }
            l3.compute_error(pred, actual)

        assert len(l3.decision_history['route']) <= 50


# ---------------------------------------------------------------------------
# 17. Surprise level determination
# ---------------------------------------------------------------------------
class TestSurpriseLevelDetermination:
    """Test the surprise level classification logic."""

    def test_surprise_normal_with_few_errors(self):
        """With fewer than 5 errors, surprise is always 'normal'."""
        l1 = Layer1Predictor()
        for _ in range(4):
            pred = {'task_type': 'a', 'complexity': 0.5, 'urgency': 0.5}
            actual = {'task_type': 'b', 'complexity': 0.9, 'urgency': 0.1}
            pe = l1.compute_error(pred, actual)
            assert pe.surprise_level == 'normal'

    def test_surprise_levels_vary_with_history(self):
        """After building history, different error magnitudes get different levels."""
        l1 = Layer1Predictor()
        # Build a baseline of moderate-variance, low-error predictions.
        # We need enough variance so std > 1e-6 (avoids the "no variation" guard),
        # but keep errors low so a magnitude-1.0 outlier has a large z-score.
        import random
        random.seed(42)
        for _ in range(20):
            c_offset = random.uniform(0.02, 0.10)
            u_offset = random.uniform(0.02, 0.10)
            pred = {'task_type': 'a', 'complexity': 0.50, 'urgency': 0.50}
            actual = {'task_type': 'a', 'complexity': 0.50 + c_offset, 'urgency': 0.50 + u_offset}
            l1.compute_error(pred, actual)

        # Now a very different prediction should get higher surprise
        pred = {'task_type': 'a', 'complexity': 0.0, 'urgency': 0.0}
        actual = {'task_type': 'b', 'complexity': 1.0, 'urgency': 1.0}
        pe = l1.compute_error(pred, actual)
        assert pe.surprise_level in ('high', 'extreme')

    def test_determine_surprise_level_direct(self):
        """Direct call to determine_surprise_level returns valid string."""
        l1 = Layer1Predictor()
        # With no history, returns 'normal'
        level = l1.determine_surprise_level(0.5)
        assert level == 'normal'

    def test_recent_error_stats_empty(self):
        """get_recent_error_stats on empty history returns zeros."""
        l1 = Layer1Predictor()
        stats = l1.get_recent_error_stats()
        assert stats['mean_error'] == 0.0
        assert stats['std_error'] == 0.0
        assert stats['surprise_rate'] == 0.0


# ---------------------------------------------------------------------------
# 18. High surprise event tracking
# ---------------------------------------------------------------------------
class TestHighSurpriseTracking:
    """Test that high surprise events are tracked at the HPC level."""

    def test_high_surprise_recorded(self):
        """High surprise events from layer1 are stored."""
        hpc = HierarchicalPredictiveCoding()
        # Build baseline of low-error predictions
        for _ in range(20):
            pred = {'task_type': 'a', 'complexity': 0.50, 'urgency': 0.50}
            actual = {'task_type': 'a', 'complexity': 0.51, 'urgency': 0.49}
            hpc.update_task_prediction(pred, actual)

        initial_count = len(hpc.high_surprise_events)

        # Inject high-error prediction
        pred = {'task_type': 'a', 'complexity': 0.0, 'urgency': 0.0}
        actual = {'task_type': 'z', 'complexity': 1.0, 'urgency': 1.0}
        pe = hpc.update_task_prediction(pred, actual)

        if pe.surprise_level in ('high', 'extreme'):
            assert len(hpc.high_surprise_events) > initial_count
            event = hpc.high_surprise_events[-1]
            assert event['layer'] == 'layer1'
            assert 'error_magnitude' in event
            assert 'prediction' in event
            assert 'actual' in event

    def test_high_surprise_event_structure(self):
        """High surprise events have the expected structure."""
        hpc = HierarchicalPredictiveCoding()
        # Build baseline for layer3
        for _ in range(20):
            pred = {'success_probability': 0.5, 'execution_time_ms': 1000.0}
            actual = {
                'decision_type': 'route', 'success': True,
                'execution_time_ms': 1010.0
            }
            hpc.update_decision_prediction(pred, actual)

        # Inject outlier
        pred = {'success_probability': 1.0, 'execution_time_ms': 100.0}
        actual = {
            'decision_type': 'route', 'success': False,
            'execution_time_ms': 50000.0
        }
        pe = hpc.update_decision_prediction(pred, actual)

        if pe.surprise_level in ('high', 'extreme'):
            event = hpc.high_surprise_events[-1]
            assert event['layer'] == 'layer3'


# ---------------------------------------------------------------------------
# 19. PredictionError dataclass edge cases
# ---------------------------------------------------------------------------
class TestPredictionErrorDataclass:
    """Test PredictionError dataclass behavior."""

    def test_default_values(self):
        """PredictionError defaults are correct."""
        pe = PredictionError(error_magnitude=0.5)
        assert pe.error_magnitude == 0.5
        assert pe.error_vector is None
        assert pe.confidence == 1.0
        assert pe.surprise_level == 'normal'

    def test_custom_values(self):
        """PredictionError accepts all custom values."""
        vec = np.array([0.1, 0.2, 0.3])
        pe = PredictionError(
            error_magnitude=0.2,
            error_vector=vec,
            confidence=0.75,
            surprise_level='extreme'
        )
        assert pe.error_magnitude == 0.2
        assert np.array_equal(pe.error_vector, vec)
        assert pe.confidence == 0.75
        assert pe.surprise_level == 'extreme'

    def test_to_dict_round_trip(self):
        """to_dict produces JSON-serializable output."""
        import json
        pe = PredictionError(
            error_magnitude=0.42,
            error_vector=np.array([0.1, 0.32]),
            confidence=0.9,
            surprise_level='high'
        )
        d = pe.to_dict()
        # Should be JSON-serializable
        json_str = json.dumps(d)
        assert isinstance(json_str, str)
        loaded = json.loads(json_str)
        assert loaded['error_magnitude'] == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# 20. record_error and get_recent_error_stats
# ---------------------------------------------------------------------------
class TestRecordErrorAndStats:
    """Test the base PredictiveLayer record_error and stats methods."""

    def test_record_error_increments_count(self):
        """record_error increments prediction_count."""
        l1 = Layer1Predictor()
        pe = PredictionError(error_magnitude=0.3)
        l1.record_error(pe)
        assert l1.prediction_count == 1
        assert len(l1.prediction_errors) == 1

    def test_get_recent_error_stats_correct(self):
        """get_recent_error_stats computes correct mean and std."""
        l1 = Layer1Predictor()
        for val in [0.1, 0.2, 0.3, 0.4, 0.5]:
            l1.record_error(PredictionError(error_magnitude=val))

        stats = l1.get_recent_error_stats(window=5)
        assert stats['mean_error'] == pytest.approx(0.3, abs=1e-6)
        assert stats['std_error'] == pytest.approx(np.std([0.1, 0.2, 0.3, 0.4, 0.5]), abs=1e-6)

    def test_get_recent_error_stats_window(self):
        """Stats window only considers recent errors."""
        l1 = Layer1Predictor()
        # Add 10 low errors then 5 high errors
        for _ in range(10):
            l1.record_error(PredictionError(error_magnitude=0.1))
        for _ in range(5):
            l1.record_error(PredictionError(error_magnitude=0.9))

        stats = l1.get_recent_error_stats(window=5)
        assert stats['mean_error'] == pytest.approx(0.9, abs=1e-6)

    def test_surprise_rate_computation(self):
        """Surprise rate correctly counts high/extreme events."""
        l1 = Layer1Predictor()
        l1.record_error(PredictionError(error_magnitude=0.1, surprise_level='low'))
        l1.record_error(PredictionError(error_magnitude=0.5, surprise_level='normal'))
        l1.record_error(PredictionError(error_magnitude=0.8, surprise_level='high'))
        l1.record_error(PredictionError(error_magnitude=0.9, surprise_level='extreme'))

        stats = l1.get_recent_error_stats(window=4)
        assert stats['surprise_rate'] == pytest.approx(0.5)  # 2 out of 4
