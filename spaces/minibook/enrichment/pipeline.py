"""
Enrichment Pipeline — Orchestrates the 4 enrichment stages.

Stages:
1. ContextGather: Collect metadata from all VibeMind stores
2. IntentClassifier: Classify user input to event_type + payload (REUSED)
3. SpaceRouter: LLM-based decision of which space(s) handle the task
4. TaskEnricher: Build per-agent enriched payloads with context

The pipeline sits between intent reception and Minibook posting.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from .context_gather import ContextGather, EnrichmentContext
from .space_router import SpaceRouter, RoutingDecision
from .task_enricher import TaskEnricher, EnrichedTask

_logger = logging.getLogger(__name__)


def _debug_print(msg: str):
    _logger.debug("[EnrichmentPipeline] %s", msg)


@dataclass
class PipelineResult:
    """Result of the Enrichment Pipeline."""
    event_type: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    routing: RoutingDecision = field(default_factory=RoutingDecision)
    enriched_tasks: List[EnrichedTask] = field(default_factory=list)
    context: EnrichmentContext = field(default_factory=EnrichmentContext)
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.event_type)


class EnrichmentPipeline:
    """
    Orchestrates the 4-stage enrichment process.

    Reuses the existing IntentClassifier for classification,
    adds LLM-based routing and per-agent enrichment on top.
    """

    def __init__(
        self,
        context_gather: ContextGather,
        classifier: Any,  # IntentClassifier instance
        space_router: SpaceRouter,
        task_enricher: TaskEnricher,
    ):
        self._gather = context_gather
        self._classifier = classifier
        self._router = space_router
        self._enricher = task_enricher

    async def process(
        self,
        intent_text: str,
        context: Optional[Dict] = None,
    ) -> PipelineResult:
        """
        Run the full enrichment pipeline.

        Args:
            intent_text: User's natural language input
            context: Optional pre-existing context from orchestrator

        Returns:
            PipelineResult with event_type, routing, enriched tasks
        """
        result = PipelineResult()

        try:
            # ─────────────────────────────────────────────────────────────
            # Stage 1: Context Gather
            # ─────────────────────────────────────────────────────────────
            enrichment_ctx = self._gather.gather(context)
            result.context = enrichment_ctx

            # ─────────────────────────────────────────────────────────────
            # Stage 2: Intent Classification (REUSE existing classifier)
            # ─────────────────────────────────────────────────────────────
            classification = await self._classify(intent_text)
            if not classification:
                result.error = "Classification failed"
                return result

            # Handle multi-step classifications:
            # The classifier returns {"is_multi_step": true, "steps": [...]}
            # SpaceAgents handle multi-tool chaining natively, so we extract
            # the first step's event_type for routing and pass the full user text.
            if classification.get("is_multi_step") and classification.get("steps"):
                first_step = classification["steps"][0]
                event_type = first_step.get("event_type", "")
                payload = first_step.get("payload", {})
                payload["user_text"] = intent_text  # Full text for SpaceAgent
                _debug_print(
                    f"Multi-step → using first step for routing: {event_type} "
                    f"({len(classification['steps'])} steps total)"
                )
            else:
                event_type = classification.get("event_type", "")
                payload = classification.get("payload", {})

            if not event_type:
                result.error = "No event_type classified"
                return result

            result.event_type = event_type
            result.payload = payload

            _debug_print(f"Classified: {event_type} | payload={payload}")

            # Skip non-actionable event types
            if event_type in ("conversation", "unclear", "none"):
                result.error = f"Non-actionable event_type: {event_type}"
                return result

            # ─────────────────────────────────────────────────────────────
            # Stage 3: Space Routing
            # ─────────────────────────────────────────────────────────────
            routing = await self._router.route(
                event_type=event_type,
                user_text=intent_text,
                payload=payload,
                context_summary=enrichment_ctx.to_summary(),
            )
            result.routing = routing

            _debug_print(
                f"Routed: primary={routing.primary_space}, "
                f"secondary={routing.secondary_spaces}, "
                f"multi={routing.is_multi_space}"
            )

            # ─────────────────────────────────────────────────────────────
            # Stage 4: Task Enrichment
            # ─────────────────────────────────────────────────────────────
            enriched_tasks = self._enricher.enrich(
                routing=routing,
                enrichment_context=enrichment_ctx,
                event_type=event_type,
                payload=payload,
                user_text=intent_text,
            )
            result.enriched_tasks = enriched_tasks

            _debug_print(
                f"Enriched: {len(enriched_tasks)} tasks for "
                f"{', '.join(t.space_key for t in enriched_tasks)}"
            )

            return result

        except Exception as e:
            _logger.error(f"EnrichmentPipeline error: {e}")
            result.error = str(e)
            return result

    async def _classify(self, intent_text: str) -> Optional[Dict[str, Any]]:
        """
        Classify user input using the existing IntentClassifier.

        Returns:
            Dict with "event_type" and "payload", or None on failure
        """
        try:
            # The IntentClassifier.classify() method returns a dict
            # with event_type, payload, and confidence
            classification = await self._classifier.classify(intent_text)

            if isinstance(classification, dict):
                return classification

            # Some versions return a ClassificationResult object
            if hasattr(classification, "event_type"):
                return {
                    "event_type": classification.event_type,
                    "payload": getattr(classification, "payload", {}) or {},
                }

            return None

        except Exception as e:
            _logger.error(f"Classification failed: {e}")
            return None


# =============================================================================
# Factory
# =============================================================================

def create_enrichment_pipeline(
    classifier: Any,
    rachel_interface: Optional[Any] = None,
    enrichment_model: Optional[str] = None,
    use_llm_routing: bool = True,
) -> EnrichmentPipeline:
    """
    Factory function to create a fully wired EnrichmentPipeline.

    Args:
        classifier: IntentClassifier instance (existing)
        rachel_interface: RachelInterface instance (for context gathering)
        enrichment_model: LLM model for SpaceRouter
        use_llm_routing: Whether to use LLM routing (True) or keywords only

    Returns:
        Configured EnrichmentPipeline instance
    """
    from llm_config import get_model
    if enrichment_model is None:
        enrichment_model = get_model("space_router")
    _logger.debug("create_enrichment_pipeline called: model=%s, llm_routing=%s", enrichment_model, use_llm_routing)
    context_gather = ContextGather(rachel_interface=rachel_interface)
    space_router = SpaceRouter(
        enrichment_model=enrichment_model,
        use_llm=use_llm_routing,
    )

    # Wrap SpaceRouter with BrainRouter if brain server is available
    try:
        import os
        brain_enabled = os.environ.get('USE_BRAIN_ROUTER', 'true').lower() == 'true'
        if brain_enabled:
            from spaces.minibook.enrichment.brain_router import BrainRouter
            router = BrainRouter(
                brain_url=os.environ.get('BRAIN_URL', 'http://localhost:5000'),
                fallback_router=space_router,
            )
            _logger.info("BrainRouter wrapping SpaceRouter (brain fast-path enabled)")
        else:
            router = space_router
    except Exception as e:
        _logger.warning(f"BrainRouter init failed, using SpaceRouter only: {e}")
        router = space_router

    task_enricher = TaskEnricher()

    pipeline = EnrichmentPipeline(
        context_gather=context_gather,
        classifier=classifier,
        space_router=router,
        task_enricher=task_enricher,
    )

    _debug_print(
        f"Created EnrichmentPipeline: "
        f"model={enrichment_model}, llm_routing={use_llm_routing}"
    )

    return pipeline


__all__ = [
    "EnrichmentPipeline",
    "PipelineResult",
    "create_enrichment_pipeline",
]
