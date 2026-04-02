"""
Fungus Worker - Async Parallel MCMP Simulation with Redis Streaming.

Runs MCMP simulation in parallel with code generation, publishing context
updates to Redis streams for consumption by Claude CLI and other components.

Architecture:
┌─────────────────────────────────────────────────────────────────────┐
│  FungusWorker (Async)                                                │
│  ├── ArchitectSteering → Guides simulation parameters                │
│  ├── MCMPBackgroundSimulation → Runs 200-agent swarm search          │
│  └── Redis Streams → Publishes context updates                       │
│                                                                       │
│  Redis Stream Keys:                                                   │
│  ├── fungus:context:{job_id} → Search results + context              │
│  ├── fungus:tasks:{job_id} → Verification tasks                      │
│  ├── fungus:verification:{job_id} → Component test status            │
│  └── fungus:steering:{job_id} → Architect decisions                  │
└─────────────────────────────────────────────────────────────────────┘
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import structlog

from src.services.mcmp_background import (
    MCMPBackgroundSimulation,
    SimulationConfig,
    JudgeMode,
)
from src.llm_config import get_model

# Import EventBus for agent notification
from src.mind.event_bus import EventBus, Event, EventType

logger = structlog.get_logger(__name__)


@dataclass
class SteeringParams:
    """Parameters for steering MCMP simulation."""
    num_steps: int = 10
    boost_areas: List[str] = field(default_factory=list)
    avoid_areas: List[str] = field(default_factory=list)
    exploration_factor: float = 0.3
    judge_mode: JudgeMode = JudgeMode.STEERING


@dataclass
class Evaluation:
    """Evaluation result from architect."""
    is_good_content: bool = False
    confidence: float = 0.0
    reasoning: str = ""
    recommended_focus: str = ""


class ArchitectSteering:
    """
    LLM-powered architect that steers MCMP simulation parameters.

    Uses Claude Haiku via OpenRouter for fast decision-making on:
    - How many simulation steps to run
    - Which areas to focus exploration on
    - When content quality is sufficient
    """

    def __init__(self, model: str = None):
        self.model = model or get_model("judge")
        self._client = None
        self.logger = logger.bind(component="ArchitectSteering")

    async def _init_client(self) -> bool:
        """Initialize async HTTP client for OpenRouter."""
        if self._client is not None:
            return True

        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            self.logger.warning("no_openrouter_key", msg="Architect steering disabled")
            return False

        try:
            import httpx
            self._client = httpx.AsyncClient(
                base_url="https://openrouter.ai/api/v1",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
            return True
        except Exception as e:
            self.logger.error("client_init_failed", error=str(e))
            return False

    async def get_parameters(
        self,
        query: str,
        sim_state: Dict[str, Any],
    ) -> SteeringParams:
        """
        Use LLM to determine optimal simulation parameters.

        Args:
            query: The search/context query
            sim_state: Current simulation state (step count, top results, etc.)

        Returns:
            SteeringParams with recommended settings
        """
        if not await self._init_client():
            return SteeringParams()  # Default params

        prompt = f"""You are steering a code context search simulation.

Query: {query}
Current State:
- Steps completed: {sim_state.get('steps_completed', 0)}
- Top results found: {len(sim_state.get('top_results', []))}
- Current confidence: {sim_state.get('judge_confidence', 0)}

Determine optimal parameters for the next simulation round:
{{
  "num_steps": 5-50 (how many simulation steps),
  "boost_areas": ["keyword1", "keyword2"] (areas to explore more),
  "avoid_areas": ["keyword3"] (areas to avoid),
  "exploration_factor": 0.0-1.0 (0=exploit known, 1=explore new),
  "reasoning": "brief explanation"
}}

Consider:
- Lower num_steps if confidence is high
- Focus boost_areas on the core query terms
- Avoid areas that are clearly unrelated
- Higher exploration_factor early, lower later"""

        try:
            response = await self._client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                },
            )

            if response.status_code != 200:
                self.logger.warning("llm_call_failed", status=response.status_code)
                return SteeringParams()

            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._parse_json_response(content)

            return SteeringParams(
                num_steps=parsed.get("num_steps", 10),
                boost_areas=parsed.get("boost_areas", []),
                avoid_areas=parsed.get("avoid_areas", []),
                exploration_factor=parsed.get("exploration_factor", 0.3),
            )

        except Exception as e:
            self.logger.warning("get_parameters_failed", error=str(e))
            return SteeringParams()

    async def evaluate(self, results: List[Dict[str, Any]]) -> Evaluation:
        """
        Evaluate if simulation results are good enough.

        Args:
            results: Top-K results from simulation

        Returns:
            Evaluation with is_good_content flag
        """
        if not await self._init_client():
            return Evaluation()

        # Format results for evaluation
        result_summary = []
        for i, r in enumerate(results[:5]):
            content_preview = r.get("content", "")[:200]
            score = r.get("relevance_score", 0)
            result_summary.append(f"[{i}] score={score:.2f}: {content_preview}...")

        prompt = f"""Evaluate these code search results for quality:

Results:
{chr(10).join(result_summary)}

Is this content sufficient to help solve a code generation/debugging task?
Return JSON:
{{
  "is_good_content": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "recommended_focus": "what to search for next if not good"
}}

Consider:
- Are results relevant to code generation?
- Is there enough context to understand the codebase?
- Would a developer find this helpful?"""

        try:
            response = await self._client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                },
            )

            if response.status_code != 200:
                return Evaluation()

            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = self._parse_json_response(content)

            return Evaluation(
                is_good_content=parsed.get("is_good_content", False),
                confidence=parsed.get("confidence", 0.0),
                reasoning=parsed.get("reasoning", ""),
                recommended_focus=parsed.get("recommended_focus", ""),
            )

        except Exception as e:
            self.logger.warning("evaluate_failed", error=str(e))
            return Evaluation()

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON from LLM response."""
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

    async def close(self) -> None:
        """Clean up resources."""
        if self._client:
            await self._client.aclose()
            self._client = None


class FungusWorker:
    """
    Async worker that runs MCMP simulation parallel to code generation.

    Publishes context updates to Redis streams for consumption by:
    - ClaudeCodeTool (context loading)
    - VerificationAgent (fullstack testing)
    - Dashboard (progress monitoring)
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        job_id: str = "default",
        working_dir: Optional[str] = None,
        max_rounds: int = 5,
        min_confidence: float = 0.7,
        event_bus: Optional[EventBus] = None,
    ):
        self.redis_url = redis_url
        self.job_id = job_id
        self.working_dir = working_dir
        self.max_rounds = max_rounds
        self.min_confidence = min_confidence
        self.event_bus = event_bus

        self.architect = ArchitectSteering()
        self.simulation = MCMPBackgroundSimulation(
            config=SimulationConfig(
                num_agents=200,
                max_iterations=50,
                enable_llm_steering=True,
            ),
            on_context_update=self._on_simulation_update,
        )

        self._redis = None
        self._running = False
        self._round = 0
        self._task: Optional[asyncio.Task] = None

        self.logger = logger.bind(component="FungusWorker", job_id=job_id)

    async def _init_redis(self) -> bool:
        """Initialize async Redis client."""
        if self._redis is not None:
            return True

        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            self.logger.info("redis_connected")
            return True
        except Exception as e:
            self.logger.error("redis_connection_failed", error=str(e))
            return False

    async def index_project(self, project_dir: Optional[str] = None) -> int:
        """
        Index project files for MCMP simulation.

        Args:
            project_dir: Directory to index (defaults to working_dir)

        Returns:
            Number of documents indexed
        """
        target_dir = project_dir or self.working_dir
        if not target_dir or not Path(target_dir).exists():
            self.logger.warning("no_project_dir_for_indexing")
            return 0

        try:
            documents = []
            extensions = {".ts", ".tsx", ".js", ".jsx", ".py", ".prisma", ".json"}

            for file_path in Path(target_dir).rglob("*"):
                if file_path.is_file() and file_path.suffix in extensions:
                    # Skip node_modules and other large dirs
                    if "node_modules" in str(file_path) or ".git" in str(file_path):
                        continue

                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        if content.strip():
                            # Add file path as metadata in content
                            doc = f"# File: {file_path.relative_to(target_dir)}\n{content[:5000]}"
                            documents.append(doc)
                    except Exception:
                        pass

            count = self.simulation.add_documents(documents)
            self.logger.info("project_indexed", documents=count)
            return count

        except Exception as e:
            self.logger.error("indexing_failed", error=str(e))
            return 0

    async def run_until_good_content(
        self,
        query: str,
        mode: JudgeMode = JudgeMode.STEERING,
    ) -> Dict[str, Any]:
        """
        Run simulation until architect approves content quality.

        Args:
            query: The search/context query
            mode: Judge mode for evaluation

        Returns:
            Final enriched context
        """
        if self._running:
            self.logger.warning("already_running")
            return {}

        self._running = True
        self._round = 0

        try:
            while self._running and self._round < self.max_rounds:
                self._round += 1

                # 1. Get steering parameters from architect
                sim_state = self.simulation.get_results()
                params = await self.architect.get_parameters(query, sim_state)

                self.logger.info(
                    "steering_round",
                    round=self._round,
                    num_steps=params.num_steps,
                    boost_areas=params.boost_areas,
                )

                # 2. Publish steering decision to Redis
                await self._publish_steering(params)

                # 3. Start simulation with params
                await self.simulation.start(query, mode=mode)

                # Wait for simulation to complete its steps
                step_count = 0
                while self.simulation.is_running and step_count < params.num_steps:
                    await asyncio.sleep(0.5)
                    step_count = self.simulation.step_count

                # 4. Get results and evaluate
                results = self.simulation.get_results()
                top_results = results.get("top_results", [])
                evaluation = await self.architect.evaluate(top_results)

                # 5. Publish results to Redis stream
                await self._publish_context(top_results, evaluation)

                self.logger.info(
                    "round_complete",
                    round=self._round,
                    confidence=evaluation.confidence,
                    is_good=evaluation.is_good_content,
                )

                # 6. Check if good enough
                if evaluation.is_good_content or evaluation.confidence >= self.min_confidence:
                    self.logger.info("good_content_found", round=self._round)

                    # Notify EventBus that good context is ready
                    await self._notify_context_ready(evaluation)
                    break

                # Stop simulation before next round
                await self.simulation.stop()

            # Final results
            final_context = self.simulation.get_enriched_context()
            await self._publish_final(final_context)

            return final_context

        except asyncio.CancelledError:
            self.logger.info("worker_cancelled")
            raise
        except Exception as e:
            self.logger.error("worker_failed", error=str(e))
            return {}
        finally:
            self._running = False
            await self.simulation.stop()

    async def start_background(
        self,
        query: str,
        mode: JudgeMode = JudgeMode.STEERING,
    ) -> None:
        """Start worker in background as async task."""
        if self._task and not self._task.done():
            self.logger.warning("background_task_already_running")
            return

        self._task = asyncio.create_task(self.run_until_good_content(query, mode))
        self.logger.info("background_task_started")

    async def stop(self) -> Dict[str, Any]:
        """Stop background worker and return results."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        return self.simulation.get_enriched_context()

    async def _on_simulation_update(self, update: Dict[str, Any]) -> None:
        """Callback for simulation step updates."""
        if not await self._init_redis():
            return

        try:
            stream_key = f"fungus:progress:{self.job_id}"
            await self._redis.xadd(
                stream_key,
                {
                    "type": update.get("type", "step"),
                    "step": str(update.get("step", 0)),
                    "timestamp": str(time.time()),
                },
                maxlen=100,  # Keep last 100 entries
            )
        except Exception as e:
            self.logger.debug("progress_publish_failed", error=str(e))

    async def _publish_context(
        self,
        results: List[Dict[str, Any]],
        evaluation: Evaluation,
    ) -> None:
        """Publish context update to Redis stream."""
        if not await self._init_redis():
            return

        try:
            stream_key = f"fungus:context:{self.job_id}"

            # Serialize results (truncate for Redis)
            serialized_results = json.dumps([
                {
                    "content": r.get("content", "")[:1000],
                    "score": r.get("relevance_score", 0),
                    "metadata": r.get("metadata", {}),
                }
                for r in results[:10]
            ])

            await self._redis.xadd(
                stream_key,
                {
                    "type": "context_update",
                    "round": str(self._round),
                    "results": serialized_results,
                    "confidence": str(evaluation.confidence),
                    "is_good_content": str(evaluation.is_good_content),
                    "recommended_focus": evaluation.recommended_focus,
                    "timestamp": str(time.time()),
                },
                maxlen=50,
            )

            self.logger.debug("context_published", round=self._round)

        except Exception as e:
            self.logger.warning("context_publish_failed", error=str(e))

    async def _publish_steering(self, params: SteeringParams) -> None:
        """Publish steering decision to Redis stream."""
        if not await self._init_redis():
            return

        try:
            stream_key = f"fungus:steering:{self.job_id}"
            await self._redis.xadd(
                stream_key,
                {
                    "type": "steering_decision",
                    "round": str(self._round),
                    "num_steps": str(params.num_steps),
                    "boost_areas": json.dumps(params.boost_areas),
                    "avoid_areas": json.dumps(params.avoid_areas),
                    "exploration_factor": str(params.exploration_factor),
                    "timestamp": str(time.time()),
                },
                maxlen=20,
            )
        except Exception as e:
            self.logger.debug("steering_publish_failed", error=str(e))

    async def _notify_context_ready(self, evaluation: Evaluation) -> None:
        """Notify EventBus that good context is ready (for Architect feedback loop)."""
        if not self.event_bus:
            return

        try:
            await self.event_bus.publish(Event(
                type=EventType.FUNGUS_CONTEXT_READY,
                source="FungusWorker",
                data={
                    "job_id": self.job_id,
                    "confidence": evaluation.confidence,
                    "recommended_focus": evaluation.recommended_focus,
                    "reasoning": evaluation.reasoning,
                    "round": self._round,
                },
            ))
            self.logger.info(
                "eventbus_notified",
                event_type="FUNGUS_CONTEXT_READY",
                confidence=evaluation.confidence,
            )
        except Exception as e:
            self.logger.warning("eventbus_notify_failed", error=str(e))

    async def _publish_final(self, context: Dict[str, Any]) -> None:
        """Publish final enriched context."""
        if not await self._init_redis():
            return

        try:
            stream_key = f"fungus:context:{self.job_id}"
            await self._redis.xadd(
                stream_key,
                {
                    "type": "final_context",
                    "round": str(self._round),
                    "context": json.dumps(context, default=str)[:5000],
                    "timestamp": str(time.time()),
                },
            )

            self.logger.info("final_context_published")

        except Exception as e:
            self.logger.warning("final_publish_failed", error=str(e))

    async def close(self) -> None:
        """Clean up all resources."""
        await self.stop()
        await self.architect.close()
        await self.simulation.close()

        if self._redis:
            await self._redis.close()
            self._redis = None

        self.logger.info("worker_closed")

    @property
    def is_running(self) -> bool:
        """Check if worker is currently running."""
        return self._running


class VerificationPublisher:
    """
    Publishes verification tasks and results to Redis streams.

    Used to track which fullstack components have been tested/verified.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        job_id: str = "default",
    ):
        self.redis_url = redis_url
        self.job_id = job_id
        self._redis = None
        self.logger = logger.bind(component="VerificationPublisher", job_id=job_id)

    async def _init_redis(self) -> bool:
        """Initialize async Redis client."""
        if self._redis is not None:
            return True

        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            return True
        except Exception as e:
            self.logger.error("redis_connection_failed", error=str(e))
            return False

    async def publish_task(self, task: Dict[str, Any]) -> bool:
        """
        Publish verification task event.

        Args:
            task: Task details (component, check type, etc.)

        Returns:
            True if published successfully
        """
        if not await self._init_redis():
            return False

        try:
            stream_key = f"fungus:tasks:{self.job_id}"
            await self._redis.xadd(
                stream_key,
                {
                    "type": "verification_task",
                    "task": json.dumps(task),
                    "timestamp": str(time.time()),
                },
                maxlen=100,
            )
            return True
        except Exception as e:
            self.logger.warning("publish_task_failed", error=str(e))
            return False

    async def report_verified(
        self,
        component: str,
        status: bool,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Report fullstack component as verified/tested.

        Args:
            component: Component name (e.g., "database", "api", "frontend")
            status: True if verified/passed
            details: Optional additional details

        Returns:
            True if published successfully
        """
        if not await self._init_redis():
            return False

        try:
            stream_key = f"fungus:verification:{self.job_id}"
            await self._redis.xadd(
                stream_key,
                {
                    "type": "component_verified",
                    "component": component,
                    "status": str(status),
                    "details": json.dumps(details or {}),
                    "timestamp": str(time.time()),
                },
                maxlen=50,
            )

            self.logger.info(
                "verification_reported",
                component=component,
                status=status,
            )
            return True
        except Exception as e:
            self.logger.warning("report_verified_failed", error=str(e))
            return False

    async def get_verification_status(self) -> Dict[str, bool]:
        """
        Get current verification status for all components.

        Returns:
            Dict mapping component name to verification status
        """
        if not await self._init_redis():
            return {}

        try:
            stream_key = f"fungus:verification:{self.job_id}"
            entries = await self._redis.xrevrange(stream_key, count=100)

            status = {}
            for entry_id, data in entries:
                if data.get("type") == "component_verified":
                    component = data.get("component", "")
                    if component and component not in status:
                        status[component] = data.get("status") == "True"

            return status
        except Exception as e:
            self.logger.warning("get_status_failed", error=str(e))
            return {}

    async def close(self) -> None:
        """Clean up resources."""
        if self._redis:
            await self._redis.close()
            self._redis = None


async def main():
    """CLI entry point for testing FungusWorker."""
    import argparse

    parser = argparse.ArgumentParser(description="Test Fungus Worker")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--project-dir", help="Project directory to index")
    parser.add_argument("--job-id", default="test", help="Job ID for Redis streams")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--max-rounds", type=int, default=3)

    args = parser.parse_args()

    worker = FungusWorker(
        redis_url=args.redis_url,
        job_id=args.job_id,
        working_dir=args.project_dir,
        max_rounds=args.max_rounds,
    )

    try:
        # Index project if provided
        if args.project_dir:
            count = await worker.index_project()
            print(f"Indexed {count} documents")

        # Run simulation
        print(f"Starting simulation for: {args.query}")
        context = await worker.run_until_good_content(args.query)

        print("\nFinal Context:")
        print(json.dumps(context, indent=2, default=str))

    finally:
        await worker.close()


if __name__ == "__main__":
    asyncio.run(main())
