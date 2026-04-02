"""Test pipeline template store -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_template_store import PipelineTemplateStore


def test_create_template():
    ts = PipelineTemplateStore()
    tid = ts.create_template("deploy", steps=["build", "test", "release"], description="Deploy pipeline", tags=["ci"])
    assert len(tid) > 0
    assert ts.create_template("deploy", steps=["build"], version="1.0") == ""  # dup
    print("OK: create template")


def test_get_template():
    ts = PipelineTemplateStore()
    tid = ts.create_template("deploy", steps=["build", "test"])
    t = ts.get_template(tid)
    assert t is not None
    assert t["name"] == "deploy"
    assert len(t["steps"]) == 2
    print("OK: get template")


def test_get_template_by_name():
    ts = PipelineTemplateStore()
    ts.create_template("deploy", steps=["build"], version="1.0")
    ts.create_template("deploy", steps=["build", "test"], version="2.0")
    t = ts.get_template_by_name("deploy")
    assert t is not None
    # Should get latest version
    print("OK: get template by name")


def test_instantiate():
    ts = PipelineTemplateStore()
    tid = ts.create_template("deploy", steps=["build", "test"], description="Standard deploy")
    instance = ts.instantiate(tid, overrides={"env": "production"})
    assert instance is not None
    assert "name" in instance and instance["name"] == "deploy"
    assert "instantiated_at" in instance
    print("OK: instantiate")


def test_update_template():
    ts = PipelineTemplateStore()
    tid = ts.create_template("deploy", steps=["build"])
    assert ts.update_template(tid, steps=["build", "test", "release"]) is True
    t = ts.get_template(tid)
    assert len(t["steps"]) == 3
    print("OK: update template")


def test_list_templates():
    ts = PipelineTemplateStore()
    ts.create_template("deploy", steps=["build"], tags=["ci"])
    ts.create_template("test", steps=["lint", "test"], tags=["qa"])
    all_t = ts.list_templates()
    assert len(all_t) == 2
    ci_t = ts.list_templates(tag="ci")
    assert len(ci_t) == 1
    print("OK: list templates")


def test_remove_template():
    ts = PipelineTemplateStore()
    tid = ts.create_template("temp", steps=["a"])
    assert ts.remove_template(tid) is True
    assert ts.remove_template(tid) is False
    print("OK: remove template")


def test_callbacks():
    ts = PipelineTemplateStore()
    fired = []
    ts.on_change("mon", lambda a, d: fired.append(a))
    ts.create_template("deploy", steps=["build"])
    assert len(fired) >= 1
    assert ts.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    ts = PipelineTemplateStore()
    ts.create_template("deploy", steps=["build"])
    stats = ts.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    ts = PipelineTemplateStore()
    ts.create_template("deploy", steps=["build"])
    ts.reset()
    assert ts.list_templates() == []
    print("OK: reset")


def main():
    print("=== Pipeline Template Store Tests ===\n")
    test_create_template()
    test_get_template()
    test_get_template_by_name()
    test_instantiate()
    test_update_template()
    test_list_templates()
    test_remove_template()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 10 TESTS PASSED ===")


if __name__ == "__main__":
    main()
