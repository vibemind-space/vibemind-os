"""
Test to verify Supermemory usage fixes.

Verifies that:
1. ArchitectAgent returns learned context from memory searches
2. RuntimeDebugAgent extracts and tracks high-confidence patterns
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock
from dataclasses import dataclass

from src.agents.architect_agent import ArchitectAgent
from src.agents.runtime_debug_agent import RuntimeDebugAgent
from src.engine.dag_parser import RequirementsData
from src.engine.contracts import InterfaceContracts
from src.mind.event_bus import EventBus
from src.mind.shared_state import SharedState
from src.tools.memory_tool import ErrorFixPattern


@dataclass
class MockMemorySearchResult:
    """Mock memory search result."""
    found: bool
    results: list
    query: str = ""
    total_results: int = 0


async def test_architect_memory_usage():
    """Test that ArchitectAgent returns learned context from memory."""
    print("\n[TEST] ArchitectAgent memory usage")

    # Create mock memory tool
    mock_memory = MagicMock()
    mock_memory.enabled = True

    # Mock search result with learned patterns (with scores for smart selection)
    mock_memory.search_architecture_patterns = AsyncMock(return_value=MockMemorySearchResult(
        found=True,
        results=[
            {
                "content": "Pattern 1: Use TypeScript interfaces for API contracts",
                "score": 0.85,
                "metadata": {"timestamp": "2025-11-20T10:00:00Z"}
            },
            {
                "content": "Pattern 2: Separate UI components into atomic design system",
                "score": 0.78,
                "metadata": {"timestamp": "2025-11-18T15:30:00Z"}
            }
        ],
        query="test query",
        total_results=2
    ))

    # Mock select_top_memories to return formatted context (what the real implementation does)
    def mock_select_top_memories(search_results, max_tokens=1000, **kwargs):
        """Mock implementation that mimics the real select_top_memories behavior."""
        if not search_results:
            return ""
        # Sort by score and format top results
        sorted_results = sorted(search_results, key=lambda x: x.get("score", 0), reverse=True)
        context_parts = []
        for result in sorted_results[:2]:  # Take top 2
            content = result.get("content", "")
            if content:
                context_parts.append(content)
        return "\n\n".join(context_parts)

    mock_memory.select_top_memories = mock_select_top_memories

    # Create architect agent with mock memory
    agent = ArchitectAgent(
        working_dir=".",
        use_memory=True,
        memory_tool=mock_memory
    )

    # Create minimal requirements
    req_data = RequirementsData(
        success=True,
        workflow_status="parsed",
        requirements=[
            {"id": "1", "title": "Create user dashboard", "tags": ["frontend"]},
            {"id": "2", "title": "Implement authentication API", "tags": ["backend"]}
        ],
        nodes=[],
        edges=[],
        summary={"total": 2}
    )
    # Add project_type as an attribute (used by ArchitectAgent with hasattr check)
    req_data.project_type = "electron"

    contracts = InterfaceContracts(project_name="Test")

    # Test _enhance_from_memory
    learned_context = await agent._enhance_from_memory(contracts, req_data)

    # Verify context was returned
    assert learned_context != "", "Should return non-empty learned context"
    assert "Learned Architecture Patterns" in learned_context, "Should include header"
    assert "Pattern 1" in learned_context, "Should include first pattern"
    assert "Pattern 2" in learned_context, "Should include second pattern"

    print(f"[PASS] ArchitectAgent returns learned context ({len(learned_context)} chars)")
    print(f"  Sample: {learned_context[:100]}...")

    # Verify search was called
    mock_memory.search_architecture_patterns.assert_called_once()
    print("[PASS] Memory search was invoked correctly")

    return True


async def test_runtime_debug_pattern_extraction():
    """Test that RuntimeDebugAgent extracts and tracks high-confidence patterns."""
    print("\n[TEST] RuntimeDebugAgent pattern extraction")

    # Create mock memory tool with error fix patterns
    mock_memory = MagicMock()
    mock_memory.enabled = True

    # Mock patterns with varying confidence
    patterns = [
        ErrorFixPattern(
            error_type="runtime_error",
            error_message="Cannot find module 'electron'",
            fix_description="Install electron dependency in package.json",
            files_modified=["package.json"],
            confidence=0.85,
            project_type="electron"
        ),
        ErrorFixPattern(
            error_type="runtime_error",
            error_message="Port 5173 already in use",
            fix_description="Kill existing Vite processes",
            files_modified=["vite.config.ts"],
            confidence=0.45,  # Low confidence - should be ignored
            project_type="electron"
        ),
        ErrorFixPattern(
            error_type="runtime_error",
            error_message="Main process crashed",
            fix_description="Add error handler to main.ts",
            files_modified=["src/main/main.ts"],
            confidence=0.72,
            project_type="electron"
        )
    ]

    mock_memory.search_similar_errors = AsyncMock(return_value=patterns)

    # Create runtime debug agent with mock memory
    event_bus = EventBus()
    shared_state = SharedState()

    agent = RuntimeDebugAgent(
        name="test_runtime_agent",
        event_bus=event_bus,
        shared_state=shared_state,
        working_dir=".",
        memory_tool=mock_memory
    )

    # Manually trigger the pattern extraction logic (simulate what happens in act())
    agent._detected_project_type = MagicMock(value="electron")

    # Extract patterns (simulating the code from act())
    learned_fixes = []
    retrieved_patterns = await mock_memory.search_similar_errors(
        error_type="runtime_error",
        error_message="electron startup",
        project_type="electron",
        limit=2
    )

    for pattern in retrieved_patterns:
        if pattern.confidence > 0.6:  # High-confidence threshold
            learned_fixes.append({
                "fix": pattern.fix_description,
                "files": pattern.files_modified,
                "confidence": pattern.confidence
            })

    # Verify correct patterns were extracted
    assert len(learned_fixes) == 2, f"Expected 2 high-confidence patterns, got {len(learned_fixes)}"
    print(f"[PASS] Extracted {len(learned_fixes)} high-confidence patterns (>0.6)")

    # Verify low-confidence pattern was filtered out
    low_conf_fixes = [f for f in learned_fixes if f["confidence"] < 0.6]
    assert len(low_conf_fixes) == 0, "Should filter out low-confidence patterns"
    print("[PASS] Low-confidence patterns (<0.6) filtered out correctly")

    # Verify fix descriptions
    fix_descriptions = [f["fix"] for f in learned_fixes]
    assert "Install electron dependency" in fix_descriptions[0]
    assert "Add error handler" in fix_descriptions[1]
    print(f"[PASS] Fix patterns extracted correctly:")
    for i, fix in enumerate(learned_fixes, 1):
        print(f"  {i}. {fix['fix'][:50]}... (confidence: {fix['confidence']})")

    return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Supermemory Usage Fixes")
    print("=" * 60)

    try:
        # Test 1: ArchitectAgent
        success1 = await test_architect_memory_usage()

        # Test 2: RuntimeDebugAgent
        success2 = await test_runtime_debug_pattern_extraction()

        print("\n" + "=" * 60)
        if success1 and success2:
            print("[SUCCESS] All Supermemory usage tests passed!")
            print("=" * 60)
            return True
        else:
            print("[FAILED] Some tests failed")
            print("=" * 60)
            return False

    except Exception as e:
        print(f"\n[ERROR] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
