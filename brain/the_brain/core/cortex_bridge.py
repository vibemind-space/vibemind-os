"""
Cortex Bridge -- connects the Cortex Trio (PFC, ACC, OFC) to the Radial Attention Network.

Translates ring activations and prediction errors into cognitive signals
(attention bias, conflict monitoring, value estimation) that modulate
RingLayers, DualProcessRouter, and top-down attention.

See: docs/plans/2026-02-26-cortex-bridge-design.md
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CortexState:
    """Snapshot of cortex module outputs for one tick.

    PFC outputs: top-down attention bias and inhibition.
    ACC outputs: conflict monitoring and cognitive control.
    OFC outputs: value estimation and decision confidence.
    """
    # PFC outputs
    bias_signal: Optional[np.ndarray] = None  # Top-down attention bias [pfc_state_dim]
    inhibit: bool = False                      # Should current action be suppressed?
    pfc_value: float = 0.5                     # State value estimate
    pfc_surprise: float = 0.0                  # Reward prediction error

    # ACC outputs
    conflict: float = 0.0                      # Response conflict [0, 1]
    control_signal: float = 0.5                # Cognitive effort [0, 1]
    error_likelihood: float = 0.0              # P(error) [0, 1]

    # OFC outputs
    subjective_value: float = 0.5              # Net action value
    decision_confidence: float = 0.5           # How sure about choice [0, 1]
    choice_difficulty: float = 0.5             # 1 - confidence


class CortexBridge:
    """Mediates between RadialAttentionNetwork and the Cortex Trio (PFC, ACC, OFC).

    After each forward pass, call update(ring_activations, prediction_errors)
    to compute a CortexState. The state is used on the NEXT forward pass
    (1-tick delay, biologically correct).

    Inter-module coupling (tick t -> tick t+1):
        - ACC conflict -> PFC context['conflict']
        - ACC effort -> OFC effort_cost
        - ACC error_likelihood -> OFC risk

    Args:
        pfc: PrefrontalCortex instance
        acc: AnteriorCingulateCortex instance
        ofc: OrbitofrontalCortex instance
        ring_to_pfc_dim: projection dim for Ring 4 -> PFC (default 32)
        ring_to_ofc_dim: projection dim for Ring 2 -> OFC (default 8)
    """

    def __init__(self, pfc, acc, ofc, ring_to_pfc_dim: int = 32,
                 ring_to_ofc_dim: int = 8):
        self._pfc = pfc
        self._acc = acc
        self._ofc = ofc
        self._state = CortexState()
        self._tick_count = 0

        # Dimension projections (numpy, no gradients)
        # Ring 4 (Abstract, 256D) -> PFC (32D)
        self._ring4_to_pfc = np.random.randn(ring_to_pfc_dim, 256) * 0.01
        # Ring 2 (Pattern, 128D) -> OFC (8D)
        self._ring2_to_ofc = np.random.randn(ring_to_ofc_dim, 128) * 0.01

        # Cache ACC outputs for inter-module coupling (previous tick)
        self._prev_acc_conflict = 0.0
        self._prev_acc_effort = 0.0
        self._prev_acc_error_likelihood = 0.0

        logger.info("CortexBridge initialized (PFC + ACC + OFC)")

    def update(self, ring_activations: list, prediction_errors: list,
               neuromod_state=None) -> CortexState:
        """Compute CortexState from current ring activations and prediction errors.

        Args:
            ring_activations: List of 5 numpy arrays (or tensors, auto-converted)
                              [Ring1(64), Ring2(128), Ring3(256), Ring4(256), Ring5(128)]
            prediction_errors: List of 4 floats [PE1, PE2, PE3, PE4]
            neuromod_state: Optional NeuromodState (unused for now, reserved)

        Returns:
            CortexState for use on next tick.
        """
        # Convert tensors to numpy if needed
        acts = []
        for a in ring_activations:
            if hasattr(a, 'detach'):
                acts.append(a.detach().cpu().numpy().flatten())
            else:
                acts.append(np.asarray(a).flatten())

        avg_error = sum(prediction_errors) / max(len(prediction_errors), 1)

        # --- Ring 4 (Abstract, 256D) -> PFC (32D) ---
        ring4 = acts[3]  # Index 3 = Ring 4 (Abstract)
        pfc_input = self._ring4_to_pfc @ ring4[:256]
        pfc_context = {'conflict': self._prev_acc_conflict}
        pfc_result = self._pfc.process(state=pfc_input, context=pfc_context)

        # --- Ring 5 (Meta, 128D) -> ACC (top 8 channels) ---
        ring5 = acts[4]  # Index 4 = Ring 5 (Meta)
        acc_activations = ring5[:8]  # Top 8 channels as response activations
        reward_magnitude = 1.0 - avg_error
        acc_result = self._acc.process(acc_activations, reward_magnitude)

        # --- Ring 2 (Pattern, 128D) -> OFC (8D) ---
        ring2 = acts[1]  # Index 1 = Ring 2 (Pattern)
        ofc_features = self._ring2_to_ofc @ ring2[:128]
        ofc_result = self._ofc.process(
            features=ofc_features,
            reward_history=reward_magnitude,
            effort_cost=self._prev_acc_effort,
            risk=self._prev_acc_error_likelihood,
        )

        # --- Build CortexState ---
        self._state = CortexState(
            bias_signal=pfc_result.get('bias_signal'),
            inhibit=pfc_result.get('inhibit', False),
            pfc_value=pfc_result.get('value', 0.5),
            pfc_surprise=pfc_result.get('surprise', 0.0),
            conflict=acc_result.get('conflict', 0.0),
            control_signal=acc_result.get('control_signal', 0.5),
            error_likelihood=acc_result.get('error_likelihood', 0.0),
            subjective_value=ofc_result.get('subjective_value', 0.5),
            decision_confidence=ofc_result.get('value_confidence', 0.5),
            choice_difficulty=1.0 - ofc_result.get('value_confidence', 0.5),
        )

        # Cache ACC outputs for inter-module coupling on next tick
        self._prev_acc_conflict = acc_result.get('conflict', 0.0)
        self._prev_acc_effort = acc_result.get('effort', 0.0)
        self._prev_acc_error_likelihood = acc_result.get('error_likelihood', 0.0)

        self._tick_count += 1
        return self._state

    def get_state(self) -> CortexState:
        """Return current CortexState (read-only access)."""
        return self._state
