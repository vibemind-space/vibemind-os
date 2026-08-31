# -*- coding: utf-8 -*-
"""
GitHub MCP plugin event task helpers.
Provides GitHub-specific event broadcasting utilities and integration helpers.
"""
import sys
import os

# CRITICAL: Add shared directory to sys.path FIRST before any imports
# This ensures event_server.py can find shared/constants.py correctly
shared_path = os.path.join(os.path.dirname(__file__), '..', 'shared')
sys.path.insert(0, shared_path)

# Now import from shared modules
from event_server import EventServer, start_ui_server

# Re-export for backward compatibility
__all__ = ['EventServer', 'start_ui_server', 'start_github_ui_server']


def start_github_ui_server(event_server: EventServer, host: str = "127.0.0.1", port: int = 0):
    """Start UI server with GitHub branding.
    
    Args:
        event_server: EventServer instance
        host: Host to bind to (default: 127.0.0.1)
        port: Port to bind to (0 for dynamic OS-assigned port)
        
    Returns:
        Tuple of (httpd, thread, bound_host, bound_port)
        
    Example:
        >>> from github.event_task import start_github_ui_server, EventServer
        >>> event_server = EventServer()
        >>> httpd, thread, host, port = start_github_ui_server(event_server)
        >>> print(f"GitHub UI at http://{host}:{port}/")
    """
    return start_ui_server(
        event_server,
        host=host,
        port=port,
        tool_name="GitHub MCP Server"  # Explicit tool name
    )