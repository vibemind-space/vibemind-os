"""
VibeMind Desktop Space Module

Desktop automation and system control via Automation_ui backend.
Includes backend agent and adapted tools.

Migrated from:
- swarm/backend_agents/desktop_agent.py
- swarm/tools/adapted_desktop_tools.py
- tools/desktop_tools.py, quickaction_tools.py, task_tools.py, moire_tools.py
"""

from .agents import DesktopAgent, get_desktop_agent

__all__ = [
    "DesktopAgent",
    "get_desktop_agent",
]
