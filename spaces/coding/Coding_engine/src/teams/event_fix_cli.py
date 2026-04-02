#!/usr/bin/env python3
"""
EventFixTeam CLI

Command Line Interface für das EventFixTeam zum Testen und Debuggen.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import argparse

# EventFixTeam Imports
try:
    from src.teams.event_fix_team import (
        EventFixTeam,
        EventFixConfig,
        FixTask,
        FixTaskType,
        FixPriority,
        FixStatus,
        EventBus,
        SharedState
    )
except ImportError:
    # Fallback: Versuche direkte Imports
    try:
        from event_fix_team import (
            EventFixTeam,
            EventFixConfig,
            FixTask,
            FixTaskType,
            FixPriority,
            FixStatus,
            EventBus,
            SharedState
        )
    except ImportError:
        print("❌ Konnte EventFixTeam nicht importieren!")
        print("   Stellen Sie sicher, dass das EventFixTeam installiert ist.")
        sys.exit(1)

# Tools Imports
try:
    from src.teams.tools.file_write_tasks import FileWriteTasks
except ImportError:
    try:
        from tools.file_write_tasks import FileWriteTasks
    except ImportError:
        print("❌ Konnte FileWriteTasks nicht importieren!")
        print("   Stellen Sie sicher, dass die Tools installiert sind.")
        sys.exit(1)


class EventFixCLI:
    """CLI für das EventFixTeam"""
    
    def __init__(self, tasks_dir: str = "tasks"):
        """Initialisiere die CLI"""
        self.tasks_dir = Path(tasks_dir)
        self.tasks_dir.mkdir(exist_ok=True)
        
        self.file_write_tasks = FileWriteTasks(tasks_dir=str(self.tasks_dir))
        self.team: Optional[EventFixTeam] = None
        self.event_bus: Optional[EventBus] = None
        self.shared_state: Optional[SharedState] = None
        
    async def start_team(self) -> None:
        """Starte das EventFixTeam"""
        print("🚀 Starte EventFixTeam...")
        
        # Event Bus und Shared State erstellen
        self.event_bus = EventBus()
        self.shared_state = SharedState()
        
        # EventFixTeam Konfiguration
        config = EventFixConfig(
            max_concurrent_tasks=5,
            task_timeout=300,
            enable_auto_fix=True,
            enable_auto_test=True,
            enable_auto_migration=True,
            enable_log_analysis=True
        )
        
        # EventFixTeam erstellen
        self.team = EventFixTeam(
            config=config,
            event_bus=self.event_bus,
            shared_state=self.shared_state
        )
        
        # EventFixTeam starten
        await self.team.start()
        
        print("✅ EventFixTeam gestartet!")
        
    async def stop_team(self) -> None:
        """Stoppe das EventFixTeam"""
        if self.team:
            print("🛑 Stoppe EventFixTeam...")
            await self.team.stop()
            print("✅ EventFixTeam gestoppt!")
        else:
            print("⚠️  EventFixTeam ist nicht gestartet!")
    
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
        if not self.team:
            print("❌ EventFixTeam ist nicht gestartet!")
            return
        
        # Task Type konvertieren
        task_type_map = {
            "fix_code": FixTaskType.FIX_CODE,
            "migration": FixTaskType.MIGRATION,
            "test_fix": FixTaskType.TEST_FIX,
            "log_analysis": FixTaskType.LOG_ANALYSIS
        }
        
        fix_task_type = task_type_map.get(task_type.lower())
        if not fix_task_type:
            print(f"❌ Ungültiger Task Type: {task_type}")
            print(f"   Gültige Werte: {', '.join(task_type_map.keys())}")
            return
        
        # Priority konvertieren
        priority_map = {
            "low": FixPriority.LOW,
            "medium": FixPriority.MEDIUM,
            "high": FixPriority.HIGH,
            "critical": FixPriority.CRITICAL
        }
        
        fix_priority = priority_map.get(priority.lower())
        if not fix_priority:
            print(f"❌ Ungültige Priority: {priority}")
            print(f"   Gültige Werte: {', '.join(priority_map.keys())}")
            return
        
        # Task erstellen
        task = await self.team.create_fix_task(
            task_type=fix_task_type,
            priority=fix_priority,
            title=title,
            description=description,
            source=source,
            data=data or {}
        )
        
        print(f"✅ Task erstellt: {task.id}")
        print(f"   Type: {task.task_type.value}")
        print(f"   Priority: {task.priority.value}")
        print(f"   Status: {task.status.value}")
        print(f"   Title: {task.title}")
    
    async def list_tasks(self, status: Optional[str] = None) -> None:
        """Liste alle Tasks auf"""
        tasks = await self.file_write_tasks.list_pending_tasks()
        
        if not tasks:
            print("📋 Keine Tasks gefunden!")
            return
        
        # Filter nach Status
        if status:
            status_map = {
                "pending": FixStatus.PENDING,
                "in_progress": FixStatus.IN_PROGRESS,
                "completed": FixStatus.COMPLETED,
                "failed": FixStatus.FAILED
            }
            
            fix_status = status_map.get(status.lower())
            if fix_status:
                tasks = [t for t in tasks if t.get("status") == fix_status.value]
        
        print(f"📋 {len(tasks)} Task(s) gefunden:")
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
            print(f"❌ Task nicht gefunden: {task_id}")
            return
        
        print(f"📋 Task Details:")
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
        # Status konvertieren
        status_map = {
            "pending": FixStatus.PENDING,
            "in_progress": FixStatus.IN_PROGRESS,
            "completed": FixStatus.COMPLETED,
            "failed": FixStatus.FAILED
        }
        
        fix_status = status_map.get(status.lower())
        if not fix_status:
            print(f"❌ Ungültiger Status: {status}")
            print(f"   Gültige Werte: {', '.join(status_map.keys())}")
            return
        
        # Task aktualisieren
        success = await self.file_write_tasks.update_task_status(
            task_id=task_id,
            status=fix_status,
            result=result
        )
        
        if success:
            print(f"✅ Task {task_id} aktualisiert auf {status}")
        else:
            print(f"❌ Task {task_id} konnte nicht aktualisiert werden")
    
    async def delete_task(self, task_id: str) -> None:
        """Lösche einen Task"""
        success = await self.file_write_tasks.delete_task(task_id)
        
        if success:
            print(f"✅ Task {task_id} gelöscht")
        else:
            print(f"❌ Task {task_id} konnte nicht gelöscht werden")
    
    async def get_statistics(self) -> None:
        """Hole Statistiken"""
        stats = await self.file_write_tasks.get_task_statistics()
        
        print("📊 Task Statistiken:")
        print(f"Total: {stats.get('total', 0)}")
        print(f"Pending: {stats.get('pending', 0)}")
        print(f"In Progress: {stats.get('in_progress', 0)}")
        print(f"Completed: {stats.get('completed', 0)}")
        print(f"Failed: {stats.get('failed', 0)}")
    
    async def simulate_event(
        self,
        event_type: str,
        source: str,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Simuliere ein Event"""
        if not self.event_bus:
            print("❌ Event Bus ist nicht gestartet!")
            return
        
        # Event erstellen
        event = {
            "type": event_type,
            "source": source,
            "data": data or {},
            "timestamp": datetime.now().isoformat()
        }
        
        # Event publishen
        await self.event_bus.publish(event_type, event)
        
        print(f"✅ Event simuliert: {event_type}")
        print(f"   Source: {source}")
        print(f"   Data: {json.dumps(data, indent=2) if data else '{}'}")
    
    async def process_tasks(self, max_tasks: Optional[int] = None) -> None:
        """Verarbeite Tasks"""
        if not self.team:
            print("❌ EventFixTeam ist nicht gestartet!")
            return
        
        print(f"🔄 Verarbeite Tasks...")
        
        result = await self.team.process_tasks(max_tasks=max_tasks)
        
        print(f"✅ Tasks verarbeitet!")
        print(f"   Total: {result.total_tasks}")
        print(f"   Successful: {result.successful_tasks}")
        print(f"   Failed: {result.failed_tasks}")
        print(f"   Duration: {result.duration:.2f}s")
        
        if result.errors:
            print(f"   Errors: {len(result.errors)}")
            for error in result.errors:
                print(f"     - {error}")


async def main():
    """Main Funktion"""
    parser = argparse.ArgumentParser(
        description="EventFixTeam CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  # EventFixTeam starten
  python -m src.teams.event_fix_cli start
  
  # Task erstellen
  python -m src.teams.event_fix_cli create-task --type fix_code --priority high --title "Fix Bug" --description "Fix critical bug" --source "user"
  
  # Tasks auflisten
  python -m src.teams.event_fix_cli list-tasks
  
  # Task Details anzeigen
  python -m src.teams.event_fix_cli get-task --id <task-id>
  
  # Task Status aktualisieren
  python -m src.teams.event_fix_cli update-task --id <task-id> --status completed
  
  # Event simulieren
  python -m src.teams.event_fix_cli simulate-event --type error --source "docker" --data '{"container": "app", "error": "Crash"}'
  
  # Tasks verarbeiten
  python -m src.teams.event_fix_cli process-tasks
  
  # Statistiken anzeigen
  python -m src.teams.event_fix_cli statistics
  
  # EventFixTeam stoppen
  python -m src.teams.event_fix_cli stop
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Verfügbare Befehle")
    
    # Start Command
    start_parser = subparsers.add_parser("start", help="Starte das EventFixTeam")
    
    # Stop Command
    stop_parser = subparsers.add_parser("stop", help="Stoppe das EventFixTeam")
    
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
    
    # Simulate Event Command
    simulate_event_parser = subparsers.add_parser("simulate-event", help="Simuliere ein Event")
    simulate_event_parser.add_argument("--type", required=True, help="Event Type")
    simulate_event_parser.add_argument("--source", required=True, help="Event Source")
    simulate_event_parser.add_argument("--data", help="Event Data (JSON)")
    
    # Process Tasks Command
    process_tasks_parser = subparsers.add_parser("process-tasks", help="Verarbeite Tasks")
    process_tasks_parser.add_argument("--max-tasks", type=int, help="Maximale Anzahl von Tasks")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # CLI erstellen
    cli = EventFixCLI()
    
    # Befehle ausführen
    if args.command == "start":
        await cli.start_team()
    elif args.command == "stop":
        await cli.stop_team()
    elif args.command == "create-task":
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
    elif args.command == "simulate-event":
        data = json.loads(args.data) if args.data else None
        await cli.simulate_event(
            event_type=args.type,
            source=args.source,
            data=data
        )
    elif args.command == "process-tasks":
        await cli.process_tasks(max_tasks=args.max_tasks)


if __name__ == "__main__":
    asyncio.run(main())
