# -*- coding: utf-8 -*-
"""
ML-ready conversation logger with sense classification.

Logs agent conversations in JSONL format optimized for machine learning training:
- Structured conversation turns with complete context
- Tool calls and results with sense classification
- Agent thinking/reasoning processes
- Rich metadata (tokens, latency, model used)
- Six-sense taxonomy (VISUAL, TACTILE, MEMORY, LINGUISTIC, TEMPORAL, COLLABORATIVE)

Output format: JSONL (JSON Lines) - one event per line
Output location: data/logs/conversations/{tool}_{timestamp}_{session_id}.jsonl

Example usage:
    >>> from conversation_logger import ConversationLogger, SenseCategory
    >>> logger = ConversationLogger("session_123", "memory", SenseCategory.MEMORY)
    >>> logger.log_session_start(task="Create entity", model="gpt-4o-mini")
    >>> logger.log_conversation_turn(agent="MemoryOperator", ...)
    >>> logger.log_session_end(status="completed")
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, asdict, field
from enum import Enum


class SenseCategory(Enum):
    """Six sense categories for MCP tools, inspired by human sensory perception."""
    VISUAL = "VISUAL"           # 👁️ Seeing: screenshots, UI, layout, DOM
    TACTILE = "TACTILE"         # ✋ Touch: files, processes, system manipulation
    MEMORY = "MEMORY"           # 🧠 Memory: storage, retrieval, knowledge graphs
    LINGUISTIC = "LINGUISTIC"   # 📝 Language: text processing, search, comprehension
    TEMPORAL = "TEMPORAL"       # ⏰ Time: scheduling, sequences, workflows
    COLLABORATIVE = "COLLABORATIVE"  # 🤝 Social: collaboration, version control


@dataclass
class SenseModality:
    """Multi-modal sense configuration for fusion tracking."""
    primary: SenseCategory
    secondary: Optional[List[SenseCategory]] = None
    fusion: bool = False
    fusion_description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "primary": self.primary.value,
            "secondary": [s.value for s in self.secondary] if self.secondary else None,
            "fusion": self.fusion,
            "fusion_description": self.fusion_description
        }


@dataclass
class ThinkingLog:
    """Agent reasoning/thinking process log."""
    reasoning_steps: List[str] = field(default_factory=list)
    sense_perception: Optional[str] = None
    complexity: str = "simple"  # simple, moderate, complex

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "reasoning_steps": self.reasoning_steps,
            "sense_perception": self.sense_perception,
            "complexity": self.complexity
        }


@dataclass
class ToolCall:
    """Individual tool invocation with sense classification."""
    tool_name: str
    sense_operation: str  # e.g., "MEMORY.write", "VISUAL.capture"
    arguments: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    predicted_outcome: Optional[str] = None
    fusion_senses: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tool_name": self.tool_name,
            "sense_operation": self.sense_operation,
            "arguments": self.arguments,
            "timestamp": self.timestamp,
            "predicted_outcome": self.predicted_outcome,
            "fusion_senses": self.fusion_senses
        }


@dataclass
class ToolResult:
    """Tool execution result with performance metrics."""
    tool_name: str
    sense_operation: str
    status: str  # success, error, timeout
    result: Any = None
    timestamp: str = ""
    latency_ms: int = 0
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tool_name": self.tool_name,
            "sense_operation": self.sense_operation,
            "status": self.status,
            "result": self.result,
            "timestamp": self.timestamp,
            "latency_ms": self.latency_ms,
            "error_message": self.error_message
        }


class ConversationLogger:
    """
    ML-ready conversation logger with six-sense classification.

    Logs structured agent conversations to JSONL format for ML training with:
    - Complete conversation turns (task -> thinking -> tool calls -> results)
    - Sense category classification (VISUAL, TACTILE, MEMORY, etc.)
    - Multi-modal fusion tracking
    - Rich metadata (model, tokens, latency, timestamps)
    - Separate file per session for easy dataset management

    Attributes:
        session_id: Unique session identifier
        tool_name: Name of the MCP tool (e.g., "memory", "playwright")
        sense_category: Primary sense category for this tool
        output_path: Path to JSONL output file
        turn_number: Current conversation turn counter
    """

    def __init__(
        self,
        session_id: str,
        tool_name: str,
        sense_category: Union[SenseCategory, str],
        output_dir: str = "data/logs/conversations",
        enable_fusion_tracking: bool = True
    ):
        """Initialize conversation logger.

        Args:
            session_id: Unique session identifier
            tool_name: Name of MCP tool (e.g., "memory", "playwright")
            sense_category: Primary sense category (SenseCategory enum or string)
            output_dir: Directory for conversation logs (default: data/logs/conversations)
            enable_fusion_tracking: Track multi-modal sense fusion (default: True)
        """
        self.session_id = session_id
        self.tool_name = tool_name

        # Convert string to SenseCategory if needed
        if isinstance(sense_category, str):
            self.sense_category = SenseCategory(sense_category)
        else:
            self.sense_category = sense_category

        self.enable_fusion_tracking = enable_fusion_tracking

        # Load sense taxonomy configuration
        self.sense_taxonomy = self._load_sense_taxonomy()

        # Determine sense modality (primary + secondary senses)
        self.sense_modality = self._determine_modality()

        # Setup output file
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{tool_name}_{timestamp}_{session_id}.jsonl"
        self.output_path = Path(output_dir) / filename
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # Conversation state
        self.turn_number = 0
        self.sense_statistics = {cat.value: {"operations": 0} for cat in SenseCategory}

    def _load_sense_taxonomy(self) -> Dict[str, Any]:
        """Load sense taxonomy configuration from JSON file."""
        try:
            taxonomy_path = Path(__file__).parent / "sense_taxonomy.json"
            if taxonomy_path.exists():
                with open(taxonomy_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass

        # Return minimal default taxonomy if file not found
        return {
            "tool_sense_map": {},
            "sense_categories": {}
        }

    def _determine_modality(self) -> SenseModality:
        """Determine sense modality from taxonomy configuration."""
        tool_config = self.sense_taxonomy.get("tool_sense_map", {}).get(self.tool_name, {})

        # Get primary sense
        primary_str = tool_config.get("primary", self.sense_category.value)
        try:
            primary = SenseCategory(primary_str)
        except ValueError:
            primary = self.sense_category

        # Get secondary senses
        secondary_list = tool_config.get("secondary", [])
        secondary = None
        if secondary_list:
            try:
                secondary = [SenseCategory(s) for s in secondary_list]
            except ValueError:
                secondary = None

        # Determine if this is a fusion configuration
        fusion = bool(secondary_list) if secondary_list else False

        fusion_desc = None
        if fusion and secondary:
            sense_names = [primary.value] + [s.value for s in secondary]
            fusion_desc = " + ".join(sense_names)

        return SenseModality(
            primary=primary,
            secondary=secondary,
            fusion=fusion,
            fusion_description=fusion_desc
        )

    def _get_sense_operation(self, tool_name: str) -> tuple[str, Optional[List[str]]]:
        """Get sense operation and fusion senses for a tool call.

        Args:
            tool_name: Name of the tool being called

        Returns:
            Tuple of (sense_operation_string, fusion_senses_list)
        """
        tool_ops = self.sense_taxonomy.get("tool_sense_map", {}).get(
            self.tool_name, {}
        ).get("operations", {})

        senses = tool_ops.get(tool_name, [self.sense_category.value])

        # Primary sense operation
        primary_sense = senses[0] if senses else self.sense_category.value
        sense_operation = f"{primary_sense}.{tool_name}"

        # Fusion senses (if multi-modal)
        fusion_senses = senses if len(senses) > 1 else None

        return sense_operation, fusion_senses

    def _write_event(self, event: Dict[str, Any]) -> None:
        """Write event to JSONL file (one JSON object per line)."""
        try:
            with open(self.output_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event, ensure_ascii=False) + '\n')
        except Exception as e:
            # Silently fail - logging should never crash the agent
            pass

    def log_session_start(
        self,
        task: str,
        model: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log session start event.

        Args:
            task: User's task/query that initiated this session
            model: LLM model being used (e.g., "gpt-4o-mini")
            metadata: Additional metadata (optional)
        """
        event = {
            "session_id": self.session_id,
            "tool": self.tool_name,
            "sense_category": self.sense_category.value,
            "sense_modality": self.sense_modality.to_dict(),
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "event_type": "session.start",
            "data": {
                "task": task,
                "model": model
            },
            "metadata": metadata or {}
        }
        self._write_event(event)

    def log_conversation_turn(
        self,
        agent: str,
        agent_response: str,
        thinking: Optional[ThinkingLog] = None,
        tool_calls: Optional[List[ToolCall]] = None,
        tool_results: Optional[List[ToolResult]] = None,
        final_response: Optional[str] = None,
        tokens: Optional[Dict[str, int]] = None,
        latency_ms: Optional[int] = None
    ) -> None:
        """Log complete conversation turn.

        Args:
            agent: Name of agent handling this turn (e.g., "MemoryOperator")
            agent_response: Agent's initial response to the task
            thinking: Agent's reasoning process (optional)
            tool_calls: List of tool invocations (optional)
            tool_results: List of tool execution results (optional)
            final_response: Agent's final response after tool execution (optional)
            tokens: Token usage statistics (optional)
            latency_ms: Total latency in milliseconds (optional)
        """
        self.turn_number += 1

        # Update sense statistics
        if tool_calls:
            for call in tool_calls:
                sense = call.sense_operation.split('.')[0]
                if sense in self.sense_statistics:
                    self.sense_statistics[sense]["operations"] += 1

        event = {
            "session_id": self.session_id,
            "tool": self.tool_name,
            "sense_category": self.sense_category.value,
            "sense_modality": self.sense_modality.to_dict(),
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "event_type": "conversation.turn",
            "turn_number": self.turn_number,
            "data": {
                "agent": agent,
                "agent_response": agent_response,
                "thinking": thinking.to_dict() if thinking else None,
                "tool_calls": [tc.to_dict() for tc in tool_calls] if tool_calls else [],
                "tool_results": [tr.to_dict() for tr in tool_results] if tool_results else [],
                "final_response": final_response
            },
            "metadata": {
                "tokens": tokens,
                "latency_ms": latency_ms,
                "sense_statistics": self.sense_statistics.copy()
            }
        }
        self._write_event(event)

    def log_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        predicted_outcome: Optional[str] = None
    ) -> ToolCall:
        """Log individual tool call and return ToolCall object.

        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments/parameters
            predicted_outcome: Agent's prediction of what will happen (optional)

        Returns:
            ToolCall object that can be passed to log_conversation_turn()
        """
        sense_operation, fusion_senses = self._get_sense_operation(tool_name)

        tool_call = ToolCall(
            tool_name=tool_name,
            sense_operation=sense_operation,
            arguments=arguments,
            timestamp=datetime.utcnow().isoformat() + 'Z',
            predicted_outcome=predicted_outcome,
            fusion_senses=fusion_senses
        )

        return tool_call

    def log_tool_result(
        self,
        tool_name: str,
        status: str,
        result: Any = None,
        latency_ms: int = 0,
        error_message: Optional[str] = None
    ) -> ToolResult:
        """Log tool execution result and return ToolResult object.

        Args:
            tool_name: Name of the tool that was executed
            status: Execution status ("success", "error", "timeout")
            result: Tool execution result (optional)
            latency_ms: Execution latency in milliseconds
            error_message: Error message if status is "error" (optional)

        Returns:
            ToolResult object that can be passed to log_conversation_turn()
        """
        sense_operation, _ = self._get_sense_operation(tool_name)

        tool_result = ToolResult(
            tool_name=tool_name,
            sense_operation=sense_operation,
            status=status,
            result=result,
            timestamp=datetime.utcnow().isoformat() + 'Z',
            latency_ms=latency_ms,
            error_message=error_message
        )

        return tool_result

    def log_thinking(
        self,
        agent: str,
        reasoning_steps: List[str],
        complexity: str = "simple"
    ) -> None:
        """Log agent thinking/reasoning as a separate event.

        Args:
            agent: Agent name doing the thinking
            reasoning_steps: List of reasoning steps
            complexity: Task complexity ("simple", "moderate", "complex")
        """
        event = {
            "session_id": self.session_id,
            "tool": self.tool_name,
            "sense_category": self.sense_category.value,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "event_type": "agent.thinking",
            "data": {
                "agent": agent,
                "reasoning_steps": reasoning_steps,
                "sense_perception": f"{self.sense_category.value} - {self.tool_name}",
                "complexity": complexity
            }
        }
        self._write_event(event)

    def log_validation(
        self,
        validator: str,
        feedback: str,
        approved: bool,
        corrections: Optional[List[str]] = None
    ) -> None:
        """Log QA validator feedback.

        Args:
            validator: Name of validator agent (e.g., "QAValidator")
            feedback: Validator's feedback message
            approved: Whether the work was approved
            corrections: List of required corrections if not approved (optional)
        """
        event = {
            "session_id": self.session_id,
            "tool": self.tool_name,
            "sense_category": self.sense_category.value,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "event_type": "validation.check",
            "data": {
                "validator": validator,
                "feedback": feedback,
                "approved": approved,
                "corrections": corrections or []
            }
        }
        self._write_event(event)

    def log_session_end(
        self,
        status: str,
        summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log session end event.

        Args:
            status: Final session status ("completed", "error", "timeout", "cancelled")
            summary: Summary of what was accomplished (optional)
            metadata: Additional metadata (optional)
        """
        event = {
            "session_id": self.session_id,
            "tool": self.tool_name,
            "sense_category": self.sense_category.value,
            "sense_modality": self.sense_modality.to_dict(),
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "event_type": "session.end",
            "data": {
                "status": status,
                "summary": summary,
                "total_turns": self.turn_number
            },
            "metadata": {
                "sense_statistics": self.sense_statistics,
                **(metadata or {})
            }
        }
        self._write_event(event)

    def log_error(
        self,
        error_type: str,
        error_message: str,
        stacktrace: Optional[str] = None
    ) -> None:
        """Log error event.

        Args:
            error_type: Type of error (e.g., "ToolExecutionError", "ValidationError")
            error_message: Error message
            stacktrace: Full stack trace (optional)
        """
        event = {
            "session_id": self.session_id,
            "tool": self.tool_name,
            "sense_category": self.sense_category.value,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "event_type": "error",
            "data": {
                "error_type": error_type,
                "error_message": error_message,
                "stacktrace": stacktrace
            }
        }
        self._write_event(event)


# Helper function for quick logger creation
def create_conversation_logger(
    session_id: str,
    tool_name: str,
    sense_category: Union[SenseCategory, str]
) -> ConversationLogger:
    """Create a conversation logger with default settings.

    Args:
        session_id: Session identifier
        tool_name: MCP tool name
        sense_category: Primary sense category

    Returns:
        Configured ConversationLogger instance
    """
    return ConversationLogger(session_id, tool_name, sense_category)
