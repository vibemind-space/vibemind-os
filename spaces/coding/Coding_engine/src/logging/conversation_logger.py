"""
ConversationLogger - Real-time conversation logging for agent interactions.

This module provides:
1. Per-agent JSON log files with real-time writing
2. Phase transition tracking
3. Output validation logging
4. Structured message format with metadata

Log Structure:
    logs/conversations/{job_id}/
        ├── architect_agent.json
        ├── coordinator_agent.json
        ├── generator_agent.json
        ├── recovery_agent.json
        ├── validation_agent.json
        └── _transitions.json
"""
import json
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, Dict, List
from contextlib import contextmanager
import structlog

logger = structlog.get_logger()

# Global logger instance
_global_logger: Optional["ConversationLogger"] = None
_global_lock = threading.Lock()


@dataclass
class ConversationMessage:
    """A single message in an agent conversation."""
    timestamp: str
    role: str  # "system", "user", "assistant", "tool"
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def create(
        cls,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ConversationMessage":
        """Create a new message with current timestamp."""
        return cls(
            timestamp=datetime.utcnow().isoformat() + "Z",
            role=role,
            content=content,
            metadata=metadata or {},
        )


@dataclass
class AgentConversation:
    """Complete conversation log for a single agent."""
    agent_name: str
    job_id: str
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    messages: List[ConversationMessage] = field(default_factory=list)
    completed_at: Optional[str] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConversationMessage:
        """Add a message to the conversation."""
        msg = ConversationMessage.create(role, content, metadata)
        self.messages.append(msg)
        return msg
    
    def complete(self, success: bool = True):
        """Mark the conversation as complete."""
        self.completed_at = datetime.utcnow().isoformat() + "Z"
        
        # Calculate duration
        start = datetime.fromisoformat(self.started_at.rstrip("Z"))
        end = datetime.fromisoformat(self.completed_at.rstrip("Z"))
        duration_ms = int((end - start).total_seconds() * 1000)
        
        self.summary = {
            "total_messages": len(self.messages),
            "duration_ms": duration_ms,
            "success": success,
            "message_counts": self._count_by_role(),
        }
    
    def _count_by_role(self) -> Dict[str, int]:
        """Count messages by role."""
        counts: Dict[str, int] = {}
        for msg in self.messages:
            counts[msg.role] = counts.get(msg.role, 0) + 1
        return counts
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "agent_name": self.agent_name,
            "job_id": self.job_id,
            "started_at": self.started_at,
            "messages": [m.to_dict() for m in self.messages],
            "completed_at": self.completed_at,
            "summary": self.summary,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


@dataclass
class TransitionEvent:
    """A phase transition event in the pipeline."""
    timestamp: str
    from_phase: str
    to_phase: str
    input_summary: Dict[str, Any] = field(default_factory=dict)
    output_summary: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    duration_ms: int = 0
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def create(
        cls,
        from_phase: str,
        to_phase: str,
        input_summary: Optional[Dict[str, Any]] = None,
        output_summary: Optional[Dict[str, Any]] = None,
        success: bool = True,
        duration_ms: int = 0,
        error: Optional[str] = None,
    ) -> "TransitionEvent":
        """Create a new transition event."""
        return cls(
            timestamp=datetime.utcnow().isoformat() + "Z",
            from_phase=from_phase,
            to_phase=to_phase,
            input_summary=input_summary or {},
            output_summary=output_summary or {},
            success=success,
            duration_ms=duration_ms,
            error=error,
        )


class ConversationLogger:
    """
    Real-time conversation logger for agent interactions.
    
    Writes JSON files per agent with automatic flushing.
    
    Usage:
        logger = ConversationLogger("job_123")
        
        with logger.agent_context("architect_agent") as agent:
            agent.log("user", "Analyze requirements...")
            agent.log("assistant", "Creating contracts...")
        
        logger.log_transition("phase_1", "phase_2", {...})
    """
    
    DEFAULT_LOG_DIR = Path("logs/conversations")
    
    def __init__(
        self,
        job_id: str,
        log_dir: Optional[Path] = None,
        auto_flush: bool = True,
    ):
        self.job_id = job_id
        self.log_dir = (log_dir or self.DEFAULT_LOG_DIR) / job_id
        self.auto_flush = auto_flush
        
        # Create log directory
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Active conversations
        self._conversations: Dict[str, AgentConversation] = {}
        self._transitions: List[TransitionEvent] = []
        self._lock = threading.Lock()
        
        # Initialize transitions file
        self._init_transitions_file()
        
        logger.info(
            "conversation_logger_initialized",
            job_id=job_id,
            log_dir=str(self.log_dir),
        )
    
    def _init_transitions_file(self):
        """Initialize the transitions JSON file."""
        transitions_path = self.log_dir / "_transitions.json"
        if not transitions_path.exists():
            with open(transitions_path, "w", encoding="utf-8") as f:
                json.dump({
                    "job_id": self.job_id,
                    "started_at": datetime.utcnow().isoformat() + "Z",
                    "transitions": [],
                }, f, indent=2)
    
    def start_agent(self, agent_name: str) -> AgentConversation:
        """
        Start logging for an agent.
        
        Args:
            agent_name: Name of the agent (e.g., "architect_agent")
            
        Returns:
            AgentConversation instance
        """
        with self._lock:
            if agent_name in self._conversations:
                # Return existing conversation
                return self._conversations[agent_name]
            
            conv = AgentConversation(
                agent_name=agent_name,
                job_id=self.job_id,
            )
            self._conversations[agent_name] = conv
            
            # Write initial file
            self._write_agent_log(agent_name)
            
            logger.debug(
                "agent_conversation_started",
                agent=agent_name,
                job_id=self.job_id,
            )
            
            return conv
    
    def end_agent(self, agent_name: str, success: bool = True):
        """
        End logging for an agent.
        
        Args:
            agent_name: Name of the agent
            success: Whether the agent completed successfully
        """
        with self._lock:
            if agent_name not in self._conversations:
                return
            
            conv = self._conversations[agent_name]
            conv.complete(success)
            self._write_agent_log(agent_name)
            
            logger.debug(
                "agent_conversation_ended",
                agent=agent_name,
                job_id=self.job_id,
                success=success,
                messages=len(conv.messages),
            )
    
    def log_message(
        self,
        agent_name: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConversationMessage:
        """
        Log a message for an agent.
        
        Args:
            agent_name: Name of the agent
            role: Message role ("system", "user", "assistant", "tool")
            content: Message content
            metadata: Optional metadata dict
            
        Returns:
            The created ConversationMessage
        """
        with self._lock:
            # Auto-start if not started
            if agent_name not in self._conversations:
                self.start_agent(agent_name)
            
            conv = self._conversations[agent_name]
            msg = conv.add_message(role, content, metadata)
            
            if self.auto_flush:
                self._write_agent_log(agent_name)
            
            return msg
    
    def log_transition(
        self,
        from_phase: str,
        to_phase: str,
        input_summary: Optional[Dict[str, Any]] = None,
        output_summary: Optional[Dict[str, Any]] = None,
        success: bool = True,
        duration_ms: int = 0,
        error: Optional[str] = None,
    ) -> TransitionEvent:
        """
        Log a phase transition.
        
        Args:
            from_phase: Source phase name
            to_phase: Target phase name
            input_summary: Summary of input data
            output_summary: Summary of output data
            success: Whether transition was successful
            duration_ms: Duration in milliseconds
            error: Error message if failed
            
        Returns:
            The created TransitionEvent
        """
        event = TransitionEvent.create(
            from_phase=from_phase,
            to_phase=to_phase,
            input_summary=input_summary,
            output_summary=output_summary,
            success=success,
            duration_ms=duration_ms,
            error=error,
        )
        
        with self._lock:
            self._transitions.append(event)
            self._write_transitions()
        
        logger.info(
            "phase_transition_logged",
            from_phase=from_phase,
            to_phase=to_phase,
            success=success,
            duration_ms=duration_ms,
        )
        
        return event
    
    def _write_agent_log(self, agent_name: str):
        """Write agent conversation to JSON file."""
        if agent_name not in self._conversations:
            return
        
        conv = self._conversations[agent_name]
        file_path = self.log_dir / f"{agent_name}.json"
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(conv.to_json())
    
    def _write_transitions(self):
        """Write transitions to JSON file."""
        file_path = self.log_dir / "_transitions.json"
        
        data = {
            "job_id": self.job_id,
            "started_at": self._transitions[0].timestamp if self._transitions else None,
            "transitions": [t.to_dict() for t in self._transitions],
            "total_transitions": len(self._transitions),
        }
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def flush(self):
        """Flush all logs to disk."""
        with self._lock:
            for agent_name in self._conversations:
                self._write_agent_log(agent_name)
            self._write_transitions()
    
    def get_conversation(self, agent_name: str) -> Optional[AgentConversation]:
        """Get conversation for an agent."""
        return self._conversations.get(agent_name)
    
    def get_all_conversations(self) -> Dict[str, AgentConversation]:
        """Get all conversations."""
        return dict(self._conversations)
    
    def get_transitions(self) -> List[TransitionEvent]:
        """Get all transitions."""
        return list(self._transitions)
    
    @contextmanager
    def agent_context(self, agent_name: str):
        """
        Context manager for agent conversation.
        
        Usage:
            with logger.agent_context("architect_agent") as agent:
                agent.log("user", "Hello")
                agent.log("assistant", "Hi there")
        """
        self.start_agent(agent_name)
        
        class AgentLogger:
            def __init__(self, parent: ConversationLogger, name: str):
                self._parent = parent
                self._name = name
            
            def log(
                self,
                role: str,
                content: str,
                metadata: Optional[Dict[str, Any]] = None,
            ) -> ConversationMessage:
                return self._parent.log_message(self._name, role, content, metadata)
            
            def log_system(self, content: str, **metadata) -> ConversationMessage:
                return self.log("system", content, metadata or None)
            
            def log_user(self, content: str, **metadata) -> ConversationMessage:
                return self.log("user", content, metadata or None)
            
            def log_assistant(self, content: str, **metadata) -> ConversationMessage:
                return self.log("assistant", content, metadata or None)
            
            def log_tool(self, content: str, tool_name: str, **metadata) -> ConversationMessage:
                meta = {"tool_name": tool_name}
                meta.update(metadata)
                return self.log("tool", content, meta)
        
        agent_logger = AgentLogger(self, agent_name)
        success = True
        
        try:
            yield agent_logger
        except Exception:
            success = False
            raise
        finally:
            self.end_agent(agent_name, success)
    
    def generate_summary(self) -> Dict[str, Any]:
        """Generate a summary of all conversations."""
        return {
            "job_id": self.job_id,
            "log_dir": str(self.log_dir),
            "agents": {
                name: {
                    "messages": len(conv.messages),
                    "started_at": conv.started_at,
                    "completed_at": conv.completed_at,
                    "success": conv.summary.get("success"),
                }
                for name, conv in self._conversations.items()
            },
            "transitions": {
                "total": len(self._transitions),
                "successful": sum(1 for t in self._transitions if t.success),
                "failed": sum(1 for t in self._transitions if not t.success),
            },
        }


def get_logger() -> Optional[ConversationLogger]:
    """Get the global conversation logger."""
    return _global_logger


def init_logger(job_id: str, log_dir: Optional[Path] = None) -> ConversationLogger:
    """
    Initialize the global conversation logger.
    
    Args:
        job_id: Job ID for the logging session
        log_dir: Optional custom log directory
        
    Returns:
        The initialized ConversationLogger
    """
    global _global_logger
    
    with _global_lock:
        _global_logger = ConversationLogger(job_id, log_dir)
        return _global_logger


def cleanup_logger():
    """Cleanup the global logger."""
    global _global_logger
    
    with _global_lock:
        if _global_logger:
            _global_logger.flush()
            _global_logger = None


# Convenience functions for direct usage
def log_agent_message(
    agent_name: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[ConversationMessage]:
    """Log a message to the global logger."""
    if _global_logger:
        return _global_logger.log_message(agent_name, role, content, metadata)
    return None


def log_transition(
    from_phase: str,
    to_phase: str,
    **kwargs,
) -> Optional[TransitionEvent]:
    """Log a transition to the global logger."""
    if _global_logger:
        return _global_logger.log_transition(from_phase, to_phase, **kwargs)
    return None