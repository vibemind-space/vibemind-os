"""Test pipeline cost optimizer -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_cost_optimizer import PipelineCostOptimizer


def test_register_resource():
    co = PipelineCostOptimizer()
    rid = co.register_resource("gpu_compute", unit_cost=2.5, resource_type="compute")
    assert rid.startswith("cor-")
    r = co.get_resource("gpu_compute")
    assert r["name"] == "gpu_compute"
    assert r["unit_cost"] == 2.5
    assert r["total_cost"] == 0.0
    assert co.register_resource("gpu_compute") == ""  # dup
    print("OK: register resource")


def test_record_usage():
    co = PipelineCostOptimizer()
    co.register_resource("gpu", unit_cost=2.0)
    uid = co.record_usage("gpu", 10.0, context="training batch 1")
    assert uid.startswith("cus-")
    r = co.get_resource("gpu")
    assert r["total_usage"] == 10.0
    assert r["total_cost"] == 20.0  # 10 * 2.0
    assert r["usage_count"] == 1
    print("OK: record usage")


def test_cost_breakdown():
    co = PipelineCostOptimizer()
    co.register_resource("gpu", unit_cost=2.0)
    co.register_resource("storage", unit_cost=0.5)
    co.record_usage("gpu", 10.0)
    co.record_usage("storage", 100.0)
    bd = co.get_cost_breakdown()
    assert bd["total"] == 70.0  # 20 + 50
    assert bd["by_resource"]["gpu"] == 20.0
    assert bd["by_resource"]["storage"] == 50.0
    # per-resource breakdown
    bd2 = co.get_cost_breakdown(resource_name="gpu")
    assert bd2["total"] == 20.0
    print("OK: cost breakdown")


def test_budget():
    co = PipelineCostOptimizer()
    co.register_resource("gpu", unit_cost=1.0)
    assert co.set_budget("gpu", 100.0) is True
    co.record_usage("gpu", 80.0)
    check = co.check_budget("gpu")
    assert check["remaining"] == 20.0
    assert check["pct_used"] == 80.0
    assert check["over_budget"] is False
    co.record_usage("gpu", 25.0)
    check2 = co.check_budget("gpu")
    assert check2["over_budget"] is True
    print("OK: budget")


def test_top_spenders():
    co = PipelineCostOptimizer()
    co.register_resource("gpu", unit_cost=10.0)
    co.register_resource("cpu", unit_cost=1.0)
    co.register_resource("storage", unit_cost=0.1)
    co.record_usage("gpu", 5.0)      # cost 50
    co.record_usage("cpu", 20.0)     # cost 20
    co.record_usage("storage", 100.0) # cost 10
    top = co.get_top_spenders(limit=2)
    assert len(top) == 2
    assert top[0]["name"] == "gpu"
    assert top[0]["total_cost"] == 50.0
    print("OK: top spenders")


def test_suggest_optimizations():
    co = PipelineCostOptimizer()
    co.register_resource("gpu", unit_cost=1.0)
    co.set_budget("gpu", 100.0)
    co.record_usage("gpu", 85.0)  # >80% budget
    co.register_resource("idle_svc", unit_cost=1.0)  # unused
    suggestions = co.suggest_optimizations()
    assert len(suggestions) >= 1
    print("OK: suggest optimizations")


def test_savings_plan():
    co = PipelineCostOptimizer()
    co.register_resource("gpu", unit_cost=1.0)
    pid = co.create_savings_plan("reduce_gpu", target_reduction_pct=30.0, resources=["gpu"])
    assert pid.startswith("csp-")
    plan = co.get_savings_plan("reduce_gpu")
    assert plan["name"] == "reduce_gpu"
    assert plan["target_reduction_pct"] == 30.0
    assert co.create_savings_plan("reduce_gpu") == ""  # dup
    assert len(co.list_savings_plans()) == 1
    print("OK: savings plan")


def test_list_resources():
    co = PipelineCostOptimizer()
    co.register_resource("gpu", resource_type="compute", tags=["ml"])
    co.register_resource("disk", resource_type="storage")
    assert len(co.list_resources()) == 2
    assert len(co.list_resources(resource_type="compute")) == 1
    assert len(co.list_resources(tag="ml")) == 1
    print("OK: list resources")


def test_remove_resource():
    co = PipelineCostOptimizer()
    co.register_resource("gpu")
    assert co.remove_resource("gpu") is True
    assert co.remove_resource("gpu") is False
    print("OK: remove resource")


def test_history():
    co = PipelineCostOptimizer()
    co.register_resource("gpu")
    co.record_usage("gpu", 10.0)
    hist = co.get_history()
    assert len(hist) >= 2
    print("OK: history")


def test_callbacks():
    co = PipelineCostOptimizer()
    fired = []
    co.on_change("mon", lambda a, d: fired.append(a))
    co.register_resource("gpu")
    assert "resource_registered" in fired
    assert co.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    co = PipelineCostOptimizer()
    co.register_resource("gpu", unit_cost=1.0)
    co.record_usage("gpu", 5.0)
    stats = co.get_stats()
    assert stats["total_resources_created"] >= 1
    assert stats["total_usage_recorded"] >= 1
    print("OK: stats")


def test_reset():
    co = PipelineCostOptimizer()
    co.register_resource("gpu")
    co.reset()
    assert co.list_resources() == []
    print("OK: reset")


def main():
    print("=== Pipeline Cost Optimizer Tests ===\n")
    test_register_resource()
    test_record_usage()
    test_cost_breakdown()
    test_budget()
    test_top_spenders()
    test_suggest_optimizations()
    test_savings_plan()
    test_list_resources()
    test_remove_resource()
    test_history()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
