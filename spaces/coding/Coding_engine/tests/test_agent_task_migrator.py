"""Tests for AgentTaskMigrator service."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_migrator import AgentTaskMigrator

class TestIdGeneration:
    def test_prefix(self):
        m = AgentTaskMigrator()
        assert m.migrate("t1", "a1", "a2").startswith("atmr-")
    def test_unique(self):
        m = AgentTaskMigrator()
        ids = {m.migrate(f"t{i}", "a1", "a2") for i in range(20)}
        assert len(ids) == 20

class TestMigrateBasic:
    def test_returns_id(self):
        m = AgentTaskMigrator()
        assert len(m.migrate("t1", "a1", "a2")) > 0
    def test_stores_fields(self):
        m = AgentTaskMigrator()
        rid = m.migrate("t1", "a1", "a2", reason="load")
        e = m.get_migration(rid)
        assert e["task_id"] == "t1"
        assert e["from_agent"] == "a1"
        assert e["to_agent"] == "a2"
        assert e["reason"] == "load"
    def test_with_metadata(self):
        m = AgentTaskMigrator()
        rid = m.migrate("t1", "a1", "a2", metadata={"x": 1})
        assert m.get_migration(rid)["metadata"]["x"] == 1
    def test_created_at(self):
        m = AgentTaskMigrator()
        before = time.time()
        rid = m.migrate("t1", "a1", "a2")
        assert m.get_migration(rid)["created_at"] >= before

class TestMigrateValidation:
    def test_empty_task_id(self):
        assert AgentTaskMigrator().migrate("", "a1", "a2") == ""
    def test_empty_from_agent(self):
        assert AgentTaskMigrator().migrate("t1", "", "a2") == ""
    def test_empty_to_agent(self):
        assert AgentTaskMigrator().migrate("t1", "a1", "") == ""

class TestGetMigration:
    def test_found(self):
        m = AgentTaskMigrator()
        rid = m.migrate("t1", "a1", "a2")
        assert m.get_migration(rid) is not None
    def test_not_found(self):
        assert AgentTaskMigrator().get_migration("xxx") is None
    def test_returns_copy(self):
        m = AgentTaskMigrator()
        rid = m.migrate("t1", "a1", "a2")
        assert m.get_migration(rid) is not m.get_migration(rid)

class TestGetMigrations:
    def test_all(self):
        m = AgentTaskMigrator()
        m.migrate("t1", "a1", "a2"); m.migrate("t2", "a3", "a4")
        assert len(m.get_migrations()) == 2
    def test_filter(self):
        m = AgentTaskMigrator()
        m.migrate("t1", "a1", "a2"); m.migrate("t2", "a3", "a4")
        assert len(m.get_migrations(from_agent="a1")) == 1
    def test_newest_first(self):
        m = AgentTaskMigrator()
        m.migrate("t1", "a1", "a2"); m.migrate("t2", "a1", "a3")
        assert m.get_migrations(from_agent="a1")[0]["task_id"] == "t2"
    def test_limit(self):
        m = AgentTaskMigrator()
        for i in range(10): m.migrate(f"t{i}", "a1", "a2")
        assert len(m.get_migrations(limit=3)) == 3

class TestGetMigrationCount:
    def test_total(self):
        m = AgentTaskMigrator()
        m.migrate("t1", "a1", "a2"); m.migrate("t2", "a3", "a4")
        assert m.get_migration_count() == 2
    def test_filtered(self):
        m = AgentTaskMigrator()
        m.migrate("t1", "a1", "a2"); m.migrate("t2", "a3", "a4")
        assert m.get_migration_count(from_agent="a1") == 1
    def test_empty(self):
        assert AgentTaskMigrator().get_migration_count() == 0

class TestGetStats:
    def test_empty(self):
        assert AgentTaskMigrator().get_stats()["total_migrations"] == 0
    def test_with_data(self):
        m = AgentTaskMigrator()
        m.migrate("t1", "a1", "a2"); m.migrate("t2", "a3", "a4")
        st = m.get_stats()
        assert st["total_migrations"] == 2

class TestCallbacks:
    def test_on_change(self):
        m = AgentTaskMigrator()
        evts = []
        m.on_change = lambda a, d: evts.append(a)
        m.migrate("t1", "a1", "a2")
        assert len(evts) >= 1
    def test_remove_callback_true(self):
        m = AgentTaskMigrator()
        m._state.callbacks["cb1"] = lambda a, d: None
        assert m.remove_callback("cb1") is True
    def test_remove_callback_false(self):
        assert AgentTaskMigrator().remove_callback("x") is False

class TestPrune:
    def test_prune(self):
        m = AgentTaskMigrator()
        m.MAX_ENTRIES = 5
        for i in range(8): m.migrate(f"t{i}", "a1", "a2")
        assert m.get_migration_count() < 8

class TestReset:
    def test_clears(self):
        m = AgentTaskMigrator()
        m.migrate("t1", "a1", "a2"); m.reset()
        assert m.get_migration_count() == 0
    def test_clears_callbacks(self):
        m = AgentTaskMigrator()
        m.on_change = lambda a, d: None
        m.reset()
        assert m.on_change is None
    def test_resets_seq(self):
        m = AgentTaskMigrator()
        m.migrate("t1", "a1", "a2"); m.reset()
        assert m._state._seq == 0
