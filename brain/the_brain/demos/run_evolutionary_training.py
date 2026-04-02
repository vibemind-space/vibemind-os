"""
Run Evolutionary Training - Production Entry Point

Complete romantic biological evolution system integrating:
1. Paper's bimodal perturbation method (89.4% improvement)
2. User's romantic 3-agent concept (love in the dark)
3. Multi-generational reproduction (puzzle multiplication)
4. Heart-Brain dual system (frozen pretrained + evolving)
5. MaxPerformanceTrainingSystem extension (500+200 base)

User Requirements:
- 200 epochs per generation
- 150 steps max per episode
- 10 generations max
- Real-world production task improvement

Expected Training Time:
- Generation 0 (baseline): ~12 minutes (500+200 episodes)
- Generation 1-10 (evolution): ~20 minutes each (200 episodes)
- Total: ~3-4 hours for complete evolution

Usage:
    python -m demos.run_evolutionary_training

    # Or with custom settings:
    python -m demos.run_evolutionary_training --generations 5 --episodes 100
"""

import sys
import os
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.multi_generational_trainer import MultiGenerationalTrainer


def main():
    """Main entry point for evolutionary training"""
    parser = argparse.ArgumentParser(
        description='Run Multi-Generational Evolutionary Training',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full training (200 episodes, 10 generations, ~3-4 hours)
  python -m demos.run_evolutionary_training

  # Quick test (50 episodes, 3 generations, ~30 minutes)
  python -m demos.run_evolutionary_training --generations 3 --episodes 50

  # Minimal test (10 episodes, 2 generations, ~5 minutes)
  python -m demos.run_evolutionary_training --generations 2 --episodes 10 --steps 50

Expected Results:
  - Generation 0: Baseline (77% accuracy, 54% confidence)
  - Generation 1-3: Learning (quality improving, conversation cost decreasing)
  - Generation 4-7: Mastery (60%+ quality, 60%+ success rate)
  - Generation 8-10: Optimization (85%+ quality, reproduction every time)

Extinction Scenarios:
  - If quality < 60% after 200 episodes -> Generation extinct
  - If success rate < 60% -> Evolution stops
  - System reverts to previous generation
        """
    )

    parser.add_argument(
        '--generations',
        type=int,
        default=10,
        help='Maximum generations (default: 10)'
    )
    parser.add_argument(
        '--episodes',
        type=int,
        default=200,
        help='Episodes per generation (default: 200)'
    )
    parser.add_argument(
        '--steps',
        type=int,
        default=150,
        help='Max steps per episode (default: 150)'
    )
    parser.add_argument(
        '--difficulty',
        type=float,
        default=1.5,
        help='Difficulty multiplier per generation (default: 1.5)'
    )
    parser.add_argument(
        '--save-dir',
        type=str,
        default='data/evolutionary_training',
        help='Save directory (default: data/evolutionary_training)'
    )
    parser.add_argument(
        '--no-terminal-monitor',
        action='store_true',
        help='Disable terminal monitoring (default: enabled)'
    )
    parser.add_argument(
        '--web-monitor',
        action='store_true',
        help='Enable web dashboard monitoring (default: disabled, requires server on port 5004)'
    )
    parser.add_argument(
        '--neurosymbolic-mode',
        action='store_true',
        help='Use real Klotski + NeuroSymbolicBrain (3.7M params, 10 modules) instead of simple heuristics'
    )
    parser.add_argument(
        '--graph-file',
        type=str,
        default=None,
        help='Path to Klotski graph file (e.g., "Klotski-Webpage/data.json")'
    )
    parser.add_argument(
        '--pretrained-heart',
        type=str,
        default=None,
        help='Path to pretrained heart weights (optional, will train with BFS if not provided)'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("MULTI-GENERATIONAL EVOLUTIONARY TRAINING")
    print("=" * 80)
    print("Romantic Biological Evolution System")
    print("-" * 80)
    print("Components:")
    print("  1. BimodalEvolutionaryOptimizer (paper's method)")
    print("  2. DarkModeCoordinator (3-agent love system)")
    print("  3. ReproductiveRewardSystem (sex = reproduction)")
    print("  4. HeartBrainDualSystem (frozen pretrained + evolving)")
    print("  5. MaxPerformanceTrainingSystem (500+200 baseline)")
    print("-" * 80)
    print("Settings:")
    print(f"  Max generations: {args.generations}")
    print(f"  Episodes per generation: {args.episodes}")
    print(f"  Max steps per episode: {args.steps}")
    print(f"  Difficulty multiplier: {args.difficulty}x")
    print(f"  Save directory: {args.save_dir}")
    print("-" * 80)
    print("User's Romantic Concept:")
    print("  'we all run in the dark' - 3 isolated puzzles")
    print("  'on match we have sex' - connection = reproduction")
    print("  'when we have sex we multiply the puzzle' - 1.5x harder")
    print("  'love is happening inbetween' - conversation penalty grows")
    print("  'the heart is the stronger guide' - frozen 70% + evolving 30%")
    print("-" * 80)

    # Estimate time
    baseline_time = 12  # Gen 0: 500+200 episodes
    gen_time = args.episodes * 0.1  # ~0.1 min per episode
    total_time = baseline_time + (args.generations * gen_time)

    print(f"Estimated time: ~{total_time:.0f} minutes ({total_time/60:.1f} hours)")
    print("=" * 80)

    # Confirm start
    if args.episodes >= 100:
        response = input("\nThis will take significant time. Continue? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Training cancelled.")
            return

    print("\nStarting training...")
    print("=" * 80)

    # Create trainer
    trainer = MultiGenerationalTrainer(
        max_generations=args.generations,
        episodes_per_generation=args.episodes,
        max_steps_per_episode=args.steps,
        difficulty_multiplier=args.difficulty,
        save_dir=args.save_dir,
        enable_terminal_monitor=not args.no_terminal_monitor,
        enable_web_monitor=args.web_monitor,
        neurosymbolic_mode=args.neurosymbolic_mode,
        graph_file=args.graph_file,
        pretrained_heart_path=args.pretrained_heart
    )

    # Run complete training
    results = trainer.train_complete_system()

    # Print summary
    print("\n" + "=" * 80)
    print("EVOLUTIONARY TRAINING COMPLETE")
    print("=" * 80)
    print(f"Overall success: {results['overall_success']}")
    print(f"Total time: {results['total_time']:.1f}s ({results['total_time']/60:.1f} minutes)")
    print(f"Generations completed: {results['total_generations']}")
    print(f"Extinct: {results['phase2_evolution'].get('extinct', False)}")
    print("-" * 80)

    # Phase results
    print("\n[PHASE 0] Baseline (Generation 0)")
    if 'phase0_baseline' in results:
        baseline = results['phase0_baseline']
        print(f"  Patterns: {baseline.get('phase2_real', {}).get('total_patterns', 'N/A')}")
        print(f"  Matrix changes: {baseline.get('phase3_transfer', {}).get('matrix_changes', 'N/A')}")

    print("\n[PHASE 1] Heart Frozen")
    print("  Heart weight: 70% (stronger guide)")
    print("  Brain weight: 30% (logical way)")

    print("\n[PHASE 2] Evolution")
    evolution = results['phase2_evolution']
    print(f"  Generations: {evolution['generations_completed']}")
    print(f"  Extinct: {evolution['extinct']}")

    if 'lineage' in evolution:
        lineage = evolution['lineage']
        print(f"  Reproductions: {lineage['total_reproductions']}")
        print(f"  Final difficulty: {lineage['current_difficulty']:.2f}x")

    print("\n[PHASE 3] Validation")
    validation = results['phase3_validation']
    print(f"  Predictions: {validation['predictions']}")

    print("\n" + "=" * 80)
    print(f"Results saved to: {args.save_dir}")
    print("=" * 80)

    # Show next steps
    print("\n[NEXT STEPS]")
    print("1. Analyze results: Check data/evolutionary_training/*.json")
    print("2. Compare generations: Look for reproduction events")
    print("3. Validate on production: Test evolved system on real tasks")
    print("4. A/B test: Compare baseline vs evolved system")
    print("=" * 80)


if __name__ == "__main__":
    main()
