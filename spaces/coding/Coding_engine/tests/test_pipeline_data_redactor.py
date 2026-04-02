"""Tests for PipelineDataRedactor service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_redactor import PipelineDataRedactor


def test_register_rule():
    r = PipelineDataRedactor()
    rule_id = r.register_rule("ssn_rule", "ssn")
    assert rule_id.startswith("pdr2-")
    assert r.get_rule_count() == 1


def test_register_rule_custom_replacement():
    r = PipelineDataRedactor()
    rule_id = r.register_rule("email_rule", "email", replacement="[REDACTED]")
    rule = r.get_rule(rule_id)
    assert rule["replacement"] == "[REDACTED]"


def test_register_rule_default_replacement():
    r = PipelineDataRedactor()
    rule_id = r.register_rule("phone_rule", "phone")
    rule = r.get_rule(rule_id)
    assert rule["replacement"] == "***"


def test_redact_single_field():
    r = PipelineDataRedactor()
    r.register_rule("ssn_rule", "ssn")
    record = {"name": "Alice", "ssn": "123-45-6789"}
    result = r.redact(record)
    assert result["ssn"] == "***"
    assert result["name"] == "Alice"


def test_redact_does_not_modify_original():
    r = PipelineDataRedactor()
    r.register_rule("ssn_rule", "ssn")
    record = {"name": "Bob", "ssn": "999-99-9999"}
    r.redact(record)
    assert record["ssn"] == "999-99-9999"


def test_redact_missing_field_unchanged():
    r = PipelineDataRedactor()
    r.register_rule("ssn_rule", "ssn")
    record = {"name": "Charlie", "age": 30}
    result = r.redact(record)
    assert result == {"name": "Charlie", "age": 30}


def test_redact_with_specific_rule_ids():
    r = PipelineDataRedactor()
    id1 = r.register_rule("ssn_rule", "ssn")
    id2 = r.register_rule("email_rule", "email")
    record = {"ssn": "123", "email": "a@b.com"}
    result = r.redact(record, rule_ids=[id1])
    assert result["ssn"] == "***"
    assert result["email"] == "a@b.com"


def test_redact_batch():
    r = PipelineDataRedactor()
    r.register_rule("ssn_rule", "ssn")
    records = [
        {"name": "A", "ssn": "111"},
        {"name": "B", "ssn": "222"},
        {"name": "C"},
    ]
    results = r.redact_batch(records)
    assert len(results) == 3
    assert results[0]["ssn"] == "***"
    assert results[1]["ssn"] == "***"
    assert "ssn" not in results[2]


def test_get_rule():
    r = PipelineDataRedactor()
    rule_id = r.register_rule("test_rule", "secret")
    rule = r.get_rule(rule_id)
    assert rule["name"] == "test_rule"
    assert rule["field"] == "secret"
    assert rule["usage_count"] == 0


def test_get_rule_nonexistent():
    r = PipelineDataRedactor()
    rule = r.get_rule("pdr2-nonexistent")
    assert rule == {}


def test_get_rules():
    r = PipelineDataRedactor()
    r.register_rule("r1", "f1")
    r.register_rule("r2", "f2")
    rules = r.get_rules()
    assert len(rules) == 2


def test_remove_rule():
    r = PipelineDataRedactor()
    rule_id = r.register_rule("temp_rule", "temp")
    assert r.remove_rule(rule_id) is True
    assert r.get_rule_count() == 0


def test_remove_rule_nonexistent():
    r = PipelineDataRedactor()
    assert r.remove_rule("pdr2-fake") is False


def test_usage_count_tracking():
    r = PipelineDataRedactor()
    rule_id = r.register_rule("ssn_rule", "ssn")
    r.redact({"ssn": "111"})
    r.redact({"ssn": "222"})
    r.redact({"name": "no ssn"})
    rule = r.get_rule(rule_id)
    assert rule["usage_count"] == 2


def test_get_stats():
    r = PipelineDataRedactor()
    r.register_rule("r1", "f1")
    r.register_rule("r2", "f2")
    r.redact({"f1": "v1", "f2": "v2"})
    r.redact({"f1": "v3"})
    stats = r.get_stats()
    assert stats["total_rules"] == 2
    assert stats["total_redactions"] == 3
    assert stats["total_fields_redacted"] == 3


def test_reset():
    r = PipelineDataRedactor()
    r.register_rule("r1", "f1")
    r.redact({"f1": "val"})
    r.reset()
    assert r.get_rule_count() == 0
    assert r.get_stats()["total_redactions"] == 0


def test_on_change_callback():
    events = []
    r = PipelineDataRedactor()
    r.on_change = lambda event, data: events.append(event)
    r.register_rule("r1", "f1")
    r.remove_rule(list(r._state.entries.keys())[0]) if r.get_rule_count() > 0 else None
    # After reset on_change is cleared, so register before reset to capture
    r.register_rule("r2", "f2")
    assert "rule_registered" in events


def test_remove_callback():
    r = PipelineDataRedactor()
    r._callbacks["test_cb"] = lambda e, d: None
    assert r.remove_callback("test_cb") is True
    assert r.remove_callback("test_cb") is False


def test_multiple_rules_same_field():
    r = PipelineDataRedactor()
    r.register_rule("r1", "ssn", replacement="XXX")
    r.register_rule("r2", "ssn", replacement="YYY")
    record = {"ssn": "123"}
    result = r.redact(record)
    # Last rule to process wins
    assert result["ssn"] in ("XXX", "YYY")


if __name__ == "__main__":
    tests = [
        test_register_rule,
        test_register_rule_custom_replacement,
        test_register_rule_default_replacement,
        test_redact_single_field,
        test_redact_does_not_modify_original,
        test_redact_missing_field_unchanged,
        test_redact_with_specific_rule_ids,
        test_redact_batch,
        test_get_rule,
        test_get_rule_nonexistent,
        test_get_rules,
        test_remove_rule,
        test_remove_rule_nonexistent,
        test_usage_count_tracking,
        test_get_stats,
        test_reset,
        test_on_change_callback,
        test_remove_callback,
        test_multiple_rules_same_field,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
    print(f"{passed}/{passed + failed} tests passed")
