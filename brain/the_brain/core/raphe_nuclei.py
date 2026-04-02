"""
Raphe Nuclei Module - Phase D4

The raphe nuclei are brainstem serotonin (5-HT) producing centers.
Serotonin is the brain's "patience" and "mood baseline" signal,
acting as an opponent to dopamine's "go" signal.

Neuroscience basis:
- Dorsal Raphe Nucleus (DRN): Patience, waiting for delayed rewards,
  impulse inhibition, mood regulation
  (Miyazaki et al., 2014: DRN 5-HT neurons promote patience)
- Median Raphe Nucleus (MRN): Hippocampal theta rhythm modulation,
  memory consolidation, behavioral inhibition

Key functions:
- Patience/impulsivity tradeoff
- Temporal discounting (how much future rewards are devalued)
- Mood baseline regulation
- Behavioral inhibition (stop signal)
- Punishment avoidance learning

Key finding (Miyazaki et al., 2014):
Activation of DRN serotonin neurons promotes patience — animals
wait longer for delayed rewards. Serotonin = opponent to dopamine.
- High 5-HT: Patient, willing to wait, reduced impulsivity
- Low 5-HT: Impulsive, want immediate reward, poor inhibition

Integration:
- Input: PFC (goal state), LHb (negative outcomes), PAG (pain/distress)
- Output: DRN -> cortex (mood), NAc (reward modulation), hippocampus (memory)
         MRN -> hippocampus (theta), septum (theta pacemaker)
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.raphe')


@dataclass
class RapheStats:
    """Raphe nuclei statistics."""
    total_cycles: int = 0
    total_patience_wins: int = 0
    total_impulsive_actions: int = 0
    total_inhibitions: int = 0
    avg_serotonin: float = 0.5
    avg_patience: float = 0.5
    avg_mood: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cycles': self.total_cycles,
            'total_patience_wins': self.total_patience_wins,
            'total_impulsive_actions': self.total_impulsive_actions,
            'total_inhibitions': self.total_inhibitions,
            'avg_serotonin': round(self.avg_serotonin, 3),
            'avg_patience': round(self.avg_patience, 3),
            'avg_mood': round(self.avg_mood, 3),
        }


class DorsalRapheNucleus:
    """
    Dorsal Raphe Nucleus (DRN) — Patience and mood regulation.

    The DRN contains the largest population of serotonin neurons
    projecting to the forebrain. Key roles:
    - Patience: Promotes waiting for delayed but larger rewards
    - Mood: Sets emotional baseline (low 5-HT = depression risk)
    - Impulse control: Inhibits premature action
    - Temporal discounting: Modulates discount factor for future rewards
    """

    def __init__(
        self,
        baseline_5ht: float = 0.5,
        patience_gain: float = 1.0,
        mood_inertia: float = 0.9,
    ):
        self.baseline_5ht = baseline_5ht
        self.patience_gain = patience_gain
        self.mood_inertia = mood_inertia

        self._serotonin_level = baseline_5ht
        self._mood = 0.5  # [0=depressed, 1=positive]
        self._patience = 0.5  # [0=impulsive, 1=very patient]
        self._5ht_history = deque(maxlen=200)
        self._mood_history = deque(maxlen=200)

    def update(
        self,
        reward_rate: float = 0.5,
        punishment: float = 0.0,
        wait_time_remaining: float = 0.0,
        goal_progress: float = 0.5,
    ) -> Dict[str, float]:
        """
        Update DRN state based on inputs.

        Args:
            reward_rate: Recent reward rate [0, 1]
            punishment: Recent punishment/negative outcomes [0, 1]
            wait_time_remaining: How long until expected reward (normalized) [0, 1]
            goal_progress: Progress toward current goal [0, 1]

        Returns:
            Dict with serotonin, patience, mood, discount_factor
        """
        # 5-HT level: increases with positive outcomes, decreases with punishment
        target_5ht = self.baseline_5ht + reward_rate * 0.2 - punishment * 0.3
        target_5ht += goal_progress * 0.1
        target_5ht = max(0.0, min(1.0, target_5ht))

        # Smooth update
        self._serotonin_level = self._serotonin_level * 0.8 + target_5ht * 0.2
        self._5ht_history.append(self._serotonin_level)

        # Patience: directly proportional to 5-HT
        self._patience = self._serotonin_level * self.patience_gain
        self._patience = min(1.0, max(0.0, self._patience))

        # Mood: slow-moving, strongly influenced by 5-HT
        target_mood = self._serotonin_level * 0.6 + (1.0 - punishment) * 0.2 + goal_progress * 0.2
        self._mood = self._mood * self.mood_inertia + target_mood * (1 - self.mood_inertia)
        self._mood = max(0.0, min(1.0, self._mood))
        self._mood_history.append(self._mood)

        # Temporal discount factor: high 5-HT = high discount (patient)
        # γ = 0.5 + 0.45 * 5-HT (range 0.5 to 0.95)
        discount_factor = 0.5 + 0.45 * self._serotonin_level

        return {
            'serotonin': self._serotonin_level,
            'patience': self._patience,
            'mood': self._mood,
            'discount_factor': discount_factor,
        }

    def should_wait(self, immediate_reward: float, delayed_reward: float, delay: float) -> bool:
        """
        Decide whether to wait for a delayed reward.

        Uses temporal discounting modulated by 5-HT level.

        Args:
            immediate_reward: Value of immediate option [0, 1]
            delayed_reward: Value of delayed option [0, 1]
            delay: Delay period (normalized) [0, 1]

        Returns:
            True if the agent should wait for delayed reward
        """
        discount = 0.5 + 0.45 * self._serotonin_level
        discounted_delayed = delayed_reward * (discount ** delay)
        return discounted_delayed > immediate_reward

    @property
    def serotonin(self) -> float:
        return self._serotonin_level

    @property
    def mood(self) -> float:
        return self._mood

    @property
    def patience(self) -> float:
        return self._patience

    def to_dict(self) -> Dict[str, Any]:
        return {
            'serotonin': round(self._serotonin_level, 3),
            'patience': round(self._patience, 3),
            'mood': round(self._mood, 3),
        }


class MedianRapheNucleus:
    """
    Median Raphe Nucleus (MRN) — Theta rhythm and memory.

    The MRN projects to hippocampus and septum, modulating
    theta oscillations (4-8 Hz) critical for:
    - Memory encoding
    - Memory retrieval
    - Behavioral inhibition (stop signal)

    MRN 5-HT suppresses hippocampal theta during non-memory states,
    allowing theta to emerge during active encoding/retrieval.
    """

    def __init__(self, theta_baseline: float = 0.5, inhibition_gain: float = 0.6):
        self.theta_baseline = theta_baseline
        self.inhibition_gain = inhibition_gain
        self._theta_power = theta_baseline
        self._inhibition_active = False

    def modulate_theta(self, memory_demand: float, behavioral_state: str = 'active') -> Dict[str, float]:
        """
        Modulate hippocampal theta rhythm.

        Args:
            memory_demand: How much memory encoding/retrieval is needed [0, 1]
            behavioral_state: 'active', 'idle', 'waiting'

        Returns:
            Dict with theta_power, memory_encoding_strength
        """
        # MRN releases theta during memory demand
        state_modifier = {
            'active': 1.0,
            'waiting': 0.8,
            'idle': 0.4,
        }.get(behavioral_state, 0.5)

        self._theta_power = self.theta_baseline + memory_demand * 0.5 * state_modifier
        self._theta_power = min(1.0, max(0.0, self._theta_power))

        # Memory encoding strength proportional to theta
        encoding_strength = self._theta_power * 0.8

        return {
            'theta_power': round(self._theta_power, 3),
            'memory_encoding_strength': round(encoding_strength, 3),
        }

    def behavioral_inhibition(self, stop_signal: float) -> bool:
        """
        Generate behavioral inhibition (stop signal).

        Args:
            stop_signal: Strength of stop demand [0, 1]

        Returns:
            True if behavior should be inhibited
        """
        inhibition = stop_signal * self.inhibition_gain
        self._inhibition_active = inhibition > 0.5
        return self._inhibition_active

    @property
    def theta_power(self) -> float:
        return self._theta_power

    def to_dict(self) -> Dict[str, Any]:
        return {
            'theta_power': round(self._theta_power, 3),
            'inhibition_active': self._inhibition_active,
        }


class RapheNuclei:
    """
    Complete Raphe Nuclei module.

    Functions:
    1. Patience/impulsivity regulation (DRN)
    2. Mood baseline setting (DRN)
    3. Temporal discounting modulation (DRN)
    4. Hippocampal theta rhythm control (MRN)
    5. Behavioral inhibition (MRN)

    Serotonin acts as the "patience" opponent to dopamine's "go" signal.
    """

    def __init__(
        self,
        baseline_5ht: float = 0.5,
        patience_gain: float = 1.0,
        mood_inertia: float = 0.9,
        theta_baseline: float = 0.5,
        inhibition_gain: float = 0.6,
    ):
        self.drn = DorsalRapheNucleus(baseline_5ht, patience_gain, mood_inertia)
        self.mrn = MedianRapheNucleus(theta_baseline, inhibition_gain)
        self._stats = RapheStats()

    def process(
        self,
        reward_rate: float = 0.5,
        punishment: float = 0.0,
        wait_time: float = 0.0,
        goal_progress: float = 0.5,
        memory_demand: float = 0.5,
        behavioral_state: str = 'active',
        stop_signal: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Full raphe nuclei processing cycle.

        Args:
            reward_rate: Recent reward rate [0, 1]
            punishment: Recent punishment [0, 1]
            wait_time: Time remaining for delayed reward [0, 1]
            goal_progress: Progress toward goals [0, 1]
            memory_demand: Memory encoding/retrieval demand [0, 1]
            behavioral_state: Current behavioral state
            stop_signal: Stop/inhibition demand [0, 1]

        Returns:
            Dict with 5-HT level, patience, mood, theta, inhibition
        """
        # DRN processing
        drn_state = self.drn.update(reward_rate, punishment, wait_time, goal_progress)

        # MRN processing
        mrn_state = self.mrn.modulate_theta(memory_demand, behavioral_state)
        should_inhibit = self.mrn.behavioral_inhibition(stop_signal)

        # Update stats
        self._stats.total_cycles += 1
        if drn_state['patience'] > 0.5:
            self._stats.total_patience_wins += 1
        else:
            self._stats.total_impulsive_actions += 1
        if should_inhibit:
            self._stats.total_inhibitions += 1
        self._stats.avg_serotonin = drn_state['serotonin']
        self._stats.avg_patience = drn_state['patience']
        self._stats.avg_mood = drn_state['mood']

        return {
            'serotonin': round(drn_state['serotonin'], 3),
            'patience': round(drn_state['patience'], 3),
            'mood': round(drn_state['mood'], 3),
            'discount_factor': round(drn_state['discount_factor'], 3),
            'theta_power': mrn_state['theta_power'],
            'memory_encoding_strength': mrn_state['memory_encoding_strength'],
            'should_inhibit': should_inhibit,
        }


    def compute_waiting_cost(self, delay: float, reward_magnitude: float = 1.0) -> Dict[str, float]:
        """
        Compute the subjective cost of waiting using hyperbolic discounting.

        Mazur (1987): V = A / (1 + k * D)
        where k is inversely proportional to serotonin level.
        High 5-HT = low k = patient (shallow discount).
        Low 5-HT = high k = impulsive (steep discount).

        Args:
            delay: Delay until reward (normalized) [0, 1]
            reward_magnitude: Size of the delayed reward [0, 1]

        Returns:
            Dict with discounted_value, waiting_cost, discount_rate
        """
        serotonin = self.drn.serotonin
        # k ranges from 5.0 (very impulsive) to 0.2 (very patient)
        k = 5.0 * (1.0 - serotonin) + 0.2 * serotonin
        # Hyperbolic discount
        discounted_value = reward_magnitude / (1.0 + k * delay)
        # Waiting cost = how much value is lost by waiting
        waiting_cost = max(0.0, reward_magnitude - discounted_value)

        return {
            'discounted_value': round(discounted_value, 4),
            'waiting_cost': round(waiting_cost, 4),
            'discount_rate_k': round(k, 3),
            'patience_level': round(serotonin, 3),
        }

    def serotonin_dopamine_opponency(self, da_level: float) -> Dict[str, float]:
        """
        Compute 5-HT/DA opponent balance (Daw et al. 2002).

        Serotonin and dopamine form an opponent system:
        - DA promotes action, approach, immediate reward (GO)
        - 5-HT promotes inhibition, patience, delayed reward (WAIT)
        - The balance determines impulsive vs patient behavior

        Args:
            da_level: Current dopamine level from VTA [0, 1]

        Returns:
            Dict with balance, action_tendency, should_act
        """
        serotonin = self.drn.serotonin
        # Opponent balance: positive = GO (DA dominant), negative = WAIT (5-HT dominant)
        balance = da_level - serotonin
        # Action tendency: 0 = full inhibition, 1 = full activation
        action_tendency = 0.5 + balance * 0.5
        action_tendency = max(0.0, min(1.0, action_tendency))
        # Should act: DA must sufficiently exceed 5-HT
        should_act = balance > 0.1

        return {
            'da_5ht_balance': round(balance, 4),
            'action_tendency': round(action_tendency, 4),
            'should_act': should_act,
            'da_level': round(da_level, 3),
            'serotonin_level': round(serotonin, 3),
        }

    def mood_stability_signal(self) -> Dict[str, float]:
        """
        Compute mood stability signal reflecting 5-HT regulatory function.

        Cools et al. (2008): Serotonin regulates emotional resilience.
        High 5-HT = stable mood, low reactivity to negative events.
        Low 5-HT = mood instability, high reactivity, rumination risk.

        Returns:
            Dict with stability, resilience, rumination_risk
        """
        serotonin = self.drn.serotonin
        mood = self.drn.mood

        # Stability: high 5-HT = stable, low = volatile
        stability = serotonin * 0.7 + mood * 0.3
        stability = max(0.0, min(1.0, stability))

        # Resilience: ability to bounce back from negative events
        resilience = serotonin ** 0.8  # Diminishing returns

        # Rumination risk: inversely related to serotonin
        rumination_risk = max(0.0, 0.8 - serotonin * 1.0)

        return {
            'stability': round(stability, 4),
            'resilience': round(resilience, 4),
            'rumination_risk': round(rumination_risk, 4),
            'serotonin': round(serotonin, 3),
        }

    def should_wait(self, immediate: float, delayed: float, delay: float) -> bool:
        """Decide whether to wait for delayed reward."""
        result = self.drn.should_wait(immediate, delayed, delay)
        if result:
            self._stats.total_patience_wins += 1
        return result

    @property
    def serotonin(self) -> float:
        return self.drn.serotonin

    @property
    def mood(self) -> float:
        return self.drn.mood

    @property
    def patience(self) -> float:
        return self.drn.patience

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'drn': self.drn.to_dict(),
            'mrn': self.mrn.to_dict(),
        }

    def get_stats(self) -> RapheStats:
        return self._stats

    def reset(self):
        self._stats = RapheStats()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'RapheNuclei':
        cfg = config.get('raphe_nuclei', {})
        return cls(
            baseline_5ht=cfg.get('baseline_5ht', 0.5),
            patience_gain=cfg.get('patience_gain', 1.0),
            mood_inertia=cfg.get('mood_inertia', 0.9),
            theta_baseline=cfg.get('theta_baseline', 0.5),
            inhibition_gain=cfg.get('inhibition_gain', 0.6),
        )
