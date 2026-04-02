"""
Minibook Hub — Central dispatch for ALL VibeMind task execution.

When USE_MINIBOOK_HUB=true, every user intent flows through Minibook:

    process_intent() → MinibookHub.dispatch()
        → EnrichmentPipeline (classify + route + enrich)
        → Minibook POST (@mentions for relevant agents)
        → Single-space: sync-wait for response (<=10s)
        → Multi-space: async-poll via ResultAggregator
        → Fallback to _process_sync() on timeout/error

Architecture principle: Minibook is the MESSAGE BUS, not the execution engine.
SpaceMinibookResponders execute tools. Minibook stores the task/result pairs.
"""

import json
import logging
import time
import uuid
from typing import Optional, Any, Callable, Dict

_logger = logging.getLogger(__name__)


def _debug_print(msg: str):
    _logger.debug("[MinibookHub] %s", msg)


class MinibookHub:
    """
    Central dispatch: all intents route through Minibook.

    Integrates:
    - EnrichmentPipeline: classifies, routes, and enriches tasks
    - MinibookClient: posts tasks to Minibook with @mentions
    - ResultAggregator: waits for (sync) or tracks (async) results
    - RachelInterface: updates agent/task status
    """

    def __init__(
        self,
        client: Any,
        enrichment_pipeline: Any,
        rachel_interface: Any,
        result_aggregator: Any,
        sync_timeout: float = 10.0,
        fallback_executor: Optional[Callable] = None,
    ):
        """
        Args:
            client: MinibookClient instance
            enrichment_pipeline: EnrichmentPipeline instance
            rachel_interface: RachelInterface instance
            result_aggregator: ResultAggregator instance
            sync_timeout: Max seconds for single-space sync-wait
            fallback_executor: Optional direct executor for fallback
                               (IntentOrchestrator._process_sync)
        """
        self._client = client
        self._pipeline = enrichment_pipeline
        self._rachel = rachel_interface
        self._aggregator = result_aggregator
        self._sync_timeout = sync_timeout
        self._fallback = fallback_executor

    async def dispatch(
        self,
        intent_text: str,
        context: Optional[Dict] = None,
    ) -> Optional[Any]:
        """
        Dispatch an intent through Minibook.

        Flow:
        1. EnrichmentPipeline → event_type, routing, enriched payloads
        2. Minibook POST with @mentions
        3. Single-space → sync-wait for response
           Multi-space → async-poll + immediate acknowledgment
        4. On timeout → fallback to direct execution (if available)

        Args:
            intent_text: User's natural language input
            context: Optional conversation context dict

        Returns:
            OrchestrationResult-like object, or None on failure
        """
        task_id = str(uuid.uuid4())[:8]
        t0 = time.time()

        try:
            # -----------------------------------------------------------------
            # Step 1: Enrichment Pipeline
            # -----------------------------------------------------------------
            pipeline_result = await self._pipeline.process(intent_text, context)

            if not pipeline_result or not pipeline_result.event_type:
                _debug_print(f"Pipeline returned no event_type for: {intent_text[:60]}")
                return None

            event_type = pipeline_result.event_type
            routing = pipeline_result.routing
            enriched_tasks = pipeline_result.enriched_tasks
            payload = pipeline_result.payload

            _debug_print(
                f"Pipeline: event={event_type}, "
                f"primary={routing.primary_space}, "
                f"multi={routing.is_multi_space}, "
                f"confidence={routing.confidence:.2f}"
            )

            # Register task in Rachel Interface
            all_spaces = [routing.primary_space] + routing.secondary_spaces
            self._rachel.register_task(task_id, all_spaces, intent_text)

            # -----------------------------------------------------------------
            # Step 2: Build Minibook POST content
            # -----------------------------------------------------------------
            post_content = self._build_post_content(
                enriched_tasks, intent_text, event_type
            )

            # Build @mentions
            from spaces.minibook.tools.collaboration_tools import SPACE_AGENT_REGISTRY
            mentions = []
            mentioned_agents = []
            for space_key in all_spaces:
                agent_info = SPACE_AGENT_REGISTRY.get(space_key)
                if agent_info:
                    agent_name = agent_info["name"]
                    mentions.append(f"@{agent_name}")
                    mentioned_agents.append(agent_name)

            full_content = f"{post_content}\n\n{' '.join(mentions)}"

            # -----------------------------------------------------------------
            # Step 3: Post to Minibook
            # -----------------------------------------------------------------
            project_id = self._client.project_id
            if not project_id:
                _debug_print("No Minibook project_id — cannot dispatch")
                return None

            try:
                post_data = self._client.create_post(
                    project_id=project_id,
                    content=full_content,
                    agent_name="vibemind_orchestrator",
                    post_type="task",
                    title=f"[{event_type}] {intent_text[:60]}",
                )
                post_id = post_data.get("id", "")
            except Exception as e:
                _debug_print(f"Minibook POST failed: {e}")
                return None

            _debug_print(f"Posted task {task_id} → post_id={post_id}")

            # -----------------------------------------------------------------
            # Step 4: Wait for results
            # -----------------------------------------------------------------
            if routing.is_multi_space:
                # ASYNC: Register for background polling
                await self._aggregator.track_multi(
                    post_id=post_id,
                    mentioned_agents=mentioned_agents,
                    original_request=intent_text,
                    task_id=task_id,
                )

                space_names = ", ".join(all_spaces)
                elapsed = time.time() - t0
                _debug_print(
                    f"Multi-space task dispatched to {space_names} "
                    f"({elapsed:.2f}s)"
                )

                # Return async acknowledgment
                return _make_result(
                    job_id=task_id,
                    event_type=event_type,
                    response_hint=(
                        f"Ich koordiniere das mit {space_names}. "
                        "Die Ergebnisse kommen gleich."
                    ),
                )

            else:
                # SYNC: Wait for the single agent's response
                primary_agent = mentioned_agents[0] if mentioned_agents else ""
                if not primary_agent:
                    return None

                result_text = await self._aggregator.wait_for_single(
                    post_id=post_id,
                    agent_name=primary_agent,
                    task_id=task_id,
                )

                if result_text is not None:
                    elapsed = time.time() - t0
                    _debug_print(
                        f"Single-space result from {primary_agent} "
                        f"in {elapsed:.2f}s"
                    )

                    return _make_result(
                        job_id=task_id,
                        event_type=event_type,
                        response_hint=result_text,
                    )

                else:
                    # Timeout — fall through to caller's fallback
                    _debug_print(
                        f"Sync-wait timeout for {primary_agent} — "
                        f"returning None for fallback"
                    )
                    self._rachel.timeout_task(task_id)
                    return None

        except Exception as e:
            _logger.error(f"MinibookHub.dispatch error: {e}")
            _debug_print(f"Dispatch error: {e}")
            return None

    # =========================================================================
    # Helpers
    # =========================================================================

    def _build_post_content(
        self,
        enriched_tasks: list,
        intent_text: str,
        event_type: str,
    ) -> str:
        """
        Build the Minibook post content with enriched task data.

        Format:
        - JSON block with structured enrichment data (for new enriched responders)
        - Human-readable fallback text (for legacy responders)
        """
        if enriched_tasks:
            # Enriched format: JSON payload that SpaceMinibookResponder can parse
            tasks_data = []
            for task in enriched_tasks:
                tasks_data.append({
                    "space_key": task.space_key,
                    "event_type": task.event_type,
                    "payload": task.payload,
                    "context": task.context,
                    "priority": task.priority,
                })

            enriched_json = json.dumps({
                "version": "2",
                "event_type": event_type,
                "tasks": tasks_data,
                "original_text": intent_text,
            }, ensure_ascii=False)

            return f"```enriched\n{enriched_json}\n```\n\nAufgabe: {intent_text}"

        else:
            # Fallback: plain text (existing format)
            return f"Aufgabe: {intent_text}"


# =============================================================================
# Helper: OrchestrationResult-compatible object
# =============================================================================

def _make_result(
    job_id: str,
    event_type: str,
    response_hint: str,
    stream: str = "minibook_hub",
    error: Optional[str] = None,
) -> Any:
    """
    Create an OrchestrationResult-compatible object.

    We use a simple namespace to avoid importing the full orchestrator module
    (which would create a circular dependency).
    """

    class _HubResult:
        def __init__(self):
            self.job_id = job_id
            self.event_type = event_type
            self.stream = stream
            self.response_hint = response_hint
            self.is_conversational = False
            self.error = error

        @property
        def success(self) -> bool:
            return self.error is None

    return _HubResult()


__all__ = ["MinibookHub"]
