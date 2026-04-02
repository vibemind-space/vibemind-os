"""
Per-Modality Prediction Errors (Phase 2)

Concept from logical_brain/routed_brain.py:
Each brain area tracks how well it can predict its inputs, computing
per-modality prediction errors (PEs) using learned generative models.

Original PyTorch implementation:
```python
def compute_prediction_errors(self, inputs):
    prediction_errors = {}
    for m in self.modalities:
        x_j = inputs[m]
        v_j = self.predictions[m]
        x_pred = self.generative_models[m](v_j)
        pe = torch.norm(x_j - x_pred, dim=-1)
        prediction_errors[m] = pe
    return prediction_errors
```

Our NumPy adaptation:
- Tracks prediction vector for each modality
- Computes reconstruction error as PE
- Uses exponential moving average for online learning
- Separate learning rates per modality (fast for errors, slow for stable signals)
"""

import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ModalityPredictionState:
    """State for a single modality's prediction tracking"""
    name: str
    dimension: int
    prediction_vector: np.ndarray  # Current prediction
    learning_rate: float           # How fast to update predictions
    pe_history: List[float]        # Recent prediction errors
    total_updates: int             # Number of updates


class ModalityPredictionErrors:
    """
    Tracks per-modality prediction errors for all brain areas

    Each modality learns to predict its input using exponential moving average.
    High PE = surprising/novel input
    Low PE = expected/predictable input

    This enables the brain to understand which aspects it can predict well
    vs. which aspects are uncertain.
    """

    def __init__(
        self,
        modalities: Dict[str, int],  # modality_name -> dimension
        learning_rates: Optional[Dict[str, float]] = None,
        history_length: int = 100
    ):
        """
        Initialize per-modality prediction tracking

        Args:
            modalities: Dict mapping modality name to dimension
            learning_rates: Optional dict of learning rates per modality
            history_length: How many recent PEs to store per modality
        """
        self.modalities = modalities
        self.history_length = history_length

        # Default learning rates (faster for errors, slower for stable signals)
        if learning_rates is None:
            learning_rates = {
                'vision': 0.05,
                'audio': 0.05,
                'touch': 0.1,
                'taste': 0.1,
                'vestibular': 0.1,
                'threat': 0.15,         # Fast learning for safety
                'tool_trace': 0.1,      # Fast learning for task patterns
                'temporal_pattern': 0.05,
                'error_signal': 0.15,   # Very fast - errors are important!
                'success_signal': 0.08
            }

        self.learning_rates = learning_rates

        # Initialize prediction states
        self.states: Dict[str, ModalityPredictionState] = {}
        for modality, dim in modalities.items():
            self.states[modality] = ModalityPredictionState(
                name=modality,
                dimension=dim,
                prediction_vector=np.zeros(dim),
                learning_rate=learning_rates.get(modality, 0.1),
                pe_history=[],
                total_updates=0
            )

    def compute_prediction_errors(
        self,
        inputs: Dict[str, np.ndarray]
    ) -> Dict[str, float]:
        """
        Compute prediction error for each modality

        PE = ||x_i - prediction_i||  (L2 norm of reconstruction error)

        Args:
            inputs: Dict mapping modality -> input vector

        Returns:
            Dict mapping modality -> prediction error (scalar)
        """
        prediction_errors = {}

        for modality in self.modalities:
            if modality not in inputs:
                # No input for this modality - zero PE
                prediction_errors[modality] = 0.0
                continue

            x_i = inputs[modality]
            state = self.states[modality]

            # Compute reconstruction error
            error_vector = x_i - state.prediction_vector
            pe = np.linalg.norm(error_vector)

            # Normalize by input dimension (makes PEs comparable across modalities)
            pe_normalized = pe / np.sqrt(state.dimension)

            prediction_errors[modality] = float(pe_normalized)

        return prediction_errors

    def update_predictions(
        self,
        inputs: Dict[str, np.ndarray]
    ) -> Dict[str, float]:
        """
        Update predictions using exponential moving average and return PEs

        This combines compute_prediction_errors + learning in one step.

        Prediction update rule:
            prediction[t+1] = (1 - α) * prediction[t] + α * input[t]

        Where α = learning_rate

        Args:
            inputs: Dict mapping modality -> input vector

        Returns:
            Dict mapping modality -> prediction error before update
        """
        prediction_errors = {}

        for modality in self.modalities:
            if modality not in inputs:
                prediction_errors[modality] = 0.0
                continue

            x_i = inputs[modality]
            state = self.states[modality]

            # Compute PE before update
            error_vector = x_i - state.prediction_vector
            pe = np.linalg.norm(error_vector) / np.sqrt(state.dimension)
            prediction_errors[modality] = float(pe)

            # Update prediction with exponential moving average
            alpha = state.learning_rate
            state.prediction_vector = (1 - alpha) * state.prediction_vector + alpha * x_i

            # Record PE in history
            state.pe_history.append(pe)
            if len(state.pe_history) > self.history_length:
                state.pe_history.pop(0)

            state.total_updates += 1

        return prediction_errors

    def get_average_pe(self, modality: str, window: int = 10) -> float:
        """
        Get average prediction error over recent history

        Args:
            modality: Modality name
            window: Number of recent PEs to average

        Returns:
            Average PE over window (or 0 if no history)
        """
        if modality not in self.states:
            return 0.0

        state = self.states[modality]
        if not state.pe_history:
            return 0.0

        recent = state.pe_history[-window:]
        return float(np.mean(recent))

    def get_pe_statistics(self, modality: str) -> Dict:
        """
        Get detailed statistics for a modality's prediction errors

        Args:
            modality: Modality name

        Returns:
            Dict with mean, std, min, max, recent PEs
        """
        if modality not in self.states:
            return {}

        state = self.states[modality]

        if not state.pe_history:
            return {
                'modality': modality,
                'mean_pe': 0.0,
                'std_pe': 0.0,
                'min_pe': 0.0,
                'max_pe': 0.0,
                'recent_pe': 0.0,
                'total_updates': 0,
                'learning_rate': state.learning_rate
            }

        history = np.array(state.pe_history)

        return {
            'modality': modality,
            'mean_pe': float(np.mean(history)),
            'std_pe': float(np.std(history)),
            'min_pe': float(np.min(history)),
            'max_pe': float(np.max(history)),
            'recent_pe': float(state.pe_history[-1]) if state.pe_history else 0.0,
            'total_updates': state.total_updates,
            'learning_rate': state.learning_rate,
            'history_length': len(state.pe_history)
        }

    def get_all_statistics(self) -> Dict[str, Dict]:
        """
        Get statistics for all modalities

        Returns:
            Dict mapping modality -> statistics dict
        """
        return {
            modality: self.get_pe_statistics(modality)
            for modality in self.modalities
        }

    def identify_surprising_modalities(
        self,
        threshold: float = 0.5,
        window: int = 10
    ) -> List[str]:
        """
        Identify which modalities have high prediction errors (surprising)

        Args:
            threshold: PE threshold for "surprising"
            window: Number of recent PEs to consider

        Returns:
            List of modality names with high PEs
        """
        surprising = []

        for modality in self.modalities:
            avg_pe = self.get_average_pe(modality, window)
            if avg_pe > threshold:
                surprising.append(modality)

        return surprising

    def get_pe_ranking(self, window: int = 10) -> List[tuple]:
        """
        Rank modalities by prediction error (highest PE first)

        Args:
            window: Number of recent PEs to average

        Returns:
            List of (modality, avg_pe) tuples sorted by PE descending
        """
        rankings = []

        for modality in self.modalities:
            avg_pe = self.get_average_pe(modality, window)
            rankings.append((modality, avg_pe))

        # Sort by PE descending (most surprising first)
        rankings.sort(key=lambda x: x[1], reverse=True)

        return rankings

    def reset_modality(self, modality: str):
        """Reset prediction state for a single modality"""
        if modality in self.states:
            state = self.states[modality]
            state.prediction_vector = np.zeros(state.dimension)
            state.pe_history = []
            state.total_updates = 0

    def reset_all(self):
        """Reset all modality predictions"""
        for modality in self.modalities:
            self.reset_modality(modality)

    def get_state(self) -> Dict:
        """Get complete state for serialization"""
        return {
            'modalities': self.modalities,
            'learning_rates': self.learning_rates,
            'states': {
                name: {
                    'prediction_vector': state.prediction_vector.tolist(),
                    'pe_history': state.pe_history,
                    'total_updates': state.total_updates,
                    'learning_rate': state.learning_rate
                }
                for name, state in self.states.items()
            }
        }

    def __repr__(self):
        num_modalities = len(self.modalities)
        total_updates = sum(s.total_updates for s in self.states.values())
        return f"ModalityPredictionErrors(modalities={num_modalities}, updates={total_updates})"


if __name__ == "__main__":
    print("=" * 70)
    print("TESTING PER-MODALITY PREDICTION ERRORS (Phase 2)")
    print("=" * 70)
    print()

    # Define modalities
    modalities = {
        'vision': 128,
        'audio': 64,
        'tool_trace': 64,
        'error_signal': 16,
        'success_signal': 8
    }

    # Initialize tracker
    tracker = ModalityPredictionErrors(modalities)
    print(f"Initialized: {tracker}")
    print()

    # Simulate 20 timesteps with different patterns
    print("Simulating 20 timesteps...")
    print()

    for t in range(20):
        # Create inputs with different patterns
        inputs = {
            'vision': np.random.randn(128) * 0.1,           # Low variance (predictable)
            'audio': np.sin(t * 0.5) * np.ones(64),         # Periodic (predictable)
            'tool_trace': np.random.randn(64),              # High variance (unpredictable)
            'error_signal': np.random.randn(16) * 2.0,      # Very high variance (surprising!)
            'success_signal': np.ones(8) * 0.5              # Constant (very predictable)
        }

        # Update predictions and get PEs
        pes = tracker.update_predictions(inputs)

        if t % 5 == 0:
            print(f"Timestep {t}:")
            for modality, pe in sorted(pes.items(), key=lambda x: x[1], reverse=True):
                print(f"  {modality:20s} PE = {pe:.4f}")
            print()

    # Show final statistics
    print("=" * 70)
    print("FINAL STATISTICS")
    print("=" * 70)
    print()

    stats = tracker.get_all_statistics()
    for modality, stat in sorted(stats.items(), key=lambda x: x[1]['mean_pe'], reverse=True):
        print(f"{modality}:")
        print(f"  Mean PE:     {stat['mean_pe']:.4f}")
        print(f"  Std PE:      {stat['std_pe']:.4f}")
        print(f"  Recent PE:   {stat['recent_pe']:.4f}")
        print(f"  Updates:     {stat['total_updates']}")
        print()

    # Identify surprising modalities
    print("SURPRISING MODALITIES (PE > 0.5):")
    surprising = tracker.identify_surprising_modalities(threshold=0.5)
    for modality in surprising:
        avg_pe = tracker.get_average_pe(modality)
        print(f"  - {modality}: {avg_pe:.4f}")
    print()

    # Show PE ranking
    print("PE RANKING (Most surprising first):")
    rankings = tracker.get_pe_ranking()
    for i, (modality, pe) in enumerate(rankings, 1):
        print(f"  {i}. {modality:20s} {pe:.4f}")

    print()
    print("=" * 70)
    print("TEST COMPLETE!")
    print("=" * 70)
