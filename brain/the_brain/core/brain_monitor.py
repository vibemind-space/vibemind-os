"""
Real-Time Brain Activity Monitor

Visualizes which brain areas activate during conversation processing.
Tracks activation across all modules: thalamus, hippocampus, basal ganglia, hierarchical layers.
"""

import numpy as np
from typing import Dict, List, Optional
from collections import deque


class BrainActivityMonitor:
    """
    Monitors and tracks brain activity in real-time.

    Tracks:
    - Thalamic gate distributions
    - Hippocampal memory retrieval
    - Error signals
    - Success predictions
    - Module activation levels
    """

    def __init__(self, history_length: int = 100):
        """
        Initialize monitor.

        Args:
            history_length: Number of timesteps to keep in history
        """
        self.history_length = history_length

        # Activity history (FIFO queues)
        self.gate_history = deque(maxlen=history_length)
        self.error_history = deque(maxlen=history_length)
        self.memory_retrieval_history = deque(maxlen=history_length)
        self.prediction_history = deque(maxlen=history_length)

        # Module activation levels (0-1)
        self.current_activation = {
            'thalamus': 0.0,
            'hippocampus': 0.0,
            'error_detection': 0.0,
            'success_prediction': 0.0,
            'tool_trace': 0.0,
            'temporal': 0.0
        }

        # Alert flags
        self.alerts = []

    def update(self, routing_output: Dict):
        """
        Update monitor with new routing output.

        Args:
            routing_output: Output from meta_router.process_trace()
        """
        # Extract gate distribution
        gates = routing_output.get('final_gates', routing_output.get('gates', np.zeros(10)))
        self.gate_history.append(gates.copy())

        # Extract error signals
        trace_features = routing_output.get('trace_features', {})
        error_count = trace_features.get('error_count', 0)
        self.error_history.append(error_count)

        # Extract memory activity
        hc_out = routing_output.get('hippocampal_output', {})
        memory_encoded = hc_out.get('encoded', False)
        num_memories = hc_out.get('num_memories', 0)
        self.memory_retrieval_history.append({
            'encoded': memory_encoded,
            'num_memories': num_memories
        })

        # Extract prediction
        success = routing_output.get('success', True)
        self.prediction_history.append(success)

        # Compute module activation levels
        self._compute_activations(gates, error_count, memory_encoded, num_memories)

        # Check for alerts
        self._check_alerts(routing_output)

    def _compute_activations(
        self,
        gates: np.ndarray,
        error_count: int,
        memory_encoded: bool,
        num_memories: int
    ):
        """Compute activation levels for each module."""
        # Thalamus: average gate strength
        self.current_activation['thalamus'] = np.mean(gates) if len(gates) > 0 else 0.0

        # Hippocampus: memory activity
        self.current_activation['hippocampus'] = min(num_memories / 20.0, 1.0)

        # Error detection: normalized error count
        self.current_activation['error_detection'] = min(error_count / 10.0, 1.0)

        # Tool trace: gate strength for tool_trace modality
        if len(gates) > 6:
            self.current_activation['tool_trace'] = gates[6]  # tool_trace is 7th modality

        # Temporal: gate strength for temporal_pattern
        if len(gates) > 7:
            self.current_activation['temporal'] = gates[7]

    def _check_alerts(self, routing_output: Dict):
        """Check for alert conditions."""
        self.alerts = []

        trace_features = routing_output.get('trace_features', {})
        error_count = trace_features.get('error_count', 0)
        repetition = trace_features.get('max_tool_repetition', 0)
        qa_rejects = trace_features.get('qa_reject_count', 0)
        clarifications = trace_features.get('clarification_count', 0)

        # Alert: High errors
        if error_count > 5:
            self.alerts.append({
                'level': 'warning',
                'message': f'High error count: {error_count}',
                'recommendation': 'Check for recurring error patterns'
            })

        # Alert: Stuck in loop
        if repetition > 5:
            self.alerts.append({
                'level': 'critical',
                'message': f'Tool repetition: {repetition} (likely stuck!)',
                'recommendation': 'Terminate and try different approach'
            })

        # Alert: Quality issues
        if qa_rejects > 3:
            self.alerts.append({
                'level': 'warning',
                'message': f'QA rejected {qa_rejects} times',
                'recommendation': 'Output quality degrading, need intervention'
            })

        # Alert: User confusion
        if clarifications > 3:
            self.alerts.append({
                'level': 'info',
                'message': f'{clarifications} clarification requests',
                'recommendation': 'Task may be unclear or unresolvable'
            })

    def get_activation_summary(self) -> Dict:
        """Get current activation summary."""
        return {
            'current_activation': self.current_activation.copy(),
            'alerts': self.alerts.copy(),
            'gate_strength': np.mean(list(self.gate_history)) if self.gate_history else 0.0,
            'avg_error_rate': np.mean(list(self.error_history)) if self.error_history else 0.0,
            'total_memories': self.memory_retrieval_history[-1]['num_memories'] if self.memory_retrieval_history else 0
        }

    def visualize_ascii(self) -> str:
        """
        Create ASCII visualization of brain activity.

        Returns:
            String with ASCII art brain visualization
        """
        lines = []
        lines.append("="*80)
        lines.append("BRAIN ACTIVITY MONITOR")
        lines.append("="*80)
        lines.append("")

        # Module activations
        lines.append("MODULE ACTIVATION LEVELS:")
        lines.append("-"*80)
        for module, activation in self.current_activation.items():
            bar_length = int(activation * 40)
            bar = "#" * bar_length + "-" * (40 - bar_length)
            lines.append(f"{module:20s} [{bar}] {activation:.2f}")
        lines.append("")

        # Recent gate distribution
        if self.gate_history:
            gates = self.gate_history[-1]
            lines.append("CURRENT GATE DISTRIBUTION:")
            lines.append("-"*80)
            modality_names = [
                'vision', 'audio', 'touch', 'taste', 'vestibular', 'threat',
                'tool_trace', 'temporal', 'error_sig', 'success_sig'
            ]
            for i, (name, gate) in enumerate(zip(modality_names[:len(gates)], gates)):
                bar_length = int(gate * 40)
                bar = "=" * bar_length + " " * (40 - bar_length)
                lines.append(f"{name:15s} [{bar}] {gate:.3f}")
            lines.append("")

        # Alerts
        if self.alerts:
            lines.append("ALERTS:")
            lines.append("-"*80)
            for alert in self.alerts:
                level = alert['level'].upper()
                lines.append(f"[{level}] {alert['message']}")
                lines.append(f"  -> {alert['recommendation']}")
            lines.append("")

        # Statistics
        summary = self.get_activation_summary()
        lines.append("STATISTICS:")
        lines.append("-"*80)
        lines.append(f"Average Gate Strength: {summary['gate_strength']:.3f}")
        lines.append(f"Average Error Rate: {summary['avg_error_rate']:.1f}")
        lines.append(f"Episodic Memories: {summary['total_memories']}")
        lines.append("")

        lines.append("="*80)

        return "\n".join(lines)

    def get_dominant_modality(self) -> str:
        """Get currently dominant modality."""
        if not self.gate_history:
            return "none"

        gates = self.gate_history[-1]
        modality_names = [
            'vision', 'audio', 'touch', 'taste', 'vestibular', 'threat',
            'tool_trace', 'temporal', 'error_sig', 'success_sig'
        ]

        max_idx = np.argmax(gates)
        if max_idx < len(modality_names):
            return modality_names[max_idx]
        return "unknown"

    def reset(self):
        """Reset monitor."""
        self.gate_history.clear()
        self.error_history.clear()
        self.memory_retrieval_history.clear()
        self.prediction_history.clear()
        self.alerts = []
        for key in self.current_activation:
            self.current_activation[key] = 0.0
