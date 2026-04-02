"""
IdeaTreeSearch - Best-First Tree Search for Idea Connection Discovery.

Adapted from AI-Scientist-v2's parallel_agent.py.
Implements BFTS algorithm to explore connections between ideas.
"""

from __future__ import annotations
import asyncio
import logging
from typing import Optional, List, Dict, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum

from .idea_node import IdeaNode, ConnectionType
from .idea_journal import IdeaJournal, ExplorationSession
from .connection_evaluator import ConnectionEvaluator, EvaluationResult

# Import clarification components (conditional to avoid circular imports)
try:
    from .exploration_clarification import (
        ExplorationClarificationAgent,
        ExplorationMode,
        InteractiveExplorationConfig,
    )
    HAS_CLARIFICATION = True
except ImportError:
    HAS_CLARIFICATION = False
    ExplorationClarificationAgent = None
    ExplorationMode = None
    InteractiveExplorationConfig = None

logger = logging.getLogger(__name__)


class ExplorationStage(Enum):
    """Exploration stages, adapted from AI-Scientist's AgentManager."""
    DIRECT = 1       # Direct connections (high embedding similarity)
    INDIRECT = 2     # Connections through intermediate concepts
    ABSTRACT = 3     # Thematic/abstract patterns
    CREATIVE = 4     # Novel, non-obvious connections


@dataclass
class ExplorationConfig:
    """Configuration for exploration."""
    # Stage limits
    stage1_max_nodes: int = 10   # Max nodes in stage 1
    stage2_max_nodes: int = 8    # Max nodes in stage 2
    stage3_max_nodes: int = 6    # Max nodes in stage 3
    stage4_max_nodes: int = 4    # Max nodes in stage 4

    # Search parameters
    num_workers: int = 3         # Parallel exploration paths
    min_score_threshold: float = 0.4  # Minimum score to keep a connection
    use_llm_for_top_k: int = 3   # Use LLM evaluation for top-k candidates

    # Timeouts
    stage_timeout_seconds: float = 60.0
    total_timeout_seconds: float = 300.0

    # Depth limits
    max_depth: int = 4           # Maximum exploration depth


class IdeaTreeSearch:
    """
    Best-First Tree Search for exploring idea connections.

    The search maintains a journal of discovered connections (nodes)
    and iteratively expands the best-scoring nodes to find more
    connections.

    Stages:
    1. DIRECT: Find bubbles with high embedding similarity
    2. INDIRECT: Explore connections through intermediate concepts
    3. ABSTRACT: Identify overarching themes and patterns
    4. CREATIVE: Propose creative, non-obvious connections
    """

    def __init__(
        self,
        evaluator: ConnectionEvaluator,
        config: Optional[ExplorationConfig] = None,
        on_node_discovered: Optional[Callable[[IdeaNode], Awaitable[None]]] = None,
        on_stage_complete: Optional[Callable[[ExplorationStage, List[IdeaNode]], Awaitable[None]]] = None,
        clarification_agent: Optional["ExplorationClarificationAgent"] = None,
        interactive_config: Optional["InteractiveExplorationConfig"] = None,
    ):
        """
        Initialize the tree search.

        Args:
            evaluator: ConnectionEvaluator for scoring connections
            config: Search configuration
            on_node_discovered: Callback when a new node is discovered
            on_stage_complete: Callback when a stage completes
            clarification_agent: Optional agent for human-in-the-loop interaction
            interactive_config: Configuration for interactive mode
        """
        self.evaluator = evaluator
        self.config = config or ExplorationConfig()
        self.on_node_discovered = on_node_discovered
        self.on_stage_complete = on_stage_complete

        # Human-in-the-loop components
        self.clarification_agent = clarification_agent
        self.interactive_config = interactive_config

        # State
        self.journal: Optional[IdeaJournal] = None
        self.current_stage = ExplorationStage.DIRECT
        self._is_running = False
        self._should_stop = False
        self._exploration_mode = ExplorationMode.AUTO if ExplorationMode else None

    async def explore(
        self,
        root_bubble: Dict[str, Any],
        all_bubbles: List[Dict[str, Any]],
        query: str = "",
        stages: Optional[List[ExplorationStage]] = None,
        mode: Optional["ExplorationMode"] = None,
    ) -> IdeaJournal:
        """
        Run the exploration from a root bubble.

        Args:
            root_bubble: Starting bubble dict with id, title, description, embedding_vector
            all_bubbles: All bubbles to explore connections with
            query: Optional user query/context
            stages: Optional list of stages to run (default: all 4)
            mode: Exploration mode (auto, interactive, guided)

        Returns:
            IdeaJournal with all discovered connections
        """
        self._is_running = True
        self._should_stop = False

        # Set exploration mode
        if mode and ExplorationMode:
            self._exploration_mode = mode
        elif self.interactive_config and ExplorationMode:
            self._exploration_mode = self.interactive_config.mode
        elif ExplorationMode:
            self._exploration_mode = ExplorationMode.AUTO

        # Initialize journal
        self.journal = IdeaJournal()
        self.journal.session = ExplorationSession(
            root_bubble_id=root_bubble.get("id", ""),
            root_bubble_title=root_bubble.get("title", ""),
            exploration_query=query,
            status="running",
            metadata={"mode": self._exploration_mode.value if self._exploration_mode else "auto"}
        )

        stages = stages or [
            ExplorationStage.DIRECT,
            ExplorationStage.INDIRECT,
            ExplorationStage.ABSTRACT,
            ExplorationStage.CREATIVE,
        ]

        try:
            # Filter out root bubble from candidates
            candidates = [b for b in all_bubbles if b.get("id") != root_bubble.get("id")]

            for stage in stages:
                if self._should_stop:
                    logger.info("Exploration stopped by user")
                    break

                self.current_stage = stage
                self.journal.session.current_stage = stage.value

                # Reset clarification agent counter for new stage
                if self.clarification_agent:
                    self.clarification_agent.reset_stage_counter()

                logger.info(f"Starting exploration stage: {stage.name}")

                stage_nodes = await self._run_stage_interactive(
                    stage, root_bubble, candidates
                )

                if self.on_stage_complete:
                    await self.on_stage_complete(stage, stage_nodes)

                # Update session stats
                if stage_nodes:
                    best_score = max(n.combined_score for n in stage_nodes)
                    if best_score > self.journal.session.best_score:
                        self.journal.session.best_score = best_score

                # Ask about continuing to next stage (in interactive mode)
                if self._should_ask_stage_complete(stage, stages):
                    continue_result = await self._ask_stage_complete(
                        stage, len(stage_nodes), best_score if stage_nodes else 0.0
                    )
                    if continue_result == "stop":
                        logger.info("User requested stop after stage")
                        break
                    elif continue_result == "show_results":
                        # User wants to see results - exploration continues but marks for display
                        self.journal.session.metadata["show_results_requested"] = True

            # Mark completed
            self.journal.session.status = "completed"
            import time
            self.journal.session.completed_at = time.time()

        except Exception as e:
            logger.error(f"Exploration error: {e}")
            self.journal.session.status = "error"
            self.journal.session.metadata["error"] = str(e)

        finally:
            self._is_running = False

        return self.journal

    async def _run_stage_interactive(
        self,
        stage: ExplorationStage,
        root_bubble: Dict[str, Any],
        candidates: List[Dict[str, Any]],
    ) -> List[IdeaNode]:
        """
        Run a single exploration stage with interactive feedback.

        Wraps _run_stage and adds human-in-the-loop for each discovered node.
        """
        stage_nodes = await self._run_stage(stage, root_bubble, candidates)

        # If not in interactive mode or no clarification agent, return as-is
        if not self._is_interactive() or not self.clarification_agent:
            return stage_nodes

        # Process nodes with user feedback
        confirmed_nodes = []
        nodes_to_explore_deeper = []

        for node in stage_nodes:
            if self._should_stop:
                break

            # Ask user about this connection
            decision = await self.clarification_agent.ask_about_connection(node)

            if decision == "accept":
                node.is_accepted = True
                confirmed_nodes.append(node)
            elif decision == "reject":
                node.is_rejected = True
                node.is_valid = False
            elif decision == "explore_deeper":
                node.is_accepted = True
                confirmed_nodes.append(node)
                nodes_to_explore_deeper.append(node)
            # timeout = keep node as tentatively accepted
            else:
                confirmed_nodes.append(node)

        # Handle "explore deeper" requests by prioritizing those nodes
        if nodes_to_explore_deeper:
            self.journal.session.metadata.setdefault("priority_nodes", [])
            for node in nodes_to_explore_deeper:
                self.journal.session.metadata["priority_nodes"].append(node.id)

        return confirmed_nodes

    def _is_interactive(self) -> bool:
        """Check if exploration is in interactive mode."""
        if not self._exploration_mode or not ExplorationMode:
            return False
        return self._exploration_mode in [ExplorationMode.INTERACTIVE, ExplorationMode.GUIDED]

    def _should_ask_stage_complete(
        self,
        current_stage: ExplorationStage,
        all_stages: List[ExplorationStage]
    ) -> bool:
        """Determine if we should ask user about continuing after stage."""
        if not self._is_interactive():
            return False
        if not self.clarification_agent:
            return False
        if not self.interactive_config:
            return False
        if not self.interactive_config.ask_between_stages:
            return False
        # Don't ask after the last stage
        if current_stage == all_stages[-1]:
            return False
        return True

    async def _ask_stage_complete(
        self,
        stage: ExplorationStage,
        nodes_found: int,
        best_score: float,
    ) -> str:
        """Ask user about continuing to next stage."""
        if not self.clarification_agent:
            return "continue"

        return await self.clarification_agent.ask_stage_complete(
            stage_name=stage.name,
            nodes_found=nodes_found,
            best_score=best_score,
        )

    async def _run_stage(
        self,
        stage: ExplorationStage,
        root_bubble: Dict[str, Any],
        candidates: List[Dict[str, Any]],
    ) -> List[IdeaNode]:
        """Run a single exploration stage."""
        stage_nodes = []

        # Get max nodes for this stage
        max_nodes = {
            ExplorationStage.DIRECT: self.config.stage1_max_nodes,
            ExplorationStage.INDIRECT: self.config.stage2_max_nodes,
            ExplorationStage.ABSTRACT: self.config.stage3_max_nodes,
            ExplorationStage.CREATIVE: self.config.stage4_max_nodes,
        }[stage]

        if stage == ExplorationStage.DIRECT:
            # Stage 1: Find direct connections via embedding similarity
            stage_nodes = await self._explore_direct(root_bubble, candidates, max_nodes)

        elif stage == ExplorationStage.INDIRECT:
            # Stage 2: Explore from best direct connections
            stage_nodes = await self._explore_indirect(root_bubble, candidates, max_nodes)

        elif stage == ExplorationStage.ABSTRACT:
            # Stage 3: Find abstract/thematic connections
            stage_nodes = await self._explore_abstract(root_bubble, candidates, max_nodes)

        elif stage == ExplorationStage.CREATIVE:
            # Stage 4: Creative synthesis
            stage_nodes = await self._explore_creative(root_bubble, candidates, max_nodes)

        return stage_nodes

    async def _explore_direct(
        self,
        root_bubble: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        max_nodes: int,
    ) -> List[IdeaNode]:
        """
        Stage 1: Find direct connections with high embedding similarity.
        """
        discovered = []

        # Evaluate all candidates
        evaluations = await self.evaluator.evaluate_candidates(
            root_bubble,
            candidates,
            top_k=max_nodes,
            use_llm_for_top=self.config.use_llm_for_top_k,
        )

        for candidate, eval_result in evaluations:
            if self._should_stop:
                break

            if not eval_result.is_valid:
                continue

            # Skip if connection already exists
            if self.journal.connection_exists(root_bubble.get("id", ""), candidate.get("id", "")):
                continue

            # Create node
            node = IdeaNode(
                source_bubble_id=root_bubble.get("id", ""),
                source_bubble_title=root_bubble.get("title", ""),
                target_bubble_id=candidate.get("id", ""),
                target_bubble_title=candidate.get("title", ""),
                connection_type=eval_result.connection_type,
                reasoning=eval_result.reasoning,
                edge_label=eval_result.edge_label,
                embedding_similarity=eval_result.embedding_similarity,
                llm_confidence=eval_result.llm_confidence,
                combined_score=eval_result.combined_score,
                exploration_depth=1,
            )

            # Add to journal
            self.journal.append(node)
            discovered.append(node)

            # Callback
            if self.on_node_discovered:
                await self.on_node_discovered(node)

            logger.debug(f"Discovered: {node}")

        return discovered

    async def _explore_indirect(
        self,
        root_bubble: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        max_nodes: int,
    ) -> List[IdeaNode]:
        """
        Stage 2: Explore indirect connections through best Stage 1 nodes.
        """
        discovered = []

        # Get best nodes from Stage 1 to expand
        best_nodes = self.journal.get_best_nodes(top_k=self.config.num_workers)

        for parent_node in best_nodes:
            if self._should_stop:
                break

            if len(discovered) >= max_nodes:
                break

            # Find the bubble corresponding to the parent's target
            parent_bubble = None
            for c in candidates:
                if c.get("id") == parent_node.target_bubble_id:
                    parent_bubble = c
                    break

            if not parent_bubble:
                continue

            # Explore from this node
            remaining_candidates = [
                c for c in candidates
                if c.get("id") not in [root_bubble.get("id"), parent_node.target_bubble_id]
                and not self.journal.connection_exists(parent_node.target_bubble_id, c.get("id", ""))
            ]

            evaluations = await self.evaluator.evaluate_candidates(
                parent_bubble,
                remaining_candidates,
                top_k=max_nodes // len(best_nodes) + 1,
                context=f"Exploring from: {parent_node.target_bubble_title}",
                use_llm_for_top=2,
            )

            for candidate, eval_result in evaluations:
                if not eval_result.is_valid:
                    continue

                node = IdeaNode(
                    source_bubble_id=parent_node.target_bubble_id,
                    source_bubble_title=parent_node.target_bubble_title,
                    target_bubble_id=candidate.get("id", ""),
                    target_bubble_title=candidate.get("title", ""),
                    connection_type=eval_result.connection_type,
                    reasoning=eval_result.reasoning,
                    edge_label=eval_result.edge_label,
                    embedding_similarity=eval_result.embedding_similarity,
                    llm_confidence=eval_result.llm_confidence,
                    combined_score=eval_result.combined_score,
                    exploration_depth=2,
                    parent=parent_node,
                )

                self.journal.append(node)
                discovered.append(node)

                if self.on_node_discovered:
                    await self.on_node_discovered(node)

        return discovered

    async def _explore_abstract(
        self,
        root_bubble: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        max_nodes: int,
    ) -> List[IdeaNode]:
        """
        Stage 3: Find abstract/thematic connections.

        Uses LLM to identify overarching themes and patterns.
        """
        discovered = []

        # Get all discovered connections so far
        existing_connections = self.journal.get_best_nodes(top_k=10)

        # Find candidates not yet connected
        connected_ids = set()
        for node in self.journal.nodes:
            connected_ids.add(node.source_bubble_id)
            connected_ids.add(node.target_bubble_id)

        unconnected = [c for c in candidates if c.get("id") not in connected_ids]

        if not unconnected:
            logger.info("No unconnected bubbles for abstract exploration")
            return discovered

        # Use LLM to find thematic connections
        for candidate in unconnected[:max_nodes]:
            if self._should_stop:
                break

            eval_result = await self.evaluator.evaluate_connection(
                root_bubble,
                candidate,
                context="Find abstract or thematic connections, even if not directly related",
                use_llm=True,
            )

            if eval_result.is_valid and eval_result.combined_score >= self.config.min_score_threshold:
                node = IdeaNode(
                    source_bubble_id=root_bubble.get("id", ""),
                    source_bubble_title=root_bubble.get("title", ""),
                    target_bubble_id=candidate.get("id", ""),
                    target_bubble_title=candidate.get("title", ""),
                    connection_type=ConnectionType.ABSTRACT if eval_result.connection_type == ConnectionType.SEMANTIC else eval_result.connection_type,
                    reasoning=eval_result.reasoning,
                    edge_label=eval_result.edge_label,
                    embedding_similarity=eval_result.embedding_similarity,
                    llm_confidence=eval_result.llm_confidence,
                    combined_score=eval_result.combined_score,
                    exploration_depth=3,
                )

                self.journal.append(node)
                discovered.append(node)

                if self.on_node_discovered:
                    await self.on_node_discovered(node)

        return discovered

    async def _explore_creative(
        self,
        root_bubble: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        max_nodes: int,
    ) -> List[IdeaNode]:
        """
        Stage 4: Creative synthesis - find novel, non-obvious connections.

        Pushes the LLM to think creatively about connections.
        """
        discovered = []

        # Get the least similar candidates (ones embedding didn't catch)
        evaluations = await self.evaluator.evaluate_candidates(
            root_bubble,
            candidates,
            top_k=len(candidates),
            use_llm_for_top=0,  # Just embeddings for sorting
        )

        # Reverse to get least similar first
        evaluations.reverse()

        # Take the least similar that aren't already connected
        for candidate, _ in evaluations[:max_nodes * 2]:
            if self._should_stop:
                break

            if len(discovered) >= max_nodes:
                break

            if self.journal.connection_exists(root_bubble.get("id", ""), candidate.get("id", "")):
                continue

            # Use LLM with creative prompt
            eval_result = await self.evaluator.evaluate_connection(
                root_bubble,
                candidate,
                context="Think creatively: what non-obvious or surprising connection might exist between these ideas?",
                use_llm=True,
            )

            # Lower threshold for creative connections
            if eval_result.llm_confidence >= 0.5:  # Focus on LLM confidence
                node = IdeaNode(
                    source_bubble_id=root_bubble.get("id", ""),
                    source_bubble_title=root_bubble.get("title", ""),
                    target_bubble_id=candidate.get("id", ""),
                    target_bubble_title=candidate.get("title", ""),
                    connection_type=ConnectionType.CREATIVE,
                    reasoning=eval_result.reasoning,
                    edge_label=eval_result.edge_label or "kreativ",
                    embedding_similarity=eval_result.embedding_similarity,
                    llm_confidence=eval_result.llm_confidence,
                    combined_score=eval_result.combined_score,
                    exploration_depth=4,
                )

                self.journal.append(node)
                discovered.append(node)

                if self.on_node_discovered:
                    await self.on_node_discovered(node)

        return discovered

    def stop(self):
        """Request the exploration to stop."""
        self._should_stop = True
        logger.info("Exploration stop requested")

    @property
    def is_running(self) -> bool:
        """Check if exploration is currently running."""
        return self._is_running

    def get_progress(self) -> Dict[str, Any]:
        """Get current exploration progress."""
        if not self.journal:
            return {
                "status": "not_started",
                "stage": None,
                "nodes_discovered": 0,
                "best_score": 0.0,
            }

        return {
            "status": self.journal.session.status if self.journal.session else "unknown",
            "stage": self.current_stage.name if self.current_stage else None,
            "stage_number": self.current_stage.value if self.current_stage else 0,
            "nodes_discovered": len(self.journal.nodes),
            "best_score": self.journal.session.best_score if self.journal.session else 0.0,
            "stats": self.journal.get_stats(),
        }
