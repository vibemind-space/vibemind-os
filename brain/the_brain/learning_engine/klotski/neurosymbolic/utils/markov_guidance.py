"""
Markov-Based Guidance from Expert Demonstrations

Extracts state transition patterns from BFS solutions to guide RL exploration.
Instead of matching exact actions, we learn:
- Which states lead toward the goal (transition probabilities)
- Distance to goal from each state (value estimates)
- State similarity for generalization

This provides soft guidance rather than hard action matching.
"""

import numpy as np
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict


class MarkovGuidance:
    """
    Markov-based guidance system from expert demonstrations

    Key idea: Use BFS solutions to build a probabilistic model of
    "which states are on the path to the goal" rather than trying
    to match exact actions.
    """

    def __init__(self, demo_dir: str = "demonstrations_formatted"):
        """
        Initialize Markov guidance

        Args:
            demo_dir: Directory containing expert demonstrations
        """
        self.demo_dir = Path(demo_dir)

        # State transition map: state_hash -> [next_state_hashes]
        self.transitions = defaultdict(list)

        # State distances: state_hash -> distance_to_goal
        self.state_distances = {}

        # State visitation counts (for confidence)
        self.state_counts = defaultdict(int)

        # Goal states
        self.goal_states = set()

        # Action supervision: state_hash -> optimal_next_state_hash
        # Maps each state to the next state in the expert demonstration
        self.optimal_transitions = {}  # state_hash -> next_state_hash

        # Total demonstrations loaded
        self.num_demos = 0

    def load_demonstration(self, puzzle_name: str) -> bool:
        """
        Load demonstration for a specific puzzle

        Args:
            puzzle_name: Name of puzzle (e.g., "01_standard")

        Returns:
            True if loaded successfully
        """
        demo_path = self.demo_dir / f"{puzzle_name}_solution.json"

        if not demo_path.exists():
            print(f"[WARNING] No demonstration found: {demo_path}")
            return False

        try:
            with open(demo_path, 'r') as f:
                demo_data = json.load(f)

            states = demo_data.get('states', [])

            if len(states) < 2:
                print(f"[WARNING] Demo too short: {len(states)} states")
                return False

            # Extract state transitions
            for i, state in enumerate(states):
                state_hash = self._hash_state(np.array(state))

                # Track distance to goal (reverse index)
                distance = len(states) - i - 1
                self.state_distances[state_hash] = distance

                # Track visitation
                self.state_counts[state_hash] += 1

                # Mark goal states (last few states)
                if distance <= 5:  # Last 5 states are "goal region"
                    self.goal_states.add(state_hash)

                # Add transition to next state
                if i < len(states) - 1:
                    next_state_hash = self._hash_state(np.array(states[i + 1]))
                    self.transitions[state_hash].append(next_state_hash)

                    # Store optimal transition for action supervision
                    self.optimal_transitions[state_hash] = next_state_hash

            self.num_demos += 1
            print(f"[OK] Loaded Markov guidance: {puzzle_name}")
            print(f"  States: {len(states)}, Unique: {len(self.state_distances)}")
            print(f"  Goal region: {len(self.goal_states)} states")

            return True

        except Exception as e:
            print(f"[ERROR] Failed to load demonstration: {e}")
            return False

    def _hash_state(self, state: np.ndarray) -> str:
        """Hash state for lookup"""
        return hashlib.md5(state.tobytes()).hexdigest()

    def get_progress_bonus(self, current_state: np.ndarray, next_state: np.ndarray) -> float:
        """
        Calculate progress bonus based on state transitions

        Returns positive reward if moving toward goal,
        negative if moving away.

        Args:
            current_state: Current state array
            next_state: Next state array

        Returns:
            Progress bonus (positive = good, negative = bad)
        """
        current_hash = self._hash_state(current_state)
        next_hash = self._hash_state(next_state)

        # Check if states are in our demonstration map
        current_dist = self.state_distances.get(current_hash, None)
        next_dist = self.state_distances.get(next_hash, None)

        # Case 1: Both states in demonstration - use exact distances
        if current_dist is not None and next_dist is not None:
            progress = current_dist - next_dist  # Positive if getting closer

            # Scale bonus: +1.0 for getting 1 step closer
            bonus = progress * 1.0

            # Extra bonus for entering goal region
            if next_hash in self.goal_states and current_hash not in self.goal_states:
                bonus += 2.0

            return bonus

        # Case 2: Only next state in demonstration (discovered known good state)
        if next_dist is not None:
            # Reward discovering a state on the optimal path
            # Closer to goal = bigger reward
            bonus = 0.5 * (1.0 - next_dist / max(self.state_distances.values()))
            return bonus

        # Case 3: Neither state in demonstration (exploring unknown territory)
        # No bonus, but also no penalty (let other rewards guide)
        return 0.0

    def is_on_optimal_path(self, state: np.ndarray) -> bool:
        """
        Check if state is on the optimal path

        Args:
            state: State array

        Returns:
            True if state is in demonstration
        """
        state_hash = self._hash_state(state)
        return state_hash in self.state_distances

    def get_distance_to_goal(self, state: np.ndarray) -> Optional[int]:
        """
        Get known distance to goal from this state

        Args:
            state: State array

        Returns:
            Distance to goal, or None if unknown
        """
        state_hash = self._hash_state(state)
        return self.state_distances.get(state_hash, None)

    def get_value_estimate(self, state: np.ndarray) -> float:
        """
        Get value estimate based on demonstration

        Higher value = closer to goal

        Args:
            state: State array

        Returns:
            Value estimate in [0, 1]
        """
        distance = self.get_distance_to_goal(state)

        if distance is None:
            return 0.0  # Unknown state

        # Normalize: 1.0 at goal, 0.0 at start
        max_distance = max(self.state_distances.values())
        return 1.0 - (distance / max_distance)

    def get_optimal_next_state(self, current_state: np.ndarray) -> Optional[str]:
        """
        Get the optimal next state hash from expert demonstration

        Args:
            current_state: Current state array

        Returns:
            Hash of optimal next state, or None if not in demonstration
        """
        state_hash = self._hash_state(current_state)
        return self.optimal_transitions.get(state_hash, None)

    def is_optimal_action(
        self,
        current_state: np.ndarray,
        next_state: np.ndarray
    ) -> bool:
        """
        Check if taking an action that leads to next_state is optimal

        Args:
            current_state: Current state
            next_state: State after action

        Returns:
            True if this action matches the expert demonstration
        """
        optimal_next = self.get_optimal_next_state(current_state)
        if optimal_next is None:
            return False

        next_state_hash = self._hash_state(next_state)
        return next_state_hash == optimal_next

    def get_statistics(self) -> Dict:
        """Get statistics about loaded demonstrations"""
        return {
            'num_demos': self.num_demos,
            'unique_states': len(self.state_distances),
            'goal_states': len(self.goal_states),
            'optimal_transitions': len(self.optimal_transitions),
            'avg_path_length': np.mean(list(self.state_distances.values())) if self.state_distances else 0,
            'max_path_length': max(self.state_distances.values()) if self.state_distances else 0,
        }


class MultiPuzzleMarkovGuidance:
    """
    Markov guidance for multiple puzzles

    Maintains separate guidance for each puzzle while
    allowing cross-puzzle generalization.
    """

    def __init__(self, demo_dir: str = "demonstrations_formatted"):
        """
        Initialize multi-puzzle guidance

        Args:
            demo_dir: Directory containing demonstrations
        """
        self.demo_dir = demo_dir
        self.guides = {}  # puzzle_name -> MarkovGuidance

    def load_puzzle(self, puzzle_name: str) -> bool:
        """
        Load guidance for a specific puzzle

        Args:
            puzzle_name: Puzzle name (e.g., "01_standard")

        Returns:
            True if loaded successfully
        """
        if puzzle_name in self.guides:
            return True  # Already loaded

        guide = MarkovGuidance(self.demo_dir)
        if guide.load_demonstration(puzzle_name):
            self.guides[puzzle_name] = guide
            return True
        return False

    def load_all_puzzles(self, puzzle_files: List[str]) -> int:
        """
        Load guidance for all puzzles

        Args:
            puzzle_files: List of puzzle file paths

        Returns:
            Number of puzzles loaded successfully
        """
        loaded = 0
        for puzzle_file in puzzle_files:
            puzzle_name = Path(puzzle_file).stem
            if self.load_puzzle(puzzle_name):
                loaded += 1
        return loaded

    def get_progress_bonus(
        self,
        puzzle_name: str,
        current_state: np.ndarray,
        next_state: np.ndarray
    ) -> float:
        """
        Get progress bonus for specific puzzle

        Args:
            puzzle_name: Puzzle name
            current_state: Current state
            next_state: Next state

        Returns:
            Progress bonus
        """
        if puzzle_name not in self.guides:
            return 0.0

        return self.guides[puzzle_name].get_progress_bonus(current_state, next_state)

    def get_statistics(self) -> Dict:
        """Get statistics for all loaded puzzles"""
        stats = {}
        for puzzle_name, guide in self.guides.items():
            stats[puzzle_name] = guide.get_statistics()
        return stats


if __name__ == "__main__":
    # Test Markov guidance
    print("="*70)
    print("TESTING MARKOV GUIDANCE")
    print("="*70)

    # Test single puzzle
    guide = MarkovGuidance("demonstrations_formatted")
    success = guide.load_demonstration("01_standard")

    if success:
        stats = guide.get_statistics()
        print(f"\nStatistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

        print(f"\n[OK] Markov guidance working!")
    else:
        print(f"\n[FAILED] Could not load demonstration")

    # Test multi-puzzle
    print("\n" + "="*70)
    print("TESTING MULTI-PUZZLE GUIDANCE")
    print("="*70)

    multi_guide = MultiPuzzleMarkovGuidance("demonstrations_formatted")
    puzzle_files = [
        'data/puzzles/01_standard.json',
        'data/puzzles/02_visual.json',
        'data/puzzles/03_planning.json',
        'data/puzzles/04_memory.json',
        'data/puzzles/05_integration.json'
    ]

    loaded = multi_guide.load_all_puzzles(puzzle_files)
    print(f"\nLoaded {loaded}/{len(puzzle_files)} puzzles")

    all_stats = multi_guide.get_statistics()
    for puzzle_name, stats in all_stats.items():
        print(f"\n{puzzle_name}:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

    print("\n" + "="*70)
    print("MARKOV GUIDANCE TEST COMPLETE")
    print("="*70)
