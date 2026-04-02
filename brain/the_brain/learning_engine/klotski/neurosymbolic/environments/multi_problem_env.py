"""
Multi-Problem Environment
Wrapper that can switch between different problem types for meta-learning
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import torch
from typing import Tuple, Dict, List, Optional
from enum import Enum

from neurosymbolic.environments.klotski_graph_env import KlotskiGraphEnv
from neurosymbolic.environments.sorting_env import SortingEnv, SortingAlgorithm, BubbleSortEnv


class ProblemType(Enum):
    """Types of problems the AI can learn"""
    KLOTSKI = "klotski"
    QUICKSORT = "quicksort"
    BUBBLESORT = "bubblesort"
    MERGESORT = "mergesort"


class MultiProblemEnv:
    """
    Multi-problem environment for meta-learning

    Can switch between different problem types to test transfer learning
    """

    def __init__(
        self,
        problem_type: ProblemType = ProblemType.KLOTSKI,
        problem_config: Dict = None
    ):
        """
        Initialize multi-problem environment

        Args:
            problem_type: Which problem to start with
            problem_config: Configuration for the problem
        """
        self.problem_type = problem_type
        self.problem_config = problem_config or {}

        # Create the appropriate environment
        self.env = self._create_environment(problem_type)

        # Track statistics per problem type
        self.problem_stats = {
            ProblemType.KLOTSKI: {'episodes': 0, 'solutions': 0},
            ProblemType.QUICKSORT: {'episodes': 0, 'solutions': 0},
            ProblemType.BUBBLESORT: {'episodes': 0, 'solutions': 0},
        }

        print(f"[MultiProblemEnv] Initialized with {problem_type.value}")

    def _create_environment(self, problem_type: ProblemType):
        """Create environment based on problem type"""

        if problem_type == ProblemType.KLOTSKI:
            return KlotskiGraphEnv(
                graph_file=self.problem_config.get('graph_file', 'Klotski-Webpage/data.json'),
                max_steps=self.problem_config.get('max_steps', 200),
                reward_shaping=self.problem_config.get('reward_shaping', True)
            )

        elif problem_type == ProblemType.QUICKSORT:
            return SortingEnv(
                algorithm=SortingAlgorithm.QUICKSORT,
                array_size=self.problem_config.get('array_size', 10),
                max_steps=self.problem_config.get('max_steps', 100)
            )

        elif problem_type == ProblemType.BUBBLESORT:
            return BubbleSortEnv(
                array_size=self.problem_config.get('array_size', 10),
                max_steps=self.problem_config.get('max_steps', 150)
            )

        else:
            raise ValueError(f"Unknown problem type: {problem_type}")

    def switch_problem(self, new_problem_type: ProblemType):
        """Switch to a different problem type"""
        print(f"[MultiProblemEnv] Switching from {self.problem_type.value} to {new_problem_type.value}")
        self.problem_type = new_problem_type
        self.env = self._create_environment(new_problem_type)

    def reset(self, **kwargs) -> Tuple[torch.Tensor, List[int]]:
        """Reset current environment"""
        state, valid_actions = self.env.reset(**kwargs)

        # Pad state if needed to match max size
        state = self._pad_state(state)

        return state, valid_actions

    def step(self, action: int) -> Tuple[torch.Tensor, float, bool, Dict]:
        """Execute action in current environment"""
        state, reward, done, info = self.env.step(action)

        # Add problem type to info
        info['problem_type'] = self.problem_type.value

        # Track statistics
        if done:
            self.problem_stats[self.problem_type]['episodes'] += 1
            if info.get('sorted', False) or info.get('solution_dist', -1) == 0:
                self.problem_stats[self.problem_type]['solutions'] += 1

        # Pad state
        state = self._pad_state(state)

        return state, reward, done, info

    def _pad_state(self, state: torch.Tensor) -> torch.Tensor:
        """
        Pad state to consistent size for neural network

        Different problems have different state sizes:
        - Klotski: (5, 4) = 20 elements
        - Sorting: (array_size,) = variable

        Pad to max size (20) for consistent input
        """
        if len(state.shape) == 2:
            # Klotski board - flatten
            state = state.flatten()

        # Pad to size 20 (max)
        if len(state) < 20:
            padding = torch.zeros(20 - len(state))
            state = torch.cat([state, padding])
        elif len(state) > 20:
            # Truncate if larger
            state = state[:20]

        return state

    def get_statistics(self) -> Dict:
        """Get combined statistics"""
        total_episodes = sum(stats['episodes'] for stats in self.problem_stats.values())
        total_solutions = sum(stats['solutions'] for stats in self.problem_stats.values())

        return {
            'current_problem': self.problem_type.value,
            'total_episodes': total_episodes,
            'total_solutions': total_solutions,
            'success_rate': (total_solutions / total_episodes * 100) if total_episodes > 0 else 0,
            'problem_breakdown': {
                prob.value: {
                    'episodes': stats['episodes'],
                    'solutions': stats['solutions'],
                    'success_rate': (stats['solutions'] / stats['episodes'] * 100)
                                   if stats['episodes'] > 0 else 0
                }
                for prob, stats in self.problem_stats.items()
            }
        }

    def get_problem_type(self) -> str:
        """Get current problem type as string"""
        return self.problem_type.value


if __name__ == '__main__':
    # Add parent directory to path
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    # Test multi-problem environment
    print("="*80)
    print("TESTING MULTI-PROBLEM ENVIRONMENT")
    print("="*80)

    # Test 1: Klotski problem
    print("\n1. Testing Klotski Problem")
    env = MultiProblemEnv(
        problem_type=ProblemType.KLOTSKI,
        problem_config={'max_steps': 50}
    )

    state, valid_actions = env.reset()
    print(f"State shape: {state.shape}")
    print(f"Valid actions: {len(valid_actions)}")

    # Take a few random actions
    for i in range(3):
        action = np.random.choice(valid_actions[:10])  # Use first 10 actions
        state, reward, done, info = env.step(action)
        print(f"Step {i+1}: Reward={reward:.2f}, Problem={info['problem_type']}")

    # Test 2: Switch to QuickSort
    print("\n2. Switching to QuickSort Problem")
    env.switch_problem(ProblemType.QUICKSORT)

    state, valid_actions = env.reset()
    print(f"State shape: {state.shape}")
    print(f"Valid actions: {len(valid_actions)}")

    # Take a few random actions
    for i in range(3):
        action = np.random.choice(valid_actions)
        state, reward, done, info = env.step(action)
        print(f"Step {i+1}: Reward={reward:.2f}, Problem={info['problem_type']}")

    # Test 3: Switch to BubbleSort
    print("\n3. Switching to BubbleSort Problem")
    env.switch_problem(ProblemType.BUBBLESORT)

    state, valid_actions = env.reset()
    print(f"State shape: {state.shape}")

    for i in range(3):
        action = np.random.choice(len(valid_actions))
        state, reward, done, info = env.step(action)
        print(f"Step {i+1}: Reward={reward:.2f}, Problem={info['problem_type']}")

    # Statistics
    print("\n4. Overall Statistics")
    stats = env.get_statistics()
    print(f"Current problem: {stats['current_problem']}")
    print(f"Total episodes: {stats['total_episodes']}")
    print(f"Total solutions: {stats['total_solutions']}")
    print(f"Success rate: {stats['success_rate']:.1f}%")

    print("\nPer-problem breakdown:")
    for problem, breakdown in stats['problem_breakdown'].items():
        print(f"  {problem}:")
        print(f"    Episodes: {breakdown['episodes']}")
        print(f"    Solutions: {breakdown['solutions']}")
        print(f"    Success: {breakdown['success_rate']:.1f}%")

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)
