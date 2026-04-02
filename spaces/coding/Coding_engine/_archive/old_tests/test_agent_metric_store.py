"""Test agent metric store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_metric_store import AgentMetricStore


def test_record():
    ms = AgentMetricStore()
    mid = ms.record("agent-1", "cpu", 45.5, tags=["system"])
    assert len(mid) > 0
    m = ms.get_metric(mid)
    assert m is not None
    assert m["agent_id"] == "agent-1"
    assert m["value"] == 45.5
    print("OK: record")


def test_get_latest():
    ms = AgentMetricStore()
    ms.record("a1", "cpu", 40.0)
    import time
    time.sleep(0.01)
    ms.record("a1", "cpu", 60.0)
    latest = ms.get_latest("a1", "cpu")
    assert latest is not None
    assert latest["value"] == 60.0
    print("OK: get latest")


def test_get_history():
    ms = AgentMetricStore()
    ms.record("a1", "cpu", 40.0)
    ms.record("a1", "cpu", 50.0)
    ms.record("a1", "cpu", 60.0)
    history = ms.get_history("a1", "cpu")
    assert len(history) == 3
    print("OK: get history")


def test_get_average():
    ms = AgentMetricStore()
    ms.record("a1", "cpu", 40.0)
    ms.record("a1", "cpu", 60.0)
    avg = ms.get_average("a1", "cpu")
    assert avg == 50.0
    print("OK: get average")


def test_agent_summary():
    ms = AgentMetricStore()
    ms.record("a1", "cpu", 40.0)
    ms.record("a1", "cpu", 60.0)
    ms.record("a1", "memory", 80.0)
    summary = ms.get_agent_summary("a1")
    assert "metrics" in summary or "cpu" in str(summary)
    print("OK: agent summary")


def test_list_agents():
    ms = AgentMetricStore()
    ms.record("a1", "cpu", 50.0)
    ms.record("a2", "cpu", 60.0)
    agents = ms.list_agents()
    assert "a1" in agents
    assert "a2" in agents
    print("OK: list agents")


def test_list_metrics():
    ms = AgentMetricStore()
    ms.record("a1", "cpu", 50.0)
    ms.record("a1", "memory", 80.0)
    metrics = ms.list_metrics(agent_id="a1")
    assert "cpu" in metrics
    assert "memory" in metrics
    print("OK: list metrics")


def test_purge():
    ms = AgentMetricStore()
    ms.record("a1", "cpu", 50.0)
    import time
    time.sleep(0.01)
    count = ms.purge(before_timestamp=time.time() + 1)
    assert count >= 1
    print("OK: purge")


def test_callbacks():
    ms = AgentMetricStore()
    fired = []
    ms.on_change("mon", lambda a, d: fired.append(a))
    ms.record("a1", "cpu", 50.0)
    assert len(fired) >= 1
    assert ms.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ms = AgentMetricStore()
    ms.record("a1", "cpu", 50.0)
    stats = ms.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ms = AgentMetricStore()
    ms.record("a1", "cpu", 50.0)
    ms.reset()
    assert ms.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Metric Store Tests ===\n")
    test_record()
    test_get_latest()
    test_get_history()
    test_get_average()
    test_agent_summary()
    test_list_agents()
    test_list_metrics()
    test_purge()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
