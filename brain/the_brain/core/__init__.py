"""
The Brain - Core Module Exports

This module provides exports for key components of the cognitive architecture.
"""

# Basal Ganglia - Action Selection
from core.basal_ganglia import (
    BasalGanglia,
    BasalGangliaOutput,
    BGAction,
    StriatumState,
    Striatum,
    DirectPathway,
    IndirectPathway,
    HyperdirectPathway,
    GPiSNr,
    create_bg_from_oscillator_state
)

# Action Potential Oscillator - Temporal Control
from core.action_potential_oscillator import (
    ActionPotentialOscillator,
    TripleOscillatorState,
    OscillatorState,
    Channel
)

# Neuromodulation System
from core.neuromodulation import (
    NeuromodulationSystem,
    NeuromodulatorLevels,
    NeuromodulatorEffects
)

# Hippocampus - Episodic Memory
from core.hippocampus import Hippocampus

# Thalamo-Hippocampal System
from core.thalamo_hippocampal_system import ThalamoHippocampalSystem

# Meta Router
from core.meta_router import MetaRouter

# Predictive Coding
from core.thalamo_pc_adaptive import ThalamoPC6Adaptive

# Cortical Feedback
from core.cortical_feedback import (
    CorticalProcessor,
    CorticalFeedback,
    CorticalState,
    AttentionController,
    FeedbackGenerator,
    ExpectationNetwork
)

# Predictive Routing
from core.predictive_router import (
    PredictiveRouter,
    PredictiveState,
    RoutingPrediction,
    ForwardModel,
    AnticipatedGateComputer,
    TemporalRoutingPattern
)

# Multi-Band Oscillator
from core.multi_band_oscillator import (
    MultiBandOscillator,
    MultiBandState,
    BandState,
    FrequencyBand,
    PhaseAmplitudeCoupler
)

# Multi-Band Synchrony Encoder
from core.multi_band_synchrony_encoder import (
    MultiBandSynchronyEncoder,
    MultiBandSynchronyVector
)

# Hierarchical Routing System
from core.hierarchical_layer import (
    HierarchicalLayer,
    LayerConfig,
    LayerOutput,
    HierarchicalRoutingResult,
    verify_gate_invariant,
    compute_gate_entropy,
    blend_gates_weighted
)
from core.sensory_layer import SensoryLayer
from core.feature_layer import FeatureLayer
from core.semantic_layer import SemanticLayer
from core.abstract_layer import AbstractLayer
from core.hierarchical_routing_system import (
    HierarchicalRoutingSystem,
    HierarchicalRoutingConfig,
    create_hierarchical_routing_system
)

# Sleep Consolidation
from core.sleep_consolidation import (
    SleepState,
    SleepConsolidationConfig,
    SleepStateMachine,
    SynapticHomeostasis,
    SharpWaveRippleGenerator,
    SleepStageManager,
    SleepConsolidation,
    SleepConsolidationOutput,
    ConsolidationMetrics
)

__all__ = [
    # Basal Ganglia
    'BasalGanglia',
    'BasalGangliaOutput',
    'BGAction',
    'StriatumState',
    'Striatum',
    'DirectPathway',
    'IndirectPathway',
    'HyperdirectPathway',
    'GPiSNr',
    'create_bg_from_oscillator_state',
    # Oscillator
    'ActionPotentialOscillator',
    'TripleOscillatorState',
    'OscillatorState',
    'Channel',
    # Neuromodulation
    'NeuromodulationSystem',
    'NeuromodulatorLevels',
    'NeuromodulatorEffects',
    # Hippocampus
    'Hippocampus',
    # Thalamo-Hippocampal
    'ThalamoHippocampalSystem',
    # Meta Router
    'MetaRouter',
    # Predictive Coding
    'ThalamoPC6Adaptive',
    # Cortical Feedback
    'CorticalProcessor',
    'CorticalFeedback',
    'CorticalState',
    'AttentionController',
    'FeedbackGenerator',
    'ExpectationNetwork',
    # Predictive Routing
    'PredictiveRouter',
    'PredictiveState',
    'RoutingPrediction',
    'ForwardModel',
    'AnticipatedGateComputer',
    'TemporalRoutingPattern',
    # Multi-Band Oscillator
    'MultiBandOscillator',
    'MultiBandState',
    'BandState',
    'FrequencyBand',
    'PhaseAmplitudeCoupler',
    # Multi-Band Synchrony Encoder
    'MultiBandSynchronyEncoder',
    'MultiBandSynchronyVector',
    # Hierarchical Routing System
    'HierarchicalLayer',
    'LayerConfig',
    'LayerOutput',
    'HierarchicalRoutingResult',
    'verify_gate_invariant',
    'compute_gate_entropy',
    'blend_gates_weighted',
    'SensoryLayer',
    'FeatureLayer',
    'SemanticLayer',
    'AbstractLayer',
    'HierarchicalRoutingSystem',
    'HierarchicalRoutingConfig',
    'create_hierarchical_routing_system',
    # Sleep Consolidation
    'SleepState',
    'SleepConsolidationConfig',
    'SleepStateMachine',
    'SynapticHomeostasis',
    'SharpWaveRippleGenerator',
    'SleepStageManager',
    'SleepConsolidation',
    'SleepConsolidationOutput',
    'ConsolidationMetrics',
]
