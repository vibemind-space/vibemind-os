"""
LogAgent - Spezialisiert auf Log-Analyse und Monitoring
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from .base_agent import BaseAgent
from .grpc_client import GrpcClient
from .proto.agent_service_pb2 import (
    TaskRequest, TaskResponse, TaskStatus, 
    TaskType, TaskPriority, AgentCapability
)

logger = logging.getLogger(__name__)


class LogAgent(BaseAgent):
    """
    Agent für Log-Analyse und Monitoring.
    """
    
    def __init__(self, agent_id: str, grpc_client: GrpcClient):
        super().__init__(agent_id, "LogAgent", grpc_client)
        self.capabilities = [
            AgentCapability.LOG_ANALYSIS,
            AgentCapability.MONITORING,
            AgentCapability.DEBUGGING,
            AgentCapability.ALERTING
        ]
    
    async def collect_logs_task(
        self,
        service_name: str,
        log_source: str,
        time_range: str = "1h",
        log_level: str = "INFO",
        priority: TaskPriority = TaskPriority.MEDIUM,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task zum Sammeln von Logs.
        
        Args:
            service_name: Name des Services
            log_source: Log-Quelle (docker, kubernetes, file)
            time_range: Zeitbereich (1h, 6h, 24h, 7d)
            log_level: Log-Level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "service_name": service_name,
            "log_source": log_source,
            "time_range": time_range,
            "log_level": log_level,
            "operation": "collect_logs"
        }
        
        task_request = TaskRequest(
            task_type=TaskType.LOG_ANALYSIS,
            priority=priority,
            description=f"Logs sammeln: {service_name}",
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"Log-Sammel Task erstellt: {response.task_id}")
        return response.task_id
    
    async def analyze_logs_task(
        self,
        log_file: str,
        analysis_type: str = "error_detection",
        patterns: Optional[List[str]] = None,
        priority: TaskPriority = TaskPriority.HIGH,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task zur Log-Analyse.
        
        Args:
            log_file: Pfad zur Log-Datei
            analysis_type: Analyse-Typ (error_detection, pattern_matching, anomaly_detection)
            patterns: Liste von Mustern zum Suchen
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "log_file": log_file,
            "analysis_type": analysis_type,
            "patterns": patterns or [],
            "operation": "analyze_logs"
        }
        
        task_request = TaskRequest(
            task_type=TaskType.LOG_ANALYSIS,
            priority=priority,
            description=f"Logs analysieren: {log_file}",
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"Log-Analyse Task erstellt: {response.task_id}")
        return response.task_id
    
    async def monitor_service_task(
        self,
        service_name: str,
        metrics: List[str],
        alert_thresholds: Optional[Dict[str, Any]] = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task zur Service-Überwachung.
        
        Args:
            service_name: Name des Services
            metrics: Liste der zu überwachenden Metriken
            alert_thresholds: Schwellenwerte für Alerts
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "service_name": service_name,
            "metrics": metrics,
            "alert_thresholds": alert_thresholds or {},
            "operation": "monitor_service"
        }
        
        task_request = TaskRequest(
            task_type=TaskType.MONITORING,
            priority=priority,
            description=f"Service überwachen: {service_name}",
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"Service-Monitoring Task erstellt: {response.task_id}")
        return response.task_id
    
    async def create_alert_task(
        self,
        alert_name: str,
        condition: str,
        severity: str = "WARNING",
        notification_channels: Optional[List[str]] = None,
        priority: TaskPriority = TaskPriority.HIGH,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task zum Erstellen eines Alerts.
        
        Args:
            alert_name: Name des Alerts
            condition: Bedingung für den Alert
            severity: Schweregrad (INFO, WARNING, ERROR, CRITICAL)
            notification_channels: Benachrichtigungs-Kanäle
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "alert_name": alert_name,
            "condition": condition,
            "severity": severity,
            "notification_channels": notification_channels or [],
            "operation": "create_alert"
        }
        
        task_request = TaskRequest(
            task_type=TaskType.MONITORING,
            priority=priority,
            description=f"Alert erstellen: {alert_name}",
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"Alert-Erstell Task erstellt: {response.task_id}")
        return response.task_id
    
    async def debug_issue_task(
        self,
        issue_description: str,
        log_files: List[str],
        context: Optional[Dict[str, Any]] = None,
        priority: TaskPriority = TaskPriority.CRITICAL,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task zum Debuggen eines Issues.
        
        Args:
            issue_description: Beschreibung des Issues
            log_files: Liste der Log-Dateien
            context: Zusätzlicher Kontext
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "issue_description": issue_description,
            "log_files": log_files,
            "context": context or {},
            "operation": "debug_issue"
        }
        
        task_request = TaskRequest(
            task_type=TaskType.DEBUGGING,
            priority=priority,
            description=f"Issue debuggen: {issue_description}",
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"Debug Task erstellt: {response.task_id}")
        return response.task_id
    
    async def generate_report_task(
        self,
        report_type: str,
        time_range: str = "24h",
        services: Optional[List[str]] = None,
        priority: TaskPriority = TaskPriority.LOW,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task zur Berichtserstellung.
        
        Args:
            report_type: Bericht-Typ (error_summary, performance, availability)
            time_range: Zeitbereich (1h, 6h, 24h, 7d)
            services: Liste der Services
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "report_type": report_type,
            "time_range": time_range,
            "services": services or [],
            "operation": "generate_report"
        }
        
        task_request = TaskRequest(
            task_type=TaskType.LOG_ANALYSIS,
            priority=priority,
            description=f"Bericht erstellen: {report_type}",
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"Bericht-Erstell Task erstellt: {response.task_id}")
        return response.task_id
    
    async def process_event(self, event: Dict[str, Any]) -> List[str]:
        """
        Verarbeitet ein Event und erstellt entsprechende Tasks.
        
        Args:
            event: Event-Daten
            
        Returns:
            Liste der erstellten Task-IDs
        """
        event_type = event.get("type", "unknown")
        task_ids = []
        
        try:
            if event_type == "log_collection_request":
                task_id = await self.collect_logs_task(
                    service_name=event["service_name"],
                    log_source=event["log_source"],
                    time_range=event.get("time_range", "1h"),
                    log_level=event.get("log_level", "INFO"),
                    priority=self._parse_priority(event.get("priority", "medium"))
                )
                task_ids.append(task_id)
            
            elif event_type == "log_analysis_request":
                task_id = await self.analyze_logs_task(
                    log_file=event["log_file"],
                    analysis_type=event.get("analysis_type", "error_detection"),
                    patterns=event.get("patterns"),
                    priority=self._parse_priority(event.get("priority", "high"))
                )
                task_ids.append(task_id)
            
            elif event_type == "service_monitoring_request":
                task_id = await self.monitor_service_task(
                    service_name=event["service_name"],
                    metrics=event["metrics"],
                    alert_thresholds=event.get("alert_thresholds"),
                    priority=self._parse_priority(event.get("priority", "medium"))
                )
                task_ids.append(task_id)
            
            elif event_type == "alert_creation_request":
                task_id = await self.create_alert_task(
                    alert_name=event["alert_name"],
                    condition=event["condition"],
                    severity=event.get("severity", "WARNING"),
                    notification_channels=event.get("notification_channels"),
                    priority=self._parse_priority(event.get("priority", "high"))
                )
                task_ids.append(task_id)
            
            elif event_type == "debug_request":
                task_id = await self.debug_issue_task(
                    issue_description=event["issue_description"],
                    log_files=event["log_files"],
                    context=event.get("context"),
                    priority=self._parse_priority(event.get("priority", "critical"))
                )
                task_ids.append(task_id)
            
            elif event_type == "report_generation_request":
                task_id = await self.generate_report_task(
                    report_type=event["report_type"],
                    time_range=event.get("time_range", "24h"),
                    services=event.get("services"),
                    priority=self._parse_priority(event.get("priority", "low"))
                )
                task_ids.append(task_id)
            
            else:
                logger.warning(f"Unbekannter Event-Typ: {event_type}")
        
        except Exception as e:
            logger.error(f"Fehler bei der Event-Verarbeitung: {e}")
            raise
        
        return task_ids
    
    def _parse_priority(self, priority_str: str) -> TaskPriority:
        """Parst Prioritäts-String zu Enum."""
        priority_map = {
            "low": TaskPriority.LOW,
            "medium": TaskPriority.MEDIUM,
            "high": TaskPriority.HIGH,
            "critical": TaskPriority.CRITICAL
        }
        return priority_map.get(priority_str.lower(), TaskPriority.MEDIUM)
