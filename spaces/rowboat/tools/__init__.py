"""
Roarboot Space Tools

Tools for interacting with Rowboat knowledge graph via voice commands.

Sections:
- KNOWLEDGE TOOLS: Search and query the knowledge graph
- CONTENT GENERATION TOOLS: Email, meeting brief, deck, voice note
- DOCKER TOOLS: Start/stop/restart/status for Rowboat Docker stack
- SYSTEM TOOLS: Status, WebView, conversation reset
"""

# =============================================================================
# KNOWLEDGE TOOLS
# =============================================================================
from .roarboot_tools import (
    search_knowledge,
    query_knowledge,
)

# =============================================================================
# CONTENT GENERATION TOOLS
# =============================================================================
from .roarboot_tools import (
    draft_email,
    generate_meeting_brief,
    generate_deck,
    process_voice_note,
)

# =============================================================================
# SYSTEM TOOLS
# =============================================================================
from .roarboot_tools import (
    get_status,
    open_webview,
    reset_conversation,
)

# =============================================================================
# DOCKER TOOLS
# =============================================================================
from .docker_tools import (
    start_docker,
    stop_docker,
    restart_docker,
    docker_status,
)

# =============================================================================
# CLIENT
# =============================================================================
from .roarboot_client import (
    RoarbootClient,
    get_roarboot_client,
)

__all__ = [
    # Knowledge Tools
    "search_knowledge",
    "query_knowledge",
    # Content Generation Tools
    "draft_email",
    "generate_meeting_brief",
    "generate_deck",
    "process_voice_note",
    # System Tools
    "get_status",
    "open_webview",
    "reset_conversation",
    # Docker Tools
    "start_docker",
    "stop_docker",
    "restart_docker",
    "docker_status",
    # Client
    "RoarbootClient",
    "get_roarboot_client",
]
