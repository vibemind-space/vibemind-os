"""
Team Agent - Society of Mind Pattern for Handoff System

Base class for agents that run internal teams in parallel.
Wraps multiple sub-agents to appear as a single agent to the
handoff system, enabling Society of Mind patterns within the
sequential handoff backbone.

Key concepts:
- TeamAgent appears as single agent to AgentRuntime
- Internally runs multiple sub-agents in parallel
- Synthesizes results through configurable strategies
- Enables debate/consensus without changing handoff infrastructure
"""

import asyncio
import logging
from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base_agent import BaseHandoffAgent, AgentConfig
from .messages import UserTask, AgentResponse

logger = logging.getLogger(__name__)


class SynthesisStrategy(Enum):
    """Strategies for combining sub-agent results."""
    FIRST_SUCCESS = "first_success"      # Return first successful result
    MAJORITY_VOTE = "majority_vote"      # Most common result wins
    WEIGHTED_VOTE = "weighted_vote"      # Agents have different weights
    CONSENSUS = "consensus"              # All must agree
    DEBATE = "debate"                    # Agents discuss until agreement
    CUSTOM = "custom"                    # Use custom synthesizer function


@dataclass
class SubAgentResult:
    """Result from a sub-agent execution."""
    agent_name: str
    response: AgentResponse
    weight: float = 1.0
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamConfig(AgentConfig):
    """Configuration for team-based agents."""
    synthesis_strategy: SynthesisStrategy = SynthesisStrategy.FIRST_SUCCESS
    max_debate_rounds: int = 3
    parallel_execution: bool = True
    timeout_per_agent: float = 30.0


class TeamAgent(BaseHandoffAgent):
    """
    Base class for agents that run internal sub-agent teams.

    Society of Mind pattern: Multiple simple agents collaborate
    to produce emergent intelligent behavior.

    Usage:
        class PlanningTeam(TeamAgent):
            def __init__(self):
                super().__init__(TeamConfig(name="planning_team"))
                self.add_member(PlannerAgent(), weight=1.0)
                self.add_member(CriticAgent(), weight=0.8)

            async def _synthesize(self, results):
                # Combine planner proposal with critic feedback
                ...
    """

    def __init__(self, config: Optional[TeamConfig] = None):
        config = config or TeamConfig(name="team", description="Team agent")
        super().__init__(config)

        self.team_config = config
        self._members: List[Tuple[BaseHandoffAgent, float]] = []  # (agent, weight)
        self._custom_synthesizer: Optional[Callable] = None

    def add_member(self, agent: BaseHandoffAgent, weight: float = 1.0):
        """
        Add a sub-agent to the team.

        Args:
            agent: The sub-agent to add
            weight: Weight for voting/synthesis (higher = more influence)
        """
        self._members.append((agent, weight))
        logger.debug(f"Team {self.name}: Added member {agent.name} (weight={weight})")

    def set_synthesizer(self, func: Callable):
        """Set a custom synthesis function."""
        self._custom_synthesizer = func
        self.team_config.synthesis_strategy = SynthesisStrategy.CUSTOM

    @property
    def members(self) -> List[BaseHandoffAgent]:
        """Get list of member agents."""
        return [agent for agent, _ in self._members]

    def _register_default_tools(self):
        """Register delegate tools - teams typically return to orchestrator."""
        self.register_delegate_tool(
            name="return_to_orchestrator",
            target_agent="orchestrator",
            description="Return team result to orchestrator"
        )

    async def start(self):
        """Start the team and all sub-agents."""
        await super().start()
        for agent, _ in self._members:
            await agent.start()

    async def stop(self):
        """Stop the team and all sub-agents."""
        for agent, _ in self._members:
            await agent.stop()
        await super().stop()

    async def _process_task(self, task: UserTask) -> Any:
        """
        Process task by running sub-agents and synthesizing results.

        The team appears as a single agent to the handoff system,
        but internally runs multiple agents in parallel.
        """
        if not self._members:
            return {"success": False, "error": "Team has no members"}

        await self.report_progress(
            task, 10.0,
            f"Team {self.name}: Starting {len(self._members)} members"
        )

        # Run sub-agents
        if self.team_config.parallel_execution:
            results = await self._run_parallel(task)
        else:
            results = await self._run_sequential(task)

        await self.report_progress(
            task, 70.0,
            f"Team {self.name}: Synthesizing {len(results)} results"
        )

        # Synthesize results
        final_result = await self._apply_synthesis(results, task)

        await self.report_progress(task, 100.0, "Team complete")

        # Return to orchestrator with synthesized result
        task.context["team_result"] = final_result
        task.context["team_member_results"] = [
            {"agent": r.agent_name, "success": r.response.success}
            for r in results
        ]

        return final_result

    async def _run_parallel(self, task: UserTask) -> List[SubAgentResult]:
        """Run all sub-agents in parallel."""
        async def run_member(agent: BaseHandoffAgent, weight: float) -> SubAgentResult:
            start_time = asyncio.get_event_loop().time()
            try:
                # Create a copy of task context for each agent
                member_task = UserTask(
                    goal=task.goal,
                    context=task.context.copy(),
                    history=task.history.copy(),
                    session_id=task.session_id
                )

                response = await asyncio.wait_for(
                    agent.handle_task(member_task),
                    timeout=self.team_config.timeout_per_agent
                )

                return SubAgentResult(
                    agent_name=agent.name,
                    response=response,
                    weight=weight,
                    execution_time=asyncio.get_event_loop().time() - start_time
                )

            except asyncio.TimeoutError:
                return SubAgentResult(
                    agent_name=agent.name,
                    response=AgentResponse(
                        success=False,
                        error=f"Timeout after {self.team_config.timeout_per_agent}s"
                    ),
                    weight=weight,
                    execution_time=self.team_config.timeout_per_agent
                )
            except Exception as e:
                return SubAgentResult(
                    agent_name=agent.name,
                    response=AgentResponse(success=False, error=str(e)),
                    weight=weight,
                    execution_time=asyncio.get_event_loop().time() - start_time
                )

        # Run all members in parallel
        tasks = [run_member(agent, weight) for agent, weight in self._members]
        results = await asyncio.gather(*tasks)

        logger.info(
            f"Team {self.name}: Parallel execution complete - "
            f"{sum(1 for r in results if r.response.success)}/{len(results)} succeeded"
        )

        return list(results)

    async def _run_sequential(self, task: UserTask) -> List[SubAgentResult]:
        """Run sub-agents sequentially (for debate pattern)."""
        results = []

        for agent, weight in self._members:
            start_time = asyncio.get_event_loop().time()

            # Add previous results to context for debate
            task.context["previous_results"] = [
                {"agent": r.agent_name, "result": r.response.result}
                for r in results
            ]

            try:
                response = await asyncio.wait_for(
                    agent.handle_task(task),
                    timeout=self.team_config.timeout_per_agent
                )

                results.append(SubAgentResult(
                    agent_name=agent.name,
                    response=response,
                    weight=weight,
                    execution_time=asyncio.get_event_loop().time() - start_time
                ))

            except Exception as e:
                results.append(SubAgentResult(
                    agent_name=agent.name,
                    response=AgentResponse(success=False, error=str(e)),
                    weight=weight,
                    execution_time=asyncio.get_event_loop().time() - start_time
                ))

        return results

    async def _apply_synthesis(
        self,
        results: List[SubAgentResult],
        task: UserTask
    ) -> Dict[str, Any]:
        """Apply the configured synthesis strategy."""
        strategy = self.team_config.synthesis_strategy

        if strategy == SynthesisStrategy.FIRST_SUCCESS:
            return self._synthesize_first_success(results)

        elif strategy == SynthesisStrategy.MAJORITY_VOTE:
            return self._synthesize_majority(results)

        elif strategy == SynthesisStrategy.WEIGHTED_VOTE:
            return self._synthesize_weighted(results)

        elif strategy == SynthesisStrategy.CONSENSUS:
            return self._synthesize_consensus(results)

        elif strategy == SynthesisStrategy.DEBATE:
            return await self._synthesize_debate(results, task)

        elif strategy == SynthesisStrategy.CUSTOM:
            if self._custom_synthesizer:
                return await self._custom_synthesizer(results, task)
            return self._synthesize_first_success(results)

        else:
            return self._synthesize_first_success(results)

    def _synthesize_first_success(self, results: List[SubAgentResult]) -> Dict[str, Any]:
        """Return the first successful result."""
        for result in results:
            if result.response.success:
                return {
                    "success": True,
                    "result": result.response.result,
                    "source_agent": result.agent_name,
                    "strategy": "first_success"
                }

        # All failed - return aggregated errors
        errors = [f"{r.agent_name}: {r.response.error}" for r in results]
        return {
            "success": False,
            "error": f"All {len(results)} agents failed",
            "details": errors,
            "strategy": "first_success"
        }

    def _synthesize_majority(self, results: List[SubAgentResult]) -> Dict[str, Any]:
        """Return the most common result."""
        # Group by result (simplified - uses string representation)
        votes: Dict[str, List[SubAgentResult]] = {}

        for result in results:
            if result.response.success:
                key = str(result.response.result)
                if key not in votes:
                    votes[key] = []
                votes[key].append(result)

        if not votes:
            return {"success": False, "error": "No successful results to vote on"}

        # Find majority
        winner_key = max(votes.keys(), key=lambda k: len(votes[k]))
        winner_results = votes[winner_key]

        return {
            "success": True,
            "result": winner_results[0].response.result,
            "votes": len(winner_results),
            "total_voters": len(results),
            "source_agents": [r.agent_name for r in winner_results],
            "strategy": "majority_vote"
        }

    def _synthesize_weighted(self, results: List[SubAgentResult]) -> Dict[str, Any]:
        """Return result with highest weighted votes."""
        votes: Dict[str, float] = {}
        result_map: Dict[str, SubAgentResult] = {}

        for result in results:
            if result.response.success:
                key = str(result.response.result)
                if key not in votes:
                    votes[key] = 0
                    result_map[key] = result
                votes[key] += result.weight

        if not votes:
            return {"success": False, "error": "No successful results to vote on"}

        winner_key = max(votes.keys(), key=lambda k: votes[k])

        return {
            "success": True,
            "result": result_map[winner_key].response.result,
            "weighted_score": votes[winner_key],
            "source_agent": result_map[winner_key].agent_name,
            "strategy": "weighted_vote"
        }

    def _synthesize_consensus(self, results: List[SubAgentResult]) -> Dict[str, Any]:
        """Require all agents to agree."""
        successful = [r for r in results if r.response.success]

        if len(successful) < len(results):
            failed = [r.agent_name for r in results if not r.response.success]
            return {
                "success": False,
                "error": f"Consensus failed: {failed} did not succeed",
                "strategy": "consensus"
            }

        # Check if all results match
        first_result = str(successful[0].response.result)
        all_agree = all(str(r.response.result) == first_result for r in successful)

        if all_agree:
            return {
                "success": True,
                "result": successful[0].response.result,
                "consensus": True,
                "agreeing_agents": [r.agent_name for r in successful],
                "strategy": "consensus"
            }
        else:
            return {
                "success": False,
                "error": "Agents did not reach consensus",
                "disagreements": [
                    {"agent": r.agent_name, "result": r.response.result}
                    for r in successful
                ],
                "strategy": "consensus"
            }

    async def _synthesize_debate(
        self,
        results: List[SubAgentResult],
        task: UserTask
    ) -> Dict[str, Any]:
        """
        Run debate rounds until consensus or max rounds.

        This is the core Society of Mind pattern - agents discuss
        and refine their positions based on others' arguments.
        """
        current_round = 1
        max_rounds = self.team_config.max_debate_rounds

        while current_round <= max_rounds:
            # Check for consensus
            consensus = self._synthesize_consensus(results)
            if consensus.get("success"):
                consensus["debate_rounds"] = current_round
                return consensus

            logger.info(f"Team {self.name}: Debate round {current_round}/{max_rounds}")

            # Add debate context
            task.context["debate_round"] = current_round
            task.context["current_positions"] = [
                {"agent": r.agent_name, "position": r.response.result}
                for r in results if r.response.success
            ]

            # Re-run agents with debate context
            results = await self._run_sequential(task)
            current_round += 1

        # No consensus after max rounds - fall back to weighted vote
        logger.warning(f"Team {self.name}: No consensus after {max_rounds} rounds")
        fallback = self._synthesize_weighted(results)
        fallback["debate_rounds"] = max_rounds
        fallback["consensus_reached"] = False
        return fallback

    @abstractmethod
    async def _synthesize(self, results: List[SubAgentResult]) -> Dict[str, Any]:
        """
        Override this method to implement custom synthesis logic.

        Called when synthesis_strategy is CUSTOM and no synthesizer function is set.

        Args:
            results: List of results from all sub-agents

        Returns:
            Synthesized result dictionary
        """
        pass
