"""
Tests for Phase 1 INTERN Sensor Systems (P1.3-6, P1.9-15).

Tests for:
  - SensorEvent / FusedPerception dataclasses
  - SystemVitalsSensor (P1.3)
  - FileSystemSensor (P1.4)
  - ProcessSensor (P1.5)
  - LogSensor (P1.6)
  - GitActivitySensor (P1.9)
  - SensorRegistry (P1.10)
  - SensorFusion (P1.11)
  - PerceptionPipeline (P1.12)
  - AttentionDrivenSampling (P1.13)
  - NoveltyFilter (P1.14)
  - SensoryMemory (P1.15)
"""

import os
import sys
import time
import tempfile
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.sensor_systems import (
    SensorEvent,
    FusedPerception,
    SystemVitalsSensor,
    FileSystemSensor,
    FileEvent,
    ProcessSensor,
    ProcessStatus,
    LogSensor,
    GitActivitySensor,
    SensorRegistry,
    SensorFusion,
    PerceptionPipeline,
    AttentionDrivenSampling,
    NoveltyFilter,
    SensoryMemory,
)


# ─── Helper Fixtures ─────────────────────────────────────────────────────────

def _make_event(source='test', modality='touch', severity='info',
                priority=0.5, data=None, timestamp=None):
    """Helper to create a SensorEvent with sensible defaults."""
    return SensorEvent(
        timestamp=timestamp or time.time(),
        source=source,
        modality=modality,
        data=data or {'key': 'value'},
        severity=severity,
        priority=priority,
    )


# ═══════════════════════════════════════════════════════════════════════
# SensorEvent / FusedPerception Dataclasses
# ═══════════════════════════════════════════════════════════════════════

class TestSensorEvent:
    """Tests for the SensorEvent dataclass."""

    def test_default_timestamp_auto_fills(self):
        before = time.time()
        event = SensorEvent(timestamp=0.0, source='test', modality='touch',
                            data={'a': 1})
        after = time.time()
        assert before <= event.timestamp <= after

    def test_explicit_timestamp_preserved(self):
        event = SensorEvent(timestamp=12345.0, source='s', modality='m',
                            data={})
        assert event.timestamp == 12345.0

    def test_to_dict_keys(self):
        event = _make_event()
        d = event.to_dict()
        expected_keys = {'timestamp', 'source', 'modality', 'data',
                         'severity', 'priority'}
        assert set(d.keys()) == expected_keys

    def test_priority_rounded(self):
        event = _make_event(priority=0.123456789)
        d = event.to_dict()
        assert d['priority'] == 0.123


class TestFusedPerception:
    """Tests for the FusedPerception dataclass."""

    def test_default_timestamp_auto_fills(self):
        before = time.time()
        fp = FusedPerception(events=[], interpretation='test', confidence=0.8)
        after = time.time()
        assert before <= fp.timestamp <= after

    def test_to_dict_keys(self):
        e = _make_event()
        fp = FusedPerception(events=[e], interpretation='interp',
                             confidence=0.75, timestamp=100.0)
        d = fp.to_dict()
        assert 'events' in d
        assert 'interpretation' in d
        assert 'confidence' in d
        assert 'event_count' in d
        assert d['event_count'] == 1

    def test_confidence_rounded(self):
        fp = FusedPerception(events=[], interpretation='x',
                             confidence=0.777777)
        d = fp.to_dict()
        assert d['confidence'] == 0.778


# ═══════════════════════════════════════════════════════════════════════
# SystemVitalsSensor (P1.3)
# ═══════════════════════════════════════════════════════════════════════

class TestSystemVitalsSensor:
    """Tests for the SystemVitalsSensor class."""

    def test_default_init(self):
        svs = SystemVitalsSensor()
        assert svs.poll_interval_seconds == 10.0
        assert svs.anomaly_window == 30
        assert svs.sigma_threshold == 2.0
        assert svs._total_reads == 0

    def test_custom_init(self):
        svs = SystemVitalsSensor(
            poll_interval_seconds=5.0,
            anomaly_window=10,
            sigma_threshold=3.0,
        )
        assert svs.poll_interval_seconds == 5.0
        assert svs.anomaly_window == 10
        assert svs.sigma_threshold == 3.0

    def test_from_yaml(self):
        config = {
            'sensor_systems': {
                'system_vitals': {
                    'poll_interval_seconds': 2.0,
                    'anomaly_window': 15,
                    'sigma_threshold': 1.5,
                }
            }
        }
        svs = SystemVitalsSensor.from_yaml(config)
        assert svs.poll_interval_seconds == 2.0
        assert svs.anomaly_window == 15
        assert svs.sigma_threshold == 1.5

    def test_from_yaml_empty_config(self):
        svs = SystemVitalsSensor.from_yaml({})
        assert svs.poll_interval_seconds == 10.0

    def test_get_state(self):
        svs = SystemVitalsSensor()
        state = svs.get_state()
        assert isinstance(state, dict)
        assert state['name'] == 'SystemVitalsSensor'
        assert 'has_psutil' in state
        assert 'poll_interval_seconds' in state
        assert 'anomaly_window' in state
        assert 'sigma_threshold' in state
        assert 'total_reads' in state
        assert 'total_anomalies' in state
        assert 'last_poll' in state
        assert 'history_lengths' in state

    def test_read_returns_list(self):
        svs = SystemVitalsSensor()
        events = svs.read()
        assert isinstance(events, list)
        assert len(events) >= 1  # At least proprioception event
        assert svs._total_reads == 1

    def test_read_always_emits_proprioception(self):
        svs = SystemVitalsSensor()
        events = svs.read()
        proprioception = [e for e in events if e.modality == 'proprioception']
        assert len(proprioception) == 1
        assert proprioception[0].source == 'system_vitals'
        assert proprioception[0].severity == 'info'

    def test_read_updates_last_poll(self):
        svs = SystemVitalsSensor()
        assert svs._last_poll == 0.0
        before = time.time()
        svs.read()
        assert svs._last_poll >= before

    def test_read_updates_histories(self):
        svs = SystemVitalsSensor()
        svs.read()
        for key, hist in svs._histories.items():
            assert len(hist) == 1

    def test_anomaly_detection_with_spike(self):
        """Feed consistent values then a spike to trigger anomaly."""
        svs = SystemVitalsSensor(anomaly_window=10, sigma_threshold=2.0)
        # Patch _collect_vitals to return controlled values
        normal = {'cpu_percent': 50.0, 'ram_percent': 50.0,
                  'disk_percent': 50.0, 'net_bytes_sent': 1000.0,
                  'net_bytes_recv': 1000.0}
        with patch.object(svs, '_collect_vitals', return_value=normal):
            for _ in range(10):
                svs.read()
        # Now inject a spike
        spike = {'cpu_percent': 99.0, 'ram_percent': 50.0,
                 'disk_percent': 50.0, 'net_bytes_sent': 1000.0,
                 'net_bytes_recv': 1000.0}
        with patch.object(svs, '_collect_vitals', return_value=spike):
            events = svs.read()
        anomaly_events = [e for e in events if e.modality == 'touch']
        assert len(anomaly_events) >= 1
        assert svs._total_anomalies >= 1


# ═══════════════════════════════════════════════════════════════════════
# FileSystemSensor (P1.4)
# ═══════════════════════════════════════════════════════════════════════

class TestFileEvent:
    """Tests for the FileEvent dataclass."""

    def test_auto_timestamp(self):
        before = time.time()
        fe = FileEvent(event_type='created', path='/tmp/test.txt')
        after = time.time()
        assert before <= fe.timestamp <= after

    def test_to_dict(self):
        fe = FileEvent(event_type='modified', path='/a/b.py', timestamp=100.0)
        d = fe.to_dict()
        assert d['event_type'] == 'modified'
        assert d['path'] == '/a/b.py'
        assert d['timestamp'] == 100.0


class TestFileSystemSensor:
    """Tests for the FileSystemSensor class."""

    def test_default_init(self):
        fss = FileSystemSensor()
        assert fss.watch_paths == []
        assert fss.poll_interval == 5.0
        assert fss.max_events == 1000
        assert fss._initialized is False

    def test_custom_init(self):
        fss = FileSystemSensor(
            watch_paths=['/tmp'],
            poll_interval=2.0,
            max_events=500,
        )
        assert fss.watch_paths == ['/tmp']
        assert fss.poll_interval == 2.0
        assert fss.max_events == 500

    def test_from_yaml(self):
        config = {
            'sensor_systems': {
                'file_system': {
                    'watch_paths': ['/var/log'],
                    'poll_interval': 3.0,
                    'max_events': 200,
                }
            }
        }
        fss = FileSystemSensor.from_yaml(config)
        assert fss.watch_paths == ['/var/log']
        assert fss.poll_interval == 3.0
        assert fss.max_events == 200

    def test_from_yaml_empty_config(self):
        fss = FileSystemSensor.from_yaml({})
        assert fss.watch_paths == []
        assert fss.poll_interval == 5.0

    def test_get_state(self):
        fss = FileSystemSensor()
        state = fss.get_state()
        assert isinstance(state, dict)
        assert state['name'] == 'FileSystemSensor'
        assert 'watch_paths' in state
        assert 'poll_interval' in state
        assert 'tracked_files' in state
        assert 'queued_events' in state
        assert 'total_events' in state
        assert 'initialized' in state

    def test_first_read_baseline_no_events(self):
        """First read builds baseline, no events emitted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file so the dir is non-empty
            fpath = os.path.join(tmpdir, 'baseline.txt')
            with open(fpath, 'w') as f:
                f.write('hello')

            fss = FileSystemSensor(watch_paths=[tmpdir])
            events = fss.read()
            assert events == []  # First call = baseline
            assert fss._initialized is True

    def test_detect_created_file(self):
        """After baseline, creating a new file should emit a 'created' event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fss = FileSystemSensor(watch_paths=[tmpdir])
            fss.read()  # baseline

            # Create a new file
            new_path = os.path.join(tmpdir, 'new_file.txt')
            with open(new_path, 'w') as f:
                f.write('new content')

            events = fss.read()
            assert len(events) >= 1
            created = [e for e in events
                       if e.data.get('event_type') == 'created']
            assert len(created) == 1
            assert fss._total_events >= 1

    def test_detect_deleted_file(self):
        """After baseline, deleting a file should emit a 'deleted' event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, 'doomed.txt')
            with open(fpath, 'w') as f:
                f.write('temp')

            fss = FileSystemSensor(watch_paths=[tmpdir])
            fss.read()  # baseline

            os.remove(fpath)
            events = fss.read()
            deleted = [e for e in events
                       if e.data.get('event_type') == 'deleted']
            assert len(deleted) == 1
            assert deleted[0].severity == 'warning'

    def test_detect_modified_file(self):
        """After baseline, modifying a file should emit 'modified' event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, 'change_me.txt')
            with open(fpath, 'w') as f:
                f.write('original')

            fss = FileSystemSensor(watch_paths=[tmpdir])
            fss.read()  # baseline

            # Ensure mtime changes (some OSes have 1s granularity)
            time.sleep(0.05)
            with open(fpath, 'w') as f:
                f.write('changed')
            # Force mtime update
            os.utime(fpath, (time.time() + 1, time.time() + 1))

            events = fss.read()
            modified = [e for e in events
                        if e.data.get('event_type') == 'modified']
            assert len(modified) == 1

    def test_get_queued_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fss = FileSystemSensor(watch_paths=[tmpdir])
            fss.read()  # baseline
            new_path = os.path.join(tmpdir, 'queued.txt')
            with open(new_path, 'w') as f:
                f.write('data')
            fss.read()
            queued = fss.get_queued_events()
            assert isinstance(queued, list)
            assert len(queued) >= 1
            assert 'event_type' in queued[0]['data']

    def test_watch_single_file(self):
        """Sensor can watch a single file path, not just directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, 'single.txt')
            with open(fpath, 'w') as f:
                f.write('initial')

            fss = FileSystemSensor(watch_paths=[fpath])
            events = fss.read()  # baseline
            assert events == []
            assert fpath in fss._known_files

    def test_empty_watch_paths(self):
        fss = FileSystemSensor(watch_paths=[])
        events = fss.read()
        assert events == []
        assert fss._initialized is True


# ═══════════════════════════════════════════════════════════════════════
# ProcessSensor (P1.5)
# ═══════════════════════════════════════════════════════════════════════

class TestProcessSensor:
    """Tests for the ProcessSensor class."""

    def test_default_init(self):
        ps = ProcessSensor()
        assert 'unified_brain' in ps.monitored_ports
        assert ps.check_interval == 15.0
        assert ps.connect_timeout == 2.0

    def test_custom_init(self):
        ps = ProcessSensor(
            monitored_ports={'my_svc': 9999},
            check_interval=5.0,
            connect_timeout=1.0,
        )
        assert ps.monitored_ports == {'my_svc': 9999}
        assert ps.check_interval == 5.0
        assert ps.connect_timeout == 1.0
        assert ps._status['my_svc'] == ProcessStatus.DOWN

    def test_from_yaml(self):
        config = {
            'sensor_systems': {
                'process_sensor': {
                    'monitored_ports': {'test_svc': 7777},
                    'check_interval': 8.0,
                    'connect_timeout': 0.5,
                }
            }
        }
        ps = ProcessSensor.from_yaml(config)
        assert ps.monitored_ports == {'test_svc': 7777}
        assert ps.check_interval == 8.0
        assert ps.connect_timeout == 0.5

    def test_from_yaml_empty_config(self):
        ps = ProcessSensor.from_yaml({})
        assert 'unified_brain' in ps.monitored_ports

    def test_get_state(self):
        ps = ProcessSensor(monitored_ports={'svc': 1234})
        state = ps.get_state()
        assert isinstance(state, dict)
        assert state['name'] == 'ProcessSensor'
        assert 'monitored_ports' in state
        assert 'check_interval' in state
        assert 'service_status' in state
        assert 'failure_counts' in state
        assert 'total_checks' in state
        assert 'total_status_changes' in state

    def test_get_service_status(self):
        ps = ProcessSensor(monitored_ports={'svc': 1234})
        status = ps.get_service_status()
        assert status == {'svc': 'down'}

    def test_read_with_mock_port_down(self):
        """All ports down should transition from DOWN -> DOWN (no event)."""
        ps = ProcessSensor(monitored_ports={'svc': 1234})
        with patch.object(ps, '_check_port', return_value=False):
            events = ps.read()
        # Initial status is already DOWN, staying DOWN produces DEGRADED first
        assert ps._total_checks == 1

    def test_read_status_change_down_to_running(self):
        """Port comes up: status changes from DOWN to RUNNING."""
        ps = ProcessSensor(monitored_ports={'svc': 1234})
        with patch.object(ps, '_check_port', return_value=True):
            events = ps.read()
        # Should emit a status change event (DOWN -> RUNNING)
        assert len(events) == 1
        assert events[0].data['new_status'] == 'running'
        assert events[0].severity == 'info'
        assert ps._total_status_changes == 1

    def test_degraded_after_one_failure(self):
        """First failure transitions DOWN->DEGRADED initially, but since
        initial state is DOWN, first failure increments count to 1 which
        is DEGRADED. No change if already DOWN."""
        ps = ProcessSensor(monitored_ports={'svc': 1234})
        # First make it running
        with patch.object(ps, '_check_port', return_value=True):
            ps.read()
        assert ps._status['svc'] == ProcessStatus.RUNNING

        # One failure -> DEGRADED
        with patch.object(ps, '_check_port', return_value=False):
            events = ps.read()
        assert ps._status['svc'] == ProcessStatus.DEGRADED
        degraded_events = [e for e in events
                           if e.data.get('new_status') == 'degraded']
        assert len(degraded_events) == 1
        assert degraded_events[0].severity == 'warning'

    def test_down_after_three_failures(self):
        """Three consecutive failures -> DOWN."""
        ps = ProcessSensor(monitored_ports={'svc': 1234})
        # First make it running
        with patch.object(ps, '_check_port', return_value=True):
            ps.read()
        # Three failures -> DOWN
        with patch.object(ps, '_check_port', return_value=False):
            ps.read()  # fail 1 -> DEGRADED
            ps.read()  # fail 2 -> still DEGRADED
            events = ps.read()  # fail 3 -> DOWN
        assert ps._status['svc'] == ProcessStatus.DOWN
        down_events = [e for e in events
                       if e.data.get('new_status') == 'down']
        assert len(down_events) == 1
        assert down_events[0].severity == 'error'

    def test_recovery_clears_failure_count(self):
        """Going from DEGRADED back to RUNNING clears failures."""
        ps = ProcessSensor(monitored_ports={'svc': 1234})
        with patch.object(ps, '_check_port', return_value=True):
            ps.read()
        with patch.object(ps, '_check_port', return_value=False):
            ps.read()
        assert ps._failure_counts['svc'] == 1
        with patch.object(ps, '_check_port', return_value=True):
            ps.read()
        assert ps._failure_counts['svc'] == 0
        assert ps._status['svc'] == ProcessStatus.RUNNING


# ═══════════════════════════════════════════════════════════════════════
# LogSensor (P1.6)
# ═══════════════════════════════════════════════════════════════════════

class TestLogSensor:
    """Tests for the LogSensor class."""

    def test_default_init(self):
        ls = LogSensor()
        assert ls.log_paths == []
        assert ls.tail_lines == 100
        assert 'critical' in ls._compiled_patterns
        assert 'error' in ls._compiled_patterns
        assert 'warning' in ls._compiled_patterns

    def test_custom_init(self):
        ls = LogSensor(
            log_paths=['/tmp/app.log'],
            patterns={'error': r'ERR'},
            tail_lines=50,
        )
        assert ls.log_paths == ['/tmp/app.log']
        assert ls.tail_lines == 50
        assert 'error' in ls._compiled_patterns

    def test_from_yaml(self):
        config = {
            'sensor_systems': {
                'log_sensor': {
                    'log_paths': ['/var/log/app.log'],
                    'tail_lines': 200,
                }
            }
        }
        ls = LogSensor.from_yaml(config)
        assert ls.log_paths == ['/var/log/app.log']
        assert ls.tail_lines == 200

    def test_from_yaml_empty_config(self):
        ls = LogSensor.from_yaml({})
        assert ls.log_paths == []
        assert ls.tail_lines == 100

    def test_get_state(self):
        ls = LogSensor()
        state = ls.get_state()
        assert isinstance(state, dict)
        assert state['name'] == 'LogSensor'
        assert 'log_paths' in state
        assert 'tail_lines' in state
        assert 'pattern_count' in state
        assert 'total_reads' in state
        assert 'total_matches' in state
        assert state['pattern_count'] == 3

    def test_read_empty_paths(self):
        ls = LogSensor(log_paths=[])
        events = ls.read()
        assert events == []
        assert ls._total_reads == 1

    def test_read_detects_error_pattern(self):
        """Write a log file with ERROR, verify detection."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log',
                                         delete=False) as f:
            f.write("2024-01-01 INFO Starting up\n")
            f.write("2024-01-01 ERROR Something broke\n")
            f.write("2024-01-01 INFO Continuing\n")
            fpath = f.name

        try:
            ls = LogSensor(log_paths=[fpath])
            events = ls.read()
            error_events = [e for e in events
                            if e.data.get('matched_severity') == 'error']
            assert len(error_events) == 1
            assert 'Something broke' in error_events[0].data['line']
            assert error_events[0].modality == 'error_signal'
            assert ls._total_matches >= 1
        finally:
            os.unlink(fpath)

    def test_read_detects_warning_pattern(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log',
                                         delete=False) as f:
            f.write("WARNING: Disk space low\n")
            fpath = f.name
        try:
            ls = LogSensor(log_paths=[fpath])
            events = ls.read()
            warning_events = [e for e in events
                              if e.data.get('matched_severity') == 'warning']
            assert len(warning_events) == 1
        finally:
            os.unlink(fpath)

    def test_read_detects_critical_pattern(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log',
                                         delete=False) as f:
            f.write("CRITICAL: System failure\n")
            fpath = f.name
        try:
            ls = LogSensor(log_paths=[fpath])
            events = ls.read()
            critical_events = [e for e in events
                               if e.data.get('matched_severity') == 'critical']
            assert len(critical_events) == 1
        finally:
            os.unlink(fpath)

    def test_read_incremental_no_duplicates(self):
        """Second read should only return new lines."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log',
                                         delete=False) as f:
            f.write("ERROR first\n")
            fpath = f.name
        try:
            ls = LogSensor(log_paths=[fpath])
            events1 = ls.read()
            assert len(events1) == 1

            # Second read with no new content
            events2 = ls.read()
            assert len(events2) == 0

            # Append new content
            with open(fpath, 'a') as f2:
                f2.write("ERROR second\n")
            events3 = ls.read()
            assert len(events3) == 1
        finally:
            os.unlink(fpath)

    def test_nonexistent_log_path(self):
        ls = LogSensor(log_paths=['/nonexistent/path/fake.log'])
        events = ls.read()
        assert events == []

    def test_match_severity_priority_critical_over_error(self):
        """A line matching both CRITICAL and ERROR should match CRITICAL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log',
                                         delete=False) as f:
            f.write("CRITICAL ERROR: both patterns\n")
            fpath = f.name
        try:
            ls = LogSensor(log_paths=[fpath])
            events = ls.read()
            assert len(events) == 1
            assert events[0].data['matched_severity'] == 'critical'
        finally:
            os.unlink(fpath)


# ═══════════════════════════════════════════════════════════════════════
# GitActivitySensor (P1.9)
# ═══════════════════════════════════════════════════════════════════════

class TestGitActivitySensor:
    """Tests for the GitActivitySensor class."""

    def test_default_init(self):
        gas = GitActivitySensor()
        assert gas.repo_paths == []
        assert gas.check_interval == 300.0
        assert gas.since_minutes == 60
        assert gas._total_reads == 0

    def test_custom_init(self):
        gas = GitActivitySensor(
            repo_paths=['/repos/myrepo'],
            check_interval=120.0,
            since_minutes=30,
        )
        assert gas.repo_paths == ['/repos/myrepo']
        assert gas.check_interval == 120.0
        assert gas.since_minutes == 30

    def test_from_yaml(self):
        config = {
            'sensor_systems': {
                'git_activity': {
                    'repo_paths': ['/code/project'],
                    'check_interval': 60.0,
                    'since_minutes': 15,
                }
            }
        }
        gas = GitActivitySensor.from_yaml(config)
        assert gas.repo_paths == ['/code/project']
        assert gas.check_interval == 60.0
        assert gas.since_minutes == 15

    def test_from_yaml_empty_config(self):
        gas = GitActivitySensor.from_yaml({})
        assert gas.repo_paths == []

    def test_get_state(self):
        gas = GitActivitySensor()
        state = gas.get_state()
        assert isinstance(state, dict)
        assert state['name'] == 'GitActivitySensor'
        assert 'repo_paths' in state
        assert 'check_interval' in state
        assert 'since_minutes' in state
        assert 'known_branches' in state
        assert 'known_heads' in state
        assert 'total_reads' in state
        assert 'total_events' in state

    def test_read_empty_repos(self):
        gas = GitActivitySensor(repo_paths=[])
        events = gas.read()
        assert events == []
        assert gas._total_reads == 1

    def test_check_repo_no_git_dir(self):
        """A path without a .git directory returns no events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gas = GitActivitySensor(repo_paths=[tmpdir])
            events = gas.read()
            assert events == []

    def test_check_repo_branch_change_mock(self):
        """Mock subprocess to simulate a branch change."""
        gas = GitActivitySensor(repo_paths=['/fake/repo'])

        # Mock .git directory existence
        with patch('os.path.isdir', return_value=True):
            # First call: set baseline
            with patch.object(
                GitActivitySensor, '_run_git',
                side_effect=lambda repo, args: {
                    ('rev-parse', '--abbrev-ref', 'HEAD'): 'main',
                    ('rev-parse', 'HEAD'): 'abc1234567890',
                    ('status', '--porcelain'): '',
                }.get(tuple(args), None)
            ):
                gas.read()  # baseline

            assert gas._known_branches['/fake/repo'] == 'main'

            # Second call: branch changed
            with patch.object(
                GitActivitySensor, '_run_git',
                side_effect=lambda repo, args: {
                    ('rev-parse', '--abbrev-ref', 'HEAD'): 'feature-x',
                    ('rev-parse', 'HEAD'): 'abc1234567890',
                    ('status', '--porcelain'): '',
                }.get(tuple(args), None)
            ):
                events = gas.read()

            branch_events = [e for e in events
                             if e.data.get('event_type') == 'branch_change']
            assert len(branch_events) == 1
            assert branch_events[0].data['old_branch'] == 'main'
            assert branch_events[0].data['new_branch'] == 'feature-x'

    def test_check_repo_new_commits_mock(self):
        """Mock subprocess to simulate new commits."""
        gas = GitActivitySensor(repo_paths=['/fake/repo'])

        with patch('os.path.isdir', return_value=True):
            with patch.object(
                GitActivitySensor, '_run_git',
                side_effect=lambda repo, args: {
                    ('rev-parse', '--abbrev-ref', 'HEAD'): 'main',
                    ('rev-parse', 'HEAD'): 'aaa1111100000000',
                    ('status', '--porcelain'): '',
                }.get(tuple(args), None)
            ):
                gas.read()

            def git_side_effect(repo, args):
                key = tuple(args)
                if key == ('rev-parse', '--abbrev-ref', 'HEAD'):
                    return 'main'
                if key == ('rev-parse', 'HEAD'):
                    return 'bbb2222200000000'
                if key == ('status', '--porcelain'):
                    return ''
                if args[0] == 'rev-list':
                    return '3'
                return None

            with patch.object(
                GitActivitySensor, '_run_git',
                side_effect=git_side_effect,
            ):
                events = gas.read()

            commit_events = [e for e in events
                             if e.data.get('event_type') == 'new_commits']
            assert len(commit_events) == 1
            assert commit_events[0].data['commit_count'] == 3

    def test_check_repo_uncommitted_changes_mock(self):
        """Mock subprocess to simulate uncommitted changes."""
        gas = GitActivitySensor(repo_paths=['/fake/repo'])

        with patch('os.path.isdir', return_value=True):
            with patch.object(
                GitActivitySensor, '_run_git',
                side_effect=lambda repo, args: {
                    ('rev-parse', '--abbrev-ref', 'HEAD'): 'main',
                    ('rev-parse', 'HEAD'): 'aaa1111100000000',
                    ('status', '--porcelain'): ' M file1.py\n M file2.py',
                }.get(tuple(args), None)
            ):
                events = gas.read()

        uncommitted = [e for e in events
                       if e.data.get('event_type') == 'uncommitted_changes']
        assert len(uncommitted) == 1
        assert uncommitted[0].data['changed_files'] == 2


# ═══════════════════════════════════════════════════════════════════════
# SensorRegistry (P1.10)
# ═══════════════════════════════════════════════════════════════════════

class TestSensorRegistry:
    """Tests for the SensorRegistry class."""

    def test_default_init(self):
        sr = SensorRegistry()
        assert sr.max_events_per_second == 100.0
        assert sr.event_buffer_size == 10000
        assert sr._running is False

    def test_custom_init(self):
        sr = SensorRegistry(
            max_events_per_second=50.0,
            event_buffer_size=5000,
        )
        assert sr.max_events_per_second == 50.0
        assert sr.event_buffer_size == 5000

    def test_from_yaml(self):
        config = {
            'sensor_systems': {
                'registry': {
                    'max_events_per_second': 25.0,
                    'event_buffer_size': 2000,
                }
            }
        }
        sr = SensorRegistry.from_yaml(config)
        assert sr.max_events_per_second == 25.0
        assert sr.event_buffer_size == 2000

    def test_from_yaml_empty_config(self):
        sr = SensorRegistry.from_yaml({})
        assert sr.max_events_per_second == 100.0

    def test_get_state(self):
        sr = SensorRegistry()
        state = sr.get_state()
        assert isinstance(state, dict)
        assert state['name'] == 'SensorRegistry'
        assert 'running' in state
        assert 'registered_sensors' in state
        assert 'sensor_count' in state
        assert 'buffered_events' in state
        assert 'total_events_received' in state
        assert 'total_events_dropped' in state

    def test_register_and_unregister(self):
        sr = SensorRegistry()
        mock_sensor = MagicMock()
        mock_sensor.read.return_value = []

        sr.register('mock_sensor', mock_sensor)
        assert 'mock_sensor' in sr._sensors
        assert sr.get_state()['sensor_count'] == 1

        sr.unregister('mock_sensor')
        assert 'mock_sensor' not in sr._sensors
        assert sr.get_state()['sensor_count'] == 0

    def test_unregister_nonexistent(self):
        sr = SensorRegistry()
        sr.unregister('nonexistent')  # Should not raise

    def test_poll_all_collects_events(self):
        sr = SensorRegistry()
        mock_sensor = MagicMock()
        mock_sensor.read.return_value = [
            _make_event(source='mock', priority=0.8),
            _make_event(source='mock', priority=0.2),
        ]
        sr.register('mock', mock_sensor)
        events = sr.poll_all()
        assert len(events) == 2
        # Sorted by priority descending
        assert events[0].priority >= events[1].priority
        assert sr._total_events_received == 2

    def test_poll_all_rate_limiting(self):
        """Exceed rate limit and verify events are dropped."""
        sr = SensorRegistry(max_events_per_second=2.0)
        mock_sensor = MagicMock()
        mock_sensor.read.return_value = [
            _make_event(source='flood') for _ in range(10)
        ]
        sr.register('flood_sensor', mock_sensor)
        events = sr.poll_all()
        assert len(events) <= 2
        assert sr._total_events_dropped >= 8

    def test_get_events_since(self):
        sr = SensorRegistry()
        mock_sensor = MagicMock()
        now = time.time()
        mock_sensor.read.return_value = [
            _make_event(source='s', timestamp=now - 10),
            _make_event(source='s', timestamp=now),
        ]
        sr.register('s', mock_sensor)
        sr.poll_all()

        recent = sr.get_events(since=now - 5)
        assert len(recent) == 1
        all_events = sr.get_events(since=0.0)
        assert len(all_events) == 2

    def test_start_stop(self):
        sr = SensorRegistry()
        assert sr._running is False
        sr.start_all()
        assert sr._running is True
        sr.stop_all()
        assert sr._running is False

    def test_poll_handles_sensor_error(self):
        """Sensor raising an exception should not crash poll_all."""
        sr = SensorRegistry()
        bad_sensor = MagicMock()
        bad_sensor.read.side_effect = RuntimeError("sensor broke")
        sr.register('bad', bad_sensor)
        events = sr.poll_all()
        assert events == []  # Graceful handling


# ═══════════════════════════════════════════════════════════════════════
# SensorFusion (P1.11)
# ═══════════════════════════════════════════════════════════════════════

class TestSensorFusion:
    """Tests for the SensorFusion class."""

    def test_default_init(self):
        sf = SensorFusion()
        assert sf.correlation_window_seconds == 5.0
        assert sf.min_events_for_fusion == 2
        assert sf._total_fusions == 0

    def test_custom_init(self):
        sf = SensorFusion(
            correlation_window_seconds=10.0,
            min_events_for_fusion=3,
        )
        assert sf.correlation_window_seconds == 10.0
        assert sf.min_events_for_fusion == 3

    def test_from_yaml(self):
        config = {
            'sensor_systems': {
                'sensor_fusion': {
                    'correlation_window_seconds': 8.0,
                    'min_events_for_fusion': 4,
                }
            }
        }
        sf = SensorFusion.from_yaml(config)
        assert sf.correlation_window_seconds == 8.0
        assert sf.min_events_for_fusion == 4

    def test_from_yaml_empty_config(self):
        sf = SensorFusion.from_yaml({})
        assert sf.correlation_window_seconds == 5.0

    def test_get_state(self):
        sf = SensorFusion()
        state = sf.get_state()
        assert isinstance(state, dict)
        assert state['name'] == 'SensorFusion'
        assert 'correlation_window_seconds' in state
        assert 'min_events_for_fusion' in state
        assert 'pending_events' in state
        assert 'total_fusions' in state
        assert 'total_events_processed' in state
        assert 'fusion_rules_count' in state

    def test_add_events_increments_count(self):
        sf = SensorFusion()
        events = [_make_event(), _make_event()]
        sf.add_events(events)
        assert sf._total_events_processed == 2
        assert len(sf._pending_events) == 2

    def test_fuse_insufficient_events(self):
        sf = SensorFusion(min_events_for_fusion=3)
        sf.add_events([_make_event()])
        perceptions = sf.fuse()
        assert perceptions == []

    def test_fuse_correlated_events(self):
        """Two events from known correlated sources should fuse."""
        sf = SensorFusion(correlation_window_seconds=10.0,
                          min_events_for_fusion=2)
        now = time.time()
        events = [
            _make_event(source='log_sensor', modality='error_signal',
                        severity='error', priority=0.8, timestamp=now),
            _make_event(source='process_sensor', modality='interoception',
                        severity='warning', priority=0.5, timestamp=now),
        ]
        sf.add_events(events)
        perceptions = sf.fuse()
        assert len(perceptions) >= 1
        assert sf._total_fusions >= 1
        p = perceptions[0]
        assert isinstance(p, FusedPerception)
        assert p.confidence > 0

    def test_fuse_no_matching_rule(self):
        """Events from sources with no fusion rule should not fuse."""
        sf = SensorFusion(correlation_window_seconds=10.0,
                          min_events_for_fusion=2)
        now = time.time()
        events = [
            _make_event(source='source_x', timestamp=now),
            _make_event(source='source_y', timestamp=now),
        ]
        sf.add_events(events)
        perceptions = sf.fuse()
        assert perceptions == []

    def test_fuse_removes_fused_events_from_pending(self):
        sf = SensorFusion(correlation_window_seconds=10.0,
                          min_events_for_fusion=2)
        now = time.time()
        events = [
            _make_event(source='log_sensor', timestamp=now),
            _make_event(source='process_sensor', timestamp=now),
        ]
        sf.add_events(events)
        before = len(sf._pending_events)
        sf.fuse()
        after = len(sf._pending_events)
        assert after < before


# ═══════════════════════════════════════════════════════════════════════
# PerceptionPipeline (P1.12)
# ═══════════════════════════════════════════════════════════════════════

class TestPerceptionPipeline:
    """Tests for the PerceptionPipeline class."""

    def test_default_init(self):
        pp = PerceptionPipeline()
        assert pp.pipeline_enabled is True
        assert pp.batch_size == 10
        assert pp._total_events_in == 0

    def test_custom_init(self):
        pp = PerceptionPipeline(pipeline_enabled=False, batch_size=5)
        assert pp.pipeline_enabled is False
        assert pp.batch_size == 5

    def test_from_yaml(self):
        config = {
            'sensor_systems': {
                'perception_pipeline': {
                    'pipeline_enabled': False,
                    'batch_size': 20,
                }
            }
        }
        pp = PerceptionPipeline.from_yaml(config)
        assert pp.pipeline_enabled is False
        assert pp.batch_size == 20

    def test_from_yaml_empty_config(self):
        pp = PerceptionPipeline.from_yaml({})
        assert pp.pipeline_enabled is True
        assert pp.batch_size == 10

    def test_get_state(self):
        pp = PerceptionPipeline()
        state = pp.get_state()
        assert isinstance(state, dict)
        assert state['name'] == 'PerceptionPipeline'
        assert 'pipeline_enabled' in state
        assert 'batch_size' in state
        assert 'incoming_queue_size' in state
        assert 'perception_queue_size' in state
        assert 'has_fusion' in state
        assert 'total_events_in' in state
        assert 'total_perceptions_out' in state
        assert 'total_steps' in state

    def test_ingest_disabled_pipeline(self):
        pp = PerceptionPipeline(pipeline_enabled=False)
        pp.ingest([_make_event()])
        assert pp._total_events_in == 0
        assert len(pp._incoming_queue) == 0

    def test_ingest_enabled_pipeline(self):
        pp = PerceptionPipeline()
        pp.ingest([_make_event(), _make_event()])
        assert pp._total_events_in == 2
        assert len(pp._incoming_queue) == 2

    def test_step_without_fusion(self):
        pp = PerceptionPipeline()
        pp.ingest([_make_event(priority=0.9)])
        results = pp.step()
        # Without fusion, high-priority events still pass through as raw
        assert pp._total_steps == 1
        # High priority event (>=0.7) should appear as raw_sensor_event
        raw = [r for r in results if r.get('type') == 'raw_sensor_event']
        assert len(raw) == 1

    def test_step_with_fusion(self):
        pp = PerceptionPipeline()
        fusion = SensorFusion(correlation_window_seconds=10.0)
        pp.set_fusion(fusion)

        now = time.time()
        events = [
            _make_event(source='log_sensor', priority=0.8, timestamp=now),
            _make_event(source='process_sensor', priority=0.5, timestamp=now),
        ]
        pp.ingest(events)
        results = pp.step()
        assert pp._total_steps == 1
        assert isinstance(results, list)

    def test_step_empty_queue(self):
        pp = PerceptionPipeline()
        results = pp.step()
        assert results == []
        assert pp._total_steps == 1

    def test_step_disabled_pipeline(self):
        pp = PerceptionPipeline(pipeline_enabled=False)
        pp._incoming_queue.append(_make_event())  # Force something in
        results = pp.step()
        assert results == []

    def test_get_recent_perceptions(self):
        """Uses list()[-N:] pattern, no deque slicing."""
        pp = PerceptionPipeline()
        # Manually add perceptions to queue
        for i in range(5):
            pp._perception_queue.append({'id': i})
        recent = pp.get_recent_perceptions(count=3)
        assert len(recent) == 3
        assert recent[0]['id'] == 2
        assert recent[2]['id'] == 4

    def test_set_fusion(self):
        pp = PerceptionPipeline()
        assert pp._fusion is None
        assert pp.get_state()['has_fusion'] is False
        fusion = SensorFusion()
        pp.set_fusion(fusion)
        assert pp._fusion is fusion
        assert pp.get_state()['has_fusion'] is True

    def test_batch_size_limits_processing(self):
        pp = PerceptionPipeline(batch_size=2)
        pp.ingest([_make_event() for _ in range(5)])
        assert len(pp._incoming_queue) == 5
        pp.step()
        # Only 2 events should be drained
        assert len(pp._incoming_queue) == 3


# ═══════════════════════════════════════════════════════════════════════
# AttentionDrivenSampling (P1.13)
# ═══════════════════════════════════════════════════════════════════════

class TestAttentionDrivenSampling:
    """Tests for the AttentionDrivenSampling class."""

    def test_default_init(self):
        ads = AttentionDrivenSampling()
        assert ads.base_multiplier == 1.0
        assert ads.max_multiplier == 5.0
        assert ads.min_multiplier == 0.2
        assert ads._total_updates == 0

    def test_custom_init(self):
        ads = AttentionDrivenSampling(
            base_multiplier=2.0,
            max_multiplier=10.0,
            min_multiplier=0.1,
        )
        assert ads.base_multiplier == 2.0
        assert ads.max_multiplier == 10.0
        assert ads.min_multiplier == 0.1

    def test_from_yaml(self):
        config = {
            'sensor_systems': {
                'attention_sampling': {
                    'base_multiplier': 1.5,
                    'max_multiplier': 8.0,
                    'min_multiplier': 0.5,
                }
            }
        }
        ads = AttentionDrivenSampling.from_yaml(config)
        assert ads.base_multiplier == 1.5
        assert ads.max_multiplier == 8.0
        assert ads.min_multiplier == 0.5

    def test_from_yaml_empty_config(self):
        ads = AttentionDrivenSampling.from_yaml({})
        assert ads.base_multiplier == 1.0

    def test_get_state(self):
        ads = AttentionDrivenSampling()
        state = ads.get_state()
        assert isinstance(state, dict)
        assert state['name'] == 'AttentionDrivenSampling'
        assert 'base_multiplier' in state
        assert 'max_multiplier' in state
        assert 'min_multiplier' in state
        assert 'attention_weights' in state
        assert 'computed_multipliers' in state
        assert 'modality_sensor_map' in state
        assert 'total_updates' in state

    def test_update_attention(self):
        ads = AttentionDrivenSampling()
        ads.update_attention({'error_signal': 0.8, 'touch': 0.2})
        assert ads._total_updates == 1
        assert ads._attention_weights['error_signal'] == 0.8
        assert 'log_sensor' in ads._multipliers

    def test_get_poll_interval_high_attention(self):
        """High attention on error_signal should shorten log_sensor interval."""
        ads = AttentionDrivenSampling()
        ads.update_attention({
            'error_signal': 0.9,
            'touch': 0.1,
            'proprioception': 0.1,
            'tool_trace': 0.1,
            'interoception': 0.1,
        })
        base_interval = 10.0
        adjusted = ads.get_poll_interval('log_sensor', base_interval)
        # Higher attention -> higher multiplier -> shorter interval
        assert adjusted < base_interval

    def test_get_poll_interval_low_attention(self):
        """Low attention on a modality should lengthen its sensor interval."""
        ads = AttentionDrivenSampling()
        ads.update_attention({
            'error_signal': 0.1,
            'touch': 0.9,
            'proprioception': 0.1,
            'tool_trace': 0.1,
            'interoception': 0.1,
        })
        base_interval = 10.0
        adjusted = ads.get_poll_interval('log_sensor', base_interval)
        # Lower attention -> lower multiplier -> longer interval
        assert adjusted > base_interval

    def test_get_poll_interval_unknown_sensor(self):
        """Unknown sensor should use base multiplier."""
        ads = AttentionDrivenSampling()
        interval = ads.get_poll_interval('unknown_sensor', 10.0)
        assert interval == 10.0

    def test_multiplier_clamped_to_max(self):
        ads = AttentionDrivenSampling(max_multiplier=3.0)
        # Give extreme attention to one modality
        ads.update_attention({
            'error_signal': 1.0,
            'touch': 0.001,
        })
        multiplier = ads._multipliers.get('log_sensor', 1.0)
        assert multiplier <= 3.0

    def test_multiplier_clamped_to_min(self):
        ads = AttentionDrivenSampling(min_multiplier=0.5)
        ads.update_attention({
            'error_signal': 0.001,
            'touch': 1.0,
        })
        multiplier = ads._multipliers.get('log_sensor', 1.0)
        assert multiplier >= 0.5

    def test_register_modality_sensor(self):
        ads = AttentionDrivenSampling()
        ads.register_modality_sensor('custom_modality', 'custom_sensor')
        assert ads._modality_sensor_map['custom_modality'] == 'custom_sensor'

    def test_empty_attention_weights(self):
        ads = AttentionDrivenSampling()
        ads.update_attention({})
        assert ads._total_updates == 1
        assert ads._multipliers == {}


# ═══════════════════════════════════════════════════════════════════════
# NoveltyFilter (P1.14)
# ═══════════════════════════════════════════════════════════════════════

class TestNoveltyFilter:
    """Tests for the NoveltyFilter class."""

    def test_default_init(self):
        nf = NoveltyFilter()
        assert nf.novelty_threshold == 0.3
        assert nf.history_window == 100
        assert nf._total_received == 0

    def test_custom_init(self):
        nf = NoveltyFilter(novelty_threshold=0.5, history_window=50)
        assert nf.novelty_threshold == 0.5
        assert nf.history_window == 50

    def test_from_yaml(self):
        config = {
            'sensor_systems': {
                'novelty_filter': {
                    'novelty_threshold': 0.6,
                    'history_window': 200,
                }
            }
        }
        nf = NoveltyFilter.from_yaml(config)
        assert nf.novelty_threshold == 0.6
        assert nf.history_window == 200

    def test_from_yaml_empty_config(self):
        nf = NoveltyFilter.from_yaml({})
        assert nf.novelty_threshold == 0.3

    def test_get_state(self):
        nf = NoveltyFilter()
        state = nf.get_state()
        assert isinstance(state, dict)
        assert state['name'] == 'NoveltyFilter'
        assert 'novelty_threshold' in state
        assert 'history_window' in state
        assert 'signatures_tracked' in state
        assert 'history_size' in state
        assert 'total_received' in state
        assert 'total_passed' in state
        assert 'total_filtered' in state
        assert 'pass_rate' in state

    def test_first_event_always_novel(self):
        """The very first event should always pass (novelty=1.0)."""
        nf = NoveltyFilter(novelty_threshold=0.3)
        event = _make_event(source='unique_source', modality='unique_mod')
        passed = nf.filter([event])
        assert len(passed) == 1
        assert nf._total_passed == 1

    def test_repeated_events_get_filtered(self):
        """Repeating the same event many times should eventually filter it."""
        nf = NoveltyFilter(novelty_threshold=0.3, history_window=20)
        event = _make_event(source='repeat', modality='repeat',
                            severity='info', data={'key': 'val'})
        total_passed = 0
        for _ in range(25):
            passed = nf.filter([event])
            total_passed += len(passed)
        # Eventually, repeated events should be filtered
        assert nf._total_filtered > 0
        assert total_passed < 25

    def test_different_events_pass(self):
        """Events with different signatures should all pass initially."""
        nf = NoveltyFilter(novelty_threshold=0.3)
        events = [
            _make_event(source='a', modality='m1', severity='info'),
            _make_event(source='b', modality='m2', severity='warning'),
            _make_event(source='c', modality='m3', severity='error'),
        ]
        passed = nf.filter(events)
        assert len(passed) == 3

    def test_reset_clears_history(self):
        nf = NoveltyFilter()
        nf.filter([_make_event()])
        assert len(nf._signature_history) > 0
        nf.reset()
        assert len(nf._signature_history) == 0
        assert len(nf._signature_counts) == 0

    def test_compute_signature_deterministic(self):
        event = _make_event(source='src', modality='mod', severity='info',
                            data={'alpha': 1, 'beta': 2})
        sig1 = NoveltyFilter._compute_signature(event)
        sig2 = NoveltyFilter._compute_signature(event)
        assert sig1 == sig2
        assert 'src' in sig1
        assert 'mod' in sig1

    def test_compute_signature_different_for_different_events(self):
        e1 = _make_event(source='a', modality='m')
        e2 = _make_event(source='b', modality='m')
        assert NoveltyFilter._compute_signature(e1) != \
               NoveltyFilter._compute_signature(e2)

    def test_pass_rate_in_state(self):
        nf = NoveltyFilter()
        nf.filter([_make_event()])
        state = nf.get_state()
        assert state['pass_rate'] == 1.0

    def test_filter_empty_list(self):
        nf = NoveltyFilter()
        passed = nf.filter([])
        assert passed == []
        assert nf._total_received == 0


# ═══════════════════════════════════════════════════════════════════════
# SensoryMemory (P1.15)
# ═══════════════════════════════════════════════════════════════════════

class TestSensoryMemory:
    """Tests for the SensoryMemory class."""

    def test_default_init(self):
        sm = SensoryMemory()
        assert sm.buffer_size == 1000
        assert sm.retention_seconds == 60.0
        assert sm._total_stored == 0

    def test_custom_init(self):
        sm = SensoryMemory(buffer_size=500, retention_seconds=30.0)
        assert sm.buffer_size == 500
        assert sm.retention_seconds == 30.0

    def test_from_yaml(self):
        config = {
            'sensor_systems': {
                'sensory_memory': {
                    'buffer_size': 2000,
                    'retention_seconds': 120.0,
                }
            }
        }
        sm = SensoryMemory.from_yaml(config)
        assert sm.buffer_size == 2000
        assert sm.retention_seconds == 120.0

    def test_from_yaml_empty_config(self):
        sm = SensoryMemory.from_yaml({})
        assert sm.buffer_size == 1000
        assert sm.retention_seconds == 60.0

    def test_get_state(self):
        sm = SensoryMemory()
        state = sm.get_state()
        assert isinstance(state, dict)
        assert state['name'] == 'SensoryMemory'
        assert 'buffer_size' in state
        assert 'retention_seconds' in state
        assert 'current_size' in state
        assert 'total_stored' in state
        assert 'oldest_event' in state
        assert 'newest_event' in state
        assert state['oldest_event'] is None  # Empty buffer

    def test_store_and_get_all(self):
        sm = SensoryMemory()
        events = [_make_event(source='s1'), _make_event(source='s2')]
        sm.store(events)
        assert sm._total_stored == 2
        all_events = sm.get_all()
        assert len(all_events) == 2

    def test_get_recent(self):
        sm = SensoryMemory()
        now = time.time()
        old_event = _make_event(timestamp=now - 100)
        recent_event = _make_event(timestamp=now)
        sm.store([old_event, recent_event])

        recent = sm.get_recent(seconds=10.0)
        assert len(recent) == 1
        assert recent[0]['timestamp'] == now

    def test_get_by_source(self):
        sm = SensoryMemory()
        sm.store([
            _make_event(source='alpha'),
            _make_event(source='beta'),
            _make_event(source='alpha'),
        ])
        alpha_events = sm.get_by_source('alpha', seconds=60.0)
        assert len(alpha_events) == 2

    def test_get_by_modality(self):
        sm = SensoryMemory()
        sm.store([
            _make_event(modality='touch'),
            _make_event(modality='error_signal'),
            _make_event(modality='touch'),
        ])
        touch_events = sm.get_by_modality('touch', seconds=60.0)
        assert len(touch_events) == 2

    def test_get_by_severity(self):
        sm = SensoryMemory()
        sm.store([
            _make_event(severity='info'),
            _make_event(severity='warning'),
            _make_event(severity='error'),
            _make_event(severity='critical'),
        ])
        warnings_plus = sm.get_by_severity('warning')
        assert len(warnings_plus) == 3  # warning, error, critical
        errors_plus = sm.get_by_severity('error')
        assert len(errors_plus) == 2  # error, critical

    def test_clear(self):
        sm = SensoryMemory()
        sm.store([_make_event()])
        assert len(sm.get_all()) == 1
        sm.clear()
        assert len(sm.get_all()) == 0

    def test_prune_old(self):
        sm = SensoryMemory(retention_seconds=5.0)
        now = time.time()
        sm.store([
            _make_event(timestamp=now - 100),  # old
            _make_event(timestamp=now),          # fresh
        ])
        sm.prune_old()
        all_events = sm.get_all()
        assert len(all_events) == 1

    def test_buffer_size_limit(self):
        """Buffer should not exceed maxlen."""
        sm = SensoryMemory(buffer_size=5)
        sm.store([_make_event() for _ in range(10)])
        assert len(sm.get_all()) == 5
        assert sm._total_stored == 10

    def test_get_state_with_events(self):
        sm = SensoryMemory()
        now = time.time()
        sm.store([_make_event(timestamp=now)])
        state = sm.get_state()
        assert state['current_size'] == 1
        assert state['oldest_event'] == now
        assert state['newest_event'] == now
        assert state['total_stored'] == 1
