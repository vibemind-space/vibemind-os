# -*- coding: utf-8 -*-
"""
MCP Tool Registry - Central registry for FunctionTools from MCP agents.

This module provides a unified interface to access all MCP tools (docker, git, etc.)
as FunctionTool objects that can be used by the LLM Planner and Executor.
"""
import shlex
import subprocess
import sys
import os
from pathlib import Path
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass
import structlog
import json

# On Windows, npm/npx/pip are .cmd files requiring shell=True
_SHELL = sys.platform == 'win32'

# Add mcp_plugins to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
MCP_PLUGINS_PATH = PROJECT_ROOT / "mcp_plugins" / "servers"
if str(MCP_PLUGINS_PATH) not in sys.path:
    sys.path.insert(0, str(MCP_PLUGINS_PATH))

logger = structlog.get_logger()


@dataclass
class ToolInfo:
    """Information about a registered tool."""
    name: str
    category: str
    description: str
    callable: Callable
    parameters: Dict[str, Any]


class MCPToolRegistry:
    """
    Central registry for MCP FunctionTools.

    Loads tool functions from various MCP agent modules and provides
    a unified interface for the Planner and Executor.

    Usage:
        registry = MCPToolRegistry()

        # List all tools
        tools = registry.list_tools()

        # Get specific tool
        tool = registry.get_tool("docker.list_containers")
        result = tool()

        # Get tools by category
        docker_tools = registry.get_tools_by_category("docker")
    """

    def __init__(self):
        self._tools: Dict[str, ToolInfo] = {}
        self._categories: Dict[str, List[str]] = {}
        self._load_all_tools()

        logger.info("mcp_tool_registry_initialized",
                   tools_count=len(self._tools),
                   categories=list(self._categories.keys()))

    def _load_all_tools(self):
        """Load tools from all available MCP agent modules."""
        # Docker Tools (16 tools)
        self._load_docker_tools()

        # Git Tools
        self._load_git_tools()

        # Filesystem Tools
        self._load_filesystem_tools()

        # NPM Tools
        self._load_npm_tools()

        # Memory Tools
        self._load_memory_tools()

        # Prisma Tools (5 tools)
        self._load_prisma_tools()

        # Pip Tools (3 tools)
        self._load_pip_tools()

        # Python Tools (1 tool)
        self._load_python_tools()

        # Node Tools (1 tool)
        self._load_node_tools()

        # Search Tools (1 tool)
        self._load_search_tools()

    def _load_docker_tools(self):
        """Load Docker CLI tools."""
        try:
            docker_path = MCP_PLUGINS_PATH / "docker"
            if str(docker_path) not in sys.path:
                sys.path.insert(0, str(docker_path))

            from agent import (
                list_containers, run_container, start_container, stop_container,
                remove_container, container_logs, container_inspect, exec_container,
                list_images, pull_image, docker_info, list_networks, list_volumes,
                docker_compose_up, docker_compose_down, docker_compose_ps
            )

            docker_tools = [
                ("list_containers", list_containers, "List Docker containers. Set all=True to include stopped."),
                ("run_container", run_container, "Run a new container. Args: image, name, ports, env, detach."),
                ("start_container", start_container, "Start a stopped container."),
                ("stop_container", stop_container, "Stop a running container."),
                ("remove_container", remove_container, "Remove a container. Set force=True for running containers."),
                ("container_logs", container_logs, "Get logs from a container."),
                ("container_inspect", container_inspect, "Get detailed container information."),
                ("exec_container", exec_container, "Execute command in running container."),
                ("list_images", list_images, "List Docker images."),
                ("pull_image", pull_image, "Pull image from registry."),
                ("docker_info", docker_info, "Get Docker system information."),
                ("list_networks", list_networks, "List Docker networks."),
                ("list_volumes", list_volumes, "List Docker volumes."),
                ("docker_compose_up", docker_compose_up, "Start Compose services."),
                ("docker_compose_down", docker_compose_down, "Stop Compose services."),
                ("docker_compose_ps", docker_compose_ps, "List Compose services status."),
            ]

            for name, func, desc in docker_tools:
                self._register_tool("docker", name, func, desc)

            logger.debug("docker_tools_loaded", count=len(docker_tools))

        except ImportError as e:
            logger.warning("docker_tools_import_failed", error=str(e))

    def _load_git_tools(self):
        """Load Git tools with cwd support."""

        def git_status(paths: str = "", cwd: str = None) -> str:
            """Get git status. Optional paths (comma-separated) to filter."""
            try:
                args = ["git", "status", "--porcelain"]
                if paths:
                    args.append("--")
                    args.extend(p.strip() for p in paths.split(","))
                result = subprocess.run(
                    args, capture_output=True, text=True, timeout=10,
                    encoding='utf-8', errors='replace', cwd=cwd,
                )
                return json.dumps({"status": result.stdout, "clean": len(result.stdout.strip()) == 0})
            except Exception as e:
                return json.dumps({"error": str(e)})

        def git_diff(staged: bool = False, name_only: bool = False, paths: str = "", cwd: str = None) -> str:
            """Get git diff. staged=True for staged, name_only=True for filenames only, paths=comma-separated file filter."""
            try:
                args = ["git", "diff"]
                if staged:
                    args.append("--staged")
                if name_only:
                    args.append("--name-only")
                if paths:
                    args.append("--")
                    args.extend(p.strip() for p in paths.split(","))
                result = subprocess.run(
                    args, capture_output=True, text=True, timeout=30,
                    encoding='utf-8', errors='replace', cwd=cwd,
                )
                output = result.stdout[:5000]
                if name_only:
                    files = [f for f in output.strip().split("\n") if f]
                    return json.dumps({"files": files, "count": len(files)})
                return json.dumps({"diff": output})
            except Exception as e:
                return json.dumps({"error": str(e)})

        def git_log(count: int = 5, cwd: str = None) -> str:
            """Get recent commits."""
            try:
                result = subprocess.run(
                    ["git", "log", f"-{count}", "--oneline"],
                    capture_output=True, text=True, timeout=10,
                    encoding='utf-8', errors='replace', cwd=cwd,
                )
                return json.dumps({"commits": result.stdout.strip().split("\n")})
            except Exception as e:
                return json.dumps({"error": str(e)})

        def git_add(files: str = ".", cwd: str = None) -> str:
            """Stage files. Args: files (comma-separated or '.' for all)."""
            try:
                file_list = files.split(",") if "," in files else [files]
                result = subprocess.run(
                    ["git", "add"] + [f.strip() for f in file_list],
                    capture_output=True, text=True, timeout=10,
                    encoding='utf-8', errors='replace', cwd=cwd,
                )
                return json.dumps({"success": result.returncode == 0, "files": file_list})
            except Exception as e:
                return json.dumps({"error": str(e)})

        def git_commit(message: str, cwd: str = None) -> str:
            """Create a commit with message."""
            try:
                result = subprocess.run(
                    ["git", "commit", "-m", message],
                    capture_output=True, text=True, timeout=30,
                    encoding='utf-8', errors='replace', cwd=cwd,
                )
                return json.dumps({
                    "success": result.returncode == 0,
                    "output": result.stdout or result.stderr
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        def git_branch(cwd: str = None) -> str:
            """Get current branch name."""
            try:
                result = subprocess.run(
                    ["git", "branch", "--show-current"],
                    capture_output=True, text=True, timeout=10,
                    encoding='utf-8', errors='replace', cwd=cwd,
                )
                return json.dumps({"branch": result.stdout.strip()})
            except Exception as e:
                return json.dumps({"error": str(e)})

        def git_checkout(branch: str, create: bool = False, cwd: str = None) -> str:
            """Switch branches. Set create=True for new branch."""
            try:
                args = ["git", "checkout"]
                if create:
                    args.append("-b")
                args.append(branch)
                result = subprocess.run(
                    args, capture_output=True, text=True, timeout=10,
                    encoding='utf-8', errors='replace', cwd=cwd,
                )
                return json.dumps({"success": result.returncode == 0, "branch": branch})
            except Exception as e:
                return json.dumps({"error": str(e)})

        def git_push(remote: str = "origin", branch: str = "", cwd: str = None) -> str:
            """Push to remote."""
            try:
                args = ["git", "push", remote]
                if branch:
                    args.append(branch)
                result = subprocess.run(
                    args, capture_output=True, text=True, timeout=60,
                    encoding='utf-8', errors='replace', cwd=cwd,
                )
                return json.dumps({
                    "success": result.returncode == 0,
                    "output": result.stdout or result.stderr
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        git_tools = [
            ("status", git_status, "Get git status."),
            ("diff", git_diff, "Get git diff. Set staged=True for staged changes."),
            ("log", git_log, "Get recent commits."),
            ("add", git_add, "Stage files."),
            ("commit", git_commit, "Create commit with message."),
            ("branch", git_branch, "Get current branch."),
            ("checkout", git_checkout, "Switch branches."),
            ("push", git_push, "Push to remote."),
        ]

        for name, func, desc in git_tools:
            self._register_tool("git", name, func, desc)

        logger.debug("git_tools_loaded", count=len(git_tools))

    def _load_filesystem_tools(self):
        """Load filesystem tools."""

        def read_file(path: str, encoding: str = "utf-8") -> str:
            """Read file contents."""
            try:
                with open(path, "r", encoding=encoding) as f:
                    content = f.read()
                return json.dumps({"path": path, "content": content[:10000]})  # Limit
            except Exception as e:
                return json.dumps({"error": str(e)})

        def write_file(path: str, content: str, encoding: str = "utf-8") -> str:
            """Write content to file."""
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding=encoding) as f:
                    f.write(content)
                return json.dumps({"success": True, "path": path, "bytes": len(content)})
            except Exception as e:
                return json.dumps({"error": str(e)})

        def list_files(path: str = ".", pattern: str = "*") -> str:
            """List files in directory."""
            try:
                from pathlib import Path
                files = list(Path(path).glob(pattern))
                return json.dumps({
                    "path": path,
                    "files": [str(f) for f in files[:100]]  # Limit
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        def file_exists(path: str) -> str:
            """Check if file exists."""
            exists = os.path.exists(path)
            is_file = os.path.isfile(path) if exists else False
            is_dir = os.path.isdir(path) if exists else False
            return json.dumps({"path": path, "exists": exists, "is_file": is_file, "is_dir": is_dir})

        def delete_file(path: str) -> str:
            """Delete a file."""
            try:
                os.remove(path)
                return json.dumps({"success": True, "path": path})
            except Exception as e:
                return json.dumps({"error": str(e)})

        fs_tools = [
            ("read_file", read_file, "Read file contents."),
            ("write_file", write_file, "Write content to file."),
            ("list_files", list_files, "List files in directory."),
            ("file_exists", file_exists, "Check if file exists."),
            ("delete_file", delete_file, "Delete a file."),
        ]

        for name, func, desc in fs_tools:
            self._register_tool("filesystem", name, func, desc)

        logger.debug("filesystem_tools_loaded", count=len(fs_tools))

    def _load_npm_tools(self):
        """Load NPM tools with cwd and Windows shell support."""

        def npm_install(package: str = "", dev: bool = False, cwd: str = None) -> str:
            """Install npm packages. Empty package installs from package.json."""
            try:
                args = ["npm", "install"]
                if package:
                    args.append(package)
                if dev:
                    args.append("--save-dev")
                result = subprocess.run(
                    args, capture_output=True, text=True, timeout=120,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return json.dumps({
                    "success": result.returncode == 0,
                    "output": result.stdout[:1000] or result.stderr[:1000]
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        def npm_run(script: str, cwd: str = None) -> str:
            """Run npm script (build, test, lint, etc.)."""
            try:
                result = subprocess.run(
                    ["npm", "run", script],
                    capture_output=True, text=True, timeout=300,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return json.dumps({
                    "success": result.returncode == 0,
                    "script": script,
                    "output": result.stdout[:2000] or result.stderr[:2000]
                })
            except subprocess.TimeoutExpired:
                return json.dumps({"error": "Script timed out after 5 minutes"})
            except Exception as e:
                return json.dumps({"error": str(e)})

        def npm_version(cwd: str = None) -> str:
            """Get npm and node versions."""
            try:
                npm_result = subprocess.run(
                    ["npm", "--version"], capture_output=True, text=True, timeout=10,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                node_result = subprocess.run(
                    ["node", "--version"], capture_output=True, text=True, timeout=10,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return json.dumps({
                    "npm": npm_result.stdout.strip(),
                    "node": node_result.stdout.strip()
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        def npm_list(depth: int = 0, cwd: str = None) -> str:
            """List installed packages."""
            try:
                result = subprocess.run(
                    ["npm", "list", f"--depth={depth}", "--json"],
                    capture_output=True, text=True, timeout=30,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return result.stdout[:5000]  # Already JSON
            except Exception as e:
                return json.dumps({"error": str(e)})

        def npm_audit(cwd: str = None) -> str:
            """Run npm audit to check for vulnerabilities."""
            try:
                result = subprocess.run(
                    ["npm", "audit", "--json"],
                    capture_output=True, text=True, timeout=60,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return result.stdout[:10000]  # Already JSON
            except Exception as e:
                return json.dumps({"error": str(e)})

        def npm_npx(command: str, args: str = "", cwd: str = None) -> str:
            """Run an npx command (e.g. prisma, lighthouse, axe)."""
            try:
                cmd = ["npx", command]
                if args:
                    cmd.extend(shlex.split(args, posix=(sys.platform != 'win32')))
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=120,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return json.dumps({
                    "success": result.returncode == 0,
                    "command": command,
                    "output": result.stdout[:5000] or result.stderr[:2000]
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        def npm_outdated(cwd: str = None) -> str:
            """Check for outdated npm packages (JSON output)."""
            try:
                result = subprocess.run(
                    ["npm", "outdated", "--json"],
                    capture_output=True, text=True, timeout=30,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                # npm outdated returns exit code 1 when outdated packages exist
                return result.stdout[:5000] if result.stdout else json.dumps({})
            except Exception as e:
                return json.dumps({"error": str(e)})

        def npm_run_cmd(cmd: str, cwd: str = None) -> str:
            """Run arbitrary npm command (e.g. 'install --legacy-peer-deps')."""
            try:
                args = ["npm"] + shlex.split(cmd, posix=(sys.platform != 'win32'))
                result = subprocess.run(
                    args, capture_output=True, text=True, timeout=120,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return json.dumps({
                    "success": result.returncode == 0,
                    "output": result.stdout[:2000] or result.stderr[:2000]
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        npm_tools = [
            ("install", npm_install, "Install npm packages."),
            ("run", npm_run, "Run npm script (build, test, lint)."),
            ("version", npm_version, "Get npm/node versions."),
            ("list", npm_list, "List installed packages."),
            ("audit", npm_audit, "Run npm audit for vulnerabilities."),
            ("npx", npm_npx, "Run npx command (e.g. prisma, lighthouse)."),
            ("outdated", npm_outdated, "Check for outdated npm packages."),
            ("run_cmd", npm_run_cmd, "Run arbitrary npm command string."),
        ]

        for name, func, desc in npm_tools:
            self._register_tool("npm", name, func, desc)

        logger.debug("npm_tools_loaded", count=len(npm_tools))

    def _load_memory_tools(self):
        """Load simple memory/context tools."""
        _memory_store: Dict[str, Any] = {}

        def memory_store(key: str, value: str) -> str:
            """Store value in memory."""
            _memory_store[key] = value
            return json.dumps({"success": True, "key": key})

        def memory_retrieve(key: str) -> str:
            """Retrieve value from memory."""
            if key in _memory_store:
                return json.dumps({"key": key, "value": _memory_store[key]})
            return json.dumps({"error": f"Key '{key}' not found"})

        def memory_list() -> str:
            """List all stored keys."""
            return json.dumps({"keys": list(_memory_store.keys())})

        memory_tools = [
            ("store", memory_store, "Store value in memory."),
            ("retrieve", memory_retrieve, "Retrieve value from memory."),
            ("list", memory_list, "List all stored keys."),
        ]

        for name, func, desc in memory_tools:
            self._register_tool("memory", name, func, desc)

        logger.debug("memory_tools_loaded", count=len(memory_tools))

    def _load_prisma_tools(self):
        """Load Prisma ORM tools."""

        def prisma_generate(cwd: str = None) -> str:
            """Run prisma generate to create client from schema."""
            try:
                result = subprocess.run(
                    ["npx", "prisma", "generate"],
                    capture_output=True, text=True, timeout=60,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return json.dumps({
                    "success": result.returncode == 0,
                    "output": result.stdout[:2000] or result.stderr[:2000]
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        def prisma_db_push(cwd: str = None) -> str:
            """Push schema changes to database without migrations."""
            try:
                result = subprocess.run(
                    ["npx", "prisma", "db", "push", "--accept-data-loss"],
                    capture_output=True, text=True, timeout=60,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return json.dumps({
                    "success": result.returncode == 0,
                    "output": result.stdout[:2000] or result.stderr[:2000]
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        def prisma_migrate_dev(name: str = "init", cwd: str = None) -> str:
            """Create and apply a new migration."""
            try:
                result = subprocess.run(
                    ["npx", "prisma", "migrate", "dev", "--name", name],
                    capture_output=True, text=True, timeout=120,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return json.dumps({
                    "success": result.returncode == 0,
                    "output": result.stdout[:2000] or result.stderr[:2000]
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        def prisma_migrate_status(cwd: str = None) -> str:
            """Check migration status."""
            try:
                result = subprocess.run(
                    ["npx", "prisma", "migrate", "status"],
                    capture_output=True, text=True, timeout=30,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return json.dumps({
                    "success": result.returncode == 0,
                    "output": result.stdout[:2000] or result.stderr[:2000]
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        def prisma_migrate_reset(cwd: str = None) -> str:
            """Reset database and re-apply all migrations."""
            try:
                result = subprocess.run(
                    ["npx", "prisma", "migrate", "reset", "--force"],
                    capture_output=True, text=True, timeout=120,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return json.dumps({
                    "success": result.returncode == 0,
                    "output": result.stdout[:2000] or result.stderr[:2000]
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        prisma_tools = [
            ("generate", prisma_generate, "Generate Prisma client from schema."),
            ("db_push", prisma_db_push, "Push schema to DB without migrations."),
            ("migrate_dev", prisma_migrate_dev, "Create and apply a new migration."),
            ("migrate_status", prisma_migrate_status, "Check migration status."),
            ("migrate_reset", prisma_migrate_reset, "Reset DB and re-apply migrations."),
        ]

        for name, func, desc in prisma_tools:
            self._register_tool("prisma", name, func, desc)

        logger.debug("prisma_tools_loaded", count=len(prisma_tools))

    def _load_pip_tools(self):
        """Load Python pip tools."""

        def pip_list_outdated(cwd: str = None) -> str:
            """List outdated pip packages as JSON."""
            try:
                result = subprocess.run(
                    ["pip", "list", "--outdated", "--format", "json"],
                    capture_output=True, text=True, timeout=30,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return result.stdout[:5000]  # Already JSON
            except Exception as e:
                return json.dumps({"error": str(e)})

        def pip_install(package: str, upgrade: bool = False, cwd: str = None) -> str:
            """Install a pip package. Set upgrade=True to upgrade."""
            try:
                args = ["pip", "install"]
                if upgrade:
                    args.append("--upgrade")
                args.append(package)
                result = subprocess.run(
                    args, capture_output=True, text=True, timeout=120,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return json.dumps({
                    "success": result.returncode == 0,
                    "output": result.stdout[:1000] or result.stderr[:1000]
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        def pip_audit(cwd: str = None) -> str:
            """Run pip-audit to check for vulnerabilities."""
            try:
                result = subprocess.run(
                    ["pip-audit", "--format", "json"],
                    capture_output=True, text=True, timeout=60,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return result.stdout[:10000]  # Already JSON
            except Exception as e:
                return json.dumps({"error": str(e)})

        pip_tools = [
            ("list_outdated", pip_list_outdated, "List outdated pip packages."),
            ("install", pip_install, "Install a pip package."),
            ("audit", pip_audit, "Run pip-audit for vulnerabilities."),
        ]

        for name, func, desc in pip_tools:
            self._register_tool("pip", name, func, desc)

        logger.debug("pip_tools_loaded", count=len(pip_tools))

    def _load_python_tools(self):
        """Load Python runtime tools."""

        def python_run_script(script_path: str, cwd: str = None) -> str:
            """Run a Python script."""
            try:
                result = subprocess.run(
                    ["python", script_path],
                    capture_output=True, text=True, timeout=120,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return json.dumps({
                    "success": result.returncode == 0,
                    "output": result.stdout[:5000] or result.stderr[:2000]
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        python_tools = [
            ("run_script", python_run_script, "Run a Python script."),
        ]

        for name, func, desc in python_tools:
            self._register_tool("python", name, func, desc)

        logger.debug("python_tools_loaded", count=len(python_tools))

    def _load_node_tools(self):
        """Load Node.js tools."""

        def node_run_script(script_path: str, cwd: str = None) -> str:
            """Run a Node.js script."""
            try:
                result = subprocess.run(
                    ["node", script_path],
                    capture_output=True, text=True, timeout=60,
                    encoding='utf-8', errors='replace', cwd=cwd, shell=_SHELL,
                )
                return json.dumps({
                    "success": result.returncode == 0,
                    "output": result.stdout[:5000] or result.stderr[:2000]
                })
            except Exception as e:
                return json.dumps({"error": str(e)})

        node_tools = [
            ("run_script", node_run_script, "Run a Node.js script file."),
        ]

        for name, func, desc in node_tools:
            self._register_tool("node", name, func, desc)

        logger.debug("node_tools_loaded", count=len(node_tools))

    def _load_search_tools(self):
        """Load code search tools."""
        import shutil

        def ripgrep(pattern: str, path: str = ".", file_type: str = "", max_results: int = 50, cwd: str = None) -> str:
            """Search code with ripgrep (rg). Args: pattern, path, file_type (e.g. 'py', 'ts')."""
            try:
                rg_bin = shutil.which("rg")
                if not rg_bin:
                    return json.dumps({"error": "ripgrep (rg) not installed"})
                args = [rg_bin, "--json", "-m", str(max_results), pattern, path]
                if file_type:
                    args.insert(1, f"--type={file_type}")
                result = subprocess.run(
                    args, capture_output=True, text=True, timeout=30,
                    encoding='utf-8', errors='replace', cwd=cwd,
                )
                # Parse rg JSON output into simplified matches
                matches = []
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("type") == "match":
                            data = entry["data"]
                            matches.append({
                                "file": data["path"]["text"],
                                "line": data["line_number"],
                                "text": data["lines"]["text"].strip(),
                            })
                    except (json.JSONDecodeError, KeyError):
                        continue
                return json.dumps({"pattern": pattern, "matches": matches[:max_results]})
            except Exception as e:
                return json.dumps({"error": str(e)})

        search_tools = [
            ("ripgrep", ripgrep, "Search code with ripgrep (rg)."),
        ]

        for name, func, desc in search_tools:
            self._register_tool("search", name, func, desc)

        logger.debug("search_tools_loaded", count=len(search_tools))

    def _register_tool(self, category: str, name: str,
                       callable: Callable, description: str):
        """Register a tool in the registry."""
        full_name = f"{category}.{name}"

        self._tools[full_name] = ToolInfo(
            name=full_name,
            category=category,
            description=description,
            callable=callable,
            parameters={}  # Could extract from function signature
        )

        if category not in self._categories:
            self._categories[category] = []
        self._categories[category].append(full_name)

    def get_tool(self, name: str) -> Optional[Callable]:
        """
        Get a tool callable by name.

        Args:
            name: Full tool name (e.g., "docker.list_containers")

        Returns:
            Tool callable or None if not found
        """
        tool_info = self._tools.get(name)
        return tool_info.callable if tool_info else None

    def get_tool_info(self, name: str) -> Optional[ToolInfo]:
        """Get tool info by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, str]]:
        """
        List all tools for LLM context.

        Returns:
            List of dicts with name and description
        """
        return [
            {"name": t.name, "description": t.description, "category": t.category}
            for t in self._tools.values()
        ]

    def get_tools_by_category(self, category: str) -> List[str]:
        """Get tool names by category."""
        return self._categories.get(category, [])

    def get_tools_info_by_category(self, category: str) -> List[ToolInfo]:
        """Get ToolInfo objects by category."""
        tool_names = self._categories.get(category, [])
        return [self._tools[name] for name in tool_names if name in self._tools]

    def as_autogen_tools(self, categories: List[str]) -> List:
        """
        Export MCP tools as AutoGen FunctionTools.

        Args:
            categories: List of tool categories to export (e.g., ["docker", "git", "npm"])

        Returns:
            List of FunctionTool objects for AutoGen operators

        Example:
            tools = registry.as_autogen_tools(["docker", "prisma"])
            team = create_team(tools=tools)
        """
        try:
            from autogen_core.tools import FunctionTool
        except ImportError:
            logger.warning("autogen_tools_not_available",
                          msg="Install autogen-agentchat to use as_autogen_tools()")
            return []

        tools = []

        for category in categories:
            tool_infos = self.get_tools_info_by_category(category)

            for tool_info in tool_infos:
                # Create a closure to capture tool_info and registry properly
                def create_tool_wrapper(ti: ToolInfo, registry: "MCPToolRegistry"):
                    def tool_wrapper(args_json: str = "{}") -> str:
                        """
                        Execute MCP tool with JSON arguments.

                        Args:
                            args_json: JSON string containing tool arguments.
                                       Example: '{"container_id": "abc123"}'

                        Returns:
                            JSON string with tool result or error.
                        """
                        import json as json_module
                        try:
                            kwargs = json_module.loads(args_json) if args_json else {}
                            if not isinstance(kwargs, dict):
                                return json_module.dumps({"error": "args_json must be a JSON object"})
                            return registry.call_tool(ti.name, **kwargs)
                        except json_module.JSONDecodeError as e:
                            return json_module.dumps({"error": f"Invalid JSON: {e}"})
                        except Exception as e:
                            return json_module.dumps({"error": str(e)})

                    # Preserve the original function name for better debugging
                    tool_wrapper.__name__ = ti.name.replace(".", "_")
                    tool_wrapper.__doc__ = f"{ti.description}\n\nArgs:\n    args_json: JSON string with tool parameters"
                    return tool_wrapper

                wrapper = create_tool_wrapper(tool_info, self)

                tools.append(FunctionTool(
                    func=wrapper,
                    name=tool_info.name.replace(".", "_"),  # AutoGen doesn't like dots
                    description=f"[MCP:{tool_info.category}] {tool_info.description}. Pass arguments as JSON string.",
                ))

        logger.debug("autogen_tools_created",
                    categories=categories,
                    tool_count=len(tools))

        return tools

    def list_categories(self) -> List[str]:
        """List all tool categories."""
        return list(self._categories.keys())

    def call_tool(self, name: str, **kwargs) -> str:
        """
        Call a tool by name with arguments.

        Args:
            name: Full tool name
            **kwargs: Tool arguments

        Returns:
            Tool result (JSON string)
        """
        tool = self.get_tool(name)
        if not tool:
            return json.dumps({"error": f"Tool '{name}' not found"})

        try:
            return tool(**kwargs)
        except Exception as e:
            logger.error("tool_call_failed", tool=name, error=str(e))
            return json.dumps({"error": str(e)})


# Module-level singleton
_registry_instance: Optional[MCPToolRegistry] = None


def get_tool_registry() -> MCPToolRegistry:
    """Get or create the global MCPToolRegistry instance."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = MCPToolRegistry()
    return _registry_instance


if __name__ == "__main__":
    # Test tool registry
    print("Testing MCPToolRegistry...")

    registry = MCPToolRegistry()

    print(f"\nLoaded {len(registry.list_tools())} tools")
    print(f"Categories: {registry.list_categories()}")

    print("\nTools by category:")
    for cat in registry.list_categories():
        tools = registry.get_tools_by_category(cat)
        print(f"  {cat}: {len(tools)} tools")
        for t in tools[:3]:
            info = registry.get_tool_info(t)
            print(f"    - {t}: {info.description[:50]}...")

    print("\nTest tool calls:")
    print("  git.status:", registry.call_tool("git.status"))
    print("  npm.version:", registry.call_tool("npm.version"))
