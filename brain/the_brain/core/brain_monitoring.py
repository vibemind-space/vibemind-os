"""
Brain Monitoring: Unified Metrics, Audit Trail, and Observability for Tahlamus

Covers Phase 4 items:
- P4.60: Structured Logging (log_with_context, LoggingMixin)
- P4.61: Metrics Collection & Export (BrainMetrics, /metrics endpoint)
- P4.62: Prediction Audit Trail (PredictionAuditLog)
- P4.63: Cognitive Loop Tracing (CognitiveLoopTracer)
- P4.64: Error Rate Tracking (ErrorRateTracker)
- P4.65: Brain Heatmap data (ActivityHeatmap)
"""

import time
import json
import threading
import logging
from collections import deque, defaultdict
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path

from core.brain_logger import get_logger


# =============================================================================
# P4.60: STRUCTURED LOGGING MIXIN
# =============================================================================

class LoggingMixin:
    """
    Mixin that adds structured logging to any class.

    Usage:
        class MySystem(LoggingMixin):
            def __init__(self):
                self._init_logger('my_system')
                self.log_info("System initialized", component="core")
    """
    _logger: Optional[logging.Logger] = None

    def _init_logger(self, name: str) -> None:
        """Initialize logger for this component."""
        self._logger = get_logger(name)

    def log_debug(self, msg: str, **ctx) -> None:
        if self._logger:
            self._logger.debug(msg, extra={'extra_data': ctx} if ctx else {})

    def log_info(self, msg: str, **ctx) -> None:
        if self._logger:
            self._logger.info(msg, extra={'extra_data': ctx} if ctx else {})

    def log_warning(self, msg: str, **ctx) -> None:
        if self._logger:
            self._logger.warning(msg, extra={'extra_data': ctx} if ctx else {})

    def log_error(self, msg: str, **ctx) -> None:
        if self._logger:
            self._logger.error(msg, extra={'extra_data': ctx} if ctx else {})


# =============================================================================
# P4.61: METRICS COLLECTION (Prometheus-compatible)
# =============================================================================

class MetricType:
    COUNTER = 'counter'
    GAUGE = 'gauge'
    HISTOGRAM = 'histogram'


@dataclass
class MetricValue:
    """A single metric with type, value, help text, and labels."""
    name: str
    metric_type: str
    value: float
    help_text: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = 0.0


class BrainMetrics:
    """
    Centralized metrics collection with Prometheus text exposition format.
    Thread-safe. Singleton.

    Usage:
        metrics = BrainMetrics.instance()
        metrics.increment('brain_predictions_total')
        metrics.set_gauge('brain_gate_entropy', 2.4)
        metrics.observe_histogram('brain_prediction_latency_ms', 42.5)
        print(metrics.to_prometheus())
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._metrics_lock = threading.Lock()
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._help: Dict[str, str] = {}
        self._histogram_max = 1000  # Keep last N observations
        self._start_time = time.time()

        # Register default brain metrics
        self._register_defaults()
        self._initialized = True

    def _register_defaults(self):
        """Register default brain metrics with help text."""
        defaults = {
            'brain_predictions_total': 'Total number of predictions made',
            'brain_prediction_latency_ms': 'Prediction latency in milliseconds',
            'brain_gate_entropy': 'Shannon entropy of brain gate distribution',
            'brain_confidence': 'Current prediction confidence',
            'brain_loop_iterations': 'Cognitive loop iterations per prediction',
            'brain_memory_cache_hits': 'Memory cache hits',
            'brain_memory_cache_misses': 'Memory cache misses',
            'brain_subsystem_errors_total': 'Total subsystem errors',
            'brain_active_subsystems': 'Number of active subsystems',
            'brain_uptime_seconds': 'Brain service uptime in seconds',
            'brain_batch_requests_total': 'Total batch prediction requests',
            'brain_feedback_total': 'Total feedback events received',
            'brain_circuit_breaker_trips_total': 'Circuit breaker trip events',
            'brain_emotional_valence': 'Current emotional valence (-1 to 1)',
            'brain_emotional_arousal': 'Current emotional arousal (0 to 1)',
            'brain_dopamine_level': 'Current dopamine neuromodulator level',
            'brain_norepinephrine_level': 'Current norepinephrine level',
            'brain_serotonin_level': 'Current serotonin level',
            'brain_energy_level': 'Homeostatic energy level',
            'brain_fatigue_level': 'Homeostatic fatigue level',
            # Bridge health monitoring (Phase 4)
            'brain_bridge_health_healthy': 'Healthy fields per bridge',
            'brain_bridge_health_stuck': 'Stuck fields per bridge',
            'brain_bridge_health_saturated': 'Saturated fields per bridge',
            'brain_bridge_health_error': 'Error fields per bridge',
            'brain_bridge_health_total_issues': 'Total unhealthy fields across all bridges',
            'brain_bridge_health_recovery_events': 'Auto-recovery events triggered',
        }
        self._help.update(defaults)

    @classmethod
    def instance(cls) -> 'BrainMetrics':
        return cls()

    def increment(self, name: str, value: float = 1.0, **labels) -> None:
        """Increment a counter metric."""
        key = self._make_key(name, labels)
        with self._metrics_lock:
            self._counters[key] += value

    def set_gauge(self, name: str, value: float, **labels) -> None:
        """Set a gauge metric."""
        key = self._make_key(name, labels)
        with self._metrics_lock:
            self._gauges[key] = value

    def observe_histogram(self, name: str, value: float, **labels) -> None:
        """Observe a value for a histogram metric."""
        key = self._make_key(name, labels)
        with self._metrics_lock:
            bucket = self._histograms[key]
            bucket.append(value)
            if len(bucket) > self._histogram_max:
                # Keep last N values
                self._histograms[key] = bucket[-self._histogram_max:]

    def get_counter(self, name: str, **labels) -> float:
        """Get current counter value."""
        key = self._make_key(name, labels)
        with self._metrics_lock:
            return self._counters.get(key, 0.0)

    def get_gauge(self, name: str, **labels) -> float:
        """Get current gauge value."""
        key = self._make_key(name, labels)
        with self._metrics_lock:
            return self._gauges.get(key, 0.0)

    def get_histogram_summary(self, name: str, **labels) -> Dict:
        """Get histogram stats (count, sum, avg, p50, p95, p99)."""
        key = self._make_key(name, labels)
        with self._metrics_lock:
            values = self._histograms.get(key, [])
            if not values:
                return {'count': 0, 'sum': 0.0, 'avg': 0.0, 'p50': 0.0, 'p95': 0.0, 'p99': 0.0}
            sorted_vals = sorted(values)
            n = len(sorted_vals)
            return {
                'count': n,
                'sum': sum(sorted_vals),
                'avg': sum(sorted_vals) / n,
                'p50': sorted_vals[int(n * 0.5)],
                'p95': sorted_vals[min(int(n * 0.95), n - 1)],
                'p99': sorted_vals[min(int(n * 0.99), n - 1)],
            }

    def to_prometheus(self) -> str:
        """
        Export all metrics in Prometheus text exposition format.
        See: https://prometheus.io/docs/instrumenting/exposition_formats/
        """
        lines = []
        now_ms = int(time.time() * 1000)

        with self._metrics_lock:
            # Counters
            for key, value in sorted(self._counters.items()):
                name, labels = self._parse_key(key)
                help_text = self._help.get(name, '')
                if help_text:
                    lines.append(f'# HELP {name} {help_text}')
                lines.append(f'# TYPE {name} counter')
                label_str = self._format_labels(labels)
                lines.append(f'{name}{label_str} {value} {now_ms}')

            # Gauges
            for key, value in sorted(self._gauges.items()):
                name, labels = self._parse_key(key)
                help_text = self._help.get(name, '')
                if help_text:
                    lines.append(f'# HELP {name} {help_text}')
                lines.append(f'# TYPE {name} gauge')
                label_str = self._format_labels(labels)
                lines.append(f'{name}{label_str} {value} {now_ms}')

            # Histograms (emit sum, count, and quantile pseudo-metrics)
            for key, values in sorted(self._histograms.items()):
                name, labels = self._parse_key(key)
                if not values:
                    continue
                help_text = self._help.get(name, '')
                if help_text:
                    lines.append(f'# HELP {name} {help_text}')
                lines.append(f'# TYPE {name} histogram')
                label_str = self._format_labels(labels)
                sorted_vals = sorted(values)
                n = len(sorted_vals)
                total = sum(sorted_vals)
                lines.append(f'{name}_count{label_str} {n} {now_ms}')
                lines.append(f'{name}_sum{label_str} {total:.4f} {now_ms}')
                # Quantile buckets
                for q in [0.5, 0.9, 0.95, 0.99]:
                    idx = min(int(n * q), n - 1)
                    lines.append(f'{name}{{quantile="{q}"{label_str.lstrip("{").rstrip("}") if label_str else ""}}} {sorted_vals[idx]:.4f} {now_ms}')

            # Always emit uptime
            uptime = time.time() - self._start_time
            lines.append(f'# HELP brain_uptime_seconds Brain service uptime in seconds')
            lines.append(f'# TYPE brain_uptime_seconds gauge')
            lines.append(f'brain_uptime_seconds {uptime:.1f} {now_ms}')

        return '\n'.join(lines) + '\n'

    def to_dict(self) -> Dict:
        """Export all metrics as a dict (for JSON API)."""
        with self._metrics_lock:
            result = {
                'counters': dict(self._counters),
                'gauges': dict(self._gauges),
                'histograms': {},
                'uptime_seconds': time.time() - self._start_time,
            }
            for key, values in self._histograms.items():
                if values:
                    sorted_vals = sorted(values)
                    n = len(sorted_vals)
                    result['histograms'][key] = {
                        'count': n,
                        'sum': sum(sorted_vals),
                        'avg': sum(sorted_vals) / n,
                        'p50': sorted_vals[int(n * 0.5)],
                        'p95': sorted_vals[min(int(n * 0.95), n - 1)],
                        'p99': sorted_vals[min(int(n * 0.99), n - 1)],
                        'min': sorted_vals[0],
                        'max': sorted_vals[-1],
                    }
        return result

    def reset(self) -> None:
        """Reset all metrics (for testing)."""
        with self._metrics_lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._start_time = time.time()

    @staticmethod
    def _make_key(name: str, labels: Dict[str, str]) -> str:
        if not labels:
            return name
        label_parts = ','.join(f'{k}={v}' for k, v in sorted(labels.items()))
        return f'{name}{{{label_parts}}}'

    @staticmethod
    def _parse_key(key: str) -> Tuple[str, Dict[str, str]]:
        if '{' not in key:
            return key, {}
        name = key[:key.index('{')]
        label_str = key[key.index('{') + 1:key.rindex('}')]
        labels = {}
        for part in label_str.split(','):
            if '=' in part:
                k, v = part.split('=', 1)
                labels[k] = v
        return name, labels

    @staticmethod
    def _format_labels(labels: Dict[str, str]) -> str:
        if not labels:
            return ''
        parts = ','.join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return '{' + parts + '}'


# =============================================================================
# P4.62: PREDICTION AUDIT TRAIL
# =============================================================================

@dataclass
class AuditEntry:
    """A single prediction audit record."""
    timestamp: str
    task: str
    task_type: str
    pipeline_mode: str  # 'cognitive_loop' or 'legacy'
    confidence: float
    success_probability: float
    brain_gates: List[float]
    dominant_modalities: List[str]
    latency_ms: float
    loop_iterations: int = 0
    ctm_domain_hint: Optional[str] = None
    emotional_valence: float = 0.0
    emotional_arousal: float = 0.0
    gating_temperature: float = 1.0
    memory_bias_active: bool = False
    reflection_loopback: bool = False
    subsystem_errors: List[str] = field(default_factory=list)


class PredictionAuditLog:
    """
    Persistent audit trail for all predictions.
    Stores entries in memory (capped deque) and optionally to JSON-lines file.

    Usage:
        audit = PredictionAuditLog(log_dir="data/logs")
        audit.record(entry)
        recent = audit.get_recent(10)
    """

    def __init__(self, log_dir: Optional[str] = None, max_memory: int = 500):
        self._entries: deque = deque(maxlen=max_memory)
        self._lock = threading.Lock()
        self._log_file = None
        self._logger = get_logger('audit')

        if log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            self._log_file = log_path / 'prediction_audit.jsonl'

    def record(self, entry: AuditEntry) -> None:
        """Record a prediction audit entry."""
        with self._lock:
            self._entries.append(entry)

        # Write to file if configured
        if self._log_file:
            try:
                with open(self._log_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(asdict(entry)) + '\n')
            except Exception as e:
                if self._logger:
                    self._logger.warning(f"Failed to write audit entry: {e}")

        self._logger.info(
            f"AUDIT: {entry.task_type} conf={entry.confidence:.2f} "
            f"latency={entry.latency_ms:.1f}ms mode={entry.pipeline_mode}"
        )

    def record_from_prediction(self, task: str, prediction: Dict, latency_ms: float,
                                loop_context: Any = None) -> None:
        """Convenience: build AuditEntry from a prediction result dict + optional LoopContext."""
        gates = prediction.get('brain_gates', [])
        if hasattr(gates, 'tolist'):
            gates = gates.tolist()

        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            task=task[:200],  # Truncate long tasks
            task_type=prediction.get('task_type', 'unknown'),
            pipeline_mode=prediction.get('latency', {}).get('pipeline_mode', 'unknown'),
            confidence=prediction.get('confidence', 0.0),
            success_probability=prediction.get('success_probability', 0.0),
            brain_gates=gates,
            dominant_modalities=prediction.get('dominant_modalities', []),
            latency_ms=latency_ms,
        )

        if loop_context is not None:
            entry.loop_iterations = getattr(loop_context, 'loop_iterations', 0)
            entry.ctm_domain_hint = getattr(loop_context, 'ctm_domain_hint', None)
            entry.emotional_valence = getattr(loop_context, 'emotional_valence', 0.0)
            entry.emotional_arousal = getattr(loop_context, 'emotional_arousal', 0.0)
            entry.gating_temperature = getattr(loop_context, 'gating_temperature', 1.0)
            entry.memory_bias_active = getattr(loop_context, 'memory_bias', None) is not None
            entry.reflection_loopback = getattr(loop_context, 'should_reconsider', False)

        self.record(entry)

    def get_recent(self, n: int = 20) -> List[Dict]:
        """Get N most recent audit entries."""
        with self._lock:
            entries = list(self._entries)
        return [asdict(e) for e in entries[-n:]]

    def get_stats(self) -> Dict:
        """Get aggregate statistics from audit trail."""
        with self._lock:
            entries = list(self._entries)

        if not entries:
            return {'total': 0, 'avg_latency_ms': 0, 'avg_confidence': 0}

        latencies = [e.latency_ms for e in entries]
        confidences = [e.confidence for e in entries]
        loop_modes = defaultdict(int)
        task_types = defaultdict(int)

        for e in entries:
            loop_modes[e.pipeline_mode] += 1
            task_types[e.task_type] += 1

        return {
            'total': len(entries),
            'avg_latency_ms': sum(latencies) / len(latencies),
            'p95_latency_ms': sorted(latencies)[min(int(len(latencies) * 0.95), len(latencies) - 1)],
            'max_latency_ms': max(latencies),
            'avg_confidence': sum(confidences) / len(confidences),
            'min_confidence': min(confidences),
            'pipeline_modes': dict(loop_modes),
            'task_types': dict(task_types),
            'loopback_count': sum(1 for e in entries if e.reflection_loopback),
            'memory_bias_count': sum(1 for e in entries if e.memory_bias_active),
        }

    def to_dict(self) -> Dict:
        return {
            'recent': self.get_recent(20),
            'stats': self.get_stats(),
        }


# =============================================================================
# P4.63: COGNITIVE LOOP TRACING
# =============================================================================

@dataclass
class PhaseTrace:
    """Trace record for a single phase execution."""
    phase: str
    start_time: float
    end_time: float
    duration_ms: float
    input_summary: Dict[str, Any] = field(default_factory=dict)
    output_summary: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


@dataclass
class LoopTrace:
    """Complete trace for one cognitive loop execution."""
    task: str
    timestamp: str
    iteration: int
    phases: List[PhaseTrace] = field(default_factory=list)
    total_ms: float = 0.0
    looped_back: bool = False


class CognitiveLoopTracer:
    """
    Records detailed traces of each cognitive loop execution.
    Each phase's input/output state is summarized for debugging.

    Usage:
        tracer = CognitiveLoopTracer()
        tracer.start_trace("What is 2+2?")
        tracer.trace_phase('perceive', start, end, input_summary={...}, output_summary={...})
        tracer.end_trace(looped_back=False)
        recent = tracer.get_recent(5)
    """

    def __init__(self, max_traces: int = 100):
        self._traces: deque = deque(maxlen=max_traces)
        self._current: Optional[LoopTrace] = None
        self._lock = threading.Lock()
        self._logger = get_logger('loop_tracer')

    def start_trace(self, task: str, iteration: int = 1) -> None:
        """Begin tracing a new cognitive loop execution."""
        self._current = LoopTrace(
            task=task[:200],
            timestamp=datetime.now().isoformat(),
            iteration=iteration,
        )

    def trace_phase(self, phase: str, start_time: float, end_time: float,
                    input_summary: Optional[Dict] = None,
                    output_summary: Optional[Dict] = None,
                    warnings: Optional[List[str]] = None) -> None:
        """Record a phase execution trace."""
        if self._current is None:
            return

        duration_ms = (end_time - start_time) * 1000
        trace = PhaseTrace(
            phase=phase,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            input_summary=input_summary or {},
            output_summary=output_summary or {},
            warnings=warnings or [],
        )
        self._current.phases.append(trace)

        self._logger.debug(
            f"Phase {phase}: {duration_ms:.1f}ms",
            extra={'extra_data': {
                'phase': phase,
                'duration_ms': duration_ms,
                'output': output_summary,
            }}
        )

    def end_trace(self, looped_back: bool = False) -> Optional[LoopTrace]:
        """End the current trace and store it."""
        if self._current is None:
            return None

        self._current.looped_back = looped_back
        total = sum(p.duration_ms for p in self._current.phases)
        self._current.total_ms = total

        with self._lock:
            self._traces.append(self._current)

        result = self._current
        self._current = None

        self._logger.info(
            f"Loop trace: {len(result.phases)} phases, "
            f"{total:.1f}ms total, loopback={looped_back}"
        )
        return result

    def get_recent(self, n: int = 10) -> List[Dict]:
        """Get N most recent loop traces."""
        with self._lock:
            traces = list(self._traces)
        result = []
        for t in traces[-n:]:
            result.append({
                'task': t.task,
                'timestamp': t.timestamp,
                'iteration': t.iteration,
                'total_ms': t.total_ms,
                'looped_back': t.looped_back,
                'phases': [
                    {
                        'phase': p.phase,
                        'duration_ms': p.duration_ms,
                        'input': p.input_summary,
                        'output': p.output_summary,
                        'warnings': p.warnings,
                    }
                    for p in t.phases
                ],
            })
        return result

    def get_phase_stats(self) -> Dict[str, Dict]:
        """Get per-phase timing statistics across all traces."""
        with self._lock:
            traces = list(self._traces)

        phase_times: Dict[str, List[float]] = defaultdict(list)
        for t in traces:
            for p in t.phases:
                phase_times[p.phase].append(p.duration_ms)

        stats = {}
        for phase, times in phase_times.items():
            sorted_t = sorted(times)
            n = len(sorted_t)
            stats[phase] = {
                'count': n,
                'avg_ms': sum(sorted_t) / n,
                'min_ms': sorted_t[0],
                'max_ms': sorted_t[-1],
                'p95_ms': sorted_t[min(int(n * 0.95), n - 1)],
            }
        return stats

    def to_dict(self) -> Dict:
        return {
            'recent_traces': self.get_recent(10),
            'phase_stats': self.get_phase_stats(),
            'total_traces': len(self._traces),
        }


# =============================================================================
# P4.64: ERROR RATE TRACKING
# =============================================================================

@dataclass
class ErrorEvent:
    """A single error event."""
    timestamp: str
    subsystem: str
    error_type: str
    message: str
    severity: str = 'error'  # 'warning', 'error', 'critical'


class ErrorRateTracker:
    """
    Tracks error rates per subsystem with sliding window.

    Usage:
        tracker = ErrorRateTracker(window_seconds=300)
        tracker.record_error('memory', ValueError("bad data"))
        rates = tracker.get_error_rates()
    """

    def __init__(self, window_seconds: float = 300.0, max_events: int = 1000):
        self._events: deque = deque(maxlen=max_events)
        self._window = window_seconds
        self._lock = threading.Lock()
        self._total_by_subsystem: Dict[str, int] = defaultdict(int)
        self._logger = get_logger('error_tracker')

    def record_error(self, subsystem: str, error: Exception,
                     severity: str = 'error') -> None:
        """Record an error event."""
        event = ErrorEvent(
            timestamp=datetime.now().isoformat(),
            subsystem=subsystem,
            error_type=type(error).__name__,
            message=str(error)[:200],
            severity=severity,
        )
        with self._lock:
            self._events.append(event)
            self._total_by_subsystem[subsystem] += 1

        self._logger.warning(
            f"Error in {subsystem}: {type(error).__name__}: {str(error)[:100]}",
            extra={'extra_data': {
                'subsystem': subsystem,
                'error_type': type(error).__name__,
                'severity': severity,
            }}
        )

    def record_warning(self, subsystem: str, message: str) -> None:
        """Record a warning (non-exception)."""
        event = ErrorEvent(
            timestamp=datetime.now().isoformat(),
            subsystem=subsystem,
            error_type='Warning',
            message=message[:200],
            severity='warning',
        )
        with self._lock:
            self._events.append(event)

    def get_error_rates(self) -> Dict[str, Dict]:
        """
        Get error rates per subsystem within the sliding window.
        Returns: {subsystem: {count, rate_per_min, total_all_time}}
        """
        cutoff = time.time() - self._window
        with self._lock:
            events = list(self._events)
            totals = dict(self._total_by_subsystem)

        # Count recent events by subsystem
        recent: Dict[str, int] = defaultdict(int)
        for e in events:
            try:
                ts = datetime.fromisoformat(e.timestamp).timestamp()
                if ts >= cutoff:
                    recent[e.subsystem] += 1
            except (ValueError, OSError):
                recent[e.subsystem] += 1  # Include if can't parse

        window_min = self._window / 60.0
        rates = {}
        all_subsystems = set(list(recent.keys()) + list(totals.keys()))
        for sub in all_subsystems:
            count = recent.get(sub, 0)
            rates[sub] = {
                'recent_count': count,
                'rate_per_min': count / window_min if window_min > 0 else 0,
                'total_all_time': totals.get(sub, 0),
            }
        return rates

    def get_recent_errors(self, n: int = 20, subsystem: Optional[str] = None) -> List[Dict]:
        """Get N most recent errors, optionally filtered by subsystem."""
        with self._lock:
            events = list(self._events)

        if subsystem:
            events = [e for e in events if e.subsystem == subsystem]

        return [asdict(e) for e in events[-n:]]

    def to_dict(self) -> Dict:
        return {
            'error_rates': self.get_error_rates(),
            'recent_errors': self.get_recent_errors(20),
            'window_seconds': self._window,
        }


# =============================================================================
# P4.65: BRAIN ACTIVITY HEATMAP
# =============================================================================

class ActivityHeatmap:
    """
    Tracks gate/modality activations over time for heatmap visualization.
    Stores a rolling window of activation snapshots.

    Usage:
        heatmap = ActivityHeatmap()
        heatmap.record_activation(gates=[0.15, 0.10, ...], modalities=['vision', 'audio', ...])
        data = heatmap.get_heatmap_data(last_n=50)
    """

    def __init__(self, max_snapshots: int = 200):
        self._snapshots: deque = deque(maxlen=max_snapshots)
        self._lock = threading.Lock()
        self._modality_names: List[str] = [
            'vision', 'audio', 'touch', 'taste', 'vestibular', 'threat',
            'tool_trace', 'temporal_pattern', 'error_signal', 'success_signal'
        ]

    def record_activation(self, gates: Any, task_type: str = 'unknown',
                          extra: Optional[Dict] = None) -> None:
        """
        Record a gate activation snapshot.

        Args:
            gates: Gate values (list or ndarray of 10 floats)
            task_type: The task type classification
            extra: Additional metadata (ctm_hint, temperature, etc.)
        """
        if hasattr(gates, 'tolist'):
            gates = gates.tolist()

        if not isinstance(gates, (list, tuple)) or len(gates) == 0:
            return

        snapshot = {
            'timestamp': datetime.now().isoformat(),
            'epoch_time': time.time(),
            'gates': gates,
            'task_type': task_type,
            'dominant': self._modality_names[int(max(range(len(gates)), key=lambda i: gates[i]))]
                if len(gates) <= len(self._modality_names) else 'unknown',
        }
        if extra:
            snapshot.update(extra)

        with self._lock:
            self._snapshots.append(snapshot)

    def get_heatmap_data(self, last_n: int = 50) -> Dict:
        """
        Get heatmap-ready data: a 2D matrix of [time_steps x modalities].

        Returns:
            {
                'modalities': ['vision', 'audio', ...],
                'timestamps': [...],
                'matrix': [[gate values per timestep], ...],
                'task_types': [...],
                'dominant_over_time': [...]
            }
        """
        with self._lock:
            snaps = list(self._snapshots)

        snaps = snaps[-last_n:]

        if not snaps:
            return {
                'modalities': self._modality_names,
                'timestamps': [],
                'matrix': [],
                'task_types': [],
                'dominant_over_time': [],
            }

        return {
            'modalities': self._modality_names[:len(snaps[0]['gates'])] if snaps else self._modality_names,
            'timestamps': [s['timestamp'] for s in snaps],
            'matrix': [s['gates'] for s in snaps],
            'task_types': [s.get('task_type', 'unknown') for s in snaps],
            'dominant_over_time': [s.get('dominant', 'unknown') for s in snaps],
        }

    def get_modality_averages(self) -> Dict[str, float]:
        """Get average activation per modality across all snapshots."""
        with self._lock:
            snaps = list(self._snapshots)

        if not snaps:
            return {}

        n_modalities = len(snaps[0]['gates'])
        sums = [0.0] * n_modalities
        for s in snaps:
            for i, v in enumerate(s['gates']):
                if i < n_modalities:
                    sums[i] += v

        n = len(snaps)
        names = self._modality_names[:n_modalities]
        return {names[i]: sums[i] / n for i in range(min(n_modalities, len(names)))}

    def to_dict(self) -> Dict:
        return {
            'heatmap': self.get_heatmap_data(50),
            'modality_averages': self.get_modality_averages(),
            'total_snapshots': len(self._snapshots),
        }
