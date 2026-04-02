"""Test pipeline execution record -- unit tests."""
import sys
sys.path.insert(0, ".")
import time

from src.services.pipeline_execution_record import PipelineExecutionRecord


def test_start_execution():
    er = PipelineExecutionRecord()
    eid = er.start_execution("deploy", context={"version": "1.0"}, tags=["prod"])
    assert len(eid) > 0
    e = er.get_execution(eid)
    assert e is not None
    assert e["pipeline_name"] == "deploy"
    print("OK: start execution")


def test_complete_execution():
    er = PipelineExecutionRecord()
    eid = er.start_execution("deploy")
    assert er.complete_execution(eid, result={"status": "ok"}) is True
    e = er.get_execution(eid)
    assert e["status"] in ("completed", "success", "succeeded", "done")
    print("OK: complete execution")


def test_fail_execution():
    er = PipelineExecutionRecord()
    eid = er.start_execution("deploy")
    assert er.fail_execution(eid, error="timeout") is True
    e = er.get_execution(eid)
    assert e["status"] in ("failed", "error")
    print("OK: fail execution")


def test_get_history():
    er = PipelineExecutionRecord()
    er.start_execution("deploy")
    eid2 = er.start_execution("deploy")
    er.complete_execution(eid2)
    history = er.get_history("deploy")
    assert len(history) >= 2
    print("OK: get history")


def test_get_summary():
    er = PipelineExecutionRecord()
    eid1 = er.start_execution("deploy")
    er.complete_execution(eid1)
    eid2 = er.start_execution("deploy")
    er.fail_execution(eid2, error="oops")
    summary = er.get_summary("deploy")
    assert summary["total"] >= 2
    assert summary["succeeded"] >= 1
    assert summary["failed"] >= 1
    print("OK: get summary")


def test_get_recent():
    er = PipelineExecutionRecord()
    er.start_execution("deploy")
    er.start_execution("build")
    recent = er.get_recent(limit=10)
    assert len(recent) >= 2
    print("OK: get recent")


def test_list_pipelines():
    er = PipelineExecutionRecord()
    er.start_execution("deploy")
    er.start_execution("build")
    pipelines = er.list_pipelines()
    assert "deploy" in pipelines
    assert "build" in pipelines
    print("OK: list pipelines")


def test_purge():
    er = PipelineExecutionRecord()
    eid = er.start_execution("old_deploy")
    er.complete_execution(eid, result={"ok": True})
    time.sleep(0.01)
    count = er.purge(before_timestamp=time.time() + 1)
    assert count >= 1
    print("OK: purge")


def test_callbacks():
    er = PipelineExecutionRecord()
    fired = []
    er.on_change("mon", lambda a, d: fired.append(a))
    er.start_execution("deploy")
    assert len(fired) >= 1
    assert er.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    er = PipelineExecutionRecord()
    er.start_execution("deploy")
    stats = er.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    er = PipelineExecutionRecord()
    er.start_execution("deploy")
    er.reset()
    assert er.list_pipelines() == []
    print("OK: reset")


def main():
    print("=== Pipeline Execution Record Tests ===\n")
    test_start_execution()
    test_complete_execution()
    test_fail_execution()
    test_get_history()
    test_get_summary()
    test_get_recent()
    test_list_pipelines()
    test_purge()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
