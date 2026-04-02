"""
Gradient Policy Learner - AGI Phase 1

Replaces static routing matrices with learnable neural network policies
that can adapt in real-time from feedback.

Key Features:
- REINFORCE policy gradient
- PPO for stable updates
- Actor-Critic architecture
- Online learning from execution feedback
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import deque
import numpy as np
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class PolicyExperience:
    """Single experience tuple for policy learning."""
    state: torch.Tensor
    action: int
    reward: float
    next_state: Optional[torch.Tensor]
    done: bool
    log_prob: float
    value: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class PolicyStats:
    """Statistics for monitoring policy learning."""
    total_updates: int = 0
    avg_reward: float = 0.0
    avg_entropy: float = 0.0
    avg_loss: float = 0.0
    success_rate: float = 0.0


class PolicyNetwork(nn.Module):
    """Neural network for action selection policy."""

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dims: List[int] = [256, 128],
        dropout: float = 0.1
    ):
        super().__init__()
        self.state_dim = state_dim
        self.action_dim = action_dim

        # Build network layers
        layers = []
        prev_dim = state_dim
        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.ReLU(),
                nn.Dropout(dropout)
            ])
            prev_dim = hidden_dim

        self.shared = nn.Sequential(*layers)

        # Policy head (actor)
        self.policy_head = nn.Sequential(
            nn.Linear(prev_dim, action_dim),
            nn.Softmax(dim=-1)
        )

        # Value head (critic)
        self.value_head = nn.Linear(prev_dim, 1)

    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Forward pass returning action probabilities and state value."""
        features = self.shared(state)
        action_probs = self.policy_head(features)
        value = self.value_head(features)
        return action_probs, value.squeeze(-1)

    def get_action(self, state: torch.Tensor, deterministic: bool = False) -> Tuple[int, float, float]:
        """Sample action from policy."""
        action_probs, value = self.forward(state)
        dist = Categorical(action_probs)

        if deterministic:
            action = action_probs.argmax(dim=-1)
        else:
            action = dist.sample()

        log_prob = dist.log_prob(action)
        return action.item(), log_prob.item(), value.item()


class GradientPolicyLearner:
    """
    Learnable routing policy using policy gradients.

    Replaces static matrix-based routing with adaptive neural policies
    that learn from execution feedback.
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        learning_rate: float = 1e-4,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_epsilon: float = 0.2,
        entropy_coef: float = 0.01,
        value_coef: float = 0.5,
        max_grad_norm: float = 0.5,
        buffer_size: int = 2048,
        batch_size: int = 64,
        ppo_epochs: int = 4,
        device: str = "cpu"
    ):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_epsilon = clip_epsilon
        self.entropy_coef = entropy_coef
        self.value_coef = value_coef
        self.max_grad_norm = max_grad_norm
        self.buffer_size = buffer_size
        self.batch_size = batch_size
        self.ppo_epochs = ppo_epochs
        self.device = torch.device(device)

        # Initialize policy network
        self.policy = PolicyNetwork(state_dim, action_dim).to(self.device)
        self.optimizer = torch.optim.Adam(self.policy.parameters(), lr=learning_rate)

        # Experience buffer
        self.buffer: deque[PolicyExperience] = deque(maxlen=buffer_size)

        # Statistics
        self.stats = PolicyStats()
        self.reward_history: deque[float] = deque(maxlen=100)

    def select_action(
        self,
        state: np.ndarray,
        deterministic: bool = False
    ) -> Tuple[int, Dict[str, float]]:
        """
        Select action based on current policy.

        Args:
            state: Current state observation
            deterministic: If True, select argmax action

        Returns:
            action: Selected action index
            info: Dict with log_prob and value
        """
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)

        with torch.no_grad():
            action, log_prob, value = self.policy.get_action(state_tensor, deterministic)

        return action, {"log_prob": log_prob, "value": value}

    def store_experience(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: Optional[np.ndarray],
        done: bool,
        log_prob: float,
        value: float
    ):
        """Store experience in buffer."""
        exp = PolicyExperience(
            state=torch.FloatTensor(state),
            action=action,
            reward=reward,
            next_state=torch.FloatTensor(next_state) if next_state is not None else None,
            done=done,
            log_prob=log_prob,
            value=value
        )
        self.buffer.append(exp)
        self.reward_history.append(reward)

    def compute_gae(
        self,
        rewards: torch.Tensor,
        values: torch.Tensor,
        dones: torch.Tensor,
        next_value: float
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Compute Generalized Advantage Estimation (GAE).

        Returns:
            advantages: GAE advantages
            returns: Discounted returns
        """
        batch_size = len(rewards)
        advantages = torch.zeros(batch_size)
        returns = torch.zeros(batch_size)

        last_gae = 0
        last_return = next_value

        for t in reversed(range(batch_size)):
            if dones[t]:
                last_gae = 0
                last_return = 0

            delta = rewards[t] + self.gamma * last_return * (1 - dones[t].float()) - values[t]
            last_gae = delta + self.gamma * self.gae_lambda * (1 - dones[t].float()) * last_gae
            advantages[t] = last_gae

            last_return = rewards[t] + self.gamma * last_return * (1 - dones[t].float())
            returns[t] = last_return

        return advantages, returns

    def update(self) -> Dict[str, float]:
        """
        Update policy using PPO.

        Returns:
            metrics: Training metrics
        """
        if len(self.buffer) < self.batch_size:
            return {"status": "insufficient_data"}

        # Convert buffer to tensors
        experiences = list(self.buffer)
        states = torch.stack([e.state for e in experiences]).to(self.device)
        actions = torch.LongTensor([e.action for e in experiences]).to(self.device)
        rewards = torch.FloatTensor([e.reward for e in experiences]).to(self.device)
        dones = torch.BoolTensor([e.done for e in experiences]).to(self.device)
        old_log_probs = torch.FloatTensor([e.log_prob for e in experiences]).to(self.device)
        old_values = torch.FloatTensor([e.value for e in experiences]).to(self.device)

        # Compute GAE
        with torch.no_grad():
            if experiences[-1].next_state is not None:
                _, next_value = self.policy(experiences[-1].next_state.unsqueeze(0).to(self.device))
                next_value = next_value.item()
            else:
                next_value = 0.0

        advantages, returns = self.compute_gae(rewards, old_values, dones, next_value)
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        advantages = advantages.to(self.device)
        returns = returns.to(self.device)

        # PPO update
        total_loss = 0
        total_policy_loss = 0
        total_value_loss = 0
        total_entropy = 0

        for _ in range(self.ppo_epochs):
            # Mini-batch updates
            indices = torch.randperm(len(experiences))

            for start in range(0, len(experiences), self.batch_size):
                end = start + self.batch_size
                batch_indices = indices[start:end]

                batch_states = states[batch_indices]
                batch_actions = actions[batch_indices]
                batch_old_log_probs = old_log_probs[batch_indices]
                batch_advantages = advantages[batch_indices]
                batch_returns = returns[batch_indices]

                # Forward pass
                action_probs, values = self.policy(batch_states)
                dist = Categorical(action_probs)
                new_log_probs = dist.log_prob(batch_actions)
                entropy = dist.entropy().mean()

                # Policy loss (PPO clipped objective)
                ratio = torch.exp(new_log_probs - batch_old_log_probs)
                surr1 = ratio * batch_advantages
                surr2 = torch.clamp(ratio, 1 - self.clip_epsilon, 1 + self.clip_epsilon) * batch_advantages
                policy_loss = -torch.min(surr1, surr2).mean()

                # Value loss
                value_loss = F.mse_loss(values, batch_returns)

                # Total loss
                loss = policy_loss + self.value_coef * value_loss - self.entropy_coef * entropy

                # Backward pass
                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm)
                self.optimizer.step()

                total_loss += loss.item()
                total_policy_loss += policy_loss.item()
                total_value_loss += value_loss.item()
                total_entropy += entropy.item()

        # Clear buffer after update
        self.buffer.clear()

        # Update statistics
        num_batches = (self.ppo_epochs * len(experiences)) // self.batch_size
        self.stats.total_updates += 1
        self.stats.avg_loss = total_loss / max(num_batches, 1)
        self.stats.avg_entropy = total_entropy / max(num_batches, 1)
        self.stats.avg_reward = np.mean(list(self.reward_history)) if self.reward_history else 0.0

        return {
            "total_loss": total_loss / max(num_batches, 1),
            "policy_loss": total_policy_loss / max(num_batches, 1),
            "value_loss": total_value_loss / max(num_batches, 1),
            "entropy": total_entropy / max(num_batches, 1),
            "avg_reward": self.stats.avg_reward
        }

    def update_from_feedback(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        success: bool = True
    ) -> Dict[str, float]:
        """
        Simple online update from single feedback.

        Used for immediate feedback after action execution.
        """
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)

        # Get current policy output
        action_probs, value = self.policy(state_tensor)
        dist = Categorical(action_probs)
        log_prob = dist.log_prob(torch.tensor([action]).to(self.device))

        # REINFORCE update
        advantage = reward - value.detach()
        policy_loss = -log_prob * advantage
        entropy = dist.entropy()

        loss = policy_loss - self.entropy_coef * entropy

        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm)
        self.optimizer.step()

        # Update success rate
        if success:
            self.stats.success_rate = 0.99 * self.stats.success_rate + 0.01
        else:
            self.stats.success_rate = 0.99 * self.stats.success_rate

        return {
            "loss": loss.item(),
            "advantage": advantage.item(),
            "success_rate": self.stats.success_rate
        }

    def save(self, path: str):
        """Save policy checkpoint."""
        torch.save({
            "policy_state_dict": self.policy.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "stats": self.stats,
            "config": {
                "state_dim": self.state_dim,
                "action_dim": self.action_dim,
                "gamma": self.gamma,
                "gae_lambda": self.gae_lambda,
                "clip_epsilon": self.clip_epsilon
            }
        }, path)
        logger.info(f"Policy saved to {path}")

    def load(self, path: str):
        """Load policy checkpoint."""
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        self.policy.load_state_dict(checkpoint["policy_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        self.stats = checkpoint["stats"]
        logger.info(f"Policy loaded from {path}")

    def get_action_distribution(self, state: np.ndarray) -> Dict[int, float]:
        """Get full action probability distribution."""
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        with torch.no_grad():
            action_probs, _ = self.policy(state_tensor)
        return {i: p.item() for i, p in enumerate(action_probs[0])}


class RoutingPolicyAdapter:
    """
    Adapter to integrate GradientPolicyLearner with existing routing system.

    Wraps the policy learner to provide the same interface as the static
    routing matrices while enabling learning.
    """

    def __init__(
        self,
        num_modalities: int = 10,
        num_actions: int = 4,
        feature_dim: int = 128,
        device: str = "cpu"
    ):
        self.num_modalities = num_modalities
        self.num_actions = num_actions
        self.feature_dim = feature_dim

        # State: modality features + context
        state_dim = num_modalities * feature_dim + 64  # +64 for context

        self.policy_learner = GradientPolicyLearner(
            state_dim=state_dim,
            action_dim=num_actions,
            device=device
        )

        # Running state for context
        self.context = np.zeros(64)
        self.last_state = None
        self.last_action = None
        self.last_info = None

    def encode_state(self, modality_features: Dict[str, np.ndarray]) -> np.ndarray:
        """Encode modality features into state vector."""
        features = []
        for i in range(self.num_modalities):
            if str(i) in modality_features:
                features.append(modality_features[str(i)])
            else:
                features.append(np.zeros(self.feature_dim))
        features.append(self.context)
        return np.concatenate(features)

    def route(self, modality_features: Dict[str, np.ndarray]) -> int:
        """Route based on current policy."""
        state = self.encode_state(modality_features)
        action, info = self.policy_learner.select_action(state)

        self.last_state = state
        self.last_action = action
        self.last_info = info

        return action

    def feedback(self, reward: float, success: bool = True):
        """Provide feedback on last routing decision."""
        if self.last_state is not None:
            self.policy_learner.update_from_feedback(
                self.last_state,
                self.last_action,
                reward,
                success
            )

    def update_context(self, context: np.ndarray):
        """Update running context."""
        self.context = context[:64] if len(context) >= 64 else np.pad(context, (0, 64 - len(context)))
