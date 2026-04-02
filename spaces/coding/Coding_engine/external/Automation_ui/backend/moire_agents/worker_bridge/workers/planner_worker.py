"""
Planner Worker für MoireTracker Tool-Using Agents

Erstellt Action Plans aus User-Requests via LLM:
1. Analysiert User-Request und UI-State
2. Generiert sequentielle Action-Steps
3. Wählt passende Tools aus verfügbaren Desktop-Tools
4. Schätzt Parameter basierend auf UI-Element-Positionen
5. Unterstützt Re-Planning nach fehlgeschlagenen Actions
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
import uuid

# Add parent paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Internal Imports
from worker_bridge.messages import (
    ToolName,
    ExecutionStatus,
    TaskContext,
    ActionStep,
    TaskExecutionRequest,
    ToolExecutionResult,
    ReplanRequest
)

from worker_bridge.workers.desktop_tools import (
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


# ==================== System Prompts ====================

PLANNING_SYSTEM_PROMPT = """Du bist ein Desktop-Automation Planner Agent.

Deine Aufgabe ist es, User-Anfragen in konkrete Desktop-Aktionen zu übersetzen.

## Verfügbare Tools:
- capture_screenshot_region: Screenshot eines Bereichs aufnehmen
- click_at_position: An Position klicken
- double_click_at_position: Doppelklick an Position
- right_click_at_position: Rechtsklick an Position
- type_text: Text eingeben
- press_key: Taste drücken (Enter, Tab, Escape, etc.)
- key_combination: Tastenkombination (Ctrl+C, Alt+Tab, etc.)
- scroll: Scrollen
- drag_and_drop: Drag & Drop
- wait: Warten
- wait_for_element: Auf Element warten

## Regeln:
1. Analysiere den UI-State um Element-Positionen zu finden
2. Plane Aktionen in logischer Reihenfolge
3. Füge wait-Schritte ein wenn UI-Updates erwartet werden
4. Verwende präzise Koordinaten basierend auf Element-Bounds
5. Bei Texteingabe: erst klicken, dann tippen

## Output-Format:
Gib Tool-Calls zurück die die Aktionen beschreiben.
Jeder Tool-Call wird zu einem ActionStep konvertiert."""

REPLAN_SYSTEM_PROMPT = """Du bist ein Desktop-Automation Re-Planner Agent.

Eine vorherige Aktion ist fehlgeschlagen. Analysiere den Fehler und plane eine korrigierte Aktion.

## Fehlermöglichkeiten:
- Element nicht gefunden → andere Position versuchen
- Keine Bildschirmänderung → Aktion war nicht erfolgreich
- Falsches Element → Koordinaten korrigieren
- UI nicht bereit → wait-Step einfügen

## Regeln:
1. Analysiere den Fehlerkontext
2. Prüfe ob die Koordinaten korrekt waren
3. Überlege alternative Ansätze
4. Plane maximal 2 Korrektur-Schritte

Gib Tool-Calls zurück für die korrigierten Aktionen."""


class PlannerWorkerConfig:
    """Konfiguration für den Planner Worker."""
    worker_id: str = "planner_worker"
    model: str = "google/gemini-2.0-flash-001"
    max_planning_steps: int = 10
    enable_tool_calling: bool = True
    temperature: float = 0.3


class PlannerWorker:
    """
    Planner Worker für Task-Planning.
    
    Workflow:
    1. Empfängt User-Request + UI-State
    2. Generiert Action Plan via LLM
    3. Konvertiert Tool-Calls zu ActionSteps
    4. Unterstützt Re-Planning bei Fehlern
    """
    
    def __init__(
        self,
        config: Optional[PlannerWorkerConfig] = None,
        openrouter_client: Optional[OpenRouterClient] = None
    ):
        self.config = config or PlannerWorkerConfig()
        self.client = openrouter_client or (get_openrouter_client() if HAS_OPENROUTER else None)
        
        # Stats
        self._plans_created: int = 0
        self._replans_created: int = 0
        self._total_steps_planned: int = 0
        
        logger.info(f"PlannerWorker initialisiert: {self.config.worker_id}")
        logger.info(f"  Model: {self.config.model}")
        logger.info(f"  OpenRouter: {'verfügbar' if self.client else 'nicht verfügbar'}")
    
    async def create_plan(
        self,
        user_request: str,
        ui_state: Dict[str, Any],
        screen_bounds: Dict[str, int],
        app_context: Optional[Dict[str, Any]] = None
    ) -> List[ActionStep]:
        """
        Erstellt Action Plan für User-Request.
        
        Args:
            user_request: Natürlichsprachliche Anfrage
            ui_state: Aktueller UI-Zustand mit Elementen
            screen_bounds: Bildschirmgröße
            app_context: Optionaler App-Kontext
            
        Returns:
            Liste von ActionSteps
        """
        logger.info(f"\n{'='*50}")
        logger.info(f"[Planner] Erstelle Plan für: {user_request[:100]}...")
        logger.info(f"{'='*50}")
        
        if not self.client:
            logger.warning("Kein OpenRouter Client - Fallback zu einfachem Plan")
            return self._create_fallback_plan(user_request, ui_state)
        
        try:
            # Build prompt
            prompt = self._build_planning_prompt(
                user_request, ui_state, screen_bounds, app_context
            )
            
            # Get tool schema
            tools = get_tool_functions_schema()
            
            # Call LLM
            response = await self.client.chat(
                messages=[
                    {"role": "system", "content": PLANNING_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                model=self.config.model,
                tools=tools,
                temperature=self.config.temperature
            )
            
            # Parse tool calls
            action_steps = self._parse_tool_calls_to_steps(response)
            
            # Limit steps
            if len(action_steps) > self.config.max_planning_steps:
                logger.warning(f"Plan hat {len(action_steps)} Steps, limitiere auf {self.config.max_planning_steps}")
                action_steps = action_steps[:self.config.max_planning_steps]
            
            # Stats
            self._plans_created += 1
            self._total_steps_planned += len(action_steps)
            
            logger.info(f"[Planner] Plan erstellt: {len(action_steps)} Steps")
            for i, step in enumerate(action_steps):
                logger.info(f"  {i+1}. {step.tool_name.value}: {step.expected_outcome}")
            
            return action_steps
            
        except Exception as e:
            logger.error(f"[Planner] Fehler bei Plan-Erstellung: {e}")
            return self._create_fallback_plan(user_request, ui_state)
    
    async def create_replan(
        self,
        replan_request: ReplanRequest
    ) -> List[ActionStep]:
        """
        Erstellt Re-Plan nach fehlgeschlagener Aktion.
        
        Args:
            replan_request: ReplanRequest mit Fehlerkontext
            
        Returns:
            Liste korrigierter ActionSteps
        """
        logger.info(f"\n[Planner] Re-Planning für Task: {replan_request.task_id}")
        logger.info(f"  Fehler: {replan_request.error_context}")
        
        if not self.client:
            logger.warning("Kein OpenRouter Client - kein Re-Plan möglich")
            return []
        
        try:
            # Build replan prompt
            prompt = self._build_replan_prompt(replan_request)
            
            # Get tool schema
            tools = get_tool_functions_schema()
            
            # Call LLM
            response = await self.client.chat(
                messages=[
                    {"role": "system", "content": REPLAN_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                model=self.config.model,
                tools=tools,
                temperature=self.config.temperature
            )
            
            # Parse tool calls
            action_steps = self._parse_tool_calls_to_steps(response, prefix="replan")
            
            # Limit replan steps
            if len(action_steps) > 3:
                action_steps = action_steps[:3]
            
            # Stats
            self._replans_created += 1
            self._total_steps_planned += len(action_steps)
            
            logger.info(f"[Planner] Re-Plan erstellt: {len(action_steps)} Steps")
            
            return action_steps
            
        except Exception as e:
            logger.error(f"[Planner] Fehler bei Re-Planning: {e}")
            return []
    
    def _build_planning_prompt(
        self,
        user_request: str,
        ui_state: Dict[str, Any],
        screen_bounds: Dict[str, int],
        app_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Baut den Planning Prompt."""
        
        # Extract elements from UI state
        elements_info = self._format_ui_elements(ui_state)
        
        prompt = f"""## User Request
{user_request}

## Screen Bounds
Width: {screen_bounds.get('width', 1920)}px
Height: {screen_bounds.get('height', 1080)}px

## Current UI State
{elements_info}
"""
        
        if app_context:
            prompt += f"""
## App Context
Active Window: {app_context.get('activeWindow', 'Unknown')}
Application: {app_context.get('application', 'Unknown')}
"""
        
        prompt += """
## Task
Erstelle einen Action Plan um die User-Anfrage auszuführen.
Verwende die verfügbaren Tools und gib präzise Koordinaten an.
"""
        
        return prompt
    
    def _build_replan_prompt(self, request: ReplanRequest) -> str:
        """Baut den Re-Planning Prompt."""
        
        # Executed steps summary
        executed_summary = "\n".join([
            f"- Step {i+1}: {r.tool_name.value} → {'✓' if r.status == ExecutionStatus.SUCCESS else '✗'}"
            for i, r in enumerate(request.executed_steps[-5:])  # Last 5 steps
        ])
        
        # Failed step details
        failed_step = request.failed_step
        failed_details = f"""
Tool: {failed_step.tool_name.value}
Status: {failed_step.status.value}
Change: {failed_step.change_percentage:.1%}
Error: {failed_step.error_context or 'No error message'}
"""
        
        return f"""## Original Task
{request.original_context.user_request}

## Executed Steps
{executed_summary}

## Failed Step
{failed_details}

## Remaining Rounds: {request.remaining_rounds}

## Task
Analysiere den Fehler und erstelle einen korrigierten Plan.
Maximal 2 Schritte für die Korrektur.
"""
    
    def _format_ui_elements(self, ui_state: Dict[str, Any]) -> str:
        """Formatiert UI-Elemente für den Prompt."""
        elements = ui_state.get('elements', [])
        
        if not elements:
            return "Keine UI-Elemente verfügbar"
        
        # Limit to most relevant elements
        relevant_elements = elements[:20]
        
        lines = []
        for elem in relevant_elements:
            bounds = elem.get('bounds', {})
            category = elem.get('category', 'unknown')
            text = elem.get('text', '')
            
            x = bounds.get('x', 0)
            y = bounds.get('y', 0)
            w = bounds.get('width', 0)
            h = bounds.get('height', 0)
            
            # Center point
            cx = x + w // 2
            cy = y + h // 2
            
            line = f"- {category}"
            if text:
                line += f" '{text[:30]}'"
            line += f" @ ({cx}, {cy}) [{w}x{h}]"
            lines.append(line)
        
        return "\n".join(lines)
    
    def _parse_tool_calls_to_steps(
        self,
        response: Any,
        prefix: str = "step"
    ) -> List[ActionStep]:
        """Konvertiert LLM Tool-Calls zu ActionSteps."""
        steps = []
        
        if not response:
            return steps
        
        # Extract tool calls from response
        tool_calls = []
        
        if hasattr(response, 'tool_calls') and response.tool_calls:
            tool_calls = response.tool_calls
        elif hasattr(response, 'choices') and response.choices:
            first_choice = response.choices[0]
            if hasattr(first_choice, 'message') and hasattr(first_choice.message, 'tool_calls'):
                tool_calls = first_choice.message.tool_calls or []
        
        for i, tool_call in enumerate(tool_calls):
            try:
                # Extract function name and arguments
                func_name = None
                func_args = {}
                
                if hasattr(tool_call, 'function'):
                    func_name = tool_call.function.name
                    if hasattr(tool_call.function, 'arguments'):
                        args_str = tool_call.function.arguments
                        if isinstance(args_str, str):
                            func_args = json.loads(args_str)
                        else:
                            func_args = args_str
                elif isinstance(tool_call, dict):
                    func = tool_call.get('function', {})
                    func_name = func.get('name')
                    func_args = func.get('arguments', {})
                    if isinstance(func_args, str):
                        func_args = json.loads(func_args)
                
                if not func_name:
                    continue
                
                # Convert to ToolName enum
                try:
                    tool_name = ToolName(func_name)
                except ValueError:
                    logger.warning(f"Unknown tool: {func_name}")
                    continue
                
                # Create ActionStep
                step = ActionStep(
                    step_id=f"{prefix}_{i}_{uuid.uuid4().hex[:6]}",
                    tool_name=tool_name,
                    tool_params=func_args,
                    expected_outcome=self._generate_expected_outcome(tool_name, func_args),
                    requires_validation=tool_name not in [ToolName.WAIT, ToolName.WAIT_FOR_ELEMENT]
                )
                
                steps.append(step)
                
            except Exception as e:
                logger.warning(f"Error parsing tool call {i}: {e}")
                continue
        
        return steps
    
    def _generate_expected_outcome(
        self,
        tool_name: ToolName,
        params: Dict[str, Any]
    ) -> str:
        """Generiert erwartetes Ergebnis für einen Step."""
        
        outcomes = {
            ToolName.CLICK_AT_POSITION: f"Click at ({params.get('x', 0)}, {params.get('y', 0)})",
            ToolName.DOUBLE_CLICK_AT_POSITION: f"Double-click at ({params.get('x', 0)}, {params.get('y', 0)})",
            ToolName.RIGHT_CLICK_AT_POSITION: f"Right-click at ({params.get('x', 0)}, {params.get('y', 0)})",
            ToolName.TYPE_TEXT: f"Type text: {params.get('text', '')[:30]}",
            ToolName.PRESS_KEY: f"Press key: {params.get('key', '')}",
            ToolName.KEY_COMBINATION: f"Key combo: {params.get('keys', '')}",
            ToolName.SCROLL: f"Scroll {params.get('direction', 'down')} by {params.get('amount', 0)}",
            ToolName.DRAG_AND_DROP: f"Drag from ({params.get('start_x', 0)}, {params.get('start_y', 0)}) to ({params.get('end_x', 0)}, {params.get('end_y', 0)})",
            ToolName.WAIT: f"Wait {params.get('seconds', 0)} seconds",
            ToolName.WAIT_FOR_ELEMENT: f"Wait for element",
            ToolName.CAPTURE_SCREENSHOT_REGION: f"Capture region ({params.get('x', 0)}, {params.get('y', 0)}, {params.get('width', 0)}x{params.get('height', 0)})"
        }
        
        return outcomes.get(tool_name, f"Execute {tool_name.value}")
    
    def _create_fallback_plan(
        self,
        user_request: str,
        ui_state: Dict[str, Any]
    ) -> List[ActionStep]:
        """Erstellt einfachen Fallback-Plan ohne LLM."""
        
        # Check for common patterns
        request_lower = user_request.lower()
        
        steps = []
        
        # Screenshot capture request
        if 'screenshot' in request_lower or 'capture' in request_lower:
            steps.append(ActionStep(
                step_id=f"fallback_0_{uuid.uuid4().hex[:6]}",
                tool_name=ToolName.CAPTURE_SCREENSHOT_REGION,
                tool_params={"x": 0, "y": 0, "width": 1920, "height": 1080},
                expected_outcome="Capture full screen",
                requires_validation=False
            ))
        
        # Click request
        elif 'click' in request_lower or 'klick' in request_lower:
            # Try to find element
            elements = ui_state.get('elements', [])
            if elements:
                first_elem = elements[0]
                bounds = first_elem.get('bounds', {})
                x = bounds.get('x', 500) + bounds.get('width', 100) // 2
                y = bounds.get('y', 500) + bounds.get('height', 50) // 2
            else:
                x, y = 500, 500
            
            steps.append(ActionStep(
                step_id=f"fallback_0_{uuid.uuid4().hex[:6]}",
                tool_name=ToolName.CLICK_AT_POSITION,
                tool_params={"x": x, "y": y},
                expected_outcome=f"Click at ({x}, {y})",
                requires_validation=True
            ))
        
        # Type request
        elif 'type' in request_lower or 'text' in request_lower or 'eingeben' in request_lower:
            # Extract text to type (simple extraction)
            import re
            match = re.search(r'"([^"]+)"', user_request)
            text = match.group(1) if match else "Hello"
            
            steps.append(ActionStep(
                step_id=f"fallback_0_{uuid.uuid4().hex[:6]}",
                tool_name=ToolName.TYPE_TEXT,
                tool_params={"text": text},
                expected_outcome=f"Type: {text[:30]}",
                requires_validation=True
            ))
        
        # Default: just wait
        else:
            steps.append(ActionStep(
                step_id=f"fallback_0_{uuid.uuid4().hex[:6]}",
                tool_name=ToolName.WAIT,
                tool_params={"seconds": 1},
                expected_outcome="Wait 1 second",
                requires_validation=False
            ))
        
        logger.info(f"[Planner] Fallback-Plan erstellt: {len(steps)} Steps")
        return steps
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt Worker-Statistiken zurück."""
        return {
            "worker_id": self.config.worker_id,
            "model": self.config.model,
            "has_client": self.client is not None,
            "plans_created": self._plans_created,
            "replans_created": self._replans_created,
            "total_steps_planned": self._total_steps_planned,
            "avg_steps_per_plan": (
                self._total_steps_planned / self._plans_created
                if self._plans_created > 0 else 0
            )
        }


# ==================== Singleton ====================

_planner_worker_instance: Optional[PlannerWorker] = None


def get_planner_worker() -> PlannerWorker:
    """Gibt Singleton-Instanz des PlannerWorkers zurück."""
    global _planner_worker_instance
    if _planner_worker_instance is None:
        _planner_worker_instance = PlannerWorker()
    return _planner_worker_instance


# ==================== Test ====================

async def main():
    """Test des Planner Workers."""
    planner = PlannerWorker()
    
    print("\n" + "=" * 60)
    print("Planner Worker Test")
    print("=" * 60)
    
    # Test UI State
    ui_state = {
        "elements": [
            {
                "category": "button",
                "text": "Submit",
                "bounds": {"x": 100, "y": 200, "width": 80, "height": 30}
            },
            {
                "category": "input",
                "text": "",
                "bounds": {"x": 100, "y": 150, "width": 200, "height": 25}
            }
        ]
    }
    
    screen_bounds = {"width": 1920, "height": 1080}
    
    # Test 1: Simple click request
    print("\nTest 1: Click Request")
    steps = await planner.create_plan(
        "Klicke auf den Submit Button",
        ui_state,
        screen_bounds
    )
    print(f"  Generated {len(steps)} steps")
    for step in steps:
        print(f"    - {step.tool_name.value}: {step.expected_outcome}")
    
    # Test 2: Type request
    print("\nTest 2: Type Request")
    steps = await planner.create_plan(
        'Gib "Hello World" in das Eingabefeld ein',
        ui_state,
        screen_bounds
    )
    print(f"  Generated {len(steps)} steps")
    for step in steps:
        print(f"    - {step.tool_name.value}: {step.expected_outcome}")
    
    # Stats
    print("\n--- Stats ---")
    stats = planner.get_stats()
    print(f"Plans created: {stats['plans_created']}")
    print(f"Total steps: {stats['total_steps_planned']}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
