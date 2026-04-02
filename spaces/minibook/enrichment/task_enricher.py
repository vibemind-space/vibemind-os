"""
Task Enricher — Builds per-agent enriched task payloads.

Takes the routing decision and enrichment context, then creates
a structured payload for each agent with:
- The specific event_type and parameters for that agent
- Relevant context (bubble state, conversation excerpt, preferences)
- Priority and response expectations
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

from .context_gather import EnrichmentContext
from .space_router import RoutingDecision

_logger = logging.getLogger(__name__)


def _debug_print(msg: str):
    _logger.debug("[TaskEnricher] %s", msg)


@dataclass
class EnrichedTask:
    """Enriched task payload for a single agent."""
    agent_name: str            # "vibemind_ideas"
    space_key: str             # "ideas"
    event_type: str            # "idea.create"
    payload: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    priority: str = "normal"   # "low", "normal", "high"
    requires_response: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "space_key": self.space_key,
            "event_type": self.event_type,
            "payload": self.payload,
            "context": self.context,
            "priority": self.priority,
            "requires_response": self.requires_response,
        }


class TaskEnricher:
    """
    Builds enriched task payloads per agent.

    For each agent in the routing decision:
    1. Determines the specific event_type for that agent
    2. Filters context to only what's relevant for that agent
    3. Adds bubble state, conversation excerpts, preferences
    4. Sets priority based on task characteristics
    """

    def enrich(
        self,
        routing: RoutingDecision,
        enrichment_context: EnrichmentContext,
        event_type: str,
        payload: Dict[str, Any],
        user_text: str,
    ) -> List[EnrichedTask]:
        """
        Build enriched task payloads for all agents in the routing.

        Args:
            routing: Which spaces handle this task
            enrichment_context: Gathered metadata
            event_type: Classified event type (e.g., "idea.create")
            payload: Classified payload (e.g., {"title": "Marketing"})
            user_text: Original user input

        Returns:
            List of EnrichedTask objects (one per agent)
        """
        _logger.debug("enrich called: event_type=%s, primary_space=%s", event_type, routing.primary_space)
        from spaces.minibook.tools.collaboration_tools import SPACE_AGENT_REGISTRY

        tasks = []

        # Primary agent gets the main task
        primary_info = SPACE_AGENT_REGISTRY.get(routing.primary_space, {})
        if primary_info:
            primary_task = EnrichedTask(
                agent_name=primary_info["name"],
                space_key=routing.primary_space,
                event_type=event_type,
                payload=dict(payload),
                context=self._build_agent_context(
                    routing.primary_space, enrichment_context, is_primary=True
                ),
                priority=self._determine_priority(event_type, routing),
                requires_response=True,
            )
            # Add user_text to payload for tools that need it
            if "user_text" not in primary_task.payload:
                primary_task.payload["user_text"] = user_text
            tasks.append(primary_task)

        # Secondary agents get supporting tasks
        for space_key in routing.secondary_spaces:
            agent_info = SPACE_AGENT_REGISTRY.get(space_key, {})
            if not agent_info:
                continue

            secondary_task = EnrichedTask(
                agent_name=agent_info["name"],
                space_key=space_key,
                event_type=self._infer_secondary_event_type(space_key, user_text),
                payload={"user_text": user_text},
                context=self._build_agent_context(
                    space_key, enrichment_context, is_primary=False
                ),
                priority="normal",
                requires_response=True,
            )
            tasks.append(secondary_task)

        _debug_print(
            f"Enriched {len(tasks)} tasks: "
            f"{', '.join(t.space_key for t in tasks)}"
        )

        return tasks

    def _build_agent_context(
        self,
        space_key: str,
        ctx: EnrichmentContext,
        is_primary: bool,
    ) -> Dict[str, Any]:
        """
        Build context dict filtered for a specific agent.

        Primary agents get full context, secondary agents get minimal context.
        """
        agent_ctx: Dict[str, Any] = {}

        # Current bubble (relevant for ideas, coding, swe_design)
        if space_key in ("ideas", "coding", "swe_design", "transformer"):
            if ctx.current_bubble_name:
                agent_ctx["current_bubble"] = ctx.current_bubble_name
            if ctx.current_bubble_id:
                agent_ctx["current_bubble_id"] = ctx.current_bubble_id

        # Idea count (for SpaceAgent context)
        idea_count = getattr(ctx, "idea_count", 0)
        if idea_count:
            agent_ctx["idea_count"] = idea_count

        # Conversation history (primary gets more)
        if is_primary and ctx.conversation_history:
            agent_ctx["conversation_history"] = ctx.conversation_history[-5:]
        elif ctx.conversation_history:
            agent_ctx["conversation_history"] = ctx.conversation_history[-2:]

        # Recent results (for continuity)
        if ctx.recent_results:
            # Filter to this space's results if possible
            space_results = [
                r for r in ctx.recent_results
                if r.get("event_type", "").startswith(
                    _space_to_prefix(space_key)
                )
            ]
            if space_results:
                agent_ctx["recent_results"] = space_results[:2]
            elif is_primary:
                agent_ctx["recent_results"] = ctx.recent_results[:1]

        # User preferences
        if ctx.user_preferences:
            agent_ctx["user_preferences"] = ctx.user_preferences

        return agent_ctx

    def _determine_priority(
        self,
        event_type: str,
        routing: RoutingDecision,
    ) -> str:
        """Determine task priority based on characteristics."""
        # Schedule tasks that fire from APScheduler are high priority
        if event_type.startswith("schedule."):
            return "high"

        # Multi-space tasks are normal (they're already complex)
        if routing.is_multi_space:
            return "normal"

        # Simple listing/status queries are low priority
        if any(event_type.endswith(s) for s in (".list", ".status", ".count")):
            return "low"

        return "normal"

    def _infer_secondary_event_type(
        self,
        space_key: str,
        user_text: str,
    ) -> str:
        """
        Infer a reasonable event_type for a secondary space.

        When the SpaceRouter adds a secondary space, we need to
        determine what that space should actually DO.
        """
        # Default patterns per space for secondary tasks
        defaults = {
            "ideas": "idea.create",
            "coding": "code.generate",
            "desktop": "desktop.execute",
            "research": "research.search",
            "rowboat": "roarboot.search",
            "schedule": "schedule.create",
            "openclaw": "desktop.orchestrate",
            "swe_design": "shuttle.analyze",
            "transformer": "shuttle.transform",
        }
        return defaults.get(space_key, f"{space_key}.process")


def _space_to_prefix(space_key: str) -> str:
    """Map space key to its event_type prefix for filtering."""
    prefixes = {
        "ideas": "idea.",
        "coding": "code.",
        "desktop": "desktop.",
        "research": "research.",
        "rowboat": "roarboot.",
        "schedule": "schedule.",
        "openclaw": "desktop.",
        "swe_design": "shuttle.",
        "transformer": "shuttle.",
    }
    return prefixes.get(space_key, f"{space_key}.")


__all__ = ["TaskEnricher", "EnrichedTask"]
