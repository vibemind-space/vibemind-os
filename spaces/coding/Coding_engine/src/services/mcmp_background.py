"""
MCMP Background Simulation Service.

Runs continuous MCMP (Mycelial Collective Pheromone Search) simulation during
code generation to discover multi-hop code dependencies and enrich context.

Features:
1. Continuous simulation loop with configurable step intervals
2. Judge LLM evaluation every N steps (default: 5)
3. Mode-aware prompts: repair, steering, deep, structure
4. Context enrichment callbacks for EventBus integration
"""

import asyncio
import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
import structlog

from src.llm_config import get_model

logger = structlog.get_logger(__name__)


class JudgeMode(Enum):
    """Judge LLM modes for different use cases."""
    REPAIR = "repair"       # BUILD_FAILED, TYPE_ERROR - Focus on error-prone code
    STEERING = "steering"   # GENERATION_REQUESTED - Suggest missing context
    DEEP = "deep"           # E2E_TEST_FAILED - Detailed code analysis
    STRUCTURE = "structure" # Component tree building - API relationships


@dataclass
class SimulationConfig:
    """Configuration for MCMP background simulation."""
    num_agents: int = 200
    max_iterations: int = 50
    pheromone_decay: float = 0.95
    exploration_bonus: float = 0.1
    step_interval: float = 0.1  # Seconds between steps
    judge_every: int = 5        # Run judge every N steps
    steering_every: int = 5     # Run LLM steering every N steps
    judge_provider: str = "openrouter"
    judge_model: str = field(default_factory=lambda: get_model("judge"))
    steering_model: str = field(default_factory=lambda: get_model("judge"))  # Fast model for steering
    top_k_results: int = 10
    enable_llm_steering: bool = True  # Enable LLM-guided exploration
    # Phase 11: Completeness checking params
    restart_every: int = 10  # Restart simulation every N steps for fresh exploration
    min_confidence: float = 0.6  # Minimum confidence threshold for results
    completeness_mode: bool = False  # Enable requirement completeness checking mode


@dataclass
class JudgeResult:
    """Result from Judge LLM evaluation."""
    mode: JudgeMode
    query: str
    step: int
    recommended_ids: List[int] = field(default_factory=list)
    reasoning: str = ""
    additional_queries: List[str] = field(default_factory=list)
    confidence: float = 0.0
    raw_response: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SteeringGuidance:
    """LLM-provided guidance for steering MCMP agents."""
    boost_areas: List[str] = field(default_factory=list)    # Keywords/areas to explore more
    avoid_areas: List[str] = field(default_factory=list)    # Areas to deprioritize
    new_keywords: List[str] = field(default_factory=list)   # New terms to search
    pheromone_boost: Dict[int, float] = field(default_factory=dict)  # doc_id -> boost factor
    reasoning: str = ""


class MCMPBackgroundSimulation:
    """
    Runs continuous MCMP simulation during code generation.

    Provides real-time context discovery for:
    - Error fixing (repair mode)
    - Feature generation (steering mode)
    - Test debugging (deep mode)
    - Architecture analysis (structure mode)
    """

    def __init__(
        self,
        config: Optional[SimulationConfig] = None,
        on_context_update: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ):
        self.config = config or SimulationConfig()
        self.on_context_update = on_context_update

        self._retriever = None
        self._running = False
        self._step_count = 0
        self._current_query: Optional[str] = None
        self._current_mode: JudgeMode = JudgeMode.STEERING
        self._simulation_task: Optional[asyncio.Task] = None
        self._judge_results: List[JudgeResult] = []
        self._steering_history: List[SteeringGuidance] = []
        self._llm_client = None

        self.logger = logger.bind(component="MCMPBackground")

    def _init_retriever(self) -> bool:
        """Lazy-initialize the MCMP retriever."""
        if self._retriever is not None:
            return True

        try:
            import sys
            fungus_path = Path(__file__).parent.parent.parent / "la_fungus_search" / "src"
            if str(fungus_path) not in sys.path:
                sys.path.insert(0, str(fungus_path))

            from embeddinggemma.mcmp_rag import MCPMRetriever

            self._retriever = MCPMRetriever(
                num_agents=self.config.num_agents,
                max_iterations=self.config.max_iterations,
                pheromone_decay=self.config.pheromone_decay,
                exploration_bonus=self.config.exploration_bonus,
            )
            self.logger.info("retriever_initialized", num_agents=self.config.num_agents)
            return True
        except Exception as e:
            self.logger.error("retriever_init_failed", error=str(e))
            return False

    async def _init_llm_client(self) -> bool:
        """Initialize async LLM client for steering."""
        if self._llm_client is not None:
            return True

        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            self.logger.warning("no_openrouter_key", msg="LLM steering disabled")
            return False

        try:
            import httpx
            self._llm_client = httpx.AsyncClient(
                base_url="https://openrouter.ai/api/v1",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
            self.logger.info("llm_client_initialized")
            return True
        except Exception as e:
            self.logger.error("llm_client_init_failed", error=str(e))
            return False

    async def _get_steering_guidance(self) -> Optional[SteeringGuidance]:
        """
        Get LLM-based steering guidance for MCMP agents.

        Calls fast LLM (Haiku) to analyze current exploration state
        and recommend areas to focus on or avoid.
        """
        if not self.config.enable_llm_steering:
            return None

        if not await self._init_llm_client():
            return None

        if not self._retriever or not self._current_query:
            return None

        try:
            # Get current top results and their content
            top_results = self._get_top_results(10)
            if not top_results:
                return None

            # Format current exploration state
            exploration_summary = []
            for i, r in enumerate(top_results[:5]):
                content_preview = r.get("content", "")[:200]
                score = r.get("relevance_score", 0)
                visits = r.get("visit_count", 0)
                exploration_summary.append(
                    f"[{i}] score={score:.2f} visits={visits}: {content_preview}..."
                )

            prompt = f"""You are steering a code search swarm to find relevant context.

Original Query: "{self._current_query}"
Mode: {self._current_mode.value}
Current Step: {self._step_count}

Current agent exploration (top 5 most relevant):
{chr(10).join(exploration_summary)}

Suggest how to steer the exploration:
{{
  "boost_areas": ["keyword1", "keyword2"],  // Areas to explore more aggressively
  "avoid_areas": ["keyword3"],              // Areas that are not relevant
  "new_keywords": ["term1", "term2"],       // New search terms to add
  "pheromone_boost": {{"0": 1.5, "2": 1.3}}, // doc index -> boost factor
  "reasoning": "brief explanation"
}}

Focus on finding code that helps answer: {self._current_query}"""

            response = await self._llm_client.post(
                "/chat/completions",
                json={
                    "model": self.config.steering_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                },
            )

            if response.status_code != 200:
                self.logger.warning("steering_llm_call_failed", status=response.status_code)
                return None

            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Parse JSON from response
            parsed = self._parse_steering_response(content)

            guidance = SteeringGuidance(
                boost_areas=parsed.get("boost_areas", []),
                avoid_areas=parsed.get("avoid_areas", []),
                new_keywords=parsed.get("new_keywords", []),
                pheromone_boost={int(k): v for k, v in parsed.get("pheromone_boost", {}).items()},
                reasoning=parsed.get("reasoning", ""),
            )

            self.logger.info(
                "steering_guidance_received",
                step=self._step_count,
                boost_areas=guidance.boost_areas,
                new_keywords=guidance.new_keywords,
            )

            return guidance

        except Exception as e:
            self.logger.warning("steering_guidance_failed", error=str(e))
            return None

    def _parse_steering_response(self, response: str) -> Dict[str, Any]:
        """Parse steering LLM response."""
        try:
            return json.loads(response)
        except Exception:
            pass

        try:
            text = response.strip()
            if text.startswith("```"):
                lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
                text = "\n".join(lines)

            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start:end + 1])
        except Exception:
            pass

        return {}

    def _apply_steering(self, guidance: SteeringGuidance) -> None:
        """
        Apply steering guidance to MCMP simulation.

        Modifies pheromone trails and agent positions based on LLM guidance.
        """
        if not self._retriever or not guidance:
            return

        try:
            # Apply pheromone boosts to specific documents
            # pheromone_trails uses (doc_id_a, doc_id_b) tuple keys
            for doc_idx, boost_factor in guidance.pheromone_boost.items():
                if 0 <= doc_idx < len(self._retriever.documents):
                    doc = self._retriever.documents[doc_idx]
                    # Boost relevance score
                    doc.relevance_score = min(1.0, doc.relevance_score * boost_factor)
                    # Boost pheromone trails involving this document
                    if hasattr(self._retriever, 'pheromone_trails'):
                        for trail_key in list(self._retriever.pheromone_trails.keys()):
                            if isinstance(trail_key, tuple) and doc.id in trail_key:
                                self._retriever.pheromone_trails[trail_key] *= boost_factor

            # Add new keywords — retriever may not have expand_query
            if guidance.new_keywords and hasattr(self._retriever, 'expand_query'):
                for keyword in guidance.new_keywords[:3]:  # Limit to 3
                    self._retriever.expand_query(keyword)

            # Reduce exploration in avoided areas
            for doc in self._retriever.documents:
                content_lower = doc.content.lower()
                for avoid_term in guidance.avoid_areas:
                    if avoid_term.lower() in content_lower:
                        # Reduce relevance for documents containing avoided terms
                        doc.relevance_score *= 0.5
                        # Reduce pheromone trails involving this document
                        if hasattr(self._retriever, 'pheromone_trails'):
                            for trail_key in list(self._retriever.pheromone_trails.keys()):
                                if isinstance(trail_key, tuple) and doc.id in trail_key:
                                    self._retriever.pheromone_trails[trail_key] *= 0.5

            # Store in history
            self._steering_history.append(guidance)

            self.logger.debug(
                "steering_applied",
                step=self._step_count,
                boosts=len(guidance.pheromone_boost),
                new_keywords=len(guidance.new_keywords),
            )

        except Exception as e:
            self.logger.warning("apply_steering_failed", error=str(e))

    def add_documents(self, documents: List[str]) -> int:
        """Add documents to the simulation corpus."""
        if not self._init_retriever():
            return 0

        try:
            self._retriever.add_documents(documents)
            self.logger.info("documents_added", count=len(documents))
            return len(documents)
        except Exception as e:
            self.logger.error("add_documents_failed", error=str(e))
            return 0

    def clear_documents(self) -> None:
        """Clear all documents from the corpus."""
        if self._retriever:
            self._retriever.clear_documents()
            self.logger.info("documents_cleared")

    async def start(
        self,
        query: str,
        mode: JudgeMode = JudgeMode.STEERING,
    ) -> bool:
        """
        Start background simulation for a query.

        Args:
            query: The search/context query
            mode: Judge LLM mode for evaluation

        Returns:
            True if simulation started successfully
        """
        if self._running:
            self.logger.warning("simulation_already_running")
            return False

        if not self._init_retriever():
            return False

        if not self._retriever.documents:
            self.logger.warning("no_documents_for_simulation")
            return False

        self._current_query = query
        self._current_mode = mode
        self._step_count = 0
        self._judge_results = []
        self._steering_history = []  # Reset steering history for new simulation

        # Initialize simulation
        if not self._retriever.initialize_simulation(query):
            self.logger.error("simulation_init_failed")
            return False

        self._running = True
        self._simulation_task = asyncio.create_task(self._simulation_loop())

        self.logger.info(
            "simulation_started",
            query=query[:50],
            mode=mode.value,
            documents=len(self._retriever.documents),
        )
        return True

    async def stop(self) -> Dict[str, Any]:
        """
        Stop the background simulation.

        Returns:
            Final simulation results
        """
        self._running = False

        if self._simulation_task:
            self._simulation_task.cancel()
            try:
                await self._simulation_task
            except asyncio.CancelledError:
                pass
            self._simulation_task = None

        results = self.get_results()
        self.logger.info(
            "simulation_stopped",
            steps=self._step_count,
            judge_evaluations=len(self._judge_results),
        )
        return results

    async def _simulation_loop(self) -> None:
        """Main simulation loop with LLM steering."""
        try:
            while self._running and self._step_count < self.config.max_iterations:
                # Step simulation
                metrics = self._retriever.step(1)
                self._step_count += 1

                # LLM steering every N steps (before judge evaluation)
                if (self.config.enable_llm_steering and
                    self._step_count % self.config.steering_every == 0 and
                    self._step_count > 0):
                    guidance = await self._get_steering_guidance()
                    if guidance:
                        self._apply_steering(guidance)

                # Judge LLM evaluation every N steps
                if self._step_count % self.config.judge_every == 0:
                    judge_result = await self._run_judge()
                    if judge_result:
                        self._judge_results.append(judge_result)

                # Broadcast update
                if self.on_context_update:
                    update = {
                        "type": "mcmp_step",
                        "step": self._step_count,
                        "metrics": metrics,
                        "top_results": self._get_top_results(5),
                    }
                    try:
                        await self.on_context_update(update)
                    except Exception as e:
                        self.logger.warning("context_update_callback_failed", error=str(e))

                # Brief pause between steps
                await asyncio.sleep(self.config.step_interval)

            # Final judge evaluation
            if self._running:
                final_result = await self._run_judge()
                if final_result:
                    self._judge_results.append(final_result)

                # Final broadcast
                if self.on_context_update:
                    await self.on_context_update({
                        "type": "mcmp_complete",
                        "total_steps": self._step_count,
                        "results": self.get_results(),
                    })

            self._running = False

        except asyncio.CancelledError:
            self.logger.info("simulation_cancelled")
            raise
        except Exception as e:
            self.logger.error("simulation_loop_error", error=str(e))
            self._running = False

    async def _run_judge(self) -> Optional[JudgeResult]:
        """Run Judge LLM evaluation on current results."""
        if not self._retriever or not self._current_query:
            return None

        try:
            # Get current top results
            top_results = self._get_top_results(self.config.top_k_results)
            if not top_results:
                return None

            # Build judge prompt
            import sys
            fungus_path = Path(__file__).parent.parent.parent / "la_fungus_search" / "src"
            if str(fungus_path) not in sys.path:
                sys.path.insert(0, str(fungus_path))

            from embeddinggemma.llm.prompts import build_judge_prompt
            from embeddinggemma.rag.generation import generate_text

            # Format results for judge
            judge_items = [
                {
                    "id": i,
                    "score": r.get("relevance_score", 0.0),
                    "content": r.get("content", "")[:500],  # Truncate for prompt
                }
                for i, r in enumerate(top_results)
            ]

            prompt = build_judge_prompt(
                self._current_mode.value,
                self._current_query,
                judge_items,
            )

            # Call Judge LLM via OpenRouter (OpenAI-compatible endpoint)
            # Note: generate_text appends /v1/chat/completions, so base is /api
            response = generate_text(
                provider="openai",
                prompt=prompt,
                openai_model=self.config.judge_model,
                openai_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                openai_base_url="https://openrouter.ai/api",
                timeout=60,
            )

            # Parse response
            parsed = self._parse_judge_response(response)

            result = JudgeResult(
                mode=self._current_mode,
                query=self._current_query,
                step=self._step_count,
                recommended_ids=parsed.get("recommended_ids", []),
                reasoning=parsed.get("reasoning", ""),
                additional_queries=parsed.get("additional_queries", []),
                confidence=parsed.get("confidence", 0.0),
                raw_response=parsed,
            )

            self.logger.info(
                "judge_evaluation_complete",
                step=self._step_count,
                recommended_count=len(result.recommended_ids),
                confidence=result.confidence,
            )

            return result

        except Exception as e:
            self.logger.warning("judge_evaluation_failed", step=self._step_count, error=str(e))
            return None

    def _parse_judge_response(self, response: str) -> Dict[str, Any]:
        """Parse Judge LLM response JSON."""
        try:
            # Try direct JSON parse
            return json.loads(response)
        except Exception:
            pass

        try:
            # Try extracting JSON from markdown code blocks
            text = response.strip()
            if text.startswith("```"):
                lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
                text = "\n".join(lines)

            # Find JSON object or array
            start_obj = text.find("{")
            start_arr = text.find("[")
            starts = [p for p in [start_obj, start_arr] if p != -1]
            start = min(starts) if starts else -1

            end_obj = text.rfind("}")
            end_arr = text.rfind("]")
            end = max(end_obj, end_arr)

            if start != -1 and end != -1 and end > start:
                return json.loads(text[start:end + 1])
        except Exception:
            pass

        return {}

    def _get_top_results(self, top_k: int) -> List[Dict[str, Any]]:
        """Get top-k results from current simulation state."""
        if not self._retriever:
            return []

        try:
            ranked = sorted(
                self._retriever.documents,
                key=lambda d: d.relevance_score,
                reverse=True,
            )[:top_k]

            return [
                {
                    "id": d.id,
                    "content": d.content,
                    "relevance_score": d.relevance_score,
                    "visit_count": d.visit_count,
                    "metadata": d.metadata,
                }
                for d in ranked
            ]
        except Exception:
            return []

    def get_results(self) -> Dict[str, Any]:
        """Get current simulation results including LLM steering history."""
        return {
            "query": self._current_query,
            "mode": self._current_mode.value if self._current_mode else None,
            "steps_completed": self._step_count,
            "is_running": self._running,
            "llm_steering_enabled": self.config.enable_llm_steering,
            "top_results": self._get_top_results(self.config.top_k_results),
            "judge_evaluations": [
                {
                    "step": jr.step,
                    "recommended_ids": jr.recommended_ids,
                    "reasoning": jr.reasoning[:200] if jr.reasoning else "",
                    "confidence": jr.confidence,
                    "additional_queries": jr.additional_queries,
                }
                for jr in self._judge_results
            ],
            "steering_history": [
                {
                    "boost_areas": sg.boost_areas,
                    "avoid_areas": sg.avoid_areas,
                    "new_keywords": sg.new_keywords,
                    "reasoning": sg.reasoning[:150] if sg.reasoning else "",
                }
                for sg in self._steering_history[-5:]  # Last 5 steering decisions
            ],
            "pheromone_trail_count": len(self._retriever.pheromone_trails) if self._retriever else 0,
        }

    def get_enriched_context(self) -> Dict[str, Any]:
        """
        Get enriched context for EventBus event enrichment.

        Returns context suitable for adding to CODE_FIX_NEEDED, BUILD_FAILED events.
        """
        results = self.get_results()

        # Extract most relevant code snippets
        relevant_code = []
        for r in results.get("top_results", [])[:5]:
            relevant_code.append({
                "content": r.get("content", ""),
                "score": r.get("relevance_score", 0.0),
                "metadata": r.get("metadata", {}),
            })

        # Aggregate judge recommendations
        recommended_focus = []
        for jr in self._judge_results[-3:]:  # Last 3 evaluations
            if jr.reasoning:
                recommended_focus.append(jr.reasoning)

        # Aggregate LLM steering insights
        steering_insights = []
        boost_keywords = set()
        for sg in self._steering_history[-3:]:  # Last 3 steering decisions
            if sg.reasoning:
                steering_insights.append(sg.reasoning)
            boost_keywords.update(sg.boost_areas)
            boost_keywords.update(sg.new_keywords)

        return {
            "fungus_context": {
                "relevant_code": relevant_code,
                "recommended_focus": recommended_focus,
                "steering_insights": steering_insights,
                "suggested_keywords": list(boost_keywords)[:10],
                "judge_confidence": self._judge_results[-1].confidence if self._judge_results else 0.0,
                "simulation_steps": self._step_count,
                "llm_steering_enabled": self.config.enable_llm_steering,
                "additional_queries": (
                    self._judge_results[-1].additional_queries
                    if self._judge_results else []
                ),
            }
        }

    @property
    def is_running(self) -> bool:
        """Check if simulation is currently running."""
        return self._running

    @property
    def step_count(self) -> int:
        """Get current step count."""
        return self._step_count

    async def close(self) -> None:
        """Clean up resources (LLM client, etc.)."""
        if self._running:
            await self.stop()

        if self._llm_client:
            try:
                await self._llm_client.aclose()
            except Exception:
                pass
            self._llm_client = None

        self.logger.info("mcmp_background_closed")


async def main():
    """CLI entry point for testing MCMP background simulation."""
    import argparse

    parser = argparse.ArgumentParser(description="Test MCMP background simulation")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--docs", nargs="+", help="Document strings to add")
    parser.add_argument("--mode", default="steering", choices=["repair", "steering", "deep", "structure"])
    parser.add_argument("--steps", type=int, default=20, help="Max iterations")

    args = parser.parse_args()

    config = SimulationConfig(
        max_iterations=args.steps,
        judge_every=5,
    )

    async def on_update(update: Dict[str, Any]):
        print(f"Update: step={update.get('step', 'N/A')}")

    sim = MCMPBackgroundSimulation(config=config, on_context_update=on_update)

    # Add sample documents if none provided
    docs = args.docs or [
        "def calculate_total(items): return sum(item.price for item in items)",
        "class Order: def __init__(self): self.items = []",
        "async def fetch_order(order_id): return await db.orders.find_one({'id': order_id})",
    ]

    sim.add_documents(docs)

    mode = JudgeMode(args.mode)
    await sim.start(args.query, mode=mode)

    # Wait for completion
    while sim.is_running:
        await asyncio.sleep(1)

    results = await sim.stop()
    print("\nFinal Results:")
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
