"""Test pipeline throttle controller -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_throttle_controller import PipelineThrottleController


def test_set_throttle():
    tc = PipelineThrottleController()
    tid = tc.set_throttle("pipeline-1", 100, window_seconds=60)
    assert len(tid) > 0
    assert tid.startswith("ptc-")
    print("OK: set throttle")


def test_get_throttle():
    tc = PipelineThrottleController()
    tid = tc.set_throttle("pipeline-1", 100)
    throttle = tc.get_throttle(tid)
    assert throttle is not None
    assert throttle["pipeline_id"] == "pipeline-1"
    assert throttle["max_rate"] == 100
    assert tc.get_throttle("nonexistent") is None
    print("OK: get throttle")


def test_allow_request():
    tc = PipelineThrottleController()
    tc.set_throttle("pipeline-1", 3, window_seconds=60)
    assert tc.allow_request("pipeline-1") is True
    assert tc.allow_request("pipeline-1") is True
    assert tc.allow_request("pipeline-1") is True
    assert tc.allow_request("pipeline-1") is False  # Exceeded limit
    print("OK: allow request")


def test_get_current_rate():
    tc = PipelineThrottleController()
    tc.set_throttle("pipeline-1", 10, window_seconds=60)
    tc.allow_request("pipeline-1")
    tc.allow_request("pipeline-1")
    rate = tc.get_current_rate("pipeline-1")
    assert rate == 2
    print("OK: get current rate")


def test_get_remaining():
    tc = PipelineThrottleController()
    tc.set_throttle("pipeline-1", 5, window_seconds=60)
    tc.allow_request("pipeline-1")
    remaining = tc.get_remaining("pipeline-1")
    assert remaining == 4
    print("OK: get remaining")


def test_is_throttled():
    tc = PipelineThrottleController()
    tc.set_throttle("pipeline-1", 2, window_seconds=60)
    assert tc.is_throttled("pipeline-1") is False
    tc.allow_request("pipeline-1")
    tc.allow_request("pipeline-1")
    assert tc.is_throttled("pipeline-1") is True
    print("OK: is throttled")


def test_reset_throttle():
    tc = PipelineThrottleController()
    tc.set_throttle("pipeline-1", 2, window_seconds=60)
    tc.allow_request("pipeline-1")
    tc.allow_request("pipeline-1")
    assert tc.reset_throttle("pipeline-1") is True
    assert tc.is_throttled("pipeline-1") is False
    assert tc.reset_throttle("nonexistent") is False
    print("OK: reset throttle")


def test_remove_throttle():
    tc = PipelineThrottleController()
    tid = tc.set_throttle("pipeline-1", 100)
    assert tc.remove_throttle(tid) is True
    assert tc.remove_throttle(tid) is False
    print("OK: remove throttle")


def test_list_pipelines():
    tc = PipelineThrottleController()
    tc.set_throttle("pipeline-1", 100)
    tc.set_throttle("pipeline-2", 200)
    pipelines = tc.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    tc = PipelineThrottleController()
    fired = []
    tc.on_change("mon", lambda a, d: fired.append(a))
    tc.set_throttle("pipeline-1", 100)
    assert len(fired) >= 1
    assert tc.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    tc = PipelineThrottleController()
    tc.set_throttle("pipeline-1", 100)
    stats = tc.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    tc = PipelineThrottleController()
    tc.set_throttle("pipeline-1", 100)
    tc.reset()
    assert tc.get_throttle_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Throttle Controller Tests ===\n")
    test_set_throttle()
    test_get_throttle()
    test_allow_request()
    test_get_current_rate()
    test_get_remaining()
    test_is_throttled()
    test_reset_throttle()
    test_remove_throttle()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
