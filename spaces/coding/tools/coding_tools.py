"""
VibeMind Coding Tools

Client tools for code generation via Hybrid Run Coding Engine.
These tools enable voice-controlled project creation and management.

Tool Categories:
- Generation: generate_code, get_generation_status
- Preview: start_preview, stop_preview
- Management: list_generated_projects

Usage:
    User says: "Erstelle eine Todo-App mit React"
    Antoni calls: generate_code(title="Todo App", tech_stack="react")
"""

import sys
import os
import json
import logging
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Add python/ directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from data import ProjectsRepository, GenerationStatus

# Global reference to Electron IPC sender (set by electron_backend.py)
_electron_send_message: Optional[Callable[[dict], None]] = None

# Global reference to CodingEngineRunner (set during initialization)
_coding_engine_runner: Optional[Any] = None


def set_electron_sender(sender: Callable[[dict], None]):
    """Set the Electron IPC message sender callback."""
    global _electron_send_message
    _electron_send_message = sender


def set_coding_engine_runner(runner):
    """Set the CodingEngineRunner instance."""
    global _coding_engine_runner
    _coding_engine_runner = runner


def _broadcast_to_electron(message: dict):
    """Send a message to Electron if connected."""
    if _electron_send_message:
        _electron_send_message(message)


def _get_runner():
    """Get or create the CodingEngineRunner instance."""
    global _coding_engine_runner
    if _coding_engine_runner is None:
        # Lazy import to avoid circular imports
        from coding_engine_runner import CodingEngineRunner
        _coding_engine_runner = CodingEngineRunner()
    return _coding_engine_runner


# ==============================================================================
# GENERATION TOOLS
# ==============================================================================

def generate_code(params: Dict[str, Any]) -> str:
    """
    Start code generation for a new project using Hybrid Run.

    Called when user says things like:
    - "Create a React Todo-App"
    - "Generate a Python API for user management"
    - "Build me a website for my portfolio"

    Args (via params):
        title: Project title (required)
        description: Detailed requirements (optional)
        tech_stack: Technology stack - react, vue, python-flask, etc. (optional)
        requirements: List of specific requirements (optional)
        autonomous: Run in full autonomous mode (default: True)

    Returns:
        Status message with job_id for tracking
    """
    title = params.get("title", "").strip()
    logger.debug("generate_code: title=%s", title)

    if not title:
        return "What should the project be called? Give me a title."

    description = params.get("description", "")
    tech_stack = params.get("tech_stack", "react")  # Default to React
    requirements = params.get("requirements", [])
    autonomous = params.get("autonomous", True)

    # Ensure requirements is a list
    if isinstance(requirements, str):
        requirements = [r.strip() for r in requirements.split(",") if r.strip()]

    # Generate job ID
    job_id = str(uuid.uuid4())[:8]

    # Create project in database
    repo = ProjectsRepository()

    # Build requirements JSON
    requirements_data = {
        "project_name": title,
        "description": description,
        "tech_stack": tech_stack,
        "requirements": requirements if requirements else [description or f"Create a {title}"],
        "autonomous": autonomous,
    }

    # Determine output path
    output_dir = Path(os.environ.get("CODING_OUTPUT_DIR", "./generated_projects"))
    output_dir.mkdir(parents=True, exist_ok=True)
    project_path = str(output_dir / f"project-{job_id}")

    project = repo.create(
        name=title,
        description=description,
        project_path=project_path,
        generation_status=GenerationStatus.PENDING,
        tech_stack=tech_stack,
        requirements_json=json.dumps(requirements_data),
        job_id=job_id,
    )

    # Start the coding engine (async in background)
    try:
        runner = _get_runner()
        runner.start_generation(
            job_id=job_id,
            project_id=project.id,
            requirements_data=requirements_data,
            output_dir=project_path,
            autonomous=autonomous,
        )

        # Notify Electron
        _broadcast_to_electron({
            "type": "generation_started",
            "project_id": project.id,
            "job_id": job_id,
            "title": title,
            "tech_stack": tech_stack,
        })

        # Publish to Rowboat knowledge graph
        try:
            from publishing import get_coding_publisher
            get_coding_publisher().publish_project(
                project_name=title,
                tech_stack=tech_stack,
                status="generating",
                progress=0.0,
                data_dir=project_path,
            )
        except Exception:
            pass

        # Publish project to Rowboat MongoDB (for Brain seeding)
        try:
            from publishing import get_ideas_publisher
            pub = get_ideas_publisher()
            if hasattr(pub, 'publish_project'):
                pub.publish_project(project.id)
        except Exception:
            pass

        return f"Starting generation of '{title}' with {tech_stack}. Job ID: {job_id}. This may take a few minutes. Ask for status with 'What's the status of {job_id}?'"

    except Exception as e:
        # Update status to failed
        repo.update_generation_status(
            project.id,
            GenerationStatus.FAILED,
            error_message=str(e)
        )
        return f"Error starting generation: {str(e)}"


def get_generation_status(params: Dict[str, Any]) -> str:
    """
    Get the current status of a code generation job.

    Called when user says things like:
    - "What's the status of abc123?"
    - "Is my project ready?"
    - "Show me the progress"

    Args (via params):
        job_id: The job ID to check (required if no project_name)
        project_name: Project name to search for (optional)

    Returns:
        Status information about the generation
    """
    job_id = params.get("job_id")
    project_name = params.get("project_name", "").strip()
    logger.debug("get_generation_status: job_id=%s, project_name=%s", job_id, project_name)

    repo = ProjectsRepository()
    project = None

    if job_id:
        project = repo.get_by_job_id(job_id)
    elif project_name:
        project = repo.get_by_name(project_name)

    if not project:
        if job_id:
            return f"No project found with job ID '{job_id}'."
        else:
            return f"No project named '{project_name}' found."

    # Get live status from runner if available
    runner = _get_runner()
    live_status = runner.get_job_status(project.job_id) if runner else None

    # Update from live status if available
    if live_status:
        project.generation_status = live_status.get("status", project.generation_status)
        project.convergence_progress = live_status.get("progress", project.convergence_progress)
        if live_status.get("error"):
            project.error_message = live_status["error"]
        repo.update(project)

        # Publish to Rowboat on status transitions
        if project.generation_status in (GenerationStatus.COMPLETED, GenerationStatus.FAILED):
            try:
                from publishing import get_coding_publisher
                get_coding_publisher().publish_project(
                    project_name=project.name,
                    tech_stack=project.tech_stack or "",
                    status=project.generation_status,
                    progress=project.convergence_progress or 100.0,
                    data_dir=project.project_path or "",
                )
            except Exception:
                pass

    # Build response
    status_messages = {
        GenerationStatus.PENDING: "waiting to start",
        GenerationStatus.GENERATING: "code is being generated",
        GenerationStatus.CONVERGING: f"Society of Mind optimizing ({project.convergence_progress:.0f}%)",
        GenerationStatus.TESTING: "tests are running",
        GenerationStatus.COMPLETED: "successfully completed",
        GenerationStatus.FAILED: f"failed: {project.error_message or 'Unknown error'}",
        GenerationStatus.PREVIEWING: f"preview running on port {project.vnc_port}",
    }

    status_text = status_messages.get(project.generation_status, project.generation_status)

    response = f"Project '{project.name}' (Job: {project.job_id}): {status_text}"

    if project.generation_status == GenerationStatus.COMPLETED:
        response += ". Say 'Start preview' to see the preview."
    elif project.generation_status == GenerationStatus.PREVIEWING:
        response += f". You can see the preview in Projects Space or at {project.preview_url}"

    return response


# ==============================================================================
# PREVIEW TOOLS
# ==============================================================================

def start_preview(params: Dict[str, Any]) -> str:
    """
    Start a VNC preview for a completed project.

    Called when user says things like:
    - "Start preview for abc123"
    - "Show me the preview"
    - "Open the project"

    Args (via params):
        job_id: The job ID (required if no project_name)
        project_name: Project name to search for (optional)
        resolution: VNC resolution like "1280x720" (optional)

    Returns:
        Preview URL or error message
    """
    job_id = params.get("job_id")
    project_name = params.get("project_name", "").strip()
    resolution = params.get("resolution", "1280x720")
    logger.debug("start_preview: job_id=%s, project_name=%s", job_id, project_name)

    repo = ProjectsRepository()
    project = None

    if job_id:
        project = repo.get_by_job_id(job_id)
    elif project_name:
        project = repo.get_by_name(project_name)

    if not project:
        return "Project not found. Give me a job ID or project name."

    # Check if already previewing
    if project.generation_status == GenerationStatus.PREVIEWING and project.vnc_port:
        return f"Preview already running on port {project.vnc_port}. URL: {project.preview_url}"

    # Check if generation is complete
    if project.generation_status not in [GenerationStatus.COMPLETED, GenerationStatus.PREVIEWING]:
        return f"Project is not ready yet. Status: {project.generation_status}"

    # Allocate VNC port
    vnc_port = repo.allocate_vnc_port()

    # Start preview via runner
    try:
        runner = _get_runner()
        preview_url = runner.start_preview(
            project_id=project.id,
            project_path=project.project_path,
            vnc_port=vnc_port,
            resolution=resolution,
        )

        # Update database
        repo.set_preview_url(project.id, vnc_port, preview_url)

        # Notify Electron
        _broadcast_to_electron({
            "type": "project_preview_ready",
            "project_id": project.id,
            "job_id": project.job_id,
            "vnc_port": vnc_port,
            "vnc_url": preview_url,
        })

        return f"Preview started for '{project.name}'. You can see it in Projects Space or at {preview_url}"

    except Exception as e:
        return f"Error starting preview: {str(e)}"


def stop_preview(params: Dict[str, Any]) -> str:
    """
    Stop a running VNC preview.

    Called when user says things like:
    - "Stop preview for abc123"
    - "Close the preview"
    - "End the preview"

    Args (via params):
        job_id: The job ID (required if no project_name)
        project_name: Project name to search for (optional)

    Returns:
        Confirmation message
    """
    job_id = params.get("job_id")
    project_name = params.get("project_name", "").strip()
    logger.debug("stop_preview: job_id=%s, project_name=%s", job_id, project_name)

    repo = ProjectsRepository()
    project = None

    if job_id:
        project = repo.get_by_job_id(job_id)
    elif project_name:
        project = repo.get_by_name(project_name)

    if not project:
        return "Project not found."

    if not project.vnc_port:
        return f"No active preview for '{project.name}'."

    try:
        runner = _get_runner()
        runner.stop_preview(project.id, project.vnc_port)

        # Clear port in database
        repo.clear_vnc_port(project.id)

        # Notify Electron
        _broadcast_to_electron({
            "type": "project_preview_stopped",
            "project_id": project.id,
            "job_id": project.job_id,
        })

        return f"Preview for '{project.name}' has been stopped."

    except Exception as e:
        return f"Error stopping preview: {str(e)}"


# ==============================================================================
# MANAGEMENT TOOLS
# ==============================================================================

def list_generated_projects(params: Dict[str, Any]) -> str:
    """
    List all generated projects.

    Called when user says things like:
    - "Show me my generated projects"
    - "What projects have I created?"
    - "List all active previews"

    Args (via params):
        status_filter: Filter by generation_status (optional)
        limit: Maximum number to return (default: 10)

    Returns:
        Formatted list of projects
    """
    status_filter = params.get("status_filter")
    limit = int(params.get("limit", 10))
    logger.debug("list_generated_projects: status_filter=%s, limit=%s", status_filter, limit)

    repo = ProjectsRepository()

    if status_filter:
        projects = repo.list_by_generation_status(status_filter, limit=limit)
    else:
        # Get projects that have a job_id (were created via code generation)
        all_projects = repo.list(limit=limit * 2)  # Get more to filter
        projects = [p for p in all_projects if p.job_id][:limit]

    if not projects:
        if status_filter:
            return f"No projects with status '{status_filter}' found."
        else:
            return "You haven't created any code projects yet. Say 'Create an app' to get started."

    # Format output
    result_parts = [f"You have {len(projects)} generated project{'s' if len(projects) > 1 else ''}:"]

    for i, project in enumerate(projects, 1):
        status_emoji = {
            GenerationStatus.PENDING: "⏳",
            GenerationStatus.GENERATING: "🔄",
            GenerationStatus.CONVERGING: "🧠",
            GenerationStatus.TESTING: "🧪",
            GenerationStatus.COMPLETED: "✅",
            GenerationStatus.FAILED: "❌",
            GenerationStatus.PREVIEWING: "👁️",
        }.get(project.generation_status, "❓")

        tech_info = f"[{project.tech_stack}]" if project.tech_stack else ""
        progress_info = f" ({project.convergence_progress:.0f}%)" if project.convergence_progress > 0 else ""

        result_parts.append(
            f"{i}. {status_emoji} {project.name} {tech_info}{progress_info} - Job: {project.job_id}"
        )

    return " ".join(result_parts)


def cancel_generation(params: Dict[str, Any]) -> str:
    """
    Cancel a running code generation job.

    Called when user says things like:
    - "Cancel the generation"
    - "Stop job abc123"
    - "Abort"

    Args (via params):
        job_id: The job ID to cancel

    Returns:
        Confirmation message
    """
    job_id = params.get("job_id")
    logger.debug("cancel_generation: job_id=%s", job_id)

    if not job_id:
        return "Which job should I cancel? Give me a job ID."

    repo = ProjectsRepository()
    project = repo.get_by_job_id(job_id)

    if not project:
        return f"No project with job ID '{job_id}' found."

    if project.generation_status in [GenerationStatus.COMPLETED, GenerationStatus.FAILED]:
        return f"Job '{job_id}' has already finished (Status: {project.generation_status})."

    try:
        runner = _get_runner()
        runner.cancel_job(job_id)

        repo.update_generation_status(
            project.id,
            GenerationStatus.FAILED,
            error_message="Cancelled by user"
        )

        # Notify Electron
        _broadcast_to_electron({
            "type": "generation_cancelled",
            "project_id": project.id,
            "job_id": job_id,
        })

        return f"Generation of '{project.name}' has been cancelled."

    except Exception as e:
        return f"Error cancelling: {str(e)}"


def exit_project(params: Dict[str, Any]) -> str:
    """
    Exit the Projects/Coding Space and return to Ideas Space.

    Called when user says things like:
    - "Zurueck" (from coding space)
    - "Exit project space"
    - "Back to Ideas"
    - "Verlasse Coding Space"
    - "Geh zurueck"

    Args (via params):
        None required

    Returns:
        Confirmation message
    """
    # Broadcast exit to Electron
    _broadcast_to_electron({
        "type": "exit_project_space",
    })

    # Also send navigate_to_space for consistency
    _broadcast_to_electron({
        "type": "navigate_to_space",
        "space": "ideas",
    })

    return "Ich wechsle zurueck zum Ideas Space."


# ==============================================================================
# TOOL REGISTRY
# ==============================================================================

# All available tools
CODING_TOOLS = {
    # Generation
    "generate_code": generate_code,
    "get_generation_status": get_generation_status,
    # Preview
    "start_preview": start_preview,
    "stop_preview": stop_preview,
    # Management
    "list_generated_projects": list_generated_projects,
    "cancel_generation": cancel_generation,
    # Navigation
    "exit_project": exit_project,
}


def register_coding_tools(tools_manager) -> None:
    """
    Register all coding tools with the ClientToolsManager.

    Args:
        tools_manager: ClientToolsManager instance
    """
    print("Registering coding tools...")
    for tool_name, tool_func in CODING_TOOLS.items():
        tools_manager.register_with_observer(tool_name, tool_func)
        print(f"  - {tool_name}")


__all__ = [
    "generate_code",
    "get_generation_status",
    "start_preview",
    "stop_preview",
    "list_generated_projects",
    "cancel_generation",
    "exit_project",
    "CODING_TOOLS",
    "register_coding_tools",
    "set_electron_sender",
    "set_coding_engine_runner",
]
