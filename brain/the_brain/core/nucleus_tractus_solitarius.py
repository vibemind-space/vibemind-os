"""
Nucleus Tractus Solitarius (NTS) — Primary Visceral Sensory Relay

The NTS is the brainstem nucleus that receives ALL visceral afferent input
from cardiovascular, respiratory, and gastrointestinal systems.  It serves
as the first central relay for interoceptive signals, forwarding processed
information to hypothalamus, amygdala, and parabrachial nucleus.

Key computational roles modelled here:

1. ViscereSensoryRelay
   - Aggregates raw visceral channel readings (0-1 floats) into a
     unified visceral state with per-system summaries.
   - Applies a configurable relay gain to amplify or dampen signals
     before downstream processing.

2. AutonomicReflexArc
   - Fast, sub-cognitive reflexes (e.g. baroreflex, respiratory
     adjustments) that bypass higher-order processing.
   - Activates only when cardiovascular or respiratory signals
     exceed a configurable threshold.

3. NucleusTractSolitarius (main facade)
   - Owns the relay and reflex arc, exposes the standard 6-method
     interface (process, get_state, from_yaml, reset, update, to_dict).
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger('brain.nts')


# ─── Stats Dataclass ───────────────────────────────────────────────────────

@dataclass
class NTSStats:
    """Accumulated statistics for the NTS module."""
    total_relays: int = 0
    avg_visceral_level: float = 0.0
    reflex_activations: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_relays': self.total_relays,
            'avg_visceral_level': round(self.avg_visceral_level, 4),
            'reflex_activations': self.reflex_activations,
        }


# ─── Visceral Sensory Relay ────────────────────────────────────────────────

class ViscereSensoryRelay:
    """
    Relays visceral afferent signals into a structured state dict.

    Each visceral channel is expected as a float in [0, 1].  The relay
    computes per-system averages and an overall visceral level, scaled
    by *relay_gain*.
    """

    _CARDIO_KEYS = ('heart_rate', 'blood_pressure', 'baroreceptor')
    _RESP_KEYS = ('breathing_rate', 'oxygen_saturation', 'chemoreceptor')
    _GI_KEYS = ('gastric_distension', 'nutrient_status', 'nausea')

    def __init__(self, relay_gain: float = 1.0):
        self.relay_gain = max(0.01, relay_gain)

    def relay(self, visceral_inputs: Dict[str, float]) -> Dict[str, Any]:
        """
        Process raw visceral inputs into a structured relay output.

        Returns dict with cardiovascular_state, respiratory_state,
        gi_state, overall_visceral, and afferent_strength.
        """
        cardio = self._mean_for(visceral_inputs, self._CARDIO_KEYS)
        resp = self._mean_for(visceral_inputs, self._RESP_KEYS)
        gi = self._mean_for(visceral_inputs, self._GI_KEYS)

        # Overall visceral level — weighted mean of the three systems
        vals = [v for v in (cardio, resp, gi) if v is not None]
        overall = float(np.mean(vals)) if vals else 0.0
        afferent = min(1.0, overall * self.relay_gain)

        return {
            'cardiovascular_state': round(cardio or 0.0, 4),
            'respiratory_state': round(resp or 0.0, 4),
            'gi_state': round(gi or 0.0, 4),
            'overall_visceral': round(overall, 4),
            'afferent_strength': round(afferent, 4),
        }

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _mean_for(
        inputs: Dict[str, float], keys: tuple
    ) -> Optional[float]:
        present = [inputs[k] for k in keys if k in inputs]
        return float(np.mean(present)) if present else None


# ─── Autonomic Reflex Arc ──────────────────────────────────────────────────

class AutonomicReflexArc:
    """
    Fast autonomic reflexes that bypass cortical processing.

    If cardiovascular or respiratory signals exceed *threshold*,
    the arc computes compensatory adjustments (negative feedback).
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = max(0.0, min(1.0, threshold))

    def compute_reflex(
        self, cardiovascular: float, respiratory: float
    ) -> Dict[str, Any]:
        """
        Compute reflex adjustments.

        Returns heart_rate_adjustment, breathing_adjustment, and
        whether a reflex was triggered.
        """
        hr_adj = 0.0
        br_adj = 0.0
        active = False

        if cardiovascular > self.threshold:
            # Baroreflex: high pressure → slow heart rate
            hr_adj = -(cardiovascular - self.threshold)
            active = True

        if respiratory > self.threshold:
            # Hering-Breuer: high respiratory drive → dampen
            br_adj = -(respiratory - self.threshold)
            active = True

        return {
            'heart_rate_adjustment': round(hr_adj, 4),
            'breathing_adjustment': round(br_adj, 4),
            'reflex_active': active,
        }


# ─── Main Class: NucleusTractSolitarius ────────────────────────────────────

class NucleusTractSolitarius:
    """
    Brainstem visceral relay nucleus.

    Standard 6-method interface:
      process, get_state, from_yaml, reset, update, to_dict
    """

    def __init__(
        self,
        relay_gain: float = 1.0,
        reflex_threshold: float = 0.6,
    ):
        self.relay = ViscereSensoryRelay(relay_gain=relay_gain)
        self.reflex_arc = AutonomicReflexArc(threshold=reflex_threshold)

        self._stats = NTSStats()
        self._history: deque = deque(maxlen=200)
        self._visceral_sum: float = 0.0
        self._last_output: Dict[str, Any] = {}

    # ── core interface ───────────────────────────────────────────────────

    def process(self, visceral_inputs: Dict[str, float]) -> Dict[str, Any]:
        """
        Full NTS processing pass: relay then reflex check.

        Returns merged dict of relay output + reflex output.
        """
        relay_out = self.relay.relay(visceral_inputs)
        reflex_out = self.reflex_arc.compute_reflex(
            cardiovascular=relay_out['cardiovascular_state'],
            respiratory=relay_out['respiratory_state'],
        )

        # Update stats
        self._stats.total_relays += 1
        self._visceral_sum += relay_out['overall_visceral']
        self._stats.avg_visceral_level = (
            self._visceral_sum / self._stats.total_relays
        )
        if reflex_out['reflex_active']:
            self._stats.reflex_activations += 1

        result = {**relay_out, **reflex_out, 'timestamp': time.time()}
        self._history.append(result)
        self._last_output = result

        logger.debug(
            "NTS relay #%d  visceral=%.3f  reflex=%s",
            self._stats.total_relays,
            relay_out['overall_visceral'],
            reflex_out['reflex_active'],
        )
        return result

    def update(self, visceral_inputs: Dict[str, float]) -> None:
        """Alias for process (fire-and-forget update)."""
        self.process(visceral_inputs)

    def vagal_tone_assessment(self) -> Dict[str, float]:
        """
        Assess vagal tone / autonomic balance (Porges, 2001 — Polyvagal Theory).

        NTS is the primary relay for vagal afferents. High vagal tone
        (parasympathetic dominance) = calm, social engagement. Low vagal
        tone (sympathetic dominance) = stress, fight-or-flight readiness.

        Returns:
            Dict with vagal_tone, autonomic_balance, social_engagement_capacity
        """
        recent = list(self._history)[-10:] if self._history else []
        if not recent:
            return {'vagal_tone': 0.5, 'autonomic_balance': 0.0, 'social_engagement_capacity': 0.5}

        # Extract autonomic signals from recent processing
        avg_activation = float(np.mean([
            r.get('autonomic_activation', 0.5) for r in recent
        ])) if recent else 0.5

        # Vagal tone: inverse of sympathetic activation
        vagal_tone = max(0.0, 1.0 - avg_activation)

        # Autonomic balance: positive = parasympathetic, negative = sympathetic
        autonomic_balance = vagal_tone - avg_activation

        # Social engagement: requires high vagal tone (Porges)
        social_capacity = min(1.0, vagal_tone * 1.3)

        return {
            'vagal_tone': round(vagal_tone, 4),
            'autonomic_balance': round(autonomic_balance, 4),
            'social_engagement_capacity': round(social_capacity, 4),
        }

    def get_state(self) -> Dict[str, Any]:
        """Return current NTS state for dashboard / orchestrator."""
        return {
            'stats': self._stats.to_dict(),
            'last_output': self._last_output,
            'history_length': len(self._history),
        }

    def get_stats(self) -> 'NTSStats':
        """Return stats dataclass."""
        return self._stats

    def reset(self) -> None:
        """Reset all internal state."""
        self._stats = NTSStats()
        self._history.clear()
        self._visceral_sum = 0.0
        self._last_output = {}
        logger.info("NTS reset")

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable snapshot."""
        return {
            'stats': self._stats.to_dict(),
            'last_output': self._last_output,
            'recent_history': list(self._history)[-5:],
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'NucleusTractSolitarius':
        """Create NTS from YAML config dict (key: 'nts')."""
        section = config.get('nts', {})
        return cls(
            relay_gain=section.get('relay_gain', 1.0),
            reflex_threshold=section.get('reflex_threshold', 0.6),
        )
