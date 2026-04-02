"""
TRAE Backend Application Package

A maintainable, scalable backend for the TRAE visual node-based automation system.
Provides OCR workflows, desktop automation, and real-time collaboration.
"""

__version__ = "1.0.0"
__title__ = "TRAE Backend"
__description__ = "Visual Node-Based Automation Backend"
__author__ = "TRAE Development Team"

from .main import create_app

__all__ = ["create_app"]
