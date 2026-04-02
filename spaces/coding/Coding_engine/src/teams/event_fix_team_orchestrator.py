"""
EventFixTeam Orchestrator - Delegiert Tasks an spezialisierte Agents

Diese Version des EventFixTeams delegiert Tasks an spezialisierte Agents,
die MCP Tool Calls verwenden, um mit den MCP Servern zu kommunizieren.
"""

import asyncio
import json
import os
import sys
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import structlog

# Pfad zu mcp_plugins/servers hinzufügen
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'mcp_plugins', 'servers'))
from mcp_server_registry import MCPServerRegistry, MCPServerType, get_registry

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
    
    # MCP Server Konfiguration
    mcp_registry: Optional[MCPServerRegistry] = None
    
    # Tool Aktivierung
    enable_docker_tools: bool = True
    enable_redis_tools: bool = True
    enable_postgres_tools: bool = True
    enable_playwright_tools: bool = True
    enable_filesystem_tools: bool = True  # Für Code-Write
    
    # Execution
    max_concurrent_tasks: int = 5
    timeout_seconds: int = 300


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


class EventFixTeamOrchestrator:
    """
    EventFixTeam Orchestrator - Delegiert Tasks an spezialisierte Agents.
    
    Architektur:
    1. EventFixTeam empfängt Events und erstellt Tasks
    2. Tasks werden an spezialisierte Agents delegiert
    3. Agents verwenden MCP Tool Calls
    4. MCP Server werden über Tool Calls angesprochen
    
    Vorteile:
    - Trennung von Verantwortlichkeiten
    - Agents können unabhängig entwickelt werden
    - MCP Server können wiederverwendet werden
    """
    
    def __init__(
        self,
        config: EventFixConfig,
    ):
        """
        Initialisiert das EventFixTeam Orchestrator.
        
        Args:
            config: EventFix-Konfiguration
        """
        self.config = config
        self.working_dir = os.path.abspath(config.working_dir)
        self.output_dir = os.path.abspath(config.output_dir)
        
        # MCP Server Registry initialisieren
        if config.mcp_registry is None:
            self.mcp_registry = get_registry()
        else:
            self.mcp_registry = config.mcp_registry
        
        # Task Queue
        self._task_queue: List[FixTask] = []
        self._completed_tasks: List[FixTask] = []
        
        # Agents (werden lazy geladen)
        self._debug_agent: Optional[Any] = None
        self._migration_agent: Optional[Any] = None
        self._test_agent: Optional[Any] = None
        self._log_agent: Optional[Any] = None
        
        # Status
        self._running = False
        self._session_id = f"eventfix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.logger = logger.bind(
            component="event_fix_team_orchestrator",
            session_id=self._session_id,
        )
        
        # Output directory erstellen
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Registry Summary loggen
        self.mcp_registry.print_summary()
    
    async def start(self) -> None:
        """Startet das EventFixTeam Orchestrator."""
        self._running = True
        self.logger.info("event_fix_team_orchestrator_starting", session_id=self._session_id)
        
        # Agents initialisieren
        await self._initialize_agents()
        
        self.logger.info("event_fix_team_orchestrator_started", session_id=self._session_id)
    
    async def stop(self) -> None:
        """Stoppt das EventFixTeam Orchestrator."""
        self._running = False
        self.logger.info("event_fix_team_orchestrator_stopping", session_id=self._session_id)
        
        # Agents stoppen
        for agent in [self._debug_agent, self._migration_agent, 
                      self._test_agent, self._log_agent]:
            if agent and hasattr(agent, 'stop'):
                try:
                    await agent.stop()
                except Exception as e:
                    self.logger.warning("agent_stop_failed", error=str(e))
    
    async def _initialize_agents(self) -> None:
        """Initialisiert die spezialisierten Agents."""
        try:
            # DebugAgent initialisieren
            if self.config.enable_docker_tools or self.config.enable_redis_tools or self.config.enable_postgres_tools:
                self._debug_agent = await self._create_debug_agent()
                self.logger.info("debug_agent_initialized")
            
            # MigrationAgent initialisieren
            if self.config.enable_postgres_tools:
                self._migration_agent = await self._create_migration_agent()
                self.logger.info("migration_agent_initialized")
            
            # TestAgent initialisieren
            if self.config.enable_playwright_tools:
                self._test_agent = await self._create_test_agent()
                self.logger.info("test_agent_initialized")
            
            # LogAgent initialisieren
            if self.config.enable_docker_tools or self.config.enable_redis_tools:
                self._log_agent = await self._create_log_agent()
                self.logger.info("log_agent_initialized")
                
        except Exception as e:
            self.logger.error("agent_initialization_failed", error=str(e))
    
    async def _create_debug_agent(self) -> Any:
        """
        Erstellt den DebugAgent.
        
        Der DebugAgent verwendet MCP Tool Calls, um mit Docker, Redis und
        PostgreSQL MCP Servern zu kommunizieren.
        """
        try:
            # Hier würde der DebugAgent initialisiert werden
            # Der DebugAgent würde MCP Tool Calls verwenden
            
            # Placeholder für DebugAgent
            class DebugAgent:
                def __init__(self, mcp_registry: MCPServerRegistry):
                    self.mcp_registry = mcp_registry
                    self.logger = logger.bind(component="debug_agent")
                
                async def handle_task(self, task: FixTask) -> Dict[str, Any]:
                    """Verarbeitet eine Fix-Task."""
                    self.logger.info(
                        "debug_agent_handling_task",
                        task_id=task.task_id,
                        type=task.type.value,
                    )
                    
                    # Hier würde der DebugAgent MCP Tool Calls verwenden
                    # z.B. Docker Logs abrufen, Redis Keys analysieren, etc.
                    
                    result = {
                        "success": True,
                        "task_id": task.task_id,
                        "message": "Debug analysis completed",
                    }
                    
                    return result
                
                async def stop(self):
                    """Stoppt den DebugAgent."""
                    self.logger.info("debug_agent_stopped")
            
            return DebugAgent(self.mcp_registry)
            
        except Exception as e:
            self.logger.error("debug_agent_creation_failed", error=str(e))
            return None
    
    async def _create_migration_agent(self) -> Any:
        """
        Erstellt den MigrationAgent.
        
        Der MigrationAgent verwendet MCP Tool Calls, um mit dem PostgreSQL
        MCP Server zu kommunizieren.
        """
        try:
            # Hier würde der MigrationAgent initialisiert werden
            # Der MigrationAgent würde MCP Tool Calls verwenden
            
            # Placeholder für MigrationAgent
            class MigrationAgent:
                def __init__(self, mcp_registry: MCPServerRegistry):
                    self.mcp_registry = mcp_registry
                    self.logger = logger.bind(component="migration_agent")
                
                async def handle_task(self, task: FixTask) -> Dict[str, Any]:
                    """Verarbeitet eine Migrations-Task."""
                    self.logger.info(
                        "migration_agent_handling_task",
                        task_id=task.task_id,
                        type=task.type.value,
                    )
                    
                    # Hier würde der MigrationAgent MCP Tool Calls verwenden
                    # z.B. PostgreSQL Schema abrufen, Migration planen, etc.
                    
                    result = {
                        "success": True,
                        "task_id": task.task_id,
                        "message": "Migration planning completed",
                    }
                    
                    return result
                
                async def stop(self):
                    """Stoppt den MigrationAgent."""
                    self.logger.info("migration_agent_stopped")
            
            return MigrationAgent(self.mcp_registry)
            
        except Exception as e:
            self.logger.error("migration_agent_creation_failed", error=str(e))
            return None
    
    async def _create_test_agent(self) -> Any:
        """
        Erstellt den TestAgent.
        
        Der TestAgent verwendet MCP Tool Calls, um mit dem Playwright
        MCP Server zu kommunizieren.
        """
        try:
            # Hier würde der TestAgent initialisiert werden
            # Der TestAgent würde MCP Tool Calls verwenden
            
            # Placeholder für TestAgent
            class TestAgent:
                def __init__(self, mcp_registry: MCPServerRegistry):
                    self.mcp_registry = mcp_registry
                    self.logger = logger.bind(component="test_agent")
                
                async def handle_task(self, task: FixTask) -> Dict[str, Any]:
                    """Verarbeitet eine Test-Fix-Task."""
                    self.logger.info(
                        "test_agent_handling_task",
                        task_id=task.task_id,
                        type=task.type.value,
                    )
                    
                    # Hier würde der TestAgent MCP Tool Calls verwenden
                    # z.B. Playwright E2E-Test ausführen, Screenshot aufnehmen, etc.
                    
                    result = {
                        "success": True,
                        "task_id": task.task_id,
                        "message": "Test execution completed",
                    }
                    
                    return result
                
                async def stop(self):
                    """Stoppt den TestAgent."""
                    self.logger.info("test_agent_stopped")
            
            return TestAgent(self.mcp_registry)
            
        except Exception as e:
            self.logger.error("test_agent_creation_failed", error=str(e))
            return None
    
    async def _create_log_agent(self) -> Any:
        """
        Erstellt den LogAgent.
        
        Der LogAgent verwendet MCP Tool Calls, um mit Docker, Redis und
        PostgreSQL MCP Servern zu kommunizieren.
        """
        try:
            # Hier würde der LogAgent initialisiert werden
            # Der LogAgent würde MCP Tool Calls verwenden
            
            # Placeholder für LogAgent
            class LogAgent:
                def __init__(self, mcp_registry: MCPServerRegistry):
                    self.mcp_registry = mcp_registry
                    self.logger = logger.bind(component="log_agent")
                
                async def handle_task(self, task: FixTask) -> Dict[str, Any]:
                    """Verarbeitet eine Log-Analyse-Task."""
                    self.logger.info(
                        "log_agent_handling_task",
                        task_id=task.task_id,
                        type=task.type.value,
                    )
                    
                    # Hier würde der LogAgent MCP Tool Calls verwenden
                    # z.B. Docker Logs abrufen, Redis Logs analysieren, etc.
                    
                    result = {
                        "success": True,
                        "task_id": task.task_id,
                        "message": "Log analysis completed",
                    }
                    
                    return result
                
                async def stop(self):
                    """Stoppt den LogAgent."""
                    self.logger.info("log_agent_stopped")
            
            return LogAgent(self.mcp_registry)
            
        except Exception as e:
            self.logger.error("log_agent_creation_failed", error=str(e))
            return None
    
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
        import uuid
        
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
        import time
        
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
                # Task an passenden Agent delegieren
                await self._delegate_task(task)
                
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
        
        self.logger.info(
            "tasks_processed",
            total=len(tasks_to_process),
            completed=result.tasks_completed,
            errors=len(result.errors),
        )
        
        return result
    
    async def _delegate_task(self, task: FixTask) -> None:
        """
        Delegiert eine Task an den passenden Agent.
        
        Args:
            task: Zu delegierende Task
        """
        self.logger.info(
            "delegating_task",
            task_id=task.task_id,
            type=task.type.value,
        )
        
        # Task-Status aktualisieren
        task.status = "processing"
        await self._save_task(task)
        
        # Task-Typ bestimmen und an passenden Agent delegieren
        if task.type == FixTaskType.FIX_CODE:
            if self._debug_agent:
                await self._debug_agent.handle_task(task)
        elif task.type == FixTaskType.MIGRATION:
            if self._migration_agent:
                await self._migration_agent.handle_task(task)
        elif task.type == FixTaskType.TEST_FIX:
            if self._test_agent:
                await self._test_agent.handle_task(task)
        elif task.type == FixTaskType.LOG_ANALYSIS:
            if self._log_agent:
                await self._log_agent.handle_task(task)
        
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
async def create_event_fix_team_orchestrator(
    working_dir: str,
    output_dir: str = "./event_fix_output",
    mcp_registry: Optional[MCPServerRegistry] = None,
    enable_docker: bool = True,
    enable_redis: bool = True,
    enable_postgres: bool = True,
    enable_playwright: bool = True,
    enable_filesystem: bool = True,
) -> EventFixTeamOrchestrator:
    """
    Convenience function zum Erstellen eines EventFixTeam Orchestrators.
    
    Args:
        working_dir: Arbeitsverzeichnis
        output_dir: Output-Verzeichnis für Tasks und Results
        mcp_registry: Optional MCP Server Registry
        enable_docker: Docker-Tools aktivieren
        enable_redis: Redis-Tools aktivieren
        enable_postgres: PostgreSQL-Tools aktivieren
        enable_playwright: Playwright-Tools aktivieren
        enable_filesystem: Filesystem-Tools aktivieren (für Code-Write)
        
    Returns:
        EventFixTeamOrchestrator Instanz
    """
    config = EventFixConfig(
        working_dir=working_dir,
        output_dir=output_dir,
        mcp_registry=mcp_registry,
        enable_docker_tools=enable_docker,
        enable_redis_tools=enable_redis,
        enable_postgres_tools=enable_postgres,
        enable_playwright_tools=enable_playwright,
        enable_filesystem_tools=enable_filesystem,
    )
    
    team = EventFixTeamOrchestrator(config=config)
    
    return team


if __name__ == "__main__":
    # Test: EventFixTeam Orchestrator erstellen
    import asyncio
    
    async def test():
        team = await create_event_fix_team_orchestrator(
            working_dir=".",
            output_dir="./event_fix_output",
        )
        
        await team.start()
        
        # Test-Task erstellen
        task = await team.create_fix_task(
            task_type=FixTaskType.FIX_CODE,
            priority=FixPriority.HIGH,
            description="Fix division by zero error",
            file_path="src/app.py",
            suggested_fix="Add zero check before division",
        )
        
        # Tasks verarbeiten
        result = await team.process_tasks(max_tasks=1)
        
        print(f"Result: {result.to_dict()}")
        print(f"Status: {team.get_status()}")
        
        await team.stop()
    
    asyncio.run(test())
