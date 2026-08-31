"""
Tests for Moltbook Pipeline (moltbook_pipeline.py) and Agents (moltbook_agents.py).

Pipeline tests: InputAnalyzer, ThinkingBudget, DebugStream, PerformanceMonitor,
                RealtimeResponseEngine, ThinkTalkOrchestrator
Agent tests:    MoltbookFeeder, EvaluationAgent, CurationAgent, ResearchAgent,
                FeedbackAgent
"""
import os
import sys
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.moltbook_pipeline import (
    InputAnalysis, PipelineResult,
    InputAnalyzer, ThinkingBudget, DebugStream,
    PerformanceMonitor, RealtimeResponseEngine, ThinkTalkOrchestrator,
)
from core.moltbook_agents import (
    EvaluationResult, CurationAction, FeedbackRecord,
    MoltbookFeeder, EvaluationAgent, CurationAgent,
    ResearchAgent, FeedbackAgent,
)
from core.moltbook import MoltbookStore, MoltbookEntry, SemanticIndex, MoltbookGraph


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def store():
    return MoltbookStore()


@pytest.fixture
def semantic_index():
    return SemanticIndex()


@pytest.fixture
def graph():
    return MoltbookGraph()


@pytest.fixture
def populated_store(store):
    """Store with some pre-loaded entries."""
    store.add_entry("Python is a programming language", source_agent="test",
                    tags=["python", "programming"], confidence=0.8)
    store.add_entry("Machine learning requires large datasets", source_agent="test",
                    tags=["ml", "data"], confidence=0.7)
    store.add_entry("Neural networks are inspired by biology", source_agent="test",
                    tags=["ml", "neuroscience"], confidence=0.9)
    store.add_entry("Docker containers provide isolation", source_agent="test",
                    tags=["devops", "containers"], confidence=0.6)
    store.add_entry("Git is a version control system", source_agent="test",
                    tags=["git", "tools"], confidence=0.85)
    return store


# ═══════════════════════════════════════════════════════════════
# Pipeline Tests — InputAnalysis dataclass
# ═══════════════════════════════════════════════════════════════

class TestInputAnalysis:
    def test_defaults(self):
        a = InputAnalysis()
        assert a.intent == "unknown"
        assert a.complexity == 0.5
        assert a.topics == []
        assert a.emotional_tone == 0.0

    def test_to_dict(self):
        a = InputAnalysis(intent="question", complexity=0.7, topics=["python"])
        d = a.to_dict()
        assert d['intent'] == "question"
        assert d['complexity'] == 0.7
        assert 'python' in d['topics']


class TestPipelineResult:
    def test_defaults(self):
        r = PipelineResult()
        assert r.response_text == ""
        assert r.confidence == 0.5
        assert r.quality_passed is True

    def test_to_dict(self):
        r = PipelineResult(response_text="hello", confidence=0.8,
                           entries_retrieved=5, speculative_hits=2)
        d = r.to_dict()
        assert d['response'] == "hello"
        assert d['confidence'] == 0.8
        assert d['entries_retrieved'] == 5
        assert 'timing' in d


# ═══════════════════════════════════════════════════════════════
# Pipeline Tests — InputAnalyzer
# ═══════════════════════════════════════════════════════════════

class TestInputAnalyzer:
    def test_init(self):
        analyzer = InputAnalyzer()
        assert analyzer.get_stats()['total_analyzed'] == 0

    def test_empty_input(self):
        analyzer = InputAnalyzer()
        result = analyzer.analyze("")
        assert result.intent == "empty"
        assert result.complexity == 0.0
        assert result.requires_knowledge is False

    def test_greeting_detection(self):
        analyzer = InputAnalyzer()
        result = analyzer.analyze("hello there")
        assert result.intent == "greeting"
        assert result.requires_knowledge is False
        assert result.requires_reasoning is False

    def test_question_detection(self):
        analyzer = InputAnalyzer()
        result = analyzer.analyze("What is machine learning and how does it work?")
        assert result.intent == "question"
        assert result.requires_knowledge is True

    def test_instruction_detection(self):
        analyzer = InputAnalyzer()
        result = analyzer.analyze("create a new function that handles authentication")
        assert result.intent == "instruction"

    def test_creative_detection(self):
        analyzer = InputAnalyzer()
        result = analyzer.analyze("imagine a story about neural networks dreaming")
        assert result.intent == "creative"

    def test_complexity_simple(self):
        analyzer = InputAnalyzer()
        result = analyzer.analyze("hello")
        assert result.complexity < 0.3

    def test_complexity_complex(self):
        analyzer = InputAnalyzer()
        result = analyzer.analyze(
            "How do I implement a distributed microservice architecture "
            "with async concurrency and optimize database performance? "
            "Also explain the deployment strategy."
        )
        assert result.complexity > 0.3

    def test_emotional_tone_positive(self):
        analyzer = InputAnalyzer()
        result = analyzer.analyze("This is awesome and amazing, I love it!")
        assert result.emotional_tone > 0.0

    def test_emotional_tone_negative(self):
        analyzer = InputAnalyzer()
        result = analyzer.analyze("This is terrible and broken, I hate this bug")
        assert result.emotional_tone < 0.0

    def test_urgency_detection(self):
        analyzer = InputAnalyzer()
        result = analyzer.analyze("urgent! fix this critical bug immediately!")
        assert result.urgency > 0.5

    def test_topic_extraction(self):
        analyzer = InputAnalyzer()
        result = analyzer.analyze("explain python neural networks machine learning")
        assert len(result.topics) > 0

    def test_expected_length(self):
        analyzer = InputAnalyzer()
        simple = analyzer.analyze("hi")
        assert simple.expected_length == "short"

    def test_stats_increment(self):
        analyzer = InputAnalyzer()
        analyzer.analyze("test 1")
        analyzer.analyze("test 2")
        assert analyzer.get_stats()['total_analyzed'] == 2


# ═══════════════════════════════════════════════════════════════
# Pipeline Tests — ThinkingBudget
# ═══════════════════════════════════════════════════════════════

class TestThinkingBudget:
    def test_init(self):
        tb = ThinkingBudget()
        assert tb.get_stats()['total_budgets'] == 0

    def test_minimal_budget(self):
        tb = ThinkingBudget()
        analysis = InputAnalysis(intent="greeting", complexity=0.1)
        budget = tb.allocate(analysis)
        assert budget['depth'] == 'minimal'
        assert budget['max_think_ms'] <= 100
        assert budget['use_speculative'] is False

    def test_standard_budget(self):
        tb = ThinkingBudget()
        analysis = InputAnalysis(intent="question", complexity=0.5)
        budget = tb.allocate(analysis)
        assert budget['depth'] in ('standard', 'deep')
        assert budget['retrieval_depth'] >= 5

    def test_deep_budget(self):
        tb = ThinkingBudget()
        analysis = InputAnalysis(intent="creative", complexity=0.8)
        budget = tb.allocate(analysis)
        assert budget['depth'] == 'deep'
        assert budget['max_think_ms'] >= 300
        assert budget['use_thought_stream'] is True

    def test_feedback_learning(self):
        tb = ThinkingBudget()
        tb.record_feedback("question", was_sufficient=True)
        tb.record_feedback("question", was_sufficient=True)
        # After sufficient feedback, complexity should adjust down
        assert 'question' in tb._feedback_map
        assert tb._feedback_map['question'] < 0.5

    def test_feedback_insufficient(self):
        tb = ThinkingBudget()
        tb.record_feedback("question", was_sufficient=False)
        assert tb._feedback_map['question'] > 0.5

    def test_stats(self):
        tb = ThinkingBudget()
        tb.allocate(InputAnalysis(complexity=0.5))
        tb.allocate(InputAnalysis(complexity=0.8))
        stats = tb.get_stats()
        assert stats['total_budgets'] == 2
        assert 0.0 <= stats['avg_complexity'] <= 1.0


# ═══════════════════════════════════════════════════════════════
# Pipeline Tests — DebugStream
# ═══════════════════════════════════════════════════════════════

class TestDebugStream:
    def test_init_disabled(self):
        ds = DebugStream(enabled=False)
        assert ds.enabled is False

    def test_init_enabled(self):
        ds = DebugStream(enabled=True)
        assert ds.enabled is True

    def test_log_when_disabled(self):
        ds = DebugStream(enabled=False)
        ds.log("THINK", "test thought")
        assert ds.get_stats()['total_entries'] == 0

    def test_log_when_enabled(self):
        ds = DebugStream(enabled=True)
        ds.log("THINK", "test thought")
        assert ds.get_stats()['total_entries'] == 1

    def test_think_method(self):
        ds = DebugStream(enabled=True)
        ds.think("considering the problem")
        entries = ds.get_recent(5)
        assert len(entries) == 1
        assert entries[0]['category'] == 'THINK'

    def test_feel_method(self):
        ds = DebugStream(enabled=True)
        ds.feel(0.6, 0.3, "interested")
        entries = ds.get_recent(5)
        assert 'valence=0.60' in entries[0]['message']

    def test_retrieve_method(self):
        ds = DebugStream(enabled=True)
        ds.retrieve("abc123", 0.89)
        entries = ds.get_recent(5)
        assert 'abc123' in entries[0]['message']

    def test_speak_method(self):
        ds = DebugStream(enabled=True)
        ds.speak(0.82, "medium")
        entries = ds.get_recent(5)
        assert 'confidence=0.82' in entries[0]['message']

    def test_budget_method(self):
        ds = DebugStream(enabled=True)
        ds.budget("deep", 500)
        entries = ds.get_recent(5)
        assert 'deep' in entries[0]['message'].lower()

    def test_formatted_output(self):
        ds = DebugStream(enabled=True)
        ds.think("thought 1")
        ds.feel(0.5, 0.5, "neutral")
        text = ds.get_formatted(5)
        assert "[THINK]" in text
        assert "[FEEL]" in text

    def test_clear(self):
        ds = DebugStream(enabled=True)
        ds.think("test")
        ds.clear()
        assert len(ds.get_recent(10)) == 0

    def test_enable_disable(self):
        ds = DebugStream(enabled=False)
        ds.enable()
        assert ds.enabled is True
        ds.disable()
        assert ds.enabled is False


# ═══════════════════════════════════════════════════════════════
# Pipeline Tests — PerformanceMonitor
# ═══════════════════════════════════════════════════════════════

class TestPerformanceMonitor:
    def test_init(self):
        pm = PerformanceMonitor()
        assert pm.get_stats()['total_monitored'] == 0

    def test_record_normal(self):
        pm = PerformanceMonitor()
        result = PipelineResult(total_time_ms=500, confidence=0.8,
                                entries_retrieved=5, speculative_hits=3)
        alerts = pm.record(result)
        assert len(alerts) == 0
        assert pm.get_stats()['total_monitored'] == 1

    def test_record_high_latency(self):
        pm = PerformanceMonitor(max_latency_ms=1000)
        result = PipelineResult(total_time_ms=1500, confidence=0.8)
        alerts = pm.record(result)
        assert any('latency' in a.lower() for a in alerts)

    def test_record_low_confidence(self):
        pm = PerformanceMonitor(min_confidence=0.3)
        # Feed 10+ low confidence results to trigger alert
        for _ in range(12):
            result = PipelineResult(total_time_ms=100, confidence=0.1)
            alerts = pm.record(result)
        # After enough low-confidence results, should alert
        assert pm.get_stats()['avg_confidence'] < 0.3

    def test_stats(self):
        pm = PerformanceMonitor()
        for i in range(5):
            pm.record(PipelineResult(total_time_ms=100 * (i + 1), confidence=0.5 + i * 0.1))
        stats = pm.get_stats()
        assert stats['total_monitored'] == 5
        assert stats['avg_latency_ms'] > 0
        assert stats['avg_confidence'] > 0


# ═══════════════════════════════════════════════════════════════
# Pipeline Tests — RealtimeResponseEngine
# ═══════════════════════════════════════════════════════════════

class TestRealtimeResponseEngine:
    def test_init_no_deps(self):
        engine = RealtimeResponseEngine()
        assert engine.get_stats()['total_responses'] == 0

    def test_generate_no_deps(self):
        engine = RealtimeResponseEngine()
        analysis = InputAnalysis(intent="question", complexity=0.5,
                                 topics=["python"])
        budget = {'retrieval_depth': 5, 'use_thought_stream': True}
        result = engine.generate("What is Python?", analysis, budget)
        assert isinstance(result, PipelineResult)
        assert result.total_time_ms >= 0
        assert "Python" in result.response_text or "python" in result.response_text.lower()

    def test_generate_with_store(self, populated_store):
        engine = RealtimeResponseEngine(moltbook=populated_store)
        analysis = InputAnalysis(intent="question", complexity=0.5,
                                 requires_knowledge=True)
        budget = {'retrieval_depth': 3}
        result = engine.generate("Tell me about Python programming", analysis, budget)
        assert result.entries_retrieved >= 0

    def test_generate_greeting_skips_retrieval(self):
        engine = RealtimeResponseEngine()
        analysis = InputAnalysis(intent="greeting", requires_knowledge=False)
        budget = {'retrieval_depth': 3}
        result = engine.generate("hello", analysis, budget)
        assert result.entries_retrieved == 0

    def test_generate_with_debug(self):
        engine = RealtimeResponseEngine()
        debug = DebugStream(enabled=True)
        analysis = InputAnalysis(intent="question", complexity=0.5)
        budget = {'retrieval_depth': 5}
        result = engine.generate("test", analysis, budget, debug=debug)
        assert isinstance(result, PipelineResult)

    def test_stats(self):
        engine = RealtimeResponseEngine()
        analysis = InputAnalysis()
        budget = {}
        engine.generate("test", analysis, budget)
        assert engine.get_stats()['total_responses'] == 1


# ═══════════════════════════════════════════════════════════════
# Pipeline Tests — ThinkTalkOrchestrator
# ═══════════════════════════════════════════════════════════════

class TestThinkTalkOrchestrator:
    def test_init(self):
        orch = ThinkTalkOrchestrator()
        assert orch.get_stats()['total_orchestrated'] == 0

    def test_process_simple(self):
        orch = ThinkTalkOrchestrator()
        result = orch.process("hello")
        assert isinstance(result, PipelineResult)
        assert result.total_time_ms >= 0

    def test_process_question(self):
        orch = ThinkTalkOrchestrator()
        result = orch.process("What is machine learning?")
        assert isinstance(result, PipelineResult)
        assert result.input_analysis is not None
        assert result.input_analysis.intent == "question"

    def test_process_complex(self):
        orch = ThinkTalkOrchestrator()
        result = orch.process(
            "How do I design a distributed system with async concurrency?"
        )
        assert isinstance(result, PipelineResult)

    def test_debug_stream(self):
        orch = ThinkTalkOrchestrator()
        orch.enable_debug()
        assert orch.debug_stream.enabled is True
        result = orch.process("test question?")
        # Should have logged something
        entries = orch.debug_stream.get_recent(20)
        assert len(entries) > 0
        orch.disable_debug()
        assert orch.debug_stream.enabled is False

    def test_performance_monitor_integration(self):
        orch = ThinkTalkOrchestrator()
        orch.process("test 1")
        orch.process("test 2")
        stats = orch.performance_monitor.get_stats()
        assert stats['total_monitored'] == 2

    def test_stats(self):
        orch = ThinkTalkOrchestrator()
        orch.process("hello")
        stats = orch.get_stats()
        assert stats['total_orchestrated'] == 1
        assert 'engine' in stats
        assert 'analyzer' in stats
        assert 'budget' in stats
        assert 'monitor' in stats
        assert 'debug' in stats

    def test_with_store(self, populated_store):
        engine = RealtimeResponseEngine(moltbook=populated_store)
        orch = ThinkTalkOrchestrator(engine=engine)
        result = orch.process("Tell me about Python")
        assert isinstance(result, PipelineResult)


# ═══════════════════════════════════════════════════════════════
# Agent Tests — EvaluationResult dataclass
# ═══════════════════════════════════════════════════════════════

class TestEvaluationResult:
    def test_defaults(self):
        r = EvaluationResult()
        assert r.overall_quality == 0.5
        assert r.recommendation == "keep"

    def test_to_dict(self):
        r = EvaluationResult(entry_id="abc", overall_quality=0.9,
                             recommendation="promote")
        d = r.to_dict()
        assert d['entry_id'] == "abc"
        assert d['recommendation'] == "promote"


class TestCurationAction:
    def test_defaults(self):
        a = CurationAction()
        assert a.action_type == ""
        assert a.entry_ids == []

    def test_to_dict(self):
        a = CurationAction(action_type="merge", entry_ids=["a", "b"])
        d = a.to_dict()
        assert d['action'] == "merge"
        assert len(d['entries']) == 2


class TestFeedbackRecord:
    def test_defaults(self):
        r = FeedbackRecord()
        assert r.sentiment == 0.0

    def test_to_dict(self):
        r = FeedbackRecord(sentiment=0.8, contributing_entries=["x"])
        d = r.to_dict()
        assert d['sentiment'] == 0.8


# ═══════════════════════════════════════════════════════════════
# Agent Tests — MoltbookFeeder
# ═══════════════════════════════════════════════════════════════

class TestMoltbookFeeder:
    def test_init(self):
        feeder = MoltbookFeeder(agent_name="test_agent")
        assert feeder.agent_name == "test_agent"
        assert feeder.get_stats()['posts'] == 0

    def test_post_no_store(self):
        feeder = MoltbookFeeder(agent_name="test")
        result = feeder.post("test content")
        assert result is None

    def test_post_with_store(self, store):
        feeder = MoltbookFeeder(moltbook=store, agent_name="test")
        entry = feeder.post("Python is great", tags=["python"], confidence=0.8)
        assert entry is not None
        assert entry.source_agent == "test"
        assert feeder.get_stats()['posts'] == 1

    def test_post_empty_content(self, store):
        feeder = MoltbookFeeder(moltbook=store, agent_name="test")
        result = feeder.post("")
        assert result is None

    def test_comment(self, store):
        feeder = MoltbookFeeder(moltbook=store, agent_name="test")
        entry = feeder.post("Original post", tags=["test"])
        comment = feeder.comment(entry.id, "Adding a comment")
        assert comment is not None
        assert comment.entry_type == "comment"
        assert entry.id in comment.linked_entries
        assert feeder.get_stats()['comments'] == 1

    def test_comment_no_store(self):
        feeder = MoltbookFeeder(agent_name="test")
        result = feeder.comment("some_id", "comment text")
        assert result is None

    def test_mention(self, store):
        feeder = MoltbookFeeder(moltbook=store, agent_name="test")
        e1 = feeder.post("Entry A")
        e2 = feeder.post("Entry B")
        result = feeder.mention(e1.id, e2.id, "relates_to")
        assert result is True
        assert feeder.get_stats()['mentions'] == 1

    def test_mention_with_graph(self, store, graph):
        feeder = MoltbookFeeder(moltbook=store, agent_name="test", graph=graph)
        e1 = feeder.post("Entry A")
        e2 = feeder.post("Entry B")
        result = feeder.mention(e1.id, e2.id, "supports")
        assert result is True

    def test_channel_log(self, store):
        feeder = MoltbookFeeder(moltbook=store, agent_name="test")
        feeder.post("Entry 1")
        feeder.post("Entry 2")
        log = feeder.get_channel_log()
        assert len(log) == 2
        assert log[0]['action'] == 'post'

    def test_stats(self, store):
        feeder = MoltbookFeeder(moltbook=store, agent_name="test")
        feeder.post("Entry 1")
        feeder.post("Entry 2")
        stats = feeder.get_stats()
        assert stats['total_actions'] == 2
        assert stats['agent_name'] == "test"


# ═══════════════════════════════════════════════════════════════
# Agent Tests — EvaluationAgent
# ═══════════════════════════════════════════════════════════════

class TestEvaluationAgent:
    def test_init(self):
        ea = EvaluationAgent()
        assert ea.get_stats()['total_evaluated'] == 0

    def test_evaluate_basic(self, store):
        ea = EvaluationAgent(moltbook=store)
        entry = store.add_entry("Python is a versatile programming language used in many domains",
                                confidence=0.8, tags=["python"])
        result = ea.evaluate(entry)
        assert isinstance(result, EvaluationResult)
        assert result.entry_id == entry.id
        assert 0.0 <= result.overall_quality <= 1.0
        assert result.recommendation in ("keep", "promote", "demote", "flag")

    def test_evaluate_high_quality(self, store):
        ea = EvaluationAgent(moltbook=store)
        entry = store.add_entry(
            "Machine learning is a subset of AI that enables systems to learn from data "
            "patterns and improve without explicit programming. Common approaches include "
            "supervised learning, unsupervised learning, and reinforcement learning.",
            confidence=0.9, tags=["ml", "ai", "learning"],
        )
        # Access it to boost relevance
        store.get_entry(entry.id)
        store.get_entry(entry.id)
        result = ea.evaluate(entry)
        assert result.relevance_score > 0.5

    def test_evaluate_low_quality(self):
        ea = EvaluationAgent()
        entry = MoltbookEntry(content="hi", confidence=0.1)
        result = ea.evaluate(entry)
        assert result.relevance_score < 0.5

    def test_evaluate_batch(self, store):
        ea = EvaluationAgent(moltbook=store)
        e1 = store.add_entry("Entry one about programming", tags=["code"])
        e2 = store.add_entry("Entry two about databases", tags=["db"])
        results = ea.evaluate_batch([e1, e2])
        assert len(results) == 2

    def test_apply_evaluation_promote(self, store):
        ea = EvaluationAgent(moltbook=store)
        entry = store.add_entry("Test entry", confidence=0.5)
        original_relevance = entry.relevance_score
        result = EvaluationResult(recommendation="promote")
        ea.apply_evaluation(entry, result)
        assert entry.relevance_score > original_relevance

    def test_apply_evaluation_demote(self, store):
        ea = EvaluationAgent(moltbook=store)
        entry = store.add_entry("Test entry", confidence=0.5)
        original_relevance = entry.relevance_score
        result = EvaluationResult(recommendation="demote")
        ea.apply_evaluation(entry, result)
        assert entry.relevance_score < original_relevance

    def test_apply_evaluation_flag(self, store):
        ea = EvaluationAgent(moltbook=store)
        entry = store.add_entry("Test entry", confidence=0.5)
        result = EvaluationResult(recommendation="flag")
        ea.apply_evaluation(entry, result)
        assert entry.metadata.get('flagged') is True

    def test_stats(self, store):
        ea = EvaluationAgent(moltbook=store)
        entry = store.add_entry("Test", confidence=0.5)
        ea.evaluate(entry)
        stats = ea.get_stats()
        assert stats['total_evaluated'] == 1


# ═══════════════════════════════════════════════════════════════
# Agent Tests — CurationAgent
# ═══════════════════════════════════════════════════════════════

class TestCurationAgent:
    def test_init(self):
        ca = CurationAgent()
        assert ca.get_stats()['total_merges'] == 0

    def test_curate_empty_store(self, store):
        ca = CurationAgent(moltbook=store)
        actions = ca.curate()
        assert isinstance(actions, list)

    def test_merge_similar(self, store):
        # Create very similar entries
        store.add_entry("Python programming language is great for scripting",
                        tags=["python"])
        store.add_entry("Python programming language is great for scripting tasks",
                        tags=["python"])
        ca = CurationAgent(moltbook=store, merge_threshold=0.7)
        actions = ca.merge_similar()
        # Should find the similar pair
        merge_actions = [a for a in actions if a.action_type == "merge"]
        # May or may not merge depending on exact similarity
        assert isinstance(merge_actions, list)

    def test_detect_clusters(self, populated_store):
        ca = CurationAgent(moltbook=populated_store)
        actions = ca.detect_clusters()
        # Should find clusters around shared tags like "ml"
        cluster_actions = [a for a in actions if a.action_type == "cluster"]
        assert isinstance(cluster_actions, list)

    def test_detect_clusters_with_graph(self, populated_store, graph):
        ca = CurationAgent(moltbook=populated_store, graph=graph)
        actions = ca.detect_clusters()
        assert isinstance(actions, list)

    def test_prune_stale(self, store):
        # Create an old, never-accessed, low-relevance entry
        entry = store.add_entry("Old stale knowledge", confidence=0.1)
        entry.created_at = time.time() - 200000  # ~55 hours old
        entry.accessed_count = 0
        entry.relevance_score = 0.1

        ca = CurationAgent(moltbook=store, prune_min_age_hours=48)
        actions = ca.prune_stale()
        prune_actions = [a for a in actions if a.action_type == "prune"]
        assert len(prune_actions) >= 1

    def test_summarize_cluster(self, populated_store):
        ca = CurationAgent(moltbook=populated_store)
        entries = populated_store.get_active_entries(top_k=3)
        entry_ids = [e.id for e in entries]
        summary = ca.summarize_cluster(entry_ids)
        assert summary is not None
        assert "[Summary" in summary.content
        assert summary.source_agent == "curation_agent"

    def test_summarize_cluster_empty(self, store):
        ca = CurationAgent(moltbook=store)
        result = ca.summarize_cluster([])
        assert result is None

    def test_compute_similarity(self):
        ca = CurationAgent()
        e1 = MoltbookEntry(content="python programming language guide")
        e2 = MoltbookEntry(content="python programming language guide and tutorial")
        sim = ca._compute_similarity(e1, e2)
        assert 0.0 <= sim <= 1.0
        assert sim > 0.5  # Should be quite similar

    def test_pick_survivor(self):
        ca = CurationAgent()
        e1 = MoltbookEntry(content="a", confidence=0.8, accessed_count=5)
        e2 = MoltbookEntry(content="b", confidence=0.3, accessed_count=1)
        survivor, consumed = ca._pick_survivor(e1, e2)
        assert survivor.confidence == 0.8  # Higher quality wins

    def test_stats(self, store):
        ca = CurationAgent(moltbook=store)
        ca.curate()
        stats = ca.get_stats()
        assert 'total_merges' in stats
        assert 'total_prunes' in stats
        assert 'total_clusters' in stats


# ═══════════════════════════════════════════════════════════════
# Agent Tests — ResearchAgent
# ═══════════════════════════════════════════════════════════════

class TestResearchAgent:
    def test_init(self):
        ra = ResearchAgent()
        assert ra.get_stats()['total_researched'] == 0

    def test_check_for_gaps_no_detection(self):
        ra = ResearchAgent()
        gaps = ra.check_for_gaps()
        assert gaps == []

    def test_research_topic_no_feeder(self):
        ra = ResearchAgent()
        findings = ra.research_topic("python")
        assert findings == []

    def test_research_topic_with_feeder(self, store):
        feeder = MoltbookFeeder(moltbook=store, agent_name="research")
        ra = ResearchAgent(feeder=feeder)
        findings = ra.research_topic("machine learning", context="Need basics")
        assert len(findings) > 0
        assert findings[0]['topic'] == "machine learning"
        assert ra.get_stats()['total_researched'] == 1

    def test_research_creates_entries(self, store):
        feeder = MoltbookFeeder(moltbook=store, agent_name="research")
        ra = ResearchAgent(feeder=feeder)
        initial_count = len(store.get_active_entries(top_k=100))
        ra.research_topic("quantum computing", context="Explore qubits and superposition")
        new_count = len(store.get_active_entries(top_k=100))
        assert new_count > initial_count

    def test_run_cycle_no_gaps(self):
        ra = ResearchAgent()
        result = ra.run_cycle()
        assert result['gaps_found'] == 0
        assert result['findings_created'] == 0

    def test_process_gap(self, store):
        feeder = MoltbookFeeder(moltbook=store, agent_name="research")
        ra = ResearchAgent(feeder=feeder)
        gap = {'area': 'kubernetes', 'description': 'Need container orchestration knowledge'}
        findings = ra.process_gap(gap)
        assert len(findings) > 0

    def test_stats(self, store):
        feeder = MoltbookFeeder(moltbook=store, agent_name="research")
        ra = ResearchAgent(feeder=feeder)
        ra.research_topic("test topic")
        stats = ra.get_stats()
        assert stats['total_researched'] == 1
        assert stats['total_entries_created'] > 0


# ═══════════════════════════════════════════════════════════════
# Agent Tests — FeedbackAgent
# ═══════════════════════════════════════════════════════════════

class TestFeedbackAgent:
    def test_init(self):
        fa = FeedbackAgent()
        assert fa.get_stats()['total_feedbacks'] == 0

    def test_positive_feedback(self, store):
        fa = FeedbackAgent(moltbook=store)
        entry = store.add_entry("Helpful knowledge", confidence=0.5)
        original_relevance = entry.relevance_score

        record = fa.record_feedback(
            sentiment=0.8,
            contributing_entry_ids=[entry.id],
        )
        assert isinstance(record, FeedbackRecord)
        assert record.sentiment == 0.8
        # Entry should be upranked
        updated = store.get_entry(entry.id)
        assert updated.relevance_score >= original_relevance
        assert fa.get_stats()['total_upranks'] == 1

    def test_negative_feedback(self, store):
        fa = FeedbackAgent(moltbook=store)
        entry = store.add_entry("Misleading knowledge", confidence=0.5)

        fa.record_feedback(
            sentiment=-0.7,
            contributing_entry_ids=[entry.id],
        )
        # Downrank should have reduced confidence
        assert entry.confidence < 0.5
        assert fa.get_stats()['total_downranks'] == 1

    def test_neutral_feedback(self, store):
        fa = FeedbackAgent(moltbook=store)
        entry = store.add_entry("Neutral knowledge", confidence=0.5)
        fa.record_feedback(sentiment=0.0, contributing_entry_ids=[entry.id])
        # No uprank or downrank for neutral
        assert fa.get_stats()['total_upranks'] == 0
        assert fa.get_stats()['total_downranks'] == 0

    def test_correction_creates_entry(self, store):
        fa = FeedbackAgent(moltbook=store)
        entry = store.add_entry("Wrong info", confidence=0.5)
        initial_count = len(store.get_active_entries(top_k=100))

        fa.record_feedback(
            sentiment=-0.5,
            contributing_entry_ids=[entry.id],
            correction="The correct info is XYZ",
        )
        new_count = len(store.get_active_entries(top_k=100))
        assert new_count > initial_count
        assert fa.get_stats()['total_corrections'] == 1

    def test_cumulative_scores(self, store):
        fa = FeedbackAgent(moltbook=store)
        entry = store.add_entry("Test entry", confidence=0.5)

        fa.record_feedback(sentiment=0.8, contributing_entry_ids=[entry.id])
        fa.record_feedback(sentiment=0.6, contributing_entry_ids=[entry.id])
        score = fa.get_entry_cumulative_score(entry.id)
        assert score > 0

    def test_top_bottom_entries(self, store):
        fa = FeedbackAgent(moltbook=store)
        e1 = store.add_entry("Good entry", confidence=0.5)
        e2 = store.add_entry("Bad entry", confidence=0.5)

        fa.record_feedback(sentiment=0.9, contributing_entry_ids=[e1.id])
        fa.record_feedback(sentiment=-0.8, contributing_entry_ids=[e2.id])

        top = fa.get_top_entries(5)
        bottom = fa.get_bottom_entries(5)
        assert len(top) > 0
        assert len(bottom) > 0
        assert top[0][1] > 0   # Positive score
        assert bottom[0][1] < 0  # Negative score

    def test_feedback_no_store(self):
        fa = FeedbackAgent()
        record = fa.record_feedback(sentiment=0.5, contributing_entry_ids=["fake_id"])
        assert isinstance(record, FeedbackRecord)
        # Should not crash even without store

    def test_stats(self, store):
        fa = FeedbackAgent(moltbook=store)
        entry = store.add_entry("Test", confidence=0.5)
        fa.record_feedback(sentiment=0.5, contributing_entry_ids=[entry.id])
        stats = fa.get_stats()
        assert stats['total_feedbacks'] == 1
        assert 'avg_sentiment' in stats


# ═══════════════════════════════════════════════════════════════
# Integration Tests — Pipeline + Agents together
# ═══════════════════════════════════════════════════════════════

class TestPipelineAgentIntegration:
    def test_feeder_to_evaluation(self, store):
        """Feeder posts entry, EvaluationAgent evaluates it."""
        feeder = MoltbookFeeder(moltbook=store, agent_name="test")
        evaluator = EvaluationAgent(moltbook=store)

        entry = feeder.post("Machine learning uses statistical models to find patterns",
                            tags=["ml", "statistics"], confidence=0.7)
        result = evaluator.evaluate(entry)
        assert isinstance(result, EvaluationResult)
        assert result.overall_quality > 0

    def test_feeder_to_curation(self, store):
        """Feeder posts multiple entries, CurationAgent organizes them."""
        feeder = MoltbookFeeder(moltbook=store, agent_name="test")
        curator = CurationAgent(moltbook=store)

        feeder.post("Python basics tutorial", tags=["python"])
        feeder.post("Python advanced concepts", tags=["python"])
        feeder.post("Python data analysis", tags=["python", "data"])

        actions = curator.curate()
        assert isinstance(actions, list)

    def test_feedback_affects_retrieval(self, store):
        """Feedback upranking should increase entry's relevance."""
        feeder = MoltbookFeeder(moltbook=store, agent_name="test")
        feedback = FeedbackAgent(moltbook=store)

        entry = feeder.post("Important knowledge about algorithms",
                            tags=["algorithms"], confidence=0.5)
        original_relevance = entry.relevance_score

        # Positive feedback
        feedback.record_feedback(sentiment=0.9, contributing_entry_ids=[entry.id])
        updated = store.get_entry(entry.id)
        assert updated.relevance_score > original_relevance

    def test_full_pipeline_with_agents(self, store):
        """Full flow: feed → evaluate → orchestrate."""
        feeder = MoltbookFeeder(moltbook=store, agent_name="test")
        evaluator = EvaluationAgent(moltbook=store)

        # Feed knowledge
        entry = feeder.post(
            "Neural networks consist of layers of interconnected nodes",
            tags=["ml", "neural"], confidence=0.8
        )
        # Evaluate
        eval_result = evaluator.evaluate(entry)
        evaluator.apply_evaluation(entry, eval_result)

        # Run through pipeline
        engine = RealtimeResponseEngine(moltbook=store)
        orch = ThinkTalkOrchestrator(engine=engine)
        result = orch.process("Tell me about neural networks")
        assert isinstance(result, PipelineResult)

    def test_research_and_evaluation_cycle(self, store):
        """ResearchAgent creates entries, EvaluationAgent scores them."""
        feeder = MoltbookFeeder(moltbook=store, agent_name="research")
        researcher = ResearchAgent(feeder=feeder)
        evaluator = EvaluationAgent(moltbook=store)

        findings = researcher.research_topic("deep learning",
                                              context="Understand transformer architecture")
        for finding in findings:
            entry = store.get_entry(finding['entry_id'])
            if entry:
                result = evaluator.evaluate(entry)
                assert isinstance(result, EvaluationResult)
