import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_migrator import PipelineStepMigrator


class TestBasic:
    def test_returns_id(self):
        s = PipelineStepMigrator()
        assert s.migrate("p1", "s1").startswith("psmr-")

    def test_fields(self):
        s = PipelineStepMigrator()
        rid = s.migrate("p1", "s1", target_env="prod")
        e = s.get_migration(rid)
        assert e["pipeline_id"] == "p1"
        assert e["step_name"] == "s1"
        assert e["target_env"] == "prod"

    def test_default_env(self):
        s = PipelineStepMigrator()
        rid = s.migrate("p1", "s1")
        assert s.get_migration(rid)["target_env"] == "staging"

    def test_metadata(self):
        s = PipelineStepMigrator()
        rid = s.migrate("p1", "s1", metadata={"x": 1})
        assert s.get_migration(rid)["metadata"] == {"x": 1}

    def test_metadata_deepcopy(self):
        s = PipelineStepMigrator()
        m = {"x": [1]}
        rid = s.migrate("p1", "s1", metadata=m)
        m["x"].append(2)
        assert s.get_migration(rid)["metadata"] == {"x": [1]}

    def test_empty_pipeline(self):
        assert PipelineStepMigrator().migrate("", "s1") == ""

    def test_empty_step(self):
        assert PipelineStepMigrator().migrate("p1", "") == ""


class TestGet:
    def test_found(self):
        s = PipelineStepMigrator()
        rid = s.migrate("p1", "s1")
        assert s.get_migration(rid) is not None

    def test_not_found(self):
        assert PipelineStepMigrator().get_migration("nope") is None

    def test_copy(self):
        s = PipelineStepMigrator()
        rid = s.migrate("p1", "s1")
        assert s.get_migration(rid) is not s.get_migration(rid)


class TestList:
    def test_all(self):
        s = PipelineStepMigrator()
        s.migrate("p1", "s1"); s.migrate("p2", "s2")
        assert len(s.get_migrations()) == 2

    def test_filter(self):
        s = PipelineStepMigrator()
        s.migrate("p1", "s1"); s.migrate("p2", "s2")
        assert len(s.get_migrations("p1")) == 1

    def test_newest_first(self):
        s = PipelineStepMigrator()
        s.migrate("p1", "s1"); s.migrate("p1", "s2")
        assert s.get_migrations("p1")[0]["_seq"] > s.get_migrations("p1")[1]["_seq"]

    def test_limit(self):
        s = PipelineStepMigrator()
        for i in range(5): s.migrate("p1", f"s{i}")
        assert len(s.get_migrations(limit=3)) == 3


class TestCount:
    def test_total(self):
        s = PipelineStepMigrator()
        s.migrate("p1", "s1"); s.migrate("p2", "s2")
        assert s.get_migration_count() == 2

    def test_filtered(self):
        s = PipelineStepMigrator()
        s.migrate("p1", "s1"); s.migrate("p2", "s2")
        assert s.get_migration_count("p1") == 1

    def test_empty(self):
        assert PipelineStepMigrator().get_migration_count() == 0


class TestStats:
    def test_empty(self):
        assert PipelineStepMigrator().get_stats()["total_migrations"] == 0

    def test_data(self):
        s = PipelineStepMigrator()
        s.migrate("p1", "s1"); s.migrate("p2", "s2")
        st = s.get_stats()
        assert st["total_migrations"] == 2
        assert st["unique_pipelines"] == 2


class TestCallbacks:
    def test_on_change(self):
        s = PipelineStepMigrator()
        calls = []
        s.on_change = lambda a, d: calls.append(a)
        s.migrate("p1", "s1")
        assert "migrated" in calls

    def test_remove_true(self):
        s = PipelineStepMigrator()
        s._state.callbacks["cb1"] = lambda a, d: None
        assert s.remove_callback("cb1") is True

    def test_remove_false(self):
        assert PipelineStepMigrator().remove_callback("nope") is False


class TestPrune:
    def test_prune(self):
        s = PipelineStepMigrator(); s.MAX_ENTRIES = 5
        for i in range(8): s.migrate("p1", f"s{i}")
        assert s.get_migration_count() < 8


class TestReset:
    def test_clears(self):
        s = PipelineStepMigrator()
        s.migrate("p1", "s1"); s.reset()
        assert s.get_migration_count() == 0

    def test_callbacks(self):
        s = PipelineStepMigrator()
        s.on_change = lambda a, d: None; s.reset()
        assert s.on_change is None

    def test_seq(self):
        s = PipelineStepMigrator()
        s.migrate("p1", "s1"); s.reset()
        assert s._state._seq == 0
