"""Tests for pipeline_data_migrator module."""

from __future__ import annotations

import sys
import os
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_migrator import PipelineDataMigrator, PipelineDataMigratorState


class TestPipelineDataMigrator(unittest.TestCase):
    """Test suite for PipelineDataMigrator."""

    def setUp(self):
        self.migrator = PipelineDataMigrator()

    # --- Initialization ---

    def test_initial_state(self):
        stats = self.migrator.get_stats()
        self.assertEqual(stats["total_migrations"], 0)
        self.assertEqual(stats["pipeline_count"], 0)
        self.assertEqual(stats["callbacks_registered"], 0)

    def test_initial_state_dataclass(self):
        state = PipelineDataMigratorState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)

    def test_initial_migrations_empty(self):
        self.assertEqual(self.migrator.get_migrations(), [])

    def test_initial_migration_count_zero(self):
        self.assertEqual(self.migrator.get_migration_count(), 0)

    # --- Migrate basics ---

    def test_migrate_returns_id(self):
        record_id = self.migrator.migrate("pipe-1", {"a": 1}, "v1", "v2")
        self.assertTrue(record_id.startswith("pdmg-"))
        self.assertEqual(len(record_id), 5 + 16)

    def test_migrate_stores_entry(self):
        record_id = self.migrator.migrate("pipe-1", {"a": 1}, "v1", "v2")
        result = self.migrator.get_migration(record_id)
        self.assertIsNotNone(result)
        self.assertEqual(result["pipeline_id"], "pipe-1")
        self.assertEqual(result["from_version"], "v1")
        self.assertEqual(result["to_version"], "v2")

    def test_migrate_stores_data(self):
        data = {"field1": "value1", "field2": 42}
        record_id = self.migrator.migrate("pipe-1", data, "v1", "v2")
        result = self.migrator.get_migration(record_id)
        self.assertEqual(result["data"], data)

    def test_migrate_with_metadata(self):
        meta = {"author": "admin", "reason": "schema upgrade"}
        record_id = self.migrator.migrate("pipe-1", {}, "v1", "v2", metadata=meta)
        result = self.migrator.get_migration(record_id)
        self.assertEqual(result["metadata"], meta)

    def test_migrate_without_metadata(self):
        record_id = self.migrator.migrate("pipe-1", {}, "v1", "v2")
        result = self.migrator.get_migration(record_id)
        self.assertEqual(result["metadata"], {})

    def test_migrate_has_status(self):
        record_id = self.migrator.migrate("pipe-1", {}, "v1", "v2")
        result = self.migrator.get_migration(record_id)
        self.assertEqual(result["status"], "completed")

    def test_migrate_has_created_at(self):
        before = time.time()
        record_id = self.migrator.migrate("pipe-1", {}, "v1", "v2")
        after = time.time()
        result = self.migrator.get_migration(record_id)
        self.assertGreaterEqual(result["created_at"], before)
        self.assertLessEqual(result["created_at"], after)

    # --- get_migration ---

    def test_get_migration_not_found(self):
        self.assertIsNone(self.migrator.get_migration("pdmg-nonexistent"))

    def test_get_migration_returns_copy(self):
        record_id = self.migrator.migrate("pipe-1", {"a": 1}, "v1", "v2")
        r1 = self.migrator.get_migration(record_id)
        r2 = self.migrator.get_migration(record_id)
        self.assertEqual(r1, r2)
        self.assertIsNot(r1, r2)

    # --- get_migrations ---

    def test_get_migrations_all(self):
        self.migrator.migrate("pipe-1", {"a": 1}, "v1", "v2")
        self.migrator.migrate("pipe-2", {"b": 1}, "v2", "v3")
        results = self.migrator.get_migrations()
        self.assertEqual(len(results), 2)

    def test_get_migrations_by_pipeline(self):
        self.migrator.migrate("pipe-1", {"a": 1}, "v1", "v2")
        self.migrator.migrate("pipe-2", {"b": 1}, "v2", "v3")
        self.migrator.migrate("pipe-1", {"c": 1}, "v2", "v3")
        results = self.migrator.get_migrations(pipeline_id="pipe-1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["pipeline_id"], "pipe-1")

    def test_get_migrations_limit(self):
        for i in range(10):
            self.migrator.migrate("pipe-1", {"v": i}, "v1", "v2")
        results = self.migrator.get_migrations(limit=3)
        self.assertEqual(len(results), 3)

    def test_get_migrations_sorted_desc(self):
        self.migrator.migrate("pipe-1", {"a": 1}, "v1", "v2")
        self.migrator.migrate("pipe-1", {"b": 1}, "v2", "v3")
        results = self.migrator.get_migrations()
        self.assertGreaterEqual(results[0]["created_at"], results[1]["created_at"])

    def test_get_migrations_returns_copies(self):
        self.migrator.migrate("pipe-1", {"a": 1}, "v1", "v2")
        r1 = self.migrator.get_migrations()
        r2 = self.migrator.get_migrations()
        self.assertIsNot(r1[0], r2[0])

    # --- get_migration_count ---

    def test_get_migration_count_all(self):
        self.migrator.migrate("pipe-1", {}, "v1", "v2")
        self.migrator.migrate("pipe-2", {}, "v1", "v2")
        self.assertEqual(self.migrator.get_migration_count(), 2)

    def test_get_migration_count_by_pipeline(self):
        self.migrator.migrate("pipe-1", {}, "v1", "v2")
        self.migrator.migrate("pipe-2", {}, "v1", "v2")
        self.migrator.migrate("pipe-1", {}, "v2", "v3")
        self.assertEqual(self.migrator.get_migration_count(pipeline_id="pipe-1"), 2)
        self.assertEqual(self.migrator.get_migration_count(pipeline_id="pipe-2"), 1)

    def test_get_migration_count_empty_pipeline(self):
        self.assertEqual(self.migrator.get_migration_count(pipeline_id="nonexistent"), 0)

    # --- Callbacks ---

    def test_register_and_fire_callback(self):
        events = []
        self.migrator.register_callback("test_cb", lambda e: events.append(e))
        self.migrator.migrate("pipe-1", {"a": 1}, "v1", "v2")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["action"], "migrate")
        self.assertEqual(events[0]["data"]["pipeline_id"], "pipe-1")

    def test_callback_receives_version_info(self):
        events = []
        self.migrator.register_callback("test_cb", lambda e: events.append(e))
        self.migrator.migrate("pipe-1", {}, "v1", "v2")
        self.assertEqual(events[0]["data"]["from_version"], "v1")
        self.assertEqual(events[0]["data"]["to_version"], "v2")

    def test_remove_callback(self):
        self.migrator.register_callback("test_cb", lambda e: None)
        self.assertTrue(self.migrator.remove_callback("test_cb"))

    def test_remove_callback_not_found(self):
        self.assertFalse(self.migrator.remove_callback("nonexistent"))

    def test_callback_error_does_not_raise(self):
        def bad_callback(e):
            raise ValueError("boom")
        self.migrator.register_callback("bad", bad_callback)
        record_id = self.migrator.migrate("pipe-1", {"a": 1}, "v1", "v2")
        self.assertIsNotNone(record_id)

    def test_on_change_property(self):
        self.assertIsNotNone(self.migrator.on_change)
        self.assertTrue(callable(self.migrator.on_change))

    def test_multiple_callbacks_fired(self):
        events_a = []
        events_b = []
        self.migrator.register_callback("cb_a", lambda e: events_a.append(e))
        self.migrator.register_callback("cb_b", lambda e: events_b.append(e))
        self.migrator.migrate("pipe-1", {}, "v1", "v2")
        self.assertEqual(len(events_a), 1)
        self.assertEqual(len(events_b), 1)

    # --- get_stats ---

    def test_get_stats_after_migrations(self):
        self.migrator.migrate("pipe-1", {}, "v1", "v2")
        self.migrator.migrate("pipe-2", {}, "v1", "v2")
        self.migrator.register_callback("cb1", lambda e: None)
        stats = self.migrator.get_stats()
        self.assertEqual(stats["total_migrations"], 2)
        self.assertEqual(stats["pipeline_count"], 2)
        self.assertEqual(stats["callbacks_registered"], 1)

    # --- reset ---

    def test_reset(self):
        self.migrator.migrate("pipe-1", {"a": 1}, "v1", "v2")
        self.migrator.register_callback("cb", lambda e: None)
        self.migrator.reset()
        self.assertEqual(self.migrator.get_migration_count(), 0)
        self.assertEqual(self.migrator.get_stats()["callbacks_registered"], 0)
        self.assertEqual(self.migrator.get_migrations(), [])

    # --- Pruning ---

    def test_prune_oldest_quarter(self):
        self.migrator.MAX_ENTRIES = 20
        for i in range(25):
            self.migrator.migrate(f"pipe-{i}", {"v": i}, "v1", "v2")
        self.assertLessEqual(self.migrator.get_migration_count(), 20)

    def test_prune_removes_oldest(self):
        self.migrator.MAX_ENTRIES = 8
        ids = []
        for i in range(10):
            ids.append(self.migrator.migrate(f"pipe-{i}", {"v": i}, "v1", "v2"))
        # Oldest entries should have been pruned
        remaining = [self.migrator.get_migration(rid) for rid in ids]
        removed = [r for r in remaining if r is None]
        self.assertGreater(len(removed), 0)

    # --- ID generation ---

    def test_unique_ids(self):
        ids = set()
        for i in range(50):
            record_id = self.migrator.migrate("pipe-1", {"v": i}, "v1", "v2")
            ids.add(record_id)
        self.assertEqual(len(ids), 50)

    def test_id_prefix(self):
        record_id = self.migrator.migrate("pipe-1", {}, "v1", "v2")
        self.assertTrue(record_id.startswith("pdmg-"))

    # --- Edge cases ---

    def test_migrate_empty_data(self):
        record_id = self.migrator.migrate("pipe-1", {}, "v1", "v2")
        result = self.migrator.get_migration(record_id)
        self.assertEqual(result["data"], {})

    def test_migrate_complex_data(self):
        data = {"nested": {"key": [1, 2, 3]}, "flag": True}
        record_id = self.migrator.migrate("pipe-1", data, "v1", "v2")
        result = self.migrator.get_migration(record_id)
        self.assertEqual(result["data"], data)

    def test_pipeline_id_in_entry(self):
        record_id = self.migrator.migrate("my-pipeline", {}, "v1", "v2")
        result = self.migrator.get_migration(record_id)
        self.assertEqual(result["pipeline_id"], "my-pipeline")

    def test_version_strings_in_entry(self):
        record_id = self.migrator.migrate("pipe-1", {}, "1.0.0", "2.0.0")
        result = self.migrator.get_migration(record_id)
        self.assertEqual(result["from_version"], "1.0.0")
        self.assertEqual(result["to_version"], "2.0.0")


if __name__ == "__main__":
    unittest.main()
