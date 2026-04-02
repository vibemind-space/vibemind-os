"""Test event correlation engine."""
import sys
import time
sys.path.insert(0, ".")

from src.services.event_correlation import (
    EventCorrelationEngine,
    CorrelationStatus,
    RulePriority,
)


def test_register_rule():
    """Register a correlation rule."""
    engine = EventCorrelationEngine()
    ok = engine.register_rule("build_fail_chain", {"build_failed", "test_failed"})
    assert ok is True
    assert engine.register_rule("build_fail_chain", {"x"}) is False  # Duplicate

    rule = engine.get_rule("build_fail_chain")
    assert rule is not None
    assert rule["name"] == "build_fail_chain"
    assert set(rule["event_types"]) == {"build_failed", "test_failed"}
    print("OK: register rule")


def test_unregister_rule():
    """Unregister a rule."""
    engine = EventCorrelationEngine()
    engine.register_rule("temp", {"x"})
    assert engine.unregister_rule("temp") is True
    assert engine.get_rule("temp") is None
    assert engine.unregister_rule("temp") is False
    print("OK: unregister rule")


def test_list_rules():
    """List all rules."""
    engine = EventCorrelationEngine()
    engine.register_rule("a_rule", {"x"})
    engine.register_rule("b_rule", {"y"})
    rules = engine.list_rules()
    assert len(rules) == 2
    assert rules[0]["name"] == "a_rule"
    print("OK: list rules")


def test_ingest_no_match():
    """Ingest event with no matching rule."""
    engine = EventCorrelationEngine()
    groups = engine.ingest("unknown_event", source="test")
    assert groups == []
    print("OK: ingest no match")


def test_ingest_creates_group():
    """Ingest matching events creates a correlated group."""
    engine = EventCorrelationEngine()
    engine.register_rule("fail_pair", {"build_failed", "test_failed"}, min_events=2, time_window=5.0)

    g1 = engine.ingest("build_failed", source="Builder")
    # Only 1 event, need 2 → no group yet
    assert g1 == []

    g2 = engine.ingest("test_failed", source="Tester")
    assert len(g2) == 1

    group = engine.get_group(g2[0])
    assert group is not None
    assert group["rule_name"] == "fail_pair"
    assert group["event_count"] == 2
    assert group["status"] == "open"
    print("OK: ingest creates group")


def test_ingest_adds_to_existing_group():
    """Additional matching events join the existing group."""
    engine = EventCorrelationEngine()
    engine.register_rule("multi", {"error"}, min_events=2, time_window=5.0)

    engine.ingest("error", source="A")
    gids = engine.ingest("error", source="B")
    assert len(gids) == 1

    # Third event should join existing group
    gids2 = engine.ingest("error", source="C")
    assert gids2 == gids  # Same group

    group = engine.get_group(gids[0])
    assert group["event_count"] == 3
    print("OK: ingest adds to existing group")


def test_close_group():
    """Close a correlated group."""
    engine = EventCorrelationEngine()
    engine.register_rule("r", {"x"}, min_events=2)
    engine.ingest("x")
    gids = engine.ingest("x")
    gid = gids[0]

    assert engine.close_group(gid) is True
    assert engine.close_group(gid) is False  # Already closed

    # Should be in archive
    archived = engine.get_archived_groups()
    assert len(archived) == 1
    assert archived[0]["group_id"] == gid
    print("OK: close group")


def test_escalate_group():
    """Escalate a group."""
    engine = EventCorrelationEngine()
    engine.register_rule("r", {"x"}, min_events=2)
    engine.ingest("x")
    gids = engine.ingest("x")
    gid = gids[0]

    assert engine.escalate_group(gid) is True
    group = engine.get_group(gid)
    assert group["status"] == "escalated"

    # Can't escalate again (not open)
    assert engine.escalate_group(gid) is False
    print("OK: escalate group")


def test_set_root_cause():
    """Set root cause on a group."""
    engine = EventCorrelationEngine()
    engine.register_rule("r", {"x"}, min_events=2)
    engine.ingest("x")
    gids = engine.ingest("x")
    gid = gids[0]

    cause = {"type": "build_failed", "description": "Missing dependency"}
    assert engine.set_root_cause(gid, cause) is True

    group = engine.get_group(gid)
    assert group["root_cause"] == cause
    print("OK: set root cause")


def test_set_root_cause_archived():
    """Set root cause on an archived group."""
    engine = EventCorrelationEngine()
    engine.register_rule("r", {"x"}, min_events=2)
    engine.ingest("x")
    gids = engine.ingest("x")
    gid = gids[0]
    engine.close_group(gid)

    cause = {"type": "oom"}
    assert engine.set_root_cause(gid, cause) is True

    group = engine.get_group(gid)
    assert group["root_cause"] == cause
    print("OK: set root cause archived")


def test_get_open_groups():
    """Get open groups with filters."""
    engine = EventCorrelationEngine()
    engine.register_rule("high", {"error"}, min_events=2, priority=RulePriority.HIGH)
    engine.register_rule("low", {"warn"}, min_events=2, priority=RulePriority.LOW)

    engine.ingest("error")
    engine.ingest("error")
    engine.ingest("warn")
    engine.ingest("warn")

    all_open = engine.get_open_groups()
    assert len(all_open) == 2
    # Sorted by priority descending
    assert all_open[0]["priority"] >= all_open[1]["priority"]

    high_only = engine.get_open_groups(min_priority=RulePriority.HIGH)
    assert len(high_only) == 1
    assert high_only[0]["rule_name"] == "high"

    by_rule = engine.get_open_groups(rule_name="low")
    assert len(by_rule) == 1
    print("OK: get open groups")


def test_define_cascade():
    """Define and trace cascade chains."""
    engine = EventCorrelationEngine()
    engine.define_cascade("db_down", "api_error")
    engine.define_cascade("api_error", "build_failed")
    engine.define_cascade("build_failed", "test_failed")

    chain = engine.get_cascade_chain("db_down")
    assert chain == ["db_down", "api_error", "build_failed", "test_failed"]

    roots = engine.get_cascade_roots("test_failed")
    assert roots == ["db_down", "api_error", "build_failed", "test_failed"]
    print("OK: define cascade")


def test_cascade_roots_no_edges():
    """Cascade roots with no edges returns just the event type."""
    engine = EventCorrelationEngine()
    roots = engine.get_cascade_roots("standalone")
    assert roots == ["standalone"]
    print("OK: cascade roots no edges")


def test_analyze_root_cause():
    """Analyze root cause candidates for a group."""
    engine = EventCorrelationEngine()
    engine.define_cascade("db_down", "api_error")
    engine.define_cascade("api_error", "build_failed")

    engine.register_rule("failures", {"db_down", "api_error", "build_failed"}, min_events=2, time_window=10.0)

    engine.ingest("db_down", source="DB")
    gids = engine.ingest("api_error", source="API")
    engine.ingest("build_failed", source="Builder")

    gid = gids[0]
    analysis = engine.analyze_root_cause(gid)
    assert analysis is not None
    assert len(analysis["candidates"]) >= 2
    # First candidate should have highest score
    assert analysis["candidates"][0]["score"] >= analysis["candidates"][-1]["score"]
    print("OK: analyze root cause")


def test_event_frequency():
    """Track event frequency."""
    engine = EventCorrelationEngine()
    for _ in range(5):
        engine.ingest("error", source="A")

    freq = engine.get_event_frequency("error", window=10.0)
    assert freq["count"] == 5
    assert freq["rate_per_second"] > 0
    print("OK: event frequency")


def test_detect_frequency_anomalies():
    """Detect abnormally high frequency events."""
    engine = EventCorrelationEngine()

    # Normal events: 2 each
    engine.ingest("info", source="A")
    engine.ingest("info", source="A")
    engine.ingest("debug", source="A")
    engine.ingest("debug", source="A")

    # Spike: 10 errors
    for _ in range(10):
        engine.ingest("error", source="B")

    anomalies = engine.detect_frequency_anomalies(window=10.0, threshold_multiplier=2.0)
    assert len(anomalies) >= 1
    assert anomalies[0]["event_type"] == "error"
    print("OK: detect frequency anomalies")


def test_condition_guard():
    """Rule with condition guard."""
    engine = EventCorrelationEngine()

    def same_source(events):
        sources = {e["source"] for e in events}
        return len(sources) == 1

    engine.register_rule("same_src", {"error"}, min_events=2, condition=same_source)

    # Different sources → no group
    engine.ingest("error", source="A")
    gids = engine.ingest("error", source="B")
    assert gids == []

    # Same source → group
    engine2 = EventCorrelationEngine()
    engine2.register_rule("same_src", {"error"}, min_events=2, condition=same_source)
    engine2.ingest("error", source="A")
    gids2 = engine2.ingest("error", source="A")
    assert len(gids2) == 1
    print("OK: condition guard")


def test_time_window():
    """Events outside time window don't correlate."""
    engine = EventCorrelationEngine()
    engine.register_rule("quick", {"x"}, min_events=2, time_window=0.1)

    engine.ingest("x")
    time.sleep(0.15)
    gids = engine.ingest("x")
    assert gids == []  # Too far apart
    print("OK: time window")


def test_cleanup_frequency():
    """Cleanup old frequency data."""
    engine = EventCorrelationEngine()
    # Add some events
    old_ts = time.time() - 7200  # 2 hours ago
    engine._frequency["old_type"] = [old_ts, old_ts + 1]
    engine.ingest("recent", source="A")

    removed = engine.cleanup_frequency(max_age=3600.0)
    assert removed == 2
    assert "old_type" not in engine._frequency
    print("OK: cleanup frequency")


def test_stats():
    """Stats are accurate."""
    engine = EventCorrelationEngine()
    engine.register_rule("r", {"x"}, min_events=2)
    engine.ingest("x")
    engine.ingest("x")

    stats = engine.get_stats()
    assert stats["total_events"] == 2
    assert stats["total_rules"] == 1
    assert stats["total_groups_created"] == 1
    assert stats["open_groups"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    engine = EventCorrelationEngine()
    engine.register_rule("r", {"x"}, min_events=2)
    engine.ingest("x")
    engine.ingest("x")

    engine.reset()
    assert engine.list_rules() == []
    assert engine.get_open_groups() == []
    stats = engine.get_stats()
    assert stats["total_events"] == 0
    assert stats["open_groups"] == 0
    print("OK: reset")


def test_max_events_pruning():
    """Event buffer is pruned when over limit."""
    engine = EventCorrelationEngine(max_events=10)
    for i in range(20):
        engine.ingest("evt", source=f"src-{i}")

    stats = engine.get_stats()
    assert stats["buffer_size"] <= 10
    assert stats["total_pruned"] >= 10
    print("OK: max events pruning")


def main():
    print("=== Event Correlation Engine Tests ===\n")
    test_register_rule()
    test_unregister_rule()
    test_list_rules()
    test_ingest_no_match()
    test_ingest_creates_group()
    test_ingest_adds_to_existing_group()
    test_close_group()
    test_escalate_group()
    test_set_root_cause()
    test_set_root_cause_archived()
    test_get_open_groups()
    test_define_cascade()
    test_cascade_roots_no_edges()
    test_analyze_root_cause()
    test_event_frequency()
    test_detect_frequency_anomalies()
    test_condition_guard()
    test_time_window()
    test_cleanup_frequency()
    test_stats()
    test_reset()
    test_max_events_pruning()
    print("\n=== ALL 22 TESTS PASSED ===")


if __name__ == "__main__":
    main()
