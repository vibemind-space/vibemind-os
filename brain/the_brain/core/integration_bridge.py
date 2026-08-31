"""
Integration Bridge -- connects the Integration Quintet (SuperiorColliculus,
DefaultModeNetwork, Claustrum, CorticalColumn, CorpusCallosum) to the
Radial Attention Network.

Translates ring activations and prediction errors into integration signals
(binding, consciousness, orienting, cortical error, bilateral coherence) that
modulate RingLayers and DualProcessRouter.

Hooks:
    H23: binding_strength   (Claustrum cross-modal binding)   [0, 1]
    H24: dmn_activation     (DMN self-referential activation)  [0, 1]
    H25: orienting_saliency (SC peak saliency / orienting)     [0, 1]

Inter-module coupling (tick t -> tick t+1):
    - SC peak_saliency      -> Claustrum salience
    - DMN activation_level  -> Claustrum attention (inverse: 1 - activation)
    - CorpusCallosum coherence -> CorticalColumn cortical_input scaling
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class IntegrationState:
    """Snapshot of integration module outputs for one tick.

    Claustrum: cross-modal binding and consciousness gating.
    DefaultModeNetwork: self-referential processing and mode.
    SuperiorColliculus: orienting and saliency.
    CorticalColumn: prediction error and output magnitude.
    CorpusCallosum: bilateral coherence and transfer efficiency.
    """
    # Claustrum outputs
    binding_strength: float = 0.5       # [0, 1] H23 hook-clamped
    reached_consciousness: bool = False  # Consciousness gate

    # DefaultModeNetwork outputs
    dmn_activation: float = 0.3         # [0, 1] H24 hook-clamped
    dmn_mode: str = 'default'           # DMN mode label

    # SuperiorColliculus outputs
    orienting_saliency: float = 0.3     # [0, 1] H25 hook-clamped

    # CorticalColumn outputs
    cortical_error: float = 0.0         # Prediction error magnitude
    cortical_output: float = 0.5        # Output magnitude

    # CorpusCallosum outputs
    bilateral_coherence: float = 0.5    # Coordination quality
    transfer_efficiency: float = 0.5    # Transfer efficiency


class IntegrationBridge:
    """Mediates between RadialAttentionNetwork and the Integration Quintet.

    After each forward pass, call update(ring_activations, prediction_errors)
    to compute an IntegrationState. The state is used on the NEXT forward pass
    (1-tick delay, biologically correct).

    Inter-module coupling (tick t -> tick t+1):
        - SC peak_saliency      -> Claustrum salience
        - DMN activation_level  -> Claustrum attention (1 - activation)
        - CorpusCallosum coherence -> CorticalColumn cortical_input scaling

    Args:
        superior_colliculus: SuperiorColliculus instance (or None)
        default_mode_network: DefaultModeNetwork instance (or None)
        claustrum: Claustrum instance (or None)
        cortical_column: CorticalColumn instance (or None)
        corpus_callosum: CorpusCallosum instance (or None)
    """

    def __init__(
        self,
        superior_colliculus=None,
        default_mode_network=None,
        claustrum=None,
        cortical_column=None,
        corpus_callosum=None,
    ):
        self._superior_colliculus = superior_colliculus
        self._default_mode_network = default_mode_network
        self._claustrum = claustrum
        self._cortical_column = cortical_column
        self._corpus_callosum = corpus_callosum
        self._state = IntegrationState()
        self._tick_count = 0

        # Cache for inter-module coupling (previous tick)
        self._prev_saliency = 0.3
        self._prev_dmn_activation = 0.3
        self._prev_coherence = 0.5

        logger.info(
            "IntegrationBridge initialized (SC=%s DMN=%s Claustrum=%s "
            "CorticalColumn=%s CorpusCallosum=%s)",
            superior_colliculus is not None,
            default_mode_network is not None,
            claustrum is not None,
            cortical_column is not None,
            corpus_callosum is not None,
        )

    def update(
        self,
        ring_activations: list,
        prediction_errors: list,
    ) -> IntegrationState:
        """Compute IntegrationState from current ring activations and PEs.

        Args:
            ring_activations: List of 5 numpy arrays
                [Ring1(64), Ring2(128), Ring3(256), Ring4(256), Ring5(128)]
            prediction_errors: List of floats [PE1, PE2, PE3, PE4]

        Returns:
            IntegrationState for use on next tick.
        """
        # Convert tensors to numpy if needed
        acts = []
        for a in ring_activations:
            if hasattr(a, 'detach'):
                acts.append(a.detach().cpu().numpy().flatten())
            else:
                acts.append(np.asarray(a).flatten())

        ring1 = acts[0]   # 64-dim
        ring3 = acts[2]   # 256-dim
        ring4 = acts[3]   # 256-dim

        avg_pe = float(np.mean(prediction_errors)) if prediction_errors else 0.1
        pe_var = float(np.var(prediction_errors)) if len(prediction_errors) > 1 else 0.0

        # --- Defaults (used when module is None) ---
        orienting_saliency = 0.3
        dmn_activation = 0.3
        dmn_mode = 'default'
        binding_strength = 0.5
        reached_consciousness = False
        cortical_error = 0.0
        cortical_output = 0.5
        bilateral_coherence = 0.5
        transfer_efficiency = 0.5

        # 1. SuperiorColliculus -- visual saliency / orienting
        if self._superior_colliculus is not None:
            try:
                sc_dim = min(len(ring1), 16)
                sc_result = self._superior_colliculus.process(
                    visual=ring1[:sc_dim],
                )
                orienting_saliency = sc_result.get(
                    'peak_saliency',
                    sc_result.get('orienting_response',
                                  sc_result.get('salience', 0.3))
                )
            except Exception as e:
                logger.warning("IntegrationBridge: SC failed: %s", e)

        # 2. DefaultModeNetwork -- self-referential processing
        if self._default_mode_network is not None:
            try:
                dmn_dim = min(len(ring4), 32)
                dmn_result = self._default_mode_network.process(
                    state=ring4[:dmn_dim],
                    task_load=1.0 - pe_var,
                )
                # DMN.process returns a DMNOutput dataclass, not a dict
                if hasattr(dmn_result, 'activation_level'):
                    dmn_activation = dmn_result.activation_level
                    dmn_mode = dmn_result.mode
                else:
                    # Fallback if it returns a dict
                    dmn_activation = dmn_result.get('activation', 0.3)
                    dmn_mode = dmn_result.get('mode', 'default')
            except Exception as e:
                logger.warning("IntegrationBridge: DMN failed: %s", e)

        # 3. Claustrum -- cross-modal binding + consciousness gating
        if self._claustrum is not None:
            try:
                claustrum_result = self._claustrum.process(
                    modality_signals={'ring1': ring1, 'ring3': ring3},
                    salience=self._prev_saliency,
                    attention=1.0 - self._prev_dmn_activation,
                )
                # binding_strength from Claustrum is a matrix (ndarray)
                bs_raw = claustrum_result.get('binding_strength', 0.5)
                if isinstance(bs_raw, np.ndarray):
                    # Compute mean of off-diagonal elements as scalar binding
                    if bs_raw.ndim == 2 and bs_raw.shape[0] > 1:
                        mask = ~np.eye(bs_raw.shape[0], dtype=bool)
                        binding_strength = float(np.mean(bs_raw[mask]))
                    else:
                        binding_strength = float(np.mean(bs_raw))
                else:
                    binding_strength = float(bs_raw)
                reached_consciousness = claustrum_result.get(
                    'reached_consciousness', False
                )
            except Exception as e:
                logger.warning("IntegrationBridge: Claustrum failed: %s", e)

        # 4. CorticalColumn -- prediction error and output
        if self._cortical_column is not None:
            try:
                cc_dim = min(len(ring1), 8)
                cortical_input = (
                    ring3[:cc_dim] * self._prev_coherence
                    if len(ring3) >= cc_dim
                    else ring1[:cc_dim]
                )
                cc_result = self._cortical_column.process(
                    thalamic_input=ring1[:cc_dim],
                    cortical_input=cortical_input,
                )
                cortical_error = cc_result.get('error_magnitude', 0.0)
                cortical_output = cc_result.get('output_magnitude', 0.5)
            except Exception as e:
                logger.warning("IntegrationBridge: CorticalColumn failed: %s", e)

        # 5. CorpusCallosum -- bilateral coherence + transfer
        if self._corpus_callosum is not None:
            try:
                cc_half = min(len(ring3) // 2, 16)
                left_signal = ring3[:cc_half]
                right_signal = (
                    ring3[cc_half:cc_half * 2]
                    if len(ring3) >= cc_half * 2
                    else ring3[:cc_half]
                )
                cc_corpus_result = self._corpus_callosum.process(
                    left_signal=left_signal,
                    right_signal=right_signal,
                )
                bilateral_coherence = cc_corpus_result.get(
                    'coordination_quality',
                    cc_corpus_result.get('coherence', 0.5)
                )
                transfer_efficiency = cc_corpus_result.get(
                    'transfer_efficiency', 0.5
                )
            except Exception as e:
                logger.warning("IntegrationBridge: CorpusCallosum failed: %s", e)

        # Build IntegrationState -- clamp hook fields to [0, 1]
        self._state = IntegrationState(
            binding_strength=float(np.clip(binding_strength, 0.0, 1.0)),
            reached_consciousness=reached_consciousness,
            dmn_activation=float(np.clip(dmn_activation, 0.0, 1.0)),
            dmn_mode=dmn_mode,
            orienting_saliency=float(np.clip(orienting_saliency, 0.0, 1.0)),
            cortical_error=cortical_error,
            cortical_output=cortical_output,
            bilateral_coherence=bilateral_coherence,
            transfer_efficiency=transfer_efficiency,
        )

        # Cache for inter-module coupling on next tick
        self._prev_saliency = float(np.clip(orienting_saliency, 0.0, 1.0))
        self._prev_dmn_activation = float(np.clip(dmn_activation, 0.0, 1.0))
        self._prev_coherence = float(np.clip(bilateral_coherence, 0.0, 1.0))

        self._tick_count += 1
        return self._state

    def get_state(self) -> IntegrationState:
        """Return current IntegrationState (read-only access)."""
        return self._state
