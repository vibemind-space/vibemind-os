"""
File Write Tool für EventFixTeam
Bietet Funktionen zum Schreiben von Dateien für Coding-Tasks
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class FileWriteTool:
    """Tool für Datei-Schreiboperationen"""
    
    def __init__(self, base_dir: str = "."):
        """
        File Write Tool initialisieren
        
        Args:
            base_dir: Basisverzeichnis für das Projekt
        """
        self.base_dir = Path(base_dir)
        self.file_write_dir = self.base_dir / "file_write"
        self.file_write_dir.mkdir(exist_ok=True)
        self.tasks_dir = self.file_write_dir / "tasks"
        self.tasks_dir.mkdir(exist_ok=True)
        
        logger.info(f"File Write Tool initialisiert mit Basisverzeichnis: {base_dir}")
    
    def write_file(self, file_path: str, content: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """
        Datei schreiben
        
        Args:
            file_path: Pfad zur Datei (relativ zum Basisverzeichnis)
            content: Inhalt der Datei
            encoding: Encoding (default: utf-8)
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            # Vollständigen Pfad erstellen
            full_path = self.base_dir / file_path
            
            # Verzeichnis erstellen, falls nicht vorhanden
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Datei schreiben
            with open(full_path, 'w', encoding=encoding) as f:
                f.write(content)
            
            # Log speichern
            logs = self._save_log("write_file", file_path, content, "")
            
            logger.info(f"Datei geschrieben: {full_path}")
            return {
                "success": True,
                "output": f"Datei geschrieben: {full_path}",
                "file_path": str(full_path),
                "logs": logs
            }
        except Exception as e:
            logger.error(f"Fehler beim Schreiben der Datei: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def append_file(self, file_path: str, content: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """
        An Datei anhängen
        
        Args:
            file_path: Pfad zur Datei (relativ zum Basisverzeichnis)
            content: Inhalt, der angehängt werden soll
            encoding: Encoding (default: utf-8)
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            # Vollständigen Pfad erstellen
            full_path = self.base_dir / file_path
            
            # Verzeichnis erstellen, falls nicht vorhanden
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # An Datei anhängen
            with open(full_path, 'a', encoding=encoding) as f:
                f.write(content)
            
            # Log speichern
            logs = self._save_log("append_file", file_path, content, "")
            
            logger.info(f"An Datei angehängt: {full_path}")
            return {
                "success": True,
                "output": f"An Datei angehängt: {full_path}",
                "file_path": str(full_path),
                "logs": logs
            }
        except Exception as e:
            logger.error(f"Fehler beim Anhängen an die Datei: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def read_file(self, file_path: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """
        Datei lesen
        
        Args:
            file_path: Pfad zur Datei (relativ zum Basisverzeichnis)
            encoding: Encoding (default: utf-8)
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            # Vollständigen Pfad erstellen
            full_path = self.base_dir / file_path
            
            # Datei lesen
            with open(full_path, 'r', encoding=encoding) as f:
                content = f.read()
            
            logger.info(f"Datei gelesen: {full_path}")
            return {
                "success": True,
                "output": content,
                "file_path": str(full_path),
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Lesen der Datei: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def delete_file(self, file_path: str) -> Dict[str, Any]:
        """
        Datei löschen
        
        Args:
            file_path: Pfad zur Datei (relativ zum Basisverzeichnis)
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            # Vollständigen Pfad erstellen
            full_path = self.base_dir / file_path
            
            # Datei löschen
            full_path.unlink()
            
            # Log speichern
            logs = self._save_log("delete_file", file_path, "", "")
            
            logger.info(f"Datei gelöscht: {full_path}")
            return {
                "success": True,
                "output": f"Datei gelöscht: {full_path}",
                "file_path": str(full_path),
                "logs": logs
            }
        except Exception as e:
            logger.error(f"Fehler beim Löschen der Datei: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def create_directory(self, dir_path: str) -> Dict[str, Any]:
        """
        Verzeichnis erstellen
        
        Args:
            dir_path: Pfad zum Verzeichnis (relativ zum Basisverzeichnis)
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            # Vollständigen Pfad erstellen
            full_path = self.base_dir / dir_path
            
            # Verzeichnis erstellen
            full_path.mkdir(parents=True, exist_ok=True)
            
            # Log speichern
            logs = self._save_log("create_directory", dir_path, "", "")
            
            logger.info(f"Verzeichnis erstellt: {full_path}")
            return {
                "success": True,
                "output": f"Verzeichnis erstellt: {full_path}",
                "dir_path": str(full_path),
                "logs": logs
            }
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Verzeichnisses: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def list_directory(self, dir_path: str = ".", recursive: bool = False) -> Dict[str, Any]:
        """
        Verzeichnis auflisten
        
        Args:
            dir_path: Pfad zum Verzeichnis (relativ zum Basisverzeichnis)
            recursive: Rekursiv auflisten
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            # Vollständigen Pfad erstellen
            full_path = self.base_dir / dir_path
            
            # Verzeichnis auflisten
            if recursive:
                files = [str(p.relative_to(self.base_dir)) for p in full_path.rglob("*")]
            else:
                files = [str(p.relative_to(self.base_dir)) for p in full_path.iterdir()]
            
            logger.info(f"Verzeichnis aufgelistet: {full_path}")
            return {
                "success": True,
                "output": files,
                "dir_path": str(full_path),
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Auflisten des Verzeichnisses: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def write_json(self, file_path: str, data: Dict[str, Any], indent: int = 2) -> Dict[str, Any]:
        """
        JSON-Datei schreiben
        
        Args:
            file_path: Pfad zur Datei (relativ zum Basisverzeichnis)
            data: JSON-Daten
            indent: Einrückung (default: 2)
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            # Vollständigen Pfad erstellen
            full_path = self.base_dir / file_path
            
            # Verzeichnis erstellen, falls nicht vorhanden
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # JSON-Datei schreiben
            with open(full_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            
            # Log speichern
            logs = self._save_log("write_json", file_path, json.dumps(data, indent=indent), "")
            
            logger.info(f"JSON-Datei geschrieben: {full_path}")
            return {
                "success": True,
                "output": f"JSON-Datei geschrieben: {full_path}",
                "file_path": str(full_path),
                "logs": logs
            }
        except Exception as e:
            logger.error(f"Fehler beim Schreiben der JSON-Datei: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def read_json(self, file_path: str) -> Dict[str, Any]:
        """
        JSON-Datei lesen
        
        Args:
            file_path: Pfad zur Datei (relativ zum Basisverzeichnis)
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            # Vollständigen Pfad erstellen
            full_path = self.base_dir / file_path
            
            # JSON-Datei lesen
            with open(full_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info(f"JSON-Datei gelesen: {full_path}")
            return {
                "success": True,
                "output": data,
                "file_path": str(full_path),
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Lesen der JSON-Datei: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def create_coding_task(self, task_name: str, description: str, files: List[Dict[str, str]], 
                          priority: str = "medium") -> Dict[str, Any]:
        """
        Coding-Task erstellen
        
        Args:
            task_name: Name des Tasks
            description: Beschreibung des Tasks
            files: Liste von Dateien mit Pfad und Inhalt
            priority: Priorität (low, medium, high)
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            # Task-Daten erstellen
            task_data = {
                "task_name": task_name,
                "description": description,
                "priority": priority,
                "files": files,
                "status": "pending",
                "created_at": datetime.now().isoformat()
            }
            
            # Task-ID generieren
            task_id = f"{task_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Task speichern
            task_file = self.tasks_dir / f"{task_id}.json"
            with open(task_file, 'w', encoding='utf-8') as f:
                json.dump(task_data, f, indent=2, ensure_ascii=False)
            
            # Dateien schreiben
            for file_info in files:
                file_path = file_info.get("path")
                content = file_info.get("content", "")
                if file_path:
                    self.write_file(file_path, content)
            
            logger.info(f"Coding-Task erstellt: {task_id}")
            return {
                "success": True,
                "output": f"Coding-Task erstellt: {task_id}",
                "task_id": task_id,
                "task_data": task_data,
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Coding-Tasks: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def get_task(self, task_id: str) -> Dict[str, Any]:
        """
        Task abrufen
        
        Args:
            task_id: ID des Tasks
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            # Task-Datei finden
            task_file = self.tasks_dir / f"{task_id}.json"
            
            # Task lesen
            with open(task_file, 'r', encoding='utf-8') as f:
                task_data = json.load(f)
            
            logger.info(f"Task abgerufen: {task_id}")
            return {
                "success": True,
                "output": task_data,
                "task_id": task_id,
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Abrufen des Tasks: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def list_tasks(self, status: str = None) -> Dict[str, Any]:
        """
        Tasks auflisten
        
        Args:
            status: Status filtern (pending, in_progress, completed)
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            tasks = []
            
            # Alle Task-Dateien auflisten
            for task_file in self.tasks_dir.glob("*.json"):
                with open(task_file, 'r', encoding='utf-8') as f:
                    task_data = json.load(f)
                
                # Filter nach Status
                if status is None or task_data.get("status") == status:
                    tasks.append(task_data)
            
            logger.info(f"Tasks aufgelistet: {len(tasks)}")
            return {
                "success": True,
                "output": tasks,
                "count": len(tasks),
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Auflisten der Tasks: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def update_task_status(self, task_id: str, status: str) -> Dict[str, Any]:
        """
        Task-Status aktualisieren
        
        Args:
            task_id: ID des Tasks
            status: Neuer Status (pending, in_progress, completed)
        
        Returns:
            Dict mit success, output, logs, error
        """
        try:
            # Task-Datei finden
            task_file = self.tasks_dir / f"{task_id}.json"
            
            # Task lesen
            with open(task_file, 'r', encoding='utf-8') as f:
                task_data = json.load(f)
            
            # Status aktualisieren
            task_data["status"] = status
            task_data["updated_at"] = datetime.now().isoformat()
            
            # Task speichern
            with open(task_file, 'w', encoding='utf-8') as f:
                json.dump(task_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Task-Status aktualisiert: {task_id} -> {status}")
            return {
                "success": True,
                "output": f"Task-Status aktualisiert: {task_id} -> {status}",
                "task_id": task_id,
                "status": status,
                "logs": ""
            }
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren des Task-Status: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": ""
            }
    
    def _save_log(self, operation: str, file_path: str, content: str, error: str) -> str:
        """
        Log speichern
        
        Args:
            operation: Operation (write_file, append_file, etc.)
            file_path: Pfad zur Datei
            content: Inhalt
            error: Fehlermeldung
        
        Returns:
            Pfad zur Log-Datei
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = self.file_write_dir / f"file_write_{operation}_{timestamp}.log"
            
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"Operation: {operation}\n")
                f.write(f"File Path: {file_path}\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write("=" * 80 + "\n\n")
                f.write("Content:\n")
                f.write(content[:1000])  # Nur erste 1000 Zeichen
                f.write("\n\n")
                f.write("Error:\n")
                f.write(error)
            
            logger.info(f"File Write Log gespeichert: {log_file}")
            return str(log_file)
        except Exception as e:
            logger.error(f"Fehler beim Speichern des File Write Logs: {e}")
            return ""
