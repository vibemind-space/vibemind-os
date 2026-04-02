"""
PHASE 8 DEMO: Active Inference

Demonstrates:
1. Hypothesis generation for uncertain tasks
2. Uncertainty estimation (epistemic + aleatoric)
3. Question generation to reduce uncertainty
4. Bayesian updating with evidence
5. Information-seeking behavior
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
print("PHASE 8: ACTIVE INFERENCE DEMO")
print("=" * 70)
print()

# Initialize system with ALL cognitive features including active inference
print("[1/5] Initializing hierarchical planner with active inference...")
meta_router = MetaRouter(enable_hippocampus=True, seed=42)
planner_layer2 = ConversationPathPlanner(
    meta_router=meta_router,
    strategy_library=StrategyLibrary(),
    brain_monitor=BrainActivityMonitor()
)

# Train from sessions
session_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
planner_layer2.train_from_sessions(session_dir, limit=39)

# Create hierarchical planner with ALL 8 cognitive features
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
    enable_active_inference=True,  # NEW: Active Inference enabled!
    ask_threshold=0.7,  # Ask question if uncertainty > 0.7
    seed=42
)

print(f"   {planner}")
print(f"   Memory: ENABLED")
print(f"   Predictive Coding: ENABLED")
print(f"   Attention: ENABLED")
print(f"   Meta-Learning: ENABLED")
print(f"   Dream Mode: ENABLED")
print(f"   Neuromodulation: ENABLED")
print(f"   Temporal Memory: ENABLED")
print(f"   Active Inference: ENABLED")
print()

# Show initial state
if planner.active_inference:
    print("Initial Active Inference State:")
    print(f"  Ask threshold: {planner.active_inference.ask_threshold}")
    print(f"  Hypotheses generated: {planner.active_inference.total_hypotheses_generated}")
    print(f"  Questions asked: {planner.active_inference.total_questions_asked}")
    print()

print("[2/5] Running tasks with varying uncertainty...")
print("=" * 70)
print()

# Test scenarios with different uncertainty levels
task_scenarios = [
    # Low uncertainty: Clear task
    ("Deploy standard Docker container to production", "docker", "clear"),

    # Medium uncertainty: Ambiguous task
    ("Fix the system issue urgently", "unknown", "ambiguous"),

    # High uncertainty: Very vague task
    ("Do something with the files", "filesystem", "vague"),

    # Medium uncertainty: Multiple interpretations
    ("Review changes and update", "github", "ambiguous"),

    # Low uncertainty: Specific task
    ("List all running Docker containers", "docker", "clear"),

    # High uncertainty: Unknown domain
    ("Handle the quantum encryption module", "unknown", "vague"),
]

predictions = []

for i, (task, task_type, uncertainty_level) in enumerate(task_scenarios, 1):
    print(f"TASK {i}/6: '{task}' [{uncertainty_level} uncertainty]")
    print("-" * 70)

    # Make prediction
    prediction = planner.predict(task)
    predictions.append((task, prediction))

    # Show inference state
    if prediction.inference_state:
        inf_state = prediction.inference_state
        print(f"  [Active Inference]")
        print(f"    Hypotheses generated: {len(inf_state.hypotheses)}")
        print(f"    Total uncertainty: {inf_state.total_uncertainty:.3f}")
        print(f"    Should ask question: {inf_state.should_ask_question}")

        # Show best hypothesis
        if inf_state.best_hypothesis:
            best_hyp = inf_state.best_hypothesis
            print(f"\n    Best Hypothesis:")
            print(f"      ID: {best_hyp.hypothesis_id}")
            print(f"      Task type: {best_hyp.task_type}")
            print(f"      Decision: {best_hyp.decision_type}")
            print(f"      Probability: {best_hyp.posterior_probability:.3f}")
            print(f"      Epistemic uncertainty: {best_hyp.epistemic_uncertainty:.3f}")
            print(f"      Aleatoric uncertainty: {best_hyp.aleatoric_uncertainty:.3f}")

        # Show questions
        if inf_state.questions:
            print(f"\n    Questions generated: {len(inf_state.questions)}")
            for q in inf_state.questions[:2]:  # Show top 2
                print(f"      - {q.question_text}")
                print(f"        (Info gain: {q.expected_information_gain:.2f}, "
                      f"Type: {q.question_type})")

    # Extract decision
    decision = prediction.actionable_decision
    primary = decision.multi_target_decision['primary']

    print(f"\n  Decision: {primary['type']} (confidence: {prediction.confidence:.1%})")
    print()

print()
print("=" * 70)
print("[3/5] HYPOTHESIS ANALYSIS")
print("=" * 70)
print()

# Analyze hypotheses across all tasks
if planner.active_inference:
    ai = planner.active_inference

    print(f"Total hypotheses generated: {ai.total_hypotheses_generated}")
    print()

    # Show hypothesis distribution
    print("Hypothesis Distribution:")
    print("-" * 70)

    hypothesis_types = {}
    for hyp in ai.hypothesis_history:
        hyp_type = hyp.hypothesis_id.split('_')[0]
        if hyp_type not in hypothesis_types:
            hypothesis_types[hyp_type] = 0
        hypothesis_types[hyp_type] += 1

    for hyp_type, count in sorted(hypothesis_types.items(), key=lambda x: x[1], reverse=True):
        bar = '#' * int(count / 2)
        print(f"  {hyp_type:12s}: {count:3d} {bar}")
    print()

    # Average uncertainties
    print("Average Uncertainties:")
    print("-" * 70)

    avg_epistemic = np.mean([h.epistemic_uncertainty for h in ai.hypothesis_history])
    avg_aleatoric = np.mean([h.aleatoric_uncertainty for h in ai.hypothesis_history])
    avg_total = np.mean([h.total_uncertainty() for h in ai.hypothesis_history])

    print(f"  Epistemic (lack of knowledge): {avg_epistemic:.3f}")
    print(f"  Aleatoric (inherent randomness): {avg_aleatoric:.3f}")
    print(f"  Total: {avg_total:.3f}")
    print()

print()
print("=" * 70)
print("[4/5] QUESTION GENERATION ANALYSIS")
print("=" * 70)
print()

if planner.active_inference:
    ai = planner.active_inference

    print(f"Total questions generated: {len(ai.question_history)}")
    print()

    if ai.question_history:
        # Question types
        print("Question Types:")
        print("-" * 70)

        question_types = {}
        for q in ai.question_history:
            if q.question_type not in question_types:
                question_types[q.question_type] = 0
            question_types[q.question_type] += 1

        for q_type, count in sorted(question_types.items(), key=lambda x: x[1], reverse=True):
            bar = '#' * int(count * 5)
            print(f"  {q_type:15s}: {count:2d} {bar}")
        print()

        # Average information gain
        print("Information Gain Analysis:")
        print("-" * 70)

        avg_info_gain = np.mean([q.expected_information_gain for q in ai.question_history])
        avg_uncertainty_reduction = np.mean([q.uncertainty_reduction for q in ai.question_history])

        print(f"  Avg expected info gain: {avg_info_gain:.3f}")
        print(f"  Avg uncertainty reduction: {avg_uncertainty_reduction:.3f}")
        print()

        # Show top questions by information gain
        print("Top 5 Questions by Information Gain:")
        print("-" * 70)

        sorted_questions = sorted(
            ai.question_history,
            key=lambda q: q.expected_information_gain,
            reverse=True
        )

        for i, q in enumerate(sorted_questions[:5], 1):
            print(f"\n  {i}. {q.question_text}")
            print(f"     Info gain: {q.expected_information_gain:.2f}, "
                  f"Type: {q.question_type}")
    else:
        print("  No questions generated (all tasks had low uncertainty)")

print()
print()
print("=" * 70)
print("[5/5] UNCERTAINTY-DRIVEN BEHAVIOR")
print("=" * 70)
print()

print("Uncertainty vs. Question-Asking Behavior:")
print("-" * 70)
print()

# Analyze relationship between uncertainty and question-asking
for i, (task, prediction) in enumerate(predictions, 1):
    task_desc, task_type, uncertainty_level = task_scenarios[i-1]

    if prediction.inference_state:
        inf_state = prediction.inference_state
        uncertainty = inf_state.total_uncertainty
        should_ask = inf_state.should_ask_question

        status = "ASKED" if should_ask else "ACTED"
        print(f"Task {i} [{uncertainty_level:12s}]: Uncertainty={uncertainty:.3f} -> {status}")

print()
print()
print("=" * 70)
print("PHASE 8 COMPLETE!")
print("=" * 70)
print()
print("ACHIEVEMENTS:")
print("  [X] Hypothesis generation for ambiguous tasks")
print("  [X] Uncertainty estimation (epistemic + aleatoric)")
print("  [X] Question generation to reduce uncertainty")
print("  [X] Information gain calculation")
print("  [X] Uncertainty-driven question-asking behavior")
print()
print("The brain now has ACTIVE INFERENCE - generating hypotheses and asking questions!")
print("Multiple interpretations considered for each task")
print("Questions asked when uncertainty is high")
print("Bayesian updating with evidence")
print("Information-seeking behavior to reduce uncertainty")
print()
print("Next: PHASE 9 - Compositional Reasoning (creating novel tool sequences)")
print("=" * 70)
