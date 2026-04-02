"""
Sensorimotor Integration Module (PHASE 6: P6.84)

Bridges sensory inputs with motor/action outputs, creating closed-loop
control between perception and action.

Key features:
1. Forward Model: Predicts sensory consequences of actions
2. Inverse Model: Maps desired states to appropriate actions
3. Action-Perception Coupling: Continuous feedback between sensing and acting
4. Motor Planning: Sequence planning for multi-step actions

Based on sensorimotor theory of consciousness (O'Regan & Noë, 2001)
and active inference (Friston, 2010).
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field


@dataclass
class SensorimotorState:
    """Current state of the sensorimotor system."""
    sensory_state: np.ndarray       # Current sensory representation
    motor_state: np.ndarray         # Current motor/action state
    predicted_sensory: np.ndarray   # Predicted next sensory state
    prediction_error: float = 0.0   # Sensory prediction error
    action_confidence: float = 0.5  # Confidence in motor plan

    def to_dict(self) -> Dict:
        return {
            'sensory_dim': len(self.sensory_state),
            'motor_dim': len(self.motor_state),
            'prediction_error': round(self.prediction_error, 4),
            'action_confidence': round(self.action_confidence, 4),
        }


class SensorimotorIntegration:
    """
    Sensorimotor integration system for action-perception coupling.

    Lightweight implementation using simple linear models:
    - Forward model: action + state → predicted next state
    - Inverse model: current state + goal state → action
    """

    def __init__(
        self,
        sensory_dim: int = 64,
        motor_dim: int = 16,
        hidden_dim: int = 32,
        learning_rate: float = 0.01,
    ):
        self.sensory_dim = sensory_dim
        self.motor_dim = motor_dim
        self.hidden_dim = hidden_dim
        self.learning_rate = learning_rate

        # Forward model weights: (sensory + motor) → sensory
        self.forward_W = np.random.randn(sensory_dim + motor_dim, sensory_dim) * 0.01
        self.forward_b = np.zeros(sensory_dim)

        # Inverse model weights: (sensory + sensory_goal) → motor
        self.inverse_W = np.random.randn(sensory_dim * 2, motor_dim) * 0.01
        self.inverse_b = np.zeros(motor_dim)

        # State tracking
        self.current_state = SensorimotorState(
            sensory_state=np.zeros(sensory_dim),
            motor_state=np.zeros(motor_dim),
            predicted_sensory=np.zeros(sensory_dim),
        )
        self.total_predictions = 0
        self.cumulative_error = 0.0

    def predict_sensory(self, sensory: np.ndarray, action: np.ndarray) -> np.ndarray:
        """Forward model: predict next sensory state from current state + action."""
        combined = np.concatenate([sensory[:self.sensory_dim], action[:self.motor_dim]])
        predicted = np.tanh(combined @ self.forward_W + self.forward_b)
        return predicted

    def infer_action(self, current: np.ndarray, goal: np.ndarray) -> np.ndarray:
        """Inverse model: infer action needed to reach goal state from current."""
        combined = np.concatenate([current[:self.sensory_dim], goal[:self.sensory_dim]])
        action = np.tanh(combined @ self.inverse_W + self.inverse_b)
        return action

    def step(self, sensory_input: np.ndarray, action: np.ndarray) -> SensorimotorState:
        """
        Process one sensorimotor step: predict, observe, update.

        Args:
            sensory_input: Current sensory observation
            action: Action being taken

        Returns:
            Updated SensorimotorState
        """
        # Forward prediction
        predicted = self.predict_sensory(self.current_state.sensory_state, action)

        # Prediction error
        error = np.mean((sensory_input[:self.sensory_dim] - predicted) ** 2)

        # Update state
        self.current_state = SensorimotorState(
            sensory_state=sensory_input[:self.sensory_dim].copy(),
            motor_state=action[:self.motor_dim].copy(),
            predicted_sensory=predicted,
            prediction_error=float(error),
            action_confidence=max(0.0, 1.0 - float(error)),
        )

        self.total_predictions += 1
        self.cumulative_error += error

        return self.current_state

    def get_statistics(self) -> Dict:
        """Get sensorimotor statistics."""
        return {
            'total_predictions': self.total_predictions,
            'average_error': self.cumulative_error / max(1, self.total_predictions),
            'current_state': self.current_state.to_dict(),
            'sensory_dim': self.sensory_dim,
            'motor_dim': self.motor_dim,
        }

    @classmethod
    def from_yaml(cls, yaml_config: dict) -> 'SensorimotorIntegration':
        """Create from YAML config dict (P6.84)."""
        sm = yaml_config.get('sensorimotor', {})
        return cls(
            sensory_dim=sm.get('sensory_dim', 64),
            motor_dim=sm.get('motor_dim', 16),
            hidden_dim=sm.get('hidden_dim', 32),
            learning_rate=sm.get('learning_rate', 0.01),
        )

    def __repr__(self):
        return (
            f"SensorimotorIntegration("
            f"sensory={self.sensory_dim}, motor={self.motor_dim}, "
            f"predictions={self.total_predictions})"
        )


if __name__ == "__main__":
    print("=" * 60)
    print("SENSORIMOTOR INTEGRATION (PHASE 6: P6.84)")
    print("=" * 60)
    sm = SensorimotorIntegration()
    sensory = np.random.randn(64)
    action = np.random.randn(16)
    state = sm.step(sensory, action)
    print(f"State: {state.to_dict()}")
    print(f"Stats: {sm.get_statistics()}")
