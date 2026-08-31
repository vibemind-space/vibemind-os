"""
Ventral Tegmental Area (VTA) Module - Phase D2

The VTA is a midbrain dopamine neuron cluster — THE reward prediction
error (RPE) signal generator. It is the core learning signal for the
entire brain, driving temporal difference learning, motivation,
and exploration/exploitation balance.

Neuroscience basis:
- Schultz et al. (1997): DA neurons encode reward prediction error
  * Phasic burst: Positive RPE (better than expected)
  * Phasic pause: Negative RPE (worse than expected)
  * Tonic firing: Baseline motivation/reward expectation
- Bromberg-Martin et al. (2010): Two DA neuron populations:
  * Value coding: reward prediction error (classic Schultz)
  * Salience coding: unsigned importance signal

Key functions:
- Temporal difference (TD) learning signal
- Reward prediction error computation
- Motivation/wanting signal (mesolimbic DA)
- Working memory modulation (mesocortical DA)
- Salience coding (unsigned novelty/importance)

Integration:
- Input: PFC (predictions), NAc (reward), LHb (inhibition), amygdala (valence)
- Output: VTA -> NAc (reward), VTA -> PFC (working memory),
         VTA -> amygdala (emotional learning), VTA -> hippocampus (memory)
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.vta')


@dataclass
class VTAStats:
    """VTA processing statistics."""
    total_predictions: int = 0
    total_positive_rpe: int = 0
    total_negative_rpe: int = 0
    total_neutral: int = 0
    avg_rpe: float = 0.0
    avg_tonic_da: float = 0.5
    avg_motivation: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_predictions': self.total_predictions,
            'total_positive_rpe': self.total_positive_rpe,
            'total_negative_rpe': self.total_negative_rpe,
            'total_neutral': self.total_neutral,
            'avg_rpe': round(self.avg_rpe, 3),
            'avg_tonic_da': round(self.avg_tonic_da, 3),
            'avg_motivation': round(self.avg_motivation, 3),
        }


class DopamineNeuronPopulation:
    """
    Models tonic and phasic dopamine neuron firing.

    Tonic mode: Sustained baseline firing (~4 Hz)
    - Sets baseline motivation and reward expectation
    - Regulated by GABAergic input from NAc, VP

    Phasic mode: Burst or pause relative to tonic
    - Burst (>20 Hz): Positive RPE, reward > expected
    - Pause (<1 Hz): Negative RPE, reward < expected
    """

    def __init__(
        self,
        tonic_baseline: float = 0.5,
        phasic_gain: float = 1.0,
        decay_rate: float = 0.1,
    ):
        self.tonic_baseline = tonic_baseline
        self.phasic_gain = phasic_gain
        self.decay_rate = decay_rate

        self._tonic_level = tonic_baseline
        self._phasic_signal = 0.0
        self._firing_history = deque(maxlen=200)

    def compute_firing(self, rpe: float) -> Dict[str, float]:
        """
        Compute DA neuron firing based on RPE.

        Args:
            rpe: Reward prediction error [-1, 1]

        Returns:
            Dict with tonic, phasic, and total dopamine output
        """
        # Phasic burst/pause
        self._phasic_signal = rpe * self.phasic_gain

        # Total DA output = tonic + phasic, clamped to [0, 1]
        total_da = self._tonic_level + self._phasic_signal
        total_da = max(0.0, min(1.0, total_da))

        self._firing_history.append(total_da)

        return {
            'tonic': self._tonic_level,
            'phasic': self._phasic_signal,
            'total_da': total_da,
            'is_burst': self._phasic_signal > 0.1,
            'is_pause': self._phasic_signal < -0.1,
        }

    def adapt_tonic(self, avg_reward: float):
        """
        Slowly adapt tonic baseline to average reward.

        Tonic level tracks long-run average reward, providing
        the baseline against which RPE is computed.
        """
        self._tonic_level += self.decay_rate * (avg_reward - self._tonic_level)
        self._tonic_level = max(0.1, min(0.9, self._tonic_level))

    @property
    def tonic_level(self) -> float:
        return self._tonic_level

    @property
    def phasic_signal(self) -> float:
        return self._phasic_signal

    def to_dict(self) -> Dict[str, Any]:
        return {
            'tonic': round(self._tonic_level, 3),
            'phasic': round(self._phasic_signal, 3),
        }


class GABAInterneurons:
    """
    Local GABA inhibitory interneurons within VTA.

    Gate DA neuron firing patterns. Can be activated by:
    - Lateral Habenula (inhibitory input)
    - NAc feedback
    - Local circuit dynamics

    When GABA interneurons are strongly active, they suppress
    DA neuron firing, implementing the LHb -> VTA inhibition pathway.
    """

    def __init__(self, inhibition_strength: float = 0.5):
        self.inhibition_strength = inhibition_strength
        self._activation = 0.0

    def compute_inhibition(
        self,
        lhb_signal: float = 0.0,
        nac_feedback: float = 0.0,
    ) -> float:
        """
        Compute inhibitory signal to DA neurons.

        Args:
            lhb_signal: Input from lateral habenula [0, 1]
            nac_feedback: Feedback from NAc [0, 1]

        Returns:
            Inhibition level [0, 1], higher = more DA suppression
        """
        # LHb is the primary inhibitory drive
        raw = lhb_signal * 0.7 + nac_feedback * 0.3
        self._activation = raw * self.inhibition_strength
        self._activation = min(1.0, max(0.0, self._activation))
        return self._activation

    @property
    def activation(self) -> float:
        return self._activation

    def to_dict(self) -> Dict[str, Any]:
        return {
            'activation': round(self._activation, 3),
            'inhibition_strength': self.inhibition_strength,
        }


class RewardPredictor:
    """
    Temporal difference (TD) reward prediction.

    Maintains a value estimate that is updated by prediction errors.
    Schultz (1997): V(t) <- V(t) + alpha * RPE
    """

    def __init__(self, learning_rate: float = 0.1, discount: float = 0.95):
        self.learning_rate = learning_rate
        self.discount = discount

        # Value estimates for different task/state contexts
        self._value_estimates: Dict[str, float] = {}
        self._default_value = 0.5
        self._rpe_history = deque(maxlen=200)

    def predict_reward(self, state_id: str = 'default') -> float:
        """Predict expected reward for a given state."""
        return self._value_estimates.get(state_id, self._default_value)

    def compute_rpe(
        self,
        actual_reward: float,
        state_id: str = 'default',
        next_state_id: Optional[str] = None,
    ) -> float:
        """
        Compute temporal difference reward prediction error.

        RPE = actual_reward + gamma * V(next) - V(current)

        Args:
            actual_reward: Actual reward received [0, 1]
            state_id: Current state identifier
            next_state_id: Next state (for TD learning)

        Returns:
            RPE in [-1, 1]
        """
        current_v = self._value_estimates.get(state_id, self._default_value)
        next_v = self._value_estimates.get(
            next_state_id or state_id, self._default_value
        )

        # TD error
        rpe = actual_reward + self.discount * next_v - current_v
        rpe = max(-1.0, min(1.0, rpe))

        # Update value estimate
        new_v = current_v + self.learning_rate * rpe
        self._value_estimates[state_id] = max(0.0, min(1.0, new_v))

        self._rpe_history.append(rpe)
        return rpe

    def get_avg_rpe(self) -> float:
        if not self._rpe_history:
            return 0.0
        return float(np.mean(list(self._rpe_history)))

    def get_avg_value(self) -> float:
        if not self._value_estimates:
            return self._default_value
        return float(np.mean(list(self._value_estimates.values())))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'n_states': len(self._value_estimates),
            'avg_rpe': round(self.get_avg_rpe(), 3),
            'avg_value': round(self.get_avg_value(), 3),
        }


class SalienceCoder:
    """
    Salience coding DA neurons.

    Bromberg-Martin et al. (2010): A subset of DA neurons encode
    unsigned salience (|RPE|) rather than signed RPE. This signals
    the IMPORTANCE of an event regardless of whether it's good or bad.
    """

    def __init__(self, salience_threshold: float = 0.3):
        self.salience_threshold = salience_threshold
        self._salience_history = deque(maxlen=100)

    def compute_salience(self, rpe: float, novelty: float = 0.0) -> float:
        """
        Compute salience signal from RPE and novelty.

        Args:
            rpe: Reward prediction error [-1, 1]
            novelty: Novelty of the stimulus [0, 1]

        Returns:
            Salience signal [0, 1]
        """
        # Unsigned RPE component
        unsigned_rpe = abs(rpe)

        # Combine with novelty
        salience = unsigned_rpe * 0.6 + novelty * 0.4
        salience = min(1.0, salience)

        self._salience_history.append(salience)
        return salience

    def is_salient(self, salience: float) -> bool:
        return salience > self.salience_threshold

    def to_dict(self) -> Dict[str, Any]:
        return {
            'threshold': self.salience_threshold,
            'avg_salience': round(
                float(np.mean(list(self._salience_history))) if self._salience_history else 0.0,
                3,
            ),
        }


class VentralTegmentalArea:
    """
    Complete Ventral Tegmental Area module.

    Functions:
    1. Reward prediction error computation (TD learning)
    2. Tonic/phasic dopamine signaling
    3. GABA-mediated inhibition (LHb pathway)
    4. Salience coding (unsigned importance)
    5. Motivation signal generation

    This is THE core learning signal for Tahlamus.
    """

    def __init__(
        self,
        tonic_baseline: float = 0.5,
        phasic_gain: float = 1.0,
        learning_rate: float = 0.1,
        discount: float = 0.95,
        inhibition_strength: float = 0.5,
        salience_threshold: float = 0.3,
    ):
        self.da_neurons = DopamineNeuronPopulation(tonic_baseline, phasic_gain)
        self.gaba = GABAInterneurons(inhibition_strength)
        self.reward_predictor = RewardPredictor(learning_rate, discount)
        self.salience_coder = SalienceCoder(salience_threshold)
        self._stats = VTAStats()
        self._motivation_history = deque(maxlen=100)

    def process(
        self,
        actual_reward: float,
        state_id: str = 'default',
        next_state_id: Optional[str] = None,
        lhb_inhibition: float = 0.0,
        novelty: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Full VTA processing cycle.

        1. Compute reward prediction error
        2. Apply GABA inhibition
        3. Generate DA neuron firing
        4. Compute salience
        5. Generate motivation signal

        Args:
            actual_reward: Actual reward received [0, 1]
            state_id: Current state identifier
            next_state_id: Next state for TD learning
            lhb_inhibition: Lateral habenula inhibitory signal [0, 1]
            novelty: Stimulus novelty [0, 1]

        Returns:
            Dict with RPE, DA levels, salience, motivation
        """
        # 1. Compute RPE
        rpe = self.reward_predictor.compute_rpe(actual_reward, state_id, next_state_id)

        # 2. GABA inhibition (can suppress positive RPE)
        inhibition = self.gaba.compute_inhibition(lhb_inhibition)
        effective_rpe = rpe * (1.0 - inhibition * 0.5)

        # 3. DA neuron firing
        firing = self.da_neurons.compute_firing(effective_rpe)

        # 4. Salience
        salience = self.salience_coder.compute_salience(rpe, novelty)

        # 5. Motivation: based on tonic DA and positive phasic
        motivation = firing['tonic'] * 0.6 + max(0, firing['phasic']) * 0.4
        motivation = min(1.0, max(0.0, motivation))
        self._motivation_history.append(motivation)

        # Adapt tonic baseline to running average
        avg_reward = self.reward_predictor.get_avg_value()
        self.da_neurons.adapt_tonic(avg_reward)

        # Update stats
        self._stats.total_predictions += 1
        if rpe > 0.1:
            self._stats.total_positive_rpe += 1
        elif rpe < -0.1:
            self._stats.total_negative_rpe += 1
        else:
            self._stats.total_neutral += 1
        self._stats.avg_rpe = self.reward_predictor.get_avg_rpe()
        self._stats.avg_tonic_da = self.da_neurons.tonic_level
        self._stats.avg_motivation = float(
            np.mean(list(self._motivation_history)) if self._motivation_history else 0.5
        )

        return {
            'rpe': round(rpe, 4),
            'effective_rpe': round(effective_rpe, 4),
            'dopamine': firing,
            'salience': round(salience, 3),
            'is_salient': self.salience_coder.is_salient(salience),
            'motivation': round(motivation, 3),
            'inhibition': round(inhibition, 3),
            'predicted_reward': round(
                self.reward_predictor.predict_reward(state_id), 3
            ),
        }


    def reward_circuit_outputs(self, rpe: float = None, salience: float = None) -> Dict[str, float]:
        """
        Map DA output to specific target regions (Haber & Knutson 2009).

        Different VTA projection targets receive weighted DA signals:
        - NAcc (mesolimbic): motivation, reward seeking, wanting
        - PFC (mesocortical): working memory gating, cognitive control
        - Amygdala: emotional/valence learning
        - Hippocampus: memory encoding strength

        Args:
            rpe: Reward prediction error (uses last computed if None)
            salience: Salience signal (uses last computed if None)

        Returns:
            Dict with DA signal strength per target region [0, 1]
        """
        if rpe is None:
            rpe = self.da_neurons.phasic_signal
        if salience is None:
            salience = float(np.mean(list(self.salience_coder._salience_history))) if self.salience_coder._salience_history else 0.0

        total_da = self.da_neurons._tonic_level + self.da_neurons._phasic_signal
        total_da = max(0.0, min(1.0, total_da))

        return {
            'nacc_motivation': round(min(1.0, total_da * 0.8 + max(0, rpe) * 0.2), 4),
            'pfc_wm_gate': round(min(1.0, max(0, rpe) * 0.6 + salience * 0.4), 4),
            'amygdala_valence': round(min(1.0, abs(rpe) * 0.5 + salience * 0.5), 4),
            'hippocampus_encoding': round(min(1.0, salience * 0.7 + abs(rpe) * 0.3), 4),
        }

    def compute_salience_weighted_da(
        self,
        rpe: float,
        novelty: float = 0.0,
        salience_weight: float = 0.3,
    ) -> Dict[str, float]:
        """
        Compute combined value-coding and salience-coding DA signal.

        Bromberg-Martin et al. (2010): Two populations of DA neurons:
        - Value-coding: signed RPE (classic Schultz)
        - Salience-coding: unsigned importance (|RPE| + novelty)

        Args:
            rpe: Reward prediction error [-1, 1]
            novelty: Stimulus novelty [0, 1]
            salience_weight: Weight of salience population [0, 1]

        Returns:
            Dict with value_signal, salience_signal, combined_da
        """
        value_signal = rpe  # Signed: positive for good, negative for bad
        salience_signal = self.salience_coder.compute_salience(rpe, novelty)

        # Combined signal: weighted blend of value and salience populations
        combined = (1.0 - salience_weight) * (value_signal * 0.5 + 0.5) + salience_weight * salience_signal
        combined = max(0.0, min(1.0, combined))

        return {
            'value_signal': round(value_signal, 4),
            'salience_signal': round(salience_signal, 4),
            'combined_da': round(combined, 4),
            'is_salient': self.salience_coder.is_salient(salience_signal),
        }

    def compute_ramping_signal(
        self,
        distance_to_goal: float,
        reward_magnitude: float = 1.0,
    ) -> Dict[str, float]:
        """
        Ramping DA signal that increases as agent approaches reward.

        Howe et al. (2013): VTA DA neurons show sustained ramping activity
        during approach to reward, not just phasic bursts at delivery.
        This provides a continuous motivational drive during goal pursuit.

        Args:
            distance_to_goal: Normalized distance to goal [0=at goal, 1=far]
            reward_magnitude: Expected reward size [0, 1]

        Returns:
            Dict with ramp_signal, approach_motivation, urgency
        """
        proximity = 1.0 - max(0.0, min(1.0, distance_to_goal))
        # Nonlinear ramp: accelerates as goal nears (convex curve)
        ramp_signal = proximity ** 1.5 * reward_magnitude
        ramp_signal = min(1.0, ramp_signal)

        # Approach motivation combines tonic DA with ramping
        approach_motivation = (
            self.da_neurons.tonic_level * 0.3
            + ramp_signal * 0.7
        )

        # Urgency increases sharply near goal
        urgency = proximity ** 2.5 * reward_magnitude

        return {
            'ramp_signal': round(ramp_signal, 4),
            'approach_motivation': round(min(1.0, approach_motivation), 4),
            'urgency': round(min(1.0, urgency), 4),
            'proximity': round(proximity, 4),
        }

    def mesolimbic_output(self) -> Dict[str, float]:
        """
        Mesolimbic pathway output (VTA -> NAcc/ventral striatum).

        Berridge (2007): Mesolimbic DA = "wanting" (incentive salience),
        distinct from "liking" (hedonic impact, opioid-mediated).

        Returns:
            Dict with wanting_signal, incentive_salience, vigor
        """
        tonic = self.da_neurons.tonic_level
        phasic = max(0.0, self.da_neurons.phasic_signal)

        wanting = tonic * 0.4 + phasic * 0.6
        vigor = min(1.0, tonic * 0.5 + phasic * 0.8)

        return {
            'wanting_signal': round(min(1.0, wanting), 4),
            'incentive_salience': round(min(1.0, phasic * 0.7 + tonic * 0.3), 4),
            'vigor': round(vigor, 4),
        }

    def mesocortical_output(self) -> Dict[str, float]:
        """
        Mesocortical pathway output (VTA -> PFC).

        Inverted-U relationship (Goldman-Rakic 1995): Too little or too
        much DA impairs PFC function. Optimal DA = best working memory.

        Returns:
            Dict with wm_modulation, cognitive_flexibility, focus
        """
        total_da = self.da_neurons.tonic_level + max(0, self.da_neurons.phasic_signal)
        total_da = max(0.0, min(1.0, total_da))

        # Inverted-U: peak performance at ~0.5-0.6 DA
        optimal = 0.55
        deviation = abs(total_da - optimal) / optimal
        wm_modulation = max(0.0, 1.0 - deviation ** 1.5)

        # High DA -> exploitation/focus, Low DA -> exploration/flexibility
        focus = min(1.0, total_da * 1.2)
        flexibility = max(0.0, 1.0 - total_da * 0.8)

        return {
            'wm_modulation': round(wm_modulation, 4),
            'cognitive_flexibility': round(flexibility, 4),
            'focus': round(focus, 4),
            'total_da_to_pfc': round(total_da, 4),
        }

    def predict_reward(self, state_id: str = 'default') -> float:
        """Get reward prediction for a state."""
        return self.reward_predictor.predict_reward(state_id)

    def get_motivation(self) -> float:
        """Get current motivation level."""
        if not self._motivation_history:
            return 0.5
        return float(self._motivation_history[-1])

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'da_neurons': self.da_neurons.to_dict(),
            'gaba': self.gaba.to_dict(),
            'reward_predictor': self.reward_predictor.to_dict(),
            'salience': self.salience_coder.to_dict(),
        }

    def get_stats(self) -> VTAStats:
        return self._stats

    def reset(self):
        self._stats = VTAStats()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'VentralTegmentalArea':
        cfg = config.get('vta', {})
        return cls(
            tonic_baseline=cfg.get('tonic_baseline', 0.5),
            phasic_gain=cfg.get('phasic_gain', 1.0),
            learning_rate=cfg.get('learning_rate', 0.1),
            discount=cfg.get('discount', 0.95),
            inhibition_strength=cfg.get('inhibition_strength', 0.5),
            salience_threshold=cfg.get('salience_threshold', 0.3),
        )
