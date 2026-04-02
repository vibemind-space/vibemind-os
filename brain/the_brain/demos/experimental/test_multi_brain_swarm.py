"""
PHASE 12 DEMO: Multi-Brain Swarm (FINAL PHASE!)

Demonstrates:
1. Multiple specialized brain instances
2. Task decomposition into subtasks
3. Consensus mechanisms (majority, weighted, expert)
4. Swarm intelligence metrics
5. Collaborative decision-making
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
print("PHASE 12: MULTI-BRAIN SWARM DEMO (FINAL PHASE!)")
print("=" * 70)
print()

# Initialize system with ALL 12 cognitive features
print("[1/7] Initializing hierarchical planner with multi-brain swarm...")
meta_router = MetaRouter(enable_hippocampus=True, seed=42)
planner_layer2 = ConversationPathPlanner(
    meta_router=meta_router,
    strategy_library=StrategyLibrary(),
    brain_monitor=BrainActivityMonitor()
)

# Train from sessions
session_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
planner_layer2.train_from_sessions(session_dir, limit=39)

# Create hierarchical planner with ALL 12 PHASES!
planner = HierarchicalPlanner(
    conversation_planner=planner_layer2,
    intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
    enable_memory=True,                     # PHASE 1
    enable_predictive_coding=True,          # PHASE 2
    enable_attention=True,                  # PHASE 3
    enable_meta_learning=True,              # PHASE 4
    enable_dream_mode=True,                 # PHASE 5
    enable_neuromodulation=True,            # PHASE 6
    enable_temporal_memory=True,            # PHASE 7
    enable_active_inference=True,           # PHASE 8
    enable_compositional_reasoning=True,    # PHASE 9
    enable_tool_creation=True,              # PHASE 10
    enable_consciousness_metrics=True,      # PHASE 11
    enable_multi_brain_swarm=True,          # PHASE 12 - FINAL!
    num_swarm_brains=5,
    seed=42
)

print(f"   {planner}")
print()
print("   ALL 12 COGNITIVE PHASES ENABLED:")
print("   [1] Memory Systems ✓")
print("   [2] Predictive Coding ✓")
print("   [3] Attention Mechanisms ✓")
print("   [4] Meta-Learning ✓")
print("   [5] Dream Mode ✓")
print("   [6] Neuromodulation ✓")
print("   [7] Temporal Memory ✓")
print("   [8] Active Inference ✓")
print("   [9] Compositional Reasoning ✓")
print("   [10] Tool Creation ✓")
print("   [11] Consciousness Metrics ✓")
print("   [12] Multi-Brain Swarm ✓")
print()

# Show swarm composition
if planner.multi_brain_swarm:
    print("Swarm Composition:")
    print("-" * 70)
    for brain_id, brain in planner.multi_brain_swarm.brains.items():
        print(f"  {brain.brain_name:40s} | Expertise: {brain.expertise_level:.2f}")
    print()

print("[2/7] Testing task decomposition...")
print("=" * 70)
print()

# Test task decomposition with varying complexity
test_tasks = [
    ("List Docker containers", "docker", 0.2),           # Simple
    ("Deploy application to production", "docker", 0.5),  # Medium
    ("Refactor and deploy microservices architecture", "docker", 0.9),  # Complex
]

print("Task Decomposition Results:")
print("-" * 70)
print()

for task, task_type, complexity in test_tasks:
    print(f"Task: '{task}'")
    print(f"  Complexity: {complexity:.1f}")

    subtasks = planner.multi_brain_swarm.decompose_task(
        task_description=task,
        task_type=task_type,
        complexity=complexity
    )

    print(f"  Subtasks: {len(subtasks)}")
    for subtask in subtasks:
        deps = f" (depends on: {', '.join(subtask.depends_on)})" if subtask.depends_on else ""
        print(f"    - {subtask.description}{deps}")

    print()

print()
print("[3/7] Testing subtask assignment...")
print("=" * 70)
print()

# Create a complex task and assign subtasks
complex_task = "Deploy multi-tier application with database migration"
subtasks = planner.multi_brain_swarm.decompose_task(
    task_description=complex_task,
    task_type="docker",
    complexity=0.8
)

print(f"Assigning {len(subtasks)} subtasks to specialized brains:")
print("-" * 70)
print()

for subtask in subtasks:
    assigned_brain = planner.multi_brain_swarm.assign_subtask_to_brain(subtask)

    if assigned_brain:
        expertise = assigned_brain.expertise_in_domain(subtask.domain)
        print(f"Subtask: {subtask.description[:50]}...")
        print(f"  Assigned to: {assigned_brain.brain_name}")
        print(f"  Domain expertise: {expertise:.2f}")
        print(f"  Brain load: {assigned_brain.current_load:.2f}")
        print()

print()
print("[4/7] Testing consensus mechanisms...")
print("=" * 70)
print()

# Run tasks through the planner (which will trigger swarm voting)
consensus_test_tasks = [
    ("Deploy urgent production hotfix", "docker"),
    ("Review and merge pull request", "github"),
    ("Clean up temporary files", "filesystem"),
    ("Diagnose network connectivity issue", "network"),
]

print("Swarm Consensus Results:")
print("-" * 70)
print()

predictions = []

for i, (task, task_type) in enumerate(consensus_test_tasks, 1):
    print(f"Task {i}/4: '{task}'")
    print("-" * 70)

    # Make prediction (triggers swarm voting)
    prediction = planner.predict(task)
    predictions.append((task, prediction))

    # Show swarm decision
    if prediction.swarm_decision:
        sd = prediction.swarm_decision
        print(f"  [Swarm Consensus]")
        print(f"    Mechanism: {sd.consensus_mechanism}")
        print(f"    Decision: {sd.consensus_decision}")
        print(f"    Confidence: {sd.consensus_confidence:.2f}")
        print(f"    Agreement: {sd.agreement_level:.1%}")
        print(f"    Participating: {len(sd.participating_brains)} brains")
        print()
        print(f"  Vote Distribution:")
        for decision, votes in sorted(sd.votes.items(), key=lambda x: x[1], reverse=True):
            bar = '#' * (votes * 3)
            print(f"    {decision:12s}: {votes} votes {bar}")

    # Compare with Layer 3 decision
    layer3_decision = prediction.actionable_decision.multi_target_decision['primary']['type']
    print(f"\n  Layer 3 Decision: {layer3_decision}")

    if prediction.swarm_decision:
        if sd.consensus_decision == layer3_decision:
            print(f"  ✓ Swarm agrees with Layer 3")
        else:
            print(f"  ⚠ Swarm disagrees (swarm: {sd.consensus_decision}, layer3: {layer3_decision})")

    print()

print()
print("=" * 70)
print("[5/7] BRAIN PERFORMANCE TRACKING")
print("=" * 70)
print()

# Simulate outcomes and track brain performance
print("Recording outcomes and updating brain expertise:")
print("-" * 70)
print()

# Simulate various outcomes
outcome_scenarios = [
    ("brain_0", "success", 0.85),
    ("brain_0", "success", 0.90),
    ("brain_1", "failure", 0.60),
    ("brain_1", "success", 0.75),
    ("brain_2", "success", 0.95),
    ("brain_2", "success", 0.88),
    ("brain_3", "failure", 0.50),
    ("brain_3", "failure", 0.45),
    ("brain_4", "success", 0.80),
]

for brain_id, outcome, confidence in outcome_scenarios:
    planner.multi_brain_swarm.record_brain_outcome(brain_id, outcome, confidence)

# Show updated brain states
print("Brain Performance After Outcomes:")
print("-" * 70)
for brain_id, brain in planner.multi_brain_swarm.brains.items():
    print(f"\n{brain.brain_name}:")
    print(f"  Tasks completed: {brain.tasks_completed}")
    print(f"  Success rate: {brain.success_rate():.1%}")
    print(f"  Avg confidence: {brain.avg_confidence:.2f}")
    print(f"  Expertise level: {brain.expertise_level:.2f}")

print()

print()
print("=" * 70)
print("[6/7] SWARM INTELLIGENCE METRICS")
print("=" * 70)
print()

# Get swarm intelligence metrics
if planner.multi_brain_swarm:
    metrics = planner.multi_brain_swarm.get_swarm_intelligence_metrics()

    print("Emergent Swarm Properties:")
    print("-" * 70)
    print(f"  Diversity (expertise variance): {metrics['diversity']:.3f}")
    print(f"  Average success rate: {metrics['avg_success_rate']:.1%}")
    print(f"  Load balance: {metrics['load_balance']:.3f}")
    print(f"  Average agreement: {metrics['avg_agreement']:.1%}")
    print(f"  Average consensus confidence: {metrics['avg_consensus_confidence']:.2f}")
    print(f"  Disagreement rate: {metrics['disagreement_rate']:.1%}")
    print()

    # Interpretation
    if metrics['diversity'] > 0.15:
        print("  ✓ Good diversity (specialized expertise)")
    else:
        print("  ⚠ Low diversity (brains too similar)")

    if metrics['load_balance'] > 0.8:
        print("  ✓ Well-balanced load distribution")
    else:
        print("  ⚠ Uneven load distribution")

    if metrics['avg_agreement'] > 0.7:
        print("  ✓ Strong consensus (brains usually agree)")
    elif metrics['avg_agreement'] < 0.4:
        print("  ⚠ Weak consensus (frequent disagreements)")
    else:
        print("  ~ Moderate consensus")

print()

print()
print("=" * 70)
print("[7/7] COMPLETE SYSTEM STATISTICS")
print("=" * 70)
print()

# Get comprehensive statistics from all 12 phases
stats = planner.get_statistics()

print("PHASE 1 - MEMORY SYSTEMS:")
if 'memory_stats' in stats:
    ms = stats['memory_stats']
    print(f"  Working memory: {ms['working_memory_size']} items")
    print(f"  Episodic memory: {ms['episodic_memory_size']} items")
    print(f"  Recent success rate: {ms['recent_success_rate']:.1%}")
print()

print("PHASE 2 - PREDICTIVE CODING:")
if 'predictive_coding_stats' in stats:
    pcs = stats['predictive_coding_stats']
    print(f"  Predictions made: {pcs['predictions_made']}")
    print(f"  Average PE: {pcs['average_prediction_error']:.3f}")
print()

print("PHASE 3 - ATTENTION:")
if 'attention_stats' in stats:
    ats = stats['attention_stats']
    print(f"  Attention updates: {ats['total_attention_updates']}")
    print(f"  Average entropy: {ats['avg_entropy']:.3f}")
print()

print("PHASE 4 - META-LEARNING:")
if 'meta_learning_stats' in stats:
    mls = stats['meta_learning_stats']
    print(f"  Adaptations: {mls['total_adaptations']}")
    print(f"  Success rate: {mls['success_rate']:.1%}")
print()

print("PHASE 5 - DREAM MODE:")
if 'dream_mode_stats' in stats:
    dms = stats['dream_mode_stats']
    print(f"  Dreams: {dms['total_dreams']}")
    print(f"  Patterns discovered: {dms['patterns_discovered']}")
print()

print("PHASE 6 - NEUROMODULATION:")
if 'neuromodulation_stats' in stats:
    nms = stats['neuromodulation_stats']
    print(f"  Updates: {nms['total_updates']}")
print()

print("PHASE 7 - TEMPORAL MEMORY:")
if 'temporal_memory_stats' in stats:
    tms = stats['temporal_memory_stats']
    print(f"  Events: {tms['total_events']}")
    print(f"  Sequences: {tms['sequences_learned']}")
print()

print("PHASE 8 - ACTIVE INFERENCE:")
if 'active_inference_stats' in stats:
    ais = stats['active_inference_stats']
    print(f"  Hypotheses: {ais['total_hypotheses_generated']}")
    print(f"  Questions: {ais['total_questions_asked']}")
print()

print("PHASE 9 - COMPOSITIONAL REASONING:")
if 'compositional_reasoning_stats' in stats:
    crs = stats['compositional_reasoning_stats']
    print(f"  Compositions: {crs['total_compositions']}")
    print(f"  Strategies: {crs['strategies_abstracted']}")
print()

print("PHASE 10 - TOOL CREATION:")
if 'tool_creation_stats' in stats:
    tcs = stats['tool_creation_stats']
    print(f"  Tools created: {tcs['total_tools_created']}")
    print(f"  Gaps identified: {tcs['total_gaps_identified']}")
print()

print("PHASE 11 - CONSCIOUSNESS METRICS:")
if 'consciousness_metrics_stats' in stats:
    cms = stats['consciousness_metrics_stats']
    print(f"  States tracked: {cms['total_states_tracked']}")
    print(f"  Assessments: {cms['total_assessments']}")
    print(f"  Known unknowns: {cms['known_unknowns']}")
print()

print("PHASE 12 - MULTI-BRAIN SWARM:")
if 'multi_brain_swarm_stats' in stats:
    mbs = stats['multi_brain_swarm_stats']
    print(f"  Brains: {mbs['num_brains']}")
    print(f"  Consensus reached: {mbs['total_consensus_reached']}")
    print(f"  Disagreements: {mbs['total_disagreements']}")
    print()
    print(f"  Consensus mechanisms:")
    for mechanism, count in mbs['consensus_mechanisms'].items():
        bar = '#' * (count * 2)
        print(f"    {mechanism:12s}: {count} {bar}")
    print()
    print(f"  Swarm intelligence:")
    si = mbs['swarm_intelligence']
    print(f"    Diversity: {si['diversity']:.3f}")
    print(f"    Success rate: {si['avg_success_rate']:.1%}")
    print(f"    Load balance: {si['load_balance']:.3f}")
    print(f"    Agreement: {si['avg_agreement']:.1%}")

print()
print()
print("=" * 70)
print("🎉 PHASE 12 COMPLETE - ALL 12 PHASES IMPLEMENTED! 🎉")
print("=" * 70)
print()
print("FINAL ACHIEVEMENTS:")
print("  [X] PHASE 1: Memory Systems")
print("  [X] PHASE 2: Predictive Coding")
print("  [X] PHASE 3: Attention Mechanisms")
print("  [X] PHASE 4: Meta-Learning")
print("  [X] PHASE 5: Dream Mode")
print("  [X] PHASE 6: Neuromodulation")
print("  [X] PHASE 7: Temporal Memory")
print("  [X] PHASE 8: Active Inference")
print("  [X] PHASE 9: Compositional Reasoning")
print("  [X] PHASE 10: Tool Creation")
print("  [X] PHASE 11: Consciousness Metrics")
print("  [X] PHASE 12: Multi-Brain Swarm")
print()
print("The cognitive architecture is now COMPLETE!")
print()
print("Key capabilities:")
print("  - Biological memory systems (working, episodic, semantic)")
print("  - Predictive processing and error minimization")
print("  - Dynamic attention allocation")
print("  - Learning to learn (meta-parameters)")
print("  - Offline consolidation (dreams)")
print("  - Neuromodulator-driven adaptation")
print("  - Temporal awareness and sequence learning")
print("  - Hypothesis generation and question asking")
print("  - Novel tool sequence composition")
print("  - Dynamic capability generation")
print("  - Self-awareness and meta-cognition")
print("  - Collaborative multi-brain intelligence")
print()
print("This is a COMPLETE cognitive system with 12 integrated phases,")
print("inspired by neuroscience and cognitive science research!")
print()
print("=" * 70)
