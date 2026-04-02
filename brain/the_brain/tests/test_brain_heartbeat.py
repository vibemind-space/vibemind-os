"""
Unit tests for BrainHeartbeat - Autonomous Background Processing.

Test coverage:
- Heartbeat initialization & configuration
- Tick interval handling & tick counting
- Idle detection (when no predictions come in)
- Dream mode trigger (after idle threshold)
- Health monitoring
- Thread safety
- Homeostatic forced dream trigger
- State reporting
- Error handling during tick
- Graceful shutdown
- Callback invocation (on_tick, on_dream, on_error)
- History trimming (heartbeat_history, errors)
- mark_prediction resets idle timer
- Meta-learning check interval
"""

import pytest
import time
import threading
import sys
import os
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime

# Add project root so imports resolve without heavy production deps
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, root)

from production.brain_heartbeat import BrainHeartbeat, BrainHeartbeatConfig


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_mock_planner(**overrides):
    """
    Build a lightweight mock that satisfies BrainHeartbeat's expectations
    for ``planner`` (ProductionPlanner) and ``planner.planner``
    (HierarchicalPlanner).
    """
    hier = MagicMock(name="HierarchicalPlanner")

    # Defaults: subsystems disabled so tick paths stay simple
    hier.enable_neuromodulation = False
    hier.neuromodulation = None
    hier.enable_temporal_memory = False
    hier.temporal_memory = None
    hier.enable_dream_mode = False
    hier.dream_mode = None
    hier.enable_memory = False
    hier.memory = None
    hier.enable_meta_learning = False
    hier.meta_learner = None

    # Layer 3 decision targets (used in dream cycle)
    hier.layer3 = MagicMock()
    hier.layer3.intervention_types = ["suggest", "retry", "terminate", "wait"]

    prod = MagicMock(name="ProductionPlanner")
    prod.planner = hier
    prod.total_predictions = 0
    prod.total_feedback = 0
    # _yaml_config = None so HomeostaticRegulator uses default config
    prod._yaml_config = None
    prod.cognitive_loop = None

    # Apply caller overrides
    for k, v in overrides.items():
        setattr(prod, k, v)

    return prod


def _make_heartbeat(planner=None, config=None, homeostatic=True, **kwargs):
    """
    Create a BrainHeartbeat, optionally disabling the real homeostatic
    regulator (set homeostatic=False to force _homeostatic = None).
    Extra kwargs are forwarded as callbacks (on_tick, on_dream, on_error).
    """
    if planner is None:
        planner = _make_mock_planner()
    hb = BrainHeartbeat(planner, config=config, **kwargs)
    if not homeostatic:
        hb._homeostatic = None
    return hb


@pytest.fixture
def mock_planner():
    """Fresh mock planner with all subsystems disabled."""
    return _make_mock_planner()


@pytest.fixture
def default_config():
    """Default heartbeat configuration."""
    return BrainHeartbeatConfig()


@pytest.fixture
def fast_config():
    """Fast heartbeat config (short intervals for testing)."""
    return BrainHeartbeatConfig(
        interval_seconds=0.05,
        dream_idle_threshold_seconds=0.2,
    )


@pytest.fixture
def heartbeat(mock_planner):
    """
    BrainHeartbeat instance with homeostatic regulator disabled
    for simple isolated tests.
    """
    return _make_heartbeat(mock_planner, homeostatic=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBrainHeartbeatConfig:
    """Tests for BrainHeartbeatConfig defaults and overrides."""

    def test_default_values(self):
        cfg = BrainHeartbeatConfig()
        assert cfg.interval_seconds == 30.0
        assert cfg.enable_dream_mode is True
        assert cfg.dream_idle_threshold_seconds == 300.0
        assert cfg.enable_temporal_updates is True
        assert cfg.enable_neuromodulation_decay is True
        assert cfg.enable_meta_learning_checks is True
        assert cfg.enable_health_monitoring is True
        assert cfg.meta_learning_check_interval == 10

    def test_custom_values(self):
        cfg = BrainHeartbeatConfig(
            interval_seconds=5.0,
            enable_dream_mode=False,
            dream_idle_threshold_seconds=60.0,
            enable_temporal_updates=False,
            enable_neuromodulation_decay=False,
            enable_meta_learning_checks=False,
            enable_health_monitoring=False,
            meta_learning_check_interval=3,
        )
        assert cfg.interval_seconds == 5.0
        assert cfg.enable_dream_mode is False
        assert cfg.dream_idle_threshold_seconds == 60.0
        assert cfg.enable_temporal_updates is False
        assert cfg.enable_neuromodulation_decay is False
        assert cfg.enable_meta_learning_checks is False
        assert cfg.enable_health_monitoring is False
        assert cfg.meta_learning_check_interval == 3


class TestBrainHeartbeatInit:
    """Tests for heartbeat initialization."""

    def test_basic_initialization(self, heartbeat, mock_planner):
        assert heartbeat.planner is mock_planner
        assert heartbeat.running is False
        assert heartbeat.tick_count == 0
        assert heartbeat.idle_time_seconds == 0.0
        assert heartbeat.total_dreams == 0
        assert heartbeat.errors == []
        assert heartbeat.heartbeat_history == []

    def test_default_config_applied(self, heartbeat):
        assert heartbeat.config.interval_seconds == 30.0
        assert heartbeat.config.enable_dream_mode is True

    def test_custom_config_applied(self, mock_planner):
        cfg = BrainHeartbeatConfig(interval_seconds=10.0, enable_dream_mode=False)
        hb = _make_heartbeat(mock_planner, config=cfg, homeostatic=False)
        assert hb.config.interval_seconds == 10.0
        assert hb.config.enable_dream_mode is False

    def test_callbacks_stored(self, mock_planner):
        on_tick = MagicMock()
        on_dream = MagicMock()
        on_error = MagicMock()
        hb = _make_heartbeat(
            mock_planner, homeostatic=False,
            on_tick=on_tick, on_dream=on_dream, on_error=on_error,
        )
        assert hb.on_tick is on_tick
        assert hb.on_dream is on_dream
        assert hb.on_error is on_error

    def test_daemon_thread(self, heartbeat):
        assert heartbeat.daemon is True
        assert heartbeat.name == "BrainHeartbeat"

    def test_homeostatic_created_with_default_config(self, mock_planner):
        """When core.homeostatic_regulation is importable, _homeostatic is set."""
        hb = _make_heartbeat(mock_planner, homeostatic=True)
        assert hb._homeostatic is not None

    def test_homeostatic_none_when_forced_off(self, heartbeat):
        """When we explicitly disable homeostatic, _homeostatic is None."""
        assert heartbeat._homeostatic is None


class TestTickHandling:
    """Tests for individual tick execution."""

    def test_tick_increments_count(self, heartbeat):
        heartbeat.tick()
        assert heartbeat.tick_count == 1
        heartbeat.tick()
        assert heartbeat.tick_count == 2

    def test_tick_records_history(self, heartbeat):
        heartbeat.tick()
        assert len(heartbeat.heartbeat_history) == 1
        record = heartbeat.heartbeat_history[0]
        assert record['tick_number'] == 1
        assert 'timestamp' in record
        assert 'idle_time_seconds' in record
        assert 'actions_taken' in record
        assert 'elapsed_ms' in record

    def test_tick_on_tick_callback(self, mock_planner):
        cb = MagicMock()
        hb = _make_heartbeat(mock_planner, homeostatic=False, on_tick=cb)
        hb.tick()
        cb.assert_called_once()
        args = cb.call_args[0]
        assert args[0]['tick_number'] == 1

    def test_history_trimmed_at_100(self, heartbeat):
        for _ in range(110):
            heartbeat.tick()
        assert len(heartbeat.heartbeat_history) == 100
        # Oldest should be tick 11 (first 10 were popped)
        assert heartbeat.heartbeat_history[0]['tick_number'] == 11

    def test_health_check_action_recorded(self, heartbeat):
        """Health monitoring is enabled by default, so each tick records it."""
        heartbeat.tick()
        actions = heartbeat.heartbeat_history[0]['actions_taken']
        assert 'health_check' in actions


class TestIdleDetection:
    """Tests for idle time tracking."""

    def test_idle_time_increases(self, heartbeat):
        # Simulate last prediction was 10 seconds ago
        heartbeat.last_prediction_time = time.time() - 10
        heartbeat.tick()
        assert heartbeat.idle_time_seconds >= 9.0

    def test_mark_prediction_resets_idle(self, heartbeat):
        heartbeat.last_prediction_time = time.time() - 60
        heartbeat.tick()
        assert heartbeat.idle_time_seconds >= 59.0

        heartbeat.mark_prediction()
        assert heartbeat.idle_time_seconds == 0.0
        # After next tick, idle should be very small
        heartbeat.tick()
        assert heartbeat.idle_time_seconds < 2.0


class TestDreamMode:
    """Tests for dream mode trigger after idle threshold."""

    def _enable_dream(self, planner):
        """Configure mock planner so dream mode path succeeds."""
        hier = planner.planner
        hier.enable_dream_mode = True
        hier.enable_memory = True

        dream_mock = MagicMock()
        dream_mock.dream_cycle.return_value = ["dream1", "dream2", "dream3"]
        hier.dream_mode = dream_mock

        mem_mock = MagicMock()
        mem_mock.episodic.memories = [{"task": "test"}]
        hier.memory = mem_mock

    def test_dream_triggers_when_idle_exceeds_threshold(self, mock_planner):
        self._enable_dream(mock_planner)
        cfg = BrainHeartbeatConfig(dream_idle_threshold_seconds=1.0)
        hb = _make_heartbeat(mock_planner, config=cfg, homeostatic=False)

        # Force idle
        hb.last_prediction_time = time.time() - 5
        hb.tick()

        actions = hb.heartbeat_history[0]['actions_taken']
        assert 'dream_mode_consolidation' in actions
        assert hb.total_dreams == 3

    def test_dream_does_not_trigger_when_active(self, mock_planner):
        self._enable_dream(mock_planner)
        cfg = BrainHeartbeatConfig(dream_idle_threshold_seconds=300.0)
        hb = _make_heartbeat(mock_planner, config=cfg, homeostatic=False)

        # Recent prediction
        hb.mark_prediction()
        hb.tick()

        actions = hb.heartbeat_history[0]['actions_taken']
        assert 'dream_mode_consolidation' not in actions

    def test_dream_callback_invoked(self, mock_planner):
        self._enable_dream(mock_planner)
        dream_cb = MagicMock()
        cfg = BrainHeartbeatConfig(dream_idle_threshold_seconds=0.1)
        hb = _make_heartbeat(
            mock_planner, config=cfg, homeostatic=False, on_dream=dream_cb,
        )

        hb.last_prediction_time = time.time() - 5
        hb.tick()
        dream_cb.assert_called_once()
        payload = dream_cb.call_args[0][0]
        assert payload['num_dreams'] == 3
        assert payload['total_dreams'] == 3

    def test_dream_skipped_when_no_episodic_memories(self, mock_planner):
        hier = mock_planner.planner
        hier.enable_dream_mode = True
        hier.enable_memory = True
        hier.dream_mode = MagicMock()
        hier.memory = MagicMock()
        hier.memory.episodic.memories = []  # empty

        cfg = BrainHeartbeatConfig(dream_idle_threshold_seconds=0.1)
        hb = _make_heartbeat(mock_planner, config=cfg, homeostatic=False)

        hb.last_prediction_time = time.time() - 5
        hb.tick()
        actions = hb.heartbeat_history[0]['actions_taken']
        assert 'dream_mode_consolidation' not in actions

    def test_dream_disabled_in_config(self, mock_planner):
        self._enable_dream(mock_planner)
        cfg = BrainHeartbeatConfig(enable_dream_mode=False, dream_idle_threshold_seconds=0.1)
        hb = _make_heartbeat(mock_planner, config=cfg, homeostatic=False)

        hb.last_prediction_time = time.time() - 5
        hb.tick()
        actions = hb.heartbeat_history[0]['actions_taken']
        assert 'dream_mode_consolidation' not in actions


class TestHealthMonitoring:
    """Tests for _monitor_health."""

    def test_healthy_status(self, heartbeat):
        health = heartbeat._monitor_health()
        # Status may be 'healthy' or 'warning:high_cpu'/'warning:high_memory'
        # depending on system load during test execution. The key assertion is
        # that with 0 errors, the status should NOT be 'warning:high_errors'.
        assert health['status'] != 'warning:high_errors'
        assert health['status'] != 'error'
        assert 'memory_mb' in health
        assert 'cpu_percent' in health
        assert health['tick_count'] == 0
        assert health['error_count'] == 0

    def test_high_errors_warning(self, heartbeat):
        # Inject >10 errors
        heartbeat.errors = [{"error": f"e{i}"} for i in range(11)]
        health = heartbeat._monitor_health()
        assert health['status'] == 'warning:high_errors'

    def test_health_reports_planner_stats(self, mock_planner):
        mock_planner.total_predictions = 42
        mock_planner.total_feedback = 7
        hb = _make_heartbeat(mock_planner, homeostatic=False)
        health = hb._monitor_health()
        assert health['total_predictions'] == 42
        assert health['total_feedback'] == 7


class TestThreadSafety:
    """Tests for background thread behaviour."""

    def test_start_and_stop(self, mock_planner):
        cfg = BrainHeartbeatConfig(interval_seconds=0.05)
        hb = _make_heartbeat(mock_planner, config=cfg, homeostatic=False)

        hb.start()
        assert hb.is_alive()
        assert hb.running is True

        time.sleep(0.25)  # let a few ticks fire
        hb.stop()
        hb.join(timeout=2)

        assert hb.running is False
        assert hb.tick_count > 0

    def test_concurrent_mark_prediction(self, mock_planner):
        """mark_prediction called from another thread should not crash."""
        cfg = BrainHeartbeatConfig(interval_seconds=0.05)
        hb = _make_heartbeat(mock_planner, config=cfg, homeostatic=False)

        hb.start()
        errors = []

        def mark_many():
            try:
                for _ in range(50):
                    hb.mark_prediction()
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        t = threading.Thread(target=mark_many)
        t.start()
        t.join(timeout=3)
        hb.stop()
        hb.join(timeout=2)

        assert errors == [], f"Concurrent mark_prediction errors: {errors}"


class TestHomeostaticForcedDream:
    """Tests for homeostatic regulation triggering dream mode."""

    def test_homeostatic_forced_dream(self, mock_planner):
        """When homeostatic says should_trigger_dream, dream fires."""
        # Enable dream mode on the planner side
        hier = mock_planner.planner
        hier.enable_dream_mode = True
        hier.enable_memory = True
        dream_mock = MagicMock()
        dream_mock.dream_cycle.return_value = ["d1"]
        hier.dream_mode = dream_mock
        mem_mock = MagicMock()
        mem_mock.episodic.memories = [{"task": "x"}]
        hier.memory = mem_mock

        # Disable the idle-based dream so only homeostatic fires
        cfg = BrainHeartbeatConfig(
            enable_dream_mode=False,  # idle dream disabled
            dream_idle_threshold_seconds=9999,
        )

        hb = _make_heartbeat(mock_planner, config=cfg, homeostatic=False)

        # Build a mock homeostatic regulator and inject it
        homeo = MagicMock()
        homeo.should_trigger_dream.return_value = True
        hb._homeostatic = homeo
        hb.last_prediction_time = time.time() - 120  # >60 so is_idle=True

        hb.tick()

        actions = hb.heartbeat_history[0]['actions_taken']
        assert 'homeostatic_forced_dream' in actions
        assert 'homeostatic_tick' in actions
        homeo.on_dream_mode.assert_called_once()

    def test_homeostatic_no_forced_dream_when_already_dreamed(self, mock_planner):
        """If idle dream already happened in same tick, homeostatic dream is skipped."""
        hier = mock_planner.planner
        hier.enable_dream_mode = True
        hier.enable_memory = True
        dream_mock = MagicMock()
        dream_mock.dream_cycle.return_value = ["d1"]
        hier.dream_mode = dream_mock
        mem_mock = MagicMock()
        mem_mock.episodic.memories = [{"task": "x"}]
        hier.memory = mem_mock

        cfg = BrainHeartbeatConfig(dream_idle_threshold_seconds=0.1)
        hb = _make_heartbeat(mock_planner, config=cfg, homeostatic=False)

        homeo = MagicMock()
        homeo.should_trigger_dream.return_value = True
        hb._homeostatic = homeo
        hb.last_prediction_time = time.time() - 5

        hb.tick()

        actions = hb.heartbeat_history[0]['actions_taken']
        # Idle dream should have fired
        assert 'dream_mode_consolidation' in actions
        # Homeostatic forced dream should NOT double-fire
        assert 'homeostatic_forced_dream' not in actions


class TestStateReporting:
    """Tests for get_state."""

    def test_get_state_returns_expected_keys(self, heartbeat):
        state = heartbeat.get_state()
        expected_keys = [
            'timestamp', 'uptime_seconds', 'tick_count',
            'idle_time_seconds', 'state',
            'neuromodulation', 'neuromodulation_effects',
            'meta_learning', 'dream_state', 'temporal_memory',
            'homeostatic', 'emotional',
            'performance', 'health', 'config',
            'recent_heartbeats', 'recent_errors',
        ]
        for key in expected_keys:
            assert key in state, f"Missing key: {key}"

    def test_state_reflects_tick_count(self, heartbeat):
        heartbeat.tick()
        heartbeat.tick()
        state = heartbeat.get_state()
        assert state['tick_count'] == 2
        assert state['uptime_seconds'] == 2 * heartbeat.config.interval_seconds

    def test_state_idle_vs_active(self, heartbeat):
        heartbeat.mark_prediction()
        heartbeat.tick()
        state = heartbeat.get_state()
        assert state['state'] == 'active'

        heartbeat.last_prediction_time = time.time() - 120
        heartbeat.tick()
        state = heartbeat.get_state()
        assert state['state'] == 'idle'

    def test_state_config_section(self, heartbeat):
        state = heartbeat.get_state()
        assert state['config']['interval_seconds'] == heartbeat.config.interval_seconds
        assert state['config']['enable_dream_mode'] == heartbeat.config.enable_dream_mode
        assert state['config']['dream_idle_threshold_seconds'] == heartbeat.config.dream_idle_threshold_seconds

    def test_state_recent_heartbeats_limited(self, heartbeat):
        for _ in range(20):
            heartbeat.tick()
        state = heartbeat.get_state()
        assert len(state['recent_heartbeats']) == 10  # last 10

    def test_state_recent_errors_limited(self, heartbeat):
        for i in range(8):
            heartbeat._handle_error(RuntimeError(f"err{i}"), context="test")
        state = heartbeat.get_state()
        assert len(state['recent_errors']) == 5  # last 5

    def test_state_subsystems_none_when_disabled(self, heartbeat):
        state = heartbeat.get_state()
        assert state['neuromodulation'] is None
        assert state['neuromodulation_effects'] is None
        assert state['meta_learning'] is None
        assert state['dream_state'] is None
        assert state['temporal_memory'] is None
        assert state['homeostatic'] is None
        assert state['emotional'] is None


class TestErrorHandling:
    """Tests for error handling during tick and subsystem failures."""

    def test_handle_error_records(self, heartbeat):
        heartbeat._handle_error(ValueError("boom"), context="test_ctx")
        assert len(heartbeat.errors) == 1
        err = heartbeat.errors[0]
        assert err['context'] == 'test_ctx'
        assert 'boom' in err['error']
        assert 'timestamp' in err

    def test_error_list_trimmed_at_50(self, heartbeat):
        for i in range(55):
            heartbeat._handle_error(RuntimeError(f"e{i}"))
        assert len(heartbeat.errors) == 50

    def test_on_error_callback(self, mock_planner):
        err_cb = MagicMock()
        hb = _make_heartbeat(mock_planner, homeostatic=False, on_error=err_cb)
        hb._handle_error(RuntimeError("x"), context="cb_test")
        err_cb.assert_called_once()
        payload = err_cb.call_args[0][0]
        assert payload['context'] == 'cb_test'

    def test_tick_survives_neuromod_exception(self, mock_planner):
        """If neuromodulation decay raises, tick still completes."""
        hier = mock_planner.planner
        hier.enable_neuromodulation = True
        hier.neuromodulation = MagicMock()
        hier.neuromodulation.apply_decay.side_effect = RuntimeError("neuro fail")

        cfg = BrainHeartbeatConfig(enable_neuromodulation_decay=True)
        hb = _make_heartbeat(mock_planner, config=cfg, homeostatic=False)

        # Should not raise
        hb.tick()
        # Error recorded
        assert len(hb.errors) >= 1
        assert 'neuro fail' in hb.errors[0]['error']
        # Tick still counted
        assert hb.tick_count == 1

    def test_tick_survives_dream_mode_exception(self, mock_planner):
        """If dream mode raises, tick continues."""
        hier = mock_planner.planner
        hier.enable_dream_mode = True
        hier.enable_memory = True
        hier.dream_mode = MagicMock()
        hier.dream_mode.dream_cycle.side_effect = RuntimeError("dream crash")
        hier.memory = MagicMock()
        hier.memory.episodic.memories = [{"t": 1}]

        cfg = BrainHeartbeatConfig(dream_idle_threshold_seconds=0.1)
        hb = _make_heartbeat(mock_planner, config=cfg, homeostatic=False)
        hb.last_prediction_time = time.time() - 5

        hb.tick()
        assert hb.tick_count == 1
        assert any('dream crash' in e['error'] for e in hb.errors)

    def test_tick_survives_health_monitoring_exception(self, mock_planner):
        """If health monitoring raises, the outer try/except catches it."""
        # Make total_predictions a property that raises
        type(mock_planner).total_predictions = PropertyMock(
            side_effect=RuntimeError("stat fail")
        )

        hb = _make_heartbeat(mock_planner, homeostatic=False)

        # Tick should not propagate exception
        hb.tick()
        # The outer _handle_error catches, so errors list may have the entry
        # and tick_count may or may not be incremented depending on where it failed
        # Key assertion: no unhandled exception
        assert True


class TestNeuromodulationDecay:
    """Tests for _apply_neuromodulation_decay path."""

    def test_decay_applied_when_enabled(self, mock_planner):
        hier = mock_planner.planner
        hier.enable_neuromodulation = True
        neuro = MagicMock()
        hier.neuromodulation = neuro

        hb = _make_heartbeat(mock_planner, homeostatic=False)

        result = hb._apply_neuromodulation_decay()
        assert result is True
        neuro.apply_decay.assert_called_once()

    def test_decay_skipped_when_disabled(self, mock_planner):
        hier = mock_planner.planner
        hier.enable_neuromodulation = False
        hier.neuromodulation = None

        hb = _make_heartbeat(mock_planner, homeostatic=False)

        result = hb._apply_neuromodulation_decay()
        assert result is False


class TestMetaLearningChecks:
    """Tests for meta-learning check interval."""

    def test_meta_learning_fires_at_interval(self, mock_planner):
        hier = mock_planner.planner
        hier.enable_meta_learning = True
        ml = MagicMock()
        ml.get_statistics.return_value = {'total_adaptations': 5}
        ml.performance.get_success_rate.return_value = 0.8
        hier.meta_learner = ml

        cfg = BrainHeartbeatConfig(meta_learning_check_interval=3)
        hb = _make_heartbeat(mock_planner, config=cfg, homeostatic=False)

        # tick_count starts at 0. The check fires when tick_count % interval == 0.
        # Before tick_count is incremented, it is 0 for the first tick -> 0%3==0 -> fires
        hb.tick()
        assert 'meta_learning_check' in hb.heartbeat_history[0]['actions_taken']

        # tick_count is now 1 -> 1%3 != 0 -> does not fire
        hb.tick()
        assert 'meta_learning_check' not in hb.heartbeat_history[1]['actions_taken']

        # tick_count 2 -> 2%3 != 0
        hb.tick()
        assert 'meta_learning_check' not in hb.heartbeat_history[2]['actions_taken']

        # tick_count 3 -> 3%3 == 0 -> fires
        hb.tick()
        assert 'meta_learning_check' in hb.heartbeat_history[3]['actions_taken']


class TestGracefulShutdown:
    """Tests for stop() and thread teardown."""

    def test_stop_sets_running_false(self, heartbeat):
        heartbeat.running = True
        heartbeat.stop()
        assert heartbeat.running is False

    def test_thread_joins_after_stop(self, mock_planner):
        cfg = BrainHeartbeatConfig(interval_seconds=0.05)
        hb = _make_heartbeat(mock_planner, config=cfg, homeostatic=False)

        hb.start()
        time.sleep(0.15)
        hb.stop()
        hb.join(timeout=3)
        assert not hb.is_alive(), "Thread should have terminated"

    def test_multiple_stops_safe(self, heartbeat):
        """Calling stop() multiple times should not raise."""
        heartbeat.stop()
        heartbeat.stop()
        assert heartbeat.running is False


class TestTemporalMemoryUpdate:
    """Tests for _update_temporal_memory path."""

    def test_temporal_update_when_enabled(self, mock_planner):
        hier = mock_planner.planner
        hier.enable_temporal_memory = True
        tm = MagicMock()
        tm.get_statistics.return_value = {'total_events': 10, 'sequences_learned': 2}
        hier.temporal_memory = tm

        hb = _make_heartbeat(mock_planner, homeostatic=False)

        result = hb._update_temporal_memory()
        assert result is True
        tm.get_statistics.assert_called_once()

    def test_temporal_update_skipped_when_disabled(self, heartbeat):
        result = heartbeat._update_temporal_memory()
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
