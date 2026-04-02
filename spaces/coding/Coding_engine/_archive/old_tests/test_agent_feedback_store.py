"""Test agent feedback store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_feedback_store import AgentFeedbackStore


def test_submit_feedback():
    fs = AgentFeedbackStore()
    fid = fs.submit_feedback("agent-1", "user-1", 4, comment="Great work", category="quality", tags=["review"])
    assert len(fid) > 0
    f = fs.get_feedback(fid)
    assert f is not None
    assert f["agent_id"] == "agent-1"
    assert f["rating"] == 4
    print("OK: submit feedback")


def test_get_agent_feedback():
    fs = AgentFeedbackStore()
    fs.submit_feedback("agent-1", "user-1", 4, category="quality")
    fs.submit_feedback("agent-1", "user-2", 3, category="speed")
    all_fb = fs.get_agent_feedback("agent-1")
    assert len(all_fb) == 2
    quality_fb = fs.get_agent_feedback("agent-1", category="quality")
    assert len(quality_fb) == 1
    print("OK: get agent feedback")


def test_get_average_rating():
    fs = AgentFeedbackStore()
    fs.submit_feedback("agent-1", "user-1", 4)
    fs.submit_feedback("agent-1", "user-2", 5)
    avg = fs.get_average_rating("agent-1")
    assert avg == 4.5
    print("OK: get average rating")


def test_get_top_rated_agents():
    fs = AgentFeedbackStore()
    fs.submit_feedback("agent-1", "user-1", 5)
    fs.submit_feedback("agent-2", "user-1", 3)
    top = fs.get_top_rated_agents(limit=10)
    assert len(top) == 2
    assert top[0]["agent_id"] == "agent-1"
    print("OK: get top rated agents")


def test_get_feedback_summary():
    fs = AgentFeedbackStore()
    fs.submit_feedback("agent-1", "user-1", 4, category="quality")
    fs.submit_feedback("agent-1", "user-2", 5, category="speed")
    summary = fs.get_feedback_summary("agent-1")
    assert summary["total"] == 2
    assert summary["avg_rating"] == 4.5
    print("OK: get feedback summary")


def test_list_agents_with_feedback():
    fs = AgentFeedbackStore()
    fs.submit_feedback("agent-1", "user-1", 4)
    fs.submit_feedback("agent-2", "user-1", 3)
    agents = fs.list_agents_with_feedback()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents with feedback")


def test_purge():
    fs = AgentFeedbackStore()
    fs.submit_feedback("agent-1", "user-1", 4)
    import time
    time.sleep(0.01)
    count = fs.purge(before_timestamp=time.time() + 1)
    assert count >= 1
    print("OK: purge")


def test_callbacks():
    fs = AgentFeedbackStore()
    fired = []
    fs.on_change("mon", lambda a, d: fired.append(a))
    fs.submit_feedback("agent-1", "user-1", 4)
    assert len(fired) >= 1
    assert fs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    fs = AgentFeedbackStore()
    fs.submit_feedback("agent-1", "user-1", 4)
    stats = fs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    fs = AgentFeedbackStore()
    fs.submit_feedback("agent-1", "user-1", 4)
    fs.reset()
    assert fs.list_agents_with_feedback() == []
    print("OK: reset")


def main():
    print("=== Agent Feedback Store Tests ===\n")
    test_submit_feedback()
    test_get_agent_feedback()
    test_get_average_rating()
    test_get_top_rated_agents()
    test_get_feedback_summary()
    test_list_agents_with_feedback()
    test_purge()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
