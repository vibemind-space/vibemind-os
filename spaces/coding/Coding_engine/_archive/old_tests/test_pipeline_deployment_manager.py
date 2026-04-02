"""Test pipeline deployment manager."""
import sys
sys.path.insert(0, ".")
from src.services.pipeline_deployment_manager import PipelineDeploymentManager

def test_create():
    dm = PipelineDeploymentManager()
    did = dm.create_deployment("api", "v1.0", tags=["prod"])
    assert did.startswith("dep-")
    d = dm.get_deployment(did)
    assert d["name"] == "api"
    assert d["status"] == "pending"
    print("OK: create")

def test_invalid():
    dm = PipelineDeploymentManager()
    assert dm.create_deployment("", "v1") == ""
    assert dm.create_deployment("x", "") == ""
    assert dm.create_deployment("x", "v1", strategy="invalid") == ""
    print("OK: invalid")

def test_deploy():
    dm = PipelineDeploymentManager()
    did = dm.create_deployment("api", "v1.0")
    assert dm.deploy(did) is True
    d = dm.get_deployment(did)
    assert d["status"] == "active"
    assert dm.deploy(did) is False  # already active
    print("OK: deploy")

def test_deploy_replaces_active():
    dm = PipelineDeploymentManager()
    d1 = dm.create_deployment("api", "v1.0", environment="prod")
    dm.deploy(d1)
    d2 = dm.create_deployment("api", "v2.0", environment="prod")
    dm.deploy(d2)
    assert dm.get_deployment(d1)["status"] == "rolled_back"
    assert dm.get_deployment(d2)["status"] == "active"
    print("OK: deploy replaces active")

def test_rollback():
    dm = PipelineDeploymentManager()
    did = dm.create_deployment("api", "v1.0", environment="prod")
    dm.deploy(did)
    assert dm.rollback("prod") is True
    assert dm.get_deployment(did)["status"] == "rolled_back"
    assert dm.get_active("prod") is None
    assert dm.rollback("prod") is False  # nothing active
    print("OK: rollback")

def test_fail():
    dm = PipelineDeploymentManager()
    did = dm.create_deployment("api", "v1.0")
    assert dm.fail_deployment(did) is True
    assert dm.get_deployment(did)["status"] == "failed"
    print("OK: fail")

def test_get_active():
    dm = PipelineDeploymentManager()
    did = dm.create_deployment("api", "v1.0", environment="staging")
    dm.deploy(did)
    active = dm.get_active("staging")
    assert active is not None
    assert active["version"] == "v1.0"
    assert dm.get_active("nonexistent") is None
    print("OK: get active")

def test_list():
    dm = PipelineDeploymentManager()
    dm.create_deployment("api", "v1", environment="prod", tags=["release"])
    dm.create_deployment("web", "v1", environment="staging")
    assert len(dm.list_deployments()) == 2
    assert len(dm.list_deployments(name="api")) == 1
    assert len(dm.list_deployments(environment="staging")) == 1
    assert len(dm.list_deployments(tag="release")) == 1
    print("OK: list")

def test_history():
    dm = PipelineDeploymentManager()
    did = dm.create_deployment("api", "v1")
    dm.deploy(did)
    hist = dm.get_history()
    assert len(hist) == 2
    limited = dm.get_history(limit=1)
    assert len(limited) == 1
    print("OK: history")

def test_callback():
    dm = PipelineDeploymentManager()
    fired = []
    dm.on_change("mon", lambda a, d: fired.append(a))
    did = dm.create_deployment("api", "v1")
    assert "deployment_created" in fired
    dm.deploy(did)
    assert "deployment_active" in fired
    print("OK: callback")

def test_callbacks():
    dm = PipelineDeploymentManager()
    assert dm.on_change("m", lambda a, d: None) is True
    assert dm.on_change("m", lambda a, d: None) is False
    assert dm.remove_callback("m") is True
    assert dm.remove_callback("m") is False
    print("OK: callbacks")

def test_stats():
    dm = PipelineDeploymentManager()
    did = dm.create_deployment("api", "v1")
    dm.deploy(did)
    stats = dm.get_stats()
    assert stats["current_deployments"] == 1
    assert stats["active_deployments"] == 1
    assert stats["total_created"] == 1
    print("OK: stats")

def test_reset():
    dm = PipelineDeploymentManager()
    dm.create_deployment("api", "v1")
    dm.reset()
    assert dm.list_deployments() == []
    print("OK: reset")

def main():
    print("=== Pipeline Deployment Manager Tests ===\n")
    test_create()
    test_invalid()
    test_deploy()
    test_deploy_replaces_active()
    test_rollback()
    test_fail()
    test_get_active()
    test_list()
    test_history()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")

if __name__ == "__main__":
    main()
