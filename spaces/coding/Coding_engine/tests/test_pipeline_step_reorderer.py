"""Tests for PipelineStepReorderer."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_reorderer import PipelineStepReorderer


# --- ID prefix and uniqueness ---

def test_id_has_prefix():
    s = PipelineStepReorderer()
    rid = s.reorder("p1", "step_a", 2)
    assert rid.startswith("psro-")


def test_id_unique():
    s = PipelineStepReorderer()
    r1 = s.reorder("p1", "step_a", 1)
    r2 = s.reorder("p1", "step_a", 1)
    assert r1 != r2


def test_id_length():
    s = PipelineStepReorderer()
    rid = s.reorder("p1", "step_a")
    assert len(rid) == len("psro-") + 12


# --- Stores fields ---

def test_stores_pipeline_id():
    s = PipelineStepReorderer()
    rid = s.reorder("pipe1", "step_x", 3)
    entry = s.get_reorder(rid)
    assert entry["pipeline_id"] == "pipe1"


def test_stores_step_name():
    s = PipelineStepReorderer()
    rid = s.reorder("pipe1", "step_x", 3)
    entry = s.get_reorder(rid)
    assert entry["step_name"] == "step_x"


def test_stores_new_position():
    s = PipelineStepReorderer()
    rid = s.reorder("pipe1", "step_x", 5)
    entry = s.get_reorder(rid)
    assert entry["new_position"] == 5


def test_stores_metadata():
    s = PipelineStepReorderer()
    rid = s.reorder("pipe1", "step_x", 1, metadata={"key": "val"})
    entry = s.get_reorder(rid)
    assert entry["metadata"] == {"key": "val"}


def test_metadata_deepcopy():
    s = PipelineStepReorderer()
    meta = {"nested": [1, 2, 3]}
    rid = s.reorder("p1", "s1", 0, metadata=meta)
    meta["nested"].append(999)
    entry = s.get_reorder(rid)
    assert 999 not in entry["metadata"]["nested"]


def test_created_at_set():
    s = PipelineStepReorderer()
    before = time.time()
    rid = s.reorder("p1", "s1")
    after = time.time()
    entry = s.get_reorder(rid)
    assert before <= entry["created_at"] <= after


# --- Empty input returns "" ---

def test_empty_pipeline_id_returns_empty():
    s = PipelineStepReorderer()
    assert s.reorder("", "step_a") == ""


def test_empty_step_name_returns_empty():
    s = PipelineStepReorderer()
    assert s.reorder("pipe1", "") == ""


def test_both_empty_returns_empty():
    s = PipelineStepReorderer()
    assert s.reorder("", "") == ""


# --- get_reorder ---

def test_get_reorder_found():
    s = PipelineStepReorderer()
    rid = s.reorder("p1", "s1", 2)
    result = s.get_reorder(rid)
    assert result is not None
    assert result["record_id"] == rid


def test_get_reorder_not_found():
    s = PipelineStepReorderer()
    assert s.get_reorder("psro-nonexistent") is None


def test_get_reorder_returns_copy():
    s = PipelineStepReorderer()
    rid = s.reorder("p1", "s1", 2)
    r1 = s.get_reorder(rid)
    r2 = s.get_reorder(rid)
    assert r1 is not r2


# --- get_reorders ---

def test_get_reorders_all():
    s = PipelineStepReorderer()
    s.reorder("p1", "s1")
    s.reorder("p2", "s2")
    s.reorder("p1", "s3")
    results = s.get_reorders()
    assert len(results) == 3


def test_get_reorders_filter_by_pipeline():
    s = PipelineStepReorderer()
    s.reorder("p1", "s1")
    s.reorder("p2", "s2")
    s.reorder("p1", "s3")
    results = s.get_reorders(pipeline_id="p1")
    assert len(results) == 2
    assert all(r["pipeline_id"] == "p1" for r in results)


def test_get_reorders_newest_first():
    s = PipelineStepReorderer()
    r1 = s.reorder("p1", "s1")
    r2 = s.reorder("p1", "s2")
    r3 = s.reorder("p1", "s3")
    results = s.get_reorders()
    assert results[0]["record_id"] == r3
    assert results[-1]["record_id"] == r1


def test_get_reorders_limit():
    s = PipelineStepReorderer()
    for i in range(10):
        s.reorder("p1", f"s{i}")
    results = s.get_reorders(limit=3)
    assert len(results) == 3


# --- get_reorder_count ---

def test_get_reorder_count_total():
    s = PipelineStepReorderer()
    s.reorder("p1", "s1")
    s.reorder("p2", "s2")
    s.reorder("p1", "s3")
    assert s.get_reorder_count() == 3


def test_get_reorder_count_filtered():
    s = PipelineStepReorderer()
    s.reorder("p1", "s1")
    s.reorder("p2", "s2")
    s.reorder("p1", "s3")
    assert s.get_reorder_count(pipeline_id="p1") == 2


def test_get_reorder_count_empty():
    s = PipelineStepReorderer()
    assert s.get_reorder_count() == 0


# --- get_stats ---

def test_stats_empty():
    s = PipelineStepReorderer()
    stats = s.get_stats()
    assert stats["total_reorders"] == 0
    assert stats["unique_pipelines"] == 0


def test_stats_with_data():
    s = PipelineStepReorderer()
    s.reorder("p1", "s1")
    s.reorder("p2", "s2")
    s.reorder("p1", "s3")
    stats = s.get_stats()
    assert stats["total_reorders"] == 3
    assert stats["unique_pipelines"] == 2


# --- Callbacks ---

def test_on_change_called():
    s = PipelineStepReorderer()
    events = []
    s.on_change = lambda action, data: events.append((action, data))
    s.reorder("p1", "s1")
    assert len(events) == 1
    assert events[0][0] == "reordered"


def test_callback_called():
    s = PipelineStepReorderer()
    events = []
    s._state.callbacks["cb1"] = lambda action, data: events.append((action, data))
    s.reorder("p1", "s1")
    assert len(events) == 1
    assert events[0][0] == "reordered"


def test_remove_callback_true():
    s = PipelineStepReorderer()
    s._state.callbacks["cb1"] = lambda a, d: None
    assert s.remove_callback("cb1") is True
    assert "cb1" not in s._state.callbacks


def test_remove_callback_false():
    s = PipelineStepReorderer()
    assert s.remove_callback("nonexistent") is False


# --- Prune ---

def test_prune_reduces_entries():
    s = PipelineStepReorderer()
    s.MAX_ENTRIES = 5
    for i in range(8):
        s.reorder("p1", f"step_{i}", i)
    assert s.get_reorder_count() < 8


# --- Reset ---

def test_reset_clears_entries():
    s = PipelineStepReorderer()
    s.reorder("p1", "s1")
    s.reorder("p2", "s2")
    s.reset()
    assert s.get_reorder_count() == 0


def test_reset_clears_callbacks():
    s = PipelineStepReorderer()
    s._state.callbacks["cb1"] = lambda a, d: None
    s.on_change = lambda a, d: None
    s.reset()
    assert len(s._state.callbacks) == 0
    assert s.on_change is None


def test_reset_clears_seq():
    s = PipelineStepReorderer()
    s.reorder("p1", "s1")
    s.reset()
    assert s._state._seq == 0
