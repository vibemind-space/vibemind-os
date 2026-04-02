"""Tests for MemoryConsolidator + ThoughtEvolutionEngine persistence."""
import json
import os
import tempfile
import threading
import time

import pytest
import numpy as np
from collections import defaultdict
from unittest.mock import MagicMock, patch, PropertyMock

from core.memory_consolidation import MemoryConsolidator
from core.brain_chat import (
    ThoughtEvolutionEngine, ContinuousThought, BrainChat,
)


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _make_mock_moltbook(n_entries=5):
    """Create a mock MoltbookStore with n entries."""
    store = MagicMock()
    entries = {}
    for i in range(n_entries):
        entry = MagicMock()
        entry.id = f"entry_{i}"
        entry.content = f"Test content {i} about topic {i % 3}"
        entry.source_agent = 'thought' if i % 2 == 0 else 'chat'
        entry.last_accessed = time.time() - (i * 10)  # stagger access times
        entry.accessed_count = i + 1
        entry.semantic_embedding = np.random.randn(384).astype(np.float32) if i < 4 else None
        entry.confidence = 0.5 + i * 0.1
        entry.tags = [f'tag_{i}']
        entries[entry.id] = entry

    store._entries = entries
    store.size = len(entries)
    store.save_to_disk = MagicMock(return_value='data/moltbook/store.jsonl')
    store.load_from_disk = MagicMock(return_value=n_entries)
    store.add_entry = MagicMock()
    store._graph = MagicMock()  # MoltbookGraph
    return store


def _make_mock_dual_graph():
    """Create a mock DualGraph."""
    dg = MagicMock()
    dg.record_event = MagicMock(return_value=1)
    dg.force_mine = MagicMock()
    dg.save = MagicMock()
    dg.load = MagicMock(return_value=True)
    kg = MagicMock()
    kg.get_statistics = MagicMock(return_value={
        'total_events': 10,
        'total_episodes': 3,
    })
    dg.kotlingraph = kg
    return dg


def _make_mock_evolution():
    """Create a mock ThoughtEvolutionEngine."""
    evo = MagicMock()
    evo.save_state = MagicMock()
    evo.load_state = MagicMock(return_value=5)
    return evo


def _make_mock_pool():
    """Create a mock MicroAgentPool."""
    pool = MagicMock()
    pool._call_agent = MagicMock(return_value="Synthesized wisdom about topic X.")
    return pool


# ═══════════════════════════════════════════════════════════════════
# TestMemoryConsolidator
# ═══════════════════════════════════════════════════════════════════

class TestMemoryConsolidator:
    """Test the 7-phase consolidation cycle."""

    def test_create_minimal(self):
        """Constructor with only moltbook_store."""
        store = _make_mock_moltbook()
        mc = MemoryConsolidator(moltbook_store=store)
        assert mc._moltbook is store
        assert mc._dual_graph is None
        assert mc._evolution is None
        assert mc._pool is None
        assert mc._cycle_count == 0

    def test_create_full(self):
        """Constructor with all dependencies."""
        store = _make_mock_moltbook()
        dg = _make_mock_dual_graph()
        evo = _make_mock_evolution()
        pool = _make_mock_pool()
        mc = MemoryConsolidator(
            moltbook_store=store, dual_graph=dg,
            evolution_engine=evo, micro_agent_pool=pool,
            interval_s=10.0,
        )
        assert mc._dual_graph is dg
        assert mc._evolution is evo
        assert mc._pool is pool
        assert mc._interval == 10.0

    def test_queue_brain_event(self):
        """Event added to buffer thread-safely."""
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook())
        mc.queue_brain_event({'action': 'test', 'reward': 0.5})
        assert mc.get_buffer_size() == 1

    def test_queue_multiple_events(self):
        """Buffer holds multiple events."""
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook())
        for i in range(10):
            mc.queue_brain_event({'action': f'test_{i}'})
        assert mc.get_buffer_size() == 10

    def test_phase_decay(self):
        """Phase 1: Calls KnowledgeDecay.apply_decay()."""
        store = _make_mock_moltbook()
        mc = MemoryConsolidator(moltbook_store=store)
        # Mock the decay object
        mc._decay = MagicMock()
        mc._decay.apply_decay = MagicMock(return_value={'decayed': 5, 'below_threshold': 1})
        # All entries alive → no evictions
        for e in store._entries.values():
            e.compute_activation = MagicMock(return_value=0.5)
        store.consolidate = MagicMock(return_value={'removed': 0, 'merged': 0})
        result = mc._phase_decay()
        mc._decay.apply_decay.assert_called_once()
        assert result['decayed'] == 5

    def test_phase_decay_no_decay(self):
        """Phase 1: Graceful when no KnowledgeDecay available."""
        store = _make_mock_moltbook()
        mc = MemoryConsolidator(moltbook_store=store)
        mc._decay = None
        result = mc._phase_decay()
        assert result == {'decayed': 0, 'below_threshold': 0, 'evicted': 0}

    def test_phase_strengthen(self):
        """Phase 2: Recent entries get boosted."""
        store = _make_mock_moltbook(n_entries=3)
        # Make all entries recently accessed
        for e in store._entries.values():
            e.last_accessed = time.time() - 5  # 5 seconds ago
            e.accessed_count = 2
        mc = MemoryConsolidator(moltbook_store=store)
        boosted = mc._phase_strengthen(window_s=60.0)
        assert boosted == 3
        # access() should have been called on each
        for e in store._entries.values():
            e.access.assert_called_once()

    def test_phase_strengthen_old_entries(self):
        """Phase 2: Old entries are NOT boosted."""
        store = _make_mock_moltbook(n_entries=3)
        for e in store._entries.values():
            e.last_accessed = time.time() - 300  # 5 minutes ago
            e.accessed_count = 2
        mc = MemoryConsolidator(moltbook_store=store)
        boosted = mc._phase_strengthen(window_s=60.0)
        assert boosted == 0

    def test_phase_compress_no_pool(self):
        """Phase 3: Graceful skip when no MicroAgentPool."""
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook())
        assert mc._pool is None
        result = mc._phase_compress()
        assert result == 0

    def test_phase_compress_too_few(self):
        """Phase 3: No compression with < 3 similar entries."""
        store = _make_mock_moltbook(n_entries=1)
        pool = _make_mock_pool()
        mc = MemoryConsolidator(moltbook_store=store, micro_agent_pool=pool)
        result = mc._phase_compress()
        assert result == 0
        pool._call_agent.assert_not_called()

    def test_phase_compress_with_pool(self):
        """Phase 3: LLM summarizes cluster -> new entry."""
        store = _make_mock_moltbook(n_entries=5)
        # Make all entries recent and from thought sources
        for e in store._entries.values():
            e.last_accessed = time.time() - 10
            e.source_agent = 'thought'
        # Make embeddings very similar (so they cluster)
        # Noise must be tiny relative to base norm to keep cosine > 0.7
        base_emb = np.random.randn(384).astype(np.float32)
        base_emb /= np.linalg.norm(base_emb)
        for i, e in enumerate(store._entries.values()):
            noise = np.random.randn(384).astype(np.float32) * 0.001
            e.semantic_embedding = base_emb + noise

        pool = _make_mock_pool()
        mc = MemoryConsolidator(moltbook_store=store, micro_agent_pool=pool)
        result = mc._phase_compress()
        assert result == 1
        pool._call_agent.assert_called_once()
        store.add_entry.assert_called_once()
        call_kwargs = store.add_entry.call_args
        assert 'consolidated' in call_kwargs.kwargs.get('tags', [])

    def test_phase_connect(self):
        """Phase 4: Embedding similarity creates edges."""
        store = _make_mock_moltbook(n_entries=4)
        # Make embeddings similar (tiny noise to keep cosine > 0.5)
        base_emb = np.random.randn(384).astype(np.float32)
        base_emb /= np.linalg.norm(base_emb)
        for e in store._entries.values():
            e.last_accessed = time.time() - 10
            noise = np.random.randn(384).astype(np.float32) * 0.001
            e.semantic_embedding = base_emb + noise

        mc = MemoryConsolidator(moltbook_store=store)
        connections = mc._phase_connect(window_s=120.0)
        assert connections > 0
        store._graph.link.assert_called()

    def test_phase_connect_no_graph(self):
        """Phase 4: No crash when no MoltbookGraph."""
        store = _make_mock_moltbook()
        store._graph = None
        mc = MemoryConsolidator(moltbook_store=store)
        connections = mc._phase_connect()
        assert connections == 0

    def test_phase_record(self):
        """Phase 5: Buffer drained -> DualGraph.record_event() calls."""
        dg = _make_mock_dual_graph()
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook(), dual_graph=dg)
        mc.queue_brain_event({'action': 'test1', 'reward': 0.5, 'done': True})
        mc.queue_brain_event({'action': 'test2', 'reward': 0.8, 'done': False})
        recorded = mc._phase_record()
        assert recorded == 2
        assert dg.record_event.call_count == 2
        assert mc._total_events_recorded == 2

    def test_phase_record_clears_buffer(self):
        """Phase 5: Buffer empty after drain."""
        dg = _make_mock_dual_graph()
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook(), dual_graph=dg)
        mc.queue_brain_event({'action': 'test'})
        mc._phase_record()
        assert mc.get_buffer_size() == 0

    def test_phase_record_no_dual_graph(self):
        """Phase 5: Buffer cleared even without DualGraph."""
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook())
        mc.queue_brain_event({'action': 'test'})
        recorded = mc._phase_record()
        assert recorded == 0
        assert mc.get_buffer_size() == 0

    def test_phase_mine(self):
        """Phase 6: DualGraph.force_mine() called."""
        dg = _make_mock_dual_graph()
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook(), dual_graph=dg)
        result = mc._phase_mine()
        assert result is True
        dg.force_mine.assert_called_once()

    def test_phase_mine_no_dual_graph(self):
        """Phase 6: Graceful skip without DualGraph."""
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook())
        result = mc._phase_mine()
        assert result is False

    def test_phase_mine_too_few_events(self):
        """Phase 6: Skip mining when too few events."""
        dg = _make_mock_dual_graph()
        dg.kotlingraph.get_statistics.return_value = {
            'total_events': 2, 'total_episodes': 1,
        }
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook(), dual_graph=dg)
        result = mc._phase_mine()
        assert result is False
        dg.force_mine.assert_not_called()

    def test_phase_persist_moltbook(self):
        """Phase 7: MoltbookStore.save_to_disk() called."""
        store = _make_mock_moltbook()
        mc = MemoryConsolidator(moltbook_store=store)
        results = mc._phase_persist()
        assert results['moltbook'] is True
        store.save_to_disk.assert_called_once()

    def test_phase_persist_dual_graph(self):
        """Phase 7: DualGraph.save() called."""
        dg = _make_mock_dual_graph()
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook(), dual_graph=dg)
        results = mc._phase_persist()
        assert results['dual_graph'] is True
        dg.save.assert_called_once_with('memory')

    def test_phase_persist_evolution(self):
        """Phase 7: ThoughtEvolutionEngine.save_state() called."""
        evo = _make_mock_evolution()
        mc = MemoryConsolidator(
            moltbook_store=_make_mock_moltbook(), evolution_engine=evo,
        )
        results = mc._phase_persist()
        assert results['evolution'] is True
        evo.save_state.assert_called_once()

    def test_run_cycle(self):
        """All 7 phases execute in order."""
        store = _make_mock_moltbook()
        dg = _make_mock_dual_graph()
        evo = _make_mock_evolution()
        mc = MemoryConsolidator(
            moltbook_store=store, dual_graph=dg, evolution_engine=evo,
        )
        mc._decay = MagicMock()
        mc._decay.apply_decay = MagicMock(return_value={'decayed': 0, 'below_threshold': 0})

        report = mc.run_cycle()
        assert 'decay' in report
        assert 'strengthened' in report
        assert 'compressed' in report
        assert 'connections' in report
        assert 'recorded' in report
        assert 'mined' in report
        assert 'persisted' in report
        assert report['cycle'] == 1

    def test_run_cycle_stats(self):
        """cycle_count increments."""
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook())
        mc._decay = None  # skip decay
        mc.run_cycle()
        mc.run_cycle()
        assert mc._cycle_count == 2
        stats = mc.get_stats()
        assert stats['cycle_count'] == 2

    def test_start_stop(self):
        """Thread starts and stops cleanly."""
        mc = MemoryConsolidator(
            moltbook_store=_make_mock_moltbook(), interval_s=1.0,
        )
        mc._decay = None
        mc.start()
        assert mc._running
        assert mc._thread is not None
        time.sleep(0.3)
        mc.stop()
        assert not mc._running
        assert mc._thread is None

    def test_save_all(self):
        """Manual save triggers Phase 7 only."""
        store = _make_mock_moltbook()
        dg = _make_mock_dual_graph()
        mc = MemoryConsolidator(moltbook_store=store, dual_graph=dg)
        results = mc.save_all()
        assert results['moltbook'] is True
        assert results['dual_graph'] is True
        store.save_to_disk.assert_called_once()
        dg.save.assert_called_once()

    def test_graceful_no_dual_graph(self):
        """Works without DualGraph."""
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook())
        mc._decay = None
        report = mc.run_cycle()
        assert report['recorded'] == 0
        assert report['mined'] is False

    def test_graceful_no_evolution(self):
        """Works without ThoughtEvolutionEngine."""
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook())
        mc._decay = None
        report = mc.run_cycle()
        assert report['persisted']['evolution'] is False

    def test_concurrent_queue(self):
        """10 threads queuing simultaneously."""
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook())
        errors = []

        def queue_events(n):
            try:
                for i in range(n):
                    mc.queue_brain_event({'action': f'thread_{threading.current_thread().name}_{i}'})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=queue_events, args=(10,)) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert mc.get_buffer_size() == 100

    def test_get_stats(self):
        """get_stats returns expected keys."""
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook())
        stats = mc.get_stats()
        assert 'cycle_count' in stats
        assert 'total_events_recorded' in stats
        assert 'total_compressed' in stats
        assert 'running' in stats
        assert stats['running'] is False

    def test_eviction_stats_in_get_stats(self):
        """get_stats() includes tombstone/eviction data."""
        store = _make_mock_moltbook()
        store.consolidate = MagicMock(return_value={'removed': 0, 'merged': 0})
        mc = MemoryConsolidator(moltbook_store=store)

        stats = mc.get_stats()
        assert 'total_evicted' in stats
        assert 'tombstone_count' in stats
        assert stats['total_evicted'] == 0
        assert stats['tombstone_count'] == 0

    def test_find_similar_clusters_empty(self):
        """No clusters when too few entries."""
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook())
        clusters = mc._find_similar_clusters([], threshold=0.7, min_size=3)
        assert clusters == []

    def test_find_similar_clusters_found(self):
        """Finds clusters of similar entries."""
        mc = MemoryConsolidator(moltbook_store=_make_mock_moltbook())
        # Create 5 entries with very similar embeddings (tiny noise)
        base = np.random.randn(384).astype(np.float32)
        base /= np.linalg.norm(base)
        entries = []
        for i in range(5):
            e = MagicMock()
            noise = np.random.randn(384).astype(np.float32) * 0.001
            e.semantic_embedding = base + noise
            entries.append(e)

        clusters = mc._find_similar_clusters(entries, threshold=0.9, min_size=3)
        assert len(clusters) >= 1
        assert len(clusters[0]) >= 3

    def test_phase_decay_evicts_dead_entries(self):
        """Phase DECAY actually removes entries with activation < 0.01."""
        store = _make_mock_moltbook(n_entries=5)

        # Make 2 entries "dead" (activation < 0.01)
        dead_entry_0 = store._entries['entry_0']
        dead_entry_0.compute_activation = MagicMock(return_value=0.005)
        dead_entry_0.tags = ['python']
        dead_entry_0.content = 'Dead content about Python'
        dead_entry_0.confidence = 0.1
        dead_entry_0.created_at = time.time() - 86400

        dead_entry_1 = store._entries['entry_1']
        dead_entry_1.compute_activation = MagicMock(return_value=0.003)
        dead_entry_1.tags = ['docker']
        dead_entry_1.content = 'Dead content about Docker'
        dead_entry_1.confidence = 0.05
        dead_entry_1.created_at = time.time() - 172800

        # Other entries are alive
        for eid in ['entry_2', 'entry_3', 'entry_4']:
            store._entries[eid].compute_activation = MagicMock(return_value=0.5)

        # Mock consolidate to actually remove the dead entries
        def fake_consolidate(activation_threshold=0.01):
            removed = 0
            dead_ids = []
            for eid, entry in list(store._entries.items()):
                if entry.compute_activation() < activation_threshold:
                    dead_ids.append(eid)
            for eid in dead_ids:
                del store._entries[eid]
                removed += 1
            return {'removed': removed, 'merged': 0}

        store.consolidate = MagicMock(side_effect=fake_consolidate)

        mc = MemoryConsolidator(moltbook_store=store)
        result = mc._phase_decay()

        # consolidate was called
        store.consolidate.assert_called_once_with(activation_threshold=0.01)
        # Eviction count reported
        assert result.get('evicted', 0) == 2
        # Only 3 entries remain
        assert len(store._entries) == 3
        # Tombstones recorded
        assert mc._tombstone_log._total_forgotten == 2

    def test_phase_decay_preserves_active_entries(self):
        """Phase DECAY does not remove entries with high activation."""
        store = _make_mock_moltbook(n_entries=3)

        # All entries are alive
        for eid in store._entries:
            store._entries[eid].compute_activation = MagicMock(return_value=0.8)

        store.consolidate = MagicMock(return_value={'removed': 0, 'merged': 0})

        mc = MemoryConsolidator(moltbook_store=store)
        result = mc._phase_decay()

        store.consolidate.assert_called_once_with(activation_threshold=0.01)
        assert result.get('evicted', 0) == 0
        assert len(store._entries) == 3
        assert mc._tombstone_log._total_forgotten == 0


# ═══════════════════════════════════════════════════════════════════
# TestThoughtEvolutionPersistence
# ═══════════════════════════════════════════════════════════════════

class TestThoughtEvolutionPersistence:
    """Test save_state/load_state on ThoughtEvolutionEngine."""

    def test_save_load_roundtrip(self):
        """Save population -> load -> verify thoughts."""
        evo = ThoughtEvolutionEngine()
        # Add some thoughts
        for i in range(5):
            t = ContinuousThought(
                timestamp=time.time() + i,
                content=f"Test thought {i}",
                category='idle',
                topic=f'topic_{i}',
                relevance=0.5 + i * 0.1,
                thought_id=f'tid_{i}',
                fitness=0.3 + i * 0.05,
                generation=i,
                parent_ids=[f'pid_{i}'] if i > 0 else [],
            )
            evo._population[t.thought_id] = t
            evo._ts_to_id[t.timestamp] = t.thought_id

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
            path = f.name

        try:
            evo.save_state(path)
            assert os.path.exists(path)

            # Load into fresh engine
            evo2 = ThoughtEvolutionEngine()
            count = evo2.load_state(path)
            assert count == 5
            assert len(evo2._population) == 5
            assert 'tid_2' in evo2._population
            assert evo2._population['tid_2'].content == 'Test thought 2'
            assert evo2._population['tid_2'].generation == 2
        finally:
            os.unlink(path)

    def test_load_nonexistent(self):
        """Returns 0, no crash."""
        evo = ThoughtEvolutionEngine()
        count = evo.load_state('/nonexistent/path/file.json')
        assert count == 0
        assert len(evo._population) == 0

    def test_save_load_scores(self):
        """Critic scores + user ratings survive."""
        evo = ThoughtEvolutionEngine()
        t = ContinuousThought(
            timestamp=1000.0, content='Scored thought',
            category='idle', topic='test',
            thought_id='scored1',
        )
        evo._population['scored1'] = t
        evo._ts_to_id[1000.0] = 'scored1'
        evo._critic_scores['scored1'] = 0.85
        evo._user_ratings['scored1'] = 0.9

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
            path = f.name

        try:
            evo.save_state(path)
            evo2 = ThoughtEvolutionEngine()
            evo2.load_state(path)
            assert evo2._critic_scores.get('scored1') == 0.85
            assert evo2._user_ratings.get('scored1') == 0.9
        finally:
            os.unlink(path)

    def test_save_load_graph_edges(self):
        """Parent + similarity edges survive."""
        evo = ThoughtEvolutionEngine()
        t1 = ContinuousThought(
            timestamp=1.0, content='T1', category='idle',
            topic='test', thought_id='t1',
        )
        t2 = ContinuousThought(
            timestamp=2.0, content='T2', category='idle',
            topic='test', thought_id='t2',
        )
        evo._population['t1'] = t1
        evo._population['t2'] = t2
        evo._graph_edges['t1']['t2'] = 'parent'
        evo._graph_edges['t2']['t1'] = 'similar'

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
            path = f.name

        try:
            evo.save_state(path)
            evo2 = ThoughtEvolutionEngine()
            evo2.load_state(path)
            assert evo2._graph_edges['t1']['t2'] == 'parent'
            assert evo2._graph_edges['t2']['t1'] == 'similar'
        finally:
            os.unlink(path)

    def test_load_restores_generation(self):
        """Max generation counter restored."""
        evo = ThoughtEvolutionEngine()
        evo._max_generation = 7
        evo._total_evolutions = 42
        t = ContinuousThought(
            timestamp=1.0, content='G7', category='evolve',
            topic='test', thought_id='g7', generation=7,
        )
        evo._population['g7'] = t

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as f:
            path = f.name

        try:
            evo.save_state(path)
            evo2 = ThoughtEvolutionEngine()
            evo2.load_state(path)
            assert evo2._max_generation == 7
            assert evo2._total_evolutions == 42
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════
# TestBrainChatConsolidatorWiring
# ═══════════════════════════════════════════════════════════════════

class TestBrainChatConsolidatorWiring:
    """Test that BrainChat wires the consolidator correctly."""

    def test_set_memory_consolidator(self):
        """set_memory_consolidator wires to BrainChat and CTE."""
        bc = BrainChat()
        cte = MagicMock()
        bc._continuous_thinking = cte

        consolidator = MagicMock()
        bc.set_memory_consolidator(consolidator)

        assert bc._memory_consolidator is consolidator
        assert cte._memory_consolidator is consolidator

    def test_set_memory_consolidator_no_cte(self):
        """set_memory_consolidator works without CTE."""
        bc = BrainChat()
        consolidator = MagicMock()
        bc.set_memory_consolidator(consolidator)
        assert bc._memory_consolidator is consolidator

    def test_send_queues_brain_event(self):
        """BrainChat.send() queues a brain event after response."""
        bc = BrainChat()
        consolidator = MagicMock()
        bc.set_memory_consolidator(consolidator)

        # Send a simple message (will use fallback response)
        response = bc.send("test message for consolidation")
        # The consolidator should have been called
        consolidator.queue_brain_event.assert_called_once()
        event = consolidator.queue_brain_event.call_args[0][0]
        assert event['action'] == 'chat_response'
        assert event['done'] is True
        assert 'test message' in event['state']['user_input']


# ═══════════════════════════════════════════════════════════════════
# TestTombstoneLog
# ═══════════════════════════════════════════════════════════════════

class TestTombstoneLog:
    """Test tombstone recording for forgotten entries."""

    def test_record_creates_tombstones(self):
        """Recording dead entries creates Tombstone objects."""
        from core.memory_consolidation import TombstoneLog
        log = TombstoneLog(max_tombstones=100)

        # Create fake dead entries
        entry = MagicMock()
        entry.id = 'dead_1'
        entry.tags = ['python', 'basics']
        entry.content = 'Python is a programming language used for many applications'
        entry.confidence = 0.3
        entry.created_at = time.time() - 7200  # 2 hours old

        log.record([entry], reason='activation_decay')
        assert len(log._tombstones) == 1

        tomb = log._tombstones[0]
        assert tomb.entry_id == 'dead_1'
        assert tomb.tags == ['python', 'basics']
        assert tomb.content_preview == 'Python is a programming language used for many applications'[:80]
        assert tomb.confidence == 0.3
        assert tomb.reason == 'activation_decay'
        assert tomb.age_hours >= 1.9  # ~2 hours

    def test_tombstone_log_cap(self):
        """Deque maxlen caps at max_tombstones."""
        from core.memory_consolidation import TombstoneLog
        log = TombstoneLog(max_tombstones=5)

        for i in range(10):
            entry = MagicMock()
            entry.id = f'dead_{i}'
            entry.tags = []
            entry.content = f'Content {i}'
            entry.confidence = 0.1
            entry.created_at = time.time()
            log.record([entry], reason='activation_decay')

        # Only last 5 should survive
        assert len(log._tombstones) == 5
        assert log._tombstones[0].entry_id == 'dead_5'
        assert log._total_forgotten == 10

    def test_recent_returns_latest(self):
        """recent(n) returns the N most recent tombstones."""
        from core.memory_consolidation import TombstoneLog
        log = TombstoneLog(max_tombstones=100)

        for i in range(8):
            entry = MagicMock()
            entry.id = f'dead_{i}'
            entry.tags = [f'topic_{i}']
            entry.content = f'Content {i}'
            entry.confidence = 0.1
            entry.created_at = time.time()
            log.record([entry], reason='activation_decay')

        recent = log.recent(3)
        assert len(recent) == 3
        assert recent[0].entry_id == 'dead_7'  # Most recent first

    def test_forgotten_concepts(self):
        """forgotten_concepts() returns all tags from tombstones."""
        from core.memory_consolidation import TombstoneLog
        log = TombstoneLog(max_tombstones=100)

        for tags in [['python', 'ml'], ['docker', 'devops'], ['python', 'web']]:
            entry = MagicMock()
            entry.id = str(id(tags))
            entry.tags = tags
            entry.content = 'Test'
            entry.confidence = 0.1
            entry.created_at = time.time()
            log.record([entry], reason='activation_decay')

        concepts = log.forgotten_concepts()
        assert concepts == {'python', 'ml', 'docker', 'devops', 'web'}

    def test_get_stats(self):
        """get_stats() returns summary dict."""
        from core.memory_consolidation import TombstoneLog
        log = TombstoneLog(max_tombstones=100)
        stats = log.get_stats()
        assert stats['total_forgotten'] == 0
        assert stats['tombstone_count'] == 0

    def test_persistence_roundtrip(self):
        """Save and load produces identical tombstone log."""
        from core.memory_consolidation import TombstoneLog

        path = os.path.join(tempfile.mkdtemp(), 'tombstones.jsonl')
        log = TombstoneLog(max_tombstones=100, persist_path=path)

        for i in range(3):
            entry = MagicMock()
            entry.id = f'dead_{i}'
            entry.tags = [f'tag_{i}']
            entry.content = f'Content about topic {i}'
            entry.confidence = 0.2 + i * 0.1
            entry.created_at = time.time() - (i * 3600)
            log.record([entry], reason='activation_decay')

        log.save()
        assert os.path.exists(path)

        log2 = TombstoneLog(max_tombstones=100, persist_path=path)
        log2.load()
        assert len(log2._tombstones) == 3
        assert log2._total_forgotten == 3
        assert log2._tombstones[0].entry_id == 'dead_0'


# ═══════════════════════════════════════════════════════════════════
# Integration: Concept Death After Eviction
# ═══════════════════════════════════════════════════════════════════

class TestConceptDeathAfterEviction:
    """Integration test: eviction → SocializationMetrics sees concept deaths."""

    def test_concept_death_rate_after_eviction(self):
        """When entries are evicted, concept death rate becomes > 0.

        End-to-end: entries with unique content exist → cycle 1 captures
        baseline concepts → entries removed → cycle 2 detects deaths.

        Each entry has ENTIRELY unique keywords (no overlap) so removal
        guarantees concept deaths in the vocabulary.
        """
        from core.socialization_metrics import SocializationMetrics

        # Each entry has completely unique vocabulary — no shared words
        unique_contents = [
            'astronomy telescope galaxy nebula constellation celestial',
            'biology mitochondria ribosome nucleus cytoplasm organelle',
            'chemistry valence catalyst polymer isotope molecule',
            'geography plateau archipelago tundra savanna peninsula',
            'linguistics morpheme phoneme syntax semantics pragmatics',
            'mathematics polynomial eigenvalue manifold topology integral',
        ]

        store = MagicMock()
        alive_entries = {}
        for i, content in enumerate(unique_contents):
            entry = MagicMock()
            entry.id = f'entry_{i}'
            entry.content = content
            entry.source_agent = 'feeder'
            entry.confidence = 0.5
            entry.tags = [f'topic_{i}']
            entry.semantic_embedding = np.random.randn(384).astype(np.float32)
            entry.created_at = time.time() - 3600
            alive_entries[entry.id] = entry

        store._entries = alive_entries
        store.size = len(alive_entries)

        metrics = SocializationMetrics(moltbook_store=store, max_history=100)

        # Cycle 1: establish baseline concepts
        report1 = metrics.compute_all()
        assert report1['concept_death_rate'] == 0.0  # first cycle = no deaths

        # "Evict" entries 3-5 by removing them (simulates consolidate())
        # Removes: geography, linguistics, mathematics concepts
        to_remove = ['entry_3', 'entry_4', 'entry_5']
        for eid in to_remove:
            del alive_entries[eid]
        store._entries = alive_entries
        store.size = len(alive_entries)

        # Cycle 2: detect concept deaths
        report2 = metrics.compute_all()
        assert report2['concept_death_rate'] > 0.0, (
            f"Expected concept death rate > 0 after eviction, got {report2['concept_death_rate']}"
        )
