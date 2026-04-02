"""Test agent learning engine."""
import sys
sys.path.insert(0, ".")

from src.services.agent_learning_engine import AgentLearningEngine


def test_record_episode():
    """Record and retrieve episode."""
    le = AgentLearningEngine()
    eid = le.record_episode("agent_a", episode_type="success",
                            context="Fixed bug #42", lesson="Always check nulls",
                            confidence=0.9, tags=["bugfix"], source="code_review")
    assert eid.startswith("ep-")

    ep = le.get_episode(eid)
    assert ep is not None
    assert ep["agent"] == "agent_a"
    assert ep["episode_type"] == "success"
    assert ep["lesson"] == "Always check nulls"
    assert ep["confidence"] == 0.9

    assert le.remove_episode(eid) is True
    assert le.remove_episode(eid) is False
    print("OK: record episode")


def test_invalid_episode():
    """Invalid episode rejected."""
    le = AgentLearningEngine()
    assert le.record_episode("") == ""
    assert le.record_episode("a", episode_type="invalid") == ""
    print("OK: invalid episode")


def test_max_episodes():
    """Max episodes enforced."""
    le = AgentLearningEngine(max_episodes=2)
    le.record_episode("a")
    le.record_episode("b")
    assert le.record_episode("c") == ""
    print("OK: max episodes")


def test_search_episodes():
    """Search episodes."""
    le = AgentLearningEngine()
    le.record_episode("agent_a", episode_type="success", tags=["t1"],
                      source="ci", confidence=0.8)
    le.record_episode("agent_b", episode_type="failure", confidence=0.3)

    all_ep = le.search_episodes()
    assert len(all_ep) == 2

    by_agent = le.search_episodes(agent="agent_a")
    assert len(by_agent) == 1

    by_type = le.search_episodes(episode_type="failure")
    assert len(by_type) == 1

    by_tag = le.search_episodes(tag="t1")
    assert len(by_tag) == 1

    by_source = le.search_episodes(source="ci")
    assert len(by_source) == 1

    by_conf = le.search_episodes(min_confidence=0.5)
    assert len(by_conf) == 1
    print("OK: search episodes")


def test_agent_lessons():
    """Get agent lessons."""
    le = AgentLearningEngine()
    le.record_episode("a", lesson="Lesson 1", confidence=0.9)
    le.record_episode("a", lesson="Lesson 2", confidence=0.5)
    le.record_episode("a", lesson="", confidence=0.8)  # no lesson
    le.record_episode("b", lesson="Other", confidence=1.0)

    lessons = le.get_agent_lessons("a")
    assert len(lessons) == 2
    assert lessons[0]["confidence"] >= lessons[1]["confidence"]

    high = le.get_agent_lessons("a", min_confidence=0.8)
    assert len(high) == 1
    print("OK: agent lessons")


def test_episode_summary():
    """Get agent episode summary."""
    le = AgentLearningEngine()
    le.record_episode("a", episode_type="success", confidence=0.8)
    le.record_episode("a", episode_type="failure", confidence=0.4)

    s = le.get_agent_episode_summary("a")
    assert s["total_episodes"] == 2
    assert s["by_type"]["success"] == 1
    assert s["by_type"]["failure"] == 1
    assert abs(s["avg_confidence"] - 0.6) < 0.01
    print("OK: episode summary")


def test_confidence_clamping():
    """Confidence clamped to 0-1."""
    le = AgentLearningEngine()
    e1 = le.record_episode("a", confidence=-5.0)
    assert le.get_episode(e1)["confidence"] == 0.0
    e2 = le.record_episode("a", confidence=99.0)
    assert le.get_episode(e2)["confidence"] == 1.0
    print("OK: confidence clamping")


def test_register_skill():
    """Register and retrieve skill."""
    le = AgentLearningEngine()
    sid = le.register_skill("agent_a", "python", initial_proficiency=30.0)
    assert sid.startswith("sk-")

    sk = le.get_skill(sid)
    assert sk is not None
    assert sk["agent"] == "agent_a"
    assert sk["name"] == "python"
    assert sk["proficiency"] == 30.0
    assert sk["practice_count"] == 0

    assert le.remove_skill(sid) is True
    assert le.remove_skill(sid) is False
    print("OK: register skill")


def test_invalid_skill():
    """Invalid skill rejected."""
    le = AgentLearningEngine()
    assert le.register_skill("", "python") == ""
    assert le.register_skill("a", "") == ""
    print("OK: invalid skill")


def test_duplicate_skill():
    """Duplicate skill name per agent rejected."""
    le = AgentLearningEngine()
    le.register_skill("a", "python")
    assert le.register_skill("a", "python") == ""
    # Different agent is OK
    assert le.register_skill("b", "python") != ""
    print("OK: duplicate skill")


def test_max_skills():
    """Max skills enforced."""
    le = AgentLearningEngine(max_skills=2)
    le.register_skill("a", "s1")
    le.register_skill("a", "s2")
    assert le.register_skill("a", "s3") == ""
    print("OK: max skills")


def test_practice_skill():
    """Practice skill increases proficiency."""
    le = AgentLearningEngine()
    sid = le.register_skill("a", "python", initial_proficiency=10.0)

    assert le.practice_skill(sid, delta=5.0) is True
    sk = le.get_skill(sid)
    assert sk["proficiency"] == 15.0
    assert sk["practice_count"] == 1
    print("OK: practice skill")


def test_proficiency_clamping():
    """Proficiency clamped to 0-100."""
    le = AgentLearningEngine()
    sid = le.register_skill("a", "python", initial_proficiency=95.0)
    le.practice_skill(sid, delta=20.0)
    assert le.get_skill(sid)["proficiency"] == 100.0
    le.practice_skill(sid, delta=-200.0)
    assert le.get_skill(sid)["proficiency"] == 0.0
    print("OK: proficiency clamping")


def test_get_agent_skills():
    """Get agent skills sorted by proficiency."""
    le = AgentLearningEngine()
    le.register_skill("a", "python", initial_proficiency=80.0)
    le.register_skill("a", "rust", initial_proficiency=30.0)
    le.register_skill("b", "go", initial_proficiency=50.0)

    skills = le.get_agent_skills("a")
    assert len(skills) == 2
    assert skills[0]["proficiency"] >= skills[1]["proficiency"]
    print("OK: get agent skills")


def test_search_skills():
    """Search skills."""
    le = AgentLearningEngine()
    le.register_skill("a", "python", initial_proficiency=80.0)
    le.register_skill("a", "rust", initial_proficiency=30.0)

    all_sk = le.search_skills()
    assert len(all_sk) == 2

    by_agent = le.search_skills(agent="a")
    assert len(by_agent) == 2

    by_name = le.search_skills(name="python")
    assert len(by_name) == 1

    by_prof = le.search_skills(min_proficiency=50.0)
    assert len(by_prof) == 1
    print("OK: search skills")


def test_get_skill_by_name():
    """Get skill by agent+name."""
    le = AgentLearningEngine()
    le.register_skill("a", "python")

    sk = le.get_skill_by_name("a", "python")
    assert sk is not None
    assert sk["name"] == "python"
    assert le.get_skill_by_name("a", "nonexistent") is None
    print("OK: get skill by name")


def test_callback():
    """Callback fires on episode and skill events."""
    le = AgentLearningEngine()
    fired = []
    le.on_change("mon", lambda a, d: fired.append(a))

    le.record_episode("a")
    assert "episode_recorded" in fired

    sid = le.register_skill("a", "python")
    assert "skill_registered" in fired

    le.practice_skill(sid)
    assert "skill_practiced" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    le = AgentLearningEngine()
    assert le.on_change("mon", lambda a, d: None) is True
    assert le.on_change("mon", lambda a, d: None) is False
    assert le.remove_callback("mon") is True
    assert le.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    le = AgentLearningEngine()
    le.record_episode("a")
    sid = le.register_skill("a", "python")
    le.practice_skill(sid)

    stats = le.get_stats()
    assert stats["total_episodes"] == 1
    assert stats["total_skills"] == 1
    assert stats["total_practice"] == 1
    assert stats["current_episodes"] == 1
    assert stats["current_skills"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    le = AgentLearningEngine()
    le.record_episode("a")
    le.register_skill("a", "python")

    le.reset()
    assert le.search_episodes() == []
    assert le.search_skills() == []
    stats = le.get_stats()
    assert stats["current_episodes"] == 0
    assert stats["current_skills"] == 0
    print("OK: reset")


def main():
    print("=== Agent Learning Engine Tests ===\n")
    test_record_episode()
    test_invalid_episode()
    test_max_episodes()
    test_search_episodes()
    test_agent_lessons()
    test_episode_summary()
    test_confidence_clamping()
    test_register_skill()
    test_invalid_skill()
    test_duplicate_skill()
    test_max_skills()
    test_practice_skill()
    test_proficiency_clamping()
    test_get_agent_skills()
    test_search_skills()
    test_get_skill_by_name()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 20 TESTS PASSED ===")


if __name__ == "__main__":
    main()
