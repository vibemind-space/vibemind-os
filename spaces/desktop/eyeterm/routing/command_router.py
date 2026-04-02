"""Route voice commands: direct actions execute locally, complex tasks go to agent team."""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional

from ..audio.command_parser import CommandParser, ParsedCommand
from ..screen.element_context import UIElementContext

logger = logging.getLogger("eyeterm.router")


class RouteTarget(Enum):
    """Where a voice command gets routed."""
    DIRECT = "direct"           # Execute locally (click, type, scroll, etc.)
    AGENT_TEAM = "agent_team"   # Route to VibeMind orchestrator / MinibookHub
    LOCAL_AI = "local_ai"       # Use eyeTerm's local IntentResolver


# Actions that execute immediately via desktop tools
_DIRECT_ACTIONS = {
    "click", "type", "read", "select", "scroll",
    "apply", "cancel", "recalibrate", "undo", "switch",
    "run_tests", "press_key", "open_app",
}

# Complex task keywords (fallback check for long freeform text)
_COMPLEX_KEYWORDS = {
    "erstelle", "create", "schreibe", "write", "plane", "design",
    "analysiere", "analyze", "recherchiere", "research",
    "implementiere", "implement", "baue", "build", "konzept",
    "strategie", "strategy", "zusammenfassung", "summary",
}


@dataclass
class RouteResult:
    """Result of routing a voice command."""
    target: RouteTarget
    command: Optional[ParsedCommand]
    transcript: str
    element_context: Optional[Dict] = None  # orchestrator-formatted context


class CommandRouter:
    """Route voice transcripts to direct execution or agent team.

    Args:
        on_direct: Callback for direct actions. Receives (ParsedCommand, UIElementContext).
        on_agent_team: Callback for complex tasks. Receives (transcript, gaze_context_dict).
        on_local_ai: Callback for local AI resolution. Receives (transcript, UIElementContext).
    """

    def __init__(
        self,
        on_direct: Optional[Callable] = None,
        on_agent_team: Optional[Callable] = None,
        on_local_ai: Optional[Callable] = None,
    ) -> None:
        self._parser = CommandParser()
        self._on_direct = on_direct
        self._on_agent_team = on_agent_team
        self._on_local_ai = on_local_ai

    def route(
        self,
        transcript: str,
        element: Optional[UIElementContext] = None,
    ) -> RouteResult:
        """Classify and route a voice transcript.

        Returns RouteResult and calls the appropriate callback.
        """
        text = transcript.strip()
        if not text:
            return RouteResult(target=RouteTarget.DIRECT, command=None, transcript="")

        cmd = self._parser.parse(text)
        element_ctx = element.to_orchestrator_context() if element else None

        # 1. Explicit complex_task from parser
        if cmd and cmd.action == "complex_task":
            result = RouteResult(
                target=RouteTarget.AGENT_TEAM,
                command=cmd,
                transcript=text,
                element_context=element_ctx,
            )
            if self._on_agent_team:
                self._on_agent_team(text, element_ctx)
            logger.info("Routed to agent team (complex_task): %s", text[:60])
            return result

        # 2. Known direct actions
        if cmd and cmd.action in _DIRECT_ACTIONS:
            result = RouteResult(
                target=RouteTarget.DIRECT,
                command=cmd,
                transcript=text,
                element_context=element_ctx,
            )
            if self._on_direct:
                self._on_direct(cmd, element)
            logger.info("Routed to direct execution (%s): %s", cmd.action, text[:60])
            return result

        # 3. Freeform — check complexity heuristics
        if cmd and cmd.action == "freeform":
            words = text.split()
            has_complex_keyword = any(w.lower() in _COMPLEX_KEYWORDS for w in words)
            is_long = len(words) > 15

            if has_complex_keyword or is_long:
                result = RouteResult(
                    target=RouteTarget.AGENT_TEAM,
                    command=cmd,
                    transcript=text,
                    element_context=element_ctx,
                )
                if self._on_agent_team:
                    self._on_agent_team(text, element_ctx)
                logger.info("Routed to agent team (freeform complex): %s", text[:60])
                return result

            # Short freeform → local AI
            result = RouteResult(
                target=RouteTarget.LOCAL_AI,
                command=cmd,
                transcript=text,
                element_context=element_ctx,
            )
            if self._on_local_ai:
                self._on_local_ai(text, element)
            logger.info("Routed to local AI: %s", text[:60])
            return result

        # 4. Fallback: direct execution for any parsed command
        if cmd:
            result = RouteResult(
                target=RouteTarget.DIRECT,
                command=cmd,
                transcript=text,
                element_context=element_ctx,
            )
            if self._on_direct:
                self._on_direct(cmd, element)
            return result

        return RouteResult(target=RouteTarget.DIRECT, command=None, transcript=text)
