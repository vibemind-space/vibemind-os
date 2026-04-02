#!/usr/bin/env python3
"""
Test-Skript für die EventFixTeam CLI

Dieses Skript testet alle CLI Befehle.
"""

import asyncio
import subprocess
import sys
from pathlib import Path


def run_command(command: str) -> tuple[int, str, str]:
    """Führe einen CLI Befehl aus"""
    print(f"\n🔧 Ausführen: {command}")
    print("-" * 80)
    
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    return result.returncode, result.stdout, result.stderr


async def test_cli():
    """Teste alle CLI Befehle"""
    print("🧪 Teste EventFixTeam CLI")
    print("=" * 80)
    
    # 1. Hilfe anzeigen
    print("\n1️⃣  Teste Hilfe")
    run_command("python -m src.teams.event_fix_cli --help")
    
    # 2. EventFixTeam starten
    print("\n2️⃣  Teste Start")
    run_command("python -m src.teams.event_fix_cli start")
    
    # 3. Task erstellen
    print("\n3️⃣  Teste Create Task")
    run_command(
        'python -m src.teams.event_fix_cli create-task '
        '--type fix_code '
        '--priority high '
        '--title "Fix Bug in User Service" '
        '--description "Fix critical bug in user authentication" '
        '--source "user"'
    )
    
    # 4. Tasks auflisten
    print("\n4️⃣  Teste List Tasks")
    run_command("python -m src.teams.event_fix_cli list-tasks")
    
    # 5. Task Details anzeigen
    print("\n5️⃣  Teste Get Task")
    # Zuerst die Task ID aus der Liste holen
    _, output, _ = run_command("python -m src.teams.event_fix_cli list-tasks")
    
    # Task ID extrahieren (einfache Implementierung)
    task_id = None
    for line in output.split('\n'):
        if line.startswith('ID:'):
            task_id = line.split(':')[1].strip()
            break
    
    if task_id:
        run_command(f"python -m src.teams.event_fix_cli get-task --id {task_id}")
        
        # 6. Task Status aktualisieren
        print("\n6️⃣  Teste Update Task")
        run_command(
            f'python -m src.teams.event_fix_cli update-task '
            f'--id {task_id} '
            f'--status in_progress'
        )
        
        # 7. Task Status auf completed setzen
        print("\n7️⃣  Teste Update Task (Completed)")
        run_command(
            f'python -m src.teams.event_fix_cli update-task '
            f'--id {task_id} '
            f'--status completed '
            f'--result \'{{"fixed": true, "files_changed": ["app.py"]}}\''
        )
    
    # 8. Statistiken anzeigen
    print("\n8️⃣  Teste Statistics")
    run_command("python -m src.teams.event_fix_cli statistics")
    
    # 9. Event simulieren
    print("\n9️⃣  Teste Simulate Event")
    run_command(
        'python -m src.teams.event_fix_cli simulate-event '
        '--type error '
        '--source "docker" '
        '--data \'{"container": "app", "error": "Crash"}\''
    )
    
    # 10. Tasks auflisten (nach Event)
    print("\n🔟 Teste List Tasks (nach Event)")
    run_command("python -m src.teams.event_fix_cli list-tasks")
    
    # 11. Tasks verarbeiten
    print("\n1️⃣1️⃣  Teste Process Tasks")
    run_command("python -m src.teams.event_fix_cli process-tasks")
    
    # 12. Statistiken anzeigen (nach Verarbeitung)
    print("\n1️⃣2️⃣  Teste Statistics (nach Verarbeitung)")
    run_command("python -m src.teams.event_fix_cli statistics")
    
    # 13. EventFixTeam stoppen
    print("\n1️⃣3️⃣  Teste Stop")
    run_command("python -m src.teams.event_fix_cli stop")
    
    print("\n✅ Alle Tests abgeschlossen!")
    print("=" * 80)


async def test_specific_commands():
    """Teste spezifische CLI Befehle"""
    print("🧪 Teste spezifische CLI Befehle")
    print("=" * 80)
    
    # 1. EventFixTeam starten
    print("\n1️⃣  Starte EventFixTeam")
    run_command("python -m src.teams.event_fix_cli start")
    
    # 2. Mehrere Tasks erstellen
    print("\n2️⃣  Erstelle mehrere Tasks")
    
    # Fix Code Task
    run_command(
        'python -m src.teams.event_fix_cli create-task '
        '--type fix_code '
        '--priority high '
        '--title "Fix Bug in User Service" '
        '--description "Fix critical bug in user authentication" '
        '--source "user"'
    )
    
    # Migration Task
    run_command(
        'python -m src.teams.event_fix_cli create-task '
        '--type migration '
        '--priority medium '
        '--title "Migrate Database Schema" '
        '--description "Migrate user table to new schema" '
        '--source "database"'
    )
    
    # Test Fix Task
    run_command(
        'python -m src.teams.event_fix_cli create-task '
        '--type test_fix '
        '--priority high '
        '--title "Fix Failing Tests" '
        '--description "Fix failing unit tests in auth module" '
        '--source "test"'
    )
    
    # Log Analysis Task
    run_command(
        'python -m src.teams.event_fix_cli create-task '
        '--type log_analysis '
        '--priority low '
        '--title "Analyze Performance Logs" '
        '--description "Analyze performance logs for bottlenecks" '
        '--source "monitoring"'
    )
    
    # 3. Tasks auflisten
    print("\n3️⃣  Liste alle Tasks auf")
    run_command("python -m src.teams.event_fix_cli list-tasks")
    
    # 4. Tasks nach Status filtern
    print("\n4️⃣  Filtere Tasks nach Status")
    run_command("python -m src.teams.event_fix_cli list-tasks --status pending")
    run_command("python -m src.teams.event_fix_cli list-tasks --status in_progress")
    run_command("python -m src.teams.event_fix_cli list-tasks --status completed")
    
    # 5. Statistiken anzeigen
    print("\n5️⃣  Zeige Statistiken")
    run_command("python -m src.teams.event_fix_cli statistics")
    
    # 6. EventFixTeam stoppen
    print("\n6️⃣  Stoppe EventFixTeam")
    run_command("python -m src.teams.event_fix_cli stop")
    
    print("\n✅ Alle spezifischen Tests abgeschlossen!")
    print("=" * 80)


async def test_event_simulation():
    """Teste Event Simulation"""
    print("🧪 Teste Event Simulation")
    print("=" * 80)
    
    # 1. EventFixTeam starten
    print("\n1️⃣  Starte EventFixTeam")
    run_command("python -m src.teams.event_fix_cli start")
    
    # 2. Error Event simulieren
    print("\n2️⃣  Simuliere Error Event")
    run_command(
        'python -m src.teams.event_fix_cli simulate-event '
        '--type error '
        '--source "docker" '
        '--data \'{"container": "app", "error": "Crash", "stack_trace": "..."}\''
    )
    
    # 3. Crash Event simulieren
    print("\n3️⃣  Simuliere Crash Event")
    run_command(
        'python -m src.teams.event_fix_cli simulate-event '
        '--type crash '
        '--source "app" '
        '--data \'{"service": "user-service", "error": "Segmentation fault"}\''
    )
    
    # 4. Performance Event simulieren
    print("\n4️⃣  Simuliere Performance Event")
    run_command(
        'python -m src.teams.event_fix_cli simulate-event '
        '--type performance '
        '--source "monitoring" '
        '--data \'{"metric": "response_time", "value": 5000, "threshold": 1000}\''
    )
    
    # 5. Test Failure Event simulieren
    print("\n5️⃣  Simuliere Test Failure Event")
    run_command(
        'python -m src.teams.event_fix_cli simulate-event '
        '--type test_failure '
        '--source "test" '
        '--data \'{"test": "test_auth", "error": "AssertionError"}\''
    )
    
    # 6. Migration Event simulieren
    print("\n6️⃣  Simuliere Migration Event")
    run_command(
        'python -m src.teams.event_fix_cli simulate-event '
        '--type migration '
        '--source "database" '
        '--data \'{"table": "users", "operation": "alter"}\''
    )
    
    # 7. Tasks auflisten
    print("\n7️⃣  Liste alle Tasks auf")
    run_command("python -m src.teams.event_fix_cli list-tasks")
    
    # 8. Statistiken anzeigen
    print("\n8️⃣  Zeige Statistiken")
    run_command("python -m src.teams.event_fix_cli statistics")
    
    # 9. EventFixTeam stoppen
    print("\n9️⃣  Stoppe EventFixTeam")
    run_command("python -m src.teams.event_fix_cli stop")
    
    print("\n✅ Event Simulation Tests abgeschlossen!")
    print("=" * 80)


async def main():
    """Main Funktion"""
    print("🚀 EventFixTeam CLI Test-Skript")
    print("=" * 80)
    
    # Prüfen, ob ein Argument übergeben wurde
    if len(sys.argv) > 1:
        test_type = sys.argv[1]
        
        if test_type == "all":
            await test_cli()
        elif test_type == "specific":
            await test_specific_commands()
        elif test_type == "events":
            await test_event_simulation()
        else:
            print(f"❌ Unbekannter Test-Typ: {test_type}")
            print("   Gültige Werte: all, specific, events")
            sys.exit(1)
    else:
        print("\nVerwendung:")
        print("  python src/teams/test_cli.py all          - Teste alle CLI Befehle")
        print("  python src/teams/test_cli.py specific    - Teste spezifische CLI Befehle")
        print("  python src/teams/test_cli.py events      - Teste Event Simulation")
        print("\nBeispiel:")
        print("  python src/teams/test_cli.py all")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
