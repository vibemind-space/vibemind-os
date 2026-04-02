"""
Sleep-Wake Bridge -- connects the Sleep/Wake Quartet (ReticularFormation,
TuberomammillaryNucleus, PinealGland, PedunculopontineNucleus) to the
Radial Attention Network.

Translates ring activations and prediction errors into sleep/wake signals
(arousal, histamine, melatonin, cholinergic tone, REM probability) that
modulate RingLayers and DualProcessRouter via hooks H14-H16.

Hook-clamped fields (used by H14, H15, H16):
  - arousal   (H14): attention gain modulation
  - histamine (H15): wakefulness gating
  - melatonin (H16): sleep pressure signal

Inter-module coupling (tick t -> tick t+1):
  - RF arousal -> TMN arousal_drive
  - PG melatonin -> TMN sleep_pressure (next tick)
  - RF arousal -> PPN arousal
  - PG sleep_pressure -> PPN sleep_pressure (next tick)
  - TMN is_awake -> RF alert_signals (next tick)
  - PG circadian -> RF circadian_phase / TMN circadian_phase (via tick counter)
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SleepWakeState:
    """Snapshot of sleep/wake module outputs for one tick.

    ReticularFormation: arousal, sensory_gain
    TuberomammillaryNucleus: histamine, is_awake, wakefulness_drive
    PinealGland: melatonin, sleep_pressure
    PedunculopontineNucleus: cholinergic_tone, rem_probability
    """
    # ReticularFormation outputs
    arousal: float = 0.5              # [0, 1] global arousal (H14 hook)
    sensory_gain: float = 0.5         # [0, 1] sensory gating gain

    # TuberomammillaryNucleus outputs
    histamine: float = 0.5            # [0, 1] histamine level (H15 hook)
    is_awake: bool = True             # Binary wakefulness flag
    wakefulness_drive: float = 0.5    # [0, 1] wakefulness drive

    # PinealGland outputs
    melatonin: float = 0.0            # [0, 1] melatonin level (H16 hook)
    sleep_pressure: float = 0.0       # [0, 1] homeostatic sleep pressure

    # PedunculopontineNucleus outputs
    cholinergic_tone: float = 0.5     # [0, 1] cholinergic tone
    rem_probability: float = 0.0      # [0, 1] REM sleep probability


class SleepWakeBridge:
    """Mediates between RadialAttentionNetwork and the Sleep/Wake Quartet.

    After each forward pass, call update(ring_activations, prediction_errors)
    to compute a SleepWakeState. The state is used on the NEXT forward pass
    (1-tick delay, biologically correct).

    Args:
        reticular_formation: ReticularFormation instance (arousal, sensory gating)
        tuberomammillary_nucleus: TuberomammillaryNucleus instance (histamine)
        pineal_gland: PinealGland instance (melatonin, circadian)
        pedunculopontine_nucleus: PedunculopontineNucleus instance (cholinergic, REM)
    """

    def __init__(
        self,
        reticular_formation=None,
        tuberomammillary_nucleus=None,
        pineal_gland=None,
        pedunculopontine_nucleus=None,
    ):
        self._reticular_formation = reticular_formation
        self._tuberomammillary_nucleus = tuberomammillary_nucleus
        self._pineal_gland = pineal_gland
        self._pedunculopontine_nucleus = pedunculopontine_nucleus

        # Coupling caches (previous tick values for inter-module coupling)
        self._prev_circadian: float = 0.5
        self._prev_is_awake: bool = True
        self._prev_melatonin: float = 0.0
        self._prev_sleep_pressure: float = 0.0

        self._tick_count: int = 0
        self._state = SleepWakeState()

        logger.info(
            "SleepWakeBridge initialized (RF + TMN + PG + PPN)"
        )

    def update(
        self,
        ring_activations: list,
        prediction_errors: list,
        neuromod_state=None,
    ) -> SleepWakeState:
        """Compute SleepWakeState from current ring activations and prediction errors.

        Args:
            ring_activations: List of 5 numpy arrays
                [Ring1(64), Ring2(128), Ring3(256), Ring4(256), Ring5(128)]
            prediction_errors: List of 4 floats [PE1, PE2, PE3, PE4]
            neuromod_state: Optional NeuromodState (reserved for future use)

        Returns:
            SleepWakeState for use on next tick.
        """
        avg_pe = float(np.mean(prediction_errors)) if prediction_errors else 0.1
        ring1 = ring_activations[0]
        avg_activation = float(np.mean(np.abs(ring1)))

        # Default values (used when modules are None or calls fail)
        rf_arousal = 0.5
        rf_sensory_gain = 0.5
        tmn_histamine = 0.5
        tmn_is_awake = True
        tmn_wakefulness_drive = 0.5
        pg_melatonin = 0.0
        pg_sleep_pressure = 0.0
        ppn_cholinergic_tone = 0.5
        ppn_rem_probability = 0.0

        # --- ReticularFormation ---
        # Sensory input from Ring 1, circadian from cache, alert from previous wakefulness
        try:
            if self._reticular_formation is not None:
                rf_result = self._reticular_formation.process(
                    sensory_input_level=avg_activation,
                    circadian_phase=self._prev_circadian,
                    alert_signals=1.0 if self._prev_is_awake else 0.0,
                )
                rf_arousal = rf_result.get('arousal', 0.5)
                rf_sensory_gain = rf_result.get('sensory_gain', 0.5)
        except Exception as e:
            logger.warning("SleepWakeBridge: RF.process() failed: %s", e)

        # --- TuberomammillaryNucleus ---
        # Arousal drive from RF, circadian from cache, sleep pressure from previous melatonin
        try:
            if self._tuberomammillary_nucleus is not None:
                tmn_result = self._tuberomammillary_nucleus.process(
                    arousal_drive=rf_arousal,
                    circadian_phase=self._prev_circadian,
                    sleep_pressure=self._prev_melatonin,
                )
                tmn_histamine = tmn_result.get('histamine_level', 0.5)
                tmn_is_awake = tmn_result.get('is_awake', True)
                tmn_wakefulness_drive = tmn_result.get('wakefulness_drive', 0.5)
        except Exception as e:
            logger.warning("SleepWakeBridge: TMN.process() failed: %s", e)

        # --- PinealGland ---
        # Light exposure fixed at 0.5, circadian from tick counter, zeitgeber from RF arousal
        try:
            if self._pineal_gland is not None:
                pg_result = self._pineal_gland.process(
                    light_exposure=0.5,
                    circadian_phase=(self._tick_count % 1000) / 1000.0,
                    external_zeitgeber=rf_arousal,
                )
                pg_melatonin = pg_result.get('melatonin_level', 0.0)
                pg_sleep_pressure = pg_result.get('sleep_pressure', 0.0)
        except Exception as e:
            logger.warning("SleepWakeBridge: PG.process() failed: %s", e)

        # --- PedunculopontineNucleus ---
        # No movement intention, standard BG release, arousal from RF, sleep pressure from cache
        try:
            if self._pedunculopontine_nucleus is not None:
                ppn_result = self._pedunculopontine_nucleus.process(
                    movement_intention=0.0,
                    bg_release=0.5,
                    arousal=rf_arousal,
                    sleep_pressure=self._prev_sleep_pressure,
                )
                ppn_cholinergic_tone = ppn_result.get('cholinergic_tone', 0.5)
                # PPN returns NESTED dict: ppn_result['rem']['rem_probability']
                rem_dict = ppn_result.get('rem', {})
                if isinstance(rem_dict, dict):
                    ppn_rem_probability = rem_dict.get('rem_probability', 0.0)
                else:
                    ppn_rem_probability = 0.0
        except Exception as e:
            logger.warning("SleepWakeBridge: PPN.process() failed: %s", e)

        # --- Build SleepWakeState (clamp hook-used fields to [0, 1]) ---
        self._state = SleepWakeState(
            arousal=float(np.clip(rf_arousal, 0.0, 1.0)),
            sensory_gain=float(np.clip(rf_sensory_gain, 0.0, 1.0)),
            histamine=float(np.clip(tmn_histamine, 0.0, 1.0)),
            is_awake=bool(tmn_is_awake),
            wakefulness_drive=float(np.clip(tmn_wakefulness_drive, 0.0, 1.0)),
            melatonin=float(np.clip(pg_melatonin, 0.0, 1.0)),
            sleep_pressure=float(np.clip(pg_sleep_pressure, 0.0, 1.0)),
            cholinergic_tone=float(np.clip(ppn_cholinergic_tone, 0.0, 1.0)),
            rem_probability=float(np.clip(ppn_rem_probability, 0.0, 1.0)),
        )

        # --- Cache coupling values for next tick ---
        self._prev_circadian = (self._tick_count % 1000) / 1000.0
        self._prev_is_awake = tmn_is_awake
        self._prev_melatonin = pg_melatonin
        self._prev_sleep_pressure = pg_sleep_pressure

        self._tick_count += 1
        return self._state

    def get_state(self) -> SleepWakeState:
        """Return current SleepWakeState (read-only access)."""
        return self._state
