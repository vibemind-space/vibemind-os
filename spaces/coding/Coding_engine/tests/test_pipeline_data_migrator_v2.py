import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pytest
from src.services.pipeline_data_migrator_v2 import PipelineDataMigratorV2

class TestBasic:
    def test_returns_id(self):
        s = PipelineDataMigratorV2()
        rid = s.migrate_v2("v1", "v2")
        assert rid.startswith("pdmv-")
    def test_fields(self):
        s = PipelineDataMigratorV2()
        rid = s.migrate_v2("v1", "v2", metadata={"k": "v"})
        e = s.get_migration(rid)
        assert e["pipeline_id"] == "v1"
        assert e["data_key"] == "v2"
        assert e["metadata"] == {"k": "v"}
    def test_default_param(self):
        s = PipelineDataMigratorV2()
        rid = s.migrate_v2("v1", "v2")
        assert s.get_migration(rid)["target"] == "default"
    def test_metadata_deepcopy(self):
        s = PipelineDataMigratorV2()
        m = {"x": [1]}
        rid = s.migrate_v2("v1", "v2", metadata=m)
        m["x"].append(2)
        assert s.get_migration(rid)["metadata"]["x"] == [1]
    def test_empty_p1(self):
        s = PipelineDataMigratorV2()
        assert s.migrate_v2("", "v2") == ""
    def test_empty_p2(self):
        s = PipelineDataMigratorV2()
        assert s.migrate_v2("v1", "") == ""

class TestGet:
    def test_found(self):
        s = PipelineDataMigratorV2()
        rid = s.migrate_v2("v1", "v2")
        assert s.get_migration(rid) is not None
    def test_not_found(self):
        s = PipelineDataMigratorV2()
        assert s.get_migration("nope") is None
    def test_copy(self):
        s = PipelineDataMigratorV2()
        rid = s.migrate_v2("v1", "v2")
        assert s.get_migration(rid) is not s.get_migration(rid)

class TestList:
    def test_all(self):
        s = PipelineDataMigratorV2()
        s.migrate_v2("v1", "v2")
        s.migrate_v2("v3", "v4")
        assert len(s.get_migrations()) == 2
    def test_filter(self):
        s = PipelineDataMigratorV2()
        s.migrate_v2("v1", "v2")
        s.migrate_v2("v3", "v4")
        assert len(s.get_migrations(pipeline_id="v1")) == 1
    def test_newest_first(self):
        s = PipelineDataMigratorV2()
        s.migrate_v2("p1", "a1")
        s.migrate_v2("p1", "a2")
        items = s.get_migrations(pipeline_id="p1")
        assert items[0]["_seq"] > items[-1]["_seq"]

class TestCount:
    def test_total(self):
        s = PipelineDataMigratorV2()
        s.migrate_v2("v1", "v2")
        s.migrate_v2("v3", "v4")
        assert s.get_migration_count() == 2
    def test_filtered(self):
        s = PipelineDataMigratorV2()
        s.migrate_v2("v1", "v2")
        s.migrate_v2("v3", "v4")
        assert s.get_migration_count("v1") == 1

class TestStats:
    def test_data(self):
        s = PipelineDataMigratorV2()
        s.migrate_v2("v1", "v2")
        st = s.get_stats()
        assert st["total_migrations"] == 1

class TestCallbacks:
    def test_on_change(self):
        s = PipelineDataMigratorV2()
        calls = []
        s.on_change = lambda action, data: calls.append(action)
        s.migrate_v2("v1", "v2")
        assert len(calls) == 1
    def test_remove_true(self):
        s = PipelineDataMigratorV2()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True
    def test_remove_false(self):
        s = PipelineDataMigratorV2()
        assert s.remove_callback("nope") is False

class TestPrune:
    def test_prune(self):
        s = PipelineDataMigratorV2()
        s.MAX_ENTRIES = 5
        for i in range(7):
            s.migrate_v2(f"p{i}", f"v{i}")
        assert s.get_migration_count() <= 6

class TestFireData:
    def test_fire_data_contains_action_key(self):
        s = PipelineDataMigratorV2()
        captured = []
        s.on_change = lambda action, data: captured.append(data)
        s.migrate_v2("t1", "a1")
        assert captured[0]["action"] == "migrate_v2"
        assert captured[0]["record_id"].startswith("pdmv-")

class TestReset:
    def test_clears(self):
        s = PipelineDataMigratorV2()
        s.on_change = lambda a, d: None
        s.migrate_v2("v1", "v2")
        s.reset()
        assert s.get_migration_count() == 0
        assert s.on_change is None
    def test_seq(self):
        s = PipelineDataMigratorV2()
        s.migrate_v2("v1", "v2")
        s.reset()
        assert s._state._seq == 0
