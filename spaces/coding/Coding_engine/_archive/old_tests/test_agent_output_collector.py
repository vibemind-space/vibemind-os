"""Test agent output collector -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_output_collector import AgentOutputCollector


def test_collect():
    oc = AgentOutputCollector()
    oid = oc.collect("agent-1", "build", {"result": "success"})
    assert len(oid) > 0
    assert oid.startswith("aoc-")
    print("OK: collect")


def test_get_output():
    oc = AgentOutputCollector()
    oid = oc.collect("agent-1", "test", {"passed": 10})
    out = oc.get_output(oid)
    assert out is not None
    assert out["agent_id"] == "agent-1"
    assert oc.get_output("nonexistent") is None
    print("OK: get output")


def test_get_outputs():
    oc = AgentOutputCollector()
    oc.collect("agent-1", "build", {"v": 1})
    oc.collect("agent-1", "test", {"v": 2})
    oc.collect("agent-1", "build", {"v": 3})
    all_out = oc.get_outputs("agent-1")
    assert len(all_out) == 3
    build_out = oc.get_outputs("agent-1", output_type="build")
    assert len(build_out) == 2
    print("OK: get outputs")


def test_get_latest_output():
    oc = AgentOutputCollector()
    oc.collect("agent-1", "build", {"v": 1})
    oc.collect("agent-1", "test", {"v": 2})
    latest = oc.get_latest_output("agent-1")
    assert latest is not None
    assert latest["output_type"] == "test"
    print("OK: get latest output")


def test_list_agents():
    oc = AgentOutputCollector()
    oc.collect("agent-1", "build", {})
    oc.collect("agent-2", "test", {})
    agents = oc.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    oc = AgentOutputCollector()
    fired = []
    oc.on_change("mon", lambda a, d: fired.append(a))
    oc.collect("agent-1", "build", {})
    assert len(fired) >= 1
    assert oc.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    oc = AgentOutputCollector()
    oc.collect("agent-1", "build", {})
    stats = oc.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    oc = AgentOutputCollector()
    oc.collect("agent-1", "build", {})
    oc.reset()
    assert oc.get_output_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Output Collector Tests ===\n")
    test_collect()
    test_get_output()
    test_get_outputs()
    test_get_latest_output()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 8 TESTS PASSED ===")


if __name__ == "__main__":
    main()
