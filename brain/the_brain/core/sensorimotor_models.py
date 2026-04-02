"""
Sensorimotor Models - AGI Phase 2

Forward and Inverse models for sensorimotor control and prediction.
Enables embodied cognition and motor planning.

Key Features:
- Forward Model: Predicts consequences of actions
- Inverse Model: Infers actions from state transitions
- Motor Primitives: Basic movement building blocks
- Sensory Prediction: Anticipates sensory feedback
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import logging

logger = logging.getLogger(__name__)


class ModelType(Enum):
    """Types of sensorimotor models."""
    FORWARD = "forward"
    INVERSE = "inverse"
    COMBINED = "combined"


@dataclass
class PredictionError:
    """Prediction error from sensorimotor model."""
    predicted: np.ndarray
    actual: np.ndarray
    error: float
    feature_errors: np.ndarray
    timestamp: int = 0


@dataclass
class MotorCommand:
    """Motor command representation."""
    action: int
    force: float = 1.0
    duration: float = 1.0
    target_state: Optional[np.ndarray] = None


@dataclass
class SensorimotorStats:
    """Statistics for sensorimotor models."""
    forward_predictions: int = 0
    inverse_inferences: int = 0
    avg_forward_error: float = 0.0
    avg_inverse_accuracy: float = 0.0


class ForwardModel(nn.Module):
    """
    Forward Model: Predicts next state given current state and action.

    P(s_{t+1} | s_t, a_t)

    Used for:
    - Action planning (predict outcomes)
    - Surprise detection (prediction errors)
    - Model-based reinforcement learning
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dim: int = 256,
        num_layers: int = 2,
        use_residual: bool = True
    ):
        super().__init__()
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.use_residual = use_residual

        # Action embedding
        self.action_embed = nn.Embedding(action_dim, hidden_dim // 4)

        # State encoder
        self.state_encoder = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim)
        )

        # Combined processing
        combined_dim = hidden_dim + hidden_dim // 4
        layers = []
        for i in range(num_layers):
            in_dim = combined_dim if i == 0 else hidden_dim
            layers.extend([
                nn.Linear(in_dim, hidden_dim),
                nn.ReLU(),
                nn.LayerNorm(hidden_dim)
            ])
        self.processor = nn.Sequential(*layers)

        # Output heads
        self.state_predictor = nn.Linear(hidden_dim, state_dim)

        # Uncertainty estimation
        self.uncertainty_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, state_dim),
            nn.Softplus()
        )

    def forward(
        self,
        state: torch.Tensor,
        action: torch.Tensor,
        return_uncertainty: bool = False
    ) -> Union[torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]:
        """
        Predict next state.

        Args:
            state: Current state [batch, state_dim]
            action: Action taken [batch] (indices)
            return_uncertainty: Whether to return uncertainty estimate

        Returns:
            predicted_state: Predicted next state
            uncertainty: Optional uncertainty estimate
        """
        # Encode state and action
        state_features = self.state_encoder(state)
        action_features = self.action_embed(action)

        # Combine
        combined = torch.cat([state_features, action_features], dim=-1)

        # Process
        features = self.processor(combined)

        # Predict state change
        state_delta = self.state_predictor(features)

        # Residual connection: predict change rather than absolute state
        if self.use_residual:
            predicted_state = state + state_delta
        else:
            predicted_state = state_delta

        if return_uncertainty:
            uncertainty = self.uncertainty_head(features)
            return predicted_state, uncertainty
        return predicted_state

    def predict_trajectory(
        self,
        initial_state: torch.Tensor,
        action_sequence: torch.Tensor,
        return_uncertainty: bool = False
    ) -> Union[torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]:
        """
        Predict trajectory given action sequence.

        Args:
            initial_state: Starting state [batch, state_dim]
            action_sequence: Sequence of actions [batch, seq_len]

        Returns:
            trajectory: Predicted states [batch, seq_len+1, state_dim]
        """
        batch_size, seq_len = action_sequence.shape
        trajectory = [initial_state]
        uncertainties = []

        current_state = initial_state
        for t in range(seq_len):
            action = action_sequence[:, t]
            if return_uncertainty:
                next_state, unc = self.forward(current_state, action, return_uncertainty=True)
                uncertainties.append(unc)
            else:
                next_state = self.forward(current_state, action)
            trajectory.append(next_state)
            current_state = next_state

        trajectory = torch.stack(trajectory, dim=1)

        if return_uncertainty:
            uncertainties = torch.stack(uncertainties, dim=1)
            return trajectory, uncertainties
        return trajectory


class InverseModel(nn.Module):
    """
    Inverse Model: Infers action from state transition.

    P(a_t | s_t, s_{t+1})

    Used for:
    - Imitation learning
    - Action recognition
    - Motor planning
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dim: int = 256,
        num_layers: int = 2
    ):
        super().__init__()
        self.state_dim = state_dim
        self.action_dim = action_dim

        # State encoders
        self.current_encoder = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim)
        )
        self.next_encoder = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim)
        )

        # Difference processing
        self.difference_processor = nn.Sequential(
            nn.Linear(hidden_dim * 2 + state_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim)
        )

        # Action predictor
        layers = []
        for _ in range(num_layers - 1):
            layers.extend([
                nn.Linear(hidden_dim, hidden_dim),
                nn.ReLU(),
                nn.LayerNorm(hidden_dim)
            ])
        layers.append(nn.Linear(hidden_dim, action_dim))
        self.action_predictor = nn.Sequential(*layers)

    def forward(
        self,
        current_state: torch.Tensor,
        next_state: torch.Tensor,
        return_logits: bool = False
    ) -> Union[torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]:
        """
        Infer action from state transition.

        Args:
            current_state: State before action [batch, state_dim]
            next_state: State after action [batch, state_dim]
            return_logits: Return raw logits instead of probabilities

        Returns:
            action_probs: Probability distribution over actions
        """
        # Encode states
        current_features = self.current_encoder(current_state)
        next_features = self.next_encoder(next_state)

        # Compute difference
        state_diff = next_state - current_state

        # Combine all information
        combined = torch.cat([current_features, next_features, state_diff], dim=-1)
        features = self.difference_processor(combined)

        # Predict action
        action_logits = self.action_predictor(features)

        if return_logits:
            return action_logits
        return F.softmax(action_logits, dim=-1)

    def infer_action(
        self,
        current_state: torch.Tensor,
        next_state: torch.Tensor
    ) -> Tuple[int, float]:
        """
        Infer most likely action.

        Returns:
            action: Predicted action index
            confidence: Confidence in prediction
        """
        with torch.no_grad():
            probs = self.forward(current_state, next_state)
            action = torch.argmax(probs, dim=-1).item()
            confidence = probs[0, action].item()
        return action, confidence


class CombinedSensorimotorModel(nn.Module):
    """
    Combined forward-inverse model with shared representations.

    Benefits:
    - Shared feature learning
    - Consistency between predictions
    - More efficient training
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dim: int = 256,
        latent_dim: int = 64
    ):
        super().__init__()
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.latent_dim = latent_dim

        # Shared state encoder
        self.state_encoder = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, latent_dim)
        )

        # Action embedding
        self.action_embed = nn.Embedding(action_dim, latent_dim)

        # Forward model: z_t + a_t → z_{t+1}
        self.forward_dynamics = nn.Sequential(
            nn.Linear(latent_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, latent_dim)
        )

        # Inverse model: z_t + z_{t+1} → a_t
        self.inverse_dynamics = nn.Sequential(
            nn.Linear(latent_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_dim)
        )

        # State decoder
        self.state_decoder = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, state_dim)
        )

    def encode_state(self, state: torch.Tensor) -> torch.Tensor:
        """Encode state to latent space."""
        return self.state_encoder(state)

    def decode_state(self, latent: torch.Tensor) -> torch.Tensor:
        """Decode latent to state space."""
        return self.state_decoder(latent)

    def forward_predict(
        self,
        state: torch.Tensor,
        action: torch.Tensor
    ) -> torch.Tensor:
        """Forward model prediction."""
        z_t = self.encode_state(state)
        a_emb = self.action_embed(action)
        z_next = self.forward_dynamics(torch.cat([z_t, a_emb], dim=-1))
        return self.decode_state(z_next)

    def inverse_predict(
        self,
        current_state: torch.Tensor,
        next_state: torch.Tensor
    ) -> torch.Tensor:
        """Inverse model prediction."""
        z_t = self.encode_state(current_state)
        z_next = self.encode_state(next_state)
        action_logits = self.inverse_dynamics(torch.cat([z_t, z_next], dim=-1))
        return F.softmax(action_logits, dim=-1)


class MotorPrimitive:
    """
    Motor primitive - basic building block for complex movements.

    Primitives can be combined and sequenced for complex behaviors.
    """

    def __init__(
        self,
        name: str,
        action_sequence: List[int],
        duration: float = 1.0,
        parameters: Optional[Dict[str, float]] = None
    ):
        self.name = name
        self.action_sequence = action_sequence
        self.duration = duration
        self.parameters = parameters or {}

    def execute(
        self,
        scale: float = 1.0
    ) -> List[MotorCommand]:
        """Generate motor commands for this primitive."""
        commands = []
        step_duration = self.duration / len(self.action_sequence)

        for action in self.action_sequence:
            commands.append(MotorCommand(
                action=action,
                force=scale,
                duration=step_duration
            ))

        return commands


class MotorPrimitiveLibrary:
    """Library of learned motor primitives."""

    def __init__(self, action_dim: int):
        self.action_dim = action_dim
        self.primitives: Dict[str, MotorPrimitive] = {}

        # Initialize basic primitives
        self._init_basic_primitives()

    def _init_basic_primitives(self):
        """Initialize basic motor primitives."""
        # Single actions as primitives
        for i in range(self.action_dim):
            self.primitives[f"action_{i}"] = MotorPrimitive(
                name=f"action_{i}",
                action_sequence=[i],
                duration=1.0
            )

    def add_primitive(self, primitive: MotorPrimitive):
        """Add a new primitive to the library."""
        self.primitives[primitive.name] = primitive

    def learn_primitive_from_trajectory(
        self,
        name: str,
        actions: List[int],
        states: Optional[List[np.ndarray]] = None
    ):
        """Learn a new primitive from observed trajectory."""
        primitive = MotorPrimitive(
            name=name,
            action_sequence=actions,
            duration=len(actions) * 1.0
        )
        self.add_primitive(primitive)

    def get_primitive(self, name: str) -> Optional[MotorPrimitive]:
        """Get primitive by name."""
        return self.primitives.get(name)

    def compose_primitives(
        self,
        primitive_names: List[str],
        name: str
    ) -> Optional[MotorPrimitive]:
        """Compose multiple primitives into a new one."""
        actions = []
        total_duration = 0.0

        for prim_name in primitive_names:
            prim = self.get_primitive(prim_name)
            if prim is None:
                return None
            actions.extend(prim.action_sequence)
            total_duration += prim.duration

        composed = MotorPrimitive(
            name=name,
            action_sequence=actions,
            duration=total_duration
        )
        self.add_primitive(composed)
        return composed


class SensoryPredictor:
    """
    Predicts sensory consequences of actions.

    Implements predictive coding for sensorimotor control.
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dim: int = 128,
        device: str = "cpu"
    ):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.device = torch.device(device)

        # Sensory prediction model
        self.model = nn.Sequential(
            nn.Linear(state_dim + action_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, state_dim)
        ).to(self.device)

        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-3)

        # Prediction error history
        self.error_history: deque = deque(maxlen=1000)

    def predict_sensory(
        self,
        state: np.ndarray,
        action: int
    ) -> np.ndarray:
        """Predict sensory feedback for action."""
        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        action_onehot = torch.zeros(1, self.action_dim).to(self.device)
        action_onehot[0, action] = 1.0

        with torch.no_grad():
            input_tensor = torch.cat([state_t, action_onehot], dim=-1)
            prediction = self.model(input_tensor)

        return prediction.squeeze(0).cpu().numpy()

    def update(
        self,
        state: np.ndarray,
        action: int,
        actual_next_state: np.ndarray
    ) -> float:
        """Update model with actual sensory feedback."""
        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        action_onehot = torch.zeros(1, self.action_dim).to(self.device)
        action_onehot[0, action] = 1.0
        target = torch.FloatTensor(actual_next_state).unsqueeze(0).to(self.device)

        input_tensor = torch.cat([state_t, action_onehot], dim=-1)
        prediction = self.model(input_tensor)

        loss = F.mse_loss(prediction, target)

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        error = loss.item()
        self.error_history.append(error)

        return error

    def get_prediction_error(
        self,
        state: np.ndarray,
        action: int,
        actual_next_state: np.ndarray
    ) -> PredictionError:
        """Compute detailed prediction error."""
        predicted = self.predict_sensory(state, action)
        error = np.mean((predicted - actual_next_state) ** 2)
        feature_errors = (predicted - actual_next_state) ** 2

        return PredictionError(
            predicted=predicted,
            actual=actual_next_state,
            error=float(error),
            feature_errors=feature_errors
        )


class SensorimotorController:
    """
    High-level sensorimotor controller combining forward and inverse models.

    Provides motor planning and execution capabilities.
    """

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dim: int = 256,
        learning_rate: float = 1e-4,
        device: str = "cpu"
    ):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.device = torch.device(device)

        # Models
        self.forward_model = ForwardModel(
            state_dim, action_dim, hidden_dim
        ).to(self.device)
        self.inverse_model = InverseModel(
            state_dim, action_dim, hidden_dim
        ).to(self.device)

        # Optimizers
        self.forward_optimizer = torch.optim.Adam(
            self.forward_model.parameters(), lr=learning_rate
        )
        self.inverse_optimizer = torch.optim.Adam(
            self.inverse_model.parameters(), lr=learning_rate
        )

        # Motor primitives
        self.primitives = MotorPrimitiveLibrary(action_dim)

        # Sensory predictor
        self.sensory_predictor = SensoryPredictor(
            state_dim, action_dim, device=device
        )

        # Statistics
        self.stats = SensorimotorStats()

        # Experience buffer for training
        self.experience_buffer: deque = deque(maxlen=10000)

    def predict_next_state(
        self,
        state: np.ndarray,
        action: int,
        return_uncertainty: bool = False
    ) -> Union[np.ndarray, Tuple[np.ndarray, np.ndarray]]:
        """
        Predict next state using forward model.

        Args:
            state: Current state
            action: Action to take
            return_uncertainty: Whether to return uncertainty

        Returns:
            Predicted next state (and uncertainty if requested)
        """
        state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        action_t = torch.LongTensor([action]).to(self.device)

        with torch.no_grad():
            if return_uncertainty:
                pred, unc = self.forward_model(state_t, action_t, return_uncertainty=True)
                return pred.squeeze(0).cpu().numpy(), unc.squeeze(0).cpu().numpy()
            else:
                pred = self.forward_model(state_t, action_t)
                return pred.squeeze(0).cpu().numpy()

        self.stats.forward_predictions += 1

    def infer_action(
        self,
        current_state: np.ndarray,
        target_state: np.ndarray
    ) -> Tuple[int, float]:
        """
        Infer action to transition from current to target state.

        Args:
            current_state: Current state
            target_state: Desired next state

        Returns:
            action: Inferred action
            confidence: Confidence in inference
        """
        current_t = torch.FloatTensor(current_state).unsqueeze(0).to(self.device)
        target_t = torch.FloatTensor(target_state).unsqueeze(0).to(self.device)

        action, confidence = self.inverse_model.infer_action(current_t, target_t)

        self.stats.inverse_inferences += 1
        return action, confidence

    def plan_action_sequence(
        self,
        current_state: np.ndarray,
        goal_state: np.ndarray,
        max_steps: int = 10
    ) -> List[int]:
        """
        Plan action sequence to reach goal state.

        Uses inverse model iteratively.

        Args:
            current_state: Starting state
            goal_state: Target state
            max_steps: Maximum steps to plan

        Returns:
            Action sequence
        """
        actions = []
        state = current_state.copy()

        for _ in range(max_steps):
            # Check if close to goal
            distance = np.linalg.norm(state - goal_state)
            if distance < 0.1:
                break

            # Infer action towards goal
            action, confidence = self.infer_action(state, goal_state)

            if confidence < 0.3:
                # Low confidence, try different approach
                # Use forward model to find best action
                action = self._search_best_action(state, goal_state)

            actions.append(action)

            # Simulate forward
            state = self.predict_next_state(state, action)

        return actions

    def _search_best_action(
        self,
        state: np.ndarray,
        goal_state: np.ndarray
    ) -> int:
        """Search for action that minimizes distance to goal."""
        best_action = 0
        best_distance = float('inf')

        for action in range(self.action_dim):
            pred_state = self.predict_next_state(state, action)
            distance = np.linalg.norm(pred_state - goal_state)

            if distance < best_distance:
                best_distance = distance
                best_action = action

        return best_action

    def store_experience(
        self,
        state: np.ndarray,
        action: int,
        next_state: np.ndarray
    ):
        """Store experience for training."""
        self.experience_buffer.append((state, action, next_state))

    def train_step(self, batch_size: int = 32) -> Dict[str, float]:
        """
        Train models on stored experiences.

        Returns:
            Training losses
        """
        if len(self.experience_buffer) < batch_size:
            return {}

        # Sample batch
        indices = np.random.choice(len(self.experience_buffer), batch_size, replace=False)
        batch = [self.experience_buffer[i] for i in indices]

        states = torch.FloatTensor([exp[0] for exp in batch]).to(self.device)
        actions = torch.LongTensor([exp[1] for exp in batch]).to(self.device)
        next_states = torch.FloatTensor([exp[2] for exp in batch]).to(self.device)

        # Train forward model
        pred_next = self.forward_model(states, actions)
        forward_loss = F.mse_loss(pred_next, next_states)

        self.forward_optimizer.zero_grad()
        forward_loss.backward()
        self.forward_optimizer.step()

        # Train inverse model
        action_probs = self.inverse_model(states, next_states)
        inverse_loss = F.cross_entropy(action_probs, actions)

        self.inverse_optimizer.zero_grad()
        inverse_loss.backward()
        self.inverse_optimizer.step()

        # Update stats
        self.stats.avg_forward_error = (
            0.9 * self.stats.avg_forward_error + 0.1 * forward_loss.item()
        )

        # Compute inverse accuracy
        pred_actions = torch.argmax(action_probs, dim=-1)
        accuracy = (pred_actions == actions).float().mean().item()
        self.stats.avg_inverse_accuracy = (
            0.9 * self.stats.avg_inverse_accuracy + 0.1 * accuracy
        )

        return {
            'forward_loss': forward_loss.item(),
            'inverse_loss': inverse_loss.item(),
            'inverse_accuracy': accuracy
        }

    def get_prediction_error(
        self,
        state: np.ndarray,
        action: int,
        actual_next_state: np.ndarray
    ) -> float:
        """
        Compute prediction error for intrinsic motivation.

        High error indicates surprising/interesting experience.
        """
        predicted = self.predict_next_state(state, action)
        return float(np.mean((predicted - actual_next_state) ** 2))

    def execute_primitive(
        self,
        primitive_name: str,
        current_state: np.ndarray,
        scale: float = 1.0
    ) -> Tuple[List[int], np.ndarray]:
        """
        Execute a motor primitive and predict outcome.

        Args:
            primitive_name: Name of primitive to execute
            current_state: Current state
            scale: Scaling factor for force

        Returns:
            actions: Action sequence
            final_state: Predicted final state
        """
        primitive = self.primitives.get_primitive(primitive_name)
        if primitive is None:
            return [], current_state

        commands = primitive.execute(scale)
        actions = [cmd.action for cmd in commands]

        # Predict trajectory
        state = current_state.copy()
        for action in actions:
            state = self.predict_next_state(state, action)

        return actions, state


def create_sensorimotor_controller(
    state_dim: int,
    action_dim: int,
    hidden_dim: int = 256,
    device: str = "cpu"
) -> SensorimotorController:
    """
    Factory function to create a sensorimotor controller.

    Args:
        state_dim: State dimension
        action_dim: Action dimension
        hidden_dim: Hidden layer dimension
        device: Device to use

    Returns:
        Configured SensorimotorController
    """
    return SensorimotorController(
        state_dim=state_dim,
        action_dim=action_dim,
        hidden_dim=hidden_dim,
        device=device
    )
