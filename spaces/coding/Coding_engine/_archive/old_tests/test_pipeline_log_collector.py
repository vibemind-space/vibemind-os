"""Test pipeline log collector -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_log_collector import PipelineLogCollector


def test_log():
    lc = PipelineLogCollector()
    lid = lc.log("pipeline-1", "info", "Step started", step_name="extract")
    assert len(lid) > 0
    assert lid.startswith("plc-")
    print("OK: log")


def test_get_logs():
    lc = PipelineLogCollector()
    lc.log("pipeline-1", "info", "started")
    lc.log("pipeline-1", "debug", "processing")
    lc.log("pipeline-1", "error", "failed")
    logs = lc.get_logs("pipeline-1")
    assert len(logs) == 3
    print("OK: get logs")


def test_get_logs_filtered_level():
    lc = PipelineLogCollector()
    lc.log("pipeline-1", "info", "msg1")
    lc.log("pipeline-1", "error", "msg2")
    logs = lc.get_logs("pipeline-1", level="error")
    assert len(logs) == 1
    print("OK: get logs filtered level")


def test_get_logs_filtered_step():
    lc = PipelineLogCollector()
    lc.log("pipeline-1", "info", "msg1", step_name="extract")
    lc.log("pipeline-1", "info", "msg2", step_name="transform")
    logs = lc.get_logs("pipeline-1", step_name="extract")
    assert len(logs) == 1
    print("OK: get logs filtered step")


def test_get_latest_log():
    lc = PipelineLogCollector()
    lc.log("pipeline-1", "info", "first")
    lc.log("pipeline-1", "warning", "second")
    latest = lc.get_latest_log("pipeline-1")
    assert latest is not None
    assert latest["message"] == "second"
    print("OK: get latest log")


def test_clear_logs():
    lc = PipelineLogCollector()
    lc.log("pipeline-1", "info", "msg1")
    lc.log("pipeline-1", "info", "msg2")
    count = lc.clear_logs("pipeline-1")
    assert count == 2
    assert lc.get_log_count("pipeline-1") == 0
    print("OK: clear logs")


def test_list_pipelines():
    lc = PipelineLogCollector()
    lc.log("pipeline-1", "info", "msg")
    lc.log("pipeline-2", "info", "msg")
    pipelines = lc.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    lc = PipelineLogCollector()
    fired = []
    lc.on_change("mon", lambda a, d: fired.append(a))
    lc.log("pipeline-1", "info", "msg")
    assert len(fired) >= 1
    assert lc.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    lc = PipelineLogCollector()
    lc.log("pipeline-1", "info", "msg")
    stats = lc.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    lc = PipelineLogCollector()
    lc.log("pipeline-1", "info", "msg")
    lc.reset()
    assert lc.get_total_logs() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Log Collector Tests ===\n")
    test_log()
    test_get_logs()
    test_get_logs_filtered_level()
    test_get_logs_filtered_step()
    test_get_latest_log()
    test_clear_logs()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
