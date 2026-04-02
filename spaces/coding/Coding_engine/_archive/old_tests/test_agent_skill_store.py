"""Test agent skill store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_skill_store import AgentSkillStore


def test_add_skill():
    ss = AgentSkillStore()
    sid = ss.add_skill("agent-1", "python", proficiency=0.8, metadata={"years": 5})
    assert len(sid) > 0
    assert sid.startswith("ask-")
    s = ss.get_skill(sid)
    assert s is not None
    assert s["agent_id"] == "agent-1"
    assert s["skill_name"] == "python"
    print("OK: add skill")


def test_add_skill_duplicate():
    ss = AgentSkillStore()
    ss.add_skill("agent-1", "python")
    dup = ss.add_skill("agent-1", "python")
    assert dup == ""
    print("OK: add skill duplicate")


def test_get_agent_skills():
    ss = AgentSkillStore()
    ss.add_skill("agent-1", "python", proficiency=0.8)
    ss.add_skill("agent-1", "rust", proficiency=0.6)
    ss.add_skill("agent-2", "python", proficiency=0.9)
    skills = ss.get_agent_skills("agent-1")
    assert len(skills) == 2
    print("OK: get agent skills")


def test_update_proficiency():
    ss = AgentSkillStore()
    ss.add_skill("agent-1", "python", proficiency=0.5)
    assert ss.update_proficiency("agent-1", "python", 0.9) is True
    skills = ss.get_agent_skills("agent-1")
    py_skill = [s for s in skills if s["skill_name"] == "python"][0]
    assert py_skill["proficiency"] == 0.9
    # Not found
    assert ss.update_proficiency("agent-1", "nonexistent", 0.5) is False
    print("OK: update proficiency")


def test_endorse():
    ss = AgentSkillStore()
    ss.add_skill("agent-1", "python")
    assert ss.endorse("agent-1", "python", "agent-2") is True
    assert ss.endorse("agent-1", "python", "agent-3") is True
    # Dup endorsement - should still return True
    assert ss.endorse("agent-1", "python", "agent-2") is True
    endorsements = ss.get_endorsements("agent-1", "python")
    assert "agent-2" in endorsements
    assert "agent-3" in endorsements
    print("OK: endorse")


def test_find_agents_with_skill():
    ss = AgentSkillStore()
    ss.add_skill("agent-1", "python", proficiency=0.8)
    ss.add_skill("agent-2", "python", proficiency=0.3)
    ss.add_skill("agent-3", "python", proficiency=0.9)
    found = ss.find_agents_with_skill("python", min_proficiency=0.5)
    agent_ids = [a["agent_id"] if isinstance(a, dict) else a for a in found]
    assert len(agent_ids) == 2
    print("OK: find agents with skill")


def test_remove_skill():
    ss = AgentSkillStore()
    ss.add_skill("agent-1", "python")
    assert ss.remove_skill("agent-1", "python") is True
    assert ss.remove_skill("agent-1", "python") is False
    print("OK: remove skill")


def test_get_top_skilled():
    ss = AgentSkillStore()
    ss.add_skill("agent-1", "python", proficiency=0.5)
    ss.add_skill("agent-2", "python", proficiency=0.9)
    ss.add_skill("agent-3", "python", proficiency=0.7)
    top = ss.get_top_skilled("python", limit=2)
    assert len(top) == 2
    # First should be highest proficiency
    first = top[0]
    if isinstance(first, dict):
        assert first["agent_id"] == "agent-2" or first["proficiency"] == 0.9
    print("OK: get top skilled")


def test_callbacks():
    ss = AgentSkillStore()
    fired = []
    ss.on_change("mon", lambda a, d: fired.append(a))
    ss.add_skill("agent-1", "python")
    assert len(fired) >= 1
    assert ss.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ss = AgentSkillStore()
    ss.add_skill("agent-1", "python")
    stats = ss.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ss = AgentSkillStore()
    ss.add_skill("agent-1", "python")
    ss.reset()
    assert ss.get_agent_skills("agent-1") == []
    print("OK: reset")


def main():
    print("=== Agent Skill Store Tests ===\n")
    test_add_skill()
    test_add_skill_duplicate()
    test_get_agent_skills()
    test_update_proficiency()
    test_endorse()
    test_find_agents_with_skill()
    test_remove_skill()
    test_get_top_skilled()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
