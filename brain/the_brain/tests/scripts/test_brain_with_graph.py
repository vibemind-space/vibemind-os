"""
Test Neurosymbolic Brain with Complete State Graph

This demo tests the end-to-end integration:
1. Load complete Klotski state graph
2. Initialize neurosymbolic brain (10 modules + CTM)
3. Test brain solving puzzle using graph-based environment
4. Benchmark brain performance vs optimal

Requirements:
- Generated graph at learning_engine/klotski/Klotski-Webpage/data.json
- Neurosymbolic brain components
- Graph-based environment

Usage:
    python demos/test_brain_with_graph.py
"""

import sys
import os
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import time

# Add learning_engine to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'learning_engine', 'klotski'))

try:
    from neurosymbolic.core.puzzle_state import PuzzleState
    from neurosymbolic.environments.klotski_graph_env import KlotskiGraphEnv
    from neurosymbolic.core.neurosymbolic_brain import NeuroSymbolicBrain
    from neurosymbolic.core.routed_brain import RoutedBrain
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"[ERROR] Cannot import required modules: {e}")
    IMPORTS_AVAILABLE = False
    sys.exit(1)


class BrainGraphTester:
    """
    Tests brain integration with complete state graph
    """

    def __init__(self, graph_path: Path):
        self.graph_path = graph_path
        self.env = None
        self.brain = None
        self.graph_data = None

    def load_graph(self) -> bool:
        """Load and validate graph"""
        print("\n" + "="*70)
        print("LOADING STATE GRAPH")
        print("="*70)

        if not self.graph_path.exists():
            print(f"\n[ERROR] Graph file not found: {self.graph_path}")
            print("Please run: python demos/generate_klotski_graph.py")
            return False

        print(f"\n[INFO] Loading graph from: {self.graph_path}")

        with open(self.graph_path, 'r') as f:
            self.graph_data = json.load(f)

        # Validate structure
        if 'metadata' not in self.graph_data or 'states' not in self.graph_data:
            print("[ERROR] Invalid graph format")
            return False

        metadata = self.graph_data['metadata']
        print(f"[INFO] Graph metadata:")
        print(f"  Total states: {metadata['total_states']}")
        print(f"  Goal states: {metadata['goal_states']}")
        print(f"  Generated: {metadata['generated_at']}")
        print(f"  Generation time: {metadata['generation_time_seconds']:.1f}s")

        # Load environment
        try:
            self.env = KlotskiGraphEnv()
            print(f"\n[INFO] Environment loaded successfully")
            print(f"  Graph states: {len(self.env.graph.nodes) if hasattr(self.env, 'graph') else 'N/A'}")
        except Exception as e:
            print(f"\n[ERROR] Failed to load environment: {e}")
            return False

        return True

    def initialize_brain(self) -> bool:
        """Initialize neurosymbolic brain"""
        print("\n" + "="*70)
        print("INITIALIZING BRAIN")
        print("="*70)

        try:
            # Create routed brain (ATM-R + 10 modules + CTM)
            self.brain = RoutedBrain(
                state_dim=64,  # Puzzle state encoding dimension
                n_modules=10,  # 10 brain modules
                use_ctm=True,  # Enable Continuous Thought Machine
                ctm_max_steps=50  # Max reasoning steps
            )

            print(f"\n[INFO] Brain initialized successfully")
            print(f"  Modules: {self.brain.n_modules}")
            print(f"  CTM enabled: {self.brain.use_ctm}")
            print(f"  Total parameters: {sum(p.numel() for p in self.brain.parameters()):,}")

            return True

        except Exception as e:
            print(f"\n[ERROR] Failed to initialize brain: {e}")
            return False

    def test_solving(self, max_steps: int = 100) -> Dict:
        """
        Test brain solving puzzle from initial state

        Returns:
            Dict with results (success, steps, optimality, etc.)
        """
        print("\n" + "="*70)
        print("TESTING BRAIN SOLVING")
        print("="*70)

        # Reset environment
        state = self.env.reset()

        print(f"\n[INFO] Initial state:")
        print(f"  Distance to goal: {self.env.get_optimal_distance()}")
        print(f"  Is goal: {self.env.is_goal()}")

        # Solve using brain
        steps = 0
        start_time = time.time()
        success = False
        path = []

        while steps < max_steps:
            # Get brain action
            action = self.brain.select_action(state)

            # Take action
            next_state, reward, done, info = self.env.step(action)

            path.append({
                'step': steps,
                'action': action,
                'reward': reward,
                'distance': info.get('distance_to_goal', None)
            })

            state = next_state
            steps += 1

            # Progress update
            if steps % 10 == 0:
                print(f"  Step {steps}: distance={info.get('distance_to_goal', '?')}, reward={reward:.2f}")

            if done:
                success = True
                break

        elapsed = time.time() - start_time

        # Get optimal solution length
        optimal_length = self.env.get_optimal_distance_from_initial()

        # Results
        results = {
            'success': success,
            'steps': steps,
            'optimal_length': optimal_length,
            'optimality': steps / optimal_length if optimal_length > 0 else None,
            'time_seconds': elapsed,
            'path': path
        }

        # Print results
        print(f"\n" + "="*70)
        print("RESULTS")
        print("="*70)
        print(f"\nSuccess: {success}")
        print(f"Steps taken: {steps}")
        print(f"Optimal length: {optimal_length}")

        if results['optimality']:
            print(f"Optimality: {results['optimality']:.2%} (1.0 = optimal)")

        print(f"Time: {elapsed:.2f}s")
        print(f"Steps/sec: {steps/elapsed:.1f}")

        return results

    def benchmark_brain(self, num_trials: int = 10) -> Dict:
        """
        Benchmark brain on multiple random starting states

        Returns:
            Dict with aggregate statistics
        """
        print("\n" + "="*70)
        print(f"BENCHMARKING BRAIN ({num_trials} trials)")
        print("="*70)

        trials = []

        for i in range(num_trials):
            print(f"\n[TRIAL {i+1}/{num_trials}]")

            # Random starting state
            state = self.env.reset_random()

            # Solve
            result = self.test_solving(max_steps=100)
            trials.append(result)

        # Aggregate stats
        success_rate = sum(1 for t in trials if t['success']) / len(trials)
        avg_steps = sum(t['steps'] for t in trials) / len(trials)
        avg_optimality = sum(t['optimality'] for t in trials if t['optimality']) / sum(1 for t in trials if t['optimality'])

        benchmark = {
            'num_trials': num_trials,
            'success_rate': success_rate,
            'avg_steps': avg_steps,
            'avg_optimality': avg_optimality,
            'trials': trials
        }

        # Print benchmark
        print(f"\n" + "="*70)
        print("BENCHMARK SUMMARY")
        print("="*70)
        print(f"\nTrials: {num_trials}")
        print(f"Success rate: {success_rate:.1%}")
        print(f"Avg steps: {avg_steps:.1f}")
        print(f"Avg optimality: {avg_optimality:.1%}")

        return benchmark


def main():
    """Main entry point"""
    print("\n" + "="*70)
    print("BRAIN + GRAPH INTEGRATION TEST")
    print("="*70)

    # Find graph file
    graph_path = Path("learning_engine/klotski/Klotski-Webpage/data.json")

    # Create tester
    tester = BrainGraphTester(graph_path)

    # Step 1: Load graph
    if not tester.load_graph():
        return

    # Step 2: Initialize brain
    if not tester.initialize_brain():
        return

    # Step 3: Test solving from initial state
    print("\n" + "="*70)
    print("TEST 1: Solve from initial state")
    print("="*70)

    result = tester.test_solving(max_steps=100)

    if result['success']:
        print(f"\n✓ Brain solved puzzle in {result['steps']} steps")
        print(f"✓ Optimality: {result['optimality']:.1%}")
    else:
        print(f"\n✗ Brain did not solve puzzle in {result['steps']} steps")

    # Step 4: Benchmark (optional - takes longer)
    # Uncomment to run full benchmark:
    # benchmark = tester.benchmark_brain(num_trials=10)

    print("\n" + "="*70)
    print("COMPLETE")
    print("="*70)


if __name__ == "__main__":
    if not IMPORTS_AVAILABLE:
        print("[ERROR] Required modules not available")
        sys.exit(1)

    main()
