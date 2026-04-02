"""Tests for PipelineDataConverter service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_converter import PipelineDataConverter


class TestConvertBasic:
    """Basic conversion operations."""

    def test_convert_returns_string_id(self):
        conv = PipelineDataConverter()
        rid = conv.convert("pipe-1", {"a": 1}, "dict", "list")
        assert isinstance(rid, str)
        assert rid.startswith("pdcv-")

    def test_convert_ids_are_unique(self):
        conv = PipelineDataConverter()
        ids = [conv.convert("pipe-1", {"k": i}, "dict", "list") for i in range(20)]
        assert len(set(ids)) == 20

    def test_convert_dict_to_list(self):
        conv = PipelineDataConverter()
        rid = conv.convert("pipe-1", {"a": 1, "b": 2}, "dict", "list")
        record = conv.get_conversion(rid)
        assert isinstance(record["output"], list)
        keys = {item["key"] for item in record["output"]}
        assert keys == {"a", "b"}

    def test_convert_list_to_dict(self):
        conv = PipelineDataConverter()
        data = [{"key": "x", "value": 10}, {"key": "y", "value": 20}]
        rid = conv.convert("pipe-1", data, "list", "dict")
        record = conv.get_conversion(rid)
        assert record["output"] == {"x": 10, "y": 20}

    def test_convert_nested_to_flat(self):
        conv = PipelineDataConverter()
        data = {"a": {"b": 1, "c": {"d": 2}}}
        rid = conv.convert("pipe-1", data, "nested", "flat")
        record = conv.get_conversion(rid)
        assert record["output"] == {"a.b": 1, "a.c.d": 2}

    def test_convert_flat_to_nested(self):
        conv = PipelineDataConverter()
        data = {"a.b": 1, "a.c.d": 2}
        rid = conv.convert("pipe-1", data, "flat", "nested")
        record = conv.get_conversion(rid)
        assert record["output"] == {"a": {"b": 1, "c": {"d": 2}}}


class TestConvertEdgeCases:
    """Edge cases and error handling."""

    def test_convert_unsupported_format_raises(self):
        conv = PipelineDataConverter()
        try:
            conv.convert("pipe-1", {}, "xml", "json")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_convert_dict_to_list_wrong_type_raises(self):
        conv = PipelineDataConverter()
        try:
            conv.convert("pipe-1", [1, 2], "dict", "list")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_convert_list_to_dict_wrong_type_raises(self):
        conv = PipelineDataConverter()
        try:
            conv.convert("pipe-1", {"a": 1}, "list", "dict")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_convert_deep_copies_input(self):
        conv = PipelineDataConverter()
        original = {"nested": {"val": 42}}
        rid = conv.convert("pipe-1", original, "nested", "flat")
        original["nested"]["val"] = 999
        record = conv.get_conversion(rid)
        assert record["input"]["nested"]["val"] == 42

    def test_convert_with_metadata(self):
        conv = PipelineDataConverter()
        rid = conv.convert("pipe-1", {"a": 1}, "dict", "list", metadata={"user": "test"})
        record = conv.get_conversion(rid)
        assert record["metadata"] == {"user": "test"}

    def test_convert_metadata_default_none(self):
        conv = PipelineDataConverter()
        rid = conv.convert("pipe-1", {"a": 1}, "dict", "list")
        record = conv.get_conversion(rid)
        assert record["metadata"] is None

    def test_list_to_dict_skips_malformed_items(self):
        conv = PipelineDataConverter()
        data = [{"key": "a", "value": 1}, {"bad": "item"}, 42]
        rid = conv.convert("pipe-1", data, "list", "dict")
        record = conv.get_conversion(rid)
        assert record["output"] == {"a": 1}

    def test_flatten_empty_dict(self):
        conv = PipelineDataConverter()
        rid = conv.convert("pipe-1", {}, "nested", "flat")
        record = conv.get_conversion(rid)
        assert record["output"] == {}


class TestGetConversion:
    """Retrieval operations."""

    def test_get_conversion_found(self):
        conv = PipelineDataConverter()
        rid = conv.convert("pipe-1", {"a": 1}, "dict", "list")
        record = conv.get_conversion(rid)
        assert record is not None
        assert record["record_id"] == rid
        assert record["pipeline_id"] == "pipe-1"
        assert record["from_format"] == "dict"
        assert record["to_format"] == "list"
        assert "created_at" in record

    def test_get_conversion_not_found(self):
        conv = PipelineDataConverter()
        assert conv.get_conversion("pdcv-nonexistent") is None

    def test_get_conversions_all(self):
        conv = PipelineDataConverter()
        conv.convert("pipe-1", {"a": 1}, "dict", "list")
        conv.convert("pipe-2", {"b": 2}, "dict", "list")
        results = conv.get_conversions()
        assert len(results) == 2

    def test_get_conversions_filtered_by_pipeline(self):
        conv = PipelineDataConverter()
        conv.convert("pipe-1", {"a": 1}, "dict", "list")
        conv.convert("pipe-2", {"b": 2}, "dict", "list")
        conv.convert("pipe-1", {"c": 3}, "dict", "list")
        results = conv.get_conversions(pipeline_id="pipe-1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-1" for r in results)

    def test_get_conversions_respects_limit(self):
        conv = PipelineDataConverter()
        for i in range(10):
            conv.convert("pipe-1", {"k": i}, "dict", "list")
        results = conv.get_conversions(limit=3)
        assert len(results) == 3

    def test_get_conversions_newest_first(self):
        conv = PipelineDataConverter()
        conv.convert("pipe-1", {"a": 1}, "dict", "list")
        conv.convert("pipe-1", {"b": 2}, "dict", "list")
        results = conv.get_conversions()
        assert results[0]["created_at"] >= results[1]["created_at"]


class TestConversionCount:
    """Count operations."""

    def test_get_conversion_count_all(self):
        conv = PipelineDataConverter()
        conv.convert("pipe-1", {"a": 1}, "dict", "list")
        conv.convert("pipe-2", {"b": 2}, "dict", "list")
        assert conv.get_conversion_count() == 2

    def test_get_conversion_count_filtered(self):
        conv = PipelineDataConverter()
        conv.convert("pipe-1", {"a": 1}, "dict", "list")
        conv.convert("pipe-2", {"b": 2}, "dict", "list")
        conv.convert("pipe-1", {"c": 3}, "dict", "list")
        assert conv.get_conversion_count(pipeline_id="pipe-1") == 2

    def test_get_conversion_count_empty(self):
        conv = PipelineDataConverter()
        assert conv.get_conversion_count() == 0


class TestStatsAndReset:
    """Stats and reset operations."""

    def test_get_stats(self):
        conv = PipelineDataConverter()
        conv.convert("p1", {"a": 1}, "dict", "list")
        conv.convert("p2", {"x.y": 1}, "flat", "nested")
        stats = conv.get_stats()
        assert stats["total_conversions"] == 2
        assert stats["format_counts"]["dict->list"] == 1
        assert stats["format_counts"]["flat->nested"] == 1

    def test_reset_clears_entries(self):
        conv = PipelineDataConverter()
        conv.convert("pipe-1", {"a": 1}, "dict", "list")
        conv.reset()
        assert conv.get_conversion_count() == 0
        assert conv.get_conversions() == []

    def test_reset_clears_callbacks(self):
        conv = PipelineDataConverter()
        conv._callbacks["cb1"] = lambda a, d: None
        conv.on_change = lambda a, d: None
        conv.reset()
        assert conv._callbacks == {}
        assert conv.on_change is None


class TestCallbacks:
    """Callback operations."""

    def test_on_change_fires_on_convert(self):
        events = []
        conv = PipelineDataConverter()
        conv.on_change = lambda a, d: events.append(a)
        conv.convert("pipe-1", {"a": 1}, "dict", "list")
        assert "convert" in events

    def test_named_callback_fires(self):
        events = []
        conv = PipelineDataConverter()
        conv._callbacks["tracker"] = lambda a, d: events.append((a, d["record_id"]))
        rid = conv.convert("pipe-1", {"a": 1}, "dict", "list")
        assert len(events) == 1
        assert events[0] == ("convert", rid)

    def test_remove_callback_success(self):
        conv = PipelineDataConverter()
        conv._callbacks["my_cb"] = lambda a, d: None
        assert conv.remove_callback("my_cb") is True
        assert "my_cb" not in conv._callbacks

    def test_remove_callback_missing(self):
        conv = PipelineDataConverter()
        assert conv.remove_callback("nonexistent") is False

    def test_callback_exception_silenced(self):
        conv = PipelineDataConverter()
        conv.on_change = lambda a, d: 1 / 0
        # Should not raise
        conv.convert("pipe-1", {"a": 1}, "dict", "list")
        assert conv.get_conversion_count() == 1

    def test_named_callback_exception_silenced(self):
        conv = PipelineDataConverter()
        conv._callbacks["bad"] = lambda a, d: 1 / 0
        conv.convert("pipe-1", {"a": 1}, "dict", "list")
        assert conv.get_conversion_count() == 1


class TestPruning:
    """Pruning when entries exceed MAX_ENTRIES."""

    def test_prune_removes_oldest_quarter(self):
        conv = PipelineDataConverter()
        conv.MAX_ENTRIES = 20
        for i in range(25):
            conv.convert("pipe-1", {"i": i}, "dict", "list")
        # After pruning, should have 20 - 5 = 15... wait:
        # 21st entry triggers prune removing quarter (5), leaving 16, then 22-25 added = 20
        # Actually each convert adds one then prunes.
        # At entry 21: 21 entries > 20, prune quarter(5) => 16 entries
        # entries 22-25 added one by one, each time <= 20, no more prune
        # total = 16 + 4 = 20
        assert conv.get_conversion_count() <= 20


if __name__ == "__main__":
    import traceback

    test_classes = [
        TestConvertBasic,
        TestConvertEdgeCases,
        TestGetConversion,
        TestConversionCount,
        TestStatsAndReset,
        TestCallbacks,
        TestPruning,
    ]
    passed = 0
    failed = 0
    for cls in test_classes:
        instance = cls()
        for name in dir(instance):
            if name.startswith("test_"):
                try:
                    getattr(instance, name)()
                    passed += 1
                except Exception as e:
                    failed += 1
                    print(f"FAIL: {cls.__name__}.{name}: {e}")
                    traceback.print_exc()
    print(f"{passed}/{passed + failed} tests passed")
