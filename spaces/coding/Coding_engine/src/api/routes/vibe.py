"""
Vibe-Coding API routes (Phase 31).

Enables real-time user intervention during pipeline execution.
Dashboard chat -> LLM agent router -> Claude CLI streaming -> EventBus.
"""
import asyncio
import json
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/vibe", tags=["Vibe-Coding"])


# --- Agent Router ---

VALID_AGENTS = {
    "coder", "debugger", "database-agent", "api-generator",
    "test-runner", "security-auditor", "deployment-agent",
    "code-reviewer", "planner", "epic-analyzer",
    "architecture-explorer", "external-services",
}

ROUTER_PROMPT = """You are an agent router. Given a user request about code, select the best agent. Reply with ONLY the agent name, nothing else.

Agents:
- coder: Create/modify UI components, pages, styles, features, general coding
- debugger: Fix errors, trace bugs, analyze stack traces, crashes
- database-agent: Schema changes, Prisma migrations, seeding, PostgreSQL
- api-generator: REST endpoints, NestJS controllers, DTOs, guards
- test-runner: Run tests, analyze test failures
- security-auditor: Security scan, find vulnerabilities (read-only)
- deployment-agent: Docker, containers, compose, health checks
- code-reviewer: Code quality review, convention check

User request: {prompt}

Agent:"""

KEYWORD_RULES = {
    "debugger": ["error", "bug", "fix", "crash", "broken", "fails", "stack trace",
                 "nicht funktioniert", "kaputt", "fehler", "traceback", "exception"],
    "database-agent": ["schema", "prisma", "migration", "database", "table", "seed",
                       "postgres", "datenbank", "model"],
    "api-generator": ["endpoint", "route", "controller", "dto", "crud", "rest", "api",
                      "nestjs", "guard"],
    "test-runner": ["test", "run tests", "pytest", "vitest", "failing test", "spec"],
    "security-auditor": ["security", "audit", "vulnerability", "secret", "injection",
                         "hardcoded", "xss", "csrf"],
    "deployment-agent": ["docker", "container", "deploy", "compose", "health check",
                         "kubernetes", "port"],
    "code-reviewer": ["review", "quality", "convention", "check code", "refactor"],
}


def _keyword_fallback(prompt: str) -> str:
    """Select agent based on keyword matching. Zero latency fallback."""
    prompt_lower = prompt.lower()
    scores = {}
    for agent, keywords in KEYWORD_RULES.items():
        score = sum(1 for kw in keywords if kw in prompt_lower)
        if score > 0:
            scores[agent] = score
    if scores:
        return max(scores, key=scores.get)
    return "coder"


async def _llm_classify(prompt: str) -> str:
    """Use Haiku to classify user intent into an agent name."""
    try:
        import anthropic
        client = anthropic.Anthropic()

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=20,
                messages=[{"role": "user", "content": ROUTER_PROMPT.format(prompt=prompt)}],
            )
        )
        return response.content[0].text.strip().lower()
    except Exception as e:
        logger.warning("llm_classify_failed", error=str(e))
        raise


async def route_to_agent(prompt: str) -> str:
    """Route a user prompt to the best Claude Code agent."""
    try:
        agent = await _llm_classify(prompt)
        # Clean up: strip whitespace, dashes at edges
        agent = agent.strip().strip('"').strip("'")
        if agent in VALID_AGENTS:
            logger.info("agent_routed_llm", agent=agent, prompt_preview=prompt[:60])
            return agent
        logger.warning("llm_returned_invalid_agent", raw=agent)
    except Exception:
        pass

    agent = _keyword_fallback(prompt)
    logger.info("agent_routed_keyword", agent=agent, prompt_preview=prompt[:60])
    return agent


# --- Vibe History ---

_vibe_history: list[dict] = []


class VibeHistoryEntry(BaseModel):
    id: str
    prompt: str
    agent: str
    files: list[str]
    success: bool
    timestamp: str
    session_id: Optional[str] = None


@router.get("/history")
async def get_vibe_history() -> list[VibeHistoryEntry]:
    """Get past vibe-coding interventions."""
    return [VibeHistoryEntry(**h) for h in _vibe_history[-50:]]


# --- WebSocket Streaming ---

@router.websocket("/ws/{project_id}")
async def vibe_websocket(websocket: WebSocket, project_id: str):
    """
    WebSocket endpoint for vibe-coding with live streaming.

    Client sends: {"prompt": "...", "output_dir": "...", "session_id": "..."}
    Server streams: {"type": "agent"|"text"|"tool_use"|"error"|"complete", ...}
    """
    await websocket.accept()
    logger.info("vibe_ws_connected", project_id=project_id)

    try:
        while True:
            data = await websocket.receive_json()
            prompt = data.get("prompt", "")
            output_dir = data.get("output_dir", ".")
            prev_session_id = data.get("session_id")

            if not prompt:
                await websocket.send_json({"type": "error", "message": "Empty prompt"})
                continue

            # Route to agent
            agent = await route_to_agent(prompt)
            await websocket.send_json({"type": "agent", "name": agent})

            # Stream Claude CLI output
            from src.autogen.cli_wrapper import ClaudeCLI
            cli = ClaudeCLI(working_dir=output_dir, agent_name=f"vibe_{agent}")

            changed_files = []
            session_id = None

            async for frame in cli.execute_streaming(
                prompt=prompt,
                agent_name=agent,
                max_turns=15,
                session_id=prev_session_id,
            ):
                await websocket.send_json(frame)

                if frame.get("type") == "complete":
                    changed_files = frame.get("files", [])
                    session_id = frame.get("session_id")

            # Mark files as user-managed in SharedState (shared instance from main.py)
            if changed_files:
                try:
                    from src.api.main import shared_state as _shared_state
                    if _shared_state:
                        _shared_state.mark_user_managed(changed_files)
                        logger.info("user_managed_marked", files=changed_files)
                    else:
                        logger.debug("shared_state_not_set", hint="run_engine.py did not inject SharedState")
                except Exception as e:
                    logger.warning("shared_state_update_failed", error=str(e))

            # Publish CODE_FIXED to EventBus (shared instance from main.py)
            if changed_files:
                try:
                    from src.api.main import event_bus
                    from src.mind.event_bus import Event, EventType
                    await event_bus.publish(Event(
                        type=EventType.CODE_FIXED,
                        source="user_vibe",
                        data={
                            "source": "user_vibe",
                            "files": changed_files,
                            "agent": agent,
                            "session_id": session_id,
                        },
                        success=True,
                    ))
                    logger.info("vibe_code_fixed_published", files=changed_files, agent=agent)
                except Exception as e:
                    logger.warning("eventbus_publish_failed", error=str(e))

            # Record in history
            entry = {
                "id": str(uuid.uuid4()),
                "prompt": prompt,
                "agent": agent,
                "files": changed_files,
                "success": True,
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
            }
            _vibe_history.append(entry)

    except WebSocketDisconnect:
        logger.info("vibe_ws_disconnected", project_id=project_id)
    except Exception as e:
        logger.error("vibe_ws_error", error=str(e))
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
