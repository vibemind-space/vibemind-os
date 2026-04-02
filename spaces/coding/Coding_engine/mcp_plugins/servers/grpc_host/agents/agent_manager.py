"""
Agent Manager - Verwaltung aller spezialisierten Agents

Der Agent Manager koordiniert die Kommunikation mit verschiedenen spezialisierten Agents
über gRPC und verwaltet Workflows, Tasks und parallele Ausführungen.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path

from agents.grpc_client import GrpcClient
from agents.workflow_engine import WorkflowEngine

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AgentManager:
    """Verwaltung aller spezialisierten Agents"""
    
    def __init__(self):
        self.agents: Dict[str, GrpcClient] = {}
        self.workflow_engine = WorkflowEngine()
        self.workflow_templates: Dict[str, Dict] = {}
        self._initialized = False
        
        # Agent-Konfigurationen
        self.agent_configs = {
            "file_write": {
                "host": "localhost",
                "port": 50051,
                "description": "Code-Schreiben und Datei-Operationen"
            },
            "docker": {
                "host": "localhost",
                "port": 50052,
                "description": "Container-Management und Docker-Operationen"
            },
            "redis": {
                "host": "localhost",
                "port": 50053,
                "description": "Cache-Management und Redis-Operationen"
            },
            "postgres": {
                "host": "localhost",
                "port": 50054,
                "description": "Datenbank-Operationen und PostgreSQL"
            },
            "playwright": {
                "host": "localhost",
                "port": 50055,
                "description": "E2E-Testing und Playwright-Tests"
            }
        }
    
    async def initialize(self):
        """Initialisiert alle Agents"""
        if self._initialized:
            return
        
        logger.info("Initialisiere Agent Manager...")
        
        # Alle Agents initialisieren
        for agent_type, config in self.agent_configs.items():
            try:
                client = GrpcClient(
                    host=config["host"],
                    port=config["port"],
                    agent_type=agent_type
                )
                await client.connect()
                self.agents[agent_type] = client
                logger.info(f"Agent {agent_type} initialisiert")
            except Exception as e:
                logger.warning(f"Konnte Agent {agent_type} nicht initialisieren: {e}")
        
        # Workflow Engine initialisieren
        await self.workflow_engine.initialize(self.agents)
        
        # Workflow-Templates laden
        await self._load_workflow_templates()
        
        self._initialized = True
        logger.info("Agent Manager initialisiert")
    
    async def get_agent_status(self) -> Dict[str, Any]:
        """Gibt den Status aller Agents zurück"""
        status = {
            "timestamp": datetime.now().isoformat(),
            "agents": {}
        }
        
        for agent_type, client in self.agents.items():
            try:
                agent_status = await client.get_status()
                status["agents"][agent_type] = {
                    "connected": True,
                    "status": agent_status,
                    "config": self.agent_configs[agent_type]
                }
            except Exception as e:
                status["agents"][agent_type] = {
                    "connected": False,
                    "error": str(e),
                    "config": self.agent_configs[agent_type]
                }
        
        return status
    
    async def execute_task(
        self,
        agent_type: str,
        task: str,
        parameters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Führt einen Task auf einem spezifischen Agent aus"""
        if agent_type not in self.agents:
            raise ValueError(f"Unbekannter Agent-Typ: {agent_type}")
        
        client = self.agents[agent_type]
        
        logger.info(f"Führe Task auf {agent_type}: {task}")
        
        result = await client.execute_task(task, parameters or {})
        
        return {
            "agent_type": agent_type,
            "task": task,
            "status": "success",
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    
    async def execute_parallel_tasks(
        self,
        tasks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Führt mehrere Tasks parallel auf verschiedenen Agents aus"""
        logger.info(f"Führe {len(tasks)} Tasks parallel aus")
        
        # Tasks erstellen
        async_tasks = []
        for task_info in tasks:
            agent_type = task_info.get("agent_type")
            task = task_info.get("task")
            parameters = task_info.get("parameters", {})
            
            async_tasks.append(
                self.execute_task(agent_type, task, parameters)
            )
        
        # Parallel ausführen
        results = await asyncio.gather(*async_tasks, return_exceptions=True)
        
        # Ergebnisse formatieren
        formatted_results = {
            "total_tasks": len(tasks),
            "successful": 0,
            "failed": 0,
            "results": []
        }
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                formatted_results["failed"] += 1
                formatted_results["results"].append({
                    "task": tasks[i],
                    "status": "error",
                    "error": str(result)
                })
            else:
                formatted_results["successful"] += 1
                formatted_results["results"].append(result)
        
        return formatted_results
    
    async def execute_workflow(
        self,
        workflow_name: str,
        steps: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Führt einen Workflow mit mehreren Agents aus"""
        logger.info(f"Führe Workflow '{workflow_name}' mit {len(steps)} Schritten aus")
        
        result = await self.workflow_engine.execute_workflow(workflow_name, steps)
        
        return result
    
    async def health_check(self) -> Dict[str, Any]:
        """Führt einen Health Check für alle Agents durch"""
        health_status = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "agents": {}
        }
        
        all_healthy = True
        
        for agent_type, client in self.agents.items():
            try:
                is_healthy = await client.health_check()
                health_status["agents"][agent_type] = {
                    "healthy": is_healthy,
                    "status": "ok" if is_healthy else "unhealthy"
                }
                
                if not is_healthy:
                    all_healthy = False
            except Exception as e:
                health_status["agents"][agent_type] = {
                    "healthy": False,
                    "status": "error",
                    "error": str(e)
                }
                all_healthy = False
        
        health_status["overall_status"] = "healthy" if all_healthy else "unhealthy"
        
        return health_status
    
    async def get_agent_logs(
        self,
        agent_type: str,
        lines: int = 100
    ) -> Dict[str, Any]:
        """Ruft Logs von einem spezifischen Agent ab"""
        if agent_type not in self.agents:
            raise ValueError(f"Unbekannter Agent-Typ: {agent_type}")
        
        client = self.agents[agent_type]
        
        logs = await client.get_logs(lines)
        
        return {
            "agent_type": agent_type,
            "logs": logs,
            "timestamp": datetime.now().isoformat()
        }
    
    async def restart_agent(self, agent_type: str) -> Dict[str, Any]:
        """Startet einen Agent neu"""
        if agent_type not in self.agents:
            raise ValueError(f"Unbekannter Agent-Typ: {agent_type}")
        
        client = self.agents[agent_type]
        
        logger.info(f"Starte Agent {agent_type} neu")
        
        result = await client.restart()
        
        return {
            "agent_type": agent_type,
            "status": "restarted",
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    
    async def scale_agent(
        self,
        agent_type: str,
        instances: int
    ) -> Dict[str, Any]:
        """Skaliert die Anzahl der Instanzen eines Agents"""
        if agent_type not in self.agents:
            raise ValueError(f"Unbekannter Agent-Typ: {agent_type}")
        
        client = self.agents[agent_type]
        
        logger.info(f"Skaliere Agent {agent_type} auf {instances} Instanzen")
        
        result = await client.scale(instances)
        
        return {
            "agent_type": agent_type,
            "instances": instances,
            "status": "scaled",
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    
    async def get_agent_metrics(self, agent_type: str) -> Dict[str, Any]:
        """Ruft Metriken von einem Agent ab"""
        if agent_type not in self.agents:
            raise ValueError(f"Unbekannter Agent-Typ: {agent_type}")
        
        client = self.agents[agent_type]
        
        metrics = await client.get_metrics()
        
        return {
            "agent_type": agent_type,
            "metrics": metrics,
            "timestamp": datetime.now().isoformat()
        }
    
    async def create_workflow_template(
        self,
        template_name: str,
        description: str,
        steps: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Erstellt ein Workflow-Template"""
        self.workflow_templates[template_name] = {
            "description": description,
            "steps": steps,
            "created_at": datetime.now().isoformat()
        }
        
        # Template speichern
        await self._save_workflow_templates()
        
        logger.info(f"Workflow-Template '{template_name}' erstellt")
        
        return {
            "template_name": template_name,
            "status": "created",
            "description": description,
            "steps_count": len(steps)
        }
    
    async def list_workflow_templates(self) -> Dict[str, Any]:
        """Listet alle Workflow-Templates auf"""
        return {
            "templates": self.workflow_templates,
            "count": len(self.workflow_templates)
        }
    
    async def execute_workflow_template(
        self,
        template_name: str,
        parameters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Führt ein Workflow-Template aus"""
        if template_name not in self.workflow_templates:
            raise ValueError(f"Unbekanntes Template: {template_name}")
        
        template = self.workflow_templates[template_name]
        steps = template["steps"]
        
        # Parameter in Steps einfügen
        if parameters:
            for step in steps:
                if "parameters" in step:
                    step["parameters"].update(parameters)
        
        logger.info(f"Führe Workflow-Template '{template_name}' aus")
        
        result = await self.execute_workflow(template_name, steps)
        
        return result
    
    async def _load_workflow_templates(self):
        """Lädt Workflow-Templates aus Datei"""
        template_file = Path(__file__).parent / "workflow_templates.json"
        
        if template_file.exists():
            try:
                with open(template_file, "r", encoding="utf-8") as f:
                    self.workflow_templates = json.load(f)
                logger.info(f"{len(self.workflow_templates)} Workflow-Templates geladen")
            except Exception as e:
                logger.warning(f"Konnte Workflow-Templates nicht laden: {e}")
    
    async def _save_workflow_templates(self):
        """Speichert Workflow-Templates in Datei"""
        template_file = Path(__file__).parent / "workflow_templates.json"
        
        try:
            with open(template_file, "w", encoding="utf-8") as f:
                json.dump(self.workflow_templates, f, indent=2, ensure_ascii=False)
            logger.info("Workflow-Templates gespeichert")
        except Exception as e:
            logger.error(f"Konnte Workflow-Templates nicht speichern: {e}")
    
    async def shutdown(self):
        """Fährt alle Agents herunter"""
        logger.info("Fahre Agent Manager herunter...")
        
        for agent_type, client in self.agents.items():
            try:
                await client.close()
                logger.info(f"Agent {agent_type} heruntergefahren")
            except Exception as e:
                logger.error(f"Fehler beim Herunterfahren von {agent_type}: {e}")
        
        self._initialized = False
