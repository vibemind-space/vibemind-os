import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_command_executor import AgentCommandExecutor, AgentCommandExecutorState


class TestAgentCommandExecutor(unittest.TestCase):
    def setUp(self):
        self.executor = AgentCommandExecutor()

    def test_register_command(self):
        cmd_id = self.executor.register_command("agent-1", "deploy")
        self.assertTrue(cmd_id.startswith("ace-"))
        self.assertEqual(len(cmd_id), 4 + 16)  # "ace-" + 16 hex chars

    def test_get_command(self):
        cmd_id = self.executor.register_command("agent-1", "deploy", params=["env", "version"])
        cmd = self.executor.get_command(cmd_id)
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd["agent_id"], "agent-1")
        self.assertEqual(cmd["command_name"], "deploy")
        self.assertEqual(cmd["params"], ["env", "version"])

    def test_get_command_not_found(self):
        self.assertIsNone(self.executor.get_command("ace-nonexistent"))

    def test_execute_command_no_handler(self):
        self.executor.register_command("agent-1", "echo")
        result = self.executor.execute_command("agent-1", "echo", args={"msg": "hello"})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"], {"msg": "hello"})
        self.assertIn("duration_ms", result)

    def test_execute_command_with_handler(self):
        def add(a, b):
            return a + b

        self.executor.register_command("agent-1", "add", handler_fn=add, params=["a", "b"])
        result = self.executor.execute_command("agent-1", "add", args={"a": 3, "b": 5})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"], 8)

    def test_execute_command_error(self):
        def fail():
            raise ValueError("boom")

        self.executor.register_command("agent-1", "fail", handler_fn=fail)
        result = self.executor.execute_command("agent-1", "fail")
        self.assertEqual(result["status"], "error")
        self.assertIn("boom", result["result"])

    def test_execute_command_not_found(self):
        result = self.executor.execute_command("agent-x", "nope")
        self.assertEqual(result["status"], "error")
        self.assertIsNone(result["command_id"])

    def test_get_commands(self):
        self.executor.register_command("agent-1", "cmd1")
        self.executor.register_command("agent-1", "cmd2")
        self.executor.register_command("agent-2", "cmd3")
        cmds = self.executor.get_commands("agent-1")
        self.assertEqual(len(cmds), 2)

    def test_get_execution_history(self):
        self.executor.register_command("agent-1", "run")
        self.executor.execute_command("agent-1", "run", args={"x": 1})
        self.executor.execute_command("agent-1", "run", args={"x": 2})
        history = self.executor.get_execution_history("agent-1")
        self.assertEqual(len(history), 2)

    def test_get_execution_history_with_filter(self):
        self.executor.register_command("agent-1", "run")
        self.executor.register_command("agent-1", "stop")
        self.executor.execute_command("agent-1", "run", args={"x": 1})
        self.executor.execute_command("agent-1", "stop")
        history = self.executor.get_execution_history("agent-1", command_name="run")
        self.assertEqual(len(history), 1)

    def test_remove_command(self):
        cmd_id = self.executor.register_command("agent-1", "cmd")
        self.assertTrue(self.executor.remove_command(cmd_id))
        self.assertIsNone(self.executor.get_command(cmd_id))
        self.assertFalse(self.executor.remove_command(cmd_id))

    def test_get_command_count(self):
        self.executor.register_command("agent-1", "a")
        self.executor.register_command("agent-1", "b")
        self.executor.register_command("agent-2", "c")
        self.assertEqual(self.executor.get_command_count(), 3)
        self.assertEqual(self.executor.get_command_count("agent-1"), 2)
        self.assertEqual(self.executor.get_command_count("agent-2"), 1)

    def test_list_agents(self):
        self.executor.register_command("agent-b", "x")
        self.executor.register_command("agent-a", "y")
        agents = self.executor.list_agents()
        self.assertEqual(agents, ["agent-a", "agent-b"])

    def test_get_stats(self):
        self.executor.register_command("agent-1", "cmd")
        self.executor.execute_command("agent-1", "cmd")
        stats = self.executor.get_stats()
        self.assertEqual(stats["total_commands"], 1)
        self.assertEqual(stats["total_executions"], 1)
        self.assertEqual(stats["total_agents"], 1)

    def test_reset(self):
        self.executor.register_command("agent-1", "cmd")
        self.executor.reset()
        self.assertEqual(self.executor.get_command_count(), 0)
        self.assertEqual(self.executor.list_agents(), [])

    def test_on_change_callback(self):
        events = []
        self.executor.on_change = lambda evt, data: events.append(evt)
        self.executor.register_command("agent-1", "cmd")
        self.assertIn("command_registered", events)

    def test_remove_callback(self):
        self.executor._callbacks["cb1"] = lambda e, d: None
        self.assertTrue(self.executor.remove_callback("cb1"))
        self.assertFalse(self.executor.remove_callback("cb1"))

    def test_prune_max_entries(self):
        executor = AgentCommandExecutor()
        executor.MAX_ENTRIES = 5
        for i in range(8):
            executor.register_command("agent-1", f"cmd-{i}")
        self.assertLessEqual(len(executor._state.entries), 5)

    def test_unique_ids(self):
        id1 = self.executor.register_command("agent-1", "cmd")
        id2 = self.executor.register_command("agent-1", "cmd2")
        self.assertNotEqual(id1, id2)

    def test_execution_history_limit(self):
        self.executor.register_command("agent-1", "run")
        for i in range(30):
            self.executor.execute_command("agent-1", "run", args={"i": i})
        history = self.executor.get_execution_history("agent-1", limit=5)
        self.assertEqual(len(history), 5)

    def test_state_dataclass(self):
        state = AgentCommandExecutorState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)


if __name__ == "__main__":
    unittest.main()
