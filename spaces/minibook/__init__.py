"""
Minibook Space - Inter-Space Collaboration Layer

Enables VibeMind spaces to collaborate on multi-step tasks via Minibook,
a self-hosted agent collaboration platform.

Architecture:
- Each VibeMind space registers as a Minibook agent with a role
- Multi-space tasks are posted as discussions with @mentions
- Spaces respond to @mentions by executing tools and posting results
- Results flow back non-blocking via inject_system_message() or NotificationQueue

When USE_MINIBOOK_HUB=true, MinibookHub becomes the central execution hub
for ALL intents (single-space and multi-space). The EnrichmentPipeline
classifies, routes, and enriches tasks before posting to Minibook.

Usage:
    from spaces.minibook import get_minibook_client, get_minibook_agent

    # Check status
    client = get_minibook_client()
    status = client.get_status()

    # Start backend agent (Redis integration)
    agent = get_minibook_agent()
    await agent.start()

    # Create space responders
    from spaces.minibook import create_space_responders
    responders = create_space_responders()

    # Central Hub (when USE_MINIBOOK_HUB=true)
    from spaces.minibook import MinibookHub
    hub = MinibookHub(client, pipeline, rachel, aggregator)
    result = await hub.dispatch("Zeig meine Bubbles")
"""

# Configuration
from .config import MinibookConfig, get_config

# Backend Agent
from .agents import MinibookBackendAgent, get_minibook_agent

# Tools
from .tools import (
    MinibookClient,
    get_minibook_client,
    get_minibook_status,
    start_discussion,
    get_discussion_results,
    list_projects,
    start_collaboration,
    poll_responses,
    register_all_space_agents,
    SPACE_AGENT_REGISTRY,
)

# Workers
from .workers import (
    DiscussionPollerWorker,
    SpaceMinibookResponder,
    get_discussion_poller,
)

# Central Hub
from .minibook_hub import MinibookHub

# Rachel Interface
from .rachel_interface import RachelInterface, get_rachel_interface

# Result Aggregator
from .result_aggregator import ResultAggregator, get_result_aggregator

# Enrichment Pipeline
from .enrichment import (
    EnrichmentPipeline,
    PipelineResult,
    create_enrichment_pipeline,
    ContextGather,
    EnrichmentContext,
    SpaceRouter,
    RoutingDecision,
    TaskEnricher,
    EnrichedTask,
)

__all__ = [
    # Config
    "MinibookConfig",
    "get_config",
    # Backend Agent
    "MinibookBackendAgent",
    "get_minibook_agent",
    # Client
    "MinibookClient",
    "get_minibook_client",
    # Tools
    "get_minibook_status",
    "start_discussion",
    "get_discussion_results",
    "list_projects",
    "start_collaboration",
    "poll_responses",
    "register_all_space_agents",
    "SPACE_AGENT_REGISTRY",
    # Workers
    "DiscussionPollerWorker",
    "SpaceMinibookResponder",
    "get_discussion_poller",
    # Central Hub
    "MinibookHub",
    # Rachel Interface
    "RachelInterface",
    "get_rachel_interface",
    # Result Aggregator
    "ResultAggregator",
    "get_result_aggregator",
    # Enrichment Pipeline
    "EnrichmentPipeline",
    "PipelineResult",
    "create_enrichment_pipeline",
    "ContextGather",
    "EnrichmentContext",
    "SpaceRouter",
    "RoutingDecision",
    "TaskEnricher",
    "EnrichedTask",
]
