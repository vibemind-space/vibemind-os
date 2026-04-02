"""Docker operations — MCP catalog, server enable/inspect, gateway, build, run, Gordon AI."""

import asyncio
import atexit
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

import yaml

from .constants import MCP_GATEWAY_PORT, OUTPUT_DIR
from .knowledge import MCP_DOMAIN_HINTS, MCP_SERVER_CONFIG_INFO


# ---------------------------------------------------------------------------
# Tier A — KNOWN_SERVER_TOOLS: static tool definitions for well-known servers
# Eliminates Docker inspect calls entirely for these servers (~0 ms).
# ---------------------------------------------------------------------------

KNOWN_SERVER_TOOLS: dict[str, list[dict]] = {
    # ── filesystem (11 tools) ──────────────────────────────────────────────
    "filesystem": [
        {"name": "read_file", "description": "Read the complete contents of a file",
         "arguments": [{"name": "path", "type": "string", "description": "Path to the file to read"}]},
        {"name": "read_multiple_files", "description": "Read multiple files simultaneously",
         "arguments": [{"name": "paths", "type": "array", "description": "List of file paths to read"}]},
        {"name": "write_file", "description": "Create or overwrite a file with new content",
         "arguments": [{"name": "path", "type": "string", "description": "Path to the file to write"},
                       {"name": "content", "type": "string", "description": "Content to write to the file"}]},
        {"name": "edit_file", "description": "Make line-based edits to a text file",
         "arguments": [{"name": "path", "type": "string", "description": "Path to the file to edit"},
                       {"name": "edits", "type": "array", "description": "List of edit operations"},
                       {"name": "dryRun", "type": "boolean", "description": "Preview changes without applying"}]},
        {"name": "create_directory", "description": "Create a new directory or ensure it exists",
         "arguments": [{"name": "path", "type": "string", "description": "Path of the directory to create"}]},
        {"name": "list_directory", "description": "List contents of a directory",
         "arguments": [{"name": "path", "type": "string", "description": "Path of the directory to list"}]},
        {"name": "directory_tree", "description": "Get a recursive tree view of a directory",
         "arguments": [{"name": "path", "type": "string", "description": "Root path for the tree"},
                       {"name": "depth", "type": "number", "description": "Maximum depth to traverse"}]},
        {"name": "move_file", "description": "Move or rename a file or directory",
         "arguments": [{"name": "source", "type": "string", "description": "Source path"},
                       {"name": "destination", "type": "string", "description": "Destination path"}]},
        {"name": "search_files", "description": "Search for files matching a pattern",
         "arguments": [{"name": "path", "type": "string", "description": "Starting directory for search"},
                       {"name": "pattern", "type": "string", "description": "Search pattern (glob)"},
                       {"name": "excludePatterns", "type": "array", "description": "Patterns to exclude"}]},
        {"name": "get_file_info", "description": "Get metadata about a file or directory",
         "arguments": [{"name": "path", "type": "string", "description": "Path to get info for"}]},
        {"name": "list_allowed_directories", "description": "List directories the server is allowed to access",
         "arguments": []},
    ],

    # ── git (12 tools) ─────────────────────────────────────────────────────
    "git": [
        {"name": "git_status", "description": "Show the working tree status",
         "arguments": [{"name": "repo_path", "type": "string", "description": "Path to the Git repository"}]},
        {"name": "git_diff_unstaged", "description": "Show changes in the working directory not yet staged",
         "arguments": [{"name": "repo_path", "type": "string", "description": "Path to the Git repository"}]},
        {"name": "git_diff_staged", "description": "Show changes staged for commit",
         "arguments": [{"name": "repo_path", "type": "string", "description": "Path to the Git repository"}]},
        {"name": "git_commit", "description": "Record changes to the repository",
         "arguments": [{"name": "repo_path", "type": "string", "description": "Path to the Git repository"},
                       {"name": "message", "type": "string", "description": "Commit message"}]},
        {"name": "git_add", "description": "Add file contents to the index",
         "arguments": [{"name": "repo_path", "type": "string", "description": "Path to the Git repository"},
                       {"name": "files", "type": "array", "description": "Files to add"}]},
        {"name": "git_reset", "description": "Unstage all staged changes",
         "arguments": [{"name": "repo_path", "type": "string", "description": "Path to the Git repository"}]},
        {"name": "git_log", "description": "Show commit logs",
         "arguments": [{"name": "repo_path", "type": "string", "description": "Path to the Git repository"},
                       {"name": "max_count", "type": "number", "description": "Maximum number of commits to show"}]},
        {"name": "git_create_branch", "description": "Create a new branch",
         "arguments": [{"name": "repo_path", "type": "string", "description": "Path to the Git repository"},
                       {"name": "branch_name", "type": "string", "description": "Name of the new branch"},
                       {"name": "base_branch", "type": "string", "description": "Base branch to create from"}]},
        {"name": "git_checkout", "description": "Switch branches",
         "arguments": [{"name": "repo_path", "type": "string", "description": "Path to the Git repository"},
                       {"name": "branch_name", "type": "string", "description": "Branch to switch to"}]},
        {"name": "git_show", "description": "Show the contents of a commit",
         "arguments": [{"name": "repo_path", "type": "string", "description": "Path to the Git repository"},
                       {"name": "revision", "type": "string", "description": "Revision to show"}]},
        {"name": "git_init", "description": "Initialize a new Git repository",
         "arguments": [{"name": "path", "type": "string", "description": "Path where to initialize the repository"}]},
        {"name": "git_clone", "description": "Clone a repository",
         "arguments": [{"name": "url", "type": "string", "description": "Repository URL to clone"},
                       {"name": "path", "type": "string", "description": "Local path to clone into"}]},
    ],

    # ── fetch (1 tool) ─────────────────────────────────────────────────────
    "fetch": [
        {"name": "fetch", "description": "Fetch a URL from the internet and extract its contents as markdown",
         "arguments": [{"name": "url", "type": "string", "description": "URL to fetch"},
                       {"name": "max_length", "type": "number", "description": "Maximum content length to return"},
                       {"name": "start_index", "type": "number", "description": "Start index for pagination"},
                       {"name": "raw", "type": "boolean", "description": "Get raw content without markdown conversion"}]},
    ],

    # ── memory (9 tools) ──────────────────────────────────────────────────
    "memory": [
        {"name": "create_entities", "description": "Create multiple new entities in the knowledge graph",
         "arguments": [{"name": "entities", "type": "array", "description": "List of entities with name, entityType, observations"}]},
        {"name": "create_relations", "description": "Create multiple new relations between entities",
         "arguments": [{"name": "relations", "type": "array", "description": "List of relations with from, to, relationType"}]},
        {"name": "add_observations", "description": "Add new observations to existing entities",
         "arguments": [{"name": "observations", "type": "array", "description": "List of {entityName, contents} to add"}]},
        {"name": "delete_entities", "description": "Delete multiple entities and their relations",
         "arguments": [{"name": "entityNames", "type": "array", "description": "Names of entities to delete"}]},
        {"name": "delete_observations", "description": "Delete specific observations from entities",
         "arguments": [{"name": "deletions", "type": "array", "description": "List of {entityName, observations} to delete"}]},
        {"name": "delete_relations", "description": "Delete multiple relations from the knowledge graph",
         "arguments": [{"name": "relations", "type": "array", "description": "List of relations to delete with from, to, relationType"}]},
        {"name": "read_graph", "description": "Read the entire knowledge graph",
         "arguments": []},
        {"name": "search_nodes", "description": "Search for nodes in the knowledge graph",
         "arguments": [{"name": "query", "type": "string", "description": "Search query"}]},
        {"name": "open_nodes", "description": "Open specific nodes by their names",
         "arguments": [{"name": "names", "type": "array", "description": "Names of nodes to open"}]},
    ],

    # ── sequentialthinking (1 tool) ────────────────────────────────────────
    "sequentialthinking": [
        {"name": "sequentialthinking", "description": "A tool for dynamic and reflective problem-solving through sequential thinking",
         "arguments": [{"name": "thought", "type": "string", "description": "The current thinking step"},
                       {"name": "nextThoughtNeeded", "type": "boolean", "description": "Whether another thought step is needed"},
                       {"name": "thoughtNumber", "type": "number", "description": "Current thought number"},
                       {"name": "totalThoughts", "type": "number", "description": "Estimated total thoughts needed"},
                       {"name": "isRevision", "type": "boolean", "description": "Whether this revises a previous thought"},
                       {"name": "revisesThought", "type": "number", "description": "Which thought number is being revised"},
                       {"name": "branchFromThought", "type": "number", "description": "Thought number to branch from"},
                       {"name": "branchId", "type": "string", "description": "Identifier for the branch"},
                       {"name": "needsMoreThoughts", "type": "boolean", "description": "Whether more thoughts are needed beyond the estimate"}]},
    ],

    # ── context7 (2 tools) ─────────────────────────────────────────────────
    "context7": [
        {"name": "resolve-library-id", "description": "Resolve a library name to a Context7 library ID",
         "arguments": [{"name": "libraryName", "type": "string", "description": "Library name to look up"}]},
        {"name": "get-library-docs", "description": "Get documentation for a library using its Context7 library ID",
         "arguments": [{"name": "context7CompatibleLibraryID", "type": "string", "description": "Context7 library ID"},
                       {"name": "topic", "type": "string", "description": "Topic to focus on"},
                       {"name": "tokens", "type": "number", "description": "Maximum tokens of documentation to return"}]},
    ],

    # ── sqlite (6 tools) ───────────────────────────────────────────────────
    "sqlite": [
        {"name": "read_query", "description": "Execute a SELECT query on the SQLite database",
         "arguments": [{"name": "query", "type": "string", "description": "SQL SELECT query to execute"}]},
        {"name": "write_query", "description": "Execute an INSERT, UPDATE, or DELETE query",
         "arguments": [{"name": "query", "type": "string", "description": "SQL write query to execute"}]},
        {"name": "create_table", "description": "Create a new table in the database",
         "arguments": [{"name": "query", "type": "string", "description": "CREATE TABLE SQL statement"}]},
        {"name": "list_tables", "description": "List all tables in the database",
         "arguments": []},
        {"name": "describe_table", "description": "Get the schema of a specific table",
         "arguments": [{"name": "table_name", "type": "string", "description": "Name of the table to describe"}]},
        {"name": "append_insight", "description": "Add a business insight to the memo",
         "arguments": [{"name": "insight", "type": "string", "description": "Business insight to record"}]},
    ],

    # ── playwright (18 tools) ──────────────────────────────────────────────
    "playwright": [
        {"name": "browser_navigate", "description": "Navigate to a URL in the browser",
         "arguments": [{"name": "url", "type": "string", "description": "URL to navigate to"}]},
        {"name": "browser_screenshot", "description": "Take a screenshot of the current page",
         "arguments": []},
        {"name": "browser_click", "description": "Click an element on the page",
         "arguments": [{"name": "element", "type": "string", "description": "Human-readable element description"},
                       {"name": "ref", "type": "string", "description": "Exact target element reference from page snapshot"}]},
        {"name": "browser_fill", "description": "Fill out an input field",
         "arguments": [{"name": "ref", "type": "string", "description": "Exact target element reference from page snapshot"},
                       {"name": "value", "type": "string", "description": "Value to fill in"}]},
        {"name": "browser_select", "description": "Select an option in a dropdown",
         "arguments": [{"name": "ref", "type": "string", "description": "Exact target element reference from page snapshot"},
                       {"name": "value", "type": "string", "description": "Value to select"}]},
        {"name": "browser_hover", "description": "Hover over an element on the page",
         "arguments": [{"name": "element", "type": "string", "description": "Human-readable element description"},
                       {"name": "ref", "type": "string", "description": "Exact target element reference from page snapshot"}]},
        {"name": "browser_type", "description": "Type text with keyboard key-by-key",
         "arguments": [{"name": "text", "type": "string", "description": "Text to type"},
                       {"name": "submit", "type": "boolean", "description": "Whether to press Enter after typing"}]},
        {"name": "browser_press_key", "description": "Press a keyboard key or key combination",
         "arguments": [{"name": "key", "type": "string", "description": "Key to press (e.g. Enter, Escape, ArrowDown)"}]},
        {"name": "browser_snapshot", "description": "Capture an accessibility snapshot of the current page",
         "arguments": []},
        {"name": "browser_tabs", "description": "List current browser tabs",
         "arguments": []},
        {"name": "browser_tab_new", "description": "Open a new browser tab",
         "arguments": [{"name": "url", "type": "string", "description": "URL to open in the new tab"}]},
        {"name": "browser_tab_select", "description": "Select a browser tab by index",
         "arguments": [{"name": "index", "type": "number", "description": "Tab index to select"}]},
        {"name": "browser_tab_close", "description": "Close a browser tab",
         "arguments": [{"name": "index", "type": "number", "description": "Tab index to close"}]},
        {"name": "browser_file_upload", "description": "Upload a file to a file input element",
         "arguments": [{"name": "paths", "type": "array", "description": "Paths to files to upload"},
                       {"name": "ref", "type": "string", "description": "Exact target element reference from page snapshot"}]},
        {"name": "browser_console_messages", "description": "Get browser console messages",
         "arguments": []},
        {"name": "browser_evaluate", "description": "Execute JavaScript in the browser console",
         "arguments": [{"name": "expression", "type": "string", "description": "JavaScript expression to evaluate"}]},
        {"name": "browser_network_requests", "description": "Get browser network requests",
         "arguments": []},
        {"name": "browser_wait", "description": "Wait for a specified time",
         "arguments": [{"name": "time", "type": "number", "description": "Time to wait in milliseconds"}]},
    ],

    # ── docker (6 tools) ───────────────────────────────────────────────────
    "docker": [
        {"name": "list_containers", "description": "List Docker containers",
         "arguments": [{"name": "all", "type": "boolean", "description": "Show all containers including stopped"}]},
        {"name": "list_images", "description": "List Docker images",
         "arguments": []},
        {"name": "run_container", "description": "Run a Docker container",
         "arguments": [{"name": "image", "type": "string", "description": "Docker image to run"},
                       {"name": "command", "type": "string", "description": "Command to execute in the container"},
                       {"name": "ports", "type": "object", "description": "Port mappings"},
                       {"name": "volumes", "type": "object", "description": "Volume mounts"},
                       {"name": "environment", "type": "object", "description": "Environment variables"}]},
        {"name": "stop_container", "description": "Stop a running Docker container",
         "arguments": [{"name": "container_id", "type": "string", "description": "Container ID or name to stop"}]},
        {"name": "get_container_logs", "description": "Get logs from a Docker container",
         "arguments": [{"name": "container_id", "type": "string", "description": "Container ID or name"},
                       {"name": "tail", "type": "number", "description": "Number of log lines to return"}]},
        {"name": "compose_up", "description": "Start services with Docker Compose",
         "arguments": [{"name": "project_dir", "type": "string", "description": "Path to the docker-compose directory"},
                       {"name": "detach", "type": "boolean", "description": "Run in detached mode"}]},
    ],
}


async def get_mcp_catalog() -> dict:
    """Query Docker MCP catalog via 'docker mcp catalog show', parse text output."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "mcp", "catalog", "show", "docker-mcp",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            print(f"  [!] docker mcp catalog show failed: {stderr.decode()[:200]}")
            return {"registry": {}}
        text = stdout.decode(errors="replace")
        # Strip ANSI escape codes
        text = re.sub(r'\x1b\[[0-9;]*m', '', text)
        # Strip Unicode box-drawing characters
        text = re.sub(r'[─━│┃┌┐└┘├┤┬┴┼╋═║╔╗╚╝╠╣╦╩╬]+', '', text)
        # Parse: "  ServerName" (2-space indent) followed by "    Description..." (4-space indent)
        registry = {}
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            raw = lines[i]
            stripped = raw.strip()
            # Skip empty, header, separator lines
            if not stripped or "MCP Server Directory" in stripped or "servers available" in stripped:
                i += 1
                continue
            # A server name: line starts with exactly 2 spaces + non-space (after ANSI strip)
            # OR is a non-empty line that isn't deeply indented
            if raw.startswith("  ") and not raw.startswith("    ") and stripped:
                name = stripped
                desc_lines = []
                i += 1
                while i < len(lines):
                    next_raw = lines[i]
                    next_stripped = next_raw.strip()
                    # Description lines: 4+ spaces indent
                    if next_raw.startswith("    ") and next_stripped:
                        desc_lines.append(next_stripped)
                        i += 1
                    elif not next_stripped:
                        i += 1
                        break
                    else:
                        break
                if desc_lines:
                    registry[name] = {"description": " ".join(desc_lines)}
                continue
            i += 1
        return {"registry": registry}
    except Exception as e:
        print(f"  [!] MCP catalog error: {e}")
        return {"registry": {}}


def format_catalog_for_llm(catalog: dict, max_servers: int = 350) -> str:
    """Format MCP catalog into LLM-readable summary with key-status annotations."""
    registry = catalog.get("registry", {})
    if not registry:
        return "(No MCP servers found in catalog)"
    lines = [f"Total: {len(registry)} MCP servers\n"]
    for i, (name, info) in enumerate(registry.items()):
        if i >= max_servers:
            lines.append(f"\n... and {len(registry) - max_servers} more servers")
            break
        desc = info.get("description", "No description")[:150]
        # Key status annotation
        secrets = [s.get("name", "") for s in info.get("secrets", [])]
        key_tag = " [NEEDS API KEY]" if secrets else ""
        # Include tools if available
        extras = ""
        tools = [t.get("name", "?") for t in info.get("tools", [])]
        if tools:
            tools_str = ", ".join(tools[:5])
            if len(tools) > 5:
                tools_str += f" (+{len(tools)-5} more)"
            extras += f"\n  Tools: {tools_str}"
        if secrets:
            extras += f" [needs: {', '.join(secrets)}]"
        lines.append(f"- **{name}**{key_tag}: {desc}{extras}")
    return "\n".join(lines)


def classify_task_domain(task_description: str) -> dict:
    """Classify a task description into MCP domain categories.
    Returns matched domains and recommended servers split by key requirements."""
    task_lower = task_description.lower()
    matched_domains = []

    for domain, info in MCP_DOMAIN_HINTS.items():
        score = sum(1 for kw in info["keywords"] if kw in task_lower)
        if score > 0:
            matched_domains.append((domain, score, info))

    matched_domains.sort(key=lambda x: x[1], reverse=True)

    seen_free = set()
    seen_keyed = set()
    recommended_free = []
    recommended_keyed = []
    for _domain, _score, info in matched_domains:
        for s in info["key_free"]:
            if s not in seen_free:
                recommended_free.append(s)
                seen_free.add(s)
        for s in info["needs_key"]:
            if s not in seen_keyed:
                recommended_keyed.append(s)
                seen_keyed.add(s)

    return {
        "domains": [d[0] for d in matched_domains],
        "recommended_key_free": recommended_free[:8],
        "recommended_needs_key": recommended_keyed[:5],
    }




# --- Docker Eval Helpers ---

_LOCAL_BASE_CACHE: str | None = None

def _check_local_base_image() -> str | None:
    """Return local base image name if available, else None."""
    global _LOCAL_BASE_CACHE
    if _LOCAL_BASE_CACHE is not None:
        return _LOCAL_BASE_CACHE or None
    import subprocess
    for candidate in ["python-node-claude:local", "python:3.11-slim"]:
        try:
            r = subprocess.run(
                ["docker", "image", "inspect", candidate],
                capture_output=True, timeout=5)
            if r.returncode == 0:
                _LOCAL_BASE_CACHE = candidate
                return candidate
        except Exception:
            pass
    _LOCAL_BASE_CACHE = ""
    return None


def prepare_docker_context(output_path: Path) -> Path:
    """Create a build directory from nested output structure."""
    build_dir = Path(tempfile.mkdtemp(prefix="autogen_eval_"))

    # Copy src/ directory preserving structure (Dockerfiles reference COPY src/ .)
    src_dir = output_path / "src"
    if src_dir.exists():
        dest_src = build_dir / "src"
        dest_src.mkdir(exist_ok=True)
        for f in src_dir.glob("*.py"):
            shutil.copy2(f, dest_src / f.name)

    # Copy project.yml and agents/ at build root (Dockerfile COPY project.yml . + COPY agents/ agents/)
    project_yml = output_path / "project.yml"
    if project_yml.exists():
        shutil.copy2(project_yml, build_dir / "project.yml")
    agents_dir = output_path / "agents"
    if agents_dir.exists():
        shutil.copytree(agents_dir, build_dir / "agents", dirs_exist_ok=True)

    # Copy docker/Dockerfile* to build dir root
    docker_dir = output_path / "docker"
    if docker_dir.exists():
        for f in docker_dir.iterdir():
            if f.name.startswith("Dockerfile"):
                shutil.copy2(f, build_dir / f.name)
        # Read and clean docker-compose.yml
        compose_file = docker_dir / "docker-compose.yml"
        if compose_file.exists():
            try:
                compose = yaml.safe_load(compose_file.read_text())
                if isinstance(compose, dict) and "services" in compose:
                    clean_services = {}
                    for svc_name, svc_config in compose["services"].items():
                        if isinstance(svc_config, dict):
                            # Fix build: always context=. dockerfile=Dockerfile
                            svc_config["build"] = {"context": ".", "dockerfile": "Dockerfile"}
                            # Fix env_file path
                            svc_config["env_file"] = [".env"]
                            # Remove ALL port mappings — AutoGen agents don't need exposed ports
                            # and LLM-generated port bindings often conflict with existing services
                            svc_config.pop("ports", None)
                            # Remove container_name (prevents parallel runs)
                            svc_config.pop("container_name", None)
                            # Remove healthcheck (often references wrong endpoints)
                            svc_config.pop("healthcheck", None)
                            clean_services[svc_name] = svc_config
                    if clean_services:
                        compose["services"] = clean_services
                    # Inject MCP Gateway access into every service
                    # Prefer container-to-container via vibemind network over host.docker.internal
                    import subprocess as _sp2
                    _vibe_ok = False
                    try:
                        _r = _sp2.run(["docker", "network", "inspect", _VIBEMIND_NETWORK],
                                      capture_output=True, timeout=5)
                        _vibe_ok = (_r.returncode == 0)
                    except Exception:
                        pass
                    if _vibe_ok:
                        gateway_url = f"http://mcp-gateway:{MCP_GATEWAY_PORT}"
                    else:
                        gateway_url = f"http://host.docker.internal:{MCP_GATEWAY_PORT}"
                    gateway_env = f"MCP_GATEWAY_URL={gateway_url}"
                    gateway_auth = f"MCP_GATEWAY_AUTH_TOKEN={_gateway_auth_token}" if _gateway_auth_token else None
                    for svc_name, svc_config in compose.get("services", {}).items():
                        if isinstance(svc_config, dict):
                            env = svc_config.setdefault("environment", [])
                            if isinstance(env, list):
                                if not any("MCP_GATEWAY_URL" in str(e) for e in env):
                                    env.append(gateway_env)
                                if gateway_auth and not any("MCP_GATEWAY_AUTH_TOKEN" in str(e) for e in env):
                                    env.append(gateway_auth)
                            elif isinstance(env, dict):
                                if "MCP_GATEWAY_URL" not in env:
                                    env["MCP_GATEWAY_URL"] = gateway_url
                                if gateway_auth and "MCP_GATEWAY_AUTH_TOKEN" not in env:
                                    env["MCP_GATEWAY_AUTH_TOKEN"] = _gateway_auth_token
                            if _vibe_ok:
                                nets = svc_config.setdefault("networks", [])
                                if _VIBEMIND_NETWORK not in nets:
                                    nets.append(_VIBEMIND_NETWORK)
                            else:
                                hosts = svc_config.setdefault("extra_hosts", [])
                                if "host.docker.internal:host-gateway" not in hosts:
                                    hosts.append("host.docker.internal:host-gateway")
                            # Also ensure env_file is set for OPENAI_API_KEY
                            if "env_file" not in svc_config:
                                svc_config["env_file"] = [".env"]
                            # Mount output dir so agent results persist after container exit
                            vols = svc_config.setdefault("volumes", [])
                            if not any("./output:/app/output" in str(v) for v in vols):
                                vols.append("./output:/app/output")
                            # Mount Claude CLI config from host (Claude Max auth)
                            claude_home = os.path.expanduser("~/.claude")
                            claude_json = os.path.expanduser("~/.claude.json")
                            if os.path.exists(claude_home):
                                # rw: Claude CLI needs to write debug/todo/session files
                                claude_mount = f"{claude_home}:/root/.claude"
                                if not any(".claude:/root/.claude" in str(v) for v in vols):
                                    vols.append(claude_mount)
                                # Also mount .claude.json (main config file, lives outside .claude/)
                                if os.path.exists(claude_json):
                                    json_mount = f"{claude_json}:/root/.claude.json"
                                    if not any(".claude.json:/root/.claude.json" in str(v) for v in vols):
                                        vols.append(json_mount)
                    # Add vibemind network definition if used
                    if _vibe_ok and compose.get("services"):
                        compose.setdefault("networks", {})[_VIBEMIND_NETWORK] = {"external": True}
                    # Remove obsolete 'version' key (Docker Compose v2 ignores it with warning)
                    compose.pop("version", None)
                    (build_dir / "docker-compose.yml").write_text(
                        yaml.dump(compose, default_flow_style=False))
            except yaml.YAMLError:
                # Copy as-is if YAML parsing fails
                shutil.copy2(compose_file, build_dir / "docker-compose.yml")

    # If no docker-compose.yml was created, generate a minimal one
    if not (build_dir / "docker-compose.yml").exists():
        dockerfile = "Dockerfile"
        if (build_dir / "Dockerfile.host").exists():
            dockerfile = "Dockerfile.host"
        claude_home = os.path.expanduser("~/.claude")
        import subprocess as _sp3
        _vibe_fallback = False
        try:
            _r2 = _sp3.run(["docker", "network", "inspect", _VIBEMIND_NETWORK],
                           capture_output=True, timeout=5)
            _vibe_fallback = (_r2.returncode == 0)
        except Exception:
            pass
        _gw_url = f"http://mcp-gateway:{MCP_GATEWAY_PORT}" if _vibe_fallback else f"http://host.docker.internal:{MCP_GATEWAY_PORT}"
        app_svc: dict = {
            "build": {"context": ".", "dockerfile": dockerfile},
            "env_file": [".env"],
            "environment": [
                f"MCP_GATEWAY_URL={_gw_url}",
            ] + ([f"MCP_GATEWAY_AUTH_TOKEN={_gateway_auth_token}"] if _gateway_auth_token else []),
            "dns": ["8.8.8.8", "8.8.4.4"],
        }
        if _vibe_fallback:
            app_svc["networks"] = [_VIBEMIND_NETWORK]
        else:
            app_svc["extra_hosts"] = ["host.docker.internal:host-gateway"]
        compose_content: dict = {"services": {"app": app_svc}}
        if _vibe_fallback:
            compose_content["networks"] = {_VIBEMIND_NETWORK: {"external": True}}
        # Mount output dir so agent results persist after container exit
        # Mount Claude CLI config from host (Claude Max auth)
        claude_json = os.path.expanduser("~/.claude.json")
        vols = ["./output:/app/output"]
        if os.path.exists(claude_home):
            vols.append(f"{claude_home}:/root/.claude:ro")
        if os.path.exists(claude_json):
            vols.append(f"{claude_json}:/root/.claude.json:ro")
        compose_content["services"]["app"]["volumes"] = vols
        (build_dir / "docker-compose.yml").write_text(
            yaml.dump(compose_content, default_flow_style=False))

    # Ensure DNS is set in docker-compose.yml (Docker Desktop DNS can break)
    compose_path = build_dir / "docker-compose.yml"
    if compose_path.exists():
        try:
            compose_data = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
            for svc_name, svc_conf in compose_data.get("services", {}).items():
                if "dns" not in svc_conf:
                    svc_conf["dns"] = ["8.8.8.8", "8.8.4.4"]
            compose_path.write_text(yaml.dump(compose_data, default_flow_style=False))
        except Exception:
            pass

    # Create output directory for volume mount (agents write to /app/output/)
    (build_dir / "output").mkdir(exist_ok=True)

    # Normalize Dockerfile to a reliable, standardized layout:
    # build_dir/ has: requirements.txt, src/main.py, src/tools.py, Dockerfile, .env
    #
    # Target Dockerfile:
    #   FROM python:3.11-slim
    #   WORKDIR /app
    #   COPY requirements.txt .
    #   RUN pip install --no-cache-dir -r requirements.txt
    #   COPY src/ .
    #   CMD ["python", "main.py"]
    #
    # This is idempotent — always produces a working Dockerfile regardless of LLM output.
    has_src = (build_dir / "src").exists()

    # Find entry point: look for main.py in src/ (most common)
    entry_point = "main.py"
    if has_src:
        if (build_dir / "src" / "main.py").exists():
            entry_point = "main.py"
        elif (build_dir / "src" / "app.py").exists():
            entry_point = "app.py"
        elif (build_dir / "src" / "host.py").exists():
            entry_point = "host.py"

    # Always generate a clean, standardized Dockerfile
    # This avoids all LLM-generated Dockerfile issues (wrong COPY paths, wrong CMD, etc.)
    # Uses local base image (python-node-claude:local) if available, falls back to python:3.11-slim
    # Check for agents/ and project.yml in build dir (copied by prepare_docker_context)
    has_agents = (build_dir / "agents").exists()
    has_project_yml = (build_dir / "project.yml").exists()
    extra_copies = ""
    if has_project_yml:
        extra_copies += "COPY project.yml .\n"
    if has_agents:
        extra_copies += "COPY agents/ agents/\n"

    _local_base = _check_local_base_image()
    if _local_base and _local_base.startswith("python-node-claude"):
        # Local base already has python + node + claude CLI + pip packages — skip installs
        standard_dockerfile = (
            f"FROM {_local_base}\n"
            "WORKDIR /app\n"
            f"COPY {'src/ .' if has_src else '. .'}\n"
            f"{extra_copies}"
            f'CMD ["python", "{entry_point}"]\n'
        )
        print(f"  [Docker] Using local base image: {_local_base} (skipping pip install)")
    else:
        # Includes Node.js + Claude CLI so agents can use claude_code tool
        standard_dockerfile = (
            "FROM python:3.11-slim\n"
            "WORKDIR /app\n"
            "# Install Node.js 20 + Claude Code CLI for claude_code tool\n"
            "RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \\\n"
            "    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \\\n"
            "    apt-get install -y --no-install-recommends nodejs && \\\n"
            "    npm install -g @anthropic-ai/claude-code && \\\n"
            "    apt-get clean && rm -rf /var/lib/apt/lists/*\n"
            "COPY requirements.txt .\n"
            "RUN pip install --no-cache-dir -r requirements.txt\n"
            f"COPY {'src/ .' if has_src else '. .'}\n"
            f"{extra_copies}"
            f'CMD ["python", "{entry_point}"]\n'
        )
    (build_dir / "Dockerfile").write_text(standard_dockerfile)
    print(f"  [Docker] Standardized Dockerfile: COPY {'src/' if has_src else '.'} -> CMD python {entry_point}")

    # Copy requirements.txt
    req = output_path / "requirements.txt"
    if req.exists():
        shutil.copy2(req, build_dir / "requirements.txt")
    elif not (build_dir / "requirements.txt").exists():
        (build_dir / "requirements.txt").write_text(
            "autogen-agentchat>=0.4\nautogen-ext[openai]>=0.4\n"
            "autogen-core>=0.4\nopenai>=1.0\nhttpx>=0.27\ntiktoken\npyyaml>=6.0\n"
        )

    # Ensure httpx, tiktoken, pyyaml are always in requirements.txt (commonly missed)
    req_final = build_dir / "requirements.txt"
    if req_final.exists():
        current_reqs = req_final.read_text().lower()
        missing = []
        if "httpx" not in current_reqs:
            missing.append("httpx>=0.27")
        if "tiktoken" not in current_reqs:
            missing.append("tiktoken")
        if "pyyaml" not in current_reqs and "yaml" not in current_reqs:
            missing.append("pyyaml>=6.0")
        if "autogen-ext" in current_reqs and "[openai]" not in current_reqs and "[grpc]" not in current_reqs:
            missing.append("autogen-ext[openai]>=0.4")
        if missing:
            with open(req_final, "a") as f:
                for pkg in missing:
                    f.write(f"\n{pkg}")
            print(f"  [Docker] Auto-added missing deps: {missing}")

    # Create .env with OPENAI_API_KEY + base URL + model + ANTHROPIC_API_KEY
    env_lines = []
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        env_lines.append(f"OPENAI_API_KEY={api_key}")
    else:
        print("  [!] WARNING: OPENAI_API_KEY not set — Docker run will fail without it")
        env_lines.append("# OPENAI_API_KEY not set")
    # Pass through OpenRouter / custom base URL
    base_url = os.environ.get("OPENAI_BASE_URL", "")
    if base_url:
        env_lines.append(f"OPENAI_BASE_URL={base_url}")
    # Pass through model override
    model_env = os.environ.get("OPENAI_MODEL", "")
    if model_env:
        env_lines.append(f"OPENAI_MODEL={model_env}")
    # Anthropic API key fallback
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        env_lines.append(f"ANTHROPIC_API_KEY={anthropic_key}")
    # Supabase local (credential storage for self-implementing tools)
    _default_anon_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0"
    env_lines.append(f"SUPABASE_URL={os.environ.get('SUPABASE_URL', 'http://host.docker.internal:54321')}")
    env_lines.append(f"SUPABASE_ANON_KEY={os.environ.get('SUPABASE_ANON_KEY', _default_anon_key)}")
    env_lines.append(f"MINIBOOK_URL={os.environ.get('MINIBOOK_URL', 'http://host.docker.internal:8899')}")
    # Inject stored credentials from Supabase
    try:
        import httpx
        _supa_url = os.environ.get("SUPABASE_URL", "http://localhost:54321")
        _supa_key = os.environ.get("SUPABASE_ANON_KEY", _default_anon_key)
        resp = httpx.get(
            f"{_supa_url}/rest/v1/credentials?select=key_name,key_value",
            headers={"apikey": _supa_key, "Authorization": f"Bearer {_supa_key}"},
            timeout=5)
        if resp.status_code == 200:
            for cred in resp.json():
                env_lines.append(f"{cred['key_name']}={cred['key_value']}")
            if resp.json():
                print(f"  [Docker] Injected {len(resp.json())} credentials from Supabase")
    except Exception:
        pass  # Supabase not available, skip
    (build_dir / ".env").write_text("\n".join(env_lines) + "\n")

    return build_dir


async def docker_build_test(build_dir: Path) -> dict:
    """Run docker compose build. Returns result dict."""
    start = time.time()

    # Pre-flight: check Docker Engine is responding
    try:
        ping = await asyncio.create_subprocess_exec(
            "docker", "info", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            _, ping_err = await asyncio.wait_for(ping.communicate(), timeout=10)
        except asyncio.TimeoutError:
            ping.kill()  # Prevent zombie docker.exe
            msg = "Docker Engine check timed out (10s)"
            print(f"  [Build] {msg}")
            return {"status": "FAIL", "output": msg, "duration": time.time() - start,
                    "docker_down": True}
        if ping.returncode != 0:
            msg = f"Docker Engine not available: {ping_err.decode()[:200]}"
            print(f"  [Build] {msg}")
            return {"status": "FAIL", "output": msg, "duration": time.time() - start,
                    "docker_down": True}
    except Exception as e:
        msg = f"Docker Engine check failed: {e}"
        print(f"  [Build] {msg}")
        return {"status": "FAIL", "output": msg, "duration": time.time() - start,
                "docker_down": True}

    # Debug: list build dir contents
    files = list(build_dir.iterdir()) if build_dir.exists() else []
    print(f"  [Build] Dir: {build_dir}")
    print(f"  [Build] Files: {[f.name for f in files]}")
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "build",
            cwd=str(build_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
            output = stdout.decode()[-3000:]  # Last 3000 chars
        except asyncio.TimeoutError:
            proc.kill()
            output = "TIMEOUT after 180s"
            # Clean up partial build containers
            try:
                cleanup = await asyncio.create_subprocess_exec(
                    "docker", "compose", "down", "-v", "--remove-orphans",
                    cwd=str(build_dir),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await asyncio.wait_for(cleanup.communicate(), timeout=15)
            except Exception:
                pass
            return {"status": "FAIL", "output": output, "duration": time.time() - start}

        status = "PASS" if proc.returncode == 0 else "FAIL"
        if status == "FAIL":
            print(f"  [Build] FAIL (rc={proc.returncode}): {output[-500:]}")
            # Clean up failed build containers
            try:
                cleanup = await asyncio.create_subprocess_exec(
                    "docker", "compose", "down", "-v", "--remove-orphans",
                    cwd=str(build_dir),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await asyncio.wait_for(cleanup.communicate(), timeout=15)
            except Exception:
                pass
        return {"status": status, "output": output, "duration": time.time() - start}
    except Exception as e:
        print(f"  [Build] Exception: {e}")
        return {"status": "FAIL", "output": str(e), "duration": time.time() - start}


async def docker_run_test(build_dir: Path, timeout: int = 300) -> dict:
    """Run docker compose up, capture logs. Returns result dict."""
    start = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "up", "--abort-on-container-exit",
            cwd=str(build_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            logs = stdout.decode()[-5000:]
        except asyncio.TimeoutError:
            proc.kill()
            logs = "TIMEOUT after " + str(timeout) + "s"

        # docker compose --abort-on-container-exit may return non-zero even when
        # containers exit code 0. Check logs for actual success indicators.
        status = "PASS" if proc.returncode == 0 else "FAIL"
        if status == "FAIL" and logs:
            # Check if container actually exited with code 0
            if "exited with code 0" in logs:
                status = "PASS"
            # Check for successful termination (MaxMessageTermination etc)
            if "stop_reason=" in logs or "Maximum number of messages" in logs:
                status = "PASS"
            # Check for clean AutoGen team completion
            if "TaskResult(" in logs or "StopMessage(" in logs:
                status = "PASS"
        return {"status": status, "logs": logs, "duration": time.time() - start}
    except Exception as e:
        return {"status": "FAIL", "logs": str(e), "duration": time.time() - start}
    finally:
        # Cleanup containers
        try:
            cleanup = await asyncio.create_subprocess_exec(
                "docker", "compose", "down", "-v", "--remove-orphans",
                cwd=str(build_dir),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(cleanup.communicate(), timeout=15)
        except Exception:
            pass


async def docker_run_test_with_args(build_dir: Path, args: list, timeout: int = 300) -> dict:
    """Run docker compose run with custom args (for eval tasks).
    Example: docker_run_test_with_args(build_dir, ["python", "main.py", "Write a calculator"])
    """
    start = time.time()
    try:
        cmd = ["docker", "compose", "run", "--rm", "app"] + args
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(build_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            logs = stdout.decode()[-5000:]
        except asyncio.TimeoutError:
            proc.kill()
            logs = f"TIMEOUT after {timeout}s"

        status = "PASS" if proc.returncode == 0 else "FAIL"
        if status == "FAIL" and logs:
            if "exited with code 0" in logs or "TaskResult(" in logs:
                status = "PASS"
            if "stop_reason=" in logs or "Maximum number of messages" in logs:
                status = "PASS"
        return {"status": status, "logs": logs, "duration": time.time() - start}
    except Exception as e:
        return {"status": "FAIL", "logs": str(e), "duration": time.time() - start}
    finally:
        try:
            cleanup = await asyncio.create_subprocess_exec(
                "docker", "compose", "down", "-v", "--remove-orphans",
                cwd=str(build_dir),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(cleanup.communicate(), timeout=15)
        except Exception:
            pass


async def configure_mcp_server(name: str, config: dict) -> bool:
    """Set config for an MCP server via docker mcp config write.

    Reads current config, merges in new values, writes back.
    Example: configure_mcp_server("filesystem", {"allowed_directories": ["/app/output"]})
    """
    try:
        # Read existing config
        proc = await asyncio.create_subprocess_exec(
            "docker", "mcp", "config", "read",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        existing = {}
        if proc.returncode == 0 and stdout.strip():
            try:
                existing = json.loads(stdout.decode())
            except json.JSONDecodeError:
                pass

        # Merge new config under server name
        if name not in existing:
            existing[name] = {}
        existing[name].update(config)

        # Write merged config
        config_json = json.dumps(existing)
        proc = await asyncio.create_subprocess_exec(
            "docker", "mcp", "config", "write", config_json,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0:
            print(f"  [MCP Config] {name}: config set OK")
            return True
        print(f"  [MCP Config] {name}: write failed — {stderr.decode()[:200]}")
        return False
    except Exception as e:
        print(f"  [MCP Config] {name}: error — {e}")
        return False


async def set_mcp_secret(name: str, key: str, value: str) -> bool:
    """Set a secret for an MCP server via docker mcp secret set.

    Example: set_mcp_secret("github", "personal_access_token", "ghp_xxxx")
    """
    try:
        secret_arg = f"{name}.{key}={value}"
        proc = await asyncio.create_subprocess_exec(
            "docker", "mcp", "secret", "set", secret_arg,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0:
            print(f"  [MCP Secret] {name}.{key}: set OK")
            return True
        print(f"  [MCP Secret] {name}.{key}: failed — {stderr.decode()[:200]}")
        return False
    except Exception as e:
        print(f"  [MCP Secret] {name}.{key}: error — {e}")
        return False


async def check_mcp_secret_exists(name: str, key: str) -> bool:
    """Check if a secret is already stored via docker mcp secret ls.

    Parses output format: "server.key  ****"
    Returns True if the secret is already set (user doesn't need to re-enter it).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "mcp", "secret", "ls",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode != 0:
            return False
        text = stdout.decode(errors="replace")
        # Look for "name.key" in any line (format: "server.key   ****")
        target = f"{name}.{key}".lower()
        for line in text.splitlines():
            if target in line.lower():
                return True
        return False
    except Exception:
        return False


async def inspect_mcp_server_fields(name: str) -> dict:
    """Dynamically discover required fields for an unknown MCP server.

    Calls 'docker mcp server inspect <name>' to find required config/secret fields.
    Returns {"fields": {"field_name": {"type": "string|secret", "description": "..."}}}
    so unknown servers can still get a user-input modal.
    """
    fields = {}
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "mcp", "server", "inspect", name,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode != 0:
            return {}
        text = stdout.decode(errors="replace")
        # Parse lines like: "  KEY_NAME (required): Description"
        # or: "  - key_name: <description>"
        for line in text.splitlines():
            stripped = line.strip()
            # Pattern: "FIELD_NAME (required)" or "field_name: description"
            import re as _re
            m = _re.match(r'[\-\*]?\s*(\w+)\s*(?:\(required\))?\s*:?\s*(.*)', stripped)
            if m and stripped and not stripped.startswith('#'):
                field_name = m.group(1).lower()
                description = m.group(2).strip() or field_name
                if field_name in ("name", "version", "description", "author", "type"):
                    continue  # Skip metadata fields
                is_secret = any(w in field_name.lower() for w in
                                ("token", "key", "secret", "password", "credential", "api"))
                fields[field_name] = {
                    "type": "secret" if is_secret else "string",
                    "description": description,
                }
    except Exception:
        pass
    return {"fields": fields} if fields else {}


async def get_installed_mcp_servers() -> list[dict]:
    """Get locally installed/enabled MCP servers via 'docker mcp server ls'.

    Returns list of dicts:
      [{"name": "filesystem", "oauth": False, "secrets": False, "config": True,
        "ready": False, "status": "config_required"}, ...]

    'ready' means no requirements pending (can be used immediately).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "mcp", "server", "ls",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        except asyncio.TimeoutError:
            proc.kill()  # Prevent zombie docker-mcp.exe
            return []
        if proc.returncode != 0:
            return []
        ls_text = re.sub(r'\x1b\[[0-9;]*m', '', stdout.decode(errors="replace"))
    except Exception:
        return []

    lines = ls_text.splitlines()

    # Find header line: NAME  OAUTH  SECRETS  CONFIG  DESCRIPTION
    header_line = None
    header_idx = -1
    for i, line in enumerate(lines):
        upper = line.upper()
        if "NAME" in upper and "CONFIG" in upper:
            header_line = upper
            header_idx = i
            break

    if header_line is None:
        return []

    # Column positions from header
    name_col = header_line.find("NAME")
    oauth_col = header_line.find("OAUTH")
    secrets_col = header_line.find("SECRET")
    config_col = header_line.find("CONFIG")
    desc_col = header_line.find("DESCRIPTION")

    # Determine column boundaries for name extraction
    req_cols = [c for c in (oauth_col, secrets_col, config_col) if c >= 0]
    first_req_col = min(req_cols) if req_cols else len(header_line)

    servers = []
    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        # Skip empty, separator, tip, and info lines
        if not stripped:
            continue
        if stripped[0] in "-=─━":
            continue
        if stripped.lower().startswith("tip:"):
            continue
        if stripped.lower().startswith("mcp server"):
            continue

        # Extract server name (from NAME col to first requirement col)
        if name_col >= 0 and first_req_col > name_col and len(line) > name_col:
            raw_name = line[name_col:min(first_req_col, len(line))].strip()
        else:
            parts = stripped.split()
            raw_name = parts[0] if parts else ""

        if not raw_name or raw_name.upper() == "NAME" or len(raw_name) < 2:
            continue

        # Clean name: remove (Reference), (Archived), trailing dots/ellipsis
        clean_name = re.sub(r'\s*\(.*?\)\s*', '', raw_name).strip().rstrip(".")
        if not clean_name or len(clean_name) < 2:
            continue
        # Skip separator-like lines that got through
        if all(c in "-=_." for c in clean_name):
            continue

        # Parse requirements — check column regions for "required" or ▲ symbol
        def _col_has_required(col_start, col_end):
            if col_start < 0 or col_start >= len(line):
                return False
            end = min(col_end, len(line)) if col_end > 0 else len(line)
            region = line[col_start:end]
            return "required" in region.lower() or "\u25b2" in region

        has_oauth = _col_has_required(oauth_col, secrets_col) if oauth_col >= 0 else False
        has_secrets = _col_has_required(secrets_col, config_col) if secrets_col >= 0 else False
        has_config = _col_has_required(config_col, desc_col if desc_col > 0 else -1) if config_col >= 0 else False

        ready = not has_oauth and not has_secrets and not has_config

        # Determine status
        if ready:
            status = "ready"
        elif has_config and not has_secrets and not has_oauth:
            info = MCP_SERVER_CONFIG_INFO.get(clean_name, {})
            status = "auto_configurable" if info.get("auto_config") else "config_required"
        elif has_secrets:
            status = "secrets_required"
        elif has_oauth:
            status = "oauth_required"
        else:
            status = "unknown"

        servers.append({
            "name": clean_name,
            "oauth": has_oauth,
            "secrets": has_secrets,
            "config": has_config,
            "ready": ready,
            "status": status,
        })

    return servers


async def enable_mcp_servers(servers: list) -> dict:
    """Enable MCP servers with intelligent config/secret handling.

    Parses 'docker mcp server ls' output to distinguish between:
    - OAUTH required (needs OAuth flow)
    - SECRETS required (needs API key)
    - CONFIG required (needs config like allowed_directories)

    Servers with known auto_config are configured automatically.
    Returns categorized result dict."""
    enabled = []
    failed = []
    needs_config = []   # CONFIG column has "required"
    needs_secret = []   # SECRETS column has "required"
    needs_oauth = []    # OAUTH column has "required"
    auto_configured = []  # auto-config applied successfully

    for name in servers:
        try:
            # Step 1: Enable the server
            proc = await asyncio.create_subprocess_exec(
                "docker", "mcp", "server", "enable", name,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                failed.append({"name": name, "error": stderr.decode()[:200]})
                continue

            # Step 2: Parse 'docker mcp server ls' — 3 columns: OAUTH, SECRETS, CONFIG
            check = await asyncio.create_subprocess_exec(
                "docker", "mcp", "server", "ls",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            ls_out, _ = await asyncio.wait_for(check.communicate(), timeout=15)
            ls_text = re.sub(r'\x1b\[[0-9;]*m', '', ls_out.decode(errors="replace"))

            # Find this server's line and parse column positions
            requirement = _parse_server_requirements(ls_text, name)

            if not requirement["oauth"] and not requirement["secrets"] and not requirement["config"]:
                # No requirements — ready to use
                enabled.append(name)
            elif requirement["config"] and not requirement["secrets"] and not requirement["oauth"]:
                # Only CONFIG required — try auto-configure
                info = MCP_SERVER_CONFIG_INFO.get(name, {})
                if info.get("auto_config"):
                    ok = await configure_mcp_server(name, info["auto_config"])
                    if ok:
                        auto_configured.append(name)
                        enabled.append(name)
                        print(f"  [MCP] {name}: auto-configured ({list(info['auto_config'].keys())})")
                    else:
                        needs_config.append(name)
                else:
                    needs_config.append(name)
            elif requirement["secrets"]:
                needs_secret.append(name)
            elif requirement["oauth"]:
                needs_oauth.append(name)
            else:
                needs_config.append(name)

        except Exception as e:
            failed.append({"name": name, "error": str(e)})

    return {
        "enabled": enabled,
        "failed": failed,
        "needs_config": needs_config,
        "needs_secret": needs_secret,
        "needs_oauth": needs_oauth,
        "auto_configured": auto_configured,
        # backward compat: combine all skipped
        "skipped_needs_key": needs_secret + needs_oauth + needs_config,
    }


def _parse_server_requirements(ls_text: str, server_name: str) -> dict:
    """Parse 'docker mcp server ls' output to determine what a server needs.

    The output has columns: NAME, OAUTH, SECRETS, CONFIG (and possibly more).
    We look for '▲ required' or 'required' in each column for the given server.
    Returns: {"oauth": bool, "secrets": bool, "config": bool}
    """
    result = {"oauth": False, "secrets": False, "config": False}
    lines = ls_text.splitlines()

    # Find header line to determine column positions
    header_line = None
    header_idx = -1
    for i, line in enumerate(lines):
        upper = line.upper()
        if "NAME" in upper and ("OAUTH" in upper or "SECRET" in upper or "CONFIG" in upper):
            header_line = upper
            header_idx = i
            break

    if header_line is None:
        # Fallback: if no header found, use simple "required" check on server line
        for line in lines:
            if server_name in line and "required" in line.lower():
                # Can't distinguish columns — mark all as potentially needed
                result["config"] = True
                break
        return result

    # Find column positions from header
    oauth_col = header_line.find("OAUTH")
    secrets_col = header_line.find("SECRET")
    config_col = header_line.find("CONFIG")

    # Find server line
    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped:
            continue
        # Check if this line contains the server name
        # Server name is typically in the first column
        line_lower = line.lower()
        if server_name.lower() not in line_lower:
            continue

        # Check each column region for "required"
        line_upper = line.upper()
        if oauth_col >= 0:
            # Check text from oauth_col to secrets_col (or end)
            end = secrets_col if secrets_col > oauth_col else (config_col if config_col > oauth_col else len(line))
            region = line_upper[oauth_col:end] if oauth_col < len(line) else ""
            if "REQUIRED" in region:
                result["oauth"] = True

        if secrets_col >= 0:
            end = config_col if config_col > secrets_col else len(line)
            region = line_upper[secrets_col:end] if secrets_col < len(line) else ""
            if "REQUIRED" in region:
                result["secrets"] = True

        if config_col >= 0:
            region = line_upper[config_col:] if config_col < len(line) else ""
            if "REQUIRED" in region:
                result["config"] = True

        break  # Found our server line

    return result


async def _inspect_unknown_server(name: str) -> list[dict]:
    """Tier B — inspect an unknown MCP server via Docker with a 30s timeout.

    Wraps the Docker inspect call with error handling. Returns a list of
    clean tool dicts (same shape as KNOWN_SERVER_TOOLS entries).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "mcp", "server", "inspect", name,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            print(f"  [MCP] inspect {name} failed: {stderr.decode()[:200]}")
            return []
        data = json.loads(stdout.decode())
        tools = data.get("tools", [])
        clean_tools = []
        for t in tools:
            if not t.get("enabled", True):
                continue
            tool_info = {
                "name": t["name"],
                "description": t.get("description", ""),
            }
            args = t.get("arguments", [])
            if args:
                tool_info["arguments"] = [
                    {"name": a["name"], "type": a.get("type", "string"),
                     "description": a.get("desc", a.get("description", ""))}
                    for a in args
                ]
            clean_tools.append(tool_info)
        return clean_tools
    except asyncio.TimeoutError:
        print(f"  [MCP] inspect {name} timed out (30s)")
        return []
    except Exception as e:
        print(f"  [MCP] inspect {name} error: {e}")
        return []


async def get_mcp_server_tools(servers: list) -> dict:
    """3-tier MCP tool resolution:

    Tier A — KNOWN_SERVER_TOOLS cache (instant, no Docker call)
    Tier B — Docker inspect with 2s throttle (unknown servers)
    Tier C — Fallback empty list on error

    Returns: {server_name: [{"name": ..., "description": ..., "arguments": [...]}]}
    """
    result = {}
    for name in servers:
        if name in KNOWN_SERVER_TOOLS:
            result[name] = KNOWN_SERVER_TOOLS[name]
            print(f"  [MCP] {name}: {len(KNOWN_SERVER_TOOLS[name])} tools (cached)")
        else:
            print(f"  [MCP] {name}: inspecting via Docker (2s throttle)...")
            await asyncio.sleep(2)  # Tier B throttle
            tools = await _inspect_unknown_server(name)
            result[name] = tools
            print(f"  [MCP] {name}: {len(tools)} tools (inspected)")
    return result


def format_mcp_tools_for_prompt(server_tools: dict) -> str:
    """Format real MCP tool details into a prompt-friendly string for CoderAgent."""
    if not server_tools:
        return "(No MCP tools available)"
    lines = ["AVAILABLE MCP TOOLS (use these EXACT names in tools.py):\n"]
    for server, tools in server_tools.items():
        lines.append(f"Server: {server}")
        for t in tools:
            args_str = ""
            if t.get("arguments"):
                params = ", ".join(
                    f'{a["name"]}: {a["type"]}' for a in t["arguments"]
                )
                args_str = f"({params})"
            else:
                args_str = "()"
            lines.append(f"  - {t['name']}{args_str} — {t['description']}")
        lines.append("")
    lines.append("IMPORTANT: Use these EXACT tool names in _call_mcp_tool() calls.")
    lines.append("Each tool parameter becomes a function parameter with the same name and type.")
    return "\n".join(lines)


# --- MCP Gateway ---

_gateway_process = None  # Track the running gateway process
_gateway_auth_token = None  # Auth token for MCP Gateway
_VIBEMIND_NETWORK = "vibemind"


async def ensure_vibemind_network() -> bool:
    """Create the 'vibemind' Docker bridge network if it doesn't exist.

    All pipeline containers (MCP Gateway + generated agent teams) join this
    network so they can communicate container-to-container without host.docker.internal.
    Returns True if network exists or was created successfully.
    """
    try:
        # Check if already exists
        check = await asyncio.create_subprocess_exec(
            "docker", "network", "inspect", _VIBEMIND_NETWORK,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(check.communicate(), timeout=10)
        if check.returncode == 0:
            return True  # Already exists

        # Create it
        create = await asyncio.create_subprocess_exec(
            "docker", "network", "create", "--driver", "bridge", _VIBEMIND_NETWORK,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(create.communicate(), timeout=15)
        if create.returncode == 0:
            print(f"  [vibemind] Docker network '{_VIBEMIND_NETWORK}' created")
            return True
        print(f"  [vibemind] Network creation failed: {stderr.decode()[:200]}")
        return False
    except Exception as e:
        print(f"  [vibemind] Network check error: {e}")
        return False


async def start_mcp_gateway(servers: list) -> dict:
    """Start Docker MCP Gateway as SSE endpoint on MCP_GATEWAY_PORT.
    Containers can reach it via http://host.docker.internal:{MCP_GATEWAY_PORT}/sse
    Returns dict with status, port, servers, and auth_token."""
    global _gateway_process, _gateway_auth_token
    if not servers:
        return {"status": "SKIP", "reason": "no servers to expose"}

    # Kill any existing gateway
    await stop_mcp_gateway()

    # Generate auth token — gateway requires MCP_GATEWAY_AUTH_TOKEN for SSE transport
    import secrets as _secrets
    _gateway_auth_token = _secrets.token_hex(16)

    # Ensure vibemind network exists so gateway + containers can talk container-to-container
    vibemind_ok = await ensure_vibemind_network()

    cmd = [
        "docker", "mcp", "gateway", "run",
        "--port", str(MCP_GATEWAY_PORT),
        "--transport", "sse",
    ]
    if vibemind_ok:
        cmd.extend(["--network", _VIBEMIND_NETWORK])
    for s in servers:
        cmd.extend(["--servers", s])

    # Set auth token in environment for the gateway process
    env = os.environ.copy()
    env["MCP_GATEWAY_AUTH_TOKEN"] = _gateway_auth_token

    print(f"  [Gateway] Starting on port {MCP_GATEWAY_PORT} with servers: {servers}")
    try:
        _gateway_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        # Wait a moment for gateway to start, read initial output
        await asyncio.sleep(4)
        if _gateway_process.returncode is not None:
            out = await _gateway_process.stdout.read(2000)
            return {"status": "FAIL", "output": out.decode(errors="replace")}
        return {"status": "RUNNING", "port": MCP_GATEWAY_PORT, "servers": servers,
                "auth_token": _gateway_auth_token}
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}


async def stop_mcp_gateway():
    """Stop the running MCP gateway process."""
    global _gateway_process
    if _gateway_process and _gateway_process.returncode is None:
        try:
            _gateway_process.terminate()
            await asyncio.wait_for(_gateway_process.wait(), timeout=5)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                _gateway_process.kill()
            except ProcessLookupError:
                pass
        print("  [Gateway] Stopped")
    _gateway_process = None
    # Also kill any orphaned gateway on the port
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-Command",
            f"Get-NetTCPConnection -LocalPort {MCP_GATEWAY_PORT} -ErrorAction SilentlyContinue "
            f"| ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await asyncio.wait_for(proc.communicate(), timeout=5)
    except Exception:
        pass


def _gateway_atexit_cleanup():
    """Sync atexit handler — kill gateway process if still running."""
    global _gateway_process
    if _gateway_process and _gateway_process.returncode is None:
        try:
            _gateway_process.kill()
        except (ProcessLookupError, OSError):
            pass
        _gateway_process = None


# Register once at import time — safe even if gateway never starts
atexit.register(_gateway_atexit_cleanup)


# --- Gordon AI Debug ---

async def gordon_diagnose(error_logs: str, context: str = "") -> str:
    """Use Docker AI (Gordon) to diagnose build/run failures."""
    # Keep prompt short — Gordon works best with concise questions
    # Extract just the error lines
    error_lines = []
    for line in error_logs.splitlines():
        low = line.lower()
        if any(kw in low for kw in ("error", "failed", "modulenotfound", "importerror", "no module", "cannot")):
            error_lines.append(line.strip())
    error_summary = "\n".join(error_lines[-10:]) if error_lines else error_logs[-500:]
    prompt = f"Fix this Docker build/run error: {error_summary}"
    if context:
        prompt = f"{prompt}. {context}"
    # Truncate to avoid CLI argument length limits
    prompt = prompt[:500]
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "ai", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=45)
        return stdout.decode(errors="replace").strip()
    except Exception as e:
        return f"Gordon unavailable: {e}"


async def gordon_fix_and_rebuild(build_dir: Path, error_logs: str, max_retries: int = 2) -> dict:
    """Auto-fix loop: Gordon diagnoses → apply fix → rebuild.
    Returns final build result dict."""
    for attempt in range(max_retries):
        diagnosis = await gordon_diagnose(
            error_logs,
            f"Dockerfile and requirements.txt are in {build_dir}. "
            f"Files: {', '.join(os.listdir(build_dir))}"
        )
        print(f"  [Gordon] Attempt {attempt+1}: {diagnosis[:200]}")

        # Extract missing packages from Gordon's response
        fixes_applied = False

        # Pattern: "pip install <package>" or "Add <package> to requirements.txt"
        req_file = build_dir / "requirements.txt"
        missing_pkgs = set()
        for match in re.finditer(r'pip install\s+([\w\-\[\]>=<.,]+)', diagnosis):
            pkg = match.group(1).strip().rstrip('.')
            if pkg and pkg not in ("--upgrade", "-U", "-r"):
                missing_pkgs.add(pkg)
        # Also catch: "add tiktoken" / "install tiktoken"
        for match in re.finditer(r'(?:add|install)\s+[`"]?([\w\-]+)[`"]?\s+(?:to|in)\s+(?:your\s+)?requirements', diagnosis, re.IGNORECASE):
            missing_pkgs.add(match.group(1))

        if missing_pkgs and req_file.exists():
            current = req_file.read_text()
            added = []
            for pkg in missing_pkgs:
                base_name = re.split(r'[>=<\[]', pkg)[0].lower()
                if base_name not in current.lower():
                    current += f"\n{pkg}"
                    added.append(pkg)
            if added:
                req_file.write_text(current.strip() + "\n")
                print(f"  [Gordon] Added to requirements.txt: {added}")
                fixes_applied = True

        if not fixes_applied:
            print(f"  [Gordon] No auto-fixable issue found, stopping")
            break

        # Rebuild
        print(f"  [Gordon] Rebuilding after fix...")
        result = await docker_build_test(build_dir)
        if result["status"] == "PASS":
            print(f"  [Gordon] Build PASS after fix!")
            return result
        error_logs = result["output"]

    return None  # All retries exhausted


async def gordon_fix_and_rerun(build_dir: Path, error_logs: str, max_retries: int = 2) -> dict:
    """Auto-fix loop for runtime failures: Gordon diagnoses → fix → rebuild → rerun."""
    for attempt in range(max_retries):
        fixes_applied = False

        # Pre-Gordon: direct pattern matching for common runtime errors
        # Fix 1: "can't open file '/app/src/main.py'" — CMD path mismatch
        no_file_match = re.search(r"can't open file '([^']+)'", error_logs)
        if no_file_match:
            bad_path = no_file_match.group(1)
            dockerfile = build_dir / "Dockerfile"
            if dockerfile.exists():
                df_content = dockerfile.read_text()
                # Extract the filename from the bad path (e.g., /app/src/main.py → main.py)
                bad_filename = os.path.basename(bad_path)
                # Check if the file exists in src/ dir
                if (build_dir / "src" / bad_filename).exists():
                    # Fix CMD to use correct path
                    df_content = re.sub(
                        r'CMD\s+\[.*?\]',
                        f'CMD ["python", "{bad_filename}"]',
                        df_content
                    )
                    # Also fix COPY if needed
                    if "COPY . ." in df_content and (build_dir / "src").exists():
                        df_content = df_content.replace("COPY . .", "COPY src/ .")
                    dockerfile.write_text(df_content)
                    print(f"  [Gordon-Run] Fixed Dockerfile CMD: {bad_path} -> {bad_filename}")
                    fixes_applied = True

        # Fix 2: "No module named 'X'" — add to requirements.txt
        req_file = build_dir / "requirements.txt"
        missing_pkgs = set()
        for match in re.finditer(r"No module named '(\w+)'", error_logs):
            missing_pkgs.add(match.group(1))

        if not fixes_applied:
            # Fall back to Gordon AI diagnosis
            diagnosis = await gordon_diagnose(
                error_logs,
                f"The container runs but crashes. Files: {', '.join(os.listdir(build_dir))}"
            )
            print(f"  [Gordon-Run] Attempt {attempt+1}: {diagnosis[:200]}".encode('ascii', 'replace').decode('ascii'))

            for match in re.finditer(r'pip install\s+([\w\-\[\]>=<.,]+)', diagnosis):
                pkg = match.group(1).strip().rstrip('.')
                if pkg and pkg not in ("--upgrade", "-U", "-r"):
                    missing_pkgs.add(pkg)
            for match in re.finditer(r'(?:add|install)\s+[`"]?([\w\-]+)[`"]?', diagnosis, re.IGNORECASE):
                pkg = match.group(1)
                if pkg.lower() not in ("the", "your", "a", "to", "in", "it", "this"):
                    missing_pkgs.add(pkg)

        if missing_pkgs and req_file.exists():
            current = req_file.read_text()
            added = []
            for pkg in missing_pkgs:
                base_name = re.split(r'[>=<\[]', pkg)[0].lower()
                if base_name not in current.lower():
                    current += f"\n{pkg}"
                    added.append(pkg)
            if added:
                req_file.write_text(current.strip() + "\n")
                print(f"  [Gordon-Run] Added to requirements.txt: {added}")
                fixes_applied = True

        if not fixes_applied:
            print(f"  [Gordon-Run] No auto-fixable issue found, stopping")
            break

        # Rebuild + Rerun
        print(f"  [Gordon-Run] Rebuilding...")
        build_result = await docker_build_test(build_dir)
        if build_result["status"] != "PASS":
            print(f"  [Gordon-Run] Rebuild FAILED, stopping")
            break

        print(f"  [Gordon-Run] Rerunning...")
        run_result = await docker_run_test(build_dir)
        if run_result["status"] == "PASS":
            print(f"  [Gordon-Run] Run PASS after fix!")
            return {"build": build_result, "run": run_result}
        error_logs = run_result["logs"]

    return None

