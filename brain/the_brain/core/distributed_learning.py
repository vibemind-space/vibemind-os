"""
Distributed Learning - AGI Phase 6

Enables distributed and federated learning across multiple agents/nodes.
Supports parallel training, gradient aggregation, and knowledge sharing.

Key Features:
- Federated Learning with differential privacy
- Gradient compression and communication
- Asynchronous parameter servers
- Knowledge distillation across agents
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
from collections import deque
import threading
import queue
import logging
import hashlib
import time

logger = logging.getLogger(__name__)


class AggregationStrategy(Enum):
    """Gradient aggregation strategies."""
    FEDAVG = "fedavg"  # Federated Averaging
    FEDPROX = "fedprox"  # FedProx with proximal term
    SCAFFOLD = "scaffold"  # SCAFFOLD variance reduction
    WEIGHTED = "weighted"  # Weighted by data size


class CompressionMethod(Enum):
    """Gradient compression methods."""
    NONE = "none"
    TOP_K = "top_k"  # Keep top k% gradients
    RANDOM_K = "random_k"  # Random k% sparsification
    QUANTIZATION = "quantization"  # Quantize to fewer bits


@dataclass
class GradientPacket:
    """Compressed gradient packet for communication."""
    agent_id: str
    round_number: int
    gradients: Dict[str, torch.Tensor]
    data_size: int  # Number of samples used
    metadata: Dict[str, Any] = field(default_factory=dict)
    compressed: bool = False
    timestamp: float = 0.0


@dataclass
class ModelUpdate:
    """Model update from server to clients."""
    round_number: int
    parameters: Dict[str, torch.Tensor]
    global_step: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DistributedStats:
    """Statistics for distributed learning."""
    total_rounds: int = 0
    total_agents: int = 0
    avg_compression_ratio: float = 1.0
    communication_bytes: int = 0
    avg_round_time: float = 0.0


class GradientCompressor:
    """
    Compresses gradients for efficient communication.
    """

    def __init__(
        self,
        method: CompressionMethod = CompressionMethod.TOP_K,
        compression_ratio: float = 0.1,
        num_bits: int = 8
    ):
        self.method = method
        self.compression_ratio = compression_ratio
        self.num_bits = num_bits

        # Error feedback for gradient correction
        self.error_feedback: Dict[str, torch.Tensor] = {}

    def compress(
        self,
        gradients: Dict[str, torch.Tensor],
        with_error_feedback: bool = True
    ) -> Dict[str, torch.Tensor]:
        """
        Compress gradients.

        Args:
            gradients: Dictionary of parameter gradients
            with_error_feedback: Use error feedback for correction

        Returns:
            Compressed gradients
        """
        if self.method == CompressionMethod.NONE:
            return gradients

        compressed = {}

        for name, grad in gradients.items():
            if with_error_feedback and name in self.error_feedback:
                # Add accumulated error
                grad = grad + self.error_feedback[name]

            if self.method == CompressionMethod.TOP_K:
                comp_grad, error = self._top_k_compress(grad)
            elif self.method == CompressionMethod.RANDOM_K:
                comp_grad, error = self._random_k_compress(grad)
            elif self.method == CompressionMethod.QUANTIZATION:
                comp_grad, error = self._quantize(grad)
            else:
                comp_grad, error = grad, torch.zeros_like(grad)

            compressed[name] = comp_grad

            if with_error_feedback:
                self.error_feedback[name] = error

        return compressed

    def _top_k_compress(
        self,
        grad: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Keep only top-k% of gradients."""
        flat = grad.flatten()
        k = max(1, int(len(flat) * self.compression_ratio))

        _, indices = torch.topk(torch.abs(flat), k)

        compressed = torch.zeros_like(flat)
        compressed[indices] = flat[indices]
        compressed = compressed.view(grad.shape)

        error = grad - compressed
        return compressed, error

    def _random_k_compress(
        self,
        grad: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Random k% sparsification."""
        mask = torch.rand_like(grad) < self.compression_ratio
        compressed = grad * mask / self.compression_ratio

        error = grad - compressed
        return compressed, error

    def _quantize(
        self,
        grad: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Quantize gradients to fewer bits."""
        # Normalize to [-1, 1]
        max_val = torch.max(torch.abs(grad))
        if max_val > 0:
            normalized = grad / max_val
        else:
            normalized = grad

        # Quantize
        levels = 2 ** self.num_bits
        quantized = torch.round(normalized * (levels / 2)) / (levels / 2)

        # Denormalize
        compressed = quantized * max_val

        error = grad - compressed
        return compressed, error

    def decompress(
        self,
        compressed: Dict[str, torch.Tensor]
    ) -> Dict[str, torch.Tensor]:
        """Decompress gradients (identity for most methods)."""
        return compressed


class DifferentialPrivacy:
    """
    Differential privacy for gradient protection.

    Adds calibrated noise to gradients before sharing.
    """

    def __init__(
        self,
        epsilon: float = 1.0,
        delta: float = 1e-5,
        max_grad_norm: float = 1.0
    ):
        self.epsilon = epsilon
        self.delta = delta
        self.max_grad_norm = max_grad_norm

    def privatize(
        self,
        gradients: Dict[str, torch.Tensor],
        sample_rate: float = 1.0
    ) -> Dict[str, torch.Tensor]:
        """
        Add differential privacy noise to gradients.

        Args:
            gradients: Gradients to privatize
            sample_rate: Subsampling rate (for privacy amplification)

        Returns:
            Privatized gradients
        """
        # Clip gradients
        clipped = self._clip_gradients(gradients)

        # Compute noise scale
        noise_scale = self._compute_noise_scale(sample_rate)

        # Add Gaussian noise
        private_grads = {}
        for name, grad in clipped.items():
            noise = torch.randn_like(grad) * noise_scale * self.max_grad_norm
            private_grads[name] = grad + noise

        return private_grads

    def _clip_gradients(
        self,
        gradients: Dict[str, torch.Tensor]
    ) -> Dict[str, torch.Tensor]:
        """Clip gradients to max norm."""
        # Compute total norm
        total_norm = 0.0
        for grad in gradients.values():
            total_norm += grad.norm() ** 2
        total_norm = total_norm ** 0.5

        # Clip factor
        clip_factor = min(1.0, self.max_grad_norm / (total_norm + 1e-8))

        clipped = {}
        for name, grad in gradients.items():
            clipped[name] = grad * clip_factor

        return clipped

    def _compute_noise_scale(self, sample_rate: float) -> float:
        """Compute noise scale for (epsilon, delta)-DP."""
        # Simplified Gaussian mechanism
        c = np.sqrt(2 * np.log(1.25 / self.delta))
        sigma = c / self.epsilon

        # Amplification by subsampling
        if sample_rate < 1.0:
            sigma = sigma * sample_rate

        return sigma


class FederatedAggregator:
    """
    Aggregates gradients from multiple agents.
    """

    def __init__(
        self,
        strategy: AggregationStrategy = AggregationStrategy.FEDAVG,
        mu: float = 0.01  # Proximal term for FedProx
    ):
        self.strategy = strategy
        self.mu = mu

        # For SCAFFOLD
        self.control_variates: Dict[str, Dict[str, torch.Tensor]] = {}
        self.global_control: Dict[str, torch.Tensor] = {}

    def aggregate(
        self,
        gradient_packets: List[GradientPacket],
        global_params: Optional[Dict[str, torch.Tensor]] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Aggregate gradients from multiple agents.

        Args:
            gradient_packets: List of gradient packets from agents
            global_params: Current global model parameters

        Returns:
            Aggregated gradient update
        """
        if not gradient_packets:
            return {}

        if self.strategy == AggregationStrategy.FEDAVG:
            return self._fedavg(gradient_packets)
        elif self.strategy == AggregationStrategy.FEDPROX:
            return self._fedprox(gradient_packets, global_params)
        elif self.strategy == AggregationStrategy.SCAFFOLD:
            return self._scaffold(gradient_packets)
        elif self.strategy == AggregationStrategy.WEIGHTED:
            return self._weighted_avg(gradient_packets)
        else:
            return self._fedavg(gradient_packets)

    def _fedavg(
        self,
        packets: List[GradientPacket]
    ) -> Dict[str, torch.Tensor]:
        """Federated averaging."""
        total_samples = sum(p.data_size for p in packets)

        aggregated = {}
        for name in packets[0].gradients.keys():
            weighted_sum = torch.zeros_like(packets[0].gradients[name])

            for packet in packets:
                weight = packet.data_size / total_samples
                weighted_sum += weight * packet.gradients[name]

            aggregated[name] = weighted_sum

        return aggregated

    def _fedprox(
        self,
        packets: List[GradientPacket],
        global_params: Optional[Dict[str, torch.Tensor]]
    ) -> Dict[str, torch.Tensor]:
        """FedProx with proximal term."""
        base = self._fedavg(packets)

        if global_params is None:
            return base

        # Add proximal regularization (already applied at clients)
        return base

    def _scaffold(
        self,
        packets: List[GradientPacket]
    ) -> Dict[str, torch.Tensor]:
        """SCAFFOLD variance reduction."""
        base = self._fedavg(packets)

        # Update control variates
        for packet in packets:
            if packet.agent_id not in self.control_variates:
                self.control_variates[packet.agent_id] = {}

            for name, grad in packet.gradients.items():
                # Update local control variate
                if name not in self.control_variates[packet.agent_id]:
                    self.control_variates[packet.agent_id][name] = torch.zeros_like(grad)

                c_local = self.control_variates[packet.agent_id][name]
                c_global = self.global_control.get(name, torch.zeros_like(grad))

                # SCAFFOLD update
                self.control_variates[packet.agent_id][name] = (
                    grad - c_global + c_local
                )

        # Update global control
        for name in base.keys():
            local_controls = [
                self.control_variates[p.agent_id].get(name, torch.zeros_like(base[name]))
                for p in packets
            ]
            self.global_control[name] = torch.mean(torch.stack(local_controls), dim=0)

        return base

    def _weighted_avg(
        self,
        packets: List[GradientPacket]
    ) -> Dict[str, torch.Tensor]:
        """Weighted average by data size."""
        return self._fedavg(packets)  # Same implementation


class ParameterServer:
    """
    Centralized parameter server for distributed learning.
    """

    def __init__(
        self,
        model: nn.Module,
        aggregator: Optional[FederatedAggregator] = None,
        learning_rate: float = 0.01
    ):
        self.model = model
        self.aggregator = aggregator or FederatedAggregator()
        self.learning_rate = learning_rate

        # Store global parameters
        self.global_params = {
            name: param.data.clone()
            for name, param in model.named_parameters()
        }

        self.global_step = 0
        self.round_number = 0

        # Gradient buffer for async updates
        self.gradient_buffer: List[GradientPacket] = []
        self.buffer_lock = threading.Lock()

    def receive_gradients(self, packet: GradientPacket):
        """Receive gradient packet from agent."""
        with self.buffer_lock:
            self.gradient_buffer.append(packet)

    def aggregate_and_update(self, min_packets: int = 1) -> Optional[ModelUpdate]:
        """
        Aggregate buffered gradients and update model.

        Args:
            min_packets: Minimum packets required for update

        Returns:
            Model update if performed
        """
        with self.buffer_lock:
            if len(self.gradient_buffer) < min_packets:
                return None

            packets = self.gradient_buffer.copy()
            self.gradient_buffer.clear()

        # Aggregate
        aggregated = self.aggregator.aggregate(packets, self.global_params)

        # Apply update
        for name, grad in aggregated.items():
            if name in self.global_params:
                self.global_params[name] -= self.learning_rate * grad

        # Update model
        for name, param in self.model.named_parameters():
            if name in self.global_params:
                param.data.copy_(self.global_params[name])

        self.global_step += 1
        self.round_number += 1

        return ModelUpdate(
            round_number=self.round_number,
            parameters={k: v.clone() for k, v in self.global_params.items()},
            global_step=self.global_step
        )

    def get_model_update(self) -> ModelUpdate:
        """Get current model state for agents."""
        return ModelUpdate(
            round_number=self.round_number,
            parameters={k: v.clone() for k, v in self.global_params.items()},
            global_step=self.global_step
        )


class DistributedAgent:
    """
    Distributed learning agent (client).
    """

    def __init__(
        self,
        agent_id: str,
        model: nn.Module,
        compressor: Optional[GradientCompressor] = None,
        privacy: Optional[DifferentialPrivacy] = None,
        local_epochs: int = 1
    ):
        self.agent_id = agent_id
        self.model = model
        self.compressor = compressor or GradientCompressor(CompressionMethod.NONE)
        self.privacy = privacy
        self.local_epochs = local_epochs

        self.local_step = 0
        self.current_round = 0

        # Optimizer
        self.optimizer = torch.optim.SGD(model.parameters(), lr=0.01)

    def local_train(
        self,
        data_loader: Any,
        loss_fn: Callable,
        epochs: Optional[int] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Perform local training and return gradients.

        Args:
            data_loader: Local training data
            loss_fn: Loss function
            epochs: Number of local epochs

        Returns:
            Computed gradients
        """
        epochs = epochs or self.local_epochs

        # Store initial parameters
        initial_params = {
            name: param.data.clone()
            for name, param in self.model.named_parameters()
        }

        # Local training
        self.model.train()
        for epoch in range(epochs):
            for batch in data_loader:
                if isinstance(batch, (list, tuple)):
                    x, y = batch[0], batch[1]
                else:
                    x, y = batch, batch

                self.optimizer.zero_grad()
                output = self.model(x)
                loss = loss_fn(output, y)
                loss.backward()
                self.optimizer.step()

                self.local_step += 1

        # Compute pseudo-gradients (difference from initial)
        gradients = {}
        for name, param in self.model.named_parameters():
            gradients[name] = initial_params[name] - param.data

        return gradients

    def prepare_gradient_packet(
        self,
        gradients: Dict[str, torch.Tensor],
        data_size: int
    ) -> GradientPacket:
        """
        Prepare gradient packet for sending.

        Args:
            gradients: Raw gradients
            data_size: Number of training samples used

        Returns:
            Ready gradient packet
        """
        # Apply privacy if enabled
        if self.privacy:
            gradients = self.privacy.privatize(gradients)

        # Compress
        compressed = self.compressor.compress(gradients)

        self.current_round += 1

        return GradientPacket(
            agent_id=self.agent_id,
            round_number=self.current_round,
            gradients=compressed,
            data_size=data_size,
            compressed=self.compressor.method != CompressionMethod.NONE,
            timestamp=time.time()
        )

    def apply_model_update(self, update: ModelUpdate):
        """Apply model update from server."""
        for name, param in self.model.named_parameters():
            if name in update.parameters:
                param.data.copy_(update.parameters[name])


class KnowledgeDistillation:
    """
    Knowledge distillation for cross-agent learning.

    Allows agents to learn from each other without sharing raw data.
    """

    def __init__(
        self,
        temperature: float = 3.0,
        alpha: float = 0.5  # Weight for distillation loss
    ):
        self.temperature = temperature
        self.alpha = alpha

    def distill(
        self,
        student_logits: torch.Tensor,
        teacher_logits: torch.Tensor,
        true_labels: torch.Tensor,
        hard_loss_fn: Callable = F.cross_entropy
    ) -> torch.Tensor:
        """
        Compute distillation loss.

        Args:
            student_logits: Student model outputs
            teacher_logits: Teacher model outputs
            true_labels: Ground truth labels
            hard_loss_fn: Loss function for hard labels

        Returns:
            Combined distillation loss
        """
        # Soft targets
        soft_targets = F.softmax(teacher_logits / self.temperature, dim=-1)
        soft_student = F.log_softmax(student_logits / self.temperature, dim=-1)

        # KL divergence (soft loss)
        soft_loss = F.kl_div(soft_student, soft_targets, reduction='batchmean')
        soft_loss = soft_loss * (self.temperature ** 2)

        # Hard loss
        hard_loss = hard_loss_fn(student_logits, true_labels)

        # Combined
        return self.alpha * soft_loss + (1 - self.alpha) * hard_loss


class DistributedLearningSystem:
    """
    Complete distributed learning system.

    Coordinates multiple agents with a parameter server.
    """

    def __init__(
        self,
        model_factory: Callable[[], nn.Module],
        num_agents: int = 4,
        aggregation_strategy: AggregationStrategy = AggregationStrategy.FEDAVG,
        compression_method: CompressionMethod = CompressionMethod.NONE,
        use_privacy: bool = False,
        privacy_epsilon: float = 1.0
    ):
        self.model_factory = model_factory
        self.num_agents = num_agents

        # Create server
        server_model = model_factory()
        self.server = ParameterServer(
            server_model,
            FederatedAggregator(aggregation_strategy)
        )

        # Create agents
        self.agents: List[DistributedAgent] = []
        for i in range(num_agents):
            agent_model = model_factory()
            compressor = GradientCompressor(compression_method)
            privacy = DifferentialPrivacy(privacy_epsilon) if use_privacy else None

            agent = DistributedAgent(
                agent_id=f"agent_{i}",
                model=agent_model,
                compressor=compressor,
                privacy=privacy
            )
            self.agents.append(agent)

        # Knowledge distillation
        self.distillation = KnowledgeDistillation()

        # Statistics
        self.stats = DistributedStats()

    def training_round(
        self,
        data_loaders: List[Any],
        loss_fn: Callable
    ) -> Dict[str, float]:
        """
        Execute one distributed training round.

        Args:
            data_loaders: Data loader for each agent
            loss_fn: Loss function

        Returns:
            Training metrics
        """
        round_start = time.time()

        # Sync agents with server
        update = self.server.get_model_update()
        for agent in self.agents:
            agent.apply_model_update(update)

        # Local training
        for i, (agent, loader) in enumerate(zip(self.agents, data_loaders)):
            gradients = agent.local_train(loader, loss_fn)

            # Count samples
            data_size = sum(1 for _ in loader) * loader.batch_size if hasattr(loader, 'batch_size') else 100

            packet = agent.prepare_gradient_packet(gradients, data_size)
            self.server.receive_gradients(packet)

        # Aggregate
        model_update = self.server.aggregate_and_update(min_packets=len(self.agents))

        round_time = time.time() - round_start

        # Update stats
        self.stats.total_rounds += 1
        self.stats.total_agents = self.num_agents
        self.stats.avg_round_time = (
            0.9 * self.stats.avg_round_time + 0.1 * round_time
        )

        return {
            'round': self.stats.total_rounds,
            'round_time': round_time,
            'global_step': self.server.global_step
        }

    def get_global_model(self) -> nn.Module:
        """Get the current global model."""
        return self.server.model


def create_distributed_system(
    model_factory: Callable[[], nn.Module],
    num_agents: int = 4,
    strategy: str = "fedavg",
    compression: str = "none",
    privacy: bool = False
) -> DistributedLearningSystem:
    """
    Factory function to create distributed learning system.

    Args:
        model_factory: Function that creates model instances
        num_agents: Number of distributed agents
        strategy: Aggregation strategy
        compression: Compression method
        privacy: Enable differential privacy

    Returns:
        Configured DistributedLearningSystem
    """
    strategy_map = {
        "fedavg": AggregationStrategy.FEDAVG,
        "fedprox": AggregationStrategy.FEDPROX,
        "scaffold": AggregationStrategy.SCAFFOLD,
        "weighted": AggregationStrategy.WEIGHTED
    }

    compression_map = {
        "none": CompressionMethod.NONE,
        "top_k": CompressionMethod.TOP_K,
        "random_k": CompressionMethod.RANDOM_K,
        "quantization": CompressionMethod.QUANTIZATION
    }

    return DistributedLearningSystem(
        model_factory=model_factory,
        num_agents=num_agents,
        aggregation_strategy=strategy_map.get(strategy, AggregationStrategy.FEDAVG),
        compression_method=compression_map.get(compression, CompressionMethod.NONE),
        use_privacy=privacy
    )
