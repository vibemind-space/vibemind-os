"""Test pipeline resource scheduler -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_resource_scheduler import PipelineResourceScheduler


def test_schedule_resource():
    rs = PipelineResourceScheduler()
    sid = rs.schedule_resource("deploy", "gpu", 4, priority=8)
    assert len(sid) > 0
    assert sid.startswith("prs-")
    print("OK: schedule resource")


def test_get_schedule():
    rs = PipelineResourceScheduler()
    sid = rs.schedule_resource("deploy", "gpu", 4)
    sched = rs.get_schedule(sid)
    assert sched is not None
    assert sched["schedule_id"] == sid
    assert sched["pipeline_id"] == "deploy"
    assert sched["resource_type"] == "gpu"
    assert sched["amount"] == 4
    assert sched["status"] == "pending"
    assert rs.get_schedule("nonexistent") is None
    print("OK: get schedule")


def test_allocate():
    rs = PipelineResourceScheduler()
    sid = rs.schedule_resource("deploy", "gpu", 4)
    assert rs.allocate(sid) is True
    sched = rs.get_schedule(sid)
    assert sched["status"] == "allocated"
    # Already allocated
    assert rs.allocate(sid) is False
    print("OK: allocate")


def test_release():
    rs = PipelineResourceScheduler()
    sid = rs.schedule_resource("deploy", "gpu", 4)
    rs.allocate(sid)
    assert rs.release(sid) is True
    sched = rs.get_schedule(sid)
    assert sched["status"] == "released"
    # Not allocated anymore
    assert rs.release(sid) is False
    print("OK: release")


def test_get_pipeline_schedules():
    rs = PipelineResourceScheduler()
    rs.schedule_resource("deploy", "gpu", 4)
    rs.schedule_resource("deploy", "cpu", 8)
    rs.schedule_resource("build", "cpu", 4)
    scheds = rs.get_pipeline_schedules("deploy")
    assert len(scheds) == 2
    print("OK: get pipeline schedules")


def test_get_pending_schedules():
    rs = PipelineResourceScheduler()
    s1 = rs.schedule_resource("deploy", "gpu", 4, priority=10)
    s2 = rs.schedule_resource("deploy", "cpu", 8, priority=5)
    rs.allocate(s1)
    pending = rs.get_pending_schedules()
    assert len(pending) == 1
    assert pending[0]["resource_type"] == "cpu"
    print("OK: get pending schedules")


def test_get_allocated_resources():
    rs = PipelineResourceScheduler()
    s1 = rs.schedule_resource("deploy", "gpu", 4)
    s2 = rs.schedule_resource("build", "cpu", 8)
    rs.allocate(s1)
    alloc = rs.get_allocated_resources()
    assert len(alloc) == 1
    alloc_deploy = rs.get_allocated_resources("deploy")
    assert len(alloc_deploy) == 1
    print("OK: get allocated resources")


def test_cancel_schedule():
    rs = PipelineResourceScheduler()
    sid = rs.schedule_resource("deploy", "gpu", 4)
    assert rs.cancel_schedule(sid) is True
    sched = rs.get_schedule(sid)
    assert sched["status"] == "cancelled"
    # Can't cancel allocated
    s2 = rs.schedule_resource("deploy", "cpu", 8)
    rs.allocate(s2)
    assert rs.cancel_schedule(s2) is False
    print("OK: cancel schedule")


def test_get_resource_usage():
    rs = PipelineResourceScheduler()
    s1 = rs.schedule_resource("deploy", "gpu", 4)
    s2 = rs.schedule_resource("build", "gpu", 2)
    rs.allocate(s1)
    usage = rs.get_resource_usage("gpu")
    assert usage["resource_type"] == "gpu"
    assert usage["total_allocated"] == 4
    assert usage["total_pending"] == 2
    print("OK: get resource usage")


def test_list_pipelines():
    rs = PipelineResourceScheduler()
    rs.schedule_resource("deploy", "gpu", 4)
    rs.schedule_resource("build", "cpu", 8)
    pipes = rs.list_pipelines()
    assert "deploy" in pipes
    assert "build" in pipes
    print("OK: list pipelines")


def test_get_schedule_count():
    rs = PipelineResourceScheduler()
    rs.schedule_resource("deploy", "gpu", 4)
    rs.schedule_resource("deploy", "cpu", 8)
    assert rs.get_schedule_count("deploy") == 2
    assert rs.get_schedule_count() >= 2
    print("OK: get schedule count")


def test_callbacks():
    rs = PipelineResourceScheduler()
    fired = []
    rs.on_change("mon", lambda a, d: fired.append(a))
    rs.schedule_resource("deploy", "gpu", 4)
    assert len(fired) >= 1
    assert rs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rs = PipelineResourceScheduler()
    rs.schedule_resource("deploy", "gpu", 4)
    stats = rs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rs = PipelineResourceScheduler()
    rs.schedule_resource("deploy", "gpu", 4)
    rs.reset()
    assert rs.get_schedule_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Resource Scheduler Tests ===\n")
    test_schedule_resource()
    test_get_schedule()
    test_allocate()
    test_release()
    test_get_pipeline_schedules()
    test_get_pending_schedules()
    test_get_allocated_resources()
    test_cancel_schedule()
    test_get_resource_usage()
    test_list_pipelines()
    test_get_schedule_count()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 14 TESTS PASSED ===")


if __name__ == "__main__":
    main()
