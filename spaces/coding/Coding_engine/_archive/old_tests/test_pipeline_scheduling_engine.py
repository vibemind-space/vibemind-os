"""Test pipeline scheduling engine."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_scheduling_engine import PipelineSchedulingEngine


def test_create_job():
    """Create and retrieve job."""
    se = PipelineSchedulingEngine()
    jid = se.create_job("daily_build", pipeline="main",
                        schedule="0 0 * * *", priority=3,
                        max_retries=2, tags=["ci"])
    assert jid.startswith("job-")

    j = se.get_job(jid)
    assert j is not None
    assert j["name"] == "daily_build"
    assert j["pipeline"] == "main"
    assert j["status"] == "pending"
    assert j["priority"] == 3
    assert j["max_retries"] == 2

    assert se.remove_job(jid) is True
    assert se.remove_job(jid) is False
    print("OK: create job")


def test_invalid_job():
    """Invalid job rejected."""
    se = PipelineSchedulingEngine()
    assert se.create_job("") == ""
    print("OK: invalid job")


def test_max_jobs():
    """Max jobs enforced."""
    se = PipelineSchedulingEngine(max_jobs=2)
    se.create_job("a")
    se.create_job("b")
    assert se.create_job("c") == ""
    print("OK: max jobs")


def test_schedule_job():
    """Schedule a job."""
    se = PipelineSchedulingEngine()
    jid = se.create_job("build")

    assert se.schedule_job(jid) is True
    assert se.get_job(jid)["status"] == "scheduled"
    assert se.schedule_job(jid) is False  # already scheduled
    print("OK: schedule job")


def test_pause_resume():
    """Pause and resume job."""
    se = PipelineSchedulingEngine()
    jid = se.create_job("build")
    se.schedule_job(jid)

    assert se.pause_job(jid) is True
    assert se.get_job(jid)["status"] == "paused"
    assert se.pause_job(jid) is False

    assert se.resume_job(jid) is True
    assert se.get_job(jid)["status"] == "scheduled"
    assert se.resume_job(jid) is False
    print("OK: pause resume")


def test_cancel_job():
    """Cancel a job."""
    se = PipelineSchedulingEngine()
    jid = se.create_job("build")

    assert se.cancel_job(jid) is True
    assert se.get_job(jid)["status"] == "cancelled"
    assert se.cancel_job(jid) is False
    print("OK: cancel job")


def test_start_execution():
    """Start job execution."""
    se = PipelineSchedulingEngine()
    jid = se.create_job("build")

    eid = se.start_execution(jid)
    assert eid.startswith("exec-")
    assert se.get_job(jid)["status"] == "running"

    ex = se.get_execution(eid)
    assert ex is not None
    assert ex["job_id"] == jid
    assert ex["status"] == "running"
    print("OK: start execution")


def test_complete_execution():
    """Complete job execution."""
    se = PipelineSchedulingEngine()
    jid = se.create_job("build")
    eid = se.start_execution(jid)

    assert se.complete_execution(eid, result="success", duration_ms=150) is True
    assert se.get_execution(eid)["status"] == "completed"
    assert se.get_execution(eid)["duration_ms"] == 150
    assert se.get_job(jid)["status"] == "completed"
    assert se.complete_execution(eid) is False
    print("OK: complete execution")


def test_fail_execution():
    """Fail job execution."""
    se = PipelineSchedulingEngine()
    jid = se.create_job("build")
    eid = se.start_execution(jid)

    assert se.fail_execution(eid, error="timeout", duration_ms=5000) is True
    assert se.get_execution(eid)["status"] == "failed"
    assert se.get_job(jid)["status"] == "failed"
    assert se.get_job(jid)["retry_count"] == 1
    assert se.fail_execution(eid) is False
    print("OK: fail execution")


def test_cancel_execution():
    """Cancel job execution."""
    se = PipelineSchedulingEngine()
    jid = se.create_job("build")
    eid = se.start_execution(jid)

    assert se.cancel_execution(eid) is True
    assert se.get_execution(eid)["status"] == "cancelled"
    assert se.cancel_execution(eid) is False
    print("OK: cancel execution")


def test_job_executions():
    """Get executions for a job."""
    se = PipelineSchedulingEngine()
    jid = se.create_job("build")
    e1 = se.start_execution(jid)
    se.complete_execution(e1)
    # Re-schedule then run again
    se.schedule_job(jid)
    e2 = se.start_execution(jid)
    se.fail_execution(e2)

    execs = se.get_job_executions(jid)
    assert len(execs) == 2
    print("OK: job executions")


def test_remove_job_cascades():
    """Remove job removes its executions."""
    se = PipelineSchedulingEngine()
    jid = se.create_job("build")
    se.start_execution(jid)

    se.remove_job(jid)
    assert se.search_executions() == []
    print("OK: remove job cascades")


def test_list_jobs():
    """List jobs with filters."""
    se = PipelineSchedulingEngine()
    se.create_job("a", pipeline="main", tags=["ci"])
    j2 = se.create_job("b", pipeline="test")
    se.cancel_job(j2)

    all_j = se.list_jobs()
    assert len(all_j) == 2

    by_status = se.list_jobs(status="cancelled")
    assert len(by_status) == 1

    by_pipe = se.list_jobs(pipeline="main")
    assert len(by_pipe) == 1

    by_tag = se.list_jobs(tag="ci")
    assert len(by_tag) == 1
    print("OK: list jobs")


def test_search_executions():
    """Search executions."""
    se = PipelineSchedulingEngine()
    j1 = se.create_job("a")
    j2 = se.create_job("b")
    e1 = se.start_execution(j1)
    se.complete_execution(e1)
    se.start_execution(j2)

    all_e = se.search_executions()
    assert len(all_e) == 2

    by_status = se.search_executions(status="completed")
    assert len(by_status) == 1

    by_job = se.search_executions(job_id=j1)
    assert len(by_job) == 1
    print("OK: search executions")


def test_queue():
    """Get job queue."""
    se = PipelineSchedulingEngine()
    se.create_job("low", priority=8)
    se.create_job("high", priority=2)
    j3 = se.create_job("done")
    se.start_execution(j3)  # now running

    queue = se.get_queue()
    assert len(queue) == 2
    assert queue[0]["name"] == "high"
    assert queue[1]["name"] == "low"
    print("OK: queue")


def test_success_rate():
    """Get job success rate."""
    se = PipelineSchedulingEngine()
    j = se.create_job("build")
    e1 = se.start_execution(j)
    se.complete_execution(e1)
    se.schedule_job(j)
    e2 = se.start_execution(j)
    se.complete_execution(e2)
    se.schedule_job(j)
    e3 = se.start_execution(j)
    se.fail_execution(e3)

    rate = se.get_job_success_rate(j)
    assert rate["completed"] == 2
    assert rate["failed"] == 1
    assert abs(rate["success_rate"] - 66.7) < 0.1
    print("OK: success rate")


def test_avg_duration():
    """Get average duration."""
    se = PipelineSchedulingEngine()
    j = se.create_job("build")
    e1 = se.start_execution(j)
    se.complete_execution(e1, duration_ms=100)
    se.schedule_job(j)
    e2 = se.start_execution(j)
    se.complete_execution(e2, duration_ms=200)

    avg = se.get_avg_duration(j)
    assert avg["count"] == 2
    assert avg["avg_ms"] == 150.0
    assert avg["min_ms"] == 100
    assert avg["max_ms"] == 200
    print("OK: avg duration")


def test_callback():
    """Callback fires on job create."""
    se = PipelineSchedulingEngine()
    fired = []
    se.on_change("mon", lambda a, d: fired.append(a))

    se.create_job("build")
    assert "job_created" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    se = PipelineSchedulingEngine()
    assert se.on_change("mon", lambda a, d: None) is True
    assert se.on_change("mon", lambda a, d: None) is False
    assert se.remove_callback("mon") is True
    assert se.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    se = PipelineSchedulingEngine()
    j1 = se.create_job("a")
    j2 = se.create_job("b")
    e1 = se.start_execution(j1)
    se.complete_execution(e1)
    e2 = se.start_execution(j2)
    se.fail_execution(e2)

    stats = se.get_stats()
    assert stats["total_jobs_created"] == 2
    assert stats["total_executions"] == 2
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    assert stats["current_jobs"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    se = PipelineSchedulingEngine()
    j = se.create_job("build")
    se.start_execution(j)

    se.reset()
    assert se.list_jobs() == []
    assert se.search_executions() == []
    stats = se.get_stats()
    assert stats["current_jobs"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Scheduling Engine Tests ===\n")
    test_create_job()
    test_invalid_job()
    test_max_jobs()
    test_schedule_job()
    test_pause_resume()
    test_cancel_job()
    test_start_execution()
    test_complete_execution()
    test_fail_execution()
    test_cancel_execution()
    test_job_executions()
    test_remove_job_cascades()
    test_list_jobs()
    test_search_executions()
    test_queue()
    test_success_rate()
    test_avg_duration()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
