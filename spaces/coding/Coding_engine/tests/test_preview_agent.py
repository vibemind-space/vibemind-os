"""
Test Script für den Preview-Agent.

Demonstriert:
1. PreviewAgent starten mit output/test-new-3
2. 30-Sekunden Timer Health-Checks
3. Status-Reporting
"""

import asyncio
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.preview_agent import PreviewAgent, PreviewState
from src.mind.event_bus import EventBus, Event, EventType


async def on_event(event: Event):
    """Event-Handler um alle Preview-Events zu loggen."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] EVENT: {event.type.value}")
    print(f"         Source: {event.source}")
    if event.data:
        for key, value in event.data.items():
            print(f"         {key}: {value}")
    print()


async def main():
    """Hauptfunktion - startet den Preview-Agent."""
    
    # Projekt-Pfad
    project_dir = Path(__file__).parent / "output" / "test-new-3"
    
    if not project_dir.exists():
        print(f"❌ Projekt nicht gefunden: {project_dir}")
        return
    
    print("=" * 60)
    print("🚀 Preview-Agent Test")
    print("=" * 60)
    print(f"📁 Projekt: {project_dir}")
    print(f"⏱️  Timer-Interval: 30 Sekunden")
    print()
    
    # EventBus erstellen und Events abonnieren
    event_bus = EventBus()
    event_bus.subscribe_all(on_event)
    
    # Preview-Agent erstellen
    agent = PreviewAgent(
        working_dir=str(project_dir),
        event_bus=event_bus,
        port=3001,  # Port 3001 verwenden
        timer_interval=30.0,  # 30 Sekunden Health-Checks
        auto_start_timer=True,
    )
    
    print("🔧 Preview-Agent erstellt")
    print()
    
    try:
        # Agent starten (installiert deps, buildet, startet server)
        print("▶️  Starte Preview-Agent...")
        print("-" * 60)
        
        success = await agent.start()
        
        print("-" * 60)
        
        if success:
            print("✅ Preview-Agent gestartet!")
            print()
            print(f"🌐 Preview URL: {agent.status.url}")
            print(f"📊 Status: {agent.status.state.value}")
            print()
            
            # Status anzeigen
            status = agent.get_status()
            print("📋 Aktueller Status:")
            for key, value in status.items():
                print(f"   {key}: {value}")
            
            print()
            print("=" * 60)
            print("🔄 Health-Checks laufen alle 30 Sekunden...")
            print("   Drücke Ctrl+C zum Beenden")
            print("=" * 60)
            
            # Laufen lassen bis Ctrl+C
            while True:
                await asyncio.sleep(10)
                
                # Status alle 10 Sekunden anzeigen
                status = agent.get_status()
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"[{timestamp}] Status: {status['state']} | Health Checks: {status['health_check_count']} | Failures: {status['consecutive_failures']}")
        else:
            print("❌ Preview-Agent konnte nicht gestartet werden")
            print(f"   Error: {agent.status.error}")
    
    except KeyboardInterrupt:
        print()
        print("⏹️  Beende Preview-Agent...")
    
    finally:
        await agent.stop()
        print("✅ Preview-Agent gestoppt")


if __name__ == "__main__":
    asyncio.run(main())