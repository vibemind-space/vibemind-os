"""Test pipeline audit trail."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_audit_trail import PipelineAuditTrail


def test_record_entry():
    """Record and retrieve audit entry."""
    at = PipelineAuditTrail()
    eid = at.record("config_changed", actor="alice",
                    target="db_module", target_type="component",
                    details="Updated connection pool",
                    old_value="5", new_value="10",
                    source="api", severity="info",
                    tags=["config"], metadata={"key": "pool_size"})
    assert eid.startswith("aud-")

    e = at.get_entry(eid)
    assert e is not None
    assert e["action"] == "config_changed"
    assert e["actor"] == "alice"
    assert e["target"] == "db_module"
    assert e["target_type"] == "component"
    assert e["old_value"] == "5"
    assert e["new_value"] == "10"
    assert e["source"] == "api"
    assert e["severity"] == "info"

    assert at.remove_entry(eid) is True
    assert at.remove_entry(eid) is False
    print("OK: record entry")


def test_invalid_record():
    """Invalid record rejected."""
    at = PipelineAuditTrail()
    assert at.record("") == ""
    assert at.record("a", severity="invalid") == ""
    assert at.record("a", target_type="invalid") == ""
    assert at.record("a", source="invalid") == ""
    print("OK: invalid record")


def test_max_entries():
    """Max entries enforced."""
    at = PipelineAuditTrail(max_entries=3)
    at.record("a")
    at.record("b")
    at.record("c")
    assert at.record("d") == ""
    print("OK: max entries")


def test_search_by_action():
    """Search by action."""
    at = PipelineAuditTrail()
    at.record("deploy", actor="alice")
    at.record("config_change", actor="bob")
    at.record("deploy", actor="charlie")

    results = at.search(action="deploy")
    assert len(results) == 2
    print("OK: search by action")


def test_search_by_actor():
    """Search by actor."""
    at = PipelineAuditTrail()
    at.record("a", actor="alice")
    at.record("b", actor="alice")
    at.record("c", actor="bob")

    results = at.search(actor="alice")
    assert len(results) == 2
    print("OK: search by actor")


def test_search_by_target():
    """Search by target."""
    at = PipelineAuditTrail()
    at.record("a", target="db")
    at.record("b", target="auth")
    at.record("c", target="db")

    results = at.search(target="db")
    assert len(results) == 2
    print("OK: search by target")


def test_search_by_target_type():
    """Search by target type."""
    at = PipelineAuditTrail()
    at.record("a", target_type="component")
    at.record("b", target_type="agent")

    results = at.search(target_type="component")
    assert len(results) == 1
    print("OK: search by target type")


def test_search_by_source():
    """Search by source."""
    at = PipelineAuditTrail()
    at.record("a", source="api")
    at.record("b", source="ui")

    results = at.search(source="api")
    assert len(results) == 1
    print("OK: search by source")


def test_search_by_severity():
    """Search by severity."""
    at = PipelineAuditTrail()
    at.record("a", severity="info")
    at.record("b", severity="error")
    at.record("c", severity="error")

    results = at.search(severity="error")
    assert len(results) == 2
    print("OK: search by severity")


def test_search_by_tag():
    """Search by tag."""
    at = PipelineAuditTrail()
    at.record("a", tags=["deploy"])
    at.record("b", tags=["config"])

    results = at.search(tag="deploy")
    assert len(results) == 1
    print("OK: search by tag")


def test_search_limit():
    """Search respects limit."""
    at = PipelineAuditTrail()
    for i in range(20):
        at.record(f"action_{i}")

    results = at.search(limit=5)
    assert len(results) == 5
    print("OK: search limit")


def test_actor_history():
    """Get actor history."""
    at = PipelineAuditTrail()
    at.record("deploy", actor="alice")
    at.record("rollback", actor="alice")
    at.record("deploy", actor="bob")

    history = at.get_actor_history("alice")
    assert len(history) == 2
    print("OK: actor history")


def test_target_history():
    """Get target history."""
    at = PipelineAuditTrail()
    at.record("start", target="db")
    at.record("stop", target="db")
    at.record("start", target="auth")

    history = at.get_target_history("db")
    assert len(history) == 2
    print("OK: target history")


def test_severity_counts():
    """Get severity counts."""
    at = PipelineAuditTrail()
    at.record("a", severity="info")
    at.record("b", severity="info")
    at.record("c", severity="error")

    counts = at.get_severity_counts()
    assert counts["info"] == 2
    assert counts["error"] == 1
    assert counts["warning"] == 0
    print("OK: severity counts")


def test_action_counts():
    """Get action counts."""
    at = PipelineAuditTrail()
    at.record("deploy")
    at.record("deploy")
    at.record("deploy")
    at.record("rollback")

    counts = at.get_action_counts()
    assert len(counts) == 2
    assert counts[0]["action"] == "deploy"
    assert counts[0]["count"] == 3
    print("OK: action counts")


def test_active_actors():
    """Get active actors."""
    at = PipelineAuditTrail()
    at.record("a", actor="alice")
    at.record("b", actor="alice")
    at.record("c", actor="alice")
    at.record("d", actor="bob")

    actors = at.get_active_actors()
    assert len(actors) == 2
    assert actors[0]["actor"] == "alice"
    assert actors[0]["entry_count"] == 3
    print("OK: active actors")


def test_recent():
    """Get recent entries."""
    at = PipelineAuditTrail()
    at.record("first")
    at.record("second")
    at.record("third")

    recent = at.get_recent(limit=2)
    assert len(recent) == 2
    assert recent[0]["action"] == "third"
    assert recent[1]["action"] == "second"
    print("OK: recent")


def test_callback():
    """Callback fires on record."""
    at = PipelineAuditTrail()
    fired = []
    at.on_change("mon", lambda a, d: fired.append(a))

    at.record("deploy")
    assert "entry_recorded" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    at = PipelineAuditTrail()
    assert at.on_change("mon", lambda a, d: None) is True
    assert at.on_change("mon", lambda a, d: None) is False
    assert at.remove_callback("mon") is True
    assert at.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    at = PipelineAuditTrail()
    at.record("a")
    at.record("b")
    at.record("c")

    stats = at.get_stats()
    assert stats["total_entries_created"] == 3
    assert stats["current_entries"] == 3
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    at = PipelineAuditTrail()
    at.record("a")

    at.reset()
    assert at.search() == []
    stats = at.get_stats()
    assert stats["current_entries"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Audit Trail Tests ===\n")
    test_record_entry()
    test_invalid_record()
    test_max_entries()
    test_search_by_action()
    test_search_by_actor()
    test_search_by_target()
    test_search_by_target_type()
    test_search_by_source()
    test_search_by_severity()
    test_search_by_tag()
    test_search_limit()
    test_actor_history()
    test_target_history()
    test_severity_counts()
    test_action_counts()
    test_active_actors()
    test_recent()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
