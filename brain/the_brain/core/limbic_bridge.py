"""
Limbic Bridge -- connects the Limbic Quartet (Amygdala, NAcc, InsularCortex,
Hypothalamus) to the Radial Attention Network.

Translates ring activations and prediction errors into emotional/motivational
signals (arousal, salience, go/nogo drives, urgency) that modulate RingLayers
and DualProcessRouter.

See: docs/plans/2026-02-26-limbic-bridge-design.md
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class LimbicState:
    """Snapshot of limbic module outputs for one tick.

    Amygdala: emotional valence, arousal, threat detection.
    NucleusAccumbens: approach/avoidance motivation.
    InsularCortex: salience, body budget, subjective feeling.
    Hypothalamus: homeostatic urgency, approach drives, stress.
    """
    # Amygdala outputs
    valence: float = 0.0           # [-1, 1] emotional valence
    arousal: float = 0.3           # [0, 1] emotional arousal
    threat_level: float = 0.0      # [0, 1] threat detection
    is_threat: bool = False        # Binary threat flag

    # NucleusAccumbens outputs
    go_drive: float = 0.5          # [0, 1] approach motivation
    nogo_drive: float = 0.5        # [0, 1] avoidance motivation
    net_value: float = 0.0         # Benefit - Cost
    effort_cost: float = 0.3       # [0, 1] perceived effort

    # InsularCortex outputs
    salience: float = 0.3          # [0, 1] overall salience
    body_budget: float = 1.0       # [0, 1] allostatic balance
    feeling: str = 'neutral'       # Subjective feeling label

    # Hypothalamus outputs
    urgency: float = 0.0           # [0, 1] homeostatic urgency
    approach_drive: float = 0.3    # [0, 1] lateral hypothalamus
    stress: float = 0.0            # [0, 1] HPA cortisol


class LimbicBridge:
    """Mediates between RadialAttentionNetwork and the Limbic Quartet.

    After each forward pass, call update(ring_activations, prediction_errors)
    to compute a LimbicState. The state is used on the NEXT forward pass
    (1-tick delay, biologically correct).

    Inter-module coupling (tick t -> tick t+1):
        - Amygdala hpa_activation -> Hypothalamus process_stressor()
        - Amygdala arousal -> InsularCortex emotional_intensity
        - Amygdala threat_level -> NAcc threat
        - Hypothalamus stress -> InsularCortex stress
        - Hypothalamus urgency -> NAcc energy (1 - urgency)
        - InsularCortex body_state -> Amygdala context

    Args:
        amygdala: AmygdalaComplex instance
        nucleus_accumbens: NucleusAccumbens instance
        insular_cortex: InsularCortex instance
        hypothalamus: HypothalamusModule instance
    """

    def __init__(self, amygdala, nucleus_accumbens, insular_cortex, hypothalamus):
        self._amygdala = amygdala
        self._nucleus_accumbens = nucleus_accumbens
        self._insular_cortex = insular_cortex
        self._hypothalamus = hypothalamus
        self._state = LimbicState()
        self._tick_count = 0

        # Projection: Ring 1 (Sensory, 64D) -> Amygdala (10 features)
        self._ring1_to_amygdala = np.random.randn(10, 64) * 0.01

        # Cache for inter-module coupling (previous tick)
        self._prev_hpa_activation = 0.0
        self._prev_amygdala_arousal = 0.3  # Default arousal
        self._prev_amygdala_threat = 0.0
        self._prev_hypo_stress = 0.0
        self._prev_hypo_urgency = 0.0
        self._prev_insula_body_state = None

        logger.info("LimbicBridge initialized (Amygdala + NAcc + InsularCortex + Hypothalamus)")

    def update(self, ring_activations: list, prediction_errors: list,
               neuromod_state=None) -> LimbicState:
        """Compute LimbicState from current ring activations and prediction errors.

        Args:
            ring_activations: List of 5 numpy arrays
                [Ring1(64), Ring2(128), Ring3(256), Ring4(256), Ring5(128)]
            prediction_errors: List of 4 floats [PE1, PE2, PE3, PE4]
            neuromod_state: Optional NeuromodState (provides dopamine for NAcc)

        Returns:
            LimbicState for use on next tick.
        """
        # Convert tensors to numpy if needed
        acts = []
        for a in ring_activations:
            if hasattr(a, 'detach'):
                acts.append(a.detach().cpu().numpy().flatten())
            else:
                acts.append(np.asarray(a).flatten())

        avg_pe = sum(prediction_errors) / max(len(prediction_errors), 1)

        # 1. Ring 1 (Sensory, 64D) -> Amygdala (10 features via projection)
        ring1 = acts[0]
        amygdala_features = self._ring1_to_amygdala @ ring1[:64]
        amygdala_result = self._amygdala.process_stimulus(
            features=amygdala_features,
            context=self._prev_insula_body_state,
        )
        evaluation = amygdala_result.get('evaluation', {})
        response = amygdala_result.get('response', {})

        # 2. InsularCortex (novelty from avg PE, arousal from previous amygdala)
        insula_result = self._insular_cortex.process(
            novelty=avg_pe,
            emotional_intensity=self._prev_amygdala_arousal,
            stress=self._prev_hypo_stress,
        )

        # 3. Hypothalamus (autonomous, no ring input)
        self._hypothalamus.process_stressor(self._prev_hpa_activation)
        hypo_result = self._hypothalamus.update_drives(elapsed_seconds=1.0)

        # 4. NucleusAccumbens (aggregates all)
        dopamine = 0.5
        if neuromod_state is not None and hasattr(neuromod_state, 'dopamine'):
            dopamine = neuromod_state.dopamine
        nacc_result = self._nucleus_accumbens.evaluate(
            dopamine=dopamine,
            reward_prediction=1.0 - avg_pe,
            threat=evaluation.get('threat_level', 0.0),
            energy=1.0 - hypo_result.get('urgency', 0.0),
        )

        # Build LimbicState (clamp hook-used fields to [0, 1] for safety)
        self._state = LimbicState(
            valence=evaluation.get('valence', 0.0),
            arousal=float(np.clip(evaluation.get('arousal', 0.3), 0.0, 1.0)),
            threat_level=evaluation.get('threat_level', 0.0),
            is_threat=amygdala_result.get('is_threat', False),
            go_drive=nacc_result.get('go_drive', 0.5),
            nogo_drive=float(np.clip(nacc_result.get('nogo_drive', 0.5), 0.0, 1.0)),
            net_value=nacc_result.get('net_value', 0.0),
            effort_cost=nacc_result.get('effort_cost', 0.3),
            salience=float(np.clip(insula_result.get('salience', 0.3), 0.0, 1.0)),
            body_budget=insula_result.get('body_budget', 1.0),
            feeling=insula_result.get('feeling', 'neutral'),
            urgency=float(np.clip(hypo_result.get('urgency', 0.0), 0.0, 1.0)),
            approach_drive=hypo_result.get('approach_drive', 0.3),
            stress=hypo_result.get('stress', 0.0),
        )

        # Cache for inter-module coupling on next tick
        self._prev_hpa_activation = response.get('hpa_activation', 0.0)
        self._prev_amygdala_arousal = evaluation.get('arousal', 0.3)
        self._prev_amygdala_threat = evaluation.get('threat_level', 0.0)
        self._prev_hypo_stress = hypo_result.get('stress', 0.0)
        self._prev_hypo_urgency = hypo_result.get('urgency', 0.0)
        self._prev_insula_body_state = insula_result.get('body_state')

        self._tick_count += 1
        return self._state

    def get_state(self) -> LimbicState:
        """Return current LimbicState (read-only access)."""
        return self._state
