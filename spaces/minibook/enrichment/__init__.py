"""
Enrichment Pipeline — Intelligent task routing and context enrichment.

Stages:
1. ContextGather: Aggregate metadata from VibeMind stores
2. IntentClassifier: Classify event_type (reuses existing classifier)
3. SpaceRouter: LLM-based routing decision (which spaces?)
4. TaskEnricher: Per-agent enriched payloads with context
"""

from .context_gather import ContextGather, EnrichmentContext
from .space_router import SpaceRouter, RoutingDecision
from .task_enricher import TaskEnricher, EnrichedTask
from .pipeline import EnrichmentPipeline, PipelineResult, create_enrichment_pipeline

__all__ = [
    # Pipeline
    "EnrichmentPipeline",
    "PipelineResult",
    "create_enrichment_pipeline",
    # Context
    "ContextGather",
    "EnrichmentContext",
    # Router
    "SpaceRouter",
    "RoutingDecision",
    # Enricher
    "TaskEnricher",
    "EnrichedTask",
]
