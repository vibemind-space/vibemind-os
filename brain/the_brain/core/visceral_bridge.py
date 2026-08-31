"""
Visceral Bridge -- connects the Visceral Duo (NTS + VP) to the
Radial Attention Network.

Translates ring activations and prediction errors into visceral/hedonic
signals (visceral_level, afferent_strength, liking, wanting, approach)
that modulate RingLayers and DualProcessRouter.

Module calls:
    NucleusTractSolitarius.process(dict) -> visceral relay + reflex
    VentralPallidum.process(kwargs) -> hedonic liking + motor approach

Hooks:
    H26: afferent_strength  -- clamped [0, 1]
    H27: liking             -- clamped [0, 1]

Coupling caches (1-tick delay, biologically correct):
    _prev_visceral: NTS overall_visceral feeds back into NTS
                    visceral_distress and VP inhibition (* 0.3)
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VisceralState:
    """Snapshot of visceral module outputs for one tick.

    NTS: visceral sensory relay, afferent signal strength, autonomic reflex.
    VP:  hedonic liking, incentive wanting, approach motor drive.
    """
    # NTS outputs
    visceral_level: float = 0.5        # [0, 1] overall visceral state
    afferent_strength: float = 0.3     # [0, 1] afferent signal -- H26 clamped
    reflex_active: bool = False        # Autonomic reflex flag

    # VP outputs
    liking: float = 0.5               # [0, 1] hedonic response -- H27 clamped
    wanting: float = 0.5              # [0, 1] incentive wanting
    approach_strength: float = 0.3    # [0, 1] approach motor drive


class VisceralBridge:
    """Mediates between RadialAttentionNetwork and the Visceral Duo
    (NucleusTractSolitarius + VentralPallidum).

    After each forward pass, call update(ring_activations, prediction_errors)
    to compute a VisceralState. The state is used on the NEXT forward pass
    (1-tick delay, biologically correct).

    Inter-module coupling (tick t -> tick t+1):
        - NTS overall_visceral -> NTS visceral_distress (self-feedback)
        - NTS overall_visceral * 0.3 -> VP inhibition

    Args:
        nucleus_tractus_solitarius: NucleusTractSolitarius instance (or None)
        ventral_pallidum: VentralPallidum instance (or None)
    """

    def __init__(
        self,
        nucleus_tractus_solitarius=None,
        ventral_pallidum=None,
    ):
        self._nucleus_tractus_solitarius = nucleus_tractus_solitarius
        self._ventral_pallidum = ventral_pallidum
        self._state = VisceralState()
        self._tick_count = 0

        # Coupling cache (previous tick)
        self._prev_visceral: float = 0.0

        logger.info("VisceralBridge initialized (NTS + VP)")

    def update(
        self,
        ring_activations: list,
        prediction_errors: list,
    ) -> VisceralState:
        """Compute VisceralState from current ring activations and prediction errors.

        Args:
            ring_activations: List of 5 numpy arrays
                [Ring1(64), Ring2(128), Ring3(256), Ring4(256), Ring5(128)]
            prediction_errors: List of 4 floats [PE1, PE2, PE3, PE4]

        Returns:
            VisceralState for use on next tick.
        """
        avg_pe = float(np.mean(prediction_errors)) if prediction_errors else 0.1

        # --- NTS processing ---
        nts_visceral = 0.5
        nts_afferent = 0.3
        nts_reflex = False

        if self._nucleus_tractus_solitarius is not None:
            try:
                nts_result = self._nucleus_tractus_solitarius.process({
                    'heart_rate': 0.5,
                    'breathing_rate': 0.5,
                    'nutrient_status': 0.5,
                    'error_rate': avg_pe,
                    'visceral_distress': self._prev_visceral,
                })
                nts_visceral = nts_result.get(
                    'overall_visceral',
                    nts_result.get('visceral_level', 0.5),
                )
                nts_afferent = nts_result.get('afferent_strength', 0.3)
                nts_reflex = nts_result.get(
                    'reflex_active',
                    nts_result.get('autonomic_reflex', False),
                )
            except Exception as e:
                logger.warning("NTS processing failed: %s", e)

        # --- VP processing ---
        vp_liking = 0.5
        vp_wanting = 0.5
        vp_approach = 0.3

        if self._ventral_pallidum is not None:
            try:
                vp_result = self._ventral_pallidum.process(
                    reward_signal=1.0 - avg_pe,
                    opioid_level=0.5,
                    wanting_signal=0.5,
                    inhibition=self._prev_visceral * 0.3,
                )
                # VP returns nested dicts
                liking_dict = vp_result.get('liking', {})
                if isinstance(liking_dict, dict):
                    vp_liking = liking_dict.get('liking_response', 0.5)
                else:
                    vp_liking = float(liking_dict)

                motor_dict = vp_result.get('motor', {})
                if isinstance(motor_dict, dict):
                    vp_approach = motor_dict.get('approach_strength', 0.3)
                else:
                    vp_approach = float(motor_dict)

                wanting_val = vp_result.get('wanting_signal', 0.5)
                if isinstance(wanting_val, dict):
                    vp_wanting = wanting_val.get('wanting', 0.5)
                else:
                    vp_wanting = float(wanting_val)
            except Exception as e:
                logger.warning("VP processing failed: %s", e)

        # --- Build VisceralState (clamp hook fields) ---
        self._state = VisceralState(
            visceral_level=float(np.clip(nts_visceral, 0.0, 1.0)),
            afferent_strength=float(np.clip(nts_afferent, 0.0, 1.0)),  # H26
            reflex_active=bool(nts_reflex),
            liking=float(np.clip(vp_liking, 0.0, 1.0)),               # H27
            wanting=float(np.clip(vp_wanting, 0.0, 1.0)),
            approach_strength=float(np.clip(vp_approach, 0.0, 1.0)),
        )

        # --- Update coupling caches ---
        self._prev_visceral = float(nts_visceral)

        self._tick_count += 1
        return self._state

    def get_state(self) -> VisceralState:
        """Return current VisceralState (read-only access)."""
        return self._state
