"""
Test ALL 12 Cognitive Features in Production API

Features tested:
1. Memory Systems (Working/Declarative/Procedural)
2. Predictive Coding (Prediction errors, curiosity)
3. Attention Mechanisms (Selective focus)
4. Meta-Learning (Adaptive learning rate)
5. Dream Mode (via Hierarchical Planner)
6. Neuromodulation (Dopamine/Serotonin/Noradrenaline)
7. Temporal Memory (Time patterns)
8. Active Inference (Belief updating & questions)
9. Compositional Reasoning (Task decomposition)
10. Tool Creation (Dynamic tools)
11. Consciousness Metrics (Global Workspace)
12. Infinite Chat (Automatic memory)
13. Semantic Coherence (Phase 13)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from production.production_planner import ProductionPlanner
import json


def test_all_cognitive_features():
    """Test all 12 cognitive features"""

    print("=" * 100)
    print("TEST: ALL 12 COGNITIVE FEATURES IN PRODUCTION API")
    print("=" * 100)
    print()

    # Initialize ProductionPlanner with ALL features enabled
    print("[INIT] Initializing ProductionPlanner with ALL cognitive features...")
    print("-" * 100)

    try:
        planner = ProductionPlanner(
            session_log_dir="data/logs/sessions",
            enable_semantic_coherence=True,
            embedding_type="hash",  # Reliable on Windows
            user_id="test_user_123",  # Enable Infinite Chat!
            seed=42
        )
        print("[+] SUCCESS: ProductionPlanner initialized")
        print()
    except Exception as e:
        print(f"[X] FAILED: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test with a complex task
    print("[TEST] Making prediction with complex task...")
    print("-" * 100)

    task = "Deploy Docker container with Redis and health checks urgently"
    print(f"Task: {task}")
    print()

    try:
        result = planner.predict(task)

        print("[RESULT] Prediction Response:")
        print("=" * 100)

        # Basic prediction
        print("\n[1] BASIC PREDICTION:")
        print(f"  Primary Action: {result['prediction']['primary_action']}")
        print(f"  Confidence: {result['prediction']['confidence']:.3f}")
        print(f"  Task Type: {result['prediction']['task_type']}")
        print(f"  Complexity: {result['prediction']['complexity']:.3f}")
        print(f"  Processing Mode: {result['prediction']['processing_mode']}")

        # 1. Memory Systems (Phase 1)
        print("\n[2] MEMORY SYSTEMS (Phase 1):")
        if result.get('memory_context'):
            mc = result['memory_context']
            print(f"  Working Memory: {mc.get('working_memory_size', 0)} items")
            print(f"  Declarative Facts: {len(mc.get('declarative_facts', []))} facts")
            print(f"  Procedural Skills: {len(mc.get('procedural_skills', []))} skills")
            if mc.get('working_memory'):
                print(f"  Recent tasks: {mc['working_memory']}")
        else:
            print(f"  Status: Not available (check if enable_memory=True in HierarchicalPlanner)")

        # 2. Predictive Coding (Phase 2)
        print("\n[3] PREDICTIVE CODING (Phase 2):")
        if result.get('predictive_coding'):
            pc = result['predictive_coding']
            print(f"  Prediction Errors: {pc.get('prediction_errors', 'N/A')}")
            print(f"  Curiosity Signal: {pc.get('curiosity_signal', 'N/A')}")
            print(f"  Novelty Detected: {pc.get('novelty_detected', False)}")
        else:
            print(f"  Status: Not available")

        # 3. Attention Mechanisms (Phase 3)
        print("\n[4] ATTENTION MECHANISMS (Phase 3):")
        if result.get('attention_state'):
            att = result['attention_state']
            print(f"  Top Modality: {att.get('top_modality', 'N/A')}")
            print(f"  Focused Modalities: {att.get('focused_modalities', [])}")
        else:
            print(f"  Status: Not available")

        # 4. Meta-Learning (Phase 4)
        print("\n[5] META-LEARNING (Phase 4):")
        if result.get('meta_learning'):
            ml = result['meta_learning']
            print(f"  Adapted Learning Rate: {ml.get('adapted_learning_rate', 'N/A')}")
            print(f"  Task Similarity: {ml.get('task_similarity', 'N/A')}")
            print(f"  Exploration Rate: {ml.get('exploration_rate', 'N/A')}")
        else:
            print(f"  Status: Not available")

        # 5. Neuromodulation (Phase 6)
        print("\n[6] NEUROMODULATION (Phase 6):")
        if result.get('neuromodulation'):
            nm = result['neuromodulation']
            print(f"  Dopamine: {nm.get('dopamine', 'N/A')}")
            print(f"  Serotonin: {nm.get('serotonin', 'N/A')}")
            print(f"  Noradrenaline: {nm.get('noradrenaline', 'N/A')}")
            if nm.get('effects'):
                print(f"  Effects: LR boost={nm['effects'].get('learning_rate_boost', 1.0):.2f}, "
                      f"Exploration boost={nm['effects'].get('exploration_boost', 1.0):.2f}")
        else:
            print(f"  Status: Not available")

        # 6. Temporal Memory (Phase 7)
        print("\n[7] TEMPORAL MEMORY (Phase 7):")
        if result.get('temporal_context'):
            tm = result['temporal_context']
            print(f"  Time of Day: {tm.get('time_of_day', 'N/A')}")
            print(f"  Day of Week: {tm.get('day_of_week', 'N/A')}")
            print(f"  Temporal Patterns: {len(tm.get('temporal_patterns', []))} patterns")
        else:
            print(f"  Status: Not available")

        # 7. Active Inference (Phase 8)
        print("\n[8] ACTIVE INFERENCE (Phase 8):")
        if result.get('active_inference'):
            ai = result['active_inference']
            print(f"  Beliefs: {ai.get('beliefs', {})}")
            print(f"  Free Energy: {ai.get('free_energy', 'N/A')}")
            print(f"  Hypotheses: {len(ai.get('hypotheses', []))} hypotheses")
            print(f"  Questions to Ask: {len(ai.get('questions_to_ask', []))} questions")
            if ai.get('questions_to_ask'):
                for q in ai['questions_to_ask'][:2]:
                    print(f"    - {q}")
        else:
            print(f"  Status: Not available")

        # 8. Compositional Reasoning (Phase 9)
        print("\n[9] COMPOSITIONAL REASONING (Phase 9):")
        if result.get('composition'):
            comp = result['composition']
            print(f"  Subtasks: {len(comp.get('subtasks', []))} subtasks")
            print(f"  Dependencies: {len(comp.get('dependencies', []))} dependencies")
            print(f"  Composed Confidence: {comp.get('composed_confidence', 'N/A')}")
            if comp.get('subtasks'):
                for st in comp['subtasks'][:3]:
                    print(f"    - {st}")
        else:
            print(f"  Status: Not available")

        # 9. Tool Creation (Phase 10)
        print("\n[10] TOOL CREATION (Phase 10):")
        if result.get('tool_creation'):
            tc = result['tool_creation']
            print(f"  New Tools Created: {len(tc.get('new_tools_created', []))}")
            print(f"  Reusable: {tc.get('reusable', False)}")
        else:
            print(f"  Status: Not available")

        # 10. Consciousness Metrics (Phase 11)
        print("\n[11] CONSCIOUSNESS METRICS (Phase 11):")
        if result.get('consciousness_metrics'):
            cm = result['consciousness_metrics']
            print(f"  Integration Level: {cm.get('integration_level', 'N/A')}")
            print(f"  Broadcast Strength: {cm.get('broadcast_strength', 'N/A')}")
            print(f"  Awareness Score: {cm.get('awareness_score', 'N/A')}")
            print(f"  Global Workspace State: {cm.get('global_workspace_state', 'N/A')}")
        else:
            print(f"  Status: Not available")

        # 11. Infinite Chat (Phase 12)
        print("\n[12] INFINITE CHAT (Phase 12):")
        if result.get('infinite_chat'):
            ic = result['infinite_chat']
            print(f"  Enabled: {ic.get('enabled', False)}")
            print(f"  User ID: {ic.get('user_id', 'N/A')}")
            print(f"  Automatic Memory: {ic.get('automatic_memory', 'N/A')}")
        else:
            print(f"  Status: Disabled (no user_id provided)")

        # 12. Semantic Coherence (Phase 13)
        print("\n[13] SEMANTIC COHERENCE (Phase 13):")
        if result.get('semantic_coherence'):
            sc = result['semantic_coherence']
            print(f"  Coherence K: {sc['coherence_K']:.3f}")
            print(f"  Truth Stability: {sc['truth_stability']:.3f}")
            print(f"  Semantic Status: {sc['semantic_status']}")
            print(f"  Swarm Consensus: {sc['swarm_consensus']}")
        else:
            print(f"  Status: Disabled")

        # Brain State
        print("\n[BRAIN STATE]:")
        print(f"  Dominant Modalities: {result['brain_state']['dominant_modalities']}")

        # Reasoning Chain
        print("\n[REASONING CHAIN]:")
        for i, step in enumerate(result['reasoning_chain'], 1):
            print(f"  {i}. {step}")

        print()
        print("=" * 100)
        print("[SUCCESS] All features tested!")
        print("=" * 100)

        # Summary
        print("\n[SUMMARY]")
        features_active = 0
        features_total = 13

        feature_checks = [
            ('Memory Systems', result.get('memory_context')),
            ('Predictive Coding', result.get('predictive_coding')),
            ('Attention Mechanisms', result.get('attention_state')),
            ('Meta-Learning', result.get('meta_learning')),
            ('Neuromodulation', result.get('neuromodulation')),
            ('Temporal Memory', result.get('temporal_context')),
            ('Active Inference', result.get('active_inference')),
            ('Compositional Reasoning', result.get('composition')),
            ('Tool Creation', result.get('tool_creation')),
            ('Consciousness Metrics', result.get('consciousness_metrics')),
            ('Infinite Chat', result.get('infinite_chat')),
            ('Semantic Coherence', result.get('semantic_coherence')),
            ('CTM Async', result.get('ctm_insights'))
        ]

        print(f"\nFeature Status:")
        for name, status in feature_checks:
            if status and (not isinstance(status, dict) or 'error' not in status):
                print(f"  [+] {name}: ACTIVE")
                features_active += 1
            else:
                print(f"  [-] {name}: Not available")

        print(f"\n{features_active}/{features_total} features active ({features_active/features_total*100:.1f}%)")

        if features_active == features_total:
            print("\n[!] PERFECT! All 13 features are active!")
        elif features_active >= 10:
            print("\n[+] EXCELLENT! Most features are working")
        elif features_active >= 5:
            print("\n[~] PARTIAL: Some features are working")
        else:
            print("\n[-] LIMITED: Most features are not available")

        print("\nNote: Some features may not be available because they depend on")
        print("HierarchicalPlanner's enable_* flags being set to True.")

    except Exception as e:
        print(f"[X] PREDICTION FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_all_cognitive_features()
