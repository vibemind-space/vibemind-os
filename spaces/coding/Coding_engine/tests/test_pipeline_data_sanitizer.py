"""Tests for PipelineDataSanitizer service."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_sanitizer import PipelineDataSanitizer


class TestPipelineDataSanitizerInit:
    def test_init_creates_instance(self):
        svc = PipelineDataSanitizer()
        assert svc is not None

    def test_init_empty_state(self):
        svc = PipelineDataSanitizer()
        assert svc.get_records() == []
        assert svc.get_rules() == []

    def test_prefix_and_max_entries(self):
        svc = PipelineDataSanitizer()
        assert svc.PREFIX == "pdsa-"
        assert svc.MAX_ENTRIES == 10000


class TestSanitize:
    def test_sanitize_returns_id(self):
        svc = PipelineDataSanitizer()
        rid = svc.sanitize({"name": " Alice "})
        assert rid.startswith("pdsa-")

    def test_sanitize_strip_whitespace(self):
        svc = PipelineDataSanitizer()
        rid = svc.sanitize({"name": "  hello  ", "age": 30}, rules=["strip_whitespace"])
        rec = svc.get_record(rid)
        assert rec["sanitized"]["name"] == "hello"
        assert rec["sanitized"]["age"] == 30

    def test_sanitize_lowercase(self):
        svc = PipelineDataSanitizer()
        rid = svc.sanitize({"name": "ALICE"}, rules=["lowercase"])
        rec = svc.get_record(rid)
        assert rec["sanitized"]["name"] == "alice"

    def test_sanitize_remove_nulls(self):
        svc = PipelineDataSanitizer()
        rid = svc.sanitize({"a": 1, "b": None, "c": "x"}, rules=["remove_nulls"])
        rec = svc.get_record(rid)
        assert "b" not in rec["sanitized"]
        assert rec["sanitized"]["a"] == 1

    def test_sanitize_trim_strings(self):
        svc = PipelineDataSanitizer()
        long_str = "x" * 2000
        rid = svc.sanitize({"text": long_str}, rules=["trim_strings"])
        rec = svc.get_record(rid)
        assert len(rec["sanitized"]["text"]) == 1000

    def test_sanitize_multiple_rules(self):
        svc = PipelineDataSanitizer()
        rid = svc.sanitize(
            {"name": "  ALICE  ", "extra": None},
            rules=["strip_whitespace", "lowercase", "remove_nulls"],
        )
        rec = svc.get_record(rid)
        assert rec["sanitized"]["name"] == "alice"
        assert "extra" not in rec["sanitized"]

    def test_sanitize_default_rules(self):
        svc = PipelineDataSanitizer()
        rid = svc.sanitize({"name": "  hello  ", "x": None})
        rec = svc.get_record(rid)
        assert rec["sanitized"]["name"] == "hello"
        assert "x" not in rec["sanitized"]

    def test_sanitize_preserves_original(self):
        svc = PipelineDataSanitizer()
        data = {"name": "  ALICE  "}
        rid = svc.sanitize(data, rules=["strip_whitespace", "lowercase"])
        rec = svc.get_record(rid)
        assert rec["original"]["name"] == "  ALICE  "

    def test_sanitize_nested_dict(self):
        svc = PipelineDataSanitizer()
        rid = svc.sanitize(
            {"outer": {"inner": "  HELLO  "}},
            rules=["strip_whitespace", "lowercase"],
        )
        rec = svc.get_record(rid)
        assert rec["sanitized"]["outer"]["inner"] == "hello"


class TestGetRecords:
    def test_get_records_returns_list(self):
        svc = PipelineDataSanitizer()
        svc.sanitize({"a": 1})
        records = svc.get_records()
        assert isinstance(records, list)
        assert len(records) == 1

    def test_get_records_newest_first(self):
        svc = PipelineDataSanitizer()
        id1 = svc.sanitize({"a": 1})
        time.sleep(0.01)
        id2 = svc.sanitize({"b": 2})
        records = svc.get_records()
        assert records[0]["id"] == id2
        assert records[1]["id"] == id1

    def test_get_records_limit(self):
        svc = PipelineDataSanitizer()
        for i in range(10):
            svc.sanitize({"val": i})
        records = svc.get_records(limit=3)
        assert len(records) == 3

    def test_get_record_not_found(self):
        svc = PipelineDataSanitizer()
        assert svc.get_record("pdsa-nonexistent") is None


class TestRules:
    def test_add_rule_returns_id(self):
        svc = PipelineDataSanitizer()
        rid = svc.add_rule("custom_clean", "My custom cleaning rule")
        assert rid.startswith("pdsa-")

    def test_get_rules(self):
        svc = PipelineDataSanitizer()
        svc.add_rule("rule_a", "Description A")
        svc.add_rule("rule_b", "Description B")
        rules = svc.get_rules()
        assert len(rules) == 2
        rule_names = {r["rule_name"] for r in rules}
        assert "rule_a" in rule_names
        assert "rule_b" in rule_names

    def test_rule_has_description(self):
        svc = PipelineDataSanitizer()
        svc.add_rule("my_rule", "cleans things")
        rules = svc.get_rules()
        assert rules[0]["description"] == "cleans things"


class TestStats:
    def test_stats_empty(self):
        svc = PipelineDataSanitizer()
        stats = svc.get_stats()
        assert stats["total_sanitizations"] == 0
        assert stats["rules_applied"] == {}

    def test_stats_after_sanitizations(self):
        svc = PipelineDataSanitizer()
        svc.sanitize({"a": " x "}, rules=["strip_whitespace"])
        svc.sanitize({"b": "Y"}, rules=["lowercase"])
        svc.sanitize({"c": " Z "}, rules=["strip_whitespace", "lowercase"])
        stats = svc.get_stats()
        assert stats["total_sanitizations"] == 3
        assert stats["rules_applied"]["strip_whitespace"] == 2
        assert stats["rules_applied"]["lowercase"] == 2


class TestCallbacks:
    def test_on_change_fires(self):
        svc = PipelineDataSanitizer()
        events = []
        svc.on_change = lambda action, data: events.append((action, data))
        svc.sanitize({"x": 1})
        assert len(events) == 1
        assert events[0][0] == "sanitized"

    def test_on_change_getter(self):
        svc = PipelineDataSanitizer()
        assert svc.on_change is None
        cb = lambda a, d: None
        svc.on_change = cb
        assert svc.on_change is cb

    def test_callback_exception_silenced(self):
        svc = PipelineDataSanitizer()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        # Should not raise
        rid = svc.sanitize({"x": 1})
        assert rid.startswith("pdsa-")

    def test_remove_callback(self):
        svc = PipelineDataSanitizer()
        svc._callbacks["test_cb"] = lambda a, d: None
        assert svc.remove_callback("test_cb") is True
        assert svc.remove_callback("test_cb") is False

    def test_fire_on_rule_added(self):
        svc = PipelineDataSanitizer()
        events = []
        svc.on_change = lambda action, data: events.append(action)
        svc.add_rule("my_rule")
        assert "rule_added" in events


class TestReset:
    def test_reset_clears_state(self):
        svc = PipelineDataSanitizer()
        svc.sanitize({"a": 1})
        svc.add_rule("r1")
        svc.reset()
        assert svc.get_records() == []
        assert svc.get_rules() == []
        assert svc.get_stats()["total_sanitizations"] == 0


class TestIdGeneration:
    def test_unique_ids(self):
        svc = PipelineDataSanitizer()
        ids = set()
        for i in range(50):
            rid = svc.sanitize({"val": i})
            ids.add(rid)
        assert len(ids) == 50


class TestDeepCopy:
    def test_mutation_does_not_affect_record(self):
        svc = PipelineDataSanitizer()
        data = {"items": [1, 2, 3]}
        rid = svc.sanitize(data, rules=[])
        data["items"].append(999)
        rec = svc.get_record(rid)
        assert 999 not in rec["original"]["items"]

    def test_get_record_returns_copy(self):
        svc = PipelineDataSanitizer()
        rid = svc.sanitize({"a": 1}, rules=[])
        rec1 = svc.get_record(rid)
        rec1["a"] = "mutated"
        rec2 = svc.get_record(rid)
        assert "a" not in rec2 or rec2.get("a") != "mutated"
