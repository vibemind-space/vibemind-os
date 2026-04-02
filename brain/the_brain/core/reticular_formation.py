"""
Reticular Formation / Ascending Reticular Activating System (ARAS)

Neuroscience basis:
  The reticular formation is a diffuse network of nuclei spanning the brainstem
  from the medulla oblongata through the pons to the midbrain tegmentum.  Its
  ascending projection — the Ascending Reticular Activating System (ARAS) — is
  the primary wakefulness controller in the mammalian brain.

  Moruzzi & Magoun (1949) demonstrated that electrical stimulation of the
  reticular formation awakens sleeping animals and produces cortical
  desynchronisation (low-amplitude, high-frequency EEG).  Conversely, lesions
  produce coma-like states regardless of intact sensory pathways.

  Core functions modelled here:
    1. Wakefulness / global arousal level (ARAS)
    2. Sensory gating — gain modulation of afferent signals based on arousal
    3. Sleep-wake state transitions with hysteresis
    4. Motor tone regulation (REM atonia, postural readiness)
    5. Pain modulation (not yet implemented — placeholder)

  References:
    - Moruzzi G, Magoun HW (1949). Brain stem reticular formation and
      activation of the EEG. Electroencephalography and Clinical
      Neurophysiology, 1(1-4), 455-473.
    - Steriade M (1996). Arousal: Revisiting the reticular activating system.
      Science, 272(5259), 225-226.
    - Garcia-Rill E (1991). The pedunculopontine nucleus. Progress in
      Neurobiology, 36(5), 363-389.
"""

import logging
import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from collections import deque
from enum import Enum

logger = logging.getLogger('brain.reticular_formation')


# ─── Sleep-Wake States ──────────────────────────────────────────────────────

class WakeState(Enum):
    """Discrete arousal states mirroring EEG-defined vigilance levels."""
    DEEP_SLEEP = "deep_sleep"
    LIGHT_SLEEP = "light_sleep"
    DROWSY = "drowsy"
    AWAKE = "awake"
    ALERT = "alert"
    HYPERAROUSED = "hyperaroused"


# ─── Stats Dataclass ────────────────────────────────────────────────────────

@dataclass
class ReticularFormationStats:
    """Cumulative statistics for the reticular formation module."""
    total_cycles: int = 0
    avg_arousal: float = 0.0
    state_transitions: int = 0
    time_in_states: Dict[str, int] = field(default_factory=lambda: {
        s.value: 0 for s in WakeState
    })

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cycles': self.total_cycles,
            'avg_arousal': round(self.avg_arousal, 4),
            'state_transitions': self.state_transitions,
            'time_in_states': dict(self.time_in_states),
        }


# ─── Ascending Reticular Activating System ──────────────────────────────────

class AscendingActivatingSystem:
    """
    Controls global arousal level via a blend of sensory drive, circadian
    modulation, and inertial decay toward baseline.

    Arousal scale [0, 1]:
      0.0 = deep sleep
      0.3 = drowsy
      0.5 = relaxed awake
      0.7 = alert
      1.0 = hyperaroused
    """

    def __init__(self, arousal_decay: float = 0.05, sensory_gain: float = 1.0):
        self.arousal_decay = arousal_decay
        self.sensory_gain = sensory_gain

    def compute_arousal(
        self,
        sensory_input_level: float,
        current_arousal: float,
        circadian_phase: float,
    ) -> float:
        """
        Compute updated arousal from sensory drive and circadian phase.

        Args:
            sensory_input_level: Aggregate sensory intensity [0, 1].
            current_arousal: Previous arousal level [0, 1].
            circadian_phase: Circadian position [0, 1] where 0.5 = peak day,
                             0.0/1.0 = nadir (deep night).

        Returns:
            Updated arousal clamped to [0, 1].
        """
        # Circadian baseline: sinusoidal, peaks at phase=0.5
        circadian_baseline = 0.35 + 0.3 * np.sin(np.pi * circadian_phase)

        # Sensory drive pushes arousal upward
        sensory_drive = sensory_input_level * self.sensory_gain

        # Target arousal blends circadian baseline with sensory drive
        target = circadian_baseline + 0.4 * sensory_drive
        target = float(np.clip(target, 0.0, 1.0))

        # Arousal moves toward target with exponential smoothing
        # High sensory input produces faster rise (asymmetric dynamics)
        rise_rate = 0.15 + 0.25 * sensory_drive
        decay_rate = self.arousal_decay

        if target > current_arousal:
            alpha = rise_rate
        else:
            alpha = decay_rate

        new_arousal = current_arousal + alpha * (target - current_arousal)
        return float(np.clip(new_arousal, 0.0, 1.0))


# ─── Sensory Gating Mechanism ──────────────────────────────────────────────

class SensoryGatingMechanism:
    """
    Gates afferent sensory signals based on current arousal level.

    Low arousal produces high gating (few signals pass through).
    High arousal lowers the gate (signals pass with near-unity gain).
    The gain function is a steep sigmoid centred at arousal ~ 0.3.
    """

    @staticmethod
    def _arousal_gain(arousal: float) -> float:
        """Sigmoid gain: near-zero below 0.15, saturates above 0.6."""
        # Logistic: 1 / (1 + exp(-k*(x - x0)))  with k=12, x0=0.3
        return float(1.0 / (1.0 + np.exp(-12.0 * (arousal - 0.3))))

    def gate_sensory(self, signals: np.ndarray, arousal: float) -> np.ndarray:
        """
        Apply arousal-dependent gain modulation to sensory signals.

        Args:
            signals: Array of sensory signal amplitudes.
            arousal: Current arousal level [0, 1].

        Returns:
            Gated signals (same shape as input).
        """
        gain = self._arousal_gain(arousal)
        return signals * gain


# ─── Sleep-Wake Controller ──────────────────────────────────────────────────

# Ascending (waking) thresholds — arousal must exceed these to enter state
_UP_THRESHOLDS = {
    WakeState.LIGHT_SLEEP: 0.12,
    WakeState.DROWSY: 0.25,
    WakeState.AWAKE: 0.42,
    WakeState.ALERT: 0.65,
    WakeState.HYPERAROUSED: 0.88,
}

# Descending (sleeping) thresholds — arousal must drop below these to leave
_DOWN_THRESHOLDS = {
    WakeState.HYPERAROUSED: 0.82,
    WakeState.ALERT: 0.58,
    WakeState.AWAKE: 0.35,
    WakeState.DROWSY: 0.18,
    WakeState.LIGHT_SLEEP: 0.08,
}

# Ordered states from lowest to highest arousal
_STATE_ORDER = [
    WakeState.DEEP_SLEEP,
    WakeState.LIGHT_SLEEP,
    WakeState.DROWSY,
    WakeState.AWAKE,
    WakeState.ALERT,
    WakeState.HYPERAROUSED,
]


class SleepWakeController:
    """
    Maps continuous arousal to discrete vigilance states with hysteresis.

    Hysteresis means the threshold for *entering* a higher state is above
    the threshold for *leaving* it, preventing rapid oscillation near
    boundaries.  This mirrors biological sleep-wake inertia.
    """

    def __init__(self, hysteresis: float = 0.05):
        self.hysteresis = hysteresis
        self.current_state = WakeState.AWAKE

    def update_state(self, arousal: float) -> str:
        """
        Determine the vigilance state for the given arousal level.

        Args:
            arousal: Current arousal [0, 1].

        Returns:
            State name string (e.g. "alert").
        """
        idx = _STATE_ORDER.index(self.current_state)

        # Try to move UP
        while idx < len(_STATE_ORDER) - 1:
            next_state = _STATE_ORDER[idx + 1]
            threshold = _UP_THRESHOLDS[next_state] + self.hysteresis
            if arousal >= threshold:
                idx += 1
            else:
                break

        # Try to move DOWN
        while idx > 0:
            cur = _STATE_ORDER[idx]
            threshold = _DOWN_THRESHOLDS[cur] - self.hysteresis
            if arousal < threshold:
                idx -= 1
            else:
                break

        self.current_state = _STATE_ORDER[idx]
        return self.current_state.value


# ─── Motor Tone Regulator ──────────────────────────────────────────────────

class MotorToneRegulator:
    """
    Regulates motor readiness proportionally to arousal.

    During deep sleep and REM, motor tone is strongly suppressed (atonia).
    Alert states maintain high motor readiness; hyperarousal produces a
    slight boost from alert-signal input (startle / defensive posture).
    """

    @staticmethod
    def compute_motor_tone(arousal: float, alert_signals: float = 0.0) -> float:
        """
        Compute motor tone [0, 1].

        Args:
            arousal: Global arousal level [0, 1].
            alert_signals: External alert/startle input [0, 1].

        Returns:
            Motor tone value [0, 1].
        """
        # Baseline motor tone follows a smooth ramp with sleep suppression
        if arousal < 0.15:
            base = 0.02  # near-atonia
        elif arousal < 0.30:
            base = 0.1 + 0.3 * (arousal - 0.15) / 0.15
        else:
            base = 0.4 + 0.5 * (arousal - 0.30) / 0.70

        # Alert signals provide an additive boost (clamped)
        boosted = base + 0.2 * alert_signals
        return float(np.clip(boosted, 0.0, 1.0))


# ─── Main Module: Reticular Formation ──────────────────────────────────────

class ReticularFormation:
    """
    Integrated reticular formation module combining the ARAS, sensory
    gating, sleep-wake control, and motor tone regulation.

    Constructor kwargs correspond to YAML config under 'reticular_formation'.
    """

    def __init__(
        self,
        arousal_decay: float = 0.05,
        sensory_gain: float = 1.0,
        circadian_period: int = 86400,
        hysteresis: float = 0.05,
    ):
        self.arousal_decay = arousal_decay
        self.sensory_gain = sensory_gain
        self.circadian_period = circadian_period
        self.hysteresis = hysteresis

        # Sub-components
        self.aras = AscendingActivatingSystem(arousal_decay, sensory_gain)
        self.sensory_gate = SensoryGatingMechanism()
        self.sleep_wake = SleepWakeController(hysteresis)
        self.motor_reg = MotorToneRegulator()

        # Internal state
        self._arousal: float = 0.5
        self._motor_tone: float = 0.4
        self._state: str = WakeState.AWAKE.value

        # History
        self._arousal_history: deque = deque(maxlen=500)
        self._arousal_sum: float = 0.0

        # Stats
        self._stats = ReticularFormationStats()
        self._prev_state: str = self._state

        logger.info(
            "ReticularFormation initialised  decay=%.3f  gain=%.2f  "
            "hysteresis=%.3f",
            arousal_decay, sensory_gain, hysteresis,
        )

    # ── Core processing ──────────────────────────────────────────────────

    def process(
        self,
        sensory_input_level: float,
        circadian_phase: float = 0.5,
        alert_signals: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Run one cycle of the reticular formation.

        Args:
            sensory_input_level: Aggregate sensory intensity [0, 1].
            circadian_phase: Position in circadian cycle [0, 1].
            alert_signals: External alert / startle input [0, 1].

        Returns:
            Dict with keys: arousal, state, sensory_gain, motor_tone,
            gated_signal_strength.
        """
        sensory_input_level = float(np.clip(sensory_input_level, 0.0, 1.0))
        circadian_phase = float(np.clip(circadian_phase, 0.0, 1.0))
        alert_signals = float(np.clip(alert_signals, 0.0, 1.0))

        # 1. Update arousal via ARAS
        self._arousal = self.aras.compute_arousal(
            sensory_input_level, self._arousal, circadian_phase,
        )

        # 2. Determine vigilance state (with hysteresis)
        self._state = self.sleep_wake.update_state(self._arousal)

        # 3. Compute gated signal strength (scalar demo signal)
        demo_signal = np.array([sensory_input_level])
        gated = self.sensory_gate.gate_sensory(demo_signal, self._arousal)
        gated_strength = float(gated[0])

        # 4. Compute current sensory gain coefficient
        current_gain = SensoryGatingMechanism._arousal_gain(self._arousal)

        # 5. Motor tone
        self._motor_tone = self.motor_reg.compute_motor_tone(
            self._arousal, alert_signals,
        )

        # 6. Update stats
        self._arousal_history.append(self._arousal)
        self._arousal_sum += self._arousal
        self._stats.total_cycles += 1
        self._stats.avg_arousal = (
            self._arousal_sum / self._stats.total_cycles
        )
        self._stats.time_in_states[self._state] = (
            self._stats.time_in_states.get(self._state, 0) + 1
        )
        if self._state != self._prev_state:
            self._stats.state_transitions += 1
            logger.debug(
                "State transition: %s -> %s  (arousal=%.3f)",
                self._prev_state, self._state, self._arousal,
            )
        self._prev_state = self._state

        return {
            'arousal': round(self._arousal, 4),
            'state': self._state,
            'sensory_gain': round(current_gain, 4),
            'motor_tone': round(self._motor_tone, 4),
            'gated_signal_strength': round(gated_strength, 4),
        }

    def arousal_state_classification(self) -> Dict[str, Any]:
        """
        Classify current arousal state (Moruzzi & Magoun, 1949).

        The ARAS (Ascending Reticular Activating System) maintains a
        continuum of arousal from coma to hyperarousal. Each state has
        distinct cognitive characteristics and optimal use cases.

        Returns:
            Dict with state_name, level, cognitive_capacity, recommendation
        """
        arousal = self._arousal

        if arousal < 0.1:
            state_name = 'coma'
            cognitive_capacity = 0.0
            recommendation = 'emergency_restart'
        elif arousal < 0.25:
            state_name = 'deep_sleep'
            cognitive_capacity = 0.05
            recommendation = 'consolidation_only'
        elif arousal < 0.4:
            state_name = 'light_sleep'
            cognitive_capacity = 0.15
            recommendation = 'memory_replay'
        elif arousal < 0.55:
            state_name = 'drowsy'
            cognitive_capacity = 0.4
            recommendation = 'routine_tasks_only'
        elif arousal < 0.75:
            state_name = 'alert'
            cognitive_capacity = 1.0
            recommendation = 'optimal_for_all_tasks'
        elif arousal < 0.9:
            state_name = 'hyperaroused'
            cognitive_capacity = 0.7
            recommendation = 'simple_urgent_tasks'
        else:
            state_name = 'panic'
            cognitive_capacity = 0.3
            recommendation = 'defensive_actions_only'

        return {
            'state_name': state_name,
            'arousal_level': round(arousal, 4),
            'cognitive_capacity': cognitive_capacity,
            'recommendation': recommendation,
        }

    # ── Accessors ────────────────────────────────────────────────────────

    def get_state(self) -> Dict[str, Any]:
        """Return current internal state snapshot."""
        return {
            'arousal': round(self._arousal, 4),
            'state': self._state,
            'motor_tone': round(self._motor_tone, 4),
            'arousal_history_len': len(self._arousal_history),
            'stats': self._stats.to_dict(),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return cumulative statistics."""
        return self._stats.to_dict()

    def reset(self) -> None:
        """Reset all internal state to defaults."""
        self._arousal = 0.5
        self._motor_tone = 0.4
        self._state = WakeState.AWAKE.value
        self._prev_state = self._state
        self._arousal_history.clear()
        self._arousal_sum = 0.0
        self.sleep_wake.current_state = WakeState.AWAKE
        self._stats = ReticularFormationStats()
        logger.info("ReticularFormation reset to defaults")

    def to_dict(self) -> Dict[str, Any]:
        """Serialise full module state for snapshot / persistence."""
        return {
            'arousal': round(self._arousal, 4),
            'state': self._state,
            'motor_tone': round(self._motor_tone, 4),
            'arousal_history': [round(a, 4) for a in self._arousal_history],
            'config': {
                'arousal_decay': self.arousal_decay,
                'sensory_gain': self.sensory_gain,
                'circadian_period': self.circadian_period,
                'hysteresis': self.hysteresis,
            },
            'stats': self._stats.to_dict(),
        }

    # ── Factory ──────────────────────────────────────────────────────────

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'ReticularFormation':
        """Create a ReticularFormation from a YAML config dict."""
        rf = config.get('reticular_formation', {})
        return cls(
            arousal_decay=rf.get('arousal_decay', 0.05),
            sensory_gain=rf.get('sensory_gain', 1.0),
            circadian_period=rf.get('circadian_period', 86400),
            hysteresis=rf.get('hysteresis', 0.05),
        )
