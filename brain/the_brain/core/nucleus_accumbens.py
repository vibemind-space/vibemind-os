"""
Nucleus Accumbens Module - Phase C2

Explicit reward gateway extending basal ganglia with dedicated
reward processing, approach/avoidance balance, and effort computation.

Neuroscience basis:
- Shell: Motivational salience, reward prediction
- Core: Motor interface for goal-directed behavior
- Dopamine D1/D2 receptors: Approach vs. avoidance
- Effort-based decision making (Salamone et al., 2007)

Integration:
- Input: VTA dopamine, PFC value signals, Amygdala valence
- Output: Go/NoGo signals to ventral pallidum, drive to Basal Ganglia
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.nucleus_accumbens')


@dataclass
class NAccStats:
    """Nucleus accumbens statistics."""
    total_evaluations: int = 0
    total_approach: int = 0
    total_avoid: int = 0
    avg_reward_signal: float = 0.0
    avg_effort_cost: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_evaluations': self.total_evaluations,
            'total_approach': self.total_approach,
            'total_avoid': self.total_avoid,
            'avg_reward_signal': round(self.avg_reward_signal, 3),
            'avg_effort_cost': round(self.avg_effort_cost, 3),
        }


class RewardGate:
    """
    Processes dopamine reward signals and gates motivational output.

    D1 receptors: Activated by phasic DA, drives Go (approach)
    D2 receptors: Tonically inhibited by DA, drives NoGo (avoid)
    """

    def __init__(self, baseline_da: float = 0.5):
        self.baseline_da = baseline_da
        self._current_da = baseline_da
        self._reward_history = deque(maxlen=100)

    def process_dopamine(self, dopamine_level: float) -> Tuple[float, float]:
        """
        Process dopamine signal into Go and NoGo drives.

        Args:
            dopamine_level: Current dopamine [0, 1]

        Returns:
            (go_drive, nogo_drive) both in [0, 1]
        """
        da = max(0.0, min(1.0, dopamine_level))
        self._current_da = da
        self._reward_history.append(da)

        # D1 (Go): increases with DA
        go_drive = da

        # D2 (NoGo): decreases with DA
        nogo_drive = 1.0 - da

        return go_drive, nogo_drive

    @property
    def current_dopamine(self) -> float:
        return self._current_da

    def get_avg_reward(self) -> float:
        if not self._reward_history:
            return self.baseline_da
        return float(np.mean(list(self._reward_history)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'current_da': round(self._current_da, 3),
            'avg_reward': round(self.get_avg_reward(), 3),
        }


class ApproachAvoidanceBalance:
    """
    Computes the balance between approach and avoidance motivation.
    """

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold

    def evaluate(
        self,
        reward_prediction: float,
        threat_level: float,
        effort_cost: float,
    ) -> Tuple[str, float]:
        """
        Evaluate whether to approach or avoid.

        Args:
            reward_prediction: Expected reward [0, 1]
            threat_level: Perceived threat [0, 1]
            effort_cost: Effort required [0, 1]

        Returns:
            ("approach" or "avoid", net_value)
        """
        benefit = reward_prediction
        cost = 0.5 * threat_level + 0.5 * effort_cost
        net_value = benefit - cost

        if net_value > self.threshold - 0.5:
            return "approach", net_value
        else:
            return "avoid", net_value


class EffortComputation:
    """
    Computes effort costs for actions.

    Salamone et al. (2007): NAcc dopamine depletion makes animals
    less willing to work for large rewards, preferring smaller
    free rewards.
    """

    def __init__(self):
        self._effort_history = deque(maxlen=50)

    def compute_effort(self, action_complexity: float, current_energy: float = 1.0) -> float:
        """
        Compute subjective effort cost.

        Args:
            action_complexity: How complex the action is [0, 1]
            current_energy: Current energy level [0, 1]

        Returns:
            Perceived effort cost [0, 1]
        """
        # Effort is higher when energy is low
        energy_penalty = 1.0 - current_energy
        effort = action_complexity * (1.0 + energy_penalty)
        effort = min(1.0, max(0.0, effort))
        self._effort_history.append(effort)
        return effort

    def get_avg_effort(self) -> float:
        if not self._effort_history:
            return 0.0
        return float(np.mean(list(self._effort_history)))


class NucleusAccumbens:
    """
    Complete Nucleus Accumbens module.

    Functions:
    1. Reward gating (dopamine D1/D2)
    2. Approach/avoidance evaluation
    3. Effort-based cost computation
    4. Motivational output to motor system
    """

    def __init__(self, baseline_da: float = 0.5, approach_threshold: float = 0.5):
        self.reward_gate = RewardGate(baseline_da)
        self.approach_avoidance = ApproachAvoidanceBalance(approach_threshold)
        self.effort_computation = EffortComputation()
        self._stats = NAccStats()

    def evaluate(
        self,
        dopamine: float = 0.5,
        reward_prediction: float = 0.5,
        threat: float = 0.0,
        action_complexity: float = 0.3,
        energy: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Full NAcc evaluation cycle.

        Returns:
            Dict with go/nogo drives, approach/avoid decision, effort cost
        """
        go, nogo = self.reward_gate.process_dopamine(dopamine)
        effort = self.effort_computation.compute_effort(action_complexity, energy)
        decision, net_value = self.approach_avoidance.evaluate(
            reward_prediction, threat, effort
        )

        self._stats.total_evaluations += 1
        if decision == "approach":
            self._stats.total_approach += 1
        else:
            self._stats.total_avoid += 1
        self._stats.avg_reward_signal = self.reward_gate.get_avg_reward()
        self._stats.avg_effort_cost = self.effort_computation.get_avg_effort()

        return {
            'go_drive': go,
            'nogo_drive': nogo,
            'decision': decision,
            'net_value': net_value,
            'effort_cost': effort,
            'dopamine': dopamine,
        }

    def effort_reward_tradeoff(
        self,
        reward_magnitude: float,
        effort_required: float,
        dopamine: float = 0.5,
    ) -> Dict[str, float]:
        """
        Effort-reward cost-benefit computation (Salamone et al., 2007).

        NAcc DA doesn't encode pleasure — it encodes willingness to exert
        effort for reward. Low DA in NAcc = still likes rewards but unwilling
        to work for them. This is the "wanting" vs "effort cost" computation.

        Args:
            reward_magnitude: Expected reward size [0, 1]
            effort_required: Effort needed to obtain reward [0, 1]
            dopamine: Current DA level in NAcc [0, 1]

        Returns:
            Dict with net_value, willingness, is_worth_effort
        """
        # DA scales effort tolerance: high DA = willing to work harder
        effort_tolerance = 0.3 + dopamine * 0.7
        subjective_effort_cost = effort_required / max(0.01, effort_tolerance)

        # Net value = reward - discounted effort cost
        net_value = reward_magnitude - subjective_effort_cost * 0.5
        net_value = max(-1.0, min(1.0, net_value))

        # Willingness to act: sigmoid of net value
        willingness = 1.0 / (1.0 + np.exp(-5.0 * net_value))

        return {
            'net_value': round(net_value, 4),
            'willingness': round(float(willingness), 4),
            'effort_tolerance': round(effort_tolerance, 4),
            'is_worth_effort': net_value > 0.0,
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'reward_gate': self.reward_gate.to_dict(),
        }

    def get_stats(self) -> NAccStats:
        return self._stats

    def reset(self):
        self._stats = NAccStats()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'NucleusAccumbens':
        nacc = config.get('nucleus_accumbens', {})
        return cls(
            baseline_da=nacc.get('baseline_dopamine', 0.5),
            approach_threshold=nacc.get('approach_threshold', 0.5),
        )
