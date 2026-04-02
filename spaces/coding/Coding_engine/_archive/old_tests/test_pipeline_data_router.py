"""Test pipeline data router."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_router import PipelineDataRouter


def test_create_route():
    """Create and retrieve route."""
    dr = PipelineDataRouter()
    rid = dr.create_route("build_to_test", source="builder", destination="tester",
                           tags=["ci"])
    assert rid.startswith("rte-")

    r = dr.get_route(rid)
    assert r is not None
    assert r["name"] == "build_to_test"
    assert r["source"] == "builder"
    assert r["destination"] == "tester"
    assert r["active"] is True

    assert dr.remove_route(rid) is True
    assert dr.remove_route(rid) is False
    print("OK: create route")


def test_invalid_route():
    """Invalid route rejected."""
    dr = PipelineDataRouter()
    assert dr.create_route("", source="x") == ""
    assert dr.create_route("x", source="") == ""
    assert dr.create_route("x", source="s", mode="invalid") == ""
    print("OK: invalid route")


def test_duplicate():
    """Duplicate name rejected."""
    dr = PipelineDataRouter()
    dr.create_route("r1", source="s")
    assert dr.create_route("r1", source="s") == ""
    print("OK: duplicate")


def test_max_routes():
    """Max routes enforced."""
    dr = PipelineDataRouter(max_routes=2)
    dr.create_route("a", source="s1")
    dr.create_route("b", source="s2")
    assert dr.create_route("c", source="s3") == ""
    print("OK: max routes")


def test_route_data():
    """Route data from source."""
    dr = PipelineDataRouter()
    dr.create_route("r1", source="builder", destination="tester")

    count = dr.route("builder", payload={"artifact": "build.zip"})
    assert count == 1
    print("OK: route data")


def test_route_no_match():
    """Route with no matching source."""
    dr = PipelineDataRouter()
    dr.create_route("r1", source="builder", destination="tester")
    count = dr.route("deployer", payload="x")
    assert count == 0
    print("OK: route no match")


def test_route_multiple():
    """Multiple routes from same source."""
    dr = PipelineDataRouter()
    dr.create_route("r1", source="builder", destination="tester")
    dr.create_route("r2", source="builder", destination="deployer")

    count = dr.route("builder", payload="artifact")
    assert count == 2
    print("OK: route multiple")


def test_content_filter():
    """Content-based filtering."""
    dr = PipelineDataRouter()
    dr.create_route("r1", source="builder", destination="tester", pattern="test")

    count = dr.route("builder", payload="x", content_key="run tests")
    assert count == 1

    count = dr.route("builder", payload="x", content_key="deploy now")
    assert count == 0
    print("OK: content filter")


def test_disable_enable():
    """Disable and enable route."""
    dr = PipelineDataRouter()
    rid = dr.create_route("r1", source="builder", destination="tester")

    assert dr.disable_route(rid) is True
    assert dr.disable_route(rid) is False
    count = dr.route("builder", payload="x")
    assert count == 0

    assert dr.enable_route(rid) is True
    assert dr.enable_route(rid) is False
    count = dr.route("builder", payload="x")
    assert count == 1
    print("OK: disable enable")


def test_update_route():
    """Update route properties."""
    dr = PipelineDataRouter()
    rid = dr.create_route("r1", source="builder", destination="old")

    assert dr.update_route(rid, destination="new", pattern="build") is True
    r = dr.get_route(rid)
    assert r["destination"] == "new"
    assert r["pattern"] == "build"

    assert dr.update_route("nonexistent") is False
    print("OK: update route")


def test_get_by_name():
    """Get route by name."""
    dr = PipelineDataRouter()
    dr.create_route("my_route", source="s")

    r = dr.get_route_by_name("my_route")
    assert r is not None
    assert r["name"] == "my_route"
    assert dr.get_route_by_name("nonexistent") is None
    print("OK: get by name")


def test_list_routes():
    """List routes with filters."""
    dr = PipelineDataRouter()
    dr.create_route("r1", source="builder", destination="tester", tags=["ci"])
    rid2 = dr.create_route("r2", source="deployer", destination="monitor")
    dr.disable_route(rid2)

    all_r = dr.list_routes()
    assert len(all_r) == 2

    by_source = dr.list_routes(source="builder")
    assert len(by_source) == 1

    by_dest = dr.list_routes(destination="monitor")
    assert len(by_dest) == 1

    by_active = dr.list_routes(active=True)
    assert len(by_active) == 1

    by_tag = dr.list_routes(tag="ci")
    assert len(by_tag) == 1
    print("OK: list routes")


def test_routing_history():
    """Routing history recorded."""
    dr = PipelineDataRouter()
    dr.create_route("r1", source="builder", destination="tester")
    dr.route("builder", payload={"v": 1})
    dr.route("builder", payload={"v": 2})

    history = dr.get_routing_history()
    assert len(history) == 2

    by_source = dr.get_routing_history(source="builder")
    assert len(by_source) == 2

    by_dest = dr.get_routing_history(destination="tester")
    assert len(by_dest) == 2
    print("OK: routing history")


def test_callback():
    """Callback fires on events."""
    dr = PipelineDataRouter()
    fired = []
    dr.on_change("mon", lambda a, d: fired.append(a))

    dr.create_route("r1", source="builder")
    assert "route_created" in fired

    dr.route("builder", payload="x")
    assert "data_routed" in fired
    print("OK: callback")


def test_callbacks():
    """Callback registration."""
    dr = PipelineDataRouter()
    assert dr.on_change("mon", lambda a, d: None) is True
    assert dr.on_change("mon", lambda a, d: None) is False
    assert dr.remove_callback("mon") is True
    assert dr.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    dr = PipelineDataRouter()
    dr.create_route("r1", source="builder", destination="tester")
    dr.route("builder", payload="x")

    stats = dr.get_stats()
    assert stats["total_routes"] == 1
    assert stats["total_routed"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    dr = PipelineDataRouter()
    dr.create_route("r1", source="builder")
    dr.route("builder", payload="x")

    dr.reset()
    assert dr.list_routes() == []
    assert dr.get_routing_history() == []
    stats = dr.get_stats()
    assert stats["current_routes"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Data Router Tests ===\n")
    test_create_route()
    test_invalid_route()
    test_duplicate()
    test_max_routes()
    test_route_data()
    test_route_no_match()
    test_route_multiple()
    test_content_filter()
    test_disable_enable()
    test_update_route()
    test_get_by_name()
    test_list_routes()
    test_routing_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
