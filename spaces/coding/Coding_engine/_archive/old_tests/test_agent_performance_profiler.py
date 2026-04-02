"""Test agent performance profiler -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.agent_performance_profiler import AgentPerformanceProfiler


def test_start_profile():
    pp = AgentPerformanceProfiler()
    pid = pp.start_profile("agent-1", "build")
    assert len(pid) > 0
    assert pid.startswith("app2-")
    print("OK: start profile")


def test_end_profile():
    pp = AgentPerformanceProfiler()
    pid = pp.start_profile("agent-1", "build")
    elapsed = pp.end_profile(pid)
    assert elapsed >= 0.0
    print("OK: end profile")


def test_get_average_time():
    pp = AgentPerformanceProfiler()
    p1 = pp.start_profile("agent-1", "build")
    pp.end_profile(p1)
    p2 = pp.start_profile("agent-1", "build")
    pp.end_profile(p2)
    avg = pp.get_average_time("agent-1", "build")
    assert avg >= 0.0
    print("OK: get average time")


def test_get_profile_count():
    pp = AgentPerformanceProfiler()
    p1 = pp.start_profile("agent-1", "build")
    pp.end_profile(p1)
    p2 = pp.start_profile("agent-1", "test")
    pp.end_profile(p2)
    count = pp.get_profile_count("agent-1")
    assert count == 2
    print("OK: get profile count")


def test_get_summary():
    pp = AgentPerformanceProfiler()
    p1 = pp.start_profile("agent-1", "build")
    pp.end_profile(p1)
    summary = pp.get_summary("agent-1")
    assert summary["total_profiles"] >= 1
    print("OK: get summary")


def test_list_agents():
    pp = AgentPerformanceProfiler()
    pp.start_profile("agent-1", "build")
    pp.start_profile("agent-2", "test")
    agents = pp.list_agents()
    assert "agent-1" in agents
    assert "agent-2" in agents
    print("OK: list agents")


def test_callbacks():
    pp = AgentPerformanceProfiler()
    fired = []
    pp.on_change("mon", lambda a, d: fired.append(a))
    pp.start_profile("agent-1", "build")
    assert len(fired) >= 1
    assert pp.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    pp = AgentPerformanceProfiler()
    pp.start_profile("agent-1", "build")
    stats = pp.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    pp = AgentPerformanceProfiler()
    pp.start_profile("agent-1", "build")
    pp.reset()
    assert pp.get_total_profiles() == 0
    print("OK: reset")


def main():
    print("=== Agent Performance Profiler Tests ===\n")
    test_start_profile()
    test_end_profile()
    test_get_average_time()
    test_get_profile_count()
    test_get_summary()
    test_list_agents()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
