"""
Defense Bridge -- connects the Defense Triad (PeriaqueductalGray,
ParabrachialNucleus, BedNucleusStriaTerminalis) to the Radial Attention
Network.

Translates ring activations and prediction errors into defense signals
(defense mode, defense intensity, anxiety, alarm, autonomic activation)
that modulate RingLayers and DualProcessRouter via hooks H19-H20.

Hook-clamped fields (used by H19, H20):
  - defense_intensity (H19): PAG defense intensity [0, 1]
  - anxiety_level     (H20): BNST sustained anxiety [0, 1]

Inter-module coupling (tick t -> tick t+1):
  - PBN alarm_level -> BNST stressor_intensity (next tick, via _prev_alarm)
  - BNST anxiety_level -> PAG proximity & arousal (next tick, via _prev_anxiety)
  - PBN autonomic_activation -> PBN visceral_distress (next tick, via _prev_autonomic)

Module call signatures:
  - PBN.process(dict)  -- takes a single dict argument
  - BNST.process(threat_level=, uncertainty=, stressor_intensity=) -- kwargs
  - PAG.process(threat=, escapability=, proximity=, arousal=) -- kwargs
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DefenseState:
    """Snapshot of defense module outputs for one tick.

    PeriaqueductalGray: defense_mode, defense_intensity, emergency_mode
    ParabrachialNucleus: alarm_level, alarm_urgency, autonomic_activation
    BedNucleusStriaTerminalis: anxiety_level, vigilance, is_chronic_stress
    Derived: should_interrupt (alarm_urgency > 0.5)
    """
    # PAG outputs
    defense_mode: str = 'freeze'           # fight / flight / freeze / calm
    defense_intensity: float = 0.0         # [0, 1] defense intensity (H19 hook)
    emergency_mode: bool = False           # PAG emergency flag

    # PBN outputs
    autonomic_activation: float = 0.0      # [0, 1] autonomic activation
    alarm_level: float = 0.0              # [0, 1] alarm level
    alarm_urgency: float = 0.0            # [0, 1] alarm urgency

    # BNST outputs
    anxiety_level: float = 0.0            # [0, 1] sustained anxiety (H20 hook)
    vigilance: float = 0.3               # [0, 1] vigilance level
    is_chronic_stress: bool = False       # BNST chronic stress flag

    # Derived
    should_interrupt: bool = False        # True if alarm_urgency > 0.5


class DefenseBridge:
    """Mediates between RadialAttentionNetwork and the Defense Triad.

    After each forward pass, call update(ring_activations, prediction_errors)
    to compute a DefenseState. The state is used on the NEXT forward pass
    (1-tick delay, biologically correct).

    Args:
        parabrachial_nucleus: ParabrachialNucleus instance (alarm, autonomic)
        bnst: BedNucleusStriaTerminalis instance (anxiety, vigilance)
        periaqueductal_gray: PeriaqueductalGray instance (defense selection)
    """

    def __init__(
        self,
        parabrachial_nucleus=None,
        bnst=None,
        periaqueductal_gray=None,
    ):
        self._parabrachial_nucleus = parabrachial_nucleus
        self._bnst = bnst
        self._periaqueductal_gray = periaqueductal_gray

        # Coupling caches (previous tick values for inter-module coupling)
        self._prev_autonomic: float = 0.0
        self._prev_alarm: float = 0.0
        self._prev_anxiety: float = 0.0

        self._tick_count: int = 0
        self._state = DefenseState()

        logger.info(
            "DefenseBridge initialized (PBN + BNST + PAG)"
        )

    def update(
        self,
        ring_activations: list,
        prediction_errors: list,
        neuromod_state=None,
    ) -> DefenseState:
        """Compute DefenseState from current ring activations and prediction errors.

        Args:
            ring_activations: List of 5 numpy arrays
                [Ring1(64), Ring2(128), Ring3(256), Ring4(256), Ring5(128)]
            prediction_errors: List of 4 floats [PE1, PE2, PE3, PE4]
            neuromod_state: Optional NeuromodState (reserved for future use)

        Returns:
            DefenseState for use on next tick.
        """
        avg_pe = float(np.mean(prediction_errors)) if prediction_errors else 0.1
        pe_var = float(np.var(prediction_errors)) if len(prediction_errors) > 1 else 0.0

        # Default values (used when modules are None or calls fail)
        pbn_alarm_level = 0.0
        pbn_alarm_urgency = 0.0
        pbn_autonomic_activation = 0.0
        bnst_anxiety_level = 0.0
        bnst_vigilance = 0.3
        bnst_is_chronic_stress = False
        pag_defense_mode = 'freeze'
        pag_defense_intensity = 0.0
        pag_emergency_mode = False

        # --- ParabrachialNucleus ---
        # PBN.process() takes a DICT argument (not kwargs)
        try:
            if self._parabrachial_nucleus is not None:
                pbn_result = self._parabrachial_nucleus.process({
                    'pain': avg_pe,
                    'error_rate': avg_pe,
                    'visceral_distress': self._prev_autonomic,
                })
                pbn_alarm_level = pbn_result.get('alarm_level', 0.0)
                # PBN returns 'urgency', we map to alarm_urgency
                pbn_alarm_urgency = pbn_result.get('alarm_urgency',
                                                    pbn_result.get('urgency', 0.0))
                pbn_autonomic_activation = pbn_result.get('autonomic_activation', 0.0)
        except Exception as e:
            logger.warning("DefenseBridge: PBN.process() failed: %s", e)

        # --- BedNucleusStriaTerminalis ---
        # BNST.process() takes kwargs
        try:
            if self._bnst is not None:
                bnst_result = self._bnst.process(
                    threat_level=avg_pe,
                    uncertainty=pe_var,
                    stressor_intensity=self._prev_alarm,
                )
                bnst_anxiety_level = bnst_result.get('anxiety_level', 0.0)
                bnst_vigilance = bnst_result.get('vigilance', 0.3)
                bnst_is_chronic_stress = bnst_result.get('is_chronic_stress', False)
        except Exception as e:
            logger.warning("DefenseBridge: BNST.process() failed: %s", e)

        # --- PeriaqueductalGray ---
        # PAG.process() takes kwargs
        try:
            if self._periaqueductal_gray is not None:
                pag_result = self._periaqueductal_gray.process(
                    threat=max(self._prev_alarm, avg_pe),
                    escapability=0.5,
                    proximity=self._prev_anxiety,
                    arousal=self._prev_anxiety,
                )
                pag_defense_mode = pag_result.get('selected_defense',
                                                   pag_result.get('defense_mode', 'freeze'))
                pag_defense_intensity = pag_result.get('defense_intensity', 0.0)
                pag_emergency_mode = pag_result.get('emergency_mode', False)
        except Exception as e:
            logger.warning("DefenseBridge: PAG.process() failed: %s", e)

        # --- Compute should_interrupt ---
        should_interrupt = pbn_alarm_urgency > 0.5

        # --- Build DefenseState (clamp hook-used fields to [0, 1]) ---
        self._state = DefenseState(
            defense_mode=str(pag_defense_mode),
            defense_intensity=float(np.clip(pag_defense_intensity, 0.0, 1.0)),
            emergency_mode=bool(pag_emergency_mode),
            autonomic_activation=float(np.clip(pbn_autonomic_activation, 0.0, 1.0)),
            anxiety_level=float(np.clip(bnst_anxiety_level, 0.0, 1.0)),
            vigilance=float(np.clip(bnst_vigilance, 0.0, 1.0)),
            is_chronic_stress=bool(bnst_is_chronic_stress),
            alarm_level=float(np.clip(pbn_alarm_level, 0.0, 1.0)),
            alarm_urgency=float(np.clip(pbn_alarm_urgency, 0.0, 1.0)),
            should_interrupt=bool(should_interrupt),
        )

        # --- Cache coupling values for next tick ---
        self._prev_autonomic = pbn_autonomic_activation
        self._prev_alarm = pbn_alarm_level
        self._prev_anxiety = bnst_anxiety_level

        self._tick_count += 1
        return self._state

    def get_state(self) -> DefenseState:
        """Return current DefenseState (read-only access)."""
        return self._state
