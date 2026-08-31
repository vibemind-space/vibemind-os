"""
Test script for GitHub MCP agent with OpenRouter integration.

Tests:
1. Simple task (should use gpt-4o-mini)
2. Complex task (should use gpt-4o)
3. Reasoning task (should use o1-mini)
"""
import asyncio
import sys
import os
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from agent import GitHubAgent


async def test_simple_task():
    """Test simple GitHub task - should use gpt-4o-mini."""
    print("\n" + "="*60)
    print("Test 1: Simple Task (List Repositories)")
    print("="*60)
    print("Expected model: gpt-4o-mini")

    agent = GitHubAgent()
    try:
        await agent.initialize()
        result = await agent.run_task(
            "List the 3 most starred Python repositories",
            correlation_id="test-simple"
        )
        print(f"✓ Task completed: {result.get('status')}")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        await agent.shutdown()


async def test_complex_task():
    """Test complex GitHub task - should use gpt-4o."""
    print("\n" + "="*60)
    print("Test 2: Complex Task (Code Review)")
    print("="*60)
    print("Expected model: gpt-4o")

    agent = GitHubAgent()
    try:
        await agent.initialize()
        result = await agent.run_task(
            "Review the latest pull request in the microsoft/vscode repository",
            correlation_id="test-complex"
        )
        print(f"✓ Task completed: {result.get('status')}")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        await agent.shutdown()


async def test_reasoning_task():
    """Test reasoning GitHub task - should use o1-mini with medium effort."""
    print("\n" + "="*60)
    print("Test 3: Reasoning Task (Architecture Analysis)")
    print("="*60)
    print("Expected model: o1-mini")
    print("Expected effort: medium")

    agent = GitHubAgent()
    try:
        await agent.initialize()
        result = await agent.run_task(
            "Analyze the architecture of the microsoft/vscode repository and suggest improvements",
            correlation_id="test-reasoning"
        )
        print(f"✓ Task completed: {result.get('status')}")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        await agent.shutdown()


async def test_high_reasoning_task():
    """Test high-complexity reasoning task - should use o1-mini with high effort."""
    print("\n" + "="*60)
    print("Test 4: High Reasoning Task (System Design)")
    print("="*60)
    print("Expected model: o1-mini")
    print("Expected effort: high")

    agent = GitHubAgent()
    try:
        await agent.initialize()
        result = await agent.run_task(
            "Design a microservices architecture for a GitHub-integrated CI/CD system",
            correlation_id="test-high-reasoning"
        )
        print(f"✓ Task completed: {result.get('status')}")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        await agent.shutdown()


async def main():
    """Run all GitHub agent tests."""
    print("\n" + "="*60)
    print("GitHub Agent OpenRouter Integration Tests")
    print("="*60)

    # Check OpenRouter API key
    if not os.getenv("OPENROUTER_API_KEY"):
        print("\n⚠️  Warning: OPENROUTER_API_KEY not set")
        print("Tests will use legacy configuration (OPENAI_API_KEY)")
    else:
        print("\n✓ OPENROUTER_API_KEY found")

    results = []

    # Run tests
    results.append(("Simple Task", await test_simple_task()))
    results.append(("Complex Task", await test_complex_task()))
    results.append(("Reasoning Task", await test_reasoning_task()))
    results.append(("High Reasoning Task", await test_high_reasoning_task()))

    # Print summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    print(f"\nPassed: {passed}/{total}")

    for name, success in results:
        status = "✓" if success else "✗"
        print(f"{status} {name}")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
