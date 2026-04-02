"""
MoireTracker AutoGen Desktop Agent System V2

Entry-Point für das verbesserte Event-driven Agent System:
- Event Queue für kontinuierliche Task-Verarbeitung
- Reasoning Agent mit Claude Sonnet 4
- Action Validation mit Timeout
- MoireServer Integration
"""

import asyncio
import argparse
import logging
import signal
import sys
import os
import time
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# Load environment
load_dotenv()

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


async def main(task: Optional[str] = None, interactive: bool = True):
    """
    Hauptfunktion des Agent-Systems.
    
    Args:
        task: Optionaler Task zum sofortigen Ausführen
        interactive: Ob interaktiver Modus aktiviert sein soll
    """
    logger.info("=" * 60)
    logger.info("MoireTracker AutoGen Agent System V2")
    logger.info("=" * 60)
    
    # Import components
    from agents.orchestrator_v2 import get_orchestrator_v2, shutdown_orchestrator
    from agents.interaction import get_interaction_agent
    from bridge.websocket_client import MoireWebSocketClient
    from core.event_queue import TaskStatus
    
    # Initialize components
    orchestrator = get_orchestrator_v2()
    interaction = get_interaction_agent()
    
    # WebSocket Client für MoireServer
    moire_host = os.getenv('MOIRE_HOST', 'localhost')
    moire_port = int(os.getenv('MOIRE_PORT', '8765'))
    moire_client = MoireWebSocketClient(host=moire_host, port=moire_port)
    
    # Wire up components
    orchestrator.set_interaction_agent(interaction)
    orchestrator.set_moire_client(moire_client)
    
    # Connect to MoireServer
    logger.info(f"Connecting to MoireServer at ws://{moire_host}:{moire_port}...")
    try:
        await moire_client.connect()
        logger.info("✓ Connected to MoireServer")
    except Exception as e:
        logger.warning(f"✗ MoireServer connection failed: {e}")
        logger.info("  Running in offline mode (no screenshots)")
    
    # Start orchestrator
    await orchestrator.start()
    logger.info("✓ Orchestrator started")

    # Initial screenshot capture for baseline
    logger.info("\n📸 Erfasse initialen Screen-State...")
    try:
        if moire_client.is_connected:
            # Trigger capture via MoireServer
            initial_result = await moire_client.capture_and_wait_for_complete(timeout=10.0)
            if initial_result.success:
                logger.info(f"✓ Initialer Screenshot erfasst")
                if initial_result.ocr_text:
                    logger.info(f"  OCR: {len(initial_result.ocr_text)} Zeichen erkannt")
                if hasattr(initial_result, 'boxes') and initial_result.boxes:
                    logger.info(f"  Detection: {len(initial_result.boxes)} Elemente gefunden")

                # NEU: An Orchestrator übergeben
                if initial_result.screenshot_base64:
                    import base64
                    screenshot_b64 = initial_result.screenshot_base64
                    if screenshot_b64.startswith('data:'):
                        screenshot_b64 = screenshot_b64.split(',', 1)[1]
                    screenshot_bytes = base64.b64decode(screenshot_b64)

                    orchestrator.set_initial_state(
                        screenshot=screenshot_bytes,
                        state={
                            "ocr_text": initial_result.ocr_text or "",
                            "boxes": initial_result.boxes if hasattr(initial_result, 'boxes') else [],
                            "timestamp": time.time()
                        }
                    )
                    logger.info(f"  ✓ Initial State an Orchestrator übergeben")
            else:
                logger.warning(f"⚠ Initialer Screenshot fehlgeschlagen")
        else:
            logger.info("  (Kein MoireServer - Screenshot übersprungen)")
    except Exception as e:
        logger.warning(f"⚠ Initialer Screenshot Fehler: {e}")

    # Print status
    status = orchestrator.get_status()
    logger.info(f"\n=== System Status ===")
    logger.info(f"Event Queue: {'✓ Running' if status['running'] else '✗ Stopped'}")
    logger.info(f"MoireServer: {'✓ Connected' if status['has_moire_client'] else '✗ Disconnected'}")
    logger.info(f"Interaction Agent: {'✓ Ready' if status['has_interaction_agent'] else '✗ Not available'}")
    logger.info(f"========================\n")
    
    # Setup signal handlers
    shutdown_event = asyncio.Event()
    
    def signal_handler():
        logger.info("\nShutdown signal received...")
        shutdown_event.set()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_event_loop().add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass
    
    # Execute task if provided
    if task:
        logger.info(f"\nExecuting task: {task}")
        logger.info("-" * 40)
        
        result_task = await orchestrator.execute_task(task)
        
        if result_task.status == TaskStatus.COMPLETED:
            logger.info(f"\n✓ Task completed successfully!")
            logger.info(f"  Actions executed: {len(result_task.actions)}")
        else:
            logger.error(f"\n✗ Task failed: {result_task.error}")
        
        # Wenn nicht interaktiv, beenden
        if not interactive:
            await shutdown_orchestrator()
            await moire_client.disconnect()
            return result_task
    
    # Interactive mode
    if interactive:
        logger.info("\n=== Interactive Mode ===")
        logger.info("Commands:")
        logger.info("  <task>   - Execute a task (e.g., 'Starte Chrome')")
        logger.info("  status   - Show system status")
        logger.info("  tasks    - Show active tasks")
        logger.info("  quit     - Exit")
        logger.info("========================\n")
        
        try:
            while not shutdown_event.is_set():
                try:
                    # Use asyncio-friendly input
                    user_input = await asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: input(">>> ")
                    )
                    user_input = user_input.strip()
                    
                    if not user_input:
                        continue
                    
                    if user_input.lower() == 'quit':
                        break
                    
                    if user_input.lower() == 'status':
                        status = orchestrator.get_status()
                        print(f"\n{'-'*40}")
                        print(f"Running: {status['running']}")
                        print(f"Queue: {status['queue']}")
                        print(f"Reasoning: {status['reasoning']}")
                        print(f"Validation: {status['validation']}")
                        print(f"{'-'*40}\n")
                        continue
                    
                    if user_input.lower() == 'tasks':
                        tasks = orchestrator.get_active_tasks()
                        print(f"\n{'-'*40}")
                        print(f"Active tasks: {len(tasks)}")
                        for t in tasks:
                            print(f"  [{t.status.value}] {t.id}: {t.goal}")
                        print(f"{'-'*40}\n")
                        continue
                    
                    # Execute task
                    logger.info(f"\nExecuting: {user_input}")
                    result_task = await orchestrator.execute_task(user_input)
                    
                    if result_task.status == TaskStatus.COMPLETED:
                        logger.info(f"✓ Completed ({len(result_task.actions)} actions)")
                    else:
                        logger.error(f"✗ Failed: {result_task.error}")
                
                except EOFError:
                    break
                except KeyboardInterrupt:
                    break
        
        except Exception as e:
            logger.error(f"Interactive mode error: {e}")
    
    # Cleanup
    logger.info("\nShutting down...")
    await shutdown_orchestrator()
    await moire_client.disconnect()
    logger.info("Goodbye!")


def run():
    """Entry-Point für Kommandozeile."""
    parser = argparse.ArgumentParser(
        description="MoireTracker AutoGen Desktop Agent System V2"
    )
    parser.add_argument(
        '--task', '-t',
        type=str,
        help='Task to execute (e.g., "Starte League of Legends")'
    )
    parser.add_argument(
        '--no-interactive', '-n',
        action='store_true',
        help='Disable interactive mode (exit after task)'
    )
    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run
    try:
        asyncio.run(main(
            task=args.task,
            interactive=not args.no_interactive
        ))
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")


if __name__ == '__main__':
    run()