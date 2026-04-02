"""Test pipeline canary deployer -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_canary_deployer import PipelineCanaryDeployer


def test_create_deployment():
    cd = PipelineCanaryDeployer()
    did = cd.create_deployment("api_v2", "v1.0", "v2.0", traffic_pct=10.0, tags=["api"])
    assert did.startswith("pcd-")
    d = cd.get_deployment("api_v2")
    assert d is not None
    assert d["name"] == "api_v2"
    assert d["canary_version"] == "v2.0"
    assert cd.create_deployment("api_v2", "v1", "v2") == ""  # dup
    print("OK: create deployment")


def test_update_traffic():
    cd = PipelineCanaryDeployer()
    cd.create_deployment("api_v2", "v1.0", "v2.0", traffic_pct=10.0)
    assert cd.update_traffic("api_v2", 50.0) is True
    d = cd.get_deployment("api_v2")
    assert d["traffic_pct"] == 50.0
    print("OK: update traffic")


def test_record_metric():
    cd = PipelineCanaryDeployer()
    cd.create_deployment("api_v2", "v1.0", "v2.0")
    assert cd.record_metric("api_v2", "baseline", "latency", 50.0) is True
    assert cd.record_metric("api_v2", "canary", "latency", 55.0) is True
    assert cd.record_metric("api_v2", "baseline", "error_rate", 1.0) is True
    assert cd.record_metric("api_v2", "canary", "error_rate", 2.0) is True
    print("OK: record metric")


def test_compare():
    cd = PipelineCanaryDeployer()
    cd.create_deployment("api_v2", "v1.0", "v2.0")
    cd.record_metric("api_v2", "baseline", "latency", 50.0)
    cd.record_metric("api_v2", "canary", "latency", 55.0)
    comp = cd.compare("api_v2")
    assert comp is not None
    assert len(comp) >= 1
    print("OK: compare")


def test_promote():
    cd = PipelineCanaryDeployer()
    cd.create_deployment("api_v2", "v1.0", "v2.0")
    assert cd.promote("api_v2") is True
    d = cd.get_deployment("api_v2")
    assert d["status"] == "promoted"
    print("OK: promote")


def test_rollback():
    cd = PipelineCanaryDeployer()
    cd.create_deployment("api_v2", "v1.0", "v2.0")
    assert cd.rollback("api_v2") is True
    d = cd.get_deployment("api_v2")
    assert d["status"] == "rolled_back"
    print("OK: rollback")


def test_should_rollback():
    cd = PipelineCanaryDeployer()
    cd.create_deployment("api_v2", "v1.0", "v2.0")
    cd.record_metric("api_v2", "baseline", "error_rate", 1.0)
    cd.record_metric("api_v2", "canary", "error_rate", 10.0)  # way above threshold
    assert cd.should_rollback("api_v2", error_threshold=5.0) is True
    print("OK: should rollback")


def test_list_deployments():
    cd = PipelineCanaryDeployer()
    cd.create_deployment("d1", "v1", "v2", tags=["api"])
    cd.create_deployment("d2", "v1", "v2")
    cd.promote("d1")
    assert len(cd.list_deployments()) == 2
    assert len(cd.list_deployments(status="promoted")) == 1
    assert len(cd.list_deployments(tag="api")) == 1
    print("OK: list deployments")


def test_remove_deployment():
    cd = PipelineCanaryDeployer()
    cd.create_deployment("d1", "v1", "v2")
    assert cd.remove_deployment("d1") is True
    assert cd.remove_deployment("d1") is False
    print("OK: remove deployment")


def test_history():
    cd = PipelineCanaryDeployer()
    cd.create_deployment("d1", "v1", "v2")
    hist = cd.get_history()
    assert len(hist) >= 1
    print("OK: history")


def test_callbacks():
    cd = PipelineCanaryDeployer()
    fired = []
    cd.on_change("mon", lambda a, d: fired.append(a))
    cd.create_deployment("d1", "v1", "v2")
    assert len(fired) >= 1
    assert cd.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    cd = PipelineCanaryDeployer()
    cd.create_deployment("d1", "v1", "v2")
    stats = cd.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    cd = PipelineCanaryDeployer()
    cd.create_deployment("d1", "v1", "v2")
    cd.reset()
    assert cd.list_deployments() == []
    print("OK: reset")


def main():
    print("=== Pipeline Canary Deployer Tests ===\n")
    test_create_deployment()
    test_update_traffic()
    test_record_metric()
    test_compare()
    test_promote()
    test_rollback()
    test_should_rollback()
    test_list_deployments()
    test_remove_deployment()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
