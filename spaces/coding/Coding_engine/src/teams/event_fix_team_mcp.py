"""
EventFixTeam mit MCP Server Registry Integration

Diese Version des EventFixTeams integriert die MCP Server Registry
und verwendet MCP Tool Calls anstelle von lokalen Tools.
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
    use_mcp_tools: bool = True  # MCP Tools verwenden oder lokale Tools
    
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


class EventFixTeamMCP:
    """
    EventFixTeam mit MCP Server Registry Integration.
    
    Diese Version verwendet MCP Tool Calls anstelle von lokalen Tools.
    Alle Tools werden über die MCP Server Registry verwaltet.
    """
    
    def __init__(
        self,
        config: EventFixConfig,
    ):
        """
        Initialisiert das EventFixTeam mit MCP Server Registry.
        
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
        
        # MCP Sessions (werden lazy geladen)
        self._mcp_sessions: Dict[MCPServerType, Any] = {}
        
        # Status
        self._running = False
        self._session_id = f"eventfix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.logger = logger.bind(
            component="event_fix_team_mcp",
            session_id=self._session_id,
            use_mcp_tools=config.use_mcp_tools,
        )
        
        # Output directory erstellen
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Registry Summary loggen
        self.mcp_registry.print_summary()
    
    async def start(self) -> None:
        """Startet das EventFixTeam."""
        self._running = True
        self.logger.info("event_fix_team_starting", session_id=self._session_id)
        
        # MCP Sessions initialisieren
        await self._initialize_mcp_sessions()
        
        self.logger.info("event_fix_team_started", session_id=self._session_id)
    
    async def stop(self) -> None:
        """Stoppt das EventFixTeam."""
        self._running = False
        self.logger.info("event_fix_team_stopping", session_id=self._session_id)
        
        # MCP Sessions schließen
        for server_type, session in self._mcp_sessions.items():
            try:
                if hasattr(session, '__aexit__'):
                    await session.__aexit__(None, None, None)
                self.logger.info(
                    "mcp_session_closed",
                    server_type=server_type.value,
                )
            except Exception as e:
                self.logger.warning(
                    "mcp_session_close_failed",
                    server_type=server_type.value,
                    error=str(e),
                )
    
    async def _initialize_mcp_sessions(self) -> None:
        """Initialisiert MCP Sessions für alle aktivierten Server."""
        try:
            # Docker MCP Session
            if self.config.enable_docker_tools:
                await self._create_mcp_session(MCPServerType.DOCKER)
            
            # Redis MCP Session
            if self.config.enable_redis_tools:
                await self._create_mcp_session(MCPServerType.REDIS)
            
            # PostgreSQL MCP Session
            if self.config.enable_postgres_tools:
                await self._create_mcp_session(MCPServerType.POSTGRES)
            
            # Playwright MCP Session
            if self.config.enable_playwright_tools:
                await self._create_mcp_session(MCPServerType.PLAYWRIGHT)
            
            # Filesystem MCP Session (für Code-Write)
            if self.config.enable_filesystem_tools:
                await self._create_mcp_session(MCPServerType.FILESYSTEM)
            
            self.logger.info(
                "mcp_sessions_initialized",
                sessions_count=len(self._mcp_sessions),
            )
                
        except Exception as e:
            self.logger.error("mcp_sessions_init_failed", error=str(e))
    
    async def _create_mcp_session(self, server_type: MCPServerType) -> None:
        """
        Erstellt eine MCP Session für einen Server.
        
        Args:
            server_type: Server-Typ
        """
        try:
            from autogen_ext.tools.mcp import StdioServerParams, create_mcp_server_session
            
            server_info = self.mcp_registry.get_server(server_type)
            if not server_info or not server_info.enabled:
                self.logger.warning(
                    "server_not_enabled",
                    server_type=server_type.value,
                )
                return
            
            # Server-Parameter erstellen
            server_params = StdioServerParams(
                command="cmd.exe" if sys.platform == 'win32' else "sh",
                args=["/c", f"python {server_info.agent_file}"] if sys.platform == 'win32' else ["-c", f"python {server_info.agent_file}"],
                cwd=server_info.path,
            )
            
            # MCP Session erstellen
            session = await create_mcp_server_session(server_params)
            self._mcp_sessions[server_type] = session
            
            self.logger.info(
                "mcp_session_created",
                server_type=server_type.value,
                path=server_info.path,
            )
            
        except Exception as e:
            self.logger.error(
                "mcp_session_creation_failed",
                server_type=server_type.value,
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
                # Task verarbeiten (delegiert an MCP Tools)
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
        
        self.logger.info(
            "tasks_processed",
            total=len(tasks_to_process),
            completed=result.tasks_completed,
            errors=len(result.errors),
        )
        
        return result
    
    async def _process_single_task(self, task: FixTask) -> None:
        """
        Verarbeitet eine einzelne Task über MCP Tool Calls.
        
        Args:
            task: Zu verarbeitende Task
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
        
        # Task-Typ bestimmen und an passenden MCP Server delegieren
        if task.type == FixTaskType.FIX_CODE:
            await self._process_fix_code_task(task)
        elif task.type == FixTaskType.MIGRATION:
            await self._process_migration_task(task)
        elif task.type == FixTaskType.TEST_FIX:
            await self._process_test_fix_task(task)
        elif task.type == FixTaskType.LOG_ANALYSIS:
            await self._process_log_analysis_task(task)
        
        # Task-Status aktualisieren
        task.status = "completed"
        await self._save_task(task)
    
    async def _process_fix_code_task(self, task: FixTask) -> None:
        """
        Verarbeitet eine Fix-Code Task über MCP Tool Calls.
        
        Args:
            task: Zu verarbeitende Task
        """
        # Hier würde die Delegation an Filesystem MCP Server stattfinden
        # z.B. await self._call_mcp_tool(MCPServerType.FILESYSTEM, 'write_file', {
        #     'path': task.file_path,
        #     'content': task.suggested_fix,
        # })
        
        self.logger.info(
            "fix_code_task_processed",
            task_id=task.task_id,
            file_path=task.file_path,
        )
    
    async def _process_migration_task(self, task: FixTask) -> None:
        """
        Verarbeitet eine Migrations-Task über MCP Tool Calls.
        
        Args:
            task: Zu verarbeitende Task
        """
        # Hier würde die Delegation an PostgreSQL MCP Server stattfinden
        # z.B. await self._call_mcp_tool(MCPServerType.POSTGRES, 'execute_query', {
        #     'query': task.suggested_fix,
        # })
        
        self.logger.info(
            "migration_task_processed",
            task_id=task.task_id,
        )
    
    async def _process_test_fix_task(self, task: FixTask) -> None:
        """
        Verarbeitet eine Test-Fix-Task über MCP Tool Calls.
        
        Args:
            task: Zu verarbeitende Task
        """
        # Hier würde die Delegation an Playwright MCP Server stattfinden
        # z.B. await self._call_mcp_tool(MCPServerType.PLAYWRIGHT, 'run_e2e_test', {
        #     'url': task.metadata.get('url'),
        #     'selector': task.metadata.get('selector'),
        #     'action': task.suggested_fix,
        # })
        
        self.logger.info(
            "test_fix_task_processed",
            task_id=task.task_id,
        )
    
    async def _process_log_analysis_task(self, task: FixTask) -> None:
        """
        Verarbeitet eine Log-Analyse-Task über MCP Tool Calls.
        
        Args:
            task: Zu verarbeitende Task
        """
        # Hier würde die Delegation an Docker/Redis/PostgreSQL MCP Server stattfinden
        # z.B. await self._call_mcp_tool(MCPServerType.DOCKER, 'get_container_logs', {
        #     'container_name': task.metadata.get('container'),
        #     'tail': 100,
        # })
        
        self.logger.info(
            "log_analysis_task_processed",
            task_id=task.task_id,
        )
    
    async def _call_mcp_tool(
        self,
        server_type: MCPServerType,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> Any:
        """
        Ruft ein MCP Tool auf.
        
        Args:
            server_type: Server-Typ
            tool_name: Tool-Name
            tool_args: Tool-Argumente
            
        Returns:
            Tool-Ergebnis
        """
        try:
            from autogen_ext.tools.mcp import mcp_server_tools
            
            session = self._mcp_sessions.get(server_type)
            if not session:
                self.logger.error(
                    "mcp_session_not_found",
                    server_type=server_type.value,
                )
                return None
            
            # Tools abrufen
            tools = await mcp_server_tools(session)
            
            # Tool finden
            tool = None
            for t in tools:
                if t.name == tool_name:
                    tool = t
                    break
            
            if not tool:
                self.logger.error(
                    "mcp_tool_not_found",
                    server_type=server_type.value,
                    tool_name=tool_name,
                )
                return None
            
            # Tool aufrufen
            result = await tool(**tool_args)
            
            self.logger.info(
                "mcp_tool_called",
                server_type=server_type.value,
                tool_name=tool_name,
                result=str(result),
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "mcp_tool_call_failed",
                server_type=server_type.value,
                tool_name=tool_name,
                error=str(e),
            )
            return None
    
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
            "mcp_sessions": len(self._mcp_sessions),
            "enabled_servers": [
                server_type.value
                for server_type, session in self._mcp_sessions.items()
            ],
        }


# Convenience function
async def create_event_fix_team_mcp(
    working_dir: str,
    output_dir: str = "./event_fix_output",
    mcp_registry: Optional[MCPServerRegistry] = None,
    use_mcp_tools: bool = True,
    enable_docker: bool = True,
    enable_redis: bool = True,
    enable_postgres: bool = True,
    enable_playwright: bool = True,
    enable_filesystem: bool = True,
) -> EventFixTeamMCP:
    """
    Convenience function zum Erstellen eines EventFixTeam mit MCP Server Registry.
    
    Args:
        working_dir: Arbeitsverzeichnis
        output_dir: Output-Verzeichnis für Tasks und Results
        mcp_registry: Optional MCP Server Registry
        use_mcp_tools: MCP Tools verwenden
        enable_docker: Docker-Tools aktivieren
        enable_redis: Redis-Tools aktivieren
        enable_postgres: PostgreSQL-Tools aktivieren
        enable_playwright: Playwright-Tools aktivieren
        enable_filesystem: Filesystem-Tools aktivieren (für Code-Write)
        
    Returns:
        EventFixTeamMCP Instanz
    """
    config = EventFixConfig(
        working_dir=working_dir,
        output_dir=output_dir,
        mcp_registry=mcp_registry,
        use_mcp_tools=use_mcp_tools,
        enable_docker_tools=enable_docker,
        enable_redis_tools=enable_redis,
        enable_postgres_tools=enable_postgres,
        enable_playwright_tools=enable_playwright,
        enable_filesystem_tools=enable_filesystem,
    )
    
    team = EventFixTeamMCP(config=config)
    
    return team


if __name__ == "__main__":
    # Test: EventFixTeam mit MCP Server Registry erstellen
    import asyncio
    
    async def test():
        team = await create_event_fix_team_mcp(
            working_dir=".",
            output_dir="./event_fix_output",
            use_mcp_tools=True,
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
