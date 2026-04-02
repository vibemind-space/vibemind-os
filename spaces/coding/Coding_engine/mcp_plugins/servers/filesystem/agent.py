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
    # Path: mcp_plugins/servers/filesystem/agent.py -> go up 3 levels to project root
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
from conversation_logger import ConversationLogger, SenseCategory, ThinkingLog, ToolCall, ToolResult

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
SECRETS_PATH = os.path.join(SERVERS_DIR, "secrets.json")
MODEL_CONFIG_PATH = os.path.join(MODELS_DIR, "model.json")

# ========== Defaults ==========
DEFAULT_SYSTEM_PROMPT = """You are an AutoGen Assistant with access to filesystem MCP tools.
Use the available tools to complete filesystem tasks.
Follow the TOOL USAGE contract strictly and call only the exposed tool names.
"""

DEFAULT_TASK_PROMPT = """Use the available filesystem tools to accomplish the goal and stream your progress.
Be clear and concise in your responses.
"""

DEFAULT_OPERATOR_PROMPT = """ROLE: Filesystem Operator
GOAL: Complete filesystem tasks using available MCP tools.
TOOLS: Use ONLY the available MCP filesystem tools.
GUIDELINES:
- Log steps briefly (bullet points)
- Extract only what's necessary (concise, structured)
- Handle errors gracefully
- When the task is fulfilled, provide a compact summary and signal completion clearly.
OUTPUT:
- Brief step log
- Relevant results (compact, JSON-like if appropriate)
- Completion signal: "READY_FOR_VALIDATION"
"""

DEFAULT_QA_VALIDATOR_PROMPT = """ROLE: QA Validator
GOAL: Verify that the user's filesystem task is completely and correctly fulfilled.
CHECK:
- Were the required filesystem operations precisely executed?
- Are the results traceable?
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
    """Get system prompt for filesystem agent."""
    prompt = _read_text_file(SYSTEM_PROMPT_PATH, DEFAULT_SYSTEM_PROMPT)
    if not os.path.isfile(SYSTEM_PROMPT_PATH):
        _write_text_file(SYSTEM_PROMPT_PATH, DEFAULT_SYSTEM_PROMPT)
    return prompt


def get_task_prompt() -> str:
    """Get task prompt for filesystem operations."""
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


def load_secrets() -> Dict[str, Any]:
    """Load secrets from secrets.json."""
    if not os.path.isfile(SECRETS_PATH):
        return {}
    try:
        with open(SECRETS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def init_model_client(task: str = "") -> OpenAIChatCompletionClient:
    """Initialize OpenAI chat completion client with intelligent routing."""
    return shared_init_model_client("filesystem", task)


# ========== Pydantic Config Model ==========
class FilesystemAgentConfig(BaseModel):
    """Configuration for filesystem agent execution."""
    task: str
    session_id: str
    name: str = "filesystem-session"
    model: Optional[str] = None
    working_dir: str = "."
    keepalive: bool = False


# ========== Main Entry Point (SESSION_ANNOUNCE Pattern) ==========
async def run_filesystem_agent(config: FilesystemAgentConfig):
    """Filesystem MCP Agent main entry point.

    Follows the SESSION_ANNOUNCE pattern for backend integration.

    Args:
        config: FilesystemAgentConfig with task, session_id, etc.
    """
    # Setup logging with session identifier
    logger = setup_logging(f"filesystem_agent_{config.session_id}")

    # Initialize EventServer with session logging
    event_server = EventServer(session_id=config.session_id, tool_name="filesystem")

    # Initialize ConversationLogger for ML-ready conversation logs
    conv_logger = ConversationLogger(
        session_id=config.session_id,
        tool_name="filesystem",
        sense_category=SenseCategory.TACTILE
    )

    # Start UI server with dynamic port assignment
    httpd, thread, host, port = start_ui_server(
        event_server,
        host="127.0.0.1",
        port=0,  # Dynamic port assignment
        tool_name="filesystem"
    )

    preview_url = f"http://{host}:{port}/"

    # SESSION_ANNOUNCE for MCPSessionManager - critical for upstream integration
    announce_data = {
        "session_id": config.session_id,
        "host": host,
        "port": port,
        "ui_url": preview_url
    }
    print(f"SESSION_ANNOUNCE {json.dumps(announce_data)}", flush=True)
    event_server.broadcast("session.started", announce_data)

    # Write event port to file for GUI backend discovery
    try:
        port_file = os.path.join(BASE_DIR, ".event_port")
        with open(port_file, 'w') as f:
            f.write(str(port))
        if console:
            console.print(f"[blue]Event port written to {port_file}: {port}[/blue]")
    except Exception as e:
        if console:
            console.print(f"[yellow]Warning: Failed to write event port file: {e}[/yellow]")

    # Load server configuration
    servers = load_servers_config()
    tool_config = None
    for srv in servers:
        if srv.get("name") == "filesystem" and srv.get("active"):
            tool_config = srv
            break

    if not tool_config:
        event_server.broadcast("error", {"text": "Filesystem MCP server not found or not active in servers.json"})
        if not config.keepalive:
            try:
                httpd.shutdown()
            except Exception:
                pass
        else:
            while True:
                await asyncio.sleep(3600)
        return

    # Load secrets
    secrets = load_secrets()
    tool_secrets = secrets.get("filesystem", {})

    # Prepare environment variables
    env = os.environ.copy()

    # Load secrets from secrets.json
    for key, val in tool_secrets.items():
        if val:
            env[key] = val

    # Override with configured env_vars if present
    env_vars = tool_config.get("env_vars", {})
    for key, val in env_vars.items():
        if isinstance(val, str) and val.startswith("env:"):
            env_key = val[4:]
            env_val = os.getenv(env_key)
            if env_val:
                env[key] = env_val

    # Create MCP server params
    server_params = StdioServerParams(
        command=tool_config["command"],
        args=tool_config["args"],
        env=env
    )

    # Initialize model client with task-aware model selection
    try:
        task_aware_client = init_model_client(config.task)
    except Exception as e:
        event_server.broadcast("error", {"text": f"LLM init failed: {e}"})
        if config.keepalive:
            event_server.broadcast("status", {"text": "SSE UI will remain online. Set your API key and restart."})
            while True:
                await asyncio.sleep(3600)
        else:
            try:
                event_server.broadcast("session.completed", {
                    "session_id": config.session_id,
                    "status": "failed",
                    "reason": "llm_init_failed",
                    "ts": time.time(),
                })
            except Exception:
                pass
            try:
                httpd.shutdown()
            except Exception:
                pass
            return

    # Run Society of Mind multi-agent system
    async with McpWorkbench(server_params) as mcp:
        # Load Society of Mind prompts
        operator_prompt = load_prompt_from_module("filesystem_operator_prompt", BASE_DIR, DEFAULT_OPERATOR_PROMPT)
        qa_prompt = load_prompt_from_module("qa_validator_prompt", BASE_DIR, DEFAULT_QA_VALIDATOR_PROMPT)

        # Create Operator agent (with MCP workbench)
        operator = AssistantAgent(
            "FilesystemOperator",
            model_client=task_aware_client,
            workbench=mcp,
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
            [operator, qa_validator],
            termination_condition=main_termination,
            max_turns=30
        )

        # Society of Mind wrapper
        som_agent = SocietyOfMindAgent(
            "filesystem_society_of_mind",
            team=main_team,
            model_client=task_aware_client
        )

        # Outer team (just the SoM agent)
        team = RoundRobinGroupChat([som_agent], max_turns=1)

        # Broadcast execution start
        event_server.broadcast("status", {"text": "Society of Mind: Filesystem Operator + QA Validator"})
        event_server.broadcast("session.status", {
            "status": "started",
            "tool": "filesystem",
            "task": config.task,
            "correlation_id": config.session_id
        })

        task_prompt = get_task_prompt()
        full_prompt = f"{task_prompt}\n\nTask: {config.task}"

        # Log session start for ML dataset
        try:
            model_name = "unknown"
            if hasattr(task_aware_client, 'model'):
                model_name = task_aware_client.model
            elif hasattr(task_aware_client, '_model_info'):
                model_name = str(task_aware_client._model_info)

            conv_logger.log_session_start(
                task=config.task,
                model=str(model_name),
                metadata={"agents": ["Operator", "QAValidator"], "system": "Society of Mind"}
            )
        except Exception:
            pass


        # Run the agent and stream messages
        print(f"\n{'='*60}")
        print(f"🎭 Society of Mind: Filesystem Operator + QA Validator")
        print(f"{'='*60}\n")

        try:
            messages = []
            tool_calls_log = []
            tool_results_log = []
            agent_messages = []
            current_agent = None
            current_response = ""

            async for message in team.run_stream(task=full_prompt):
                messages.append(message)

                # Extract and broadcast agent messages for live viewing
                if hasattr(message, 'source') and hasattr(message, 'content'):
                    source = message.source
                    content = str(message.content)

                    # Store FULL message for ML logging
                    agent_messages.append({
                        "agent": source,
                        "content": content,
                        "timestamp": datetime.utcnow().isoformat() + 'Z'
                    })


                    # Pretty print agent dialogue
                    if source == "FilesystemOperator":
                        print(f"\n🔧 FilesystemOperator:")
                        print(f"   {content[:500]}{'...' if len(content) > 500 else ''}")
                        if event_server:
                            event_server.broadcast("agent.message", {
                                "agent": "FilesystemOperator",
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
                                tool_name = item.name
                                tool_args = getattr(item, 'arguments', {})

                                try:
                                    tool_call = conv_logger.log_tool_call(
                                        tool_name=tool_name,
                                        arguments=tool_args if isinstance(tool_args, dict) else {}
                                    )
                                    tool_calls_log.append(tool_call)
                                except Exception:
                                    pass

                                print(f"   🛠️  Tool: {item.name}")
                                if event_server:
                                    event_server.broadcast("tool.call", {
                                        "tool": item.name,
                                        "icon": "🛠️"
                                    })

            print(f"\n{'='*60}")
            print(f"✅ Task completed")
            print(f"{'='*60}\n")

            # Extract final result from messages
            final_content = ""
            if messages:
                final_message = messages[-1]
                if hasattr(final_message, 'content'):
                    final_content = str(final_message.content)

            # Log conversation turn for ML dataset
            try:
                if agent_messages:
                    full_conversation = "\n\n".join([f"[{msg['agent']}]: {msg['content']}" for msg in agent_messages])
                    operator_msgs = [m for m in agent_messages if 'Operator' in m['agent']]
                    validator_msgs = [m for m in agent_messages if 'Validator' in m['agent']]
                    operator_response = operator_msgs[0]['content'] if operator_msgs else "No response"
                    validator_feedback = validator_msgs[-1]['content'] if validator_msgs else "No validation"

                    conv_logger.log_conversation_turn(
                        agent="Operator",
                        agent_response=operator_response,
                        tool_calls=tool_calls_log if tool_calls_log else None,
                        tool_results=tool_results_log if tool_results_log else None,
                        final_response=full_conversation
                    )

                    if validator_msgs:
                        approved = "APPROVE" in validator_feedback.upper()
                        conv_logger.log_validation(
                            validator="QAValidator",
                            feedback=validator_feedback,
                            approved=approved
                        )
            except Exception:
                pass

            # Broadcast session completion with final result
            if event_server:
                event_server.broadcast("session.status", {
                    "status": "completed",
                    "message_count": len(messages)
                })

                # Send final result event for modal display
                event_server.broadcast("agent.completion", {
                    "status": "success",
                    "content": final_content,
                    "tool": "filesystem",
                    "timestamp": time.time(),
                    "metadata": {
                        "message_count": len(messages)
                    }
                })

        except Exception as e:
            print(f"\n❌ Error: {e}\n")
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
        return


# ========== CLI Entry Point ==========
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Filesystem MCP Agent with Society of Mind")
    parser.add_argument("--task", help="Task for the agent to execute")
    parser.add_argument("--session-id", dest="session_id", help="Session identifier")
    parser.add_argument("--name", default="filesystem-session", help="Agent session name")
    parser.add_argument("--model", help="Model to use (e.g., gpt-4o-mini)")
    parser.add_argument("--working-dir", dest="working_dir", default=".", help="Working directory for file operations")
    parser.add_argument("--keepalive", action="store_true", help="Keep UI alive after completion")
    # gRPC Worker Mode
    parser.add_argument("--grpc", action="store_true", help="Start as gRPC worker")
    parser.add_argument("--grpc-port", dest="grpc_port", type=int, default=50072, help="gRPC port (default: 50072)")
    args = parser.parse_args()

    # gRPC Worker Mode
    if args.grpc:
        import sys
        from pathlib import Path
        shared_dir = Path(__file__).parent.parent / "shared"
        if str(shared_dir) not in sys.path:
            sys.path.insert(0, str(shared_dir))
        from grpc_adapter import serve_as_grpc, AgentGRPCConfig
        grpc_config = AgentGRPCConfig(
            name="filesystem",
            port=args.grpc_port,
            agent_runner=run_filesystem_agent,
            config_class=FilesystemAgentConfig,
            description="Filesystem MCP Agent for file operations",
            capabilities=["read_file", "write_file", "list_directory", "delete_file", "move_file"]
        )
        print(f"🚀 Starting filesystem gRPC worker on port {args.grpc_port}...")
        asyncio.run(serve_as_grpc(grpc_config))
    else:
        # Standard CLI Mode
        # Generate session_id if not provided
        session_id = args.session_id or str(uuid.uuid4())

        # Determine task
        task = args.task or os.getenv("MCP_TASK") or "Complete filesystem task"

        # Create config
        config = FilesystemAgentConfig(
            task=task,
            session_id=session_id,
            name=args.name,
            model=args.model,
            working_dir=args.working_dir,
            keepalive=bool(args.keepalive)
        )

        asyncio.run(run_filesystem_agent(config))
