"""Test pipeline execution history -- unit tests."""
import sys, time
sys.path.insert(0, ".")

from src.services.pipeline_execution_history import PipelineExecutionHistory


def test_record_execution():
    h = PipelineExecutionHistory()
    eid = h.record_execution("deploy", "success", 1500.0, result={"deployed": True})
    assert len(eid) > 0
    assert eid.startswith("peh-")
    e = h.get_execution(eid)
    assert e is not None
    assert e["pipeline_name"] == "deploy"
    assert e["status"] == "success"
    print("OK: record execution")


def test_get_pipeline_history():
    h = PipelineExecutionHistory()
    h.record_execution("deploy", "success", 1000.0)
    h.record_execution("deploy", "failed", 500.0)
    h.record_execution("test", "success", 200.0)
    hist = h.get_pipeline_history("deploy")
    assert len(hist) == 2
    print("OK: get pipeline history")


def test_get_latest_execution():
    h = PipelineExecutionHistory()
    h.record_execution("deploy", "success", 1000.0)
    h.record_execution("deploy", "failed", 2000.0)
    latest = h.get_latest_execution("deploy")
    assert latest is not None
    assert latest["status"] == "failed"
    assert h.get_latest_execution("nonexistent") is None
    print("OK: get latest execution")


def test_get_success_rate():
    h = PipelineExecutionHistory()
    h.record_execution("deploy", "success", 1000.0)
    h.record_execution("deploy", "success", 1000.0)
    h.record_execution("deploy", "failed", 500.0)
    rate = h.get_success_rate("deploy")
    assert abs(rate - 2/3) < 0.01
    assert h.get_success_rate("nonexistent") == 0.0
    print("OK: get success rate")


def test_get_average_duration():
    h = PipelineExecutionHistory()
    h.record_execution("deploy", "success", 1000.0)
    h.record_execution("deploy", "success", 2000.0)
    h.record_execution("deploy", "success", 3000.0)
    avg = h.get_average_duration("deploy")
    assert avg == 2000.0
    assert h.get_average_duration("nonexistent") == 0.0
    print("OK: get average duration")


def test_get_execution_count():
    h = PipelineExecutionHistory()
    h.record_execution("deploy", "success", 1000.0)
    h.record_execution("deploy", "success", 1000.0)
    h.record_execution("test", "success", 500.0)
    assert h.get_execution_count() == 3
    assert h.get_execution_count("deploy") == 2
    print("OK: get execution count")


def test_list_pipelines():
    h = PipelineExecutionHistory()
    h.record_execution("deploy", "success", 1000.0)
    h.record_execution("test", "success", 500.0)
    pipes = h.list_pipelines()
    assert "deploy" in pipes
    assert "test" in pipes
    print("OK: list pipelines")


def test_purge():
    h = PipelineExecutionHistory()
    h.record_execution("deploy", "success", 1000.0)
    time.sleep(0.01)
    count = h.purge(before_timestamp=time.time() + 1)
    assert count >= 1
    print("OK: purge")


def test_callbacks():
    h = PipelineExecutionHistory()
    fired = []
    h.on_change("mon", lambda a, d: fired.append(a))
    h.record_execution("deploy", "success", 1000.0)
    assert len(fired) >= 1
    assert h.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    h = PipelineExecutionHistory()
    h.record_execution("deploy", "success", 1000.0)
    stats = h.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    h = PipelineExecutionHistory()
    h.record_execution("deploy", "success", 1000.0)
    h.reset()
    assert h.get_execution_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Execution History Tests ===\n")
    test_record_execution()
    test_get_pipeline_history()
    test_get_latest_execution()
    test_get_success_rate()
    test_get_average_duration()
    test_get_execution_count()
    test_list_pipelines()
    test_purge()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
