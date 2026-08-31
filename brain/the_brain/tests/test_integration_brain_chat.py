"""Integration test: BrainChat with full pipeline wiring."""
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_full_brain_chat_integration():
    """Test BrainChat with MoltbookStore + Pipeline + Thalamus routing."""
    from core.moltbook import MoltbookStore, MoltbookGraph
    store = MoltbookStore(config={'similarity_threshold': 0.3})
    graph = MoltbookGraph()

    from core.moltbook_agents import MoltbookFeeder
    feeder = MoltbookFeeder(moltbook=store, agent_name='dashboard', graph=graph)
    feeder.post(content='AI is transforming information processing.', tags=[])
    feeder.post(content='Neural networks use interconnected nodes.', tags=[])

    from core.moltbook_pipeline import InputAnalyzer, KnowledgeAugmentor
    from core.moltbook_thinking import ThoughtStream
    from core.moltbook_thinker import InternalMonologue
    from core.moltbook_talker import TalkerModule

    analyzer = InputAnalyzer()
    thought_stream = ThoughtStream(moltbook=store)
    internal_monologue = InternalMonologue(moltbook=store)
    talker = TalkerModule()
    aug_feeder = MoltbookFeeder(moltbook=store, agent_name='augmentor', graph=graph)
    knowledge_augmentor = KnowledgeAugmentor(moltbook=store, feeder=aug_feeder)

    # Try L1 router
    l1_router = None
    try:
        from core.task_feature_router import TaskFeatureRouter
        l1_router = TaskFeatureRouter()
    except Exception:
        pass

    from core.brain_chat import BrainChat, ContinuousThinkingEngine

    ct = ContinuousThinkingEngine(
        thought_stream=thought_stream, moltbook=store,
        knowledge_augmentor=knowledge_augmentor, interval_ms=300,
    )
    ct.start()

    bc = BrainChat(
        task_feature_router=l1_router,
        continuous_thinking=ct,
        internal_monologue=internal_monologue,
        knowledge_augmentor=knowledge_augmentor,
        talker=talker,
        moltbook=store,
        input_analyzer=analyzer,
    )

    time.sleep(0.5)  # Let continuous thinking warm up

    # Test 1: Greeting
    r = bc.send('Hallo, wer bist du?')
    assert 'Tahlamus' in r.response_text
    assert r.confidence == 0.95
    assert r.task_type == 'greeting'
    assert len(r.thought_trace) >= 1

    # Test 2: Question (should use internal knowledge)
    r2 = bc.send('What are neural networks?')
    assert r2.response_text
    assert len(r2.thought_trace) >= 1
    # Should have routing trace
    has_routing = any(t.category == 'routing' for t in r2.thought_trace)
    assert has_routing, "Should have routing trace entry"

    # Test 3: Continuous thinking produced thoughts
    thoughts = ct.get_recent_thoughts(10)
    assert len(thoughts) >= 1, "Continuous thinking should have produced at least 1 thought"

    # Test 4: Stats
    stats = bc.get_stats()
    assert stats['total_messages'] == 2

    ct_stats = ct.get_stats()
    assert ct_stats['running'] is True
    assert ct_stats['total_ticks'] >= 1

    ct.stop()


def test_brain_chat_with_thalamus_routing():
    """Test that L1 routing works when available."""
    try:
        from core.task_feature_router import TaskFeatureRouter
    except ImportError:
        import pytest
        pytest.skip("TaskFeatureRouter not available")

    from core.moltbook_pipeline import InputAnalyzer
    from core.brain_chat import BrainChat

    l1 = TaskFeatureRouter()
    analyzer = InputAnalyzer()
    bc = BrainChat(task_feature_router=l1, input_analyzer=analyzer)

    r = bc.send("Deploy the Docker container with updated config")
    assert r.routing_mode  # Should have a routing mode
    assert r.response_text  # Should have some response

    # Check that routing happened
    has_routing = any(t.category == 'routing' for t in r.thought_trace)
    assert has_routing

    # Check routing weights
    if r.routing_weights:
        assert len(r.routing_weights) == 10  # 10 modalities


def test_continuous_thinking_with_moltbook():
    """Test that continuous thinking explores Moltbook knowledge."""
    from core.moltbook import MoltbookStore
    from core.moltbook_agents import MoltbookFeeder
    from core.brain_chat import ContinuousThinkingEngine

    store = MoltbookStore(config={'similarity_threshold': 0.3})
    feeder = MoltbookFeeder(moltbook=store, agent_name='test')
    feeder.post(content='Reinforcement learning uses reward signals.', tags=[])

    ct = ContinuousThinkingEngine(moltbook=store, interval_ms=100)
    ct.start()
    time.sleep(1.0)  # Let it think

    thoughts = ct.get_recent_thoughts(20)
    ct.stop()

    assert len(thoughts) >= 1
    # At least one thought should be about exploration
    categories = {t.category for t in thoughts}
    assert 'explore' in categories


def test_brain_chat_to_dict_format():
    """Test that to_dict produces correct format for the API."""
    from core.brain_chat import BrainChat

    bc = BrainChat()
    r = bc.send("Hello!")
    d = r.to_dict()

    # Check required fields
    assert isinstance(d['response'], str)
    assert isinstance(d['confidence'], float)
    assert isinstance(d['routing'], dict)
    assert isinstance(d['thought_trace'], list)
    assert isinstance(d['timing'], dict)

    # Check routing subdict
    assert 'mode' in d['routing']
    assert 'weights' in d['routing']
    assert 'dominant_areas' in d['routing']
    assert 'task_type' in d['routing']

    # Check timing subdict
    assert 'routing_ms' in d['timing']
    assert 'thinking_ms' in d['timing']
    assert 'speaking_ms' in d['timing']
    assert 'total_ms' in d['timing']
