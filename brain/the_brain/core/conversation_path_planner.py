"""
Conversation Path Planner - Brain-based puzzle solver for agent conversations

Integrates:
- ConversationGraph: State space representation
- MetaRouter: Thalamic routing + hippocampal memory
- StrategyLibrary: Proven successful sequences
- Hierarchical routing: Multi-layer decision making

Given a task like "git add and push", the brain:
1. Searches episodic memory for similar past sessions
2. Builds conversation graph from all observed traces
3. Finds optimal path through graph (A* search)
4. Returns predicted command sequence with expected outcome

This is like solving a Klotski puzzle, but for agent conversations.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import json

from core.conversation_graph import ConversationGraph, ConversationState
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor
from core.conversation_trace_encoder import load_session_logs
from core.multi_target_router import MultiTargetDecisionRouter, MultiTargetDecision


@dataclass
class PathPrediction:
    """
    Predicted optimal path through conversation space
    """
    task_type: str
    predicted_sequence: List[str]  # Tool names in order
    expected_duration: float        # Estimated duration in seconds
    expected_errors: int            # Estimated error count
    success_probability: float      # Probability of success
    confidence: float               # Overall confidence (0-1)

    # Supporting evidence
    similar_sessions: int           # Number of similar past sessions
    alternative_paths: List[List[str]]  # Alternative sequences

    # Brain routing info
    dominant_modalities: List[str]  # Which brain areas are most active
    memory_retrieval: Dict          # Hippocampal memory info

    # Phase 3: Multi-target decision routing
    multi_target_decision: Optional[Dict] = None  # Weighted intervention decisions


class ConversationPathPlanner:
    """
    Brain-based path planner for agent conversations

    Combines graph search with neural routing to predict optimal
    sequences of actions for completing tasks.
    """

    def __init__(
        self,
        meta_router: MetaRouter,
        strategy_library: StrategyLibrary,
        brain_monitor: Optional[BrainActivityMonitor] = None,
        # Learnable gate temperature parameters
        enable_adaptive_gating: bool = True,
        initial_gate_temp: float = 0.5,
        gate_temp_lr: float = 0.01,
        gate_temp_min: float = 0.1,
        gate_temp_max: float = 2.0
    ):
        self.meta_router = meta_router
        self.strategy_library = strategy_library
        self.brain_monitor = brain_monitor

        # Conversation graph (built from training data)
        self.graph = ConversationGraph()

        # === LEARNABLE GATE TEMPERATURE (Phase 1) ===
        self.enable_adaptive_gating = enable_adaptive_gating
        self.log_gate_temp = np.log(initial_gate_temp)  # Log-space for positivity
        self.gate_temp_lr = gate_temp_lr
        self.gate_temp_min = gate_temp_min
        self.gate_temp_max = gate_temp_max

        # Statistics for adaptation
        self.predictions_made = 0
        self.predictions_correct = 0
        self.recent_accuracies = []  # Track recent prediction accuracy
        self.gate_temp_history = []  # Track temperature evolution

        # === Phase 3: Multi-Target Decision Router ===
        self.multi_target_router = MultiTargetDecisionRouter(
            num_modalities=10,  # Standard ATM-R modalities
            intervention_types=['suggest', 'retry', 'wait', 'terminate'],
            seed=42
        )

    @property
    def gate_temp(self) -> float:
        """Get current gate temperature (always positive via exp)"""
        return float(np.exp(self.log_gate_temp))

    def adapt_gate_temperature(self, prediction_accuracy: float):
        """
        Adapt gate temperature based on prediction accuracy

        Concept from routed_brain.py:
        - High accuracy (>0.8) → sharper gates (decrease τ_g)
        - Low accuracy (<0.6) → softer gates (increase τ_g)

        Rationale:
        - When predictions are accurate, the brain should commit more strongly (sharp routing)
        - When predictions are uncertain, the brain should hedge bets (soft routing)

        Args:
            prediction_accuracy: Accuracy of recent predictions (0-1)
        """
        if not self.enable_adaptive_gating:
            return

        # High confidence → sharper gates (lower temp)
        if prediction_accuracy > 0.8:
            self.log_gate_temp -= self.gate_temp_lr
        # Low confidence → softer gates (higher temp)
        elif prediction_accuracy < 0.6:
            self.log_gate_temp += self.gate_temp_lr
        # Medium confidence → small adjustment toward optimal
        else:
            # Gentle nudge toward 0.5 (balanced)
            target_log_temp = np.log(0.5)
            self.log_gate_temp += 0.1 * self.gate_temp_lr * (target_log_temp - self.log_gate_temp)

        # Clip to bounds
        self.log_gate_temp = np.clip(
            self.log_gate_temp,
            np.log(self.gate_temp_min),
            np.log(self.gate_temp_max)
        )

        # Record for visualization
        self.gate_temp_history.append(self.gate_temp)

        # Propagate to meta_router's underlying thalamo system
        if hasattr(self.meta_router, 'thalamo_system') and hasattr(self.meta_router.thalamo_system, 'thalamus'):
            self.meta_router.thalamo_system.thalamus.set_gating_temp(self.gate_temp)

    def provide_prediction_feedback(self, prediction_correct: bool):
        """
        Provide feedback on whether a prediction was correct

        This enables the system to learn optimal gate temperature based on
        prediction accuracy over time.

        Args:
            prediction_correct: True if prediction matched actual outcome
        """
        if prediction_correct:
            self.predictions_correct += 1

        # Calculate recent accuracy (window of last 10 predictions)
        self.recent_accuracies.append(1.0 if prediction_correct else 0.0)
        if len(self.recent_accuracies) > 10:
            self.recent_accuracies.pop(0)

        recent_accuracy = np.mean(self.recent_accuracies) if self.recent_accuracies else 0.5

        # Adapt gate temperature based on accuracy
        self.adapt_gate_temperature(recent_accuracy)

        if self.enable_adaptive_gating:
            feedback_symbol = 'OK' if prediction_correct else 'XX'
            print(f"[GateTemp] Feedback: {feedback_symbol} | "
                  f"Recent accuracy: {recent_accuracy:.1%} | "
                  f"Gate temp: {self.gate_temp:.3f}")

    def train_from_sessions(self, session_log_dir: str, limit: Optional[int] = None):
        """
        Train the path planner from session logs

        Builds conversation graph and trains neural routing system.
        """
        print(f"Loading session logs from {session_log_dir}...")
        traces = load_session_logs(session_log_dir, limit=limit)
        print(f"Loaded {len(traces)} conversation traces")

        print("Building conversation graph...")
        for trace in traces:
            features = trace.get_features()

            # Add to graph
            self.graph.add_conversation_trace(features)

            # Train meta-router
            out = self.meta_router.process_trace(trace, adapt=True)

            if self.brain_monitor:
                self.brain_monitor.update(out)

            # Add successful strategies
            if features['success']:
                self.strategy_library.add_strategy(
                    task_type=features['tool_type'],
                    tool_sequence=features['tools_used'],
                    duration=features['duration_seconds'],
                    success=True
                )

        graph_stats = self.graph.get_statistics()
        print(f"Graph built: {graph_stats['total_states']} states, "
              f"{graph_stats['total_transitions']} transitions")
        print(f"Task types: {list(graph_stats['task_distribution'].keys())}")
        print(f"Strategies learned: {self.strategy_library.total_strategies}")

    def predict_optimal_path(
        self,
        task_description: str,
        task_type: Optional[str] = None,
        max_steps: int = 10,
        max_errors: int = 3
    ) -> Optional[PathPrediction]:
        """
        Predict optimal path for completing a task

        Args:
            task_description: Natural language description (e.g., "git add and push")
            task_type: Optional task type hint (e.g., 'github')
            max_steps: Maximum number of steps to consider
            max_errors: Maximum tolerable errors

        Returns:
            PathPrediction with optimal sequence and expected outcome
        """
        # Infer task type if not provided
        if task_type is None:
            task_type = self._infer_task_type(task_description)

        print(f"\n[PathPlanner] Predicting path for: '{task_description}'")
        print(f"[PathPlanner] Inferred task type: {task_type}")

        # === LAYER 1: RETRIEVE FROM STRATEGY LIBRARY ===
        strategy_rec = self.strategy_library.get_recommendation(
            task_type=task_type,
            current_errors=0
        )

        # === LAYER 2: SEARCH CONVERSATION GRAPH ===
        graph_path = self.graph.find_optimal_path(
            start_task_type=task_type,
            max_steps=max_steps,
            max_errors=max_errors
        )

        # === LAYER 3: COMBINE RECOMMENDATIONS ===
        # Prefer graph path if available (more comprehensive)
        if graph_path:
            predicted_sequence = graph_path
            source = "graph_search"
        elif strategy_rec:
            predicted_sequence = strategy_rec['strategy']
            source = "strategy_library"
        else:
            print(f"[PathPlanner] No path found for task type: {task_type}")
            return None

        print(f"[PathPlanner] Path source: {source}")
        print(f"[PathPlanner] Predicted sequence: {' -> '.join(predicted_sequence)}")

        # === ESTIMATE OUTCOME ===
        # Get statistics from similar successful sessions
        similar_states = [
            state for state in self.graph.states
            if state.task_type == task_type and state.success
        ]

        if similar_states:
            expected_duration = np.mean([s.duration for s in similar_states])
            expected_errors = np.mean([s.error_count for s in similar_states])
            success_probability = len(similar_states) / len([
                s for s in self.graph.states if s.task_type == task_type
            ])
        else:
            # Fallback estimates
            expected_duration = len(predicted_sequence) * 5.0  # 5s per tool
            expected_errors = 0
            success_probability = 0.7 if strategy_rec else 0.5

        # Calculate confidence
        confidence = self._calculate_confidence(
            task_type=task_type,
            num_similar=len(similar_states),
            success_prob=success_probability
        )

        # Get alternative paths
        alternative_paths = []
        if strategy_rec and strategy_rec.get('alternatives'):
            alternative_paths = [alt['tools'] for alt in strategy_rec['alternatives'][:3]]

        # Get brain routing info
        dominant_modalities = self._get_dominant_modalities(task_type)
        memory_info = self.meta_router.get_state()

        # === Phase 3: Multi-Target Decision Routing ===
        # Get current gate distribution from brain monitor
        multi_target_decision = None
        if self.brain_monitor and self.brain_monitor.gate_history:
            gate_list = list(self.brain_monitor.gate_history)
            if gate_list:
                # Use most recent gates
                latest_gates = gate_list[-1]

                # Get per-modality PEs if available
                per_modality_pes = None
                if 'per_modality_pes' in memory_info:
                    pe_ranking = memory_info['per_modality_pes']['pe_ranking']
                    per_modality_pes = {mod: pe for mod, pe in pe_ranking}

                # Route to weighted intervention decisions
                decision = self.multi_target_router.route_decision(
                    gates=latest_gates,
                    confidence=confidence,
                    dominant_modalities=dominant_modalities,
                    per_modality_pes=per_modality_pes
                )

                multi_target_decision = decision.to_dict()

        prediction = PathPrediction(
            task_type=task_type,
            predicted_sequence=predicted_sequence,
            expected_duration=expected_duration,
            expected_errors=int(expected_errors),
            success_probability=success_probability,
            confidence=confidence,
            similar_sessions=len(similar_states),
            alternative_paths=alternative_paths,
            dominant_modalities=dominant_modalities,
            memory_retrieval={
                'hippocampal_memories': memory_info['thalamo_hippocampal_state']['hippocampal']['num_memories'],
                'traces_processed': memory_info['traces_processed']
            },
            multi_target_decision=multi_target_decision  # Phase 3!
        )

        self.predictions_made += 1

        return prediction

    def _infer_task_type(self, task_description: str) -> str:
        """
        Infer task type from natural language description

        Uses keyword matching for now. Could be upgraded to LLM.
        """
        desc_lower = task_description.lower()

        # Keyword mapping
        keywords = {
            'github': ['git', 'commit', 'push', 'pull', 'clone', 'branch', 'repo'],
            'docker': ['docker', 'container', 'image', 'build', 'run'],
            'playwright': ['browser', 'web', 'scrape', 'page', 'click'],
            'filesystem': ['file', 'dir', 'folder', 'read', 'write', 'delete'],
            'search': ['find', 'search', 'grep', 'query'],
            'memory': ['remember', 'recall', 'memory', 'past'],
            'context': ['context', 'understand', 'analyze']
        }

        for task_type, words in keywords.items():
            if any(word in desc_lower for word in words):
                return task_type

        return 'unknown'

    def _calculate_confidence(
        self,
        task_type: str,
        num_similar: int,
        success_prob: float
    ) -> float:
        """
        Calculate confidence in prediction

        Higher confidence with:
        - More similar past sessions
        - Higher success probability
        - More familiar task types
        """
        # Data factor: more similar sessions = higher confidence
        data_factor = min(num_similar / 10.0, 1.0)

        # Success factor
        success_factor = success_prob

        # Familiarity factor
        task_counts = {
            task: len(states)
            for task, states in self.graph.task_graphs.items()
        }
        total_observations = task_counts.get(task_type, 0)
        familiarity_factor = min(total_observations / 20.0, 1.0)

        # Weighted combination
        confidence = (
            data_factor * 0.4 +
            success_factor * 0.4 +
            familiarity_factor * 0.2
        )

        return confidence

    def _get_dominant_modalities(self, task_type: str) -> List[str]:
        """
        Identify which brain modalities are most active for this task type

        Analyzes gate history from brain monitor.
        """
        if not self.brain_monitor or not self.brain_monitor.gate_history:
            return []

        # Convert deque to list for slicing
        gate_list = list(self.brain_monitor.gate_history)
        if not gate_list:
            return []

        # Average gate distribution across recent history
        recent_gates = gate_list[-10:]
        avg_gates = np.mean(recent_gates, axis=0)

        modality_names = [
            'vision', 'audio', 'touch', 'taste', 'vestibular', 'threat',
            'tool_trace', 'temporal', 'error_sig', 'success_sig'
        ]

        # Get top 3 modalities
        top_indices = np.argsort(avg_gates)[-3:][::-1]
        dominant = [modality_names[i] for i in top_indices]

        return dominant

    def visualize_prediction(self, prediction: PathPrediction) -> str:
        """
        Create ASCII visualization of path prediction
        """
        lines = ["", "=" * 70, "PATH PREDICTION", "=" * 70, ""]

        lines.append(f"Task Type: {prediction.task_type}")
        lines.append(f"Confidence: {prediction.confidence:.1%}")
        lines.append("")

        lines.append("PREDICTED SEQUENCE:")
        for i, tool in enumerate(prediction.predicted_sequence, 1):
            lines.append(f"  {i}. {tool}")
        lines.append("")

        lines.append("EXPECTED OUTCOME:")
        lines.append(f"  Duration: ~{prediction.expected_duration:.1f} seconds")
        lines.append(f"  Errors: ~{prediction.expected_errors}")
        lines.append(f"  Success Probability: {prediction.success_probability:.1%}")
        lines.append("")

        lines.append("EVIDENCE:")
        lines.append(f"  Similar past sessions: {prediction.similar_sessions}")
        lines.append(f"  Hippocampal memories: {prediction.memory_retrieval['hippocampal_memories']}")
        lines.append(f"  Total traces processed: {prediction.memory_retrieval['traces_processed']}")
        lines.append("")

        if prediction.dominant_modalities:
            lines.append("DOMINANT BRAIN AREAS:")
            for modality in prediction.dominant_modalities:
                lines.append(f"  - {modality}")
            lines.append("")

        if prediction.alternative_paths:
            lines.append("ALTERNATIVE PATHS:")
            for i, path in enumerate(prediction.alternative_paths, 1):
                lines.append(f"  {i}. {' -> '.join(path)}")
            lines.append("")

        # Phase 3: Multi-target decision routing
        if prediction.multi_target_decision:
            lines.append("WEIGHTED INTERVENTION DECISIONS (Phase 3):")
            mtd = prediction.multi_target_decision

            primary = mtd['primary']
            lines.append(f"  PRIMARY ({primary['weight']:.1%}): {primary['type']}")
            lines.append(f"    Reasoning: {primary['reasoning']}")
            lines.append("")

            lines.append("  ALTERNATIVES:")
            for alt in mtd['alternatives']:
                lines.append(f"    {alt['type']:12s} {alt['weight']:.1%}")
            lines.append("")

        lines.append("=" * 70)

        return "\n".join(lines)

    def get_statistics(self) -> Dict:
        """Get path planner statistics"""
        stats = {
            'predictions_made': self.predictions_made,
            'predictions_correct': self.predictions_correct,
            'accuracy': self.predictions_correct / self.predictions_made if self.predictions_made > 0 else 0.0,
            'graph_stats': self.graph.get_statistics(),
            'strategy_stats': self.strategy_library.get_statistics()
        }

        # Add gate temperature info (Phase 1)
        if self.enable_adaptive_gating:
            stats['gate_temperature'] = {
                'current': self.gate_temp,
                'log_space': float(self.log_gate_temp),
                'bounds': [self.gate_temp_min, self.gate_temp_max],
                'learning_rate': self.gate_temp_lr,
                'history_length': len(self.gate_temp_history),
                'recent_accuracies': self.recent_accuracies[-5:] if self.recent_accuracies else []
            }

        return stats


if __name__ == "__main__":
    print("Testing Conversation Path Planner...")
    print("=" * 70)

    # Initialize components
    meta_router = MetaRouter(enable_hippocampus=True, seed=42)
    strategy_lib = StrategyLibrary(max_strategies_per_type=20)
    brain_monitor = BrainActivityMonitor(history_length=100)

    # Create path planner
    planner = ConversationPathPlanner(
        meta_router=meta_router,
        strategy_library=strategy_lib,
        brain_monitor=brain_monitor
    )

    # Train from session logs
    log_dir = os.environ.get(
        'SESSION_LOG_DIR',
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'logs', 'sessions')
    )
    planner.train_from_sessions(log_dir, limit=39)

    print("\n" + "=" * 70)
    print("TESTING PATH PREDICTIONS")
    print("=" * 70)

    # Test predictions
    test_tasks = [
        "I want to add all files and push to GitHub",
        "Deploy the application using Docker",
        "Search for function definitions in the codebase"
    ]

    for task in test_tasks:
        prediction = planner.predict_optimal_path(task)

        if prediction:
            print(planner.visualize_prediction(prediction))
        else:
            print(f"\nNo prediction available for: {task}\n")

    # Show statistics
    print("\n" + "=" * 70)
    print("PLANNER STATISTICS")
    print("=" * 70)
    stats = planner.get_statistics()
    print(json.dumps(stats, indent=2))

    print("\n" + "=" * 70)
    print("Path Planner working correctly!")
