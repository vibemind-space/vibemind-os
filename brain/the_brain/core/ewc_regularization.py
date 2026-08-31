"""
Elastic Weight Consolidation (EWC) - AGI Phase 1

Prevents catastrophic forgetting by protecting important weights
from previous tasks while learning new ones.

Key Features:
- Fisher Information Matrix computation
- Online EWC for streaming tasks
- Progressive Neural Networks support
- Memory-aware consolidation
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from copy import deepcopy
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class TaskSnapshot:
    """Snapshot of model state after learning a task."""
    task_id: str
    params: Dict[str, torch.Tensor]
    fisher: Dict[str, torch.Tensor]
    importance: float = 1.0
    timestamp: float = field(default_factory=lambda: __import__('time').time())


class EWCRegularizer:
    """
    Elastic Weight Consolidation for continual learning.

    Computes Fisher Information to identify important parameters
    and adds regularization to prevent overwriting them.
    """

    def __init__(
        self,
        model: nn.Module,
        ewc_lambda: float = 1000.0,
        fisher_sample_size: int = 200,
        online: bool = True,
        gamma: float = 0.9,
        device: str = "cpu"
    ):
        """
        Initialize EWC regularizer.

        Args:
            model: Neural network to protect
            ewc_lambda: Regularization strength
            fisher_sample_size: Samples for Fisher estimation
            online: Use online EWC (single accumulated Fisher)
            gamma: Decay factor for online EWC
            device: Computation device
        """
        self.model = model
        self.ewc_lambda = ewc_lambda
        self.fisher_sample_size = fisher_sample_size
        self.online = online
        self.gamma = gamma
        self.device = torch.device(device)

        # Task snapshots
        self.task_snapshots: List[TaskSnapshot] = []

        # Online EWC state
        self.online_fisher: Optional[Dict[str, torch.Tensor]] = None
        self.online_params: Optional[Dict[str, torch.Tensor]] = None

    def compute_fisher_information(
        self,
        dataloader: DataLoader,
        criterion: Optional[nn.Module] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Compute Fisher Information Matrix diagonal.

        The Fisher Information measures how sensitive the loss is
        to changes in each parameter - higher = more important.

        Args:
            dataloader: Data samples for Fisher estimation
            criterion: Loss function (default: CrossEntropyLoss)

        Returns:
            Dictionary of Fisher values for each parameter
        """
        if criterion is None:
            criterion = nn.CrossEntropyLoss()

        fisher = {n: torch.zeros_like(p).to(self.device)
                  for n, p in self.model.named_parameters() if p.requires_grad}

        self.model.eval()
        sample_count = 0

        for batch in dataloader:
            if sample_count >= self.fisher_sample_size:
                break

            # Handle different batch formats
            if isinstance(batch, (tuple, list)):
                inputs, targets = batch[0], batch[1]
            else:
                inputs, targets = batch, None

            inputs = inputs.to(self.device)
            if targets is not None:
                targets = targets.to(self.device)

            self.model.zero_grad()
            outputs = self.model(inputs)

            # If no targets, use model's own predictions (self-supervised)
            if targets is None:
                targets = outputs.argmax(dim=-1)

            loss = criterion(outputs, targets)
            loss.backward()

            # Accumulate squared gradients (Fisher diagonal approximation)
            for n, p in self.model.named_parameters():
                if p.requires_grad and p.grad is not None:
                    fisher[n] += p.grad.data.pow(2)

            sample_count += inputs.size(0)

        # Normalize
        for n in fisher:
            fisher[n] /= max(sample_count, 1)

        return fisher

    def consolidate_task(
        self,
        task_id: str,
        dataloader: DataLoader,
        importance: float = 1.0
    ):
        """
        Consolidate learning from a completed task.

        Computes Fisher Information and stores parameter snapshot.

        Args:
            task_id: Unique identifier for the task
            dataloader: Task data for Fisher computation
            importance: Relative importance of this task
        """
        logger.info(f"Consolidating task: {task_id}")

        # Compute Fisher Information
        fisher = self.compute_fisher_information(dataloader)

        # Store current parameters
        params = {n: p.data.clone() for n, p in self.model.named_parameters() if p.requires_grad}

        if self.online:
            # Online EWC: Merge with accumulated Fisher
            if self.online_fisher is None:
                self.online_fisher = fisher
                self.online_params = params
            else:
                for n in fisher:
                    self.online_fisher[n] = self.gamma * self.online_fisher[n] + fisher[n]
                self.online_params = params
        else:
            # Standard EWC: Store separate snapshot per task
            snapshot = TaskSnapshot(
                task_id=task_id,
                params=params,
                fisher=fisher,
                importance=importance
            )
            self.task_snapshots.append(snapshot)

        logger.info(f"Task {task_id} consolidated with {len(fisher)} parameter groups")

    def ewc_loss(self) -> torch.Tensor:
        """
        Compute EWC regularization loss.

        Penalizes changes to important parameters from previous tasks.

        Returns:
            EWC loss term to add to task loss
        """
        loss = torch.tensor(0.0).to(self.device)

        if self.online and self.online_fisher is not None:
            # Online EWC loss
            for n, p in self.model.named_parameters():
                if n in self.online_fisher and p.requires_grad:
                    loss += (self.online_fisher[n] *
                            (p - self.online_params[n]).pow(2)).sum()
        else:
            # Standard EWC loss (sum over all tasks)
            for snapshot in self.task_snapshots:
                for n, p in self.model.named_parameters():
                    if n in snapshot.fisher and p.requires_grad:
                        loss += snapshot.importance * (
                            snapshot.fisher[n] *
                            (p - snapshot.params[n]).pow(2)
                        ).sum()

        return self.ewc_lambda * loss

    def total_loss(
        self,
        task_loss: torch.Tensor,
        apply_ewc: bool = True
    ) -> torch.Tensor:
        """
        Compute total loss with EWC regularization.

        Args:
            task_loss: Loss for current task
            apply_ewc: Whether to apply EWC regularization

        Returns:
            Total loss
        """
        if apply_ewc and (self.online_fisher is not None or self.task_snapshots):
            return task_loss + self.ewc_loss()
        return task_loss

    def get_parameter_importance(self) -> Dict[str, float]:
        """Get importance scores for each parameter."""
        importance = {}

        if self.online and self.online_fisher is not None:
            for n, f in self.online_fisher.items():
                importance[n] = f.mean().item()
        elif self.task_snapshots:
            for n in self.task_snapshots[0].fisher:
                total = sum(s.fisher[n].mean().item() * s.importance
                           for s in self.task_snapshots)
                importance[n] = total / len(self.task_snapshots)

        return importance

    def save_state(self, path: str):
        """Save EWC state to file."""
        state = {
            "ewc_lambda": self.ewc_lambda,
            "online": self.online,
            "gamma": self.gamma,
            "online_fisher": self.online_fisher,
            "online_params": self.online_params,
            "task_snapshots": [
                {
                    "task_id": s.task_id,
                    "params": s.params,
                    "fisher": s.fisher,
                    "importance": s.importance,
                    "timestamp": s.timestamp
                }
                for s in self.task_snapshots
            ]
        }
        torch.save(state, path)
        logger.info(f"EWC state saved to {path}")

    def load_state(self, path: str):
        """Load EWC state from file."""
        state = torch.load(path, map_location=self.device, weights_only=False)
        self.ewc_lambda = state["ewc_lambda"]
        self.online = state["online"]
        self.gamma = state["gamma"]
        self.online_fisher = state["online_fisher"]
        self.online_params = state["online_params"]
        self.task_snapshots = [
            TaskSnapshot(**s) for s in state["task_snapshots"]
        ]
        logger.info(f"EWC state loaded from {path}")


class ProgressiveNeuralNetwork:
    """
    Progressive Neural Networks for zero-forgetting.

    Freezes previous task columns and adds new lateral connections.
    No forgetting at all, but memory grows with tasks.
    """

    def __init__(
        self,
        base_model_fn,
        lateral_dim: int = 64,
        device: str = "cpu"
    ):
        """
        Initialize Progressive Neural Network.

        Args:
            base_model_fn: Function that creates a new column
            lateral_dim: Dimension for lateral connections
            device: Computation device
        """
        self.base_model_fn = base_model_fn
        self.lateral_dim = lateral_dim
        self.device = torch.device(device)

        # Task columns
        self.columns: List[nn.Module] = []
        self.lateral_connections: List[nn.ModuleList] = []

    def add_column(self) -> nn.Module:
        """Add new column for new task."""
        new_column = self.base_model_fn().to(self.device)

        # Freeze previous columns
        for col in self.columns:
            for param in col.parameters():
                param.requires_grad = False

        # Add lateral connections to previous columns
        if self.columns:
            laterals = nn.ModuleList([
                nn.Linear(self.lateral_dim, self.lateral_dim).to(self.device)
                for _ in self.columns
            ])
            self.lateral_connections.append(laterals)

        self.columns.append(new_column)
        return new_column

    def forward(self, x: torch.Tensor, task_id: int) -> torch.Tensor:
        """Forward through progressive network."""
        if task_id >= len(self.columns):
            raise ValueError(f"Task {task_id} not found")

        # Get outputs from previous columns
        prev_outputs = []
        for i, col in enumerate(self.columns[:task_id]):
            with torch.no_grad():
                prev_outputs.append(col(x))

        # Current column output
        output = self.columns[task_id](x)

        # Add lateral contributions
        if task_id > 0 and self.lateral_connections:
            for i, (lateral, prev_out) in enumerate(
                zip(self.lateral_connections[task_id - 1], prev_outputs)
            ):
                output = output + lateral(prev_out)

        return output


class MemoryAwareConsolidation:
    """
    Memory-aware consolidation that balances forgetting and capacity.

    Implements intelligent forgetting when memory is constrained.
    """

    def __init__(
        self,
        max_tasks: int = 10,
        forgetting_strategy: str = "oldest",  # oldest, least_important, random
        importance_decay: float = 0.95
    ):
        self.max_tasks = max_tasks
        self.forgetting_strategy = forgetting_strategy
        self.importance_decay = importance_decay
        self.task_history: List[TaskSnapshot] = []

    def should_forget(self) -> bool:
        """Check if we need to forget old tasks."""
        return len(self.task_history) >= self.max_tasks

    def select_task_to_forget(self) -> Optional[str]:
        """Select which task to forget based on strategy."""
        if not self.task_history:
            return None

        if self.forgetting_strategy == "oldest":
            return self.task_history[0].task_id
        elif self.forgetting_strategy == "least_important":
            min_task = min(self.task_history, key=lambda t: t.importance)
            return min_task.task_id
        elif self.forgetting_strategy == "random":
            import random
            return random.choice(self.task_history).task_id
        else:
            return self.task_history[0].task_id

    def add_task(self, snapshot: TaskSnapshot):
        """Add new task, potentially forgetting old one."""
        if self.should_forget():
            forget_id = self.select_task_to_forget()
            self.task_history = [t for t in self.task_history if t.task_id != forget_id]
            logger.info(f"Forgot task {forget_id} due to memory constraints")

        # Decay importance of existing tasks
        for task in self.task_history:
            task.importance *= self.importance_decay

        self.task_history.append(snapshot)

    def get_consolidated_fisher(self) -> Dict[str, torch.Tensor]:
        """Get importance-weighted consolidated Fisher."""
        if not self.task_history:
            return {}

        consolidated = {}
        total_importance = sum(t.importance for t in self.task_history)

        for task in self.task_history:
            weight = task.importance / total_importance
            for n, f in task.fisher.items():
                if n not in consolidated:
                    consolidated[n] = weight * f
                else:
                    consolidated[n] += weight * f

        return consolidated
