"""
Pineal Gland — Melatonin Production and Circadian Entrainment

Endocrine gland producing melatonin, inversely proportional to light.
Melatonin is high at night (dark) and low during the day (bright light
suppresses production). Circadian entrainment synchronises the internal
clock to external zeitgebers.

References:
    - Reiter (1991): Melatonin and circadian entrainment
    - Czeisler et al. (1999): Light-dependent suppression of melatonin
"""

import logging
import numpy as np
from typing import Dict, Any
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger('brain.pineal')


# ============================================================================
# Stats Dataclass
# ============================================================================

@dataclass
class PinealGlandStats:
    """Accumulated statistics for the pineal gland module."""
    total_cycles: int = 0
    avg_melatonin: float = 0.0
    dark_phase_ratio: float = 0.0
    entrainment_events: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cycles': self.total_cycles,
            'avg_melatonin': round(self.avg_melatonin, 4),
            'dark_phase_ratio': round(self.dark_phase_ratio, 4),
            'entrainment_events': self.entrainment_events,
        }


# ============================================================================
# Sub-component Classes
# ============================================================================

class MelatoninProduction:
    """Melatonin synthesis driven by light exposure and circadian phase."""

    def __init__(self, baseline: float = 0.5, light_sensitivity: float = 1.0):
        self.baseline = np.clip(baseline, 0.0, 1.0)
        self.light_sensitivity = max(light_sensitivity, 0.0)

    def compute_melatonin(self, light_exposure: float, circadian_phase: float) -> Dict[str, float]:
        """Compute melatonin_level, sleep_pressure, and circadian_strength.
        light_exposure: 0 (dark) to 1 (bright). circadian_phase: 0/1=midnight, 0.5=midday."""
        light = float(np.clip(light_exposure, 0.0, 1.0))
        phase = float(np.clip(circadian_phase, 0.0, 1.0))
        # Light suppression: high light => low melatonin
        suppression = float(np.clip(1.0 - self.light_sensitivity * light, 0.0, 1.0))
        # Circadian modulation: cosine peaks at phase=0 (midnight), trough at phase=0.5 (midday)
        circadian_mod = 0.5 * (1.0 + np.cos(2.0 * np.pi * phase))
        melatonin = float(np.clip(self.baseline * suppression * circadian_mod, 0.0, 1.0))
        sleep_pressure = float(np.clip(melatonin * 0.8 + 0.1 * circadian_mod, 0.0, 1.0))
        return {
            'melatonin_level': melatonin,
            'sleep_pressure': sleep_pressure,
            'circadian_strength': float(circadian_mod),
        }


class CircadianEntrainer:
    """Synchronises internal clock to external zeitgeber (time-giver) cues."""

    def __init__(self, entrainment_rate: float = 0.1, threshold: float = 0.15):
        self.entrainment_rate = np.clip(entrainment_rate, 0.01, 1.0)
        self.threshold = threshold

    def entrain(self, external_zeitgeber: float, internal_phase: float) -> Dict[str, Any]:
        """Compute phase_shift, entrainment_strength, and is_entrained."""
        ext = float(np.clip(external_zeitgeber, 0.0, 1.0))
        internal = float(np.clip(internal_phase, 0.0, 1.0))
        # Circular phase difference (wraps around 1.0)
        phase_diff = ext - internal
        if phase_diff > 0.5:
            phase_diff -= 1.0
        elif phase_diff < -0.5:
            phase_diff += 1.0
        phase_shift = float(self.entrainment_rate * phase_diff)
        entrainment_strength = float(1.0 - min(abs(phase_diff) / 0.5, 1.0))
        is_entrained = abs(phase_diff) < self.threshold
        return {
            'phase_shift': round(phase_shift, 6),
            'entrainment_strength': round(entrainment_strength, 4),
            'is_entrained': is_entrained,
        }


# ============================================================================
# Main Class
# ============================================================================

class PinealGland:
    """Pineal gland integrating melatonin production and circadian entrainment."""

    def __init__(self, melatonin_baseline: float = 0.5, light_sensitivity: float = 1.0,
                 entrainment_rate: float = 0.1):
        self.melatonin_baseline = melatonin_baseline
        self.light_sensitivity = light_sensitivity
        self.entrainment_rate = entrainment_rate
        self.melatonin = MelatoninProduction(baseline=melatonin_baseline, light_sensitivity=light_sensitivity)
        self.entrainer = CircadianEntrainer(entrainment_rate=entrainment_rate)
        self._stats = PinealGlandStats()
        self._melatonin_history: deque = deque(maxlen=200)
        self._dark_count: int = 0
        logger.info("PinealGland initialised — baseline=%.2f, sensitivity=%.1f, rate=%.2f",
                     melatonin_baseline, light_sensitivity, entrainment_rate)

    # ------------------------------------------------------------------ core
    def process(self, light_exposure: float = 0.5, circadian_phase: float = 0.5,
                external_zeitgeber: float = 0.5) -> Dict[str, Any]:
        """Run one cycle. Returns melatonin, sleep, circadian, and entrainment outputs."""
        mel = self.melatonin.compute_melatonin(light_exposure, circadian_phase)
        ent = self.entrainer.entrain(external_zeitgeber, circadian_phase)
        # Bookkeeping
        self._melatonin_history.append(mel['melatonin_level'])
        if light_exposure < 0.3:
            self._dark_count += 1
        self._stats.total_cycles += 1
        if ent['is_entrained']:
            self._stats.entrainment_events += 1
        total = max(self._stats.total_cycles, 1)
        self._stats.avg_melatonin = float(np.mean(list(self._melatonin_history)))
        self._stats.dark_phase_ratio = self._dark_count / total
        logger.debug("Pineal cycle %d — melatonin=%.3f sleep=%.3f entrained=%s",
                      self._stats.total_cycles, mel['melatonin_level'],
                      mel['sleep_pressure'], ent['is_entrained'])
        return {
            'melatonin_level': mel['melatonin_level'],
            'sleep_pressure': mel['sleep_pressure'],
            'circadian_strength': mel['circadian_strength'],
            'phase_shift': ent['phase_shift'],
            'entrainment_strength': ent['entrainment_strength'],
            'is_entrained': ent['is_entrained'],
        }

    def circadian_phase_assessment(self) -> Dict[str, Any]:
        """
        Assess current circadian phase for optimal function (Czeisler, 1999).

        Melatonin from the pineal gland is the primary circadian signal.
        Its secretion profile determines alertness windows, optimal
        learning times, and sleep propensity.

        Returns:
            Dict with phase, optimal_for, melatonin_trend
        """
        melatonin = float(self._melatonin_history[-1]) if self._melatonin_history else 0.0

        if melatonin < 0.2:
            phase = 'day_active'
            optimal_for = 'complex_tasks_and_learning'
        elif melatonin < 0.4:
            phase = 'evening_transition'
            optimal_for = 'creative_tasks'
        elif melatonin < 0.7:
            phase = 'night_onset'
            optimal_for = 'consolidation_prep'
        else:
            phase = 'deep_night'
            optimal_for = 'memory_consolidation'

        # Trend: rising or falling melatonin
        if len(self._melatonin_history) >= 2:
            recent = list(self._melatonin_history)[-5:]
            trend = recent[-1] - recent[0]
        else:
            trend = 0.0

        return {
            'phase': phase,
            'optimal_for': optimal_for,
            'melatonin_level': round(melatonin, 4),
            'melatonin_trend': round(trend, 4),
            'trend_direction': 'rising' if trend > 0.01 else ('falling' if trend < -0.01 else 'stable'),
        }

    # --------------------------------------------------------- introspection
    def get_state(self) -> Dict[str, Any]:
        """Return current internal state snapshot."""
        return {
            'melatonin_level': float(self._melatonin_history[-1]) if self._melatonin_history else 0.0,
            'avg_melatonin': self._stats.avg_melatonin,
            'dark_phase_ratio': self._stats.dark_phase_ratio,
            'entrainment_events': self._stats.entrainment_events,
            'total_cycles': self._stats.total_cycles,
        }

    def get_stats(self) -> PinealGlandStats:
        """Return accumulated statistics."""
        return self._stats

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable dictionary of state + stats."""
        return {
            'state': self.get_state(),
            'stats': self._stats.to_dict(),
            'melatonin_history': [round(v, 4) for v in list(self._melatonin_history)[-20:]],
        }

    # --------------------------------------------------------------- control
    def reset(self) -> None:
        """Reset all internal state (preserve config)."""
        self.melatonin = MelatoninProduction(baseline=self.melatonin_baseline,
                                             light_sensitivity=self.light_sensitivity)
        self.entrainer = CircadianEntrainer(entrainment_rate=self.entrainment_rate)
        self._melatonin_history.clear()
        self._dark_count = 0
        self._stats = PinealGlandStats()
        logger.info("PinealGland reset")

    # ------------------------------------------------------------ from_yaml
    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'PinealGland':
        """Construct from parsed YAML config dict."""
        pg = config.get('pineal_gland', {})
        return cls(
            melatonin_baseline=pg.get('melatonin_baseline', 0.5),
            light_sensitivity=pg.get('light_sensitivity', 1.0),
            entrainment_rate=pg.get('entrainment_rate', 0.1),
        )

    def __repr__(self) -> str:
        return (f"PinealGland(cycles={self._stats.total_cycles}, "
                f"melatonin={self._stats.avg_melatonin:.3f})")
