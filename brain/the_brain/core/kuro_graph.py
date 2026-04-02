"""
KuroGraph - Domain-Agnostic Pattern Extraction and Strategy Mining

Extracts high-level strategy patterns from KotlinGraph's episodic data:
- n-gram mining: Find frequent action sequences
- Strategy patterns: Clusters of successful moves
- Pattern-based guidance: Suggest actions based on learned patterns
- Co-occurrence matrix: Track which actions appear together

This is the "semantic memory" of the system - stores what works.

Ported from learning_engine/klotski/neurosymbolic/memory/kurograph.py.
Generalized from int actions + np.ndarray states to str actions + Dict states.
"""

import json
import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass, field
from collections import Counter, defaultdict

from core.kotlin_graph import KotlinGraph, BrainEvent


@dataclass
class ActionNGram:
    """N-gram of actions (sequence pattern)."""
    actions: Tuple[str, ...]       # Sequence of action labels
    frequency: int                  # How often this sequence appears
    avg_reward: float               # Average reward when using this sequence
    success_rate: float             # Fraction of episodes where this led to success
    contexts: List[str] = field(default_factory=list)  # State hashes where used

    def __len__(self) -> int:
        return len(self.actions)

    def __hash__(self) -> int:
        return hash(self.actions)

    def __eq__(self, other) -> bool:
        if not isinstance(other, ActionNGram):
            return NotImplemented
        return self.actions == other.actions


@dataclass
class StrategyPattern:
    """High-level strategy pattern."""
    pattern_id: int
    name: str
    description: str
    ngrams: List[ActionNGram]       # Component n-grams
    total_reward: float             # Total reward from using this pattern
    usage_count: int                # How many times this pattern was used
    success_episodes: List[int]     # Episodes where this appeared in successful runs


class KuroGraph:
    """
    Pattern extraction and strategy mining.

    Mines patterns from KotlinGraph:
    - n-grams: Frequent action sequences
    - Strategies: High-level patterns that lead to success
    - Recommendations: Pattern-based action suggestions
    """

    def __init__(self, kotlingraph: Optional[KotlinGraph] = None):
        self.kotlingraph = kotlingraph

        # n-gram storage: actions tuple -> ActionNGram
        self.ngrams: Dict[Tuple[str, ...], ActionNGram] = {}

        # Strategy patterns
        self.strategies: Dict[int, StrategyPattern] = {}
        self.next_strategy_id: int = 0

        # Action co-occurrence matrix
        self.action_cooccurrence: Dict[Tuple[str, str], int] = defaultdict(int)

        # Statistics
        self.stats: Dict[str, Any] = {
            'total_ngrams': 0,
            'total_strategies': 0,
            'total_patterns_mined': 0,
        }

    def mine_ngrams(
        self,
        n: int = 3,
        min_frequency: int = 2,
        min_reward: float = 0.0,
    ) -> List[ActionNGram]:
        """
        Mine n-grams from KotlinGraph episodes.

        Args:
            n: Length of n-gram.
            min_frequency: Minimum frequency to include.
            min_reward: Minimum average reward to include.

        Returns:
            List of mined n-grams.
        """
        if self.kotlingraph is None:
            return []

        ngram_counter: Counter = Counter()
        ngram_rewards: Dict[Tuple[str, ...], List[float]] = defaultdict(list)
        ngram_episodes: Dict[Tuple[str, ...], Set[int]] = defaultdict(set)
        ngram_contexts: Dict[Tuple[str, ...], List[str]] = defaultdict(list)

        # Extract n-grams from all episodes
        for episode_id, event_ids in self.kotlingraph.episodes.items():
            if len(event_ids) < n:
                continue

            events = [self.kotlingraph.events[eid] for eid in event_ids]

            # Sliding window of size n
            for i in range(len(events) - n + 1):
                window = events[i:i + n]
                actions = tuple(e.action for e in window)
                total_reward = sum(e.reward for e in window)
                context = window[0].state_hash()

                ngram_counter[actions] += 1
                ngram_rewards[actions].append(total_reward)
                ngram_episodes[actions].add(episode_id)
                ngram_contexts[actions].append(context)

        # Create n-gram objects
        mined_ngrams: List[ActionNGram] = []
        for actions, freq in ngram_counter.items():
            if freq < min_frequency:
                continue

            avg_reward = float(np.mean(ngram_rewards[actions]))
            if avg_reward < min_reward:
                continue

            # Compute success rate (appeared in successful episodes)
            episode_set = ngram_episodes[actions]
            successful = sum(
                1 for ep_id in episode_set
                if self.kotlingraph.episodes[ep_id]
                and self.kotlingraph.events[
                    self.kotlingraph.episodes[ep_id][-1]
                ].reward > 0
            )
            success_rate = successful / len(episode_set) if episode_set else 0.0

            ngram = ActionNGram(
                actions=actions,
                frequency=freq,
                avg_reward=avg_reward,
                success_rate=success_rate,
                contexts=ngram_contexts[actions],
            )

            self.ngrams[actions] = ngram
            mined_ngrams.append(ngram)

        self.stats['total_ngrams'] = len(self.ngrams)
        self.stats['total_patterns_mined'] += len(mined_ngrams)

        return mined_ngrams

    def get_best_ngrams(
        self, top_k: int = 10, min_length: int = 2
    ) -> List[ActionNGram]:
        """
        Get best n-grams by reward and frequency.

        Score = avg_reward * log1p(frequency) * (success_rate + 0.1)

        Args:
            top_k: Number of top n-grams to return.
            min_length: Minimum n-gram length.

        Returns:
            List of best n-grams sorted by score descending.
        """
        filtered = [ng for ng in self.ngrams.values() if len(ng) >= min_length]

        scored = [
            (ng, ng.avg_reward * np.log1p(ng.frequency) * (ng.success_rate + 0.1))
            for ng in filtered
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        return [ng for ng, _ in scored[:top_k]]

    def extract_strategies(
        self, min_ngrams: int = 3
    ) -> List[StrategyPattern]:
        """
        Extract high-level strategy patterns from n-grams.

        Groups similar n-grams into strategy patterns by clustering
        on the first action.

        Args:
            min_ngrams: Minimum number of n-grams to form a strategy.

        Returns:
            List of extracted strategies.
        """
        if not self.ngrams:
            return []

        # Get successful n-grams (high reward and success rate)
        successful_ngrams = [
            ng for ng in self.ngrams.values()
            if ng.avg_reward > 0.5 and ng.success_rate > 0.3
        ]

        if len(successful_ngrams) < min_ngrams:
            return []

        # Simple clustering: group by first action
        clusters: Dict[str, List[ActionNGram]] = defaultdict(list)
        for ng in successful_ngrams:
            first_action = ng.actions[0]
            clusters[first_action].append(ng)

        # Create strategy patterns
        new_strategies: List[StrategyPattern] = []
        for first_action, ngram_group in clusters.items():
            if len(ngram_group) < min_ngrams:
                continue

            total_reward = sum(ng.avg_reward * ng.frequency for ng in ngram_group)
            usage_count = sum(ng.frequency for ng in ngram_group)

            # Get episodes where these n-grams appeared
            success_episodes: Set[int] = set()
            for ng in ngram_group:
                for event in self.kotlingraph.events:
                    if event.state_hash() in ng.contexts and event.reward > 0:
                        success_episodes.add(event.episode_id)

            strategy = StrategyPattern(
                pattern_id=self.next_strategy_id,
                name=f"Strategy_{self.next_strategy_id}_Action_{first_action}",
                description=(
                    f"Pattern starting with action '{first_action}', "
                    f"{len(ngram_group)} variants"
                ),
                ngrams=ngram_group,
                total_reward=total_reward,
                usage_count=usage_count,
                success_episodes=list(success_episodes),
            )

            self.strategies[self.next_strategy_id] = strategy
            self.next_strategy_id += 1
            new_strategies.append(strategy)

        self.stats['total_strategies'] = len(self.strategies)

        return new_strategies

    def suggest_action(
        self,
        state: Dict[str, Any],
        recent_actions: List[str],
        top_k: int = 3,
    ) -> List[Tuple[str, float]]:
        """
        Suggest next action based on learned patterns.

        Args:
            state: Current state as a dict.
            recent_actions: Last few actions taken.
            top_k: Number of suggestions to return.

        Returns:
            List of (action, confidence) tuples sorted by confidence descending.
        """
        # No history: return most successful first actions
        if not recent_actions:
            first_action_rewards: Dict[str, List[float]] = defaultdict(list)
            for ng in self.ngrams.values():
                first_action_rewards[ng.actions[0]].append(
                    ng.avg_reward * ng.success_rate
                )

            action_scores = [
                (action, float(np.mean(rewards)))
                for action, rewards in first_action_rewards.items()
            ]
            action_scores.sort(key=lambda x: x[1], reverse=True)
            return action_scores[:top_k]

        # Look for n-grams that start with recent actions
        matching_ngrams: List[Tuple[str, float]] = []
        # Use list() to safely slice (deque gotcha)
        recent_tuple = tuple(list(recent_actions)[-3:])

        for ng in self.ngrams.values():
            if len(ng.actions) > len(recent_tuple):
                if ng.actions[:len(recent_tuple)] == recent_tuple:
                    next_action = ng.actions[len(recent_tuple)]
                    score = ng.avg_reward * np.log1p(ng.frequency) * ng.success_rate
                    matching_ngrams.append((next_action, float(score)))

        if not matching_ngrams:
            # Fallback: suggest based on state
            return self._suggest_from_state(state, top_k)

        # Aggregate scores for each action
        action_scores_map: Dict[str, List[float]] = defaultdict(list)
        for action, score in matching_ngrams:
            action_scores_map[action].append(score)

        aggregated = [
            (action, float(np.mean(scores)))
            for action, scores in action_scores_map.items()
        ]
        aggregated.sort(key=lambda x: x[1], reverse=True)

        return aggregated[:top_k]

    def _suggest_from_state(
        self, state: Dict[str, Any], top_k: int
    ) -> List[Tuple[str, float]]:
        """Fallback suggestion based on state similarity."""
        state_hash = str(
            hash(json.dumps(state, sort_keys=True, default=str))
        )

        action_scores: Dict[str, List[float]] = defaultdict(list)
        for ng in self.ngrams.values():
            if state_hash in ng.contexts:
                for action in ng.actions:
                    action_scores[action].append(ng.avg_reward * ng.success_rate)

        if not action_scores:
            return []

        aggregated = [
            (action, float(np.mean(scores)))
            for action, scores in action_scores.items()
        ]
        aggregated.sort(key=lambda x: x[1], reverse=True)

        return aggregated[:top_k]

    def build_cooccurrence_matrix(self, window_size: int = 5) -> None:
        """
        Build action co-occurrence matrix.

        Tracks which actions tend to appear together within a sliding window.

        Args:
            window_size: Size of the sliding window.
        """
        if self.kotlingraph is None:
            return

        self.action_cooccurrence.clear()

        for episode_id, event_ids in self.kotlingraph.episodes.items():
            events = [self.kotlingraph.events[eid] for eid in event_ids]
            actions = [e.action for e in events]

            # Sliding window
            for i in range(len(actions)):
                for j in range(i + 1, min(i + window_size, len(actions))):
                    pair = (actions[i], actions[j])
                    self.action_cooccurrence[pair] += 1

    def get_statistics(self) -> Dict[str, Any]:
        """Get KuroGraph statistics."""
        stats = dict(self.stats)

        if self.ngrams:
            ngram_lengths = [len(ng) for ng in self.ngrams.values()]
            stats['avg_ngram_length'] = float(np.mean(ngram_lengths))
            stats['max_ngram_length'] = max(ngram_lengths)

            rewards = [ng.avg_reward for ng in self.ngrams.values()]
            stats['avg_pattern_reward'] = float(np.mean(rewards))

        if self.strategies:
            per_use_rewards = [
                s.total_reward / s.usage_count
                for s in self.strategies.values()
                if s.usage_count > 0
            ]
            if per_use_rewards:
                stats['avg_strategy_reward'] = float(np.mean(per_use_rewards))

        return stats

    def save(self, filepath: str) -> None:
        """Save KuroGraph to disk as JSON."""
        data = {
            'ngrams': [
                {
                    'actions': list(ng.actions),
                    'frequency': ng.frequency,
                    'avg_reward': ng.avg_reward,
                    'success_rate': ng.success_rate,
                    'contexts': ng.contexts,
                }
                for ng in self.ngrams.values()
            ],
            'strategies': [
                {
                    'pattern_id': s.pattern_id,
                    'name': s.name,
                    'description': s.description,
                    'total_reward': s.total_reward,
                    'usage_count': s.usage_count,
                    'success_episodes': s.success_episodes,
                    'ngrams': [list(ng.actions) for ng in s.ngrams],
                }
                for s in self.strategies.values()
            ],
            'action_cooccurrence': [
                {'pair': [k[0], k[1]], 'count': v}
                for k, v in self.action_cooccurrence.items()
            ],
            'next_strategy_id': self.next_strategy_id,
            'stats': self.stats,
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    def load(self, filepath: str) -> None:
        """Load KuroGraph from disk."""
        with open(filepath, 'r') as f:
            data = json.load(f)

        # Load n-grams
        self.ngrams = {
            tuple(ng_data['actions']): ActionNGram(
                actions=tuple(ng_data['actions']),
                frequency=ng_data['frequency'],
                avg_reward=ng_data['avg_reward'],
                success_rate=ng_data['success_rate'],
                contexts=ng_data['contexts'],
            )
            for ng_data in data['ngrams']
        }

        # Load strategies (reconstruct n-gram references where possible)
        self.strategies = {}
        for s_data in data['strategies']:
            ngrams = [
                self.ngrams.get(
                    tuple(actions),
                    ActionNGram(tuple(actions), 0, 0.0, 0.0),
                )
                for actions in s_data['ngrams']
            ]

            strategy = StrategyPattern(
                pattern_id=s_data['pattern_id'],
                name=s_data['name'],
                description=s_data['description'],
                ngrams=ngrams,
                total_reward=s_data['total_reward'],
                usage_count=s_data['usage_count'],
                success_episodes=s_data['success_episodes'],
            )
            self.strategies[s_data['pattern_id']] = strategy

        # Load co-occurrence (stored as list of {pair: [a, b], count: n})
        self.action_cooccurrence = defaultdict(int)
        for entry in data['action_cooccurrence']:
            pair = tuple(entry['pair'])
            self.action_cooccurrence[pair] = entry['count']

        self.next_strategy_id = data['next_strategy_id']
        self.stats = data['stats']

    # ── Cluster Overlay (Meta-Knowledge Graph) ───────────────────

    def set_cluster_overlay(self, clusters: List[Dict[str, Any]]):
        """Overlay cluster density data onto the pattern space.

        Each cluster becomes a 'semantic areal' in the KuroGraph —
        more points = more knowledge in that domain.

        Args:
            clusters: List of dicts with cluster_id, dominant_topic, size,
                      avg_fitness, coherence, connections
        """
        self.cluster_overlay = {
            c['cluster_id']: {
                'topic': c['dominant_topic'],
                'size': c['size'],
                'avg_fitness': c.get('avg_fitness', 0.0),
                'coherence': c.get('coherence', 0.0),
                'connections': c.get('connections', 0),
            }
            for c in clusters
        }
        self.stats['total_cluster_areals'] = len(clusters)

    def get_cluster_overlay(self) -> Dict[int, Dict[str, Any]]:
        """Return current cluster overlay for visualization."""
        return getattr(self, 'cluster_overlay', {})
