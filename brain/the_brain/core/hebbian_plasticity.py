# core/hebbian_plasticity.py
"""
Hebbian live plasticity for RadialAttentionNetwork.

Updates attention biases based on activation correlations.
No gradients -- runs on CPU in <1ms per update.
"Neurons that fire together, wire together."
"""
import logging
from typing import Optional

import torch

logger = logging.getLogger(__name__)


class HebbianAttentionUpdate:
    """Correlation-based Hebbian learning for RingLayer attention biases.

    Applied after every forward pass during waking state.
    Modifies ring.attention_bias in-place based on pre/post activation
    correlations (outer product), with anti-Hebbian decay and clamping.

    Args:
        learning_rate: Scaling factor for the Hebbian update term.
        decay: Anti-Hebbian decay rate applied each step (shrinks bias toward 0).
        clamp_range: Hard bounds on bias values to prevent runaway growth.
    """

    def __init__(self, learning_rate: float = 0.001, decay: float = 0.0001,
                 clamp_range: float = 2.0):
        self.lr = learning_rate
        self.decay = decay
        self.clamp_range = clamp_range
        self._total_updates = 0

    def update(self, ring, pre_activation: torch.Tensor,
               post_activation: torch.Tensor, neuromod=None) -> None:
        """Update ring's attention bias based on pre/post correlations.

        Computes the outer product of batch-averaged pre and post activations,
        adds it (scaled by learning_rate) to the attention bias, applies
        multiplicative decay, then clamps to [-clamp_range, clamp_range].

        Args:
            ring: RingLayer instance with attention_bias buffer (out_dim, out_dim).
            pre_activation: Activation before ring (batch, dim).
            post_activation: Activation after ring (batch, dim).
            neuromod: Optional NeuromodState. If provided, serotonin modulates decay.
        """
        with torch.no_grad():
            # Batch-average activations -> (dim,)
            pre_mean = pre_activation.mean(dim=0)
            post_mean = post_activation.mean(dim=0)

            bias = ring.attention_bias  # (out_dim, out_dim)
            bias_d = bias.shape[0]

            # Project both activations to bias dimension via interpolation
            # so the full outer product always fills the entire bias matrix.
            pre_proj = self._project_to_dim(pre_mean, bias_d)
            post_proj = self._project_to_dim(post_mean, bias_d)

            # Full outer product Hebbian update
            correlation = torch.outer(pre_proj, post_proj)
            bias.add_(correlation, alpha=self.lr)

            # Hook 5: 5-HT modulates decay (high 5-HT = slow decay = consolidation)
            if neuromod is not None:
                effective_decay = self.decay * (1.5 - neuromod.serotonin)  # [0.5x, 1.5x]
            else:
                effective_decay = self.decay

            # Anti-Hebbian decay: shrink all bias values toward zero
            bias.mul_(1.0 - effective_decay)

            # Hard clamp to prevent explosion
            bias.clamp_(-self.clamp_range, self.clamp_range)

            self._total_updates += 1

    def update_with_reward(self, ring, pre_activation: torch.Tensor,
                           post_activation: torch.Tensor,
                           reward: float = 0.0,
                           neuromod=None) -> None:
        """Reward-modulated Hebbian update.

        reward > 0: LTP — strengthen the pathway (larger lr)
        reward < 0: LTD — weaken the pathway (inverted update)
        reward = 0: baseline Hebbian (same as update())

        The reward scales the learning rate:
          effective_lr = base_lr * (1.0 + reward)
        So reward=0.9 -> 1.9x lr, reward=-0.5 -> 0.5x lr (inverted sign).
        """
        effective_lr = self.lr * (1.0 + reward)

        with torch.no_grad():
            pre_mean = pre_activation.mean(dim=0)
            post_mean = post_activation.mean(dim=0)

            bias = ring.attention_bias
            bias_d = bias.shape[0]

            # Project to bias dimension (same logic as update())
            pre_proj = self._project_to_dim(pre_mean, bias_d)
            post_proj = self._project_to_dim(post_mean, bias_d)

            # Hebbian outer product with reward-modulated learning rate
            delta = torch.outer(pre_proj, post_proj)
            bias.add_(delta * effective_lr)

            # Anti-Hebbian decay (reward doesn't affect decay)
            effective_decay = self.decay
            if neuromod is not None:
                serotonin = getattr(neuromod, 'serotonin', 0.5)
                effective_decay *= (0.5 + serotonin)
            bias.mul_(1.0 - effective_decay)

            # Clamp
            bias.clamp_(-self.clamp_range, self.clamp_range)
            self._total_updates += 1

    @staticmethod
    def _project_to_dim(vec: torch.Tensor, target_dim: int) -> torch.Tensor:
        """Project a 1-D vector to target_dim via interpolation.

        Same dim -> passthrough. Different dim -> linear interpolation.
        No learnable parameters, runs in <0.1ms.
        """
        if vec.shape[0] == target_dim:
            return vec
        # Reshape (D,) -> (1, 1, D) for F.interpolate, then back to (target_dim,)
        return torch.nn.functional.interpolate(
            vec.unsqueeze(0).unsqueeze(0),
            size=target_dim,
            mode='linear',
            align_corners=False,
        ).squeeze()

    def get_stats(self) -> dict:
        """Return update statistics.

        Returns:
            Dict with total_updates, learning_rate, decay.
        """
        return {
            'total_updates': self._total_updates,
            'learning_rate': self.lr,
            'decay': self.decay,
        }
