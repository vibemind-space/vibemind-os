"""Test pipeline backpressure handler -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_backpressure_handler import PipelineBackpressureHandler


def test_register_pipeline():
    bp = PipelineBackpressureHandler()
    eid = bp.register_pipeline("pipeline-1", max_queue_depth=100, throttle_threshold=0.8)
    assert len(eid) > 0
    assert eid.startswith("pbh-")
    print("OK: register pipeline")


def test_record_depth():
    bp = PipelineBackpressureHandler()
    bp.register_pipeline("pipeline-1", max_queue_depth=100)
    bp.record_depth("pipeline-1", 50)
    assert bp.get_current_depth("pipeline-1") == 50
    print("OK: record depth")


def test_is_throttled_false():
    bp = PipelineBackpressureHandler()
    bp.register_pipeline("pipeline-1", max_queue_depth=100, throttle_threshold=0.8)
    bp.record_depth("pipeline-1", 50)
    assert bp.is_throttled("pipeline-1") is False
    print("OK: is throttled false")


def test_is_throttled_true():
    bp = PipelineBackpressureHandler()
    bp.register_pipeline("pipeline-1", max_queue_depth=100, throttle_threshold=0.8)
    bp.record_depth("pipeline-1", 85)
    assert bp.is_throttled("pipeline-1") is True
    print("OK: is throttled true")


def test_get_pressure():
    bp = PipelineBackpressureHandler()
    bp.register_pipeline("pipeline-1", max_queue_depth=100)
    bp.record_depth("pipeline-1", 50)
    pressure = bp.get_pressure("pipeline-1")
    assert abs(pressure - 0.5) < 0.01
    print("OK: get pressure")


def test_get_current_depth():
    bp = PipelineBackpressureHandler()
    bp.register_pipeline("pipeline-1", max_queue_depth=100)
    bp.record_depth("pipeline-1", 42)
    assert bp.get_current_depth("pipeline-1") == 42
    print("OK: get current depth")


def test_list_pipelines():
    bp = PipelineBackpressureHandler()
    bp.register_pipeline("pipeline-1")
    bp.register_pipeline("pipeline-2")
    pipelines = bp.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    bp = PipelineBackpressureHandler()
    fired = []
    bp.on_change("mon", lambda a, d: fired.append(a))
    bp.register_pipeline("pipeline-1")
    assert len(fired) >= 1
    assert bp.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    bp = PipelineBackpressureHandler()
    bp.register_pipeline("pipeline-1")
    stats = bp.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    bp = PipelineBackpressureHandler()
    bp.register_pipeline("pipeline-1")
    bp.reset()
    assert bp.get_pipeline_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Backpressure Handler Tests ===\n")
    test_register_pipeline()
    test_record_depth()
    test_is_throttled_false()
    test_is_throttled_true()
    test_get_pressure()
    test_get_current_depth()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
