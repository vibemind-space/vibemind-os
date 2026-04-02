"""
Rachel - Voice Interface for VibeMind

Rachel is the PURE VOICE INTERFACE - she speaks with the user,
understands their intent, and sends it to the orchestrator.

She does NOT execute tools directly - that's done by backend agents.
This keeps her responsive and focused on conversation.

Architecture:
- Rachel (voice) → Orchestrator (classification) → Backend Agents (tool execution)
- Status events flow back through StatusListener → Rachel TTS

MIGRATED FROM: swarm/user_agents/rachel.py
"""

import logging
from typing import List, Callable, Any, Optional

# NOTE: These imports will be updated as core migration progresses
from swarm.navigation import SpaceType
from swarm.event_buffer import InputEvent
from swarm.user_agents.base import (
    BaseUserAgent,
    UserAgentConfig,
    CLARIFICATION_PHRASES_DE,
)

# Context sources for Rachel's awareness
from swarm.orchestrator.system_context_store import get_system_context_store
from swarm.executive.conversation_memory import ConversationMemory
from swarm.orchestrator.question_queue import get_question_queue

logger = logging.getLogger(__name__)


# Rachel's voice-only system prompt
RACHEL_VOICE_PROMPT = """Du bist Rachel - die persoenliche VibeMind Sprachassistentin.

## Deine Rolle

Du bist die Stimme von VibeMind. Du sprichst mit dem User, verstehst was er moechte,
und sendest seine Anfragen an das System. Ergebnisse kommen ASYNCHRON zurueck —
du sagst kurz Bescheid dass du dich kuemmerst, und wenn das Ergebnis eintrifft,
integrierst du es natuerlich ins Gespraech.

## Deine Tools

1. **send_intent** — Sende Anfragen an VibeMind. Laeuft async: du bekommst das
   Ergebnis automatisch zurueck wenn es fertig ist.
2. **check_results** — Pruefe ob neue Ergebnisse vorliegen. Nutze das wenn der User
   fragt "Gibt es Neuigkeiten?" oder wenn du laenger keine Rueckmeldung hattest.

## VibeMind Spaces

VibeMind hat folgende SPACES (Hauptbereiche):

1. **Ideas Space** — Bubbles und Ideen verwalten (voll orchestrierbar)
2. **Desktop Space** — Desktop-Automatisierung (Apps oeffnen, klicken, tippen)
3. **Coding Space** — Code-Generierung und Projekte
4. **Rowboat Space** — Projektplanung und Workflows
5. **Research Space** — Webrecherche und Wissenssuche
6. **Schedule Space** — Termine und geplante Aufgaben

Du bist die einzige Stimme fuer alle Spaces. Alle Anfragen laufen ueber dich.

### Ideas Space Details
- **Bubbles** = Themen-Container (z.B. Marketing, Finanzen, Urlaub)
- **Ideen** = Notizen/Gedanken innerhalb einer Bubble

## WICHTIG: Terminologie

- Sag "Bubble" fuer Themen-Container (Marketing, Finanzen)
- Sag "Space" NUR fuer die Hauptbereiche (Ideas/Desktop/Coding/...)
- Sag "Idee" fuer einzelne Notizen innerhalb einer Bubble

## Async Verhalten

1. **Warte bis der User fertig ist** — Lass den User ausreden!
2. **Sende EXAKT was der User sagt** — Gib die Anfrage WOERTLICH weiter
3. **Kurze Bestaetigung** — "Mach ich!" / "Ich schau mal..." / "Moment..."
4. **Weiter im Gespraech** — Du kannst weiterreden waehrend das System arbeitet
5. **Ergebnis natuerlich einbauen** — Wenn das Ergebnis kommt:
   - Erfolg: "So, deine Bubble Marketing ist erstellt!"
   - Fehler: "Hmm, das hat leider nicht geklappt — die Bubble gibt es schon."
   - Info: "Du hast uebrigens drei Bubbles: Marketing, Finanzen und Test."

## WICHTIG: send_intent Genauigkeit

- Sende IMMER den KOMPLETTEN Wunsch des Users, nicht nur Teile davon
- Erfinde KEINE Details dazu — nur was der User gesagt hat
- Bei Zahlen (z.B. "erstelle 15 Ideen") — die Zahl MUSS im user_request enthalten sein
- Warte bis der User FERTIG gesprochen hat bevor du send_intent aufrufst

## Beispiele (async)

User: "Welche Bubbles hab ich?"
Du: Ich schau mal nach... (rufe send_intent auf → "Ich kuemmere mich darum")
[... kurze Pause, Ergebnis kommt automatisch ...]
Du: Du hast drei Bubbles: Projekt Alpha, Ideen, und Notizen.

User: "Erstelle Bubble Marketing und notiere drei Ideen darin"
Du: Mach ich! (rufe send_intent auf → "Ich kuemmere mich darum")
[... Ergebnis kommt ...]
Du: Alles klar — Bubble Marketing ist da, und ich hab drei Ideen drin notiert.

User: "Oeffne Chrome"
Du: Moment... (rufe send_intent auf)
[... Ergebnis kommt ...]
Du: Chrome ist offen!

User: "Gibt es Neuigkeiten?"
Du: (rufe check_results auf)
→ Entweder: "Ja! Deine Code-Generierung ist fertig."
→ Oder: "Nein, noch nichts Neues. Ich sag Bescheid sobald was kommt."

## Sprache & Persoenlichkeit

- IMMER in der Sprache antworten die der User benutzt
- Wenn der User Deutsch spricht → Deutsch antworten
- Wenn der User Englisch spricht → Englisch antworten
- Sprache NIE wechseln mitten im Gespraech
- Sei freundlich, locker und natuerlich — wie eine gute Kollegin
- Halte Antworten kurz und praegnant
- Niemals JSON oder technische Details ausgeben
- Bei unklaren Anfragen: Rueckfrage stellen
- IMMER "Bubble" sagen fuer Themen-Container, NICHT "Space"!
"""


class RachelAgent(BaseUserAgent):
    """
    Rachel - Voice Interface for VibeMind.

    Rachel is the pure voice interface that:
    - Speaks with the user
    - Understands their intent
    - Sends intent to orchestrator via send_intent()
    - Receives status updates and speaks them back
    - Checks NotificationQueue for pending task results

    She does NOT execute tools directly.
    """

    def __init__(
        self,
        model_client: Any = None,
        orchestrator: Any = None,
        notification_queue: Any = None,
        tts_callback: Optional[Callable] = None
    ):
        config = UserAgentConfig(
            name="rachel",
            display_name="Rachel",
            space_type=SpaceType.IDEAS,
            voice_id="Rachel",
            greeting="Hallo! Ich bin Rachel, deine VibeMind Assistentin. Was soll ich fuer dich tun?",
            clarification_phrases=CLARIFICATION_PHRASES_DE,
        )
        super().__init__(config, model_client, tts_callback)

        self._orchestrator = orchestrator
        self._notification_queue = notification_queue
        self._context_store = None
        self._conversation_memory = None
        logger.info("RachelAgent (Voice Interface) initialized")

    @property
    def orchestrator(self):
        """Lazy-load orchestrator."""
        if self._orchestrator is None:
            from swarm.orchestrator import get_orchestrator
            self._orchestrator = get_orchestrator()
        return self._orchestrator

    @property
    def notification_queue(self):
        """Lazy-load notification queue."""
        if self._notification_queue is None:
            from swarm.orchestrator import get_notification_queue
            self._notification_queue = get_notification_queue()
        return self._notification_queue

    @property
    def context_store(self):
        """Lazy-load SystemContextStore for recent actions (10-min window)."""
        if self._context_store is None:
            self._context_store = get_system_context_store()
        return self._context_store

    @property
    def conversation_memory(self):
        """Lazy-load ConversationMemory for long-term history."""
        if self._conversation_memory is None:
            try:
                from data.database import get_database
                self._conversation_memory = ConversationMemory(get_database())
            except Exception as e:
                logger.warning(f"Could not initialize ConversationMemory: {e}")
                self._conversation_memory = None
        return self._conversation_memory

    @property
    def question_queue(self):
        """Lazy-load QuestionQueue for backend questions."""
        if not hasattr(self, '_question_queue') or self._question_queue is None:
            self._question_queue = get_question_queue()
        return self._question_queue

    def set_orchestrator(self, orchestrator):
        """Set the orchestrator instance."""
        self._orchestrator = orchestrator

    def set_notification_queue(self, queue):
        """Set the notification queue instance."""
        self._notification_queue = queue

    def get_system_prompt(self) -> str:
        return RACHEL_VOICE_PROMPT

    def get_tools(self) -> List[Callable]:
        """
        Get Rachel's tools - only send_intent().

        Rachel is voice-only and sends user intent to the orchestrator.
        Backend agents execute the actual tools.
        """
        return [self.send_intent]

    def send_intent(self, user_request: str) -> str:
        """
        Send user intent to the orchestrator for processing.

        This is Rachel's ONLY tool. It sends the user's natural language
        request to the orchestrator, which classifies it and seeds events
        for backend agents to execute.

        Args:
            user_request: What the user wants to do (natural language)

        Returns:
            Confirmation message with response hint
        """
        try:
            result = self.orchestrator.process_intent_sync(user_request)

            if result.is_conversational:
                # Conversational - no backend action needed
                return result.response_hint

            if result.error:
                return f"Es gab ein Problem: {result.error}"

            # Return the response hint for voice output
            logger.info(f"Rachel sent intent: {result.event_type} (job={result.job_id})")
            return result.response_hint

        except Exception as e:
            logger.error(f"Rachel send_intent error: {e}")
            return "Es gab ein Problem bei der Verarbeitung. Bitte versuch es nochmal."

    async def send_intent_async(self, user_request: str) -> str:
        """
        Async version of send_intent.

        Args:
            user_request: What the user wants to do

        Returns:
            Confirmation message
        """
        try:
            result = await self.orchestrator.process_intent(user_request)

            if result.is_conversational:
                return result.response_hint

            if result.error:
                return f"Es gab ein Problem: {result.error}"

            logger.info(f"Rachel sent intent: {result.event_type} (job={result.job_id})")
            return result.response_hint

        except Exception as e:
            logger.error(f"Rachel send_intent_async error: {e}")
            return "Es gab ein Problem bei der Verarbeitung."

    async def process_input(self, event: InputEvent) -> str:
        """
        Process user input through LLM with FULL context awareness.

        Aggregates context from 4 sources:
        0. RealTimeState - current system state (space, tasks, confidence)
        1. NotificationQueue - immediate task completion results
        2. SystemContextStore - 10-minute window of recent actions
        3. ConversationMemory - long-term history (SQLite)

        Args:
            event: Input event to process

        Returns:
            Response text
        """
        user_text = event.text
        logger.info(f"Rachel (Voice): Processing: {user_text}")

        context_parts = []

        # 0. RealTimeState - current system state (most immediate)
        try:
            from swarm.context.real_time_state import get_real_time_state
            rt_state = get_real_time_state()
            state_context = rt_state.get_rachel_context()
            if state_context:
                context_parts.append(state_context)
                logger.debug(f"Rachel: Added real-time state context")
        except Exception as e:
            logger.debug(f"RealTimeState unavailable: {e}")

        # 1. NotificationQueue - task completion results (immediate)
        pending_notifications = self.notification_queue.get_and_clear()
        if pending_notifications:
            logger.info(f"Rachel: Found {len(pending_notifications)} pending notifications")
            notification_context = self._format_notifications(pending_notifications)
            context_parts.append(f"[TASK-ERGEBNIS: {notification_context}]")

        # 1.5 QuestionQueue - pending questions from backend agents
        pending_questions = self.question_queue.get_and_clear()
        if pending_questions:
            logger.info(f"Rachel: Found {len(pending_questions)} pending questions from backend")
            question_context = self.question_queue.format_for_context(pending_questions)
            context_parts.append(f"[OFFENE FRAGEN VOM SYSTEM:\n{question_context}]")

        # 2. SystemContextStore - recent actions (10-min window)
        try:
            relevant_context = self.context_store.get_relevant(user_text, limit=3)
            if relevant_context:
                recent_actions = ", ".join([
                    f"{e.event_type}: {str(e.result)[:50]}" for e in relevant_context
                ])
                context_parts.append(f"[LETZTE AKTIONEN: {recent_actions}]")
                logger.debug(f"Rachel: Added {len(relevant_context)} recent actions to context")
        except Exception as e:
            logger.debug(f"SystemContextStore unavailable: {e}")

        # 3. ConversationMemory - long-term history
        try:
            if self.conversation_memory:
                memory_context = await self.conversation_memory.get_recent_context(limit=3)
                if memory_context:
                    history = ", ".join([
                        f"{m['input'][:30]}→{m['results'][0] if m['results'] else 'ok'}"
                        for m in memory_context
                    ])
                    context_parts.append(f"[VERLAUF: {history}]")
                    logger.debug(f"Rachel: Added {len(memory_context)} history items to context")
        except Exception as e:
            logger.debug(f"ConversationMemory unavailable: {e}")

        # Combine context and create enriched event
        if context_parts:
            context_hint = "\n".join(context_parts)
            enriched_text = f"{context_hint}\n\nUser sagt: {user_text}"
            event = InputEvent(
                text=enriched_text,
                timestamp=event.timestamp,
                source=event.source,
                metadata={**event.metadata, "has_context": True, "context_sources": len(context_parts)}
            )
            logger.info(f"Rachel: Enriched input with {len(context_parts)} context sources")

            # Phase 9: Debug-Logging für enriched prompts - zeigt was an LLM gesendet wird
            logger.info("=" * 60)
            logger.info("ENRICHED INPUT TO LLM:")
            logger.info("-" * 60)
            for line in enriched_text.split("\n"):
                logger.info(f"  {line}")
            logger.info("=" * 60)

        return await self.process_input_with_llm(event)

    def _format_notifications(self, notifications: list) -> str:
        """
        Format pending notifications as context string for the LLM.

        Args:
            notifications: List of Notification objects

        Returns:
            Formatted string for LLM context
        """
        lines = []
        for n in notifications:
            # Truncate long results
            result_str = str(n.result)
            if len(result_str) > 150:
                result_str = result_str[:150] + "..."

            # Make event type human-readable
            event_readable = n.event_type.replace(".", " ").replace("_", " ").title()
            lines.append(f"{event_readable}: {result_str}")

        return " | ".join(lines)


def create_rachel_agent(
    model_client: Any = None,
    orchestrator: Any = None,
    notification_queue: Any = None
) -> RachelAgent:
    """
    Factory function to create Rachel agent.

    Args:
        model_client: LLM client
        orchestrator: Optional pre-configured orchestrator
        notification_queue: Optional pre-configured notification queue

    Returns:
        RachelAgent instance
    """
    return RachelAgent(
        model_client=model_client,
        orchestrator=orchestrator,
        notification_queue=notification_queue
    )


__all__ = ["RachelAgent", "create_rachel_agent", "RACHEL_VOICE_PROMPT"]
