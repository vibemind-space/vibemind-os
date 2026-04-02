"""
Event Queue System - Kontinuierliche Task-Verarbeitung

Drei Queues:
- task_queue: Eingehende Tasks vom Benutzer
- action_queue: Geplante Aktionen vom Reasoning Agent
- result_queue: Validierungsergebnisse
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EventType(Enum):
    """Typen von Events im System."""
    TASK = "task"           # Neuer Task vom Benutzer
    ACTION = "action"       # Geplante Aktion
    RESULT = "result"       # Ausführungsergebnis
    VALIDATION = "validation"  # Validierungsergebnis
    STATE_CHANGE = "state_change"  # Bildschirmänderung
    ERROR = "error"         # Fehler


class TaskStatus(Enum):
    """Status eines Tasks."""
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionStatus(Enum):
    """Status einer Aktion."""
    PENDING = "pending"
    QUEUED = "queued"           # In Queue für Ausführung
    EXECUTING = "executing"
    EXECUTED = "executed"       # Ausgeführt, Validierung pending
    VALIDATING = "validating"   # Validierung läuft
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskEvent:
    """Ein Task der verarbeitet werden soll."""
    id: str
    goal: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    actions: List['ActionEvent'] = field(default_factory=list)
    current_action_idx: int = 0
    context: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class ActionEvent:
    """Eine einzelne Aktion."""
    id: str
    task_id: str
    action_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    status: ActionStatus = ActionStatus.PENDING
    created_at: float = field(default_factory=time.time)
    executed_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    validation: Optional[Dict[str, Any]] = None
    screenshot_before: Optional[str] = None
    screenshot_after: Optional[str] = None
    # ROI für fokussierte Validierung
    # Format: {origin_x, origin_y, base_width, base_height, zoom}
    roi: Optional[Dict[str, Any]] = None
    roi_description: Optional[str] = None
    # Batch & Dependency Tracking für parallele Ausführung
    batch_id: Optional[str] = None           # Welcher Batch
    depends_on: List[str] = field(default_factory=list)  # Action IDs die erst fertig sein müssen
    can_parallel: bool = True                # Parallelisierbar mit anderen Actions?
    priority: int = 0                        # Höher = früher ausführen


@dataclass
class ValidationEvent:
    """Validierungsergebnis einer Aktion."""
    action_id: str
    task_id: str
    success: bool
    confidence: float = 0.0
    description: str = ""
    state_changed: bool = False
    timestamp: float = field(default_factory=time.time)


class EventQueue:
    """
    Event Queue System für kontinuierliche Verarbeitung.
    
    Verwendet drei asyncio.Queue:
    - task_queue: Eingehende Tasks
    - action_queue: Geplante Aktionen
    - result_queue: Ergebnisse und Validierungen
    """
    
    def __init__(
        self,
        max_concurrent_tasks: int = 3,          # Erhöht von 1 auf 3
        max_concurrent_actions: int = 5,        # NEU: Parallele Actions
        max_concurrent_validations: int = 10,   # NEU: Parallele Validierungen
        action_timeout: float = 30.0,           # Reduziert von 60 auf 30
        validation_timeout: float = 3.0,        # Reduziert von 10 auf 3
        batch_size: int = 5                     # NEU: Actions pro Batch
    ):
        self.task_queue: asyncio.Queue[TaskEvent] = asyncio.Queue()
        self.action_queue: asyncio.Queue[ActionEvent] = asyncio.Queue()
        self.validation_queue: asyncio.Queue[ActionEvent] = asyncio.Queue()  # NEU: Separate Validation Queue
        self.result_queue: asyncio.Queue[ValidationEvent] = asyncio.Queue()

        self.max_concurrent_tasks = max_concurrent_tasks
        self.max_concurrent_actions = max_concurrent_actions
        self.max_concurrent_validations = max_concurrent_validations
        self.action_timeout = action_timeout
        self.validation_timeout = validation_timeout
        self.batch_size = batch_size

        # Active tasks
        self.active_tasks: Dict[str, TaskEvent] = {}
        self.completed_tasks: List[TaskEvent] = []

        # Handlers
        self._task_handler: Optional[Callable[[TaskEvent], Awaitable[List[ActionEvent]]]] = None
        self._action_handler: Optional[Callable[[ActionEvent], Awaitable[Dict[str, Any]]]] = None
        self._validation_handler: Optional[Callable[[ActionEvent, Dict[str, Any]], Awaitable[ValidationEvent]]] = None
        self._state_change_handler: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None

        # Event callbacks
        self._on_task_start: List[Callable[[TaskEvent], None]] = []
        self._on_task_complete: List[Callable[[TaskEvent], None]] = []
        self._on_action_start: List[Callable[[ActionEvent], None]] = []
        self._on_action_complete: List[Callable[[ActionEvent, ValidationEvent], None]] = []
        self._on_error: List[Callable[[str, Exception], None]] = []

        # State
        self._running = False
        self._task_counter = 0
        self._action_counter = 0

        # Processing tasks
        self._task_processor: Optional[asyncio.Task] = None
        self._action_processor: Optional[asyncio.Task] = None
        self._result_processor: Optional[asyncio.Task] = None
        self._validation_processor: Optional[asyncio.Task] = None  # NEU

        # Parallel execution tracking
        self._executing_actions: Dict[str, asyncio.Task] = {}    # NEU: Laufende Actions
        self._validating_actions: Dict[str, asyncio.Task] = {}   # NEU: Laufende Validierungen
        self._pending_actions: Dict[str, ActionEvent] = {}       # NEU: Wartende Actions (Dependencies)
        self._completed_action_ids: set = set()                  # NEU: Tracking für Dependencies
    
    def _calculate_action_timeout(self, action: ActionEvent) -> float:
        """
        Berechnet dynamischen Timeout basierend auf Aktionstyp.
        
        Args:
            action: Die Aktion
        
        Returns:
            Timeout in Sekunden
        """
        base_timeout = self.action_timeout
        
        if action.action_type == "type":
            # Texteingabe: 0.1s pro Zeichen + Basis
            text = action.params.get("text", "")
            text_timeout = len(text) * 0.05 + 5  # 50ms pro Zeichen + 5s Puffer
            return max(base_timeout, text_timeout)
        
        elif action.action_type == "wait":
            # Wait-Aktion: Die angegebene Dauer + Puffer
            duration = action.params.get("duration", 1.0)
            return duration + 5  # Wait-Dauer + 5s Puffer
        
        elif action.action_type == "click":
            # Klicks brauchen evtl länger wenn Vision verwendet wird
            return base_timeout
        
        elif action.action_type == "drag":
            # Drag-Operationen können länger dauern
            return base_timeout * 1.5
        
        elif action.action_type == "scroll":
            # Scrolling ist schnell
            return 15.0
        
        return base_timeout
    
    
    # ==================== Handler Registration ====================
    
    def set_task_handler(self, handler: Callable[[TaskEvent], Awaitable[List[ActionEvent]]]):
        """Setzt den Handler für Task-Planung (Reasoning Agent)."""
        self._task_handler = handler
    
    def set_action_handler(self, handler: Callable[[ActionEvent], Awaitable[Dict[str, Any]]]):
        """Setzt den Handler für Action-Ausführung (Interaction Agent)."""
        self._action_handler = handler
    
    def set_validation_handler(
        self, 
        handler: Callable[[ActionEvent, Dict[str, Any]], Awaitable[ValidationEvent]]
    ):
        """Setzt den Handler für Action-Validierung."""
        self._validation_handler = handler
    
    def set_state_change_handler(self, handler: Callable[[Dict[str, Any]], Awaitable[None]]):
        """Setzt den Handler für State-Changes."""
        self._state_change_handler = handler
    
    # ==================== Event Callbacks ====================
    
    def on_task_start(self, callback: Callable[[TaskEvent], None]):
        """Callback wenn Task startet."""
        self._on_task_start.append(callback)
    
    def on_task_complete(self, callback: Callable[[TaskEvent], None]):
        """Callback wenn Task abgeschlossen."""
        self._on_task_complete.append(callback)
    
    def on_action_start(self, callback: Callable[[ActionEvent], None]):
        """Callback wenn Aktion startet."""
        self._on_action_start.append(callback)
    
    def on_action_complete(self, callback: Callable[[ActionEvent, ValidationEvent], None]):
        """Callback wenn Aktion abgeschlossen und validiert."""
        self._on_action_complete.append(callback)
    
    def on_error(self, callback: Callable[[str, Exception], None]):
        """Callback bei Fehlern."""
        self._on_error.append(callback)
    
    # ==================== Task Management ====================
    
    async def add_task(self, goal: str, context: Optional[Dict[str, Any]] = None) -> TaskEvent:
        """
        Fügt einen neuen Task zur Queue hinzu.
        
        Args:
            goal: Beschreibung des Ziels
            context: Optionaler Kontext
        
        Returns:
            TaskEvent
        """
        self._task_counter += 1
        task = TaskEvent(
            id=f"task_{self._task_counter}_{int(time.time())}",
            goal=goal,
            context=context or {}
        )
        
        await self.task_queue.put(task)
        logger.info(f"Task hinzugefügt: {task.id} - {goal}")
        
        return task
    
    def get_task(self, task_id: str) -> Optional[TaskEvent]:
        """Gibt Task nach ID zurück."""
        return self.active_tasks.get(task_id)
    
    def get_all_tasks(self) -> List[TaskEvent]:
        """Gibt alle aktiven Tasks zurück."""
        return list(self.active_tasks.values())
    
    def get_task_actions(self, task_id: str) -> List[ActionEvent]:
        """
        Gibt alle Aktionen für einen Task zurück.
        
        Args:
            task_id: Die Task-ID
        
        Returns:
            Liste der Aktionen oder leere Liste
        """
        task = self.active_tasks.get(task_id)
        if task:
            return task.actions
        
        # Auch in abgeschlossenen Tasks suchen
        for completed_task in self.completed_tasks:
            if completed_task.id == task_id:
                return completed_task.actions
        
        return []
    
    async def cancel_task(self, task_id: str) -> bool:
        """Bricht einen Task ab."""
        task = self.active_tasks.get(task_id)
        if task:
            task.status = TaskStatus.CANCELLED
            task.completed_at = time.time()
            logger.info(f"Task abgebrochen: {task_id}")
            return True
        return False
    
    # ==================== Processing Loops ====================
    
    async def start(self):
        """Startet die Event-Verarbeitung."""
        if self._running:
            logger.warning("EventQueue already running")
            return

        self._running = True
        logger.info("EventQueue gestartet (parallel mode: max_actions=%d, max_validations=%d)",
                    self.max_concurrent_actions, self.max_concurrent_validations)

        # Starte Processor-Tasks
        self._task_processor = asyncio.create_task(self._process_tasks())
        self._action_processor = asyncio.create_task(self._process_actions_parallel())  # NEU: Parallel
        self._result_processor = asyncio.create_task(self._process_results())
        self._validation_processor = asyncio.create_task(self._process_validations_parallel())  # NEU
    
    async def stop(self):
        """Stoppt die Event-Verarbeitung."""
        self._running = False

        # Cancel all executing actions
        for action_id, task in list(self._executing_actions.items()):
            task.cancel()
        for action_id, task in list(self._validating_actions.items()):
            task.cancel()

        # Stoppe Processor-Tasks
        for processor in [self._task_processor, self._action_processor,
                          self._result_processor, self._validation_processor]:
            if processor:
                processor.cancel()
                try:
                    await processor
                except asyncio.CancelledError:
                    pass

        # Clear tracking
        self._executing_actions.clear()
        self._validating_actions.clear()
        self._pending_actions.clear()
        self._completed_action_ids.clear()

        logger.info("EventQueue gestoppt")
    
    async def _process_tasks(self):
        """Verarbeitet Tasks aus der Queue."""
        while self._running:
            try:
                # Warte auf nächsten Task
                task = await asyncio.wait_for(
                    self.task_queue.get(),
                    timeout=1.0
                )
                
                # Prüfe Kapazität
                active_count = sum(
                    1 for t in self.active_tasks.values() 
                    if t.status in [TaskStatus.PLANNING, TaskStatus.EXECUTING, TaskStatus.VALIDATING]
                )
                
                if active_count >= self.max_concurrent_tasks:
                    # Zurück in Queue
                    await self.task_queue.put(task)
                    await asyncio.sleep(0.5)
                    continue
                
                # Starte Task-Verarbeitung
                await self._handle_task(task)
                
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Task processing error: {e}")
                self._emit_error("task_processing", e)
    
    async def _handle_task(self, task: TaskEvent):
        """Verarbeitet einen einzelnen Task."""
        task.status = TaskStatus.PLANNING
        task.started_at = time.time()
        self.active_tasks[task.id] = task
        
        # Emit start callback
        for cb in self._on_task_start:
            try:
                cb(task)
            except Exception as e:
                logger.error(f"Task start callback error: {e}")
        
        logger.info(f"Task wird geplant: {task.id}")
        
        try:
            # Plane Aktionen
            if self._task_handler:
                actions = await self._task_handler(task)
                task.actions = actions
                
                # Füge Aktionen zur Queue hinzu
                for action in actions:
                    await self.action_queue.put(action)
                
                task.status = TaskStatus.EXECUTING
                logger.info(f"Task geplant: {task.id} mit {len(actions)} Aktionen")
            else:
                logger.error("Kein Task-Handler registriert")
                task.status = TaskStatus.FAILED
                task.error = "No task handler registered"
        
        except Exception as e:
            logger.error(f"Task planning failed: {e}")
            task.status = TaskStatus.FAILED
            task.error = str(e)
            self._emit_error("task_planning", e)
    
    async def _process_actions(self):
        """Verarbeitet Aktionen aus der Queue."""
        while self._running:
            try:
                # Warte auf nächste Aktion
                action = await asyncio.wait_for(
                    self.action_queue.get(),
                    timeout=1.0
                )
                
                # Prüfe ob Task noch aktiv
                task = self.active_tasks.get(action.task_id)
                if not task or task.status == TaskStatus.CANCELLED:
                    action.status = ActionStatus.SKIPPED
                    continue
                
                # Führe Aktion aus
                await self._handle_action(action, task)
                
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Action processing error: {e}")
                self._emit_error("action_processing", e)
    
    async def _handle_action(self, action: ActionEvent, task: TaskEvent):
        """Führt eine einzelne Aktion aus."""
        action.status = ActionStatus.EXECUTING
        action.executed_at = time.time()
        
        # Emit start callback
        for cb in self._on_action_start:
            try:
                cb(action)
            except Exception as e:
                logger.error(f"Action start callback error: {e}")
        
        logger.info(f"Aktion wird ausgeführt: {action.action_type} - {action.description}")
        
        # Berechne dynamischen Timeout
        timeout = self._calculate_action_timeout(action)
        logger.debug(f"Action timeout: {timeout}s für {action.action_type}")
        
        try:
            # Führe Aktion aus
            if self._action_handler:
                result = await asyncio.wait_for(
                    self._action_handler(action),
                    timeout=timeout  # Dynamischer Timeout
                )
                action.result = result
                
                # Validiere Ergebnis
                if self._validation_handler:
                    validation = await asyncio.wait_for(
                        self._validation_handler(action, result),
                        timeout=self.validation_timeout
                    )
                    action.validation = {
                        "success": validation.success,
                        "confidence": validation.confidence,
                        "description": validation.description
                    }
                    
                    # Füge Validierung zur Result-Queue hinzu
                    await self.result_queue.put(validation)
                else:
                    # Ohne Validierung als erfolgreich markieren
                    action.status = ActionStatus.COMPLETED
                    action.completed_at = time.time()
            else:
                logger.error("Kein Action-Handler registriert")
                action.status = ActionStatus.FAILED
                action.error = "No action handler registered"
        
        except asyncio.TimeoutError:
            logger.error(f"Aktion Timeout nach {timeout}s: {action.id}")
            action.status = ActionStatus.FAILED
            action.error = f"Action timeout after {timeout}s"
        
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            action.status = ActionStatus.FAILED
            action.error = str(e)
            self._emit_error("action_execution", e)

    # ==================== Parallel Processing ====================

    def _dependencies_resolved(self, action: ActionEvent) -> bool:
        """Prüft ob alle Dependencies einer Action erfüllt sind."""
        if not action.depends_on:
            logger.info(f"🔗 Action {action.id} hat KEINE Dependencies - startet sofort")
            return True
        resolved = all(dep_id in self._completed_action_ids for dep_id in action.depends_on)
        logger.info(f"🔗 Action {action.id}: depends_on={action.depends_on}, completed={list(self._completed_action_ids)}, resolved={resolved}")
        return resolved

    async def _process_actions_parallel(self):
        """Verarbeitet Actions parallel mit Dependency-Tracking."""
        while self._running:
            try:
                # Starte neue Actions wenn Kapazität vorhanden
                while len(self._executing_actions) < self.max_concurrent_actions:
                    # Erst pending Actions mit erfüllten Dependencies prüfen
                    started_pending = False
                    for action_id in list(self._pending_actions.keys()):
                        action = self._pending_actions[action_id]
                        if self._dependencies_resolved(action):
                            del self._pending_actions[action_id]
                            task = asyncio.create_task(
                                self._execute_action_isolated(action)
                            )
                            self._executing_actions[action.id] = task
                            started_pending = True
                            break

                    if started_pending:
                        continue

                    # Neue Action aus Queue holen
                    try:
                        action = self.action_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    # Prüfe ob Task noch aktiv
                    task = self.active_tasks.get(action.task_id)
                    if not task or task.status == TaskStatus.CANCELLED:
                        action.status = ActionStatus.SKIPPED
                        continue

                    # Check Dependencies
                    if not self._dependencies_resolved(action):
                        self._pending_actions[action.id] = action
                        action.status = ActionStatus.QUEUED
                        logger.info(f"⏳ Action {action.id} wartet auf Dependencies: {action.depends_on}")
                        continue

                    # Starte Action parallel
                    action.status = ActionStatus.QUEUED
                    exec_task = asyncio.create_task(
                        self._execute_action_isolated(action)
                    )
                    self._executing_actions[action.id] = exec_task

                # Cleanup abgeschlossene Actions
                for action_id in list(self._executing_actions.keys()):
                    exec_task = self._executing_actions[action_id]
                    if exec_task.done():
                        try:
                            exec_task.result()  # Raise any exceptions
                        except Exception as e:
                            logger.error(f"Action {action_id} failed: {e}")
                        del self._executing_actions[action_id]

                await asyncio.sleep(0.05)  # 50ms poll interval

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Parallel action processing error: {e}")
                self._emit_error("parallel_action_processing", e)
                await asyncio.sleep(0.1)

    async def _execute_action_isolated(self, action: ActionEvent):
        """Führt eine Action isoliert aus (für parallele Ausführung)."""
        action.status = ActionStatus.EXECUTING
        action.executed_at = time.time()

        # Emit start callback
        for cb in self._on_action_start:
            try:
                cb(action)
            except Exception as e:
                logger.error(f"Action start callback error: {e}")

        logger.info(f"⚡ Parallel-Aktion: {action.action_type} - {action.description}")

        timeout = self._calculate_action_timeout(action)

        try:
            if self._action_handler:
                result = await asyncio.wait_for(
                    self._action_handler(action),
                    timeout=timeout
                )
                action.result = result
                action.status = ActionStatus.EXECUTED  # Ausgeführt, Validierung pending

                # Action in Validation Queue für deferred validation
                await self.validation_queue.put(action)

                # Mark as completed for dependency tracking
                self._completed_action_ids.add(action.id)
                logger.info(f"✅ Action {action.id} completed - dependencies können fortfahren")

            else:
                logger.error("Kein Action-Handler registriert")
                action.status = ActionStatus.FAILED
                action.error = "No action handler registered"

        except asyncio.TimeoutError:
            logger.error(f"Action Timeout nach {timeout}s: {action.id}")
            action.status = ActionStatus.FAILED
            action.error = f"Action timeout after {timeout}s"
            self._completed_action_ids.add(action.id)  # Auch failed actions zählen für deps

        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            action.status = ActionStatus.FAILED
            action.error = str(e)
            self._completed_action_ids.add(action.id)
            self._emit_error("action_execution", e)

    async def _process_validations_parallel(self):
        """Validiert Actions parallel (non-blocking, deferred)."""
        while self._running:
            try:
                # Starte neue Validierungen wenn Kapazität vorhanden
                while len(self._validating_actions) < self.max_concurrent_validations:
                    try:
                        action = self.validation_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    action.status = ActionStatus.VALIDATING
                    val_task = asyncio.create_task(
                        self._validate_action_isolated(action)
                    )
                    self._validating_actions[action.id] = val_task

                # Cleanup abgeschlossene Validierungen und emit results
                for action_id in list(self._validating_actions.keys()):
                    val_task = self._validating_actions[action_id]
                    if val_task.done():
                        try:
                            validation = val_task.result()
                            if validation:
                                await self.result_queue.put(validation)
                        except Exception as e:
                            logger.error(f"Validation {action_id} failed: {e}")
                        del self._validating_actions[action_id]

                await asyncio.sleep(0.05)  # 50ms poll interval

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Parallel validation processing error: {e}")
                self._emit_error("parallel_validation_processing", e)
                await asyncio.sleep(0.1)

    async def _validate_action_isolated(self, action: ActionEvent) -> Optional[ValidationEvent]:
        """Validiert eine Action isoliert (für parallele Validierung)."""
        try:
            if self._validation_handler and action.result is not None:
                validation = await asyncio.wait_for(
                    self._validation_handler(action, action.result),
                    timeout=self.validation_timeout
                )
                action.validation = {
                    "success": validation.success,
                    "confidence": validation.confidence,
                    "description": validation.description
                }
                return validation
            else:
                # Ohne Validierung als erfolgreich markieren
                action.status = ActionStatus.COMPLETED
                action.completed_at = time.time()
                return ValidationEvent(
                    action_id=action.id,
                    task_id=action.task_id,
                    success=True,
                    confidence=0.8,
                    description="No validation handler - assumed success"
                )

        except asyncio.TimeoutError:
            logger.warning(f"Validation timeout für {action.id}")
            action.status = ActionStatus.COMPLETED  # Trotzdem als completed markieren
            action.completed_at = time.time()
            return ValidationEvent(
                action_id=action.id,
                task_id=action.task_id,
                success=True,
                confidence=0.5,
                description="Validation timeout - assumed success"
            )

        except Exception as e:
            logger.error(f"Validation failed for {action.id}: {e}")
            return ValidationEvent(
                action_id=action.id,
                task_id=action.task_id,
                success=False,
                confidence=0.0,
                description=f"Validation error: {str(e)}"
            )

    async def _process_results(self):
        """Verarbeitet Validierungsergebnisse."""
        while self._running:
            try:
                # Warte auf nächstes Ergebnis
                validation = await asyncio.wait_for(
                    self.result_queue.get(),
                    timeout=1.0
                )
                
                await self._handle_validation(validation)
                
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Result processing error: {e}")
                self._emit_error("result_processing", e)
    
    async def _handle_validation(self, validation: ValidationEvent):
        """Verarbeitet Validierungsergebnis."""
        task = self.active_tasks.get(validation.task_id)
        if not task:
            return
        
        # Finde zugehörige Aktion
        action = None
        for a in task.actions:
            if a.id == validation.action_id:
                action = a
                break
        
        if not action:
            return
        
        if validation.success:
            action.status = ActionStatus.COMPLETED
            action.completed_at = time.time()
            logger.info(f"Aktion validiert: {action.id} (Confidence: {validation.confidence:.2f})")
            
            # Emit complete callback
            for cb in self._on_action_complete:
                try:
                    cb(action, validation)
                except Exception as e:
                    logger.error(f"Action complete callback error: {e}")
            
            # Prüfe ob alle Aktionen abgeschlossen
            all_done = all(
                a.status in [ActionStatus.COMPLETED, ActionStatus.SKIPPED]
                for a in task.actions
            )
            
            if all_done:
                task.status = TaskStatus.COMPLETED
                task.completed_at = time.time()
                self.completed_tasks.append(task)
                
                # Emit task complete callback
                for cb in self._on_task_complete:
                    try:
                        cb(task)
                    except Exception as e:
                        logger.error(f"Task complete callback error: {e}")
                
                logger.info(f"Task abgeschlossen: {task.id}")
        
        else:
            # Validierung fehlgeschlagen
            action.status = ActionStatus.FAILED
            action.error = validation.description
            
            # Prüfe Retry
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                logger.warning(f"Aktion fehlgeschlagen, Retry {task.retry_count}/{task.max_retries}")
                
                # Re-queue task for replanning
                task.status = TaskStatus.PENDING
                await self.task_queue.put(task)
            else:
                task.status = TaskStatus.FAILED
                task.error = f"Max retries exceeded: {validation.description}"
                logger.error(f"Task fehlgeschlagen: {task.id}")
    
    def _emit_error(self, context: str, error: Exception):
        """Emittiert Fehler an Callbacks."""
        for cb in self._on_error:
            try:
                cb(context, error)
            except:
                pass
    
    # ==================== Status ====================
    
    def get_status(self) -> Dict[str, Any]:
        """Gibt Status des EventQueue Systems zurück."""
        return {
            "running": self._running,
            "task_queue_size": self.task_queue.qsize(),
            "action_queue_size": self.action_queue.qsize(),
            "result_queue_size": self.result_queue.qsize(),
            "active_tasks": len(self.active_tasks),
            "completed_tasks": len(self.completed_tasks),
            "total_tasks_processed": self._task_counter,
            "total_actions_processed": self._action_counter
        }
    
    async def wait_for_task(self, task_id: str, timeout: float = 60.0) -> TaskEvent:
        """Wartet bis ein Task abgeschlossen ist."""
        start = time.time()
        while time.time() - start < timeout:
            task = self.active_tasks.get(task_id)
            if task:
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    return task
            await asyncio.sleep(0.1)
        
        raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")


# Singleton
_queue_instance: Optional[EventQueue] = None


def get_event_queue() -> EventQueue:
    """Gibt Singleton-Instanz des EventQueue zurück."""
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = EventQueue()
    return _queue_instance


def reset_event_queue():
    """Setzt EventQueue zurück."""
    global _queue_instance
    if _queue_instance:
        asyncio.create_task(_queue_instance.stop())
    _queue_instance = None