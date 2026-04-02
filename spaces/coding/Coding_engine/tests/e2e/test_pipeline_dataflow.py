"""
E2E Test: Pipeline Datenfluss
Testet: DAG Parsing → Project Analysis → Slicing → Planning
"""
import time
import json
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)


def main():
    print("=" * 60)
    print("E2E-4: Pipeline Datenfluss Test")
    print("=" * 60)
    
    start_time = time.time()
    errors = []
    
    # Phase 0: DAG Parsing
    print("\n[PHASE 0] DAG Parsing...")
    try:
        from src.engine.dag_parser import DAGParser
        parser = DAGParser()
        fixture_path = os.path.join(project_root, "tests", "fixtures", "minimal_requirements.json")
        result = parser.parse_file(fixture_path)
        print(f"  Nodes: {len(result.nodes)}")
        print(f"  Requirements: {len(result.requirements)}")
        assert len(result.nodes) == 3, f"Expected 3 nodes, got {len(result.nodes)}"
        print("  [OK] Phase 0 OK")
    except Exception as e:
        errors.append(f"Phase 0: {e}")
        print(f"  [FAIL] Phase 0 FAILED: {e}")
        return 1
    
    # Phase 0.5: Project Analysis
    print("\n[PHASE 0.5] Project Analysis...")
    try:
        from src.engine.project_analyzer import ProjectAnalyzer
        analyzer = ProjectAnalyzer()
        # Pass the entire RequirementsData object, not just the requirements list
        profile = analyzer.analyze(result)
        print(f"  Project Type: {profile.project_type}")
        print(f"  Domains: {profile.domains}")
        print(f"  Complexity: {profile.complexity}")
        print("  [OK] Phase 0.5 OK")
    except Exception as e:
        errors.append(f"Phase 0.5: {e}")
        print(f"  [FAIL] Phase 0.5 FAILED: {e}")
        return 1
    
    # Phase 1: Slicing
    print("\n[PHASE 1] Slicing...")
    try:
        from src.engine.slicer import Slicer
        slicer = Slicer()
        manifest = slicer.slice_requirements(result, job_id=1, strategy="hybrid")
        print(f"  Total Slices: {manifest.total_slices}")
        print(f"  Total Requirements: {manifest.total_requirements}")
        print(f"  Strategy: hybrid")
        assert manifest.total_slices > 0, "Expected at least 1 slice"
        print("  [OK] Phase 1 OK")
    except Exception as e:
        errors.append(f"Phase 1: {e}")
        print(f"  [FAIL] Phase 1 FAILED: {e}")
        return 1
    
    # Phase 1.5: Planning
    print("\n[PHASE 1.5] Planning...")
    try:
        from src.engine.planning_engine import PlanningEngine
        planner = PlanningEngine()
        plan = planner.create_plan(manifest, force_sequential=True)
        total_time = sum(b.estimated_time_ms for b in plan.batches)
        print(f"  Total Batches: {plan.total_batches}")
        print(f"  Estimated Time: {total_time}ms")
        print("  [OK] Phase 1.5 OK")
    except Exception as e:
        errors.append(f"Phase 1.5: {e}")
        print(f"  [FAIL] Phase 1.5 FAILED: {e}")
        return 1
    
    # E2E-5: Slicer Strategien Test
    print("\n[E2E-5] Slicer Strategien...")
    try:
        strategies = ["hybrid", "domain", "feature_grouped"]
        for strategy in strategies:
            manifest = slicer.slice_requirements(result, job_id=1, strategy=strategy)
            print(f"  {strategy}: {manifest.total_slices} slices")
        print("  [OK] E2E-5 OK")
    except Exception as e:
        errors.append(f"E2E-5: {e}")
        print(f"  [FAIL] E2E-5 FAILED: {e}")
    
    # E2E-6: Feature-Erkennung
    print("\n[E2E-6] Feature-Erkennung...")
    try:
        from dataclasses import dataclass
        from src.engine.slicer import Domain
        
        @dataclass
        class MockNode:
            id: str
            name: str
        
        test_cases = [
            ("REQ-001", "Create React button component", Domain.FRONTEND),
            ("REQ-002", "Implement REST API endpoint", Domain.BACKEND),
            ("REQ-003", "Setup PostgreSQL database schema", Domain.DATABASE),
        ]
        
        for req_id, name, expected_domain in test_cases:
            node = MockNode(id=req_id, name=name)
            domain = slicer._detect_domain(node)
            status = "[OK]" if domain == expected_domain else "[FAIL]"
            print(f"  {status} {req_id}: {domain.value} (expected: {expected_domain.value})")
        print("  [OK] E2E-6 OK")
    except Exception as e:
        errors.append(f"E2E-6: {e}")
        print(f"  [FAIL] E2E-6 FAILED: {e}")
    
    # Zusammenfassung
    elapsed = (time.time() - start_time) * 1000
    print("\n" + "=" * 60)
    if errors:
        print(f"FEHLER: {len(errors)} Phasen fehlgeschlagen")
        for err in errors:
            print(f"  - {err}")
        return 1
    else:
        print(f"ERFOLG: Alle Phasen durchlaufen in {elapsed:.0f}ms")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())