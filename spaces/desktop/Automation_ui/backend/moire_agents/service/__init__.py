"""
Handoff MCP Service Module

Production deployment infrastructure for the Handoff MCP desktop automation system.
Provides cross-platform service management, health monitoring, and process supervision.

Supported Platforms:
- Windows: Task Scheduler, NSSM, native services
- Linux: systemd user services
- macOS: launchd agents
"""

from .health_monitor import HealthMonitor
from .process_manager import ProcessManager
from .service_manager import ServiceManager, ServiceConfig, Platform

__all__ = [
    'HealthMonitor',
    'ProcessManager',
    'ServiceManager',
    'ServiceConfig',
    'Platform'
]

# Version info
__version__ = '1.0.0'
