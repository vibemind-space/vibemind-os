"""
Test script for Document Registry System.

Tests the document flow:
1. Create DocumentRegistry
2. Write a DebugReport (simulating PlaywrightE2EAgent)
3. Read pending documents for Generator agent
4. Write ImplementationPlan (simulating GeneratorAgent)
5. Read pending documents for TesterTeam agent
6. Write TestSpec (simulating TesterTeamAgent)
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.registry import (
    DocumentRegistry,
    DocumentType,
    DocumentStatus,
    DebugReport,
    ImplementationPlan,
    TestSpec,
    VisualIssue,
    SuggestedFix,
    PlannedFix,
    FileChange,
    TestCase,
    TestResults,
)


async def test_document_registry():
    """Test the full document flow."""
    output_dir = "output_memory_test_fixed"
    registry = DocumentRegistry(output_dir)

    print("=" * 60)
    print("Document Registry Test")
    print("=" * 60)

    # 1. Create and write a DebugReport (from PlaywrightE2EAgent)
    print("\n[1] Creating DebugReport (PlaywrightE2EAgent -> Generator)...")

    debug_report = DebugReport(
        id=f"debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        timestamp=datetime.now(),
        screenshots=["screenshots/test_001.png"],
        visual_issues=[
            VisualIssue(
                severity="major",
                description="Button text is truncated on small screens",
                element=".primary-btn",
                expected="Full text visible",
                actual="Text is cut off",
            )
        ],
        console_errors=["TypeError: Cannot read property 'map' of undefined"],
        suggested_fixes=[
            SuggestedFix(
                id="fix_001",
                priority=1,
                description="Fix truncated button text with CSS ellipsis",
                file="src/components/Button.tsx",
                action="modify",
                code_hint="Use text-overflow: ellipsis and add title attribute",
            ),
            SuggestedFix(
                id="fix_002",
                priority=2,
                description="Fix undefined array error in component",
                file="src/App.tsx",
                action="modify",
                code_hint="Add null check before mapping array",
            ),
        ],
        priority_order=["fix_002", "fix_001"],
        affected_files=["src/components/Button.tsx", "src/App.tsx"],
        root_cause_hypothesis="State not initialized properly before render",
        readiness_score=60,
        test_url="http://localhost:5173",
    )

    doc_id = await registry.write_document(debug_report, priority=10)
    print(f"   [OK] DebugReport written: {doc_id}")

    # 2. Check pending documents for Generator
    print("\n[2] Checking pending documents for Generator agent...")
    pending = await registry.get_pending_for_agent("Generator")
    print(f"   Found {len(pending)} pending document(s)")
    for doc in pending:
        print(f"   - {doc.id} ({doc.document_type.value})")

    # 3. Read the debug report
    print("\n[3] Reading DebugReport...")
    read_doc = await registry.read_document(doc_id)
    if read_doc:
        print(f"   [OK] Successfully read document: {read_doc.id}")
        print(f"   - Visual issues: {len(read_doc.visual_issues)}")
        print(f"   - Console errors: {len(read_doc.console_errors)}")
        print(f"   - Suggested fixes: {len(read_doc.suggested_fixes)}")

    # 4. Mark as consumed by Generator
    print("\n[4] Marking DebugReport as consumed by Generator...")
    await registry.mark_consumed(doc_id, "Generator")
    print("   [OK] Marked as consumed")

    # 5. Create and write ImplementationPlan (from GeneratorAgent)
    print("\n[5] Creating ImplementationPlan (GeneratorAgent -> TesterTeam)...")

    impl_plan = ImplementationPlan(
        id=f"impl_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        timestamp=datetime.now(),
        responding_to=doc_id,
        fixes_planned=[
            PlannedFix(
                id="planned_001",
                description="Add null check to prevent undefined error",
                responding_to_fix_id="fix_002",
                approach="Add optional chaining and default empty array",
                estimated_complexity="low",
            ),
            PlannedFix(
                id="planned_002",
                description="Fix button text overflow",
                responding_to_fix_id="fix_001",
                approach="Add CSS for text-overflow: ellipsis",
                estimated_complexity="low",
            ),
        ],
        file_manifest={
            "src/App.tsx": FileChange(
                action="modified",
                lines_added=2,
                lines_removed=1,
                summary="Added null check for array mapping",
            ),
            "src/components/Button.tsx": FileChange(
                action="modified",
                lines_added=3,
                lines_removed=0,
                summary="Added text overflow handling",
            ),
        },
        test_focus_areas=["Button component", "App state initialization"],
        expected_outcomes=["No console errors", "Button text visible"],
        verification_steps=[
            "Check no TypeErrors in console",
            "Verify button text is not truncated",
        ],
        summary="Fixed 2 issues: null check for array and button text overflow",
        total_files_changed=2,
    )

    impl_id = await registry.write_document(impl_plan, priority=5)
    print(f"   [OK] ImplementationPlan written: {impl_id}")

    # 6. Check pending documents for TesterTeam
    print("\n[6] Checking pending documents for TesterTeam agent...")
    pending = await registry.get_pending_for_agent("TesterTeam")
    print(f"   Found {len(pending)} pending document(s)")
    for doc in pending:
        print(f"   - {doc.id} ({doc.document_type.value})")

    # 7. Mark as consumed and create TestSpec
    print("\n[7] Marking ImplementationPlan as consumed by TesterTeam...")
    await registry.mark_consumed(impl_id, "TesterTeam")
    print("   [OK] Marked as consumed")

    print("\n[8] Creating TestSpec (TesterTeamAgent)...")

    test_spec = TestSpec(
        id=f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        timestamp=datetime.now(),
        responding_to=impl_id,
        test_cases=[
            TestCase(
                id="tc_001",
                name="App renders without console errors",
                description="Verify app loads without TypeError",
                test_type="e2e",
                priority=1,
                steps=[
                    "Navigate to http://localhost:5173",
                    "Check console for errors",
                    "Verify no TypeErrors present",
                ],
                expected_result="No console errors",
            ),
            TestCase(
                id="tc_002",
                name="Button text is visible",
                description="Verify button text is not truncated",
                test_type="e2e",
                priority=2,
                steps=[
                    "Navigate to http://localhost:5173",
                    "Find .primary-btn element",
                    "Check text is fully visible",
                ],
                expected_result="Button text is readable",
                target_element=".primary-btn",
            ),
        ],
        coverage_targets=["src/App.tsx", "src/components/Button.tsx"],
        results=TestResults(
            total=2,
            passed=2,
            failed=0,
            skipped=0,
            duration_seconds=3.5,
        ),
        executed_at=datetime.now(),
    )

    test_id = await registry.write_document(test_spec, priority=3)
    print(f"   [OK] TestSpec written: {test_id}")

    # 8. Get document chain
    print("\n[9] Getting document chain from TestSpec...")
    chain = await registry.get_document_chain(test_id)
    print(f"   Chain length: {len(chain)} documents")
    for i, doc in enumerate(chain):
        print(f"   {i+1}. {doc.id} ({doc.document_type.value})")

    # 9. Registry stats
    print("\n[10] Registry Statistics:")
    stats = registry.get_stats()
    print(f"   Total documents: {stats['total_documents']}")
    print(f"   By type: {stats['by_type']}")
    print(f"   By status: {stats['by_status']}")

    print("\n" + "=" * 60)
    print("[OK] All Document Registry tests passed!")
    print("=" * 60)

    # Show where files were saved
    print(f"\nDocuments saved to: {Path(output_dir).absolute() / 'reports'}")

    return True


if __name__ == "__main__":
    asyncio.run(test_document_registry())
