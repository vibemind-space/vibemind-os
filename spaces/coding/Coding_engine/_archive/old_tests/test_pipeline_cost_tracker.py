"""Test pipeline cost tracker."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_cost_tracker import PipelineCostTracker


def test_record_cost():
    """Record and retrieve cost entries."""
    ct = PipelineCostTracker()
    eid = ct.record_cost("compute", 10.0, 0.5, "agent-1", pipeline_id="p1")
    assert eid.startswith("cost-")

    e = ct.get_entry(eid)
    assert e is not None
    assert e["resource_type"] == "compute"
    assert e["amount"] == 10.0
    assert e["unit_cost"] == 0.5
    assert e["total_cost"] == 5.0
    assert e["owner"] == "agent-1"

    assert ct.remove_entry(eid) is True
    assert ct.remove_entry(eid) is False
    print("OK: record cost")


def test_invalid_cost():
    """Invalid cost params rejected."""
    ct = PipelineCostTracker()
    assert ct.record_cost("", 1, 1, "a") == ""
    assert ct.record_cost("invalid", 1, 1, "a") == ""
    assert ct.record_cost("compute", 0, 1, "a") == ""
    assert ct.record_cost("compute", 1, 1, "") == ""
    assert ct.record_cost("compute", 1, 1, "a", owner_type="invalid") == ""
    print("OK: invalid cost")


def test_max_entries():
    """Max entries enforced."""
    ct = PipelineCostTracker(max_entries=2)
    ct.record_cost("compute", 1, 1, "a")
    ct.record_cost("compute", 1, 1, "a")
    assert ct.record_cost("compute", 1, 1, "a") == ""
    print("OK: max entries")


def test_list_entries():
    """List entries with filters."""
    ct = PipelineCostTracker()
    ct.record_cost("compute", 1, 1, "agent-1", pipeline_id="p1", tags=["gpu"])
    ct.record_cost("memory", 2, 1, "agent-1", pipeline_id="p2")
    ct.record_cost("compute", 3, 1, "agent-2", pipeline_id="p1")

    all_e = ct.list_entries()
    assert len(all_e) == 3

    by_owner = ct.list_entries(owner="agent-1")
    assert len(by_owner) == 2

    by_type = ct.list_entries(resource_type="compute")
    assert len(by_type) == 2

    by_pipeline = ct.list_entries(pipeline_id="p1")
    assert len(by_pipeline) == 2

    by_tag = ct.list_entries(tag="gpu")
    assert len(by_tag) == 1
    print("OK: list entries")


def test_create_budget():
    """Create and remove budgets."""
    ct = PipelineCostTracker()
    bid = ct.create_budget("compute_budget", "agent-1", 100.0)
    assert bid.startswith("budget-")

    b = ct.get_budget(bid)
    assert b is not None
    assert b["name"] == "compute_budget"
    assert b["limit"] == 100.0
    assert b["spent"] == 0.0
    assert b["remaining"] == 100.0

    assert ct.remove_budget(bid) is True
    assert ct.remove_budget(bid) is False
    print("OK: create budget")


def test_invalid_budget():
    """Invalid budget params rejected."""
    ct = PipelineCostTracker()
    assert ct.create_budget("", "a", 100) == ""
    assert ct.create_budget("x", "", 100) == ""
    assert ct.create_budget("x", "a", 0) == ""
    assert ct.create_budget("x", "a", 100, owner_type="invalid") == ""
    print("OK: invalid budget")


def test_max_budgets():
    """Max budgets enforced."""
    ct = PipelineCostTracker(max_budgets=2)
    ct.create_budget("a", "x", 100)
    ct.create_budget("b", "x", 100)
    assert ct.create_budget("c", "x", 100) == ""
    print("OK: max budgets")


def test_budget_tracking():
    """Costs automatically tracked against budget."""
    ct = PipelineCostTracker()
    bid = ct.create_budget("limit", "agent-1", 10.0)

    ct.record_cost("compute", 2, 3, "agent-1")  # total=6
    b = ct.get_budget(bid)
    assert b["spent"] == 6.0
    assert b["remaining"] == 4.0
    print("OK: budget tracking")


def test_budget_exceeded():
    """Budget exceeded callback fires."""
    ct = PipelineCostTracker()
    bid = ct.create_budget("limit", "agent-1", 5.0)

    fired = []
    ct.on_change("mon", lambda a, d: fired.append(a))

    ct.record_cost("compute", 3, 2, "agent-1")  # total=6 > limit 5
    assert "budget_exceeded" in fired
    print("OK: budget exceeded")


def test_update_budget_limit():
    """Update budget limit."""
    ct = PipelineCostTracker()
    bid = ct.create_budget("limit", "agent-1", 100)

    assert ct.update_budget_limit(bid, 200) is True
    assert ct.get_budget(bid)["limit"] == 200
    assert ct.update_budget_limit(bid, 0) is False
    print("OK: update budget limit")


def test_list_budgets():
    """List budgets with filters."""
    ct = PipelineCostTracker()
    ct.create_budget("a", "agent-1", 100, "agent")
    ct.create_budget("b", "team-1", 500, "team")

    all_b = ct.list_budgets()
    assert len(all_b) == 2

    by_owner = ct.list_budgets(owner="agent-1")
    assert len(by_owner) == 1

    by_type = ct.list_budgets(owner_type="team")
    assert len(by_type) == 1
    print("OK: list budgets")


def test_period_reset():
    """Budget auto-resets after period."""
    ct = PipelineCostTracker()
    bid = ct.create_budget("limit", "agent-1", 100, period_seconds=0.02)
    ct.record_cost("compute", 50, 1, "agent-1")

    assert ct.get_budget(bid)["spent"] == 50.0

    time.sleep(0.03)
    b = ct.get_budget(bid)
    assert b["spent"] == 0.0
    print("OK: period reset")


def test_owner_total():
    """Get total cost for owner."""
    ct = PipelineCostTracker()
    ct.record_cost("compute", 10, 1, "agent-1")
    ct.record_cost("memory", 5, 2, "agent-1")
    ct.record_cost("compute", 3, 1, "agent-2")

    assert ct.get_owner_total("agent-1") == 20.0
    assert ct.get_owner_total("agent-2") == 3.0
    print("OK: owner total")


def test_cost_by_resource():
    """Cost breakdown by resource type."""
    ct = PipelineCostTracker()
    ct.record_cost("compute", 10, 1, "agent-1")
    ct.record_cost("compute", 5, 1, "agent-1")
    ct.record_cost("memory", 3, 2, "agent-1")

    breakdown = ct.get_cost_by_resource("agent-1")
    assert breakdown["compute"] == 15.0
    assert breakdown["memory"] == 6.0
    print("OK: cost by resource")


def test_cost_by_pipeline():
    """Cost per pipeline."""
    ct = PipelineCostTracker()
    ct.record_cost("compute", 10, 1, "a", pipeline_id="p1")
    ct.record_cost("compute", 5, 1, "a", pipeline_id="p1")
    ct.record_cost("compute", 20, 1, "a", pipeline_id="p2")

    pipelines = ct.get_cost_by_pipeline()
    assert len(pipelines) == 2
    assert pipelines[0]["pipeline_id"] == "p2"  # Higher cost first
    assert pipelines[0]["total_cost"] == 20.0
    print("OK: cost by pipeline")


def test_top_spenders():
    """Top spenders."""
    ct = PipelineCostTracker()
    ct.record_cost("compute", 100, 1, "big-spender")
    ct.record_cost("compute", 10, 1, "small-spender")

    top = ct.get_top_spenders()
    assert len(top) == 2
    assert top[0]["owner"] == "big-spender"
    print("OK: top spenders")


def test_over_budget():
    """Get over-budget entries."""
    ct = PipelineCostTracker()
    b1 = ct.create_budget("a", "agent-1", 5.0)
    b2 = ct.create_budget("b", "agent-2", 100.0)

    ct.record_cost("compute", 10, 1, "agent-1")  # Over budget
    ct.record_cost("compute", 1, 1, "agent-2")  # Under budget

    over = ct.get_over_budget()
    assert len(over) == 1
    assert over[0]["owner"] == "agent-1"
    assert over[0]["overage"] == 5.0
    print("OK: over budget")


def test_owner_summary():
    """Owner summary."""
    ct = PipelineCostTracker()
    ct.create_budget("b", "agent-1", 100)
    ct.record_cost("compute", 10, 1, "agent-1")
    ct.record_cost("memory", 5, 2, "agent-1")

    summary = ct.get_owner_summary("agent-1")
    assert summary["entry_count"] == 2
    assert summary["total_cost"] == 20.0
    assert summary["budget_count"] == 1

    assert ct.get_owner_summary("nonexistent") == {}
    print("OK: owner summary")


def test_callbacks():
    """Callbacks fire on events."""
    ct = PipelineCostTracker()

    fired = []
    assert ct.on_change("mon", lambda a, d: fired.append(a)) is True
    assert ct.on_change("mon", lambda a, d: None) is False

    ct.record_cost("compute", 1, 1, "agent-1")
    assert "cost_recorded" in fired

    assert ct.remove_callback("mon") is True
    assert ct.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    ct = PipelineCostTracker()
    ct.record_cost("compute", 10, 1, "a")
    ct.record_cost("memory", 5, 2, "a")

    stats = ct.get_stats()
    assert stats["total_entries"] == 2
    assert stats["total_cost"] == 20.0
    assert stats["current_entries"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    ct = PipelineCostTracker()
    ct.record_cost("compute", 1, 1, "a")
    ct.create_budget("b", "a", 100)

    ct.reset()
    assert ct.list_entries() == []
    assert ct.list_budgets() == []
    stats = ct.get_stats()
    assert stats["total_entries"] == 0
    assert stats["current_entries"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Cost Tracker Tests ===\n")
    test_record_cost()
    test_invalid_cost()
    test_max_entries()
    test_list_entries()
    test_create_budget()
    test_invalid_budget()
    test_max_budgets()
    test_budget_tracking()
    test_budget_exceeded()
    test_update_budget_limit()
    test_list_budgets()
    test_period_reset()
    test_owner_total()
    test_cost_by_resource()
    test_cost_by_pipeline()
    test_top_spenders()
    test_over_budget()
    test_owner_summary()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
