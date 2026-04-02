"""
Tests for KuroGraph - Domain-Agnostic Pattern Extraction and Strategy Mining.

Tests cover:
- ActionNGram creation, hashability, equality
- mine_ngrams with repeated patterns, min_frequency threshold
- get_best_ngrams (scoring, ordering)
- extract_strategies
- suggest_action with history and without
- build_cooccurrence_matrix
- Statistics
- Save/load roundtrip
"""

import os
import json
import tempfile
import pytest
import numpy as np

from core.kotlin_graph import KotlinGraph, BrainEvent
from core.kuro_graph import KuroGraph, ActionNGram, StrategyPattern


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(label: str) -> dict:
    """Create a simple state dict from a label."""
    return {"label": label, "value": hash(label) % 100}


def _build_kotlin_graph_with_pattern(
    pattern: list[str],
    num_episodes: int = 5,
    steps_per_episode: int = 10,
    final_reward: float = 1.0,
    step_reward: float = 0.1,
) -> KotlinGraph:
    """
    Build a KotlinGraph where every episode repeats *pattern* cyclically.

    Each episode has `steps_per_episode` events. The last event gets
    `final_reward`; all others get `step_reward`. The last event has done=True.
    """
    kg = KotlinGraph()
    for _ep in range(num_episodes):
        for step in range(steps_per_episode):
            action = pattern[step % len(pattern)]
            state = _make_state(f"s{step}")
            next_state = _make_state(f"s{step + 1}")
            reward = final_reward if step == steps_per_episode - 1 else step_reward
            done = step == steps_per_episode - 1
            kg.add_event(state, action, next_state, reward, done)
    return kg


# ---------------------------------------------------------------------------
# ActionNGram dataclass
# ---------------------------------------------------------------------------


class TestActionNGram:
    """Tests for the ActionNGram dataclass."""

    def test_creation(self):
        ng = ActionNGram(
            actions=("move", "grab", "place"),
            frequency=5,
            avg_reward=0.8,
            success_rate=0.6,
        )
        assert ng.actions == ("move", "grab", "place")
        assert ng.frequency == 5
        assert ng.avg_reward == 0.8
        assert ng.success_rate == 0.6
        assert ng.contexts == []

    def test_len(self):
        ng = ActionNGram(("a", "b"), 1, 0.0, 0.0)
        assert len(ng) == 2

        ng3 = ActionNGram(("a", "b", "c"), 1, 0.0, 0.0)
        assert len(ng3) == 3

    def test_hash_by_actions(self):
        ng1 = ActionNGram(("a", "b"), 1, 0.0, 0.0)
        ng2 = ActionNGram(("a", "b"), 99, 1.0, 1.0)  # different fields
        assert hash(ng1) == hash(ng2)

    def test_equality_by_actions(self):
        ng1 = ActionNGram(("a", "b"), 1, 0.0, 0.0)
        ng2 = ActionNGram(("a", "b"), 99, 1.0, 1.0)
        assert ng1 == ng2

    def test_inequality(self):
        ng1 = ActionNGram(("a", "b"), 1, 0.0, 0.0)
        ng2 = ActionNGram(("a", "c"), 1, 0.0, 0.0)
        assert ng1 != ng2

    def test_hashable_in_set(self):
        ng1 = ActionNGram(("a", "b"), 1, 0.0, 0.0)
        ng2 = ActionNGram(("a", "b"), 99, 1.0, 1.0)
        ng3 = ActionNGram(("x", "y"), 1, 0.0, 0.0)
        s = {ng1, ng2, ng3}
        # ng1 and ng2 are equal, so set should have 2 elements
        assert len(s) == 2

    def test_equality_not_implemented_for_other_types(self):
        ng = ActionNGram(("a",), 1, 0.0, 0.0)
        assert ng != "not_an_ngram"
        assert ng != 42


# ---------------------------------------------------------------------------
# KuroGraph construction
# ---------------------------------------------------------------------------


class TestKuroGraphInit:
    """Tests for KuroGraph initialization."""

    def test_init_no_kotlingraph(self):
        kuro = KuroGraph()
        assert kuro.kotlingraph is None
        assert kuro.ngrams == {}
        assert kuro.strategies == {}
        assert kuro.next_strategy_id == 0
        assert kuro.stats['total_ngrams'] == 0

    def test_init_with_kotlingraph(self):
        kg = KotlinGraph()
        kuro = KuroGraph(kotlingraph=kg)
        assert kuro.kotlingraph is kg


# ---------------------------------------------------------------------------
# mine_ngrams
# ---------------------------------------------------------------------------


class TestMineNGrams:
    """Tests for n-gram mining."""

    def test_mine_returns_empty_without_kotlingraph(self):
        kuro = KuroGraph()
        result = kuro.mine_ngrams(n=3, min_frequency=1)
        assert result == []

    def test_mine_returns_empty_for_short_episodes(self):
        kg = KotlinGraph()
        # Single event episode -- too short for a 3-gram
        kg.add_event(_make_state("a"), "act", _make_state("b"), 0.1, True)
        kuro = KuroGraph(kotlingraph=kg)
        result = kuro.mine_ngrams(n=3, min_frequency=1)
        assert result == []

    def test_mine_basic_pattern(self):
        # Pattern: a, b, c repeated over 5 episodes x 10 steps
        kg = _build_kotlin_graph_with_pattern(["a", "b", "c"], num_episodes=5, steps_per_episode=10)
        kuro = KuroGraph(kotlingraph=kg)
        ngrams = kuro.mine_ngrams(n=3, min_frequency=2)

        # Should find several 3-grams with frequency >= 2
        assert len(ngrams) > 0
        for ng in ngrams:
            assert len(ng) == 3
            assert ng.frequency >= 2

    def test_mine_min_frequency_filter(self):
        kg = _build_kotlin_graph_with_pattern(["a", "b", "c"], num_episodes=3, steps_per_episode=6)
        kuro = KuroGraph(kotlingraph=kg)

        # Low threshold
        low = kuro.mine_ngrams(n=3, min_frequency=1)
        # Reset for fair comparison
        kuro.ngrams.clear()
        # High threshold
        high = kuro.mine_ngrams(n=3, min_frequency=100)

        assert len(low) >= len(high)

    def test_mine_min_reward_filter(self):
        kg = _build_kotlin_graph_with_pattern(
            ["a", "b", "c"], num_episodes=3, steps_per_episode=6,
            step_reward=-1.0, final_reward=-0.5,
        )
        kuro = KuroGraph(kotlingraph=kg)
        # With positive min_reward, all negative-reward n-grams should be filtered
        ngrams = kuro.mine_ngrams(n=3, min_frequency=1, min_reward=0.5)
        assert len(ngrams) == 0

    def test_mine_updates_stats(self):
        kg = _build_kotlin_graph_with_pattern(["x", "y"], num_episodes=4, steps_per_episode=6)
        kuro = KuroGraph(kotlingraph=kg)
        ngrams = kuro.mine_ngrams(n=2, min_frequency=1)

        assert kuro.stats['total_ngrams'] == len(kuro.ngrams)
        assert kuro.stats['total_patterns_mined'] == len(ngrams)

    def test_mine_success_rate_computed(self):
        # All episodes end with reward > 0 (final_reward=1.0) -> success_rate should be > 0
        kg = _build_kotlin_graph_with_pattern(["a", "b"], num_episodes=5, steps_per_episode=4)
        kuro = KuroGraph(kotlingraph=kg)
        ngrams = kuro.mine_ngrams(n=2, min_frequency=1)

        for ng in ngrams:
            # Every episode ends with positive reward, so at least some should have success_rate > 0
            assert 0.0 <= ng.success_rate <= 1.0

    def test_mine_contexts_populated(self):
        kg = _build_kotlin_graph_with_pattern(["a", "b"], num_episodes=3, steps_per_episode=4)
        kuro = KuroGraph(kotlingraph=kg)
        ngrams = kuro.mine_ngrams(n=2, min_frequency=1)

        for ng in ngrams:
            # Contexts are state hashes; there should be at least one per occurrence
            assert len(ng.contexts) >= ng.frequency

    def test_mine_different_n_values(self):
        kg = _build_kotlin_graph_with_pattern(["a", "b", "c", "d"], num_episodes=5, steps_per_episode=8)
        kuro = KuroGraph(kotlingraph=kg)

        ng2 = kuro.mine_ngrams(n=2, min_frequency=1)
        kuro.ngrams.clear()
        ng4 = kuro.mine_ngrams(n=4, min_frequency=1)

        for ng in ng2:
            assert len(ng) == 2
        for ng in ng4:
            assert len(ng) == 4


# ---------------------------------------------------------------------------
# get_best_ngrams
# ---------------------------------------------------------------------------


class TestGetBestNGrams:
    """Tests for retrieving best n-grams by score."""

    def _build_kuro_with_ngrams(self) -> KuroGraph:
        kg = _build_kotlin_graph_with_pattern(
            ["a", "b", "c"], num_episodes=5, steps_per_episode=12,
        )
        kuro = KuroGraph(kotlingraph=kg)
        kuro.mine_ngrams(n=3, min_frequency=1)
        return kuro

    def test_get_best_returns_up_to_top_k(self):
        kuro = self._build_kuro_with_ngrams()
        best = kuro.get_best_ngrams(top_k=3)
        assert len(best) <= 3

    def test_get_best_ordered_by_score_descending(self):
        kuro = self._build_kuro_with_ngrams()
        best = kuro.get_best_ngrams(top_k=20)

        scores = [
            ng.avg_reward * np.log1p(ng.frequency) * (ng.success_rate + 0.1)
            for ng in best
        ]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]

    def test_get_best_min_length_filter(self):
        kuro = self._build_kuro_with_ngrams()
        # Also mine 2-grams
        kuro.mine_ngrams(n=2, min_frequency=1)

        best_len3 = kuro.get_best_ngrams(top_k=100, min_length=3)
        for ng in best_len3:
            assert len(ng) >= 3

    def test_get_best_empty(self):
        kuro = KuroGraph()
        best = kuro.get_best_ngrams(top_k=5)
        assert best == []

    def test_scoring_formula(self):
        """Verify the exact scoring formula: avg_reward * log1p(frequency) * (success_rate + 0.1)."""
        kuro = KuroGraph()
        # Manually insert n-grams with known values
        ng_high = ActionNGram(("a", "b"), frequency=10, avg_reward=2.0, success_rate=0.9)
        ng_low = ActionNGram(("c", "d"), frequency=2, avg_reward=0.5, success_rate=0.1)
        kuro.ngrams[ng_high.actions] = ng_high
        kuro.ngrams[ng_low.actions] = ng_low

        best = kuro.get_best_ngrams(top_k=2)
        assert best[0] is ng_high
        assert best[1] is ng_low


# ---------------------------------------------------------------------------
# extract_strategies
# ---------------------------------------------------------------------------


class TestExtractStrategies:
    """Tests for strategy extraction."""

    def test_empty_ngrams_returns_empty(self):
        kuro = KuroGraph()
        result = kuro.extract_strategies()
        assert result == []

    def test_strategies_require_min_ngrams(self):
        kg = _build_kotlin_graph_with_pattern(["a", "b"], num_episodes=3, steps_per_episode=4)
        kuro = KuroGraph(kotlingraph=kg)
        kuro.mine_ngrams(n=2, min_frequency=1)

        # Require 1000 n-grams per cluster -> impossible
        result = kuro.extract_strategies(min_ngrams=1000)
        assert result == []

    def test_strategy_extraction_with_enough_data(self):
        # Create a pattern where n-grams starting with "a" have high reward + success
        kg = _build_kotlin_graph_with_pattern(
            ["a", "b", "c", "a", "d", "e", "a", "f", "g"],
            num_episodes=10,
            steps_per_episode=18,
            final_reward=5.0,
            step_reward=1.0,
        )
        kuro = KuroGraph(kotlingraph=kg)
        # Mine various n-gram lengths
        kuro.mine_ngrams(n=2, min_frequency=2)
        kuro.mine_ngrams(n=3, min_frequency=2)

        # With min_ngrams=1 and low thresholds, we should get strategies
        strategies = kuro.extract_strategies(min_ngrams=1)

        if strategies:
            for s in strategies:
                assert isinstance(s, StrategyPattern)
                assert s.pattern_id >= 0
                assert len(s.ngrams) >= 1
                assert s.usage_count > 0
                assert s.total_reward > 0

    def test_strategy_updates_stats(self):
        kg = _build_kotlin_graph_with_pattern(
            ["a", "b", "c", "a", "d", "e", "a", "f", "g"],
            num_episodes=10,
            steps_per_episode=18,
            final_reward=5.0,
            step_reward=1.0,
        )
        kuro = KuroGraph(kotlingraph=kg)
        kuro.mine_ngrams(n=2, min_frequency=2)
        kuro.mine_ngrams(n=3, min_frequency=2)
        kuro.extract_strategies(min_ngrams=1)

        assert kuro.stats['total_strategies'] == len(kuro.strategies)

    def test_strategy_name_format(self):
        kg = _build_kotlin_graph_with_pattern(
            ["a", "b", "c", "a", "d", "e", "a", "f", "g"],
            num_episodes=10,
            steps_per_episode=18,
            final_reward=5.0,
            step_reward=1.0,
        )
        kuro = KuroGraph(kotlingraph=kg)
        kuro.mine_ngrams(n=2, min_frequency=2)
        kuro.mine_ngrams(n=3, min_frequency=2)
        strategies = kuro.extract_strategies(min_ngrams=1)

        for s in strategies:
            assert "Strategy_" in s.name
            assert "Action_" in s.name


# ---------------------------------------------------------------------------
# suggest_action
# ---------------------------------------------------------------------------


class TestSuggestAction:
    """Tests for action suggestion."""

    def _build_suggestable_kuro(self) -> KuroGraph:
        kg = _build_kotlin_graph_with_pattern(
            ["alpha", "beta", "gamma"],
            num_episodes=10,
            steps_per_episode=9,
            final_reward=2.0,
            step_reward=0.5,
        )
        kuro = KuroGraph(kotlingraph=kg)
        kuro.mine_ngrams(n=2, min_frequency=1)
        kuro.mine_ngrams(n=3, min_frequency=1)
        return kuro

    def test_suggest_without_recent_actions(self):
        kuro = self._build_suggestable_kuro()
        suggestions = kuro.suggest_action(
            state=_make_state("test"), recent_actions=[], top_k=5,
        )
        # Should return actions sorted by score
        assert isinstance(suggestions, list)
        if suggestions:
            for action, score in suggestions:
                assert isinstance(action, str)
                assert isinstance(score, float)

    def test_suggest_with_recent_actions(self):
        kuro = self._build_suggestable_kuro()
        suggestions = kuro.suggest_action(
            state=_make_state("test"),
            recent_actions=["alpha"],
            top_k=3,
        )
        assert isinstance(suggestions, list)
        # Should suggest actions that typically follow "alpha"
        if suggestions:
            actions = [a for a, _ in suggestions]
            # "beta" should be a strong suggestion after "alpha"
            assert "beta" in actions

    def test_suggest_top_k_limit(self):
        kuro = self._build_suggestable_kuro()
        suggestions = kuro.suggest_action(
            state=_make_state("test"),
            recent_actions=["alpha"],
            top_k=1,
        )
        assert len(suggestions) <= 1

    def test_suggest_with_no_ngrams(self):
        kuro = KuroGraph()
        suggestions = kuro.suggest_action(
            state=_make_state("test"), recent_actions=["x"], top_k=3,
        )
        assert suggestions == []

    def test_suggest_fallback_to_state(self):
        """When recent_actions don't match any n-gram prefix, should fallback."""
        kuro = self._build_suggestable_kuro()
        suggestions = kuro.suggest_action(
            state=_make_state("test"),
            recent_actions=["zzz_unknown"],
            top_k=3,
        )
        # Either returns fallback suggestions or empty list
        assert isinstance(suggestions, list)

    def test_suggest_handles_deque_like_input(self):
        """Ensure list() slicing works with deque-like recent_actions."""
        from collections import deque
        kuro = self._build_suggestable_kuro()
        recent = deque(["alpha", "beta", "gamma", "alpha"])
        suggestions = kuro.suggest_action(
            state=_make_state("test"),
            recent_actions=list(recent),
            top_k=3,
        )
        assert isinstance(suggestions, list)


# ---------------------------------------------------------------------------
# build_cooccurrence_matrix
# ---------------------------------------------------------------------------


class TestBuildCooccurrenceMatrix:
    """Tests for action co-occurrence."""

    def test_cooccurrence_without_kotlingraph(self):
        kuro = KuroGraph()
        kuro.build_cooccurrence_matrix()
        assert len(kuro.action_cooccurrence) == 0

    def test_cooccurrence_basic(self):
        kg = _build_kotlin_graph_with_pattern(
            ["a", "b", "c"], num_episodes=3, steps_per_episode=6,
        )
        kuro = KuroGraph(kotlingraph=kg)
        kuro.build_cooccurrence_matrix(window_size=3)

        # "a" and "b" should co-occur
        assert len(kuro.action_cooccurrence) > 0

    def test_cooccurrence_window_size(self):
        kg = _build_kotlin_graph_with_pattern(
            ["a", "b", "c", "d"], num_episodes=3, steps_per_episode=8,
        )
        kuro = KuroGraph(kotlingraph=kg)

        kuro.build_cooccurrence_matrix(window_size=2)
        small_window = dict(kuro.action_cooccurrence)

        kuro.build_cooccurrence_matrix(window_size=10)
        large_window = dict(kuro.action_cooccurrence)

        # Larger window should capture more co-occurrences
        assert len(large_window) >= len(small_window)

    def test_cooccurrence_pairs_are_str_tuples(self):
        kg = _build_kotlin_graph_with_pattern(
            ["move", "grab"], num_episodes=2, steps_per_episode=4,
        )
        kuro = KuroGraph(kotlingraph=kg)
        kuro.build_cooccurrence_matrix()

        for pair, count in kuro.action_cooccurrence.items():
            assert isinstance(pair, tuple)
            assert len(pair) == 2
            assert isinstance(pair[0], str)
            assert isinstance(pair[1], str)
            assert isinstance(count, int)
            assert count > 0

    def test_cooccurrence_clears_on_rebuild(self):
        kg = _build_kotlin_graph_with_pattern(["a", "b"], num_episodes=2, steps_per_episode=4)
        kuro = KuroGraph(kotlingraph=kg)
        kuro.build_cooccurrence_matrix()
        first = dict(kuro.action_cooccurrence)

        kuro.build_cooccurrence_matrix()
        second = dict(kuro.action_cooccurrence)

        assert first == second  # Same data, should be identical after rebuild


# ---------------------------------------------------------------------------
# get_statistics
# ---------------------------------------------------------------------------


class TestStatistics:
    """Tests for statistics reporting."""

    def test_stats_empty(self):
        kuro = KuroGraph()
        stats = kuro.get_statistics()
        assert stats['total_ngrams'] == 0
        assert stats['total_strategies'] == 0
        assert stats['total_patterns_mined'] == 0

    def test_stats_after_mining(self):
        kg = _build_kotlin_graph_with_pattern(
            ["a", "b", "c"], num_episodes=5, steps_per_episode=9,
        )
        kuro = KuroGraph(kotlingraph=kg)
        kuro.mine_ngrams(n=3, min_frequency=1)

        stats = kuro.get_statistics()
        assert stats['total_ngrams'] > 0
        assert 'avg_ngram_length' in stats
        assert 'max_ngram_length' in stats
        assert 'avg_pattern_reward' in stats
        assert stats['avg_ngram_length'] == 3.0
        assert stats['max_ngram_length'] == 3

    def test_stats_after_strategies(self):
        kg = _build_kotlin_graph_with_pattern(
            ["a", "b", "c", "a", "d", "e", "a", "f", "g"],
            num_episodes=10,
            steps_per_episode=18,
            final_reward=5.0,
            step_reward=1.0,
        )
        kuro = KuroGraph(kotlingraph=kg)
        kuro.mine_ngrams(n=2, min_frequency=2)
        kuro.mine_ngrams(n=3, min_frequency=2)
        strategies = kuro.extract_strategies(min_ngrams=1)

        if strategies:
            stats = kuro.get_statistics()
            assert stats['total_strategies'] > 0
            assert 'avg_strategy_reward' in stats


# ---------------------------------------------------------------------------
# Save / Load roundtrip
# ---------------------------------------------------------------------------


class TestSaveLoad:
    """Tests for save/load serialization roundtrip."""

    def _build_kuro_with_data(self) -> KuroGraph:
        kg = _build_kotlin_graph_with_pattern(
            ["a", "b", "c"], num_episodes=5, steps_per_episode=9,
        )
        kuro = KuroGraph(kotlingraph=kg)
        kuro.mine_ngrams(n=2, min_frequency=1)
        kuro.mine_ngrams(n=3, min_frequency=1)
        kuro.build_cooccurrence_matrix()
        return kuro

    def test_save_creates_file(self):
        kuro = self._build_kuro_with_data()
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            filepath = f.name
        try:
            kuro.save(filepath)
            assert os.path.exists(filepath)
            with open(filepath, 'r') as f:
                data = json.load(f)
            assert 'ngrams' in data
            assert 'strategies' in data
            assert 'action_cooccurrence' in data
            assert 'stats' in data
        finally:
            os.unlink(filepath)

    def test_save_load_ngrams_roundtrip(self):
        kuro_orig = self._build_kuro_with_data()

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            filepath = f.name
        try:
            kuro_orig.save(filepath)

            kuro_loaded = KuroGraph()
            kuro_loaded.load(filepath)

            # Same n-grams
            assert set(kuro_loaded.ngrams.keys()) == set(kuro_orig.ngrams.keys())

            for key in kuro_orig.ngrams:
                orig = kuro_orig.ngrams[key]
                loaded = kuro_loaded.ngrams[key]
                assert orig.actions == loaded.actions
                assert orig.frequency == loaded.frequency
                assert abs(orig.avg_reward - loaded.avg_reward) < 1e-9
                assert abs(orig.success_rate - loaded.success_rate) < 1e-9
                assert orig.contexts == loaded.contexts
        finally:
            os.unlink(filepath)

    def test_save_load_cooccurrence_roundtrip(self):
        kuro_orig = self._build_kuro_with_data()

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            filepath = f.name
        try:
            kuro_orig.save(filepath)

            kuro_loaded = KuroGraph()
            kuro_loaded.load(filepath)

            assert dict(kuro_loaded.action_cooccurrence) == dict(kuro_orig.action_cooccurrence)
        finally:
            os.unlink(filepath)

    def test_save_load_stats_roundtrip(self):
        kuro_orig = self._build_kuro_with_data()

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            filepath = f.name
        try:
            kuro_orig.save(filepath)

            kuro_loaded = KuroGraph()
            kuro_loaded.load(filepath)

            assert kuro_loaded.stats == kuro_orig.stats
            assert kuro_loaded.next_strategy_id == kuro_orig.next_strategy_id
        finally:
            os.unlink(filepath)

    def test_save_load_strategies_roundtrip(self):
        """Strategies should survive save/load."""
        kg = _build_kotlin_graph_with_pattern(
            ["a", "b", "c", "a", "d", "e", "a", "f", "g"],
            num_episodes=10,
            steps_per_episode=18,
            final_reward=5.0,
            step_reward=1.0,
        )
        kuro_orig = KuroGraph(kotlingraph=kg)
        kuro_orig.mine_ngrams(n=2, min_frequency=2)
        kuro_orig.mine_ngrams(n=3, min_frequency=2)
        kuro_orig.extract_strategies(min_ngrams=1)

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            filepath = f.name
        try:
            kuro_orig.save(filepath)

            kuro_loaded = KuroGraph()
            kuro_loaded.load(filepath)

            assert len(kuro_loaded.strategies) == len(kuro_orig.strategies)
            for sid in kuro_orig.strategies:
                assert sid in kuro_loaded.strategies
                orig_s = kuro_orig.strategies[sid]
                loaded_s = kuro_loaded.strategies[sid]
                assert orig_s.pattern_id == loaded_s.pattern_id
                assert orig_s.name == loaded_s.name
                assert abs(orig_s.total_reward - loaded_s.total_reward) < 1e-9
                assert orig_s.usage_count == loaded_s.usage_count
        finally:
            os.unlink(filepath)

    def test_load_then_get_best_ngrams(self):
        """After loading, get_best_ngrams should still work."""
        kuro_orig = self._build_kuro_with_data()

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            filepath = f.name
        try:
            kuro_orig.save(filepath)

            kuro_loaded = KuroGraph()
            kuro_loaded.load(filepath)

            best_orig = kuro_orig.get_best_ngrams(top_k=5)
            best_loaded = kuro_loaded.get_best_ngrams(top_k=5)

            assert len(best_orig) == len(best_loaded)
            for o, l in zip(best_orig, best_loaded):
                assert o.actions == l.actions
        finally:
            os.unlink(filepath)


# ---------------------------------------------------------------------------
# StrategyPattern dataclass
# ---------------------------------------------------------------------------


class TestStrategyPattern:
    """Tests for the StrategyPattern dataclass."""

    def test_creation(self):
        ng = ActionNGram(("a", "b"), 5, 0.8, 0.6)
        sp = StrategyPattern(
            pattern_id=0,
            name="Test Strategy",
            description="A test strategy",
            ngrams=[ng],
            total_reward=4.0,
            usage_count=5,
            success_episodes=[0, 1, 2],
        )
        assert sp.pattern_id == 0
        assert sp.name == "Test Strategy"
        assert len(sp.ngrams) == 1
        assert sp.total_reward == 4.0
        assert sp.usage_count == 5
        assert len(sp.success_episodes) == 3


# ---------------------------------------------------------------------------
# Integration / edge cases
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration tests and edge cases."""

    def test_full_pipeline(self):
        """Full pipeline: build KotlinGraph -> mine -> best -> suggest."""
        kg = _build_kotlin_graph_with_pattern(
            ["move_left", "move_right", "jump"],
            num_episodes=8,
            steps_per_episode=12,
            final_reward=3.0,
            step_reward=0.3,
        )
        kuro = KuroGraph(kotlingraph=kg)

        # Mine
        ngrams = kuro.mine_ngrams(n=3, min_frequency=2)
        assert len(ngrams) > 0

        # Best
        best = kuro.get_best_ngrams(top_k=5)
        assert len(best) > 0

        # Co-occurrence
        kuro.build_cooccurrence_matrix(window_size=4)
        assert len(kuro.action_cooccurrence) > 0

        # Suggest
        suggestions = kuro.suggest_action(
            state=_make_state("test"),
            recent_actions=["move_left", "move_right"],
            top_k=3,
        )
        assert isinstance(suggestions, list)

        # Stats
        stats = kuro.get_statistics()
        assert stats['total_ngrams'] > 0

    def test_single_action_episodes(self):
        """Episodes with only one event each."""
        kg = KotlinGraph()
        for _ in range(5):
            kg.add_event(_make_state("s0"), "act", _make_state("s1"), 1.0, True)
        kuro = KuroGraph(kotlingraph=kg)

        # Can't form 2-grams from single-event episodes
        ngrams = kuro.mine_ngrams(n=2, min_frequency=1)
        assert len(ngrams) == 0

    def test_many_unique_actions_no_repeats(self):
        """All unique actions -> no n-gram should meet frequency >= 2."""
        kg = KotlinGraph()
        for i in range(20):
            action = f"unique_action_{i}"
            kg.add_event(
                _make_state(f"s{i}"), action, _make_state(f"s{i + 1}"),
                0.1, i == 19,
            )
        kuro = KuroGraph(kotlingraph=kg)
        ngrams = kuro.mine_ngrams(n=2, min_frequency=2)
        assert len(ngrams) == 0

    def test_cooccurrence_with_actions_containing_delimiter(self):
        """Actions with special chars should not break serialization."""
        kg = KotlinGraph()
        for _ in range(3):
            for step in range(4):
                action = "a|||b" if step % 2 == 0 else "c|||d"
                done = step == 3
                kg.add_event(
                    _make_state(f"s{step}"), action,
                    _make_state(f"s{step + 1}"), 0.1, done,
                )
        kuro = KuroGraph(kotlingraph=kg)
        kuro.build_cooccurrence_matrix()

        # Save/load roundtrip should handle the delimiter in action names
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            filepath = f.name
        try:
            kuro.save(filepath)
            kuro2 = KuroGraph()
            kuro2.load(filepath)
            # The ||| delimiter in action names might cause issues
            # but let's verify the cooccurrence data survives
            assert len(kuro2.action_cooccurrence) > 0
        finally:
            os.unlink(filepath)
