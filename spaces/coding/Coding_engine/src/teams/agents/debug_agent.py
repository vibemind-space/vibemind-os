"""
DebugAgent - Spezialisierter Agent für Debugging mit Docker, Redis, PostgreSQL.

Verantwortlichkeiten:
- Container-Logs abrufen
- Datenbank-Status prüfen
- Redis-Cache analysieren
- Debug-Tasks an File-Write delegieren (kein direktes Code-Schreiben)
"""

import asyncio
import json
import os
import sys
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import structlog

# Shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from mind.event_bus import EventBus, Event, EventType
from mind.shared_state import SharedState
from agents.autonomous_base import AutonomousAgent, AgentStatus
from ..event_fix_team import FixTask, FixTaskType, FixPriority

logger = structlog.get_logger(__name__)


@dataclass
class DebugContext:
    """Kontext für Debug-Operation."""
    container_name: Optional[str] = None
    error_message: str = ""
    error_type: str = ""
    stack_trace: Optional[str] = None
    timestamp: str = ""
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> dict:
        return {
            "container_name": self.container_name,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "stack_trace": self.stack_trace,
            "timestamp": self.timestamp,
            "metadata": self.metadata or {},
        }


class DebugAgent(AutonomousAgent):
    """
    DebugAgent - Analysiert Fehler und erstellt Fix-Tasks.
    
    Verwendet:
    - Docker Tools für Container-Logs und Status
    - Redis Tools für Cache-Analyse
    - PostgreSQL Tools für Datenbank-Status
    
    Schreibt KEINEN Code direkt, sondern erstellt Fix-Tasks.
    """
    
    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        enable_docker: bool = True,
        enable_redis: bool = True,
        enable_postgres: bool = True,
    ):
        super().__init__(name, event_bus, shared_state, working_dir)
        
        self.enable_docker = enable_docker
        self.enable_redis = enable_redis
        self.enable_postgres = enable_postgres
        
        # Tools (werden lazy geladen)
        self._docker_tools = None
        self._redis_tools = None
        self._postgres_tools = None
        
        # Task Queue
        self._pending_tasks: List[FixTask] = []
        
        self.logger = logger.bind(component="debug_agent", agent=name)
    
    @property
    def subscribed_events(self) -> List[EventType]:
        """Events die dieser Agent abonniert."""
        return [
            EventType.ERROR_DETECTED,
            EventType.CRASH_DETECTED,
            EventType.DEBUG_REQUEST,
        ]
    
    async def should_act(self, events: List[Event]) -> bool:
        """Entscheidet ob der Agent agieren soll."""
        if not events:
            return False
        
        # Prüfen ob relevante Events vorhanden sind
        relevant_events = [
            e for e in events
            if e.type in self.subscribed_events
        ]
        
        return len(relevant_events) > 0
    
    async def act(self, events: List[Event]) -> Optional[Event]:
        """
        Analysiert Events und erstellt Fix-Tasks.
        
        Args:
            events: Liste von Events
            
        Returns:
            Optional Event mit Ergebnis
        """
        self.logger.info(
            "debug_agent_acting",
            event_count=len(events),
        )
        
        # Tools initialisieren
        await self._initialize_tools()
        
        # Events verarbeiten
        for event in events:
            if event.type in self.subscribed_events:
                await self._handle_debug_event(event)
        
        # Tasks verarbeiten
        if self._pending_tasks:
            await self._process_tasks()
        
        return None
    
    async def _initialize_tools(self) -> None:
        """Initialisiert die Debug-Tools."""
        try:
            if self.enable_docker and self._docker_tools is None:
                from ..tools.docker_debug_tools import DockerDebugTools
                self._docker_tools = DockerDebugTools()
                self.logger.info("docker_tools_initialized")
            
            if self.enable_redis and self._redis_tools is None:
                from ..tools.redis_debug_tools import RedisDebugTools
                self._redis_tools = RedisDebugTools()
                self.logger.info("redis_tools_initialized")
            
            if self.enable_postgres and self._postgres_tools is None:
                from ..tools.postgres_debug_tools import PostgresDebugTools
                self._postgres_tools = PostgresDebugTools()
                self.logger.info("postgres_tools_initialized")
                
        except ImportError as e:
            self.logger.error("tool_import_failed", error=str(e))
    
    async def _handle_debug_event(self, event: Event) -> None:
        """
        Verarbeitet ein Debug-Event.
        
        Args:
            event: Das zu verarbeitende Event
        """
        self.logger.info(
            "handling_debug_event",
            event_type=event.type.value,
            source=event.source,
        )
        
        # Debug-Kontext extrahieren
        context = self._extract_debug_context(event)
        
        # Analyse basierend auf Event-Typ
        if event.type == EventType.ERROR_DETECTED:
            await self._analyze_error(context)
        elif event.type == EventType.CRASH_DETECTED:
            await self._analyze_crash(context)
        elif event.type == EventType.DEBUG_REQUEST:
            await self._analyze_debug_request(context)
    
    def _extract_debug_context(self, event: Event) -> DebugContext:
        """
        Extrahiert Debug-Kontext aus Event.
        
        Args:
            event: Das Event
            
        Returns:
            DebugContext mit extrahierten Informationen
        """
        context = DebugContext(
            error_message=event.error_message or "",
            error_type=event.type.value,
            timestamp=event.timestamp.isoformat() if hasattr(event, 'timestamp') else "",
            metadata=event.data.copy() if event.data else {},
        )
        
        # Container-Name aus Metadaten extrahieren
        if event.data:
            context.container_name = event.data.get("container_name")
            context.stack_trace = event.data.get("stack_trace")
        
        return context
    
    async def _analyze_error(self, context: DebugContext) -> None:
        """
        Analysiert einen Fehler und erstellt Fix-Tasks.
        
        Args:
            context: Debug-Kontext
        """
        self.logger.info(
            "analyzing_error",
            error_type=context.error_type,
            container=context.container_name,
        )
        
        # Docker-Logs abrufen
        logs = ""
        if self.enable_docker and self._docker_tools and context.container_name:
            try:
                logs_result = await self._docker_tools.get_container_logs(
                    container_name=context.container_name,
                    tail=100,
                )
                if logs_result.get("success"):
                    logs = logs_result.get("logs", "")
            except Exception as e:
                self.logger.warning("docker_logs_failed", error=str(e))
        
        # Container-Stats abrufen
        stats = {}
        if self.enable_docker and self._docker_tools and context.container_name:
            try:
                stats_result = await self._docker_tools.get_container_stats(
                    container_name=context.container_name,
                )
                if stats_result.get("success"):
                    stats = stats_result.get("stats", {})
            except Exception as e:
                self.logger.warning("docker_stats_failed", error=str(e))
        
        # Redis-Cache prüfen
        cache_info = {}
        if self.enable_redis and self._redis_tools:
            try:
                cache_result = await self._redis_tools.analyze_cache_hit_rate(time_range="1h")
                if cache_result.get("success"):
                    cache_info = cache_result.get("cache_info", {})
            except Exception as e:
                self.logger.warning("redis_cache_failed", error=str(e))
        
        # Fix-Task erstellen
        task = await self._create_fix_task(
            context=context,
            logs=logs,
            stats=stats,
            cache_info=cache_info,
        )
        
        self._pending_tasks.append(task)
    
    async def _analyze_crash(self, context: DebugContext) -> None:
        """
        Analysiert einen Crash und erstellt Fix-Tasks.
        
        Args:
            context: Debug-Kontext
        """
        self.logger.info(
            "analyzing_crash",
            error_type=context.error_type,
            container=context.container_name,
        )
        
        # Stack-Trace analysieren
        root_cause = self._analyze_stack_trace(context.stack_trace)
        
        # Container-Status prüfen
        container_status = "unknown"
        if self.enable_docker and self._docker_tools and context.container_name:
            try:
                status_result = await self._docker_tools.get_container_status(
                    container_name=context.container_name,
                )
                if status_result.get("success"):
                    container_status = status_result.get("status", "unknown")
            except Exception as e:
                self.logger.warning("container_status_failed", error=str(e))
        
        # Fix-Task erstellen
        task = await self._create_fix_task(
            context=context,
            root_cause=root_cause,
            container_status=container_status,
        )
        
        self._pending_tasks.append(task)
    
    async def _analyze_debug_request(self, context: DebugContext) -> None:
        """
        Analysiert einen Debug-Request und erstellt Fix-Tasks.
        
        Args:
            context: Debug-Kontext
        """
        self.logger.info(
            "analyzing_debug_request",
            error_type=context.error_type,
        )
        
        # Umfassende Analyse durchführen
        # Logs, Stats, Cache, etc.
        
        # Fix-Task erstellen
        task = await self._create_fix_task(
            context=context,
            debug_mode=True,
        )
        
        self._pending_tasks.append(task)
    
    def _analyze_stack_trace(self, stack_trace: Optional[str]) -> str:
        """
        Analysiert einen Stack-Trace und extrahiert Root Cause.
        
        Args:
            stack_trace: Stack-Trace als String
            
        Returns:
            Root Cause als String
        """
        if not stack_trace:
            return "Unknown - no stack trace available"
        
        # Einfache Heuristik
        lines = stack_trace.split('\n')
        
        # Nach häufigen Fehlern suchen
        for line in lines:
            if 'ConnectionRefusedError' in line:
                return "Connection refused - service not reachable"
            elif 'TimeoutError' in line:
                return "Timeout - service not responding"
            elif 'MemoryError' in line or 'OutOfMemoryError' in line:
                return "Out of memory - increase memory limit"
            elif 'FileNotFoundError' in line:
                return "File not found - check file paths"
            elif 'ImportError' in line or 'ModuleNotFoundError' in line:
                return "Import error - check dependencies"
        
        # Erste Zeile als Root Cause verwenden
        if lines:
            return lines[0][:200]
        
        return "Unknown error"
    
    async def _create_fix_task(
        self,
        context: DebugContext,
        logs: str = "",
        stats: Dict[str, Any] = None,
        cache_info: Dict[str, Any] = None,
        root_cause: str = "",
        container_status: str = "",
        debug_mode: bool = False,
    ) -> FixTask:
        """
        Erstellt eine Fix-Task basierend auf Analyse.
        
        Args:
            context: Debug-Kontext
            logs: Container-Logs
            stats: Container-Statistiken
            cache_info: Redis-Cache-Informationen
            root_cause: Ermittelte Root Cause
            container_status: Container-Status
            debug_mode: Ob dies ein Debug-Request ist
            
        Returns:
            Erstellte FixTask
        """
        # Priorität bestimmen
        if context.error_type == "CRASH_DETECTED":
            priority = FixPriority.CRITICAL
        elif "timeout" in context.error_message.lower():
            priority = FixPriority.HIGH
        elif "memory" in context.error_message.lower():
            priority = FixPriority.HIGH
        else:
            priority = FixPriority.MEDIUM
        
        # Beschreibung erstellen
        description_parts = [
            f"Error: {context.error_message}",
        ]
        
        if root_cause:
            description_parts.append(f"Root Cause: {root_cause}")
        
        if container_status:
            description_parts.append(f"Container Status: {container_status}")
        
        if cache_info:
            hit_rate = cache_info.get("hit_rate", "N/A")
            description_parts.append(f"Cache Hit Rate: {hit_rate}")
        
        description = " | ".join(description_parts)
        
        # Suggested Fix erstellen
        suggested_fix = self._generate_suggested_fix(
            context=context,
            logs=logs,
            stats=stats,
            cache_info=cache_info,
            root_cause=root_cause,
        )
        
        # Metadaten
        metadata = {
            "container_name": context.container_name,
            "error_type": context.error_type,
            "logs_sample": logs[:500] if logs else "",
            "stats": stats or {},
            "cache_info": cache_info or {},
            "root_cause": root_cause,
            "container_status": container_status,
            "debug_mode": debug_mode,
        }
        
        # Task erstellen
        from ..event_fix_team import create_fix_task
        task = await create_fix_task(
            task_type=FixTaskType.FIX_CODE,
            priority=priority,
            description=description,
            file_path=context.metadata.get("file_path"),
            suggested_fix=suggested_fix,
            metadata=metadata,
        )
        
        return task
    
    def _generate_suggested_fix(
        self,
        context: DebugContext,
        logs: str = "",
        stats: Dict[str, Any] = None,
        cache_info: Dict[str, Any] = None,
        root_cause: str = "",
    ) -> str:
        """
        Generiert einen Fix-Vorschlag basierend auf Analyse.
        
        Args:
            context: Debug-Kontext
            logs: Container-Logs
            stats: Container-Statistiken
            cache_info: Redis-Cache-Informationen
            root_cause: Ermittelte Root Cause
            
        Returns:
            Suggested Fix als String
        """
        fixes = []
        
        # Basierend auf Root Cause
        if "connection refused" in root_cause.lower():
            fixes.append("Check if service is running and accessible")
            fixes.append("Verify network configuration and firewall rules")
        elif "timeout" in root_cause.lower():
            fixes.append("Increase timeout configuration")
            fixes.append("Check service performance and optimize queries")
        elif "out of memory" in root_cause.lower():
            fixes.append("Increase container memory limit")
            fixes.append("Check for memory leaks in application")
        elif "import error" in root_cause.lower():
            fixes.append("Install missing dependencies")
            fixes.append("Check import paths and module structure")
        
        # Basierend auf Stats
        if stats:
            cpu_usage = stats.get("cpu_percent", 0)
            memory_usage = stats.get("memory_percent", 0)
            
            if cpu_usage > 80:
                fixes.append(f"High CPU usage ({cpu_usage}%) - optimize code or scale")
            
            if memory_usage > 80:
                fixes.append(f"High memory usage ({memory_usage}%) - check for leaks or increase limit")
        
        # Basierend auf Cache
        if cache_info:
            hit_rate = cache_info.get("hit_rate", 100)
            if hit_rate < 50:
                fixes.append(f"Low cache hit rate ({hit_rate}%) - review caching strategy")
        
        return "; ".join(fixes) if fixes else "Review logs and error details for specific fix"
    
    async def _process_tasks(self) -> None:
        """Verarbeitet alle ausstehenden Tasks."""
        self.logger.info(
            "processing_tasks",
            count=len(self._pending_tasks),
        )
        
        for task in self._pending_tasks:
            self.logger.info(
                "processing_task",
                task_id=task.task_id,
                type=task.type.value,
            )
            
            # Task wird hier NICHT ausgeführt, sondern nur geloggt
            # Die eigentliche Ausführung passiert über File-Write Tools
        
        self._pending_tasks.clear()


# Convenience function
async def create_debug_agent(
    name: str = "DebugAgent",
    event_bus: Optional[EventBus] = None,
    shared_state: Optional[SharedState] = None,
    working_dir: str = ".",
    enable_docker: bool = True,
    enable_redis: bool = True,
    enable_postgres: bool = True,
) -> DebugAgent:
    """
    Convenience function zum Erstellen eines DebugAgent.
    
    Args:
        name: Name des Agents
        event_bus: Optionaler EventBus
        shared_state: Optionaler SharedState
        working_dir: Arbeitsverzeichnis
        enable_docker: Docker-Tools aktivieren
        enable_redis: Redis-Tools aktivieren
        enable_postgres: PostgreSQL-Tools aktivieren
        
    Returns:
        DebugAgent Instanz
    """
    # EventBus und SharedState erstellen falls nicht vorhanden
    if event_bus is None:
        from mind.event_bus import create_event_bus
        event_bus = await create_event_bus()
    
    if shared_state is None:
        from mind.shared_state import SharedState
        shared_state = SharedState()
    
    agent = DebugAgent(
        name=name,
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=working_dir,
        enable_docker=enable_docker,
        enable_redis=enable_redis,
        enable_postgres=enable_postgres,
    )
    
    return agent
