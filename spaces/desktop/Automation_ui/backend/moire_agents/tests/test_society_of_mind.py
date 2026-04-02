"""
Test Society of Mind Pattern Integration

Tests the team-based agents that implement Society of Mind patterns:
- PlanningTeam: Planner + Critic debate for robust plans
- ValidationTeam: Parallel validators for confidence

Usage:
    python test_society_of_mind.py --test-planning
    python test_society_of_mind.py --test-validation
    python test_society_of_mind.py --test-all
"""

import asyncio
import argparse
import logging
import sys
import os
from typing import Any

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.handoff import (
    # Team infrastructure
    TeamAgent,
    TeamConfig,
    SynthesisStrategy,

    # Planning team
    PlanningTeam,
    PlannerAgent,
    CriticAgent,

    # Validation team
    ValidationTeam,
    ElementFinderAgent,
    ScreenStateValidator,
    ChangeDetector,

    # Messages
    UserTask
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_planning_team():
    """Test the PlanningTeam with Planner + Critic debate."""
    print("\n" + "=" * 60)
    print("PLANNING TEAM TEST")
    print("Society of Mind: Planner + Critic Debate")
    print("=" * 60)

    # Create planning team
    team = PlanningTeam(max_debate_rounds=2)
    await team.start()

    print(f"\nTeam: {team.name}")
    print(f"Members: {[m.name for m in team.members]}")
    print(f"Synthesis strategy: {team.team_config.synthesis_strategy.value}")

    # Test 1: Claude Desktop workflow
    print("\n" + "-" * 40)
    print("Test 1: Plan Claude Desktop workflow")
    print("-" * 40)

    result = await team.create_plan(
        goal="Send message to Claude Desktop",
        context={"message": "Hello from Society of Mind!"}
    )

    print(f"\nResult:")
    print(f"  Success: {result.get('success')}")
    print(f"  Approved: {result.get('approved')}")
    print(f"  Planner confidence: {result.get('planner_confidence', 0):.1%}")
    print(f"  Critic verdict: {result.get('critic_verdict')}")
    print(f"  Risk score: {result.get('risk_score', 0):.1%}")

    if result.get("issues"):
        print(f"\n  Issues found:")
        for issue in result["issues"]:
            print(f"    - {issue}")

    if result.get("suggestions"):
        print(f"\n  Suggestions:")
        for sug in result["suggestions"]:
            print(f"    - {sug}")

    print(f"\n  Plan ({len(result.get('plan', []))} steps):")
    for i, step in enumerate(result.get("plan", []), 1):
        print(f"    {i}. [{step.get('type')}] {step.get('description')}")
        if step.get('rationale'):
            print(f"       Rationale: {step.get('rationale')}")

    # Test 2: Unknown goal
    print("\n" + "-" * 40)
    print("Test 2: Plan for unknown goal")
    print("-" * 40)

    result2 = await team.create_plan(
        goal="Do something unusual",
        context={}
    )

    print(f"\nResult:")
    print(f"  Success: {result2.get('success')}")
    print(f"  Risk score: {result2.get('risk_score', 0):.1%}")
    print(f"  Issues: {result2.get('issues', [])}")

    await team.stop()

    print("\n" + "=" * 60)
    print("PLANNING TEAM TEST COMPLETE")
    print("=" * 60)


async def test_validation_team():
    """Test the ValidationTeam with parallel validators."""
    print("\n" + "=" * 60)
    print("VALIDATION TEAM TEST")
    print("Society of Mind: Parallel Validators")
    print("=" * 60)

    # Create validation team
    team = ValidationTeam(confidence_threshold=0.6)
    await team.start()

    print(f"\nTeam: {team.name}")
    print(f"Members: {[m.name for m in team.members]}")
    print(f"Synthesis strategy: {team.team_config.synthesis_strategy.value}")
    print(f"Parallel execution: {team.team_config.parallel_execution}")
    print(f"Confidence threshold: {team.confidence_threshold:.0%}")

    # Test 1: Find element
    print("\n" + "-" * 40)
    print("Test 1: Validate chat input element")
    print("-" * 40)

    result = await team.validate_element(
        target="chat input field",
        expected_state={"elements": [{"name": "input", "type": "text"}]}
    )

    print(f"\nResult:")
    print(f"  Valid: {result.get('valid')}")
    print(f"  Overall confidence: {result.get('overall_confidence', 0):.1%}")
    print(f"  Threshold: {result.get('threshold', 0):.0%}")
    print(f"  Validators succeeded: {result.get('validators_succeeded')}/{result.get('validators_total')}")

    if result.get("element_location"):
        loc = result["element_location"]
        print(f"  Element location: ({loc['x']}, {loc['y']})")

    if result.get("issues"):
        print(f"\n  Issues:")
        for issue in result["issues"]:
            print(f"    - {issue}")

    # Test 2: Validate action
    print("\n" + "-" * 40)
    print("Test 2: Validate action effect")
    print("-" * 40)

    before_state = {
        "text": ["Type a message..."],
        "elements": [{"id": "input", "type": "text"}]
    }

    after_state = {
        "text": ["Type a message...", "Hello!"],
        "elements": [{"id": "input", "type": "text"}, {"id": "msg1", "type": "message"}]
    }

    result2 = await team.validate_action(
        before_state=before_state,
        after_state=after_state,
        expected_change="text entered"
    )

    print(f"\nResult:")
    print(f"  Valid: {result2.get('valid')}")
    print(f"  Changes detected: {result2.get('changes_detected')}")
    print(f"  Overall confidence: {result2.get('overall_confidence', 0):.1%}")

    if result2.get("detailed_results"):
        print(f"\n  Detailed results:")
        for name, details in result2["detailed_results"].items():
            print(f"    {name}:")
            if isinstance(details, dict):
                for k, v in list(details.items())[:3]:
                    print(f"      {k}: {v}")

    await team.stop()

    print("\n" + "=" * 60)
    print("VALIDATION TEAM TEST COMPLETE")
    print("=" * 60)


async def test_synthesis_strategies():
    """Test different synthesis strategies."""
    print("\n" + "=" * 60)
    print("SYNTHESIS STRATEGIES TEST")
    print("=" * 60)

    # Create a simple test agent
    class SimpleAgent(PlannerAgent):
        def __init__(self, name: str, result_value: Any):
            super().__init__()
            self.config.name = name
            self._result_value = result_value

        async def _process_task(self, task):
            return {"value": self._result_value}

    # Create a concrete TeamAgent subclass for testing
    class TestTeam(TeamAgent):
        async def _synthesize(self, results):
            # Not used when strategy is not CUSTOM
            return {"success": True}

    # Test FIRST_SUCCESS
    print("\n" + "-" * 40)
    print("Strategy: FIRST_SUCCESS")
    print("-" * 40)

    team1 = TestTeam(TeamConfig(
        name="first_success_team",
        synthesis_strategy=SynthesisStrategy.FIRST_SUCCESS
    ))
    team1.add_member(SimpleAgent("agent1", "result_A"), weight=1.0)
    team1.add_member(SimpleAgent("agent2", "result_B"), weight=1.0)
    await team1.start()

    result = await team1._process_task(UserTask(goal="test"))
    print(f"Result: {result.get('result', {}).get('value')}")
    print(f"Source: {result.get('source_agent')}")
    await team1.stop()

    # Test MAJORITY_VOTE
    print("\n" + "-" * 40)
    print("Strategy: MAJORITY_VOTE")
    print("-" * 40)

    team2 = TestTeam(TeamConfig(
        name="majority_team",
        synthesis_strategy=SynthesisStrategy.MAJORITY_VOTE
    ))
    team2.add_member(SimpleAgent("agent1", "A"), weight=1.0)
    team2.add_member(SimpleAgent("agent2", "A"), weight=1.0)
    team2.add_member(SimpleAgent("agent3", "B"), weight=1.0)
    await team2.start()

    result2 = await team2._process_task(UserTask(goal="test"))
    print(f"Result: {result2.get('result', {}).get('value')}")
    print(f"Votes: {result2.get('votes')}/{result2.get('total_voters')}")
    await team2.stop()

    # Test WEIGHTED_VOTE
    print("\n" + "-" * 40)
    print("Strategy: WEIGHTED_VOTE")
    print("-" * 40)

    team3 = TestTeam(TeamConfig(
        name="weighted_team",
        synthesis_strategy=SynthesisStrategy.WEIGHTED_VOTE
    ))
    team3.add_member(SimpleAgent("expert", "expert_answer"), weight=2.0)
    team3.add_member(SimpleAgent("novice1", "wrong"), weight=0.5)
    team3.add_member(SimpleAgent("novice2", "wrong"), weight=0.5)
    await team3.start()

    result3 = await team3._process_task(UserTask(goal="test"))
    print(f"Result: {result3.get('result', {}).get('value')}")
    print(f"Weighted score: {result3.get('weighted_score')}")
    print(f"Source: {result3.get('source_agent')}")
    await team3.stop()

    print("\n" + "=" * 60)
    print("SYNTHESIS STRATEGIES TEST COMPLETE")
    print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description="Test Society of Mind Pattern")
    parser.add_argument("--test-planning", action="store_true",
                       help="Test PlanningTeam")
    parser.add_argument("--test-validation", action="store_true",
                       help="Test ValidationTeam")
    parser.add_argument("--test-synthesis", action="store_true",
                       help="Test synthesis strategies")
    parser.add_argument("--test-all", action="store_true",
                       help="Run all tests")

    args = parser.parse_args()

    if args.test_all or (not args.test_planning and not args.test_validation and not args.test_synthesis):
        await test_planning_team()
        await test_validation_team()
        await test_synthesis_strategies()
    else:
        if args.test_planning:
            await test_planning_team()
        if args.test_validation:
            await test_validation_team()
        if args.test_synthesis:
            await test_synthesis_strategies()


if __name__ == "__main__":
    asyncio.run(main())
