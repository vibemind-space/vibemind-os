"""
LogAgent - Spezialisierter Agent für Log-Analyse und Performance-Monitoring.

Verantwortlichkeiten:
- Logs aus allen Services sammeln
- Fehlermuster erkennen
- Performance-Bottlenecks identifizieren
- Log-Analyse-Reports generieren
"""

import asyncio
import json
import os
import sys
import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import structlog

# Shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from mind.event_bus import EventBus, Event, EventType
from mind.shared_state import SharedState
from agents.autonomous_base import AutonomousAgent, AgentStatus
from ..event_fix_team import FixTask, FixTaskType, FixPriority

logger = structlog.get_logger(__name__)


@dataclass
class LogEntry:
    """Einzelner Log-Eintrag."""
    timestamp: str
    level: str  # "INFO", "WARNING", "ERROR", "DEBUG"
    service: str
    message: str
    container_name: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "service": self.service,
            "message": self.message,
            "container_name": self.container_name,
            "metadata": self.metadata,
        }


@dataclass
class LogAnalysisResult:
    """Ergebnis einer Log-Analyse."""
    analysis_id: str
    time_range: str
    total_entries: int = 0
    error_count: int = 0
    warning_count: int = 0
    error_patterns: Dict[str, int] = field(default_factory=dict)
    performance_issues: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    created_at: str = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> dict:
        return {
            "analysis_id": self.analysis_id,
            "time_range": self.time_range,
            "total_entries": self.total_entries,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "error_patterns": self.error_patterns,
            "performance_issues": self.performance_issues,
            "recommendations": self.recommendations,
            "created_at": self.created_at,
        }


@dataclass
class LogContext:
    """Kontext für Log-Analyse."""
    analysis_type: str  # "error_detection", "performance", "anomaly"
    time_range: str = "1h"
    services: List[str] = None
    containers: List[str] = None
    keywords: List[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.services is None:
            self.services = []
        if self.containers is None:
            self.containers = []
        if self.keywords is None:
            self.keywords = []
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> dict:
        return {
            "analysis_type": self.analysis_type,
            "time_range": self.time_range,
            "services": self.services,
            "containers": self.containers,
            "keywords": self.keywords,
            "metadata": self.metadata,
        }


class LogAgent(AutonomousAgent):
    """
    LogAgent - Analysiert Logs und erstellt Analyse-Tasks.
    
    Verwendet:
    - Docker Tools für Container-Logs
    - Redis Tools für Cache-Analyse
    - PostgreSQL Tools für Query-Analyse
    - Pattern-Erkennung für Fehlermuster
    
    Schreibt KEINEN Code direkt, sondern erstellt Analyse-Tasks.
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
        
        # Log Queue
        self._pending_analyses: List[LogContext] = []
        self._completed_analyses: List[LogAnalysisResult] = []
        
        # Pattern-Registrierung
        self._error_patterns = {
            "connection_refused": re.compile(r'connection refused', re.IGNORECASE),
            "timeout": re.compile(r'timeout', re.IGNORECASE),
            "out_of_memory": re.compile(r'out of memory|oom', re.IGNORECASE),
            "file_not_found": re.compile(r'file not found|no such file', re.IGNORECASE),
            "permission_denied": re.compile(r'permission denied', re.IGNORECASE),
            "database_error": re.compile(r'database error|sql error', re.IGNORECASE),
            "api_error": re.compile(r'api error|http error \d{3}', re.IGNORECASE),
        }
        
        self.logger = logger.bind(component="log_agent", agent=name)
    
    @property
    def subscribed_events(self) -> List[EventType]:
        """Events die dieser Agent abonniert."""
        return [
            EventType.LOG_ANALYSIS_REQUEST,
            EventType.PERFORMANCE_ISSUE,
            EventType.ANOMALY_DETECTED,
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
        Analysiert Events und führt Log-Analysen durch.
        
        Args:
            events: Liste von Events
            
        Returns:
            Optional Event mit Ergebnis
        """
        self.logger.info(
            "log_agent_acting",
            event_count=len(events),
        )
        
        # Tools initialisieren
        await self._initialize_tools()
        
        # Events verarbeiten
        for event in events:
            if event.type in self.subscribed_events:
                await self._handle_log_event(event)
        
        # Analysen verarbeiten
        if self._pending_analyses:
            await self._process_analyses()
        
        return None
    
    async def _initialize_tools(self) -> None:
        """Initialisiert die Log-Tools."""
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
    
    async def _handle_log_event(self, event: Event) -> None:
        """
        Verarbeitet ein Log-Event.
        
        Args:
            event: Das zu verarbeitende Event
        """
        self.logger.info(
            "handling_log_event",
            event_type=event.type.value,
            source=event.source,
        )
        
        # Log-Kontext extrahieren
        context = self._extract_log_context(event)
        
        # Analyse basierend auf Event-Typ
        if event.type == EventType.LOG_ANALYSIS_REQUEST:
            await self._analyze_logs(context)
        elif event.type == EventType.PERFORMANCE_ISSUE:
            await self._analyze_performance(context)
        elif event.type == EventType.ANOMALY_DETECTED:
            await self._analyze_anomaly(context)
    
    def _extract_log_context(self, event: Event) -> LogContext:
        """
        Extrahiert Log-Kontext aus Event.
        
        Args:
            event: Das Event
            
        Returns:
            LogContext mit extrahierten Informationen
        """
        context = LogContext(
            analysis_type=event.type.value,
            metadata=event.data.copy() if event.data else {},
        )
        
        # Log-Informationen aus Metadaten extrahieren
        if event.data:
            context.time_range = event.data.get("time_range", "1h")
            context.services = event.data.get("services", [])
            context.containers = event.data.get("containers", [])
            context.keywords = event.data.get("keywords", [])
        
        return context
    
    async def _analyze_logs(self, context: LogContext) -> None:
        """
        Analysiert Logs und erstellt Analyse-Tasks.
        
        Args:
            context: Log-Kontext
        """
        self.logger.info(
            "analyzing_logs",
            time_range=context.time_range,
            services=context.services,
            containers=context.containers,
        )
        
        # Logs sammeln
        log_entries = await self._collect_logs(context)
        
        # Logs analysieren
        analysis_result = await self._analyze_log_entries(log_entries, context)
        
        self._completed_analyses.append(analysis_result)
        
        # Fix-Task erstellen wenn Fehler gefunden
        if analysis_result.error_count > 0 or analysis_result.performance_issues:
            await self._create_log_fix_task(analysis_result, context)
    
    async def _analyze_performance(self, context: LogContext) -> None:
        """
        Analysiert Performance-Issues und erstellt Analyse-Tasks.
        
        Args:
            context: Log-Kontext
        """
        self.logger.info(
            "analyzing_performance",
            time_range=context.time_range,
            services=context.services,
        )
        
        # Logs sammeln
        log_entries = await self._collect_logs(context)
        
        # Performance-Analyse
        analysis_result = await self._analyze_performance_logs(log_entries, context)
        
        self._completed_analyses.append(analysis_result)
        
        # Fix-Task erstellen
        if analysis_result.performance_issues:
            await self._create_log_fix_task(analysis_result, context)
    
    async def _analyze_anomaly(self, context: LogContext) -> None:
        """
        Analysiert Anomalien und erstellt Analyse-Tasks.
        
        Args:
            context: Log-Kontext
        """
        self.logger.info(
            "analyzing_anomaly",
            time_range=context.time_range,
            keywords=context.keywords,
        )
        
        # Logs sammeln
        log_entries = await self._collect_logs(context)
        
        # Anomalie-Analyse
        analysis_result = await self._analyze_anomaly_logs(log_entries, context)
        
        self._completed_analyses.append(analysis_result)
        
        # Fix-Task erstellen
        if analysis_result.error_count > 0 or analysis_result.performance_issues:
            await self._create_log_fix_task(analysis_result, context)
    
    async def _collect_logs(self, context: LogContext) -> List[LogEntry]:
        """
        Sammelt Logs aus verschiedenen Quellen.
        
        Args:
            context: Log-Kontext
            
        Returns:
            Liste von Log-Einträgen
        """
        log_entries = []
        
        # Docker-Logs
        if self.enable_docker and self._docker_tools and context.containers:
            for container in context.containers:
                try:
                    logs_result = await self._docker_tools.get_container_logs(
                        container_name=container,
                        tail=500,  # Mehr Logs für Analyse
                    )
                    if logs_result.get("success"):
                        logs_text = logs_result.get("logs", "")
                        entries = self._parse_logs(logs_text, container, "docker")
                        log_entries.extend(entries)
                except Exception as e:
                    self.logger.warning("docker_log_collection_failed", container=container, error=str(e))
        
        # Redis-Logs (falls verfügbar)
        if self.enable_redis and self._redis_tools:
            try:
                redis_logs_result = await self._redis_tools.get_recent_logs(
                    limit=100,
                )
                if redis_logs_result.get("success"):
                    logs_text = redis_logs_result.get("logs", "")
                    entries = self._parse_logs(logs_text, "redis", "redis")
                    log_entries.extend(entries)
            except Exception as e:
                self.logger.warning("redis_log_collection_failed", error=str(e))
        
        # PostgreSQL-Logs (falls verfügbar)
        if self.enable_postgres and self._postgres_tools:
            try:
                postgres_logs_result = await self._postgres_tools.get_slow_queries(
                    limit=50,
                )
                if postgres_logs_result.get("success"):
                    queries = postgres_logs_result.get("queries", [])
                    for query in queries:
                        entry = LogEntry(
                            timestamp=datetime.now().isoformat(),
                            level="WARNING",
                            service="postgres",
                            message=f"Slow query: {query.get('query', '')[:200]}",
                            metadata={
                                "duration_ms": query.get("duration_ms", 0),
                                "query": query.get("query", ""),
                            },
                        )
                        log_entries.append(entry)
            except Exception as e:
                self.logger.warning("postgres_log_collection_failed", error=str(e))
        
        return log_entries
    
    def _parse_logs(self, logs_text: str, service: str, container_name: str) -> List[LogEntry]:
        """
        Parst Log-Text in Log-Einträge.
        
        Args:
            logs_text: Log-Text
            service: Service-Name
            container_name: Container-Name
            
        Returns:
            Liste von Log-Einträgen
        """
        entries = []
        
        for line in logs_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Log-Level extrahieren
            level = "INFO"
            if any(keyword in line.upper() for keyword in ["ERROR", "CRITICAL", "FATAL"]):
                level = "ERROR"
            elif any(keyword in line.upper() for keyword in ["WARNING", "WARN"]):
                level = "WARNING"
            elif "DEBUG" in line.upper():
                level = "DEBUG"
            
            entry = LogEntry(
                timestamp=datetime.now().isoformat(),
                level=level,
                service=service,
                message=line[:500],  # Limit Länge
                container_name=container_name,
            )
            
            entries.append(entry)
        
        return entries
    
    async def _analyze_log_entries(
        self,
        log_entries: List[LogEntry],
        context: LogContext,
    ) -> LogAnalysisResult:
        """
        Analysiert Log-Einträge auf Fehlermuster.
        
        Args:
            log_entries: Liste von Log-Einträgen
            context: Log-Kontext
            
        Returns:
            LogAnalysisResult
        """
        analysis_id = f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        error_count = 0
        warning_count = 0
        error_patterns = defaultdict(int)
        performance_issues = []
        
        for entry in log_entries:
            # Zählen
            if entry.level == "ERROR":
                error_count += 1
            elif entry.level == "WARNING":
                warning_count += 1
            
            # Pattern-Erkennung
            for pattern_name, pattern in self._error_patterns.items():
                if pattern.search(entry.message):
                    error_patterns[pattern_name] += 1
            
            # Performance-Issues
            if "slow" in entry.message.lower() or "timeout" in entry.message.lower():
                performance_issues.append({
                    "type": "slow_operation",
                    "message": entry.message,
                    "service": entry.service,
                    "timestamp": entry.timestamp,
                })
        
        # Empfehlungen generieren
        recommendations = self._generate_recommendations(error_patterns, performance_issues)
        
        return LogAnalysisResult(
            analysis_id=analysis_id,
            time_range=context.time_range,
            total_entries=len(log_entries),
            error_count=error_count,
            warning_count=warning_count,
            error_patterns=dict(error_patterns),
            performance_issues=performance_issues,
            recommendations=recommendations,
        )
    
    async def _analyze_performance_logs(
        self,
        log_entries: List[LogEntry],
        context: LogContext,
    ) -> LogAnalysisResult:
        """
        Analysiert Logs auf Performance-Issues.
        
        Args:
            log_entries: Liste von Log-Einträgen
            context: Log-Kontext
            
        Returns:
            LogAnalysisResult
        """
        analysis_id = f"perf_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        performance_issues = []
        
        for entry in log_entries:
            # Performance-Keywords suchen
            perf_keywords = ["slow", "timeout", "latency", "delay", "bottleneck"]
            
            if any(keyword in entry.message.lower() for keyword in perf_keywords):
                performance_issues.append({
                    "type": "performance_issue",
                    "message": entry.message,
                    "service": entry.service,
                    "timestamp": entry.timestamp,
                })
        
        # Empfehlungen generieren
        recommendations = []
        if performance_issues:
            recommendations.append("Review slow operations and optimize queries")
            recommendations.append("Check for resource bottlenecks (CPU, memory, I/O)")
            recommendations.append("Consider caching frequently accessed data")
            recommendations.append("Scale services if consistently hitting limits")
        
        return LogAnalysisResult(
            analysis_id=analysis_id,
            time_range=context.time_range,
            total_entries=len(log_entries),
            error_count=0,
            warning_count=0,
            performance_issues=performance_issues,
            recommendations=recommendations,
        )
    
    async def _analyze_anomaly_logs(
        self,
        log_entries: List[LogEntry],
        context: LogContext,
    ) -> LogAnalysisResult:
        """
        Analysiert Logs auf Anomalien.
        
        Args:
            log_entries: Liste von Log-Einträgen
            context: Log-Kontext
            
        Returns:
            LogAnalysisResult
        """
        analysis_id = f"anomaly_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        error_count = 0
        error_patterns = defaultdict(int)
        performance_issues = []
        
        # Nach Keywords suchen
        for entry in log_entries:
            if context.keywords:
                for keyword in context.keywords:
                    if keyword.lower() in entry.message.lower():
                        error_count += 1
                        error_patterns[keyword] += 1
        
        # Anomalien identifizieren
        if error_count > 0:
            performance_issues.append({
                "type": "anomaly",
                "message": f"Found {error_count} anomalies matching keywords",
                "keywords": context.keywords,
            })
        
        # Empfehlungen generieren
        recommendations = []
        if error_count > 0:
            recommendations.append("Investigate anomalies and root cause")
            recommendations.append("Check if keywords are still relevant")
            recommendations.append("Review recent changes that might have caused anomalies")
        
        return LogAnalysisResult(
            analysis_id=analysis_id,
            time_range=context.time_range,
            total_entries=len(log_entries),
            error_count=error_count,
            error_patterns=dict(error_patterns),
            performance_issues=performance_issues,
            recommendations=recommendations,
        )
    
    def _generate_recommendations(
        self,
        error_patterns: Dict[str, int],
        performance_issues: List[Dict[str, Any]],
    ) -> List[str]:
        """
        Generiert Empfehlungen basierend auf Analyse.
        
        Args:
            error_patterns: Gefundene Fehlermuster
            performance_issues: Performance-Issues
            
        Returns:
            Liste von Empfehlungen
        """
        recommendations = []
        
        # Basierend auf Fehlermustern
        if error_patterns.get("connection_refused", 0) > 0:
            recommendations.append("Check network connectivity and service availability")
        
        if error_patterns.get("timeout", 0) > 0:
            recommendations.append("Increase timeout values or optimize slow operations")
        
        if error_patterns.get("out_of_memory", 0) > 0:
            recommendations.append("Increase memory limits or check for memory leaks")
        
        if error_patterns.get("database_error", 0) > 0:
            recommendations.append("Review database queries and optimize indexes")
        
        if error_patterns.get("api_error", 0) > 0:
            recommendations.append("Check API endpoints and error handling")
        
        # Basierend auf Performance-Issues
        if performance_issues:
            slow_count = len([i for i in performance_issues if i.get("type") == "slow_operation"])
            if slow_count > 5:
                recommendations.append("Multiple slow operations detected - consider optimization")
        
        return recommendations
    
    async def _create_log_fix_task(
        self,
        analysis_result: LogAnalysisResult,
        context: LogContext,
    ) -> None:
        """
        Erstellt eine Fix-Task basierend auf Log-Analyse.
        
        Args:
            analysis_result: Analyse-Ergebnis
            context: Log-Kontext
        """
        self.logger.info(
            "creating_log_fix_task",
            analysis_id=analysis_result.analysis_id,
            error_count=analysis_result.error_count,
        )
        
        # Priorität bestimmen
        if analysis_result.error_count > 10:
            priority = FixPriority.CRITICAL
        elif analysis_result.error_count > 5:
            priority = FixPriority.HIGH
        elif analysis_result.performance_issues:
            priority = FixPriority.MEDIUM
        else:
            priority = FixPriority.LOW
        
        # Beschreibung erstellen
        description_parts = [
            f"Log Analysis: {analysis_result.analysis_id}",
            f"Time Range: {analysis_result.time_range}",
            f"Errors: {analysis_result.error_count}",
            f"Warnings: {analysis_result.warning_count}",
        ]
        
        if analysis_result.error_patterns:
            top_errors = sorted(
                analysis_result.error_patterns.items(),
                key=lambda x: x[1],
                reverse=True
            )[:3]
            description_parts.append(f"Top Errors: {', '.join([f'{k} ({v})' for k, v in top_errors])}")
        
        description = " | ".join(description_parts)
        
        # Suggested Fix erstellen
        suggested_fix = "; ".join(analysis_result.recommendations)
        
        # Metadaten
        metadata = {
            "analysis_id": analysis_result.analysis_id,
            "time_range": analysis_result.time_range,
            "total_entries": analysis_result.total_entries,
            "error_count": analysis_result.error_count,
            "warning_count": analysis_result.warning_count,
            "error_patterns": analysis_result.error_patterns,
            "performance_issues": analysis_result.performance_issues,
            "recommendations": analysis_result.recommendations,
            "services": context.services,
            "containers": context.containers,
            "keywords": context.keywords,
        }
        
        # Task erstellen
        from ..event_fix_team import create_fix_task
        task = await create_fix_task(
            task_type=FixTaskType.LOG_ANALYSIS,
            priority=priority,
            description=description,
            file_path=None,
            suggested_fix=suggested_fix,
            metadata=metadata,
        )
        
        self.logger.info(
            "log_fix_task_created",
            analysis_id=analysis_result.analysis_id,
            task_id=task.task_id,
        )
    
    async def _process_analyses(self) -> None:
        """Verarbeitet alle ausstehenden Analysen."""
        self.logger.info(
            "processing_analyses",
            count=len(self._pending_analyses),
        )
        
        for analysis_context in self._pending_analyses:
            self.logger.info(
                "processing_analysis",
                type=analysis_context.analysis_type,
                time_range=analysis_context.time_range,
            )
            
            # Analyse wird hier NICHT ausgeführt, sondern nur geloggt
            # Die eigentliche Ausführung passiert über die Analyse-Methoden
        
        self._completed_analyses.extend([
            LogAnalysisResult(
                analysis_id=f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                time_range=analysis_context.time_range,
                metadata=analysis_context.metadata,
            )
            for analysis_context in self._pending_analyses
        ])
        
        self._pending_analyses.clear()


# Convenience function
async def create_log_agent(
    name: str = "LogAgent",
    event_bus: Optional[EventBus] = None,
    shared_state: Optional[SharedState] = None,
    working_dir: str = ".",
    enable_docker: bool = True,
    enable_redis: bool = True,
    enable_postgres: bool = True,
) -> LogAgent:
    """
    Convenience function zum Erstellen eines LogAgent.
    
    Args:
        name: Name des Agents
        event_bus: Optionaler EventBus
        shared_state: Optionaler SharedState
        working_dir: Arbeitsverzeichnis
        enable_docker: Docker-Tools aktivieren
        enable_redis: Redis-Tools aktivieren
        enable_postgres: PostgreSQL-Tools aktivieren
        
    Returns:
        LogAgent Instanz
    """
    # EventBus und SharedState erstellen falls nicht vorhanden
    if event_bus is None:
        from mind.event_bus import create_event_bus
        event_bus = await create_event_bus()
    
    if shared_state is None:
        from mind.shared_state import SharedState
        shared_state = SharedState()
    
    agent = LogAgent(
        name=name,
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=working_dir,
        enable_docker=enable_docker,
        enable_redis=enable_redis,
        enable_postgres=enable_postgres,
    )
    
    return agent
