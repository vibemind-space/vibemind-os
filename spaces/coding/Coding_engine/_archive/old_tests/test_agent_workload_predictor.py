"""Test agent workload predictor -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_workload_predictor import AgentWorkloadPredictor


def test_register_agent():
    wp = AgentWorkloadPredictor()
    aid = wp.register_agent("agent-1", capacity=100.0)
    assert aid.startswith("wpa-")
    a = wp.get_agent(aid)
    assert a is not None
    assert a["agent_id"] == "agent-1"
    assert a["capacity"] == 100.0
    assert a["capacity_pct_used"] == 0.0
    print("OK: register agent")


def test_record_task():
    wp = AgentWorkloadPredictor()
    aid = wp.register_agent("agent-1")
    tid = wp.record_task(aid, "build_auth", duration=5.0, complexity=7)
    assert tid.startswith("wpt-")
    a = wp.get_agent(aid)
    assert a["task_count"] == 1
    assert a["avg_task_duration"] == 5.0
    print("OK: record task")


def test_assign_release_load():
    wp = AgentWorkloadPredictor()
    aid = wp.register_agent("agent-1", capacity=100.0)
    assert wp.assign_load(aid, 40.0) is True
    a = wp.get_agent(aid)
    assert a["current_load"] == 40.0
    assert wp.release_load(aid, 15.0) is True
    a2 = wp.get_agent(aid)
    assert a2["current_load"] == 25.0
    print("OK: assign release load")


def test_predict_completion():
    wp = AgentWorkloadPredictor()
    aid = wp.register_agent("agent-1")
    wp.record_task(aid, "t1", duration=10.0)
    wp.record_task(aid, "t2", duration=20.0)
    # avg = 15.0, so 4 tasks = 60.0
    predicted = wp.predict_completion(aid, 4)
    assert predicted == 60.0
    print("OK: predict completion")


def test_bottlenecks():
    wp = AgentWorkloadPredictor()
    a1 = wp.register_agent("agent-1", capacity=100.0)
    a2 = wp.register_agent("agent-2", capacity=100.0)
    wp.assign_load(a1, 90.0)  # 90% -- bottleneck
    wp.assign_load(a2, 30.0)  # 30% -- fine
    bottlenecks = wp.get_bottlenecks(threshold=80.0)
    assert len(bottlenecks) == 1
    assert bottlenecks[0]["agent_id"] == "agent-1"
    print("OK: bottlenecks")


def test_suggest_scaling():
    wp = AgentWorkloadPredictor()
    a1 = wp.register_agent("agent-1", capacity=100.0)
    a2 = wp.register_agent("agent-2", capacity=100.0)
    wp.assign_load(a1, 90.0)
    wp.assign_load(a2, 10.0)
    suggestion = wp.suggest_scaling()
    assert len(suggestion["overloaded"]) >= 1
    assert len(suggestion["underloaded"]) >= 1
    print("OK: suggest scaling")


def test_agent_trend():
    wp = AgentWorkloadPredictor()
    aid = wp.register_agent("agent-1")
    for i in range(10):
        wp.record_task(aid, f"t{i}", duration=float(i + 1))
    trend = wp.get_agent_trend(aid, window=10)
    assert "direction" in trend or "trend" in trend
    print("OK: agent trend")


def test_list_agents():
    wp = AgentWorkloadPredictor()
    wp.register_agent("a1", tags=["gpu"])
    wp.register_agent("a2")
    assert len(wp.list_agents()) == 2
    assert len(wp.list_agents(tag="gpu")) == 1
    print("OK: list agents")


def test_remove_agent():
    wp = AgentWorkloadPredictor()
    aid = wp.register_agent("a1")
    assert wp.remove_agent(aid) is True
    assert wp.remove_agent(aid) is False
    print("OK: remove agent")


def test_history():
    wp = AgentWorkloadPredictor()
    aid = wp.register_agent("a1")
    wp.record_task(aid, "t1", duration=5.0)
    hist = wp.get_history()
    assert len(hist) >= 1
    print("OK: history")


def test_callbacks():
    wp = AgentWorkloadPredictor()
    fired = []
    wp.on_change("mon", lambda a, d: fired.append(a))
    wp.register_agent("a1")
    assert len(fired) >= 1
    assert wp.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    wp = AgentWorkloadPredictor()
    wp.register_agent("a1")
    stats = wp.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    wp = AgentWorkloadPredictor()
    wp.register_agent("a1")
    wp.reset()
    assert wp.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Workload Predictor Tests ===\n")
    test_register_agent()
    test_record_task()
    test_assign_release_load()
    test_predict_completion()
    test_bottlenecks()
    test_suggest_scaling()
    test_agent_trend()
    test_list_agents()
    test_remove_agent()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
