"""Test pipeline step condition -- unit tests."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_step_condition import PipelineStepCondition


def test_add_condition():
    sc = PipelineStepCondition()
    cid = sc.add_condition("pipeline-1", "deploy", "env", "eq", "prod")
    assert len(cid) > 0
    assert cid.startswith("psc-")
    print("OK: add condition")


def test_evaluate_pass():
    sc = PipelineStepCondition()
    sc.add_condition("pipeline-1", "deploy", "env", "eq", "prod")
    assert sc.evaluate("pipeline-1", "deploy", {"env": "prod"}) is True
    print("OK: evaluate pass")


def test_evaluate_fail():
    sc = PipelineStepCondition()
    sc.add_condition("pipeline-1", "deploy", "env", "eq", "prod")
    assert sc.evaluate("pipeline-1", "deploy", {"env": "staging"}) is False
    print("OK: evaluate fail")


def test_evaluate_multiple():
    sc = PipelineStepCondition()
    sc.add_condition("pipeline-1", "deploy", "env", "eq", "prod")
    sc.add_condition("pipeline-1", "deploy", "version", "gt", 2)
    assert sc.evaluate("pipeline-1", "deploy", {"env": "prod", "version": 3}) is True
    assert sc.evaluate("pipeline-1", "deploy", {"env": "prod", "version": 1}) is False
    print("OK: evaluate multiple")


def test_evaluate_in():
    sc = PipelineStepCondition()
    sc.add_condition("pipeline-1", "deploy", "region", "in", ["us", "eu"])
    assert sc.evaluate("pipeline-1", "deploy", {"region": "us"}) is True
    assert sc.evaluate("pipeline-1", "deploy", {"region": "ap"}) is False
    print("OK: evaluate in")


def test_get_conditions():
    sc = PipelineStepCondition()
    sc.add_condition("pipeline-1", "deploy", "env", "eq", "prod")
    sc.add_condition("pipeline-1", "test", "type", "eq", "unit")
    conditions = sc.get_conditions("pipeline-1")
    assert len(conditions) == 2
    print("OK: get conditions")


def test_get_conditions_by_step():
    sc = PipelineStepCondition()
    sc.add_condition("pipeline-1", "deploy", "env", "eq", "prod")
    sc.add_condition("pipeline-1", "test", "type", "eq", "unit")
    conditions = sc.get_conditions("pipeline-1", step_name="deploy")
    assert len(conditions) == 1
    print("OK: get conditions by step")


def test_remove_condition():
    sc = PipelineStepCondition()
    cid = sc.add_condition("pipeline-1", "deploy", "env", "eq", "prod")
    assert sc.remove_condition(cid) is True
    assert sc.remove_condition("nonexistent") is False
    assert sc.get_condition_count("pipeline-1") == 0
    print("OK: remove condition")


def test_get_condition_count():
    sc = PipelineStepCondition()
    sc.add_condition("pipeline-1", "deploy", "env", "eq", "prod")
    sc.add_condition("pipeline-2", "test", "type", "eq", "unit")
    assert sc.get_condition_count() == 2
    assert sc.get_condition_count("pipeline-1") == 1
    print("OK: get condition count")


def test_list_pipelines():
    sc = PipelineStepCondition()
    sc.add_condition("pipeline-1", "deploy", "env", "eq", "prod")
    sc.add_condition("pipeline-2", "test", "type", "eq", "unit")
    pipelines = sc.list_pipelines()
    assert "pipeline-1" in pipelines
    assert "pipeline-2" in pipelines
    print("OK: list pipelines")


def test_callbacks():
    sc = PipelineStepCondition()
    fired = []
    sc.on_change("mon", lambda a, d: fired.append(a))
    sc.add_condition("pipeline-1", "deploy", "env", "eq", "prod")
    assert len(fired) >= 1
    assert sc.remove_callback("mon") is True
    print("OK: callbacks")


def test_stats():
    sc = PipelineStepCondition()
    sc.add_condition("pipeline-1", "deploy", "env", "eq", "prod")
    stats = sc.get_stats()
    assert len(stats) > 0
    print("OK: stats")


def test_reset():
    sc = PipelineStepCondition()
    sc.add_condition("pipeline-1", "deploy", "env", "eq", "prod")
    sc.reset()
    assert sc.get_condition_count() == 0
    print("OK: reset")


def main():
    print("=== Pipeline Step Condition Tests ===\n")
    test_add_condition()
    test_evaluate_pass()
    test_evaluate_fail()
    test_evaluate_multiple()
    test_evaluate_in()
    test_get_conditions()
    test_get_conditions_by_step()
    test_remove_condition()
    test_get_condition_count()
    test_list_pipelines()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 13 TESTS PASSED ===")


if __name__ == "__main__":
    main()
