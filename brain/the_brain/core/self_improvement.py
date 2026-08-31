"""
Self-Improvement Engine - AGI Phase 6

Enables continuous autonomous self-improvement through meta-learning,
architecture search, and performance monitoring.

Key Features:
- Meta-learning (learning to learn faster)
- Neural Architecture Search (NAS)
- Self-diagnosis and repair
- Performance-driven adaptation
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
import copy
import logging
import time

logger = logging.getLogger(__name__)


class ImprovementType(Enum):
    """Types of self-improvement."""
    META_LEARNING = "meta_learning"
    ARCHITECTURE_SEARCH = "architecture_search"
    HYPERPARAMETER_TUNING = "hyperparameter_tuning"
    SELF_DIAGNOSIS = "self_diagnosis"
    KNOWLEDGE_CONSOLIDATION = "knowledge_consolidation"


@dataclass
class PerformanceMetric:
    """Performance metric for tracking."""
    name: str
    value: float
    timestamp: float
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImprovementProposal:
    """Proposed improvement."""
    improvement_type: ImprovementType
    description: str
    expected_gain: float
    confidence: float
    changes: Dict[str, Any] = field(default_factory=dict)
    reversible: bool = True


@dataclass
class SelfImprovementStats:
    """Statistics for self-improvement."""
    total_improvements: int = 0
    successful_improvements: int = 0
    meta_learning_rounds: int = 0
    architecture_changes: int = 0
    avg_improvement_gain: float = 0.0


class PerformanceMonitor:
    """
    Monitors system performance over time.

    Detects degradation and improvement opportunities.
    """

    def __init__(
        self,
        window_size: int = 100,
        degradation_threshold: float = 0.1
    ):
        self.window_size = window_size
        self.degradation_threshold = degradation_threshold

        # Performance history
        self.metrics_history: Dict[str, deque] = {}
        self.baseline_metrics: Dict[str, float] = {}

    def record_metric(
        self,
        name: str,
        value: float,
        context: Optional[Dict[str, Any]] = None
    ):
        """Record a performance metric."""
        if name not in self.metrics_history:
            self.metrics_history[name] = deque(maxlen=self.window_size)

        self.metrics_history[name].append(PerformanceMetric(
            name=name,
            value=value,
            timestamp=time.time(),
            context=context or {}
        ))

        # Update baseline if not set
        if name not in self.baseline_metrics:
            self.baseline_metrics[name] = value

    def get_current_performance(self, name: str) -> float:
        """Get current performance for a metric."""
        if name not in self.metrics_history or len(self.metrics_history[name]) == 0:
            return 0.0
        return self.metrics_history[name][-1].value

    def get_trend(self, name: str, window: int = 20) -> float:
        """
        Get performance trend.

        Returns:
            Trend value (positive = improving, negative = degrading)
        """
        if name not in self.metrics_history:
            return 0.0

        history = list(self.metrics_history[name])
        if len(history) < 2:
            return 0.0

        recent = history[-min(window, len(history)):]
        values = [m.value for m in recent]

        # Simple linear trend
        n = len(values)
        x = np.arange(n)
        slope = np.polyfit(x, values, 1)[0]

        return slope

    def detect_degradation(self, name: str) -> bool:
        """Detect if performance is degrading."""
        if name not in self.baseline_metrics:
            return False

        current = self.get_current_performance(name)
        baseline = self.baseline_metrics[name]

        if baseline == 0:
            return False

        degradation = (baseline - current) / abs(baseline)
        return degradation > self.degradation_threshold

    def identify_improvement_opportunities(self) -> List[str]:
        """Identify metrics that need improvement."""
        opportunities = []

        for name in self.metrics_history:
            if self.detect_degradation(name):
                opportunities.append(name)

            trend = self.get_trend(name)
            if trend < -0.01:  # Negative trend
                if name not in opportunities:
                    opportunities.append(name)

        return opportunities

    def update_baseline(self, name: str, value: Optional[float] = None):
        """Update baseline for a metric."""
        if value is not None:
            self.baseline_metrics[name] = value
        elif name in self.metrics_history and len(self.metrics_history[name]) > 0:
            self.baseline_metrics[name] = self.get_current_performance(name)


class MetaLearner:
    """
    Meta-learning module - learns how to learn faster.

    Implements MAML-style meta-learning for quick adaptation.
    """

    def __init__(
        self,
        model: nn.Module,
        inner_lr: float = 0.01,
        outer_lr: float = 0.001,
        num_inner_steps: int = 5
    ):
        self.model = model
        self.inner_lr = inner_lr
        self.outer_lr = outer_lr
        self.num_inner_steps = num_inner_steps

        # Meta-optimizer
        self.meta_optimizer = torch.optim.Adam(model.parameters(), lr=outer_lr)

        # Learning rate adaptation
        self.adaptive_lr = nn.ParameterDict()
        for name, param in model.named_parameters():
            safe_name = name.replace('.', '_')
            self.adaptive_lr[safe_name] = nn.Parameter(
                torch.ones(param.shape) * inner_lr
            )

    def inner_loop(
        self,
        task_data: Tuple[torch.Tensor, torch.Tensor],
        loss_fn: Callable,
        num_steps: Optional[int] = None
    ) -> nn.Module:
        """
        Perform inner loop adaptation on a task.

        Args:
            task_data: (inputs, targets) for the task
            loss_fn: Loss function
            num_steps: Number of inner update steps

        Returns:
            Adapted model copy
        """
        num_steps = num_steps or self.num_inner_steps
        inputs, targets = task_data

        # Clone model for task-specific adaptation
        adapted_model = copy.deepcopy(self.model)
        adapted_params = dict(adapted_model.named_parameters())

        for step in range(num_steps):
            # Forward pass
            outputs = adapted_model(inputs)
            loss = loss_fn(outputs, targets)

            # Compute gradients
            grads = torch.autograd.grad(
                loss, adapted_params.values(),
                create_graph=True, allow_unused=True
            )

            # Update parameters with adaptive learning rates
            for (name, param), grad in zip(adapted_params.items(), grads):
                if grad is not None:
                    safe_name = name.replace('.', '_')
                    if safe_name in self.adaptive_lr:
                        lr = self.adaptive_lr[safe_name]
                        param.data = param.data - lr * grad
                    else:
                        param.data = param.data - self.inner_lr * grad

        return adapted_model

    def meta_update(
        self,
        tasks: List[Tuple[Tuple[torch.Tensor, torch.Tensor], Tuple[torch.Tensor, torch.Tensor]]],
        loss_fn: Callable
    ) -> float:
        """
        Meta-update using multiple tasks.

        Args:
            tasks: List of (support_data, query_data) for each task
            loss_fn: Loss function

        Returns:
            Meta-loss value
        """
        self.meta_optimizer.zero_grad()
        meta_loss = 0.0

        for support_data, query_data in tasks:
            # Adapt to task
            adapted_model = self.inner_loop(support_data, loss_fn)

            # Evaluate on query set
            query_inputs, query_targets = query_data
            query_outputs = adapted_model(query_inputs)
            task_loss = loss_fn(query_outputs, query_targets)

            meta_loss += task_loss

        # Average and backprop
        meta_loss = meta_loss / len(tasks)
        meta_loss.backward()
        self.meta_optimizer.step()

        return meta_loss.item()

    def adapt_to_new_task(
        self,
        task_data: Tuple[torch.Tensor, torch.Tensor],
        loss_fn: Callable
    ) -> nn.Module:
        """Quick adaptation to a new task."""
        return self.inner_loop(task_data, loss_fn)


class ArchitectureSearcher:
    """
    Neural Architecture Search (NAS) for self-improvement.

    Searches for better architectures within constraints.
    """

    def __init__(
        self,
        search_space: Dict[str, List[Any]],
        max_evaluations: int = 20
    ):
        self.search_space = search_space
        self.max_evaluations = max_evaluations

        # History of tried architectures
        self.architecture_history: List[Tuple[Dict[str, Any], float]] = []

    def sample_architecture(self) -> Dict[str, Any]:
        """Sample a random architecture from search space."""
        architecture = {}
        for key, options in self.search_space.items():
            architecture[key] = np.random.choice(options)
        return architecture

    def mutate_architecture(
        self,
        base_arch: Dict[str, Any],
        mutation_prob: float = 0.3
    ) -> Dict[str, Any]:
        """Mutate an architecture."""
        mutated = base_arch.copy()

        for key in mutated:
            if np.random.random() < mutation_prob:
                mutated[key] = np.random.choice(self.search_space[key])

        return mutated

    def search(
        self,
        build_fn: Callable[[Dict[str, Any]], nn.Module],
        evaluate_fn: Callable[[nn.Module], float],
        num_iterations: Optional[int] = None
    ) -> Tuple[Dict[str, Any], float]:
        """
        Search for best architecture.

        Args:
            build_fn: Function to build model from architecture config
            evaluate_fn: Function to evaluate model performance

        Returns:
            Best architecture and its score
        """
        num_iterations = num_iterations or self.max_evaluations
        best_arch = None
        best_score = float('-inf')

        for i in range(num_iterations):
            # Sample or mutate
            if i == 0 or len(self.architecture_history) == 0:
                arch = self.sample_architecture()
            elif np.random.random() < 0.5:
                # Mutate best
                arch = self.mutate_architecture(best_arch)
            else:
                # Random sample
                arch = self.sample_architecture()

            try:
                # Build and evaluate
                model = build_fn(arch)
                score = evaluate_fn(model)

                self.architecture_history.append((arch, score))

                if score > best_score:
                    best_score = score
                    best_arch = arch

            except Exception as e:
                logger.warning(f"Architecture evaluation failed: {e}")
                continue

        return best_arch, best_score

    def get_top_architectures(self, k: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        """Get top k architectures."""
        sorted_archs = sorted(
            self.architecture_history,
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_archs[:k]


class SelfDiagnosis:
    """
    Self-diagnosis module for detecting and fixing issues.
    """

    def __init__(self, model: nn.Module):
        self.model = model

        # Health metrics
        self.gradient_norms: deque = deque(maxlen=100)
        self.activation_stats: Dict[str, deque] = {}
        self.weight_changes: deque = deque(maxlen=100)

        # Previous state for comparison
        self.prev_weights: Dict[str, torch.Tensor] = {}

        # Register hooks
        self._register_hooks()

    def _register_hooks(self):
        """Register forward hooks for monitoring."""
        for name, module in self.model.named_modules():
            if isinstance(module, (nn.Linear, nn.Conv2d)):
                self.activation_stats[name] = deque(maxlen=100)
                module.register_forward_hook(
                    lambda m, i, o, n=name: self._activation_hook(n, o)
                )

    def _activation_hook(self, name: str, output: torch.Tensor):
        """Hook to record activation statistics."""
        with torch.no_grad():
            mean = output.mean().item()
            std = output.std().item()
            self.activation_stats[name].append((mean, std))

    def check_gradient_health(self) -> Dict[str, Any]:
        """Check gradient health."""
        issues = []

        if len(self.gradient_norms) > 0:
            recent_norms = list(self.gradient_norms)[-20:]
            avg_norm = np.mean(recent_norms)
            max_norm = np.max(recent_norms)
            min_norm = np.min(recent_norms)

            # Check for vanishing gradients
            if avg_norm < 1e-7:
                issues.append("vanishing_gradients")

            # Check for exploding gradients
            if max_norm > 1e4:
                issues.append("exploding_gradients")

            # Check for high variance
            if max_norm / (min_norm + 1e-8) > 100:
                issues.append("unstable_gradients")

        return {
            'healthy': len(issues) == 0,
            'issues': issues
        }

    def check_activation_health(self) -> Dict[str, Any]:
        """Check activation health across layers."""
        issues = []
        layer_health = {}

        for name, stats in self.activation_stats.items():
            if len(stats) == 0:
                continue

            means, stds = zip(*stats)
            avg_mean = np.mean(means)
            avg_std = np.mean(stds)

            layer_health[name] = {
                'mean': avg_mean,
                'std': avg_std,
                'healthy': True
            }

            # Check for dead neurons
            if avg_std < 1e-6:
                issues.append(f"dead_neurons:{name}")
                layer_health[name]['healthy'] = False

            # Check for saturation
            if abs(avg_mean) > 10:
                issues.append(f"saturation:{name}")
                layer_health[name]['healthy'] = False

        return {
            'healthy': len(issues) == 0,
            'issues': issues,
            'layer_health': layer_health
        }

    def record_gradients(self):
        """Record current gradient norms."""
        total_norm = 0.0
        for param in self.model.parameters():
            if param.grad is not None:
                total_norm += param.grad.norm().item() ** 2
        total_norm = total_norm ** 0.5
        self.gradient_norms.append(total_norm)

    def diagnose(self) -> Dict[str, Any]:
        """Run full diagnosis."""
        gradient_health = self.check_gradient_health()
        activation_health = self.check_activation_health()

        all_issues = gradient_health['issues'] + activation_health['issues']

        return {
            'overall_health': len(all_issues) == 0,
            'gradient_health': gradient_health,
            'activation_health': activation_health,
            'all_issues': all_issues,
            'recommendations': self._get_recommendations(all_issues)
        }

    def _get_recommendations(self, issues: List[str]) -> List[str]:
        """Get recommendations for fixing issues."""
        recommendations = []

        for issue in issues:
            if 'vanishing_gradients' in issue:
                recommendations.append("Consider using skip connections or different activation functions")
            elif 'exploding_gradients' in issue:
                recommendations.append("Apply gradient clipping or reduce learning rate")
            elif 'dead_neurons' in issue:
                recommendations.append("Check for dying ReLU, consider LeakyReLU or batch normalization")
            elif 'saturation' in issue:
                recommendations.append("Reduce weight initialization scale or use normalization")

        return recommendations


class KnowledgeConsolidator:
    """
    Consolidates learned knowledge for efficient retention.
    """

    def __init__(
        self,
        model: nn.Module,
        consolidation_rate: float = 0.1
    ):
        self.model = model
        self.consolidation_rate = consolidation_rate

        # Knowledge store
        self.knowledge_bank: Dict[str, torch.Tensor] = {}
        self.importance_scores: Dict[str, torch.Tensor] = {}

    def compute_importance(
        self,
        data_loader: Any,
        loss_fn: Callable
    ) -> Dict[str, torch.Tensor]:
        """
        Compute parameter importance using Fisher Information.
        """
        importance = {}

        # Initialize
        for name, param in self.model.named_parameters():
            importance[name] = torch.zeros_like(param)

        self.model.eval()
        num_samples = 0

        for batch in data_loader:
            if isinstance(batch, (list, tuple)):
                x, y = batch[0], batch[1]
            else:
                x = y = batch

            self.model.zero_grad()
            output = self.model(x)
            loss = loss_fn(output, y)
            loss.backward()

            for name, param in self.model.named_parameters():
                if param.grad is not None:
                    importance[name] += param.grad.data ** 2

            num_samples += 1

        # Normalize
        for name in importance:
            importance[name] /= (num_samples + 1e-8)

        self.importance_scores = importance
        return importance

    def consolidate(
        self,
        task_id: str,
        data_loader: Optional[Any] = None,
        loss_fn: Optional[Callable] = None
    ):
        """
        Consolidate knowledge from current task.
        """
        # Store current parameters
        for name, param in self.model.named_parameters():
            key = f"{task_id}_{name}"
            self.knowledge_bank[key] = param.data.clone()

        # Update importance if data provided
        if data_loader and loss_fn:
            self.compute_importance(data_loader, loss_fn)

    def regularization_loss(self, current_task_id: str) -> torch.Tensor:
        """
        Compute consolidation regularization loss.
        """
        loss = torch.tensor(0.0)

        for name, param in self.model.named_parameters():
            for task_id in self._get_previous_tasks(current_task_id):
                key = f"{task_id}_{name}"
                if key in self.knowledge_bank:
                    old_param = self.knowledge_bank[key]
                    importance = self.importance_scores.get(name, torch.ones_like(param))

                    loss += (importance * (param - old_param) ** 2).sum()

        return self.consolidation_rate * loss

    def _get_previous_tasks(self, current_task_id: str) -> List[str]:
        """Get list of previous task IDs."""
        task_ids = set()
        for key in self.knowledge_bank:
            task_id = key.rsplit('_', 1)[0]
            if task_id != current_task_id:
                task_ids.add(task_id)
        return list(task_ids)


class SelfImprovementEngine:
    """
    Main self-improvement engine.

    Orchestrates meta-learning, architecture search, and self-diagnosis.
    """

    def __init__(
        self,
        model: nn.Module,
        search_space: Optional[Dict[str, List[Any]]] = None,
        enable_meta_learning: bool = True,
        enable_nas: bool = False,
        enable_diagnosis: bool = True
    ):
        self.model = model
        self.enable_meta_learning = enable_meta_learning
        self.enable_nas = enable_nas
        self.enable_diagnosis = enable_diagnosis

        # Components
        self.performance_monitor = PerformanceMonitor()

        if enable_meta_learning:
            self.meta_learner = MetaLearner(model)
        else:
            self.meta_learner = None

        if enable_nas and search_space:
            self.architecture_searcher = ArchitectureSearcher(search_space)
        else:
            self.architecture_searcher = None

        if enable_diagnosis:
            self.self_diagnosis = SelfDiagnosis(model)
        else:
            self.self_diagnosis = None

        self.knowledge_consolidator = KnowledgeConsolidator(model)

        # Statistics
        self.stats = SelfImprovementStats()

        # Improvement history
        self.improvement_history: List[Tuple[ImprovementProposal, bool]] = []

    def record_performance(
        self,
        metric_name: str,
        value: float,
        context: Optional[Dict[str, Any]] = None
    ):
        """Record a performance metric."""
        self.performance_monitor.record_metric(metric_name, value, context)

    def diagnose_system(self) -> Dict[str, Any]:
        """Run system diagnosis."""
        if not self.self_diagnosis:
            return {'healthy': True, 'message': 'Diagnosis disabled'}

        return self.self_diagnosis.diagnose()

    def propose_improvements(self) -> List[ImprovementProposal]:
        """
        Analyze system and propose improvements.
        """
        proposals = []

        # Check for degradation
        opportunities = self.performance_monitor.identify_improvement_opportunities()

        for metric in opportunities:
            proposals.append(ImprovementProposal(
                improvement_type=ImprovementType.META_LEARNING,
                description=f"Meta-learning to improve {metric}",
                expected_gain=0.1,
                confidence=0.7,
                changes={'target_metric': metric}
            ))

        # Check health issues
        if self.self_diagnosis:
            diagnosis = self.self_diagnosis.diagnose()
            if not diagnosis['overall_health']:
                proposals.append(ImprovementProposal(
                    improvement_type=ImprovementType.SELF_DIAGNOSIS,
                    description="Fix detected health issues",
                    expected_gain=0.2,
                    confidence=0.8,
                    changes={'issues': diagnosis['all_issues']}
                ))

        # Consider architecture search
        if self.architecture_searcher and len(self.improvement_history) > 5:
            recent_success_rate = sum(
                1 for _, success in self.improvement_history[-5:]
                if success
            ) / 5

            if recent_success_rate < 0.5:
                proposals.append(ImprovementProposal(
                    improvement_type=ImprovementType.ARCHITECTURE_SEARCH,
                    description="Search for better architecture",
                    expected_gain=0.15,
                    confidence=0.5,
                    reversible=False
                ))

        return proposals

    def apply_improvement(
        self,
        proposal: ImprovementProposal,
        **kwargs
    ) -> bool:
        """
        Apply a proposed improvement.

        Returns:
            Success status
        """
        success = False

        try:
            if proposal.improvement_type == ImprovementType.META_LEARNING:
                if self.meta_learner and 'tasks' in kwargs:
                    loss = self.meta_learner.meta_update(
                        kwargs['tasks'],
                        kwargs.get('loss_fn', F.mse_loss)
                    )
                    success = loss < kwargs.get('threshold', 1.0)
                    self.stats.meta_learning_rounds += 1

            elif proposal.improvement_type == ImprovementType.ARCHITECTURE_SEARCH:
                if self.architecture_searcher:
                    best_arch, score = self.architecture_searcher.search(
                        kwargs['build_fn'],
                        kwargs['evaluate_fn']
                    )
                    success = score > kwargs.get('baseline_score', 0)
                    self.stats.architecture_changes += 1

            elif proposal.improvement_type == ImprovementType.KNOWLEDGE_CONSOLIDATION:
                self.knowledge_consolidator.consolidate(
                    kwargs.get('task_id', 'default'),
                    kwargs.get('data_loader'),
                    kwargs.get('loss_fn')
                )
                success = True

            if success:
                self.stats.successful_improvements += 1
                self.stats.avg_improvement_gain = (
                    0.9 * self.stats.avg_improvement_gain +
                    0.1 * proposal.expected_gain
                )

            self.stats.total_improvements += 1
            self.improvement_history.append((proposal, success))

        except Exception as e:
            logger.error(f"Improvement failed: {e}")
            success = False

        return success

    def continuous_improvement_step(
        self,
        data_loader: Optional[Any] = None,
        loss_fn: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Perform one step of continuous improvement.

        Returns:
            Step results
        """
        results = {
            'proposals': [],
            'applied': [],
            'diagnosis': None
        }

        # Run diagnosis
        if self.enable_diagnosis:
            results['diagnosis'] = self.diagnose_system()

        # Record gradients after training
        if self.self_diagnosis:
            self.self_diagnosis.record_gradients()

        # Propose improvements
        proposals = self.propose_improvements()
        results['proposals'] = [p.description for p in proposals]

        # Apply top proposal
        if proposals:
            top_proposal = max(proposals, key=lambda p: p.expected_gain * p.confidence)
            success = self.apply_improvement(
                top_proposal,
                data_loader=data_loader,
                loss_fn=loss_fn
            )
            results['applied'] = [(top_proposal.description, success)]

        return results

    def get_improvement_report(self) -> Dict[str, Any]:
        """Get comprehensive improvement report."""
        return {
            'stats': {
                'total_improvements': self.stats.total_improvements,
                'successful': self.stats.successful_improvements,
                'success_rate': (
                    self.stats.successful_improvements / max(1, self.stats.total_improvements)
                ),
                'meta_learning_rounds': self.stats.meta_learning_rounds,
                'architecture_changes': self.stats.architecture_changes,
                'avg_gain': self.stats.avg_improvement_gain
            },
            'recent_history': [
                (p.description, s) for p, s in self.improvement_history[-10:]
            ],
            'current_health': self.diagnose_system() if self.enable_diagnosis else None
        }


def create_self_improvement_engine(
    model: nn.Module,
    search_space: Optional[Dict[str, List[Any]]] = None,
    enable_all: bool = True
) -> SelfImprovementEngine:
    """
    Factory function to create self-improvement engine.

    Args:
        model: The model to improve
        search_space: Optional NAS search space
        enable_all: Enable all improvement features

    Returns:
        Configured SelfImprovementEngine
    """
    return SelfImprovementEngine(
        model=model,
        search_space=search_space,
        enable_meta_learning=enable_all,
        enable_nas=enable_all and search_space is not None,
        enable_diagnosis=enable_all
    )
