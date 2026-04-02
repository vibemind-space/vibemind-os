"""Tests for AgentCircuitBreaker."""

import sys
import time
import unittest

sys.path.insert(0, ".")

from src.services.agent_circuit_breaker import AgentCircuitBreaker


class TestAgentCircuitBreaker(unittest.TestCase):
    """Tests for the AgentCircuitBreaker service."""

    def setUp(self):
        self.cb = AgentCircuitBreaker()

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def test_create_circuit(self):
        cid = self.cb.create_circuit("agent-1", "deploy")
        self.assertTrue(cid.startswith("acb-"))
        self.assertEqual(len(cid), 4 + 16)  # "acb-" + 16 hex chars

    def test_create_circuit_idempotent(self):
        cid1 = self.cb.create_circuit("agent-1", "deploy")
        cid2 = self.cb.create_circuit("agent-1", "deploy")
        self.assertEqual(cid1, cid2)

    def test_create_circuit_default_state_closed(self):
        self.cb.create_circuit("agent-1", "build")
        state = self.cb.get_state("agent-1", "build")
        self.assertEqual(state, "closed")

    # ------------------------------------------------------------------
    # Success / failure recording
    # ------------------------------------------------------------------

    def test_record_success_returns_true(self):
        self.cb.create_circuit("agent-1", "test")
        result = self.cb.record_success("agent-1", "test")
        self.assertTrue(result)

    def test_record_success_no_circuit_returns_false(self):
        result = self.cb.record_success("ghost", "op")
        self.assertFalse(result)

    def test_record_failure_returns_dict(self):
        self.cb.create_circuit("agent-1", "deploy", failure_threshold=3)
        result = self.cb.record_failure("agent-1", "deploy")
        self.assertIn("circuit_id", result)
        self.assertIn("state", result)
        self.assertEqual(result["failure_count"], 1)

    def test_record_failure_no_circuit_returns_empty(self):
        result = self.cb.record_failure("ghost", "op")
        self.assertEqual(result, {})

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def test_threshold_opens_circuit(self):
        self.cb.create_circuit("agent-1", "deploy", failure_threshold=3)
        for _ in range(3):
            self.cb.record_failure("agent-1", "deploy")
        state = self.cb.get_state("agent-1", "deploy")
        self.assertEqual(state, "open")

    def test_open_blocks_requests(self):
        self.cb.create_circuit("agent-1", "deploy", failure_threshold=2)
        self.cb.record_failure("agent-1", "deploy")
        self.cb.record_failure("agent-1", "deploy")
        self.assertFalse(self.cb.is_allowed("agent-1", "deploy"))

    def test_timeout_transitions_to_half_open(self):
        self.cb.create_circuit("agent-1", "deploy", failure_threshold=1, reset_timeout=0.01)
        self.cb.record_failure("agent-1", "deploy")
        self.assertEqual(self.cb.get_state("agent-1", "deploy"), "open")
        time.sleep(0.02)
        state = self.cb.get_state("agent-1", "deploy")
        self.assertEqual(state, "half_open")
        self.assertTrue(self.cb.is_allowed("agent-1", "deploy"))

    def test_half_open_success_closes_circuit(self):
        self.cb.create_circuit("agent-1", "deploy", failure_threshold=1, reset_timeout=0.01)
        self.cb.record_failure("agent-1", "deploy")
        time.sleep(0.02)
        self.cb.get_state("agent-1", "deploy")  # triggers half_open
        self.cb.record_success("agent-1", "deploy")
        state = self.cb.get_state("agent-1", "deploy")
        self.assertEqual(state, "closed")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def test_callback_fires_on_create(self):
        events = []
        self.cb.on_change("listener", lambda action, detail: events.append(action))
        self.cb.create_circuit("agent-1", "build")
        self.assertIn("circuit_created", events)

    def test_callback_fires_on_open(self):
        events = []
        self.cb.on_change("listener", lambda action, detail: events.append(action))
        self.cb.create_circuit("agent-1", "build", failure_threshold=1)
        self.cb.record_failure("agent-1", "build")
        self.assertIn("circuit_opened", events)

    def test_remove_callback(self):
        self.cb.on_change("x", lambda a, d: None)
        self.assertTrue(self.cb.remove_callback("x"))
        self.assertFalse(self.cb.remove_callback("x"))

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def test_get_circuit_by_id(self):
        cid = self.cb.create_circuit("agent-1", "deploy")
        circuit = self.cb.get_circuit(cid)
        self.assertIsNotNone(circuit)
        self.assertEqual(circuit["agent_id"], "agent-1")

    def test_get_circuit_not_found(self):
        self.assertIsNone(self.cb.get_circuit("acb-nonexistent"))

    def test_get_circuits_by_agent(self):
        self.cb.create_circuit("agent-1", "deploy")
        self.cb.create_circuit("agent-1", "build")
        self.cb.create_circuit("agent-2", "deploy")
        circuits = self.cb.get_circuits("agent-1")
        self.assertEqual(len(circuits), 2)

    def test_get_circuit_count(self):
        self.cb.create_circuit("agent-1", "deploy")
        self.cb.create_circuit("agent-2", "build")
        self.assertEqual(self.cb.get_circuit_count(), 2)
        self.assertEqual(self.cb.get_circuit_count("agent-1"), 1)

    def test_list_agents(self):
        self.cb.create_circuit("agent-b", "op")
        self.cb.create_circuit("agent-a", "op")
        agents = self.cb.list_agents()
        self.assertEqual(agents, ["agent-a", "agent-b"])

    # ------------------------------------------------------------------
    # Stats / reset
    # ------------------------------------------------------------------

    def test_get_stats(self):
        self.cb.create_circuit("a1", "op1")
        self.cb.create_circuit("a1", "op2", failure_threshold=1)
        self.cb.record_failure("a1", "op2")
        stats = self.cb.get_stats()
        self.assertEqual(stats["total_circuits"], 2)
        self.assertEqual(stats["closed"], 1)
        self.assertEqual(stats["open"], 1)

    def test_reset_clears_state(self):
        self.cb.create_circuit("agent-1", "deploy")
        self.cb.reset()
        self.assertEqual(self.cb.get_circuit_count(), 0)
        self.assertEqual(self.cb.get_state("agent-1", "deploy"), "")

    def test_is_allowed_no_circuit(self):
        self.assertTrue(self.cb.is_allowed("ghost", "op"))


if __name__ == "__main__":
    unittest.main()
