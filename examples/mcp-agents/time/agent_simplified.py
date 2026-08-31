import asyncio
import json
import os
import sys
import time
from dataclasses import field

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Load .env
try:
    import dotenv
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '.env')
    dotenv.load_dotenv(dotenv_path=env_path)
except Exception:
    pass

# Autogen imports
from autogen_ext.tools.mcp import StdioServerParams, mcp_server_tools
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_core.model_context import BufferedChatCompletionContext
from pydantic import BaseModel

# Import global LLM config
from src.llm_config import get_model

# Shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from event_server import EventServer
from constants import *
from model_utils import get_model_client
from logging_utils import setup_logging

class TimeAgentConfig(BaseModel):
    session_id: str
    name: str
    model: str
    task: str

async def run_time_agent(config: TimeAgentConfig):
    """Simplified time agent"""
    logger = setup_logging(f"time_agent_{config.session_id}")
    event_server = EventServer(session_id=config.session_id, tool_name="time")

    try:
        event_port = await event_server.start()
        logger.info(f"Event server started on port {event_port}")

        # Announce session
        await event_server.send_event({
            "type": MCP_EVENT_SESSION_ANNOUNCE,
            "session_id": config.session_id,
            "host": "127.0.0.1",
            "port": event_port,
            "status": SESSION_STATE_CREATED,
            "timestamp": time.time()
        })

        # Get model client
        model_client = get_model_client(config.model)
        logger.info(f"Model initialized: {config.model}")

        # Set up Time MCP server (use venv python if available)
        python_cmd = os.getenv("SAKANA_VENV_PYTHON", sys.executable)
        server_params = StdioServerParams(
            command=python_cmd,
            args=["-m", "mcp_server_time"],
            env={}
        )

        # Get tools (mcp_server_tools manages session internally)
        time_tools = await mcp_server_tools(server_params)
        logger.info(f"Loaded {len(time_tools)} time tools")

        # Create agent with tools
        agent = AssistantAgent(
            name="TimeAgent",
            model_client=model_client,
            tools=time_tools,
            system_message="You are a time operations expert. Use the time tools to answer questions about time, timezones, and date calculations."
        )

        # Send running status
        await event_server.send_event({
            "type": MCP_EVENT_AGENT_MESSAGE,
            "message": f"Starting task: {config.task}",
            "status": SESSION_STATE_RUNNING,
            "timestamp": time.time()
        })

        # Run task
        result = await agent.run(task=config.task)

        # Send completion
        await event_server.send_event({
            "type": MCP_EVENT_TASK_COMPLETE,
            "result": str(result.messages[-1].content) if result.messages else "Task completed",
            "status": SESSION_STATE_STOPPED,
            "timestamp": time.time()
        })

        logger.info("Task completed")

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        await event_server.send_event({
            "type": MCP_EVENT_AGENT_ERROR,
            "error": str(e),
            "status": SESSION_STATE_ERROR,
            "timestamp": time.time()
        })
        raise
    finally:
        await event_server.stop()

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--session-id', required=False)
    parser.add_argument('--name', default='time-session')
    parser.add_argument('--model', default=get_model("mcp_agent"))
    parser.add_argument('--task', default='Get current time')
    parser.add_argument('config_json', nargs='?')
    args = parser.parse_args()

    try:
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
            print(json.dumps({"error": "Missing session config"}), file=sys.stderr)
            sys.exit(1)

        config = TimeAgentConfig(**config_dict)
        await run_time_agent(config)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
