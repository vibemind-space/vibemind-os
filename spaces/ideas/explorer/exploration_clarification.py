"""
ExplorationClarificationAgent - Human-in-the-Loop interaction during exploration.

Handles user interaction during idea exploration using VibeMind's existing
clarification pattern (EventServer.broadcast + file-based polling).
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Awaitable
from enum import Enum
from pathlib import Path

from .idea_node import IdeaNode

logger = logging.getLogger(__name__)


class ExplorationMode(Enum):
    """Exploration interaction modes."""
    AUTO = "auto"              # Autonomous exploration, results at end
    INTERACTIVE = "interactive"  # Ask after each discovery
    GUIDED = "guided"          # User steers direction


class QuestionType(Enum):
    """Types of questions the agent can ask."""
    CONNECTION_FOUND = "connection_found"      # Ask about a discovered connection
    DIRECTION_REQUEST = "direction_request"    # Ask which direction to explore
    STAGE_COMPLETE = "stage_complete"          # Ask whether to continue to next stage
    VALIDATION_REQUEST = "validation_request"  # Ask for important decision validation


@dataclass
class ClarificationQuestion:
    """A question to ask the user."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    question_type: QuestionType = QuestionType.CONNECTION_FOUND
    question_text: str = ""
    voice_text: str = ""  # Text optimized for voice synthesis
    options: List[str] = field(default_factory=list)
    node: Optional[IdeaNode] = None
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    timeout: int = 30  # seconds


@dataclass
class ClarificationResponse:
    """User's response to a clarification question."""
    question_id: str
    response_type: str  # 'accept', 'reject', 'explore_deeper', 'direction', 'continue', 'stop'
    selected_option: Optional[str] = None
    custom_text: Optional[str] = None
    responded_at: float = field(default_factory=time.time)


@dataclass
class InteractiveExplorationConfig:
    """Configuration for interactive exploration."""
    mode: ExplorationMode = ExplorationMode.INTERACTIVE
    ask_on_discovery: bool = True           # Ask when connection found
    ask_between_stages: bool = True         # Ask between exploration stages
    min_score_for_question: float = 0.5     # Only ask for good connections
    max_questions_per_stage: int = 3        # Limit questions per stage
    response_timeout: int = 30              # Seconds to wait for response
    use_voice: bool = True                  # Enable voice questions
    use_ui: bool = True                     # Enable UI dialogs
    auto_accept_threshold: float = 0.85     # Auto-accept above this score
    auto_reject_threshold: float = 0.3      # Auto-reject below this score


class ExplorationClarificationAgent:
    """
    Handles human-in-the-loop interaction during idea exploration.

    Uses VibeMind's existing patterns:
    - EventServer.broadcast() for sending questions to UI
    - File-based polling for receiving responses
    - Rachel voice integration for audio questions
    """

    # Clarification file path (same pattern as VibeMind's clarification system)
    CLARIFICATION_DIR = Path(os.environ.get(
        "VIBEMIND_CLARIFICATION_DIR",
        Path.home() / ".vibemind" / "clarification"
    ))

    def __init__(
        self,
        config: Optional[InteractiveExplorationConfig] = None,
        event_broadcaster: Optional[Callable[[str, Dict], Awaitable[None]]] = None,
        voice_synthesizer: Optional[Callable[[str], Awaitable[None]]] = None,
    ):
        """
        Initialize the clarification agent.

        Args:
            config: Interactive exploration configuration
            event_broadcaster: Function to broadcast events (typically EventServer.broadcast)
            voice_synthesizer: Function to synthesize voice (typically Rachel TTS)
        """
        self.config = config or InteractiveExplorationConfig()
        self._event_broadcaster = event_broadcaster
        self._voice_synthesizer = voice_synthesizer

        # State
        self._pending_questions: Dict[str, ClarificationQuestion] = {}
        self._responses: Dict[str, ClarificationResponse] = {}
        self._questions_this_stage: int = 0

        # Ensure clarification directory exists
        self.CLARIFICATION_DIR.mkdir(parents=True, exist_ok=True)

    def set_event_broadcaster(self, broadcaster: Callable[[str, Dict], Awaitable[None]]):
        """Set the event broadcaster (late binding)."""
        self._event_broadcaster = broadcaster

    def set_voice_synthesizer(self, synthesizer: Callable[[str], Awaitable[None]]):
        """Set the voice synthesizer (late binding)."""
        self._voice_synthesizer = synthesizer

    def reset_stage_counter(self):
        """Reset the questions-per-stage counter."""
        self._questions_this_stage = 0

    # ============================================================
    # Question Generation
    # ============================================================

    def create_connection_question(self, node: IdeaNode) -> ClarificationQuestion:
        """Create a question about a discovered connection."""
        question_text = (
            f"Ich habe eine Verbindung gefunden: '{node.source_bubble_title}' "
            f"und '{node.target_bubble_title}' sind durch '{node.edge_label}' "
            f"verbunden. {node.reasoning} Soll ich diese behalten?"
        )

        # Shorter version for voice
        voice_text = (
            f"Ich habe eine Verbindung gefunden: {node.source_bubble_title} "
            f"und {node.target_bubble_title}. {node.edge_label}. "
            f"Soll ich diese behalten?"
        )

        return ClarificationQuestion(
            question_type=QuestionType.CONNECTION_FOUND,
            question_text=question_text,
            voice_text=voice_text,
            options=["Akzeptieren", "Ablehnen", "Tiefer erkunden"],
            node=node,
            metadata={
                "source_bubble_id": node.source_bubble_id,
                "target_bubble_id": node.target_bubble_id,
                "combined_score": node.combined_score,
            }
        )

    def create_direction_question(
        self,
        candidates: List[Dict[str, Any]],
        context: str = ""
    ) -> ClarificationQuestion:
        """Create a question about exploration direction."""
        logger.debug("create_direction_question: candidates=%s, context=%s",
                     len(candidates), context[:50] if context else "")
        options = [c.get("title", "Unbekannt") for c in candidates[:4]]

        question_text = "Welchen Bereich soll ich als nächstes erkunden?"
        if context:
            question_text = f"{context} {question_text}"

        voice_text = "Welchen Bereich soll ich als nächstes erkunden? " + \
                     " oder ".join(options[:3])

        return ClarificationQuestion(
            question_type=QuestionType.DIRECTION_REQUEST,
            question_text=question_text,
            voice_text=voice_text,
            options=options,
            candidates=candidates[:4],
        )

    def create_stage_complete_question(
        self,
        stage_name: str,
        nodes_found: int,
        best_score: float,
    ) -> ClarificationQuestion:
        """Create a question about continuing to next stage."""
        question_text = (
            f"Stage '{stage_name}' ist abgeschlossen. "
            f"Ich habe {nodes_found} Verbindungen gefunden. "
            f"Beste Bewertung: {best_score:.0%}. "
            f"Soll ich weitermachen?"
        )

        voice_text = (
            f"Stage {stage_name} fertig. {nodes_found} Verbindungen gefunden. "
            f"Weitermachen?"
        )

        return ClarificationQuestion(
            question_type=QuestionType.STAGE_COMPLETE,
            question_text=question_text,
            voice_text=voice_text,
            options=["Weitermachen", "Hier stoppen", "Ergebnisse zeigen"],
            metadata={
                "stage": stage_name,
                "nodes_found": nodes_found,
                "best_score": best_score,
            }
        )

    def create_validation_question(
        self,
        action: str,
        context: str,
    ) -> ClarificationQuestion:
        """Create a validation question for important decisions."""
        question_text = f"{context} Soll ich {action}?"

        return ClarificationQuestion(
            question_type=QuestionType.VALIDATION_REQUEST,
            question_text=question_text,
            voice_text=question_text,
            options=["Ja", "Nein", "Mehr Infos"],
            metadata={"action": action, "context": context}
        )

    # ============================================================
    # Question Asking
    # ============================================================

    async def ask_about_connection(self, node: IdeaNode) -> str:
        """
        Ask user about a discovered connection.

        Returns: 'accept', 'reject', 'explore_deeper', or 'timeout'
        """
        # Check if we should ask based on configuration
        if not self._should_ask_for_node(node):
            return self._auto_decide_for_node(node)

        question = self.create_connection_question(node)
        response = await self._ask_question(question)

        if not response:
            return "timeout"

        # Map response to action
        option = response.selected_option or ""
        if "akzeptieren" in option.lower() or "ja" in option.lower():
            return "accept"
        elif "ablehnen" in option.lower() or "nein" in option.lower():
            return "reject"
        elif "tiefer" in option.lower() or "erkunden" in option.lower():
            return "explore_deeper"
        elif response.custom_text:
            # Handle free-form response
            text = response.custom_text.lower()
            if any(w in text for w in ["ja", "gut", "ok", "behalten"]):
                return "accept"
            elif any(w in text for w in ["nein", "nicht", "schlecht"]):
                return "reject"
            else:
                return "accept"  # Default to accept for unclear responses
        else:
            return "timeout"

    async def ask_for_direction(
        self,
        candidates: List[Dict[str, Any]],
        context: str = ""
    ) -> Optional[str]:
        """
        Ask user which direction to explore next.

        Returns: Selected bubble ID, or None if timeout/cancel
        """
        logger.debug("ask_for_direction: candidates=%s, context=%s",
                     len(candidates), context[:50] if context else "")
        if not candidates:
            return None

        question = self.create_direction_question(candidates, context)
        response = await self._ask_question(question)

        if not response:
            return None

        # Find matching candidate
        selected = response.selected_option or response.custom_text
        if selected:
            for c in candidates:
                if c.get("title", "").lower() == selected.lower():
                    return c.get("id")
            # Partial match
            for c in candidates:
                if selected.lower() in c.get("title", "").lower():
                    return c.get("id")

        return None

    async def ask_stage_complete(
        self,
        stage_name: str,
        nodes_found: int,
        best_score: float,
    ) -> str:
        """
        Ask user about continuing after stage completion.

        Returns: 'continue', 'stop', 'show_results'
        """
        if not self.config.ask_between_stages:
            return "continue"

        question = self.create_stage_complete_question(stage_name, nodes_found, best_score)
        response = await self._ask_question(question)

        if not response:
            return "continue"  # Default to continue on timeout

        option = (response.selected_option or "").lower()
        if "weitermachen" in option or "continue" in option:
            return "continue"
        elif "stoppen" in option or "stop" in option:
            return "stop"
        elif "ergebnisse" in option or "zeigen" in option:
            return "show_results"
        else:
            return "continue"

    async def ask_validation(self, action: str, context: str) -> bool:
        """
        Ask for validation on an important action.

        Returns: True if confirmed, False otherwise
        """
        question = self.create_validation_question(action, context)
        response = await self._ask_question(question)

        if not response:
            return False

        option = (response.selected_option or "").lower()
        return "ja" in option or "yes" in option

    # ============================================================
    # Core Question/Response Flow
    # ============================================================

    async def _ask_question(self, question: ClarificationQuestion) -> Optional[ClarificationResponse]:
        """
        Ask a question and wait for response.

        Uses both voice and UI based on configuration.
        """
        self._pending_questions[question.id] = question
        self._questions_this_stage += 1

        try:
            # Broadcast to UI
            if self.config.use_ui:
                await self._broadcast_question(question)

            # Synthesize voice
            if self.config.use_voice:
                await self._synthesize_voice(question)

            # Write question file for polling
            self._write_question_file(question)

            # Wait for response
            response = await self._wait_for_response(
                question.id,
                timeout=question.timeout or self.config.response_timeout
            )

            return response

        finally:
            # Cleanup
            self._pending_questions.pop(question.id, None)
            self._cleanup_question_file(question.id)

    async def _broadcast_question(self, question: ClarificationQuestion):
        """Broadcast question to Electron UI."""
        if not self._event_broadcaster:
            logger.warning("No event broadcaster configured")
            return

        event_type = f"exploration.{question.question_type.value}"

        payload = {
            "question_id": question.id,
            "question_text": question.question_text,
            "options": question.options,
            "question_type": question.question_type.value,
            "timeout": question.timeout,
        }

        # Add node visualization data if available
        if question.node:
            payload["node"] = question.node.to_visualization_dict()

        # Add candidates for direction questions
        if question.candidates:
            payload["candidates"] = [
                {"id": c.get("id"), "title": c.get("title")}
                for c in question.candidates
            ]

        try:
            await self._event_broadcaster(event_type, payload)
        except Exception as e:
            logger.error(f"Failed to broadcast question: {e}")

    async def _synthesize_voice(self, question: ClarificationQuestion):
        """Synthesize voice question using Rachel."""
        if not self._voice_synthesizer:
            logger.debug("No voice synthesizer configured")
            return

        try:
            await self._voice_synthesizer(question.voice_text)
        except Exception as e:
            logger.error(f"Failed to synthesize voice: {e}")

    def _write_question_file(self, question: ClarificationQuestion):
        """Write question to file for external response handling."""
        question_file = self.CLARIFICATION_DIR / f"question_{question.id}.json"

        data = {
            "id": question.id,
            "type": question.question_type.value,
            "question": question.question_text,
            "options": question.options,
            "created_at": question.created_at,
            "timeout": question.timeout,
            "awaiting_response": True,
        }

        try:
            with open(question_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to write question file: {e}")

    def _cleanup_question_file(self, question_id: str):
        """Remove question file after response or timeout."""
        question_file = self.CLARIFICATION_DIR / f"question_{question_id}.json"
        response_file = self.CLARIFICATION_DIR / f"response_{question_id}.json"

        for f in [question_file, response_file]:
            try:
                if f.exists():
                    f.unlink()
            except Exception as e:
                logger.warning(f"Failed to cleanup file {f}: {e}")

    async def _wait_for_response(
        self,
        question_id: str,
        timeout: int
    ) -> Optional[ClarificationResponse]:
        """
        Wait for user response via file polling.

        The Electron frontend or voice handler writes to response_{question_id}.json
        """
        response_file = self.CLARIFICATION_DIR / f"response_{question_id}.json"
        start_time = time.time()
        poll_interval = 0.5  # seconds

        while time.time() - start_time < timeout:
            if response_file.exists():
                try:
                    with open(response_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    response = ClarificationResponse(
                        question_id=question_id,
                        response_type=data.get("response_type", "unknown"),
                        selected_option=data.get("selected_option"),
                        custom_text=data.get("custom_text"),
                    )

                    self._responses[question_id] = response
                    logger.info(f"Received response for {question_id}: {response.response_type}")
                    return response

                except Exception as e:
                    logger.error(f"Failed to read response file: {e}")

            await asyncio.sleep(poll_interval)

        logger.info(f"Timeout waiting for response to {question_id}")
        return None

    # ============================================================
    # Decision Logic
    # ============================================================

    def _should_ask_for_node(self, node: IdeaNode) -> bool:
        """Determine if we should ask about this node."""
        # Check mode
        if self.config.mode == ExplorationMode.AUTO:
            return False

        # Check questions limit
        if self._questions_this_stage >= self.config.max_questions_per_stage:
            return False

        # Check score thresholds for auto-decision
        if node.combined_score >= self.config.auto_accept_threshold:
            return False  # Auto-accept
        if node.combined_score < self.config.auto_reject_threshold:
            return False  # Auto-reject

        # Check minimum score for asking
        if node.combined_score < self.config.min_score_for_question:
            return False

        return self.config.ask_on_discovery

    def _auto_decide_for_node(self, node: IdeaNode) -> str:
        """Make automatic decision for a node."""
        if node.combined_score >= self.config.auto_accept_threshold:
            logger.debug(f"Auto-accepting node with score {node.combined_score:.2f}")
            return "accept"
        elif node.combined_score < self.config.auto_reject_threshold:
            logger.debug(f"Auto-rejecting node with score {node.combined_score:.2f}")
            return "reject"
        else:
            # Middle ground - accept but don't explore deeper
            return "accept"

    # ============================================================
    # External Response Handling
    # ============================================================

    def handle_external_response(
        self,
        question_id: str,
        response_type: str,
        selected_option: Optional[str] = None,
        custom_text: Optional[str] = None,
    ) -> bool:
        """
        Handle response from external source (Electron UI or voice).

        Writes response file that the polling loop will pick up.
        """
        response_file = self.CLARIFICATION_DIR / f"response_{question_id}.json"

        data = {
            "question_id": question_id,
            "response_type": response_type,
            "selected_option": selected_option,
            "custom_text": custom_text,
            "responded_at": time.time(),
        }

        try:
            with open(response_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to write response file: {e}")
            return False

    def get_pending_questions(self) -> List[ClarificationQuestion]:
        """Get list of pending questions."""
        return list(self._pending_questions.values())

    def has_pending_questions(self) -> bool:
        """Check if there are pending questions."""
        return len(self._pending_questions) > 0


# ============================================================
# Voice Response Patterns
# ============================================================

VOICE_RESPONSE_PATTERNS = {
    # Acceptance patterns (German)
    "accept": [
        "ja", "gut", "ok", "okay", "behalten", "akzeptieren", "speichern",
        "klingt gut", "nehmen", "passt", "stimmt", "richtig", "genau",
        "das ist gut", "perfekt", "super", "ja bitte",
    ],

    # Rejection patterns (German)
    "reject": [
        "nein", "nicht", "schlecht", "ablehnen", "weg", "verwerfen",
        "passt nicht", "falsch", "stimmt nicht", "quatsch", "unsinn",
        "das ist nichts", "lieber nicht", "nee", "ne",
    ],

    # Explore deeper patterns
    "explore_deeper": [
        "tiefer", "mehr", "weiter erkunden", "genauer", "detail",
        "mehr davon", "interessant", "erforsche das", "geh tiefer",
    ],

    # Continue patterns
    "continue": [
        "weitermachen", "weiter", "fortfahren", "nächste", "mehr suchen",
        "such weiter", "mach weiter",
    ],

    # Stop patterns
    "stop": [
        "stopp", "stop", "halt", "aufhören", "genug", "reicht",
        "beenden", "fertig", "schluss",
    ],
}


def classify_voice_response(text: str) -> Optional[str]:
    """
    Classify a voice response text into a response type.

    Returns: 'accept', 'reject', 'explore_deeper', 'continue', 'stop', or None
    """
    text_lower = text.lower().strip()

    # Check each pattern category
    for response_type, patterns in VOICE_RESPONSE_PATTERNS.items():
        for pattern in patterns:
            if pattern in text_lower:
                return response_type

    return None


__all__ = [
    "ExplorationClarificationAgent",
    "ExplorationMode",
    "QuestionType",
    "ClarificationQuestion",
    "ClarificationResponse",
    "InteractiveExplorationConfig",
    "classify_voice_response",
    "VOICE_RESPONSE_PATTERNS",
]
