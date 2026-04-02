"""
ZeroClaw Research Agent

Backend agent for the Research Space that routes research tasks
to ZeroClaw's gateway for web research, scraping, and summarization.

Results flow back into VibeMind as Ideas or Rowboat Knowledge Graph entries.
"""

import logging
from typing import Callable, Dict, Optional

from swarm.backend_agents.base_agent import BaseBackendAgent

logger = logging.getLogger(__name__)


class ZeroClawResearchAgent(BaseBackendAgent):
    """
    Backend agent for Research Space (ZeroClaw-powered).

    Extends BaseBackendAgent to route research tasks to ZeroClaw.
    Results are stored as Ideas or pushed to Rowboat.
    """

    # Event type to tool name mapping
    EVENT_TO_TOOL = {
        "research.web": "web_research",
        "research.scrape": "scrape_url",
        "research.summarize": "summarize_url",
        "research.to_idea": "research_to_idea",
        "research.to_rowboat": "research_to_rowboat",
    }

    # Parameter normalization (classifier output -> tool params)
    PARAM_MAPPING = {
        "research.web": {
            "thema": "query",
            "topic": "query",
            "suche": "query",
            "frage": "query",
            "text": "query",
        },
        "research.scrape": {
            "link": "url",
            "seite": "url",
            "webseite": "url",
            "website": "url",
        },
        "research.summarize": {
            "link": "url",
            "seite": "url",
            "webseite": "url",
            "website": "url",
        },
        "research.to_idea": {
            "thema": "query",
            "topic": "query",
            "suche": "query",
            "name": "title",
            "titel": "title",
        },
        "research.to_rowboat": {
            "thema": "query",
            "topic": "query",
            "suche": "query",
        },
    }

    def __init__(self):
        super().__init__()

    @property
    def name(self) -> str:
        return "ZeroClawResearchAgent"

    @property
    def stream(self) -> str:
        return "events:tasks:zeroclaw"

    def _load_tools(self) -> Dict[str, Callable]:
        """Load research tools."""
        tools = {}

        try:
            from spaces.research.tools.research_tools import (
                web_research,
                scrape_url,
                summarize_url,
                research_to_idea,
                research_to_rowboat,
            )

            tools.update({
                "web_research": web_research,
                "scrape_url": scrape_url,
                "summarize_url": summarize_url,
                "research_to_idea": research_to_idea,
                "research_to_rowboat": research_to_rowboat,
            })
            logger.info(f"{self.name}: Loaded {len(tools)} research tools")

        except ImportError as e:
            logger.warning(f"{self.name}: Could not load research tools: {e}")

        return tools

    def _get_tool_name(self, event_type: str) -> Optional[str]:
        """Map event type to tool name."""
        return self.EVENT_TO_TOOL.get(event_type)


# Singleton
_agent: Optional[ZeroClawResearchAgent] = None


def get_zeroclaw_research_agent() -> ZeroClawResearchAgent:
    """Get or create ZeroClawResearchAgent singleton."""
    global _agent
    if _agent is None:
        _agent = ZeroClawResearchAgent()
    return _agent


__all__ = [
    "ZeroClawResearchAgent",
    "get_zeroclaw_research_agent",
]
