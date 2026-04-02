"""
Hypothalamus Module - Neuroscience Architecture Extension Phase A3

Computational model of the hypothalamus for homeostatic drives,
circadian rhythms, stress response, and motivation signaling.

Neuroscience basis:
- Lateral Hypothalamus: Appetite, approach behavior, orexin/hypocretin
- Ventromedial Hypothalamus: Satiety, avoidance
- Suprachiasmatic Nucleus: Circadian clock (~24h oscillator)
- Paraventricular Nucleus: HPA axis stress response (CRH -> ACTH -> cortisol)
- Homeostatic comparator: set-point vs. current state

Key references:
- Saper et al. (2005): Hypothalamic regulation of sleep and circadian rhythms
- Berthoud (2002): Multiple neural systems controlling food intake
- Ulrich-Lai & Herman (2009): Neural regulation of HPA axis

Integration points:
- Input: Interoceptive signals (Insular Cortex), reward signals (NAcc)
- Output: Drive signals to Motivation System, arousal to Neuromodulation
- Wiring: agent_loop.hypothalamus = HypothalamusModule.from_yaml(config)
- Upgrade: Extends/complements the abstract homeostatic_regulation.py
"""

import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.hypothalamus')


# ─── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class DriveState:
    """Current state of all homeostatic drives."""
    hunger: float = 0.5       # 0=sated, 1=starving
    thirst: float = 0.5       # 0=hydrated, 1=dehydrated
    temperature: float = 0.5  # 0=cold, 0.5=optimal, 1=hot
    sleep_pressure: float = 0.3  # 0=rested, 1=exhausted
    social: float = 0.5       # 0=isolated, 1=over-stimulated
    curiosity: float = 0.5    # 0=bored, 1=overwhelmed

    def to_vector(self) -> np.ndarray:
        return np.array([
            self.hunger, self.thirst, self.temperature,
            self.sleep_pressure, self.social, self.curiosity
        ], dtype=np.float32)

    def from_vector(self, vec: np.ndarray):
        v = np.clip(vec, 0.0, 1.0)
        self.hunger = float(v[0])
        self.thirst = float(v[1])
        self.temperature = float(v[2])
        self.sleep_pressure = float(v[3])
        self.social = float(v[4]) if len(v) > 4 else self.social
        self.curiosity = float(v[5]) if len(v) > 5 else self.curiosity

    def total_deviation(self, setpoints: np.ndarray) -> float:
        """Total deviation from homeostatic setpoints."""
        return float(np.abs(self.to_vector() - setpoints).sum())

    def most_urgent_drive(self, setpoints: np.ndarray) -> Tuple[str, float]:
        """Return the drive with the largest deviation from setpoint."""
        names = ['hunger', 'thirst', 'temperature', 'sleep_pressure', 'social', 'curiosity']
        deviations = np.abs(self.to_vector() - setpoints)
        idx = int(np.argmax(deviations))
        return names[idx], float(deviations[idx])

    def to_dict(self) -> Dict[str, float]:
        return {
            'hunger': round(self.hunger, 3),
            'thirst': round(self.thirst, 3),
            'temperature': round(self.temperature, 3),
            'sleep_pressure': round(self.sleep_pressure, 3),
            'social': round(self.social, 3),
            'curiosity': round(self.curiosity, 3),
        }


@dataclass
class HypothalamusStats:
    """Aggregate stats for the hypothalamus."""
    total_drive_updates: int = 0
    circadian_phase: float = 0.0
    stress_level: float = 0.0
    arousal_output: float = 0.5
    most_urgent_drive: str = ""
    deviation_from_homeostasis: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_drive_updates': self.total_drive_updates,
            'circadian_phase': round(self.circadian_phase, 3),
            'stress_level': round(self.stress_level, 3),
            'arousal_output': round(self.arousal_output, 3),
            'most_urgent_drive': self.most_urgent_drive,
            'deviation_from_homeostasis': round(self.deviation_from_homeostasis, 3),
        }


# ─── Lateral Hypothalamus ─────────────────────────────────────────────────────

class LateralHypothalamus:
    """
    Lateral Hypothalamus: approach behavior and appetite.

    Drives approach/appetitive behavior when needs are unmet.
    Orexin/hypocretin neurons promote wakefulness and feeding.
    """

    def __init__(self, approach_threshold: float = 0.3):
        self.approach_threshold = approach_threshold

    def compute_approach_drive(self, drives: DriveState, setpoints: np.ndarray) -> float:
        """
        Compute approach motivation based on drive deficits.

        Returns:
            Approach drive [0, 1] - higher means stronger approach motivation
        """
        deviations = drives.to_vector() - setpoints
        # Positive deviations = need is above setpoint (too much)
        # Negative deviations = need is below setpoint (need more)
        deficits = np.maximum(0, -deviations)  # Only care about deficits
        approach = float(np.max(deficits))
        return min(1.0, max(0.0, approach))

    def should_approach(self, approach_drive: float) -> bool:
        return approach_drive > self.approach_threshold


# ─── Ventromedial Hypothalamus ─────────────────────────────────────────────────

class VentromedialHypothalamus:
    """
    Ventromedial Hypothalamus: satiety and avoidance.

    Signals satiation and drives avoidance when needs are over-fulfilled
    or when threats are detected.
    """

    def __init__(self, satiety_threshold: float = 0.7):
        self.satiety_threshold = satiety_threshold

    def compute_avoidance_drive(self, drives: DriveState, setpoints: np.ndarray) -> float:
        """
        Compute avoidance motivation based on drive excesses.

        Returns:
            Avoidance drive [0, 1]
        """
        deviations = drives.to_vector() - setpoints
        excesses = np.maximum(0, deviations)  # Over-fulfillment
        avoidance = float(np.max(excesses))
        return min(1.0, max(0.0, avoidance))

    def is_satiated(self, avoidance_drive: float) -> bool:
        return avoidance_drive > self.satiety_threshold


# ─── Suprachiasmatic Nucleus ───────────────────────────────────────────────────

class SuprachiasmaticNucleus:
    """
    Suprachiasmatic Nucleus (SCN): the master circadian clock.

    Generates a ~24h oscillation that modulates arousal, sleep pressure,
    cognitive performance, and hormone release.

    Saper et al. (2005): SCN synchronizes all peripheral clocks.
    """

    def __init__(self, cycle_period: float = 86400.0, initial_phase: float = 0.0):
        self.cycle_period = cycle_period  # seconds (24h = 86400)
        self._phase = initial_phase  # [0, 2*pi]
        self._start_time = time.time()

    def tick(self, elapsed_seconds: Optional[float] = None) -> float:
        """
        Update circadian phase.

        Args:
            elapsed_seconds: Time elapsed (uses real time if None)

        Returns:
            Current phase [0, 2*pi]
        """
        if elapsed_seconds is not None:
            dt = elapsed_seconds
        else:
            dt = time.time() - self._start_time

        self._phase = (2.0 * math.pi * dt / self.cycle_period) % (2.0 * math.pi)
        return self._phase

    def get_arousal_modulation(self) -> float:
        """
        Get circadian arousal modulation.

        Returns:
            Arousal factor [0, 1] - high during "day", low during "night"
        """
        # Cosine: peak at phase=0 (morning), trough at phase=pi (night)
        return 0.5 + 0.5 * math.cos(self._phase)

    def get_sleep_pressure_rate(self) -> float:
        """
        Get circadian modulation of sleep pressure accumulation.

        Sleep pressure builds faster during the "night" phase.
        """
        # Inverse of arousal
        return 0.5 - 0.5 * math.cos(self._phase)

    @property
    def phase(self) -> float:
        return self._phase

    def to_dict(self) -> Dict[str, Any]:
        return {
            'phase': round(self._phase, 3),
            'arousal_modulation': round(self.get_arousal_modulation(), 3),
            'sleep_pressure_rate': round(self.get_sleep_pressure_rate(), 3),
            'cycle_period': self.cycle_period,
        }


# ─── HPA Axis ─────────────────────────────────────────────────────────────────

class HPAAxis:
    """
    Hypothalamic-Pituitary-Adrenal axis for stress response.

    CRH (hypothalamus) -> ACTH (pituitary) -> Cortisol (adrenal)
    Cortisol provides negative feedback to shut down the response.

    Ulrich-Lai & Herman (2009): Neural regulation of endocrine
    stress responses.
    """

    def __init__(self, stress_threshold: float = 0.8, recovery_rate: float = 0.02):
        self.stress_threshold = stress_threshold
        self.recovery_rate = recovery_rate
        self._cortisol = 0.0  # [0, 1]
        self._crh = 0.0
        self._stress_history = deque(maxlen=100)

    def process_stressor(self, stressor_intensity: float) -> float:
        """
        Process a stressor through the HPA axis.

        Args:
            stressor_intensity: Intensity of stressor [0, 1]

        Returns:
            Current cortisol level after processing
        """
        intensity = max(0.0, min(1.0, stressor_intensity))

        # CRH release proportional to stressor intensity
        self._crh = intensity

        # Cortisol rises, but with negative feedback
        cortisol_rise = self._crh * (1.0 - self._cortisol)  # Diminishing returns
        self._cortisol = min(1.0, self._cortisol + cortisol_rise * 0.3)

        self._stress_history.append(self._cortisol)
        return self._cortisol

    def recover(self) -> float:
        """
        Natural cortisol recovery (negative feedback).

        Returns:
            Current cortisol level after recovery
        """
        self._cortisol = max(0.0, self._cortisol - self.recovery_rate)
        self._crh = max(0.0, self._crh - self.recovery_rate * 2)
        return self._cortisol

    @property
    def cortisol(self) -> float:
        return self._cortisol

    @property
    def is_stressed(self) -> bool:
        return self._cortisol > self.stress_threshold

    def get_chronic_stress(self) -> float:
        """Return average cortisol over recent history."""
        if not self._stress_history:
            return 0.0
        return float(np.mean(list(self._stress_history)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'cortisol': round(self._cortisol, 3),
            'crh': round(self._crh, 3),
            'is_stressed': self.is_stressed,
            'chronic_stress': round(self.get_chronic_stress(), 3),
        }


# ─── Homeostatic Comparator ───────────────────────────────────────────────────

class HomeostaticComparator:
    """
    Compares current drive state against setpoints and generates
    error signals for each drive.

    This is the core homeostatic control loop:
    setpoint -> comparator -> error -> effector -> drives -> (feedback)
    """

    def __init__(self, setpoints: Optional[np.ndarray] = None):
        # Default setpoints: moderate levels for all drives
        if setpoints is not None:
            self.setpoints = np.asarray(setpoints, dtype=np.float32)
        else:
            self.setpoints = np.array([0.3, 0.3, 0.5, 0.3, 0.5, 0.5], dtype=np.float32)

    def compute_error(self, drives: DriveState) -> np.ndarray:
        """
        Compute homeostatic error for each drive.

        Positive error = drive too high (need to reduce)
        Negative error = drive too low (need to increase)
        """
        return drives.to_vector() - self.setpoints

    def compute_urgency(self, drives: DriveState) -> float:
        """Return overall homeostatic urgency [0, 1]."""
        errors = np.abs(self.compute_error(drives))
        return float(np.clip(errors.max(), 0.0, 1.0))

    def to_dict(self) -> Dict[str, Any]:
        names = ['hunger', 'thirst', 'temperature', 'sleep_pressure', 'social', 'curiosity']
        return {
            'setpoints': {names[i]: round(float(self.setpoints[i]), 3)
                         for i in range(len(names))},
        }


# ─── Main Hypothalamus Module ─────────────────────────────────────────────────

class HypothalamusModule:
    """
    Complete hypothalamus module integrating all sub-nuclei.

    Functions:
    1. Homeostatic drive management (comparator + lateral/ventromedial)
    2. Circadian rhythm generation (SCN)
    3. Stress response (HPA axis)
    4. Arousal/motivation output signal
    """

    def __init__(
        self,
        setpoints: Optional[np.ndarray] = None,
        circadian_period: float = 86400.0,
        stress_threshold: float = 0.8,
        sleep_pressure_rate: float = 0.01,
        approach_threshold: float = 0.3,
        satiety_threshold: float = 0.7,
    ):
        self.drives = DriveState()
        self.comparator = HomeostaticComparator(setpoints)
        self.lateral = LateralHypothalamus(approach_threshold)
        self.ventromedial = VentromedialHypothalamus(satiety_threshold)
        self.scn = SuprachiasmaticNucleus(circadian_period)
        self.hpa = HPAAxis(stress_threshold)

        self._sleep_pressure_rate = sleep_pressure_rate
        self._stats = HypothalamusStats()

    def update_drives(
        self,
        external_signals: Optional[Dict[str, float]] = None,
        elapsed_seconds: float = 1.0
    ) -> Dict[str, Any]:
        """
        Update all drives based on elapsed time and external signals.

        Args:
            external_signals: Dict of drive adjustments (e.g., {'hunger': -0.1} for eating)
            elapsed_seconds: Time elapsed since last update

        Returns:
            Dict with drive state, urgency, approach/avoidance, arousal
        """
        # 1. Natural drive drift over time
        time_factor = elapsed_seconds / 3600.0  # Normalize to hours
        self.drives.hunger = min(1.0, self.drives.hunger + 0.02 * time_factor)
        self.drives.thirst = min(1.0, self.drives.thirst + 0.03 * time_factor)

        # Sleep pressure modulated by circadian phase
        circadian_sleep_rate = self.scn.get_sleep_pressure_rate()
        self.drives.sleep_pressure = min(1.0,
            self.drives.sleep_pressure + self._sleep_pressure_rate * circadian_sleep_rate * time_factor)

        # 2. Apply external signals (e.g., eating reduces hunger)
        if external_signals:
            for drive_name, delta in external_signals.items():
                if hasattr(self.drives, drive_name):
                    current = getattr(self.drives, drive_name)
                    setattr(self.drives, drive_name,
                            max(0.0, min(1.0, current + delta)))

        # 3. Update circadian clock
        self.scn.tick(elapsed_seconds)

        # 4. Stress recovery
        self.hpa.recover()

        # 5. Compute drive signals
        setpoints = self.comparator.setpoints
        approach_drive = self.lateral.compute_approach_drive(self.drives, setpoints)
        avoidance_drive = self.ventromedial.compute_avoidance_drive(self.drives, setpoints)

        # 6. Compute arousal output
        circadian_arousal = self.scn.get_arousal_modulation()
        stress_arousal = self.hpa.cortisol * 0.5
        drive_arousal = approach_drive * 0.3
        arousal = min(1.0, circadian_arousal * 0.5 + stress_arousal + drive_arousal)

        # 7. Determine most urgent drive
        urgent_name, urgent_dev = self.drives.most_urgent_drive(setpoints)

        # Update stats
        self._stats.total_drive_updates += 1
        self._stats.circadian_phase = self.scn.phase
        self._stats.stress_level = self.hpa.cortisol
        self._stats.arousal_output = arousal
        self._stats.most_urgent_drive = urgent_name
        self._stats.deviation_from_homeostasis = self.drives.total_deviation(setpoints)

        return {
            'drives': self.drives.to_dict(),
            'urgency': self.comparator.compute_urgency(self.drives),
            'approach_drive': approach_drive,
            'avoidance_drive': avoidance_drive,
            'arousal': arousal,
            'most_urgent': urgent_name,
            'stress': self.hpa.cortisol,
            'circadian_phase': self.scn.phase,
        }

    def process_stressor(self, intensity: float) -> float:
        """Process an external stressor through HPA axis."""
        return self.hpa.process_stressor(intensity)

    def satisfy_drive(self, drive_name: str, amount: float = 0.3):
        """Reduce a specific drive (e.g., eating satisfies hunger)."""
        if hasattr(self.drives, drive_name):
            current = getattr(self.drives, drive_name)
            setattr(self.drives, drive_name, max(0.0, current - amount))

    def compute_allostatic_load(self) -> Dict[str, float]:
        """
        Compute allostatic load — cumulative wear from chronic stress.

        Sterling (2012) / McEwen (2003): Allostasis = stability through
        change. The hypothalamus doesn't just maintain homeostasis (fixed
        setpoints) but dynamically adjusts setpoints based on predicted
        demands. Allostatic load = the cost of this constant adaptation.

        Returns:
            Dict with allostatic_load, adaptive_capacity, burnout_risk
        """
        # Drive deviations from setpoints
        errors = self.comparator.compute_error(self.drives)
        total_deviation = float(np.sum(np.abs(errors)))

        # HPA axis chronic stress contribution
        chronic_stress = self.hpa.get_chronic_stress()

        # Allostatic load: cumulative stress + drive instability
        allostatic_load = chronic_stress * 0.6 + total_deviation * 0.4
        allostatic_load = min(1.0, allostatic_load)

        # Adaptive capacity: inversely related to load
        adaptive_capacity = max(0.0, 1.0 - allostatic_load * 0.8)

        # Burnout risk: high load + low recovery
        burnout_risk = max(0.0, allostatic_load - adaptive_capacity)

        return {
            'allostatic_load': round(allostatic_load, 4),
            'adaptive_capacity': round(adaptive_capacity, 4),
            'burnout_risk': round(min(1.0, burnout_risk), 4),
            'chronic_stress': round(chronic_stress, 4),
            'drive_deviation': round(total_deviation, 4),
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'drives': self.drives.to_dict(),
            'comparator': self.comparator.to_dict(),
            'circadian': self.scn.to_dict(),
            'hpa': self.hpa.to_dict(),
        }

    def get_stats(self) -> HypothalamusStats:
        return self._stats

    def reset(self):
        self.drives = DriveState()
        self.hpa._cortisol = 0.0
        self.hpa._crh = 0.0
        self._stats = HypothalamusStats()

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'HypothalamusModule':
        """
        Create HypothalamusModule from YAML configuration.

        Expected config:
            hypothalamus:
              hunger_setpoint: 0.5
              sleep_pressure_rate: 0.01
              circadian_period: 86400
              stress_threshold: 0.8
        """
        ht = config.get('hypothalamus', {})

        setpoints = None
        if 'hunger_setpoint' in ht:
            setpoints = np.array([
                ht.get('hunger_setpoint', 0.3),
                ht.get('thirst_setpoint', 0.3),
                ht.get('temperature_setpoint', 0.5),
                ht.get('sleep_setpoint', 0.3),
                ht.get('social_setpoint', 0.5),
                ht.get('curiosity_setpoint', 0.5),
            ], dtype=np.float32)

        return cls(
            setpoints=setpoints,
            circadian_period=ht.get('circadian_period', 86400.0),
            stress_threshold=ht.get('stress_threshold', 0.8),
            sleep_pressure_rate=ht.get('sleep_pressure_rate', 0.01),
        )
