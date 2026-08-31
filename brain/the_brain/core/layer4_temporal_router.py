"""
Layer 4 Temporal Router - Integration Layer for Temporal Tool Control

This is the integration layer that combines all temporal tool control components
into a unified routing system that can be used by the hierarchical planner.

Architecture:
    Layer 1: TaskFeatureRouter (task classification)
    Layer 2: ConversationPathPlanner (sequential context)
    Layer 3: DecisionRouter (action decisions)
    Layer 4: TemporalRouter (temporal tool control) ← THIS MODULE

Information Flow:
    Raw Events → Stream Separator → Variable Extractor → Stability Analyzer
                                                              ↓
                                                    Temporal State Builder
                                                              ↓
                                                      Temporal CTM
                                                              ↓
                                                    Drumpad + Tonic/Phasic
                                                              ↓
                                                    Temporal Decision
                                                              ↓
                                                    Tool Orchestration

Security:
    - Text NEVER reaches execution path
    - All tool calls arise from validated state
    - Conflicts block execution
    - Full audit trail

Core Principle:
    "Nicht Text ruft Tools auf. Zustand ruft Zeit auf. Zeit ruft Aktion auf."
    (Not text calls tools. State calls time. Time calls action.)
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from core.stream_separator import (
    StreamSeparator, SeparatedStreams, ConversationEvent, ToolEvent,
    SecurityFlag
)
from core.variable_extractor import VariableExtractor, ExtractedVariable, VariableType
from core.stability_analyzer import (
    StabilityAnalyzer, OverallStabilityReport, StabilityClass
)
from core.temporal_state_builder import (
    TemporalStateBuilder, TemporalBrainState, StaticState, DynamicState, ToolState
)
from core.drumpad import Drumpad, DrumpadAction, CellSemantics
from core.tonic_phasic_activation import TonicPhasicActivation
from core.temporal_ctm import TemporalCTM, TemporalDecision

# Token → Frequency Integration
from core.action_potential_oscillator import ActionPotentialOscillator
from core.token_frequency_adapter import TokenFrequencyAdapter
from core.synchrony_encoder import SynchronyEncoder
from core.event_bridge import EventBridge, TokenExtractionConfig


@dataclass
class TemporalRoutingResult:
    """Complete result from temporal routing"""
    # Decision
    decision: TemporalDecision
    should_execute: bool

    # Tool information
    tool_name: Optional[str]
    tool_parameters: Dict[str, Any]

    # State information
    brain_state: TemporalBrainState
    stability_report: OverallStabilityReport

    # Security
    security_flags: List[Tuple[SecurityFlag, str]]
    blocked: bool
    block_reason: str

    # Timing
    processing_time_ms: float
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def is_safe(self) -> bool:
        """Check if routing is safe to proceed"""
        return not self.blocked and self.decision.should_act

    def to_dict(self) -> Dict:
        return {
            'should_execute': self.should_execute,
            'tool_name': self.tool_name,
            'tool_parameters': self.tool_parameters,
            'blocked': self.blocked,
            'block_reason': self.block_reason,
            'timing_confidence': self.decision.timing_confidence,
            'action_cell': self.decision.action.cell_id,
            'security_flags': len(self.security_flags),
            'processing_time_ms': self.processing_time_ms
        }


class Layer4TemporalRouter:
    """
    Layer 4: Temporal Router for Tool Control

    Integrates all temporal tool control components into a single routing layer
    that fits into the existing hierarchical planner architecture.

    Components:
    - StreamSeparator: Security-first stream separation
    - VariableExtractor: Extract semantic variables
    - StabilityAnalyzer: Classify variable stability
    - TemporalStateBuilder: Build 3-part brain state
    - TemporalCTM: Continuous temporal reasoning
    - Drumpad: Action grid
    - TonicPhasicActivation: Tool activation model

    Usage:
        router = Layer4TemporalRouter()

        # Process raw events
        result = router.route(raw_events, task_description="Deploy container")

        if result.should_execute:
            # Execute the tool
            execute_tool(result.tool_name, result.tool_parameters)
        else:
            # Wait or handle block
            handle_wait_or_block(result)
    """

    def __init__(
        self,
        strict_security: bool = True,
        timing_threshold: float = 0.5,
        enable_deep_reasoning: bool = True,
        custom_tools: Optional[set] = None
    ):
        """
        Initialize Layer 4 Temporal Router

        Args:
            strict_security: Block on any security concern
            timing_threshold: Threshold for action emission
            enable_deep_reasoning: Enable KlotskiCTM reasoning
            custom_tools: Additional tools to recognize
        """
        self.strict_security = strict_security
        self.timing_threshold = timing_threshold
        self.enable_deep_reasoning = enable_deep_reasoning

        # Initialize components
        self.stream_separator = StreamSeparator(
            strict_mode=strict_security,
            custom_tools=custom_tools
        )

        self.variable_extractor = VariableExtractor(confidence_threshold=0.5)

        self.stability_analyzer = StabilityAnalyzer(
            strict_mode=strict_security
        )

        self.state_builder = TemporalStateBuilder(
            stability_analyzer=self.stability_analyzer
        )

        self.temporal_ctm = TemporalCTM(
            timing_threshold=timing_threshold,
            use_klotski_ctm=enable_deep_reasoning,
            use_mamba=True,  # Phase 2: Enable Mamba SSM for latent dynamics
            use_oscillator_extended=True,  # Token→Frequency: Extended 201D state
            oscillator_dim=9  # 9D synchrony vector
        )

        # Token → Frequency: Oscillator and Adapter
        self.oscillator = ActionPotentialOscillator(
            natural_frequencies=(1.0, 1.2, 0.8),  # A, B, C
            coupling_strength=0.5,
            use_neural_coupling=False
        )

        self.token_adapter = TokenFrequencyAdapter(
            oscillator=self.oscillator,
            llm_router=None,  # Can be set via set_llm_router()
            use_local_fallback=True,
            use_ollama=True,  # Try Ollama for LLM classification
            enable_security_checks=True
        )

        self.synchrony_encoder = SynchronyEncoder()

        # EventBridge: Automatic token extraction from events
        self.event_bridge = EventBridge(
            token_adapter=self.token_adapter,
            config=TokenExtractionConfig(
                min_token_length=2,
                max_tokens_per_event=50,
                lowercase=True
            )
        )

        # Statistics
        self.total_routes = 0
        self.total_executions = 0
        self.total_blocks = 0
        self.total_waits = 0

    def route(
        self,
        raw_events: List[Dict],
        task_description: str = "",
        source_trusted: bool = False,
        force_reasoning: bool = False
    ) -> TemporalRoutingResult:
        """
        Route events through temporal processing pipeline

        Args:
            raw_events: Raw conversation and tool events
            task_description: Description for deep reasoning
            source_trusted: Whether tool events come from trusted source
            force_reasoning: Force deep CTM reasoning

        Returns:
            TemporalRoutingResult with decision and tool information
        """
        start_time = datetime.now()
        self.total_routes += 1

        # === PHASE 1: Stream Separation ===
        streams = self.stream_separator.separate(raw_events, source_trusted)

        # Check for critical security issues
        if streams.has_critical_issues and self.strict_security:
            return self._create_blocked_result(
                "Critical security issues detected",
                streams,
                start_time
            )

        # === PHASE 1b: Automatic Token Extraction via EventBridge ===
        # Extract tokens from conversation events to modulate oscillator
        for event in streams.conversation_stream:
            # ConversationEvent has text attribute directly
            event_dict = {'text': event.text, 'type': 'conversation'}
            self.event_bridge.process_conversation_event(event_dict)

        # === PHASE 2: Variable Extraction ===
        variables = self.variable_extractor.extract(streams.conversation_stream)

        # === PHASE 3: Stability Analysis ===
        stability_report = self.stability_analyzer.analyze(variables)

        # Check for conflicts
        is_safe, safety_reason = self.stability_analyzer.is_safe_to_execute(stability_report)
        if not is_safe:
            return self._create_blocked_result(
                f"Stability conflict: {safety_reason}",
                streams,
                start_time,
                stability_report=stability_report
            )

        # === PHASE 4: State Building ===
        brain_state = self.state_builder.build(streams, variables, stability_report)

        # === PHASE 4b: Inject Oscillator State ===
        # Token modulations affect oscillator, which feeds into CTM
        brain_state.oscillator_state = self.token_adapter.get_oscillator_state()
        brain_state.synchrony_vector = self.token_adapter.get_synchrony_vector()

        # Additional safety check from state
        if not brain_state.is_safe_for_action:
            return self._create_blocked_result(
                "Brain state not safe for action",
                streams,
                start_time,
                brain_state=brain_state,
                stability_report=stability_report
            )

        # === PHASE 5: Temporal CTM Processing ===
        decision = self.temporal_ctm.process(
            brain_state,
            task_description=task_description,
            force_reasoning=force_reasoning
        )

        # === PHASE 6: Build Result ===
        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        # Determine if we should execute
        should_execute = decision.should_act and not decision.blocked_by_conflict

        # Get tool information from drumpad action
        tool_name = decision.action.tool_name
        tool_parameters = decision.action.parameters

        # Fill parameters from stable variables
        if tool_parameters:
            safe_vars = self.stability_analyzer.get_safe_variables(stability_report)
            tool_parameters = self._fill_tool_parameters(tool_parameters, safe_vars)

        # Update statistics
        if should_execute:
            self.total_executions += 1
        elif decision.blocked_by_conflict:
            self.total_blocks += 1
        else:
            self.total_waits += 1

        return TemporalRoutingResult(
            decision=decision,
            should_execute=should_execute,
            tool_name=tool_name,
            tool_parameters=tool_parameters,
            brain_state=brain_state,
            stability_report=stability_report,
            security_flags=streams.security_flags,
            blocked=decision.blocked_by_conflict,
            block_reason=decision.block_reason if decision.blocked_by_conflict else "",
            processing_time_ms=processing_time
        )

    def route_incremental(
        self,
        new_event: Dict,
        task_description: str = ""
    ) -> TemporalRoutingResult:
        """
        Incrementally route a single new event

        More efficient for real-time processing.
        """
        # Classify event type
        event_type = self.stream_separator._classify_event(new_event)

        start_time = datetime.now()
        self.total_routes += 1

        # Process based on type
        if event_type.value == "conversation":
            # Process as conversation event
            conv_event = self.stream_separator._process_conversation_event(
                new_event, self.total_routes, SeparatedStreams()
            )
            if conv_event:
                # Extract variables
                new_vars = self.variable_extractor.extract_from_text(
                    conv_event.text,
                    turn_id=conv_event.turn_id,
                    timestamp=conv_event.timestamp
                )

                # Update state incrementally
                brain_state = self.state_builder.build_incremental(
                    new_conversation=conv_event,
                    new_variables=new_vars
                )
            else:
                brain_state = self.state_builder.current_state

        elif event_type.value == "tool_event":
            # Process as tool event
            result = SeparatedStreams()
            tool_event = self.stream_separator._process_tool_event(
                new_event, self.total_routes, True, result
            )
            if tool_event:
                brain_state = self.state_builder.build_incremental(
                    new_tool_event=tool_event
                )
            else:
                brain_state = self.state_builder.current_state
        else:
            brain_state = self.state_builder.current_state

        # Run CTM
        decision = self.temporal_ctm.process(brain_state, task_description)

        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        # Get current stability report
        stability_report = self.stability_analyzer.analyze(
            list(self.variable_extractor.known_variables.values())
        )

        should_execute = decision.should_act and not decision.blocked_by_conflict

        return TemporalRoutingResult(
            decision=decision,
            should_execute=should_execute,
            tool_name=decision.action.tool_name,
            tool_parameters=decision.action.parameters,
            brain_state=brain_state,
            stability_report=stability_report,
            security_flags=[],
            blocked=decision.blocked_by_conflict,
            block_reason=decision.block_reason if decision.blocked_by_conflict else "",
            processing_time_ms=processing_time
        )

    def record_execution_result(
        self,
        tool_name: str,
        success: bool,
        duration_ms: float = 0.0,
        result: Optional[Dict] = None,
        error: Optional[str] = None
    ):
        """
        Record tool execution result for learning

        Args:
            tool_name: Name of executed tool
            success: Whether execution succeeded
            duration_ms: Execution duration
            result: Tool result (if any)
            error: Error message (if any)
        """
        # Update temporal CTM
        self.temporal_ctm.record_outcome(tool_name, success, duration_ms)

        # Update state builder with tool event
        tool_event = ToolEvent(
            timestamp=datetime.now(),
            tool_name=tool_name,
            parameters={},
            result=result,
            success=success,
            error_message=error,
            execution_time_ms=duration_ms
        )

        self.state_builder.build_incremental(new_tool_event=tool_event)

        # Update oscillator based on outcome
        if success:
            self.token_adapter.apply_success_modulation(tool_name)
        else:
            self.token_adapter.apply_failure_modulation(tool_name)

        # Update event bridge stats
        self.event_bridge.record_tool_outcome(tool_name, success)

    def _create_blocked_result(
        self,
        reason: str,
        streams: SeparatedStreams,
        start_time: datetime,
        brain_state: Optional[TemporalBrainState] = None,
        stability_report: Optional[OverallStabilityReport] = None
    ) -> TemporalRoutingResult:
        """Create a blocked routing result"""
        self.total_blocks += 1

        # Create empty decision
        from core.temporal_ctm import TemporalDecision
        from core.drumpad import DrumpadAction
        import numpy as np

        noop_action = DrumpadAction(
            cell_id=0,
            semantic=CellSemantics.NOOP,
            tool_name=None,
            parameters={},
            confidence=0.0
        )

        decision = TemporalDecision(
            action=noop_action,
            cell_probabilities=np.zeros(64),
            should_act=False,
            timing_confidence=0.0,
            wait_time_ms=1000.0,
            hidden_state_norm=0.0,
            state_change_magnitude=0.0,
            blocked_by_conflict=True,
            block_reason=reason
        )

        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        return TemporalRoutingResult(
            decision=decision,
            should_execute=False,
            tool_name=None,
            tool_parameters={},
            brain_state=brain_state or TemporalBrainState(),
            stability_report=stability_report or OverallStabilityReport(),
            security_flags=streams.security_flags,
            blocked=True,
            block_reason=reason,
            processing_time_ms=processing_time
        )

    def _fill_tool_parameters(
        self,
        template: Dict[str, Any],
        safe_vars: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fill tool parameter template with safe variable values"""
        filled = {}

        for key, value in template.items():
            if isinstance(value, str) and value.startswith('$'):
                # Variable reference
                var_name = value[1:]
                if var_name in safe_vars:
                    filled[key] = safe_vars[var_name]
                else:
                    filled[key] = value  # Keep placeholder
            else:
                filled[key] = value

        return filled

    def reset(self):
        """Reset all components to initial state"""
        self.variable_extractor.clear()
        self.state_builder.reset()
        self.temporal_ctm.reset_state()
        self.token_adapter.reset()

    # =========================================================================
    # TOKEN → FREQUENCY INTERFACE
    # =========================================================================

    def process_tokens(self, tokens: List[str]) -> None:
        """
        Process tokens to modulate oscillator before routing.

        Call this with tokens from the conversation/LLM response
        before calling route() to let tokens influence the CTM decision.

        Args:
            tokens: List of tokens to process
        """
        for token in tokens:
            self.token_adapter.process_token_sync(token)

    async def process_tokens_async(self, tokens: List[str]) -> None:
        """
        Async version with LLM classification.

        Use this when you want full LLM-based token classification.
        Slower but more accurate for complex tokens.

        Args:
            tokens: List of tokens to process
        """
        for token in tokens:
            await self.token_adapter.process_token(token)

    def set_llm_router(self, llm_router) -> None:
        """
        Set LLM router for token classification.

        Args:
            llm_router: MultiLLMRouter instance
        """
        self.token_adapter.llm_router = llm_router

    def get_oscillator_state(self):
        """Get current oscillator state for inspection."""
        return self.token_adapter.get_oscillator_state()

    def get_synchrony_vector(self):
        """Get current synchrony vector for inspection."""
        return self.token_adapter.get_synchrony_vector()

    def get_dominant_channel(self):
        """Get currently dominant oscillator channel (ADVANCE, EXPLORE, CORRECT)."""
        return self.token_adapter.get_dominant_channel()

    def get_statistics(self) -> Dict:
        """Get router statistics"""
        return {
            'total_routes': self.total_routes,
            'total_executions': self.total_executions,
            'total_blocks': self.total_blocks,
            'total_waits': self.total_waits,
            'execution_rate': self.total_executions / max(1, self.total_routes),
            'block_rate': self.total_blocks / max(1, self.total_routes),
            'stream_separator': self.stream_separator.get_statistics(),
            'variable_extractor': self.variable_extractor.get_statistics(),
            'stability_analyzer': self.stability_analyzer.get_statistics(),
            'state_builder': self.state_builder.get_statistics(),
            'temporal_ctm': self.temporal_ctm.get_statistics(),
            'token_adapter': self.token_adapter.get_statistics(),
            'event_bridge': self.event_bridge.get_statistics()
        }

    def get_current_state_summary(self) -> Dict:
        """Get summary of current state"""
        state = self.state_builder.current_state

        return {
            'static': {
                'containers': len(state.static_state.container_ids),
                'files': len(state.static_state.file_paths),
                'requirements': len(state.static_state.requirements),
                'prohibitions': len(state.static_state.prohibitions)
            },
            'dynamic': {
                'current_intent': state.dynamic_state.current_intent,
                'needs_clarification': state.dynamic_state.needs_clarification,
                'turn': state.dynamic_state.current_turn
            },
            'tool': {
                'last_tool': state.tool_state.last_tool_name,
                'success_rate': state.tool_state.success_rate,
                'consecutive_failures': state.tool_state.consecutive_failures
            },
            'overall': {
                'has_conflicts': state.has_conflicts,
                'stability': state.overall_stability,
                'safe_for_action': state.is_safe_for_action
            }
        }


if __name__ == "__main__":
    print("=" * 70)
    print("LAYER 4 TEMPORAL ROUTER - Integration Layer for Temporal Tool Control")
    print("=" * 70)
    print()
    print('Core Principle:')
    print('  "Nicht Text ruft Tools auf. Zustand ruft Zeit auf. Zeit ruft Aktion auf."')
    print('  (Not text calls tools. State calls time. Time calls action.)')
    print()

    # Create router
    router = Layer4TemporalRouter(
        strict_security=True,
        timing_threshold=0.5,
        enable_deep_reasoning=False  # Disable for testing
    )

    print("Router initialized with components:")
    print("  - StreamSeparator")
    print("  - VariableExtractor")
    print("  - StabilityAnalyzer")
    print("  - TemporalStateBuilder")
    print("  - TemporalCTM")
    print()

    # Sample events
    events = [
        {'role': 'user', 'text': 'Deploy container nginx:latest on port 8080',
         'timestamp': datetime.now()},
        {'role': 'assistant', 'text': 'I will deploy nginx on port 8080',
         'timestamp': datetime.now()},
        {'tool_name': 'docker_run', 'parameters': {'image': 'nginx:latest', 'port': 8080},
         'success': True, 'timestamp': datetime.now()},
        {'role': 'user', 'text': 'Check the container status',
         'timestamp': datetime.now()},
    ]

    print("Processing sample events...")
    print("-" * 70)

    result = router.route(events, task_description="Deploy nginx container", source_trusted=True)

    print()
    print("Routing Result:")
    print(f"  Should Execute: {result.should_execute}")
    print(f"  Tool: {result.tool_name}")
    print(f"  Parameters: {result.tool_parameters}")
    print(f"  Blocked: {result.blocked}")
    print(f"  Block Reason: {result.block_reason}")
    print(f"  Timing Confidence: {result.decision.timing_confidence:.3f}")
    print(f"  Processing Time: {result.processing_time_ms:.1f}ms")
    print()

    print("Current State Summary:")
    summary = router.get_current_state_summary()
    for category, values in summary.items():
        print(f"  {category}:")
        for k, v in values.items():
            print(f"    {k}: {v}")

    print()
    print("Statistics:", router.get_statistics())
    print()
    print("=" * 70)
