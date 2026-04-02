"""
Context-Aligned State System

This module implements conversation states with context alignment as a temporal
dimension. Context alignment (0-1) measures how familiar we are with the current
conversation territory, enabling confidence-based adaptation.

Key Concepts:
- Context alignment: 0.0 = new territory, 1.0 = familiar territory
- Confidence level: Adapts based on success/failure
- Action hierarchy: tool_call (1.0) > agent_response (0.5) > thinking (0.1)
- Multiple context dimensions: technical, user preference, task type

Author: Tahlamus Brain Team
Date: 2025-10-24
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
import numpy as np


@dataclass
class ActionMetadata:
    """Metadata for an action performed in this state"""
    action_type: str  # "tool_call", "agent_response", "thinking", "waiting"
    action_name: str  # Specific tool/operation name
    success: bool  # Whether action succeeded
    duration: float  # Time taken (seconds)
    result: Optional[str] = None  # Action result/output
    error: Optional[str] = None  # Error message if failed

    @property
    def action_value(self) -> float:
        """
        Hierarchical value of this action type.

        tool_call = 1.0 (highest: definite progress)
        agent_response = 0.5 (medium: potential progress)
        thinking = 0.1 (low: no observable progress)
        waiting = 0.05 (minimal: passive state)
        """
        ACTION_HIERARCHY = {
            'tool_call': 1.0,
            'agent_response': 0.5,
            'thinking': 0.1,
            'waiting': 0.05
        }
        return ACTION_HIERARCHY.get(self.action_type, 0.0)

    @property
    def is_checkpoint(self) -> bool:
        """
        This action represents a checkpoint if:
        - Tool call succeeded (definite progress)
        - Agent response with high value (semantic progress)
        """
        if self.action_type == 'tool_call' and self.success:
            return True

        if self.action_type == 'agent_response' and self.success:
            # Could add semantic validation here
            return True

        return False


@dataclass
class ContextDimensions:
    """
    Multiple dimensions of context alignment (all 0-1 scale).

    Higher values = more familiar = better prediction.
    """
    technical_context: float = 0.0  # Technical domain familiarity
    user_preference_context: float = 0.0  # User's style/preference familiarity
    task_context: float = 0.0  # Task type familiarity
    conversation_continuity: float = 0.0  # Thread continuity (same topic)

    @property
    def overall_alignment(self) -> float:
        """Weighted average of all context dimensions"""
        return (
            0.3 * self.technical_context +
            0.2 * self.user_preference_context +
            0.3 * self.task_context +
            0.2 * self.conversation_continuity
        )


@dataclass
class ContextAlignedState:
    """
    Conversation state with context alignment as temporal dimension.

    This is the core state representation for the quantum checkpoint system.
    Each state tracks:
    - Context alignment (0-1): How familiar is this territory?
    - Confidence level (0-1): How sure are we of our actions?
    - Action metadata: What action led to this state?
    - Checkpoint status: Is this a verified progress point?

    Context alignment enables temporal reasoning:
    - High context = fast navigation (familiar paths)
    - Low context = slow exploration (new territory)
    """

    # Identity
    state_id: str
    step_count: int
    timestamp: datetime = field(default_factory=datetime.now)

    # State content
    puzzle_state: Optional[Any] = None  # Klotski board or conversation status
    state_summary: str = ""  # Human-readable description

    # Context dimensions (0-1 scale)
    context: ContextDimensions = field(default_factory=ContextDimensions)

    # Confidence and adaptation
    confidence_level: float = 0.5  # 0-1: How confident are we?
    ctm_thinking_rate: float = 0.5  # How often CTM should provide hints

    # Action that led to this state
    last_action: Optional[ActionMetadata] = None

    # Checkpoint status
    is_checkpoint: bool = False
    checkpoint_type: str = ""  # "tool_success", "semantic_progress", "goal_reached"
    reliability_score: float = 0.0  # How reliable is this checkpoint (0-1)

    # Path tracking
    path_progress: float = 0.0  # 0-1: How far along optimal path?
    cumulative_time: float = 0.0  # Total time from start (seconds)

    # Parent state (for path reconstruction)
    parent_state_id: Optional[str] = None

    # Multi-path tracking
    alternative_paths: List[str] = field(default_factory=list)  # Other state IDs

    # Goal status
    is_goal: bool = False
    is_stuck: bool = False

    def calculate_context_alignment(
        self,
        previous_states: List['ContextAlignedState'],
        use_embeddings: bool = False
    ) -> float:
        """
        Calculate context alignment with conversation history.

        Higher alignment = we've seen similar states before = faster prediction.

        Args:
            previous_states: Recent conversation history
            use_embeddings: Use semantic embeddings (slower but more accurate)

        Returns:
            Context alignment score (0-1)
        """
        if not previous_states:
            return 0.0  # New conversation, no context

        # Compare current state with recent history (last 10 states)
        recent_states = previous_states[-10:]

        alignments = []
        for i, prev_state in enumerate(recent_states):
            if use_embeddings:
                alignment = self._semantic_similarity_embedding(prev_state)
            else:
                alignment = self._semantic_similarity_simple(prev_state)

            alignments.append(alignment)

        # Average alignment with exponential decay (recent states weighted more)
        weights = np.array([0.9 ** i for i in range(len(alignments))])
        weighted_avg = np.average(alignments, weights=weights)

        return float(weighted_avg)

    def _semantic_similarity_simple(self, other: 'ContextAlignedState') -> float:
        """
        Simple semantic similarity based on action types and success patterns.

        Fast approximation without embeddings.
        """
        similarity_score = 0.0

        # Same action type (max 0.4 points)
        if self.last_action and other.last_action:
            if self.last_action.action_type == other.last_action.action_type:
                similarity_score += 0.4

            # Same action name gives bonus (max 0.3 points)
            # But only if we didn't already get full credit for type
            if self.last_action.action_name == other.last_action.action_name:
                similarity_score += 0.3
            elif self._actions_are_related(self.last_action.action_name, other.last_action.action_name):
                # Related actions (e.g., read_file and write_file) get partial credit
                similarity_score += 0.2

            # Same success pattern (max 0.2 points)
            if self.last_action.success == other.last_action.success:
                similarity_score += 0.2

        # Similar progress level (max 0.1 points)
        progress_diff = abs(self.path_progress - other.path_progress)
        if progress_diff < 0.1:
            similarity_score += 0.1

        return min(1.0, similarity_score)

    def _actions_are_related(self, action1: str, action2: str) -> bool:
        """Check if two actions are related (e.g., read_file and write_file)"""
        # File operations
        file_ops = {'read_file', 'write_file', 'edit_file'}
        if action1 in file_ops and action2 in file_ops:
            return True

        # API operations
        api_ops = {'api_get', 'api_post', 'api_put', 'api_delete'}
        if action1 in api_ops and action2 in api_ops:
            return True

        # DevOps operations
        devops_ops = {'deploy', 'configure', 'monitor', 'rollback'}
        if action1 in devops_ops and action2 in devops_ops:
            return True

        return False

    def _semantic_similarity_embedding(self, other: 'ContextAlignedState') -> float:
        """
        Semantic similarity using embeddings (more accurate, slower).

        Would use sentence-transformers or similar.
        """
        # Placeholder for future implementation
        # Would embed state_summary and compare cosine similarity
        return self._semantic_similarity_simple(other)

    def update_context_dimensions(
        self,
        technical_context: Optional[float] = None,
        user_preference_context: Optional[float] = None,
        task_context: Optional[float] = None,
        conversation_continuity: Optional[float] = None
    ):
        """Update specific context dimensions"""
        if technical_context is not None:
            self.context.technical_context = np.clip(technical_context, 0.0, 1.0)
        if user_preference_context is not None:
            self.context.user_preference_context = np.clip(user_preference_context, 0.0, 1.0)
        if task_context is not None:
            self.context.task_context = np.clip(task_context, 0.0, 1.0)
        if conversation_continuity is not None:
            self.context.conversation_continuity = np.clip(conversation_continuity, 0.0, 1.0)

    def adapt_confidence(self, success: bool, learning_rate: float = 0.05):
        """
        Adapt confidence level based on action outcome.

        Success → confidence increases
        Failure → confidence decreases (more dramatic)

        Args:
            success: Whether the action succeeded
            learning_rate: How fast confidence changes
        """
        if success:
            self.confidence_level = min(1.0, self.confidence_level + learning_rate)
        else:
            # Failures decrease confidence more dramatically
            self.confidence_level = max(0.0, self.confidence_level - (2 * learning_rate))

        # Update CTM thinking rate (inverse of confidence)
        self.ctm_thinking_rate = 1.0 - self.confidence_level

    def mark_as_checkpoint(
        self,
        checkpoint_type: str,
        reliability_score: float
    ):
        """
        Mark this state as a checkpoint.

        Args:
            checkpoint_type: "tool_success", "semantic_progress", "goal_reached"
            reliability_score: 0-1 confidence in this checkpoint
        """
        self.is_checkpoint = True
        self.checkpoint_type = checkpoint_type
        self.reliability_score = np.clip(reliability_score, 0.0, 1.0)

    def get_hint_interval(self) -> int:
        """
        Calculate how often CTM should provide hints based on confidence.

        Low confidence (0.0) → hint every 1 step (novice mode)
        High confidence (1.0) → hint every 20 steps (expert mode)

        Returns:
            Number of steps between hints
        """
        return 1 + int(self.confidence_level * 19)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state to dictionary"""
        return {
            'state_id': self.state_id,
            'step_count': self.step_count,
            'timestamp': self.timestamp.isoformat(),
            'state_summary': self.state_summary,
            'context': {
                'technical': self.context.technical_context,
                'user_preference': self.context.user_preference_context,
                'task': self.context.task_context,
                'continuity': self.context.conversation_continuity,
                'overall': self.context.overall_alignment
            },
            'confidence_level': self.confidence_level,
            'ctm_thinking_rate': self.ctm_thinking_rate,
            'last_action': {
                'type': self.last_action.action_type if self.last_action else None,
                'name': self.last_action.action_name if self.last_action else None,
                'success': self.last_action.success if self.last_action else None,
                'value': self.last_action.action_value if self.last_action else 0.0,
                'is_checkpoint': self.last_action.is_checkpoint if self.last_action else False
            } if self.last_action else None,
            'is_checkpoint': self.is_checkpoint,
            'checkpoint_type': self.checkpoint_type,
            'reliability_score': self.reliability_score,
            'path_progress': self.path_progress,
            'cumulative_time': self.cumulative_time,
            'is_goal': self.is_goal,
            'is_stuck': self.is_stuck
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContextAlignedState':
        """Deserialize state from dictionary"""
        # Create context dimensions
        context = ContextDimensions(
            technical_context=data['context']['technical'],
            user_preference_context=data['context']['user_preference'],
            task_context=data['context']['task'],
            conversation_continuity=data['context']['continuity']
        )

        # Create last action if present
        last_action = None
        if data.get('last_action'):
            last_action = ActionMetadata(
                action_type=data['last_action']['type'],
                action_name=data['last_action']['name'],
                success=data['last_action']['success'],
                duration=0.0  # Not stored in dict
            )

        # Create state
        return cls(
            state_id=data['state_id'],
            step_count=data['step_count'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            state_summary=data['state_summary'],
            context=context,
            confidence_level=data['confidence_level'],
            ctm_thinking_rate=data['ctm_thinking_rate'],
            last_action=last_action,
            is_checkpoint=data['is_checkpoint'],
            checkpoint_type=data['checkpoint_type'],
            reliability_score=data['reliability_score'],
            path_progress=data['path_progress'],
            cumulative_time=data['cumulative_time'],
            is_goal=data['is_goal'],
            is_stuck=data['is_stuck']
        )

    def __repr__(self) -> str:
        checkpoint_marker = "[CHECKPOINT]" if self.is_checkpoint else ""
        return (
            f"ContextAlignedState({checkpoint_marker} "
            f"step={self.step_count}, "
            f"context={self.context.overall_alignment:.2f}, "
            f"confidence={self.confidence_level:.2f}, "
            f"progress={self.path_progress:.2f})"
        )
