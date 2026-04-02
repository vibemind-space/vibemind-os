"""Test pipeline output router -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_output_router import PipelineOutputRouter


def test_add_route():
    pr = PipelineOutputRouter()
    rid = pr.add_route("pipeline-1", "logs", "elasticsearch")
    assert len(rid) > 0
    assert rid.startswith("por-")
    print("OK: add route")


def test_add_multiple_routes():
    pr = PipelineOutputRouter()
    pr.add_route("pipeline-1", "logs", "elasticsearch")
    pr.add_route("pipeline-1", "logs", "s3")
    pr.add_route("pipeline-1", "metrics", "prometheus")
    routes = pr.get_routes("pipeline-1")
    assert len(routes) == 3
    print("OK: add multiple routes")


def test_remove_route():
    pr = PipelineOutputRouter()
    rid = pr.add_route("pipeline-1", "logs", "elasticsearch")
    assert pr.remove_route(rid) is True
    assert pr.remove_route("nonexistent") is False
    print("OK: remove route")


def test_route_output():
    pr = PipelineOutputRouter()
    pr.add_route("pipeline-1", "logs", "elasticsearch")
    pr.add_route("pipeline-1", "logs", "s3")
    destinations = pr.route_output("pipeline-1", "logs", {"message": "test"})
    assert "elasticsearch" in destinations
    assert "s3" in destinations
    assert len(destinations) == 2
    print("OK: route output")


def test_route_output_no_routes():
    pr = PipelineOutputRouter()
    destinations = pr.route_output("pipeline-1", "logs", {"message": "test"})
    assert len(destinations) == 0
    print("OK: route output no routes")


def test_get_routes_filtered():
    pr = PipelineOutputRouter()
    pr.add_route("pipeline-1", "logs", "elasticsearch")
    pr.add_route("pipeline-1", "metrics", "prometheus")
    log_routes = pr.get_routes("pipeline-1", output_type="logs")
    assert len(log_routes) == 1
    print("OK: get routes filtered")


def test_list_pipelines():
    pr = PipelineOutputRouter()
    pr.add_route("pipeline-1", "logs", "es")
    pr.add_route("pipeline-2", "metrics", "prom")
    pipelines = pr.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    pr = PipelineOutputRouter()
    fired = []
    pr.on_change("mon", lambda a, d: fired.append(a))
    pr.add_route("pipeline-1", "logs", "es")
    assert len(fired) >= 1
    assert pr.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    pr = PipelineOutputRouter()
    pr.add_route("pipeline-1", "logs", "es")
    stats = pr.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    pr = PipelineOutputRouter()
    pr.add_route("pipeline-1", "logs", "es")
    pr.reset()
    assert pr.get_route_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Output Router Tests ===\n")
    test_add_route()
    test_add_multiple_routes()
    test_remove_route()
    test_route_output()
    test_route_output_no_routes()
    test_get_routes_filtered()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
