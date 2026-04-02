"""Async team runner for Autogen 0.4 multi-agent teams.

Non-blocking: uses asyncio.create_task() since Autogen 0.4 is async-native.
LLM API calls are I/O-bound, so the event loop stays free for voice and other agents.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

try:
    from tools.workspace_tools import _broadcast_to_electron
except ImportError:
    def _broadcast_to_electron(msg):
        pass


@dataclass
class RunState:
    """State for a single team run."""
    run_id: str
    team_id: str
    task: str
    status: str = "running"
    step_count: int = 0
    messages: List[Dict] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    cancel_token: object = None  # autogen_core.CancellationToken, lazy-imported in start_run


class TeamRunner:
    """Singleton manager for async Autogen 0.4 team runs."""

    _instance: Optional["TeamRunner"] = None
    MAX_COMPLETED_RUNS = 50

    def __init__(self):
        self._active_runs: Dict[str, RunState] = {}

    @classmethod
    def get_instance(cls) -> "TeamRunner":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start_run(self, team_id: str, team_config: dict, task: str) -> str:
        """Start a team run. Returns run_id immediately."""
        from autogen_core import CancellationToken

        run_id = str(uuid4())
        state = RunState(run_id=run_id, team_id=team_id, task=task)
        state.cancel_token = CancellationToken()
        self._active_runs[run_id] = state
        self._prune_completed()
        asyncio.create_task(self._execute_run(state, team_config))
        _broadcast_to_electron({
            "type": "agentfarm_run_started",
            "run_id": run_id,
            "team_id": team_id,
            "task": task,
        })
        return run_id

    async def _execute_run(self, state: RunState, team_config: dict):
        """Background execution. Streams progress via Electron broadcast."""
        try:
            team = self._build_team(team_config)
            async for message in team.run_stream(
                task=state.task,
                cancellation_token=state.cancel_token,
            ):
                state.step_count += 1
                entry = {
                    "source": getattr(message, "source", "unknown"),
                    "content": getattr(message, "content", str(message)),
                }
                state.messages.append(entry)
                _broadcast_to_electron({
                    "type": "agentfarm_progress",
                    "run_id": state.run_id,
                    "agent": entry["source"],
                    "content": entry["content"],
                    "step": state.step_count,
                })
            state.status = "completed"
        except asyncio.CancelledError:
            state.status = "cancelled"
        except Exception as e:
            state.status = "failed"
            state.error = str(e)
            logger.error(f"TeamRunner run {state.run_id} failed: {e}")
        finally:
            state.completed_at = datetime.now()
            _broadcast_to_electron({
                "type": "agentfarm_run_finished",
                "run_id": state.run_id,
                "status": state.status,
                "step_count": state.step_count,
                "error": state.error,
            })

    def cancel_run(self, run_id: str) -> bool:
        """Cancel a running team. Returns True if cancelled."""
        state = self._active_runs.get(run_id)
        if state and state.status == "running" and state.cancel_token:
            state.cancel_token.cancel()
            return True
        return False

    def get_status(self) -> Dict:
        """Return status of all runs."""
        return {
            run_id: {
                "team_id": s.team_id,
                "status": s.status,
                "step_count": s.step_count,
                "task": s.task,
                "started_at": s.started_at.isoformat(),
            }
            for run_id, s in self._active_runs.items()
        }

    def get_run(self, run_id: str) -> Optional[RunState]:
        """Get a specific run state."""
        return self._active_runs.get(run_id)

    def _prune_completed(self):
        """Remove oldest completed runs to prevent memory leak."""
        completed = [
            (rid, s) for rid, s in self._active_runs.items()
            if s.status in ("completed", "failed", "cancelled")
        ]
        if len(completed) > self.MAX_COMPLETED_RUNS:
            completed.sort(key=lambda x: x[1].completed_at or datetime.min)
            for rid, _ in completed[: len(completed) - self.MAX_COMPLETED_RUNS]:
                del self._active_runs[rid]

    def _build_team(self, config: dict):
        """Build Autogen 0.4 team from config dict.

        Supports team_type: "selector" (default), "round_robin", "swarm".
        """
        from llm_config import get_model
        from autogen_agentchat.agents import AssistantAgent
        from autogen_agentchat.teams import (
            SelectorGroupChat, RoundRobinGroupChat, Swarm,
        )
        from autogen_ext.models.openai import OpenAIChatCompletionClient

        model_client = OpenAIChatCompletionClient(
            model=config.get("model") or get_model("agentfarm"),
        )
        agents = []
        for agent_cfg in config.get("agents", []):
            agents.append(AssistantAgent(
                name=agent_cfg["name"],
                system_message=agent_cfg.get("system_message", ""),
                model_client=model_client,
            ))

        team_type = config.get("team_type", "selector")
        team_classes = {
            "selector": SelectorGroupChat,
            "round_robin": RoundRobinGroupChat,
            "swarm": Swarm,
        }
        team_cls = team_classes.get(team_type, SelectorGroupChat)
        return team_cls(participants=agents, model_client=model_client)
