"""Tests for AgentTaskTemplate service."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_template import AgentTaskTemplate


def test_register_template():
    mgr = AgentTaskTemplate()
    tid = mgr.register_template("build", "ci")
    assert tid.startswith("att-")
    assert mgr.get_template_count() == 1


def test_register_template_with_params():
    mgr = AgentTaskTemplate()
    tid = mgr.register_template("deploy", "cd", default_params={"env": "staging"}, metadata={"owner": "ops"})
    t = mgr.get_template(tid)
    assert t["name"] == "deploy"
    assert t["task_type"] == "cd"
    assert t["default_params"] == {"env": "staging"}
    assert t["metadata"] == {"owner": "ops"}
    assert t["usage_count"] == 0


def test_get_template_not_found():
    mgr = AgentTaskTemplate()
    assert mgr.get_template("att-nonexistent") == {}


def test_instantiate_basic():
    mgr = AgentTaskTemplate()
    tid = mgr.register_template("test", "unit", default_params={"timeout": 30})
    inst = mgr.instantiate(tid)
    assert inst["template_id"] == tid
    assert inst["task_type"] == "unit"
    assert inst["params"] == {"timeout": 30}
    assert inst["instance_id"].startswith("att-")


def test_instantiate_with_overrides():
    mgr = AgentTaskTemplate()
    tid = mgr.register_template("test", "unit", default_params={"timeout": 30, "retries": 3})
    inst = mgr.instantiate(tid, overrides={"timeout": 60, "verbose": True})
    assert inst["params"]["timeout"] == 60
    assert inst["params"]["retries"] == 3
    assert inst["params"]["verbose"] is True


def test_instantiate_increments_usage():
    mgr = AgentTaskTemplate()
    tid = mgr.register_template("test", "unit")
    mgr.instantiate(tid)
    mgr.instantiate(tid)
    mgr.instantiate(tid)
    t = mgr.get_template(tid)
    assert t["usage_count"] == 3


def test_instantiate_not_found():
    mgr = AgentTaskTemplate()
    result = mgr.instantiate("att-missing")
    assert result == {}


def test_get_templates_all():
    mgr = AgentTaskTemplate()
    mgr.register_template("a", "ci")
    mgr.register_template("b", "cd")
    mgr.register_template("c", "ci")
    assert len(mgr.get_templates()) == 3


def test_get_templates_filtered():
    mgr = AgentTaskTemplate()
    mgr.register_template("a", "ci")
    mgr.register_template("b", "cd")
    mgr.register_template("c", "ci")
    ci_templates = mgr.get_templates(task_type="ci")
    assert len(ci_templates) == 2
    assert all(t["task_type"] == "ci" for t in ci_templates)


def test_get_template_count():
    mgr = AgentTaskTemplate()
    assert mgr.get_template_count() == 0
    mgr.register_template("x", "t")
    mgr.register_template("y", "t")
    assert mgr.get_template_count() == 2


def test_remove_template():
    mgr = AgentTaskTemplate()
    tid = mgr.register_template("rm", "test")
    assert mgr.remove_template(tid) is True
    assert mgr.get_template_count() == 0
    assert mgr.get_template(tid) == {}


def test_remove_template_not_found():
    mgr = AgentTaskTemplate()
    assert mgr.remove_template("att-nope") is False


def test_get_most_used():
    mgr = AgentTaskTemplate()
    t1 = mgr.register_template("a", "ci")
    t2 = mgr.register_template("b", "ci")
    t3 = mgr.register_template("c", "ci")
    for _ in range(5):
        mgr.instantiate(t2)
    for _ in range(3):
        mgr.instantiate(t1)
    for _ in range(1):
        mgr.instantiate(t3)
    most = mgr.get_most_used(limit=2)
    assert len(most) == 2
    assert most[0]["usage_count"] == 5
    assert most[1]["usage_count"] == 3


def test_get_stats():
    mgr = AgentTaskTemplate()
    t1 = mgr.register_template("a", "ci")
    t2 = mgr.register_template("b", "cd")
    mgr.instantiate(t1)
    mgr.instantiate(t1)
    mgr.instantiate(t2)
    stats = mgr.get_stats()
    assert stats["total_templates"] == 2
    assert stats["total_instantiations"] == 3
    assert stats["unique_task_types"] == 2


def test_reset():
    mgr = AgentTaskTemplate()
    mgr.register_template("x", "t")
    mgr.on_change = lambda e, d: None
    mgr.register_callback("cb1", lambda e, d: None)
    mgr.reset()
    assert mgr.get_template_count() == 0
    assert mgr.on_change is None


def test_on_change_callback():
    events = []
    mgr = AgentTaskTemplate()
    mgr.on_change = lambda e, d: events.append((e, d))
    tid = mgr.register_template("x", "t")
    mgr.instantiate(tid)
    mgr.remove_template(tid)
    assert len(events) == 3
    assert events[0][0] == "template_registered"
    assert events[1][0] == "template_instantiated"
    assert events[2][0] == "template_removed"


def test_remove_callback():
    mgr = AgentTaskTemplate()
    mgr.register_callback("cb1", lambda e, d: None)
    assert mgr.remove_callback("cb1") is True
    assert mgr.remove_callback("cb1") is False


def test_unique_ids():
    mgr = AgentTaskTemplate()
    ids = set()
    for i in range(20):
        tid = mgr.register_template(f"tmpl_{i}", "ci")
        ids.add(tid)
    assert len(ids) == 20


def test_instantiate_does_not_mutate_defaults():
    mgr = AgentTaskTemplate()
    tid = mgr.register_template("test", "unit", default_params={"a": 1, "b": 2})
    mgr.instantiate(tid, overrides={"a": 99, "c": 3})
    t = mgr.get_template(tid)
    assert t["default_params"] == {"a": 1, "b": 2}


if __name__ == "__main__":
    tests = [
        test_register_template,
        test_register_template_with_params,
        test_get_template_not_found,
        test_instantiate_basic,
        test_instantiate_with_overrides,
        test_instantiate_increments_usage,
        test_instantiate_not_found,
        test_get_templates_all,
        test_get_templates_filtered,
        test_get_template_count,
        test_remove_template,
        test_remove_template_not_found,
        test_get_most_used,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_unique_ids,
        test_instantiate_does_not_mutate_defaults,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")
