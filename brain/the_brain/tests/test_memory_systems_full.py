"""
Comprehensive tests for Memory Systems (core/memory_systems.py)

Tests cover:
- WorkingMemoryEntry: to_dict with ndarray and list brain_gates
- EpisodicMemoryEntry: to_dict, rich context fields
- WorkingMemory: capacity limits, get_recent, retrieve_similar, get_success_rate,
  get_decision_patterns, clear, cosine similarity, text similarity
- EpisodicMemory: add, retrieve_similar, importance filtering, eviction,
  get_important_memories, get_by_outcome, get_by_decision,
  compute_decision_success_rate, persistence (save/load), clear
- MemoryManager: remember_task, consolidate_to_episodic, get_context,
  empty operations, large-scale stress, thread safety
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import numpy as np
import json
import tempfile
import shutil
import threading
from datetime import datetime, timedelta
from pathlib import Path

from core.memory_systems import (
    WorkingMemoryEntry,
    EpisodicMemoryEntry,
    WorkingMemory,
    EpisodicMemory,
    MemoryManager,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gates(n=10, seed=None):
    """Return a valid brain_gates ndarray (sums to 1)."""
    rng = np.random.RandomState(seed)
    return rng.dirichlet(np.ones(n))


def _make_working_entry(
    task="Deploy Docker container",
    task_type="docker",
    decision="execute",
    confidence=0.85,
    outcome="success",
    brain_gates=None,
    timestamp=None,
):
    if brain_gates is None:
        brain_gates = _make_gates(seed=42)
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    return WorkingMemoryEntry(
        task=task,
        task_type=task_type,
        decision=decision,
        confidence=confidence,
        outcome=outcome,
        brain_gates=brain_gates,
        timestamp=timestamp,
    )


def _make_episodic_entry(
    task="Fix authentication bug",
    task_type="bug",
    decision="suggest",
    confidence=0.75,
    outcome="success",
    brain_gates=None,
    importance=0.8,
    emotional_valence="positive",
    prediction_error=0.1,
    timestamp=None,
):
    if brain_gates is None:
        brain_gates = _make_gates(seed=99)
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    return EpisodicMemoryEntry(
        task=task,
        task_type=task_type,
        decision=decision,
        confidence=confidence,
        outcome=outcome,
        brain_gates=brain_gates,
        layer1_features={"complexity": 0.6, "urgency": 0.3},
        layer2_sequence=["analyze", "plan", "execute"],
        reasoning_chain=["Step 1", "Step 2"],
        timestamp=timestamp,
        importance=importance,
        emotional_valence=emotional_valence,
        retrieval_count=0,
        prediction_error=prediction_error,
        execution_time_ms=120.5,
        user_rating=0.9,
    )


# ===========================================================================
# 1. WorkingMemoryEntry Tests
# ===========================================================================

class TestWorkingMemoryEntry:
    """Tests for the WorkingMemoryEntry dataclass."""

    def test_to_dict_basic(self):
        """to_dict returns all expected keys."""
        entry = _make_working_entry()
        d = entry.to_dict()
        assert isinstance(d, dict)
        for key in ("task", "task_type", "decision", "confidence",
                     "outcome", "brain_gates", "timestamp"):
            assert key in d

    def test_to_dict_with_ndarray_brain_gates(self):
        """brain_gates stored as ndarray serialize to a list."""
        gates = np.array([0.1, 0.2, 0.3, 0.4])
        entry = _make_working_entry(brain_gates=gates)
        d = entry.to_dict()
        assert isinstance(d["brain_gates"], list)
        np.testing.assert_allclose(d["brain_gates"], [0.1, 0.2, 0.3, 0.4])

    def test_to_dict_with_list_brain_gates(self):
        """brain_gates stored as plain list serialize correctly."""
        gates = [0.25, 0.25, 0.25, 0.25]
        entry = _make_working_entry(brain_gates=gates)
        d = entry.to_dict()
        assert isinstance(d["brain_gates"], list)
        assert d["brain_gates"] == [0.25, 0.25, 0.25, 0.25]

    def test_to_dict_json_serializable(self):
        """to_dict output can be round-tripped through JSON."""
        entry = _make_working_entry()
        d = entry.to_dict()
        serialized = json.dumps(d)
        restored = json.loads(serialized)
        assert restored["task"] == entry.task
        np.testing.assert_allclose(restored["brain_gates"],
                                    entry.brain_gates.tolist() if hasattr(entry.brain_gates, 'tolist') else entry.brain_gates)


# ===========================================================================
# 2. EpisodicMemoryEntry Tests
# ===========================================================================

class TestEpisodicMemoryEntry:
    """Tests for the EpisodicMemoryEntry dataclass."""

    def test_to_dict_basic(self):
        entry = _make_episodic_entry()
        d = entry.to_dict()
        assert isinstance(d, dict)
        for key in ("task", "task_type", "decision", "confidence", "outcome",
                     "brain_gates", "layer1_features", "layer2_sequence",
                     "reasoning_chain", "timestamp", "importance",
                     "emotional_valence", "retrieval_count",
                     "prediction_error", "execution_time_ms", "user_rating"):
            assert key in d

    def test_to_dict_with_ndarray_brain_gates(self):
        gates = np.array([0.5, 0.3, 0.2])
        entry = _make_episodic_entry(brain_gates=gates)
        d = entry.to_dict()
        assert isinstance(d["brain_gates"], list)
        np.testing.assert_allclose(d["brain_gates"], [0.5, 0.3, 0.2])

    def test_to_dict_with_list_brain_gates(self):
        gates = [0.5, 0.3, 0.2]
        entry = _make_episodic_entry(brain_gates=gates)
        d = entry.to_dict()
        assert isinstance(d["brain_gates"], list)

    def test_to_dict_json_serializable(self):
        entry = _make_episodic_entry()
        d = entry.to_dict()
        serialized = json.dumps(d)
        restored = json.loads(serialized)
        assert restored["task"] == entry.task


# ===========================================================================
# 3. WorkingMemory Tests
# ===========================================================================

class TestWorkingMemory:
    """Tests for the WorkingMemory class."""

    def test_default_initialization(self):
        wm = WorkingMemory()
        assert wm.capacity == 10
        assert len(wm) == 0

    def test_custom_capacity(self):
        wm = WorkingMemory(capacity=5)
        assert wm.capacity == 5

    def test_add_single_entry(self):
        wm = WorkingMemory()
        wm.add(_make_working_entry())
        assert len(wm) == 1

    def test_capacity_limit_evicts_oldest(self):
        """Adding beyond capacity evicts oldest entry."""
        wm = WorkingMemory(capacity=3)
        for i in range(5):
            wm.add(_make_working_entry(task=f"Task {i}"))
        assert len(wm) == 3
        recent = wm.get_recent(3)
        tasks = [e.task for e in recent]
        # Most recent first
        assert tasks == ["Task 4", "Task 3", "Task 2"]

    def test_get_recent_returns_correct_count(self):
        wm = WorkingMemory(capacity=10)
        for i in range(7):
            wm.add(_make_working_entry(task=f"Task {i}"))
        recent = wm.get_recent(3)
        assert len(recent) == 3
        # Most recent first
        assert recent[0].task == "Task 6"

    def test_get_recent_fewer_than_n(self):
        """When fewer entries than n, return all available."""
        wm = WorkingMemory()
        wm.add(_make_working_entry(task="Only"))
        recent = wm.get_recent(5)
        assert len(recent) == 1
        assert recent[0].task == "Only"

    def test_get_recent_empty(self):
        wm = WorkingMemory()
        assert wm.get_recent(5) == []

    def test_retrieve_similar_empty_buffer(self):
        wm = WorkingMemory()
        result = wm.retrieve_similar("test", _make_gates(), top_k=3)
        assert result == []

    def test_retrieve_similar_returns_tuples(self):
        wm = WorkingMemory()
        gates = _make_gates(seed=10)
        wm.add(_make_working_entry(task="Deploy Docker", brain_gates=gates))
        results = wm.retrieve_similar("Deploy Docker", gates, top_k=3)
        assert len(results) == 1
        entry, score = results[0]
        assert isinstance(entry, WorkingMemoryEntry)
        assert isinstance(score, float)

    def test_retrieve_similar_ranking_by_score(self):
        """More similar tasks rank higher."""
        wm = WorkingMemory()
        gates_a = np.array([1.0, 0.0, 0.0, 0.0, 0.0])
        gates_b = np.array([0.0, 0.0, 0.0, 0.0, 1.0])
        wm.add(_make_working_entry(task="Deploy Docker image", brain_gates=gates_a))
        wm.add(_make_working_entry(task="Update database", brain_gates=gates_b))

        results = wm.retrieve_similar("Deploy Docker image", gates_a, top_k=2)
        assert len(results) == 2
        # First result should be more similar (same gates + same text)
        assert results[0][1] >= results[1][1]
        assert results[0][0].task == "Deploy Docker image"

    def test_similarity_score_range(self):
        """Similarity scores should be between 0 and 1 (approximately)."""
        wm = WorkingMemory()
        for i in range(5):
            wm.add(_make_working_entry(task=f"Task {i}", brain_gates=_make_gates(seed=i)))

        results = wm.retrieve_similar("Task 2", _make_gates(seed=2), top_k=5)
        for _, score in results:
            assert -0.1 <= score <= 1.1  # small tolerance for floating point

    def test_get_success_rate_with_no_data(self):
        """Empty buffer returns 0.5 default."""
        wm = WorkingMemory()
        assert wm.get_success_rate() == 0.5

    def test_get_success_rate_all_success(self):
        wm = WorkingMemory()
        for i in range(5):
            wm.add(_make_working_entry(outcome="success"))
        assert wm.get_success_rate() == 1.0

    def test_get_success_rate_all_failure(self):
        wm = WorkingMemory()
        for i in range(5):
            wm.add(_make_working_entry(outcome="failure"))
        assert wm.get_success_rate() == 0.0

    def test_get_success_rate_mixed(self):
        wm = WorkingMemory()
        wm.add(_make_working_entry(outcome="success"))
        wm.add(_make_working_entry(outcome="failure"))
        wm.add(_make_working_entry(outcome="success"))
        wm.add(_make_working_entry(outcome="success"))
        assert wm.get_success_rate() == 0.75

    def test_get_success_rate_with_none_outcomes(self):
        """Entries with outcome=None are excluded from rate calculation."""
        wm = WorkingMemory()
        wm.add(_make_working_entry(outcome="success"))
        wm.add(_make_working_entry(outcome=None))
        wm.add(_make_working_entry(outcome="failure"))
        # 1 success out of 2 known outcomes
        assert wm.get_success_rate() == 0.5

    def test_get_success_rate_all_none_returns_default(self):
        """If all outcomes are None, return 0.5 default."""
        wm = WorkingMemory()
        wm.add(_make_working_entry(outcome=None))
        wm.add(_make_working_entry(outcome=None))
        assert wm.get_success_rate() == 0.5

    def test_get_success_rate_last_n(self):
        wm = WorkingMemory()
        # Older: all failures
        for _ in range(5):
            wm.add(_make_working_entry(outcome="failure"))
        # Recent: all successes
        for _ in range(3):
            wm.add(_make_working_entry(outcome="success"))
        assert wm.get_success_rate(last_n=3) == 1.0
        assert wm.get_success_rate() < 1.0  # overall includes failures

    def test_get_decision_patterns_empty(self):
        wm = WorkingMemory()
        assert wm.get_decision_patterns() == {}

    def test_get_decision_patterns(self):
        wm = WorkingMemory()
        wm.add(_make_working_entry(decision="execute"))
        wm.add(_make_working_entry(decision="execute"))
        wm.add(_make_working_entry(decision="suggest"))
        wm.add(_make_working_entry(decision="wait"))
        patterns = wm.get_decision_patterns()
        assert patterns["execute"] == pytest.approx(0.5)
        assert patterns["suggest"] == pytest.approx(0.25)
        assert patterns["wait"] == pytest.approx(0.25)

    def test_clear(self):
        wm = WorkingMemory()
        for i in range(5):
            wm.add(_make_working_entry())
        wm.clear()
        assert len(wm) == 0

    def test_repr(self):
        wm = WorkingMemory(capacity=7)
        wm.add(_make_working_entry())
        r = repr(wm)
        assert "7" in r
        assert "1" in r

    def test_cosine_similarity_identical(self):
        a = np.array([1.0, 2.0, 3.0])
        sim = WorkingMemory._cosine_similarity(a, a)
        assert sim == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        sim = WorkingMemory._cosine_similarity(a, b)
        assert sim == pytest.approx(0.0)

    def test_cosine_similarity_zero_vector(self):
        a = np.array([0.0, 0.0, 0.0])
        b = np.array([1.0, 2.0, 3.0])
        assert WorkingMemory._cosine_similarity(a, b) == 0.0
        assert WorkingMemory._cosine_similarity(b, a) == 0.0

    def test_text_similarity_identical(self):
        sim = WorkingMemory._text_similarity("deploy docker", "deploy docker")
        assert sim == pytest.approx(1.0)

    def test_text_similarity_no_overlap(self):
        sim = WorkingMemory._text_similarity("deploy docker", "fix authentication")
        assert sim == pytest.approx(0.0)

    def test_text_similarity_partial(self):
        sim = WorkingMemory._text_similarity("deploy docker container",
                                              "deploy api container")
        # 'deploy' and 'container' overlap out of {'deploy','docker','container','api'}
        assert 0.0 < sim < 1.0

    def test_text_similarity_empty(self):
        assert WorkingMemory._text_similarity("", "something") == 0.0
        assert WorkingMemory._text_similarity("something", "") == 0.0


# ===========================================================================
# 4. EpisodicMemory Tests
# ===========================================================================

class TestEpisodicMemory:
    """Tests for the EpisodicMemory class."""

    def test_default_initialization(self):
        em = EpisodicMemory()
        assert em.max_size == 1000
        assert len(em) == 0
        assert em.save_dir is None

    def test_add_single(self):
        em = EpisodicMemory()
        em.add(_make_episodic_entry())
        assert len(em) == 1

    def test_eviction_at_capacity(self):
        """When over capacity, least important memory is evicted."""
        em = EpisodicMemory(max_size=3)
        # Add with increasing importance
        em.add(_make_episodic_entry(task="Low", importance=0.1))
        em.add(_make_episodic_entry(task="Mid", importance=0.5))
        em.add(_make_episodic_entry(task="High", importance=0.9))
        assert len(em) == 3
        # Trigger eviction
        em.add(_make_episodic_entry(task="New", importance=0.6))
        assert len(em) == 3
        # Least important ("Low" with 0.1) should be evicted
        tasks = [m.task for m in em.memories]
        assert "Low" not in tasks

    def test_retrieve_similar_empty(self):
        em = EpisodicMemory()
        result = em.retrieve_similar("test", _make_gates(), "bug")
        assert result == []

    def test_retrieve_similar_returns_sorted(self):
        em = EpisodicMemory()
        gates = _make_gates(seed=10)
        em.add(_make_episodic_entry(task="Fix auth bug", task_type="bug",
                                     brain_gates=gates, importance=0.8))
        em.add(_make_episodic_entry(task="Deploy API", task_type="deploy",
                                     brain_gates=_make_gates(seed=20), importance=0.8))

        results = em.retrieve_similar("Fix auth bug", gates, "bug", top_k=2)
        assert len(results) == 2
        # First should have higher relevance
        assert results[0][1] >= results[1][1]

    def test_retrieve_similar_increments_retrieval_count(self):
        em = EpisodicMemory()
        entry = _make_episodic_entry(importance=0.8)
        em.add(entry)
        assert entry.retrieval_count == 0
        em.retrieve_similar("test", _make_gates(), "bug")
        assert entry.retrieval_count == 1
        em.retrieve_similar("test", _make_gates(), "bug")
        assert entry.retrieval_count == 2

    def test_retrieve_similar_min_importance_filter(self):
        em = EpisodicMemory()
        em.add(_make_episodic_entry(task="Important", importance=0.9))
        em.add(_make_episodic_entry(task="Unimportant", importance=0.1))
        results = em.retrieve_similar("test", _make_gates(), "bug",
                                       min_importance=0.5)
        tasks = [e.task for e, _ in results]
        assert "Important" in tasks
        assert "Unimportant" not in tasks

    def test_retrieve_similar_all_below_min_importance(self):
        em = EpisodicMemory()
        em.add(_make_episodic_entry(importance=0.1))
        em.add(_make_episodic_entry(importance=0.2))
        results = em.retrieve_similar("test", _make_gates(), "bug",
                                       min_importance=0.5)
        assert results == []

    def test_get_important_memories(self):
        em = EpisodicMemory()
        em.add(_make_episodic_entry(task="Low", importance=0.2))
        em.add(_make_episodic_entry(task="High", importance=0.9))
        em.add(_make_episodic_entry(task="Mid", importance=0.5))
        top = em.get_important_memories(top_k=2)
        assert len(top) == 2
        assert top[0].task == "High"
        assert top[1].task == "Mid"

    def test_get_by_outcome(self):
        em = EpisodicMemory()
        em.add(_make_episodic_entry(task="S1", outcome="success"))
        em.add(_make_episodic_entry(task="F1", outcome="failure"))
        em.add(_make_episodic_entry(task="S2", outcome="success"))
        successes = em.get_by_outcome("success")
        assert len(successes) == 2
        assert all(m.outcome == "success" for m in successes)

    def test_get_by_decision(self):
        em = EpisodicMemory()
        em.add(_make_episodic_entry(decision="execute"))
        em.add(_make_episodic_entry(decision="suggest"))
        em.add(_make_episodic_entry(decision="execute"))
        execs = em.get_by_decision("execute")
        assert len(execs) == 2

    def test_compute_decision_success_rate_no_data(self):
        em = EpisodicMemory()
        assert em.compute_decision_success_rate("execute") == 0.5

    def test_compute_decision_success_rate(self):
        em = EpisodicMemory()
        em.add(_make_episodic_entry(decision="execute", outcome="success"))
        em.add(_make_episodic_entry(decision="execute", outcome="success"))
        em.add(_make_episodic_entry(decision="execute", outcome="failure"))
        rate = em.compute_decision_success_rate("execute")
        assert rate == pytest.approx(2.0 / 3.0)

    def test_clear(self):
        em = EpisodicMemory()
        for _ in range(5):
            em.add(_make_episodic_entry())
        em.clear()
        assert len(em) == 0

    def test_repr(self):
        em = EpisodicMemory(max_size=50)
        em.add(_make_episodic_entry())
        r = repr(em)
        assert "1" in r
        assert "50" in r

    def test_time_since_valid(self):
        ts = datetime.now().isoformat()
        days = EpisodicMemory._time_since(ts)
        assert 0.0 <= days < 1.0  # just created, less than a day

    def test_time_since_invalid(self):
        days = EpisodicMemory._time_since("not-a-date")
        assert days == 999.0

    def test_cosine_similarity(self):
        a = np.array([1.0, 0.0])
        b = np.array([1.0, 0.0])
        assert EpisodicMemory._cosine_similarity(a, b) == pytest.approx(1.0)


# ===========================================================================
# 5. EpisodicMemory Persistence Tests
# ===========================================================================

class TestEpisodicMemoryPersistence:
    """Tests for episodic memory save/load functionality."""

    def test_save_and_load(self):
        """Memories saved to disk are reloaded on init."""
        tmpdir = tempfile.mkdtemp()
        try:
            # Create and populate
            em1 = EpisodicMemory(max_size=100, save_dir=tmpdir)
            entry = _make_episodic_entry(task="Persist me", importance=0.7)
            em1.add(entry)
            assert len(em1) == 1

            # Create new instance pointing to same dir -- should load
            em2 = EpisodicMemory(max_size=100, save_dir=tmpdir)
            assert len(em2) == 1
            assert em2.memories[0].task == "Persist me"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_saved_file_is_valid_json(self):
        tmpdir = tempfile.mkdtemp()
        try:
            em = EpisodicMemory(max_size=100, save_dir=tmpdir)
            em.add(_make_episodic_entry(task="JSON check"))

            json_files = list(Path(tmpdir).glob("memory_*.json"))
            assert len(json_files) == 1

            with open(json_files[0], "r") as f:
                data = json.load(f)
            assert data["task"] == "JSON check"
            assert isinstance(data["brain_gates"], list)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_no_persistence_without_save_dir(self):
        em = EpisodicMemory(max_size=100, save_dir=None)
        em.add(_make_episodic_entry())
        # No crash, just no file written
        assert len(em) == 1


# ===========================================================================
# 6. MemoryManager Tests
# ===========================================================================

class TestMemoryManager:
    """Tests for the MemoryManager class."""

    def test_default_initialization(self):
        mm = MemoryManager()
        assert mm.working.capacity == 10
        assert mm.episodic.max_size == 1000
        assert len(mm.working) == 0
        assert len(mm.episodic) == 0

    def test_remember_single_task(self):
        mm = MemoryManager()
        mm.remember_task(
            task="Deploy Docker",
            task_type="docker",
            decision="execute",
            confidence=0.9,
            brain_gates=_make_gates(),
            outcome="success",
        )
        assert len(mm.working) == 1

    def test_remember_and_retrieve_task(self):
        mm = MemoryManager()
        gates = _make_gates(seed=7)
        mm.remember_task("Deploy Docker", "docker", "execute", 0.9, gates, "success")

        context = mm.get_context("Deploy Docker", gates, "docker")
        assert "working_memory" in context
        assert "episodic_memory" in context
        assert len(context["working_memory"]["recent_tasks"]) == 1

    def test_get_context_with_matching_task(self):
        mm = MemoryManager()
        gates = _make_gates(seed=5)
        mm.remember_task("Deploy Docker image", "docker", "execute", 0.9, gates, "success")

        context = mm.get_context("Deploy Docker image", gates, "docker")
        similar = context["working_memory"]["similar_tasks"]
        assert len(similar) >= 1
        # The stored task should appear with high similarity
        entry_dict, score = similar[0]
        assert entry_dict["task"] == "Deploy Docker image"
        assert score > 0.5

    def test_get_context_with_no_matches(self):
        """get_context on empty memory returns empty lists."""
        mm = MemoryManager()
        context = mm.get_context("Anything", _make_gates(), "misc")
        assert context["working_memory"]["recent_tasks"] == []
        assert context["working_memory"]["similar_tasks"] == []
        assert context["working_memory"]["decision_patterns"] == {}
        assert context["working_memory"]["recent_success_rate"] == 0.5
        assert context["episodic_memory"]["similar_episodes"] == []
        assert context["episodic_memory"]["num_memories"] == 0

    def test_get_context_similar_tasks_format(self):
        """similar_tasks entries are (dict, float) tuples."""
        mm = MemoryManager()
        mm.remember_task("Deploy", "docker", "execute", 0.8, _make_gates(), "success")
        context = mm.get_context("Deploy", _make_gates(), "docker")
        for item in context["working_memory"]["similar_tasks"]:
            assert isinstance(item, (list, tuple))
            assert len(item) == 2
            assert isinstance(item[0], dict)
            assert isinstance(item[1], float)

    def test_consolidate_to_episodic(self):
        mm = MemoryManager()
        mm.consolidate_to_episodic(
            task="Fix bug",
            task_type="bug",
            decision="suggest",
            confidence=0.7,
            outcome="success",
            brain_gates=_make_gates(),
            layer1_features={"complexity": 0.5},
            layer2_sequence=["plan"],
            reasoning_chain=["reason"],
            importance=0.8,
            emotional_valence="positive",
        )
        assert len(mm.episodic) == 1

    def test_consolidate_and_retrieve_episodic(self):
        mm = MemoryManager()
        gates = _make_gates(seed=3)
        mm.consolidate_to_episodic(
            task="Fix auth bug",
            task_type="bug",
            decision="suggest",
            confidence=0.7,
            outcome="success",
            brain_gates=gates,
            layer1_features={"complexity": 0.5},
            layer2_sequence=["plan"],
            reasoning_chain=["reason"],
            importance=0.8,
            emotional_valence="positive",
        )
        context = mm.get_context("Fix auth bug", gates, "bug")
        episodes = context["episodic_memory"]["similar_episodes"]
        assert len(episodes) >= 1

    def test_multiple_tasks_different_types(self):
        mm = MemoryManager()
        mm.remember_task("Deploy Docker", "docker", "execute", 0.9, _make_gates(seed=1))
        mm.remember_task("Fix bug", "bug", "suggest", 0.7, _make_gates(seed=2))
        mm.remember_task("Update DB", "database", "wait", 0.4, _make_gates(seed=3))
        assert len(mm.working) == 3

    def test_confidence_tracking(self):
        """Confidence values are preserved in stored entries."""
        mm = MemoryManager()
        mm.remember_task("Task A", "type_a", "execute", 0.123, _make_gates())
        recent = mm.working.get_recent(1)
        assert recent[0].confidence == pytest.approx(0.123)

    def test_outcome_update_via_remember(self):
        """Outcome can be passed as None then stored as success."""
        mm = MemoryManager()
        mm.remember_task("Task", "type", "execute", 0.5, _make_gates(), outcome=None)
        assert mm.working.get_recent(1)[0].outcome is None
        mm.remember_task("Task 2", "type", "execute", 0.5, _make_gates(), outcome="success")
        assert mm.working.get_recent(1)[0].outcome == "success"

    def test_empty_memory_operations(self):
        """All operations work gracefully on empty memory."""
        mm = MemoryManager()
        context = mm.get_context("test", _make_gates(), "test")
        assert context["working_memory"]["recent_success_rate"] == 0.5
        assert context["episodic_memory"]["num_memories"] == 0

    def test_repr(self):
        mm = MemoryManager(working_capacity=5, episodic_max=50)
        r = repr(mm)
        assert "MemoryManager" in r
        assert "WorkingMemory" in r
        assert "EpisodicMemory" in r

    def test_state_serialization_full_context(self):
        """Full context output is JSON-serializable."""
        mm = MemoryManager()
        mm.remember_task("Deploy", "docker", "execute", 0.8, _make_gates(), "success")
        mm.consolidate_to_episodic(
            task="Deploy",
            task_type="docker",
            decision="execute",
            confidence=0.8,
            outcome="success",
            brain_gates=_make_gates(),
            layer1_features={"c": 0.5},
            layer2_sequence=["s"],
            reasoning_chain=["r"],
            importance=0.7,
            emotional_valence="positive",
        )
        context = mm.get_context("Deploy", _make_gates(), "docker")
        # Must be JSON serializable
        serialized = json.dumps(context)
        restored = json.loads(serialized)
        assert "working_memory" in restored
        assert "episodic_memory" in restored


# ===========================================================================
# 7. Stress / Scale Tests
# ===========================================================================

class TestMemoryScale:
    """Tests with large numbers of entries."""

    def test_large_working_memory_throughput(self):
        """Insert 100+ entries without error."""
        wm = WorkingMemory(capacity=10)
        for i in range(150):
            wm.add(_make_working_entry(task=f"Task {i}", brain_gates=_make_gates(seed=i)))
        # Should still be at capacity
        assert len(wm) == 10
        # Most recent should be Task 149
        assert wm.get_recent(1)[0].task == "Task 149"

    def test_large_episodic_memory(self):
        """Insert 100+ episodes without error."""
        em = EpisodicMemory(max_size=200)
        for i in range(120):
            em.add(_make_episodic_entry(
                task=f"Episode {i}",
                importance=np.random.RandomState(i).rand(),
                brain_gates=_make_gates(seed=i),
            ))
        assert len(em) == 120

    def test_large_episodic_eviction(self):
        """Eviction works correctly at scale."""
        em = EpisodicMemory(max_size=50)
        for i in range(100):
            em.add(_make_episodic_entry(
                task=f"Episode {i}",
                importance=i / 100.0,
                brain_gates=_make_gates(seed=i),
            ))
        assert len(em) == 50
        # All remaining should have higher importance (least important evicted)
        importances = [m.importance for m in em.memories]
        assert min(importances) >= 0.49  # roughly the top half should remain

    def test_retrieve_similar_with_many_entries(self):
        """Similarity search works at scale."""
        wm = WorkingMemory(capacity=50)
        for i in range(50):
            wm.add(_make_working_entry(task=f"Task {i}", brain_gates=_make_gates(seed=i)))
        results = wm.retrieve_similar("Task 25", _make_gates(seed=25), top_k=5)
        assert len(results) == 5
        # First result should be the exact match
        assert results[0][0].task == "Task 25"


# ===========================================================================
# 8. Thread Safety Tests
# ===========================================================================

class TestMemoryThreadSafety:
    """Basic thread-safety smoke tests."""

    def test_concurrent_working_memory_adds(self):
        """Multiple threads adding to working memory should not crash."""
        wm = WorkingMemory(capacity=100)
        errors = []

        def adder(thread_id):
            try:
                for i in range(50):
                    wm.add(_make_working_entry(
                        task=f"Thread-{thread_id}-Task-{i}",
                        brain_gates=_make_gates(seed=thread_id * 1000 + i),
                    ))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=adder, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Some entries should exist (exact count depends on race conditions)
        assert len(wm) > 0

    def test_concurrent_memory_manager_operations(self):
        """Mixed read/write operations from multiple threads."""
        mm = MemoryManager(working_capacity=100, episodic_max=200)
        errors = []

        def writer(thread_id):
            try:
                for i in range(20):
                    mm.remember_task(
                        task=f"T{thread_id}-{i}",
                        task_type="test",
                        decision="execute",
                        confidence=0.5,
                        brain_gates=_make_gates(seed=thread_id * 100 + i),
                        outcome="success",
                    )
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(20):
                    mm.get_context("test query", _make_gates(), "test")
            except Exception as e:
                errors.append(e)

        threads = []
        for t in range(3):
            threads.append(threading.Thread(target=writer, args=(t,)))
        threads.append(threading.Thread(target=reader))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# ===========================================================================
# 9. Edge Case / Decay Tests
# ===========================================================================

class TestMemoryEdgeCases:
    """Edge cases and decay behavior."""

    def test_zero_gate_vector(self):
        """Zero brain gates should not crash cosine similarity."""
        wm = WorkingMemory()
        zero_gates = np.zeros(10)
        wm.add(_make_working_entry(brain_gates=zero_gates))
        results = wm.retrieve_similar("test", zero_gates, top_k=1)
        assert len(results) == 1
        _, score = results[0]
        # cosine similarity with zero vectors returns 0
        assert score >= 0.0

    def test_single_element_gate(self):
        wm = WorkingMemory()
        gates = np.array([1.0])
        wm.add(_make_working_entry(brain_gates=gates))
        results = wm.retrieve_similar("test", gates, top_k=1)
        assert len(results) == 1

    def test_episodic_recency_decay(self):
        """Older memories get lower recency weight in retrieval."""
        em = EpisodicMemory()
        gates = _make_gates(seed=42)

        # Recent entry
        recent_ts = datetime.now().isoformat()
        em.add(_make_episodic_entry(
            task="Recent task",
            brain_gates=gates,
            importance=0.8,
            timestamp=recent_ts,
        ))

        # Old entry (simulate 30 days ago)
        old_ts = (datetime.now() - timedelta(days=30)).isoformat()
        em.add(_make_episodic_entry(
            task="Old task",
            brain_gates=gates,
            importance=0.8,
            timestamp=old_ts,
        ))

        results = em.retrieve_similar("Recent task", gates, "bug", top_k=2)
        assert len(results) == 2
        # Recent should rank higher due to recency factor
        assert results[0][0].task == "Recent task"
        assert results[0][1] > results[1][1]

    def test_episodic_type_match_boost(self):
        """Same task_type gets boosted in relevance."""
        em = EpisodicMemory()
        gates = _make_gates(seed=50)

        em.add(_make_episodic_entry(
            task="Bug A", task_type="bug", brain_gates=gates, importance=0.8,
        ))
        em.add(_make_episodic_entry(
            task="Deploy A", task_type="deploy", brain_gates=gates, importance=0.8,
        ))

        results = em.retrieve_similar("Bug B", gates, "bug", top_k=2)
        # Bug A should rank higher due to type match
        assert results[0][0].task_type == "bug"

    def test_empty_task_text(self):
        """Empty task text should not crash."""
        mm = MemoryManager()
        mm.remember_task("", "empty", "execute", 0.5, _make_gates())
        context = mm.get_context("", _make_gates(), "empty")
        assert len(context["working_memory"]["recent_tasks"]) == 1

    def test_very_long_task_text(self):
        """Very long task text should not crash."""
        long_text = "word " * 10000
        mm = MemoryManager()
        mm.remember_task(long_text, "long", "execute", 0.5, _make_gates())
        context = mm.get_context(long_text, _make_gates(), "long")
        assert len(context["working_memory"]["recent_tasks"]) == 1

    def test_special_characters_in_task(self):
        """Special characters in task text."""
        mm = MemoryManager()
        special = "Deploy <container> & run 'tests' \"now\" @#$%"
        mm.remember_task(special, "misc", "execute", 0.5, _make_gates())
        recent = mm.working.get_recent(1)
        assert recent[0].task == special


# ===========================================================================
# Run guard
# ===========================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
