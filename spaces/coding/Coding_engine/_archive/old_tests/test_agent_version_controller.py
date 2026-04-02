"""Test agent version controller."""
import sys
sys.path.insert(0, ".")
from src.services.agent_version_controller import AgentVersionController

def test_init():
    vc = AgentVersionController()
    vid = vc.init_agent("w1", {"model": "gpt4", "temp": 0.7}, tags=["core"])
    assert vid.startswith("ver-")
    v = vc.get_current("w1")
    assert v["version_num"] == 1
    assert v["config"]["model"] == "gpt4"
    print("OK: init")

def test_invalid_init():
    vc = AgentVersionController()
    assert vc.init_agent("", {}) == ""
    vc.init_agent("w1", {})
    assert vc.init_agent("w1", {}) == ""  # duplicate
    print("OK: invalid init")

def test_max_agents():
    vc = AgentVersionController(max_agents=2)
    vc.init_agent("a", {})
    vc.init_agent("b", {})
    assert vc.init_agent("c", {}) == ""
    print("OK: max agents")

def test_commit():
    vc = AgentVersionController()
    vc.init_agent("w1", {"v": 1})
    vid = vc.commit("w1", {"v": 2}, message="update v")
    assert vid.startswith("ver-")
    v = vc.get_current("w1")
    assert v["version_num"] == 2
    assert v["config"]["v"] == 2
    print("OK: commit")

def test_commit_nonexistent():
    vc = AgentVersionController()
    assert vc.commit("nonexistent", {}) == ""
    print("OK: commit nonexistent")

def test_max_versions():
    vc = AgentVersionController(max_versions_per_agent=3)
    vc.init_agent("w1", {"v": 0})
    vc.commit("w1", {"v": 1})
    vc.commit("w1", {"v": 2})
    assert vc.commit("w1", {"v": 3}) == ""
    print("OK: max versions")

def test_get_version():
    vc = AgentVersionController()
    vc.init_agent("w1", {"v": 1})
    vc.commit("w1", {"v": 2})
    v1 = vc.get_version("w1", 1)
    assert v1["config"]["v"] == 1
    v2 = vc.get_version("w1", 2)
    assert v2["config"]["v"] == 2
    assert vc.get_version("w1", 99) is None
    assert vc.get_version("nonexistent", 1) is None
    print("OK: get version")

def test_rollback():
    vc = AgentVersionController()
    vc.init_agent("w1", {"v": 1})
    vc.commit("w1", {"v": 2})
    assert vc.rollback("w1", 1) is True
    assert vc.get_current("w1")["config"]["v"] == 1
    assert vc.rollback("w1", 99) is False
    assert vc.rollback("nonexistent", 1) is False
    print("OK: rollback")

def test_log():
    vc = AgentVersionController()
    vc.init_agent("w1", {"v": 1})
    vc.commit("w1", {"v": 2})
    vc.commit("w1", {"v": 3})
    log = vc.get_log("w1")
    assert len(log) == 3
    assert log[0]["version_num"] == 3  # most recent first
    limited = vc.get_log("w1", limit=1)
    assert len(limited) == 1
    print("OK: log")

def test_diff():
    vc = AgentVersionController()
    vc.init_agent("w1", {"a": 1, "b": 2})
    vc.commit("w1", {"a": 1, "c": 3})
    d = vc.diff("w1", 1, 2)
    assert "b" in d["removed"]
    assert "c" in d["added"]
    assert d["changed"] == {}
    print("OK: diff")

def test_branches():
    vc = AgentVersionController()
    vc.init_agent("w1", {"v": 1})
    assert vc.create_branch("w1", "experiment") is True
    assert vc.create_branch("w1", "experiment") is False
    assert "experiment" in vc.list_branches("w1")
    print("OK: branches")

def test_switch_branch():
    vc = AgentVersionController()
    vc.init_agent("w1", {"v": 1})
    vc.commit("w1", {"v": 2})
    vc.create_branch("w1", "exp")
    vc.rollback("w1", 1)  # go to v1 on main
    vc.switch_branch("w1", "exp")
    assert vc.get_current("w1")["version_num"] == 2  # exp branch at v2
    assert vc.switch_branch("w1", "nonexistent") is False
    print("OK: switch branch")

def test_list_agents():
    vc = AgentVersionController()
    vc.init_agent("w1", {})
    vc.init_agent("w2", {})
    assert sorted(vc.list_agents()) == ["w1", "w2"]
    print("OK: list agents")

def test_history():
    vc = AgentVersionController()
    vc.init_agent("w1", {})
    vc.commit("w1", {"v": 2})
    hist = vc.get_history()
    assert len(hist) == 2
    limited = vc.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")

def test_callback():
    vc = AgentVersionController()
    fired = []
    vc.on_change("mon", lambda a, d: fired.append(a))
    vc.init_agent("w1", {})
    assert "agent_initialized" in fired
    vc.commit("w1", {"v": 2})
    assert "version_committed" in fired
    print("OK: callback")

def test_callbacks():
    vc = AgentVersionController()
    assert vc.on_change("m", lambda a, d: None) is True
    assert vc.on_change("m", lambda a, d: None) is False
    assert vc.remove_callback("m") is True
    assert vc.remove_callback("m") is False
    print("OK: callbacks")

def test_stats():
    vc = AgentVersionController()
    vc.init_agent("w1", {})
    vc.commit("w1", {"v": 2})
    vc.rollback("w1", 1)
    stats = vc.get_stats()
    assert stats["current_agents"] == 1
    assert stats["total_versions"] == 2
    assert stats["total_commits"] == 2
    assert stats["total_rollbacks"] == 1
    print("OK: stats")

def test_reset():
    vc = AgentVersionController()
    vc.init_agent("w1", {})
    vc.reset()
    assert vc.list_agents() == []
    assert vc.get_stats()["total_commits"] == 0
    print("OK: reset")

def main():
    print("=== Agent Version Controller Tests ===\n")
    test_init()
    test_invalid_init()
    test_max_agents()
    test_commit()
    test_commit_nonexistent()
    test_max_versions()
    test_get_version()
    test_rollback()
    test_log()
    test_diff()
    test_branches()
    test_switch_branch()
    test_list_agents()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 18 TESTS PASSED ===")

if __name__ == "__main__":
    main()
