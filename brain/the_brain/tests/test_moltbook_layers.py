"""
Tests for Moltbook layers: Thinking, Retrieval, Thinker, Talker.

Covers:
  - moltbook_thinking.py:  MicroThought, ThoughtQuality, ThoughtBuffer,
                           AssociativeThinking, EmotionalThinking, ThoughtStream, MetaThinking
  - moltbook_retrieval.py: MarkovKnowledgeChain, SpeculativeRetrieval,
                           ContextPredictor, RelevanceScorer, KnowledgeDecay,
                           AttentionDrivenRetrieval
  - moltbook_thinker.py:   ThreadOutput, UnifiedThought, GoalThread, ReasoningThread,
                           MemoryThread, ConfidenceEstimator, ThoughtQualityGate,
                           CognitiveController, InternalMonologue
  - moltbook_talker.py:    ResponsePlan, TalkerResponse, PersonalityFilter,
                           HumanLikeTransformer, ResponseStructurer, TalkerModule
"""

import math
import os
import sys
import tempfile
import time

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.moltbook import MoltbookStore


# ═════════════════════════════════════════════════════════════
# Thinking Layer Tests
# ═════════════════════════════════════════════════════════════

class TestMicroThought:
    """Tests for MicroThought dataclass."""

    def test_create_default(self):
        from core.moltbook_thinking import MicroThought
        t = MicroThought()
        assert t.content == ""
        assert t.relevance_to_current_task == 0.0
        assert t.emotional_charge == 0.0
        assert t.arousal == 0.0
        assert t.thought_type == "association"
        assert t.activation == 1.0
        assert t.was_conscious is False

    def test_create_with_values(self):
        from core.moltbook_thinking import MicroThought
        t = MicroThought(
            content="Python is great",
            relevance_to_current_task=0.8,
            emotional_charge=0.5,
            arousal=0.3,
            thought_type="reflection",
            activation=0.9,
        )
        assert t.content == "Python is great"
        assert t.relevance_to_current_task == 0.8
        assert t.thought_type == "reflection"

    def test_decay(self):
        from core.moltbook_thinking import MicroThought
        t = MicroThought(activation=1.0)
        # Manually age the thought
        t.created_at = time.time() - 100  # 100 seconds ago
        t.decay(rate=0.01)
        assert t.activation < 1.0
        assert t.activation >= 0.0

    def test_decay_never_negative(self):
        from core.moltbook_thinking import MicroThought
        t = MicroThought(activation=1.0)
        t.created_at = time.time() - 100000  # Very old
        t.decay(rate=1.0)
        assert t.activation >= 0.0

    def test_to_dict(self):
        from core.moltbook_thinking import MicroThought
        t = MicroThought(content="test", thought_type="memory")
        d = t.to_dict()
        assert d['content'] == "test"
        assert d['type'] == "memory"
        assert 'activation' in d
        assert 'was_conscious' in d


class TestThoughtQuality:
    """Tests for ThoughtQuality dataclass."""

    def test_defaults(self):
        from core.moltbook_thinking import ThoughtQuality
        q = ThoughtQuality()
        assert q.productivity == 0.5
        assert q.creativity == 0.5
        assert q.circularity == 0.0
        assert q.recommendation == "continue"

    def test_to_dict(self):
        from core.moltbook_thinking import ThoughtQuality
        q = ThoughtQuality(productivity=0.9, recommendation="deepen")
        d = q.to_dict()
        assert d['productivity'] == 0.9
        assert d['recommendation'] == "deepen"
        assert 'evc' in d


class TestThoughtBuffer:
    """Tests for ThoughtBuffer (Global Workspace)."""

    def test_init(self):
        from core.moltbook_thinking import ThoughtBuffer
        buf = ThoughtBuffer(capacity=50, workspace_size=5)
        assert buf.size == 0

    def test_add_and_size(self):
        from core.moltbook_thinking import ThoughtBuffer, MicroThought
        buf = ThoughtBuffer()
        buf.add(MicroThought(content="thought1"))
        buf.add(MicroThought(content="thought2"))
        assert buf.size == 2

    def test_capacity_limit(self):
        from core.moltbook_thinking import ThoughtBuffer, MicroThought
        buf = ThoughtBuffer(capacity=5)
        for i in range(10):
            buf.add(MicroThought(content=f"thought_{i}"))
        assert buf.size == 5  # Oldest evicted

    def test_get_workspace_empty(self):
        from core.moltbook_thinking import ThoughtBuffer
        buf = ThoughtBuffer()
        ws = buf.get_workspace()
        assert ws == []

    def test_get_workspace_returns_top_k(self):
        from core.moltbook_thinking import ThoughtBuffer, MicroThought
        buf = ThoughtBuffer(workspace_size=3)
        for i in range(10):
            buf.add(MicroThought(content=f"t_{i}", activation=float(i) / 10))
        ws = buf.get_workspace()
        assert len(ws) <= 3

    def test_get_workspace_marks_conscious(self):
        from core.moltbook_thinking import ThoughtBuffer, MicroThought
        buf = ThoughtBuffer(workspace_size=2)
        t1 = MicroThought(content="hello", activation=0.9)
        t2 = MicroThought(content="world", activation=0.8)
        buf.add(t1)
        buf.add(t2)
        ws = buf.get_workspace()
        # All in workspace should be conscious
        for t in ws:
            assert t.was_conscious is True

    def test_get_workspace_context_boost(self):
        from core.moltbook_thinking import ThoughtBuffer, MicroThought
        buf = ThoughtBuffer(workspace_size=5)
        t1 = MicroThought(content="python programming language", activation=0.5)
        t2 = MicroThought(content="weather forecast", activation=0.5)
        buf.add(t1)
        buf.add(t2)
        ws = buf.get_workspace(context="python")
        # Python-related thought should be boosted
        assert len(ws) == 2

    def test_get_recent(self):
        from core.moltbook_thinking import ThoughtBuffer, MicroThought
        buf = ThoughtBuffer()
        for i in range(20):
            buf.add(MicroThought(content=f"t_{i}"))
        recent = buf.get_recent(5)
        assert len(recent) == 5
        assert recent[-1].content == "t_19"

    def test_get_by_type(self):
        from core.moltbook_thinking import ThoughtBuffer, MicroThought
        buf = ThoughtBuffer()
        buf.add(MicroThought(content="a", thought_type="association"))
        buf.add(MicroThought(content="b", thought_type="reflection"))
        buf.add(MicroThought(content="c", thought_type="association"))
        assocs = buf.get_by_type("association")
        assert len(assocs) == 2

    def test_clear(self):
        from core.moltbook_thinking import ThoughtBuffer, MicroThought
        buf = ThoughtBuffer()
        buf.add(MicroThought(content="test"))
        buf.clear()
        assert buf.size == 0

    def test_get_stats(self):
        from core.moltbook_thinking import ThoughtBuffer, MicroThought
        buf = ThoughtBuffer()
        buf.add(MicroThought(content="test"))
        stats = buf.get_stats()
        assert stats['size'] == 1
        assert stats['total_thoughts'] == 1
        assert 'consciousness_rate' in stats


class TestAssociativeThinking:
    """Tests for AssociativeThinking."""

    def test_init_no_moltbook(self):
        from core.moltbook_thinking import AssociativeThinking
        at = AssociativeThinking()
        assert at._max_hops == 3
        assert at._decay_per_hop == 0.5

    def test_associate_no_moltbook_returns_empty(self):
        from core.moltbook_thinking import AssociativeThinking
        at = AssociativeThinking()
        result = at.associate("test")
        assert result == []

    def test_associate_with_moltbook(self):
        from core.moltbook_thinking import AssociativeThinking
        store = MoltbookStore()
        store.add_entry("Python programming language")
        store.add_entry("Machine learning with Python")
        at = AssociativeThinking(moltbook=store)
        result = at.associate("Python", max_results=3)
        assert isinstance(result, list)
        # May or may not find associations depending on embedding similarity
        for t in result:
            assert hasattr(t, 'content')
            assert t.thought_type == "association"

    def test_find_creative_bridge_no_moltbook(self):
        from core.moltbook_thinking import AssociativeThinking
        at = AssociativeThinking()
        result = at.find_creative_bridge("A", "B")
        assert result == []

    def test_decay_per_hop_reduces_relevance(self):
        from core.moltbook_thinking import AssociativeThinking
        store = MoltbookStore()
        for i in range(5):
            store.add_entry(f"topic alpha beta {i}")
        at = AssociativeThinking(moltbook=store, decay_per_hop=0.5)
        result = at.associate("alpha beta", max_results=5)
        if len(result) >= 2:
            assert result[0].relevance_to_current_task >= result[1].relevance_to_current_task

    def test_get_stats(self):
        from core.moltbook_thinking import AssociativeThinking
        at = AssociativeThinking()
        stats = at.get_stats()
        assert stats['total_chains'] == 0
        assert stats['total_hops'] == 0


class TestEmotionalThinking:
    """Tests for EmotionalThinking."""

    def test_init(self):
        from core.moltbook_thinking import EmotionalThinking
        et = EmotionalThinking()
        assert et._current_valence == 0.0

    def test_get_search_breadth_positive(self):
        from core.moltbook_thinking import EmotionalThinking
        et = EmotionalThinking()
        et._current_valence = 0.8  # Positive affect
        breadth = et.get_search_breadth()
        # Positive affect should broaden
        assert breadth > 0.5

    def test_get_search_breadth_negative(self):
        from core.moltbook_thinking import EmotionalThinking
        et = EmotionalThinking()
        et._current_valence = -0.8  # Negative affect
        breadth = et.get_search_breadth()
        # Negative affect should narrow
        assert breadth <= 0.5

    def test_modulate_thought(self):
        from core.moltbook_thinking import EmotionalThinking, MicroThought
        et = EmotionalThinking()
        t = MicroThought(content="test", emotional_charge=0.0)
        result = et.modulate_thought(t)
        assert isinstance(result, MicroThought)

    def test_get_state(self):
        from core.moltbook_thinking import EmotionalThinking
        et = EmotionalThinking()
        state = et.get_state()
        assert 'valence' in state
        assert 'arousal' in state


class TestThoughtStream:
    """Tests for ThoughtStream."""

    def test_init_creates_buffer(self):
        from core.moltbook_thinking import ThoughtStream
        ts = ThoughtStream()
        assert ts.buffer is not None
        assert ts.is_running is False

    def test_init_with_external_buffer(self):
        from core.moltbook_thinking import ThoughtStream, ThoughtBuffer
        buf = ThoughtBuffer(capacity=50)
        ts = ThoughtStream(buffer=buf)
        assert ts.buffer is buf

    def test_set_context(self):
        from core.moltbook_thinking import ThoughtStream
        ts = ThoughtStream()
        ts.set_context("Python programming")
        assert ts._current_context == "Python programming"

    def test_add_seed(self):
        from core.moltbook_thinking import ThoughtStream
        ts = ThoughtStream()
        ts.add_seed("topic_a")
        ts.add_seed("topic_b")
        assert len(ts._seeds) == 2

    def test_add_seed_limit(self):
        from core.moltbook_thinking import ThoughtStream
        ts = ThoughtStream()
        for i in range(30):
            ts.add_seed(f"seed_{i}")
        assert len(ts._seeds) == 20  # Max 20

    def test_background_tick_no_context(self):
        from core.moltbook_thinking import ThoughtStream
        ts = ThoughtStream()
        result = ts.background_tick()
        assert result is None  # No context, no seeds

    def test_background_tick_with_context(self):
        from core.moltbook_thinking import ThoughtStream
        ts = ThoughtStream()
        ts.set_context("test context")
        result = ts.background_tick()
        # Without moltbook, gets fallback thought
        assert result is not None
        assert "test context" in result.content or result.thought_type == "reflection"

    def test_background_tick_with_moltbook(self):
        from core.moltbook_thinking import ThoughtStream
        store = MoltbookStore()
        store.add_entry("Python programming is versatile")
        ts = ThoughtStream(moltbook=store)
        ts.set_context("Python")
        result = ts.background_tick()
        assert result is not None

    def test_get_relevant_thoughts(self):
        from core.moltbook_thinking import ThoughtStream, MicroThought
        ts = ThoughtStream()
        # Manually add thoughts to buffer
        ts._buffer.add(MicroThought(content="python code", activation=0.8))
        ts._buffer.add(MicroThought(content="weather forecast", activation=0.3))
        thoughts = ts.get_relevant_thoughts("python", top_k=5)
        assert isinstance(thoughts, list)

    def test_start_stop(self):
        from core.moltbook_thinking import ThoughtStream
        ts = ThoughtStream(interval_ms=50)
        ts.set_context("test")
        ts.start()
        assert ts.is_running is True
        time.sleep(0.15)  # Let a few ticks run
        ts.stop()
        assert ts.is_running is False

    def test_get_stats(self):
        from core.moltbook_thinking import ThoughtStream
        ts = ThoughtStream()
        stats = ts.get_stats()
        assert 'running' in stats
        assert 'total_ticks' in stats
        assert 'buffer' in stats

    def test_from_yaml(self):
        from core.moltbook_thinking import ThoughtStream
        config = {'moltbook': {'thought_stream_interval_ms': 500}}
        ts = ThoughtStream.from_yaml(config)
        assert ts._interval_ms == 500


class TestMetaThinking:
    """Tests for MetaThinking."""

    def test_init(self):
        from core.moltbook_thinking import MetaThinking
        mt = MetaThinking()
        assert mt._circularity_threshold == 0.7

    def test_evaluate_none_returns_continue(self):
        from core.moltbook_thinking import MetaThinking
        mt = MetaThinking()
        q = mt.evaluate()
        assert q.recommendation == "continue"

    def test_evaluate_thoughts(self):
        from core.moltbook_thinking import MetaThinking, MicroThought, ThoughtQuality
        mt = MetaThinking()
        thoughts = [
            MicroThought(content="thought 1", activation=0.8),
            MicroThought(content="thought 2", activation=0.6),
        ]
        q = mt.evaluate(thoughts=thoughts)
        assert isinstance(q, ThoughtQuality)
        assert 0.0 <= q.productivity <= 1.0

    def test_evaluate_circular_thoughts(self):
        from core.moltbook_thinking import MetaThinking, MicroThought, ThoughtQuality
        mt = MetaThinking(circularity_threshold=0.5)
        # Repeated content should increase circularity
        thoughts = [
            MicroThought(content="same thing"),
            MicroThought(content="same thing"),
            MicroThought(content="same thing"),
        ]
        q = mt.evaluate(thoughts=thoughts)
        assert isinstance(q, ThoughtQuality)

    def test_should_redirect(self):
        from core.moltbook_thinking import MetaThinking
        mt = MetaThinking()
        # Feed many identical hashes to trigger redirect
        for _ in range(10):
            mt._recent_thought_hashes.append("same_hash")
        assert mt.should_redirect() is True

    def test_should_not_redirect_diverse(self):
        from core.moltbook_thinking import MetaThinking
        mt = MetaThinking()
        # Feed diverse hashes
        for i in range(10):
            mt._recent_thought_hashes.append(f"hash_{i}")
        assert mt.should_redirect() is False


# ═════════════════════════════════════════════════════════════
# Retrieval Layer Tests
# ═════════════════════════════════════════════════════════════

class TestMarkovKnowledgeChain:
    """Tests for MarkovKnowledgeChain."""

    def test_init(self):
        from core.moltbook_retrieval import MarkovKnowledgeChain
        mk = MarkovKnowledgeChain()
        assert mk._total_updates == 0

    def test_update_single_sequence(self):
        from core.moltbook_retrieval import MarkovKnowledgeChain
        mk = MarkovKnowledgeChain()
        mk.update(["python", "testing", "deployment"])
        assert mk._total_updates == 1
        assert mk._total_from["python"] == 1.0
        assert mk._transitions_1["python"]["testing"] == 1.0

    def test_update_short_sequence_ignored(self):
        from core.moltbook_retrieval import MarkovKnowledgeChain
        mk = MarkovKnowledgeChain()
        mk.update(["single"])
        assert mk._total_updates == 0

    def test_predict_next_topics(self):
        from core.moltbook_retrieval import MarkovKnowledgeChain
        mk = MarkovKnowledgeChain()
        # Train with multiple sequences
        mk.update(["python", "testing", "deployment"])
        mk.update(["python", "testing", "ci"])
        mk.update(["python", "machine_learning", "data"])
        predictions = mk.predict_next_topics(["python"], n=3)
        assert len(predictions) > 0
        # "testing" should be most likely after "python"
        topics = [t for t, _ in predictions]
        assert "testing" in topics

    def test_predict_empty_input(self):
        from core.moltbook_retrieval import MarkovKnowledgeChain
        mk = MarkovKnowledgeChain()
        predictions = mk.predict_next_topics([], n=3)
        assert predictions == []

    def test_second_order_predictions(self):
        from core.moltbook_retrieval import MarkovKnowledgeChain
        mk = MarkovKnowledgeChain()
        # Train to learn: python + testing → deployment
        for _ in range(5):
            mk.update(["python", "testing", "deployment"])
        predictions = mk.predict_next_topics(["python", "testing"], n=3)
        assert len(predictions) > 0
        topics = [t for t, _ in predictions]
        assert "deployment" in topics

    def test_get_transition_probability(self):
        from core.moltbook_retrieval import MarkovKnowledgeChain
        mk = MarkovKnowledgeChain()
        mk.update(["A", "B", "C"])
        mk.update(["A", "B", "D"])
        prob = mk.get_transition_probability("A", "B")
        assert prob == 1.0  # A always transitions to B

    def test_get_transition_probability_unknown(self):
        from core.moltbook_retrieval import MarkovKnowledgeChain
        mk = MarkovKnowledgeChain()
        prob = mk.get_transition_probability("X", "Y")
        assert prob == 0.0

    def test_get_popular_topics(self):
        from core.moltbook_retrieval import MarkovKnowledgeChain
        mk = MarkovKnowledgeChain()
        mk.update(["python", "python", "testing", "python"])
        popular = mk.get_popular_topics(n=2)
        assert popular[0][0] == "python"  # Most frequent
        assert popular[0][1] >= 3

    def test_save_and_load(self):
        from core.moltbook_retrieval import MarkovKnowledgeChain
        mk = MarkovKnowledgeChain()
        mk.update(["A", "B", "C", "D"])
        mk.update(["A", "B", "E"])

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = f.name
        try:
            mk.save(path)
            mk2 = MarkovKnowledgeChain()
            loaded = mk2.load(path)
            assert loaded is True
            assert mk2._total_updates == 2
            preds1 = mk.predict_next_topics(["A"], n=3)
            preds2 = mk2.predict_next_topics(["A"], n=3)
            assert [t for t, _ in preds1] == [t for t, _ in preds2]
        finally:
            os.unlink(path)

    def test_load_nonexistent_returns_false(self):
        from core.moltbook_retrieval import MarkovKnowledgeChain
        mk = MarkovKnowledgeChain()
        assert mk.load("/nonexistent/path.json") is False

    def test_get_stats(self):
        from core.moltbook_retrieval import MarkovKnowledgeChain
        mk = MarkovKnowledgeChain()
        mk.update(["A", "B", "C"])
        stats = mk.get_stats()
        assert stats['total_updates'] == 1
        assert stats['unique_topics'] > 0


class TestSpeculativeRetrieval:
    """Tests for SpeculativeRetrieval."""

    def test_init(self):
        from core.moltbook_retrieval import SpeculativeRetrieval
        sr = SpeculativeRetrieval()
        assert sr.hit_rate == 0.0

    def test_prefetch_no_deps(self):
        from core.moltbook_retrieval import SpeculativeRetrieval
        sr = SpeculativeRetrieval()
        result = sr.prefetch(["topic"])
        assert result == []

    def test_prefetch_with_markov_and_moltbook(self):
        from core.moltbook_retrieval import SpeculativeRetrieval, MarkovKnowledgeChain
        store = MoltbookStore()
        store.add_entry("testing best practices")
        store.add_entry("deployment pipeline")
        markov = MarkovKnowledgeChain(moltbook=store)
        markov.update(["python", "testing", "deployment"])
        sr = SpeculativeRetrieval(markov=markov, moltbook=store)
        result = sr.prefetch(["python"])
        assert isinstance(result, list)

    def test_check_hit_miss(self):
        from core.moltbook_retrieval import SpeculativeRetrieval
        sr = SpeculativeRetrieval()
        assert sr.check_hit("nonexistent_id") is False
        assert sr._total_misses == 1

    def test_clear_buffer(self):
        from core.moltbook_retrieval import SpeculativeRetrieval
        sr = SpeculativeRetrieval()
        sr._speculative_buffer["test_id"] = "test_entry"
        sr.clear_buffer()
        assert len(sr._speculative_buffer) == 0

    def test_get_stats(self):
        from core.moltbook_retrieval import SpeculativeRetrieval
        sr = SpeculativeRetrieval()
        stats = sr.get_stats()
        assert stats['buffer_size'] == 0
        assert stats['hit_rate'] == 0.0


class TestContextPredictor:
    """Tests for ContextPredictor."""

    def test_init(self):
        from core.moltbook_retrieval import ContextPredictor
        cp = ContextPredictor()
        assert cp._total_predictions == 0

    def test_predict_basic(self):
        from core.moltbook_retrieval import ContextPredictor
        cp = ContextPredictor()
        result = cp.predict({'topics': ['python'], 'intent': 'learn'})
        assert 'predicted_topics' in result
        assert 'confidence' in result
        assert result['confidence'] == 0.0  # No markov, no predictions

    def test_predict_with_markov(self):
        from core.moltbook_retrieval import ContextPredictor, MarkovKnowledgeChain
        markov = MarkovKnowledgeChain()
        markov.update(["python", "testing", "deploy"])
        cp = ContextPredictor(markov=markov)
        result = cp.predict({'topics': ['python']})
        assert len(result['predicted_topics']) > 0

    def test_record_actual(self):
        from core.moltbook_retrieval import ContextPredictor
        cp = ContextPredictor()
        cp.predict({'topics': ['A']})
        error = cp.record_actual(['A'])
        assert 0.0 <= error <= 1.0

    def test_accuracy(self):
        from core.moltbook_retrieval import ContextPredictor
        cp = ContextPredictor()
        assert cp.accuracy == 0.0  # No predictions yet

    def test_get_stats(self):
        from core.moltbook_retrieval import ContextPredictor
        cp = ContextPredictor()
        stats = cp.get_stats()
        assert 'total_predictions' in stats
        assert 'accuracy' in stats


class TestRelevanceScorer:
    """Tests for RelevanceScorer."""

    def test_init(self):
        from core.moltbook_retrieval import RelevanceScorer
        rs = RelevanceScorer()
        assert rs._total_scored == 0
        assert 'semantic' in rs._weights

    def test_score_empty(self):
        from core.moltbook_retrieval import RelevanceScorer
        rs = RelevanceScorer()
        result = rs.score([], "test")
        assert result == []

    def test_score_entries(self):
        from core.moltbook_retrieval import RelevanceScorer
        store = MoltbookStore()
        e1 = store.add_entry("Python programming")
        e2 = store.add_entry("Java programming")
        rs = RelevanceScorer()
        scored = rs.score([e1, e2], "Python")
        assert len(scored) == 2
        assert rs._total_scored == 2

    def test_score_with_custom_weights(self):
        from core.moltbook_retrieval import RelevanceScorer
        custom = {'semantic': 0.5, 'activation': 0.2, 'recency': 0.1,
                  'emotional': 0.1, 'confidence': 0.1}
        rs = RelevanceScorer(weights=custom)
        assert rs._weights['semantic'] == 0.5

    def test_get_stats(self):
        from core.moltbook_retrieval import RelevanceScorer
        rs = RelevanceScorer()
        stats = rs.get_stats()
        assert stats['total_scored'] == 0
        assert 'weights' in stats


class TestKnowledgeDecay:
    """Tests for KnowledgeDecay."""

    def test_init(self):
        from core.moltbook_retrieval import KnowledgeDecay
        kd = KnowledgeDecay()
        assert kd._base_decay_rate == 0.001

    def test_apply_decay(self):
        from core.moltbook_retrieval import KnowledgeDecay
        store = MoltbookStore()
        store.add_entry("old knowledge")
        kd = KnowledgeDecay(moltbook=store)
        result = kd.apply_decay()
        assert isinstance(result, dict)
        assert 'decayed' in result

    def test_consolidate(self):
        from core.moltbook_retrieval import KnowledgeDecay
        store = MoltbookStore()
        for i in range(5):
            store.add_entry(f"entry {i}")
        kd = KnowledgeDecay(moltbook=store)
        result = kd.consolidate()
        assert isinstance(result, dict)
        assert 'merged' in result or 'removed' in result


class TestAttentionDrivenRetrieval:
    """Tests for AttentionDrivenRetrieval."""

    def test_init(self):
        from core.moltbook_retrieval import AttentionDrivenRetrieval
        adr = AttentionDrivenRetrieval()
        assert adr._base_top_k == 7

    def test_get_retrieval_params_default(self):
        from core.moltbook_retrieval import AttentionDrivenRetrieval
        adr = AttentionDrivenRetrieval()
        params = adr.get_retrieval_params()
        assert params['top_k'] == 7
        assert 0.0 <= params['threshold'] <= 1.0
        assert 0.0 <= params['breadth'] <= 1.0

    def test_get_retrieval_params_custom_base(self):
        from core.moltbook_retrieval import AttentionDrivenRetrieval
        adr = AttentionDrivenRetrieval(base_top_k=10)
        params = adr.get_retrieval_params()
        assert params['top_k'] == 10


# ═════════════════════════════════════════════════════════════
# Thinker Layer Tests
# ═════════════════════════════════════════════════════════════

class TestThreadOutput:
    """Tests for ThreadOutput dataclass."""

    def test_defaults(self):
        from core.moltbook_thinker import ThreadOutput
        t = ThreadOutput()
        assert t.thread_name == ""
        assert t.confidence == 0.5

    def test_to_dict(self):
        from core.moltbook_thinker import ThreadOutput
        t = ThreadOutput(thread_name="goal", content="help user", confidence=0.8)
        d = t.to_dict()
        assert d['thread'] == "goal"
        assert d['confidence'] == 0.8


class TestUnifiedThought:
    """Tests for UnifiedThought dataclass."""

    def test_defaults(self):
        from core.moltbook_thinker import UnifiedThought
        ut = UnifiedThought()
        assert ut.narrative == ""
        assert ut.quality_passed is True
        assert ut.confidence == 0.5

    def test_to_dict(self):
        from core.moltbook_thinker import UnifiedThought
        ut = UnifiedThought(
            narrative="I think about Python",
            confidence=0.8,
            coherence=0.7,
            key_facts=["Python is versatile"],
        )
        d = ut.to_dict()
        assert d['narrative'] == "I think about Python"
        assert d['confidence'] == 0.8
        assert len(d['key_facts']) == 1
        assert 'threads' in d


class TestGoalThread:
    """Tests for GoalThread."""

    def test_init(self):
        from core.moltbook_thinker import GoalThread
        gt = GoalThread()
        # No dependencies, should init fine

    def test_think_no_deps(self):
        from core.moltbook_thinker import GoalThread, ThreadOutput
        gt = GoalThread()
        result = gt.think("How do I sort a list in Python?")
        assert isinstance(result, ThreadOutput)
        assert result.thread_name == "goal"
        assert "sort a list" in result.content or "No specific" in result.content

    def test_think_with_context(self):
        from core.moltbook_thinker import GoalThread
        gt = GoalThread()
        result = gt.think("Help me with machine learning")
        assert result.processing_time_ms >= 0
        assert result.confidence > 0


class TestReasoningThread:
    """Tests for ReasoningThread."""

    def test_init(self):
        from core.moltbook_thinker import ReasoningThread
        rt = ReasoningThread()

    def test_think_no_entries(self):
        from core.moltbook_thinker import ReasoningThread, ThreadOutput
        rt = ReasoningThread()
        result = rt.think("What is Python?")
        assert isinstance(result, ThreadOutput)
        assert result.thread_name == "reasoning"
        assert result.confidence == 0.3  # Low without facts

    def test_think_with_entries(self):
        from core.moltbook_thinker import ReasoningThread
        rt = ReasoningThread()
        store = MoltbookStore()
        e1 = store.add_entry("Python is a programming language")
        e2 = store.add_entry("Python supports OOP")
        result = rt.think("What is Python?", moltbook_entries=[e1, e2])
        assert result.confidence > 0.3  # Higher with entries
        assert len(result.key_points) > 0


class TestMemoryThread:
    """Tests for MemoryThread."""

    def test_init(self):
        from core.moltbook_thinker import MemoryThread
        mt = MemoryThread()

    def test_think_no_deps(self):
        from core.moltbook_thinker import MemoryThread, ThreadOutput
        mt = MemoryThread()
        result = mt.think("Tell me about Python")
        assert isinstance(result, ThreadOutput)
        assert result.thread_name == "memory"


class TestConfidenceEstimator:
    """Tests for ConfidenceEstimator."""

    def test_init(self):
        from core.moltbook_thinker import ConfidenceEstimator
        ce = ConfidenceEstimator()

    def test_estimate_from_threads(self):
        from core.moltbook_thinker import ConfidenceEstimator, ThreadOutput
        ce = ConfidenceEstimator()
        outputs = [
            ThreadOutput(thread_name="goal", confidence=0.8),
            ThreadOutput(thread_name="reasoning", confidence=0.6),
            ThreadOutput(thread_name="memory", confidence=0.4),
        ]
        conf = ce.estimate(outputs, [])
        assert 0.0 <= conf <= 1.0


class TestThoughtQualityGate:
    """Tests for ThoughtQualityGate."""

    def test_init(self):
        from core.moltbook_thinker import ThoughtQualityGate
        gate = ThoughtQualityGate()

    def test_check_passes_normal(self):
        from core.moltbook_thinker import ThoughtQualityGate, UnifiedThought
        gate = ThoughtQualityGate()
        ut = UnifiedThought(
            narrative="A clear helpful response",
            confidence=0.7,
            coherence=0.8,
        )
        passed = gate.check(ut)
        assert passed is True

    def test_get_stats(self):
        from core.moltbook_thinker import ThoughtQualityGate
        gate = ThoughtQualityGate()
        stats = gate.get_stats()
        assert 'total_checked' in stats


class TestCognitiveController:
    """Tests for CognitiveController."""

    def test_init(self):
        from core.moltbook_thinker import CognitiveController
        cc = CognitiveController()

    def test_synthesize(self):
        from core.moltbook_thinker import CognitiveController, ThreadOutput, UnifiedThought
        cc = CognitiveController()
        outputs = [
            ThreadOutput(thread_name="goal", content="Help with Python",
                        key_points=["Python"], confidence=0.8),
            ThreadOutput(thread_name="reasoning", content="Python is versatile",
                        key_points=["versatile"], confidence=0.7,
                        source_ids=["entry_1"]),
            ThreadOutput(thread_name="memory", content="Used Python before",
                        confidence=0.5),
        ]
        result = cc.synthesize(outputs, confidence=0.7)
        assert isinstance(result, UnifiedThought)
        assert result.confidence == 0.7
        assert "goal" in result.narrative.lower() or result.goal_summary != ""

    def test_get_stats(self):
        from core.moltbook_thinker import CognitiveController
        cc = CognitiveController()
        stats = cc.get_stats()
        assert stats['total_syntheses'] == 0


class TestInternalMonologue:
    """Tests for InternalMonologue."""

    def test_init_no_deps(self):
        from core.moltbook_thinker import InternalMonologue
        im = InternalMonologue()

    def test_think_basic(self):
        from core.moltbook_thinker import InternalMonologue, UnifiedThought
        im = InternalMonologue()
        result = im.think("How do I use Python decorators?")
        assert isinstance(result, UnifiedThought)
        assert result.narrative != ""
        assert result.processing_time_ms >= 0

    def test_think_with_entries(self):
        from core.moltbook_thinker import InternalMonologue
        store = MoltbookStore()
        e1 = store.add_entry("Decorators wrap functions")
        e2 = store.add_entry("Use @decorator syntax")
        im = InternalMonologue()
        result = im.think("decorators", moltbook_entries=[e1, e2])
        assert result.confidence > 0  # Should have some confidence with entries

    def test_quality_gate_tracking(self):
        from core.moltbook_thinker import InternalMonologue
        im = InternalMonologue()
        im.think("test query")
        stats = im.get_stats()
        assert stats['total_thoughts'] == 1

    def test_get_stats(self):
        from core.moltbook_thinker import InternalMonologue
        im = InternalMonologue()
        stats = im.get_stats()
        assert 'total_thoughts' in stats
        assert 'pass_rate' in stats
        assert 'controller' in stats


# ═════════════════════════════════════════════════════════════
# Talker Layer Tests
# ═════════════════════════════════════════════════════════════

class TestResponsePlan:
    """Tests for ResponsePlan dataclass."""

    def test_defaults(self):
        from core.moltbook_talker import ResponsePlan
        plan = ResponsePlan()
        assert plan.response_type == "informative"
        assert plan.length == "medium"
        assert plan.tone == "neutral"
        assert plan.include_examples is False

    def test_custom(self):
        from core.moltbook_talker import ResponsePlan
        plan = ResponsePlan(
            response_type="technical",
            length="long",
            tone="formal",
            include_examples=True,
        )
        assert plan.response_type == "technical"
        assert plan.include_examples is True


class TestTalkerResponse:
    """Tests for TalkerResponse dataclass."""

    def test_defaults(self):
        from core.moltbook_talker import TalkerResponse
        r = TalkerResponse()
        assert r.text == ""
        assert r.confidence == 0.5

    def test_to_dict(self):
        from core.moltbook_talker import TalkerResponse
        r = TalkerResponse(text="Hello!", confidence=0.9, emotional_tone=0.5)
        d = r.to_dict()
        assert d['text'] == "Hello!"
        assert d['confidence'] == 0.9
        assert 'think_ms' in d
        assert 'speak_ms' in d


class TestPersonalityFilter:
    """Tests for PersonalityFilter."""

    def test_init(self):
        from core.moltbook_talker import PersonalityFilter
        pf = PersonalityFilter()
        assert pf._formality == 0.5
        assert pf._warmth == 0.6

    def test_determine_tone_neutral(self):
        from core.moltbook_talker import PersonalityFilter
        pf = PersonalityFilter()
        tone = pf.determine_tone("Hello, how are you?")
        assert tone in ["neutral", "warm", "formal", "technical"]

    def test_determine_tone_technical(self):
        from core.moltbook_talker import PersonalityFilter
        pf = PersonalityFilter()
        tone = pf.determine_tone("How do I fix this error in my API code?")
        assert tone == "technical"

    def test_determine_tone_empathetic(self):
        from core.moltbook_talker import PersonalityFilter
        pf = PersonalityFilter()
        tone = pf.determine_tone("I'm feeling bad", emotional_tone=-0.7)
        assert tone == "empathetic"

    def test_determine_tone_enthusiastic(self):
        from core.moltbook_talker import PersonalityFilter
        pf = PersonalityFilter()
        tone = pf.determine_tone("This is amazing!", emotional_tone=0.8)
        assert tone == "enthusiastic"

    def test_determine_length(self):
        from core.moltbook_talker import PersonalityFilter
        pf = PersonalityFilter()
        assert pf.determine_length(0.1) == "short"
        assert pf.determine_length(0.5) == "medium"
        assert pf.determine_length(0.9) == "long"

    def test_determine_length_user_preference(self):
        from core.moltbook_talker import PersonalityFilter
        pf = PersonalityFilter()
        assert pf.determine_length(0.1, user_preference="long") == "long"

    def test_create_plan(self):
        from core.moltbook_talker import PersonalityFilter, ResponsePlan
        pf = PersonalityFilter()
        plan = pf.create_plan("How do I debug this code?", confidence=0.4, complexity=0.7)
        assert isinstance(plan, ResponsePlan)
        assert plan.include_caveats is True  # Low confidence
        assert plan.include_examples is True  # High complexity

    def test_create_plan_list_structure(self):
        from core.moltbook_talker import PersonalityFilter
        pf = PersonalityFilter()
        plan = pf.create_plan("Give me a list of steps to deploy")
        assert plan.structure == "list"

    def test_get_state(self):
        from core.moltbook_talker import PersonalityFilter
        pf = PersonalityFilter()
        state = pf.get_state()
        assert 'formality' in state
        assert 'warmth' in state
        assert 'verbosity' in state


class TestHumanLikeTransformer:
    """Tests for HumanLikeTransformer."""

    def test_init(self):
        from core.moltbook_talker import HumanLikeTransformer
        ht = HumanLikeTransformer()
        assert 'low' in ht._hedges
        assert 'high' in ht._hedges

    def test_transform_empty(self):
        from core.moltbook_talker import HumanLikeTransformer
        ht = HumanLikeTransformer()
        result = ht.transform("")
        assert result == ""

    def test_transform_high_confidence_no_hedge(self):
        from core.moltbook_talker import HumanLikeTransformer
        ht = HumanLikeTransformer()
        result = ht.transform("Python is a programming language.", confidence=0.9)
        # High confidence should not add hedging (empty strings in hedges['high'])
        assert "Python" in result or "programming" in result

    def test_transform_low_confidence_adds_hedge(self):
        from core.moltbook_talker import HumanLikeTransformer
        ht = HumanLikeTransformer()
        # Run multiple times since hedge is random
        hedged = False
        for _ in range(10):
            result = ht.transform("The answer is 42.", confidence=0.2)
            if result != "The answer is 42.":
                hedged = True
                break
        assert hedged is True  # Should have added a hedge at least once

    def test_add_caveat_low_confidence(self):
        from core.moltbook_talker import HumanLikeTransformer
        ht = HumanLikeTransformer()
        result = ht.add_caveat("The answer is 42.", confidence=0.2)
        assert "not fully confident" in result

    def test_add_caveat_high_confidence(self):
        from core.moltbook_talker import HumanLikeTransformer
        ht = HumanLikeTransformer()
        result = ht.add_caveat("The answer is 42.", confidence=0.8)
        assert result == "The answer is 42."  # No caveat added

    def test_add_followup(self):
        from core.moltbook_talker import HumanLikeTransformer
        ht = HumanLikeTransformer()
        result = ht.add_followup("Some text.", "context")
        assert result == "Some text."  # Current implementation returns as-is


class TestResponseStructurer:
    """Tests for ResponseStructurer."""

    def test_init(self):
        from core.moltbook_talker import ResponseStructurer
        rs = ResponseStructurer()

    def test_structure_short(self):
        from core.moltbook_talker import ResponseStructurer, ResponsePlan
        rs = ResponseStructurer()
        plan = ResponsePlan(length="short")
        result = rs.structure({'main': 'Hello world'}, plan)
        assert result == "Hello world"

    def test_structure_medium_with_examples(self):
        from core.moltbook_talker import ResponseStructurer, ResponsePlan
        rs = ResponseStructurer()
        plan = ResponsePlan(length="medium")
        result = rs.structure(
            {'main': 'Main content', 'examples': 'Example 1'},
            plan
        )
        assert "Main content" in result
        assert "Example 1" in result

    def test_structure_long_with_all_parts(self):
        from core.moltbook_talker import ResponseStructurer, ResponsePlan
        rs = ResponseStructurer()
        plan = ResponsePlan(length="long", include_followup=True)
        result = rs.structure(
            {'main': 'Main', 'examples': 'Ex', 'caveats': 'Caveat', 'followup': 'More?'},
            plan
        )
        assert "Main" in result
        assert "Ex" in result
        assert "Caveat" in result
        assert "More?" in result

    def test_structure_empty_parts_filtered(self):
        from core.moltbook_talker import ResponseStructurer, ResponsePlan
        rs = ResponseStructurer()
        plan = ResponsePlan(length="long")
        result = rs.structure({'main': 'Only main', 'examples': '', 'caveats': ''}, plan)
        assert result == "Only main"  # Empty parts filtered out


class TestTalkerModule:
    """Tests for TalkerModule."""

    def test_init(self):
        from core.moltbook_talker import TalkerModule
        tm = TalkerModule()

    def test_speak_with_dict(self):
        from core.moltbook_talker import TalkerModule, TalkerResponse
        tm = TalkerModule()
        thought = {
            'narrative': 'Python is a versatile language used for many tasks.',
            'confidence': 0.8,
            'emotional_tone': 0.0,
            'key_facts': ['versatile', 'many tasks'],
            'source_entry_ids': ['e1'],
            'processing_time_ms': 5.0,
        }
        result = tm.speak(thought, context="What is Python?")
        assert isinstance(result, TalkerResponse)
        assert result.text != ""
        assert result.confidence == 0.8
        assert result.speaking_time_ms >= 0

    def test_speak_with_unified_thought(self):
        from core.moltbook_talker import TalkerModule
        from core.moltbook_thinker import UnifiedThought
        tm = TalkerModule()
        ut = UnifiedThought(
            narrative="I know about Python decorators.",
            confidence=0.7,
            key_facts=["decorators wrap functions"],
        )
        result = tm.speak(ut, context="Python decorators", complexity=0.6)
        assert result.text != ""

    def test_speak_low_confidence_adds_caveat(self):
        from core.moltbook_talker import TalkerModule
        tm = TalkerModule()
        thought = {
            'narrative': 'I am not sure about quantum computing.',
            'confidence': 0.2,
            'emotional_tone': 0.0,
            'key_facts': [],
            'source_entry_ids': [],
            'processing_time_ms': 3.0,
        }
        result = tm.speak(thought, context="quantum computing")
        # Low confidence should include caveat
        assert "not fully confident" in result.text or result.response_plan.include_caveats

    def test_get_stats(self):
        from core.moltbook_talker import TalkerModule
        tm = TalkerModule()
        tm.speak({'narrative': 'test', 'confidence': 0.5}, context="test")
        stats = tm.get_stats()
        assert stats['total_responses'] == 1
        assert stats['avg_time_ms'] >= 0
        assert 'personality' in stats


# ═════════════════════════════════════════════════════════════
# Integration Tests
# ═════════════════════════════════════════════════════════════

class TestThinkingRetrievalIntegration:
    """Integration tests combining Thinking + Retrieval layers."""

    def test_markov_feeds_speculative(self):
        """Train Markov → predict → prefetch entries."""
        from core.moltbook_retrieval import MarkovKnowledgeChain, SpeculativeRetrieval
        store = MoltbookStore()
        store.add_entry("deployment pipeline automation")
        store.add_entry("testing frameworks comparison")
        markov = MarkovKnowledgeChain(moltbook=store)
        for _ in range(3):
            markov.update(["python", "testing", "deployment"])
        sr = SpeculativeRetrieval(markov=markov, moltbook=store)
        prefetched = sr.prefetch(["python"])
        assert isinstance(prefetched, list)

    def test_thought_stream_to_buffer_to_workspace(self):
        """ThoughtStream → ThoughtBuffer → get_workspace."""
        from core.moltbook_thinking import ThoughtStream, ThoughtBuffer
        store = MoltbookStore()
        store.add_entry("neural networks deep learning")
        buf = ThoughtBuffer(workspace_size=3)
        ts = ThoughtStream(moltbook=store, buffer=buf)
        ts.set_context("deep learning")
        # Generate a few ticks
        for _ in range(3):
            ts.background_tick()
        ws = buf.get_workspace("deep learning")
        assert isinstance(ws, list)


class TestThinkerTalkerIntegration:
    """Integration tests combining Thinker + Talker."""

    def test_full_think_speak_pipeline(self):
        """InternalMonologue.think() → TalkerModule.speak()."""
        from core.moltbook_thinker import InternalMonologue
        from core.moltbook_talker import TalkerModule, TalkerResponse
        im = InternalMonologue()
        tm = TalkerModule()
        # Think
        thought = im.think("How do I use Python list comprehensions?")
        # Speak
        response = tm.speak(thought, context="list comprehensions", complexity=0.5)
        assert isinstance(response, TalkerResponse)
        assert response.text != ""
        assert response.total_time_ms >= 0

    def test_full_pipeline_with_moltbook_entries(self):
        """Entries → InternalMonologue → TalkerModule."""
        from core.moltbook_thinker import InternalMonologue
        from core.moltbook_talker import TalkerModule
        store = MoltbookStore()
        e1 = store.add_entry("List comprehensions provide concise syntax")
        e2 = store.add_entry("Use [expr for item in iterable] pattern")
        im = InternalMonologue(moltbook=store)
        tm = TalkerModule()
        thought = im.think("list comprehensions", moltbook_entries=[e1, e2])
        response = tm.speak(thought, context="list comprehensions")
        assert response.text != ""
        assert response.confidence > 0

    def test_emotional_context_affects_response(self):
        """Negative emotional tone → empathetic response plan."""
        from core.moltbook_talker import TalkerModule
        tm = TalkerModule()
        thought = {
            'narrative': 'The user seems frustrated with debugging.',
            'confidence': 0.6,
            'emotional_tone': -0.7,
            'key_facts': [],
            'source_entry_ids': [],
            'processing_time_ms': 2.0,
        }
        response = tm.speak(thought, context="debugging frustration")
        assert response.response_plan.tone == "empathetic"
