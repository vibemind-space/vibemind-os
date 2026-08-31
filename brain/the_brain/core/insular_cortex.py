"""
Insular Cortex Module - Neuroscience Architecture Extension Phase B2

Computational model of the insular cortex for interoception,
salience detection, subjective feeling generation, and network switching.

Neuroscience basis:
- Anterior Insula: Subjective feelings, empathy, time perception
- Posterior Insula: Primary interoceptive processing
- Craig (2009): "Interoceptive awareness" hub
- Menon & Uddin (2010): Salience Network drives DMN <-> TPN switching
- Part of Salience Network (with dorsal ACC)

Key references:
- "Insular Cortex-Biology and Its Role in Psychiatric Disorders" (PubMed)
- Craig (2009): How do you feel - now?
- Menon & Uddin (2010): Saliency, switching, attention, and control

Integration points:
- Input: Body signals (Hypothalamus), emotions (Amygdala), sensory data
- Output: Salience signal to attention, feelings to consciousness
- Wiring: agent_loop.insular_cortex = InsularCortex.from_yaml(config)
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.insular_cortex')


# ─── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class SalienceEvent:
    """A detected salience event."""
    source: str
    intensity: float
    timestamp: float = field(default_factory=time.time)
    features: Optional[np.ndarray] = None


@dataclass
class InsularStats:
    """Insular cortex statistics."""
    interoceptive_updates: int = 0
    salience_detections: int = 0
    network_switches: int = 0
    current_feeling: str = "neutral"
    body_budget_balance: float = 0.0
    avg_salience: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'interoceptive_updates': self.interoceptive_updates,
            'salience_detections': self.salience_detections,
            'network_switches': self.network_switches,
            'current_feeling': self.current_feeling,
            'body_budget_balance': round(self.body_budget_balance, 3),
            'avg_salience': round(self.avg_salience, 3),
        }


# ─── Interoceptive Processor (Posterior Insula) ───────────────────────────────

class InteroceptiveProcessor:
    """
    Posterior insula: processes body-state signals.

    Monitors internal body signals including heart rate, respiration,
    gut feelings, temperature, pain, and energy levels.

    Craig (2002): Primary interoceptive cortex - maps the physiological
    condition of the body.
    """

    def __init__(self, n_channels: int = 6):
        self.n_channels = n_channels
        # Body signal channels: [energy, pain, temperature, heartrate, respiration, gut]
        self._body_state = np.full(n_channels, 0.5, dtype=np.float32)
        self._baseline = np.full(n_channels, 0.5, dtype=np.float32)
        self._history = deque(maxlen=50)

    def update(self, body_signals: np.ndarray) -> np.ndarray:
        """
        Process incoming body signals.

        Args:
            body_signals: Raw interoceptive signals

        Returns:
            Deviation from baseline (interoceptive prediction error)
        """
        signals = np.asarray(body_signals, dtype=np.float32).flatten()
        padded = np.full(self.n_channels, 0.5, dtype=np.float32)
        n = min(len(signals), self.n_channels)
        padded[:n] = np.clip(signals[:n], 0.0, 1.0)

        self._body_state = padded
        deviation = padded - self._baseline
        self._history.append(padded.copy())

        # Slowly adapt baseline (allostatic adjustment)
        self._baseline = 0.99 * self._baseline + 0.01 * padded

        return deviation

    def get_body_state(self) -> np.ndarray:
        return self._body_state.copy()

    def get_deviation(self) -> float:
        """Return total deviation from baseline."""
        return float(np.abs(self._body_state - self._baseline).sum())

    def to_dict(self) -> Dict[str, Any]:
        names = ['energy', 'pain', 'temperature', 'heartrate', 'respiration', 'gut']
        return {
            names[i]: round(float(self._body_state[i]), 3)
            for i in range(min(len(names), self.n_channels))
        }


# ─── Salience Detector ────────────────────────────────────────────────────────

class SalienceDetector:
    """
    Salience detection combining multiple signal sources.

    Menon & Uddin (2010): The anterior insula, as part of the
    Salience Network, identifies the most relevant stimuli
    for further processing.
    """

    def __init__(self, n_modalities: int = 4, threshold: float = 0.6):
        self.n_modalities = n_modalities
        self.threshold = threshold
        self._modality_weights = np.ones(n_modalities, dtype=np.float32) / n_modalities
        self._salience_history = deque(maxlen=100)
        self._events = deque(maxlen=50)

    def compute_salience(
        self,
        signals: Dict[str, float],
        novelty: float = 0.0,
        emotional_intensity: float = 0.0
    ) -> float:
        """
        Compute overall salience from multiple sources.

        Args:
            signals: Dict of signal_name -> intensity pairs
            novelty: Novelty of current input [0, 1]
            emotional_intensity: Emotional arousal [0, 1]

        Returns:
            Salience score [0, 1]
        """
        # Combine signal intensities
        values = list(signals.values())[:self.n_modalities]
        if not values:
            signal_salience = 0.0
        else:
            signal_salience = float(np.mean(values))

        # Weighted combination
        salience = (0.4 * signal_salience +
                    0.3 * novelty +
                    0.3 * emotional_intensity)
        salience = max(0.0, min(1.0, salience))

        self._salience_history.append(salience)

        if salience > self.threshold:
            self._events.append(SalienceEvent(
                source="multi",
                intensity=salience,
            ))

        return salience

    def is_salient(self, salience: float) -> bool:
        return salience > self.threshold

    def get_avg_salience(self) -> float:
        if not self._salience_history:
            return 0.0
        return float(np.mean(list(self._salience_history)))

    def get_recent_events(self, n: int = 5) -> List[SalienceEvent]:
        return list(self._events)[-n:]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'threshold': self.threshold,
            'avg_salience': self.get_avg_salience(),
            'recent_events': len(self._events),
        }


# ─── Subjective Feeling Generator (Anterior Insula) ───────────────────────────

class SubjectiveFeelingGenerator:
    """
    Generates subjective feeling states.

    Craig (2009): The anterior insula integrates interoceptive signals
    with emotional and cognitive context to produce subjective feelings.
    """

    FEELINGS = ['neutral', 'alert', 'calm', 'stressed', 'energized',
                'fatigued', 'curious', 'satisfied', 'uneasy']

    def __init__(self):
        self._current_feeling = 'neutral'
        self._feeling_history = deque(maxlen=50)

    def generate_feeling(
        self,
        body_deviation: float,
        salience: float,
        stress: float = 0.0,
        energy: float = 0.5
    ) -> str:
        """
        Generate a subjective feeling label from internal signals.

        This is a simplified mapping - real feelings emerge from
        complex interactions.
        """
        if stress > 0.7:
            feeling = 'stressed'
        elif energy < 0.3:
            feeling = 'fatigued'
        elif salience > 0.7:
            feeling = 'alert'
        elif body_deviation > 0.5:
            feeling = 'uneasy'
        elif energy > 0.7 and stress < 0.3:
            feeling = 'energized'
        elif salience < 0.2 and stress < 0.2:
            feeling = 'calm'
        elif salience > 0.4:
            feeling = 'curious'
        elif body_deviation < 0.2 and stress < 0.3:
            feeling = 'satisfied'
        else:
            feeling = 'neutral'

        self._current_feeling = feeling
        self._feeling_history.append(feeling)
        return feeling

    @property
    def current_feeling(self) -> str:
        return self._current_feeling

    def to_dict(self) -> Dict[str, Any]:
        return {
            'current': self._current_feeling,
            'history_size': len(self._feeling_history),
        }


# ─── Body Budget Accounting ───────────────────────────────────────────────────

class BodyBudgetAccounting:
    """
    Allostatic body budgeting system.

    Barrett (2017): The brain is a prediction machine that
    manages a "body budget" (allostasis) - predicting and
    regulating metabolic resources.
    """

    def __init__(self):
        self._budget = 1.0  # [0, 1] - 1.0 = full resources
        self._expenditures = deque(maxlen=100)
        self._deposits = deque(maxlen=100)

    def spend(self, amount: float, category: str = "general") -> float:
        """Spend from the body budget."""
        amount = max(0.0, min(amount, self._budget))
        self._budget -= amount
        self._expenditures.append({'amount': amount, 'category': category})
        return self._budget

    def deposit(self, amount: float, source: str = "rest") -> float:
        """Add to the body budget (rest, food, etc.)."""
        amount = max(0.0, amount)
        self._budget = min(1.0, self._budget + amount)
        self._deposits.append({'amount': amount, 'source': source})
        return self._budget

    @property
    def balance(self) -> float:
        return self._budget

    @property
    def is_depleted(self) -> bool:
        return self._budget < 0.2

    def to_dict(self) -> Dict[str, Any]:
        return {
            'balance': round(self._budget, 3),
            'is_depleted': self.is_depleted,
        }


# ─── Network Switcher ─────────────────────────────────────────────────────────

class NetworkSwitcher:
    """
    Controls switching between brain networks based on salience.

    The anterior insula acts as a causal hub for switching between
    the DMN (internal focus) and TPN (external focus).
    """

    def __init__(self, switch_speed: float = 0.5):
        self.switch_speed = switch_speed
        self._current_network = "dmn"  # "dmn" or "tpn"
        self._switch_count = 0
        self._transition_smooth = 0.0  # 0=DMN, 1=TPN

    def evaluate_switch(self, salience: float, current_task_demand: float) -> str:
        """
        Decide which network should be active.

        Args:
            salience: Current salience level
            current_task_demand: Current task cognitive demand

        Returns:
            "dmn" or "tpn"
        """
        target = salience * 0.5 + current_task_demand * 0.5
        self._transition_smooth += self.switch_speed * (target - self._transition_smooth)
        self._transition_smooth = max(0.0, min(1.0, self._transition_smooth))

        new_network = "tpn" if self._transition_smooth > 0.5 else "dmn"
        if new_network != self._current_network:
            self._switch_count += 1
            self._current_network = new_network

        return self._current_network

    @property
    def current_network(self) -> str:
        return self._current_network

    @property
    def switch_count(self) -> int:
        return self._switch_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            'current_network': self._current_network,
            'transition': round(self._transition_smooth, 3),
            'switch_count': self._switch_count,
        }


# ─── Main Insular Cortex Module ───────────────────────────────────────────────

class InsularCortex:
    """
    Complete insular cortex module.

    Functions:
    1. Interoceptive processing (posterior insula)
    2. Salience detection (anterior insula / salience network)
    3. Subjective feeling generation (anterior insula)
    4. Body budget management (allostasis)
    5. Network switching (DMN <-> TPN)
    """

    def __init__(
        self,
        n_body_channels: int = 6,
        n_modalities: int = 4,
        salience_threshold: float = 0.6,
        interoceptive_gain: float = 1.0,
        network_switch_speed: float = 0.5,
    ):
        self.interoceptive = InteroceptiveProcessor(n_body_channels)
        self.salience_detector = SalienceDetector(n_modalities, salience_threshold)
        self.feeling_generator = SubjectiveFeelingGenerator()
        self.body_budget = BodyBudgetAccounting()
        self.network_switcher = NetworkSwitcher(network_switch_speed)

        self._interoceptive_gain = interoceptive_gain
        self._stats = InsularStats()

    def process(
        self,
        body_signals: Optional[np.ndarray] = None,
        sensory_signals: Optional[Dict[str, float]] = None,
        novelty: float = 0.0,
        emotional_intensity: float = 0.0,
        stress: float = 0.0,
        task_demand: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Full insular cortex processing cycle.

        Args:
            body_signals: Interoceptive signals [n_channels]
            sensory_signals: Dict of modality -> intensity
            novelty: Novelty of current input
            emotional_intensity: Emotional arousal
            stress: Current stress level
            task_demand: Current task cognitive demand

        Returns:
            Dict with salience, feeling, network, body_budget, etc.
        """
        # 1. Interoceptive processing
        if body_signals is not None:
            deviation = self.interoceptive.update(body_signals)
            body_deviation = float(np.abs(deviation).mean()) * self._interoceptive_gain
            self._stats.interoceptive_updates += 1
        else:
            body_deviation = self.interoceptive.get_deviation()

        # 2. Salience detection
        signals = sensory_signals or {}
        signals['interoceptive'] = body_deviation
        salience = self.salience_detector.compute_salience(
            signals, novelty, emotional_intensity
        )
        if self.salience_detector.is_salient(salience):
            self._stats.salience_detections += 1

        # 3. Subjective feeling
        energy = self.body_budget.balance
        feeling = self.feeling_generator.generate_feeling(
            body_deviation, salience, stress, energy
        )

        # 4. Body budget update
        # Task demand costs energy
        if task_demand > 0.3:
            self.body_budget.spend(task_demand * 0.01, "cognitive")

        # 5. Network switching
        old_network = self.network_switcher.current_network
        active_network = self.network_switcher.evaluate_switch(salience, task_demand)
        if active_network != old_network:
            self._stats.network_switches += 1

        # Update stats
        self._stats.current_feeling = feeling
        self._stats.body_budget_balance = self.body_budget.balance
        self._stats.avg_salience = self.salience_detector.get_avg_salience()

        return {
            'salience': salience,
            'is_salient': self.salience_detector.is_salient(salience),
            'feeling': feeling,
            'body_deviation': body_deviation,
            'body_budget': self.body_budget.balance,
            'active_network': active_network,
            'body_state': self.interoceptive.get_body_state(),
        }

    def predictive_interoception(
        self,
        predicted_body_state: np.ndarray,
        actual_body_state: np.ndarray,
    ) -> Dict[str, float]:
        """
        Predictive interoception (Seth & Friston, 2016 — Active Inference).

        The insula maintains a generative model of body states and computes
        interoceptive prediction errors. Emotions arise from these prediction
        errors: surprise about body state = emotional experience. Chronic
        interoceptive prediction errors -> anxiety, alexithymia.

        Args:
            predicted_body_state: Expected body signals (from allostatic model)
            actual_body_state: Actual interoceptive signals

        Returns:
            Dict with prediction_error, emotional_intensity, body_surprise
        """
        predicted = np.asarray(predicted_body_state, dtype=np.float32)
        actual = np.asarray(actual_body_state, dtype=np.float32)

        # Ensure same length
        min_len = min(len(predicted), len(actual))
        predicted = predicted[:min_len]
        actual = actual[:min_len]

        # Interoceptive prediction error
        error = actual - predicted
        error_magnitude = float(np.mean(np.abs(error))) if min_len > 0 else 0.0

        # Emotional intensity scales with prediction error
        emotional_intensity = min(1.0, error_magnitude * 2.0)

        # Body surprise (negative log-likelihood proxy)
        body_surprise = min(1.0, error_magnitude ** 0.8)

        # Anxiety: sustained high prediction error
        anxiety_signal = min(1.0, error_magnitude * 1.5)

        return {
            'prediction_error': round(error_magnitude, 4),
            'emotional_intensity': round(emotional_intensity, 4),
            'body_surprise': round(body_surprise, 4),
            'anxiety_signal': round(anxiety_signal, 4),
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'interoceptive': self.interoceptive.to_dict(),
            'salience': self.salience_detector.to_dict(),
            'feeling': self.feeling_generator.to_dict(),
            'body_budget': self.body_budget.to_dict(),
            'network': self.network_switcher.to_dict(),
        }

    def get_stats(self) -> InsularStats:
        return self._stats

    def reset(self):
        self._stats = InsularStats()
        self.body_budget._budget = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'InsularCortex':
        """
        Expected config:
            insular_cortex:
              salience_threshold: 0.6
              interoceptive_gain: 1.0
              network_switch_speed: 0.5
        """
        ic = config.get('insular_cortex', {})
        return cls(
            salience_threshold=ic.get('salience_threshold', 0.6),
            interoceptive_gain=ic.get('interoceptive_gain', 1.0),
            network_switch_speed=ic.get('network_switch_speed', 0.5),
        )
