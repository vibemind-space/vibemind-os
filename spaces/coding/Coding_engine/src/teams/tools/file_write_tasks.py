"""
FileWriteTasks - File-Write Tasks für Event-Fixes.

Verantwortlichkeiten:
- Fix-Tasks erstellen (kein Code-Schreiben)
- Migrations-Tasks erstellen
- Test-Fix-Tasks erstellen
- Log-Analyse-Tasks erstellen

Alle Tasks werden als JSON gespeichert und können von File-Write Tools ausgeführt werden.
"""

import asyncio
import json
import os
import sys
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FixTaskSpec:
    """Spezifikation einer Fix-Task."""
    task_id: str
    task_type: str  # "fix_code", "migration", "test_fix", "log_analysis"
    priority: str  # "critical", "high", "medium", "low"
    description: str
    file_path: Optional[str] = None
    suggested_fix: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "pending"
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "priority": self.priority,
            "file_path": self.file_path,
            "description": self.description,
            "suggested_fix": self.suggested_fix,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "status": self.status,
        }


@dataclass
class MigrationTaskSpec:
    """Spezifikation einer Migrations-Task."""
    task_id: str
    migration_type: str  # "schema", "data", "rollback"
    source_schema: str
    target_schema: str
    description: str
    rollback_plan: str
    dependencies: List[str] = field(default_factory=list)
    estimated_duration: str = "5m"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "pending"
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "migration_type": self.migration_type,
            "source_schema": self.source_schema,
            "target_schema": self.target_schema,
            "description": self.description,
            "rollback_plan": self.rollback_plan,
            "dependencies": self.dependencies,
            "estimated_duration": self.estimated_duration,
            "created_at": self.created_at,
            "status": self.status,
        }


@dataclass
class TestFixTaskSpec:
    """Spezifikation einer Test-Fix-Task."""
    task_id: str
    test_type: str  # "e2e", "unit", "regression"
    expected_behavior: str
    actual_behavior: str
    test_file: Optional[str] = None
    test_url: Optional[str] = None
    test_selector: Optional[str] = None
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None
    suggested_fix: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "pending"
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "test_type": self.test_type,
            "test_file": self.test_file,
            "test_url": self.test_url,
            "test_selector": self.test_selector,
            "expected_behavior": self.expected_behavior,
            "actual_behavior": self.actual_behavior,
            "error_message": self.error_message,
            "screenshot_path": self.screenshot_path,
            "suggested_fix": self.suggested_fix,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "status": self.status,
        }


@dataclass
class LogAnalysisTaskSpec:
    """Spezifikation einer Log-Analyse-Task."""
    task_id: str
    analysis_type: str  # "error_detection", "performance", "anomaly"
    time_range: str
    services: List[str] = field(default_factory=list)
    containers: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    error_patterns: Dict[str, int] = field(default_factory=dict)
    performance_issues: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "pending"
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "analysis_type": self.analysis_type,
            "time_range": self.time_range,
            "services": self.services,
            "containers": self.containers,
            "keywords": self.keywords,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "error_patterns": self.error_patterns,
            "performance_issues": self.performance_issues,
            "recommendations": self.recommendations,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "status": self.status,
        }


class FileWriteTasks:
    """
    File-Write Tasks - Erstellt Tasks für File-Write Tools.
    
    Alle Tasks werden als JSON gespeichert und können von File-Write Tools
    ausgeführt werden, ohne dass der Agent Code direkt schreibt.
    """
    
    def __init__(self, output_dir: str = "./event_fix_tasks"):
        self.output_dir = os.path.abspath(output_dir)
        self.logger = logger.bind(component="file_write_tasks", output_dir=output_dir)
        
        # Output-Verzeichnis erstellen
        os.makedirs(self.output_dir, exist_ok=True)
    
    async def create_fix_task(
        self,
        task_type: str,
        priority: str,
        description: str,
        file_path: Optional[str] = None,
        suggested_fix: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FixTaskSpec:
        """
        Erstellt eine Fix-Task.
        
        Args:
            task_type: Typ der Task ("fix_code", "migration", "test_fix", "log_analysis")
            priority: Priorität ("critical", "high", "medium", "low")
            description: Beschreibung des Problems
            file_path: Optionaler Dateipfad
            suggested_fix: Optionaler Fix-Vorschlag
            metadata: Optionale Metadaten
            
        Returns:
            Erstellte FixTaskSpec
        """
        import uuid
        
        task = FixTaskSpec(
            task_id=f"fix_{uuid.uuid4().hex[:8]}",
            task_type=task_type,
            priority=priority,
            file_path=file_path,
            description=description,
            suggested_fix=suggested_fix,
            metadata=metadata or {},
        )
        
        # Task speichern
        await self._save_task(task)
        
        self.logger.info(
            "fix_task_created",
            task_id=task.task_id,
            type=task_type,
            priority=priority,
            file_path=file_path,
        )
        
        return task
    
    async def create_migration_task(
        self,
        migration_type: str,
        source_schema: str,
        target_schema: str,
        description: str,
        rollback_plan: str,
        dependencies: Optional[List[str]] = None,
        estimated_duration: str = "5m",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MigrationTaskSpec:
        """
        Erstellt eine Migrations-Task.
        
        Args:
            migration_type: Typ der Migration ("schema", "data", "rollback")
            source_schema: Quell-Schema
            target_schema: Ziel-Schema
            description: Beschreibung der Migration
            rollback_plan: Rollback-Plan
            dependencies: Optionale Abhängigkeiten
            estimated_duration: Geschätzte Dauer
            metadata: Optionale Metadaten
            
        Returns:
            Erstellte MigrationTaskSpec
        """
        import uuid
        
        task = MigrationTaskSpec(
            task_id=f"mig_{uuid.uuid4().hex[:8]}",
            migration_type=migration_type,
            source_schema=source_schema,
            target_schema=target_schema,
            description=description,
            rollback_plan=rollback_plan,
            dependencies=dependencies or [],
            estimated_duration=estimated_duration,
            metadata=metadata or {},
        )
        
        # Task speichern
        await self._save_task(task)
        
        self.logger.info(
            "migration_task_created",
            task_id=task.task_id,
            type=migration_type,
            source_schema=source_schema,
            target_schema=target_schema,
        )
        
        return task
    
    async def create_test_fix_task(
        self,
        test_type: str,
        test_file: Optional[str] = None,
        test_url: Optional[str] = None,
        test_selector: Optional[str] = None,
        expected_behavior: str = "",
        actual_behavior: str = "",
        error_message: Optional[str] = None,
        screenshot_path: Optional[str] = None,
        suggested_fix: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TestFixTaskSpec:
        """
        Erstellt eine Test-Fix-Task.
        
        Args:
            test_type: Typ des Tests ("e2e", "unit", "regression")
            test_file: Optionaler Test-Dateipfad
            test_url: Optionaler Test-URL
            test_selector: Optionaler CSS-Selector
            expected_behavior: Erwartetes Verhalten
            actual_behavior: Tatsächliches Verhalten
            error_message: Optionale Fehlermeldung
            screenshot_path: Optionaler Screenshot-Pfad
            suggested_fix: Optionaler Fix-Vorschlag
            metadata: Optionale Metadaten
            
        Returns:
            Erstellte TestFixTaskSpec
        """
        import uuid
        
        task = TestFixTaskSpec(
            task_id=f"test_{uuid.uuid4().hex[:8]}",
            test_type=test_type,
            test_file=test_file,
            test_url=test_url,
            test_selector=test_selector,
            expected_behavior=expected_behavior,
            actual_behavior=actual_behavior,
            error_message=error_message,
            screenshot_path=screenshot_path,
            suggested_fix=suggested_fix,
            metadata=metadata or {},
        )
        
        # Task speichern
        await self._save_task(task)
        
        self.logger.info(
            "test_fix_task_created",
            task_id=task.task_id,
            type=test_type,
            test_file=test_file,
            test_url=test_url,
        )
        
        return task
    
    async def create_log_analysis_task(
        self,
        analysis_type: str,
        time_range: str = "1h",
        services: Optional[List[str]] = None,
        containers: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        error_count: int = 0,
        warning_count: int = 0,
        error_patterns: Optional[Dict[str, int]] = None,
        performance_issues: Optional[List[Dict[str, Any]]] = None,
        recommendations: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LogAnalysisTaskSpec:
        """
        Erstellt eine Log-Analyse-Task.
        
        Args:
            analysis_type: Typ der Analyse ("error_detection", "performance", "anomaly")
            time_range: Zeitbereich für Analyse
            services: Optionale Liste von Services
            containers: Optionale Liste von Containern
            keywords: Optionale Liste von Keywords
            error_count: Anzahl der Fehler
            warning_count: Anzahl der Warnungen
            error_patterns: Gefundene Fehlermuster
            performance_issues: Performance-Issues
            recommendations: Empfehlungen
            metadata: Optionale Metadaten
            
        Returns:
            Erstellte LogAnalysisTaskSpec
        """
        import uuid
        
        task = LogAnalysisTaskSpec(
            task_id=f"log_{uuid.uuid4().hex[:8]}",
            analysis_type=analysis_type,
            time_range=time_range,
            services=services or [],
            containers=containers or [],
            keywords=keywords or [],
            error_count=error_count,
            warning_count=warning_count,
            error_patterns=error_patterns or {},
            performance_issues=performance_issues or [],
            recommendations=recommendations or [],
            metadata=metadata or {},
        )
        
        # Task speichern
        await self._save_task(task)
        
        self.logger.info(
            "log_analysis_task_created",
            task_id=task.task_id,
            type=analysis_type,
            time_range=time_range,
            error_count=error_count,
        warning_count=warning_count,
        )
        
        return task
    
    async def _save_task(self, task: Any) -> None:
        """
        Speichert eine Task als JSON.
        
        Args:
            task: Die zu speichernde Task (FixTaskSpec, MigrationTaskSpec, etc.)
        """
        try:
            # Task-Dateiname bestimmen
            task_type = getattr(task, 'task_type', 'unknown')
            task_id = getattr(task, 'task_id', 'unknown')
            
            filename = f"{task_type}_{task_id}.json"
            filepath = os.path.join(self.output_dir, filename)
            
            # Task als JSON speichern
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(task.to_dict(), f, indent=2, ensure_ascii=False)
            
            self.logger.debug(
                "task_saved",
                task_id=task_id,
                type=task_type,
                filepath=filepath,
            )
                
        except Exception as e:
            self.logger.error(
                "task_save_failed",
                task_id=getattr(task, 'task_id', 'unknown'),
                type=task_type,
                error=str(e),
            )
    
    async def list_pending_tasks(
        self,
        task_type: Optional[str] = None,
        status: str = "pending",
    ) -> List[Dict[str, Any]]:
        """
        Listet alle ausstehenden Tasks.
        
        Args:
            task_type: Optionaler Filter nach Task-Typ
            status: Filter nach Status ("pending", "processing", "completed")
            
        Returns:
            Liste von Tasks
        """
        self.logger.info(
            "listing_pending_tasks",
            task_type=task_type,
            status=status,
        )
        
        tasks = []
        
        try:
            # Alle JSON-Dateien im Output-Verzeichnis lesen
            for filename in os.listdir(self.output_dir):
                if not filename.endswith('.json'):
                    continue
                
                filepath = os.path.join(self.output_dir, filename)
                
                with open(filepath, 'r', encoding='utf-8') as f:
                    task_data = json.load(f)
                
                # Filter anwenden
                if task_type and task_data.get('task_type') != task_type:
                    continue
                
                if status and task_data.get('status') != status:
                    continue
                
                tasks.append(task_data)
            
            self.logger.info(
                "tasks_found",
                count=len(tasks),
                task_type=task_type,
                status=status,
            )
            
        except Exception as e:
            self.logger.error(
                "list_tasks_failed",
                error=str(e),
            )
        
        return tasks
    
    async def get_task(
        self,
        task_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Holt eine Task anhand ihrer ID.
        
        Args:
            task_id: ID der Task
            
        Returns:
            Task-Daten oder None
        """
        self.logger.info(
            "getting_task",
            task_id=task_id,
        )
        
        try:
            # Task-Datei finden
            for filename in os.listdir(self.output_dir):
                if not filename.endswith('.json'):
                    continue
                
                if task_id in filename:
                    filepath = os.path.join(self.output_dir, filename)
                    
                    with open(filepath, 'r', encoding='utf-8') as f:
                        return json.load(f)
            
            self.logger.warning(
                "task_not_found",
                task_id=task_id,
            )
            
        except Exception as e:
            self.logger.error(
                "get_task_failed",
                task_id=task_id,
                error=str(e),
            )
        
        return None
    
    async def update_task_status(
        self,
        task_id: str,
        status: str,
    ) -> bool:
        """
        Aktualisiert den Status einer Task.
        
        Args:
            task_id: ID der Task
            status: Neuer Status ("pending", "processing", "completed", "failed")
            
        Returns:
            True bei Erfolg, False bei Misserfolg
        """
        self.logger.info(
            "updating_task_status",
            task_id=task_id,
            status=status,
        )
        
        try:
            # Task finden
            task_data = await self.get_task(task_id)
            
            if not task_data:
                self.logger.warning(
                    "task_not_found_for_update",
                    task_id=task_id,
                )
                return False
            
            # Status aktualisieren
            task_data['status'] = status
            
            # Task-Dateiname bestimmen
            task_type = task_data.get('task_type', 'unknown')
            filename = f"{task_type}_{task_id}.json"
            filepath = os.path.join(self.output_dir, filename)
            
            # Task speichern
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(task_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(
                "task_status_updated",
                task_id=task_id,
                status=status,
                filepath=filepath,
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "update_task_status_failed",
                task_id=task_id,
                status=status,
                error=str(e),
            )
            return False
    
    async def delete_task(
        self,
        task_id: str,
    ) -> bool:
        """
        Löscht eine Task.
        
        Args:
            task_id: ID der Task
            
        Returns:
            True bei Erfolg, False bei Misserfolg
        """
        self.logger.info(
            "deleting_task",
            task_id=task_id,
        )
        
        try:
            # Task-Datei finden
            for filename in os.listdir(self.output_dir):
                if task_id in filename and filename.endswith('.json'):
                    filepath = os.path.join(self.output_dir, filename)
                    
                    # Datei löschen
                    os.remove(filepath)
                    
                    self.logger.info(
                        "task_deleted",
                        task_id=task_id,
                        filepath=filepath,
                    )
                    
                    return True
            
            self.logger.warning(
                "task_not_found_for_deletion",
                task_id=task_id,
            )
            
        except Exception as e:
            self.logger.error(
                "delete_task_failed",
                task_id=task_id,
                error=str(e),
            )
            return False
    
    async def get_task_statistics(
        self,
    ) -> Dict[str, Any]:
        """
        Holt Statistiken über alle Tasks.
        
        Returns:
            Dict mit Statistiken
        """
        self.logger.info("getting_task_statistics")
        
        try:
            # Alle JSON-Dateien im Output-Verzeichnis lesen
            all_tasks = []
            
            for filename in os.listdir(self.output_dir):
                if not filename.endswith('.json'):
                    continue
                    
                filepath = os.path.join(self.output_dir, filename)
                
                with open(filepath, 'r', encoding='utf-8') as f:
                    task_data = json.load(f)
                    all_tasks.append(task_data)
            
            # Statistiken berechnen
            stats = {
                "total_tasks": len(all_tasks),
                "by_type": {},
                "by_status": {},
                "by_priority": {},
            }
            
            for task in all_tasks:
                task_type = task.get('task_type', 'unknown')
                status = task.get('status', 'unknown')
                priority = task.get('priority', 'unknown')
                
                # Nach Typ gruppieren
                if task_type not in stats['by_type']:
                    stats['by_type'][task_type] = 0
                stats['by_type'][task_type] += 1
                
                # Nach Status gruppieren
                if status not in stats['by_status']:
                    stats['by_status'][status] = 0
                stats['by_status'][status] += 1
                
                # Nach Priorität gruppieren
                if priority not in stats['by_priority']:
                    stats['by_priority'][priority] = 0
                stats['by_priority'][priority] += 1
            
            self.logger.info(
                "task_statistics_calculated",
                total=stats['total_tasks'],
                by_type=stats['by_type'],
                by_status=stats['by_status'],
                by_priority=stats['by_priority'],
            )
            
            return stats
            
        except Exception as e:
            self.logger.error(
                "get_task_statistics_failed",
                error=str(e),
            )
            return {
                "total_tasks": 0,
                "by_type": {},
                "by_status": {},
                "by_priority": {},
            }
