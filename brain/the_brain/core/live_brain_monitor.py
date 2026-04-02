"""
Real-Time Live Brain Monitor

Monitors ongoing conversations in real-time and triggers interventions
when failure patterns are detected BEFORE the task fails completely.

This creates a proactive self-aware system that can prevent failures
instead of just learning from them.
"""

import numpy as np
import time
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, deque

from core.meta_router import MetaRouter
from core.brain_monitor import BrainActivityMonitor
from core.strategy_library import StrategyLibrary
from core.conversation_trace_encoder import ConversationTraceEncoder


class LiveConversationState:
    """
    Tracks state of an ongoing conversation in real-time.

    Updated incrementally as events occur (tool calls, errors, etc.)
    """

    def __init__(self, task_description: str = ""):
        """
        Initialize live conversation state.

        Args:
            task_description: Brief description of the task
        """
        self.task = task_description
        self.start_time = time.time()

        # Incremental counters
        self.tool_calls: List[str] = []
        self.tool_counts: Dict[str, int] = defaultdict(int)
        self.error_count = 0
        self.clarification_count = 0
        self.qa_reject_count = 0
        self.context_switches = 0

        # Pattern detection
        self.last_tool = None
        self.tool_repetition_streak = 0
        self.max_tool_repetition = 0

        # Agents involved
        self.agents: List[str] = []
        self.agent_counts: Dict[str, int] = defaultdict(int)

        # Task identification
        self.tool_type = "unknown"

        # Outcome (set at end)
        self.outcome = "in_progress"
        self.success = None

    def add_tool_call(self, tool_name: str):
        """Record a tool call."""
        self.tool_calls.append(tool_name)
        self.tool_counts[tool_name] += 1

        # Detect tool repetition
        if tool_name == self.last_tool:
            self.tool_repetition_streak += 1
            self.max_tool_repetition = max(self.max_tool_repetition, self.tool_repetition_streak)
        else:
            self.tool_repetition_streak = 1
            self.last_tool = tool_name

        # Infer tool type from first tool
        if self.tool_type == "unknown" and tool_name:
            self.tool_type = tool_name.split('_')[0].lower()

    def add_error(self):
        """Record an error."""
        self.error_count += 1

    def add_clarification(self):
        """Record a user clarification request."""
        self.clarification_count += 1

    def add_qa_reject(self):
        """Record a QA rejection."""
        self.qa_reject_count += 1

    def add_agent(self, agent_name: str):
        """Record agent involvement."""
        if agent_name not in self.agents:
            self.agents.append(agent_name)
        self.agent_counts[agent_name] += 1

    def add_context_switch(self):
        """Record a context switch."""
        self.context_switches += 1

    def get_duration(self) -> float:
        """Get elapsed duration in seconds."""
        return time.time() - self.start_time

    def get_features(self) -> Dict:
        """
        Get current features as dict (compatible with ConversationTrace).

        Returns:
            Feature dict that can be encoded
        """
        return {
            'tool_type': self.tool_type,
            'task': self.task,
            'duration_seconds': self.get_duration(),
            'num_lines': len(self.tool_calls) * 10,  # Estimate
            'tools_used': list(set(self.tool_calls)),
            'tool_counts': dict(self.tool_counts),
            'max_tool_repetition': self.max_tool_repetition,
            'agents_involved': self.agents,
            'agent_counts': dict(self.agent_counts),
            'context_switches': self.context_switches,
            'error_count': self.error_count,
            'clarification_count': self.clarification_count,
            'qa_reject_count': self.qa_reject_count,
            'outcome': self.outcome,
            'success': self.success if self.success is not None else True
        }

    def finalize(self, success: bool, outcome: str = "completed"):
        """Mark conversation as complete."""
        self.success = success
        self.outcome = outcome


class LiveBrainMonitor:
    """
    Real-time brain monitoring system that watches conversations as they happen
    and triggers interventions when failure patterns emerge.
    """

    def __init__(
        self,
        meta_router: MetaRouter,
        brain_monitor: BrainActivityMonitor,
        strategy_library: StrategyLibrary,
        # Intervention thresholds
        error_threshold: int = 5,
        repetition_threshold: int = 3,
        qa_reject_threshold: int = 3,
        clarification_threshold: int = 4,
        duration_multiplier: float = 2.0,  # Trigger if 2x expected duration
        # Update frequency
        check_interval: int = 3  # Check every N tool calls
    ):
        """
        Initialize live brain monitor.

        Args:
            meta_router: Trained meta-router for prediction
            brain_monitor: Brain activity monitor
            strategy_library: Library of successful strategies
            error_threshold: Error count to trigger intervention
            repetition_threshold: Tool repetition to trigger intervention
            qa_reject_threshold: QA reject count to trigger intervention
            clarification_threshold: Clarification count to trigger intervention
            duration_multiplier: Duration multiplier vs expected to trigger
            check_interval: Check for interventions every N tool calls
        """
        self.meta_router = meta_router
        self.brain_monitor = brain_monitor
        self.strategy_library = strategy_library

        self.error_threshold = error_threshold
        self.repetition_threshold = repetition_threshold
        self.qa_reject_threshold = qa_reject_threshold
        self.clarification_threshold = clarification_threshold
        self.duration_multiplier = duration_multiplier
        self.check_interval = check_interval

        # Current conversation
        self.current_conversation: Optional[LiveConversationState] = None

        # Intervention history
        self.interventions_triggered = []
        self.intervention_count = 0

        # Statistics
        self.conversations_monitored = 0
        self.failures_prevented = 0

    def start_conversation(self, task_description: str = "") -> LiveConversationState:
        """
        Start monitoring a new conversation.

        Args:
            task_description: Brief task description

        Returns:
            LiveConversationState object to update
        """
        self.current_conversation = LiveConversationState(task_description)
        print(f"\n[BRAIN] Started monitoring: {task_description}")
        return self.current_conversation

    def update(self, conversation: LiveConversationState) -> Optional[Dict]:
        """
        Update brain state with current conversation and check for interventions.

        Args:
            conversation: Current conversation state

        Returns:
            Intervention dict if triggered, None otherwise
        """
        # Check if we should evaluate (every N tool calls)
        if len(conversation.tool_calls) % self.check_interval != 0:
            return None

        # Check intervention conditions
        intervention = self._check_intervention_conditions(conversation)

        if intervention:
            self.intervention_count += 1
            self.interventions_triggered.append({
                'timestamp': time.time(),
                'conversation': conversation.task,
                'intervention': intervention
            })
            print(f"\n[BRAIN] INTERVENTION TRIGGERED!")
            print(f"Reason: {intervention['reason']}")
            print(f"Recommendation: {intervention['recommendation']}")

        return intervention

    def _check_intervention_conditions(
        self,
        conversation: LiveConversationState
    ) -> Optional[Dict]:
        """
        Check if intervention should be triggered.

        Args:
            conversation: Current conversation state

        Returns:
            Intervention dict if conditions met, None otherwise
        """
        features = conversation.get_features()

        # Condition 1: High error count
        if conversation.error_count >= self.error_threshold:
            return self._generate_intervention(
                conversation,
                reason=f"High error count ({conversation.error_count})",
                urgency="high"
            )

        # Condition 2: Tool repetition (stuck in loop)
        if conversation.max_tool_repetition >= self.repetition_threshold:
            return self._generate_intervention(
                conversation,
                reason=f"Tool repetition detected ({conversation.max_tool_repetition}x '{conversation.last_tool}')",
                urgency="critical"
            )

        # Condition 3: QA rejecting repeatedly
        if conversation.qa_reject_count >= self.qa_reject_threshold:
            return self._generate_intervention(
                conversation,
                reason=f"QA rejected {conversation.qa_reject_count} times (quality degrading)",
                urgency="high"
            )

        # Condition 4: User confusion (many clarifications)
        if conversation.clarification_count >= self.clarification_threshold:
            return self._generate_intervention(
                conversation,
                reason=f"User requested {conversation.clarification_count} clarifications (task unclear)",
                urgency="medium"
            )

        # Condition 5: Duration exceeds expected
        expected_duration = self._get_expected_duration(conversation.tool_type)
        if expected_duration and conversation.get_duration() > expected_duration * self.duration_multiplier:
            return self._generate_intervention(
                conversation,
                reason=f"Duration ({conversation.get_duration():.1f}s) exceeds expected ({expected_duration:.1f}s)",
                urgency="medium"
            )

        return None

    def _generate_intervention(
        self,
        conversation: LiveConversationState,
        reason: str,
        urgency: str
    ) -> Dict:
        """
        Generate intervention with strategy recommendation.

        Args:
            conversation: Current conversation
            reason: Why intervention triggered
            urgency: Urgency level

        Returns:
            Intervention dict with recommendations
        """
        # Get recommendation from strategy library
        recommendation = self.strategy_library.get_recommendation(
            task_type=conversation.tool_type,
            current_errors=conversation.error_count
        )

        intervention = {
            'reason': reason,
            'urgency': urgency,
            'current_state': conversation.get_features(),
            'recommendation': None,
            'alternatives': []
        }

        if recommendation:
            intervention['recommendation'] = {
                'strategy': recommendation['strategy'],
                'expected_duration': recommendation['expected_duration'],
                'success_rate': recommendation['success_rate'],
                'confidence': recommendation['confidence']
            }
            intervention['alternatives'] = recommendation.get('alternatives', [])
            intervention['message'] = recommendation.get('message', 'Consider proven alternative strategy')
        else:
            intervention['message'] = f"No proven strategies found for {conversation.tool_type}. Consider terminating."

        return intervention

    def _get_expected_duration(self, tool_type: str) -> Optional[float]:
        """Get expected duration for a tool type from strategy library."""
        strategies = self.strategy_library.retrieve_strategies(tool_type, top_k=1)
        if strategies:
            return strategies[0].duration
        return None

    def end_conversation(
        self,
        conversation: LiveConversationState,
        success: bool,
        outcome: str = "completed"
    ):
        """
        End conversation monitoring and learn from it.

        Args:
            conversation: Conversation to finalize
            success: Whether task succeeded
            outcome: Outcome description
        """
        conversation.finalize(success, outcome)

        print(f"\n[BRAIN] Conversation ended: {outcome}")
        print(f"  Duration: {conversation.get_duration():.1f}s")
        print(f"  Tools used: {len(conversation.tool_calls)}")
        print(f"  Errors: {conversation.error_count}")
        print(f"  Success: {success}")

        # Learn from this conversation
        self._learn_from_conversation(conversation)

        self.conversations_monitored += 1

        # Check if intervention prevented failure
        if not success and self.intervention_count > 0:
            # Failure occurred despite intervention
            print(f"[BRAIN] Failure occurred (intervention did not prevent)")
        elif success and self.intervention_count > 0:
            # Success after intervention
            self.failures_prevented += 1
            print(f"[BRAIN] Success after intervention (possibly prevented failure)")

        # Reset for next conversation
        self.current_conversation = None
        self.intervention_count = 0

    def _learn_from_conversation(self, conversation: LiveConversationState):
        """
        Learn from completed conversation.

        Args:
            conversation: Completed conversation
        """
        features = conversation.get_features()

        # Add to strategy library if successful
        if conversation.success:
            self.strategy_library.add_strategy(
                task_type=features['tool_type'],
                tool_sequence=features['tools_used'],
                duration=features['duration_seconds'],
                success=True
            )
            print(f"[BRAIN] Added successful strategy to library")

        # Update meta-router (encode failures in hippocampus)
        # Note: We'd need to convert features to ConversationTrace for full integration
        print(f"[BRAIN] Learning from conversation pattern")

    def get_statistics(self) -> Dict:
        """Get monitoring statistics."""
        return {
            'conversations_monitored': self.conversations_monitored,
            'interventions_triggered': len(self.interventions_triggered),
            'failures_prevented': self.failures_prevented,
            'strategy_library_size': self.strategy_library.total_strategies,
            'intervention_history': self.interventions_triggered[-10:]  # Last 10
        }

    def visualize_statistics(self) -> str:
        """Create ASCII visualization of statistics."""
        stats = self.get_statistics()

        lines = []
        lines.append("="*80)
        lines.append("LIVE BRAIN MONITOR STATISTICS")
        lines.append("="*80)
        lines.append("")
        lines.append(f"Conversations Monitored: {stats['conversations_monitored']}")
        lines.append(f"Interventions Triggered: {stats['interventions_triggered']}")
        lines.append(f"Failures Prevented: {stats['failures_prevented']}")
        lines.append(f"Strategy Library Size: {stats['strategy_library_size']}")
        lines.append("")

        if stats['intervention_history']:
            lines.append("RECENT INTERVENTIONS:")
            lines.append("-"*80)
            for i, interv in enumerate(stats['intervention_history'][-5:], 1):
                lines.append(f"{i}. {interv['conversation']}")
                lines.append(f"   Reason: {interv['intervention']['reason']}")
                lines.append(f"   Urgency: {interv['intervention']['urgency']}")
                lines.append("")

        lines.append("="*80)
        return "\n".join(lines)
