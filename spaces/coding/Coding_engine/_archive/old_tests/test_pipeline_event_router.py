"""Test pipeline event router -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_event_router import PipelineEventRouter


def test_register_route():
    er = PipelineEventRouter()
    rid = er.register_route("deploy.started", "logging-pipeline", priority=10)
    assert len(rid) > 0
    assert rid.startswith("per-")
    print("OK: register route")


def test_get_route():
    er = PipelineEventRouter()
    rid = er.register_route("deploy.started", "logging-pipeline", priority=10)
    route = er.get_route(rid)
    assert route is not None
    assert route["event_type"] == "deploy.started"
    assert route["target_pipeline"] == "logging-pipeline"
    assert route["enabled"] is True
    assert er.get_route("nonexistent") is None
    print("OK: get route")


def test_resolve_targets():
    er = PipelineEventRouter()
    er.register_route("deploy.started", "logging", priority=5)
    er.register_route("deploy.started", "metrics", priority=10)
    er.register_route("deploy.started", "alerts", priority=1)
    targets = er.resolve_targets("deploy.started")
    assert targets == ["metrics", "logging", "alerts"]
    print("OK: resolve targets")


def test_disable_enable():
    er = PipelineEventRouter()
    rid = er.register_route("deploy.started", "logging", priority=5)
    assert er.disable_route(rid) is True
    assert len(er.resolve_targets("deploy.started")) == 0
    assert er.enable_route(rid) is True
    assert len(er.resolve_targets("deploy.started")) == 1
    print("OK: disable/enable")


def test_delete_route():
    er = PipelineEventRouter()
    rid = er.register_route("deploy.started", "logging")
    assert er.delete_route(rid) is True
    assert er.delete_route(rid) is False
    print("OK: delete route")


def test_get_routes_for_event():
    er = PipelineEventRouter()
    er.register_route("deploy.started", "logging")
    er.register_route("deploy.started", "metrics")
    er.register_route("build.completed", "notify")
    routes = er.get_routes_for_event("deploy.started")
    assert len(routes) == 2
    print("OK: get routes for event")


def test_list_event_types():
    er = PipelineEventRouter()
    er.register_route("deploy.started", "logging")
    er.register_route("build.completed", "notify")
    types = er.list_event_types()
    assert "deploy.started" in types
    assert "build.completed" in types
    print("OK: list event types")


def test_callbacks():
    er = PipelineEventRouter()
    fired = []
    er.on_change("mon", lambda a, d: fired.append(a))
    er.register_route("deploy.started", "logging")
    assert len(fired) >= 1
    assert er.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    er = PipelineEventRouter()
    er.register_route("deploy.started", "logging")
    stats = er.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    er = PipelineEventRouter()
    er.register_route("deploy.started", "logging")
    er.reset()
    assert er.get_route_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Event Router Tests ===\n")
    test_register_route()
    test_get_route()
    test_resolve_targets()
    test_disable_enable()
    test_delete_route()
    test_get_routes_for_event()
    test_list_event_types()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
