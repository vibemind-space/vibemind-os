"""
Prefrontal Cortex Module - Neuroscience Architecture Extension Phase A2

Computational model of the prefrontal cortex for working memory,
executive control, value-based decisions, and cognitive flexibility.

Neuroscience basis:
- DLPFC: Working memory, cognitive flexibility (Goldman-Rakic, 1995)
- vmPFC: Value-based decisions, outcome evaluation (Rushworth et al., 2011)
- OFC: Reward prediction, expectation updating (Schoenbaum et al., 2009)
- Miller & Cohen (2001): PFC as "bias signal" for task-set selection
- Persistent activity: Sustained firing during delay periods

Key references:
- Miller & Cohen (2001): An integrative theory of PFC function
- Goldman-Rakic (1995): Cellular basis of working memory
- Fuster (2001): The prefrontal cortex - an update

Integration points:
- Input: Thalamus (sensory), Hippocampus (memories), Amygdala (emotion)
- Output: Top-down bias to Thalamus (attention), Basal Ganglia (action selection)
- Wiring: agent_loop.prefrontal_cortex = PrefrontalCortex.from_yaml(config)
"""

import logging
import time
from collections import deque, OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger('brain.prefrontal_cortex')


# ─── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class WorkingMemoryItem:
    """An item held in working memory."""
    content: np.ndarray
    label: str = ""
    relevance: float = 1.0
    age: int = 0
    timestamp: float = field(default_factory=time.time)

    def decay(self, rate: float = 0.05):
        self.relevance *= (1.0 - rate)
        self.age += 1


@dataclass
class TaskSet:
    """A task-set (rule mapping) maintained by PFC."""
    name: str
    rule_vector: np.ndarray
    priority: float = 1.0
    active: bool = False
    switch_cost: float = 0.1
    uses: int = 0


@dataclass
class PFCStats:
    """Aggregate PFC statistics."""
    wm_items: int = 0
    wm_capacity: int = 7
    active_task: str = ""
    task_switches: int = 0
    inhibitions: int = 0
    value_estimates: int = 0
    avg_value: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'wm_items': self.wm_items,
            'wm_capacity': self.wm_capacity,
            'active_task': self.active_task,
            'task_switches': self.task_switches,
            'inhibitions': self.inhibitions,
            'value_estimates': self.value_estimates,
            'avg_value': self.avg_value,
        }


# ─── Working Memory Buffer (DLPFC) ────────────────────────────────────────────

class WorkingMemoryBuffer:
    """
    Working memory buffer modeling DLPFC persistent activity.

    Capacity limited (~7 items, Miller's Law) with relevance-based
    displacement. Items decay over time unless refreshed.

    Goldman-Rakic (1995): Sustained firing of DLPFC neurons during
    delay periods represents working memory maintenance.
    """

    def __init__(self, capacity: int = 7, state_dim: int = 32, decay_rate: float = 0.05):
        self.capacity = capacity
        self.state_dim = state_dim
        self.decay_rate = decay_rate
        self._items: List[WorkingMemoryItem] = []

    def store(self, content: np.ndarray, label: str = "", relevance: float = 1.0) -> bool:
        """
        Store item in working memory. Displaces least relevant if full.

        Returns:
            True if stored successfully
        """
        content = np.asarray(content, dtype=np.float32).flatten()

        item = WorkingMemoryItem(
            content=content[:self.state_dim] if len(content) > self.state_dim else content,
            label=label,
            relevance=relevance,
        )

        if len(self._items) >= self.capacity:
            # Displace least relevant
            self._items.sort(key=lambda x: x.relevance, reverse=True)
            self._items.pop()

        self._items.append(item)
        return True

    def retrieve(self, query: Optional[np.ndarray] = None, top_k: int = 1) -> List[WorkingMemoryItem]:
        """
        Retrieve items from working memory.

        If query is provided, returns most similar items.
        Otherwise returns most relevant items.
        """
        if not self._items:
            return []

        if query is not None:
            q = np.asarray(query, dtype=np.float32).flatten()
            scored = []
            for item in self._items:
                c = item.content
                min_dim = min(len(q), len(c))
                sim = float(np.dot(q[:min_dim], c[:min_dim]) /
                           (np.linalg.norm(q[:min_dim]) * np.linalg.norm(c[:min_dim]) + 1e-8))
                scored.append((sim * item.relevance, item))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [item for _, item in scored[:top_k]]
        else:
            sorted_items = sorted(self._items, key=lambda x: x.relevance, reverse=True)
            return sorted_items[:top_k]

    def refresh(self, label: str):
        """Refresh an item (reset its relevance) by attentional rehearsal."""
        for item in self._items:
            if item.label == label:
                item.relevance = 1.0
                item.age = 0
                return True
        return False

    def tick(self):
        """Advance time: decay all items and remove negligible ones."""
        for item in self._items:
            item.decay(self.decay_rate)
        self._items = [i for i in self._items if i.relevance > 0.01]

    def clear(self):
        """Clear working memory."""
        self._items.clear()

    def get_contents_vector(self) -> np.ndarray:
        """Return mean vector of all WM contents (for downstream use)."""
        if not self._items:
            return np.zeros(self.state_dim, dtype=np.float32)
        vectors = [i.content for i in self._items]
        # Pad to state_dim
        padded = []
        for v in vectors:
            p = np.zeros(self.state_dim, dtype=np.float32)
            n = min(len(v), self.state_dim)
            p[:n] = v[:n]
            padded.append(p)
        return np.mean(padded, axis=0).astype(np.float32)

    @property
    def count(self) -> int:
        return len(self._items)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'count': self.count,
            'capacity': self.capacity,
            'items': [{'label': i.label, 'relevance': round(i.relevance, 3), 'age': i.age}
                      for i in self._items],
        }


# ─── Cognitive Control Unit (DLPFC) ───────────────────────────────────────────

class CognitiveControlUnit:
    """
    Cognitive control for task-set management and switching.

    Miller & Cohen (2001): PFC maintains task-relevant patterns of
    activity that serve as bias signals, guiding the flow of neural
    activity along pathways that implement a given task.
    """

    def __init__(self, n_rules: int = 10, state_dim: int = 32, switch_cost: float = 0.1):
        self.n_rules = n_rules
        self.state_dim = state_dim
        self.switch_cost = switch_cost
        self._task_sets: Dict[str, TaskSet] = {}
        self._active_task: Optional[str] = None
        self._switch_count = 0

    def register_task(self, name: str, rule_vector: np.ndarray, priority: float = 1.0):
        """Register a task-set (rule mapping)."""
        vec = np.asarray(rule_vector, dtype=np.float32).flatten()
        self._task_sets[name] = TaskSet(
            name=name,
            rule_vector=vec,
            priority=priority,
            switch_cost=self.switch_cost,
        )

    def select_task(self, context: np.ndarray) -> Tuple[str, np.ndarray]:
        """
        Select best task-set given current context.

        Returns:
            (task_name, bias_signal)
        """
        if not self._task_sets:
            return "", np.zeros(self.state_dim, dtype=np.float32)

        ctx = np.asarray(context, dtype=np.float32).flatten()
        best_name = ""
        best_score = -float('inf')

        for name, ts in self._task_sets.items():
            min_dim = min(len(ctx), len(ts.rule_vector))
            match = float(np.dot(ctx[:min_dim], ts.rule_vector[:min_dim]))
            score = match * ts.priority

            # Apply switch cost if different from current
            if self._active_task and name != self._active_task:
                score -= ts.switch_cost

            if score > best_score:
                best_score = score
                best_name = name

        if best_name and best_name != self._active_task:
            self._switch_count += 1
            if self._active_task and self._active_task in self._task_sets:
                self._task_sets[self._active_task].active = False

        self._active_task = best_name
        if best_name in self._task_sets:
            self._task_sets[best_name].active = True
            self._task_sets[best_name].uses += 1

        bias_signal = self._task_sets[best_name].rule_vector if best_name else np.zeros(self.state_dim, dtype=np.float32)
        return best_name, bias_signal

    @property
    def active_task(self) -> Optional[str]:
        return self._active_task

    @property
    def switch_count(self) -> int:
        return self._switch_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            'active_task': self._active_task,
            'n_tasks': len(self._task_sets),
            'switch_count': self._switch_count,
            'tasks': {name: {'priority': ts.priority, 'active': ts.active, 'uses': ts.uses}
                      for name, ts in self._task_sets.items()},
        }


# ─── Value Estimator (vmPFC) ──────────────────────────────────────────────────

class ValueEstimator:
    """
    Value estimation modeling vmPFC function.

    The vmPFC computes the subjective value of states and options,
    integrating reward history, effort costs, and emotional valence.

    Rushworth et al. (2011): vmPFC tracks expected value and
    guides value-based decisions.
    """

    def __init__(self, state_dim: int = 32, learning_rate: float = 0.01):
        self.state_dim = state_dim
        self.learning_rate = learning_rate
        self._weights = np.zeros(state_dim, dtype=np.float32)
        self._bias = 0.0
        self._value_history = deque(maxlen=100)

    def estimate_value(self, state: np.ndarray) -> float:
        """
        Estimate the value of a state.

        Args:
            state: State vector

        Returns:
            Estimated value (unbounded)
        """
        s = np.asarray(state, dtype=np.float32).flatten()
        padded = np.zeros(self.state_dim, dtype=np.float32)
        n = min(len(s), self.state_dim)
        padded[:n] = s[:n]

        value = float(np.dot(self._weights, padded) + self._bias)
        self._value_history.append(value)
        return value

    def update(self, state: np.ndarray, target_value: float) -> float:
        """
        Update value estimate from observed outcome.

        Returns:
            Prediction error (target - estimate)
        """
        s = np.asarray(state, dtype=np.float32).flatten()
        padded = np.zeros(self.state_dim, dtype=np.float32)
        n = min(len(s), self.state_dim)
        padded[:n] = s[:n]

        predicted = float(np.dot(self._weights, padded) + self._bias)
        error = target_value - predicted

        # Gradient update
        self._weights += self.learning_rate * error * padded
        self._bias += self.learning_rate * error

        return error

    def get_avg_value(self) -> float:
        if not self._value_history:
            return 0.0
        return float(np.mean(list(self._value_history)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'state_dim': self.state_dim,
            'avg_value': self.get_avg_value(),
            'weight_norm': float(np.linalg.norm(self._weights)),
        }


# ─── Reward Prediction Unit (OFC) ─────────────────────────────────────────────

class RewardPredictionUnit:
    """
    Reward prediction modeling OFC function.

    The OFC predicts expected rewards and detects violations of
    reward expectations, driving flexible behavior adaptation.

    Schoenbaum et al. (2009): OFC signals expected outcomes
    and updates when expectations are violated.
    """

    def __init__(self, state_dim: int = 32, n_outcomes: int = 4, learning_rate: float = 0.02):
        self.state_dim = state_dim
        self.n_outcomes = n_outcomes
        self.learning_rate = learning_rate

        # Weights for predicting reward given state
        self._weights = np.random.randn(state_dim, n_outcomes).astype(np.float32) * 0.01
        self._expectation_violations = deque(maxlen=100)

    def predict_reward(self, state: np.ndarray) -> np.ndarray:
        """
        Predict expected rewards for each possible outcome.

        Returns:
            Expected reward vector [n_outcomes]
        """
        s = np.asarray(state, dtype=np.float32).flatten()
        padded = np.zeros(self.state_dim, dtype=np.float32)
        n = min(len(s), self.state_dim)
        padded[:n] = s[:n]

        return np.tanh(padded @ self._weights)

    def update_expectation(self, state: np.ndarray, outcome_idx: int, actual_reward: float) -> float:
        """
        Update reward prediction from actual outcome.

        Returns:
            Reward prediction error
        """
        s = np.asarray(state, dtype=np.float32).flatten()
        padded = np.zeros(self.state_dim, dtype=np.float32)
        n = min(len(s), self.state_dim)
        padded[:n] = s[:n]

        predicted = float(np.tanh(padded @ self._weights[:, outcome_idx]))
        rpe = actual_reward - predicted

        # Update weights
        self._weights[:, outcome_idx] += self.learning_rate * rpe * padded
        np.clip(self._weights, -3.0, 3.0, out=self._weights)

        self._expectation_violations.append(abs(rpe))
        return rpe

    def get_surprise(self) -> float:
        """Return recent average expectation violation."""
        if not self._expectation_violations:
            return 0.0
        return float(np.mean(list(self._expectation_violations)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'n_outcomes': self.n_outcomes,
            'surprise': self.get_surprise(),
        }


# ─── Inhibitory Control ───────────────────────────────────────────────────────

class InhibitoryControl:
    """
    Go/NoGo mechanism modeling PFC inhibitory function.

    The PFC exerts top-down inhibition to suppress prepotent but
    inappropriate responses (Aron et al., 2004).
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self._inhibition_count = 0

    def should_inhibit(self, action_urgency: float, conflict_level: float) -> bool:
        """
        Decide whether to inhibit an action.

        Args:
            action_urgency: How urgent the action is [0, 1]
            conflict_level: How much conflict exists [0, 1]

        Returns:
            True if action should be inhibited
        """
        # Inhibit when conflict is high relative to urgency
        inhibit = conflict_level > self.threshold and conflict_level > action_urgency
        if inhibit:
            self._inhibition_count += 1
        return inhibit

    @property
    def inhibition_count(self) -> int:
        return self._inhibition_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            'threshold': self.threshold,
            'inhibition_count': self._inhibition_count,
        }


# ─── Main Prefrontal Cortex Module ────────────────────────────────────────────

class PrefrontalCortex:
    """
    Complete prefrontal cortex module integrating all sub-regions.

    Functions:
    1. Working memory maintenance (DLPFC)
    2. Cognitive control and task switching (DLPFC)
    3. Value estimation (vmPFC)
    4. Reward prediction and surprise detection (OFC)
    5. Inhibitory control (lateral PFC)
    6. Top-down bias signal generation
    """

    def __init__(
        self,
        state_dim: int = 32,
        working_memory_capacity: int = 7,
        n_rules: int = 10,
        inhibition_threshold: float = 0.6,
        task_switch_cost: float = 0.1,
        learning_rate: float = 0.01,
    ):
        self.state_dim = state_dim

        # Sub-regions
        self.working_memory = WorkingMemoryBuffer(
            capacity=working_memory_capacity,
            state_dim=state_dim,
        )
        self.cognitive_control = CognitiveControlUnit(
            n_rules=n_rules,
            state_dim=state_dim,
            switch_cost=task_switch_cost,
        )
        self.value_estimator = ValueEstimator(
            state_dim=state_dim,
            learning_rate=learning_rate,
        )
        self.reward_prediction = RewardPredictionUnit(
            state_dim=state_dim,
            learning_rate=learning_rate * 2,
        )
        self.inhibitory_control = InhibitoryControl(
            threshold=inhibition_threshold,
        )

        self._stats = PFCStats(wm_capacity=working_memory_capacity)

    def process(self, state: np.ndarray, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Full PFC processing cycle.

        1. Store relevant info in working memory
        2. Select appropriate task-set
        3. Estimate state value
        4. Generate top-down bias signal

        Args:
            state: Current state vector
            context: Optional context dict with 'task_label', 'urgency', etc.

        Returns:
            Dict with 'bias_signal', 'value', 'task', 'inhibit'
        """
        ctx = context or {}
        state_arr = np.asarray(state, dtype=np.float32).flatten()

        # 1. Working memory update
        self.working_memory.tick()
        label = ctx.get('task_label', f"state_{self._stats.value_estimates}")
        self.working_memory.store(state_arr, label=label)

        # 2. Task selection
        wm_context = self.working_memory.get_contents_vector()
        task_name, bias_signal = self.cognitive_control.select_task(wm_context)

        # 3. Value estimation
        value = self.value_estimator.estimate_value(state_arr)
        self._stats.value_estimates += 1

        # 4. Reward prediction
        expected_rewards = self.reward_prediction.predict_reward(state_arr)

        # 5. Inhibitory check
        urgency = ctx.get('urgency', 0.5)
        conflict = ctx.get('conflict', 0.0)
        should_inhibit = self.inhibitory_control.should_inhibit(urgency, conflict)

        # Update stats
        self._stats.wm_items = self.working_memory.count
        self._stats.active_task = task_name or ""
        self._stats.task_switches = self.cognitive_control.switch_count
        self._stats.inhibitions = self.inhibitory_control.inhibition_count
        self._stats.avg_value = self.value_estimator.get_avg_value()

        return {
            'bias_signal': bias_signal,
            'value': value,
            'task': task_name,
            'inhibit': should_inhibit,
            'expected_rewards': expected_rewards,
            'wm_contents': wm_context,
            'surprise': self.reward_prediction.get_surprise(),
        }

    def learn_from_outcome(self, state: np.ndarray, reward: float, outcome_idx: int = 0) -> Dict[str, float]:
        """
        Learn from observed outcome.

        Updates both value estimator and reward prediction.
        """
        value_error = self.value_estimator.update(state, reward)
        reward_pe = self.reward_prediction.update_expectation(state, outcome_idx, reward)
        return {
            'value_error': value_error,
            'reward_prediction_error': reward_pe,
        }

    def hierarchical_control_signal(
        self,
        goal_abstraction_level: float = 0.5,
        da_level: float = 0.5,
    ) -> Dict[str, float]:
        """
        Hierarchical cognitive control along rostro-caudal PFC axis.

        Badre & D'Esposito (2009): PFC is organized along an abstraction
        gradient — posterior PFC handles concrete stimulus-response mappings,
        anterior PFC handles abstract rules and long-horizon goals.
        DA gating (Goldman-Rakic 1995) controls WM updating.

        Args:
            goal_abstraction_level: How abstract the current goal is [0=concrete, 1=abstract]
            da_level: Dopamine level from VTA (gates WM updating) [0, 1]

        Returns:
            Dict with control levels at each PFC tier
        """
        # Posterior PFC: stimulus-response (always active for concrete)
        posterior = max(0.0, 1.0 - goal_abstraction_level * 0.8)

        # Mid-lateral PFC: rule-based control
        mid_lateral = 1.0 - 2.0 * (goal_abstraction_level - 0.4) ** 2
        mid_lateral = max(0.2, min(1.0, mid_lateral))

        # Anterior/frontopolar PFC: abstract goals, branching
        anterior = goal_abstraction_level ** 0.8

        # DA gating: inverted-U for WM updating
        optimal_da = 0.55
        gating_efficiency = max(0.0, 1.0 - abs(da_level - optimal_da) / optimal_da)

        # Overall control strength = weighted by abstraction
        control_strength = (
            posterior * (1.0 - goal_abstraction_level)
            + anterior * goal_abstraction_level
        ) * (0.5 + gating_efficiency * 0.5)

        return {
            'posterior_pfc': round(posterior, 4),
            'mid_lateral_pfc': round(mid_lateral, 4),
            'anterior_pfc': round(anterior, 4),
            'da_gating_efficiency': round(gating_efficiency, 4),
            'control_strength': round(min(1.0, control_strength), 4),
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            'stats': self._stats.to_dict(),
            'working_memory': self.working_memory.to_dict(),
            'cognitive_control': self.cognitive_control.to_dict(),
            'value': self.value_estimator.to_dict(),
            'reward_prediction': self.reward_prediction.to_dict(),
            'inhibition': self.inhibitory_control.to_dict(),
        }

    def get_stats(self) -> PFCStats:
        return self._stats

    def reset(self):
        self.working_memory.clear()
        self._stats = PFCStats(wm_capacity=self.working_memory.capacity)

    def to_dict(self) -> Dict[str, Any]:
        return self.get_state()

    @classmethod
    def from_yaml(cls, config: Dict[str, Any]) -> 'PrefrontalCortex':
        """
        Create PrefrontalCortex from YAML configuration.

        Expected config:
            prefrontal_cortex:
              working_memory_capacity: 7
              cognitive_control_rules: 10
              inhibition_threshold: 0.6
              task_switch_cost: 0.1
        """
        pfc = config.get('prefrontal_cortex', {})
        state_dim = config.get('state_dim',
                    config.get('model', {}).get('input_dim', 32))

        return cls(
            state_dim=state_dim,
            working_memory_capacity=pfc.get('working_memory_capacity', 7),
            n_rules=pfc.get('cognitive_control_rules', 10),
            inhibition_threshold=pfc.get('inhibition_threshold', 0.6),
            task_switch_cost=pfc.get('task_switch_cost', 0.1),
            learning_rate=pfc.get('learning_rate', 0.01),
        )
