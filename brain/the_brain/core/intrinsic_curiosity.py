"""
Intrinsic Curiosity Module (ICM) - AGI Phase 3

Generates intrinsic rewards based on prediction error to drive
autonomous exploration and learning.

Key Features:
- Forward dynamics model (predicts next state)
- Inverse dynamics model (infers action from states)
- Random Network Distillation (RND) for novelty
- Empowerment-based motivation
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import deque
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class CuriosityMetrics:
    """Metrics for tracking curiosity-driven exploration."""
    total_intrinsic_reward: float = 0.0
    avg_prediction_error: float = 0.0
    novelty_score: float = 0.0
    exploration_bonus: float = 0.0
    visited_states: int = 0


class FeatureEncoder(nn.Module):
    """Encodes raw states into learned feature representations."""

    def __init__(
        self,
        input_dim: int,
        feature_dim: int = 256,
        hidden_dim: int = 128
    ):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, feature_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.encoder(x)


class ForwardDynamicsModel(nn.Module):
    """
    Predicts next state features given current state and action.

    High prediction error = novel/interesting situation = high intrinsic reward
    """

    def __init__(
        self,
        feature_dim: int,
        action_dim: int,
        hidden_dim: int = 256
    ):
        super().__init__()
        self.model = nn.Sequential(
            nn.Linear(feature_dim + action_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, feature_dim)
        )

    def forward(
        self,
        state_features: torch.Tensor,
        action: torch.Tensor
    ) -> torch.Tensor:
        """Predict next state features."""
        if action.dim() == 1:
            action = F.one_hot(action, num_classes=self.model[0].in_features - state_features.size(-1)).float()
        x = torch.cat([state_features, action], dim=-1)
        return self.model(x)


class InverseDynamicsModel(nn.Module):
    """
    Infers action from state transition.

    Helps learn state representations that capture action-relevant information.
    """

    def __init__(
        self,
        feature_dim: int,
        action_dim: int,
        hidden_dim: int = 256
    ):
        super().__init__()
        self.model = nn.Sequential(
            nn.Linear(feature_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_dim)
        )

    def forward(
        self,
        state_features: torch.Tensor,
        next_state_features: torch.Tensor
    ) -> torch.Tensor:
        """Predict action that caused state transition."""
        x = torch.cat([state_features, next_state_features], dim=-1)
        return self.model(x)


class IntrinsicCuriosityModule:
    """
    Intrinsic Curiosity Module for self-motivated exploration.

    Generates intrinsic rewards based on prediction error of forward model.
    The agent is rewarded for encountering states it cannot predict well.
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        feature_dim: int = 256,
        hidden_dim: int = 256,
        intrinsic_reward_scale: float = 0.01,
        forward_loss_coef: float = 0.2,
        inverse_loss_coef: float = 0.8,
        learning_rate: float = 1e-4,
        device: str = "cpu"
    ):
        """
        Initialize ICM.

        Args:
            state_dim: Dimension of state observations
            action_dim: Number of possible actions
            feature_dim: Dimension of learned features
            hidden_dim: Hidden layer dimension
            intrinsic_reward_scale: Scale factor for intrinsic rewards
            forward_loss_coef: Weight for forward model loss
            inverse_loss_coef: Weight for inverse model loss
            learning_rate: Learning rate for ICM networks
            device: Computation device
        """
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.feature_dim = feature_dim
        self.intrinsic_reward_scale = intrinsic_reward_scale
        self.forward_loss_coef = forward_loss_coef
        self.inverse_loss_coef = inverse_loss_coef
        self.device = torch.device(device)

        # Networks
        self.feature_encoder = FeatureEncoder(state_dim, feature_dim, hidden_dim).to(self.device)
        self.forward_model = ForwardDynamicsModel(feature_dim, action_dim, hidden_dim).to(self.device)
        self.inverse_model = InverseDynamicsModel(feature_dim, action_dim, hidden_dim).to(self.device)

        # Combined optimizer
        params = list(self.feature_encoder.parameters()) + \
                 list(self.forward_model.parameters()) + \
                 list(self.inverse_model.parameters())
        self.optimizer = torch.optim.Adam(params, lr=learning_rate)

        # Metrics
        self.metrics = CuriosityMetrics()
        self.prediction_errors: deque = deque(maxlen=1000)

    def compute_intrinsic_reward(
        self,
        state: np.ndarray,
        action: int,
        next_state: np.ndarray
    ) -> float:
        """
        Compute intrinsic reward based on prediction error.

        Args:
            state: Current state
            action: Action taken
            next_state: Resulting state

        Returns:
            Intrinsic reward (higher = more novel/interesting)
        """
        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        action_t = torch.LongTensor([action]).to(self.device)
        next_state_t = torch.FloatTensor(next_state).unsqueeze(0).to(self.device)

        with torch.no_grad():
            # Encode states
            state_features = self.feature_encoder(state_t)
            next_state_features = self.feature_encoder(next_state_t)

            # Predict next state features
            action_onehot = F.one_hot(action_t, self.action_dim).float()
            predicted_next_features = self.forward_model(state_features, action_onehot)

            # Prediction error = intrinsic reward
            prediction_error = F.mse_loss(predicted_next_features, next_state_features)
            intrinsic_reward = self.intrinsic_reward_scale * prediction_error.item()

        self.prediction_errors.append(prediction_error.item())
        self.metrics.total_intrinsic_reward += intrinsic_reward
        self.metrics.avg_prediction_error = np.mean(list(self.prediction_errors))

        return intrinsic_reward

    def update(
        self,
        states: torch.Tensor,
        actions: torch.Tensor,
        next_states: torch.Tensor
    ) -> Dict[str, float]:
        """
        Update ICM networks from batch of experiences.

        Args:
            states: Batch of states [B, state_dim]
            actions: Batch of actions [B]
            next_states: Batch of next states [B, state_dim]

        Returns:
            Dictionary of loss values
        """
        states = states.to(self.device)
        actions = actions.to(self.device)
        next_states = next_states.to(self.device)

        # Encode states
        state_features = self.feature_encoder(states)
        next_state_features = self.feature_encoder(next_states)

        # Forward model loss
        action_onehot = F.one_hot(actions, self.action_dim).float()
        predicted_next_features = self.forward_model(state_features, action_onehot)
        forward_loss = F.mse_loss(predicted_next_features, next_state_features.detach())

        # Inverse model loss
        predicted_actions = self.inverse_model(state_features, next_state_features)
        inverse_loss = F.cross_entropy(predicted_actions, actions)

        # Combined loss
        total_loss = self.forward_loss_coef * forward_loss + self.inverse_loss_coef * inverse_loss

        # Update
        self.optimizer.zero_grad()
        total_loss.backward()
        self.optimizer.step()

        return {
            "forward_loss": forward_loss.item(),
            "inverse_loss": inverse_loss.item(),
            "total_loss": total_loss.item()
        }

    def get_exploration_bonus(self, state: np.ndarray) -> float:
        """Get exploration bonus for a state (based on novelty)."""
        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        with torch.no_grad():
            features = self.feature_encoder(state_t)
            # Use feature norm as simple novelty proxy
            novelty = features.norm().item()
        return novelty * self.intrinsic_reward_scale


class RandomNetworkDistillation:
    """
    Random Network Distillation (RND) for novelty-based exploration.

    Uses prediction error of a randomly initialized target network
    as an exploration bonus. Novel states are harder to predict.
    """

    def __init__(
        self,
        state_dim: int,
        feature_dim: int = 256,
        hidden_dim: int = 256,
        learning_rate: float = 1e-4,
        device: str = "cpu"
    ):
        self.device = torch.device(device)

        # Target network (randomly initialized, never trained)
        self.target_network = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, feature_dim)
        ).to(self.device)

        # Freeze target network
        for param in self.target_network.parameters():
            param.requires_grad = False

        # Predictor network (trained to match target)
        self.predictor_network = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, feature_dim)
        ).to(self.device)

        self.optimizer = torch.optim.Adam(self.predictor_network.parameters(), lr=learning_rate)

        # Running statistics for normalization
        self.obs_mean = torch.zeros(state_dim).to(self.device)
        self.obs_std = torch.ones(state_dim).to(self.device)
        self.reward_mean = 0.0
        self.reward_std = 1.0
        self.update_count = 0

    def compute_intrinsic_reward(self, state: np.ndarray) -> float:
        """
        Compute intrinsic reward based on RND prediction error.

        Args:
            state: Current state observation

        Returns:
            Intrinsic reward (higher for novel states)
        """
        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)

        # Normalize observation
        state_normalized = (state_t - self.obs_mean) / (self.obs_std + 1e-8)

        with torch.no_grad():
            target_features = self.target_network(state_normalized)
            predicted_features = self.predictor_network(state_normalized)
            prediction_error = F.mse_loss(predicted_features, target_features)

        # Normalize reward
        intrinsic_reward = prediction_error.item()
        normalized_reward = (intrinsic_reward - self.reward_mean) / (self.reward_std + 1e-8)

        return max(normalized_reward, 0.0)

    def update(self, states: torch.Tensor) -> Dict[str, float]:
        """Update predictor network and running statistics."""
        states = states.to(self.device)

        # Update observation statistics
        batch_mean = states.mean(dim=0)
        batch_std = states.std(dim=0)
        self.update_count += 1
        alpha = 1.0 / self.update_count
        self.obs_mean = (1 - alpha) * self.obs_mean + alpha * batch_mean
        self.obs_std = (1 - alpha) * self.obs_std + alpha * batch_std

        # Normalize states
        states_normalized = (states - self.obs_mean) / (self.obs_std + 1e-8)

        # Compute loss
        with torch.no_grad():
            target_features = self.target_network(states_normalized)
        predicted_features = self.predictor_network(states_normalized)
        loss = F.mse_loss(predicted_features, target_features)

        # Update reward statistics
        with torch.no_grad():
            errors = (predicted_features - target_features).pow(2).mean(dim=-1)
            self.reward_mean = errors.mean().item()
            self.reward_std = errors.std().item() + 1e-8

        # Update predictor
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        return {"rnd_loss": loss.item()}


class EmpowermentModule:
    """
    Empowerment-based intrinsic motivation.

    Empowerment = channel capacity between actions and future states.
    The agent is motivated to reach states where its actions have
    maximum influence on the environment.
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dim: int = 256,
        planning_horizon: int = 5,
        learning_rate: float = 1e-4,
        device: str = "cpu"
    ):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.planning_horizon = planning_horizon
        self.device = torch.device(device)

        # Source distribution q(a|s) - action distribution
        self.source_network = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_dim),
            nn.Softmax(dim=-1)
        ).to(self.device)

        # Planning distribution p(a|s,s') - action from transition
        self.planning_network = nn.Sequential(
            nn.Linear(state_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_dim),
            nn.Softmax(dim=-1)
        ).to(self.device)

        # Dynamics model for n-step planning
        self.dynamics_model = nn.Sequential(
            nn.Linear(state_dim + action_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, state_dim)
        ).to(self.device)

        params = list(self.source_network.parameters()) + \
                 list(self.planning_network.parameters()) + \
                 list(self.dynamics_model.parameters())
        self.optimizer = torch.optim.Adam(params, lr=learning_rate)

    def compute_empowerment(self, state: np.ndarray) -> float:
        """
        Estimate empowerment at a given state.

        Empowerment ≈ I(a; s_{t+n} | s_t) = mutual information
        between actions and future states.
        """
        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)

        with torch.no_grad():
            # Sample actions from source
            action_probs = self.source_network(state_t)

            # Simulate n-step futures for each action
            empowerment = 0.0
            for a in range(self.action_dim):
                action_onehot = F.one_hot(torch.tensor([a]), self.action_dim).float().to(self.device)

                # Roll out dynamics
                current_state = state_t
                for _ in range(self.planning_horizon):
                    x = torch.cat([current_state, action_onehot], dim=-1)
                    current_state = self.dynamics_model(x)

                # Planning distribution
                combined = torch.cat([state_t, current_state], dim=-1)
                planning_probs = self.planning_network(combined)

                # Contribution to mutual information
                p_a = action_probs[0, a]
                q_a = planning_probs[0, a]
                if p_a > 0 and q_a > 0:
                    empowerment += p_a * torch.log(q_a / p_a + 1e-8)

        # Handle both tensor and float cases
        if hasattr(empowerment, 'item'):
            return -empowerment.item()
        return -float(empowerment)


class CuriosityDrivenAgent:
    """
    Agent that combines multiple curiosity mechanisms.

    Integrates ICM, RND, and Empowerment for comprehensive
    intrinsic motivation.
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        icm_weight: float = 0.5,
        rnd_weight: float = 0.3,
        empowerment_weight: float = 0.2,
        device: str = "cpu"
    ):
        self.icm = IntrinsicCuriosityModule(state_dim, action_dim, device=device)
        self.rnd = RandomNetworkDistillation(state_dim, device=device)
        self.empowerment = EmpowermentModule(state_dim, action_dim, device=device)

        self.icm_weight = icm_weight
        self.rnd_weight = rnd_weight
        self.empowerment_weight = empowerment_weight

    def compute_total_intrinsic_reward(
        self,
        state: np.ndarray,
        action: int,
        next_state: np.ndarray
    ) -> Tuple[float, Dict[str, float]]:
        """Compute combined intrinsic reward from all modules."""
        icm_reward = self.icm.compute_intrinsic_reward(state, action, next_state)
        rnd_reward = self.rnd.compute_intrinsic_reward(next_state)
        emp_reward = self.empowerment.compute_empowerment(state)

        total_reward = (
            self.icm_weight * icm_reward +
            self.rnd_weight * rnd_reward +
            self.empowerment_weight * emp_reward
        )

        return total_reward, {
            "icm": icm_reward,
            "rnd": rnd_reward,
            "empowerment": emp_reward,
            "total": total_reward
        }

    def update(
        self,
        state: np.ndarray,
        action: int,
        next_state: np.ndarray
    ) -> Dict[str, float]:
        """Update all curiosity modules from a transition."""
        state_t = torch.FloatTensor(state).unsqueeze(0)
        action_t = torch.LongTensor([action])
        next_state_t = torch.FloatTensor(next_state).unsqueeze(0)

        # Update ICM
        icm_metrics = self.icm.update(state_t, action_t, next_state_t)

        # Update RND
        rnd_metrics = self.rnd.update(next_state_t)

        return {**icm_metrics, **rnd_metrics}
