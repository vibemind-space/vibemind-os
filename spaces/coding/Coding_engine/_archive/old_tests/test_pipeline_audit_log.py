"""Test pipeline audit log."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_audit_log import PipelineAuditLog


def test_log_basic():
    """Log a basic entry."""
    audit = PipelineAuditLog()
    eid = audit.log("deploy", actor="Builder", resource="app.py",
                     details={"version": "1.0"})
    assert eid.startswith("audit-")

    entry = audit.get_entry(eid)
    assert entry is not None
    assert entry["action"] == "deploy"
    assert entry["actor"] == "Builder"
    assert entry["resource"] == "app.py"
    assert entry["outcome"] == "success"
    assert entry["category"] == "action"
    print("OK: log basic")


def test_log_action():
    """Convenience log_action."""
    audit = PipelineAuditLog()
    eid = audit.log_action("build", "Builder", resource="project",
                            details={"time": 12.5})
    entry = audit.get_entry(eid)
    assert entry["category"] == "action"
    assert entry["outcome"] == "success"
    print("OK: log action")


def test_log_security():
    """Convenience log_security."""
    audit = PipelineAuditLog()
    eid = audit.log_security("auth_attempt", "Unknown", outcome="denied")
    entry = audit.get_entry(eid)
    assert entry["category"] == "security"
    assert entry["outcome"] == "denied"
    assert entry["severity"] == "warning"
    print("OK: log security")


def test_log_error():
    """Convenience log_error."""
    audit = PipelineAuditLog()
    eid = audit.log_error("crash", actor="Tester", details={"error": "OOM"})
    entry = audit.get_entry(eid)
    assert entry["category"] == "error"
    assert entry["outcome"] == "failure"
    print("OK: log error")


def test_search_by_category():
    """Search by category."""
    audit = PipelineAuditLog()
    audit.log_action("build", "Builder")
    audit.log_security("auth", "Admin")
    audit.log_error("crash", "System")

    actions = audit.search(category="action")
    assert len(actions) == 1
    security = audit.search(category="security")
    assert len(security) == 1
    print("OK: search by category")


def test_search_by_actor():
    """Search by actor."""
    audit = PipelineAuditLog()
    audit.log_action("build", "Builder")
    audit.log_action("test", "Tester")
    audit.log_action("deploy", "Builder")

    builder = audit.search(actor="Builder")
    assert len(builder) == 2
    print("OK: search by actor")


def test_search_by_resource():
    """Search by resource."""
    audit = PipelineAuditLog()
    audit.log_action("edit", "A", resource="app.py")
    audit.log_action("edit", "B", resource="test.py")

    app = audit.search(resource="app.py")
    assert len(app) == 1
    print("OK: search by resource")


def test_search_by_action():
    """Search by action substring."""
    audit = PipelineAuditLog()
    audit.log_action("deploy_staging", "A")
    audit.log_action("deploy_prod", "B")
    audit.log_action("build", "C")

    deploys = audit.search(action="deploy")
    assert len(deploys) == 2
    print("OK: search by action")


def test_search_by_outcome():
    """Search by outcome."""
    audit = PipelineAuditLog()
    audit.log("a", outcome="success")
    audit.log("b", outcome="failure")
    audit.log("c", outcome="denied")

    failures = audit.search(outcome="failure")
    assert len(failures) == 1
    denied = audit.search(outcome="denied")
    assert len(denied) == 1
    print("OK: search by outcome")


def test_search_by_tags():
    """Search by tags."""
    audit = PipelineAuditLog()
    audit.log("a", tags={"deploy", "prod"})
    audit.log("b", tags={"deploy", "staging"})
    audit.log("c", tags={"test"})

    deploy = audit.search(tags={"deploy"})
    assert len(deploy) == 2
    prod = audit.search(tags={"deploy", "prod"})
    assert len(prod) == 1
    print("OK: search by tags")


def test_search_by_time():
    """Search by time range."""
    audit = PipelineAuditLog()
    now = time.time()
    audit.log("old", timestamp=now - 100)
    audit.log("mid", timestamp=now - 50)
    audit.log("new", timestamp=now)

    recent = audit.search(since=now - 60)
    assert len(recent) == 2

    old = audit.search(until=now - 60)
    assert len(old) == 1
    print("OK: search by time")


def test_search_limit():
    """Search respects limit."""
    audit = PipelineAuditLog()
    for i in range(10):
        audit.log(f"action-{i}")

    limited = audit.search(limit=3)
    assert len(limited) == 3
    print("OK: search limit")


def test_get_entry_not_found():
    """Get nonexistent entry."""
    audit = PipelineAuditLog()
    assert audit.get_entry("fake") is None
    print("OK: get entry not found")


def test_actor_activity():
    """Get actor activity."""
    audit = PipelineAuditLog()
    audit.log_action("build", "Builder")
    audit.log_action("test", "Tester")
    audit.log_action("deploy", "Builder")

    activity = audit.get_actor_activity("Builder")
    assert len(activity) == 2
    print("OK: actor activity")


def test_resource_history():
    """Get resource history."""
    audit = PipelineAuditLog()
    audit.log_action("create", "A", resource="app.py")
    audit.log_action("edit", "B", resource="app.py")

    history = audit.get_resource_history("app.py")
    assert len(history) == 2
    print("OK: resource history")


def test_get_recent():
    """Get most recent entries."""
    audit = PipelineAuditLog()
    for i in range(5):
        audit.log(f"action-{i}")

    recent = audit.get_recent(limit=3)
    assert len(recent) == 3
    assert recent[0]["action"] == "action-4"  # Most recent first
    print("OK: get recent")


def test_actor_summary():
    """Actor summary."""
    audit = PipelineAuditLog()
    audit.log("a", actor="Builder", outcome="success")
    audit.log("b", actor="Builder", outcome="success")
    audit.log("c", actor="Builder", outcome="failure")
    audit.log("d", actor="Tester", outcome="success")

    summary = audit.get_actor_summary()
    assert len(summary) == 2
    builder = summary[0]  # Most active
    assert builder["actor"] == "Builder"
    assert builder["actions"] == 3
    assert builder["successes"] == 2
    assert builder["failures"] == 1
    print("OK: actor summary")


def test_category_counts():
    """Category counts."""
    audit = PipelineAuditLog()
    audit.log_action("a", "A")
    audit.log_action("b", "B")
    audit.log_security("c", "C")
    audit.log_error("d")

    counts = audit.get_category_counts()
    assert counts["action"] == 2
    assert counts["security"] == 1
    assert counts["error"] == 1
    print("OK: category counts")


def test_timeline():
    """Timeline buckets."""
    audit = PipelineAuditLog()
    now = time.time()
    audit.log("a", timestamp=now - 100)
    audit.log("b", timestamp=now - 50)
    audit.log("c", timestamp=now - 10)

    timeline = audit.get_timeline(bucket_seconds=3600.0, num_buckets=1)
    assert len(timeline) == 1
    assert timeline[0]["count"] == 3
    print("OK: timeline")


def test_export():
    """Export entries."""
    audit = PipelineAuditLog()
    audit.log_action("a", "A")
    audit.log_security("b", "B")
    audit.log_error("c")

    all_export = audit.export()
    assert len(all_export) == 3

    actions_only = audit.export(category="action")
    assert len(actions_only) == 1
    print("OK: export")


def test_prune_by_count():
    """Prune when over max entries."""
    audit = PipelineAuditLog(max_entries=5)
    for i in range(10):
        audit.log(f"action-{i}")

    assert len(audit._entries) <= 5
    print("OK: prune by count")


def test_invalid_category():
    """Invalid category falls back to action."""
    audit = PipelineAuditLog()
    eid = audit.log("test", category="invalid_cat")
    entry = audit.get_entry(eid)
    assert entry["category"] == "action"
    print("OK: invalid category")


def test_stats():
    """Stats are accurate."""
    audit = PipelineAuditLog()
    audit.log_action("a", "A")
    audit.log_security("b", "B", outcome="denied")
    audit.log_error("c")

    stats = audit.get_stats()
    assert stats["total_logged"] == 3
    assert stats["total_actions"] == 1
    assert stats["total_security"] == 1
    assert stats["total_errors"] == 1
    assert stats["total_denied"] == 1
    assert stats["total_entries"] == 3
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    audit = PipelineAuditLog()
    audit.log_action("a", "A")

    audit.reset()
    assert audit.search() == []
    stats = audit.get_stats()
    assert stats["total_entries"] == 0
    assert stats["total_logged"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Audit Log Tests ===\n")
    test_log_basic()
    test_log_action()
    test_log_security()
    test_log_error()
    test_search_by_category()
    test_search_by_actor()
    test_search_by_resource()
    test_search_by_action()
    test_search_by_outcome()
    test_search_by_tags()
    test_search_by_time()
    test_search_limit()
    test_get_entry_not_found()
    test_actor_activity()
    test_resource_history()
    test_get_recent()
    test_actor_summary()
    test_category_counts()
    test_timeline()
    test_export()
    test_prune_by_count()
    test_invalid_category()
    test_stats()
    test_reset()
    print("\n=== ALL 24 TESTS PASSED ===")


if __name__ == "__main__":
    main()
