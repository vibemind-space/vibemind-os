"""Test agent skill registry -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_skill_registry import AgentSkillRegistry


def test_register_skill():
    sr = AgentSkillRegistry()
    sid = sr.register_skill("agent-1", "python", proficiency=0.9)
    assert len(sid) > 0
    assert sid.startswith("asr-")
    print("OK: register skill")


def test_get_skill():
    sr = AgentSkillRegistry()
    sid = sr.register_skill("agent-1", "python", proficiency=0.9)
    skill = sr.get_skill(sid)
    assert skill is not None
    assert skill["agent_id"] == "agent-1"
    assert skill["skill_name"] == "python"
    assert skill["proficiency"] == 0.9
    assert sr.get_skill("nonexistent") is None
    print("OK: get skill")


def test_get_agent_skills():
    sr = AgentSkillRegistry()
    sr.register_skill("agent-1", "python", proficiency=0.9)
    sr.register_skill("agent-1", "javascript", proficiency=0.7)
    sr.register_skill("agent-2", "python", proficiency=0.8)
    skills = sr.get_agent_skills("agent-1")
    assert len(skills) == 2
    print("OK: get agent skills")


def test_find_agents_by_skill():
    sr = AgentSkillRegistry()
    sr.register_skill("agent-1", "python", proficiency=0.7)
    sr.register_skill("agent-2", "python", proficiency=0.9)
    sr.register_skill("agent-3", "python", proficiency=0.8)
    agents = sr.find_agents_by_skill("python")
    assert agents[0] == "agent-2"  # Highest proficiency first
    assert len(agents) == 3
    print("OK: find agents by skill")


def test_update_proficiency():
    sr = AgentSkillRegistry()
    sid = sr.register_skill("agent-1", "python", proficiency=0.5)
    assert sr.update_proficiency(sid, 0.95) is True
    skill = sr.get_skill(sid)
    assert skill["proficiency"] == 0.95
    assert sr.update_proficiency("nonexistent", 0.5) is False
    print("OK: update proficiency")


def test_remove_skill():
    sr = AgentSkillRegistry()
    sid = sr.register_skill("agent-1", "python")
    assert sr.remove_skill(sid) is True
    assert sr.remove_skill(sid) is False
    print("OK: remove skill")


def test_list_skills():
    sr = AgentSkillRegistry()
    sr.register_skill("agent-1", "python")
    sr.register_skill("agent-1", "javascript")
    sr.register_skill("agent-2", "python")
    skills = sr.list_skills()
    assert "python" in skills
    assert "javascript" in skills
    print("OK: list skills")


def test_list_agents():
    sr = AgentSkillRegistry()
    sr.register_skill("agent-1", "python")
    sr.register_skill("agent-2", "javascript")
    agents = sr.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    sr = AgentSkillRegistry()
    fired = []
    sr.on_change("mon", lambda a, d: fired.append(a))
    sr.register_skill("agent-1", "python")
    assert len(fired) >= 1
    assert sr.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    sr = AgentSkillRegistry()
    sr.register_skill("agent-1", "python")
    stats = sr.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    sr = AgentSkillRegistry()
    sr.register_skill("agent-1", "python")
    sr.reset()
    assert sr.get_skill_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Skill Registry Tests ===\n")
    test_register_skill()
    test_get_skill()
    test_get_agent_skills()
    test_find_agents_by_skill()
    test_update_proficiency()
    test_remove_skill()
    test_list_skills()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
