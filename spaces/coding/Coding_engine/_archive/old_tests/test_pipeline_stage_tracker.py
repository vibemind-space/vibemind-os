"""Test pipeline stage tracker -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_stage_tracker import PipelineStageTracker


def test_create_pipeline():
    st = PipelineStageTracker()
    pid = st.create_pipeline("deploy", stages=["build", "test", "release"], tags=["ci"])
    assert len(pid) > 0
    p = st.get_pipeline(pid)
    assert p is not None
    assert p["name"] == "deploy"
    assert st.create_pipeline("deploy") == ""  # dup
    print("OK: create pipeline")


def test_start_and_complete_stage():
    st = PipelineStageTracker()
    pid = st.create_pipeline("deploy", stages=["build", "test"])
    eid = st.start_stage(pid, "build")
    assert len(eid) > 0
    assert st.complete_stage(eid) is True
    print("OK: start and complete stage")


def test_fail_stage():
    st = PipelineStageTracker()
    pid = st.create_pipeline("deploy", stages=["build", "test"])
    eid = st.start_stage(pid, "build")
    assert st.fail_stage(eid, error="compile error") is True
    print("OK: fail stage")


def test_pipeline_progress():
    st = PipelineStageTracker()
    pid = st.create_pipeline("deploy", stages=["build", "test", "release"])
    e1 = st.start_stage(pid, "build")
    st.complete_stage(e1)
    e2 = st.start_stage(pid, "test")
    st.complete_stage(e2)
    prog = st.get_pipeline_progress(pid)
    assert prog["total_stages"] >= 2
    assert prog["completed"] >= 2
    print("OK: pipeline progress")


def test_stage_status():
    st = PipelineStageTracker()
    pid = st.create_pipeline("deploy", stages=["build"])
    eid = st.start_stage(pid, "build")
    st.complete_stage(eid, status="success")
    status = st.get_stage_status(pid, "build")
    assert status is not None
    print("OK: stage status")


def test_list_pipelines():
    st = PipelineStageTracker()
    st.create_pipeline("p1", tags=["ci"])
    st.create_pipeline("p2", tags=["cd"])
    assert len(st.list_pipelines()) == 2
    assert len(st.list_pipelines(tag="ci")) == 1
    print("OK: list pipelines")


def test_remove_pipeline():
    st = PipelineStageTracker()
    pid = st.create_pipeline("temp")
    assert st.remove_pipeline(pid) is True
    assert st.remove_pipeline(pid) is False
    print("OK: remove pipeline")


def test_callbacks():
    st = PipelineStageTracker()
    fired = []
    st.on_change("mon", lambda a, d: fired.append(a))
    st.create_pipeline("p1")
    assert len(fired) >= 1
    assert st.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    st = PipelineStageTracker()
    st.create_pipeline("p1")
    stats = st.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    st = PipelineStageTracker()
    st.create_pipeline("p1")
    st.reset()
    assert st.list_pipelines() == []
    print("OK: reset")


def main():
    print("=== Pipeline Stage Tracker Tests ===\n")
    test_create_pipeline()
    test_start_and_complete_stage()
    test_fail_stage()
    test_pipeline_progress()
    test_stage_status()
    test_list_pipelines()
    test_remove_pipeline()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
