"""
EventFixTeam - Code Writer Agent
Schreibt Code-Tasks und sendet sie an file_write
"""

import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class CodeWriterAgent:
    """Agent für das Schreiben von Code-Tasks"""
    
    def __init__(self):
        self.agent_id = "code_writer_001"
        self.name = "Code Writer Agent"
        self.description = "Erstellt Code-Tasks und sendet sie an file_write"
        self.status = "idle"
        self.capabilities = [
            "create_code_task",
            "validate_code_task",
            "format_code_task"
        ]
        self.task_queue = []
        self.completed_tasks = []
    
    def execute_task(self, task_type: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Führe eine Aufgabe aus
        
        Args:
            task_type: Typ der Aufgabe
            parameters: Parameter für die Aufgabe
            
        Returns:
            Ergebnis der Aufgabe
        """
        self.status = "active"
        logger.info(f"CodeWriterAgent führt Task aus: {task_type}")
        
        try:
            if task_type == "create_code_task":
                result = self._create_code_task(parameters)
            elif task_type == "validate_code_task":
                result = self._validate_code_task(parameters)
            elif task_type == "format_code_task":
                result = self._format_code_task(parameters)
            else:
                raise ValueError(f"Unbekannter Task-Typ: {task_type}")
            
            self.status = "idle"
            return {
                "success": True,
                "message": f"Task {task_type} erfolgreich ausgeführt",
                "result": result
            }
        except Exception as e:
            self.status = "error"
            logger.error(f"Fehler bei Task-Ausführung: {e}")
            return {
                "success": False,
                "message": f"Fehler: {str(e)}",
                "result": {}
            }
    
    def _create_code_task(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Erstelle einen Code-Task"""
        file_path = parameters.get("file_path")
        code_content = parameters.get("code_content")
        task_id = parameters.get("task_id", f"code_task_{datetime.now().timestamp()}")
        
        if not file_path or not code_content:
            raise ValueError("file_path und code_content sind erforderlich")
        
        task = {
            "task_id": task_id,
            "type": "write_code",
            "file_path": file_path,
            "code_content": code_content,
            "created_at": datetime.now().isoformat(),
            "status": "pending"
        }
        
        self.task_queue.append(task)
        logger.info(f"Code-Task erstellt: {task_id} für {file_path}")
        
        return {
            "task_id": task_id,
            "task": task,
            "message": "Code-Task erstellt und zur Warteschlange hinzugefügt"
        }
    
    def _validate_code_task(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Validiere einen Code-Task"""
        task_id = parameters.get("task_id")
        
        if not task_id:
            raise ValueError("task_id ist erforderlich")
        
        # Suche den Task in der Warteschlange
        task = next((t for t in self.task_queue if t["task_id"] == task_id), None)
        
        if not task:
            raise ValueError(f"Task {task_id} nicht gefunden")
        
        # Validierung
        validation_result = {
            "task_id": task_id,
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        # Prüfe ob file_path vorhanden ist
        if not task.get("file_path"):
            validation_result["valid"] = False
            validation_result["errors"].append("file_path fehlt")
        
        # Prüfe ob code_content vorhanden ist
        if not task.get("code_content"):
            validation_result["valid"] = False
            validation_result["errors"].append("code_content fehlt")
        
        logger.info(f"Code-Task validiert: {task_id} - Valid: {validation_result['valid']}")
        
        return validation_result
    
    def _format_code_task(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Formatiere einen Code-Task"""
        task_id = parameters.get("task_id")
        
        if not task_id:
            raise ValueError("task_id ist erforderlich")
        
        # Suche den Task in der Warteschlange
        task = next((t for t in self.task_queue if t["task_id"] == task_id), None)
        
        if not task:
            raise ValueError(f"Task {task_id} nicht gefunden")
        
        # Formatierung (einfache Implementierung)
        code_content = task.get("code_content", "")
        formatted_code = code_content.strip()
        
        task["code_content"] = formatted_code
        task["formatted"] = True
        
        logger.info(f"Code-Task formatiert: {task_id}")
        
        return {
            "task_id": task_id,
            "formatted_code": formatted_code,
            "message": "Code-Task formatiert"
        }
    
    def get_info(self) -> Dict[str, Any]:
        """Hole Agent-Informationen"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "capabilities": self.capabilities,
            "queue_size": len(self.task_queue),
            "completed_tasks": len(self.completed_tasks)
        }
    
    def get_logs(self, task_id: str = None, lines: int = 0) -> list:
        """Hole Logs"""
        # In einer echten Implementierung würden hier echte Logs zurückgegeben
        logs = [
            {
                "timestamp": datetime.now().isoformat(),
                "level": "INFO",
                "message": f"CodeWriterAgent initialisiert"
            }
        ]
        
        if task_id:
            logs.append({
                "timestamp": datetime.now().isoformat(),
                "level": "INFO",
                "message": f"Task {task_id} verarbeitet"
            })
        
        if lines > 0:
            logs = logs[-lines:]
        
        return logs
    
    def get_metrics(self, task_id: str = None) -> list:
        """Hole Metriken"""
        metrics = [
            {
                "timestamp": datetime.now().isoformat(),
                "metric_name": "queue_size",
                "metric_value": str(len(self.task_queue))
            },
            {
                "timestamp": datetime.now().isoformat(),
                "metric_name": "completed_tasks",
                "metric_value": str(len(self.completed_tasks))
            }
        ]
        
        return metrics
