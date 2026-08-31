"""
Multi-Puzzle Environment Wrapper

Manages multiple puzzle layouts for multi-task training.
Supports two modes:
1. Sequential: Rotate through puzzles each episode
2. Parallel: Sample random puzzle each episode
"""

import torch
import numpy as np
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import random

from neurosymbolic.training.puzzle_env import PuzzleEnv
from neurosymbolic.symbolic.allis_rules import Action


class MultiPuzzleEnv:
    """
    Multi-Puzzle Environment Wrapper

    Manages multiple puzzle configurations for diverse training.

    Modes:
    - 'sequential': Rotate through puzzles in order (Episode N uses puzzle N % num_puzzles)
    - 'random': Sample random puzzle each episode
    - 'weighted': Sample puzzles with custom weights (harder puzzles less frequent)
    """

    def __init__(
        self,
        puzzle_files: List[str],
        max_steps: int = 200,
        reward_shaping: bool = True,
        mode: str = 'sequential',
        puzzle_weights: Optional[List[float]] = None
    ):
        """
        Initialize multi-puzzle environment

        Args:
            puzzle_files: List of paths to puzzle JSON files
            max_steps: Maximum steps per episode
            reward_shaping: Use shaped rewards
            mode: 'sequential', 'random', or 'weighted'
            puzzle_weights: Sampling weights for 'weighted' mode (must sum to 1.0)
        """
        self.puzzle_files = puzzle_files
        self.max_steps = max_steps
        self.reward_shaping = reward_shaping
        self.mode = mode
        self.puzzle_weights = puzzle_weights

        # Validate mode
        if mode not in ['sequential', 'random', 'weighted']:
            raise ValueError(f"Invalid mode: {mode}. Must be 'sequential', 'random', or 'weighted'")

        # Validate weights
        if mode == 'weighted':
            if puzzle_weights is None:
                raise ValueError("puzzle_weights required for 'weighted' mode")
            if len(puzzle_weights) != len(puzzle_files):
                raise ValueError(f"puzzle_weights length ({len(puzzle_weights)}) must match puzzle_files ({len(puzzle_files)})")
            if not np.isclose(sum(puzzle_weights), 1.0):
                raise ValueError(f"puzzle_weights must sum to 1.0, got {sum(puzzle_weights)}")

        # Create environments for each puzzle
        self.envs = []
        self.puzzle_names = []
        self.puzzle_emphasis = []

        for i, puzzle_file in enumerate(puzzle_files):
            env = PuzzleEnv(
                layout_file=puzzle_file,
                max_steps=max_steps,
                reward_shaping=reward_shaping
            )
            self.envs.append(env)

            # Extract puzzle metadata
            import json
            with open(puzzle_file, 'r') as f:
                data = json.load(f)
                self.puzzle_names.append(data.get('name', f'Puzzle {i+1}'))
                self.puzzle_emphasis.append(data.get('emphasis', []))

        # Current environment tracking
        self.current_env_idx = 0
        self.current_env = self.envs[0]
        self.episode_count = 0

        # Statistics
        self.puzzle_episode_counts = [0] * len(self.envs)
        self.puzzle_success_counts = [0] * len(self.envs)
        self.puzzle_total_rewards = [0.0] * len(self.envs)

        print(f"[MultiPuzzleEnv] Initialized with {len(self.envs)} puzzles:")
        for i, name in enumerate(self.puzzle_names):
            emphasis_str = ', '.join(self.puzzle_emphasis[i]) if self.puzzle_emphasis[i] else 'balanced'
            print(f"  {i+1}. {name} (emphasis: {emphasis_str})")
        print(f"  Mode: {mode}")
        if mode == 'weighted':
            print(f"  Weights: {puzzle_weights}")

    def _select_next_env(self) -> int:
        """Select next environment based on mode"""
        if self.mode == 'sequential':
            # Rotate through puzzles
            return self.episode_count % len(self.envs)

        elif self.mode == 'random':
            # Random uniform sampling
            return random.randint(0, len(self.envs) - 1)

        elif self.mode == 'weighted':
            # Weighted sampling
            return np.random.choice(len(self.envs), p=self.puzzle_weights)

    def reset(self) -> Tuple[torch.Tensor, List[Action]]:
        """
        Reset environment (may switch to new puzzle)

        Returns:
            Tuple of (state_tensor, valid_actions)
        """
        # Select environment for this episode
        self.current_env_idx = self._select_next_env()
        self.current_env = self.envs[self.current_env_idx]

        # Reset the selected environment
        state, valid_actions = self.current_env.reset()

        # Update statistics
        self.episode_count += 1
        self.puzzle_episode_counts[self.current_env_idx] += 1

        return state, valid_actions

    def step(self, action_idx: int) -> Tuple[torch.Tensor, float, bool, Dict]:
        """
        Execute action in current environment

        Args:
            action_idx: Index of action to execute

        Returns:
            Tuple of (next_state, reward, done, info)
        """
        next_state, reward, done, info = self.current_env.step(action_idx)

        # Add puzzle information to info
        info['puzzle_idx'] = self.current_env_idx
        info['puzzle_name'] = self.puzzle_names[self.current_env_idx]
        info['puzzle_emphasis'] = self.puzzle_emphasis[self.current_env_idx]

        # Update statistics on episode end
        if done:
            self.puzzle_total_rewards[self.current_env_idx] += info.get('episode_reward', 0.0)
            if info.get('success', False):
                self.puzzle_success_counts[self.current_env_idx] += 1

        return next_state, reward, done, info

    def _get_valid_actions(self) -> List[Action]:
        """Get valid actions from current environment"""
        return self.current_env._get_valid_actions()

    def _state_to_tensor(self) -> torch.Tensor:
        """Convert current state to tensor"""
        return self.current_env._state_to_tensor()

    def get_puzzle_name(self) -> str:
        """Get name of current puzzle"""
        return self.puzzle_names[self.current_env_idx]

    def get_puzzle_emphasis(self) -> List[str]:
        """Get emphasis modules for current puzzle"""
        return self.puzzle_emphasis[self.current_env_idx]

    def get_statistics(self) -> Dict:
        """
        Get training statistics for each puzzle

        Returns:
            Dict with per-puzzle statistics
        """
        stats = {
            'total_episodes': self.episode_count,
            'puzzles': []
        }

        for i in range(len(self.envs)):
            episodes = self.puzzle_episode_counts[i]
            successes = self.puzzle_success_counts[i]
            total_reward = self.puzzle_total_rewards[i]

            puzzle_stats = {
                'name': self.puzzle_names[i],
                'emphasis': self.puzzle_emphasis[i],
                'episodes': episodes,
                'successes': successes,
                'success_rate': successes / episodes if episodes > 0 else 0.0,
                'avg_reward': total_reward / episodes if episodes > 0 else 0.0,
                'frequency': episodes / self.episode_count if self.episode_count > 0 else 0.0
            }
            stats['puzzles'].append(puzzle_stats)

        return stats

    def print_statistics(self):
        """Print training statistics"""
        stats = self.get_statistics()

        print(f"\n{'='*80}")
        print(f"MULTI-PUZZLE STATISTICS (Total Episodes: {stats['total_episodes']})")
        print(f"{'='*80}")

        for puz in stats['puzzles']:
            emphasis_str = ', '.join(puz['emphasis']) if puz['emphasis'] else 'balanced'
            print(f"\n{puz['name']} ({emphasis_str}):")
            print(f"  Episodes:     {puz['episodes']:>6} ({puz['frequency']*100:>5.1f}%)")
            print(f"  Successes:    {puz['successes']:>6} ({puz['success_rate']*100:>5.1f}%)")
            print(f"  Avg Reward:   {puz['avg_reward']:>6.2f}")

        print(f"{'='*80}\n")

    @property
    def num_puzzles(self) -> int:
        """Number of puzzles in the environment"""
        return len(self.envs)


# Test code
if __name__ == "__main__":
    print("Testing MultiPuzzleEnv...")

    # Find puzzle files
    puzzle_dir = Path("data/puzzles")
    puzzle_files = sorted(puzzle_dir.glob("*.json"))

    if len(puzzle_files) == 0:
        print("No puzzle files found in data/puzzles/")
        exit(1)

    print(f"Found {len(puzzle_files)} puzzle files\n")

    # Test sequential mode
    print("Testing sequential mode...")
    env = MultiPuzzleEnv(
        puzzle_files=[str(f) for f in puzzle_files],
        max_steps=100,
        mode='sequential'
    )

    # Run a few episodes
    for ep in range(10):
        state, actions = env.reset()
        print(f"Episode {ep+1}: {env.get_puzzle_name()}")

        # Take a few random steps
        for step in range(5):
            action_idx = np.random.randint(0, len(actions))
            next_state, reward, done, info = env.step(action_idx)
            if done:
                break

    # Print statistics
    env.print_statistics()

    print("\n✓ MultiPuzzleEnv test passed!")
