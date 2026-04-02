"""
Meta-Brain System (PHASE 13 - Gödel-inspired Meta-level)

Implements S_(n+1) validation over S_n swarm decisions.

Based on Gödel's incompleteness: A formal system cannot prove its own
consistency, but a meta-system can analyze patterns and contradictions
across multiple system instances.

Key functions:
1. Pattern Analysis: Identify recurring decision patterns
2. Contradiction Detection: Find self-referential conflicts
3. Brain Performance Profiling: Track success/failure by domain & context
4. Drift Detection: Detect degradation in coherence over time
5. Policy Updates: Adapt brain weights based on meta-level insights

Mathematical foundation:
- Level S_n: Individual brain decisions
- Level S_(n+1): Meta-brain analyzing S_n patterns
- Gödel sentence: "This brain combination produces contradictions"
- Meta-validation: Checks consistency across decision history
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import hashlib


@dataclass
class BrainProfile:
    """
    Performance profile for a single brain
    """
    brain_id: str
    brain_name: str

    # Performance by domain
    domain_success: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    domain_failure: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    # Semantic coherence metrics
    avg_distance_to_consensus: float = 0.5  # How far from swarm consensus
    coherence_contribution: float = 0.5  # How much brain adds to K
    disagreement_count: int = 0  # Times brain disagreed with consensus

    # Context sensitivity
    context_performance: Dict[str, float] = field(default_factory=dict)

    # Meta-level patterns
    contradiction_count: int = 0  # Self-contradictions over time
    consistency_score: float = 0.5  # Temporal consistency

    def domain_success_rate(self, domain: str) -> float:
        """Get success rate for a domain"""
        total = self.domain_success[domain] + self.domain_failure[domain]
        return self.domain_success[domain] / total if total > 0 else 0.5

    def overall_success_rate(self) -> float:
        """Get overall success rate"""
        total_success = sum(self.domain_success.values())
        total_failure = sum(self.domain_failure.values())
        total = total_success + total_failure
        return total_success / total if total > 0 else 0.5

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'brain_id': self.brain_id,
            'brain_name': self.brain_name,
            'avg_distance_to_consensus': self.avg_distance_to_consensus,
            'coherence_contribution': self.coherence_contribution,
            'disagreement_count': self.disagreement_count,
            'contradiction_count': self.contradiction_count,
            'consistency_score': self.consistency_score,
            'overall_success_rate': self.overall_success_rate()
        }


@dataclass
class MetaPattern:
    """
    Detected pattern in swarm behavior
    """
    pattern_id: str
    pattern_type: str  # 'contradiction', 'drift', 'bias', 'convergence'
    description: str

    # Evidence
    affected_brains: List[str] = field(default_factory=list)
    evidence_count: int = 0
    confidence: float = 0.5

    # Context
    domain: Optional[str] = None
    time_detected: Optional[int] = None

    # Recommendation
    recommendation: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'pattern_id': self.pattern_id,
            'pattern_type': self.pattern_type,
            'description': self.description,
            'affected_brains': self.affected_brains,
            'evidence_count': self.evidence_count,
            'confidence': self.confidence,
            'domain': self.domain,
            'recommendation': self.recommendation
        }


class MetaBrain:
    """
    Meta-brain system for analyzing swarm patterns (Level S_(n+1))

    Analyzes decision history to detect:
    - Self-contradictions (Gödel-inspired)
    - Performance drift over time
    - Domain-specific biases
    - Coherence degradation
    - Optimal brain combinations
    """

    def __init__(
        self,
        consistency_window: int = 10,
        drift_threshold: float = 0.15,
        contradiction_threshold: float = 0.3
    ):
        """
        Initialize meta-brain

        Args:
            consistency_window: Rolling window for consistency checks
            drift_threshold: Threshold for detecting drift in K
            contradiction_threshold: Threshold for contradiction detection
        """
        self.consistency_window = consistency_window
        self.drift_threshold = drift_threshold
        self.contradiction_threshold = contradiction_threshold

        # Brain profiles
        self.brain_profiles: Dict[str, BrainProfile] = {}

        # Detected patterns
        self.detected_patterns: List[MetaPattern] = []

        # History tracking
        self.coherence_history: List[float] = []  # K over time
        self.disagreement_history: List[float] = []  # U over time
        self.decision_history: List[Dict] = []  # Full decisions

        # Statistics
        self.total_analyses = 0
        self.patterns_detected = 0
        self.contradictions_found = 0

    def analyze_decision(
        self,
        swarm_decision: Dict,
        brain_answers: List,
        outcome: Optional[str] = None
    ):
        """
        Analyze a single swarm decision (meta-level validation)

        Args:
            swarm_decision: Swarm decision dict
            brain_answers: List of brain answers
            outcome: Optional outcome ('success', 'failure')
        """
        self.total_analyses += 1

        # Update history
        if 'coherence_K' in swarm_decision:
            self.coherence_history.append(swarm_decision['coherence_K'])
        if 'disagreement_U' in swarm_decision:
            self.disagreement_history.append(swarm_decision['disagreement_U'])

        self.decision_history.append({
            'decision': swarm_decision,
            'brain_answers': brain_answers,
            'outcome': outcome,
            'timestamp': self.total_analyses
        })

        # Update brain profiles
        self._update_brain_profiles(swarm_decision, brain_answers, outcome)

        # Detect patterns (every N decisions)
        if self.total_analyses % 10 == 0:
            self._detect_patterns()

    def _update_brain_profiles(
        self,
        swarm_decision: Dict,
        brain_answers: List,
        outcome: Optional[str]
    ):
        """Update brain performance profiles"""
        decision = swarm_decision.get('consensus_decision', 'wait')
        domain = swarm_decision.get('task_description', '').split()[0]

        for answer in brain_answers:
            brain_id = answer.brain_id

            # Create profile if not exists
            if brain_id not in self.brain_profiles:
                self.brain_profiles[brain_id] = BrainProfile(
                    brain_id=brain_id,
                    brain_name=f"Brain-{brain_id}"
                )

            profile = self.brain_profiles[brain_id]

            # Update outcome
            if outcome == 'success':
                profile.domain_success[domain] += 1
            elif outcome == 'failure':
                profile.domain_failure[domain] += 1

            # Check if brain disagreed with consensus
            if answer.decision_type != decision:
                profile.disagreement_count += 1

    def _detect_patterns(self):
        """Detect meta-level patterns"""
        # Pattern 1: Coherence drift
        if len(self.coherence_history) >= self.consistency_window:
            recent_K = self.coherence_history[-self.consistency_window:]
            older_K = self.coherence_history[-(2 * self.consistency_window):-self.consistency_window] if len(
                self.coherence_history) >= 2 * self.consistency_window else recent_K

            drift = np.mean(older_K) - np.mean(recent_K)

            if abs(drift) > self.drift_threshold:
                pattern = MetaPattern(
                    pattern_id=f"drift_{self.total_analyses}",
                    pattern_type='drift',
                    description=f"Coherence drift detected: {drift:.3f} change",
                    evidence_count=len(recent_K),
                    confidence=min(1.0, abs(drift) / self.drift_threshold),
                    time_detected=self.total_analyses,
                    recommendation="Review brain weights or training data"
                )
                self.detected_patterns.append(pattern)
                self.patterns_detected += 1

        # Pattern 2: Self-contradictions (Gödel-inspired)
        for brain_id, profile in self.brain_profiles.items():
            # Check if brain's recent decisions contradict earlier ones
            brain_decisions = [
                h for h in self.decision_history[-self.consistency_window:]
                if any(a.brain_id == brain_id for a in h['brain_answers'])
            ]

            if len(brain_decisions) >= 5:
                # Extract decisions
                decisions = [
                    next((a.decision_type for a in h['brain_answers'] if a.brain_id == brain_id), None)
                    for h in brain_decisions
                ]

                # Check for flip-flopping (A → B → A → B)
                flips = 0
                for i in range(len(decisions) - 1):
                    if decisions[i] != decisions[i + 1]:
                        flips += 1

                flip_rate = flips / (len(decisions) - 1)

                if flip_rate > self.contradiction_threshold:
                    pattern = MetaPattern(
                        pattern_id=f"contradiction_{brain_id}_{self.total_analyses}",
                        pattern_type='contradiction',
                        description=f"Brain {brain_id} shows inconsistent decisions (flip rate: {flip_rate:.2f})",
                        affected_brains=[brain_id],
                        evidence_count=flips,
                        confidence=flip_rate,
                        time_detected=self.total_analyses,
                        recommendation=f"Reduce weight for brain {brain_id} or retrain"
                    )
                    self.detected_patterns.append(pattern)
                    self.patterns_detected += 1
                    self.contradictions_found += 1
                    profile.contradiction_count += 1

        # Pattern 3: Domain bias
        for brain_id, profile in self.brain_profiles.items():
            # Check if brain consistently fails in specific domains
            for domain, failures in profile.domain_failure.items():
                successes = profile.domain_success.get(domain, 0)
                total = successes + failures

                if total >= 5 and failures / total > 0.7:  # >70% failure rate
                    pattern = MetaPattern(
                        pattern_id=f"bias_{brain_id}_{domain}_{self.total_analyses}",
                        pattern_type='bias',
                        description=f"Brain {brain_id} shows poor performance in {domain} ({failures}/{total} failures)",
                        affected_brains=[brain_id],
                        evidence_count=failures,
                        confidence=failures / total,
                        domain=domain,
                        time_detected=self.total_analyses,
                        recommendation=f"Reduce brain {brain_id} weight for {domain} tasks"
                    )
                    self.detected_patterns.append(pattern)
                    self.patterns_detected += 1

    def get_policy_updates(self) -> Dict[str, float]:
        """
        Generate policy updates based on meta-analysis

        Returns:
            Dict of brain_id -> weight adjustment (-1 to +1)
        """
        updates = {}

        for brain_id, profile in self.brain_profiles.items():
            adjustment = 0.0

            # Positive adjustment for high success
            success_rate = profile.overall_success_rate()
            if success_rate > 0.7:
                adjustment += 0.1
            elif success_rate < 0.3:
                adjustment -= 0.1

            # Negative adjustment for contradictions
            if profile.contradiction_count > 3:
                adjustment -= 0.2

            # Negative adjustment for high disagreement
            if profile.disagreement_count > 10:
                adjustment -= 0.1

            if adjustment != 0.0:
                updates[brain_id] = adjustment

        return updates

    def get_statistics(self) -> Dict:
        """Get meta-brain statistics"""
        recent_K = np.mean(self.coherence_history[-10:]) if self.coherence_history else 0.5
        recent_U = np.mean(self.disagreement_history[-10:]) if self.disagreement_history else 0.5

        # Pattern breakdown
        pattern_types = defaultdict(int)
        for pattern in self.detected_patterns:
            pattern_types[pattern.pattern_type] += 1

        return {
            'total_analyses': self.total_analyses,
            'patterns_detected': self.patterns_detected,
            'contradictions_found': self.contradictions_found,
            'recent_coherence_K': recent_K,
            'recent_disagreement_U': recent_U,
            'pattern_types': dict(pattern_types),
            'brain_profiles': len(self.brain_profiles),
            'policy_updates_available': len(self.get_policy_updates())
        }

    def __repr__(self):
        return (
            f"MetaBrain("
            f"analyses={self.total_analyses}, "
            f"patterns={self.patterns_detected}, "
            f"contradictions={self.contradictions_found})"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("META-BRAIN SYSTEM (PHASE 13 - Gödel-inspired Meta-level)")
    print("=" * 70)
    print()
    print("Implements S_(n+1) validation over S_n swarm decisions:")
    print("  1. Pattern Analysis: Recurring decision patterns")
    print("  2. Contradiction Detection: Self-referential conflicts")
    print("  3. Brain Performance Profiling: Success/failure by domain")
    print("  4. Drift Detection: Coherence degradation over time")
    print("  5. Policy Updates: Adaptive brain weight adjustments")
    print()
    print("Based on Gödel's incompleteness theorem:")
    print("  - Level S_n: Individual brain decisions")
    print("  - Level S_(n+1): Meta-brain analyzing S_n patterns")
    print("  - Gödel sentence: 'This brain combination produces contradictions'")
    print()
    print("To test the complete system, run:")
    print("  python demos/test_semantic_coherence.py")
    print()
    print("=" * 70)
