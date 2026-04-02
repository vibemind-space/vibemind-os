#!/usr/bin/env python3
from src.llm_config import get_model
"""
Chat Interface für den EventFix Orchestrator

Ermöglicht interaktive Konversation mit dem AutoGen-basierten Orchestrator.
Der Orchestrator kann MCP Tools aufrufen um Aufgaben auszuführen.

Usage:
    python chat_orchestrator.py
    python chat_orchestrator.py --model gpt-4o
"""
import asyncio
import sys
import os
import argparse
from datetime import datetime

# Setup paths
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(script_dir, "shared"))
sys.path.insert(0, os.path.join(script_dir, "grpc_host"))

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'


def print_header():
    print(f"\n{Colors.CYAN}{Colors.BOLD}")
    print("+----------------------------------------------------------+")
    print("|           EventFix Orchestrator Chat                     |")
    print("|                                                          |")
    print("|  Befehle:                                                |")
    print("|    /quit, /exit  - Chat beenden                          |")
    print("|    /status       - Orchestrator Status anzeigen          |")
    print("|    /workers      - Verfuegbare Worker anzeigen           |")
    print("|    /clear        - Bildschirm loeschen                   |")
    print("|    /help         - Diese Hilfe anzeigen                  |")
    print("+----------------------------------------------------------+")
    print(f"{Colors.END}\n")


def print_user_prompt():
    print(f"{Colors.GREEN}{Colors.BOLD}Du:{Colors.END} ", end="", flush=True)


def print_assistant(text: str):
    print(f"{Colors.BLUE}{Colors.BOLD}Orchestrator:{Colors.END} {text}")


def print_info(text: str):
    print(f"{Colors.DIM}[i] {text}{Colors.END}")


def print_error(text: str):
    print(f"{Colors.RED}[!] {text}{Colors.END}")


def print_tool_call(tool_name: str, args: dict):
    print(f"{Colors.YELLOW}  🔧 Tool: {tool_name}{Colors.END}")
    if args:
        args_str = str(args)[:100] + "..." if len(str(args)) > 100 else str(args)
        print(f"{Colors.DIM}     Args: {args_str}{Colors.END}")


def print_agent_message(source: str, content: str, is_streaming: bool = True):
    """Prints agent message with source indicator"""
    if not content.strip():
        return

    # Truncate very long content
    if len(content) > 1000:
        content = content[:1000] + "..."

    if source == "ReasoningAgent":
        icon = "🧠"
        color = Colors.CYAN
    elif source == "ValidatorAgent":
        icon = "✓"
        color = Colors.GREEN
    else:
        icon = "💬"
        color = Colors.BLUE

    if is_streaming:
        print(f"{color}{icon} [{source}]:{Colors.END}")
        print(f"   {content}")
    else:
        print(f"{color}{icon} {source}: {content[:200]}...{Colors.END}" if len(content) > 200 else f"{color}{icon} {source}: {content}{Colors.END}")


def print_tool_result(content: str):
    """Prints tool result"""
    if not content.strip():
        return
    # Truncate very long results
    if len(content) > 300:
        content = content[:300] + "..."
    print(f"{Colors.DIM}   📋 Result: {content}{Colors.END}")


def print_streaming_divider():
    print(f"{Colors.DIM}{'─' * 60}{Colors.END}")


async def main():
    parser = argparse.ArgumentParser(description="Chat mit EventFix Orchestrator")
    parser.add_argument("--model", default=get_model("mcp_standard"), help="Model zu verwenden")
    parser.add_argument("--stream", "-s", action="store_true", default=True,
                        help="Live-Streaming des Reasoning (default: aktiviert)")
    parser.add_argument("--no-stream", action="store_true",
                        help="Streaming deaktivieren")
    args = parser.parse_args()

    # Handle stream flag
    use_streaming = args.stream and not args.no_stream

    print_header()

    # Import orchestrator
    try:
        from autogen_orchestrator import EventFixOrchestrator, get_worker_registry
        print_info(f"Lade Orchestrator mit Model: {args.model}")
    except ImportError as e:
        print_error(f"Konnte Orchestrator nicht importieren: {e}")
        return

    # Initialize orchestrator
    orchestrator = EventFixOrchestrator(model=args.model)

    print_info("Initialisiere Orchestrator...")
    try:
        await orchestrator.initialize()
        status = orchestrator.get_status()
        print_info(f"Initialisiert! MCP Tools: {status['mcp_tools_loaded']}")
    except Exception as e:
        print_error(f"Initialisierung fehlgeschlagen: {e}")
        print_info("Orchestrator funktioniert trotzdem, aber ohne MCP Tools")

    # Show available workers
    try:
        registry = get_worker_registry()
        workers = registry.list_workers()
        print_info(f"Verfuegbare Worker: {len(workers)}")
    except Exception:
        pass

    print()
    if use_streaming:
        print_info("🔴 LIVE-MODUS: Reasoning wird in Echtzeit angezeigt")
    print_info("Bereit! Stelle deine Fragen oder gib Aufgaben ein.")
    print_info("Tipp: Der Orchestrator kann Dateien lesen/schreiben, Docker steuern, etc.")
    print()

    # Chat loop
    while True:
        try:
            print_user_prompt()
            user_input = input().strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                cmd = user_input.lower()

                if cmd in ["/quit", "/exit", "/q"]:
                    print_info("Auf Wiedersehen!")
                    break

                elif cmd == "/status":
                    status = orchestrator.get_status()
                    print_info(f"Initialized: {status['initialized']}")
                    print_info(f"Model: {status['model']}")
                    print_info(f"MCP Tools: {status['mcp_tools_loaded']}")
                    print_info(f"AutoGen MCP Available: {status['autogen_mcp_available']}")
                    continue

                elif cmd == "/workers":
                    try:
                        registry = get_worker_registry()
                        workers = registry.list_workers()
                        print_info(f"Verfuegbare Worker ({len(workers)}):")
                        for w in workers[:10]:
                            print(f"    - {w['name']}: Port {w['port']}")
                        if len(workers) > 10:
                            print(f"    ... und {len(workers) - 10} weitere")
                    except Exception as e:
                        print_error(f"Fehler: {e}")
                    continue

                elif cmd == "/clear":
                    os.system('cls' if os.name == 'nt' else 'clear')
                    print_header()
                    continue

                elif cmd == "/help":
                    print_header()
                    continue

                else:
                    print_error(f"Unbekannter Befehl: {user_input}")
                    continue

            # Execute task via orchestrator
            start_time = datetime.now()

            try:
                if use_streaming:
                    # Stream-Modus: Zeige Reasoning live
                    print()
                    print_streaming_divider()
                    step_count = 0
                    tool_count = 0
                    final_result = None

                    async for event in orchestrator.execute_task_stream(
                        task=user_input,
                        task_type="general"
                    ):
                        event_type = event.get("type", "")

                        if event_type == "task_started":
                            print_info(f"▶ Task gestartet: {event.get('task', '')}")

                        elif event_type == "agent_message":
                            source = event.get("source", "Unknown")
                            content = event.get("content", "")
                            print_agent_message(source, content, is_streaming=True)
                            step_count += 1

                        elif event_type == "tool_call":
                            tool_name = event.get("tool", "unknown")
                            arguments = event.get("arguments", {})
                            print_tool_call(tool_name, arguments)
                            tool_count += 1

                        elif event_type == "tool_result":
                            content = event.get("content", "")
                            print_tool_result(content)

                        elif event_type == "task_completed":
                            final_result = event.get("result", "")
                            duration_ms = event.get("duration_ms", 0)
                            print_streaming_divider()
                            print()
                            print_assistant(final_result or "Aufgabe erledigt.")
                            print()
                            print_info(f"✓ Abgeschlossen: {step_count} Steps, {tool_count} Tool Calls, {duration_ms/1000:.1f}s")

                        elif event_type == "task_failed":
                            error = event.get("error", "Unbekannter Fehler")
                            print_streaming_divider()
                            print_error(f"Fehler: {error}")

                else:
                    # Nicht-Streaming-Modus: Warte auf Ergebnis
                    print_info("Verarbeite...")

                    result = await orchestrator.execute_task(
                        task=user_input,
                        task_type="general"
                    )

                    duration = (datetime.now() - start_time).total_seconds()

                    # Show tool calls if any
                    if result.tool_calls:
                        print_info(f"Tool Calls ({len(result.tool_calls)}):")
                        for tc in result.tool_calls[:5]:
                            print_tool_call(tc.get("tool", "unknown"), tc.get("arguments", {}))
                        if len(result.tool_calls) > 5:
                            print_info(f"  ... und {len(result.tool_calls) - 5} weitere")

                    # Show result
                    print()
                    if result.status == "completed":
                        print_assistant(result.result or "Aufgabe erledigt.")
                    else:
                        print_error(f"Fehler: {result.error or 'Unbekannter Fehler'}")

                    print()
                    print_info(f"Steps: {result.steps}, Dauer: {duration:.1f}s")

            except Exception as e:
                print_error(f"Fehler bei Ausfuehrung: {e}")
                import traceback
                traceback.print_exc()

            print()

        except KeyboardInterrupt:
            print()
            print_info("Abgebrochen. /quit zum Beenden.")
            continue
        except EOFError:
            print_info("Auf Wiedersehen!")
            break


if __name__ == "__main__":
    asyncio.run(main())
