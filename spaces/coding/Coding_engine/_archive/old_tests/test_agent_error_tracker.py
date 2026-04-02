"""Test agent error tracker."""
import sys
sys.path.insert(0, ".")

from src.services.agent_error_tracker import AgentErrorTracker


def test_log_error():
    """Log and retrieve error."""
    et = AgentErrorTracker()
    eid = et.log_error("agent-1", "RuntimeError", "null pointer",
                       severity="error", source="build",
                       stack_trace="line 42", context={"module": "auth"},
                       tags=["critical"])
    assert eid.startswith("err-")

    e = et.get_error(eid)
    assert e is not None
    assert e["agent"] == "agent-1"
    assert e["error_type"] == "RuntimeError"
    assert e["message"] == "null pointer"
    assert e["severity"] == "error"
    assert e["source"] == "build"
    assert e["status"] == "open"

    assert et.remove_error(eid) is True
    assert et.remove_error(eid) is False
    print("OK: log error")


def test_invalid_error():
    """Invalid error rejected."""
    et = AgentErrorTracker()
    assert et.log_error("", "t", "m") == ""
    assert et.log_error("a", "", "m") == ""
    assert et.log_error("a", "t", "") == ""
    assert et.log_error("a", "t", "m", severity="invalid") == ""
    print("OK: invalid error")


def test_acknowledge_error():
    """Acknowledge an error."""
    et = AgentErrorTracker()
    eid = et.log_error("a", "t", "m")

    assert et.acknowledge_error(eid) is True
    assert et.get_error(eid)["status"] == "acknowledged"
    assert et.acknowledge_error(eid) is False  # not open
    print("OK: acknowledge error")


def test_resolve_error():
    """Resolve an error."""
    et = AgentErrorTracker()
    eid = et.log_error("a", "t", "m")

    assert et.resolve_error(eid, resolution="fixed null check") is True
    assert et.get_error(eid)["status"] == "resolved"
    assert et.get_error(eid)["resolution"] == "fixed null check"
    assert et.resolve_error(eid) is False
    print("OK: resolve error")


def test_resolve_acknowledged():
    """Can resolve acknowledged error."""
    et = AgentErrorTracker()
    eid = et.log_error("a", "t", "m")
    et.acknowledge_error(eid)

    assert et.resolve_error(eid) is True
    assert et.get_error(eid)["status"] == "resolved"
    print("OK: resolve acknowledged")


def test_ignore_error():
    """Ignore an error."""
    et = AgentErrorTracker()
    eid = et.log_error("a", "t", "m")

    assert et.ignore_error(eid) is True
    assert et.get_error(eid)["status"] == "ignored"
    assert et.ignore_error(eid) is False
    print("OK: ignore error")


def test_create_pattern():
    """Create and manage pattern."""
    et = AgentErrorTracker()
    pid = et.create_pattern("timeout_errors", error_type="TimeoutError",
                            message_pattern="timed out",
                            tags=["network"])
    assert pid.startswith("epat-")

    p = et.get_pattern(pid)
    assert p is not None
    assert p["name"] == "timeout_errors"
    assert p["error_type"] == "TimeoutError"
    assert p["occurrence_count"] == 0
    assert p["status"] == "active"

    assert et.remove_pattern(pid) is True
    assert et.remove_pattern(pid) is False
    print("OK: create pattern")


def test_invalid_pattern():
    """Invalid pattern rejected."""
    et = AgentErrorTracker()
    assert et.create_pattern("") == ""
    assert et.create_pattern("x", severity="invalid") == ""
    print("OK: invalid pattern")


def test_max_patterns():
    """Max patterns enforced."""
    et = AgentErrorTracker(max_patterns=2)
    et.create_pattern("a")
    et.create_pattern("b")
    assert et.create_pattern("c") == ""
    print("OK: max patterns")


def test_pattern_auto_match():
    """Pattern auto-matches logged errors."""
    et = AgentErrorTracker()
    pid = et.create_pattern("timeout", error_type="TimeoutError",
                            message_pattern="timed out")

    et.log_error("a", "TimeoutError", "request timed out")
    et.log_error("a", "TimeoutError", "connection timed out")
    et.log_error("a", "ValueError", "invalid input")  # no match

    p = et.get_pattern(pid)
    assert p["occurrence_count"] == 2
    print("OK: pattern auto match")


def test_suppress_activate_pattern():
    """Suppress and activate pattern."""
    et = AgentErrorTracker()
    pid = et.create_pattern("test")

    assert et.suppress_pattern(pid) is True
    assert et.get_pattern(pid)["status"] == "suppressed"
    assert et.suppress_pattern(pid) is False

    # Suppressed pattern doesn't match
    et.log_error("a", "t", "m")
    assert et.get_pattern(pid)["occurrence_count"] == 0

    assert et.activate_pattern(pid) is True
    assert et.get_pattern(pid)["status"] == "active"
    assert et.activate_pattern(pid) is False
    print("OK: suppress activate pattern")


def test_search_errors():
    """Search errors with filters."""
    et = AgentErrorTracker()
    et.log_error("alice", "RuntimeError", "null", severity="error",
                 source="build", tags=["ci"])
    et.log_error("bob", "TimeoutError", "slow", severity="warning",
                 source="test")
    e3 = et.log_error("alice", "ValueError", "bad", severity="error")
    et.resolve_error(e3)

    by_agent = et.search_errors(agent="alice")
    assert len(by_agent) == 2

    by_type = et.search_errors(error_type="TimeoutError")
    assert len(by_type) == 1

    by_sev = et.search_errors(severity="error")
    assert len(by_sev) == 2

    by_status = et.search_errors(status="resolved")
    assert len(by_status) == 1

    by_source = et.search_errors(source="build")
    assert len(by_source) == 1

    by_tag = et.search_errors(tag="ci")
    assert len(by_tag) == 1
    print("OK: search errors")


def test_search_limit():
    """Search respects limit."""
    et = AgentErrorTracker()
    for i in range(20):
        et.log_error("a", "t", f"m{i}")

    results = et.search_errors(limit=5)
    assert len(results) == 5
    print("OK: search limit")


def test_agent_error_summary():
    """Get agent error summary."""
    et = AgentErrorTracker()
    et.log_error("alice", "RuntimeError", "null", severity="error")
    et.log_error("alice", "RuntimeError", "null2", severity="error")
    e3 = et.log_error("alice", "TimeoutError", "slow", severity="warning")
    et.resolve_error(e3)

    summary = et.get_agent_error_summary("alice")
    assert summary["total_errors"] == 3
    assert summary["by_severity"]["error"] == 2
    assert summary["by_severity"]["warning"] == 1
    assert summary["by_status"]["open"] == 2
    assert summary["by_status"]["resolved"] == 1
    assert summary["by_type"]["RuntimeError"] == 2
    assert summary["by_type"]["TimeoutError"] == 1
    print("OK: agent error summary")


def test_error_rate():
    """Get error rate."""
    et = AgentErrorTracker()
    e1 = et.log_error("a", "t", "m1")
    e2 = et.log_error("a", "t", "m2")
    et.resolve_error(e1)

    rate = et.get_error_rate()
    assert rate["total"] == 2
    assert rate["open"] == 1
    assert rate["resolved"] == 1
    assert rate["resolution_rate"] == 50.0
    print("OK: error rate")


def test_error_rate_by_agent():
    """Error rate filtered by agent."""
    et = AgentErrorTracker()
    e1 = et.log_error("alice", "t", "m")
    et.resolve_error(e1)
    et.log_error("bob", "t", "m")

    rate = et.get_error_rate(agent="alice")
    assert rate["total"] == 1
    assert rate["resolution_rate"] == 100.0
    print("OK: error rate by agent")


def test_severity_counts():
    """Get severity counts."""
    et = AgentErrorTracker()
    et.log_error("a", "t", "m", severity="error")
    et.log_error("a", "t", "m", severity="error")
    et.log_error("a", "t", "m", severity="critical")

    counts = et.get_severity_counts()
    assert counts["error"] == 2
    assert counts["critical"] == 1
    assert counts["warning"] == 0
    print("OK: severity counts")


def test_top_error_types():
    """Get top error types."""
    et = AgentErrorTracker()
    et.log_error("a", "RuntimeError", "m")
    et.log_error("a", "RuntimeError", "m")
    et.log_error("a", "RuntimeError", "m")
    et.log_error("a", "TimeoutError", "m")

    tops = et.get_top_error_types()
    assert len(tops) == 2
    assert tops[0]["error_type"] == "RuntimeError"
    assert tops[0]["count"] == 3
    print("OK: top error types")


def test_error_prone_agents():
    """Get error-prone agents."""
    et = AgentErrorTracker()
    et.log_error("alice", "t", "m")
    et.log_error("alice", "t", "m")
    et.log_error("alice", "t", "m")
    et.log_error("bob", "t", "m")

    agents = et.get_error_prone_agents()
    assert len(agents) == 2
    assert agents[0]["agent"] == "alice"
    assert agents[0]["error_count"] == 3
    print("OK: error prone agents")


def test_list_patterns():
    """List patterns with filters."""
    et = AgentErrorTracker()
    et.create_pattern("a", tags=["net"])
    p2 = et.create_pattern("b")
    et.suppress_pattern(p2)

    all_p = et.list_patterns()
    assert len(all_p) == 2

    active = et.list_patterns(status="active")
    assert len(active) == 1

    by_tag = et.list_patterns(tag="net")
    assert len(by_tag) == 1
    print("OK: list patterns")


def test_error_callback():
    """Callback fires on error log."""
    et = AgentErrorTracker()
    fired = []
    et.on_change("mon", lambda a, d: fired.append(a))

    et.log_error("a", "t", "m")
    assert "error_logged" in fired
    print("OK: error callback")


def test_callbacks():
    """Callback registration."""
    et = AgentErrorTracker()
    assert et.on_change("mon", lambda a, d: None) is True
    assert et.on_change("mon", lambda a, d: None) is False
    assert et.remove_callback("mon") is True
    assert et.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    et = AgentErrorTracker()
    e1 = et.log_error("a", "t", "m")
    e2 = et.log_error("a", "t", "m")
    e3 = et.log_error("a", "t", "m")
    et.acknowledge_error(e1)
    et.resolve_error(e2)
    et.ignore_error(e3)
    et.create_pattern("p")

    stats = et.get_stats()
    assert stats["total_errors_logged"] == 3
    assert stats["total_acknowledged"] == 1
    assert stats["total_resolved"] == 1
    assert stats["total_ignored"] == 1
    assert stats["total_patterns_created"] == 1
    assert stats["current_errors"] == 3
    assert stats["open_errors"] == 0
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    et = AgentErrorTracker()
    et.log_error("a", "t", "m")
    et.create_pattern("p")

    et.reset()
    assert et.search_errors() == []
    assert et.list_patterns() == []
    stats = et.get_stats()
    assert stats["current_errors"] == 0
    print("OK: reset")


def main():
    print("=== Agent Error Tracker Tests ===\n")
    test_log_error()
    test_invalid_error()
    test_acknowledge_error()
    test_resolve_error()
    test_resolve_acknowledged()
    test_ignore_error()
    test_create_pattern()
    test_invalid_pattern()
    test_max_patterns()
    test_pattern_auto_match()
    test_suppress_activate_pattern()
    test_search_errors()
    test_search_limit()
    test_agent_error_summary()
    test_error_rate()
    test_error_rate_by_agent()
    test_severity_counts()
    test_top_error_types()
    test_error_prone_agents()
    test_list_patterns()
    test_error_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 24 TESTS PASSED ===")


if __name__ == "__main__":
    main()
