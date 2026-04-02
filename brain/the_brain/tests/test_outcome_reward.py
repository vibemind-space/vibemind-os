# tests/test_outcome_reward.py
"""Tests for OutcomeRewardTracker — outcome-based reward signals."""
import time
import threading
from unittest.mock import MagicMock, patch
from core.outcome_reward import OutcomeRewardTracker


def _make_thought(thought_id="abc", content="test thought", relevance=0.5):
    t = MagicMock()
    t.thought_id = thought_id
    t.content = content
    t.relevance = relevance
    return t


class TestOutcomeReward:

    def test_moltbook_entry_records_reward(self):
        bridge = MagicMock()
        tracker = OutcomeRewardTracker(bridge=bridge, cte=MagicMock())
        tracker.on_moltbook_entry("abc")
        bridge.record_reward.assert_called_once_with("abc", 0.5, "moltbook_entry")
        assert tracker.get_stats()['moltbook_entry'] == 1

    def test_moltbook_entry_dedup(self):
        bridge = MagicMock()
        tracker = OutcomeRewardTracker(bridge=bridge, cte=MagicMock())
        tracker.on_moltbook_entry("abc")
        tracker.on_moltbook_entry("abc")  # duplicate
        assert bridge.record_reward.call_count == 1

    def test_moltbook_entry_no_bridge(self):
        tracker = OutcomeRewardTracker(bridge=None, cte=MagicMock())
        tracker.on_moltbook_entry("abc")  # no crash

    def test_mkg_edges_rewards_top3(self):
        bridge = MagicMock()
        cte = MagicMock()
        thoughts = [_make_thought(f"t{i}", relevance=0.1 * i) for i in range(10)]
        cte._thought_lock = threading.Lock()
        cte._thoughts = thoughts
        tracker = OutcomeRewardTracker(bridge=bridge, cte=cte)
        tracker.on_new_mkg_edges(5)
        assert bridge.record_reward.call_count == 3
        assert tracker.get_stats()['mkg_edge'] == 3

    def test_mkg_edges_zero_noop(self):
        bridge = MagicMock()
        tracker = OutcomeRewardTracker(bridge=bridge, cte=MagicMock())
        tracker.on_new_mkg_edges(0)
        bridge.record_reward.assert_not_called()

    def test_thoughts_cited(self):
        bridge = MagicMock()
        tracker = OutcomeRewardTracker(bridge=bridge, cte=MagicMock())
        tracker.on_thoughts_cited(["a", "b", "c"])
        assert bridge.record_reward.call_count == 3
        bridge.record_reward.assert_any_call("a", 0.9, "cited_in_response")
        assert tracker.get_stats()['cited'] == 3

    def test_thoughts_cited_dedup(self):
        bridge = MagicMock()
        tracker = OutcomeRewardTracker(bridge=bridge, cte=MagicMock())
        tracker.on_thoughts_cited(["a", "b"])
        tracker.on_thoughts_cited(["a", "c"])  # "a" already rewarded
        assert bridge.record_reward.call_count == 3  # a, b, c

    def test_redundancy_detected(self):
        bridge = MagicMock()
        mock_store = MagicMock()
        mock_idx = MagicMock()
        mock_idx.embed.return_value = [0.1] * 384
        mock_idx.search.return_value = [("entry1", 0.92)]
        mock_store.semantic_index = mock_idx
        tracker = OutcomeRewardTracker(bridge=bridge, cte=MagicMock(),
                                       moltbook_store=mock_store)
        thought = _make_thought("abc", "some repeated content")
        tracker.check_redundancy(thought)
        bridge.record_reward.assert_called_once_with("abc", -0.2, "redundant_thought")
        assert tracker.get_stats()['redundant'] == 1

    def test_redundancy_not_triggered(self):
        bridge = MagicMock()
        mock_store = MagicMock()
        mock_idx = MagicMock()
        mock_idx.embed.return_value = [0.1] * 384
        mock_idx.search.return_value = []  # no matches above 0.85
        mock_store.semantic_index = mock_idx
        tracker = OutcomeRewardTracker(bridge=bridge, cte=MagicMock(),
                                       moltbook_store=mock_store)
        tracker.check_redundancy(_make_thought())
        bridge.record_reward.assert_not_called()

    def test_stats(self):
        tracker = OutcomeRewardTracker(bridge=MagicMock(), cte=MagicMock())
        stats = tracker.get_stats()
        assert stats == {'moltbook_entry': 0, 'mkg_edge': 0, 'cited': 0, 'redundant': 0}

    def test_thread_safety(self):
        bridge = MagicMock()
        tracker = OutcomeRewardTracker(bridge=bridge, cte=MagicMock())
        errors = []
        def worker(i):
            try:
                tracker.on_moltbook_entry(f"t{i}")
                tracker.on_thoughts_cited([f"c{i}"])
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
