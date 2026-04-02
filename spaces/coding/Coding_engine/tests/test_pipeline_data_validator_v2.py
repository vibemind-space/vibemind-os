"""Tests for PipelineDataValidatorV2."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_data_validator_v2 import PipelineDataValidatorV2


class TestPipelineDataValidatorV2(unittest.TestCase):

    def setUp(self):
        self.validator = PipelineDataValidatorV2()

    # -- validate_v2 basics --

    def test_validate_v2_returns_id(self):
        rid = self.validator.validate_v2("pipe1", "key1")
        self.assertTrue(rid.startswith("pdvv-"))

    def test_validate_v2_empty_pipeline_id(self):
        self.assertEqual(self.validator.validate_v2("", "key1"), "")

    def test_validate_v2_empty_data_key(self):
        self.assertEqual(self.validator.validate_v2("pipe1", ""), "")

    def test_validate_v2_both_empty(self):
        self.assertEqual(self.validator.validate_v2("", ""), "")

    def test_validate_v2_default_rules(self):
        rid = self.validator.validate_v2("pipe1", "key1")
        rec = self.validator.get_validation(rid)
        self.assertEqual(rec["rules"], "default")

    def test_validate_v2_custom_rules(self):
        rid = self.validator.validate_v2("pipe1", "key1", rules="strict")
        rec = self.validator.get_validation(rid)
        self.assertEqual(rec["rules"], "strict")

    def test_validate_v2_with_metadata(self):
        meta = {"source": "test", "version": 2}
        rid = self.validator.validate_v2("pipe1", "key1", metadata=meta)
        rec = self.validator.get_validation(rid)
        self.assertEqual(rec["metadata"]["source"], "test")
        self.assertEqual(rec["metadata"]["version"], 2)

    def test_validate_v2_metadata_is_deep_copied(self):
        meta = {"items": [1, 2, 3]}
        rid = self.validator.validate_v2("pipe1", "key1", metadata=meta)
        meta["items"].append(4)
        rec = self.validator.get_validation(rid)
        self.assertEqual(rec["metadata"]["items"], [1, 2, 3])

    # -- get_validation --

    def test_get_validation_found(self):
        rid = self.validator.validate_v2("pipe1", "key1")
        rec = self.validator.get_validation(rid)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["record_id"], rid)
        self.assertEqual(rec["pipeline_id"], "pipe1")

    def test_get_validation_not_found(self):
        self.assertIsNone(self.validator.get_validation("pdvv-nonexistent"))

    # -- get_validations --

    def test_get_validations_all(self):
        self.validator.validate_v2("pipe1", "k1")
        self.validator.validate_v2("pipe2", "k2")
        results = self.validator.get_validations()
        self.assertEqual(len(results), 2)

    def test_get_validations_filtered(self):
        self.validator.validate_v2("pipe1", "k1")
        self.validator.validate_v2("pipe1", "k2")
        self.validator.validate_v2("pipe2", "k3")
        results = self.validator.get_validations(pipeline_id="pipe1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["pipeline_id"], "pipe1")

    def test_get_validations_sorted_descending(self):
        r1 = self.validator.validate_v2("pipe1", "k1")
        r2 = self.validator.validate_v2("pipe1", "k2")
        r3 = self.validator.validate_v2("pipe1", "k3")
        results = self.validator.get_validations(pipeline_id="pipe1")
        ids = [r["record_id"] for r in results]
        self.assertEqual(ids[0], r3)
        self.assertEqual(ids[-1], r1)

    def test_get_validations_limit(self):
        for i in range(10):
            self.validator.validate_v2("pipe1", f"k{i}")
        results = self.validator.get_validations(limit=3)
        self.assertEqual(len(results), 3)

    # -- get_validation_count --

    def test_get_validation_count_all(self):
        self.validator.validate_v2("pipe1", "k1")
        self.validator.validate_v2("pipe2", "k2")
        self.assertEqual(self.validator.get_validation_count(), 2)

    def test_get_validation_count_filtered(self):
        self.validator.validate_v2("pipe1", "k1")
        self.validator.validate_v2("pipe1", "k2")
        self.validator.validate_v2("pipe2", "k3")
        self.assertEqual(self.validator.get_validation_count("pipe1"), 2)
        self.assertEqual(self.validator.get_validation_count("pipe2"), 1)

    # -- get_stats --

    def test_get_stats(self):
        self.validator.validate_v2("pipe1", "k1")
        self.validator.validate_v2("pipe2", "k2")
        self.validator.validate_v2("pipe1", "k3")
        stats = self.validator.get_stats()
        self.assertEqual(stats["total_validations"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)

    # -- reset --

    def test_reset(self):
        self.validator.validate_v2("pipe1", "k1")
        self.validator.on_change(lambda a, d: None)
        self.validator.reset()
        self.assertEqual(self.validator.get_validation_count(), 0)
        self.assertEqual(self.validator.get_stats()["total_validations"], 0)

    # -- callbacks --

    def test_on_change_fires(self):
        events = []
        self.validator.on_change(lambda a, d: events.append((a, d)))
        self.validator.validate_v2("pipe1", "k1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "validation_created")
        self.assertEqual(events[0][1]["action"], "validation_created")

    def test_remove_callback(self):
        events = []
        cb_id = self.validator.on_change(lambda a, d: events.append(a))
        self.assertTrue(self.validator.remove_callback(cb_id))
        self.validator.validate_v2("pipe1", "k1")
        self.assertEqual(len(events), 0)

    def test_remove_callback_not_found(self):
        self.assertFalse(self.validator.remove_callback("pdvv-nonexistent"))

    def test_get_stats_empty(self):
        stats = self.validator.get_stats()
        self.assertEqual(stats["total_validations"], 0)
        self.assertEqual(stats["unique_pipelines"], 0)


if __name__ == "__main__":
    unittest.main()
