"""Test pipeline load balancer -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_load_balancer import PipelineLoadBalancer


def test_register_instance():
    lb = PipelineLoadBalancer()
    rid = lb.register_instance("pipeline-1", "inst-a", capacity=100)
    assert len(rid) > 0
    assert rid.startswith("plb-")
    print("OK: register instance")


def test_get_instance():
    lb = PipelineLoadBalancer()
    rid = lb.register_instance("pipeline-1", "inst-a", capacity=100)
    inst = lb.get_instance(rid)
    assert inst is not None
    assert inst["pipeline_id"] == "pipeline-1"
    assert inst["instance_id"] == "inst-a"
    assert inst["capacity"] == 100
    assert lb.get_instance("nonexistent") is None
    print("OK: get instance")


def test_route_request():
    lb = PipelineLoadBalancer()
    lb.register_instance("pipeline-1", "inst-a", capacity=100)
    lb.register_instance("pipeline-1", "inst-b", capacity=100)
    lb.record_load("pipeline-1", "inst-a", 80)
    lb.record_load("pipeline-1", "inst-b", 20)
    routed = lb.route_request("pipeline-1")
    assert routed == "inst-b"  # Least loaded
    print("OK: route request")


def test_record_load():
    lb = PipelineLoadBalancer()
    lb.register_instance("pipeline-1", "inst-a", capacity=100)
    assert lb.record_load("pipeline-1", "inst-a", 50) is True
    assert lb.record_load("pipeline-1", "nonexistent", 50) is False
    print("OK: record load")


def test_get_instance_load():
    lb = PipelineLoadBalancer()
    lb.register_instance("pipeline-1", "inst-a", capacity=100)
    lb.record_load("pipeline-1", "inst-a", 75)
    load = lb.get_instance_load("pipeline-1", "inst-a")
    assert load == 75.0
    print("OK: get instance load")


def test_get_pipeline_instances():
    lb = PipelineLoadBalancer()
    lb.register_instance("pipeline-1", "inst-a")
    lb.register_instance("pipeline-1", "inst-b")
    lb.register_instance("pipeline-2", "inst-c")
    instances = lb.get_pipeline_instances("pipeline-1")
    assert len(instances) == 2
    print("OK: get pipeline instances")


def test_remove_instance():
    lb = PipelineLoadBalancer()
    rid = lb.register_instance("pipeline-1", "inst-a")
    assert lb.remove_instance(rid) is True
    assert lb.remove_instance(rid) is False
    print("OK: remove instance")


def test_list_pipelines():
    lb = PipelineLoadBalancer()
    lb.register_instance("pipeline-1", "inst-a")
    lb.register_instance("pipeline-2", "inst-b")
    pipelines = lb.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    lb = PipelineLoadBalancer()
    fired = []
    lb.on_change("mon", lambda a, d: fired.append(a))
    lb.register_instance("pipeline-1", "inst-a")
    assert len(fired) >= 1
    assert lb.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    lb = PipelineLoadBalancer()
    lb.register_instance("pipeline-1", "inst-a")
    stats = lb.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    lb = PipelineLoadBalancer()
    lb.register_instance("pipeline-1", "inst-a")
    lb.reset()
    assert lb.get_instance_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Load Balancer Tests ===\n")
    test_register_instance()
    test_get_instance()
    test_route_request()
    test_record_load()
    test_get_instance_load()
    test_get_pipeline_instances()
    test_remove_instance()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 11 TESTS PASSED ===")


if __name__ == "__main__":
    main()
