"""
Tool-Using Agent für MoireTracker V2

Integriert die gRPC Worker Bridge mit dem Orchestrator V2:
- Nutzt PlannerWorker für LLM-basiertes Task-Planning
- Nutzt ExecutionWorker für Tool-Ausführung mit Validation
- Propagiert TaskContext an alle Worker
- Unterstützt Orchestrator V2 Reflection-Loop
"""

import asyncio
import logging
import os
import sys
import time
from typing import Optional, Dict, Any, List, Callable, Awaitable
from dataclasses import dataclass
import uuid

# Add parent paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Worker Bridge Imports
try:
    from worker_bridge.messages import (
        ToolName,
        ExecutionStatus,
        TaskContext,
        ActionStep,
        TaskExecutionRequest,
        TaskExecutionResult,
        ToolExecutionResult,
        ReplanRequest
    )
    from worker_bridge.workers.execution_worker import ExecutionWorker, get_execution_worker
    from worker_bridge.workers.planner_worker import PlannerWorker, get_planner_worker
    from worker_bridge.workers.desktop_tools import DESKTOP_TOOLS
    HAS_WORKER_BRIDGE = True
except ImportError as e:
    logging.warning(f"Worker Bridge nicht verfügbar: {e}")
    HAS_WORKER_BRIDGE = False

# Orchestrator V2 Import
try:
    from agents.orchestrator_v2 import OrchestratorV2, get_orchestrator_v2
    HAS_ORCHESTRATOR = True
except ImportError:
    HAS_ORCHESTRATOR = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ToolUsingAgentConfig:
    """Konfiguration für den Tool-Using Agent."""
    agent_id: str = "tool_using_agent"
    max_validation_rounds: int = 3
    validation_threshold: float = 0.02
    enable_llm_planning: bool = True
    enable_screenshots: bool = True
    integration_mode: str = "standalone"  # "standalone" or "orchestrator"


class ToolUsingAgent:
    """
    Tool-Using Agent für Desktop-Automation.
    
    Modi:
    - standalone: Direkte Nutzung von Planner + Execution Worker
    - orchestrator: Integration mit OrchestratorV2 Reflection-Loop
    
    Features:
    - LLM-basiertes Task-Planning
    - Tool-Ausführung mit Screenshot-Validation
    - TaskContext Propagation
    - Re-Planning bei Fehlschlag
    """
    
    def __init__(
        self,
        config: Optional[ToolUsingAgentConfig] = None,
        orchestrator: Optional[OrchestratorV2] = None
    ):
        self.config = config or ToolUsingAgentConfig()
        
        # Worker Bridge
        self._execution_worker: Optional[ExecutionWorker] = None
        self._planner_worker: Optional[PlannerWorker] = None
        
        if HAS_WORKER_BRIDGE:
            self._execution_worker = get_execution_worker()
            self._planner_worker = get_planner_worker()
            
            # Set replan callback
            if self._execution_worker and self._planner_worker:
                self._execution_worker.set_replan_callback(self._handle_replan)
        
        # Orchestrator Integration
        self._orchestrator = orchestrator
        if HAS_ORCHESTRATOR and orchestrator is None and self.config.integration_mode == "orchestrator":
            self._orchestrator = get_orchestrator_v2()
        
        # State
        self._current_task: Optional[str] = None
        self._current_context: Optional[TaskContext] = None
        
        # Stats
        self._tasks_executed: int = 0
        self._tasks_successful: int = 0
        self._total_actions: int = 0
        
        # Callbacks
        self._on_task_complete: List[Callable[[TaskExecutionResult], Awaitable[None]]] = []
        self._on_step_complete: List[Callable[[ToolExecutionResult], Awaitable[None]]] = []
        
        logger.info(f"ToolUsingAgent initialisiert: {self.config.agent_id}")
        logger.info(f"  Mode: {self.config.integration_mode}")
        logger.info(f"  Worker Bridge: {'verfügbar' if HAS_WORKER_BRIDGE else 'nicht verfügbar'}")
        logger.info(f"  Orchestrator: {'verbunden' if self._orchestrator else 'nicht verbunden'}")
    
    async def execute_natural_language_task(
        self,
        user_request: str,
        ui_state: Optional[Dict[str, Any]] = None,
        screen_bounds: Optional[Dict[str, int]] = None,
        app_context: Optional[Dict[str, Any]] = None
    ) -> TaskExecutionResult:
        """
        Führt natürlichsprachlichen Task aus.
        
        Workflow:
        1. PlannerWorker erstellt Action-Plan aus User-Request
        2. ExecutionWorker führt Plan aus mit Validation
        3. Bei Fehlschlag: Re-Planning und Retry
        
        Args:
            user_request: Natürlichsprachliche Anfrage
            ui_state: Aktueller UI-Zustand
            screen_bounds: Bildschirmgröße
            app_context: App-Kontext
            
        Returns:
            TaskExecutionResult mit allen Ergebnissen
        """
        if not HAS_WORKER_BRIDGE or not self._execution_worker or not self._planner_worker:
            return self._create_error_result(
                "Worker Bridge nicht verfügbar",
                user_request
            )
        
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        self._current_task = task_id
        self._tasks_executed += 1
        
        logger.info(f"\n{'='*60}")
        logger.info(f"[{task_id}] Natural Language Task")
        logger.info(f"  Request: {user_request[:100]}...")
        logger.info(f"{'='*60}")
        
        # Defaults
        if ui_state is None:
            ui_state = {"elements": []}
        if screen_bounds is None:
            screen_bounds = {"width": 1920, "height": 1080}
        if app_context is None:
            app_context = {}
        
        # Create TaskContext
        context = TaskContext(
            user_request=user_request,
            app_context=app_context,
            ui_state=ui_state,
            screen_bounds=screen_bounds
        )
        self._current_context = context
        
        try:
            # Step 1: Create Plan
            logger.info(f"[{task_id}] Step 1: Creating action plan...")
            
            action_plan = await self._planner_worker.create_plan(
                user_request=user_request,
                ui_state=ui_state,
                screen_bounds=screen_bounds,
                app_context=app_context
            )
            
            if not action_plan:
                return self._create_error_result(
                    "Planner konnte keinen Plan erstellen",
                    user_request,
                    task_id
                )
            
            logger.info(f"[{task_id}] Plan created: {len(action_plan)} steps")
            
            # Step 2: Execute Plan
            logger.info(f"[{task_id}] Step 2: Executing plan...")
            
            request = TaskExecutionRequest(
                task_id=task_id,
                context=context,
                action_plan=action_plan,
                max_validation_rounds=self.config.max_validation_rounds,
                validation_threshold=self.config.validation_threshold,
                request_id=f"req_{uuid.uuid4().hex[:8]}"
            )
            
            result = await self._execution_worker.execute_task(request)
            
            # Stats
            self._total_actions += result.steps_executed
            if result.success:
                self._tasks_successful += 1
            
            # Callbacks
            for callback in self._on_task_complete:
                try:
                    await callback(result)
                except Exception as e:
                    logger.warning(f"Task complete callback error: {e}")
            
            logger.info(f"[{task_id}] Task completed: {result.status.value}")
            
            return result
            
        except Exception as e:
            logger.error(f"[{task_id}] Task failed: {e}")
            return self._create_error_result(str(e), user_request, task_id)
        
        finally:
            self._current_task = None
            self._current_context = None
    
    async def execute_predefined_plan(
        self,
        action_plan: List[ActionStep],
        context: TaskContext
    ) -> TaskExecutionResult:
        """
        Führt vordefinierten Action-Plan aus.
        
        Für Fälle wo der Plan bereits extern erstellt wurde.
        """
        if not HAS_WORKER_BRIDGE or not self._execution_worker:
            return self._create_error_result(
                "Worker Bridge nicht verfügbar",
                context.user_request
            )
        
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        
        request = TaskExecutionRequest(
            task_id=task_id,
            context=context,
            action_plan=action_plan,
            max_validation_rounds=self.config.max_validation_rounds,
            validation_threshold=self.config.validation_threshold,
            request_id=f"req_{uuid.uuid4().hex[:8]}"
        )
        
        return await self._execution_worker.execute_task(request)
    
    async def execute_single_action(
        self,
        tool_name: str,
        params: Dict[str, Any],
        context: Optional[TaskContext] = None
    ) -> ToolExecutionResult:
        """
        Führt einzelne Aktion aus.
        
        Args:
            tool_name: Name des Tools (z.B. "click_at_position")
            params: Tool-Parameter
            context: Optionaler TaskContext
            
        Returns:
            ToolExecutionResult
        """
        if not HAS_WORKER_BRIDGE or not self._execution_worker:
            # Create error result
            return ToolExecutionResult(
                step_id=f"error_{int(time.time()*1000)}",
                tool_name=ToolName.WAIT,  # Fallback
                status=ExecutionStatus.FAILED,
                error_context="Worker Bridge nicht verfügbar",
                duration_ms=0
            )
        
        try:
            tool_name_enum = ToolName(tool_name)
        except ValueError:
            return ToolExecutionResult(
                step_id=f"error_{int(time.time()*1000)}",
                tool_name=ToolName.WAIT,
                status=ExecutionStatus.FAILED,
                error_context=f"Unknown tool: {tool_name}",
                duration_ms=0
            )
        
        return await self._execution_worker.execute_single_action(
            tool_name=tool_name_enum,
            params=params,
            context=context
        )
    
    async def _handle_replan(
        self,
        replan_request: ReplanRequest
    ) -> List[ActionStep]:
        """
        Callback für Re-Planning vom ExecutionWorker.
        """
        if not self._planner_worker:
            return []
        
        return await self._planner_worker.create_replan(replan_request)
    
    def _create_error_result(
        self,
        error: str,
        user_request: str,
        task_id: Optional[str] = None
    ) -> TaskExecutionResult:
        """Erstellt Fehler-Result."""
        return TaskExecutionResult(
            task_id=task_id or f"error_{int(time.time()*1000)}",
            success=False,
            status=ExecutionStatus.FAILED,
            steps_executed=0,
            steps_total=0,
            validation_rounds=0,
            results=[],
            error_summary=error,
            total_duration_ms=0
        )
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Gibt Liste verfügbarer Tools zurück."""
        if not HAS_WORKER_BRIDGE:
            return []
        
        tools = []
        for name, definition in DESKTOP_TOOLS.items():
            tools.append({
                "name": name,
                "description": definition.get("description", ""),
                "parameters": definition.get("parameters", {}),
                "requires_validation": definition.get("requires_validation", True)
            })
        
        return tools
    
    def on_task_complete(
        self,
        callback: Callable[[TaskExecutionResult], Awaitable[None]]
    ):
        """Registriert Callback für Task-Abschluss."""
        self._on_task_complete.append(callback)
    
    def on_step_complete(
        self,
        callback: Callable[[ToolExecutionResult], Awaitable[None]]
    ):
        """Registriert Callback für Step-Abschluss."""
        self._on_step_complete.append(callback)
        
        # Forward to execution worker
        if self._execution_worker:
            self._execution_worker._on_step_complete.append(callback)
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Agent-Statistiken zurück."""
        stats = {
            "agent_id": self.config.agent_id,
            "mode": self.config.integration_mode,
            "current_task": self._current_task,
            "tasks_executed": self._tasks_executed,
            "tasks_successful": self._tasks_successful,
            "success_rate": (
                self._tasks_successful / self._tasks_executed 
                if self._tasks_executed > 0 else 0
            ),
            "total_actions": self._total_actions,
            "worker_bridge_available": HAS_WORKER_BRIDGE,
            "orchestrator_connected": self._orchestrator is not None
        }
        
        # Add worker stats
        if self._execution_worker:
            stats["execution_worker"] = self._execution_worker.get_stats()
        
        if self._planner_worker:
            stats["planner_worker"] = self._planner_worker.get_stats()
        
        return stats
    
    async def execute_with_orchestrator_reflection(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        max_rounds: int = 3
    ) -> Dict[str, Any]:
        """
        Führt Task mit Orchestrator V2 Reflection-Loop aus.
        
        Kombiniert Tool-Using Agent Planning mit Orchestrator Reflection.
        """
        if not self._orchestrator:
            return {
                "success": False,
                "error": "Orchestrator nicht verbunden",
                "mode": "standalone_fallback"
            }
        
        logger.info(f"Executing with Orchestrator Reflection: {goal[:100]}...")
        
        # Use orchestrator's execute_task_with_reflection
        result = await self._orchestrator.execute_task_with_reflection(
            goal=goal,
            context=context,
            max_reflection_rounds=max_rounds
        )
        
        return result


# ==================== Singleton ====================

_tool_using_agent_instance: Optional[ToolUsingAgent] = None


def get_tool_using_agent() -> ToolUsingAgent:
    """Gibt Singleton-Instanz des ToolUsingAgents zurück."""
    global _tool_using_agent_instance
    if _tool_using_agent_instance is None:
        _tool_using_agent_instance = ToolUsingAgent()
    return _tool_using_agent_instance


# ==================== Test ====================

async def main():
    """Test des Tool-Using Agents."""
    agent = ToolUsingAgent()
    
    print("\n" + "=" * 60)
    print("Tool-Using Agent Test")
    print("=" * 60)
    
    # Show available tools
    print("\nVerfügbare Tools:")
    for tool in agent.get_available_tools()[:5]:
        print(f"  - {tool['name']}: {tool['description'][:50]}...")
    
    # Test natural language task
    if HAS_WORKER_BRIDGE:
        print("\nTest: Natural Language Task")
        result = await agent.execute_natural_language_task(
            user_request="Warte 0.5 Sekunden",
            ui_state={"elements": []},
            screen_bounds={"width": 1920, "height": 1080}
        )
        
        print(f"\n--- Result ---")
        print(f"Success: {result.success}")
        print(f"Status: {result.status.value}")
        print(f"Steps: {result.steps_executed}/{result.steps_total}")
    else:
        print("\nWorker Bridge nicht verfügbar - überspringe Test")
    
    # Stats
    print("\n--- Stats ---")
    stats = agent.get_stats()
    print(f"Tasks: {stats['tasks_executed']}")
    print(f"Success Rate: {stats['success_rate']:.1%}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
