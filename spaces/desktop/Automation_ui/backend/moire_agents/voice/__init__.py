"""Voice-controlled desktop automation module.

This module provides:
- speech_to_text: Whisper-based speech recognition
- intent_parser: Claude-based natural language understanding
- command_executor: MCP tool execution
- text_to_speech: Voice feedback
"""

from .speech_to_text import SpeechToText
from .intent_parser import IntentParser
from .command_executor import CommandExecutor
from .text_to_speech import TextToSpeech

__all__ = [
    "SpeechToText",
    "IntentParser",
    "CommandExecutor",
    "TextToSpeech"
]
