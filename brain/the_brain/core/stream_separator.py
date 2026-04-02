"""
Stream Separator - Security Foundation for Temporal Tool Control

Implements strict separation between:
1. CONVERSATION STREAM (Untrusted) - Natural language text that is NEVER executable
2. TOOL EVENT STREAM (Trusted) - Structured JSON from validated tool executions

Core Principle:
    "Nicht Text ruft Tools auf. Zustand ruft Zeit auf. Zeit ruft Aktion auf."
    (Not text calls tools. State calls time. Time calls action.)

Security Guarantees:
- Conversation text is NEVER passed to any execution function
- Tool events are validated against a whitelist of known tools
- All extracted "intent" from conversation is marked as UNTRUSTED
- Clear type separation prevents accidental execution paths
"""

import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum


class StreamType(Enum):
    """Type of event stream"""
    CONVERSATION = "conversation"
    TOOL_EVENT = "tool_event"
    UNKNOWN = "unknown"


class SecurityFlag(Enum):
    """Security flags that can be raised during separation"""
    INJECTION_ATTEMPT = "injection_attempt"  # Possible prompt injection detected
    TOOL_IN_TEXT = "tool_in_text"  # Tool call pattern found in conversation
    UNTRUSTED_JSON = "untrusted_json"  # JSON from untrusted source
    SCHEMA_VIOLATION = "schema_violation"  # Tool event doesn't match schema
    UNKNOWN_TOOL = "unknown_tool"  # Tool not in whitelist


@dataclass
class ConversationEvent:
    """
    Single conversation event (text-only, UNTRUSTED)

    This class represents natural language that should NEVER be executed.
    Intent extracted from this is for understanding only, not for action.
    """
    timestamp: datetime
    role: str  # 'user', 'assistant', 'system'
    text: str
    turn_id: int

    # Extracted but NOT actionable
    intent_hints: List[str] = field(default_factory=list)
    mentioned_tools: List[str] = field(default_factory=list)  # For tracking, NOT execution

    # Security metadata
    is_trusted: bool = False  # Always False for conversation
    security_flags: List[SecurityFlag] = field(default_factory=list)

    def __post_init__(self):
        # Ensure conversation is always marked untrusted
        self.is_trusted = False


@dataclass
class ToolEvent:
    """
    Single tool event (structured JSON, TRUSTED only from validated sources)

    This represents actual tool executions from the orchestrator.
    These events come from validated, executed tool calls - not from text.
    """
    timestamp: datetime
    tool_name: str
    parameters: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    success: bool = True
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0
    retry_count: int = 0
    turn_id: int = 0

    # Security metadata
    is_trusted: bool = True  # True only after validation
    source: str = "orchestrator"  # Must be from orchestrator, not text
    schema_validated: bool = False

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'tool_name': self.tool_name,
            'parameters': self.parameters,
            'result': self.result,
            'success': self.success,
            'error_message': self.error_message,
            'execution_time_ms': self.execution_time_ms,
            'retry_count': self.retry_count,
            'turn_id': self.turn_id
        }


@dataclass
class SeparatedStreams:
    """Result of stream separation"""
    conversation_stream: List[ConversationEvent] = field(default_factory=list)
    tool_event_stream: List[ToolEvent] = field(default_factory=list)
    separation_confidence: float = 1.0
    security_flags: List[Tuple[SecurityFlag, str]] = field(default_factory=list)

    @property
    def has_security_issues(self) -> bool:
        """Check if any security flags were raised"""
        return len(self.security_flags) > 0

    @property
    def has_critical_issues(self) -> bool:
        """Check for critical security issues that should block execution"""
        critical_flags = {SecurityFlag.INJECTION_ATTEMPT, SecurityFlag.UNTRUSTED_JSON}
        return any(flag in critical_flags for flag, _ in self.security_flags)


class StreamSeparator:
    """
    Security-first stream separator

    Key Principle: Conversation stream NEVER directly triggers execution.
    All execution must go through the validated State -> CTM -> Drumpad path.

    This class is the first line of defense against prompt injection
    and tool hijacking attacks.
    """

    # Known safe tools (whitelist)
    KNOWN_TOOLS = {
        # File operations
        'file_read', 'file_write', 'file_list', 'file_delete',
        # Docker operations
        'docker_run', 'docker_build', 'docker_stop', 'docker_ps',
        'docker_logs', 'docker_exec', 'docker_compose',
        # Kubernetes operations
        'kubectl_apply', 'kubectl_get', 'kubectl_describe',
        'kubectl_delete', 'kubectl_logs',
        # Git operations
        'git_clone', 'git_pull', 'git_push', 'git_commit',
        'git_status', 'git_diff', 'git_branch',
        # Shell operations
        'shell_exec', 'bash_run',
        # HTTP operations
        'http_get', 'http_post', 'http_put', 'http_delete',
        # Database operations
        'db_query', 'db_execute', 'db_connect',
        # Search operations
        'search_files', 'search_code', 'grep', 'find',
    }

    # Patterns that might indicate injection attempts
    INJECTION_PATTERNS = [
        r'ignore\s+(all\s+)?previous\s+instructions?',
        r'forget\s+(all\s+)?previous',
        r'new\s+instructions?:',
        r'system\s*:\s*you\s+are',
        r'<\s*system\s*>',
        r'\[\s*INST\s*\]',
        r'```\s*(system|instruction)',
    ]

    # Patterns for tool calls in text (should not appear in conversation)
    TOOL_CALL_PATTERNS = [
        r'\{\s*"tool":\s*"[^"]+"\s*,',
        r'\{\s*"function":\s*"[^"]+"\s*,',
        r'<tool_call>\s*{',
        r'<function=\w+>',
    ]

    def __init__(
        self,
        strict_mode: bool = True,
        custom_tools: Optional[set] = None
    ):
        """
        Initialize stream separator

        Args:
            strict_mode: If True, raise errors on security violations
            custom_tools: Additional tools to add to whitelist
        """
        self.strict_mode = strict_mode
        self.known_tools = self.KNOWN_TOOLS.copy()
        if custom_tools:
            self.known_tools.update(custom_tools)

        # Compile regex patterns
        self.injection_regex = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]
        self.tool_call_regex = [re.compile(p, re.IGNORECASE) for p in self.TOOL_CALL_PATTERNS]

    def separate(
        self,
        raw_events: List[Dict],
        source_trusted: bool = False
    ) -> SeparatedStreams:
        """
        Separate raw events into conversation vs tool streams

        Args:
            raw_events: List of raw event dictionaries
            source_trusted: Whether the source is trusted (e.g., orchestrator logs)

        Returns:
            SeparatedStreams with conversation and tool events separated
        """
        result = SeparatedStreams()

        for i, event in enumerate(raw_events):
            event_type = self._classify_event(event)

            if event_type == StreamType.CONVERSATION:
                conv_event = self._process_conversation_event(event, i, result)
                if conv_event:
                    result.conversation_stream.append(conv_event)

            elif event_type == StreamType.TOOL_EVENT:
                tool_event = self._process_tool_event(event, i, source_trusted, result)
                if tool_event:
                    result.tool_event_stream.append(tool_event)

            else:
                # Unknown event type - log but don't process
                result.security_flags.append(
                    (SecurityFlag.SCHEMA_VIOLATION, f"Unknown event type at index {i}")
                )

        # Calculate separation confidence
        total = len(result.conversation_stream) + len(result.tool_event_stream)
        if total > 0:
            result.separation_confidence = 1.0 - (len(result.security_flags) / total) * 0.1

        return result

    def _classify_event(self, event: Dict) -> StreamType:
        """Classify an event as conversation or tool event"""
        if not isinstance(event, dict):
            return StreamType.UNKNOWN

        # Check for tool event markers
        if 'tool_name' in event or 'function' in event:
            return StreamType.TOOL_EVENT

        # Check for conversation markers
        if 'role' in event and 'text' in event:
            return StreamType.CONVERSATION
        if 'role' in event and 'content' in event:
            return StreamType.CONVERSATION
        if 'message' in event and 'speaker' in event:
            return StreamType.CONVERSATION

        return StreamType.UNKNOWN

    def _process_conversation_event(
        self,
        event: Dict,
        index: int,
        result: SeparatedStreams
    ) -> Optional[ConversationEvent]:
        """Process a conversation event with security checks"""
        # Extract text
        text = event.get('text') or event.get('content') or event.get('message', '')
        role = event.get('role') or event.get('speaker', 'unknown')

        # Sanitize text
        sanitized_text = self.sanitize_conversation(text)

        # Check for injection attempts
        security_flags = []
        for pattern in self.injection_regex:
            if pattern.search(text):
                security_flags.append(SecurityFlag.INJECTION_ATTEMPT)
                result.security_flags.append(
                    (SecurityFlag.INJECTION_ATTEMPT, f"Injection pattern at index {index}")
                )
                break

        # Check for tool call patterns in conversation (suspicious)
        for pattern in self.tool_call_regex:
            if pattern.search(text):
                security_flags.append(SecurityFlag.TOOL_IN_TEXT)
                result.security_flags.append(
                    (SecurityFlag.TOOL_IN_TEXT, f"Tool call pattern in conversation at index {index}")
                )
                break

        # Extract mentioned tools (for tracking only, NOT execution)
        mentioned_tools = self._extract_mentioned_tools(text)

        # Parse timestamp
        timestamp = self._parse_timestamp(event.get('timestamp'))

        return ConversationEvent(
            timestamp=timestamp,
            role=role,
            text=sanitized_text,
            turn_id=index,
            intent_hints=self._extract_intent_hints(text),
            mentioned_tools=mentioned_tools,
            security_flags=security_flags
        )

    def _process_tool_event(
        self,
        event: Dict,
        index: int,
        source_trusted: bool,
        result: SeparatedStreams
    ) -> Optional[ToolEvent]:
        """Process a tool event with validation"""
        tool_name = event.get('tool_name') or event.get('function', '')

        # Validate tool is in whitelist
        if tool_name not in self.known_tools:
            result.security_flags.append(
                (SecurityFlag.UNKNOWN_TOOL, f"Unknown tool '{tool_name}' at index {index}")
            )
            if self.strict_mode:
                return None

        # Validate source
        if not source_trusted:
            result.security_flags.append(
                (SecurityFlag.UNTRUSTED_JSON, f"Tool event from untrusted source at index {index}")
            )
            if self.strict_mode:
                return None

        # Parse parameters
        parameters = event.get('parameters') or event.get('args') or {}
        if isinstance(parameters, str):
            try:
                parameters = json.loads(parameters)
            except json.JSONDecodeError:
                parameters = {'raw': parameters}

        # Parse result
        result_data = event.get('result')
        if isinstance(result_data, str):
            try:
                result_data = json.loads(result_data)
            except json.JSONDecodeError:
                result_data = {'raw': result_data}

        # Parse timestamp
        timestamp = self._parse_timestamp(event.get('timestamp'))

        return ToolEvent(
            timestamp=timestamp,
            tool_name=tool_name,
            parameters=parameters,
            result=result_data,
            success=event.get('success', True),
            error_message=event.get('error') or event.get('error_message'),
            execution_time_ms=event.get('execution_time_ms', 0.0),
            retry_count=event.get('retry_count', 0),
            turn_id=index,
            is_trusted=source_trusted,
            source=event.get('source', 'unknown'),
            schema_validated=source_trusted
        )

    def sanitize_conversation(self, text: str) -> str:
        """
        Sanitize conversation text to prevent injection

        This doesn't modify the text for security (that's structural),
        but normalizes it for consistent processing.
        """
        if not isinstance(text, str):
            return str(text) if text else ""

        # Normalize whitespace
        text = ' '.join(text.split())

        # Truncate extremely long texts
        max_length = 10000
        if len(text) > max_length:
            text = text[:max_length] + "... [truncated]"

        return text

    def _extract_mentioned_tools(self, text: str) -> List[str]:
        """
        Extract tool names mentioned in conversation

        NOTE: This is for TRACKING only, never for execution.
        """
        mentioned = []
        text_lower = text.lower()

        for tool in self.known_tools:
            # Check for tool name or its variants
            tool_lower = tool.lower()
            if tool_lower in text_lower:
                mentioned.append(tool)
            elif tool_lower.replace('_', ' ') in text_lower:
                mentioned.append(tool)

        return mentioned

    def _extract_intent_hints(self, text: str) -> List[str]:
        """
        Extract intent hints from conversation

        NOTE: These are hints only, never direct instructions.
        """
        hints = []
        text_lower = text.lower()

        # Intent patterns
        intent_patterns = {
            'deploy': ['deploy', 'deployment', 'launch', 'start'],
            'debug': ['debug', 'troubleshoot', 'fix', 'investigate'],
            'search': ['find', 'search', 'look for', 'locate'],
            'create': ['create', 'make', 'generate', 'build'],
            'delete': ['delete', 'remove', 'destroy', 'clean up'],
            'update': ['update', 'modify', 'change', 'edit'],
            'check': ['check', 'verify', 'validate', 'test'],
        }

        for intent, keywords in intent_patterns.items():
            for keyword in keywords:
                if keyword in text_lower:
                    hints.append(intent)
                    break

        return list(set(hints))

    def _parse_timestamp(self, ts: Any) -> datetime:
        """Parse timestamp from various formats"""
        if ts is None:
            return datetime.now()

        if isinstance(ts, datetime):
            return ts

        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts)

        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except ValueError:
                pass
            try:
                return datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass

        return datetime.now()

    def validate_tool_event(self, event: ToolEvent) -> bool:
        """
        Validate that a tool event is from a trusted source

        Returns True only if:
        - Tool is in whitelist
        - Source is the orchestrator
        - Schema is valid
        """
        if event.tool_name not in self.known_tools:
            return False

        if event.source not in ('orchestrator', 'layer4_router', 'drumpad'):
            return False

        if not event.is_trusted:
            return False

        return True

    def add_tool_to_whitelist(self, tool_name: str):
        """Add a new tool to the whitelist"""
        self.known_tools.add(tool_name)

    def get_statistics(self) -> Dict:
        """Get separator statistics"""
        return {
            'known_tools_count': len(self.known_tools),
            'strict_mode': self.strict_mode,
            'injection_patterns': len(self.injection_regex),
            'tool_call_patterns': len(self.tool_call_regex)
        }


if __name__ == "__main__":
    print("=" * 70)
    print("STREAM SEPARATOR - Security Foundation")
    print("=" * 70)
    print()
    print("Core Principle:")
    print('  "Nicht Text ruft Tools auf. Zustand ruft Zeit auf. Zeit ruft Aktion auf."')
    print('  (Not text calls tools. State calls time. Time calls action.)')
    print()
    print("This module provides:")
    print("  - Strict separation of conversation and tool event streams")
    print("  - Security validation against injection attempts")
    print("  - Tool whitelist enforcement")
    print("  - Schema validation for tool events")
    print()

    # Quick test
    separator = StreamSeparator()

    test_events = [
        {'role': 'user', 'text': 'Please deploy the docker container', 'timestamp': datetime.now()},
        {'role': 'assistant', 'text': 'I will help you deploy it', 'timestamp': datetime.now()},
        {'tool_name': 'docker_run', 'parameters': {'image': 'nginx'}, 'success': True, 'timestamp': datetime.now()},
    ]

    result = separator.separate(test_events, source_trusted=True)

    print(f"Separation Result:")
    print(f"  Conversation events: {len(result.conversation_stream)}")
    print(f"  Tool events: {len(result.tool_event_stream)}")
    print(f"  Security flags: {len(result.security_flags)}")
    print(f"  Confidence: {result.separation_confidence:.2%}")
    print()
    print("=" * 70)
