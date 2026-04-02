"""
Execution Worker für MoireTracker Tool-Using Agents

Führt Desktop-Automation-Tasks aus mit:
1. LLM Function-Calling für Tool-Ausführung
2. Screenshot-basierte Validation nach jeder Aktion
3. Validation-Loop mit max 3 Runden
4. Re-Planning bei Fehlschlag
5. TaskContext Propagation an alle Tools
"""

import asyncio
import base64
import io
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable, Awaitable

# Add parent paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# AutoGen Imports (optional)
try:
    from autogen_core import RoutedAgent, message_handler, type_subscription, MessageContext
    HAS_AUTOGEN = True
except ImportError:
    HAS_AUTOGEN = False
    class RoutedAgent:
        pass
    def message_handler(func):
        return func
    def type_subscription(topic_type):
        def decorator(cls):
            return cls
        return decorator
    class MessageContext:
        pass

# PIL für Screenshot-Vergleich
try:
    from PIL import Image, ImageChops
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Internal Imports
from worker_bridge.messages import (
    ToolName,
    ExecutionStatus,
    TaskContext,
    ActionStep,
    TaskExecutionRequest,
    ToolExecutionResult,
    TaskExecutionResult,
    SizeValidationReport,
    ReplanRequest
)

from worker_bridge.workers.desktop_tools import (
    DesktopToolExecutor,
    get_tool_executor,
    get_tool_functions_schema,
    DESKTOP_TOOLS
)

# OpenRouter Client
try:
    from core.openrouter_client import OpenRouterClient, get_openrouter_client
    HAS_OPENROUTER = True
except ImportError:
    HAS_OPENROUTER = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExecutionWorkerConfig:
    """Konfiguration für den Execution Worker."""
    worker_id: str = "execution_worker"
    model: str = "google/gemini-2.0-flash-001"
    max_validation_rounds: int = 3
    validation_threshold: float = 0.02  # 2% Änderung für Erfolg
    validation_timeout: float = 5.0  # Sekunden
    validation_check_interval: float = 0.3  # Sekunden
    enable_llm_planning: bool = True
    enable_screenshots: bool = True


class ExecutionWorker:
    """
    Execution Worker für Tool-Using Agent Tasks.
    
    Workflow:
    1. Empfängt TaskExecutionRequest mit Kontext und ActionPlan
    2. Führt jeden ActionStep aus
    3. Validiert nach jeder Aktion via Screenshot-Vergleich
    4. Bei Fehlschlag: Re-Planning mit Fehlerkontext
    5. Gibt TaskExecutionResult zurück
    """
    
    def __init__(
        self,
        config: Optional[ExecutionWorkerConfig] = None,
        tool_executor: Optional[DesktopToolExecutor] = None,
        openrouter_client: Optional[OpenRouterClient] = None
    ):
        self.config = config or ExecutionWorkerConfig()
        self.tool_executor = tool_executor or get_tool_executor()
        self.client = openrouter_client or (get_openrouter_client() if HAS_OPENROUTER else None)
        
        # State
        self._is_running: bool = False
        self._current_task: Optional[str] = None
        
        # Stats
        self._tasks_processed: int = 0
        self._tasks_successful: int = 0
        self._tasks_failed: int = 0
        self._total_actions: int = 0
        self._validation_rounds: int = 0
        
        # Callbacks
        self._on_step_complete: List[Callable[[ToolExecutionResult], Awaitable[None]]] = []
        self._on_validation_failed: List[Callable[[ToolExecutionResult], Awaitable[None]]] = []
        self._on_replan_requested: List[Callable[[ReplanRequest], Awaitable[List[ActionStep]]]] = []
        
        logger.info(f"ExecutionWorker initialisiert: {self.config.worker_id}")
        logger.info(f"  Model: {self.config.model}")
        logger.info(f"  Max Validation Rounds: {self.config.max_validation_rounds}")
        logger.info(f"  Validation Threshold: {self.config.validation_threshold * 100}%")
    
    def set_replan_callback(
        self,
        callback: Callable[[ReplanRequest], Awaitable[List[ActionStep]]]
    ):
        """Setzt Callback für Re-Planning."""
        self._on_replan_requested.append(callback)
    
    async def execute_task(
        self,
        request: TaskExecutionRequest
    ) -> TaskExecutionResult:
        """
        Führt kompletten Task mit Validation-Loop aus.
        
        Args:
            request: TaskExecutionRequest mit Kontext und ActionPlan
            
        Returns:
            TaskExecutionResult mit allen Step-Ergebnissen
        """
        task_id = request.task_id
        self._current_task = task_id
        self._tasks_processed += 1
        start_time = time.time()
        
        logger.info(f"\n{'='*60}")
        logger.info(f"[{task_id}] Task-Ausführung gestartet")
        logger.info(f"  User Request: {request.context.user_request[:100]}...")
        logger.info(f"  Action Plan: {len(request.action_plan)} Steps")
        logger.info(f"{'='*60}")
        
        results: List[ToolExecutionResult] = []
        validation_rounds = 0
        current_plan = request.action_plan.copy()
        executed_steps = 0
        
        try:
            while current_plan and validation_rounds < request.max_validation_rounds:
                step = current_plan.pop(0)
                executed_steps += 1
                self._total_actions += 1
                
                logger.info(f"\n[{task_id}] Step {executed_steps}: {step.tool_name.value}")
                logger.info(f"  Expected: {step.expected_outcome}")
                
                # Pre-Screenshot
                screenshot_before = None
                if self.config.enable_screenshots and step.requires_validation:
                    screenshot_before = await self.tool_executor.capture_full_screen()
                
                # Tool ausführen
                step_start = time.time()
                tool_result = await self.tool_executor.execute_tool(
                    step.tool_name,
                    step.tool_params,
                    ui_state=request.context.ui_state
                )
                
                # Warte kurz für UI-Update
                await asyncio.sleep(0.2)
                
                # Post-Screenshot
                screenshot_after = None
                if self.config.enable_screenshots and step.requires_validation:
                    screenshot_after = await self.tool_executor.capture_full_screen()
                
                # Validierung
                validation_result = await self._validate_step(
                    step=step,
                    tool_result=tool_result,
                    screenshot_before=screenshot_before,
                    screenshot_after=screenshot_after,
                    threshold=request.validation_threshold
                )
                
                # Build ToolExecutionResult
                step_result = ToolExecutionResult(
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    status=validation_result["status"],
                    screenshot_before=screenshot_before,
                    screenshot_after=screenshot_after,
                    change_percentage=validation_result["change_percentage"],
                    action_result=tool_result,
                    size_validation=validation_result.get("size_validation"),
                    error_context=validation_result.get("error"),
                    duration_ms=(time.time() - step_start) * 1000,
                    validation_attempts=validation_result.get("attempts", 1)
                )
                
                results.append(step_result)
                
                # Callbacks
                for callback in self._on_step_complete:
                    try:
                        await callback(step_result)
                    except Exception as e:
                        logger.warning(f"Step complete callback failed: {e}")
                
                # Status-basierte Entscheidung
                if step_result.status == ExecutionStatus.SUCCESS:
                    logger.info(f"  ✓ Step erfolgreich ({step_result.change_percentage:.1%} Änderung)")
                    
                elif step_result.status == ExecutionStatus.NEEDS_REPLAN:
                    logger.warning(f"  ⚠ Validation fehlgeschlagen - Re-Planning")
                    validation_rounds += 1
                    self._validation_rounds += 1
                    
                    # Callbacks für Validation-Fehler
                    for callback in self._on_validation_failed:
                        try:
                            await callback(step_result)
                        except Exception as e:
                            logger.warning(f"Validation failed callback error: {e}")
                    
                    # Re-Planning anfordern
                    if validation_rounds < request.max_validation_rounds:
                        new_steps = await self._request_replan(
                            request=request,
                            executed_results=results,
                            failed_step=step_result,
                            remaining_rounds=request.max_validation_rounds - validation_rounds
                        )
                        
                        if new_steps:
                            # Neue Steps vorne einfügen
                            current_plan = new_steps + current_plan
                            logger.info(f"  Re-Planning erfolgreich: {len(new_steps)} neue Steps")
                        else:
                            logger.warning(f"  Re-Planning ergab keine neuen Steps")
                    else:
                        logger.error(f"  Max Validation-Rounds erreicht ({request.max_validation_rounds})")
                
                elif step_result.status == ExecutionStatus.FAILED:
                    logger.error(f"  ✗ Step fehlgeschlagen: {step_result.error_context}")
                    # Continue trotzdem mit nächstem Step
            
            # Finaler Status
            successful_steps = sum(1 for r in results if r.status == ExecutionStatus.SUCCESS)
            all_success = successful_steps == executed_steps
            
            final_status = ExecutionStatus.SUCCESS if all_success else (
                ExecutionStatus.PARTIAL if successful_steps > 0 else ExecutionStatus.FAILED
            )
            
            # Final Screenshot
            final_screenshot = None
            if self.config.enable_screenshots:
                final_screenshot = await self.tool_executor.capture_full_screen()
            
            # Stats
            if all_success:
                self._tasks_successful += 1
            else:
                self._tasks_failed += 1
            
            total_duration = (time.time() - start_time) * 1000
            
            logger.info(f"\n{'='*60}")
            logger.info(f"[{task_id}] Task-Ausführung abgeschlossen")
            logger.info(f"  Status: {final_status.value}")
            logger.info(f"  Steps: {successful_steps}/{executed_steps} erfolgreich")
            logger.info(f"  Validation Rounds: {validation_rounds}")
            logger.info(f"  Duration: {total_duration:.0f}ms")
            logger.info(f"{'='*60}")
            
            return TaskExecutionResult(
                task_id=task_id,
                success=all_success,
                status=final_status,
                steps_executed=executed_steps,
                steps_total=len(request.action_plan),
                validation_rounds=validation_rounds,
                results=results,
                final_screenshot=final_screenshot,
                error_summary=None if all_success else f"{executed_steps - successful_steps} steps failed",
                total_duration_ms=total_duration,
                request_id=request.request_id
            )
        
        except Exception as e:
            logger.error(f"[{task_id}] Task-Ausführung fehlgeschlagen: {e}")
            self._tasks_failed += 1
            
            return TaskExecutionResult(
                task_id=task_id,
                success=False,
                status=ExecutionStatus.FAILED,
                steps_executed=executed_steps,
                steps_total=len(request.action_plan),
                validation_rounds=validation_rounds,
                results=results,
                error_summary=str(e),
                total_duration_ms=(time.time() - start_time) * 1000,
                request_id=request.request_id
            )
        
        finally:
            self._current_task = None
    
    async def _validate_step(
        self,
        step: ActionStep,
        tool_result: Dict[str, Any],
        screenshot_before: Optional[str],
        screenshot_after: Optional[str],
        threshold: float = 0.02
    ) -> Dict[str, Any]:
        """
        Validiert einen ausgeführten Step via Screenshot-Vergleich.
        
        Returns:
            Dict mit status, change_percentage, error, etc.
        """
        result = {
            "status": ExecutionStatus.SUCCESS,
            "change_percentage": 0.0,
            "attempts": 1,
            "error": None
        }
        
        # Tool-Execution fehlgeschlagen?
        if not tool_result.get("success", False):
            result["status"] = ExecutionStatus.FAILED
            result["error"] = tool_result.get("error", "Tool execution failed")
            return result
        
        # Keine Validation für bestimmte Tools
        if step.tool_name in [ToolName.WAIT, ToolName.WAIT_FOR_ELEMENT]:
            result["status"] = ExecutionStatus.SUCCESS
            return result
        
        # Keine Screenshots für Validation
        if not screenshot_before or not screenshot_after:
            # Ohne Screenshots: Optimistic success wenn Tool-Result success ist
            result["status"] = ExecutionStatus.SUCCESS
            return result
        
        if not step.requires_validation:
            result["status"] = ExecutionStatus.SUCCESS
            return result
        
        # Screenshot-basierte Validation
        if HAS_PIL:
            try:
                change = self._compare_screenshots(screenshot_before, screenshot_after)
                result["change_percentage"] = change
                
                if change >= threshold:
                    result["status"] = ExecutionStatus.SUCCESS
                else:
                    # Versuche nochmal mit längerer Wartezeit
                    await asyncio.sleep(0.5)
                    screenshot_after_retry = await self.tool_executor.capture_full_screen()
                    
                    if screenshot_after_retry:
                        change_retry = self._compare_screenshots(screenshot_before, screenshot_after_retry)
                        result["change_percentage"] = change_retry
                        result["attempts"] = 2
                        
                        if change_retry >= threshold:
                            result["status"] = ExecutionStatus.SUCCESS
                        else:
                            result["status"] = ExecutionStatus.NEEDS_REPLAN
                            result["error"] = f"Change {change_retry:.1%} below threshold {threshold:.1%}"
                    else:
                        result["status"] = ExecutionStatus.NEEDS_REPLAN
                        result["error"] = f"Change {change:.1%} below threshold {threshold:.1%}"
            
            except Exception as e:
                logger.warning(f"Screenshot comparison failed: {e}")
                # Fallback: Success basierend auf Tool-Result
                result["status"] = ExecutionStatus.SUCCESS
        else:
            # Ohne PIL: Success basierend auf Tool-Result
            result["status"] = ExecutionStatus.SUCCESS
        
        # Size-Validation Report (wenn verfügbar)
        if "size_validation" in tool_result:
            result["size_validation"] = tool_result["size_validation"]
        
        return result
    
    def _compare_screenshots(
        self,
        screenshot_before: str,
        screenshot_after: str
    ) -> float:
        """
        Vergleicht zwei Screenshots und gibt Änderungs-Prozent zurück.
        
        Args:
            screenshot_before: Base64-encoded PNG
            screenshot_after: Base64-encoded PNG
            
        Returns:
            Float 0.0-1.0 (Prozent geänderter Pixel)
        """
        try:
            # Decode base64
            img_before = Image.open(io.BytesIO(base64.b64decode(screenshot_before)))
            img_after = Image.open(io.BytesIO(base64.b64decode(screenshot_after)))
            
            # Resize wenn unterschiedliche Größen
            if img_before.size != img_after.size:
                img_after = img_after.resize(img_before.size)
            
            # Convert to RGB wenn nötig
            if img_before.mode != 'RGB':
                img_before = img_before.convert('RGB')
            if img_after.mode != 'RGB':
                img_after = img_after.convert('RGB')
            
            # Calculate difference
            diff = ImageChops.difference(img_before, img_after)
            
            # Count changed pixels (with threshold to ignore minor noise)
            changed_pixels = 0
            total_pixels = img_before.width * img_before.height
            
            for pixel in diff.getdata():
                # Pixel ist geändert wenn Summe > 30 (noise filter)
                if sum(pixel) > 30:
                    changed_pixels += 1
            
            return changed_pixels / total_pixels if total_pixels > 0 else 0.0
        
        except Exception as e:
            logger.error(f"Screenshot comparison error: {e}")
            return 0.0
    
    async def _request_replan(
        self,
        request: TaskExecutionRequest,
        executed_results: List[ToolExecutionResult],
        failed_step: ToolExecutionResult,
        remaining_rounds: int
    ) -> List[ActionStep]:
        """
        Fordert Re-Planning vom Planner an.
        
        Returns:
            Liste neuer ActionSteps oder leere Liste
        """
        replan_request = ReplanRequest(
            task_id=request.task_id,
            original_context=request.context,
            executed_steps=executed_results,
            failed_step=failed_step,
            error_context=failed_step.error_context or "Validation failed",
            remaining_rounds=remaining_rounds,
            request_id=request.request_id
        )
        
        # Versuche Callbacks
        for callback in self._on_replan_requested:
            try:
                new_steps = await callback(replan_request)
                if new_steps:
                    return new_steps
            except Exception as e:
                logger.error(f"Replan callback failed: {e}")
        
        # Fallback: LLM-basiertes Re-Planning
        if self.config.enable_llm_planning and self.client:
            return await self._llm_replan(replan_request)
        
        return []
    
    async def _llm_replan(self, replan_request: ReplanRequest) -> List[ActionStep]:
        """
        LLM-basiertes Re-Planning mit Fehlerkontext.
        """
        if not self.client:
            return []
        
        try:
            # Build replan prompt
            prompt = self._build_replan_prompt(replan_request)
            
            # Call LLM
            response = await self.client.chat(
                messages=[
                    {"role": "system", "content": self._get_replan_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                model=self.config.model,
                tools=get_tool_functions_schema()
            )
            
            # Parse tool calls from response
            if response and hasattr(response, 'tool_calls') and response.tool_calls:
                new_steps = []
                for i, tool_call in enumerate(response.tool_calls):
                    step = ActionStep(
                        step_id=f"replan_{i}_{int(time.time()*1000)}",
                        tool_name=ToolName(tool_call.function.name),
                        tool_params=tool_call.function.arguments,
                        expected_outcome=f"Korrektur für fehlgeschlagenen Step",
                        requires_validation=True
                    )
                    new_steps.append(step)
                
                return new_steps
            
            return []
        
        except Exception as e:
            logger.error(f"LLM replan failed: {e}")
            return []
    
    def _get_replan_system_prompt(self) -> str:
        """System-Prompt für Re-Planning."""
        return """Du bist ein Desktop-Automation Agent für Re-Planning.

Eine Aktion ist fehlgeschlagen und du musst eine korrigierte Aktion planen.

Analyse den Fehlerkontext und plane eine verbesserte Aktion.

Beachte:
- Verwende die verfügbaren Desktop-Tools
- Screenshot-Validation prüft ob sich der Bildschirm geändert hat
- Bei fehlenden visuellen Änderungen war die Aktion möglicherweise nicht erfolgreich
- Versuche alternative Ansätze wenn der erste fehlgeschlagen ist

Gib Tool-Calls zurück für die korrigierten Aktionen."""
    
    def _build_replan_prompt(self, request: ReplanRequest) -> str:
        """Baut den Re-Planning Prompt."""
        executed_summary = "\n".join([
            f"- {r.tool_name.value}: {'✓' if r.status == ExecutionStatus.SUCCESS else '✗'}"
            for r in request.executed_steps[-5:]  # Letzte 5 Steps
        ])
        
        return f"""TASK: {request.original_context.user_request}

BISHERIGE AKTIONEN:
{executed_summary}

FEHLGESCHLAGENE AKTION:
- Tool: {request.failed_step.tool_name.value}
- Fehler: {request.failed_step.error_context}
- Änderung erkannt: {request.failed_step.change_percentage:.1%}

VERBLEIBENDE RUNDEN: {request.remaining_rounds}

Bitte plane eine korrigierte Aktion um das Ziel zu erreichen."""
    
    async def execute_single_action(
        self,
        tool_name: ToolName,
        params: Dict[str, Any],
        context: Optional[TaskContext] = None
    ) -> ToolExecutionResult:
        """
        Führt eine einzelne Aktion aus (für direkte API-Calls).
        """
        step = ActionStep(
            step_id=f"single_{int(time.time()*1000)}",
            tool_name=tool_name,
            tool_params=params,
            expected_outcome="Single action execution",
            requires_validation=True
        )
        
        # Pre-Screenshot
        screenshot_before = await self.tool_executor.capture_full_screen() if self.config.enable_screenshots else None
        
        # Execute
        start_time = time.time()
        tool_result = await self.tool_executor.execute_tool(
            tool_name,
            params,
            ui_state=context.ui_state if context else None
        )
        
        await asyncio.sleep(0.2)
        
        # Post-Screenshot
        screenshot_after = await self.tool_executor.capture_full_screen() if self.config.enable_screenshots else None
        
        # Validate
        validation = await self._validate_step(
            step=step,
            tool_result=tool_result,
            screenshot_before=screenshot_before,
            screenshot_after=screenshot_after
        )
        
        return ToolExecutionResult(
            step_id=step.step_id,
            tool_name=tool_name,
            status=validation["status"],
            screenshot_before=screenshot_before,
            screenshot_after=screenshot_after,
            change_percentage=validation["change_percentage"],
            action_result=tool_result,
            error_context=validation.get("error"),
            duration_ms=(time.time() - start_time) * 1000
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Worker-Statistiken zurück."""
        return {
            "worker_id": self.config.worker_id,
            "is_running": self._is_running,
            "current_task": self._current_task,
            "tasks_processed": self._tasks_processed,
            "tasks_successful": self._tasks_successful,
            "tasks_failed": self._tasks_failed,
            "success_rate": self._tasks_successful / self._tasks_processed if self._tasks_processed > 0 else 0,
            "total_actions": self._total_actions,
            "total_validation_rounds": self._validation_rounds,
            "tool_executor_stats": self.tool_executor.get_execution_stats() if self.tool_executor else {}
        }


# ==================== AutoGen RoutedAgent Version ====================

if HAS_AUTOGEN:
    @type_subscription(topic_type="moire.execution")
    class ExecutionWorkerAgent(RoutedAgent):
        """
        AutoGen 0.4 gRPC Worker Agent für Task-Execution.
        """
        
        def __init__(self, config: Optional[ExecutionWorkerConfig] = None):
            super().__init__()
            self._worker = ExecutionWorker(config)
        
        @message_handler
        async def handle_execute_task(
            self,
            message: TaskExecutionRequest,
            ctx: MessageContext
        ) -> TaskExecutionResult:
            """Handler für TaskExecutionRequest."""
            return await self._worker.execute_task(message)


# ==================== Singleton ====================

_execution_worker_instance: Optional[ExecutionWorker] = None


def get_execution_worker() -> ExecutionWorker:
    """Gibt Singleton-Instanz des ExecutionWorkers zurück."""
    global _execution_worker_instance
    if _execution_worker_instance is None:
        _execution_worker_instance = ExecutionWorker()
    return _execution_worker_instance


# ==================== Test ====================

async def main():
    """Test des Execution Workers."""
    worker = ExecutionWorker()
    
    print("\n" + "=" * 60)
    print("Execution Worker Test")
    print("=" * 60)
    
    # Test-Task erstellen
    context = TaskContext(
        user_request="Teste Desktop-Automation",
        app_context={"active_window": "Test"},
        ui_state={"elements": []},
        screen_bounds={"width": 1920, "height": 1080}
    )
    
    # Einfacher Test: Warten und Screenshot
    action_plan = [
        ActionStep(
            step_id="test_1",
            tool_name=ToolName.WAIT,
            tool_params={"seconds": 0.5},
            expected_outcome="Wait completed",
            requires_validation=False
        ),
        ActionStep(
            step_id="test_2",
            tool_name=ToolName.CAPTURE_SCREENSHOT_REGION,
            tool_params={"x": 0, "y": 0, "width": 200, "height": 200},
            expected_outcome="Screenshot captured",
            requires_validation=False
        )
    ]
    
    request = TaskExecutionRequest(
        task_id="test_task_001",
        context=context,
        action_plan=action_plan,
        max_validation_rounds=3
    )
    
    print(f"\nTask: {request.task_id}")
    print(f"Steps: {len(action_plan)}")
    
    # Execute
    result = await worker.execute_task(request)
    
    print(f"\n--- Result ---")
    print(f"Success: {result.success}")
    print(f"Status: {result.status.value}")
    print(f"Steps: {result.steps_executed}/{result.steps_total}")
    print(f"Duration: {result.total_duration_ms:.0f}ms")
    
    for r in result.results:
        print(f"  - {r.tool_name.value}: {r.status.value} ({r.duration_ms:.0f}ms)")
    
    print(f"\n--- Stats ---")
    stats = worker.get_stats()
    print(f"Tasks: {stats['tasks_processed']} total, {stats['tasks_successful']} successful")
    print(f"Actions: {stats['total_actions']}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
