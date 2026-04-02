"""Tests for PipelineDataNormalizer service."""

import sys
sys.path.insert(0, ".")

from src.services.pipeline_data_normalizer import PipelineDataNormalizer


def test_add_rule():
    svc = PipelineDataNormalizer()
    rid = svc.add_rule("p1", "name", "lowercase")
    assert rid.startswith("pdn-"), f"Expected pdn- prefix, got {rid}"
    assert len(rid) > 4
    # default operation
    rid2 = svc.add_rule("p1", "email")
    assert rid2.startswith("pdn-")
    assert rid != rid2
    # invalid operation
    try:
        svc.add_rule("p1", "x", "invalid_op")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("  test_add_rule PASSED")


def test_normalize_lowercase():
    svc = PipelineDataNormalizer()
    svc.add_rule("p1", "name", "lowercase")
    result = svc.normalize("p1", {"name": "HELLO", "age": 25})
    assert result["name"] == "hello", f"Expected 'hello', got {result['name']}"
    assert result["age"] == 25
    print("  test_normalize_lowercase PASSED")


def test_normalize_uppercase():
    svc = PipelineDataNormalizer()
    svc.add_rule("p1", "name", "uppercase")
    result = svc.normalize("p1", {"name": "hello", "other": 10})
    assert result["name"] == "HELLO", f"Expected 'HELLO', got {result['name']}"
    assert result["other"] == 10
    print("  test_normalize_uppercase PASSED")


def test_normalize_trim():
    svc = PipelineDataNormalizer()
    svc.add_rule("p1", "name", "trim")
    result = svc.normalize("p1", {"name": "  hello  ", "x": 1})
    assert result["name"] == "hello", f"Expected 'hello', got {result['name']}"
    assert result["x"] == 1
    print("  test_normalize_trim PASSED")


def test_normalize_round():
    svc = PipelineDataNormalizer()
    svc.add_rule("p1", "score", "round")
    result = svc.normalize("p1", {"score": 3.7, "name": "test"})
    assert result["score"] == 4, f"Expected 4, got {result['score']}"
    assert result["name"] == "test"
    # non-numeric should be unchanged
    result2 = svc.normalize("p1", {"score": "not_a_number"})
    assert result2["score"] == "not_a_number"
    print("  test_normalize_round PASSED")


def test_remove_rule():
    svc = PipelineDataNormalizer()
    rid = svc.add_rule("p1", "name", "lowercase")
    assert svc.remove_rule(rid) is True
    assert svc.remove_rule(rid) is False
    assert svc.remove_rule("pdn-nonexistent") is False
    print("  test_remove_rule PASSED")


def test_get_rules():
    svc = PipelineDataNormalizer()
    svc.add_rule("p1", "name", "lowercase")
    svc.add_rule("p1", "email", "trim")
    svc.add_rule("p2", "title", "uppercase")
    rules = svc.get_rules("p1")
    assert len(rules) == 2, f"Expected 2 rules, got {len(rules)}"
    fields = {r["field"] for r in rules}
    assert fields == {"name", "email"}
    rules_p2 = svc.get_rules("p2")
    assert len(rules_p2) == 1
    assert svc.get_rules("p_none") == []
    print("  test_get_rules PASSED")


def test_get_rule_count():
    svc = PipelineDataNormalizer()
    svc.add_rule("p1", "name", "lowercase")
    svc.add_rule("p1", "email", "trim")
    svc.add_rule("p2", "title", "uppercase")
    assert svc.get_rule_count() == 3
    assert svc.get_rule_count("p1") == 2
    assert svc.get_rule_count("p2") == 1
    assert svc.get_rule_count("p_none") == 0
    print("  test_get_rule_count PASSED")


def test_list_pipelines():
    svc = PipelineDataNormalizer()
    assert svc.list_pipelines() == []
    svc.add_rule("beta", "name", "lowercase")
    svc.add_rule("alpha", "name", "uppercase")
    svc.add_rule("beta", "email", "trim")
    result = svc.list_pipelines()
    assert result == ["alpha", "beta"], f"Expected sorted list, got {result}"
    print("  test_list_pipelines PASSED")


def test_callbacks():
    svc = PipelineDataNormalizer()
    events = []
    svc.on_change("my_cb", lambda action, detail: events.append((action, detail)))
    svc.add_rule("p1", "name", "lowercase")
    assert len(events) == 1
    assert events[0][0] == "add_rule"
    svc.normalize("p1", {"name": "TEST"})
    assert len(events) == 2
    assert events[1][0] == "normalize"
    # remove_callback returns True/False
    assert svc.remove_callback("my_cb") is True
    assert svc.remove_callback("my_cb") is False
    svc.add_rule("p1", "email", "trim")
    assert len(events) == 2  # no new events after callback removed
    print("  test_callbacks PASSED")


def test_stats():
    svc = PipelineDataNormalizer()
    svc.on_change("cb1", lambda a, d: None)
    svc.add_rule("p1", "name", "lowercase")
    svc.add_rule("p2", "email", "trim")
    svc.normalize("p1", {"name": "X"})
    stats = svc.get_stats()
    assert stats["total_rules"] == 2
    assert stats["total_pipelines"] == 2
    assert stats["total_apply_count"] >= 1
    assert stats["callbacks_registered"] == 1
    print("  test_stats PASSED")


def test_reset():
    svc = PipelineDataNormalizer()
    svc.on_change("cb1", lambda a, d: None)
    svc.add_rule("p1", "name", "lowercase")
    svc.add_rule("p2", "email", "trim")
    svc.reset()
    assert svc.get_rule_count() == 0
    assert svc.list_pipelines() == []
    assert svc.get_stats()["callbacks_registered"] == 0
    print("  test_reset PASSED")


if __name__ == "__main__":
    passed = 0
    tests = [
        test_add_rule,
        test_normalize_lowercase,
        test_normalize_uppercase,
        test_normalize_trim,
        test_normalize_round,
        test_remove_rule,
        test_get_rules,
        test_get_rule_count,
        test_list_pipelines,
        test_callbacks,
        test_stats,
        test_reset,
    ]
    for t in tests:
        t()
        passed += 1
    print(f"\n=== ALL {passed} TESTS PASSED ===")
