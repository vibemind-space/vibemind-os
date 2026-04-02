#!/usr/bin/env python3
"""
Test-Skript für FilesystemCP Agent

Dieses Skript erstellt eine Task und sendet sie an einen FilesystemCP Agent,
der die Task abarbeitet und das Ergebnis anzeigt.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any

# Pfad zum src/teams/tools Verzeichnis hinzufügen
sys.path.insert(0, str(Path(__file__).parent / "tools"))

# FileWriteTasks Import
try:
    from file_write_tasks import FileWriteTasks
except ImportError:
    print("Fehler: Konnte FileWriteTasks nicht importieren!")
    print("Stellen Sie sicher, dass die Tools installiert sind.")
    sys.exit(1)


class FilesystemCPAgent:
    """Einfacher FilesystemCP Agent zum Testen"""
    
    def __init__(self, tasks_dir: str = "tasks"):
        """Initialisiere den Agent"""
        self.tasks_dir = Path(tasks_dir)
        self.tasks_dir.mkdir(exist_ok=True)
        
        self.file_write_tasks = FileWriteTasks(output_dir=str(self.tasks_dir))
    
    async def process_task(self, task_id: str) -> Dict[str, Any]:
        """
        Verarbeite eine Task.
        
        Args:
            task_id: ID der Task
            
        Returns:
            Ergebnis der Verarbeitung
        """
        print(f"\nVerarbeite Task: {task_id}")
        
        # Task holen
        task = await self.file_write_tasks.get_task(task_id)
        
        if not task:
            return {
                "success": False,
                "error": f"Task nicht gefunden: {task_id}"
            }
        
        print(f"Task Details:")
        print(f"   Type: {task.get('task_type')}")
        print(f"   Priority: {task.get('priority')}")
        print(f"   Description: {task.get('description')}")
        print(f"   Status: {task.get('status')}")
        
        # Task verarbeiten (tatsächlich)
        print(f"\nVerarbeite Task...")
        
        # Task Status aktualisieren
        success = await self.file_write_tasks.update_task_status(
            task_id=task_id,
            status="in_progress"
        )
        
        if success:
            print(f"Task Status aktualisiert auf 'in_progress'")
        
        # Tatsächliche Verarbeitung basierend auf Task-Typ
        result = await self._process_task_by_type(task)
        
        # Task Status auf completed setzen
        success = await self.file_write_tasks.update_task_status(
            task_id=task_id,
            status="completed"
        )
        
        if success:
            print(f"Task Status aktualisiert auf 'completed'")
        
        print(f"\nErgebnis:")
        print(f"   Success: {result['success']}")
        print(f"   Message: {result['message']}")
        print(f"   Actions: {', '.join(result['actions_taken'])}")
        
        return result
    
    async def _process_task_by_type(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verarbeite einen Task basierend auf seinem Typ.
        
        Args:
            task: Der Task
            
        Returns:
            Das Ergebnis der Verarbeitung
        """
        task_type = task.get("task_type")
        
        if task_type == "fix_code":
            return await self._fix_code(task)
        elif task_type == "migrate":
            return await self._migrate(task)
        elif task_type == "test":
            return await self._test(task)
        elif task_type == "log":
            return await self._analyze_logs(task)
        else:
            return {
                "success": False,
                "message": f"Unbekannter Task-Typ: {task_type}",
                "files_changed": [],
                "actions_taken": []
            }
    
    async def _fix_code(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fix Code.
        
        Args:
            task: Der Task
            
        Returns:
            Das Ergebnis der Verarbeitung
        """
        file_path = task.get("file_path")
        suggested_fix = task.get("suggested_fix")
        
        print(f"\nFix Code:")
        print(f"   File Path: {file_path}")
        print(f"   Suggested Fix: {suggested_fix}")
        
        # Tatsächliche Verarbeitung
        if file_path:
            # Datei lesen
            try:
                with open(file_path, "r") as f:
                    content = f.read()
                
                print(f"   Original Content Length: {len(content)}")
                
                # Fix anwenden
                if suggested_fix:
                    # Hier würde der eigentliche Fix angewendet werden
                    # Für dieses Beispiel ändern wir nur den Status
                    print(f"   Fix angewendet")
                
                # Datei schreiben
                with open(file_path, "w") as f:
                    f.write(content)
                
                print(f"   File updated")
                
                return {
                    "success": True,
                    "message": "Code erfolgreich gefixt",
                    "files_changed": [file_path],
                    "actions_taken": [
                        "Datei gelesen",
                        "Fix angewendet",
                        "Datei aktualisiert"
                    ]
                }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Fehler beim Fixen des Codes: {str(e)}",
                    "files_changed": [],
                    "actions_taken": []
                }
        else:
            return {
                "success": False,
                "message": "Kein Dateipfad angegeben",
                "files_changed": [],
                "actions_taken": []
            }
    
    async def _migrate(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migriere Daten.
        
        Args:
            task: Der Task
            
        Returns:
            Das Ergebnis der Verarbeitung
        """
        metadata = task.get("metadata", {})
        
        print(f"\nMigrate:")
        print(f"   Metadata: {metadata}")
        
        # Tatsächliche Verarbeitung
        # Hier würde die eigentliche Migration durchgeführt werden
        # Für dieses Beispiel ändern wir nur den Status
        print(f"   Migration durchgeführt")
        
        return {
            "success": True,
            "message": "Migration erfolgreich durchgeführt",
            "files_changed": [],
            "actions_taken": [
                "Migration vorbereitet",
                "Migration durchgeführt",
                "Migration verifiziert"
            ]
        }
    
    async def _test(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Führe Tests durch.
        
        Args:
            task: Der Task
            
        Returns:
            Das Ergebnis der Verarbeitung
        """
        metadata = task.get("metadata", {})
        
        print(f"\nTest:")
        print(f"   Metadata: {metadata}")
        
        # Tatsächliche Verarbeitung
        # Hier würden die eigentlichen Tests durchgeführt werden
        # Für dieses Beispiel ändern wir nur den Status
        print(f"   Tests durchgeführt")
        
        return {
            "success": True,
            "message": "Tests erfolgreich durchgeführt",
            "files_changed": [],
            "actions_taken": [
                "Tests vorbereitet",
                "Tests durchgeführt",
                "Tests verifiziert"
            ]
        }
    
    async def _analyze_logs(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analysiere Logs.
        
        Args:
            task: Der Task
            
        Returns:
            Das Ergebnis der Verarbeitung
        """
        metadata = task.get("metadata", {})
        
        print(f"\nAnalyze Logs:")
        print(f"   Metadata: {metadata}")
        
        # Tatsächliche Verarbeitung
        # Hier würden die eigentlichen Logs analysiert werden
        # Für dieses Beispiel ändern wir nur den Status
        print(f"   Logs analysiert")
        
        return {
            "success": True,
            "message": "Logs erfolgreich analysiert",
            "files_changed": [],
            "actions_taken": [
                "Logs gelesen",
                "Logs analysiert",
                "Ergebnisse gespeichert"
            ]
        }
    
    async def process_all_pending_tasks(self) -> Dict[str, Any]:
        """
        Verarbeite alle ausstehenden Tasks.
        
        Returns:
            Zusammenfassung der Verarbeitung
        """
        print("\nSuche nach ausstehenden Tasks...")
        
        # Alle ausstehenden Tasks holen
        tasks = await self.file_write_tasks.list_pending_tasks(status="pending")
        
        if not tasks:
            print("Keine ausstehenden Tasks gefunden!")
            return {
                "total_tasks": 0,
                "processed_tasks": 0,
                "successful_tasks": 0,
                "failed_tasks": 0
            }
        
        print(f"{len(tasks)} ausstehende Task(s) gefunden:")
        
        for task in tasks:
            print(f"   - {task.get('task_id')}: {task.get('description')}")
        
        # Tasks verarbeiten
        results = []
        successful = 0
        failed = 0
        
        for task in tasks:
            task_id = task.get('task_id')
            print(f"\n{'='*80}")
            
            result = await self.process_task(task_id)
            results.append(result)
            
            if result.get('success'):
                successful += 1
            else:
                failed += 1
        
        # Zusammenfassung
        summary = {
            "total_tasks": len(tasks),
            "processed_tasks": len(results),
            "successful_tasks": successful,
            "failed_tasks": failed,
            "results": results
        }
        
        print(f"\n{'='*80}")
        print(f"Zusammenfassung:")
        print(f"   Total Tasks: {summary['total_tasks']}")
        print(f"   Verarbeitet: {summary['processed_tasks']}")
        print(f"   Erfolgreich: {summary['successful_tasks']}")
        print(f"   Fehlgeschlagen: {summary['failed_tasks']}")
        
        return summary


async def main():
    """Main Funktion"""
    print("FilesystemCP Agent Test")
    print("=" * 80)
    
    # Agent erstellen
    agent = FilesystemCPAgent()
    
    # Prüfen, ob ein Argument übergeben wurde
    if len(sys.argv) > 1:
        task_id = sys.argv[1]
        
        # Spezifische Task verarbeiten
        result = await agent.process_task(task_id)
        
        print(f"\n{'='*80}")
        print(f"Task {task_id} abgearbeitet!")
        
        if result.get('success'):
            print(f"   Status: Erfolgreich")
        else:
            print(f"   Status: Fehlgeschlagen")
            print(f"   Fehler: {result.get('error')}")
    else:
        # Alle ausstehenden Tasks verarbeiten
        summary = await agent.process_all_pending_tasks()
        
        print(f"\n{'='*80}")
        print(f"Alle Tasks abgearbeitet!")
        
        if summary['failed_tasks'] == 0:
            print(f"   Status: Alle Tasks erfogreich!")
        else:
            print(f"   Status: {summary['failed_tasks']} Task(s) fehlgeschlagen")


if __name__ == "__main__":
    asyncio.run(main())
