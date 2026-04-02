"""
Tests for Phase 7 modules: Event Bus, Brain Snapshot, Health Startup, Matrix Migration.
"""

import os
import sys
import json
import time
import tempfile
import shutil
import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# ============================================================================
# EVENT BUS TESTS (P7.99)
# ============================================================================

class TestEventBus:
    """Tests for core/event_bus.py"""

    def test_import(self):
        from core.event_bus import EventBus, BrainEvent, EventPriority, BrainTopics
        assert EventBus is not None
        assert BrainEvent is not None

    def test_subscribe_and_publish(self):
        from core.event_bus import EventBus, BrainEvent
        bus = EventBus()
        received = []
        bus.subscribe('test.topic', lambda e: received.append(e))
        event = BrainEvent(topic='test.topic', data={'key': 'value'}, source='test')
        dispatched = bus.publish(event)
        assert dispatched == 1
        assert len(received) == 1
        assert received[0].data['key'] == 'value'

    def test_emit_convenience(self):
        from core.event_bus import EventBus
        bus = EventBus()
        received = []
        bus.subscribe('hello', lambda e: received.append(e.data))
        bus.emit('hello', {'msg': 'world'}, source='test')
        assert len(received) == 1
        assert received[0]['msg'] == 'world'

    def test_wildcard_subscription(self):
        from core.event_bus import EventBus
        bus = EventBus()
        received = []
        bus.subscribe('memory.*', lambda e: received.append(e.topic))
        bus.emit('memory.store', {}, source='test')
        bus.emit('memory.recall', {}, source='test')
        bus.emit('predict.start', {}, source='test')  # should NOT match
        assert len(received) == 2
        assert 'memory.store' in received
        assert 'memory.recall' in received

    def test_global_wildcard(self):
        from core.event_bus import EventBus
        bus = EventBus()
        received = []
        bus.subscribe('*', lambda e: received.append(e.topic))
        bus.emit('any.topic', {}, source='test')
        bus.emit('another', {}, source='test')
        assert len(received) == 2

    def test_unsubscribe(self):
        from core.event_bus import EventBus
        bus = EventBus()
        received = []
        handler = lambda e: received.append(e)
        bus.subscribe('test', handler)
        bus.emit('test', {}, source='test')
        assert len(received) == 1

        result = bus.unsubscribe('test', handler)
        assert result is True
        bus.emit('test', {}, source='test')
        assert len(received) == 1  # No new events

    def test_event_history(self):
        from core.event_bus import EventBus
        bus = EventBus(max_history=10)
        for i in range(5):
            bus.emit(f'event.{i}', {'i': i}, source='test')
        history = bus.get_history()
        assert len(history) == 5
        assert history[0]['data']['i'] == 0

    def test_history_limit(self):
        from core.event_bus import EventBus
        bus = EventBus(max_history=3)
        for i in range(10):
            bus.emit('test', {'i': i}, source='test')
        history = bus.get_history()
        assert len(history) == 3

    def test_history_filter_by_topic(self):
        from core.event_bus import EventBus
        bus = EventBus()
        bus.emit('a.1', {}, source='test')
        bus.emit('b.1', {}, source='test')
        bus.emit('a.2', {}, source='test')
        history = bus.get_history(topic='a')
        assert len(history) == 2

    def test_statistics(self):
        from core.event_bus import EventBus
        bus = EventBus()
        bus.subscribe('test', lambda e: None)
        bus.emit('test', {}, source='s')
        bus.emit('test', {}, source='s')
        stats = bus.get_statistics()
        assert stats['total_events'] == 2
        assert stats['total_dispatched'] == 2
        assert stats['subscriber_count'] == 1

    def test_error_handling_in_handler(self):
        from core.event_bus import EventBus
        bus = EventBus()
        bus.subscribe('test', lambda e: 1/0)  # Will raise ZeroDivisionError
        dispatched = bus.emit('test', {}, source='test')
        assert dispatched == 0  # Failed handler not counted
        assert bus.get_statistics()['error_count'] == 1

    def test_brain_event_to_dict(self):
        from core.event_bus import BrainEvent, EventPriority
        event = BrainEvent(topic='test', data={'x': 1}, source='src', priority=EventPriority.HIGH)
        d = event.to_dict()
        assert d['topic'] == 'test'
        assert d['source'] == 'src'
        assert d['priority'] == 'HIGH'
        assert d['data'] == {'x': 1}

    def test_brain_topics_constants(self):
        from core.event_bus import BrainTopics
        assert BrainTopics.MEMORY_STORE == 'memory.store'
        assert BrainTopics.SYSTEM_STARTUP == 'system.startup'
        assert BrainTopics.PREDICT_COMPLETE == 'predict.complete'

    def test_get_subscribers(self):
        from core.event_bus import EventBus
        bus = EventBus()
        bus.subscribe('a', lambda e: None)
        bus.subscribe('a', lambda e: None)
        bus.subscribe('b', lambda e: None)
        subs = bus.get_subscribers()
        assert subs['a'] == 2
        assert subs['b'] == 1

    def test_reset(self):
        from core.event_bus import EventBus
        bus = EventBus()
        bus.subscribe('test', lambda e: None)
        bus.emit('test', {}, source='test')
        bus.reset()
        stats = bus.get_statistics()
        assert stats['total_events'] == 0
        assert stats['subscriber_count'] == 0

    def test_singleton_get_event_bus(self):
        from core.event_bus import get_event_bus
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2


# ============================================================================
# BRAIN SNAPSHOT TESTS (P7.100)
# ============================================================================

class TestBrainSnapshot:
    """Tests for core/brain_snapshot.py"""

    def test_import(self):
        from core.brain_snapshot import BrainSnapshot, NumpyJSONEncoder
        assert BrainSnapshot is not None

    def test_numpy_encoder_array(self):
        from core.brain_snapshot import NumpyJSONEncoder
        data = {'arr': np.array([1.0, 2.0, 3.0])}
        result = json.dumps(data, cls=NumpyJSONEncoder)
        parsed = json.loads(result)
        assert parsed['arr'] == [1.0, 2.0, 3.0]

    def test_numpy_encoder_scalar(self):
        from core.brain_snapshot import NumpyJSONEncoder
        data = {'int': np.int64(42), 'float': np.float32(3.14), 'bool': np.bool_(True)}
        result = json.dumps(data, cls=NumpyJSONEncoder)
        parsed = json.loads(result)
        assert parsed['int'] == 42
        assert abs(parsed['float'] - 3.14) < 0.01
        assert parsed['bool'] is True

    def test_snapshot_dir_creation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            snap_dir = os.path.join(tmpdir, 'snapshots')
            from core.brain_snapshot import BrainSnapshot
            mgr = BrainSnapshot(snapshot_dir=snap_dir)
            assert os.path.isdir(snap_dir)

    def test_capture_returns_dict(self):
        from core.brain_snapshot import BrainSnapshot

        class MockBrain:
            pass

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = BrainSnapshot(snapshot_dir=tmpdir)
            snapshot = mgr.capture(MockBrain())
            assert 'metadata' in snapshot
            assert 'subsystems' in snapshot
            assert 'version' in snapshot['metadata']
            assert 'timestamp' in snapshot['metadata']

    def test_save_and_load(self):
        from core.brain_snapshot import BrainSnapshot

        class MockBrain:
            pass

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = BrainSnapshot(snapshot_dir=tmpdir)
            filepath = mgr.save(MockBrain(), filename='test_snap.json')
            assert os.path.exists(filepath)

            loaded = mgr.load(filepath)
            assert loaded['metadata']['version'] == '1.0.0'

    def test_list_snapshots(self):
        from core.brain_snapshot import BrainSnapshot

        class MockBrain:
            pass

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = BrainSnapshot(snapshot_dir=tmpdir)
            mgr.save(MockBrain(), filename='brain_snapshot_test1.json')
            mgr.save(MockBrain(), filename='brain_snapshot_test2.json')
            listing = mgr.list_snapshots()
            assert len(listing) == 2

    def test_statistics(self):
        from core.brain_snapshot import BrainSnapshot

        class MockBrain:
            pass

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = BrainSnapshot(snapshot_dir=tmpdir)
            mgr.save(MockBrain())
            stats = mgr.get_statistics()
            assert stats['snapshot_count'] == 1
            assert stats['last_snapshot_time'] is not None

    def test_atomic_save_no_tmp_left(self):
        from core.brain_snapshot import BrainSnapshot

        class MockBrain:
            pass

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = BrainSnapshot(snapshot_dir=tmpdir)
            mgr.save(MockBrain(), filename='test.json')
            # No .tmp files should remain
            tmp_files = [f for f in os.listdir(tmpdir) if f.endswith('.tmp')]
            assert len(tmp_files) == 0


# ============================================================================
# HEALTH STARTUP TESTS (P7.95)
# ============================================================================

class TestHealthStartup:
    """Tests for core/health_startup.py"""

    def test_import(self):
        from core.health_startup import HealthCheckStartup, StartupPhase, HealthStatus
        assert HealthCheckStartup is not None

    def test_all_healthy(self):
        from core.health_startup import HealthCheckStartup, HealthStatus
        startup = HealthCheckStartup()
        startup.register_check('comp_a', lambda: True)
        startup.register_check('comp_b', lambda: True)
        report = startup.run_startup()
        assert report.overall_status == HealthStatus.HEALTHY
        assert len(report.components) == 2

    def test_optional_failure_is_degraded(self):
        from core.health_startup import HealthCheckStartup, HealthStatus
        startup = HealthCheckStartup(max_retries=0)
        startup.register_check('core', lambda: True)
        startup.register_check('optional_comp', lambda: (_ for _ in ()).throw(RuntimeError("fail")), optional=True)
        report = startup.run_startup()
        assert report.overall_status == HealthStatus.DEGRADED

    def test_critical_failure_is_unhealthy(self):
        from core.health_startup import HealthCheckStartup, HealthStatus
        startup = HealthCheckStartup(max_retries=0)
        startup.register_check('critical', lambda: (_ for _ in ()).throw(RuntimeError("fail")), optional=False)
        report = startup.run_startup()
        assert report.overall_status == HealthStatus.UNHEALTHY

    def test_retry_logic(self):
        from core.health_startup import HealthCheckStartup, HealthStatus
        attempt_count = [0]

        def flaky_check():
            attempt_count[0] += 1
            if attempt_count[0] < 2:
                raise RuntimeError("Not ready yet")
            return True

        startup = HealthCheckStartup(max_retries=2, retry_delay=0.01)
        startup.register_check('flaky', flaky_check)
        report = startup.run_startup()
        assert report.overall_status == HealthStatus.HEALTHY
        assert report.components[0].retries == 1

    def test_report_to_dict(self):
        from core.health_startup import HealthCheckStartup
        startup = HealthCheckStartup()
        startup.register_check('test', lambda: True)
        report = startup.run_startup()
        d = report.to_dict()
        assert 'overall_status' in d
        assert 'summary' in d
        assert d['summary']['healthy'] == 1

    def test_timing_recorded(self):
        from core.health_startup import HealthCheckStartup
        startup = HealthCheckStartup()
        startup.register_check('slow', lambda: (time.sleep(0.01) or True))
        report = startup.run_startup()
        assert report.components[0].init_time_ms > 0
        assert report.total_time_ms > 0

    def test_create_brain_startup_checks(self):
        from core.health_startup import create_brain_startup_checks

        class MockPlanner:
            memory = object()
            attention = object()
            neuromodulation = object()
            layer1 = object()
            layer2 = object()
            layer3 = object()
            predictive_coding = object()
            consciousness = object()
            goal_graph = object()

        class MockBrain:
            planner = MockPlanner()
            cognitive_loop = object()

        startup = create_brain_startup_checks(MockBrain())
        report = startup.run_startup()
        assert report.overall_status.value in ('healthy', 'degraded')
        assert len(report.components) == 10


# ============================================================================
# MATRIX MIGRATION TESTS (P7.97)
# ============================================================================

class TestMatrixMigration:
    """Tests for core/matrix_migration.py"""

    def test_import(self):
        from core.matrix_migration import MatrixMigrator, MigrationRecord
        assert MatrixMigrator is not None

    def test_resize_matrix_expand(self):
        from core.matrix_migration import MatrixMigrator
        mig = MatrixMigrator(data_dir=tempfile.mkdtemp())
        m = np.array([[1, 2], [3, 4]])
        result = mig.resize_matrix(m, (3, 4))
        assert result.shape == (3, 4)
        assert result[0, 0] == 1
        assert result[0, 1] == 2
        assert result[2, 3] == 0  # New element

    def test_resize_matrix_shrink(self):
        from core.matrix_migration import MatrixMigrator
        mig = MatrixMigrator(data_dir=tempfile.mkdtemp())
        m = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        result = mig.resize_matrix(m, (2, 2))
        assert result.shape == (2, 2)
        assert result[0, 0] == 1
        assert result[1, 1] == 5

    def test_resize_matrix_noop(self):
        from core.matrix_migration import MatrixMigrator
        mig = MatrixMigrator(data_dir=tempfile.mkdtemp())
        m = np.array([[1, 2], [3, 4]])
        result = mig.resize_matrix(m, (2, 2))
        assert np.array_equal(result, m)

    def test_resize_gate_vector_expand(self):
        from core.matrix_migration import MatrixMigrator
        mig = MatrixMigrator(data_dir=tempfile.mkdtemp())
        gates = np.array([0.3, 0.3, 0.4])
        result = mig.resize_gate_vector(gates, 5)
        assert len(result) == 5
        assert abs(sum(result) - 1.0) < 1e-6  # Normalized

    def test_resize_gate_vector_shrink(self):
        from core.matrix_migration import MatrixMigrator
        mig = MatrixMigrator(data_dir=tempfile.mkdtemp())
        gates = np.array([0.2, 0.2, 0.2, 0.2, 0.2])
        result = mig.resize_gate_vector(gates, 3)
        assert len(result) == 3
        assert abs(sum(result) - 1.0) < 1e-6

    def test_migrate_config_adds_cognitive_loop(self):
        from core.matrix_migration import MatrixMigrator
        mig = MatrixMigrator(data_dir=tempfile.mkdtemp())
        config = {'modalities': ['vision', 'audio']}
        result = mig.migrate_config(config, '0.9.0', '1.0.0')
        assert 'cognitive_loop' in result
        assert result['cognitive_loop']['enabled'] is False

    def test_migrate_config_noop_same_version(self):
        from core.matrix_migration import MatrixMigrator
        mig = MatrixMigrator(data_dir=tempfile.mkdtemp())
        config = {'key': 'value'}
        result = mig.migrate_config(config, '1.0.0', '1.0.0')
        assert result == config

    def test_migrate_checkpoint(self):
        from core.matrix_migration import MatrixMigrator
        tmpdir = tempfile.mkdtemp()
        mig = MatrixMigrator(data_dir=tmpdir, backup_dir=os.path.join(tmpdir, 'backups'))

        # Create a fake checkpoint
        cp_path = os.path.join(tmpdir, 'test_checkpoint.json')
        checkpoint = {
            'brain_gates': [0.5, 0.3, 0.1, 0.05, 0.03, 0.02],
            'routing_weights': [0.2, 0.2, 0.2, 0.2, 0.1, 0.1],
        }
        with open(cp_path, 'w') as f:
            json.dump(checkpoint, f)

        result = mig.migrate_checkpoint(cp_path, '0.9.0', '1.0.0')
        assert result is not None

        with open(cp_path, 'r') as f:
            migrated = json.load(f)
        assert len(migrated['brain_gates']) == 10  # Expanded to 10 modalities
        assert abs(sum(migrated['brain_gates']) - 1.0) < 1e-6

        shutil.rmtree(tmpdir)

    def test_migration_history(self):
        from core.matrix_migration import MatrixMigrator
        tmpdir = tempfile.mkdtemp()
        mig = MatrixMigrator(data_dir=tmpdir)
        mig.migrate_config({}, '0.9.0', '1.0.0')
        history = mig.get_migration_history()
        assert len(history) == 1
        assert history[0]['operation'] == 'schema_update'
        shutil.rmtree(tmpdir)

    def test_statistics(self):
        from core.matrix_migration import MatrixMigrator
        tmpdir = tempfile.mkdtemp()
        mig = MatrixMigrator(data_dir=tmpdir)
        stats = mig.get_statistics()
        assert stats['total_migrations'] == 0
        assert stats['version'] == '1.0.0'
        shutil.rmtree(tmpdir)

    def test_resize_matrix_mean_fill(self):
        from core.matrix_migration import MatrixMigrator
        mig = MatrixMigrator(data_dir=tempfile.mkdtemp())
        m = np.array([[10.0, 20.0], [30.0, 40.0]])
        result = mig.resize_matrix(m, (3, 3), fill_strategy='mean')
        assert result.shape == (3, 3)
        # Mean of original is 25.0, new cells should be 25.0
        assert result[2, 2] == 25.0
        # Original data preserved
        assert result[0, 0] == 10.0


# ============================================================================
# WEBSOCKET LIVE STATE TESTS (P7.98)
# ============================================================================

class TestWebSocketLiveState:
    """Tests for core/websocket_state.py"""

    def test_import(self):
        from core.websocket_state import LiveStateStreamer, SSEClient, get_live_streamer
        assert LiveStateStreamer is not None

    def test_register_client(self):
        from core.websocket_state import LiveStateStreamer
        streamer = LiveStateStreamer()
        client = streamer.register_client('test-1', channels=['brain_state', 'emotional'])
        assert client.client_id == 'test-1'
        assert 'brain_state' in client.channels
        assert 'emotional' in client.channels

    def test_unregister_client(self):
        from core.websocket_state import LiveStateStreamer
        streamer = LiveStateStreamer()
        client = streamer.register_client('test-2')
        streamer.unregister_client('test-2')
        stats = streamer.get_statistics()
        assert stats['active_clients'] == 0

    def test_broadcast(self):
        from core.websocket_state import LiveStateStreamer
        streamer = LiveStateStreamer()
        client = streamer.register_client('test-3', channels=['brain_state'])
        dispatched = streamer.broadcast('brain_state', {'test': True})
        assert dispatched == 1

        msg = client.queue.get_nowait()
        assert msg['event'] == 'brain_state'
        assert msg['data']['test'] is True

    def test_broadcast_channel_filter(self):
        from core.websocket_state import LiveStateStreamer
        streamer = LiveStateStreamer()
        client = streamer.register_client('test-4', channels=['emotional'])
        dispatched = streamer.broadcast('brain_state', {'test': True})
        assert dispatched == 0  # Client not subscribed to brain_state
        assert client.queue.empty()

    def test_statistics(self):
        from core.websocket_state import LiveStateStreamer
        streamer = LiveStateStreamer()
        streamer.register_client('c1', channels=['brain_state'])
        streamer.register_client('c2', channels=['emotional'])
        stats = streamer.get_statistics()
        assert stats['active_clients'] == 2
        assert stats['available_channels'] == LiveStateStreamer.CHANNELS

    def test_invalid_channel_filtered(self):
        from core.websocket_state import LiveStateStreamer
        streamer = LiveStateStreamer()
        client = streamer.register_client('test-5', channels=['invalid_channel', 'brain_state'])
        assert 'brain_state' in client.channels
        assert 'invalid_channel' not in client.channels

    def test_default_channel(self):
        from core.websocket_state import LiveStateStreamer
        streamer = LiveStateStreamer()
        client = streamer.register_client('test-6')
        assert client.channels == ['brain_state']


# ============================================================================
# COGNITIVE LOOP VISUALIZATION TESTS (P7.93)
# ============================================================================

class TestCognitiveLoopVisualization:
    """Tests for the cognitive loop visualization template."""

    def test_template_exists(self):
        template_path = os.path.join(
            os.path.dirname(__file__), '..', 'web', 'templates', 'cognitive_loop_viz.html'
        )
        assert os.path.exists(template_path)

    def test_template_contains_phases(self):
        template_path = os.path.join(
            os.path.dirname(__file__), '..', 'web', 'templates', 'cognitive_loop_viz.html'
        )
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'phase-perceive' in content
        assert 'phase-reason' in content
        assert 'phase-reflect' in content
        assert 'phase-consolidate' in content
