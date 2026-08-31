"""
Temporo-Parietal Junction (TPJ)

Junction of temporal and parietal lobes supporting higher-order cognition:
- Saxe & Kanwisher (2003): TPJ for theory of mind / mentalising
- Self-other distinction and sense of agency
- Attentional reorienting to unexpected salient events (Corbetta & Shulman, 2002)
"""

import time
import logging
import numpy as np
from typing import Dict, Optional, Any
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger('brain.tpj')


@dataclass
class TPJStats:
    """Aggregate statistics for the temporo-parietal junction."""
    total_inferences: int = 0
    self_attributions: int = 0
    other_attributions: int = 0
    reorienting_events: int = 0
    avg_agency: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_inferences': self.total_inferences,
            'self_attributions': self.self_attributions,
            'other_attributions': self.other_attributions,
            'reorienting_events': self.reorienting_events,
            'avg_agency': round(self.avg_agency, 4),
        }


# ─── Theory of Mind Processor ───────────────────────────────────────────

class TheoryOfMindProcessor:
    """Models beliefs, intentions, and emotional states of other agents."""

    def __init__(self, sensitivity: float = 0.5):
        self._sensitivity = max(0.0, min(1.0, sensitivity))

    def infer_mental_state(self, observed_actions: np.ndarray,
                           context: Dict[str, float]) -> Dict[str, Any]:
        """Infer another agent's mental state from actions and context."""
        vec = np.array(observed_actions, dtype=np.float64).flatten()
        energy = float(np.mean(np.abs(vec))) if len(vec) > 0 else 0.0
        ctx_vals = list(context.values()) if context else [0.0]
        ctx_mean = float(np.mean(ctx_vals))

        intention = min(1.0, energy * self._sensitivity + ctx_mean * 0.3)
        variance = float(np.var(vec)) if len(vec) > 1 else 0.0
        belief = max(0.0, 1.0 - variance)
        emotional = float(np.tanh(energy - 0.5 + ctx_mean * 0.2))
        n_cues = len(context) if context else 0
        confidence = min(1.0, self._sensitivity * (0.5 + 0.1 * n_cues))

        return {
            'inferred_intention': round(intention, 4),
            'belief_state': round(belief, 4),
            'emotional_state': round(emotional, 4),
            'confidence': round(confidence, 4),
        }


# ─── Self-Other Distinction ─────────────────────────────────────────────

class SelfOtherDistinction:
    """Distinguishes self-generated from externally generated events."""

    def __init__(self, agency_threshold: float = 0.6):
        self._threshold = max(0.0, min(1.0, agency_threshold))

    def distinguish(self, action_signal: float, sensory_feedback: float,
                    prediction: float) -> Dict[str, Any]:
        """Determine whether an event was self-generated via prediction error."""
        pred_error = abs(sensory_feedback - prediction)
        agency = max(0.0, min(1.0, action_signal * (1.0 - pred_error)))
        clarity = abs(agency - 0.5) * 2.0  # 0 = ambiguous, 1 = clear
        return {
            'is_self_generated': agency >= self._threshold,
            'agency_score': round(agency, 4),
            'distinction_clarity': round(clarity, 4),
        }


# ─── Attentional Reorienter ─────────────────────────────────────────────

class AttentionalReorienter:
    """Detects salient mismatches and produces reorienting signals."""

    def __init__(self, reorienting_threshold: float = 0.3):
        self._threshold = max(0.0, min(1.0, reorienting_threshold))

    def should_reorient(self, expected_salience: float,
                        actual_salience: float) -> Dict[str, Any]:
        """Decide whether attention should be reoriented to a new stimulus."""
        surprise = max(0.0, actual_salience - expected_salience)
        novelty_drive = float(np.tanh(surprise * 2.0))
        return {
            'reorient_signal': surprise >= self._threshold,
            'surprise': round(surprise, 4),
            'novelty_drive': round(novelty_drive, 4),
        }


# ─── Main Class: Temporo-Parietal Junction ──────────────────────────────

class TemporoparietalJunction:
    """
    Temporo-Parietal Junction combining theory-of-mind, self-other
    distinction, and attentional reorienting.
    """

    def __init__(self, tom_sensitivity: float = 0.5,
                 agency_threshold: float = 0.6,
                 reorienting_threshold: float = 0.3):
        self.tom_sensitivity = tom_sensitivity
        self.agency_threshold = agency_threshold
        self.reorienting_threshold = reorienting_threshold
        self._tom = TheoryOfMindProcessor(sensitivity=tom_sensitivity)
        self._sod = SelfOtherDistinction(agency_threshold=agency_threshold)
        self._reorienter = AttentionalReorienter(reorienting_threshold=reorienting_threshold)
        self._stats = TPJStats()
        self._agency_history: deque = deque(maxlen=200)
        self._last_result: Dict[str, Any] = {}
        logger.info("TemporoparietalJunction initialised (tom=%.2f, agency=%.2f, reorient=%.2f)",
                     tom_sensitivity, agency_threshold, reorienting_threshold)

    def process(self, observed_actions: Optional[np.ndarray] = None,
                context: Optional[Dict[str, float]] = None,
                action_signal: float = 0.0, sensory_feedback: float = 0.0,
                prediction: float = 0.0, expected_salience: float = 0.5,
                actual_salience: float = 0.5) -> Dict[str, Any]:
        """Run all TPJ sub-processors and return unified result."""
        if observed_actions is None:
            observed_actions = np.zeros(4)
        if context is None:
            context = {}

        tom_result = self._tom.infer_mental_state(observed_actions, context)
        agency_result = self._sod.distinguish(action_signal, sensory_feedback, prediction)
        reorienting_result = self._reorienter.should_reorient(expected_salience, actual_salience)

        self._stats.total_inferences += 1
        if agency_result['is_self_generated']:
            self._stats.self_attributions += 1
        else:
            self._stats.other_attributions += 1
        if reorienting_result['reorient_signal']:
            self._stats.reorienting_events += 1

        self._agency_history.append(agency_result['agency_score'])
        self._stats.avg_agency = float(np.mean(list(self._agency_history)))

        self._last_result = {
            'tom_result': tom_result, 'agency_result': agency_result,
            'reorienting_result': reorienting_result, 'timestamp': time.time(),
        }
        logger.debug("TPJ processed: agency=%.3f reorient=%s tom_conf=%.3f",
                      agency_result['agency_score'], reorienting_result['reorient_signal'],
                      tom_result['confidence'])
        return self._last_result

    def update(self, tom_sensitivity: Optional[float] = None,
               agency_threshold: Optional[float] = None,
               reorienting_threshold: Optional[float] = None) -> None:
        """Update processor parameters at runtime."""
        if tom_sensitivity is not None:
            self.tom_sensitivity = max(0.0, min(1.0, tom_sensitivity))
            self._tom._sensitivity = self.tom_sensitivity
        if agency_threshold is not None:
            self.agency_threshold = max(0.0, min(1.0, agency_threshold))
            self._sod._threshold = self.agency_threshold
        if reorienting_threshold is not None:
            self.reorienting_threshold = max(0.0, min(1.0, reorienting_threshold))
            self._reorienter._threshold = self.reorienting_threshold
        logger.info("TPJ parameters updated")

    def reset(self) -> None:
        """Reset all internal state."""
        self._stats = TPJStats()
        self._agency_history.clear()
        self._last_result = {}
        logger.info("TemporoparietalJunction reset")

    def theory_of_mind_inference(
        self,
        observed_action: float,
        context_congruence: float,
    ) -> Dict[str, float]:
        """
        Theory of Mind inference (Saxe & Kanwisher, 2003).

        TPJ is the core neural substrate for mentalizing — inferring
        others' beliefs, desires, and intentions. It computes the
        difference between what we know and what others might know
        (false belief reasoning).

        Args:
            observed_action: Strength of observed action signal [0, 1]
            context_congruence: How well action matches expected context [0, 1]

        Returns:
            Dict with belief_inference, surprise_about_other, empathy_signal
        """
        # Incongruent actions trigger stronger mentalizing
        incongruence = max(0.0, 1.0 - context_congruence)

        # Belief inference: stronger for surprising actions
        belief_inference = min(1.0, observed_action * 0.4 + incongruence * 0.6)

        # Surprise about other's mental state
        surprise = incongruence * observed_action

        # Empathy signal: understanding leads to empathy
        empathy = min(1.0, belief_inference * 0.7 + context_congruence * 0.3)

        return {
            'belief_inference': round(belief_inference, 4),
            'surprise_about_other': round(min(1.0, surprise), 4),
            'empathy_signal': round(empathy, 4),
            'mentalizing_demand': round(incongruence, 4),
        }

    def get_state(self) -> Dict[str, Any]:
        """Return current state snapshot."""
        return {
            'stats': self._stats.to_dict(),
            'parameters': {
                'tom_sensitivity': self.tom_sensitivity,
                'agency_threshold': self.agency_threshold,
                'reorienting_threshold': self.reorienting_threshold,
            },
            'last_result': self._last_result,
        }

    def get_stats(self) -> 'TPJStats':
        """Return stats dataclass."""
        return self._stats

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable representation."""
        return {
            'tom_sensitivity': self.tom_sensitivity,
            'agency_threshold': self.agency_threshold,
            'reorienting_threshold': self.reorienting_threshold,
            'stats': self._stats.to_dict(),
        }

    @classmethod
    def from_yaml(cls, cfg: Dict) -> 'TemporoparietalJunction':
        section = cfg.get('temporoparietal_junction', {})
        return cls(
            tom_sensitivity=section.get('tom_sensitivity', 0.5),
            agency_threshold=section.get('agency_threshold', 0.6),
            reorienting_threshold=section.get('reorienting_threshold', 0.3),
        )
