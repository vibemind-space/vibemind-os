"""
Test Supermemory API Integration

This script validates:
1. API authentication
2. Store operation (POST /documents)
3. Search operation (GET /documents/search)
4. Error handling
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.tools.memory_tool import MemoryTool
from src.config import get_settings


async def test_memory_api():
    """Test complete memory API flow."""
    print("=" * 70)
    print("SUPERMEMORY API VALIDATION TEST")
    print("=" * 70)

    # Load config
    settings = get_settings()
    print(f"\nConfiguration:")
    print(f"  Enabled: {settings.supermemory_enabled}")
    print(f"  API URL: {settings.supermemory_api_url}")
    print(f"  API Key: {'*' * 20 if settings.supermemory_api_key else 'NOT SET'}")
    print(f"  Container Tag: {settings.supermemory_container_tag}")

    if not settings.supermemory_api_key:
        print("\n[ERROR] SUPERMEMORY_API_KEY not set in environment")
        print("        Set it in .env file or environment variables")
        return False

    # Initialize memory tool
    print("\n" + "-" * 70)
    print("TEST 1: Initialize MemoryTool")
    print("-" * 70)

    try:
        memory_tool = MemoryTool(
            api_key=settings.supermemory_api_key,
            enabled=settings.supermemory_enabled,
            container_tag=settings.supermemory_container_tag
        )
        print(f"[OK] MemoryTool initialized")
        print(f"  Enabled: {memory_tool.enabled}")
        print(f"  Client initialized: {memory_tool.supermemory.client is not None}")
    except Exception as e:
        print(f"[FAIL] Failed to initialize: {e}")
        return False

    # Test storing a memory
    print("\n" + "-" * 70)
    print("TEST 2: Store Error Fix")
    print("-" * 70)

    try:
        store_result = await memory_tool.store_error_fix(
            error_type="test_error",
            error_message="Test TypeScript error for validation",
            fix_description="Applied fix by updating import statement",
            files_modified=["src/test.ts"],
            project_type="electron",
            project_name="test_project",
            iteration=1,
            success=True
        )

        if store_result.success:
            print(f"[OK] Memory stored successfully")
            print(f"  Memory ID: {store_result.memory_id}")
        else:
            print(f"[FAIL] Store failed: {store_result.error}")
            return False
    except Exception as e:
        print(f"[FAIL] Store exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test searching for similar errors
    print("\n" + "-" * 70)
    print("TEST 3: Search Similar Errors")
    print("-" * 70)

    try:
        patterns = await memory_tool.search_similar_errors(
            error_type="test_error",
            error_message="TypeScript error",
            project_type="electron",
            limit=5
        )

        print(f"[OK] Search completed")
        print(f"  Found {len(patterns)} patterns")

        if patterns:
            print(f"\n  Sample pattern:")
            pattern = patterns[0]
            print(f"    Error Type: {pattern.error_type}")
            print(f"    Fix: {pattern.fix_description[:100]}...")
            print(f"    Files: {', '.join(pattern.files_modified[:3])}")
            print(f"    Confidence: {pattern.confidence}")
        else:
            print(f"  (No patterns found - this is OK for first run)")

    except Exception as e:
        print(f"[FAIL] Search exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test storing test run
    print("\n" + "-" * 70)
    print("TEST 4: Store Test Run")
    print("-" * 70)

    try:
        test_result = await memory_tool.store_test_run(
            project_name="test_project",
            project_type="electron",
            test_framework="vitest",
            total_tests=10,
            passed=8,
            failed=2,
            execution_time_ms=1500,
            iteration=1,
            failure_details=[
                {"test_name": "test_auth", "error": "Assertion failed"},
                {"test_name": "test_render", "error": "Timeout"}
            ]
        )

        if test_result.success:
            print(f"[OK] Test run stored successfully")
            print(f"  Memory ID: {test_result.memory_id}")
        else:
            print(f"[FAIL] Store failed: {test_result.error}")
            return False
    except Exception as e:
        print(f"[FAIL] Store exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test storing convergence metrics
    print("\n" + "-" * 70)
    print("TEST 5: Store Convergence Metrics")
    print("-" * 70)

    try:
        conv_result = await memory_tool.store_convergence_metrics(
            project_name="test_project",
            iteration=1,
            confidence_score=0.75,
            test_pass_rate=0.8,
            build_success=True,
            validation_errors=2,
            type_errors=1,
            converged=False,
            blocking_reasons=["Test failures", "Type errors"]
        )

        if conv_result.success:
            print(f"[OK] Convergence metrics stored successfully")
            print(f"  Memory ID: {conv_result.memory_id}")
        else:
            print(f"[FAIL] Store failed: {conv_result.error}")
            return False
    except Exception as e:
        print(f"[FAIL] Store exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Close connections
    await memory_tool.close()

    print("\n" + "=" * 70)
    print("[OK] ALL TESTS PASSED")
    print("=" * 70)
    print("\nSupermemory integration is working correctly!")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_memory_api())
    sys.exit(0 if success else 1)
