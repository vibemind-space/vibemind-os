"""Test pipeline step profiler -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_step_profiler import PipelineStepProfiler


def test_start_profile():
    sp = PipelineStepProfiler()
    pid = sp.start_profile("pipeline-1", "extract")
    assert len(pid) > 0
    assert pid.startswith("psp-")
    print("OK: start profile")


def test_end_profile():
    sp = PipelineStepProfiler()
    sp.start_profile("pipeline-1", "extract")
    elapsed = sp.end_profile("pipeline-1", "extract")
    assert elapsed >= 0.0
    assert sp.end_profile("pipeline-1", "nonexistent") == 0.0
    print("OK: end profile")


def test_get_profile():
    sp = PipelineStepProfiler()
    sp.start_profile("pipeline-1", "extract")
    sp.end_profile("pipeline-1", "extract")
    profile = sp.get_profile("pipeline-1", "extract")
    assert profile is not None
    assert profile["step_name"] == "extract"
    assert sp.get_profile("pipeline-1", "nonexistent") is None
    print("OK: get profile")


def test_get_profiles():
    sp = PipelineStepProfiler()
    sp.start_profile("pipeline-1", "extract")
    sp.start_profile("pipeline-1", "transform")
    profiles = sp.get_profiles("pipeline-1")
    assert len(profiles) == 2
    print("OK: get profiles")


def test_get_slowest_step():
    sp = PipelineStepProfiler()
    sp.start_profile("pipeline-1", "fast")
    sp.end_profile("pipeline-1", "fast")
    # Start another and give it more time to be "slower"
    sp.start_profile("pipeline-1", "slow")
    import time
    time.sleep(0.01)
    sp.end_profile("pipeline-1", "slow")
    slowest = sp.get_slowest_step("pipeline-1")
    assert slowest is not None
    assert slowest["step_name"] == "slow"
    print("OK: get slowest step")


def test_get_profile_count():
    sp = PipelineStepProfiler()
    sp.start_profile("pipeline-1", "extract")
    sp.start_profile("pipeline-2", "load")
    assert sp.get_profile_count() == 2
    assert sp.get_profile_count("pipeline-1") == 1
    print("OK: get profile count")


def test_list_pipelines():
    sp = PipelineStepProfiler()
    sp.start_profile("pipeline-1", "extract")
    sp.start_profile("pipeline-2", "load")
    pipelines = sp.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    sp = PipelineStepProfiler()
    fired = []
    sp.on_change("mon", lambda a, d: fired.append(a))
    sp.start_profile("pipeline-1", "extract")
    assert len(fired) >= 1
    assert sp.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    sp = PipelineStepProfiler()
    sp.start_profile("pipeline-1", "extract")
    stats = sp.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    sp = PipelineStepProfiler()
    sp.start_profile("pipeline-1", "extract")
    sp.reset()
    assert sp.get_profile_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Step Profiler Tests ===\n")
    test_start_profile()
    test_end_profile()
    test_get_profile()
    test_get_profiles()
    test_get_slowest_step()
    test_get_profile_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
