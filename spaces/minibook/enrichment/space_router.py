"""
Space Router — LLM-based routing decision: WHO handles the task?

Replaces the simple keyword-based detect_needed_spaces() with an
LLM-powered routing that understands context, agent capabilities,
and multi-space task decomposition.

Falls back to keyword-based routing if LLM is unavailable.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from llm_config import get_model, get_async_client

_logger = logging.getLogger(__name__)


def _debug_print(msg: str):
    _logger.debug("[SpaceRouter] %s", msg)


@dataclass
class RoutingDecision:
    """Result of the space routing decision."""
    primary_space: str = "ideas"
    secondary_spaces: List[str] = field(default_factory=list)
    is_multi_space: bool = False
    reasoning: str = ""
    confidence: float = 0.5

    @property
    def all_spaces(self) -> List[str]:
        """All spaces involved (primary + secondary)."""
        return [self.primary_space] + self.secondary_spaces


# The event_type prefix → space mapping (deterministic, no LLM needed)
EVENT_TYPE_TO_SPACE: Dict[str, str] = {
    "bubble.": "ideas",
    "idea.": "ideas",
    "shuttle.": "ideas",
    "code.": "coding",
    "desktop.": "desktop",
    "task.": "desktop",
    "research.": "research",
    "roarboot.": "rowboat",
    "schedule.": "schedule",
    "minibook.": "ideas",  # default for minibook.* events
    "rose.": "flowzen",
}


ROUTER_PROMPT_TEMPLATE = """Du bist der VibeMind SpaceRouter. Entscheide welche Spaces fuer eine Aufgabe noetig sind.

VERFUEGBARE SPACES:
{agent_registry}

KLASSIFIZIERTER EVENT-TYPE: {event_type}
BENUTZER-EINGABE: "{user_text}"
KONTEXT: {context_summary}

REGELN:
- Wenn der event_type eindeutig zu einem Space gehoert (z.B. bubble.create → ideas), waehle NUR diesen.
- Nur bei echt uebergreifenden Aufgaben mehrere Spaces waehlen.
- Bei Unsicherheit: nur primary_space setzen, secondary_spaces leer lassen.
- WICHTIG: Maximal 3 Spaces gesamt.

Antworte NUR mit JSON (kein anderer Text):
{{"primary_space": "...", "secondary_spaces": [...], "reasoning": "..."}}"""


class SpaceRouter:
    """
    LLM-based routing: decides which space(s) handle a task.

    Strategy:
    1. Deterministic: If event_type uniquely maps to a space, use that.
    2. LLM-based: For ambiguous cases, call a fast LLM.
    3. Keyword fallback: If LLM fails, use detect_needed_spaces().
    """

    def __init__(
        self,
        enrichment_model: Optional[str] = None,
        use_llm: bool = True,
    ):
        self._model = enrichment_model or get_model("space_router")
        self._use_llm = use_llm

    async def route(
        self,
        event_type: str,
        user_text: str,
        payload: Dict[str, Any],
        context_summary: str = "",
    ) -> RoutingDecision:
        """
        Decide which space(s) should handle this task.

        Args:
            event_type: Classified event type (e.g., "idea.create")
            user_text: Original user input
            payload: Classified payload
            context_summary: Context string from ContextGather

        Returns:
            RoutingDecision with primary + secondary spaces
        """
        # Step 1: Deterministic mapping from event_type
        deterministic = self._route_by_event_type(event_type)
        if deterministic:
            _debug_print(
                f"Deterministic route: {event_type} → {deterministic.primary_space}"
            )
            return deterministic

        # Step 2: LLM-based routing
        if self._use_llm:
            llm_result = await self._route_by_llm(event_type, user_text, context_summary)
            if llm_result:
                _debug_print(
                    f"LLM route: {event_type} → "
                    f"primary={llm_result.primary_space}, "
                    f"secondary={llm_result.secondary_spaces}"
                )
                return llm_result

        # Step 3: Keyword fallback
        keyword_result = self._route_by_keywords(user_text)
        _debug_print(
            f"Keyword route: → primary={keyword_result.primary_space}, "
            f"secondary={keyword_result.secondary_spaces}"
        )
        return keyword_result

    def _route_by_event_type(self, event_type: str) -> Optional[RoutingDecision]:
        """
        Deterministic routing based on event_type prefix.

        If the event_type clearly belongs to one space, route there
        with high confidence. No LLM needed.
        """
        for prefix, space in EVENT_TYPE_TO_SPACE.items():
            if event_type.startswith(prefix):
                return RoutingDecision(
                    primary_space=space,
                    secondary_spaces=[],
                    is_multi_space=False,
                    reasoning=f"event_type '{event_type}' maps to '{space}'",
                    confidence=0.95,
                )
        return None

    async def _route_by_llm(
        self,
        event_type: str,
        user_text: str,
        context_summary: str,
    ) -> Optional[RoutingDecision]:
        """
        LLM-based routing for ambiguous or multi-space tasks.

        Uses a fast model via OpenRouter to analyze the task and
        decide which spaces are needed.
        """
        try:
            client = get_async_client("space_router")

            # Build agent registry description for the prompt
            from spaces.minibook.tools.collaboration_tools import SPACE_AGENT_REGISTRY
            registry_lines = []
            for key, info in SPACE_AGENT_REGISTRY.items():
                registry_lines.append(f"- {key}: {info['role'][:100]}")
            registry_str = "\n".join(registry_lines)

            prompt = ROUTER_PROMPT_TEMPLATE.format(
                agent_registry=registry_str,
                event_type=event_type,
                user_text=user_text[:200],
                context_summary=context_summary[:300] if context_summary else "Kein Kontext",
            )

            from llm_config import token_kwargs
            response = await client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                **token_kwargs(self._model, 200),
            )

            content = response.choices[0].message.content.strip()

            # Parse JSON response
            # Handle potential markdown code fences
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            data = json.loads(content)

            primary = data.get("primary_space", "ideas")
            secondary = data.get("secondary_spaces", [])
            reasoning = data.get("reasoning", "")

            # Validate spaces exist
            valid_spaces = set(SPACE_AGENT_REGISTRY.keys())
            if primary not in valid_spaces:
                primary = "ideas"
            secondary = [s for s in secondary if s in valid_spaces and s != primary]

            return RoutingDecision(
                primary_space=primary,
                secondary_spaces=secondary,
                is_multi_space=len(secondary) > 0,
                reasoning=reasoning,
                confidence=0.8,
            )

        except json.JSONDecodeError as e:
            _logger.warning(f"SpaceRouter: LLM returned invalid JSON: {e}")
            return None
        except Exception as e:
            _logger.warning(f"SpaceRouter: LLM routing failed: {e}")
            return None

    def _route_by_keywords(self, user_text: str) -> RoutingDecision:
        """
        Keyword-based fallback routing.

        Uses the existing detect_needed_spaces() from collaboration_tools.
        """
        try:
            from spaces.minibook.tools.collaboration_tools import detect_needed_spaces
            needed = detect_needed_spaces(user_text)

            if not needed:
                needed = ["ideas"]

            primary = needed[0]
            secondary = needed[1:] if len(needed) > 1 else []

            return RoutingDecision(
                primary_space=primary,
                secondary_spaces=secondary,
                is_multi_space=len(secondary) > 0,
                reasoning="keyword-based fallback",
                confidence=0.5,
            )
        except Exception:
            return RoutingDecision(
                primary_space="ideas",
                reasoning="default fallback",
                confidence=0.3,
            )


__all__ = ["SpaceRouter", "RoutingDecision", "EVENT_TYPE_TO_SPACE"]
