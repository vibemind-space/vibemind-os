#!/usr/bin/env python3
"""
Supermemory MCP Agent - Semantic code pattern memory.

Uses the Supermemory API for:
- Searching code patterns and solutions
- Storing successful implementations
- Finding similar error fixes
- Architecture pattern retrieval
"""
import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import field
from datetime import datetime
from typing import Any, Dict, List, Optional

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Load .env for environment variables
try:
    import dotenv
    # Path: mcp_plugins/servers/supermemory/agent.py -> go up 3 levels to project root
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    dotenv.load_dotenv(dotenv_path=env_path)
except Exception:
    pass

# Autogen / MCP imports - Society of Mind pattern
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_core.model_context import BufferedChatCompletionContext
from pydantic import BaseModel

# Import global LLM config
from src.llm_config import get_model

# Supermemory constants
from supermemory_constants import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TASK_PROMPT,
    DEFAULT_SUPERMEMORY_OPERATOR_PROMPT,
    DEFAULT_QA_VALIDATOR_PROMPT,
)

# Shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from event_server import EventServer
from constants import (
    MCP_EVENT_SESSION_ANNOUNCE,
    MCP_EVENT_AGENT_MESSAGE,
    MCP_EVENT_AGENT_ERROR,
    MCP_EVENT_TASK_COMPLETE,
    MCP_EVENT_CONVERSATION_HISTORY,
    SESSION_STATE_CREATED,
    SESSION_STATE_RUNNING,
    SESSION_STATE_STOPPED,
    SESSION_STATE_ERROR,
)
from model_utils import get_model_client
from logging_utils import setup_logging
from conversation_logger import ConversationLogger, SenseCategory

# Import SupermemoryTools directly (avoid __init__.py circular imports)
import importlib.util
_supermemory_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src', 'tools', 'supermemory_tools.py')
_spec = importlib.util.spec_from_file_location("supermemory_tools", _supermemory_path)
_supermemory_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_supermemory_module)
SupermemoryTools = _supermemory_module.SupermemoryTools


class SupermemoryAgentConfig(BaseModel):
    """Configuration for Supermemory MCP agent."""
    session_id: str
    name: str = "supermemory-session"
    model: str = field(default_factory=lambda: get_model("mcp_agent"))
    task: str
    working_dir: str = "."
    container_tag: str = "coding_engine_v1"
    api_key: Optional[str] = None


class SupermemoryMCPAgent:
    """Supermemory MCP Agent with Society of Mind architecture."""

    def __init__(self, config: SupermemoryAgentConfig):
        self.config = config
        self.session_id = config.session_id
        self.logger = setup_logging(f"supermemory_agent_{self.session_id}")
        self.event_server = None
        self.event_port = None
        self.model_client = None
        self.team = None
        self.conversation_history = []

        # Initialize SupermemoryTools
        api_key = config.api_key or os.environ.get("SUPERMEMORY_API_KEY")
        self.supermemory = SupermemoryTools(api_key=api_key)

        # Initialize ConversationLogger for ML-ready conversation logs
        self.conv_logger = ConversationLogger(
            session_id=self.session_id,
            tool_name="supermemory",
            sense_category=SenseCategory.MEMORY
        )

    async def initialize(self):
        """Initialize the agent with event server and tools."""
        try:
            # Start event server
            self.event_server = EventServer(session_id=self.session_id, tool_name="supermemory")
            self.event_port = await self.event_server.start()
            self.logger.info(f"Event server started on port {self.event_port}")

            # Send SESSION_ANNOUNCE
            announce_timestamp = time.time()
            self.logger.info("=" * 80)
            self.logger.info("PORT ANNOUNCEMENT: SESSION_ANNOUNCE (EventServer.send_event)")
            self.logger.info(f"  Session ID: {self.session_id}")
            self.logger.info(f"  Host: 127.0.0.1")
            self.logger.info(f"  Port: {self.event_port}")
            self.logger.info("=" * 80)

            await self.event_server.send_event({
                "type": MCP_EVENT_SESSION_ANNOUNCE,
                "session_id": self.session_id,
                "host": "127.0.0.1",
                "port": self.event_port,
                "status": SESSION_STATE_CREATED,
                "timestamp": announce_timestamp
            })
            self.logger.info("SESSION_ANNOUNCE event sent successfully")

            # Initialize model client
            self.model_client = get_model_client(self.config.model)
            self.logger.info(f"Model client initialized: {self.config.model}")

            # Log session start for ML dataset
            self.conv_logger.log_session_start(
                task=self.config.task,
                model=self.config.model
            )

            # Check Supermemory availability
            if not self.supermemory.enabled:
                self.logger.warning("Supermemory not available - API key missing or invalid")
            else:
                self.logger.info("Supermemory client initialized")

            # Create Society of Mind team
            await self._create_team()

            self.logger.info("Supermemory agent initialized successfully")

        except Exception as e:
            self.logger.error(f"Initialization error: {str(e)}", exc_info=True)
            if self.event_server:
                await self.event_server.send_event({
                    "type": MCP_EVENT_AGENT_ERROR,
                    "error": str(e),
                    "status": SESSION_STATE_ERROR,
                    "timestamp": time.time()
                })
            raise

    def _create_tools(self) -> List:
        """Create tool functions for the agent."""
        tools = []

        # Search memory tool
        async def search_memory(query: str, category: str = "all", limit: int = 5) -> dict:
            """Search for code patterns, solutions, or errors in Supermemory.

            Args:
                query: What to search for (e.g., 'authentication middleware fastapi')
                category: Category filter - code_pattern, error_fix, architecture, or all
                limit: Maximum number of results (default: 5)

            Returns:
                Search results with matching patterns
            """
            result = await self.supermemory.search(
                query=query,
                category=category,
                limit=limit,
                container_tag=self.config.container_tag,
                rerank=True
            )
            return result.to_dict()

        tools.append(search_memory)

        # Store memory tool
        async def store_memory(
            content: str,
            description: str,
            category: str,
            tags: List[str] = None
        ) -> dict:
            """Store a successful code pattern or solution in Supermemory.

            Args:
                content: The code or solution to store
                description: Description of what this code does
                category: Category - code_pattern, error_fix, or architecture
                tags: Optional tags for easier retrieval

            Returns:
                Store result with memory ID
            """
            result = await self.supermemory.store(
                content=content,
                description=description,
                category=category,
                tags=tags or [],
                container_tag=self.config.container_tag
            )
            return result.to_dict()

        tools.append(store_memory)

        # Search v4 (speed optimized)
        async def search_patterns(
            query: str,
            limit: int = 10,
            threshold: float = 0.5
        ) -> dict:
            """Fast semantic search for code patterns using v4 API.

            Args:
                query: What to search for
                limit: Maximum results (default: 10)
                threshold: Minimum similarity threshold 0.0-1.0 (default: 0.5)

            Returns:
                Search results optimized for speed
            """
            result = await self.supermemory.search_v4(
                query=query,
                container_tag=self.config.container_tag,
                limit=limit,
                threshold=threshold,
                rerank=False  # Faster without rerank
            )
            return result.to_dict()

        tools.append(search_patterns)

        return tools

    async def _create_team(self):
        """Create Society of Mind team with Supermemory-specific agents."""
        # Get tools
        supermemory_tools = self._create_tools()

        # Supermemory Operator Agent - Main memory expert
        supermemory_operator = AssistantAgent(
            name="Supermemory_Operator",
            model_client=self.model_client,
            tools=supermemory_tools,
            system_message=DEFAULT_SUPERMEMORY_OPERATOR_PROMPT,
            model_context=BufferedChatCompletionContext(buffer_size=10)
        )

        # QA Validator Agent - Validates results
        qa_validator = AssistantAgent(
            name="QA_Validator",
            model_client=self.model_client,
            tools=[],
            system_message=DEFAULT_QA_VALIDATOR_PROMPT,
            model_context=BufferedChatCompletionContext(buffer_size=5)
        )

        # Create Round Robin team
        self.team = RoundRobinGroupChat(
            participants=[supermemory_operator, qa_validator],
            termination_condition=TextMentionTermination("TASK_COMPLETE")
        )

        self.logger.info("Society of Mind team created with Supermemory_Operator and QA_Validator")

    async def run_task(self):
        """Run the Supermemory task."""
        try:
            await self.event_server.send_event({
                "type": MCP_EVENT_AGENT_MESSAGE,
                "message": f"Starting Supermemory task: {self.config.task}",
                "status": SESSION_STATE_RUNNING,
                "timestamp": time.time()
            })

            # Run the team
            result = await self.team.run(task=self.config.task)

            # Extract conversation history and collect agent messages for ML logging
            agent_messages = []
            for msg in result.messages:
                self.conversation_history.append({
                    "source": msg.source,
                    "content": str(msg.content),
                    "timestamp": time.time()
                })
                agent_messages.append({
                    "agent": msg.source,
                    "content": str(msg.content)
                })

            # Get final response
            final_response = str(result.messages[-1].content) if result.messages else "Task completed"

            # Log conversation turn for ML dataset
            if agent_messages:
                operator_msgs = [m for m in agent_messages if 'Supermemory_Operator' in m['agent']]
                operator_response = operator_msgs[0]['content'] if operator_msgs else final_response

                self.conv_logger.log_conversation_turn(
                    agent="Supermemory_Operator",
                    agent_response=operator_response,
                    final_response=final_response
                )

            # Send completion event
            await self.event_server.send_event({
                "type": MCP_EVENT_TASK_COMPLETE,
                "result": final_response,
                "status": SESSION_STATE_STOPPED,
                "timestamp": time.time()
            })

            # Send conversation history
            await self.event_server.send_event({
                "type": MCP_EVENT_CONVERSATION_HISTORY,
                "history": self.conversation_history,
                "timestamp": time.time()
            })

            self.logger.info("Task completed successfully")

        except Exception as e:
            self.logger.error(f"Task execution error: {str(e)}", exc_info=True)
            await self.event_server.send_event({
                "type": MCP_EVENT_AGENT_ERROR,
                "error": str(e),
                "status": SESSION_STATE_ERROR,
                "timestamp": time.time()
            })

    async def cleanup(self):
        """Clean up resources."""
        try:
            if self.supermemory and self.supermemory.client:
                await self.supermemory.client.aclose()
            if self.event_server:
                await self.event_server.stop()
            self.logger.info("Cleanup completed")
        except Exception as e:
            self.logger.error(f"Cleanup error: {str(e)}", exc_info=True)


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Supermemory MCP Agent with Society of Mind")
    parser.add_argument("--task", default="Search for code patterns", help="Task for the agent to execute")
    parser.add_argument("--session-id", dest="session_id", default=None, help="Session identifier")
    parser.add_argument("--name", default="supermemory-session", help="Agent session name")
    parser.add_argument("--model", default=get_model("mcp_agent"), help="Model to use (e.g., gpt-4o-mini)")
    parser.add_argument("--working-dir", dest="working_dir", default=".", help="Working directory")
    parser.add_argument("--container-tag", dest="container_tag", default="coding_engine_v1", help="Supermemory container tag")
    parser.add_argument("--api-key", dest="api_key", default=None, help="Supermemory API key (or use SUPERMEMORY_API_KEY env)")
    parser.add_argument("--keepalive", action="store_true", help="Keep UI alive after completion")
    parser.add_argument("config_json", nargs="?", help="JSON config (legacy mode)")

    args = parser.parse_args()

    try:
        # Support legacy JSON mode or new CLI args
        if args.config_json:
            config_dict = json.loads(args.config_json)
            config = SupermemoryAgentConfig(**config_dict)
        else:
            config = SupermemoryAgentConfig(
                session_id=args.session_id or f"supermemory_{uuid.uuid4().hex[:8]}",
                name=args.name,
                model=args.model,
                task=args.task,
                working_dir=args.working_dir,
                container_tag=args.container_tag,
                api_key=args.api_key,
            )

        agent = SupermemoryMCPAgent(config)
        await agent.initialize()

        # Run task
        await agent.run_task()

        # Keep alive for event streaming
        if args.keepalive:
            await asyncio.sleep(3600)  # 1 hour max
        else:
            await asyncio.sleep(5)  # Brief delay for event delivery

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
    finally:
        if 'agent' in locals():
            await agent.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
