"""
API Module - Interfaces for interacting with MoireTracker.

Provides:
- ConversationInterface: Natural language API for conversational AI
- quick_automate: Simple helper for one-off automation tasks
"""

from .conversation_interface import ConversationInterface, quick_automate

__all__ = [
    "ConversationInterface",
    "quick_automate"
]
