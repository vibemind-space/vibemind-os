"""
Dual-Graph Memory System

KotlinGraph + KuroGraph architecture:
- KotlinGraph: Raw event storage (episodic memory)
- KuroGraph: Pattern extraction (semantic memory)
"""

from .kotlingraph import KotlinGraph, GameEvent
from .kurograph import KuroGraph, ActionNGram, StrategyPattern
from .dual_graph_manager import DualGraphManager

__all__ = [
    'KotlinGraph',
    'GameEvent',
    'KuroGraph',
    'ActionNGram',
    'StrategyPattern',
    'DualGraphManager'
]
