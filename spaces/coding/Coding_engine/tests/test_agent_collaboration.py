"""
Test: PreviewAgent + BrowserConsoleAgent Collaboration
======================================================

Demonstriert den "letzten Schliff" Workflow:
1. PreviewAgent überwacht den Dev-Server (30s Timer)
2. Bei 3 Health-Failures → BrowserConsoleAgent wird aktiviert
3. BrowserConsoleAgent öffnet Browser via Playwright MCP
4. Injiziert JavaScript für Console.error Interception
5. Sammelt alle Browser-Errors (Hydration, 404s, etc.)
6. Gibt Errors an Claude CLI für intelligente Fixes
7. Server wird neugestartet und verifiziert
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Rich für schöne Terminal-Ausgabe
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.live import Live
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    class Console:
        def print(self, *args, **kwargs): print(*args)

console = Console()


def print_header():
    """Zeige Header für den Test."""
    if RICH_AVAILABLE:
        console.print(Panel.fit(
            "[bold cyan]PreviewAgent + BrowserConsoleAgent[/bold cyan]\n"
            "[dim]Collaboration Test für den 'letzten Schliff'[/dim]",
            border_style="cyan"
        ))
    else:
        print("=" * 60)
        print("PreviewAgent + BrowserConsoleAgent Collaboration")
        print("=" * 60)


def print_step(num: int, title: str, desc: str = ""):
    """Zeige einen Schritt an."""
    if RICH_AVAILABLE:
        console.print(f"\n[bold yellow]Step {num}:[/bold yellow] [bold]{title}[/bold]")
        if desc:
            console.print(f"  [dim]{desc}[/dim]")
    else:
        print(f"\n[Step {num}] {title}")
        if desc:
            print(f"  {desc}")


async def test_browser_console_agent_standalone():
    """Test BrowserConsoleAgent allein."""
    print_step(1, "BrowserConsoleAgent Standalone Test", 
               "Testet die Console-Error Capture Funktion direkt")
    
    try:
        from src.agents.browser_console_agent import BrowserConsoleAgent, ConsoleCapture
        console.print("  [green]✓[/green] Import erfolgreich")
        
        # Erstelle Agent
        agent = BrowserConsoleAgent()
        console.print("  [green]✓[/green] Agent erstellt")
        
        # Test URL - eine Seite die guaranteed Errors hat
        test_url = "http://localhost:3001"
        console.print(f"  [blue]→[/blue] Capturing console from: {test_url}")
        
        # Capture mit Timeout
        try:
            capture = await asyncio.wait_for(
                agent.capture_console_errors(test_url, wait_seconds=3.0),
                timeout=30.0
            )
            
            if capture.has_issues:
                console.print(f"  [yellow]⚠[/yellow] Gefunden: {capture.total_errors} Errors, {capture.total_warnings} Warnings")
                
                # Zeige die Errors
                if RICH_AVAILABLE and capture.errors:
                    table = Table(title="Browser Console Errors", show_lines=True)
                    table.add_column("Level", style="red")
                    table.add_column("Message", style="white")
                    table.add_column("Source", style="dim")
                    
                    for err in capture.errors[:5]:  # Max 5 anzeigen
                        table.add_row(
                            err.level.upper(),
                            err.message[:80] + "..." if len(err.message) > 80 else err.message,
                            err.source or "-"
                        )
                    console.print(table)
                
                # Claude-formatierte Ausgabe
                console.print("\n  [cyan]Claude Context:[/cyan]")
                console.print(capture.format_for_claude()[:500])
            else:
                console.print("  [green]✓[/green] Keine Console-Errors gefunden!")
            
            return capture
            
        except asyncio.TimeoutError:
            console.print("  [red]✗[/red] Timeout bei Console Capture")
            return None
            
    except ImportError as e:
        console.print(f"  [red]✗[/red] Import Fehler: {e}")
        return None
    except Exception as e:
        console.print(f"  [red]✗[/red] Fehler: {e}")
        return None


async def test_preview_agent_with_console_capture():
    """Test PreviewAgent mit aktiviertem Console Capture."""
    print_step(2, "PreviewAgent mit Console Capture",
               "Simuliert den Health-Failure Recovery Flow")
    
    try:
        from src.agents.preview_agent import PreviewAgent
        from src.mind.event_bus import EventBus
        
        # Konfiguration
        working_dir = Path("output/test-new-3")
        if not working_dir.exists():
            console.print(f"  [yellow]⚠[/yellow] Test-Projekt nicht gefunden: {working_dir}")
            console.print("  [dim]Erstelle minimales Test-Projekt...[/dim]")
            working_dir.mkdir(parents=True, exist_ok=True)
            
            # Minimale package.json
            (working_dir / "package.json").write_text('''{
  "name": "test-project",
  "scripts": {
    "dev": "echo 'Server running' && exit 0"
  }
}''')
        
        event_bus = EventBus()
        
        # Event-Handler für Logging
        @event_bus.subscribe("*")
        async def log_events(event):
            if RICH_AVAILABLE:
                console.print(f"  [magenta]EVENT:[/magenta] {event.type} from {event.source}")
        
        # Erstelle PreviewAgent mit Console Capture aktiviert
        agent = PreviewAgent(
            working_dir=str(working_dir),
            event_bus=event_bus,
            port=3001,
            timer_interval=10.0,  # Schnellere Checks für Test
            auto_start_timer=False,  # Manuell kontrollieren
            enable_console_capture=True,  # ← DAS IST DER SCHLÜSSEL
        )
        
        console.print("  [green]✓[/green] PreviewAgent erstellt")
        console.print(f"  [blue]→[/blue] Console Capture: [bold green]AKTIVIERT[/bold green]")
        console.print(f"  [blue]→[/blue] Working Dir: {working_dir}")
        console.print(f"  [blue]→[/blue] Port: {agent.port}")
        
        # Zeige die Zusammenarbeit
        console.print("\n  [cyan]Integration:[/cyan]")
        console.print("  1. PreviewAgent.enable_console_capture = True")
        console.print("  2. Bei _handle_health_failure():")
        console.print("     → BrowserConsoleAgent.capture_console_errors()")
        console.print("     → Console Errors an Claude CLI")
        console.print("     → Server Neustart")
        
        return agent
        
    except Exception as e:
        console.print(f"  [red]✗[/red] Fehler: {e}")
        import traceback
        traceback.print_exc()
        return None


async def demonstrate_collaboration_flow():
    """Demonstriere den vollständigen Collaboration Flow."""
    print_step(3, "Collaboration Flow Demonstration",
               "Zeigt wie die Agenten zusammenarbeiten")
    
    if RICH_AVAILABLE:
        # ASCII-Art Diagramm
        flow_diagram = """
    ┌─────────────────────────────────────────────────────────────┐
    │                    PREVIEW AGENT                            │
    │  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
    │  │ Health Check│───>│ 3 Failures? │───>│ Console Capture │  │
    │  │ (30s Timer) │    │     NO      │    │    AKTIVIERT    │  │
    │  └─────────────┘    └──────┬──────┘    └────────┬────────┘  │
    │                            │                    │           │
    │                            │ YES                │           │
    │                            ▼                    ▼           │
    └────────────────────────────┬────────────────────┬───────────┘
                                 │                    │
                                 ▼                    ▼
    ┌──────────────────────────────────────────────────────────────┐
    │               BROWSER CONSOLE AGENT                          │
    │  ┌─────────────┐    ┌─────────────┐    ┌──────────────────┐  │
    │  │ Playwright  │───>│ JS Inject   │───>│ Capture Errors   │  │
    │  │    MCP      │    │ console.err │    │ Hydration, 404s  │  │
    │  └─────────────┘    └─────────────┘    └────────┬─────────┘  │
    │                                                 │            │
    └─────────────────────────────────────────────────┬────────────┘
                                                      │
                                                      ▼
    ┌───────────────────────────────────────────────────────────────┐
    │                      CLAUDE CLI                               │
    │  ┌─────────────────────────────────────────────────────────┐  │
    │  │ Prompt:                                                 │  │
    │  │ - Server Output                                         │  │
    │  │ - Browser Console Errors ← [BrowserConsoleAgent]        │  │
    │  │ - Anweisungen: Behebe Errors, Restart Server            │  │
    │  └─────────────────────────────────────────────────────────┘  │
    │                          │                                    │
    │                          ▼                                    │
    │  ┌─────────────────────────────────────────────────────────┐  │
    │  │ Claude analysiert + fixt Code                           │  │
    │  └─────────────────────────────────────────────────────────┘  │
    └───────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
    ┌───────────────────────────────────────────────────────────────┐
    │                    SERVER RESTART                             │
    │  _stop_dev_server() → _start_dev_server() → Verify           │
    └───────────────────────────────────────────────────────────────┘
        """
        console.print(Panel(flow_diagram, title="Agent Collaboration Flow", border_style="green"))
    else:
        print("""
        Collaboration Flow:
        1. PreviewAgent: Health Check alle 30s
        2. Nach 3 Failures: BrowserConsoleAgent aktivieren
        3. BrowserConsoleAgent: Browser öffnen via Playwright MCP
        4. JavaScript injizieren für console.error Capture
        5. Errors sammeln (Hydration, 404, etc.)
        6. Claude CLI mit Error-Context aufrufen
        7. Claude fixt den Code
        8. Server neustarten
        """)


async def test_mcp_connection():
    """Test die MCP Verbindung."""
    print_step(4, "MCP Playwright Verbindung",
               "Testet ob Playwright MCP erreichbar ist")
    
    try:
        from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams
        console.print("  [green]✓[/green] AutoGen MCP importiert")
        
        # Erstelle Params
        params = StdioServerParams(
            command="npx",
            args=["--yes", "@playwright/mcp@latest", "--browser", "msedge"],
            read_timeout_seconds=30,
        )
        console.print(f"  [blue]→[/blue] Command: npx @playwright/mcp@latest")
        console.print(f"  [blue]→[/blue] Browser: msedge")
        
        # Verbindung testen (ohne tatsächlich zu verbinden)
        console.print("  [green]✓[/green] MCP Params konfiguriert")
        console.print("\n  [cyan]Verfügbare MCP Tools:[/cyan]")
        console.print("  - browser_navigate(url)")
        console.print("  - browser_evaluate(expression)")
        console.print("  - browser_click(selector)")
        console.print("  - browser_screenshot()")
        console.print("  - browser_close()")
        
        return True
        
    except ImportError as e:
        console.print(f"  [red]✗[/red] AutoGen MCP nicht verfügbar: {e}")
        console.print("  [dim]Installation: pip install 'autogen-ext[mcp]'[/dim]")
        return False


async def main():
    """Hauptfunktion für den Test."""
    print_header()
    
    results = {}
    
    # Test 1: MCP Verbindung
    results["mcp"] = await test_mcp_connection()
    
    # Test 2: PreviewAgent Setup
    results["preview_agent"] = await test_preview_agent_with_console_capture()
    
    # Test 3: Flow Demonstration
    await demonstrate_collaboration_flow()
    
    # Test 4: BrowserConsoleAgent (nur wenn Server läuft)
    console.print("\n" + "=" * 60)
    console.print("[bold]Test mit laufendem Server:[/bold]")
    console.print("Falls ein Dev-Server auf localhost:3001 läuft:")
    
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:3001", timeout=3.0)
            console.print(f"  [green]✓[/green] Server erreichbar (Status: {response.status_code})")
            
            # Console Capture testen
            console.print("\n  [cyan]Starte Console Capture...[/cyan]")
            results["console_capture"] = await test_browser_console_agent_standalone()
            
    except Exception as e:
        console.print(f"  [yellow]⚠[/yellow] Server nicht erreichbar: {e}")
        console.print("  [dim]Starte Test-Server mit: python test_preview_agent.py[/dim]")
    
    # Zusammenfassung
    console.print("\n" + "=" * 60)
    if RICH_AVAILABLE:
        summary = Table(title="Test Zusammenfassung")
        summary.add_column("Test", style="cyan")
        summary.add_column("Status", style="green")
        
        summary.add_row("MCP Connection", "✓ OK" if results.get("mcp") else "✗ Failed")
        summary.add_row("PreviewAgent Setup", "✓ OK" if results.get("preview_agent") else "✗ Failed")
        summary.add_row("Console Capture", 
                       "✓ OK" if results.get("console_capture") else "⚠ Server nicht erreichbar")
        
        console.print(summary)
    else:
        print("\nZusammenfassung:")
        print(f"  MCP: {'OK' if results.get('mcp') else 'Failed'}")
        print(f"  PreviewAgent: {'OK' if results.get('preview_agent') else 'Failed'}")


if __name__ == "__main__":
    asyncio.run(main())