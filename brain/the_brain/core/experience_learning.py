"""
Experience-Based Learning System (V2 PHASE 5: P5.61-63)

P5.61: ExperienceReplaySystem
  - Stores (Situation, System, Action, Params, Outcome, Duration, EmotionalState) tuples
  - Prioritized replay: failures and surprising successes replayed more often
  - Pattern mining across experiences to find cross-system strategies

P5.62: AutomaticOutcomeLearning
  - Automatic outcome detection without manual feedback
  - Shell exit-code != 0 -> failure
  - HTTP status >= 400 -> failure
  - Job status == FAILED -> failure
  - Feeds remember_task() with outcome automatically

P5.63: TransferLearning
  - Cross-domain knowledge transfer
  - Maps successful strategies from one domain to similar domains
  - Tracks transfer success rates to validate transfers
"""

import time
import json
import os
import math
import logging
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger('brain.experience_learning')


# ─── P5.61: Experience Replay System ────────────────────────────────────

class OutcomeType(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class Experience:
    """A single recorded experience tuple."""
    situation: str               # Task description / context
    system: str                  # Which system handled it (e.g., "coding_engine", "shell")
    action: str                  # Action taken
    params: Dict[str, Any]       # Action parameters
    outcome: OutcomeType         # Result
    duration_ms: float           # How long it took
    emotional_valence: float     # Emotional state at time (-1 to 1)
    emotional_arousal: float     # Arousal level (0 to 1)
    domain: str = ""             # Domain category (e.g., "deployment", "testing")
    confidence: float = 0.5      # Prediction confidence before action
    prediction_error: float = 0.0  # abs(predicted - actual) outcome
    timestamp: float = 0.0
    replay_count: int = 0        # How many times this was replayed
    priority: float = 0.0        # Replay priority (higher = more important)

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
        self._compute_priority()

    def _compute_priority(self):
        """Priority based on surprise and failure (TD-error inspired)."""
        # Failures are more important to learn from
        failure_bonus = 1.5 if self.outcome == OutcomeType.FAILURE else 0.0
        # Surprising outcomes (high prediction error) are more important
        surprise_bonus = self.prediction_error * 2.0
        # Emotional intensity adds salience
        emotional_bonus = abs(self.emotional_valence) * self.emotional_arousal
        # Recency decay (newer = higher priority)
        age_hours = (time.time() - self.timestamp) / 3600.0
        recency = max(0.1, 1.0 / (1.0 + age_hours * 0.1))
        # Diminish priority after many replays
        replay_decay = 1.0 / (1.0 + self.replay_count * 0.3)

        self.priority = (failure_bonus + surprise_bonus + emotional_bonus) * recency * replay_decay

    def to_dict(self) -> Dict:
        return {
            'situation': self.situation,
            'system': self.system,
            'action': self.action,
            'params': self.params,
            'outcome': self.outcome.value,
            'duration_ms': round(self.duration_ms, 1),
            'emotional_valence': round(self.emotional_valence, 3),
            'emotional_arousal': round(self.emotional_arousal, 3),
            'domain': self.domain,
            'confidence': round(self.confidence, 3),
            'prediction_error': round(self.prediction_error, 3),
            'timestamp': self.timestamp,
            'replay_count': self.replay_count,
            'priority': round(self.priority, 3),
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'Experience':
        return cls(
            situation=d.get('situation', ''),
            system=d.get('system', ''),
            action=d.get('action', ''),
            params=d.get('params', {}),
            outcome=OutcomeType(d.get('outcome', 'unknown')),
            duration_ms=d.get('duration_ms', 0.0),
            emotional_valence=d.get('emotional_valence', 0.0),
            emotional_arousal=d.get('emotional_arousal', 0.0),
            domain=d.get('domain', ''),
            confidence=d.get('confidence', 0.5),
            prediction_error=d.get('prediction_error', 0.0),
            timestamp=d.get('timestamp', 0.0),
            replay_count=d.get('replay_count', 0),
        )


class ExperienceReplaySystem:
    """
    P5.61: Stores experiences and provides prioritized replay for learning.

    Uses prioritized experience replay (PER): experiences with higher
    prediction error, failures, and emotional salience are replayed more.
    """

    def __init__(self, max_buffer: int = 5000, batch_size: int = 16,
                 persist_dir: Optional[str] = None):
        self.max_buffer = max_buffer
        self.batch_size = batch_size
        self.persist_dir = persist_dir
        self._buffer: List[Experience] = []
        self._domain_index: Dict[str, List[int]] = defaultdict(list)  # domain -> buffer indices
        self._system_index: Dict[str, List[int]] = defaultdict(list)  # system -> buffer indices
        self._total_stored = 0
        self._total_replayed = 0

        # Load persisted experiences
        if persist_dir:
            self._load_from_disk()

    def record(self, experience: Experience) -> None:
        """Record a new experience."""
        if len(self._buffer) >= self.max_buffer:
            # Remove lowest priority experience
            min_idx = min(range(len(self._buffer)), key=lambda i: self._buffer[i].priority)
            self._remove_at(min_idx)

        idx = len(self._buffer)
        self._buffer.append(experience)
        self._domain_index[experience.domain].append(idx)
        self._system_index[experience.system].append(idx)
        self._total_stored += 1

    def _remove_at(self, idx: int) -> None:
        """Remove experience at index and rebuild indices."""
        exp = self._buffer[idx]
        self._buffer.pop(idx)
        # Rebuild indices (simple approach for correctness)
        self._rebuild_indices()

    def _rebuild_indices(self) -> None:
        """Rebuild domain and system indices."""
        self._domain_index.clear()
        self._system_index.clear()
        for i, exp in enumerate(self._buffer):
            self._domain_index[exp.domain].append(i)
            self._system_index[exp.system].append(i)

    def sample_batch(self, domain: Optional[str] = None) -> List[Experience]:
        """
        Sample a batch of experiences weighted by priority.
        Optionally filter by domain.
        """
        if not self._buffer:
            return []

        candidates = self._buffer
        if domain and domain in self._domain_index:
            indices = self._domain_index[domain]
            candidates = [self._buffer[i] for i in indices if i < len(self._buffer)]

        if not candidates:
            return []

        # Recompute priorities
        for exp in candidates:
            exp._compute_priority()

        # Sort by priority descending and take top batch_size
        sorted_candidates = sorted(candidates, key=lambda e: e.priority, reverse=True)
        batch = sorted_candidates[:self.batch_size]

        # Mark as replayed
        for exp in batch:
            exp.replay_count += 1
            self._total_replayed += 1

        return batch

    def get_similar_experiences(self, situation: str, domain: str = "",
                                top_k: int = 5) -> List[Experience]:
        """Find experiences similar to the given situation."""
        # Simple keyword overlap similarity
        situation_words = set(situation.lower().split())

        scored = []
        for exp in self._buffer:
            if domain and exp.domain != domain:
                continue
            exp_words = set(exp.situation.lower().split())
            overlap = len(situation_words & exp_words)
            if overlap > 0:
                similarity = overlap / max(len(situation_words), 1)
                scored.append((exp, similarity))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [exp for exp, _ in scored[:top_k]]

    def get_domain_stats(self) -> Dict[str, Dict]:
        """Get success/failure statistics per domain."""
        stats = {}
        for domain, indices in self._domain_index.items():
            experiences = [self._buffer[i] for i in indices if i < len(self._buffer)]
            total = len(experiences)
            successes = sum(1 for e in experiences if e.outcome == OutcomeType.SUCCESS)
            failures = sum(1 for e in experiences if e.outcome == OutcomeType.FAILURE)
            avg_duration = sum(e.duration_ms for e in experiences) / max(total, 1)
            avg_pe = sum(e.prediction_error for e in experiences) / max(total, 1)
            stats[domain] = {
                'total': total,
                'success_rate': round(successes / max(total, 1), 3),
                'failure_rate': round(failures / max(total, 1), 3),
                'avg_duration_ms': round(avg_duration, 1),
                'avg_prediction_error': round(avg_pe, 3),
            }
        return stats

    def find_patterns(self, min_occurrences: int = 3) -> List[Dict]:
        """
        Pattern mining: find recurring (system, action, domain) combinations
        and their outcome distributions.
        """
        pattern_counts: Dict[Tuple, List[Experience]] = defaultdict(list)
        for exp in self._buffer:
            key = (exp.system, exp.action, exp.domain)
            pattern_counts[key].append(exp)

        patterns = []
        for key, experiences in pattern_counts.items():
            if len(experiences) >= min_occurrences:
                system, action, domain = key
                successes = sum(1 for e in experiences if e.outcome == OutcomeType.SUCCESS)
                total = len(experiences)
                avg_dur = sum(e.duration_ms for e in experiences) / total
                patterns.append({
                    'system': system,
                    'action': action,
                    'domain': domain,
                    'occurrences': total,
                    'success_rate': round(successes / total, 3),
                    'avg_duration_ms': round(avg_dur, 1),
                })

        patterns.sort(key=lambda p: p['occurrences'], reverse=True)
        return patterns

    def _load_from_disk(self) -> None:
        """Load experiences from disk."""
        if not self.persist_dir or not os.path.isdir(self.persist_dir):
            return
        filepath = os.path.join(self.persist_dir, 'experience_buffer.json')
        if os.path.isfile(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                for d in data:
                    self._buffer.append(Experience.from_dict(d))
                self._rebuild_indices()
                self._total_stored = len(self._buffer)
            except Exception as e:
                logger.warning(f"Failed to load experiences: {e}")

    def save_to_disk(self) -> None:
        """Persist experiences to disk."""
        if not self.persist_dir:
            return
        os.makedirs(self.persist_dir, exist_ok=True)
        filepath = os.path.join(self.persist_dir, 'experience_buffer.json')
        try:
            data = [exp.to_dict() for exp in self._buffer]
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save experiences: {e}")

    def get_state(self) -> Dict:
        return {
            'buffer_size': len(self._buffer),
            'max_buffer': self.max_buffer,
            'total_stored': self._total_stored,
            'total_replayed': self._total_replayed,
            'domains': list(self._domain_index.keys()),
            'systems': list(self._system_index.keys()),
            'domain_stats': self.get_domain_stats(),
        }

    @classmethod
    def from_yaml(cls, cfg: Dict) -> 'ExperienceReplaySystem':
        section = cfg.get('experience_replay', {})
        return cls(
            max_buffer=section.get('max_buffer', 5000),
            batch_size=section.get('batch_size', 16),
            persist_dir=section.get('persist_dir', None),
        )


# ─── P5.62: Automatic Outcome Learning ─────────────────────────────────

class OutcomeSignal:
    """A detected outcome from system signals."""
    def __init__(self, outcome: OutcomeType, source: str, details: str = "",
                 confidence: float = 1.0):
        self.outcome = outcome
        self.source = source
        self.details = details
        self.confidence = confidence
        self.timestamp = time.time()

    def to_dict(self) -> Dict:
        return {
            'outcome': self.outcome.value,
            'source': self.source,
            'details': self.details,
            'confidence': round(self.confidence, 3),
            'timestamp': self.timestamp,
        }


class AutomaticOutcomeLearning:
    """
    P5.62: Detects outcomes automatically from system signals.

    No manual feedback needed — watches exit codes, HTTP status,
    job statuses, and other signals to determine success/failure.
    """

    def __init__(self, success_threshold: float = 0.7):
        self.success_threshold = success_threshold
        self._outcome_rules: List[Dict] = self._default_rules()
        self._total_detections = 0
        self._outcome_counts: Dict[str, int] = defaultdict(int)
        self._recent_outcomes: deque = deque(maxlen=100)

    def _default_rules(self) -> List[Dict]:
        """Default outcome detection rules."""
        return [
            # Shell command outcomes
            {'source': 'shell', 'field': 'exit_code', 'condition': 'eq', 'value': 0,
             'outcome': OutcomeType.SUCCESS, 'confidence': 0.95},
            {'source': 'shell', 'field': 'exit_code', 'condition': 'neq', 'value': 0,
             'outcome': OutcomeType.FAILURE, 'confidence': 0.9},

            # HTTP outcomes
            {'source': 'http', 'field': 'status_code', 'condition': 'lt', 'value': 400,
             'outcome': OutcomeType.SUCCESS, 'confidence': 0.85},
            {'source': 'http', 'field': 'status_code', 'condition': 'gte', 'value': 400,
             'outcome': OutcomeType.FAILURE, 'confidence': 0.85},
            {'source': 'http', 'field': 'status_code', 'condition': 'gte', 'value': 500,
             'outcome': OutcomeType.FAILURE, 'confidence': 0.95},

            # Job outcomes
            {'source': 'job', 'field': 'status', 'condition': 'eq', 'value': 'completed',
             'outcome': OutcomeType.SUCCESS, 'confidence': 0.95},
            {'source': 'job', 'field': 'status', 'condition': 'eq', 'value': 'failed',
             'outcome': OutcomeType.FAILURE, 'confidence': 0.95},

            # Timeout
            {'source': 'any', 'field': 'timed_out', 'condition': 'eq', 'value': True,
             'outcome': OutcomeType.TIMEOUT, 'confidence': 0.9},
        ]

    def detect_outcome(self, signals: Dict[str, Any],
                       source: str = "unknown") -> Optional[OutcomeSignal]:
        """
        Detect outcome from raw signals.

        Args:
            signals: Dict of signal values, e.g. {'exit_code': 0} or {'status_code': 200}
            source: Signal source type ('shell', 'http', 'job', etc.)

        Returns:
            OutcomeSignal if detected, None otherwise
        """
        best_match: Optional[OutcomeSignal] = None
        best_confidence = 0.0

        for rule in self._outcome_rules:
            if rule['source'] != source and rule['source'] != 'any':
                continue

            field_val = signals.get(rule['field'])
            if field_val is None:
                continue

            matched = self._check_condition(field_val, rule['condition'], rule['value'])
            if matched and rule['confidence'] > best_confidence:
                best_confidence = rule['confidence']
                best_match = OutcomeSignal(
                    outcome=rule['outcome'],
                    source=source,
                    details=f"{rule['field']}={field_val}",
                    confidence=rule['confidence'],
                )

        if best_match:
            self._total_detections += 1
            self._outcome_counts[best_match.outcome.value] += 1
            self._recent_outcomes.append(best_match)

        return best_match

    def _check_condition(self, actual: Any, condition: str, expected: Any) -> bool:
        """Check a single condition."""
        try:
            if condition == 'eq':
                return actual == expected
            elif condition == 'neq':
                return actual != expected
            elif condition == 'lt':
                return actual < expected
            elif condition == 'lte':
                return actual <= expected
            elif condition == 'gt':
                return actual > expected
            elif condition == 'gte':
                return actual >= expected
            elif condition == 'contains':
                return expected in str(actual)
        except (TypeError, ValueError):
            pass
        return False

    def add_rule(self, source: str, field: str, condition: str,
                 value: Any, outcome: OutcomeType, confidence: float = 0.8) -> None:
        """Add a custom outcome detection rule."""
        self._outcome_rules.append({
            'source': source, 'field': field, 'condition': condition,
            'value': value, 'outcome': outcome, 'confidence': confidence,
        })

    def get_recent_success_rate(self, window: int = 20) -> float:
        """Get success rate from recent outcomes."""
        recent = list(self._recent_outcomes)[-window:]
        if not recent:
            return 0.0
        successes = sum(1 for o in recent if o.outcome == OutcomeType.SUCCESS)
        return successes / len(recent)

    def get_state(self) -> Dict:
        return {
            'total_detections': self._total_detections,
            'outcome_counts': dict(self._outcome_counts),
            'num_rules': len(self._outcome_rules),
            'recent_success_rate': round(self.get_recent_success_rate(), 3),
            'recent_outcomes': len(self._recent_outcomes),
        }


# ─── P5.63: Transfer Learning ──────────────────────────────────────────

@dataclass
class DomainMapping:
    """A mapping of knowledge from source to target domain."""
    source_domain: str
    target_domain: str
    strategy: str            # The strategy being transferred
    source_success_rate: float
    transfer_success_rate: float = 0.0
    transfer_attempts: int = 0
    transfer_successes: int = 0
    confidence: float = 0.5
    created_at: float = 0.0

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

    def record_transfer_outcome(self, success: bool) -> None:
        """Record whether a transfer worked."""
        self.transfer_attempts += 1
        if success:
            self.transfer_successes += 1
        self.transfer_success_rate = self.transfer_successes / self.transfer_attempts
        # Update confidence: Bayesian-ish update
        self.confidence = (self.confidence * 0.8 +
                           self.transfer_success_rate * 0.2)

    def to_dict(self) -> Dict:
        return {
            'source_domain': self.source_domain,
            'target_domain': self.target_domain,
            'strategy': self.strategy,
            'source_success_rate': round(self.source_success_rate, 3),
            'transfer_success_rate': round(self.transfer_success_rate, 3),
            'transfer_attempts': self.transfer_attempts,
            'transfer_successes': self.transfer_successes,
            'confidence': round(self.confidence, 3),
        }


class TransferLearning:
    """
    P5.63: Cross-domain knowledge transfer.

    Identifies successful strategies in one domain and suggests
    applying them to similar domains. Tracks transfer success
    to validate whether transfers actually work.
    """

    # Domain similarity matrix (pre-defined relationships)
    DOMAIN_SIMILARITY: Dict[str, List[str]] = {
        'code_review': ['config_validation', 'testing', 'documentation'],
        'deployment': ['configuration', 'infrastructure', 'monitoring'],
        'testing': ['code_review', 'debugging', 'validation'],
        'debugging': ['testing', 'monitoring', 'code_review'],
        'infrastructure': ['deployment', 'configuration', 'monitoring'],
        'monitoring': ['debugging', 'infrastructure', 'alerting'],
        'configuration': ['deployment', 'infrastructure'],
        'documentation': ['code_review', 'reporting'],
    }

    def __init__(self, min_source_success_rate: float = 0.7,
                 min_source_experiences: int = 5,
                 max_mappings: int = 200):
        self.min_source_success_rate = min_source_success_rate
        self.min_source_experiences = min_source_experiences
        self.max_mappings = max_mappings
        self._mappings: List[DomainMapping] = []
        self._mapping_index: Dict[str, List[int]] = defaultdict(list)  # target -> mapping indices
        self._total_transfers = 0
        self._successful_transfers = 0

    def discover_transfers(self, experience_system: ExperienceReplaySystem) -> List[DomainMapping]:
        """
        Analyze experience buffer to discover potential transfers.

        Finds strategies with high success in source domain and
        suggests transfer to similar target domains.
        """
        domain_stats = experience_system.get_domain_stats()
        patterns = experience_system.find_patterns()
        new_mappings = []

        for pattern in patterns:
            source_domain = pattern['domain']
            if not source_domain:
                continue
            if pattern['success_rate'] < self.min_source_success_rate:
                continue
            if pattern['occurrences'] < self.min_source_experiences:
                continue

            strategy = f"{pattern['system']}:{pattern['action']}"

            # Find similar domains
            similar = self.DOMAIN_SIMILARITY.get(source_domain, [])
            for target_domain in similar:
                # Check if we already have this mapping
                existing = self._find_mapping(source_domain, target_domain, strategy)
                if existing:
                    continue

                mapping = DomainMapping(
                    source_domain=source_domain,
                    target_domain=target_domain,
                    strategy=strategy,
                    source_success_rate=pattern['success_rate'],
                    confidence=pattern['success_rate'] * 0.5,  # Start at half source confidence
                )
                self._add_mapping(mapping)
                new_mappings.append(mapping)

        return new_mappings

    def suggest_strategy(self, target_domain: str,
                         min_confidence: float = 0.3) -> List[DomainMapping]:
        """
        Suggest strategies for a target domain based on transfers.

        Returns mappings sorted by confidence (highest first).
        """
        indices = self._mapping_index.get(target_domain, [])
        candidates = [self._mappings[i] for i in indices
                       if i < len(self._mappings)
                       and self._mappings[i].confidence >= min_confidence]
        candidates.sort(key=lambda m: m.confidence, reverse=True)
        return candidates

    def record_transfer_outcome(self, source_domain: str, target_domain: str,
                                strategy: str, success: bool) -> None:
        """Record the outcome of a transfer attempt."""
        mapping = self._find_mapping(source_domain, target_domain, strategy)
        if mapping:
            mapping.record_transfer_outcome(success)
            self._total_transfers += 1
            if success:
                self._successful_transfers += 1

    def _find_mapping(self, source: str, target: str, strategy: str) -> Optional[DomainMapping]:
        """Find an existing mapping."""
        for m in self._mappings:
            if m.source_domain == source and m.target_domain == target and m.strategy == strategy:
                return m
        return None

    def _add_mapping(self, mapping: DomainMapping) -> None:
        """Add a new mapping, evicting lowest confidence if at capacity."""
        if len(self._mappings) >= self.max_mappings:
            min_idx = min(range(len(self._mappings)),
                          key=lambda i: self._mappings[i].confidence)
            self._mappings.pop(min_idx)
            self._rebuild_index()

        idx = len(self._mappings)
        self._mappings.append(mapping)
        self._mapping_index[mapping.target_domain].append(idx)

    def _rebuild_index(self) -> None:
        self._mapping_index.clear()
        for i, m in enumerate(self._mappings):
            self._mapping_index[m.target_domain].append(i)

    def get_state(self) -> Dict:
        return {
            'total_mappings': len(self._mappings),
            'total_transfers': self._total_transfers,
            'successful_transfers': self._successful_transfers,
            'transfer_success_rate': round(
                self._successful_transfers / max(self._total_transfers, 1), 3),
            'target_domains': list(self._mapping_index.keys()),
            'top_mappings': [m.to_dict() for m in
                             sorted(self._mappings, key=lambda m: m.confidence, reverse=True)[:5]],
        }

    @classmethod
    def from_yaml(cls, cfg: Dict) -> 'TransferLearning':
        section = cfg.get('transfer_learning', {})
        return cls(
            min_source_success_rate=section.get('min_source_success_rate', 0.7),
            min_source_experiences=section.get('min_source_experiences', 5),
            max_mappings=section.get('max_mappings', 200),
        )
