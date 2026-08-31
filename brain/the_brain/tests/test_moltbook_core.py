"""
Tests for Moltbook Core — MoltbookEntry, MoltbookStore, SemanticIndex, MoltbookGraph.

Covers: Points [1]-[5] of the 100-point Moltbook masterplan.
"""

import math
import os
import tempfile
import time

import numpy as np
import pytest

from core.moltbook import (
    MoltbookEntry, EntryType, LinkType,
    MoltbookStore, SemanticIndex, MoltbookGraph,
    MoltbookConfig,
)


# ═══════════════════════════════════════════════════════════════════
# MoltbookEntry Tests
# ═══════════════════════════════════════════════════════════════════

class TestMoltbookEntry:
    """Test MoltbookEntry dataclass and its methods."""

    def test_create_default_entry(self):
        entry = MoltbookEntry()
        assert entry.id is not None
        assert len(entry.id) == 12
        assert entry.content == ""
        assert entry.source_agent == "unknown"
        assert entry.entry_type == "knowledge"
        assert entry.confidence == 0.5
        assert entry.emotional_valence == 0.0
        assert entry.accessed_count == 0

    def test_create_entry_with_content(self):
        entry = MoltbookEntry(
            content="Python uses garbage collection",
            source_agent="research_agent",
            entry_type="knowledge",
            tags=["python", "memory"],
            confidence=0.9,
            emotional_valence=0.3,
        )
        assert entry.content == "Python uses garbage collection"
        assert entry.source_agent == "research_agent"
        assert entry.tags == ["python", "memory"]
        assert entry.confidence == 0.9

    def test_access_increments_count(self):
        entry = MoltbookEntry(content="test")
        assert entry.accessed_count == 0
        entry.access()
        assert entry.accessed_count == 1
        entry.access()
        assert entry.accessed_count == 2

    def test_access_boosts_relevance(self):
        entry = MoltbookEntry(content="test", relevance_score=0.5)
        initial = entry.relevance_score
        entry.access()
        assert entry.relevance_score > initial

    def test_access_relevance_caps_at_1(self):
        entry = MoltbookEntry(content="test", relevance_score=0.99)
        for _ in range(100):
            entry.access()
        assert entry.relevance_score <= 1.0

    def test_compute_activation_decays_over_time(self):
        entry = MoltbookEntry(content="test", relevance_score=0.8)
        t0 = time.time()
        act_now = entry.compute_activation(t0)
        act_later = entry.compute_activation(t0 + 10000)
        assert act_later < act_now

    def test_compute_activation_frequency_boost(self):
        entry1 = MoltbookEntry(content="test", relevance_score=0.5)
        entry2 = MoltbookEntry(content="test", relevance_score=0.5)
        entry2.accessed_count = 10
        t = time.time()
        assert entry2.compute_activation(t) > entry1.compute_activation(t)

    def test_emotional_entries_decay_slower(self):
        neutral = MoltbookEntry(content="test", emotional_valence=0.0)
        emotional = MoltbookEntry(content="test", emotional_valence=0.9)
        t0 = time.time()
        neutral.last_accessed = t0 - 5000
        emotional.last_accessed = t0 - 5000
        # Emotional entry should have higher activation after same time
        assert emotional.compute_activation(t0) > neutral.compute_activation(t0)

    def test_to_dict_and_from_dict(self):
        entry = MoltbookEntry(
            content="Test content",
            source_agent="agent_1",
            tags=["a", "b"],
            confidence=0.7,
            semantic_embedding=np.array([1.0, 2.0, 3.0], dtype=np.float32),
        )
        d = entry.to_dict()
        assert isinstance(d, dict)
        assert d['content'] == "Test content"
        assert d['semantic_embedding'] == [1.0, 2.0, 3.0]

        restored = MoltbookEntry.from_dict(d)
        assert restored.content == entry.content
        assert restored.source_agent == entry.source_agent
        assert restored.tags == entry.tags
        assert np.allclose(restored.semantic_embedding, entry.semantic_embedding)

    def test_to_dict_without_embedding(self):
        entry = MoltbookEntry(content="No embedding")
        d = entry.to_dict()
        assert 'semantic_embedding' not in d

    def test_content_hash(self):
        e1 = MoltbookEntry(content="hello world")
        e2 = MoltbookEntry(content="hello world")
        e3 = MoltbookEntry(content="different")
        assert e1.content_hash() == e2.content_hash()
        assert e1.content_hash() != e3.content_hash()

    def test_linked_entries(self):
        entry = MoltbookEntry(
            content="test",
            linked_entries={"abc123": "supports", "def456": "contradicts"}
        )
        assert len(entry.linked_entries) == 2
        assert entry.linked_entries["abc123"] == "supports"


# ═══════════════════════════════════════════════════════════════════
# MoltbookConfig Tests
# ═══════════════════════════════════════════════════════════════════

class TestMoltbookConfig:
    """Test MoltbookConfig dataclass."""

    def test_default_config(self):
        config = MoltbookConfig()
        assert config.max_entries == 50000
        assert config.embedding_dim == 384
        assert config.similarity_threshold == 0.3
        assert config.workspace_capacity == 7
        assert config.decay_rate == 0.001

    def test_from_yaml(self):
        yaml = {
            'moltbook': {
                'max_entries': 10000,
                'embedding_dim': 128,
                'decay_rate': 0.01,
            }
        }
        config = MoltbookConfig.from_yaml(yaml)
        assert config.max_entries == 10000
        assert config.embedding_dim == 128
        assert config.decay_rate == 0.01
        # Defaults for unspecified
        assert config.similarity_threshold == 0.3

    def test_from_yaml_empty(self):
        config = MoltbookConfig.from_yaml({})
        assert config.max_entries == 50000


# ═══════════════════════════════════════════════════════════════════
# SemanticIndex Tests
# ═══════════════════════════════════════════════════════════════════

class TestSemanticIndex:
    """Test SemanticIndex vector-based search."""

    def test_init(self):
        idx = SemanticIndex()
        assert idx.size == 0
        assert idx._dim == 384

    def test_init_custom_dim(self):
        idx = SemanticIndex(embedding_dim=128)
        assert idx._dim == 128

    def test_embed_produces_vector(self):
        idx = SemanticIndex()
        vec = idx.embed("hello world")
        assert vec.shape == (384,)
        assert vec.dtype == np.float32

    def test_embed_is_normalized(self):
        idx = SemanticIndex()
        vec = idx.embed("this is a test sentence")
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-5

    def test_embed_deterministic(self):
        idx = SemanticIndex()
        v1 = idx.embed("hello world")
        v2 = idx.embed("hello world")
        assert np.allclose(v1, v2)

    def test_similar_texts_have_higher_similarity(self):
        idx = SemanticIndex()
        v1 = idx.embed("python programming language")
        v2 = idx.embed("python coding language")
        v3 = idx.embed("cooking recipe for pasta")
        sim_close = float(v1 @ v2)
        sim_far = float(v1 @ v3)
        assert sim_close > sim_far

    def test_add_and_search(self):
        idx = SemanticIndex()
        v1 = idx.embed("machine learning algorithms")
        v2 = idx.embed("deep learning neural networks")
        v3 = idx.embed("cooking pasta recipe")

        idx.add("e1", v1)
        idx.add("e2", v2)
        idx.add("e3", v3)
        assert idx.size == 3

        results = idx.search(idx.embed("machine learning"), top_k=2)
        assert len(results) >= 1
        # e1 should be closest to "machine learning"
        assert results[0][0] == "e1"

    def test_search_empty_index(self):
        idx = SemanticIndex()
        results = idx.search(np.zeros(384))
        assert results == []

    def test_remove(self):
        idx = SemanticIndex()
        idx.add("e1", idx.embed("hello"))
        idx.add("e2", idx.embed("world"))
        assert idx.size == 2
        idx.remove("e1")
        assert idx.size == 1

    def test_remove_nonexistent(self):
        idx = SemanticIndex()
        idx.remove("nonexistent")  # Should not raise

    def test_batch_index(self):
        idx = SemanticIndex()
        entries = [
            ("e1", idx.embed("hello")),
            ("e2", idx.embed("world")),
            ("e3", idx.embed("test")),
        ]
        count = idx.batch_index(entries)
        assert count == 3
        assert idx.size == 3

    def test_reindex(self):
        idx = SemanticIndex()
        idx.add("old", idx.embed("old entry"))
        assert idx.size == 1

        idx.reindex({
            "new1": idx.embed("new entry 1"),
            "new2": idx.embed("new entry 2"),
        })
        assert idx.size == 2

    def test_search_with_threshold(self):
        idx = SemanticIndex()
        idx.add("e1", idx.embed("machine learning"))
        idx.add("e2", idx.embed("cooking pasta"))

        # High threshold should filter out dissimilar
        results = idx.search(idx.embed("machine learning"), top_k=10, threshold=0.5)
        ids = [r[0] for r in results]
        assert "e1" in ids

    def test_get_stats(self):
        idx = SemanticIndex()
        idx.add("e1", idx.embed("test"))
        stats = idx.get_stats()
        assert stats['size'] == 1
        assert stats['dim'] == 384
        assert stats['memory_mb'] > 0

    def test_from_yaml(self):
        idx = SemanticIndex.from_yaml({'moltbook': {'embedding_dim': 128}})
        assert idx._dim == 128

    def test_update_existing_entry(self):
        idx = SemanticIndex()
        v1 = idx.embed("version 1")
        v2 = idx.embed("version 2")
        idx.add("e1", v1)
        idx.add("e1", v2)  # Update
        assert idx.size == 1
        # Search should return updated version
        results = idx.search(v2, top_k=1)
        assert results[0][0] == "e1"
        assert results[0][1] > 0.99  # Almost perfect match


# ═══════════════════════════════════════════════════════════════════
# MoltbookStore Tests
# ═══════════════════════════════════════════════════════════════════

class TestMoltbookStore:
    """Test MoltbookStore persistent knowledge storage."""

    def test_init(self):
        store = MoltbookStore()
        assert store.size == 0
        assert store._max_entries == 50000

    def test_init_with_config(self):
        store = MoltbookStore(config={'max_entries': 100})
        assert store._max_entries == 100

    def test_add_entry(self):
        store = MoltbookStore()
        entry = store.add_entry(
            content="Python is a programming language",
            source_agent="test_agent",
            tags=["python", "programming"],
            confidence=0.9,
        )
        assert store.size == 1
        assert entry.content == "Python is a programming language"
        assert entry.source_agent == "test_agent"
        assert entry.semantic_embedding is not None

    def test_get_entry(self):
        store = MoltbookStore()
        added = store.add_entry(content="Test entry")
        retrieved = store.get_entry(added.id)
        assert retrieved is not None
        assert retrieved.content == "Test entry"
        assert retrieved.accessed_count == 1  # get_entry records access

    def test_get_entry_nonexistent(self):
        store = MoltbookStore()
        assert store.get_entry("nonexistent") is None

    def test_query_semantic(self):
        store = MoltbookStore()
        store.add_entry(content="machine learning algorithms", tags=["ml"])
        store.add_entry(content="deep learning neural networks", tags=["dl"])
        store.add_entry(content="cooking pasta italian recipe", tags=["food"])

        results = store.query_semantic("machine learning", top_k=2)
        assert len(results) >= 1
        assert results[0].content == "machine learning algorithms"

    def test_query_by_tag(self):
        store = MoltbookStore()
        store.add_entry(content="Python basics", tags=["python", "basics"])
        store.add_entry(content="Python advanced", tags=["python", "advanced"])
        store.add_entry(content="Java basics", tags=["java", "basics"])

        results = store.query_by_tag(["python"])
        assert len(results) == 2

    def test_query_by_tag_match_all(self):
        store = MoltbookStore()
        store.add_entry(content="Python basics", tags=["python", "basics"])
        store.add_entry(content="Python advanced", tags=["python", "advanced"])
        store.add_entry(content="Java basics", tags=["java", "basics"])

        results = store.query_by_tag(["python", "basics"], match_all=True)
        assert len(results) == 1
        assert results[0].content == "Python basics"

    def test_link_entries(self):
        store = MoltbookStore()
        e1 = store.add_entry(content="Entry 1")
        e2 = store.add_entry(content="Entry 2")
        success = store.link_entries(e1.id, e2.id, link_type="supports")
        assert success
        assert e1.linked_entries[e2.id] == "supports"

    def test_get_linked(self):
        store = MoltbookStore()
        e1 = store.add_entry(content="Root entry")
        e2 = store.add_entry(content="Linked entry")
        store.link_entries(e1.id, e2.id, "supports")

        linked = store.get_linked(e1.id)
        assert len(linked) == 1
        assert linked[0].id == e2.id

    def test_get_active_entries(self):
        store = MoltbookStore()
        for i in range(10):
            store.add_entry(content=f"Entry {i}", confidence=0.1 * i)

        active = store.get_active_entries(top_k=3)
        assert len(active) == 3

    def test_decay_old(self):
        store = MoltbookStore()
        entry = store.add_entry(content="Old entry")
        # Set last_accessed to long ago
        entry.last_accessed = time.time() - 1000000
        entry.relevance_score = 0.001
        entry.decay_rate = 1.0  # Very fast decay

        dead_count = store.decay_old()
        assert dead_count >= 1

    def test_consolidate(self):
        store = MoltbookStore()
        # Add an entry that should be consolidated (very old, low relevance)
        entry = store.add_entry(content="Dead entry")
        entry.last_accessed = time.time() - 1000000
        entry.relevance_score = 0.0001
        entry.decay_rate = 10.0

        result = store.consolidate()
        assert result['removed'] >= 1

    def test_eviction_on_max_entries(self):
        store = MoltbookStore(config={'max_entries': 5})
        for i in range(10):
            store.add_entry(content=f"Entry {i}")
        assert store.size <= 5

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "store.jsonl")
            store1 = MoltbookStore()
            store1.add_entry(content="Entry 1", tags=["a"])
            store1.add_entry(content="Entry 2", tags=["b"])
            store1.save_to_disk(path)

            store2 = MoltbookStore()
            count = store2.load_from_disk(path)
            assert count == 2
            assert store2.size == 2

    def test_load_nonexistent_path(self):
        store = MoltbookStore()
        count = store.load_from_disk("/nonexistent/path.jsonl")
        assert count == 0

    def test_get_stats(self):
        store = MoltbookStore()
        store.add_entry(content="Test", tags=["x"])
        stats = store.get_stats()
        assert stats['size'] == 1
        assert stats['total_added'] == 1
        assert stats['tag_count'] == 1
        assert 'semantic_index' in stats

    def test_from_yaml(self):
        store = MoltbookStore.from_yaml({'moltbook': {'max_entries': 100}})
        assert store._max_entries == 100

    def test_multiple_queries_track_count(self):
        store = MoltbookStore()
        store.add_entry(content="Test entry")
        store.query_semantic("test")
        store.query_semantic("test")
        assert store._total_queries == 2


# ═══════════════════════════════════════════════════════════════════
# MoltbookGraph Tests
# ═══════════════════════════════════════════════════════════════════

class TestMoltbookGraph:
    """Test MoltbookGraph knowledge linkage and spreading activation."""

    def test_init(self):
        graph = MoltbookGraph()
        assert graph.node_count == 0
        assert graph.edge_count == 0

    def test_link(self):
        graph = MoltbookGraph()
        graph.link("a", "b", "supports")
        assert graph.edge_count == 1
        assert graph.node_count == 2

    def test_unlink(self):
        graph = MoltbookGraph()
        graph.link("a", "b", "supports")
        assert graph.unlink("a", "b")
        assert graph.edge_count == 0

    def test_unlink_nonexistent(self):
        graph = MoltbookGraph()
        assert not graph.unlink("a", "b")

    def test_get_neighborhood(self):
        graph = MoltbookGraph()
        graph.link("a", "b", "supports", weight=1.0)
        graph.link("a", "c", "relates_to", weight=0.5)
        graph.link("b", "d", "extends", weight=1.0)

        # Depth 1: only direct neighbors of a
        hood = graph.get_neighborhood("a", depth=1)
        assert "b" in hood
        assert "c" in hood
        assert "d" not in hood  # d is 2 hops away

        # Depth 2: should reach d
        hood2 = graph.get_neighborhood("a", depth=2)
        assert "d" in hood2

    def test_get_neighborhood_with_link_type_filter(self):
        graph = MoltbookGraph()
        graph.link("a", "b", "supports")
        graph.link("a", "c", "contradicts")

        hood = graph.get_neighborhood("a", depth=1, link_type="supports")
        assert "b" in hood
        assert "c" not in hood

    def test_spreading_activation(self):
        graph = MoltbookGraph()
        graph.link("a", "b", "supports", weight=1.0)
        graph.link("b", "c", "extends", weight=0.8)
        graph.link("a", "d", "relates_to", weight=0.3)

        result = graph.spreading_activation(["a"], depth=2)
        ids = [r[0] for r in result]
        assert "b" in ids
        assert "d" in ids
        # b should have higher activation than d (weight 1.0 vs 0.3)
        b_act = dict(result).get("b", 0)
        d_act = dict(result).get("d", 0)
        assert b_act > d_act

    def test_spreading_activation_single_seed_string(self):
        graph = MoltbookGraph()
        graph.link("a", "b", "supports")
        result = graph.spreading_activation("a", depth=1)
        assert len(result) >= 1

    def test_find_clusters(self):
        graph = MoltbookGraph()
        # Cluster 1: a-b-c
        graph.link("a", "b")
        graph.link("b", "c")
        # Cluster 2: x-y-z
        graph.link("x", "y")
        graph.link("y", "z")
        # Isolated: i-j (only 2, below min_cluster_size=3)
        graph.link("i", "j")

        clusters = graph.find_clusters(min_cluster_size=3)
        assert len(clusters) == 2

    def test_get_contradictions(self):
        graph = MoltbookGraph()
        graph.link("a", "b", "supports")
        graph.link("a", "c", "contradicts")
        graph.link("d", "e", "contradicts")

        contradictions = graph.get_contradictions()
        assert len(contradictions) == 2

    def test_remove_node(self):
        graph = MoltbookGraph()
        graph.link("a", "b")
        graph.link("a", "c")
        graph.link("d", "a")

        removed = graph.remove_node("a")
        assert removed == 3  # 2 outgoing + 1 incoming
        assert graph.edge_count == 0

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "graph.json")
            g1 = MoltbookGraph()
            g1.link("a", "b", "supports", weight=0.8)
            g1.link("b", "c", "extends", weight=0.5)
            g1.save(path)

            g2 = MoltbookGraph()
            count = g2.load(path)
            assert count == 2
            assert g2.edge_count == 2

    def test_get_stats(self):
        graph = MoltbookGraph()
        graph.link("a", "b", "supports")
        graph.link("b", "c", "extends")
        graph.link("a", "c", "contradicts")

        stats = graph.get_stats()
        assert stats['node_count'] == 3
        assert stats['edge_count'] == 3
        assert stats['contradictions'] == 1

    def test_from_yaml(self):
        graph = MoltbookGraph.from_yaml({'moltbook': {}})
        assert graph.node_count == 0

    def test_spreading_activation_threshold(self):
        """Entries with low activation should be filtered out."""
        graph = MoltbookGraph()
        graph.link("a", "b", weight=0.01)  # Very weak link

        result = graph.spreading_activation(["a"], depth=1, activation_threshold=0.1)
        # b should be filtered out because 0.01 * 0.5 < 0.1
        ids = [r[0] for r in result]
        assert "b" not in ids


# ═══════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════

class TestMoltbookIntegration:
    """Integration tests across Moltbook components."""

    def test_store_with_graph_linking(self):
        """Test that store entries can be linked via graph."""
        store = MoltbookStore()
        graph = MoltbookGraph()

        e1 = store.add_entry(content="Python is interpreted", tags=["python"])
        e2 = store.add_entry(content="Python uses garbage collection", tags=["python"])
        e3 = store.add_entry(content="Java is compiled", tags=["java"])

        graph.link(e1.id, e2.id, "supports")
        graph.link(e1.id, e3.id, "contradicts")

        # Spreading activation from e1 should reach e2 and e3
        activated = graph.spreading_activation([e1.id], depth=1)
        activated_ids = [a[0] for a in activated]
        assert e2.id in activated_ids
        assert e3.id in activated_ids

    def test_semantic_search_and_graph_enrichment(self):
        """Test combining semantic search with graph-based enrichment."""
        store = MoltbookStore()
        graph = MoltbookGraph()

        e1 = store.add_entry(content="Neural networks learn patterns")
        e2 = store.add_entry(content="Backpropagation trains neural networks")
        e3 = store.add_entry(content="Cooking Italian pasta")

        graph.link(e1.id, e2.id, "relates_to")

        # Semantic search for "neural networks"
        results = store.query_semantic("neural networks", top_k=2)
        assert len(results) >= 1

        # Enrich with graph — spread from top result
        activated = graph.spreading_activation([results[0].id], depth=1)
        all_relevant_ids = [r.id for r in results] + [a[0] for a in activated]
        # Both e1 and e2 should be included
        assert e1.id in all_relevant_ids or e2.id in all_relevant_ids

    def test_full_lifecycle_add_query_decay_consolidate(self):
        """Test the full lifecycle: add → query → decay → consolidate."""
        store = MoltbookStore()

        # Add entries
        e1 = store.add_entry(content="Important knowledge", confidence=0.9)
        e2 = store.add_entry(content="Trivial info", confidence=0.1)

        # Query
        results = store.query_semantic("important knowledge")
        assert len(results) >= 1

        # Make e2 very old and dead
        e2.last_accessed = time.time() - 1000000
        e2.relevance_score = 0.0001
        e2.decay_rate = 10.0

        # Consolidate should remove dead entry
        result = store.consolidate()
        assert result['removed'] >= 1

    def test_entry_type_enum(self):
        """Test EntryType enum values."""
        assert EntryType.POST.value == "post"
        assert EntryType.THOUGHT.value == "thought"
        assert EntryType.KNOWLEDGE.value == "knowledge"
        assert EntryType.REFLECTION.value == "reflection"

    def test_link_type_enum(self):
        """Test LinkType enum values."""
        assert LinkType.SUPPORTS.value == "supports"
        assert LinkType.CONTRADICTS.value == "contradicts"
        assert LinkType.REFINES.value == "refines"
