"""
EventFixTeam - Spezialisiertes Team für Event-Fixes.

Architektur:
1. DebugAgent - Debuggt Fehler mit Docker, Redis, PostgreSQL Tools
2. MigrationAgent - Führt Schema-Migrationen durch
3. TestAgent - Führt E2E-Tests mit Playwright aus
4. LogAgent - Analysiert Logs und Performance

Alle Agents schreiben KEINEN Code direkt, sondern delegieren Tasks an File-Write Tools.
"""

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import structlog

# Shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from mind.event_bus import EventBus, Event, EventType
from mind.shared_state import SharedState
from agents.autonomous_base import AutonomousAgent, AgentStatus

logger = structlog.get_logger(__name__)


class FixTaskType(str, Enum):
    """Typen von Fix-Tasks."""
    FIX_CODE = "fix_code"
    MIGRATION = "migration"
    TEST_FIX = "test_fix"
    LOG_ANALYSIS = "log_analysis"


class FixPriority(str, Enum):
    """Prioritäten für Fix-Tasks."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class FixTask:
    """Eine Fix-Task (kein Code, nur Metadaten)."""
    task_id: str
    type: FixTaskType
    priority: FixPriority
    file_path: Optional[str] = None
    description: str = ""
    suggested_fix: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "type": self.type.value,
            "priority": self.priority.value,
            "file_path": self.file_path,
            "description": self.description,
            "suggested_fix": self.suggested_fix,
            "metadata": self.metadata,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass
class EventFixConfig:
    """Konfiguration für EventFixTeam."""
    # Paths
    working_dir: str
    output_dir: str = "./event_fix_output"
    
    # Tool Konfiguration
    enable_docker_tools: bool = True
    enable_redis_tools: bool = True
    enable_postgres_tools: bool = True
    enable_playwright_tools: bool = True
    
    # Execution
    max_concurrent_tasks: int = 5
    timeout_seconds: int = 300
    
    # Callbacks
    on_progress: Optional[Callable[[str, dict], None]] = None
    on_task_created: Optional[Callable[[FixTask], None]] = None


@dataclass
class EventFixResult:
    """Ergebnis der Event-Fix-Operation."""
    success: bool
    tasks_created: int = 0
    tasks_completed: int = 0
    errors: List[str] = field(default_factory=list)
    execution_time_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "tasks_created": self.tasks_created,
            "tasks_completed": self.tasks_completed,
            "errors": self.errors,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata,
        }


class EventFixTeam:
    """
    EventFixTeam - Orchestriert spezialisierte Agents für Event-Fixes.
    
    Workflow:
    1. Empfängt Events von EventBus
    2. Verteilt an passende spezialisierte Agents
    3. Agents analysieren und erstellen Fix-Tasks
    4. Tasks werden an File-Write Tools delegiert
    5. Fortschritt wird gemeldet
    """
    
    def __init__(
        self,
        config: EventFixConfig,
        event_bus: EventBus,
        shared_state: SharedState,
    ):
        self.config = config
        self.event_bus = event_bus
        self.shared_state = shared_state
        self.working_dir = os.path.abspath(config.working_dir)
        self.output_dir = os.path.abspath(config.output_dir)
        
        # Task Queue
        self._task_queue: List[FixTask] = []
        self._completed_tasks: List[FixTask] = []
        
        # Agents (werden lazy geladen)
        self._debug_agent: Optional[AutonomousAgent] = None
        self._migration_agent: Optional[AutonomousAgent] = None
        self._test_agent: Optional[AutonomousAgent] = None
        self._log_agent: Optional[AutonomousAgent] = None
        
        # Status
        self._running = False
        self._session_id = str(uuid.uuid4())
        
        self.logger = logger.bind(component="event_fix_team", session_id=self._session_id)
        
        # Output directory erstellen
        os.makedirs(self.output_dir, exist_ok=True)
    
    async def start(self) -> None:
        """Startet das EventFixTeam."""
        self._running = True
        self.logger.info("event_fix_team_starting", session_id=self._session_id)
        
        # Agents initialisieren
        await self._initialize_agents()
        
        # Event-Bus Subscription
        await self._subscribe_to_events()
        
        self._report_progress("started", {
            "session_id": self._session_id,
            "working_dir": self.working_dir,
        })
    
    async def stop(self) -> None:
        """Stoppt das EventFixTeam."""
        self._running = False
        self.logger.info("event_fix_team_stopping", session_id=self._session_id)
        
        # Agents stoppen
        for agent in [self._debug_agent, self._migration_agent, 
                      self._test_agent, self._log_agent]:
            if agent and hasattr(agent, 'stop'):
                try:
                    await agent.stop()
                except Exception as e:
                    self.logger.warning("agent_stop_failed", agent=agent.name, error=str(e))
    
    async def _initialize_agents(self) -> None:
        """Initialisiert die spezialisierten Agents."""
        try:
            # DebugAgent
            if self.config.enable_docker_tools or self.config.enable_redis_tools or self.config.enable_postgres_tools:
                from .agents.debug_agent import DebugAgent
                self._debug_agent = DebugAgent(
                    name="DebugAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    enable_docker=self.config.enable_docker_tools,
                    enable_redis=self.config.enable_redis_tools,
                    enable_postgres=self.config.enable_postgres_tools,
                )
                await self._debug_agent.start()
                self.logger.info("debug_agent_initialized")
            
            # MigrationAgent
            if self.config.enable_postgres_tools:
                from .agents.migration_agent import MigrationAgent
                self._migration_agent = MigrationAgent(
                    name="MigrationAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                )
                await self._migration_agent.start()
                self.logger.info("migration_agent_initialized")
            
            # TestAgent
            if self.config.enable_playwright_tools:
                from .agents.test_agent import TestAgent
                self._test_agent = TestAgent(
                    name="TestAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                )
                await self._test_agent.start()
                self.logger.info("test_agent_initialized")
            
            # LogAgent
            if self.config.enable_docker_tools or self.config.enable_redis_tools:
                from .agents.log_agent import LogAgent
                self._log_agent = LogAgent(
                    name="LogAgent",
                    event_bus=self.event_bus,
                    shared_state=self.shared_state,
                    working_dir=self.working_dir,
                    enable_docker=self.config.enable_docker_tools,
                    enable_redis=self.config.enable_redis_tools,
                )
                await self._log_agent.start()
                self.logger.info("log_agent_initialized")
                
        except ImportError as e:
            self.logger.error("agent_import_failed", error=str(e))
    
    async def _subscribe_to_events(self) -> None:
        """Subscribed zu relevanten Events."""
        # Debug Events
        debug_events = [
            EventType.ERROR_DETECTED,
            EventType.CRASH_DETECTED,
            EventType.DEBUG_REQUEST,
        ]
        
        # Migration Events
        migration_events = [
            EventType.MIGRATION_NEEDED,
            EventType.SCHEMA_CHANGE,
            EventType.DATA_MIGRATION,
        ]
        
        # Test Events
        test_events = [
            EventType.TEST_REQUEST,
            EventType.E2E_TEST_NEEDED,
            EventType.REGRESSION_TEST,
        ]
        
        # Log Events
        log_events = [
            EventType.LOG_ANALYSIS_REQUEST,
            EventType.PERFORMANCE_ISSUE,
            EventType.ANOMALY_DETECTED,
        ]
        
        # Subscribe zu allen Events
        all_events = debug_events + migration_events + test_events + log_events
        for event_type in all_events:
            await self.event_bus.subscribe(event_type, self._handle_event)
        
        self.logger.info(
            "event_subscriptions_created",
            debug_events=len(debug_events),
            migration_events=len(migration_events),
            test_events=len(test_events),
            log_events=len(log_events),
        )
    
    async def _handle_event(self, event: Event) -> None:
        """Verarbeitet ein eingehendes Event."""
        if not self._running:
            return
        
        self.logger.info(
            "event_received",
            event_type=event.type.value,
            source=event.source,
        )
        
        # Event an passenden Agent weiterleiten
        try:
            if event.type in [EventType.ERROR_DETECTED, EventType.CRASH_DETECTED, EventType.DEBUG_REQUEST]:
                if self._debug_agent:
                    await self._debug_agent.handle_event(event)
            
            elif event.type in [EventType.MIGRATION_NEEDED, EventType.SCHEMA_CHANGE, EventType.DATA_MIGRATION]:
                if self._migration_agent:
                    await self._migration_agent.handle_event(event)
            
            elif event.type in [EventType.TEST_REQUEST, EventType.E2E_TEST_NEEDED, EventType.REGRESSION_TEST]:
                if self._test_agent:
                    await self._test_agent.handle_event(event)
            
            elif event.type in [EventType.LOG_ANALYSIS_REQUEST, EventType.PERFORMANCE_ISSUE, EventType.ANOMALY_DETECTED]:
                if self._log_agent:
                    await self._log_agent.handle_event(event)
                    
        except Exception as e:
            self.logger.error(
                "event_handling_failed",
                event_type=event.type.value,
                error=str(e),
            )
    
    async def create_fix_task(
        self,
        task_type: FixTaskType,
        priority: FixPriority,
        description: str,
        file_path: Optional[str] = None,
        suggested_fix: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FixTask:
        """
        Erstellt eine Fix-Task und fügt sie zur Queue hinzu.
        
        Args:
            task_type: Typ der Task
            priority: Priorität
            description: Beschreibung des Problems
            file_path: Optionaler Dateipfad
            suggested_fix: Optionaler Fix-Vorschlag
            metadata: Zusätzliche Metadaten
            
        Returns:
            Erstellte FixTask
        """
        task = FixTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            type=task_type,
            priority=priority,
            file_path=file_path,
            description=description,
            suggested_fix=suggested_fix,
            metadata=metadata or {},
        )
        
        self._task_queue.append(task)
        
        # Callback
        if self.config.on_task_created:
            try:
                self.config.on_task_created(task)
            except Exception as e:
                self.logger.warning("task_created_callback_failed", error=str(e))
        
        # Task speichern
        await self._save_task(task)
        
        self.logger.info(
            "fix_task_created",
            task_id=task.task_id,
            type=task_type.value,
            priority=priority.value,
        )
        
        return task
    
    async def _save_task(self, task: FixTask) -> None:
        """Speichert eine Task als JSON."""
        try:
            task_file = os.path.join(
                self.output_dir,
                f"task_{task.task_id}.json"
            )
            with open(task_file, 'w', encoding='utf-8') as f:
                json.dump(task.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error("task_save_failed", task_id=task.task_id, error=str(e))
    
    async def process_tasks(self, max_tasks: Optional[int] = None) -> EventFixResult:
        """
        Verarbeitet Tasks aus der Queue.
        
        Args:
            max_tasks: Maximale Anzahl zu verarbeitender Tasks
            
        Returns:
            EventFixResult mit Statistiken
        """
        start_time = time.time()
        result = EventFixResult(success=True)
        
        tasks_to_process = self._task_queue[:max_tasks] if max_tasks else self._task_queue.copy()
        
        self.logger.info(
            "processing_tasks",
            total=len(self._task_queue),
            processing=len(tasks_to_process),
        )
        
        for task in tasks_to_process:
            try:
                # Task verarbeiten (delegiert an File-Write Tools)
                await self._process_single_task(task)
                
                result.tasks_completed += 1
                self._completed_tasks.append(task)
                
                # Aus Queue entfernen
                if task in self._task_queue:
                    self._task_queue.remove(task)
                    
            except Exception as e:
                error_msg = f"Task {task.task_id} failed: {str(e)}"
                result.errors.append(error_msg)
                self.logger.error("task_processing_failed", task_id=task.task_id, error=str(e))
        
        result.tasks_created = len(self._completed_tasks)
        result.execution_time_ms = int((time.time() - start_time) * 1000)
        result.success = len(result.errors) == 0
        
        # Report speichern
        await self._save_result(result)
        
        self._report_progress("tasks_processed", {
            "total": len(tasks_to_process),
            "completed": result.tasks_completed,
            "errors": len(result.errors),
        })
        
        return result
    
    async def _process_single_task(self, task: FixTask) -> None:
        """
        Verarbeitet eine einzelne Task.
        
        Hier würde die Delegation an File-Write Tools stattfinden.
        Für jetzt simulieren wir dies durch Speichern der Task.
        """
        self.logger.info(
            "processing_task",
            task_id=task.task_id,
            type=task.type.value,
            file_path=task.file_path,
        )
        
        # Task-Status aktualisieren
        task.status = "processing"
        await self._save_task(task)
        
        # Hier würde die eigentliche Delegation an File-Write Tools stattfinden
        # z.B. await file_write_tool.execute(task)
        
        # Task-Status aktualisieren
        task.status = "completed"
        await self._save_task(task)
    
    async def _save_result(self, result: EventFixResult) -> None:
        """Speichert das Ergebnis als JSON."""
        try:
            result_file = os.path.join(
                self.output_dir,
                f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error("result_save_failed", error=str(e))
    
    def _report_progress(self, phase: str, data: dict) -> None:
        """Reportet Fortschritt."""
        if self.config.on_progress:
            try:
                self.config.on_progress(phase, data)
            except Exception as e:
                self.logger.warning("progress_callback_failed", error=str(e))
        
        self.logger.info("progress_report", phase=phase, data=data)
    
    def get_status(self) -> dict:
        """Gibt aktuellen Status zurück."""
        return {
            "session_id": self._session_id,
            "running": self._running,
            "pending_tasks": len(self._task_queue),
            "completed_tasks": len(self._completed_tasks),
            "agents": {
                "debug_agent": self._debug_agent is not None,
                "migration_agent": self._migration_agent is not None,
                "test_agent": self._test_agent is not None,
                "log_agent": self._log_agent is not None,
            },
        }


# Convenience function
async def create_event_fix_team(
    working_dir: str,
    output_dir: str = "./event_fix_output",
    event_bus: Optional[EventBus] = None,
    shared_state: Optional[SharedState] = None,
    enable_docker: bool = True,
    enable_redis: bool = True,
    enable_postgres: bool = True,
    enable_playwright: bool = True,
) -> EventFixTeam:
    """
    Convenience function zum Erstellen eines EventFixTeam.
    
    Args:
        working_dir: Arbeitsverzeichnis
        output_dir: Output-Verzeichnis für Tasks und Results
        event_bus: Optionaler EventBus (wird erstellt wenn None)
        shared_state: Optionaler SharedState (wird erstellt wenn None)
        enable_docker: Docker-Tools aktivieren
        enable_redis: Redis-Tools aktivieren
        enable_postgres: PostgreSQL-Tools aktivieren
        enable_playwright: Playwright-Tools aktivieren
        
    Returns:
        EventFixTeam Instanz
    """
    # EventBus und SharedState erstellen falls nicht vorhanden
    if event_bus is None:
        from mind.event_bus import create_event_bus
        event_bus = await create_event_bus()
    
    if shared_state is None:
        from mind.shared_state import SharedState
        shared_state = SharedState()
    
    config = EventFixConfig(
        working_dir=working_dir,
        output_dir=output_dir,
        enable_docker_tools=enable_docker,
        enable_redis_tools=enable_redis,
        enable_postgres_tools=enable_postgres,
        enable_playwright_tools=enable_playwright,
    )
    
    team = EventFixTeam(
        config=config,
        event_bus=event_bus,
        shared_state=shared_state,
    )
    
    return team
