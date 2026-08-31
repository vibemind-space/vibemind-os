"""
Theory of Mind Module - AGI Phase 4

Models beliefs, desires, and intentions of other agents.
Enables multi-agent reasoning and social intelligence.

Key Features:
- Belief-Desire-Intention (BDI) modeling
- Inverse reinforcement learning for goal inference
- Perspective taking
- Mental state prediction
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class MentalStateType(Enum):
    """Types of mental states."""
    BELIEF = "belief"
    DESIRE = "desire"
    INTENTION = "intention"
    EMOTION = "emotion"
    KNOWLEDGE = "knowledge"


@dataclass
class MentalState:
    """Representation of an agent's mental state."""
    state_type: MentalStateType
    content: Any
    confidence: float = 0.5
    source: str = "inferred"
    timestamp: int = 0


@dataclass
class AgentModel:
    """Model of another agent's mind."""
    agent_id: str
    beliefs: Dict[str, MentalState] = field(default_factory=dict)
    desires: Dict[str, MentalState] = field(default_factory=dict)
    intentions: Dict[str, MentalState] = field(default_factory=dict)
    observed_actions: List[Tuple[Any, int]] = field(default_factory=list)
    inferred_reward_function: Optional[np.ndarray] = None
    predicted_policy: Optional[np.ndarray] = None
    trust_level: float = 0.5
    last_update: int = 0


@dataclass
class ToMStats:
    """Statistics for Theory of Mind module."""
    total_inferences: int = 0
    successful_predictions: int = 0
    prediction_accuracy: float = 0.0
    avg_belief_confidence: float = 0.0


class BeliefNetwork(nn.Module):
    """Neural network for inferring agent beliefs from observations."""

    def __init__(
        self,
        observation_dim: int,
        belief_dim: int = 64,
        hidden_dim: int = 128
    ):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(observation_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU()
        )

        # Output belief distribution parameters
        self.belief_mean = nn.Linear(hidden_dim, belief_dim)
        self.belief_logvar = nn.Linear(hidden_dim, belief_dim)

    def forward(self, observation: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Infer belief distribution from observation."""
        features = self.encoder(observation)
        mean = self.belief_mean(features)
        logvar = self.belief_logvar(features)
        return mean, logvar

    def sample_belief(
        self,
        observation: torch.Tensor,
        deterministic: bool = False
    ) -> torch.Tensor:
        """Sample from belief distribution."""
        mean, logvar = self.forward(observation)
        if deterministic:
            return mean
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        return mean + eps * std


class GoalInferenceNetwork(nn.Module):
    """Network for inferring agent goals from observed behavior (Inverse RL)."""

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        goal_dim: int = 32,
        hidden_dim: int = 128
    ):
        super().__init__()
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.goal_dim = goal_dim

        # Trajectory encoder
        self.trajectory_encoder = nn.LSTM(
            state_dim + action_dim,
            hidden_dim,
            batch_first=True
        )

        # Goal inference head
        self.goal_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, goal_dim)
        )

        # Reward function approximator
        self.reward_net = nn.Sequential(
            nn.Linear(state_dim + action_dim + goal_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1)
        )

    def forward(
        self,
        states: torch.Tensor,
        actions: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Infer goal from trajectory.

        Args:
            states: [batch, seq_len, state_dim]
            actions: [batch, seq_len, action_dim]

        Returns:
            goals: Inferred goals
            rewards: Predicted rewards for trajectory
        """
        # Encode trajectory
        trajectory = torch.cat([states, actions], dim=-1)
        _, (h_n, _) = self.trajectory_encoder(trajectory)

        # Infer goal
        goal = self.goal_head(h_n.squeeze(0))

        # Predict rewards given inferred goal
        goal_expanded = goal.unsqueeze(1).expand(-1, states.size(1), -1)
        reward_input = torch.cat([states, actions, goal_expanded], dim=-1)
        rewards = self.reward_net(reward_input)

        return goal, rewards.squeeze(-1)


class ActionPredictor(nn.Module):
    """Predicts agent actions given inferred mental state."""

    def __init__(
        self,
        state_dim: int,
        belief_dim: int,
        goal_dim: int,
        action_dim: int,
        hidden_dim: int = 128
    ):
        super().__init__()
        input_dim = state_dim + belief_dim + goal_dim

        self.predictor = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_dim)
        )

    def forward(
        self,
        state: torch.Tensor,
        belief: torch.Tensor,
        goal: torch.Tensor
    ) -> torch.Tensor:
        """Predict action distribution."""
        x = torch.cat([state, belief, goal], dim=-1)
        logits = self.predictor(x)
        return F.softmax(logits, dim=-1)


class TheoryOfMind:
    """
    Theory of Mind module for understanding other agents.

    Models beliefs, desires, and intentions of other agents
    based on observed behavior.
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        belief_dim: int = 64,
        goal_dim: int = 32,
        hidden_dim: int = 128,
        learning_rate: float = 1e-4,
        device: str = "cpu"
    ):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.belief_dim = belief_dim
        self.goal_dim = goal_dim
        self.device = torch.device(device)

        # Agent models
        self.agent_models: Dict[str, AgentModel] = {}

        # Neural networks
        self.belief_net = BeliefNetwork(state_dim, belief_dim, hidden_dim).to(self.device)
        self.goal_net = GoalInferenceNetwork(state_dim, action_dim, goal_dim, hidden_dim).to(self.device)
        self.action_predictor = ActionPredictor(
            state_dim, belief_dim, goal_dim, action_dim, hidden_dim
        ).to(self.device)

        # Optimizers
        self.belief_optimizer = torch.optim.Adam(self.belief_net.parameters(), lr=learning_rate)
        self.goal_optimizer = torch.optim.Adam(self.goal_net.parameters(), lr=learning_rate)
        self.action_optimizer = torch.optim.Adam(self.action_predictor.parameters(), lr=learning_rate)

        # Statistics
        self.stats = ToMStats()
        self.timestamp = 0

    def observe_agent(
        self,
        agent_id: str,
        state: np.ndarray,
        action: int
    ):
        """
        Observe an agent's action in a state.

        Args:
            agent_id: Identifier for the agent
            state: State in which action was taken
            action: Action taken by agent
        """
        # Create model if new agent
        if agent_id not in self.agent_models:
            self.agent_models[agent_id] = AgentModel(agent_id=agent_id)

        model = self.agent_models[agent_id]
        model.observed_actions.append((state.copy(), action))
        model.last_update = self.timestamp
        self.timestamp += 1

        # Limit history
        if len(model.observed_actions) > 1000:
            model.observed_actions = model.observed_actions[-1000:]

    def infer_beliefs(self, agent_id: str) -> Dict[str, MentalState]:
        """
        Infer agent's beliefs from observations.

        Args:
            agent_id: Agent to model

        Returns:
            Dictionary of inferred beliefs
        """
        if agent_id not in self.agent_models:
            return {}

        model = self.agent_models[agent_id]

        if not model.observed_actions:
            return model.beliefs

        # Get recent observations
        recent_states = [obs[0] for obs in model.observed_actions[-10:]]
        states_tensor = torch.FloatTensor(np.array(recent_states)).to(self.device)

        with torch.no_grad():
            belief_mean, belief_logvar = self.belief_net(states_tensor)
            avg_belief = belief_mean.mean(dim=0)
            confidence = 1.0 / (1.0 + belief_logvar.mean().exp().item())

        # Update model beliefs
        model.beliefs["world_state"] = MentalState(
            state_type=MentalStateType.BELIEF,
            content=avg_belief.cpu().numpy(),
            confidence=confidence,
            timestamp=self.timestamp
        )

        self.stats.total_inferences += 1
        return model.beliefs

    def infer_goal(self, agent_id: str) -> Optional[np.ndarray]:
        """
        Infer agent's goal from observed trajectory.

        Uses inverse reinforcement learning approach.

        Args:
            agent_id: Agent to model

        Returns:
            Inferred goal vector
        """
        if agent_id not in self.agent_models:
            return None

        model = self.agent_models[agent_id]

        if len(model.observed_actions) < 5:
            return model.inferred_reward_function

        # Prepare trajectory
        states = np.array([obs[0] for obs in model.observed_actions[-50:]])
        actions = np.array([obs[1] for obs in model.observed_actions[-50:]])

        states_tensor = torch.FloatTensor(states).unsqueeze(0).to(self.device)
        actions_onehot = F.one_hot(
            torch.LongTensor(actions),
            self.action_dim
        ).float().unsqueeze(0).to(self.device)

        with torch.no_grad():
            goal, _ = self.goal_net(states_tensor, actions_onehot)
            goal = goal.squeeze(0).cpu().numpy()

        # Update model
        model.inferred_reward_function = goal
        model.desires["primary_goal"] = MentalState(
            state_type=MentalStateType.DESIRE,
            content=goal,
            confidence=min(len(model.observed_actions) / 100, 1.0),
            timestamp=self.timestamp
        )

        return goal

    def predict_action(
        self,
        agent_id: str,
        state: np.ndarray
    ) -> Tuple[np.ndarray, float]:
        """
        Predict what action an agent will take.

        Args:
            agent_id: Agent to predict
            state: Current state

        Returns:
            action_probs: Probability distribution over actions
            confidence: Confidence in prediction
        """
        if agent_id not in self.agent_models:
            # Uniform distribution for unknown agent
            return np.ones(self.action_dim) / self.action_dim, 0.0

        model = self.agent_models[agent_id]

        # Get inferred mental state
        beliefs = self.infer_beliefs(agent_id)
        goal = self.infer_goal(agent_id)

        if "world_state" not in beliefs or goal is None:
            return np.ones(self.action_dim) / self.action_dim, 0.0

        # Predict action
        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        belief_t = torch.FloatTensor(beliefs["world_state"].content).unsqueeze(0).to(self.device)
        goal_t = torch.FloatTensor(goal).unsqueeze(0).to(self.device)

        with torch.no_grad():
            action_probs = self.action_predictor(state_t, belief_t, goal_t)
            action_probs = action_probs.squeeze(0).cpu().numpy()

        # Confidence based on observation history
        confidence = min(len(model.observed_actions) / 50, 1.0) * beliefs["world_state"].confidence

        return action_probs, confidence

    def update_from_prediction(
        self,
        agent_id: str,
        predicted_probs: np.ndarray,
        actual_action: int
    ):
        """
        Update models based on prediction accuracy.

        Args:
            agent_id: Agent that was predicted
            predicted_probs: Predicted action probabilities
            actual_action: Action actually taken
        """
        # Track prediction accuracy
        predicted_action = np.argmax(predicted_probs)
        correct = predicted_action == actual_action

        self.stats.successful_predictions += int(correct)
        self.stats.prediction_accuracy = (
            self.stats.successful_predictions / max(self.stats.total_inferences, 1)
        )

        # Update trust level
        if agent_id in self.agent_models:
            model = self.agent_models[agent_id]
            if correct:
                model.trust_level = min(1.0, model.trust_level + 0.01)
            else:
                model.trust_level = max(0.0, model.trust_level - 0.02)

    def take_perspective(
        self,
        agent_id: str,
        state: np.ndarray
    ) -> Dict[str, Any]:
        """
        Take the perspective of another agent.

        Returns what the agent likely believes, desires, and intends.

        Args:
            agent_id: Agent whose perspective to take
            state: Current world state

        Returns:
            Dictionary with agent's perspective
        """
        beliefs = self.infer_beliefs(agent_id)
        goal = self.infer_goal(agent_id)
        action_probs, confidence = self.predict_action(agent_id, state)

        return {
            "beliefs": {k: v.content for k, v in beliefs.items()},
            "goal": goal,
            "likely_action": int(np.argmax(action_probs)),
            "action_probs": action_probs,
            "confidence": confidence
        }

    def simulate_interaction(
        self,
        my_action: int,
        their_id: str,
        state: np.ndarray
    ) -> Dict[str, Any]:
        """
        Simulate how another agent might respond to my action.

        Args:
            my_action: Action I'm considering
            their_id: Other agent's ID
            state: Current state

        Returns:
            Predicted response and outcomes
        """
        # Predict their current intention
        their_probs, conf = self.predict_action(their_id, state)

        # Simple simulation: assume my action affects state
        # In practice, would use world model
        hypothetical_next_state = state.copy()

        # Predict their response
        response_probs, _ = self.predict_action(their_id, hypothetical_next_state)

        return {
            "their_current_intention": int(np.argmax(their_probs)),
            "their_likely_response": int(np.argmax(response_probs)),
            "response_probs": response_probs,
            "simulation_confidence": conf
        }

    def get_social_context(self, state: np.ndarray) -> Dict[str, Any]:
        """
        Get social context including all modeled agents.

        Args:
            state: Current world state

        Returns:
            Summary of all agents' mental states
        """
        context = {}

        for agent_id, model in self.agent_models.items():
            perspective = self.take_perspective(agent_id, state)
            context[agent_id] = {
                "perspective": perspective,
                "trust_level": model.trust_level,
                "observations": len(model.observed_actions)
            }

        return context
