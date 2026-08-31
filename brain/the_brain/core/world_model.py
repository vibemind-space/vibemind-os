"""
World Model System (V2 PHASE 5: P5.67-69)

P5.67: WorldModel
  - Internal model of system environment
  - Tracks: services, repos, APIs, baselines
  - Continuously updated from sensor data

P5.68: CausalWorldModel
  - Extends CausalDAG with observed causalities
  - Learned from experience, not just configured
  - Enables root-cause analysis for failure chains

P5.69: PredictiveWorldModel
  - Predicts future states from trends
  - Uses temporal patterns + causal model
  - E.g., "disk will be full in 2h", "merge conflicts expected"
"""

import time
import math
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger('brain.world_model')


# ─── P5.67: World Model ────────────────────────────────────────────────

class EntityStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


@dataclass
class WorldEntity:
    """A tracked entity in the world model (service, repo, API, etc.)."""
    name: str
    entity_type: str         # "service", "repo", "api", "resource", "sensor"
    status: EntityStatus = EntityStatus.UNKNOWN
    properties: Dict[str, Any] = field(default_factory=dict)
    last_updated: float = 0.0
    history: List[Dict] = field(default_factory=list)
    max_history: int = 100

    def update(self, status: EntityStatus, properties: Optional[Dict] = None) -> None:
        """Update entity state."""
        old_status = self.status
        self.status = status
        if properties:
            self.properties.update(properties)
        self.last_updated = time.time()

        # Record in history
        self.history.append({
            'timestamp': self.last_updated,
            'status': status.value,
            'old_status': old_status.value,
            'changed': old_status != status,
        })
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def get_uptime_ratio(self, window_hours: float = 24.0) -> float:
        """Calculate uptime ratio over a time window."""
        cutoff = time.time() - (window_hours * 3600)
        relevant = [h for h in self.history if h['timestamp'] >= cutoff]
        if not relevant:
            return 1.0 if self.status == EntityStatus.HEALTHY else 0.0
        healthy = sum(1 for h in relevant if h['status'] == 'healthy')
        return healthy / len(relevant)

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'entity_type': self.entity_type,
            'status': self.status.value,
            'properties': self.properties,
            'last_updated': self.last_updated,
            'uptime_24h': round(self.get_uptime_ratio(24.0), 3),
            'history_size': len(self.history),
        }


class WorldModel:
    """
    P5.67: Internal model of the system environment.

    Tracks services, repos, APIs, resources — what's running, what's normal.
    Baselines established from observation over time.
    """

    def __init__(self, baseline_window_hours: float = 168.0,  # 7 days
                 max_entities: int = 200):
        self.baseline_window_hours = baseline_window_hours
        self.max_entities = max_entities
        self._entities: Dict[str, WorldEntity] = {}
        self._baselines: Dict[str, Dict[str, float]] = {}  # entity -> metric -> baseline value
        self._anomalies: deque = deque(maxlen=100)
        self._total_updates = 0

    def update_entity(self, name: str, entity_type: str, status: EntityStatus,
                       properties: Optional[Dict] = None) -> None:
        """Update or create a world entity."""
        if name not in self._entities:
            if len(self._entities) >= self.max_entities:
                self._evict_oldest()
            self._entities[name] = WorldEntity(name=name, entity_type=entity_type)

        entity = self._entities[name]
        old_status = entity.status
        entity.update(status, properties)
        self._total_updates += 1

        # Check for anomaly (status change)
        if old_status != status and old_status != EntityStatus.UNKNOWN:
            self._anomalies.append({
                'entity': name,
                'from': old_status.value,
                'to': status.value,
                'timestamp': time.time(),
            })

    def get_entity(self, name: str) -> Optional[WorldEntity]:
        return self._entities.get(name)

    def get_entities_by_type(self, entity_type: str) -> List[WorldEntity]:
        return [e for e in self._entities.values() if e.entity_type == entity_type]

    def get_entities_by_status(self, status: EntityStatus) -> List[WorldEntity]:
        return [e for e in self._entities.values() if e.status == status]

    def update_baseline(self, entity_name: str, metric: str, value: float) -> None:
        """Update a baseline metric using exponential moving average."""
        if entity_name not in self._baselines:
            self._baselines[entity_name] = {}
        if metric not in self._baselines[entity_name]:
            self._baselines[entity_name][metric] = value
        else:
            alpha = 0.1  # Slow-moving baseline
            self._baselines[entity_name][metric] = (
                alpha * value + (1 - alpha) * self._baselines[entity_name][metric]
            )

    def check_anomaly(self, entity_name: str, metric: str, value: float,
                       threshold_factor: float = 2.0) -> Optional[Dict]:
        """Check if a value deviates significantly from baseline."""
        baselines = self._baselines.get(entity_name, {})
        baseline = baselines.get(metric)
        if baseline is None or baseline == 0:
            return None

        deviation = abs(value - baseline) / abs(baseline)
        if deviation >= threshold_factor:
            anomaly = {
                'entity': entity_name,
                'metric': metric,
                'value': round(value, 3),
                'baseline': round(baseline, 3),
                'deviation': round(deviation, 3),
                'timestamp': time.time(),
            }
            self._anomalies.append(anomaly)
            return anomaly
        return None

    def get_system_health_summary(self) -> Dict:
        """Get overall system health."""
        total = len(self._entities)
        by_status = defaultdict(int)
        for e in self._entities.values():
            by_status[e.status.value] += 1

        return {
            'total_entities': total,
            'by_status': dict(by_status),
            'healthy_ratio': round(by_status.get('healthy', 0) / max(total, 1), 3),
            'recent_anomalies': len([a for a in self._anomalies
                                      if a['timestamp'] > time.time() - 3600]),
        }

    def _evict_oldest(self) -> None:
        if self._entities:
            oldest = min(self._entities.values(), key=lambda e: e.last_updated)
            del self._entities[oldest.name]

    def get_state(self) -> Dict:
        return {
            'total_entities': len(self._entities),
            'total_updates': self._total_updates,
            'baselines': len(self._baselines),
            'recent_anomalies': list(self._anomalies)[-5:],
            'health_summary': self.get_system_health_summary(),
            'entity_types': list(set(e.entity_type for e in self._entities.values())),
        }

    @classmethod
    def from_yaml(cls, cfg: Dict) -> 'WorldModel':
        section = cfg.get('world_model', {})
        return cls(
            baseline_window_hours=section.get('baseline_window_hours', 168.0),
            max_entities=section.get('max_entities', 200),
        )


# ─── P5.68: Causal World Model ─────────────────────────────────────────

@dataclass
class CausalLink:
    """An observed causal relationship between entities/events."""
    cause: str
    effect: str
    strength: float = 0.5    # 0-1, how strong the causal link is
    observations: int = 0
    co_occurrences: int = 0  # Times cause and effect co-occurred
    cause_only: int = 0      # Times cause occurred without effect
    effect_only: int = 0     # Times effect occurred without cause
    avg_delay_ms: float = 0.0  # Average time between cause and effect
    last_observed: float = 0.0

    def observe(self, co_occurred: bool, delay_ms: float = 0.0) -> None:
        """Record an observation."""
        self.observations += 1
        if co_occurred:
            self.co_occurrences += 1
            alpha = 0.3
            self.avg_delay_ms = alpha * delay_ms + (1 - alpha) * self.avg_delay_ms
        else:
            self.cause_only += 1
        self.last_observed = time.time()
        self._update_strength()

    def _update_strength(self) -> None:
        """Update causal strength based on observations."""
        if self.observations == 0:
            return
        # P(effect|cause) estimated from observations
        self.strength = self.co_occurrences / max(self.observations, 1)

    def to_dict(self) -> Dict:
        return {
            'cause': self.cause,
            'effect': self.effect,
            'strength': round(self.strength, 3),
            'observations': self.observations,
            'co_occurrences': self.co_occurrences,
            'avg_delay_ms': round(self.avg_delay_ms, 1),
        }


class CausalWorldModel:
    """
    P5.68: Causal model of system relationships.

    Learns causal relationships from observed co-occurrences:
    "When A fails, B often fails within 5 minutes."
    Enables root-cause analysis.
    """

    def __init__(self, min_observations: int = 3, min_strength: float = 0.3,
                 max_links: int = 500):
        self.min_observations = min_observations
        self.min_strength = min_strength
        self.max_links = max_links
        self._links: Dict[str, CausalLink] = {}  # "cause->effect" -> CausalLink
        self._recent_events: deque = deque(maxlen=500)  # For co-occurrence detection
        self._co_occurrence_window_ms: float = 300000.0  # 5 minutes

    def observe_event(self, event: str, timestamp: Optional[float] = None) -> List[CausalLink]:
        """
        Observe an event and check for causal links with recent events.
        Returns newly updated causal links.
        """
        ts = timestamp or time.time()
        updated_links = []

        # Check recent events for potential causes
        for recent in self._recent_events:
            delay_ms = (ts - recent['timestamp']) * 1000
            if delay_ms > self._co_occurrence_window_ms:
                continue
            if recent['event'] == event:
                continue

            # Record co-occurrence: recent event may have caused this event
            key = f"{recent['event']}->{event}"
            if key not in self._links:
                self._links[key] = CausalLink(
                    cause=recent['event'], effect=event
                )
            self._links[key].observe(co_occurred=True, delay_ms=delay_ms)
            updated_links.append(self._links[key])

        self._recent_events.append({'event': event, 'timestamp': ts})

        # Cleanup old links if over capacity
        if len(self._links) > self.max_links:
            self._prune_weak_links()

        return updated_links

    def get_causes(self, effect: str, min_strength: Optional[float] = None) -> List[CausalLink]:
        """Find potential causes of an effect."""
        threshold = min_strength or self.min_strength
        causes = []
        for link in self._links.values():
            if (link.effect == effect and
                    link.strength >= threshold and
                    link.observations >= self.min_observations):
                causes.append(link)
        causes.sort(key=lambda l: l.strength, reverse=True)
        return causes

    def get_effects(self, cause: str, min_strength: Optional[float] = None) -> List[CausalLink]:
        """Find potential effects of a cause."""
        threshold = min_strength or self.min_strength
        effects = []
        for link in self._links.values():
            if (link.cause == cause and
                    link.strength >= threshold and
                    link.observations >= self.min_observations):
                effects.append(link)
        effects.sort(key=lambda l: l.strength, reverse=True)
        return effects

    def root_cause_analysis(self, symptom: str, max_depth: int = 3) -> List[List[str]]:
        """
        Trace back through causal chains to find root causes.
        Returns list of causal chains (most likely first).
        """
        chains: List[List[str]] = []
        self._trace_back(symptom, [symptom], max_depth, chains)
        # Sort by chain strength (product of link strengths)
        chains.sort(key=lambda c: self._chain_strength(c), reverse=True)
        return chains[:10]

    def _trace_back(self, effect: str, chain: List[str],
                    depth: int, results: List[List[str]]) -> None:
        if depth <= 0:
            if len(chain) > 1:
                results.append(list(chain))
            return

        causes = self.get_causes(effect)
        if not causes:
            if len(chain) > 1:
                results.append(list(chain))
            return

        explored_any = False
        for link in causes[:3]:  # Top 3 causes only
            if link.cause not in chain:  # Avoid cycles
                explored_any = True
                chain.append(link.cause)
                self._trace_back(link.cause, chain, depth - 1, results)
                chain.pop()
        # If all causes are already in chain (cycle), save current chain
        if not explored_any and len(chain) > 1:
            results.append(list(chain))

    def _chain_strength(self, chain: List[str]) -> float:
        """Calculate overall chain strength (product of link strengths)."""
        if len(chain) <= 1:
            return 0.0
        strength = 1.0
        for i in range(len(chain) - 1):
            key = f"{chain[i + 1]}->{chain[i]}"
            link = self._links.get(key)
            if link:
                strength *= link.strength
            else:
                strength *= 0.1
        return strength

    def _prune_weak_links(self) -> None:
        """Remove weakest links to stay under capacity."""
        sorted_links = sorted(self._links.items(),
                               key=lambda x: x[1].strength * x[1].observations)
        to_remove = len(self._links) - self.max_links + 50  # Remove 50 extra
        for key, _ in sorted_links[:to_remove]:
            del self._links[key]

    def get_state(self) -> Dict:
        strong_links = [l for l in self._links.values()
                        if l.strength >= self.min_strength and
                        l.observations >= self.min_observations]
        return {
            'total_links': len(self._links),
            'strong_links': len(strong_links),
            'recent_events': len(self._recent_events),
            'top_links': [l.to_dict() for l in
                          sorted(strong_links, key=lambda l: l.strength, reverse=True)[:10]],
        }

    @classmethod
    def from_yaml(cls, cfg: Dict) -> 'CausalWorldModel':
        section = cfg.get('causal_world_model', {})
        return cls(
            min_observations=section.get('min_observations', 3),
            min_strength=section.get('min_strength', 0.3),
            max_links=section.get('max_links', 500),
        )


# ─── P5.69: Predictive World Model ─────────────────────────────────────

@dataclass
class Prediction:
    """A prediction about future state."""
    entity: str
    metric: str
    predicted_value: float
    predicted_time: float       # When the prediction applies
    confidence: float = 0.5
    basis: str = ""             # What this prediction is based on
    created_at: float = 0.0
    verified: bool = False
    actual_value: Optional[float] = None
    prediction_error: float = 0.0

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

    def verify(self, actual: float) -> float:
        """Verify prediction against actual value."""
        self.verified = True
        self.actual_value = actual
        if self.predicted_value != 0:
            self.prediction_error = abs(actual - self.predicted_value) / abs(self.predicted_value)
        else:
            self.prediction_error = abs(actual)
        return self.prediction_error

    def to_dict(self) -> Dict:
        d = {
            'entity': self.entity,
            'metric': self.metric,
            'predicted_value': round(self.predicted_value, 3),
            'predicted_time': self.predicted_time,
            'confidence': round(self.confidence, 3),
            'basis': self.basis,
            'verified': self.verified,
        }
        if self.verified:
            d['actual_value'] = self.actual_value
            d['prediction_error'] = round(self.prediction_error, 3)
        return d


class TrendAnalyzer:
    """Simple linear trend analyzer for time series data."""

    def __init__(self, max_points: int = 100):
        self.max_points = max_points
        self._data: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_points))

    def add_point(self, series_key: str, value: float,
                  timestamp: Optional[float] = None) -> None:
        ts = timestamp or time.time()
        self._data[series_key].append((ts, value))

    def get_trend(self, series_key: str) -> Optional[Dict]:
        """
        Calculate linear trend for a series.
        Returns slope, intercept, and R² goodness of fit.
        """
        points = list(self._data.get(series_key, []))
        if len(points) < 3:
            return None

        times = [p[0] for p in points]
        values = [p[1] for p in points]
        n = len(points)

        # Normalize times to hours for meaningful slope
        t0 = times[0]
        t_hours = [(t - t0) / 3600.0 for t in times]

        # Linear regression
        sum_t = sum(t_hours)
        sum_v = sum(values)
        sum_tv = sum(t * v for t, v in zip(t_hours, values))
        sum_t2 = sum(t * t for t in t_hours)

        denom = n * sum_t2 - sum_t * sum_t
        if abs(denom) < 1e-10:
            return None

        slope = (n * sum_tv - sum_t * sum_v) / denom
        intercept = (sum_v - slope * sum_t) / n

        # R² (coefficient of determination)
        mean_v = sum_v / n
        ss_tot = sum((v - mean_v) ** 2 for v in values)
        ss_res = sum((v - (slope * t + intercept)) ** 2
                      for t, v in zip(t_hours, values))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        return {
            'slope_per_hour': round(slope, 6),
            'intercept': round(intercept, 3),
            'r_squared': round(r_squared, 3),
            'data_points': n,
            'current_value': round(values[-1], 3),
            't0': t0,
        }

    def _current_hours(self, series_key: str, t0: float) -> float:
        """Get current position in hours relative to t0, accounting for future timestamps."""
        points = list(self._data.get(series_key, []))
        last_ts = points[-1][0] if points else time.time()
        ref = max(time.time(), last_ts)
        return (ref - t0) / 3600.0

    def predict_value(self, series_key: str, hours_ahead: float) -> Optional[float]:
        """Predict value at hours_ahead from latest data point."""
        trend = self.get_trend(series_key)
        if not trend or trend['r_squared'] < 0.3:
            return None

        current_hours = self._current_hours(series_key, trend['t0'])
        future_hours = current_hours + hours_ahead
        return trend['slope_per_hour'] * future_hours + trend['intercept']

    def predict_threshold_time(self, series_key: str, threshold: float) -> Optional[float]:
        """Predict when a metric will reach a threshold. Returns hours from now."""
        trend = self.get_trend(series_key)
        if not trend or trend['r_squared'] < 0.3:
            return None
        if abs(trend['slope_per_hour']) < 1e-10:
            return None

        current_hours = self._current_hours(series_key, trend['t0'])
        current_value = trend['slope_per_hour'] * current_hours + trend['intercept']

        # Time to reach threshold
        hours_to_threshold = (threshold - current_value) / trend['slope_per_hour']
        if hours_to_threshold <= 0:
            return None  # Already past or moving away

        return hours_to_threshold


class PredictiveWorldModel:
    """
    P5.69: Predicts future states from trends and causal model.

    Combines linear trend analysis with causal reasoning to make
    predictions about future system states.
    """

    def __init__(self, min_confidence: float = 0.3,
                 max_predictions: int = 50):
        self.min_confidence = min_confidence
        self.max_predictions = max_predictions
        self.trend_analyzer = TrendAnalyzer()
        self._predictions: deque = deque(maxlen=max_predictions)
        self._verified_predictions: deque = deque(maxlen=200)
        self._calibration_error: float = 0.0  # Running average prediction error
        self._total_predictions = 0
        self._total_verified = 0

    def add_observation(self, entity: str, metric: str, value: float,
                        timestamp: Optional[float] = None) -> None:
        """Add a data point for trend analysis."""
        key = f"{entity}:{metric}"
        self.trend_analyzer.add_point(key, value, timestamp)

    def predict_trend(self, entity: str, metric: str,
                      hours_ahead: float = 2.0) -> Optional[Prediction]:
        """Predict a metric value based on trend."""
        key = f"{entity}:{metric}"
        trend = self.trend_analyzer.get_trend(key)
        if not trend:
            return None

        predicted = self.trend_analyzer.predict_value(key, hours_ahead)
        if predicted is None:
            return None

        pred = Prediction(
            entity=entity,
            metric=metric,
            predicted_value=predicted,
            predicted_time=time.time() + hours_ahead * 3600,
            confidence=max(0.1, trend['r_squared'] * (1 - self._calibration_error)),
            basis=f"linear_trend(slope={trend['slope_per_hour']:.4f}/hr, R²={trend['r_squared']:.2f})",
        )

        if pred.confidence >= self.min_confidence:
            self._predictions.append(pred)
            self._total_predictions += 1
            return pred
        return None

    def predict_threshold_breach(self, entity: str, metric: str,
                                  threshold: float,
                                  alert_label: str = "") -> Optional[Prediction]:
        """Predict when a metric will breach a threshold."""
        key = f"{entity}:{metric}"
        hours = self.trend_analyzer.predict_threshold_time(key, threshold)
        if hours is None:
            return None

        trend = self.trend_analyzer.get_trend(key)
        if not trend:
            return None

        pred = Prediction(
            entity=entity,
            metric=metric,
            predicted_value=threshold,
            predicted_time=time.time() + hours * 3600,
            confidence=max(0.1, trend['r_squared'] * 0.8),
            basis=f"threshold_breach({alert_label or metric}>={threshold} in {hours:.1f}h)",
        )

        if pred.confidence >= self.min_confidence:
            self._predictions.append(pred)
            self._total_predictions += 1
            return pred
        return None

    def predict_cascade(self, trigger_event: str,
                         causal_model: CausalWorldModel) -> List[Prediction]:
        """Predict cascade effects using causal model."""
        effects = causal_model.get_effects(trigger_event)
        predictions = []

        for link in effects:
            pred = Prediction(
                entity=link.effect,
                metric="status",
                predicted_value=0.0,  # "failure" encoded as 0
                predicted_time=time.time() + link.avg_delay_ms / 1000.0,
                confidence=link.strength * 0.7,
                basis=f"causal({link.cause}->{link.effect}, strength={link.strength:.2f})",
            )
            if pred.confidence >= self.min_confidence:
                predictions.append(pred)
                self._predictions.append(pred)
                self._total_predictions += 1

        return predictions

    def verify_prediction(self, entity: str, metric: str,
                           actual_value: float) -> List[Dict]:
        """Verify pending predictions against actual values."""
        results = []
        for pred in self._predictions:
            if (pred.entity == entity and pred.metric == metric and
                    not pred.verified and
                    time.time() >= pred.predicted_time - 300):  # 5min tolerance
                error = pred.verify(actual_value)
                self._total_verified += 1
                self._verified_predictions.append(pred)

                # Update calibration error
                alpha = 0.1
                self._calibration_error = (alpha * error +
                                            (1 - alpha) * self._calibration_error)

                results.append(pred.to_dict())

        return results

    def get_active_predictions(self) -> List[Prediction]:
        """Get unverified predictions."""
        now = time.time()
        return [p for p in self._predictions
                if not p.verified and p.predicted_time > now]

    def get_accuracy(self) -> float:
        """Get prediction accuracy from verified predictions."""
        verified = [p for p in self._verified_predictions if p.verified]
        if not verified:
            return 0.0
        accurate = sum(1 for p in verified if p.prediction_error < 0.2)
        return accurate / len(verified)

    def get_state(self) -> Dict:
        active = self.get_active_predictions()
        return {
            'total_predictions': self._total_predictions,
            'total_verified': self._total_verified,
            'active_predictions': len(active),
            'calibration_error': round(self._calibration_error, 3),
            'accuracy': round(self.get_accuracy(), 3),
            'active_details': [p.to_dict() for p in active[:5]],
        }

    @classmethod
    def from_yaml(cls, cfg: Dict) -> 'PredictiveWorldModel':
        section = cfg.get('predictive_world_model', {})
        return cls(
            min_confidence=section.get('min_confidence', 0.3),
            max_predictions=section.get('max_predictions', 50),
        )
