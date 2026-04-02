#!/usr/bin/env python3
"""
Git MCP Agent - Version control operations.

Provides:
- Git status, add, commit, push, pull
- Branch management
- Diff and log viewing
- Repository cloning

Follows Society of Mind pattern with EventServer broadcasting.
Uses custom tools for Git operations (shell-based).
"""
import asyncio
import json
import os
import sys
import time
from dataclasses import field
from pathlib import Path
from typing import Optional, List

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Load .env from project root
try:
    import dotenv
    # Path: mcp_plugins/servers/git/agent.py -> go up 3 levels to project root
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    dotenv.load_dotenv(dotenv_path=env_path)
except Exception:
    pass

# Autogen imports
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
from constants import (
    MCP_EVENT_SESSION_ANNOUNCE,
    SESSION_STATE_RUNNING,
    SESSION_STATE_STOPPED,
    SESSION_STATE_ERROR,
)
from model_init import init_model_client as shared_init_model_client
from logging_utils import setup_logging
from conversation_logger import ConversationLogger, SenseCategory, SenseModality


class GitAgentConfig(BaseModel):
    """Configuration for Git MCP Agent."""
    session_id: str
    task: str
    name: str = "git-session"
    model: str = field(default_factory=lambda: get_model("mcp_agent"))
    working_dir: str = "."


# System prompts
GIT_OPERATOR_PROMPT = """You are a Git version control expert.

Your capabilities include:
- git_status: Check repository status
- git_add: Stage files for commit
- git_commit: Create commits with descriptive messages
- git_push: Push to remote repository
- git_pull: Pull from remote repository
- git_branch: List and manage branches
- git_checkout: Switch branches or restore files
- git_diff: View changes (staged and unstaged)
- git_log: View commit history
- git_clone: Clone a repository
- git_fetch: Fetch from remote
- git_merge: Merge branches
- git_stash: Stash and unstash changes

Guidelines:
1. Always check status before committing
2. Write clear, descriptive commit messages
3. Pull before push to avoid conflicts
4. Explain what each operation does
5. Warn before destructive operations (reset, force push)

When you have completed the task, say "TASK_COMPLETE".
"""

QA_VALIDATOR_PROMPT = """You are a QA Validator for Git operations.

Your role:
1. Verify that commits were created successfully
2. Check that pushes/pulls completed without errors
3. Ensure branches are properly managed
4. Validate that the task was completed correctly

When the task is fully validated, say "TASK_COMPLETE".
"""


class GitTools:
    """Custom Git tool implementations using subprocess."""

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir).resolve()

    async def _run_git(self, *args) -> dict:
        """Run a git command and return the result."""
        cmd = ["git"] + list(args)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.working_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return {
                "success": proc.returncode == 0,
                "output": stdout.decode('utf-8', errors='replace').strip(),
                "error": stderr.decode('utf-8', errors='replace').strip() if proc.returncode != 0 else "",
                "command": " ".join(cmd)
            }
        except Exception as e:
            return {"success": False, "error": str(e), "command": " ".join(cmd)}

    async def git_status(self) -> dict:
        """Get the current git status.

        Returns:
            Dict with status information including staged, unstaged, and untracked files.
        """
        result = await self._run_git("status", "--porcelain=v2", "--branch")
        if result["success"]:
            lines = result["output"].splitlines()
            staged = []
            unstaged = []
            untracked = []
            branch = None

            for line in lines:
                if line.startswith("# branch.head"):
                    branch = line.split()[-1]
                elif line.startswith("1 ") or line.startswith("2 "):
                    # Modified/renamed files
                    parts = line.split()
                    xy = parts[1]
                    filename = parts[-1]
                    if xy[0] != '.':
                        staged.append(filename)
                    if xy[1] != '.':
                        unstaged.append(filename)
                elif line.startswith("? "):
                    untracked.append(line[2:])

            return {
                "success": True,
                "branch": branch,
                "staged": staged,
                "unstaged": unstaged,
                "untracked": untracked,
                "clean": len(staged) == 0 and len(unstaged) == 0 and len(untracked) == 0,
                "raw": result["output"]
            }
        return result

    async def git_add(self, files: str = ".") -> dict:
        """Stage files for commit.

        Args:
            files: Files to stage (space-separated or '.' for all)

        Returns:
            Dict with staging result.
        """
        file_list = files.split() if files != "." else ["."]
        result = await self._run_git("add", *file_list)
        if result["success"]:
            return {
                "success": True,
                "message": f"Staged: {files}",
                "files": file_list
            }
        return result

    async def git_commit(self, message: str) -> dict:
        """Create a commit with the given message.

        Args:
            message: Commit message

        Returns:
            Dict with commit result including hash.
        """
        result = await self._run_git("commit", "-m", message)
        if result["success"]:
            # Extract commit hash from output
            lines = result["output"].splitlines()
            commit_hash = None
            for line in lines:
                if line.startswith("["):
                    # Format: [branch hash] message
                    parts = line.split()
                    if len(parts) >= 2:
                        commit_hash = parts[1].rstrip("]")
                    break
            return {
                "success": True,
                "message": message,
                "commit_hash": commit_hash,
                "output": result["output"]
            }
        return result

    async def git_push(self, remote: str = "origin", branch: str = None, force: bool = False) -> dict:
        """Push to remote repository.

        Args:
            remote: Remote name (default: origin)
            branch: Branch to push (default: current branch)
            force: Force push (use with caution!)

        Returns:
            Dict with push result.
        """
        args = ["push", remote]
        if branch:
            args.append(branch)
        if force:
            args.append("--force")

        result = await self._run_git(*args)
        return {
            **result,
            "remote": remote,
            "branch": branch,
            "forced": force
        }

    async def git_pull(self, remote: str = "origin", branch: str = None) -> dict:
        """Pull from remote repository.

        Args:
            remote: Remote name (default: origin)
            branch: Branch to pull (default: current branch)

        Returns:
            Dict with pull result.
        """
        args = ["pull", remote]
        if branch:
            args.append(branch)

        return await self._run_git(*args)

    async def git_branch(self, name: str = None, delete: bool = False, list_all: bool = False) -> dict:
        """Manage branches.

        Args:
            name: Branch name (for create/delete)
            delete: Delete the branch
            list_all: List all branches including remote

        Returns:
            Dict with branch operation result.
        """
        if name and delete:
            return await self._run_git("branch", "-d", name)
        elif name:
            return await self._run_git("branch", name)
        elif list_all:
            return await self._run_git("branch", "-a")
        else:
            result = await self._run_git("branch")
            if result["success"]:
                branches = [b.strip().lstrip("* ") for b in result["output"].splitlines()]
                current = None
                for line in result["output"].splitlines():
                    if line.startswith("* "):
                        current = line[2:].strip()
                        break
                return {
                    "success": True,
                    "branches": branches,
                    "current": current
                }
            return result

    async def git_checkout(self, target: str, create: bool = False) -> dict:
        """Checkout a branch or file.

        Args:
            target: Branch name or file path
            create: Create new branch if it doesn't exist

        Returns:
            Dict with checkout result.
        """
        if create:
            return await self._run_git("checkout", "-b", target)
        return await self._run_git("checkout", target)

    async def git_diff(self, staged: bool = False, file_path: str = None) -> dict:
        """View changes.

        Args:
            staged: Show staged changes instead of unstaged
            file_path: Specific file to diff

        Returns:
            Dict with diff output.
        """
        args = ["diff"]
        if staged:
            args.append("--staged")
        if file_path:
            args.append(file_path)

        result = await self._run_git(*args)
        if result["success"]:
            return {
                "success": True,
                "staged": staged,
                "diff": result["output"],
                "has_changes": len(result["output"]) > 0
            }
        return result

    async def git_log(self, count: int = 10, oneline: bool = True) -> dict:
        """View commit history.

        Args:
            count: Number of commits to show
            oneline: Use oneline format

        Returns:
            Dict with log entries.
        """
        args = ["log", f"-{count}"]
        if oneline:
            args.append("--oneline")

        result = await self._run_git(*args)
        if result["success"] and oneline:
            commits = []
            for line in result["output"].splitlines():
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    commits.append({"hash": parts[0], "message": parts[1]})
            return {
                "success": True,
                "commits": commits,
                "count": len(commits)
            }
        return result

    async def git_clone(self, url: str, directory: str = None) -> dict:
        """Clone a repository.

        Args:
            url: Repository URL
            directory: Target directory (optional)

        Returns:
            Dict with clone result.
        """
        args = ["clone", url]
        if directory:
            args.append(directory)

        return await self._run_git(*args)

    async def git_fetch(self, remote: str = "origin", all_remotes: bool = False) -> dict:
        """Fetch from remote.

        Args:
            remote: Remote name
            all_remotes: Fetch from all remotes

        Returns:
            Dict with fetch result.
        """
        if all_remotes:
            return await self._run_git("fetch", "--all")
        return await self._run_git("fetch", remote)

    async def git_merge(self, branch: str, no_ff: bool = False) -> dict:
        """Merge a branch into current branch.

        Args:
            branch: Branch to merge
            no_ff: Create merge commit even if fast-forward is possible

        Returns:
            Dict with merge result.
        """
        args = ["merge", branch]
        if no_ff:
            args.insert(1, "--no-ff")
        return await self._run_git(*args)

    async def git_stash(self, action: str = "push", message: str = None) -> dict:
        """Stash changes.

        Args:
            action: Stash action (push, pop, list, drop)
            message: Stash message (for push)

        Returns:
            Dict with stash result.
        """
        args = ["stash", action]
        if action == "push" and message:
            args.extend(["-m", message])

        result = await self._run_git(*args)
        if action == "list" and result["success"]:
            stashes = result["output"].splitlines() if result["output"] else []
            return {
                "success": True,
                "stashes": stashes,
                "count": len(stashes)
            }
        return result


async def run_git_agent(config: GitAgentConfig):
    """Run the Git MCP agent with the given configuration."""
    logger = setup_logging(f"git_agent_{config.session_id}")
    event_server = EventServer(session_id=config.session_id, tool_name="git")

    # Initialize ConversationLogger
    conv_logger = ConversationLogger(
        session_id=config.session_id,
        tool_name="git",
        sense_category=SenseCategory.COLLABORATIVE
    )

    try:
        # Start the UI server
        httpd, thread, host, port = start_ui_server(
            event_server,
            host="127.0.0.1",
            port=0,
            tool_name="git"
        )
        logger.info(f"UI server started on {host}:{port}")

        # Announce session
        announce_data = {
            "session_id": config.session_id,
            "host": host,
            "port": port,
            "ui_url": f"http://{host}:{port}/",
            "working_dir": config.working_dir
        }
        print(f"SESSION_ANNOUNCE {json.dumps(announce_data)}", flush=True)
        event_server.broadcast(MCP_EVENT_SESSION_ANNOUNCE, announce_data)

        # Log session start
        conv_logger.log_session_start(config.task, config.model)

        # Get model client
        model_client = shared_init_model_client("git", config.task)
        logger.info(f"Model initialized: {config.model}")

        # Initialize Git tools
        git_tools = GitTools(working_dir=config.working_dir)

        # Create tool list
        tools = [
            git_tools.git_status,
            git_tools.git_add,
            git_tools.git_commit,
            git_tools.git_push,
            git_tools.git_pull,
            git_tools.git_branch,
            git_tools.git_checkout,
            git_tools.git_diff,
            git_tools.git_log,
            git_tools.git_clone,
            git_tools.git_fetch,
            git_tools.git_merge,
            git_tools.git_stash,
        ]

        event_server.broadcast("log", f"Loaded {len(tools)} Git tools")
        event_server.broadcast("log", f"Working directory: {config.working_dir}")

        # Create Operator agent
        operator = AssistantAgent(
            name="GitOperator",
            model_client=model_client,
            tools=tools,
            system_message=GIT_OPERATOR_PROMPT,
            model_context=BufferedChatCompletionContext(buffer_size=20),
        )

        # Create QA Validator agent
        qa_validator = AssistantAgent(
            name="QA_Validator",
            model_client=model_client,
            tools=[],
            system_message=QA_VALIDATOR_PROMPT,
            model_context=BufferedChatCompletionContext(buffer_size=10),
        )

        # Create team
        termination = TextMentionTermination("TASK_COMPLETE")
        team = RoundRobinGroupChat(
            participants=[operator, qa_validator],
            termination_condition=termination,
            max_turns=20,
        )

        # Send running status
        event_server.broadcast("log", f"Starting task: {config.task}")
        event_server.broadcast("status", SESSION_STATE_RUNNING)

        # Run the team
        result = await team.run(task=config.task)

        # Extract result
        result_text = ""
        if result.messages:
            result_text = str(result.messages[-1].content)
        else:
            result_text = "Task completed"

        # Log agent messages
        for msg in result.messages:
            agent_name = getattr(msg, 'source', 'Unknown')
            content = str(msg.content) if hasattr(msg, 'content') else str(msg)
            event_server.broadcast("agent.message", {
                "agent": agent_name,
                "content": content[:500],
                "timestamp": time.time()
            })

        # Send completion
        event_server.broadcast("log", f"Result: {result_text[:200]}...")
        event_server.broadcast("status", SESSION_STATE_STOPPED)

        # Log conversation
        conv_logger.log_conversation_turn(
            agent="GitOperator",
            agent_response=result_text,
            final_response=result_text
        )

        # Send final result
        event_server.broadcast("agent.completion", {
            "status": "success",
            "content": result_text,
            "tool": "git",
            "timestamp": time.time()
        })

        logger.info("Task completed successfully")
        return {"success": True, "result": result_text}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error: {error_msg}", exc_info=True)
        event_server.broadcast("error", error_msg)
        event_server.broadcast("status", SESSION_STATE_ERROR)
        return {"success": False, "error": error_msg}

    finally:
        await asyncio.sleep(2)
        try:
            httpd.shutdown()
        except Exception:
            pass


async def main():
    """Main entry point with argument parsing."""
    import argparse
    parser = argparse.ArgumentParser(description="Git MCP Agent")
    parser.add_argument('--session-id', required=False, help="Session identifier")
    parser.add_argument('--name', default='git-session', help="Session name")
    parser.add_argument('--model', default=get_model("mcp_agent"), help="Model to use")
    parser.add_argument('--task', default='Check git status', help="Task to execute")
    parser.add_argument('--working-dir', default='.', help="Git working directory")
    parser.add_argument('config_json', nargs='?', help="JSON config (alternative)")
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
                'session_id': f"git_{uuid.uuid4().hex[:8]}",
                'name': args.name,
                'model': args.model,
                'task': args.task,
                'working_dir': args.working_dir,
            }

        config = GitAgentConfig(**config_dict)
        result = await run_git_agent(config)

        if not result.get("success"):
            sys.exit(1)

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
