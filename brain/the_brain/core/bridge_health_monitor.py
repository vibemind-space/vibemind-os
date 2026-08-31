"""
Bridge Health Monitor: Anomaly detection and auto-recovery for all 10 bridges.

Tracks rolling statistics (mean, variance, min, max) for each numeric bridge state
field over the last N ticks. Detects:
  - **Stuck**: variance < epsilon for a rolling window (field not changing)
  - **Saturated**: value at clamp boundary for >K consecutive ticks
  - **Error**: NaN or Inf detected in any field

Provides auto-recovery by perturbing stuck fields with small noise.
Reports health status via check_health() and publishes Prometheus gauges.
"""

import math
import random
import logging
from collections import deque, defaultdict
from dataclasses import fields as dc_fields, is_dataclass
from typing import Dict, Any, Optional, List, Tuple

from core.brain_logger import get_logger

logger = get_logger('bridge_health_monitor')

# ─── Field metadata: expected ranges for numeric fields ───────────────────────
# Format: {bridge_name: {field_name: (low, high)}}
# Fields not listed here (bool, str, ndarray) are skipped.

BRIDGE_FIELD_RANGES: Dict[str, Dict[str, Tuple[float, float]]] = {
    'neuromod': {
        'dopamine': (0.0, 1.0),
        'norepinephrine': (0.0, 1.0),
        'serotonin': (0.0, 1.0),
        'acetylcholine': (0.0, 1.0),
        'anti_reward': (0.0, 1.0),
        'ne_gain': (0.2, 2.0),
        'explore_ratio': (0.0, 1.0),
    },
    'cortex': {
        'pfc_value': (0.0, 1.0),
        'pfc_surprise': (0.0, 1.0),
        'conflict': (0.0, 1.0),
        'control_signal': (0.0, 1.0),
        'error_likelihood': (0.0, 1.0),
        'subjective_value': (0.0, 1.0),
        'decision_confidence': (0.0, 1.0),
        'choice_difficulty': (0.0, 1.0),
    },
    'limbic': {
        'valence': (-1.0, 1.0),
        'arousal': (0.0, 1.0),
        'threat_level': (0.0, 1.0),
        'go_drive': (0.0, 1.0),
        'nogo_drive': (0.0, 1.0),
        'net_value': (-1.0, 1.0),
        'effort_cost': (0.0, 1.0),
        'salience': (0.0, 1.0),
        'body_budget': (0.0, 1.0),
        'urgency': (0.0, 1.0),
        'approach_drive': (0.0, 1.0),
        'stress': (0.0, 1.0),
    },
    'sleep_wake': {
        'arousal': (0.0, 1.0),
        'sensory_gain': (0.0, 1.0),
        'histamine': (0.0, 1.0),
        'wakefulness_drive': (0.0, 1.0),
        'melatonin': (0.0, 1.0),
        'sleep_pressure': (0.0, 1.0),
        'cholinergic_tone': (0.0, 1.0),
        'rem_probability': (0.0, 1.0),
    },
    'motor': {
        'prediction_error': (0.0, 5.0),
        'model_confidence': (0.0, 1.0),
        'motor_da': (0.0, 1.0),
        'go_nogo_balance': (-1.0, 1.0),
        'inhibition_level': (0.0, 1.0),
        'action_tendency': (0.0, 1.0),
        'error_correction': (-1.0, 1.0),
        'peak_salience': (0.0, 1.0),
        'movement_confidence': (0.0, 1.0),
    },
    'defense': {
        'defense_intensity': (0.0, 1.0),
        'autonomic_activation': (0.0, 1.0),
        'alarm_level': (0.0, 1.0),
        'alarm_urgency': (0.0, 1.0),
        'anxiety_level': (0.0, 1.0),
        'vigilance': (0.0, 1.0),
    },
    'memory': {
        'theta_power': (0.0, 1.0),
        'theta_frequency': (4.0, 8.0),
        'coupling_strength': (0.0, 1.0),
        'consolidation_strength': (0.0, 1.0),
        'relay_strength': (0.0, 1.0),
        'teaching_signal': (-1.0, 1.0),
        'error_magnitude': (0.0, 5.0),
        'memory_gateway': (0.0, 1.0),
    },
    'integration': {
        'binding_strength': (0.0, 1.0),
        'dmn_activation': (0.0, 1.0),
        'orienting_saliency': (0.0, 1.0),
        'cortical_error': (0.0, 5.0),
        'cortical_output': (0.0, 1.0),
        'bilateral_coherence': (0.0, 1.0),
        'transfer_efficiency': (0.0, 1.0),
    },
    'visceral': {
        'visceral_level': (0.0, 1.0),
        'afferent_strength': (0.0, 1.0),
        'liking': (0.0, 1.0),
        'wanting': (0.0, 1.0),
        'approach_strength': (0.0, 1.0),
    },
    'social': {
        'identity_score': (0.0, 1.0),
        'word_score': (0.0, 1.0),
        'agency_score': (0.0, 1.0),
        'social_inference': (0.0, 1.0),
        'social_salience': (0.0, 1.0),
        'familiarity': (0.0, 1.0),
    },
}

# All 10 bridge names in canonical order
BRIDGE_NAMES = list(BRIDGE_FIELD_RANGES.keys())


class FieldStatus:
    """Health status constants for a single field."""
    HEALTHY = 'healthy'
    STUCK = 'stuck'
    SATURATED = 'saturated'
    ERROR = 'error'


class BridgeHealthMonitor:
    """
    Monitors all 10 bridge states for anomalies.

    Parameters
    ----------
    window_size : int
        Rolling window size for stats computation (default 50 ticks).
    stuck_epsilon : float
        Variance threshold below which a field is considered "stuck" (default 1e-8).
    saturation_ticks : int
        Number of consecutive ticks at boundary before "saturated" (default 20).
    saturation_margin : float
        How close to boundary counts as "at boundary" (default 0.01).
    auto_recover : bool
        Whether to automatically perturb stuck fields (default False).
    noise_scale : float
        Scale of noise perturbation for auto-recovery (default 0.05).
    """

    def __init__(
        self,
        window_size: int = 50,
        stuck_epsilon: float = 1e-8,
        saturation_ticks: int = 20,
        saturation_margin: float = 0.01,
        auto_recover: bool = False,
        noise_scale: float = 0.05,
    ):
        self.window_size = window_size
        self.stuck_epsilon = stuck_epsilon
        self.saturation_ticks = saturation_ticks
        self.saturation_margin = saturation_margin
        self.auto_recover = auto_recover
        self.noise_scale = noise_scale

        # Rolling history: {bridge_name: {field_name: deque([values])}}
        self._history: Dict[str, Dict[str, deque]] = {}
        for bridge_name, field_ranges in BRIDGE_FIELD_RANGES.items():
            self._history[bridge_name] = {}
            for field_name in field_ranges:
                self._history[bridge_name][field_name] = deque(maxlen=window_size)

        # Consecutive-at-boundary counter: {bridge_name: {field_name: int}}
        self._boundary_streak: Dict[str, Dict[str, int]] = {}
        for bridge_name, field_ranges in BRIDGE_FIELD_RANGES.items():
            self._boundary_streak[bridge_name] = {f: 0 for f in field_ranges}

        # Tick counter
        self._tick_count = 0

        # Last health report (cached)
        self._last_health: Dict[str, Dict[str, str]] = {}

        # Recovery events log
        self._recovery_log: List[Dict[str, Any]] = []

    def record_tick(self, bridge_states: Dict[str, Any]) -> None:
        """
        Record one tick of bridge states.

        Parameters
        ----------
        bridge_states : dict
            Keys are bridge names (e.g. 'neuromod', 'cortex'), values are
            either dataclass instances or dicts with field values.
        """
        self._tick_count += 1

        for bridge_name, expected_fields in BRIDGE_FIELD_RANGES.items():
            state = bridge_states.get(bridge_name)
            if state is None:
                continue

            for field_name, (low, high) in expected_fields.items():
                value = self._extract_field(state, field_name)
                if value is None:
                    continue

                # Record to history
                self._history[bridge_name][field_name].append(value)

                # Update boundary streak
                if self._is_at_boundary(value, low, high):
                    self._boundary_streak[bridge_name][field_name] += 1
                else:
                    self._boundary_streak[bridge_name][field_name] = 0

    def check_health(self) -> Dict[str, Dict[str, str]]:
        """
        Check health of all bridge fields.

        Returns
        -------
        dict
            {bridge_name: {field_name: status}} where status is one of
            'healthy', 'stuck', 'saturated', 'error'.
        """
        report: Dict[str, Dict[str, str]] = {}

        for bridge_name, expected_fields in BRIDGE_FIELD_RANGES.items():
            report[bridge_name] = {}
            for field_name in expected_fields:
                history = self._history[bridge_name][field_name]
                status = self._check_field(bridge_name, field_name, history)
                report[bridge_name][field_name] = status

        self._last_health = report
        return report

    def get_stats(self, bridge_name: str, field_name: str) -> Dict[str, float]:
        """Get rolling stats for a specific field."""
        history = self._history.get(bridge_name, {}).get(field_name)
        if history is None or len(history) == 0:
            return {'mean': 0.0, 'variance': 0.0, 'min': 0.0, 'max': 0.0, 'count': 0}

        values = list(history)
        n = len(values)
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n if n > 1 else 0.0
        return {
            'mean': mean,
            'variance': variance,
            'min': min(values),
            'max': max(values),
            'count': n,
        }

    def attempt_recovery(
        self, bridge_name: str, field_name: str, bridge_state: Any
    ) -> bool:
        """
        Attempt to recover a stuck/saturated field by perturbing it.

        Modifies the bridge state dataclass in-place. Returns True if
        perturbation was applied.
        """
        if bridge_name not in BRIDGE_FIELD_RANGES:
            return False
        if field_name not in BRIDGE_FIELD_RANGES[bridge_name]:
            return False

        low, high = BRIDGE_FIELD_RANGES[bridge_name][field_name]
        current = self._extract_field(bridge_state, field_name)
        if current is None:
            return False

        # Compute noise relative to field range
        field_range = high - low
        noise = random.gauss(0, self.noise_scale * field_range)
        new_value = max(low, min(high, current + noise))

        # Apply perturbation
        if is_dataclass(bridge_state) and not isinstance(bridge_state, type):
            try:
                setattr(bridge_state, field_name, new_value)
            except (AttributeError, TypeError):
                return False
        elif isinstance(bridge_state, dict):
            bridge_state[field_name] = new_value
        else:
            return False

        self._recovery_log.append({
            'tick': self._tick_count,
            'bridge': bridge_name,
            'field': field_name,
            'old_value': current,
            'new_value': new_value,
            'noise': noise,
        })
        logger.info(
            f"Auto-recovery: {bridge_name}.{field_name} "
            f"{current:.4f} -> {new_value:.4f} (noise={noise:.4f})"
        )
        return True

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the monitor's state."""
        health = self.check_health()
        counts = {FieldStatus.HEALTHY: 0, FieldStatus.STUCK: 0,
                  FieldStatus.SATURATED: 0, FieldStatus.ERROR: 0}
        for bridge_fields in health.values():
            for status in bridge_fields.values():
                counts[status] = counts.get(status, 0) + 1
        return {
            'tick_count': self._tick_count,
            'total_fields': sum(counts.values()),
            'status_counts': counts,
            'recovery_events': len(self._recovery_log),
            'per_bridge': {
                bridge: {
                    'healthy': sum(1 for s in fields.values() if s == FieldStatus.HEALTHY),
                    'issues': sum(1 for s in fields.values() if s != FieldStatus.HEALTHY),
                }
                for bridge, fields in health.items()
            },
        }

    def publish_metrics(self, metrics) -> None:
        """
        Publish bridge health gauges to BrainMetrics.

        Parameters
        ----------
        metrics : BrainMetrics
            The metrics singleton to publish to.
        """
        health = self._last_health or self.check_health()

        for bridge_name, fields in health.items():
            healthy = sum(1 for s in fields.values() if s == FieldStatus.HEALTHY)
            stuck = sum(1 for s in fields.values() if s == FieldStatus.STUCK)
            saturated = sum(1 for s in fields.values() if s == FieldStatus.SATURATED)
            errors = sum(1 for s in fields.values() if s == FieldStatus.ERROR)

            metrics.set_gauge(
                f'brain_bridge_health_healthy', healthy, bridge=bridge_name)
            metrics.set_gauge(
                f'brain_bridge_health_stuck', stuck, bridge=bridge_name)
            metrics.set_gauge(
                f'brain_bridge_health_saturated', saturated, bridge=bridge_name)
            metrics.set_gauge(
                f'brain_bridge_health_error', errors, bridge=bridge_name)

        # Publish composite modulation factor health if available
        metrics.set_gauge('brain_bridge_health_total_issues',
                          sum(1 for b in health.values()
                              for s in b.values() if s != FieldStatus.HEALTHY))
        metrics.set_gauge('brain_bridge_health_recovery_events',
                          len(self._recovery_log))

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def recovery_log(self) -> List[Dict[str, Any]]:
        return list(self._recovery_log)

    # ── Private helpers ──────────────────────────────────────────────────

    def _extract_field(self, state: Any, field_name: str) -> Optional[float]:
        """Extract a numeric field value from a state object (dataclass or dict)."""
        if is_dataclass(state) and not isinstance(state, type):
            value = getattr(state, field_name, None)
        elif isinstance(state, dict):
            value = state.get(field_name)
        else:
            return None

        if value is None:
            return None
        if isinstance(value, bool):
            return None  # Skip boolean fields
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _is_at_boundary(self, value: float, low: float, high: float) -> bool:
        """Check if value is at or beyond the field boundary."""
        if math.isnan(value) or math.isinf(value):
            return False  # These are errors, not saturation
        return (value <= low + self.saturation_margin or
                value >= high - self.saturation_margin)

    def _check_field(
        self, bridge_name: str, field_name: str, history: deque
    ) -> str:
        """Determine health status for a single field."""
        if len(history) == 0:
            return FieldStatus.HEALTHY  # No data yet

        latest = history[-1]

        # Check for NaN / Inf
        if math.isnan(latest) or math.isinf(latest):
            return FieldStatus.ERROR

        # Check any value in window is NaN/Inf
        for v in history:
            if math.isnan(v) or math.isinf(v):
                return FieldStatus.ERROR

        # Check saturation (consecutive ticks at boundary)
        streak = self._boundary_streak[bridge_name][field_name]
        if streak >= self.saturation_ticks:
            return FieldStatus.SATURATED

        # Check stuck (variance below epsilon) — need enough data
        if len(history) >= min(10, self.window_size):
            values = list(history)
            n = len(values)
            mean = sum(values) / n
            variance = sum((v - mean) ** 2 for v in values) / n
            if variance < self.stuck_epsilon:
                return FieldStatus.STUCK

        return FieldStatus.HEALTHY
