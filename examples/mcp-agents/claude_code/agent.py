#!/usr/bin/env python3
"""
MCP Server für Claude Code Integration

Stellt Claude Code (CLI/SDK) als MCP Tools bereit.
Ermöglicht die Nutzung von Claude Code über das MCP Protokoll.

Tools:
- claude_execute: Führt einen Claude Code Prompt aus
- claude_execute_in_dir: Führt Claude Code in einem spezifischen Verzeichnis aus
- claude_conversation: Multi-Turn Konversation
- claude_status: Prüft ob Claude Code verfügbar ist
"""
import asyncio
import json
import os
import sys
import shutil
import subprocess
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

# Setup paths
script_dir = os.path.dirname(os.path.abspath(__file__))
servers_dir = os.path.dirname(script_dir)
sys.path.insert(0, os.path.join(servers_dir, "shared"))

# MCP imports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Pydantic for config
from pydantic import BaseModel, Field

# Shared imports (optional - may not be needed for standalone operation)
try:
    from event_server import EventServer
    from constants import MCP_EVENT_SESSION_ANNOUNCE as SESSION_ANNOUNCE
except ImportError:
    EventServer = None
    SESSION_ANNOUNCE = "SESSION_ANNOUNCE"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

class ClaudeCodeConfig(BaseModel):
    """Konfiguration für den Claude Code MCP Server"""
    working_dir: str = Field(default=".", description="Working directory for Claude Code")
    timeout: int = Field(default=300, description="Timeout in seconds")
    model: str = Field(default="", description="Model override (optional)")
    session_id: str = Field(default="", description="Session ID for tracking")


# ============================================================================
# Claude Code Wrapper
# ============================================================================

def find_claude_executable() -> Optional[str]:
    """Findet das Claude Code Executable oder npx fallback"""
    # Mögliche Pfade
    possible_paths = [
        shutil.which("claude"),  # In PATH
        r"C:\Users\User\.claude\local\claude.exe",
        r"C:\Program Files\Claude\claude.exe",
        os.path.expanduser("~/.claude/local/claude"),
        "/usr/local/bin/claude",
    ]

    for path in possible_paths:
        if path and os.path.exists(path):
            return path

    # Fallback: npx
    npx_path = shutil.which("npx")
    if npx_path:
        return "npx"  # Special marker für npx-Modus

    return None


def get_claude_command(claude_exe: str) -> List[str]:
    """Gibt den Basis-Befehl für Claude Code zurück"""
    if claude_exe == "npx":
        return ["npx", "@anthropic-ai/claude-code"]
    return [claude_exe]


async def run_claude_code(
    prompt: str,
    working_dir: str = ".",
    timeout: int = 300,
    model: str = "",
    output_format: str = "text",
    allowed_tools: Optional[List[str]] = None,
    agent_name: Optional[str] = None,
    max_turns: Optional[int] = None,
    dangerously_skip_permissions: bool = False,
) -> Dict[str, Any]:
    """
    Führt Claude Code mit einem Prompt aus.

    Args:
        prompt: Der Prompt für Claude
        working_dir: Arbeitsverzeichnis
        timeout: Timeout in Sekunden
        model: Model override (optional)
        output_format: text oder json
        allowed_tools: List of tools Claude may use (e.g. ["Edit","Write","Read","Bash"]).
                       When set, --allowedTools is passed so Claude can modify files
                       in non-interactive --print mode.
        agent_name: Optional .claude/agents/ agent name for --agent flag
        max_turns: Optional max agentic turns for --max-turns cost control
        dangerously_skip_permissions: If True, use --dangerously-skip-permissions
                                      (all tools allowed, no prompts). Overrides allowed_tools.

    Returns:
        Dict mit status, output, error
    """
    claude_exe = find_claude_executable()

    if not claude_exe:
        return {
            "status": "error",
            "error": "Claude Code nicht gefunden. Bitte installieren: npm install -g @anthropic-ai/claude-code",
            "output": ""
        }

    # Command bauen (mit npx support)
    cmd = get_claude_command(claude_exe)

    # Permission mode: --dangerously-skip-permissions (all tools, no prompts)
    # OR --allowedTools for specific tool access
    if dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")
        # With --dangerously-skip-permissions, always pipe via stdin (safe for large prompts)
        use_stdin_prompt = True
    else:
        cmd.append("--print")
        # Allow specific tools so Claude can write files in --print mode
        # NOTE: --allowedTools is variadic (<tools...>) and swallows the
        # positional prompt argument.  When allowed_tools is set we pipe
        # the prompt via stdin instead of appending it to the command.
        use_stdin_prompt = bool(allowed_tools)
        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])

    if model:
        cmd.extend(["--model", model])

    if output_format == "json":
        cmd.append("--output-format=json")

    # Agent routing: .claude/agents/{name}.md
    if agent_name:
        cmd.extend(["--agent", agent_name])

    # Cost control: max agentic turns
    if max_turns:
        cmd.extend(["--max-turns", str(max_turns)])

    # -p flag for non-interactive mode (when not using --dangerously-skip-permissions)
    if dangerously_skip_permissions:
        cmd.append("-p")

    # Prompt: positional arg (default) or via stdin (when --allowedTools/--dangerously-skip-permissions is used)
    if not use_stdin_prompt:
        cmd.append(prompt)

    try:
        prompt_bytes = prompt.encode("utf-8") if use_stdin_prompt else None
        stdin_pipe = asyncio.subprocess.PIPE if use_stdin_prompt else None

        # Prozess starten - nutze shell für npx auf Windows
        if claude_exe == "npx":
            if use_stdin_prompt:
                cmd_str = " ".join(cmd)
            else:
                # Shell command für npx - Prompt mit Double-Quotes für Windows
                prompt_escaped = prompt.replace('"', '\\"')
                base_cmd = cmd[:-1]  # Alles außer Prompt
                cmd_str = " ".join(base_cmd) + ' "' + prompt_escaped + '"'
            process = await asyncio.create_subprocess_shell(
                cmd_str,
                cwd=working_dir,
                stdin=stdin_pipe,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ}
            )
        else:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=working_dir,
                stdin=stdin_pipe,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ}
            )

        # Auf Ergebnis warten
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=prompt_bytes),
            timeout=timeout
        )

        output = stdout.decode("utf-8", errors="replace")
        error = stderr.decode("utf-8", errors="replace")

        if process.returncode == 0:
            return {
                "status": "completed",
                "output": output,
                "error": error if error else None,
                "exit_code": process.returncode
            }
        else:
            return {
                "status": "failed",
                "output": output,
                "error": error or f"Exit code: {process.returncode}",
                "exit_code": process.returncode
            }

    except asyncio.TimeoutError:
        return {
            "status": "timeout",
            "error": f"Timeout nach {timeout} Sekunden",
            "output": ""
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "output": ""
        }


async def run_claude_streaming(
    prompt: str,
    working_dir: str = ".",
    timeout: int = 300
) -> asyncio.subprocess.Process:
    """
    Startet Claude Code mit Streaming Output.

    Returns:
        Der laufende Prozess für Streaming
    """
    claude_exe = find_claude_executable()

    if not claude_exe:
        raise FileNotFoundError("Claude Code nicht gefunden")

    cmd = get_claude_command(claude_exe)
    cmd.append("--print")  # Non-interactive mode

    if claude_exe == "npx":
        # Shell command mit Double-Quote Escaping für Windows
        prompt_escaped = prompt.replace('"', '\\"')
        cmd_str = " ".join(cmd) + ' "' + prompt_escaped + '"'
        process = await asyncio.create_subprocess_shell(
            cmd_str,
            cwd=working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ}
        )
    else:
        cmd.append(prompt)  # Positional argument
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ}
        )

    return process


# ============================================================================
# Conversation Manager
# ============================================================================

class ConversationManager:
    """Verwaltet Multi-Turn Konversationen"""

    def __init__(self):
        self.conversations: Dict[str, List[Dict]] = {}

    def get_or_create(self, session_id: str) -> List[Dict]:
        if session_id not in self.conversations:
            self.conversations[session_id] = []
        return self.conversations[session_id]

    def add_message(self, session_id: str, role: str, content: str):
        conv = self.get_or_create(session_id)
        conv.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

    def get_context(self, session_id: str, max_messages: int = 10) -> str:
        conv = self.get_or_create(session_id)
        recent = conv[-max_messages:] if len(conv) > max_messages else conv

        context_parts = []
        for msg in recent:
            role = "User" if msg["role"] == "user" else "Assistant"
            context_parts.append(f"{role}: {msg['content']}")

        return "\n\n".join(context_parts)

    def clear(self, session_id: str):
        if session_id in self.conversations:
            del self.conversations[session_id]


# Global conversation manager
_conversation_manager = ConversationManager()


# ============================================================================
# MCP Server
# ============================================================================

# Create MCP server
app = Server("claude-code")


@app.list_tools()
async def list_tools():
    """List available tools"""
    return [
        Tool(
            name="claude_execute",
            description="Execute a prompt using Claude Code CLI. Returns the AI response. "
                       "Use this for code generation, analysis, refactoring, and other AI tasks.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The prompt to send to Claude"
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Working directory for file operations (default: current dir)",
                        "default": "."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 300)",
                        "default": 300
                    }
                },
                "required": ["prompt"]
            }
        ),
        Tool(
            name="claude_execute_with_context",
            description="Execute a prompt with file context. Reads specified files and includes them in the prompt.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The prompt to send to Claude"
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths to include as context"
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Working directory",
                        "default": "."
                    }
                },
                "required": ["prompt"]
            }
        ),
        Tool(
            name="claude_conversation",
            description="Multi-turn conversation with Claude. Maintains context across messages.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Your message to Claude"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session ID for conversation continuity",
                        "default": "default"
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Working directory",
                        "default": "."
                    }
                },
                "required": ["message"]
            }
        ),
        Tool(
            name="claude_code_generation",
            description="Generate code using Claude Code with structured output. "
                       "Optimized for code generation tasks.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Description of the code to generate"
                    },
                    "language": {
                        "type": "string",
                        "description": "Programming language (typescript, python, etc.)",
                        "default": "typescript"
                    },
                    "output_file": {
                        "type": "string",
                        "description": "Path where the code should be saved (optional)"
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Working directory",
                        "default": "."
                    }
                },
                "required": ["task"]
            }
        ),
        Tool(
            name="claude_status",
            description="Check if Claude Code is available and return version info",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="claude_clear_conversation",
            description="Clear conversation history for a session",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID to clear",
                        "default": "default"
                    }
                },
                "required": []
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls"""

    if name == "claude_execute":
        prompt = arguments.get("prompt", "")
        working_dir = arguments.get("working_dir", ".")
        timeout = arguments.get("timeout", 300)

        if not prompt:
            return [TextContent(type="text", text="Error: prompt is required")]

        result = await run_claude_code(
            prompt=prompt,
            working_dir=working_dir,
            timeout=timeout
        )

        response = {
            "status": result["status"],
            "output": result.get("output", ""),
        }
        if result.get("error"):
            response["error"] = result["error"]

        return [TextContent(type="text", text=json.dumps(response, indent=2, ensure_ascii=False))]

    elif name == "claude_execute_with_context":
        prompt = arguments.get("prompt", "")
        files = arguments.get("files", [])
        working_dir = arguments.get("working_dir", ".")

        if not prompt:
            return [TextContent(type="text", text="Error: prompt is required")]

        # Build context from files
        file_contexts = []
        for file_path in files:
            full_path = os.path.join(working_dir, file_path) if not os.path.isabs(file_path) else file_path
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                file_contexts.append(f"### File: {file_path}\n```\n{content}\n```")
            except Exception as e:
                file_contexts.append(f"### File: {file_path}\nError reading file: {e}")

        # Combine prompt with file context
        full_prompt = prompt
        if file_contexts:
            full_prompt = f"""## File Context

{chr(10).join(file_contexts)}

## Task

{prompt}"""

        result = await run_claude_code(
            prompt=full_prompt,
            working_dir=working_dir,
            timeout=300
        )

        return [TextContent(type="text", text=json.dumps({
            "status": result["status"],
            "output": result.get("output", ""),
            "files_included": files,
            "error": result.get("error")
        }, indent=2, ensure_ascii=False))]

    elif name == "claude_conversation":
        message = arguments.get("message", "")
        session_id = arguments.get("session_id", "default")
        working_dir = arguments.get("working_dir", ".")

        if not message:
            return [TextContent(type="text", text="Error: message is required")]

        # Add user message
        _conversation_manager.add_message(session_id, "user", message)

        # Get conversation context
        context = _conversation_manager.get_context(session_id)

        # Build prompt with context
        full_prompt = f"""## Conversation History

{context}

## Current Message

Please continue the conversation naturally based on the context above.
Respond to the latest user message."""

        result = await run_claude_code(
            prompt=full_prompt,
            working_dir=working_dir,
            timeout=300
        )

        if result["status"] == "completed":
            # Add assistant response
            _conversation_manager.add_message(session_id, "assistant", result["output"])

        return [TextContent(type="text", text=json.dumps({
            "status": result["status"],
            "response": result.get("output", ""),
            "session_id": session_id,
            "message_count": len(_conversation_manager.get_or_create(session_id)),
            "error": result.get("error")
        }, indent=2, ensure_ascii=False))]

    elif name == "claude_code_generation":
        task = arguments.get("task", "")
        language = arguments.get("language", "typescript")
        output_file = arguments.get("output_file", "")
        working_dir = arguments.get("working_dir", ".")

        if not task:
            return [TextContent(type="text", text="Error: task is required")]

        # Build code generation prompt
        prompt = f"""Generate {language} code for the following task:

{task}

Requirements:
- Write clean, production-ready code
- Include proper type annotations
- Add comments for complex logic
- Follow best practices for {language}

Output ONLY the code, no explanations."""

        result = await run_claude_code(
            prompt=prompt,
            working_dir=working_dir,
            timeout=300
        )

        # Optionally save to file
        saved = False
        if output_file and result["status"] == "completed":
            try:
                full_path = os.path.join(working_dir, output_file) if not os.path.isabs(output_file) else output_file
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(result["output"])
                saved = True
            except Exception as e:
                result["save_error"] = str(e)

        return [TextContent(type="text", text=json.dumps({
            "status": result["status"],
            "code": result.get("output", ""),
            "language": language,
            "saved_to": output_file if saved else None,
            "error": result.get("error")
        }, indent=2, ensure_ascii=False))]

    elif name == "claude_status":
        claude_exe = find_claude_executable()

        if not claude_exe:
            return [TextContent(type="text", text=json.dumps({
                "available": False,
                "error": "Claude Code nicht gefunden",
                "install_hint": "npm install -g @anthropic-ai/claude-code"
            }, indent=2))]

        # Try to get version
        try:
            if claude_exe == "npx":
                cmd = "npx @anthropic-ai/claude-code --version"
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, shell=True)
            else:
                result = subprocess.run([claude_exe, "--version"], capture_output=True, text=True, timeout=30)
            version = result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception as e:
            version = f"unknown ({str(e)[:50]})"

        return [TextContent(type="text", text=json.dumps({
            "available": True,
            "executable": claude_exe,
            "mode": "npx" if claude_exe == "npx" else "direct",
            "version": version,
            "active_sessions": len(_conversation_manager.conversations)
        }, indent=2))]

    elif name == "claude_clear_conversation":
        session_id = arguments.get("session_id", "default")
        _conversation_manager.clear(session_id)

        return [TextContent(type="text", text=json.dumps({
            "cleared": True,
            "session_id": session_id
        }, indent=2))]

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ============================================================================
# Main
# ============================================================================

async def run_server():
    """Run the MCP server"""
    logger.info("Starting Claude Code MCP Server on stdio...")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


async def run_task_mode(
    task: str,
    working_dir: str,
    session_id: str,
    timeout: int = 300,
    agent_name: Optional[str] = None,
    max_turns: Optional[int] = None,
):
    """
    Run a single task using Claude Code and exit.

    This mode is used by MCPAgentPool to spawn claude-code as a subprocess
    with --task/--session-id/--working-dir CLI args (same pattern as prisma/npm agents).

    Uses --dangerously-skip-permissions for full tool access with zero
    permission prompts + --output-format json for structured parsing.
    """
    logger.info(f"[{session_id}] Task mode: {task[:100]}...")
    logger.info(f"[{session_id}] Working dir: {working_dir}")
    logger.info(f"[{session_id}] Agent: {agent_name or 'default'} | Max turns: {max_turns or 'unlimited'}")

    # Get model from llm_models.yml (single source of truth)
    cli_model = ""
    try:
        from src.llm_config import get_model
        cli_model = get_model("cli")
    except (ImportError, Exception):
        pass

    result = await run_claude_code(
        prompt=task,
        working_dir=working_dir,
        timeout=timeout,
        model=cli_model,
        output_format="json",
        dangerously_skip_permissions=True,
        agent_name=agent_name,
        max_turns=max_turns or 10,
    )

    # Output structured result to stdout (MCPAgentPool parses this)
    output = {
        "session_id": session_id,
        "status": result["status"],
        "output": result.get("output", ""),
        "error": result.get("error"),
    }

    # Print the output for MCPAgentPool to capture
    if result.get("output"):
        print(result["output"])

    # Print structured JSON on a separate line for data parsing
    print(json.dumps({"success": result["status"] == "completed", "session_id": session_id}))

    if result["status"] != "completed":
        logger.error(f"[{session_id}] Task failed: {result.get('error', 'unknown')}")
        sys.exit(1)
    else:
        logger.info(f"[{session_id}] Task completed successfully")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Claude Code MCP Server")
    parser.add_argument("--check", action="store_true", help="Check if Claude Code is available")
    parser.add_argument("--task", default=None, help="Task to execute (enables task mode)")
    parser.add_argument("--session-id", default=None, help="Session identifier")
    parser.add_argument("--working-dir", default=".", help="Working directory for file operations")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout in seconds (default: 600)")

    args = parser.parse_args()

    if args.check:
        exe = find_claude_executable()
        if exe:
            mode = "npx" if exe == "npx" else "direct"
            print(f"[OK] Claude Code found: {exe} (mode: {mode})")
            try:
                if exe == "npx":
                    cmd = "npx @anthropic-ai/claude-code --version"
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, shell=True)
                else:
                    result = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    print(f"     Version: {result.stdout.strip()}")
            except Exception as e:
                print(f"     Version check failed: {e}")
        else:
            print("[X] Claude Code not found")
            print("  Install: npm install -g @anthropic-ai/claude-code")
        return

    # Task mode: run a single task and exit (used by MCPAgentPool)
    if args.task:
        import uuid
        session_id = args.session_id or f"claude-code_{uuid.uuid4().hex[:8]}"
        asyncio.run(run_task_mode(
            task=args.task,
            working_dir=args.working_dir,
            session_id=session_id,
            timeout=args.timeout,
        ))
        return

    # Default: run as MCP stdio server
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
