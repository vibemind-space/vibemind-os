"""
VibeMind Ideas Space Module

Rachel's domain - Bubble and idea management.
Includes backend agents, tools, and user agent.
"""

# Import from local agents module (migrated code)
from .agents import (
    IdeasAgent,
    get_ideas_agent,
    BubblesAgent,
    get_bubbles_agent,
    RachelAgent,
    create_rachel_agent,
    RACHEL_VOICE_PROMPT,
)

__all__ = [
    # Backend Agents
    "IdeasAgent",
    "get_ideas_agent",
    "BubblesAgent",
    "get_bubbles_agent",
    # User Agent
    "RachelAgent",
    "create_rachel_agent",
    "RACHEL_VOICE_PROMPT",
]
