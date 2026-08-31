"""
Tuberomammillary Nucleus (TMN) — Histaminergic Wakefulness System

The TMN in the posterior hypothalamus is the sole source of histamine in
the mammalian brain.  TMN neurons fire tonically during wakefulness,
reduce during drowsiness, and fall silent during sleep.

References:
  Haas & Panula (2003) — "The role of histamine and the tuberomammillary
      nucleus in the nervous system", Nature Reviews Neuroscience 4, 121
  Lin et al. (1988) — "The hypothalamic histaminergic system and wakefulness"
  Parmentier et al. (2002) — "Characteristics of histidine decarboxylase
      knock-out mice"

Functions: wakefulness promotion, circadian regulation, arousal gating,
           sleep-wake transition.
"""

import logging
import math
import numpy as np
from typing import Dict, Any
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger('brain.tmn')


# ─── Histamine Release ─────────────────────────────────────────────────────

class HistamineRelease:
    """Computes histamine level from arousal drive, circadian phase, and
    sleep pressure.  High arousal + daytime = high histamine (awake);
    low arousal + high sleep pressure = low histamine (drowsy)."""

    def __init__(self, baseline: float = 0.5, circadian_gain: float = 1.0,
                 wake_threshold: float = 0.4):
        self.baseline = float(np.clip(baseline, 0.0, 1.0))
        self.circadian_gain = float(np.clip(circadian_gain, 0.0, 3.0))
        self.wake_threshold = float(np.clip(wake_threshold, 0.0, 1.0))

    def compute_histamine(self, arousal_drive: float,
                          circadian_phase: float,
                          sleep_pressure: float) -> Dict[str, Any]:
        """Returns histamine_level, wakefulness_drive, is_awake.
        circadian_phase: 0/1=midnight trough, 0.5=noon peak."""
        arousal = float(np.clip(arousal_drive, 0.0, 1.0))
        phase = float(np.clip(circadian_phase, 0.0, 1.0))
        pressure = float(np.clip(sleep_pressure, 0.0, 1.0))

        circadian_factor = 0.5 + 0.5 * math.sin(math.pi * phase)
        circadian_mod = circadian_factor * self.circadian_gain

        raw = self.baseline + arousal * 0.3 + circadian_mod * 0.3 - pressure * 0.5
        histamine_level = float(np.clip(raw, 0.0, 1.0))
        wakefulness_drive = float(np.clip(histamine_level * 1.2, 0.0, 1.0))
        is_awake = histamine_level >= self.wake_threshold

        return {
            'histamine_level': round(histamine_level, 4),
            'wakefulness_drive': round(wakefulness_drive, 4),
            'is_awake': is_awake,
        }


# ─── Stats ──────────────────────────────────────────────────────────────────

@dataclass
class TMNStats:
    """Accumulated statistics for the Tuberomammillary Nucleus."""
    total_cycles: int = 0
    avg_histamine: float = 0.0
    wake_ratio: float = 0.0
    sleep_ratio: float = 0.0
    _histamine_accum: float = field(default=0.0, repr=False)
    _wake_count: int = field(default=0, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cycles': self.total_cycles,
            'avg_histamine': round(self.avg_histamine, 4),
            'wake_ratio': round(self.wake_ratio, 4),
            'sleep_ratio': round(self.sleep_ratio, 4),
        }


# ─── Tuberomammillary Nucleus (main) ────────────────────────────────────────

class TuberomammillaryNucleus:
    """Histaminergic wakefulness module.  High histamine sustains
    wakefulness; low histamine triggers drowsiness and DreamMode."""

    def __init__(self, histamine_baseline: float = 0.5,
                 wake_threshold: float = 0.4,
                 circadian_gain: float = 1.0):
        self.histamine_baseline = float(np.clip(histamine_baseline, 0.0, 1.0))
        self.wake_threshold = float(np.clip(wake_threshold, 0.0, 1.0))
        self.circadian_gain = float(np.clip(circadian_gain, 0.0, 3.0))
        self._release = HistamineRelease(
            baseline=self.histamine_baseline,
            circadian_gain=self.circadian_gain,
            wake_threshold=self.wake_threshold,
        )
        self._stats = TMNStats()
        self._history: deque = deque(maxlen=200)
        logger.info("TMN initialised  baseline=%.2f  wake_thresh=%.2f  "
                     "circ_gain=%.2f", self.histamine_baseline,
                     self.wake_threshold, self.circadian_gain)

    def process(self, arousal_drive: float = 0.5,
                circadian_phase: float = 0.5,
                sleep_pressure: float = 0.0) -> Dict[str, Any]:
        """Run one cycle.  Returns histamine_level, wakefulness_drive,
        is_awake, arousal_input, circadian_input, sleep_pressure_input."""
        release_out = self._release.compute_histamine(
            arousal_drive, circadian_phase, sleep_pressure)
        histamine = release_out['histamine_level']
        is_awake = release_out['is_awake']

        self._stats.total_cycles += 1
        self._stats._histamine_accum += histamine
        self._stats.avg_histamine = (
            self._stats._histamine_accum / self._stats.total_cycles)
        if is_awake:
            self._stats._wake_count += 1
        self._stats.wake_ratio = self._stats._wake_count / self._stats.total_cycles
        self._stats.sleep_ratio = 1.0 - self._stats.wake_ratio

        result = {
            'histamine_level': release_out['histamine_level'],
            'wakefulness_drive': release_out['wakefulness_drive'],
            'is_awake': is_awake,
            'arousal_input': round(float(np.clip(arousal_drive, 0.0, 1.0)), 4),
            'circadian_input': round(float(np.clip(circadian_phase, 0.0, 1.0)), 4),
            'sleep_pressure_input': round(float(np.clip(sleep_pressure, 0.0, 1.0)), 4),
        }
        self._history.append(result)
        return result

    def wake_stability_assessment(self) -> Dict[str, float]:
        """
        Assess wakefulness stability (Haas et al., 2008).

        TMN histamine neurons fire only during waking — they are silent
        during sleep. Histamine provides tonic excitation that stabilizes
        wakefulness. Antihistamines cause drowsiness by blocking this.

        Returns:
            Dict with wake_stability, drowsiness_risk, histamine_tone
        """
        recent = list(self._history)[-10:] if self._history else []
        if not recent:
            return {'wake_stability': 0.5, 'drowsiness_risk': 0.3, 'histamine_tone': self.histamine_baseline}

        hist_levels = [r.get('histamine_output', 0.5) for r in recent]
        avg_hist = float(np.mean(hist_levels))
        hist_var = float(np.var(hist_levels))

        wake_stability = min(1.0, avg_hist * (1.0 - hist_var * 4.0))
        drowsiness_risk = max(0.0, 1.0 - avg_hist * 1.5)

        return {
            'wake_stability': round(max(0.0, wake_stability), 4),
            'drowsiness_risk': round(drowsiness_risk, 4),
            'histamine_tone': round(avg_hist, 4),
        }

    def get_state(self) -> Dict[str, Any]:
        last = self._history[-1] if self._history else {}
        return {
            'histamine_baseline': self.histamine_baseline,
            'wake_threshold': self.wake_threshold,
            'circadian_gain': self.circadian_gain,
            'last_output': last,
            'stats': self._stats.to_dict(),
        }

    def get_stats(self) -> TMNStats:
        return self._stats

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    def reset(self) -> None:
        self._stats = TMNStats()
        self._history.clear()
        logger.debug("TMN reset")

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> "TuberomammillaryNucleus":
        tmn_cfg = config.get('tuberomammillary_nucleus', {})
        return cls(
            histamine_baseline=tmn_cfg.get('histamine_baseline', 0.5),
            wake_threshold=tmn_cfg.get('wake_threshold', 0.4),
            circadian_gain=tmn_cfg.get('circadian_gain', 1.0),
        )
