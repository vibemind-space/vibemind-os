"""
Prioritized Experience Replay - AGI Phase 1

Implements prioritized sampling of experiences based on TD-error,
with importance sampling correction for unbiased updates.

Key Features:
- Sum-tree for O(log n) prioritized sampling
- TD-error based priorities
- Importance sampling weights
- Integration with Dream Mode
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import deque
import random
import logging

logger = logging.getLogger(__name__)


@dataclass
class Experience:
    """Single experience tuple."""
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool
    priority: float = 1.0
    td_error: float = 0.0
    timestamp: int = 0


class SumTree:
    """
    Binary sum tree for efficient prioritized sampling.

    Each leaf stores a priority, and internal nodes store the sum of children.
    Enables O(log n) sampling proportional to priorities.
    """

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.tree = np.zeros(2 * capacity - 1)
        self.data = [None] * capacity
        self.write_idx = 0
        self.n_entries = 0

    def _propagate(self, idx: int, change: float):
        """Propagate priority change up the tree."""
        parent = (idx - 1) // 2
        self.tree[parent] += change
        if parent != 0:
            self._propagate(parent, change)

    def _retrieve(self, idx: int, s: float) -> int:
        """Retrieve leaf index for a given cumulative sum."""
        left = 2 * idx + 1
        right = left + 1

        if left >= len(self.tree):
            return idx

        if s <= self.tree[left]:
            return self._retrieve(left, s)
        else:
            return self._retrieve(right, s - self.tree[left])

    def total(self) -> float:
        """Get total sum of all priorities."""
        return self.tree[0]

    def add(self, priority: float, data: Any):
        """Add new experience with given priority."""
        idx = self.write_idx + self.capacity - 1

        self.data[self.write_idx] = data
        self.update(idx, priority)

        self.write_idx = (self.write_idx + 1) % self.capacity
        self.n_entries = min(self.n_entries + 1, self.capacity)

    def update(self, idx: int, priority: float):
        """Update priority of experience at index."""
        change = priority - self.tree[idx]
        self.tree[idx] = priority
        self._propagate(idx, change)

    def get(self, s: float) -> Tuple[int, float, Any]:
        """Get experience by cumulative sum."""
        idx = self._retrieve(0, s)
        data_idx = idx - self.capacity + 1
        return idx, self.tree[idx], self.data[data_idx]

    def min_priority(self) -> float:
        """Get minimum priority in tree."""
        if self.n_entries == 0:
            return 1.0
        # Only check leaves that have data
        leaf_start = self.capacity - 1
        leaf_end = leaf_start + self.n_entries
        return min(self.tree[leaf_start:leaf_end])


class PrioritizedReplayBuffer:
    """
    Prioritized Experience Replay Buffer.

    Samples experiences with probability proportional to TD-error,
    with importance sampling weights for unbiased gradient updates.
    """

    def __init__(
        self,
        capacity: int = 100000,
        alpha: float = 0.6,
        beta: float = 0.4,
        beta_increment: float = 0.001,
        epsilon: float = 1e-6,
        max_priority: float = 1.0
    ):
        """
        Initialize prioritized replay buffer.

        Args:
            capacity: Maximum buffer size
            alpha: Prioritization exponent (0 = uniform, 1 = full prioritization)
            beta: Importance sampling exponent (0 = no correction, 1 = full correction)
            beta_increment: Increment for beta per sample
            epsilon: Small constant for numerical stability
            max_priority: Default priority for new experiences
        """
        self.capacity = capacity
        self.alpha = alpha
        self.beta = beta
        self.beta_increment = beta_increment
        self.epsilon = epsilon
        self.max_priority = max_priority

        self.tree = SumTree(capacity)
        self.timestamp = 0

    def add(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool,
        td_error: Optional[float] = None
    ):
        """Add experience to buffer."""
        # Calculate priority
        if td_error is not None:
            priority = (abs(td_error) + self.epsilon) ** self.alpha
        else:
            priority = self.max_priority ** self.alpha

        experience = Experience(
            state=state,
            action=action,
            reward=reward,
            next_state=next_state,
            done=done,
            priority=priority,
            td_error=td_error or 0.0,
            timestamp=self.timestamp
        )

        self.tree.add(priority, experience)
        self.timestamp += 1

    def sample(self, batch_size: int) -> Tuple[List[Experience], np.ndarray, List[int]]:
        """
        Sample batch of experiences with prioritized sampling.

        Args:
            batch_size: Number of experiences to sample

        Returns:
            experiences: List of sampled experiences
            weights: Importance sampling weights
            indices: Tree indices for updating priorities
        """
        experiences = []
        indices = []
        priorities = []

        # Divide total priority into segments
        total = self.tree.total()
        segment = total / batch_size

        # Increase beta over time
        self.beta = min(1.0, self.beta + self.beta_increment)

        for i in range(batch_size):
            # Sample uniformly within segment
            low = segment * i
            high = segment * (i + 1)
            s = random.uniform(low, high)

            idx, priority, experience = self.tree.get(s)

            if experience is not None:
                experiences.append(experience)
                indices.append(idx)
                priorities.append(priority)

        # Calculate importance sampling weights
        min_priority = self.tree.min_priority()
        max_weight = (min_priority / total * self.tree.n_entries) ** (-self.beta)

        weights = np.array([
            ((p / total * self.tree.n_entries) ** (-self.beta)) / max_weight
            for p in priorities
        ])

        return experiences, weights, indices

    def update_priorities(self, indices: List[int], td_errors: np.ndarray):
        """Update priorities based on new TD-errors."""
        for idx, td_error in zip(indices, td_errors):
            priority = (abs(td_error) + self.epsilon) ** self.alpha
            self.tree.update(idx, priority)
            self.max_priority = max(self.max_priority, priority)

    def __len__(self) -> int:
        return self.tree.n_entries


class DreamModeReplay:
    """
    Experience replay integrated with Dream Mode.

    Performs offline consolidation and counterfactual learning
    during idle periods.
    """

    def __init__(
        self,
        replay_buffer: PrioritizedReplayBuffer,
        consolidation_threshold: float = 0.7,
        counterfactual_ratio: float = 0.2
    ):
        """
        Initialize dream mode replay.

        Args:
            replay_buffer: Prioritized replay buffer to use
            consolidation_threshold: Priority threshold for consolidation
            counterfactual_ratio: Ratio of counterfactual samples
        """
        self.buffer = replay_buffer
        self.consolidation_threshold = consolidation_threshold
        self.counterfactual_ratio = counterfactual_ratio

        # Consolidated memories
        self.consolidated: List[Experience] = []
        self.max_consolidated = 1000

    def dream_cycle(
        self,
        model,
        num_replays: int = 100,
        generate_counterfactuals: bool = True
    ) -> Dict[str, Any]:
        """
        Run a dream cycle for memory consolidation.

        Args:
            model: Model to update during dreaming
            num_replays: Number of experiences to replay
            generate_counterfactuals: Whether to generate counterfactual scenarios

        Returns:
            Statistics from dream cycle
        """
        stats = {
            "replays": 0,
            "consolidations": 0,
            "counterfactuals": 0,
            "avg_td_error": 0.0
        }

        if len(self.buffer) < num_replays:
            return stats

        # Sample high-priority experiences
        experiences, weights, indices = self.buffer.sample(num_replays)
        td_errors = []

        for exp, weight in zip(experiences, weights):
            # Replay experience through model
            td_error = self._replay_experience(model, exp, weight)
            td_errors.append(td_error)
            stats["replays"] += 1

            # Check for consolidation
            if exp.priority > self.consolidation_threshold:
                self._consolidate(exp)
                stats["consolidations"] += 1

        # Generate counterfactuals
        if generate_counterfactuals:
            num_cf = int(num_replays * self.counterfactual_ratio)
            for _ in range(num_cf):
                cf_exp = self._generate_counterfactual(experiences)
                if cf_exp:
                    td_error = self._replay_experience(model, cf_exp, 1.0)
                    stats["counterfactuals"] += 1

        # Update priorities
        self.buffer.update_priorities(indices, np.array(td_errors))

        stats["avg_td_error"] = np.mean(td_errors) if td_errors else 0.0
        return stats

    def _replay_experience(
        self,
        model,
        experience: Experience,
        weight: float
    ) -> float:
        """Replay single experience through model."""
        # This would be implemented based on the specific model
        # For now, return the stored TD-error
        return experience.td_error

    def _consolidate(self, experience: Experience):
        """Consolidate high-priority experience to long-term memory."""
        self.consolidated.append(experience)

        # Trim if over capacity
        if len(self.consolidated) > self.max_consolidated:
            # Remove lowest priority
            self.consolidated.sort(key=lambda e: e.priority, reverse=True)
            self.consolidated = self.consolidated[:self.max_consolidated]

    def _generate_counterfactual(
        self,
        experiences: List[Experience]
    ) -> Optional[Experience]:
        """Generate counterfactual experience."""
        if not experiences:
            return None

        # Select random experience
        base = random.choice(experiences)

        # Modify action (what if we took a different action?)
        new_action = random.randint(0, 9)  # Assuming 10 actions
        if new_action == base.action:
            new_action = (new_action + 1) % 10

        # Create counterfactual
        return Experience(
            state=base.state,
            action=new_action,
            reward=0.0,  # Unknown reward for counterfactual
            next_state=base.next_state,  # Would need world model for accurate prediction
            done=base.done,
            priority=base.priority * 0.5,  # Lower priority for counterfactuals
            td_error=0.0,
            timestamp=self.buffer.timestamp
        )

    def get_consolidated_memories(self) -> List[Experience]:
        """Get consolidated long-term memories."""
        return self.consolidated


class HindsightExperienceReplay:
    """
    Hindsight Experience Replay (HER) for goal-conditioned learning.

    Retroactively relabels failed episodes with achieved goals.
    """

    def __init__(
        self,
        replay_buffer: PrioritizedReplayBuffer,
        goal_dim: int,
        strategy: str = "future",  # future, final, episode, random
        k: int = 4  # Number of additional goals per transition
    ):
        self.buffer = replay_buffer
        self.goal_dim = goal_dim
        self.strategy = strategy
        self.k = k

        # Episode buffer for HER
        self.current_episode: List[Tuple[np.ndarray, int, float, np.ndarray, np.ndarray]] = []

    def store_transition(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        goal: np.ndarray,
        achieved_goal: np.ndarray,
        done: bool
    ):
        """Store transition with goal information."""
        self.current_episode.append((state, action, reward, next_state, achieved_goal))

        # Original transition
        self.buffer.add(state, action, reward, next_state, done)

        if done:
            # Apply HER at end of episode
            self._apply_her()
            self.current_episode = []

    def _apply_her(self):
        """Apply hindsight experience replay to current episode."""
        episode_length = len(self.current_episode)

        for t, (state, action, _, next_state, achieved_goal) in enumerate(self.current_episode):
            # Sample k additional goals
            additional_goals = self._sample_goals(t, episode_length)

            for new_goal in additional_goals:
                # Compute new reward (did we achieve the new goal?)
                new_reward = self._compute_reward(achieved_goal, new_goal)

                # Store with new goal
                # In practice, state/next_state would include goal
                self.buffer.add(
                    state, action, new_reward, next_state,
                    done=(new_reward > 0)
                )

    def _sample_goals(self, t: int, episode_length: int) -> List[np.ndarray]:
        """Sample additional goals based on strategy."""
        goals = []

        for _ in range(self.k):
            if self.strategy == "future":
                # Sample from future states in episode
                future_t = random.randint(t, episode_length - 1)
                goals.append(self.current_episode[future_t][4])  # achieved_goal

            elif self.strategy == "final":
                # Use final achieved goal
                goals.append(self.current_episode[-1][4])

            elif self.strategy == "episode":
                # Sample from any state in episode
                rand_t = random.randint(0, episode_length - 1)
                goals.append(self.current_episode[rand_t][4])

            elif self.strategy == "random":
                # Random goal (from buffer or generated)
                goals.append(np.random.randn(self.goal_dim))

        return goals

    def _compute_reward(
        self,
        achieved_goal: np.ndarray,
        desired_goal: np.ndarray,
        threshold: float = 0.05
    ) -> float:
        """Compute sparse reward based on goal achievement."""
        distance = np.linalg.norm(achieved_goal - desired_goal)
        return 1.0 if distance < threshold else 0.0
