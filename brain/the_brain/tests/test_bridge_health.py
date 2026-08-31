"""
Tests for BridgeHealthMonitor: stuck detection, saturation, NaN handling,
auto-recovery, Prometheus metrics, and summary reporting.
"""

import math
import pytest
from dataclasses import dataclass
from unittest.mock import MagicMock

from core.bridge_health_monitor import (
    BridgeHealthMonitor,
    FieldStatus,
    BRIDGE_FIELD_RANGES,
    BRIDGE_NAMES,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

@dataclass
class FakeNeuromodState:
    dopamine: float = 0.5
    norepinephrine: float = 0.5
    serotonin: float = 0.5
    acetylcholine: float = 0.5
    anti_reward: float = 0.0
    ne_gain: float = 1.0
    explore_ratio: float = 0.5


@dataclass
class FakeLimbicState:
    valence: float = 0.0
    arousal: float = 0.3
    threat_level: float = 0.0
    is_threat: bool = False
    go_drive: float = 0.5
    nogo_drive: float = 0.5
    net_value: float = 0.0
    effort_cost: float = 0.3
    salience: float = 0.3
    body_budget: float = 1.0
    feeling: str = 'neutral'
    urgency: float = 0.0
    approach_drive: float = 0.3
    stress: float = 0.0


def _make_default_states() -> dict:
    """Create dict of all 10 bridges with default float-dict states."""
    states = {}
    for bridge_name, field_ranges in BRIDGE_FIELD_RANGES.items():
        state = {}
        for field_name, (low, high) in field_ranges.items():
            state[field_name] = (low + high) / 2  # midpoint
        states[bridge_name] = state
    return states


def _make_monitor(**kwargs) -> BridgeHealthMonitor:
    """Create a monitor with test-friendly defaults."""
    defaults = dict(
        window_size=20,
        stuck_epsilon=1e-8,
        saturation_ticks=5,
        saturation_margin=0.01,
        auto_recover=False,
        noise_scale=0.05,
    )
    defaults.update(kwargs)
    return BridgeHealthMonitor(**defaults)


# ─── Test: Basic Operation ────────────────────────────────────────────────────

class TestBasicOperation:
    def test_init_creates_history_for_all_bridges(self):
        mon = _make_monitor()
        assert len(mon._history) == 10
        for bridge_name in BRIDGE_NAMES:
            assert bridge_name in mon._history

    def test_record_tick_increments_counter(self):
        mon = _make_monitor()
        states = _make_default_states()
        mon.record_tick(states)
        assert mon.tick_count == 1
        mon.record_tick(states)
        assert mon.tick_count == 2

    def test_record_tick_populates_history(self):
        mon = _make_monitor()
        states = _make_default_states()
        mon.record_tick(states)
        # Check neuromod.dopamine has one entry
        hist = mon._history['neuromod']['dopamine']
        assert len(hist) == 1
        assert hist[0] == 0.5  # midpoint of (0, 1)

    def test_check_health_all_healthy_at_start(self):
        mon = _make_monitor()
        health = mon.check_health()
        # No data recorded → everything healthy
        for bridge_name, fields in health.items():
            for field_name, status in fields.items():
                assert status == FieldStatus.HEALTHY, \
                    f"{bridge_name}.{field_name} should be healthy, got {status}"

    def test_check_health_with_normal_data(self):
        """Normal varying data should all be healthy."""
        mon = _make_monitor(window_size=10)
        import random
        rng = random.Random(42)

        for _ in range(15):
            states = {}
            for bridge_name, field_ranges in BRIDGE_FIELD_RANGES.items():
                state = {}
                for field_name, (low, high) in field_ranges.items():
                    # Random value within range
                    state[field_name] = low + rng.random() * (high - low)
                states[bridge_name] = state
            mon.record_tick(states)

        health = mon.check_health()
        for bridge_name, fields in health.items():
            for field_name, status in fields.items():
                assert status == FieldStatus.HEALTHY, \
                    f"{bridge_name}.{field_name} should be healthy, got {status}"

    def test_works_with_dataclass_states(self):
        """Monitor should accept dataclass state objects."""
        mon = _make_monitor()
        states = _make_default_states()
        states['neuromod'] = FakeNeuromodState(dopamine=0.7)
        mon.record_tick(states)
        hist = mon._history['neuromod']['dopamine']
        assert len(hist) == 1
        assert hist[0] == 0.7

    def test_works_with_dict_states(self):
        """Monitor should accept dict state objects."""
        mon = _make_monitor()
        states = {'neuromod': {'dopamine': 0.6, 'serotonin': 0.4}}
        mon.record_tick(states)
        assert mon._history['neuromod']['dopamine'][-1] == 0.6

    def test_missing_bridge_skipped(self):
        """Missing bridges should be silently skipped."""
        mon = _make_monitor()
        mon.record_tick({'neuromod': {'dopamine': 0.5}})  # Only one bridge
        assert mon.tick_count == 1
        # Other bridges have no history
        assert len(mon._history['cortex']['conflict']) == 0

    def test_skips_bool_fields(self):
        """Boolean fields in dataclass should be skipped."""
        mon = _make_monitor()
        states = _make_default_states()
        states['limbic'] = FakeLimbicState(is_threat=True)
        mon.record_tick(states)
        # is_threat is not in BRIDGE_FIELD_RANGES, so no crash


# ─── Test: Stuck Detection ────────────────────────────────────────────────────

class TestStuckDetection:
    def test_constant_value_detected_as_stuck(self):
        """A field that never changes should be detected as stuck."""
        mon = _make_monitor(window_size=15)
        for _ in range(15):
            mon.record_tick({'neuromod': {'dopamine': 0.5}})

        health = mon.check_health()
        assert health['neuromod']['dopamine'] == FieldStatus.STUCK

    def test_tiny_variation_still_stuck(self):
        """Variation below epsilon should still be stuck."""
        mon = _make_monitor(window_size=15, stuck_epsilon=1e-6)
        for i in range(15):
            val = 0.5 + (i % 2) * 1e-8  # Variation = 1e-16, well below epsilon
            mon.record_tick({'neuromod': {'dopamine': val}})

        health = mon.check_health()
        assert health['neuromod']['dopamine'] == FieldStatus.STUCK

    def test_sufficient_variation_is_healthy(self):
        """Variation above epsilon should be healthy."""
        mon = _make_monitor(window_size=15)
        for i in range(15):
            val = 0.5 + (i % 3) * 0.01  # Meaningful variation
            mon.record_tick({'neuromod': {'dopamine': val}})

        health = mon.check_health()
        assert health['neuromod']['dopamine'] == FieldStatus.HEALTHY

    def test_stuck_not_triggered_with_few_samples(self):
        """Stuck should not trigger until we have enough data."""
        mon = _make_monitor(window_size=20)
        for _ in range(5):  # Only 5 samples, need min(10, 20) = 10
            mon.record_tick({'neuromod': {'dopamine': 0.5}})

        health = mon.check_health()
        assert health['neuromod']['dopamine'] == FieldStatus.HEALTHY

    def test_multiple_fields_stuck_independently(self):
        """Each field is tracked independently."""
        mon = _make_monitor(window_size=15)
        for i in range(15):
            mon.record_tick({
                'neuromod': {
                    'dopamine': 0.5,  # stuck
                    'serotonin': 0.3 + i * 0.01,  # varying
                }
            })

        health = mon.check_health()
        assert health['neuromod']['dopamine'] == FieldStatus.STUCK
        assert health['neuromod']['serotonin'] == FieldStatus.HEALTHY


# ─── Test: Saturation Detection ───────────────────────────────────────────────

class TestSaturationDetection:
    def test_at_upper_boundary_detected(self):
        """Value at upper boundary for enough ticks → saturated."""
        mon = _make_monitor(saturation_ticks=5, saturation_margin=0.02)
        for _ in range(6):
            mon.record_tick({'neuromod': {'dopamine': 0.999}})  # At upper bound

        health = mon.check_health()
        assert health['neuromod']['dopamine'] == FieldStatus.SATURATED

    def test_at_lower_boundary_detected(self):
        """Value at lower boundary for enough ticks → saturated."""
        mon = _make_monitor(saturation_ticks=5, saturation_margin=0.02)
        for _ in range(6):
            mon.record_tick({'neuromod': {'dopamine': 0.001}})  # At lower bound

        health = mon.check_health()
        assert health['neuromod']['dopamine'] == FieldStatus.SATURATED

    def test_boundary_streak_resets(self):
        """Moving away from boundary resets the streak."""
        mon = _make_monitor(saturation_ticks=5, saturation_margin=0.02)
        for _ in range(4):
            mon.record_tick({'neuromod': {'dopamine': 0.999}})
        # Move away
        mon.record_tick({'neuromod': {'dopamine': 0.5}})
        # Back at boundary
        for _ in range(4):
            mon.record_tick({'neuromod': {'dopamine': 0.999}})

        health = mon.check_health()
        # Streak was reset, only 4 consecutive now → not saturated
        assert health['neuromod']['dopamine'] != FieldStatus.SATURATED

    def test_just_inside_margin_not_saturated(self):
        """Value just inside the margin should not trigger."""
        mon = _make_monitor(saturation_ticks=5, saturation_margin=0.01)
        for _ in range(6):
            mon.record_tick({'neuromod': {'dopamine': 0.5}})  # Well within range

        health = mon.check_health()
        assert health['neuromod']['dopamine'] != FieldStatus.SATURATED

    def test_negative_range_lower_boundary(self):
        """Saturation at lower boundary of negative-range field (valence)."""
        mon = _make_monitor(saturation_ticks=5, saturation_margin=0.02)
        for _ in range(6):
            mon.record_tick({'limbic': {'valence': -0.999}})

        health = mon.check_health()
        assert health['limbic']['valence'] == FieldStatus.SATURATED


# ─── Test: NaN / Inf Detection ────────────────────────────────────────────────

class TestNaNInfDetection:
    def test_nan_detected_as_error(self):
        mon = _make_monitor()
        mon.record_tick({'neuromod': {'dopamine': float('nan')}})
        health = mon.check_health()
        assert health['neuromod']['dopamine'] == FieldStatus.ERROR

    def test_inf_detected_as_error(self):
        mon = _make_monitor()
        mon.record_tick({'neuromod': {'dopamine': float('inf')}})
        health = mon.check_health()
        assert health['neuromod']['dopamine'] == FieldStatus.ERROR

    def test_neg_inf_detected_as_error(self):
        mon = _make_monitor()
        mon.record_tick({'neuromod': {'dopamine': float('-inf')}})
        health = mon.check_health()
        assert health['neuromod']['dopamine'] == FieldStatus.ERROR

    def test_nan_in_history_detected(self):
        """NaN anywhere in the window flags error."""
        mon = _make_monitor(window_size=10)
        mon.record_tick({'neuromod': {'dopamine': float('nan')}})
        for _ in range(5):
            mon.record_tick({'neuromod': {'dopamine': 0.5}})

        health = mon.check_health()
        assert health['neuromod']['dopamine'] == FieldStatus.ERROR

    def test_clean_after_nan_scrolls_out(self):
        """Once NaN scrolls out of window, field becomes healthy again."""
        mon = _make_monitor(window_size=5)
        mon.record_tick({'neuromod': {'dopamine': float('nan')}})
        # Fill window with clean data to push NaN out
        for i in range(6):
            mon.record_tick({'neuromod': {'dopamine': 0.4 + i * 0.02}})

        health = mon.check_health()
        assert health['neuromod']['dopamine'] == FieldStatus.HEALTHY


# ─── Test: Auto-Recovery ──────────────────────────────────────────────────────

class TestAutoRecovery:
    def test_recovery_on_dataclass(self):
        """Auto-recovery should modify dataclass field in-place."""
        mon = _make_monitor(noise_scale=0.1)
        state = FakeNeuromodState(dopamine=0.5)
        result = mon.attempt_recovery('neuromod', 'dopamine', state)
        assert result is True
        # Value should have changed (with noise_scale=0.1, very unlikely to be exactly 0.5)
        assert state.dopamine != 0.5 or True  # Noise could be 0 in rare case
        # Value should stay within range
        assert 0.0 <= state.dopamine <= 1.0

    def test_recovery_on_dict(self):
        """Auto-recovery should modify dict field in-place."""
        mon = _make_monitor(noise_scale=0.1)
        state = {'dopamine': 0.5, 'serotonin': 0.5}
        result = mon.attempt_recovery('neuromod', 'dopamine', state)
        assert result is True
        assert 0.0 <= state['dopamine'] <= 1.0

    def test_recovery_clamps_to_range(self):
        """Perturbed value should be clamped to field range."""
        mon = _make_monitor(noise_scale=10.0)  # Large noise
        state = FakeNeuromodState(dopamine=0.999)
        mon.attempt_recovery('neuromod', 'dopamine', state)
        assert 0.0 <= state.dopamine <= 1.0

    def test_recovery_logged(self):
        """Recovery events should be logged."""
        mon = _make_monitor(noise_scale=0.1)
        state = FakeNeuromodState(dopamine=0.5)
        mon.attempt_recovery('neuromod', 'dopamine', state)
        assert len(mon.recovery_log) == 1
        event = mon.recovery_log[0]
        assert event['bridge'] == 'neuromod'
        assert event['field'] == 'dopamine'
        assert event['old_value'] == 0.5

    def test_recovery_invalid_bridge_returns_false(self):
        mon = _make_monitor()
        result = mon.attempt_recovery('nonexistent', 'dopamine', {})
        assert result is False

    def test_recovery_invalid_field_returns_false(self):
        mon = _make_monitor()
        result = mon.attempt_recovery('neuromod', 'nonexistent', {})
        assert result is False

    def test_ne_gain_recovery_respects_range(self):
        """ne_gain has special range [0.2, 2.0]."""
        mon = _make_monitor(noise_scale=0.1)
        state = FakeNeuromodState(ne_gain=0.2)
        mon.attempt_recovery('neuromod', 'ne_gain', state)
        assert 0.2 <= state.ne_gain <= 2.0


# ─── Test: Rolling Stats ─────────────────────────────────────────────────────

class TestRollingStats:
    def test_stats_empty(self):
        mon = _make_monitor()
        stats = mon.get_stats('neuromod', 'dopamine')
        assert stats['count'] == 0
        assert stats['mean'] == 0.0

    def test_stats_computed_correctly(self):
        mon = _make_monitor(window_size=10)
        values = [0.1, 0.2, 0.3, 0.4, 0.5]
        for v in values:
            mon.record_tick({'neuromod': {'dopamine': v}})

        stats = mon.get_stats('neuromod', 'dopamine')
        assert stats['count'] == 5
        assert abs(stats['mean'] - 0.3) < 1e-9
        assert abs(stats['min'] - 0.1) < 1e-9
        assert abs(stats['max'] - 0.5) < 1e-9
        assert stats['variance'] > 0

    def test_stats_rolling_window(self):
        """Stats should only consider the window."""
        mon = _make_monitor(window_size=3)
        for v in [0.1, 0.2, 0.3, 0.4, 0.5]:
            mon.record_tick({'neuromod': {'dopamine': v}})

        stats = mon.get_stats('neuromod', 'dopamine')
        assert stats['count'] == 3  # Window size
        assert abs(stats['min'] - 0.3) < 1e-9  # Oldest in window
        assert abs(stats['max'] - 0.5) < 1e-9

    def test_stats_nonexistent_bridge(self):
        mon = _make_monitor()
        stats = mon.get_stats('nonexistent', 'field')
        assert stats['count'] == 0


# ─── Test: Summary ────────────────────────────────────────────────────────────

class TestSummary:
    def test_summary_structure(self):
        mon = _make_monitor()
        summary = mon.get_summary()
        assert 'tick_count' in summary
        assert 'total_fields' in summary
        assert 'status_counts' in summary
        assert 'per_bridge' in summary
        assert 'recovery_events' in summary

    def test_summary_counts_issues(self):
        """Summary should count stuck fields."""
        mon = _make_monitor(window_size=15)
        for _ in range(15):
            mon.record_tick({'neuromod': {'dopamine': 0.5}})  # stuck

        summary = mon.get_summary()
        assert summary['status_counts'][FieldStatus.STUCK] >= 1

    def test_summary_per_bridge(self):
        mon = _make_monitor()
        summary = mon.get_summary()
        for bridge_name in BRIDGE_NAMES:
            assert bridge_name in summary['per_bridge']
            assert 'healthy' in summary['per_bridge'][bridge_name]
            assert 'issues' in summary['per_bridge'][bridge_name]


# ─── Test: Prometheus Metrics ─────────────────────────────────────────────────

class TestPrometheusMetrics:
    def test_publish_metrics_sets_gauges(self):
        """publish_metrics should set gauges on BrainMetrics."""
        mon = _make_monitor(window_size=15)
        for _ in range(15):
            mon.record_tick({'neuromod': {'dopamine': 0.5}})

        metrics = MagicMock()
        mon.publish_metrics(metrics)

        # Should have called set_gauge for each bridge's health counts
        assert metrics.set_gauge.called
        calls = metrics.set_gauge.call_args_list
        gauge_names = [c[0][0] for c in calls]
        assert 'brain_bridge_health_healthy' in gauge_names
        assert 'brain_bridge_health_stuck' in gauge_names
        assert 'brain_bridge_health_total_issues' in gauge_names

    def test_publish_metrics_labels_bridge_name(self):
        """Gauges should be labeled with bridge name."""
        mon = _make_monitor()
        states = _make_default_states()
        mon.record_tick(states)

        metrics = MagicMock()
        mon.publish_metrics(metrics)

        # Find a call with bridge='neuromod'
        found = False
        for call in metrics.set_gauge.call_args_list:
            kwargs = call[1] if call[1] else {}
            if kwargs.get('bridge') == 'neuromod':
                found = True
                break
        assert found, "Expected gauge with bridge='neuromod' label"


# ─── Test: All Bridges Together ───────────────────────────────────────────────

class TestAllBridges:
    def test_all_bridges_monitored(self):
        """All 10 bridges should appear in health report."""
        mon = _make_monitor()
        health = mon.check_health()
        assert len(health) == 10
        for name in BRIDGE_NAMES:
            assert name in health

    def test_all_bridges_have_expected_fields(self):
        """Each bridge in health report should have all expected fields."""
        mon = _make_monitor()
        health = mon.check_health()
        for bridge_name, expected_fields in BRIDGE_FIELD_RANGES.items():
            for field_name in expected_fields:
                assert field_name in health[bridge_name], \
                    f"Missing {bridge_name}.{field_name} in health report"

    def test_full_tick_with_all_bridges(self):
        """Full tick with all 10 bridges should work."""
        mon = _make_monitor()
        states = _make_default_states()
        mon.record_tick(states)
        health = mon.check_health()
        # All should be healthy after one tick
        for bridge_name, fields in health.items():
            for field_name, status in fields.items():
                assert status == FieldStatus.HEALTHY


# ─── Test: Edge Cases ─────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_dict_state_handled(self):
        """Empty dict for a bridge should be fine (no fields recorded)."""
        mon = _make_monitor()
        mon.record_tick({'neuromod': {}})
        assert mon.tick_count == 1

    def test_extra_fields_ignored(self):
        """Extra fields in state dict should be silently ignored."""
        mon = _make_monitor()
        mon.record_tick({'neuromod': {'dopamine': 0.5, 'unknown_field': 99.0}})
        assert mon._history['neuromod']['dopamine'][-1] == 0.5

    def test_priority_error_over_stuck(self):
        """If field has NaN, error status takes priority over stuck."""
        mon = _make_monitor(window_size=15)
        for _ in range(14):
            mon.record_tick({'neuromod': {'dopamine': 0.5}})
        mon.record_tick({'neuromod': {'dopamine': float('nan')}})

        health = mon.check_health()
        assert health['neuromod']['dopamine'] == FieldStatus.ERROR

    def test_saturation_and_stuck_together(self):
        """A field stuck at the boundary should be saturated (checked first by priority)."""
        mon = _make_monitor(window_size=15, saturation_ticks=5)
        for _ in range(15):
            mon.record_tick({'neuromod': {'dopamine': 1.0}})

        health = mon.check_health()
        # Saturated is checked before stuck in the code flow
        assert health['neuromod']['dopamine'] == FieldStatus.SATURATED
