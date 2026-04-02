"""
Dual-Graph Manager

Coordinates KotlinGraph and KuroGraph:
- Records events to KotlinGraph
- Periodically mines patterns into KuroGraph
- Provides unified interface for memory operations
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path

from .kotlingraph import KotlinGraph, GameEvent
from .kurograph import KuroGraph, ActionNGram, StrategyPattern


class DualGraphManager:
    """
    Unified manager for dual-graph memory system

    Workflow:
    1. Record gameplay events → KotlinGraph (raw storage)
    2. Periodically mine patterns → KuroGraph (pattern extraction)
    3. Use patterns to guide policy (action suggestions)
    """

    def __init__(
        self,
        save_dir: str = "./memory",
        auto_mine_interval: int = 10  # Mine patterns every N episodes
    ):
        """
        Args:
            save_dir: Directory to save graphs
            auto_mine_interval: How often to mine patterns (in episodes)
        """
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        # Initialize graphs
        self.kotlingraph = KotlinGraph()
        self.kurograph = KuroGraph(kotlingraph=self.kotlingraph)

        # Auto-mining configuration
        self.auto_mine_interval = auto_mine_interval
        self.episodes_since_last_mine = 0

        # Statistics
        self.stats = {
            'total_events_recorded': 0,
            'total_patterns_mined': 0,
            'last_mine_episode': 0
        }

    def record_event(
        self,
        state: np.ndarray,
        action: int,
        next_state: np.ndarray,
        reward: float,
        done: bool,
        value: float = 0.0,
        policy_entropy: float = 0.0,
        consciousness: float = 0.0,
        dmn_energy: float = 0.0,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Record a gameplay event

        Args:
            state: Current board state
            action: Action taken
            next_state: Resulting state
            reward: Reward received
            done: Episode termination flag
            value: Value estimate from brain
            policy_entropy: Policy entropy
            consciousness: Consciousness metric
            dmn_energy: DMN energy
            metadata: Additional metadata

        Returns:
            event_id: ID of recorded event
        """
        event_id = self.kotlingraph.add_event(
            state=state,
            action=action,
            next_state=next_state,
            reward=reward,
            done=done,
            value=value,
            policy_entropy=policy_entropy,
            consciousness=consciousness,
            dmn_energy=dmn_energy,
            metadata=metadata
        )

        self.stats['total_events_recorded'] += 1

        # Check if we should mine patterns
        if done:
            self.episodes_since_last_mine += 1

            if self.episodes_since_last_mine >= self.auto_mine_interval:
                self._auto_mine()

        return event_id

    def _auto_mine(self):
        """Automatically mine patterns from KotlinGraph"""
        print(f"Auto-mining patterns (episode {self.kotlingraph.current_episode_id})...")

        # Mine n-grams of different lengths
        for n in [2, 3, 4, 5]:
            ngrams = self.kurograph.mine_ngrams(
                n=n,
                min_frequency=2,
                min_reward=0.0
            )
            self.stats['total_patterns_mined'] += len(ngrams)

        # Extract strategies
        strategies = self.kurograph.extract_strategies(min_ngrams=2)
        print(f"  Found {len(ngrams)} n-grams, {len(strategies)} strategies")

        # Build co-occurrence matrix
        self.kurograph.build_cooccurrence_matrix(window_size=5)

        self.episodes_since_last_mine = 0
        self.stats['last_mine_episode'] = self.kotlingraph.current_episode_id

    def force_mine(self):
        """Force pattern mining immediately"""
        self._auto_mine()

    def suggest_actions(
        self,
        state: np.ndarray,
        recent_actions: List[int],
        top_k: int = 3
    ) -> List[Tuple[int, float]]:
        """
        Get action suggestions from learned patterns

        Args:
            state: Current state
            recent_actions: Recent action history
            top_k: Number of suggestions

        Returns:
            List of (action, confidence) tuples
        """
        return self.kurograph.suggest_action(state, recent_actions, top_k)

    def get_episode_trajectory(self, episode_id: int) -> Tuple[List[np.ndarray], List[int], List[float]]:
        """Get full episode trajectory from KotlinGraph"""
        return self.kotlingraph.get_episode_trajectory(episode_id)

    def get_best_patterns(self, top_k: int = 10) -> List[ActionNGram]:
        """Get best learned patterns from KuroGraph"""
        return self.kurograph.get_best_ngrams(top_k=top_k)

    def get_strategies(self) -> List[StrategyPattern]:
        """Get all extracted strategies"""
        return list(self.kurograph.strategies.values())

    def get_statistics(self) -> Dict[str, Any]:
        """Get combined statistics from both graphs"""
        stats = self.stats.copy()
        stats['kotlingraph'] = self.kotlingraph.get_statistics()
        stats['kurograph'] = self.kurograph.get_statistics()
        return stats

    def save(self, name: str = "memory"):
        """
        Save both graphs to disk

        Args:
            name: Base name for saved files
        """
        kotlingraph_path = self.save_dir / f"{name}_kotlingraph.json"
        kurograph_path = self.save_dir / f"{name}_kurograph.json"

        self.kotlingraph.save(str(kotlingraph_path))
        self.kurograph.save(str(kurograph_path))

        print(f"Saved memory to {self.save_dir}/")
        print(f"  KotlinGraph: {kotlingraph_path.name}")
        print(f"  KuroGraph: {kurograph_path.name}")

    def load(self, name: str = "memory"):
        """
        Load both graphs from disk

        Args:
            name: Base name of saved files
        """
        kotlingraph_path = self.save_dir / f"{name}_kotlingraph.json"
        kurograph_path = self.save_dir / f"{name}_kurograph.json"

        if not kotlingraph_path.exists():
            print(f"Warning: {kotlingraph_path} not found")
            return False

        if not kurograph_path.exists():
            print(f"Warning: {kurograph_path} not found")
            return False

        self.kotlingraph.load(str(kotlingraph_path))
        self.kurograph.load(str(kurograph_path))

        # Reconnect KuroGraph to KotlinGraph
        self.kurograph.kotlingraph = self.kotlingraph

        print(f"Loaded memory from {self.save_dir}/")
        print(f"  Events: {self.kotlingraph.stats['total_events']}")
        print(f"  Episodes: {self.kotlingraph.stats['total_episodes']}")
        print(f"  Patterns: {self.kurograph.stats['total_ngrams']}")
        print(f"  Strategies: {self.kurograph.stats['total_strategies']}")

        return True

    def clear(self):
        """Clear all data from both graphs"""
        self.kotlingraph.clear()
        self.kurograph = KuroGraph(kotlingraph=self.kotlingraph)
        self.episodes_since_last_mine = 0
        self.stats = {
            'total_events_recorded': 0,
            'total_patterns_mined': 0,
            'last_mine_episode': 0
        }

    def export_patterns_for_training(self) -> Dict[str, Any]:
        """
        Export patterns in format suitable for training

        Returns:
            Dictionary with patterns, strategies, and statistics
        """
        best_ngrams = self.get_best_patterns(top_k=20)

        return {
            'ngrams': [
                {
                    'actions': list(ng.actions),
                    'frequency': ng.frequency,
                    'avg_reward': ng.avg_reward,
                    'success_rate': ng.success_rate
                }
                for ng in best_ngrams
            ],
            'strategies': [
                {
                    'name': s.name,
                    'description': s.description,
                    'total_reward': s.total_reward,
                    'usage_count': s.usage_count,
                    'success_episodes': len(s.success_episodes)
                }
                for s in self.get_strategies()
            ],
            'statistics': self.get_statistics()
        }

    def analyze_episode(self, episode_id: int) -> Dict[str, Any]:
        """
        Analyze an episode using both graphs

        Returns:
            Analysis with trajectory, patterns used, and insights
        """
        if episode_id not in self.kotlingraph.episodes:
            return {'error': f'Episode {episode_id} not found'}

        events = self.kotlingraph.get_episode(episode_id)
        states, actions, rewards = self.kotlingraph.get_episode_trajectory(episode_id)

        # Find which patterns appeared in this episode
        episode_actions = tuple(actions)
        patterns_used = []

        for ng in self.kurograph.ngrams.values():
            # Check if n-gram appears in episode
            ng_actions = ng.actions
            for i in range(len(episode_actions) - len(ng_actions) + 1):
                if episode_actions[i:i+len(ng_actions)] == ng_actions:
                    patterns_used.append({
                        'actions': list(ng.actions),
                        'position': i,
                        'reward': ng.avg_reward,
                        'frequency': ng.frequency
                    })
                    break

        return {
            'episode_id': episode_id,
            'length': len(events),
            'total_reward': sum(rewards),
            'success': events[-1].reward > 0 if events else False,
            'patterns_used': patterns_used,
            'avg_consciousness': np.mean([e.consciousness for e in events]),
            'avg_value': np.mean([e.value for e in events])
        }


if __name__ == '__main__':
    # Test DualGraphManager
    print("Testing DualGraphManager...")
    print("="*60)

    manager = DualGraphManager(save_dir="./test_memory", auto_mine_interval=3)

    # Simulate 5 episodes
    for episode in range(5):
        print(f"\nEpisode {episode}:")

        for step in range(8):
            state = np.random.randint(0, 10, size=(4, 5))
            # Use repeating pattern [1, 2, 3]
            action = (step % 3) + 1
            next_state = np.random.randint(0, 10, size=(4, 5))
            reward = 1.0 if step == 7 else 0.1
            done = (step == 7)

            manager.record_event(
                state=state,
                action=action,
                next_state=next_state,
                reward=reward,
                done=done,
                value=np.random.rand(),
                consciousness=np.random.rand()
            )

        print(f"  Recorded {step + 1} events")

    # Get statistics
    print("\n" + "="*60)
    print("Statistics:")
    stats = manager.get_statistics()
    print(f"  Total events: {stats['total_events_recorded']}")
    print(f"  Patterns mined: {stats['total_patterns_mined']}")
    print(f"  Episodes: {stats['kotlingraph']['total_episodes']}")
    print(f"  Unique states: {stats['kotlingraph']['total_states']}")
    print(f"  N-grams found: {stats['kurograph']['total_ngrams']}")
    print(f"  Strategies: {stats['kurograph']['total_strategies']}")

    # Get best patterns
    print("\nBest Patterns:")
    best = manager.get_best_patterns(top_k=5)
    for ng in best:
        print(f"  {ng.actions} - reward: {ng.avg_reward:.2f}, freq: {ng.frequency}")

    # Test action suggestion
    print("\nAction Suggestions:")
    state = np.random.randint(0, 10, size=(4, 5))
    suggestions = manager.suggest_actions(state, recent_actions=[1, 2], top_k=3)
    print(f"  Given recent actions [1, 2]:")
    for action, confidence in suggestions:
        print(f"    Action {action}: confidence {confidence:.3f}")

    # Analyze an episode
    print("\nEpisode Analysis:")
    analysis = manager.analyze_episode(0)
    print(f"  Episode 0:")
    print(f"    Length: {analysis['length']}")
    print(f"    Total reward: {analysis['total_reward']:.2f}")
    print(f"    Success: {analysis['success']}")
    print(f"    Patterns used: {len(analysis['patterns_used'])}")

    # Save and load
    print("\n" + "="*60)
    manager.save("test")

    manager2 = DualGraphManager(save_dir="./test_memory")
    success = manager2.load("test")
    print(f"Load successful: {success}")

    print("\n" + "="*60)
    print("[OK] DualGraphManager test passed!")
