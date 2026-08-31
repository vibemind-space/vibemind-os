"""
AGI Test Fixtures

Common fixtures for testing all 16 AGI components.
"""

import pytest
import torch
import numpy as np
from typing import Dict, Any


# ============================================================================
# Basic Dimension Fixtures
# ============================================================================

@pytest.fixture
def seed():
    """Random seed for reproducibility."""
    np.random.seed(42)
    torch.manual_seed(42)
    return 42


@pytest.fixture
def state_dim():
    """Standard state dimension."""
    return 32


@pytest.fixture
def action_dim():
    """Standard action dimension."""
    return 4


@pytest.fixture
def hidden_dim():
    """Reduced hidden dimension for fast testing."""
    return 64


@pytest.fixture
def feature_dim():
    """Feature dimension for encoders."""
    return 128


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_state(state_dim, seed):
    """Sample state observation as numpy array."""
    np.random.seed(seed)
    return np.random.randn(state_dim).astype(np.float32)


@pytest.fixture
def sample_state_tensor(sample_state):
    """Sample state as PyTorch tensor."""
    return torch.FloatTensor(sample_state)


@pytest.fixture
def sample_batch_states(state_dim, seed):
    """Batch of sample states."""
    np.random.seed(seed)
    return np.random.randn(16, state_dim).astype(np.float32)


@pytest.fixture
def sample_action(action_dim, seed):
    """Random valid action."""
    np.random.seed(seed)
    return np.random.randint(0, action_dim)


@pytest.fixture
def sample_reward():
    """Sample reward value."""
    return 1.0


@pytest.fixture
def sample_next_state(state_dim, seed):
    """Sample next state observation."""
    np.random.seed(seed + 1)  # Different seed for next state
    return np.random.randn(state_dim).astype(np.float32)


# ============================================================================
# Component Fixtures
# ============================================================================

@pytest.fixture
def policy_learner(state_dim, action_dim):
    """GradientPolicyLearner instance."""
    from core.gradient_policy_learner import GradientPolicyLearner
    return GradientPolicyLearner(state_dim=state_dim, action_dim=action_dim)


@pytest.fixture
def safety_layer(action_dim):
    """SafetyLayer instance."""
    from core.safety_layer import SafetyLayer
    return SafetyLayer(action_dim=action_dim)


@pytest.fixture
def replay_buffer():
    """PrioritizedReplayBuffer instance."""
    from core.prioritized_replay import PrioritizedReplayBuffer
    return PrioritizedReplayBuffer(capacity=1000)


@pytest.fixture
def mcts_planner(state_dim, action_dim):
    """MCTSPlanner instance."""
    from core.mcts_planner import MCTSPlanner
    return MCTSPlanner(state_dim=state_dim, action_dim=action_dim)


@pytest.fixture
def curiosity_module(state_dim, action_dim):
    """IntrinsicCuriosityModule instance."""
    from core.intrinsic_curiosity import IntrinsicCuriosityModule
    return IntrinsicCuriosityModule(state_dim=state_dim, action_dim=action_dim)


@pytest.fixture
def goal_generator(state_dim, action_dim, hidden_dim):
    """AutonomousGoalGenerator instance."""
    from core.autonomous_goal_generator import AutonomousGoalGenerator
    return AutonomousGoalGenerator(
        state_dim=state_dim,
        action_dim=action_dim,
        hidden_dim=hidden_dim
    )


@pytest.fixture
def theory_of_mind(state_dim, action_dim, hidden_dim):
    """TheoryOfMind instance."""
    from core.theory_of_mind import TheoryOfMind
    return TheoryOfMind(
        state_dim=state_dim,
        action_dim=action_dim,
        hidden_dim=hidden_dim
    )


@pytest.fixture
def explainer():
    """ExplanationGenerator instance."""
    from core.explanation_generator import create_explainer
    return create_explainer(
        feature_names=['f1', 'f2', 'f3', 'f4'],
        decision_space=[0, 1, 2, 3]
    )


@pytest.fixture
def verifier(state_dim, action_dim):
    """FormalVerifier instance (simplified)."""
    from core.formal_verifier import create_verifier
    return create_verifier(state_dim, action_dim)


@pytest.fixture
def ewc_regularizer():
    """EWCRegularizer instance."""
    from core.ewc_regularization import EWCRegularizer
    return EWCRegularizer()


@pytest.fixture
def sensorimotor(state_dim, action_dim, hidden_dim):
    """SensorimotorController instance."""
    from core.sensorimotor_models import create_sensorimotor_controller
    return create_sensorimotor_controller(
        state_dim=state_dim,
        action_dim=action_dim,
        hidden_dim=hidden_dim
    )


# ============================================================================
# Integration Fixtures
# ============================================================================

@pytest.fixture
def agi_controller(state_dim, action_dim, hidden_dim):
    """AGIMetaController instance."""
    from core.agi_meta_controller import create_agi_controller
    return create_agi_controller(
        state_dim=state_dim,
        action_dim=action_dim,
        hidden_dim=hidden_dim
    )


# ============================================================================
# Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_environment(state_dim, action_dim):
    """Simple mock environment."""
    class MockEnv:
        def __init__(self):
            self.state_dim = state_dim
            self.action_dim = action_dim

        def reset(self):
            return np.random.randn(state_dim).astype(np.float32), {}

        def step(self, action):
            next_state = np.random.randn(state_dim).astype(np.float32)
            reward = np.random.random()
            done = np.random.random() < 0.1
            truncated = False
            info = {}
            return next_state, reward, done, truncated, info

    return MockEnv()


@pytest.fixture
def simple_model(state_dim, action_dim, hidden_dim):
    """Simple neural network for testing."""
    return torch.nn.Sequential(
        torch.nn.Linear(state_dim, hidden_dim),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden_dim, action_dim)
    )


# ============================================================================
# Utility Functions
# ============================================================================

def assert_valid_action(action: int, action_dim: int):
    """Assert action is valid."""
    assert isinstance(action, int), f"Action must be int, got {type(action)}"
    assert 0 <= action < action_dim, f"Action {action} out of range [0, {action_dim})"


def assert_valid_probability(prob: float):
    """Assert value is a valid probability."""
    assert 0.0 <= prob <= 1.0, f"Probability {prob} not in [0, 1]"


def assert_valid_state(state: np.ndarray, expected_dim: int):
    """Assert state has expected dimension."""
    assert state.shape[-1] == expected_dim, f"State dim {state.shape[-1]} != {expected_dim}"
