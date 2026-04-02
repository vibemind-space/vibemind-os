"""
EventFixTeam Main Entry Point
Startet und verwaltet das EventFixTeam System mit gRPC-basierter Agent-Architektur.
"""

import asyncio
import argparse
import logging
import signal
import sys
from pathlib import Path
from typing import List, Dict, Any

# Importiere lokale Module
from grpc_client import EventFixTeamClient
from agents import create_agent

# Konfiguration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EventFixTeamOrchestrator:
    """Orchestrator für das EventFixTeam System"""
    
    def __init__(self, server_address: str = "localhost:50051"):
        self.server_address = server_address
        self.grpc_client = None
        self.agents: List[Any] = []
        self.running = False
        
    async def initialize(self):
        """Initialisiert das EventFixTeam System"""
        logger.info("Initialisiere EventFixTeam System...")
        
        # Initialisiere gRPC Client
        self.grpc_client = EventFixTeamClient(self.server_address)
        await self.grpc_client.connect()
        
        logger.info("EventFixTeam System initialisiert")
    
    async def create_agents(self, agent_configs: List[Dict[str, Any]]):
        """Erstellt Agents basierend auf der Konfiguration"""
        logger.info(f"Erstelle {len(agent_configs)} Agents...")
        
        for config in agent_configs:
            try:
                agent = await create_agent(
                    agent_type=config['type'],
                    agent_id=config['id'],
                    grpc_client=self.grpc_client
                )
                self.agents.append(agent)
                logger.info(f"Agent {config['id']} ({config['type']}) erstellt")
            except Exception as e:
                logger.error(f"Fehler beim Erstellen von Agent {config['id']}: {e}")
    
    async def start_agents(self):
        """Startet alle Agents"""
        logger.info("Starte Agents...")
        
        tasks = []
        for agent in self.agents:
            task = asyncio.create_task(agent.run())
            tasks.append(task)
        
        self.running = True
        logger.info(f"{len(self.agents)} Agents gestartet")
        
        return tasks
    
    async def stop(self):
        """Stoppt das EventFixTeam System"""
        logger.info("Stoppe EventFixTeam System...")
        
        self.running = False
        
        # Schließe gRPC Verbindung
        if self.grpc_client:
            await self.grpc_client.disconnect()
        
        logger.info("EventFixTeam System gestoppt")
    
    async def run(self, agent_configs: List[Dict[str, Any]]):
        """Haupt-Schleife des Orchestrators"""
        try:
            # Initialisiere
            await self.initialize()
            
            # Erstelle Agents
            await self.create_agents(agent_configs)
            
            # Starte Agents
            agent_tasks = await self.start_agents()
            
            # Warte auf Shutdown-Signal
            while self.running:
                await asyncio.sleep(1)
            
            # Stoppe Agents
            for task in agent_tasks:
                task.cancel()
            
            # Stoppe System
            await self.stop()
            
        except Exception as e:
            logger.error(f"Fehler in Orchestrator: {e}")
            await self.stop()
            raise


def get_default_agent_configs() -> List[Dict[str, Any]]:
    """Gibt die Standard-Agent-Konfiguration zurück"""
    return [
        {
            "id": "code_writer_1",
            "type": "code_writer"
        },
        {
            "id": "debugger_1",
            "type": "debugger"
        },
        {
            "id": "tester_1",
            "type": "tester"
        }
    ]


def load_agent_configs(config_file: str) -> List[Dict[str, Any]]:
    """Lädt Agent-Konfigurationen aus einer Datei"""
    import json
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            return config.get('agents', [])
    except Exception as e:
        logger.error(f"Fehler beim Laden der Konfiguration: {e}")
        return get_default_agent_configs()


async def main():
    """Hauptfunktion"""
    parser = argparse.ArgumentParser(
        description="EventFixTeam - gRPC-basiertes Agent-System für Event-Fixes"
    )
    parser.add_argument(
        '--server',
        default='localhost:50051',
        help='gRPC Server Adresse (default: localhost:50051)'
    )
    parser.add_argument(
        '--config',
        help='Pfad zur Agent-Konfigurationsdatei (JSON)'
    )
    parser.add_argument(
        '--agents',
        nargs='+',
        help='Liste der zu startenden Agent-Typen (code_writer, debugger, tester)'
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Log-Level (default: INFO)'
    )
    
    args = parser.parse_args()
    
    # Setze Log-Level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Erstelle Orchestrator
    orchestrator = EventFixTeamOrchestrator(args.server)
    
    # Lade Agent-Konfigurationen
    if args.config:
        agent_configs = load_agent_configs(args.config)
    elif args.agents:
        # Erstelle Konfigurationen basierend auf CLI-Argumenten
        agent_configs = []
        for i, agent_type in enumerate(args.agents):
            agent_configs.append({
                "id": f"{agent_type}_{i+1}",
                "type": agent_type
            })
    else:
        # Verwende Standard-Konfiguration
        agent_configs = get_default_agent_configs()
    
    # Setup Shutdown-Handler
    def signal_handler(signum, frame):
        logger.info(f"Signal {signum} empfangen, stoppe System...")
        orchestrator.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Starte Orchestrator
    try:
        await orchestrator.run(agent_configs)
    except KeyboardInterrupt:
        logger.info("Keyboard Interrupt empfangen")
        await orchestrator.stop()
    except Exception as e:
        logger.error(f"Unerwarteter Fehler: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
