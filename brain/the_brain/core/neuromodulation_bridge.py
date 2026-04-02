"""
Neuromodulation Bridge -- connects neuromodulator brain modules to the Radial Attention Network.

Translates prediction errors into neuromodulator signals (DA, NE, 5-HT, ACh, anti-reward)
that modulate attention gain, precision gating, plasticity, and stability in RingLayers.

See: docs/plans/2026-02-25-neuromodulation-bridge-design.md
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class NeuromodState:
    """Snapshot of neuromodulator levels for one tick.

    All values are floats in [0, 1] except ne_gain which is [0.2, 2.0].
    Passed to RingLayer.forward() and DualProcessRouter.forward() as optional param.
    """
    dopamine: float = 0.5        # VTA: precision/salience boost
    norepinephrine: float = 0.5  # LC: attention gain
    serotonin: float = 0.5       # Raphe: stability/consolidation
    acetylcholine: float = 0.5   # BF: plasticity gate
    anti_reward: float = 0.0     # LHb: suppression signal
    ne_gain: float = 1.0         # LC derived gain [0.2, 2.0]
    explore_ratio: float = 0.5   # LC explore/exploit [0, 1]


class NeuromodulationBridge:
    """Mediates between RadialAttentionNetwork prediction errors and 5 neuromodulator modules.

    After each forward pass, call update(prediction_errors) to compute a NeuromodState.
    The state is used on the NEXT forward pass (1-tick delay, biologically correct).

    Inter-module coupling:
        - LHb anti_reward (prev tick) -> VTA lhb_inhibition
        - LC arousal -> BasalForebrain arousal
        - VTA rpe -> BasalForebrain reward_signal

    Args:
        vta: VentralTegmentalArea instance (dopamine)
        lc: LocusCoeruleus instance (norepinephrine)
        raphe: RapheNuclei instance (serotonin)
        basal_forebrain: BasalForebrain instance (acetylcholine)
        lateral_habenula: LateralHabenula instance (anti-reward)
    """

    def __init__(self, vta, lc, raphe, basal_forebrain, lateral_habenula):
        self._vta = vta
        self._lc = lc
        self._raphe = raphe
        self._bf = basal_forebrain
        self._lhb = lateral_habenula

        self._state = NeuromodState()
        self._prev_avg_error = 0.0
        self._tick_count = 0

    def update(self, prediction_errors: List[float]) -> NeuromodState:
        """Compute new neuromodulator state from prediction errors.

        Args:
            prediction_errors: List of per-ring prediction errors from RadialAttentionNetwork.
                              Typically 4 values (rings 1-4, inner->outer). Can be empty.

        Returns:
            NeuromodState with updated transmitter levels.
        """
        if not prediction_errors:
            self._tick_count += 1
            return self._state

        avg_error = sum(prediction_errors) / len(prediction_errors)
        max_error = max(prediction_errors)
        min_error = min(prediction_errors)
        error_spread = max_error - min_error

        # --- VTA (Dopamine) ---
        # Low error = "prediction correct" = reward; high error = surprise
        vta_result = self._vta.process(
            actual_reward=1.0 - avg_error,
            novelty=max_error,
            lhb_inhibition=self._state.anti_reward,  # Previous tick's LHb
        )

        # --- LC (Norepinephrine) ---
        # Low error = good performance; error spread = conflict
        lc_result = self._lc.process(
            task_performance=1.0 - avg_error,
            conflict=error_spread,
        )

        # --- Raphe (Serotonin) ---
        # Low error = reward flowing = patience
        raphe_result = self._raphe.process(
            reward_rate=1.0 - avg_error,
            goal_progress=1.0 - avg_error,
        )

        # --- BasalForebrain (Acetylcholine) ---
        # Coupled to LC (arousal) and VTA (reward signal)
        bf_result = self._bf.process(
            attention_demand=max_error,
            arousal=lc_result['arousal'],
            reward_signal=vta_result['rpe'],
        )

        # --- LHb (Anti-Reward) ---
        # Compares previous vs current error (deterioration = disappointment)
        lhb_result = self._lhb.process(
            expected_reward=1.0 - self._prev_avg_error,
            actual_reward=1.0 - avg_error,
        )

        self._prev_avg_error = avg_error
        self._tick_count += 1

        self._state = NeuromodState(
            dopamine=vta_result['dopamine']['total_da'],
            norepinephrine=lc_result['ne_level'],
            serotonin=raphe_result['serotonin'],
            acetylcholine=bf_result['ach_level'],
            anti_reward=lhb_result['anti_reward'],
            ne_gain=lc_result['gain'],
            explore_ratio=lc_result['explore_ratio'],
        )

        return self._state

    @property
    def state(self) -> NeuromodState:
        """Current neuromodulator state (read-only)."""
        return self._state

    def get_state(self) -> Dict[str, Any]:
        """Full state for monitoring/debugging."""
        return {
            'neuromod_state': {
                'dopamine': self._state.dopamine,
                'norepinephrine': self._state.norepinephrine,
                'serotonin': self._state.serotonin,
                'acetylcholine': self._state.acetylcholine,
                'anti_reward': self._state.anti_reward,
                'ne_gain': self._state.ne_gain,
                'explore_ratio': self._state.explore_ratio,
            },
            'tick_count': self._tick_count,
            'prev_avg_error': self._prev_avg_error,
        }
