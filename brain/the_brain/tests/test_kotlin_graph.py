"""
Tests for core/kotlin_graph.py - Domain-Agnostic KotlinGraph (Episodic Memory)

Ported from learning_engine/klotski/neurosymbolic/memory/kotlingraph.py.
Generalized from np.ndarray states + int actions to Dict[str, Any] states + str actions.
"""

import json
import os
import pytest
from typing import Dict, Any

from core.kotlin_graph import BrainEvent, KotlinGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_state(label: str, x: int = 0, y: int = 0, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Create a simple test state dict."""
    s = {"label": label, "x": x, "y": y}
    if extra:
        s.update(extra)
    return s


def add_simple_episode(kg: KotlinGraph, n_steps: int = 3, episode_label: str = "ep") -> int:
    """Add a simple episode of n_steps transitions, last step done=True.
    Returns the episode_id that was used."""
    ep_id = kg.current_episode_id
    for i in range(n_steps):
        state = make_state(f"{episode_label}_s{i}", x=i)
        next_state = make_state(f"{episode_label}_s{i+1}", x=i + 1)
        action = f"move_{i}"
        reward = 1.0 if i == n_steps - 1 else 0.0
        done = (i == n_steps - 1)
        kg.add_event(
            state=state,
            action=action,
            next_state=next_state,
            reward=reward,
            done=done,
        )
    return ep_id


# ===================================================================
# BrainEvent
# ===================================================================

class TestBrainEvent:

    def test_creation_with_dict_states(self):
        """BrainEvent stores dict states and str action."""
        state = {"a": 1, "b": [2, 3]}
        next_state = {"a": 2, "b": [3, 4]}
        ev = BrainEvent(
            event_id=0,
            timestamp="2026-01-01T00:00:00",
            state=state,
            action="push",
            next_state=next_state,
            reward=1.0,
            done=False,
        )
        assert ev.state == state
        assert ev.next_state == next_state
        assert ev.action == "push"
        assert ev.reward == 1.0
        assert ev.done is False
        assert ev.event_id == 0

    def test_default_fields(self):
        """Optional fields have sensible defaults."""
        ev = BrainEvent(
            event_id=0,
            timestamp="t",
            state={},
            action="noop",
            next_state={},
            reward=0.0,
            done=False,
        )
        assert ev.value == 0.0
        assert ev.policy_entropy == 0.0
        assert ev.consciousness == 0.0
        assert ev.dmn_energy == 0.0
        assert ev.episode_id == 0
        assert ev.step_in_episode == 0
        assert ev.metadata == {}

    def test_state_hash_deterministic(self):
        """Same state dict produces the same hash every time."""
        state = {"x": 1, "y": 2, "label": "test"}
        ev1 = BrainEvent(0, "t", state, "a", {}, 0, False)
        ev2 = BrainEvent(1, "t", state, "b", {}, 0, False)
        assert ev1.state_hash() == ev2.state_hash()

    def test_state_hash_key_order_independent(self):
        """Dicts with same keys in different insertion order produce same hash."""
        state_a = {"z": 3, "a": 1, "m": 2}
        state_b = {"a": 1, "m": 2, "z": 3}
        ev_a = BrainEvent(0, "t", state_a, "a", {}, 0, False)
        ev_b = BrainEvent(0, "t", state_b, "a", {}, 0, False)
        assert ev_a.state_hash() == ev_b.state_hash()

    def test_different_states_different_hashes(self):
        """Different state dicts produce different hashes."""
        ev1 = BrainEvent(0, "t", {"a": 1}, "a", {}, 0, False)
        ev2 = BrainEvent(0, "t", {"a": 2}, "a", {}, 0, False)
        assert ev1.state_hash() != ev2.state_hash()

    def test_next_state_hash(self):
        """next_state_hash() hashes the next_state field."""
        ev = BrainEvent(0, "t", {"a": 1}, "a", {"b": 2}, 0, False)
        # Should be based on next_state, not state
        ev2 = BrainEvent(0, "t", {"b": 2}, "a", {"c": 3}, 0, False)
        assert ev.next_state_hash() == ev2.state_hash()

    def test_state_hash_with_nested_structures(self):
        """Handles nested dicts/lists deterministically."""
        state = {"config": {"layers": [1, 2, 3]}, "name": "test"}
        ev1 = BrainEvent(0, "t", state, "a", {}, 0, False)
        ev2 = BrainEvent(1, "t", state, "a", {}, 0, False)
        assert ev1.state_hash() == ev2.state_hash()

    def test_state_hash_with_default_str(self):
        """json.dumps with default=str handles non-standard types gracefully."""
        from datetime import datetime
        state = {"time": datetime(2026, 1, 1), "value": 42}
        ev = BrainEvent(0, "t", state, "a", {}, 0, False)
        # Should not raise
        h = ev.state_hash()
        assert isinstance(h, str)
        assert len(h) > 0


# ===================================================================
# KotlinGraph - Basic Operations
# ===================================================================

class TestKotlinGraphBasic:

    def test_init(self):
        """Fresh graph has empty state."""
        kg = KotlinGraph()
        assert kg.stats['total_events'] == 0
        assert kg.stats['total_episodes'] == 0
        assert kg.stats['total_states'] == 0
        assert kg.stats['total_transitions'] == 0
        assert len(kg.events) == 0
        assert len(kg.state_index) == 0
        assert kg.current_episode_id == 0

    def test_add_event_returns_sequential_ids(self):
        """add_event returns monotonically increasing event IDs."""
        kg = KotlinGraph()
        id0 = kg.add_event({"a": 1}, "go", {"a": 2}, 0.0, False)
        id1 = kg.add_event({"a": 2}, "go", {"a": 3}, 0.0, False)
        id2 = kg.add_event({"a": 3}, "go", {"a": 4}, 1.0, True)
        assert id0 == 0
        assert id1 == 1
        assert id2 == 2

    def test_add_event_creates_graph_nodes(self):
        """Each unique state gets a node in the graph."""
        kg = KotlinGraph()
        kg.add_event({"s": "A"}, "act", {"s": "B"}, 0.0, False)
        # Two unique states -> two nodes
        assert kg.graph.number_of_nodes() == 2
        assert kg.stats['total_states'] == 2

    def test_add_event_creates_graph_edges(self):
        """Each transition creates a directed edge."""
        kg = KotlinGraph()
        kg.add_event({"s": "A"}, "act", {"s": "B"}, 0.0, False)
        assert kg.graph.number_of_edges() == 1
        assert kg.stats['total_transitions'] == 1

    def test_duplicate_states_share_node(self):
        """Revisiting a state reuses the existing node, not creating a new one."""
        kg = KotlinGraph()
        # A -> B
        kg.add_event({"s": "A"}, "right", {"s": "B"}, 0.0, False)
        # B -> A (A already exists)
        kg.add_event({"s": "B"}, "left", {"s": "A"}, 0.0, False)
        # Only 2 unique states
        assert kg.graph.number_of_nodes() == 2
        assert kg.stats['total_states'] == 2
        # But 2 edges
        assert kg.graph.number_of_edges() == 2

    def test_visit_count_incremented(self):
        """Visit count on source node increments on each transition from that state."""
        kg = KotlinGraph()
        kg.add_event({"s": "A"}, "go", {"s": "B"}, 0.0, False)
        kg.add_event({"s": "A"}, "go", {"s": "C"}, 0.0, False)
        # Node for state A should have visit_count=2
        state_hash = json.dumps({"s": "A"}, sort_keys=True, default=str)
        h = str(hash(state_hash))
        node_id = kg.state_index[h]
        assert kg.graph.nodes[node_id]['visit_count'] == 2

    def test_get_event(self):
        """get_event retrieves the correct BrainEvent by id."""
        kg = KotlinGraph()
        kg.add_event({"x": 1}, "act", {"x": 2}, 0.5, False, value=0.8)
        ev = kg.get_event(0)
        assert ev.state == {"x": 1}
        assert ev.next_state == {"x": 2}
        assert ev.action == "act"
        assert ev.reward == 0.5
        assert ev.value == 0.8

    def test_metadata_stored(self):
        """Optional metadata dict is preserved on the event."""
        kg = KotlinGraph()
        meta = {"source": "test", "priority": 3}
        kg.add_event({"a": 1}, "go", {"a": 2}, 0.0, False, metadata=meta)
        ev = kg.get_event(0)
        assert ev.metadata == meta

    def test_brain_metrics_stored(self):
        """Brain metrics (value, entropy, consciousness, dmn) are stored."""
        kg = KotlinGraph()
        kg.add_event(
            {"a": 1}, "go", {"a": 2}, 0.0, False,
            value=0.7, policy_entropy=0.3, consciousness=0.9, dmn_energy=0.1
        )
        ev = kg.get_event(0)
        assert ev.value == 0.7
        assert ev.policy_entropy == 0.3
        assert ev.consciousness == 0.9
        assert ev.dmn_energy == 0.1


# ===================================================================
# KotlinGraph - Episode Tracking
# ===================================================================

class TestKotlinGraphEpisodes:

    def test_episode_advances_on_done(self):
        """done=True advances the episode counter."""
        kg = KotlinGraph()
        kg.add_event({"s": 0}, "a", {"s": 1}, 0.0, False)
        assert kg.current_episode_id == 0
        kg.add_event({"s": 1}, "a", {"s": 2}, 1.0, True)  # done
        assert kg.current_episode_id == 1
        assert kg.stats['total_episodes'] == 1

    def test_multiple_episodes(self):
        """Multiple episodes are tracked separately."""
        kg = KotlinGraph()
        # Episode 0: 2 steps
        kg.add_event({"s": "a"}, "go", {"s": "b"}, 0.0, False)
        kg.add_event({"s": "b"}, "go", {"s": "c"}, 1.0, True)
        # Episode 1: 1 step
        kg.add_event({"s": "d"}, "go", {"s": "e"}, 1.0, True)

        assert kg.stats['total_episodes'] == 2
        assert len(kg.episodes[0]) == 2
        assert len(kg.episodes[1]) == 1

    def test_get_episode(self):
        """get_episode returns the correct BrainEvent list for an episode."""
        kg = KotlinGraph()
        add_simple_episode(kg, n_steps=3, episode_label="ep0")
        add_simple_episode(kg, n_steps=2, episode_label="ep1")

        ep0_events = kg.get_episode(0)
        assert len(ep0_events) == 3
        assert ep0_events[0].state["label"] == "ep0_s0"
        assert ep0_events[2].done is True

        ep1_events = kg.get_episode(1)
        assert len(ep1_events) == 2
        assert ep1_events[0].state["label"] == "ep1_s0"

    def test_get_episode_empty(self):
        """get_episode for non-existent episode returns empty list."""
        kg = KotlinGraph()
        assert kg.get_episode(999) == []

    def test_get_episode_trajectory(self):
        """get_episode_trajectory returns (states, actions, rewards) tuple."""
        kg = KotlinGraph()
        add_simple_episode(kg, n_steps=3, episode_label="traj")

        states, actions, rewards = kg.get_episode_trajectory(0)
        assert len(states) == 3
        assert len(actions) == 3
        assert len(rewards) == 3
        assert states[0] == make_state("traj_s0", x=0)
        assert actions[0] == "move_0"
        assert rewards[-1] == 1.0  # last step reward
        assert rewards[0] == 0.0   # non-terminal reward

    def test_get_episode_trajectory_empty(self):
        """Trajectory for non-existent episode returns empty lists."""
        kg = KotlinGraph()
        states, actions, rewards = kg.get_episode_trajectory(999)
        assert states == []
        assert actions == []
        assert rewards == []

    def test_step_in_episode_tracked(self):
        """Each event knows its step within the episode."""
        kg = KotlinGraph()
        add_simple_episode(kg, n_steps=4)
        for i in range(4):
            assert kg.get_event(i).step_in_episode == i

    def test_episode_id_on_events(self):
        """Events carry the correct episode_id."""
        kg = KotlinGraph()
        add_simple_episode(kg, n_steps=2, episode_label="e0")  # ep 0
        add_simple_episode(kg, n_steps=2, episode_label="e1")  # ep 1
        assert kg.get_event(0).episode_id == 0
        assert kg.get_event(1).episode_id == 0
        assert kg.get_event(2).episode_id == 1
        assert kg.get_event(3).episode_id == 1


# ===================================================================
# KotlinGraph - Graph Queries
# ===================================================================

class TestKotlinGraphQueries:

    def test_get_state_transitions(self):
        """get_state_transitions returns action, next_node, avg_reward."""
        kg = KotlinGraph()
        # From A: go_right -> B (reward 0.5), go_left -> C (reward 1.0)
        kg.add_event({"s": "A"}, "go_right", {"s": "B"}, 0.5, False)
        kg.add_event({"s": "A"}, "go_left", {"s": "C"}, 1.0, False)

        state_hash = BrainEvent(0, "t", {"s": "A"}, "", {}, 0, False).state_hash()
        transitions = kg.get_state_transitions(state_hash)
        assert len(transitions) == 2

        trans_dict = {action: avg_r for action, _, avg_r in transitions}
        assert abs(trans_dict["go_right"] - 0.5) < 1e-6
        assert abs(trans_dict["go_left"] - 1.0) < 1e-6

    def test_get_state_transitions_avg_reward(self):
        """Multiple transitions with same action average the rewards."""
        kg = KotlinGraph()
        # Two go_right from A: rewards 0.0 and 1.0 -> avg 0.5
        kg.add_event({"s": "A"}, "go_right", {"s": "B"}, 0.0, False)
        kg.add_event({"s": "A"}, "go_right", {"s": "B"}, 1.0, False)

        state_hash = BrainEvent(0, "t", {"s": "A"}, "", {}, 0, False).state_hash()
        transitions = kg.get_state_transitions(state_hash)
        assert len(transitions) == 1
        action, _, avg_reward = transitions[0]
        assert action == "go_right"
        assert abs(avg_reward - 0.5) < 1e-6

    def test_get_state_transitions_unknown_state(self):
        """Unknown state hash returns empty transitions list."""
        kg = KotlinGraph()
        assert kg.get_state_transitions("nonexistent_hash") == []

    def test_get_most_visited_states(self):
        """Returns states sorted by visit count descending."""
        kg = KotlinGraph()
        # Visit A 3 times, B 1 time
        kg.add_event({"s": "A"}, "go", {"s": "B"}, 0.0, False)
        kg.add_event({"s": "A"}, "go", {"s": "C"}, 0.0, False)
        kg.add_event({"s": "A"}, "go", {"s": "D"}, 0.0, False)
        kg.add_event({"s": "B"}, "go", {"s": "E"}, 0.0, False)

        top = kg.get_most_visited_states(top_k=2)
        assert len(top) == 2
        # A should be first with count 3
        assert top[0][1] == 3
        assert top[1][1] == 1

    def test_get_best_actions_from_state(self):
        """Returns actions sorted by average reward descending."""
        kg = KotlinGraph()
        kg.add_event({"s": "A"}, "bad_move", {"s": "B"}, 0.1, False)
        kg.add_event({"s": "A"}, "good_move", {"s": "C"}, 0.9, False)
        kg.add_event({"s": "A"}, "ok_move", {"s": "D"}, 0.5, False)

        best = kg.get_best_actions_from_state({"s": "A"}, top_k=2)
        assert len(best) == 2
        assert best[0][0] == "good_move"
        assert best[0][1] == pytest.approx(0.9)
        assert best[1][0] == "ok_move"
        assert best[1][1] == pytest.approx(0.5)

    def test_get_best_actions_unknown_state(self):
        """Unknown state returns empty list."""
        kg = KotlinGraph()
        assert kg.get_best_actions_from_state({"s": "nonexistent"}) == []


# ===================================================================
# KotlinGraph - Statistics
# ===================================================================

class TestKotlinGraphStatistics:

    def test_statistics_basic(self):
        """get_statistics returns correct basic counts."""
        kg = KotlinGraph()
        add_simple_episode(kg, n_steps=3)
        stats = kg.get_statistics()
        assert stats['total_events'] == 3
        assert stats['total_episodes'] == 1
        assert stats['total_transitions'] == 3

    def test_statistics_avg_episode_length(self):
        """Average episode length is computed correctly."""
        kg = KotlinGraph()
        add_simple_episode(kg, n_steps=4, episode_label="a")
        add_simple_episode(kg, n_steps=2, episode_label="b")
        stats = kg.get_statistics()
        # 6 events, 2 episodes -> avg = 3.0
        assert stats['avg_episode_length'] == pytest.approx(3.0)

    def test_statistics_no_episodes(self):
        """avg_episode_length is 0 when no episodes completed."""
        kg = KotlinGraph()
        kg.add_event({"a": 1}, "go", {"a": 2}, 0.0, False)  # not done
        stats = kg.get_statistics()
        assert stats['avg_episode_length'] == 0

    def test_statistics_episode_lengths(self):
        """min/max/median episode lengths."""
        kg = KotlinGraph()
        add_simple_episode(kg, n_steps=5, episode_label="long")
        add_simple_episode(kg, n_steps=1, episode_label="short")
        add_simple_episode(kg, n_steps=3, episode_label="mid")
        stats = kg.get_statistics()
        assert stats['min_episode_length'] == 1
        assert stats['max_episode_length'] == 5
        assert stats['median_episode_length'] == 3.0

    def test_statistics_graph_density(self):
        """Graph density is included in statistics."""
        kg = KotlinGraph()
        add_simple_episode(kg, n_steps=2)
        stats = kg.get_statistics()
        assert 'graph_density' in stats
        assert isinstance(stats['graph_density'], float)


# ===================================================================
# KotlinGraph - Save / Load
# ===================================================================

class TestKotlinGraphSaveLoad:

    def test_save_load_roundtrip(self, tmp_path):
        """Save and load preserves all data."""
        kg = KotlinGraph()
        add_simple_episode(kg, n_steps=3, episode_label="ep0")
        add_simple_episode(kg, n_steps=2, episode_label="ep1")
        # Add one with metadata and brain metrics
        kg2_ep = kg.current_episode_id
        kg.add_event(
            {"special": True, "val": 42},
            "special_action",
            {"special": False, "val": 43},
            reward=0.99,
            done=True,
            value=0.7,
            policy_entropy=0.3,
            consciousness=0.9,
            dmn_energy=0.1,
            metadata={"tag": "important"}
        )

        filepath = str(tmp_path / "test_graph.json")
        kg.save(filepath)
        assert os.path.exists(filepath)

        # Load into new instance
        kg_loaded = KotlinGraph()
        kg_loaded.load(filepath)

        # Verify stats
        assert kg_loaded.stats == kg.stats

        # Verify events
        assert len(kg_loaded.events) == len(kg.events)
        for orig, loaded in zip(kg.events, kg_loaded.events):
            assert loaded.event_id == orig.event_id
            assert loaded.state == orig.state
            assert loaded.action == orig.action
            assert loaded.next_state == orig.next_state
            assert loaded.reward == orig.reward
            assert loaded.done == orig.done
            assert loaded.episode_id == orig.episode_id
            assert loaded.step_in_episode == orig.step_in_episode
            assert loaded.metadata == orig.metadata
            assert loaded.value == orig.value
            assert loaded.consciousness == orig.consciousness

        # Verify episodes
        assert kg_loaded.episodes == kg.episodes
        assert kg_loaded.current_episode_id == kg.current_episode_id

        # Verify graph structure
        assert kg_loaded.graph.number_of_nodes() == kg.graph.number_of_nodes()
        assert kg_loaded.graph.number_of_edges() == kg.graph.number_of_edges()

        # Verify state_index
        assert kg_loaded.state_index == kg.state_index
        assert kg_loaded.next_node_id == kg.next_node_id

    def test_save_load_empty_graph(self, tmp_path):
        """Save/load works on empty graph."""
        kg = KotlinGraph()
        filepath = str(tmp_path / "empty.json")
        kg.save(filepath)

        kg_loaded = KotlinGraph()
        kg_loaded.load(filepath)
        assert kg_loaded.stats['total_events'] == 0
        assert len(kg_loaded.events) == 0

    def test_save_produces_valid_json(self, tmp_path):
        """Saved file is valid JSON."""
        kg = KotlinGraph()
        add_simple_episode(kg, n_steps=2)
        filepath = str(tmp_path / "valid.json")
        kg.save(filepath)

        with open(filepath, 'r') as f:
            data = json.load(f)  # should not raise
        assert 'events' in data
        assert 'stats' in data
        assert 'graph' in data

    def test_load_restores_graph_queries(self, tmp_path):
        """After load, graph queries still work correctly."""
        kg = KotlinGraph()
        kg.add_event({"s": "A"}, "go", {"s": "B"}, 0.5, False)
        kg.add_event({"s": "A"}, "stay", {"s": "A"}, 0.1, True)

        filepath = str(tmp_path / "queries.json")
        kg.save(filepath)

        kg_loaded = KotlinGraph()
        kg_loaded.load(filepath)

        # Can still query transitions
        state_hash = BrainEvent(0, "t", {"s": "A"}, "", {}, 0, False).state_hash()
        transitions = kg_loaded.get_state_transitions(state_hash)
        assert len(transitions) == 2

        # Can still get episodes
        ep = kg_loaded.get_episode(0)
        assert len(ep) == 2


# ===================================================================
# KotlinGraph - Clear
# ===================================================================

class TestKotlinGraphClear:

    def test_clear_resets_everything(self):
        """clear() resets graph to initial empty state."""
        kg = KotlinGraph()
        add_simple_episode(kg, n_steps=5)
        add_simple_episode(kg, n_steps=3)

        kg.clear()

        assert kg.stats['total_events'] == 0
        assert kg.stats['total_episodes'] == 0
        assert kg.stats['total_states'] == 0
        assert kg.stats['total_transitions'] == 0
        assert len(kg.events) == 0
        assert len(kg.state_index) == 0
        assert len(kg.episodes) == 0
        assert kg.current_episode_id == 0
        assert kg.next_node_id == 0
        assert kg.graph.number_of_nodes() == 0
        assert kg.graph.number_of_edges() == 0

    def test_clear_then_reuse(self):
        """After clear(), graph can be populated again normally."""
        kg = KotlinGraph()
        add_simple_episode(kg, n_steps=2)
        kg.clear()

        # Add new data
        eid = kg.add_event({"fresh": True}, "start", {"fresh": False}, 1.0, True)
        assert eid == 0
        assert kg.stats['total_events'] == 1
        assert kg.stats['total_episodes'] == 1


# ===================================================================
# KotlinGraph - Edge Cases
# ===================================================================

class TestKotlinGraphEdgeCases:

    def test_self_loop(self):
        """Transition from state to same state (self-loop)."""
        kg = KotlinGraph()
        kg.add_event({"s": "A"}, "wait", {"s": "A"}, 0.0, False)
        # One unique state, one edge (self-loop)
        assert kg.graph.number_of_nodes() == 1
        assert kg.graph.number_of_edges() == 1
        assert kg.stats['total_states'] == 1

    def test_many_episodes(self):
        """Handles many episodes without issues."""
        kg = KotlinGraph()
        for i in range(50):
            add_simple_episode(kg, n_steps=2, episode_label=f"ep{i}")
        assert kg.stats['total_episodes'] == 50
        assert kg.stats['total_events'] == 100

    def test_state_with_empty_dict(self):
        """Empty dict is a valid state."""
        kg = KotlinGraph()
        kg.add_event({}, "act", {"done": True}, 1.0, True)
        assert kg.stats['total_events'] == 1
        assert kg.graph.number_of_nodes() == 2

    def test_multidigraph_allows_parallel_edges(self):
        """MultiDiGraph allows multiple edges between same nodes (different events)."""
        kg = KotlinGraph()
        kg.add_event({"s": "A"}, "go", {"s": "B"}, 0.0, False)
        kg.add_event({"s": "A"}, "go", {"s": "B"}, 1.0, False)
        # Two nodes, two parallel edges
        assert kg.graph.number_of_nodes() == 2
        assert kg.graph.number_of_edges() == 2

    def test_edge_attributes(self):
        """Edges store event_id, action, reward, consciousness, episode_id."""
        kg = KotlinGraph()
        kg.add_event(
            {"s": "A"}, "jump", {"s": "B"}, 0.75, False,
            value=0.5, consciousness=0.8
        )
        # Get the single edge
        edges = list(kg.graph.edges(data=True))
        assert len(edges) == 1
        _, _, data = edges[0]
        assert data['action'] == "jump"
        assert data['reward'] == 0.75
        assert data['event_id'] == 0
        assert data['consciousness'] == 0.8
        assert data['value'] == 0.5
        assert data['episode_id'] == 0

    def test_node_attributes(self):
        """Nodes store state, state_hash, first_seen, visit_count."""
        kg = KotlinGraph()
        kg.add_event({"s": "A"}, "go", {"s": "B"}, 0.0, False)
        node_data = dict(kg.graph.nodes(data=True))
        for nid, attrs in node_data.items():
            assert 'state' in attrs
            assert 'state_hash' in attrs
            assert 'first_seen' in attrs
            assert 'visit_count' in attrs
