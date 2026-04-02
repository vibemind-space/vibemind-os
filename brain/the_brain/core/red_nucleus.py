"""
Red Nucleus — Midbrain Motor Redundancy (Rubrospinal Tract)

The red nucleus gives rise to the rubrospinal tract, a descending motor
pathway parallel to the corticospinal tract.  Vestigial in humans but
primary in other mammals, it provides motor error correction and backup
motor signals when primary cortical output is degraded.

References:
  Massion (1967) — "The red nucleus: past and present"
  Ten Donkelaar (1988) — "Evolution of the red nucleus and rubrospinal tract"
  Kennedy (1990) — "Corticospinal, rubrospinal and rubro-olivary projections"

Functions: motor control redundancy, motor error correction, limb coordination.
"""

import logging
import numpy as np
from typing import Dict, Any
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger('brain.red_nucleus')


# ─── Rubrospinal Pathway ──────────────────────────────────────────────────

class RubrospinalPathway:
    """Backup motor signal pathway with cerebellar error correction."""

    def __init__(self, compensation_threshold: float = 0.5,
                 correction_gain: float = 0.5):
        self.compensation_threshold = float(np.clip(compensation_threshold, 0.0, 1.0))
        self.correction_gain = float(np.clip(correction_gain, 0.0, 2.0))

    def compute_motor_signal(self, primary_motor: float,
                             error_signal: float) -> Dict[str, Any]:
        """Produce backup motor signal.  Returns backup_signal,
        error_correction, is_compensating."""
        primary_motor = float(np.clip(primary_motor, 0.0, 1.0))
        error_signal = float(np.clip(error_signal, -1.0, 1.0))

        is_compensating = primary_motor < self.compensation_threshold
        error_correction = -error_signal * self.correction_gain

        if is_compensating:
            deficit = self.compensation_threshold - primary_motor
            backup_signal = float(np.clip(deficit + error_correction, 0.0, 1.0))
        else:
            backup_signal = float(np.clip(error_correction * 0.1, 0.0, 1.0))

        return {
            'backup_signal': round(backup_signal, 4),
            'error_correction': round(error_correction, 4),
            'is_compensating': is_compensating,
        }


# ─── Stats ─────────────────────────────────────────────────────────────────

@dataclass
class RedNucleusStats:
    """Accumulated statistics for the Red Nucleus."""
    total_cycles: int = 0
    compensations_triggered: int = 0
    avg_error_correction: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_cycles': self.total_cycles,
            'compensations_triggered': self.compensations_triggered,
            'avg_error_correction': round(self.avg_error_correction, 4),
        }


# ─── Red Nucleus (main) ───────────────────────────────────────────────────

class RedNucleus:
    """Midbrain motor redundancy module.  Blends primary motor signal with
    a rubrospinal backup weighted by cerebellar error feedback."""

    def __init__(self, compensation_threshold: float = 0.5,
                 correction_gain: float = 0.5):
        self.compensation_threshold = float(np.clip(compensation_threshold, 0.0, 1.0))
        self.correction_gain = float(np.clip(correction_gain, 0.0, 2.0))
        self._pathway = RubrospinalPathway(
            compensation_threshold=self.compensation_threshold,
            correction_gain=self.correction_gain,
        )
        self._stats = RedNucleusStats()
        self._history: deque = deque(maxlen=200)
        self._error_accum: float = 0.0
        logger.info("RedNucleus initialised  threshold=%.2f  gain=%.2f",
                     self.compensation_threshold, self.correction_gain)

    def process(self, primary_motor_signal: float,
                error_signal: float = 0.0,
                cerebellar_input: float = 0.0) -> Dict[str, Any]:
        """Run one cycle.  Returns corrected_signal, backup_signal,
        error_correction, is_compensating, blend_ratio."""
        primary = float(np.clip(primary_motor_signal, 0.0, 1.0))
        cerebellar = float(np.clip(cerebellar_input, 0.0, 1.0))
        combined_error = float(np.clip(error_signal + cerebellar * 0.3, -1.0, 1.0))

        pathway_out = self._pathway.compute_motor_signal(primary, combined_error)
        backup = pathway_out['backup_signal']
        is_comp = pathway_out['is_compensating']

        blend_ratio = 1.0 - primary if is_comp else 0.05
        corrected = float(np.clip(
            primary * (1.0 - blend_ratio) + backup * blend_ratio, 0.0, 1.0))

        self._stats.total_cycles += 1
        if is_comp:
            self._stats.compensations_triggered += 1
        ec = pathway_out['error_correction']
        self._error_accum += abs(ec)
        self._stats.avg_error_correction = self._error_accum / self._stats.total_cycles

        result = {
            'corrected_signal': round(corrected, 4),
            'backup_signal': round(backup, 4),
            'error_correction': round(ec, 4),
            'is_compensating': is_comp,
            'blend_ratio': round(blend_ratio, 4),
        }
        self._history.append(result)
        return result

    def motor_backup_assessment(self) -> Dict[str, float]:
        """
        Assess backup motor pathway readiness (Muir & Whishaw, 2000).

        The red nucleus provides a backup motor pathway (rubrospinal)
        when the primary corticospinal tract is impaired. It supports
        coarse motor control as a redundant system for resilience.

        Returns:
            Dict with backup_ready, compensation_level, primary_impairment
        """
        recent = list(self._history)[-10:] if self._history else []
        if not recent:
            return {'backup_ready': True, 'compensation_level': 0.0, 'primary_impairment': 0.0}

        avg_comp = float(np.mean([r.get('compensation_active', False) for r in recent]))
        avg_error = float(np.mean([r.get('correction_magnitude', 0.0) for r in recent]))

        return {
            'backup_ready': True,
            'compensation_level': round(avg_comp, 4),
            'primary_impairment': round(min(1.0, avg_error * 2.0), 4),
            'recent_corrections': len(recent),
        }

    def get_state(self) -> Dict[str, Any]:
        last = self._history[-1] if self._history else {}
        return {
            'compensation_threshold': self.compensation_threshold,
            'correction_gain': self.correction_gain,
            'last_output': last,
            'stats': self._stats.to_dict(),
        }

    def get_stats(self) -> RedNucleusStats:
        return self._stats

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    def reset(self) -> None:
        self._stats = RedNucleusStats()
        self._history.clear()
        self._error_accum = 0.0
        logger.debug("RedNucleus reset")

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> "RedNucleus":
        rn_cfg = config.get('red_nucleus', {})
        return cls(
            compensation_threshold=rn_cfg.get('compensation_threshold', 0.5),
            correction_gain=rn_cfg.get('correction_gain', 0.5),
        )
