"""
Dialogue Management (V2 Phase 4: P4.58-60)

DialogueManager: Multi-turn conversation state with slot tracking.
ClarificationEngine: Detects ambiguous inputs and generates targeted questions.
ConversationMemory: Long-term conversation history with session summaries.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Conversation Memory (P4.60) ─────────────────────────────────────────

@dataclass
class ConversationTurn:
    """A single turn in a conversation."""
    role: str               # 'user', 'brain', 'system'
    content: str
    channel: str = 'default'  # 'websocket', 'whatsapp', 'voice', etc.
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'role': self.role,
            'content': self.content[:200],
            'channel': self.channel,
            'timestamp': self.timestamp,
            'metadata': self.metadata,
        }


@dataclass
class SessionSummary:
    """Automatic summary of a conversation session."""
    session_id: str
    start_time: float
    end_time: float
    turn_count: int
    topics: List[str]
    summary: str
    channel: str = 'default'
    key_decisions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'session_id': self.session_id,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'turn_count': self.turn_count,
            'topics': self.topics,
            'summary': self.summary[:200],
            'channel': self.channel,
            'key_decisions': self.key_decisions[:5],
        }


class ConversationMemory:
    """
    Long-term conversation history (P4.60).

    Stores:
    - Current session turns (recent history)
    - Session summaries (compressed long-term memory)
    - Cross-channel unified memory stream

    Supports reference to previous conversations:
    "Last week we discussed X" → retrieves relevant session summary.
    """

    def __init__(
        self,
        max_turns_per_session: int = 100,
        max_sessions: int = 50,
        memory_manager: Optional[Any] = None,
    ):
        self.max_turns_per_session = max_turns_per_session
        self.max_sessions = max_sessions
        self._memory_manager = memory_manager

        self._current_turns: Deque[ConversationTurn] = deque(maxlen=max_turns_per_session)
        self._session_summaries: List[SessionSummary] = []
        self._session_counter = 0
        self._current_session_start = time.time()

    def add_turn(self, role: str, content: str, channel: str = 'default',
                 **metadata) -> ConversationTurn:
        """Record a conversation turn."""
        turn = ConversationTurn(
            role=role,
            content=content,
            channel=channel,
            metadata=metadata,
        )
        self._current_turns.append(turn)
        return turn

    def get_recent_turns(self, count: int = 10) -> List[ConversationTurn]:
        """Get the most recent turns."""
        turns = list(self._current_turns)
        return turns[-count:] if turns else []

    def get_context_for_llm(self, max_turns: int = 5) -> str:
        """
        Build conversation context string for LLM prompt injection.

        Returns recent turns formatted as:
        [User]: message
        [Brain]: response
        """
        recent = self.get_recent_turns(max_turns)
        if not recent:
            return ""

        lines = []
        for turn in recent:
            role_label = turn.role.capitalize()
            lines.append(f"[{role_label}]: {turn.content[:200]}")
        return '\n'.join(lines)

    def end_session(self, topics: Optional[List[str]] = None,
                    summary: Optional[str] = None) -> SessionSummary:
        """
        End the current session and create a summary.

        If no summary provided, auto-generates from recent turns.
        """
        self._session_counter += 1
        turns = list(self._current_turns)

        # Auto-generate topics from turn content
        if not topics:
            topics = self._extract_topics(turns)

        # Auto-generate summary
        if not summary:
            summary = self._auto_summarize(turns)

        # Extract key decisions
        decisions = self._extract_decisions(turns)

        # Determine channel
        channels = set(t.channel for t in turns) if turns else {'default'}
        primary_channel = max(channels, key=lambda c: sum(1 for t in turns if t.channel == c)) if channels else 'default'

        session = SessionSummary(
            session_id=f"session_{self._session_counter}",
            start_time=self._current_session_start,
            end_time=time.time(),
            turn_count=len(turns),
            topics=topics,
            summary=summary,
            channel=primary_channel,
            key_decisions=decisions,
        )

        self._session_summaries.append(session)
        if len(self._session_summaries) > self.max_sessions:
            self._session_summaries = self._session_summaries[-self.max_sessions:]

        # Reset for new session
        self._current_turns.clear()
        self._current_session_start = time.time()

        return session

    def search_history(self, query: str, max_results: int = 5) -> List[SessionSummary]:
        """
        Search past sessions for relevant conversations.

        Simple keyword matching on topics and summaries.
        """
        query_lower = query.lower()
        scored: List[Tuple[float, SessionSummary]] = []

        for session in self._session_summaries:
            score = 0.0
            # Check topics
            for topic in session.topics:
                if query_lower in topic.lower():
                    score += 1.0

            # Check summary
            if query_lower in session.summary.lower():
                score += 0.5

            # Check decisions
            for decision in session.key_decisions:
                if query_lower in decision.lower():
                    score += 0.3

            if score > 0:
                scored.append((score, session))

        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored[:max_results]]

    def _extract_topics(self, turns: List[ConversationTurn]) -> List[str]:
        """Extract topics from conversation turns (simple heuristic)."""
        topics = set()
        for turn in turns:
            if turn.role == 'user':
                # Extract first 3 significant words
                words = turn.content.split()
                significant = [
                    w.strip('.,!?:;').lower() for w in words
                    if len(w) > 3 and w.lower() not in {
                        'this', 'that', 'what', 'when', 'where', 'which',
                        'there', 'here', 'with', 'from', 'about', 'have',
                        'please', 'could', 'would', 'should', 'will', 'just',
                    }
                ]
                if significant:
                    topics.add(significant[0])
        return list(topics)[:5]

    def _auto_summarize(self, turns: List[ConversationTurn]) -> str:
        """Auto-generate a brief session summary."""
        if not turns:
            return "Empty session."

        user_turns = [t for t in turns if t.role == 'user']
        brain_turns = [t for t in turns if t.role == 'brain']

        parts = [f"{len(turns)} turns ({len(user_turns)} user, {len(brain_turns)} brain)."]

        if user_turns:
            first_msg = user_turns[0].content[:80]
            parts.append(f"Started with: '{first_msg}'")

        if len(user_turns) > 1:
            last_msg = user_turns[-1].content[:80]
            parts.append(f"Ended with: '{last_msg}'")

        return ' '.join(parts)

    def _extract_decisions(self, turns: List[ConversationTurn]) -> List[str]:
        """Extract key decisions from brain turns."""
        decisions = []
        for turn in turns:
            if turn.role == 'brain':
                content_lower = turn.content.lower()
                if any(kw in content_lower for kw in ('decided', 'chose', 'will', "i'll", 'going to', 'committed')):
                    decisions.append(turn.content[:100])
        return decisions[:5]

    def get_state(self) -> Dict[str, Any]:
        return {
            'current_session_turns': len(self._current_turns),
            'total_sessions': len(self._session_summaries),
            'session_counter': self._session_counter,
            'recent_topics': self._extract_topics(list(self._current_turns)),
        }


# ─── Clarification Engine (P4.59) ────────────────────────────────────────

@dataclass
class ClarificationRequest:
    """A request for user clarification."""
    question: str
    reason: str           # Why clarification is needed
    slot_name: str        # Which slot needs filling
    options: Optional[List[str]] = None  # Suggested options
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'question': self.question,
            'reason': self.reason,
            'slot_name': self.slot_name,
            'options': self.options,
            'timestamp': self.timestamp,
        }


class ClarificationEngine:
    """
    Detects ambiguous or incomplete inputs and generates clarifying questions (P4.59).

    Patterns detected:
    - Missing target: "Deploy that" → Which project?
    - Missing environment: "Run tests" → Which test suite? Which environment?
    - Ambiguous reference: "Fix it" → Fix what specifically?
    - Conflicting instructions: "Deploy but also rollback" → Which one?

    Tracks open clarification points.
    """

    # Ambiguity patterns: (pattern_keywords, slot_needed, question_template)
    AMBIGUITY_RULES = [
        # Pronoun references without clear antecedent
        {
            'triggers': ['that', 'it', 'this', 'those', 'them'],
            'slot': 'target',
            'question': "What specifically are you referring to?",
            'reason': 'ambiguous_reference',
        },
        # Deploy without target
        {
            'triggers': ['deploy'],
            'requires_context': ['project', 'service', 'app', 'application', 'branch'],
            'slot': 'deploy_target',
            'question': "Which project or service should I deploy?",
            'reason': 'missing_deploy_target',
        },
        # Run without specific target
        {
            'triggers': ['run'],
            'requires_context': ['test', 'script', 'command', 'task', 'job'],
            'slot': 'run_target',
            'question': "What should I run? (tests, a specific script, etc.)",
            'reason': 'missing_run_target',
        },
        # Fix without specific issue
        {
            'triggers': ['fix', 'repair', 'resolve'],
            'requires_context': ['bug', 'issue', 'error', 'problem', 'crash'],
            'slot': 'fix_target',
            'question': "What issue should I fix? Can you describe the problem?",
            'reason': 'missing_fix_target',
        },
    ]

    def __init__(self, max_open_clarifications: int = 5):
        self.max_open_clarifications = max_open_clarifications
        self._open_clarifications: List[ClarificationRequest] = []
        self._total_requests = 0
        self._total_resolved = 0

    def check_input(
        self,
        user_input: str,
        conversation_context: Optional[List[ConversationTurn]] = None,
        filled_slots: Optional[Dict[str, Any]] = None,
    ) -> List[ClarificationRequest]:
        """
        Check user input for ambiguities that need clarification.

        Returns list of ClarificationRequests (empty if input is clear).
        """
        requests = []
        words = user_input.lower().split()
        filled = filled_slots or {}

        for rule in self.AMBIGUITY_RULES:
            # Check if any trigger word is present
            triggers = rule.get('triggers', [])
            has_trigger = any(t in words for t in triggers)
            if not has_trigger:
                continue

            slot = rule['slot']

            # If slot is already filled, skip
            if slot in filled:
                continue

            # Check if required context words are present
            requires = rule.get('requires_context')
            if requires:
                has_context = any(c in words for c in requires)
                if has_context:
                    continue  # Context word present, no clarification needed

            # Check conversation context for reference resolution
            if conversation_context and rule.get('reason') == 'ambiguous_reference':
                # If recent context has a clear referent, skip
                recent = conversation_context[-3:] if conversation_context else []
                context_text = ' '.join(t.content.lower() for t in recent)
                # Simple heuristic: if a noun was recently mentioned, the pronoun may be clear
                if any(c in context_text for c in ['project', 'service', 'task', 'build', 'test', 'deploy']):
                    continue

            # Only flag very short/ambiguous inputs (< 5 words with a trigger)
            if len(words) > 8:
                continue

            request = ClarificationRequest(
                question=rule['question'],
                reason=rule['reason'],
                slot_name=slot,
            )
            requests.append(request)

        # Track open clarifications
        for req in requests:
            self._total_requests += 1
            self._open_clarifications.append(req)
            if len(self._open_clarifications) > self.max_open_clarifications:
                self._open_clarifications = self._open_clarifications[-self.max_open_clarifications:]

        return requests

    def resolve_clarification(self, slot_name: str, value: str) -> bool:
        """Mark a clarification as resolved."""
        before = len(self._open_clarifications)
        self._open_clarifications = [
            c for c in self._open_clarifications if c.slot_name != slot_name
        ]
        resolved = len(self._open_clarifications) < before
        if resolved:
            self._total_resolved += 1
        return resolved

    def get_open_clarifications(self) -> List[ClarificationRequest]:
        """Get currently open clarification requests."""
        return list(self._open_clarifications)

    def get_state(self) -> Dict[str, Any]:
        return {
            'open_count': len(self._open_clarifications),
            'total_requests': self._total_requests,
            'total_resolved': self._total_resolved,
            'open_slots': [c.slot_name for c in self._open_clarifications],
        }


# ─── Dialogue Manager (P4.58) ────────────────────────────────────────────

class DialogueState(Enum):
    """Current state of the dialogue."""
    IDLE = 'idle'
    AWAITING_INPUT = 'awaiting_input'
    PROCESSING = 'processing'
    AWAITING_CLARIFICATION = 'awaiting_clarification'
    RESPONDING = 'responding'


@dataclass
class DialogueSlots:
    """Tracked dialogue slots for context."""
    current_topic: Optional[str] = None
    user_intent: Optional[str] = None
    open_questions: List[str] = field(default_factory=list)
    context_stack: List[str] = field(default_factory=list)
    commitments: List[str] = field(default_factory=list)
    filled: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'current_topic': self.current_topic,
            'user_intent': self.user_intent,
            'open_questions': self.open_questions[:5],
            'context_stack': self.context_stack[-5:],
            'commitments': self.commitments[:10],
            'filled': dict(list(self.filled.items())[:10]),
        }


class DialogueManager:
    """
    Multi-turn dialogue management (P4.58).

    Manages:
    - Dialogue state tracking (slots: topic, intent, questions, context)
    - Reference resolution: "Do that again" → last task
    - Commitment tracking: "I'll handle it" → GoalGraph entry
    - Context stack for nested conversations

    Integrates ClarificationEngine and ConversationMemory.
    """

    def __init__(
        self,
        clarification_engine: Optional[ClarificationEngine] = None,
        conversation_memory: Optional[ConversationMemory] = None,
        max_context_depth: int = 10,
    ):
        self.clarification = clarification_engine or ClarificationEngine()
        self.memory = conversation_memory or ConversationMemory()
        self.max_context_depth = max_context_depth

        self._state = DialogueState.IDLE
        self._slots = DialogueSlots()
        self._total_turns = 0

    def process_user_input(
        self,
        user_input: str,
        channel: str = 'default',
    ) -> Dict[str, Any]:
        """
        Process a user input message.

        Returns:
        - needs_clarification: bool
        - clarification_requests: List[Dict] (if needed)
        - resolved_input: str (with references resolved)
        - intent: str (detected intent)
        - slots: Dict (current slot values)
        """
        self._state = DialogueState.PROCESSING
        self._total_turns += 1

        # Record turn
        self.memory.add_turn('user', user_input, channel=channel)

        # Resolve references ("that", "it", etc.)
        resolved = self._resolve_references(user_input)

        # Detect intent
        intent = self._detect_intent(resolved)
        self._slots.user_intent = intent

        # Update topic
        topic = self._extract_topic(resolved)
        if topic:
            if self._slots.current_topic:
                self._slots.context_stack.append(self._slots.current_topic)
                if len(self._slots.context_stack) > self.max_context_depth:
                    self._slots.context_stack = self._slots.context_stack[-self.max_context_depth:]
            self._slots.current_topic = topic

        # Check for ambiguity
        recent_turns = self.memory.get_recent_turns(5)
        clarifications = self.clarification.check_input(
            user_input,
            conversation_context=recent_turns,
            filled_slots=self._slots.filled,
        )

        if clarifications:
            self._state = DialogueState.AWAITING_CLARIFICATION
            return {
                'needs_clarification': True,
                'clarification_requests': [c.to_dict() for c in clarifications],
                'resolved_input': resolved,
                'intent': intent,
                'slots': self._slots.to_dict(),
            }

        self._state = DialogueState.RESPONDING
        return {
            'needs_clarification': False,
            'clarification_requests': [],
            'resolved_input': resolved,
            'intent': intent,
            'slots': self._slots.to_dict(),
        }

    def record_response(self, response: str, channel: str = 'default',
                        commitment: Optional[str] = None):
        """Record the brain's response."""
        self.memory.add_turn('brain', response, channel=channel)

        # Track commitments
        if commitment:
            self._slots.commitments.append(commitment)

        # Auto-detect commitments in response
        response_lower = response.lower()
        for phrase in ("i'll", "i will", "going to", "committed to"):
            if phrase in response_lower:
                idx = response_lower.index(phrase)
                commitment_text = response[idx:idx + 80].strip()
                if commitment_text not in self._slots.commitments:
                    self._slots.commitments.append(commitment_text)
                break

        self._state = DialogueState.IDLE

    def provide_clarification(self, slot_name: str, value: str) -> bool:
        """
        User provides clarification for an open question.

        Returns True if clarification was accepted.
        """
        self._slots.filled[slot_name] = value
        resolved = self.clarification.resolve_clarification(slot_name, value)

        # If no more open clarifications, move to responding
        if not self.clarification.get_open_clarifications():
            self._state = DialogueState.RESPONDING

        return resolved

    def _resolve_references(self, text: str) -> str:
        """
        Resolve anaphoric references ("that", "it", "do it again").

        Uses recent conversation history to find referents.
        """
        text_lower = text.lower().strip()

        # "Do that again" / "repeat that" → last task
        repeat_phrases = ['do that again', 'repeat that', 'again', 'do it again', 'once more']
        for phrase in repeat_phrases:
            if text_lower == phrase or text_lower.startswith(phrase):
                recent = self.memory.get_recent_turns(5)
                last_user = None
                for turn in reversed(recent):
                    if turn.role == 'user' and turn.content.lower().strip() != text_lower:
                        last_user = turn
                        break
                if last_user:
                    return last_user.content

        # "What about X?" → maintains current context
        if text_lower.startswith('what about '):
            new_topic = text[len('what about '):]
            if self._slots.current_topic:
                return f"{new_topic} (context: {self._slots.current_topic})"

        return text

    def _detect_intent(self, text: str) -> str:
        """Simple rule-based intent detection."""
        text_lower = text.lower()

        intent_keywords = {
            'deploy': ['deploy', 'ship', 'release', 'push to prod'],
            'fix': ['fix', 'repair', 'resolve', 'debug'],
            'analyze': ['analyze', 'investigate', 'look into', 'check'],
            'status': ['status', 'how is', 'what\'s happening', 'update'],
            'create': ['create', 'make', 'build', 'generate', 'write'],
            'explain': ['explain', 'why', 'how does', 'what does'],
            'cancel': ['cancel', 'stop', 'abort', 'nevermind'],
        }

        for intent, keywords in intent_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return intent

        return 'general'

    def _extract_topic(self, text: str) -> Optional[str]:
        """Extract the main topic from user input."""
        words = text.split()
        # Simple: use first noun-like word (> 3 chars, not a common word)
        skip = {
            'what', 'when', 'where', 'which', 'this', 'that', 'there', 'here',
            'with', 'from', 'about', 'have', 'please', 'could', 'would', 'should',
            'will', 'just', 'also', 'then', 'been', 'were', 'does', 'done',
            'context', 'again',
        }
        for word in words:
            clean = word.strip('.,!?:;()[]').lower()
            if len(clean) > 3 and clean not in skip:
                return clean
        return None

    def end_session(self) -> Optional[Dict]:
        """End the current dialogue session."""
        summary = self.memory.end_session(
            topics=[self._slots.current_topic] if self._slots.current_topic else [],
        )
        # Reset slots
        self._slots = DialogueSlots()
        self._state = DialogueState.IDLE
        return summary.to_dict() if summary else None

    def get_state(self) -> Dict[str, Any]:
        return {
            'state': self._state.value,
            'total_turns': self._total_turns,
            'slots': self._slots.to_dict(),
            'clarification': self.clarification.get_state(),
            'memory': self.memory.get_state(),
        }

    @classmethod
    def from_yaml(cls, config: Dict) -> 'DialogueManager':
        """Create from YAML config."""
        dm = config.get('dialogue_manager', {})
        mem_cfg = dm.get('conversation_memory', {})
        clar_cfg = dm.get('clarification', {})

        memory = ConversationMemory(
            max_turns_per_session=mem_cfg.get('max_turns_per_session', 100),
            max_sessions=mem_cfg.get('max_sessions', 50),
        )
        clarification = ClarificationEngine(
            max_open_clarifications=clar_cfg.get('max_open_clarifications', 5),
        )
        return cls(
            clarification_engine=clarification,
            conversation_memory=memory,
            max_context_depth=dm.get('max_context_depth', 10),
        )
