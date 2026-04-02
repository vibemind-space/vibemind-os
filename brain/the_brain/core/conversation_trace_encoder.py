"""
Conversation Trace Encoder for Meta-Cognitive Monitoring

Parses agentic conversation logs and encodes them as dimensional vectors
that can be fed into the routing system for self-reflective learning.

Extracts features:
- Tool usage patterns (Read, Write, Bash, etc.)
- Duration and timing
- Error patterns and types
- Clarification requests
- Success/failure signals
- Agent interaction patterns
- Context switches

Encodes to modalities:
- tool_trace: Which tools were used and in what sequence
- temporal_pattern: Timing and duration features
- error_signal: Error types and frequencies
- success_signal: Task completion status
"""

import numpy as np
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import Counter, defaultdict
from pathlib import Path


class ConversationTrace:
    """
    Single conversation trace extracted from log file.
    """

    def __init__(self, log_path: str):
        """Initialize from log file path."""
        self.log_path = log_path
        self.filename = Path(log_path).name

        # Extract session metadata from filename
        # Format: {tool}_{date}_{time}_{session_id}.log
        parts = self.filename.replace('.log', '').split('_')
        if len(parts) >= 4:
            self.tool_type = parts[0]
            self.date = parts[1]
            self.time = parts[2]
            self.session_id = '_'.join(parts[3:])
        else:
            self.tool_type = "unknown"
            self.date = "unknown"
            self.time = "unknown"
            self.session_id = "unknown"

        # Parse log content
        self.lines = []
        self.timestamps = []
        self.agents = []
        self.tools_used = []
        self.errors = []
        self.clarifications = []
        self.qa_validations = []

        self.start_time = None
        self.end_time = None
        self.duration_seconds = 0

        self.task = None
        self.outcome = "unknown"  # success, failed, terminated

    def parse(self, log_content: str):
        """Parse log content and extract features."""
        lines = log_content.split('\n')
        self.lines = lines

        for line in lines:
            # Extract timestamp
            ts_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})', line)
            if ts_match:
                ts_str = ts_match.group(1)
                try:
                    ts = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S,%f')
                    self.timestamps.append(ts)

                    if self.start_time is None:
                        self.start_time = ts
                    self.end_time = ts
                except (ValueError, TypeError):
                    pass

            # Extract task
            if '[TASK PROPAGATION]' in line or 'Task:' in line:
                task_match = re.search(r'(?:Task:|TASK PROPAGATION\] Task in kwargs:)\s*(.+)', line)
                if task_match and not self.task:
                    self.task = task_match.group(1).strip()

            # Extract agent mentions
            if '🔧 GitHubOperator' in line or '❓ UserClarificationAgent' in line or '✓ QAValidator' in line:
                if 'GitHubOperator' in line:
                    self.agents.append('GitHubOperator')
                if 'UserClarificationAgent' in line:
                    self.agents.append('UserClarificationAgent')
                if 'QAValidator' in line:
                    self.agents.append('QAValidator')

            # Extract tool usage
            if '🛠️  Tool:' in line:
                tool_match = re.search(r'🛠️  Tool:\s*(\w+)', line)
                if tool_match:
                    self.tools_used.append(tool_match.group(1))

            # Extract errors
            if 'Error' in line or 'error' in line or '403' in line or '402' in line or 'failed' in line:
                self.errors.append(line.strip())

            # Extract clarifications
            if 'USER QUESTION' in line or 'ask_user' in line or 'Waiting for user response' in line:
                self.clarifications.append(line.strip())

            # Extract QA validation
            if '✓ QAValidator' in line:
                if '❌ BAD (Reject)' in line or lines[lines.index(line)+1:]:
                    next_line_idx = lines.index(line) + 1
                    if next_line_idx < len(lines) and ('❌ BAD' in lines[next_line_idx] or '✅ GOOD' in lines[next_line_idx]):
                        self.qa_validations.append(lines[next_line_idx].strip())

            # Extract outcome
            if 'cannot be completed' in line.lower() or 'cannot proceed' in line.lower():
                self.outcome = "failed"
            if 'Stopping agent' in line or 'force kill' in line or 'terminieren' in line.lower():
                self.outcome = "terminated"

        # Calculate duration
        if self.start_time and self.end_time:
            self.duration_seconds = (self.end_time - self.start_time).total_seconds()

    def get_features(self) -> Dict:
        """Extract feature dictionary."""
        # Count patterns
        tool_counts = Counter(self.tools_used)
        agent_counts = Counter(self.agents)
        error_count = len(self.errors)
        clarification_count = len(self.clarifications)
        qa_reject_count = sum(1 for v in self.qa_validations if 'BAD' in v)

        # Repetition detection (same tool used multiple times)
        max_tool_repetition = max(tool_counts.values()) if tool_counts else 0

        # Context switches (agent changes)
        context_switches = 0
        for i in range(1, len(self.agents)):
            if self.agents[i] != self.agents[i-1]:
                context_switches += 1

        return {
            'tool_type': self.tool_type,
            'task': self.task,
            'duration_seconds': self.duration_seconds,
            'num_lines': len(self.lines),
            'num_timestamps': len(self.timestamps),
            'tools_used': list(tool_counts.keys()),
            'tool_counts': dict(tool_counts),
            'max_tool_repetition': max_tool_repetition,
            'agents_involved': list(agent_counts.keys()),
            'agent_counts': dict(agent_counts),
            'context_switches': context_switches,
            'error_count': error_count,
            'clarification_count': clarification_count,
            'qa_reject_count': qa_reject_count,
            'outcome': self.outcome,
            'success': self.outcome not in ['failed', 'terminated']
        }


class ConversationTraceEncoder:
    """
    Encodes conversation traces as multi-modal vectors for routing system.

    Converts parsed conversation features into vectors that can be fed
    into the thalamic routing system alongside vision, audio, etc.
    """

    def __init__(
        self,
        trace_dim: int = 64,
        temporal_dim: int = 32,
        error_dim: int = 16,
        success_dim: int = 8
    ):
        """
        Initialize encoder.

        Args:
            trace_dim: Dimension for tool trace vector
            temporal_dim: Dimension for temporal pattern vector
            error_dim: Dimension for error signal vector
            success_dim: Dimension for success signal vector
        """
        self.trace_dim = trace_dim
        self.temporal_dim = temporal_dim
        self.error_dim = error_dim
        self.success_dim = success_dim

        # Tool type vocabulary
        self.tool_vocab = [
            'github', 'docker', 'memory', 'filesystem', 'context7',
            'brave-search', 'n8n', 'desktop', 'unknown'
        ]

        # Common tool actions
        self.tool_action_vocab = [
            'list_notifications', 'ask_user_impl', 'search', 'read', 'write',
            'create', 'update', 'delete', 'connect', 'query', 'unknown'
        ]

        # Agent types
        self.agent_vocab = [
            'GitHubOperator', 'UserClarificationAgent', 'QAValidator',
            'DockerOperator', 'MemoryAgent', 'FileSystemAgent', 'unknown'
        ]

    def encode_trace(self, features: Dict) -> np.ndarray:
        """
        Encode tool trace features as vector.

        Args:
            features: Feature dictionary from ConversationTrace

        Returns:
            trace_dim-dimensional vector
        """
        vec = np.zeros(self.trace_dim)

        # One-hot encode tool type
        tool_type = features.get('tool_type', 'unknown')
        if tool_type in self.tool_vocab:
            idx = self.tool_vocab.index(tool_type)
            vec[idx] = 1.0

        # Encode tool usage counts (normalized)
        tool_counts = features.get('tool_counts', {})
        total_tools = sum(tool_counts.values()) if tool_counts else 1
        offset = len(self.tool_vocab)
        for i, tool_action in enumerate(self.tool_action_vocab):
            if i + offset < self.trace_dim:
                count = tool_counts.get(tool_action, 0)
                vec[i + offset] = count / total_tools

        # Encode repetition (normalized)
        rep_idx = len(self.tool_vocab) + len(self.tool_action_vocab)
        if rep_idx < self.trace_dim:
            max_rep = features.get('max_tool_repetition', 0)
            vec[rep_idx] = min(max_rep / 5.0, 1.0)  # Normalize to [0, 1]

        # Encode context switches (normalized)
        ctx_idx = rep_idx + 1
        if ctx_idx < self.trace_dim:
            switches = features.get('context_switches', 0)
            vec[ctx_idx] = min(switches / 10.0, 1.0)

        return vec

    def encode_temporal(self, features: Dict) -> np.ndarray:
        """
        Encode temporal patterns as vector.

        Args:
            features: Feature dictionary

        Returns:
            temporal_dim-dimensional vector
        """
        vec = np.zeros(self.temporal_dim)

        # Duration (log scale)
        duration = features.get('duration_seconds', 0)
        vec[0] = np.log1p(duration) / 10.0  # Log scale, normalize

        # Number of lines (log scale)
        num_lines = features.get('num_lines', 0)
        vec[1] = np.log1p(num_lines) / 10.0

        # Activity rate (lines per second)
        if duration > 0:
            vec[2] = min(num_lines / duration / 10.0, 1.0)

        # Clarification frequency
        clarifications = features.get('clarification_count', 0)
        if duration > 0:
            vec[3] = min(clarifications / duration, 1.0)

        # Remaining dimensions: time of day features (future extension)

        return vec

    def encode_error(self, features: Dict) -> np.ndarray:
        """
        Encode error signals as vector.

        Args:
            features: Feature dictionary

        Returns:
            error_dim-dimensional vector
        """
        vec = np.zeros(self.error_dim)

        # Error count (normalized)
        error_count = features.get('error_count', 0)
        vec[0] = min(error_count / 10.0, 1.0)

        # QA rejection count (normalized)
        qa_rejects = features.get('qa_reject_count', 0)
        vec[1] = min(qa_rejects / 5.0, 1.0)

        # Clarification count (indicates confusion)
        clarifications = features.get('clarification_count', 0)
        vec[2] = min(clarifications / 3.0, 1.0)

        return vec

    def encode_success(self, features: Dict) -> np.ndarray:
        """
        Encode success signal as vector.

        Args:
            features: Feature dictionary

        Returns:
            success_dim-dimensional vector
        """
        vec = np.zeros(self.success_dim)

        # Success/failure
        success = features.get('success', False)
        vec[0] = 1.0 if success else 0.0

        # Outcome type (one-hot)
        outcome = features.get('outcome', 'unknown')
        outcome_map = {'success': 1, 'failed': 2, 'terminated': 3, 'unknown': 4}
        outcome_idx = outcome_map.get(outcome, 4)
        if outcome_idx < len(vec):
            vec[outcome_idx] = 1.0

        return vec

    def encode_full(self, trace: ConversationTrace) -> Dict[str, np.ndarray]:
        """
        Encode full conversation trace to multi-modal vectors.

        Args:
            trace: Parsed conversation trace

        Returns:
            Dict mapping modality names to vectors
        """
        features = trace.get_features()

        return {
            'tool_trace': self.encode_trace(features),
            'temporal_pattern': self.encode_temporal(features),
            'error_signal': self.encode_error(features),
            'success_signal': self.encode_success(features),
            'features': features  # Also return raw features for inspection
        }


def load_session_logs(
    log_dir: str,
    limit: Optional[int] = None
) -> List[ConversationTrace]:
    """
    Load and parse all session logs from directory.

    Args:
        log_dir: Path to sessions directory
        limit: Maximum number of logs to load (None = all)

    Returns:
        List of parsed conversation traces
    """
    log_path = Path(log_dir)
    log_files = sorted(log_path.glob('*.log'))

    if limit:
        log_files = log_files[:limit]

    traces = []
    for log_file in log_files:
        try:
            trace = ConversationTrace(str(log_file))
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            trace.parse(content)
            traces.append(trace)
        except Exception as e:
            print(f"Error parsing {log_file}: {e}")
            continue

    return traces
