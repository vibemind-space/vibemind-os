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
    # Path: mcp_plugins/servers/context7/agent.py -> go up 3 levels to project root
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
from pydantic import BaseModel

# Import global LLM config
from src.llm_config import get_model

# Shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from event_server import EventServer, start_ui_server
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

# ========== Defaults ==========
DEFAULT_SYSTEM_PROMPT = """You are an AutoGen Assistant with Context7 MCP server integration.
You have access to up-to-date code documentation, API references, and real-world code examples from official sources.

Follow the tool usage contract strictly:
- Use context7_* tools for documentation retrieval
- Search for version-specific API documentation
- Fetch code examples from official sources
- Provide accurate, current information
- Handle rate limits gracefully
"""

DEFAULT_TASK_PROMPT = """Use the available Context7 tools to retrieve up-to-date documentation and code examples.

**Instructions:**
1. Specify the framework/library and version when querying
2. Search official documentation sources first
3. Provide code examples with context and explanations
4. Include links to official documentation when available
5. Handle rate limits gracefully and inform user if limits are hit
6. Validate that documentation matches the requested version

**Query Best Practices:**
- Be specific: "React 18 hooks API" instead of "React hooks"
- Include version: "Django 4.2 ORM examples" not just "Django ORM"
- Specify language: "TypeScript async/await syntax" vs "JavaScript async/await"
- Target platform: "AWS Lambda Python runtime" vs "serverless Python"

**Output Format:**
- Provide clear documentation summaries
- Include relevant code examples
- Link to official sources
- Mention version compatibility
- Note any deprecations or breaking changes
"""

DEFAULT_CONTEXT7_OPERATOR_PROMPT = """ROLE: Context7 Documentation Operator
GOAL: Retrieve up-to-date documentation and code examples using Context7 MCP tools.
TOOLS: Use ONLY the available Context7 tools.
GUIDELINES:
- Be specific with versions
- Provide code examples
- Link to official sources
- Handle rate limits gracefully
OUTPUT:
- Brief documentation summary
- Relevant code examples with explanations
- Links to official documentation
- Completion signal: "READY_FOR_VALIDATION"
"""

DEFAULT_QA_VALIDATOR_PROMPT = """ROLE: QA Validator
GOAL: Verify that documentation retrieval is complete and accurate.
CHECK:
- Is documentation up-to-date and version-specific?
- Are code examples provided and explained?
- Are official sources referenced?
RESPONSE:
- If everything is correct: respond ONLY with 'APPROVE' plus 1-2 bullet points
- If something is missing: name precisely 1-2 gaps
"""

# Ensure directory structure exists
os.makedirs(BASE_DIR, exist_ok=True)


def _read_text_file(path: str, default: str) -> str:
    """Read a text file, return default if missing."""
    if not os.path.isfile(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return default


def _write_text_file(path: str, content: str) -> None:
    """Write content to a text file."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception:
        pass


def get_system_prompt() -> str:
    """Get system prompt for Context7 agent."""
    prompt = _read_text_file(SYSTEM_PROMPT_PATH, DEFAULT_SYSTEM_PROMPT)
    if not os.path.isfile(SYSTEM_PROMPT_PATH):
        _write_text_file(SYSTEM_PROMPT_PATH, DEFAULT_SYSTEM_PROMPT)
    return prompt


def get_task_prompt() -> str:
    """Get task prompt for Context7 operations."""
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


def load_prompt_from_module(module_name: str, base_dir: str, default: str) -> str:
    """Load prompt from a Python module's PROMPT variable."""
    try:
        import importlib.util
        module_path = os.path.join(base_dir, f"{module_name}.py")
        if os.path.exists(module_path):
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, 'PROMPT'):
                    return module.PROMPT
        return default
    except Exception as e:
        print(f"Warning: Failed to load prompt from {module_name}: {e}")
        return default


def init_model_client(task: str = "") -> OpenAIChatCompletionClient:
    """Initialize OpenAI chat completion client with intelligent routing."""
    return shared_init_model_client("context7", task)


class Context7AgentConfig(BaseModel):
    session_id: str
    name: str = "context7-session"
    model: str = field(default_factory=lambda: get_model("mcp_agent"))
    task: str
    working_dir: str = "."


async def run_context7_agent(config: Context7AgentConfig):
    """Context7 agent with SESSION_ANNOUNCE and event streaming."""
    logger = setup_logging(f"context7_agent_{config.session_id}")
    event_server = EventServer(session_id=config.session_id, tool_name="context7")

    # Initialize ConversationLogger for ML-ready conversation logs
    conv_logger = ConversationLogger(
        session_id=config.session_id,
        tool_name="context7",
        sense_category=SenseCategory.LINGUISTIC
    )

    try:
        # Start the UI server with event broadcasting
        httpd, thread, host, port = start_ui_server(
            event_server,
            host="127.0.0.1",
            port=0,  # Dynamic port assignment
            tool_name="context7"
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
        event_server.broadcast("session.started", announce_data)

        # Get model client
        model_client = init_model_client(config.task)
        logger.info(f"Model initialized: {config.model}")

        # Load server configuration
        servers = load_servers_config()
        context7_config = None
        for srv in servers:
            if srv.get("name") == "context7" and srv.get("active"):
                context7_config = srv
                break

        if not context7_config:
            event_server.broadcast("error", "Context7 MCP server not found or not active in servers.json")
            logger.error("Context7 server not configured")
            return

        # Load secrets
        secrets = load_secrets()
        context7_secrets = secrets.get("context7", {})

        # Prepare environment variables
        env = os.environ.copy()
        for key, val in context7_secrets.items():
            if val:
                env[key] = val

        env_vars = context7_config.get("env_vars", {})
        for key, val in env_vars.items():
            if isinstance(val, str) and val.startswith("env:"):
                env_key = val[4:]
                env_val = os.getenv(env_key)
                if env_val:
                    env[key] = env_val

        # Create Context7 MCP server params
        server_params = StdioServerParams(
            command=context7_config["command"],
            args=context7_config["args"],
            env=env
        )

        event_server.broadcast("log", f"Starting task: {config.task}")
        event_server.broadcast("status", "running")

        # Run Society of Mind multi-agent system with Context7 workbench
        async with McpWorkbench(server_params) as context7_mcp:
            # Load Society of Mind prompts
            operator_prompt = load_prompt_from_module("context7_operator_prompt", BASE_DIR, DEFAULT_CONTEXT7_OPERATOR_PROMPT)
            qa_prompt = load_prompt_from_module("qa_validator_prompt", BASE_DIR, DEFAULT_QA_VALIDATOR_PROMPT)

            # Create Context7 Operator agent (with Context7 MCP workbench)
            context7_operator = AssistantAgent(
                "Context7Operator",
                model_client=model_client,
                workbench=context7_mcp,
                system_message=operator_prompt
            )

            # Create QA Validator agent (no tools, pure validation)
            qa_validator = AssistantAgent(
                "QAValidator",
                model_client=model_client,
                system_message=qa_prompt
            )

            # Inner team termination: wait for "APPROVE" from QA Validator
            inner_termination = TextMentionTermination("APPROVE")
            inner_team = RoundRobinGroupChat(
                [context7_operator, qa_validator],
                termination_condition=inner_termination,
                max_turns=30
            )

            # Society of Mind wrapper
            som_agent = SocietyOfMindAgent(
                "context7_society_of_mind",
                team=inner_team,
                model_client=model_client
            )

            # Outer team (just the SoM agent)
            team = RoundRobinGroupChat([som_agent], max_turns=1)

            # Broadcast execution start
            event_server.broadcast("status", "Society of Mind: Context7 Operator + QA Validator")

            task_prompt = get_task_prompt()
            full_prompt = f"{task_prompt}\n\nTask: {config.task}"

            # Log session start for ML dataset
            conv_logger.log_session_start(
                task=config.task,
                model=config.model or get_model("mcp_agent"),
                metadata={
                    "agents": ["Context7Operator", "QAValidator"],
                    "system": "Society of Mind"
                }
            )

            # Run the agent and stream messages
            print(f"\n{'='*60}")
            print(f"🎭 Society of Mind: Context7 Operator + QA Validator")
            print(f"{'='*60}\n")

            messages = []
            agent_messages = []  # Full messages for ML logging
            tool_calls_log = []
            tool_results_log = []

            async for message in team.run_stream(task=full_prompt):
                messages.append(message)

                # Extract and broadcast agent messages for live viewing
                if hasattr(message, 'source') and hasattr(message, 'content'):
                    source = message.source
                    content = str(message.content)

                    # Store FULL message for ML logging
                    agent_messages.append({
                        "agent": source,
                        "content": content,  # FULL content, not truncated
                        "timestamp": datetime.utcnow().isoformat() + 'Z'
                    })

                    # Pretty print agent dialogue
                    if source == "Context7Operator":
                        print(f"\n🔧 Context7Operator:")
                        print(f"   {content[:500]}{'...' if len(content) > 500 else ''}")
                        # Broadcast to GUI
                        if event_server:
                            event_server.broadcast("agent.message", {
                                "agent": "Context7Operator",
                                "role": "operator",
                                "content": content,
                                "icon": "🔧"
                            })

                    elif source == "QAValidator":
                        print(f"\n✓ QAValidator:")
                        print(f"   {content[:500]}{'...' if len(content) > 500 else ''}")
                        # Broadcast to GUI
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
                            if hasattr(item, 'name'):  # Tool call
                                print(f"   🛠️  Tool: {item.name}")
                                # Broadcast to GUI
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

            # Log conversation turn for ML dataset with FULL agent messages
            if agent_messages:
                # Build complete conversation text from all agent messages
                full_conversation = "\n\n".join([
                    f"[{msg['agent']}]: {msg['content']}"
                    for msg in agent_messages
                ])

                # Extract operator and validator messages separately
                operator_msgs = [m for m in agent_messages if 'Operator' in m['agent']]
                validator_msgs = [m for m in agent_messages if 'Validator' in m['agent']]

                operator_response = operator_msgs[0]['content'] if operator_msgs else "No operator response"
                validator_feedback = validator_msgs[-1]['content'] if validator_msgs else "No validation"

                conv_logger.log_conversation_turn(
                    agent="Context7Operator",
                    agent_response=operator_response,  # FULL operator response
                    tool_calls=tool_calls_log if tool_calls_log else None,
                    tool_results=tool_results_log if tool_results_log else None,
                    final_response=full_conversation  # COMPLETE multi-agent conversation
                )

                # Also log validator feedback separately
                if validator_msgs:
                    approved = "APPROVE" in validator_feedback.upper()
                    conv_logger.log_validation(
                        validator="QAValidator",
                        feedback=validator_feedback,  # FULL validator feedback
                        approved=approved
                    )

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
                    "tool": "context7",
                    "timestamp": time.time(),
                    "metadata": {
                        "message_count": len(messages)
                    }
                })

            logger.info("Task completed")

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        event_server.broadcast("error", str(e))
        event_server.broadcast("status", "error")

        # Send error as final result
        event_server.broadcast("agent.completion", {
            "status": "error",
            "content": "",
            "tool": "context7",
            "timestamp": time.time(),
            "error": str(e)
        })
        raise
    finally:
        # Keep server running briefly so events can be consumed
        await asyncio.sleep(2)
        httpd.shutdown()


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--session-id', required=False, help='Session identifier')
    parser.add_argument('--name', default='context7-session', help='Session name')
    parser.add_argument('--model', default=get_model("mcp_agent"), help='Model to use')
    parser.add_argument('--task', default='Find React hooks documentation', help='Task to execute')
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
                'session_id': f"context7_{uuid.uuid4().hex[:8]}",
                'name': args.name,
                'model': args.model,
                'task': args.task,
                'working_dir': args.working_dir,
            }

        config = Context7AgentConfig(**config_dict)
        await run_context7_agent(config)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
