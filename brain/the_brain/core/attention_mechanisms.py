"""
Attention Mechanisms (PHASE 3)

Implements biologically-inspired attention mechanisms for dynamic resource allocation:

1. Bottom-up attention (saliency-based):
   - Driven by prediction errors and novelty
   - Automatic capture by surprising stimuli

2. Top-down attention (goal-directed):
   - Driven by task context and goals
   - Voluntary focus on task-relevant modalities

3. Attention gating:
   - Modulates brain modality activations
   - Limited resource - competition between modalities

4. Attention tracking:
   - Monitors attention history
   - Detects attention shifts and sustenance

Based on cognitive neuroscience models:
- Posner's model of attention
- Feature Integration Theory (Treisman)
- Biased Competition Model (Desimone & Duncan)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque


@dataclass
class AttentionState:
    """
    Complete attention state at a given moment
    """
    # Bottom-up attention (saliency)
    saliency_map: np.ndarray  # Per-modality saliency scores

    # Top-down attention (goals)
    goal_map: np.ndarray  # Per-modality goal relevance

    # Combined attention
    attention_weights: np.ndarray  # Final attention weights (normalized)

    # Metadata
    dominant_modalities: List[str]  # Top attended modalities
    attention_focus: str  # 'distributed', 'focused', 'shifting'
    total_saliency: float  # Sum of saliency
    total_goal_relevance: float  # Sum of goal relevance

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'saliency_map': self.saliency_map.tolist(),
            'goal_map': self.goal_map.tolist(),
            'attention_weights': self.attention_weights.tolist(),
            'dominant_modalities': self.dominant_modalities,
            'attention_focus': self.attention_focus,
            'total_saliency': float(self.total_saliency),
            'total_goal_relevance': float(self.total_goal_relevance)
        }


class AttentionMechanism:
    """
    Attention mechanism for dynamic resource allocation

    Combines:
    - Bottom-up attention (prediction errors, novelty)
    - Top-down attention (task goals, context)
    - Competition and normalization
    """

    def __init__(
        self,
        num_modalities: int = 10,
        modality_names: Optional[List[str]] = None,
        alpha_bottom_up: float = 0.4,  # Weight for bottom-up attention
        alpha_top_down: float = 0.6,   # Weight for top-down attention
        history_size: int = 50
    ):
        """
        Initialize attention mechanism

        Args:
            num_modalities: Number of brain modalities
            modality_names: Names of modalities
            alpha_bottom_up: Weight for bottom-up (saliency) attention
            alpha_top_down: Weight for top-down (goal) attention
            history_size: Number of attention states to remember
        """
        self.num_modalities = num_modalities

        if modality_names is None:
            self.modality_names = [f"modality_{i}" for i in range(num_modalities)]
        else:
            self.modality_names = modality_names

        self.alpha_bottom_up = alpha_bottom_up
        self.alpha_top_down = alpha_top_down

        # Attention history
        self.attention_history: deque = deque(maxlen=history_size)

        # Statistics
        self.total_attention_updates = 0
        self.attention_shifts = 0  # Count of significant attention shifts

    def compute_saliency(
        self,
        brain_gates: np.ndarray,
        prediction_errors: Optional[Dict] = None,
        novelty_signals: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Compute bottom-up saliency map

        Saliency is driven by:
        1. Prediction errors (high PE = high saliency)
        2. Novelty signals
        3. Current brain activation (strong activation attracts attention)

        Args:
            brain_gates: Current brain gate activations
            prediction_errors: Optional prediction errors by layer
            novelty_signals: Optional per-modality novelty signals

        Returns:
            Saliency map (num_modalities,)
        """
        saliency = np.zeros(self.num_modalities)

        # Component 1: Brain activation (normalized)
        if brain_gates is not None:
            saliency += brain_gates / (np.sum(brain_gates) + 1e-8)

        # Component 2: Prediction errors
        if prediction_errors:
            # Layer 1 prediction error
            layer1_pe = prediction_errors.get('layer1')
            if layer1_pe and 'error_magnitude' in layer1_pe:
                # Distribute error across modalities
                error_boost = layer1_pe['error_magnitude']
                # Boost modalities that are already active
                saliency += error_boost * (brain_gates / (np.sum(brain_gates) + 1e-8))

        # Component 3: Novelty signals
        if novelty_signals is not None:
            saliency += novelty_signals

        # Normalize to [0, 1]
        if np.max(saliency) > 0:
            saliency = saliency / np.max(saliency)

        return saliency

    def compute_goal_relevance(
        self,
        task_type: str,
        task_features: Optional[Dict] = None,
        memory_context: Optional[Dict] = None
    ) -> np.ndarray:
        """
        Compute top-down goal relevance map

        Goal relevance is driven by:
        1. Task type requirements
        2. Task features (complexity, urgency)
        3. Memory of successful modality usage

        Args:
            task_type: Type of task
            task_features: Optional task features (complexity, urgency, etc.)
            memory_context: Optional memory context

        Returns:
            Goal relevance map (num_modalities,)
        """
        goal_map = np.ones(self.num_modalities) * 0.5  # Baseline

        # Task type priors
        # Map task types to modality preferences
        task_type_priors = {
            'docker': [0, 0, 1, 0, 0, 0, 1, 0, 0, 0],  # touch, tool_trace
            'github': [0, 0, 0, 0, 0, 0, 1, 0, 0, 0],  # tool_trace
            'filesystem': [0, 0, 1, 0, 0, 0, 1, 0, 0, 0],  # touch, tool_trace
            'memory': [1, 0, 0, 0, 0, 0, 0, 1, 0, 1],  # vision, temporal, success
            'unknown': [1, 1, 0, 0, 0, 1, 0, 0, 1, 0]  # vision, audio, threat, error
        }

        if task_type in task_type_priors:
            prior = np.array(task_type_priors[task_type])
            goal_map = 0.7 * goal_map + 0.3 * prior

        # Task features modulation
        if task_features:
            urgency = task_features.get('urgency', 0.5)
            complexity = task_features.get('complexity', 0.5)

            # High urgency -> boost threat detection
            if urgency > 0.7 and len(self.modality_names) > 5:
                goal_map[5] += 0.3  # threat modality

            # High complexity -> boost temporal pattern recognition
            if complexity > 0.7 and len(self.modality_names) > 7:
                goal_map[7] += 0.3  # temporal_pattern modality

        # Memory-based priors
        if memory_context:
            # If we have similar past tasks, use their brain gates
            working_mem = memory_context.get('working_memory', {})
            similar = working_mem.get('similar_tasks', [])

            if similar:
                # Average brain gates from similar tasks
                avg_gates = np.zeros(self.num_modalities)
                for task_dict, similarity in similar[:3]:
                    if 'brain_gates' in task_dict:
                        gates = np.array(task_dict['brain_gates'])
                        if len(gates) == self.num_modalities:
                            avg_gates += similarity * gates

                if np.sum(avg_gates) > 0:
                    avg_gates = avg_gates / np.sum(avg_gates)
                    # Blend with goal map
                    goal_map = 0.6 * goal_map + 0.4 * avg_gates

        # Normalize to [0, 1]
        goal_map = np.clip(goal_map, 0, 1)

        return goal_map

    def compute_attention(
        self,
        brain_gates: np.ndarray,
        task_type: str,
        prediction_errors: Optional[Dict] = None,
        task_features: Optional[Dict] = None,
        memory_context: Optional[Dict] = None,
        novelty_signals: Optional[np.ndarray] = None
    ) -> AttentionState:
        """
        Compute complete attention state

        Combines bottom-up and top-down attention with competition

        Args:
            brain_gates: Current brain activations
            task_type: Task type
            prediction_errors: Optional prediction errors
            task_features: Optional task features
            memory_context: Optional memory context
            novelty_signals: Optional novelty signals

        Returns:
            AttentionState with full attention information
        """
        # Compute bottom-up saliency
        saliency_map = self.compute_saliency(
            brain_gates=brain_gates,
            prediction_errors=prediction_errors,
            novelty_signals=novelty_signals
        )

        # Compute top-down goal relevance
        goal_map = self.compute_goal_relevance(
            task_type=task_type,
            task_features=task_features,
            memory_context=memory_context
        )

        # Combine with weighted sum
        combined = (
            self.alpha_bottom_up * saliency_map +
            self.alpha_top_down * goal_map
        )

        # Normalize to create attention weights (sum to 1)
        attention_weights = combined / (np.sum(combined) + 1e-8)

        # Detect dominant modalities (top 3)
        top_indices = np.argsort(attention_weights)[::-1][:3]
        dominant_modalities = [self.modality_names[i] for i in top_indices]

        # Determine attention focus type
        # Entropy-based measure: low entropy = focused, high entropy = distributed
        entropy = -np.sum(attention_weights * np.log(attention_weights + 1e-8))
        max_entropy = np.log(self.num_modalities)

        if entropy < 0.3 * max_entropy:
            attention_focus = 'focused'
        elif entropy > 0.7 * max_entropy:
            attention_focus = 'distributed'
        else:
            attention_focus = 'shifting'

        # Create attention state
        attention_state = AttentionState(
            saliency_map=saliency_map,
            goal_map=goal_map,
            attention_weights=attention_weights,
            dominant_modalities=dominant_modalities,
            attention_focus=attention_focus,
            total_saliency=float(np.sum(saliency_map)),
            total_goal_relevance=float(np.sum(goal_map))
        )

        # Detect attention shift
        if self.attention_history:
            prev_state = self.attention_history[-1]
            # Compare dominant modalities
            if set(prev_state.dominant_modalities[:2]) != set(dominant_modalities[:2]):
                self.attention_shifts += 1

        # Record in history
        self.attention_history.append(attention_state)
        self.total_attention_updates += 1

        return attention_state

    def apply_attention_gating(
        self,
        brain_gates: np.ndarray,
        attention_weights: np.ndarray,
        gating_strength: float = 0.5
    ) -> np.ndarray:
        """
        Apply attention gating to brain activations

        Modulates brain gates by attention weights

        Args:
            brain_gates: Original brain gates
            attention_weights: Attention weights
            gating_strength: How strongly attention modulates gates (0-1)

        Returns:
            Attention-gated brain activations
        """
        # Blend original gates with attention-modulated gates
        modulated = brain_gates * (1 + gating_strength * (attention_weights - 0.5))

        # Normalize to maintain total activation
        modulated = modulated / (np.sum(modulated) + 1e-8) * np.sum(brain_gates)

        return modulated

    def get_attention_statistics(self) -> Dict:
        """Get statistics about attention over time"""
        if not self.attention_history:
            return {
                'total_updates': 0,
                'attention_shifts': 0
            }

        # Analyze recent attention patterns
        recent = list(self.attention_history)[-20:]

        # Count focus types
        focus_types = [state.attention_focus for state in recent]
        from collections import Counter
        focus_counts = Counter(focus_types)

        # Average saliency and goal relevance
        avg_saliency = np.mean([state.total_saliency for state in recent])
        avg_goal_relevance = np.mean([state.total_goal_relevance for state in recent])

        # Most attended modalities
        all_dominant = []
        for state in recent:
            all_dominant.extend(state.dominant_modalities[:2])
        modality_counts = Counter(all_dominant)

        return {
            'total_updates': self.total_attention_updates,
            'attention_shifts': self.attention_shifts,
            'focus_distribution': dict(focus_counts),
            'average_saliency': float(avg_saliency),
            'average_goal_relevance': float(avg_goal_relevance),
            'most_attended_modalities': modality_counts.most_common(5)
        }

    def __repr__(self):
        return (
            f"AttentionMechanism("
            f"modalities={self.num_modalities}, "
            f"updates={self.total_attention_updates}, "
            f"shifts={self.attention_shifts})"
        )


if __name__ == "__main__":
    print("=" * 70)
    print("ATTENTION MECHANISMS (PHASE 3)")
    print("=" * 70)
    print()
    print("This module implements biologically-inspired attention:")
    print("  - Bottom-up attention (saliency from prediction errors)")
    print("  - Top-down attention (goal-directed from task context)")
    print("  - Attention gating (modulating brain activations)")
    print("  - Attention tracking (monitoring shifts and focus)")
    print()
    print("To test the complete system, run:")
    print("  python demos/test_attention_mechanisms.py")
    print()
    print("=" * 70)
