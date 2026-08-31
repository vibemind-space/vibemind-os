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
    # Path: mcp_plugins/servers/time/agent.py -> go up 3 levels to project root
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
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
from event_server import EventServer, start_ui_server
from constants import *
from model_utils import get_model_client
from model_init import init_model_client as shared_init_model_client
from logging_utils import setup_logging
from conversation_logger import ConversationLogger, SenseCategory, ThinkingLog, ToolCall, ToolResult

class TimeAgentConfig(BaseModel):
    session_id: str
    name: str = "time-session"
    model: str = field(default_factory=lambda: get_model("mcp_agent"))
    task: str
    working_dir: str = "."

async def run_time_agent(config: TimeAgentConfig):
    """Simplified time agent"""
    logger = setup_logging(f"time_agent_{config.session_id}")
    event_server = EventServer(session_id=config.session_id, tool_name="time")

    # Initialize ConversationLogger for ML-ready conversation logs
    conv_logger = ConversationLogger(
        session_id=config.session_id,
        tool_name="time",
        sense_category=SenseCategory.TEMPORAL
    )

    try:
        # Start the UI server with event broadcasting
        httpd, thread, host, port = start_ui_server(
            event_server,
            host="127.0.0.1",
            port=0,  # Dynamic port assignment
            tool_name="time"
        )
        logger.info(f"UI server started on {host}:{port}")

        # Announce session (print to stdout for session manager to capture)
        announce_data = {
            "session_id": config.session_id,
            "host": host,
            "port": port,
            "ui_url": f"http://{host}:{port}/"
        }
        print(f"SESSION_ANNOUNCE {json.dumps(announce_data)}", flush=True)
        event_server.broadcast(MCP_EVENT_SESSION_ANNOUNCE, announce_data)

        # Log session start for ML dataset
        conv_logger.log_session_start(config.task, config.model)

        # Get model client (use shared for OpenRouter compatibility)
        model_client = shared_init_model_client("time", config.task)
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
        event_server.broadcast("log", f"Starting task: {config.task}")
        event_server.broadcast("status", SESSION_STATE_RUNNING)

        # Run task
        result = await agent.run(task=config.task)

        # Send completion
        result_text = str(result.messages[-1].content) if result.messages else "Task completed"
        event_server.broadcast("log", f"Result: {result_text}")
        event_server.broadcast("status", SESSION_STATE_STOPPED)

        # Log conversation turn for ML dataset
        conv_logger.log_conversation_turn(
            agent="TimeAgent",
            agent_response=result_text,
            final_response=result_text
        )

        # Send final result event for modal display
        event_server.broadcast("agent.completion", {
            "status": "success",
            "content": result_text,
            "tool": "time",
            "timestamp": time.time()
        })

        logger.info("Task completed")

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        event_server.broadcast("error", str(e))
        event_server.broadcast("status", SESSION_STATE_ERROR)
        raise
    finally:
        # Keep server running briefly so events can be consumed
        await asyncio.sleep(2)
        httpd.shutdown()

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--session-id', required=False, help='Session identifier')
    parser.add_argument('--name', default='time-session', help='Session name')
    parser.add_argument('--model', default=get_model("mcp_agent"), help='Model to use')
    parser.add_argument('--task', default='Get current time', help='Task to execute')
    parser.add_argument('--working-dir', dest='working_dir', default='.', help='Working directory')
    parser.add_argument('config_json', nargs='?', help='JSON config (alternative)')
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
            }
        else:
            import uuid
            config_dict = {
                'session_id': f"time_{uuid.uuid4().hex[:8]}",
                'name': args.name,
                'model': args.model,
                'task': args.task,
                'working_dir': args.working_dir,
            }

        config = TimeAgentConfig(**config_dict)
        await run_time_agent(config)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
