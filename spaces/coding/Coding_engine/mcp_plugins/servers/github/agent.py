import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Load .env for environment variables
try:
    import dotenv
    # Find .env in project root (3 levels up from agent.py)
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

# GitHub plugin imports FIRST (before sys.path.insert!)
# This prevents conflict with shared/constants.py
from github_constants import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TASK_PROMPT,
    DEFAULT_GITHUB_OPERATOR_PROMPT,
    DEFAULT_QA_VALIDATOR_PROMPT,
    DEFAULT_USER_CLARIFICATION_PROMPT,
    DEFAULT_GIT_EXPERT_PROMPT,
    DEFAULT_QUESTION_FORMULATOR_PROMPT,
    DEFAULT_ANSWER_VALIDATOR_PROMPT,
)
from event_task import start_github_ui_server
from user_interaction_utils import create_ask_user_tool

# Shared module imports AFTER local imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from event_server import EventServer
from conversation_logger import ConversationLogger, SenseCategory, ThinkingLog, ToolCall, ToolResult
from utils import load_prompt_from_module
from model_init import init_model_client as shared_init_model_client

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
SERVERS_DIR = os.path.dirname(BASE_DIR)  # .../servers
PLUGINS_DIR = os.path.dirname(SERVERS_DIR)  # .../MCP PLUGINS
MODELS_DIR = os.path.join(PLUGINS_DIR, "models")

SYSTEM_PROMPT_PATH = os.path.join(BASE_DIR, "system_prompt.txt")
TASK_PROMPT_PATH = os.path.join(BASE_DIR, "task_prompt.txt")
SERVERS_CONFIG_PATH = os.path.join(SERVERS_DIR, "servers.json")
SECRETS_PATH = os.path.join(SERVERS_DIR, "secrets.json")
MODEL_CONFIG_PATH = os.path.join(MODELS_DIR, "model.json")


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
    """Get system prompt for GitHub agent."""
    prompt = _read_text_file(SYSTEM_PROMPT_PATH, DEFAULT_SYSTEM_PROMPT)
    if not os.path.isfile(SYSTEM_PROMPT_PATH):
        _write_text_file(SYSTEM_PROMPT_PATH, DEFAULT_SYSTEM_PROMPT)
    return prompt


def get_task_prompt() -> str:
    """Get task prompt for GitHub operations."""
    prompt = _read_text_file(TASK_PROMPT_PATH, DEFAULT_TASK_PROMPT)
    if not os.path.isfile(TASK_PROMPT_PATH):
        _write_text_file(TASK_PROMPT_PATH, DEFAULT_TASK_PROMPT)
    return prompt


def load_model_config() -> Dict[str, Any]:
    """Load model configuration from models/model.json."""
    from src.llm_config import get_model
    if not os.path.isfile(MODEL_CONFIG_PATH):
        return {
            "model": os.getenv("OPENAI_MODEL", get_model("mcp_agent")),
            "base_url": os.getenv("OPENAI_BASE_URL"),
            "api_key_env": "OPENAI_API_KEY"
        }
    try:
        with open(MODEL_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {
            "model": get_model("mcp_agent"),
            "base_url": None,
            "api_key_env": "OPENAI_API_KEY"
        }


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
    """Initialize OpenAI chat completion client with intelligent routing.

    Args:
        task: Task description (optional, used for model selection)

    Returns:
        OpenAIChatCompletionClient configured with appropriate model
    """
    # Use shared model initialization utility
    return shared_init_model_client("github", task)


# ========== Main Entry Point (Playwright Pattern) ==========

async def run(
    task_override: Optional[str] = None,
    session_id: Optional[str] = None,
    name: str = "github-session",
    working_dir: str = ".",
    keepalive: bool = False,
):
    """GitHub MCP Agent main entry point.

    Follows the same pattern as Playwright agent for consistency.

    Args:
        task_override: Optional task override from CLI
        name: Session name
        working_dir: Working directory for file operations
        session_id: Optional session identifier
        keepalive: Keep UI server alive after task completion
    """
    # Start UI early using shared EventServer
    event_server = EventServer()
    
    # Generate session_id if not provided
    session_id = session_id or os.getenv("MCP_SESSION_ID") or str(uuid.uuid4())
    
    # Initialize ConversationLogger for ML-ready conversation logs
    conv_logger = ConversationLogger(
        session_id=session_id,
        tool_name="github",
        sense_category=SenseCategory.COLLABORATIVE
    )

    # Start UI with GitHub branding and dynamic port (0 = OS assigns free port)
    httpd, thread, bound_host, bound_port = start_github_ui_server(
        event_server,
        host="127.0.0.1",
        port=0  # Dynamic port assignment
    )

    preview_url = f"http://{bound_host}:{bound_port}/"
    
    # Broadcast session start
    try:
        event_server.broadcast("session.started", {
            "session_id": session_id,
            "ui_url": preview_url,
            "host": bound_host,
            "port": bound_port,
            "ts": time.time(),
        })
    except Exception:
        pass
    
    # SESSION_ANNOUNCE for MCPSessionManager - critical for upstream integration
    try:
        print("SESSION_ANNOUNCE " + json.dumps({
            "session_id": session_id,
            "ui_url": preview_url,
            "host": bound_host,
            "port": bound_port,
        }))
    except Exception:
        print(f"Preview: {preview_url}")

    # Note: Removed .event_port file write - following Playwright single-path pattern
    # SESSION_ANNOUNCE stdout is sufficient for MCPSessionManager discovery

    # Load server configuration
    servers = load_servers_config()
    github_config = None
    git_config = None
    for srv in servers:
        if srv.get("name") == "github" and srv.get("active"):
            github_config = srv
        if srv.get("name") == "git" and srv.get("active"):
            git_config = srv

    if not github_config:
        event_server.broadcast("error", {"text": "GitHub MCP server not found or not active in servers.json"})
        if not keepalive:
            try:
                httpd.shutdown()
            except Exception:
                pass
        else:
            # Keep UI alive for debugging
            while True:
                await asyncio.sleep(3600)
        return

    # Git MCP is optional - nested SoM will work without it, just less context-aware
    if not git_config:
        print("[WARNING] Git MCP server not configured - clarification will work without Git context")

    # Load secrets
    secrets = load_secrets()
    github_secrets = secrets.get("github", {})

    # Prepare environment variables
    env = os.environ.copy()

    # Priority: .env file > secrets.json
    github_token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    if github_token:
        env["GITHUB_PERSONAL_ACCESS_TOKEN"] = github_token
    else:
        # Fallback to secrets.json
        for key, val in github_secrets.items():
            if val:  # Only set if value is not empty
                env[key] = val

    # Then, override with configured env_vars if present
    env_vars = github_config.get("env_vars", {})
    for key, val in env_vars.items():
        if isinstance(val, str) and val.startswith("env:"):
            env_key = val[4:]
            env_val = os.getenv(env_key)
            if env_val:
                env[key] = env_val

    # Create GitHub MCP server params
    github_server_params = StdioServerParams(
        command=github_config["command"],
        args=github_config["args"],
        env=env
    )

    # Create Git MCP server params (if configured)
    git_server_params = None
    if git_config:
        git_env = {}
        git_env_vars = git_config.get("env_vars", {})
        for key, val in git_env_vars.items():
            if isinstance(val, str) and val.startswith("env:"):
                env_key = val[4:]
                env_val = os.getenv(env_key)
                if env_val:
                    git_env[key] = env_val

        git_server_params = StdioServerParams(
            command=git_config["command"],
            args=git_config["args"],
            env=git_env
        )

    # Determine task goal override
    goal_override = task_override or os.getenv("MCP_TASK") or os.getenv("TASK")
    if not goal_override or not goal_override.strip():
        goal_override = "Use the available GitHub tools to accomplish the goal."

    # Initialize model client with task-aware model selection
    try:
        task_aware_client = init_model_client(goal_override)
    except Exception as e:
        event_server.broadcast("error", {"text": f"LLM init failed: {e}"}),
        if keepalive:
            event_server.broadcast("status", {"text": "SSE UI will remain online. Set your API key and restart."}),
            while True:
                await asyncio.sleep(3600)
        else:
            try:
                event_server.broadcast("session.completed", {
                    "session_id": session_id,
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

    # Run Society of Mind multi-agent system with GitHub workbench
    async with McpWorkbench(github_server_params) as github_mcp:
        # Load Society of Mind prompts
        operator_prompt = load_prompt_from_module("github_operator_prompt", BASE_DIR, DEFAULT_GITHUB_OPERATOR_PROMPT)
        qa_prompt = load_prompt_from_module("qa_validator_prompt", BASE_DIR, DEFAULT_QA_VALIDATOR_PROMPT)
        clarification_prompt = load_prompt_from_module("user_clarification_prompt", BASE_DIR, DEFAULT_USER_CLARIFICATION_PROMPT)

        # Create GitHub Operator agent (with GitHub MCP workbench)
        # Add model context to maintain conversation history (last 20 messages)
        github_operator = AssistantAgent(
            "GitHubOperator",
            model_client=task_aware_client,
            workbench=github_mcp,
            system_message=operator_prompt,
            model_context=BufferedChatCompletionContext(buffer_size=20)
        )

        # ========== NESTED CLARIFICATION SOCIETY OF MIND ==========
        # Load nested SoM prompts
        git_expert_prompt = load_prompt_from_module("git_expert_prompt", BASE_DIR, DEFAULT_GIT_EXPERT_PROMPT)
        question_formulator_prompt = load_prompt_from_module("question_formulator_prompt", BASE_DIR, DEFAULT_QUESTION_FORMULATOR_PROMPT)
        answer_validator_prompt = load_prompt_from_module("answer_validator_prompt", BASE_DIR, DEFAULT_ANSWER_VALIDATOR_PROMPT)

        # Create ask_user tool WITHOUT LLM validation (causes issues with "list repos" tasks)
        # The GitHubOperator + QAValidator handle format validation better
        ask_user_tool = create_ask_user_tool(
            event_server=event_server,
            correlation_id=session_id,
            llm_client=None  # Disable LLM validation - let agent handle it
        )

        # Helper function to create nested clarification SoM
        async def create_clarification_som(git_mcp=None):
            """Create nested clarification SoM with optional Git context."""
            # Check if model supports function calling (needed for tools)
            supports_function_calling = task_aware_client.model_info.get("function_calling", False)

            if not supports_function_calling:
                # Reasoning models (o1-mini, o1-preview) don't support tools
                # Fall back to simple clarification agent
                print("[INFO] Model doesn't support function calling - using simple clarification agent")
                return AssistantAgent(
                    "UserClarificationAgent",
                    model_client=task_aware_client,
                    system_message=clarification_prompt
                )

            if git_mcp:
                print("[INFO] Creating Nested Clarification SoM with Git context analysis")

                # 1. GitExpertAgent - Analyzes local Git repository
                git_expert = AssistantAgent(
                    "GitExpertAgent",
                    model_client=task_aware_client,
                    workbench=git_mcp,  # Git MCP tools
                    system_message=git_expert_prompt
                )

                # 2. QuestionFormulatorAgent - Asks user based on Git context
                question_formulator = AssistantAgent(
                    "QuestionFormulatorAgent",
                    model_client=task_aware_client,
                    tools=[ask_user_tool],  # ask_user with LLM validation
                    system_message=question_formulator_prompt
                )

                # 3. AnswerValidatorAgent - Validates user answer format
                answer_validator = AssistantAgent(
                    "AnswerValidatorAgent",
                    model_client=task_aware_client,
                    system_message=answer_validator_prompt
                )

                # Create nested clarification team
                clarification_termination = TextMentionTermination("CLARIFICATION_COMPLETE")
                clarification_team = RoundRobinGroupChat(
                    [git_expert, question_formulator, answer_validator],
                    termination_condition=clarification_termination,
                    max_turns=10  # Limit nested SoM rounds
                )

                # Wrap nested team in SocietyOfMindAgent
                return SocietyOfMindAgent(
                    "ClarificationSociety",
                    team=clarification_team,
                    model_client=task_aware_client
                )
            else:
                # Fallback: Simple clarification agent without Git context
                print("[INFO] Git MCP not available - using simple clarification agent")
                return AssistantAgent(
                    "UserClarificationAgent",
                    model_client=task_aware_client,
                    tools=[ask_user_tool],
                    system_message=clarification_prompt
                )

        # If Git MCP configured, open workbench and create nested SoM
        # Otherwise create simple clarification agent
        if git_server_params:
            git_mcp_context = McpWorkbench(git_server_params)
            git_mcp = await git_mcp_context.__aenter__()
            nested_clarification_som = await create_clarification_som(git_mcp)
        else:
            git_mcp_context = None
            nested_clarification_som = await create_clarification_som(None)

        # Create QA Validator agent (no tools, pure validation)
        # Add model context for validating against conversation history
        qa_validator = AssistantAgent(
            "QAValidator",
            model_client=task_aware_client,
            system_message=qa_prompt,
            model_context=BufferedChatCompletionContext(buffer_size=15)
        )

        # Main team termination: wait for "APPROVE" from QA Validator
        main_termination = TextMentionTermination("APPROVE")
        main_team = RoundRobinGroupChat(
            [github_operator, nested_clarification_som, qa_validator],
            termination_condition=main_termination,
            max_turns=50  # Increased for user interaction and nested SoM
        )

        # Society of Mind wrapper (Main SoM)
        som_agent = SocietyOfMindAgent(
            "github_society_of_mind",
            team=main_team,
            model_client=task_aware_client
        )

        # Outer team (just the SoM agent)
        team = RoundRobinGroupChat([som_agent], max_turns=1)

        # Broadcast execution start with nested SoM info
        som_description = "Society of Mind: GitHub Operator + Nested Clarification SoM (Git Expert + Question Formulator + Answer Validator) + QA Validator" if git_server_params else "Society of Mind: GitHub Operator + User Clarification + QA Validator"
        event_server.broadcast("status", {"text": som_description})
        event_server.broadcast("session.status", {
            "status": "started",
            "tool": "github",
            "task": goal_override,
            "correlation_id": session_id,
            "nested_som": git_server_params is not None
        })

        task_prompt = get_task_prompt()
        full_prompt = f"{task_prompt}\n\nTask: {goal_override}"

        # Log session start for ML dataset
        conv_logger.log_session_start(
            task=config.task,
            model=config.model or get_model("mcp_agent"),
            metadata={
                "agents": ["GitHubOperator", "QAValidator"],
                "system": "Society of Mind",
                "nested_som": git_server_params is not None
            }
        )

        # Run the agent and stream messages
        print(f"\n{'='*60}")
        print(f"🎭 {som_description}")
        print(f"{'='*60}\n")

        try:
            messages = []
            tool_calls_log = []
            tool_results_log = []
            agent_messages = []  # Full messages for ML logging
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
                        "content": content,  # FULL content, not truncated
                        "timestamp": datetime.utcnow().isoformat() + 'Z'
                    })

                    # Pretty print agent dialogue
                    if source == "GitHubOperator":
                        print(f"\n🔧 GitHubOperator:")
                        print(f"   {content[:500]}{'...' if len(content) > 500 else ''}")
                        # Broadcast to GUI
                        if event_server:
                            event_server.broadcast("agent.message", {
                                "agent": "GitHubOperator",
                                "role": "operator",
                                "content": content,
                                "icon": "🔧"
                            })
                        
                    elif source in ["UserClarificationAgent", "ClarificationSociety"]:
                        print(f"\n❓ {source}:")
                        print(f"   {content[:500]}{'...' if len(content) > 500 else ''}")
                        # Broadcast to GUI
                        if event_server:
                            event_server.broadcast("agent.message", {
                                "agent": source,
                                "role": "clarification",
                                "content": content,
                                "icon": "❓"
                            })

                    # Nested SoM agents
                    elif source == "GitExpertAgent":
                        print(f"\n🔍 GitExpertAgent:")
                        print(f"   {content[:500]}{'...' if len(content) > 500 else ''}")
                        if event_server:
                            event_server.broadcast("agent.message", {
                                "agent": "GitExpertAgent",
                                "role": "git_expert",
                                "content": content,
                                "icon": "🔍"
                            })

                    elif source == "QuestionFormulatorAgent":
                        print(f"\n💬 QuestionFormulatorAgent:")
                        print(f"   {content[:500]}{'...' if len(content) > 500 else ''}")
                        if event_server:
                            event_server.broadcast("agent.message", {
                                "agent": "QuestionFormulatorAgent",
                                "role": "question_formulator",
                                "content": content,
                                "icon": "💬"
                            })

                    elif source == "AnswerValidatorAgent":
                        print(f"\n✅ AnswerValidatorAgent:")
                        print(f"   {content[:500]}{'...' if len(content) > 500 else ''}")
                        if event_server:
                            event_server.broadcast("agent.message", {
                                "agent": "AnswerValidatorAgent",
                                "role": "answer_validator",
                                "content": content,
                                "icon": "✅"
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
            try:
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
                        agent="GitHubOperator",
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
            except Exception:
                pass  # Don't crash if conversation logging fails

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
                    "tool": "github",
                    "timestamp": time.time(),
                    "metadata": {
                        "message_count": len(messages),
                        "nested_som": git_server_params is not None
                    }
                })

        except Exception as e:
            # Check for token overflow specifically
            error_msg = str(e).lower()
            if 'context' in error_msg and ('length' in error_msg or 'limit' in error_msg or 'token' in error_msg):
                # Token overflow error
                friendly_msg = (
                    "⚠️ Token Limit Exceeded\n"
                    "Die API-Response war zu groß für das Kontextfenster.\n"
                    "Bitte:\n"
                    "1. Schränken Sie die Suche ein (z.B. spezifisches Repository)\n"
                    "2. Oder verwenden Sie kleinere Result-Limits\n"
                    f"Original Error: {str(e)[:200]}"
                )
                print(f"\n{friendly_msg}\n")
                
                # Broadcast helpful error
                if event_server:
                    event_server.broadcast("session.status", {
                        "status": "error",
                        "error": friendly_msg,
                        "error_type": "token_overflow"
                    })
            else:
                # Other errors
                print(f"\n❌ Error: {e}\n")
                
                # Broadcast generic error
                if event_server:
                    event_server.broadcast("session.status", {
                        "status": "error",
                        "error": str(e)
                    })

    # Cleanup Git MCP workbench if it was created
    if git_mcp_context:
        try:
            await git_mcp_context.__aexit__(None, None, None)
            print("[INFO] Git MCP workbench cleaned up")
        except Exception as e:
            print(f"[WARNING] Error cleaning up Git MCP workbench: {e}")

    # Emit session completed event
    try:
        event_server.broadcast("session.completed", {
            "session_id": session_id,
            "status": "ok",
            "ts": time.time(),
        })
    except Exception:
        pass

    # Keep UI alive or shutdown based on flag
    if keepalive:
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
    parser = argparse.ArgumentParser(description="GitHub MCP Agent with Society of Mind")
    parser.add_argument("--task", help="Task for the agent to execute")
    parser.add_argument("--session-id", dest="session_id", help="Session identifier")
    parser.add_argument("--name", default="github-session", help="Agent session name")
    parser.add_argument("--model", help="Model to use (e.g., gpt-4o-mini)")
    parser.add_argument("--working-dir", dest="working_dir", default=".", help="Working directory")
    parser.add_argument("--keepalive", action="store_true", help="Keep UI alive after completion")
    args = parser.parse_args()

    asyncio.run(run(
        task_override=args.task,
        session_id=args.session_id,
        name=args.name,
        working_dir=args.working_dir,
        keepalive=bool(args.keepalive),
    ))