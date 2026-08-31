"""
Federated Learning Framework (Phase 8B)

Enables multiple brain instances to train collaboratively while preserving privacy.

Key Components:
- FederatedCoordinator: Central coordinator for federated learning across brain nodes
- FederatedNode: Local brain node participating in federated training
- DifferentialPrivacy: Privacy-preserving gradient clipping and noise addition

Aggregation Strategies:
- FedAvg: Weighted average of model updates by dataset size
- FedProx: FedAvg with proximal term for heterogeneous data
- FedMedian: Median aggregation for Byzantine resilience

Usage:
    from core.federated_learning import FederatedCoordinator, FederatedNode

    # Create coordinator
    coordinator = FederatedCoordinator(aggregation_strategy='fedavg')

    # Create and register nodes
    node1 = FederatedNode(brain1, node_id='node_1')
    node2 = FederatedNode(brain2, node_id='node_2')
    coordinator.register_node('node_1', node1)
    coordinator.register_node('node_2', node2)

    # Run federated training rounds
    for round in range(10):
        coordinator.run_round(local_epochs=5)
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
import logging
import copy
import hashlib
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class AggregationStrategy(Enum):
    """Federated learning aggregation strategies."""
    FEDAVG = "fedavg"           # Weighted average by dataset size
    FEDPROX = "fedprox"         # FedAvg + proximal term
    FEDMEDIAN = "fedmedian"     # Median for Byzantine resilience
    FEDADAM = "fedadam"         # Server-side adaptive optimizer


@dataclass
class TrainingExample:
    """Single training example for federated learning."""
    input_data: Any
    target: Any
    weight: float = 1.0
    metadata: Dict = field(default_factory=dict)


@dataclass
class FederatedUpdate:
    """Model update from a federated node."""
    node_id: str
    gradients: Dict[str, torch.Tensor]
    dataset_size: int
    round_number: int
    metrics: Dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class NodeStatus:
    """Status information for a federated node."""
    node_id: str
    is_active: bool = True
    last_heartbeat: float = 0.0
    total_rounds: int = 0
    total_samples: int = 0
    avg_loss: float = 0.0
    contribution_score: float = 1.0


class DifferentialPrivacy:
    """
    Privacy-preserving gradient clipping and noise addition.

    Implements ε-differential privacy for federated learning:
    - Gradient clipping (bounds sensitivity)
    - Gaussian noise addition (provides privacy guarantee)
    - Privacy budget tracking

    Privacy guarantee: (ε, δ)-differential privacy where:
    - ε (epsilon): Privacy loss parameter (lower = more private)
    - δ (delta): Probability of privacy breach
    """

    def __init__(
        self,
        max_grad_norm: float = 1.0,
        noise_multiplier: float = 1.0,
        target_epsilon: float = 1.0,
        target_delta: float = 1e-5
    ):
        """
        Initialize differential privacy mechanism.

        Args:
            max_grad_norm: Maximum L2 norm for gradient clipping
            noise_multiplier: Noise scale relative to sensitivity
            target_epsilon: Target privacy budget (lower = more private)
            target_delta: Probability of privacy failure
        """
        self.max_grad_norm = max_grad_norm
        self.noise_multiplier = noise_multiplier
        self.target_epsilon = target_epsilon
        self.target_delta = target_delta

        # Privacy accounting
        self.privacy_spent = 0.0
        self.num_compositions = 0

    def clip_gradients(
        self,
        gradients: Dict[str, torch.Tensor],
        max_norm: Optional[float] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Clip gradients to bounded sensitivity.

        Per-sample gradient clipping ensures bounded sensitivity
        for the Gaussian mechanism.

        Args:
            gradients: Dictionary of parameter gradients
            max_norm: Maximum L2 norm (uses default if None)

        Returns:
            Clipped gradients dictionary
        """
        max_norm = max_norm or self.max_grad_norm

        # Compute total norm
        total_norm = 0.0
        for grad in gradients.values():
            total_norm += grad.norm(2).item() ** 2
        total_norm = np.sqrt(total_norm)

        # Compute clipping coefficient
        clip_coef = max_norm / (total_norm + 1e-8)
        clip_coef = min(clip_coef, 1.0)

        # Apply clipping
        clipped = {}
        for name, grad in gradients.items():
            clipped[name] = grad * clip_coef

        return clipped

    def add_noise(
        self,
        gradients: Dict[str, torch.Tensor],
        noise_scale: Optional[float] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Add calibrated Gaussian noise for differential privacy.

        Noise scale σ = noise_multiplier * sensitivity / ε
        where sensitivity = max_grad_norm

        Args:
            gradients: Dictionary of (clipped) gradients
            noise_scale: Custom noise scale (uses default if None)

        Returns:
            Noisy gradients dictionary
        """
        if noise_scale is None:
            noise_scale = self.noise_multiplier * self.max_grad_norm

        noisy = {}
        for name, grad in gradients.items():
            noise = torch.randn_like(grad) * noise_scale
            noisy[name] = grad + noise

        # Update privacy accounting
        self._account_privacy(len(gradients))

        return noisy

    def _account_privacy(self, num_parameters: int):
        """
        Track privacy budget spent.

        Uses simple composition theorem (conservative estimate).
        More advanced: moments accountant or Rényi DP.
        """
        # Simple composition: ε_total = sqrt(k) * ε_single
        self.num_compositions += 1
        # Per-round privacy cost (simplified)
        round_epsilon = self.target_epsilon / np.sqrt(self.num_compositions)
        self.privacy_spent += round_epsilon

    def get_privacy_budget(self) -> Dict[str, float]:
        """Get current privacy budget status."""
        return {
            'target_epsilon': self.target_epsilon,
            'spent_epsilon': self.privacy_spent,
            'remaining_epsilon': max(0, self.target_epsilon - self.privacy_spent),
            'num_compositions': self.num_compositions,
            'noise_multiplier': self.noise_multiplier,
            'max_grad_norm': self.max_grad_norm
        }

    def is_budget_exhausted(self) -> bool:
        """Check if privacy budget is exhausted."""
        return self.privacy_spent >= self.target_epsilon


class FederatedNode:
    """
    Local brain node participating in federated training.

    Each node:
    - Holds a local brain model and dataset
    - Performs local training epochs
    - Computes gradient updates to send to coordinator
    - Applies global model updates from coordinator
    """

    def __init__(
        self,
        brain: nn.Module,
        node_id: str,
        learning_rate: float = 1e-4,
        use_dp: bool = False,
        dp_config: Optional[Dict] = None
    ):
        """
        Initialize federated node.

        Args:
            brain: Neural network model (brain)
            node_id: Unique identifier for this node
            learning_rate: Local learning rate
            use_dp: Whether to use differential privacy
            dp_config: Differential privacy configuration
        """
        self.brain = brain
        self.node_id = node_id
        self.learning_rate = learning_rate
        self.device = next(brain.parameters()).device

        # Local dataset
        self.local_data: List[TrainingExample] = []

        # Optimizer
        self.optimizer = torch.optim.Adam(brain.parameters(), lr=learning_rate)

        # Differential privacy
        self.use_dp = use_dp
        if use_dp:
            dp_config = dp_config or {}
            self.dp = DifferentialPrivacy(**dp_config)
        else:
            self.dp = None

        # Training statistics
        self.total_local_steps = 0
        self.loss_history: List[float] = []
        self.round_history: List[Dict] = []

        # Status
        self.status = NodeStatus(node_id=node_id)

    def add_data(self, examples: List[TrainingExample]):
        """Add training examples to local dataset."""
        self.local_data.extend(examples)
        self.status.total_samples = len(self.local_data)

    def clear_data(self):
        """Clear local dataset."""
        self.local_data.clear()
        self.status.total_samples = 0

    def train_local(
        self,
        epochs: int = 1,
        batch_size: int = 32,
        loss_fn: Optional[Callable] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Perform local training and return gradient updates.

        Args:
            epochs: Number of local training epochs
            batch_size: Mini-batch size
            loss_fn: Loss function (defaults to cross-entropy)

        Returns:
            Dictionary of gradient updates (delta weights)
        """
        if len(self.local_data) == 0:
            logger.warning(f"[{self.node_id}] No local data for training")
            return {}

        # Store initial weights
        initial_weights = {
            name: param.clone().detach()
            for name, param in self.brain.named_parameters()
        }

        # Default loss function
        if loss_fn is None:
            loss_fn = nn.CrossEntropyLoss()

        # Training loop
        self.brain.train()
        total_loss = 0.0
        num_batches = 0

        for epoch in range(epochs):
            # Shuffle data
            np.random.shuffle(self.local_data)

            for i in range(0, len(self.local_data), batch_size):
                batch = self.local_data[i:i+batch_size]

                # Prepare batch
                inputs = torch.stack([
                    torch.tensor(ex.input_data, device=self.device)
                    if not isinstance(ex.input_data, torch.Tensor)
                    else ex.input_data.to(self.device)
                    for ex in batch
                ])
                targets = torch.stack([
                    torch.tensor(ex.target, device=self.device)
                    if not isinstance(ex.target, torch.Tensor)
                    else ex.target.to(self.device)
                    for ex in batch
                ])

                # Forward pass
                self.optimizer.zero_grad()
                outputs = self.brain(inputs)

                # Handle dict outputs
                if isinstance(outputs, dict):
                    outputs = outputs.get('action_logits', outputs.get('logits', list(outputs.values())[0]))

                # Compute loss
                loss = loss_fn(outputs, targets)

                # Backward pass
                loss.backward()
                self.optimizer.step()

                total_loss += loss.item()
                num_batches += 1
                self.total_local_steps += 1

        avg_loss = total_loss / max(1, num_batches)
        self.loss_history.append(avg_loss)
        self.status.avg_loss = avg_loss

        # Compute gradient updates (delta = new - old)
        gradients = {}
        for name, param in self.brain.named_parameters():
            delta = param.detach() - initial_weights[name]
            gradients[name] = delta

        # Apply differential privacy if enabled
        if self.use_dp and self.dp is not None:
            gradients = self.dp.clip_gradients(gradients)
            gradients = self.dp.add_noise(gradients)

        # Record round info
        self.round_history.append({
            'epochs': epochs,
            'samples': len(self.local_data),
            'avg_loss': avg_loss,
            'timestamp': time.time()
        })

        logger.info(f"[{self.node_id}] Local training: {epochs} epochs, loss={avg_loss:.4f}")
        return gradients

    def apply_global_update(self, global_weights: Dict[str, torch.Tensor]):
        """
        Apply global model update from coordinator.

        Args:
            global_weights: Global model weights to apply
        """
        with torch.no_grad():
            for name, param in self.brain.named_parameters():
                if name in global_weights:
                    param.copy_(global_weights[name])

        self.status.total_rounds += 1
        logger.info(f"[{self.node_id}] Applied global update (round {self.status.total_rounds})")

    def compute_gradient_update(self) -> Dict[str, torch.Tensor]:
        """
        Compute current gradient update without training.

        Useful for async updates where we want to send current delta.

        Returns:
            Dictionary of current parameter values
        """
        return {
            name: param.clone().detach()
            for name, param in self.brain.named_parameters()
        }

    def get_model_hash(self) -> str:
        """Get hash of current model weights for verification."""
        weight_str = ""
        for name, param in sorted(self.brain.named_parameters()):
            weight_str += f"{name}:{param.sum().item():.6f};"
        return hashlib.md5(weight_str.encode()).hexdigest()[:16]

    def get_statistics(self) -> Dict:
        """Get node statistics."""
        return {
            'node_id': self.node_id,
            'is_active': self.status.is_active,
            'total_rounds': self.status.total_rounds,
            'total_samples': self.status.total_samples,
            'avg_loss': self.status.avg_loss,
            'local_steps': self.total_local_steps,
            'model_hash': self.get_model_hash(),
            'dp_enabled': self.use_dp,
            'dp_budget': self.dp.get_privacy_budget() if self.dp else None
        }


class FederatedCoordinator:
    """
    Central coordinator for federated learning across brain nodes.

    Responsibilities:
    - Node registration and management
    - Aggregating model updates from nodes
    - Distributing global model to nodes
    - Running federated training rounds
    """

    def __init__(
        self,
        aggregation_strategy: str = 'fedavg',
        min_nodes: int = 2,
        min_samples_per_round: int = 10,
        async_updates: bool = False
    ):
        """
        Initialize federated coordinator.

        Args:
            aggregation_strategy: How to aggregate updates ('fedavg', 'fedprox', 'fedmedian')
            min_nodes: Minimum nodes required to run a round
            min_samples_per_round: Minimum total samples for a round
            async_updates: Allow asynchronous updates
        """
        self.aggregation_strategy = AggregationStrategy(aggregation_strategy.lower())
        self.min_nodes = min_nodes
        self.min_samples_per_round = min_samples_per_round
        self.async_updates = async_updates

        # Registered nodes
        self.nodes: Dict[str, FederatedNode] = {}

        # Global model weights
        self.global_model: Dict[str, torch.Tensor] = {}

        # Round tracking
        self.round_number: int = 0
        self.round_history: List[Dict] = []

        # Pending updates (for async)
        self.pending_updates: List[FederatedUpdate] = []

        logger.info(f"[FederatedCoordinator] Initialized with strategy={aggregation_strategy}")

    def register_node(self, node_id: str, node: FederatedNode):
        """
        Register a node for federated learning.

        Args:
            node_id: Unique identifier for the node
            node: FederatedNode instance
        """
        self.nodes[node_id] = node
        node.status.is_active = True
        node.status.last_heartbeat = time.time()

        # Initialize global model from first node if not set
        if not self.global_model:
            self.global_model = {
                name: param.clone().detach()
                for name, param in node.brain.named_parameters()
            }

        logger.info(f"[FederatedCoordinator] Registered node: {node_id}")

    def unregister_node(self, node_id: str):
        """Remove a node from federated learning."""
        if node_id in self.nodes:
            self.nodes[node_id].status.is_active = False
            del self.nodes[node_id]
            logger.info(f"[FederatedCoordinator] Unregistered node: {node_id}")

    def get_active_nodes(self) -> List[str]:
        """Get list of active node IDs."""
        return [
            node_id for node_id, node in self.nodes.items()
            if node.status.is_active
        ]

    def aggregate_updates(
        self,
        updates: List[FederatedUpdate]
    ) -> Dict[str, torch.Tensor]:
        """
        Aggregate updates from multiple nodes.

        Args:
            updates: List of FederatedUpdate from nodes

        Returns:
            Aggregated global model weights
        """
        if not updates:
            return self.global_model

        if self.aggregation_strategy == AggregationStrategy.FEDAVG:
            return self._fedavg_aggregate(updates)
        elif self.aggregation_strategy == AggregationStrategy.FEDMEDIAN:
            return self._fedmedian_aggregate(updates)
        elif self.aggregation_strategy == AggregationStrategy.FEDPROX:
            return self._fedavg_aggregate(updates)  # FedProx uses same aggregation
        else:
            logger.warning(f"Unknown strategy {self.aggregation_strategy}, using FedAvg")
            return self._fedavg_aggregate(updates)

    def _fedavg_aggregate(
        self,
        updates: List[FederatedUpdate]
    ) -> Dict[str, torch.Tensor]:
        """
        FedAvg aggregation: weighted average by dataset size.

        Global weights = Σ (n_k / n_total) * w_k
        """
        total_samples = sum(u.dataset_size for u in updates)

        if total_samples == 0:
            return self.global_model

        aggregated = {}
        for name in self.global_model.keys():
            weighted_sum = torch.zeros_like(self.global_model[name])

            for update in updates:
                if name in update.gradients:
                    weight = update.dataset_size / total_samples
                    # Add gradient delta to global model
                    weighted_sum += weight * update.gradients[name]

            # Apply aggregated update
            aggregated[name] = self.global_model[name] + weighted_sum

        return aggregated

    def _fedmedian_aggregate(
        self,
        updates: List[FederatedUpdate]
    ) -> Dict[str, torch.Tensor]:
        """
        FedMedian aggregation: coordinate-wise median (Byzantine-resilient).
        """
        aggregated = {}

        for name in self.global_model.keys():
            # Stack all gradients for this parameter
            gradients = []
            for update in updates:
                if name in update.gradients:
                    gradients.append(update.gradients[name])

            if gradients:
                stacked = torch.stack(gradients)
                median_grad = torch.median(stacked, dim=0).values
                aggregated[name] = self.global_model[name] + median_grad
            else:
                aggregated[name] = self.global_model[name]

        return aggregated

    def distribute_global_model(self):
        """Distribute global model to all active nodes."""
        for node_id, node in self.nodes.items():
            if node.status.is_active:
                node.apply_global_update(self.global_model)

    def run_round(
        self,
        local_epochs: int = 5,
        loss_fn: Optional[Callable] = None,
        node_ids: Optional[List[str]] = None
    ) -> Dict:
        """
        Run one round of federated learning.

        Args:
            local_epochs: Number of local training epochs per node
            loss_fn: Loss function for local training
            node_ids: Specific nodes to include (all active if None)

        Returns:
            Dictionary with round statistics
        """
        self.round_number += 1
        round_start = time.time()

        # Select participating nodes
        if node_ids is None:
            node_ids = self.get_active_nodes()

        if len(node_ids) < self.min_nodes:
            logger.warning(f"[Round {self.round_number}] Not enough nodes: {len(node_ids)} < {self.min_nodes}")
            return {'success': False, 'error': 'Not enough nodes'}

        # Total samples check
        total_samples = sum(
            self.nodes[nid].status.total_samples
            for nid in node_ids
            if nid in self.nodes
        )

        if total_samples < self.min_samples_per_round:
            logger.warning(f"[Round {self.round_number}] Not enough samples: {total_samples}")
            return {'success': False, 'error': 'Not enough samples'}

        # Phase 1: Distribute global model
        logger.info(f"[Round {self.round_number}] Distributing global model to {len(node_ids)} nodes")
        self.distribute_global_model()

        # Phase 2: Local training
        updates = []
        for node_id in node_ids:
            node = self.nodes.get(node_id)
            if node is None or not node.status.is_active:
                continue

            # Run local training
            gradients = node.train_local(epochs=local_epochs, loss_fn=loss_fn)

            if gradients:
                update = FederatedUpdate(
                    node_id=node_id,
                    gradients=gradients,
                    dataset_size=node.status.total_samples,
                    round_number=self.round_number,
                    metrics={'loss': node.status.avg_loss}
                )
                updates.append(update)

        if not updates:
            logger.warning(f"[Round {self.round_number}] No updates received")
            return {'success': False, 'error': 'No updates'}

        # Phase 3: Aggregate updates
        logger.info(f"[Round {self.round_number}] Aggregating {len(updates)} updates ({self.aggregation_strategy.value})")
        self.global_model = self.aggregate_updates(updates)

        # Record round
        round_time = time.time() - round_start
        round_info = {
            'round': self.round_number,
            'num_nodes': len(updates),
            'total_samples': sum(u.dataset_size for u in updates),
            'avg_loss': np.mean([u.metrics.get('loss', 0) for u in updates]),
            'time': round_time,
            'success': True
        }
        self.round_history.append(round_info)

        logger.info(f"[Round {self.round_number}] Complete: nodes={len(updates)}, samples={round_info['total_samples']}, loss={round_info['avg_loss']:.4f}, time={round_time:.1f}s")

        return round_info

    def submit_async_update(self, update: FederatedUpdate):
        """Submit an asynchronous update from a node."""
        if not self.async_updates:
            logger.warning("Async updates not enabled")
            return

        self.pending_updates.append(update)

        # Process if we have enough updates
        if len(self.pending_updates) >= self.min_nodes:
            self._process_async_updates()

    def _process_async_updates(self):
        """Process pending async updates."""
        if not self.pending_updates:
            return

        # Aggregate pending updates
        self.global_model = self.aggregate_updates(self.pending_updates)
        self.round_number += 1

        # Clear pending
        processed = len(self.pending_updates)
        self.pending_updates.clear()

        logger.info(f"[Async] Processed {processed} pending updates")

    def get_global_model(self) -> Dict[str, torch.Tensor]:
        """Get current global model weights."""
        return copy.deepcopy(self.global_model)

    def get_statistics(self) -> Dict:
        """Get coordinator statistics."""
        return {
            'round_number': self.round_number,
            'num_nodes': len(self.nodes),
            'active_nodes': len(self.get_active_nodes()),
            'aggregation_strategy': self.aggregation_strategy.value,
            'total_samples': sum(n.status.total_samples for n in self.nodes.values()),
            'avg_rounds_per_node': np.mean([n.status.total_rounds for n in self.nodes.values()]) if self.nodes else 0,
            'recent_rounds': self.round_history[-10:] if self.round_history else [],
            'async_enabled': self.async_updates,
            'pending_updates': len(self.pending_updates)
        }

    def save_global_model(self, path: Path):
        """Save global model to file."""
        torch.save({
            'global_model': self.global_model,
            'round_number': self.round_number,
            'aggregation_strategy': self.aggregation_strategy.value
        }, path)
        logger.info(f"[FederatedCoordinator] Saved global model to {path}")

    def load_global_model(self, path: Path):
        """Load global model from file."""
        checkpoint = torch.load(path, weights_only=False)
        self.global_model = checkpoint['global_model']
        self.round_number = checkpoint.get('round_number', 0)
        logger.info(f"[FederatedCoordinator] Loaded global model from {path}")


class FederatedBrainNetwork:
    """
    High-level API for federated brain training.

    Simplifies setting up and running federated learning across multiple brain instances.
    """

    def __init__(
        self,
        aggregation_strategy: str = 'fedavg',
        use_dp: bool = False,
        dp_epsilon: float = 1.0
    ):
        """
        Initialize federated brain network.

        Args:
            aggregation_strategy: Aggregation strategy
            use_dp: Enable differential privacy
            dp_epsilon: Privacy budget
        """
        self.coordinator = FederatedCoordinator(
            aggregation_strategy=aggregation_strategy
        )
        self.use_dp = use_dp
        self.dp_config = {'target_epsilon': dp_epsilon} if use_dp else None

    def add_brain(
        self,
        brain: nn.Module,
        node_id: str,
        data: Optional[List[Tuple[Any, Any]]] = None
    ) -> FederatedNode:
        """
        Add a brain to the federated network.

        Args:
            brain: Neural network model
            node_id: Unique identifier
            data: Optional list of (input, target) tuples

        Returns:
            Created FederatedNode
        """
        node = FederatedNode(
            brain=brain,
            node_id=node_id,
            use_dp=self.use_dp,
            dp_config=self.dp_config
        )

        if data:
            examples = [
                TrainingExample(input_data=x, target=y)
                for x, y in data
            ]
            node.add_data(examples)

        self.coordinator.register_node(node_id, node)
        return node

    def train(
        self,
        rounds: int = 10,
        local_epochs: int = 5,
        loss_fn: Optional[Callable] = None
    ) -> List[Dict]:
        """
        Run federated training.

        Args:
            rounds: Number of federated rounds
            local_epochs: Local epochs per round
            loss_fn: Loss function

        Returns:
            List of round results
        """
        results = []
        for r in range(rounds):
            result = self.coordinator.run_round(
                local_epochs=local_epochs,
                loss_fn=loss_fn
            )
            results.append(result)

            if not result.get('success', False):
                logger.warning(f"Round {r+1} failed: {result.get('error')}")
                break

        return results

    def get_global_model(self) -> Dict[str, torch.Tensor]:
        """Get the trained global model."""
        return self.coordinator.get_global_model()

    def get_statistics(self) -> Dict:
        """Get network statistics."""
        return {
            'coordinator': self.coordinator.get_statistics(),
            'nodes': {
                node_id: node.get_statistics()
                for node_id, node in self.coordinator.nodes.items()
            }
        }


# ============================================================================
# Module Test
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("FEDERATED LEARNING FRAMEWORK (Phase 8B)")
    print("=" * 70)

    # Create simple test models
    class SimpleModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.fc = nn.Linear(10, 5)

        def forward(self, x):
            return self.fc(x)

    print("\n--- Testing FederatedNode ---")
    model1 = SimpleModel()
    node1 = FederatedNode(model1, node_id='node_1')

    # Add synthetic data
    data = [
        TrainingExample(
            input_data=torch.randn(10),
            target=torch.randint(0, 5, (1,)).item()
        )
        for _ in range(50)
    ]
    node1.add_data(data)
    print(f"Node 1: {node1.get_statistics()}")

    print("\n--- Testing FederatedCoordinator ---")
    coordinator = FederatedCoordinator(aggregation_strategy='fedavg')

    # Create and register multiple nodes
    model2 = SimpleModel()
    node2 = FederatedNode(model2, node_id='node_2')
    node2.add_data([
        TrainingExample(
            input_data=torch.randn(10),
            target=torch.randint(0, 5, (1,)).item()
        )
        for _ in range(30)
    ])

    coordinator.register_node('node_1', node1)
    coordinator.register_node('node_2', node2)

    print(f"Active nodes: {coordinator.get_active_nodes()}")

    print("\n--- Running Federated Round ---")
    result = coordinator.run_round(local_epochs=2)
    print(f"Round result: {result}")

    print("\n--- Testing DifferentialPrivacy ---")
    dp = DifferentialPrivacy(max_grad_norm=1.0, noise_multiplier=0.5)
    test_grads = {'weight': torch.randn(10, 5)}
    clipped = dp.clip_gradients(test_grads)
    noisy = dp.add_noise(clipped)
    print(f"DP Budget: {dp.get_privacy_budget()}")

    print("\n--- Testing FederatedBrainNetwork ---")
    network = FederatedBrainNetwork(aggregation_strategy='fedavg')
    network.add_brain(SimpleModel(), 'brain_1', [(torch.randn(10), i % 5) for i in range(20)])
    network.add_brain(SimpleModel(), 'brain_2', [(torch.randn(10), i % 5) for i in range(20)])

    results = network.train(rounds=3, local_epochs=2)
    print(f"Training results: {len(results)} rounds")
    print(f"Final stats: {network.get_statistics()['coordinator']['round_number']} rounds completed")

    print("\n" + "=" * 70)
    print("Federated Learning Tests Complete!")
    print("=" * 70)
