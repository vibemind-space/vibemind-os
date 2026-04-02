"""Test pipeline stage manager."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_stage_manager import PipelineStageManager


def test_create_pipeline():
    """Create and retrieve pipeline."""
    sm = PipelineStageManager()
    pid = sm.create_pipeline("deploy_v2", tags=["prod"])
    assert pid.startswith("ppl-")

    p = sm.get_pipeline(pid)
    assert p is not None
    assert p["name"] == "deploy_v2"
    assert p["status"] == "created"
    assert p["stages"] == []

    assert sm.remove_pipeline(pid) is True
    assert sm.remove_pipeline(pid) is False
    print("OK: create pipeline")


def test_invalid_pipeline():
    """Invalid pipeline rejected."""
    sm = PipelineStageManager()
    assert sm.create_pipeline("") == ""
    print("OK: invalid pipeline")


def test_duplicate_name():
    """Duplicate name rejected."""
    sm = PipelineStageManager()
    sm.create_pipeline("deploy")
    assert sm.create_pipeline("deploy") == ""
    print("OK: duplicate name")


def test_max_pipelines():
    """Max pipelines enforced."""
    sm = PipelineStageManager(max_pipelines=2)
    sm.create_pipeline("a")
    sm.create_pipeline("b")
    assert sm.create_pipeline("c") == ""
    print("OK: max pipelines")


def test_add_stage():
    """Add stages to pipeline."""
    sm = PipelineStageManager()
    pid = sm.create_pipeline("deploy")

    s1 = sm.add_stage(pid, "Build", gate="tests pass")
    assert s1.startswith("stg-")

    s2 = sm.add_stage(pid, "Test")
    stage1 = sm.get_stage(s1)
    assert stage1["name"] == "Build"
    assert stage1["order"] == 0
    assert stage1["gate"] == "tests pass"

    stage2 = sm.get_stage(s2)
    assert stage2["order"] == 1
    print("OK: add stage")


def test_invalid_stage():
    """Invalid stage rejected."""
    sm = PipelineStageManager()
    pid = sm.create_pipeline("deploy")
    assert sm.add_stage(pid, "") == ""
    assert sm.add_stage("nonexistent", "stage") == ""
    print("OK: invalid stage")


def test_start_pipeline():
    """Start pipeline execution."""
    sm = PipelineStageManager()
    pid = sm.create_pipeline("deploy")
    sm.add_stage(pid, "Build")
    sm.add_stage(pid, "Test")

    assert sm.start_pipeline(pid) is True
    p = sm.get_pipeline(pid)
    assert p["status"] == "running"
    assert p["current_stage_idx"] == 0

    # first stage should be running
    stages = sm.get_pipeline_stages(pid)
    assert stages[0]["status"] == "running"
    assert stages[1]["status"] == "pending"
    print("OK: start pipeline")


def test_start_empty_pipeline():
    """Can't start pipeline with no stages."""
    sm = PipelineStageManager()
    pid = sm.create_pipeline("empty")
    assert sm.start_pipeline(pid) is False
    print("OK: start empty pipeline")


def test_advance_stage():
    """Advance through stages."""
    sm = PipelineStageManager()
    pid = sm.create_pipeline("deploy")
    sm.add_stage(pid, "Build")
    sm.add_stage(pid, "Test")
    sm.add_stage(pid, "Deploy")
    sm.start_pipeline(pid)

    assert sm.advance_stage(pid, result="build ok") is True
    p = sm.get_pipeline(pid)
    assert p["current_stage_idx"] == 1
    assert p["status"] == "running"

    stages = sm.get_pipeline_stages(pid)
    assert stages[0]["status"] == "completed"
    assert stages[0]["result"] == "build ok"
    assert stages[1]["status"] == "running"
    print("OK: advance stage")


def test_complete_pipeline():
    """Pipeline completes when all stages done."""
    sm = PipelineStageManager()
    pid = sm.create_pipeline("deploy")
    sm.add_stage(pid, "Build")
    sm.add_stage(pid, "Test")
    sm.start_pipeline(pid)

    sm.advance_stage(pid)  # Build -> Test
    sm.advance_stage(pid)  # Test -> done

    p = sm.get_pipeline(pid)
    assert p["status"] == "completed"
    print("OK: complete pipeline")


def test_fail_stage():
    """Fail stage fails pipeline."""
    sm = PipelineStageManager()
    pid = sm.create_pipeline("deploy")
    sm.add_stage(pid, "Build")
    sm.start_pipeline(pid)

    assert sm.fail_stage(pid, result="compile error") is True
    p = sm.get_pipeline(pid)
    assert p["status"] == "failed"

    stages = sm.get_pipeline_stages(pid)
    assert stages[0]["status"] == "failed"
    assert stages[0]["result"] == "compile error"
    print("OK: fail stage")


def test_skip_stage():
    """Skip stage."""
    sm = PipelineStageManager()
    pid = sm.create_pipeline("deploy")
    sm.add_stage(pid, "Build")
    sm.add_stage(pid, "Optional")
    sm.add_stage(pid, "Deploy")
    sm.start_pipeline(pid)

    sm.advance_stage(pid)  # Build done
    sm.skip_stage(pid)     # Skip Optional

    p = sm.get_pipeline(pid)
    assert p["current_stage_idx"] == 2
    stages = sm.get_pipeline_stages(pid)
    assert stages[1]["status"] == "skipped"
    assert stages[2]["status"] == "running"
    print("OK: skip stage")


def test_pause_resume():
    """Pause and resume pipeline."""
    sm = PipelineStageManager()
    pid = sm.create_pipeline("deploy")
    sm.add_stage(pid, "Build")
    sm.start_pipeline(pid)

    assert sm.pause_pipeline(pid) is True
    assert sm.get_pipeline(pid)["status"] == "paused"
    assert sm.pause_pipeline(pid) is False

    assert sm.resume_pipeline(pid) is True
    assert sm.get_pipeline(pid)["status"] == "running"
    assert sm.resume_pipeline(pid) is False
    print("OK: pause resume")


def test_get_progress():
    """Get pipeline progress."""
    sm = PipelineStageManager()
    pid = sm.create_pipeline("deploy")
    sm.add_stage(pid, "Build")
    sm.add_stage(pid, "Test")
    sm.add_stage(pid, "Deploy")
    sm.start_pipeline(pid)

    progress = sm.get_progress(pid)
    assert progress["completed"] == 0
    assert progress["total"] == 3
    assert progress["percentage"] == 0.0

    sm.advance_stage(pid)
    progress = sm.get_progress(pid)
    assert progress["completed"] == 1
    assert progress["percentage"] == 33.3
    print("OK: get progress")


def test_get_by_name():
    """Get pipeline by name."""
    sm = PipelineStageManager()
    sm.create_pipeline("my_pipeline")

    p = sm.get_pipeline_by_name("my_pipeline")
    assert p is not None
    assert p["name"] == "my_pipeline"
    assert sm.get_pipeline_by_name("nonexistent") is None
    print("OK: get by name")


def test_list_pipelines():
    """List pipelines with filters."""
    sm = PipelineStageManager()
    pid1 = sm.create_pipeline("a", tags=["prod"])
    pid2 = sm.create_pipeline("b")
    sm.add_stage(pid2, "stage")
    sm.start_pipeline(pid2)

    all_p = sm.list_pipelines()
    assert len(all_p) == 2

    by_status = sm.list_pipelines(status="running")
    assert len(by_status) == 1

    by_tag = sm.list_pipelines(tag="prod")
    assert len(by_tag) == 1
    print("OK: list pipelines")


def test_remove_cascades():
    """Remove pipeline cascades to stages."""
    sm = PipelineStageManager()
    pid = sm.create_pipeline("deploy")
    s1 = sm.add_stage(pid, "Build")

    sm.remove_pipeline(pid)
    assert sm.get_stage(s1) is None
    print("OK: remove cascades")


def test_callback():
    """Callback fires on events."""
    sm = PipelineStageManager()
    fired = []
    sm.on_change("mon", lambda a, d: fired.append(a))

    pid = sm.create_pipeline("deploy")
    assert "pipeline_created" in fired

    sm.add_stage(pid, "Build")
    assert "stage_added" in fired

    sm.start_pipeline(pid)
    assert "pipeline_started" in fired

    sm.advance_stage(pid)
    assert "stage_completed" in fired
    assert "pipeline_completed" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    sm = PipelineStageManager()
    assert sm.on_change("mon", lambda a, d: None) is True
    assert sm.on_change("mon", lambda a, d: None) is False
    assert sm.remove_callback("mon") is True
    assert sm.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    sm = PipelineStageManager()
    pid = sm.create_pipeline("deploy")
    sm.add_stage(pid, "Build")
    sm.start_pipeline(pid)
    sm.advance_stage(pid)

    stats = sm.get_stats()
    assert stats["total_pipelines"] == 1
    assert stats["total_stages"] == 1
    assert stats["total_completed"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    sm = PipelineStageManager()
    pid = sm.create_pipeline("deploy")
    sm.add_stage(pid, "Build")

    sm.reset()
    assert sm.list_pipelines() == []
    stats = sm.get_stats()
    assert stats["current_pipelines"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Stage Manager Tests ===\n")
    test_create_pipeline()
    test_invalid_pipeline()
    test_duplicate_name()
    test_max_pipelines()
    test_add_stage()
    test_invalid_stage()
    test_start_pipeline()
    test_start_empty_pipeline()
    test_advance_stage()
    test_complete_pipeline()
    test_fail_stage()
    test_skip_stage()
    test_pause_resume()
    test_get_progress()
    test_get_by_name()
    test_list_pipelines()
    test_remove_cascades()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
