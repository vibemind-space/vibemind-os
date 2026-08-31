"""
Sorting Algorithm Environments
Reinforcement learning environments for learning sorting algorithms
"""

import numpy as np
import torch
from typing import Tuple, Dict, List
from enum import Enum


class SortingAlgorithm(Enum):
    """Types of sorting algorithms"""
    QUICKSORT = "quicksort"
    MERGESORT = "mergesort"
    BUBBLESORT = "bubblesort"
    INSERTIONSORT = "insertionsort"


class SortingEnv:
    """
    Environment for learning sorting algorithms through RL

    State: Current array configuration
    Actions: Swap two elements or mark partition point
    Reward: Progress toward sorted array
    """

    def __init__(
        self,
        algorithm: SortingAlgorithm = SortingAlgorithm.QUICKSORT,
        array_size: int = 10,
        max_steps: int = 100,
        value_range: Tuple[int, int] = (0, 100)
    ):
        """
        Initialize sorting environment

        Args:
            algorithm: Which sorting algorithm to learn
            array_size: Size of array to sort
            max_steps: Maximum steps per episode
            value_range: Range of values in array (min, max)
        """
        self.algorithm = algorithm
        self.array_size = array_size
        self.max_steps = max_steps
        self.value_range = value_range

        # Current state
        self.array = None
        self.target = None
        self.step_count = 0
        self.swaps_made = 0

        # Episode stats
        self.episode_count = 0
        self.total_solutions = 0

        print(f"[SortingEnv] Initialized {algorithm.value} environment")
        print(f"  Array size: {array_size}")
        print(f"  Value range: {value_range}")
        print(f"  Max steps: {max_steps}")

    def reset(self, seed: int = None) -> Tuple[torch.Tensor, List[int]]:
        """
        Reset environment with new random array

        Returns:
            state: Current array as tensor
            valid_actions: List of valid action indices
        """
        if seed is not None:
            np.random.seed(seed)

        # Generate random unsorted array
        self.array = np.random.randint(
            self.value_range[0],
            self.value_range[1],
            size=self.array_size
        ).astype(np.float32)

        # Target is sorted array
        self.target = np.sort(self.array)

        self.step_count = 0
        self.swaps_made = 0
        self.episode_count += 1

        # Valid actions: swap any two elements
        # Action encoding: index = i * array_size + j means swap(i, j)
        valid_actions = list(range(self.array_size * self.array_size))

        return self._get_state(), valid_actions

    def step(self, action: int) -> Tuple[torch.Tensor, float, bool, Dict]:
        """
        Execute action (swap two elements)

        Args:
            action: Action index (i * array_size + j = swap i and j)

        Returns:
            state: New array state
            reward: Reward for this action
            done: Episode finished?
            info: Additional information
        """
        self.step_count += 1

        # Decode action to swap indices
        i = action // self.array_size
        j = action % self.array_size

        # Calculate inversions before swap
        inversions_before = self._count_inversions()

        # Perform swap
        if i != j and i < self.array_size and j < self.array_size:
            self.array[i], self.array[j] = self.array[j], self.array[i]
            self.swaps_made += 1

        # Calculate inversions after swap
        inversions_after = self._count_inversions()

        # Check if sorted
        is_sorted = np.array_equal(self.array, self.target)
        done = is_sorted or (self.step_count >= self.max_steps)

        # Compute reward
        if is_sorted:
            # Big reward for solving
            reward = 100.0
            self.total_solutions += 1
            print(f"[SortingEnv] SOLVED {self.algorithm.value} in {self.step_count} steps!")
            print(f"  Swaps made: {self.swaps_made}")
            print(f"  Total solutions: {self.total_solutions}/{self.episode_count}")
        else:
            # Reward based on progress (reducing inversions)
            progress = inversions_before - inversions_after
            reward = progress * 2.0  # Positive if reducing inversions

            # Small penalty for each step to encourage efficiency
            reward -= 0.1

            # Extra penalty for useless swaps (same element)
            if i == j:
                reward -= 1.0

        # Info
        info = {
            'inversions': inversions_after,
            'swaps': self.swaps_made,
            'sorted': is_sorted,
            'progress': inversions_before - inversions_after,
            'algorithm': self.algorithm.value
        }

        return self._get_state(), reward, done, info

    def _get_state(self) -> torch.Tensor:
        """Get current state as tensor"""
        # Normalize array values to [0, 1]
        normalized = (self.array - self.value_range[0]) / (self.value_range[1] - self.value_range[0])
        return torch.tensor(normalized, dtype=torch.float32)

    def _count_inversions(self) -> int:
        """Count number of inversions (pairs out of order)"""
        inversions = 0
        for i in range(len(self.array)):
            for j in range(i + 1, len(self.array)):
                if self.array[i] > self.array[j]:
                    inversions += 1
        return inversions

    def get_statistics(self) -> Dict:
        """Get environment statistics"""
        return {
            'algorithm': self.algorithm.value,
            'total_episodes': self.episode_count,
            'total_solutions': self.total_solutions,
            'success_rate': (self.total_solutions / self.episode_count * 100)
                           if self.episode_count > 0 else 0,
            'array_size': self.array_size
        }

    def render(self):
        """Print current array state"""
        print(f"Current: {self.array}")
        print(f"Target:  {self.target}")
        print(f"Inversions: {self._count_inversions()}")


class BubbleSortEnv(SortingEnv):
    """Specialized environment for learning bubble sort"""

    def __init__(self, array_size: int = 10, **kwargs):
        super().__init__(
            algorithm=SortingAlgorithm.BUBBLESORT,
            array_size=array_size,
            **kwargs
        )
        print("[BubbleSortEnv] Can only swap adjacent elements")

    def step(self, action: int) -> Tuple[torch.Tensor, float, bool, Dict]:
        """
        Bubble sort only allows adjacent swaps

        Action: index of left element to swap with right neighbor
        """
        self.step_count += 1

        # Decode action (0 to array_size-2)
        i = action % (self.array_size - 1)
        j = i + 1

        inversions_before = self._count_inversions()

        # Swap adjacent elements
        self.array[i], self.array[j] = self.array[j], self.array[i]
        self.swaps_made += 1

        inversions_after = self._count_inversions()

        # Check if sorted
        is_sorted = np.array_equal(self.array, self.target)
        done = is_sorted or (self.step_count >= self.max_steps)

        # Reward
        if is_sorted:
            reward = 100.0
            self.total_solutions += 1
            print(f"[BubbleSortEnv] SOLVED in {self.step_count} swaps!")
        else:
            progress = inversions_before - inversions_after
            reward = progress * 3.0 - 0.1  # Higher weight for bubble sort

        info = {
            'inversions': inversions_after,
            'swaps': self.swaps_made,
            'sorted': is_sorted,
            'algorithm': 'bubblesort'
        }

        return self._get_state(), reward, done, info


if __name__ == '__main__':
    # Test sorting environments
    print("="*80)
    print("TESTING SORTING ENVIRONMENTS")
    print("="*80)

    # Test QuickSort environment
    print("\n1. QuickSort Environment")
    env = SortingEnv(
        algorithm=SortingAlgorithm.QUICKSORT,
        array_size=5,
        max_steps=50
    )

    state, valid_actions = env.reset(seed=42)
    print(f"Initial state: {state}")
    env.render()

    # Try random swaps
    for i in range(10):
        action = np.random.choice(valid_actions)
        state, reward, done, info = env.step(action)
        print(f"Step {i+1}: Swap action={action}, Reward={reward:.2f}, Inversions={info['inversions']}")

        if done:
            print("Episode finished!")
            break

    # Test BubbleSort environment
    print("\n2. BubbleSort Environment")
    bubble_env = BubbleSortEnv(array_size=5, max_steps=50)

    state, _ = bubble_env.reset(seed=42)
    print(f"Initial state: {state}")
    bubble_env.render()

    # Statistics
    print("\n3. Statistics")
    stats = env.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)
