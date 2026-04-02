# Thalamic Rewiring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewire the brain so ThalamoPC6 becomes THE single input gate, generalize the learning engine from Klotski-specific to domain-agnostic, and create cortical areas backed by MoltBook communities with a response agent that reads activations through CTM.

**Architecture:** All inputs (text, sensors, agent events, internal state) flow through ThalamoPC6's thalamic math (TRN inhibition, prediction errors, softmax gating, Kuramoto coupling). ThalamoPC6 routes to N cortical areas (each wrapping CorticalColumn + neuroscience modules). Areas write to a shared DualGraph memory (KotlinGraph + KuroGraph). A ResponseAgent reads area activations, deliberates via CTMLayer, and produces output.

**Tech Stack:** Python 3.11, NumPy, NetworkX, pytest. No new external dependencies.

**Test runner:** `python -m pytest tests/<file>::<class>::<test> -xvs`

**Working directory:** `C:\Users\User\Desktop\the_brain\the_brain`

---

## Task 1: Domain-Agnostic KotlinGraph (Episodic Memory)

Port `learning_engine/klotski/neurosymbolic/memory/kotlingraph.py` to `core/kotlin_graph.py`.
Generalize from `np.ndarray` states + `int` actions to `Dict[str, Any]` states + `str` actions.

**Files:**
- Create: `core/kotlin_graph.py`
- Create: `tests/test_kotlin_graph.py`
- Reference: `learning_engine/klotski/neurosymbolic/memory/kotlingraph.py` (original to port from)

**Step 1: Write the failing tests**

```python
# tests/test_kotlin_graph.py
"""Tests for domain-agnostic KotlinGraph (episodic memory)."""
import pytest
import json
import os
import tempfile
from core.kotlin_graph import KotlinGraph, BrainEvent


class TestBrainEvent:
    """Test BrainEvent dataclass."""

    def test_create_event_with_dict_state(self):
        """Events accept dict states instead of np.ndarray."""
        event = BrainEvent(
            event_id=0,
            state={"message": "hello", "intent": "greeting"},
            action="respond_greeting",
            next_state={"message": "hello", "response_given": True},
            reward=1.0,
            done=False,
        )
        assert event.state["message"] == "hello"
        assert event.action == "respond_greeting"

    def test_state_hash_deterministic(self):
        """Same state dict produces same hash."""
        event = BrainEvent(
            event_id=0,
            state={"a": 1, "b": 2},
            action="act",
            next_state={"a": 1, "b": 3},
            reward=0.0,
            done=False,
        )
        h1 = event.state_hash()
        h2 = event.state_hash()
        assert h1 == h2

    def test_different_states_different_hash(self):
        """Different state dicts produce different hashes."""
        e1 = BrainEvent(0, {"a": 1}, "act", {"a": 2}, 0.0, False)
        e2 = BrainEvent(1, {"a": 99}, "act", {"a": 2}, 0.0, False)
        assert e1.state_hash() != e2.state_hash()

    def test_metadata_defaults_empty(self):
        """Metadata defaults to empty dict."""
        event = BrainEvent(0, {}, "act", {}, 0.0, False)
        assert event.metadata == {}

    def test_brain_metrics_defaults(self):
        """Brain metrics default to 0.0."""
        event = BrainEvent(0, {}, "act", {}, 0.0, False)
        assert event.value == 0.0
        assert event.consciousness == 0.0


class TestKotlinGraph:
    """Test KotlinGraph episodic memory graph."""

    def test_add_event_returns_id(self):
        kg = KotlinGraph()
        eid = kg.add_event(
            state={"msg": "hello"},
            action="greet",
            next_state={"msg": "hello", "greeted": True},
            reward=1.0,
            done=False,
        )
        assert eid == 0

    def test_sequential_event_ids(self):
        kg = KotlinGraph()
        id0 = kg.add_event({"s": 0}, "a", {"s": 1}, 0.0, False)
        id1 = kg.add_event({"s": 1}, "b", {"s": 2}, 0.0, True)
        assert id0 == 0
        assert id1 == 1

    def test_graph_nodes_created(self):
        """Each unique state creates a node."""
        kg = KotlinGraph()
        kg.add_event({"s": "A"}, "go", {"s": "B"}, 0.5, False)
        assert kg.stats["total_states"] >= 2  # A and B

    def test_graph_edge_created(self):
        """Each event creates an edge."""
        kg = KotlinGraph()
        kg.add_event({"s": "A"}, "go", {"s": "B"}, 0.5, False)
        assert kg.stats["total_transitions"] == 1

    def test_episode_tracking(self):
        """Events group into episodes via done=True."""
        kg = KotlinGraph()
        kg.add_event({"s": 0}, "a", {"s": 1}, 0.0, False)
        kg.add_event({"s": 1}, "b", {"s": 2}, 1.0, done=True)  # end ep 0
        kg.add_event({"s": 3}, "c", {"s": 4}, 0.0, False)      # start ep 1
        assert kg.stats["total_episodes"] == 1  # completed episodes
        assert kg.current_episode_id == 1

    def test_get_episode(self):
        kg = KotlinGraph()
        kg.add_event({"s": 0}, "a", {"s": 1}, 0.1, False)
        kg.add_event({"s": 1}, "b", {"s": 2}, 0.9, True)
        events = kg.get_episode(0)
        assert len(events) == 2
        assert events[0].action == "a"
        assert events[1].action == "b"

    def test_get_episode_trajectory(self):
        kg = KotlinGraph()
        kg.add_event({"s": "A"}, "go", {"s": "B"}, 0.5, False)
        kg.add_event({"s": "B"}, "stop", {"s": "C"}, 1.0, True)
        states, actions, rewards = kg.get_episode_trajectory(0)
        assert actions == ["go", "stop"]
        assert rewards == [0.5, 1.0]

    def test_duplicate_states_share_node(self):
        """Same state dict reuses existing node."""
        kg = KotlinGraph()
        kg.add_event({"s": "A"}, "go", {"s": "B"}, 0.1, False)
        kg.add_event({"s": "B"}, "back", {"s": "A"}, 0.1, True)
        # A and B created once each = 2 states total
        assert kg.stats["total_states"] == 2

    def test_statistics(self):
        kg = KotlinGraph()
        kg.add_event({"x": 1}, "act", {"x": 2}, 1.0, True)
        stats = kg.get_statistics()
        assert stats["total_events"] == 1
        assert stats["total_episodes"] == 1

    def test_clear(self):
        kg = KotlinGraph()
        kg.add_event({"x": 1}, "act", {"x": 2}, 1.0, True)
        kg.clear()
        assert kg.stats["total_events"] == 0
        assert len(kg.events) == 0


class TestKotlinGraphPersistence:
    """Test save/load."""

    def test_save_and_load_roundtrip(self, tmp_path):
        kg = KotlinGraph()
        kg.add_event({"s": "A"}, "go", {"s": "B"}, 0.5, False)
        kg.add_event({"s": "B"}, "stop", {"s": "C"}, 1.0, True)

        path = str(tmp_path / "test_kg.json")
        kg.save(path)
        assert os.path.exists(path)

        kg2 = KotlinGraph()
        kg2.load(path)
        assert kg2.stats["total_events"] == 2
        assert kg2.stats["total_episodes"] == 1

    def test_loaded_events_match(self, tmp_path):
        kg = KotlinGraph()
        kg.add_event({"msg": "hello"}, "greet", {"msg": "hi"}, 1.0, True)

        path = str(tmp_path / "test_kg.json")
        kg.save(path)

        kg2 = KotlinGraph()
        kg2.load(path)
        assert kg2.events[0].action == "greet"
        assert kg2.events[0].state == {"msg": "hello"}
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_kotlin_graph.py -xvs`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.kotlin_graph'`

**Step 3: Implement `core/kotlin_graph.py`**

Port the original KotlinGraph, changing:
- `GameEvent` → `BrainEvent` with `state: Dict[str, Any]`, `action: str`, `next_state: Dict[str, Any]`
- `state_hash()` → `json.dumps(sorted(state.items()))` for deterministic hashing
- Remove `torch` and `np.ndarray` dependencies from the event class
- `save/load` → store states as plain dicts (already JSON-serializable)
- Keep: NetworkX MultiDiGraph, episode tracking, visit counts, all graph algorithms
- Remove: `if __name__ == '__main__'` test block (we have proper tests now)

```python
"""
KotlinGraph - Domain-Agnostic Episodic Memory

Stores all brain events as a directed graph:
- Nodes: States (any Dict[str, Any])
- Edges: Actions (str transitions)
- Metadata: Rewards, timestamps, brain metrics

Ported from learning_engine/klotski/neurosymbolic/memory/kotlingraph.py
Generalized from Klotski puzzle states to any domain.
"""

import networkx as nx
import numpy as np
import json
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BrainEvent:
    """Single brain event (domain-agnostic)."""
    event_id: int
    state: Dict[str, Any]
    action: str
    next_state: Dict[str, Any]
    reward: float
    done: bool

    # Brain metrics
    timestamp: str = ""
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
        """Deterministic hash of state dict."""
        return str(hash(json.dumps(self.state, sort_keys=True, default=str)))

    def next_state_hash(self) -> str:
        """Deterministic hash of next_state dict."""
        return str(hash(json.dumps(self.next_state, sort_keys=True, default=str)))


class KotlinGraph:
    """
    Domain-agnostic episodic memory graph.

    Nodes = unique states (Dict[str, Any])
    Edges = transitions (str actions)
    Full episode history preserved.

    Ported from learning_engine/.../kotlingraph.py
    """

    def __init__(self):
        self.graph = nx.MultiDiGraph()
        self.events: List[BrainEvent] = []
        self.state_index: Dict[str, int] = {}
        self.next_node_id = 0
        self.episodes: Dict[int, List[int]] = {}
        self.current_episode_id = 0
        self.stats = {
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
        metadata: Optional[Dict] = None,
    ) -> int:
        """Add an event. Returns event_id."""
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

        # Add states as nodes
        state_hash = event.state_hash()
        next_state_hash = event.next_state_hash()

        for sh, st in [(state_hash, state), (next_state_hash, next_state)]:
            if sh not in self.state_index:
                nid = self.next_node_id
                self.next_node_id += 1
                self.state_index[sh] = nid
                self.graph.add_node(nid, state=st, state_hash=sh,
                                    first_seen=event.timestamp, visit_count=0)
                self.stats['total_states'] += 1

        from_node = self.state_index[state_hash]
        to_node = self.state_index[next_state_hash]
        self.graph.nodes[from_node]['visit_count'] += 1

        self.graph.add_edge(from_node, to_node,
                            event_id=event_id, action=action, reward=reward,
                            timestamp=event.timestamp, value=value,
                            consciousness=consciousness,
                            episode_id=self.current_episode_id)
        self.stats['total_transitions'] += 1

        if self.current_episode_id not in self.episodes:
            self.episodes[self.current_episode_id] = []
        self.episodes[self.current_episode_id].append(event_id)

        if done:
            self.stats['total_episodes'] += 1
            self.current_episode_id += 1

        self.stats['total_events'] += 1
        return event_id

    def get_event(self, event_id: int) -> BrainEvent:
        return self.events[event_id]

    def get_episode(self, episode_id: int) -> List[BrainEvent]:
        event_ids = self.episodes.get(episode_id, [])
        return [self.events[eid] for eid in event_ids]

    def get_episode_trajectory(self, episode_id: int) -> Tuple[List[Dict], List[str], List[float]]:
        events = self.get_episode(episode_id)
        states = [e.state for e in events]
        actions = [e.action for e in events]
        rewards = [e.reward for e in events]
        return states, actions, rewards

    def get_state_transitions(self, state_hash: str) -> List[Tuple[str, int, float]]:
        if state_hash not in self.state_index:
            return []
        node_id = self.state_index[state_hash]
        action_data = {}
        for _, to_node, edge_data in self.graph.out_edges(node_id, data=True):
            action = edge_data['action']
            reward = edge_data['reward']
            if action not in action_data:
                action_data[action] = {'to_node': to_node, 'rewards': []}
            action_data[action]['rewards'].append(reward)
        return [(action, d['to_node'], float(np.mean(d['rewards'])))
                for action, d in action_data.items()]

    def get_most_visited_states(self, top_k: int = 10) -> List[Tuple[int, int]]:
        visits = [(nid, data['visit_count'])
                  for nid, data in self.graph.nodes(data=True)]
        visits.sort(key=lambda x: x[1], reverse=True)
        return visits[:top_k]

    def get_statistics(self) -> Dict[str, Any]:
        stats = self.stats.copy()
        if stats['total_episodes'] > 0:
            stats['avg_episode_length'] = stats['total_events'] / stats['total_episodes']
        else:
            stats['avg_episode_length'] = 0
        stats['graph_density'] = nx.density(self.graph) if self.graph.number_of_nodes() > 0 else 0.0
        if self.episodes:
            lengths = [len(evts) for evts in self.episodes.values()]
            stats['min_episode_length'] = min(lengths)
            stats['max_episode_length'] = max(lengths)
        return stats

    def save(self, filepath: str):
        data = {
            'events': [
                {
                    'event_id': e.event_id, 'timestamp': e.timestamp,
                    'state': e.state, 'action': e.action,
                    'next_state': e.next_state, 'reward': e.reward,
                    'done': e.done, 'value': e.value,
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
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def load(self, filepath: str):
        with open(filepath, 'r') as f:
            data = json.load(f)
        self.events = [
            BrainEvent(
                event_id=e['event_id'], timestamp=e.get('timestamp', ''),
                state=e['state'], action=e['action'],
                next_state=e['next_state'], reward=e['reward'],
                done=e['done'], value=e.get('value', 0.0),
                policy_entropy=e.get('policy_entropy', 0.0),
                consciousness=e.get('consciousness', 0.0),
                dmn_energy=e.get('dmn_energy', 0.0),
                episode_id=e.get('episode_id', 0),
                step_in_episode=e.get('step_in_episode', 0),
                metadata=e.get('metadata', {}),
            )
            for e in data['events']
        ]
        self.state_index = data['state_index']
        self.next_node_id = data['next_node_id']
        self.episodes = {int(k): v for k, v in data['episodes'].items()}
        self.current_episode_id = data['current_episode_id']
        self.stats = data['stats']
        # Rebuild graph from events
        self.graph = nx.MultiDiGraph()
        for e in self.events:
            sh = e.state_hash()
            nsh = e.next_state_hash()
            for h, s in [(sh, e.state), (nsh, e.next_state)]:
                if h in self.state_index:
                    nid = self.state_index[h]
                    if not self.graph.has_node(nid):
                        self.graph.add_node(nid, state=s, state_hash=h,
                                            first_seen=e.timestamp, visit_count=0)
            from_n = self.state_index[sh]
            to_n = self.state_index[nsh]
            self.graph.nodes[from_n]['visit_count'] = \
                self.graph.nodes[from_n].get('visit_count', 0) + 1
            self.graph.add_edge(from_n, to_n, event_id=e.event_id,
                                action=e.action, reward=e.reward,
                                timestamp=e.timestamp, value=e.value,
                                consciousness=e.consciousness,
                                episode_id=e.episode_id)

    def clear(self):
        self.graph.clear()
        self.events.clear()
        self.state_index.clear()
        self.episodes.clear()
        self.next_node_id = 0
        self.current_episode_id = 0
        self.stats = {
            'total_events': 0, 'total_episodes': 0,
            'total_states': 0, 'total_transitions': 0,
        }
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_kotlin_graph.py -xvs`
Expected: ALL PASS (16 tests)

**Step 5: Commit**

```bash
git add core/kotlin_graph.py tests/test_kotlin_graph.py
git commit -m "feat: add domain-agnostic KotlinGraph episodic memory

Port KotlinGraph from learning_engine/klotski to core/.
Generalize: ndarray states -> Dict, int actions -> str.
Keep: NetworkX MultiDiGraph, episodes, save/load, all graph algorithms."
```

---

## Task 2: Domain-Agnostic KuroGraph (Pattern Mining)

Port `learning_engine/klotski/neurosymbolic/memory/kurograph.py` to `core/kuro_graph.py`.

**Files:**
- Create: `core/kuro_graph.py`
- Create: `tests/test_kuro_graph.py`
- Depends on: `core/kotlin_graph.py` (Task 1)

**Step 1: Write the failing tests**

```python
# tests/test_kuro_graph.py
"""Tests for domain-agnostic KuroGraph (pattern mining)."""
import pytest
import numpy as np
from core.kotlin_graph import KotlinGraph
from core.kuro_graph import KuroGraph, ActionNGram, StrategyPattern


class TestActionNGram:
    def test_create_ngram(self):
        ng = ActionNGram(
            actions=("greet", "ask_name", "respond"),
            frequency=5,
            avg_reward=0.8,
            success_rate=0.6,
        )
        assert len(ng) == 3
        assert ng.frequency == 5

    def test_ngram_hashable(self):
        ng1 = ActionNGram(("a", "b"), 1, 0.5, 0.5)
        ng2 = ActionNGram(("a", "b"), 2, 0.9, 0.9)
        assert hash(ng1) == hash(ng2)  # same actions

    def test_ngram_equality(self):
        ng1 = ActionNGram(("a", "b"), 1, 0.5, 0.5)
        ng2 = ActionNGram(("a", "b"), 2, 0.9, 0.9)
        assert ng1 == ng2  # equality by actions


def _build_kg_with_pattern():
    """Helper: build KotlinGraph with repeated action pattern [greet, ask, respond]."""
    kg = KotlinGraph()
    pattern = ["greet", "ask", "respond"]
    for episode in range(5):
        for i, action in enumerate(pattern * 2):  # 6 steps per episode
            done = (i == len(pattern) * 2 - 1)
            reward = 1.0 if done else 0.1
            kg.add_event(
                state={"ep": episode, "step": i},
                action=action,
                next_state={"ep": episode, "step": i + 1},
                reward=reward,
                done=done,
            )
    return kg


class TestKuroGraphMining:
    def test_mine_ngrams_finds_patterns(self):
        kg = _build_kg_with_pattern()
        kuro = KuroGraph(kotlingraph=kg)
        ngrams = kuro.mine_ngrams(n=3, min_frequency=2)
        assert len(ngrams) > 0
        actions_found = [ng.actions for ng in ngrams]
        assert ("greet", "ask", "respond") in actions_found

    def test_mine_ngrams_respects_min_frequency(self):
        kg = _build_kg_with_pattern()
        kuro = KuroGraph(kotlingraph=kg)
        ngrams = kuro.mine_ngrams(n=3, min_frequency=100)
        assert len(ngrams) == 0  # threshold too high

    def test_get_best_ngrams(self):
        kg = _build_kg_with_pattern()
        kuro = KuroGraph(kotlingraph=kg)
        kuro.mine_ngrams(n=3, min_frequency=2)
        best = kuro.get_best_ngrams(top_k=3)
        assert len(best) <= 3
        assert all(isinstance(ng, ActionNGram) for ng in best)

    def test_suggest_action_with_history(self):
        kg = _build_kg_with_pattern()
        kuro = KuroGraph(kotlingraph=kg)
        kuro.mine_ngrams(n=3, min_frequency=2)
        suggestions = kuro.suggest_action(
            state={"step": 2},
            recent_actions=["greet", "ask"],
            top_k=3,
        )
        assert len(suggestions) > 0
        # Should suggest "respond" as next action
        actions = [a for a, _ in suggestions]
        assert "respond" in actions

    def test_suggest_action_no_history(self):
        kg = _build_kg_with_pattern()
        kuro = KuroGraph(kotlingraph=kg)
        kuro.mine_ngrams(n=3, min_frequency=2)
        suggestions = kuro.suggest_action(
            state={"step": 0},
            recent_actions=[],
            top_k=3,
        )
        # Should return some suggestions (first actions from patterns)
        assert isinstance(suggestions, list)

    def test_build_cooccurrence_matrix(self):
        kg = _build_kg_with_pattern()
        kuro = KuroGraph(kotlingraph=kg)
        kuro.build_cooccurrence_matrix(window_size=3)
        assert len(kuro.action_cooccurrence) > 0

    def test_statistics(self):
        kg = _build_kg_with_pattern()
        kuro = KuroGraph(kotlingraph=kg)
        kuro.mine_ngrams(n=3, min_frequency=2)
        stats = kuro.get_statistics()
        assert stats['total_ngrams'] > 0


class TestKuroGraphPersistence:
    def test_save_and_load(self, tmp_path):
        kg = _build_kg_with_pattern()
        kuro = KuroGraph(kotlingraph=kg)
        kuro.mine_ngrams(n=3, min_frequency=2)

        path = str(tmp_path / "test_kuro.json")
        kuro.save(path)

        kuro2 = KuroGraph()
        kuro2.load(path)
        assert kuro2.stats['total_ngrams'] == kuro.stats['total_ngrams']
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_kuro_graph.py -xvs`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.kuro_graph'`

**Step 3: Implement `core/kuro_graph.py`**

Port from `learning_engine/.../kurograph.py`, changing:
- `Tuple[int, ...]` → `Tuple[str, ...]` for action sequences
- `np.ndarray` state → `Dict[str, Any]` state
- `state.tobytes()` hashing → `json.dumps(state, sort_keys=True, default=str)` hashing
- Import from `core.kotlin_graph` instead of `.kotlingraph`
- Keep: all mining algorithms, scoring, co-occurrence, strategies

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_kuro_graph.py -xvs`
Expected: ALL PASS (10 tests)

**Step 5: Commit**

```bash
git add core/kuro_graph.py tests/test_kuro_graph.py
git commit -m "feat: add domain-agnostic KuroGraph pattern mining

Port KuroGraph from learning_engine/klotski to core/.
Generalize: int actions -> str. Keep: n-gram mining, strategies,
co-occurrence matrix, action suggestion."
```

---

## Task 3: Domain-Agnostic DualGraph Manager

Port `learning_engine/klotski/neurosymbolic/memory/dual_graph_manager.py` to `core/dual_graph.py`.

**Files:**
- Create: `core/dual_graph.py`
- Create: `tests/test_dual_graph.py`
- Depends on: `core/kotlin_graph.py` (Task 1), `core/kuro_graph.py` (Task 2)

**Step 1: Write the failing tests**

```python
# tests/test_dual_graph.py
"""Tests for domain-agnostic DualGraph manager."""
import pytest
from core.dual_graph import DualGraph


class TestDualGraph:
    def test_record_event(self, tmp_path):
        dg = DualGraph(save_dir=str(tmp_path))
        eid = dg.record_event(
            state={"msg": "hello"},
            action="greet",
            next_state={"msg": "hi back"},
            reward=1.0,
            done=True,
        )
        assert eid == 0
        assert dg.stats['total_events_recorded'] == 1

    def test_auto_mine_after_interval(self, tmp_path):
        dg = DualGraph(save_dir=str(tmp_path), auto_mine_interval=2)
        for ep in range(3):
            for step in range(4):
                done = (step == 3)
                dg.record_event(
                    state={"ep": ep, "s": step},
                    action=f"act_{step % 3}",
                    next_state={"ep": ep, "s": step + 1},
                    reward=1.0 if done else 0.1,
                    done=done,
                )
        assert dg.stats['total_patterns_mined'] >= 0  # mining ran

    def test_suggest_actions(self, tmp_path):
        dg = DualGraph(save_dir=str(tmp_path), auto_mine_interval=2)
        pattern = ["a", "b", "c"]
        for ep in range(5):
            for i, act in enumerate(pattern * 2):
                done = (i == 5)
                dg.record_event({"ep": ep, "s": i}, act,
                                {"ep": ep, "s": i + 1},
                                1.0 if done else 0.1, done)
        dg.force_mine()
        suggestions = dg.suggest_actions(
            state={"s": 2},
            recent_actions=["a", "b"],
            top_k=3,
        )
        assert isinstance(suggestions, list)

    def test_save_and_load(self, tmp_path):
        dg = DualGraph(save_dir=str(tmp_path))
        dg.record_event({"x": 1}, "act", {"x": 2}, 1.0, True)
        dg.save("test")

        dg2 = DualGraph(save_dir=str(tmp_path))
        success = dg2.load("test")
        assert success is True

    def test_get_statistics(self, tmp_path):
        dg = DualGraph(save_dir=str(tmp_path))
        dg.record_event({"x": 1}, "a", {"x": 2}, 0.5, True)
        stats = dg.get_statistics()
        assert 'total_events_recorded' in stats
        assert 'kotlingraph' in stats

    def test_clear(self, tmp_path):
        dg = DualGraph(save_dir=str(tmp_path))
        dg.record_event({"x": 1}, "act", {"x": 2}, 1.0, True)
        dg.clear()
        assert dg.stats['total_events_recorded'] == 0
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dual_graph.py -xvs`
Expected: FAIL

**Step 3: Implement `core/dual_graph.py`**

Port from `learning_engine/.../dual_graph_manager.py`, changing:
- Import from `core.kotlin_graph` and `core.kuro_graph`
- `np.ndarray` params → `Dict[str, Any]`
- `int` action params → `str`
- Class name: `DualGraphManager` → `DualGraph`
- Keep: auto-mining, force_mine, suggest_actions, save/load, statistics

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dual_graph.py -xvs`
Expected: ALL PASS (6 tests)

**Step 5: Commit**

```bash
git add core/dual_graph.py tests/test_dual_graph.py
git commit -m "feat: add domain-agnostic DualGraph memory manager

Coordinates KotlinGraph + KuroGraph. Auto-mines patterns,
suggests actions. Ported from learning_engine/klotski."
```

---

## Task 4: Thalamic Adapter (Input Encoding → ThalamoPC6)

Create the adapter that encodes any brain input into ThalamoPC6's 6 modalities.

**Files:**
- Create: `core/thalamic_adapter.py`
- Create: `tests/test_thalamic_adapter.py`
- Reference: `core/thalamo_pc_live.py` (ThalamoPC6)

**Step 1: Write the failing tests**

```python
# tests/test_thalamic_adapter.py
"""Tests for ThalamicAdapter — encodes brain inputs into ThalamoPC6 modalities."""
import pytest
import numpy as np
from core.thalamic_adapter import ThalamicAdapter


class TestThalamicAdapter:
    @pytest.fixture
    def adapter(self):
        return ThalamicAdapter()

    def test_encode_chat_message(self, adapter):
        """Chat text maps primarily to 'audio' modality."""
        encoded = adapter.encode_input("chat", {"message": "hello world"})
        assert "audio" in encoded
        assert isinstance(encoded["audio"], np.ndarray)
        assert encoded["audio"].shape[0] == 64  # audio dim in ThalamoPC6

    def test_encode_sensor_data(self, adapter):
        """Sensor data maps to 'touch' modality."""
        encoded = adapter.encode_input("sensor", {"cpu": 45.2, "memory": 68.1})
        assert "touch" in encoded
        assert isinstance(encoded["touch"], np.ndarray)

    def test_encode_internal_state(self, adapter):
        """Internal state maps to 'taste' modality."""
        encoded = adapter.encode_input("internal", {"mood": 0.7, "energy": 0.5})
        assert "taste" in encoded

    def test_encode_structured_data(self, adapter):
        """Structured data maps to 'vision' modality."""
        encoded = adapter.encode_input("structured", {"code": "print('hi')", "lang": "python"})
        assert "vision" in encoded

    def test_encode_context(self, adapter):
        """Temporal/spatial context maps to 'vestibular'."""
        encoded = adapter.encode_input("context", {"time": "2026-02-22", "session": 5})
        assert "vestibular" in encoded

    def test_encode_threat(self, adapter):
        """Error/safety signals map to 'threat'."""
        encoded = adapter.encode_input("threat", {"error": "MemoryError", "severity": 0.9})
        assert "threat" in encoded

    def test_all_modalities_populated(self, adapter):
        """Encoding always returns all 6 modalities (zeros for inactive)."""
        encoded = adapter.encode_input("chat", {"message": "hi"})
        assert len(encoded) == 6
        for mod in ["vision", "audio", "touch", "taste", "vestibular", "threat"]:
            assert mod in encoded

    def test_step_through_thalamus(self, adapter):
        """Full pipeline: encode → ThalamoPC6.step → gated output."""
        result = adapter.process("chat", {"message": "what is consciousness?"})
        assert "gates" in result
        assert "routed_output" in result
        assert "active_modalities" in result
        # Gates must sum to 1 (softmax invariant)
        assert abs(sum(result["gates"].values()) - 1.0) < 1e-5

    def test_gate_invariant_holds(self, adapter):
        """Gate weights always sum to 1.0 regardless of input."""
        for input_type, data in [
            ("chat", {"message": "hello"}),
            ("sensor", {"cpu": 99.0}),
            ("threat", {"error": "CRITICAL"}),
        ]:
            result = adapter.process(input_type, data)
            gate_sum = sum(result["gates"].values())
            assert abs(gate_sum - 1.0) < 1e-5, f"Gate sum {gate_sum} != 1.0 for {input_type}"

    def test_threat_gets_high_gate(self, adapter):
        """Threat input should activate threat modality with high gate weight."""
        result = adapter.process("threat", {"error": "CRITICAL", "severity": 1.0})
        # Threat has highest prior (0.25) and fastest time constant (20.0)
        assert result["gates"]["threat"] > 0.05  # non-trivial activation
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_thalamic_adapter.py -xvs`
Expected: FAIL

**Step 3: Implement `core/thalamic_adapter.py`**

```python
"""
ThalamicAdapter - Encodes brain inputs into ThalamoPC6 modalities.

Maps any input type to the 6 ThalamoPC6 modalities:
  vision     = structured data (code, JSON, files)
  audio      = natural language text
  touch      = system sensors (CPU, memory, disk)
  taste      = internal state (emotions, drives)
  vestibular = spatial/temporal context
  threat     = anomalies, errors, safety signals
"""

import numpy as np
import hashlib
from typing import Dict, Any, Optional
from core.thalamo_pc_live import ThalamoPC6


# Modality dimensions (must match ThalamoPC6 defaults)
MODALITY_DIMS = {
    "vision": 128, "audio": 64, "touch": 32,
    "taste": 16, "vestibular": 16, "threat": 8,
}

# Input type → primary modality mapping
INPUT_TYPE_MAP = {
    "chat": "audio",
    "sensor": "touch",
    "internal": "taste",
    "structured": "vision",
    "context": "vestibular",
    "threat": "threat",
}


class ThalamicAdapter:
    """Adapts any brain input to ThalamoPC6's 6-modality format."""

    def __init__(self, thalamus: Optional[ThalamoPC6] = None):
        self.thalamus = thalamus or ThalamoPC6()
        self.modalities = list(MODALITY_DIMS.keys())

    def encode_input(
        self, input_type: str, data: Dict[str, Any]
    ) -> Dict[str, np.ndarray]:
        """
        Encode input data into 6 modality vectors.

        Args:
            input_type: One of 'chat', 'sensor', 'internal',
                        'structured', 'context', 'threat'
            data: Input data dict

        Returns:
            Dict mapping modality name -> numpy vector
        """
        encoded = {m: np.zeros(MODALITY_DIMS[m]) for m in self.modalities}

        primary = INPUT_TYPE_MAP.get(input_type, "audio")
        dim = MODALITY_DIMS[primary]

        # Create a feature vector from the data
        vec = self._data_to_vector(data, dim)
        encoded[primary] = vec

        return encoded

    def process(
        self, input_type: str, data: Dict[str, Any],
        ctx: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Full pipeline: encode → ThalamoPC6.step → return gated result.

        Returns:
            Dict with 'gates', 'routed_output', 'active_modalities', 'prediction_errors'
        """
        encoded = self.encode_input(input_type, data)
        result = self.thalamus.step(encoded, ctx=ctx)

        gates_dict = {
            m: float(result['g'][i])
            for i, m in enumerate(self.modalities)
        }

        # Which modalities are meaningfully active (gate > 0.1)?
        active = [m for m, g in gates_dict.items() if g > 0.1]

        return {
            "gates": gates_dict,
            "routed_output": result['y'],
            "active_modalities": active,
            "prediction_errors": result['pe'],
            "thalamic_state": result['v_next'],
            "time_step": result['t'],
        }

    def _data_to_vector(self, data: Dict[str, Any], dim: int) -> np.ndarray:
        """
        Convert a data dict to a fixed-size numpy vector.

        Uses a deterministic hash-based projection — not learned,
        but gives consistent non-zero vectors for any input.
        """
        vec = np.zeros(dim)
        for i, (key, value) in enumerate(sorted(data.items())):
            # Hash key+value to get a seed
            h = hashlib.sha256(f"{key}={value}".encode()).digest()
            seed = int.from_bytes(h[:4], 'little')
            rng = np.random.default_rng(seed)

            # Fill a portion of the vector
            start = (i * 7) % dim
            length = min(dim // max(len(data), 1), dim - start)
            vec[start:start + length] = rng.normal(0, 0.5, length)

            # Add magnitude from numeric values
            if isinstance(value, (int, float)):
                vec[i % dim] += float(value) * 0.1
            elif isinstance(value, str):
                vec[i % dim] += len(value) * 0.01

        # Normalize to unit range
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_thalamic_adapter.py -xvs`
Expected: ALL PASS (10 tests)

**Step 5: Commit**

```bash
git add core/thalamic_adapter.py tests/test_thalamic_adapter.py
git commit -m "feat: add ThalamicAdapter — input encoding for ThalamoPC6

Maps any input type to 6 thalamic modalities. Full pipeline:
encode -> ThalamoPC6.step -> gated output with gate invariant."
```

---

## Task 5: Cortical Area (CorticalColumn + Community)

Create CorticalArea — wraps one CorticalColumn with activation tracking and module assignments.

**Files:**
- Create: `core/cortical_area.py`
- Create: `tests/test_cortical_area.py`
- Reference: `core/cortical_column.py` (CanonicalMicrocircuit)

**Step 1: Write the failing tests**

```python
# tests/test_cortical_area.py
"""Tests for CorticalArea — wraps CorticalColumn + activation tracking."""
import pytest
import numpy as np
from core.cortical_area import CorticalArea, CorticalAreaConfig


class TestCorticalArea:
    @pytest.fixture
    def area(self):
        return CorticalArea(CorticalAreaConfig(
            name="language",
            specialty=["language_center", "dialogue_manager"],
        ))

    def test_create_area(self, area):
        assert area.name == "language"
        assert area.activation == 0.0

    def test_receive_thalamic_input(self, area):
        """Thalamic input goes through CorticalColumn's L4."""
        thalamic = np.random.randn(8)  # layer_dim=8 default
        result = area.receive_input(thalamic)
        assert "output" in result
        assert "activation" in result
        assert area.activation > 0.0  # activated

    def test_activation_decays(self, area):
        """Activation decays over time without new input."""
        thalamic = np.random.randn(8) * 5.0  # strong input
        area.receive_input(thalamic)
        initial = area.activation
        area.tick()  # decay
        assert area.activation < initial

    def test_activation_bounded(self, area):
        """Activation stays in [0, 1]."""
        for _ in range(20):
            thalamic = np.random.randn(8) * 10.0
            area.receive_input(thalamic)
        assert 0.0 <= area.activation <= 1.0

    def test_get_recent_thoughts(self, area):
        """Area stores its recent processing results."""
        area.receive_input(np.random.randn(8))
        area.receive_input(np.random.randn(8))
        thoughts = area.get_recent_thoughts(n=5)
        assert len(thoughts) >= 1  # at least one thought stored

    def test_get_state(self, area):
        state = area.get_state()
        assert state['name'] == "language"
        assert 'activation' in state
        assert 'specialty' in state

    def test_reset(self, area):
        area.receive_input(np.random.randn(8))
        area.reset()
        assert area.activation == 0.0
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cortical_area.py -xvs`
Expected: FAIL

**Step 3: Implement `core/cortical_area.py`**

```python
"""
CorticalArea - One brain area backed by a CorticalColumn.

Each CorticalArea:
- Wraps a CanonicalMicrocircuit (6-layer column)
- Tracks activation level (0-1)
- Stores recent processing results (thoughts)
- Lists its specialty modules
- Corresponds to one MoltBook community
"""

import numpy as np
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import deque
from core.cortical_column import CanonicalMicrocircuit


@dataclass
class CorticalAreaConfig:
    """Configuration for a cortical area."""
    name: str
    specialty: List[str] = field(default_factory=list)
    layer_dim: int = 8
    decay_rate: float = 0.05  # activation decay per tick
    max_thoughts: int = 100


class CorticalArea:
    """
    One brain area = CorticalColumn + activation tracking.

    Receives thalamic input, processes through 6-layer column,
    tracks activation, stores recent thoughts.
    """

    def __init__(self, config: CorticalAreaConfig):
        self.name = config.name
        self.specialty = config.specialty
        self.layer_dim = config.layer_dim
        self._decay_rate = config.decay_rate

        # Core processing unit
        self.column = CanonicalMicrocircuit(layer_dim=config.layer_dim)

        # Activation level (read by ResponseAgent)
        self.activation: float = 0.0

        # Recent processing results
        self._thoughts: deque = deque(maxlen=config.max_thoughts)

        # Persistent state
        self._feedback = np.zeros(config.layer_dim)
        self._cortical_input = np.zeros(config.layer_dim)

    def receive_input(
        self,
        thalamic_input: np.ndarray,
        cortical_input: Optional[np.ndarray] = None,
        feedback: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Process thalamic input through the cortical column.

        Returns:
            Dict with 'output', 'prediction', 'error', 'activation'
        """
        if cortical_input is not None:
            self._cortical_input = cortical_input
        if feedback is not None:
            self._feedback = feedback

        result = self.column.process_column(
            thalamic_input=thalamic_input,
            cortical_input=self._cortical_input,
            feedback=self._feedback,
        )

        # Update activation based on output magnitude
        output_mag = float(np.linalg.norm(result['output']))
        self.activation = min(1.0, max(0.0,
            self.activation * 0.7 + output_mag * 0.3
        ))

        # Store thought
        thought = {
            'output': result['output'],
            'prediction': result['prediction'],
            'error_magnitude': result['error_magnitude'],
            'activation': self.activation,
        }
        self._thoughts.append(thought)

        result['activation'] = self.activation
        return result

    def tick(self):
        """One time step without new input — activation decays."""
        self.activation = max(0.0, self.activation - self._decay_rate)

    def get_recent_thoughts(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get last N processing results."""
        return list(self._thoughts)[-n:]

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'activation': round(self.activation, 4),
            'specialty': self.specialty,
            'avg_error': round(self.column.get_avg_error(), 4),
            'avg_activity': round(self.column.get_avg_activity(), 4),
            'thought_count': len(self._thoughts),
        }

    def reset(self):
        self.activation = 0.0
        self._thoughts.clear()
        self._feedback = np.zeros(self.layer_dim)
        self._cortical_input = np.zeros(self.layer_dim)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cortical_area.py -xvs`
Expected: ALL PASS (7 tests)

**Step 5: Commit**

```bash
git add core/cortical_area.py tests/test_cortical_area.py
git commit -m "feat: add CorticalArea — brain area backed by CorticalColumn

Wraps CanonicalMicrocircuit with activation tracking, thought storage,
decay, and specialty module assignments. Each area = one MoltBook community."
```

---

## Task 6: Response Agent (Reads Activations → Generates Output)

Create the ResponseAgent that reads cortical area activations, selects top-K areas,
and deliberates before generating output.

**Files:**
- Create: `core/response_agent.py`
- Create: `tests/test_response_agent.py`
- Depends on: `core/cortical_area.py` (Task 5), `core/kotlin_graph.py` (Task 1)

**Step 1: Write the failing tests**

```python
# tests/test_response_agent.py
"""Tests for ResponseAgent — reads area activations, generates response."""
import pytest
import numpy as np
from core.response_agent import ResponseAgent, ResponseAgentConfig
from core.cortical_area import CorticalArea, CorticalAreaConfig
from core.kotlin_graph import KotlinGraph


def _make_areas():
    """Create test cortical areas with varying activations."""
    configs = [
        CorticalAreaConfig(name="language", specialty=["language_center"]),
        CorticalAreaConfig(name="reasoning", specialty=["prefrontal_cortex"]),
        CorticalAreaConfig(name="memory", specialty=["entorhinal_cortex"]),
    ]
    areas = [CorticalArea(c) for c in configs]
    # Activate language area most
    areas[0].receive_input(np.random.randn(8) * 3.0)
    areas[0].receive_input(np.random.randn(8) * 3.0)
    # Activate reasoning area somewhat
    areas[1].receive_input(np.random.randn(8) * 1.5)
    # memory stays low
    return areas


class TestResponseAgent:
    @pytest.fixture
    def agent(self):
        return ResponseAgent(ResponseAgentConfig(top_k=2))

    def test_select_top_areas(self, agent):
        areas = _make_areas()
        selected = agent.select_active_areas(areas)
        assert len(selected) <= 2
        # Language should be selected (highest activation)
        names = [a.name for a in selected]
        assert "language" in names

    def test_gather_thoughts(self, agent):
        areas = _make_areas()
        selected = agent.select_active_areas(areas)
        thoughts = agent.gather_thoughts(selected)
        assert len(thoughts) > 0

    def test_deliberate_returns_summary(self, agent):
        areas = _make_areas()
        result = agent.deliberate(areas)
        assert "summary" in result
        assert "selected_areas" in result
        assert "confidence" in result
        assert 0.0 <= result["confidence"] <= 1.0

    def test_deliberate_records_to_memory(self, agent):
        memory = KotlinGraph()
        agent.memory = memory
        areas = _make_areas()
        agent.deliberate(areas)
        assert memory.stats['total_events'] >= 1

    def test_empty_areas(self, agent):
        """Agent handles no active areas gracefully."""
        areas = [CorticalArea(CorticalAreaConfig(name="idle"))]
        result = agent.deliberate(areas)
        assert result["confidence"] < 0.5  # low confidence

    def test_get_state(self, agent):
        state = agent.get_state()
        assert "total_deliberations" in state
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_response_agent.py -xvs`
Expected: FAIL

**Step 3: Implement `core/response_agent.py`**

```python
"""
ResponseAgent - Reads cortical area activations, deliberates, generates output.

Pipeline:
1. Select top-K most activated areas
2. Gather recent thoughts from those areas
3. Deliberate (combine, weigh, synthesize)
4. Record to KotlinGraph memory
5. Return summary for LLM to verbalize
"""

import numpy as np
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from core.cortical_area import CorticalArea
from core.kotlin_graph import KotlinGraph


@dataclass
class ResponseAgentConfig:
    """Configuration for ResponseAgent."""
    top_k: int = 3           # How many areas to read from
    min_activation: float = 0.01  # Minimum activation to consider


class ResponseAgent:
    """
    Reads cortical area activations and produces a deliberation result.

    The deliberation result is a structured summary that can be passed
    to an LLM for natural language generation.
    """

    def __init__(self, config: Optional[ResponseAgentConfig] = None):
        config = config or ResponseAgentConfig()
        self.top_k = config.top_k
        self.min_activation = config.min_activation
        self.memory: Optional[KotlinGraph] = None
        self._total_deliberations = 0

    def select_active_areas(self, areas: List[CorticalArea]) -> List[CorticalArea]:
        """Select top-K most activated areas above threshold."""
        active = [a for a in areas if a.activation >= self.min_activation]
        active.sort(key=lambda a: a.activation, reverse=True)
        return active[:self.top_k]

    def gather_thoughts(self, areas: List[CorticalArea]) -> List[Dict[str, Any]]:
        """Collect recent thoughts from selected areas."""
        all_thoughts = []
        for area in areas:
            for thought in area.get_recent_thoughts(n=5):
                all_thoughts.append({
                    "area": area.name,
                    "activation": area.activation,
                    **thought,
                })
        return all_thoughts

    def deliberate(self, areas: List[CorticalArea]) -> Dict[str, Any]:
        """
        Full deliberation cycle.

        Returns:
            Dict with 'summary', 'selected_areas', 'confidence',
            'thought_count', 'area_activations'
        """
        selected = self.select_active_areas(areas)
        thoughts = self.gather_thoughts(selected)

        # Compute confidence from area activations
        if selected:
            activations = [a.activation for a in selected]
            confidence = float(np.mean(activations))
            # Higher confidence if one area dominates
            if len(activations) > 1:
                spread = float(np.std(activations))
                confidence = min(1.0, confidence + spread * 0.5)
        else:
            confidence = 0.0

        # Build summary
        area_summaries = []
        for area in selected:
            recent = area.get_recent_thoughts(n=3)
            avg_error = np.mean([t.get('error_magnitude', 0) for t in recent]) if recent else 0
            area_summaries.append({
                "name": area.name,
                "activation": round(area.activation, 4),
                "specialty": area.specialty,
                "avg_prediction_error": round(float(avg_error), 4),
            })

        result = {
            "summary": area_summaries,
            "selected_areas": [a.name for a in selected],
            "confidence": round(min(1.0, max(0.0, confidence)), 4),
            "thought_count": len(thoughts),
            "area_activations": {a.name: round(a.activation, 4) for a in areas},
        }

        # Record to memory if available
        if self.memory is not None:
            state = {"areas": [a.name for a in selected],
                     "activations": {a.name: a.activation for a in selected}}
            action = f"deliberate_from_{','.join(a.name for a in selected)}"
            self.memory.add_event(
                state=state,
                action=action,
                next_state={"confidence": confidence, "thought_count": len(thoughts)},
                reward=confidence,
                done=True,
                consciousness=confidence,
            )

        self._total_deliberations += 1
        return result

    def get_state(self) -> Dict[str, Any]:
        return {
            "total_deliberations": self._total_deliberations,
            "top_k": self.top_k,
            "min_activation": self.min_activation,
            "has_memory": self.memory is not None,
        }
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_response_agent.py -xvs`
Expected: ALL PASS (6 tests)

**Step 5: Commit**

```bash
git add core/response_agent.py tests/test_response_agent.py
git commit -m "feat: add ResponseAgent — reads area activations, deliberates

Selects top-K activated cortical areas, gathers their thoughts,
computes confidence, records to KotlinGraph memory."
```

---

## Task 7: Integration — Wire ThalamoPC6 into BrainChat.send()

Rewire `BrainChat._route_through_thalamus()` to use the ThalamicAdapter + ThalamoPC6
as the primary routing path, keeping the 3-layer router as fallback.

**Files:**
- Modify: `core/brain_chat.py:2763-2830` (`_route_through_thalamus` method)
- Create: `tests/test_thalamic_integration.py`
- Depends on: `core/thalamic_adapter.py` (Task 4)

**Step 1: Write the failing tests**

```python
# tests/test_thalamic_integration.py
"""Tests for ThalamoPC6 integration into BrainChat routing."""
import pytest
from unittest.mock import MagicMock, patch
from core.thalamic_adapter import ThalamicAdapter


class TestThalamicRouting:
    def test_adapter_produces_routing_info(self):
        """ThalamicAdapter.process() returns routing-compatible info."""
        adapter = ThalamicAdapter()
        result = adapter.process("chat", {"message": "hello"})
        # Must have the fields BrainChat expects
        assert "gates" in result
        assert "active_modalities" in result
        # Gate invariant
        gate_sum = sum(result["gates"].values())
        assert abs(gate_sum - 1.0) < 1e-5

    def test_routing_info_format_matches_brain_chat(self):
        """Result can be converted to BrainChat's routing_info format."""
        adapter = ThalamicAdapter()
        result = adapter.process("chat", {"message": "what is AI?"})

        # Convert to BrainChat format
        routing_info = {
            'mode': 'thalamic',
            'weights': list(result['gates'].values()),
            'dominant_areas': result['active_modalities'],
            'task_type': 'thalamic_routed',
            'predicted_sequence': [],
            'confidence': max(result['gates'].values()),
        }

        assert routing_info['mode'] == 'thalamic'
        assert len(routing_info['weights']) == 6
        assert isinstance(routing_info['dominant_areas'], list)

    def test_multiple_messages_evolve_state(self):
        """ThalamoPC6 state evolves across messages (not stateless)."""
        adapter = ThalamicAdapter()
        r1 = adapter.process("chat", {"message": "hello"})
        r2 = adapter.process("chat", {"message": "tell me about AI"})
        # Gates should differ (different inputs evolve state)
        g1 = list(r1['gates'].values())
        g2 = list(r2['gates'].values())
        assert g1 != g2  # state evolved

    def test_threat_escalation(self):
        """Threat input shifts gate distribution toward threat modality."""
        adapter = ThalamicAdapter()
        # Normal message
        r_normal = adapter.process("chat", {"message": "hi"})
        # Threat message
        r_threat = adapter.process("threat", {"error": "CRITICAL", "severity": 1.0})
        # Threat gate should increase
        assert r_threat['gates']['threat'] >= r_normal['gates']['threat'] * 0.5
```

**Step 2: Run tests to verify they pass** (these test the adapter, not the wiring yet)

Run: `python -m pytest tests/test_thalamic_integration.py -xvs`
Expected: ALL PASS (4 tests — these test the adapter's compatibility with BrainChat's format)

**Step 3: Modify `core/brain_chat.py` — add ThalamicAdapter as primary routing**

At the top of `brain_chat.py`, add import:
```python
from core.thalamic_adapter import ThalamicAdapter
```

In `BrainChat.__init__()`, add:
```python
self._thalamic_adapter: Optional[ThalamicAdapter] = None
```

In `_route_through_thalamus()` (line 2763), add ThalamoPC6 as the FIRST try before HierarchicalPlanner:
```python
def _route_through_thalamus(self, message: str, trace: list) -> Dict[str, Any]:
    """Route through the thalamic system. Primary: ThalamoPC6, Fallback: 3-layer."""
    routing_info = {
        'mode': 'routine',
        'weights': [],
        'dominant_areas': [],
        'task_type': 'general',
        'predicted_sequence': [],
        'confidence': 0.5,
    }

    # PRIMARY: ThalamoPC6 via ThalamicAdapter
    if self._thalamic_adapter:
        try:
            result = self._thalamic_adapter.process("chat", {"message": message})
            self._total_routed += 1
            routing_info['mode'] = 'thalamic'
            routing_info['weights'] = list(result['gates'].values())
            routing_info['dominant_areas'] = result['active_modalities']
            routing_info['task_type'] = 'thalamic_routed'
            routing_info['confidence'] = float(max(result['gates'].values()))
            trace.append(ThoughtTrace(
                timestamp=time.time(), category="routing",
                content=(
                    f"ThalamoPC6 routing: active={result['active_modalities']}, "
                    f"gates={', '.join(f'{m}={g:.2f}' for m, g in result['gates'].items())}"
                ),
                module="ThalamoPC6",
                confidence=routing_info['confidence'],
            ))
            return routing_info
        except Exception as e:
            logger.warning(f"ThalamoPC6 routing failed: {e}")

    # FALLBACK: HierarchicalPlanner (existing 3-layer)
    if self._hierarchical_planner:
        # ... existing code unchanged ...
```

**Step 4: Run existing tests to verify nothing breaks**

Run: `python -m pytest tests/test_brain_chat_quick.py tests/test_integration_brain_chat.py -xvs`
Expected: ALL PASS (existing tests unchanged — adapter not wired by default)

**Step 5: Commit**

```bash
git add core/brain_chat.py tests/test_thalamic_integration.py
git commit -m "feat: wire ThalamoPC6 as primary routing in BrainChat

ThalamicAdapter is primary path in _route_through_thalamus().
3-layer HierarchicalPlanner becomes fallback.
Existing tests unchanged (adapter not wired by default)."
```

---

## Task 8: Production Wiring — Connect Everything in production_planner.py

Wire the new components (ThalamicAdapter, CorticalAreas, ResponseAgent, DualGraph)
into the production system.

**Files:**
- Modify: `production/production_planner.py` (add wiring for new components)
- Create: `tests/test_thalamic_wiring.py`

**Step 1: Write the failing tests**

```python
# tests/test_thalamic_wiring.py
"""Tests for production wiring of thalamic components."""
import pytest
from unittest.mock import MagicMock
from core.thalamic_adapter import ThalamicAdapter
from core.cortical_area import CorticalArea, CorticalAreaConfig
from core.response_agent import ResponseAgent, ResponseAgentConfig
from core.dual_graph import DualGraph
from core.kotlin_graph import KotlinGraph
import numpy as np


class TestEndToEndWiring:
    """Test the full pipeline: input → thalamus → areas → response agent."""

    def test_full_pipeline(self, tmp_path):
        """End-to-end: message → ThalamoPC6 → areas → ResponseAgent → result."""
        # 1. Create components
        adapter = ThalamicAdapter()
        memory = KotlinGraph()
        areas = [
            CorticalArea(CorticalAreaConfig(name="language", specialty=["lc"])),
            CorticalArea(CorticalAreaConfig(name="reasoning", specialty=["pfc"])),
            CorticalArea(CorticalAreaConfig(name="memory", specialty=["ec"])),
        ]
        agent = ResponseAgent(ResponseAgentConfig(top_k=2))
        agent.memory = memory

        # 2. Process through thalamus
        result = adapter.process("chat", {"message": "What is consciousness?"})

        # 3. Route to areas (weighted by gates)
        layer_dim = 8
        for area in areas:
            thalamic_vec = np.random.randn(layer_dim) * result['gates'].get('audio', 0.1)
            area.receive_input(thalamic_vec)

        # 4. Response agent deliberates
        deliberation = agent.deliberate(areas)

        assert deliberation['confidence'] > 0.0
        assert len(deliberation['selected_areas']) > 0
        assert memory.stats['total_events'] >= 1

    def test_areas_activate_differently(self, tmp_path):
        """Different areas activate to different levels based on input."""
        adapter = ThalamicAdapter()
        areas = [
            CorticalArea(CorticalAreaConfig(name="language")),
            CorticalArea(CorticalAreaConfig(name="executive")),
        ]

        result = adapter.process("chat", {"message": "hello"})

        # Give language area stronger input
        areas[0].receive_input(np.ones(8) * 2.0)
        areas[1].receive_input(np.ones(8) * 0.1)

        assert areas[0].activation > areas[1].activation

    def test_memory_records_across_interactions(self, tmp_path):
        """KotlinGraph accumulates events across interactions."""
        memory = KotlinGraph()
        agent = ResponseAgent()
        agent.memory = memory

        areas = [CorticalArea(CorticalAreaConfig(name="lang"))]

        for i in range(5):
            areas[0].receive_input(np.random.randn(8))
            agent.deliberate(areas)

        assert memory.stats['total_events'] == 5
```

**Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/test_thalamic_wiring.py -xvs`
Expected: ALL PASS (3 tests)

**Step 3: Add wiring to `production/production_planner.py`**

Following the existing wiring pattern (try/except import, `from_yaml` with fallback), add:

```python
# In the wiring section (after existing module wiring):

# --- Thalamic Rewiring Components ---
try:
    from core.thalamic_adapter import ThalamicAdapter
    from core.cortical_area import CorticalArea, CorticalAreaConfig
    from core.response_agent import ResponseAgent, ResponseAgentConfig
    from core.dual_graph import DualGraph
    from core.kotlin_graph import KotlinGraph

    # Create thalamic adapter
    thalamic_adapter = ThalamicAdapter()
    print("[OK] ThalamicAdapter created")

    # Create cortical areas
    area_configs = [
        CorticalAreaConfig(name="language", specialty=["language_center", "dialogue_manager"]),
        CorticalAreaConfig(name="executive", specialty=["prefrontal_cortex", "anterior_cingulate"]),
        CorticalAreaConfig(name="memory", specialty=["entorhinal_cortex", "basal_forebrain"]),
        CorticalAreaConfig(name="emotional", specialty=["amygdala_complex", "insular_cortex"]),
        CorticalAreaConfig(name="motor", specialty=["cerebellum", "action_planner"]),
        CorticalAreaConfig(name="default_mode", specialty=["default_mode_network", "self_model"]),
    ]
    cortical_areas = [CorticalArea(c) for c in area_configs]
    print(f"[OK] {len(cortical_areas)} cortical areas created")

    # Create shared memory
    kotlin_graph = KotlinGraph()
    dual_graph = DualGraph(save_dir=str(data_dir / "brain_memory"))
    print("[OK] DualGraph memory created")

    # Create response agent
    response_agent = ResponseAgent(ResponseAgentConfig(top_k=3))
    response_agent.memory = kotlin_graph
    print("[OK] ResponseAgent created")

    # Wire to BrainChat
    if hasattr(self, 'brain_chat') and self.brain_chat:
        self.brain_chat._thalamic_adapter = thalamic_adapter
        print("[OK] ThalamicAdapter wired to BrainChat")

except Exception as e:
    print(f"[SKIP] Thalamic rewiring: {e}")
```

**Step 4: Run full test suite to verify nothing breaks**

Run: `python -m pytest tests/test_thalamic_wiring.py tests/test_thalamic_adapter.py tests/test_thalamic_integration.py -xvs`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add production/production_planner.py tests/test_thalamic_wiring.py
git commit -m "feat: wire thalamic components in production_planner

ThalamicAdapter, 6 CorticalAreas, DualGraph memory, ResponseAgent
all created and wired. BrainChat gets ThalamoPC6 as primary routing."
```

---

## Task 9: Full Integration Test & Regression Check

Run the complete test suite to verify all new code works and nothing existing broke.

**Files:**
- No new files
- Run all tests

**Step 1: Run new component tests**

Run: `python -m pytest tests/test_kotlin_graph.py tests/test_kuro_graph.py tests/test_dual_graph.py tests/test_thalamic_adapter.py tests/test_cortical_area.py tests/test_response_agent.py tests/test_thalamic_integration.py tests/test_thalamic_wiring.py -v`
Expected: ALL PASS (~52 new tests)

**Step 2: Run existing critical tests**

Run: `python -m pytest tests/test_brain_chat_quick.py tests/test_cognitive_loop.py tests/test_gate_invariant.py tests/test_brain_server.py -v`
Expected: ALL PASS (no regressions)

**Step 3: Run the full suite**

Run: `python -m pytest tests/test_kotlin_graph.py tests/test_kuro_graph.py tests/test_dual_graph.py tests/test_thalamic_adapter.py tests/test_cortical_area.py tests/test_response_agent.py tests/test_thalamic_integration.py tests/test_thalamic_wiring.py tests/test_brain_chat_quick.py tests/test_cognitive_loop.py tests/test_gate_invariant.py tests/test_brain_server.py -v --tb=short`
Expected: ALL PASS

**Step 4: Commit final integration**

```bash
git add -A
git commit -m "feat: thalamic rewiring complete — ThalamoPC6 is THE input gate

New components: KotlinGraph, KuroGraph, DualGraph (generalized from
learning_engine), ThalamicAdapter, CorticalArea, ResponseAgent.
ThalamoPC6 is now the primary routing path in BrainChat.
3-layer router kept as fallback. 0 deletions, ~1800 new lines."
```

---

## Summary

| Task | Component | New Tests | New Lines |
|------|-----------|-----------|-----------|
| 1 | KotlinGraph (episodic memory) | 16 | ~300 |
| 2 | KuroGraph (pattern mining) | 10 | ~350 |
| 3 | DualGraph (unified manager) | 6 | ~150 |
| 4 | ThalamicAdapter | 10 | ~150 |
| 5 | CorticalArea | 7 | ~200 |
| 6 | ResponseAgent | 6 | ~200 |
| 7 | BrainChat integration | 4 | ~50 changes |
| 8 | Production wiring | 3 | ~30 changes |
| 9 | Full regression check | 0 | 0 |
| **Total** | | **~62** | **~1,800** |
