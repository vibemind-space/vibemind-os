import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.agent_workflow_migrator_v2 import AgentWorkflowMigratorV2

class TestBasic:
    def test_returns_id(self):
        s = AgentWorkflowMigratorV2()
        rid = s.migrate_v2("a1", "wf1")
        assert rid.startswith("awmv-")

    def test_fields(self):
        s = AgentWorkflowMigratorV2()
        rid = s.migrate_v2("a1", "wf1", metadata={"k": "v"})
        e = s.get_migration(rid)
        assert e["agent_id"] == "a1"
        assert e["workflow_name"] == "wf1"
        assert e["metadata"] == {"k": "v"}
        assert "created_at" in e

    def test_default_param(self):
        s = AgentWorkflowMigratorV2()
        rid = s.migrate_v2("a1", "wf1")
        assert s.get_migration(rid)["target_version"] == "latest"

    def test_metadata_deepcopy(self):
        s = AgentWorkflowMigratorV2()
        m = {"x": [1]}
        rid = s.migrate_v2("a1", "wf1", metadata=m)
        m["x"].append(2)
        assert s.get_migration(rid)["metadata"]["x"] == [1]

    def test_empty_agent_id(self):
        s = AgentWorkflowMigratorV2()
        assert s.migrate_v2("", "wf1") == ""

    def test_empty_workflow_name(self):
        s = AgentWorkflowMigratorV2()
        assert s.migrate_v2("a1", "") == ""

    def test_unique_ids(self):
        s = AgentWorkflowMigratorV2()
        r1 = s.migrate_v2("a1", "wf1")
        r2 = s.migrate_v2("a1", "wf2")
        assert r1 != r2

class TestGet:
    def test_found(self):
        s = AgentWorkflowMigratorV2()
        rid = s.migrate_v2("a1", "wf1")
        assert s.get_migration(rid) is not None

    def test_not_found(self):
        s = AgentWorkflowMigratorV2()
        assert s.get_migration("nope") is None

    def test_copy(self):
        s = AgentWorkflowMigratorV2()
        rid = s.migrate_v2("a1", "wf1")
        e1 = s.get_migration(rid)
        e2 = s.get_migration(rid)
        assert e1 is not e2

class TestList:
    def test_all(self):
        s = AgentWorkflowMigratorV2()
        s.migrate_v2("a1", "wf1")
        s.migrate_v2("a2", "wf2")
        assert len(s.get_migrations()) == 2

    def test_filter(self):
        s = AgentWorkflowMigratorV2()
        s.migrate_v2("a1", "wf1")
        s.migrate_v2("a2", "wf2")
        assert len(s.get_migrations(agent_id="a1")) == 1

    def test_newest_first(self):
        s = AgentWorkflowMigratorV2()
        s.migrate_v2("a1", "wf1")
        s.migrate_v2("a1", "wf2")
        items = s.get_migrations(agent_id="a1")
        assert items[0]["_seq"] > items[-1]["_seq"]

class TestCount:
    def test_total(self):
        s = AgentWorkflowMigratorV2()
        s.migrate_v2("a1", "wf1")
        s.migrate_v2("a2", "wf2")
        assert s.get_migration_count() == 2

    def test_filtered(self):
        s = AgentWorkflowMigratorV2()
        s.migrate_v2("a1", "wf1")
        s.migrate_v2("a2", "wf2")
        assert s.get_migration_count("a1") == 1

class TestStats:
    def test_data(self):
        s = AgentWorkflowMigratorV2()
        s.migrate_v2("a1", "wf1")
        s.migrate_v2("a2", "wf2")
        st = s.get_stats()
        assert st["total_migrations"] == 2
        assert st["unique_agents"] == 2

class TestCallbacks:
    def test_on_change(self):
        s = AgentWorkflowMigratorV2()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.migrate_v2("a1", "wf1")
        assert len(calls) == 1

    def test_remove_true(self):
        s = AgentWorkflowMigratorV2()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        s = AgentWorkflowMigratorV2()
        assert s.remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = AgentWorkflowMigratorV2()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.migrate_v2(f"a{i}", f"wf{i}")
        assert s.get_migration_count() <= 6

class TestReset:
    def test_clears(self):
        s = AgentWorkflowMigratorV2()
        s.on_change = lambda a, d: None
        s.migrate_v2("a1", "wf1")
        s.reset()
        assert s.get_migration_count() == 0
        assert s.on_change is None

    def test_seq(self):
        s = AgentWorkflowMigratorV2()
        s.migrate_v2("a1", "wf1")
        s.reset()
        assert s._state._seq == 0
