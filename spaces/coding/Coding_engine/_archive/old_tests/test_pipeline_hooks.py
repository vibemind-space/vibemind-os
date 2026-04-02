"""Test pipeline hooks system."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_hooks import (
    PipelineHookManager,
    HookPoint,
)


def test_register_hook():
    """Register a hook."""
    mgr = PipelineHookManager()
    hid = mgr.register(
        "before_phase", "log_phase",
        callback=lambda ctx: f"Starting {ctx.get('phase', '?')}",
        priority=10,
        tags={"logging"},
    )

    assert hid.startswith("hook-")
    info = mgr.get_hook(hid)
    assert info is not None
    assert info["name"] == "log_phase"
    assert info["priority"] == 10
    assert "logging" in info["tags"]
    print("OK: register hook")


def test_fire_hooks():
    """Fire hooks and get results."""
    mgr = PipelineHookManager()
    results = []
    mgr.register("before_step", "tracker",
                  callback=lambda ctx: results.append(ctx.get("step")))

    mgr.fire("before_step", {"step": "lint"})
    assert results == ["lint"]
    print("OK: fire hooks")


def test_fire_priority_order():
    """Hooks fire in priority order (lower first)."""
    mgr = PipelineHookManager()
    order = []

    mgr.register("before_phase", "last", callback=lambda c: order.append("last"), priority=100)
    mgr.register("before_phase", "first", callback=lambda c: order.append("first"), priority=1)
    mgr.register("before_phase", "middle", callback=lambda c: order.append("middle"), priority=50)

    mgr.fire("before_phase", {})
    assert order == ["first", "middle", "last"]
    print("OK: fire priority order")


def test_fire_with_results():
    """Hook return values are captured."""
    mgr = PipelineHookManager()
    mgr.register("after_step", "get_result",
                  callback=lambda ctx: {"score": 95})

    results = mgr.fire("after_step", {})
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].result == {"score": 95}
    print("OK: fire with results")


def test_fire_nonexistent_point():
    """Firing at unregistered point returns empty."""
    mgr = PipelineHookManager()
    results = mgr.fire("nonexistent", {})
    assert results == []
    print("OK: fire nonexistent point")


def test_hook_error_handling():
    """Errors in hooks are caught and reported."""
    mgr = PipelineHookManager()
    mgr.register("on_error", "bad_hook",
                  callback=lambda ctx: 1 / 0)

    results = mgr.fire("on_error", {})
    assert len(results) == 1
    assert results[0].success is False
    assert "division by zero" in results[0].error
    print("OK: hook error handling")


def test_stop_on_failure():
    """Stop chain on first failure."""
    mgr = PipelineHookManager()
    executed = []

    mgr.register("before_step", "ok1", callback=lambda c: executed.append(1), priority=1)
    mgr.register("before_step", "fail", callback=lambda c: (_ for _ in ()).throw(ValueError("boom")), priority=2)
    mgr.register("before_step", "ok2", callback=lambda c: executed.append(3), priority=3)

    results = mgr.fire("before_step", {}, stop_on_failure=True)
    assert len(results) == 2  # Stopped after failure
    assert executed == [1]
    print("OK: stop on failure")


def test_conditional_hook():
    """Conditional hooks only fire when condition matches."""
    mgr = PipelineHookManager()
    results = []

    mgr.register("before_phase", "python_only",
                  callback=lambda c: results.append("python"),
                  condition=lambda c: c.get("language") == "python")

    mgr.fire("before_phase", {"language": "java"})
    assert results == []

    mgr.fire("before_phase", {"language": "python"})
    assert results == ["python"]
    print("OK: conditional hook")


def test_disabled_hook():
    """Disabled hooks are skipped."""
    mgr = PipelineHookManager()
    executed = []

    hid = mgr.register("before_step", "toggle",
                        callback=lambda c: executed.append(1))

    mgr.disable(hid)
    results = mgr.fire("before_step", {})
    assert executed == []
    assert results[0].skipped is True

    mgr.enable(hid)
    mgr.fire("before_step", {})
    assert executed == [1]
    print("OK: disabled hook")


def test_unregister_hook():
    """Remove a hook."""
    mgr = PipelineHookManager()
    hid = mgr.register("before_step", "temp", callback=lambda c: None)

    assert mgr.unregister(hid) is True
    assert mgr.get_hook(hid) is None
    assert mgr.unregister(hid) is False  # Already removed
    print("OK: unregister hook")


def test_list_hooks():
    """List hooks with filters."""
    mgr = PipelineHookManager()
    mgr.register("before_phase", "a", callback=lambda c: None, tags={"logging"})
    mgr.register("after_phase", "b", callback=lambda c: None, tags={"metrics"})
    mgr.register("before_phase", "c", callback=lambda c: None, tags={"logging", "audit"})

    all_hooks = mgr.list_hooks()
    assert len(all_hooks) == 3

    before = mgr.list_hooks(hook_point="before_phase")
    assert len(before) == 2

    logging = mgr.list_hooks(tags={"logging"})
    assert len(logging) == 2
    print("OK: list hooks")


def test_list_hook_points():
    """List all registered hook points."""
    mgr = PipelineHookManager()
    mgr.register("before_phase", "a", callback=lambda c: None)
    mgr.register("after_step", "b", callback=lambda c: None)

    points = mgr.list_hook_points()
    assert "before_phase" in points
    assert "after_step" in points
    print("OK: list hook points")


def test_hook_count():
    """Count hooks at a point."""
    mgr = PipelineHookManager()
    mgr.register("before_step", "a", callback=lambda c: None)
    mgr.register("before_step", "b", callback=lambda c: None)

    assert mgr.get_hook_count("before_step") == 2
    assert mgr.get_hook_count("nonexistent") == 0
    print("OK: hook count")


def test_fire_and_collect():
    """Fire and get summary."""
    mgr = PipelineHookManager()
    mgr.register("after_phase", "ok", callback=lambda c: "done")
    mgr.register("after_phase", "fail", callback=lambda c: 1 / 0)

    summary = mgr.fire_and_collect("after_phase", {})
    assert summary["total_hooks"] == 2
    assert summary["executed"] == 2
    assert summary["succeeded"] == 1
    assert summary["failed"] == 1
    assert len(summary["errors"]) == 1
    print("OK: fire and collect")


def test_hook_stats_tracking():
    """Hook invocation stats are tracked."""
    mgr = PipelineHookManager()
    hid = mgr.register("before_step", "tracked", callback=lambda c: None)

    mgr.fire("before_step", {})
    mgr.fire("before_step", {})
    mgr.fire("before_step", {})

    info = mgr.get_hook(hid)
    assert info["invocations"] == 3
    assert info["successes"] == 3
    assert info["failures"] == 0
    print("OK: hook stats tracking")


def test_stats():
    """Manager stats are accurate."""
    mgr = PipelineHookManager()
    mgr.register("before_step", "a", callback=lambda c: None)
    mgr.register("after_step", "b", callback=lambda c: 1 / 0)

    mgr.fire("before_step", {})
    mgr.fire("after_step", {})

    stats = mgr.get_stats()
    assert stats["total_hooks"] == 2
    assert stats["total_fired"] == 2
    assert stats["total_invocations"] == 2
    assert stats["total_errors"] == 1
    assert stats["hook_points"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    mgr = PipelineHookManager()
    mgr.register("before_step", "a", callback=lambda c: None)
    mgr.fire("before_step", {})

    mgr.reset()
    assert mgr.list_hooks() == []
    stats = mgr.get_stats()
    assert stats["total_hooks"] == 0
    assert stats["total_fired"] == 0
    print("OK: reset")


def test_multiple_hooks_same_point():
    """Multiple hooks at same point all fire."""
    mgr = PipelineHookManager()
    collected = []

    for i in range(5):
        mgr.register("on_checkpoint", f"hook_{i}",
                      callback=lambda c, idx=i: collected.append(idx))

    mgr.fire("on_checkpoint", {})
    assert len(collected) == 5
    print("OK: multiple hooks same point")


def main():
    print("=== Pipeline Hooks Tests ===\n")
    test_register_hook()
    test_fire_hooks()
    test_fire_priority_order()
    test_fire_with_results()
    test_fire_nonexistent_point()
    test_hook_error_handling()
    test_stop_on_failure()
    test_conditional_hook()
    test_disabled_hook()
    test_unregister_hook()
    test_list_hooks()
    test_list_hook_points()
    test_hook_count()
    test_fire_and_collect()
    test_hook_stats_tracking()
    test_stats()
    test_reset()
    test_multiple_hooks_same_point()
    print("\n=== ALL 18 TESTS PASSED ===")


if __name__ == "__main__":
    main()
