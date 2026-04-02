"""
Adapted Coding Tools for AutoGen Swarm

Typed wrappers around the original Dict-based coding tools.
These can be used directly as FunctionTool in AssistantAgent.

Note: Coding tools require the Hybrid Run Coding Engine to be available.
"""

from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


def generate_code(
    title: str = None,
    description: str = "",
    tech_stack: str = "react",
    requirements: Optional[List[str]] = None,
    autonomous: bool = True
) -> str:
    """
    Start code generation for a new project using Hybrid Run.

    Args:
        title: Project title (required)
        description: Detailed requirements (optional)
        tech_stack: Technology stack - react, vue, python-flask, etc. (default: react)
        requirements: List of specific requirements (optional)
        autonomous: Run in full autonomous mode (default: True)

    Returns:
        Status message with job_id for tracking
    """
    if not title:
        return "Error: No project title provided. Please tell me what the project should be called."
    try:
        from .coding_tools import generate_code as _generate
        return _generate({
            "title": title,
            "description": description,
            "tech_stack": tech_stack,
            "requirements": requirements or [],
            "autonomous": autonomous,
        })
    except ImportError:
        return "Coding tools not available. Hybrid Run Coding Engine required."


def get_generation_status(job_id: str = "", project_name: str = "") -> str:
    """
    Get the current status of a code generation job.

    Args:
        job_id: The job ID to check (optional)
        project_name: Project name to search for (optional)

    Returns:
        Status information about the generation
    """
    try:
        from .coding_tools import get_generation_status as _status
        return _status({
            "job_id": job_id,
            "project_name": project_name,
        })
    except ImportError:
        return "Coding tools not available."


def start_preview(job_id: str = "", project_name: str = "", resolution: str = "1280x720") -> str:
    """
    Start a VNC preview for a completed project.

    Args:
        job_id: The job ID (optional)
        project_name: Project name to search for (optional)
        resolution: VNC resolution like "1280x720" (optional)

    Returns:
        Preview URL or error message
    """
    try:
        from .coding_tools import start_preview as _preview
        return _preview({
            "job_id": job_id,
            "project_name": project_name,
            "resolution": resolution,
        })
    except ImportError:
        return "Coding tools not available."


def stop_preview(job_id: str = "", project_name: str = "") -> str:
    """
    Stop a running VNC preview.

    Args:
        job_id: The job ID (optional)
        project_name: Project name to search for (optional)

    Returns:
        Confirmation message
    """
    try:
        from .coding_tools import stop_preview as _stop
        return _stop({
            "job_id": job_id,
            "project_name": project_name,
        })
    except ImportError:
        return "Coding tools not available."


def list_generated_projects(status_filter: str = "", limit: int = 10) -> str:
    """
    List all generated projects.

    Args:
        status_filter: Filter by generation_status (optional)
        limit: Maximum number to return (default: 10)

    Returns:
        Formatted list of projects
    """
    try:
        from .coding_tools import list_generated_projects as _list
        return _list({
            "status_filter": status_filter,
            "limit": limit,
        })
    except ImportError:
        return "Coding tools not available."


def cancel_generation(job_id: str = None) -> str:
    """
    Cancel a running code generation job.

    Args:
        job_id: The job ID to cancel (required)

    Returns:
        Confirmation message
    """
    if not job_id:
        return "Error: No job ID provided. Please tell me which job to cancel."
    try:
        from .coding_tools import cancel_generation as _cancel
        return _cancel({"job_id": job_id})
    except ImportError:
        return "Coding tools not available."


# Collect all tools for export
CODING_TOOLS = [
    generate_code,
    get_generation_status,
    start_preview,
    stop_preview,
    list_generated_projects,
    cancel_generation,
]


__all__ = [
    "generate_code",
    "get_generation_status",
    "start_preview",
    "stop_preview",
    "list_generated_projects",
    "cancel_generation",
    "CODING_TOOLS",
]
