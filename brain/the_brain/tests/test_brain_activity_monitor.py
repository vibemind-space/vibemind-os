"""
Tests for BrainActivityMonitor (P3.35)
Verifies gate history, statistics, anomaly detection, activation levels, and alerts.
"""

import sys
import os
import numpy as np
import pytest

# Project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.brain_monitor import BrainActivityMonitor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def monitor():
    """Fresh monitor with default history length."""
    return BrainActivityMonitor(history_length=100)


@pytest.fixture
def small_monitor():
    """Monitor with short history (5) for overflow testing."""
    return BrainActivityMonitor(history_length=5)


def _make_routing_output(gates=None, error_count=0, memory_encoded=False,
                         num_memories=0, success=True, max_tool_repetition=0,
                         qa_reject_count=0, clarification_count=0):
    """Helper to create a routing output dict."""
    if gates is None:
        gates = np.ones(10) / 10.0
    return {
        'final_gates': np.array(gates, dtype=np.float64),
        'trace_features': {
            'error_count': error_count,
            'max_tool_repetition': max_tool_repetition,
            'qa_reject_count': qa_reject_count,
            'clarification_count': clarification_count,
        },
        'hippocampal_output': {
            'encoded': memory_encoded,
            'num_memories': num_memories,
        },
        'success': success,
    }


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestBrainActivityMonitorInit:

    def test_default_init(self, monitor):
        assert monitor.history_length == 100
        assert len(monitor.gate_history) == 0
        assert len(monitor.error_history) == 0
        assert len(monitor.memory_retrieval_history) == 0
        assert len(monitor.prediction_history) == 0

    def test_custom_history_length(self):
        m = BrainActivityMonitor(history_length=10)
        assert m.history_length == 10

    def test_initial_activations_zero(self, monitor):
        for key, val in monitor.current_activation.items():
            assert val == 0.0, f"Activation {key} should start at 0.0"

    def test_initial_alerts_empty(self, monitor):
        assert monitor.alerts == []


# ---------------------------------------------------------------------------
# Update & Activation computation
# ---------------------------------------------------------------------------

class TestBrainActivityMonitorUpdate:

    def test_single_update(self, monitor):
        monitor.update(_make_routing_output())
        assert len(monitor.gate_history) == 1
        assert len(monitor.error_history) == 1
        assert len(monitor.memory_retrieval_history) == 1
        assert len(monitor.prediction_history) == 1

    def test_multiple_updates(self, monitor):
        for _ in range(5):
            monitor.update(_make_routing_output())
        assert len(monitor.gate_history) == 5

    def test_history_overflow(self, small_monitor):
        """History should respect maxlen."""
        for i in range(10):
            small_monitor.update(_make_routing_output(error_count=i))
        assert len(small_monitor.gate_history) == 5
        assert len(small_monitor.error_history) == 5
        # Oldest entries should be gone, newest = 5,6,7,8,9
        errors = list(small_monitor.error_history)
        assert errors == [5, 6, 7, 8, 9]

    def test_thalamus_activation(self, monitor):
        gates = np.array([0.2, 0.1, 0.05, 0.05, 0.1, 0.05, 0.15, 0.1, 0.1, 0.1])
        monitor.update(_make_routing_output(gates=gates))
        assert abs(monitor.current_activation['thalamus'] - np.mean(gates)) < 1e-6

    def test_hippocampus_activation_low(self, monitor):
        monitor.update(_make_routing_output(num_memories=5))
        assert abs(monitor.current_activation['hippocampus'] - 5 / 20.0) < 1e-6

    def test_hippocampus_activation_clamped(self, monitor):
        """More than 20 memories should clamp activation to 1.0."""
        monitor.update(_make_routing_output(num_memories=50))
        assert monitor.current_activation['hippocampus'] == 1.0

    def test_error_detection_activation(self, monitor):
        monitor.update(_make_routing_output(error_count=3))
        assert abs(monitor.current_activation['error_detection'] - 3 / 10.0) < 1e-6

    def test_error_detection_clamped(self, monitor):
        monitor.update(_make_routing_output(error_count=20))
        assert monitor.current_activation['error_detection'] == 1.0

    def test_tool_trace_activation(self, monitor):
        gates = np.zeros(10)
        gates[6] = 0.75  # tool_trace index
        monitor.update(_make_routing_output(gates=gates))
        assert abs(monitor.current_activation['tool_trace'] - 0.75) < 1e-6

    def test_temporal_activation(self, monitor):
        gates = np.zeros(10)
        gates[7] = 0.42  # temporal_pattern index
        monitor.update(_make_routing_output(gates=gates))
        assert abs(monitor.current_activation['temporal'] - 0.42) < 1e-6

    def test_success_prediction_tracked(self, monitor):
        monitor.update(_make_routing_output(success=True))
        monitor.update(_make_routing_output(success=False))
        preds = list(monitor.prediction_history)
        assert preds == [True, False]

    def test_gates_copied_not_referenced(self, monitor):
        """Gate arrays in history should be copies, not references."""
        gates = np.ones(10) / 10.0
        out = _make_routing_output(gates=gates)
        monitor.update(out)
        # Mutate original
        out['final_gates'][0] = 999.0
        stored = list(monitor.gate_history)[0]
        assert stored[0] != 999.0


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class TestBrainActivityMonitorAlerts:

    def test_no_alerts_normal(self, monitor):
        monitor.update(_make_routing_output())
        assert monitor.alerts == []

    def test_high_error_alert(self, monitor):
        monitor.update(_make_routing_output(error_count=6))
        assert len(monitor.alerts) == 1
        assert monitor.alerts[0]['level'] == 'warning'
        assert 'error' in monitor.alerts[0]['message'].lower()

    def test_stuck_loop_alert(self, monitor):
        monitor.update(_make_routing_output(max_tool_repetition=6))
        assert any(a['level'] == 'critical' for a in monitor.alerts)

    def test_qa_reject_alert(self, monitor):
        monitor.update(_make_routing_output(qa_reject_count=4))
        assert any('QA' in a['message'] for a in monitor.alerts)

    def test_clarification_alert(self, monitor):
        monitor.update(_make_routing_output(clarification_count=4))
        assert any('clarification' in a['message'] for a in monitor.alerts)

    def test_multiple_alerts(self, monitor):
        """Multiple alert conditions trigger multiple alerts."""
        monitor.update(_make_routing_output(
            error_count=6,
            max_tool_repetition=6,
            qa_reject_count=4,
            clarification_count=4
        ))
        assert len(monitor.alerts) == 4

    def test_alerts_reset_on_next_update(self, monitor):
        """Alerts from one update should not persist to the next."""
        monitor.update(_make_routing_output(error_count=10))
        assert len(monitor.alerts) >= 1
        monitor.update(_make_routing_output(error_count=0))
        assert len(monitor.alerts) == 0

    def test_alert_has_recommendation(self, monitor):
        monitor.update(_make_routing_output(error_count=6))
        for alert in monitor.alerts:
            assert 'recommendation' in alert
            assert len(alert['recommendation']) > 0


# ---------------------------------------------------------------------------
# Activation Summary
# ---------------------------------------------------------------------------

class TestBrainActivityMonitorSummary:

    def test_summary_empty(self, monitor):
        summary = monitor.get_activation_summary()
        assert summary['gate_strength'] == 0.0
        assert summary['avg_error_rate'] == 0.0
        assert summary['total_memories'] == 0

    def test_summary_after_updates(self, monitor):
        monitor.update(_make_routing_output(error_count=2, num_memories=10))
        monitor.update(_make_routing_output(error_count=4, num_memories=15))
        summary = monitor.get_activation_summary()
        assert abs(summary['avg_error_rate'] - 3.0) < 1e-6
        assert summary['total_memories'] == 15  # latest value

    def test_summary_contains_activations(self, monitor):
        monitor.update(_make_routing_output())
        summary = monitor.get_activation_summary()
        assert 'current_activation' in summary
        assert 'thalamus' in summary['current_activation']

    def test_summary_copy_safety(self, monitor):
        """Summary dict should be a copy, not a reference."""
        monitor.update(_make_routing_output())
        s1 = monitor.get_activation_summary()
        s1['current_activation']['thalamus'] = 999
        s2 = monitor.get_activation_summary()
        assert s2['current_activation']['thalamus'] != 999


# ---------------------------------------------------------------------------
# Dominant Modality
# ---------------------------------------------------------------------------

class TestBrainActivityMonitorDominantModality:

    def test_dominant_none_when_empty(self, monitor):
        assert monitor.get_dominant_modality() == "none"

    def test_dominant_vision(self, monitor):
        gates = np.zeros(10)
        gates[0] = 0.9  # vision
        monitor.update(_make_routing_output(gates=gates))
        assert monitor.get_dominant_modality() == "vision"

    def test_dominant_temporal(self, monitor):
        gates = np.zeros(10)
        gates[7] = 0.8  # temporal
        monitor.update(_make_routing_output(gates=gates))
        assert monitor.get_dominant_modality() == "temporal"

    def test_dominant_tool_trace(self, monitor):
        gates = np.zeros(10)
        gates[6] = 0.7  # tool_trace
        monitor.update(_make_routing_output(gates=gates))
        assert monitor.get_dominant_modality() == "tool_trace"

    def test_dominant_error_sig(self, monitor):
        gates = np.zeros(10)
        gates[8] = 0.95  # error_sig
        monitor.update(_make_routing_output(gates=gates))
        assert monitor.get_dominant_modality() == "error_sig"


# ---------------------------------------------------------------------------
# ASCII Visualization
# ---------------------------------------------------------------------------

class TestBrainActivityMonitorVisualize:

    def test_visualize_empty(self, monitor):
        viz = monitor.visualize_ascii()
        assert "BRAIN ACTIVITY MONITOR" in viz

    def test_visualize_after_update(self, monitor):
        monitor.update(_make_routing_output())
        viz = monitor.visualize_ascii()
        assert "MODULE ACTIVATION LEVELS" in viz
        assert "CURRENT GATE DISTRIBUTION" in viz
        assert "STATISTICS" in viz

    def test_visualize_shows_alerts(self, monitor):
        monitor.update(_make_routing_output(error_count=10))
        viz = monitor.visualize_ascii()
        assert "ALERTS" in viz
        assert "WARNING" in viz


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

class TestBrainActivityMonitorReset:

    def test_reset_clears_history(self, monitor):
        for _ in range(5):
            monitor.update(_make_routing_output())
        monitor.reset()
        assert len(monitor.gate_history) == 0
        assert len(monitor.error_history) == 0
        assert len(monitor.memory_retrieval_history) == 0
        assert len(monitor.prediction_history) == 0

    def test_reset_clears_activations(self, monitor):
        monitor.update(_make_routing_output(error_count=5, num_memories=10))
        monitor.reset()
        for key, val in monitor.current_activation.items():
            assert val == 0.0

    def test_reset_clears_alerts(self, monitor):
        monitor.update(_make_routing_output(error_count=10))
        assert len(monitor.alerts) >= 1
        monitor.reset()
        assert len(monitor.alerts) == 0


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestBrainActivityMonitorEdgeCases:

    def test_short_gate_vector(self, monitor):
        """Gates with fewer than 10 elements should not crash."""
        gates = np.array([0.5, 0.5])
        monitor.update(_make_routing_output(gates=gates))
        assert monitor.current_activation['thalamus'] == 0.5

    def test_empty_gate_vector(self, monitor):
        gates = np.array([])
        monitor.update(_make_routing_output(gates=gates))
        assert monitor.current_activation['thalamus'] == 0.0

    def test_missing_trace_features(self, monitor):
        """Routing output with no trace_features should not crash."""
        out = {'final_gates': np.ones(10) / 10.0}
        monitor.update(out)
        assert len(monitor.gate_history) == 1

    def test_fallback_to_gates_key(self, monitor):
        """If final_gates is missing, fall back to 'gates' key."""
        out = {'gates': np.ones(10) * 0.1}
        monitor.update(out)
        stored = list(monitor.gate_history)[0]
        assert abs(stored[0] - 0.1) < 1e-6


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
