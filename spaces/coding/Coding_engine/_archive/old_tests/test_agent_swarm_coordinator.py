"""Test agent swarm coordinator -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_swarm_coordinator import AgentSwarmCoordinator


def test_create_swarm():
    sc = AgentSwarmCoordinator()
    sid = sc.create_swarm("alpha", objective="build auth module")
    assert sid.startswith("swm-")
    s = sc.get_swarm("alpha")
    assert s["name"] == "alpha"
    assert s["objective"] == "build auth module"
    assert s["member_count"] == 0
    assert sc.create_swarm("alpha") == ""  # dup
    print("OK: create swarm")


def test_join_leave():
    sc = AgentSwarmCoordinator()
    sc.create_swarm("alpha", max_agents=2)
    assert sc.join_swarm("alpha", "agent-1") is True
    assert sc.join_swarm("alpha", "agent-2") is True
    s = sc.get_swarm("alpha")
    assert s["member_count"] == 2
    # max reached
    assert sc.join_swarm("alpha", "agent-3") is False
    # duplicate
    assert sc.join_swarm("alpha", "agent-1") is False
    # leave
    assert sc.leave_swarm("alpha", "agent-1") is True
    assert sc.leave_swarm("alpha", "agent-1") is False  # already left
    assert sc.get_swarm("alpha")["member_count"] == 1
    print("OK: join leave")


def test_elect_leader():
    sc = AgentSwarmCoordinator()
    sc.create_swarm("alpha")
    sc.join_swarm("alpha", "agent-1", role="worker")
    sc.join_swarm("alpha", "agent-2", role="worker")
    leader = sc.elect_leader("alpha")
    assert leader == "agent-1"  # first joined
    s = sc.get_swarm("alpha")
    assert s["leader"] == "agent-1"
    print("OK: elect leader")


def test_assign_complete_task():
    sc = AgentSwarmCoordinator()
    sc.create_swarm("alpha")
    sc.join_swarm("alpha", "agent-1")
    tid = sc.assign_task("alpha", "agent-1", "build_login", priority=8)
    assert tid.startswith("stk-")
    s = sc.get_swarm("alpha")
    assert s["task_count"] >= 1
    assert sc.complete_task("alpha", tid) is True
    assert sc.complete_task("alpha", tid) is False  # already completed
    print("OK: assign complete task")


def test_fail_task():
    sc = AgentSwarmCoordinator()
    sc.create_swarm("alpha")
    sc.join_swarm("alpha", "agent-1")
    tid = sc.assign_task("alpha", "agent-1", "build_oauth")
    assert sc.fail_task("alpha", tid, reason="timeout") is True
    print("OK: fail task")


def test_progress():
    sc = AgentSwarmCoordinator()
    sc.create_swarm("alpha")
    sc.join_swarm("alpha", "agent-1")
    t1 = sc.assign_task("alpha", "agent-1", "task1")
    t2 = sc.assign_task("alpha", "agent-1", "task2")
    sc.complete_task("alpha", t1)
    prog = sc.get_swarm_progress("alpha")
    assert prog["total_tasks"] == 2
    assert prog["completed"] == 1
    assert prog["completion_pct"] == 50.0
    print("OK: progress")


def test_broadcast():
    sc = AgentSwarmCoordinator()
    sc.create_swarm("alpha")
    sc.join_swarm("alpha", "agent-1")
    sc.join_swarm("alpha", "agent-2")
    count = sc.broadcast("alpha", "starting build", sender="leader")
    assert count == 2
    print("OK: broadcast")


def test_list_swarms():
    sc = AgentSwarmCoordinator()
    sc.create_swarm("alpha", tags=["infra"])
    sc.create_swarm("beta")
    assert len(sc.list_swarms()) == 2
    assert len(sc.list_swarms(tag="infra")) == 1
    print("OK: list swarms")


def test_remove_swarm():
    sc = AgentSwarmCoordinator()
    sc.create_swarm("alpha")
    assert sc.remove_swarm("alpha") is True
    assert sc.remove_swarm("alpha") is False
    assert sc.get_swarm("alpha") is None
    print("OK: remove swarm")


def test_history():
    sc = AgentSwarmCoordinator()
    sc.create_swarm("alpha")
    sc.join_swarm("alpha", "agent-1")
    hist = sc.get_history()
    assert len(hist) >= 2
    print("OK: history")


def test_callbacks():
    sc = AgentSwarmCoordinator()
    fired = []
    sc.on_change("mon", lambda a, d: fired.append(a))
    sc.create_swarm("alpha")
    assert "swarm_created" in fired
    assert sc.on_change("mon", lambda a, d: None) is False
    assert sc.remove_callback("mon") is True
    assert sc.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    sc = AgentSwarmCoordinator()
    sc.create_swarm("alpha")
    sc.join_swarm("alpha", "agent-1")
    sc.assign_task("alpha", "agent-1", "t1")
    stats = sc.get_stats()
    assert stats["current_swarms"] >= 1
    print("OK: stats")


def test_reset():
    sc = AgentSwarmCoordinator()
    sc.create_swarm("alpha")
    sc.reset()
    assert sc.list_swarms() == []
    assert sc.get_stats()["current_swarms"] == 0
    print("OK: reset")


def main():
    print("=== Agent Swarm Coordinator Tests ===\n")
    test_create_swarm()
    test_join_leave()
    test_elect_leader()
    test_assign_complete_task()
    test_fail_task()
    test_progress()
    test_broadcast()
    test_list_swarms()
    test_remove_swarm()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
