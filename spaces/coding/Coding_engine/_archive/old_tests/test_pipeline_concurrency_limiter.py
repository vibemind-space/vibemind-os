"""Test pipeline concurrency limiter -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_concurrency_limiter import PipelineConcurrencyLimiter


def test_set_limit():
    cl = PipelineConcurrencyLimiter()
    lid = cl.set_limit("deploy", 3)
    assert len(lid) > 0
    assert lid.startswith("pcl-")
    print("OK: set limit")


def test_get_limit():
    cl = PipelineConcurrencyLimiter()
    cl.set_limit("deploy", 3)
    lim = cl.get_limit("deploy")
    assert lim is not None
    assert lim["pipeline_id"] == "deploy"
    assert lim["max_concurrent"] == 3
    assert cl.get_limit("nonexistent") is None
    print("OK: get limit")


def test_acquire_slot():
    cl = PipelineConcurrencyLimiter()
    cl.set_limit("deploy", 2)
    assert cl.acquire_slot("deploy", "exec-1") is True
    assert cl.acquire_slot("deploy", "exec-2") is True
    assert cl.acquire_slot("deploy", "exec-3") is False  # At max
    print("OK: acquire slot")


def test_release_slot():
    cl = PipelineConcurrencyLimiter()
    cl.set_limit("deploy", 2)
    cl.acquire_slot("deploy", "exec-1")
    assert cl.release_slot("deploy", "exec-1") is True
    assert cl.release_slot("deploy", "exec-1") is False  # Not held
    print("OK: release slot")


def test_get_current_count():
    cl = PipelineConcurrencyLimiter()
    cl.set_limit("deploy", 5)
    cl.acquire_slot("deploy", "exec-1")
    cl.acquire_slot("deploy", "exec-2")
    assert cl.get_current_count("deploy") == 2
    print("OK: get current count")


def test_is_available():
    cl = PipelineConcurrencyLimiter()
    cl.set_limit("deploy", 1)
    assert cl.is_available("deploy") is True
    cl.acquire_slot("deploy", "exec-1")
    assert cl.is_available("deploy") is False
    print("OK: is available")


def test_get_active_executions():
    cl = PipelineConcurrencyLimiter()
    cl.set_limit("deploy", 5)
    cl.acquire_slot("deploy", "exec-1")
    cl.acquire_slot("deploy", "exec-2")
    active = cl.get_active_executions("deploy")
    assert "exec-1" in active
    assert "exec-2" in active
    print("OK: get active executions")


def test_remove_limit():
    cl = PipelineConcurrencyLimiter()
    cl.set_limit("deploy", 3)
    assert cl.remove_limit("deploy") is True
    assert cl.remove_limit("deploy") is False
    print("OK: remove limit")


def test_list_pipelines():
    cl = PipelineConcurrencyLimiter()
    cl.set_limit("deploy", 3)
    cl.set_limit("build", 5)
    pipes = cl.list_pipelines()
    assert "deploy" in pipes
    assert "build" in pipes
    print("OK: list pipelines")


def test_get_utilization():
    cl = PipelineConcurrencyLimiter()
    cl.set_limit("deploy", 4)
    cl.acquire_slot("deploy", "exec-1")
    cl.acquire_slot("deploy", "exec-2")
    util = cl.get_utilization("deploy")
    assert util == 0.5
    assert cl.get_utilization("nonexistent") == 0.0
    print("OK: get utilization")


def test_callbacks():
    cl = PipelineConcurrencyLimiter()
    fired = []
    cl.on_change("mon", lambda a, d: fired.append(a))
    cl.set_limit("deploy", 3)
    assert len(fired) >= 1
    assert cl.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cl = PipelineConcurrencyLimiter()
    cl.set_limit("deploy", 3)
    stats = cl.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cl = PipelineConcurrencyLimiter()
    cl.set_limit("deploy", 3)
    cl.reset()
    assert cl.list_pipelines() == []
    print("OK: reset")


def main():
    print("=== Pipeline Concurrency Limiter Tests ===\n")
    test_set_limit()
    test_get_limit()
    test_acquire_slot()
    test_release_slot()
    test_get_current_count()
    test_is_available()
    test_get_active_executions()
    test_remove_limit()
    test_list_pipelines()
    test_get_utilization()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
