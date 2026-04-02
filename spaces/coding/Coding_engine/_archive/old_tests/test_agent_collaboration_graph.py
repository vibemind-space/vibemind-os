"""Test agent collaboration graph -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_collaboration_graph import AgentCollaborationGraph


def test_add_agent():
    cg = AgentCollaborationGraph()
    aid = cg.add_agent("agent-1", tags=["backend"])
    assert aid.startswith("acg-")
    a = cg.get_agent("agent-1")
    assert a is not None
    assert a["agent_id"] == "agent-1"
    print("OK: add agent")


def test_add_collaboration():
    cg = AgentCollaborationGraph()
    cg.add_agent("a1")
    cg.add_agent("a2")
    eid = cg.add_collaboration("a1", "a2", weight=3.0, context="shared_task")
    assert eid.startswith("col-")
    # Adding again should increase weight
    cg.add_collaboration("a1", "a2", weight=2.0, context="another_task")
    collab = cg.get_collaboration("a1", "a2")
    assert collab is not None
    assert collab["weight"] == 5.0
    assert collab["interaction_count"] == 2
    print("OK: add collaboration")


def test_get_connections():
    cg = AgentCollaborationGraph()
    cg.add_agent("a1")
    cg.add_agent("a2")
    cg.add_agent("a3")
    cg.add_collaboration("a1", "a2", weight=5.0)
    cg.add_collaboration("a1", "a3", weight=3.0)
    conns = cg.get_agent_connections("a1")
    assert len(conns) == 2
    print("OK: get connections")


def test_most_collaborative():
    cg = AgentCollaborationGraph()
    cg.add_agent("a1")
    cg.add_agent("a2")
    cg.add_agent("a3")
    cg.add_collaboration("a1", "a2", weight=10.0)
    cg.add_collaboration("a1", "a3", weight=5.0)
    cg.add_collaboration("a2", "a3", weight=2.0)
    top = cg.get_most_collaborative(limit=2)
    assert len(top) >= 1
    assert top[0]["agent_id"] == "a1"  # highest total weight
    print("OK: most collaborative")


def test_strongest_pairs():
    cg = AgentCollaborationGraph()
    cg.add_agent("a1")
    cg.add_agent("a2")
    cg.add_agent("a3")
    cg.add_collaboration("a1", "a2", weight=10.0)
    cg.add_collaboration("a2", "a3", weight=3.0)
    pairs = cg.get_strongest_pairs(limit=2)
    assert len(pairs) >= 1
    assert pairs[0]["weight"] == 10.0
    print("OK: strongest pairs")


def test_clusters():
    cg = AgentCollaborationGraph()
    for a in ["a1", "a2", "a3", "b1", "b2"]:
        cg.add_agent(a)
    cg.add_collaboration("a1", "a2", weight=5.0)
    cg.add_collaboration("a2", "a3", weight=5.0)
    cg.add_collaboration("b1", "b2", weight=5.0)
    clusters = cg.get_clusters(min_weight=3.0)
    assert len(clusters) >= 2  # two clusters: {a1,a2,a3} and {b1,b2}
    print("OK: clusters")


def test_isolated_agents():
    cg = AgentCollaborationGraph()
    cg.add_agent("a1")
    cg.add_agent("a2")
    cg.add_agent("lonely")
    cg.add_collaboration("a1", "a2", weight=5.0)
    isolated = cg.get_isolated_agents()
    assert len(isolated) >= 1
    assert any(a["agent_id"] == "lonely" for a in isolated)
    print("OK: isolated agents")


def test_remove():
    cg = AgentCollaborationGraph()
    cg.add_agent("a1")
    cg.add_agent("a2")
    cg.add_collaboration("a1", "a2")
    assert cg.remove_collaboration("a1", "a2") is True
    assert cg.remove_collaboration("a1", "a2") is False
    assert cg.remove_agent("a1") is True
    assert cg.remove_agent("a1") is False
    print("OK: remove")


def test_list_agents():
    cg = AgentCollaborationGraph()
    cg.add_agent("a1", tags=["backend"])
    cg.add_agent("a2")
    assert len(cg.list_agents()) == 2
    assert len(cg.list_agents(tag="backend")) == 1
    print("OK: list agents")


def test_history():
    cg = AgentCollaborationGraph()
    cg.add_agent("a1")
    hist = cg.get_history()
    assert len(hist) >= 1
    print("OK: history")


def test_callbacks():
    cg = AgentCollaborationGraph()
    fired = []
    cg.on_change("mon", lambda a, d: fired.append(a))
    cg.add_agent("a1")
    assert len(fired) >= 1
    assert cg.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cg = AgentCollaborationGraph()
    cg.add_agent("a1")
    stats = cg.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cg = AgentCollaborationGraph()
    cg.add_agent("a1")
    cg.reset()
    assert cg.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Collaboration Graph Tests ===\n")
    test_add_agent()
    test_add_collaboration()
    test_get_connections()
    test_most_collaborative()
    test_strongest_pairs()
    test_clusters()
    test_isolated_agents()
    test_remove()
    test_list_agents()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
