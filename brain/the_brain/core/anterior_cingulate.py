"""
Anterior Cingulate Cortex Module - Phase C3

Explicit conflict monitoring and cognitive effort allocation,
extending cortical feedback with a dedicated ACC model.

Neuroscience basis:
- Botvinick et al. (2001): Conflict monitoring theory
- Shenhav et al. (2013): Expected Value of Control (EVC)
- dorsal ACC: Conflict detection, error monitoring
- subgenual ACC: Emotional regulation, autonomic link

Key functions:
- Conflict monitoring: Detects response competition
- Error likelihood estimation: Predicts when errors are likely
- Cognitive effort allocation: How much control to invest
- Autonomic regulation: ACC -> autonomic nervous system link

Integration:
- Input: Response channels (from PFC/BG), error signals
- Output: Control signal to PFC, arousal modulation to NE system
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.acc')


@dataclass
class ACCStats:
    """ACC statistics."""
    total_conflict_checks: int = 0
    total_high_conflict: int = 0
    total_errors_detected: int = 0
    avg_conflict: float = 0.0
    avg_effort_allocated: float = 0.0
    current_control_signal: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_conflict_checks': self.total_conflict_checks,
            'total_high_conflict': self.total_high_conflict,
            'total_errors_detected': self.total_errors_detected,
            'avg_conflict': round(self.avg_conflict, 3),
            'avg_effort_allocated': round(self.avg_effort_allocated, 3),
            'current_control_signal': round(self.current_control_signal, 3),
        }


class ConflictMonitor:
    """
    Detects response conflict from competing action channels.

    Botvinick et al. (2001): Conflict = simultaneous activation
    of incompatible response representations. Measured as the
    energy of response competition.
    """

    def __init__(self, n_channels: int = 4, conflict_threshold: float = 0.5):
        self.n_channels = n_channels
        self.conflict_threshold = conflict_threshold
        self._conflict_history = deque(maxlen=100)

    def compute_conflict(self, response_activations: np.ndarray) -> float:
        """
        Compute conflict from response channel activations.

        Conflict is high when multiple channels are simultaneously active
        (Hopfield energy of competition).

        Args:
            response_activations: Activation levels for each response [n_channels]

        Returns:
            Conflict level [0, 1]
        """
        act = np.asarray(response_activations, dtype=np.float32).flatten()
        padded = np.zeros(self.n_channels, dtype=np.float32)
        n = min(len(act), self.n_channels)
        padded[:n] = np.clip(act[:n], 0.0, 1.0)

        if padded.sum() < 1e-8:
            conflict = 0.0
        else:
            # Entropy-based conflict: high when activations are uniform
            probs = padded / (padded.sum() + 1e-8)
            max_entropy = np.log(self.n_channels) if self.n_channels > 1 else 1.0
            entropy = -float(np.sum(probs * np.log(probs + 1e-8)))
            conflict = entropy / max_entropy if max_entropy > 0 else 0.0

        self._conflict_history.append(conflict)
        return conflict

    def is_high_conflict(self, conflict: float) -> bool:
        return conflict > self.conflict_threshold

    def get_avg_conflict(self) -> float:
        if not self._conflict_history:
            return 0.0
        return float(np.mean(list(self._conflict_history)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'threshold': self.conflict_threshold,
            'avg_conflict': self.get_avg_conflict(),
        }


class ErrorLikelihoodEstimator:
    """
    Estimates the probability of making an error given current state.

    Brown & Braver (2005): ACC tracks error likelihood,
    not just conflict per se.
    """

    def __init__(self, history_size: int = 50):
        self.history_size = history_size
        self._outcomes = deque(maxlen=history_size)  # True=error, False=correct

    def record_outcome(self, was_error: bool):
        """Record whether the last response was an error."""
        self._outcomes.append(was_error)

    def estimate_error_likelihood(self, conflict: float) -> float:
        """
        Estimate error probability based on recent history and conflict.

        Returns:
            Estimated error probability [0, 1]
        """
        if not self._outcomes:
            # Prior: error likelihood proportional to conflict
            return conflict * 0.5

        base_rate = sum(self._outcomes) / len(self._outcomes)
        # Higher conflict increases error likelihood
        estimated = base_rate * 0.5 + conflict * 0.5
        return min(1.0, max(0.0, estimated))

    def to_dict(self) -> Dict[str, Any]:
        n_errors = sum(self._outcomes) if self._outcomes else 0
        return {
            'error_rate': round(n_errors / max(1, len(self._outcomes)), 3),
            'sample_size': len(self._outcomes),
        }


class CognitiveEffortAllocator:
    """
    Determines how much cognitive effort to invest.

    Shenhav et al. (2013): Expected Value of Control (EVC)
    EVC = Reward * P(correct|effort) - Cost(effort)
    """

    def __init__(self, effort_budget: float = 1.0):
        self.effort_budget = effort_budget
        self._current_effort = 0.5
        self._effort_history = deque(maxlen=50)

    def allocate_effort(
        self,
        conflict: float,
        error_likelihood: float,
        reward_magnitude: float = 0.5,
    ) -> float:
        """
        Determine effort allocation based on conflict and error risk.

        Args:
            conflict: Current conflict level
            error_likelihood: Estimated error probability
            reward_magnitude: How much reward is at stake

        Returns:
            Effort level to allocate [0, 1]
        """
        # EVC: invest more effort when conflict is high and reward matters
        need = conflict * 0.4 + error_likelihood * 0.3 + reward_magnitude * 0.3
        effort = min(1.0, max(0.0, need))

        # Budget constraint
        effort = min(effort, self.effort_budget)

        self._current_effort = effort
        self._effort_history.append(effort)
        return effort

    def get_avg_effort(self) -> float:
        if not self._effort_history:
            return 0.5
        return float(np.mean(list(self._effort_history)))

    @property
    def current_effort(self) -> float:
        return self._current_effort


class AutonomicRegulator:
    """
    ACC link to autonomic nervous system.

    The ACC influences arousal through connections to
    brainstem autonomic centers (locus coeruleus, etc.).
    """

    def __init__(self, gain: float = 0.5):
        self.gain = gain

    def compute_arousal_adjustment(self, conflict: float, error_likelihood: float) -> float:
        """
        Compute arousal adjustment based on ACC state.

        Returns:
            Arousal adjustment [-1, 1] (positive = increase arousal)
        """
        # High conflict/errors increase arousal
        adjustment = self.gain * (conflict + error_likelihood - 1.0)
        return max(-1.0, min(1.0, adjustment))


class AnteriorCingulateCortex:
    """
    Complete Anterior Cingulate Cortex module.

    Functions:
    1. Conflict monitoring (response competition)
    2. Error likelihood estimation
    3. Cognitive effort allocation (EVC)
    4. Autonomic arousal regulation
    """

    def __init__(
        self,
        n_channels: int = 4,
        conflict_threshold: float = 0.5,
        effort_budget: float = 1.0,
    ):
        self.conflict_monitor = ConflictMonitor(n_channels, conflict_threshold)
        self.error_estimator = ErrorLikelihoodEstimator()
        self.effort_allocator = CognitiveEffortAllocator(effort_budget)
        self.autonomic = AutonomicRegulator()
        self._stats = ACCStats()

    def process(
        self,
        response_activations: np.ndarray,
        reward_magnitude: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Full ACC processing cycle.

        Args:
            response_activations: Activation of competing responses
            reward_magnitude: How important the current decision is

        Returns:
            Dict with conflict, error_likelihood, effort, control_signal, arousal_adjustment
        """
        conflict = self.conflict_monitor.compute_conflict(response_activations)
        error_likelihood = self.error_estimator.estimate_error_likelihood(conflict)
        effort = self.effort_allocator.allocate_effort(
            conflict, error_likelihood, reward_magnitude
        )
        arousal_adj = self.autonomic.compute_arousal_adjustment(conflict, error_likelihood)

        # Control signal: higher when more control is needed
        control_signal = effort

        self._stats.total_conflict_checks += 1
        if self.conflict_monitor.is_high_conflict(conflict):
            self._stats.total_high_conflict += 1
        self._stats.avg_conflict = self.conflict_monitor.get_avg_conflict()
        self._stats.avg_effort_allocated = self.effort_allocator.get_avg_effort()
        self._stats.current_control_signal = control_signal

        return {
            'conflict': conflict,
            'error_likelihood': error_likelihood,
            'effort': effort,
            'control_signal': control_signal,
            'arousal_adjustment': arousal_adj,
            'is_high_conflict': self.conflict_monitor.is_high_conflict(conflict),
        }

    def record_outcome(self, was_error: bool):
        """Record outcome for error likelihood estimation."""
        self.error_estimator.record_outcome(was_error)
        if was_error:
            self._stats.total_errors_detected += 1

    def expected_value_of_control(
        self,
        control_intensity: float,
        expected_reward: float,
        expected_cost: float,
    ) -> Dict[str, float]:
        """
        Expected Value of Control (EVC) computation (Shenhav et al., 2013).

        dACC computes whether it's worth investing cognitive control:
        EVC = Expected(Reward | Control) - Cost(Control)
        This determines how much effort/attention to allocate to a task.

        Args:
            control_intensity: How much control to invest [0, 1]
            expected_reward: Expected reward if control succeeds [0, 1]
            expected_cost: Cognitive/metabolic cost of control [0, 1]

        Returns:
            Dict with evc, optimal_control, should_engage
        """
        # Reward probability increases with control (diminishing returns)
        reward_prob = 1.0 - np.exp(-3.0 * control_intensity)

        # Expected benefit = reward * probability of success
        expected_benefit = expected_reward * float(reward_prob)

        # Cost scales superlinearly with intensity (fatigue)
        control_cost = expected_cost * control_intensity ** 1.5

        # EVC = benefit - cost
        evc = expected_benefit - control_cost

        # Optimal control: find the level that maximizes EVC
        # Analytical approximation for this cost structure
        if expected_reward > 0 and expected_cost > 0:
            ratio = expected_reward / expected_cost
            optimal = min(1.0, max(0.1, 0.3 + ratio * 0.2))
        else:
            optimal = 0.5

        return {
            'evc': round(evc, 4),
            'expected_benefit': round(expected_benefit, 4),
            'control_cost': round(control_cost, 4),
            'optimal_control': round(optimal, 4),
            'should_engage': evc > 0.05,
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'conflict': self.conflict_monitor.to_dict(),
            'errors': self.error_estimator.to_dict(),
        }

    def get_stats(self) -> ACCStats:
        return self._stats

    def reset(self):
        self._stats = ACCStats()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'AnteriorCingulateCortex':
        acc = config.get('anterior_cingulate', {})
        return cls(
            n_channels=acc.get('n_channels', 4),
            conflict_threshold=acc.get('conflict_threshold', 0.5),
            effort_budget=acc.get('effort_budget', 1.0),
        )
