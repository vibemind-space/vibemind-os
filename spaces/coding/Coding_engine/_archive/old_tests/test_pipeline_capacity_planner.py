"""Test pipeline capacity planner -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_capacity_planner import PipelineCapacityPlanner


def test_set_capacity():
    cp = PipelineCapacityPlanner()
    pid = cp.set_capacity("deploy", "cpu", 100, 200)
    assert len(pid) > 0
    assert pid.startswith("pcp-")
    print("OK: set capacity")


def test_get_capacity():
    cp = PipelineCapacityPlanner()
    cp.set_capacity("deploy", "cpu", 100, 200)
    cap = cp.get_capacity("deploy", "cpu")
    assert cap is not None
    assert cap["pipeline_id"] == "deploy"
    assert cap["current_capacity"] == 100
    assert cap["max_capacity"] == 200
    assert cp.get_capacity("nonexistent", "cpu") is None
    print("OK: get capacity")


def test_record_load():
    cp = PipelineCapacityPlanner()
    cp.set_capacity("deploy", "cpu", 100, 200)
    assert cp.record_load("deploy", "cpu", 80) is True
    assert cp.record_load("nonexistent", "cpu", 50) is False
    print("OK: record load")


def test_get_headroom():
    cp = PipelineCapacityPlanner()
    cp.set_capacity("deploy", "cpu", 100, 200)
    cp.record_load("deploy", "cpu", 60)
    assert cp.get_headroom("deploy", "cpu") == 40
    assert cp.get_headroom("nonexistent", "cpu") == 0.0
    print("OK: get headroom")


def test_needs_scaling():
    cp = PipelineCapacityPlanner()
    cp.set_capacity("deploy", "cpu", 100, 200)
    cp.record_load("deploy", "cpu", 90)
    assert cp.needs_scaling("deploy", "cpu", threshold=0.8) is True
    cp.record_load("deploy", "cpu", 50)
    assert cp.needs_scaling("deploy", "cpu", threshold=0.8) is False
    print("OK: needs scaling")


def test_scale_up():
    cp = PipelineCapacityPlanner()
    cp.set_capacity("deploy", "cpu", 100, 200)
    assert cp.scale_up("deploy", "cpu", 50) is True
    cap = cp.get_capacity("deploy", "cpu")
    assert cap["current_capacity"] == 150
    assert cp.scale_up("deploy", "cpu", 100) is True  # Should cap at max=200
    cap2 = cp.get_capacity("deploy", "cpu")
    assert cap2["current_capacity"] == 200
    assert cp.scale_up("deploy", "cpu", 10) is False  # Already at max
    print("OK: scale up")


def test_get_utilization():
    cp = PipelineCapacityPlanner()
    cp.set_capacity("deploy", "cpu", 100, 200)
    cp.record_load("deploy", "cpu", 25)
    assert cp.get_utilization("deploy", "cpu") == 0.25
    assert cp.get_utilization("nonexistent", "cpu") == 0.0
    print("OK: get utilization")


def test_remove_capacity():
    cp = PipelineCapacityPlanner()
    cp.set_capacity("deploy", "cpu", 100, 200)
    assert cp.remove_capacity("deploy", "cpu") is True
    assert cp.remove_capacity("deploy", "cpu") is False
    print("OK: remove capacity")


def test_list_pipelines():
    cp = PipelineCapacityPlanner()
    cp.set_capacity("deploy", "cpu", 100, 200)
    cp.set_capacity("build", "memory", 50, 100)
    pipes = cp.list_pipelines()
    assert "deploy" in pipes
    assert "build" in pipes
    print("OK: list pipelines")


def test_get_pipeline_capacities():
    cp = PipelineCapacityPlanner()
    cp.set_capacity("deploy", "cpu", 100, 200)
    cp.set_capacity("deploy", "memory", 50, 100)
    caps = cp.get_pipeline_capacities("deploy")
    assert len(caps) == 2
    print("OK: get pipeline capacities")


def test_callbacks():
    cp = PipelineCapacityPlanner()
    fired = []
    cp.on_change("mon", lambda a, d: fired.append(a))
    cp.set_capacity("deploy", "cpu", 100, 200)
    assert len(fired) >= 1
    assert cp.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cp = PipelineCapacityPlanner()
    cp.set_capacity("deploy", "cpu", 100, 200)
    stats = cp.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cp = PipelineCapacityPlanner()
    cp.set_capacity("deploy", "cpu", 100, 200)
    cp.reset()
    assert cp.get_plan_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Capacity Planner Tests ===\n")
    test_set_capacity()
    test_get_capacity()
    test_record_load()
    test_get_headroom()
    test_needs_scaling()
    test_scale_up()
    test_get_utilization()
    test_remove_capacity()
    test_list_pipelines()
    test_get_pipeline_capacities()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
