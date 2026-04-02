import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Load .env for environment variables
try:
    import dotenv
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    dotenv.load_dotenv(dotenv_path=env_path)
except Exception:
    pass

# Autogen / MCP imports - Society of Mind pattern
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import McpWorkbench
from autogen_ext.tools.mcp import StdioServerParams
from autogen_agentchat.agents import AssistantAgent, SocietyOfMindAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_core.model_context import BufferedChatCompletionContext

# Shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from event_server import EventServer, start_ui_server
from utils import load_prompt_from_module
from model_init import init_model_client as shared_init_model_client
from logging_utils import setup_logging
from conversation_logger import ConversationLogger, SenseCategory

# Optional: rich console for nicer logs
try:
    from rich.console import Console
    from rich.traceback import install
    install()
    console = Console()
except Exception:
    console = None

# ========== File helpers ==========
BASE_DIR = os.path.dirname(__file__)
SERVERS_DIR = os.path.dirname(BASE_DIR)
PLUGINS_DIR = os.path.dirname(SERVERS_DIR)
MODELS_DIR = os.path.join(PLUGINS_DIR, "models")

SYSTEM_PROMPT_PATH = os.path.join(BASE_DIR, "system_prompt.txt")
TASK_PROMPT_PATH = os.path.join(BASE_DIR, "task_prompt.txt")
SERVERS_CONFIG_PATH = os.path.join(SERVERS_DIR, "servers.json")
MODEL_CONFIG_PATH = os.path.join(MODELS_DIR, "model.json")

# ========== Defaults ==========
DEFAULT_SYSTEM_PROMPT = """You are an AutoGen Assistant with access to Fetch MCP tools.
Use the available tools to fetch and analyze web content.
Follow the TOOL USAGE contract strictly and call only the exposed tool names.
"""

DEFAULT_TASK_PROMPT = """Use the available fetch tools to accomplish the goal and stream your progress.
Be clear and concise in your responses.
"""

DEFAULT_OPERATOR_PROMPT = """ROLE: Fetch Operator (Fetch MCP)
GOAL: Complete HTTP fetch tasks using available MCP tools.
TOOLS: Use ONLY the available MCP fetch tools (fetch URL, get content).
GUIDELINES:
- Fetch the requested URL or content
- Extract relevant information from the response
- Handle errors gracefully (404, timeouts, etc.)
- When the task is fulfilled, provide a compact summary and signal completion clearly.
OUTPUT:
- Brief step log
- Relevant results (compact, structured)
- Completion signal: "READY_FOR_VALIDATION"
"""

DEFAULT_QA_VALIDATOR_PROMPT = """ROLE: QA Validator
GOAL: Verify that the user's fetch task is completely and correctly fulfilled.
CHECK:
- Was the URL fetched successfully?
- Were the required data extracted?
- Are the results accurate and complete?
RESPONSE:
- If everything is correct: respond ONLY with 'APPROVE' plus 1-2 bullet points (no long texts).
- If something is missing: name precisely 1-2 gaps (why/what is missing).
"""


def _read_text_file(path: str, default: str = "") -> str:
    """Read content from a text file."""
    try:
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        return default
    except Exception:
        return default


def _write_text_file(path: str, content: str) -> None:
    """Write content to a text file."""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception:
        pass


def get_system_prompt() -> str:
    """Get system prompt for fetch agent."""
    prompt = _read_text_file(SYSTEM_PROMPT_PATH, DEFAULT_SYSTEM_PROMPT)
    if not os.path.isfile(SYSTEM_PROMPT_PATH):
        _write_text_file(SYSTEM_PROMPT_PATH, DEFAULT_SYSTEM_PROMPT)
    return prompt


def get_task_prompt() -> str:
    """Get task prompt for fetch operations."""
    prompt = _read_text_file(TASK_PROMPT_PATH, DEFAULT_TASK_PROMPT)
    if not os.path.isfile(TASK_PROMPT_PATH):
        _write_text_file(TASK_PROMPT_PATH, DEFAULT_TASK_PROMPT)
    return prompt


def load_servers_config() -> List[Dict[str, Any]]:
    """Load servers configuration from servers.json."""
    if not os.path.isfile(SERVERS_CONFIG_PATH):
        return []
    try:
        with open(SERVERS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('servers', [])
    except Exception:
        return []


def init_model_client(task: str = "") -> OpenAIChatCompletionClient:
    """Initialize OpenAI chat completion client with intelligent routing."""
    return shared_init_model_client("fetch", task)


# ========== Pydantic Config Model ==========
class FetchAgentConfig(BaseModel):
    """Configuration for Fetch agent execution."""
    task: str
    session_id: str
    name: str = "fetch-session"
    model: Optional[str] = None
    working_dir: str = "."
    keepalive: bool = False


# ========== Main Entry Point ==========
async def run_fetch_agent(config: FetchAgentConfig):
    """Fetch MCP Agent main entry point.

    Follows the SESSION_ANNOUNCE pattern for backend integration.
    """
    # Setup logging with session identifier
    logger = setup_logging(f"fetch_agent_{config.session_id}")

    # Initialize EventServer with session logging
    event_server = EventServer(session_id=config.session_id, tool_name="fetch")

    # Initialize ConversationLogger for ML-ready conversation logs
    conv_logger = ConversationLogger(
        session_id=config.session_id,
        tool_name="fetch",
        sense_category=SenseCategory.LINGUISTIC
    )

    # Start UI server with dynamic port assignment
    httpd, thread, host, port = start_ui_server(
        event_server,
        host="127.0.0.1",
        port=0,
        tool_name="fetch"
    )

    preview_url = f"http://{host}:{port}/"

    # SESSION_ANNOUNCE for MCPSessionManager
    announce_data = {
        "session_id": config.session_id,
        "host": host,
        "port": port,
        "ui_url": preview_url
    }
    print(f"SESSION_ANNOUNCE {json.dumps(announce_data)}", flush=True)
    event_server.broadcast("session.started", announce_data)

    # Load server configuration for fetch
    servers = load_servers_config()
    fetch_config = None
    for srv in servers:
        if srv.get("name") == "fetch" and srv.get("active"):
            fetch_config = srv
            break

    if not fetch_config:
        # Use default uvx mcp-server-fetch
        fetch_config = {
            "command": "C:\\Windows\\System32\\cmd.exe" if sys.platform == 'win32' else "sh",
            "args": ["/c", "uvx", "mcp-server-fetch"] if sys.platform == 'win32' else ["-c", "uvx mcp-server-fetch"]
        }

    # Create Fetch MCP server params
    server_params = StdioServerParams(
        command=fetch_config["command"],
        args=fetch_config["args"],
        env=os.environ.copy()
    )

    # Initialize model client with task-aware model selection
    try:
        task_aware_client = init_model_client(config.task)
    except Exception as e:
        event_server.broadcast("error", {"text": f"LLM init failed: {e}"})
        if not config.keepalive:
            try:
                httpd.shutdown()
            except Exception:
                pass
        return

    # Run Society of Mind multi-agent system with Fetch workbench
    async with McpWorkbench(server_params) as fetch_mcp:
        # Load Society of Mind prompts
        operator_prompt = load_prompt_from_module("fetch_operator_prompt", BASE_DIR, DEFAULT_OPERATOR_PROMPT)
        qa_prompt = load_prompt_from_module("qa_validator_prompt", BASE_DIR, DEFAULT_QA_VALIDATOR_PROMPT)

        # Create Fetch Operator agent (with Fetch MCP workbench)
        fetch_operator = AssistantAgent(
            "FetchOperator",
            model_client=task_aware_client,
            workbench=fetch_mcp,
            system_message=operator_prompt,
            model_context=BufferedChatCompletionContext(buffer_size=20)
        )

        # Create QA Validator agent (no tools, pure validation)
        qa_validator = AssistantAgent(
            "QAValidator",
            model_client=task_aware_client,
            system_message=qa_prompt,
            model_context=BufferedChatCompletionContext(buffer_size=15)
        )

        # Main team termination: wait for "APPROVE" from QA Validator
        main_termination = TextMentionTermination("APPROVE")
        main_team = RoundRobinGroupChat(
            [fetch_operator, qa_validator],
            termination_condition=main_termination,
            max_turns=30
        )

        # Society of Mind wrapper
        som_agent = SocietyOfMindAgent(
            "fetch_society_of_mind",
            team=main_team,
            model_client=task_aware_client
        )

        # Outer team (just the SoM agent)
        team = RoundRobinGroupChat([som_agent], max_turns=1)

        # Broadcast execution start
        event_server.broadcast("status", {"text": "Society of Mind: Fetch Operator + QA Validator"})

        task_prompt = get_task_prompt()
        full_prompt = f"{task_prompt}\n\nTask: {config.task}"

        # Run the agent and stream messages
        print(f"\n{'='*60}")
        print(f"🎭 Society of Mind: Fetch Operator + QA Validator")
        print(f"{'='*60}\n")

        try:
            messages = []
            async for message in team.run_stream(task=full_prompt):
                messages.append(message)

                if hasattr(message, 'source') and hasattr(message, 'content'):
                    source = message.source
                    content = str(message.content)

                    if source == "FetchOperator":
                        print(f"\n🔧 FetchOperator:")
                        print(f"   {content[:500]}{'...' if len(content) > 500 else ''}")
                        if event_server:
                            event_server.broadcast("agent.message", {
                                "agent": "FetchOperator",
                                "role": "operator",
                                "content": content,
                                "icon": "🔧"
                            })

                    elif source == "QAValidator":
                        print(f"\n✓ QAValidator:")
                        print(f"   {content[:500]}{'...' if len(content) > 500 else ''}")
                        if event_server:
                            event_server.broadcast("agent.message", {
                                "agent": "QAValidator",
                                "role": "validator",
                                "content": content,
                                "icon": "✓"
                            })

                    # Check for tool calls
                    if hasattr(message, 'content') and isinstance(message.content, list):
                        for item in message.content:
                            if hasattr(item, 'name'):
                                print(f"   🛠️  Tool: {item.name}")
                                if event_server:
                                    event_server.broadcast("tool.call", {
                                        "tool": item.name,
                                        "icon": "🛠️"
                                    })

            print(f"\n{'='*60}")
            print(f"✅ Task completed")
            print(f"{'='*60}\n")
            print("TASK_COMPLETE", flush=True)

        except Exception as e:
            print(f"\n❌ Error: {e}")
            print(f"Traceback:")
            import traceback
            traceback.print_exc()
            if event_server:
                event_server.broadcast("session.status", {
                    "status": "error",
                    "error": str(e)
                })

    # Emit session completed event
    try:
        event_server.broadcast("session.completed", {
            "session_id": config.session_id,
            "status": "ok",
            "ts": time.time(),
        })
    except Exception:
        pass

    # Keep UI alive or shutdown based on flag
    if config.keepalive:
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
    else:
        try:
            httpd.shutdown()
        except Exception:
            pass


# ========== CLI Entry Point ==========
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch MCP Agent with Society of Mind")
    parser.add_argument("--task", help="Task for the agent to execute")
    parser.add_argument("--session-id", dest="session_id", help="Session identifier")
    parser.add_argument("--name", default="fetch-session", help="Agent session name")
    parser.add_argument("--model", help="Model to use (e.g., gpt-4o-mini)")
    parser.add_argument("--working-dir", dest="working_dir", default=".", help="Working directory")
    parser.add_argument("--keepalive", action="store_true", help="Keep UI alive after completion")
    args = parser.parse_args()

    # Generate session_id if not provided
    session_id = args.session_id or str(uuid.uuid4())

    # Determine task
    task = args.task or os.getenv("MCP_TASK") or "Fetch web content"

    # Create config
    config = FetchAgentConfig(
        task=task,
        session_id=session_id,
        name=args.name,
        model=args.model,
        working_dir=args.working_dir,
        keepalive=bool(args.keepalive)
    )

    asyncio.run(run_fetch_agent(config))
