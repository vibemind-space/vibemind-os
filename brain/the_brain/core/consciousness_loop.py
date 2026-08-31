"""
ConsciousnessLoop — Recursive feedback for integrated consciousness.

Reads from IntegrationBridge (Claustrum binding, DMN self-referential),
CortexBridge (ACC conflict), and SocialPerceptionBridge (TPJ self/other)
to compute a scalar consciousness_level in [0, 1].

The consciousness_level feeds back to:
  - Ring 5 (Meta): sharper attention at high consciousness
  - DualProcess threshold: System 2 bias at high consciousness
  - DMN gating: mind-wandering when conscious + low load

Follows 1-tick delay pattern: consciousness computed from tick t data,
applied on tick t+1 (biologically correct, consistent with all bridges).

See: docs/plans/2026-03-01-full-bridge-integration-design.md (Phase 9)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ConsciousnessState:
    """Snapshot of consciousness computation at one tick.

    Attributes:
        consciousness_level: Global workspace awareness [0, 1].
            0.0 = no integration (unconscious automatic processing)
            0.5 = moderate awareness (routine conscious processing)
            1.0 = peak awareness (vivid, reflective, deliberate)
        integration_score: Cross-modal binding quality from Claustrum.
        self_referential: DMN self-referential activation.
        conflict: ACC response conflict signal.
        agency: TPJ self/other distinction.
        cognitive_load: Estimated processing demands [0, 1].
        dmn_gated: Whether DMN mind-wandering is allowed.
        system2_bias: Additional System 2 bias from consciousness.
        ring5_gain: Multiplicative gain for Ring 5 (Meta) attention.
    """
    consciousness_level: float = 0.5
    integration_score: float = 0.5
    self_referential: float = 0.3
    conflict: float = 0.0
    agency: float = 0.5
    cognitive_load: float = 0.5
    dmn_gated: bool = False
    system2_bias: float = 0.0
    ring5_gain: float = 1.0


class ConsciousnessLoop:
    """Recursive consciousness feedback loop.

    On each tick:
      1. Read bridge states (Integration, Cortex, Social)
      2. Compute consciousness_level from weighted inputs
      3. Derive feedback signals (Ring 5 gain, DualProcess bias, DMN gate)
      4. Store state for use on NEXT tick (1-tick delay)

    Parameters
    ----------
    integration_weight : float
        Weight for Claustrum binding_strength in consciousness formula.
    dmn_weight : float
        Weight for DMN self-referential activation.
    conflict_weight : float
        Weight for ACC conflict (higher conflict -> higher consciousness).
    agency_weight : float
        Weight for TPJ self/other distinction (agency_score).
    consciousness_threshold : float
        Minimum consciousness_level to engage System 2 bias.
    dmn_load_threshold : float
        Maximum cognitive load for DMN mind-wandering.
    ring5_gain_scale : float
        How strongly consciousness_level scales Ring 5 attention.
    system2_bias_scale : float
        How strongly consciousness_level lowers DualProcess threshold.
    smoothing : float
        Exponential smoothing alpha for consciousness_level (0=no change, 1=instant).
    """

    def __init__(
        self,
        integration_weight: float = 0.35,
        dmn_weight: float = 0.20,
        conflict_weight: float = 0.25,
        agency_weight: float = 0.20,
        consciousness_threshold: float = 0.6,
        dmn_load_threshold: float = 0.4,
        ring5_gain_scale: float = 0.6,
        system2_bias_scale: float = 0.3,
        smoothing: float = 0.3,
    ):
        self._w_integration = integration_weight
        self._w_dmn = dmn_weight
        self._w_conflict = conflict_weight
        self._w_agency = agency_weight
        self._consciousness_threshold = consciousness_threshold
        self._dmn_load_threshold = dmn_load_threshold
        self._ring5_gain_scale = ring5_gain_scale
        self._system2_bias_scale = system2_bias_scale
        self._smoothing = smoothing

        # 1-tick delay: current state (computed last tick, used this tick)
        self._current_state = ConsciousnessState()
        # Previous raw value for smoothing
        self._prev_raw = 0.5
        self._tick_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> ConsciousnessState:
        """Current consciousness state (read by radial network on this tick)."""
        return self._current_state

    @property
    def consciousness_level(self) -> float:
        """Shortcut for current consciousness_level."""
        return self._current_state.consciousness_level

    def update(
        self,
        integration_state=None,
        cortex_state=None,
        social_state=None,
        ring_activations: Optional[list] = None,
        prediction_errors: Optional[list] = None,
    ) -> ConsciousnessState:
        """Compute new consciousness state for NEXT tick.

        Called after bridge updates in RadialAttentionNetwork.forward().
        The returned state is stored and used on the NEXT forward pass
        (1-tick delay, biologically correct).

        Parameters
        ----------
        integration_state : IntegrationState or None
            From IntegrationBridge (Claustrum, DMN, SC).
        cortex_state : CortexState or None
            From CortexBridge (PFC, ACC, OFC).
        social_state : SocialPerceptionState or None
            From SocialPerceptionBridge (TPJ, FFA).
        ring_activations : list of torch.Tensor or None
            5 ring activation tensors (for cognitive load estimate).
        prediction_errors : list of float or None
            4 prediction error values (for cognitive load estimate).

        Returns
        -------
        ConsciousnessState
            New state that will be active on the next tick.
        """
        # --- Extract signals from bridge states ---
        integration_score = 0.5
        dmn_activation = 0.3
        reached_consciousness = False

        if integration_state is not None:
            integration_score = getattr(
                integration_state, 'binding_strength', 0.5
            )
            dmn_activation = getattr(
                integration_state, 'dmn_activation', 0.3
            )
            reached_consciousness = getattr(
                integration_state, 'reached_consciousness', False
            )

        conflict = 0.0
        if cortex_state is not None:
            conflict = getattr(cortex_state, 'conflict', 0.0)

        agency = 0.5
        if social_state is not None:
            agency = getattr(social_state, 'agency_score', 0.5)

        # --- Estimate cognitive load ---
        cognitive_load = self._estimate_cognitive_load(
            ring_activations, prediction_errors
        )

        # --- Compute raw consciousness level ---
        # Weighted sum of input signals, each in [0, 1]
        raw = (
            self._w_integration * float(integration_score)
            + self._w_dmn * float(dmn_activation)
            + self._w_conflict * float(conflict)
            + self._w_agency * float(agency)
        )

        # Claustrum consciousness gate: if not reached, dampen
        if not reached_consciousness:
            raw *= 0.6  # Partial awareness without full binding

        # Clamp to [0, 1]
        raw = max(0.0, min(1.0, raw))

        # Exponential smoothing for temporal stability
        smoothed = (
            self._smoothing * raw
            + (1.0 - self._smoothing) * self._prev_raw
        )
        smoothed = max(0.0, min(1.0, smoothed))
        self._prev_raw = smoothed

        # --- Derive feedback signals ---

        # Ring 5 gain: higher consciousness = sharper meta-attention
        # Base gain = 1.0, scales up to (1.0 + ring5_gain_scale)
        ring5_gain = 1.0 + self._ring5_gain_scale * (smoothed - 0.5)
        ring5_gain = max(0.5, min(2.0, ring5_gain))

        # System 2 bias: additional threshold reduction at high consciousness
        # Only active above consciousness_threshold
        if smoothed > self._consciousness_threshold:
            excess = smoothed - self._consciousness_threshold
            system2_bias = self._system2_bias_scale * excess
        else:
            system2_bias = 0.0

        # DMN gating: allow mind-wandering when conscious + low load
        dmn_gated = (
            smoothed > self._consciousness_threshold
            and cognitive_load < self._dmn_load_threshold
        )

        # --- Build new state ---
        new_state = ConsciousnessState(
            consciousness_level=smoothed,
            integration_score=float(integration_score),
            self_referential=float(dmn_activation),
            conflict=float(conflict),
            agency=float(agency),
            cognitive_load=cognitive_load,
            dmn_gated=dmn_gated,
            system2_bias=system2_bias,
            ring5_gain=ring5_gain,
        )

        # Store for next tick (1-tick delay)
        self._current_state = new_state
        self._tick_count += 1

        if self._tick_count % 100 == 0:
            logger.debug(
                "ConsciousnessLoop tick %d: level=%.3f, load=%.3f, "
                "dmn_gated=%s, s2_bias=%.3f",
                self._tick_count, smoothed, cognitive_load,
                dmn_gated, system2_bias,
            )

        return new_state

    def get_ring5_bias(self, ring5_dim: int = 128) -> np.ndarray:
        """Generate additive bias for Ring 5 based on consciousness_level.

        Higher consciousness -> stronger meta-cognitive attention.
        Returns a gain vector that multiplicatively modulates Ring 5.

        Parameters
        ----------
        ring5_dim : int
            Dimension of Ring 5 (default 128).

        Returns
        -------
        np.ndarray
            Ring 5 gain vector (ring5_dim,).
        """
        gain = self._current_state.ring5_gain
        return np.full(ring5_dim, gain, dtype=np.float32)

    def get_threshold_adjustment(self) -> float:
        """Get DualProcess threshold multiplier from consciousness.

        High consciousness -> lower effective threshold -> System 2 bias.

        Returns
        -------
        float
            Multiplier for DualProcess threshold (< 1.0 biases to System 2).
        """
        return max(0.5, 1.0 - self._current_state.system2_bias)

    def get_dmn_gate(self) -> bool:
        """Whether DMN mind-wandering should be allowed.

        True when consciousness is high AND cognitive load is low.
        """
        return self._current_state.dmn_gated

    def get_stats(self) -> dict:
        """Return loop statistics."""
        s = self._current_state
        return {
            'tick_count': self._tick_count,
            'consciousness_level': s.consciousness_level,
            'integration_score': s.integration_score,
            'self_referential': s.self_referential,
            'conflict': s.conflict,
            'agency': s.agency,
            'cognitive_load': s.cognitive_load,
            'dmn_gated': s.dmn_gated,
            'system2_bias': s.system2_bias,
            'ring5_gain': s.ring5_gain,
        }

    def reset(self):
        """Reset to default state."""
        self._current_state = ConsciousnessState()
        self._prev_raw = 0.5
        self._tick_count = 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _estimate_cognitive_load(
        self,
        ring_activations: Optional[list],
        prediction_errors: Optional[list],
    ) -> float:
        """Estimate cognitive load from ring activations and PEs.

        High activation norms + high prediction errors = high load.
        Low/calm activations + low PE = low load.

        Returns float in [0, 1].
        """
        load = 0.5  # Default moderate load

        if prediction_errors is not None and len(prediction_errors) > 0:
            pe_mean = float(np.mean([
                float(pe) for pe in prediction_errors
            ]))
            # PE typically in [0, 1], map to load contribution
            pe_load = min(1.0, pe_mean * 2.0)
            load = pe_load

        if ring_activations is not None and len(ring_activations) > 0:
            # Use Ring 4 (Abstract) and Ring 5 (Meta) norms as load proxy
            try:
                import torch
                # Higher-order ring activity = higher cognitive demand
                if len(ring_activations) >= 5:
                    ring4_norm = ring_activations[3].detach().abs().mean().item()
                    ring5_norm = ring_activations[4].detach().abs().mean().item()
                    # Normalize: typical norms are ~0.1-1.0
                    activity_load = min(1.0, (ring4_norm + ring5_norm) / 2.0)
                    # Blend with PE-based load
                    load = 0.6 * load + 0.4 * activity_load
            except Exception:
                pass  # Graceful degradation

        return max(0.0, min(1.0, load))
