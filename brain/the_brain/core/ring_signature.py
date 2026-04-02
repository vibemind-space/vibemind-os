# core/ring_signature.py
"""
RingSignature — the per-thought radial fingerprint.

Each thought that passes through the 5-ring RadialAttentionNetwork
receives 5 interpretable signals:

  Ring 1 (Sensory)  → novelty:           How different is this from recent inputs?
  Ring 2 (Pattern)  → pattern_match:     Does this match known patterns (Hebbian bias)?
  Ring 3 (Semantic) → semantic_richness:  How much associative depth does this have?
  Ring 4 (Abstract) → goal_alignment:    Does this serve active goals/projects?
  Ring 5 (Meta)     → action_readiness:  Should the system act on this or keep thinking?

These signals modulate thought activation, routing, and Hebbian learning.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import torch
import torch.nn.functional as F


@dataclass
class RingSignature:
    """Per-thought fingerprint from radial network."""

    novelty: float = 0.0
    pattern_match: float = 0.0
    semantic_richness: float = 0.0
    goal_alignment: float = 0.0
    action_readiness: float = 0.0

    @property
    def activation_boost(self) -> float:
        """Weighted combination — how much to boost this thought's activation."""
        raw = (
            0.30 * self.novelty
            + 0.10 * (1.0 - self.pattern_match)
            + 0.20 * self.semantic_richness
            + 0.30 * self.goal_alignment
            + 0.10 * self.action_readiness
        )
        return max(0.0, min(1.0, raw))

    def should_act(self, threshold: float = 0.6) -> bool:
        """Meta ring says: stop thinking, start doing."""
        return self.action_readiness >= threshold

    def to_dict(self) -> Dict[str, Any]:
        return {
            'novelty': round(self.novelty, 4),
            'pattern_match': round(self.pattern_match, 4),
            'semantic_richness': round(self.semantic_richness, 4),
            'goal_alignment': round(self.goal_alignment, 4),
            'action_readiness': round(self.action_readiness, 4),
            'activation_boost': round(self.activation_boost, 4),
        }


def extract_ring_signature(
    ring_activations: List[torch.Tensor],
    prediction_errors: List[float],
    previous_sensory: Optional[torch.Tensor] = None,
) -> RingSignature:
    """Extract interpretable signals from raw ring activations.

    Args:
        ring_activations: 5 tensors from RadialAttentionNetwork.forward()
        prediction_errors: 4 scalar errors (ring pairs 1-2, 2-3, 3-4, 4-5)
        previous_sensory: Last Ring 1 activation for novelty comparison
    """
    # Ring 1 — Novelty: prediction error at the sensory level
    if prediction_errors:
        raw_error = abs(prediction_errors[0])
        novelty = float(2.0 / (1.0 + math.exp(-raw_error)) - 1.0)
    else:
        novelty = 0.0

    if previous_sensory is not None and ring_activations:
        with torch.no_grad():
            cos_sim = F.cosine_similarity(
                ring_activations[0].flatten().unsqueeze(0),
                previous_sensory.flatten().unsqueeze(0),
            ).item()
            novelty = max(novelty, (1.0 - cos_sim) / 2.0)

    # Ring 2 — Pattern Match: entropy-based (low entropy = strong pattern)
    pattern_match = 0.0
    if len(ring_activations) > 1:
        act = ring_activations[1].detach().flatten().abs()
        total = act.sum().item()
        if total > 1e-6:
            probs = act / total
            entropy = -(probs * (probs + 1e-8).log()).sum().item()
            max_entropy = math.log(len(act))
            pattern_match = max(0.0, min(1.0, 1.0 - (entropy / max_entropy))) if max_entropy > 0 else 0.0

    # Ring 3 — Semantic Richness: top-k activation concentration
    # After LayerNorm, var ≈ 1.0 always. Instead measure how much energy
    # is concentrated in the top-k dimensions (sparse = rich, uniform = shallow).
    semantic_richness = 0.0
    if len(ring_activations) > 2:
        act = ring_activations[2].detach().flatten().abs()
        k = max(1, len(act) // 8)  # top 12.5% of dimensions
        topk_vals, _ = act.topk(k)
        topk_energy = topk_vals.sum().item()
        total_energy = act.sum().item()
        if total_energy > 1e-6:
            concentration = topk_energy / total_energy
            # Uniform: top 12.5% holds 12.5% energy → ratio=1.0
            # Concentrated: top 12.5% holds 50%+ → ratio=4.0+
            # Normalize: ratio 1.0→0.0, ratio 3.0→1.0
            ratio = concentration / (k / len(act))
            semantic_richness = max(0.0, min(1.0, (ratio - 1.0) / 2.0))

    # Ring 4 — Goal Alignment: max activation magnitude relative to mean
    # After LayerNorm, mean≈0, var≈1. The MAX value varies per input.
    # High max = one dimension dominates = goal-directed focus
    # Low max = everything flat = no clear goal signal
    goal_alignment = 0.0
    if len(ring_activations) > 3:
        act = ring_activations[3].detach().flatten()
        max_abs = act.abs().max().item()
        # Untrained: max ≈ 2.5-4.0 for 256-dim normal (Gaussian extreme stats)
        # Use sigmoid centered at 3.0 (expected max for N(0,1) with 256 samples)
        goal_alignment = float(1.0 / (1.0 + math.exp(-(max_abs - 3.0) * 2.0)))

    # Ring 5 — Action Readiness: peak activation magnitude in meta ring
    # After LayerNorm, mean=0 and pos/neg are exactly balanced.
    # But max |activation| varies per input (2.3-3.7 for 128-dim).
    # Strong peak = meta ring "fires" for this thought = act on it.
    # Weak peak = diffuse response = keep thinking.
    action_readiness = 0.0
    if len(ring_activations) > 4:
        meta_act = ring_activations[4].detach().flatten()
        max_abs = meta_act.abs().max().item()
        # Empirical for 128-dim LayerNorm'd: max_abs ∈ [2.3, 3.7]
        # Sigmoid centered at 2.8 (median), steep slope
        action_readiness = float(1.0 / (1.0 + math.exp(-(max_abs - 2.8) * 3.0)))

    return RingSignature(
        novelty=novelty,
        pattern_match=pattern_match,
        semantic_richness=semantic_richness,
        goal_alignment=goal_alignment,
        action_readiness=action_readiness,
    )
