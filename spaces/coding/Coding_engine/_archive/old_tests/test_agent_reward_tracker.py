"""Test agent reward tracker -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_reward_tracker import AgentRewardTracker


def test_grant_reward():
    rt = AgentRewardTracker()
    rid = rt.grant_reward("agent-1", "completion", 10.0, reason="task done")
    assert len(rid) > 0
    assert rid.startswith("arw-")
    print("OK: grant reward")


def test_get_reward():
    rt = AgentRewardTracker()
    rid = rt.grant_reward("agent-1", "completion", 10.0)
    reward = rt.get_reward(rid)
    assert reward is not None
    assert reward["agent_id"] == "agent-1"
    assert reward["reward_type"] == "completion"
    assert reward["amount"] == 10.0
    assert rt.get_reward("nonexistent") is None
    print("OK: get reward")


def test_get_agent_rewards():
    rt = AgentRewardTracker()
    rt.grant_reward("agent-1", "completion", 10.0)
    rt.grant_reward("agent-1", "bonus", 5.0)
    rt.grant_reward("agent-2", "completion", 8.0)
    rewards = rt.get_agent_rewards("agent-1")
    assert len(rewards) == 2
    print("OK: get agent rewards")


def test_get_total_rewards():
    rt = AgentRewardTracker()
    rt.grant_reward("agent-1", "completion", 10.0)
    rt.grant_reward("agent-1", "bonus", 5.0)
    total = rt.get_total_rewards("agent-1")
    assert total == 15.0
    assert rt.get_total_rewards("agent-999") == 0.0
    print("OK: get total rewards")


def test_get_reward_by_type():
    rt = AgentRewardTracker()
    rt.grant_reward("agent-1", "completion", 10.0)
    rt.grant_reward("agent-2", "completion", 8.0)
    rt.grant_reward("agent-1", "bonus", 5.0)
    rewards = rt.get_reward_by_type("completion")
    assert len(rewards) == 2
    print("OK: get reward by type")


def test_get_leaderboard():
    rt = AgentRewardTracker()
    rt.grant_reward("agent-1", "completion", 10.0)
    rt.grant_reward("agent-1", "bonus", 5.0)
    rt.grant_reward("agent-2", "completion", 20.0)
    board = rt.get_leaderboard(top_n=2)
    assert len(board) == 2
    assert board[0]["agent_id"] == "agent-2"
    assert board[0]["total"] == 20.0
    print("OK: get leaderboard")


def test_list_agents():
    rt = AgentRewardTracker()
    rt.grant_reward("agent-1", "completion", 10.0)
    rt.grant_reward("agent-2", "bonus", 5.0)
    agents = rt.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_list_reward_types():
    rt = AgentRewardTracker()
    rt.grant_reward("agent-1", "completion", 10.0)
    rt.grant_reward("agent-1", "bonus", 5.0)
    types = rt.list_reward_types()
    assert "completion" in types
    assert "bonus" in types
    print("OK: list reward types")


def test_callbacks():
    rt = AgentRewardTracker()
    fired = []
    rt.on_change("mon", lambda a, d: fired.append(a))
    rt.grant_reward("agent-1", "completion", 10.0)
    assert len(fired) >= 1
    assert rt.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rt = AgentRewardTracker()
    rt.grant_reward("agent-1", "completion", 10.0)
    stats = rt.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rt = AgentRewardTracker()
    rt.grant_reward("agent-1", "completion", 10.0)
    rt.reset()
    assert rt.get_reward_count() == 0
    print("OK: reset")


def main():
    print("=== Agent Reward Tracker Tests ===\n")
    test_grant_reward()
    test_get_reward()
    test_get_agent_rewards()
    test_get_total_rewards()
    test_get_reward_by_type()
    test_get_leaderboard()
    test_list_agents()
    test_list_reward_types()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
