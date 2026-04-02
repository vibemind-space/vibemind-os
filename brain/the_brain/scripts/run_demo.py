"""
Interactive demo for ATM-R.

Runs a live simulation with synthetic data and displays gate dynamics.
Optional: parameter controls via command-line arguments.

Usage:
    python run_demo.py --steps 200 --adaptive --log-dir data/demo
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import argparse
from thalamo_pc_live import ThalamoPC6
from thalamo_pc_adaptive import ThalamoPC6Adaptive
from config_loader import load_config, create_model_from_config
from logger_viz import ATMRLogger, ATMRVisualizer, ATMRMetrics


def generate_synthetic_input(t, modalities, dims, scenario='multimodal'):
    """
    Generate synthetic multimodal input.

    Args:
        t: time step
        modalities: list of modality names
        dims: dict of dimensions
        scenario: 'multimodal', 'conflict', 'threat'

    Returns:
        dict of input vectors
    """
    x_t = {}

    if scenario == 'multimodal':
        # All modalities active (except threat)
        for m in modalities:
            if m == 'vision':
                x_t[m] = np.sin(0.05 * t + np.linspace(0, 2*np.pi, dims[m])) + 0.2 * np.random.randn(dims[m])
            elif m == 'audio':
                x_t[m] = np.cos(0.08 * t + np.linspace(0, np.pi, dims[m])) + 0.1 * np.random.randn(dims[m])
            elif m == 'touch':
                touch = np.random.randn(dims[m]) * 0.1
                if t % 10 == 0:
                    touch[np.random.randint(dims[m])] = 2.0
                x_t[m] = touch
            elif m == 'vestibular':
                x_t[m] = np.array([np.sin(0.1 * t + i * 0.5) for i in range(dims[m])]) + 0.1 * np.random.randn(dims[m])
            else:
                x_t[m] = np.zeros(dims[m])

    elif scenario == 'conflict':
        # Vision and audio competing
        for m in modalities:
            if m == 'vision' or m == 'audio':
                x_t[m] = np.ones(dims[m]) + 0.3 * np.random.randn(dims[m])
            else:
                x_t[m] = np.zeros(dims[m])

    elif scenario == 'threat':
        # Threat burst at t >= 50
        for m in modalities:
            if m == 'vision':
                x_t[m] = np.ones(dims[m]) + 0.2 * np.random.randn(dims[m])
            elif m == 'threat' and t >= 50 and t < 70:
                x_t[m] = 3.0 * np.ones(dims[m]) + 0.5 * np.random.randn(dims[m])
            else:
                x_t[m] = np.zeros(dims[m])

    return x_t


def main():
    parser = argparse.ArgumentParser(description='Run ATM-R interactive demo')
    parser.add_argument('--config', type=str, default='configs/default.yaml', help='Path to config file')
    parser.add_argument('--adaptive', action='store_true', help='Use adaptive model')
    parser.add_argument('--steps', type=int, default=200, help='Number of simulation steps')
    parser.add_argument('--scenario', type=str, default='multimodal',
                        choices=['multimodal', 'conflict', 'threat'],
                        help='Input scenario')
    parser.add_argument('--log-dir', type=str, default='data/demo', help='Log directory')
    parser.add_argument('--seed', type=int, default=42, help='Random seed')
    parser.add_argument('--plot', action='store_true', help='Generate plots')

    args = parser.parse_args()

    print("=" * 60)
    print("ATM-R Interactive Demo")
    print("=" * 60)

    # Load config
    config = load_config(args.config)
    config['simulation']['seed'] = args.seed

    # Create model
    print(f"\nInitializing {'Adaptive' if args.adaptive else 'Standard'} ATM-R...")
    model = create_model_from_config(config, adaptive=args.adaptive)
    print(f"  Modalities: {model.modalities}")
    print(f"  Dimensions: {model.d}")

    # Logger
    logger = ATMRLogger(log_dir=args.log_dir, save_interval=10)

    # Simulation
    print(f"\nRunning {args.steps} steps with scenario '{args.scenario}'...")
    np.random.seed(args.seed)

    for t in range(args.steps):
        # Generate input
        x_t = generate_synthetic_input(t, model.modalities, model.d, scenario=args.scenario)

        # Context: prefer vision for multimodal, switch at t=100 for conflict
        ctx = np.zeros(model.M)
        if args.scenario == 'conflict':
            if t < 100:
                ctx[model.modalities.index('vision')] = 1.0
            else:
                ctx[model.modalities.index('audio')] = 1.0
        else:
            ctx[model.modalities.index('vision')] = 0.5

        # Hazard/reward for adaptive
        hazard = None
        reward = None
        if args.adaptive:
            if args.scenario == 'threat' and t == 50:
                hazard = {'threat': 1.0}
            if t % 50 == 0:
                reward = {'vision': 0.1}

        # Step
        if args.adaptive:
            out = model.step(x_t, ctx=ctx, hazard=hazard, reward=reward, adapt=True)
        else:
            out = model.step(x_t, ctx=ctx)

        # Log
        state = model.get_state() if not args.adaptive else model.get_adaptive_state()
        logger.log_step(t, out['g'], out['pe'], out['v_next'], params=state)

        # Print every 50 steps
        if t % 50 == 0:
            dominant = model.modalities[np.argmax(out['g'])]
            print(f"  t={t:3d}: Dominant={dominant:12s}, Gate={np.max(out['g']):.3f}")

    logger.save_csv()
    print(f"\nSimulation complete! Logs saved to {args.log_dir}")

    # Compute metrics
    gates_array = np.array(logger.history['gates'])
    purities = [ATMRMetrics.routing_purity(g) for g in gates_array]
    entropies = [ATMRMetrics.gate_entropy(g) for g in gates_array]

    print("\n" + "=" * 60)
    print("Metrics")
    print("=" * 60)
    print(f"  Mean routing purity: {np.mean(purities):.3f}")
    print(f"  Mean gate entropy:   {np.mean(entropies):.3f} bits")
    print(f"  Gate stability:      {ATMRMetrics.stability(gates_array):.3f}")

    if args.scenario == 'conflict':
        audio_idx = model.modalities.index('audio')
        latency = ATMRMetrics.switch_latency(gates_array, 100, audio_idx, threshold=0.4)
        print(f"  Switch latency:      {latency} steps")

    # Generate plots
    if args.plot:
        print("\nGenerating plots...")
        ATMRVisualizer.plot_gates(
            logger, model.modalities,
            save_path=os.path.join(args.log_dir, 'gates.png')
        )

        if args.adaptive:
            ATMRVisualizer.plot_parameter_evolution(
                logger, 'prior', model.modalities,
                save_path=os.path.join(args.log_dir, 'priors.png')
            )

        print(f"  Plots saved to {args.log_dir}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
