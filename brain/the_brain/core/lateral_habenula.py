"""
Lateral Habenula (LHb) Module - Phase D5

The lateral habenula is an epithalamic nucleus known as the brain's
"anti-reward center" or "disappointment center." It is activated by
negative outcomes, punishment, and reward omission, and INHIBITS
both VTA dopamine and raphe serotonin neurons.

Neuroscience basis:
- Matsumoto & Hikosaka (2007): LHb neurons encode negative RPE
  (mirror image of VTA DA neurons)
- Proulx et al. (2014): LHb overactivation linked to depression
- Li et al. (2019): NMDA burst firing in LHb drives depression-like behavior

Key functions:
- Negative RPE amplification (disappointment signal)
- Punishment/aversive learning signal
- Inhibits VTA DA neurons (suppresses reward)
- Inhibits DRN 5-HT neurons (reduces patience/mood)
- Drives behavioral avoidance and "stop doing this" signal
- Depression-linked when chronically overactive

Integration:
- Input: PFC (expectations), basal ganglia (action outcomes),
         amygdala (valence), NAc (reward mismatch)
- Output: LHb -> VTA (inhibits DA), LHb -> DRN (inhibits 5-HT)
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.lateral_habenula')


@dataclass
class LHbStats:
    """Lateral habenula statistics."""
    total_evaluations: int = 0
    total_disappointments: int = 0
    total_punishments: int = 0
    total_reward_omissions: int = 0
    avg_anti_reward: float = 0.0
    avg_vta_inhibition: float = 0.0
    avg_drn_inhibition: float = 0.0
    chronic_activation: float = 0.0  # Depression risk indicator

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_evaluations': self.total_evaluations,
            'total_disappointments': self.total_disappointments,
            'total_punishments': self.total_punishments,
            'total_reward_omissions': self.total_reward_omissions,
            'avg_anti_reward': round(self.avg_anti_reward, 3),
            'avg_vta_inhibition': round(self.avg_vta_inhibition, 3),
            'avg_drn_inhibition': round(self.avg_drn_inhibition, 3),
            'chronic_activation': round(self.chronic_activation, 3),
        }


class AntiRewardSignal:
    """
    Computes the anti-reward (disappointment) signal.

    Matsumoto & Hikosaka (2007): LHb neurons fire when:
    - Expected reward is omitted
    - Punishment is received
    - Outcome is worse than expected (negative RPE)

    The anti-reward signal is the mirror image of VTA's RPE.
    """

    def __init__(self, sensitivity: float = 1.0, omission_weight: float = 0.8):
        self.sensitivity = sensitivity
        self.omission_weight = omission_weight
        self._signal_history = deque(maxlen=200)

    def compute(
        self,
        expected_reward: float,
        actual_reward: float,
        punishment: float = 0.0,
    ) -> float:
        """
        Compute anti-reward signal.

        Args:
            expected_reward: What was expected [0, 1]
            actual_reward: What was received [0, 1]
            punishment: Direct punishment signal [0, 1]

        Returns:
            Anti-reward signal [0, 1], higher = more disappointment
        """
        # Disappointment: expected > actual
        disappointment = max(0.0, expected_reward - actual_reward)

        # Reward omission: expected reward but got nothing
        omission = expected_reward * (1.0 - actual_reward) * self.omission_weight

        # Total anti-reward signal
        signal = (disappointment * 0.4 + omission * 0.3 + punishment * 0.3) * self.sensitivity
        signal = min(1.0, max(0.0, signal))

        self._signal_history.append(signal)
        return signal

    def get_avg_signal(self) -> float:
        if not self._signal_history:
            return 0.0
        return float(np.mean(list(self._signal_history)))

    def get_chronic_level(self) -> float:
        """
        Get chronic activation level.

        Sustained high anti-reward signal is linked to depression.
        """
        if len(self._signal_history) < 10:
            return 0.0
        recent = list(self._signal_history)[-50:]
        return float(np.mean(recent))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'avg_signal': round(self.get_avg_signal(), 3),
            'chronic_level': round(self.get_chronic_level(), 3),
        }


class AvoidanceLearning:
    """
    Drives avoidance learning from negative outcomes.

    When the LHb is active, it teaches the brain to AVOID
    the current action/stimulus combination that led to
    disappointment or punishment.
    """

    def __init__(self, learning_rate: float = 0.1):
        self.learning_rate = learning_rate
        # Maps action/stimulus -> avoidance strength
        self._avoidance_memory: Dict[str, float] = {}

    def learn_avoidance(self, action_id: str, anti_reward: float):
        """
        Strengthen avoidance for a given action.

        Args:
            action_id: Identifier for the action/stimulus
            anti_reward: Anti-reward signal strength [0, 1]
        """
        current = self._avoidance_memory.get(action_id, 0.0)
        update = anti_reward * self.learning_rate
        new_value = min(1.0, current + update)
        self._avoidance_memory[action_id] = new_value

    def get_avoidance(self, action_id: str) -> float:
        """Get avoidance strength for an action."""
        return self._avoidance_memory.get(action_id, 0.0)

    def decay_avoidance(self, decay_rate: float = 0.01):
        """Slowly decay all avoidance associations (forgetting)."""
        for key in list(self._avoidance_memory.keys()):
            self._avoidance_memory[key] *= (1.0 - decay_rate)
            if self._avoidance_memory[key] < 0.01:
                del self._avoidance_memory[key]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'n_avoided_actions': len(self._avoidance_memory),
            'max_avoidance': round(
                max(self._avoidance_memory.values()) if self._avoidance_memory else 0.0,
                3,
            ),
        }


class LateralHabenula:
    """
    Complete Lateral Habenula module.

    Functions:
    1. Anti-reward signal computation (disappointment)
    2. VTA dopamine inhibition
    3. DRN serotonin inhibition
    4. Avoidance learning
    5. Depression risk monitoring (chronic overactivation)

    This is the brain's "disappointment center" — it balances
    VTA's optimism with realistic assessment of negative outcomes.
    """

    def __init__(
        self,
        sensitivity: float = 1.0,
        omission_weight: float = 0.8,
        vta_inhibition_gain: float = 0.7,
        drn_inhibition_gain: float = 0.5,
        avoidance_learning_rate: float = 0.1,
        depression_threshold: float = 0.7,
    ):
        self.anti_reward = AntiRewardSignal(sensitivity, omission_weight)
        self.avoidance = AvoidanceLearning(avoidance_learning_rate)
        self._vta_inhibition_gain = vta_inhibition_gain
        self._drn_inhibition_gain = drn_inhibition_gain
        self._depression_threshold = depression_threshold
        self._stats = LHbStats()
        self._vta_inhibition = 0.0
        self._drn_inhibition = 0.0

    def process(
        self,
        expected_reward: float,
        actual_reward: float,
        punishment: float = 0.0,
        action_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Full LHb processing cycle.

        1. Compute anti-reward signal
        2. Generate inhibitory outputs to VTA and DRN
        3. Update avoidance learning
        4. Monitor chronic activation (depression risk)

        Args:
            expected_reward: What was expected [0, 1]
            actual_reward: What was received [0, 1]
            punishment: Direct punishment [0, 1]
            action_id: Optional action identifier for avoidance learning

        Returns:
            Dict with anti_reward, vta_inhibition, drn_inhibition, etc.
        """
        # 1. Anti-reward signal
        anti_reward = self.anti_reward.compute(expected_reward, actual_reward, punishment)

        # 2. Inhibitory outputs
        self._vta_inhibition = anti_reward * self._vta_inhibition_gain
        self._drn_inhibition = anti_reward * self._drn_inhibition_gain

        # 3. Avoidance learning
        if action_id and anti_reward > 0.1:
            self.avoidance.learn_avoidance(action_id, anti_reward)

        # Periodic decay of avoidance associations
        if self._stats.total_evaluations % 50 == 0:
            self.avoidance.decay_avoidance()

        # 4. Chronic activation monitoring
        chronic = self.anti_reward.get_chronic_level()
        is_depressive = chronic > self._depression_threshold

        # Update stats
        self._stats.total_evaluations += 1
        if anti_reward > 0.3:
            self._stats.total_disappointments += 1
        if punishment > 0.3:
            self._stats.total_punishments += 1
        if expected_reward > 0.3 and actual_reward < 0.1:
            self._stats.total_reward_omissions += 1
        self._stats.avg_anti_reward = self.anti_reward.get_avg_signal()
        self._stats.avg_vta_inhibition = self._vta_inhibition
        self._stats.avg_drn_inhibition = self._drn_inhibition
        self._stats.chronic_activation = chronic

        return {
            'anti_reward': round(anti_reward, 3),
            'vta_inhibition': round(self._vta_inhibition, 3),
            'drn_inhibition': round(self._drn_inhibition, 3),
            'chronic_activation': round(chronic, 3),
            'is_depressive': is_depressive,
            'avoidance': self.avoidance.get_avoidance(action_id) if action_id else 0.0,
        }


    def negative_pe_routing(self, pe_value: float) -> Dict[str, float]:
        """
        Route negative prediction errors to downstream targets.

        LHb receives negative RPE and distributes inhibitory signals:
        - VTA DA neurons: suppressed (less reward seeking)
        - Raphe 5-HT neurons: excited (more patience/waiting)

        Matsumoto & Hikosaka (2007): LHb fires proportionally to
        negative RPE magnitude.

        Args:
            pe_value: Prediction error from VTA [-1, 1]
                      Negative values activate LHb

        Returns:
            Dict with vta_suppression, raphe_excitation, lhb_activation
        """
        # LHb is activated by negative PE (worse than expected)
        lhb_activation = max(0.0, -pe_value)  # Only negative PE activates

        # VTA suppression: LHb -> RMTg -> VTA DA inhibition
        vta_suppression = lhb_activation * self._vta_inhibition_gain
        vta_suppression = min(1.0, vta_suppression)

        # Raphe excitation: LHb disinhibits raphe (promotes patience after disappointment)
        # When things go badly, increase 5-HT to promote waiting/patience
        raphe_excitation = lhb_activation * 0.4  # Moderate excitation
        raphe_excitation = min(1.0, raphe_excitation)

        return {
            'lhb_activation': round(lhb_activation, 4),
            'vta_suppression': round(vta_suppression, 4),
            'raphe_excitation': round(raphe_excitation, 4),
            'pe_was_negative': pe_value < -0.05,
        }

    def compute_disappointment_from_rpe(self, rpe: float) -> Dict[str, float]:
        """
        Compute disappointment signal directly from RPE (VTA input).

        Rather than comparing expected vs actual reward separately,
        this uses the VTA's already-computed RPE signal to drive LHb.
        This is more biologically accurate as LHb receives RPE-coded
        input from basal ganglia output.

        Args:
            rpe: Reward prediction error from VTA [-1, 1]

        Returns:
            Dict with disappointment level and downstream signals
        """
        # Disappointment is the negative part of RPE
        disappointment = max(0.0, -rpe)

        # Scale by sensitivity
        anti_reward = disappointment * self.anti_reward.sensitivity
        anti_reward = min(1.0, anti_reward)

        # Compute inhibitory outputs using anti-reward signal
        vta_inh = anti_reward * self._vta_inhibition_gain
        drn_inh = anti_reward * self._drn_inhibition_gain

        # Track in history
        self.anti_reward._signal_history.append(anti_reward)

        return {
            'disappointment': round(disappointment, 4),
            'anti_reward': round(anti_reward, 4),
            'vta_inhibition': round(vta_inh, 4),
            'drn_inhibition': round(drn_inh, 4),
        }

    def learned_helplessness_detector(self) -> Dict[str, Any]:
        """
        Detect learned helplessness from chronic LHb overactivation.

        Li et al. (2019): Sustained LHb NMDA burst firing drives
        depression-like behavior. When the agent consistently experiences
        negative outcomes with no controllable escape, LHb becomes
        chronically active, suppressing DA/5-HT and producing helplessness.

        Returns:
            Dict with helplessness_score, should_intervene, chronic_level
        """
        chronic = self.anti_reward.get_chronic_level()
        total_evals = max(1, self._stats.total_evaluations)
        disappointment_rate = self._stats.total_disappointments / total_evals

        # Helplessness = chronic activation * disappointment frequency
        helplessness = chronic * 0.6 + disappointment_rate * 0.4
        helplessness = min(1.0, helplessness)

        # Intervention needed if helplessness is high
        should_intervene = helplessness > 0.65

        return {
            'helplessness_score': round(helplessness, 4),
            'chronic_activation': round(chronic, 4),
            'disappointment_rate': round(disappointment_rate, 4),
            'should_intervene': should_intervene,
            'is_depressive': chronic > self._depression_threshold,
        }

    def get_avoidance_for(self, action_id: str) -> float:
        """Get avoidance signal for a specific action."""
        return self.avoidance.get_avoidance(action_id)

    @property
    def vta_inhibition(self) -> float:
        return self._vta_inhibition

    @property
    def drn_inhibition(self) -> float:
        return self._drn_inhibition

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'anti_reward': self.anti_reward.to_dict(),
            'avoidance': self.avoidance.to_dict(),
        }

    def get_stats(self) -> LHbStats:
        return self._stats

    def reset(self):
        self._stats = LHbStats()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'LateralHabenula':
        cfg = config.get('lateral_habenula', {})
        return cls(
            sensitivity=cfg.get('sensitivity', 1.0),
            omission_weight=cfg.get('omission_weight', 0.8),
            vta_inhibition_gain=cfg.get('vta_inhibition_gain', 0.7),
            drn_inhibition_gain=cfg.get('drn_inhibition_gain', 0.5),
            avoidance_learning_rate=cfg.get('avoidance_learning_rate', 0.1),
            depression_threshold=cfg.get('depression_threshold', 0.7),
        )
