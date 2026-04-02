"""
Shared fixtures for ATM-R tests.

Provides pre-configured component instances that can be composed
for unit and integration testing.
"""

import pytest
import numpy as np
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Standard modality configuration
STANDARD_MODALITIES = ['vision', 'audio', 'touch', 'taste', 'vestibular', 'threat']
STANDARD_MODALITY_DIMS = {
    'vision': 128,
    'audio': 64,
    'touch': 32,
    'taste': 16,
    'vestibular': 16,
    'threat': 8
}


@pytest.fixture
def seed():
    """Standard random seed for reproducibility."""
    return 42


@pytest.fixture
def modalities():
    """Standard 6 modality names."""
    return STANDARD_MODALITIES.copy()


@pytest.fixture
def modality_dims():
    """Standard modality dimensions."""
    return STANDARD_MODALITY_DIMS.copy()


@pytest.fixture
def sample_sensory_input(modalities, modality_dims, seed):
    """Generate reproducible sample sensory input for all 6 modalities."""
    np.random.seed(seed)
    return {m: np.random.randn(modality_dims[m]) for m in modalities}


@pytest.fixture
def sample_context(seed):
    """Sample 6D normalized context vector."""
    np.random.seed(seed + 1)
    ctx = np.random.rand(6)
    return ctx / np.sum(ctx)


@pytest.fixture
def sample_goal(seed):
    """Sample 32D goal vector."""
    np.random.seed(seed + 2)
    return np.random.randn(32)


@pytest.fixture
def sample_gates(seed):
    """Sample 6D gate vector (normalized)."""
    np.random.seed(seed + 3)
    gates = np.random.rand(6)
    return gates / np.sum(gates)
