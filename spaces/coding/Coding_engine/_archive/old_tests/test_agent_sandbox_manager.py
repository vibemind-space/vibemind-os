"""Test agent sandbox manager."""
import sys
sys.path.insert(0, ".")

from src.services.agent_sandbox_manager import AgentSandboxManager


def test_create():
    """Create and retrieve sandbox."""
    sm = AgentSandboxManager()
    sid = sm.create_sandbox("worker1", tags=["gpu"])
    assert sid.startswith("sbx-")

    sb = sm.get_sandbox(sid)
    assert sb is not None
    assert sb["agent"] == "worker1"
    assert sb["status"] == "active"

    assert sm.remove_sandbox(sid) is True
    assert sm.remove_sandbox(sid) is False
    print("OK: create")


def test_invalid_create():
    """Invalid create rejected."""
    sm = AgentSandboxManager()
    assert sm.create_sandbox("") == ""
    print("OK: invalid create")


def test_max_sandboxes():
    """Max sandboxes enforced."""
    sm = AgentSandboxManager(max_sandboxes=2)
    sm.create_sandbox("a")
    sm.create_sandbox("b")
    assert sm.create_sandbox("c") == ""
    print("OK: max sandboxes")


def test_agent_sandboxes():
    """Get sandboxes by agent."""
    sm = AgentSandboxManager()
    sm.create_sandbox("worker1")
    sm.create_sandbox("worker1")
    sm.create_sandbox("worker2")

    sbs = sm.get_agent_sandboxes("worker1")
    assert len(sbs) == 2
    assert sm.get_agent_sandboxes("nonexistent") == []
    print("OK: agent sandboxes")


def test_pause_resume():
    """Pause and resume sandbox."""
    sm = AgentSandboxManager()
    sid = sm.create_sandbox("w1")

    assert sm.pause_sandbox(sid) is True
    assert sm.get_sandbox(sid)["status"] == "paused"
    assert sm.pause_sandbox(sid) is False  # already paused

    assert sm.resume_sandbox(sid) is True
    assert sm.get_sandbox(sid)["status"] == "active"
    assert sm.resume_sandbox(sid) is False  # already active
    print("OK: pause resume")


def test_terminate():
    """Terminate sandbox."""
    sm = AgentSandboxManager()
    sid = sm.create_sandbox("w1")

    assert sm.terminate_sandbox(sid) is True
    assert sm.get_sandbox(sid)["status"] == "terminated"
    assert sm.terminate_sandbox(sid) is False  # already terminated
    print("OK: terminate")


def test_report_usage():
    """Report resource usage."""
    sm = AgentSandboxManager()
    sid = sm.create_sandbox("w1", cpu_limit=10.0, memory_limit=256)

    assert sm.report_usage(sid, cpu_used=5.0, memory_used=128) is True
    sb = sm.get_sandbox(sid)
    assert sb["cpu_used"] == 5.0
    assert sb["memory_used"] == 128
    print("OK: report usage")


def test_report_usage_terminated():
    """Report usage on terminated sandbox fails."""
    sm = AgentSandboxManager()
    sid = sm.create_sandbox("w1")
    sm.terminate_sandbox(sid)
    assert sm.report_usage(sid, cpu_used=1.0) is False
    print("OK: report usage terminated")


def test_limit_exceeded():
    """Limit exceeded fires event."""
    sm = AgentSandboxManager()
    fired = []
    sm.on_change("mon", lambda a, d: fired.append(a))

    sid = sm.create_sandbox("w1", cpu_limit=10.0, memory_limit=256)
    sm.report_usage(sid, cpu_used=20.0, memory_used=100)
    assert "limit_exceeded" in fired
    print("OK: limit exceeded")


def test_check_limits():
    """Check resource limits."""
    sm = AgentSandboxManager()
    sid = sm.create_sandbox("w1", cpu_limit=10.0, memory_limit=256)
    sm.report_usage(sid, cpu_used=5.0, memory_used=128)

    result = sm.check_limits(sid)
    assert result["cpu_ok"] is True
    assert result["memory_ok"] is True

    sm.report_usage(sid, cpu_used=15.0, memory_used=512)
    result = sm.check_limits(sid)
    assert result["cpu_ok"] is False
    assert result["memory_ok"] is False

    assert sm.check_limits("nonexistent")["exists"] is False
    print("OK: check limits")


def test_list_sandboxes():
    """List sandboxes with filters."""
    sm = AgentSandboxManager()
    sid1 = sm.create_sandbox("w1", tags=["gpu"])
    sid2 = sm.create_sandbox("w2")
    sm.pause_sandbox(sid1)

    all_sb = sm.list_sandboxes()
    assert len(all_sb) == 2

    by_status = sm.list_sandboxes(status="paused")
    assert len(by_status) == 1

    by_agent = sm.list_sandboxes(agent="w1")
    assert len(by_agent) == 1

    by_tag = sm.list_sandboxes(tag="gpu")
    assert len(by_tag) == 1
    print("OK: list sandboxes")


def test_active_count():
    """Active count is correct."""
    sm = AgentSandboxManager()
    sm.create_sandbox("w1")
    sm.create_sandbox("w2")
    sid3 = sm.create_sandbox("w3")
    sm.pause_sandbox(sid3)

    assert sm.get_active_count() == 2
    print("OK: active count")


def test_history():
    """History tracking."""
    sm = AgentSandboxManager()
    sid = sm.create_sandbox("w1")
    sm.pause_sandbox(sid)
    sm.resume_sandbox(sid)

    hist = sm.get_history()
    assert len(hist) == 3  # created, paused, resumed

    by_action = sm.get_history(action="paused")
    assert len(by_action) == 1

    by_agent = sm.get_history(agent="w1")
    assert len(by_agent) == 3

    limited = sm.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")


def test_callback():
    """Callback fires on events."""
    sm = AgentSandboxManager()
    fired = []
    sm.on_change("mon", lambda a, d: fired.append(a))

    sm.create_sandbox("w1")
    assert "sandbox_created" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    sm = AgentSandboxManager()
    assert sm.on_change("mon", lambda a, d: None) is True
    assert sm.on_change("mon", lambda a, d: None) is False
    assert sm.remove_callback("mon") is True
    assert sm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    sm = AgentSandboxManager()
    sid1 = sm.create_sandbox("w1")
    sm.create_sandbox("w2")
    sm.terminate_sandbox(sid1)

    stats = sm.get_stats()
    assert stats["current_sandboxes"] == 2
    assert stats["active_sandboxes"] == 1
    assert stats["total_created"] == 2
    assert stats["total_terminated"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    sm = AgentSandboxManager()
    sm.create_sandbox("w1")

    sm.reset()
    assert sm.list_sandboxes() == []
    stats = sm.get_stats()
    assert stats["current_sandboxes"] == 0
    assert stats["total_created"] == 0
    print("OK: reset")


def main():
    print("=== Agent Sandbox Manager Tests ===\n")
    test_create()
    test_invalid_create()
    test_max_sandboxes()
    test_agent_sandboxes()
    test_pause_resume()
    test_terminate()
    test_report_usage()
    test_report_usage_terminated()
    test_limit_exceeded()
    test_check_limits()
    test_list_sandboxes()
    test_active_count()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
