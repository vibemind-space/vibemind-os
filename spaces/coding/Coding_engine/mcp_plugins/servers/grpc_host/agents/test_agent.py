"""
TestAgent - Spezialisiert auf automatisiertes Testing mit Playwright
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


class TestAgent(BaseAgent):
    """
    Agent für automatisiertes Testing mit Playwright.
    """
    
    def __init__(self, agent_id: str, grpc_client: GrpcClient):
        super().__init__(agent_id, "TestAgent", grpc_client)
        self.capabilities = [
            AgentCapability.TESTING,
            AgentCapability.E2E_TESTING,
            AgentCapability.UI_TESTING,
            AgentCapability.API_TESTING
        ]
    
    async def e2e_test_task(
        self,
        test_file: str,
        test_description: str,
        test_environment: str = "staging",
        priority: TaskPriority = TaskPriority.HIGH,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task für E2E-Testing.
        
        Args:
            test_file: Pfad zur Test-Datei
            test_description: Beschreibung des Tests
            test_environment: Test-Umgebung (staging, production, local)
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "test_file": test_file,
            "test_description": test_description,
            "test_environment": test_environment,
            "test_type": "e2e",
            "operation": "run_e2e_test"
        }
        
        task_request = TaskRequest(
            task_type=TaskType.TESTING,
            priority=priority,
            description=f"E2E-Test: {test_file}",
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"E2E-Test Task erstellt: {response.task_id}")
        return response.task_id
    
    async def ui_test_task(
        self,
        test_file: str,
        test_description: str,
        browser_type: str = "chromium",
        headless: bool = True,
        priority: TaskPriority = TaskPriority.HIGH,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task für UI-Testing mit Playwright.
        
        Args:
            test_file: Pfad zur Test-Datei
            test_description: Beschreibung des Tests
            browser_type: Browser-Typ (chromium, firefox, webkit)
            headless: Ob der Test im Headless-Modus läuft
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "test_file": test_file,
            "test_description": test_description,
            "browser_type": browser_type,
            "headless": headless,
            "test_type": "ui",
            "operation": "run_ui_test"
        }
        
        task_request = TaskRequest(
            task_type=TaskType.TESTING,
            priority=priority,
            description=f"UI-Test: {test_file}",
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"UI-Test Task erstellt: {response.task_id}")
        return response.task_id
    
    async def api_test_task(
        self,
        test_file: str,
        test_description: str,
        api_endpoint: str,
        http_method: str = "GET",
        priority: TaskPriority = TaskPriority.HIGH,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task für API-Testing.
        
        Args:
            test_file: Pfad zur Test-Datei
            test_description: Beschreibung des Tests
            api_endpoint: API-Endpoint
            http_method: HTTP-Methode (GET, POST, PUT, DELETE)
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "test_file": test_file,
            "test_description": test_description,
            "api_endpoint": api_endpoint,
            "http_method": http_method,
            "test_type": "api",
            "operation": "run_api_test"
        }
        
        task_request = TaskRequest(
            task_type=TaskType.TESTING,
            priority=priority,
            description=f"API-Test: {api_endpoint}",
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"API-Test Task erstellt: {response.task_id}")
        return response.task_id
    
    async def performance_test_task(
        self,
        test_file: str,
        test_description: str,
        load_pattern: str = "constant",
        duration: int = 60,
        priority: TaskPriority = TaskPriority.MEDIUM,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task für Performance-Testing.
        
        Args:
            test_file: Pfad zur Test-Datei
            test_description: Beschreibung des Tests
            load_pattern: Last-Muster (constant, ramp_up, spike)
            duration: Dauer in Sekunden
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "test_file": test_file,
            "test_description": test_description,
            "load_pattern": load_pattern,
            "duration": duration,
            "test_type": "performance",
            "operation": "run_performance_test"
        }
        
        task_request = TaskRequest(
            task_type=TaskType.TESTING,
            priority=priority,
            description=f"Performance-Test: {test_file}",
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"Performance-Test Task erstellt: {response.task_id}")
        return response.task_id
    
    async def accessibility_test_task(
        self,
        test_file: str,
        test_description: str,
        wcag_level: str = "AA",
        priority: TaskPriority = TaskPriority.MEDIUM,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task für Accessibility-Testing.
        
        Args:
            test_file: Pfad zur Test-Datei
            test_description: Beschreibung des Tests
            wcag_level: WCAG-Level (A, AA, AAA)
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "test_file": test_file,
            "test_description": test_description,
            "wcag_level": wcag_level,
            "test_type": "accessibility",
            "operation": "run_accessibility_test"
        }
        
        task_request = TaskRequest(
            task_type=TaskType.TESTING,
            priority=priority,
            description=f"Accessibility-Test: {test_file}",
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"Accessibility-Test Task erstellt: {response.task_id}")
        return response.task_id
    
    async def visual_regression_test_task(
        self,
        test_file: str,
        test_description: str,
        baseline_path: str,
        screenshot_path: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task für Visual-Regression-Testing.
        
        Args:
            test_file: Pfad zur Test-Datei
            test_description: Beschreibung des Tests
            baseline_path: Pfad zum Baseline-Screenshot
            screenshot_path: Pfad zum aktuellen Screenshot
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "test_file": test_file,
            "test_description": test_description,
            "baseline_path": baseline_path,
            "screenshot_path": screenshot_path,
            "test_type": "visual_regression",
            "operation": "run_visual_regression_test"
        }
        
        task_request = TaskRequest(
            task_type=TaskType.TESTING,
            priority=priority,
            description=f"Visual-Regression-Test: {test_file}",
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"Visual-Regression-Test Task erstellt: {response.task_id}")
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
            if event_type == "e2e_test_request":
                task_id = await self.e2e_test_task(
                    test_file=event["test_file"],
                    test_description=event["test_description"],
                    test_environment=event.get("test_environment", "staging"),
                    priority=self._parse_priority(event.get("priority", "high"))
                )
                task_ids.append(task_id)
            
            elif event_type == "ui_test_request":
                task_id = await self.ui_test_task(
                    test_file=event["test_file"],
                    test_description=event["test_description"],
                    browser_type=event.get("browser_type", "chromium"),
                    headless=event.get("headless", True),
                    priority=self._parse_priority(event.get("priority", "high"))
                )
                task_ids.append(task_id)
            
            elif event_type == "api_test_request":
                task_id = await self.api_test_task(
                    test_file=event["test_file"],
                    test_description=event["test_description"],
                    api_endpoint=event["api_endpoint"],
                    http_method=event.get("http_method", "GET"),
                    priority=self._parse_priority(event.get("priority", "high"))
                )
                task_ids.append(task_id)
            
            elif event_type == "performance_test_request":
                task_id = await self.performance_test_task(
                    test_file=event["test_file"],
                    test_description=event["test_description"],
                    load_pattern=event.get("load_pattern", "constant"),
                    duration=event.get("duration", 60),
                    priority=self._parse_priority(event.get("priority", "medium"))
                )
                task_ids.append(task_id)
            
            elif event_type == "accessibility_test_request":
                task_id = await self.accessibility_test_task(
                    test_file=event["test_file"],
                    test_description=event["test_description"],
                    wcag_level=event.get("wcag_level", "AA"),
                    priority=self._parse_priority(event.get("priority", "medium"))
                )
                task_ids.append(task_id)
            
            elif event_type == "visual_regression_test_request":
                task_id = await self.visual_regression_test_task(
                    test_file=event["test_file"],
                    test_description=event["test_description"],
                    baseline_path=event["baseline_path"],
                    screenshot_path=event["screenshot_path"],
                    priority=self._parse_priority(event.get("priority", "medium"))
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
