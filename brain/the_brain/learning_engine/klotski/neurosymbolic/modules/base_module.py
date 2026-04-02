"""
Base Brain Module

Abstract base class for all neural brain modules.
Each module represents a functional brain area with specific processing.
"""

import torch
import torch.nn as nn
from abc import ABC, abstractmethod
from typing import Dict, Tuple, Optional


class BrainModule(nn.Module, ABC):
    """
    Abstract base class for brain modules

    All modules implement:
    - forward(): Process input and return output
    - get_state(): Return internal state (for working memory)
    - reset_state(): Reset internal state
    - get_info(): Return module information
    """

    def __init__(
        self,
        module_id: str,
        module_name: str,
        input_dim: int,
        output_dim: int,
        brodmann_areas: str
    ):
        """
        Initialize brain module

        Args:
            module_id: Module identifier (VIS, AUD, etc.)
            module_name: Human-readable name
            input_dim: Input dimension
            output_dim: Output dimension
            brodmann_areas: Brodmann areas (e.g., "17-19")
        """
        super().__init__()

        self.module_id = module_id
        self.module_name = module_name
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.brodmann_areas = brodmann_areas

        # Internal state (optional, for recurrent modules)
        self._state = None

    @abstractmethod
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through module

        Args:
            x: Input tensor

        Returns:
            Output tensor
        """
        pass

    def get_state(self) -> Optional[torch.Tensor]:
        """
        Get current internal state

        Returns:
            State tensor or None
        """
        return self._state

    def reset_state(self):
        """Reset internal state to None"""
        self._state = None

    def get_info(self) -> Dict[str, any]:
        """
        Get module information

        Returns:
            Dict with module metadata
        """
        return {
            'module_id': self.module_id,
            'module_name': self.module_name,
            'input_dim': self.input_dim,
            'output_dim': self.output_dim,
            'brodmann_areas': self.brodmann_areas,
            'num_parameters': sum(p.numel() for p in self.parameters()),
            'has_state': self._state is not None
        }

    def __repr__(self):
        return (
            f"{self.__class__.__name__}("
            f"id={self.module_id}, "
            f"in={self.input_dim}, "
            f"out={self.output_dim}, "
            f"BA={self.brodmann_areas})"
        )


class IdentityModule(BrainModule):
    """Simple identity module for testing"""

    def __init__(self, module_id: str, dim: int):
        super().__init__(
            module_id=module_id,
            module_name="Identity",
            input_dim=dim,
            output_dim=dim,
            brodmann_areas="N/A"
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x


if __name__ == "__main__":
    # Test base module
    print("Testing BrainModule base class...")

    module = IdentityModule("TEST", dim=128)
    print(f"\nModule: {module}")

    info = module.get_info()
    print("\nModule Info:")
    for key, value in info.items():
        print(f"  {key}: {value}")

    # Test forward pass
    x = torch.randn(4, 128)  # batch_size=4, dim=128
    y = module(x)
    print(f"\nInput shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Outputs match inputs: {torch.allclose(x, y)}")

    # Test state
    print(f"\nInitial state: {module.get_state()}")
    module._state = torch.randn(4, 64)
    print(f"After setting state: {module.get_state().shape}")
    module.reset_state()
    print(f"After reset: {module.get_state()}")
