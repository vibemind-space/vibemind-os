"""Test agent budget controller."""
import sys
sys.path.insert(0, ".")
from src.services.agent_budget_controller import AgentBudgetController

def test_create():
    bc = AgentBudgetController()
    bid = bc.create_budget("project_x", 1000.0, owner="team1", tags=["ai"])
    assert bid.startswith("bgt-")
    b = bc.get_budget("project_x")
    assert b["total_budget"] == 1000.0
    assert b["spent"] == 0.0
    print("OK: create")

def test_invalid():
    bc = AgentBudgetController()
    assert bc.create_budget("", 100) == ""
    assert bc.create_budget("x", 0) == ""
    assert bc.create_budget("x", -10) == ""
    print("OK: invalid")

def test_duplicate():
    bc = AgentBudgetController()
    bc.create_budget("b1", 100)
    assert bc.create_budget("b1", 200) == ""
    print("OK: duplicate")

def test_charge():
    bc = AgentBudgetController()
    bc.create_budget("b1", 100.0)
    assert bc.charge("b1", 30.0) is True
    b = bc.get_budget("b1")
    assert b["spent"] == 30.0
    assert abs(b["remaining"] - 70.0) < 0.01
    print("OK: charge")

def test_charge_over_budget():
    bc = AgentBudgetController()
    bc.create_budget("b1", 100.0)
    bc.charge("b1", 80.0)
    assert bc.charge("b1", 30.0) is False  # would exceed
    print("OK: charge over budget")

def test_reserve():
    bc = AgentBudgetController()
    bc.create_budget("b1", 100.0)
    assert bc.reserve("b1", 40.0) is True
    assert abs(bc.get_remaining("b1") - 60.0) < 0.01
    # Can't reserve more than remaining
    assert bc.reserve("b1", 70.0) is False
    print("OK: reserve")

def test_release_reservation():
    bc = AgentBudgetController()
    bc.create_budget("b1", 100.0)
    bc.reserve("b1", 40.0)
    assert bc.release_reservation("b1", 20.0) is True
    assert abs(bc.get_remaining("b1") - 80.0) < 0.01
    print("OK: release reservation")

def test_get_remaining():
    bc = AgentBudgetController()
    bc.create_budget("b1", 100.0)
    bc.charge("b1", 30.0)
    bc.reserve("b1", 20.0)
    assert abs(bc.get_remaining("b1") - 50.0) < 0.01
    assert bc.get_remaining("nonexistent") == 0.0
    print("OK: get remaining")

def test_increase_budget():
    bc = AgentBudgetController()
    bc.create_budget("b1", 100.0)
    assert bc.increase_budget("b1", 50.0) is True
    assert bc.get_budget("b1")["total_budget"] == 150.0
    assert bc.increase_budget("nonexistent", 10) is False
    print("OK: increase budget")

def test_remove():
    bc = AgentBudgetController()
    bc.create_budget("b1", 100.0)
    assert bc.remove_budget("b1") is True
    assert bc.remove_budget("b1") is False
    print("OK: remove")

def test_alert_threshold():
    bc = AgentBudgetController()
    fired = []
    bc.on_change("mon", lambda a, d: fired.append(a))
    bc.create_budget("b1", 100.0, alert_threshold_pct=80.0)
    bc.charge("b1", 85.0)
    assert "budget_alert" in fired
    print("OK: alert threshold")

def test_exceeded_callback():
    bc = AgentBudgetController()
    fired = []
    bc.on_change("mon", lambda a, d: fired.append(a))
    bc.create_budget("b1", 100.0)
    bc.charge("b1", 90.0)
    bc.charge("b1", 20.0)  # should fail and fire exceeded
    assert "budget_exceeded" in fired
    print("OK: exceeded callback")

def test_list():
    bc = AgentBudgetController()
    bc.create_budget("b1", 100, owner="team1", tags=["ai"])
    bc.create_budget("b2", 200, owner="team2")
    assert len(bc.list_budgets()) == 2
    assert len(bc.list_budgets(owner="team1")) == 1
    assert len(bc.list_budgets(tag="ai")) == 1
    print("OK: list")

def test_history():
    bc = AgentBudgetController()
    bc.create_budget("b1", 100)
    bc.charge("b1", 10)
    hist = bc.get_history()
    assert len(hist) >= 2
    limited = bc.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")

def test_callbacks():
    bc = AgentBudgetController()
    assert bc.on_change("m", lambda a, d: None) is True
    assert bc.on_change("m", lambda a, d: None) is False
    assert bc.remove_callback("m") is True
    assert bc.remove_callback("m") is False
    print("OK: callbacks")

def test_stats():
    bc = AgentBudgetController()
    bc.create_budget("b1", 100)
    bc.charge("b1", 30)
    stats = bc.get_stats()
    assert stats["current_budgets"] == 1
    assert stats["total_budget"] == 100
    assert stats["total_spent"] == 30
    print("OK: stats")

def test_reset():
    bc = AgentBudgetController()
    bc.create_budget("b1", 100)
    bc.reset()
    assert bc.list_budgets() == []
    assert bc.get_stats()["total_created"] == 0
    print("OK: reset")

def main():
    print("=== Agent Budget Controller Tests ===\n")
    test_create()
    test_invalid()
    test_duplicate()
    test_charge()
    test_charge_over_budget()
    test_reserve()
    test_release_reservation()
    test_get_remaining()
    test_increase_budget()
    test_remove()
    test_alert_threshold()
    test_exceeded_callback()
    test_list()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")

if __name__ == "__main__":
    main()
