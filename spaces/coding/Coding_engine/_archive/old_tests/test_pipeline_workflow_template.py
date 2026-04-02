"""Test pipeline workflow template."""
import sys
sys.path.insert(0, ".")
from src.services.pipeline_workflow_template import PipelineWorkflowTemplate

def test_create():
    wt = PipelineWorkflowTemplate()
    tid = wt.create_template("deploy", [{"name": "build"}, {"name": "test"}, {"name": "deploy"}], tags=["ci"])
    assert tid.startswith("tmpl-")
    t = wt.get_template("deploy")
    assert len(t["steps"]) == 3
    print("OK: create")

def test_invalid():
    wt = PipelineWorkflowTemplate()
    assert wt.create_template("", [{"a": 1}]) == ""
    assert wt.create_template("x", []) == ""
    print("OK: invalid")

def test_duplicate():
    wt = PipelineWorkflowTemplate()
    wt.create_template("t1", [{"a": 1}])
    assert wt.create_template("t1", [{"a": 1}]) == ""
    print("OK: duplicate")

def test_update():
    wt = PipelineWorkflowTemplate()
    wt.create_template("t1", [{"a": 1}])
    assert wt.update_template("t1", [{"a": 1}, {"b": 2}]) is True
    t = wt.get_template("t1")
    assert len(t["steps"]) == 2
    assert t["version"] == 2
    print("OK: update")

def test_remove():
    wt = PipelineWorkflowTemplate()
    wt.create_template("t1", [{"a": 1}])
    assert wt.remove_template("t1") is True
    assert wt.remove_template("t1") is False
    print("OK: remove")

def test_instantiate():
    wt = PipelineWorkflowTemplate()
    wt.create_template("deploy", [{"name": "build"}, {"name": "test"}])
    iid = wt.instantiate("deploy", context={"env": "prod"})
    assert iid.startswith("wfi-")
    inst = wt.get_instance(iid)
    assert inst["status"] == "pending"
    assert inst["context"]["env"] == "prod"
    print("OK: instantiate")

def test_advance():
    wt = PipelineWorkflowTemplate()
    wt.create_template("deploy", [{"name": "build"}, {"name": "test"}])
    iid = wt.instantiate("deploy")
    assert wt.advance_step(iid, result="built") is True
    inst = wt.get_instance(iid)
    assert inst["status"] == "running"
    assert inst["current_step"] == 1
    assert wt.advance_step(iid, result="tested") is True
    inst = wt.get_instance(iid)
    assert inst["status"] == "completed"
    print("OK: advance")

def test_fail():
    wt = PipelineWorkflowTemplate()
    wt.create_template("deploy", [{"name": "build"}])
    iid = wt.instantiate("deploy")
    assert wt.fail_instance(iid, error="build failed") is True
    assert wt.get_instance(iid)["status"] == "failed"
    assert wt.fail_instance(iid) is False  # already failed
    print("OK: fail")

def test_list_templates():
    wt = PipelineWorkflowTemplate()
    wt.create_template("t1", [{"a": 1}], tags=["ci"])
    wt.create_template("t2", [{"a": 1}])
    assert len(wt.list_templates()) == 2
    assert len(wt.list_templates(tag="ci")) == 1
    print("OK: list templates")

def test_list_instances():
    wt = PipelineWorkflowTemplate()
    wt.create_template("t1", [{"a": 1}, {"b": 2}])
    wt.instantiate("t1")
    iid2 = wt.instantiate("t1")
    wt.advance_step(iid2)  # still has step 2 remaining -> running
    assert len(wt.list_instances()) == 2
    assert len(wt.list_instances(status="running")) == 1
    print("OK: list instances")

def test_callback():
    wt = PipelineWorkflowTemplate()
    fired = []
    wt.on_change("mon", lambda a, d: fired.append(a))
    wt.create_template("t1", [{"a": 1}])
    assert "template_created" in fired
    print("OK: callback")

def test_callbacks():
    wt = PipelineWorkflowTemplate()
    assert wt.on_change("m", lambda a, d: None) is True
    assert wt.on_change("m", lambda a, d: None) is False
    assert wt.remove_callback("m") is True
    assert wt.remove_callback("m") is False
    print("OK: callbacks")

def test_stats():
    wt = PipelineWorkflowTemplate()
    wt.create_template("t1", [{"a": 1}])
    wt.instantiate("t1")
    stats = wt.get_stats()
    assert stats["current_templates"] == 1
    assert stats["current_instances"] == 1
    print("OK: stats")

def test_reset():
    wt = PipelineWorkflowTemplate()
    wt.create_template("t1", [{"a": 1}])
    wt.reset()
    assert wt.list_templates() == []
    print("OK: reset")

def main():
    print("=== Pipeline Workflow Template Tests ===\n")
    test_create()
    test_invalid()
    test_duplicate()
    test_update()
    test_remove()
    test_instantiate()
    test_advance()
    test_fail()
    test_list_templates()
    test_list_instances()
    test_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 14 TESTS PASSED ===")

if __name__ == "__main__":
    main()
