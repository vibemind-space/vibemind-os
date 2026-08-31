"""
Tests for SocializationMetrics — proving the brain actually learns.

Covers all 6 metrics, time-series storage, consolidator integration,
and edge cases. Uses mocked MoltbookStore with controllable embeddings.
"""

import time
import threading
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.socialization_metrics import SocializationMetrics


# ── Helpers ──────────────────────────────────────────────────────────

def _make_entry(
    content="test content",
    embedding=None,
    source_agent="unknown",
    confidence=0.5,
    entry_id=None,
):
    """Create a mock MoltbookEntry."""
    entry = SimpleNamespace(
        id=entry_id or f"e_{id(content) % 10000:04d}",
        content=content,
        semantic_embedding=embedding,
        source_agent=source_agent,
        confidence=confidence,
        entry_type="knowledge",
        tags=[],
        created_at=time.time(),
        last_accessed=time.time(),
        accessed_count=0,
    )
    return entry


def _make_store(entries=None):
    """Create a mock MoltbookStore with given entries."""
    store = MagicMock()
    if entries is None:
        entries = []
    store._entries = {e.id: e for e in entries}
    return store


def _rand_embedding(dim=384, seed=None):
    """Generate a random unit-norm embedding."""
    rng = np.random.RandomState(seed)
    v = rng.randn(dim).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


def _shifted_embedding(base, shift_magnitude=0.1, seed=None):
    """Create an embedding shifted from base by a small amount."""
    rng = np.random.RandomState(seed)
    shift = rng.randn(len(base)).astype(np.float32)
    shift = shift / np.linalg.norm(shift) * shift_magnitude
    result = base + shift
    result /= np.linalg.norm(result)
    return result


# =====================================================================
# Test Semantic Drift
# =====================================================================

class TestSemanticDrift:
    """Metric 1: 1 - cos(prev_centroid, current_centroid)."""

    def test_zero_drift_identical_entries(self):
        """Same entries across cycles → zero drift."""
        emb = _rand_embedding(seed=1)
        entries = [_make_entry(f"entry_{i}", embedding=emb.copy(), entry_id=f"id_{i}") for i in range(5)]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        # First cycle: no previous centroid
        r1 = sm._compute_semantic_drift(time.time())
        assert r1 == 0.0  # no previous centroid

        # Second cycle: same entries → zero drift
        r2 = sm._compute_semantic_drift(time.time())
        assert r2 == pytest.approx(0.0, abs=1e-5)

    def test_positive_drift_different_entries(self):
        """Changing entries between cycles → positive drift."""
        emb1 = _rand_embedding(seed=10)
        entries = [_make_entry("a", embedding=emb1.copy(), entry_id=f"id_{i}") for i in range(5)]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        sm._compute_semantic_drift(time.time())

        # Now change embeddings significantly
        emb2 = _rand_embedding(seed=99)
        for e in store._entries.values():
            e.semantic_embedding = emb2.copy()

        drift = sm._compute_semantic_drift(time.time())
        assert drift > 0.01  # significant drift

    def test_no_embeddings(self):
        """Entries without embeddings → zero drift."""
        entries = [_make_entry(f"e_{i}", embedding=None, entry_id=f"id_{i}") for i in range(5)]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        assert sm._compute_semantic_drift(time.time()) == 0.0

    def test_single_entry(self):
        """Single entry → valid centroid, computable drift."""
        emb = _rand_embedding(seed=5)
        store = _make_store([_make_entry("one", embedding=emb, entry_id="single")])
        sm = SocializationMetrics(store)

        r1 = sm._compute_semantic_drift(time.time())
        assert r1 == 0.0  # first cycle

        r2 = sm._compute_semantic_drift(time.time())
        assert r2 == pytest.approx(0.0, abs=1e-5)  # same entry

    def test_drift_accumulates_in_history(self):
        """Drift values are stored in time-series."""
        emb = _rand_embedding(seed=1)
        entries = [_make_entry("x", embedding=emb.copy(), entry_id=f"id_{i}") for i in range(3)]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        for _ in range(5):
            sm._compute_semantic_drift(time.time())

        assert len(sm._drift_history) == 5


# =====================================================================
# Test Drift Consistency
# =====================================================================

class TestDriftConsistency:
    """Metric 2: cos(latest_drift, mean_drift)."""

    def test_consistent_direction(self):
        """Same drift direction → high consistency."""
        base = _rand_embedding(seed=1)
        store = _make_store([_make_entry("x", embedding=base.copy(), entry_id="id_0")])
        sm = SocializationMetrics(store)

        # Simulate consistent drift in same direction
        direction = np.zeros(384, dtype=np.float32)
        direction[0] = 1.0  # drift along axis 0

        for i in range(5):
            shifted = base + direction * (i + 1) * 0.01
            shifted /= np.linalg.norm(shifted)
            for e in store._entries.values():
                e.semantic_embedding = shifted.copy()

            sm._compute_semantic_drift(time.time())

        consistency = sm._compute_drift_consistency(time.time())
        assert consistency > 0.5  # high consistency

    def test_insufficient_history(self):
        """Less than 2 drift vectors → zero consistency."""
        store = _make_store([_make_entry("x", embedding=_rand_embedding(seed=1), entry_id="id_0")])
        sm = SocializationMetrics(store)

        sm._compute_semantic_drift(time.time())
        c = sm._compute_drift_consistency(time.time())
        assert c == 0.0

    def test_no_drift_vectors(self):
        """No drift vectors at all → zero."""
        store = _make_store([])
        sm = SocializationMetrics(store)
        assert sm._compute_drift_consistency(time.time()) == 0.0

    def test_consistency_stored_in_history(self):
        """Consistency values accumulate in time-series."""
        sm = SocializationMetrics(_make_store([]))
        for _ in range(3):
            sm._compute_drift_consistency(time.time())
        assert len(sm._consistency_history) == 3


# =====================================================================
# Test KNN Density
# =====================================================================

class TestKNNDensity:
    """Metric 3: average cosine distance to K nearest neighbors."""

    def test_clustered_entries_low_density(self):
        """Identical embeddings → near-zero distances (high similarity)."""
        emb = _rand_embedding(seed=1)
        entries = [
            _make_entry(f"e_{i}", embedding=emb.copy() + np.random.randn(384).astype(np.float32) * 0.001, entry_id=f"id_{i}")
            for i in range(20)
        ]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        density = sm._compute_knn_density(time.time())
        assert density < 0.1  # very close together

    def test_spread_entries_high_density(self):
        """Random embeddings → larger distances."""
        entries = [
            _make_entry(f"e_{i}", embedding=_rand_embedding(seed=i), entry_id=f"id_{i}")
            for i in range(20)
        ]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        density = sm._compute_knn_density(time.time())
        assert density > 0.1  # spread out

    def test_too_few_entries(self):
        """Fewer than K+1 entries → zero density."""
        entries = [
            _make_entry(f"e_{i}", embedding=_rand_embedding(seed=i), entry_id=f"id_{i}")
            for i in range(5)  # < K=10 + 1
        ]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        assert sm._compute_knn_density(time.time()) == 0.0

    def test_density_stored_in_history(self):
        """Density values accumulate."""
        entries = [
            _make_entry(f"e_{i}", embedding=_rand_embedding(seed=i), entry_id=f"id_{i}")
            for i in range(15)
        ]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        for _ in range(3):
            sm._compute_knn_density(time.time())
        assert len(sm._density_history) == 3


# =====================================================================
# Test Concept Turnover
# =====================================================================

class TestConceptTurnover:
    """Metric 4: birth/death of concepts."""

    def test_new_concepts_appear(self):
        """Adding entries with new words → positive birth rate."""
        entries_a = [_make_entry("neural network architecture design", entry_id="a")]
        store = _make_store(entries_a)
        sm = SocializationMetrics(store)

        # First cycle: establish baseline
        b1, d1 = sm._compute_concept_turnover(time.time())
        assert b1 == 0.0  # no previous to compare

        # Add new content
        store._entries["b"] = _make_entry(
            "quantum computing optimization algorithm",
            entry_id="b",
        )

        b2, d2 = sm._compute_concept_turnover(time.time())
        assert b2 > 0  # new concepts appeared

    def test_concepts_disappear(self):
        """Removing entries → positive death rate."""
        entries = [
            _make_entry("deep learning transformer model", entry_id="a"),
            _make_entry("reinforcement learning reward signal", entry_id="b"),
        ]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        sm._compute_concept_turnover(time.time())

        # Remove an entry
        del store._entries["b"]

        _, death = sm._compute_concept_turnover(time.time())
        assert death > 0  # concepts disappeared

    def test_stable_vocabulary(self):
        """Same entries → zero turnover."""
        entries = [_make_entry("stable content here testing", entry_id="a")]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        sm._compute_concept_turnover(time.time())
        birth, death = sm._compute_concept_turnover(time.time())
        assert birth == 0.0
        assert death == 0.0

    def test_empty_store(self):
        """No entries → zero turnover."""
        store = _make_store([])
        sm = SocializationMetrics(store)

        birth, death = sm._compute_concept_turnover(time.time())
        assert birth == 0.0
        assert death == 0.0

    def test_turnover_stored_in_history(self):
        """Birth and death rates accumulate."""
        store = _make_store([_make_entry("test content words", entry_id="a")])
        sm = SocializationMetrics(store)

        for _ in range(3):
            sm._compute_concept_turnover(time.time())

        assert len(sm._birth_rate_history) == 3
        assert len(sm._death_rate_history) == 3


# =====================================================================
# Test Interaction Influence Delta
# =====================================================================

class TestInfluenceDelta:
    """Metric 5: centroid shift from pre→post interaction."""

    def test_snapshot_and_shift(self):
        """Snapshot before, change entries, measure shift."""
        emb1 = _rand_embedding(seed=1)
        entries = [_make_entry(f"e_{i}", embedding=emb1.copy(), entry_id=f"id_{i}") for i in range(5)]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        # Snapshot pre-interaction
        sm.snapshot_pre_interaction()
        assert sm._pre_interaction_centroid is not None

        # Simulate interaction changing entries
        emb2 = _rand_embedding(seed=99)
        for e in store._entries.values():
            e.semantic_embedding = emb2.copy()

        delta = sm._compute_influence_delta(time.time())
        assert delta > 0.01  # measurable influence

    def test_no_snapshot(self):
        """No pre-interaction snapshot → zero delta."""
        store = _make_store([_make_entry("x", embedding=_rand_embedding(seed=1), entry_id="a")])
        sm = SocializationMetrics(store)

        delta = sm._compute_influence_delta(time.time())
        assert delta == 0.0

    def test_no_shift(self):
        """Snapshot taken but entries unchanged → near-zero delta."""
        emb = _rand_embedding(seed=1)
        entries = [_make_entry(f"e_{i}", embedding=emb.copy(), entry_id=f"id_{i}") for i in range(5)]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        sm.snapshot_pre_interaction()
        delta = sm._compute_influence_delta(time.time())
        assert delta == pytest.approx(0.0, abs=1e-4)

    def test_snapshot_cleared_after_read(self):
        """Snapshot is consumed (one-shot)."""
        emb = _rand_embedding(seed=1)
        store = _make_store([_make_entry("x", embedding=emb, entry_id="a")])
        sm = SocializationMetrics(store)

        sm.snapshot_pre_interaction()
        sm._compute_influence_delta(time.time())

        # Second read should give zero (snapshot consumed)
        delta2 = sm._compute_influence_delta(time.time())
        assert delta2 == 0.0


# =====================================================================
# Test Net Progress
# =====================================================================

class TestNetProgress:
    """Metric 6: delta_bottom25% - delta_top25% by confidence."""

    def _make_quartile_entries(self, n=20, seed=1):
        """Create entries with varying confidence and embeddings."""
        entries = []
        for i in range(n):
            conf = i / (n - 1)  # 0.0 to 1.0
            emb = _rand_embedding(seed=seed + i)
            entries.append(_make_entry(
                f"entry_{i}", embedding=emb, confidence=conf, entry_id=f"id_{i}"
            ))
        return entries

    def test_net_progress_computes(self):
        """Net progress should compute without error."""
        entries = self._make_quartile_entries(20, seed=1)
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        # First cycle: no previous centroids
        np1 = sm._compute_net_progress(time.time())
        assert np1 == 0.0  # no previous

        # Second cycle: should have a value
        np2 = sm._compute_net_progress(time.time())
        assert isinstance(np2, float)

    def test_too_few_entries(self):
        """Fewer than 8 entries → zero progress."""
        entries = [
            _make_entry(f"e_{i}", embedding=_rand_embedding(seed=i),
                       confidence=0.5, entry_id=f"id_{i}")
            for i in range(5)
        ]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        assert sm._compute_net_progress(time.time()) == 0.0

    def test_progress_stored_in_history(self):
        """Net progress accumulates in time-series."""
        entries = self._make_quartile_entries(20, seed=1)
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        for _ in range(3):
            sm._compute_net_progress(time.time())
        assert len(sm._net_progress_history) == 3

    def test_no_store(self):
        """No moltbook store → zero."""
        sm = SocializationMetrics(None)
        assert sm._compute_net_progress(time.time()) == 0.0


# =====================================================================
# Test compute_all()
# =====================================================================

class TestComputeAll:
    """Full compute_all() integration."""

    def test_all_metrics_computed(self):
        """compute_all() returns all 6 metrics."""
        entries = [
            _make_entry(f"content about topic {i} in the knowledge base",
                       embedding=_rand_embedding(seed=i),
                       confidence=i / 19,
                       entry_id=f"id_{i}")
            for i in range(20)
        ]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        report = sm.compute_all()
        assert 'semantic_drift' in report
        assert 'drift_consistency' in report
        assert 'knn_density' in report
        assert 'concept_birth_rate' in report
        assert 'concept_death_rate' in report
        assert 'influence_delta' in report
        assert 'net_progress' in report
        assert sm._total_measurements == 1

    def test_empty_store(self):
        """Empty store → all zeros, no crash."""
        store = _make_store([])
        sm = SocializationMetrics(store)

        report = sm.compute_all()
        assert report['semantic_drift'] == 0.0
        assert report['knn_density'] == 0.0
        assert sm._total_measurements == 1

    def test_partial_embeddings(self):
        """Mix of entries with/without embeddings → no crash."""
        entries = [
            _make_entry("with embedding", embedding=_rand_embedding(seed=1), entry_id="a"),
            _make_entry("no embedding", embedding=None, entry_id="b"),
            _make_entry("another with", embedding=_rand_embedding(seed=2), entry_id="c"),
        ]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        report = sm.compute_all()
        assert isinstance(report['semantic_drift'], float)

    def test_none_store(self):
        """None store → all zeros, no crash."""
        sm = SocializationMetrics(None)
        report = sm.compute_all()
        assert report['semantic_drift'] == 0.0
        assert report['knn_density'] == 0.0
        assert report['concept_birth_rate'] == 0.0
        assert report['net_progress'] == 0.0
        assert sm._total_measurements == 1

    def test_concurrent_entry_modification(self):
        """compute_all() survives concurrent store mutation."""
        entries = [
            _make_entry(f"e_{i}", embedding=_rand_embedding(seed=i), entry_id=f"id_{i}")
            for i in range(50)
        ]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        errors = []

        def mutate_store():
            for i in range(100):
                store._entries[f"new_{i}"] = _make_entry(
                    f"new_{i}", embedding=_rand_embedding(seed=100 + i), entry_id=f"new_{i}"
                )
                old_key = f"new_{max(0, i - 5)}"
                if old_key in store._entries:
                    del store._entries[old_key]

        t = threading.Thread(target=mutate_store)
        t.start()
        try:
            for _ in range(10):
                sm.compute_all()
        except Exception as e:
            errors.append(e)
        t.join()
        assert len(errors) == 0


# =====================================================================
# Test Time-Series
# =====================================================================

class TestTimeSeries:
    """Time-series storage and retrieval."""

    def test_history_accumulates(self):
        """Multiple compute_all() calls → growing history."""
        entries = [
            _make_entry(f"e_{i}", embedding=_rand_embedding(seed=i),
                       confidence=0.5, entry_id=f"id_{i}")
            for i in range(15)
        ]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        for _ in range(5):
            sm.compute_all()

        ts = sm.get_time_series()
        assert len(ts['semantic_drift']) == 5
        assert len(ts['knn_density']) == 5

    def test_max_history_cap(self):
        """History respects max_history limit."""
        store = _make_store([_make_entry("x", embedding=_rand_embedding(seed=1), entry_id="a")])
        sm = SocializationMetrics(store, max_history=3)

        for _ in range(10):
            sm.compute_all()

        ts = sm.get_time_series()
        assert len(ts['semantic_drift']) == 3  # capped at 3

    def test_single_metric_filter(self):
        """get_time_series(metric=...) returns only that metric."""
        store = _make_store([_make_entry("x", embedding=_rand_embedding(seed=1), entry_id="a")])
        sm = SocializationMetrics(store)
        sm.compute_all()

        ts = sm.get_time_series(metric='semantic_drift')
        assert 'semantic_drift' in ts
        assert 'knn_density' not in ts


# =====================================================================
# Test get_stats()
# =====================================================================

class TestGetStats:
    """Stats summary with trend indicators."""

    def test_returns_all_metrics(self):
        """get_stats() includes all metric names."""
        store = _make_store([_make_entry("x", embedding=_rand_embedding(seed=1), entry_id="a")])
        sm = SocializationMetrics(store)
        sm.compute_all()

        stats = sm.get_stats()
        assert 'semantic_drift' in stats
        assert 'knn_density' in stats
        assert 'net_progress' in stats
        assert 'trends' in stats
        assert 'total_measurements' in stats

    def test_initial_state(self):
        """Before any computation → all zeros."""
        sm = SocializationMetrics(_make_store([]))
        stats = sm.get_stats()
        assert stats['total_measurements'] == 0
        assert stats['semantic_drift'] == 0.0

    def test_trend_indicators(self):
        """Trends computed from history."""
        entries = [
            _make_entry(f"e_{i}", embedding=_rand_embedding(seed=i),
                       confidence=0.5, entry_id=f"id_{i}")
            for i in range(15)
        ]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        for _ in range(12):
            sm.compute_all()

        stats = sm.get_stats()
        trends = stats['trends']
        assert trends['semantic_drift'] in ('increasing', 'decreasing', 'stable')


# =====================================================================
# Test Consolidator Integration
# =====================================================================

class TestConsolidatorIntegration:
    """Integration with MemoryConsolidator Phase 3.5."""

    def test_phase_measure_called(self):
        """Consolidator's _phase_measure() delegates to SocializationMetrics."""
        from core.memory_consolidation import MemoryConsolidator

        store = MagicMock()
        store._entries = {}
        consolidator = MemoryConsolidator(moltbook_store=store)

        sm = SocializationMetrics(_make_store([]))
        consolidator.set_socialization_metrics(sm)

        result = consolidator._phase_measure()
        assert isinstance(result, dict)

    def test_graceful_without_metrics(self):
        """No SocializationMetrics → empty dict, no crash."""
        from core.memory_consolidation import MemoryConsolidator

        store = MagicMock()
        store._entries = {}
        consolidator = MemoryConsolidator(moltbook_store=store)

        result = consolidator._phase_measure()
        assert result == {}

    def test_run_cycle_includes_measured(self):
        """run_cycle() report includes 'measured' key."""
        from core.memory_consolidation import MemoryConsolidator

        store = MagicMock()
        store._entries = {}
        store.save_to_disk = MagicMock()
        consolidator = MemoryConsolidator(moltbook_store=store)

        sm = SocializationMetrics(_make_store([]))
        consolidator.set_socialization_metrics(sm)

        report = consolidator.run_cycle()
        assert 'measured' in report


# =====================================================================
# Test Concept Extraction Helper
# =====================================================================

class TestConceptExtraction:
    """Helper method for extracting concepts from content."""

    def test_extracts_meaningful_words(self):
        """Stopwords filtered, short words filtered."""
        entries = [_make_entry(
            "The neural network architecture uses transformer layers for processing",
            entry_id="a"
        )]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        concepts = sm._extract_concepts()
        assert 'neural' in concepts
        assert 'the' not in concepts  # stopword
        assert len(concepts) > 0

    def test_bigrams_extracted(self):
        """Adjacent non-stopword pairs form bigrams."""
        entries = [_make_entry(
            "deep learning neural network reinforcement learning",
            entry_id="a"
        )]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        concepts = sm._extract_concepts()
        assert 'deep_learning' in concepts or 'neural_network' in concepts

    def test_empty_content(self):
        """Empty content → empty concepts."""
        entries = [_make_entry("", entry_id="a")]
        store = _make_store(entries)
        sm = SocializationMetrics(store)

        concepts = sm._extract_concepts()
        assert len(concepts) == 0


# =====================================================================
# Test Cosine Distance Helper
# =====================================================================

class TestCosineDistance:
    """Static cosine distance helper."""

    def test_identical_vectors(self):
        """Same vector → zero distance."""
        v = _rand_embedding(seed=1)
        assert SocializationMetrics._cosine_distance(v, v) == pytest.approx(0.0, abs=1e-6)

    def test_orthogonal_vectors(self):
        """Orthogonal → distance 1.0."""
        a = np.zeros(384, dtype=np.float32)
        a[0] = 1.0
        b = np.zeros(384, dtype=np.float32)
        b[1] = 1.0
        assert SocializationMetrics._cosine_distance(a, b) == pytest.approx(1.0, abs=1e-6)

    def test_zero_vector(self):
        """Zero vector → zero distance (safe)."""
        v = _rand_embedding(seed=1)
        z = np.zeros(384, dtype=np.float32)
        assert SocializationMetrics._cosine_distance(v, z) == 0.0
