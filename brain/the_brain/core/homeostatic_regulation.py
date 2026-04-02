"""
Homeostatic Regulation - Energy/Fatigue/Sleep Model for Tahlamus

Real brains have metabolic constraints. Neurons deplete ATP, neurotransmitters
get exhausted, and performance degrades without rest. This module models:

1. Energy Budget: Processing depletes energy; rest restores it.
2. Cognitive Fatigue: Repeated high-complexity tasks degrade performance.
3. Sleep Pressure: Extended operation builds homeostatic sleep drive.
4. Circadian Rhythm: Simple sinusoidal activity/alertness oscillation.
5. Allostatic Load: Chronic stress accumulates and degrades baseline.

Integration with cognitive loop:
- Energy level modulates gating temperature (low energy → more exploration noise)
- Fatigue level reduces attention strength
- Sleep pressure influences dream mode threshold
- Allostatic load affects baseline neuromodulation

The brain heartbeat calls `tick()` every cycle to update these values.
"""

import numpy as np
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class HomeostaticState:
    """Current homeostatic state of the brain."""

    # Energy (0 = depleted, 1 = fully charged)
    energy: float = 1.0

    # Cognitive fatigue (0 = fresh, 1 = exhausted)
    fatigue: float = 0.0

    # Sleep pressure (0 = rested, 1 = must sleep)
    sleep_pressure: float = 0.0

    # Allostatic load (0 = no stress, 1 = chronic overload)
    allostatic_load: float = 0.0

    # Circadian phase (0-2π, where π/2 = peak alertness)
    circadian_phase: float = 0.0

    # Performance multiplier (computed from above)
    performance_factor: float = 1.0

    # Task counter (resets on rest)
    tasks_since_rest: int = 0

    # Time tracking
    uptime_seconds: float = 0.0
    last_rest_time: float = 0.0

    def to_dict(self) -> Dict:
        return {
            'energy': round(self.energy, 3),
            'fatigue': round(self.fatigue, 3),
            'sleep_pressure': round(self.sleep_pressure, 3),
            'allostatic_load': round(self.allostatic_load, 3),
            'circadian_phase': round(self.circadian_phase, 3),
            'performance_factor': round(self.performance_factor, 3),
            'tasks_since_rest': self.tasks_since_rest,
            'uptime_seconds': round(self.uptime_seconds, 1),
        }


@dataclass
class HomeostaticConfig:
    """Configuration for homeostatic regulation."""

    # Energy parameters
    energy_per_task: float = 0.02          # Energy consumed per task
    energy_recovery_rate: float = 0.01     # Energy recovered per idle tick
    energy_rest_recovery: float = 0.3      # Energy recovered during rest/dream

    # Fatigue parameters
    fatigue_per_task: float = 0.015        # Fatigue accumulated per task
    fatigue_decay_rate: float = 0.005      # Fatigue recovered per idle tick
    fatigue_complexity_multiplier: float = 1.5  # Extra fatigue for complex tasks

    # Sleep pressure
    sleep_accumulation_rate: float = 0.001  # Sleep pressure per tick
    sleep_dream_reduction: float = 0.5     # Sleep pressure reduced by dream mode
    sleep_threshold: float = 0.8           # Trigger forced dream mode above this

    # Allostatic load
    stress_accumulation_rate: float = 0.001   # Chronic stress buildup rate
    stress_recovery_rate: float = 0.0005      # Very slow baseline recovery
    stress_threshold: float = 0.5             # Above this, performance degrades faster

    # Circadian rhythm
    circadian_period_seconds: float = 3600.0  # Full cycle period (1 hour for demo)
    circadian_amplitude: float = 0.1          # How much circadian affects performance

    # Performance thresholds
    low_energy_threshold: float = 0.3         # Below this, temperature increases
    high_fatigue_threshold: float = 0.7       # Above this, attention degrades

    @classmethod
    def from_yaml(cls, yaml_config: Dict) -> 'HomeostaticConfig':
        """Create from YAML config dict."""
        h_cfg = yaml_config.get('homeostatic', {})
        kwargs = {}
        for field_name in cls.__dataclass_fields__:
            if field_name in h_cfg:
                kwargs[field_name] = h_cfg[field_name]
        return cls(**kwargs)


class HomeostaticRegulator:
    """
    Manages brain energy, fatigue, sleep pressure, and allostatic load.

    Called by the brain heartbeat on every tick and by the cognitive loop
    after each task processing cycle.
    """

    def __init__(self, config: Optional[HomeostaticConfig] = None):
        self._config = config or HomeostaticConfig()
        self._state = HomeostaticState(last_rest_time=time.time())
        self._start_time = time.time()

    @property
    def state(self) -> HomeostaticState:
        return self._state

    def on_task_processed(self, complexity: float = 0.5, success: bool = True):
        """
        Called after each task is processed. Depletes energy, accumulates fatigue.

        Args:
            complexity: Task complexity (0-1). Higher = more costly.
            success: Whether task succeeded. Failure adds stress.
        """
        cfg = self._config

        # Energy depletion (complex tasks cost more)
        energy_cost = cfg.energy_per_task * (1.0 + complexity)
        self._state.energy = max(0.0, self._state.energy - energy_cost)

        # Fatigue accumulation (complex tasks fatigue more)
        fatigue_gain = cfg.fatigue_per_task
        if complexity > 0.7:
            fatigue_gain *= cfg.fatigue_complexity_multiplier
        self._state.fatigue = min(1.0, self._state.fatigue + fatigue_gain)

        # Failure adds allostatic load (stress)
        if not success:
            self._state.allostatic_load = min(
                1.0, self._state.allostatic_load + cfg.stress_accumulation_rate * 5
            )

        self._state.tasks_since_rest += 1
        self._update_performance_factor()

    def tick(self, dt_seconds: float = 30.0, is_idle: bool = True):
        """
        Called by brain heartbeat on each tick.

        Args:
            dt_seconds: Time since last tick.
            is_idle: Whether brain is idle (no active tasks).
        """
        cfg = self._config

        # Update uptime
        self._state.uptime_seconds = time.time() - self._start_time

        # Sleep pressure always accumulates (homeostatic sleep drive)
        self._state.sleep_pressure = min(
            1.0,
            self._state.sleep_pressure + cfg.sleep_accumulation_rate * (dt_seconds / 30.0)
        )

        # Circadian rhythm update
        self._state.circadian_phase = (
            (self._state.uptime_seconds / cfg.circadian_period_seconds) * 2 * np.pi
        ) % (2 * np.pi)

        if is_idle:
            # Recovery during idle
            self._state.energy = min(1.0, self._state.energy + cfg.energy_recovery_rate)
            self._state.fatigue = max(0.0, self._state.fatigue - cfg.fatigue_decay_rate)
            self._state.allostatic_load = max(
                0.0, self._state.allostatic_load - cfg.stress_recovery_rate
            )
        else:
            # Slow allostatic load accumulation during active processing
            self._state.allostatic_load = min(
                1.0, self._state.allostatic_load + cfg.stress_accumulation_rate
            )

        self._update_performance_factor()

    def on_dream_mode(self):
        """Called when dream mode activates. Significant recovery."""
        cfg = self._config

        self._state.energy = min(1.0, self._state.energy + cfg.energy_rest_recovery)
        self._state.sleep_pressure = max(
            0.0, self._state.sleep_pressure - cfg.sleep_dream_reduction
        )
        self._state.fatigue = max(0.0, self._state.fatigue * 0.5)
        self._state.tasks_since_rest = 0
        self._state.last_rest_time = time.time()

        logger.debug(
            f"Dream mode recovery: energy={self._state.energy:.2f}, "
            f"sleep_pressure={self._state.sleep_pressure:.2f}"
        )

    def should_trigger_dream(self) -> bool:
        """Check if sleep pressure warrants forced dream mode."""
        return self._state.sleep_pressure >= self._config.sleep_threshold

    def get_temperature_adjustment(self) -> float:
        """
        Get gating temperature adjustment based on homeostatic state.

        Low energy → higher temperature (more exploration/noise)
        High fatigue → higher temperature (less decisive)
        """
        temp_adj = 0.0

        if self._state.energy < self._config.low_energy_threshold:
            # Low energy → increase temperature (more random, less precise)
            energy_deficit = self._config.low_energy_threshold - self._state.energy
            temp_adj += energy_deficit * 0.5

        if self._state.fatigue > self._config.high_fatigue_threshold:
            # High fatigue → increase temperature
            fatigue_excess = self._state.fatigue - self._config.high_fatigue_threshold
            temp_adj += fatigue_excess * 0.3

        return temp_adj

    def get_attention_degradation(self) -> float:
        """
        Get attention strength multiplier.
        Returns 1.0 when fresh, decreases with fatigue and low energy.
        """
        # Base performance factor
        factor = self._state.performance_factor

        # Additional circadian modulation
        circadian_mod = self._config.circadian_amplitude * np.sin(self._state.circadian_phase)
        factor += circadian_mod

        return np.clip(factor, 0.3, 1.0)

    def _update_performance_factor(self):
        """Recompute performance factor from current state."""
        # Base: 1.0 when fully rested
        factor = 1.0

        # Energy: below 50% starts degrading
        if self._state.energy < 0.5:
            factor *= (0.5 + self._state.energy)

        # Fatigue: above 50% starts degrading
        if self._state.fatigue > 0.5:
            factor *= (1.5 - self._state.fatigue)

        # Allostatic load: chronic stress degrades baseline
        if self._state.allostatic_load > self._config.stress_threshold:
            excess = self._state.allostatic_load - self._config.stress_threshold
            factor *= (1.0 - 0.5 * excess)

        self._state.performance_factor = np.clip(factor, 0.2, 1.0)
