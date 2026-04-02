"""
Auto-Extending Curriculum Manager

Implements Sakana AI's progressive curriculum strategy from the Mazes example.
Gradually extends trajectory length from start_len to max_len over training.

Key benefits:
- Easier credit assignment for short trajectories
- Progressive difficulty scaling
- Faster convergence (2-4x improvement)
"""

import numpy as np
from typing import Dict, List


class CurriculumManager:
    """
    Manages progressive trajectory length curriculum

    Starts with short trajectories (5 steps) and gradually extends
    to full solution length (60 steps) as training progresses.

    Based on Sakana AI CTM Mazes example.
    """

    def __init__(
        self,
        start_len: int = 5,
        max_len: int = 60,
        extend_every: int = 1000,
        extend_by: int = 5,
        mode: str = "linear"
    ):
        """
        Args:
            start_len: Initial trajectory length
            max_len: Maximum trajectory length (full solution)
            extend_every: Extend curriculum every N training steps
            extend_by: Extend by this many steps each time
            mode: Extension mode ('linear', 'exponential', 'adaptive')
        """
        self.start_len = start_len
        self.max_len = max_len
        self.extend_every = extend_every
        self.extend_by = extend_by
        self.mode = mode

        # State
        self.current_len = start_len
        self.steps_trained = 0
        self.extensions = 0
        self.avg_losses = []  # Track for adaptive mode

    def get_trajectory_length(self) -> int:
        """Get current curriculum trajectory length"""
        return min(self.current_len, self.max_len)

    def should_extend(self) -> bool:
        """Check if curriculum should be extended"""
        if self.current_len >= self.max_len:
            return False

        if self.mode == "adaptive":
            # Extend when loss plateaus (adaptive)
            if len(self.avg_losses) < 5:
                return False
            recent_losses = self.avg_losses[-5:]
            loss_variance = np.var(recent_losses)
            return loss_variance < 0.01  # Loss plateaued
        else:
            # Extend every N steps (linear/exponential)
            return self.steps_trained > 0 and self.steps_trained % self.extend_every == 0

    def update(self, steps: int = 1, avg_loss: float = None):
        """
        Update curriculum based on training progress

        Args:
            steps: Number of training steps completed
            avg_loss: Average loss (for adaptive mode)
        """
        self.steps_trained += steps

        if avg_loss is not None:
            self.avg_losses.append(avg_loss)

        # Check if we should extend
        if self.should_extend():
            self._extend_curriculum()

    def _extend_curriculum(self):
        """Extend curriculum length"""
        if self.current_len >= self.max_len:
            return

        old_len = self.current_len

        if self.mode == "exponential":
            # Exponential growth: 5, 10, 20, 40, 60
            self.current_len = min(self.current_len * 2, self.max_len)
        else:
            # Linear growth: 5, 10, 15, 20, ..., 60
            self.current_len = min(self.current_len + self.extend_by, self.max_len)

        self.extensions += 1
        self.avg_losses = []  # Reset for adaptive mode

        return old_len, self.current_len

    def get_truncated_demo(self, demonstration: Dict, shuffle: bool = False) -> Dict:
        """
        Truncate demonstration to current curriculum length

        Args:
            demonstration: Full demonstration dict with 'actions' key
            shuffle: If True, randomly sample a window instead of from start

        Returns:
            Truncated demonstration dict
        """
        full_actions = demonstration['actions']
        current_len = self.get_trajectory_length()

        if current_len >= len(full_actions):
            # Return full demo
            return demonstration

        if shuffle:
            # Random window sampling
            max_start = len(full_actions) - current_len
            start_idx = np.random.randint(0, max_start + 1)
            end_idx = start_idx + current_len
        else:
            # From beginning (standard curriculum)
            start_idx = 0
            end_idx = current_len

        truncated = {
            'puzzle_file': demonstration['puzzle_file'],
            'actions': full_actions[start_idx:end_idx],
            'solution_length': current_len,
            'truncated': True,
            'truncated_from': len(full_actions),
            'window_start': start_idx,
            'window_end': end_idx
        }

        if 'action_names' in demonstration:
            truncated['action_names'] = demonstration['action_names'][start_idx:end_idx]

        return truncated

    def get_state(self) -> Dict:
        """Get curriculum state for logging"""
        return {
            'current_len': self.current_len,
            'max_len': self.max_len,
            'steps_trained': self.steps_trained,
            'extensions': self.extensions,
            'completion': self.current_len / self.max_len
        }

    def __repr__(self):
        return (f"CurriculumManager(current={self.current_len}/{self.max_len}, "
                f"steps={self.steps_trained}, extensions={self.extensions})")


class MultiStepCurriculum(CurriculumManager):
    """
    Multi-step curriculum with explicit milestones

    Example: 5 → 10 → 20 → 40 → 60 with specific loss thresholds
    """

    def __init__(
        self,
        milestones: List[int] = None,
        loss_thresholds: List[float] = None
    ):
        """
        Args:
            milestones: List of trajectory lengths [5, 10, 20, 40, 60]
            loss_thresholds: Loss thresholds to advance [1.5, 1.2, 1.0, 0.8]
        """
        self.milestones = milestones or [5, 10, 20, 40, 60]
        self.loss_thresholds = loss_thresholds or [1.5, 1.2, 1.0, 0.8]
        self.milestone_idx = 0

        super().__init__(
            start_len=self.milestones[0],
            max_len=self.milestones[-1],
            extend_every=0,  # Not used
            mode="adaptive"
        )

        self.current_len = self.milestones[0]

    def should_extend(self) -> bool:
        """Extend when loss threshold reached"""
        if self.milestone_idx >= len(self.milestones) - 1:
            return False

        if len(self.avg_losses) < 10:
            return False

        # Check if recent average loss is below threshold
        recent_avg = np.mean(self.avg_losses[-10:])
        current_threshold = self.loss_thresholds[min(self.milestone_idx, len(self.loss_thresholds) - 1)]

        return recent_avg < current_threshold

    def _extend_curriculum(self):
        """Advance to next milestone"""
        if self.milestone_idx >= len(self.milestones) - 1:
            return

        old_len = self.current_len
        self.milestone_idx += 1
        self.current_len = self.milestones[self.milestone_idx]
        self.extensions += 1
        self.avg_losses = []

        return old_len, self.current_len


def create_curriculum(config: Dict) -> CurriculumManager:
    """
    Factory function to create curriculum manager

    Args:
        config: Curriculum configuration dict

    Returns:
        CurriculumManager instance
    """
    curriculum_type = config.get('type', 'linear')

    if curriculum_type == 'multi_step':
        return MultiStepCurriculum(
            milestones=config.get('milestones', [5, 10, 20, 40, 60]),
            loss_thresholds=config.get('loss_thresholds', [1.5, 1.2, 1.0, 0.8])
        )
    else:
        return CurriculumManager(
            start_len=config.get('start_len', 5),
            max_len=config.get('max_len', 60),
            extend_every=config.get('extend_every', 1000),
            extend_by=config.get('extend_by', 5),
            mode=config.get('mode', 'linear')
        )
