import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import field
from typing import Any, Dict, List, Optional

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Load .env for environment variables
try:
    import dotenv
    # Find .env in project root (4 levels up from agent.py)
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '.env')
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

# Time plugin imports FIRST (before sys.path.insert!)
from time_constants import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TASK_PROMPT,
    DEFAULT_TIME_OPERATOR_PROMPT,
    DEFAULT_QA_VALIDATOR_PROMPT,
    DEFAULT_USER_CLARIFICATION_PROMPT,
)
from event_task import start_time_ui_server
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


class TimeAgentConfig(BaseModel):
    """Configuration for Time MCP agent"""
    session_id: str
    name: str
    model: str
    task: str


async def run_time_agent(config: TimeAgentConfig):
    """Run the time agent with proper MCP session lifecycle management"""
    logger = setup_logging(f"time_agent_{config.session_id}")
    event_server = None
    conversation_history = []

    try:
        # Start event server
        event_server = EventServer(session_id=config.session_id, tool_name="time")
        event_port = await event_server.start()
        logger.info(f"Event server started on port {event_port}")

        # Send SESSION_ANNOUNCE
        await event_server.send_event({
            "type": MCP_EVENT_SESSION_ANNOUNCE,
            "session_id": config.session_id,
            "host": "127.0.0.1",
            "port": event_port,
            "status": SESSION_STATE_CREATED,
            "timestamp": time.time()
        })

        # Initialize model client
        model_client = get_model_client(config.model)
        logger.info(f"Model client initialized: {config.model}")

        # Set up Time MCP server parameters (Python module)
        server_params = StdioServerParams(
            command="python",
            args=["-m", "mcp_server_time"],
            env={}
        )

        # Use async with for proper context management
        async with create_mcp_server_session(server_params) as mcp_session:
            logger.info("Time MCP session created")

            # Get Time MCP tools
            time_tools = await mcp_server_tools(mcp_session)

            # Create ask_user tool for clarifications
            ask_user_tool = create_ask_user_tool(event_server, config.session_id)

            # Time Operator Agent - Main time operations expert
            time_operator = AssistantAgent(
                name="Time_Operator",
                model_client=model_client,
                tools=time_tools + [ask_user_tool],
                system_message=DEFAULT_TIME_OPERATOR_PROMPT,
                model_context=BufferedChatCompletionContext(buffer_size=10)
            )

            # QA Validator Agent - Validates results
            qa_validator = AssistantAgent(
                name="QA_Validator",
                model_client=model_client,
                tools=[],
                system_message=DEFAULT_QA_VALIDATOR_PROMPT,
                model_context=BufferedChatCompletionContext(buffer_size=5)
            )

            # Create Round Robin team
            team = RoundRobinGroupChat(
                participants=[time_operator, qa_validator],
                termination_condition=TextMentionTermination("TASK_COMPLETE")
            )

            logger.info("Society of Mind team created with Time_Operator and QA_Validator")

            # Start UI server in background
            asyncio.create_task(start_time_ui_server(config.session_id, event_port))

            # Send running status
            await event_server.send_event({
                "type": MCP_EVENT_AGENT_MESSAGE,
                "message": f"Starting time task: {config.task}",
                "status": SESSION_STATE_RUNNING,
                "timestamp": time.time()
            })

            # Run the team
            result = await team.run(task=config.task)

            # Extract conversation history
            for msg in result.messages:
                conversation_history.append({
                    "source": msg.source,
                    "content": str(msg.content),
                    "timestamp": time.time()
                })

            # Send completion event
            await event_server.send_event({
                "type": MCP_EVENT_TASK_COMPLETE,
                "result": str(result.messages[-1].content) if result.messages else "Task completed",
                "status": SESSION_STATE_STOPPED,
                "timestamp": time.time()
            })

            # Send conversation history
            await event_server.send_event({
                "type": MCP_EVENT_CONVERSATION_HISTORY,
                "history": conversation_history,
                "timestamp": time.time()
            })

            logger.info("Task completed successfully")

    except Exception as e:
        logger.error(f"Task execution error: {str(e)}", exc_info=True)
        if event_server:
            await event_server.send_event({
                "type": MCP_EVENT_AGENT_ERROR,
                "error": str(e),
                "status": SESSION_STATE_ERROR,
                "timestamp": time.time()
            })
        raise
    finally:
        # Cleanup
        if event_server:
            await event_server.stop()
            logger.info("Cleanup completed")


async def main():
    """Main entry point"""
    import argparse

    # Parse command-line arguments (compatible with session manager)
    parser = argparse.ArgumentParser(description='Time MCP Agent')
    parser.add_argument('--session-id', required=False, help='Session ID')
    parser.add_argument('--name', default='time-session', help='Session name')
    parser.add_argument('--model', default=get_model("mcp_agent"), help='Model to use')
    parser.add_argument('--task', default='Get current time', help='Task to execute')
    parser.add_argument('config_json', nargs='?', help='JSON config (alternative to flags)')

    args = parser.parse_args()

    try:
        # Support both JSON arg and command-line flags
        if args.config_json:
            config_dict = json.loads(args.config_json)
        elif args.session_id:
            config_dict = {
                'session_id': args.session_id,
                'name': args.name,
                'model': args.model,
                'task': args.task
            }
        else:
            print(json.dumps({"error": "Missing session config (provide --session-id or JSON)"}), file=sys.stderr)
            sys.exit(1)

        config = TimeAgentConfig(**config_dict)
        await run_time_agent(config)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
