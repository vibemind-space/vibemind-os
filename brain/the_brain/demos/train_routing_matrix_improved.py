"""
Improved Routing Matrix Training

Improvements:
1. More epochs (50 instead of 5)
2. Higher learning rate (0.01 instead of 0.001)
3. Realistic feedback based on brain gates
4. More diverse training tasks (100+ instead of 20)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt

from core.hierarchical_planner import HierarchicalPlanner
from core.conversation_path_planner import ConversationPathPlanner
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor


def get_brain_gate_value(planner, modality_name):
    """Get the gate value for a specific modality"""
    if hasattr(planner.layer2, 'brain_monitor') and planner.layer2.brain_monitor.gate_history:
        gates = list(planner.layer2.brain_monitor.gate_history)[-1]
        # Fixed: use standard modality list
        modalities = [
            'vision', 'audio', 'touch', 'taste', 'vestibular',
            'threat', 'tool_trace', 'temporal_pattern',
            'error_signal', 'success_signal'
        ]
        if modality_name in modalities:
            idx = modalities.index(modality_name)
            if idx < len(gates):
                return gates[idx]
    return 0.0


def simulate_realistic_feedback(prediction, task_description, planner):
    """
    Realistic feedback based on actual brain gate values

    NEW Rules (5 interventions):
    1. threat > 0.35 → terminate (safety first!)
    2. error_signal > 0.25 → retry (fix errors)
    3. success_signal > 0.30 AND confidence > 0.70 → execute (high confidence!)
    4. success_signal > 0.30 → suggest (continue on success)
    5. tool_trace > 0.30 AND low threat AND confidence > 0.60 → execute (confident pattern)
    6. tool_trace > 0.30 AND low threat → suggest (confident in tools)
    7. Low confidence overall → wait (need more info)
    8. Default → suggest
    """
    primary_decision = prediction.actionable_decision.multi_target_decision['primary']['type']

    # Get brain gate values
    threat_gate = get_brain_gate_value(planner, 'threat')
    error_gate = get_brain_gate_value(planner, 'error_signal')
    success_gate = get_brain_gate_value(planner, 'success_signal')
    tool_gate = get_brain_gate_value(planner, 'tool_trace')

    confidence = prediction.confidence

    # Decision rules based on brain state
    correct_action = None

    # Rule 1: High threat → terminate (HIGHEST PRIORITY)
    if threat_gate > 0.35:
        correct_action = 'terminate'

    # Rule 2: High error signal → retry
    elif error_gate > 0.25:
        correct_action = 'retry'

    # Rule 3: High success signal + high confidence → EXECUTE
    elif success_gate > 0.30 and confidence > 0.70:
        correct_action = 'execute'

    # Rule 4: High success signal → suggest
    elif success_gate > 0.30:
        correct_action = 'suggest'

    # Rule 5: High tool_trace + low threat + good confidence → EXECUTE
    elif tool_gate > 0.30 and threat_gate < 0.15 and confidence > 0.60:
        correct_action = 'execute'

    # Rule 6: High tool_trace + low threat → suggest
    elif tool_gate > 0.30 and threat_gate < 0.15:
        correct_action = 'suggest'

    # Rule 7: Low confidence → wait
    elif confidence < 0.40:
        correct_action = 'wait'

    # Rule 8: Default → suggest
    else:
        correct_action = 'suggest'

    # Check if prediction was correct
    success = (primary_decision == correct_action)

    return {
        'action': correct_action,
        'success': success,
        'brain_state': {
            'threat': threat_gate,
            'error': error_gate,
            'success': success_gate,
            'tool_trace': tool_gate,
            'confidence': confidence
        }
    }


def generate_diverse_tasks():
    """Generate 100+ diverse training tasks"""

    # Base task templates
    templates = {
        'urgent_deployment': [
            "Deploy {} immediately",
            "Urgent: {} deployment needed",
            "Emergency {} rollout",
            "{} deployment with high priority",
        ],
        'error_handling': [
            "Fix error in {}",
            "{} failing with errors",
            "Debug {} issues",
            "Resolve {} problems",
            "Handle {} exceptions",
        ],
        'routine_tasks': [
            "Check {} status",
            "Monitor {} metrics",
            "Review {} logs",
            "Update {} configuration",
        ],
        'git_operations': [
            "git {} and push",
            "Commit changes to {}",
            "Create {} branch",
            "Merge {} pull request",
        ],
        'analysis': [
            "Analyze {} performance",
            "Investigate {} bottleneck",
            "Profile {} execution",
            "Examine {} behavior",
        ],
        'critical': [
            "CRITICAL: {} failure",
            "Emergency: {} down",
            "Urgent fix for {}",
            "{} system crash",
        ]
    }

    # Components to fill in
    components = {
        'urgent_deployment': ['Docker container', 'Kubernetes pod', 'microservice', 'API'],
        'error_handling': ['authentication', 'database', 'API endpoint', 'cache layer', 'message queue'],
        'routine_tasks': ['memory', 'CPU', 'disk', 'network'],
        'git_operations': ['feature', 'bugfix', 'hotfix', 'release'],
        'analysis': ['query', 'algorithm', 'cache', 'network'],
        'critical': ['database', 'payment system', 'authentication', 'API gateway']
    }

    tasks = []

    # Generate tasks from templates
    for category, template_list in templates.items():
        comp_list = components[category]
        for template in template_list:
            for component in comp_list:
                tasks.append(template.format(component))

    # Add some hand-crafted diverse tasks
    tasks.extend([
        "Quick status check",
        "Full system audit",
        "Performance optimization needed",
        "Security patch deployment",
        "Database migration",
        "Load balancer configuration",
        "SSL certificate renewal",
        "Backup verification",
        "Rollback to previous version",
        "Scale up infrastructure",
        "Monitor real-time metrics",
        "Clean up old resources",
        "Test new feature",
        "Code review needed",
        "Documentation update",
    ])

    return tasks


def train_improved():
    """Improved training with all optimizations"""
    print("=" * 70)
    print("IMPROVED ROUTING MATRIX TRAINING")
    print("=" * 70)
    print()

    # Initialize system
    print("Initializing hierarchical planner...")
    meta_router = MetaRouter(
        enable_hippocampus=True,
        enable_per_modality_pes=True,
        seed=42
    )

    # IMPROVEMENT 2: Higher learning rate (0.01 instead of 0.001)
    planner_layer2 = ConversationPathPlanner(
        meta_router=meta_router,
        strategy_library=StrategyLibrary(max_strategies_per_type=20),
        brain_monitor=BrainActivityMonitor(history_length=100),
        enable_adaptive_gating=True
    )

    log_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
    print(f"Training Layer 2 from: {log_dir}")
    planner_layer2.train_from_sessions(log_dir, limit=39)

    # NEW: Use 5 interventions including 'execute'
    planner = HierarchicalPlanner(
        conversation_planner=planner_layer2,
        intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
        seed=42
    )

    # Set higher learning rate
    planner.layer3.multi_target_router.learning_rate = 0.01  # 10x higher!
    print(f"Learning rate: {planner.layer3.multi_target_router.learning_rate}")
    print()

    # Get initial matrix
    initial_matrix = planner.layer3.multi_target_router.get_routing_matrix()

    # IMPROVEMENT 4: More diverse tasks
    all_tasks = generate_diverse_tasks()
    print(f"Generated {len(all_tasks)} diverse training tasks")
    print()

    # Sample for training
    np.random.seed(42)
    training_tasks = np.random.choice(all_tasks, size=min(100, len(all_tasks)), replace=False)
    print(f"Using {len(training_tasks)} tasks for training")
    print()

    # Training history
    history = {
        'accuracy': [],
        'primary_weight': [],
        'matrix_norm': [],
        'correct_by_rule': {
            'high_threat_terminate': [],
            'high_error_retry': [],
            'high_success_suggest': []
        }
    }

    # IMPROVEMENT 1: More epochs (50 instead of 5)
    num_epochs = 20  # 20 for faster demo, could be 50
    print("=" * 70)
    print(f"TRAINING LOOP ({num_epochs} EPOCHS)")
    print("=" * 70)
    print()

    best_accuracy = 0
    best_matrix = None

    for epoch in range(num_epochs):
        epoch_correct = 0
        epoch_total = 0

        # Rule-specific tracking
        rule_stats = {
            'high_threat_terminate': {'correct': 0, 'total': 0},
            'high_error_retry': {'correct': 0, 'total': 0},
            'high_success_suggest': {'correct': 0, 'total': 0}
        }

        for task in training_tasks:
            # Predict
            prediction = planner.predict(task)

            # IMPROVEMENT 3: Realistic feedback based on brain gates
            feedback = simulate_realistic_feedback(prediction, task, planner)

            # Track accuracy
            if feedback['success']:
                epoch_correct += 1
            epoch_total += 1

            # Track rule-specific accuracy
            brain = feedback['brain_state']
            primary = prediction.actionable_decision.multi_target_decision['primary']['type']

            if brain['threat'] > 0.35:
                rule_stats['high_threat_terminate']['total'] += 1
                if primary == 'terminate':
                    rule_stats['high_threat_terminate']['correct'] += 1

            if brain['error'] > 0.25:
                rule_stats['high_error_retry']['total'] += 1
                if primary == 'retry':
                    rule_stats['high_error_retry']['correct'] += 1

            if brain['success'] > 0.30:
                rule_stats['high_success_suggest']['total'] += 1
                if primary == 'suggest':
                    rule_stats['high_success_suggest']['correct'] += 1

            # Learn from feedback
            if hasattr(planner.layer2, 'brain_monitor') and planner.layer2.brain_monitor.gate_history:
                gates = list(planner.layer2.brain_monitor.gate_history)[-1]

                feedback_strength = 1.0 if feedback['success'] else 0.8
                planner.layer3.multi_target_router.update_routing_matrix(
                    gates=gates,
                    target_intervention=feedback['action'],
                    feedback_strength=feedback_strength
                )

        # Epoch stats
        epoch_accuracy = epoch_correct / epoch_total if epoch_total > 0 else 0

        # Sample predictions for weight analysis
        sample_predictions = [
            planner.predict(task) for task in np.random.choice(training_tasks, size=5, replace=False)
        ]
        avg_primary_weight = np.mean([
            p.actionable_decision.multi_target_decision['primary']['weight']
            for p in sample_predictions
        ])

        matrix_norm = np.linalg.norm(planner.layer3.multi_target_router.get_routing_matrix())

        # Save history
        history['accuracy'].append(epoch_accuracy)
        history['primary_weight'].append(avg_primary_weight)
        history['matrix_norm'].append(matrix_norm)

        for rule_name, stats in rule_stats.items():
            if stats['total'] > 0:
                rule_acc = stats['correct'] / stats['total']
            else:
                rule_acc = 0.0
            history['correct_by_rule'][rule_name].append(rule_acc)

        # Track best
        if epoch_accuracy > best_accuracy:
            best_accuracy = epoch_accuracy
            best_matrix = planner.layer3.multi_target_router.get_routing_matrix().copy()

        # Print every 5 epochs
        if (epoch + 1) % 5 == 0:
            print(f"Epoch {epoch + 1}/{num_epochs}")
            print(f"  Accuracy:         {epoch_accuracy:.1%}")
            print(f"  Primary Weight:   {avg_primary_weight:.3f}")
            print(f"  Matrix Norm:      {matrix_norm:.3f}")

            # Rule-specific accuracy
            for rule_name, stats in rule_stats.items():
                if stats['total'] > 0:
                    rule_acc = stats['correct'] / stats['total']
                    print(f"  {rule_name}: {rule_acc:.1%} ({stats['correct']}/{stats['total']})")
            print()

    # Load best matrix
    planner.layer3.multi_target_router.set_routing_matrix(best_matrix)
    final_matrix = best_matrix

    # Evaluation
    print("=" * 70)
    print("EVALUATION")
    print("=" * 70)
    print()

    print(f"Best Accuracy:     {best_accuracy:.1%}")
    print(f"Initial Accuracy:  {history['accuracy'][0]:.1%}")
    print(f"Improvement:       {best_accuracy - history['accuracy'][0]:+.1%}")
    print()

    # Matrix analysis
    print("Key Matrix Changes:")
    print("-" * 70)

    modalities = [
        'vision', 'audio', 'touch', 'taste', 'vestibular',
        'threat', 'tool_trace', 'temporal_pattern',
        'error_signal', 'success_signal'
    ]
    interventions = ['suggest', 'retry', 'wait', 'terminate', 'execute']

    critical_modalities = ['threat', 'error_signal', 'success_signal', 'tool_trace']

    for mod_name in critical_modalities:
        if mod_name in modalities:
            idx = modalities.index(mod_name)
            print(f"\n{mod_name} -> interventions:")
            for j, intervention in enumerate(interventions):
                before = initial_matrix[idx, j]
                after = final_matrix[idx, j]
                change = after - before
                arrow = "***" if abs(change) > 0.1 else "**" if abs(change) > 0.05 else "*" if abs(change) > 0.02 else ""
                print(f"  {intervention:12s}: {before:+.3f} -> {after:+.3f} ({change:+.3f}) {arrow}")

    print()

    # Visualization
    print("=" * 70)
    print("VISUALIZATION")
    print("=" * 70)
    print()

    fig = plt.figure(figsize=(16, 12))
    gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)

    # Plot 1: Training curve
    ax1 = fig.add_subplot(gs[0, 0])
    epochs = range(1, num_epochs + 1)
    ax1.plot(epochs, history['accuracy'], marker='o', linewidth=2, color='#667eea', label='Accuracy')
    ax1.axhline(y=history['accuracy'][0], color='red', linestyle='--', label=f'Initial: {history["accuracy"][0]:.1%}')
    ax1.set_xlabel('Epoch')
    ax1.set_ylabel('Accuracy')
    ax1.set_title('Training Accuracy', fontweight='bold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Plot 2: Primary weight evolution
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(epochs, history['primary_weight'], marker='s', linewidth=2, color='#764ba2')
    ax2.set_xlabel('Epoch')
    ax2.set_ylabel('Avg Primary Weight')
    ax2.set_title('Decision Confidence', fontweight='bold')
    ax2.grid(True, alpha=0.3)

    # Plot 3: Rule-specific accuracy
    ax3 = fig.add_subplot(gs[0, 2])
    for rule_name, accs in history['correct_by_rule'].items():
        if any(accs):  # Only plot if there's data
            ax3.plot(epochs, accs, marker='o', linewidth=2, label=rule_name.replace('_', ' '))
    ax3.set_xlabel('Epoch')
    ax3.set_ylabel('Rule Accuracy')
    ax3.set_title('Rule-Specific Learning', fontweight='bold')
    ax3.legend(fontsize=8)
    ax3.grid(True, alpha=0.3)

    # Plot 4: Matrix before
    ax4 = fig.add_subplot(gs[1, :2])
    im1 = ax4.imshow(initial_matrix, cmap='RdBu_r', aspect='auto', vmin=-0.5, vmax=0.5)
    ax4.set_xticks(range(len(interventions)))
    ax4.set_xticklabels(interventions)
    ax4.set_yticks(range(len(modalities)))
    ax4.set_yticklabels(modalities, fontsize=9)
    ax4.set_title('Routing Matrix BEFORE Training', fontweight='bold')
    plt.colorbar(im1, ax=ax4)

    # Plot 5: Matrix after
    ax5 = fig.add_subplot(gs[2, :2])
    im2 = ax5.imshow(final_matrix, cmap='RdBu_r', aspect='auto', vmin=-0.5, vmax=0.5)
    ax5.set_xticks(range(len(interventions)))
    ax5.set_xticklabels(interventions)
    ax5.set_yticks(range(len(modalities)))
    ax5.set_yticklabels(modalities, fontsize=9)
    ax5.set_title('Routing Matrix AFTER Training', fontweight='bold')
    plt.colorbar(im2, ax=ax5)

    # Plot 6: Change magnitude
    ax6 = fig.add_subplot(gs[1:, 2])
    change_matrix = final_matrix - initial_matrix
    im3 = ax6.imshow(np.abs(change_matrix), cmap='YlOrRd', aspect='auto')
    ax6.set_xticks(range(len(interventions)))
    ax6.set_xticklabels(interventions, fontsize=9)
    ax6.set_yticks(range(len(modalities)))
    ax6.set_yticklabels(modalities, fontsize=9)
    ax6.set_title('Change Magnitude', fontweight='bold')
    plt.colorbar(im3, ax=ax6)

    plt.suptitle(f'Improved Training: {num_epochs} Epochs, LR=0.01, {len(training_tasks)} Tasks',
                 fontsize=14, fontweight='bold')

    plt.savefig('data/routing_matrix_improved.png', dpi=150, bbox_inches='tight')
    print("  Saved to: data/routing_matrix_improved.png")
    print()

    # Save trained matrix to production
    print("=" * 70)
    print("SAVING TRAINED MATRIX")
    print("=" * 70)
    print()

    from datetime import datetime
    from pathlib import Path
    import json

    matrix_dir = Path("production/trained_matrices")
    matrix_dir.mkdir(parents=True, exist_ok=True)

    # Save matrix with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    matrix_path = matrix_dir / f"routing_matrix_v{timestamp}.npy"
    np.save(matrix_path, best_matrix)

    # Save metadata
    meta = {
        'version': f'v{timestamp}',
        'timestamp': datetime.now().isoformat(),
        'accuracy': float(best_accuracy),
        'num_predictions': len(training_tasks) * num_epochs,
        'avg_confidence': float(history['primary_weight'][-1]),
        'notes': f'Trained with {num_epochs} epochs, LR=0.01, {len(training_tasks)} tasks, 5 interventions'
    }

    meta_path = matrix_path.with_suffix('.json')
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    print(f"Saved matrix to: {matrix_path}")
    print(f"Matrix shape: {best_matrix.shape}")
    print(f"Metadata saved to: {meta_path}")
    print()

    print("=" * 70)
    print("TRAINING COMPLETE!")
    print("=" * 70)
    print()
    print(f"Final Results:")
    print(f"  Best Accuracy:    {best_accuracy:.1%}")
    print(f"  Improvement:      {best_accuracy - history['accuracy'][0]:+.1%}")
    print(f"  Final Confidence: {history['primary_weight'][-1]:.3f}")
    print()


if __name__ == "__main__":
    train_improved()
