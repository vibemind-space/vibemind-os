"""
AgentManager für EventFixTeam
Verwaltet und koordiniert alle Agents
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from .grpc_client import EventFixTeamClient
from .agents.code_agent import CodeAgent
from .agents.debug_agent import DebugAgent
from .agents.test_agent import TestAgent

logger = logging.getLogger(__name__)


class AgentManager:
    """
    AgentManager für EventFixTeam
    
    Verantwortlichkeiten:
    - Agents initialisieren und verwalten
    - Tasks an die richtigen Agents verteilen
    - Agent-Koordination
    - Task-Status überwachen
    """
    
    def __init__(self, grpc_client: EventFixTeamClient):
        """
        AgentManager initialisieren
        
        Args:
            grpc_client: EventFixTeamClient Instanz
        """
        self.client = grpc_client
        self.agents: Dict[str, Any] = {}
        self._initialize_agents()
    
    def _initialize_agents(self):
        """Alle Agents initialisieren"""
        logger.info("AgentManager: Initialisiere Agents...")
        
        # CodeAgent initialisieren
        self.agents["code"] = CodeAgent(self.client)
        logger.info("AgentManager: CodeAgent initialisiert")
        
        # DebugAgent initialisieren
        self.agents["debug"] = DebugAgent(self.client)
        logger.info("AgentManager: DebugAgent initialisiert")
        
        # TestAgent initialisieren
        self.agents["test"] = TestAgent(self.client)
        logger.info("AgentManager: TestAgent initialisiert")
        
        logger.info(f"AgentManager: {len(self.agents)} Agents initialisiert")
    
    def get_agent(self, agent_type: str) -> Optional[Any]:
        """
        Agent nach Typ abrufen
        
        Args:
            agent_type: Typ des Agents (code, debug, test)
        
        Returns:
            Agent-Instanz oder None
        """
        return self.agents.get(agent_type)
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Task an den passenden Agent weiterleiten
        
        Args:
            task: Task-Dict mit:
                - agent_type: Typ des Agents (code, debug, test)
                - task_type: Art des Tasks
                - ... weitere Parameter je nach Task-Typ
        
        Returns:
            Dict mit success, output, logs, error
        """
        agent_type = task.get("agent_type")
        
        if not agent_type:
            return {
                "success": False,
                "error": "agent_type ist erforderlich",
                "logs": []
            }
        
        agent = self.get_agent(agent_type)
        if not agent:
            return {
                "success": False,
                "error": f"Unbekannter Agent-Typ: {agent_type}",
                "logs": []
            }
        
        logger.info(f"AgentManager: Leite Task an {agent_type}-Agent weiter")
        
        try:
            result = await agent.execute_task(task)
            logger.info(f"AgentManager: Task von {agent_type}-Agent abgeschlossen")
            return result
        except Exception as e:
            logger.error(f"AgentManager: Fehler bei Task-Ausführung: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": []
            }
    
    async def execute_workflow(self, workflow: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Workflow mit mehreren Tasks ausführen
        
        Args:
            workflow: Liste von Tasks
        
        Returns:
            Dict mit success, results, logs, error
        """
        logger.info(f"AgentManager: Führe Workflow mit {len(workflow)} Tasks aus")
        
        results = []
        logs = []
        all_success = True
        
        for i, task in enumerate(workflow):
            logger.info(f"AgentManager: Führe Task {i+1}/{len(workflow)} aus")
            
            result = await self.execute_task(task)
            results.append(result)
            
            if result.get("logs"):
                logs.extend(result["logs"])
            
            if not result.get("success"):
                all_success = False
                logger.error(f"AgentManager: Task {i+1} fehlgeschlagen: {result.get('error')}")
                # Workflow abbrechen bei Fehler
                break
        
        logger.info(f"AgentManager: Workflow abgeschlossen: {'Erfolg' if all_success else 'Fehlgeschlagen'}")
        
        return {
            "success": all_success,
            "results": results,
            "logs": logs,
            "error": None if all_success else "Ein oder mehrere Tasks sind fehlgeschlagen"
        }
    
    async def get_agent_status(self) -> Dict[str, Any]:
        """
        Status aller Agents abrufen
        
        Returns:
            Dict mit Agent-Status
        """
        status = {}
        
        for agent_type, agent in self.agents.items():
            status[agent_type] = {
                "type": agent_type,
                "agent_id": agent.agent_id,
                "initialized": True
            }
        
        return {
            "success": True,
            "agents": status,
            "total_agents": len(self.agents)
        }
