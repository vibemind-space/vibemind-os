"""
Temporal State Builder - Build 3-Part Brain State for CTM

Constructs the unified state representation that feeds into the Temporal CTM.
The state is divided into three parts:

1. STATIC STATE (Anchors)
   - Stable IDs and references
   - Constraints and policies
   - Long-term goals
   - Values that don't change across turns

2. DYNAMIC STATE (Evolution)
   - Current intent
   - Progress indicators
   - Hypotheses and uncertainties
   - Values that legitimately evolve

3. TOOL STATE (Execution)
   - Last tool result
   - Retry count
   - Error history
   - Execution timing

Information Flow:
    Conversation Stream → Variable Extraction → Stability Analysis
                                                        ↓
    Tool Event Stream  →────────────────────→ State Builder
                                                        ↓
                                              3-Part Brain State
                                                        ↓
                                              Temporal CTM → Drumpad

This state is what the CTM reasons about - never raw text.
"""

import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from core.stream_separator import SeparatedStreams, ToolEvent, ConversationEvent
from core.variable_extractor import ExtractedVariable, VariableType
from core.stability_analyzer import (
    StabilityAnalyzer, StabilityClass, OverallStabilityReport, StabilityReport
)

# Token → Frequency types (optional, may not be set)
try:
    from core.action_potential_oscillator import TripleOscillatorState
    from core.synchrony_encoder import SynchronyVector
    HAS_OSCILLATOR = True
except ImportError:
    TripleOscillatorState = None
    SynchronyVector = None
    HAS_OSCILLATOR = False


@dataclass
class StaticState:
    """
    Static state - stable anchors that don't change

    These are the "facts" that remain constant throughout the conversation.
    Safe to use for tool parameters.
    """
    # Stable identifiers
    container_ids: Dict[str, str] = field(default_factory=dict)
    file_paths: Dict[str, str] = field(default_factory=dict)
    service_names: Dict[str, str] = field(default_factory=dict)
    urls: Dict[str, str] = field(default_factory=dict)

    # Constraints (things that must/must not happen)
    requirements: List[str] = field(default_factory=list)
    prohibitions: List[str] = field(default_factory=list)
    orderings: List[Tuple[str, str]] = field(default_factory=list)  # (before, after) pairs

    # Long-term goals
    primary_goal: str = ""
    sub_goals: List[str] = field(default_factory=list)

    # Fixed parameters
    ports: Dict[str, int] = field(default_factory=dict)
    limits: Dict[str, Any] = field(default_factory=dict)

    # Confidence in static state
    overall_confidence: float = 1.0

    def to_vector(self, dim: int = 64) -> np.ndarray:
        """Convert to fixed-size vector for CTM input"""
        # Simple encoding: count-based features + confidence
        features = [
            len(self.container_ids),
            len(self.file_paths),
            len(self.service_names),
            len(self.urls),
            len(self.requirements),
            len(self.prohibitions),
            len(self.orderings),
            1.0 if self.primary_goal else 0.0,
            len(self.sub_goals),
            len(self.ports),
            len(self.limits),
            self.overall_confidence
        ]

        # Pad to desired dimension
        vector = np.zeros(dim)
        vector[:len(features)] = features
        return vector

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'container_ids': self.container_ids,
            'file_paths': self.file_paths,
            'service_names': self.service_names,
            'urls': self.urls,
            'requirements': self.requirements,
            'prohibitions': self.prohibitions,
            'orderings': self.orderings,
            'primary_goal': self.primary_goal,
            'sub_goals': self.sub_goals,
            'ports': self.ports,
            'limits': self.limits,
            'overall_confidence': self.overall_confidence
        }


@dataclass
class DynamicState:
    """
    Dynamic state - values that legitimately evolve

    These track the current context and progress.
    Require careful tracking for tool decisions.
    """
    # Current intent
    current_intent: str = ""
    intent_confidence: float = 0.0
    intent_history: List[str] = field(default_factory=list)

    # Progress tracking
    progress_percent: float = 0.0
    steps_completed: int = 0
    steps_remaining: int = 0

    # Hypotheses (what we think might be true)
    hypotheses: List[Tuple[str, float]] = field(default_factory=list)  # (hypothesis, confidence)

    # Uncertainty indicators
    needs_clarification: bool = False
    clarification_questions: List[str] = field(default_factory=list)

    # Context switches
    context_changes: int = 0
    last_context_change: Optional[datetime] = None

    # Turn information
    current_turn: int = 0
    conversation_length: int = 0

    def to_vector(self, dim: int = 64) -> np.ndarray:
        """Convert to fixed-size vector for CTM input"""
        features = [
            self.intent_confidence,
            len(self.intent_history),
            self.progress_percent,
            self.steps_completed,
            self.steps_remaining,
            len(self.hypotheses),
            sum(h[1] for h in self.hypotheses) / max(1, len(self.hypotheses)),  # avg hypothesis confidence
            1.0 if self.needs_clarification else 0.0,
            len(self.clarification_questions),
            self.context_changes,
            self.current_turn,
            self.conversation_length
        ]

        vector = np.zeros(dim)
        vector[:len(features)] = features
        return vector

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'current_intent': self.current_intent,
            'intent_confidence': self.intent_confidence,
            'progress_percent': self.progress_percent,
            'steps_completed': self.steps_completed,
            'steps_remaining': self.steps_remaining,
            'hypotheses': self.hypotheses,
            'needs_clarification': self.needs_clarification,
            'clarification_questions': self.clarification_questions,
            'current_turn': self.current_turn
        }


@dataclass
class ToolState:
    """
    Tool state - execution context

    Tracks tool execution history and current state.
    Critical for retry/wait/abort decisions.
    """
    # Last execution
    last_tool_name: str = ""
    last_tool_success: bool = True
    last_tool_result: Optional[Dict] = None
    last_execution_time: Optional[datetime] = None
    last_execution_duration_ms: float = 0.0

    # Retry tracking
    retry_count: int = 0
    max_retries: int = 3
    consecutive_failures: int = 0

    # Error state
    has_error: bool = False
    error_message: str = ""
    error_severity: float = 0.0  # 0-1, 1 being critical

    # Execution history (last N tools)
    tool_history: List[str] = field(default_factory=list)
    success_history: List[bool] = field(default_factory=list)
    timing_history: List[float] = field(default_factory=list)

    # Pending actions
    pending_tool: str = ""
    pending_params: Dict = field(default_factory=dict)

    # Backoff state
    backoff_until: Optional[datetime] = None
    current_backoff_ms: float = 0.0

    # Statistics
    total_executions: int = 0
    total_successes: int = 0
    total_failures: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.total_executions == 0:
            return 1.0
        return self.total_successes / self.total_executions

    @property
    def should_backoff(self) -> bool:
        """Check if currently in backoff period"""
        if self.backoff_until is None:
            return False
        return datetime.now() < self.backoff_until

    @property
    def can_retry(self) -> bool:
        """Check if retry is allowed"""
        return self.retry_count < self.max_retries and not self.should_backoff

    def to_vector(self, dim: int = 64) -> np.ndarray:
        """Convert to fixed-size vector for CTM input"""
        # Calculate timing statistics
        avg_timing = sum(self.timing_history) / max(1, len(self.timing_history))
        max_timing = max(self.timing_history) if self.timing_history else 0.0

        features = [
            1.0 if self.last_tool_success else 0.0,
            self.last_execution_duration_ms / 1000.0,  # Normalize to seconds
            self.retry_count / max(1, self.max_retries),
            self.consecutive_failures,
            1.0 if self.has_error else 0.0,
            self.error_severity,
            len(self.tool_history),
            sum(self.success_history) / max(1, len(self.success_history)),  # recent success rate
            avg_timing / 1000.0,
            max_timing / 1000.0,
            1.0 if self.pending_tool else 0.0,
            1.0 if self.should_backoff else 0.0,
            self.current_backoff_ms / 1000.0,
            self.success_rate,
            self.total_executions,
            self.total_failures
        ]

        vector = np.zeros(dim)
        vector[:len(features)] = features
        return vector

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'last_tool_name': self.last_tool_name,
            'last_tool_success': self.last_tool_success,
            'last_execution_duration_ms': self.last_execution_duration_ms,
            'retry_count': self.retry_count,
            'consecutive_failures': self.consecutive_failures,
            'has_error': self.has_error,
            'error_message': self.error_message,
            'pending_tool': self.pending_tool,
            'should_backoff': self.should_backoff,
            'success_rate': self.success_rate,
            'total_executions': self.total_executions
        }


@dataclass
class TemporalBrainState:
    """
    Complete 3-part brain state for CTM

    This is the unified state representation that:
    - Feeds into the Temporal CTM
    - Is used by the Drumpad for action selection
    - Never contains raw text (only structured state)

    With Token→Frequency integration:
    - oscillator_state: Current A/B/C oscillator amplitudes and phases
    - synchrony_vector: 9D encoding of oscillator relationships
    """
    static_state: StaticState = field(default_factory=StaticState)
    dynamic_state: DynamicState = field(default_factory=DynamicState)
    tool_state: ToolState = field(default_factory=ToolState)

    # Token → Frequency: Oscillator state (optional)
    oscillator_state: Optional[Any] = None  # TripleOscillatorState when available
    synchrony_vector: Optional[Any] = None  # SynchronyVector when available

    # Stability metadata
    has_conflicts: bool = False
    conflict_count: int = 0
    overall_stability: float = 1.0

    # State metadata
    build_timestamp: datetime = field(default_factory=datetime.now)
    source_turns: int = 0
    source_tool_events: int = 0

    def to_vector(self, dim: int = 192, include_oscillator: bool = True) -> np.ndarray:
        """
        Convert entire state to fixed-size vector for CTM

        Default dimension: 192 = 64 (static) + 64 (dynamic) + 64 (tool)
        If include_oscillator and synchrony_vector is set, appends 9D synchrony vector.
        """
        static_dim = dim // 3
        dynamic_dim = dim // 3
        tool_dim = dim - static_dim - dynamic_dim

        static_vec = self.static_state.to_vector(static_dim)
        dynamic_vec = self.dynamic_state.to_vector(dynamic_dim)
        tool_vec = self.tool_state.to_vector(tool_dim)

        # Concatenate and add metadata
        combined = np.concatenate([static_vec, dynamic_vec, tool_vec])

        # Add state-level features in remaining space
        if len(combined) < dim:
            metadata = [
                1.0 if self.has_conflicts else 0.0,
                self.conflict_count,
                self.overall_stability
            ]
            combined = np.concatenate([combined, metadata])

        base_vector = combined[:dim]

        # Optionally append oscillator synchrony vector (9D)
        if include_oscillator and self.synchrony_vector is not None:
            try:
                sync_vec = self.synchrony_vector.vector  # 9D numpy array
                return np.concatenate([base_vector, sync_vec])
            except (AttributeError, TypeError):
                pass

        return base_vector

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        result = {
            'static': self.static_state.to_dict(),
            'dynamic': self.dynamic_state.to_dict(),
            'tool': self.tool_state.to_dict(),
            'has_conflicts': self.has_conflicts,
            'conflict_count': self.conflict_count,
            'overall_stability': self.overall_stability,
            'build_timestamp': self.build_timestamp.isoformat(),
            'source_turns': self.source_turns,
            'source_tool_events': self.source_tool_events
        }

        # Add oscillator info if available
        if self.oscillator_state is not None:
            try:
                result['oscillator'] = {
                    'A_amplitude': self.oscillator_state.A.amplitude,
                    'B_amplitude': self.oscillator_state.B.amplitude,
                    'C_amplitude': self.oscillator_state.C.amplitude,
                    'dominant': self.oscillator_state.dominant_channel().value
                }
            except AttributeError:
                pass

        if self.synchrony_vector is not None:
            try:
                result['synchrony'] = {
                    'mean_coherence': self.synchrony_vector.mean_coherence,
                    'amplitudes': self.synchrony_vector.amplitudes.tolist()
                }
            except AttributeError:
                pass

        return result

    @property
    def is_safe_for_action(self) -> bool:
        """Check if state is safe for action execution"""
        return not self.has_conflicts and self.overall_stability > 0.5

    @property
    def has_oscillator(self) -> bool:
        """Check if oscillator state is available"""
        return self.oscillator_state is not None


class TemporalStateBuilder:
    """
    Builds 3-part brain state from separated streams and stability analysis

    Information Flow:
        Streams + Variables + Stability → State Builder → TemporalBrainState
    """

    # History limits
    MAX_TOOL_HISTORY = 10
    MAX_INTENT_HISTORY = 5

    def __init__(
        self,
        stability_analyzer: Optional[StabilityAnalyzer] = None,
        state_dim: int = 192
    ):
        """
        Initialize state builder

        Args:
            stability_analyzer: Analyzer for variable stability (creates one if not provided)
            state_dim: Dimension of output state vector
        """
        self.stability_analyzer = stability_analyzer or StabilityAnalyzer()
        self.state_dim = state_dim

        # Current state (persists across builds for incremental updates)
        self.current_state = TemporalBrainState()

        # Tracking
        self.processed_turns: set = set()
        self.processed_tool_events: set = set()

    def build(
        self,
        streams: SeparatedStreams,
        variables: List[ExtractedVariable],
        stability_report: Optional[OverallStabilityReport] = None
    ) -> TemporalBrainState:
        """
        Build complete brain state from inputs

        Args:
            streams: Separated conversation and tool streams
            variables: Extracted variables from conversation
            stability_report: Pre-computed stability (computed if not provided)

        Returns:
            Complete TemporalBrainState
        """
        # Compute stability if not provided
        if stability_report is None:
            stability_report = self.stability_analyzer.analyze(variables)

        # Build each state component
        static = self._build_static_state(variables, stability_report)
        dynamic = self._build_dynamic_state(streams.conversation_stream, variables, stability_report)
        tool = self._build_tool_state(streams.tool_event_stream)

        # Create complete state
        state = TemporalBrainState(
            static_state=static,
            dynamic_state=dynamic,
            tool_state=tool,
            has_conflicts=stability_report.has_conflicts,
            conflict_count=stability_report.conflict_count,
            overall_stability=stability_report.overall_stability_score,
            source_turns=len(streams.conversation_stream),
            source_tool_events=len(streams.tool_event_stream)
        )

        self.current_state = state
        return state

    def build_incremental(
        self,
        new_conversation: Optional[ConversationEvent] = None,
        new_tool_event: Optional[ToolEvent] = None,
        new_variables: Optional[List[ExtractedVariable]] = None
    ) -> TemporalBrainState:
        """
        Incrementally update state with new information

        More efficient than full rebuild for real-time updates.
        """
        state = self.current_state

        if new_conversation:
            self._update_dynamic_from_conversation(state.dynamic_state, new_conversation)

        if new_tool_event:
            self._update_tool_state(state.tool_state, new_tool_event)

        if new_variables:
            # Re-analyze stability with new variables
            stability_report = self.stability_analyzer.analyze(new_variables)
            self._update_static_from_variables(state.static_state, new_variables, stability_report)

            state.has_conflicts = stability_report.has_conflicts
            state.conflict_count = stability_report.conflict_count
            state.overall_stability = stability_report.overall_stability_score

        state.build_timestamp = datetime.now()
        return state

    def _build_static_state(
        self,
        variables: List[ExtractedVariable],
        stability_report: OverallStabilityReport
    ) -> StaticState:
        """Build static state from stable variables"""
        static = StaticState()

        # Process only STATIC classified variables
        for name, report in stability_report.static_variables.items():
            var_type = report.variable_type
            value = report.current_value

            if var_type == VariableType.ID_HANDLE:
                # Categorize by name hints
                if 'container' in name or 'image' in name or 'docker' in name:
                    static.container_ids[name] = str(value)
                elif 'file' in name or 'path' in name:
                    static.file_paths[name] = str(value)
                elif 'url' in name or 'http' in name:
                    static.urls[name] = str(value)
                elif 'service' in name:
                    static.service_names[name] = str(value)

            elif var_type == VariableType.ENTITY:
                static.service_names[name] = str(value)

            elif var_type == VariableType.NUMERIC:
                if 'port' in name:
                    try:
                        static.ports[name] = int(value)
                    except (ValueError, TypeError):
                        pass
                else:
                    static.limits[name] = value

            elif var_type == VariableType.CONSTRAINT:
                value_str = str(value).lower()
                if any(kw in value_str for kw in ['must not', 'cannot', "don't", 'forbidden']):
                    static.prohibitions.append(str(value))
                elif any(kw in value_str for kw in ['must', 'require', 'need']):
                    static.requirements.append(str(value))
                elif 'before' in value_str or 'after' in value_str:
                    # Extract ordering (simplified)
                    static.orderings.append((str(value), ''))

            elif var_type == VariableType.GOAL:
                if not static.primary_goal:
                    static.primary_goal = str(value)
                else:
                    static.sub_goals.append(str(value))

        # Calculate overall confidence
        if stability_report.static_variables:
            confidences = [r.confidence for r in stability_report.static_variables.values()]
            static.overall_confidence = sum(confidences) / len(confidences)

        return static

    def _build_dynamic_state(
        self,
        conversation: List[ConversationEvent],
        variables: List[ExtractedVariable],
        stability_report: OverallStabilityReport
    ) -> DynamicState:
        """Build dynamic state from conversation and dynamic variables"""
        dynamic = DynamicState()

        # Extract intents from variables
        intent_vars = [v for v in variables if v.var_type == VariableType.INTENT_STATE]
        if intent_vars:
            # Most recent intent
            latest_intent = sorted(intent_vars, key=lambda v: v.source_turn)[-1]
            dynamic.current_intent = str(latest_intent.value)
            dynamic.intent_confidence = latest_intent.confidence
            dynamic.intent_history = [str(v.value) for v in intent_vars[-self.MAX_INTENT_HISTORY:]]

        # Track conversation progress
        dynamic.conversation_length = len(conversation)
        dynamic.current_turn = conversation[-1].turn_id if conversation else 0

        # Check for clarification needs
        if stability_report.has_conflicts:
            dynamic.needs_clarification = True
            for name, report in stability_report.conflicting_variables.items():
                dynamic.clarification_questions.append(
                    f"Please clarify: {report.conflict_description}"
                )

        # Build hypotheses from dynamic variables
        for name, report in stability_report.dynamic_variables.items():
            if report.unique_values > 1:
                dynamic.hypotheses.append((
                    f"{name} might be {report.current_value}",
                    report.consistency_score
                ))

        return dynamic

    def _build_tool_state(self, tool_events: List[ToolEvent]) -> ToolState:
        """Build tool state from tool event stream"""
        tool = ToolState()

        if not tool_events:
            return tool

        # Sort by timestamp
        sorted_events = sorted(tool_events, key=lambda e: e.timestamp)

        # Process all events
        for event in sorted_events:
            self._update_tool_state(tool, event)

        return tool

    def _update_tool_state(self, tool: ToolState, event: ToolEvent):
        """Update tool state with a new event"""
        tool.last_tool_name = event.tool_name
        tool.last_tool_success = event.success
        tool.last_tool_result = event.result
        tool.last_execution_time = event.timestamp
        tool.last_execution_duration_ms = event.execution_time_ms

        # Update history
        tool.tool_history.append(event.tool_name)
        tool.success_history.append(event.success)
        tool.timing_history.append(event.execution_time_ms)

        # Trim history
        if len(tool.tool_history) > self.MAX_TOOL_HISTORY:
            tool.tool_history = tool.tool_history[-self.MAX_TOOL_HISTORY:]
            tool.success_history = tool.success_history[-self.MAX_TOOL_HISTORY:]
            tool.timing_history = tool.timing_history[-self.MAX_TOOL_HISTORY:]

        # Update counters
        tool.total_executions += 1
        if event.success:
            tool.total_successes += 1
            tool.consecutive_failures = 0
            tool.retry_count = 0
            tool.has_error = False
            tool.error_message = ""
        else:
            tool.total_failures += 1
            tool.consecutive_failures += 1
            tool.retry_count = event.retry_count
            tool.has_error = True
            tool.error_message = event.error_message or "Unknown error"

            # Calculate error severity
            tool.error_severity = min(1.0, tool.consecutive_failures * 0.25)

            # Set backoff if multiple failures
            if tool.consecutive_failures >= 2:
                backoff_ms = 1000 * (2 ** tool.consecutive_failures)  # Exponential backoff
                tool.current_backoff_ms = min(backoff_ms, 30000)  # Max 30 seconds
                tool.backoff_until = datetime.now() + timedelta(milliseconds=tool.current_backoff_ms)

    def _update_dynamic_from_conversation(
        self,
        dynamic: DynamicState,
        event: ConversationEvent
    ):
        """Update dynamic state from new conversation event"""
        dynamic.conversation_length += 1
        dynamic.current_turn = event.turn_id

        # Check for intent hints
        if event.intent_hints:
            new_intent = event.intent_hints[0]
            if new_intent != dynamic.current_intent:
                dynamic.context_changes += 1
                dynamic.last_context_change = event.timestamp
            dynamic.current_intent = new_intent
            dynamic.intent_history.append(new_intent)
            if len(dynamic.intent_history) > self.MAX_INTENT_HISTORY:
                dynamic.intent_history = dynamic.intent_history[-self.MAX_INTENT_HISTORY:]

    def _update_static_from_variables(
        self,
        static: StaticState,
        variables: List[ExtractedVariable],
        stability_report: OverallStabilityReport
    ):
        """Update static state from new variables (only if stable)"""
        # Only add newly confirmed static variables
        for name, report in stability_report.static_variables.items():
            if report.stability_class == StabilityClass.STATIC:
                var_type = report.variable_type
                value = report.current_value

                if var_type == VariableType.ID_HANDLE:
                    if 'container' in name:
                        static.container_ids[name] = str(value)
                    elif 'file' in name:
                        static.file_paths[name] = str(value)

    def reset(self):
        """Reset state builder to initial state"""
        self.current_state = TemporalBrainState()
        self.processed_turns.clear()
        self.processed_tool_events.clear()

    def get_statistics(self) -> Dict:
        """Get builder statistics"""
        return {
            'state_dim': self.state_dim,
            'processed_turns': len(self.processed_turns),
            'processed_tool_events': len(self.processed_tool_events),
            'current_state_safe': self.current_state.is_safe_for_action,
            'current_conflicts': self.current_state.conflict_count
        }


if __name__ == "__main__":
    print("=" * 70)
    print("TEMPORAL STATE BUILDER - Build 3-Part Brain State for CTM")
    print("=" * 70)
    print()
    print("Information Flow:")
    print("    Streams + Variables + Stability → State Builder → TemporalBrainState")
    print()

    from core.stream_separator import StreamSeparator, SeparatedStreams
    from core.variable_extractor import VariableExtractor

    # Create components
    separator = StreamSeparator()
    extractor = VariableExtractor()
    builder = TemporalStateBuilder()

    # Sample events
    raw_events = [
        {'role': 'user', 'text': 'Deploy container nginx:latest on port 8080',
         'timestamp': datetime.now()},
        {'role': 'assistant', 'text': 'I will deploy nginx on port 8080',
         'timestamp': datetime.now()},
        {'tool_name': 'docker_run', 'parameters': {'image': 'nginx:latest', 'port': 8080},
         'success': True, 'timestamp': datetime.now()},
        {'role': 'user', 'text': 'Check the container status',
         'timestamp': datetime.now()},
        {'tool_name': 'docker_ps', 'parameters': {},
         'success': True, 'result': {'status': 'running'}, 'timestamp': datetime.now()},
    ]

    # Separate streams
    streams = separator.separate(raw_events, source_trusted=True)
    print(f"Separated: {len(streams.conversation_stream)} conversation, "
          f"{len(streams.tool_event_stream)} tool events")

    # Extract variables
    variables = extractor.extract(streams.conversation_stream)
    print(f"Extracted: {len(variables)} variables")

    # Build state
    state = builder.build(streams, variables)

    print()
    print("Built State:")
    print("-" * 70)
    print(f"  Static State:")
    print(f"    Container IDs: {state.static_state.container_ids}")
    print(f"    Ports: {state.static_state.ports}")
    print(f"    Confidence: {state.static_state.overall_confidence:.2f}")
    print()
    print(f"  Dynamic State:")
    print(f"    Current Intent: {state.dynamic_state.current_intent}")
    print(f"    Turn: {state.dynamic_state.current_turn}")
    print(f"    Needs Clarification: {state.dynamic_state.needs_clarification}")
    print()
    print(f"  Tool State:")
    print(f"    Last Tool: {state.tool_state.last_tool_name}")
    print(f"    Success Rate: {state.tool_state.success_rate:.1%}")
    print(f"    Total Executions: {state.tool_state.total_executions}")
    print()
    print(f"Overall:")
    print(f"  Has Conflicts: {state.has_conflicts}")
    print(f"  Safe for Action: {state.is_safe_for_action}")
    print(f"  Stability Score: {state.overall_stability:.2f}")
    print()

    # Show vector representation
    state_vector = state.to_vector()
    print(f"State Vector: shape={state_vector.shape}, "
          f"norm={np.linalg.norm(state_vector):.2f}")
    print()
    print("=" * 70)
