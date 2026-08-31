"""
Module Specialization Tracker

Tracks brain module activations across different puzzle types
to measure whether modules specialize on puzzles that emphasize them.

Example: VIS (visual cortex) should activate more on "Visual Puzzle"
         DLPFC (planning) should activate more on "Planning Puzzle"
"""

import numpy as np
from typing import Dict, List
from collections import defaultdict
import json


class SpecializationTracker:
    """
    Tracks module activations per puzzle type

    Usage:
        tracker = SpecializationTracker()

        # During training:
        for episode in training:
            puzzle_name = env.get_puzzle_name()
            activations = brain.get_module_activations(state)  # Dict[module_name] -> float
            tracker.record(puzzle_name, activations)

        # After training:
        metrics = tracker.compute_specialization()
        tracker.print_report()
    """

    def __init__(self):
        # Dict[puzzle_name][module_name] -> List[activation_values]
        self.activations = defaultdict(lambda: defaultdict(list))

        # Puzzle emphasis (what modules each puzzle is designed to emphasize)
        self.puzzle_emphasis = {
            'Standard Klotski': ['balanced'],
            'Visual Puzzle': ['VIS', 'SOM', 'AUD', 'LAN'],
            'Planning Puzzle': ['DLPFC', 'OFC', 'ACC'],
            'Memory Puzzle': ['MTL', 'INS', 'ACC'],
            'Integration Puzzle': ['DMN', 'all']
        }

        self.module_names = ['VIS', 'AUD', 'SOM', 'LAN', 'DLPFC', 'OFC', 'ACC', 'INS', 'MTL', 'DMN']

    def record(self, puzzle_name: str, module_activations: Dict[str, float]):
        """
        Record module activations for a puzzle

        Args:
            puzzle_name: Name of the puzzle
            module_activations: Dict mapping module name -> activation value
        """
        for module, activation in module_activations.items():
            self.activations[puzzle_name][module].append(activation)

    def compute_specialization(self) -> Dict:
        """
        Compute module specialization metrics

        Returns:
            Dict with specialization scores for each module
        """
        specialization = {}

        for module in self.module_names:
            # Find puzzles that emphasize this module
            emphasis_puzzles = [
                puz for puz, emph in self.puzzle_emphasis.items()
                if module in emph or 'all' in emph
            ]

            # Find puzzles that don't emphasize this module
            other_puzzles = [
                puz for puz in self.puzzle_emphasis.keys()
                if puz not in emphasis_puzzles and 'balanced' not in self.puzzle_emphasis[puz]
            ]

            # Compute average activations
            activations_on_emphasis = []
            activations_on_other = []

            for puzzle in emphasis_puzzles:
                if puzzle in self.activations:
                    acts = self.activations[puzzle].get(module, [])
                    if len(acts) > 0:
                        activations_on_emphasis.extend(acts)

            for puzzle in other_puzzles:
                if puzzle in self.activations:
                    acts = self.activations[puzzle].get(module, [])
                    if len(acts) > 0:
                        activations_on_other.extend(acts)

            # Compute specialization score
            if len(activations_on_emphasis) > 0 and len(activations_on_other) > 0:
                emphasis_avg = np.mean(activations_on_emphasis)
                other_avg = np.mean(activations_on_other)
                specialization_score = emphasis_avg - other_avg
                specialization_ratio = emphasis_avg / (other_avg + 1e-8)
            else:
                emphasis_avg = np.mean(activations_on_emphasis) if activations_on_emphasis else 0.0
                other_avg = np.mean(activations_on_other) if activations_on_other else 0.0
                specialization_score = 0.0
                specialization_ratio = 1.0

            specialization[module] = {
                'specialization_score': float(specialization_score),
                'specialization_ratio': float(specialization_ratio),
                'avg_activation_on_emphasis': float(emphasis_avg),
                'avg_activation_on_other': float(other_avg),
                'num_emphasis_samples': len(activations_on_emphasis),
                'num_other_samples': len(activations_on_other),
                'emphasis_puzzles': emphasis_puzzles,
            }

        return specialization

    def get_puzzle_statistics(self) -> Dict:
        """
        Get activation statistics per puzzle

        Returns:
            Dict[puzzle_name][module_name] -> {mean, std, count}
        """
        stats = {}

        for puzzle_name in self.activations.keys():
            stats[puzzle_name] = {}
            for module_name in self.module_names:
                acts = self.activations[puzzle_name].get(module_name, [])
                if len(acts) > 0:
                    stats[puzzle_name][module_name] = {
                        'mean': float(np.mean(acts)),
                        'std': float(np.std(acts)),
                        'min': float(np.min(acts)),
                        'max': float(np.max(acts)),
                        'count': len(acts)
                    }
                else:
                    stats[puzzle_name][module_name] = {
                        'mean': 0.0,
                        'std': 0.0,
                        'min': 0.0,
                        'max': 0.0,
                        'count': 0
                    }

        return stats

    def print_report(self):
        """Print specialization report"""
        specialization = self.compute_specialization()

        print("\n" + "="*80)
        print("MODULE SPECIALIZATION REPORT")
        print("="*80)

        print("\nSpecialization Scores (Higher = More Specialized):")
        print("-" * 80)
        print(f"{'Module':<10} {'Score':>8} {'Ratio':>8} {'Emphasis':>10} {'Other':>10} {'Puzzles':<30}")
        print("-" * 80)

        # Sort by specialization score
        sorted_modules = sorted(
            specialization.items(),
            key=lambda x: x[1]['specialization_score'],
            reverse=True
        )

        for module, metrics in sorted_modules:
            score = metrics['specialization_score']
            ratio = metrics['specialization_ratio']
            emph_avg = metrics['avg_activation_on_emphasis']
            other_avg = metrics['avg_activation_on_other']
            puzzles_str = ', '.join(metrics['emphasis_puzzles'][:2])  # First 2 puzzles

            print(f"{module:<10} {score:>8.3f} {ratio:>8.2f}x {emph_avg:>10.3f} {other_avg:>10.3f} {puzzles_str:<30}")

        print("="*80)

        # Summary
        avg_score = np.mean([m['specialization_score'] for m in specialization.values()])
        specialized_count = sum(1 for m in specialization.values() if m['specialization_score'] > 0.1)

        print(f"\nSummary:")
        print(f"  Average specialization score: {avg_score:.3f}")
        print(f"  Modules with strong specialization (>0.1): {specialized_count}/{len(specialization)}")
        print()

    def save_to_file(self, filepath: str):
        """Save specialization metrics to JSON file"""
        data = {
            'specialization': self.compute_specialization(),
            'puzzle_statistics': self.get_puzzle_statistics()
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"Specialization metrics saved to: {filepath}")


# Test code
if __name__ == "__main__":
    print("Testing SpecializationTracker...\n")

    tracker = SpecializationTracker()

    # Simulate some activations
    # VIS should be high on Visual Puzzle
    # DLPFC should be high on Planning Puzzle
    # etc.

    for _ in range(100):
        # Visual Puzzle - high VIS activation
        tracker.record('Visual Puzzle', {
            'VIS': np.random.uniform(0.8, 1.0),
            'AUD': np.random.uniform(0.3, 0.5),
            'SOM': np.random.uniform(0.7, 0.9),
            'LAN': np.random.uniform(0.6, 0.8),
            'DLPFC': np.random.uniform(0.2, 0.4),
            'OFC': np.random.uniform(0.2, 0.4),
            'ACC': np.random.uniform(0.3, 0.5),
            'INS': np.random.uniform(0.2, 0.4),
            'MTL': np.random.uniform(0.3, 0.5),
            'DMN': np.random.uniform(0.4, 0.6),
        })

        # Planning Puzzle - high DLPFC activation
        tracker.record('Planning Puzzle', {
            'VIS': np.random.uniform(0.2, 0.4),
            'AUD': np.random.uniform(0.2, 0.4),
            'SOM': np.random.uniform(0.3, 0.5),
            'LAN': np.random.uniform(0.3, 0.5),
            'DLPFC': np.random.uniform(0.8, 1.0),
            'OFC': np.random.uniform(0.7, 0.9),
            'ACC': np.random.uniform(0.6, 0.8),
            'INS': np.random.uniform(0.3, 0.5),
            'MTL': np.random.uniform(0.3, 0.5),
            'DMN': np.random.uniform(0.4, 0.6),
        })

        # Memory Puzzle - high MTL activation
        tracker.record('Memory Puzzle', {
            'VIS': np.random.uniform(0.2, 0.4),
            'AUD': np.random.uniform(0.2, 0.4),
            'SOM': np.random.uniform(0.3, 0.5),
            'LAN': np.random.uniform(0.3, 0.5),
            'DLPFC': np.random.uniform(0.3, 0.5),
            'OFC': np.random.uniform(0.3, 0.5),
            'ACC': np.random.uniform(0.6, 0.8),
            'INS': np.random.uniform(0.6, 0.8),
            'MTL': np.random.uniform(0.8, 1.0),
            'DMN': np.random.uniform(0.4, 0.6),
        })

    # Print report
    tracker.print_report()

    # Save to file
    tracker.save_to_file('specialization_test.json')

    print("\n✓ SpecializationTracker test passed!")
