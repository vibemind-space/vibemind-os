"""
Scaled CTM - Configuration Presets for Different Model Sizes

Provides standardized configurations for CTM models at various scales,
from lightweight (small) to high-capacity (xl) variants.

Size Variants:
- Small: ~4M params, good for edge/mobile
- Medium: ~16M params, balanced performance
- Large: ~64M params, high quality
- XL: ~256M params, maximum capacity

Each variant includes appropriate settings for:
- Feature dimensions
- Memory length
- Synchronization pairs
- Depth/complexity

Usage:
    from core.scaled_ctm import create_ctm, CTMSize

    # Create a medium-sized CTM
    ctm = create_ctm(CTMSize.MEDIUM)

    # Or use string
    ctm = create_ctm('large')

    # Get config without creating
    config = get_config(CTMSize.SMALL)
"""

import torch
import torch.nn as nn
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum

try:
    from core.hybrid_ctm import HybridNeuroSymbolicCTM
    from core.modular_ctm import ModularCTM
    from core.hierarchical_ctm import HierarchicalCTM
    from core.memory_augmented_ctm import MemoryAugmentedCTM
except ImportError:
    from hybrid_ctm import HybridNeuroSymbolicCTM
    from modular_ctm import ModularCTM
    from hierarchical_ctm import HierarchicalCTM
    from memory_augmented_ctm import MemoryAugmentedCTM


class CTMSize(Enum):
    """CTM model size variants."""
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    XL = "xl"


class CTMType(Enum):
    """CTM architecture types."""
    HYBRID = "hybrid"
    MODULAR = "modular"
    HIERARCHICAL = "hierarchical"
    MEMORY = "memory"


@dataclass
class CTMConfig:
    """Configuration for a CTM model."""
    # Basic dimensions
    feature_dim: int
    memory_length: int
    iterations: int

    # Synchronization
    n_synch_out: int
    n_synch_action: int

    # Architecture
    synapse_depth: int
    nlm_hidden_dims: int

    # Output
    out_dims: int
    thought_dim: int

    # Thresholds
    consciousness_threshold: float

    # Estimated parameters (approximate)
    estimated_params: int

    # Name
    name: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Pre-defined configurations
CONFIGS = {
    CTMSize.SMALL: CTMConfig(
        name="small",
        feature_dim=128,
        memory_length=5,
        iterations=20,
        n_synch_out=32,
        n_synch_action=16,
        synapse_depth=2,
        nlm_hidden_dims=32,
        out_dims=4,
        thought_dim=512,
        consciousness_threshold=0.85,
        estimated_params=2_000_000  # ~2M
    ),
    CTMSize.MEDIUM: CTMConfig(
        name="medium",
        feature_dim=256,
        memory_length=10,
        iterations=30,
        n_synch_out=64,
        n_synch_action=32,
        synapse_depth=4,
        nlm_hidden_dims=64,
        out_dims=4,
        thought_dim=1024,
        consciousness_threshold=0.85,
        estimated_params=8_000_000  # ~8M
    ),
    CTMSize.LARGE: CTMConfig(
        name="large",
        feature_dim=512,
        memory_length=20,
        iterations=50,
        n_synch_out=128,
        n_synch_action=64,
        synapse_depth=6,
        nlm_hidden_dims=128,
        out_dims=4,
        thought_dim=2048,
        consciousness_threshold=0.85,
        estimated_params=32_000_000  # ~32M
    ),
    CTMSize.XL: CTMConfig(
        name="xl",
        feature_dim=1024,
        memory_length=30,
        iterations=100,
        n_synch_out=256,
        n_synch_action=128,
        synapse_depth=8,
        nlm_hidden_dims=256,
        out_dims=4,
        thought_dim=4096,
        consciousness_threshold=0.80,
        estimated_params=128_000_000  # ~128M
    )
}


def get_config(size: Union[CTMSize, str]) -> CTMConfig:
    """
    Get configuration for a given size.

    Args:
        size: CTMSize enum or string ('small', 'medium', 'large', 'xl')

    Returns:
        CTMConfig for the specified size
    """
    if isinstance(size, str):
        size = CTMSize(size.lower())

    return CONFIGS[size]


def create_ctm(
    size: Union[CTMSize, str] = CTMSize.MEDIUM,
    ctm_type: Union[CTMType, str] = CTMType.HYBRID,
    device: str = 'cpu',
    **kwargs
) -> nn.Module:
    """
    Create a CTM with the specified size and type.

    Args:
        size: Model size ('small', 'medium', 'large', 'xl')
        ctm_type: Architecture type ('hybrid', 'modular', 'hierarchical', 'memory')
        device: Torch device
        **kwargs: Override specific config parameters

    Returns:
        CTM model instance
    """
    # Get base config
    if isinstance(size, str):
        size = CTMSize(size.lower())
    config = get_config(size)

    # Convert ctm_type to enum if string
    if isinstance(ctm_type, str):
        ctm_type = CTMType(ctm_type.lower())

    # Apply overrides
    config_dict = config.to_dict()
    for key, value in kwargs.items():
        if key in config_dict:
            config_dict[key] = value

    # Create appropriate CTM type
    if ctm_type == CTMType.HYBRID:
        ctm = HybridNeuroSymbolicCTM(
            feature_dim=config_dict['feature_dim'],
            memory_length=config_dict['memory_length'],
            iterations=config_dict['iterations'],
            n_synch_out=config_dict['n_synch_out'],
            n_synch_action=config_dict['n_synch_action'],
            synapse_depth=config_dict['synapse_depth'],
            nlm_hidden_dims=config_dict['nlm_hidden_dims'],
            out_dims=config_dict['out_dims'],
            consciousness_threshold=config_dict['consciousness_threshold'],
            enable_thought_projection=True,
            thought_dim=config_dict['thought_dim'],
            device=device
        )

    elif ctm_type == CTMType.MODULAR:
        ctm = ModularCTM(
            feature_dim=config_dict['feature_dim'],
            memory_length=config_dict['memory_length'],
            iterations=config_dict['iterations'],
            n_synch_out=config_dict['n_synch_out'],
            module_hidden_dim=config_dict['feature_dim'] * 2,
            consciousness_threshold=config_dict['consciousness_threshold'],
            enable_thought_projection=True,
            thought_dim=config_dict['thought_dim'],
            device=device
        )

    elif ctm_type == CTMType.HIERARCHICAL:
        # Scale fast/slow relative to config
        fast_dim = config_dict['feature_dim'] // 2
        slow_dim = config_dict['feature_dim']

        ctm = HierarchicalCTM(
            fast_feature_dim=fast_dim,
            slow_feature_dim=slow_dim,
            fast_iterations=config_dict['iterations'] // 3,
            slow_iterations=config_dict['iterations'],
            fast_threshold=0.9,
            slow_threshold=config_dict['consciousness_threshold'],
            uncertainty_threshold=0.7,
            enable_thought_projection=True,
            thought_dim=config_dict['thought_dim'],
            device=device
        )

    elif ctm_type == CTMType.MEMORY:
        ctm = MemoryAugmentedCTM(
            feature_dim=config_dict['feature_dim'],
            iterations=config_dict['iterations'],
            working_memory_capacity=config_dict['memory_length'] * 3,
            episodic_capacity=10000,
            semantic_slots=config_dict['feature_dim'] * 4,
            consciousness_threshold=config_dict['consciousness_threshold'],
            enable_thought_projection=True,
            thought_dim=config_dict['thought_dim'],
            device=device
        )

    else:
        raise ValueError(f"Unknown CTM type: {ctm_type}")

    return ctm


def get_all_configs() -> Dict[str, CTMConfig]:
    """Get all available configurations."""
    return {size.value: config for size, config in CONFIGS.items()}


def estimate_memory(
    size: Union[CTMSize, str],
    batch_size: int = 1,
    dtype: torch.dtype = torch.float32
) -> Dict[str, int]:
    """
    Estimate memory requirements for a given size.

    Args:
        size: Model size
        batch_size: Batch size for inference
        dtype: Data type (float32 = 4 bytes, float16 = 2 bytes)

    Returns:
        Dict with memory estimates in bytes
    """
    config = get_config(size)

    bytes_per_element = 4 if dtype == torch.float32 else 2

    # Parameter memory
    param_memory = config.estimated_params * bytes_per_element

    # Activation memory (rough estimate)
    activation_memory = (
        batch_size *
        config.feature_dim *
        config.memory_length *
        config.iterations *
        bytes_per_element
    )

    # Gradient memory (same as params for training)
    gradient_memory = param_memory

    return {
        'parameters_mb': param_memory / (1024 ** 2),
        'activations_mb': activation_memory / (1024 ** 2),
        'gradients_mb': gradient_memory / (1024 ** 2),
        'total_training_mb': (param_memory + activation_memory + gradient_memory) / (1024 ** 2),
        'total_inference_mb': (param_memory + activation_memory) / (1024 ** 2)
    }


def recommend_size(
    available_memory_gb: float,
    batch_size: int = 1,
    training: bool = True
) -> CTMSize:
    """
    Recommend appropriate CTM size based on available memory.

    Args:
        available_memory_gb: Available GPU/CPU memory in GB
        batch_size: Expected batch size
        training: Whether for training (requires more memory)

    Returns:
        Recommended CTMSize
    """
    available_mb = available_memory_gb * 1024

    # Check each size from largest to smallest
    for size in [CTMSize.XL, CTMSize.LARGE, CTMSize.MEDIUM, CTMSize.SMALL]:
        memory = estimate_memory(size, batch_size)
        required = memory['total_training_mb'] if training else memory['total_inference_mb']

        # Leave 20% headroom
        if required * 1.2 <= available_mb:
            return size

    return CTMSize.SMALL  # Default to small if nothing fits


def create_ensemble(
    sizes: list = None,
    device: str = 'cpu'
) -> Dict[str, nn.Module]:
    """
    Create an ensemble of different-sized CTMs.

    Args:
        sizes: List of sizes to include. None = all sizes
        device: Torch device

    Returns:
        Dict mapping size name to CTM instance
    """
    if sizes is None:
        sizes = [CTMSize.SMALL, CTMSize.MEDIUM, CTMSize.LARGE]

    ensemble = {}
    for size in sizes:
        if isinstance(size, str):
            size = CTMSize(size.lower())
        ensemble[size.value] = create_ctm(size, device=device)

    return ensemble


# Convenience functions
def create_small_ctm(device: str = 'cpu', **kwargs) -> nn.Module:
    """Create a small CTM (~2M params)."""
    return create_ctm(CTMSize.SMALL, device=device, **kwargs)


def create_medium_ctm(device: str = 'cpu', **kwargs) -> nn.Module:
    """Create a medium CTM (~8M params)."""
    return create_ctm(CTMSize.MEDIUM, device=device, **kwargs)


def create_large_ctm(device: str = 'cpu', **kwargs) -> nn.Module:
    """Create a large CTM (~32M params)."""
    return create_ctm(CTMSize.LARGE, device=device, **kwargs)


def create_xl_ctm(device: str = 'cpu', **kwargs) -> nn.Module:
    """Create an XL CTM (~128M params)."""
    return create_ctm(CTMSize.XL, device=device, **kwargs)


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Scaled CTM Configurations")
    print("=" * 60)

    # Show all configurations
    print("\n" + "-" * 40)
    print("Available Configurations:")
    print("-" * 40)

    for size_name, config in get_all_configs().items():
        print(f"\n{size_name.upper()}:")
        print(f"  Feature dim: {config.feature_dim}")
        print(f"  Memory length: {config.memory_length}")
        print(f"  Iterations: {config.iterations}")
        print(f"  Thought dim: {config.thought_dim}")
        print(f"  Est. params: {config.estimated_params:,}")

    # Memory estimates
    print("\n" + "-" * 40)
    print("Memory Estimates (batch_size=1, float32):")
    print("-" * 40)

    for size in CTMSize:
        memory = estimate_memory(size)
        print(f"\n{size.value.upper()}:")
        print(f"  Parameters: {memory['parameters_mb']:.1f} MB")
        print(f"  Activations: {memory['activations_mb']:.1f} MB")
        print(f"  Training total: {memory['total_training_mb']:.1f} MB")
        print(f"  Inference total: {memory['total_inference_mb']:.1f} MB")

    # Size recommendation
    print("\n" + "-" * 40)
    print("Size Recommendations:")
    print("-" * 40)

    for memory_gb in [1, 4, 8, 16]:
        recommended = recommend_size(memory_gb, batch_size=8, training=True)
        print(f"  {memory_gb} GB available -> {recommended.value}")

    # Create and test different sizes
    print("\n" + "-" * 40)
    print("Creating CTMs of each size:")
    print("-" * 40)

    for size in [CTMSize.SMALL, CTMSize.MEDIUM]:
        print(f"\nCreating {size.value} CTM...")
        ctm = create_ctm(size)

        # Initialize lazy modules
        dummy = torch.randint(0, 11, (1, 5, 4))
        with torch.no_grad():
            _ = ctm(dummy, max_iterations=1)

        actual_params = ctm.get_num_parameters()
        config = get_config(size)
        print(f"  Estimated: {config.estimated_params:,}")
        print(f"  Actual: {actual_params:,}")

    # Test different CTM types
    print("\n" + "-" * 40)
    print("Creating different CTM types (small):")
    print("-" * 40)

    for ctm_type in CTMType:
        print(f"\nCreating {ctm_type.value} CTM...")
        try:
            ctm = create_ctm(CTMSize.SMALL, ctm_type)

            # Initialize
            dummy = torch.randn(1, 20)
            with torch.no_grad():
                _ = ctm(dummy, max_iterations=2)

            params = sum(p.numel() for p in ctm.parameters())
            print(f"  Type: {ctm_type.value}")
            print(f"  Parameters: {params:,}")
        except Exception as e:
            print(f"  Error: {e}")

    print("\n" + "=" * 60)
    print("Scaled CTM tests completed!")
    print("=" * 60)
