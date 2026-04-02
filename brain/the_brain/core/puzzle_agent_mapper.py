"""
Puzzle-Agent Mapper - Phase 4
Maps Klotski puzzle moves to agent conversation actions

Key concept: Puzzle solving and agent conversations are isomorphic:
- Puzzle state ≈ Conversation state (context, progress, confidence)
- Puzzle move ≈ Agent action (tool call, response, thinking)
- Puzzle checkpoint ≈ Successful tool call
- Optimal path ≈ Efficient conversation flow

This mapping enables training on puzzle data to improve agent conversations.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
from enum import Enum

from core.context_aligned_state import ContextAlignedState, ActionMetadata, ContextDimensions


class PuzzleActionType(Enum):
    """Types of actions in puzzle solving"""
    MOVE_PIECE = "move_piece"           # Move a piece (like tool call)
    ANALYZE_BOARD = "analyze_board"     # Analyze state (like thinking)
    UNDO_MOVE = "undo_move"             # Backtrack (like retry)
    PLAN_SEQUENCE = "plan_sequence"     # Plan ahead (like reasoning)
    CHECK_GOAL = "check_goal"           # Verify progress (like validation)


class AgentActionType(Enum):
    """Types of actions in agent conversations"""
    TOOL_CALL = "tool_call"             # Execute tool (concrete action)
    AGENT_RESPONSE = "agent_response"   # Generate response (communication)
    THINKING = "thinking"               # Internal reasoning
    RETRY = "retry"                     # Retry failed action
    VALIDATION = "validation"           # Check result
    WAITING = "waiting"                 # Wait for external event


@dataclass
class PuzzleMove:
    """A move in puzzle solving"""
    action_type: PuzzleActionType
    piece_id: Optional[str] = None      # Which piece moved (if applicable)
    direction: Optional[str] = None     # Direction of move (if applicable)
    success: bool = True
    creates_checkpoint: bool = False    # Is this a critical move?
    cost: float = 1.0                   # Time/effort cost


@dataclass
class AgentAction:
    """An action in agent conversation"""
    action_type: AgentActionType
    action_name: str                    # Specific action (e.g., "read_file")
    parameters: Dict = None             # Action parameters
    success: bool = True
    creates_checkpoint: bool = False    # Is this a critical action?
    cost: float = 1.0                   # Time/effort cost


@dataclass
class MappingRule:
    """Rule for mapping puzzle actions to agent actions"""
    puzzle_pattern: str                 # Pattern to match in puzzle
    agent_action: AgentActionType       # Corresponding agent action
    weight: float = 1.0                 # How strongly this mapping applies
    conditions: List[str] = None        # Conditions for mapping


class PuzzleAgentMapper:
    """
    Maps puzzle moves to agent conversation actions

    Enables training on puzzle solving data to improve agent conversations:
    1. Puzzle moves → Agent actions (forward mapping)
    2. Agent actions → Puzzle moves (reverse mapping for interpretation)
    3. Puzzle checkpoints → Agent checkpoints (critical progress points)
    4. Optimal puzzle path → Efficient conversation flow

    This creates a shared representation space for learning.
    """

    def __init__(self):
        """Initialize mapper with default rules"""
        self.mapping_rules = self._initialize_mapping_rules()
        self.action_taxonomy = self._build_action_taxonomy()

        # Statistics
        self.total_mappings = 0
        self.successful_mappings = 0
        self.failed_mappings = 0

    def _initialize_mapping_rules(self) -> List[MappingRule]:
        """
        Initialize mapping rules

        Core insight: Both puzzle and conversation have similar action patterns:
        - Concrete actions (move piece / call tool)
        - Analysis (analyze board / think)
        - Backtracking (undo / retry)
        - Planning (plan sequence / reason)
        - Validation (check goal / validate)
        """
        return [
            # Concrete actions (highest value)
            MappingRule(
                puzzle_pattern="move_piece_successful",
                agent_action=AgentActionType.TOOL_CALL,
                weight=1.0,
                conditions=["success=True", "creates_checkpoint=True"]
            ),

            # Failed actions (retry needed)
            MappingRule(
                puzzle_pattern="move_piece_failed",
                agent_action=AgentActionType.RETRY,
                weight=0.8,
                conditions=["success=False"]
            ),

            # Analysis/thinking
            MappingRule(
                puzzle_pattern="analyze_board",
                agent_action=AgentActionType.THINKING,
                weight=0.3,
                conditions=[]
            ),

            # Planning (before action)
            MappingRule(
                puzzle_pattern="plan_sequence",
                agent_action=AgentActionType.THINKING,
                weight=0.4,
                conditions=["before_checkpoint=True"]
            ),

            # Validation (after action)
            MappingRule(
                puzzle_pattern="check_goal",
                agent_action=AgentActionType.VALIDATION,
                weight=0.6,
                conditions=["after_checkpoint=True"]
            ),

            # Backtracking
            MappingRule(
                puzzle_pattern="undo_move",
                agent_action=AgentActionType.RETRY,
                weight=0.7,
                conditions=["previous_failed=True"]
            ),

            # Communication (agent-specific)
            MappingRule(
                puzzle_pattern="explain_move",
                agent_action=AgentActionType.AGENT_RESPONSE,
                weight=0.5,
                conditions=[]
            )
        ]

    def _build_action_taxonomy(self) -> Dict:
        """
        Build hierarchical action taxonomy

        Maps specific actions to categories for pattern matching:
        - File operations → TOOL_CALL (concrete)
        - API operations → TOOL_CALL (concrete)
        - DevOps operations → TOOL_CALL (concrete)
        - Text generation → AGENT_RESPONSE (communication)
        - Analysis → THINKING (internal)

        Expanded to support tool_call_generator integration:
        - Docker operations → docker_deploy, docker_exec, docker_logs
        - Kubernetes operations → kubectl_apply, kubectl_get, kubectl_delete
        - Git operations → git_commit_push, git_pull, git_branch
        - Monitoring → wait_for_condition, check_status, get_metrics
        - Shell operations → shell_execute, shell_script
        """
        return {
            'tool_call': {
                # File system operations
                'file_ops': [
                    'read_file', 'write_file', 'edit_file', 'delete_file',
                    'create_directory', 'list_files', 'copy_file', 'move_file'
                ],

                # API operations
                'api_ops': [
                    'api_get', 'api_post', 'api_put', 'api_delete',
                    'api_patch', 'api_request', 'fetch_data', 'send_request'
                ],

                # Docker operations (maps to docker_deploy)
                'docker_ops': [
                    'docker_deploy', 'docker_run', 'docker_stop', 'docker_start',
                    'docker_exec', 'docker_logs', 'docker_ps', 'docker_build',
                    'docker_compose_up', 'docker_compose_down'
                ],

                # Kubernetes operations (maps to kubectl_apply)
                'kubernetes_ops': [
                    'kubectl_apply', 'kubectl_get', 'kubectl_delete', 'kubectl_describe',
                    'kubectl_logs', 'kubectl_exec', 'kubectl_port_forward',
                    'kubectl_scale', 'kubectl_rollout', 'helm_install'
                ],

                # Git operations (maps to git_commit_push)
                'git_ops': [
                    'git_commit_push', 'git_pull', 'git_fetch', 'git_branch',
                    'git_merge', 'git_checkout', 'git_status', 'git_diff',
                    'git_clone', 'git_push', 'git_commit'
                ],

                # Database operations
                'db_ops': [
                    'db_query', 'db_insert', 'db_update', 'db_delete',
                    'db_migrate', 'db_backup', 'db_restore', 'db_execute'
                ],

                # Code operations
                'code_ops': [
                    'compile', 'test', 'lint', 'format', 'debug',
                    'run_tests', 'build', 'package', 'install_deps'
                ],

                # Monitoring operations (maps to wait_for_condition)
                'monitoring_ops': [
                    'wait_for_condition', 'check_status', 'get_metrics',
                    'monitor_service', 'check_health', 'verify_deployment',
                    'tail_logs', 'watch_events'
                ],

                # Shell operations (maps to shell_execute)
                'shell_ops': [
                    'shell_execute', 'bash_command', 'run_script',
                    'execute_command', 'run_shell', 'system_command'
                ],

                # Network operations
                'network_ops': [
                    'curl_request', 'ping', 'nslookup', 'netstat',
                    'check_port', 'trace_route', 'download_file'
                ]
            },

            'agent_response': {
                'explanation': ['explain', 'clarify', 'describe', 'elaborate'],
                'question': ['ask', 'inquire', 'request_info', 'query_user'],
                'confirmation': ['confirm', 'acknowledge', 'agree', 'verify_intent'],
                'suggestion': ['suggest', 'recommend', 'propose', 'advise']
            },

            'thinking': {
                'analysis': ['analyze', 'examine', 'investigate', 'assess'],
                'planning': ['plan', 'design', 'strategize', 'architect'],
                'reasoning': ['infer', 'deduce', 'conclude', 'reason'],
                'debugging': ['debug', 'diagnose', 'troubleshoot', 'trace']
            },

            'retry': {
                'correction': ['fix', 'correct', 'adjust', 'patch'],
                'alternative': ['try_alternative', 'different_approach', 'fallback'],
                'modification': ['retry_with_modification', 'modify_and_retry', 'adjust_and_retry']
            },

            'validation': {
                'check': ['verify', 'validate', 'test', 'check', 'confirm'],
                'review': ['review', 'inspect', 'audit', 'examine'],
                'comparison': ['compare', 'diff', 'assert', 'ensure']
            },

            'waiting': {
                'condition': ['wait_for_condition', 'wait_until', 'poll_until'],
                'timeout': ['wait_with_timeout', 'wait_seconds', 'sleep'],
                'event': ['wait_for_event', 'await_completion', 'block_until']
            }
        }

    def puzzle_to_agent(
        self,
        puzzle_move: PuzzleMove,
        context: Optional[Dict] = None
    ) -> AgentAction:
        """
        Map puzzle move to agent action

        Args:
            puzzle_move: Puzzle move to map
            context: Optional context (previous actions, state)

        Returns:
            Corresponding agent action
        """
        context = context or {}

        # Find matching rule
        matching_rule = self._find_matching_rule(puzzle_move, context)

        if not matching_rule:
            # Default mapping
            self.failed_mappings += 1
            return AgentAction(
                action_type=AgentActionType.TOOL_CALL,
                action_name="unknown_action",
                success=puzzle_move.success,
                creates_checkpoint=puzzle_move.creates_checkpoint,
                cost=puzzle_move.cost
            )

        # Create agent action from rule
        self.successful_mappings += 1
        self.total_mappings += 1

        action_name = self._infer_action_name(matching_rule.agent_action, puzzle_move)

        return AgentAction(
            action_type=matching_rule.agent_action,
            action_name=action_name,
            success=puzzle_move.success,
            creates_checkpoint=puzzle_move.creates_checkpoint,
            cost=puzzle_move.cost * matching_rule.weight
        )

    def agent_to_puzzle(
        self,
        agent_action: AgentAction,
        context: Optional[Dict] = None
    ) -> PuzzleMove:
        """
        Map agent action to puzzle move (reverse mapping)

        Useful for interpreting agent behavior in puzzle terms.

        Args:
            agent_action: Agent action to map
            context: Optional context

        Returns:
            Corresponding puzzle move
        """
        context = context or {}

        # Map agent action type to puzzle action type
        puzzle_type_map = {
            AgentActionType.TOOL_CALL: PuzzleActionType.MOVE_PIECE,
            AgentActionType.AGENT_RESPONSE: PuzzleActionType.ANALYZE_BOARD,
            AgentActionType.THINKING: PuzzleActionType.ANALYZE_BOARD,
            AgentActionType.RETRY: PuzzleActionType.UNDO_MOVE,
            AgentActionType.VALIDATION: PuzzleActionType.CHECK_GOAL,
            AgentActionType.WAITING: PuzzleActionType.ANALYZE_BOARD
        }

        puzzle_type = puzzle_type_map.get(
            agent_action.action_type,
            PuzzleActionType.MOVE_PIECE
        )

        return PuzzleMove(
            action_type=puzzle_type,
            piece_id=agent_action.action_name,
            success=agent_action.success,
            creates_checkpoint=agent_action.creates_checkpoint,
            cost=agent_action.cost
        )

    def map_conversation_to_puzzle_path(
        self,
        conversation: List[ContextAlignedState]
    ) -> List[PuzzleMove]:
        """
        Map entire conversation to puzzle path

        Enables analyzing conversations as puzzle-solving episodes.

        Args:
            conversation: List of conversation states

        Returns:
            Equivalent puzzle move sequence
        """
        puzzle_path = []

        for i, state in enumerate(conversation):
            if state.last_action:
                # Create agent action from state
                agent_action = AgentAction(
                    action_type=self._classify_action_type(state.last_action.action_type),
                    action_name=state.last_action.action_name,
                    success=state.last_action.success,
                    creates_checkpoint=state.is_checkpoint,
                    cost=state.last_action.duration
                )

                # Map to puzzle move
                puzzle_move = self.agent_to_puzzle(
                    agent_action,
                    context={'step': i, 'total_steps': len(conversation)}
                )
                puzzle_path.append(puzzle_move)

        return puzzle_path

    def map_puzzle_path_to_conversation(
        self,
        puzzle_path: List[PuzzleMove],
        initial_state: ContextAlignedState
    ) -> List[ContextAlignedState]:
        """
        Map puzzle path to conversation states

        Enables generating conversation data from puzzle solutions.

        Args:
            puzzle_path: Sequence of puzzle moves
            initial_state: Starting conversation state

        Returns:
            Equivalent conversation sequence
        """
        conversation = [initial_state]
        current_state = initial_state

        for i, puzzle_move in enumerate(puzzle_path):
            # Map puzzle move to agent action
            agent_action = self.puzzle_to_agent(
                puzzle_move,
                context={'step': i, 'total_steps': len(puzzle_path)}
            )

            # Create new state from action
            new_state = ContextAlignedState(
                state_id=f"state_{i+1}",
                step_count=i + 1,
                context=ContextDimensions(
                    technical_context=min(1.0, current_state.context.technical_context + 0.05),
                    user_preference_context=current_state.context.user_preference_context,
                    task_context=min(1.0, current_state.context.task_context + 0.05),
                    conversation_continuity=min(1.0, current_state.context.conversation_continuity + 0.03)
                ),
                confidence_level=current_state.confidence_level,
                ctm_thinking_rate=current_state.ctm_thinking_rate,
                last_action=ActionMetadata(
                    action_type=agent_action.action_type.value,
                    action_name=agent_action.action_name,
                    success=agent_action.success,
                    duration=agent_action.cost
                ),
                is_checkpoint=agent_action.creates_checkpoint,
                checkpoint_type='tool_success' if agent_action.creates_checkpoint else '',
                reliability_score=0.8 if agent_action.success else 0.4,
                path_progress=min(1.0, (i + 1) / len(puzzle_path)),
                cumulative_time=current_state.cumulative_time + agent_action.cost
            )

            # Update confidence based on success
            if agent_action.success:
                new_state.adapt_confidence(True)
            else:
                new_state.adapt_confidence(False)

            conversation.append(new_state)
            current_state = new_state

        return conversation

    # ============================================
    # Helper Methods
    # ============================================

    def _find_matching_rule(
        self,
        puzzle_move: PuzzleMove,
        context: Dict
    ) -> Optional[MappingRule]:
        """Find best matching rule for puzzle move"""
        # Build pattern string
        pattern = f"{puzzle_move.action_type.value}"
        if puzzle_move.success:
            pattern += "_successful"
        else:
            pattern += "_failed"

        # Find exact matching rules first
        exact_matches = [
            rule for rule in self.mapping_rules
            if rule.puzzle_pattern == pattern
        ]

        if exact_matches:
            # Return highest weight exact match
            return max(exact_matches, key=lambda r: r.weight)

        # Try base type match (without _successful/_failed)
        base_matches = [
            rule for rule in self.mapping_rules
            if rule.puzzle_pattern.replace("_successful", "").replace("_failed", "") == puzzle_move.action_type.value
        ]

        if base_matches:
            return max(base_matches, key=lambda r: r.weight)

        return None

    def _infer_action_name(
        self,
        action_type: AgentActionType,
        puzzle_move: PuzzleMove
    ) -> str:
        """Infer specific action name from action type"""
        # Get taxonomy for action type
        type_key = action_type.value
        if type_key not in self.action_taxonomy:
            return "generic_action"

        # Choose random action from taxonomy (or use piece_id if available)
        if puzzle_move.piece_id:
            return puzzle_move.piece_id

        # Pick first subcategory and first action
        subcategories = self.action_taxonomy[type_key]
        first_category = list(subcategories.values())[0]
        return first_category[0] if first_category else "generic_action"

    def _classify_action_type(self, action_type_str: str) -> AgentActionType:
        """Classify action type string to enum"""
        type_map = {
            'tool_call': AgentActionType.TOOL_CALL,
            'agent_response': AgentActionType.AGENT_RESPONSE,
            'thinking': AgentActionType.THINKING,
            'retry': AgentActionType.RETRY,
            'validation': AgentActionType.VALIDATION,
            'waiting': AgentActionType.WAITING
        }
        return type_map.get(action_type_str, AgentActionType.TOOL_CALL)

    def get_statistics(self) -> Dict:
        """Get mapping statistics"""
        success_rate = (self.successful_mappings / max(1, self.total_mappings))

        return {
            'total_mappings': self.total_mappings,
            'successful_mappings': self.successful_mappings,
            'failed_mappings': self.failed_mappings,
            'success_rate': success_rate,
            'num_rules': len(self.mapping_rules),
            'taxonomy_categories': len(self.action_taxonomy)
        }
