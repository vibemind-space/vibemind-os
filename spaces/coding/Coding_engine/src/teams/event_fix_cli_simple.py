#!/usr/bin/env python3
"""
EventFixTeam CLI (Simplified)

Command Line Interface für das EventFixTeam zum Testen und Debuggen.
Diese Version verwendet nur die FileWriteTasks und importiert nicht das EventFixTeam.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import argparse

# Tools Imports
try:
    from src.teams.tools.file_write_tasks import FileWriteTasks
except ImportError:
    try:
        from tools.file_write_tasks import FileWriteTasks
    except ImportError:
        print("Fehler: Konnte FileWriteTasks nicht importieren!")
        print("Stellen Sie sicher, dass die Tools installiert sind.")
        sys.exit(1)


class EventFixCLI:
    """CLI für das EventFixTeam"""
    
    def __init__(self, tasks_dir: str = "tasks"):
        """Initialisiere die CLI"""
        self.tasks_dir = Path(tasks_dir)
        self.tasks_dir.mkdir(exist_ok=True)
        
        self.file_write_tasks = FileWriteTasks(output_dir=str(self.tasks_dir))
    
    async def create_task(
        self,
        task_type: str,
        priority: str,
        title: str,
        description: str,
        source: str,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Erstelle einen neuen Task"""
        # Task erstellen
        task = await self.file_write_tasks.create_fix_task(
            task_type=task_type,
            priority=priority,
            description=description,
            metadata=data or {}
        )
        
        print(f"Task erstellt: {task.task_id}")
        print(f"  Type: {task.task_type}")
        print(f"  Priority: {task.priority}")
        print(f"  Status: {task.status}")
        print(f"  Description: {task.description}")
    
    async def list_tasks(self, status: Optional[str] = None) -> None:
        """Liste alle Tasks auf"""
        tasks = await self.file_write_tasks.list_pending_tasks()
        
        if not tasks:
            print("Keine Tasks gefunden!")
            return
        
        # Filter nach Status
        if status:
            tasks = [t for t in tasks if t.get('status') == status]
        
        print(f"{len(tasks)} Task(s) gefunden:")
        print()
        
        for task in tasks:
            print(f"ID: {task.get('id')}")
            print(f"  Type: {task.get('task_type')}")
            print(f"  Priority: {task.get('priority')}")
            print(f"  Status: {task.get('status')}")
            print(f"  Title: {task.get('title')}")
            print(f"  Created: {task.get('created_at')}")
            print()
    
    async def get_task(self, task_id: str) -> None:
        """Hole einen Task"""
        task = await self.file_write_tasks.get_task(task_id)
        
        if not task:
            print(f"Task nicht gefunden: {task_id}")
            return
        
        print(f"Task Details:")
        print(f"ID: {task.get('id')}")
        print(f"Type: {task.get('task_type')}")
        print(f"Priority: {task.get('priority')}")
        print(f"Status: {task.get('status')}")
        print(f"Title: {task.get('title')}")
        print(f"Description: {task.get('description')}")
        print(f"Source: {task.get('source')}")
        print(f"Created: {task.get('created_at')}")
        print(f"Updated: {task.get('updated_at')}")
        
        if task.get('data'):
            print(f"Data: {json.dumps(task.get('data'), indent=2)}")
        
        if task.get('result'):
            print(f"Result: {json.dumps(task.get('result'), indent=2)}")
    
    async def update_task_status(
        self,
        task_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None
    ) -> None:
        """Aktualisiere den Status eines Tasks"""
        # Task aktualisieren
        success = await self.file_write_tasks.update_task_status(
            task_id=task_id,
            status=status
        )
        
        if success:
            print(f"Task {task_id} aktualisiert auf {status}")
        else:
            print(f"Task {task_id} konnte nicht aktualisiert werden")
    
    async def delete_task(self, task_id: str) -> None:
        """Lösche einen Task"""
        success = await self.file_write_tasks.delete_task(task_id)
        
        if success:
            print(f"Task {task_id} gelöscht")
        else:
            print(f"Task {task_id} konnte nicht gelöscht werden")
    
    async def get_statistics(self) -> None:
        """Hole Statistiken"""
        stats = await self.file_write_tasks.get_task_statistics()
        
        print("Task Statistiken:")
        print(f"Total: {stats.get('total', 0)}")
        print(f"Pending: {stats.get('pending', 0)}")
        print(f"In Progress: {stats.get('in_progress', 0)}")
        print(f"Completed: {stats.get('completed', 0)}")
        print(f"Failed: {stats.get('failed', 0)}")


async def main():
    """Main Funktion"""
    parser = argparse.ArgumentParser(
        description="EventFixTeam CLI (Simplified)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  # Task erstellen
  python -m src.teams.event_fix_cli_simple create-task --type fix_code --priority high --title "Fix Bug" --description "Fix critical bug" --source "user"
  
  # Tasks auflisten
  python -m src.teams.event_fix_cli_simple list-tasks
  
  # Task Details anzeigen
  python -m src.teams.event_fix_cli_simple get-task --id <task-id>
  
  # Task Status aktualisieren
  python -m src.teams.event_fix_cli_simple update-task --id <task-id> --status completed
  
  # Task löschen
  python -m src.teams.event_fix_cli_simple delete-task --id <task-id>
  
  # Statistiken anzeigen
  python -m src.teams.event_fix_cli_simple statistics
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Verfügbare Befehle")
    
    # Create Task Command
    create_task_parser = subparsers.add_parser("create-task", help="Erstelle einen neuen Task")
    create_task_parser.add_argument("--type", required=True, choices=["fix_code", "migration", "test_fix", "log_analysis"], help="Task Type")
    create_task_parser.add_argument("--priority", required=True, choices=["low", "medium", "high", "critical"], help="Priority")
    create_task_parser.add_argument("--title", required=True, help="Task Title")
    create_task_parser.add_argument("--description", required=True, help="Task Description")
    create_task_parser.add_argument("--source", required=True, help="Task Source")
    create_task_parser.add_argument("--data", help="Task Data (JSON)")
    
    # List Tasks Command
    list_tasks_parser = subparsers.add_parser("list-tasks", help="Liste alle Tasks auf")
    list_tasks_parser.add_argument("--status", choices=["pending", "in_progress", "completed", "failed"], help="Filter nach Status")
    
    # Get Task Command
    get_task_parser = subparsers.add_parser("get-task", help="Hole Task Details")
    get_task_parser.add_argument("--id", required=True, help="Task ID")
    
    # Update Task Command
    update_task_parser = subparsers.add_parser("update-task", help="Aktualisiere Task Status")
    update_task_parser.add_argument("--id", required=True, help="Task ID")
    update_task_parser.add_argument("--status", required=True, choices=["pending", "in_progress", "completed", "failed"], help="Neuer Status")
    update_task_parser.add_argument("--result", help="Result (JSON)")
    
    # Delete Task Command
    delete_task_parser = subparsers.add_parser("delete-task", help="Lösche einen Task")
    delete_task_parser.add_argument("--id", required=True, help="Task ID")
    
    # Statistics Command
    statistics_parser = subparsers.add_parser("statistics", help="Zeige Statistiken")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # CLI erstellen
    cli = EventFixCLI()
    
    # Befehle ausführen
    if args.command == "create-task":
        data = json.loads(args.data) if args.data else None
        await cli.create_task(
            task_type=args.type,
            priority=args.priority,
            title=args.title,
            description=args.description,
            source=args.source,
            data=data
        )
    elif args.command == "list-tasks":
        await cli.list_tasks(status=args.status)
    elif args.command == "get-task":
        await cli.get_task(task_id=args.id)
    elif args.command == "update-task":
        result = json.loads(args.result) if args.result else None
        await cli.update_task_status(
            task_id=args.id,
            status=args.status,
            result=result
        )
    elif args.command == "delete-task":
        await cli.delete_task(task_id=args.id)
    elif args.command == "statistics":
        await cli.get_statistics()


if __name__ == "__main__":
    asyncio.run(main())
