"""Tests for ThoughtJury — 5-judge autonomous thought evaluation system."""
import threading
import time

import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from core.thought_jury import (
    ThoughtJury, CoherenceJudge, NoveltyJudge, RelevanceJudge,
    DepthJudge, ProgressJudge, ConsensusGate, DeepReview,
    JudgeResult, JuryContext, BaseJudge,
)
from core.brain_chat import ContinuousThought


# ── Helpers ──────────────────────────────────────────────────────


def _make_thought(content="test thought", category="reflect", topic="test"):
    return ContinuousThought(
        timestamp=time.time(),
        content=content,
        category=category,
        topic=topic,
        relevance=0.5,
        thought_id="abc123",
    )


def _make_mock_semantic_index():
    """Mock SemanticIndex with embed() and search()."""
    idx = MagicMock()
    # embed returns L2-normalized 384-dim vector seeded by text hash
    idx.embed.side_effect = lambda text: (
        np.random.RandomState(hash(text) % 2**31).randn(384).astype(np.float32) / 10.0
    )
    idx.search.return_value = []  # default: no matches
    return idx


def _make_mock_cte():
    """Mock ContinuousThinkingEngine with _thoughts, _current_topic, _thought_lock."""
    cte = MagicMock()
    cte._thought_lock = threading.Lock()
    cte._thoughts = []
    cte._current_topic = ""
    return cte


# ── Tests ────────────────────────────────────────────────────────


class TestThoughtJury:

    def test_evaluate_returns_float(self):
        """ThoughtJury.evaluate returns a float reward."""
        idx = _make_mock_semantic_index()
        jury = ThoughtJury(semantic_index=idx)
        thought = _make_thought()
        cte = _make_mock_cte()
        reward = jury.evaluate(thought, cte)
        assert isinstance(reward, float)

    def test_coherence_high_similarity(self):
        """CoherenceJudge scores > 0.6 when search returns high-similarity hits."""
        idx = _make_mock_semantic_index()
        idx.search.return_value = [("id1", 0.8), ("id2", 0.7)]

        judge = CoherenceJudge()
        judge._semantic_index = idx

        ctx = JuryContext(
            thought_embedding=np.ones(384, dtype=np.float32),
            moltbook_available=True,
        )
        result = judge.evaluate(_make_thought(), ctx)
        assert result.score > 0.6

    def test_coherence_empty_moltbook(self):
        """CoherenceJudge returns 0.0 when no semantic_index (abstains)."""
        judge = CoherenceJudge()
        ctx = JuryContext(moltbook_available=False)
        result = judge.evaluate(_make_thought(), ctx)
        assert result.score == 0.0

    def test_novelty_novel_thought(self):
        """NoveltyJudge scores > 0.5 for a thought with different embeddings than recent."""
        idx = _make_mock_semantic_index()
        # Different texts produce different embeddings via seeded RNG
        thought_emb = idx.embed("brand new idea about quantum computing")
        recent = [idx.embed("old thought about gardening"),
                  idx.embed("another old thought about cooking")]

        ctx = JuryContext(
            thought_embedding=thought_emb,
            recent_thought_embeddings=recent,
        )
        judge = NoveltyJudge()
        result = judge.evaluate(_make_thought(), ctx)
        assert result.score > 0.5

    def test_novelty_repetitive(self):
        """NoveltyJudge scores < 0.3 when thought is identical to recent (fixed embedding)."""
        # Fixed unit vector so cosine sim ~ 1.0
        fixed_vec = np.ones(384, dtype=np.float32)
        fixed_vec /= np.linalg.norm(fixed_vec)

        ctx = JuryContext(
            thought_embedding=fixed_vec,
            recent_thought_embeddings=[fixed_vec.copy(), fixed_vec.copy()],
        )
        judge = NoveltyJudge()
        result = judge.evaluate(_make_thought(), ctx)
        assert result.score < 0.3

    def test_relevance_on_topic(self):
        """RelevanceJudge scores > 0.3 when thought matches topic embedding."""
        idx = _make_mock_semantic_index()
        emb = idx.embed("machine learning")

        ctx = JuryContext(
            thought_embedding=emb,
            current_topic="machine learning",
            current_topic_embedding=emb,  # same text -> same embedding
        )
        judge = RelevanceJudge()
        result = judge.evaluate(_make_thought(content="machine learning"), ctx)
        assert result.score > 0.3

    def test_relevance_no_topic(self):
        """RelevanceJudge returns 0.0 when topic is empty (abstains)."""
        ctx = JuryContext(
            thought_embedding=np.ones(384, dtype=np.float32),
            current_topic="",
        )
        judge = RelevanceJudge()
        result = judge.evaluate(_make_thought(), ctx)
        assert result.score == 0.0

    def test_depth_with_ring_signature(self):
        """DepthJudge scores > 0.5 with high semantic_richness ring signature."""
        ring_sig = MagicMock()
        ring_sig.semantic_richness = 0.8

        # Long content with many unique words for text_score
        long_content = " ".join(f"word{i}" for i in range(40))
        ctx = JuryContext(ring_signature=ring_sig)
        judge = DepthJudge()
        result = judge.evaluate(_make_thought(content=long_content), ctx)
        assert result.score > 0.5

    def test_progress_building(self):
        """ProgressJudge scores > 0.4 for moderately related thoughts."""
        # Create two somewhat different embeddings (related but not identical)
        rng = np.random.RandomState(42)
        base = rng.randn(384).astype(np.float32)
        base /= np.linalg.norm(base)
        # Perturb to get moderate similarity (~0.5 cosine sim)
        noise = rng.randn(384).astype(np.float32) * 0.08
        thought_emb = base + noise
        thought_emb /= np.linalg.norm(thought_emb)

        ctx = JuryContext(
            thought_embedding=thought_emb,
            recent_thought_embeddings=[base],
        )
        judge = ProgressJudge()
        result = judge.evaluate(_make_thought(), ctx)
        assert result.score > 0.4

    def test_progress_repetition(self):
        """ProgressJudge scores <= 0.15 when thoughts are near-identical (max_sim > 0.85)."""
        fixed_vec = np.ones(384, dtype=np.float32)
        fixed_vec /= np.linalg.norm(fixed_vec)

        ctx = JuryContext(
            thought_embedding=fixed_vec,
            recent_thought_embeddings=[fixed_vec.copy()],
        )
        judge = ProgressJudge()
        result = judge.evaluate(_make_thought(), ctx)
        # max_sim ~ 1.0 -> score = 0.1
        assert result.score <= 0.15

    def test_consensus_positive(self):
        """ConsensusGate returns positive aggregate when >= 3 judges score > threshold."""
        gate = ConsensusGate()
        results = [
            JudgeResult(name="coherence", score=0.8),
            JudgeResult(name="novelty", score=0.6),
            JudgeResult(name="relevance", score=0.7),
            JudgeResult(name="depth", score=0.9),
            JudgeResult(name="progress", score=0.2),  # only one below
        ]
        weights = {r.name: 1.0 for r in results}
        reward = gate.aggregate(results, weights)
        assert reward > 0

    def test_consensus_negative(self):
        """ConsensusGate returns negative aggregate when < 3 judges score above threshold."""
        gate = ConsensusGate()
        results = [
            JudgeResult(name="coherence", score=0.6),
            JudgeResult(name="novelty", score=0.5),
            JudgeResult(name="relevance", score=0.1),
            JudgeResult(name="depth", score=0.2),
            JudgeResult(name="progress", score=0.1),
        ]
        weights = {r.name: 1.0 for r in results}
        reward = gate.aggregate(results, weights)
        assert reward < 0

    def test_graceful_no_index(self):
        """ThoughtJury works without crashing when semantic_index is None."""
        jury = ThoughtJury(semantic_index=None)
        thought = _make_thought()
        cte = _make_mock_cte()
        reward = jury.evaluate(thought, cte)
        assert isinstance(reward, float)

    def test_thread_safety(self):
        """10 threads calling evaluate concurrently should not crash."""
        idx = _make_mock_semantic_index()
        jury = ThoughtJury(semantic_index=idx)
        cte = _make_mock_cte()
        errors = []

        def _run():
            try:
                for _ in range(5):
                    jury.evaluate(_make_thought(), cte)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_run) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Thread errors: {errors}"

    def test_stats_populated(self):
        """After 5 evaluations, stats reflect correct counts."""
        idx = _make_mock_semantic_index()
        jury = ThoughtJury(semantic_index=idx)
        cte = _make_mock_cte()

        for _ in range(5):
            jury.evaluate(_make_thought(), cte)

        stats = jury.get_stats()
        assert stats['total_evaluations'] == 5
        assert stats['total_positive'] + stats['total_negative'] == 5

    def test_deep_review_triggers(self):
        """DeepReview triggers after `interval` evaluations and calibrates weights."""
        mock_pool = MagicMock()
        mock_result = MagicMock()
        mock_result.confidence = 0.6
        mock_pool.summarize.return_value = mock_result

        idx = _make_mock_semantic_index()
        jury = ThoughtJury(semantic_index=idx, micro_agent_pool=mock_pool,
                           deep_review_interval=2)
        cte = _make_mock_cte()

        jury.evaluate(_make_thought(content="first thought"), cte)
        jury.evaluate(_make_thought(content="second thought"), cte)

        assert jury._deep_review._total_reviews == 1

    def test_weights_bounded(self):
        """After deep review calibration, all weights remain in [0.5, 2.0]."""
        mock_pool = MagicMock()
        mock_result = MagicMock()
        mock_result.confidence = 0.6
        mock_pool.summarize.return_value = mock_result

        idx = _make_mock_semantic_index()
        jury = ThoughtJury(semantic_index=idx, micro_agent_pool=mock_pool,
                           deep_review_interval=1)
        cte = _make_mock_cte()

        # Run many evaluations to accumulate weight changes
        for i in range(20):
            jury.evaluate(_make_thought(content=f"thought number {i}"), cte)

        for name, w in jury._weights.items():
            assert 0.5 <= w <= 2.0, f"Weight {name}={w} out of bounds [0.5, 2.0]"
