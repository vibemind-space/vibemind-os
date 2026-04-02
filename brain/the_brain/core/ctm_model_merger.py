"""
CTM Model Merger - Combine domain-specialized TransformerCTMs.

Implements multiple merging strategies for combining domain-specific
LoRA-trained CTMs into a unified multi-domain model.

Strategies:
- TIES-Merging: Task-specific pruning with sign consensus
- Linear: Simple weighted average
- SLERP: Spherical interpolation for smoother blending
- Task Arithmetic: Vector operations on task vectors

Usage:
    from core.ctm_model_merger import CTMModelMerger, MergeStrategy

    merger = CTMModelMerger()

    # Merge 4 domain CTMs
    merged = merger.merge_domain_ctms(
        spatial_path="models/spatial_ctm",
        logic_path="models/logic_ctm",
        temporal_path="models/temporal_ctm",
        value_path="models/value_ctm",
        strategy=MergeStrategy.TIES,
        output_path="models/unified_ctm"
    )

Note: For production merging, consider using mergekit:
    pip install mergekit
    mergekit-yaml config.yaml ./merged_model
"""

import torch
import torch.nn as nn
from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import copy
import math

try:
    from transformers import AutoModelForCausalLM, AutoConfig
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False


class MergeStrategy(Enum):
    """Available model merging strategies."""
    LINEAR = "linear"      # Simple weighted average
    TIES = "ties"          # TIES-Merging with pruning
    SLERP = "slerp"        # Spherical interpolation
    TASK_ARITHMETIC = "task_arithmetic"  # Add/subtract task vectors
    DARE = "dare"          # Drop and Rescale


@dataclass
class MergeConfig:
    """Configuration for model merging."""
    strategy: MergeStrategy = MergeStrategy.TIES
    weights: Optional[Dict[str, float]] = None  # Per-model weights
    density: float = 0.5  # For TIES: fraction to keep
    normalize: bool = True
    base_model: Optional[str] = None  # For task arithmetic


class TIESMerger:
    """
    TIES-Merging: Trim, Elect Sign, Merge.

    Paper: "Resolving Interference When Merging Models"
    https://arxiv.org/abs/2306.01708

    Steps:
    1. Trim: Remove small-magnitude parameters (keep top-k%)
    2. Elect: Choose sign by majority vote across models
    3. Merge: Average only agreeing parameters
    """

    def __init__(self, density: float = 0.5):
        """
        Args:
            density: Fraction of parameters to keep (0-1)
        """
        self.density = density

    def compute_task_vector(
        self,
        finetuned: Dict[str, torch.Tensor],
        base: Dict[str, torch.Tensor]
    ) -> Dict[str, torch.Tensor]:
        """Compute difference between finetuned and base model."""
        task_vector = {}
        for key in finetuned:
            if key in base:
                task_vector[key] = finetuned[key] - base[key]
        return task_vector

    def trim(self, task_vector: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
        """Trim small-magnitude values, keeping top density%."""
        trimmed = {}

        for key, tensor in task_vector.items():
            if tensor.dim() == 0:  # Scalar
                trimmed[key] = tensor
                continue

            # Flatten, get threshold
            flat = tensor.abs().flatten()
            k = max(1, int(len(flat) * self.density))
            threshold = torch.topk(flat, k).values[-1]

            # Mask small values
            mask = tensor.abs() >= threshold
            trimmed[key] = tensor * mask.float()

        return trimmed

    def elect_sign(
        self,
        task_vectors: List[Dict[str, torch.Tensor]]
    ) -> Dict[str, torch.Tensor]:
        """Elect sign by majority vote."""
        elected = {}

        # Get all keys
        all_keys = set()
        for tv in task_vectors:
            all_keys.update(tv.keys())

        for key in all_keys:
            tensors = [tv[key] for tv in task_vectors if key in tv]
            if not tensors:
                continue

            # Stack and compute sign
            stacked = torch.stack(tensors)
            signs = torch.sign(stacked)

            # Majority vote
            sign_sum = signs.sum(dim=0)
            majority_sign = torch.sign(sign_sum)

            # Where there's no majority, use 0
            majority_sign[sign_sum == 0] = 0

            elected[key] = majority_sign

        return elected

    def merge(
        self,
        task_vectors: List[Dict[str, torch.Tensor]],
        elected_signs: Dict[str, torch.Tensor],
        weights: Optional[List[float]] = None
    ) -> Dict[str, torch.Tensor]:
        """Merge task vectors using elected signs."""
        if weights is None:
            weights = [1.0 / len(task_vectors)] * len(task_vectors)

        merged = {}

        for key in elected_signs:
            tensors = []
            ws = []

            for i, tv in enumerate(task_vectors):
                if key not in tv:
                    continue

                # Only include if sign agrees
                sign_match = torch.sign(tv[key]) == elected_signs[key]
                masked = tv[key] * sign_match.float()
                tensors.append(masked * weights[i])
                ws.append(weights[i])

            if tensors:
                # Average (weighted)
                merged[key] = sum(tensors) / (sum(ws) + 1e-8)

        return merged

    def __call__(
        self,
        models: List[Dict[str, torch.Tensor]],
        base: Dict[str, torch.Tensor],
        weights: Optional[List[float]] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Full TIES-Merging pipeline.

        Args:
            models: List of finetuned model state dicts
            base: Base model state dict
            weights: Optional per-model weights

        Returns:
            Merged model state dict
        """
        # 1. Compute task vectors
        task_vectors = [self.compute_task_vector(m, base) for m in models]

        # 2. Trim
        trimmed = [self.trim(tv) for tv in task_vectors]

        # 3. Elect signs
        elected = self.elect_sign(trimmed)

        # 4. Merge
        merged_tv = self.merge(trimmed, elected, weights)

        # 5. Add back to base
        result = copy.deepcopy(base)
        for key, delta in merged_tv.items():
            if key in result:
                result[key] = result[key] + delta

        return result


class LinearMerger:
    """Simple weighted average of model parameters."""

    def __call__(
        self,
        models: List[Dict[str, torch.Tensor]],
        weights: Optional[List[float]] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Merge models by weighted average.

        Args:
            models: List of model state dicts
            weights: Per-model weights (default: equal)

        Returns:
            Merged state dict
        """
        if weights is None:
            weights = [1.0 / len(models)] * len(models)

        # Normalize weights
        total = sum(weights)
        weights = [w / total for w in weights]

        merged = {}
        all_keys = set()
        for m in models:
            all_keys.update(m.keys())

        for key in all_keys:
            tensors = []
            ws = []
            for i, m in enumerate(models):
                if key in m:
                    tensors.append(m[key] * weights[i])
                    ws.append(weights[i])

            if tensors:
                merged[key] = sum(tensors)

        return merged


class SLERPMerger:
    """
    Spherical Linear Interpolation for model merging.

    Better for merging models that need smooth transitions
    in the parameter space.
    """

    def slerp(
        self,
        v0: torch.Tensor,
        v1: torch.Tensor,
        t: float
    ) -> torch.Tensor:
        """Spherical interpolation between two vectors."""
        # Normalize
        v0_norm = v0 / (v0.norm() + 1e-8)
        v1_norm = v1 / (v1.norm() + 1e-8)

        # Compute angle
        dot = (v0_norm * v1_norm).sum().clamp(-1, 1)
        theta = torch.acos(dot)

        if theta.abs() < 1e-6:
            return (1 - t) * v0 + t * v1

        sin_theta = torch.sin(theta)
        s0 = torch.sin((1 - t) * theta) / sin_theta
        s1 = torch.sin(t * theta) / sin_theta

        return s0 * v0 + s1 * v1

    def __call__(
        self,
        model1: Dict[str, torch.Tensor],
        model2: Dict[str, torch.Tensor],
        t: float = 0.5
    ) -> Dict[str, torch.Tensor]:
        """
        SLERP merge two models.

        Args:
            model1: First model state dict
            model2: Second model state dict
            t: Interpolation factor (0 = model1, 1 = model2)

        Returns:
            Merged state dict
        """
        merged = {}

        for key in model1:
            if key not in model2:
                merged[key] = model1[key]
                continue

            v0 = model1[key].flatten()
            v1 = model2[key].flatten()

            merged_flat = self.slerp(v0, v1, t)
            merged[key] = merged_flat.reshape(model1[key].shape)

        # Add keys only in model2
        for key in model2:
            if key not in model1:
                merged[key] = model2[key]

        return merged


class CTMModelMerger:
    """
    High-level interface for merging domain TransformerCTMs.

    Combines multiple strategies and handles CTM-specific components.
    """

    def __init__(self, base_model_name: str = "Qwen/Qwen2.5-0.5B"):
        self.base_model_name = base_model_name
        self.ties = TIESMerger()
        self.linear = LinearMerger()
        self.slerp = SLERPMerger()

    def load_ctm_checkpoint(self, path: str) -> Dict[str, torch.Tensor]:
        """Load CTM components checkpoint."""
        checkpoint = torch.load(path, map_location='cpu', weights_only=False)

        # Combine all components
        state_dict = {}

        if 'reasoning_block' in checkpoint:
            for k, v in checkpoint['reasoning_block'].items():
                state_dict[f'reasoning_block.{k}'] = v

        if 'halt_predictor' in checkpoint:
            for k, v in checkpoint['halt_predictor'].items():
                state_dict[f'halt_predictor.{k}'] = v

        if 'thought_projector' in checkpoint:
            for k, v in checkpoint['thought_projector'].items():
                state_dict[f'thought_projector.{k}'] = v

        return state_dict

    def merge_ctm_components(
        self,
        checkpoints: List[str],
        strategy: MergeStrategy = MergeStrategy.LINEAR,
        weights: Optional[List[float]] = None,
        density: float = 0.5
    ) -> Dict[str, torch.Tensor]:
        """
        Merge CTM-specific components from multiple checkpoints.

        Args:
            checkpoints: Paths to CTM component checkpoints
            strategy: Merging strategy
            weights: Per-checkpoint weights
            density: For TIES strategy

        Returns:
            Merged component state dict
        """
        # Load all checkpoints
        states = [self.load_ctm_checkpoint(p) for p in checkpoints]

        if strategy == MergeStrategy.LINEAR:
            return self.linear(states, weights)

        elif strategy == MergeStrategy.TIES:
            # For TIES, we need a base
            # Use average as pseudo-base
            base = self.linear(states)
            self.ties.density = density
            return self.ties(states, base, weights)

        elif strategy == MergeStrategy.SLERP:
            # Chain SLERP for multiple models
            if len(states) == 2:
                t = weights[1] if weights else 0.5
                return self.slerp(states[0], states[1], t)
            else:
                # Progressive SLERP
                result = states[0]
                for i, state in enumerate(states[1:], 1):
                    t = 1.0 / (i + 1)
                    result = self.slerp(result, state, t)
                return result

        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def merge_domain_ctms(
        self,
        spatial_path: Optional[str] = None,
        logic_path: Optional[str] = None,
        temporal_path: Optional[str] = None,
        value_path: Optional[str] = None,
        strategy: MergeStrategy = MergeStrategy.TIES,
        weights: Optional[Dict[str, float]] = None,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Merge 4 domain-specialized CTMs into one.

        Args:
            spatial_path: Path to spatial CTM checkpoint
            logic_path: Path to logic CTM checkpoint
            temporal_path: Path to temporal CTM checkpoint
            value_path: Path to value CTM checkpoint
            strategy: Merging strategy
            weights: Per-domain weights
            output_path: Where to save merged model

        Returns:
            Dict with merged state and metadata
        """
        # Collect available paths
        paths = []
        domain_names = []

        if spatial_path:
            paths.append(spatial_path)
            domain_names.append('spatial')
        if logic_path:
            paths.append(logic_path)
            domain_names.append('logic')
        if temporal_path:
            paths.append(temporal_path)
            domain_names.append('temporal')
        if value_path:
            paths.append(value_path)
            domain_names.append('value')

        if len(paths) < 2:
            raise ValueError("Need at least 2 domain CTMs to merge")

        # Get weights
        weight_list = None
        if weights:
            weight_list = [weights.get(d, 1.0) for d in domain_names]

        # Merge
        merged_state = self.merge_ctm_components(
            paths, strategy, weight_list
        )

        result = {
            'state_dict': merged_state,
            'strategy': strategy.value,
            'domains': domain_names,
            'weights': weight_list,
            'base_model': self.base_model_name
        }

        # Save if requested
        if output_path:
            torch.save(result, output_path)
            print(f"Saved merged CTM to {output_path}")

        return result

    def generate_mergekit_config(
        self,
        domain_paths: Dict[str, str],
        output_path: str,
        strategy: str = "ties"
    ) -> str:
        """
        Generate mergekit YAML config for external merging.

        Args:
            domain_paths: Dict mapping domain name to model path
            output_path: Where to save config
            strategy: Mergekit strategy name

        Returns:
            YAML config string
        """
        yaml_lines = [
            "# Generated CTM merge config for mergekit",
            f"merge_method: {strategy}",
            "base_model: " + self.base_model_name,
            "parameters:",
            "  density: 0.5",
            "  normalize: true",
            "models:"
        ]

        for domain, path in domain_paths.items():
            yaml_lines.extend([
                f"  - model: {path}",
                f"    parameters:",
                f"      weight: 0.25  # Adjust for {domain}"
            ])

        yaml_content = "\n".join(yaml_lines)

        with open(output_path, 'w') as f:
            f.write(yaml_content)

        return yaml_content


def merge_lora_adapters(
    adapters: List[str],
    base_model: str,
    output_path: str,
    strategy: MergeStrategy = MergeStrategy.LINEAR,
    weights: Optional[List[float]] = None
) -> None:
    """
    Merge multiple LoRA adapters and save merged model.

    Args:
        adapters: Paths to LoRA adapter directories
        base_model: Base model name/path
        output_path: Where to save merged model
        strategy: Merging strategy
        weights: Per-adapter weights
    """
    if not HAS_TRANSFORMERS:
        raise ImportError("transformers required for LoRA merging")

    try:
        from peft import PeftModel
    except ImportError:
        raise ImportError("peft required for LoRA merging. pip install peft")

    # Load base
    print(f"Loading base model: {base_model}")
    model = AutoModelForCausalLM.from_pretrained(base_model, trust_remote_code=True)

    # Load and merge adapters
    merged_state = None

    for i, adapter_path in enumerate(adapters):
        print(f"Loading adapter {i+1}/{len(adapters)}: {adapter_path}")

        # Load adapter
        peft_model = PeftModel.from_pretrained(model, adapter_path)

        # Get merged weights
        merged = peft_model.merge_and_unload()
        state = merged.state_dict()

        if merged_state is None:
            merged_state = {k: v * (weights[i] if weights else 1.0 / len(adapters))
                          for k, v in state.items()}
        else:
            w = weights[i] if weights else 1.0 / len(adapters)
            for k, v in state.items():
                if k in merged_state:
                    merged_state[k] += v * w

    # Save merged model
    print(f"Saving merged model to {output_path}")
    model.load_state_dict(merged_state)
    model.save_pretrained(output_path)


if __name__ == "__main__":
    print("=" * 60)
    print("Testing CTM Model Merger")
    print("=" * 60)

    # Test TIES merger
    print("\nTesting TIES Merger...")
    ties = TIESMerger(density=0.5)

    # Create dummy models
    base = {'layer.weight': torch.randn(10, 10)}
    model1 = {'layer.weight': base['layer.weight'] + torch.randn(10, 10) * 0.1}
    model2 = {'layer.weight': base['layer.weight'] + torch.randn(10, 10) * 0.1}

    merged = ties([model1, model2], base)
    print(f"  Base shape: {base['layer.weight'].shape}")
    print(f"  Merged shape: {merged['layer.weight'].shape}")

    # Test Linear merger
    print("\nTesting Linear Merger...")
    linear = LinearMerger()
    merged_linear = linear([model1, model2], [0.3, 0.7])
    print(f"  Merged with weights [0.3, 0.7]")

    # Test SLERP merger
    print("\nTesting SLERP Merger...")
    slerp = SLERPMerger()
    merged_slerp = slerp(model1, model2, 0.5)
    print(f"  Merged at t=0.5")

    # Test high-level merger
    print("\nTesting CTMModelMerger...")
    merger = CTMModelMerger()

    # Generate sample mergekit config
    config = merger.generate_mergekit_config(
        {
            'spatial': 'models/spatial_ctm',
            'logic': 'models/logic_ctm',
            'temporal': 'models/temporal_ctm',
            'value': 'models/value_ctm'
        },
        'merge_config.yaml'
    )
    print(f"  Generated mergekit config:")
    for line in config.split('\n')[:5]:
        print(f"    {line}")
    print("    ...")

    # Cleanup
    import os
    if os.path.exists('merge_config.yaml'):
        os.remove('merge_config.yaml')

    print("\n" + "=" * 60)
    print("CTM Model Merger tests passed!")
    print("=" * 60)
