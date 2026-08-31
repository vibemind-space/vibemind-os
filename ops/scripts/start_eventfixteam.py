#!/usr/bin/env python3
"""
Start-Skript für das EventFixTeam System
Startet alle Komponenten: gRPC-Server, Agents und CLI
"""

import subprocess
import sys
import time
import signal
from pathlib import Path


class EventFixTeamLauncher:
    """Launcher für das EventFixTeam System"""
    
    def __init__(self):
        self.processes = []
        self.base_dir = Path(__file__).parent / "grpc_host"
    
    def start_grpc_server(self):
        """Startet den gRPC-Server"""
        print("Starte gRPC-Server...")
        server_script = self.base_dir / "grpc_server.py"
        
        process = subprocess.Popen(
            [sys.executable, str(server_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        self.processes.append(("gRPC-Server", process))
        
        # Warten auf Server-Start
        time.sleep(2)
        print("✓ gRPC-Server gestartet")
    
    def start_agents(self):
        """Startet alle Agents"""
        print("\nStarte Agents...")
        
        agents = [
            ("CodeWriterAgent", "code_writer_1"),
            ("DebuggerAgent", "debugger_1"),
            ("TesterAgent", "tester_1"),
            ("MigrationAgent", "migration_1"),
            ("LogAnalyzerAgent", "log_analyzer_1")
        ]
        
        for agent_class, agent_id in agents:
            agent_script = self.base_dir / "agents" / f"{agent_class.lower()}.py"
            
            if agent_script.exists():
                process = subprocess.Popen(
                    [sys.executable, str(agent_script)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                self.processes.append((f"Agent {agent_id}", process))
                print(f"✓ {agent_class} ({agent_id}) gestartet")
            else:
                print(f"✗ {agent_class} nicht gefunden: {agent_script}")
    
    def start_cli(self):
        """Startet die CLI"""
        print("\nStarte CLI...")
        cli_script = Path(__file__).parent / "eventfixteam_cli.py"
        
        if cli_script.exists():
            process = subprocess.Popen(
                [sys.executable, str(cli_script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.processes.append(("CLI", process))
            print("✓ CLI gestartet")
        else:
            print("✗ CLI nicht gefunden")
    
    def stop_all(self):
        """Stoppt alle Prozesse"""
        print("\nStoppe alle Prozesse...")
        
        for name, process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"✓ {name} gestoppt")
            except subprocess.TimeoutExpired:
                process.kill()
                print(f"✗ {name} erzwungen gestoppt")
            except Exception as e:
                print(f"✗ Fehler beim Stoppen von {name}: {e}")
    
    def run(self):
        """Startet das gesamte System"""
        print("=" * 60)
        print("EventFixTeam System Launcher")
        print("=" * 60)
        
        try:
            # gRPC-Server starten
            self.start_grpc_server()
            
            # Agents starten
            self.start_agents()
            
            # CLI starten
            self.start_cli()
            
            print("\n" + "=" * 60)
            print("System erfolgreich gestartet!")
            print("=" * 60)
            print("\nVerfügbare Komponenten:")
            print("  - gRPC-Server: localhost:50051")
            print("  - CLI: ./eventfixteam_cli.py")
            print("  - Test-Skript: ./test_grpc_system.py")
            print("\nDrücken Sie STRG+C zum Beenden...")
            
            # Warten auf Benutzer-Interrupt
            while True:
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n\nBeende System...")
            self.stop_all()
            print("\nSystem beendet.")
        except Exception as e:
            print(f"\nFehler: {e}")
            self.stop_all()
            sys.exit(1)


def main():
    """Hauptfunktion"""
    launcher = EventFixTeamLauncher()
    launcher.run()


if __name__ == "__main__":
    main()
