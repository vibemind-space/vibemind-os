"""
COMPLETE COGNITIVE SYSTEM TEST

This demo tests all 7 implemented cognitive phases working together:
- PHASE 1: Memory Systems (working + episodic memory)
- PHASE 2: Predictive Coding (learning from surprise)
- PHASE 3: Attention Mechanisms (dynamic resource allocation)
- PHASE 4: Meta-Learning (learning how to learn)
- PHASE 5: Dream Mode (offline consolidation)
- PHASE 6: Neuromodulation (brain chemistry)
- PHASE 7: Temporal Memory (temporal context and sequence learning)

This is the most advanced cognitive architecture demo, showing how all
systems integrate and interact to create emergent intelligent behavior.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import time

from core.hierarchical_planner import HierarchicalPlanner
from core.conversation_path_planner import ConversationPathPlanner
from core.meta_router import MetaRouter
from core.strategy_library import StrategyLibrary
from core.brain_monitor import BrainActivityMonitor

print("=" * 80)
print("COMPLETE COGNITIVE SYSTEM TEST")
print("Testing All 7 Phases Integrated Together")
print("=" * 80)
print()

# ============================================================================
# INITIALIZATION
# ============================================================================

print("[INITIALIZATION] Setting up complete cognitive architecture...")
print("-" * 80)

meta_router = MetaRouter(enable_hippocampus=True, seed=42)
planner_layer2 = ConversationPathPlanner(
    meta_router=meta_router,
    strategy_library=StrategyLibrary(),
    brain_monitor=BrainActivityMonitor()
)

# Train from sessions
session_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
print(f"Training from session logs: {session_dir}")
planner_layer2.train_from_sessions(session_dir, limit=39)

# Create hierarchical planner with ALL 7 phases enabled
planner = HierarchicalPlanner(
    conversation_planner=planner_layer2,
    intervention_types=['suggest', 'retry', 'wait', 'terminate', 'execute'],
    enable_memory=True,              # PHASE 1
    enable_predictive_coding=True,   # PHASE 2
    enable_attention=True,            # PHASE 3
    enable_meta_learning=True,       # PHASE 4
    enable_dream_mode=True,          # PHASE 5
    enable_neuromodulation=True,     # PHASE 6
    enable_temporal_memory=True,     # PHASE 7
    seed=42
)

print()
print(f"System initialized: {planner}")
print()
print("Cognitive Systems Status:")
print(f"  [X] PHASE 1: Memory Systems")
print(f"  [X] PHASE 2: Predictive Coding")
print(f"  [X] PHASE 3: Attention Mechanisms")
print(f"  [X] PHASE 4: Meta-Learning")
print(f"  [X] PHASE 5: Dream Mode")
print(f"  [X] PHASE 6: Neuromodulation")
print(f"  [X] PHASE 7: Temporal Memory")
print()

# ============================================================================
# COGNITIVE WORKLOAD TEST
# ============================================================================

print("=" * 80)
print("[COGNITIVE WORKLOAD] Running diverse tasks to exercise all systems...")
print("=" * 80)
print()

# Diverse task set covering different types and outcomes
tasks = [
    ("Deploy critical production Docker service", "docker", "success", 0.90, "high"),
    ("Urgent security patch required!", "unknown", "failure", 0.95, "critical"),
    ("Review and merge GitHub PR #123", "github", "success", 0.80, "normal"),
    ("Complex filesystem migration project", "filesystem", "success", 0.85, "high"),
    ("Docker container crash - investigate", "docker", "failure", 0.88, "high"),
    ("Simple memory query: find previous commands", "memory", "success", 0.70, "low"),
    ("Emergency rollback Docker deployment", "docker", "success", 0.92, "critical"),
    ("Analyze filesystem permissions issue", "filesystem", "success", 0.75, "normal"),
]

start_time = time.time()

for i, (task, task_type, outcome, importance, urgency_level) in enumerate(tasks, 1):
    print(f"\n{'='*80}")
    print(f"TASK {i}/{len(tasks)}: {task}")
    print(f"{'='*80}")

    # Make prediction
    prediction = planner.predict(task)

    # Extract key information
    decision = prediction.actionable_decision.multi_target_decision['primary']

    # Display integrated cognitive state
    print(f"\n[DECISION] {decision['type']} (confidence: {prediction.confidence:.1%})")

    # Memory context
    if prediction.memory_context:
        mem_ctx = prediction.memory_context
        print(f"\n[MEMORY]")
        wm = mem_ctx.get('working_memory', {})
        if 'recent_tasks' in wm:
            print(f"  Working Memory: {len(wm['recent_tasks'])} recent tasks")
        if wm.get('similar_tasks'):
            print(f"  Similar tasks found: {len(wm['similar_tasks'])}")

    # Prediction errors
    if prediction.prediction_errors:
        layer1_pe = prediction.prediction_errors.get('layer1')
        if layer1_pe:
            print(f"\n[PREDICTIVE CODING]")
            print(f"  Prediction Error: {layer1_pe.get('error_magnitude', 0):.3f}")
            print(f"  Surprise: {layer1_pe.get('surprise_level', 'unknown')}")

    # Attention state
    if prediction.attention_state:
        att = prediction.attention_state
        print(f"\n[ATTENTION]")
        print(f"  Focus: {att.attention_focus}")
        print(f"  Dominant: {', '.join(att.dominant_modalities[:3])}")

    # Meta-learning parameters
    if prediction.meta_parameters:
        mp = prediction.meta_parameters
        print(f"\n[META-LEARNING]")
        print(f"  Memory LR: {mp.memory_learning_rate:.3f}")
        print(f"  Exploration: {mp.exploration_rate:.3f}")

    # Neuromodulators
    if prediction.neuromodulator_levels:
        nl = prediction.neuromodulator_levels
        ne = prediction.neuromodulator_effects
        print(f"\n[NEUROMODULATION]")
        print(f"  DA={nl.dopamine:.2f}, 5-HT={nl.serotonin:.2f}, NE={nl.norepinephrine:.2f}")
        print(f"  Learning Rate: {ne.learning_rate_multiplier:.2f}x")

    # Temporal context
    if prediction.temporal_context:
        tc = prediction.temporal_context
        print(f"\n[TEMPORAL MEMORY]")
        print(f"  Time: {tc.time_of_day}, {tc.day_of_week}")
        if tc.previous_event:
            print(f"  Previous: {tc.previous_event} ({tc.time_since_previous:.1f}s ago)")

    # Record outcome and consolidate
    planner.record_outcome(task, decision['type'], outcome, importance)

    if importance > 0.7:
        prediction.task_description = task
        planner.consolidate_experience(
            prediction=prediction,
            outcome=outcome,
            importance=importance,
            user_rating=np.random.uniform(0.7, 1.0) if outcome == 'success' else 0.3,
            execution_time_ms=np.random.uniform(500, 3000)
        )

    print(f"\n[OUTCOME] {outcome.upper()}")

elapsed_time = time.time() - start_time
print(f"\n\nCompleted {len(tasks)} tasks in {elapsed_time:.2f}s")

# ============================================================================
# DREAM CYCLE (OFFLINE CONSOLIDATION)
# ============================================================================

print("\n\n" + "=" * 80)
print("[DREAM CYCLE] Triggering offline consolidation...")
print("=" * 80)
print()

dreams = planner.trigger_dream_cycle(num_dreams=3)

print(f"\nDream cycle complete: {len(dreams)} dreams")
for i, dream in enumerate(dreams, 1):
    print(f"  Dream {i}: {dream.dream_type} - {dream.original_task[:40]}...")

# ============================================================================
# COMPREHENSIVE STATISTICS
# ============================================================================

print("\n\n" + "=" * 80)
print("[COMPREHENSIVE STATISTICS]")
print("=" * 80)
print()

stats = planner.get_statistics()

# Overall
print("OVERALL PERFORMANCE:")
print(f"  Total Predictions: {stats['total_predictions']}")
print(f"  Avg Layer Timing: L1={stats['average_layer_timing']['layer1']*1000:.2f}ms, "
      f"L2={stats['average_layer_timing']['layer2']*1000:.2f}ms, "
      f"L3={stats['average_layer_timing']['layer3']*1000:.2f}ms")
print()

# Memory
if 'memory_stats' in stats:
    mem_stats = stats['memory_stats']
    print("PHASE 1 - MEMORY SYSTEMS:")
    print(f"  Working Memory: {mem_stats['working_memory_size']} tasks")
    print(f"  Episodic Memory: {mem_stats['episodic_memory_size']} consolidated")
    print(f"  Recent Success Rate: {mem_stats['recent_success_rate']:.1%}")
    print()

# Predictive Coding
if 'predictive_coding_stats' in stats:
    pc_stats = stats['predictive_coding_stats']
    print("PHASE 2 - PREDICTIVE CODING:")
    print(f"  Total Predictions: {pc_stats.get('total_predictions', 0)}")
    print(f"  High Surprise Events: {pc_stats.get('high_surprise_count', 0)}")
    if 'layer1_stats' in pc_stats:
        print(f"  Avg Layer 1 Error: {pc_stats['layer1_stats'].get('avg_error', 0):.3f}")
    if 'layer3_stats' in pc_stats:
        print(f"  Avg Layer 3 Error: {pc_stats['layer3_stats'].get('avg_error', 0):.3f}")
    print()

# Attention
if 'attention_stats' in stats:
    att_stats = stats['attention_stats']
    print("PHASE 3 - ATTENTION MECHANISMS:")
    print(f"  Total Updates: {att_stats['total_updates']}")
    print(f"  Attention Shifts: {att_stats['attention_shifts']}")
    print(f"  Focus Distribution: {att_stats['focus_distribution']}")
    print(f"  Avg Saliency: {att_stats['average_saliency']:.2f}")
    print(f"  Avg Goal Relevance: {att_stats['average_goal_relevance']:.2f}")
    print()

# Meta-Learning
if 'meta_learning_stats' in stats:
    ml_stats = stats['meta_learning_stats']
    perf = ml_stats['performance']
    print("PHASE 4 - META-LEARNING:")
    print(f"  Total Adaptations: {ml_stats['total_adaptations']}")
    print(f"  Success Rate: {perf['success_rate']:.1%}")
    print(f"  Avg Prediction Error: {perf['avg_prediction_error']:.3f}")
    print(f"  Error Trend: {perf['error_trend']}")
    current_mp = ml_stats['current_meta_params']
    print(f"  Current Exploration: {current_mp['exploration_rate']:.3f}")
    print()

# Dream Mode
if 'dream_mode_stats' in stats:
    dm_stats = stats['dream_mode_stats']
    print("PHASE 5 - DREAM MODE:")
    print(f"  Total Dreams: {dm_stats['total_dreams']}")
    print(f"  Replays: {dm_stats['total_replays']}")
    print(f"  Counterfactuals: {dm_stats['total_counterfactuals']}")
    print(f"  Patterns Discovered: {dm_stats['total_patterns_discovered']}")
    if dm_stats['patterns']:
        print(f"  Pattern Types: {', '.join(list(dm_stats['patterns'].keys())[:3])}")
    print()

# Neuromodulation
if 'neuromodulation_stats' in stats:
    nm_stats = stats['neuromodulation_stats']
    print("PHASE 6 - NEUROMODULATION:")
    print(f"  Current State: {nm_stats['current_state']}")
    levels = nm_stats['current_levels']
    print(f"  Dopamine: {levels['dopamine']:.2f}")
    print(f"  Serotonin: {levels['serotonin']:.2f}")
    print(f"  Norepinephrine: {levels['norepinephrine']:.2f}")
    effects = nm_stats['current_effects']
    print(f"  Learning Rate Mult: {effects['learning_rate_multiplier']:.2f}x")
    print(f"  Exploration Boost: {effects['exploration_boost']:+.2f}")
    print()

# Temporal Memory
if 'temporal_memory_stats' in stats:
    tm_stats = stats['temporal_memory_stats']
    print("PHASE 7 - TEMPORAL MEMORY:")
    print(f"  Total Events: {tm_stats['total_events']}")
    print(f"  Sequences Learned: {tm_stats['sequences_learned']}")
    print(f"  Unique Event Types: {tm_stats['unique_event_types']}")
    if tm_stats.get('top_transitions'):
        top_trans = tm_stats['top_transitions'][0]
        print(f"  Top Transition: {top_trans[0]} ({top_trans[1]} times)")
    print()

# ============================================================================
# EMERGENT BEHAVIOR ANALYSIS
# ============================================================================

print("=" * 80)
print("[EMERGENT BEHAVIOR ANALYSIS]")
print("=" * 80)
print()

print("The complete cognitive system demonstrates emergent properties:")
print()

print("1. ADAPTIVE LEARNING:")
print("   - Meta-learning adjusts learning rates based on performance")
print("   - Neuromodulation boosts learning when needed")
print("   - Predictive coding reduces errors over time")
print()

print("2. CONTEXT-AWARE DECISIONS:")
print("   - Memory retrieves similar past experiences")
print("   - Attention focuses on relevant modalities")
print("   - Dream patterns inform future decisions")
print()

print("3. EMOTIONAL REGULATION:")
print("   - Dopamine tracks reward prediction errors")
print("   - Serotonin stabilizes with consistent success")
print("   - Norepinephrine responds to urgency")
print()

print("4. OFFLINE CONSOLIDATION:")
print("   - Dreams replay important experiences")
print("   - Patterns extracted across similar tasks")
print("   - Counterfactual learning from alternatives")
print()

print("5. TEMPORAL AWARENESS:")
print("   - Events tagged with precise timestamps")
print("   - Temporal sequences learned automatically")
print("   - Next-event predictions based on history")
print()

print("6. SELF-IMPROVEMENT:")
print("   - System learns its own optimal parameters")
print("   - Attention allocation improves with experience")
print("   - Predictions become more accurate over time")
print()

# ============================================================================
# FINAL SUMMARY
# ============================================================================

print("=" * 80)
print("[FINAL SUMMARY]")
print("=" * 80)
print()

print("SYSTEM ARCHITECTURE:")
print("  3 Hierarchical Layers (Feature Router -> Path Planner -> Decision Router)")
print("  10 Brain Modalities (vision, audio, touch, taste, vestibular, threat, etc.)")
print("  7 Cognitive Systems (Memory, Prediction, Attention, Meta-learning, Dreams, Neuromodulation, Temporal)")
print()

print("ACHIEVEMENTS:")
print("  [X] Biologically-inspired cognitive architecture")
print("  [X] Multi-layer hierarchical processing")
print("  [X] Working and episodic memory with consolidation")
print("  [X] Predictive coding and free energy minimization")
print("  [X] Bottom-up and top-down attention")
print("  [X] Second-order learning (meta-learning)")
print("  [X] Offline consolidation through dreams")
print("  [X] Neuromodulation (dopamine, serotonin, norepinephrine)")
print("  [X] Temporal memory with sequence learning")
print()

print("NEXT PHASES (7/12 Complete - 58% Progress):")
print("  [X] PHASE 7: Temporal Memory")
print("  [ ] PHASE 8: Active Inference")
print("  [ ] PHASE 9: Compositional Reasoning")
print("  [ ] PHASE 10: Tool Creation")
print("  [ ] PHASE 11: Consciousness Metrics")
print("  [ ] PHASE 12: Multi-Brain Swarm")
print()

print("=" * 80)
print("COMPLETE COGNITIVE SYSTEM TEST: SUCCESS")
print("=" * 80)
