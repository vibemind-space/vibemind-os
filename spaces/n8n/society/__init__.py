"""
n8n Society of Mind — Multi-Agent Workflow Generation

Uses AutoGen 0.4 SocietyOfMindAgent with SelectorGroupChat
to plan, build, test, and review n8n workflows iteratively.
"""

from .workflow_society import run_workflow_society

__all__ = ["run_workflow_society"]
