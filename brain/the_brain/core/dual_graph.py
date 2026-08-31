"""
DualGraph - Domain-Agnostic Dual-Graph Memory Manager

Coordinates KotlinGraph and KuroGraph as a unified memory system:
- Records events to KotlinGraph (episodic memory / raw storage)
- Periodically mines patterns into KuroGraph (semantic memory / pattern extraction)
- Provides unified API for memory operations (suggest_actions, get_statistics, etc.)

Ported from learning_engine/klotski/neurosymbolic/memory/dual_graph_manager.py.
Changes from original:
- Class name: DualGraphManager -> DualGraph
- Imports from core.kotlin_graph and core.kuro_graph
- States are Dict[str, Any] instead of np.ndarray
- Actions are str instead of int
- print() replaced with logging
- Removed if __name__ == '__main__' test block
"""

import logging
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path

from core.kotlin_graph import KotlinGraph, BrainEvent
from core.kuro_graph import KuroGraph, ActionNGram, StrategyPattern

logger = logging.getLogger('brain.dual_graph')


class DualGraph:
    """
    Unified manager for dual-graph memory system.

    Workflow:
    1. Record events -> KotlinGraph (raw storage)
    2. Periodically mine patterns -> KuroGraph (pattern extraction)
    3. Use patterns to guide policy (action suggestions)
    """

    def __init__(
        self,
        save_dir: str = "./memory",
        auto_mine_interval: int = 10,  # Mine patterns every N episodes
    ):
        """
        Args:
            save_dir: Directory to save graphs.
            auto_mine_interval: How often to mine patterns (in episodes).
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
        self.stats: Dict[str, Any] = {
            'total_events_recorded': 0,
            'total_patterns_mined': 0,
            'last_mine_episode': 0,
        }

    def record_event(
        self,
        state: Dict[str, Any],
        action: str,
        next_state: Dict[str, Any],
        reward: float,
        done: bool,
        value: float = 0.0,
        policy_entropy: float = 0.0,
        consciousness: float = 0.0,
        dmn_energy: float = 0.0,
        metadata: Optional[Dict] = None,
    ) -> int:
        """
        Record a brain event.

        Args:
            state: Current state snapshot (arbitrary dict).
            action: Action label (str).
            next_state: Resulting state snapshot.
            reward: Reward received.
            done: Episode termination flag.
            value: Value estimate from brain.
            policy_entropy: Policy entropy.
            consciousness: Consciousness metric.
            dmn_energy: DMN energy.
            metadata: Additional metadata.

        Returns:
            event_id: ID of the recorded event.
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
            metadata=metadata,
        )

        self.stats['total_events_recorded'] += 1

        # Check if we should mine patterns
        if done:
            self.episodes_since_last_mine += 1

            if self.episodes_since_last_mine >= self.auto_mine_interval:
                self._auto_mine()

        return event_id

    def _auto_mine(self) -> None:
        """Automatically mine patterns from KotlinGraph."""
        logger.info(
            "Auto-mining patterns (episode %d)...",
            self.kotlingraph.current_episode_id,
        )

        # Mine n-grams of different lengths
        ngrams = []
        for n in [2, 3, 4, 5]:
            found = self.kurograph.mine_ngrams(
                n=n,
                min_frequency=2,
                min_reward=0.0,
            )
            self.stats['total_patterns_mined'] += len(found)
            ngrams = found  # keep last for logging

        # Extract strategies
        strategies = self.kurograph.extract_strategies(min_ngrams=2)
        logger.info(
            "  Found %d n-grams, %d strategies",
            len(ngrams),
            len(strategies),
        )

        # Build co-occurrence matrix
        self.kurograph.build_cooccurrence_matrix(window_size=5)

        self.episodes_since_last_mine = 0
        self.stats['last_mine_episode'] = self.kotlingraph.current_episode_id

    def force_mine(self) -> None:
        """Force pattern mining immediately."""
        self._auto_mine()

    def suggest_actions(
        self,
        state: Dict[str, Any],
        recent_actions: List[str],
        top_k: int = 3,
    ) -> List[Tuple[str, float]]:
        """
        Get action suggestions from learned patterns.

        Args:
            state: Current state.
            recent_actions: Recent action history.
            top_k: Number of suggestions.

        Returns:
            List of (action, confidence) tuples.
        """
        return self.kurograph.suggest_action(state, recent_actions, top_k)

    def get_episode_trajectory(
        self, episode_id: int
    ) -> Tuple[List[Dict[str, Any]], List[str], List[float]]:
        """Get full episode trajectory from KotlinGraph."""
        return self.kotlingraph.get_episode_trajectory(episode_id)

    def get_best_patterns(self, top_k: int = 10) -> List[ActionNGram]:
        """Get best learned patterns from KuroGraph."""
        return self.kurograph.get_best_ngrams(top_k=top_k)

    def get_strategies(self) -> List[StrategyPattern]:
        """Get all extracted strategies."""
        return list(self.kurograph.strategies.values())

    def get_statistics(self) -> Dict[str, Any]:
        """Get combined statistics from both graphs."""
        stats = self.stats.copy()
        stats['kotlingraph'] = self.kotlingraph.get_statistics()
        stats['kurograph'] = self.kurograph.get_statistics()
        return stats

    def save(self, name: str = "memory") -> None:
        """
        Save both graphs to disk.

        Args:
            name: Base name for saved files.
        """
        kotlingraph_path = self.save_dir / f"{name}_kotlingraph.json"
        kurograph_path = self.save_dir / f"{name}_kurograph.json"

        self.kotlingraph.save(str(kotlingraph_path))
        self.kurograph.save(str(kurograph_path))

        logger.info("Saved memory to %s/", self.save_dir)
        logger.debug("  KotlinGraph: %s", kotlingraph_path.name)
        logger.debug("  KuroGraph: %s", kurograph_path.name)

    def load(self, name: str = "memory") -> bool:
        """
        Load both graphs from disk.

        Args:
            name: Base name of saved files.

        Returns:
            True if load succeeded, False if files not found.
        """
        kotlingraph_path = self.save_dir / f"{name}_kotlingraph.json"
        kurograph_path = self.save_dir / f"{name}_kurograph.json"

        if not kotlingraph_path.exists():
            logger.warning("%s not found", kotlingraph_path)
            return False

        if not kurograph_path.exists():
            logger.warning("%s not found", kurograph_path)
            return False

        self.kotlingraph.load(str(kotlingraph_path))
        self.kurograph.load(str(kurograph_path))

        # Reconnect KuroGraph to KotlinGraph
        self.kurograph.kotlingraph = self.kotlingraph

        logger.info("Loaded memory from %s/", self.save_dir)
        logger.info(
            "  Events: %d, Episodes: %d, Patterns: %d, Strategies: %d",
            self.kotlingraph.stats['total_events'],
            self.kotlingraph.stats['total_episodes'],
            self.kurograph.stats['total_ngrams'],
            self.kurograph.stats['total_strategies'],
        )

        return True

    def clear(self) -> None:
        """Clear all data from both graphs."""
        self.kotlingraph.clear()
        self.kurograph = KuroGraph(kotlingraph=self.kotlingraph)
        self.episodes_since_last_mine = 0
        self.stats = {
            'total_events_recorded': 0,
            'total_patterns_mined': 0,
            'last_mine_episode': 0,
        }

    def export_patterns_for_training(self) -> Dict[str, Any]:
        """
        Export patterns in format suitable for training.

        Returns:
            Dictionary with patterns, strategies, and statistics.
        """
        best_ngrams = self.get_best_patterns(top_k=20)

        return {
            'ngrams': [
                {
                    'actions': list(ng.actions),
                    'frequency': ng.frequency,
                    'avg_reward': ng.avg_reward,
                    'success_rate': ng.success_rate,
                }
                for ng in best_ngrams
            ],
            'strategies': [
                {
                    'name': s.name,
                    'description': s.description,
                    'total_reward': s.total_reward,
                    'usage_count': s.usage_count,
                    'success_episodes': len(s.success_episodes),
                }
                for s in self.get_strategies()
            ],
            'statistics': self.get_statistics(),
        }

    def analyze_episode(self, episode_id: int) -> Dict[str, Any]:
        """
        Analyze an episode using both graphs.

        Returns:
            Analysis with trajectory, patterns used, and insights.
        """
        if episode_id not in self.kotlingraph.episodes:
            return {'error': f'Episode {episode_id} not found'}

        events = self.kotlingraph.get_episode(episode_id)
        states, actions, rewards = self.kotlingraph.get_episode_trajectory(episode_id)

        # Find which patterns appeared in this episode
        episode_actions = tuple(actions)
        patterns_used = []

        for ng in self.kurograph.ngrams.values():
            ng_actions = ng.actions
            for i in range(len(episode_actions) - len(ng_actions) + 1):
                if episode_actions[i:i + len(ng_actions)] == ng_actions:
                    patterns_used.append({
                        'actions': list(ng.actions),
                        'position': i,
                        'reward': ng.avg_reward,
                        'frequency': ng.frequency,
                    })
                    break

        return {
            'episode_id': episode_id,
            'length': len(events),
            'total_reward': sum(rewards),
            'success': events[-1].reward > 0 if events else False,
            'patterns_used': patterns_used,
            'avg_consciousness': float(np.mean([e.consciousness for e in events])),
            'avg_value': float(np.mean([e.value for e in events])),
        }
