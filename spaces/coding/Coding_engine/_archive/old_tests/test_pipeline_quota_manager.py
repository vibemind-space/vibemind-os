"""Test pipeline quota manager."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_quota_manager import PipelineQuotaManager


def test_create_quota():
    """Create and remove quotas."""
    qm = PipelineQuotaManager()
    qid = qm.create_quota("api_limit", "api_calls", 1000, "agent-1")
    assert qid.startswith("quota-")

    q = qm.get_quota(qid)
    assert q is not None
    assert q["name"] == "api_limit"
    assert q["resource_type"] == "api_calls"
    assert q["limit"] == 1000
    assert q["current_usage"] == 0.0
    assert q["remaining"] == 1000

    assert qm.remove_quota(qid) is True
    assert qm.remove_quota(qid) is False
    print("OK: create quota")


def test_invalid_quota():
    """Invalid quota params rejected."""
    qm = PipelineQuotaManager()
    assert qm.create_quota("", "cpu", 100, "a") == ""
    assert qm.create_quota("x", "invalid", 100, "a") == ""
    assert qm.create_quota("x", "cpu", 0, "a") == ""
    assert qm.create_quota("x", "cpu", 100, "a", owner_type="invalid") == ""
    print("OK: invalid quota")


def test_max_quotas():
    """Max quotas enforced."""
    qm = PipelineQuotaManager(max_quotas=2)
    qm.create_quota("a", "cpu", 100, "x")
    qm.create_quota("b", "cpu", 100, "x")
    assert qm.create_quota("c", "cpu", 100, "x") == ""
    print("OK: max quotas")


def test_consume():
    """Consume quota."""
    qm = PipelineQuotaManager()
    qid = qm.create_quota("limit", "tasks", 5, "agent-1")

    assert qm.consume(qid, 2) is True
    q = qm.get_quota(qid)
    assert q["current_usage"] == 2
    assert q["remaining"] == 3

    assert qm.consume(qid, 3) is True
    assert qm.consume(qid, 1) is False  # Would exceed
    print("OK: consume")


def test_release():
    """Release quota."""
    qm = PipelineQuotaManager()
    qid = qm.create_quota("limit", "tasks", 10, "agent-1")
    qm.consume(qid, 5)

    assert qm.release(qid, 3) is True
    assert qm.get_quota(qid)["current_usage"] == 2

    # Can't release below 0
    assert qm.release(qid, 10) is True
    assert qm.get_quota(qid)["current_usage"] == 0
    print("OK: release")


def test_check_available():
    """Check availability without consuming."""
    qm = PipelineQuotaManager()
    qid = qm.create_quota("limit", "tasks", 5, "agent-1")
    qm.consume(qid, 3)

    assert qm.check_available(qid, 2) is True
    assert qm.check_available(qid, 3) is False
    assert qm.get_quota(qid)["current_usage"] == 3  # Unchanged
    print("OK: check available")


def test_reset_usage():
    """Reset usage manually."""
    qm = PipelineQuotaManager()
    qid = qm.create_quota("limit", "tasks", 10, "agent-1")
    qm.consume(qid, 5)

    assert qm.reset_usage(qid) is True
    assert qm.get_quota(qid)["current_usage"] == 0
    print("OK: reset usage")


def test_period_reset():
    """Auto-reset after period expires."""
    qm = PipelineQuotaManager()
    qid = qm.create_quota("limit", "api_calls", 100, "agent-1",
                           period_seconds=0.02)
    qm.consume(qid, 50)
    assert qm.get_quota(qid)["current_usage"] == 50

    time.sleep(0.03)
    q = qm.get_quota(qid)
    assert q["current_usage"] == 0  # Auto-reset
    print("OK: period reset")


def test_update_limit():
    """Update quota limit."""
    qm = PipelineQuotaManager()
    qid = qm.create_quota("limit", "tasks", 5, "agent-1")

    assert qm.update_limit(qid, 20) is True
    assert qm.get_quota(qid)["limit"] == 20
    assert qm.update_limit(qid, 0) is False
    print("OK: update limit")


def test_list_quotas():
    """List quotas with filters."""
    qm = PipelineQuotaManager()
    qm.create_quota("a", "cpu", 100, "agent-1", "agent")
    qm.create_quota("b", "memory", 200, "agent-1", "agent")
    qm.create_quota("c", "cpu", 500, "team-1", "team")

    all_q = qm.list_quotas()
    assert len(all_q) == 3

    by_owner = qm.list_quotas(owner="agent-1")
    assert len(by_owner) == 2

    by_type = qm.list_quotas(resource_type="cpu")
    assert len(by_type) == 2

    by_owner_type = qm.list_quotas(owner_type="team")
    assert len(by_owner_type) == 1
    print("OK: list quotas")


def test_owner_usage():
    """Get owner usage per resource type."""
    qm = PipelineQuotaManager()
    q1 = qm.create_quota("a", "cpu", 100, "agent-1")
    q2 = qm.create_quota("b", "memory", 200, "agent-1")
    qm.consume(q1, 30)
    qm.consume(q2, 50)

    usage = qm.get_owner_usage("agent-1")
    assert usage["cpu"] == 30
    assert usage["memory"] == 50
    print("OK: owner usage")


def test_exhausted_quotas():
    """Get near-exhausted quotas."""
    qm = PipelineQuotaManager()
    q1 = qm.create_quota("a", "tasks", 10, "agent-1")
    q2 = qm.create_quota("b", "tasks", 10, "agent-2")
    qm.consume(q1, 9)  # 90%
    qm.consume(q2, 3)  # 30%

    exhausted = qm.get_exhausted_quotas()
    assert len(exhausted) == 1
    assert exhausted[0]["quota_id"] == q1
    print("OK: exhausted quotas")


def test_usage_history():
    """Usage history recorded."""
    qm = PipelineQuotaManager()
    qid = qm.create_quota("limit", "tasks", 100, "agent-1")
    qm.consume(qid, 5, source="test")
    qm.consume(qid, 3, source="test")

    history = qm.get_usage_history(quota_id=qid)
    assert len(history) == 2
    assert history[0]["amount"] == 3  # Most recent first
    print("OK: usage history")


def test_owner_summary():
    """Owner summary."""
    qm = PipelineQuotaManager()
    q1 = qm.create_quota("a", "cpu", 100, "agent-1")
    q2 = qm.create_quota("b", "memory", 200, "agent-1")
    qm.consume(q1, 30)
    qm.consume(q2, 50)

    summary = qm.get_owner_summary("agent-1")
    assert summary["quota_count"] == 2
    assert summary["total_limit"] == 300
    assert summary["total_usage"] == 80

    assert qm.get_owner_summary("nonexistent") == {}
    print("OK: owner summary")


def test_callbacks():
    """Callbacks fire on events."""
    qm = PipelineQuotaManager()
    qid = qm.create_quota("limit", "tasks", 2, "agent-1")

    fired = []
    assert qm.on_change("mon", lambda a, q: fired.append(a)) is True
    assert qm.on_change("mon", lambda a, q: None) is False

    qm.consume(qid, 2)
    qm.consume(qid, 1)  # Should exceed

    assert "quota_exceeded" in fired

    assert qm.remove_callback("mon") is True
    assert qm.remove_callback("mon") is False
    print("OK: callbacks")


def test_warning_callback():
    """Warning fires at 80%."""
    qm = PipelineQuotaManager()
    qid = qm.create_quota("limit", "tasks", 10, "agent-1")

    fired = []
    qm.on_change("mon", lambda a, q: fired.append(a))

    qm.consume(qid, 8)  # 80% - should warn
    assert "quota_warning" in fired
    print("OK: warning callback")


def test_stats():
    """Stats are accurate."""
    qm = PipelineQuotaManager()
    qid = qm.create_quota("limit", "tasks", 5, "agent-1")
    qm.consume(qid, 3)
    qm.consume(qid, 3)  # Rejected

    stats = qm.get_stats()
    assert stats["total_quotas_created"] == 1
    assert stats["total_consumed"] == 1
    assert stats["total_rejected"] == 1
    assert stats["total_quotas"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    qm = PipelineQuotaManager()
    qm.create_quota("a", "cpu", 100, "x")

    qm.reset()
    assert qm.list_quotas() == []
    stats = qm.get_stats()
    assert stats["total_quotas"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Quota Manager Tests ===\n")
    test_create_quota()
    test_invalid_quota()
    test_max_quotas()
    test_consume()
    test_release()
    test_check_available()
    test_reset_usage()
    test_period_reset()
    test_update_limit()
    test_list_quotas()
    test_owner_usage()
    test_exhausted_quotas()
    test_usage_history()
    test_owner_summary()
    test_callbacks()
    test_warning_callback()
    test_stats()
    test_reset()
    print("\n=== ALL 18 TESTS PASSED ===")


if __name__ == "__main__":
    main()
