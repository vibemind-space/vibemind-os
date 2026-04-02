#!/usr/bin/env python3
"""
MoireTracker_v2 - Society of Mind Desktop Agent

Nutzt das AutoGen SocietyOfMind Pattern für hierarchische Agent-Teams:
- PlanningTeam: Planner + Critic iterieren bis APPROVE
- ExecutionAgent: Führt Aktionen mit Tools aus
- ReflectionTeam: VisionAnalyzer + GoalChecker prüfen Fortschritt

Usage:
    python main_society.py --task "Öffne Word und erstelle ein neues Dokument"
    python main_society.py  # Interaktiver Modus
"""

import asyncio
import argparse
import logging
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Import Agents
from agents.society_orchestrator import (
    SocietyOfMindOrchestrator,
    get_society_orchestrator,
    HAS_AUTOGEN_AGENTCHAT
)
from agents.interaction import get_interaction_agent
from bridge.websocket_client import MoireWebSocketClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SocietyDesktopAgent:
    """
    Desktop Agent mit SocietyOfMind Pattern.
    
    Kombiniert:
    - MoireServer für Screen-State und Screenshots
    - AutoGen Teams für hierarchische Planung/Reflection
    - pyautogui für Desktop-Automation
    """
    
    def __init__(self, model_name: str = None):
        if model_name is None:
            from llm_config import get_model as _get_model
            model_name = _get_model("desktop_reasoning")
        self.model_name = model_name
        
        # Clients
        self.moire_client: MoireWebSocketClient = None
        self.interaction_agent = None
        self.orchestrator: SocietyOfMindOrchestrator = None
        
        # Config
        self.moire_host = os.getenv("MOIRE_HOST", "localhost")
        self.moire_port = int(os.getenv("MOIRE_PORT", "8765"))
    
    async def initialize(self) -> bool:
        """Initialisiert alle Komponenten."""
        logger.info("🚀 Initialisiere Society Desktop Agent...")
        
        # 1. Prüfe AutoGen
        if not HAS_AUTOGEN_AGENTCHAT:
            logger.error("❌ autogen-agentchat nicht installiert!")
            logger.error("   Installiere mit: pip install autogen-agentchat autogen-ext[openai]")
            return False
        
        # 2. Prüfe API Key
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("❌ Kein API Key gefunden!")
            logger.error("   Setze OPENROUTER_API_KEY oder OPENAI_API_KEY in .env")
            return False
        
        # 3. Verbinde MoireServer
        try:
            self.moire_client = MoireWebSocketClient(
                host=self.moire_host,
                port=self.moire_port
            )
            connected = await self.moire_client.connect()
            
            if connected:
                logger.info(f"✓ MoireServer verbunden ({self.moire_host}:{self.moire_port})")
            else:
                logger.warning("⚠ MoireServer nicht verbunden - Screenshots nicht verfügbar")
        except Exception as e:
            logger.warning(f"⚠ MoireServer Verbindung fehlgeschlagen: {e}")
            self.moire_client = None
        
        # 4. Interaction Agent
        self.interaction_agent = get_interaction_agent()
        logger.info("✓ Interaction Agent initialisiert")
        
        # 5. Society Orchestrator
        self.orchestrator = get_society_orchestrator(
            moire_client=self.moire_client,
            interaction_agent=self.interaction_agent,
            model_name=self.model_name
        )
        logger.info("✓ SocietyOfMind Orchestrator initialisiert")
        
        return True
    
    async def execute_task(self, task: str, max_rounds: int = 20) -> dict:
        """
        Führt einen Task mit dem SocietyOfMind Pattern aus.
        
        Args:
            task: Der auszuführende Task
            max_rounds: Maximale Plan-Execute-Reflect Zyklen
            
        Returns:
            Dict mit Ergebnis und Details
        """
        if not self.orchestrator:
            return {"success": False, "error": "Agent nicht initialisiert"}
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📋 TASK: {task}")
        logger.info(f"{'='*60}\n")
        
        result = await self.orchestrator.execute_task(task, max_rounds=max_rounds)
        
        # Log Ergebnis
        logger.info(f"\n{'='*60}")
        if result["success"]:
            logger.info(f"✅ ERFOLG nach {len(result['rounds'])} Runde(n)")
        else:
            logger.info(f"❌ FEHLGESCHLAGEN nach {len(result['rounds'])} Runde(n)")
        
        if result.get("error"):
            logger.info(f"   Fehler: {result['error']}")
        logger.info(f"{'='*60}\n")
        
        return result
    
    async def interactive_mode(self):
        """Interaktiver Modus für Task-Eingabe."""
        print("\n" + "="*60)
        print("🤖 Society of Mind Desktop Agent")
        print("="*60)
        print("\nBefehle:")
        print("  - Gib einen Task ein und drücke Enter")
        print("  - 'status' zeigt den aktuellen Status")
        print("  - 'exit' oder 'quit' beendet den Agent")
        print("="*60 + "\n")
        
        while True:
            try:
                task = input("\n📝 Task: ").strip()
                
                if not task:
                    continue
                
                if task.lower() in ["exit", "quit", "q"]:
                    print("\n👋 Auf Wiedersehen!")
                    break
                
                if task.lower() == "status":
                    status = self.orchestrator.get_status()
                    print(f"\n📊 Status:")
                    print(f"   MoireServer: {'✓' if status['has_moire_client'] else '✗'}")
                    print(f"   Interaction: {'✓' if status['has_interaction_agent'] else '✗'}")
                    print(f"   Model: {status['model']}")        
                    continue
                
                # Task ausführen
                result = await self.execute_task(task)
                
                # Zusammenfassung
                print(f"\n📊 Zusammenfassung:")
                print(f"   Erfolg: {'✓' if result['success'] else '✗'}")
                print(f"   Runden: {len(result['rounds'])}")
                
                for i, round_data in enumerate(result['rounds'], 1):
                    print(f"\n   Runde {i}:")
                    planning = round_data.get('planning', '')[:100]
                    print(f"     Plan: {planning}...")
                    
            except KeyboardInterrupt:
                print("\n\n👋 Unterbrochen. Auf Wiedersehen!")
                break
            except Exception as e:
                logger.error(f"Fehler: {e}")
    
    async def cleanup(self):
        """Räumt Ressourcen auf."""
        if self.moire_client:
            try:
                await self.moire_client.disconnect()
            except:
                pass


async def main():
    """Hauptfunktion."""
    parser = argparse.ArgumentParser(
        description="Society of Mind Desktop Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python main_society.py --task "Öffne den Windows Explorer"
  python main_society.py --task "Starte Word und schreibe 'Hallo Welt'"
  python main_society.py  # Interaktiver Modus
        """
    )
    parser.add_argument(
        "--task", "-t",
        type=str,
        help="Task der ausgeführt werden soll"
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=None,
        help="Model für die Agents (default: from llm_models.yml desktop_reasoning)"
    )
    parser.add_argument(
        "--max-rounds", "-r",
        type=int,
        default=20,
        help="Maximale Plan-Execute-Reflect Zyklen (default: 20)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose Output"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Agent initialisieren
    agent = SocietyDesktopAgent(model_name=args.model)
    
    if not await agent.initialize():
        print("\n❌ Agent konnte nicht initialisiert werden!")
        return
    
    try:
        if args.task:
            # Einzelner Task
            result = await agent.execute_task(args.task, max_rounds=args.max_rounds)
            
            # Exit Code basierend auf Erfolg
            sys.exit(0 if result["success"] else 1)
        else:
            # Interaktiver Modus
            await agent.interactive_mode()
    finally:
        await agent.cleanup()


if __name__ == "__main__":
    asyncio.run(main())