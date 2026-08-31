"""
Meta-Learning System (PHASE 4)

Implements second-order learning - the brain learns how to learn:

1. Performance-based learning rate adaptation:
   - Success → reduce learning rate (exploitation)
   - Failure → increase learning rate (exploration)
   - Oscillation → reduce learning rate (stability)

2. Meta-parameters controlled:
   - Memory consolidation thresholds
   - Attention focus strength
   - Prediction confidence weights
   - Curiosity/exploration rate

3. Adaptive algorithms:
   - Adam-style momentum for meta-parameters
   - Performance gradient estimation
   - Stability detection
   - Progress tracking

Based on:
- MAML (Model-Agnostic Meta-Learning)
- Meta-SGD
- Adaptive learning rate methods
- Biological meta-plasticity
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque


@dataclass
class MetaParameters:
    """
    Meta-parameters that control learning behavior
    """
    # Learning rates
    memory_learning_rate: float = 0.1  # How quickly to consolidate memories
    prediction_learning_rate: float = 0.1  # How quickly to update predictions
    attention_learning_rate: float = 0.05  # How quickly to shift attention

    # Thresholds
    memory_importance_threshold: float = 0.7  # When to consolidate to episodic
    prediction_confidence_threshold: float = 0.5  # When to trust predictions
    attention_focus_strength: float = 0.5  # How strongly to gate attention

    # Exploration/exploitation
    exploration_rate: float = 0.2  # Curiosity-driven exploration
    temperature: float = 1.0  # Decision randomness

    # Constraints (min/max bounds)
    min_learning_rate: float = 0.01
    max_learning_rate: float = 0.5
    min_threshold: float = 0.1
    max_threshold: float = 0.9

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'memory_learning_rate': self.memory_learning_rate,
            'prediction_learning_rate': self.prediction_learning_rate,
            'attention_learning_rate': self.attention_learning_rate,
            'memory_importance_threshold': self.memory_importance_threshold,
            'prediction_confidence_threshold': self.prediction_confidence_threshold,
            'attention_focus_strength': self.attention_focus_strength,
            'exploration_rate': self.exploration_rate,
            'temperature': self.temperature
        }

    def clip_values(self):
        """Ensure all values are within valid bounds"""
        # Clip learning rates
        self.memory_learning_rate = np.clip(
            self.memory_learning_rate,
            self.min_learning_rate,
            self.max_learning_rate
        )
        self.prediction_learning_rate = np.clip(
            self.prediction_learning_rate,
            self.min_learning_rate,
            self.max_learning_rate
        )
        self.attention_learning_rate = np.clip(
            self.attention_learning_rate,
            self.min_learning_rate,
            self.max_learning_rate
        )

        # Clip thresholds
        self.memory_importance_threshold = np.clip(
            self.memory_importance_threshold,
            self.min_threshold,
            self.max_threshold
        )
        self.prediction_confidence_threshold = np.clip(
            self.prediction_confidence_threshold,
            self.min_threshold,
            self.max_threshold
        )
        self.attention_focus_strength = np.clip(
            self.attention_focus_strength,
            self.min_threshold,
            self.max_threshold
        )

        # Clip exploration and temperature
        self.exploration_rate = np.clip(self.exploration_rate, 0.0, 1.0)
        self.temperature = np.clip(self.temperature, 0.1, 2.0)


@dataclass
class PerformanceMetrics:
    """
    Tracks performance for meta-learning
    """
    success_count: int = 0
    failure_count: int = 0
    total_tasks: int = 0

    # Running averages
    avg_prediction_error: float = 0.5
    avg_confidence: float = 0.5
    avg_attention_entropy: float = 1.0

    # Recent history
    recent_outcomes: deque = field(default_factory=lambda: deque(maxlen=20))
    recent_errors: deque = field(default_factory=lambda: deque(maxlen=20))

    def update(
        self,
        outcome: str,
        prediction_error: Optional[float] = None,
        confidence: Optional[float] = None,
        attention_entropy: Optional[float] = None
    ):
        """Update metrics with new observation"""
        # Update counts
        self.total_tasks += 1
        if outcome == 'success':
            self.success_count += 1
            self.recent_outcomes.append(1)
        else:
            self.failure_count += 1
            self.recent_outcomes.append(0)

        # Update running averages with exponential moving average
        alpha = 0.1
        if prediction_error is not None:
            self.avg_prediction_error = (
                (1 - alpha) * self.avg_prediction_error +
                alpha * prediction_error
            )
            self.recent_errors.append(prediction_error)

        if confidence is not None:
            self.avg_confidence = (
                (1 - alpha) * self.avg_confidence +
                alpha * confidence
            )

        if attention_entropy is not None:
            self.avg_attention_entropy = (
                (1 - alpha) * self.avg_attention_entropy +
                alpha * attention_entropy
            )

    def get_success_rate(self, window: int = 10) -> float:
        """Get recent success rate"""
        if not self.recent_outcomes:
            return 0.5

        recent = list(self.recent_outcomes)[-window:]
        return sum(recent) / len(recent)

    def get_error_trend(self) -> str:
        """Determine if errors are increasing, decreasing, or stable"""
        if len(self.recent_errors) < 5:
            return 'unknown'

        recent = list(self.recent_errors)
        first_half = np.mean(recent[:len(recent)//2])
        second_half = np.mean(recent[len(recent)//2:])

        diff = second_half - first_half
        if diff > 0.1:
            return 'increasing'
        elif diff < -0.1:
            return 'decreasing'
        else:
            return 'stable'

    def detect_oscillation(self) -> bool:
        """Detect if performance is oscillating"""
        if len(self.recent_errors) < 6:
            return False

        recent = list(self.recent_errors)[-6:]
        # Check for alternating high/low pattern
        diffs = [recent[i+1] - recent[i] for i in range(len(recent)-1)]
        sign_changes = sum(1 for i in range(len(diffs)-1) if diffs[i] * diffs[i+1] < 0)

        return sign_changes >= 3  # At least 3 sign changes = oscillation


class MetaLearner:
    """
    Meta-learning system that adapts learning rates and meta-parameters

    Key features:
    - Performance-based learning rate adaptation
    - Stability detection and oscillation damping
    - Progress monitoring
    - Multi-timescale adaptation
    """

    def __init__(
        self,
        initial_meta_params: Optional[MetaParameters] = None,
        meta_learning_rate: float = 0.01,
        adaptation_window: int = 20
    ):
        """
        Initialize meta-learner

        Args:
            initial_meta_params: Initial meta-parameters
            meta_learning_rate: How quickly to adapt meta-parameters
            adaptation_window: Window for computing performance trends
        """
        self.meta_params = initial_meta_params or MetaParameters()
        self.meta_learning_rate = meta_learning_rate
        self.adaptation_window = adaptation_window

        # Performance tracking
        self.performance = PerformanceMetrics()

        # Meta-optimizer state (Adam-style)
        self.momentum = {}  # First moment estimates
        self.velocity = {}  # Second moment estimates
        self.beta1 = 0.9  # Momentum decay
        self.beta2 = 0.999  # Velocity decay
        self.epsilon = 1e-8
        self.t = 0  # Time step

        # Initialize momentum and velocity for each meta-parameter
        for param_name in ['memory_learning_rate', 'prediction_learning_rate',
                          'attention_learning_rate', 'memory_importance_threshold',
                          'exploration_rate']:
            self.momentum[param_name] = 0.0
            self.velocity[param_name] = 0.0

        # Statistics
        self.total_adaptations = 0
        self.adaptation_history: List[Dict] = []

    def compute_performance_gradient(self) -> Dict[str, float]:
        """
        Estimate gradients for meta-parameters based on performance

        Returns:
            Dictionary of parameter gradients
        """
        gradients = {}

        # Get recent performance
        success_rate = self.performance.get_success_rate(window=self.adaptation_window)
        error_trend = self.performance.get_error_trend()
        is_oscillating = self.performance.detect_oscillation()

        # === Memory Learning Rate ===
        # High error → increase memory LR (learn more from mistakes)
        # Low error → decrease memory LR (exploitation)
        memory_grad = 0.0
        if self.performance.avg_prediction_error > 0.6:
            memory_grad = 0.1  # Increase
        elif self.performance.avg_prediction_error < 0.3:
            memory_grad = -0.05  # Decrease
        gradients['memory_learning_rate'] = memory_grad

        # === Prediction Learning Rate ===
        # Oscillating → decrease prediction LR (stability)
        # Increasing error → increase prediction LR (need more adaptation)
        # Decreasing error → maintain or slightly decrease
        pred_grad = 0.0
        if is_oscillating:
            pred_grad = -0.1  # Reduce for stability
        elif error_trend == 'increasing':
            pred_grad = 0.1  # Increase to adapt
        elif error_trend == 'decreasing':
            pred_grad = -0.02  # Slight decrease (doing well)
        gradients['prediction_learning_rate'] = pred_grad

        # === Attention Learning Rate ===
        # High attention entropy (distributed) → increase attention LR (focus more)
        # Low attention entropy (focused) → decrease attention LR (already focused)
        att_grad = 0.0
        if self.performance.avg_attention_entropy > 0.8:
            att_grad = 0.05  # Increase to focus better
        elif self.performance.avg_attention_entropy < 0.3:
            att_grad = -0.03  # Decrease (already very focused)
        gradients['attention_learning_rate'] = att_grad

        # === Memory Importance Threshold ===
        # High success rate → increase threshold (be more selective)
        # Low success rate → decrease threshold (consolidate more)
        threshold_grad = 0.0
        if success_rate > 0.7:
            threshold_grad = 0.05  # Be more selective
        elif success_rate < 0.4:
            threshold_grad = -0.05  # Consolidate more
        gradients['memory_importance_threshold'] = threshold_grad

        # === Exploration Rate ===
        # Low success rate → increase exploration
        # High success rate → decrease exploration
        explore_grad = 0.0
        if success_rate < 0.4:
            explore_grad = 0.1  # Explore more
        elif success_rate > 0.7:
            explore_grad = -0.05  # Exploit more
        gradients['exploration_rate'] = explore_grad

        return gradients

    def adapt_meta_parameters(
        self,
        outcome: str,
        prediction_error: Optional[float] = None,
        confidence: Optional[float] = None,
        attention_entropy: Optional[float] = None
    ) -> MetaParameters:
        """
        Adapt meta-parameters based on performance

        Args:
            outcome: 'success' or 'failure'
            prediction_error: Recent prediction error
            confidence: Recent confidence
            attention_entropy: Recent attention entropy

        Returns:
            Updated meta-parameters
        """
        # Update performance metrics
        self.performance.update(
            outcome=outcome,
            prediction_error=prediction_error,
            confidence=confidence,
            attention_entropy=attention_entropy
        )

        # Only adapt if we have enough data
        if self.performance.total_tasks < 5:
            return self.meta_params

        # Compute gradients
        gradients = self.compute_performance_gradient()

        # Update time step
        self.t += 1

        # Adam-style meta-parameter updates
        for param_name, gradient in gradients.items():
            # Update biased first moment estimate
            self.momentum[param_name] = (
                self.beta1 * self.momentum[param_name] +
                (1 - self.beta1) * gradient
            )

            # Update biased second moment estimate
            self.velocity[param_name] = (
                self.beta2 * self.velocity[param_name] +
                (1 - self.beta2) * (gradient ** 2)
            )

            # Bias correction
            m_hat = self.momentum[param_name] / (1 - self.beta1 ** self.t)
            v_hat = self.velocity[param_name] / (1 - self.beta2 ** self.t)

            # Update meta-parameter
            update = self.meta_learning_rate * m_hat / (np.sqrt(v_hat) + self.epsilon)

            # Apply update
            current_value = getattr(self.meta_params, param_name)
            new_value = current_value + update
            setattr(self.meta_params, param_name, new_value)

        # Clip all values to valid ranges
        self.meta_params.clip_values()

        # Record adaptation
        self.total_adaptations += 1
        self.adaptation_history.append({
            'step': self.t,
            'meta_params': self.meta_params.to_dict(),
            'gradients': gradients,
            'success_rate': self.performance.get_success_rate(),
            'avg_error': self.performance.avg_prediction_error
        })

        return self.meta_params

    def get_statistics(self) -> Dict:
        """Get meta-learning statistics"""
        return {
            'total_adaptations': self.total_adaptations,
            'current_meta_params': self.meta_params.to_dict(),
            'performance': {
                'total_tasks': self.performance.total_tasks,
                'success_count': self.performance.success_count,
                'failure_count': self.performance.failure_count,
                'success_rate': self.performance.get_success_rate(),
                'avg_prediction_error': self.performance.avg_prediction_error,
                'avg_confidence': self.performance.avg_confidence,
                'error_trend': self.performance.get_error_trend(),
                'is_oscillating': self.performance.detect_oscillation()
            }
        }

    def __repr__(self):
        return (
            f"MetaLearner("
            f"adaptations={self.total_adaptations}, "
            f"success_rate={self.performance.get_success_rate():.1%})"
        )


# =============================================================================
# MAML and Advanced Meta-Learning (Phase 8B)
# =============================================================================

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.optim import Adam
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    nn = None

import copy
import logging
from pathlib import Path
import json
from datetime import datetime
from typing import Any, Iterator, Callable

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """
    Represents a meta-learning task.

    A task consists of:
    - Support set: Examples for adaptation (few-shot learning)
    - Query set: Examples for evaluation
    """
    task_id: str
    domain: str
    support_x: Any  # torch.Tensor or np.ndarray
    support_y: Any  # torch.Tensor or np.ndarray
    query_x: Any
    query_y: Any
    metadata: Dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.support_x) + len(self.query_x)

    @property
    def n_support(self) -> int:
        return len(self.support_x)

    @property
    def n_query(self) -> int:
        return len(self.query_x)


class MAMLOptimizer:
    """
    Model-Agnostic Meta-Learning (MAML) optimizer.

    MAML learns a model initialization that can quickly adapt to new tasks
    with just a few gradient steps.

    Algorithm:
    1. For each task in batch:
       a. Clone model parameters
       b. Perform K inner-loop gradient steps on support set
       c. Compute loss on query set with adapted parameters
    2. Update original parameters using sum of query losses

    Features:
    - First-order approximation (FOMAML) for memory efficiency
    - Supports any PyTorch model
    - Configurable inner/outer learning rates

    Requires PyTorch.
    """

    def __init__(
        self,
        model: 'nn.Module',
        inner_lr: float = 0.01,
        outer_lr: float = 0.001,
        inner_steps: int = 5,
        first_order: bool = True,
        device: str = 'cpu'
    ):
        if not TORCH_AVAILABLE:
            raise ImportError("MAML requires PyTorch. Install with: pip install torch")

        self.model = model
        self.inner_lr = inner_lr
        self.outer_lr = outer_lr
        self.inner_steps = inner_steps
        self.first_order = first_order
        self.device = device

        self.meta_optimizer = Adam(model.parameters(), lr=outer_lr)

        self.meta_losses: List[float] = []
        self.adaptation_losses: List[float] = []
        self.train_step = 0

    def inner_loop(
        self,
        support_x: 'torch.Tensor',
        support_y: 'torch.Tensor',
        loss_fn: Callable,
        steps: Optional[int] = None
    ) -> Tuple['nn.Module', List[float]]:
        """
        Perform inner loop adaptation on a task.

        Args:
            support_x: Support set inputs
            support_y: Support set targets
            loss_fn: Loss function
            steps: Number of gradient steps

        Returns:
            Adapted model and list of losses per step
        """
        import torch

        steps = steps or self.inner_steps
        adapted_model = self._clone_model()
        adapted_params = list(adapted_model.parameters())

        losses = []

        for step in range(steps):
            predictions = adapted_model(support_x)
            loss = loss_fn(predictions, support_y)
            losses.append(loss.item())

            grads = torch.autograd.grad(
                loss,
                adapted_params,
                create_graph=not self.first_order
            )

            for param, grad in zip(adapted_params, grads):
                param.data = param.data - self.inner_lr * grad

        return adapted_model, losses

    def outer_loop(
        self,
        tasks: List[Task],
        loss_fn: Callable
    ) -> float:
        """
        Perform outer loop meta-update.

        Args:
            tasks: List of tasks for meta-training
            loss_fn: Loss function

        Returns:
            Average meta-loss across tasks
        """
        import torch

        self.meta_optimizer.zero_grad()
        meta_loss = torch.tensor(0.0, device=self.device)

        for task in tasks:
            support_x = task.support_x.to(self.device) if hasattr(task.support_x, 'to') else torch.tensor(task.support_x, device=self.device)
            support_y = task.support_y.to(self.device) if hasattr(task.support_y, 'to') else torch.tensor(task.support_y, device=self.device)
            query_x = task.query_x.to(self.device) if hasattr(task.query_x, 'to') else torch.tensor(task.query_x, device=self.device)
            query_y = task.query_y.to(self.device) if hasattr(task.query_y, 'to') else torch.tensor(task.query_y, device=self.device)

            adapted_model, inner_losses = self.inner_loop(support_x, support_y, loss_fn)

            query_pred = adapted_model(query_x)
            query_loss = loss_fn(query_pred, query_y)
            meta_loss = meta_loss + query_loss

            self.adaptation_losses.extend(inner_losses)

        meta_loss = meta_loss / len(tasks)
        meta_loss.backward()
        self.meta_optimizer.step()

        self.meta_losses.append(meta_loss.item())
        self.train_step += 1

        return meta_loss.item()

    def adapt(
        self,
        task: Task,
        loss_fn: Callable,
        shots: int = 5
    ) -> 'nn.Module':
        """Quickly adapt model to a new task."""
        import torch

        n_use = min(shots, task.n_support)
        support_x = task.support_x[:n_use]
        support_y = task.support_y[:n_use]

        if not isinstance(support_x, torch.Tensor):
            support_x = torch.tensor(support_x, dtype=torch.float32)
            support_y = torch.tensor(support_y, dtype=torch.long)

        support_x = support_x.to(self.device)
        support_y = support_y.to(self.device)

        adapted_model, _ = self.inner_loop(support_x, support_y, loss_fn)
        return adapted_model

    def _clone_model(self) -> 'nn.Module':
        """Create a clone of the model."""
        clone = copy.deepcopy(self.model)
        clone.to(self.device)
        return clone

    def get_statistics(self) -> Dict:
        """Get training statistics."""
        return {
            'train_step': self.train_step,
            'avg_meta_loss': np.mean(self.meta_losses[-100:]) if self.meta_losses else 0,
            'avg_adaptation_loss': np.mean(self.adaptation_losses[-100:]) if self.adaptation_losses else 0,
            'inner_lr': self.inner_lr,
            'outer_lr': self.outer_lr,
            'inner_steps': self.inner_steps
        }

    def save_state(self, path: Path) -> None:
        """Save optimizer state."""
        import torch
        state = {
            'model_state_dict': self.model.state_dict(),
            'meta_optimizer_state_dict': self.meta_optimizer.state_dict(),
            'config': {
                'inner_lr': self.inner_lr,
                'outer_lr': self.outer_lr,
                'inner_steps': self.inner_steps
            },
            'train_step': self.train_step,
            'meta_losses': self.meta_losses[-1000:],
            'adaptation_losses': self.adaptation_losses[-1000:]
        }
        torch.save(state, path)
        logger.info(f"Saved MAML state to {path}")

    def load_state(self, path: Path) -> None:
        """Load optimizer state."""
        import torch
        state = torch.load(path, map_location=self.device, weights_only=False)
        self.model.load_state_dict(state['model_state_dict'])
        self.meta_optimizer.load_state_dict(state['meta_optimizer_state_dict'])
        config = state.get('config', {})
        self.inner_lr = config.get('inner_lr', self.inner_lr)
        self.outer_lr = config.get('outer_lr', self.outer_lr)
        self.inner_steps = config.get('inner_steps', self.inner_steps)
        self.train_step = state.get('train_step', 0)
        self.meta_losses = state.get('meta_losses', [])
        self.adaptation_losses = state.get('adaptation_losses', [])
        logger.info(f"Loaded MAML state from {path}")


class TaskDistribution:
    """
    Generates and manages meta-learning tasks from experience.

    Supports:
    - Sampling tasks from experience buffer
    - Creating domain-specific task distributions
    - Task difficulty curriculum
    """

    def __init__(
        self,
        experience_buffer: Optional[List[Dict]] = None,
        n_support: int = 5,
        n_query: int = 10
    ):
        self.buffer: List[Dict] = experience_buffer or []
        self.n_support = n_support
        self.n_query = n_query
        self.domain_buffers: Dict[str, List[Dict]] = {}
        self.task_counter = 0

    def add_experience(self, experience: Dict, domain: str = 'default') -> None:
        """Add an experience to the buffer."""
        self.buffer.append(experience)
        if domain not in self.domain_buffers:
            self.domain_buffers[domain] = []
        self.domain_buffers[domain].append(experience)

    def sample_task(
        self,
        domain: Optional[str] = None,
        n_support: Optional[int] = None,
        n_query: Optional[int] = None
    ) -> Task:
        """Sample a random task from the buffer."""
        n_support = n_support or self.n_support
        n_query = n_query or self.n_query
        n_total = n_support + n_query

        buffer = self.domain_buffers.get(domain, self.buffer) if domain else self.buffer

        if len(buffer) < n_total:
            raise ValueError(f"Not enough experiences ({len(buffer)}) for task ({n_total})")

        indices = np.random.choice(len(buffer), n_total, replace=False)
        samples = [buffer[i] for i in indices]

        support_samples = samples[:n_support]
        query_samples = samples[n_support:]

        # Convert to arrays
        support_x = np.array([s['state'] for s in support_samples], dtype=np.float32)
        support_y = np.array([s['action'] for s in support_samples], dtype=np.int64)
        query_x = np.array([s['state'] for s in query_samples], dtype=np.float32)
        query_y = np.array([s['action'] for s in query_samples], dtype=np.int64)

        self.task_counter += 1

        return Task(
            task_id=f"task_{self.task_counter}",
            domain=domain or 'default',
            support_x=support_x,
            support_y=support_y,
            query_x=query_x,
            query_y=query_y,
            metadata={'sample_indices': indices.tolist()}
        )

    def create_domain_tasks(self, domain: str, n_tasks: int = 10) -> List[Task]:
        """Create multiple tasks from a specific domain."""
        tasks = []
        for _ in range(n_tasks):
            try:
                task = self.sample_task(domain=domain)
                tasks.append(task)
            except ValueError:
                break
        return tasks

    def get_statistics(self) -> Dict:
        """Get task distribution statistics."""
        return {
            'total_experiences': len(self.buffer),
            'domains': list(self.domain_buffers.keys()),
            'experiences_per_domain': {
                domain: len(exps)
                for domain, exps in self.domain_buffers.items()
            },
            'tasks_generated': self.task_counter
        }


class AdaptiveHyperparameters:
    """
    Online hyperparameter tuning based on performance.

    Features:
    - Population-based training style updates
    - Exploration/exploitation balance
    - Performance-based adaptation
    """

    def __init__(
        self,
        param_bounds: Optional[Dict[str, Tuple[float, float]]] = None,
        history_size: int = 100
    ):
        self.param_bounds = param_bounds or {
            'learning_rate': (1e-5, 1e-1),
            'batch_size': (8, 128),
            'inner_steps': (1, 10),
            'weight_decay': (0, 0.1)
        }

        self.history_size = history_size
        self.current_params: Dict[str, float] = {}
        self._initialize_params()

        self.performance_history: deque = deque(maxlen=history_size)
        self.param_history: Dict[str, deque] = {
            param: deque(maxlen=history_size) for param in self.param_bounds
        }

        self.best_params: Dict[str, float] = self.current_params.copy()
        self.best_performance: float = float('-inf')
        self.exploration_rate = 0.2
        self.update_count = 0

    def _initialize_params(self) -> None:
        """Initialize parameters to middle of bounds."""
        for param, (low, high) in self.param_bounds.items():
            if param in ['batch_size', 'inner_steps']:
                self.current_params[param] = int((low + high) / 2)
            elif 'rate' in param or 'lr' in param:
                self.current_params[param] = np.exp((np.log(low) + np.log(high)) / 2)
            else:
                self.current_params[param] = (low + high) / 2

    def suggest_lr(self, current_loss: float) -> float:
        """Suggest learning rate based on current loss."""
        if len(self.performance_history) > 0:
            prev_loss = self.performance_history[-1]
            if current_loss > prev_loss * 1.1:
                self.current_params['learning_rate'] *= 0.9
            elif current_loss < prev_loss * 0.9:
                self.current_params['learning_rate'] *= 1.05

        low, high = self.param_bounds.get('learning_rate', (1e-5, 1e-1))
        self.current_params['learning_rate'] = np.clip(
            self.current_params['learning_rate'], low, high
        )
        return self.current_params['learning_rate']

    def suggest_batch_size(self, memory_available: int) -> int:
        """Suggest batch size based on available memory."""
        low, high = self.param_bounds.get('batch_size', (8, 128))
        max_batch = min(high, memory_available // 50)
        suggested = max(low, min(max_batch, self.current_params.get('batch_size', 32)))
        self.current_params['batch_size'] = int(suggested)
        return int(suggested)

    def update(self, params: Dict[str, float], performance: float) -> None:
        """Update with new parameter-performance observation."""
        self.performance_history.append(performance)
        for param, value in params.items():
            if param in self.param_history:
                self.param_history[param].append(value)

        if performance > self.best_performance:
            self.best_performance = performance
            self.best_params = params.copy()

        self.update_count += 1

        if self.update_count % 10 == 0:
            self._explore_or_exploit()

    def _explore_or_exploit(self) -> None:
        """Decide whether to explore new params or exploit best known."""
        if np.random.random() < self.exploration_rate:
            for param, (low, high) in self.param_bounds.items():
                if param in self.current_params:
                    if param in ['batch_size', 'inner_steps']:
                        delta = np.random.randint(-5, 6)
                        self.current_params[param] = int(np.clip(
                            self.current_params[param] + delta, low, high
                        ))
                    elif 'rate' in param or 'lr' in param:
                        log_value = np.log(self.current_params[param])
                        log_value += np.random.normal(0, 0.2)
                        self.current_params[param] = np.clip(np.exp(log_value), low, high)
                    else:
                        delta = np.random.normal(0, (high - low) * 0.1)
                        self.current_params[param] = np.clip(
                            self.current_params[param] + delta, low, high
                        )
        else:
            for param in self.current_params:
                if param in self.best_params:
                    current = self.current_params[param]
                    best = self.best_params[param]
                    self.current_params[param] = current + 0.3 * (best - current)

        self.exploration_rate = max(0.05, self.exploration_rate * 0.99)

    def get_current_params(self) -> Dict[str, float]:
        """Get current hyperparameters."""
        return self.current_params.copy()

    def get_best_params(self) -> Dict[str, float]:
        """Get best observed hyperparameters."""
        return self.best_params.copy()

    def get_statistics(self) -> Dict:
        """Get tuning statistics."""
        return {
            'current_params': self.current_params,
            'best_params': self.best_params,
            'best_performance': self.best_performance,
            'update_count': self.update_count,
            'exploration_rate': self.exploration_rate,
            'recent_performance': list(self.performance_history)[-10:]
        }


if __name__ == "__main__":
    print("=" * 70)
    print("META-LEARNING SYSTEM (PHASE 4 + Phase 8B MAML)")
    print("=" * 70)
    print()
    print("This module implements:")
    print("  - Performance-based learning rate adaptation")
    print("  - Stability detection and oscillation damping")
    print("  - MAML (Model-Agnostic Meta-Learning)")
    print("  - Task distributions for few-shot learning")
    print("  - Adaptive hyperparameter tuning")
    print()

    # Test existing MetaLearner
    print("--- Testing MetaLearner ---")
    meta = MetaLearner()
    for i in range(20):
        outcome = 'success' if np.random.random() > 0.3 else 'failure'
        meta.adapt_meta_parameters(
            outcome=outcome,
            prediction_error=np.random.random() * 0.5,
            confidence=0.5 + np.random.random() * 0.3
        )
    print(f"MetaLearner: {meta}")

    # Test TaskDistribution
    print("\n--- Testing TaskDistribution ---")
    task_dist = TaskDistribution(n_support=5, n_query=10)
    for i in range(50):
        task_dist.add_experience({
            'state': np.random.randn(10).tolist(),
            'action': np.random.randint(0, 5)
        }, domain='test')
    print(f"TaskDistribution: {task_dist.get_statistics()}")

    task = task_dist.sample_task(domain='test')
    print(f"Sampled task: {task.task_id}, support={task.n_support}, query={task.n_query}")

    # Test AdaptiveHyperparameters
    print("\n--- Testing AdaptiveHyperparameters ---")
    hp_tuner = AdaptiveHyperparameters()
    for i in range(30):
        lr = hp_tuner.suggest_lr(current_loss=1.0 / (i + 1))
        hp_tuner.update({'learning_rate': lr}, performance=-np.log(lr + 0.01))
    print(f"Best params: {hp_tuner.get_best_params()}")

    print("\n" + "=" * 70)
    print("Meta-Learning Tests Complete!")
    print("=" * 70)
