"""
Messaging Pipeline — Voice ↔ WhatsApp/Telegram via Clawdbot

Connects Voice → Rowboat → Clawdbot for outgoing messages
and Clawdbot → Ollama → Rowboat → Voice for incoming messages.
"""

from .messaging_pipeline import MessagingPipeline, get_messaging_pipeline
from .relevance_filter import RelevanceFilter
from .incoming_handler import IncomingMessageHandler

__all__ = [
    "MessagingPipeline",
    "get_messaging_pipeline",
    "RelevanceFilter",
    "IncomingMessageHandler",
]
