"""Test pipeline routing store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_routing_store import PipelineRoutingStore


def test_add_rule():
    rs = PipelineRoutingStore()
    rid = rs.add_rule("deploy", "env==prod", "prod-cluster", priority=1, metadata={"region": "us"})
    assert len(rid) > 0
    assert rid.startswith("prs-")
    r = rs.get_rule(rid)
    assert r is not None
    assert r["pipeline_name"] == "deploy"
    assert r["target"] == "prod-cluster"
    print("OK: add rule")


def test_enable_disable():
    rs = PipelineRoutingStore()
    rid = rs.add_rule("deploy", "env==prod", "prod")
    assert rs.disable_rule(rid) is True
    r = rs.get_rule(rid)
    assert r["enabled"] is False
    assert rs.enable_rule(rid) is True
    r = rs.get_rule(rid)
    assert r["enabled"] is True
    print("OK: enable/disable")


def test_delete_rule():
    rs = PipelineRoutingStore()
    rid = rs.add_rule("deploy", "cond", "target")
    assert rs.delete_rule(rid) is True
    assert rs.delete_rule(rid) is False
    print("OK: delete rule")


def test_get_rules_for_pipeline():
    rs = PipelineRoutingStore()
    rs.add_rule("deploy", "c1", "t1")
    rs.add_rule("deploy", "c2", "t2")
    rid3 = rs.add_rule("deploy", "c3", "t3")
    rs.disable_rule(rid3)
    rs.add_rule("test", "c4", "t4")
    rules = rs.get_rules_for_pipeline("deploy")
    assert len(rules) == 2  # Only enabled
    print("OK: get rules for pipeline")


def test_resolve_route():
    rs = PipelineRoutingStore()
    rs.add_rule("deploy", "default", "default-target", priority=1)
    rs.add_rule("deploy", "priority", "fast-target", priority=10)
    target = rs.resolve_route("deploy")
    assert target == "fast-target"  # Higher priority (higher number)
    assert rs.resolve_route("nonexistent") is None
    print("OK: resolve route")


def test_list_rules():
    rs = PipelineRoutingStore()
    rs.add_rule("deploy", "c1", "t1")
    rid2 = rs.add_rule("test", "c2", "t2")
    rs.disable_rule(rid2)
    all_r = rs.list_rules()
    assert len(all_r) == 2
    enabled = rs.list_rules(enabled_only=True)
    assert len(enabled) == 1
    deploy_r = rs.list_rules(pipeline_name="deploy")
    assert len(deploy_r) == 1
    print("OK: list rules")


def test_update_rule():
    rs = PipelineRoutingStore()
    rid = rs.add_rule("deploy", "old-cond", "old-target", priority=5)
    assert rs.update_rule(rid, target="new-target", priority=1) is True
    r = rs.get_rule(rid)
    assert r["target"] == "new-target"
    assert r["priority"] == 1
    assert rs.update_rule("nonexistent", target="x") is False
    print("OK: update rule")


def test_callbacks():
    rs = PipelineRoutingStore()
    fired = []
    rs.on_change("mon", lambda a, d: fired.append(a))
    rs.add_rule("deploy", "c", "t")
    assert len(fired) >= 1
    assert rs.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    rs = PipelineRoutingStore()
    rs.add_rule("deploy", "c", "t")
    stats = rs.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    rs = PipelineRoutingStore()
    rs.add_rule("deploy", "c", "t")
    rs.reset()
    assert rs.list_rules() == []
    print("OK: reset")


def main():
    print("=== Pipeline Routing Store Tests ===\n")
    test_add_rule()
    test_enable_disable()
    test_delete_rule()
    test_get_rules_for_pipeline()
    test_resolve_route()
    test_list_rules()
    test_update_rule()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
