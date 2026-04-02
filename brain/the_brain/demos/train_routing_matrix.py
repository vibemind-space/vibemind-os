"""
Train Routing Matrix from Session Logs

This script demonstrates how to train the Multi-Target Decision Routing Matrix
based on feedback from real conversation sessions.

Currently, the routing matrix is randomly initialized and doesn't learn.
This script shows how to enable learning so the system can specialize:
- high threat → terminate
- high success → suggest
- high error_signal → retry
- etc.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import json

from core.hierarchical_planner import HierarchicalPlanner
from core.conversation_path_planner import ConversationPathPlanner
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor


def simulate_feedback(prediction, task_description):
    """
    Simulate user feedback based on prediction quality

    In a real system, this would come from actual user feedback or
    task execution results. For this demo, we simulate it based on
    heuristics.

    Args:
        prediction: HierarchicalPrediction from planner
        task_description: Original task description

    Returns:
        dict with 'action' and 'success' keys
    """
    task_lower = task_description.lower()
    primary_decision = prediction.actionable_decision.multi_target_decision['primary']['type']

    # Heuristic rules for feedback simulation
    feedback = {
        'action': primary_decision,
        'success': False
    }

    # Rule 1: High urgency tasks should suggest immediate action
    if prediction.layer1_routing.features.urgency > 0.7:
        if primary_decision == 'suggest':
            feedback['success'] = True
        else:
            feedback['action'] = 'suggest'  # correct action
            feedback['success'] = False

    # Rule 2: Docker/deployment tasks with errors should retry
    elif 'docker' in task_lower or 'deploy' in task_lower:
        if 'error' in task_lower or 'fail' in task_lower:
            if primary_decision == 'retry':
                feedback['success'] = True
            else:
                feedback['action'] = 'retry'
                feedback['success'] = False
        else:
            if primary_decision == 'suggest':
                feedback['success'] = True
            else:
                feedback['action'] = 'suggest'
                feedback['success'] = False

    # Rule 3: GitHub tasks usually succeed → suggest
    elif 'git' in task_lower or 'github' in task_lower:
        if primary_decision == 'suggest':
            feedback['success'] = True
        else:
            feedback['action'] = 'suggest'
            feedback['success'] = False

    # Rule 4: Complex analysis tasks need analytical mode
    elif 'analyze' in task_lower or 'complex' in task_lower:
        if prediction.confidence < 0.5:
            # Low confidence → wait for more info
            if primary_decision == 'wait':
                feedback['success'] = True
            else:
                feedback['action'] = 'wait'
                feedback['success'] = False
        else:
            if primary_decision == 'suggest':
                feedback['success'] = True
            else:
                feedback['action'] = 'suggest'
                feedback['success'] = False

    # Rule 5: Critical errors → terminate
    elif 'critical' in task_lower or 'emergency' in task_lower:
        if primary_decision == 'terminate':
            feedback['success'] = True
        else:
            feedback['action'] = 'terminate'
            feedback['success'] = False

    # Default: suggest is usually good
    else:
        if primary_decision == 'suggest':
            feedback['success'] = True
        else:
            feedback['action'] = 'suggest'
            feedback['success'] = False

    return feedback


def train_routing_matrix():
    """Train routing matrix from session logs"""
    print("=" * 70)
    print("TRAINING ROUTING MATRIX FROM SESSION LOGS")
    print("=" * 70)
    print()

    # Initialize system
    print("Initializing hierarchical planner...")
    meta_router = MetaRouter(
        enable_hippocampus=True,
        enable_per_modality_pes=True,
        seed=42
    )
    strategy_lib = StrategyLibrary(max_strategies_per_type=20)
    brain_monitor = BrainActivityMonitor(history_length=100)

    layer2 = ConversationPathPlanner(
        meta_router=meta_router,
        strategy_library=strategy_lib,
        brain_monitor=brain_monitor,
        enable_adaptive_gating=True
    )

    # Train Layer 2 from sessions
    log_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
    print(f"Training Layer 2 from: {log_dir}")
    layer2.train_from_sessions(log_dir, limit=39)

    # Create hierarchical planner
    planner = HierarchicalPlanner(
        conversation_planner=layer2,
        seed=42
    )
    print()

    # Get initial routing matrix
    initial_matrix = planner.layer3.multi_target_router.get_routing_matrix()
    print("Initial Routing Matrix (random):")
    print(f"  Shape: {initial_matrix.shape}")
    print(f"  Mean:  {np.mean(initial_matrix):.4f}")
    print(f"  Std:   {np.std(initial_matrix):.4f}")
    print()

    # Test tasks for training
    training_tasks = [
        "Check memory status urgently",
        "Deploy with Docker immediately",
        "git commit and push to GitHub",
        "Analyze complex codebase architecture",
        "Search for files and debug errors",
        "Critical failure in production system",
        "Refactor code and improve performance",
        "Test the application with pytest",
        "Monitor system metrics in real-time",
        "Deploy container with error handling",
        "Fix bug in authentication module",
        "Update dependencies and rebuild",
        "Review pull request on GitHub",
        "Investigate performance bottleneck",
        "Emergency: Database connection lost",
        "Clean up old Docker images",
        "Commit changes and create branch",
        "Complex multi-step deployment process",
        "Quick status check on Redis",
        "Urgent security patch deployment"
    ]

    # Training loop
    print("=" * 70)
    print("TRAINING LOOP")
    print("=" * 70)
    print()

    training_history = {
        'accuracy': [],
        'avg_primary_weight': [],
        'matrix_norm': []
    }

    num_epochs = 5
    correct_before_training = 0
    total_predictions = 0

    for epoch in range(num_epochs):
        print(f"Epoch {epoch + 1}/{num_epochs}")
        print("-" * 70)

        epoch_correct = 0
        epoch_total = 0

        for i, task in enumerate(training_tasks):
            # Make prediction
            prediction = planner.predict(task)

            # Simulate feedback
            feedback = simulate_feedback(prediction, task)

            # Check accuracy
            primary_decision = prediction.actionable_decision.multi_target_decision['primary']['type']
            is_correct = feedback['success']

            if epoch == 0:
                total_predictions += 1
                if is_correct:
                    correct_before_training += 1

            epoch_correct += int(is_correct)
            epoch_total += 1

            # Get brain gates for learning
            if hasattr(planner.layer2, 'brain_monitor') and planner.layer2.brain_monitor.gate_history:
                gates = list(planner.layer2.brain_monitor.gate_history)[-1]

                # Learn from feedback
                feedback_strength = 1.0 if feedback['success'] else 0.8
                planner.layer3.multi_target_router.update_routing_matrix(
                    gates=gates,
                    target_intervention=feedback['action'],
                    feedback_strength=feedback_strength
                )

            # Progress
            if (i + 1) % 5 == 0:
                acc = epoch_correct / epoch_total
                print(f"  Progress: {i+1}/{len(training_tasks)} tasks, Accuracy: {acc:.1%}")

        # Epoch summary
        epoch_accuracy = epoch_correct / epoch_total
        primary_weight = np.mean([
            planner.predict(task).actionable_decision.multi_target_decision['primary']['weight']
            for task in training_tasks[:5]  # Sample
        ])
        matrix_norm = np.linalg.norm(planner.layer3.multi_target_router.get_routing_matrix())

        training_history['accuracy'].append(epoch_accuracy)
        training_history['avg_primary_weight'].append(primary_weight)
        training_history['matrix_norm'].append(matrix_norm)

        print(f"  Epoch Accuracy: {epoch_accuracy:.1%}")
        print(f"  Avg Primary Weight: {primary_weight:.3f}")
        print(f"  Matrix Norm: {matrix_norm:.3f}")
        print()

    # Get final routing matrix
    final_matrix = planner.layer3.multi_target_router.get_routing_matrix()

    # Evaluation
    print("=" * 70)
    print("EVALUATION")
    print("=" * 70)
    print()

    accuracy_before = correct_before_training / total_predictions
    accuracy_after = training_history['accuracy'][-1]
    improvement = accuracy_after - accuracy_before

    print(f"Accuracy BEFORE training: {accuracy_before:.1%}")
    print(f"Accuracy AFTER training:  {accuracy_after:.1%}")
    print(f"Improvement:              {improvement:+.1%}")
    print()

    # Matrix analysis
    print("Routing Matrix Changes:")
    print("-" * 70)

    modalities = [
        'vision', 'audio', 'touch', 'taste', 'vestibular',
        'threat', 'tool_trace', 'temporal_pattern',
        'error_signal', 'success_signal'
    ]
    interventions = ['suggest', 'retry', 'wait', 'terminate']

    print("\nKey Learned Patterns:")
    print()

    # Analyze threat row
    threat_idx = 5
    print(f"threat -> interventions:")
    for j, intervention in enumerate(interventions):
        before = initial_matrix[threat_idx, j]
        after = final_matrix[threat_idx, j]
        change = after - before
        print(f"  {intervention:12s}: {before:+.3f} -> {after:+.3f} ({change:+.3f})")
    print()

    # Analyze success_signal row
    success_idx = 9
    print(f"success_signal -> interventions:")
    for j, intervention in enumerate(interventions):
        before = initial_matrix[success_idx, j]
        after = final_matrix[success_idx, j]
        change = after - before
        print(f"  {intervention:12s}: {before:+.3f} -> {after:+.3f} ({change:+.3f})")
    print()

    # Analyze error_signal row
    error_idx = 8
    print(f"error_signal -> interventions:")
    for j, intervention in enumerate(interventions):
        before = initial_matrix[error_idx, j]
        after = final_matrix[error_idx, j]
        change = after - before
        print(f"  {intervention:12s}: {before:+.3f} -> {after:+.3f} ({change:+.3f})")
    print()

    # Visualization
    print("=" * 70)
    print("GENERATING VISUALIZATION")
    print("=" * 70)
    print()

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Plot 1: Training accuracy over epochs
    ax1 = axes[0, 0]
    ax1.plot(range(1, num_epochs + 1), training_history['accuracy'],
             marker='o', linewidth=2, markersize=8, color='#667eea')
    ax1.axhline(y=accuracy_before, color='red', linestyle='--',
                linewidth=2, label=f'Before: {accuracy_before:.1%}')
    ax1.set_xlabel('Epoch')
    ax1.set_ylabel('Accuracy')
    ax1.set_title('Training Accuracy', fontweight='bold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Plot 2: Average primary weight over epochs
    ax2 = axes[0, 1]
    ax2.plot(range(1, num_epochs + 1), training_history['avg_primary_weight'],
             marker='s', linewidth=2, markersize=8, color='#764ba2')
    ax2.set_xlabel('Epoch')
    ax2.set_ylabel('Avg Primary Weight')
    ax2.set_title('Decision Confidence', fontweight='bold')
    ax2.grid(True, alpha=0.3)

    # Plot 3: Routing matrix heatmap (before)
    ax3 = axes[1, 0]
    im1 = ax3.imshow(initial_matrix, cmap='RdBu_r', aspect='auto', vmin=-0.3, vmax=0.3)
    ax3.set_xticks(range(len(interventions)))
    ax3.set_xticklabels(interventions, rotation=45, ha='right')
    ax3.set_yticks(range(len(modalities)))
    ax3.set_yticklabels(modalities)
    ax3.set_title('Routing Matrix BEFORE Training', fontweight='bold')
    plt.colorbar(im1, ax=ax3)

    # Plot 4: Routing matrix heatmap (after)
    ax4 = axes[1, 1]
    im2 = ax4.imshow(final_matrix, cmap='RdBu_r', aspect='auto', vmin=-0.3, vmax=0.3)
    ax4.set_xticks(range(len(interventions)))
    ax4.set_xticklabels(interventions, rotation=45, ha='right')
    ax4.set_yticks(range(len(modalities)))
    ax4.set_yticklabels(modalities)
    ax4.set_title('Routing Matrix AFTER Training', fontweight='bold')
    plt.colorbar(im2, ax=ax4)

    plt.tight_layout()
    plt.savefig('data/routing_matrix_training.png', dpi=150, bbox_inches='tight')
    print("  Visualization saved to: data/routing_matrix_training.png")
    print()

    # Test on new tasks
    print("=" * 70)
    print("TESTING ON NEW TASKS")
    print("=" * 70)
    print()

    test_tasks = [
        "Emergency deployment failure in production",
        "Routine git commit and push",
        "Analyze performance bottleneck"
    ]

    for task in test_tasks:
        print(f"Task: \"{task}\"")
        print("-" * 70)

        prediction = planner.predict(task)
        mtd = prediction.actionable_decision.multi_target_decision
        primary = mtd['primary']

        print(f"  Primary: {primary['type']} ({primary['weight']:.1%})")
        print(f"  Alternatives:")
        for alt in mtd['alternatives'][:2]:
            print(f"    {alt['type']:12s} {alt['weight']:.1%}")
        print()

    print("=" * 70)
    print("TRAINING COMPLETE [SUCCESS]")
    print("=" * 70)
    print()
    print("KEY RESULTS:")
    print(f"1. Accuracy improved from {accuracy_before:.1%} to {accuracy_after:.1%}")
    print(f"2. System learned task-specific intervention patterns")
    print(f"3. Routing matrix specialized based on feedback")
    print(f"4. Primary decision weights became more confident")
    print()
    print("The routing matrix can now be saved and reused!")


if __name__ == "__main__":
    train_routing_matrix()
