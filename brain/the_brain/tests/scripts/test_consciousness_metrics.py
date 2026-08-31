"""
PHASE 11 DEMO: Consciousness Metrics

Demonstrates:
1. Self-awareness tracking through cognitive state monitoring
2. Confidence calibration (tracking accuracy vs. confidence)
3. Bias detection (overconfidence, underconfidence)
4. Meta-cognitive assessment of decisions
5. Introspection and "known unknowns"
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core.hierarchical_planner import HierarchicalPlanner
from core.conversation_path_planner import ConversationPathPlanner
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor

print("=" * 70)
print("PHASE 11: CONSCIOUSNESS METRICS DEMO")
print("=" * 70)
print()

# Initialize system with ALL cognitive features including consciousness metrics
print("[1/6] Initializing hierarchical planner with consciousness metrics...")
meta_router = MetaRouter(enable_hippocampus=True, seed=42)
planner_layer2 = ConversationPathPlanner(
    meta_router=meta_router,
    strategy_library=StrategyLibrary(),
    brain_monitor=BrainActivityMonitor()
)

# Train from sessions
session_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
planner_layer2.train_from_sessions(session_dir, limit=39)

# Create hierarchical planner with ALL 11 cognitive features
planner = HierarchicalPlanner(
    conversation_planner=planner_layer2,
    intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
    enable_memory=True,
    enable_predictive_coding=True,
    enable_attention=True,
    enable_meta_learning=True,
    enable_dream_mode=True,
    enable_neuromodulation=True,
    enable_temporal_memory=True,
    enable_active_inference=True,
    enable_compositional_reasoning=True,
    enable_tool_creation=True,
    enable_consciousness_metrics=True,  # PHASE 11 enabled!
    seed=42
)

print(f"   {planner}")
print(f"   Consciousness Metrics: ENABLED")
print()

# Show initial state
if planner.consciousness_metrics:
    print("Initial Consciousness State:")
    print("-" * 70)
    print(f"  States tracked: {planner.consciousness_metrics.total_states_tracked}")
    print(f"  Assessments made: {planner.consciousness_metrics.total_assessments}")
    print(f"  Self-awareness events: {planner.consciousness_metrics.self_awareness_events}")
    print()

print("[2/6] Running tasks and tracking cognitive states...")
print("=" * 70)
print()

# Test scenarios with different cognitive demands
task_scenarios = [
    ("Deploy urgent hotfix to production", "docker", 0.9, 0.8),  # High urgency, high complexity
    ("List running containers", "docker", 0.1, 0.2),  # Low urgency, low complexity
    ("Debug complex memory leak in distributed system", "terminal", 0.7, 0.9),  # Medium urgency, very complex
    ("Check git status", "github", 0.2, 0.1),  # Low urgency, simple
    ("Refactor legacy authentication module", "filesystem", 0.5, 0.8),  # Medium urgency, high complexity
]

predictions = []

for i, (task, task_type, urgency, complexity) in enumerate(task_scenarios, 1):
    print(f"TASK {i}/5: '{task}'")
    print(f"  Expected: urgency={urgency:.1f}, complexity={complexity:.1f}")
    print("-" * 70)

    # Make prediction
    prediction = planner.predict(task)
    predictions.append((task, prediction))

    # Show cognitive state
    if prediction.cognitive_state:
        cs = prediction.cognitive_state
        print(f"  [Cognitive State]")
        print(f"    Attention focus: {cs.attention_focus}")
        print(f"    Memory load: {cs.memory_load:.2f}")
        print(f"    Reasoning depth: {cs.reasoning_depth}/3")
        print(f"    Uncertainty: {cs.uncertainty_level:.2f}")
        print(f"    Confidence in self-assessment: {cs.confidence_in_state:.2f}")

    print()

print()
print("=" * 70)
print("[3/6] META-COGNITIVE ASSESSMENT")
print("=" * 70)
print()

# Simulate decision outcomes and assess quality
print("Assessing decision quality (comparing predictions vs. outcomes):")
print("-" * 70)
print()

# Simulate outcomes with varying accuracy
assessment_scenarios = [
    # (task_type, decision, predicted_outcome, actual_outcome, confidence)
    ("docker", "execute", "success", "success", 0.9),  # Well-calibrated
    ("docker", "wait", "success", "failure", 0.8),  # Overconfident
    ("terminal", "suggest", "failure", "success", 0.4),  # Underconfident
    ("github", "execute", "success", "success", 0.95),  # Well-calibrated
    ("filesystem", "retry", "success", "failure", 0.7),  # Overconfident
    ("docker", "execute", "success", "failure", 0.85),  # Overconfident again
    ("terminal", "suggest", "success", "success", 0.6),  # Reasonable
    ("github", "wait", "failure", "success", 0.3),  # Underconfident
]

assessments = []

for i, (task_type, decision, predicted, actual, confidence) in enumerate(assessment_scenarios, 1):
    print(f"Assessment {i}/8:")
    print(f"  Task: {task_type}, Decision: {decision}")
    print(f"  Predicted: {predicted} (confidence: {confidence:.1%})")
    print(f"  Actual: {actual}")

    assessment = planner.consciousness_metrics.assess_decision_quality(
        task_type=task_type,
        decision=decision,
        predicted_outcome=predicted,
        actual_outcome=actual,
        confidence=confidence
    )

    assessments.append(assessment)

    print(f"  Surprise: {assessment.surprise_after:.2f}")
    print(f"  Calibration error: {assessment.calibration_error:.2f}")

    if assessment.identified_biases:
        print(f"  Biases detected: {', '.join(assessment.identified_biases)}")

    if assessment.lessons_learned:
        print(f"  Lessons:")
        for lesson in assessment.lessons_learned:
            print(f"    - {lesson}")

    print()

print()
print("=" * 70)
print("[4/6] CONFIDENCE CALIBRATION ANALYSIS")
print("=" * 70)
print()

# Get calibration statistics
if planner.consciousness_metrics:
    calibration = planner.consciousness_metrics.get_confidence_calibration()

    print("Confidence Calibration:")
    print("-" * 70)
    print(f"  Samples: {calibration['num_samples']}")
    print(f"  Mean calibration error: {calibration['calibration_error']:.3f}")
    print(f"  Average confidence: {calibration['avg_confidence']:.3f}")
    print(f"  Average accuracy: {calibration['avg_accuracy']:.3f}")
    print()
    print(f"  Overconfidence: {calibration['overconfidence']:.3f}")
    print(f"  Underconfidence: {calibration['underconfidence']:.3f}")
    print()

    # Interpretation
    if calibration['overconfidence'] > calibration['underconfidence'] + 0.1:
        print("  ⚠️  BIAS DETECTED: System tends to be OVERCONFIDENT")
        print("     (Confidence exceeds actual accuracy)")
    elif calibration['underconfidence'] > calibration['overconfidence'] + 0.1:
        print("  ⚠️  BIAS DETECTED: System tends to be UNDERCONFIDENT")
        print("     (Actual accuracy exceeds confidence)")
    else:
        print("  ✓ WELL-CALIBRATED: Confidence matches accuracy")

    print()

print()
print("=" * 70)
print("[5/6] INTROSPECTION")
print("=" * 70)
print()

# Track some "known unknowns" (epistemic humility)
print("Recording known unknowns (epistemic humility):")
print("-" * 70)

known_unknowns = [
    "quantum_computing_deployment",
    "neural_network_debugging",
    "distributed_consensus_algorithms",
    "quantum_computing_deployment",  # Repeated
    "blockchain_smart_contracts",
]

for unknown in known_unknowns:
    planner.consciousness_metrics.track_known_unknown(unknown)
    print(f"  Acknowledged: 'I don't know how to handle {unknown}'")

print()

# Perform introspection
print("\nIntrospection Report:")
print("-" * 70)

if planner.consciousness_metrics:
    introspection = planner.consciousness_metrics.introspect()

    if introspection['current_state']:
        cs = introspection['current_state']
        print(f"\nCurrent Cognitive State:")
        print(f"  Attention: {cs['attention_focus']}")
        print(f"  Memory load: {cs['memory_load']:.2f}")
        print(f"  Reasoning depth: {cs['reasoning_depth']}/3")
        print(f"  Uncertainty: {cs['uncertainty_level']:.2f}")

    print(f"\nSelf-Awareness:")
    print(f"  Known unknowns: {introspection['known_unknowns_count']}")

    if introspection['detected_biases']:
        print(f"\nDetected Biases:")
        for bias, count in introspection['detected_biases'].items():
            print(f"  {bias}: {count} occurrences")

    cal = introspection['confidence_calibration']
    print(f"\nConfidence Calibration:")
    print(f"  Calibration error: {cal['calibration_error']:.3f}")
    print(f"  Overconfidence: {cal['overconfidence']:.3f}")
    print(f"  Underconfidence: {cal['underconfidence']:.3f}")

    perf = introspection['recent_performance']
    print(f"\nRecent Performance (last {perf['num_tasks']} tasks):")
    print(f"  Accuracy: {perf['accuracy']:.1%}")
    print(f"  Avg surprise: {perf['avg_surprise']:.2f}")
    print(f"  Avg confidence: {perf['avg_confidence']:.2f}")

    print(f"\nCognitive Load: {introspection['cognitive_load']:.2f}")

print()

print()
print("=" * 70)
print("[6/6] CONSCIOUSNESS METRICS STATISTICS")
print("=" * 70)
print()

# Get comprehensive statistics
if planner.consciousness_metrics:
    stats = planner.consciousness_metrics.get_statistics()

    print("Overall Statistics:")
    print("-" * 70)
    print(f"  States tracked: {stats['total_states_tracked']}")
    print(f"  Assessments made: {stats['total_assessments']}")
    print(f"  Self-awareness events: {stats['self_awareness_events']}")
    print(f"  Known unknowns: {stats['known_unknowns']}")
    print()

    if stats['top_unknowns']:
        print("Top Known Unknowns (Epistemic Humility):")
        print("-" * 70)
        for unknown, count in stats['top_unknowns']:
            bar = '#' * (count * 5)
            print(f"  {unknown:35s}: {count} {bar}")
        print()

    if stats['detected_biases']:
        print("Bias Detection Summary:")
        print("-" * 70)
        for bias, count in stats['detected_biases'].items():
            bar = '#' * (count * 2)
            print(f"  {bias:25s}: {count:2d} {bar}")
        print()

    cal = stats['confidence_calibration']
    print("Confidence Calibration:")
    print("-" * 70)
    print(f"  Samples: {cal['num_samples']}")
    print(f"  Mean error: {cal['calibration_error']:.3f}")
    print(f"  Overconfidence: {cal['overconfidence']:.3f}")
    print(f"  Underconfidence: {cal['underconfidence']:.3f}")
    print()

print()
print("=" * 70)
print("PHASE 11 COMPLETE!")
print("=" * 70)
print()
print("ACHIEVEMENTS:")
print("  [X] Self-awareness through cognitive state tracking")
print("  [X] Confidence calibration (comparing confidence vs. accuracy)")
print("  [X] Bias detection (overconfidence, underconfidence)")
print("  [X] Meta-cognitive assessment of decisions")
print("  [X] Introspection and 'known unknowns' tracking")
print()
print("The brain now has CONSCIOUSNESS METRICS - self-awareness!")
print("It can monitor its own cognitive states, detect biases,")
print("calibrate confidence, and practice epistemic humility")
print("('knowing what it doesn't know').")
print()
print("Next: PHASE 12 - Multi-Brain Swarm (collaborative intelligence)")
print("=" * 70)
