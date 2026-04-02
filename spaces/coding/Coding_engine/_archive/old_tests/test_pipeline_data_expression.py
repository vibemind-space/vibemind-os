"""Tests for PipelineDataExpression."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_data_expression import PipelineDataExpression


class TestPipelineDataExpression(unittest.TestCase):
    def setUp(self):
        self.pde = PipelineDataExpression()

    def test_add_expression_returns_id(self):
        expr_id = self.pde.add_expression("p1", "total", "price", "+", "tax")
        self.assertTrue(expr_id.startswith("pde-"))
        self.assertEqual(len(expr_id), 4 + 16)  # prefix + hash

    def test_add_expression_invalid_operator(self):
        with self.assertRaises(ValueError):
            self.pde.add_expression("p1", "x", "a", "mod", "b")

    def test_evaluate_addition(self):
        self.pde.add_expression("p1", "total", "price", "+", "tax")
        result = self.pde.evaluate("p1", {"price": 100, "tax": 15})
        self.assertEqual(result["total"], 115)
        self.assertEqual(result["price"], 100)

    def test_evaluate_subtraction(self):
        self.pde.add_expression("p1", "diff", "a", "-", "b")
        result = self.pde.evaluate("p1", {"a": 50, "b": 20})
        self.assertEqual(result["diff"], 30)

    def test_evaluate_multiplication(self):
        self.pde.add_expression("p1", "product", "qty", "*", 5)
        result = self.pde.evaluate("p1", {"qty": 10})
        self.assertEqual(result["product"], 50)

    def test_evaluate_division(self):
        self.pde.add_expression("p1", "avg", "total", "/", "count")
        result = self.pde.evaluate("p1", {"total": 100, "count": 4})
        self.assertEqual(result["avg"], 25)

    def test_evaluate_division_by_zero(self):
        self.pde.add_expression("p1", "avg", "total", "/", "count")
        result = self.pde.evaluate("p1", {"total": 100, "count": 0})
        self.assertEqual(result["avg"], 0)

    def test_evaluate_concat(self):
        self.pde.add_expression("p1", "full_name", "first", "concat", "last")
        result = self.pde.evaluate("p1", {"first": "John", "last": "Doe"})
        self.assertEqual(result["full_name"], "JohnDoe")

    def test_evaluate_upper(self):
        self.pde.add_expression("p1", "upper_name", "name", "upper", "")
        result = self.pde.evaluate("p1", {"name": "hello"})
        self.assertEqual(result["upper_name"], "HELLO")

    def test_evaluate_lower(self):
        self.pde.add_expression("p1", "lower_name", "name", "lower", "")
        result = self.pde.evaluate("p1", {"name": "HELLO"})
        self.assertEqual(result["lower_name"], "hello")

    def test_evaluate_many(self):
        self.pde.add_expression("p1", "doubled", "val", "*", 2)
        records = [{"val": 1}, {"val": 2}, {"val": 3}]
        results = self.pde.evaluate_many("p1", records)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["doubled"], 2)
        self.assertEqual(results[2]["doubled"], 6)

    def test_get_expressions(self):
        self.pde.add_expression("p1", "a", "x", "+", "y")
        self.pde.add_expression("p2", "b", "x", "-", "y")
        self.assertEqual(len(self.pde.get_expressions("p1")), 1)
        self.assertEqual(len(self.pde.get_expressions("p2")), 1)

    def test_remove_expression(self):
        expr_id = self.pde.add_expression("p1", "a", "x", "+", "y")
        self.assertTrue(self.pde.remove_expression(expr_id))
        self.assertFalse(self.pde.remove_expression(expr_id))
        self.assertEqual(self.pde.get_expression_count(), 0)

    def test_get_expression_count(self):
        self.pde.add_expression("p1", "a", "x", "+", "y")
        self.pde.add_expression("p1", "b", "x", "-", "y")
        self.pde.add_expression("p2", "c", "x", "*", "y")
        self.assertEqual(self.pde.get_expression_count(), 3)
        self.assertEqual(self.pde.get_expression_count("p1"), 2)
        self.assertEqual(self.pde.get_expression_count("p2"), 1)

    def test_list_pipelines(self):
        self.pde.add_expression("p1", "a", "x", "+", "y")
        self.pde.add_expression("p2", "b", "x", "-", "y")
        pipelines = self.pde.list_pipelines()
        self.assertEqual(sorted(pipelines), ["p1", "p2"])

    def test_callbacks(self):
        events = []
        self.pde.on_change("test_cb", lambda e, d: events.append(e))
        self.pde.add_expression("p1", "a", "x", "+", "y")
        self.assertEqual(events, ["add_expression"])
        self.assertTrue(self.pde.remove_callback("test_cb"))
        self.assertFalse(self.pde.remove_callback("test_cb"))

    def test_get_stats(self):
        self.pde.add_expression("p1", "a", "x", "+", "y")
        stats = self.pde.get_stats()
        self.assertEqual(stats["total_expressions"], 1)
        self.assertEqual(stats["pipelines"], 1)
        self.assertIn("uptime", stats)

    def test_reset(self):
        self.pde.add_expression("p1", "a", "x", "+", "y")
        self.pde.on_change("cb", lambda e, d: None)
        self.pde.reset()
        self.assertEqual(self.pde.get_expression_count(), 0)
        self.assertEqual(len(self.pde._callbacks), 0)

    def test_unique_ids(self):
        id1 = self.pde.add_expression("p1", "a", "x", "+", "y")
        id2 = self.pde.add_expression("p1", "a", "x", "+", "y")
        self.assertNotEqual(id1, id2)

    def test_prune_max_entries(self):
        pde = PipelineDataExpression()
        pde.MAX_ENTRIES = 10
        for i in range(15):
            pde.add_expression("p1", f"expr_{i}", "x", "+", i)
        self.assertLessEqual(pde.get_expression_count(), 10)


if __name__ == "__main__":
    unittest.main()
