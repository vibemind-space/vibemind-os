"""
PRODUCTION-READY ADAPTIVE ROUTER

This is a production version of ATM-R with:
- Feedback loops for reinforcement learning
- Model persistence (save/load learned states)
- Evaluation metrics and logging
- Real adaptive learning over time
"""
import logging
import numpy as np
import json
import pickle
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List
import sys
sys.path.append('..')
from core.thalamo_pc_adaptive import ThalamoPC6Adaptive

logger = logging.getLogger(__name__)


class ProductionRouter:
    """
    Production-ready adaptive router with feedback learning.

    This router learns from experience:
    - Routes that lead to success are reinforced
    - Routes that lead to failure are weakened
    - Performance is tracked over time
    - Learned states can be saved and loaded
    """

    def __init__(self,
                 name: str = "router",
                 seed: int = 42,
                 learning_rate: float = 0.1,
                 log_dir: str = "logs"):
        """
        Initialize production router.

        Args:
            name: Router name (for logging/saving)
            seed: Random seed
            learning_rate: How fast to adapt based on feedback
            log_dir: Directory for logs and saved models
        """
        self.name = name
        self.learning_rate = learning_rate
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # Core ATM-R model
        self.atmr = ThalamoPC6Adaptive(seed=seed)

        # Tracking
        self.history = {
            'routes': [],           # Which route was chosen
            'successes': [],        # Was it successful?
            'rewards': [],          # Reward value
            'confidence': [],       # Route confidence
            'timestamp': []
        }

        # Performance metrics
        self.metrics = {
            'total_steps': 0,
            'total_successes': 0,
            'success_rate': 0.0,
            'route_success_counts': {m: 0 for m in self.atmr.modalities},
            'route_attempt_counts': {m: 0 for m in self.atmr.modalities},
            'route_success_rates': {m: 0.0 for m in self.atmr.modalities}
        }

        # Current episode tracking
        self.current_route = None
        self.current_confidence = 0.0

    def route(self, x: Dict[str, np.ndarray], adapt: bool = True) -> tuple:
        """
        Route input to best modality/method.

        Args:
            x: Multimodal input dictionary
            adapt: Whether to apply adaptive learning

        Returns:
            (chosen_modality, confidence, full_output)
        """
        # Run ATM-R routing
        out = self.atmr.step(x, adapt=adapt)

        # Get dominant route
        dominant_idx = np.argmax(out['g'])
        chosen_modality = self.atmr.modalities[dominant_idx]
        confidence = out['g'][dominant_idx]

        # Store for feedback later
        self.current_route = chosen_modality
        self.current_confidence = confidence

        # Track attempt
        self.metrics['total_steps'] += 1
        self.metrics['route_attempt_counts'][chosen_modality] += 1

        return chosen_modality, confidence, out

    def feedback(self, success: bool, reward: float = None):
        """
        Provide feedback on the last routing decision.

        This is where the REAL learning happens!

        Args:
            success: Was the route successful?
            reward: Optional reward value (defaults to +1/-1)
        """
        if self.current_route is None:
            raise ValueError("No route to provide feedback for. Call route() first!")

        # Default reward
        if reward is None:
            reward = 1.0 if success else -1.0

        # Update metrics
        if success:
            self.metrics['total_successes'] += 1
            self.metrics['route_success_counts'][self.current_route] += 1

        self.metrics['success_rate'] = (
            self.metrics['total_successes'] / self.metrics['total_steps']
            if self.metrics['total_steps'] > 0 else 0.0
        )

        # Update route success rates
        for modality in self.atmr.modalities:
            attempts = self.metrics['route_attempt_counts'][modality]
            if attempts > 0:
                self.metrics['route_success_rates'][modality] = (
                    self.metrics['route_success_counts'][modality] / attempts
                )

        # Store in history
        self.history['routes'].append(self.current_route)
        self.history['successes'].append(success)
        self.history['rewards'].append(reward)
        self.history['confidence'].append(self.current_confidence)
        self.history['timestamp'].append(datetime.now().isoformat())

        # ADAPTIVE LEARNING: Adjust priors based on feedback
        # This is the key difference from demos!
        self._update_priors(success, reward)

        # Reset current
        self.current_route = None
        self.current_confidence = 0.0

    def _update_priors(self, success: bool, reward: float):
        """
        Update ATM-R priors based on feedback.

        Successful routes -> strengthen (increase prior)
        Failed routes -> weaken (decrease prior)
        """
        # Calculate adjustment
        adjustment = self.learning_rate * reward

        # Update prior for this route
        self.atmr.priors[self.current_route] += adjustment

        # Keep priors in reasonable range
        self.atmr.priors[self.current_route] = np.clip(
            self.atmr.priors[self.current_route], 0.1, 10.0
        )

    def get_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        return self.metrics.copy()

    def get_history(self, last_n: Optional[int] = None) -> Dict[str, List]:
        """
        Get routing history.

        Args:
            last_n: Only return last N entries (None = all)
        """
        if last_n is None:
            return self.history.copy()

        return {
            key: values[-last_n:]
            for key, values in self.history.items()
        }

    def print_metrics(self):
        """Print current performance metrics."""
        print("=" * 70)
        print(f"ROUTER METRICS: {self.name}")
        print("=" * 70)
        print(f"Total Steps: {self.metrics['total_steps']}")
        print(f"Total Successes: {self.metrics['total_successes']}")
        print(f"Overall Success Rate: {self.metrics['success_rate']:.1%}")
        print()
        print("Route Performance:")
        print("-" * 70)
        print(f"{'Route':<15s} {'Attempts':<10s} {'Successes':<12s} {'Success Rate':<15s}")
        print("-" * 70)

        for modality in self.atmr.modalities:
            attempts = self.metrics['route_attempt_counts'][modality]
            successes = self.metrics['route_success_counts'][modality]
            rate = self.metrics['route_success_rates'][modality]

            if attempts > 0:
                print(f"{modality:<15s} {attempts:<10d} {successes:<12d} {rate:<15.1%}")

        print("=" * 70)

    def save(self, filename: Optional[str] = None):
        """
        Save learned router state.

        Args:
            filename: Save filename (defaults to router name + timestamp)
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.name}_{timestamp}.pkl"

        filepath = self.log_dir / filename

        # Get full ATMR state using get_adaptive_state()
        atmr_state = self.atmr.get_adaptive_state()

        state = {
            'name': self.name,
            'atmr_state': atmr_state,
            'metrics': self.metrics,
            'history': self.history,
            'learning_rate': self.learning_rate,
        }

        try:
            with open(filepath, 'wb') as f:
                pickle.dump(state, f)
            logger.info(f"Router saved to: {filepath}")
        except (IOError, OSError) as e:
            logger.error(f"Failed to save router state to {filepath}: {e}")
            raise
        return filepath

    def load(self, filepath: str):
        """
        Load previously saved router state.

        Args:
            filepath: Path to saved router file
        """
        try:
            with open(filepath, 'rb') as f:
                state = pickle.load(f)
        except (IOError, OSError) as e:
            logger.error(f"Failed to load router state from {filepath}: {e}")
            raise
        except (pickle.UnpicklingError, EOFError) as e:
            logger.error(f"Corrupted router checkpoint {filepath}: {e}")
            raise

        # Restore state
        self.name = state['name']
        self.learning_rate = state['learning_rate']
        self.metrics = state['metrics']
        self.history = state['history']

        # Restore ATM-R learned state (priors and other learned params)
        atmr_state = state['atmr_state']

        # Restore priors (main learned component)
        if 'priors' in atmr_state:
            self.atmr.priors = atmr_state['priors']

        # Restore other learned components if available
        if 'G' in atmr_state:
            self.atmr.G = atmr_state['G']
        if 'tau' in atmr_state:
            self.atmr.tau = atmr_state['tau']
        if 'gate_temp' in atmr_state:
            self.atmr.gate_temp = atmr_state['gate_temp']

        logger.info(f"Router loaded from: {filepath}")
        logger.info(f"Total steps: {self.metrics['total_steps']}, Success rate: {self.metrics['success_rate']:.1%}")

    def save_history_json(self, filename: Optional[str] = None):
        """
        Save history as JSON (for analysis/plotting).

        Args:
            filename: Save filename
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.name}_history_{timestamp}.json"

        filepath = self.log_dir / filename

        # Convert numpy types to native Python for JSON serialization
        history_serializable = {}
        for key, values in self.history.items():
            if key == 'successes':
                # Convert numpy bools to Python bools
                history_serializable[key] = [bool(v) for v in values]
            elif key == 'rewards' or key == 'confidence':
                # Convert numpy floats to Python floats
                history_serializable[key] = [float(v) for v in values]
            else:
                history_serializable[key] = values

        try:
            with open(filepath, 'w') as f:
                json.dump(history_serializable, f, indent=2)
            logger.info(f"History saved to: {filepath}")
        except (IOError, OSError) as e:
            logger.error(f"Failed to save history to {filepath}: {e}")
            raise
        return filepath


class MethodRegistry:
    """
    Registry for methods that can be routed to.

    This maps modalities to actual executable methods.
    """

    def __init__(self):
        self.methods = {}

    def register(self, modality: str, method: Callable, name: str = None):
        """
        Register a method for a modality.

        Args:
            modality: Modality name (e.g., 'vision', 'audio')
            method: Callable method
            name: Optional display name
        """
        self.methods[modality] = {
            'callable': method,
            'name': name or method.__name__
        }

    def execute(self, modality: str, *args, **kwargs):
        """
        Execute registered method for modality.

        Args:
            modality: Which modality to execute
            *args, **kwargs: Arguments to pass to method

        Returns:
            Result from method execution
        """
        if modality not in self.methods:
            raise ValueError(f"No method registered for modality: {modality}")

        method_info = self.methods[modality]
        return method_info['callable'](*args, **kwargs)

    def get_name(self, modality: str) -> str:
        """Get display name for modality's method."""
        if modality not in self.methods:
            return modality
        return self.methods[modality]['name']

    def list_methods(self):
        """List all registered methods."""
        print("Registered Methods:")
        print("-" * 50)
        for modality, info in self.methods.items():
            print(f"  {modality:<15s} -> {info['name']}")
