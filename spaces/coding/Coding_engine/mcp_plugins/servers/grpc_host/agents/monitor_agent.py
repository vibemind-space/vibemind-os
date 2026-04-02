"""
MonitorAgent - Spezialisiert für das Monitoring von Fixes
Erstellt Tasks zum Monitoring von Fixes
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
import subprocess
import re
import shutil

logger = logging.getLogger(__name__)


class MonitorAgent:
    """Agent für das Monitoring von Fixes"""
    
    def __init__(self, base_dir: str = "."):
        """
        MonitorAgent initialisieren
        
        Args:
            base_dir: Basisverzeichnis für das Projekt
        """
        self.base_dir = Path(base_dir)
        self.monitor_dir = self.base_dir / ".monitor"
        self.monitor_dir.mkdir(exist_ok=True)
        self.monitor_tasks_dir = self.monitor_dir / "tasks"
        self.monitor_tasks_dir.mkdir(exist_ok=True)
        self.monitor_results_dir = self.monitor_dir / "results"
        self.monitor_results_dir.mkdir(exist_ok=True)
        self.monitor_reports_dir = self.monitor_dir / "reports"
        self.monitor_reports_dir.mkdir(exist_ok=True)
        self.monitor_templates_dir = self.monitor_dir / "templates"
        self.monitor_templates_dir.mkdir(exist_ok=True)
        self.monitor_snippets_dir = self.monitor_dir / "snippets"
        self.monitor_snippets_dir.mkdir(exist_ok=True)
        self.monitor_files_dir = self.monitor_dir / "files"
        self.monitor_files_dir.mkdir(exist_ok=True)
        self.monitor_archives_dir = self.monitor_dir / "archives"
        self.monitor_archives_dir.mkdir(exist_ok=True)
        self.monitor_configs_dir = self.monitor_dir / "configs"
        self.monitor_configs_dir.mkdir(exist_ok=True)
        self.monitor_logs_dir = self.monitor_dir / "logs"
        self.monitor_logs_dir.mkdir(exist_ok=True)
        logger.info(f"MonitorAgent initialisiert mit Basisverzeichnis: {base_dir}")
    
    def create_monitor_task(self, task_name: str,
                           description: str,
                           monitor_type: str,
                           monitor_config: Dict[str, Any],
                           priority: str = "high",
                           context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Monitor-Task erstellen
        
        Args:
            task_name: Name der Task
            description: Beschreibung der Task
            monitor_type: Monitor-Typ (performance, error, health, custom)
            monitor_config: Konfiguration des Monitorings
            priority: Priorität (low, medium, high, critical)
            context: Zusätzlicher Kontext
        
        Returns:
            Dictionary mit der erstellten Monitor-Task
        """
        try:
            task_id = f"monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            task = {
                "task_id": task_id,
                "type": "monitor",
                "task_name": task_name,
                "description": description,
                "monitor_type": monitor_type,
                "monitor_config": monitor_config,
                "priority": priority,
                "context": context or {},
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            # Task speichern
            task_file = self.monitor_tasks_dir / f"{task_id}.json"
            with open(task_file, 'w', encoding='utf-8') as f:
                json.dump(task, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Monitor-Task erstellt: {task_id}")
            
            return {
                "success": True,
                "task": task
            }
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Monitor-Task: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def create_performance_monitor_task(self, task_name: str,
                                       description: str,
                                       performance_monitor_config: Dict[str, Any],
                                       priority: str = "high",
                                       context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Performance-Monitor-Task erstellen
        
        Args:
            task_name: Name der Task
            description: Beschreibung der Task
            performance_monitor_config: Konfiguration des Performance-Monitorings
            priority: Priorität (low, medium, high, critical)
            context: Zusätzlicher Kontext
        
        Returns:
            Dictionary mit der erstellten Performance-Monitor-Task
        """
        try:
            task_id = f"performance_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            task = {
                "task_id": task_id,
                "type": "performance_monitor",
                "task_name": task_name,
                "description": description,
                "performance_monitor_config": performance_monitor_config,
                "priority": priority,
                "context": context or {},
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            # Task speichern
            task_file = self.monitor_tasks_dir / f"{task_id}.json"
            with open(task_file, 'w', encoding='utf-8') as f:
                json.dump(task, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Performance-Monitor-Task erstellt: {task_id}")
            
            return {
                "success": True,
                "task": task
            }
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Performance-Monitor-Task: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def create_error_monitor_task(self, task_name: str,
                                 description: str,
                                 error_monitor_config: Dict[str, Any],
                                 priority: str = "high",
                                 context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Error-Monitor-Task erstellen
        
        Args:
            task_name: Name der Task
            description: Beschreibung der Task
            error_monitor_config: Konfiguration des Error-Monitorings
            priority: Priorität (low, medium, high, critical)
            context: Zusätzlicher Kontext
        
        Returns:
            Dictionary mit der erstellten Error-Monitor-Task
        """
        try:
            task_id = f"error_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            task = {
                "task_id": task_id,
                "type": "error_monitor",
                "task_name": task_name,
                "description": description,
                "error_monitor_config": error_monitor_config,
                "priority": priority,
                "context": context or {},
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            # Task speichern
            task_file = self.monitor_tasks_dir / f"{task_id}.json"
            with open(task_file, 'w', encoding='utf-8') as f:
                json.dump(task, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Error-Monitor-Task erstellt: {task_id}")
            
            return {
                "success": True,
                "task": task
            }
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Error-Monitor-Task: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def create_health_monitor_task(self, task_name: str,
                                  description: str,
                                  health_monitor_config: Dict[str, Any],
                                  priority: str = "high",
                                  context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Health-Monitor-Task erstellen
        
        Args:
            task_name: Name der Task
            description: Beschreibung der Task
            health_monitor_config: Konfiguration des Health-Monitorings
            priority: Priorität (low, medium, high, critical)
            context: Zusätzlicher Kontext
        
        Returns:
            Dictionary mit der erstellten Health-Monitor-Task
        """
        try:
            task_id = f"health_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            task = {
                "task_id": task_id,
                "type": "health_monitor",
                "task_name": task_name,
                "description": description,
                "health_monitor_config": health_monitor_config,
                "priority": priority,
                "context": context or {},
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            # Task speichern
            task_file = self.monitor_tasks_dir / f"{task_id}.json"
            with open(task_file, 'w', encoding='utf-8') as f:
                json.dump(task, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Health-Monitor-Task erstellt: {task_id}")
            
            return {
                "success": True,
                "task": task
            }
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Health-Monitor-Task: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def create_custom_monitor_task(self, task_name: str,
                                  description: str,
                                  custom_monitor_config: Dict[str, Any],
                                  priority: str = "high",
                                  context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Custom-Monitor-Task erstellen
        
        Args:
            task_name: Name der Task
            description: Beschreibung der Task
            custom_monitor_config: Konfiguration des Custom-Monitorings
            priority: Priorität (low, medium, high, critical)
            context: Zusätzlicher Kontext
        
        Returns:
            Dictionary mit der erstellten Custom-Monitor-Task
        """
        try:
            task_id = f"custom_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            task = {
                "task_id": task_id,
                "type": "custom_monitor",
                "task_name": task_name,
                "description": description,
                "custom_monitor_config": custom_monitor_config,
                "priority": priority,
                "context": context or {},
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            # Task speichern
            task_file = self.monitor_tasks_dir / f"{task_id}.json"
            with open(task_file, 'w', encoding='utf-8') as f:
                json.dump(task, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Custom-Monitor-Task erstellt: {task_id}")
            
            return {
                "success": True,
                "task": task
            }
        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Custom-Monitor-Task: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def execute_monitor_task(self, task_id: str) -> Dict[str, Any]:
        """
        Monitor-Task ausführen
        
        Args:
            task_id: ID der Task
        
        Returns:
            Dictionary mit dem Ergebnis
        """
        try:
            # Task abrufen
            task_result = self.get_task(task_id)
            
            if not task_result["success"]:
                return task_result
            
            task = task_result["task"]
            
            # Status aktualisieren
            self.update_task_status(task_id, "in_progress", "Monitor-Task wird ausgeführt")
            
            monitor_type = task.get("monitor_type", "performance")
            monitor_config = task.get("monitor_config", {})
            
            # Monitoring durchführen
            monitor_result = self._perform_monitor(monitor_type, monitor_config)
            
            if not monitor_result["success"]:
                self.update_task_status(task_id, "failed", f"Monitoring fehlgeschlagen: {monitor_result.get('error', 'Unknown')}")
                return {
                    "success": False,
                    "error": monitor_result.get("error", "Unknown")
                }
            
            # Monitor-Ergebnis speichern
            monitor_result_data = {
                "task_id": task_id,
                "monitor_type": monitor_type,
                "monitor_config": monitor_config,
                "result": monitor_result,
                "executed_at": datetime.now().isoformat()
            }
            
            monitor_result_file = self.monitor_results_dir / f"{task_id}_result.json"
            with open(monitor_result_file, 'w', encoding='utf-8') as f:
                json.dump(monitor_result_data, f, indent=2, ensure_ascii=False)
            
            # Monitor-Report erstellen
            report_file = self._create_monitor_report(task_id, monitor_result_data)
            
            # Status aktualisieren
            self.update_task_status(task_id, "completed", "Monitor-Task erfolgreich ausgeführt", monitor_result_data)
            
            logger.info(f"Monitor-Task ausgeführt: {task_id}")
            
            return {
                "success": True,
                "monitor_result": monitor_result_data,
                "monitor_result_file": str(monitor_result_file),
                "report_file": str(report_file)
            }
        except Exception as e:
            logger.error(f"Fehler beim Ausführen der Monitor-Task: {e}")
            
            # Status aktualisieren
            self.update_task_status(task_id, "failed", f"Fehler beim Ausführen: {str(e)}")
            
            return {
                "success": False,
                "error": str(e)
            }
    
    def execute_performance_monitor_task(self, task_id: str) -> Dict[str, Any]:
        """
        Performance-Monitor-Task ausführen
        
        Args:
            task_id: ID der Task
        
        Returns:
            Dictionary mit dem Ergebnis
        """
        try:
            # Task abrufen
            task_result = self.get_task(task_id)
            
            if not task_result["success"]:
                return task_result
            
            task = task_result["task"]
            
            # Status aktualisieren
            self.update_task_status(task_id, "in_progress", "Performance-Monitor-Task wird ausgeführt")
            
            performance_monitor_config = task.get("performance_monitor_config", {})
            
            # Performance-Monitoring durchführen
            performance_monitor_result = self._perform_performance_monitor(performance_monitor_config)
            
            if not performance_monitor_result["success"]:
                self.update_task_status(task_id, "failed", f"Performance-Monitoring fehlgeschlagen: {performance_monitor_result.get('error', 'Unknown')}")
                return {
                    "success": False,
                    "error": performance_monitor_result.get("error", "Unknown")
                }
            
            # Performance-Monitor-Ergebnis speichern
            performance_monitor_result_data = {
                "task_id": task_id,
                "performance_monitor_config": performance_monitor_config,
                "result": performance_monitor_result,
                "executed_at": datetime.now().isoformat()
            }
            
            performance_monitor_result_file = self.monitor_results_dir / f"{task_id}_result.json"
            with open(performance_monitor_result_file, 'w', encoding='utf-8') as f:
                json.dump(performance_monitor_result_data, f, indent=2, ensure_ascii=False)
            
            # Performance-Monitor-Report erstellen
            report_file = self._create_monitor_report(task_id, performance_monitor_result_data)
            
            # Status aktualisieren
            self.update_task_status(task_id, "completed", "Performance-Monitor-Task erfolgreich ausgeführt", performance_monitor_result_data)
            
            logger.info(f"Performance-Monitor-Task ausgeführt: {task_id}")
            
            return {
                "success": True,
                "performance_monitor_result": performance_monitor_result_data,
                "performance_monitor_result_file": str(performance_monitor_result_file),
                "report_file": str(report_file)
            }
        except Exception as e:
            logger.error(f"Fehler beim Ausführen der Performance-Monitor-Task: {e}")
            
            # Status aktualisieren
            self.update_task_status(task_id, "failed", f"Fehler beim Ausführen: {str(e)}")
            
            return {
                "success": False,
                "error": str(e)
            }
    
    def execute_error_monitor_task(self, task_id: str) -> Dict[str, Any]:
        """
        Error-Monitor-Task ausführen
        
        Args:
            task_id: ID der Task
        
        Returns:
            Dictionary mit dem Ergebnis
        """
        try:
            # Task abrufen
            task_result = self.get_task(task_id)
            
            if not task_result["success"]:
                return task_result
            
            task = task_result["task"]
            
            # Status aktualisieren
            self.update_task_status(task_id, "in_progress", "Error-Monitor-Task wird ausgeführt")
            
            error_monitor_config = task.get("error_monitor_config", {})
            
            # Error-Monitoring durchführen
            error_monitor_result = self._perform_error_monitor(error_monitor_config)
            
            if not error_monitor_result["success"]:
                self.update_task_status(task_id, "failed", f"Error-Monitoring fehlgeschlagen: {error_monitor_result.get('error', 'Unknown')}")
                return {
                    "success": False,
                    "error": error_monitor_result.get("error", "Unknown")
                }
            
            # Error-Monitor-Ergebnis speichern
            error_monitor_result_data = {
                "task_id": task_id,
                "error_monitor_config": error_monitor_config,
                "result": error_monitor_result,
                "executed_at": datetime.now().isoformat()
            }
            
            error_monitor_result_file = self.monitor_results_dir / f"{task_id}_result.json"
            with open(error_monitor_result_file, 'w', encoding='utf-8') as f:
                json.dump(error_monitor_result_data, f, indent=2, ensure_ascii=False)
            
            # Error-Monitor-Report erstellen
            report_file = self._create_monitor_report(task_id, error_monitor_result_data)
            
            # Status aktualisieren
            self.update_task_status(task_id, "completed", "Error-Monitor-Task erfolgreich ausgeführt", error_monitor_result_data)
            
            logger.info(f"Error-Monitor-Task ausgeführt: {task_id}")
            
            return {
                "success": True,
                "error_monitor_result": error_monitor_result_data,
                "error_monitor_result_file": str(error_monitor_result_file),
                "report_file": str(report_file)
            }
        except Exception as e:
            logger.error(f"Fehler beim Ausführen der Error-Monitor-Task: {e}")
            
            # Status aktualisieren
            self.update_task_status(task_id, "failed", f"Fehler beim Ausführen: {str(e)}")
            
            return {
                "success": False,
                "error": str(e)
            }
    
    def execute_health_monitor_task(self, task_id: str) -> Dict[str, Any]:
        """
        Health-Monitor-Task ausführen
        
        Args:
            task_id: ID der Task
        
        Returns:
            Dictionary mit dem Ergebnis
        """
        try:
            # Task abrufen
            task_result = self.get_task(task_id)
            
            if not task_result["success"]:
                return task_result
            
            task = task_result["task"]
            
            # Status aktualisieren
            self.update_task_status(task_id, "in_progress", "Health-Monitor-Task wird ausgeführt")
            
            health_monitor_config = task.get("health_monitor_config", {})
            
            # Health-Monitoring durchführen
            health_monitor_result = self._perform_health_monitor(health_monitor_config)
            
            if not health_monitor_result["success"]:
                self.update_task_status(task_id, "failed", f"Health-Monitoring fehlgeschlagen: {health_monitor_result.get('error', 'Unknown')}")
                return {
                    "success": False,
                    "error": health_monitor_result.get("error", "Unknown")
                }
            
            # Health-Monitor-Ergebnis speichern
            health_monitor_result_data = {
                "task_id": task_id,
                "health_monitor_config": health_monitor_config,
                "result": health_monitor_result,
                "executed_at": datetime.now().isoformat()
            }
            
            health_monitor_result_file = self.monitor_results_dir / f"{task_id}_result.json"
            with open(health_monitor_result_file, 'w', encoding='utf-8') as f:
                json.dump(health_monitor_result_data, f, indent=2, ensure_ascii=False)
            
            # Health-Monitor-Report erstellen
            report_file = self._create_monitor_report(task_id, health_monitor_result_data)
            
            # Status aktualisieren
            self.update_task_status(task_id, "completed", "Health-Monitor-Task erfolgreich ausgeführt", health_monitor_result_data)
            
            logger.info(f"Health-Monitor-Task ausgeführt: {task_id}")
            
            return {
                "success": True,
                "health_monitor_result": health_monitor_result_data,
                "health_monitor_result_file": str(health_monitor_result_file),
                "report_file": str(report_file)
            }
        except Exception as e:
            logger.error(f"Fehler beim Ausführen der Health-Monitor-Task: {e}")
            
            # Status aktualisieren
            self.update_task_status(task_id, "failed", f"Fehler beim Ausführen: {str(e)}")
            
            return {
                "success": False,
                "error": str(e)
            }
    
    def execute_custom_monitor_task(self, task_id: str) -> Dict[str, Any]:
        """
        Custom-Monitor-Task ausführen
        
        Args:
            task_id: ID der Task
        
        Returns:
            Dictionary mit dem Ergebnis
        """
        try:
            # Task abrufen
            task_result = self.get_task(task_id)
            
            if not task_result["success"]:
                return task_result
            
            task = task_result["task"]
            
            # Status aktualisieren
            self.update_task_status(task_id, "in_progress", "Custom-Monitor-Task wird ausgeführt")
            
            custom_monitor_config = task.get("custom_monitor_config", {})
            
            # Custom-Monitoring durchführen
            custom_monitor_result = self._perform_custom_monitor(custom_monitor_config)
            
            if not custom_monitor_result["success"]:
                self.update_task_status(task_id, "failed", f"Custom-Monitoring fehlgeschlagen: {custom_monitor_result.get('error', 'Unknown')}")
                return {
                    "success": False,
                    "error": custom_monitor_result.get("error", "Unknown")
                }
            
            # Custom-Monitor-Ergebnis speichern
            custom_monitor_result_data = {
                "task_id": task_id,
                "custom_monitor_config": custom_monitor_config,
                "result": custom_monitor_result,
                "executed_at": datetime.now().isoformat()
            }
            
            custom_monitor_result_file = self.monitor_results_dir / f"{task_id}_result.json"
            with open(custom_monitor_result_file, 'w', encoding='utf-8') as f:
                json.dump(custom_monitor_result_data, f, indent=2, ensure_ascii=False)
            
            # Custom-Monitor-Report erstellen
            report_file = self._create_monitor_report(task_id, custom_monitor_result_data)
            
            # Status aktualisieren
            self.update_task_status(task_id, "completed", "Custom-Monitor-Task erfolgreich ausgeführt", custom_monitor_result_data)
            
            logger.info(f"Custom-Monitor-Task ausgeführt: {task_id}")
            
            return {
                "success": True,
                "custom_monitor_result": custom_monitor_result_data,
                "custom_monitor_result_file": str(custom_monitor_result_file),
                "report_file": str(report_file)
            }
        except Exception as e:
            logger.error(f"Fehler beim Ausführen der Custom-Monitor-Task: {e}")
            
            # Status aktualisieren
            self.update_task_status(task_id, "failed", f"Fehler beim Ausführen: {str(e)}")
            
            return {
                "success": False,
                "error": str(e)
            }
    
    def _perform_monitor(self, monitor_type: str, monitor_config: Dict[str, Any]) -> Dict[str, Any]:
        """Monitoring durchführen"""
        try:
            if monitor_type == "performance":
                return self._perform_performance_monitor(monitor_config)
            elif monitor_type == "error":
                return self._perform_error_monitor(monitor_config)
            elif monitor_type == "health":
                return self._perform_health_monitor(monitor_config)
            elif monitor_type == "custom":
                return self._perform_custom_monitor(monitor_config)
            else:
                return {
                    "success": False,
                    "error": f"Unbekannter Monitor-Typ: {monitor_type}"
                }
        except Exception as e:
            logger.error(f"Fehler beim Durchführen des Monitorings: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _perform_performance_monitor(self, performance_monitor_config: Dict[str, Any]) -> Dict[str, Any]:
        """Performance-Monitoring durchführen"""
        try:
            # Performance-Monitoring durchführen simulieren
            # Hier würde das eigentliche Performance-Monitoring stattfinden
            
            return {
                "success": True,
                "performance_monitor_config": performance_monitor_config,
                "monitor_results": [],
                "monitor_summary": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Durchführen des Performance-Monitorings: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _perform_error_monitor(self, error_monitor_config: Dict[str, Any]) -> Dict[str, Any]:
        """Error-Monitoring durchführen"""
        try:
            # Error-Monitoring durchführen simulieren
            # Hier würde das eigentliche Error-Monitoring stattfinden
            
            return {
                "success": True,
                "error_monitor_config": error_monitor_config,
                "monitor_results": [],
                "monitor_summary": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Durchführen des Error-Monitorings: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _perform_health_monitor(self, health_monitor_config: Dict[str, Any]) -> Dict[str, Any]:
        """Health-Monitoring durchführen"""
        try:
            # Health-Monitoring durchführen simulieren
            # Hier würde das eigentliche Health-Monitoring stattfinden
            
            return {
                "success": True,
                "health_monitor_config": health_monitor_config,
                "monitor_results": [],
                "monitor_summary": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Durchführen des Health-Monitorings: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _perform_custom_monitor(self, custom_monitor_config: Dict[str, Any]) -> Dict[str, Any]:
        """Custom-Monitoring durchführen"""
        try:
            # Custom-Monitoring durchführen simulieren
            # Hier würde das eigentliche Custom-Monitoring stattfinden
            
            return {
                "success": True,
                "custom_monitor_config": custom_monitor_config,
                "monitor_results": [],
                "monitor_summary": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Durchführen des Custom-Monitorings: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _create_monitor_report(self, task_id: str, monitor_result: Dict[str, Any]) -> Path:
        """Monitor-Report erstellen"""
        try:
            report = {
                "task_id": task_id,
                "monitor_type": monitor_result.get("monitor_type", "unknown"),
                "summary": monitor_result.get("result", {}),
                "details": monitor_result,
                "generated_at": datetime.now().isoformat()
            }
            
            report_file = self.monitor_reports_dir / f"{task_id}_report.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            return report_file
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Monitor-Reports: {e}")
            return None
    
    def get_task(self, task_id: str) -> Dict[str, Any]:
        """
        Task abrufen
        
        Args:
            task_id: ID der Task
        
        Returns:
            Dictionary mit der Task
        """
        try:
            task_file = self.monitor_tasks_dir / f"{task_id}.json"
            
            if not task_file.exists():
                return {
                    "success": False,
                    "error": f"Task {task_id} nicht gefunden"
                }
            
            with open(task_file, 'r', encoding='utf-8') as f:
                task = json.load(f)
            
            return {
                "success": True,
                "task": task
            }
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Task: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def list_tasks(self, task_type: Optional[str] = None,
                   task_name: Optional[str] = None,
                   status: Optional[str] = None,
                   priority: Optional[str] = None) -> Dict[str, Any]:
        """
        Alle Tasks auflisten
        
        Args:
            task_type: Filter nach Task-Typ (monitor, performance_monitor, error_monitor, health_monitor, custom_monitor)
            task_name: Filter nach Task-Name
            status: Filter nach Status (pending, in_progress, completed, failed)
            priority: Filter nach Priorität (low, medium, high, critical)
        
        Returns:
            Dictionary mit der Liste der Tasks
        """
        try:
            tasks = []
            
            for task_file in self.monitor_tasks_dir.glob("*.json"):
                with open(task_file, 'r', encoding='utf-8') as f:
                    task = json.load(f)
                
                # Filter anwenden
                if task_type and task.get('type') != task_type:
                    continue
                
                if task_name and task.get('task_name') != task_name:
                    continue
                
                if status and task.get('status') != status:
                    continue
                
                if priority and task.get('priority') != priority:
                    continue
                
                tasks.append(task)
            
            # Sortieren nach Priorität und Erstellungszeitpunkt
            priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
            tasks.sort(key=lambda x: (
                priority_order.get(x.get('priority', 'medium'), 2),
                x.get('created_at', '')
            ))
            
            return {
                "success": True,
                "tasks": tasks,
                "count": len(tasks)
            }
        except Exception as e:
            logger.error(f"Fehler beim Auflisten der Tasks: {e}")
            return {
                "success": False,
                "tasks": [],
                "error": str(e)
            }
    
    def update_task_status(self, task_id: str,
                          status: str,
                          notes: Optional[str] = None,
                          results: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Task-Status aktualisieren
        
        Args:
            task_id: ID der Task
            status: Neuer Status (pending, in_progress, completed, failed)
            notes: Zusätzliche Notizen
            results: Ergebnisse
        
        Returns:
            Dictionary mit dem aktualisierten Task
        """
        try:
            task_file = self.monitor_tasks_dir / f"{task_id}.json"
            
            if not task_file.exists():
                return {
                    "success": False,
                    "error": f"Task {task_id} nicht gefunden"
                }
            
            with open(task_file, 'r', encoding='utf-8') as f:
                task = json.load(f)
            
            # Status aktualisieren
            task['status'] = status
            task['updated_at'] = datetime.now().isoformat()
            
            if notes:
                if 'notes' not in task:
                    task['notes'] = []
                task['notes'].append({
                    "timestamp": datetime.now().isoformat(),
                    "note": notes
                })
            
            if results:
                task['results'] = results
            
            # Task speichern
            with open(task_file, 'w', encoding='utf-8') as f:
                json.dump(task, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Task-Status aktualisiert: {task_id} -> {status}")
            
            return {
                "success": True,
                "task": task
            }
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren des Task-Status: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def delete_task(self, task_id: str) -> Dict[str, Any]:
        """
        Task löschen
        
        Args:
            task_id: ID der Task
        
        Returns:
            Dictionary mit dem Ergebnis
        """
        try:
            task_file = self.monitor_tasks_dir / f"{task_id}.json"
            
            if not task_file.exists():
                return {
                    "success": False,
                    "error": f"Task {task_id} nicht gefunden"
                }
            
            task_file.unlink()
            
            logger.info(f"Task gelöscht: {task_id}")
            
            return {
                "success": True,
                "message": f"Task {task_id} gelöscht"
            }
        except Exception as e:
            logger.error(f"Fehler beim Löschen der Task: {e}")
            return {
                "success": False,
                "error": str(e)
            }
