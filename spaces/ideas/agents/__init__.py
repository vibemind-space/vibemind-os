"""
VibeMind Ideas Space - Agents Module

Backend and User agents for bubble and idea management.
"""

from .ideas_agent import IdeasAgent, get_ideas_agent
from .bubbles_agent import BubblesAgent, get_bubbles_agent
from .rachel_agent import RachelAgent, create_rachel_agent, RACHEL_VOICE_PROMPT

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
