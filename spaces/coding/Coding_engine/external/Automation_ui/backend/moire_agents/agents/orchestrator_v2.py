"""
Orchestrator V2 - Event-driven Agent Koordination

Nutzt das neue Event Queue System für:
- Kontinuierliche Task-Verarbeitung
- Reasoning Agent für Planung
- Action Validation mit Timeout
- Screen State Monitoring
- Vision-basierte Element-Lokalisierung
- ContextTracker für Selektion/Cursor-Tracking
- Iterativer Workflow mit Goal-Detection
- Reflection-Loop mit max 3 Runden für Orchestrator-Intervention
"""

import asyncio
import logging
import time
import base64
import sys
import os
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum

# Ensure parent directory is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.event_queue import (
    EventQueue, TaskEvent, ActionEvent, ValidationEvent,
    TaskStatus, ActionStatus, get_event_queue
)
from core.openrouter_client import OpenRouterClient, get_openrouter_client
from agents.reasoning import ReasoningAgent, get_reasoning_agent
from validation.action_validator import ActionValidator, get_action_validator
from validation.state_comparator import ScreenState

# Import Vision Agent
try:
    from agents.vision_agent import VisionAnalystAgent, get_vision_agent
    HAS_VISION = True
except ImportError:
    HAS_VISION = False

# Import ContextTracker für Selektion/Cursor-Tracking
try:
    from context import (
        ContextTracker, SelectionManager, WordHelper,
        get_selection_manager, get_word_helper
    )
    HAS_CONTEXT = True
except ImportError:
    HAS_CONTEXT = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==================== Reflection Dataclasses ====================

class ReflectionStatus(Enum):
    """Status der Reflection-Analyse."""
    IN_PROGRESS = "in_progress"
    GOAL_ACHIEVED = "goal_achieved"
    NEEDS_CORRECTION = "needs_correction"
    MAX_ROUNDS_REACHED = "max_rounds_reached"
    FAILED = "failed"


@dataclass
class ReflectionRequest:
    """Anfrage für eine Reflection-Analyse."""
    task_id: str
    round_number: int
    screenshot_base64: str
    executed_actions: List[str]
    current_state: Dict[str, Any]
    original_goal: str
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReflectionResult:
    """Ergebnis einer Reflection-Analyse."""
    round_number: int
    goal_achieved: bool
    progress_score: float  # 0.0 - 1.0
    vision_analysis: str
    issues_detected: List[str]
    suggested_corrections: List[str]
    status: ReflectionStatus = ReflectionStatus.IN_PROGRESS
    screenshot_base64: Optional[str] = None
    context_state: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für Serialisierung."""
        return {
            "round_number": self.round_number,
            "goal_achieved": self.goal_achieved,
            "progress_score": self.progress_score,
            "vision_analysis": self.vision_analysis,
            "issues_detected": self.issues_detected,
            "suggested_corrections": self.suggested_corrections,
            "status": self.status.value,
            "has_screenshot": self.screenshot_base64 is not None,
            "context_state": self.context_state
        }


@dataclass
class TaskResult:
    """Ergebnis einer Task-Ausführung (für Batch-Execution)."""
    success: bool
    actions_executed: int = 0
    batches_executed: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None
    final_state: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für Serialisierung."""
        return {
            "success": self.success,
            "actions_executed": self.actions_executed,
            "batches_executed": self.batches_executed,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "final_state": self.final_state
        }


class OrchestratorV2:
    """
    Event-driven Orchestrator für das Agent-Team.
    
    Verbindet:
    - EventQueue für Task/Action Management
    - ReasoningAgent für Planung
    - InteractionAgent für Ausführung
    - ActionValidator für Validierung
    - MoireServer für Screen-State
    - VisionAgent für Element-Lokalisierung
    - ContextTracker für Selektion/Cursor-Tracking
    - Iterativer Workflow mit Goal-Detection
    """
    
    def __init__(
        self,
        event_queue: Optional[EventQueue] = None,
        openrouter_client: Optional[OpenRouterClient] = None,
        moire_client: Optional[Any] = None
    ):
        # Core Components
        self.queue = event_queue or get_event_queue()
        self.client = openrouter_client or get_openrouter_client()
        self.reasoning = get_reasoning_agent(self.client)
        self.validator = get_action_validator()
        
        # Vision Agent für Element-Lokalisierung
        self.vision_agent: Optional[VisionAnalystAgent] = None
        if HAS_VISION:
            try:
                self.vision_agent = get_vision_agent()
                logger.info("Vision Agent verfügbar für Element-Lokalisierung")
            except Exception as e:
                logger.warning(f"Vision Agent nicht verfügbar: {e}")
        
        # ContextTracker für Selektion/Cursor-Tracking
        self.context_tracker: Optional[ContextTracker] = None
        self.word_helper: Optional[WordHelper] = None
        if HAS_CONTEXT:
            try:
                self.context_tracker = ContextTracker()
                logger.info("ContextTracker verfügbar für Selektion-Tracking")
            except Exception as e:
                logger.warning(f"ContextTracker nicht verfügbar: {e}")
        
        # MoireServer WebSocket Client
        self.moire_client = moire_client
        
        # Interaction Agent (wird später gesetzt)
        self._interaction_agent: Optional[Any] = None
        
        # State
        self._running = False
        self._current_screen_state: Optional[Dict[str, Any]] = None
        self._last_screenshot: Optional[bytes] = None

        # Initial State Storage (für erste Task-Planung)
        self._initial_screenshot: Optional[bytes] = None
        self._initial_state: Optional[Dict[str, Any]] = None
        self._initial_timestamp: float = 0

        # Iterativer Workflow State
        self._current_task: Optional[TaskEvent] = None
        self._iteration_count: int = 0
        self._max_iterations: int = 10
        self._goal_achieved: bool = False
        
        # Callbacks
        self._on_task_complete: List[Callable[[TaskEvent], None]] = []
        self._on_action_complete: List[Callable[[ActionEvent], None]] = []
        self._on_error: List[Callable[[str, Exception], None]] = []
        self._on_state_change: List[Callable[[Dict[str, Any]], None]] = []
        
        # Setup Event Handlers
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Konfiguriert Event Handler für die Queue."""
        self.queue.set_task_handler(self._handle_task_planning)
        self.queue.set_action_handler(self._handle_action_execution)
        self.queue.set_validation_handler(self._handle_validation)
        
        self.queue.on_task_complete(self._on_task_completed)
        self.queue.on_action_complete(self._on_action_completed)
        self.queue.on_error(self._on_queue_error)
        
        self.validator.set_screenshot_callback(self._capture_screenshot)
        self.validator.set_screen_state_callback(self._get_current_state)

    def _on_task_completed(self, task: TaskEvent):
        """Callback wenn Task abgeschlossen."""
        logger.info(f"Task abgeschlossen: {task.id} - Status: {task.status.value}")

    def _on_action_completed(self, action: ActionEvent, validation: ValidationEvent):
        """Callback wenn Aktion validiert."""
        logger.debug(f"Aktion abgeschlossen: {action.id} - Erfolg: {validation.success}")

    def _on_queue_error(self, context: str, error: Exception):
        """Callback bei Queue-Fehlern."""
        logger.error(f"Queue-Fehler in {context}: {error}")

    async def start(self):
        """Startet den Orchestrator und die Event Queue."""
        if self._running:
            logger.warning("Orchestrator already running")
            return

        self._running = True
        await self.queue.start()
        logger.info("Orchestrator gestartet")

    async def stop(self):
        """Stoppt den Orchestrator und die Event Queue."""
        self._running = False
        await self.queue.stop()
        logger.info("Orchestrator gestoppt")

    async def execute_task(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None
    ) -> TaskEvent:
        """
        Führt einen Task aus und wartet auf Abschluss.

        Args:
            goal: Das zu erreichende Ziel
            context: Optionaler Kontext

        Returns:
            TaskEvent mit Ergebnis
        """
        # Nutze execute_task_with_reflection
        result = await self.execute_task_with_reflection(
            goal=goal,
            context=context
        )

        # Erstelle TaskEvent aus Ergebnis
        task = TaskEvent(
            id=f"task_{int(time.time())}",
            goal=goal,
            status=TaskStatus.COMPLETED if result.get("success") else TaskStatus.FAILED,
            error=result.get("error"),
            actions=result.get("executed_actions", []),
            context=context or {}
        )

        return task

    def set_interaction_agent(self, agent: Any):
        """Setzt den Interaction Agent für Aktionsausführung."""
        self._interaction_agent = agent
        logger.info("Interaction Agent gesetzt")
        
        if HAS_CONTEXT and self._interaction_agent:
            try:
                self.word_helper = WordHelper(
                    interaction_agent=self._interaction_agent,
                    vision_agent=self.vision_agent
                )
                logger.info("WordHelper initialisiert für Word-Formatierung")
            except Exception as e:
                logger.warning(f"WordHelper nicht verfügbar: {e}")
    
    def set_moire_client(self, client: Any):
        """Setzt den MoireServer WebSocket Client."""
        self.moire_client = client
        logger.info("MoireServer Client gesetzt")

    def set_initial_state(self, screenshot: bytes, state: Dict[str, Any]):
        """
        Speichert initialen Screen-State für erste Task-Planung.

        Args:
            screenshot: Screenshot als bytes
            state: State mit OCR-Text, Boxes, etc.
        """
        self._initial_screenshot = screenshot
        self._initial_state = state
        self._initial_timestamp = time.time()
        self._last_screenshot = screenshot  # Auch als letzten Screenshot setzen
        self._current_screen_state = state  # Auch als aktuellen State setzen
        logger.info(f"Initial state gespeichert: {len(screenshot)} bytes, "
                   f"OCR: {len(state.get('ocr_text', ''))} Zeichen, "
                   f"Boxes: {len(state.get('boxes', []))}")

    def get_initial_state(self) -> Optional[Dict[str, Any]]:
        """Gibt initialen State zurück wenn vorhanden."""
        if self._initial_screenshot is None:
            return None
        return {
            "screenshot": self._initial_screenshot,
            "state": self._initial_state,
            "timestamp": self._initial_timestamp
        }

    # ==================== Event Handlers ====================
    
    async def _handle_task_planning(self, task: TaskEvent) -> List[ActionEvent]:
        """Plant Aktionen mit dem Reasoning Agent."""
        logger.info(f"Planning task: {task.goal}")
        
        screen_state = await self._get_current_state()
        screenshot_bytes = await self._capture_screenshot()
        
        actions = await self.reasoning.plan_task(
            task, 
            screen_state,
            screenshot_bytes
        )
        
        logger.info(f"Planned {len(actions)} actions for task {task.id}")
        return actions
    
    async def _handle_action_execution(self, action: ActionEvent) -> Dict[str, Any]:
        """Führt Aktion aus und aktualisiert ContextTracker."""
        logger.info(f"Executing action: {action.action_type} - {action.description}")
        
        action.screenshot_before = await self._capture_screenshot()
        
        if self._is_word_format_action(action):
            result = await self._execute_word_format_action(action)
        else:
            result = await self._execute_action(action)
        
        await asyncio.sleep(0.1)
        
        if self.context_tracker:
            try:
                await self.context_tracker.update_after_action(
                    action_type=action.action_type,
                    action_params=action.params
                )
                
                if self.context_tracker.selection.is_active:
                    text = self.context_tracker.selection.text or ""
                    logger.info(f"Aktuelle Selektion: '{text[:50]}...' "
                               f"({self.context_tracker.selection.word_count} Wörter)")
            except Exception as e:
                logger.warning(f"ContextTracker update failed: {e}")
        
        action.screenshot_after = await self._capture_screenshot()
        return result

    async def _execute_action(self, action: ActionEvent) -> Dict[str, Any]:
        """
        Führt eine Aktion über den Interaction Agent aus.

        Args:
            action: Die auszuführende Aktion

        Returns:
            Dict mit Ergebnis der Aktion
        """
        if not self._interaction_agent:
            return {"success": False, "error": "Kein Interaction Agent verfügbar"}

        action_type = action.action_type
        params = action.params

        try:
            if action_type == "click":
                x = params.get("x", 0)
                y = params.get("y", 0)
                return await self._interaction_agent.click(x, y)

            elif action_type == "double_click":
                x = params.get("x", 0)
                y = params.get("y", 0)
                return await self._interaction_agent.double_click(x, y)

            elif action_type == "right_click":
                x = params.get("x", 0)
                y = params.get("y", 0)
                return await self._interaction_agent.right_click(x, y)

            elif action_type == "type":
                text = params.get("text", "")
                return await self._interaction_agent.type_text(text)

            elif action_type == "press_key":
                key = params.get("key", "")
                return await self._interaction_agent.press_key(key)

            elif action_type == "hotkey":
                keys = params.get("keys", [])
                return await self._interaction_agent.hotkey(*keys)

            elif action_type == "scroll":
                direction = params.get("direction", "down")
                amount = params.get("amount", 3)
                clicks = amount if direction == "down" else -amount
                return await self._interaction_agent.scroll(clicks)

            elif action_type == "wait":
                duration = params.get("duration", 1.0)
                return await self._interaction_agent.wait(duration)

            elif action_type == "drag":
                start_x = params.get("start_x", 0)
                start_y = params.get("start_y", 0)
                end_x = params.get("end_x", 0)
                end_y = params.get("end_y", 0)
                return await self._interaction_agent.drag(start_x, start_y, end_x, end_y)

            elif action_type == "move":
                x = params.get("x", 0)
                y = params.get("y", 0)
                return await self._interaction_agent.move_to(x, y)

            else:
                return {"success": False, "error": f"Unbekannter Aktionstyp: {action_type}"}

        except Exception as e:
            logger.error(f"Fehler bei Aktionsausführung: {e}")
            return {"success": False, "error": str(e)}

    async def _handle_validation(
        self,
        action: ActionEvent,
        result: Dict[str, Any]
    ) -> ValidationEvent:
        """Validiert Ergebnis und analysiert State."""
        await asyncio.sleep(0.3)
        
        validation_result = await self.validator.validate_action(
            action,
            timeout=5.0,
            require_change=self._action_requires_change(action)
        )
        
        validation = await self.validator.create_validation_event(action, validation_result)
        
        logger.info(
            f"Validation: {'✓' if validation.success else '✗'} "
            f"(confidence: {validation.confidence:.2f})"
        )
        
        await self._analyze_state_after_action(action, validation)

        return validation

    def _action_requires_change(self, action: ActionEvent) -> bool:
        """Bestimmt ob eine Aktion eine Bildschirmänderung erwartet."""
        no_change_actions = {"wait", "move"}
        return action.action_type not in no_change_actions

    async def _analyze_state_after_action(
        self, 
        action: ActionEvent, 
        validation: ValidationEvent
    ):
        """Analysiert State nach jeder Aktion."""
        self._iteration_count += 1
        
        new_state = await self._get_current_state()
        new_screenshot = await self._capture_screenshot()
        
        for cb in self._on_state_change:
            try:
                cb(new_state)
            except Exception as e:
                logger.warning(f"State change callback error: {e}")
        
        if self._current_task and not self._goal_achieved:
            goal_check = await self._check_goal_achieved(
                self._current_task.goal,
                new_state,
                new_screenshot
            )
            
            if goal_check["achieved"]:
                self._goal_achieved = True
                logger.info(f"🎯 GOAL ERREICHT: {goal_check['reason']}")
            else:
                logger.info(f"📍 Goal noch nicht erreicht: {goal_check['reason']}")
                
                if self._iteration_count >= self._max_iterations:
                    logger.warning(f"⚠ Max Iterationen ({self._max_iterations}) erreicht!")

    async def _check_goal_achieved(
        self,
        goal: str,
        state: Dict[str, Any],
        screenshot: Optional[bytes]
    ) -> Dict[str, Any]:
        """Prüft ob das Ziel erreicht wurde."""
        goal_lower = goal.lower()
        
        if "öffne" in goal_lower or "open" in goal_lower:
            if state.get("elements"):
                return {"achieved": True, "reason": "App wurde geöffnet (Elemente erkannt)"}
        
        if "schreibe" in goal_lower or "type" in goal_lower or "tippe" in goal_lower:
            if self.context_tracker and self.context_tracker.selection.text:
                return {"achieved": True, "reason": "Text wurde eingegeben"}
        
        if "formatier" in goal_lower or "bold" in goal_lower or "fett" in goal_lower:
            if self.word_helper and screenshot:
                state_result = await self.word_helper.get_ribbon_state(screenshot)
                if state_result.get("bold_active"):
                    return {"achieved": True, "reason": "Text wurde fett formatiert"}
        
        if "markier" in goal_lower or "select" in goal_lower:
            if self.context_tracker and self.context_tracker.selection.is_active:
                text = self.context_tracker.selection.text or ""
                return {"achieved": True, "reason": f"Text markiert: '{text[:30]}...'"}
        
        if self.vision_agent and self.vision_agent.is_available() and screenshot:
            try:
                vision_check = await self._vision_goal_check(goal, screenshot)
                if vision_check["confidence"] > 0.7:
                    return {"achieved": vision_check["achieved"], "reason": vision_check["reason"]}
            except Exception as e:
                logger.warning(f"Vision goal check failed: {e}")
        
        return {"achieved": False, "reason": "Ziel noch nicht erreicht"}
    
    async def _vision_goal_check(self, goal: str, screenshot: bytes) -> Dict[str, Any]:
        """Nutzt Vision Agent für Goal-Check."""
        if not self.vision_agent:
            return {"achieved": False, "confidence": 0, "reason": "No vision agent"}
        
        try:
            # Encode screenshot to base64 for vision analysis
            screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')
            
            # Nutze Vision Agent für Goal-Analyse
            if hasattr(self.vision_agent, 'analyze_for_reflection'):
                result = await self.vision_agent.analyze_for_reflection(
                    screenshot=screenshot,
                    goal=goal,
                    executed_actions=[],
                    round_number=0
                )
                
                goal_achieved = result.get("goal_achieved", False)
                confidence = result.get("progress_score", 0.0) * 100
                reason = result.get("analysis", "Vision analysis completed")
                
                logger.info(f"Vision Goal Check: achieved={goal_achieved}, confidence={confidence:.0f}%")
                
                return {
                    "achieved": goal_achieved,
                    "confidence": confidence,
                    "reason": reason
                }
            
            # Fallback: Einfache Analyse
            if hasattr(self.vision_agent, 'analyze_screen'):
                analysis = await self.vision_agent.analyze_screen(screenshot_b64)
                if analysis:
                    # Prüfe ob das Ziel in der Analyse erwähnt wird
                    goal_keywords = goal.lower().split()
                    analysis_lower = analysis.lower()
                    matches = sum(1 for kw in goal_keywords if kw in analysis_lower)
                    confidence = (matches / len(goal_keywords)) * 100 if goal_keywords else 0
                    achieved = confidence > 50
                    
                    return {
                        "achieved": achieved,
                        "confidence": confidence,
                        "reason": analysis[:200]
                    }
            
            return {"achieved": False, "confidence": 0, "reason": "Vision analysis not available"}
            
        except Exception as e:
            logger.error(f"Vision goal check failed: {e}")
            return {"achieved": False, "confidence": 0, "reason": f"Error: {e}"}
    
    def _is_word_format_action(self, action: ActionEvent) -> bool:
        """Prüft ob es eine Word-Formatierungs-Aktion ist."""
        if not self.word_helper:
            return False
        
        format_types = ["format_bold", "format_italic", "format_underline", 
                       "select_paragraph", "select_word", "format_paragraph"]
        if action.action_type in format_types:
            return True
        
        format_keywords = ["bold", "fett", "italic", "kursiv", "underline", 
                         "unterstreichen", "formatier", "markier", "selektier"]
        desc_lower = action.description.lower()
        return any(kw in desc_lower for kw in format_keywords)
    
    async def _execute_word_format_action(self, action: ActionEvent) -> Dict[str, Any]:
        """Führt Word-Formatierungs-Aktion aus."""
        if not self.word_helper:
            return {"success": False, "error": "WordHelper nicht verfügbar"}
        
        action_type = action.action_type
        
        try:
            if action_type == "select_paragraph" or "absatz" in action.description.lower():
                result = await self.word_helper.select_paragraph()
                return {"success": result, "action": "select_paragraph"}
            
            elif action_type == "select_word" or "wort markier" in action.description.lower():
                result = await self.word_helper.select_word()
                return {"success": result, "action": "select_word"}
            
            elif action_type == "format_bold" or "fett" in action.description.lower() or "bold" in action.description.lower():
                result = await self.word_helper.bold()
                return {"success": result, "action": "format_bold"}
            
            elif action_type == "format_italic" or "kursiv" in action.description.lower() or "italic" in action.description.lower():
                result = await self.word_helper.italic()
                return {"success": result, "action": "format_italic"}
            
            elif action_type == "format_underline" or "unterstreich" in action.description.lower():
                result = await self.word_helper.underline()
                return {"success": result, "action": "format_underline"}
            
            elif action_type == "format_paragraph" or "absatz fett" in action.description.lower():
                success, state = await self.word_helper.format_paragraph_bold()
                return {
                    "success": success, 
                    "action": "format_paragraph_bold",
                    "formatting_state": {
                        "bold": state.bold if state else False,
                        "selection": state.text_selected if state else ""
                    }
                }
            
            else:
                return await self._execute_action(action)
        
        except Exception as e:
            logger.error(f"Word format action failed: {e}")
            return {"success": False, "error": str(e)}
    
    # ==================== Screen State ====================
    
    async def _capture_screenshot(self) -> Optional[bytes]:
        """Capture Screenshot via MoireServer mit proper waiting."""
        if not self.moire_client:
            logger.warning("No MoireServer client for screenshot")
            return None

        try:
            if hasattr(self.moire_client, 'ensure_connected'):
                await self.moire_client.ensure_connected()

            # Use the proven capture_and_wait_for_complete method
            if hasattr(self.moire_client, 'capture_and_wait_for_complete'):
                result = await self.moire_client.capture_and_wait_for_complete(timeout=10.0)
                if result.success and result.screenshot_base64:
                    # Convert base64 to bytes
                    screenshot_b64 = result.screenshot_base64
                    if screenshot_b64.startswith('data:'):
                        screenshot_b64 = screenshot_b64.split(',', 1)[1]
                    screenshot = base64.b64decode(screenshot_b64)
                    self._last_screenshot = screenshot
                    return screenshot

            # Fallback to old method if capture_and_wait_for_complete unavailable
            if hasattr(self.moire_client, 'request_capture'):
                await self.moire_client.request_capture()
                await asyncio.sleep(2.0)  # Increased timeout as fallback

            if hasattr(self.moire_client, 'get_last_screenshot'):
                screenshot = await self.moire_client.get_last_screenshot()
                if screenshot:
                    self._last_screenshot = screenshot
                    return screenshot

            return self._last_screenshot

        except Exception as e:
            logger.error(f"Screenshot capture failed: {e}")
            return None
    
    async def _get_current_state(self) -> Dict[str, Any]:
        """Holt aktuellen Screen-State."""
        if not self.moire_client:
            return {}
        
        try:
            if hasattr(self.moire_client, 'ensure_connected'):
                await self.moire_client.ensure_connected()
            
            if hasattr(self.moire_client, 'get_state'):
                state = await self.moire_client.get_state()
                self._current_screen_state = state
                return state
            
            return self._current_screen_state or {}
        
        except Exception as e:
            logger.error(f"Get state failed: {e}")
            return {}
    
    def update_screen_state(self, state: Dict[str, Any]):
        """Aktualisiert Screen-State von außen."""
        self._current_screen_state = state
    
    # ==================== Connection Guard ====================
    
    async def ensure_moire_connection(self) -> bool:
        """Prüft und stellt MoireServer-Verbindung sicher."""
        if not self.moire_client:
            logger.error("❌ Kein MoireServer Client konfiguriert!")
            return False
        
        try:
            if hasattr(self.moire_client, 'is_connected'):
                if not self.moire_client.is_connected:
                    logger.info("🔌 MoireServer nicht verbunden, verbinde...")
                    
                    if hasattr(self.moire_client, 'connect'):
                        connected = await self.moire_client.connect()
                        if not connected:
                            logger.error("❌ MoireServer Verbindung fehlgeschlagen!")
                            return False
                        logger.info("✓ MoireServer verbunden")
                    else:
                        return False
            
            if hasattr(self.moire_client, 'ensure_connected'):
                await self.moire_client.ensure_connected()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ MoireServer Connection Guard Fehler: {e}")
            return False
    
    async def check_connection_health(self) -> Dict[str, Any]:
        """Gibt detaillierten Verbindungsstatus zurück."""
        health = {
            "moire_client_set": self.moire_client is not None,
            "oire_connected": False,
            "interaction_agent_set": self._interaction_agent is not None,
            "vision_available": self.vision_agent is not None and (
                self.vision_agent.is_available() if self.vision_agent else False
            ),
            "context_tracker_available": self.context_tracker is not None,
            "last_state_timestamp": None,
            "errors": []
        }
        
        if self.moire_client:
            try:
                if hasattr(self.moire_client, 'is_connected'):
                    health["oire_connected"] = self.moire_client.is_connected
                
                if hasattr(self.moire_client, 'get_last_state_timestamp'):
                    health["last_state_timestamp"] = self.moire_client.get_last_state_timestamp()
            except Exception as e:
                health["errors"].append(f"Moire check error: {e}")
        
        return health
    
    # ==================== Reflection-Loop ====================
    
    async def execute_task_with_reflection(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        max_reflection_rounds: int = 3,
        actions_per_round: int = 3
    ) -> Dict[str, Any]:
        """
        Führt Task mit Reflection-Loop aus.
        
        Nach jedem Action-Batch wird ein Screenshot gemacht und der VisionAgent
        analysiert den Fortschritt. Bei Problemen wird der Orchestrator für
        Re-Planning eingeschaltet.
        
        Args:
            goal: Das zu erreichende Ziel
            context: Optionaler Kontext
            max_reflection_rounds: Maximale Anzahl Reflection-Runden (default: 3)
            actions_per_round: Aktionen pro Runde vor Reflection (default: 3)
            
        Returns:
            Dict mit Ergebnis und allen Reflection-Resultaten
        """
        logger.info(f"🔄 Starte Task mit Reflection-Loop: {goal}")
        logger.info(f"   Max Runden: {max_reflection_rounds}, Aktionen/Runde: {actions_per_round}")
        
        # Connection sicherstellen
        if not await self.ensure_moire_connection():
            return {
                "success": False,
                "error": "MoireServer nicht verbunden",
                "reflection_results": []
            }
        
        if not self._running:
            await self.start()
        
        # State für Reflection-Loop
        reflection_results: List[ReflectionResult] = []
        executed_actions: List[str] = []
        total_actions = 0
        final_status = ReflectionStatus.IN_PROGRESS
        
        # Initial-Screenshot
        initial_screenshot = await self._capture_screenshot()
        initial_state = await self._get_current_state()
        
        for round_num in range(1, max_reflection_rounds + 1):
            logger.info(f"\n{'='*50}")
            logger.info(f"📍 Reflection-Runde {round_num}/{max_reflection_rounds}")
            logger.info(f"{'='*50}")
            
            # Plane Aktionen für diese Runde
            round_context = {
                **(context or {}),
                "round_number": round_num,
                "previous_actions": executed_actions,
                "reflection_feedback": reflection_results[-1].to_dict() if reflection_results else None
            }
            
            # Task für diese Runde erstellen
            task = await self.queue.add_task(goal, round_context)
            self._current_task = task
            
            try:
                self.queue.set_task_handler(self._handle_task_planning)
                self.queue.set_action_handler(self._handle_action_execution)
                self.queue.set_validation_handler(self._handle_validation)
                self.queue.on_task_complete(self._on_task_completed)
                self.queue.on_action_complete(self._on_action_completed)
                self.queue.on_error(self._on_queue_error)
                self.validator.set_screenshot_callback(self._capture_screenshot)
                self.validator.set_screen_state_callback(self._get_current_state)
                # Warte auf Task-Completion oder führe max actions_per_round aus
                round_actions = []
                for action_num in range(actions_per_round):
                    try:
                        completed = await self.queue.wait_for_task(task.id, timeout=15.0)
                        
                        # Sammle ausgeführte Aktionen
                        for action in self.queue.get_task_actions(task.id):
                            if action.status == ActionStatus.COMPLETED:
                                round_actions.append(f"{action.action_type}: {action.description}")
                        
                        if completed.status == TaskStatus.COMPLETED:
                            break
                        if completed.status == TaskStatus.FAILED:
                            logger.warning(f"Runde {round_num} Aktion fehlgeschlagen")
                            break
                    
                    except TimeoutError:
                        logger.warning(f"Timeout bei Aktion {action_num + 1} in Runde {round_num}")
                        continue
                    except Exception as e:
                        logger.error(f"Fehler bei Aktion {action_num + 1}: {e}")
                        break

                executed_actions.extend(round_actions)
                total_actions += len(round_actions)
                logger.info(f"   Ausgeführte Aktionen in Runde {round_num}: {len(round_actions)}")
                for action in round_actions:
                    logger.info(f"   - {action}")
            
            except Exception as e:
                logger.error(f"Fehler in Runde {round_num}: {e}")
                round_actions = []
            
            finally:
                self._current_task = None
            
            # Reflection durchführen - Screenshot für Vision-Analyse erfassen
            reflection_screenshot = await self._capture_screenshot()
            reflection_screenshot_b64 = ""
            if reflection_screenshot:
                reflection_screenshot_b64 = base64.b64encode(reflection_screenshot).decode('utf-8')
                logger.info(f"📸 Reflection-Screenshot erfasst: {len(reflection_screenshot)} bytes")
            else:
                logger.warning("⚠ Kein Screenshot für Reflection verfügbar")

            # Aktuellen Screen-State für Kontext holen
            current_state = await self._get_current_state()

            reflection_request = ReflectionRequest(
                task_id=task.id,
                round_number=round_num,
                screenshot_base64=reflection_screenshot_b64,
                executed_actions=executed_actions,
                current_state=current_state,
                original_goal=goal,
                context=round_context
            )
            
            reflection_result = await self._perform_reflection(reflection_request)
            reflection_results.append(reflection_result)
            
            logger.info(f"\n📊 Reflection-Ergebnis Runde {round_num}:")
            logger.info(f"   Goal erreicht: {reflection_result.goal_achieved}")
            logger.info(f"   Progress Score: {reflection_result.progress_score:.2f}")
            logger.info(f"   Status: {reflection_result.status.value}")
            
            if reflection_result.issues_detected:
                logger.info(f"   Issues: {reflection_result.issues_detected}")
            
            # Prüfe ob Ziel erreicht
            if reflection_result.goal_achieved:
                final_status = ReflectionStatus.GOAL_ACHIEVED
                logger.info(f"🎯 ZIEL ERREICHT nach Runde {round_num}!")
                break
                
            # Prüfe ob Korrektur nötig
            if reflection_result.status == ReflectionStatus.NEEDS_CORRECTION:
                logger.info(f"🔧 Orchestrator Re-Planning für Runde {round_num + 1}...")
                
                # Re-Planning mit Feedback
                replan_result = await self._orchestrator_replan(
                    goal=goal,
                    reflection=reflection_result,
                    executed_actions=executed_actions
                )
                
                if replan_result.get("abort"):
                    logger.warning(f"⚠ Orchestrator empfiehlt Abbruch: {replan_result.get('reason')}")
                    final_status = ReflectionStatus.FAILED
                    break
                    
                # Aktualisiere Kontext mit neuen Anweisungen
                context = {
                    **(context or {}),
                    "correction_instructions": replan_result.get("instructions", []),
                    "priority_actions": replan_result.get("priority_actions", [])
                }
        
        # Max Runden erreicht ohne Erfolg
        if final_status == ReflectionStatus.IN_PROGRESS:
            final_status = ReflectionStatus.MAX_ROUNDS_REACHED
            logger.warning(f"⚠ Max Reflection-Runden ({max_reflection_rounds}) erreicht ohne Zielerreichung")
        
        # Final Screenshot
        final_screenshot = await self._capture_screenshot()
        
        return {
            "success": final_status == ReflectionStatus.GOAL_ACHIEVED,
            "status": final_status.value,
            "goal": goal,
            "total_rounds": len(reflection_results),
            "total_actions": total_actions,
            "executed_actions": executed_actions,
            "reflection_results": [r.to_dict() for r in reflection_results],
            "final_screenshot_available": final_screenshot is not None
        }
    
    async def _perform_reflection(self, request: ReflectionRequest) -> ReflectionResult:
        """
        Führt Reflection-Analyse durch.
        
        Kombiniert:
        - Screenshot des aktuellen Zustands
        - Vision-Analyse des Fortschritts
        - ContextTracker State
        - Goal-Achievement Check
        """
        logger.info(f"🔍 Führe Reflection durch für Runde {request.round_number}...")
        
        # Aktueller Screenshot
        screenshot = await self._capture_screenshot()
        screenshot_b64 = ""
        
        if screenshot:
            screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')
            logger.info(f"   Screenshot erfasst: {len(screenshot)} bytes")
        else:
            logger.warning("   ⚠ Kein Screenshot verfügbar!")
        
        # Aktueller State
        current_state = await self._get_current_state()
        
        # Context State
        context_state = {}
        if self.context_tracker:
            context_state = {
                "selection_active": self.context_tracker.selection.is_active,
                "selection_text": self.context_tracker.selection.text,
                "word_count": self.context_tracker.selection.word_count,
                "app_type": self.context_tracker.app.app_type.value,
                "window_title": self.context_tracker.app.window_title
            }
        
        # Vision-Analyse mit spezialisierter Methode
        vision_analysis = ""
        progress_score = 0.0
        issues_detected = []
        suggested_corrections = []
        goal_achieved = False
        
        # Prüfe Vision-Verfügbarkeit
        vision_available = (
            self.vision_agent is not None and 
            self.vision_agent.is_available() and 
            screenshot is not None
        )
        
        logger.info(f"   Vision Agent verfügbar: {self.vision_agent is not None}")
        logger.info(f"   Vision Agent is_available(): {self.vision_agent.is_available() if self.vision_agent else False}")
        logger.info(f"   Screenshot vorhanden: {screenshot is not None}")
        
        if vision_available:
            try:
                logger.info("   🔎 Starte Vision-Analyse...")
                
                # Nutze die speziailisierte analyze_for_reflection Methode
                reflection_result = await self.vision_agent.analyze_for_reflection(
                    screenshot=screenshot,
                    goal=request.original_goal,
                    executed_actions=request.executed_actions,
                    round_number=request.round_number
                )
                
                # Extrahiere Ergebnisse
                goal_achieved = reflection_result.get("goal_achieved", False)
                progress_score = reflection_result.get("progress_score", 0.0)
                issues_detected = reflection_result.get("issues", [])
                suggested_corrections = reflection_result.get("corrections", [])
                vision_analysis = reflection_result.get("analysis", "")
                
                logger.info(f"   Vision-Analyse erfolgreich:")
                logger.info(f"      - Goal achieved: {goal_achieved}")
                logger.info(f"      - Progress: {progress_score:.2f}")
                logger.info(f"      - Issues: {len(issues_detected)}")
                
            except Exception as e:
                logger.error(f"   ❌ Vision-Analyse fehlgeschlagen: {e}")
                vision_analysis = f"Analyse-Fehler: {e}"
                # Fallback zu heuristischer Prüfung
                goal_check = await self._check_goal_achieved(
                    request.original_goal,
                    current_state,
                    screenshot
                )
                goal_achieved = goal_check.get("achieved", False)
                progress_score = 0.5 if goal_achieved else 0.2
        
        else:
            # Fallback ohne Vision: Simple heuristic check
            logger.warning("   ⚠ Keine Vision-Analyse möglich, nutze Heuristik")
            goal_check = await self._check_goal_achieved(
                request.original_goal,
                current_state,
                screenshot
            )
            goal_achieved = goal_check.get("achieved", False)
            vision_analysis = goal_check.get("reason", "Keine Vision-Analyse verfügbar")
            progress_score = 0.8 if goal_achieved else 0.3
        
        # Bestimme Status
        status = ReflectionStatus.IN_PROGRESS
        if goal_achieved:
            status = ReflectionStatus.GOAL_ACHIEVED
        elif issues_detected or progress_score < 0.3:
            status = ReflectionStatus.NEEDS_CORRECTION
        
        return ReflectionResult(
            round_number=request.round_number,
            goal_achieved=goal_achieved,
            progress_score=progress_score,
            vision_analysis=vision_analysis,
            issues_detected=issues_detected,
            suggested_corrections=suggested_corrections,
            status=status,
            screenshot_base64=screenshot_b64 if screenshot else None,
            context_state=context_state
        )
    
    async def _orchestrator_replan(
        self,
        goal: str,
        reflection: ReflectionResult,
        executed_actions: List[str]
    ) -> Dict[str, Any]:
        """
        Orchestrator Re-Planning basierend auf Reflection-Feedback.
        
        Nutzt den ReasoningAgent um korrigierte Aktionen zu planen.
        """
        logger.info(f"🧠 Orchestrator Re-Planning...")
        
        # Baue Re-Planning Prompt
        replan_context = f"""
REFLECTION-FEEDBACK:
- Runde: {reflection.round_number}
- Progress Score: {reflection.progress_score:.2f}
- Issues: {reflection.issues_detected}
- Vorgeschlagene Korrekturen: {reflection.suggested_corrections}
- Vision-Analyse: {reflection.vision_analysis[:500]}

BISHERIGE AKTIONEN:
{chr(10).join(f"- {a}" for a in executed_actions[-10:])}

URSPRÜNGLICHES ZIEL: {goal}

Basierend auf dem Feedback, welche Korrekturen oder alternativen Aktionen werden empfohlen?
Soll der Task abgebrochen werden, wenn keine Fortschritte möglich sind?
"""
        
        try:
            # Nutze ReasoningAgent für Re-Planning
            screen_state = await self._get_current_state()
            screenshot = await self._capture_screenshot()
            
            # Erstelle einen Pseudo-Task für Re-Planning
            from core.event_queue import TaskEvent, TaskStatus
            replan_task = TaskEvent(
                id=f"replan_{int(time.time()*1000)}",
                goal=f"[REPLAN] {goal}\n\n{replan_context}",
                context={"is_replan": True, "reflection": reflection.to_dict()},
                status=TaskStatus.PENDING
            )
            
            # Plane neue Aktionen
            new_actions = await self.reasoning.plan_task(
                replan_task,
                screen_state,
                screenshot
            )
            
            if not new_actions:
                logger.warning("Re-Planning ergab keine neuen Aktionen")
                return {
                    "abort": True,
                    "reason": "Keine weiteren Aktionen möglich",
                    "instructions": [],
                    "priority_actions": []
                }
            
            # Extrahiere Anweisungen
            instructions = []
            priority_actions = []
            
            for action in new_actions[:5]:  # Max 5 Prioritäts-Aktionen
                priority_actions.append({
                    "type": action.action_type,
                    "description": action.description,
                    "params": action.params
                })
                instructions.append(f"{action.action_type}: {action.description}")
            
            logger.info(f"   Re-Planning ergab {len(priority_actions)} neue Prioritäts-Aktionen")
            
            return {
                "abort": False,
                "reason": "Re-Planning erfolgreich",
                "instructions": instructions,
                "priority_actions": priority_actions
            }
            
        except Exception as e:
            logger.error(f"Re-Planning fehlgeschlagen: {e}")
            return {
                "abort": True,
                "reason": f"Re-Planning Fehler: {e}",
                "instructions": [],
                "priority_actions": []
            }
    
    async def execute_task_async(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None
    ) -> TaskEvent:
        """Startet Task ohne zu warten."""
        if not self._running:
            await self.start()

        task = await self.queue.add_task(goal, context)
        return task

    # ==================== Batch Execution ====================

    async def execute_task_batched(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        batch_size: int = 5,
        checkpoint_interval: int = 3
    ) -> TaskResult:
        """
        Führt Task mit Batch-Execution aus.

        Features:
        - Plant alle Actions basierend auf initialem Screenshot
        - Gruppiert Actions in Batches für parallele Ausführung
        - Checkpoint-Validierung nach jedem Batch
        - Re-Planning bei Fehlern

        Args:
            goal: Ziel des Tasks
            context: Zusätzlicher Kontext
            batch_size: Anzahl Actions pro Batch
            checkpoint_interval: Batches zwischen Checkpoints
        """
        if not self._running:
            await self.start()

        logger.info(f"\n{'='*60}")
        logger.info(f"🚀 BATCH EXECUTION: {goal}")
        logger.info(f"   Batch-Größe: {batch_size}, Checkpoint-Intervall: {checkpoint_interval}")
        logger.info(f"{'='*60}\n")

        start_time = time.time()
        executed_actions = []
        total_batches = 0

        try:
            # 1. Initial Capture für Planung
            logger.info("📸 Erfasse initialen Screen-State...")
            screenshot = await self._capture_screenshot()
            screen_state = await self._get_current_state()

            if not screenshot:
                logger.error("Konnte keinen Screenshot erfassen!")
                return TaskResult(
                    success=False,
                    error="Screenshot capture failed",
                    actions_executed=0,
                    duration_ms=(time.time() - start_time) * 1000
                )

            # 2. Vision-Analyse für Kontext
            vision_context = {}
            if self.vision_agent and self.vision_agent.is_available():
                logger.info("👁 Vision-Analyse...")
                try:
                    vision_result = await self.vision_agent.analyze_screen_for_task(
                        screenshot=screenshot,
                        task_description=goal,
                        return_actionable_elements=True
                    )
                    vision_context = vision_result if isinstance(vision_result, dict) else {}
                except Exception as e:
                    logger.warning(f"Vision-Analyse fehlgeschlagen: {e}")

            # 3. Plane alle Actions auf einmal
            logger.info("🧠 Plane alle Actions...")
            plan_context = {
                **(context or {}),
                "screen_state": screen_state,
                "vision_context": vision_context,
                "batch_mode": True
            }

            all_actions = await self.reasoning.plan_task(
                goal=goal,
                screen_state=screen_state,
                screenshot=screenshot,
                context=plan_context
            )

            if not all_actions:
                logger.warning("Keine Actions geplant!")
                return TaskResult(
                    success=False,
                    error="No actions planned",
                    actions_executed=0,
                    duration_ms=(time.time() - start_time) * 1000
                )

            logger.info(f"   📋 {len(all_actions)} Actions geplant")

            # 4. Gruppiere in Batches
            batches = self._create_action_batches(all_actions, batch_size)
            logger.info(f"   📦 {len(batches)} Batches erstellt")

            # 5. Führe Batches aus
            for batch_idx, batch in enumerate(batches):
                total_batches += 1
                logger.info(f"\n▶ Batch {batch_idx + 1}/{len(batches)} ({len(batch)} Actions)")

                # Queue alle Actions im Batch
                batch_id = f"batch_{batch_idx}_{time.time()}"
                for action in batch:
                    action.batch_id = batch_id
                    await self.queue.action_queue.put(action)

                # Warte auf Batch-Completion
                batch_result = await self._wait_for_batch_completion(batch, timeout=60.0)
                executed_actions.extend(batch)

                logger.info(f"   ✓ Batch {batch_idx + 1} abgeschlossen: {batch_result['completed']}/{len(batch)} erfolgreich")

                # Checkpoint-Validierung
                if (batch_idx + 1) % checkpoint_interval == 0 or batch_idx == len(batches) - 1:
                    logger.info(f"   🔍 Checkpoint-Validierung...")
                    checkpoint_result = await self._validate_checkpoint(goal, executed_actions)

                    if checkpoint_result.get("goal_achieved"):
                        logger.info(f"🎯 ZIEL ERREICHT nach Batch {batch_idx + 1}!")
                        return TaskResult(
                            success=True,
                            actions_executed=len(executed_actions),
                            batches_executed=total_batches,
                            duration_ms=(time.time() - start_time) * 1000
                        )

                    if checkpoint_result.get("needs_replan"):
                        logger.info(f"   🔄 Re-Planning erforderlich...")
                        remaining_actions = await self._replan_from_checkpoint(
                            goal, checkpoint_result, executed_actions
                        )
                        if remaining_actions:
                            # Neue Batches erstellen und weiter
                            batches = self._create_action_batches(remaining_actions, batch_size)
                            # Setze batch_idx zurück für neue Batches
                            break

            # 6. Finale Validierung
            logger.info("\n📊 Finale Validierung...")
            final_screenshot = await self._capture_screenshot()
            final_result = await self._validate_final_result(goal, final_screenshot, executed_actions)

            duration_ms = (time.time() - start_time) * 1000
            logger.info(f"\n{'='*60}")
            logger.info(f"✅ BATCH EXECUTION ABGESCHLOSSEN")
            logger.info(f"   Actions: {len(executed_actions)}, Batches: {total_batches}")
            logger.info(f"   Dauer: {duration_ms:.0f}ms ({duration_ms/1000:.1f}s)")
            logger.info(f"   Erfolg: {final_result.get('success', False)}")
            logger.info(f"{'='*60}\n")

            return TaskResult(
                success=final_result.get("success", False),
                actions_executed=len(executed_actions),
                batches_executed=total_batches,
                duration_ms=duration_ms,
                final_state=final_result
            )

        except Exception as e:
            logger.error(f"Batch execution failed: {e}")
            return TaskResult(
                success=False,
                error=str(e),
                actions_executed=len(executed_actions),
                batches_executed=total_batches,
                duration_ms=(time.time() - start_time) * 1000
            )

    def _create_action_batches(
        self,
        actions: List[ActionEvent],
        batch_size: int
    ) -> List[List[ActionEvent]]:
        """Gruppiert Actions in Batches mit Dependency-Tracking."""
        batches = []
        current_batch = []
        prev_action_id = None

        for action in actions:
            # Setze Dependency auf vorherige Action (sequentielle Abhängigkeit)
            if prev_action_id and not action.can_parallel:
                action.depends_on = [prev_action_id]

            current_batch.append(action)
            prev_action_id = action.id

            if len(current_batch) >= batch_size:
                batches.append(current_batch)
                current_batch = []

        if current_batch:
            batches.append(current_batch)

        return batches

    async def _wait_for_batch_completion(
        self,
        batch: List[ActionEvent],
        timeout: float = 60.0
    ) -> Dict[str, Any]:
        """Wartet auf Completion eines Batches."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Prüfe ob alle Actions abgeschlossen
            completed = sum(
                1 for a in batch
                if a.status in [ActionStatus.COMPLETED, ActionStatus.FAILED, ActionStatus.SKIPPED]
            )

            if completed >= len(batch):
                return {
                    "completed": sum(1 for a in batch if a.status == ActionStatus.COMPLETED),
                    "failed": sum(1 for a in batch if a.status == ActionStatus.FAILED),
                    "skipped": sum(1 for a in batch if a.status == ActionStatus.SKIPPED)
                }

            await asyncio.sleep(0.1)  # 100ms poll interval

        # Timeout
        return {
            "completed": sum(1 for a in batch if a.status == ActionStatus.COMPLETED),
            "failed": sum(1 for a in batch if a.status == ActionStatus.FAILED),
            "skipped": sum(1 for a in batch if a.status == ActionStatus.SKIPPED),
            "timeout": True
        }

    async def _validate_checkpoint(
        self,
        goal: str,
        executed_actions: List[ActionEvent]
    ) -> Dict[str, Any]:
        """Validiert Fortschritt an einem Checkpoint."""
        screenshot = await self._capture_screenshot()
        if not screenshot:
            return {"needs_replan": False, "goal_achieved": False}

        # Vision-basierte Validierung wenn verfügbar
        if self.vision_agent and self.vision_agent.is_available():
            try:
                validation = await self.vision_agent.analyze_with_prompt(
                    screenshot=screenshot,
                    prompt=f"""Analysiere den aktuellen Bildschirmzustand.

Ursprüngliches Ziel: {goal}

Ausgeführte Aktionen:
{chr(10).join(f"- {a.description}" for a in executed_actions[-5:])}

Fragen:
1. Wurde das Ziel erreicht? (ja/nein)
2. Gibt es Fehler oder unerwartete Zustände?
3. Sind weitere Aktionen nötig?

Antworte als JSON:
{{"goal_achieved": true/false, "needs_replan": true/false, "issues": [], "next_steps": []}}"""
                )
                return validation if isinstance(validation, dict) else {"needs_replan": False, "goal_achieved": False}
            except Exception as e:
                logger.warning(f"Checkpoint-Validierung fehlgeschlagen: {e}")

        return {"needs_replan": False, "goal_achieved": False}

    async def _replan_from_checkpoint(
        self,
        goal: str,
        checkpoint_result: Dict[str, Any],
        executed_actions: List[ActionEvent]
    ) -> List[ActionEvent]:
        """Re-Plant verbleibende Actions nach Checkpoint."""
        screenshot = await self._capture_screenshot()
        screen_state = await self._get_current_state()

        context = {
            "replan": True,
            "checkpoint_issues": checkpoint_result.get("issues", []),
            "executed_actions": [a.description for a in executed_actions],
            "next_steps_hint": checkpoint_result.get("next_steps", [])
        }

        try:
            new_actions = await self.reasoning.plan_task(
                goal=goal,
                screen_state=screen_state,
                screenshot=screenshot,
                context=context
            )
            return new_actions or []
        except Exception as e:
            logger.error(f"Re-Planning fehlgeschlagen: {e}")
            return []

    async def _validate_final_result(
        self,
        goal: str,
        screenshot: Optional[bytes],
        executed_actions: List[ActionEvent]
    ) -> Dict[str, Any]:
        """Validiert das finale Ergebnis."""
        if not screenshot:
            return {"success": False, "reason": "No screenshot available"}

        success_count = sum(1 for a in executed_actions if a.status == ActionStatus.COMPLETED)
        fail_count = sum(1 for a in executed_actions if a.status == ActionStatus.FAILED)

        # Basis-Erfolg wenn > 50% Actions erfolgreich
        base_success = success_count > len(executed_actions) * 0.5

        if self.vision_agent and self.vision_agent.is_available():
            try:
                validation = await self.vision_agent.analyze_with_prompt(
                    screenshot=screenshot,
                    prompt=f"""Wurde folgendes Ziel erreicht: "{goal}"?
Antworte mit {{"success": true/false, "confidence": 0.0-1.0, "reason": "..."}}"""
                )
                if isinstance(validation, dict):
                    return validation
            except Exception as e:
                logger.warning(f"Finale Validierung fehlgeschlagen: {e}")

        return {
            "success": base_success,
            "confidence": 0.6 if base_success else 0.3,
            "reason": f"{success_count} erfolgreich, {fail_count} fehlgeschlagen von {len(executed_actions)} Actions"
        }

    def on_task_complete(self, callback: Callable[[TaskEvent], None]):
        """Registriert Callback für Task-Abschluss."""
        self._on_task_complete.append(callback)
    
    def on_action_execute(self, callback: Callable[[ActionEvent], None]):
        """Registriert Callback für Aktionsausführung."""
        self._on_action_complete.append(callback)
    
    def on_error(self, callback: Callable[[str, Exception], None]):
        """Registriert Error-Callback."""
        self._on_error.append(callback)
    
    def on_state_change(self, callback: Callable[[Dict[str, Any]], None]):
        """Registriert Callback für State-Änderungen."""
        self._on_state_change.append(callback)
    
    def get_status(self) -> Dict[str, Any]:
        """Gibt Status zurück."""
        status = {
            "running": self._running,
            "queue": self.queue.get_status(),
            "reasoning": self.reasoning.get_stats(),
            "validation": self.validator.get_stats(),
            "has_moire_client": self.moire_client is not None,
            "has_interaction_agent": self._interaction_agent is not None,
            "has_vision_agent": self.vision_agent is not None and self.vision_agent.is_available(),
            "has_context_tracker": self.context_tracker is not None,
            "has_word_helper": self.word_helper is not None
        }
        
        if self.context_tracker:
            status["context"] = {
                "selection_active": self.context_tracker.selection.is_active,
                "selection_text": self.context_tracker.selection.text[:100] if self.context_tracker.selection.text else "",
                "app_type": self.context_tracker.app.app_type.value,
                "window_title": self.context_tracker.app.window_title
            }
        
        return status
    
    def get_active_tasks(self) -> List[TaskEvent]:
        """Gibt aktive Tasks zurück."""
        return self.queue.get_all_tasks()
    
    async def get_current_selection(self) -> Optional[str]:
        """Gibt aktuelle Selektion zurück."""
        if not self.context_tracker:
            return None
        
        await self.context_tracker._capture_selection()
        
        if self.context_tracker.selection.is_active:
            return self.context_tracker.selection.text
        return None
    
    async def is_text_selected(self) -> bool:
        """Prüft ob Text selektiert ist."""
        if not self.context_tracker:
            return False
        
        return self.context_tracker.has_selection


# Singleton
_orchestrator_v2_instance: Optional[OrchestratorV2] = None


def get_orchestrator_v2() -> OrchestratorV2:
    """Gibt Singleton-Instanz des Orchestrators zurück."""
    global _orchestrator_v2_instance
    if _orchestrator_v2_instance is None:
        _orchestrator_v2_instance = OrchestratorV2()
    return _orchestrator_v2_instance


async def shutdown_orchestrator():
    """Fährt den Orchestrator herunter."""
    global _orchestrator_v2_instance
    if _orchestrator_v2_instance:
        await _orchestrator_v2_instance.stop()
        _orchestrator_v2_instance = None