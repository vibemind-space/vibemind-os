"""Test pipeline priority scheduler -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_priority_scheduler import PipelinePriorityScheduler


def test_schedule():
    ps = PipelinePriorityScheduler()
    sid = ps.schedule("pipeline-1", priority=5)
    assert len(sid) > 0
    assert sid.startswith("pps-")
    print("OK: schedule")


def test_get_next():
    ps = PipelinePriorityScheduler()
    ps.schedule("pipeline-1", priority=1)
    ps.schedule("pipeline-2", priority=10)
    nxt = ps.get_next()
    assert nxt is not None
    assert nxt["pipeline_id"] == "pipeline-2"  # higher priority
    print("OK: get next")


def test_mark_running():
    ps = PipelinePriorityScheduler()
    sid = ps.schedule("pipeline-1", priority=5)
    assert ps.mark_running(sid) is True
    sched = ps.get_schedule(sid)
    assert sched is not None
    print("OK: mark running")


def test_mark_completed():
    ps = PipelinePriorityScheduler()
    sid = ps.schedule("pipeline-1", priority=5)
    ps.mark_running(sid)
    assert ps.mark_completed(sid) is True
    print("OK: mark completed")


def test_mark_failed():
    ps = PipelinePriorityScheduler()
    sid = ps.schedule("pipeline-1", priority=5)
    ps.mark_running(sid)
    assert ps.mark_failed(sid) is True
    print("OK: mark failed")


def test_get_schedule():
    ps = PipelinePriorityScheduler()
    sid = ps.schedule("pipeline-1", priority=7)
    sched = ps.get_schedule(sid)
    assert sched is not None
    assert sched["pipeline_id"] == "pipeline-1"
    assert sched["priority"] == 7
    assert ps.get_schedule("nonexistent") is None
    print("OK: get schedule")


def test_dependencies():
    ps = PipelinePriorityScheduler()
    s1 = ps.schedule("pipeline-1", priority=5)
    s2 = ps.schedule("pipeline-2", priority=10, depends_on=[s1])
    # pipeline-2 has higher priority but depends on s1
    nxt = ps.get_next()
    assert nxt["pipeline_id"] == "pipeline-1"  # pipeline-1 first (no deps)
    ps.mark_running(s1)
    ps.mark_completed(s1)
    nxt2 = ps.get_next()
    assert nxt2["pipeline_id"] == "pipeline-2"  # now pipeline-2 is ready
    print("OK: dependencies")


def test_get_pending_count():
    ps = PipelinePriorityScheduler()
    ps.schedule("pipeline-1", priority=5)
    ps.schedule("pipeline-2", priority=3)
    assert ps.get_pending_count() == 2
    print("OK: get pending count")


def test_list_pipelines():
    ps = PipelinePriorityScheduler()
    ps.schedule("pipeline-1")
    ps.schedule("pipeline-2")
    pipelines = ps.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    ps = PipelinePriorityScheduler()
    fired = []
    ps.on_change("mon", lambda a, d: fired.append(a))
    ps.schedule("pipeline-1")
    assert len(fired) >= 1
    assert ps.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ps = PipelinePriorityScheduler()
    ps.schedule("pipeline-1")
    stats = ps.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ps = PipelinePriorityScheduler()
    ps.schedule("pipeline-1")
    ps.reset()
    assert ps.get_schedule_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Priority Scheduler Tests ===\n")
    test_schedule()
    test_get_next()
    test_mark_running()
    test_mark_completed()
    test_mark_failed()
    test_get_schedule()
    test_dependencies()
    test_get_pending_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
