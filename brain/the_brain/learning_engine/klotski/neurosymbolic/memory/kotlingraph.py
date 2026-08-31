"""
KotlinGraph - Raw Event Storage

Stores all gameplay events as a directed graph:
- Nodes: States (board configurations)
- Edges: Actions (state transitions)
- Metadata: Rewards, timestamps, brain activations

This is the "episodic memory" of the system - stores everything that happened.
"""

import networkx as nx
import numpy as np
import torch
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import pickle
import json


@dataclass
class GameEvent:
    """Single gameplay event"""
    event_id: int
    timestamp: str
    state: np.ndarray  # Board state (4, 5)
    action: int  # Action taken
    next_state: np.ndarray  # Resulting state
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
        """Create hash of state for indexing"""
        state_array = self.state.cpu().numpy() if isinstance(self.state, torch.Tensor) else self.state
        return hash(state_array.tobytes()).__str__()

    def next_state_hash(self) -> str:
        """Create hash of next state"""
        next_state_array = self.next_state.cpu().numpy() if isinstance(self.next_state, torch.Tensor) else self.next_state
        return hash(next_state_array.tobytes()).__str__()


class KotlinGraph:
    """
    Raw event storage graph

    Stores all gameplay events in a directed graph structure:
    - Nodes represent unique board states
    - Edges represent state transitions (actions)
    - Full history of all episodes preserved
    """

    def __init__(self):
        self.graph = nx.MultiDiGraph()  # Multi-graph allows duplicate edges

        # Event log (chronological)
        self.events: List[GameEvent] = []

        # State index (hash -> node_id)
        self.state_index: Dict[str, int] = {}
        self.next_node_id = 0

        # Episode tracking
        self.episodes: Dict[int, List[int]] = {}  # episode_id -> [event_ids]
        self.current_episode_id = 0

        # Statistics
        self.stats = {
            'total_events': 0,
            'total_episodes': 0,
            'total_states': 0,
            'total_transitions': 0
        }

    def add_event(
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
        Add a gameplay event to the graph

        Returns:
            event_id: ID of the added event
        """
        # Create event
        event_id = len(self.events)
        event = GameEvent(
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
            metadata=metadata or {}
        )

        self.events.append(event)

        # Add states as nodes if new
        state_hash = event.state_hash()
        next_state_hash = event.next_state_hash()

        if state_hash not in self.state_index:
            node_id = self.next_node_id
            self.next_node_id += 1
            self.state_index[state_hash] = node_id
            self.graph.add_node(
                node_id,
                state=state,
                state_hash=state_hash,
                first_seen=event.timestamp,
                visit_count=0
            )
            self.stats['total_states'] += 1

        if next_state_hash not in self.state_index:
            node_id = self.next_node_id
            self.next_node_id += 1
            self.state_index[next_state_hash] = node_id
            self.graph.add_node(
                node_id,
                state=next_state,
                state_hash=next_state_hash,
                first_seen=event.timestamp,
                visit_count=0
            )
            self.stats['total_states'] += 1

        # Get node IDs
        from_node = self.state_index[state_hash]
        to_node = self.state_index[next_state_hash]

        # Update visit counts
        self.graph.nodes[from_node]['visit_count'] += 1

        # Add edge (transition)
        self.graph.add_edge(
            from_node,
            to_node,
            event_id=event_id,
            action=action,
            reward=reward,
            timestamp=event.timestamp,
            value=value,
            consciousness=consciousness,
            episode_id=self.current_episode_id
        )

        self.stats['total_transitions'] += 1

        # Track episode
        if self.current_episode_id not in self.episodes:
            self.episodes[self.current_episode_id] = []
        self.episodes[self.current_episode_id].append(event_id)

        # If episode done, increment episode counter
        if done:
            self.stats['total_episodes'] += 1
            self.current_episode_id += 1

        self.stats['total_events'] += 1

        return event_id

    def get_event(self, event_id: int) -> GameEvent:
        """Get event by ID"""
        return self.events[event_id]

    def get_episode(self, episode_id: int) -> List[GameEvent]:
        """Get all events in an episode"""
        event_ids = self.episodes.get(episode_id, [])
        return [self.events[eid] for eid in event_ids]

    def get_episode_trajectory(self, episode_id: int) -> Tuple[List[np.ndarray], List[int], List[float]]:
        """
        Get episode as (states, actions, rewards) trajectory

        Returns:
            states: List of states
            actions: List of actions
            rewards: List of rewards
        """
        events = self.get_episode(episode_id)
        states = [e.state for e in events]
        actions = [e.action for e in events]
        rewards = [e.reward for e in events]
        return states, actions, rewards

    def get_state_transitions(self, state_hash: str) -> List[Tuple[int, int, float]]:
        """
        Get all transitions from a state

        Returns:
            List of (action, next_node_id, avg_reward) tuples
        """
        if state_hash not in self.state_index:
            return []

        node_id = self.state_index[state_hash]
        transitions = []

        # Group edges by action
        action_data = {}
        for _, to_node, edge_data in self.graph.out_edges(node_id, data=True):
            action = edge_data['action']
            reward = edge_data['reward']

            if action not in action_data:
                action_data[action] = {'to_node': to_node, 'rewards': []}
            action_data[action]['rewards'].append(reward)

        # Compute average rewards
        for action, data in action_data.items():
            avg_reward = np.mean(data['rewards'])
            transitions.append((action, data['to_node'], avg_reward))

        return transitions

    def get_most_visited_states(self, top_k: int = 10) -> List[Tuple[int, int]]:
        """
        Get most frequently visited states

        Returns:
            List of (node_id, visit_count) tuples
        """
        visits = [(nid, data['visit_count']) for nid, data in self.graph.nodes(data=True)]
        visits.sort(key=lambda x: x[1], reverse=True)
        return visits[:top_k]

    def get_best_actions_from_state(self, state: np.ndarray, top_k: int = 3) -> List[Tuple[int, float]]:
        """
        Get best actions from a state based on historical rewards

        Returns:
            List of (action, avg_reward) tuples
        """
        state_hash = hash(state.tobytes()).__str__()
        transitions = self.get_state_transitions(state_hash)

        if not transitions:
            return []

        # Sort by average reward
        actions_rewards = [(action, avg_reward) for action, _, avg_reward in transitions]
        actions_rewards.sort(key=lambda x: x[1], reverse=True)

        return actions_rewards[:top_k]

    def get_statistics(self) -> Dict[str, Any]:
        """Get graph statistics"""
        stats = self.stats.copy()

        # Compute additional stats
        if self.stats['total_episodes'] > 0:
            stats['avg_episode_length'] = self.stats['total_events'] / self.stats['total_episodes']
        else:
            stats['avg_episode_length'] = 0

        stats['graph_density'] = nx.density(self.graph)

        # Episode statistics
        if self.episodes:
            episode_lengths = [len(events) for events in self.episodes.values()]
            stats['min_episode_length'] = min(episode_lengths)
            stats['max_episode_length'] = max(episode_lengths)
            stats['median_episode_length'] = float(np.median(episode_lengths))

        return stats

    def save(self, filepath: str):
        """Save graph to disk"""
        data = {
            'graph': nx.node_link_data(self.graph),
            'events': [
                {
                    'event_id': e.event_id,
                    'timestamp': e.timestamp,
                    'state': e.state.tolist(),
                    'action': e.action,
                    'next_state': e.next_state.tolist(),
                    'reward': e.reward,
                    'done': e.done,
                    'value': e.value,
                    'policy_entropy': e.policy_entropy,
                    'consciousness': e.consciousness,
                    'dmn_energy': e.dmn_energy,
                    'episode_id': e.episode_id,
                    'step_in_episode': e.step_in_episode,
                    'metadata': e.metadata
                }
                for e in self.events
            ],
            'state_index': self.state_index,
            'next_node_id': self.next_node_id,
            'episodes': {k: v for k, v in self.episodes.items()},
            'current_episode_id': self.current_episode_id,
            'stats': self.stats
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    def load(self, filepath: str):
        """Load graph from disk"""
        with open(filepath, 'r') as f:
            data = json.load(f)

        self.graph = nx.node_link_graph(data['graph'], multigraph=True, directed=True)

        self.events = [
            GameEvent(
                event_id=e['event_id'],
                timestamp=e['timestamp'],
                state=np.array(e['state']),
                action=e['action'],
                next_state=np.array(e['next_state']),
                reward=e['reward'],
                done=e['done'],
                value=e['value'],
                policy_entropy=e['policy_entropy'],
                consciousness=e['consciousness'],
                dmn_energy=e['dmn_energy'],
                episode_id=e['episode_id'],
                step_in_episode=e['step_in_episode'],
                metadata=e['metadata']
            )
            for e in data['events']
        ]

        self.state_index = data['state_index']
        self.next_node_id = data['next_node_id']
        self.episodes = {int(k): v for k, v in data['episodes'].items()}
        self.current_episode_id = data['current_episode_id']
        self.stats = data['stats']

    def clear(self):
        """Clear all data"""
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
            'total_transitions': 0
        }


if __name__ == '__main__':
    # Test KotlinGraph
    print("Testing KotlinGraph...")

    kg = KotlinGraph()

    # Simulate a short episode
    for step in range(5):
        state = np.random.randint(0, 10, size=(4, 5))
        action = np.random.randint(0, 20)
        next_state = np.random.randint(0, 10, size=(4, 5))
        reward = 1.0 if step == 4 else 0.0
        done = (step == 4)

        kg.add_event(
            state=state,
            action=action,
            next_state=next_state,
            reward=reward,
            done=done,
            value=np.random.rand(),
            consciousness=np.random.rand()
        )

    # Print statistics
    stats = kg.get_statistics()
    print(f"\nStatistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Get episode
    episode = kg.get_episode(0)
    print(f"\nEpisode 0 has {len(episode)} events")

    # Save and load
    kg.save("test_kotlingraph.json")
    print("\nSaved to test_kotlingraph.json")

    kg2 = KotlinGraph()
    kg2.load("test_kotlingraph.json")
    print(f"Loaded graph with {kg2.stats['total_events']} events")

    print("\n[OK] KotlinGraph test passed!")
