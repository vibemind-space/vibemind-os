"""
Roarboot Space — Rowboat Knowledge Graph Integration

AI coworker that turns work into a knowledge graph and acts on it.
Rowboat runs as a Docker container, VibeMind communicates via Python SDK.

Features:
- Knowledge Graph search and queries (emails, meetings, people, projects)
- Email drafting with historical context
- Meeting brief generation
- Presentation deck creation
- Voice note processing
- Docker stack management (start/stop/restart/status)
- WebView embedding for Rowboat UI
- Per-context conversation management

Integration:
- Listens to Redis stream 'events:tasks:roarboot'
- Uses Rowboat Python SDK (with direct HTTP fallback)
- Electron WebView for Rowboat's Next.js UI
- Broadcast agent for fan-out event handling
- Health check worker for Docker monitoring

Usage:
    from spaces.rowboat import get_roarboot_agent

    # Backend agent for Redis integration
    agent = get_roarboot_agent()
    await agent.start()  # Listen to Redis stream

    # Broadcast agent for fan-out
    from spaces.rowboat import get_roarboot_broadcast_agent
    broadcast = get_roarboot_broadcast_agent()

    # Workers for background monitoring
    from spaces.rowboat import create_roarboot_workers
    workers = create_roarboot_workers()
"""

# Configuration
from .config import RoarbootConfig, get_config

# Backend Agent (Redis integration)
from .agents import (
    RoarbootBackendAgent,
    get_roarboot_agent,
)

# Broadcast Agent (fan-out)
from .broadcast import (
    RoarbootBroadcastAgent,
    get_roarboot_broadcast_agent,
)

# Workers (background monitoring)
from .workers import (
    HealthCheckWorker,
    create_roarboot_workers,
)

# Knowledge & Content Tools
from .tools import (
    search_knowledge,
    query_knowledge,
    draft_email,
    generate_meeting_brief,
    generate_deck,
    process_voice_note,
    get_status,
    open_webview,
    reset_conversation,
    RoarbootClient,
    get_roarboot_client,
)

# Docker Tools
from .tools import (
    start_docker,
    stop_docker,
    restart_docker,
    docker_status,
)

__all__ = [
    # Config
    "RoarbootConfig",
    "get_config",
    # Backend Agent
    "RoarbootBackendAgent",
    "get_roarboot_agent",
    # Broadcast Agent
    "RoarbootBroadcastAgent",
    "get_roarboot_broadcast_agent",
    # Workers
    "HealthCheckWorker",
    "create_roarboot_workers",
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
