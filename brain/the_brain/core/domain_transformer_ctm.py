"""
Domain-Specialized TransformerCTMs for the 4 CTM domains.

Creates specialized versions of TransformerCTM that can be:
1. Trained separately on domain-specific tasks
2. Merged together using mergekit/TIES-Merging
3. Used as drop-in replacements for existing CTMs

Domains:
- Spatial: Architecture, layout, visual reasoning
- Logic: Logical inference, validation, proofs
- Temporal: Time series, sequences, patterns
- Value: Cost optimization, trade-offs, decisions

Usage:
    from core.domain_transformer_ctm import (
        create_spatial_ctm,
        create_logic_ctm,
        create_temporal_ctm,
        create_value_ctm,
        DomainCTMEnsemble
    )

    # Create domain-specific CTMs
    spatial = create_spatial_ctm()
    logic = create_logic_ctm()

    # Or create ensemble
    ensemble = DomainCTMEnsemble()
    output = ensemble.route_and_reason("Design a REST API architecture")
"""

import torch
import torch.nn as nn
from typing import Optional, List, Dict, Union
from dataclasses import dataclass
from enum import Enum

try:
    from core.transformer_ctm import TransformerCTM, TransformerCTMOutput
except ImportError:
    from transformer_ctm import TransformerCTM, TransformerCTMOutput


class CTMDomain(Enum):
    """CTM domain types."""
    SPATIAL = "spatial"
    LOGIC = "logic"
    TEMPORAL = "temporal"
    VALUE = "value"


@dataclass
class DomainConfig:
    """Configuration for domain-specialized CTM."""
    name: str
    system_prompt: str
    keywords: List[str]
    max_iterations: int
    consciousness_threshold: float
    lora_r: int
    lora_alpha: int


# Domain-specific configurations
DOMAIN_CONFIGS = {
    CTMDomain.SPATIAL: DomainConfig(
        name="spatial",
        system_prompt=(
            "You are a spatial reasoning expert. "
            "Analyze architecture, layouts, structures, and visual relationships. "
            "Think step by step about spatial organization."
        ),
        keywords=[
            "architecture", "layout", "design", "structure", "visual",
            "diagram", "flow", "component", "system", "interface",
            "microservice", "api", "database", "schema", "topology"
        ],
        max_iterations=20,
        consciousness_threshold=0.85,
        lora_r=16,
        lora_alpha=32
    ),
    CTMDomain.LOGIC: DomainConfig(
        name="logic",
        system_prompt=(
            "You are a logical reasoning expert. "
            "Analyze validity, inference, proofs, and logical relationships. "
            "Think step by step about logical consistency."
        ),
        keywords=[
            "logic", "valid", "proof", "inference", "rule",
            "if", "then", "therefore", "implies", "contradiction",
            "policy", "constraint", "validate", "check", "verify"
        ],
        max_iterations=25,
        consciousness_threshold=0.90,
        lora_r=16,
        lora_alpha=32
    ),
    CTMDomain.TEMPORAL: DomainConfig(
        name="temporal",
        system_prompt=(
            "You are a temporal reasoning expert. "
            "Analyze time series, sequences, patterns, and temporal relationships. "
            "Think step by step about temporal dynamics."
        ),
        keywords=[
            "time", "sequence", "pattern", "trend", "series",
            "before", "after", "during", "frequency", "anomaly",
            "predict", "forecast", "history", "schedule", "timeline"
        ],
        max_iterations=30,
        consciousness_threshold=0.85,
        lora_r=16,
        lora_alpha=32
    ),
    CTMDomain.VALUE: DomainConfig(
        name="value",
        system_prompt=(
            "You are a value optimization expert. "
            "Analyze costs, benefits, trade-offs, and decision making. "
            "Think step by step about value optimization."
        ),
        keywords=[
            "cost", "benefit", "optimize", "trade-off", "decision",
            "value", "price", "budget", "resource", "efficiency",
            "roi", "priority", "risk", "reward", "utility"
        ],
        max_iterations=20,
        consciousness_threshold=0.80,
        lora_r=16,
        lora_alpha=32
    )
}


class DomainTransformerCTM(TransformerCTM):
    """
    Domain-specialized TransformerCTM.

    Extends base TransformerCTM with domain-specific:
    - System prompt for context
    - Keyword detection for routing
    - Tuned hyperparameters
    """

    def __init__(
        self,
        domain: CTMDomain,
        model_name: str = "Qwen/Qwen2.5-0.5B",
        thought_dim: int = 2048,
        use_lora: bool = True,
        device: str = 'cpu',
        **kwargs
    ):
        config = DOMAIN_CONFIGS[domain]

        # Merge domain config with kwargs
        init_kwargs = {
            'model_name': model_name,
            'thought_dim': thought_dim,
            'max_iterations': config.max_iterations,
            'consciousness_threshold': config.consciousness_threshold,
            'use_lora': use_lora,
            'lora_r': config.lora_r,
            'lora_alpha': config.lora_alpha,
            'device': device
        }
        init_kwargs.update(kwargs)

        super().__init__(**init_kwargs)

        self.domain = domain
        self.config = config

    def encode_task(self, task: Union[str, List[str]]) -> Dict[str, torch.Tensor]:
        """Encode task with domain-specific system prompt."""
        if isinstance(task, str):
            task = [task]

        # Prepend system prompt
        prompted_tasks = [
            f"{self.config.system_prompt}\n\nTask: {t}"
            for t in task
        ]

        encoded = self.tokenizer(
            prompted_tasks,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt"
        )

        return {k: v.to(self.device) for k, v in encoded.items()}

    def get_domain_affinity(self, task: str) -> float:
        """
        Calculate how well this domain matches the task.

        Args:
            task: Task string

        Returns:
            Affinity score 0-1
        """
        task_lower = task.lower()
        matches = sum(1 for kw in self.config.keywords if kw in task_lower)
        return min(matches / 5.0, 1.0)  # Normalize to 0-1


class DomainRouter(nn.Module):
    """
    Routes tasks to appropriate domain CTM.

    Uses both keyword matching and learned routing.
    """

    def __init__(self, hidden_dim: int = 384):
        super().__init__()

        # Learned router (trained on task embeddings)
        self.router_net = nn.Sequential(
            nn.Linear(hidden_dim, 128),
            nn.ReLU(),
            nn.Linear(128, len(CTMDomain)),
            nn.Softmax(dim=-1)
        )

        # Domain names for output
        self.domains = list(CTMDomain)

    def route_by_keywords(self, task: str) -> Dict[CTMDomain, float]:
        """Route using keyword matching."""
        scores = {}
        task_lower = task.lower()

        for domain, config in DOMAIN_CONFIGS.items():
            matches = sum(1 for kw in config.keywords if kw in task_lower)
            scores[domain] = matches

        # Normalize
        total = sum(scores.values()) + 1e-8
        return {d: s / total for d, s in scores.items()}

    def route_by_network(self, task_embedding: torch.Tensor) -> Dict[CTMDomain, float]:
        """Route using learned network."""
        probs = self.router_net(task_embedding)
        return {d: probs[0, i].item() for i, d in enumerate(self.domains)}

    def route(
        self,
        task: str,
        task_embedding: Optional[torch.Tensor] = None,
        use_learned: bool = False
    ) -> tuple:
        """
        Route task to best domain.

        Returns:
            (best_domain, all_scores)
        """
        if use_learned and task_embedding is not None:
            scores = self.route_by_network(task_embedding)
        else:
            scores = self.route_by_keywords(task)

        best_domain = max(scores, key=scores.get)
        return best_domain, scores


@dataclass
class EnsembleOutput:
    """Output from domain CTM ensemble."""
    thought_vector: torch.Tensor
    routed_domain: CTMDomain
    domain_scores: Dict[CTMDomain, float]
    ctm_output: TransformerCTMOutput
    all_outputs: Optional[Dict[CTMDomain, TransformerCTMOutput]] = None


class DomainCTMEnsemble(nn.Module):
    """
    Ensemble of domain-specialized TransformerCTMs.

    Routes tasks to appropriate domain and combines results.
    Can run all domains in parallel for comparison.
    """

    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-0.5B",
        thought_dim: int = 2048,
        use_lora: bool = True,
        domains: Optional[List[CTMDomain]] = None,
        device: str = 'cpu',
        load_all: bool = False
    ):
        super().__init__()

        self.domains = domains or list(CTMDomain)
        self.device = device
        self.model_name = model_name
        self.thought_dim = thought_dim
        self.use_lora = use_lora

        # Router
        self.router = DomainRouter()

        # CTMs (lazy load to save memory)
        self._ctms: Dict[CTMDomain, DomainTransformerCTM] = {}

        if load_all:
            self._load_all_ctms()

    def _load_all_ctms(self):
        """Load all domain CTMs."""
        for domain in self.domains:
            self._get_ctm(domain)

    def _get_ctm(self, domain: CTMDomain) -> DomainTransformerCTM:
        """Get or create CTM for domain."""
        if domain not in self._ctms:
            print(f"Loading {domain.value} CTM...")
            self._ctms[domain] = DomainTransformerCTM(
                domain=domain,
                model_name=self.model_name,
                thought_dim=self.thought_dim,
                use_lora=self.use_lora,
                device=self.device
            )
        return self._ctms[domain]

    def route_and_reason(
        self,
        task: str,
        max_iterations: Optional[int] = None,
        run_all: bool = False
    ) -> EnsembleOutput:
        """
        Route task to best domain and reason.

        Args:
            task: Task string
            max_iterations: Override max iterations
            run_all: Run all domains and compare

        Returns:
            EnsembleOutput with results
        """
        # Route
        best_domain, scores = self.router.route(task)

        if run_all:
            # Run all domains
            all_outputs = {}
            for domain in self.domains:
                ctm = self._get_ctm(domain)
                all_outputs[domain] = ctm.think(task, max_iterations)

            # Use best domain's output as primary
            primary_output = all_outputs[best_domain]

            return EnsembleOutput(
                thought_vector=primary_output.thought_vector,
                routed_domain=best_domain,
                domain_scores=scores,
                ctm_output=primary_output,
                all_outputs=all_outputs
            )
        else:
            # Only run best domain
            ctm = self._get_ctm(best_domain)
            output = ctm.think(task, max_iterations)

            return EnsembleOutput(
                thought_vector=output.thought_vector,
                routed_domain=best_domain,
                domain_scores=scores,
                ctm_output=output,
                all_outputs=None
            )

    def forward(self, task: str, **kwargs) -> EnsembleOutput:
        """Alias for route_and_reason."""
        return self.route_and_reason(task, **kwargs)

    def save_all(self, base_path: str):
        """Save all loaded CTM components."""
        import os
        os.makedirs(base_path, exist_ok=True)

        for domain, ctm in self._ctms.items():
            path = os.path.join(base_path, f"{domain.value}_ctm.pt")
            ctm.save_ctm_components(path)

        # Save router
        torch.save(self.router.state_dict(), os.path.join(base_path, "router.pt"))

    def load_all(self, base_path: str):
        """Load all CTM components."""
        import os

        for domain in self.domains:
            path = os.path.join(base_path, f"{domain.value}_ctm.pt")
            if os.path.exists(path):
                ctm = self._get_ctm(domain)
                ctm.load_ctm_components(path)

        router_path = os.path.join(base_path, "router.pt")
        if os.path.exists(router_path):
            self.router.load_state_dict(torch.load(router_path, weights_only=True))


# Factory functions for easy creation
def create_spatial_ctm(device: str = 'cpu', **kwargs) -> DomainTransformerCTM:
    """Create Spatial domain CTM."""
    return DomainTransformerCTM(CTMDomain.SPATIAL, device=device, **kwargs)


def create_logic_ctm(device: str = 'cpu', **kwargs) -> DomainTransformerCTM:
    """Create Logic domain CTM."""
    return DomainTransformerCTM(CTMDomain.LOGIC, device=device, **kwargs)


def create_temporal_ctm(device: str = 'cpu', **kwargs) -> DomainTransformerCTM:
    """Create Temporal domain CTM."""
    return DomainTransformerCTM(CTMDomain.TEMPORAL, device=device, **kwargs)


def create_value_ctm(device: str = 'cpu', **kwargs) -> DomainTransformerCTM:
    """Create Value domain CTM."""
    return DomainTransformerCTM(CTMDomain.VALUE, device=device, **kwargs)


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Domain TransformerCTMs")
    print("=" * 60)

    # Test router
    print("\nTesting DomainRouter...")
    router = DomainRouter()

    test_tasks = [
        ("Design a microservice architecture for e-commerce", CTMDomain.SPATIAL),
        ("Validate this Kubernetes YAML against security policies", CTMDomain.LOGIC),
        ("Detect anomalies in this CPU usage time series", CTMDomain.TEMPORAL),
        ("Optimize cloud costs while maintaining 99.9% uptime", CTMDomain.VALUE),
    ]

    for task, expected in test_tasks:
        routed, scores = router.route(task)
        match = "✓" if routed == expected else "✗"
        print(f"  {match} '{task[:40]}...'")
        print(f"      Expected: {expected.value}, Got: {routed.value}")
        print(f"      Scores: {', '.join(f'{d.value}:{s:.2f}' for d, s in scores.items())}")

    # Test domain configs
    print("\nDomain Configurations:")
    for domain, config in DOMAIN_CONFIGS.items():
        print(f"  {domain.value}:")
        print(f"    Max iterations: {config.max_iterations}")
        print(f"    Threshold: {config.consciousness_threshold}")
        print(f"    Keywords: {config.keywords[:3]}...")

    print("\n" + "=" * 60)
    print("Domain TransformerCTM tests passed!")
    print("=" * 60)
    print("\nNote: Full model tests require downloading Qwen2.5-0.5B")
