"""Test agent skill matcher -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_skill_matcher import AgentSkillMatcher


def test_register_agent():
    sm = AgentSkillMatcher()
    aid = sm.register_agent("agent-1", tags=["backend"])
    assert aid.startswith("asm-")
    p = sm.get_agent_profile("agent-1")
    assert p is not None
    assert p["agent_id"] == "agent-1"
    assert sm.register_agent("agent-1") == aid  # dup returns existing id
    print("OK: register agent")


def test_add_remove_skill():
    sm = AgentSkillMatcher()
    sm.register_agent("agent-1")
    assert sm.add_skill("agent-1", "python", proficiency=90.0) is True
    assert sm.add_skill("agent-1", "rust", proficiency=60.0) is True
    p = sm.get_agent_profile("agent-1")
    assert p["skill_count"] == 2
    assert p["skills"]["python"] == 90.0
    assert sm.remove_skill("agent-1", "rust") is True
    assert sm.remove_skill("agent-1", "rust") is False
    assert sm.get_agent_profile("agent-1")["skill_count"] == 1
    print("OK: add remove skill")


def test_create_task_profile():
    sm = AgentSkillMatcher()
    tid = sm.create_task_profile("build_api", required_skills=["python", "fastapi"], min_proficiency=50.0)
    assert tid.startswith("atp-")
    tp = sm.get_task_profile("build_api")
    assert tp is not None
    assert "python" in tp["required_skills"]
    assert sm.create_task_profile("build_api") == tid  # dup returns existing id
    print("OK: create task profile")


def test_match():
    sm = AgentSkillMatcher()
    sm.register_agent("agent-1")
    sm.add_skill("agent-1", "python", 90.0)
    sm.add_skill("agent-1", "fastapi", 80.0)
    sm.register_agent("agent-2")
    sm.add_skill("agent-2", "python", 60.0)
    sm.register_agent("agent-3")
    sm.add_skill("agent-3", "rust", 95.0)
    sm.create_task_profile("build_api", required_skills=["python", "fastapi"])
    matches = sm.match("build_api", limit=3)
    assert len(matches) >= 1
    # agent-1 should be best (has both skills at high proficiency)
    assert matches[0]["agent_id"] == "agent-1"
    assert matches[0]["match_score"] > 0
    print("OK: match")


def test_best_match():
    sm = AgentSkillMatcher()
    sm.register_agent("a1")
    sm.add_skill("a1", "python", 90.0)
    sm.register_agent("a2")
    sm.add_skill("a2", "python", 50.0)
    sm.create_task_profile("py_task", required_skills=["python"])
    best = sm.get_best_match("py_task")
    assert best is not None
    assert best["agent_id"] == "a1"
    print("OK: best match")


def test_list_agents():
    sm = AgentSkillMatcher()
    sm.register_agent("a1", tags=["gpu"])
    sm.register_agent("a2")
    sm.add_skill("a1", "cuda", 80.0)
    assert len(sm.list_agents()) == 2
    assert len(sm.list_agents(tag="gpu")) == 1
    assert len(sm.list_agents(skill="cuda")) == 1
    print("OK: list agents")


def test_list_task_profiles():
    sm = AgentSkillMatcher()
    sm.create_task_profile("t1", tags=["api"])
    sm.create_task_profile("t2")
    assert len(sm.list_task_profiles()) == 2
    assert len(sm.list_task_profiles(tag="api")) == 1
    print("OK: list task profiles")


def test_remove():
    sm = AgentSkillMatcher()
    sm.register_agent("a1")
    sm.create_task_profile("t1")
    assert sm.remove_agent("a1") is True
    assert sm.remove_agent("a1") is False
    assert sm.remove_task_profile("t1") is True
    assert sm.remove_task_profile("t1") is False
    print("OK: remove")


def test_history():
    sm = AgentSkillMatcher()
    sm.register_agent("a1")
    hist = sm.get_history()
    assert len(hist) >= 1
    print("OK: history")


def test_callbacks():
    sm = AgentSkillMatcher()
    fired = []
    sm.on_change("mon", lambda a, d: fired.append(a))
    sm.register_agent("a1")
    assert len(fired) >= 1
    assert sm.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    sm = AgentSkillMatcher()
    sm.register_agent("a1")
    stats = sm.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    sm = AgentSkillMatcher()
    sm.register_agent("a1")
    sm.reset()
    assert sm.list_agents() == []
    print("OK: reset")


def main():
    print("=== Agent Skill Matcher Tests ===\n")
    test_register_agent()
    test_add_remove_skill()
    test_create_task_profile()
    test_match()
    test_best_match()
    test_list_agents()
    test_list_task_profiles()
    test_remove()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
