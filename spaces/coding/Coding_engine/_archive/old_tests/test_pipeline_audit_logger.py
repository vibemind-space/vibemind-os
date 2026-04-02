"""Test pipeline audit logger -- unit tests."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_audit_logger import PipelineAuditLogger


def test_log():
    al = PipelineAuditLogger()
    eid = al.log("deploy", "admin", "api_server", details={"version": "v2.0"}, severity="info")
    assert len(eid) > 0
    e = al.get_entry(eid)
    assert e is not None
    assert e["action"] == "deploy"
    assert e["actor"] == "admin"
    print("OK: log")


def test_query():
    al = PipelineAuditLogger()
    al.log("deploy", "admin", "api", severity="info")
    al.log("restart", "admin", "db", severity="warning")
    al.log("deploy", "bot", "cache", severity="info")
    results = al.query(actor="admin")
    assert len(results) == 2
    results2 = al.query(action="deploy")
    assert len(results2) == 2
    results3 = al.query(severity="warning")
    assert len(results3) == 1
    print("OK: query")


def test_actor_history():
    al = PipelineAuditLogger()
    al.log("a1", "admin", "r1")
    al.log("a2", "admin", "r2")
    al.log("a3", "bot", "r3")
    history = al.get_actor_history("admin")
    assert len(history) == 2
    print("OK: actor history")


def test_resource_history():
    al = PipelineAuditLogger()
    al.log("deploy", "admin", "api")
    al.log("restart", "bot", "api")
    history = al.get_resource_history("api")
    assert len(history) == 2
    print("OK: resource history")


def test_summary():
    al = PipelineAuditLogger()
    al.log("deploy", "admin", "api", severity="info")
    al.log("error", "bot", "db", severity="error")
    summary = al.get_summary()
    assert summary["total_entries"] >= 2
    print("OK: summary")


def test_list_actors():
    al = PipelineAuditLogger()
    al.log("a", "admin", "r")
    al.log("a", "bot", "r")
    actors = al.list_actors()
    assert "admin" in actors
    assert "bot" in actors
    print("OK: list actors")


def test_list_actions():
    al = PipelineAuditLogger()
    al.log("deploy", "admin", "r")
    al.log("restart", "admin", "r")
    actions = al.list_actions()
    assert "deploy" in actions
    assert "restart" in actions
    print("OK: list actions")


def test_purge():
    al = PipelineAuditLogger()
    al.log("old", "admin", "r")
    cutoff = time.time() + 1
    count = al.purge_before(cutoff)
    assert count >= 1
    print("OK: purge")


def test_callbacks():
    al = PipelineAuditLogger()
    fired = []
    al.on_change("mon", lambda a, d: fired.append(a))
    al.log("deploy", "admin", "r")
    assert len(fired) >= 1
    assert al.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    al = PipelineAuditLogger()
    al.log("deploy", "admin", "r")
    stats = al.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    al = PipelineAuditLogger()
    al.log("deploy", "admin", "r")
    al.reset()
    assert al.list_actors() == []
    print("OK: reset")


def main():
    print("=== Pipeline Audit Logger Tests ===\n")
    test_log()
    test_query()
    test_actor_history()
    test_resource_history()
    test_summary()
    test_list_actors()
    test_list_actions()
    test_purge()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
