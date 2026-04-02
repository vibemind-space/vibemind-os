"""
Context Gather — Collects metadata from all existing VibeMind stores.

Gathers conversation history, current bubble state, recent results,
user preferences, and agent status into a single EnrichmentContext
that the Enrichment Pipeline uses for intelligent routing and enrichment.

All data sources are EXISTING — this module only aggregates.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

_logger = logging.getLogger(__name__)


def _debug_print(msg: str):
    _logger.debug("[ContextGather] %s", msg)


@dataclass
class EnrichmentContext:
    """Aggregated context from all VibeMind stores."""

    # Conversation history (last N messages)
    conversation_history: List[Dict[str, str]] = field(default_factory=list)

    # Current bubble/workspace state
    current_bubble_id: Optional[str] = None
    current_bubble_name: Optional[str] = None

    # Idea count in current bubble (for SpaceAgent context)
    idea_count: int = 0

    # Recent task results (for continuity)
    recent_results: List[Dict[str, Any]] = field(default_factory=list)

    # User preferences from profile
    user_preferences: Dict[str, Any] = field(default_factory=dict)

    # Agent status (from RachelInterface)
    agent_status: Dict[str, str] = field(default_factory=dict)

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_summary(self) -> str:
        """Build a compact summary string for LLM prompts."""
        _logger.debug("to_summary called: bubble=%s, history_len=%s", self.current_bubble_name, len(self.conversation_history))
        parts = []

        if self.current_bubble_name:
            parts.append(f"Aktueller Bubble: {self.current_bubble_name}")

        if self.conversation_history:
            last_msgs = self.conversation_history[-3:]
            history_str = " | ".join(
                f"{m.get('speaker', '?')}: {m.get('text', '')[:60]}"
                for m in last_msgs
            )
            parts.append(f"Letzte Nachrichten: {history_str}")

        if self.recent_results:
            last = self.recent_results[0]
            parts.append(
                f"Letztes Ergebnis: {last.get('event_type', '?')} "
                f"({last.get('summary', '')[:40]})"
            )

        online = [k for k, v in self.agent_status.items() if v in ("online", "registered")]
        if online:
            parts.append(f"Online Agents: {', '.join(online)}")

        return "\n".join(parts) if parts else "Kein Kontext verfuegbar."


class ContextGather:
    """
    Gathers metadata from existing VibeMind stores.

    Sources (all optional, graceful degradation):
    - ConversationRepository → conversation_history
    - get_current_bubble_id() → current_bubble
    - SystemContextStore → recent_results
    - UserProfileService (Supermemory) → user_preferences
    - RachelInterface → agent_status
    """

    def __init__(
        self,
        rachel_interface: Optional[Any] = None,
        max_conversation_messages: int = 5,
        max_recent_results: int = 3,
    ):
        self._rachel = rachel_interface
        self._max_messages = max_conversation_messages
        self._max_results = max_recent_results

    def gather(self, context: Optional[Dict] = None) -> EnrichmentContext:
        """
        Gather all available context.

        Args:
            context: Optional pre-existing context dict from the orchestrator

        Returns:
            EnrichmentContext with all available metadata
        """
        _logger.debug("gather called: context=%s", type(context).__name__ if context else "None")
        ctx = EnrichmentContext()

        # Pre-existing context from orchestrator (may be dict or TaskContext)
        if context:
            if isinstance(context, dict):
                ctx.metadata = context
            elif hasattr(context, '__dict__'):
                ctx.metadata = {
                    k: v for k, v in context.__dict__.items()
                    if not k.startswith('_')
                }
            else:
                ctx.metadata = {"raw": str(context)}

        # Source 1: Conversation history
        self._gather_conversation(ctx)

        # Source 2: Current bubble state
        self._gather_bubble_state(ctx)

        # Source 3: Recent results
        self._gather_recent_results(ctx)

        # Source 4: User preferences
        self._gather_user_preferences(ctx)

        # Source 5: Agent status from Rachel Interface
        self._gather_agent_status(ctx)

        return ctx

    def _gather_conversation(self, ctx: EnrichmentContext) -> None:
        """Get recent conversation messages."""
        try:
            from data import ConversationRepository
            repo = ConversationRepository()
            # Get latest session
            sessions = repo.get_recent_sessions(limit=1)
            if sessions:
                session_id = sessions[0].get("id") or sessions[0].get("session_id", "")
                if session_id:
                    messages = repo.get_messages(session_id, limit=self._max_messages)
                    ctx.conversation_history = [
                        {"speaker": m.get("speaker", ""), "text": m.get("text", "")}
                        for m in messages
                    ]
        except Exception as e:
            _logger.debug(f"Could not gather conversation: {e}")

    def _gather_bubble_state(self, ctx: EnrichmentContext) -> None:
        """Get current bubble/workspace context and idea count."""
        try:
            from electron_backend import get_current_bubble_id, _bubbles
            bubble_id = get_current_bubble_id()
            if bubble_id is not None:
                ctx.current_bubble_id = str(bubble_id)
                bubble = _bubbles.get(bubble_id)
                if bubble and hasattr(bubble, "name"):
                    ctx.current_bubble_name = bubble.name

                # Get idea count for the current bubble
                try:
                    from data.database import get_db
                    db = get_db()
                    row = db.fetch_one(
                        "SELECT COUNT(*) as cnt FROM ideas WHERE parent_id = ?",
                        (bubble_id,)
                    )
                    ctx.idea_count = row["cnt"] if row else 0
                except Exception:
                    pass
        except Exception as e:
            _logger.debug(f"Could not gather bubble state: {e}")

    def _gather_recent_results(self, ctx: EnrichmentContext) -> None:
        """Get recent task results from system context or Rachel."""
        if self._rachel:
            try:
                results = list(self._rachel._recent_results)[:self._max_results]
                ctx.recent_results = [
                    {
                        "event_type": r.event_type,
                        "summary": r.result_summary[:100] if r.result_summary else "",
                        "success": r.success,
                    }
                    for r in results
                ]
                return
            except Exception:
                pass

        # Fallback: SystemContextStore
        try:
            from swarm.monitoring.system_status import get_status_monitor
            monitor = get_status_monitor()
            if monitor and hasattr(monitor, "recent_results"):
                ctx.recent_results = monitor.recent_results[:self._max_results]
        except Exception as e:
            _logger.debug(f"Could not gather recent results: {e}")

    def _gather_user_preferences(self, ctx: EnrichmentContext) -> None:
        """Get user preferences from Supermemory profile."""
        try:
            from memory import get_user_profile_service
            profile_svc = get_user_profile_service()
            if profile_svc:
                profile = profile_svc.get_current_profile()
                if profile:
                    ctx.user_preferences = {
                        "language": getattr(profile, "language", "de"),
                        "verbosity": getattr(profile, "verbosity", "normal"),
                    }
        except Exception as e:
            _logger.debug(f"Could not gather user preferences: {e}")

    def _gather_agent_status(self, ctx: EnrichmentContext) -> None:
        """Get agent online/offline status from Rachel Interface."""
        if self._rachel:
            try:
                for agent_name, agent in self._rachel._agents.items():
                    short_name = agent.space_key
                    ctx.agent_status[short_name] = (
                        "online" if agent.is_online else agent.status
                    )
            except Exception as e:
                _logger.debug(f"Could not gather agent status: {e}")


__all__ = ["ContextGather", "EnrichmentContext"]
