"""
Test script for Code Quality Agent.

Tests:
1. QualityReport document creation and serialization
2. CodeQualityAgent finding documentation gaps
3. CodeQualityAgent finding large files
4. Document flow: TestSpec -> CodeQualityAgent -> QualityReport -> Generator
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
    QualityReport,
    TestSpec,
    TestResults,
    TestCase,
    DocumentationTask,
    CleanupTask,
    RefactorTask,
)


async def test_quality_report_creation():
    """Test creating and serializing a QualityReport."""
    print("\n[1] Testing QualityReport creation...")

    report = QualityReport(
        id="quality_20251126_120000",
        timestamp=datetime.now(),
        source_agent="CodeQuality",
        responding_to="test_20251126_115500",
        documentation_tasks=[
            DocumentationTask(
                id="doc_001",
                task_type="readme",
                target_path="README.md",
                scope=["project root"],
                priority=1,
                description="Create project README",
            ),
            DocumentationTask(
                id="doc_002",
                task_type="jsdoc",
                target_path="src/",
                scope=["src/utils.ts", "src/helpers.ts"],
                priority=3,
                description="Add JSDoc to exported functions",
            ),
        ],
        cleanup_tasks=[
            CleanupTask(
                id="cleanup_001",
                file_path="src/old_utils.ts",
                reason="orphan_file",
                confidence=0.95,
                references_found=0,
                size_bytes=1024,
            ),
        ],
        refactor_tasks=[
            RefactorTask(
                id="refactor_001",
                file_path="src/components/App.tsx",
                reason="too_large",
                current_lines=3500,
                target_lines=500,
                suggested_splits=["app.types.ts", "app.utils.ts", "app.hooks.ts"],
                complexity_score=1.17,
                description="File has 3500 lines, consider splitting",
            ),
        ],
        total_files_analyzed=25,
        unused_files_found=1,
        large_files_found=1,
        documentation_gaps=2,
        requires_action=True,
    )

    # Test serialization
    data = report.to_dict()
    assert data["id"] == "quality_20251126_120000"
    assert data["type"] == "quality_report"
    assert data["requires_action"] == True
    assert len(data["documentation_tasks"]) == 2
    assert len(data["cleanup_tasks"]) == 1
    assert len(data["refactor_tasks"]) == 1
    print("   [OK] QualityReport created and serialized")

    # Test deserialization
    restored = QualityReport.from_dict(data)
    assert restored.id == report.id
    assert len(restored.documentation_tasks) == 2
    assert restored.documentation_tasks[0].task_type == "readme"
    assert restored.cleanup_tasks[0].confidence == 0.95
    assert restored.refactor_tasks[0].current_lines == 3500
    print("   [OK] QualityReport deserialized correctly")

    return report


async def test_document_registry_flow():
    """Test the full document flow through the registry."""
    print("\n[2] Testing document registry flow...")

    output_dir = "output_quality_test"
    registry = DocumentRegistry(output_dir)

    # 1. Create a TestSpec (simulating TesterTeamAgent)
    test_spec = TestSpec(
        id="test_20251126_120000",
        timestamp=datetime.now(),
        source_agent="TesterTeam",
        responding_to="impl_20251126_115500",
        test_cases=[
            TestCase(
                id="tc_001",
                name="App renders correctly",
                description="Verify app loads without errors",
                test_type="e2e",
                priority=1,
                steps=["Navigate to app", "Check no errors"],
                expected_result="App loads successfully",
            ),
        ],
        coverage_targets=["src/App.tsx"],
        results=TestResults(
            total=1,
            passed=1,
            failed=0,
            skipped=0,
            duration_seconds=2.5,
        ),
        executed_at=datetime.now(),
    )

    test_id = await registry.write_document(test_spec, priority=3)
    print(f"   [OK] TestSpec written: {test_id}")

    # 2. Check pending documents for CodeQuality
    pending = await registry.get_pending_for_agent("CodeQuality")
    assert len(pending) == 1
    assert pending[0].id == test_id
    print(f"   [OK] Found {len(pending)} pending document(s) for CodeQuality")

    # 3. Mark as consumed and create QualityReport (simulating CodeQualityAgent)
    await registry.mark_consumed(test_id, "CodeQuality")

    quality_report = QualityReport(
        id="quality_20251126_120100",
        timestamp=datetime.now(),
        source_agent="CodeQuality",
        responding_to=test_id,
        documentation_tasks=[
            DocumentationTask(
                id="doc_001",
                task_type="claudemd",
                target_path="CLAUDE.md",
                priority=1,
                description="Create CLAUDE.md for AI guidance",
            ),
        ],
        cleanup_tasks=[],
        refactor_tasks=[],
        total_files_analyzed=10,
        documentation_gaps=1,
        requires_action=True,
    )

    quality_id = await registry.write_document(quality_report, priority=3)
    print(f"   [OK] QualityReport written: {quality_id}")

    # 4. Check pending documents for Generator
    pending = await registry.get_pending_for_agent("Generator")
    # Should include the quality report
    quality_pending = [p for p in pending if isinstance(p, QualityReport)]
    assert len(quality_pending) >= 1
    print(f"   [OK] Found {len(quality_pending)} QualityReport(s) pending for Generator")

    # 5. Get document chain
    chain = await registry.get_document_chain(quality_id)
    print(f"   [OK] Document chain length: {len(chain)}")
    for doc in chain:
        print(f"       - {doc.id} ({doc.document_type.value})")

    # 6. Registry stats
    stats = registry.get_stats()
    print(f"   [OK] Registry stats: {stats['total_documents']} documents")
    print(f"       By type: {stats['by_type']}")

    return True


async def test_code_quality_agent_analysis():
    """Test CodeQualityAgent's analysis capabilities."""
    print("\n[3] Testing CodeQualityAgent analysis...")

    # Create a test project structure
    test_dir = Path("output_quality_test_project")
    test_dir.mkdir(exist_ok=True)

    # Create src directory
    src_dir = test_dir / "src"
    src_dir.mkdir(exist_ok=True)

    # Create a file without JSDoc
    utils_file = src_dir / "utils.ts"
    utils_file.write_text("""
export function calculateTotal(items: number[]): number {
    return items.reduce((sum, item) => sum + item, 0);
}

export class DataProcessor {
    process(data: string): string {
        return data.toUpperCase();
    }
}
""")

    # Create a large file (simulated)
    large_file = src_dir / "large_component.tsx"
    large_content = "// Large file simulation\n" + ("const x = 1;\n" * 3100)
    large_file.write_text(large_content)

    # Create an orphan file (not imported anywhere)
    orphan_file = src_dir / "orphan_helper.ts"
    orphan_file.write_text("export const unused = 'not imported anywhere';")

    # Create main entry point
    main_file = src_dir / "main.ts"
    main_file.write_text("""
import { calculateTotal } from './utils';
console.log(calculateTotal([1, 2, 3]));
""")

    print(f"   Created test project at {test_dir}")

    # Test the CodeQualityAgent
    from src.mind.event_bus import EventBus
    from src.mind.shared_state import SharedState
    from src.registry.document_registry import DocumentRegistry
    from src.agents.code_quality_agent import CodeQualityAgent

    event_bus = EventBus()
    shared_state = SharedState()
    registry = DocumentRegistry(str(test_dir))

    agent = CodeQualityAgent(
        name="CodeQuality",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=str(test_dir),
        document_registry=registry,
        max_file_lines=3000,  # Lower threshold for testing
    )

    # Test documentation gap detection
    doc_tasks = await agent._find_documentation_gaps()
    print(f"   [OK] Found {len(doc_tasks)} documentation tasks")
    for task in doc_tasks:
        print(f"       - {task.task_type}: {task.description[:50]}...")

    # Test large file detection
    refactor_tasks = await agent._find_large_files()
    print(f"   [OK] Found {len(refactor_tasks)} refactor tasks")
    for task in refactor_tasks:
        print(f"       - {task.file_path}: {task.current_lines} lines")

    # Test unused file detection (basic)
    cleanup_tasks = await agent._find_unused_files()
    print(f"   [OK] Found {len(cleanup_tasks)} cleanup tasks")
    for task in cleanup_tasks:
        print(f"       - {task.file_path}: {task.reason} (confidence: {task.confidence:.0%})")

    # Cleanup test files
    import shutil
    shutil.rmtree(test_dir, ignore_errors=True)
    print(f"   [OK] Cleaned up test project")

    return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Code Quality Agent Tests")
    print("=" * 60)

    try:
        # Test 1: QualityReport creation
        await test_quality_report_creation()

        # Test 2: Document registry flow
        await test_document_registry_flow()

        # Test 3: CodeQualityAgent analysis
        await test_code_quality_agent_analysis()

        print("\n" + "=" * 60)
        print("[OK] All Code Quality Agent tests passed!")
        print("=" * 60)

        # Cleanup
        import shutil
        shutil.rmtree("output_quality_test", ignore_errors=True)

        return True

    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
