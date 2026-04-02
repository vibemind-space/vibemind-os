"""Tests for PipelineStepConditionV2."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_condition_v2 import PipelineStepConditionV2


def test_register_condition():
    svc = PipelineStepConditionV2()
    cid = svc.register_condition("check_status", "status", "eq", "active")
    assert cid.startswith("pscv2-")
    assert svc.get_condition_count() == 1


def test_get_condition():
    svc = PipelineStepConditionV2()
    cid = svc.register_condition("check_status", "status", "eq", "active")
    cond = svc.get_condition(cid)
    assert cond["name"] == "check_status"
    assert cond["field"] == "status"
    assert cond["operator"] == "eq"
    assert cond["value"] == "active"
    assert cond["eval_count"] == 0


def test_get_condition_not_found():
    svc = PipelineStepConditionV2()
    assert svc.get_condition("nonexistent") == {}


def test_get_conditions():
    svc = PipelineStepConditionV2()
    svc.register_condition("c1", "f1", "eq", "v1")
    svc.register_condition("c2", "f2", "ne", "v2")
    conds = svc.get_conditions()
    assert len(conds) == 2


def test_evaluate_eq_true():
    svc = PipelineStepConditionV2()
    cid = svc.register_condition("check", "status", "eq", "active")
    assert svc.evaluate(cid, {"status": "active"}) is True


def test_evaluate_eq_false():
    svc = PipelineStepConditionV2()
    cid = svc.register_condition("check", "status", "eq", "active")
    assert svc.evaluate(cid, {"status": "inactive"}) is False


def test_evaluate_ne():
    svc = PipelineStepConditionV2()
    cid = svc.register_condition("check", "status", "ne", "failed")
    assert svc.evaluate(cid, {"status": "active"}) is True
    assert svc.evaluate(cid, {"status": "failed"}) is False


def test_evaluate_gt_lt():
    svc = PipelineStepConditionV2()
    cid_gt = svc.register_condition("gt_check", "score", "gt", 50)
    cid_lt = svc.register_condition("lt_check", "score", "lt", 100)
    assert svc.evaluate(cid_gt, {"score": 75}) is True
    assert svc.evaluate(cid_gt, {"score": 30}) is False
    assert svc.evaluate(cid_lt, {"score": 75}) is True
    assert svc.evaluate(cid_lt, {"score": 150}) is False


def test_evaluate_gte_lte():
    svc = PipelineStepConditionV2()
    cid_gte = svc.register_condition("gte_check", "score", "gte", 50)
    cid_lte = svc.register_condition("lte_check", "score", "lte", 100)
    assert svc.evaluate(cid_gte, {"score": 50}) is True
    assert svc.evaluate(cid_gte, {"score": 49}) is False
    assert svc.evaluate(cid_lte, {"score": 100}) is True
    assert svc.evaluate(cid_lte, {"score": 101}) is False


def test_evaluate_contains():
    svc = PipelineStepConditionV2()
    cid = svc.register_condition("check", "tags", "contains", "python")
    assert svc.evaluate(cid, {"tags": ["python", "java"]}) is True
    assert svc.evaluate(cid, {"tags": ["java", "go"]}) is False


def test_evaluate_in():
    svc = PipelineStepConditionV2()
    cid = svc.register_condition("check", "env", "in", ["dev", "staging"])
    assert svc.evaluate(cid, {"env": "dev"}) is True
    assert svc.evaluate(cid, {"env": "prod"}) is False


def test_evaluate_missing_field():
    svc = PipelineStepConditionV2()
    cid = svc.register_condition("check", "status", "eq", "active")
    assert svc.evaluate(cid, {"other_field": "value"}) is False


def test_evaluate_nonexistent_condition():
    svc = PipelineStepConditionV2()
    assert svc.evaluate("nonexistent", {"status": "active"}) is False


def test_evaluate_increments_eval_count():
    svc = PipelineStepConditionV2()
    cid = svc.register_condition("check", "status", "eq", "active")
    svc.evaluate(cid, {"status": "active"})
    svc.evaluate(cid, {"status": "inactive"})
    svc.evaluate(cid, {"status": "active"})
    cond = svc.get_condition(cid)
    assert cond["eval_count"] == 3


def test_evaluate_all_mode_all():
    svc = PipelineStepConditionV2()
    c1 = svc.register_condition("c1", "status", "eq", "active")
    c2 = svc.register_condition("c2", "score", "gt", 50)
    result = svc.evaluate_all([c1, c2], {"status": "active", "score": 75})
    assert result["passed"] is True
    assert result["total"] == 2
    assert result["passed_count"] == 2

    result2 = svc.evaluate_all([c1, c2], {"status": "active", "score": 30})
    assert result2["passed"] is False
    assert result2["passed_count"] == 1


def test_evaluate_all_mode_any():
    svc = PipelineStepConditionV2()
    c1 = svc.register_condition("c1", "status", "eq", "active")
    c2 = svc.register_condition("c2", "score", "gt", 50)
    result = svc.evaluate_all([c1, c2], {"status": "inactive", "score": 75}, mode="any")
    assert result["passed"] is True
    assert result["passed_count"] == 1

    result2 = svc.evaluate_all([c1, c2], {"status": "inactive", "score": 30}, mode="any")
    assert result2["passed"] is False
    assert result2["passed_count"] == 0


def test_remove_condition():
    svc = PipelineStepConditionV2()
    cid = svc.register_condition("check", "status", "eq", "active")
    assert svc.remove_condition(cid) is True
    assert svc.get_condition_count() == 0
    assert svc.remove_condition(cid) is False


def test_get_stats():
    svc = PipelineStepConditionV2()
    c1 = svc.register_condition("c1", "status", "eq", "active")
    c2 = svc.register_condition("c2", "score", "gt", 50)
    svc.evaluate(c1, {"status": "active"})
    svc.evaluate(c1, {"status": "active"})
    svc.evaluate(c2, {"score": 75})
    stats = svc.get_stats()
    assert stats["total_conditions"] == 2
    assert stats["total_evaluations"] == 3


def test_reset():
    svc = PipelineStepConditionV2()
    svc.register_condition("c1", "status", "eq", "active")
    svc.register_condition("c2", "score", "gt", 50)
    svc.reset()
    assert svc.get_condition_count() == 0
    assert svc.get_conditions() == []
    assert svc.get_stats()["total_evaluations"] == 0


def test_on_change_callback():
    events = []
    svc = PipelineStepConditionV2()
    svc.on_change = lambda action, detail: events.append((action, detail))
    svc.register_condition("check", "status", "eq", "active")
    assert len(events) == 1
    assert events[0][0] == "condition_registered"


def test_remove_callback():
    svc = PipelineStepConditionV2()
    svc._callbacks["test_cb"] = lambda a, d: None
    assert svc.remove_callback("test_cb") is True
    assert svc.remove_callback("test_cb") is False


def test_prefix_and_max_entries():
    assert PipelineStepConditionV2.PREFIX == "pscv2-"
    assert PipelineStepConditionV2.MAX_ENTRIES == 10000


def test_unknown_operator():
    svc = PipelineStepConditionV2()
    cid = svc.register_condition("check", "status", "unknown_op", "active")
    assert svc.evaluate(cid, {"status": "active"}) is False


if __name__ == "__main__":
    tests = [
        test_register_condition,
        test_get_condition,
        test_get_condition_not_found,
        test_get_conditions,
        test_evaluate_eq_true,
        test_evaluate_eq_false,
        test_evaluate_ne,
        test_evaluate_gt_lt,
        test_evaluate_gte_lte,
        test_evaluate_contains,
        test_evaluate_in,
        test_evaluate_missing_field,
        test_evaluate_nonexistent_condition,
        test_evaluate_increments_eval_count,
        test_evaluate_all_mode_all,
        test_evaluate_all_mode_any,
        test_remove_condition,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_prefix_and_max_entries,
        test_unknown_operator,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(tests)} tests passed")
