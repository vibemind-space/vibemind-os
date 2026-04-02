# -*- coding: utf-8 -*-
"""
Fungus Memory Agent - Phase 18

Autonomous agent that runs memory-augmented MCMP simulation during epic
generation. Searches Supermemory alongside code files to discover correlations
between past experiences and current code via pheromone trails.

Event lifecycle:
    EPIC_EXECUTION_STARTED  -> Start service, index code, fetch memories
    EPIC_TASK_COMPLETED     -> Re-index files, run pattern recall if threshold met
    EPIC_TASK_FAILED        -> Run error fix recall to find applicable past fixes
    BUILD_FAILED / TYPE_ERROR -> Run error fix recall
    CODE_FIX_NEEDED         -> Enrich with memory context
    EPIC_EXECUTION_COMPLETED -> Run learning round, store patterns, final report

Publishes:
    FUNGUS_MEMORY_STARTED          -> Service initialized
    FUNGUS_MEMORY_CONTEXT_ENRICHED -> Task enriched with relevant memories
    FUNGUS_MEMORY_PATTERN_FOUND    -> Code<->memory correlation discovered
    FUNGUS_MEMORY_FIX_SUGGESTED    -> Past fix applicable to current error
    FUNGUS_MEMORY_STORED           -> New pattern stored to Supermemory
    FUNGUS_MEMORY_REPORT           -> Aggregated round summary
    FUNGUS_MEMORY_STOPPED          -> Service stopped, final stats
"""
import asyncio
from typing import Optional

import structlog

from ..mind.event_bus import EventBus, Event, EventType
from ..mind.shared_state import SharedState
from .autonomous_base import AutonomousAgent

logger = structlog.get_logger(__name__)


class FungusMemoryAgent(AutonomousAgent):
    """
    Autonomous memory-augmented MCMP agent.

    Uses Fungus MCMP simulation to discover correlations between Supermemory
    (past experiences) and current codebase during epic generation.
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: Optional[SharedState],
        working_dir: str,
        memory_interval: int = 10,
        min_files_for_search: int = 5,
        auto_enrich_threshold: float = 0.7,
        seed_queries: Optional[list] = None,
        **kwargs,
    ):
        super().__init__(
            name=name,
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
            **kwargs,
        )
        self._memory_interval = memory_interval
        self._min_files = min_files_for_search
        self._auto_enrich_threshold = auto_enrich_threshold
        self._seed_queries = seed_queries or []

        # Runtime state
        self._memory_service = None
        self._epic_active = False
        self._files_since_last_search = 0
        self._current_epic_id: Optional[str] = None

    # ------------------------------------------------------------------
    # AutonomousAgent interface
    # ------------------------------------------------------------------

    @property
    def subscribed_events(self) -> list:
        return [
            EventType.EPIC_EXECUTION_STARTED,
            EventType.EPIC_TASK_COMPLETED,
            EventType.EPIC_TASK_FAILED,
            EventType.EPIC_EXECUTION_COMPLETED,
            EventType.CODE_GENERATED,
            EventType.BUILD_FAILED,
            EventType.TYPE_ERROR,
            EventType.CODE_FIX_NEEDED,
        ]

    async def should_act(self, events: list) -> bool:
        """Act on any subscribed event."""
        return any(e.type in self.subscribed_events for e in events)

    async def act(self, events: list) -> Optional[Event]:
        """Process events and drive memory search."""
        for event in events:
            if event.source == self.name:
                continue  # Skip own events

            try:
                if event.type == EventType.EPIC_EXECUTION_STARTED:
                    await self._handle_epic_start(event)
                elif event.type == EventType.EPIC_TASK_COMPLETED:
                    await self._handle_task_completed(event)
                elif event.type == EventType.EPIC_TASK_FAILED:
                    await self._handle_task_failed(event)
                elif event.type == EventType.CODE_GENERATED:
                    await self._handle_code_generated(event)
                elif event.type in (EventType.BUILD_FAILED, EventType.TYPE_ERROR):
                    await self._handle_error_event(event)
                elif event.type == EventType.CODE_FIX_NEEDED:
                    await self._handle_code_fix_needed(event)
                elif event.type == EventType.EPIC_EXECUTION_COMPLETED:
                    await self._handle_epic_end(event)
            except Exception as e:
                self.logger.warning(
                    "event_handling_error",
                    event_type=event.type.value if hasattr(event.type, "value") else str(event.type),
                    error=str(e),
                )

        return None

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------

    async def _handle_epic_start(self, event: Event) -> None:
        """Start memory service when an epic begins."""
        if self._epic_active:
            self.logger.warning("epic_already_active", current=self._current_epic_id)
            return

        from ..services.fungus_memory_service import FungusMemoryService

        epic_id = event.data.get("epic_id", "unknown")
        self._current_epic_id = epic_id

        self._memory_service = FungusMemoryService(
            working_dir=self.working_dir,
            event_bus=self.event_bus,
            job_id=f"memory_{epic_id}",
        )

        started = await self._memory_service.start(
            seed_queries=self._seed_queries,
        )

        if started:
            self._epic_active = True
            self._files_since_last_search = 0

            await self.event_bus.publish(Event(
                type=EventType.FUNGUS_MEMORY_STARTED,
                source=self.name,
                data={
                    "epic_id": epic_id,
                    "files_indexed": self._memory_service.indexed_count,
                    "memories_loaded": self._memory_service.memory_count,
                },
            ))

            self.logger.info(
                "memory_started",
                epic_id=epic_id,
                files_indexed=self._memory_service.indexed_count,
                memories_loaded=self._memory_service.memory_count,
            )
        else:
            self.logger.warning("memory_start_failed", epic_id=epic_id)
            self._memory_service = None

    async def _handle_task_completed(self, event: Event) -> None:
        """On task completion, re-index and optionally run pattern recall."""
        if not self._memory_service or not self._epic_active:
            return

        task_data = event.data or {}

        # Re-index files from this task
        files_created = task_data.get("files_created", [])
        files_modified = task_data.get("files_modified", [])
        output_files = task_data.get("output_files", [])

        changed_count = 0
        for f in files_created + files_modified + output_files:
            if await self._memory_service.reindex_file(f):
                changed_count += 1

        self._files_since_last_search += max(1, changed_count)

        # Run pattern recall if threshold met
        if self._files_since_last_search >= self._memory_interval:
            task_title = task_data.get("title", task_data.get("task_id", ""))
            task_type = task_data.get("type", "")

            from ..services.fungus_memory_service import MemoryJudgeMode

            query = f"recall patterns for {task_type}: {task_title}"
            await self._run_and_publish_memory(
                focus_query=query,
                mode=MemoryJudgeMode.PATTERN_RECALL,
                task_context=task_data,
            )
            self._files_since_last_search = 0

    async def _handle_task_failed(self, event: Event) -> None:
        """On task failure, run error fix recall."""
        if not self._memory_service or not self._epic_active:
            return

        task_data = event.data or {}
        error_msg = task_data.get("error_message", task_data.get("error", ""))
        task_type = task_data.get("type", "")

        from ..services.fungus_memory_service import MemoryJudgeMode

        query = f"find fix for {task_type} error: {error_msg[:200]}"
        await self._run_and_publish_memory(
            focus_query=query,
            mode=MemoryJudgeMode.ERROR_FIX_RECALL,
            task_context=task_data,
        )

    async def _handle_code_generated(self, event: Event) -> None:
        """On code generation, re-index generated files."""
        if not self._memory_service or not self._epic_active:
            return

        files = event.data.get("files", [])
        for f in files:
            if isinstance(f, str):
                if await self._memory_service.reindex_file(f):
                    self._files_since_last_search += 1

    async def _handle_error_event(self, event: Event) -> None:
        """On BUILD_FAILED/TYPE_ERROR, run error fix recall."""
        if not self._memory_service or not self._epic_active:
            return

        error_msg = event.error_message or event.data.get("message", "")

        from ..services.fungus_memory_service import MemoryJudgeMode

        query = f"find fix for error: {error_msg[:200]}"
        await self._run_and_publish_memory(
            focus_query=query,
            mode=MemoryJudgeMode.ERROR_FIX_RECALL,
        )

    async def _handle_code_fix_needed(self, event: Event) -> None:
        """On CODE_FIX_NEEDED, enrich with memory context."""
        if not self._memory_service or not self._epic_active:
            return

        description = event.data.get("description", "")
        file_path = event.data.get("file_path", event.file_path or "")

        from ..services.fungus_memory_service import MemoryJudgeMode

        query = f"context for fixing {file_path}: {description[:200]}"
        await self._run_and_publish_memory(
            focus_query=query,
            mode=MemoryJudgeMode.CONTEXT_ENRICHMENT,
            task_context=event.data,
        )

    async def _handle_epic_end(self, event: Event) -> None:
        """Stop memory service when epic completes."""
        if not self._memory_service:
            return

        # Run learning round to discover storable patterns
        from ..services.fungus_memory_service import MemoryJudgeMode

        learning_report = await self._memory_service.run_memory_round(
            focus_query="identify new patterns worth remembering from this project",
            mode=MemoryJudgeMode.LEARNING,
        )

        # Store accumulated patterns to Supermemory
        stored = await self._memory_service.store_pending_patterns()

        if stored > 0:
            await self.event_bus.publish(Event(
                type=EventType.FUNGUS_MEMORY_STORED,
                source=self.name,
                data={
                    "epic_id": self._current_epic_id,
                    "patterns_stored": stored,
                },
            ))

        reports = await self._memory_service.stop()

        total_correlations = sum(len(r.correlations) for r in reports)

        await self.event_bus.publish(Event(
            type=EventType.FUNGUS_MEMORY_STOPPED,
            source=self.name,
            data={
                "epic_id": self._current_epic_id,
                "total_rounds": len(reports),
                "total_correlations": total_correlations,
                "patterns_stored": stored,
            },
        ))

        self.logger.info(
            "memory_stopped",
            epic_id=self._current_epic_id,
            rounds=len(reports),
            total_correlations=total_correlations,
            patterns_stored=stored,
        )

        self._epic_active = False
        self._memory_service = None
        self._current_epic_id = None

    # ------------------------------------------------------------------
    # Internal: Memory Search + Event Publishing
    # ------------------------------------------------------------------

    async def _run_and_publish_memory(
        self,
        focus_query: str,
        mode=None,
        task_context: Optional[dict] = None,
    ) -> None:
        """Run a memory round and publish results as events."""
        if not self._memory_service:
            return

        from ..services.fungus_memory_service import MemoryJudgeMode

        if mode is None:
            mode = MemoryJudgeMode.PATTERN_RECALL

        report = await self._memory_service.run_memory_round(
            focus_query=focus_query,
            mode=mode,
            task_context=task_context,
        )

        # Publish individual correlations
        for corr in report.correlations:
            if mode == MemoryJudgeMode.ERROR_FIX_RECALL and corr.correlation_type == "applicable_fix":
                # Publish as fix suggestion
                await self.event_bus.publish(Event(
                    type=EventType.FUNGUS_MEMORY_FIX_SUGGESTED,
                    source=self.name,
                    data={
                        "memory_id": corr.memory_id,
                        "memory_category": corr.memory_category,
                        "related_code_files": corr.related_code_files,
                        "description": corr.description,
                        "suggested_action": corr.suggested_action,
                        "relevance_score": corr.relevance_score,
                    },
                ))
            elif mode == MemoryJudgeMode.CONTEXT_ENRICHMENT:
                # Publish as context enrichment
                await self.event_bus.publish(Event(
                    type=EventType.FUNGUS_MEMORY_CONTEXT_ENRICHED,
                    source=self.name,
                    data={
                        "memory_id": corr.memory_id,
                        "memory_category": corr.memory_category,
                        "related_code_files": corr.related_code_files,
                        "description": corr.description,
                        "suggested_action": corr.suggested_action,
                        "relevance_score": corr.relevance_score,
                    },
                ))
            else:
                # Publish as pattern found
                await self.event_bus.publish(Event(
                    type=EventType.FUNGUS_MEMORY_PATTERN_FOUND,
                    source=self.name,
                    data={
                        "memory_id": corr.memory_id,
                        "memory_category": corr.memory_category,
                        "correlation_type": corr.correlation_type,
                        "related_code_files": corr.related_code_files,
                        "description": corr.description,
                        "relevance_score": corr.relevance_score,
                    },
                ))

        # Publish aggregated report
        await self.event_bus.publish(Event(
            type=EventType.FUNGUS_MEMORY_REPORT,
            source=self.name,
            data={
                "round": report.round_number,
                "correlations_count": len(report.correlations),
                "memories_searched": report.memories_searched,
                "code_files_analyzed": report.code_files_analyzed,
                "new_patterns_found": report.new_patterns_found,
                "focus_query": report.focus_query,
            },
        ))
