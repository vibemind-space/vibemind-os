"""Tests for AgentWorkflowMigrator service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_workflow_migrator import AgentWorkflowMigrator

class TestIdGeneration:
    def test_prefix(self):
        s = AgentWorkflowMigrator()
        assert s.migrate("a1", "wf1", "prod").startswith("awmg-")
    def test_unique(self):
        s = AgentWorkflowMigrator()
        ids = {s.migrate("a1", f"wf{i}", "prod") for i in range(20)}
        assert len(ids) == 20

class TestMigrateBasic:
    def test_returns_id(self):
        s = AgentWorkflowMigrator()
        assert len(s.migrate("a1", "wf1", "prod")) > 0
    def test_stores_fields(self):
        s = AgentWorkflowMigrator()
        rid = s.migrate("a1", "wf1", "staging")
        e = s.get_migration(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["target_env"] == "staging"
    def test_with_metadata(self):
        s = AgentWorkflowMigrator()
        rid = s.migrate("a1", "wf1", "prod", metadata={"x": 1})
        assert s.get_migration(rid)["metadata"]["x"] == 1
    def test_metadata_deepcopy(self):
        s = AgentWorkflowMigrator()
        m = {"a": [1]}
        rid = s.migrate("a1", "wf1", "prod", metadata=m)
        m["a"].append(2)
        assert s.get_migration(rid)["metadata"]["a"] == [1]
    def test_created_at(self):
        s = AgentWorkflowMigrator()
        before = time.time()
        rid = s.migrate("a1", "wf1", "prod")
        assert s.get_migration(rid)["created_at"] >= before
    def test_empty_agent_returns_empty(self):
        assert AgentWorkflowMigrator().migrate("", "wf1", "prod") == ""
    def test_empty_workflow_returns_empty(self):
        assert AgentWorkflowMigrator().migrate("a1", "", "prod") == ""
    def test_empty_target_returns_empty(self):
        assert AgentWorkflowMigrator().migrate("a1", "wf1", "") == ""

class TestGetMigration:
    def test_found(self):
        s = AgentWorkflowMigrator()
        rid = s.migrate("a1", "wf1", "prod")
        assert s.get_migration(rid) is not None
    def test_not_found(self):
        assert AgentWorkflowMigrator().get_migration("xxx") is None
    def test_returns_copy(self):
        s = AgentWorkflowMigrator()
        rid = s.migrate("a1", "wf1", "prod")
        assert s.get_migration(rid) is not s.get_migration(rid)

class TestGetMigrations:
    def test_all(self):
        s = AgentWorkflowMigrator()
        s.migrate("a1", "wf1", "prod"); s.migrate("a2", "wf2", "staging")
        assert len(s.get_migrations()) == 2
    def test_filter(self):
        s = AgentWorkflowMigrator()
        s.migrate("a1", "wf1", "prod"); s.migrate("a2", "wf2", "staging")
        assert len(s.get_migrations(agent_id="a1")) == 1
    def test_newest_first(self):
        s = AgentWorkflowMigrator()
        s.migrate("a1", "wf1", "prod"); s.migrate("a1", "wf2", "staging")
        assert s.get_migrations(agent_id="a1")[0]["workflow_name"] == "wf2"
    def test_limit(self):
        s = AgentWorkflowMigrator()
        for i in range(10): s.migrate("a1", f"wf{i}", "prod")
        assert len(s.get_migrations(limit=3)) == 3

class TestGetMigrationCount:
    def test_total(self):
        s = AgentWorkflowMigrator()
        s.migrate("a1", "wf1", "prod"); s.migrate("a2", "wf2", "staging")
        assert s.get_migration_count() == 2
    def test_filtered(self):
        s = AgentWorkflowMigrator()
        s.migrate("a1", "wf1", "prod"); s.migrate("a2", "wf2", "staging")
        assert s.get_migration_count(agent_id="a1") == 1
    def test_empty(self):
        assert AgentWorkflowMigrator().get_migration_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentWorkflowMigrator().get_stats()["total_migrations"] == 0
    def test_with_data(self):
        s = AgentWorkflowMigrator()
        s.migrate("a1", "wf1", "prod"); s.migrate("a2", "wf2", "staging")
        st = s.get_stats()
        assert st["total_migrations"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowMigrator()
        evts = []
        s.on_change = lambda a, d: evts.append(a)
        s.migrate("a1", "wf1", "prod")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        s = AgentWorkflowMigrator()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentWorkflowMigrator().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowMigrator()
        s.MAX_ENTRIES = 5
        for i in range(8): s.migrate("a1", f"wf{i}", "prod")
        assert s.get_migration_count() < 8

class TestReset:
    def test_clears(self):
        s = AgentWorkflowMigrator()
        s.migrate("a1", "wf1", "prod"); s.reset()
        assert s.get_migration_count() == 0
    def test_clears_callbacks(self):
        s = AgentWorkflowMigrator()
        s.on_change = lambda a, d: None
        s.reset()
        assert s.on_change is None
    def test_resets_seq(self):
        s = AgentWorkflowMigrator()
        s.migrate("a1", "wf1", "prod"); s.reset()
        assert s._state._seq == 0
