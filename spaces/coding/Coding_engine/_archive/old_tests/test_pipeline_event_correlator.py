"""Test pipeline event correlator."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_event_correlator import PipelineEventCorrelator


def test_ingest_event():
    """Ingest and retrieve event."""
    ec = PipelineEventCorrelator()
    eid = ec.ingest_event("agent-1", "task_started", severity="info",
                          message="Starting build", tags=["ci"])
    assert eid.startswith("evt-")

    e = ec.get_event(eid)
    assert e is not None
    assert e["source"] == "agent-1"
    assert e["event_type"] == "task_started"
    assert e["severity"] == "info"
    assert "ci" in e["tags"]
    print("OK: ingest event")


def test_invalid_event():
    """Invalid event rejected."""
    ec = PipelineEventCorrelator()
    assert ec.ingest_event("", "type") == ""
    assert ec.ingest_event("src", "") == ""
    assert ec.ingest_event("src", "type", severity="invalid") == ""
    print("OK: invalid event")


def test_add_rule():
    """Add and remove rule."""
    ec = PipelineEventCorrelator()
    rid = ec.add_rule("error_burst", "severity", "error",
                      window_seconds=30.0, min_events=3)
    assert rid.startswith("rule-")

    r = ec.get_rule(rid)
    assert r is not None
    assert r["name"] == "error_burst"
    assert r["match_field"] == "severity"
    assert r["match_value"] == "error"
    assert r["enabled"] is True

    assert ec.remove_rule(rid) is True
    assert ec.remove_rule(rid) is False
    print("OK: add rule")


def test_invalid_rule():
    """Invalid rule rejected."""
    ec = PipelineEventCorrelator()
    assert ec.add_rule("", "source", "x") == ""
    assert ec.add_rule("r", "invalid_field", "x") == ""
    assert ec.add_rule("r", "source", "") == ""
    assert ec.add_rule("r", "source", "x", window_seconds=0) == ""
    assert ec.add_rule("r", "source", "x", min_events=0) == ""
    print("OK: invalid rule")


def test_max_rules():
    """Max rules enforced."""
    ec = PipelineEventCorrelator(max_rules=2)
    ec.add_rule("a", "source", "x")
    ec.add_rule("b", "source", "y")
    assert ec.add_rule("c", "source", "z") == ""
    print("OK: max rules")


def test_enable_disable_rule():
    """Enable and disable rule."""
    ec = PipelineEventCorrelator()
    rid = ec.add_rule("test", "source", "x")

    assert ec.disable_rule(rid) is True
    assert ec.get_rule(rid)["enabled"] is False
    assert ec.disable_rule(rid) is False

    assert ec.enable_rule(rid) is True
    assert ec.get_rule(rid)["enabled"] is True
    assert ec.enable_rule(rid) is False
    print("OK: enable disable rule")


def test_list_rules():
    """List rules with filter."""
    ec = PipelineEventCorrelator()
    r1 = ec.add_rule("a", "source", "x")
    r2 = ec.add_rule("b", "source", "y")
    ec.disable_rule(r2)

    all_r = ec.list_rules()
    assert len(all_r) == 2

    enabled = ec.list_rules(enabled_only=True)
    assert len(enabled) == 1
    print("OK: list rules")


def test_auto_correlation():
    """Rule triggers automatic correlation."""
    ec = PipelineEventCorrelator()
    ec.add_rule("error_burst", "severity", "error",
                window_seconds=60.0, min_events=3)

    # Ingest 3 error events to trigger rule
    ec.ingest_event("a", "fail", severity="error")
    ec.ingest_event("b", "fail", severity="error")
    ec.ingest_event("c", "fail", severity="error")

    corrs = ec.list_correlations()
    assert len(corrs) >= 1
    assert corrs[0]["name"].startswith("Auto:")
    print("OK: auto correlation")


def test_auto_correlation_below_threshold():
    """Rule doesn't trigger below min_events."""
    ec = PipelineEventCorrelator()
    ec.add_rule("error_burst", "severity", "error",
                window_seconds=60.0, min_events=5)

    # Only 2 errors, need 5
    ec.ingest_event("a", "fail", severity="error")
    ec.ingest_event("b", "fail", severity="error")

    corrs = ec.list_correlations()
    assert len(corrs) == 0
    print("OK: auto correlation below threshold")


def test_disabled_rule_skipped():
    """Disabled rule doesn't trigger."""
    ec = PipelineEventCorrelator()
    rid = ec.add_rule("err", "severity", "error",
                      window_seconds=60.0, min_events=2)
    ec.disable_rule(rid)

    ec.ingest_event("a", "fail", severity="error")
    ec.ingest_event("b", "fail", severity="error")

    corrs = ec.list_correlations()
    assert len(corrs) == 0
    print("OK: disabled rule skipped")


def test_manual_correlation():
    """Create manual correlation."""
    ec = PipelineEventCorrelator()
    e1 = ec.ingest_event("a", "start")
    e2 = ec.ingest_event("a", "end")

    cid = ec.create_correlation("deploy_cycle", event_ids=[e1, e2],
                                 tags=["deploy"])
    assert cid.startswith("corr-")

    c = ec.get_correlation(cid)
    assert c is not None
    assert c["name"] == "deploy_cycle"
    assert c["event_count"] == 2
    assert c["status"] == "open"
    assert "deploy" in c["tags"]

    # Events should be linked
    assert ec.get_event(e1)["correlation_id"] == cid
    print("OK: manual correlation")


def test_add_event_to_correlation():
    """Add event to existing correlation."""
    ec = PipelineEventCorrelator()
    e1 = ec.ingest_event("a", "x")
    e2 = ec.ingest_event("b", "y")

    cid = ec.create_correlation("group", event_ids=[e1])

    assert ec.add_event_to_correlation(cid, e2) is True
    assert ec.get_correlation(cid)["event_count"] == 2

    # Duplicate
    assert ec.add_event_to_correlation(cid, e2) is False
    # Nonexistent event
    assert ec.add_event_to_correlation(cid, "fake") is False
    print("OK: add event to correlation")


def test_close_correlation():
    """Close a correlation."""
    ec = PipelineEventCorrelator()
    cid = ec.create_correlation("test")

    assert ec.close_correlation(cid) is True
    assert ec.get_correlation(cid)["status"] == "closed"
    assert ec.close_correlation(cid) is False
    print("OK: close correlation")


def test_correlation_events():
    """Get events in correlation."""
    ec = PipelineEventCorrelator()
    e1 = ec.ingest_event("a", "first")
    e2 = ec.ingest_event("b", "second")

    cid = ec.create_correlation("group", event_ids=[e1, e2])
    events = ec.get_correlation_events(cid)
    assert len(events) == 2
    # Should be sorted by timestamp
    assert events[0]["timestamp"] <= events[1]["timestamp"]
    print("OK: correlation events")


def test_search_events():
    """Search events with filters."""
    ec = PipelineEventCorrelator()
    ec.ingest_event("agent-1", "build", severity="info", tags=["ci"])
    ec.ingest_event("agent-2", "test", severity="error")
    ec.ingest_event("agent-1", "deploy", severity="warning")

    by_source = ec.search_events(source="agent-1")
    assert len(by_source) == 2

    by_type = ec.search_events(event_type="test")
    assert len(by_type) == 1

    by_sev = ec.search_events(severity="error")
    assert len(by_sev) == 1

    by_tag = ec.search_events(tag="ci")
    assert len(by_tag) == 1
    print("OK: search events")


def test_search_limit():
    """Search respects limit."""
    ec = PipelineEventCorrelator()
    for i in range(20):
        ec.ingest_event("src", f"type-{i}")

    results = ec.search_events(limit=5)
    assert len(results) == 5
    print("OK: search limit")


def test_event_sources():
    """Get event source counts."""
    ec = PipelineEventCorrelator()
    ec.ingest_event("agent-1", "a")
    ec.ingest_event("agent-1", "b")
    ec.ingest_event("agent-2", "c")

    sources = ec.get_event_sources()
    assert sources["agent-1"] == 2
    assert sources["agent-2"] == 1
    print("OK: event sources")


def test_severity_counts():
    """Get severity counts."""
    ec = PipelineEventCorrelator()
    ec.ingest_event("a", "x", severity="info")
    ec.ingest_event("b", "y", severity="error")
    ec.ingest_event("c", "z", severity="error")

    counts = ec.get_severity_counts()
    assert counts["info"] == 1
    assert counts["error"] == 2
    assert counts["warning"] == 0
    print("OK: severity counts")


def test_list_correlations():
    """List correlations with filters."""
    ec = PipelineEventCorrelator()
    c1 = ec.create_correlation("open_one", tags=["ci"])
    c2 = ec.create_correlation("closed_one")
    ec.close_correlation(c2)

    all_c = ec.list_correlations()
    assert len(all_c) == 2

    by_status = ec.list_correlations(status="open")
    assert len(by_status) == 1

    by_tag = ec.list_correlations(tag="ci")
    assert len(by_tag) == 1
    print("OK: list correlations")


def test_recent_correlations():
    """Get recent correlations."""
    ec = PipelineEventCorrelator()
    ec.create_correlation("first")
    ec.create_correlation("second")
    ec.create_correlation("third")

    recent = ec.get_recent_correlations(limit=2)
    assert len(recent) == 2
    print("OK: recent correlations")


def test_rule_triggered_callback():
    """Callback fires on rule trigger."""
    ec = PipelineEventCorrelator()
    fired = []
    ec.on_change("mon", lambda a, d: fired.append(a))

    ec.add_rule("burst", "source", "agent-1",
                window_seconds=60.0, min_events=2)
    ec.ingest_event("agent-1", "a")
    ec.ingest_event("agent-1", "b")

    assert "rule_triggered" in fired
    print("OK: rule triggered callback")


def test_event_ingested_callback():
    """Callback fires on event ingest."""
    ec = PipelineEventCorrelator()
    fired = []
    ec.on_change("mon", lambda a, d: fired.append(a))

    ec.ingest_event("src", "type")
    assert "event_ingested" in fired
    print("OK: event ingested callback")


def test_callbacks():
    """Callback registration."""
    ec = PipelineEventCorrelator()
    assert ec.on_change("mon", lambda a, d: None) is True
    assert ec.on_change("mon", lambda a, d: None) is False
    assert ec.remove_callback("mon") is True
    assert ec.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ec = PipelineEventCorrelator()
    ec.add_rule("burst", "source", "x", window_seconds=60.0, min_events=2)

    ec.ingest_event("x", "a")
    ec.ingest_event("x", "b")
    ec.create_correlation("manual")
    ec.close_correlation(ec.list_correlations(status="open")[-1]["correlation_id"])

    stats = ec.get_stats()
    assert stats["total_events_ingested"] == 2
    assert stats["total_correlations_created"] >= 2  # 1 auto + 1 manual
    assert stats["total_correlations_closed"] >= 1
    assert stats["total_rules_triggered"] >= 1
    assert stats["current_events"] == 2
    assert stats["current_rules"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ec = PipelineEventCorrelator()
    ec.ingest_event("src", "type")
    ec.add_rule("r", "source", "x")
    ec.create_correlation("c")

    ec.reset()
    assert ec.search_events() == []
    assert ec.list_rules() == []
    assert ec.list_correlations() == []
    stats = ec.get_stats()
    assert stats["current_events"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Event Correlator Tests ===\n")
    test_ingest_event()
    test_invalid_event()
    test_add_rule()
    test_invalid_rule()
    test_max_rules()
    test_enable_disable_rule()
    test_list_rules()
    test_auto_correlation()
    test_auto_correlation_below_threshold()
    test_disabled_rule_skipped()
    test_manual_correlation()
    test_add_event_to_correlation()
    test_close_correlation()
    test_correlation_events()
    test_search_events()
    test_search_limit()
    test_event_sources()
    test_severity_counts()
    test_list_correlations()
    test_recent_correlations()
    test_rule_triggered_callback()
    test_event_ingested_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 25 TESTS PASSED ===")


if __name__ == "__main__":
    main()
