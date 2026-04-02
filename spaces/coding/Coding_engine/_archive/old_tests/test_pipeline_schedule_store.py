"""Test pipeline schedule store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_schedule_store import PipelineScheduleStore


def test_create_schedule():
    ss = PipelineScheduleStore()
    sid = ss.create_schedule("deploy", interval_seconds=3600, metadata={"env": "prod"}, tags=["ci"])
    assert len(sid) > 0
    assert ss.create_schedule("deploy", interval_seconds=1800) == ""  # dup
    print("OK: create schedule")


def test_get_schedule():
    ss = PipelineScheduleStore()
    sid = ss.create_schedule("deploy", interval_seconds=3600)
    s = ss.get_schedule(sid)
    assert s is not None
    assert s["pipeline_name"] == "deploy"
    assert s["interval_seconds"] == 3600
    print("OK: get schedule")


def test_enable_disable():
    ss = PipelineScheduleStore()
    sid = ss.create_schedule("deploy", interval_seconds=3600)
    assert ss.disable_schedule(sid) is True
    s = ss.get_schedule(sid)
    assert s["enabled"] is False
    assert ss.enable_schedule(sid) is True
    s = ss.get_schedule(sid)
    assert s["enabled"] is True
    print("OK: enable/disable")


def test_mark_run():
    ss = PipelineScheduleStore()
    sid = ss.create_schedule("deploy", interval_seconds=60)
    assert ss.mark_run(sid) is True
    s = ss.get_schedule(sid)
    assert s["last_run"] is not None
    print("OK: mark run")


def test_get_due_schedules():
    ss = PipelineScheduleStore()
    # Create schedule with 0 interval so it's immediately due
    sid = ss.create_schedule("deploy", interval_seconds=0)
    import time
    time.sleep(0.01)
    due = ss.get_due_schedules()
    assert len(due) >= 1
    print("OK: get due schedules")


def test_get_schedule_by_pipeline():
    ss = PipelineScheduleStore()
    ss.create_schedule("deploy", interval_seconds=3600)
    s = ss.get_schedule_by_pipeline("deploy")
    assert s is not None
    assert s["pipeline_name"] == "deploy"
    print("OK: get schedule by pipeline")


def test_list_schedules():
    ss = PipelineScheduleStore()
    sid1 = ss.create_schedule("deploy", interval_seconds=3600)
    sid2 = ss.create_schedule("test", interval_seconds=1800)
    ss.disable_schedule(sid2)
    all_s = ss.list_schedules()
    assert len(all_s) == 2
    enabled_s = ss.list_schedules(enabled_only=True)
    assert len(enabled_s) == 1
    print("OK: list schedules")


def test_remove_schedule():
    ss = PipelineScheduleStore()
    sid = ss.create_schedule("temp", interval_seconds=60)
    assert ss.remove_schedule(sid) is True
    assert ss.remove_schedule(sid) is False
    print("OK: remove schedule")


def test_callbacks():
    ss = PipelineScheduleStore()
    fired = []
    ss.on_change("mon", lambda a, d: fired.append(a))
    ss.create_schedule("deploy", interval_seconds=3600)
    assert len(fired) >= 1
    assert ss.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ss = PipelineScheduleStore()
    ss.create_schedule("deploy", interval_seconds=3600)
    stats = ss.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ss = PipelineScheduleStore()
    ss.create_schedule("deploy", interval_seconds=3600)
    ss.reset()
    assert ss.list_schedules() == []
    print("OK: reset")


def main():
    print("=== Pipeline Schedule Store Tests ===\n")
    test_create_schedule()
    test_get_schedule()
    test_enable_disable()
    test_mark_run()
    test_get_due_schedules()
    test_get_schedule_by_pipeline()
    test_list_schedules()
    test_remove_schedule()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
