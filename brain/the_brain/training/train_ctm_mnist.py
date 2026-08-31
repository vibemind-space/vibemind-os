"""
Train ATM-R + classifier on MNIST.

Standalone script for MNIST classification with ATM-R routing.
Ready for CTM integration when available.

Usage:
    python train_ctm_mnist.py --adaptive --epochs 10 --log-dir data/mnist_exp
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import argparse
from sklearn.datasets import fetch_openml
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report

from thalamo_pc_adaptive import ThalamoPC6Adaptive
from config_loader import load_config, create_model_from_config
from logger_viz import ATMRLogger, ATMRVisualizer, ATMRMetrics


def load_mnist(n_samples=5000, test_size=0.2, seed=42):
    """Load and preprocess MNIST."""
    print("Loading MNIST...")
    mnist = fetch_openml('mnist_784', version=1, parser='auto')
    X, y = mnist['data'].values[:n_samples], mnist['target'].values[:n_samples].astype(int)

    # Normalize
    X = X / 255.0

    # Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=seed)

    print(f"  Train: {X_train.shape}, Test: {X_test.shape}")
    return X_train, X_test, y_train, y_test


def project_to_latent(X, target_dim=128, seed=42):
    """Project high-dim input to ATM-R latent dim."""
    np.random.seed(seed)
    input_dim = X.shape[1]
    proj_matrix = np.random.randn(target_dim, input_dim) / np.sqrt(input_dim)
    X_proj = (proj_matrix @ X.T).T
    return X_proj, proj_matrix


def generate_audio(label, dim=64):
    """Generate synthetic audio correlated with label."""
    freq = 0.1 + label * 0.05
    t = np.linspace(0, 2*np.pi, dim)
    audio = np.sin(freq * t) + 0.1 * np.random.randn(dim)
    return audio


def main():
    parser = argparse.ArgumentParser(description='Train ATM-R on MNIST')
    parser.add_argument('--config', type=str, default='configs/default.yaml', help='Config file')
    parser.add_argument('--adaptive', action='store_true', help='Use adaptive ATM-R')
    parser.add_argument('--n-samples', type=int, default=5000, help='Number of MNIST samples')
    parser.add_argument('--log-dir', type=str, default='data/mnist_train', help='Log directory')
    parser.add_argument('--seed', type=int, default=42, help='Random seed')
    parser.add_argument('--plot', action='store_true', help='Generate plots')

    args = parser.parse_args()

    print("=" * 60)
    print("ATM-R MNIST Training")
    print("=" * 60)

    # Load data
    X_train, X_test, y_train, y_test = load_mnist(n_samples=args.n_samples, seed=args.seed)

    # Load config
    config = load_config(args.config)
    config['simulation']['seed'] = args.seed
    config['dimensions']['vision'] = 128
    config['dimensions']['audio'] = 64

    # Create ATM-R
    print(f"\nInitializing {'Adaptive' if args.adaptive else 'Standard'} ATM-R...")
    atmr = create_model_from_config(config, adaptive=args.adaptive)

    # Project MNIST to vision dimension
    print("\nProjecting MNIST to ATM-R vision dimension...")
    X_train_proj, proj_matrix = project_to_latent(X_train, target_dim=atmr.d['vision'], seed=args.seed)
    X_test_proj = (proj_matrix @ X_test.T).T

    # Generate synthetic audio
    print("Generating synthetic audio...")
    audio_train = np.array([generate_audio(label, atmr.d['audio']) for label in y_train])
    audio_test = np.array([generate_audio(label, atmr.d['audio']) for label in y_test])

    # Process training data through ATM-R
    print("\nProcessing training data through ATM-R...")
    logger = ATMRLogger(log_dir=args.log_dir, save_interval=100)
    routed_train = []

    ctx = np.zeros(atmr.M)
    ctx[atmr.modalities.index('vision')] = 1.0  # Task prefers vision

    for i, (vis, aud) in enumerate(zip(X_train_proj, audio_train)):
        x_t = {
            'vision': vis,
            'audio': aud,
            'touch': np.zeros(atmr.d['touch']),
            'taste': np.zeros(atmr.d['taste']),
            'vestibular': np.zeros(atmr.d['vestibular']),
            'threat': np.zeros(atmr.d['threat'])
        }

        if args.adaptive:
            out = atmr.step(x_t, ctx=ctx, adapt=True)
        else:
            out = atmr.step(x_t, ctx=ctx)

        logger.log_step(i, out['g'], out['pe'], out['v_next'])
        routed_train.append(out['y'].flatten())

        if i % 500 == 0 and i > 0:
            print(f"  Processed {i}/{len(X_train_proj)} samples")

    routed_train = np.array(routed_train)
    logger.save_csv()
    print(f"  Routed train features: {routed_train.shape}")

    # Train classifier
    print("\nTraining classifier on routed features...")
    clf = LogisticRegression(max_iter=1000, random_state=args.seed, verbose=0)
    clf.fit(routed_train, y_train)

    # Baseline: raw vision
    print("Training baseline classifier on raw vision...")
    clf_baseline = LogisticRegression(max_iter=1000, random_state=args.seed, verbose=0)
    clf_baseline.fit(X_train_proj, y_train)

    # Process test data
    print("\nProcessing test data...")
    atmr.reset_state()
    routed_test = []

    for vis, aud in zip(X_test_proj, audio_test):
        x_t = {
            'vision': vis,
            'audio': aud,
            'touch': np.zeros(atmr.d['touch']),
            'taste': np.zeros(atmr.d['taste']),
            'vestibular': np.zeros(atmr.d['vestibular']),
            'threat': np.zeros(atmr.d['threat'])
        }

        out = atmr.step(x_t, ctx=ctx, adapt=False)
        routed_test.append(out['y'].flatten())

    routed_test = np.array(routed_test)

    # Evaluate
    print("\n" + "=" * 60)
    print("Results")
    print("=" * 60)

    y_pred_atmr = clf.predict(routed_test)
    y_pred_baseline = clf_baseline.predict(X_test_proj)

    acc_atmr = accuracy_score(y_test, y_pred_atmr)
    acc_baseline = accuracy_score(y_test, y_pred_baseline)

    print(f"\nAccuracy:")
    print(f"  ATM-R + Classifier:   {acc_atmr:.4f}")
    print(f"  Baseline (raw vision): {acc_baseline:.4f}")
    print(f"  Improvement:           {(acc_atmr - acc_baseline)*100:+.2f}%")

    # Metrics
    gates_array = np.array(logger.history['gates'])
    purities = [ATMRMetrics.routing_purity(g) for g in gates_array]
    entropies = [ATMRMetrics.gate_entropy(g) for g in gates_array]

    print(f"\nATM-R Metrics:")
    print(f"  Mean routing purity:  {np.mean(purities):.3f}")
    print(f"  Mean gate entropy:    {np.mean(entropies):.3f} bits")
    print(f"  Gate stability:       {ATMRMetrics.stability(gates_array):.3f}")

    # Detailed classification report
    print(f"\nClassification Report (ATM-R):")
    print(classification_report(y_test, y_pred_atmr, digits=3))

    # Generate plots
    if args.plot:
        print("\nGenerating plots...")
        ATMRVisualizer.plot_gates(
            logger, atmr.modalities,
            save_path=os.path.join(args.log_dir, 'gates_train.png')
        )

        if args.adaptive:
            ATMRVisualizer.plot_parameter_evolution(
                logger, 'prior', atmr.modalities,
                save_path=os.path.join(args.log_dir, 'priors_train.png')
            )

        print(f"  Plots saved to {args.log_dir}")

    print("\n" + "=" * 60)
    print("Training complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
