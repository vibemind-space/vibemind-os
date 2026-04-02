"""Allow running as: python -m spaces.desktop.eyeterm"""
import logging

from .app import main

logger = logging.getLogger(__name__)

main()
