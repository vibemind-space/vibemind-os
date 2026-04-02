"""
DebugAgent für EventFixTeam
Verantwortlich für Debugging und Log-Analyse
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from .grpc_client import EventFixTeamClient

logger = logging.getLogger(__name__)


class DebugAgent:
    """
    DebugAgent für EventFixTeam
    
    Verantwortlichkeiten:
    - Debugging
    - Log-Analyse
    - Fehler-Diagnose
    - Root-Cause-Analyse
    """
    
    def __init__(self, grpc_client: EventFixTeamClient):
        """
        DebugAgent initialisieren
        
        Args:
            grpc_client: EventFixTeamClient Instanz
        """
        self.client = grpc_client
        self.agent_id = "debug_agent"
        self.agent_type = "debug"
    
    async def analyze_logs(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Logs analysieren
        
        Args:
            task: Task-Dict mit:
                - log_source: Log-Quelle (file, docker, redis, postgres)
                - log_path: Pfad zu den Logs (für file)
                - container_name: Container-Name (für docker)
                - redis_key: Redis-Key (für redis)
                - postgres_query: PostgreSQL-Query (für postgres)
                - error_pattern: Fehler-Pattern zum Suchen (optional)
                - time_range: Zeitbereich (optional)
        
        Returns:
            Dict mit success, output, logs, error
        """
        logger.info(f"DebugAgent: Analysiere Logs: {task.get('log_source', 'unknown')}")
        
        log_source = task.get("log_source", "file")
        error_pattern = task.get("error_pattern")
        time_range = task.get("time_range")
        
        # Logs abrufen
        logs = []
        
        if log_source == "file":
            log_path = task.get("log_path")
            if not log_path:
                return {
                    "success": False,
                    "error": "log_path ist erforderlich für file-Quelle",
                    "logs": []
                }
            
            read_result = await self.client.read_file(log_path)
            if not read_result["success"]:
                return read_result
            
            logs = read_result["content"].split("\n")
        
        elif log_source == "docker":
            container_name = task.get("container_name")
            if not container_name:
                return {
                    "success": False,
                    "error": "container_name ist erforderlich für docker-Quelle",
                    "logs": []
                }
            
            # Docker-Logs abrufen
            docker_result = await self.client.get_docker_logs(container_name)
            if not docker_result["success"]:
                return docker_result
            
            logs = docker_result["logs"]
        
        elif log_source == "redis":
            redis_key = task.get("redis_key")
            if not redis_key:
                return {
                    "success": False,
                    "error": "redis_key ist erforderlich für redis-Quelle",
                    "logs": []
                }
            
            # Redis-Logs abrufen
            redis_result = await self.client.get_redis_logs(redis_key)
            if not redis_result["success"]:
                return redis_result
            
            logs = redis_result["logs"]
        
        elif log_source == "postgres":
            postgres_query = task.get("postgres_query")
            if not postgres_query:
                return {
                    "success": False,
                    "error": "postgres_query ist erforderlich für postgres-Quelle",
                    "logs": []
                }
            
            # PostgreSQL-Logs abrufen
            postgres_result = await self.client.get_postgres_logs(postgres_query)
            if not postgres_result["success"]:
                return postgres_result
            
            logs = postgres_result["logs"]
        
        else:
            return {
                "success": False,
                "error": f"Unbekannte Log-Quelle: {log_source}",
                "logs": []
            }
        
        # Analyse-Task erstellen
        analysis_task = {
            "task_type": "debug",
            "debug_type": "log_analysis",
            "log_source": log_source,
            "logs": logs,
            "error_pattern": error_pattern,
            "time_range": time_range
        }
        
        # Analyse ausführen
        result = await self.client.execute_agent_task(
            agent_id=self.agent_id,
            task=analysis_task
        )
        
        logger.info(f"DebugAgent: Log-Analyse abgeschlossen")
        
        return result
    
    async def diagnose_error(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fehler diagnostizieren
        
        Args:
            task: Task-Dict mit:
                - error_message: Fehlermeldung
                - stack_trace: Stack-Trace (optional)
                - file_path: Pfad zur Datei mit dem Fehler (optional)
                - line_number: Zeilennummer (optional)
                - context_code: Kontext-Code (optional)
        
        Returns:
            Dict mit success, output, logs, error
        """
        logger.info(f"DebugAgent: Diagnostiziere Fehler: {task.get('error_message', 'unknown')}")
        
        error_message = task.get("error_message")
        stack_trace = task.get("stack_trace")
        file_path = task.get("file_path")
        line_number = task.get("line_number")
        context_code = task.get("context_code")
        
        if not error_message:
            return {
                "success": False,
                "error": "error_message ist erforderlich",
                "logs": []
            }
        
        # Kontext-Code abrufen, falls nicht bereitgestellt
        if not context_code and file_path:
            read_result = await self.client.read_file(file_path)
            if read_result["success"]:
                context_code = read_result["content"]
        
        # Diagnose-Task erstellen
        diagnosis_task = {
            "task_type": "debug",
            "debug_type": "error_diagnosis",
            "error_message": error_message,
            "stack_trace": stack_trace,
            "file_path": file_path,
            "line_number": line_number,
            "context_code": context_code
        }
        
        # Diagnose ausführen
        result = await self.client.execute_agent_task(
            agent_id=self.agent_id,
            task=diagnosis_task
        )
        
        logger.info(f"DebugAgent: Fehler-Diagnose abgeschlossen")
        
        return result
    
    async def analyze_root_cause(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Root-Cause-Analyse durchführen
        
        Args:
            task: Task-Dict mit:
                - issue_description: Beschreibung des Problems
                - symptoms: Symptome (Liste)
                - affected_components: Betroffene Komponenten (Liste)
                - logs: Logs (optional)
                - metrics: Metriken (optional)
        
        Returns:
            Dict mit success, output, logs, error
        """
        logger.info(f"DebugAgent: Analysiere Root-Cause: {task.get('issue_description', 'unknown')}")
        
        issue_description = task.get("issue_description")
        symptoms = task.get("symptoms", [])
        affected_components = task.get("affected_components", [])
        logs = task.get("logs", [])
        metrics = task.get("metrics", {})
        
        if not issue_description:
            return {
                "success": False,
                "error": "issue_description ist erforderlich",
                "logs": []
            }
        
        # Root-Cause-Task erstellen
        root_cause_task = {
            "task_type": "debug",
            "debug_type": "root_cause_analysis",
            "issue_description": issue_description,
            "symptoms": symptoms,
            "affected_components": affected_components,
            "logs": logs,
            "metrics": metrics
        }
        
        # Root-Cause-Analyse ausführen
        result = await self.client.execute_agent_task(
            agent_id=self.agent_id,
            task=root_cause_task
        )
        
        logger.info(f"DebugAgent: Root-Cause-Analyse abgeschlossen")
        
        return result
    
    async def trace_execution(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ausführung trace
        
        Args:
            task: Task-Dict mit:
                - file_path: Pfad zur Datei
                - function_name: Funktionsname (optional)
                - line_number: Start-Zeile (optional)
                - trace_depth: Trace-Tiefe (optional)
        
        Returns:
            Dict mit success, output, logs, error
        """
        logger.info(f"DebugAgent: Trace Ausführung: {task.get('file_path', 'unknown')}")
        
        file_path = task.get("file_path")
        function_name = task.get("function_name")
        line_number = task.get("line_number")
        trace_depth = task.get("trace_depth", 10)
        
        if not file_path:
            return {
                "success": False,
                "error": "file_path ist erforderlich",
                "logs": []
            }
        
        # Datei lesen
        read_result = await self.client.read_file(file_path)
        if not read_result["success"]:
            return read_result
        
        code = read_result["content"]
        
        # Trace-Task erstellen
        trace_task = {
            "task_type": "debug",
            "debug_type": "execution_trace",
            "file_path": file_path,
            "function_name": function_name,
            "line_number": line_number,
            "trace_depth": trace_depth,
            "code": code
        }
        
        # Trace ausführen
        result = await self.client.execute_agent_task(
            agent_id=self.agent_id,
            task=trace_task
        )
        
        logger.info(f"DebugAgent: Ausführungs-Trace abgeschlossen")
        
        return result
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Task ausführen
        
        Args:
            task: Task-Dict mit:
                - task_type: Art des Tasks (log_analysis, error_diagnosis, root_cause, execution_trace)
                - ... weitere Parameter je nach Task-Typ
        
        Returns:
            Dict mit success, output, logs, error
        """
        task_type = task.get("task_type", "log_analysis")
        
        logger.info(f"DebugAgent: Führe Task aus: {task_type}")
        
        try:
            if task_type == "log_analysis":
                return await self.analyze_logs(task)
            elif task_type == "error_diagnosis":
                return await self.diagnose_error(task)
            elif task_type == "root_cause":
                return await self.analyze_root_cause(task)
            elif task_type == "execution_trace":
                return await self.trace_execution(task)
            else:
                return {
                    "success": False,
                    "error": f"Unbekannter Task-Typ: {task_type}",
                    "logs": []
                }
        except Exception as e:
            logger.error(f"DebugAgent: Fehler bei Task-Ausführung: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": []
            }
