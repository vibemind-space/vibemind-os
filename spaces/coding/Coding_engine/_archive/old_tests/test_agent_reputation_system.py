"""Test agent reputation system."""
import sys
sys.path.insert(0, ".")

from src.services.agent_reputation_system import AgentReputationSystem


def test_create_profile():
    """Create and retrieve profile."""
    rs = AgentReputationSystem()
    pid = rs.create_profile("agent_alpha", initial_score=60.0,
                            tags=["code"])
    assert pid.startswith("rep-")

    p = rs.get_profile(pid)
    assert p is not None
    assert p["agent_name"] == "agent_alpha"
    assert p["reputation_score"] == 60.0
    assert p["level"] == "senior"

    assert rs.remove_profile(pid) is True
    assert rs.remove_profile(pid) is False
    print("OK: create profile")


def test_invalid_profile():
    """Invalid profile rejected."""
    rs = AgentReputationSystem()
    assert rs.create_profile("") == ""
    print("OK: invalid profile")


def test_duplicate_name():
    """Duplicate name rejected."""
    rs = AgentReputationSystem()
    rs.create_profile("agent_x")
    assert rs.create_profile("agent_x") == ""
    print("OK: duplicate name")


def test_max_profiles():
    """Max profiles enforced."""
    rs = AgentReputationSystem(max_profiles=2)
    rs.create_profile("a")
    rs.create_profile("b")
    assert rs.create_profile("c") == ""
    print("OK: max profiles")


def test_get_by_name():
    """Get profile by name."""
    rs = AgentReputationSystem()
    rs.create_profile("my_agent")

    p = rs.get_profile_by_name("my_agent")
    assert p is not None
    assert p["agent_name"] == "my_agent"
    assert rs.get_profile_by_name("nonexistent") is None
    print("OK: get by name")


def test_task_success():
    """Task success increases reputation."""
    rs = AgentReputationSystem()
    pid = rs.create_profile("agent", initial_score=50.0)

    eid = rs.record_task_success(pid, delta=5.0)
    assert eid.startswith("revt-")

    p = rs.get_profile(pid)
    assert p["reputation_score"] == 55.0
    assert p["total_tasks"] == 1
    assert p["successful_tasks"] == 1
    print("OK: task success")


def test_task_failure():
    """Task failure decreases reputation."""
    rs = AgentReputationSystem()
    pid = rs.create_profile("agent", initial_score=50.0)

    rs.record_task_failure(pid, delta=-5.0)
    p = rs.get_profile(pid)
    assert p["reputation_score"] == 45.0
    assert p["total_tasks"] == 1
    assert p["failed_tasks"] == 1
    print("OK: task failure")


def test_review():
    """Reviews affect reputation."""
    rs = AgentReputationSystem()
    pid = rs.create_profile("agent", initial_score=50.0)

    rs.record_review(pid, positive=True, delta=2.0)
    p = rs.get_profile(pid)
    assert p["reputation_score"] == 52.0
    assert p["total_reviews"] == 1
    assert p["positive_reviews"] == 1

    rs.record_review(pid, positive=False, delta=-1.0)
    p = rs.get_profile(pid)
    assert p["total_reviews"] == 2
    assert p["positive_reviews"] == 1
    print("OK: review")


def test_bonus_penalty():
    """Bonus and penalty affect reputation."""
    rs = AgentReputationSystem()
    pid = rs.create_profile("agent", initial_score=50.0)

    rs.record_bonus(pid, delta=10.0)
    assert rs.get_profile(pid)["reputation_score"] == 60.0

    rs.record_penalty(pid, delta=-5.0)
    assert rs.get_profile(pid)["reputation_score"] == 55.0
    print("OK: bonus penalty")


def test_score_clamping():
    """Score stays in 0-100 range."""
    rs = AgentReputationSystem()
    pid = rs.create_profile("agent", initial_score=95.0)

    rs.record_bonus(pid, delta=20.0)
    assert rs.get_profile(pid)["reputation_score"] == 100.0

    pid2 = rs.create_profile("agent2", initial_score=5.0)
    rs.record_penalty(pid2, delta=-20.0)
    assert rs.get_profile(pid2)["reputation_score"] == 0.0
    print("OK: score clamping")


def test_level_progression():
    """Levels change with score."""
    rs = AgentReputationSystem()
    pid = rs.create_profile("agent", initial_score=23.0)
    assert rs.get_profile(pid)["level"] == "novice"

    rs.record_bonus(pid, delta=5.0)  # 28
    assert rs.get_profile(pid)["level"] == "junior"

    rs.record_bonus(pid, delta=25.0)  # 53
    assert rs.get_profile(pid)["level"] == "senior"

    rs.record_bonus(pid, delta=25.0)  # 78
    assert rs.get_profile(pid)["level"] == "expert"

    rs.record_bonus(pid, delta=15.0)  # 93
    assert rs.get_profile(pid)["level"] == "master"
    print("OK: level progression")


def test_promotion_callback():
    """Callback fires on promotion."""
    rs = AgentReputationSystem()
    fired = []
    rs.on_change("mon", lambda a, d: fired.append(a))

    pid = rs.create_profile("agent", initial_score=48.0)
    rs.record_bonus(pid, delta=5.0)  # 53 -> senior promotion
    assert "agent_promoted" in fired
    print("OK: promotion callback")


def test_search_profiles():
    """Search profiles."""
    rs = AgentReputationSystem()
    rs.create_profile("a", initial_score=80.0, tags=["code"])
    rs.create_profile("b", initial_score=30.0)

    all_p = rs.search_profiles()
    assert len(all_p) == 2

    by_level = rs.search_profiles(level="expert")
    assert len(by_level) == 1

    by_tag = rs.search_profiles(tag="code")
    assert len(by_tag) == 1

    by_score = rs.search_profiles(min_score=50.0)
    assert len(by_score) == 1
    print("OK: search profiles")


def test_leaderboard():
    """Get leaderboard."""
    rs = AgentReputationSystem()
    rs.create_profile("low", initial_score=20.0)
    rs.create_profile("high", initial_score=90.0)
    rs.create_profile("mid", initial_score=50.0)

    board = rs.get_leaderboard(limit=2)
    assert len(board) == 2
    assert board[0]["agent_name"] == "high"
    assert board[1]["agent_name"] == "mid"
    print("OK: leaderboard")


def test_profile_events():
    """Get events for a profile."""
    rs = AgentReputationSystem()
    pid = rs.create_profile("agent")
    rs.record_task_success(pid)
    rs.record_task_failure(pid)
    rs.record_bonus(pid)

    all_e = rs.get_profile_events(pid)
    assert len(all_e) == 3

    by_type = rs.get_profile_events(pid, event_type="task_success")
    assert len(by_type) == 1
    print("OK: profile events")


def test_success_rate():
    """Get success rate."""
    rs = AgentReputationSystem()
    pid = rs.create_profile("agent")
    rs.record_task_success(pid)
    rs.record_task_success(pid)
    rs.record_task_failure(pid)

    rate = rs.get_success_rate(pid)
    assert rate["total_tasks"] == 3
    assert abs(rate["success_rate"] - 66.7) < 0.1
    print("OK: success rate")


def test_level_distribution():
    """Get level distribution."""
    rs = AgentReputationSystem()
    rs.create_profile("a", initial_score=10.0)  # novice
    rs.create_profile("b", initial_score=30.0)  # junior
    rs.create_profile("c", initial_score=60.0)  # senior

    dist = rs.get_level_distribution()
    assert dist["novice"] == 1
    assert dist["junior"] == 1
    assert dist["senior"] == 1
    assert dist["expert"] == 0
    print("OK: level distribution")


def test_remove_cascades():
    """Remove profile removes its events."""
    rs = AgentReputationSystem()
    pid = rs.create_profile("agent")
    rs.record_task_success(pid)

    rs.remove_profile(pid)
    assert rs.get_profile_events(pid) == []
    print("OK: remove cascades")


def test_callbacks():
    """Callback registration."""
    rs = AgentReputationSystem()
    assert rs.on_change("mon", lambda a, d: None) is True
    assert rs.on_change("mon", lambda a, d: None) is False
    assert rs.remove_callback("mon") is True
    assert rs.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    rs = AgentReputationSystem()
    pid = rs.create_profile("agent", initial_score=50.0)
    rs.record_task_success(pid)
    rs.record_task_failure(pid)

    stats = rs.get_stats()
    assert stats["total_profiles_created"] == 1
    assert stats["total_events"] == 2
    assert stats["current_profiles"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    rs = AgentReputationSystem()
    pid = rs.create_profile("agent")
    rs.record_task_success(pid)

    rs.reset()
    assert rs.search_profiles() == []
    stats = rs.get_stats()
    assert stats["current_profiles"] == 0
    print("OK: reset")


def main():
    print("=== Agent Reputation System Tests ===\n")
    test_create_profile()
    test_invalid_profile()
    test_duplicate_name()
    test_max_profiles()
    test_get_by_name()
    test_task_success()
    test_task_failure()
    test_review()
    test_bonus_penalty()
    test_score_clamping()
    test_level_progression()
    test_promotion_callback()
    test_search_profiles()
    test_leaderboard()
    test_profile_events()
    test_success_rate()
    test_level_distribution()
    test_remove_cascades()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
