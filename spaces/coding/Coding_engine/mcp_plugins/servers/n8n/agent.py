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
    # Path: mcp_plugins/servers/n8n/agent.py -> go up 3 levels to project root
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    dotenv.load_dotenv(dotenv_path=env_path)
except Exception:
    pass

# Autogen / MCP imports - Society of Mind pattern
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import McpWorkbench
from autogen_ext.tools.mcp import StdioServerParams, create_mcp_server_session, mcp_server_tools
from autogen_agentchat.agents import AssistantAgent, SocietyOfMindAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_core.model_context import BufferedChatCompletionContext
from pydantic import BaseModel

# Import global LLM config
from src.llm_config import get_model

# n8n plugin imports FIRST (before sys.path.insert!)
from n8n_constants import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TASK_PROMPT,
    DEFAULT_N8N_OPERATOR_PROMPT,
    DEFAULT_QA_VALIDATOR_PROMPT,
    DEFAULT_USER_CLARIFICATION_PROMPT,
)
from event_task import start_n8n_ui_server
from user_interaction_utils import create_ask_user_tool

# Shared module imports AFTER local imports
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
from conversation_logger import ConversationLogger, SenseCategory, ThinkingLog, ToolCall, ToolResult


class N8NAgentConfig(BaseModel):
    """Configuration for n8n MCP agent"""
    session_id: str
    name: str = "n8n-session"
    model: str = field(default_factory=lambda: get_model("mcp_agent"))
    task: str
    working_dir: str = "."
    n8n_api_url: Optional[str] = None
    n8n_api_key: Optional[str] = None


class N8NMCPAgent:
    """n8n MCP Agent with Society of Mind architecture"""

    def __init__(self, config: N8NAgentConfig):
        self.config = config
        self.session_id = config.session_id
        self.logger = setup_logging(f"n8n_agent_{self.session_id}")
        self.event_server = None
        self.event_port = None
        self.mcp_session = None
        self.model_client = None
        self.team = None
        self.conversation_history = []

        # Initialize ConversationLogger for ML-ready conversation logs
        self.conv_logger = ConversationLogger(
            session_id=self.session_id,
            tool_name="n8n",
            sense_category=SenseCategory.TEMPORAL
        )

    async def initialize(self):
        """Initialize the agent with event server and MCP session"""
        try:
            # Start event server
            self.event_server = EventServer(session_id=self.session_id, tool_name="n8n")
            self.event_port = await self.event_server.start()
            self.logger.info(f"Event server started on port {self.event_port}")

            # Send SESSION_ANNOUNCE
            announce_timestamp = time.time()
            self.logger.info("=" * 80)
            self.logger.info("PORT ANNOUNCEMENT: SESSION_ANNOUNCE (EventServer.send_event)")
            self.logger.info(f"  Method: EventServer.send_event() with MCP_EVENT_SESSION_ANNOUNCE")
            self.logger.info(f"  Session ID: {self.session_id}")
            self.logger.info(f"  Host: 127.0.0.1")
            self.logger.info(f"  Port: {self.event_port}")
            self.logger.info(f"  Timestamp: {announce_timestamp}")
            self.logger.info(f"  NOTE: n8n agent uses ONLY SESSION_ANNOUNCE (no .event_port file)")
            self.logger.info("=" * 80)
            await self.event_server.send_event({
                "type": MCP_EVENT_SESSION_ANNOUNCE,
                "session_id": self.session_id,
                "host": "127.0.0.1",
                "port": self.event_port,
                "status": SESSION_STATE_CREATED,
                "timestamp": announce_timestamp
            })
            self.logger.info("✓ SESSION_ANNOUNCE event sent successfully")

            # Initialize model client
            self.model_client = get_model_client(self.config.model)
            self.logger.info(f"Model client initialized: {self.config.model}")

            # Log session start for ML dataset
            self.conv_logger.log_session_start(
                task=self.config.task,
                model=self.config.model
            )

            # Set up n8n MCP server parameters
            n8n_env = {}
            if self.config.n8n_api_url:
                n8n_env["N8N_API_URL"] = self.config.n8n_api_url
            if self.config.n8n_api_key:
                n8n_env["N8N_API_KEY"] = self.config.n8n_api_key
            n8n_env["MCP_MODE"] = "stdio"
            n8n_env["LOG_LEVEL"] = "error"

            server_params = StdioServerParams(
                command="cmd.exe" if sys.platform == 'win32' else "sh",
                args=["/c", "npx", "-y", "n8n-mcp"] if sys.platform == 'win32' else ["-c", "npx -y n8n-mcp"],
                env=n8n_env
            )

            # Create MCP session
            self.mcp_session = await create_mcp_server_session(server_params, read_timeout_seconds=120)
            self.logger.info("n8n MCP session created")

            # Create Society of Mind team
            await self._create_team()

            self.logger.info("n8n agent initialized successfully")

        except Exception as e:
            self.logger.error(f"Initialization error: {str(e)}", exc_info=True)
            await self.event_server.send_event({
                "type": MCP_EVENT_AGENT_ERROR,
                "error": str(e),
                "status": SESSION_STATE_ERROR,
                "timestamp": time.time()
            })
            raise

    async def _create_team(self):
        """Create Society of Mind team with n8n-specific agents"""
        # Get n8n MCP tools
        n8n_tools = await mcp_server_tools(self.mcp_session, read_timeout_seconds=120)

        # Create ask_user tool for clarifications
        ask_user_tool = create_ask_user_tool(self.event_server, self.session_id)

        # n8n Operator Agent - Main workflow expert
        n8n_operator = AssistantAgent(
            name="N8N_Operator",
            model_client=self.model_client,
            tools=n8n_tools + [ask_user_tool],
            system_message=DEFAULT_N8N_OPERATOR_PROMPT,
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
            participants=[n8n_operator, qa_validator],
            termination_condition=TextMentionTermination("TASK_COMPLETE")
        )

        self.logger.info("Society of Mind team created with N8N_Operator and QA_Validator")

    async def run_task(self):
        """Run the n8n task"""
        try:
            await self.event_server.send_event({
                "type": MCP_EVENT_AGENT_MESSAGE,
                "message": f"Starting n8n task: {self.config.task}",
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
                n8n_operator_msgs = [m for m in agent_messages if 'N8N_Operator' in m['agent']]
                operator_response = n8n_operator_msgs[0]['content'] if n8n_operator_msgs else final_response

                self.conv_logger.log_conversation_turn(
                    agent="N8N_Operator",
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
        """Clean up resources"""
        try:
            if self.mcp_session:
                await self.mcp_session.__aexit__(None, None, None)
            if self.event_server:
                await self.event_server.stop()
            self.logger.info("Cleanup completed")
        except Exception as e:
            self.logger.error(f"Cleanup error: {str(e)}", exc_info=True)


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="n8n MCP Agent with Society of Mind")
    parser.add_argument("--task", default="List all workflows", help="Task for the agent to execute")
    parser.add_argument("--session-id", dest="session_id", default=None, help="Session identifier")
    parser.add_argument("--name", default="n8n-session", help="Agent session name")
    parser.add_argument("--model", default=get_model("mcp_agent"), help="Model to use (e.g., gpt-4o-mini)")
    parser.add_argument("--working-dir", dest="working_dir", default=".", help="Working directory")
    parser.add_argument("--n8n-api-url", dest="n8n_api_url", default=None, help="n8n API URL")
    parser.add_argument("--n8n-api-key", dest="n8n_api_key", default=None, help="n8n API key")
    parser.add_argument("--keepalive", action="store_true", help="Keep UI alive after completion")
    parser.add_argument("config_json", nargs="?", help="JSON config (legacy mode)")

    args = parser.parse_args()

    try:
        # Support legacy JSON mode or new CLI args
        if args.config_json:
            config_dict = json.loads(args.config_json)
            config = N8NAgentConfig(**config_dict)
        else:
            config = N8NAgentConfig(
                session_id=args.session_id or f"n8n_{uuid.uuid4().hex[:8]}",
                name=args.name,
                model=args.model,
                task=args.task,
                working_dir=args.working_dir,
                n8n_api_url=args.n8n_api_url,
                n8n_api_key=args.n8n_api_key,
            )

        agent = N8NMCPAgent(config)
        await agent.initialize()

        # Start UI server in background
        asyncio.create_task(start_n8n_ui_server(agent.session_id, agent.event_port))

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
