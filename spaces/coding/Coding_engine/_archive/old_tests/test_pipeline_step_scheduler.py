"""Tests for PipelineStepScheduler service."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_step_scheduler import PipelineStepScheduler


def test_schedule_step():
    svc = PipelineStepScheduler()
    sid = svc.schedule_step("p1", "build")
    assert sid.startswith("pss2-")
    assert len(sid) > 5
    assert svc.get_schedule_count() == 1


def test_get_schedule():
    svc = PipelineStepScheduler()
    sid = svc.schedule_step("p1", "build", delay_seconds=5.0, priority=3)
    sched = svc.get_schedule(sid)
    assert sched is not None
    assert sched["schedule_id"] == sid
    assert sched["pipeline_id"] == "p1"
    assert sched["step_name"] == "build"
    assert sched["delay_seconds"] == 5.0
    assert sched["priority"] == 3
    assert sched["status"] == "pending"
    assert svc.get_schedule("nonexistent") is None


def test_get_pending():
    svc = PipelineStepScheduler()
    svc.schedule_step("p1", "build", priority=1)
    svc.schedule_step("p1", "test", priority=5)
    svc.schedule_step("p2", "deploy", priority=10)
    pending = svc.get_pending("p1")
    assert len(pending) == 2
    assert pending[0]["step_name"] == "test"  # higher priority first
    assert pending[1]["step_name"] == "build"
    assert svc.get_pending("p2")[0]["step_name"] == "deploy"


def test_mark_running():
    svc = PipelineStepScheduler()
    sid = svc.schedule_step("p1", "build")
    assert svc.mark_running(sid) is True
    sched = svc.get_schedule(sid)
    assert sched["status"] == "running"
    # Cannot mark running again
    assert svc.mark_running(sid) is False
    # Nonexistent
    assert svc.mark_running("nonexistent") is False


def test_mark_completed():
    svc = PipelineStepScheduler()
    sid = svc.schedule_step("p1", "build")
    # Cannot complete a pending step
    assert svc.mark_completed(sid) is False
    svc.mark_running(sid)
    assert svc.mark_completed(sid) is True
    sched = svc.get_schedule(sid)
    assert sched["status"] == "completed"
    # Cannot complete again
    assert svc.mark_completed(sid) is False


def test_cancel_schedule():
    svc = PipelineStepScheduler()
    sid = svc.schedule_step("p1", "build")
    assert svc.cancel_schedule(sid) is True
    assert svc.get_schedule(sid) is None
    assert svc.cancel_schedule(sid) is False
    assert svc.get_schedule_count() == 0


def test_priority_ordering():
    svc = PipelineStepScheduler()
    svc.schedule_step("p1", "low", priority=1)
    svc.schedule_step("p1", "high", priority=100)
    svc.schedule_step("p1", "mid", priority=50)
    pending = svc.get_pending("p1")
    assert len(pending) == 3
    assert pending[0]["step_name"] == "high"
    assert pending[1]["step_name"] == "mid"
    assert pending[2]["step_name"] == "low"


def test_get_schedule_count():
    svc = PipelineStepScheduler()
    assert svc.get_schedule_count() == 0
    svc.schedule_step("p1", "build")
    svc.schedule_step("p2", "test")
    svc.schedule_step("p1", "deploy")
    assert svc.get_schedule_count() == 3
    assert svc.get_schedule_count("p1") == 2
    assert svc.get_schedule_count("p2") == 1
    assert svc.get_schedule_count("p3") == 0


def test_list_pipelines():
    svc = PipelineStepScheduler()
    assert svc.list_pipelines() == []
    svc.schedule_step("p1", "build")
    svc.schedule_step("p2", "test")
    svc.schedule_step("p1", "deploy")
    pipelines = svc.list_pipelines()
    assert sorted(pipelines) == ["p1", "p2"]


def test_callbacks():
    events = []

    def tracker(action, detail):
        events.append((action, detail))

    svc = PipelineStepScheduler()
    assert svc.on_change("tracker", tracker) is True
    assert svc.on_change("tracker", tracker) is False  # duplicate

    sid = svc.schedule_step("p1", "build")
    assert len(events) == 1
    assert events[0][0] == "step_scheduled"
    assert events[0][1]["schedule_id"] == sid

    svc.mark_running(sid)
    assert len(events) == 2
    assert events[1][0] == "step_running"

    svc.mark_completed(sid)
    assert len(events) == 3
    assert events[2][0] == "step_completed"

    assert svc.remove_callback("tracker") is True
    assert svc.remove_callback("tracker") is False
    svc.schedule_step("p1", "test")
    assert len(events) == 3  # no new events after callback removed


def test_stats():
    svc = PipelineStepScheduler()
    svc.on_change("cb1", lambda a, d: None)
    svc.schedule_step("p1", "build")
    svc.schedule_step("p2", "test")
    stats = svc.get_stats()
    assert stats["total_schedules"] == 2
    assert stats["max_entries"] == 10000
    assert stats["pipelines"] == 2
    assert stats["registered_callbacks"] == 1


def test_reset():
    svc = PipelineStepScheduler()
    svc.on_change("cb", lambda a, d: None)
    svc.schedule_step("p1", "build")
    svc.schedule_step("p2", "test")
    svc.reset()
    assert svc.get_schedule_count() == 0
    assert svc.list_pipelines() == []
    assert svc.get_stats()["registered_callbacks"] == 0


if __name__ == "__main__":
    test_schedule_step()
    test_get_schedule()
    test_get_pending()
    test_mark_running()
    test_mark_completed()
    test_cancel_schedule()
    test_priority_ordering()
    test_get_schedule_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("=== ALL 12 TESTS PASSED ===")
