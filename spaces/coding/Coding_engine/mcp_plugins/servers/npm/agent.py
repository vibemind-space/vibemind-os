#!/usr/bin/env python3
"""
npm/pnpm MCP Agent - Package management operations.

Provides:
- Package installation (npm install / pnpm add)
- Script execution (npm run)
- Dependency listing and auditing
- Package.json management

Follows Society of Mind pattern with EventServer broadcasting.
Uses custom tools (no external MCP server required).
"""
import asyncio
import json
import os
import sys
import time
from dataclasses import field
from pathlib import Path
from typing import Optional, List

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Load .env from project root
try:
    import dotenv
    # Path: mcp_plugins/servers/npm/agent.py -> go up 3 levels to project root
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    dotenv.load_dotenv(dotenv_path=env_path)
except Exception:
    pass

# Autogen imports
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_core.model_context import BufferedChatCompletionContext
from pydantic import BaseModel

# Import global LLM config
from src.llm_config import get_model

# Shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from event_server import EventServer, start_ui_server
from constants import (
    MCP_EVENT_SESSION_ANNOUNCE,
    SESSION_STATE_RUNNING,
    SESSION_STATE_STOPPED,
    SESSION_STATE_ERROR,
)
from model_init import init_model_client as shared_init_model_client
from logging_utils import setup_logging
from conversation_logger import ConversationLogger, SenseCategory


class NpmAgentConfig(BaseModel):
    """Configuration for npm/pnpm MCP Agent."""
    session_id: str
    task: str
    name: str = "npm-session"
    model: str = field(default_factory=lambda: get_model("mcp_agent"))
    working_dir: str = "."
    package_manager: str = "npm"  # "npm" or "pnpm"


# System prompts
NPM_OPERATOR_PROMPT = """You are a Node.js package management expert with deep knowledge of npm and pnpm.

Your capabilities include:
- Installing packages (npm_install)
- Running scripts (npm_run)
- Listing dependencies (npm_list)
- Security auditing (npm_audit)
- Reading package.json (read_package_json)

Guidelines:
1. Always check package.json before installing to avoid duplicates
2. Use --save-dev for development dependencies
3. Run audit after installing new packages
4. Explain what each package does when installing
5. Handle errors gracefully and suggest fixes

When you have completed the task, say "TASK_COMPLETE".
"""

QA_VALIDATOR_PROMPT = """You are a QA Validator for npm/pnpm operations.

Your role:
1. Verify that package operations completed successfully
2. Check for security vulnerabilities after installation
3. Ensure dependencies are appropriate for the project
4. Validate that the task was completed correctly

When the task is fully validated, say "TASK_COMPLETE".
"""


class NpmTools:
    """Custom npm/pnpm tool implementations."""

    def __init__(self, working_dir: str, package_manager: str = "npm"):
        self.working_dir = Path(working_dir).resolve()
        self.pm = package_manager
        self.logger = None

    async def _run_command(self, *args: str, timeout: int = 120) -> dict:
        """Run a command and return the result."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(self.working_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                return {
                    "success": False,
                    "error": f"Command timed out after {timeout}s",
                    "command": " ".join(args)
                }

            return {
                "success": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": stdout.decode('utf-8', errors='replace'),
                "stderr": stderr.decode('utf-8', errors='replace'),
                "command": " ".join(args)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "command": " ".join(args)
            }

    async def npm_install(self, package: str = None, dev: bool = False) -> dict:
        """Install npm packages.

        Args:
            package: Package name to install (optional, installs from package.json if omitted)
            dev: Whether to install as dev dependency

        Returns:
            Dict with success status and output
        """
        cmd = [self.pm, "install"]
        if package:
            cmd.append(package)
        if dev:
            cmd.append("--save-dev" if self.pm == "npm" else "-D")

        result = await self._run_command(*cmd)
        return result

    async def npm_run(self, script: str) -> dict:
        """Run an npm script.

        Args:
            script: Name of the script to run (e.g., "build", "test", "dev")

        Returns:
            Dict with success status and output
        """
        result = await self._run_command(self.pm, "run", script)
        return result

    async def npm_list(self, depth: int = 0) -> dict:
        """List installed packages.

        Args:
            depth: How deep to traverse the dependency tree (default: 0 = top-level only)

        Returns:
            Dict with package list
        """
        result = await self._run_command(self.pm, "list", f"--depth={depth}")
        return result

    async def npm_audit(self) -> dict:
        """Run security audit on installed packages.

        Returns:
            Dict with audit results including vulnerabilities
        """
        result = await self._run_command(self.pm, "audit", "--json")

        # Try to parse JSON output
        if result.get("success") or result.get("stdout"):
            try:
                audit_data = json.loads(result.get("stdout", "{}"))
                result["audit"] = audit_data
            except json.JSONDecodeError:
                pass

        return result

    async def npm_outdated(self) -> dict:
        """Check for outdated packages.

        Returns:
            Dict with outdated package information
        """
        result = await self._run_command(self.pm, "outdated", "--json")

        if result.get("stdout"):
            try:
                outdated_data = json.loads(result.get("stdout", "{}"))
                result["outdated"] = outdated_data
            except json.JSONDecodeError:
                pass

        return result

    async def read_package_json(self) -> dict:
        """Read the package.json file.

        Returns:
            Dict with package.json contents
        """
        package_path = self.working_dir / "package.json"
        try:
            if not package_path.exists():
                return {"success": False, "error": "package.json not found"}

            with open(package_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return {
                "success": True,
                "package": data,
                "name": data.get("name"),
                "version": data.get("version"),
                "dependencies": list(data.get("dependencies", {}).keys()),
                "devDependencies": list(data.get("devDependencies", {}).keys()),
                "scripts": list(data.get("scripts", {}).keys()),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def npm_init(self, name: str = None) -> dict:
        """Initialize a new package.json.

        Args:
            name: Package name (optional)

        Returns:
            Dict with result
        """
        cmd = [self.pm, "init", "-y"]
        result = await self._run_command(*cmd)
        return result


async def run_npm_agent(config: NpmAgentConfig):
    """Run the npm/pnpm MCP agent with the given configuration."""
    logger = setup_logging(f"npm_agent_{config.session_id}")
    event_server = EventServer(session_id=config.session_id, tool_name="npm")

    # Initialize ConversationLogger
    conv_logger = ConversationLogger(
        session_id=config.session_id,
        tool_name="npm",
        sense_category=SenseCategory.TACTILE
    )

    try:
        # Start the UI server
        httpd, thread, host, port = start_ui_server(
            event_server,
            host="127.0.0.1",
            port=0,
            tool_name="npm"
        )
        logger.info(f"UI server started on {host}:{port}")

        # Announce session
        announce_data = {
            "session_id": config.session_id,
            "host": host,
            "port": port,
            "ui_url": f"http://{host}:{port}/"
        }
        print(f"SESSION_ANNOUNCE {json.dumps(announce_data)}", flush=True)
        event_server.broadcast(MCP_EVENT_SESSION_ANNOUNCE, announce_data)

        # Log session start
        conv_logger.log_session_start(config.task, config.model)

        # Get model client
        model_client = shared_init_model_client("npm", config.task)
        logger.info(f"Model initialized: {config.model}")

        # Initialize npm tools
        npm_tools = NpmTools(
            working_dir=config.working_dir,
            package_manager=config.package_manager
        )

        # Create tool list for the agent
        tools = [
            npm_tools.npm_install,
            npm_tools.npm_run,
            npm_tools.npm_list,
            npm_tools.npm_audit,
            npm_tools.npm_outdated,
            npm_tools.read_package_json,
            npm_tools.npm_init,
        ]

        event_server.broadcast("log", f"Loaded {len(tools)} npm tools")
        event_server.broadcast("log", f"Package manager: {config.package_manager}")
        event_server.broadcast("log", f"Working directory: {config.working_dir}")

        # Create Operator agent
        operator = AssistantAgent(
            name="NpmOperator",
            model_client=model_client,
            tools=tools,
            system_message=NPM_OPERATOR_PROMPT,
            model_context=BufferedChatCompletionContext(buffer_size=20),
        )

        # Create QA Validator agent
        qa_validator = AssistantAgent(
            name="QA_Validator",
            model_client=model_client,
            tools=[],
            system_message=QA_VALIDATOR_PROMPT,
            model_context=BufferedChatCompletionContext(buffer_size=10),
        )

        # Create team
        termination = TextMentionTermination("TASK_COMPLETE")
        team = RoundRobinGroupChat(
            participants=[operator, qa_validator],
            termination_condition=termination,
            max_turns=20,
        )

        # Send running status
        event_server.broadcast("log", f"Starting task: {config.task}")
        event_server.broadcast("status", SESSION_STATE_RUNNING)

        # Run the team
        result = await team.run(task=config.task)

        # Extract result
        result_text = ""
        if result.messages:
            result_text = str(result.messages[-1].content)
        else:
            result_text = "Task completed"

        # Log agent messages
        for msg in result.messages:
            agent_name = getattr(msg, 'source', 'Unknown')
            content = str(msg.content) if hasattr(msg, 'content') else str(msg)
            event_server.broadcast("agent.message", {
                "agent": agent_name,
                "content": content[:500],
                "timestamp": time.time()
            })

        # Send completion
        event_server.broadcast("log", f"Result: {result_text[:200]}...")
        event_server.broadcast("status", SESSION_STATE_STOPPED)

        # Log conversation
        conv_logger.log_conversation_turn(
            agent="NpmOperator",
            agent_response=result_text,
            final_response=result_text
        )

        # Send final result
        event_server.broadcast("agent.completion", {
            "status": "success",
            "content": result_text,
            "tool": "npm",
            "timestamp": time.time()
        })

        logger.info("Task completed successfully")
        return {"success": True, "result": result_text}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error: {error_msg}", exc_info=True)
        event_server.broadcast("error", error_msg)
        event_server.broadcast("status", SESSION_STATE_ERROR)
        return {"success": False, "error": error_msg}

    finally:
        await asyncio.sleep(2)
        try:
            httpd.shutdown()
        except Exception:
            pass


async def main():
    """Main entry point with argument parsing."""
    import argparse
    parser = argparse.ArgumentParser(description="npm/pnpm MCP Agent")
    parser.add_argument('--session-id', required=False, help="Session identifier")
    parser.add_argument('--name', default='npm-session', help="Session name")
    parser.add_argument('--model', default=get_model("mcp_agent"), help="Model to use")
    parser.add_argument('--task', default='List installed packages', help="Task to execute")
    parser.add_argument('--working-dir', default='.', help="Working directory")
    parser.add_argument('--package-manager', default='npm', choices=['npm', 'pnpm'],
                        help="Package manager to use")
    parser.add_argument('config_json', nargs='?', help="JSON config (alternative)")
    args = parser.parse_args()

    try:
        if args.config_json:
            config_dict = json.loads(args.config_json)
        elif args.session_id:
            config_dict = {
                'session_id': args.session_id,
                'name': args.name,
                'model': args.model,
                'task': args.task,
                'working_dir': args.working_dir,
                'package_manager': args.package_manager,
            }
        else:
            import uuid
            config_dict = {
                'session_id': f"npm_{uuid.uuid4().hex[:8]}",
                'name': args.name,
                'model': args.model,
                'task': args.task,
                'working_dir': args.working_dir,
                'package_manager': args.package_manager,
            }

        config = NpmAgentConfig(**config_dict)
        result = await run_npm_agent(config)

        if not result.get("success"):
            sys.exit(1)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
