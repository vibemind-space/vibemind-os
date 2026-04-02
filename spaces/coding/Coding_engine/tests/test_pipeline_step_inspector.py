"""Tests for PipelineStepInspector service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_inspector import PipelineStepInspector


class TestInspectStep:
    def test_inspect_step_returns_id_with_prefix(self):
        svc = PipelineStepInspector()
        rid = svc.inspect_step("pipe-1", "step-a")
        assert rid.startswith("psin-")

    def test_inspect_step_stores_entry(self):
        svc = PipelineStepInspector()
        rid = svc.inspect_step("pipe-1", "step-a", status="ok")
        entry = svc.get_inspection(rid)
        assert entry is not None
        assert entry["pipeline_id"] == "pipe-1"
        assert entry["step_name"] == "step-a"
        assert entry["status"] == "ok"

    def test_inspect_step_with_input_output(self):
        svc = PipelineStepInspector()
        inp = {"key": "val"}
        out = {"result": 42}
        rid = svc.inspect_step("pipe-1", "step-a", input_data=inp, output_data=out)
        entry = svc.get_inspection(rid)
        assert entry["input_data"] == {"key": "val"}
        assert entry["output_data"] == {"result": 42}

    def test_inspect_step_deepcopies_input(self):
        svc = PipelineStepInspector()
        inp = {"key": [1, 2]}
        rid = svc.inspect_step("pipe-1", "step-a", input_data=inp)
        inp["key"].append(3)
        entry = svc.get_inspection(rid)
        assert entry["input_data"]["key"] == [1, 2]

    def test_inspect_step_records_duration(self):
        svc = PipelineStepInspector()
        rid = svc.inspect_step("pipe-1", "step-a", duration=1.5)
        entry = svc.get_inspection(rid)
        assert entry["duration"] == 1.5

    def test_inspect_step_default_status(self):
        svc = PipelineStepInspector()
        rid = svc.inspect_step("pipe-1", "step-a")
        entry = svc.get_inspection(rid)
        assert entry["status"] == "ok"

    def test_inspect_step_custom_status(self):
        svc = PipelineStepInspector()
        rid = svc.inspect_step("pipe-1", "step-a", status="error")
        entry = svc.get_inspection(rid)
        assert entry["status"] == "error"


class TestGetInspection:
    def test_get_inspection_not_found(self):
        svc = PipelineStepInspector()
        assert svc.get_inspection("psin-nonexistent") is None

    def test_get_inspection_returns_deepcopy(self):
        svc = PipelineStepInspector()
        rid = svc.inspect_step("pipe-1", "step-a", input_data={"x": 1})
        entry1 = svc.get_inspection(rid)
        entry2 = svc.get_inspection(rid)
        assert entry1 is not entry2
        entry1["input_data"]["x"] = 999
        entry2_check = svc.get_inspection(rid)
        assert entry2_check["input_data"]["x"] == 1


class TestGetInspections:
    def test_get_inspections_returns_all(self):
        svc = PipelineStepInspector()
        svc.inspect_step("pipe-1", "step-a")
        svc.inspect_step("pipe-1", "step-b")
        results = svc.get_inspections()
        assert len(results) == 2

    def test_get_inspections_filter_by_pipeline(self):
        svc = PipelineStepInspector()
        svc.inspect_step("pipe-1", "step-a")
        svc.inspect_step("pipe-2", "step-a")
        results = svc.get_inspections(pipeline_id="pipe-1")
        assert len(results) == 1
        assert results[0]["pipeline_id"] == "pipe-1"

    def test_get_inspections_filter_by_step_name(self):
        svc = PipelineStepInspector()
        svc.inspect_step("pipe-1", "step-a")
        svc.inspect_step("pipe-1", "step-b")
        results = svc.get_inspections(step_name="step-b")
        assert len(results) == 1
        assert results[0]["step_name"] == "step-b"

    def test_get_inspections_filter_by_status(self):
        svc = PipelineStepInspector()
        svc.inspect_step("pipe-1", "step-a", status="ok")
        svc.inspect_step("pipe-1", "step-b", status="error")
        results = svc.get_inspections(status="error")
        assert len(results) == 1
        assert results[0]["status"] == "error"

    def test_get_inspections_newest_first(self):
        svc = PipelineStepInspector()
        id1 = svc.inspect_step("pipe-1", "step-a")
        id2 = svc.inspect_step("pipe-1", "step-b")
        results = svc.get_inspections()
        assert results[0]["inspection_id"] == id2
        assert results[1]["inspection_id"] == id1

    def test_get_inspections_respects_limit(self):
        svc = PipelineStepInspector()
        for i in range(10):
            svc.inspect_step("pipe-1", f"step-{i}")
        results = svc.get_inspections(limit=3)
        assert len(results) == 3

    def test_get_inspections_combined_filters(self):
        svc = PipelineStepInspector()
        svc.inspect_step("pipe-1", "step-a", status="ok")
        svc.inspect_step("pipe-1", "step-a", status="error")
        svc.inspect_step("pipe-2", "step-a", status="ok")
        results = svc.get_inspections(pipeline_id="pipe-1", status="ok")
        assert len(results) == 1


class TestGetInspectionCount:
    def test_count_all(self):
        svc = PipelineStepInspector()
        svc.inspect_step("pipe-1", "step-a")
        svc.inspect_step("pipe-2", "step-b")
        assert svc.get_inspection_count() == 2

    def test_count_by_pipeline(self):
        svc = PipelineStepInspector()
        svc.inspect_step("pipe-1", "step-a")
        svc.inspect_step("pipe-1", "step-b")
        svc.inspect_step("pipe-2", "step-c")
        assert svc.get_inspection_count(pipeline_id="pipe-1") == 2

    def test_count_by_status(self):
        svc = PipelineStepInspector()
        svc.inspect_step("pipe-1", "step-a", status="ok")
        svc.inspect_step("pipe-1", "step-b", status="error")
        assert svc.get_inspection_count(status="error") == 1


class TestGetStats:
    def test_stats_empty(self):
        svc = PipelineStepInspector()
        stats = svc.get_stats()
        assert stats["total_inspections"] == 0
        assert stats["by_status"] == {}
        assert stats["avg_duration"] == 0.0
        assert stats["unique_pipelines"] == 0

    def test_stats_with_data(self):
        svc = PipelineStepInspector()
        svc.inspect_step("pipe-1", "step-a", duration=2.0, status="ok")
        svc.inspect_step("pipe-1", "step-b", duration=4.0, status="error")
        svc.inspect_step("pipe-2", "step-a", duration=3.0, status="ok")
        stats = svc.get_stats()
        assert stats["total_inspections"] == 3
        assert stats["by_status"]["ok"] == 2
        assert stats["by_status"]["error"] == 1
        assert abs(stats["avg_duration"] - 3.0) < 0.001
        assert stats["unique_pipelines"] == 2


class TestReset:
    def test_reset_clears_entries(self):
        svc = PipelineStepInspector()
        svc.inspect_step("pipe-1", "step-a")
        svc.reset()
        assert svc.get_inspection_count() == 0
        assert svc.get_inspections() == []

    def test_reset_clears_seq(self):
        svc = PipelineStepInspector()
        svc.inspect_step("pipe-1", "step-a")
        svc.reset()
        assert svc._state._seq == 0


class TestCallbacks:
    def test_on_change_property_set_callable(self):
        svc = PipelineStepInspector()
        events = []
        svc.on_change = lambda action, data: events.append((action, data))
        svc.inspect_step("pipe-1", "step-a")
        assert len(events) == 1
        assert events[0][0] == "inspection_created"

    def test_on_change_property_get(self):
        svc = PipelineStepInspector()
        cb = lambda action, data: None
        svc.on_change = cb
        assert "default" in svc.on_change
        assert svc.on_change["default"] is cb

    def test_remove_callback_existing(self):
        svc = PipelineStepInspector()
        svc.on_change = lambda action, data: None
        assert svc.remove_callback("default") is True
        assert "default" not in svc.on_change

    def test_remove_callback_nonexistent(self):
        svc = PipelineStepInspector()
        assert svc.remove_callback("nope") is False

    def test_fire_silences_exceptions(self):
        svc = PipelineStepInspector()

        def bad_cb(action, data):
            raise RuntimeError("boom")

        svc.on_change = bad_cb
        # Should not raise
        rid = svc.inspect_step("pipe-1", "step-a")
        assert rid.startswith("psin-")

    def test_callback_receives_deepcopy(self):
        svc = PipelineStepInspector()
        captured = []
        svc.on_change = lambda action, data: captured.append(data)
        rid = svc.inspect_step("pipe-1", "step-a", input_data={"x": 1})
        captured[0]["input_data"]["x"] = 999
        entry = svc.get_inspection(rid)
        assert entry["input_data"]["x"] == 1


class TestPrune:
    def test_prune_removes_oldest(self):
        svc = PipelineStepInspector()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(svc.inspect_step("pipe-1", f"step-{i}"))
        assert len(svc._state.entries) <= 5
        # oldest should be gone
        assert svc.get_inspection(ids[0]) is None
        # newest should remain
        assert svc.get_inspection(ids[-1]) is not None


class TestIdGeneration:
    def test_ids_are_unique(self):
        svc = PipelineStepInspector()
        ids = set()
        for i in range(100):
            rid = svc.inspect_step("pipe-1", f"step-{i}")
            ids.add(rid)
        assert len(ids) == 100
