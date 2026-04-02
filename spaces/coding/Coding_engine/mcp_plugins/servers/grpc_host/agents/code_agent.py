"""
CodeAgent - Spezialisiert auf Code-Generierung und -Modifikation
Sendet Tasks an file_write statt Code direkt zu schreiben
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from .base_agent import BaseAgent
from .grpc_client import GrpcClient
from .proto.agent_service_pb2 import (
    TaskRequest, TaskResponse, TaskStatus, 
    TaskType, TaskPriority, AgentCapability
)

logger = logging.getLogger(__name__)


class CodeAgent(BaseAgent):
    """
    Agent für Code-Generierung und -Modifikation.
    Erstellt Tasks für file_write statt Code direkt zu schreiben.
    """
    
    def __init__(self, agent_id: str, grpc_client: GrpcClient):
        super().__init__(agent_id, "CodeAgent", grpc_client)
        self.capabilities = [
            AgentCapability.CODE_GENERATION,
            AgentCapability.CODE_MODIFICATION,
            AgentCapability.CODE_REFACTORING,
            AgentCapability.FILE_OPERATIONS
        ]
    
    async def generate_code_task(
        self,
        file_path: str,
        code_content: str,
        description: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task für Code-Generierung.
        
        Args:
            file_path: Pfad zur Datei
            code_content: Code-Inhalt
            description: Beschreibung des Tasks
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "file_path": file_path,
            "code_content": code_content,
            "operation": "write",
            "description": description
        }
        
        task_request = TaskRequest(
            task_type=TaskType.CODE_GENERATION,
            priority=priority,
            description=description,
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"Code-Generierung Task erstellt: {response.task_id}")
        return response.task_id
    
    async def modify_code_task(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
        description: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task für Code-Modifikation.
        
        Args:
            file_path: Pfad zur Datei
            old_content: Alter Code-Inhalt
            new_content: Neuer Code-Inhalt
            description: Beschreibung der Änderung
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "file_path": file_path,
            "old_content": old_content,
            "new_content": new_content,
            "operation": "modify",
            "description": description
        }
        
        task_request = TaskRequest(
            task_type=TaskType.CODE_MODIFICATION,
            priority=priority,
            description=description,
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"Code-Modifikation Task erstellt: {response.task_id}")
        return response.task_id
    
    async def refactor_code_task(
        self,
        file_path: str,
        refactoring_type: str,
        description: str,
        priority: TaskPriority = TaskPriority.LOW,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task für Code-Refactoring.
        
        Args:
            file_path: Pfad zur Datei
            refactoring_type: Art des Refactorings
            description: Beschreibung des Refactorings
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "file_path": file_path,
            "refactoring_type": refactoring_type,
            "operation": "refactor",
            "description": description
        }
        
        task_request = TaskRequest(
            task_type=TaskType.CODE_REFACTORING,
            priority=priority,
            description=description,
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"Code-Refactoring Task erstellt: {response.task_id}")
        return response.task_id
    
    async def create_file_task(
        self,
        file_path: str,
        content: str,
        description: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task zum Erstellen einer neuen Datei.
        
        Args:
            file_path: Pfad zur neuen Datei
            content: Datei-Inhalt
            description: Beschreibung der Datei
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "file_path": file_path,
            "content": content,
            "operation": "create",
            "description": description
        }
        
        task_request = TaskRequest(
            task_type=TaskType.FILE_OPERATION,
            priority=priority,
            description=description,
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"Datei-Erstellung Task erstellt: {response.task_id}")
        return response.task_id
    
    async def delete_file_task(
        self,
        file_path: str,
        description: str,
        priority: TaskPriority = TaskPriority.LOW,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Erstellt einen Task zum Löschen einer Datei.
        
        Args:
            file_path: Pfad zur Datei
            description: Beschreibung des Löschvorgangs
            priority: Priorität des Tasks
            dependencies: Liste von abhängigen Task-IDs
            
        Returns:
            Task-ID
        """
        task_data = {
            "file_path": file_path,
            "operation": "delete",
            "description": description
        }
        
        task_request = TaskRequest(
            task_type=TaskType.FILE_OPERATION,
            priority=priority,
            description=description,
            task_data=json.dumps(task_data),
            dependencies=dependencies or [],
            created_by=self.agent_id
        )
        
        response = await self.grpc_client.submit_task(task_request)
        logger.info(f"Datei-Löschung Task erstellt: {response.task_id}")
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
            if event_type == "code_generation_request":
                task_id = await self.generate_code_task(
                    file_path=event["file_path"],
                    code_content=event["code_content"],
                    description=event.get("description", "Code generieren"),
                    priority=self._parse_priority(event.get("priority", "medium"))
                )
                task_ids.append(task_id)
            
            elif event_type == "code_modification_request":
                task_id = await self.modify_code_task(
                    file_path=event["file_path"],
                    old_content=event["old_content"],
                    new_content=event["new_content"],
                    description=event.get("description", "Code modifizieren"),
                    priority=self._parse_priority(event.get("priority", "medium"))
                )
                task_ids.append(task_id)
            
            elif event_type == "file_creation_request":
                task_id = await self.create_file_task(
                    file_path=event["file_path"],
                    content=event["content"],
                    description=event.get("description", "Datei erstellen"),
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
