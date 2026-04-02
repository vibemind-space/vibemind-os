"""Test pipeline timeout manager -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_timeout_manager import PipelineTimeoutManager


def test_set_timeout():
    tm = PipelineTimeoutManager()
    tid = tm.set_timeout("pipeline-1", timeout_seconds=60.0, label="build-phase")
    assert len(tid) > 0
    assert tid.startswith("ptm2-")
    print("OK: set timeout")


def test_check_timeout_not_expired():
    tm = PipelineTimeoutManager()
    tm.set_timeout("pipeline-1", timeout_seconds=60.0)
    assert tm.check_timeout("pipeline-1") is False
    print("OK: check timeout not expired")


def test_get_remaining():
    tm = PipelineTimeoutManager()
    tm.set_timeout("pipeline-1", timeout_seconds=60.0)
    remaining = tm.get_remaining("pipeline-1")
    assert remaining > 50.0  # should be close to 60
    print("OK: get remaining")


def test_cancel_timeout():
    tm = PipelineTimeoutManager()
    tm.set_timeout("pipeline-1", timeout_seconds=60.0)
    assert tm.cancel_timeout("pipeline-1") is True
    assert tm.cancel_timeout("nonexistent") is False
    print("OK: cancel timeout")


def test_extend_timeout():
    tm = PipelineTimeoutManager()
    tm.set_timeout("pipeline-1", timeout_seconds=30.0)
    assert tm.extend_timeout("pipeline-1", extra_seconds=30.0) is True
    remaining = tm.get_remaining("pipeline-1")
    assert remaining > 50.0  # 30 + 30 = ~60
    print("OK: extend timeout")


def test_list_pipelines():
    tm = PipelineTimeoutManager()
    tm.set_timeout("pipeline-1", timeout_seconds=60.0)
    tm.set_timeout("pipeline-2", timeout_seconds=30.0)
    pipelines = tm.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    tm = PipelineTimeoutManager()
    fired = []
    tm.on_change("mon", lambda a, d: fired.append(a))
    tm.set_timeout("pipeline-1", timeout_seconds=60.0)
    assert len(fired) >= 1
    assert tm.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    tm = PipelineTimeoutManager()
    tm.set_timeout("pipeline-1", timeout_seconds=60.0)
    stats = tm.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    tm = PipelineTimeoutManager()
    tm.set_timeout("pipeline-1", timeout_seconds=60.0)
    tm.reset()
    assert tm.get_timeout_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Timeout Manager Tests ===\n")
    test_set_timeout()
    test_check_timeout_not_expired()
    test_get_remaining()
    test_cancel_timeout()
    test_extend_timeout()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 9 TESTS PASSED ===")


if __name__ == "__main__":
    main()
