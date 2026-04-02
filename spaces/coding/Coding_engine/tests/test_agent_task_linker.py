"""Tests for AgentTaskLinker service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.agent_task_linker import AgentTaskLinker


class TestLinkBasic:
    """Basic link creation and retrieval."""

    def test_link_returns_id(self):
        svc = AgentTaskLinker()
        lid = svc.link("src1", "tgt1", "a1")
        assert lid.startswith("atln-")
        assert len(lid) > 5

    def test_link_empty_source_returns_empty(self):
        svc = AgentTaskLinker()
        assert svc.link("", "tgt1", "a1") == ""

    def test_link_empty_target_returns_empty(self):
        svc = AgentTaskLinker()
        assert svc.link("src1", "", "a1") == ""

    def test_link_empty_agent_returns_empty(self):
        svc = AgentTaskLinker()
        assert svc.link("src1", "tgt1", "") == ""

    def test_get_link_existing(self):
        svc = AgentTaskLinker()
        lid = svc.link("src1", "tgt1", "a1", link_type="depends_on")
        entry = svc.get_link(lid)
        assert entry is not None
        assert entry["source_task_id"] == "src1"
        assert entry["target_task_id"] == "tgt1"
        assert entry["agent_id"] == "a1"
        assert entry["link_type"] == "depends_on"

    def test_get_link_nonexistent(self):
        svc = AgentTaskLinker()
        assert svc.get_link("atln-nonexistent") is None

    def test_default_link_type_is_related(self):
        svc = AgentTaskLinker()
        lid = svc.link("src1", "tgt1", "a1")
        entry = svc.get_link(lid)
        assert entry["link_type"] == "related"

    def test_get_link_returns_copy(self):
        svc = AgentTaskLinker()
        lid = svc.link("src1", "tgt1", "a1")
        entry = svc.get_link(lid)
        entry["link_type"] = "mutated"
        original = svc.get_link(lid)
        assert original["link_type"] == "related"


class TestMetadata:
    """Metadata deep-copy behaviour."""

    def test_metadata_stored(self):
        svc = AgentTaskLinker()
        lid = svc.link("src1", "tgt1", "a1", metadata={"key": "val"})
        entry = svc.get_link(lid)
        assert entry["metadata"] == {"key": "val"}

    def test_metadata_deep_copied(self):
        meta = {"nested": {"x": 1}}
        svc = AgentTaskLinker()
        lid = svc.link("src1", "tgt1", "a1", metadata=meta)
        meta["nested"]["x"] = 999
        entry = svc.get_link(lid)
        assert entry["metadata"]["nested"]["x"] == 1

    def test_metadata_default_empty(self):
        svc = AgentTaskLinker()
        lid = svc.link("src1", "tgt1", "a1")
        entry = svc.get_link(lid)
        assert entry["metadata"] == {}


class TestGetLinks:
    """Querying and filtering links."""

    def test_get_links_all(self):
        svc = AgentTaskLinker()
        svc.link("s1", "t1", "a1")
        svc.link("s2", "t2", "a2")
        results = svc.get_links()
        assert len(results) == 2

    def test_get_links_filter_by_agent(self):
        svc = AgentTaskLinker()
        svc.link("s1", "t1", "a1")
        svc.link("s2", "t2", "a2")
        svc.link("s3", "t3", "a1")
        results = svc.get_links(agent_id="a1")
        assert len(results) == 2
        assert all(r["agent_id"] == "a1" for r in results)

    def test_get_links_filter_by_type(self):
        svc = AgentTaskLinker()
        svc.link("s1", "t1", "a1", link_type="depends_on")
        svc.link("s2", "t2", "a1", link_type="blocks")
        svc.link("s3", "t3", "a1", link_type="depends_on")
        results = svc.get_links(link_type="depends_on")
        assert len(results) == 2
        assert all(r["link_type"] == "depends_on" for r in results)

    def test_get_links_filter_by_agent_and_type(self):
        svc = AgentTaskLinker()
        svc.link("s1", "t1", "a1", link_type="depends_on")
        svc.link("s2", "t2", "a2", link_type="depends_on")
        svc.link("s3", "t3", "a1", link_type="blocks")
        results = svc.get_links(agent_id="a1", link_type="depends_on")
        assert len(results) == 1
        assert results[0]["agent_id"] == "a1"
        assert results[0]["link_type"] == "depends_on"

    def test_get_links_newest_first(self):
        svc = AgentTaskLinker()
        lid1 = svc.link("s1", "t1", "a1")
        lid2 = svc.link("s2", "t2", "a1")
        results = svc.get_links()
        assert results[0]["link_id"] == lid2
        assert results[1]["link_id"] == lid1

    def test_get_links_respects_limit(self):
        svc = AgentTaskLinker()
        for i in range(10):
            svc.link(f"s{i}", f"t{i}", "a1")
        results = svc.get_links(limit=3)
        assert len(results) == 3

    def test_get_links_empty(self):
        svc = AgentTaskLinker()
        assert svc.get_links() == []


class TestGetLinkCount:
    """Counting links."""

    def test_count_all(self):
        svc = AgentTaskLinker()
        svc.link("s1", "t1", "a1")
        svc.link("s2", "t2", "a2")
        assert svc.get_link_count() == 2

    def test_count_by_agent(self):
        svc = AgentTaskLinker()
        svc.link("s1", "t1", "a1")
        svc.link("s2", "t2", "a2")
        svc.link("s3", "t3", "a1")
        assert svc.get_link_count(agent_id="a1") == 2
        assert svc.get_link_count(agent_id="a2") == 1

    def test_count_empty(self):
        svc = AgentTaskLinker()
        assert svc.get_link_count() == 0


class TestCallbacks:
    """Callback and on_change behaviour."""

    def test_on_change_fires(self):
        svc = AgentTaskLinker()
        fired = []
        svc.on_change = lambda action, data: fired.append((action, data))
        svc.link("s1", "t1", "a1")
        assert len(fired) == 1
        assert fired[0][0] == "linked"

    def test_on_change_exception_silenced(self):
        svc = AgentTaskLinker()
        svc.on_change = lambda action, data: (_ for _ in ()).throw(ValueError("boom"))
        lid = svc.link("s1", "t1", "a1")
        assert lid != ""

    def test_callback_fires(self):
        svc = AgentTaskLinker()
        fired = []
        svc._callbacks["cb1"] = lambda action, data: fired.append(action)
        svc.link("s1", "t1", "a1")
        assert fired == ["linked"]

    def test_callback_exception_silenced(self):
        svc = AgentTaskLinker()
        svc._callbacks["bad"] = lambda action, data: (_ for _ in ()).throw(RuntimeError("fail"))
        lid = svc.link("s1", "t1", "a1")
        assert lid != ""

    def test_remove_callback_existing(self):
        svc = AgentTaskLinker()
        svc._callbacks["cb1"] = lambda a, d: None
        assert svc.remove_callback("cb1") is True
        assert "cb1" not in svc._callbacks

    def test_remove_callback_missing(self):
        svc = AgentTaskLinker()
        assert svc.remove_callback("nope") is False

    def test_on_change_property(self):
        svc = AgentTaskLinker()
        assert svc.on_change is None
        fn = lambda a, d: None
        svc.on_change = fn
        assert svc.on_change is fn


class TestStats:
    """Statistics reporting."""

    def test_stats_empty(self):
        svc = AgentTaskLinker()
        stats = svc.get_stats()
        assert stats["total_links"] == 0
        assert stats["unique_agents"] == 0
        assert stats["unique_sources"] == 0
        assert stats["unique_targets"] == 0
        assert stats["link_types"] == {}

    def test_stats_populated(self):
        svc = AgentTaskLinker()
        svc.link("s1", "t1", "a1", link_type="depends_on")
        svc.link("s2", "t2", "a2", link_type="blocks")
        svc.link("s1", "t3", "a1", link_type="depends_on")
        stats = svc.get_stats()
        assert stats["total_links"] == 3
        assert stats["unique_agents"] == 2
        assert stats["unique_sources"] == 2
        assert stats["unique_targets"] == 3
        assert stats["link_types"]["depends_on"] == 2
        assert stats["link_types"]["blocks"] == 1


class TestReset:
    """Reset clears all state."""

    def test_reset_clears_entries(self):
        svc = AgentTaskLinker()
        svc.link("s1", "t1", "a1")
        svc.reset()
        assert svc.get_link_count() == 0

    def test_reset_clears_callbacks(self):
        svc = AgentTaskLinker()
        svc._callbacks["cb1"] = lambda a, d: None
        svc.on_change = lambda a, d: None
        svc.reset()
        assert len(svc._callbacks) == 0
        assert svc.on_change is None

    def test_reset_allows_reuse(self):
        svc = AgentTaskLinker()
        svc.link("s1", "t1", "a1")
        svc.reset()
        lid = svc.link("s2", "t2", "a2")
        assert lid.startswith("atln-")
        assert svc.get_link_count() == 1


class TestPruning:
    """Pruning when MAX_ENTRIES is exceeded."""

    def test_prune_removes_oldest_quarter(self):
        svc = AgentTaskLinker()
        svc.MAX_ENTRIES = 20
        for i in range(20):
            svc.link(f"s{i}", f"t{i}", "a1")
        assert svc.get_link_count() == 20
        # Adding one more triggers pruning
        svc.link("sX", "tX", "a1")
        assert svc.get_link_count() <= 17  # 20 - 5 + 1

    def test_prune_keeps_newest(self):
        svc = AgentTaskLinker()
        svc.MAX_ENTRIES = 8
        ids = []
        for i in range(8):
            ids.append(svc.link(f"s{i}", f"t{i}", "a1"))
        newest_id = ids[-1]
        svc.link("sN", "tN", "a1")
        assert svc.get_link(newest_id) is not None


class TestIdGeneration:
    """Link ID generation properties."""

    def test_ids_are_unique(self):
        svc = AgentTaskLinker()
        ids = set()
        for i in range(100):
            lid = svc.link(f"s{i}", f"t{i}", "a1")
            ids.add(lid)
        assert len(ids) == 100

    def test_id_has_correct_prefix(self):
        svc = AgentTaskLinker()
        lid = svc.link("s1", "t1", "a1")
        assert lid.startswith("atln-")
