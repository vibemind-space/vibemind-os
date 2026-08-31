"""
Motor Bridge -- connects the Motor Quintet (Cerebellum, SubstantiaNigra,
ZonaIncerta, RedNucleus, PosteriorParietalCortex) to the Radial Attention
Network.

Translates ring activations and prediction errors into motor-planning signals
(prediction error, motor DA, inhibition, action tendency, movement confidence)
that modulate RingLayers and DualProcessRouter via hooks H17-H18.

Hook-clamped fields (used by H17, H18):
  - model_confidence (H17): cerebellar forward-model confidence
  - action_tendency  (H18): zona incerta limbic-motor integration

Inter-module coupling (tick t -> tick t+1):
  - CB prediction_error -> RN error_signal (same tick, intra-tick)
  - CB model_confidence -> RN cerebellar_input (same tick, intra-tick)
  - SN motor_da -> ZI motivation (next tick, via _prev_motor_da)
  - PPC peak_salience -> SN action_value (next tick, via _prev_peak_salience)
  - ZI inhibition_level -> PPC goal_relevance modulation (next tick, via _prev_inhibition)
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class MotorState:
    """Snapshot of motor module outputs for one tick.

    Cerebellum: prediction_error, model_confidence
    SubstantiaNigra: motor_da, go_nogo_balance, disinhibited
    ZonaIncerta: inhibition_level, action_tendency
    RedNucleus: is_compensating, error_correction
    PosteriorParietalCortex: peak_salience, movement_confidence
    """
    # Cerebellum outputs
    prediction_error: float = 0.0       # [0, inf) sensory prediction error
    model_confidence: float = 0.5       # [0, 1] forward-model confidence (H17)

    # SubstantiaNigra outputs
    motor_da: float = 0.5              # [0, 1] nigrostriatal dopamine
    go_nogo_balance: float = 0.0       # [-1, 1] go/nogo pathway balance
    disinhibited: bool = False          # SNr disinhibition flag

    # ZonaIncerta outputs
    inhibition_level: float = 0.5      # [0, 1] GABAergic inhibition
    action_tendency: float = 0.5       # [0, 1] limbic-motor integration (H18)

    # RedNucleus outputs
    is_compensating: bool = False       # Rubrospinal backup active
    error_correction: float = 0.0      # Error correction signal

    # PosteriorParietalCortex outputs
    peak_salience: float = 0.5         # [0, 1] spatial attention peak
    movement_confidence: float = 0.5   # [0, 1] action plan confidence


class MotorBridge:
    """Mediates between RadialAttentionNetwork and the Motor Quintet.

    After each forward pass, call update(ring_activations, prediction_errors)
    to compute a MotorState. The state is used on the NEXT forward pass
    (1-tick delay, biologically correct).

    Args:
        cerebellum: CerebellumModule instance (prediction error, model confidence)
        substantia_nigra: SubstantiaNigra instance (motor DA, go/nogo)
        zona_incerta: ZonaIncerta instance (inhibition, action tendency)
        red_nucleus: RedNucleus instance (motor backup, error correction)
        posterior_parietal_cortex: PosteriorParietalCortex instance (spatial attention, action planning)
    """

    def __init__(
        self,
        cerebellum=None,
        substantia_nigra=None,
        zona_incerta=None,
        red_nucleus=None,
        posterior_parietal_cortex=None,
    ):
        self._cerebellum = cerebellum
        self._substantia_nigra = substantia_nigra
        self._zona_incerta = zona_incerta
        self._red_nucleus = red_nucleus
        self._posterior_parietal_cortex = posterior_parietal_cortex

        # Coupling caches (previous tick values for inter-module coupling)
        self._prev_peak_salience: float = 0.5
        self._prev_motor_da: float = 0.5
        self._prev_inhibition: float = 0.5

        self._tick_count: int = 0
        self._state = MotorState()

        logger.info(
            "MotorBridge initialized (CB + SN + ZI + RN + PPC)"
        )

    def update(
        self,
        ring_activations: list,
        prediction_errors: list,
        neuromod_state=None,
    ) -> MotorState:
        """Compute MotorState from current ring activations and prediction errors.

        Args:
            ring_activations: List of 5 numpy arrays
                [Ring1(64), Ring2(128), Ring3(256), Ring4(256), Ring5(128)]
            prediction_errors: List of 4 floats [PE1, PE2, PE3, PE4]
            neuromod_state: Optional NeuromodState (reserved for future use)

        Returns:
            MotorState for use on next tick.
        """
        # Convert tensors to numpy if needed
        acts = []
        for a in ring_activations:
            if hasattr(a, 'detach'):
                acts.append(a.detach().cpu().numpy().flatten())
            else:
                acts.append(np.asarray(a).flatten())

        ring1 = acts[0]   # 64-dim
        ring2 = acts[1]   # 128-dim
        avg_pe = float(np.mean(prediction_errors)) if prediction_errors else 0.1

        # Default values (used when modules are None or calls fail)
        cb_prediction_error = 0.0
        cb_model_confidence = 0.5
        sn_motor_da = 0.5
        sn_go_nogo_balance = 0.0
        sn_disinhibited = False
        zi_inhibition_level = 0.5
        zi_action_tendency = 0.5
        rn_is_compensating = False
        rn_error_correction = 0.0
        ppc_peak_salience = 0.5
        ppc_movement_confidence = 0.5

        # --- Cerebellum ---
        # Compare ring2 prediction with ring1 actual
        try:
            if self._cerebellum is not None:
                cb_dim = min(len(ring1), len(ring2), 16)
                cb_result = self._cerebellum.compute_sensory_prediction_error(
                    predicted_sensory=ring2[:cb_dim],
                    actual_sensory=ring1[:cb_dim],
                )
                cb_prediction_error = cb_result.get('prediction_error', 0.0)
                cb_model_confidence = cb_result.get('model_confidence', 0.5)
        except Exception as e:
            logger.warning("MotorBridge: CB.compute_sensory_prediction_error() failed: %s", e)

        # --- SubstantiaNigra ---
        try:
            if self._substantia_nigra is not None:
                sn_result = self._substantia_nigra.process(
                    motor_demand=avg_pe,
                    effort=0.5,
                    action_value=self._prev_peak_salience,
                )
                sn_motor_da = sn_result.get('motor_da', 0.5)
                sn_go_nogo_balance = sn_result.get('go_nogo_balance', 0.0)
                sn_disinhibited = sn_result.get('disinhibited', False)
        except Exception as e:
            logger.warning("MotorBridge: SN.process() failed: %s", e)

        # --- ZonaIncerta ---
        try:
            if self._zona_incerta is not None:
                zi_result = self._zona_incerta.process(
                    motivation=self._prev_motor_da,
                    motor_readiness=0.5,
                    arousal=0.5,
                )
                zi_inhibition_level = zi_result.get('inhibition_level', 0.5)
                zi_action_tendency = zi_result.get('action_tendency', 0.5)
        except Exception as e:
            logger.warning("MotorBridge: ZI.process() failed: %s", e)

        # --- RedNucleus ---
        # Intra-tick coupling: CB prediction_error -> RN error_signal
        try:
            if self._red_nucleus is not None:
                rn_result = self._red_nucleus.process(
                    primary_motor_signal=0.5,
                    error_signal=cb_prediction_error,
                    cerebellar_input=cb_model_confidence,
                )
                rn_is_compensating = rn_result.get('is_compensating', False)
                rn_error_correction = rn_result.get('error_correction', 0.0)
        except Exception as e:
            logger.warning("MotorBridge: RN.process() failed: %s", e)

        # --- PosteriorParietalCortex ---
        # Inter-tick coupling: ZI inhibition modulates goal relevance
        try:
            if self._posterior_parietal_cortex is not None:
                ppc_dim = 16
                ppc_vis = ring1[:ppc_dim] if len(ring1) >= ppc_dim else np.pad(
                    ring1, (0, ppc_dim - len(ring1))
                )
                ppc_goal = ppc_vis * (1.0 - self._prev_inhibition)
                ppc_result = self._posterior_parietal_cortex.process(
                    visual_salience=ppc_vis,
                    goal_relevance=ppc_goal,
                )
                ppc_peak_salience = ppc_result.get('peak_salience', 0.5)
                # NESTED dict: ppc_result['action_plan']['movement_confidence']
                action_plan = ppc_result.get('action_plan', {})
                if isinstance(action_plan, dict):
                    ppc_movement_confidence = action_plan.get('movement_confidence', 0.5)
                else:
                    ppc_movement_confidence = 0.5
        except Exception as e:
            logger.warning("MotorBridge: PPC.process() failed: %s", e)

        # --- Build MotorState (clamp hook-used fields to [0, 1]) ---
        self._state = MotorState(
            prediction_error=float(cb_prediction_error),
            model_confidence=float(np.clip(cb_model_confidence, 0.0, 1.0)),
            motor_da=float(sn_motor_da),
            go_nogo_balance=float(sn_go_nogo_balance),
            disinhibited=bool(sn_disinhibited),
            inhibition_level=float(zi_inhibition_level),
            action_tendency=float(np.clip(zi_action_tendency, 0.0, 1.0)),
            is_compensating=bool(rn_is_compensating),
            error_correction=float(rn_error_correction),
            peak_salience=float(ppc_peak_salience),
            movement_confidence=float(ppc_movement_confidence),
        )

        # --- Cache coupling values for next tick ---
        self._prev_peak_salience = ppc_peak_salience
        self._prev_motor_da = sn_motor_da
        self._prev_inhibition = zi_inhibition_level

        self._tick_count += 1
        return self._state

    def get_state(self) -> MotorState:
        """Return current MotorState (read-only access)."""
        return self._state
