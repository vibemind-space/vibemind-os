"""
Voice Coding Tools for VibeMind

Special tools that bridge voice commands to the coding pipeline via Event Bus.
These tools enable:
- Converting ideas to coding projects
- Voice-controlled code modifications
- Real-time feedback during code generation

These tools publish events to Redis streams for the backend swarm to process.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

# Add python/ directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

logger = logging.getLogger(__name__)


async def idea_to_project(idea_name: str = None, tech_stack: str = "react") -> str:
    """
    Convert an idea/note from a bubble into a coding project.

    This tool:
    1. Fetches the idea content from the current bubble
    2. Creates a project specification
    3. Seeds a code.generate event to the Event Bus
    4. Backend swarm picks up and starts code generation

    Args:
        idea_name: Name of the idea to convert (required)
        tech_stack: Technology stack for the project (default: react)

    Returns:
        Status message with job_id
    """
    if not idea_name:
        return "Fehler: Kein Ideen-Name angegeben. Bitte sag mir welche Idee ich in ein Projekt umwandeln soll."
    try:
        # Get the idea content
        from tools.idea_tools import find_idea
        idea_result = find_idea({"query": idea_name})

        if "not found" in idea_result.lower() or "keine" in idea_result.lower():
            return f"Idee '{idea_name}' nicht gefunden. Erstelle zuerst eine Idee mit create_idea()."

        # Try to get event bus (if Redis available)
        try:
            from swarm.event_bus import get_event_bus, SwarmEvent

            bus = get_event_bus()
            event = SwarmEvent(
                stream="events:tasks",
                event_type="idea.to_project",
                payload={
                    "idea_name": idea_name,
                    "idea_content": idea_result,
                    "tech_stack": tech_stack,
                }
            )
            job_id = await bus.publish(event)

            logger.info(f"idea_to_project: Published event for '{idea_name}' (job={job_id})")
            return f"Projekt aus Idee '{idea_name}' gestartet. Job-ID: {job_id}. Der Backend-Swarm verarbeitet jetzt die Anfrage."

        except Exception as e:
            # Fallback: use direct coding tools
            logger.warning(f"Event bus not available, using direct tools: {e}")
            from .adapted_coding_tools import generate_code

            result = generate_code(
                title=idea_name,
                description=idea_result,
                tech_stack=tech_stack,
            )
            return result

    except ImportError as e:
        logger.error(f"idea_to_project import error: {e}")
        return f"Tools nicht verfügbar: {e}"
    except Exception as e:
        logger.error(f"idea_to_project error: {e}")
        return f"Fehler beim Konvertieren der Idee: {e}"


async def modify_code(instruction: str = None, job_id: str = "") -> str:
    """
    Send a voice instruction to modify generated code.

    This enables voice-controlled coding:
    - "Add dark mode to the app"
    - "Change the button color to blue"
    - "Add a login page"

    The instruction is sent to the Coding Engine via Event Bus.

    Args:
        instruction: Natural language instruction for code modification (required)
        job_id: Job ID of the project to modify (optional, uses latest if empty)

    Returns:
        Confirmation message
    """
    if not instruction:
        return "Was soll ich am Code ändern? Gib mir eine Anweisung."

    try:
        # Try to get event bus
        try:
            from swarm.event_bus import get_event_bus, SwarmEvent

            bus = get_event_bus()
            event = SwarmEvent(
                stream="events:tasks",
                event_type="code.modify",
                payload={
                    "instruction": instruction,
                    "job_id": job_id,
                }
            )
            event_job_id = await bus.publish(event)

            logger.info(f"modify_code: Published modification '{instruction[:50]}...' (job={event_job_id})")
            return f"Änderung '{instruction}' wurde an den Code-Generator gesendet. Job-ID: {event_job_id}"

        except Exception as e:
            # Fallback: log the instruction for manual processing
            logger.warning(f"Event bus not available: {e}")
            logger.info(f"Code modification requested: {instruction} (job_id={job_id})")
            return f"Event Bus nicht verfügbar. Änderung notiert: '{instruction}'. Bitte manuell anwenden."

    except Exception as e:
        logger.error(f"modify_code error: {e}")
        return f"Fehler bei der Code-Änderung: {e}"


async def show_code(file_path: str = "", job_id: str = "") -> str:
    """
    Show generated code for review (via voice summary).

    Args:
        file_path: Specific file to show (optional)
        job_id: Job ID of the project (optional, uses latest if empty)

    Returns:
        Code summary or content
    """
    try:
        from swarm.event_bus import get_event_bus, SwarmEvent

        bus = get_event_bus()
        event = SwarmEvent(
            stream="events:tasks",
            event_type="code.show",
            payload={
                "file_path": file_path,
                "job_id": job_id,
            }
        )
        await bus.publish(event)

        return f"Code wird geladen... Die Anzeige erscheint im Preview-Bereich."

    except Exception as e:
        logger.warning(f"show_code: Event bus not available: {e}")
        return "Code-Anzeige nicht verfügbar. Öffne das Projekt im Editor."


async def run_preview(job_id: str = "", project_name: str = "") -> str:
    """
    Start the live preview for a generated project.

    Convenience wrapper that publishes a preview.start event.

    Args:
        job_id: Job ID of the project (optional)
        project_name: Project name (optional)

    Returns:
        Preview status message
    """
    try:
        # Use adapted coding tools directly for preview
        from .adapted_coding_tools import start_preview
        return start_preview(job_id=job_id, project_name=project_name)

    except Exception as e:
        logger.error(f"run_preview error: {e}")
        return f"Preview konnte nicht gestartet werden: {e}"


# Synchronous wrappers for tools that don't need async
def idea_to_project_sync(idea_name: str = None, tech_stack: str = "react") -> str:
    """Synchronous wrapper for idea_to_project."""
    if not idea_name:
        return "Fehler: Kein Ideen-Name angegeben. Bitte sag mir welche Idee ich in ein Projekt umwandeln soll."
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a new task in the running loop
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, idea_to_project(idea_name, tech_stack))
                return future.result()
        else:
            return loop.run_until_complete(idea_to_project(idea_name, tech_stack))
    except RuntimeError:
        return asyncio.run(idea_to_project(idea_name, tech_stack))


def modify_code_sync(instruction: str = None, job_id: str = "") -> str:
    """Synchronous wrapper for modify_code."""
    if not instruction:
        return "Fehler: Keine Anweisung angegeben. Bitte sag mir was ich am Code aendern soll."
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, modify_code(instruction, job_id))
                return future.result()
        else:
            return loop.run_until_complete(modify_code(instruction, job_id))
    except RuntimeError:
        return asyncio.run(modify_code(instruction, job_id))


# Export sync versions for non-async contexts
VOICE_CODING_TOOLS = [
    idea_to_project_sync,
    modify_code_sync,
]

# Also export async versions for async contexts
VOICE_CODING_TOOLS_ASYNC = [
    idea_to_project,
    modify_code,
    show_code,
    run_preview,
]


__all__ = [
    "idea_to_project",
    "idea_to_project_sync",
    "modify_code",
    "modify_code_sync",
    "show_code",
    "run_preview",
    "VOICE_CODING_TOOLS",
    "VOICE_CODING_TOOLS_ASYNC",
]
