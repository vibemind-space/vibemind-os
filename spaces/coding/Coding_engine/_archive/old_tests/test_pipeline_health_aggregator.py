"""Test pipeline health aggregator -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_health_aggregator import PipelineHealthAggregator


def test_register_component():
    ha = PipelineHealthAggregator()
    cid = ha.register_component("api_gateway", component_type="service", tags=["core"])
    assert cid.startswith("phc-")
    c = ha.get_component("api_gateway")
    assert c is not None
    assert c["name"] == "api_gateway"
    assert ha.register_component("api_gateway") == cid  # dup returns existing id
    print("OK: register component")


def test_report_health():
    ha = PipelineHealthAggregator()
    ha.register_component("api_gw")
    assert ha.report_health("api_gw", status="healthy", latency=50.0, error_rate=0.01) is True
    c = ha.get_component("api_gw")
    assert c["current_status"] == "healthy"
    assert c["check_count"] == 1
    print("OK: report health")


def test_system_health():
    ha = PipelineHealthAggregator()
    ha.register_component("svc1")
    ha.register_component("svc2")
    ha.register_component("svc3")
    ha.report_health("svc1", status="healthy")
    ha.report_health("svc2", status="degraded")
    ha.report_health("svc3", status="unhealthy")
    health = ha.get_system_health()
    assert health["component_count"] == 3
    assert health["healthy_count"] == 1
    assert health["degraded_count"] == 1
    assert health["unhealthy_count"] == 1
    assert 0 <= health["health_score"] <= 100
    print("OK: system health")


def test_unhealthy_components():
    ha = PipelineHealthAggregator()
    ha.register_component("svc1")
    ha.register_component("svc2")
    ha.report_health("svc1", status="unhealthy")
    ha.report_health("svc2", status="healthy")
    unhealthy = ha.get_unhealthy_components()
    assert len(unhealthy) == 1
    assert unhealthy[0]["name"] == "svc1"
    print("OK: unhealthy components")


def test_degraded_components():
    ha = PipelineHealthAggregator()
    ha.register_component("svc1")
    ha.report_health("svc1", status="degraded")
    degraded = ha.get_degraded_components()
    assert len(degraded) == 1
    print("OK: degraded components")


def test_health_timeline():
    ha = PipelineHealthAggregator()
    ha.register_component("svc1")
    ha.report_health("svc1", status="healthy", latency=10.0)
    ha.report_health("svc1", status="degraded", latency=200.0)
    ha.report_health("svc1", status="healthy", latency=15.0)
    timeline = ha.get_health_timeline("svc1")
    assert len(timeline) == 3
    print("OK: health timeline")


def test_list_components():
    ha = PipelineHealthAggregator()
    ha.register_component("a", component_type="service", tags=["core"])
    ha.register_component("b", component_type="agent")
    ha.report_health("a", status="healthy")
    ha.report_health("b", status="degraded")
    assert len(ha.list_components()) == 2
    assert len(ha.list_components(component_type="service")) == 1
    assert len(ha.list_components(status="healthy")) == 1
    assert len(ha.list_components(tag="core")) == 1
    print("OK: list components")


def test_remove_component():
    ha = PipelineHealthAggregator()
    ha.register_component("svc1")
    assert ha.remove_component("svc1") is True
    assert ha.remove_component("svc1") is False
    print("OK: remove component")


def test_history():
    ha = PipelineHealthAggregator()
    ha.register_component("svc1")
    ha.report_health("svc1", status="healthy")
    hist = ha.get_history()
    assert len(hist) >= 1
    print("OK: history")


def test_callbacks():
    ha = PipelineHealthAggregator()
    fired = []
    ha.on_change("mon", lambda a, d: fired.append(a))
    ha.register_component("svc1")
    assert len(fired) >= 1
    assert ha.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ha = PipelineHealthAggregator()
    ha.register_component("svc1")
    stats = ha.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ha = PipelineHealthAggregator()
    ha.register_component("svc1")
    ha.reset()
    assert ha.list_components() == []
    print("OK: reset")


def main():
    print("=== Pipeline Health Aggregator Tests ===\n")
    test_register_component()
    test_report_health()
    test_system_health()
    test_unhealthy_components()
    test_degraded_components()
    test_health_timeline()
    test_list_components()
    test_remove_component()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 12 TESTS PASSED ===")


if __name__ == "__main__":
    main()
