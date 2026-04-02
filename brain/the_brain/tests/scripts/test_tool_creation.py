"""
PHASE 10 DEMO: Tool Creation

Demonstrates:
1. Capability gap identification from failures
2. Dynamic tool generation
3. Tool composition from existing tools
4. Tool usage tracking and evolution
5. Automatic deprecation of underperforming tools
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
print("PHASE 10: TOOL CREATION DEMO")
print("=" * 70)
print()

# Initialize system with ALL cognitive features including tool creation
print("[1/6] Initializing hierarchical planner with tool creation...")
meta_router = MetaRouter(enable_hippocampus=True, seed=42)
planner_layer2 = ConversationPathPlanner(
    meta_router=meta_router,
    strategy_library=StrategyLibrary(),
    brain_monitor=BrainActivityMonitor()
)

# Train from sessions
session_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
planner_layer2.train_from_sessions(session_dir, limit=39)

# Create hierarchical planner with ALL cognitive features
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
    enable_tool_creation=True,  # PHASE 10 enabled!
    seed=42
)

print(f"   {planner}")
print(f"   Tool Creation: ENABLED")
print()

# Show initial tool state
if planner.tool_creation:
    print("Initial Tool Library:")
    print("-" * 70)
    for tool_id, tool in planner.tool_creation.tools.items():
        print(f"  {tool.tool_name:30s} | {tool.tool_type:10s} | "
              f"Success: {tool.success_rate():.1%} | "
              f"Uses: {tool.usage_count}")
    print()

print("[2/6] Simulating task failures to identify capability gaps...")
print("=" * 70)
print()

# Simulate capability gaps from task failures
capability_gaps = [
    ("docker", "deploy_container", "auto_rollback", "Automatic rollback on failure"),
    ("docker", "deploy_container", "auto_rollback", "Automatic rollback on failure"),  # Frequency 2
    ("docker", "deploy_container", "auto_rollback", "Automatic rollback on failure"),  # Frequency 3 -> trigger

    ("github", "merge_pr", "conflict_resolver", "Automatic conflict resolution"),
    ("github", "merge_pr", "conflict_resolver", "Automatic conflict resolution"),  # Frequency 2

    ("filesystem", "organize_files", "smart_categorizer", "AI-based file categorization"),
    ("filesystem", "organize_files", "smart_categorizer", "AI-based file categorization"),  # Frequency 2
    ("filesystem", "organize_files", "smart_categorizer", "AI-based file categorization"),  # Frequency 3 -> trigger

    ("terminal", "run_command", "error_diagnostic", "Automatic error diagnosis"),
]

print("Identifying capability gaps from failures:")
print("-" * 70)

for i, (task_type, failed_action, capability, description) in enumerate(capability_gaps, 1):
    print(f"Gap {i}/9: {task_type} - {failed_action} -> needs '{capability}'")

    planner.tool_creation.identify_capability_gap(
        task_type=task_type,
        failed_action=failed_action,
        missing_capability=capability
    )

print()
print(f"Total gaps identified: {planner.tool_creation.total_gaps_identified}")
print()

print("[3/6] TOOL GENERATION RESULTS")
print("=" * 70)
print()

# Show generated tools
print("Updated Tool Library:")
print("-" * 70)
for tool_id, tool in planner.tool_creation.tools.items():
    if tool.tool_type in ['composed', 'generated']:
        print(f"\n  NEW: {tool.tool_name}")
        print(f"    Type: {tool.tool_type}")
        print(f"    Capabilities: {', '.join(tool.capabilities[:3])}")
        if tool.dependencies:
            print(f"    Dependencies: {len(tool.dependencies)} tools")
        print(f"    Created: {tool.creator}")

print()
print(f"Total tools created: {planner.tool_creation.total_tools_created}")
print(f"Successful generations: {planner.tool_creation.successful_tool_generations}")
print()

print("[4/6] Simulating tool usage...")
print("=" * 70)
print()

# Simulate tool usage
print("Recording tool usage and outcomes:")
print("-" * 70)

# Get some generated tool IDs
generated_tools = [t for t in planner.tool_creation.tools.values()
                  if t.tool_type in ['composed', 'generated']]

if generated_tools:
    # Use first generated tool multiple times
    tool = generated_tools[0]
    print(f"\nTesting: {tool.tool_name}")

    # Simulate usage with varying success
    outcomes = ['success'] * 7 + ['failure'] * 3  # 70% success rate

    for i, outcome in enumerate(outcomes, 1):
        execution_time = np.random.uniform(0.5, 2.0)
        planner.tool_creation.record_tool_usage(
            tool_id=tool.tool_id,
            outcome=outcome,
            execution_time=execution_time
        )

        if i % 3 == 0:
            print(f"  After {i} uses: Success rate = {tool.success_rate():.1%}, "
                  f"Avg time = {tool.avg_execution_time:.2f}s")

print()

# Use another tool with poor performance (for deprecation demo)
if len(generated_tools) > 1:
    poor_tool = generated_tools[1]
    print(f"\nTesting (poor performance): {poor_tool.tool_name}")

    # Simulate 100% failure for deprecation
    for i in range(12):
        planner.tool_creation.record_tool_usage(
            tool_id=poor_tool.tool_id,
            outcome='failure',
            execution_time=2.0
        )

    print(f"  After 12 uses: Success rate = {poor_tool.success_rate():.1%}")
    print(f"  Status: Tool may be deprecated due to poor performance")

print()

print("[5/6] TOOL RETRIEVAL AND RECOMMENDATIONS")
print("=" * 70)
print()

# Test tool retrieval for capabilities
test_capabilities = [
    'auto_rollback',
    'conflict_resolver',
    'smart_categorizer',
    'decide'  # Primitive capability
]

print("Finding best tools for capabilities:")
print("-" * 70)

for capability in test_capabilities:
    tool = planner.tool_creation.get_tool_for_capability(capability)
    if tool:
        print(f"\n  Capability: '{capability}'")
        print(f"    Best Tool: {tool.tool_name}")
        print(f"    Type: {tool.tool_type}")
        print(f"    Success Rate: {tool.success_rate():.1%}")
        print(f"    Usage Count: {tool.usage_count}")

        # Get improvement suggestions
        suggestions = planner.tool_creation.suggest_tool_improvements(tool.tool_id)
        if suggestions:
            print(f"    Suggestions:")
            for sugg in suggestions:
                print(f"      - {sugg}")
    else:
        print(f"\n  Capability: '{capability}' - No tool found")

print()

print("[6/6] TOOL CREATION STATISTICS")
print("=" * 70)
print()

# Get comprehensive statistics
if planner.tool_creation:
    stats = planner.tool_creation.get_statistics()

    print("Overall Statistics:")
    print("-" * 70)
    print(f"  Total Tools: {stats['total_tools']}")
    print(f"  Total Created: {stats['total_tools_created']}")
    print(f"  Successful Generations: {stats['successful_generations']}")
    print(f"  Deprecated Tools: {stats['deprecated_tools']}")
    print(f"  Average Success Rate: {stats['avg_tool_success_rate']:.1%}")
    print()

    print("Tool Types:")
    print("-" * 70)
    for tool_type, count in stats['tool_types'].items():
        bar = '#' * (count * 2)
        print(f"  {tool_type:12s}: {count:2d} {bar}")
    print()

    print("Capability Gaps:")
    print("-" * 70)
    print(f"  Total Identified: {stats['total_gaps_identified']}")
    print(f"  Significant (≥3): {stats['significant_gaps']}")
    print()

    if stats['top_capabilities']:
        print("Top Capabilities Used:")
        print("-" * 70)
        for capability, usage_count in stats['top_capabilities'][:5]:
            bar = '#' * (usage_count // 2)
            print(f"  {capability:20s}: {usage_count:3d} {bar}")
        print()

print()
print("=" * 70)
print("PHASE 10 COMPLETE!")
print("=" * 70)
print()
print("ACHIEVEMENTS:")
print("  [X] Capability gap identification from failures")
print("  [X] Dynamic tool generation (3 gap threshold)")
print("  [X] Tool composition from existing primitives")
print("  [X] Tool usage tracking and evolution")
print("  [X] Performance-based tool deprecation")
print()
print("The brain can now CREATE NEW TOOLS dynamically!")
print("When capability gaps are identified (from repeated failures),")
print("the system automatically generates or composes new tools.")
print("Tools are tracked, evolved, and deprecated based on performance.")
print()
print("Next: PHASE 11 - Consciousness Metrics (self-awareness and meta-cognition)")
print("=" * 70)
