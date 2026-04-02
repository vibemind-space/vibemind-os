"""Tests for AgentTaskValidator service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_validator import AgentTaskValidator


class TestValidateBasic:
    """Basic validation creation and retrieval."""

    def test_validate_returns_id(self):
        svc = AgentTaskValidator()
        vid = svc.validate("t1", {"name": "test"})
        assert vid.startswith("atva-")
        assert len(vid) > 5

    def test_validate_empty_task_id_returns_empty(self):
        svc = AgentTaskValidator()
        assert svc.validate("", {"name": "test"}) == ""

    def test_validate_none_data_returns_empty(self):
        svc = AgentTaskValidator()
        assert svc.validate("t1", None) == ""

    def test_get_validation_existing(self):
        svc = AgentTaskValidator()
        vid = svc.validate("t1", {"name": "test"}, label="input")
        entry = svc.get_validation(vid)
        assert entry is not None
        assert entry["task_id"] == "t1"
        assert entry["label"] == "input"
        assert entry["passed"] is True

    def test_get_validation_nonexistent(self):
        svc = AgentTaskValidator()
        assert svc.get_validation("atva-nonexistent") is None

    def test_default_label_is_empty_string(self):
        svc = AgentTaskValidator()
        vid = svc.validate("t1", {"a": 1})
        entry = svc.get_validation(vid)
        assert entry["label"] == ""


class TestValidationRules:
    """Rule checking behaviour."""

    def test_required_fields_pass(self):
        svc = AgentTaskValidator()
        vid = svc.validate("t1", {"name": "x"}, rules=["required_fields"])
        entry = svc.get_validation(vid)
        assert entry["passed"] is True
        assert entry["errors"] == []

    def test_required_fields_fail_empty_data(self):
        svc = AgentTaskValidator()
        vid = svc.validate("t1", {}, rules=["required_fields"])
        entry = svc.get_validation(vid)
        assert entry["passed"] is False
        assert len(entry["errors"]) > 0

    def test_type_check_pass(self):
        svc = AgentTaskValidator()
        vid = svc.validate("t1", {"a": 1, "b": "s", "c": [1], "d": True}, rules=["type_check"])
        entry = svc.get_validation(vid)
        assert entry["passed"] is True

    def test_type_check_fail(self):
        svc = AgentTaskValidator()
        vid = svc.validate("t1", {"a": object()}, rules=["type_check"])
        entry = svc.get_validation(vid)
        assert entry["passed"] is False
        assert len(entry["errors"]) > 0

    def test_non_empty_pass(self):
        svc = AgentTaskValidator()
        vid = svc.validate("t1", {"name": "x", "count": 0}, rules=["non_empty"])
        entry = svc.get_validation(vid)
        assert entry["passed"] is True

    def test_non_empty_fail_empty_string(self):
        svc = AgentTaskValidator()
        vid = svc.validate("t1", {"name": ""}, rules=["non_empty"])
        entry = svc.get_validation(vid)
        assert entry["passed"] is False

    def test_non_empty_fail_empty_list(self):
        svc = AgentTaskValidator()
        vid = svc.validate("t1", {"items": []}, rules=["non_empty"])
        entry = svc.get_validation(vid)
        assert entry["passed"] is False

    def test_multiple_rules_combined(self):
        svc = AgentTaskValidator()
        vid = svc.validate("t1", {"name": ""}, rules=["required_fields", "non_empty"])
        entry = svc.get_validation(vid)
        assert entry["passed"] is False
        assert len(entry["errors"]) >= 1

    def test_default_rule_is_required_fields(self):
        svc = AgentTaskValidator()
        vid = svc.validate("t1", {"a": 1})
        entry = svc.get_validation(vid)
        assert "required_fields" in entry["rules"]


class TestDeepCopy:
    """Data deep-copy behaviour."""

    def test_data_deep_copied(self):
        data = {"nested": {"x": 1}}
        svc = AgentTaskValidator()
        vid = svc.validate("t1", data)
        data["nested"]["x"] = 999
        entry = svc.get_validation(vid)
        assert entry["data"]["nested"]["x"] == 1


class TestGetValidations:
    """Querying multiple validations."""

    def test_get_validations_all(self):
        svc = AgentTaskValidator()
        svc.validate("t1", {"a": 1})
        svc.validate("t2", {"b": 2})
        results = svc.get_validations()
        assert len(results) == 2

    def test_get_validations_filter_by_task(self):
        svc = AgentTaskValidator()
        svc.validate("t1", {"a": 1})
        svc.validate("t2", {"b": 2})
        svc.validate("t1", {"c": 3})
        results = svc.get_validations(task_id="t1")
        assert len(results) == 2
        assert all(r["task_id"] == "t1" for r in results)

    def test_get_validations_filter_by_label(self):
        svc = AgentTaskValidator()
        svc.validate("t1", {"a": 1}, label="input")
        svc.validate("t1", {"b": 2}, label="output")
        svc.validate("t2", {"c": 3}, label="input")
        results = svc.get_validations(label="input")
        assert len(results) == 2
        assert all(r["label"] == "input" for r in results)

    def test_get_validations_newest_first(self):
        svc = AgentTaskValidator()
        id1 = svc.validate("t1", {"a": 1})
        id2 = svc.validate("t2", {"b": 2})
        results = svc.get_validations()
        assert results[0]["validation_id"] == id2
        assert results[1]["validation_id"] == id1

    def test_get_validations_respects_limit(self):
        svc = AgentTaskValidator()
        for i in range(10):
            svc.validate(f"t{i}", {"x": i})
        results = svc.get_validations(limit=3)
        assert len(results) == 3


class TestGetValidationCount:
    """Counting validations."""

    def test_count_all(self):
        svc = AgentTaskValidator()
        svc.validate("t1", {"a": 1})
        svc.validate("t2", {"b": 2})
        assert svc.get_validation_count() == 2

    def test_count_by_task(self):
        svc = AgentTaskValidator()
        svc.validate("t1", {"a": 1})
        svc.validate("t2", {"b": 2})
        svc.validate("t1", {"c": 3})
        assert svc.get_validation_count(task_id="t1") == 2

    def test_count_by_passed(self):
        svc = AgentTaskValidator()
        svc.validate("t1", {"a": 1}, rules=["required_fields"])
        svc.validate("t2", {}, rules=["required_fields"])
        assert svc.get_validation_count(passed=True) == 1
        assert svc.get_validation_count(passed=False) == 1

    def test_count_empty(self):
        svc = AgentTaskValidator()
        assert svc.get_validation_count() == 0


class TestGetStats:
    """Statistics."""

    def test_stats_empty(self):
        svc = AgentTaskValidator()
        stats = svc.get_stats()
        assert stats["total_validations"] == 0
        assert stats["passed_count"] == 0
        assert stats["failed_count"] == 0
        assert stats["pass_rate"] == 0.0

    def test_stats_populated(self):
        svc = AgentTaskValidator()
        svc.validate("t1", {"a": 1}, rules=["required_fields"])
        svc.validate("t2", {"b": 2}, rules=["required_fields"])
        svc.validate("t3", {}, rules=["required_fields"])
        stats = svc.get_stats()
        assert stats["total_validations"] == 3
        assert stats["passed_count"] == 2
        assert stats["failed_count"] == 1
        assert abs(stats["pass_rate"] - 2 / 3) < 0.01


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskValidator()
        svc.validate("t1", {"a": 1})
        svc.reset()
        assert svc.get_validation_count() == 0
        assert svc.get_stats()["total_validations"] == 0

    def test_reset_clears_on_change(self):
        svc = AgentTaskValidator()
        svc.on_change = lambda a, d: None
        svc.reset()
        assert svc.on_change is None


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires_on_validate(self):
        events = []
        svc = AgentTaskValidator()
        svc.on_change = lambda action, data: events.append((action, data))
        svc.validate("t1", {"a": 1})
        assert len(events) == 1
        assert events[0][0] == "validation_created"

    def test_on_change_getter(self):
        svc = AgentTaskValidator()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn

    def test_remove_callback(self):
        svc = AgentTaskValidator()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert svc.remove_callback("cb1") is False

    def test_callback_exception_silenced(self):
        svc = AgentTaskValidator()
        svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        vid = svc.validate("t1", {"a": 1})
        assert vid.startswith("atva-")

    def test_named_callbacks_fire(self):
        events = []
        svc = AgentTaskValidator()
        svc._callbacks["my_cb"] = lambda action, data: events.append(action)
        svc.validate("t1", {"a": 1})
        assert "validation_created" in events


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_evicts_oldest(self):
        svc = AgentTaskValidator()
        svc.MAX_ENTRIES = 5
        ids = []
        for i in range(6):
            ids.append(svc.validate(f"t{i}", {"x": i}))
        assert svc.get_validation(ids[0]) is None
        assert svc.get_validation_count() <= 5


class TestUniqueIds:
    """IDs are unique."""

    def test_unique_ids(self):
        svc = AgentTaskValidator()
        ids = set()
        for i in range(50):
            ids.add(svc.validate(f"t{i}", {"x": i}))
        assert len(ids) == 50


class TestReturnTypes:
    """All public methods return expected types."""

    def test_validate_returns_dict_via_get(self):
        svc = AgentTaskValidator()
        vid = svc.validate("t1", {"a": 1})
        assert isinstance(svc.get_validation(vid), dict)

    def test_get_validations_returns_list_of_dicts(self):
        svc = AgentTaskValidator()
        svc.validate("t1", {"a": 1})
        results = svc.get_validations()
        assert isinstance(results, list)
        assert all(isinstance(r, dict) for r in results)

    def test_get_stats_returns_dict(self):
        svc = AgentTaskValidator()
        assert isinstance(svc.get_stats(), dict)
