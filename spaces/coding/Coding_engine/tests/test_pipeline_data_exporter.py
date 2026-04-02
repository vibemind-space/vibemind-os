"""Tests for PipelineDataExporter service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_exporter import PipelineDataExporter


class TestExportBasic:
    """Basic export operations."""

    def test_export_returns_string_id(self):
        exporter = PipelineDataExporter()
        rid = exporter.export("pipe-1", {"key": "val"}, "s3-bucket")
        assert isinstance(rid, str)
        assert rid.startswith("pdex-")

    def test_export_ids_are_unique(self):
        exporter = PipelineDataExporter()
        ids = [exporter.export("pipe-1", {"i": i}, "dest") for i in range(10)]
        assert len(set(ids)) == 10

    def test_export_stores_pipeline_id(self):
        exporter = PipelineDataExporter()
        rid = exporter.export("pipe-x", {"a": 1}, "dest")
        rec = exporter.get_export(rid)
        assert rec["pipeline_id"] == "pipe-x"

    def test_export_stores_data(self):
        exporter = PipelineDataExporter()
        rid = exporter.export("pipe-1", {"nested": [1, 2, 3]}, "dest")
        rec = exporter.get_export(rid)
        assert rec["data"] == {"nested": [1, 2, 3]}

    def test_export_stores_destination(self):
        exporter = PipelineDataExporter()
        rid = exporter.export("pipe-1", {}, "s3-bucket-west")
        rec = exporter.get_export(rid)
        assert rec["destination"] == "s3-bucket-west"

    def test_export_default_format_json(self):
        exporter = PipelineDataExporter()
        rid = exporter.export("pipe-1", {}, "dest")
        rec = exporter.get_export(rid)
        assert rec["format"] == "json"

    def test_export_custom_format(self):
        exporter = PipelineDataExporter()
        rid = exporter.export("pipe-1", {}, "dest", format="csv")
        rec = exporter.get_export(rid)
        assert rec["format"] == "csv"

    def test_export_default_metadata_empty_dict(self):
        exporter = PipelineDataExporter()
        rid = exporter.export("pipe-1", {}, "dest")
        rec = exporter.get_export(rid)
        assert rec["metadata"] == {}

    def test_export_with_metadata(self):
        exporter = PipelineDataExporter()
        rid = exporter.export("pipe-1", {}, "dest", metadata={"author": "bot"})
        rec = exporter.get_export(rid)
        assert rec["metadata"]["author"] == "bot"


class TestGetExport:
    """get_export method."""

    def test_get_export_existing(self):
        exporter = PipelineDataExporter()
        rid = exporter.export("p1", {"v": 1}, "dest")
        result = exporter.get_export(rid)
        assert result is not None
        assert result["record_id"] == rid

    def test_get_export_missing_returns_none(self):
        exporter = PipelineDataExporter()
        assert exporter.get_export("pdex-nonexistent") is None

    def test_get_export_returns_copy(self):
        exporter = PipelineDataExporter()
        rid = exporter.export("p1", {"v": 1}, "dest")
        r1 = exporter.get_export(rid)
        r2 = exporter.get_export(rid)
        assert r1 is not r2
        assert r1 == r2


class TestGetExports:
    """get_exports method."""

    def test_get_exports_all(self):
        exporter = PipelineDataExporter()
        exporter.export("p1", {}, "d1")
        exporter.export("p2", {}, "d2")
        results = exporter.get_exports()
        assert len(results) == 2

    def test_get_exports_filtered_by_pipeline_id(self):
        exporter = PipelineDataExporter()
        exporter.export("p1", {}, "d1")
        exporter.export("p2", {}, "d2")
        exporter.export("p1", {}, "d3")
        results = exporter.get_exports(pipeline_id="p1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "p1" for r in results)

    def test_get_exports_filtered_by_destination(self):
        exporter = PipelineDataExporter()
        exporter.export("p1", {}, "s3")
        exporter.export("p1", {}, "gcs")
        exporter.export("p2", {}, "s3")
        results = exporter.get_exports(destination="s3")
        assert len(results) == 2
        assert all(r["destination"] == "s3" for r in results)

    def test_get_exports_filtered_by_both(self):
        exporter = PipelineDataExporter()
        exporter.export("p1", {}, "s3")
        exporter.export("p1", {}, "gcs")
        exporter.export("p2", {}, "s3")
        results = exporter.get_exports(pipeline_id="p1", destination="s3")
        assert len(results) == 1

    def test_get_exports_newest_first(self):
        exporter = PipelineDataExporter()
        exporter.export("p1", {"n": 1}, "d1")
        exporter.export("p1", {"n": 2}, "d2")
        exporter.export("p1", {"n": 3}, "d3")
        results = exporter.get_exports(pipeline_id="p1")
        assert results[0]["data"]["n"] == 3
        assert results[-1]["data"]["n"] == 1

    def test_get_exports_respects_limit(self):
        exporter = PipelineDataExporter()
        for i in range(10):
            exporter.export("p1", {"i": i}, "dest")
        results = exporter.get_exports(limit=3)
        assert len(results) == 3

    def test_get_exports_returns_copies(self):
        exporter = PipelineDataExporter()
        exporter.export("p1", {}, "dest")
        r1 = exporter.get_exports()
        r2 = exporter.get_exports()
        assert r1[0] is not r2[0]

    def test_get_exports_empty_pipeline_returns_all(self):
        exporter = PipelineDataExporter()
        exporter.export("p1", {}, "d1")
        exporter.export("p2", {}, "d2")
        results = exporter.get_exports(pipeline_id="")
        assert len(results) == 2


class TestGetExportCount:
    """get_export_count method."""

    def test_count_all(self):
        exporter = PipelineDataExporter()
        exporter.export("p1", {}, "d1")
        exporter.export("p2", {}, "d2")
        assert exporter.get_export_count() == 2

    def test_count_filtered(self):
        exporter = PipelineDataExporter()
        exporter.export("p1", {}, "d1")
        exporter.export("p2", {}, "d2")
        exporter.export("p1", {}, "d3")
        assert exporter.get_export_count(pipeline_id="p1") == 2

    def test_count_empty(self):
        exporter = PipelineDataExporter()
        assert exporter.get_export_count() == 0


class TestCallbacks:
    """Callback and on_change functionality."""

    def test_on_change_property_default_none(self):
        exporter = PipelineDataExporter()
        assert exporter.on_change is None

    def test_on_change_setter(self):
        exporter = PipelineDataExporter()
        fn = lambda action, data: None
        exporter.on_change = fn
        assert exporter.on_change is fn

    def test_on_change_fires_on_export(self):
        exporter = PipelineDataExporter()
        events = []
        exporter.on_change = lambda action, data: events.append(action)
        exporter.export("p1", {}, "dest")
        assert "export" in events

    def test_callback_fires_on_export(self):
        exporter = PipelineDataExporter()
        events = []
        exporter.register_callback("my_cb", lambda action, data: events.append(action))
        exporter.export("p1", {}, "dest")
        assert "export" in events

    def test_on_change_fires_before_callbacks(self):
        exporter = PipelineDataExporter()
        order = []
        exporter.on_change = lambda a, d: order.append("on_change")
        exporter.register_callback("cb", lambda a, d: order.append("cb"))
        exporter.export("p1", {}, "dest")
        assert order == ["on_change", "cb"]

    def test_callback_exception_silenced(self):
        exporter = PipelineDataExporter()
        exporter.register_callback("bad", lambda a, d: 1 / 0)
        exporter.export("p1", {}, "dest")  # should not raise

    def test_on_change_exception_silenced(self):
        exporter = PipelineDataExporter()
        exporter.on_change = lambda a, d: 1 / 0
        exporter.export("p1", {}, "dest")  # should not raise

    def test_remove_callback_existing(self):
        exporter = PipelineDataExporter()
        exporter.register_callback("cb1", lambda a, d: None)
        assert exporter.remove_callback("cb1") is True

    def test_remove_callback_missing(self):
        exporter = PipelineDataExporter()
        assert exporter.remove_callback("nope") is False

    def test_removed_callback_not_called(self):
        exporter = PipelineDataExporter()
        events = []
        exporter.register_callback("cb1", lambda a, d: events.append("cb1"))
        exporter.remove_callback("cb1")
        exporter.export("p1", {}, "dest")
        assert events == []


class TestPruning:
    """Pruning when entries exceed MAX_ENTRIES."""

    def test_prune_removes_oldest_quarter(self):
        exporter = PipelineDataExporter()
        exporter.MAX_ENTRIES = 20
        for i in range(25):
            exporter.export("p1", {"i": i}, "dest")
        assert len(exporter._state.entries) <= 20


class TestGetStats:
    """get_stats method."""

    def test_stats_empty(self):
        exporter = PipelineDataExporter()
        stats = exporter.get_stats()
        assert stats["total_exports"] == 0

    def test_stats_with_data(self):
        exporter = PipelineDataExporter()
        exporter.export("p1", {}, "s3")
        exporter.export("p2", {}, "gcs")
        exporter.export("p1", {}, "s3")
        stats = exporter.get_stats()
        assert stats["total_exports"] == 3
        assert stats["unique_pipelines"] == 2
        assert stats["unique_destinations"] == 2


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        exporter = PipelineDataExporter()
        exporter.export("p1", {}, "dest")
        exporter.reset()
        assert exporter.get_export_count() == 0

    def test_reset_clears_seq(self):
        exporter = PipelineDataExporter()
        exporter.export("p1", {}, "dest")
        exporter.reset()
        assert exporter._state._seq == 0

    def test_reset_clears_callbacks(self):
        exporter = PipelineDataExporter()
        exporter.register_callback("cb1", lambda a, d: None)
        exporter.reset()
        assert len(exporter._callbacks) == 0

    def test_reset_clears_on_change(self):
        exporter = PipelineDataExporter()
        exporter.on_change = lambda a, d: None
        exporter.reset()
        assert exporter.on_change is None
