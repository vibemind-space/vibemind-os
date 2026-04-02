"""
Integration test fixtures.

These fixtures create fully wired component systems for end-to-end testing.
"""

import pytest
import numpy as np
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.hierarchical_routing_system import (
    HierarchicalRoutingSystem,
    HierarchicalRoutingConfig,
    create_hierarchical_routing_system
)
from core.basal_ganglia import BasalGanglia
from core.hippocampus import Hippocampus
from core.neuromodulation import NeuromodulationSystem
from core.sleep_consolidation import (
    SleepConsolidation,
    SleepConsolidationConfig,
    create_sleep_consolidation
)
from core.multi_band_oscillator import MultiBandOscillator


@pytest.fixture
def neuromodulation():
    """Pre-configured neuromodulation system."""
    return NeuromodulationSystem(
        baseline_dopamine=0.5,
        baseline_serotonin=0.5,
        baseline_norepinephrine=0.5,
        decay_rate=0.05,
        sensitivity=1.0,
        history_size=50
    )


@pytest.fixture
def hippocampus(modality_dims):
    """Pre-configured hippocampus with standard dimensions."""
    total_dim = sum(modality_dims.values())  # 264
    return Hippocampus(
        state_dim=total_dim,
        context_dim=6,
        num_modalities=6,
        memory_capacity=100,
        novelty_threshold=0.5,
        seed=42
    )


@pytest.fixture
def basal_ganglia():
    """Pre-configured basal ganglia."""
    return BasalGanglia(
        n_inputs=6,
        n_actions=3,
        learning_rate=0.01
    )


@pytest.fixture
def hierarchical_routing(seed):
    """Pre-configured hierarchical routing system."""
    return create_hierarchical_routing_system(seed=seed)


@pytest.fixture
def oscillator():
    """Pre-configured multi-band oscillator."""
    return MultiBandOscillator(
        theta_freq=6.0,
        alpha_freq=10.0,
        gamma_freq=40.0
    )


@pytest.fixture
def fast_sleep_config():
    """Fast sleep configuration for testing."""
    return SleepConsolidationConfig(
        idle_threshold_seconds=2.0,
        drowsy_duration=1.0,
        nrem_n1_duration=1.0,
        nrem_n2_duration=2.0,
        nrem_n3_duration=3.0,
        rem_duration=2.0,
        max_sleep_cycles=2,
        swr_probability=0.8,
        swr_replay_count=3,
        seed=42
    )


@pytest.fixture
def sleep_consolidation(fast_sleep_config, hippocampus, neuromodulation):
    """Pre-configured sleep consolidation with connected components."""
    return SleepConsolidation(
        config=fast_sleep_config,
        hippocampus=hippocampus,
        neuromodulation=neuromodulation
    )
