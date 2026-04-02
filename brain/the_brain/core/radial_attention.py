"""
Radial Attention Network — learned intelligence core for Tahlamus.

5 concentric rings of increasing abstraction around a thalamic center.
Bottom-up: prediction errors propagate outward.
Top-down: predictions flow inward.
Training: Hebbian live + Backprop sleep.

See: docs/plans/2026-02-25-radial-attention-network-design.md
"""
import logging
import math
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)


class RingLayer(nn.Module):
    """One concentric ring = one abstraction level.

    Implements: Self-Attention -> Predictive Coding Error -> FFN -> Residual + Norm.
    """

    def __init__(self, in_dim: int, out_dim: int, num_heads: int = 4,
                 ffn_mult: int = 4, dropout: float = 0.1):
        super().__init__()
        self.in_dim = in_dim
        self.out_dim = out_dim
        self.num_heads = num_heads

        # Project input to out_dim if dimensions differ
        self.input_proj = nn.Linear(in_dim, out_dim) if in_dim != out_dim else nn.Identity()

        # Self-Attention
        self.self_attention = nn.MultiheadAttention(
            embed_dim=out_dim, num_heads=num_heads,
            dropout=dropout, batch_first=True,
        )

        # Precision gate — learns how much to trust prediction errors
        self.precision_gate = nn.Sequential(
            nn.Linear(out_dim, out_dim),
            nn.Sigmoid(),
        )

        # Feedforward network
        self.ffn = nn.Sequential(
            nn.Linear(out_dim, out_dim * ffn_mult),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(out_dim * ffn_mult, out_dim),
            nn.Dropout(dropout),
        )

        # Layer normalization
        self.norm1 = nn.LayerNorm(out_dim)
        self.norm2 = nn.LayerNorm(out_dim)

        # Hebbian attention bias — updated live, no gradients
        self.register_buffer(
            'attention_bias',
            torch.zeros(out_dim, out_dim),
        )

    def forward(self, bottom_up: torch.Tensor,
                top_down_prediction: Optional[torch.Tensor] = None,
                neuromod=None,
                cortex_state=None,
                limbic_state=None,
                modulation=None,
                ) -> torch.Tensor:
        """Process signal through this ring.

        Args:
            bottom_up: Signal from inner ring (batch, in_dim)
            top_down_prediction: Prediction from outer ring (batch, out_dim)
            neuromod: LEGACY -- Optional NeuromodState (use modulation instead).
            cortex_state: LEGACY -- Optional CortexState (use modulation instead).
            limbic_state: LEGACY -- Optional LimbicState (use modulation instead).
            modulation: Optional ModulationContext with pre-computed composite factors.
        """
        # Project to ring dimension
        x = self.input_proj(bottom_up)

        # Ensure 3D for attention: (batch, seq=1, dim)
        if x.dim() == 2:
            x = x.unsqueeze(1)

        # Self-Attention (Hebbian bias wired in Task 3)
        attended, _ = self.self_attention(x, x, x)

        # === ATTENTION GAIN ===
        if modulation is not None:
            attended = attended * modulation.attention_gain
        else:
            # Legacy per-hook path (backward compat)
            if neuromod is not None:
                attended = attended * neuromod.ne_gain  # H1
            if limbic_state is not None:
                arousal_gain = 0.7 + 0.6 * limbic_state.arousal  # H10
                attended = attended * arousal_gain

        attended = self.norm1(attended + x)  # Residual + Norm

        # Squeeze back to 2D
        attended = attended.squeeze(1)

        # Predictive Coding: precision-weighted error modulates the signal
        if top_down_prediction is not None:
            error = attended - top_down_prediction
            precision = self.precision_gate(error)

            # === PRECISION GATE ===
            if modulation is not None:
                precision = precision * modulation.precision_boost
            else:
                # Legacy per-hook path (backward compat)
                if neuromod is not None:
                    da_boost = 0.5 + neuromod.dopamine         # [0.5, 1.5]
                    anti_dampen = 1.0 - 0.5 * neuromod.anti_reward  # [0.5, 1.0]
                    precision = precision * da_boost * anti_dampen  # H2
                if cortex_state is not None:
                    value_boost = 0.8 + 0.4 * cortex_state.subjective_value  # H9
                    precision = precision * value_boost
                if limbic_state is not None:
                    sal_boost = 0.8 + 0.4 * limbic_state.salience  # H11
                    precision = precision * sal_boost

            # Additive correction: zero error -> signal == attended (no change)
            signal = attended + error * precision
        else:
            signal = attended

        # Feedforward + Residual + Norm
        output = self.ffn(signal)

        # === FFN THROUGHPUT ===
        if modulation is not None:
            output = output * modulation.ffn_throughput
        else:
            # Legacy per-hook path (backward compat)
            if neuromod is not None:
                ach_gate = 0.5 + neuromod.acetylcholine  # H3
                output = output * ach_gate
                stability = 0.8 + 0.4 * neuromod.serotonin  # H4
                output = output * stability
            if limbic_state is not None:
                urg_gate = 0.8 + 0.4 * limbic_state.urgency  # H13
                output = output * urg_gate

        output = self.norm2(output + signal)

        return output


class RadialAttentionNetwork(nn.Module):
    """5 concentric rings around a thalamic center.

    Ring 1 (Sensory):  VIS+AUD+SOM -> 64-dim, 4 heads
    Ring 2 (Pattern):  OFC+INS     -> 128-dim, 4 heads
    Ring 3 (Semantic): LAN+MTL     -> 256-dim, 8 heads
    Ring 4 (Abstract): DLPFC+DMN   -> 256-dim, 8 heads
    Ring 5 (Meta):     ACC         -> 128-dim, 4 heads

    Signal flows bottom-up (radial outward) with top-down predictions.
    Only prediction errors propagate between rings.
    """

    RING_SPECS = [
        # (name, out_dim, num_heads)
        ('sensory',  64,  4),
        ('pattern',  128, 4),
        ('semantic', 256, 8),
        ('abstract', 256, 8),
        ('meta',     128, 4),
    ]

    def __init__(self, seed_dim: int = 384, thalamic_dim: int = 128,
                 dropout: float = 0.1):
        super().__init__()
        self.seed_dim = seed_dim
        self.thalamic_dim = thalamic_dim

        # Thalamic encoder: input embedding -> seed
        self.thalamic_encoder = nn.Sequential(
            nn.Linear(seed_dim, thalamic_dim),
            nn.GELU(),
            nn.LayerNorm(thalamic_dim),
        )

        # Build rings with increasing dimensions
        self.rings = nn.ModuleList()
        prev_dim = thalamic_dim
        for name, out_dim, heads in self.RING_SPECS:
            self.rings.append(RingLayer(
                in_dim=prev_dim, out_dim=out_dim,
                num_heads=heads, dropout=dropout,
            ))
            prev_dim = out_dim

        # Top-down prediction projections (outer -> inner)
        self.top_down_projections = nn.ModuleList()
        for i in range(len(self.RING_SPECS) - 1):
            outer_dim = self.RING_SPECS[i + 1][1]
            inner_dim = self.RING_SPECS[i][1]
            self.top_down_projections.append(
                nn.Linear(outer_dim, inner_dim)
            )

        # Neuromodulation bridge (optional, attached via attach_neuromodulation)
        self._neuromod_bridge = None
        self._neuromod_state = None

        # Cortex bridge (optional, attached via attach_cortex)
        self._cortex_bridge = None
        self._cortex_state = None

        # Limbic bridge (optional, attached via attach_limbic)
        self._limbic_bridge = None
        self._limbic_state = None

        # Generic bridge registry (for new bridges)
        self._bridges = {}  # name -> bridge instance
        self._bridge_states = {}  # name -> state from last update

        # Consciousness loop (optional, attached via attach_consciousness_loop)
        self._consciousness_loop = None

    def attach_neuromodulation(self, bridge) -> None:
        """Attach a NeuromodulationBridge for live neuromodulator modulation.

        Args:
            bridge: NeuromodulationBridge instance.
        """
        self._neuromod_bridge = bridge
        logger.info("NeuromodulationBridge attached to RadialAttentionNetwork")

    def attach_cortex(self, bridge) -> None:
        """Attach a CortexBridge for cognitive modulation (PFC, ACC, OFC).

        Args:
            bridge: CortexBridge instance.
        """
        self._cortex_bridge = bridge
        self._cortex_state = None
        # Learnable projection: PFC bias (32D) -> Ring 4 dim (256D)
        self._pfc_bias_proj = nn.Linear(32, 256, bias=False)
        logger.info("CortexBridge attached to RadialAttentionNetwork")

    def attach_limbic(self, bridge) -> None:
        """Attach a LimbicBridge for emotional/motivational modulation.

        Args:
            bridge: LimbicBridge instance.
        """
        self._limbic_bridge = bridge
        self._limbic_state = None
        logger.info("LimbicBridge attached to RadialAttentionNetwork")

    def attach_bridge(self, name: str, bridge) -> None:
        """Attach a bridge by name. Used for new bridges (sleep_wake, motor, etc.)."""
        self._bridges[name] = bridge
        self._bridge_states[name] = None
        logger.info(f"{name} bridge attached to RadialAttentionNetwork")

    def attach_consciousness_loop(self, loop) -> None:
        """Attach a ConsciousnessLoop for recursive consciousness feedback.

        Args:
            loop: ConsciousnessLoop instance.
        """
        self._consciousness_loop = loop
        logger.info("ConsciousnessLoop attached to RadialAttentionNetwork")

    def forward(self, seed_embedding: torch.Tensor) -> Dict[str, any]:
        """Full radial pass: bottom-up then top-down.

        Args:
            seed_embedding: Input from Moltbook/BrainChat (batch, seed_dim)

        Returns:
            Dict with ring_activations, meta_output, thalamic_seed,
            prediction_errors, neuromod_state, modulation_context.
        """
        # Import here to avoid circular imports
        from core.modulation_context import ModulationContext

        # Thalamic encoding
        thalamic = self.thalamic_encoder(seed_embedding)

        # Build ModulationContext from current bridge states
        mod_ctx = ModulationContext()
        mod_ctx.neuromod = self._neuromod_state
        mod_ctx.cortex = self._cortex_state
        mod_ctx.limbic = self._limbic_state
        # Populate from generic bridge registry
        for name, state in self._bridge_states.items():
            if state is not None and hasattr(mod_ctx, name):
                setattr(mod_ctx, name, state)
        mod_ctx.compute()

        # -- Bottom-Up Pass (radial outward) --
        ring_activations = []
        x = thalamic
        for ring in self.rings:
            x = ring(x, modulation=mod_ctx)
            ring_activations.append(x)

        # Hook 7: PFC bias additive on Ring 4 (Abstract)
        # Uses ring4_bias from ModulationContext (set by cortex hooks in compute())
        if mod_ctx.ring4_bias is not None and hasattr(self, '_pfc_bias_proj'):
            bias_tensor = torch.tensor(
                mod_ctx.ring4_bias, dtype=torch.float32
            ).unsqueeze(0)  # (1, 32)
            bias_expanded = self._pfc_bias_proj(bias_tensor)  # (1, 256)
            ring_activations[3] = ring_activations[3] + bias_expanded * 0.1

        # Consciousness feedback: Ring 5 gain from PREVIOUS tick
        # Higher consciousness -> sharper meta-cognitive attention
        if self._consciousness_loop is not None:
            c_state = self._consciousness_loop.state
            ring5_gain = c_state.ring5_gain
            ring_activations[4] = ring_activations[4] * ring5_gain
            # Apply consciousness System 2 bias to threshold_mod
            thr_adj = self._consciousness_loop.get_threshold_adjustment()
            mod_ctx.threshold_mod *= thr_adj
            # Store consciousness level on ModulationContext
            mod_ctx.consciousness_level = c_state.consciousness_level
            mod_ctx.consciousness_state = c_state

        # -- Top-Down Pass (predictions inward) --
        prediction_errors = []
        for i in range(len(self.rings) - 1, 0, -1):
            # Outer ring predicts what inner ring should look like
            prediction = self.top_down_projections[i - 1](ring_activations[i])

            # Re-run inner ring with top-down prediction
            if i == 1:
                inner_input = thalamic
            else:
                inner_input = ring_activations[i - 2]

            refined = self.rings[i - 1](
                inner_input, top_down_prediction=prediction,
                modulation=mod_ctx,
            )
            error = (ring_activations[i - 1] - refined).abs().mean().item()
            prediction_errors.append(error)
            ring_activations[i - 1] = refined

        prediction_errors.reverse()  # Inner -> outer order

        # Update neuromodulation for NEXT tick (1-tick delay)
        if self._neuromod_bridge is not None:
            self._neuromod_state = self._neuromod_bridge.update(prediction_errors)

        # Update cortex for NEXT tick (1-tick delay)
        if self._cortex_bridge is not None:
            np_activations = [a.detach().cpu().numpy().flatten()
                              for a in ring_activations]
            self._cortex_state = self._cortex_bridge.update(
                np_activations, prediction_errors, self._neuromod_state
            )

        # Update limbic for NEXT tick (1-tick delay)
        if self._limbic_bridge is not None:
            np_activations = [a.detach().cpu().numpy().flatten()
                              for a in ring_activations]
            self._limbic_state = self._limbic_bridge.update(
                np_activations, prediction_errors, self._neuromod_state
            )

        # Update generic bridges for NEXT tick (1-tick delay)
        for name, bridge in self._bridges.items():
            if hasattr(bridge, 'update'):
                try:
                    np_activations = [a.detach().cpu().numpy().flatten()
                                      for a in ring_activations]
                    self._bridge_states[name] = bridge.update(
                        np_activations, prediction_errors
                    )
                except Exception as e:
                    logger.warning(f"Bridge {name} update failed: {e}")

        # Update ConsciousnessLoop for NEXT tick (1-tick delay)
        if self._consciousness_loop is not None:
            self._consciousness_loop.update(
                integration_state=self._bridge_states.get('integration'),
                cortex_state=self._cortex_state,
                social_state=self._bridge_states.get('social'),
                ring_activations=ring_activations,
                prediction_errors=prediction_errors,
            )

        return {
            'ring_activations': ring_activations,
            'meta_output': ring_activations[-1],      # Ring 5 = final output
            'thalamic_seed': thalamic,
            'prediction_errors': prediction_errors,
            'neuromod_state': self._neuromod_state,
            'cortex_state': self._cortex_state,
            'limbic_state': self._limbic_state,
            'modulation_context': mod_ctx,
            'consciousness_state': (
                self._consciousness_loop.state
                if self._consciousness_loop is not None else None
            ),
        }

    def get_hebbian_targets(self) -> List[torch.Tensor]:
        """Current attention biases as training targets (shaped by reward-modulated Hebbian)."""
        return [ring.attention_bias.detach().clone() for ring in self.rings]

    def get_parameter_count(self) -> Dict[str, int]:
        """Parameter count breakdown by component."""
        counts = {'thalamic_encoder': sum(
            p.numel() for p in self.thalamic_encoder.parameters()
        )}
        for i, (name, _, _) in enumerate(self.RING_SPECS):
            counts[f'ring_{i+1}_{name}'] = sum(
                p.numel() for p in self.rings[i].parameters()
            )
        counts['top_down'] = sum(
            p.numel() for p in self.top_down_projections.parameters()
        )
        counts['total'] = sum(p.numel() for p in self.parameters())
        return counts

    @classmethod
    def from_yaml(cls, yaml_config: dict) -> 'RadialAttentionNetwork':
        """Create from YAML config."""
        rc = yaml_config.get('radial_attention', {})
        return cls(
            seed_dim=rc.get('seed_dim', 384),
            thalamic_dim=rc.get('thalamic_dim', 128),
            dropout=rc.get('dropout', 0.1),
        )


class DualProcessRouter(nn.Module):
    """ACC-based router: System 1 (fast/intuitive) vs System 2 (slow/deliberate).

    Measures conflict between fast and slow paths.
    Low conflict -> trust fast path (System 1).
    High conflict -> use slow path (System 2).

    Conflict is primarily geometric (cosine distance, normalized to [0,1]).
    A learned head adjusts the boundary over time via sleep training.
    """

    def __init__(self, dim: int = 128, conflict_threshold: float = 0.3):
        super().__init__()
        self.conflict_threshold = conflict_threshold
        # Learned conflict adjustment — starts at 0 (no effect)
        self.conflict_head = nn.Sequential(
            nn.Linear(dim * 2, dim),
            nn.GELU(),
            nn.Linear(dim, 1),
        )
        # Initialize final layer to near-zero so head starts neutral
        nn.init.zeros_(self.conflict_head[-1].weight)
        nn.init.zeros_(self.conflict_head[-1].bias)

    def forward(self, system1_output: torch.Tensor,
                system2_output: torch.Tensor,
                neuromod=None, cortex_state=None, limbic_state=None,
                modulation=None) -> Dict[str, any]:
        """Decide which system's output to use.

        Args:
            system1_output: Fast path result (batch, dim)
            system2_output: Slow path result (batch, dim)
            neuromod: LEGACY -- Optional NeuromodState (use modulation instead).
            cortex_state: LEGACY -- Optional CortexState (use modulation instead).
            limbic_state: LEGACY -- Optional LimbicState (use modulation instead).
            modulation: Optional ModulationContext with pre-computed threshold_mod.

        Returns:
            Dict with 'output', 'system_used', 'conflict_level'.
        """
        # Primary signal: cosine distance normalized to [0, 1]
        cos_sim = F.cosine_similarity(
            system1_output.flatten(), system2_output.flatten(), dim=0
        ).item()
        distance = (1.0 - cos_sim) / 2.0  # [0, 1]

        # Learned adjustment: sigmoid centered at 0 -> range [-0.5, 0.5]
        combined = torch.cat([system1_output, system2_output], dim=-1)
        learned_raw = self.conflict_head(combined).squeeze(-1)
        learned_adj = torch.sigmoid(learned_raw).item() - 0.5

        # Combine: cosine distance + learned shift, clamped to [0, 1]
        conflict_level = max(0.0, min(1.0, distance + learned_adj))

        # === THRESHOLD MODULATION ===
        if modulation is not None:
            effective_threshold = self.conflict_threshold * modulation.threshold_mod
        else:
            # Legacy per-hook path (backward compat)
            # Hook 6: NE explore_ratio modulates threshold
            if neuromod is not None:
                effective_threshold = self.conflict_threshold * (1.5 - neuromod.explore_ratio)
            else:
                effective_threshold = self.conflict_threshold

            # Hook 8: ACC conflict reduces threshold
            if cortex_state is not None:
                effective_threshold *= (1.0 - 0.3 * cortex_state.conflict)

            # Hook 12: NoGo drive lowers threshold
            if limbic_state is not None:
                effective_threshold *= (1.0 - 0.2 * limbic_state.nogo_drive)

        if conflict_level < effective_threshold:
            return {
                'output': system1_output,
                'system_used': 1,
                'conflict_level': conflict_level,
            }
        else:
            return {
                'output': system2_output,
                'system_used': 2,
                'conflict_level': conflict_level,
            }
