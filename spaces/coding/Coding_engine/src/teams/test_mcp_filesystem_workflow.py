#!/usr/bin/env python3
"""
Beispiel-Workflow für MCP Agent Filesystem

Dieses Skript zeigt, wie ein MCP Agent eine Datei erstellt
und diese an einen FilesystemCP Agent sendet, der die Datei verarbeitet.
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


class MCPFilesystemAgent:
    """Einfacher MCP Filesystem Agent zum Testen"""
    
    def __init__(self, output_dir: str = "tasks"):
        """Initialisiere den Agent"""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.file_write_tasks = FileWriteTasks(output_dir=str(self.output_dir))
    
    async def create_file(self, file_path: str, content: str) -> Dict[str, Any]:
        """
        Erstellt eine Datei.
        
        Args:
            file_path: Pfad zur Datei
            content: Inhalt der Datei
            
        Returns:
            Ergebnis der Erstellung
        """
        print(f"\nErstelle Datei: {file_path}")
        
        # Datei erstellen
        full_path = self.output_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"Datei erstellt: {full_path}")
        
        return {
            "success": True,
            "file_path": str(full_path),
            "content": content
        }
    
    async def create_hello_file(self) -> Dict[str, Any]:
        """
        Erstellt eine "hallo.txt" Datei.
        
        Returns:
            Ergebnis der Erstellung
        """
        content = "hallo"
        file_path = "hallo.txt"
        
        return await self.create_file(file_path, content)
    
    async def create_fix_task_for_file(self, file_path: str) -> Dict[str, Any]:
        """
        Erstellt eine Fix-Task für eine Datei.
        
        Args:
            file_path: Pfad zur Datei
            
        Returns:
            Ergebnis der Task-Erstellung
        """
        print(f"\nErstelle Fix-Task für Datei: {file_path}")
        
        # Task erstellen
        task = await self.file_write_tasks.create_fix_task(
            task_type="fix_code",
            priority="high",
            description=f"Erstelle Datei: {file_path}",
            file_path=file_path,
            metadata={
                "action": "create_file",
                "file_path": file_path,
                "content": "hallo"
            }
        )
        
        print(f"Task erstellt: {task.task_id}")
        print(f"   Type: {task.task_type}")
        print(f"   Priority: {task.priority}")
        print(f"   Description: {task.description}")
        
        return {
            "success": True,
            "task_id": task.task_id,
            "task": task.to_dict()
        }


async def main():
    """Main Funktion"""
    print("MCP Agent Filesystem Workflow")
    print("=" * 80)
    
    # Agent erstellen
    agent = MCPFilesystemAgent()
    
    # 1. Datei erstellen
    print("\nSchritt 1: Datei erstellen")
    print("-" * 80)
    
    file_result = await agent.create_hello_file()
    
    if file_result.get('success'):
        print(f"\nErfolg: Datei erstellt!")
        print(f"   Pfad: {file_result.get('file_path')}")
        print(f"   Inhalt: {file_result.get('content')}")
    else:
        print(f"\nFehler: Datei konnte nicht erstellt werden!")
        sys.exit(1)
    
    # 2. Fix-Task erstellen
    print("\nSchritt 2: Fix-Task erstellen")
    print("-" * 80)
    
    task_result = await agent.create_fix_task_for_file("hallo.txt")
    
    if task_result.get('success'):
        print(f"\nErfolg: Task erstellt!")
        print(f"   Task ID: {task_result.get('task_id')}")
        print(f"   Task Details: {json.dumps(task_result.get('task'), indent=2)}")
    else:
        print(f"\nFehler: Task konnte nicht erstellt werden!")
        sys.exit(1)
    
    # 3. Zusammenfassung
    print("\n" + "=" * 80)
    print("Zusammenfassung:")
    print("-" * 80)
    print(f"Datei erstellt: {file_result.get('file_path')}")
    print(f"Task erstellt: {task_result.get('task_id')}")
    print(f"Task Status: pending")
    print(f"\nNächste Schritte:")
    print(f"1. Task mit FilesystemCP Agent abarbeiten:")
    print(f"   python src/teams/test_filesystem_cp.py {task_result.get('task_id')}")
    print(f"2. Task Status überprüfen:")
    print(f"   python -m src.teams.event_fix_cli_simple get-task --id {task_result.get('task_id')}")
    print(f"3. Datei überprüfen:")
    print(f"   cat {file_result.get('file_path')}")


if __name__ == "__main__":
    asyncio.run(main())
