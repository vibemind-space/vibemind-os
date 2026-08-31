"""
Curriculum Manager - Automatic Level Progression

When the agent solves a puzzle, this manager automatically generates
a new starting position by rotating/transforming the state space,
creating progressively harder challenges.

Flow:
  Episode 1: Start (dist=126) > 126 moves > SOLVED!
    > Rotate > Level 2 start (dist=110)
  Episode 2: Start (dist=110) > 110 moves > SOLVED!
    > Rotate > Level 3 start (dist=95)
  ...infinite progression
"""

import numpy as np
import random
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import json


class CurriculumManager:
    """
    Manages automatic curriculum learning for Klotski puzzle

    Strategy:
    - Level 1: Start from furthest node (dist=126)
    - On solve: Pick new start from nodes with high solution_dist
    - Gradually reduce difficulty to ensure success
    - Track statistics for each level
    """

    def __init__(
        self,
        graph: Dict,
        start_hash: str,
        initial_difficulty: int = 126,
        min_difficulty: int = 40,
        difficulty_decay: float = 0.9,
        difficulty_window: int = 10
    ):
        """
        Initialize curriculum manager

        Args:
            graph: The complete 25,955-node Klotski graph
            start_hash: Initial start node hash (furthest from solution)
            initial_difficulty: Starting difficulty (solution_dist)
            min_difficulty: Minimum difficulty level
            difficulty_decay: How much to reduce difficulty each level
            difficulty_window: +/- range when selecting new start nodes
        """
        self.graph = graph
        self.initial_start_hash = start_hash
        self.initial_difficulty = initial_difficulty
        self.min_difficulty = min_difficulty
        self.difficulty_decay = difficulty_decay
        self.difficulty_window = difficulty_window

        # Current state
        self.current_level = 1
        self.current_start_hash = start_hash
        self.current_difficulty = initial_difficulty

        # Level history
        self.level_history: List[Dict] = []
        self.solved_hashes: List[str] = []

        # Pre-compute nodes by difficulty
        self._build_difficulty_index()

        print(f"[CurriculumManager] Initialized")
        print(f"  Initial difficulty: {initial_difficulty}")
        print(f"  Difficulty range: {min_difficulty} - {initial_difficulty}")
        print(f"  Decay rate: {difficulty_decay}")

    def _build_difficulty_index(self):
        """Build index of nodes by solution distance for fast lookup"""
        self.nodes_by_distance: Dict[int, List[str]] = {}

        for node_hash, node_data in self.graph.items():
            dist = node_data['solution_dist']
            if dist not in self.nodes_by_distance:
                self.nodes_by_distance[dist] = []
            self.nodes_by_distance[dist].append(node_hash)

        # Sort for statistics
        distances = sorted(self.nodes_by_distance.keys(), reverse=True)
        print(f"[CurriculumManager] Difficulty index built:")
        print(f"  Max distance: {distances[0]}")
        print(f"  Min distance: {distances[-1]}")
        print(f"  Unique distances: {len(distances)}")

    def on_episode_end(
        self,
        solved: bool,
        episode_reward: float,
        episode_length: int,
        final_hash: str
    ) -> Tuple[str, int]:
        """
        Called when an episode ends

        Args:
            solved: Whether the puzzle was solved
            episode_reward: Total reward for the episode
            episode_length: Number of steps taken
            final_hash: Final state hash

        Returns:
            (new_start_hash, new_level): Next starting position and level number
        """
        # Record level statistics
        level_stats = {
            'level': self.current_level,
            'start_hash': self.current_start_hash,
            'target_difficulty': self.current_difficulty,
            'solved': solved,
            'reward': episode_reward,
            'steps': episode_length,
            'final_hash': final_hash
        }
        self.level_history.append(level_stats)

        if solved:
            self.solved_hashes.append(final_hash)
            print(f"\n[CurriculumManager] Level {self.current_level} SOLVED!")
            print(f"  Reward: {episode_reward:.2f}")
            print(f"  Steps: {episode_length}")
            print(f"  Total solutions: {len(self.solved_hashes)}")

            # Generate next level
            return self._generate_next_level()
        else:
            # Failed - make it slightly easier
            print(f"\n[CurriculumManager] Level {self.current_level} failed")
            print(f"  Reward: {episode_reward:.2f}")
            print(f"  Steps: {episode_length}")
            print(f"  Making next level easier...")

            return self._generate_easier_level()

    def _generate_next_level(self) -> Tuple[str, int]:
        """
        Generate next level after successful solve

        Strategy:
        1. Reduce difficulty by decay factor
        2. Find nodes near target difficulty
        3. Randomly select from candidates
        4. Avoid recently solved states
        """
        # Increase level
        self.current_level += 1

        # Calculate target difficulty
        target_difficulty = max(
            self.min_difficulty,
            int(self.current_difficulty * self.difficulty_decay)
        )

        # Find candidate nodes near target difficulty
        candidates = self._find_nodes_near_difficulty(
            target_difficulty,
            window=self.difficulty_window
        )

        # Filter out recently solved states
        candidates = [h for h in candidates if h not in self.solved_hashes[-5:]]

        if not candidates:
            # Fallback: use any node at target difficulty
            candidates = self.nodes_by_distance.get(target_difficulty, [])

        if not candidates:
            # Last resort: return to initial start
            print(f"[CurriculumManager] No candidates found, resetting to initial start")
            self.current_start_hash = self.initial_start_hash
            self.current_difficulty = self.initial_difficulty
            return self.initial_start_hash, self.current_level

        # Randomly select new start
        new_start_hash = random.choice(candidates)
        actual_difficulty = self.graph[new_start_hash]['solution_dist']

        self.current_start_hash = new_start_hash
        self.current_difficulty = actual_difficulty

        print(f"[CurriculumManager] Level {self.current_level} generated!")
        print(f"  Target difficulty: {target_difficulty}")
        print(f"  Actual difficulty: {actual_difficulty}")
        print(f"  Candidates: {len(candidates)}")

        return new_start_hash, self.current_level

    def _generate_easier_level(self) -> Tuple[str, int]:
        """
        Generate easier level after failure

        Makes the puzzle easier to maintain training progress
        """
        # Keep same level number (retry)

        # Reduce difficulty more aggressively
        target_difficulty = max(
            self.min_difficulty,
            int(self.current_difficulty * 0.8)  # More aggressive reduction
        )

        # Find easier candidates
        candidates = self._find_nodes_near_difficulty(
            target_difficulty,
            window=self.difficulty_window * 2  # Wider search
        )

        if not candidates:
            candidates = self.nodes_by_distance.get(target_difficulty, [])

        if not candidates:
            # Reset to easier start
            candidates = self.nodes_by_distance.get(self.min_difficulty, [])

        if candidates:
            new_start_hash = random.choice(candidates)
            actual_difficulty = self.graph[new_start_hash]['solution_dist']

            self.current_start_hash = new_start_hash
            self.current_difficulty = actual_difficulty

            print(f"[CurriculumManager] Easier level generated")
            print(f"  Target difficulty: {target_difficulty}")
            print(f"  Actual difficulty: {actual_difficulty}")

        return self.current_start_hash, self.current_level

    def _find_nodes_near_difficulty(
        self,
        target_difficulty: int,
        window: int
    ) -> List[str]:
        """
        Find nodes with solution_dist near target difficulty

        Args:
            target_difficulty: Target solution distance
            window: +/- range to search

        Returns:
            List of node hashes
        """
        candidates = []

        for dist in range(
            max(0, target_difficulty - window),
            min(200, target_difficulty + window + 1)
        ):
            if dist in self.nodes_by_distance:
                candidates.extend(self.nodes_by_distance[dist])

        return candidates

    def get_current_start(self) -> str:
        """Get current level's starting hash"""
        return self.current_start_hash

    def get_statistics(self) -> Dict:
        """Get curriculum statistics"""
        total_attempts = len(self.level_history)
        total_solved = sum(1 for level in self.level_history if level['solved'])

        return {
            'current_level': self.current_level,
            'current_difficulty': self.current_difficulty,
            'total_attempts': total_attempts,
            'total_solved': total_solved,
            'success_rate': (total_solved / total_attempts * 100) if total_attempts > 0 else 0,
            'avg_steps_per_solve': np.mean([
                level['steps'] for level in self.level_history if level['solved']
            ]) if total_solved > 0 else 0,
            'level_history_length': len(self.level_history)
        }

    def save_progress(self, save_path: str):
        """Save curriculum progress to file"""
        save_data = {
            'current_level': self.current_level,
            'current_start_hash': self.current_start_hash,
            'current_difficulty': self.current_difficulty,
            'solved_hashes': self.solved_hashes,
            'level_history': self.level_history
        }

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'w') as f:
            json.dump(save_data, f, indent=2)

        print(f"[CurriculumManager] Progress saved to {save_path}")

    def load_progress(self, load_path: str):
        """Load curriculum progress from file"""
        if not Path(load_path).exists():
            print(f"[CurriculumManager] No saved progress found at {load_path}")
            return

        with open(load_path, 'r') as f:
            save_data = json.load(f)

        self.current_level = save_data['current_level']
        self.current_start_hash = save_data['current_start_hash']
        self.current_difficulty = save_data['current_difficulty']
        self.solved_hashes = save_data['solved_hashes']
        self.level_history = save_data['level_history']

        print(f"[CurriculumManager] Progress loaded from {load_path}")
        print(f"  Resumed at level {self.current_level}")
        print(f"  Total solutions: {len(self.solved_hashes)}")


if __name__ == '__main__':
    # Test curriculum manager
    print("="*80)
    print("TESTING CURRICULUM MANAGER")
    print("="*80)

    # Load graph
    from klotski_graph_env import KlotskiGraphEnv

    env = KlotskiGraphEnv()

    # Create curriculum manager
    curriculum = CurriculumManager(
        graph=env.graph,
        start_hash=env.start_hash,
        initial_difficulty=126,
        min_difficulty=40,
        difficulty_decay=0.95,
        difficulty_window=5
    )

    # Simulate episodes
    print("\nSimulating episodes:")

    for episode in range(10):
        start_hash = curriculum.get_current_start()
        difficulty = env.graph[start_hash]['solution_dist']

        print(f"\nEpisode {episode + 1}:")
        print(f"  Start: {start_hash[:20]}...")
        print(f"  Difficulty: {difficulty}")

        # Simulate episode (50% success rate)
        solved = random.random() > 0.5
        reward = random.uniform(50, 200) if solved else random.uniform(-50, 50)
        steps = random.randint(50, 150)

        # Get next level
        new_start, new_level = curriculum.on_episode_end(
            solved=solved,
            episode_reward=reward,
            episode_length=steps,
            final_hash=start_hash
        )

    # Statistics
    print("\n" + "="*80)
    print("CURRICULUM STATISTICS")
    print("="*80)
    stats = curriculum.get_statistics()
    for key, value in stats.items():
        print(f"{key}: {value}")

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)
