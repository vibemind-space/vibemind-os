"""Test pipeline scheduler."""
import sys
import time
sys.path.insert(0, ".")

from src.services.pipeline_scheduler import (
    PipelineScheduler,
    ScheduleType,
    TriggerStatus,
)


def test_create_schedule():
    """Create a schedule."""
    sched = PipelineScheduler()
    sid = sched.create_schedule("nightly_build", "build_all", schedule_type="interval",
                                interval_seconds=3600, description="Hourly build")
    assert sid is not None
    assert sid.startswith("sched-")

    # Duplicate name fails
    assert sched.create_schedule("nightly_build", "build_all") is None

    info = sched.get_schedule("nightly_build")
    assert info is not None
    assert info["name"] == "nightly_build"
    assert info["action"] == "build_all"
    assert info["schedule_type"] == "interval"
    assert info["enabled"] is True
    print("OK: create schedule")


def test_delete_schedule():
    """Delete a schedule."""
    sched = PipelineScheduler()
    sched.create_schedule("temp", "do_thing")
    assert sched.delete_schedule("temp") is True
    assert sched.get_schedule("temp") is None
    assert sched.delete_schedule("temp") is False
    print("OK: delete schedule")


def test_enable_disable():
    """Enable and disable schedules."""
    sched = PipelineScheduler()
    sched.create_schedule("job", "action")

    assert sched.disable_schedule("job") is True
    assert sched.get_schedule("job")["enabled"] is False

    assert sched.enable_schedule("job") is True
    assert sched.get_schedule("job")["enabled"] is True

    assert sched.disable_schedule("nope") is False
    print("OK: enable disable")


def test_list_schedules():
    """List schedules with filters."""
    sched = PipelineScheduler()
    sched.create_schedule("a", "build", schedule_type="interval", interval_seconds=60)
    sched.create_schedule("b", "test", schedule_type="once", run_at=time.time() + 100)
    sched.create_schedule("c", "deploy", schedule_type="interval", interval_seconds=120,
                          tags={"prod"})

    all_s = sched.list_schedules()
    assert len(all_s) == 3

    intervals = sched.list_schedules(schedule_type="interval")
    assert len(intervals) == 2

    tagged = sched.list_schedules(tags={"prod"})
    assert len(tagged) == 1
    assert tagged[0]["name"] == "c"

    sched.disable_schedule("a")
    enabled = sched.list_schedules(enabled_only=True)
    assert len(enabled) == 2
    print("OK: list schedules")


def test_register_action():
    """Register and list action handlers."""
    sched = PipelineScheduler()
    results = []
    sched.register_action("build", lambda ctx: results.append("built"))
    sched.register_action("test", lambda ctx: results.append("tested"))

    actions = sched.list_actions()
    assert actions == ["build", "test"]

    assert sched.unregister_action("test") is True
    assert sched.unregister_action("test") is False
    assert sched.list_actions() == ["build"]
    print("OK: register action")


def test_trigger_with_handler():
    """Trigger a schedule that has an action handler."""
    sched = PipelineScheduler()
    results = []
    sched.register_action("build", lambda ctx: results.append(ctx.get("project", "default")))
    sched.create_schedule("job", "build", context={"project": "myapp"})

    tid = sched.trigger("job")
    assert tid is not None
    assert tid.startswith("trig-")
    assert results == ["myapp"]

    info = sched.get_schedule("job")
    assert info["trigger_count"] == 1
    assert info["last_triggered"] > 0
    print("OK: trigger with handler")


def test_trigger_without_handler():
    """Trigger without handler still records."""
    sched = PipelineScheduler()
    sched.create_schedule("job", "unknown_action")

    tid = sched.trigger("job")
    assert tid is not None

    history = sched.get_trigger_history("job")
    assert len(history) == 1
    assert history[0]["status"] == "completed"
    print("OK: trigger without handler")


def test_trigger_handler_failure():
    """Failed handler records failure."""
    sched = PipelineScheduler()
    sched.register_action("fail", lambda ctx: 1 / 0)
    sched.create_schedule("job", "fail")

    tid = sched.trigger("job")
    assert tid is not None

    history = sched.get_trigger_history("job")
    assert history[0]["status"] == "failed"
    assert "division" in history[0]["error"].lower()
    print("OK: trigger handler failure")


def test_trigger_nonexistent():
    """Trigger nonexistent schedule returns None."""
    sched = PipelineScheduler()
    assert sched.trigger("nope") is None
    print("OK: trigger nonexistent")


def test_trigger_context_override():
    """Override context when triggering."""
    sched = PipelineScheduler()
    results = []
    sched.register_action("build", lambda ctx: results.append(ctx.get("env")))
    sched.create_schedule("job", "build", context={"env": "dev"})

    sched.trigger("job", context_override={"env": "prod"})
    assert results == ["prod"]
    print("OK: trigger context override")


def test_max_triggers():
    """Schedule respects max_triggers limit."""
    sched = PipelineScheduler()
    sched.create_schedule("limited", "action", max_triggers=2)

    assert sched.trigger("limited") is not None
    assert sched.trigger("limited") is not None
    assert sched.trigger("limited") is None  # Over limit
    print("OK: max triggers")


def test_skip_trigger():
    """Record a skipped trigger."""
    sched = PipelineScheduler()
    sched.create_schedule("job", "build")

    tid = sched.skip_trigger("job", reason="System busy")
    assert tid is not None

    history = sched.get_trigger_history("job")
    assert len(history) == 1
    assert history[0]["status"] == "skipped"
    assert history[0]["error"] == "System busy"
    print("OK: skip trigger")


def test_check_due_interval():
    """Check due schedules for interval type."""
    sched = PipelineScheduler()
    sched.create_schedule("fast", "action", schedule_type="interval", interval_seconds=0.1)

    # Never triggered → should be due immediately
    due = sched.check_due()
    assert "fast" in due

    sched.trigger("fast")
    # Just triggered → not due
    due2 = sched.check_due()
    assert "fast" not in due2

    time.sleep(0.15)
    # Enough time passed → due again
    due3 = sched.check_due()
    assert "fast" in due3
    print("OK: check due interval")


def test_check_due_once():
    """Check due for one-time schedule."""
    sched = PipelineScheduler()
    future = time.time() + 100
    sched.create_schedule("future_job", "action", schedule_type="once", run_at=future)

    # Not yet → not due
    due = sched.check_due()
    assert "future_job" not in due

    # Past run_at → due
    past = time.time() - 1
    sched.create_schedule("past_job", "action", schedule_type="once", run_at=past)
    due2 = sched.check_due()
    assert "past_job" in due2

    # After triggering → not due again
    sched.trigger("past_job")
    due3 = sched.check_due()
    assert "past_job" not in due3
    print("OK: check due once")


def test_once_auto_disable():
    """One-time schedule auto-disables after trigger."""
    sched = PipelineScheduler()
    sched.create_schedule("once_job", "action", schedule_type="once", run_at=time.time() - 1)

    sched.trigger("once_job")
    info = sched.get_schedule("once_job")
    assert info["enabled"] is False
    print("OK: once auto disable")


def test_check_due_disabled():
    """Disabled schedules are not due."""
    sched = PipelineScheduler()
    sched.create_schedule("job", "action", schedule_type="interval", interval_seconds=0.01)
    sched.disable_schedule("job")

    due = sched.check_due()
    assert "job" not in due
    print("OK: check due disabled")


def test_trigger_history():
    """Get trigger history with filters."""
    sched = PipelineScheduler()
    sched.register_action("build", lambda ctx: "ok")
    sched.register_action("fail", lambda ctx: 1 / 0)
    sched.create_schedule("good_job", "build")
    sched.create_schedule("bad_job", "fail")

    sched.trigger("good_job")
    sched.trigger("bad_job")
    sched.trigger("good_job")

    all_h = sched.get_trigger_history()
    assert len(all_h) == 3

    good_h = sched.get_trigger_history(name="good_job")
    assert len(good_h) == 2

    failed_h = sched.get_trigger_history(status="failed")
    assert len(failed_h) == 1
    print("OK: trigger history")


def test_get_last_trigger():
    """Get most recent trigger for a schedule."""
    sched = PipelineScheduler()
    sched.create_schedule("job", "action")

    assert sched.get_last_trigger("job") is None

    sched.trigger("job")
    sched.trigger("job")

    last = sched.get_last_trigger("job")
    assert last is not None
    assert last["status"] == "completed"
    print("OK: get last trigger")


def test_stats():
    """Stats are accurate."""
    sched = PipelineScheduler()
    sched.register_action("ok", lambda ctx: "done")
    sched.register_action("fail", lambda ctx: 1 / 0)
    sched.create_schedule("a", "ok")
    sched.create_schedule("b", "fail")

    sched.trigger("a")
    sched.trigger("b")
    sched.skip_trigger("a")

    stats = sched.get_stats()
    assert stats["total_created"] == 2
    assert stats["total_triggered"] == 2
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    assert stats["total_skipped"] == 1
    assert stats["total_schedules"] == 2
    assert stats["registered_actions"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    sched = PipelineScheduler()
    sched.create_schedule("job", "action")
    sched.trigger("job")
    sched.register_action("build", lambda ctx: None)

    sched.reset()
    assert sched.list_schedules() == []
    assert sched.get_trigger_history() == []
    assert sched.list_actions() == []
    stats = sched.get_stats()
    assert stats["total_schedules"] == 0
    print("OK: reset")


def test_history_pruning():
    """History is pruned when over limit."""
    sched = PipelineScheduler(max_history=5)
    sched.create_schedule("job", "action")

    for _ in range(10):
        sched.trigger("job")

    history = sched.get_trigger_history(limit=100)
    assert len(history) <= 5
    print("OK: history pruning")


def main():
    print("=== Pipeline Scheduler Tests ===\n")
    test_create_schedule()
    test_delete_schedule()
    test_enable_disable()
    test_list_schedules()
    test_register_action()
    test_trigger_with_handler()
    test_trigger_without_handler()
    test_trigger_handler_failure()
    test_trigger_nonexistent()
    test_trigger_context_override()
    test_max_triggers()
    test_skip_trigger()
    test_check_due_interval()
    test_check_due_once()
    test_once_auto_disable()
    test_check_due_disabled()
    test_trigger_history()
    test_get_last_trigger()
    test_stats()
    test_reset()
    test_history_pruning()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
