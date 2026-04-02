"""
Sleep training for RadialAttentionNetwork.

Runs during DreamMode -- full backprop on collected experiences.
4 losses: Predictive Coding + Trajectory Matching + Reward + EWC.

Prediction errors from RadialAttentionNetwork.forward() are .item() floats
(no gradients). We handle this by:
  - Using ring activations from the forward pass (which DO have gradients)
    to compute a differentiable predictive-coding proxy loss.
  - Trajectory matching and reward losses operate on live ring activations.
  - EWC penalty keeps weights near their anchor values.
"""
import logging
from typing import Dict, List, Optional

import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


class RadialSleepTrainer:
    """Train RadialAttentionNetwork on experience replay during sleep."""

    def __init__(self, network: nn.Module, buffer, lr: float = 0.001,
                 ewc_lambda: float = 100.0):
        self._network = network
        self._buffer = buffer
        self._optimizer = torch.optim.AdamW(network.parameters(), lr=lr)
        self._ewc_lambda = ewc_lambda
        self._ewc_anchor: Optional[Dict[str, torch.Tensor]] = None
        self._fisher: Optional[Dict[str, torch.Tensor]] = None
        self._total_epochs = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def train_epoch(self, batch_size: int = 32) -> float:
        """One training epoch on sampled experiences.

        Returns average loss.
        """
        if len(self._buffer) < batch_size:
            return 0.0

        self._network.train()
        batch = self._buffer.sample(batch_size)
        total_loss = 0.0

        for exp in batch:
            self._optimizer.zero_grad()

            # Forward pass (with gradients)
            seed = exp['input_embedding'].unsqueeze(0)
            result = self._network(seed)

            # Task loss (PC + trajectory + reward)
            task_loss = self._compute_task_loss(exp, result)

            # EWC regularization
            ewc_loss = self._compute_ewc_loss()

            # Combine
            loss = task_loss + self._ewc_lambda * ewc_loss

            if loss.requires_grad:
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    self._network.parameters(), 1.0
                )
                self._optimizer.step()

            total_loss += loss.item()

        self._total_epochs += 1
        avg_loss = total_loss / max(len(batch), 1)
        logger.info(
            "Sleep training epoch %d: avg_loss=%.4f",
            self._total_epochs, avg_loss,
        )
        return avg_loss

    def register_ewc_anchor(self) -> None:
        """Snapshot current weights as EWC anchor (after learning a task).

        Computes a diagonal Fisher Information approximation by sampling
        from the buffer and accumulating squared gradients from the actual
        task loss (PC + trajectory + reward — the same losses used in
        train_epoch), so the Fisher reflects true parameter importance.
        """
        self._ewc_anchor = {
            name: param.data.clone()
            for name, param in self._network.named_parameters()
        }
        self._fisher = {
            name: torch.zeros_like(param)
            for name, param in self._network.named_parameters()
        }

        # Approximate Fisher using the real task loss on buffer samples
        if len(self._buffer) > 0:
            self._network.train()
            batch = self._buffer.sample(min(32, len(self._buffer)))
            for exp in batch:
                self._optimizer.zero_grad()
                seed = exp['input_embedding'].unsqueeze(0)
                result = self._network(seed)
                task_loss = self._compute_task_loss(exp, result)
                if task_loss.requires_grad:
                    task_loss.backward()
                    for name, param in self._network.named_parameters():
                        if param.grad is not None:
                            self._fisher[name] += param.grad.data ** 2
            for name in self._fisher:
                self._fisher[name] /= max(len(batch), 1)

            # Normalize Fisher: scale so max across all params = 1.0.
            # At convergence, raw grad^2 is tiny. Without normalization
            # the EWC penalty is ~0 regardless of lambda. Normalizing
            # preserves relative importance while making lambda meaningful.
            max_fisher = max(
                (f.max().item() for f in self._fisher.values()),
                default=1.0,
            )
            if max_fisher > 0:
                for name in self._fisher:
                    self._fisher[name] /= max_fisher

        logger.info(
            "EWC anchor registered with %d parameter groups",
            len(self._ewc_anchor),
        )

    def get_stats(self) -> dict:
        """Return trainer statistics."""
        return {
            'total_epochs': self._total_epochs,
            'has_ewc_anchor': self._ewc_anchor is not None,
            'buffer_size': len(self._buffer),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _compute_task_loss(self, exp: dict, result: dict) -> torch.Tensor:
        """Compute the combined task loss (PC + trajectory + reward).

        Used by both train_epoch and register_ewc_anchor so Fisher
        reflects actual parameter importance.
        """
        # Loss 1: Predictive Coding proxy
        pc_loss = torch.tensor(0.0)
        ring_acts = result['ring_activations']
        if len(ring_acts) >= 2:
            for i in range(len(ring_acts) - 1):
                td_proj = self._network.top_down_projections[i]
                predicted_inner = td_proj(ring_acts[i + 1])
                pc_loss = pc_loss + nn.functional.mse_loss(
                    ring_acts[i], predicted_inner
                )

        # Loss 2: Trajectory matching
        traj = exp['ctm_trajectory']
        if len(traj) > 0 and len(ring_acts) > 0:
            ring_magnitudes = torch.stack([a.abs().mean() for a in ring_acts])
            target_len = len(ring_acts)
            padded_traj = list(traj)
            if len(padded_traj) < target_len:
                padded_traj = padded_traj + [padded_traj[-1]] * (
                    target_len - len(padded_traj)
                )
            traj_tensor = torch.tensor(
                padded_traj[:target_len], dtype=torch.float32
            )
            traj_loss = nn.functional.mse_loss(ring_magnitudes, traj_tensor)
        else:
            traj_loss = torch.tensor(0.0)

        # Loss 3: Reward signal
        reward = exp['kuro_reward']
        meta_magnitude = result['meta_output'].abs().mean()
        reward_loss = -reward * torch.log(meta_magnitude + 1e-8)

        return pc_loss + traj_loss + 0.1 * reward_loss

    def _compute_ewc_loss(self) -> torch.Tensor:
        """EWC loss: penalize deviation from anchor on important weights."""
        if self._ewc_anchor is None:
            return torch.tensor(0.0)

        loss = torch.tensor(0.0)
        for name, param in self._network.named_parameters():
            if name in self._ewc_anchor:
                fisher = self._fisher.get(name, torch.ones_like(param))
                loss = loss + (
                    fisher * (param - self._ewc_anchor[name]) ** 2
                ).sum()

        return loss
