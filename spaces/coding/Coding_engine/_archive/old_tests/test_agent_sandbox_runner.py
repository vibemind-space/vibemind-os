"""Test agent sandbox runner."""
import sys
sys.path.insert(0, ".")

from src.services.agent_sandbox_runner import AgentSandboxRunner


def test_create_sandbox():
    """Create and retrieve sandbox."""
    sr = AgentSandboxRunner()
    sid = sr.create_sandbox("worker1", timeout_ms=5000, tags=["test"])
    assert sid.startswith("sbx-")

    s = sr.get_sandbox(sid)
    assert s is not None
    assert s["agent"] == "worker1"
    assert s["status"] == "idle"
    assert s["timeout_ms"] == 5000
    assert "test" in s["tags"]

    assert sr.remove_sandbox(sid) is True
    assert sr.remove_sandbox(sid) is False
    print("OK: create sandbox")


def test_invalid_create():
    """Invalid creation rejected."""
    sr = AgentSandboxRunner()
    assert sr.create_sandbox("") == ""
    print("OK: invalid create")


def test_max_sandboxes():
    """Max sandboxes enforced."""
    sr = AgentSandboxRunner(max_sandboxes=2)
    sr.create_sandbox("a")
    sr.create_sandbox("b")
    assert sr.create_sandbox("c") == ""
    print("OK: max sandboxes")


def test_run_no_fn():
    """Run without run_fn (dry run)."""
    sr = AgentSandboxRunner()
    sid = sr.create_sandbox("worker1")

    assert sr.run(sid, "build_app") is True
    s = sr.get_sandbox(sid)
    assert s["status"] == "completed"
    assert s["task"] == "build_app"
    assert s["total_runs"] == 1
    assert s["completed_at"] > 0
    print("OK: run no fn")


def test_run_with_fn():
    """Run with run_fn."""
    sr = AgentSandboxRunner()
    sid = sr.create_sandbox("worker1")

    def my_fn(task, config):
        return {"output": f"done-{task}"}

    assert sr.run(sid, "build", run_fn=my_fn) is True
    s = sr.get_sandbox(sid)
    assert s["status"] == "completed"
    assert s["result"]["output"] == "done-build"
    print("OK: run with fn")


def test_run_failure():
    """Run function failure."""
    sr = AgentSandboxRunner()
    sid = sr.create_sandbox("worker1")

    def bad_fn(task, config):
        raise RuntimeError("crash")

    assert sr.run(sid, "build", run_fn=bad_fn) is False
    s = sr.get_sandbox(sid)
    assert s["status"] == "failed"
    assert s["error"] == "crash"
    print("OK: run failure")


def test_run_timeout():
    """Run function timeout."""
    sr = AgentSandboxRunner()
    sid = sr.create_sandbox("worker1")

    def timeout_fn(task, config):
        raise TimeoutError("too slow")

    assert sr.run(sid, "build", run_fn=timeout_fn) is False
    s = sr.get_sandbox(sid)
    assert s["status"] == "timeout"
    assert s["error"] == "timeout"
    print("OK: run timeout")


def test_run_invalid():
    """Invalid run rejected."""
    sr = AgentSandboxRunner()
    sid = sr.create_sandbox("worker1")

    assert sr.run(sid, "") is False  # empty task
    assert sr.run("nonexistent", "build") is False  # bad sandbox
    print("OK: run invalid")


def test_run_while_running():
    """Can't run while already running (simulated)."""
    sr = AgentSandboxRunner()
    sid = sr.create_sandbox("worker1")
    # Force running state
    sr._sandboxes[sid].status = "running"
    assert sr.run(sid, "build") is False
    print("OK: run while running")


def test_reset_sandbox():
    """Reset sandbox to idle."""
    sr = AgentSandboxRunner()
    sid = sr.create_sandbox("worker1")
    sr.run(sid, "build")

    assert sr.reset_sandbox(sid) is True
    s = sr.get_sandbox(sid)
    assert s["status"] == "idle"
    assert s["task"] == ""
    assert s["result"] is None

    assert sr.reset_sandbox("nonexistent") is False
    print("OK: reset sandbox")


def test_reset_running():
    """Can't reset while running."""
    sr = AgentSandboxRunner()
    sid = sr.create_sandbox("worker1")
    sr._sandboxes[sid].status = "running"
    assert sr.reset_sandbox(sid) is False
    print("OK: reset running")


def test_get_sandboxes_for_agent():
    """Get sandboxes by agent."""
    sr = AgentSandboxRunner()
    sr.create_sandbox("w1")
    sr.create_sandbox("w1")
    sr.create_sandbox("w2")

    w1_sandboxes = sr.get_sandboxes_for_agent("w1")
    assert len(w1_sandboxes) == 2

    w2_sandboxes = sr.get_sandboxes_for_agent("w2")
    assert len(w2_sandboxes) == 1

    assert sr.get_sandboxes_for_agent("nonexistent") == []
    print("OK: get sandboxes for agent")


def test_list_sandboxes():
    """List sandboxes with filters."""
    sr = AgentSandboxRunner()
    sid1 = sr.create_sandbox("w1", tags=["ci"])
    sr.create_sandbox("w2")
    sr.run(sid1, "build")

    all_s = sr.list_sandboxes()
    assert len(all_s) == 2

    by_status = sr.list_sandboxes(status="completed")
    assert len(by_status) == 1

    by_agent = sr.list_sandboxes(agent="w1")
    assert len(by_agent) == 1

    by_tag = sr.list_sandboxes(tag="ci")
    assert len(by_tag) == 1
    print("OK: list sandboxes")


def test_get_running_idle():
    """Get running and idle sandboxes."""
    sr = AgentSandboxRunner()
    sr.create_sandbox("w1")
    sid2 = sr.create_sandbox("w2")
    sr._sandboxes[sid2].status = "running"

    assert len(sr.get_idle()) == 1
    assert len(sr.get_running()) == 1
    print("OK: get running idle")


def test_callback():
    """Callback fires on events."""
    sr = AgentSandboxRunner()
    fired = []
    sr.on_change("mon", lambda a, d: fired.append(a))

    sid = sr.create_sandbox("w1")
    assert "sandbox_created" in fired

    sr.run(sid, "build")
    assert "sandbox_started" in fired
    assert "sandbox_completed" in fired
    print("OK: callback")


def test_callback_failure():
    """Callback fires on failure."""
    sr = AgentSandboxRunner()
    fired = []
    sr.on_change("mon", lambda a, d: fired.append(a))

    sid = sr.create_sandbox("w1")
    sr.run(sid, "build", run_fn=lambda t, c: (_ for _ in ()).throw(RuntimeError("x")))
    assert "sandbox_failed" in fired
    print("OK: callback failure")


def test_callbacks():
    """Callback registration."""
    sr = AgentSandboxRunner()
    assert sr.on_change("mon", lambda a, d: None) is True
    assert sr.on_change("mon", lambda a, d: None) is False
    assert sr.remove_callback("mon") is True
    assert sr.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    sr = AgentSandboxRunner()
    sid1 = sr.create_sandbox("w1")
    sr.run(sid1, "build")
    sid2 = sr.create_sandbox("w2")
    sr.run(sid2, "test", run_fn=lambda t, c: (_ for _ in ()).throw(RuntimeError("x")))

    stats = sr.get_stats()
    assert stats["total_created"] == 2
    assert stats["total_runs"] == 2
    assert stats["total_failures"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    sr = AgentSandboxRunner()
    sr.create_sandbox("w1")

    sr.reset()
    assert sr.list_sandboxes() == []
    stats = sr.get_stats()
    assert stats["current_sandboxes"] == 0
    print("OK: reset")


def main():
    print("=== Agent Sandbox Runner Tests ===\n")
    test_create_sandbox()
    test_invalid_create()
    test_max_sandboxes()
    test_run_no_fn()
    test_run_with_fn()
    test_run_failure()
    test_run_timeout()
    test_run_invalid()
    test_run_while_running()
    test_reset_sandbox()
    test_reset_running()
    test_get_sandboxes_for_agent()
    test_list_sandboxes()
    test_get_running_idle()
    test_callback()
    test_callback_failure()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 19 TESTS PASSED ===")


if __name__ == "__main__":
    main()
