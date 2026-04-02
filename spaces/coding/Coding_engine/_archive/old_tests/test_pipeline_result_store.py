"""Test pipeline result store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_result_store import PipelineResultStore


def test_store_result():
    rs = PipelineResultStore()
    rid = rs.store_result("pipeline-1", "extract", {"rows": 100})
    assert len(rid) > 0
    assert rid.startswith("prs-")
    print("OK: store result")


def test_get_result():
    rs = PipelineResultStore()
    rid = rs.store_result("pipeline-1", "extract", {"rows": 100})
    result = rs.get_result(rid)
    assert result is not None
    assert result["result_data"]["rows"] == 100
    assert rs.get_result("nonexistent") is None
    print("OK: get result")


def test_get_results():
    rs = PipelineResultStore()
    rs.store_result("pipeline-1", "extract", {"rows": 100})
    rs.store_result("pipeline-1", "transform", {"rows": 95})
    results = rs.get_results("pipeline-1")
    assert len(results) == 2
    print("OK: get results")


def test_get_results_filtered():
    rs = PipelineResultStore()
    rs.store_result("pipeline-1", "extract", {"rows": 100})
    rs.store_result("pipeline-1", "transform", {"rows": 95})
    results = rs.get_results("pipeline-1", step_name="extract")
    assert len(results) == 1
    print("OK: get results filtered")


def test_get_latest_result():
    rs = PipelineResultStore()
    rs.store_result("pipeline-1", "extract", {"rows": 100})
    rs.store_result("pipeline-1", "transform", {"rows": 95})
    latest = rs.get_latest_result("pipeline-1")
    assert latest is not None
    assert latest["step_name"] == "transform"
    print("OK: get latest result")


def test_list_pipelines():
    rs = PipelineResultStore()
    rs.store_result("pipeline-1", "extract", {})
    rs.store_result("pipeline-2", "load", {})
    pipelines = rs.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    rs = PipelineResultStore()
    fired = []
    rs.on_change("mon", lambda a, d: fired.append(a))
    rs.store_result("pipeline-1", "extract", {})
    assert len(fired) >= 1
    assert rs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rs = PipelineResultStore()
    rs.store_result("pipeline-1", "extract", {})
    stats = rs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rs = PipelineResultStore()
    rs.store_result("pipeline-1", "extract", {})
    rs.reset()
    assert rs.get_result_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Result Store Tests ===\n")
    test_store_result()
    test_get_result()
    test_get_results()
    test_get_results_filtered()
    test_get_latest_result()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
