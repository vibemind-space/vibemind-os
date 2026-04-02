"""Tests for PipelineDataReplicator service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_replicator import PipelineDataReplicator


class TestPipelineDataReplicatorIDGeneration:
    """ID prefix and uniqueness."""

    def test_id_has_correct_prefix(self):
        rep = PipelineDataReplicator()
        rid = rep.replicate("p1", "key1")
        assert rid.startswith("pdrp-")

    def test_ids_are_unique(self):
        rep = PipelineDataReplicator()
        ids = [rep.replicate("p1", f"k{i}") for i in range(10)]
        assert len(set(ids)) == 10

    def test_id_is_string(self):
        rep = PipelineDataReplicator()
        rid = rep.replicate("p1", "key1")
        assert isinstance(rid, str)


class TestPipelineDataReplicatorBasic:
    """Basic replicate operations."""

    def test_replicate_returns_id(self):
        rep = PipelineDataReplicator()
        rid = rep.replicate("pipeline-a", "data-key-1")
        assert rid is not None
        assert len(rid) > len("pdrp-")

    def test_replicate_stores_pipeline_id(self):
        rep = PipelineDataReplicator()
        rid = rep.replicate("pipeline-a", "dk1")
        record = rep.get_replication(rid)
        assert record["pipeline_id"] == "pipeline-a"

    def test_replicate_stores_data_key(self):
        rep = PipelineDataReplicator()
        rid = rep.replicate("p1", "my-data-key")
        record = rep.get_replication(rid)
        assert record["data_key"] == "my-data-key"

    def test_replicate_with_targets(self):
        rep = PipelineDataReplicator()
        rid = rep.replicate("p1", "k1", targets=["t1", "t2"])
        record = rep.get_replication(rid)
        assert record["targets"] == ["t1", "t2"]

    def test_replicate_without_targets_defaults_empty(self):
        rep = PipelineDataReplicator()
        rid = rep.replicate("p1", "k1")
        record = rep.get_replication(rid)
        assert record["targets"] == []

    def test_replicate_with_metadata(self):
        rep = PipelineDataReplicator()
        rid = rep.replicate("p1", "k1", metadata={"env": "staging"})
        record = rep.get_replication(rid)
        assert record["metadata"]["env"] == "staging"

    def test_replicate_without_metadata_defaults_empty(self):
        rep = PipelineDataReplicator()
        rid = rep.replicate("p1", "k1")
        record = rep.get_replication(rid)
        assert record["metadata"] == {}


class TestPipelineDataReplicatorGet:
    """get_replication found / not found."""

    def test_get_existing_record(self):
        rep = PipelineDataReplicator()
        rid = rep.replicate("p1", "k1")
        record = rep.get_replication(rid)
        assert record is not None
        assert record["record_id"] == rid

    def test_get_nonexistent_returns_none(self):
        rep = PipelineDataReplicator()
        assert rep.get_replication("pdrp-does-not-exist") is None

    def test_get_returns_copy(self):
        rep = PipelineDataReplicator()
        rid = rep.replicate("p1", "k1", metadata={"x": 1})
        r1 = rep.get_replication(rid)
        r1["pipeline_id"] = "mutated"
        r2 = rep.get_replication(rid)
        assert r2["pipeline_id"] == "p1"


class TestPipelineDataReplicatorList:
    """get_replications filtering, ordering, and limit."""

    def test_list_returns_all_when_no_filter(self):
        rep = PipelineDataReplicator()
        rep.replicate("p1", "k1")
        rep.replicate("p2", "k2")
        assert len(rep.get_replications()) == 2

    def test_list_filters_by_pipeline_id(self):
        rep = PipelineDataReplicator()
        rep.replicate("p1", "k1")
        rep.replicate("p2", "k2")
        rep.replicate("p1", "k3")
        results = rep.get_replications(pipeline_id="p1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "p1" for r in results)

    def test_list_newest_first(self):
        rep = PipelineDataReplicator()
        r1 = rep.replicate("p1", "k1")
        r2 = rep.replicate("p1", "k2")
        r3 = rep.replicate("p1", "k3")
        results = rep.get_replications()
        assert results[0]["record_id"] == r3
        assert results[-1]["record_id"] == r1

    def test_list_respects_limit(self):
        rep = PipelineDataReplicator()
        for i in range(10):
            rep.replicate("p1", f"k{i}")
        results = rep.get_replications(limit=3)
        assert len(results) == 3


class TestPipelineDataReplicatorCount:
    """get_replication_count."""

    def test_count_all(self):
        rep = PipelineDataReplicator()
        rep.replicate("p1", "k1")
        rep.replicate("p2", "k2")
        assert rep.get_replication_count() == 2

    def test_count_filtered_by_pipeline(self):
        rep = PipelineDataReplicator()
        rep.replicate("p1", "k1")
        rep.replicate("p2", "k2")
        rep.replicate("p1", "k3")
        assert rep.get_replication_count(pipeline_id="p1") == 2

    def test_count_empty(self):
        rep = PipelineDataReplicator()
        assert rep.get_replication_count() == 0


class TestPipelineDataReplicatorStats:
    """get_stats."""

    def test_stats_totals(self):
        rep = PipelineDataReplicator()
        rep.replicate("p1", "k1")
        rep.replicate("p2", "k2")
        rep.replicate("p1", "k3")
        stats = rep.get_stats()
        assert stats["total_replications"] == 3
        assert stats["unique_pipelines"] == 2

    def test_stats_empty(self):
        rep = PipelineDataReplicator()
        stats = rep.get_stats()
        assert stats["total_replications"] == 0


class TestPipelineDataReplicatorOnChange:
    """on_change property and callback firing."""

    def test_on_change_initially_none(self):
        rep = PipelineDataReplicator()
        assert rep.on_change is None

    def test_on_change_setter_and_getter(self):
        rep = PipelineDataReplicator()
        cb = lambda action, data: None
        rep.on_change = cb
        assert rep.on_change is cb

    def test_on_change_fires_on_replicate(self):
        rep = PipelineDataReplicator()
        events = []
        rep.on_change = lambda action, data: events.append((action, data))
        rep.replicate("p1", "k1")
        assert len(events) == 1
        assert events[0][0] == "replicate"

    def test_on_change_exception_swallowed(self):
        rep = PipelineDataReplicator()
        rep.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        # Should not raise
        rid = rep.replicate("p1", "k1")
        assert rid is not None


class TestPipelineDataReplicatorRemoveCallback:
    """remove_callback returns bool."""

    def test_remove_existing_callback_returns_true(self):
        rep = PipelineDataReplicator()
        rep._state.callbacks["my_cb"] = lambda a, d: None
        assert rep.remove_callback("my_cb") is True

    def test_remove_nonexistent_callback_returns_false(self):
        rep = PipelineDataReplicator()
        assert rep.remove_callback("no_such") is False


class TestPipelineDataReplicatorPrune:
    """Pruning when exceeding MAX_ENTRIES."""

    def test_prune_evicts_oldest(self):
        rep = PipelineDataReplicator()
        rep.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(rep.replicate("p1", f"k{i}"))
        assert len(rep._state.entries) == 5
        # The first two should have been evicted
        assert rep.get_replication(ids[0]) is None
        assert rep.get_replication(ids[1]) is None
        # The latest should still exist
        assert rep.get_replication(ids[6]) is not None


class TestPipelineDataReplicatorReset:
    """reset clears state."""

    def test_reset_clears_entries(self):
        rep = PipelineDataReplicator()
        rep.replicate("p1", "k1")
        rep.replicate("p2", "k2")
        rep.reset()
        assert rep.get_replication_count() == 0

    def test_reset_fires_event(self):
        rep = PipelineDataReplicator()
        events = []
        rep.on_change = lambda a, d: events.append(a)
        rep.reset()
        assert "reset" in events

    def test_reset_resets_seq(self):
        rep = PipelineDataReplicator()
        rep.replicate("p1", "k1")
        rep.reset()
        assert rep._state._seq == 0
