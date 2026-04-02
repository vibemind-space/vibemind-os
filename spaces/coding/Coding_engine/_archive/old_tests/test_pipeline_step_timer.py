"""Test pipeline step timer -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_step_timer import PipelineStepTimer


def test_start_timer():
    st = PipelineStepTimer()
    tid = st.start_timer("pipeline-1", "extract")
    assert len(tid) > 0
    assert tid.startswith("pst-")
    print("OK: start timer")


def test_stop_timer():
    st = PipelineStepTimer()
    st.start_timer("pipeline-1", "extract")
    elapsed = st.stop_timer("pipeline-1", "extract")
    assert elapsed >= 0.0
    assert st.stop_timer("pipeline-1", "nonexistent") == 0.0
    print("OK: stop timer")


def test_get_elapsed_running():
    st = PipelineStepTimer()
    st.start_timer("pipeline-1", "extract")
    elapsed = st.get_elapsed("pipeline-1", "extract")
    assert elapsed >= 0.0
    print("OK: get elapsed running")


def test_get_elapsed_stopped():
    st = PipelineStepTimer()
    st.start_timer("pipeline-1", "extract")
    st.stop_timer("pipeline-1", "extract")
    elapsed = st.get_elapsed("pipeline-1", "extract")
    assert elapsed >= 0.0
    assert st.get_elapsed("pipeline-1", "nonexistent") == 0.0
    print("OK: get elapsed stopped")


def test_get_average_time():
    st = PipelineStepTimer()
    st.start_timer("pipeline-1", "extract")
    st.stop_timer("pipeline-1", "extract")
    st.start_timer("pipeline-1", "extract")
    st.stop_timer("pipeline-1", "extract")
    avg = st.get_average_time("pipeline-1", "extract")
    assert avg >= 0.0
    print("OK: get average time")


def test_get_timers():
    st = PipelineStepTimer()
    st.start_timer("pipeline-1", "extract")
    st.start_timer("pipeline-1", "transform")
    timers = st.get_timers("pipeline-1")
    assert len(timers) == 2
    print("OK: get timers")


def test_get_timer_count():
    st = PipelineStepTimer()
    st.start_timer("pipeline-1", "extract")
    st.start_timer("pipeline-2", "load")
    assert st.get_timer_count() == 2
    assert st.get_timer_count("pipeline-1") == 1
    print("OK: get timer count")


def test_list_pipelines():
    st = PipelineStepTimer()
    st.start_timer("pipeline-1", "extract")
    st.start_timer("pipeline-2", "load")
    pipelines = st.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    st = PipelineStepTimer()
    fired = []
    st.on_change("mon", lambda a, d: fired.append(a))
    st.start_timer("pipeline-1", "extract")
    assert len(fired) >= 1
    assert st.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    st = PipelineStepTimer()
    st.start_timer("pipeline-1", "extract")
    stats = st.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    st = PipelineStepTimer()
    st.start_timer("pipeline-1", "extract")
    st.reset()
    assert st.get_timer_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Step Timer Tests ===\n")
    test_start_timer()
    test_stop_timer()
    test_get_elapsed_running()
    test_get_elapsed_stopped()
    test_get_average_time()
    test_get_timers()
    test_get_timer_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
