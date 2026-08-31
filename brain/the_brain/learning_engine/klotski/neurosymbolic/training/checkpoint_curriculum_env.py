"""
Checkpoint Curriculum Environment

Wraps the abstract action environment to add checkpoint-based curriculum learning.
Provides:
1. Checkpoint detection and bonus rewards
2. Ability to start from checkpoint states
3. Progressive difficulty through checkpoints
"""

import json
import torch
import numpy as np
from typing import Tuple, Dict, Optional, List
from neurosymbolic.training.abstract_action_env import AbstractActionEnv


class CheckpointCurriculumEnv(AbstractActionEnv):
    """
    Environment with checkpoint-based curriculum learning

    Features:
    - Detects when agent reaches checkpoint states
    - Provides bonus rewards for reaching checkpoints
    - Can initialize from any checkpoint state
    - Supports progressive training (start from later checkpoints)
    """

    def __init__(
        self,
        checkpoint_file: str,
        checkpoint_reward: float = 20.0,
        start_checkpoint: int = 0,
        *args,
        **kwargs
    ):
        """
        Initialize checkpoint curriculum environment

        Args:
            checkpoint_file: Path to checkpoint JSON file
            checkpoint_reward: Bonus reward for reaching a checkpoint
            start_checkpoint: Which checkpoint to start from (0 = initial state)
        """
        super().__init__(*args, **kwargs)

        self.checkpoint_reward = checkpoint_reward
        self.start_checkpoint = start_checkpoint

        # Load checkpoint states
        with open(checkpoint_file, 'r') as f:
            checkpoint_data = json.load(f)

        self.checkpoints = checkpoint_data['checkpoints']
        self.num_checkpoints = len(self.checkpoints)

        # Track which checkpoints have been reached in current episode
        self.reached_checkpoints = set()

        print(f"[Checkpoint Curriculum] Loaded {self.num_checkpoints} checkpoints")
        print(f"[Checkpoint Curriculum] Checkpoint reward: +{checkpoint_reward}")
        print(f"[Checkpoint Curriculum] Starting from checkpoint: {start_checkpoint}")

    def reset(self, checkpoint_idx: Optional[int] = None) -> Tuple[torch.Tensor, int]:
        """
        Reset environment

        Args:
            checkpoint_idx: Reserved for future use (starting from checkpoints)

        Returns:
            Tuple of (state_tensor, num_actions=4)
        """
        # Reset base environment
        state_tensor, num_actions = super().reset()

        # Clear reached checkpoints
        self.reached_checkpoints = set()

        return state_tensor, num_actions

    def step(self, action: int) -> Tuple[torch.Tensor, float, bool, Dict]:
        """
        Execute action and check for checkpoint completion

        Args:
            action: Abstract action index (0=UP, 1=DOWN, 2=LEFT, 3=RIGHT)

        Returns:
            Tuple of (next_state, reward, done, info)
        """
        # Execute base step
        state_tensor, reward, done, info = super().step(action)

        # Step penalty removed - was causing negative rewards and hindering learning
        # TODO: Re-add smaller penalty (0.0001) once puzzles start solving
        # reward -= 0.001

        # Check if we've reached a new checkpoint
        current_board = self.state.get_board_string()

        for i, checkpoint in enumerate(self.checkpoints):
            # Skip if already reached
            if i in self.reached_checkpoints:
                continue

            # Check if current state matches checkpoint
            if current_board == checkpoint['board_state']:
                # Checkpoint reached!
                self.reached_checkpoints.add(i)
                reward += self.checkpoint_reward

                info['checkpoint_reached'] = i
                info['checkpoint_description'] = checkpoint['description']

                print(f"[Checkpoint {i}] REACHED! {checkpoint['description']} (+{self.checkpoint_reward} reward)")
                break

        # Add checkpoint progress to info
        info['checkpoints_reached'] = len(self.reached_checkpoints)
        info['checkpoint_progress'] = len(self.reached_checkpoints) / self.num_checkpoints

        return state_tensor, reward, done, info

    def set_start_checkpoint(self, checkpoint_idx: int):
        """
        Set which checkpoint to start from for future resets

        Args:
            checkpoint_idx: Index of checkpoint to start from (0 = initial state)
        """
        if 0 <= checkpoint_idx < self.num_checkpoints:
            self.start_checkpoint = checkpoint_idx
            print(f"[Checkpoint Curriculum] Start checkpoint set to: {checkpoint_idx}")
        else:
            print(f"[Checkpoint Curriculum] Invalid checkpoint index: {checkpoint_idx}")

    def get_checkpoint_info(self) -> Dict:
        """
        Get information about current checkpoint progress

        Returns:
            Dictionary with checkpoint statistics
        """
        return {
            'num_checkpoints': self.num_checkpoints,
            'reached_checkpoints': list(self.reached_checkpoints),
            'checkpoints_reached': len(self.reached_checkpoints),
            'checkpoint_progress': len(self.reached_checkpoints) / self.num_checkpoints,
            'start_checkpoint': self.start_checkpoint
        }
