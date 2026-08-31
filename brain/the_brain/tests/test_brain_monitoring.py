"""
Tests for Brain Monitoring (P4.60-65)

Covers:
- P4.60: LoggingMixin
- P4.61: BrainMetrics (Prometheus format)
- P4.62: PredictionAuditLog
- P4.63: CognitiveLoopTracer
- P4.64: ErrorRateTracker
- P4.65: ActivityHeatmap
"""

import sys
import os
import time
import threading
import json
import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.brain_monitoring import (
    LoggingMixin,
    BrainMetrics,
    AuditEntry,
    PredictionAuditLog,
    PhaseTrace,
    LoopTrace,
    CognitiveLoopTracer,
    ErrorEvent,
    ErrorRateTracker,
    ActivityHeatmap,
)


# ============================================================================
# P4.60: LOGGING MIXIN TESTS
# ============================================================================

class TestLoggingMixin:
    """Tests for the LoggingMixin (P4.60)."""

    def test_mixin_init_logger(self):
        """Mixin creates a named logger."""
        class MySystem(LoggingMixin):
            def __init__(self):
                self._init_logger('test_system')

        system = MySystem()
        assert system._logger is not None
        assert 'test_system' in system._logger.name

    def test_mixin_log_methods_exist(self):
        """All log level methods exist."""
        class MySystem(LoggingMixin):
            def __init__(self):
                self._init_logger('test_mixin')

        system = MySystem()
        for method in ['log_debug', 'log_info', 'log_warning', 'log_error']:
            assert hasattr(system, method)
            assert callable(getattr(system, method))

    def test_mixin_log_without_init(self):
        """Logging without init doesn't crash (no-op)."""
        mixin = LoggingMixin()
        mixin.log_info("Should not crash")
        mixin.log_error("Also fine")

    def test_mixin_log_with_context(self):
        """Logging with keyword context doesn't crash."""
        class MySystem(LoggingMixin):
            def __init__(self):
                self._init_logger('ctx_test')

        system = MySystem()
        system.log_info("Processing", task="test", latency=42.5)


# ============================================================================
# P4.61: BRAIN METRICS TESTS
# ============================================================================

class TestBrainMetrics:
    """Tests for the BrainMetrics system (P4.61)."""

    @pytest.fixture
    def metrics(self):
        """Fresh metrics instance (reset singleton)."""
        m = BrainMetrics.instance()
        m.reset()
        return m

    def test_singleton(self):
        """BrainMetrics is singleton."""
        m1 = BrainMetrics.instance()
        m2 = BrainMetrics.instance()
        assert m1 is m2

    def test_counter_increment(self, metrics):
        """Counter increments correctly."""
        metrics.increment('test_counter')
        assert metrics.get_counter('test_counter') == 1.0
        metrics.increment('test_counter', 5.0)
        assert metrics.get_counter('test_counter') == 6.0

    def test_counter_with_labels(self, metrics):
        """Counters with different labels are separate."""
        metrics.increment('errors', subsystem='memory')
        metrics.increment('errors', subsystem='memory')
        metrics.increment('errors', subsystem='attention')
        assert metrics.get_counter('errors', subsystem='memory') == 2.0
        assert metrics.get_counter('errors', subsystem='attention') == 1.0

    def test_gauge_set(self, metrics):
        """Gauge sets to exact value."""
        metrics.set_gauge('temperature', 0.8)
        assert metrics.get_gauge('temperature') == 0.8
        metrics.set_gauge('temperature', 1.2)
        assert metrics.get_gauge('temperature') == 1.2

    def test_histogram_observe(self, metrics):
        """Histogram records observations."""
        for v in [10.0, 20.0, 30.0, 40.0, 50.0]:
            metrics.observe_histogram('latency', v)
        summary = metrics.get_histogram_summary('latency')
        assert summary['count'] == 5
        assert summary['sum'] == 150.0
        assert summary['avg'] == 30.0

    def test_histogram_percentiles(self, metrics):
        """Histogram computes percentiles."""
        for i in range(100):
            metrics.observe_histogram('latency', float(i + 1))
        summary = metrics.get_histogram_summary('latency')
        assert summary['p50'] == pytest.approx(51.0, abs=1)
        assert summary['p95'] >= 90.0
        assert summary['p99'] >= 95.0

    def test_prometheus_format(self, metrics):
        """Prometheus export has correct format."""
        metrics.increment('brain_predictions_total')
        metrics.set_gauge('brain_confidence', 0.85)
        metrics.observe_histogram('brain_prediction_latency_ms', 42.0)

        output = metrics.to_prometheus()
        assert '# HELP brain_predictions_total' in output
        assert '# TYPE brain_predictions_total counter' in output
        assert 'brain_predictions_total' in output
        assert '# TYPE brain_confidence gauge' in output
        assert '# TYPE brain_prediction_latency_ms histogram' in output
        assert 'brain_uptime_seconds' in output

    def test_prometheus_format_has_timestamps(self, metrics):
        """Prometheus output includes timestamps."""
        metrics.increment('test_ts')
        output = metrics.to_prometheus()
        # Should have numeric timestamp at end of metric lines
        lines = [l for l in output.strip().split('\n') if not l.startswith('#')]
        for line in lines:
            parts = line.split()
            if len(parts) >= 3:
                # Last part should be a timestamp
                assert parts[-1].isdigit(), f"Expected timestamp in: {line}"

    def test_to_dict(self, metrics):
        """Dict export contains all metric types."""
        metrics.increment('counter_x')
        metrics.set_gauge('gauge_y', 1.5)
        metrics.observe_histogram('hist_z', 10.0)

        d = metrics.to_dict()
        assert 'counters' in d
        assert 'gauges' in d
        assert 'histograms' in d
        assert 'uptime_seconds' in d
        assert d['counters']['counter_x'] == 1.0
        assert d['gauges']['gauge_y'] == 1.5

    def test_reset(self, metrics):
        """Reset clears all metrics."""
        metrics.increment('c1')
        metrics.set_gauge('g1', 1.0)
        metrics.observe_histogram('h1', 5.0)
        metrics.reset()
        assert metrics.get_counter('c1') == 0.0
        assert metrics.get_gauge('g1') == 0.0
        assert metrics.get_histogram_summary('h1')['count'] == 0

    def test_thread_safety(self, metrics):
        """Concurrent increments are safe."""
        def worker():
            for _ in range(100):
                metrics.increment('concurrent_counter')

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert metrics.get_counter('concurrent_counter') == 1000.0

    def test_histogram_bounded(self, metrics):
        """Histogram doesn't grow unbounded."""
        for i in range(2000):
            metrics.observe_histogram('bounded', float(i))
        summary = metrics.get_histogram_summary('bounded')
        assert summary['count'] <= 1000  # max is 1000


# ============================================================================
# P4.62: PREDICTION AUDIT LOG TESTS
# ============================================================================

class TestPredictionAuditLog:
    """Tests for the PredictionAuditLog (P4.62)."""

    @pytest.fixture
    def audit(self):
        return PredictionAuditLog(max_memory=50)

    def _make_entry(self, task="test task", confidence=0.8, latency=42.0):
        return AuditEntry(
            timestamp="2025-01-01T12:00:00",
            task=task,
            task_type="analysis",
            pipeline_mode="cognitive_loop",
            confidence=confidence,
            success_probability=0.75,
            brain_gates=[0.15, 0.10, 0.12, 0.08, 0.10, 0.15, 0.08, 0.07, 0.05, 0.10],
            dominant_modalities=['vision', 'threat'],
            latency_ms=latency,
        )

    def test_record_and_retrieve(self, audit):
        """Record entries and retrieve them."""
        entry = self._make_entry()
        audit.record(entry)
        recent = audit.get_recent(10)
        assert len(recent) == 1
        assert recent[0]['task'] == "test task"
        assert recent[0]['confidence'] == 0.8

    def test_record_from_prediction(self, audit):
        """Record from prediction dict."""
        prediction = {
            'brain_gates': np.array([0.15, 0.10, 0.12, 0.08, 0.10, 0.15, 0.08, 0.07, 0.05, 0.10]),
            'task_type': 'query',
            'confidence': 0.9,
            'success_probability': 0.85,
            'dominant_modalities': ['vision'],
            'latency': {'pipeline_mode': 'cognitive_loop'},
        }
        audit.record_from_prediction("What is 2+2?", prediction, 35.0)
        recent = audit.get_recent(5)
        assert len(recent) == 1
        assert recent[0]['task_type'] == 'query'
        assert recent[0]['latency_ms'] == 35.0

    def test_stats(self, audit):
        """Statistics computed correctly."""
        for i in range(10):
            entry = self._make_entry(
                confidence=0.5 + i * 0.05,
                latency=20.0 + i * 5,
            )
            audit.record(entry)

        stats = audit.get_stats()
        assert stats['total'] == 10
        assert stats['avg_latency_ms'] == pytest.approx(42.5, abs=0.1)
        assert stats['avg_confidence'] == pytest.approx(0.725, abs=0.01)

    def test_max_memory_bounded(self, audit):
        """Audit doesn't grow beyond max_memory."""
        for i in range(100):
            audit.record(self._make_entry(task=f"task_{i}"))
        recent = audit.get_recent(100)
        assert len(recent) == 50  # max_memory=50

    def test_to_dict(self, audit):
        """to_dict returns recent entries and stats."""
        audit.record(self._make_entry())
        d = audit.to_dict()
        assert 'recent' in d
        assert 'stats' in d

    def test_file_persistence(self, tmp_path):
        """Audit writes to JSON-lines file."""
        audit = PredictionAuditLog(log_dir=str(tmp_path), max_memory=50)
        entry = self._make_entry()
        audit.record(entry)

        audit_file = tmp_path / 'prediction_audit.jsonl'
        assert audit_file.exists()
        content = audit_file.read_text(encoding='utf-8').strip()
        parsed = json.loads(content)
        assert parsed['task'] == "test task"

    def test_task_truncation(self, audit):
        """Long tasks are truncated to 200 chars."""
        prediction = {
            'brain_gates': [0.1] * 10,
            'task_type': 'query',
            'confidence': 0.5,
            'success_probability': 0.5,
            'dominant_modalities': [],
            'latency': {'pipeline_mode': 'legacy'},
        }
        long_task = "x" * 500
        audit.record_from_prediction(long_task, prediction, 10.0)
        recent = audit.get_recent(1)
        assert len(recent[0]['task']) == 200


# ============================================================================
# P4.63: COGNITIVE LOOP TRACER TESTS
# ============================================================================

class TestCognitiveLoopTracer:
    """Tests for the CognitiveLoopTracer (P4.63)."""

    @pytest.fixture
    def tracer(self):
        return CognitiveLoopTracer(max_traces=50)

    def test_basic_trace(self, tracer):
        """Record a simple trace."""
        tracer.start_trace("What is 2+2?")
        start = time.time()
        time.sleep(0.001)
        end = time.time()
        tracer.trace_phase('perceive', start, end, output_summary={'gates': [0.1]*10})
        result = tracer.end_trace()

        assert result is not None
        assert result.task == "What is 2+2?"
        assert len(result.phases) == 1
        assert result.phases[0].phase == 'perceive'
        assert result.phases[0].duration_ms > 0

    def test_multi_phase_trace(self, tracer):
        """Record trace with all phases."""
        phases = ['perceive', 'remember', 'attend', 'modulate', 'reason', 'reflect', 'learn', 'consolidate']
        tracer.start_trace("Complex task")

        for phase in phases:
            start = time.time()
            tracer.trace_phase(phase, start, start + 0.001)

        result = tracer.end_trace()
        assert len(result.phases) == 8
        assert result.total_ms > 0

    def test_get_recent(self, tracer):
        """Retrieve recent traces."""
        for i in range(5):
            tracer.start_trace(f"task_{i}")
            tracer.trace_phase('perceive', time.time(), time.time() + 0.001)
            tracer.end_trace()

        recent = tracer.get_recent(3)
        assert len(recent) == 3
        assert recent[-1]['task'] == 'task_4'

    def test_loopback_tracking(self, tracer):
        """Loopback flag is tracked."""
        tracer.start_trace("uncertain task")
        tracer.trace_phase('perceive', time.time(), time.time() + 0.001)
        result = tracer.end_trace(looped_back=True)
        assert result.looped_back is True

        recent = tracer.get_recent(1)
        assert recent[0]['looped_back'] is True

    def test_phase_stats(self, tracer):
        """Phase statistics computed correctly."""
        for _ in range(10):
            tracer.start_trace("task")
            t = time.time()
            tracer.trace_phase('perceive', t, t + 0.010)
            tracer.trace_phase('reason', t, t + 0.020)
            tracer.end_trace()

        stats = tracer.get_phase_stats()
        assert 'perceive' in stats
        assert 'reason' in stats
        assert stats['perceive']['count'] == 10
        assert stats['reason']['avg_ms'] > stats['perceive']['avg_ms']

    def test_max_traces_bounded(self, tracer):
        """Traces don't exceed max_traces."""
        for i in range(100):
            tracer.start_trace(f"task_{i}")
            tracer.end_trace()

        recent = tracer.get_recent(100)
        assert len(recent) == 50  # max_traces=50

    def test_to_dict(self, tracer):
        """to_dict returns structured data."""
        tracer.start_trace("test")
        tracer.trace_phase('perceive', time.time(), time.time() + 0.001)
        tracer.end_trace()

        d = tracer.to_dict()
        assert 'recent_traces' in d
        assert 'phase_stats' in d
        assert 'total_traces' in d

    def test_trace_without_start(self, tracer):
        """Phase trace without start doesn't crash."""
        tracer.trace_phase('perceive', time.time(), time.time() + 0.001)
        result = tracer.end_trace()
        assert result is None

    def test_phase_warnings(self, tracer):
        """Phase warnings are recorded."""
        tracer.start_trace("warned task")
        tracer.trace_phase('modulate', time.time(), time.time() + 0.001,
                           warnings=['Low dopamine', 'High fatigue'])
        result = tracer.end_trace()
        assert result.phases[0].warnings == ['Low dopamine', 'High fatigue']


# ============================================================================
# P4.64: ERROR RATE TRACKER TESTS
# ============================================================================

class TestErrorRateTracker:
    """Tests for the ErrorRateTracker (P4.64)."""

    @pytest.fixture
    def tracker(self):
        return ErrorRateTracker(window_seconds=300.0, max_events=100)

    def test_record_error(self, tracker):
        """Record an error event."""
        tracker.record_error('memory', ValueError("bad data"))
        recent = tracker.get_recent_errors(10)
        assert len(recent) == 1
        assert recent[0]['subsystem'] == 'memory'
        assert recent[0]['error_type'] == 'ValueError'

    def test_record_warning(self, tracker):
        """Record a warning event."""
        tracker.record_warning('attention', 'Low gate entropy')
        recent = tracker.get_recent_errors(10)
        assert len(recent) == 1
        assert recent[0]['severity'] == 'warning'

    def test_error_rates(self, tracker):
        """Error rates computed per subsystem."""
        for i in range(5):
            tracker.record_error('memory', RuntimeError(f"err_{i}"))
        for i in range(3):
            tracker.record_error('attention', ValueError(f"err_{i}"))

        rates = tracker.get_error_rates()
        assert rates['memory']['recent_count'] == 5
        assert rates['attention']['recent_count'] == 3
        assert rates['memory']['total_all_time'] == 5

    def test_filter_by_subsystem(self, tracker):
        """Retrieve errors filtered by subsystem."""
        tracker.record_error('memory', ValueError("mem_err"))
        tracker.record_error('attention', TypeError("att_err"))
        tracker.record_error('memory', RuntimeError("mem_err2"))

        mem_errors = tracker.get_recent_errors(10, subsystem='memory')
        assert len(mem_errors) == 2
        assert all(e['subsystem'] == 'memory' for e in mem_errors)

    def test_max_events_bounded(self, tracker):
        """Events don't exceed max_events."""
        for i in range(200):
            tracker.record_error('test', RuntimeError(f"err_{i}"))
        recent = tracker.get_recent_errors(200)
        assert len(recent) <= 100

    def test_to_dict(self, tracker):
        """to_dict returns structured data."""
        tracker.record_error('memory', ValueError("test"))
        d = tracker.to_dict()
        assert 'error_rates' in d
        assert 'recent_errors' in d
        assert 'window_seconds' in d

    def test_thread_safety(self, tracker):
        """Concurrent error recording is safe."""
        def worker(name):
            for _ in range(50):
                tracker.record_error(name, RuntimeError("test"))

        threads = [threading.Thread(target=worker, args=(f"sub_{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        rates = tracker.get_error_rates()
        total = sum(r['total_all_time'] for r in rates.values())
        # Some may be lost due to bounded deque but totals should be exact
        assert total == 250

    def test_error_message_truncation(self, tracker):
        """Long error messages are truncated."""
        tracker.record_error('test', RuntimeError("x" * 500))
        recent = tracker.get_recent_errors(1)
        assert len(recent[0]['message']) <= 200


# ============================================================================
# P4.65: ACTIVITY HEATMAP TESTS
# ============================================================================

class TestActivityHeatmap:
    """Tests for the ActivityHeatmap (P4.65)."""

    @pytest.fixture
    def heatmap(self):
        return ActivityHeatmap(max_snapshots=100)

    def test_record_activation(self, heatmap):
        """Record gate activations."""
        gates = [0.15, 0.10, 0.12, 0.08, 0.10, 0.15, 0.08, 0.07, 0.05, 0.10]
        heatmap.record_activation(gates, task_type='analysis')

        data = heatmap.get_heatmap_data()
        assert len(data['matrix']) == 1
        assert data['matrix'][0] == gates
        assert data['task_types'] == ['analysis']

    def test_record_numpy_array(self, heatmap):
        """Record from numpy array."""
        gates = np.array([0.15, 0.10, 0.12, 0.08, 0.10, 0.15, 0.08, 0.07, 0.05, 0.10])
        heatmap.record_activation(gates)
        data = heatmap.get_heatmap_data()
        assert len(data['matrix']) == 1
        assert isinstance(data['matrix'][0], list)

    def test_dominant_modality(self, heatmap):
        """Dominant modality detected correctly."""
        # Vision highest (index 0)
        gates_vision = [0.50, 0.10, 0.10, 0.05, 0.05, 0.05, 0.05, 0.05, 0.02, 0.03]
        heatmap.record_activation(gates_vision)
        data = heatmap.get_heatmap_data()
        assert data['dominant_over_time'][0] == 'vision'

        # Threat highest (index 5)
        gates_threat = [0.05, 0.05, 0.05, 0.05, 0.05, 0.50, 0.05, 0.05, 0.05, 0.10]
        heatmap.record_activation(gates_threat)
        data = heatmap.get_heatmap_data()
        assert data['dominant_over_time'][-1] == 'threat'

    def test_heatmap_data_shape(self, heatmap):
        """Heatmap data has correct structure."""
        for i in range(10):
            gates = [float(j) / 10 for j in range(10)]
            heatmap.record_activation(gates, task_type=f'type_{i}')

        data = heatmap.get_heatmap_data(last_n=5)
        assert len(data['matrix']) == 5
        assert len(data['timestamps']) == 5
        assert len(data['task_types']) == 5
        assert 'modalities' in data

    def test_modality_averages(self, heatmap):
        """Modality averages computed correctly."""
        gates1 = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        gates2 = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        heatmap.record_activation(gates1)
        heatmap.record_activation(gates2)

        averages = heatmap.get_modality_averages()
        assert averages['vision'] == pytest.approx(0.5)
        assert averages['audio'] == pytest.approx(0.5)
        assert averages['touch'] == pytest.approx(0.0)

    def test_max_snapshots_bounded(self, heatmap):
        """Snapshots don't exceed max."""
        for i in range(200):
            heatmap.record_activation([0.1] * 10)

        data = heatmap.get_heatmap_data(last_n=200)
        assert len(data['matrix']) <= 100

    def test_empty_heatmap(self, heatmap):
        """Empty heatmap returns valid structure."""
        data = heatmap.get_heatmap_data()
        assert data['modalities'] == [
            'vision', 'audio', 'touch', 'taste', 'vestibular', 'threat',
            'tool_trace', 'temporal_pattern', 'error_signal', 'success_signal'
        ]
        assert data['matrix'] == []
        assert data['timestamps'] == []

    def test_invalid_gates_ignored(self, heatmap):
        """Empty or invalid gates are silently ignored."""
        heatmap.record_activation([])
        heatmap.record_activation(None)
        heatmap.record_activation("not a list")

        data = heatmap.get_heatmap_data()
        assert len(data['matrix']) == 0

    def test_extra_metadata(self, heatmap):
        """Extra metadata is included in snapshots."""
        heatmap.record_activation(
            [0.1] * 10,
            task_type='test',
            extra={'ctm_hint': 'temporal', 'temperature': 0.8}
        )
        data = heatmap.get_heatmap_data()
        assert len(data['matrix']) == 1

    def test_to_dict(self, heatmap):
        """to_dict returns valid dict."""
        heatmap.record_activation([0.1] * 10)
        d = heatmap.to_dict()
        assert 'heatmap' in d
        assert 'modality_averages' in d
        assert 'total_snapshots' in d


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestMonitoringIntegration:
    """Integration tests across monitoring components."""

    def test_metrics_and_audit_together(self):
        """Metrics and audit can work together."""
        metrics = BrainMetrics.instance()
        metrics.reset()
        audit = PredictionAuditLog(max_memory=10)

        # Simulate a prediction cycle
        metrics.increment('brain_predictions_total')
        metrics.observe_histogram('brain_prediction_latency_ms', 42.0)
        metrics.set_gauge('brain_confidence', 0.85)

        entry = AuditEntry(
            timestamp="2025-01-01T12:00:00",
            task="test",
            task_type="analysis",
            pipeline_mode="cognitive_loop",
            confidence=0.85,
            success_probability=0.8,
            brain_gates=[0.1] * 10,
            dominant_modalities=['vision'],
            latency_ms=42.0,
        )
        audit.record(entry)

        assert metrics.get_counter('brain_predictions_total') == 1.0
        assert audit.get_stats()['total'] == 1

    def test_tracer_and_heatmap_together(self):
        """Tracer and heatmap can record from the same prediction."""
        tracer = CognitiveLoopTracer(max_traces=10)
        heatmap = ActivityHeatmap(max_snapshots=10)

        tracer.start_trace("combined test")
        t = time.time()
        tracer.trace_phase('perceive', t, t + 0.005,
                           output_summary={'gates': [0.1]*10})
        tracer.trace_phase('reason', t + 0.005, t + 0.015,
                           output_summary={'confidence': 0.85})
        tracer.end_trace()

        heatmap.record_activation([0.15, 0.10, 0.12, 0.08, 0.10, 0.15, 0.08, 0.07, 0.05, 0.10])

        assert len(tracer.get_recent(5)) == 1
        assert len(heatmap.get_heatmap_data()['matrix']) == 1

    def test_error_tracker_and_metrics(self):
        """Error tracker feeds metrics."""
        metrics = BrainMetrics.instance()
        metrics.reset()
        tracker = ErrorRateTracker()

        tracker.record_error('memory', ValueError("test"))
        # In real code, you'd increment the metric when recording:
        metrics.increment('brain_subsystem_errors_total', subsystem='memory')

        assert metrics.get_counter('brain_subsystem_errors_total', subsystem='memory') == 1.0
        assert tracker.get_error_rates()['memory']['recent_count'] == 1
