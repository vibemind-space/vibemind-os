"""
KotlinGraph - Domain-Agnostic Episodic Memory

Stores all brain events as a directed graph:
- Nodes: States (arbitrary Dict[str, Any] snapshots)
- Edges: Actions (state transitions with str action labels)
- Metadata: Rewards, timestamps, brain activation metrics

This is the "episodic memory" of the system - stores everything that happened.

Ported from learning_engine/klotski/neurosymbolic/memory/kotlingraph.py.
Generalized from np.ndarray states + int actions to Dict[str, Any] states + str actions.
Removed torch dependency entirely.
"""

import json
import os
import threading
import time

import networkx as nx
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime


def atomic_write_json(filepath: str, data: Any, **dump_kwargs: Any) -> None:
    """Write `data` as JSON to `filepath` CRASH-SAFELY.

    A plain `open(filepath, 'w')` TRUNCATES the destination before the first
    byte is written, so a crash/kill mid-save leaves a fragment — for the
    episodic diary that means the WHOLE memory file is destroyed, not one
    episode. Here the bytes go to a temp file, are fsync'd (really on disk),
    and only then atomically renamed over the destination. The destination is
    therefore always either the old complete file or the new complete file.

    The temp name is UNIQUE PER WRITER (pid + thread id): MemoryConsolidator
    and the diary drain save the same graph from different threads, and a
    shared "<dest>.tmp" would let one rename the other's half-written bytes
    onto the destination — reintroducing the very corruption we remove.
    """
    tmp = f"{filepath}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, **dump_kwargs)
            f.flush()
            os.fsync(f.fileno())      # durable BEFORE the rename
        # os.replace is atomic on POSIX and Windows. On WINDOWS only, it
        # fails with PermissionError if a reader currently holds the
        # destination open (POSIX readers just keep the old inode). That is a
        # transient sharing violation, not corruption — retry briefly.
        for attempt in range(5):
            try:
                os.replace(tmp, filepath)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)
    except BaseException:
        # Failed write -> drop the half-built tmp. The destination is
        # untouched and still holds the last complete save.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@dataclass
class BrainEvent:
    """Single brain event - domain-agnostic."""
    event_id: int
    timestamp: str
    state: Dict[str, Any]       # Arbitrary state snapshot
    action: str                  # Action label
    next_state: Dict[str, Any]  # Resulting state snapshot
    reward: float
    done: bool

    # Brain metrics
    value: float = 0.0
    policy_entropy: float = 0.0
    consciousness: float = 0.0
    dmn_energy: float = 0.0

    # Episode info
    episode_id: int = 0
    step_in_episode: int = 0

    # Optional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def state_hash(self) -> str:
        """Create deterministic hash of state for graph indexing.

        Uses json.dumps with sort_keys=True and default=str to ensure
        deterministic serialization regardless of dict key insertion order
        and to handle non-standard types (datetime, etc.).
        """
        serialized = json.dumps(self.state, sort_keys=True, default=str)
        return str(hash(serialized))

    def next_state_hash(self) -> str:
        """Create deterministic hash of next_state."""
        serialized = json.dumps(self.next_state, sort_keys=True, default=str)
        return str(hash(serialized))


class KotlinGraph:
    """
    Domain-agnostic episodic memory graph.

    Stores all brain events in a directed graph structure:
    - Nodes represent unique states (Dict[str, Any])
    - Edges represent state transitions (str actions)
    - Full history of all episodes preserved

    This is a generalized version of the Klotski-specific KotlinGraph,
    now working with arbitrary dict states and string actions instead of
    numpy arrays and integer actions.
    """

    def __init__(self):
        # KG-C2 (Phase 0): add_event is called from parallel _exec_hop worker
        # threads (plan_executor ThreadPoolExecutor). ID allocation, graph
        # mutation and the done=True episode close must be ONE critical
        # section — RLock (re-entrant) like plan_executor's own locks.
        self._lock = threading.RLock()
        self.graph = nx.MultiDiGraph()  # Multi-graph allows duplicate edges

        # Event log (chronological)
        self.events: List[BrainEvent] = []

        # State index (hash -> node_id)
        self.state_index: Dict[str, int] = {}
        self.next_node_id: int = 0

        # Episode tracking
        self.episodes: Dict[int, List[int]] = {}  # episode_id -> [event_ids]
        self.current_episode_id: int = 0

        # Statistics
        self.stats: Dict[str, int] = {
            'total_events': 0,
            'total_episodes': 0,
            'total_states': 0,
            'total_transitions': 0,
        }

    def add_event(
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
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Add a brain event to the graph.

        Args:
            state: Current state as a dict.
            action: Action label (str).
            next_state: Resulting state as a dict.
            reward: Reward received.
            done: Whether this ends an episode.
            value: Value estimate (brain metric).
            policy_entropy: Policy entropy (brain metric).
            consciousness: Consciousness level (brain metric).
            dmn_energy: Default-mode network energy (brain metric).
            metadata: Optional extra metadata dict.

        Returns:
            event_id: Sequential ID of the added event.

        Caller contract for `done` on TASK episodes (KG-C3, Phase 0):
            done=True closes the episode and MUST only be passed when ALL
            three hold — use `KotlinGraph.is_episode_done(...)` to decide:
              (1) this is the LAST hop of the plan,
              (2) if a truth-validator ran, it PASSED
                  (verdict `verified is True`; no validator = vacuously
                  satisfied; `verified is None` = NOT passed), and
              (3) ZERO further hops are pending/queued.
            KuroGraph mines success-patterns per episode — a wrong done
            boundary poisons every pattern that touches the episode.
        """
        # KG-C2: one critical section — event-ID allocation, graph/state-index
        # mutation, episode membership AND the done-triggered episode close
        # must not interleave across hop threads (observed: 85/200 duplicate
        # event_ids under an 8-thread batch before the lock).
        with self._lock:
            event_id = len(self.events)
            event = BrainEvent(
                event_id=event_id,
                timestamp=datetime.now().isoformat(),
                state=state,
                action=action,
                next_state=next_state,
                reward=reward,
                done=done,
                value=value,
                policy_entropy=policy_entropy,
                consciousness=consciousness,
                dmn_energy=dmn_energy,
                episode_id=self.current_episode_id,
                step_in_episode=len(self.episodes.get(self.current_episode_id, [])),
                metadata=metadata or {},
            )

            self.events.append(event)

            # Add states as graph nodes if new
            s_hash = event.state_hash()
            ns_hash = event.next_state_hash()

            if s_hash not in self.state_index:
                node_id = self.next_node_id
                self.next_node_id += 1
                self.state_index[s_hash] = node_id
                self.graph.add_node(
                    node_id,
                    state=state,
                    state_hash=s_hash,
                    first_seen=event.timestamp,
                    visit_count=0,
                )
                self.stats['total_states'] += 1

            if ns_hash not in self.state_index:
                node_id = self.next_node_id
                self.next_node_id += 1
                self.state_index[ns_hash] = node_id
                self.graph.add_node(
                    node_id,
                    state=next_state,
                    state_hash=ns_hash,
                    first_seen=event.timestamp,
                    visit_count=0,
                )
                self.stats['total_states'] += 1

            # Get node IDs for this transition
            from_node = self.state_index[s_hash]
            to_node = self.state_index[ns_hash]

            # Update visit count on source node
            self.graph.nodes[from_node]['visit_count'] += 1

            # Add directed edge (transition)
            self.graph.add_edge(
                from_node,
                to_node,
                event_id=event_id,
                action=action,
                reward=reward,
                timestamp=event.timestamp,
                value=value,
                consciousness=consciousness,
                episode_id=self.current_episode_id,
            )
            self.stats['total_transitions'] += 1

            # Track episode membership
            if self.current_episode_id not in self.episodes:
                self.episodes[self.current_episode_id] = []
            self.episodes[self.current_episode_id].append(event_id)

            # Advance episode counter when done
            if done:
                self.stats['total_episodes'] += 1
                self.current_episode_id += 1

            self.stats['total_events'] += 1
            return event_id

    @staticmethod
    def is_episode_done(
        is_last_hop: bool,
        validator_present: bool,
        validator_passed: Optional[bool],
        pending_hops: int,
    ) -> bool:
        """KG-C3 (Phase 0) — the 3-condition rule for task-episode `done`.

        Centralizes the caller contract (see add_event docstring) for the
        multihop ingest adapter: True only when (1) last hop, (2) validator
        passed if one was present (None = unobserved = NOT passed), and
        (3) no pending hops. Pure function, no state."""
        if not is_last_hop or pending_hops > 0:
            return False
        if validator_present:
            return validator_passed is True
        return True

    def get_event(self, event_id: int) -> BrainEvent:
        """Get event by ID."""
        return self.events[event_id]

    def get_episode(self, episode_id: int) -> List[BrainEvent]:
        """Get all events in an episode."""
        event_ids = self.episodes.get(episode_id, [])
        return [self.events[eid] for eid in event_ids]

    def get_episode_trajectory(
        self, episode_id: int
    ) -> Tuple[List[Dict[str, Any]], List[str], List[float]]:
        """
        Get episode as (states, actions, rewards) trajectory.

        Returns:
            states: List of state dicts.
            actions: List of action strings.
            rewards: List of reward floats.
        """
        events = self.get_episode(episode_id)
        states = [e.state for e in events]
        actions = [e.action for e in events]
        rewards = [e.reward for e in events]
        return states, actions, rewards

    def get_state_transitions(
        self, state_hash: str
    ) -> List[Tuple[str, int, float]]:
        """
        Get all transitions from a state.

        Args:
            state_hash: Hash of the source state (from BrainEvent.state_hash()).

        Returns:
            List of (action, next_node_id, avg_reward) tuples.
        """
        if state_hash not in self.state_index:
            return []

        node_id = self.state_index[state_hash]
        action_data: Dict[str, Dict[str, Any]] = {}

        for _, to_node, edge_data in self.graph.out_edges(node_id, data=True):
            action = edge_data['action']
            reward = edge_data['reward']
            if action not in action_data:
                action_data[action] = {'to_node': to_node, 'rewards': []}
            action_data[action]['rewards'].append(reward)

        transitions = []
        for action, data in action_data.items():
            avg_reward = float(np.mean(data['rewards']))
            transitions.append((action, data['to_node'], avg_reward))

        return transitions

    def get_most_visited_states(self, top_k: int = 10) -> List[Tuple[int, int]]:
        """
        Get most frequently visited states.

        Returns:
            List of (node_id, visit_count) tuples, sorted descending.
        """
        visits = [
            (nid, data['visit_count'])
            for nid, data in self.graph.nodes(data=True)
        ]
        visits.sort(key=lambda x: x[1], reverse=True)
        return visits[:top_k]

    def get_best_actions_from_state(
        self, state: Dict[str, Any], top_k: int = 3
    ) -> List[Tuple[str, float]]:
        """
        Get best actions from a state based on historical rewards.

        Args:
            state: State dict to query from.
            top_k: Number of top actions to return.

        Returns:
            List of (action, avg_reward) tuples, sorted by reward descending.
        """
        serialized = json.dumps(state, sort_keys=True, default=str)
        state_hash = str(hash(serialized))
        transitions = self.get_state_transitions(state_hash)

        if not transitions:
            return []

        actions_rewards = [
            (action, avg_reward) for action, _, avg_reward in transitions
        ]
        actions_rewards.sort(key=lambda x: x[1], reverse=True)
        return actions_rewards[:top_k]

    def get_statistics(self) -> Dict[str, Any]:
        """Get graph statistics."""
        stats: Dict[str, Any] = dict(self.stats)

        if self.stats['total_episodes'] > 0:
            stats['avg_episode_length'] = (
                self.stats['total_events'] / self.stats['total_episodes']
            )
        else:
            stats['avg_episode_length'] = 0

        stats['graph_density'] = nx.density(self.graph)

        if self.episodes:
            episode_lengths = [len(evts) for evts in self.episodes.values()]
            stats['min_episode_length'] = min(episode_lengths)
            stats['max_episode_length'] = max(episode_lengths)
            stats['median_episode_length'] = float(np.median(episode_lengths))

        return stats

    def save(self, filepath: str) -> None:
        """Save graph to disk as JSON.

        States are already JSON-serializable dicts, so no ndarray conversion needed.
        """
        data = {
            'graph': nx.node_link_data(self.graph),
            'events': [
                {
                    'event_id': e.event_id,
                    'timestamp': e.timestamp,
                    'state': e.state,
                    'action': e.action,
                    'next_state': e.next_state,
                    'reward': e.reward,
                    'done': e.done,
                    'value': e.value,
                    'policy_entropy': e.policy_entropy,
                    'consciousness': e.consciousness,
                    'dmn_energy': e.dmn_energy,
                    'episode_id': e.episode_id,
                    'step_in_episode': e.step_in_episode,
                    'metadata': e.metadata,
                }
                for e in self.events
            ],
            'state_index': self.state_index,
            'next_node_id': self.next_node_id,
            'episodes': {str(k): v for k, v in self.episodes.items()},
            'current_episode_id': self.current_episode_id,
            'stats': self.stats,
        }

        # Crash-safe: tmp + fsync + atomic replace. A truncate-then-write
        # would destroy the whole diary on a kill mid-save.
        atomic_write_json(filepath, data, indent=2, default=str)

    def load(self, filepath: str) -> None:
        """Load graph from disk."""
        with open(filepath, 'r') as f:
            data = json.load(f)

        self.graph = nx.node_link_graph(data['graph'], multigraph=True, directed=True)

        self.events = [
            BrainEvent(
                event_id=e['event_id'],
                timestamp=e['timestamp'],
                state=e['state'],
                action=e['action'],
                next_state=e['next_state'],
                reward=e['reward'],
                done=e['done'],
                value=e['value'],
                policy_entropy=e['policy_entropy'],
                consciousness=e['consciousness'],
                dmn_energy=e['dmn_energy'],
                episode_id=e['episode_id'],
                step_in_episode=e['step_in_episode'],
                metadata=e['metadata'],
            )
            for e in data['events']
        ]

        self.state_index = data['state_index']
        self.next_node_id = data['next_node_id']
        self.episodes = {int(k): v for k, v in data['episodes'].items()}
        self.current_episode_id = data['current_episode_id']
        self.stats = data['stats']

    def clear(self) -> None:
        """Clear all data, resetting to initial empty state."""
        with self._lock:
            self.graph.clear()
            self.events.clear()
            self.state_index.clear()
            self.episodes.clear()
            self.next_node_id = 0
            self.current_episode_id = 0
            self.stats = {
                'total_events': 0,
                'total_episodes': 0,
                'total_states': 0,
                'total_transitions': 0,
            }
