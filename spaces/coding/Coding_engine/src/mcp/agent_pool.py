"""
MCP Agent Pool - Spawns and manages MCP agents on demand.

This module provides the MCPAgentPool class for spawning MCP agents
as subprocesses and collecting their results.
"""
import asyncio
import os
import uuid
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
import structlog

from .registry import MCPRegistry, MCPAgentInfo, get_registry
from .project_config import ProjectMCPConfig, load_project_mcp_config

logger = structlog.get_logger()


@dataclass
class MCPAgentResult:
    """Result from an MCP agent execution."""
    agent: str
    task: str
    session_id: str
    success: bool
    output: str
    error: Optional[str]
    duration: float
    data: Optional[Dict[str, Any]] = None  # Parsed JSON data if available


class MCPAgentPool:
    """
    Pool for on-demand MCP agent spawning.

    Spawns MCP agents as subprocesses, waits for their completion,
    and returns structured results. Supports both sequential and
    parallel execution.

    Supports per-project config via .mcp-config.json that overrides
    global servers.json (env vars, paths, container names).

    Usage:
        pool = MCPAgentPool(working_dir="./my-project")

        # With project-specific config
        pool = MCPAgentPool(working_dir="./output", project_path="/data/projects/my-app")

        # Spawn single agent
        result = await pool.spawn("supermemory", "Search for React patterns")

        # Spawn multiple in parallel
        results = await pool.spawn_parallel([
            {"agent": "supermemory", "task": "Search patterns"},
            {"agent": "playwright", "task": "Test login flow"},
        ])

        # Check available agents
        available = pool.list_available()
    """

    def __init__(self, working_dir: str, registry: MCPRegistry = None,
                 project_path: str = None):
        """
        Initialize the agent pool.

        Args:
            working_dir: Working directory for agent operations
            registry: MCPRegistry instance (uses global if None)
            project_path: Optional project path to load .mcp-config.json
        """
        self.working_dir = Path(working_dir).resolve()
        self.registry = registry or get_registry()
        self._running: Dict[str, asyncio.subprocess.Process] = {}
        self._project_config: Optional[ProjectMCPConfig] = None

        # Load project-specific MCP config if available
        if project_path:
            self._project_config = load_project_mcp_config(project_path)
        if not self._project_config:
            # Try loading from working_dir parent
            self._project_config = load_project_mcp_config(str(self.working_dir))

        logger.info("mcp_agent_pool_initialized",
                   working_dir=str(self.working_dir),
                   project_config=bool(self._project_config),
                   available_agents=len(self.list_available()))

    def _build_command(self, agent_info: MCPAgentInfo, task: str,
                       session_id: str) -> List[str]:
        """Build command line for spawning an agent.

        If project config has args_override for this server, those
        replace the trailing path arguments (e.g., filesystem root dir).
        """
        cmd = []

        # Resolve command path
        command = agent_info.command
        if command == "python":
            import sys
            command = sys.executable

        cmd.append(command)

        # Check if project config has args override
        args_override = None
        if self._project_config:
            srv_override = self._project_config.servers.get(agent_info.name)
            if srv_override and srv_override.enabled and srv_override.args_override:
                args_override = srv_override.args_override

        # Add args, resolving paths
        for arg in agent_info.args:
            if arg.startswith("mcp_plugins/"):
                # Resolve relative path
                project_root = Path(__file__).parent.parent.parent
                arg = str(project_root / arg)
            cmd.append(arg)

        # Replace trailing path args if override exists
        # (e.g., filesystem server: npx ... @mcp/server-filesystem /old/path → /new/path)
        if args_override:
            # Find where path-like args start (after the npm/python command parts)
            # Override replaces only the trailing non-flag arguments
            non_flag_end = []
            for i in range(len(cmd) - 1, 0, -1):
                if cmd[i].startswith("-") or cmd[i].startswith("@"):
                    break
                non_flag_end.insert(0, i)
            if non_flag_end:
                # Replace trailing path args with overrides
                cmd = cmd[:non_flag_end[0]] + args_override
            else:
                # Just append
                cmd.extend(args_override)

        # Add standard CLI args for custom Python agents
        if agent_info.server_type == "custom":
            cmd.extend(["--task", task])
            cmd.extend(["--session-id", session_id])
            cmd.extend(["--working-dir", str(self.working_dir)])

        return cmd

    def _build_env(self, agent_info: MCPAgentInfo) -> Dict[str, str]:
        """Build environment variables for spawning.

        Merges: OS env → servers.json env_vars → project .mcp-config.json overrides
        """
        env = os.environ.copy()

        # 1. Add agent-specific env vars from servers.json
        for key, value in agent_info.env_vars.items():
            if isinstance(value, str) and value.startswith("env:"):
                # Resolve from environment
                env_name = value.split(":", 1)[1]
                env_value = os.getenv(env_name, "")
                env[key] = env_value
            else:
                env[key] = str(value)

        # 2. Override with project-specific config (highest priority)
        if self._project_config:
            srv_override = self._project_config.servers.get(agent_info.name)
            if srv_override and srv_override.enabled:
                for key, value in srv_override.env_vars.items():
                    env[key] = str(value)

            # Always inject project context vars
            env["MCP_PROJECT_ID"] = self._project_config.project_id
            env["MCP_PROJECT_PATH"] = self._project_config.project_path
            env["MCP_OUTPUT_DIR"] = self._project_config.output_dir
            env["MCP_SANDBOX_CONTAINER"] = self._project_config.sandbox_container
            env["MCP_VNC_PORT"] = str(self._project_config.vnc_port)
            env["MCP_APP_PORT"] = str(self._project_config.app_port)

        # Ensure UTF-8 encoding
        env["PYTHONIOENCODING"] = "utf-8"

        return env

    async def spawn(self, agent_name: str, task: str,
                    session_id: str = None,
                    timeout: int = None) -> MCPAgentResult:
        """
        Spawn an MCP agent and wait for result.

        Args:
            agent_name: Name of the agent to spawn (e.g., "supermemory")
            task: Task description for the agent
            session_id: Optional session ID (auto-generated if None)
            timeout: Timeout in seconds (uses agent default if None)

        Returns:
            MCPAgentResult with output and status
        """
        import time
        start_time = time.time()

        # Generate session ID if not provided
        if not session_id:
            session_id = f"{agent_name}_{uuid.uuid4().hex[:8]}"

        # Get agent info
        agent_info = self.registry.get_agent(agent_name)
        if not agent_info:
            return MCPAgentResult(
                agent=agent_name,
                task=task,
                session_id=session_id,
                success=False,
                output="",
                error=f"Agent '{agent_name}' not found in registry",
                duration=0,
            )

        # Check requirements
        if not self.registry.is_available(agent_name):
            missing = self.registry.get_missing_requirements(agent_name)
            return MCPAgentResult(
                agent=agent_name,
                task=task,
                session_id=session_id,
                success=False,
                output="",
                error=f"Missing requirements: {', '.join(missing)}",
                duration=0,
            )

        # Build command and environment
        cmd = self._build_command(agent_info, task, session_id)
        env = self._build_env(agent_info)
        timeout = timeout or agent_info.read_timeout

        logger.info("mcp_agent_spawning",
                   agent=agent_name,
                   session_id=session_id,
                   task=task[:50])

        try:
            # Spawn subprocess
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
                env=env,
            )

            self._running[session_id] = proc

            # Wait for completion with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                duration = time.time() - start_time
                return MCPAgentResult(
                    agent=agent_name,
                    task=task,
                    session_id=session_id,
                    success=False,
                    output="",
                    error=f"Timeout after {timeout}s",
                    duration=duration,
                )

            duration = time.time() - start_time
            output = stdout.decode('utf-8', errors='replace')
            error_output = stderr.decode('utf-8', errors='replace')

            success = proc.returncode == 0

            # Try to parse structured output
            data = None
            if success and output:
                try:
                    # Look for JSON in output
                    for line in output.splitlines():
                        line = line.strip()
                        if line.startswith('{') and line.endswith('}'):
                            data = json.loads(line)
                            break
                except json.JSONDecodeError:
                    pass

            logger.info("mcp_agent_completed",
                       agent=agent_name,
                       session_id=session_id,
                       success=success,
                       duration=round(duration, 2))

            return MCPAgentResult(
                agent=agent_name,
                task=task,
                session_id=session_id,
                success=success,
                output=output,
                error=error_output if not success else None,
                duration=duration,
                data=data,
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.error("mcp_agent_spawn_error",
                        agent=agent_name,
                        error=str(e))
            return MCPAgentResult(
                agent=agent_name,
                task=task,
                session_id=session_id,
                success=False,
                output="",
                error=str(e),
                duration=duration,
            )

        finally:
            self._running.pop(session_id, None)

    async def spawn_parallel(self, tasks: List[Dict[str, Any]],
                             max_concurrent: int = 5) -> List[MCPAgentResult]:
        """
        Spawn multiple agents in parallel.

        Args:
            tasks: List of task dicts with 'agent' and 'task' keys
                   Optional: 'session_id', 'timeout'
            max_concurrent: Maximum concurrent agents

        Returns:
            List of MCPAgentResult in same order as input tasks
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def spawn_with_semaphore(task_dict: dict) -> MCPAgentResult:
            async with semaphore:
                return await self.spawn(
                    agent_name=task_dict["agent"],
                    task=task_dict["task"],
                    session_id=task_dict.get("session_id"),
                    timeout=task_dict.get("timeout"),
                )

        coros = [spawn_with_semaphore(t) for t in tasks]
        return await asyncio.gather(*coros)

    def list_available(self) -> List[str]:
        """
        List agents that can be spawned (requirements met).

        Returns:
            List of agent names
        """
        return self.registry.list_available()

    def list_running(self) -> List[str]:
        """
        List currently running agent sessions.

        Returns:
            List of session IDs
        """
        return list(self._running.keys())

    async def stop(self, session_id: str) -> bool:
        """
        Stop a running agent.

        Args:
            session_id: Session ID to stop

        Returns:
            True if stopped, False if not found
        """
        proc = self._running.get(session_id)
        if proc:
            proc.kill()
            await proc.wait()
            self._running.pop(session_id, None)
            logger.info("mcp_agent_stopped", session_id=session_id)
            return True
        return False

    async def stop_all(self):
        """Stop all running agents."""
        for session_id in list(self._running.keys()):
            await self.stop(session_id)


# Module-level pool instance
_pool_instance: Optional[MCPAgentPool] = None


def get_pool(working_dir: str = ".") -> MCPAgentPool:
    """Get or create the global MCPAgentPool instance."""
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = MCPAgentPool(working_dir)
    return _pool_instance


if __name__ == "__main__":
    # Test pool
    import sys

    async def test_pool():
        print("Testing MCPAgentPool...")

        pool = MCPAgentPool(working_dir=".")

        print(f"\nAvailable agents: {pool.list_available()}")

        # Test spawning supermemory if available
        if "supermemory" in pool.list_available():
            print("\nSpawning supermemory agent...")
            result = await pool.spawn(
                "supermemory",
                "Search for React component patterns",
                timeout=60
            )
            print(f"  Success: {result.success}")
            print(f"  Duration: {result.duration:.1f}s")
            if result.error:
                print(f"  Error: {result.error[:100]}")
            if result.output:
                print(f"  Output (last 200 chars): ...{result.output[-200:]}")
        else:
            print("\nSupermemory not available (missing SUPERMEMORY_API_KEY)")

    asyncio.run(test_pool())
