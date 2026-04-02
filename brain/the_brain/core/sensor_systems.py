"""
Sensor Systems (V2 Phase 1: P1.3-6, P1.9-15)

Eleven subsystems that give Tahlamus environmental awareness through
polling-based sensors, event fusion, and attention-driven sampling:

1. SystemVitalsSensor (P1.3):
   Monitors CPU, RAM, Disk, Network via psutil (optional dependency).
   Anomaly detection via rolling average + 2-sigma threshold.
   Maps to 'touch' (pain on overload) and 'proprioception' modalities.

2. FileSystemSensor (P1.4):
   Watches configurable paths for file events (created, modified, deleted).
   Uses polling with os.path.getmtime() — no watchdog dependency.
   Maps to 'tool_trace' modality.

3. ProcessSensor (P1.5):
   Monitors system processes by port (5003, 8007, 8000, 8766).
   Health check via socket connect.  Status: running, degraded, down.
   Maps to 'interoception' modality.

4. LogSensor (P1.6):
   Tail-based watcher for log files.  Pattern recognition for
   ERROR, WARNING, Exception, Traceback.  Maps to 'error_signal'.

5. GitActivitySensor (P1.9):
   Periodic git log analysis on configured repos.  Detects new commits,
   branch changes, uncommitted changes.  Maps to 'tool_trace'.

6. SensorRegistry (P1.10):
   Central registry for all sensors.  Priority queue for events.
   Rate limiting per sensor.

7. SensorFusion (P1.11):
   Fuses multi-sensor events into coherent perceptions.
   Time-window correlation (events within N seconds = related).

8. PerceptionPipeline (P1.12):
   Connects SensorFusion -> SensoryPreprocessor -> CognitiveLoop.
   New sensor events trigger asynchronous mini cognitive loops.

9. AttentionDrivenSampling (P1.13):
   Attention weights from CognitiveLoop steer sensor polling frequencies.
   High attention on error_signal -> LogSensor polls 5x more.

10. NoveltyFilter (P1.14):
    Only prediction errors (unexpected events) reach the cognitive loop.
    Known, expected patterns are filtered.

11. SensoryMemory (P1.15):
    Ring buffer (deque, 1000 events, ~60s) for ALL sensor events
    before filtering.  Allows retrospective analysis.
"""

import logging
import math
import os
import re
import socket
import subprocess
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# Optional dependency: psutil
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

logger = logging.getLogger('brain.sensors')


# ─── Common Dataclasses ─────────────────────────────────────────────────────

@dataclass
class SensorEvent:
    """Standard event emitted by all sensors."""
    timestamp: float
    source: str           # Sensor name, e.g. 'system_vitals', 'file_system'
    modality: str         # Brain modality: 'touch', 'tool_trace', etc.
    data: Dict[str, Any]
    severity: str = 'info'   # 'info', 'warning', 'error', 'critical'
    priority: float = 0.5    # 0.0 (low) to 1.0 (urgent)

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'source': self.source,
            'modality': self.modality,
            'data': self.data,
            'severity': self.severity,
            'priority': round(self.priority, 3),
        }


@dataclass
class FusedPerception:
    """Result of fusing multiple correlated sensor events."""
    events: List[SensorEvent]
    interpretation: str
    confidence: float
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'events': [e.to_dict() for e in self.events],
            'interpretation': self.interpretation,
            'confidence': round(self.confidence, 3),
            'timestamp': self.timestamp,
            'event_count': len(self.events),
        }


# Severity → priority mapping
_SEVERITY_PRIORITY = {
    'info': 0.2,
    'warning': 0.5,
    'error': 0.8,
    'critical': 1.0,
}


# ─── P1.3: System Vitals Sensor ─────────────────────────────────────────────

class SystemVitalsSensor:
    """
    Monitors CPU, RAM, Disk, Network via psutil (P1.3).

    Anomaly detection via rolling average + configurable sigma threshold.
    Produces SensorEvents mapped to 'touch' (pain on overload) and
    'proprioception' (body awareness) modalities.
    """

    def __init__(
        self,
        poll_interval_seconds: float = 10.0,
        anomaly_window: int = 30,
        sigma_threshold: float = 2.0,
    ):
        """
        Args:
            poll_interval_seconds: How often to poll vitals.
            anomaly_window: Number of samples for rolling average.
            sigma_threshold: Standard deviations above mean to flag anomaly.
        """
        self.poll_interval_seconds = poll_interval_seconds
        self.anomaly_window = anomaly_window
        self.sigma_threshold = sigma_threshold

        # Rolling histories keyed by metric name
        self._histories: Dict[str, deque] = {
            'cpu_percent': deque(maxlen=anomaly_window),
            'ram_percent': deque(maxlen=anomaly_window),
            'disk_percent': deque(maxlen=anomaly_window),
            'net_bytes_sent': deque(maxlen=anomaly_window),
            'net_bytes_recv': deque(maxlen=anomaly_window),
        }

        self._last_poll: float = 0.0
        self._total_reads: int = 0
        self._total_anomalies: int = 0

    def read(self) -> List[SensorEvent]:
        """
        Read current system vitals and return sensor events.

        Returns one event per anomaly detected, plus a periodic
        proprioception event with all current values.
        """
        now = time.time()
        self._total_reads += 1
        events: List[SensorEvent] = []

        vitals = self._collect_vitals()

        # Update histories
        for metric, value in vitals.items():
            if metric in self._histories:
                self._histories[metric].append(value)

        # Check for anomalies
        anomalies: Dict[str, float] = {}
        for metric, value in vitals.items():
            if metric not in self._histories:
                continue
            history = list(self._histories[metric])
            if len(history) < 3:
                continue
            mean = statistics.mean(history)
            try:
                stdev = statistics.stdev(history)
            except statistics.StatisticsError:
                stdev = 0.0

            if stdev > 0 and (value - mean) > self.sigma_threshold * stdev:
                anomalies[metric] = value
                self._total_anomalies += 1

        # Emit anomaly events as 'touch' modality (pain signal)
        if anomalies:
            severity = 'error' if any(v > 90 for v in anomalies.values()) else 'warning'
            events.append(SensorEvent(
                timestamp=now,
                source='system_vitals',
                modality='touch',
                data={
                    'anomalies': anomalies,
                    'vitals': vitals,
                    'message': f"Anomaly detected: {', '.join(anomalies.keys())}",
                },
                severity=severity,
                priority=_SEVERITY_PRIORITY.get(severity, 0.5),
            ))

        # Always emit a proprioception event with current readings
        events.append(SensorEvent(
            timestamp=now,
            source='system_vitals',
            modality='proprioception',
            data=vitals,
            severity='info',
            priority=0.1,
        ))

        self._last_poll = now
        return events

    def _collect_vitals(self) -> Dict[str, float]:
        """Collect system vitals via psutil, or return zeros if unavailable."""
        if not HAS_PSUTIL:
            return {
                'cpu_percent': 0.0,
                'ram_percent': 0.0,
                'disk_percent': 0.0,
                'net_bytes_sent': 0.0,
                'net_bytes_recv': 0.0,
            }

        try:
            cpu = psutil.cpu_percent(interval=0)
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent if os.name != 'nt' else psutil.disk_usage('C:\\').percent
            net = psutil.net_io_counters()
            return {
                'cpu_percent': float(cpu),
                'ram_percent': float(ram),
                'disk_percent': float(disk),
                'net_bytes_sent': float(net.bytes_sent),
                'net_bytes_recv': float(net.bytes_recv),
            }
        except Exception as e:
            logger.warning("Failed to collect vitals: %s", e)
            return {
                'cpu_percent': 0.0,
                'ram_percent': 0.0,
                'disk_percent': 0.0,
                'net_bytes_sent': 0.0,
                'net_bytes_recv': 0.0,
            }

    def get_state(self) -> Dict[str, Any]:
        """Get sensor state for dashboard."""
        return {
            'name': 'SystemVitalsSensor',
            'has_psutil': HAS_PSUTIL,
            'poll_interval_seconds': self.poll_interval_seconds,
            'anomaly_window': self.anomaly_window,
            'sigma_threshold': self.sigma_threshold,
            'total_reads': self._total_reads,
            'total_anomalies': self._total_anomalies,
            'last_poll': self._last_poll,
            'history_lengths': {
                k: len(v) for k, v in self._histories.items()
            },
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'SystemVitalsSensor':
        """Create from YAML config dict."""
        s = config.get('sensor_systems', {}).get('system_vitals', {})
        return cls(
            poll_interval_seconds=s.get('poll_interval_seconds', 10.0),
            anomaly_window=s.get('anomaly_window', 30),
            sigma_threshold=s.get('sigma_threshold', 2.0),
        )


# ─── P1.4: File System Sensor ───────────────────────────────────────────────

@dataclass
class FileEvent:
    """A file system change event."""
    event_type: str    # 'created', 'modified', 'deleted'
    path: str
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_type': self.event_type,
            'path': self.path,
            'timestamp': self.timestamp,
        }


class FileSystemSensor:
    """
    Watches configurable paths for file events via polling (P1.4).

    Uses os.path.getmtime() to detect changes — no watchdog dependency.
    Maps to 'tool_trace' modality.  Event-Bus compatible via internal queue.
    """

    def __init__(
        self,
        watch_paths: Optional[List[str]] = None,
        poll_interval: float = 5.0,
        max_events: int = 1000,
    ):
        """
        Args:
            watch_paths: List of directories/files to watch.
            poll_interval: Seconds between polls.
            max_events: Maximum events to keep in the internal queue.
        """
        self.watch_paths = list(watch_paths or [])
        self.poll_interval = poll_interval
        self.max_events = max_events

        # path -> last known mtime
        self._known_files: Dict[str, float] = {}
        self._event_queue: deque = deque(maxlen=max_events)
        self._last_poll: float = 0.0
        self._total_events: int = 0
        self._initialized: bool = False

    def read(self) -> List[SensorEvent]:
        """
        Poll watched paths and return sensor events for changes.

        On first call, builds a baseline snapshot (no events emitted).
        Subsequent calls detect created/modified/deleted files.
        """
        now = time.time()
        events: List[SensorEvent] = []

        current_files: Dict[str, float] = {}
        for watch_path in self.watch_paths:
            self._scan_path(watch_path, current_files)

        if not self._initialized:
            # First run: baseline
            self._known_files = current_files
            self._initialized = True
            self._last_poll = now
            return events

        # Detect changes
        file_events: List[FileEvent] = []

        # New or modified files
        for path, mtime in current_files.items():
            if path not in self._known_files:
                file_events.append(FileEvent('created', path, now))
            elif mtime > self._known_files[path]:
                file_events.append(FileEvent('modified', path, now))

        # Deleted files
        for path in self._known_files:
            if path not in current_files:
                file_events.append(FileEvent('deleted', path, now))

        # Convert to SensorEvents
        for fe in file_events:
            severity = 'warning' if fe.event_type == 'deleted' else 'info'
            event = SensorEvent(
                timestamp=now,
                source='file_system',
                modality='tool_trace',
                data=fe.to_dict(),
                severity=severity,
                priority=_SEVERITY_PRIORITY.get(severity, 0.2),
            )
            events.append(event)
            self._event_queue.append(event)
            self._total_events += 1

        self._known_files = current_files
        self._last_poll = now
        return events

    def _scan_path(self, path: str, result: Dict[str, float]):
        """Scan a path and populate result with file -> mtime mapping."""
        try:
            if os.path.isfile(path):
                result[path] = os.path.getmtime(path)
            elif os.path.isdir(path):
                for entry in os.listdir(path):
                    full = os.path.join(path, entry)
                    if os.path.isfile(full):
                        try:
                            result[full] = os.path.getmtime(full)
                        except OSError:
                            pass
        except OSError as e:
            logger.debug("Cannot scan path '%s': %s", path, e)

    def get_queued_events(self) -> List[Dict[str, Any]]:
        """Get all queued events (for event-bus consumption)."""
        return [e.to_dict() for e in self._event_queue]

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': 'FileSystemSensor',
            'watch_paths': self.watch_paths,
            'poll_interval': self.poll_interval,
            'tracked_files': len(self._known_files),
            'queued_events': len(self._event_queue),
            'total_events': self._total_events,
            'last_poll': self._last_poll,
            'initialized': self._initialized,
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'FileSystemSensor':
        s = config.get('sensor_systems', {}).get('file_system', {})
        return cls(
            watch_paths=s.get('watch_paths', []),
            poll_interval=s.get('poll_interval', 5.0),
            max_events=s.get('max_events', 1000),
        )


# ─── P1.5: Process Sensor ───────────────────────────────────────────────────

class ProcessStatus(Enum):
    """Status of a monitored process."""
    RUNNING = "running"
    DEGRADED = "degraded"
    DOWN = "down"


class ProcessSensor:
    """
    Monitors system processes by port (P1.5).

    Health check via socket connect.  Tracks status transitions
    (running -> degraded -> down).  Maps to 'interoception' modality.
    """

    def __init__(
        self,
        monitored_ports: Optional[Dict[str, int]] = None,
        check_interval: float = 15.0,
        connect_timeout: float = 2.0,
    ):
        """
        Args:
            monitored_ports: Dict of service_name -> port number.
            check_interval: Seconds between health checks.
            connect_timeout: Socket connect timeout in seconds.
        """
        self.monitored_ports = dict(monitored_ports or {
            'unified_brain': 5003,
            'dashboard': 5000,
            'swarm': 5002,
        })
        self.check_interval = check_interval
        self.connect_timeout = connect_timeout

        # service_name -> current status
        self._status: Dict[str, ProcessStatus] = {
            name: ProcessStatus.DOWN for name in self.monitored_ports
        }
        # service_name -> consecutive failures
        self._failure_counts: Dict[str, int] = {
            name: 0 for name in self.monitored_ports
        }

        self._last_check: float = 0.0
        self._total_checks: int = 0
        self._total_status_changes: int = 0

    def read(self) -> List[SensorEvent]:
        """Check all monitored ports and return status events."""
        now = time.time()
        self._total_checks += 1
        events: List[SensorEvent] = []

        for name, port in self.monitored_ports.items():
            is_up = self._check_port(port)
            old_status = self._status[name]

            if is_up:
                self._failure_counts[name] = 0
                new_status = ProcessStatus.RUNNING
            else:
                self._failure_counts[name] += 1
                if self._failure_counts[name] >= 3:
                    new_status = ProcessStatus.DOWN
                else:
                    new_status = ProcessStatus.DEGRADED

            # Emit event on status change
            if new_status != old_status:
                self._total_status_changes += 1
                severity = 'info'
                if new_status == ProcessStatus.DOWN:
                    severity = 'error'
                elif new_status == ProcessStatus.DEGRADED:
                    severity = 'warning'

                events.append(SensorEvent(
                    timestamp=now,
                    source='process_sensor',
                    modality='interoception',
                    data={
                        'service': name,
                        'port': port,
                        'old_status': old_status.value,
                        'new_status': new_status.value,
                        'consecutive_failures': self._failure_counts[name],
                    },
                    severity=severity,
                    priority=_SEVERITY_PRIORITY.get(severity, 0.5),
                ))

            self._status[name] = new_status

        self._last_check = now
        return events

    def _check_port(self, port: int) -> bool:
        """Check if a port is accepting connections."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.connect_timeout)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            return result == 0
        except (OSError, socket.error):
            return False

    def get_service_status(self) -> Dict[str, str]:
        """Get current status of all monitored services."""
        return {name: status.value for name, status in self._status.items()}

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': 'ProcessSensor',
            'monitored_ports': self.monitored_ports,
            'check_interval': self.check_interval,
            'service_status': self.get_service_status(),
            'failure_counts': dict(self._failure_counts),
            'total_checks': self._total_checks,
            'total_status_changes': self._total_status_changes,
            'last_check': self._last_check,
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'ProcessSensor':
        s = config.get('sensor_systems', {}).get('process_sensor', {})
        return cls(
            monitored_ports=s.get('monitored_ports', None),
            check_interval=s.get('check_interval', 15.0),
            connect_timeout=s.get('connect_timeout', 2.0),
        )


# ─── P1.6: Log Sensor ───────────────────────────────────────────────────────

# Default severity patterns
_DEFAULT_LOG_PATTERNS = {
    'critical': r'CRITICAL|FATAL',
    'error': r'ERROR|Exception|Traceback',
    'warning': r'WARNING|WARN',
}


class LogSensor:
    """
    Tail-based watcher for log files (P1.6).

    Pattern recognition for ERROR, WARNING, Exception, Traceback.
    Maps to 'error_signal' modality.  Prioritised by severity.
    """

    def __init__(
        self,
        log_paths: Optional[List[str]] = None,
        patterns: Optional[Dict[str, str]] = None,
        tail_lines: int = 100,
    ):
        """
        Args:
            log_paths: List of log file paths to monitor.
            patterns: Dict of severity -> regex pattern.
            tail_lines: Number of lines to read from the end of each file.
        """
        self.log_paths = list(log_paths or [])
        self.tail_lines = tail_lines

        raw_patterns = dict(patterns or _DEFAULT_LOG_PATTERNS)
        self._compiled_patterns: Dict[str, re.Pattern] = {
            severity: re.compile(pattern, re.IGNORECASE)
            for severity, pattern in raw_patterns.items()
        }

        # Track last read position per file (byte offset)
        self._file_positions: Dict[str, int] = {}
        self._total_reads: int = 0
        self._total_matches: int = 0

    def read(self) -> List[SensorEvent]:
        """Read new lines from monitored log files and detect patterns."""
        now = time.time()
        self._total_reads += 1
        events: List[SensorEvent] = []

        for log_path in self.log_paths:
            new_lines = self._read_new_lines(log_path)
            for line in new_lines:
                matched_severity = self._match_severity(line)
                if matched_severity:
                    self._total_matches += 1
                    events.append(SensorEvent(
                        timestamp=now,
                        source='log_sensor',
                        modality='error_signal',
                        data={
                            'log_path': log_path,
                            'line': line.strip()[:500],  # Truncate long lines
                            'matched_severity': matched_severity,
                        },
                        severity=matched_severity,
                        priority=_SEVERITY_PRIORITY.get(matched_severity, 0.5),
                    ))

        return events

    def _read_new_lines(self, path: str) -> List[str]:
        """Read new lines from a log file since last position."""
        try:
            file_size = os.path.getsize(path)
        except OSError:
            return []

        last_pos = self._file_positions.get(path, 0)

        # If file was truncated/rotated, reset position
        if file_size < last_pos:
            last_pos = 0

        if file_size == last_pos:
            return []

        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                if last_pos == 0 and file_size > 0:
                    # First read: tail the last N lines
                    lines = self._tail_file(f, self.tail_lines)
                    self._file_positions[path] = file_size
                    return lines
                else:
                    f.seek(last_pos)
                    lines = f.readlines()
                    self._file_positions[path] = f.tell()
                    return lines
        except OSError as e:
            logger.debug("Cannot read log file '%s': %s", path, e)
            return []

    @staticmethod
    def _tail_file(f, n: int) -> List[str]:
        """Read the last n lines from a file object."""
        lines = f.readlines()
        return lines[-n:] if len(lines) > n else lines

    def _match_severity(self, line: str) -> Optional[str]:
        """Match a log line against severity patterns, highest severity first."""
        for severity in ('critical', 'error', 'warning'):
            pattern = self._compiled_patterns.get(severity)
            if pattern and pattern.search(line):
                return severity
        return None

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': 'LogSensor',
            'log_paths': self.log_paths,
            'tail_lines': self.tail_lines,
            'pattern_count': len(self._compiled_patterns),
            'tracked_files': len(self._file_positions),
            'total_reads': self._total_reads,
            'total_matches': self._total_matches,
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'LogSensor':
        s = config.get('sensor_systems', {}).get('log_sensor', {})
        return cls(
            log_paths=s.get('log_paths', []),
            patterns=s.get('patterns', None),
            tail_lines=s.get('tail_lines', 100),
        )


# ─── P1.9: Git Activity Sensor ──────────────────────────────────────────────

class GitActivitySensor:
    """
    Periodic git log analysis on configured repos (P1.9).

    Detects: new commits, branch changes, uncommitted changes.
    Maps to 'tool_trace' modality.
    """

    def __init__(
        self,
        repo_paths: Optional[List[str]] = None,
        check_interval: float = 300.0,
        since_minutes: int = 60,
    ):
        """
        Args:
            repo_paths: List of git repository root paths.
            check_interval: Seconds between git checks.
            since_minutes: Look at git log for commits in the last N minutes.
        """
        self.repo_paths = list(repo_paths or [])
        self.check_interval = check_interval
        self.since_minutes = since_minutes

        # repo_path -> last known branch
        self._known_branches: Dict[str, str] = {}
        # repo_path -> last known HEAD commit hash
        self._known_heads: Dict[str, str] = {}

        self._last_check: float = 0.0
        self._total_reads: int = 0
        self._total_events: int = 0

    def read(self) -> List[SensorEvent]:
        """Check configured repos for git activity."""
        now = time.time()
        self._total_reads += 1
        events: List[SensorEvent] = []

        for repo_path in self.repo_paths:
            repo_events = self._check_repo(repo_path, now)
            events.extend(repo_events)

        self._last_check = now
        return events

    def _check_repo(self, repo_path: str, now: float) -> List[SensorEvent]:
        """Check a single git repo for activity."""
        events: List[SensorEvent] = []

        if not os.path.isdir(os.path.join(repo_path, '.git')):
            return events

        # Check current branch
        current_branch = self._run_git(repo_path, ['rev-parse', '--abbrev-ref', 'HEAD'])
        if current_branch:
            old_branch = self._known_branches.get(repo_path)
            if old_branch is not None and current_branch != old_branch:
                self._total_events += 1
                events.append(SensorEvent(
                    timestamp=now,
                    source='git_activity',
                    modality='tool_trace',
                    data={
                        'repo': repo_path,
                        'event_type': 'branch_change',
                        'old_branch': old_branch,
                        'new_branch': current_branch,
                    },
                    severity='info',
                    priority=0.3,
                ))
            self._known_branches[repo_path] = current_branch

        # Check HEAD commit
        current_head = self._run_git(repo_path, ['rev-parse', 'HEAD'])
        if current_head:
            old_head = self._known_heads.get(repo_path)
            if old_head is not None and current_head != old_head:
                # New commit(s) detected
                commit_count = self._run_git(
                    repo_path,
                    ['rev-list', '--count', f'{old_head}..{current_head}'],
                )
                self._total_events += 1
                events.append(SensorEvent(
                    timestamp=now,
                    source='git_activity',
                    modality='tool_trace',
                    data={
                        'repo': repo_path,
                        'event_type': 'new_commits',
                        'old_head': old_head[:8],
                        'new_head': current_head[:8],
                        'commit_count': int(commit_count) if commit_count else 1,
                    },
                    severity='info',
                    priority=0.3,
                ))
            self._known_heads[repo_path] = current_head

        # Check for uncommitted changes
        status_output = self._run_git(repo_path, ['status', '--porcelain'])
        if status_output and status_output.strip():
            changed_files = len(status_output.strip().split('\n'))
            self._total_events += 1
            events.append(SensorEvent(
                timestamp=now,
                source='git_activity',
                modality='tool_trace',
                data={
                    'repo': repo_path,
                    'event_type': 'uncommitted_changes',
                    'changed_files': changed_files,
                },
                severity='info',
                priority=0.2,
            ))

        return events

    @staticmethod
    def _run_git(repo_path: str, args: List[str]) -> Optional[str]:
        """Run a git command and return stripped stdout, or None on failure."""
        try:
            result = subprocess.run(
                ['git'] + args,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': 'GitActivitySensor',
            'repo_paths': self.repo_paths,
            'check_interval': self.check_interval,
            'since_minutes': self.since_minutes,
            'known_branches': dict(self._known_branches),
            'known_heads': {k: v[:8] for k, v in self._known_heads.items()},
            'total_reads': self._total_reads,
            'total_events': self._total_events,
            'last_check': self._last_check,
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'GitActivitySensor':
        s = config.get('sensor_systems', {}).get('git_activity', {})
        return cls(
            repo_paths=s.get('repo_paths', []),
            check_interval=s.get('check_interval', 300.0),
            since_minutes=s.get('since_minutes', 60),
        )


# ─── P10.6: Minibook Sensor ─────────────────────────────────────────────────

class MinibookSensor:
    """
    Polls Minibook API for @mentions, replies, and thread updates (Phase 10, Task 6).

    Converts Minibook notifications into SensorEvents mapped to the
    'social_signal' modality.  Gracefully handles Minibook being offline.

    Works with MinibookClient from core.minibook_client for the actual
    HTTP communication.
    """

    def __init__(
        self,
        minibook_client=None,
        poll_interval: float = 30.0,
    ):
        """
        Args:
            minibook_client: Optional MinibookClient instance.
                If None, sensor operates in stub mode.
            poll_interval: Seconds between Minibook polls.
        """
        self._client = minibook_client
        self.poll_interval = poll_interval
        self._last_poll: float = 0.0
        self._last_notification_ts: float = 0.0
        self._total_reads: int = 0
        self._total_events: int = 0

    def read(self) -> List[SensorEvent]:
        """
        Poll Minibook for new notifications and return SensorEvents.

        Returns empty list if Minibook is offline or client is None.
        Respects poll_interval to avoid hammering the server.
        """
        now = time.time()
        self._total_reads += 1
        events: List[SensorEvent] = []

        if self._client is None:
            return events

        # Respect poll interval
        if now - self._last_poll < self.poll_interval:
            return events

        self._last_poll = now

        try:
            notifications = self._client.check_notifications(
                since=self._last_notification_ts if self._last_notification_ts > 0 else None,
                limit=50,
            )

            for notif in notifications:
                # Update timestamp watermark
                if notif.timestamp > self._last_notification_ts:
                    self._last_notification_ts = notif.timestamp

                # Map notification type to severity/priority
                severity, priority = self._classify_notification(notif)

                self._total_events += 1
                events.append(SensorEvent(
                    timestamp=now,
                    source='minibook',
                    modality='social_signal',
                    data={
                        'notification_id': notif.notification_id,
                        'notification_type': notif.notification_type,
                        'sender_name': notif.sender_name,
                        'sender_id': notif.sender_id,
                        'content': notif.content[:500],  # Truncate long content
                        'post_id': notif.post_id,
                        'project_id': notif.project_id,
                        'thread_id': notif.thread_id,
                        'social_signals': notif.to_social_signals(),
                    },
                    severity=severity,
                    priority=priority,
                ))

        except Exception as e:
            logger.debug("MinibookSensor poll error: %s", e)

        return events

    @staticmethod
    def _classify_notification(notif) -> Tuple[str, float]:
        """Map notification type to severity and priority."""
        type_map = {
            'mention': ('warning', 0.7),    # @mentions are high priority
            'reply': ('info', 0.5),          # Replies are moderate
            'thread_update': ('info', 0.3),  # Thread updates are low
            'system': ('info', 0.2),         # System messages are lowest
        }
        return type_map.get(notif.notification_type, ('info', 0.3))

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': 'MinibookSensor',
            'has_client': self._client is not None,
            'client_online': (
                self._client.is_online if self._client is not None else False
            ),
            'poll_interval': self.poll_interval,
            'last_poll': self._last_poll,
            'last_notification_ts': self._last_notification_ts,
            'total_reads': self._total_reads,
            'total_events': self._total_events,
        }

    @classmethod
    def from_yaml(cls, config: Dict, minibook_client=None) -> 'MinibookSensor':
        s = config.get('minibook', {})
        return cls(
            minibook_client=minibook_client,
            poll_interval=s.get('poll_interval', 30.0),
        )


# ─── P1.10: Sensor Registry ─────────────────────────────────────────────────

class SensorRegistry:
    """
    Central registry for all sensors (P1.10).

    Provides: register(sensor), start_all(), stop_all(), get_events(since).
    Priority queue (sorted list) for events.  Rate limiting per sensor.
    """

    def __init__(
        self,
        max_events_per_second: float = 100.0,
        event_buffer_size: int = 10000,
    ):
        """
        Args:
            max_events_per_second: Global rate limit for events.
            event_buffer_size: Maximum events to keep in the buffer.
        """
        self.max_events_per_second = max_events_per_second
        self.event_buffer_size = event_buffer_size

        # Registered sensors: name -> sensor object
        self._sensors: Dict[str, Any] = {}
        # Event buffer (priority sorted: highest priority first)
        self._event_buffer: deque = deque(maxlen=event_buffer_size)
        # Rate limiting: source -> deque of timestamps
        self._rate_windows: Dict[str, deque] = {}

        self._running: bool = False
        self._total_events_received: int = 0
        self._total_events_dropped: int = 0

    def register(self, name: str, sensor: Any):
        """
        Register a sensor by name.

        The sensor must have a read() method that returns List[SensorEvent].
        """
        self._sensors[name] = sensor
        self._rate_windows[name] = deque(maxlen=1000)
        logger.info("Registered sensor '%s'", name)

    def unregister(self, name: str):
        """Remove a sensor from the registry."""
        if name in self._sensors:
            del self._sensors[name]
            if name in self._rate_windows:
                del self._rate_windows[name]
            logger.info("Unregistered sensor '%s'", name)

    def poll_all(self) -> List[SensorEvent]:
        """
        Poll all registered sensors and collect events.

        Applies rate limiting per sensor source.  Returns events
        sorted by priority (highest first).
        """
        all_events: List[SensorEvent] = []
        now = time.time()

        for name, sensor in self._sensors.items():
            try:
                events = sensor.read()
                for event in events:
                    if self._check_rate_limit(event.source, now):
                        all_events.append(event)
                        self._event_buffer.append(event)
                        self._total_events_received += 1
                    else:
                        self._total_events_dropped += 1
            except Exception as e:
                logger.warning("Error polling sensor '%s': %s", name, e)

        # Sort by priority descending
        all_events.sort(key=lambda e: e.priority, reverse=True)
        return all_events

    def _check_rate_limit(self, source: str, now: float) -> bool:
        """Check if a sensor source is within its rate limit."""
        if source not in self._rate_windows:
            self._rate_windows[source] = deque(maxlen=1000)

        window = self._rate_windows[source]
        cutoff = now - 1.0  # 1-second window

        # Prune old entries
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= self.max_events_per_second:
            return False

        window.append(now)
        return True

    def get_events(self, since: float = 0.0) -> List[Dict[str, Any]]:
        """
        Get events since a given timestamp.

        Args:
            since: Unix timestamp; returns events after this time.
                   If 0, returns all buffered events.
        """
        result = []
        for event in self._event_buffer:
            if event.timestamp > since:
                result.append(event.to_dict())
        return result

    def start_all(self):
        """Mark the registry as running (sensors are polled externally)."""
        self._running = True
        logger.info("SensorRegistry started with %d sensors", len(self._sensors))

    def stop_all(self):
        """Mark the registry as stopped."""
        self._running = False
        logger.info("SensorRegistry stopped")

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': 'SensorRegistry',
            'running': self._running,
            'registered_sensors': list(self._sensors.keys()),
            'sensor_count': len(self._sensors),
            'max_events_per_second': self.max_events_per_second,
            'event_buffer_size': self.event_buffer_size,
            'buffered_events': len(self._event_buffer),
            'total_events_received': self._total_events_received,
            'total_events_dropped': self._total_events_dropped,
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'SensorRegistry':
        s = config.get('sensor_systems', {}).get('registry', {})
        return cls(
            max_events_per_second=s.get('max_events_per_second', 100.0),
            event_buffer_size=s.get('event_buffer_size', 10000),
        )


# ─── P1.11: Sensor Fusion ───────────────────────────────────────────────────

# Fusion rules: (source_a, source_b) -> interpretation template
_FUSION_RULES: Dict[Tuple[str, str], str] = {
    ('log_sensor', 'process_sensor'): "Service failure detected: log errors correlate with process status change",
    ('system_vitals', 'process_sensor'): "Resource-induced degradation: vitals anomaly correlates with process issues",
    ('system_vitals', 'log_sensor'): "System stress detected: vitals anomaly correlates with log errors",
    ('file_system', 'git_activity'): "Development activity detected: file changes correlate with git activity",
    ('log_sensor', 'log_sensor'): "Error cascade detected: multiple log sources reporting issues",
}


class SensorFusion:
    """
    Fuses multi-sensor events into coherent perceptions (P1.11).

    Time-window correlation: events within correlation_window_seconds
    of each other from different sources are considered related and
    fused into a FusedPerception.
    """

    def __init__(
        self,
        correlation_window_seconds: float = 5.0,
        min_events_for_fusion: int = 2,
    ):
        """
        Args:
            correlation_window_seconds: Events within this window are correlated.
            min_events_for_fusion: Minimum events needed to trigger fusion.
        """
        self.correlation_window_seconds = correlation_window_seconds
        self.min_events_for_fusion = min_events_for_fusion

        self._pending_events: deque = deque(maxlen=500)
        self._total_fusions: int = 0
        self._total_events_processed: int = 0

    def add_events(self, events: List[SensorEvent]):
        """Add new sensor events for correlation analysis."""
        for event in events:
            self._pending_events.append(event)
            self._total_events_processed += 1

    def fuse(self) -> List[FusedPerception]:
        """
        Attempt to fuse pending events into coherent perceptions.

        Groups events by time window, then checks for cross-source
        correlations using built-in fusion rules.

        Returns list of FusedPerception objects.
        """
        if len(self._pending_events) < self.min_events_for_fusion:
            return []

        now = time.time()
        perceptions: List[FusedPerception] = []

        # Get events within the correlation window
        # Python 3.11: deque does NOT support slicing, use list()
        recent = [
            e for e in list(self._pending_events)
            if now - e.timestamp <= self.correlation_window_seconds
        ]

        if len(recent) < self.min_events_for_fusion:
            return []

        # Group by source
        by_source: Dict[str, List[SensorEvent]] = {}
        for event in recent:
            by_source.setdefault(event.source, []).append(event)

        # Check fusion rules for cross-source correlations
        sources = list(by_source.keys())
        fused_event_ids: set = set()

        for i in range(len(sources)):
            for j in range(i, len(sources)):
                src_a, src_b = sources[i], sources[j]
                key = (src_a, src_b)
                rev_key = (src_b, src_a)

                interpretation = _FUSION_RULES.get(key) or _FUSION_RULES.get(rev_key)
                if not interpretation:
                    continue

                # Fuse events from these two sources
                fused_events = by_source[src_a] + (
                    by_source[src_b] if src_b != src_a else []
                )
                if len(fused_events) < self.min_events_for_fusion:
                    continue

                # Calculate confidence based on event count and severity
                max_priority = max(e.priority for e in fused_events)
                confidence = min(1.0, 0.5 + 0.1 * len(fused_events) + 0.2 * max_priority)

                perception = FusedPerception(
                    events=fused_events,
                    interpretation=interpretation,
                    confidence=confidence,
                    timestamp=now,
                )
                perceptions.append(perception)
                self._total_fusions += 1

                # Track which events were fused
                for e in fused_events:
                    fused_event_ids.add(id(e))

        # Remove fused events from pending
        remaining = deque(maxlen=500)
        for e in self._pending_events:
            if id(e) not in fused_event_ids:
                remaining.append(e)
        self._pending_events = remaining

        return perceptions

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': 'SensorFusion',
            'correlation_window_seconds': self.correlation_window_seconds,
            'min_events_for_fusion': self.min_events_for_fusion,
            'pending_events': len(self._pending_events),
            'total_fusions': self._total_fusions,
            'total_events_processed': self._total_events_processed,
            'fusion_rules_count': len(_FUSION_RULES),
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'SensorFusion':
        s = config.get('sensor_systems', {}).get('sensor_fusion', {})
        return cls(
            correlation_window_seconds=s.get('correlation_window_seconds', 5.0),
            min_events_for_fusion=s.get('min_events_for_fusion', 2),
        )


# ─── P1.12: Perception Pipeline ─────────────────────────────────────────────

class PerceptionPipeline:
    """
    Connects SensorFusion -> SensoryPreprocessor -> CognitiveLoop (P1.12).

    New sensor events trigger asynchronous mini cognitive loops.
    The pipeline collects raw events, fuses them, and formats them
    for consumption by the cognitive loop.
    """

    def __init__(
        self,
        pipeline_enabled: bool = True,
        batch_size: int = 10,
    ):
        """
        Args:
            pipeline_enabled: Whether the pipeline is active.
            batch_size: Max events to process per pipeline step.
        """
        self.pipeline_enabled = pipeline_enabled
        self.batch_size = batch_size

        self._fusion: Optional[SensorFusion] = None
        self._incoming_queue: deque = deque(maxlen=1000)
        self._perception_queue: deque = deque(maxlen=200)

        self._total_events_in: int = 0
        self._total_perceptions_out: int = 0
        self._total_steps: int = 0

    def set_fusion(self, fusion: SensorFusion):
        """Attach a SensorFusion instance to the pipeline."""
        self._fusion = fusion

    def ingest(self, events: List[SensorEvent]):
        """
        Ingest raw sensor events into the pipeline.

        Events are queued for the next step() call.
        """
        if not self.pipeline_enabled:
            return

        for event in events:
            self._incoming_queue.append(event)
            self._total_events_in += 1

    def step(self) -> List[Dict[str, Any]]:
        """
        Process one batch through the pipeline.

        1. Take up to batch_size events from the incoming queue
        2. Feed them to SensorFusion
        3. Collect fused perceptions
        4. Format for cognitive loop consumption

        Returns list of perception dicts ready for the cognitive loop.
        """
        if not self.pipeline_enabled:
            return []

        self._total_steps += 1
        results: List[Dict[str, Any]] = []

        # Drain incoming queue (up to batch_size)
        batch: List[SensorEvent] = []
        for _ in range(min(self.batch_size, len(self._incoming_queue))):
            batch.append(self._incoming_queue.popleft())

        if not batch:
            return []

        # Feed to fusion
        if self._fusion:
            self._fusion.add_events(batch)
            perceptions = self._fusion.fuse()
            for p in perceptions:
                p_dict = p.to_dict()
                p_dict['pipeline_step'] = self._total_steps
                self._perception_queue.append(p_dict)
                self._total_perceptions_out += 1
                results.append(p_dict)

        # Also pass through unfused high-priority events
        for event in batch:
            if event.priority >= 0.7:
                event_dict = {
                    'type': 'raw_sensor_event',
                    'event': event.to_dict(),
                    'pipeline_step': self._total_steps,
                }
                results.append(event_dict)

        return results

    def get_recent_perceptions(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get the most recent perceptions from the pipeline."""
        # Python 3.11: deque does NOT support slicing
        return list(self._perception_queue)[-count:]

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': 'PerceptionPipeline',
            'pipeline_enabled': self.pipeline_enabled,
            'batch_size': self.batch_size,
            'incoming_queue_size': len(self._incoming_queue),
            'perception_queue_size': len(self._perception_queue),
            'has_fusion': self._fusion is not None,
            'total_events_in': self._total_events_in,
            'total_perceptions_out': self._total_perceptions_out,
            'total_steps': self._total_steps,
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'PerceptionPipeline':
        s = config.get('sensor_systems', {}).get('perception_pipeline', {})
        return cls(
            pipeline_enabled=s.get('pipeline_enabled', True),
            batch_size=s.get('batch_size', 10),
        )


# ─── P1.13: Attention-Driven Sampling ───────────────────────────────────────

class AttentionDrivenSampling:
    """
    Attention weights steer sensor polling frequencies (P1.13).

    When the cognitive loop has high attention on a modality
    (e.g., 'error_signal'), the corresponding sensor is polled
    more frequently.  This saves resources by reducing polls for
    modalities that are currently uninteresting.
    """

    def __init__(
        self,
        base_multiplier: float = 1.0,
        max_multiplier: float = 5.0,
        min_multiplier: float = 0.2,
    ):
        """
        Args:
            base_multiplier: Default polling rate multiplier.
            max_multiplier: Maximum polling rate increase factor.
            min_multiplier: Minimum polling rate decrease factor.
        """
        self.base_multiplier = base_multiplier
        self.max_multiplier = max_multiplier
        self.min_multiplier = min_multiplier

        # Mapping: modality -> sensor_name (for lookup)
        self._modality_sensor_map: Dict[str, str] = {
            'touch': 'system_vitals',
            'proprioception': 'system_vitals',
            'tool_trace': 'file_system',
            'interoception': 'process_sensor',
            'error_signal': 'log_sensor',
        }

        # Current attention weights from cognitive loop
        self._attention_weights: Dict[str, float] = {}
        # Computed multipliers per sensor
        self._multipliers: Dict[str, float] = {}

        self._total_updates: int = 0

    def update_attention(self, attention_weights: Dict[str, float]):
        """
        Update attention weights from the cognitive loop.

        Args:
            attention_weights: Dict of modality -> attention weight (0-1).
        """
        self._attention_weights = dict(attention_weights)
        self._recompute_multipliers()
        self._total_updates += 1

    def _recompute_multipliers(self):
        """Recompute polling multipliers based on current attention."""
        # Find mean attention for normalization
        values = list(self._attention_weights.values())
        if not values:
            return

        mean_attn = statistics.mean(values) if values else 0.5

        # Compute per-sensor multiplier
        sensor_attentions: Dict[str, List[float]] = {}
        for modality, weight in self._attention_weights.items():
            sensor = self._modality_sensor_map.get(modality)
            if sensor:
                sensor_attentions.setdefault(sensor, []).append(weight)

        for sensor, weights in sensor_attentions.items():
            avg_attention = statistics.mean(weights)
            if mean_attn > 0:
                ratio = avg_attention / mean_attn
            else:
                ratio = 1.0

            multiplier = self.base_multiplier * ratio
            multiplier = max(self.min_multiplier, min(self.max_multiplier, multiplier))
            self._multipliers[sensor] = multiplier

    def get_poll_interval(self, sensor_name: str, base_interval: float) -> float:
        """
        Get the adjusted poll interval for a sensor.

        A higher multiplier means MORE polling (shorter interval).

        Args:
            sensor_name: Name of the sensor.
            base_interval: Default poll interval in seconds.

        Returns:
            Adjusted interval in seconds.
        """
        multiplier = self._multipliers.get(sensor_name, self.base_multiplier)
        if multiplier <= 0:
            multiplier = self.base_multiplier
        return base_interval / multiplier

    def register_modality_sensor(self, modality: str, sensor_name: str):
        """Register a mapping from modality to sensor name."""
        self._modality_sensor_map[modality] = sensor_name

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': 'AttentionDrivenSampling',
            'base_multiplier': self.base_multiplier,
            'max_multiplier': self.max_multiplier,
            'min_multiplier': self.min_multiplier,
            'attention_weights': dict(self._attention_weights),
            'computed_multipliers': {
                k: round(v, 3) for k, v in self._multipliers.items()
            },
            'modality_sensor_map': dict(self._modality_sensor_map),
            'total_updates': self._total_updates,
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'AttentionDrivenSampling':
        s = config.get('sensor_systems', {}).get('attention_sampling', {})
        return cls(
            base_multiplier=s.get('base_multiplier', 1.0),
            max_multiplier=s.get('max_multiplier', 5.0),
            min_multiplier=s.get('min_multiplier', 0.2),
        )


# ─── P1.14: Novelty Filter ──────────────────────────────────────────────────

class NoveltyFilter:
    """
    Only prediction errors (unexpected events) reach the cognitive loop (P1.14).

    Maintains a history of recent event signatures.  If a new event
    closely matches a known pattern, it is filtered out.  Only events
    with novelty above the threshold pass through.
    """

    def __init__(
        self,
        novelty_threshold: float = 0.3,
        history_window: int = 100,
    ):
        """
        Args:
            novelty_threshold: Minimum novelty score (0-1) to pass through.
            history_window: Number of recent event signatures to remember.
        """
        self.novelty_threshold = novelty_threshold
        self.history_window = history_window

        # Ring buffer of recent event signatures
        self._signature_history: deque = deque(maxlen=history_window)
        # Frequency counts: signature -> count
        self._signature_counts: Dict[str, int] = {}

        self._total_received: int = 0
        self._total_passed: int = 0
        self._total_filtered: int = 0

    def filter(self, events: List[SensorEvent]) -> List[SensorEvent]:
        """
        Filter events, passing only novel ones.

        Args:
            events: List of sensor events to filter.

        Returns:
            List of events that pass the novelty threshold.
        """
        passed: List[SensorEvent] = []

        for event in events:
            self._total_received += 1
            signature = self._compute_signature(event)
            novelty = self._compute_novelty(signature)

            if novelty >= self.novelty_threshold:
                passed.append(event)
                self._total_passed += 1
            else:
                self._total_filtered += 1

            # Record signature in history
            self._signature_history.append(signature)
            self._signature_counts[signature] = self._signature_counts.get(signature, 0) + 1

            # Prune old entries from counts when history wraps
            self._prune_counts()

        return passed

    @staticmethod
    def _compute_signature(event: SensorEvent) -> str:
        """
        Compute a hashable signature for an event.

        Combines source, modality, and severity.  Data content is
        abstracted to keys only (not values) to detect structural
        patterns rather than exact duplicates.
        """
        data_keys = ','.join(sorted(event.data.keys())) if event.data else ''
        return f"{event.source}|{event.modality}|{event.severity}|{data_keys}"

    def _compute_novelty(self, signature: str) -> float:
        """
        Compute novelty score for a signature (0=completely expected, 1=novel).

        Based on inverse frequency in the history window.
        """
        count = self._signature_counts.get(signature, 0)
        if count == 0:
            return 1.0

        # Inverse frequency: more common = less novel
        total = len(self._signature_history)
        if total == 0:
            return 1.0

        frequency = count / total
        novelty = 1.0 - frequency
        return max(0.0, min(1.0, novelty))

    def _prune_counts(self):
        """Keep signature counts aligned with current history window."""
        if len(self._signature_counts) > self.history_window * 2:
            # Rebuild counts from current history
            # Python 3.11: deque does NOT support slicing
            current_sigs = list(self._signature_history)
            self._signature_counts.clear()
            for sig in current_sigs:
                self._signature_counts[sig] = self._signature_counts.get(sig, 0) + 1

    def reset(self):
        """Clear all history and counts."""
        self._signature_history.clear()
        self._signature_counts.clear()

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': 'NoveltyFilter',
            'novelty_threshold': self.novelty_threshold,
            'history_window': self.history_window,
            'signatures_tracked': len(self._signature_counts),
            'history_size': len(self._signature_history),
            'total_received': self._total_received,
            'total_passed': self._total_passed,
            'total_filtered': self._total_filtered,
            'pass_rate': (
                round(self._total_passed / max(1, self._total_received), 3)
            ),
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'NoveltyFilter':
        s = config.get('sensor_systems', {}).get('novelty_filter', {})
        return cls(
            novelty_threshold=s.get('novelty_threshold', 0.3),
            history_window=s.get('history_window', 100),
        )


# ─── P1.15: Sensory Memory ──────────────────────────────────────────────────

class SensoryMemory:
    """
    Ring buffer for ALL sensor events before filtering (P1.15).

    Allows retrospective analysis: "What happened in the last 30 seconds?"
    Events are stored in a deque with configurable size and retention.
    """

    def __init__(
        self,
        buffer_size: int = 1000,
        retention_seconds: float = 60.0,
    ):
        """
        Args:
            buffer_size: Maximum number of events in the buffer.
            retention_seconds: Events older than this are pruned on access.
        """
        self.buffer_size = buffer_size
        self.retention_seconds = retention_seconds

        self._buffer: deque = deque(maxlen=buffer_size)
        self._total_stored: int = 0

    def store(self, events: List[SensorEvent]):
        """Store sensor events in the ring buffer."""
        for event in events:
            self._buffer.append(event)
            self._total_stored += 1

    def get_recent(self, seconds: float = 30.0) -> List[Dict[str, Any]]:
        """
        Get events from the last N seconds.

        Args:
            seconds: Time window in seconds.

        Returns:
            List of event dicts within the time window.
        """
        cutoff = time.time() - seconds
        # Python 3.11: deque does NOT support slicing — use list()
        return [
            e.to_dict() for e in list(self._buffer)
            if e.timestamp >= cutoff
        ]

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all events currently in the buffer."""
        # Python 3.11: deque does NOT support slicing
        return [e.to_dict() for e in list(self._buffer)]

    def get_by_source(self, source: str, seconds: float = 60.0) -> List[Dict[str, Any]]:
        """Get events from a specific source within a time window."""
        cutoff = time.time() - seconds
        return [
            e.to_dict() for e in list(self._buffer)
            if e.source == source and e.timestamp >= cutoff
        ]

    def get_by_modality(self, modality: str, seconds: float = 60.0) -> List[Dict[str, Any]]:
        """Get events for a specific modality within a time window."""
        cutoff = time.time() - seconds
        return [
            e.to_dict() for e in list(self._buffer)
            if e.modality == modality and e.timestamp >= cutoff
        ]

    def get_by_severity(self, min_severity: str = 'warning') -> List[Dict[str, Any]]:
        """Get events at or above a minimum severity level."""
        severity_order = {'info': 0, 'warning': 1, 'error': 2, 'critical': 3}
        min_level = severity_order.get(min_severity, 0)
        return [
            e.to_dict() for e in list(self._buffer)
            if severity_order.get(e.severity, 0) >= min_level
        ]

    def clear(self):
        """Clear the buffer."""
        self._buffer.clear()

    def prune_old(self):
        """Remove events older than retention_seconds."""
        cutoff = time.time() - self.retention_seconds
        # Rebuild buffer without old events
        fresh = deque(maxlen=self.buffer_size)
        for event in self._buffer:
            if event.timestamp >= cutoff:
                fresh.append(event)
        self._buffer = fresh

    def get_state(self) -> Dict[str, Any]:
        return {
            'name': 'SensoryMemory',
            'buffer_size': self.buffer_size,
            'retention_seconds': self.retention_seconds,
            'current_size': len(self._buffer),
            'total_stored': self._total_stored,
            'oldest_event': (
                list(self._buffer)[0].timestamp if self._buffer else None
            ),
            'newest_event': (
                list(self._buffer)[-1].timestamp if self._buffer else None
            ),
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'SensoryMemory':
        s = config.get('sensor_systems', {}).get('sensory_memory', {})
        return cls(
            buffer_size=s.get('buffer_size', 1000),
            retention_seconds=s.get('retention_seconds', 60.0),
        )
