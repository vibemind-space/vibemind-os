"""
AGI Meta-Controller - Phase 6 Integration

Central orchestration layer that integrates all AGI components into a
unified, coherent system capable of autonomous operation.

Key Features:
- Unified component orchestration
- Resource allocation and scheduling
- Cross-component communication
- Autonomous operation loop
- Self-monitoring and adaptation
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import threading
import queue
import time
import logging

# Import all AGI components
from .gradient_policy_learner import GradientPolicyLearner
from .ewc_regularization import EWCRegularizer
from .prioritized_replay import PrioritizedReplayBuffer
from .environment_interface import EnvironmentInterface
from .sensorimotor_models import SensorimotorController
from .safety_layer import SafetyLayer
from .intrinsic_curiosity import CuriosityDrivenAgent
from .autonomous_goal_generator import AutonomousGoalGenerator
from .mcts_planner import MCTSPlanner
from .theory_of_mind import TheoryOfMind
from .formal_verifier import create_verifier
from .explanation_generator import ExplanationGenerator
from .multimodal_fusion import MultiModalFusion, Modality
from .distributed_learning import DistributedLearningSystem
from .self_improvement import SelfImprovementEngine

logger = logging.getLogger(__name__)


class SystemState(Enum):
    """Overall system state."""
    INITIALIZING = "initializing"
    IDLE = "idle"
    LEARNING = "learning"
    PLANNING = "planning"
    EXECUTING = "executing"
    SELF_IMPROVING = "self_improving"
    ERROR = "error"
    SHUTDOWN = "shutdown"


class Priority(Enum):
    """Task priority levels."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass
class Task:
    """Internal task representation."""
    task_id: str
    task_type: str
    priority: Priority
    data: Dict[str, Any]
    created_at: float = field(default_factory=time.time)
    deadline: Optional[float] = None
    dependencies: List[str] = field(default_factory=list)


@dataclass
class ComponentStatus:
    """Status of an AGI component."""
    name: str
    active: bool
    last_update: float
    performance: float
    errors: int = 0


@dataclass
class SystemMetrics:
    """Overall system metrics."""
    uptime: float = 0.0
    total_decisions: int = 0
    total_actions: int = 0
    total_learning_steps: int = 0
    avg_decision_time: float = 0.0
    avg_reward: float = 0.0
    goal_completion_rate: float = 0.0
    safety_violations: int = 0


class ResourceManager:
    """
    Manages computational resources across components.
    """

    def __init__(
        self,
        max_memory_mb: int = 4096,
        max_compute_fraction: float = 0.8
    ):
        self.max_memory_mb = max_memory_mb
        self.max_compute_fraction = max_compute_fraction

        # Resource tracking
        self.allocated_memory: Dict[str, int] = {}
        self.compute_allocation: Dict[str, float] = {}

    def request_resources(
        self,
        component_name: str,
        memory_mb: int = 0,
        compute_fraction: float = 0.0
    ) -> bool:
        """Request resources for a component."""
        current_memory = sum(self.allocated_memory.values())
        current_compute = sum(self.compute_allocation.values())

        if current_memory + memory_mb > self.max_memory_mb:
            return False
        if current_compute + compute_fraction > self.max_compute_fraction:
            return False

        self.allocated_memory[component_name] = memory_mb
        self.compute_allocation[component_name] = compute_fraction
        return True

    def release_resources(self, component_name: str):
        """Release resources for a component."""
        self.allocated_memory.pop(component_name, None)
        self.compute_allocation.pop(component_name, None)

    def get_available_resources(self) -> Dict[str, float]:
        """Get available resources."""
        return {
            'memory_mb': self.max_memory_mb - sum(self.allocated_memory.values()),
            'compute_fraction': self.max_compute_fraction - sum(self.compute_allocation.values())
        }


class MessageBus:
    """
    Inter-component communication bus.
    """

    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}
        self.message_queue: queue.Queue = queue.Queue()
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def subscribe(self, topic: str, callback: Callable):
        """Subscribe to a topic."""
        if topic not in self.subscribers:
            self.subscribers[topic] = []
        self.subscribers[topic].append(callback)

    def publish(self, topic: str, message: Any):
        """Publish a message to a topic."""
        self.message_queue.put((topic, message))

    def start(self):
        """Start the message bus."""
        self.running = True
        self._thread = threading.Thread(target=self._process_messages)
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        """Stop the message bus."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def _process_messages(self):
        """Process messages from queue."""
        while self.running:
            try:
                topic, message = self.message_queue.get(timeout=0.1)

                if topic in self.subscribers:
                    for callback in self.subscribers[topic]:
                        try:
                            callback(message)
                        except Exception as e:
                            logger.error(f"Message callback error: {e}")

            except queue.Empty:
                continue


class AGIMetaController:
    """
    Central AGI Meta-Controller.

    Orchestrates all components for unified, autonomous operation.
    """

    def __init__(
        self,
        state_dim: int = 128,
        action_dim: int = 16,
        hidden_dim: int = 256,
        device: str = "cpu"
    ):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.hidden_dim = hidden_dim
        self.device = torch.device(device)

        # System state
        self.state = SystemState.INITIALIZING
        self.start_time = time.time()
        self.metrics = SystemMetrics()

        # Resource management
        self.resource_manager = ResourceManager()
        self.message_bus = MessageBus()

        # Component status tracking
        self.component_status: Dict[str, ComponentStatus] = {}

        # Task queue
        self.task_queue: queue.PriorityQueue = queue.PriorityQueue()

        # Initialize components
        self._init_components()

        # Register message handlers
        self._register_handlers()

        self.state = SystemState.IDLE

    def _init_components(self):
        """Initialize all AGI components."""
        logger.info("Initializing AGI components...")

        # Phase 1: Learning Infrastructure
        self.policy_learner = GradientPolicyLearner(
            self.state_dim, self.action_dim, self.hidden_dim
        )
        self._register_component("policy_learner")

        self.ewc = EWCRegularizer(
            nn.Linear(self.state_dim, self.hidden_dim)
        )
        self._register_component("ewc_regularizer")

        self.replay_buffer = PrioritizedReplayBuffer(
            capacity=100000
        )
        self._register_component("replay_buffer")

        # Phase 2: Embodiment
        self.sensorimotor = SensorimotorController(
            self.state_dim, self.action_dim, self.hidden_dim, device=self.device
        )
        self._register_component("sensorimotor")

        self.safety_layer = SafetyLayer(self.action_dim)
        self._register_component("safety_layer")

        # Phase 3: Motivation
        self.curiosity_agent = CuriosityDrivenAgent(
            self.state_dim, self.action_dim, self.hidden_dim
        )
        self._register_component("curiosity")

        self.goal_generator = AutonomousGoalGenerator(
            self.state_dim, self.hidden_dim, max_active_goals=5
        )
        self._register_component("goal_generator")

        # Phase 4: Higher Cognition
        self.planner = MCTSPlanner(self.state_dim, self.action_dim)
        self._register_component("planner")

        self.theory_of_mind = TheoryOfMind(
            self.state_dim, self.action_dim, hidden_dim=self.hidden_dim
        )
        self._register_component("theory_of_mind")

        # Phase 5: Transparency
        self.verifier = create_verifier(self.state_dim, self.action_dim)
        self._register_component("verifier")

        self.explainer = ExplanationGenerator(
            feature_names=[f"f{i}" for i in range(self.state_dim)],
            decision_space=list(range(self.action_dim))
        )
        self._register_component("explainer")

        # Phase 6: Integration
        self.self_improvement = SelfImprovementEngine(
            nn.Linear(self.state_dim, self.action_dim),
            enable_meta_learning=True,
            enable_diagnosis=True
        )
        self._register_component("self_improvement")

        logger.info(f"Initialized {len(self.component_status)} AGI components")

    def _register_component(self, name: str):
        """Register a component for status tracking."""
        self.component_status[name] = ComponentStatus(
            name=name,
            active=True,
            last_update=time.time(),
            performance=1.0
        )

    def _register_handlers(self):
        """Register message handlers."""
        self.message_bus.subscribe("action_result", self._handle_action_result)
        self.message_bus.subscribe("goal_achieved", self._handle_goal_achieved)
        self.message_bus.subscribe("safety_violation", self._handle_safety_violation)
        self.message_bus.subscribe("performance_update", self._handle_performance_update)

    def _handle_action_result(self, message: Dict[str, Any]):
        """Handle action result messages."""
        self.metrics.total_actions += 1
        if 'reward' in message:
            alpha = 0.01
            self.metrics.avg_reward = (
                (1 - alpha) * self.metrics.avg_reward + alpha * message['reward']
            )

    def _handle_goal_achieved(self, message: Dict[str, Any]):
        """Handle goal achievement messages."""
        alpha = 0.01
        self.metrics.goal_completion_rate = (
            (1 - alpha) * self.metrics.goal_completion_rate + alpha
        )

    def _handle_safety_violation(self, message: Dict[str, Any]):
        """Handle safety violation messages."""
        self.metrics.safety_violations += 1
        logger.warning(f"Safety violation: {message}")

    def _handle_performance_update(self, message: Dict[str, Any]):
        """Handle performance update messages."""
        component = message.get('component')
        performance = message.get('performance', 1.0)

        if component in self.component_status:
            self.component_status[component].performance = performance
            self.component_status[component].last_update = time.time()

    def decide(
        self,
        state: np.ndarray,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Make a decision given current state.

        Integrates all components for optimal decision-making.

        Args:
            state: Current state observation
            context: Optional context information

        Returns:
            action: Selected action
            metadata: Decision metadata including explanations
        """
        decision_start = time.time()
        self.state = SystemState.PLANNING

        context = context or {}
        metadata = {'reasoning_steps': []}

        # Record reasoning step
        self.explainer.record_reasoning_step(
            "Received state observation",
            input_state=state,
            output_state=None,
            confidence=1.0
        )

        # Phase 1: Generate intrinsic motivation
        curiosity_reward, _ = self.curiosity_agent.compute_total_intrinsic_reward(
            state, 0, state  # Will be updated after action
        )
        metadata['curiosity_reward'] = curiosity_reward

        self.explainer.record_reasoning_step(
            f"Computed curiosity reward: {curiosity_reward:.3f}",
            input_state=state,
            output_state=curiosity_reward
        )

        # Phase 2: Generate/update goals
        goals = self.goal_generator.generate_goals(state, world_model=None)
        active_goals = self.goal_generator.get_active_goals()
        metadata['active_goals'] = [g.description for g in active_goals]

        self.explainer.record_reasoning_step(
            f"Active goals: {len(active_goals)}",
            input_state=state,
            output_state=active_goals
        )

        # Phase 3: Plan with MCTS
        state_tensor = torch.FloatTensor(state).unsqueeze(0)

        # Define simple world model for planning (with step and is_terminal methods for MCTSPlanner)
        class SimpleWorldModel:
            def __init__(self, sensorimotor):
                self.sensorimotor = sensorimotor

            def step(self, s, a):
                s_np = s.numpy() if hasattr(s, 'numpy') else np.asarray(s)
                pred_next = self.sensorimotor.predict_next_state(s_np.flatten(), a)
                return torch.FloatTensor(pred_next), 0.0, False

            def is_terminal(self, state):
                # For now, never terminal - this is a simple approximation
                return False, 0.0

        world_model = SimpleWorldModel(self.sensorimotor)

        def valid_actions(s):
            return list(range(self.action_dim))

        planned_action, plan_stats = self.planner.plan(
            state_tensor.numpy(), world_model, valid_actions, horizon=20
        )
        metadata['plan_stats'] = plan_stats

        self.explainer.record_reasoning_step(
            f"MCTS planned action: {planned_action}",
            input_state=state,
            output_state=planned_action,
            confidence=plan_stats.get('confidence', 0.8)
        )

        # Phase 4: Safety check
        safety_report = self.safety_layer.check_action(state, planned_action)
        metadata['safety'] = {
            'safe': safety_report.is_safe,
            'risk': safety_report.risk_score
        }

        if not safety_report.is_safe:
            self.message_bus.publish("safety_violation", {
                'action': planned_action,
                'reason': str(safety_report.violated_constraints)
            })

            # Find safe alternative
            safe_action = self.safety_layer.get_safe_action_mask(state)
            for a in range(self.action_dim):
                if safe_action[a]:
                    planned_action = a
                    break

            self.explainer.record_reasoning_step(
                f"Unsafe action blocked, using safe alternative: {planned_action}",
                input_state=state,
                output_state=planned_action,
                confidence=0.9
            )

        # Phase 5: Policy refinement
        policy_action, policy_info = self.policy_learner.select_action(state)
        policy_value = policy_info.get('value', 0.0)

        # Combine MCTS and policy (weighted by confidence)
        mcts_weight = plan_stats.get('confidence', 0.5)
        if np.random.random() < mcts_weight:
            final_action = planned_action
            metadata['decision_source'] = 'mcts'
        else:
            final_action = policy_action
            metadata['decision_source'] = 'policy'

        self.explainer.record_reasoning_step(
            f"Final action: {final_action} (source: {metadata['decision_source']})",
            input_state=state,
            output_state=final_action,
            confidence=max(mcts_weight, abs(policy_value))
        )

        # Generate explanation
        explanation = self.explainer.generate_explanation(
            state, final_action
        )
        metadata['explanation'] = explanation.summary

        # Update metrics
        decision_time = time.time() - decision_start
        self.metrics.total_decisions += 1
        alpha = 0.01
        self.metrics.avg_decision_time = (
            (1 - alpha) * self.metrics.avg_decision_time + alpha * decision_time
        )

        self.state = SystemState.IDLE
        return final_action, metadata

    def learn(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool
    ):
        """
        Learn from experience.

        Updates all learning components.
        """
        self.state = SystemState.LEARNING

        # Store experience
        self.replay_buffer.add(state, action, reward, next_state, done)

        # Update policy
        self.policy_learner.update_from_feedback(state, action, reward)

        # Update sensorimotor models
        self.sensorimotor.store_experience(state, action, next_state)
        if len(self.sensorimotor.experience_buffer) >= 32:
            self.sensorimotor.train_step(32)

        # Update curiosity
        intrinsic_reward, _ = self.curiosity_agent.compute_total_intrinsic_reward(
            state, action, next_state
        )
        self.curiosity_agent.update(state, action, next_state)

        # Update theory of mind if other agents present
        # (Would be called with observed agent data)

        # Record performance
        self.self_improvement.record_performance("reward", reward)
        self.self_improvement.record_performance("intrinsic_reward", intrinsic_reward)

        self.metrics.total_learning_steps += 1

        # Publish result
        self.message_bus.publish("action_result", {
            'reward': reward,
            'intrinsic_reward': intrinsic_reward,
            'done': done
        })

        self.state = SystemState.IDLE

    def self_improve(self) -> Dict[str, Any]:
        """
        Run self-improvement cycle.
        """
        self.state = SystemState.SELF_IMPROVING

        # Run improvement step
        results = self.self_improvement.continuous_improvement_step()

        # Check component health
        for name, status in self.component_status.items():
            if status.errors > 5:
                logger.warning(f"Component {name} has {status.errors} errors")

        self.state = SystemState.IDLE
        return results

    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        self.metrics.uptime = time.time() - self.start_time

        return {
            'state': self.state.value,
            'metrics': {
                'uptime_seconds': self.metrics.uptime,
                'total_decisions': self.metrics.total_decisions,
                'total_actions': self.metrics.total_actions,
                'total_learning_steps': self.metrics.total_learning_steps,
                'avg_decision_time_ms': self.metrics.avg_decision_time * 1000,
                'avg_reward': self.metrics.avg_reward,
                'goal_completion_rate': self.metrics.goal_completion_rate,
                'safety_violations': self.metrics.safety_violations
            },
            'components': {
                name: {
                    'active': status.active,
                    'performance': status.performance,
                    'errors': status.errors
                }
                for name, status in self.component_status.items()
            },
            'resources': self.resource_manager.get_available_resources(),
            'improvement_report': self.self_improvement.get_improvement_report()
        }

    def explain_decision(
        self,
        state: np.ndarray,
        action: int
    ) -> str:
        """Get human-readable explanation for a decision."""
        return self.explainer.generate_natural_language_explanation(
            state, action, context="the current observation"
        )

    def shutdown(self):
        """Gracefully shutdown the system."""
        self.state = SystemState.SHUTDOWN
        self.message_bus.stop()
        logger.info("AGI Meta-Controller shutdown complete")

    def run_autonomous_loop(
        self,
        env_step_fn: Callable[[int], Tuple[np.ndarray, float, bool]],
        initial_state: np.ndarray,
        max_steps: int = 1000,
        self_improve_interval: int = 100
    ) -> Dict[str, Any]:
        """
        Run autonomous operation loop.

        Args:
            env_step_fn: Function to step environment (action) -> (next_state, reward, done)
            initial_state: Initial state
            max_steps: Maximum steps to run
            self_improve_interval: Steps between self-improvement

        Returns:
            Run statistics
        """
        state = initial_state
        total_reward = 0.0
        episode_rewards = []
        current_episode_reward = 0.0

        self.message_bus.start()

        for step in range(max_steps):
            # Decide
            action, metadata = self.decide(state)

            # Execute
            self.state = SystemState.EXECUTING
            next_state, reward, done = env_step_fn(action)

            # Learn
            self.learn(state, action, reward, next_state, done)

            total_reward += reward
            current_episode_reward += reward
            state = next_state

            # Self-improve periodically
            if (step + 1) % self_improve_interval == 0:
                self.self_improve()

            if done:
                episode_rewards.append(current_episode_reward)
                current_episode_reward = 0.0
                state = initial_state  # Reset

        self.message_bus.stop()

        return {
            'total_steps': max_steps,
            'total_reward': total_reward,
            'avg_episode_reward': np.mean(episode_rewards) if episode_rewards else 0.0,
            'final_status': self.get_system_status()
        }


def create_agi_controller(
    state_dim: int = 128,
    action_dim: int = 16,
    hidden_dim: int = 256,
    device: str = "cpu"
) -> AGIMetaController:
    """
    Factory function to create AGI Meta-Controller.

    Args:
        state_dim: State observation dimension
        action_dim: Action space dimension
        hidden_dim: Hidden layer dimension
        device: Compute device

    Returns:
        Configured AGIMetaController
    """
    return AGIMetaController(
        state_dim=state_dim,
        action_dim=action_dim,
        hidden_dim=hidden_dim,
        device=device
    )
