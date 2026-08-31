"""
Log Parser - Parse Session Logs into Training Trajectories

Parses existing log formats:
- Text .log files (ConversationTrace format)
- JSON files (semantic_coherence format)

Converts to TemporalTrajectory for training.
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np

# Import from training modules
from .temporal_dataset import (
    TemporalStep,
    TemporalTrajectory,
    TemporalDataset,
    Regime
)
from .regime_inference import (
    RegimeInference,
    ToolCallInfo,
    classify_tool,
    infer_session_regimes
)
from .synthetic_data_generator import REGIME_SYNC_PATTERNS


@dataclass
class ToolCallRecord:
    """Single tool call extracted from logs"""
    timestamp: str
    tool_name: str
    tool_args: Dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None
    success: bool = True
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None


@dataclass
class SessionTrajectory:
    """Parsed session converted to trajectory format"""
    session_id: str
    task: str
    tool_calls: List[ToolCallRecord]
    outcome: str  # success/failed/terminated
    total_duration_ms: float = 0.0

    @property
    def num_calls(self) -> int:
        return len(self.tool_calls)

    @property
    def success(self) -> bool:
        return self.outcome == 'success'

    def infer_regimes(self) -> List[Tuple[Regime, float]]:
        """Infer regime sequence from tool patterns"""
        if not self.tool_calls:
            return []

        tool_names = [tc.tool_name for tc in self.tool_calls]
        success_flags = [tc.success for tc in self.tool_calls]
        error_messages = [tc.error_message for tc in self.tool_calls]

        return infer_session_regimes(tool_names, success_flags, error_messages)

    def to_temporal_trajectory(
        self,
        state_dim: int = 192,
        num_cells: int = 24,
        noise_level: float = 0.1
    ) -> Optional[TemporalTrajectory]:
        """
        Convert to TemporalTrajectory for training

        Args:
            state_dim: State vector dimension
            num_cells: Number of drumpad cells (3x8)
            noise_level: Noise to add to sync vectors

        Returns:
            TemporalTrajectory or None if conversion fails
        """
        if not self.tool_calls:
            return None

        # Infer regimes
        regime_sequence = self.infer_regimes()
        if not regime_sequence:
            return None

        steps = []
        num_cols = num_cells // 3

        for i, (tool_call, (regime, confidence)) in enumerate(zip(self.tool_calls, regime_sequence)):
            # Generate state vector
            state_vector = self._generate_state_vector(
                tool_call, regime, i / len(self.tool_calls), state_dim
            )

            # Generate sync vector from regime pattern
            sync_pattern = REGIME_SYNC_PATTERNS.get(regime)
            if sync_pattern:
                sync_vector = sync_pattern.to_vector(noise_level)
            else:
                sync_vector = np.random.rand(9) * 2 - 1

            # Map tool to drumpad cell
            channel = self._tool_to_channel(tool_call.tool_name)
            phase_bucket = i % num_cols
            target_cell = channel * num_cols + phase_bucket

            # Determine if action should be emitted
            target_should_act = tool_call.success or (i == len(self.tool_calls) - 1)

            # Check for transition
            is_transition = False
            if i > 0 and regime_sequence[i][0] != regime_sequence[i-1][0]:
                is_transition = True

            step = TemporalStep(
                state_vector=state_vector,
                sync_vector=sync_vector,
                target_cell=target_cell,
                target_should_act=target_should_act,
                target_regime=regime,
                transition_expected=is_transition,
                tool_name=tool_call.tool_name,
                tool_success=tool_call.success,
                timestamp_ms=int(tool_call.duration_ms or (i * 100))
            )
            steps.append(step)

        return TemporalTrajectory(
            steps=steps,
            task_description=self.task,
            success=self.success,
            task_id=self.session_id,
            total_duration_ms=int(self.total_duration_ms)
        )

    def _generate_state_vector(
        self,
        tool_call: ToolCallRecord,
        regime: Regime,
        progress: float,
        state_dim: int
    ) -> np.ndarray:
        """Generate state vector for a tool call"""
        state = np.zeros(state_dim)

        # Regime encoding (first 5 dims)
        regime_idx = list(Regime).index(regime)
        state[regime_idx] = 1.0

        # Progress encoding (dims 5-9)
        state[5] = progress
        state[6] = np.sin(progress * np.pi)
        state[7] = np.cos(progress * np.pi)
        state[8] = 1.0 - progress

        # Tool classification (dims 10-20)
        classification = classify_tool(tool_call.tool_name)
        for i, (key, val) in enumerate(classification.items()):
            if i < 10:
                state[10 + i] = float(val)

        # Success/failure (dim 20)
        state[20] = float(tool_call.success)

        # Random context (dims 64-128)
        state[64:128] = np.random.randn(64) * 0.3

        # Task embedding placeholder (dims 128-192)
        state[128:192] = np.random.randn(64) * 0.2

        return state

    def _tool_to_channel(self, tool_name: str) -> int:
        """Map tool to channel (0=Advance, 1=Explore, 2=Correct)"""
        classification = classify_tool(tool_name)

        if classification.get('is_search', False):
            return 1  # Explore
        elif classification.get('is_write', False):
            return 0  # Advance
        elif classification.get('is_read', False):
            return 0  # Advance
        else:
            return 2  # Correct (default for unknown)


class LogParser:
    """
    Parse session logs into training trajectories

    Supports:
    - Text .log files (ConversationTrace format)
    - JSON files (semantic_coherence format)
    """

    def __init__(
        self,
        log_dir: str,
        state_dim: int = 192,
        num_cells: int = 24
    ):
        """
        Initialize log parser

        Args:
            log_dir: Directory containing log files
            state_dim: State vector dimension
            num_cells: Number of drumpad cells
        """
        self.log_dir = Path(log_dir)
        self.state_dim = state_dim
        self.num_cells = num_cells
        self.sessions: List[SessionTrajectory] = []

        # Regex patterns for parsing
        self.timestamp_pattern = re.compile(
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})'
        )
        self.tool_call_pattern = re.compile(
            r'(?:tool|calling|executing|running)\s*[:\-]?\s*(\w+)',
            re.IGNORECASE
        )
        self.error_pattern = re.compile(
            r'(?:error|failed|exception|traceback)',
            re.IGNORECASE
        )
        self.success_pattern = re.compile(
            r'(?:success|completed|done|finished)',
            re.IGNORECASE
        )

    def parse_text_log(self, path: str) -> Optional[SessionTrajectory]:
        """
        Parse a text .log file

        Args:
            path: Path to log file

        Returns:
            SessionTrajectory or None if parsing fails
        """
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            print(f"[LogParser] Error reading {path}: {e}")
            return None

        # Extract session ID from filename
        session_id = Path(path).stem

        # Extract timestamps
        timestamps = self.timestamp_pattern.findall(content)

        # Extract tool calls
        tool_calls = []
        lines = content.split('\n')
        current_tool = None
        current_timestamp = None

        for line in lines:
            # Check for timestamp
            ts_match = self.timestamp_pattern.search(line)
            if ts_match:
                current_timestamp = ts_match.group(1)

            # Check for tool call
            tool_match = self.tool_call_pattern.search(line)
            if tool_match:
                tool_name = tool_match.group(1)

                # Determine success
                is_error = bool(self.error_pattern.search(line))
                is_success = bool(self.success_pattern.search(line))
                success = not is_error or is_success

                tool_calls.append(ToolCallRecord(
                    timestamp=current_timestamp or '',
                    tool_name=tool_name,
                    success=success,
                    error_message=line if is_error else None
                ))

        # Determine overall outcome
        error_count = sum(1 for tc in tool_calls if not tc.success)
        if error_count == 0:
            outcome = 'success'
        elif error_count >= len(tool_calls) * 0.5:
            outcome = 'failed'
        else:
            outcome = 'success'

        # Calculate duration
        total_duration = 0.0
        if len(timestamps) >= 2:
            try:
                start = datetime.strptime(timestamps[0], '%Y-%m-%d %H:%M:%S')
                end = datetime.strptime(timestamps[-1], '%Y-%m-%d %H:%M:%S')
                total_duration = (end - start).total_seconds() * 1000
            except Exception:
                pass

        # Extract task from first lines
        task = ''
        for line in lines[:10]:
            if 'task' in line.lower() or 'goal' in line.lower():
                task = line.strip()
                break
        if not task and lines:
            task = lines[0][:100] if lines[0] else 'Unknown task'

        if not tool_calls:
            return None

        return SessionTrajectory(
            session_id=session_id,
            task=task,
            tool_calls=tool_calls,
            outcome=outcome,
            total_duration_ms=total_duration
        )

    def parse_json_log(self, path: str) -> Optional[SessionTrajectory]:
        """
        Parse a JSON log file (semantic_coherence format)

        Args:
            path: Path to JSON file

        Returns:
            SessionTrajectory or None if parsing fails
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"[LogParser] Error reading {path}: {e}")
            return None

        # Handle different JSON formats
        session_id = Path(path).stem

        # Extract from semantic_coherence format
        if 'task' in data:
            task = data.get('task', 'Unknown task')

            # Extract tool calls from decision data
            tool_calls = []
            timestamp = data.get('timestamp', '')

            # Check for brain_answers which contain decision info
            if 'brain_answers' in data:
                for answer in data['brain_answers']:
                    decision_type = answer.get('decision_type', 'unknown')
                    confidence = answer.get('confidence', 0.5)

                    # Map decision to tool-like structure
                    tool_calls.append(ToolCallRecord(
                        timestamp=timestamp,
                        tool_name=f"decision_{decision_type}",
                        success=confidence > 0.5,
                        result=answer.get('text', '')
                    ))

            # Check for tool_calls array
            if 'tool_calls' in data:
                for tc in data['tool_calls']:
                    tool_calls.append(ToolCallRecord(
                        timestamp=tc.get('timestamp', timestamp),
                        tool_name=tc.get('tool', tc.get('tool_name', 'unknown')),
                        tool_args=tc.get('args', {}),
                        result=tc.get('result', ''),
                        success=tc.get('success', True),
                        duration_ms=tc.get('duration_ms'),
                        error_message=tc.get('error')
                    ))

            # Determine outcome
            decision = data.get('decision', {})
            if isinstance(decision, dict):
                status = decision.get('status', 'unknown')
                outcome = 'success' if status == 'GREEN' else 'failed'
            else:
                outcome = 'success'

            if not tool_calls:
                return None

            return SessionTrajectory(
                session_id=session_id,
                task=task,
                tool_calls=tool_calls,
                outcome=outcome
            )

        # Handle array format (list of trajectories)
        if isinstance(data, list):
            # Take first entry
            if data:
                return self.parse_json_log_entry(data[0], session_id)

        return None

    def parse_json_log_entry(
        self,
        entry: Dict,
        session_id: str
    ) -> Optional[SessionTrajectory]:
        """Parse a single JSON log entry"""
        task = entry.get('task', entry.get('description', 'Unknown'))
        tool_calls = []

        for tc in entry.get('tool_calls', entry.get('steps', [])):
            tool_calls.append(ToolCallRecord(
                timestamp=tc.get('timestamp', ''),
                tool_name=tc.get('tool', tc.get('tool_name', tc.get('action', 'unknown'))),
                tool_args=tc.get('args', tc.get('input', {})),
                result=str(tc.get('result', tc.get('output', ''))),
                success=tc.get('success', True),
                duration_ms=tc.get('duration_ms', tc.get('latency_ms'))
            ))

        if not tool_calls:
            return None

        return SessionTrajectory(
            session_id=session_id,
            task=task,
            tool_calls=tool_calls,
            outcome='success' if entry.get('success', True) else 'failed'
        )

    def parse_all(self) -> List[SessionTrajectory]:
        """
        Parse all log files in directory

        Returns:
            List of parsed SessionTrajectory
        """
        sessions = []

        if not self.log_dir.exists():
            print(f"[LogParser] Directory not found: {self.log_dir}")
            return sessions

        # Parse .log files
        for log_file in self.log_dir.glob('*.log'):
            session = self.parse_text_log(str(log_file))
            if session and session.num_calls > 0:
                sessions.append(session)

        # Parse .json files
        for json_file in self.log_dir.glob('*.json'):
            session = self.parse_json_log(str(json_file))
            if session and session.num_calls > 0:
                sessions.append(session)

        self.sessions = sessions
        print(f"[LogParser] Parsed {len(sessions)} sessions from {self.log_dir}")

        return sessions

    def to_dataset(
        self,
        noise_level: float = 0.1
    ) -> TemporalDataset:
        """
        Convert parsed sessions to TemporalDataset

        Args:
            noise_level: Noise to add to sync vectors

        Returns:
            TemporalDataset for training
        """
        if not self.sessions:
            self.parse_all()

        trajectories = []
        for session in self.sessions:
            traj = session.to_temporal_trajectory(
                state_dim=self.state_dim,
                num_cells=self.num_cells,
                noise_level=noise_level
            )
            if traj and traj.num_steps > 0:
                trajectories.append(traj)

        print(f"[LogParser] Converted {len(trajectories)} trajectories")

        return TemporalDataset(
            trajectories=trajectories,
            state_dim=self.state_dim
        )

    def get_statistics(self) -> Dict:
        """Get parsing statistics"""
        if not self.sessions:
            return {'num_sessions': 0}

        total_calls = sum(s.num_calls for s in self.sessions)
        success_count = sum(1 for s in self.sessions if s.success)

        return {
            'num_sessions': len(self.sessions),
            'total_tool_calls': total_calls,
            'avg_calls_per_session': total_calls / len(self.sessions),
            'success_rate': success_count / len(self.sessions),
            'log_dir': str(self.log_dir)
        }


if __name__ == "__main__":
    print("=" * 70)
    print("LOG PARSER - Testing")
    print("=" * 70)
    print()

    # Test 1: Create mock log data
    print("[1] Creating mock log data...")

    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create mock text log
        log_content = """2025-01-15 10:30:00 Starting task: Deploy container
2025-01-15 10:30:01 Calling tool: bash
2025-01-15 10:30:02 Tool bash completed successfully
2025-01-15 10:30:03 Executing tool: docker_ps
2025-01-15 10:30:04 Tool docker_ps success
2025-01-15 10:30:05 Running tool: docker_run
2025-01-15 10:30:06 Error: container failed to start
2025-01-15 10:30:07 Calling tool: docker_run
2025-01-15 10:30:08 Tool docker_run completed successfully
2025-01-15 10:30:09 Finished
"""
        log_path = os.path.join(tmpdir, 'test_session.log')
        with open(log_path, 'w') as f:
            f.write(log_content)

        # Create mock JSON log
        json_content = {
            "timestamp": "2025-01-15T10:30:00",
            "task": "Build and test application",
            "tool_calls": [
                {"tool": "read_file", "success": True, "duration_ms": 50},
                {"tool": "edit_file", "success": True, "duration_ms": 100},
                {"tool": "bash_run", "success": False, "error": "Test failed"},
                {"tool": "bash_run", "success": True, "duration_ms": 200}
            ],
            "decision": {"status": "GREEN"}
        }
        json_path = os.path.join(tmpdir, 'test_session.json')
        with open(json_path, 'w') as f:
            json.dump(json_content, f)

        print(f"    Created mock logs in {tmpdir}")
        print()

        # Test 2: Parse logs
        print("[2] Testing LogParser...")
        parser = LogParser(tmpdir)
        sessions = parser.parse_all()
        print(f"    Parsed {len(sessions)} sessions")

        for session in sessions:
            print(f"    Session: {session.session_id}")
            print(f"        Task: {session.task[:50]}...")
            print(f"        Tool calls: {session.num_calls}")
            print(f"        Outcome: {session.outcome}")
        print()

        # Test 3: Regime inference
        print("[3] Testing regime inference on parsed sessions...")
        for session in sessions:
            regimes = session.infer_regimes()
            print(f"    Session {session.session_id}:")
            print(f"        Regimes: {[(r.name, f'{c:.2f}') for r, c in regimes[:3]]}...")
        print()

        # Test 4: Convert to trajectories
        print("[4] Testing conversion to TemporalTrajectory...")
        for session in sessions:
            traj = session.to_temporal_trajectory()
            if traj:
                print(f"    Session {session.session_id}:")
                print(f"        Steps: {traj.num_steps}")
                print(f"        Success: {traj.success}")
                print(f"        First step regime: {traj.steps[0].target_regime.name}")
        print()

        # Test 5: Create dataset
        print("[5] Testing dataset creation...")
        dataset = parser.to_dataset()
        stats = dataset.get_statistics()
        print(f"    Dataset: {stats['num_trajectories']} trajectories")
        print(f"    Total steps: {stats['total_steps']}")
        print(f"    Success rate: {stats['success_rate']:.1%}")
        print()

        # Test 6: Parser statistics
        print("[6] Testing parser statistics...")
        parser_stats = parser.get_statistics()
        print(f"    Sessions: {parser_stats['num_sessions']}")
        print(f"    Total tool calls: {parser_stats['total_tool_calls']}")
        print(f"    Avg calls/session: {parser_stats['avg_calls_per_session']:.1f}")
        print()

    print("=" * 70)
    print("LOG PARSER TESTS COMPLETE")
    print("=" * 70)
