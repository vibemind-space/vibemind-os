"""Tests for PipelineStepBenchmarker service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_benchmarker import PipelineStepBenchmarker

class TestIdGeneration:
    def test_prefix(self):
        s = PipelineStepBenchmarker()
        assert s.benchmark("p1", "step1", 42.5).startswith("psbm-")
    def test_unique(self):
        s = PipelineStepBenchmarker()
        ids = {s.benchmark("p1", f"s{i}", float(i)) for i in range(20)}
        assert len(ids) == 20

class TestBenchmarkBasic:
    def test_returns_id(self):
        s = PipelineStepBenchmarker()
        assert len(s.benchmark("p1", "step1", 10.0)) > 0
    def test_stores_fields(self):
        s = PipelineStepBenchmarker()
        rid = s.benchmark("p1", "step1", 42.5)
        e = s.get_benchmark(rid)
        assert e["pipeline_id"] == "p1"
        assert e["step_name"] == "step1"
        assert e["duration_ms"] == 42.5
    def test_with_metadata(self):
        s = PipelineStepBenchmarker()
        rid = s.benchmark("p1", "step1", 10.0, metadata={"x": 1})
        assert s.get_benchmark(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = PipelineStepBenchmarker()
        m = {"a": [1]}
        rid = s.benchmark("p1", "step1", 10.0, metadata=m)
        m["a"].append(2)
        assert s.get_benchmark(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = PipelineStepBenchmarker()
        before = time.time()
        rid = s.benchmark("p1", "step1", 10.0)
        assert s.get_benchmark(rid)["created_at"] >= before
    def test_empty_pipeline_returns_empty(self):
        assert PipelineStepBenchmarker().benchmark("", "step1", 10.0) == ""
    def test_empty_step_returns_empty(self):
        assert PipelineStepBenchmarker().benchmark("p1", "", 10.0) == ""

class TestGetBenchmark:
    def test_found(self):
        s = PipelineStepBenchmarker()
        rid = s.benchmark("p1", "step1", 10.0)
        assert s.get_benchmark(rid) is not None
    def test_not_found(self):
        assert PipelineStepBenchmarker().get_benchmark("xxx") is None
    def test_returns_copy(self):
        s = PipelineStepBenchmarker()
        rid = s.benchmark("p1", "step1", 10.0)
        assert s.get_benchmark(rid) is not s.get_benchmark(rid)

class TestGetBenchmarks:
    def test_all(self):
        s = PipelineStepBenchmarker()
        s.benchmark("p1", "s1", 10.0); s.benchmark("p2", "s2", 20.0)
        assert len(s.get_benchmarks()) == 2
    def test_filter(self):
        s = PipelineStepBenchmarker()
        s.benchmark("p1", "s1", 10.0); s.benchmark("p2", "s2", 20.0)
        assert len(s.get_benchmarks(pipeline_id="p1")) == 1
    def test_newest_first(self):
        s = PipelineStepBenchmarker()
        s.benchmark("p1", "s1", 10.0); s.benchmark("p1", "s2", 20.0)
        assert s.get_benchmarks(pipeline_id="p1")[0]["step_name"] == "s2"
    def test_limit(self):
        s = PipelineStepBenchmarker()
        for i in range(10): s.benchmark("p1", f"s{i}", float(i))
        assert len(s.get_benchmarks(limit=3)) == 3

class TestGetBenchmarkCount:
    def test_total(self):
        s = PipelineStepBenchmarker()
        s.benchmark("p1", "s1", 10.0); s.benchmark("p2", "s2", 20.0)
        assert s.get_benchmark_count() == 2
    def test_filtered(self):
        s = PipelineStepBenchmarker()
        s.benchmark("p1", "s1", 10.0); s.benchmark("p2", "s2", 20.0)
        assert s.get_benchmark_count(pipeline_id="p1") == 1
    def test_empty(self):
        assert PipelineStepBenchmarker().get_benchmark_count() == 0

class TestGetStats:
    def test_empty(self):
        assert PipelineStepBenchmarker().get_stats()["total_benchmarks"] == 0
    def test_with_data(self):
        s = PipelineStepBenchmarker()
        s.benchmark("p1", "s1", 10.0); s.benchmark("p2", "s2", 20.0)
        st = s.get_stats()
        assert st["total_benchmarks"] == 2
        assert st["unique_pipelines"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepBenchmarker()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.benchmark("p1", "s1", 10.0)
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = PipelineStepBenchmarker()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert PipelineStepBenchmarker().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = PipelineStepBenchmarker()
        s.MAX_ENTRIES = 5
        for i in range(8): s.benchmark("p1", f"s{i}", float(i))
        assert s.get_benchmark_count() < 8

class TestReset:
    def test_clears(self):
        s = PipelineStepBenchmarker()
        s.benchmark("p1", "s1", 10.0); s.reset()
        assert s.get_benchmark_count() == 0
    def test_clears_callbacks(self):
        s = PipelineStepBenchmarker()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = PipelineStepBenchmarker()
        s.benchmark("p1", "s1", 10.0); s.reset()
        assert s._state._seq == 0
