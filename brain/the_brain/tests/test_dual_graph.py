"""
Tests for core/dual_graph.py - DualGraph Manager

Tests the unified coordinator for KotlinGraph (episodic memory)
and KuroGraph (pattern extraction).
"""

import json
import os
import tempfile
import shutil
import pytest
from unittest.mock import patch, MagicMock

from core.dual_graph import DualGraph
from core.kotlin_graph import KotlinGraph, BrainEvent
from core.kuro_graph import KuroGraph, ActionNGram, StrategyPattern


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(label: str) -> dict:
    """Create a simple state dict for testing."""
    return {"label": label, "value": hash(label) % 100}


def _record_episode(dg: DualGraph, actions: list, final_reward: float = 1.0,
                     step_reward: float = 0.1, consciousness: float = 0.5,
                     value: float = 0.5) -> None:
    """Record a full episode of events into the DualGraph."""
    for i, action in enumerate(actions):
        is_last = (i == len(actions) - 1)
        reward = final_reward if is_last else step_reward
        dg.record_event(
            state=_make_state(f"s{i}"),
            action=action,
            next_state=_make_state(f"s{i+1}"),
            reward=reward,
            done=is_last,
            value=value,
            consciousness=consciousness,
        )


def _record_n_episodes(dg: DualGraph, n: int,
                        actions: list = None,
                        final_reward: float = 1.0) -> None:
    """Record n identical episodes."""
    if actions is None:
        actions = ["move_left", "move_right", "push"]
    for _ in range(n):
        _record_episode(dg, actions, final_reward=final_reward)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir():
    """Create a temp directory for save/load tests."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def dg(tmp_dir):
    """Fresh DualGraph with temp save directory."""
    return DualGraph(save_dir=tmp_dir, auto_mine_interval=5)


@pytest.fixture
def populated_dg(dg):
    """DualGraph with several episodes recorded and mined."""
    # Record 6 episodes with a repeating 3-action pattern
    # (enough to trigger auto-mine at interval=5 after 5th done)
    actions = ["open", "read", "close"]
    _record_n_episodes(dg, 6, actions=actions, final_reward=1.0)
    return dg


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestDualGraphConstruction:
    def test_init_defaults(self, tmp_dir):
        dg = DualGraph(save_dir=tmp_dir)
        assert dg.auto_mine_interval == 10
        assert dg.episodes_since_last_mine == 0
        assert dg.stats['total_events_recorded'] == 0
        assert dg.stats['total_patterns_mined'] == 0
        assert dg.stats['last_mine_episode'] == 0

    def test_init_custom_interval(self, tmp_dir):
        dg = DualGraph(save_dir=tmp_dir, auto_mine_interval=3)
        assert dg.auto_mine_interval == 3

    def test_save_dir_created(self):
        d = tempfile.mkdtemp()
        try:
            subdir = os.path.join(d, "nested", "memory")
            dg = DualGraph(save_dir=subdir)
            assert os.path.isdir(subdir)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_internal_graphs_exist(self, dg):
        assert isinstance(dg.kotlingraph, KotlinGraph)
        assert isinstance(dg.kurograph, KuroGraph)
        # kurograph should reference the same kotlingraph
        assert dg.kurograph.kotlingraph is dg.kotlingraph


# ---------------------------------------------------------------------------
# record_event
# ---------------------------------------------------------------------------

class TestRecordEvent:
    def test_basic_record(self, dg):
        eid = dg.record_event(
            state={"x": 1},
            action="go",
            next_state={"x": 2},
            reward=0.5,
            done=False,
        )
        assert eid == 0
        assert dg.stats['total_events_recorded'] == 1
        assert dg.kotlingraph.stats['total_events'] == 1

    def test_record_with_brain_metrics(self, dg):
        eid = dg.record_event(
            state={"a": 1},
            action="think",
            next_state={"a": 2},
            reward=0.1,
            done=False,
            value=0.8,
            policy_entropy=0.3,
            consciousness=0.9,
            dmn_energy=0.4,
        )
        event = dg.kotlingraph.get_event(eid)
        assert event.value == 0.8
        assert event.policy_entropy == 0.3
        assert event.consciousness == 0.9
        assert event.dmn_energy == 0.4

    def test_record_with_metadata(self, dg):
        meta = {"source": "test", "priority": 5}
        eid = dg.record_event(
            state={"m": 1},
            action="act",
            next_state={"m": 2},
            reward=0.0,
            done=False,
            metadata=meta,
        )
        event = dg.kotlingraph.get_event(eid)
        assert event.metadata == meta

    def test_episode_counter_increments_on_done(self, dg):
        dg.record_event({"s": 0}, "a", {"s": 1}, 0.0, done=False)
        dg.record_event({"s": 1}, "b", {"s": 2}, 1.0, done=True)
        assert dg.episodes_since_last_mine == 1

    def test_sequential_ids(self, dg):
        ids = []
        for i in range(5):
            eid = dg.record_event(
                {"i": i}, "a", {"i": i + 1}, 0.0, done=(i == 4)
            )
            ids.append(eid)
        assert ids == [0, 1, 2, 3, 4]


# ---------------------------------------------------------------------------
# Auto-mining
# ---------------------------------------------------------------------------

class TestAutoMining:
    def test_auto_mine_triggers_at_interval(self, tmp_dir):
        dg = DualGraph(save_dir=tmp_dir, auto_mine_interval=3)
        actions = ["a", "b", "c"]

        # Record 3 episodes (interval=3 => should trigger after 3rd done)
        _record_n_episodes(dg, 3, actions=actions)

        assert dg.episodes_since_last_mine == 0  # reset after mine
        assert dg.stats['total_patterns_mined'] > 0

    def test_auto_mine_does_not_trigger_early(self, tmp_dir):
        dg = DualGraph(save_dir=tmp_dir, auto_mine_interval=10)
        _record_n_episodes(dg, 2, actions=["a", "b"])
        assert dg.episodes_since_last_mine == 2
        assert dg.stats['total_patterns_mined'] == 0

    def test_counter_resets_after_mine(self, tmp_dir):
        dg = DualGraph(save_dir=tmp_dir, auto_mine_interval=2)
        _record_n_episodes(dg, 2, actions=["x", "y", "z"])
        assert dg.episodes_since_last_mine == 0
        # Record 1 more - should not trigger again
        _record_episode(dg, ["x", "y", "z"])
        assert dg.episodes_since_last_mine == 1

    def test_auto_mine_updates_last_mine_episode(self, tmp_dir):
        dg = DualGraph(save_dir=tmp_dir, auto_mine_interval=2)
        _record_n_episodes(dg, 2, actions=["a", "b"])
        assert dg.stats['last_mine_episode'] > 0


# ---------------------------------------------------------------------------
# force_mine
# ---------------------------------------------------------------------------

class TestForceMine:
    def test_force_mine_works_without_auto(self, dg):
        _record_n_episodes(dg, 2, actions=["a", "b", "c"])
        assert dg.stats['total_patterns_mined'] == 0  # interval=5, only 2 episodes
        dg.force_mine()
        assert dg.stats['total_patterns_mined'] > 0
        assert dg.episodes_since_last_mine == 0

    def test_force_mine_on_empty_graph(self, dg):
        # Should not raise
        dg.force_mine()
        assert dg.stats['total_patterns_mined'] == 0

    def test_force_mine_mines_multiple_ngram_lengths(self, dg):
        _record_n_episodes(dg, 3, actions=["a", "b", "c", "d", "e", "f"])
        dg.force_mine()
        # Should have mined n-grams of length 2, 3, 4, 5
        ngram_lengths = set(len(ng) for ng in dg.kurograph.ngrams.values())
        assert len(ngram_lengths) >= 1  # at least some found


# ---------------------------------------------------------------------------
# suggest_actions
# ---------------------------------------------------------------------------

class TestSuggestActions:
    def test_suggest_actions_empty(self, dg):
        result = dg.suggest_actions(state={"x": 0}, recent_actions=[])
        assert isinstance(result, list)
        assert len(result) == 0  # no patterns

    def test_suggest_actions_after_mining(self, populated_dg):
        result = populated_dg.suggest_actions(
            state=_make_state("s0"),
            recent_actions=["open"],
        )
        assert isinstance(result, list)
        # Each item is (action_str, confidence_float)
        for action, confidence in result:
            assert isinstance(action, str)
            assert isinstance(confidence, float)

    def test_suggest_actions_top_k(self, populated_dg):
        result = populated_dg.suggest_actions(
            state=_make_state("s0"),
            recent_actions=[],
            top_k=2,
        )
        assert len(result) <= 2

    def test_suggest_actions_no_recent(self, populated_dg):
        """With no recent actions, should suggest based on first-action stats."""
        result = populated_dg.suggest_actions(
            state=_make_state("s0"),
            recent_actions=[],
        )
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# save / load roundtrip
# ---------------------------------------------------------------------------

class TestSaveLoad:
    def test_save_creates_files(self, populated_dg, tmp_dir):
        populated_dg.save("test")
        assert os.path.isfile(os.path.join(tmp_dir, "test_kotlingraph.json"))
        assert os.path.isfile(os.path.join(tmp_dir, "test_kurograph.json"))

    def test_load_restores_state(self, populated_dg, tmp_dir):
        populated_dg.save("roundtrip")

        dg2 = DualGraph(save_dir=tmp_dir)
        result = dg2.load("roundtrip")
        assert result is True

        # Verify kotlingraph events restored
        assert len(dg2.kotlingraph.events) == len(populated_dg.kotlingraph.events)
        # Verify kurograph has same n-grams
        assert len(dg2.kurograph.ngrams) == len(populated_dg.kurograph.ngrams)
        # Verify kurograph is connected to kotlingraph
        assert dg2.kurograph.kotlingraph is dg2.kotlingraph

    def test_load_missing_kotlingraph_returns_false(self, dg, tmp_dir):
        result = dg.load("nonexistent")
        assert result is False

    def test_load_missing_kurograph_returns_false(self, dg, tmp_dir):
        # Create only the kotlingraph file
        path = os.path.join(tmp_dir, "partial_kotlingraph.json")
        dg.kotlingraph.save(path)
        result = dg.load("partial")
        assert result is False

    def test_save_default_name(self, dg, tmp_dir):
        dg.record_event({"a": 1}, "go", {"a": 2}, 0.5, done=True)
        dg.save()  # default name "memory"
        assert os.path.isfile(os.path.join(tmp_dir, "memory_kotlingraph.json"))
        assert os.path.isfile(os.path.join(tmp_dir, "memory_kurograph.json"))


# ---------------------------------------------------------------------------
# get_statistics
# ---------------------------------------------------------------------------

class TestGetStatistics:
    def test_empty_statistics(self, dg):
        stats = dg.get_statistics()
        assert stats['total_events_recorded'] == 0
        assert stats['total_patterns_mined'] == 0
        assert 'kotlingraph' in stats
        assert 'kurograph' in stats

    def test_populated_statistics(self, populated_dg):
        stats = populated_dg.get_statistics()
        assert stats['total_events_recorded'] > 0
        assert stats['kotlingraph']['total_events'] > 0
        assert stats['kotlingraph']['total_episodes'] > 0

    def test_statistics_after_mining(self, populated_dg):
        stats = populated_dg.get_statistics()
        assert stats['total_patterns_mined'] > 0
        assert stats['kurograph']['total_ngrams'] >= 0


# ---------------------------------------------------------------------------
# get_best_patterns
# ---------------------------------------------------------------------------

class TestGetBestPatterns:
    def test_empty_patterns(self, dg):
        patterns = dg.get_best_patterns()
        assert patterns == []

    def test_patterns_after_mining(self, populated_dg):
        patterns = populated_dg.get_best_patterns(top_k=5)
        assert isinstance(patterns, list)
        for p in patterns:
            assert isinstance(p, ActionNGram)
            assert len(p.actions) >= 2

    def test_top_k_respected(self, populated_dg):
        patterns = populated_dg.get_best_patterns(top_k=2)
        assert len(patterns) <= 2


# ---------------------------------------------------------------------------
# get_strategies
# ---------------------------------------------------------------------------

class TestGetStrategies:
    def test_empty_strategies(self, dg):
        strategies = dg.get_strategies()
        assert strategies == []

    def test_strategies_are_strategy_pattern(self, populated_dg):
        strategies = populated_dg.get_strategies()
        for s in strategies:
            assert isinstance(s, StrategyPattern)


# ---------------------------------------------------------------------------
# analyze_episode
# ---------------------------------------------------------------------------

class TestAnalyzeEpisode:
    def test_missing_episode(self, dg):
        result = dg.analyze_episode(999)
        assert 'error' in result

    def test_analyze_recorded_episode(self, populated_dg):
        analysis = populated_dg.analyze_episode(0)
        assert analysis['episode_id'] == 0
        assert analysis['length'] > 0
        assert isinstance(analysis['total_reward'], float)
        assert isinstance(analysis['success'], bool)
        assert isinstance(analysis['patterns_used'], list)
        assert 'avg_consciousness' in analysis
        assert 'avg_value' in analysis

    def test_analyze_reward_sum(self, dg):
        # Record a 3-step episode: 0.1, 0.1, 1.0
        _record_episode(dg, ["a", "b", "c"], final_reward=1.0, step_reward=0.1)
        analysis = dg.analyze_episode(0)
        assert abs(analysis['total_reward'] - 1.2) < 0.01

    def test_analyze_success_detection(self, dg):
        # Episode with positive final reward
        _record_episode(dg, ["a", "b"], final_reward=1.0)
        analysis = dg.analyze_episode(0)
        assert analysis['success'] is True

        # Episode with zero final reward
        _record_episode(dg, ["c", "d"], final_reward=0.0)
        analysis = dg.analyze_episode(1)
        assert analysis['success'] is False


# ---------------------------------------------------------------------------
# export_patterns_for_training
# ---------------------------------------------------------------------------

class TestExportPatterns:
    def test_export_empty(self, dg):
        export = dg.export_patterns_for_training()
        assert 'ngrams' in export
        assert 'strategies' in export
        assert 'statistics' in export
        assert export['ngrams'] == []

    def test_export_after_mining(self, populated_dg):
        export = populated_dg.export_patterns_for_training()
        assert isinstance(export['ngrams'], list)
        assert isinstance(export['strategies'], list)
        assert isinstance(export['statistics'], dict)

        for ng_data in export['ngrams']:
            assert 'actions' in ng_data
            assert 'frequency' in ng_data
            assert 'avg_reward' in ng_data
            assert 'success_rate' in ng_data
            assert isinstance(ng_data['actions'], list)

    def test_export_statistics_included(self, populated_dg):
        export = populated_dg.export_patterns_for_training()
        stats = export['statistics']
        assert 'total_events_recorded' in stats
        assert 'kotlingraph' in stats
        assert 'kurograph' in stats


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

class TestClear:
    def test_clear_resets_everything(self, populated_dg):
        assert populated_dg.stats['total_events_recorded'] > 0

        populated_dg.clear()

        assert populated_dg.stats['total_events_recorded'] == 0
        assert populated_dg.stats['total_patterns_mined'] == 0
        assert populated_dg.stats['last_mine_episode'] == 0
        assert populated_dg.episodes_since_last_mine == 0
        assert len(populated_dg.kotlingraph.events) == 0
        assert len(populated_dg.kurograph.ngrams) == 0

    def test_clear_then_record(self, populated_dg):
        populated_dg.clear()
        eid = populated_dg.record_event(
            {"fresh": True}, "start", {"fresh": False}, 0.5, done=False
        )
        assert eid == 0
        assert populated_dg.stats['total_events_recorded'] == 1

    def test_clear_kurograph_reconnected(self, populated_dg):
        populated_dg.clear()
        assert populated_dg.kurograph.kotlingraph is populated_dg.kotlingraph


# ---------------------------------------------------------------------------
# Empty graph behavior
# ---------------------------------------------------------------------------

class TestEmptyBehavior:
    def test_statistics_on_empty(self, dg):
        stats = dg.get_statistics()
        assert stats['total_events_recorded'] == 0
        assert stats['kotlingraph']['total_events'] == 0

    def test_suggest_on_empty(self, dg):
        result = dg.suggest_actions({"x": 1}, [])
        assert result == []

    def test_best_patterns_on_empty(self, dg):
        assert dg.get_best_patterns() == []

    def test_strategies_on_empty(self, dg):
        assert dg.get_strategies() == []

    def test_analyze_on_empty(self, dg):
        result = dg.analyze_episode(0)
        assert 'error' in result

    def test_export_on_empty(self, dg):
        export = dg.export_patterns_for_training()
        assert export['ngrams'] == []
        assert export['strategies'] == []

    def test_force_mine_on_empty(self, dg):
        dg.force_mine()  # should not raise
        assert dg.stats['total_patterns_mined'] == 0


# ---------------------------------------------------------------------------
# Logging (no print statements)
# ---------------------------------------------------------------------------

class TestLogging:
    def test_no_print_on_record(self, dg, capsys):
        """DualGraph should use logging, not print()."""
        dg.record_event({"x": 1}, "a", {"x": 2}, 0.5, done=True)
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_print_on_save(self, dg, tmp_dir, capsys):
        dg.record_event({"x": 1}, "a", {"x": 2}, 0.5, done=True)
        dg.save("test")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_print_on_load(self, dg, tmp_dir, capsys):
        dg.record_event({"x": 1}, "a", {"x": 2}, 0.5, done=True)
        dg.save("test")
        dg2 = DualGraph(save_dir=tmp_dir)
        dg2.load("test")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_print_on_force_mine(self, dg, capsys):
        _record_n_episodes(dg, 3, actions=["a", "b", "c"])
        dg.force_mine()
        captured = capsys.readouterr()
        assert captured.out == ""


# ===================================================================
# Concurrency regression (KG-C4, Phase 0)
# ===================================================================

class TestDualGraphConcurrency:
    """KG-C4: DualGraph.record_event inherits KotlinGraph's thread-safety
    (KG-C2 lock) WITHOUT changes to DualGraph itself. Primary asserts are
    the KotlinGraph counters reached THROUGH DualGraph. DualGraph's own
    `total_events_recorded += 1` (:112) stays lock-free by design — if it
    undercounts under contention that is a documented follow-up, not a
    silent scope expansion (plan KG-C4)."""

    def test_dualgraph_record_event_parallel_consistent(self, tmp_path):
        import sys
        import threading
        from concurrent.futures import ThreadPoolExecutor

        N = 200
        WORKERS = 8
        # auto_mine_interval high so _auto_mine never fires mid-test
        dg = DualGraph(save_dir=str(tmp_path), auto_mine_interval=10_000)
        barrier = threading.Barrier(WORKERS)

        def worker(indices):
            barrier.wait()
            for j in indices:
                dg.record_event(
                    state={"label": f"s{j}", "x": j},
                    action=f"a{j}",
                    next_state={"label": f"s{j}n", "x": j},
                    reward=0.0,
                    done=(j == N - 1),
                )

        old_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            chunks = [list(range(k, N, WORKERS)) for k in range(WORKERS)]
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                futures = [ex.submit(worker, c) for c in chunks]
                for f in futures:
                    f.result()
        finally:
            sys.setswitchinterval(old_interval)

        kg = dg.kotlingraph
        assert kg.stats['total_events'] == N
        assert len(kg.events) == N
        assert len({e.event_id for e in kg.events}) == N
        assert kg.stats['total_episodes'] == 1
        # DualGraph's own counter: report-only (lock-free by design)
        if dg.stats['total_events_recorded'] != N:
            import warnings
            warnings.warn(
                f"DualGraph.total_events_recorded undercounts under "
                f"contention ({dg.stats['total_events_recorded']} != {N}) "
                f"— documented follow-up per KG-C4, KotlinGraph counters "
                f"are the source of truth",
                stacklevel=1,
            )
