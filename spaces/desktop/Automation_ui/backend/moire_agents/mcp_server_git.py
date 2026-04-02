"""
MCP Server for Git/GitHub Operations

A dedicated MCP server for Git and GitHub CLI operations,
enabling AI agents to manage repositories.

Usage:
    python mcp_server_git.py

Add to .claude/.mcp.json:
{
    "mcpServers": {
        "git": {
            "command": "python",
            "args": ["python/mcp_server_git.py"]
        }
    }
}
"""

import asyncio
import subprocess
import os
import sys
import json
import logging
from typing import Any, Dict, List, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('GitMCP')

# MCP imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("MCP package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

# Create server instance
server = Server("git-mcp")


async def run_command(cmd: List[str], cwd: Optional[str] = None) -> Dict[str, Any]:
    """Execute a command and return the result."""
    try:
        # Use shell=True on Windows for proper command execution
        if os.name == 'nt':
            cmd_str = ' '.join(f'"{c}"' if ' ' in c else c for c in cmd)
            process = await asyncio.create_subprocess_shell(
                cmd_str,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
        else:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)

        return {
            "success": process.returncode == 0,
            "returncode": process.returncode,
            "stdout": stdout.decode('utf-8', errors='replace').strip(),
            "stderr": stderr.decode('utf-8', errors='replace').strip()
        }
    except asyncio.TimeoutError:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "Command timed out after 60 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e)
        }


def format_result(result: Dict[str, Any]) -> str:
    """Format command result for display."""
    output = []
    if result["stdout"]:
        output.append(result["stdout"])
    if result["stderr"] and not result["success"]:
        output.append(f"Error: {result['stderr']}")
    if not output:
        output.append("Command completed successfully" if result["success"] else "Command failed")
    return "\n".join(output)


# ============================================================================
# Tool Definitions
# ============================================================================

@server.list_tools()
async def list_tools() -> List[Tool]:
    """List all available Git/GitHub tools."""
    return [
        Tool(
            name="git_status",
            description="Show the working tree status of a Git repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the Git repository (default: current directory)"
                    }
                }
            }
        ),
        Tool(
            name="git_init",
            description="Initialize a new Git repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path where to initialize the repository"
                    },
                    "initial_branch": {
                        "type": "string",
                        "description": "Name of the initial branch (default: main)"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="git_add",
            description="Add file contents to the staging area",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the Git repository"
                    },
                    "files": {
                        "type": "string",
                        "description": "Files to add (default: '.' for all)"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="git_commit",
            description="Record changes to the repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the Git repository"
                    },
                    "message": {
                        "type": "string",
                        "description": "Commit message"
                    }
                },
                "required": ["path", "message"]
            }
        ),
        Tool(
            name="git_push",
            description="Push commits to a remote repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the Git repository"
                    },
                    "remote": {
                        "type": "string",
                        "description": "Remote name (default: origin)"
                    },
                    "branch": {
                        "type": "string",
                        "description": "Branch name (default: current branch)"
                    },
                    "set_upstream": {
                        "type": "boolean",
                        "description": "Set upstream tracking (default: false)"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="git_pull",
            description="Fetch and integrate changes from a remote repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the Git repository"
                    },
                    "remote": {
                        "type": "string",
                        "description": "Remote name (default: origin)"
                    },
                    "branch": {
                        "type": "string",
                        "description": "Branch name (default: current branch)"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="git_log",
            description="Show commit logs",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the Git repository"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of commits to show (default: 10)"
                    },
                    "oneline": {
                        "type": "boolean",
                        "description": "Show each commit on one line (default: true)"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="git_diff",
            description="Show changes between commits, working tree, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the Git repository"
                    },
                    "staged": {
                        "type": "boolean",
                        "description": "Show staged changes only (default: false)"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="git_branch",
            description="List, create, or delete branches",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the Git repository"
                    },
                    "name": {
                        "type": "string",
                        "description": "Branch name (for create/delete/checkout)"
                    },
                    "action": {
                        "type": "string",
                        "enum": ["list", "create", "delete", "checkout"],
                        "description": "Action to perform (default: list)"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="git_remote",
            description="Manage remote repositories",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the Git repository"
                    },
                    "action": {
                        "type": "string",
                        "enum": ["list", "add", "remove"],
                        "description": "Action to perform (default: list)"
                    },
                    "name": {
                        "type": "string",
                        "description": "Remote name (for add/remove)"
                    },
                    "url": {
                        "type": "string",
                        "description": "Remote URL (for add)"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="gh_repo_create",
            description="Create a new GitHub repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Repository name"
                    },
                    "description": {
                        "type": "string",
                        "description": "Repository description"
                    },
                    "visibility": {
                        "type": "string",
                        "enum": ["public", "private"],
                        "description": "Repository visibility (default: private)"
                    },
                    "clone": {
                        "type": "boolean",
                        "description": "Clone the repository after creation (default: false)"
                    },
                    "source": {
                        "type": "string",
                        "description": "Path to local repository to push (creates remote from local)"
                    }
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="gh_repo_list",
            description="List GitHub repositories",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of repositories to list (default: 30)"
                    },
                    "visibility": {
                        "type": "string",
                        "enum": ["public", "private", "all"],
                        "description": "Filter by visibility (default: all)"
                    }
                }
            }
        ),
        Tool(
            name="gh_auth_status",
            description="Check GitHub CLI authentication status",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


# ============================================================================
# Tool Handlers
# ============================================================================

@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls."""
    logger.info(f"Tool called: {name} with args: {arguments}")

    try:
        if name == "git_status":
            result = await handle_git_status(arguments)
        elif name == "git_init":
            result = await handle_git_init(arguments)
        elif name == "git_add":
            result = await handle_git_add(arguments)
        elif name == "git_commit":
            result = await handle_git_commit(arguments)
        elif name == "git_push":
            result = await handle_git_push(arguments)
        elif name == "git_pull":
            result = await handle_git_pull(arguments)
        elif name == "git_log":
            result = await handle_git_log(arguments)
        elif name == "git_diff":
            result = await handle_git_diff(arguments)
        elif name == "git_branch":
            result = await handle_git_branch(arguments)
        elif name == "git_remote":
            result = await handle_git_remote(arguments)
        elif name == "gh_repo_create":
            result = await handle_gh_repo_create(arguments)
        elif name == "gh_repo_list":
            result = await handle_gh_repo_list(arguments)
        elif name == "gh_auth_status":
            result = await handle_gh_auth_status(arguments)
        else:
            result = f"Unknown tool: {name}"

        return [TextContent(type="text", text=result)]

    except Exception as e:
        logger.error(f"Error in {name}: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# ============================================================================
# Git Handlers
# ============================================================================

async def handle_git_status(args: Dict[str, Any]) -> str:
    """Handle git status command."""
    path = args.get("path", os.getcwd())
    result = await run_command(["git", "status"], cwd=path)
    return format_result(result)


async def handle_git_init(args: Dict[str, Any]) -> str:
    """Handle git init command."""
    path = args["path"]
    initial_branch = args.get("initial_branch", "main")

    # Create directory if it doesn't exist
    os.makedirs(path, exist_ok=True)

    result = await run_command(["git", "init", "-b", initial_branch], cwd=path)
    return format_result(result)


async def handle_git_add(args: Dict[str, Any]) -> str:
    """Handle git add command."""
    path = args["path"]
    files = args.get("files", ".")

    result = await run_command(["git", "add", files], cwd=path)
    return format_result(result)


async def handle_git_commit(args: Dict[str, Any]) -> str:
    """Handle git commit command."""
    path = args["path"]
    message = args["message"]

    result = await run_command(["git", "commit", "-m", message], cwd=path)
    return format_result(result)


async def handle_git_push(args: Dict[str, Any]) -> str:
    """Handle git push command."""
    path = args["path"]
    remote = args.get("remote", "origin")
    branch = args.get("branch")
    set_upstream = args.get("set_upstream", False)

    cmd = ["git", "push"]
    if set_upstream:
        cmd.append("-u")
    cmd.append(remote)
    if branch:
        cmd.append(branch)

    result = await run_command(cmd, cwd=path)
    return format_result(result)


async def handle_git_pull(args: Dict[str, Any]) -> str:
    """Handle git pull command."""
    path = args["path"]
    remote = args.get("remote", "origin")
    branch = args.get("branch")

    cmd = ["git", "pull", remote]
    if branch:
        cmd.append(branch)

    result = await run_command(cmd, cwd=path)
    return format_result(result)


async def handle_git_log(args: Dict[str, Any]) -> str:
    """Handle git log command."""
    path = args["path"]
    limit = args.get("limit", 10)
    oneline = args.get("oneline", True)

    cmd = ["git", "log", f"-{limit}"]
    if oneline:
        cmd.append("--oneline")

    result = await run_command(cmd, cwd=path)
    return format_result(result)


async def handle_git_diff(args: Dict[str, Any]) -> str:
    """Handle git diff command."""
    path = args["path"]
    staged = args.get("staged", False)

    cmd = ["git", "diff"]
    if staged:
        cmd.append("--staged")

    result = await run_command(cmd, cwd=path)
    return format_result(result) if result["stdout"] else "No changes"


async def handle_git_branch(args: Dict[str, Any]) -> str:
    """Handle git branch operations."""
    path = args["path"]
    action = args.get("action", "list")
    name = args.get("name")

    if action == "list":
        result = await run_command(["git", "branch", "-a"], cwd=path)
    elif action == "create":
        if not name:
            return "Error: Branch name required for create"
        result = await run_command(["git", "branch", name], cwd=path)
    elif action == "delete":
        if not name:
            return "Error: Branch name required for delete"
        result = await run_command(["git", "branch", "-d", name], cwd=path)
    elif action == "checkout":
        if not name:
            return "Error: Branch name required for checkout"
        result = await run_command(["git", "checkout", name], cwd=path)
    else:
        return f"Unknown action: {action}"

    return format_result(result)


async def handle_git_remote(args: Dict[str, Any]) -> str:
    """Handle git remote operations."""
    path = args["path"]
    action = args.get("action", "list")
    name = args.get("name")
    url = args.get("url")

    if action == "list":
        result = await run_command(["git", "remote", "-v"], cwd=path)
    elif action == "add":
        if not name or not url:
            return "Error: Remote name and URL required for add"
        result = await run_command(["git", "remote", "add", name, url], cwd=path)
    elif action == "remove":
        if not name:
            return "Error: Remote name required for remove"
        result = await run_command(["git", "remote", "remove", name], cwd=path)
    else:
        return f"Unknown action: {action}"

    return format_result(result)


# ============================================================================
# GitHub CLI Handlers
# ============================================================================

async def handle_gh_repo_create(args: Dict[str, Any]) -> str:
    """Handle gh repo create command."""
    name = args["name"]
    description = args.get("description", "")
    visibility = args.get("visibility", "private")
    clone = args.get("clone", False)
    source = args.get("source")

    cmd = ["gh", "repo", "create", name]
    cmd.append(f"--{visibility}")

    if description:
        cmd.extend(["--description", description])

    if source:
        # Create from local directory
        cmd.extend(["--source", source, "--push"])
        result = await run_command(cmd)
    elif clone:
        cmd.append("--clone")
        result = await run_command(cmd)
    else:
        result = await run_command(cmd)

    return format_result(result)


async def handle_gh_repo_list(args: Dict[str, Any]) -> str:
    """Handle gh repo list command."""
    limit = args.get("limit", 30)
    visibility = args.get("visibility", "all")

    cmd = ["gh", "repo", "list", "--limit", str(limit)]

    if visibility != "all":
        cmd.extend(["--visibility", visibility])

    result = await run_command(cmd)
    return format_result(result)


async def handle_gh_auth_status(args: Dict[str, Any]) -> str:
    """Handle gh auth status command."""
    result = await run_command(["gh", "auth", "status"])
    return format_result(result)


# ============================================================================
# Main
# ============================================================================

async def main():
    """Main entry point for the MCP server."""
    logger.info("Starting Git MCP Server...")

    async with stdio_server() as (read, write):
        await server.run(
            read,
            write,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)
