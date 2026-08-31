"""
Environment Interface - AGI Phase 2

Provides bidirectional connection between the Brain and
real/simulated environments (Gymnasium, MuJoCo, etc.).

Key Features:
- Gymnasium/MuJoCo integration
- Sensory encoding pipeline
- Action decoding
- Multi-environment support
- Reward shaping
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

# Conditional imports
try:
    import gymnasium as gym
    HAS_GYMNASIUM = True
except ImportError:
    HAS_GYMNASIUM = False
    logger.warning("Gymnasium not installed. Install with: pip install gymnasium")

try:
    import mujoco
    HAS_MUJOCO = True
except ImportError:
    HAS_MUJOCO = False


@dataclass
class EnvironmentConfig:
    """Configuration for environment interface."""
    env_name: str = "CartPole-v1"
    max_episode_steps: int = 1000
    reward_scale: float = 1.0
    frame_skip: int = 1
    normalize_observations: bool = True
    normalize_rewards: bool = True
    clip_observations: float = 10.0
    clip_rewards: float = 10.0


@dataclass
class EnvironmentStats:
    """Statistics for environment interaction."""
    total_steps: int = 0
    total_episodes: int = 0
    total_reward: float = 0.0
    avg_episode_reward: float = 0.0
    avg_episode_length: float = 0.0
    success_rate: float = 0.0


class SensoryEncoder(ABC):
    """Abstract base class for encoding environment observations."""

    @abstractmethod
    def encode(self, observation: Any) -> np.ndarray:
        """Encode observation into brain-compatible format."""
        pass

    @abstractmethod
    def get_output_dim(self) -> int:
        """Get dimension of encoded output."""
        pass


class FlattenEncoder(SensoryEncoder):
    """Simple encoder that flattens observations."""

    def __init__(self, observation_space):
        if hasattr(observation_space, 'shape'):
            self.input_shape = observation_space.shape
            self.output_dim = int(np.prod(observation_space.shape))
        else:
            self.input_shape = (1,)
            self.output_dim = 1

    def encode(self, observation: Any) -> np.ndarray:
        if isinstance(observation, np.ndarray):
            return observation.flatten().astype(np.float32)
        return np.array([observation], dtype=np.float32)

    def get_output_dim(self) -> int:
        return self.output_dim


class ImageEncoder(SensoryEncoder):
    """Encoder for image observations (CNN-based)."""

    def __init__(
        self,
        observation_space,
        output_dim: int = 256,
        grayscale: bool = False
    ):
        self.input_shape = observation_space.shape
        self._output_dim = output_dim
        self.grayscale = grayscale

        # Will use neural network encoding when torch is available
        self._use_nn = False
        try:
            import torch
            import torch.nn as nn
            self._use_nn = True
            self._build_cnn()
        except ImportError:
            logger.warning("PyTorch not available, using simple image encoding")

    def _build_cnn(self):
        import torch.nn as nn
        channels = 1 if self.grayscale else self.input_shape[-1]
        self.cnn = nn.Sequential(
            nn.Conv2d(channels, 32, 8, stride=4),
            nn.ReLU(),
            nn.Conv2d(32, 64, 4, stride=2),
            nn.ReLU(),
            nn.Conv2d(64, 64, 3, stride=1),
            nn.ReLU(),
            nn.Flatten(),
            nn.Linear(64 * 7 * 7, self._output_dim),
            nn.ReLU()
        )

    def encode(self, observation: np.ndarray) -> np.ndarray:
        if self._use_nn:
            import torch
            # Convert to tensor and add batch dimension
            obs = observation.astype(np.float32) / 255.0
            if self.grayscale and obs.ndim == 3:
                obs = np.mean(obs, axis=-1, keepdims=True)
            obs = np.transpose(obs, (2, 0, 1))  # HWC -> CHW
            obs_t = torch.FloatTensor(obs).unsqueeze(0)
            with torch.no_grad():
                encoded = self.cnn(obs_t).squeeze(0).numpy()
            return encoded
        else:
            # Simple encoding: downsample and flatten
            small = observation[::4, ::4]
            if self.grayscale and small.ndim == 3:
                small = np.mean(small, axis=-1)
            return small.flatten().astype(np.float32) / 255.0

    def get_output_dim(self) -> int:
        return self._output_dim


class ActionDecoder(ABC):
    """Abstract base class for decoding brain actions to environment."""

    @abstractmethod
    def decode(self, brain_action: int) -> Any:
        """Decode brain action to environment action."""
        pass

    @abstractmethod
    def get_num_actions(self) -> int:
        """Get number of discrete actions."""
        pass


class DiscreteActionDecoder(ActionDecoder):
    """Decoder for discrete action spaces."""

    def __init__(self, action_space):
        self.n_actions = action_space.n

    def decode(self, brain_action: int) -> int:
        return brain_action % self.n_actions

    def get_num_actions(self) -> int:
        return self.n_actions


class ContinuousActionDecoder(ActionDecoder):
    """Decoder for continuous action spaces (discretized)."""

    def __init__(
        self,
        action_space,
        num_bins: int = 11
    ):
        self.action_dim = action_space.shape[0]
        self.num_bins = num_bins
        self.low = action_space.low
        self.high = action_space.high

        # Create discrete action space
        self.n_actions = num_bins ** self.action_dim

    def decode(self, brain_action: int) -> np.ndarray:
        """Convert discrete action to continuous action."""
        # Decode multi-dimensional discrete action
        actions = []
        remaining = brain_action
        for i in range(self.action_dim):
            bin_idx = remaining % self.num_bins
            remaining //= self.num_bins
            # Map bin to continuous value
            value = self.low[i] + (self.high[i] - self.low[i]) * bin_idx / (self.num_bins - 1)
            actions.append(value)
        return np.array(actions, dtype=np.float32)

    def get_num_actions(self) -> int:
        return self.n_actions


class EnvironmentInterface:
    """
    Bidirectional interface between Brain and environment.

    Handles observation encoding, action decoding, and reward shaping.
    """

    def __init__(
        self,
        config: Optional[EnvironmentConfig] = None,
        encoder: Optional[SensoryEncoder] = None,
        decoder: Optional[ActionDecoder] = None
    ):
        self.config = config or EnvironmentConfig()
        self._env = None
        self._encoder = encoder
        self._decoder = decoder

        # Statistics
        self.stats = EnvironmentStats()

        # Running statistics for normalization
        self._obs_mean = None
        self._obs_var = None
        self._reward_mean = 0.0
        self._reward_var = 1.0
        self._update_count = 0

        # Episode tracking
        self._current_episode_reward = 0.0
        self._current_episode_length = 0
        self._episode_rewards: List[float] = []

    def create(self, env_name: Optional[str] = None) -> 'EnvironmentInterface':
        """Create and initialize the environment."""
        if not HAS_GYMNASIUM:
            raise ImportError("Gymnasium is required. Install with: pip install gymnasium")

        env_name = env_name or self.config.env_name
        self._env = gym.make(env_name, max_episode_steps=self.config.max_episode_steps)

        # Create encoder if not provided
        if self._encoder is None:
            obs_space = self._env.observation_space
            if len(obs_space.shape) == 3:  # Image
                self._encoder = ImageEncoder(obs_space)
            else:
                self._encoder = FlattenEncoder(obs_space)

        # Create decoder if not provided
        if self._decoder is None:
            act_space = self._env.action_space
            if hasattr(act_space, 'n'):  # Discrete
                self._decoder = DiscreteActionDecoder(act_space)
            else:  # Continuous
                self._decoder = ContinuousActionDecoder(act_space)

        # Initialize normalization statistics
        self._obs_mean = np.zeros(self._encoder.get_output_dim())
        self._obs_var = np.ones(self._encoder.get_output_dim())

        logger.info(f"Environment created: {env_name}")
        logger.info(f"  Observation dim: {self._encoder.get_output_dim()}")
        logger.info(f"  Action dim: {self._decoder.get_num_actions()}")

        return self

    def reset(self) -> np.ndarray:
        """Reset environment and return initial observation."""
        if self._env is None:
            raise RuntimeError("Environment not created. Call create() first.")

        obs, info = self._env.reset()
        encoded_obs = self._encode_observation(obs)

        # Track episode
        if self._current_episode_length > 0:
            self._episode_rewards.append(self._current_episode_reward)
            self.stats.total_episodes += 1
            self.stats.avg_episode_reward = np.mean(self._episode_rewards[-100:])
            self.stats.avg_episode_length = self.stats.total_steps / max(self.stats.total_episodes, 1)

        self._current_episode_reward = 0.0
        self._current_episode_length = 0

        return encoded_obs

    def step(self, brain_action: int) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """
        Execute action in environment.

        Args:
            brain_action: Discrete action from brain

        Returns:
            observation: Encoded observation
            reward: Shaped reward
            terminated: Episode ended naturally
            truncated: Episode ended due to time limit
            info: Additional information
        """
        if self._env is None:
            raise RuntimeError("Environment not created. Call create() first.")

        # Decode action
        env_action = self._decoder.decode(brain_action)

        # Execute in environment (with frame skip)
        total_reward = 0.0
        for _ in range(self.config.frame_skip):
            obs, reward, terminated, truncated, info = self._env.step(env_action)
            total_reward += reward
            if terminated or truncated:
                break

        # Encode observation
        encoded_obs = self._encode_observation(obs)

        # Shape reward
        shaped_reward = self._shape_reward(total_reward)

        # Update statistics
        self.stats.total_steps += 1
        self.stats.total_reward += total_reward
        self._current_episode_reward += total_reward
        self._current_episode_length += 1

        return encoded_obs, shaped_reward, terminated, truncated, info

    def _encode_observation(self, obs: Any) -> np.ndarray:
        """Encode and normalize observation."""
        encoded = self._encoder.encode(obs)

        if self.config.normalize_observations:
            # Update running statistics
            self._update_count += 1
            delta = encoded - self._obs_mean
            self._obs_mean += delta / self._update_count
            self._obs_var += delta * (encoded - self._obs_mean)

            # Normalize
            std = np.sqrt(self._obs_var / max(self._update_count, 1) + 1e-8)
            encoded = (encoded - self._obs_mean) / std

            # Clip
            encoded = np.clip(encoded, -self.config.clip_observations, self.config.clip_observations)

        return encoded

    def _shape_reward(self, reward: float) -> float:
        """Apply reward shaping."""
        reward = reward * self.config.reward_scale

        if self.config.normalize_rewards:
            # Update running statistics
            delta = reward - self._reward_mean
            self._reward_mean += delta * 0.01
            self._reward_var = 0.99 * self._reward_var + 0.01 * delta * (reward - self._reward_mean)

            # Normalize
            std = np.sqrt(self._reward_var + 1e-8)
            reward = reward / std

            # Clip
            reward = np.clip(reward, -self.config.clip_rewards, self.config.clip_rewards)

        return reward

    def get_state_dim(self) -> int:
        """Get dimension of encoded state."""
        return self._encoder.get_output_dim()

    def get_action_dim(self) -> int:
        """Get number of discrete actions."""
        return self._decoder.get_num_actions()

    def render(self):
        """Render environment."""
        if self._env is not None:
            return self._env.render()

    def close(self):
        """Close environment."""
        if self._env is not None:
            self._env.close()
            self._env = None


class MultiEnvironmentManager:
    """
    Manages multiple environments for parallel experience collection.
    """

    def __init__(
        self,
        env_name: str,
        num_envs: int = 4,
        config: Optional[EnvironmentConfig] = None
    ):
        self.env_name = env_name
        self.num_envs = num_envs
        self.config = config or EnvironmentConfig(env_name=env_name)

        self.envs: List[EnvironmentInterface] = []
        self._create_envs()

    def _create_envs(self):
        """Create all environments."""
        for _ in range(self.num_envs):
            env = EnvironmentInterface(self.config).create(self.env_name)
            self.envs.append(env)

    def reset_all(self) -> np.ndarray:
        """Reset all environments."""
        observations = [env.reset() for env in self.envs]
        return np.stack(observations)

    def step_all(self, actions: List[int]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[Dict]]:
        """Step all environments with given actions."""
        results = [env.step(action) for env, action in zip(self.envs, actions)]

        obs = np.stack([r[0] for r in results])
        rewards = np.array([r[1] for r in results])
        terminated = np.array([r[2] for r in results])
        truncated = np.array([r[3] for r in results])
        infos = [r[4] for r in results]

        # Auto-reset terminated environments
        for i, (term, trunc) in enumerate(zip(terminated, truncated)):
            if term or trunc:
                obs[i] = self.envs[i].reset()

        return obs, rewards, terminated, truncated, infos

    def get_state_dim(self) -> int:
        return self.envs[0].get_state_dim()

    def get_action_dim(self) -> int:
        return self.envs[0].get_action_dim()

    def close_all(self):
        """Close all environments."""
        for env in self.envs:
            env.close()


class SimulatedEnvironment(EnvironmentInterface):
    """
    Simulated environment for testing without external dependencies.
    """

    def __init__(
        self,
        state_dim: int = 4,
        action_dim: int = 2,
        episode_length: int = 200
    ):
        super().__init__()
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.episode_length = episode_length

        self._state = None
        self._step_count = 0

    def create(self, env_name: Optional[str] = None) -> 'SimulatedEnvironment':
        """Initialize simulated environment."""
        self._encoder = FlattenEncoder(type('Space', (), {'shape': (self.state_dim,)})())
        self._decoder = DiscreteActionDecoder(type('Space', (), {'n': self.action_dim})())
        return self

    def reset(self) -> np.ndarray:
        """Reset simulated environment."""
        self._state = np.random.randn(self.state_dim).astype(np.float32)
        self._step_count = 0
        return self._state.copy()

    def step(self, brain_action: int) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """Step simulated environment."""
        # Simple dynamics: state changes based on action
        action_effect = np.zeros(self.state_dim)
        action_effect[brain_action % self.state_dim] = 0.1

        self._state = self._state + action_effect + 0.01 * np.random.randn(self.state_dim)
        self._step_count += 1

        # Simple reward: negative distance from origin
        reward = -np.linalg.norm(self._state)

        # Check termination
        terminated = np.linalg.norm(self._state) < 0.1
        truncated = self._step_count >= self.episode_length

        return self._state.copy(), reward, terminated, truncated, {}

    def get_state_dim(self) -> int:
        return self.state_dim

    def get_action_dim(self) -> int:
        return self.action_dim
