"""
Neuromodulation System (PHASE 6)

Implements biologically-inspired neuromodulatory systems:

1. Dopamine System (Reward & Motivation):
   - Increases with success and positive outcomes
   - Boosts exploration and learning rates
   - Enhances motivation and reward prediction
   - Implements reward prediction error (RPE)

2. Serotonin System (Mood & Patience):
   - Increases with consistent success
   - Stabilizes behavior, reduces impulsivity
   - Promotes patience and sustained effort
   - Associated with well-being

3. Norepinephrine System (Arousal & Urgency):
   - Increases with task urgency or threat
   - Boosts attention focus and response speed
   - Associated with stress response
   - Enhances alertness

Effects on Cognition:
- Learning rate modulation
- Exploration/exploitation balance
- Attention focus strength
- Decision confidence thresholds
- Response speed and urgency

Based on neuroscience research:
- Dopamine: Reward prediction error (Schultz et al., 1997)
- Serotonin: Behavioral inhibition (Dayan & Huys, 2009)
- Norepinephrine: Arousal and attention (Sara, 2009)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque


@dataclass
class NeuromodulatorLevels:
    """
    Current levels of neuromodulators (0-1 range)
    """
    dopamine: float = 0.5  # Reward/motivation
    serotonin: float = 0.5  # Mood/patience
    norepinephrine: float = 0.5  # Arousal/urgency

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'dopamine': float(self.dopamine),
            'serotonin': float(self.serotonin),
            'norepinephrine': float(self.norepinephrine)
        }

    def clip(self, min_val: float = 0.0, max_val: float = 1.0):
        """Clip all values to valid range"""
        self.dopamine = np.clip(self.dopamine, min_val, max_val)
        self.serotonin = np.clip(self.serotonin, min_val, max_val)
        self.norepinephrine = np.clip(self.norepinephrine, min_val, max_val)


@dataclass
class NeuromodulatorEffects:
    """
    Effects of neuromodulators on cognitive parameters
    """
    learning_rate_multiplier: float = 1.0
    exploration_boost: float = 0.0
    attention_focus_multiplier: float = 1.0
    confidence_threshold_delta: float = 0.0
    response_urgency: float = 0.5

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'learning_rate_multiplier': float(self.learning_rate_multiplier),
            'exploration_boost': float(self.exploration_boost),
            'attention_focus_multiplier': float(self.attention_focus_multiplier),
            'confidence_threshold_delta': float(self.confidence_threshold_delta),
            'response_urgency': float(self.response_urgency)
        }


class NeuromodulationSystem:
    """
    Neuromodulation system that dynamically adjusts brain state

    Key features:
    - Dopamine: Reward-based modulation
    - Serotonin: Mood and stability modulation
    - Norepinephrine: Arousal and urgency modulation
    - Dynamic parameter adjustment based on neuromodulator levels
    """

    @classmethod
    def from_yaml(cls, yaml_config: dict) -> 'NeuromodulationSystem':
        """Create NeuromodulationSystem from YAML config dict (P5.66)."""
        nm = yaml_config.get('neuromodulation', {})
        return cls(
            baseline_dopamine=nm.get('baseline_dopamine', 0.5),
            baseline_serotonin=nm.get('baseline_serotonin', 0.5),
            baseline_norepinephrine=nm.get('baseline_norepinephrine', 0.5),
            decay_rate=nm.get('decay_rate', 0.05),
            sensitivity=nm.get('sensitivity', 1.0),
            history_size=nm.get('history_size', 50),
        )

    def __init__(
        self,
        baseline_dopamine: float = 0.5,
        baseline_serotonin: float = 0.5,
        baseline_norepinephrine: float = 0.5,
        decay_rate: float = 0.05,  # How fast neuromodulators return to baseline
        sensitivity: float = 1.0,  # Overall sensitivity to modulation
        history_size: int = 50
    ):
        """
        Initialize neuromodulation system

        Args:
            baseline_dopamine: Baseline dopamine level (0-1)
            baseline_serotonin: Baseline serotonin level (0-1)
            baseline_norepinephrine: Baseline norepinephrine level (0-1)
            decay_rate: Rate at which neuromodulators return to baseline
            sensitivity: Overall sensitivity to neuromodulation effects
            history_size: Size of history buffer
        """
        # Baseline levels
        self.baseline_dopamine = baseline_dopamine
        self.baseline_serotonin = baseline_serotonin
        self.baseline_norepinephrine = baseline_norepinephrine

        # Current levels
        self.levels = NeuromodulatorLevels(
            dopamine=baseline_dopamine,
            serotonin=baseline_serotonin,
            norepinephrine=baseline_norepinephrine
        )

        # Parameters
        self.decay_rate = decay_rate
        self.sensitivity = sensitivity

        # History
        self.level_history: deque = deque(maxlen=history_size)

        # Reward prediction
        self.expected_reward = 0.5
        self.reward_history: deque = deque(maxlen=20)

        # Statistics
        self.total_updates = 0
        self.reward_prediction_errors: List[float] = []

    def update_dopamine(
        self,
        reward: float,
        expected_reward: Optional[float] = None
    ) -> float:
        """
        Update dopamine based on reward prediction error

        Args:
            reward: Actual reward (0-1, where 1=success, 0=failure)
            expected_reward: Expected reward (uses stored if None)

        Returns:
            Reward prediction error (RPE)
        """
        if expected_reward is None:
            expected_reward = self.expected_reward

        # Compute reward prediction error
        rpe = reward - expected_reward

        # Update dopamine based on RPE
        # Positive RPE → dopamine increase
        # Negative RPE → dopamine decrease
        dopamine_change = 0.2 * rpe * self.sensitivity

        self.levels.dopamine += dopamine_change

        # Update expected reward (learning)
        alpha = 0.1  # Learning rate for reward prediction
        self.expected_reward = expected_reward + alpha * rpe

        # Store RPE
        self.reward_prediction_errors.append(rpe)
        self.reward_history.append(reward)

        return rpe

    def update_serotonin(
        self,
        recent_success_rate: float,
        consistency: float = 0.5
    ):
        """
        Update serotonin based on consistent success

        Args:
            recent_success_rate: Recent success rate (0-1)
            consistency: Consistency of outcomes (0-1)
        """
        # High success rate + high consistency → increased serotonin
        target_serotonin = 0.3 + 0.4 * recent_success_rate + 0.3 * consistency

        # Gradual update toward target
        change = 0.1 * (target_serotonin - self.levels.serotonin) * self.sensitivity
        self.levels.serotonin += change

    def update_norepinephrine(
        self,
        urgency: float = 0.5,
        threat: float = 0.0,
        complexity: float = 0.5
    ):
        """
        Update norepinephrine based on urgency and threat

        Args:
            urgency: Task urgency (0-1)
            threat: Threat level (0-1)
            complexity: Task complexity (0-1)
        """
        # High urgency or threat → increased norepinephrine
        # High complexity also requires heightened arousal
        arousal_demand = 0.4 * urgency + 0.4 * threat + 0.2 * complexity

        # Update norepinephrine toward arousal demand
        change = 0.15 * (arousal_demand - self.levels.norepinephrine) * self.sensitivity
        self.levels.norepinephrine += change

    def apply_decay(self):
        """
        Apply decay toward baseline levels (homeostasis)
        """
        # Dopamine decay
        dopamine_diff = self.baseline_dopamine - self.levels.dopamine
        self.levels.dopamine += self.decay_rate * dopamine_diff

        # Serotonin decay
        serotonin_diff = self.baseline_serotonin - self.levels.serotonin
        self.levels.serotonin += self.decay_rate * serotonin_diff

        # Norepinephrine decay
        norepinephrine_diff = self.baseline_norepinephrine - self.levels.norepinephrine
        self.levels.norepinephrine += self.decay_rate * norepinephrine_diff

        # Clip to valid range
        self.levels.clip()

    def compute_effects(self) -> NeuromodulatorEffects:
        """
        Compute cognitive effects based on current neuromodulator levels

        Returns:
            NeuromodulatorEffects with parameter adjustments
        """
        effects = NeuromodulatorEffects()

        # === DOPAMINE EFFECTS ===
        # High dopamine → increased learning rate and exploration
        dopamine_deviation = self.levels.dopamine - self.baseline_dopamine
        effects.learning_rate_multiplier = 1.0 + 0.5 * dopamine_deviation
        effects.exploration_boost = 0.2 * dopamine_deviation

        # === SEROTONIN EFFECTS ===
        # High serotonin → increased confidence threshold (more patient)
        # Low serotonin → decreased confidence threshold (more impulsive)
        serotonin_deviation = self.levels.serotonin - self.baseline_serotonin
        effects.confidence_threshold_delta = 0.1 * serotonin_deviation

        # === NOREPINEPHRINE EFFECTS ===
        # High norepinephrine → increased attention focus and response urgency
        norepinephrine_deviation = self.levels.norepinephrine - self.baseline_norepinephrine
        effects.attention_focus_multiplier = 1.0 + 0.3 * norepinephrine_deviation
        effects.response_urgency = 0.5 + 0.5 * self.levels.norepinephrine

        return effects

    def update(
        self,
        outcome: str,
        confidence: float = 0.5,
        urgency: float = 0.5,
        threat: float = 0.0,
        complexity: float = 0.5,
        recent_success_rate: float = 0.5
    ) -> NeuromodulatorEffects:
        """
        Complete update of all neuromodulators

        Args:
            outcome: 'success' or 'failure'
            confidence: Confidence in the decision (0-1)
            urgency: Task urgency (0-1)
            threat: Threat level (0-1)
            complexity: Task complexity (0-1)
            recent_success_rate: Recent success rate (0-1)

        Returns:
            NeuromodulatorEffects with parameter adjustments
        """
        # Update dopamine based on reward
        reward = 1.0 if outcome == 'success' else 0.0
        rpe = self.update_dopamine(reward, expected_reward=confidence)

        # Update serotonin based on recent success
        # Estimate consistency from reward history variance
        if len(self.reward_history) > 3:
            consistency = 1.0 - np.std(list(self.reward_history))
        else:
            consistency = 0.5

        self.update_serotonin(recent_success_rate, consistency)

        # Update norepinephrine based on task properties
        self.update_norepinephrine(urgency, threat, complexity)

        # Apply decay toward baseline
        self.apply_decay()

        # Record history
        self.level_history.append(self.levels.to_dict())
        self.total_updates += 1

        # Compute and return effects
        return self.compute_effects()

    def get_state_description(self) -> str:
        """
        Get human-readable description of current neuromodulator state

        Returns:
            String description
        """
        descriptions = []

        # Dopamine state
        if self.levels.dopamine > 0.7:
            descriptions.append("MOTIVATED (high dopamine)")
        elif self.levels.dopamine < 0.3:
            descriptions.append("DEMOTIVATED (low dopamine)")
        else:
            descriptions.append("BALANCED (normal dopamine)")

        # Serotonin state
        if self.levels.serotonin > 0.7:
            descriptions.append("PATIENT (high serotonin)")
        elif self.levels.serotonin < 0.3:
            descriptions.append("IMPULSIVE (low serotonin)")
        else:
            descriptions.append("STABLE (normal serotonin)")

        # Norepinephrine state
        if self.levels.norepinephrine > 0.7:
            descriptions.append("ALERT (high norepinephrine)")
        elif self.levels.norepinephrine < 0.3:
            descriptions.append("RELAXED (low norepinephrine)")
        else:
            descriptions.append("CALM (normal norepinephrine)")

        return " | ".join(descriptions)

    def get_statistics(self) -> Dict:
        """Get neuromodulation statistics"""
        recent_levels = list(self.level_history)[-20:] if self.level_history else []

        if recent_levels:
            avg_dopamine = np.mean([l['dopamine'] for l in recent_levels])
            avg_serotonin = np.mean([l['serotonin'] for l in recent_levels])
            avg_norepinephrine = np.mean([l['norepinephrine'] for l in recent_levels])
        else:
            avg_dopamine = self.levels.dopamine
            avg_serotonin = self.levels.serotonin
            avg_norepinephrine = self.levels.norepinephrine

        # Compute recent RPE statistics
        recent_rpes = self.reward_prediction_errors[-20:] if self.reward_prediction_errors else []
        avg_rpe = np.mean(recent_rpes) if recent_rpes else 0.0
        rpe_std = np.std(recent_rpes) if recent_rpes else 0.0

        return {
            'total_updates': self.total_updates,
            'current_levels': self.levels.to_dict(),
            'current_state': self.get_state_description(),
            'average_levels': {
                'dopamine': float(avg_dopamine),
                'serotonin': float(avg_serotonin),
                'norepinephrine': float(avg_norepinephrine)
            },
            'reward_prediction': {
                'expected_reward': float(self.expected_reward),
                'avg_rpe': float(avg_rpe),
                'rpe_std': float(rpe_std)
            },
            'current_effects': self.compute_effects().to_dict()
        }

    def __repr__(self):
        return (
            f"NeuromodulationSystem("
            f"DA={self.levels.dopamine:.2f}, "
            f"5-HT={self.levels.serotonin:.2f}, "
            f"NE={self.levels.norepinephrine:.2f})"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("NEUROMODULATION SYSTEM (PHASE 6)")
    print("=" * 70)
    print()
    print("This module implements biologically-inspired neuromodulation:")
    print("  - Dopamine: Reward-based modulation (motivation, learning)")
    print("  - Serotonin: Mood and patience modulation (stability)")
    print("  - Norepinephrine: Arousal and urgency modulation (alertness)")
    print()
    print("Neuromodulators dynamically adjust:")
    print("  - Learning rates")
    print("  - Exploration/exploitation balance")
    print("  - Attention focus strength")
    print("  - Decision confidence thresholds")
    print("  - Response urgency")
    print()
    print("To test the complete system, run:")
    print("  python demos/test_neuromodulation.py")
    print()
    print("=" * 70)
