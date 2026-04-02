"""Tests for AgentTimeoutManager."""

import time
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "services"))

from agent_timeout_manager import AgentTimeoutManager


def test_set_timeout():
    mgr = AgentTimeoutManager()
    tid = mgr.set_timeout("agent-1", "compute", 30.0)
    assert tid.startswith("atm-"), f"Expected atm- prefix, got {tid}"
    assert len(tid) > 4
    # Invalid inputs return empty string
    assert mgr.set_timeout("", "op", 10.0) == ""
    assert mgr.set_timeout("a", "", 10.0) == ""
    assert mgr.set_timeout("a", "op", -1.0) == ""
    print("  PASSED test_set_timeout")


def test_is_timed_out_no():
    mgr = AgentTimeoutManager()
    mgr.set_timeout("agent-1", "compute", 60.0)
    assert not mgr.is_timed_out("agent-1", "compute"), "Should not be timed out yet"
    # Non-existent returns False
    assert not mgr.is_timed_out("agent-1", "nonexistent")
    assert not mgr.is_timed_out("no-agent", "compute")
    print("  PASSED test_is_timed_out_no")


def test_is_timed_out_yes():
    mgr = AgentTimeoutManager()
    mgr.set_timeout("agent-1", "compute", 0.05)
    time.sleep(0.1)
    assert mgr.is_timed_out("agent-1", "compute"), "Should be timed out"
    print("  PASSED test_is_timed_out_yes")


def test_get_remaining():
    mgr = AgentTimeoutManager()
    mgr.set_timeout("agent-1", "compute", 60.0)
    rem = mgr.get_remaining("agent-1", "compute")
    assert 50.0 < rem <= 60.0, f"Remaining should be ~60s, got {rem}"
    # Not found returns 0.0
    assert mgr.get_remaining("agent-1", "nope") == 0.0
    assert mgr.get_remaining("nope", "compute") == 0.0
    # Expired returns 0.0
    mgr.set_timeout("agent-2", "op", 0.05)
    time.sleep(0.1)
    assert mgr.get_remaining("agent-2", "op") == 0.0
    print("  PASSED test_get_remaining")


def test_cancel_timeout():
    mgr = AgentTimeoutManager()
    mgr.set_timeout("agent-1", "compute", 30.0)
    assert mgr.cancel_timeout("agent-1", "compute") is True
    assert mgr.cancel_timeout("agent-1", "compute") is False  # already removed
    assert mgr.cancel_timeout("no-agent", "op") is False
    assert mgr.get_timeout_count("agent-1") == 0
    print("  PASSED test_cancel_timeout")


def test_get_timeouts():
    mgr = AgentTimeoutManager()
    mgr.set_timeout("agent-1", "compute", 30.0)
    mgr.set_timeout("agent-1", "network", 60.0)
    touts = mgr.get_timeouts("agent-1")
    assert len(touts) == 2
    ops = {t["operation"] for t in touts}
    assert ops == {"compute", "network"}
    # Empty agent
    assert mgr.get_timeouts("no-agent") == []
    print("  PASSED test_get_timeouts")


def test_get_timeout_count():
    mgr = AgentTimeoutManager()
    mgr.set_timeout("agent-1", "compute", 30.0)
    mgr.set_timeout("agent-1", "network", 60.0)
    mgr.set_timeout("agent-2", "disk", 10.0)
    assert mgr.get_timeout_count("agent-1") == 2
    assert mgr.get_timeout_count("agent-2") == 1
    assert mgr.get_timeout_count() == 3
    assert mgr.get_timeout_count("no-agent") == 0
    print("  PASSED test_get_timeout_count")


def test_list_agents():
    mgr = AgentTimeoutManager()
    mgr.set_timeout("agent-1", "compute", 30.0)
    mgr.set_timeout("agent-2", "network", 60.0)
    agents = mgr.list_agents()
    assert set(agents) == {"agent-1", "agent-2"}
    print("  PASSED test_list_agents")


def test_callbacks():
    mgr = AgentTimeoutManager()
    events = []
    mgr.on_change("tracker", lambda action, detail: events.append((action, detail)))
    mgr.set_timeout("agent-1", "compute", 30.0)
    assert len(events) == 1
    assert events[0][0] == "timeout_set"
    assert events[0][1]["agent_id"] == "agent-1"

    mgr.cancel_timeout("agent-1", "compute")
    assert len(events) == 2
    assert events[1][0] == "timeout_cancelled"

    # remove_callback
    assert mgr.remove_callback("tracker") is True
    assert mgr.remove_callback("tracker") is False
    mgr.set_timeout("agent-2", "op", 10.0)
    assert len(events) == 2  # no new events
    print("  PASSED test_callbacks")


def test_stats():
    mgr = AgentTimeoutManager()
    mgr.set_timeout("agent-1", "compute", 60.0)
    mgr.set_timeout("agent-1", "network", 60.0)
    mgr.set_timeout("agent-2", "disk", 60.0)
    mgr.cancel_timeout("agent-2", "disk")

    stats = mgr.get_stats()
    assert stats["total_timeouts"] == 2
    assert stats["total_agents"] == 1
    assert stats["total_set"] == 3
    assert stats["total_cancelled"] == 1
    assert stats["max_entries"] == 10000
    print("  PASSED test_stats")


def test_reset():
    mgr = AgentTimeoutManager()
    mgr.set_timeout("agent-1", "compute", 30.0)
    mgr.on_change("cb", lambda a, d: None)
    mgr.reset()
    assert mgr.get_timeout_count() == 0
    assert mgr.list_agents() == []
    stats = mgr.get_stats()
    assert stats["total_set"] == 0
    assert stats["total_cancelled"] == 0
    assert stats["callbacks"] == 0
    print("  PASSED test_reset")


if __name__ == "__main__":
    tests = [
        test_set_timeout,
        test_is_timed_out_no,
        test_is_timed_out_yes,
        test_get_remaining,
        test_cancel_timeout,
        test_get_timeouts,
        test_get_timeout_count,
        test_list_agents,
        test_callbacks,
        test_stats,
        test_reset,
    ]
    for t in tests:
        t()
    print(f"=== ALL {len(tests)} TESTS PASSED ===")
