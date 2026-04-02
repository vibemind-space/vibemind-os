"""
VibeMind Coding Space Tools

Tools for code generation and project management.
Includes client tools, adapted swarm tools, and voice coding tools.
"""

from .coding_tools import (
    generate_code,
    get_generation_status,
    cancel_generation,
    list_generated_projects,
    start_preview,
    stop_preview,
    exit_project,
    CODING_TOOLS,
    register_coding_tools,
    set_electron_sender,
    set_coding_engine_runner,
)

from .adapted_coding_tools import (
    CODING_TOOLS as ADAPTED_CODING_TOOLS,
)

from .voice_coding_tools import (
    VOICE_CODING_TOOLS,
    VOICE_CODING_TOOLS_ASYNC,
)

__all__ = [
    # Core coding tools
    "generate_code",
    "get_generation_status",
    "cancel_generation",
    "list_generated_projects",
    "start_preview",
    "stop_preview",
    "exit_project",
    "CODING_TOOLS",
    "register_coding_tools",
    "set_electron_sender",
    "set_coding_engine_runner",
    # Adapted tools
    "ADAPTED_CODING_TOOLS",
    # Voice coding tools
    "VOICE_CODING_TOOLS",
    "VOICE_CODING_TOOLS_ASYNC",
]
