#!/usr/bin/env python3
"""
Prisma MCP Agent - ORM and database schema operations.

Provides:
- Schema generation (prisma generate)
- Database push (prisma db push)
- Migrations (prisma migrate)
- Schema validation (prisma validate)
- Prisma Studio launch

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
from typing import Optional

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Load .env from project root
try:
    import dotenv
    # Path: mcp_plugins/servers/prisma/agent.py -> go up 3 levels to project root
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


class PrismaAgentConfig(BaseModel):
    """Configuration for Prisma MCP Agent."""
    session_id: str
    task: str
    name: str = "prisma-session"
    model: str = field(default_factory=lambda: get_model("mcp_agent"))
    working_dir: str = "."
    database_url: Optional[str] = None


# System prompts
PRISMA_OPERATOR_PROMPT = """You are a Prisma ORM expert with deep knowledge of database schemas and migrations.

Your capabilities include:
- Generating Prisma Client (prisma_generate)
- Pushing schema to database (prisma_db_push)
- Creating migrations (prisma_migrate)
- Validating schema (prisma_validate)
- Formatting schema (prisma_format)
- Reading schema.prisma (prisma_read_schema)
- Launching Prisma Studio (prisma_studio)
- Checking migration status (prisma_migrate_status)

Guidelines:
1. Always validate schema before pushing or migrating
2. Read the current schema before making suggestions
3. Use prisma_format to keep schema files clean
4. Explain what each model and relation does
5. After schema changes, always run prisma_generate

When you have completed the task, say "TASK_COMPLETE".
"""

QA_VALIDATOR_PROMPT = """You are a QA Validator for Prisma operations.

Your role:
1. Verify that schema changes are valid
2. Check that migrations applied successfully
3. Ensure Prisma Client was regenerated after schema changes
4. Validate that the task was completed correctly

When the task is fully validated, say "TASK_COMPLETE".
"""


class PrismaTools:
    """Custom Prisma tool implementations."""

    def __init__(self, working_dir: str, database_url: Optional[str] = None):
        self.working_dir = Path(working_dir).resolve()
        self.database_url = database_url
        self._env = None

    def _get_env(self) -> dict:
        """Get environment with DATABASE_URL set."""
        if self._env is None:
            self._env = os.environ.copy()
            if self.database_url:
                self._env["DATABASE_URL"] = self.database_url
        return self._env

    async def _run_prisma(self, *args: str, timeout: int = 120) -> dict:
        """Run a prisma command."""
        cmd = ["npx", "prisma", *args]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.working_dir),
                env=self._get_env(),
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
                    "command": " ".join(cmd)
                }

            return {
                "success": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": stdout.decode('utf-8', errors='replace'),
                "stderr": stderr.decode('utf-8', errors='replace'),
                "command": " ".join(cmd)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "command": " ".join(cmd)
            }

    async def prisma_generate(self) -> dict:
        """Generate Prisma Client from schema.

        This must be run after any schema changes to update the TypeScript types.

        Returns:
            Dict with success status and output
        """
        result = await self._run_prisma("generate")
        if result.get("success"):
            result["message"] = "Prisma Client generated successfully"
        return result

    async def prisma_db_push(self) -> dict:
        """Push schema to database without creating migrations.

        This is useful for development. It will sync the schema with the database.
        WARNING: May cause data loss if there are breaking changes.

        Returns:
            Dict with success status and output
        """
        result = await self._run_prisma("db", "push", "--accept-data-loss")
        if result.get("success"):
            result["message"] = "Schema pushed to database successfully"
        return result

    async def prisma_migrate(self, name: str = "migration") -> dict:
        """Create and apply a new migration.

        Args:
            name: Name for the migration (e.g., "add_user_table")

        Returns:
            Dict with success status and output
        """
        result = await self._run_prisma("migrate", "dev", "--name", name)
        if result.get("success"):
            result["message"] = f"Migration '{name}' created and applied"
        return result

    async def prisma_migrate_status(self) -> dict:
        """Check the status of migrations.

        Returns:
            Dict with migration status information
        """
        result = await self._run_prisma("migrate", "status")
        return result

    async def prisma_validate(self) -> dict:
        """Validate the schema.prisma file.

        Returns:
            Dict with validation result
        """
        result = await self._run_prisma("validate")
        if result.get("success"):
            result["message"] = "Schema is valid"
        return result

    async def prisma_format(self) -> dict:
        """Format the schema.prisma file.

        Returns:
            Dict with format result
        """
        result = await self._run_prisma("format")
        if result.get("success"):
            result["message"] = "Schema formatted successfully"
        return result

    async def prisma_read_schema(self) -> dict:
        """Read the current schema.prisma content.

        Returns:
            Dict with schema content and model information
        """
        schema_path = self.working_dir / "prisma" / "schema.prisma"
        try:
            if not schema_path.exists():
                # Try root directory
                schema_path = self.working_dir / "schema.prisma"
                if not schema_path.exists():
                    return {"success": False, "error": "schema.prisma not found"}

            content = schema_path.read_text(encoding='utf-8')

            # Parse basic info from schema
            models = []
            enums = []
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('model '):
                    model_name = line.split()[1]
                    models.append(model_name)
                elif line.startswith('enum '):
                    enum_name = line.split()[1]
                    enums.append(enum_name)

            return {
                "success": True,
                "schema": content,
                "path": str(schema_path),
                "models": models,
                "enums": enums,
                "model_count": len(models),
                "enum_count": len(enums),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def prisma_studio(self) -> dict:
        """Launch Prisma Studio in the background.

        Prisma Studio is a visual database browser.

        Returns:
            Dict with launch status
        """
        try:
            # Launch in background
            proc = await asyncio.create_subprocess_exec(
                "npx", "prisma", "studio",
                cwd=str(self.working_dir),
                env=self._get_env(),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return {
                "success": True,
                "message": "Prisma Studio launched",
                "url": "http://localhost:5555",
                "pid": proc.pid
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def prisma_db_seed(self) -> dict:
        """Run the database seed script.

        Returns:
            Dict with seed result
        """
        result = await self._run_prisma("db", "seed")
        if result.get("success"):
            result["message"] = "Database seeded successfully"
        return result


async def run_prisma_agent(config: PrismaAgentConfig):
    """Run the Prisma MCP agent with the given configuration."""
    logger = setup_logging(f"prisma_agent_{config.session_id}")
    event_server = EventServer(session_id=config.session_id, tool_name="prisma")

    # Initialize ConversationLogger
    conv_logger = ConversationLogger(
        session_id=config.session_id,
        tool_name="prisma",
        sense_category=SenseCategory.TACTILE
    )

    try:
        # Start the UI server
        httpd, thread, host, port = start_ui_server(
            event_server,
            host="127.0.0.1",
            port=0,
            tool_name="prisma"
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
        model_client = shared_init_model_client("prisma", config.task)
        logger.info(f"Model initialized: {config.model}")

        # Initialize Prisma tools
        prisma_tools = PrismaTools(
            working_dir=config.working_dir,
            database_url=config.database_url
        )

        # Create tool list
        tools = [
            prisma_tools.prisma_generate,
            prisma_tools.prisma_db_push,
            prisma_tools.prisma_migrate,
            prisma_tools.prisma_migrate_status,
            prisma_tools.prisma_validate,
            prisma_tools.prisma_format,
            prisma_tools.prisma_read_schema,
            prisma_tools.prisma_studio,
            prisma_tools.prisma_db_seed,
        ]

        event_server.broadcast("log", f"Loaded {len(tools)} Prisma tools")
        event_server.broadcast("log", f"Working directory: {config.working_dir}")

        # Create Operator agent
        operator = AssistantAgent(
            name="PrismaOperator",
            model_client=model_client,
            tools=tools,
            system_message=PRISMA_OPERATOR_PROMPT,
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
            agent="PrismaOperator",
            agent_response=result_text,
            final_response=result_text
        )

        # Send final result
        event_server.broadcast("agent.completion", {
            "status": "success",
            "content": result_text,
            "tool": "prisma",
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
    parser = argparse.ArgumentParser(description="Prisma MCP Agent")
    parser.add_argument('--session-id', required=False, help="Session identifier")
    parser.add_argument('--name', default='prisma-session', help="Session name")
    parser.add_argument('--model', default=get_model("mcp_agent"), help="Model to use")
    parser.add_argument('--task', default='Read and validate the Prisma schema', help="Task")
    parser.add_argument('--working-dir', default='.', help="Working directory")
    parser.add_argument('--database-url', default=None, help="Database connection URL")
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
                'database_url': args.database_url,
            }
        else:
            import uuid
            config_dict = {
                'session_id': f"prisma_{uuid.uuid4().hex[:8]}",
                'name': args.name,
                'model': args.model,
                'task': args.task,
                'working_dir': args.working_dir,
                'database_url': args.database_url,
            }

        config = PrismaAgentConfig(**config_dict)
        result = await run_prisma_agent(config)

        if not result.get("success"):
            sys.exit(1)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
