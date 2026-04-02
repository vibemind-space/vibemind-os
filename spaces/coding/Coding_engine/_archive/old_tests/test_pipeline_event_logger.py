"""Test pipeline event logger -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_event_logger import PipelineEventLogger


def test_log_event():
    el = PipelineEventLogger()
    eid = el.log_event("deploy", "ci_server", data={"version": "1.0"}, severity="info")
    assert len(eid) > 0
    e = el.get_event(eid)
    assert e is not None
    assert e["event_type"] == "deploy"
    assert e["source"] == "ci_server"
    print("OK: log event")


def test_query_by_type():
    el = PipelineEventLogger()
    el.log_event("deploy", "ci", severity="info")
    el.log_event("build", "ci", severity="info")
    el.log_event("deploy", "cd", severity="warning")
    results = el.query(event_type="deploy")
    assert len(results) == 2
    print("OK: query by type")


def test_query_by_source():
    el = PipelineEventLogger()
    el.log_event("deploy", "ci", severity="info")
    el.log_event("build", "ci", severity="info")
    el.log_event("deploy", "cd", severity="warning")
    results = el.query(source="ci")
    assert len(results) == 2
    print("OK: query by source")


def test_query_by_severity():
    el = PipelineEventLogger()
    el.log_event("e1", "s1", severity="info")
    el.log_event("e2", "s1", severity="error")
    el.log_event("e3", "s1", severity="info")
    results = el.query(severity="error")
    assert len(results) == 1
    print("OK: query by severity")


def test_get_by_source():
    el = PipelineEventLogger()
    el.log_event("e1", "api", severity="info")
    el.log_event("e2", "api", severity="warning")
    el.log_event("e3", "db", severity="info")
    results = el.get_by_source("api")
    assert len(results) == 2
    print("OK: get by source")


def test_get_summary():
    el = PipelineEventLogger()
    el.log_event("deploy", "ci", severity="info")
    el.log_event("error", "ci", severity="error")
    el.log_event("deploy", "cd", severity="info")
    summary = el.get_summary()
    assert summary["total_events"] == 3
    assert "info" in summary["by_severity"]
    assert "error" in summary["by_severity"]
    print("OK: get summary")


def test_list_sources():
    el = PipelineEventLogger()
    el.log_event("e1", "api", severity="info")
    el.log_event("e2", "db", severity="info")
    sources = el.list_sources()
    assert "api" in sources
    assert "db" in sources
    print("OK: list sources")


def test_list_event_types():
    el = PipelineEventLogger()
    el.log_event("deploy", "ci", severity="info")
    el.log_event("build", "ci", severity="info")
    types = el.list_event_types()
    assert "deploy" in types
    assert "build" in types
    print("OK: list event types")


def test_purge():
    el = PipelineEventLogger()
    el.log_event("e1", "s1", severity="info")
    el.log_event("e2", "s1", severity="info")
    import time
    time.sleep(0.01)
    count = el.purge(before_timestamp=time.time() + 1)
    assert count >= 2
    print("OK: purge")


def test_callbacks():
    el = PipelineEventLogger()
    fired = []
    el.on_change("mon", lambda a, d: fired.append(a))
    el.log_event("e1", "s1", severity="info")
    assert len(fired) >= 1
    assert el.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    el = PipelineEventLogger()
    el.log_event("e1", "s1", severity="info")
    stats = el.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    el = PipelineEventLogger()
    el.log_event("e1", "s1", severity="info")
    el.reset()
    assert el.list_sources() == []
    print("OK: reset")


def main():
    print("=== Pipeline Event Logger Tests ===\n")
    test_log_event()
    test_query_by_type()
    test_query_by_source()
    test_query_by_severity()
    test_get_by_source()
    test_get_summary()
    test_list_sources()
    test_list_event_types()
    test_purge()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
