import sys
import unittest

sys.path.insert(0, ".")

from src.services.pipeline_data_lookup import PipelineDataLookup


class TestPipelineDataLookup(unittest.TestCase):

    def setUp(self):
        self.pdl = PipelineDataLookup()

    def test_create_table_returns_id(self):
        tid = self.pdl.create_table("p1", "users", "user_id")
        self.assertTrue(tid.startswith("pdl-"))
        self.assertEqual(len(tid), 4 + 16)  # "pdl-" + 16 hex chars

    def test_load_data_and_lookup(self):
        tid = self.pdl.create_table("p1", "users", "id")
        records = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        count = self.pdl.load_data(tid, records)
        self.assertEqual(count, 2)
        result = self.pdl.lookup(tid, 1)
        self.assertEqual(result["name"], "Alice")

    def test_lookup_missing_key(self):
        tid = self.pdl.create_table("p1", "t", "k")
        self.pdl.load_data(tid, [{"k": "a", "v": 1}])
        self.assertIsNone(self.pdl.lookup(tid, "nonexistent"))

    def test_lookup_invalid_table(self):
        self.assertIsNone(self.pdl.lookup("pdl-fake", "key"))

    def test_lookup_many(self):
        tid = self.pdl.create_table("p1", "items", "code")
        self.pdl.load_data(tid, [
            {"code": "A", "val": 10},
            {"code": "B", "val": 20},
            {"code": "C", "val": 30},
        ])
        results = self.pdl.lookup_many(tid, ["A", "missing", "C"])
        self.assertEqual(results[0]["val"], 10)
        self.assertIsNone(results[1])
        self.assertEqual(results[2]["val"], 30)

    def test_get_table(self):
        tid = self.pdl.create_table("p1", "tbl", "id")
        self.pdl.load_data(tid, [{"id": 1}, {"id": 2}])
        info = self.pdl.get_table(tid)
        self.assertEqual(info["table_name"], "tbl")
        self.assertEqual(info["size"], 2)

    def test_get_table_invalid(self):
        self.assertIsNone(self.pdl.get_table("pdl-nope"))

    def test_get_tables_by_pipeline(self):
        self.pdl.create_table("p1", "a", "id")
        self.pdl.create_table("p1", "b", "id")
        self.pdl.create_table("p2", "c", "id")
        tables = self.pdl.get_tables("p1")
        self.assertEqual(len(tables), 2)

    def test_get_table_size(self):
        tid = self.pdl.create_table("p1", "t", "k")
        self.assertEqual(self.pdl.get_table_size(tid), 0)
        self.pdl.load_data(tid, [{"k": "x"}, {"k": "y"}])
        self.assertEqual(self.pdl.get_table_size(tid), 2)

    def test_get_table_count(self):
        self.pdl.create_table("p1", "a", "id")
        self.pdl.create_table("p1", "b", "id")
        self.pdl.create_table("p2", "c", "id")
        self.assertEqual(self.pdl.get_table_count(), 3)
        self.assertEqual(self.pdl.get_table_count("p1"), 2)
        self.assertEqual(self.pdl.get_table_count("p2"), 1)

    def test_list_pipelines(self):
        self.pdl.create_table("beta", "t1", "id")
        self.pdl.create_table("alpha", "t2", "id")
        self.pdl.create_table("beta", "t3", "id")
        pipelines = self.pdl.list_pipelines()
        self.assertEqual(pipelines, ["alpha", "beta"])

    def test_callbacks(self):
        events = []
        cb_id = self.pdl.on_change(lambda e, d: events.append((e, d)))
        tid = self.pdl.create_table("p1", "t", "id")
        self.pdl.load_data(tid, [{"id": 1}])
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0][0], "table_created")
        self.assertEqual(events[1][0], "data_loaded")
        self.assertTrue(self.pdl.remove_callback(cb_id))
        self.assertFalse(self.pdl.remove_callback(cb_id))

    def test_get_stats_and_reset(self):
        self.pdl.create_table("p1", "t", "id")
        stats = self.pdl.get_stats()
        self.assertEqual(stats["total_tables"], 1)
        self.assertGreater(stats["seq"], 0)
        self.pdl.reset()
        stats = self.pdl.get_stats()
        self.assertEqual(stats["total_tables"], 0)
        self.assertEqual(stats["seq"], 0)

    def test_load_data_invalid_table(self):
        with self.assertRaises(ValueError):
            self.pdl.load_data("pdl-bogus", [{"a": 1}])

    def test_records_without_key_field_skipped(self):
        tid = self.pdl.create_table("p1", "t", "id")
        count = self.pdl.load_data(tid, [{"id": 1}, {"no_id": 2}, {"id": 3}])
        self.assertEqual(count, 2)
        self.assertEqual(self.pdl.get_table_size(tid), 2)


if __name__ == "__main__":
    unittest.main()
