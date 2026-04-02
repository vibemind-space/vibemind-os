"""
Social Perception Bridge -- connects OlfactorySystem, FusiformGyrus, and
TemporoparietalJunction to the Radial Attention Network.

Translates ring activations and prediction errors into social perception
signals (face/text detection, agency, social salience, familiarity) that
modulate RingLayers and DualProcessRouter.

Hooks:
    H28 -- social_salience: max(identity_score, social_inference), clamped [0,1]
    H29 -- familiarity: olfactory familiarity, clamped [0,1]

Inter-module coupling (tick t -> tick t+1):
    - FG face_detected -> TPJ action_signal (1.0 if face, else 0.0)
    - Olfactory familiarity -> FG input bias (1.0 + 0.1 * familiarity)
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SocialPerceptionState:
    """Snapshot of social perception module outputs for one tick.

    FusiformGyrus: face/text detection, identity/word scores.
    TemporoparietalJunction: agency, reorienting, theory of mind.
    OlfactorySystem: familiarity, novelty.
    Computed: social_salience = max(identity_score, social_inference).
    """
    # FusiformGyrus outputs
    face_detected: bool = False
    identity_score: float = 0.0
    text_detected: bool = False
    word_score: float = 0.0

    # TemporoparietalJunction outputs
    agency_score: float = 0.5
    reorient_signal: bool = False
    social_inference: float = 0.0

    # Computed field (H28)
    social_salience: float = 0.0

    # OlfactorySystem outputs (H29)
    familiarity: float = 0.3
    is_novel: bool = False


class SocialPerceptionBridge:
    """Mediates between RadialAttentionNetwork and the Social Perception Triad.

    After each forward pass, call update(ring_activations, prediction_errors)
    to compute a SocialPerceptionState. The state is used on the NEXT forward
    pass (1-tick delay, biologically correct).

    Args:
        olfactory_system: OlfactorySystem instance (or None)
        fusiform_gyrus: FusiformGyrus instance (or None)
        temporoparietal_junction: TemporoparietalJunction instance (or None)
    """

    def __init__(
        self,
        olfactory_system=None,
        fusiform_gyrus=None,
        temporoparietal_junction=None,
    ):
        self._olfactory_system = olfactory_system
        self._fusiform_gyrus = fusiform_gyrus
        self._temporoparietal_junction = temporoparietal_junction
        self._state = SocialPerceptionState()
        self._tick_count = 0

        # Coupling caches (previous tick values)
        self._prev_familiarity = 0.3   # default olfactory familiarity
        self._prev_face_detected = False  # default FG face detection

        logger.info(
            "SocialPerceptionBridge initialized (olfa=%s, fg=%s, tpj=%s)",
            olfactory_system is not None,
            fusiform_gyrus is not None,
            temporoparietal_junction is not None,
        )

    def update(
        self,
        ring_activations: list,
        prediction_errors: list,
        neuromod_state=None,
        external_signals: Optional[Dict[str, float]] = None,
    ) -> SocialPerceptionState:
        """Compute SocialPerceptionState from current ring activations and PEs.

        Args:
            ring_activations: List of 5 numpy arrays
                [Ring1(64), Ring2(128), Ring3(256), Ring4(256), Ring5(128)]
            prediction_errors: List of floats [PE1, PE2, ...]
            neuromod_state: Optional (unused, reserved for future hooks)
            external_signals: Optional dict of social signals from external
                sources (e.g., Minibook @mentions). Expected keys:
                    sender_familiarity: float [0, 1]
                    social_salience: float [0, 1]
                    agency_signal: float [0, 1]
                    content_novelty: float [0, 1]
                These blend with module-computed values when present.

        Returns:
            SocialPerceptionState for use on next tick.
        """
        # Convert tensors to numpy if needed
        acts = []
        for a in ring_activations:
            if hasattr(a, 'detach'):
                acts.append(a.detach().cpu().numpy().flatten())
            else:
                acts.append(np.asarray(a).flatten())

        ring1 = acts[0]  # 64-dim
        avg_pe = float(np.mean(prediction_errors)) if prediction_errors else 0.1

        # ── 1. OlfactorySystem ──────────────────────────────────────────
        olfa_familiarity = 0.3
        olfa_is_novel = False
        try:
            if self._olfactory_system is not None:
                olfa_dim = min(len(ring1), 32)
                olfa_input = ring1[:olfa_dim].copy()
                if olfa_dim < 32:
                    olfa_input = np.pad(olfa_input, (0, 32 - olfa_dim))
                olfa_result = self._olfactory_system.process(olfa_input)
                if isinstance(olfa_result, dict):
                    olfa_familiarity = olfa_result.get('familiarity', 0.3)
                    olfa_is_novel = olfa_result.get('is_novel', False)
        except Exception as e:
            logger.warning("OlfactorySystem error: %s", e)

        # ── 2. FusiformGyrus ────────────────────────────────────────────
        face_detected = False
        identity_score = 0.0
        text_detected = False
        word_score = 0.0
        try:
            if self._fusiform_gyrus is not None:
                fg_dim = min(len(ring1), 32)
                fg_input = ring1[:fg_dim].copy() * (1.0 + 0.1 * self._prev_familiarity)
                if fg_dim < 32:
                    fg_input = np.pad(fg_input, (0, 32 - fg_dim))
                fg_result = self._fusiform_gyrus.process(fg_input, domain='auto')
                if isinstance(fg_result, dict):
                    face_r = fg_result.get('face_result', {})
                    if isinstance(face_r, dict):
                        face_detected = bool(face_r.get('face_detected', False))
                        identity_score = float(face_r.get('identity_score', 0.0))
                    text_r = fg_result.get('text_result', {})
                    if isinstance(text_r, dict):
                        text_detected = bool(text_r.get('text_detected', False))
                        word_score = float(text_r.get('word_score', 0.0))
        except Exception as e:
            logger.warning("FusiformGyrus error: %s", e)

        # ── 3. TemporoparietalJunction ──────────────────────────────────
        agency_score = 0.5
        reorient_signal = False
        social_inference = 0.0
        try:
            if self._temporoparietal_junction is not None:
                tpj_result = self._temporoparietal_junction.process(
                    action_signal=1.0 if self._prev_face_detected else 0.0,
                    sensory_feedback=avg_pe,
                    prediction=1.0 - avg_pe,
                )
                if isinstance(tpj_result, dict):
                    agency_r = tpj_result.get('agency_result', {})
                    if isinstance(agency_r, dict):
                        agency_score = float(agency_r.get('agency_score', 0.5))
                    tom_r = tpj_result.get('tom_result', {})
                    if isinstance(tom_r, dict):
                        social_inference = float(tom_r.get('confidence', 0.0))
                    reorient_r = tpj_result.get('reorienting_result', {})
                    if isinstance(reorient_r, dict):
                        reorient_signal = bool(reorient_r.get('reorient_signal', False))
        except Exception as e:
            logger.warning("TemporoparietalJunction error: %s", e)

        # ── Computed fields ─────────────────────────────────────────────
        social_salience = max(identity_score, social_inference)

        # ── External signal blending (e.g., Minibook) ─────────────────
        if external_signals is not None:
            ext_salience = external_signals.get('social_salience', 0.0)
            ext_familiarity = external_signals.get('sender_familiarity', 0.0)
            ext_agency = external_signals.get('agency_signal', 0.0)
            ext_novelty = external_signals.get('content_novelty', 0.0)

            # Blend: take max of module-computed vs external (most urgent wins)
            social_salience = max(social_salience, ext_salience)
            olfa_familiarity = max(olfa_familiarity, ext_familiarity)
            agency_score = max(agency_score, ext_agency)

            # External novelty can boost identity_score (social identity signal)
            identity_score = max(identity_score, ext_novelty * 0.5)

            # If external signals indicate active social engagement,
            # boost social_inference (theory-of-mind engagement)
            if ext_agency > 0.5:
                social_inference = max(social_inference, ext_agency * 0.7)

        # ── Hook clamping ───────────────────────────────────────────────
        social_salience = float(np.clip(social_salience, 0.0, 1.0))  # H28
        familiarity = float(np.clip(olfa_familiarity, 0.0, 1.0))     # H29

        # ── Build state ─────────────────────────────────────────────────
        self._state = SocialPerceptionState(
            face_detected=face_detected,
            identity_score=identity_score,
            text_detected=text_detected,
            word_score=word_score,
            agency_score=agency_score,
            reorient_signal=reorient_signal,
            social_inference=social_inference,
            social_salience=social_salience,
            familiarity=familiarity,
            is_novel=olfa_is_novel,
        )

        # ── Cache for inter-module coupling on next tick ────────────────
        self._prev_familiarity = olfa_familiarity
        self._prev_face_detected = face_detected

        self._tick_count += 1
        return self._state

    def get_state(self) -> SocialPerceptionState:
        """Return current SocialPerceptionState (read-only access)."""
        return self._state
