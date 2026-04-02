"""
Autonomous Agent Base - Foundation for self-directing agents.

Autonomous agents:
- Subscribe to relevant events from the event bus
- Decide when to act based on events and state
- Publish results back to the event bus
- Run in a continuous loop until convergence
"""

import asyncio
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING
import structlog
import hashlib

from ..mind.event_bus import (
    EventBus, Event, EventType, agent_event,
    file_created_event,
    test_suite_complete_event,
    build_succeeded_event,
    build_failed_event,
    type_check_passed_event,
    type_error_event,
    code_fixed_event,
    system_error_event,
)
from ..mind.event_payloads import TypeErrorPayload  # Phase 3: Rich error extraction
from ..mind.shared_state import SharedState
from ..mind.escalation_manager import EscalationManager, EscalationLevel
from ..mind.confidence_estimator import ConfidenceEstimator
from ..mind.session_memory import SessionMemory
from ..mind.fix_voter import (
    FixVoter, ProposedFix, ErrorContext as VoterErrorContext, VotingMethod
)
from ..config import get_settings
from ..utils.classification_cache import (
    get_classification_cache,
    ClassificationResult,
    ClassificationSource,
)

if TYPE_CHECKING:
    from ..mind.convergence import ConvergenceCriteria
    from ..skills.skill import Skill
    from ..skills.dynamic_skill_generator import DynamicSkillGenerator, GeneratedSkill
    from ..engine.agent_context_bridge import AgentContextBridge, MergedContext

from .autogen_team_mixin import AutogenTeamMixin

logger = structlog.get_logger(__name__)


# Push Architecture Constants
QUEUE_TIMEOUT = 5.0  # Seconds to wait for event before checking stop flag
EVENT_BATCH_WINDOW = 0.5  # Seconds to batch events before processing


@dataclass
class ErrorGroup:
    """Group of related errors for batch fixing."""
    group_type: str  # "type_error", "build_error", "test_failure", etc.
    file_pattern: Optional[str] = None  # Common file pattern if errors share files
    errors: list[dict] = field(default_factory=list)
    priority: int = 0  # Higher priority = fix first
    
    def add_error(self, error: dict) -> None:
        """Add error to group."""
        self.errors.append(error)
    
    @property
    def error_count(self) -> int:
        return len(self.errors)
    
    def get_error_summary(self) -> str:
        """Get summary of errors in this group."""
        files = set(e.get("file") for e in self.errors if e.get("file"))
        return f"{self.group_type}: {self.error_count} errors in {len(files)} files"


@dataclass
class BatchFixResult:
    """Result of a batch fix operation."""
    group_type: str
    attempted: int
    fixed: int
    files_modified: list[str]
    remaining_errors: list[dict]
    duration_seconds: float


class FixerPool:
    """Pool for parallel batch fixing with semaphore limiting."""
    
    def __init__(self, max_concurrent: int = 3, working_dir: str = "."):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._working_dir = working_dir
        self._logger = logger.bind(component="FixerPool")
    
    async def fix_group(self, group: ErrorGroup) -> BatchFixResult:
        """Fix a single error group with semaphore limiting."""
        import time
        from ..tools.claude_code_tool import ClaudeCodeTool
        
        start_time = time.time()
        
        async with self._semaphore:
            self._logger.info(
                "fixing_group",
                group_type=group.group_type,
                error_count=group.error_count,
            )
            
            # Build error description for this group
            errors_text = "\n\n".join([
                f"File: {e.get('file', 'Unknown')}\n"
                f"Line: {e.get('line', 'Unknown')}\n"
                f"Code: {e.get('code', '')}\n"
                f"Message: {e.get('message', 'Unknown error')}"
                for e in group.errors[:30]  # Phase 3: Limit errors
            ])
            
            prompt = self._build_group_prompt(group, errors_text)
            
            try:
                tool = ClaudeCodeTool(working_dir=self._working_dir, timeout=180)
                result = await tool.execute(
                    prompt=prompt,
                    context=f"Batch fixing {group.error_count} {group.group_type} errors",
                    agent_type="fixer",
                )
                
                duration = time.time() - start_time
                
                if result.success and result.files:
                    return BatchFixResult(
                        group_type=group.group_type,
                        attempted=group.error_count,
                        fixed=group.error_count,
                        files_modified=result.files,
                        remaining_errors=[],
                        duration_seconds=duration,
                    )
                else:
                    return BatchFixResult(
                        group_type=group.group_type,
                        attempted=group.error_count,
                        fixed=0,
                        files_modified=[],
                        remaining_errors=group.errors,
                        duration_seconds=duration,
                    )
                    
            except Exception as e:
                self._logger.error("group_fix_failed", error=str(e))
                return BatchFixResult(
                    group_type=group.group_type,
                    attempted=group.error_count,
                    fixed=0,
                    files_modified=[],
                    remaining_errors=group.errors,
                    duration_seconds=time.time() - start_time,
                )
    
    def _build_group_prompt(self, group: ErrorGroup, errors_text: str) -> str:
        """Build specialized prompt based on error group type."""
        type_instructions = {
            "type_error": "Fix TypeScript/type errors. Ensure proper type definitions and imports.",
            "build_error": "Fix build/compilation errors. Check imports and dependencies.",
            "test_failure": "Fix failing tests. Analyze test expectations and code behavior.",
            "missing_file": "Create missing files with appropriate content.",
            "import_error": "Fix import/dependency errors. Check paths and packages.",
        }
        
        instructions = type_instructions.get(group.group_type, "Analyze and fix errors.")
        
        return f"""Fix the following {group.group_type} errors:

{errors_text}

Instructions: {instructions}
"""
    
    async def fix_batch(self, groups: list[ErrorGroup], parallel: bool = True) -> list[BatchFixResult]:
        """Fix multiple error groups, optionally in parallel."""
        if not groups:
            return []
        
        sorted_groups = sorted(groups, key=lambda g: g.priority, reverse=True)
        
        if parallel and len(sorted_groups) > 1:
            self._logger.info("parallel_batch_fix", group_count=len(sorted_groups))
            tasks = [self.fix_group(g) for g in sorted_groups]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            final_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    final_results.append(BatchFixResult(
                        group_type=sorted_groups[i].group_type,
                        attempted=sorted_groups[i].error_count,
                        fixed=0,
                        files_modified=[],
                        remaining_errors=sorted_groups[i].errors,
                        duration_seconds=0,
                    ))
                else:
                    final_results.append(result)
            return final_results
        else:
            results = []
            for group in sorted_groups:
                result = await self.fix_group(group)
                results.append(result)
            return results


@dataclass
class AgentStatus:
    """Current status of an autonomous agent."""
    name: str
    running: bool = False
    paused: bool = False
    last_action: Optional[str] = None
    last_action_time: Optional[datetime] = None
    actions_taken: int = 0
    errors_encountered: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "running": self.running,
            "paused": self.paused,
            "last_action": self.last_action,
            "last_action_time": self.last_action_time.isoformat() if self.last_action_time else None,
            "actions_taken": self.actions_taken,
            "errors_encountered": self.errors_encountered,
        }


class AutonomousAgent(ABC):
    """
    Base class for autonomous agents in the Society of Mind.

    Agents run in a continuous loop, reacting to events and taking
    actions until the system converges.
    
    ARCHITECTURE: Push-based (v2.0)
    - Uses asyncio.Queue for event delivery instead of polling
    - Agents wake up immediately when events arrive
    - Supports event batching for efficiency

    Subclasses must implement:
    - subscribed_events: Which events to listen to
    - should_act: Decision logic for when to act
    - act: The actual work to perform
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        poll_interval: float = 1.0,  # Kept for backwards compatibility
        memory_tool: Optional[Any] = None,
        use_push_architecture: bool = True,  # NEW: Enable push-based architecture
        skill_generator: Optional["DynamicSkillGenerator"] = None,  # Dynamic skill gen
        context_bridge: Optional["AgentContextBridge"] = None,  # Context delivery
    ):
        """
        Initialize the autonomous agent.

        Args:
            name: Unique name for this agent
            event_bus: The event bus for communication
            shared_state: Shared state for convergence tracking
            working_dir: Working directory for file operations
            poll_interval: Seconds between event checks (legacy, only used if push disabled)
            memory_tool: Optional memory tool for learning/storing patterns
            use_push_architecture: Use push-based event delivery (default: True)
            skill_generator: Optional DynamicSkillGenerator for on-demand skill creation
            context_bridge: Optional AgentContextBridge for rich context delivery
        """
        self.name = name
        self.event_bus = event_bus
        self.shared_state = shared_state
        self.working_dir = working_dir
        self.poll_interval = poll_interval
        self.memory_tool = memory_tool
        self.use_push_architecture = use_push_architecture
        self.skill_generator = skill_generator
        self.context_bridge = context_bridge

        # Skill injection - populated by Orchestrator._inject_skills_to_agents()
        self.skill: Optional["Skill"] = None

        # Dynamic skill - generated on-demand before act()
        self._dynamic_skill: Optional["GeneratedSkill"] = None

        self._status = AgentStatus(name=name)
        self._pending_events: list[Event] = []
        self._should_stop = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        # NEW: Push architecture - async queue for event delivery
        self._event_queue: asyncio.Queue[Event] = asyncio.Queue()
        self._batch_events: list[Event] = []
        self._last_batch_time: float = 0

        self.logger = logger.bind(agent=name)

        # Subscribe to events
        for event_type in self.subscribed_events:
            self.event_bus.subscribe(event_type, self._handle_event)

    @property
    @abstractmethod
    def subscribed_events(self) -> list[EventType]:
        """Event types this agent listens to."""
        pass

    @abstractmethod
    async def should_act(self, events: list[Event]) -> bool:
        """
        Decide whether to take action based on recent events.

        Args:
            events: Recent events matching subscriptions

        Returns:
            True if the agent should act now
        """
        pass

    @abstractmethod
    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Perform the agent's work.

        Args:
            events: Events that triggered this action

        Returns:
            Event describing the result (or None)
        """
        pass

    @property
    def status(self) -> AgentStatus:
        """Get current agent status."""
        return self._status

    @property
    def tool_registry(self):
        """Lazy-loaded MCPToolRegistry for centralized tool execution."""
        if not hasattr(self, '_tool_registry') or self._tool_registry is None:
            from ..mcp.tool_registry import get_tool_registry
            self._tool_registry = get_tool_registry()
        return self._tool_registry

    async def call_tool(self, tool_name: str, **kwargs) -> dict:
        """
        Call an MCP tool asynchronously with auto-cwd and JSON parsing.

        Wraps the synchronous MCPToolRegistry.call_tool() in asyncio.to_thread()
        to avoid blocking the event loop.

        Args:
            tool_name: Full tool name (e.g., "docker.container_inspect", "npm.install")
            **kwargs: Tool arguments

        Returns:
            Parsed dict from JSON result, or {"error": "..."} on failure
        """
        if 'cwd' not in kwargs:
            kwargs['cwd'] = self.working_dir
        result_str = await asyncio.to_thread(
            self.tool_registry.call_tool, tool_name, **kwargs
        )
        try:
            return json.loads(result_str)
        except (json.JSONDecodeError, TypeError):
            return {"result": result_str}

    # ===== Context Bridge Integration (Phase 2) =====

    async def get_task_context(
        self,
        query: Optional[str] = None,
        epic_id: Optional[str] = None,
        feature_id: Optional[str] = None,
    ) -> Optional["MergedContext"]:
        """
        Get context for current task using AgentContextBridge.

        This method bridges static context (RichContextProvider) with dynamic
        context (Fungus/RAG) to provide optimal context for agent tasks.

        Args:
            query: Optional search query for RAG (enhances context with code examples)
            epic_id: Optional epic ID to scope context
            feature_id: Optional feature ID to scope context

        Returns:
            MergedContext with diagrams, entities, design tokens, and RAG results,
            or None if no context_bridge is configured.
        """
        # Try direct context_bridge first, then fallback to shared_state
        bridge = self.context_bridge
        if not bridge and self.shared_state and hasattr(self.shared_state, "context_bridge"):
            bridge = self.shared_state.context_bridge

        if not bridge:
            self.logger.debug("no_context_bridge_configured", agent=self.name)
            return None

        task_type = self._get_task_type()
        self.logger.info(
            "getting_task_context",
            agent=self.name,
            task_type=task_type,
            query=query[:50] if query else None,
        )

        try:
            context = await bridge.get_context_for_task(
                task_type=task_type,
                query=query,
                epic_id=epic_id,
                feature_id=feature_id,
            )
            self.logger.info(
                "task_context_retrieved",
                agent=self.name,
                diagrams_count=len(context.diagrams) if context else 0,
                entities_count=len(context.entities) if context else 0,
                rag_results_count=len(context.rag_results) if context else 0,
            )
            return context
        except Exception as e:
            self.logger.warning(
                "task_context_error",
                agent=self.name,
                error=str(e),
            )
            return None

    def _get_task_type(self) -> str:
        """
        Get the task type for this agent.

        Override in subclass to specify the task type for context retrieval.
        Common types: "database", "api", "frontend", "auth", "infra", "testing"

        Returns:
            Task type string used by AgentContextBridge
        """
        return "generic"

    def _format_context_for_prompt(
        self,
        context: Optional["MergedContext"],
        max_diagrams: int = 3,
        max_entities: int = 10,
        max_rag_results: int = 5,
    ) -> str:
        """
        Format MergedContext as a prompt-friendly string.

        Args:
            context: MergedContext from get_task_context()
            max_diagrams: Maximum diagrams to include
            max_entities: Maximum entities to include
            max_rag_results: Maximum RAG results to include

        Returns:
            Formatted context string for injection into prompts
        """
        if not context:
            return ""

        return context.get_prompt_context(
            max_diagrams=max_diagrams,
            max_entities=max_entities,
            max_rag_results=max_rag_results,
        )

    # ===== End Context Bridge Integration =====

    def _handle_event(self, event: Event) -> None:
        """Handle incoming events (callback from event bus)."""
        # Don't process our own events
        if event.source == self.name:
            return
        
        if self.use_push_architecture:
            # Push architecture: Add to async queue for immediate processing
            try:
                self._event_queue.put_nowait(event)
            except asyncio.QueueFull:
                self.logger.warning("event_queue_full", event_type=event.type.value)
        else:
            # Legacy: Add to pending list for polling
            self._pending_events.append(event)

    async def _collect_batched_events(self, timeout: float = QUEUE_TIMEOUT) -> list[Event]:
        """
        Collect events from queue with batching support.
        
        Waits for first event, then collects additional events
        within EVENT_BATCH_WINDOW for batch processing.
        
        Args:
            timeout: Maximum time to wait for first event
            
        Returns:
            List of batched events
        """
        events = []
        
        try:
            # Wait for first event
            first_event = await asyncio.wait_for(
                self._event_queue.get(),
                timeout=timeout
            )
            events.append(first_event)
            
            # Collect more events within batch window
            batch_deadline = asyncio.get_event_loop().time() + EVENT_BATCH_WINDOW
            while asyncio.get_event_loop().time() < batch_deadline:
                try:
                    event = await asyncio.wait_for(
                        self._event_queue.get(),
                        timeout=batch_deadline - asyncio.get_event_loop().time()
                    )
                    events.append(event)
                except asyncio.TimeoutError:
                    break
                    
        except asyncio.TimeoutError:
            pass  # No events within timeout, return empty list
            
        return events

    async def _run_loop(self) -> None:
        """
        Main agent loop - PUSH-BASED ARCHITECTURE.

        Instead of polling with sleep, waits on async queue for events.
        This eliminates CPU waste and provides immediate response.
        """
        import time

        self._status.running = True
        await self.event_bus.publish(agent_event(
            self.name,
            EventType.AGENT_STARTED,
        ))

        # Enhanced startup logging
        self.logger.info(
            "🤖 AGENT_STARTED",
            agent=self.name,
            architecture="push" if self.use_push_architecture else "poll",
            subscribed_events=[e.value for e in self.subscribed_events],
            has_skill=self.skill is not None,
        )

        try:
            while not self._should_stop:
                if self._status.paused:
                    await asyncio.sleep(0.5)
                    continue

                # Get events based on architecture
                if self.use_push_architecture:
                    # PUSH: Wait for events from queue (no CPU waste)
                    events = await self._collect_batched_events(timeout=QUEUE_TIMEOUT)
                    # Diagnostic: Log when events are collected
                    if events:
                        self.logger.debug(
                            "📦 EVENTS_COLLECTED",
                            agent=self.name,
                            count=len(events),
                            types=[e.type.value for e in events[:5]],
                        )
                else:
                    # LEGACY POLL: Check pending events
                    async with self._lock:
                        events = self._pending_events.copy()
                        self._pending_events.clear()
                    if not events:
                        await asyncio.sleep(self.poll_interval)
                        continue

                # Check if we should act (either from events or state)
                state_triggered = await self._should_act_on_state()
                if events or state_triggered:
                    try:
                        # If state triggered action OR events trigger action, proceed
                        should_act_result = False
                        if not state_triggered:
                            should_act_result = await self.should_act(events)
                            self.logger.debug(
                                "🤔 SHOULD_ACT_CHECKED",
                                agent=self.name,
                                event_count=len(events),
                                result=should_act_result,
                            )
                        if state_triggered or should_act_result:
                            # Log action start with trigger details
                            trigger_events = [e.type.value for e in events] if events else ["state_triggered"]
                            self.logger.info(
                                "AGENT_ACTING",
                                agent=self.name,
                                trigger_events=trigger_events,
                                trigger_sources=list(set(e.source for e in events)) if events else [],
                                action=self._get_action_description(),
                            )

                            # Announce we're acting
                            await self.event_bus.publish(agent_event(
                                self.name,
                                EventType.AGENT_ACTING,
                                action=self._get_action_description(),
                            ))

                            # Prepare dynamic skill before acting (if generator available)
                            await self._prepare_skill(events)

                            # Do the work with timing
                            action_start = time.time()
                            result = await self.act(events)
                            action_duration_ms = int((time.time() - action_start) * 1000)

                            # Update status
                            self._status.actions_taken += 1
                            self._status.last_action = self._get_action_description()
                            self._status.last_action_time = datetime.now()

                            # Log action completion
                            self.logger.info(
                                "AGENT_ACTION_COMPLETE",
                                agent=self.name,
                                result_event=result.type.value if result else "None",
                                result_success=result.success if result else None,
                                duration_ms=action_duration_ms,
                                total_actions=self._status.actions_taken,
                            )

                            # Publish result if any
                            if result:
                                await self.event_bus.publish(result)

                    except Exception as e:
                        self._status.errors_encountered += 1
                        self.logger.error(
                            "AGENT_ERROR",
                            agent=self.name,
                            error=str(e),
                            error_count=self._status.errors_encountered,
                        )
                        await self.event_bus.publish(agent_event(
                            self.name,
                            EventType.AGENT_ERROR,
                            error=str(e),
                        ))

        finally:
            self._status.running = False
            await self.event_bus.publish(agent_event(
                self.name,
                EventType.AGENT_COMPLETED,
                actions_taken=self._status.actions_taken,
            ))
            self.logger.info(
                "AGENT_STOPPED",
                agent=self.name,
                actions_taken=self._status.actions_taken,
                errors_encountered=self._status.errors_encountered,
            )

    async def _should_act_on_state(self) -> bool:
        """
        Check if agent should act based on current state (not events).

        Override in subclasses for state-triggered actions.
        """
        return False

    def _get_action_description(self) -> str:
        """Get a description of the current action."""
        return f"{self.name} action"

    async def start(self) -> None:
        """Start the agent's main loop."""
        if self._task and not self._task.done():
            self.logger.warning("agent_already_running")
            return

        self._should_stop = False
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the agent gracefully."""
        self._should_stop = True
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                # Task was cancelled during wait_for
                pass

    def pause(self) -> None:
        """Pause the agent temporarily."""
        self._status.paused = True
        self.logger.info("agent_paused")

    def resume(self) -> None:
        """Resume a paused agent."""
        self._status.paused = False
        self.logger.info("agent_resumed")

    # =========================================================================
    # SKILL INTEGRATION - Progressive Disclosure Pattern
    # =========================================================================

    def get_skill_instructions(self) -> str:
        """
        Get full skill instructions for prompt enrichment.

        Returns the complete instructions from either:
        1. Dynamically generated skill (preferred if available)
        2. Static injected skill
        3. Empty string if no skill is assigned

        Token Impact: ~3-5k tokens when skill is activated
        """
        # Prefer dynamic skill if available
        if self._dynamic_skill:
            return self._dynamic_skill.instructions
        if self.skill:
            return self.skill.instructions
        return ""

    def get_skill_metadata_prompt(self) -> str:
        """
        Get minimal skill metadata for context (low token count).

        Returns only name and description, not full instructions.

        Token Impact: ~100 tokens
        """
        if self.skill:
            return self.skill.get_metadata_prompt()
        return ""

    def build_enriched_prompt(self, base_prompt: str) -> str:
        """
        Combine skill instructions with base prompt for LLM call.

        This is the key method for progressive disclosure - skill
        instructions are only included when the agent actually acts,
        not when idle.

        Args:
            base_prompt: The task-specific prompt

        Returns:
            Enriched prompt with skill context prepended

        Token Impact: ~3-5k tokens added from skill instructions
        """
        if not self.skill:
            return base_prompt

        return f"""## Skill: {self.skill.name}
{self.skill.description}

---

{self.skill.instructions}

---

## Current Task

{base_prompt}
"""

    def has_skill(self) -> bool:
        """Check if this agent has a skill assigned."""
        return self.skill is not None or self._dynamic_skill is not None

    def get_skill_name(self) -> Optional[str]:
        """Get the name of the assigned skill, if any."""
        if self._dynamic_skill:
            return self._dynamic_skill.name
        return self.skill.name if self.skill else None

    # =========================================================================
    # DYNAMIC SKILL GENERATION - On-demand skill creation via LLM
    # =========================================================================

    async def _prepare_skill(self, events: list[Event]) -> None:
        """
        Generate a dynamic skill before act() if skill_generator is available.

        This method is called automatically before act() to ensure the agent
        has appropriate skill context for the task at hand.

        The generated skill is cached for the session and reused for similar
        task contexts.
        """
        if not self.skill_generator:
            return

        # If we already have a static skill, prefer it
        if self.skill:
            return

        try:
            # Infer task type from events and agent context
            task_type = self._infer_task_type(events)
            if not task_type:
                return

            # Get tech stack from shared state
            tech_stack = {}
            if hasattr(self.shared_state, 'tech_stack') and self.shared_state.tech_stack:
                tech_stack = self.shared_state.tech_stack
            elif hasattr(self.shared_state, 'metrics') and hasattr(self.shared_state.metrics, 'tech_stack'):
                tech_stack = self.shared_state.metrics.tech_stack or {}

            # Extract relevant diagrams from events
            diagrams = self._extract_diagrams_from_events(events)

            # Extract requirements from events
            requirements = self._extract_requirements_from_events(events)

            # Generate the skill
            self._dynamic_skill = await self.skill_generator.generate(
                task_type=task_type,
                tech_stack=tech_stack,
                context_diagrams=diagrams,
                requirements=requirements,
            )

            self.logger.info(
                "dynamic_skill_generated",
                task_type=task_type,
                skill_name=self._dynamic_skill.name,
                tier=self._dynamic_skill.tier,
            )

        except Exception as e:
            self.logger.warning(
                "dynamic_skill_generation_failed",
                error=str(e),
                fallback="continuing without dynamic skill",
            )

    def _infer_task_type(self, events: list[Event]) -> Optional[str]:
        """
        Infer the task type from events for dynamic skill generation.

        Returns a task type string that maps to skill generator templates,
        or None if no suitable task type can be inferred.
        """
        # Map agent name patterns to task types
        agent_name_lower = self.name.lower()

        # Direct agent-to-task mapping
        agent_task_map = {
            "database": "database_schema",
            "api": "nestjs_controller",
            "auth": "nestjs_guard",
            "websocket": "nestjs_websocket",
            "redis": "redis_integration",
            "generator": "react_component",
            "frontend": "react_component",
            "tester": "vitest_test",
            "validation": "vitest_test",
            "fixer": "typescript_fix",
            "builder": "typescript_fix",
        }

        for pattern, task_type in agent_task_map.items():
            if pattern in agent_name_lower:
                return task_type

        # Infer from event types if agent name doesn't match
        for event in events:
            if event.type == EventType.DATABASE_SCHEMA_GENERATED:
                return "nestjs_controller"
            if event.type == EventType.API_ROUTES_GENERATED:
                return "nestjs_websocket"
            if event.type == EventType.CONTRACTS_GENERATED:
                return "database_schema"
            if event.type in (EventType.BUILD_FAILED, EventType.TYPE_ERROR):
                return "typescript_fix"
            if event.type == EventType.TEST_FAILED:
                return "vitest_test"

        return None

    def _extract_diagrams_from_events(self, events: list[Event]) -> list[dict]:
        """Extract relevant Mermaid diagrams from event data."""
        diagrams = []
        for event in events:
            if event.data:
                # Look for diagrams in event data
                if "diagrams" in event.data:
                    diagrams.extend(event.data["diagrams"])
                if "context" in event.data and isinstance(event.data["context"], dict):
                    ctx_diagrams = event.data["context"].get("diagrams", [])
                    diagrams.extend(ctx_diagrams)
        return diagrams[:5]  # Limit to 5 diagrams to avoid token explosion

    def _extract_requirements_from_events(self, events: list[Event]) -> list[dict]:
        """Extract relevant requirements from event data."""
        requirements = []
        for event in events:
            if event.data:
                if "requirements" in event.data:
                    reqs = event.data["requirements"]
                    if isinstance(reqs, list):
                        requirements.extend(reqs)
                if "requirement_ids" in event.data:
                    req_ids = event.data["requirement_ids"]
                    for req_id in req_ids:
                        requirements.append({"req_id": req_id})
        return requirements[:20]  # Limit to 20 requirements

    def get_dynamic_skill_instructions(self) -> str:
        """
        Get instructions from dynamically generated skill.

        Returns the instructions from the dynamic skill if available,
        or empty string if no dynamic skill was generated.
        """
        if self._dynamic_skill:
            return self._dynamic_skill.instructions
        return ""

    def build_enriched_prompt_with_dynamic_skill(self, base_prompt: str) -> str:
        """
        Build prompt enriched with dynamic skill instructions.

        This is an alternative to build_enriched_prompt() that uses
        the dynamically generated skill instead of the static one.

        Args:
            base_prompt: The task-specific prompt

        Returns:
            Enriched prompt with dynamic skill context prepended
        """
        # Prefer dynamic skill if available
        if self._dynamic_skill:
            return f"""## Dynamic Skill: {self._dynamic_skill.name}

{self._dynamic_skill.instructions}

---

## Current Task

{base_prompt}
"""
        # Fall back to static skill
        return self.build_enriched_prompt(base_prompt)


class TesterAgent(AutonomousAgent):
    """
    Agent that runs tests continuously.

    Triggers on:
    - Build success (primary trigger, waits for build before testing)
    - Code fixes (re-run tests after fixes)
    - Code generation complete
    
    OPTIMIZED: No longer subscribes to FILE_CREATED/FILE_MODIFIED
    to avoid redundant processing with Builder.
    """

    @property
    def subscribed_events(self) -> list[EventType]:
        # OPTIMIZED: Wait for build success instead of all file changes
        return [
            EventType.BUILD_SUCCEEDED,  # Primary trigger: test after build
            EventType.CODE_GENERATED,
            EventType.CODE_FIXED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        # Act on build success or code changes
        for event in events:
            # Check for initial trigger from orchestrator
            if event.data and event.data.get("trigger") == "initial":
                return True
            # Primary trigger: Build succeeded
            if event.type == EventType.BUILD_SUCCEEDED:
                return True
            # Code was fixed - re-run tests
            if event.type == EventType.CODE_FIXED and event.success:
                return True
            # Code was generated
            if event.type == EventType.CODE_GENERATED:
                return True
        return False

    async def _should_act_on_state(self) -> bool:
        """Run tests if none have been run yet."""
        metrics = self.shared_state.metrics
        return metrics.iteration == 1 and metrics.total_tests == 0

    async def act(self, events: list[Event]) -> Optional[Event]:
        """Run the test suite."""
        from ..tools.test_runner_tool import TestRunnerTool

        self.logger.info("running_tests")

        try:
            runner = TestRunnerTool(self.working_dir)
            result = await runner.execute()

            # Update shared state
            await self.shared_state.update_tests(
                total=result.total_tests,
                passed=result.passed,
                failed=result.failed,
                skipped=result.skipped,
            )

            # Return appropriate event
            if result.success:
                return test_suite_complete_event(
                    source=self.name,
                    success=True,
                    total=result.total_tests,
                    passed=result.passed,
                    failed=result.failed,
                )
            else:
                return test_suite_complete_event(
                    source=self.name,
                    success=False,
                    total=result.total_tests,
                    passed=result.passed,
                    failed=result.failed,
                    failures=[f.to_dict() for f in result.failures[:50]],  # Increased from 5 to 50
                )

        except Exception as e:
            self.logger.error("test_run_failed", error=str(e))
            return system_error_event(
                source=self.name,
                error_message=str(e),
            )

    def _get_action_description(self) -> str:
        return "Running test suite"


class BuilderAgent(AutonomousAgent):
    """
    Agent that monitors and runs builds.

    Triggers on:
    - Source file changes (FILE_CREATED, FILE_MODIFIED)
    - Code fixes
    - Dependency updates
    
    This is the PRIMARY agent for file change events.
    Other agents (Tester, Validator) wait for BUILD_SUCCEEDED.
    """

    @property
    def subscribed_events(self) -> list[EventType]:
        # Builder is the primary handler for file changes
        return [
            EventType.FILE_CREATED,
            EventType.FILE_MODIFIED,
            EventType.CODE_FIXED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        # Act on source file changes
        for event in events:
            # Check for initial trigger from orchestrator (FIX-B: also check bootstrap)
            if event.data and (
                event.data.get("trigger") == "initial" or
                event.data.get("bootstrap") == True
            ):
                return True
            if event.file_path:
                # Check for relevant file types
                if any(event.file_path.endswith(ext) for ext in [
                    '.ts', '.tsx', '.js', '.jsx', '.json', '.css', '.html'
                ]):
                    return True
        return False

    async def _should_act_on_state(self) -> bool:
        """Run build if not attempted yet."""
        metrics = self.shared_state.metrics
        return metrics.iteration == 1 and not metrics.build_attempted

    async def act(self, events: list[Event]) -> Optional[Event]:
        """Run the build."""
        from ..validators.build_validator import BuildValidator

        self.logger.info("running_build")

        try:
            validator = BuildValidator(self.working_dir)
            result = await validator.validate()

            # Update shared state
            await self.shared_state.update_build(
                attempted=True,
                success=result.passed,
                errors=result.error_count,
            )

            if result.passed:
                return build_succeeded_event(source=self.name)
            else:
                return build_failed_event(
                    source=self.name,
                    errors=[f.to_dict() for f in result.failures[:50]],  # Increased from 5 to 50
                )

        except Exception as e:
            self.logger.error("build_failed", error=str(e))
            await self.shared_state.update_build(attempted=True, success=False)
            return build_failed_event(
                source=self.name,
                errors=[{"message": str(e)}],
            )

    def _get_action_description(self) -> str:
        return "Running build"


class ValidatorAgent(AutonomousAgent):
    """
    Agent that runs validation checks (type checking, linting).

    Triggers on:
    - Build success (primary trigger, type-check after build)
    - Code fixes (re-validate after fixes)
    - Code generation complete
    
    OPTIMIZED: No longer subscribes to FILE_CREATED/FILE_MODIFIED
    to avoid redundant processing with Builder.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # FIX-H: Track which iteration we last did a state-triggered check
        self._last_state_check_iteration: int = -1

    @property
    def subscribed_events(self) -> list[EventType]:
        # OPTIMIZED: Wait for build success instead of all file changes
        return [
            EventType.BUILD_SUCCEEDED,  # Primary trigger: validate after build
            EventType.CODE_GENERATED,
            EventType.CODE_FIXED,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        for event in events:
            # Check for initial trigger from orchestrator
            if event.data and event.data.get("trigger") == "initial":
                return True
            # Primary trigger: Build succeeded
            if event.type == EventType.BUILD_SUCCEEDED:
                return True
            # Code was fixed - re-validate
            if event.type == EventType.CODE_FIXED and event.success:
                return True
            # Code was generated
            if event.type == EventType.CODE_GENERATED:
                return True
        return False

    async def _should_act_on_state(self) -> bool:
        """Run type check on first iteration ONLY after build has been attempted.
        
        FIX-H: Only trigger once per iteration to prevent spam loop.
        """
        metrics = self.shared_state.metrics
        # FIX-G: Don't spam type checks before build is attempted
        if not metrics.build_attempted:
            return False
        # FIX-H: Don't re-trigger if we already checked this iteration
        if self._last_state_check_iteration >= metrics.iteration:
            return False
        # Only on first iterations
        if metrics.iteration <= 1:
            # Mark this iteration as checked
            self._last_state_check_iteration = metrics.iteration
            return True
        return False

    async def act(self, events: list[Event]) -> Optional[Event]:
        """Run TypeScript type checking."""
        from ..validators.typescript_validator import TypeScriptValidator

        self.logger.info("running_type_check")

        try:
            validator = TypeScriptValidator(self.working_dir)
            result = await validator.validate()

            # Check for TOOL_NOT_FOUND errors (unfixable by code changes)
            tool_not_found = any(
                f.error_code == "TOOL_NOT_FOUND" 
                for f in result.failures
            )
            
            if tool_not_found:
                # Don't report as TYPE_ERROR - this is a system configuration issue
                self.logger.warning(
                    "validator_tool_not_found",
                    message="TypeScript compiler not available, skipping type checks"
                )
                # Mark as passed to avoid infinite loop (tool problem, not code problem)
                await self.shared_state.update_types(errors=0, warnings=0)
                return system_error_event(
                    source=self.name,
                    error_message="TypeScript tools not available (npm/npx not in PATH)",
                    error_type="TOOL_NOT_FOUND",
                    recoverable=False,
                    hint="Ensure Node.js is installed and npm/npx are in PATH",
                )

            # Update shared state
            await self.shared_state.update_types(
                errors=result.error_count,
                warnings=result.warning_count,
            )

            if result.passed:
                return type_check_passed_event(source=self.name)
            else:
                return type_error_event(
                    source=self.name,
                    tsc_output="\n".join(f.to_dict().get("message", "") for f in result.failures[:50]),  # Increased from 10 to 50
                )

        except Exception as e:
            self.logger.error("type_check_failed", error=str(e))
            return system_error_event(
                source=self.name,
                error_message=str(e),
            )

    def _get_action_description(self) -> str:
        return "Running type checks"


class FixerAgent(AutonomousAgent, AutogenTeamMixin):
    """
    Agent that attempts to fix errors using Claude Code Tool.

    Triggers on:
    - Test failures
    - Build failures
    - Type errors
    - Validation errors
    
    Uses ClaudeCodeTool for intelligent error analysis and fixing
    instead of hardcoded patterns. Supports batch fixing with error grouping.
    """

    def __init__(self, *args, tech_stack: Optional[Any] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._recent_fixes: dict[str, datetime] = {}
        self._fix_cooldown = 10  # CHANGED: Reduced from 30s to 10s for faster iteration
        self._fixer_pool: Optional[FixerPool] = None
        # FIX-28: Store tech_stack for technology-aware fixing
        self.tech_stack = tech_stack

        # Tier 1 Core Intelligence: Escalation, Confidence, and Session Learning
        self.escalation_manager = EscalationManager(
            shared_state=self.shared_state,
            event_bus=self.event_bus,
        )
        self.confidence_estimator = ConfidenceEstimator()
        self.session_memory = SessionMemory()

        # Phase 10: FixVoter for democratic fix selection
        settings = get_settings()
        self.voting_enabled = settings.voting_enabled
        if self.voting_enabled:
            self.fix_voter = FixVoter(
                working_dir=self.working_dir,
                voting_method=VotingMethod(settings.voting_default_method),
            )
        else:
            self.fix_voter = None

        # Classification cache for error type categorization with LLM fallback
        self._classification_cache = get_classification_cache()

        # Log tech_stack if present
        if tech_stack:
            self.logger.info(
                "fixer_tech_stack_configured",
                frontend=getattr(tech_stack, 'frontend_framework', None),
                backend=getattr(tech_stack, 'backend_framework', None),
            )

    def _get_fixer_pool(self) -> FixerPool:
        """Get or create the fixer pool."""
        if self._fixer_pool is None:
            self._fixer_pool = FixerPool(max_concurrent=3, working_dir=self.working_dir)
        return self._fixer_pool

    @property
    def subscribed_events(self) -> list[EventType]:
        return [
            EventType.TEST_FAILED,
            EventType.BUILD_FAILED,
            EventType.TYPE_ERROR,
            EventType.VALIDATION_ERROR,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        # Only act on error events that we haven't recently tried to fix
        for event in events:
            if not event.success:
                error_key = f"{event.type.value}:{event.error_message or 'unknown'}"
                last_fix = self._recent_fixes.get(error_key)
                if not last_fix or (datetime.now() - last_fix).seconds > self._fix_cooldown:
                    return True
        return False

    def _group_errors(self, error_context: list[dict]) -> list[ErrorGroup]:
        """Group errors by type and pattern for efficient batch fixing."""
        groups: dict[str, ErrorGroup] = {}
        
        # Priority mapping
        priority_map = {
            "type_error": 3,
            "build_error": 4,
            "test_failure": 2,
            "missing_file": 5,
            "import_error": 4,
        }
        
        for error in error_context:
            error_type = error.get("type", "unknown").lower()
            
            # Map event types to group types
            if "type" in error_type:
                group_type = "type_error"
            elif "build" in error_type:
                group_type = "build_error"
            elif "test" in error_type:
                group_type = "test_failure"
            elif "missing" in error.get("message", "").lower():
                group_type = "missing_file"
            elif "import" in error.get("message", "").lower():
                group_type = "import_error"
            else:
                group_type = "general"
            
            if group_type not in groups:
                groups[group_type] = ErrorGroup(
                    group_type=group_type,
                    priority=priority_map.get(group_type, 1),
                )
            
            groups[group_type].add_error(error)
        
        return list(groups.values())

    async def fix_batch(self, error_context: list[dict]) -> list[BatchFixResult]:
        """
        Fix errors in batches, grouped by type for efficiency.
        
        Args:
            error_context: List of error dicts with type, message, file, data
            
        Returns:
            List of BatchFixResults
        """
        if not error_context:
            return []
        
        # Group errors
        groups = self._group_errors(error_context)
        
        self.logger.info(
            "batch_fixing",
            total_errors=len(error_context),
            groups=len(groups),
            group_types=[g.group_type for g in groups],
        )
        
        # Use fixer pool for parallel fixing
        pool = self._get_fixer_pool()
        results = await pool.fix_batch(groups, parallel=len(groups) > 1)
        
        # Log results
        total_fixed = sum(r.fixed for r in results)
        total_files = sum(len(r.files_modified) for r in results)
        
        self.logger.info(
            "batch_fix_complete",
            attempted=len(error_context),
            fixed=total_fixed,
            files_modified=total_files,
        )
        
        return results

    async def act(self, events: list[Event]) -> Optional[Event]:
        """
        Attempt to fix errors. Dispatches to autogen team or legacy ClaudeCodeTool.
        """
        self.logger.info(
            "attempting_fixes",
            error_count=len(events),
            mode="autogen" if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true" else "legacy",
        )
        if self.is_autogen_available() and os.getenv("USE_AUTOGEN_TEAMS", "false").lower() == "true":
            return await self._act_with_autogen_team(events)
        return await self._act_legacy(events)

    async def _act_with_autogen_team(self, events: list[Event]) -> Optional[Event]:
        """
        Fix errors using autogen team: ErrorAnalyst + FixOperator + FixValidator.

        Preserves escalation, confidence estimation, session memory, and voting.
        """
        import hashlib

        # --- Reuse existing error collection logic ---
        error_context = []
        for event in events:
            if not event.success:
                if event.type == EventType.TYPE_ERROR and event.typed and isinstance(event.typed, TypeErrorPayload):
                    payload = event.typed
                    for file_path, file_errors in payload.errors_by_file.items():
                        for err in file_errors:
                            error_key = f"{event.type.value}:{file_path}:{err.get('line', '')}:{err.get('message', '')}"
                            error_hash = hashlib.md5(error_key.encode()).hexdigest()[:16]
                            is_stuck = await self.shared_state.record_error(error_hash)
                            if is_stuck:
                                continue
                            error_context.append({
                                "type": "type_error",
                                "message": err.get("message", "Unknown type error"),
                                "file": file_path,
                                "line": err.get("line"),
                                "code": err.get("code", ""),
                                "data": err,
                                "hash": error_hash,
                            })
                            self._recent_fixes[f"{event.type.value}:{file_path}:{err.get('message', '')}"] = datetime.now()
                    continue

                error_key = f"{event.type.value}:{event.file_path or ''}:{event.error_message or ''}"
                error_hash = hashlib.md5(error_key.encode()).hexdigest()[:16]
                is_stuck = await self.shared_state.record_error(error_hash)
                if is_stuck:
                    continue
                error_context.append({
                    "type": event.type.value,
                    "message": event.error_message or "Unknown error",
                    "file": event.file_path,
                    "line": None,
                    "code": "",
                    "data": event.data,
                    "hash": error_hash,
                })
                self._recent_fixes[f"{event.type.value}:{event.error_message}"] = datetime.now()

        if not error_context:
            return None

        # --- Escalation + Confidence (preserved) ---
        for error in error_context:
            error_type = await self._categorize_error_type(error["message"])
            self.escalation_manager.get_or_create_state(
                error_hash=error["hash"],
                error_type=error_type,
            )

        primary_error = error_context[0]
        error_type = await self._categorize_error_type(primary_error["message"])
        strategy = self.escalation_manager.get_current_strategy(primary_error["hash"])
        escalation_level = strategy.level if strategy else EscalationLevel.LLM_TARGETED

        confidence = self.confidence_estimator.estimate_confidence(
            error_type=error_type,
            error_message=primary_error["message"],
            escalation_level=escalation_level.value,
            context_files=[e["file"] for e in error_context if e.get("file")],
        )

        if self.confidence_estimator.should_seek_help(
            confidence.overall,
            self.escalation_manager.get_state(primary_error["hash"]).total_attempts
            if self.escalation_manager.get_state(primary_error["hash"])
            else 0,
        ):
            await self.escalation_manager.escalate(primary_error["hash"])
            return code_fixed_event(
                source=self.name,
                success=False,
                attempted=len(error_context),
                error="Low confidence - escalated to human review",
            )

        # --- Build task prompt for autogen team ---
        errors_text = "\n\n".join([
            f"Error Type: {e['type']}\n"
            f"File: {e['file'] or 'Unknown'}\n"
            f"Line: {e.get('line') or 'Unknown'}\n"
            f"Code: {e.get('code', '')}\n"
            f"Message: {e['message']}"
            for e in error_context[:30]
        ])

        # Session memory enhancement
        enhanced_prompt = self.session_memory.enhance_prompt(
            original_prompt=self._build_tech_aware_prompt(errors_text, len(error_context)),
            error_type=error_type,
            error_message=primary_error["message"],
        )

        # MCP context enhancement
        try:
            mcp_context = await self._build_enhanced_context(error_context)
            if mcp_context:
                enhanced_prompt += mcp_context
        except Exception:
            pass

        try:
            team = self.create_team(
                operator_name="ErrorAnalyst",
                operator_prompt=(
                    "You are an expert error analyst for TypeScript/React/Node projects. "
                    "Analyze build errors, type errors, test failures, and runtime errors. "
                    "Identify root causes and determine the best fix strategy. "
                    "Focus on the most critical errors first. "
                    "When you identify the fix, apply it by editing the relevant files. "
                    "After applying fixes, say TASK_COMPLETE."
                ),
                validator_name="FixValidator",
                validator_prompt=(
                    "You validate error fixes. Check that:\n"
                    "1. Root cause is properly addressed (not just symptoms)\n"
                    "2. Fix doesn't break other functionality\n"
                    "3. Type safety is maintained\n"
                    "4. No mocks or placeholders are introduced\n"
                    "5. Fix follows project coding style\n"
                    "If the fix is correct, say TASK_COMPLETE.\n"
                    "If issues remain, describe what needs to change."
                ),
                tool_categories=["filesystem", "npm", "git"],
                max_turns=20,
                task=enhanced_prompt,
            )

            result = await self.run_team(team, enhanced_prompt)

            if result["success"]:
                self.session_memory.record_fix(
                    error_type=error_type,
                    error_message=primary_error["message"],
                    fix_prompt=enhanced_prompt[:500],
                    fix_succeeded=True,
                    files_modified=[],
                    fix_approach="autogen-team fix",
                    escalation_level=escalation_level.value,
                    confidence_score=confidence.overall,
                )
                self.confidence_estimator.record_fix(
                    error_type=error_type,
                    error_message=primary_error["message"],
                    escalation_level=escalation_level.value,
                    success=True,
                    confidence_before=confidence.overall,
                )
                for error in error_context:
                    self.escalation_manager.clear_error_state(error["hash"])
                await self.shared_state.clear_stuck_state()

                return code_fixed_event(
                    source=self.name,
                    success=True,
                    attempted=len(error_context),
                    files_modified=0,
                )
            else:
                self.session_memory.record_fix(
                    error_type=error_type,
                    error_message=primary_error["message"],
                    fix_prompt=enhanced_prompt[:500],
                    fix_succeeded=False,
                    fix_approach="autogen-team fix",
                    escalation_level=escalation_level.value,
                    confidence_score=confidence.overall,
                )
                self.confidence_estimator.record_fix(
                    error_type=error_type,
                    error_message=primary_error["message"],
                    escalation_level=escalation_level.value,
                    success=False,
                    confidence_before=confidence.overall,
                )
                state = self.escalation_manager.get_state(primary_error["hash"])
                if state and state.should_escalate:
                    await self.escalation_manager.escalate(primary_error["hash"])

                return code_fixed_event(
                    source=self.name,
                    success=False,
                    attempted=len(error_context),
                    error=result.get("result_text", "Autogen team fix failed"),
                )

        except Exception as e:
            self.logger.error("autogen_fix_failed", error=str(e))
            return system_error_event(
                source=self.name,
                error_message=str(e),
            )

    async def _act_legacy(self, events: list[Event]) -> Optional[Event]:
        """
        Legacy: Attempt to fix errors using ClaudeCodeTool with progressive escalation.

        Uses Tier 1 Core Intelligence:
        - EscalationManager: Progressive fix strategies instead of giving up
        - ConfidenceEstimator: Know when to try harder vs. ask for help
        - SessionMemory: Learn from fixes within a session
        """
        from ..tools.claude_code_tool import ClaudeCodeTool
        import hashlib

        self.logger.info("attempting_fixes_legacy", error_count=len(events))

        # Collect all error messages
        error_context = []
        for event in events:
            if not event.success:
                # Phase 3 Fix 3: Extract rich TypeErrorPayload if available
                if event.type == EventType.TYPE_ERROR and event.typed and isinstance(event.typed, TypeErrorPayload):
                    payload = event.typed
                    self.logger.debug(
                        "extracting_type_error_payload",
                        error_count=payload.error_count,
                        files_with_errors=len(payload.errors_by_file),
                    )
                    # Extract structured errors from payload
                    for file_path, file_errors in payload.errors_by_file.items():
                        for err in file_errors:
                            # Phase 3 Fix 5: More specific hash including file and line
                            error_key = f"{event.type.value}:{file_path}:{err.get('line', '')}:{err.get('message', '')}"
                            error_hash = hashlib.md5(error_key.encode()).hexdigest()[:16]

                            is_stuck = await self.shared_state.record_error(error_hash)
                            if is_stuck:
                                continue

                            error_info = {
                                "type": "type_error",
                                "message": err.get("message", "Unknown type error"),
                                "file": file_path,
                                "line": err.get("line"),
                                "code": err.get("code", ""),
                                "data": err,
                                "hash": error_hash,
                            }
                            error_context.append(error_info)

                            error_key = f"{event.type.value}:{file_path}:{err.get('message', '')}"
                            self._recent_fixes[error_key] = datetime.now()
                    continue  # Skip fallback processing

                # Fallback: Original logic for non-TYPE_ERROR or events without typed payload
                # Phase 3 Fix 5: More specific hash including file_path
                error_key = f"{event.type.value}:{event.file_path or ''}:{event.error_message or ''}"
                error_hash = hashlib.md5(error_key.encode()).hexdigest()[:16]

                # Record error for deadlock detection
                is_stuck = await self.shared_state.record_error(error_hash)
                if is_stuck:
                    self.logger.warning(
                        "skipping_stuck_error",
                        error_type=event.type.value,
                        error_hash=error_hash,
                    )
                    continue

                error_info = {
                    "type": event.type.value,
                    "message": event.error_message or "Unknown error",
                    "file": event.file_path,
                    "line": None,  # Not available in fallback
                    "code": "",
                    "data": event.data,
                    "hash": error_hash,
                }
                error_context.append(error_info)

                # Mark as recently attempted
                error_key = f"{event.type.value}:{event.error_message}"
                self._recent_fixes[error_key] = datetime.now()

        if not error_context:
            return None

        # Get or create escalation state for each error
        for error in error_context:
            error_type = await self._categorize_error_type(error["message"])
            self.escalation_manager.get_or_create_state(
                error_hash=error["hash"],
                error_type=error_type,
            )

        # Build prompt for Claude
        # Phase 3 Fix 4: Include line numbers and error codes, limit to 30 errors
        errors_text = "\n\n".join([
            f"Error Type: {e['type']}\n"
            f"File: {e['file'] or 'Unknown'}\n"
            f"Line: {e.get('line') or 'Unknown'}\n"
            f"Code: {e.get('code', '')}\n"
            f"Message: {e['message']}"
            for e in error_context[:30]  # Max 30 errors for prompt
        ])

        # FIX-28: Build technology-specific prompt
        prompt = self._build_tech_aware_prompt(errors_text, len(error_context))

        # Estimate confidence before attempting fix
        primary_error = error_context[0]
        error_type = await self._categorize_error_type(primary_error["message"])
        strategy = self.escalation_manager.get_current_strategy(primary_error["hash"])
        escalation_level = strategy.level if strategy else EscalationLevel.LLM_TARGETED

        confidence = self.confidence_estimator.estimate_confidence(
            error_type=error_type,
            error_message=primary_error["message"],
            escalation_level=escalation_level.value,
            context_files=[e["file"] for e in error_context if e.get("file")],
        )

        self.logger.info(
            "fix_confidence_estimated",
            confidence=f"{confidence.overall:.2f}",
            category=confidence.category.value,
            escalation_level=escalation_level.name,
        )

        # Check if we should seek help instead of trying
        if self.confidence_estimator.should_seek_help(
            confidence.overall,
            self.escalation_manager.get_state(primary_error["hash"]).total_attempts
            if self.escalation_manager.get_state(primary_error["hash"])
            else 0,
        ):
            self.logger.warning(
                "seeking_help_low_confidence",
                confidence=confidence.overall,
                error_type=error_type,
            )
            # Trigger escalation to human review
            await self.escalation_manager.escalate(primary_error["hash"])
            return code_fixed_event(
                source=self.name,
                success=False,
                attempted=len(error_context),
                error="Low confidence - escalated to human review",
            )

        # Enhance prompt with session memory (lessons learned)
        enhanced_prompt = self.session_memory.enhance_prompt(
            original_prompt=prompt,
            error_type=error_type,
            error_message=primary_error["message"],
        )

        # MCP Integration: Collect enhanced context from filesystem + Docker
        try:
            mcp_context = await self._build_enhanced_context(error_context)
            if mcp_context:
                enhanced_prompt += mcp_context
                self.logger.debug(
                    "mcp_context_appended",
                    context_len=len(mcp_context),
                )
        except Exception as e:
            self.logger.debug("mcp_context_failed", error=str(e))

        try:
            # Phase 10: Use voting when enabled and errors are manageable
            if self.voting_enabled and self.fix_voter and len(error_context) <= 3:
                result = await self._fix_with_voting(
                    enhanced_prompt=enhanced_prompt,
                    error_context=error_context,
                    primary_error=primary_error,
                    error_type=error_type,
                )
            else:
                # Original single-fix approach
                tool = ClaudeCodeTool(working_dir=self.working_dir, timeout=180)
                result = await tool.execute(
                    prompt=enhanced_prompt,
                    context=f"Project has {len(error_context)} errors that need fixing",
                    agent_type="fixer",
                )

            if result.success and result.files:
                self.logger.info(
                    "fixes_applied",
                    files_modified=len(result.files),
                )

                # Record successful fix in session memory
                self.session_memory.record_fix(
                    error_type=error_type,
                    error_message=primary_error["message"],
                    fix_prompt=enhanced_prompt[:500],
                    fix_succeeded=True,
                    files_modified=result.files,
                    fix_approach="Claude-generated fix",
                    escalation_level=escalation_level.value,
                    confidence_score=confidence.overall,
                )

                # Record in confidence estimator
                self.confidence_estimator.record_fix(
                    error_type=error_type,
                    error_message=primary_error["message"],
                    escalation_level=escalation_level.value,
                    success=True,
                    confidence_before=confidence.overall,
                )

                # Clear escalation state for fixed errors
                for error in error_context:
                    self.escalation_manager.clear_error_state(error["hash"])

                # Publish FILE_CREATED events for each fixed file
                for file in result.files:
                    # Handle both GeneratedFile objects and string paths
                    path = file.path if hasattr(file, 'path') else str(file)
                    await self.event_bus.publish(file_created_event(
                        source=self.name,
                        file_path=path,
                    ))

                # Clear stuck state since we made progress
                await self.shared_state.clear_stuck_state()

                return code_fixed_event(
                    source=self.name,
                    success=True,
                    attempted=len(error_context),
                    files_modified=len(result.files),
                )
            else:
                self.logger.error("fix_attempt_failed", error=result.error)

                # Record failed fix in session memory
                self.session_memory.record_fix(
                    error_type=error_type,
                    error_message=primary_error["message"],
                    fix_prompt=enhanced_prompt[:500],
                    fix_succeeded=False,
                    fix_approach="Claude-generated fix",
                    escalation_level=escalation_level.value,
                    confidence_score=confidence.overall,
                )

                # Record in confidence estimator
                self.confidence_estimator.record_fix(
                    error_type=error_type,
                    error_message=primary_error["message"],
                    escalation_level=escalation_level.value,
                    success=False,
                    confidence_before=confidence.overall,
                )

                # Record attempt and check for escalation
                state = self.escalation_manager.get_state(primary_error["hash"])
                if state and state.should_escalate:
                    new_level = await self.escalation_manager.escalate(primary_error["hash"])
                    if new_level:
                        self.logger.info(
                            "escalated_to_next_level",
                            new_level=new_level.name,
                            error_hash=primary_error["hash"][:8],
                        )

                return code_fixed_event(
                    source=self.name,
                    success=False,
                    attempted=len(error_context),
                    error=result.error,
                )

        except Exception as e:
            self.logger.error("fix_attempt_failed", error=str(e))

            # Record exception in session memory
            self.session_memory.record_fix(
                error_type=error_type,
                error_message=primary_error["message"],
                fix_prompt=enhanced_prompt[:500] if 'enhanced_prompt' in dir() else prompt[:500],
                fix_succeeded=False,
                fix_approach=f"Exception: {str(e)[:100]}",
                escalation_level=escalation_level.value,
                confidence_score=confidence.overall if 'confidence' in dir() else 0.5,
            )

            return system_error_event(
                source=self.name,
                error_message=str(e),
            )

    async def _categorize_error_type(self, error_message: str) -> str:
        """
        Categorize error message into a type for confidence estimation.

        Uses multi-tier classification:
        1. Local/Redis cache for repeated errors
        2. Pattern-based fast classification
        3. LLM fallback for unknown error types
        """
        key = self._classification_cache._generate_key(error_message, "error")

        result = await self._classification_cache.classify(
            key=key,
            content=error_message,
            pattern_classifier=self._pattern_classify_error,
            llm_classifier=self._llm_classify_error,
            category_type="error_type",
        )

        self.logger.debug(
            "error_categorized",
            category=result.category,
            confidence=f"{result.confidence:.2f}",
            source=result.source.value,
        )

        return result.category

    def _pattern_classify_error(self, message: str) -> ClassificationResult:
        """Fast pattern-based error classification."""
        message_lower = message.lower()

        # Pattern tuples: (keywords_all_required, category, confidence)
        patterns = [
            (["cannot find module"], "import_error", 0.95),
            (["module not found"], "import_error", 0.95),
            (["is not defined"], "undefined_variable", 0.9),
            (["property", "does not exist"], "property_not_exist", 0.9),
            (["type", "assignable"], "type_mismatch", 0.85),
            (["type", "mismatch"], "type_mismatch", 0.85),
            (["ts2"], "type_error", 0.8),
            (["typescript"], "type_error", 0.75),
            (["syntax error"], "syntax_error", 0.95),
            (["unexpected token"], "syntax_error", 0.9),
            (["null"], "null_undefined", 0.7),
            (["undefined"], "null_undefined", 0.7),
            (["connection refused"], "connection_error", 0.9),
            (["econnrefused"], "connection_error", 0.9),
            (["database"], "database_connection", 0.75),
            (["relation", "does not exist"], "database_error", 0.9),
            (["build failed"], "build_error", 0.85),
            (["permission denied"], "permission_error", 0.9),
            (["out of memory"], "memory_error", 0.95),
            (["timeout"], "timeout_error", 0.85),
        ]

        for keywords, category, confidence in patterns:
            if all(kw in message_lower for kw in keywords):
                return ClassificationResult(
                    category=category,
                    confidence=confidence,
                    source=ClassificationSource.PATTERN,
                    metadata={"matched_keywords": keywords},
                )

        return ClassificationResult(
            category="unknown",
            confidence=0.0,
            source=ClassificationSource.PATTERN,
        )

    async def _llm_classify_error(self, message: str) -> ClassificationResult:
        """LLM-based semantic error classification for unknown error types."""
        import json
        import re

        prompt = f"""Classify this error into ONE category:

Error: {message[:1000]}

Categories:
- import_error: Missing module, failed import, cannot find module
- undefined_variable: Variable/function is not defined
- property_not_exist: Property does not exist on type
- type_mismatch: Type is not assignable, incompatible types
- type_error: General TypeScript/type errors
- syntax_error: Invalid syntax, unexpected token
- null_undefined: Null/undefined reference errors
- connection_error: Network connection refused/failed
- database_connection: Database connection issues
- database_error: Database schema/query errors
- build_error: Build tool failures, compilation errors
- permission_error: Permission denied, access errors
- memory_error: Out of memory, heap errors
- timeout_error: Operation timeout
- runtime_error: General runtime exceptions
- unknown: Cannot classify

Return ONLY valid JSON: {{"category": "...", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}
"""
        try:
            from ..tools.claude_code_tool import ClaudeCodeTool
            tool = ClaudeCodeTool(working_dir=self.working_dir)
            response = await tool.execute(prompt=prompt, skill_tier="minimal")

            # Parse JSON response
            match = re.search(r'\{[^}]+\}', response)
            if match:
                data = json.loads(match.group())
                category = data.get("category", "unknown")
                # Validate category is in our known list
                valid_categories = [
                    "import_error", "undefined_variable", "property_not_exist",
                    "type_mismatch", "type_error", "syntax_error", "null_undefined",
                    "connection_error", "database_connection", "database_error",
                    "build_error", "permission_error", "memory_error", "timeout_error",
                    "runtime_error", "unknown"
                ]
                if category not in valid_categories:
                    category = "unknown"

                return ClassificationResult(
                    category=category,
                    confidence=min(data.get("confidence", 0.7), 0.95),
                    source=ClassificationSource.LLM,
                    metadata={"reasoning": data.get("reasoning", "")},
                )
        except Exception as e:
            self.logger.warning("llm_error_classify_failed", error=str(e))

        return ClassificationResult(
            category="unknown",
            confidence=0.3,
            source=ClassificationSource.LLM,
            metadata={"error": "LLM classification failed"},
        )

    def _build_tech_aware_prompt(self, errors_text: str, error_count: int) -> str:
        """
        FIX-28: Build a technology-aware fix prompt based on tech_stack.
        """
        lines = [f"Fix the following {error_count} errors in this project:\n"]
        lines.append(errors_text)
        lines.append("\n")
        
        # Add technology-specific instructions
        if self.tech_stack:
            lines.append("\n## Technology Stack Requirements:\n")
            
            if hasattr(self.tech_stack, 'frontend_framework') and self.tech_stack.frontend_framework:
                frontend = self.tech_stack.frontend_framework.lower()
                lines.append(f"### Frontend: {self.tech_stack.frontend_framework}")
                
                if 'react' in frontend:
                    lines.append("- Use React functional components with TypeScript (.tsx)")
                    lines.append("- Use hooks (useState, useEffect) appropriately")
                    lines.append("- Components go in src/components/")
                elif 'vue' in frontend:
                    lines.append("- Use Vue 3 Composition API with <script setup>")
                    lines.append("- Use TypeScript for type safety")
                elif 'angular' in frontend:
                    lines.append("- Use Angular standalone components")
                    lines.append("- Follow Angular style guide")
                lines.append("")
            
            if hasattr(self.tech_stack, 'backend_framework') and self.tech_stack.backend_framework:
                backend = self.tech_stack.backend_framework.lower()
                lines.append(f"### Backend: {self.tech_stack.backend_framework}")
                
                if 'fastapi' in backend:
                    lines.append("- Use FastAPI with Pydantic models")
                    lines.append("- Routes go in src/api/routes/")
                    lines.append("- Use async/await for all endpoints")
                elif 'flask' in backend:
                    lines.append("- Use Flask blueprints for organization")
                elif 'express' in backend or 'node' in backend:
                    lines.append("- Use Express.js with TypeScript")
                lines.append("")
            
            if hasattr(self.tech_stack, 'styling_framework') and self.tech_stack.styling_framework:
                styling = self.tech_stack.styling_framework.lower()
                lines.append(f"### Styling: {self.tech_stack.styling_framework}")
                
                if 'tailwind' in styling:
                    lines.append("- Use Tailwind CSS utility classes")
                elif 'bootstrap' in styling:
                    lines.append("- Use Bootstrap classes and components")
                elif 'mui' in styling or 'material' in styling:
                    lines.append("- Use MUI components and sx prop")
                lines.append("")
        
        lines.append("\nInstructions:")
        lines.append("1. Analyze each error and understand the root cause")
        lines.append("2. Create or modify the necessary files to fix the errors")
        lines.append("3. For missing file errors, create the file with appropriate content")
        lines.append("4. For type errors, fix the type definitions or usage")
        lines.append("5. For build errors, ensure all imports and dependencies are correct")
        lines.append("6. For test failures, fix the failing tests or the code they test")
        if self.tech_stack:
            lines.append("7. Follow the technology stack requirements above")
        lines.append("\nFocus on the most critical errors first. Implement complete solutions, not placeholders.")
        
        return "\n".join(lines)

    # =========================================================================
    # MCP Integration: Filesystem + Docker for Enhanced Error Context
    # =========================================================================

    async def _collect_docker_logs(self, container_name: Optional[str] = None) -> Optional[str]:
        """
        Collect Docker container logs via subprocess for enhanced error context.

        Uses the same pattern as MCPToolRegistry docker tools.
        Returns truncated logs or None if no container is running.
        """
        import subprocess as _sp

        try:
            # If no specific container, try to find project container
            if not container_name:
                list_result = _sp.run(
                    ["docker", "ps", "--format", "{{.Names}}"],
                    capture_output=True, text=True, timeout=10,
                    encoding="utf-8", errors="replace",
                    cwd=self.working_dir,
                )
                if list_result.returncode != 0 or not list_result.stdout.strip():
                    return None

                containers = list_result.stdout.strip().split("\n")
                # Look for project-related container
                project_dir_name = Path(self.working_dir).name.lower()
                container_name = None
                for c in containers:
                    if project_dir_name in c.lower() or "sandbox" in c.lower():
                        container_name = c.strip()
                        break
                if not container_name and containers:
                    container_name = containers[0].strip()

            if not container_name:
                return None

            # Collect last 100 lines of logs
            log_result = _sp.run(
                ["docker", "logs", "--tail", "100", container_name],
                capture_output=True, text=True, timeout=15,
                encoding="utf-8", errors="replace",
            )

            if log_result.returncode == 0:
                logs = (log_result.stdout or "") + (log_result.stderr or "")
                self.logger.debug(
                    "docker_logs_collected",
                    container=container_name,
                    lines=len(logs.split("\n")),
                )
                return logs[:5000]  # Truncate

        except Exception as e:
            self.logger.debug("docker_log_collection_failed", error=str(e))

        return None

    async def _read_related_files(self, file_paths: list[str], max_per_file: int = 200) -> dict[str, str]:
        """
        Read related source files for enhanced fix context.

        Uses direct file I/O (same pattern as MCPToolRegistry filesystem tools).
        Returns dict of {filepath: content_preview}.
        """
        contents: dict[str, str] = {}

        for file_path in file_paths[:5]:  # Max 5 files to avoid overloading
            if not file_path:
                continue

            # Resolve relative paths against working_dir
            full_path = file_path
            if not os.path.isabs(file_path):
                full_path = os.path.join(self.working_dir, file_path)

            try:
                if os.path.isfile(full_path):
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()[:max_per_file]
                        contents[file_path] = "".join(lines)
            except Exception as e:
                self.logger.debug("file_read_failed", file=file_path, error=str(e))

        return contents

    async def _build_enhanced_context(self, error_context: list[dict]) -> str:
        """
        Build enhanced error context using MCP-integrated data sources.

        Collects:
        1. Related file contents (via filesystem)
        2. Docker container logs (via docker)
        3. Previous fix attempts from session memory

        Returns additional context string to append to fix prompt.
        """
        context_parts: list[str] = []

        # 1. Collect affected file contents
        affected_files = list(set(
            e.get("file") for e in error_context if e.get("file")
        ))
        if affected_files:
            file_contents = await self._read_related_files(affected_files)
            if file_contents:
                context_parts.append("\n## Related Source Files:\n")
                for path, content in file_contents.items():
                    context_parts.append(f"### {path}\n```\n{content[:2000]}\n```\n")

        # 2. Collect Docker logs if errors suggest runtime issues
        runtime_keywords = ["runtime", "connection", "econnrefused", "crash", "segfault", "timeout"]
        has_runtime_errors = any(
            any(kw in e.get("message", "").lower() for kw in runtime_keywords)
            for e in error_context
        )
        if has_runtime_errors:
            docker_logs = await self._collect_docker_logs()
            if docker_logs:
                context_parts.append(f"\n## Docker Container Logs:\n```\n{docker_logs[:3000]}\n```\n")

        return "\n".join(context_parts)

    def _get_action_description(self) -> str:
        return "Attempting to fix errors with Claude"

    async def _fix_with_voting(
        self,
        enhanced_prompt: str,
        error_context: list[dict],
        primary_error: dict,
        error_type: str,
    ) -> Any:
        """
        Phase 10: Generate multiple fix proposals and vote on the best one.

        This method generates 2 fix proposals using different approaches,
        then uses FixVoter to select the best one based on code quality,
        stability, and minimal change criteria.

        Args:
            enhanced_prompt: The prompt for fix generation
            error_context: List of error dictionaries
            primary_error: The primary error being fixed
            error_type: Categorized error type

        Returns:
            Result object with success, files, and error attributes
        """
        from types import SimpleNamespace
        from ..tools.claude_code_tool import ClaudeCodeTool

        self.logger.info(
            "fix_with_voting_started",
            error_count=len(error_context),
            error_type=error_type,
        )

        # Define fix approaches
        approaches = [
            ("minimal", "Apply the smallest, most targeted fix that resolves the error without changing unrelated code."),
            ("thorough", "Apply a comprehensive fix that resolves the error and also improves the surrounding code quality."),
        ]

        # Get configurable timeout from settings
        from ..config import get_settings
        settings = get_settings()
        proposal_timeout = settings.voting_proposal_timeout  # Default 90s (reduced from 120)

        # Generate fix proposals
        proposals = []
        tool = ClaudeCodeTool(working_dir=self.working_dir, timeout=proposal_timeout)

        # Helper function for generating a single proposal
        async def gen_proposal(approach_id: str, approach_desc: str) -> "ProposedFix | None":
            approach_prompt = f"{enhanced_prompt}\n\n## FIX APPROACH: {approach_desc}"
            try:
                result = await tool.execute(
                    prompt=approach_prompt,
                    context=f"Generating {approach_id} fix proposal",
                    agent_type="fixer",
                )
                if result.success and result.files:
                    self.logger.info(
                        "fix_proposal_generated",
                        approach=approach_id,
                        files_count=len(result.files),
                    )
                    return ProposedFix(
                        id=f"fix_{approach_id}",
                        description=f"{approach_id.capitalize()} fix: {primary_error['message'][:50]}...",
                        code_changes=[{"approach": approach_id}],
                        files_modified=result.files,
                        complexity="low" if approach_id == "minimal" else "medium",
                        reasoning=f"Generated using {approach_id} approach",
                        source="llm",
                    )
            except Exception as e:
                self.logger.warning(
                    "fix_proposal_failed",
                    approach=approach_id,
                    error=str(e),
                )
            return None

        # Generate proposals (parallel or sequential based on config)
        if settings.voting_parallel_proposals:
            # Parallel generation for faster recovery
            import asyncio
            tasks = [gen_proposal(aid, adesc) for aid, adesc in approaches]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            proposals = [r for r in results if r and not isinstance(r, Exception)]
            self.logger.info(
                "parallel_proposals_complete",
                total=len(approaches),
                successful=len(proposals),
            )
        else:
            # Sequential generation (original behavior)
            for approach_id, approach_desc in approaches:
                proposal = await gen_proposal(approach_id, approach_desc)
                if proposal:
                    proposals.append(proposal)

        # If no proposals generated, fall back to original approach
        if not proposals:
            self.logger.warning("no_proposals_generated_falling_back")
            return await tool.execute(
                prompt=enhanced_prompt,
                context=f"Project has {len(error_context)} errors that need fixing",
                agent_type="fixer",
            )

        # If only one proposal, return it directly
        if len(proposals) == 1:
            self.logger.info("single_proposal_selected", proposal=proposals[0].id)
            return SimpleNamespace(
                success=True,
                files=proposals[0].files_modified,
                error=None,
            )

        # Vote on the best proposal
        voter_error = VoterErrorContext(
            error_type=error_type,
            error_message=primary_error["message"],
            file_path=primary_error.get("file"),
            related_files=[e["file"] for e in error_context if e.get("file")],
        )

        voting_result = await self.fix_voter.select_fix(voter_error, proposals)

        self.logger.info(
            "fix_voting_complete",
            winner=voting_result.winning_option_id,
            confidence=voting_result.confidence_score,
            consensus=voting_result.consensus_reached,
            votes=[v.selected_option for v in voting_result.votes] if voting_result.votes else [],
        )

        # Return the winning fix
        if voting_result.winning_fix:
            return SimpleNamespace(
                success=True,
                files=voting_result.winning_fix.files_modified,
                error=None,
            )
        else:
            # Fallback to first proposal
            return SimpleNamespace(
                success=True,
                files=proposals[0].files_modified,
                error=None,
            )
