"""Tests for PipelineDataSerializer service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_serializer import PipelineDataSerializer


class TestSerialize:
    """Tests for the serialize method."""

    def test_serialize_returns_string_id(self):
        s = PipelineDataSerializer()
        rid = s.serialize("pipe-1", {"key": "value"})
        assert isinstance(rid, str)
        assert rid.startswith("pdsr-")

    def test_serialize_json_default(self):
        s = PipelineDataSerializer()
        rid = s.serialize("pipe-1", {"x": 1})
        record = s.get_record(rid)
        assert record["format"] == "json"
        assert record["data"] == {"x": 1}

    def test_serialize_csv_format(self):
        s = PipelineDataSerializer()
        rid = s.serialize("pipe-1", {"name": "alice", "age": 30}, format="csv")
        record = s.get_record(rid)
        assert record["format"] == "csv"
        assert b"name" in record["serialized"]

    def test_serialize_text_format(self):
        s = PipelineDataSerializer()
        rid = s.serialize("pipe-1", "hello world", format="text")
        record = s.get_record(rid)
        assert record["serialized"] == b"hello world"

    def test_serialize_msgpack_format(self):
        s = PipelineDataSerializer()
        rid = s.serialize("pipe-1", {"a": 1}, format="msgpack")
        record = s.get_record(rid)
        assert record["format"] == "msgpack"
        assert record["size_bytes"] > 0

    def test_serialize_unsupported_format_raises(self):
        s = PipelineDataSerializer()
        try:
            s.serialize("pipe-1", {"a": 1}, format="xml")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_serialize_with_metadata(self):
        s = PipelineDataSerializer()
        rid = s.serialize("pipe-1", {"x": 1}, metadata={"author": "test"})
        record = s.get_record(rid)
        assert record["metadata"]["author"] == "test"

    def test_serialize_deep_copies_data(self):
        s = PipelineDataSerializer()
        original = {"nested": {"a": 1}}
        rid = s.serialize("pipe-1", original)
        original["nested"]["a"] = 999
        record = s.get_record(rid)
        assert record["data"]["nested"]["a"] == 1

    def test_serialize_deep_copies_metadata(self):
        s = PipelineDataSerializer()
        meta = {"tags": ["a", "b"]}
        rid = s.serialize("pipe-1", {"x": 1}, metadata=meta)
        meta["tags"].append("c")
        record = s.get_record(rid)
        assert "c" not in record["metadata"]["tags"]


class TestGetRecord:
    """Tests for the get_record method."""

    def test_get_existing_record(self):
        s = PipelineDataSerializer()
        rid = s.serialize("pipe-1", {"x": 1})
        record = s.get_record(rid)
        assert record is not None
        assert record["record_id"] == rid

    def test_get_missing_record_returns_none(self):
        s = PipelineDataSerializer()
        result = s.get_record("pdsr-nonexistent")
        assert result is None

    def test_get_record_returns_copy(self):
        s = PipelineDataSerializer()
        rid = s.serialize("pipe-1", {"x": 1})
        r1 = s.get_record(rid)
        r2 = s.get_record(rid)
        assert r1 is not r2
        assert r1 == r2


class TestGetRecords:
    """Tests for the get_records method."""

    def test_get_records_all(self):
        s = PipelineDataSerializer()
        s.serialize("pipe-1", {"a": 1})
        s.serialize("pipe-2", {"b": 2})
        records = s.get_records()
        assert len(records) == 2

    def test_get_records_filter_by_pipeline(self):
        s = PipelineDataSerializer()
        s.serialize("pipe-1", {"a": 1})
        s.serialize("pipe-2", {"b": 2})
        s.serialize("pipe-1", {"c": 3})
        records = s.get_records(pipeline_id="pipe-1")
        assert len(records) == 2
        for r in records:
            assert r["pipeline_id"] == "pipe-1"

    def test_get_records_filter_by_format(self):
        s = PipelineDataSerializer()
        s.serialize("pipe-1", {"a": 1}, format="json")
        s.serialize("pipe-1", "hello", format="text")
        records = s.get_records(format="text")
        assert len(records) == 1
        assert records[0]["format"] == "text"

    def test_get_records_sorted_newest_first(self):
        s = PipelineDataSerializer()
        r1 = s.serialize("pipe-1", {"i": 1})
        r2 = s.serialize("pipe-1", {"i": 2})
        r3 = s.serialize("pipe-1", {"i": 3})
        records = s.get_records()
        assert records[0]["record_id"] == r3
        assert records[1]["record_id"] == r2
        assert records[2]["record_id"] == r1

    def test_get_records_limit(self):
        s = PipelineDataSerializer()
        for i in range(10):
            s.serialize("pipe-1", {"i": i})
        records = s.get_records(limit=3)
        assert len(records) == 3

    def test_get_records_empty(self):
        s = PipelineDataSerializer()
        records = s.get_records()
        assert records == []


class TestGetRecordCount:
    """Tests for the get_record_count method."""

    def test_count_all(self):
        s = PipelineDataSerializer()
        s.serialize("pipe-1", {"a": 1})
        s.serialize("pipe-2", {"b": 2})
        assert s.get_record_count() == 2

    def test_count_by_pipeline(self):
        s = PipelineDataSerializer()
        s.serialize("pipe-1", {"a": 1})
        s.serialize("pipe-2", {"b": 2})
        s.serialize("pipe-1", {"c": 3})
        assert s.get_record_count(pipeline_id="pipe-1") == 2
        assert s.get_record_count(pipeline_id="pipe-2") == 1

    def test_count_empty(self):
        s = PipelineDataSerializer()
        assert s.get_record_count() == 0


class TestGetStats:
    """Tests for the get_stats method."""

    def test_stats_empty(self):
        s = PipelineDataSerializer()
        stats = s.get_stats()
        assert stats["total_records"] == 0
        assert stats["total_size_bytes"] == 0

    def test_stats_with_records(self):
        s = PipelineDataSerializer()
        s.serialize("pipe-1", {"a": 1}, format="json")
        s.serialize("pipe-2", "hello", format="text")
        stats = s.get_stats()
        assert stats["total_records"] == 2
        assert stats["total_size_bytes"] > 0
        assert "json" in stats["formats"]
        assert "text" in stats["formats"]
        assert "pipe-1" in stats["pipelines"]
        assert "pipe-2" in stats["pipelines"]


class TestReset:
    """Tests for the reset method."""

    def test_reset_clears_entries(self):
        s = PipelineDataSerializer()
        s.serialize("pipe-1", {"a": 1})
        s.reset()
        assert s.get_record_count() == 0

    def test_reset_clears_callbacks(self):
        s = PipelineDataSerializer()
        s._callbacks["cb1"] = lambda a, d: None
        s.on_change = lambda a, d: None
        s.reset()
        assert len(s._callbacks) == 0
        assert s.on_change is None


class TestCallbacks:
    """Tests for callback functionality."""

    def test_on_change_fires_on_serialize(self):
        s = PipelineDataSerializer()
        events = []
        s.on_change = lambda action, data: events.append((action, data))
        s.serialize("pipe-1", {"x": 1})
        assert len(events) == 1
        assert events[0][0] == "serialize"

    def test_named_callback_fires(self):
        s = PipelineDataSerializer()
        events = []
        s._callbacks["my_cb"] = lambda action, data: events.append((action, data))
        s.serialize("pipe-1", {"x": 1})
        assert len(events) == 1

    def test_on_change_fires_before_named_callbacks(self):
        s = PipelineDataSerializer()
        order = []
        s.on_change = lambda a, d: order.append("on_change")
        s._callbacks["cb1"] = lambda a, d: order.append("cb1")
        s.serialize("pipe-1", {"x": 1})
        assert order[0] == "on_change"
        assert order[1] == "cb1"

    def test_callback_exception_silenced(self):
        s = PipelineDataSerializer()
        s.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        # Should not raise
        rid = s.serialize("pipe-1", {"x": 1})
        assert rid.startswith("pdsr-")

    def test_remove_callback_found(self):
        s = PipelineDataSerializer()
        s._callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
        assert "cb1" not in s._callbacks

    def test_remove_callback_not_found(self):
        s = PipelineDataSerializer()
        assert s.remove_callback("nonexistent") is False

    def test_on_change_property_getter_setter(self):
        s = PipelineDataSerializer()
        assert s.on_change is None
        handler = lambda a, d: None
        s.on_change = handler
        assert s.on_change is handler


class TestPrune:
    """Tests for pruning when exceeding MAX_ENTRIES."""

    def test_prune_removes_oldest_quarter(self):
        s = PipelineDataSerializer()
        s.MAX_ENTRIES = 20
        for i in range(25):
            s.serialize("pipe-1", {"i": i})
        # After inserting 21st, prune removes 5 (quarter of 21), leaving 16
        # Then inserts continue; final count should be <= 20
        assert s.get_record_count() <= 20

    def test_prune_preserves_newest(self):
        s = PipelineDataSerializer()
        s.MAX_ENTRIES = 10
        ids = []
        for i in range(15):
            ids.append(s.serialize("pipe-1", {"i": i}))
        # The most recent entries should still be present
        last_id = ids[-1]
        assert s.get_record(last_id) is not None

    def test_unique_ids_across_many(self):
        s = PipelineDataSerializer()
        ids = set()
        for i in range(100):
            rid = s.serialize("pipe-1", {"i": i})
            ids.add(rid)
        assert len(ids) == 100
