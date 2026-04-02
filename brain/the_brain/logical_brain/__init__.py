"""
Logical Brain - Hierarchical Routing from klotskipuzzle

This module contains the routed brain architecture from the klotskipuzzle project,
adapted for integration with the Tahlamus conversation puzzle solver.

Original source: C:\Users\User\Desktop\klotskipuzzle\neurosymbolic\core\

Components:
- routed_brain.py: 3-Layer hierarchical routing (Sensory → Brain → Module)
- neurosymbolic_brain.py: 10-module brain with K-graph connectivity
- brain_graph.py: Graph structure for brain modules
- ctm_layer.py: Continuous Thinking Model integration
- puzzle_state.py: State representation for puzzles
- state_graph_mapper.py: Maps states to graph structures
"""

from logical_brain.routed_brain import (
    RoutedNeuroSymbolicBrain,
    SensoryATMRouter,
    ModuleATMRouter,
    RoutingConfig
)

__all__ = [
    'RoutedNeuroSymbolicBrain',
    'SensoryATMRouter',
    'ModuleATMRouter',
    'RoutingConfig'
]
