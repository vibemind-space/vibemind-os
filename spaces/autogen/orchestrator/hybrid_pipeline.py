"""
HybridPipeline — Orchestrates AgentFarm pipeline steps across 3 layers:

- Swarm (LLM reasoning via Minibook)
- OpenClaw (sandboxed Docker execution + user communication, no timeout)
- Claude CLI (code generation via ACP)

Replaces the monolithic SwarmPipeline.run() with a step-by-step controller
that routes each step to the appropriate orchestrator.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .openclaw_bridge import OpenClawBridge
from .step_registry import PIPELINE_STEPS, get_step_order

logger = logging.getLogger(__name__)

# Broadcast to Electron UI (optional)
try:
    from tools.workspace_tools import _broadcast_to_electron
except ImportError:
    def _broadcast_to_electron(msg):
        pass


class HybridPipeline:
    """Orchestrates 13 pipeline steps across Swarm, OpenClaw, and Claude CLI."""

    def __init__(self):
        self.openclaw = OpenClawBridge()
        self._status = "idle"
        self._current_step = None
        self._step_results: Dict[str, Any] = {}
        self._start_time = None
        self._task_description = ""
        self._project_id = ""
        self._agents = {}
        self._pipeline = None  # SwarmPipeline instance (for Swarm steps)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, task_description: str, channel: str = None) -> Dict[str, Any]:
        """Run the full hybrid pipeline using original SwarmPipeline.run().

        The original pipeline handles @mention chains between steps internally.
        HybridPipeline wraps it with: Setup, Status-Updates, Channel-Communication.

        Args:
            task_description: What to build (e.g. "Agent team for data analysis")
            channel: OpenClaw channel for user communication (e.g. "whatsapp")
        """
        import aiohttp

        self._status = "starting"
        self._task_description = task_description
        self._start_time = time.time()

        # 1. Connect to OpenClaw (optional — falls back gracefully)
        openclaw_available = await self.openclaw.connect()
        if openclaw_available:
            await self.openclaw.send_status(
                f"Pipeline gestartet: {task_description[:100]}...", channel
            )

        # 2. Setup Minibook (register agents + create project)
        try:
            setup = await self._setup_minibook()
            self._agents = setup["agents"]
            self._project_id = setup["project_id"]
        except Exception as e:
            self._status = "error"
            return {"success": False, "message": f"Minibook setup failed: {e}"}

        # 3. Create SwarmPipeline (lazy-loaded from submodule)
        from spaces.autogen.wrapper import _ensure_pipeline_loaded
        _ensure_pipeline_loaded()
        from spaces.autogen.wrapper import SwarmPipeline
        self._pipeline = SwarmPipeline(
            agents=self._agents,
            project_id=self._project_id,
            task_name=task_description[:80],
        )

        # 4. Inject Claude CLI via OpenClaw ACP into pipeline's _call_claude_code
        if openclaw_available:
            original_call = self._pipeline._call_claude_code

            async def _patched_call_claude_code(prompt: str) -> str:
                """Route through OpenClaw ACP first, fall back to original."""
                try:
                    result = await self.openclaw.delegate_to_claude_cli(prompt, timeout=300.0)
                    if result["success"] and result["output"]:
                        logger.info("[ACP] Claude CLI via OpenClaw returned code")
                        return result["output"]
                except Exception as e:
                    logger.debug(f"[ACP] OpenClaw delegation failed: {e}, using original")
                return await original_call(prompt)

            self._pipeline._call_claude_code = _patched_call_claude_code
            logger.info("Patched pipeline._call_claude_code → OpenClaw ACP")

        # 5. Run the ORIGINAL pipeline.run() — it handles @mention chains internally
        self._status = "running"
        _broadcast_to_electron({
            "type": "agentfarm_pipeline_started",
            "task": task_description[:100],
            "project_id": self._project_id,
        })

        try:
            async with aiohttp.ClientSession() as session:
                success = await self._pipeline.run(session, task_description)
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            self._status = "error"
            if openclaw_available:
                await self.openclaw.send_status(f"Pipeline fehlgeschlagen: {e}", channel)
            return {"success": False, "message": f"Pipeline failed: {e}"}

        # 5. Summary
        elapsed = time.time() - self._start_time
        self._status = "completed"
        steps_done = len(self._pipeline.completed_steps) if hasattr(self._pipeline, "completed_steps") else 0
        summary = {
            "success": success,
            "steps_completed": steps_done,
            "total_steps": 13,
            "elapsed_seconds": round(elapsed, 1),
            "project_id": self._project_id,
            "task": task_description,
            "output_path": str(self._pipeline.output_path) if self._pipeline.output_path else None,
            "generated_files": len(self._pipeline.generated_files),
            "yaml_files": len(self._pipeline.yaml_files),
        }
        if openclaw_available:
            await self.openclaw.send_status(
                f"Pipeline fertig! {steps_done}/13 Steps in {elapsed:.0f}s. "
                f"Output: {self._pipeline.output_path}", channel
            )
            await self.openclaw.disconnect()

        _broadcast_to_electron({
            "type": "agentfarm_pipeline_completed",
            "project_id": self._project_id, **summary,
        })
        return summary

    def get_status(self) -> Dict[str, Any]:
        """Get current pipeline status."""
        elapsed = round(time.time() - self._start_time, 1) if self._start_time else 0
        return {
            "status": self._status,
            "current_step": self._current_step,
            "task": self._task_description,
            "project_id": self._project_id,
            "elapsed": elapsed,
            "step_results": {
                k: "ok" if not isinstance(v, dict) or not v.get("error") else v["error"]
                for k, v in self._step_results.items()
            },
        }

    # ------------------------------------------------------------------
    # Step Execution Router
    # ------------------------------------------------------------------

    async def _execute_step(self, step_name: str, config, channel: str = None):
        """Route step to Swarm, OpenClaw, or Claude CLI."""
        if config.orchestrator == "swarm":
            return await self._run_swarm_step(step_name, channel)
        elif config.orchestrator == "openclaw":
            return await self._run_openclaw_step(step_name, config, channel)
        elif config.orchestrator == "claude_cli":
            return await self._run_claude_cli_step(step_name, config, channel)
        else:
            raise ValueError(f"Unknown orchestrator: {config.orchestrator}")

    # ------------------------------------------------------------------
    # Swarm Steps (LLM Reasoning via Minibook)
    # ------------------------------------------------------------------

    async def _run_swarm_step(self, step_name: str, channel: str = None):
        """Execute step via SwarmPipeline's native Minibook agents."""
        import aiohttp, inspect
        async with aiohttp.ClientSession() as session:
            method = getattr(self._pipeline, f"step_{step_name}", None)
            if method is None:
                raise AttributeError(f"SwarmPipeline has no step_{step_name}")
            # Some steps take (session, task_description), others just (session)
            sig = inspect.signature(method)
            params = list(sig.parameters.keys())
            if len(params) >= 2:
                result = await method(session, self._task_description)
            else:
                result = await method(session)

            # Log pipeline state after each step
            logger.info(
                f"[Swarm:{step_name}] files={len(self._pipeline.generated_files)} "
                f"yamls={len(self._pipeline.yaml_files)} "
                f"output_path={self._pipeline.output_path}"
            )
            return {"output": str(result)[:500] if result else "ok"}

    # ------------------------------------------------------------------
    # OpenClaw Steps (Sandboxed Docker + User Interaction)
    # ------------------------------------------------------------------

    async def _run_openclaw_step(self, step_name: str, config, channel: str = None):
        """Execute step via OpenClaw (Docker sandbox, user questions)."""
        handler = {
            "catalog": self._openclaw_catalog,
            "builder": self._openclaw_docker_build,
            "executor": self._openclaw_docker_run,
            "output_eval": self._openclaw_output_assessment,
            "export": self._openclaw_export,
        }.get(step_name)

        if handler:
            return await handler(channel)
        # Fallback to swarm for unhandled openclaw steps
        return await self._run_swarm_step(step_name, channel)

    async def _openclaw_catalog(self, channel: str = None):
        """MCP server discovery + user selection (no timeout)."""
        # Try Docker MCP discovery; fall back to defaults if Docker unavailable
        try:
            from spaces.autogen.wrapper import _ensure_pipeline_loaded
            _ensure_pipeline_loaded()
            # Import from the loaded submodule namespace
            import sys
            docker_ops = sys.modules.get("swarm.docker_ops")
            if docker_ops and hasattr(docker_ops, "get_installed_mcp_servers"):
                installed = await docker_ops.get_installed_mcp_servers()
            else:
                installed = []
        except Exception as e:
            logger.warning(f"MCP discovery failed: {e}, using defaults")
            installed = []

        # Add default servers (context7, web_fetch, filesystem)
        default_names = {"context7", "web_fetch", "filesystem"}
        for name in default_names:
            if not any(s.get("name") == name for s in installed):
                installed.append({"name": name, "description": f"Default: {name}"})

        if self.openclaw.is_connected:
            server_list = [f"{s['name']} - {s.get('description', '')}" for s in installed]
            answer = await self.openclaw.ask_user(
                "Welche MCP-Server sollen aktiviert werden?",
                channel=channel, options=server_list,
            )
            if answer:
                selected = [s["name"] for i, s in enumerate(installed)
                            if str(i + 1) in answer or s["name"].lower() in answer.lower()]
            else:
                selected = [s["name"] for s in installed]
        else:
            selected = [s["name"] for s in installed]

        return {"selected_servers": selected}

    async def _openclaw_docker_build(self, channel: str = None):
        """Docker build via OpenClaw sandbox (no timeout)."""
        build_dir = str(self._pipeline.output_path) if self._pipeline.output_path else ""
        if not build_dir:
            # Try to build from generated files directly
            logger.warning("No output_path — validator may not have written files. Skipping Docker build.")
            return {"output": "Skipped — no output path (validator step may have failed)", "skipped": True}
        result = await self.openclaw.docker_build(build_dir)
        if not result["success"] and self.openclaw.is_connected:
            await self.openclaw.send_status("Docker Build fehlgeschlagen. Auto-Fix...", channel)
        return result

    async def _openclaw_docker_run(self, channel: str = None):
        """Docker run via OpenClaw sandbox (no timeout)."""
        build_dir = str(self._pipeline.output_path) if self._pipeline.output_path else ""
        if not build_dir:
            return {"output": "Skipped — no build output", "skipped": True}
        return await self.openclaw.docker_run(build_dir)

    async def _openclaw_output_assessment(self, channel: str = None):
        """Claude CLI generates test, OpenClaw runs in Docker."""
        yaml_ctx = self._pipeline.architect_output or ""
        cli_result = await self.openclaw.delegate_to_claude_cli(
            f"Generate a concrete test task for this AutoGen agent team:\n{yaml_ctx[:2000]}"
        )
        test_task = cli_result.get("output", "Run a basic test")

        build_dir = str(self._pipeline.output_path) if self._pipeline.output_path else ""
        run_result = await self.openclaw.run_in_sandbox(
            ["docker", "compose", "-f", f"{build_dir}/docker-compose.yml",
             "run", "--rm", "host", "python", "main.py", test_task],
            workdir=build_dir,
        )
        return {"test_task": test_task, "run_result": run_result}

    async def _openclaw_export(self, channel: str = None):
        """Export to Git via OpenClaw filesystem access."""
        output = str(self._pipeline.output_path) if self._pipeline.output_path else ""
        if not output:
            return {"output": "Skipped — no output to export", "skipped": True}

        # Init git repo + initial commit
        await self.openclaw.run_in_sandbox(["git", "init"], workdir=output, timeout=15.0)
        await self.openclaw.run_in_sandbox(["git", "add", "."], workdir=output, timeout=15.0)
        result = await self.openclaw.run_in_sandbox(
            ["git", "commit", "-m", f"Generated by VibeMind HybridPipeline: {self._task_description[:60]}"],
            workdir=output, timeout=15.0,
        )

        if self.openclaw.is_connected:
            await self.openclaw.send_status(f"Exported to: {output}", channel)

        return {"output": output, "git_init": True, **result}

    # ------------------------------------------------------------------
    # Claude CLI Steps (Code Generation via ACP)
    # ------------------------------------------------------------------

    async def _run_claude_cli_step(self, step_name: str, config, channel: str = None):
        """Execute step via Claude CLI (ACP)."""
        handler = {
            "coder": self._cli_coder,
            "todo_implement": self._cli_todo_implement,
        }.get(step_name)

        if handler:
            return await handler(channel)
        return await self._run_swarm_step(step_name, channel)

    async def _cli_coder(self, channel: str = None):
        """Generate tools.py via Claude CLI (better than GPT-4o)."""
        yaml_ctx = self._pipeline.architect_output or ""
        mcp_tools = self._pipeline.mcp_tools_prompt or ""

        result = await self.openclaw.delegate_to_claude_cli(
            f"Generate src/tools.py for this AutoGen agent team.\n\n"
            f"YAML Architecture:\n{yaml_ctx[:3000]}\n\n"
            f"Available MCP tools:\n{mcp_tools[:2000]}\n\n"
            f"Requirements:\n"
            f"- Typed parameters (no **kwargs)\n"
            f"- Proper docstrings\n"
            f"- async def for I/O operations\n"
            f"- Use MCP tools where applicable",
            timeout=300.0,
        )
        if result["success"]:
            self._pipeline.generated_files["src/tools.py"] = result["output"]
        return result

    async def _cli_todo_implement(self, channel: str = None):
        """Implement TODO stubs via Claude CLI."""
        tools_py = self._pipeline.generated_files.get("src/tools.py", "")

        # Try reading from output_path if not in memory
        if not tools_py and self._pipeline.output_path:
            tools_path = Path(str(self._pipeline.output_path)) / "src" / "tools.py"
            if tools_path.exists():
                tools_py = tools_path.read_text(encoding="utf-8", errors="replace")

        if not tools_py:
            return {"output": "No tools.py found — skipping TODO implementation", "skipped": True}

        todos = [line.strip() for line in tools_py.splitlines()
                 if "# TODO" in line or "# todo" in line]
        if not todos:
            return {"success": True, "message": "No TODOs found"}

        todo_text = "\n".join(todos[:20])
        result = await self.openclaw.delegate_to_claude_cli(
            f"Implement these TODO functions in tools.py.\n\n"
            f"TODOs found:\n{todo_text}\n\n"
            f"Current tools.py:\n{tools_py[:5000]}",
            timeout=300.0,
        )
        if result["success"]:
            self._pipeline.generated_files["src/tools.py"] = result["output"]
        return result

    # ------------------------------------------------------------------
    # Minibook Setup
    # ------------------------------------------------------------------

    async def _setup_minibook(self) -> Dict[str, Any]:
        """Register agents + create project at Minibook."""
        from spaces.autogen.tools.agentfarm_tools import _ensure_minibook_setup
        return await _ensure_minibook_setup()
