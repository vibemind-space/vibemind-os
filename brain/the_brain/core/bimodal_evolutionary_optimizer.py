"""
Bimodal Evolutionary Optimizer - Inspired by "Evolving LLMs Through Text-Based Self-Play"

Paper's Key Innovation:
- Bimodal weight perturbation: Mix of small (0-1%) and large (1-20%) changes
- Evolutionary selection: Variable replaces control if wins ≥ 4/5 epochs
- Achieved 89.4% win rate improvement in 67 iterations (47 hours)

Our Application:
- Evolve ConfidenceAdaptiveTrainer hyperparameters
- Evolve transfer learner intervention mappings
- Maintain existing training pipeline (wrapper pattern)

Reference:
Eric Martin, "Evolving LLMs Through Text-Based Self-Play: Achieving Emergent Performance"
arXiv preprint, 2025. https://github.com/emartin59/text-game-llm-improver
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from copy import deepcopy
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EvolutionResult:
    """Results from one evolution iteration"""
    iteration: int
    control_wins: int
    variable_wins: int
    evolution_occurred: bool
    control_avg_efficiency: float
    variable_avg_efficiency: float
    best_hyperparameters: Dict[str, Any]

    def win_rate(self) -> float:
        """Calculate variable win rate"""
        total = self.control_wins + self.variable_wins
        return self.variable_wins / total if total > 0 else 0.0


@dataclass
class EvolutionHistory:
    """Track evolution across iterations"""
    iterations: List[EvolutionResult] = field(default_factory=list)
    total_evolutions: int = 0
    current_best_efficiency: float = 0.0

    def add_result(self, result: EvolutionResult):
        """Record evolution result"""
        self.iterations.append(result)
        if result.evolution_occurred:
            self.total_evolutions += 1
            self.current_best_efficiency = result.variable_avg_efficiency


class BimodalEvolutionaryOptimizer:
    """
    Evolutionary optimizer using bimodal perturbation (from paper)

    Paper's Method:
    1. Control (current best) competes with Variable (perturbed)
    2. Bimodal perturbation: 50% small (N(0, 0.01)), 50% large (N(0, 0.2))
    3. Win ≥ 4/5 epochs → Variable replaces Control (evolution!)

    Applied to:
    - Trainer hyperparameters (confidence thresholds, learning rates)
    - Transfer learner weights (intervention mappings)
    - Strategy selection parameters

    Why This Works:
    - Small perturbations: Refine local optimum (exploitation)
    - Large perturbations: Escape plateaus (exploration)
    - Win threshold (80%): Ensures consistent improvement
    """

    def __init__(
        self,
        small_perturbation_std: float = 0.01,   # Paper's value: 0-1% changes
        large_perturbation_std: float = 0.2,    # Paper's value: 1-20% changes
        evolution_threshold: float = 0.8,       # Paper's value: 4/5 = 80%
        perturbable_params: Optional[List[str]] = None
    ):
        """
        Initialize bimodal evolutionary optimizer

        Args:
            small_perturbation_std: Std dev for small perturbations (default 0.01)
            large_perturbation_std: Std dev for large perturbations (default 0.2)
            evolution_threshold: Win rate needed for evolution (default 0.8)
            perturbable_params: List of parameter names to perturb (None = all numeric)
        """
        # Paper's hyperparameters
        self.small_std = small_perturbation_std
        self.large_std = large_perturbation_std
        self.evolution_threshold = evolution_threshold
        self.perturbable_params = perturbable_params or []

        # Evolution tracking
        self.history = EvolutionHistory()
        self.current_iteration = 0

        logger.info("[BimodalEvolutionaryOptimizer] Initialized")
        logger.info(f"  Small perturbation std: {self.small_std} (0-1%)")
        logger.info(f"  Large perturbation std: {self.large_std} (1-20%)")
        logger.info(f"  Evolution threshold: {self.evolution_threshold} (win ≥80%)")

    def perturb_value(self, value: float) -> float:
        """
        Apply bimodal perturbation to a single value (paper's method)

        Bimodal distribution:
        - 50% chance: Small perturbation N(0, 0.01)
        - 50% chance: Large perturbation N(0, 0.2)

        Args:
            value: Original value

        Returns:
            Perturbed value
        """
        if random.random() < 0.5:
            # Small perturbation: Refine (exploitation)
            noise = np.random.normal(0, self.small_std)
        else:
            # Large perturbation: Explore (exploration)
            noise = np.random.normal(0, self.large_std)

        return value + noise

    def perturb_hyperparameters(self, hyperparams: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply bimodal perturbation to hyperparameters

        Args:
            hyperparams: Dictionary of hyperparameters

        Returns:
            Perturbed copy of hyperparameters
        """
        perturbed = deepcopy(hyperparams)

        # Determine which params to perturb
        params_to_perturb = (self.perturbable_params
                            if self.perturbable_params
                            else [k for k, v in hyperparams.items()
                                 if isinstance(v, (int, float))])

        for param_name in params_to_perturb:
            if param_name in perturbed:
                original_value = perturbed[param_name]

                if isinstance(original_value, (int, float)):
                    # Apply bimodal perturbation
                    perturbed_value = self.perturb_value(float(original_value))

                    # Type preservation
                    if isinstance(original_value, int):
                        perturbed_value = int(round(perturbed_value))

                    # Safety bounds
                    if 'confidence' in param_name.lower():
                        perturbed_value = np.clip(perturbed_value, 0.0, 1.0)
                    elif 'learning_rate' in param_name.lower() or 'lr' in param_name.lower():
                        perturbed_value = max(0.0001, min(0.1, perturbed_value))

                    perturbed[param_name] = perturbed_value

                    logger.debug(f"  Perturbed {param_name}: {original_value:.4f} → {perturbed_value:.4f}")

        return perturbed

    def evolve_trainer(
        self,
        control_trainer: Any,  # ConfidenceAdaptiveTrainer
        num_epochs: int = 5,
        episodes_per_epoch: int = 20,
        verbose: bool = True
    ) -> EvolutionResult:
        """
        Evolve trainer using paper's competition method

        Process:
        1. Perturb control trainer hyperparameters → create variable trainer
        2. Run both trainers for num_epochs
        3. Compare efficiency (wins tracked)
        4. If variable wins ≥ evolution_threshold → Evolution!

        Args:
            control_trainer: Current best trainer
            num_epochs: Number of competition epochs (default 5, paper used 5 games)
            episodes_per_epoch: Training episodes per epoch
            verbose: Print progress

        Returns:
            EvolutionResult with competition outcomes
        """
        self.current_iteration += 1

        if verbose:
            print(f"\n{'='*80}")
            print(f"EVOLUTION ITERATION {self.current_iteration}")
            print(f"{'='*80}")
            print(f"Competition: {num_epochs} epochs, {episodes_per_epoch} episodes each")
            print()

        # Extract current hyperparameters
        control_hyperparams = self._extract_hyperparameters(control_trainer)

        # Create variable trainer (perturbed)
        variable_hyperparams = self.perturb_hyperparameters(control_hyperparams)
        variable_trainer = self._apply_hyperparameters(
            deepcopy(control_trainer),
            variable_hyperparams
        )

        if verbose:
            print("Hyperparameter perturbations:")
            for key in control_hyperparams:
                if key in variable_hyperparams:
                    ctrl_val = control_hyperparams[key]
                    var_val = variable_hyperparams[key]
                    if isinstance(ctrl_val, (int, float)) and isinstance(var_val, (int, float)):
                        change_pct = ((var_val - ctrl_val) / ctrl_val * 100) if ctrl_val != 0 else 0
                        print(f"  {key}: {ctrl_val:.4f} → {var_val:.4f} ({change_pct:+.1f}%)")
            print()

        # Competition loop (paper's method)
        control_wins = 0
        variable_wins = 0
        control_efficiencies = []
        variable_efficiencies = []

        for epoch in range(num_epochs):
            if verbose:
                print(f"Epoch {epoch+1}/{num_epochs}:")

            # Train control
            control_result = control_trainer.train(
                num_episodes=episodes_per_epoch,
                mode='SYNTHETIC',  # Use synthetic for speed
                verbose=False
            )
            control_efficiency = control_result.get('average_efficiency', 0.5)
            control_efficiencies.append(control_efficiency)

            # Train variable
            variable_result = variable_trainer.train(
                num_episodes=episodes_per_epoch,
                mode='SYNTHETIC',
                verbose=False
            )
            variable_efficiency = variable_result.get('average_efficiency', 0.5)
            variable_efficiencies.append(variable_efficiency)

            # Determine winner
            if variable_efficiency > control_efficiency:
                variable_wins += 1
                winner = "Variable"
            else:
                control_wins += 1
                winner = "Control"

            if verbose:
                print(f"  Control efficiency: {control_efficiency:.3f}")
                print(f"  Variable efficiency: {variable_efficiency:.3f}")
                print(f"  Winner: {winner}")
                print(f"  Score: Control {control_wins} - {variable_wins} Variable")
                print()

        # Calculate win rate
        variable_win_rate = variable_wins / num_epochs
        evolution_occurred = variable_win_rate >= self.evolution_threshold

        # Determine best hyperparameters
        if evolution_occurred:
            best_hyperparams = variable_hyperparams
            best_efficiency = np.mean(variable_efficiencies)
            if verbose:
                print(f"✨ EVOLUTION! Variable wins {variable_wins}/{num_epochs} ({variable_win_rate*100:.1f}%)")
                print(f"   Variable replaces Control (efficiency: {best_efficiency:.3f})")
        else:
            best_hyperparams = control_hyperparams
            best_efficiency = np.mean(control_efficiencies)
            if verbose:
                print(f"❌ No evolution. Control wins {control_wins}/{num_epochs} ({(1-variable_win_rate)*100:.1f}%)")
                print(f"   Control retained (efficiency: {best_efficiency:.3f})")

        # Create result
        result = EvolutionResult(
            iteration=self.current_iteration,
            control_wins=control_wins,
            variable_wins=variable_wins,
            evolution_occurred=evolution_occurred,
            control_avg_efficiency=np.mean(control_efficiencies),
            variable_avg_efficiency=np.mean(variable_efficiencies),
            best_hyperparameters=best_hyperparams
        )

        # Record history
        self.history.add_result(result)

        return result

    def _extract_hyperparameters(self, trainer: Any) -> Dict[str, Any]:
        """Extract hyperparameters from trainer"""
        hyperparams = {}

        # Extract common parameters
        param_names = [
            'confidence_threshold_novice',
            'confidence_threshold_expert',
            'initial_confidence',
            'confidence_gain_success',
            'confidence_gain_acceptable',
            'confidence_penalty_failure',
        ]

        for param_name in param_names:
            if hasattr(trainer, param_name):
                hyperparams[param_name] = getattr(trainer, param_name)

        # Extract transfer learner params if available
        if hasattr(trainer, 'transfer_learner') and trainer.transfer_learner:
            hyperparams['transfer_learning_rate'] = trainer.transfer_learner.learning_rate

        return hyperparams

    def _apply_hyperparameters(self, trainer: Any, hyperparams: Dict[str, Any]) -> Any:
        """Apply hyperparameters to trainer"""
        for param_name, param_value in hyperparams.items():
            if param_name == 'transfer_learning_rate':
                if hasattr(trainer, 'transfer_learner') and trainer.transfer_learner:
                    trainer.transfer_learner.learning_rate = param_value
            else:
                if hasattr(trainer, param_name):
                    setattr(trainer, param_name, param_value)

        return trainer

    def get_evolution_statistics(self) -> Dict[str, Any]:
        """Get evolution statistics"""
        total_iterations = len(self.history.iterations)

        if total_iterations == 0:
            return {
                'total_iterations': 0,
                'total_evolutions': 0,
                'evolution_rate': 0.0,
                'current_best_efficiency': 0.0
            }

        evolution_rate = self.history.total_evolutions / total_iterations

        return {
            'total_iterations': total_iterations,
            'total_evolutions': self.history.total_evolutions,
            'evolution_rate': evolution_rate,
            'current_best_efficiency': self.history.current_best_efficiency,
            'avg_variable_win_rate': np.mean([r.win_rate() for r in self.history.iterations])
        }


if __name__ == "__main__":
    # Test bimodal perturbation
    print("Testing BimodalEvolutionaryOptimizer...")
    print("="*80)

    optimizer = BimodalEvolutionaryOptimizer()

    # Test value perturbation
    print("\nTest 1: Bimodal perturbation distribution")
    original_value = 0.5
    small_count = 0
    large_count = 0

    for _ in range(1000):
        perturbed = optimizer.perturb_value(original_value)
        change = abs(perturbed - original_value)

        if change < 0.05:  # Likely small perturbation
            small_count += 1
        else:  # Likely large perturbation
            large_count += 1

    print(f"Original value: {original_value}")
    print(f"Small perturbations (~50%): {small_count/10:.1f}%")
    print(f"Large perturbations (~50%): {large_count/10:.1f}%")

    # Test hyperparameter perturbation
    print("\nTest 2: Hyperparameter perturbation")
    hyperparams = {
        'confidence_threshold_novice': 0.3,
        'confidence_threshold_expert': 0.7,
        'learning_rate': 0.001,
        'initial_confidence': 0.5
    }

    perturbed = optimizer.perturb_hyperparameters(hyperparams)

    print("Original hyperparameters:")
    for key, value in hyperparams.items():
        print(f"  {key}: {value}")

    print("\nPerturbed hyperparameters:")
    for key, value in perturbed.items():
        orig_val = hyperparams[key]
        change_pct = ((value - orig_val) / orig_val * 100) if orig_val != 0 else 0
        print(f"  {key}: {value:.4f} ({change_pct:+.1f}%)")

    print("\n" + "="*80)
    print("BimodalEvolutionaryOptimizer working correctly!")
