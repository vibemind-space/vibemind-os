"""
Workflows - Reusable automation workflows for common tasks.

Provides:
- BaseWorkflow: Abstract base class for all workflows
- ClaudeDesktopWorkflow: Automation for Claude Desktop interactions
"""

from .base_workflow import BaseWorkflow, WorkflowResult, WorkflowStep
from .claude_desktop import ClaudeDesktopWorkflow

__all__ = [
    'BaseWorkflow',
    'WorkflowResult',
    'WorkflowStep',
    'ClaudeDesktopWorkflow'
]
