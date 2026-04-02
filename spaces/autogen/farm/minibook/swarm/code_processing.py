"""Code processing — parsing, testing, output writing, cascade context loading."""

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import yaml

from .constants import CascadeContext, OUTPUT_DIR
from .knowledge import GENERIC_MAIN_PY


def parse_code_blocks(content: str) -> dict:
    """Extract ### FILE: <name> + ```python blocks from content."""
    files = {}
    # Match: ### FILE: filename\n```python\n...code...\n```
    pattern = r'### FILE:\s*([^\n]+?)\s*\n```(?:python|yaml|dockerfile|txt|plaintext|markdown|md|toml|ini|cfg|sh|bash|json)?\s*\n(.*?)```'
    for match in re.finditer(pattern, content, re.DOTALL):
        filename = match.group(1).strip()
        code = match.group(2).strip()
        if filename and code:
            files[filename] = code
    return files


def parse_yaml_blocks(content: str) -> dict:
    """Extract ### YAML: <path/file.yml> + ```yaml blocks from content."""
    files = {}
    pattern = r'### YAML:\s*(.+?)\s*\n```(?:yaml|yml)?\s*\n(.*?)```'
    for match in re.finditer(pattern, content, re.DOTALL):
        filepath = match.group(1).strip()
        yaml_content = match.group(2).strip()
        if filepath and yaml_content:
            files[filepath] = yaml_content
    return files


def find_code_post(posts: list) -> dict:
    """Find the most recent code post (type='code' or has code blocks)."""
    for post in posts:
        if post.get("type") == "code" or "### FILE:" in post.get("content", ""):
            return post
    return None


# --- Testing Logic ---

def test_generated_code(files: dict, yaml_files: dict = None) -> dict:
    """Validate generated code and YAML files. Returns test results."""
    results = {"syntax": [], "structure": [], "imports": [], "overall": "PASS"}

    if not files:
        results["overall"] = "FAIL"
        results["syntax"].append({"file": "N/A", "status": "FAIL", "error": "No files found"})
        return results

    # 0. YAML validation (if provided)
    if yaml_files:
        yaml_results = []
        yaml_agents = []  # Collect agent names from YAML for cross-reference
        for filepath, content in yaml_files.items():
            try:
                parsed = yaml.safe_load(content)
                yaml_results.append({"file": filepath, "status": "PASS"})
                # Schema check for agent.yml files
                if filepath.endswith("agent.yml") and isinstance(parsed, dict):
                    required_fields = ["name", "role", "model", "system_message"]
                    missing = [f for f in required_fields if f not in parsed]
                    if missing:
                        yaml_results.append({
                            "file": filepath, "status": "WARN",
                            "error": f"Missing fields: {', '.join(missing)}"
                        })
                    if "name" in parsed:
                        yaml_agents.append(parsed["name"])
            except yaml.YAMLError as e:
                yaml_results.append({"file": filepath, "status": "FAIL", "error": str(e)})
                results["overall"] = "FAIL"
        results["yaml"] = yaml_results

        # Cross-reference: YAML tool names vs tools.py functions
        tools_code = None
        for fname, code in files.items():
            if fname.endswith("tools.py"):
                tools_code = code
                break
        if tools_code:
            # Extract async function names from tools.py
            py_tool_names = set(re.findall(r'async\s+def\s+(\w+)\s*\(', tools_code))
            xref = []
            for filepath, content in yaml_files.items():
                if filepath.endswith("agent.yml"):
                    try:
                        parsed = yaml.safe_load(content)
                        if not isinstance(parsed, dict):
                            continue
                        agent_name = parsed.get("name", "unknown")
                        # Get tool names from domain_tools or tools
                        tool_names = parsed.get("domain_tools", [])
                        if not tool_names:
                            for t in parsed.get("tools", []):
                                if isinstance(t, str):
                                    tool_names.append(t)
                                elif isinstance(t, dict) and "name" in t:
                                    tool_names.append(t["name"])
                        for tn in tool_names:
                            if tn in py_tool_names:
                                xref.append({"agent": agent_name, "tool": tn, "status": "PASS"})
                            else:
                                xref.append({"agent": agent_name, "tool": tn, "status": "WARN",
                                             "error": f"Tool '{tn}' in {agent_name}'s YAML not found in tools.py"})
                    except yaml.YAMLError:
                        pass
            results["cross_reference"] = xref

    # Helper: find file by basename (handles src/messages.py and messages.py)
    def find_file(name):
        for key in files:
            if key == name or key.endswith(f"/{name}"):
                return files[key]
        return None

    # 1. Syntax validation
    for filename, code in files.items():
        if filename.endswith(".py"):
            try:
                ast.parse(code)
                results["syntax"].append({"file": filename, "status": "PASS"})
            except SyntaxError as e:
                results["syntax"].append({"file": filename, "status": "FAIL", "error": str(e)})
                results["overall"] = "FAIL"

    # Detect pattern from project.yml
    pattern = "distributed_grpc"  # default
    if yaml_files:
        for fp, content in yaml_files.items():
            if fp.endswith("project.yml"):
                try:
                    parsed = yaml.safe_load(content)
                    if isinstance(parsed, dict):
                        pattern = parsed.get("pattern", "distributed_grpc")
                except yaml.YAMLError:
                    pass

    # 2. Structure validation (pattern-aware)
    main_py = find_file("main.py")
    tools_py = find_file("tools.py")

    if pattern in ("swarm", "selector", "round_robin"):
        # === AGENTCHAT PATTERN CHECKS ===
        # main.py is auto-generated (YAML loader) — skip main.py content checks
        # Focus on tools.py and YAML consistency

        if tools_py:
            # Check: No **kwargs in tool functions
            if "**kwargs" in tools_py:
                results["structure"].append({"check": "No **kwargs in tools", "status": "FAIL",
                                             "error": "Tool functions must not use **kwargs — use typed parameters"})
                results["overall"] = "FAIL"
            else:
                results["structure"].append({"check": "No **kwargs in tools", "status": "PASS"})

            # Check: Tool functions should be async def
            try:
                tree = ast.parse(tools_py)
                sync_tools = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and not isinstance(node, ast.AsyncFunctionDef):
                        if not node.name.startswith("_"):
                            sync_tools.append(node.name)
                if sync_tools:
                    results["structure"].append({"check": "Tools are async def", "status": "WARN",
                                                 "error": f"Sync tool functions (should be async): {', '.join(sync_tools)}"})
                else:
                    results["structure"].append({"check": "Tools are async def", "status": "PASS"})
            except SyntaxError:
                pass  # Already caught in syntax validation

            # Check: Tools use httpx/MCP Gateway (not subprocess docker cli)
            if "httpx" in tools_py or "MCP_GATEWAY_URL" in tools_py or "_call_mcp_tool" in tools_py:
                results["structure"].append({"check": "Tools use MCP Gateway (httpx)", "status": "PASS"})
            elif "subprocess" in tools_py and "docker" in tools_py:
                results["structure"].append({"check": "Tools use MCP Gateway (httpx)", "status": "WARN",
                                             "error": "Tools use subprocess+docker CLI — should use httpx+MCP Gateway for container compatibility"})

    else:
        # === DISTRIBUTED_GRPC PATTERN CHECKS ===
        messages_py = find_file("messages.py")
        if messages_py:
            if "@dataclass" in messages_py:
                results["structure"].append({"check": "messages.py has @dataclass", "status": "PASS"})
            else:
                results["structure"].append({"check": "messages.py has @dataclass", "status": "FAIL"})
                results["overall"] = "FAIL"

        host_py = find_file("host.py")
        if host_py:
            if "GrpcWorkerAgentRuntimeHost" in host_py:
                results["structure"].append({"check": "host.py has GrpcWorkerAgentRuntimeHost", "status": "PASS"})
            else:
                results["structure"].append({"check": "host.py has GrpcWorkerAgentRuntimeHost", "status": "FAIL"})
                results["overall"] = "FAIL"

        worker_py = find_file("worker.py")
        if worker_py:
            if "GrpcWorkerAgentRuntime" in worker_py:
                results["structure"].append({"check": "worker.py has GrpcWorkerAgentRuntime", "status": "PASS"})
            else:
                results["structure"].append({"check": "worker.py has GrpcWorkerAgentRuntime", "status": "FAIL"})
                results["overall"] = "FAIL"
            if "try_get_known_serializers_for_type" in worker_py:
                results["structure"].append({"check": "worker.py registers serializers", "status": "PASS"})
            else:
                results["structure"].append({"check": "worker.py registers serializers", "status": "WARN"})

    # Common checks (all patterns)
    docker_compose = find_file("docker-compose.yml")
    if docker_compose:
        results["structure"].append({"check": "docker-compose.yml exists", "status": "PASS"})
    else:
        results["structure"].append({"check": "docker-compose.yml exists", "status": "WARN"})

    if find_file("requirements.txt") is not None:
        results["structure"].append({"check": "requirements.txt exists", "status": "PASS"})
    else:
        results["structure"].append({"check": "requirements.txt exists", "status": "WARN"})

    # 3. API correctness checks
    api_antipatterns = [
        ("ctx.send_message", "Must use self.send_message(), not ctx.send_message()"),
        (".Completion.create", "Must use .chat.completions.create(), not .Completion.create()"),
        ("engine=\"davinci\"", "Must use model='gpt-4o', not engine='davinci'"),
        ("engine='davinci'", "Must use model='gpt-4o', not engine='davinci'"),
        (".choices[0].text", "Must use .choices[0].message.content, not .choices[0].text"),
    ]
    for filename, code in files.items():
        if filename.endswith(".py"):
            for pattern, msg in api_antipatterns:
                if pattern in code:
                    results.setdefault("api_check", []).append(
                        {"file": filename, "status": "FAIL", "error": f"{msg} (found: {pattern})"}
                    )
                    results["overall"] = "FAIL"
    if "api_check" not in results:
        results["api_check"] = [{"check": "No API antipatterns found", "status": "PASS"}]

    # 4. Import validation (internal imports only, in temp dir)
    tmpdir = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="autogen_test_")
        for filename, code in files.items():
            if filename.endswith(".py"):
                # Strip src/ prefix for flat import test
                basename = filename.split("/")[-1]
                (Path(tmpdir) / basename).write_text(code, encoding="utf-8")

        # Test that messages.py can be imported standalone
        if find_file("messages.py"):
            try:
                proc = subprocess.run(
                    [sys.executable, "-c", "import messages"],
                    cwd=tmpdir, capture_output=True, text=True, timeout=10
                )
                if proc.returncode == 0:
                    results["imports"].append({"file": "messages.py", "status": "PASS"})
                else:
                    err = proc.stderr.strip().split("\n")[-1] if proc.stderr else "unknown"
                    # Tolerate autogen imports
                    if "autogen" in err.lower() or "No module named" in err:
                        results["imports"].append({"file": "messages.py", "status": "SKIP", "reason": err})
                    else:
                        results["imports"].append({"file": "messages.py", "status": "FAIL", "error": err})
                        results["overall"] = "FAIL"
            except subprocess.TimeoutExpired:
                results["imports"].append({"file": "messages.py", "status": "SKIP", "reason": "timeout"})

    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)

    return results


# --- Output Writer ---

def write_output(task_name: str, code_files: dict, yaml_files: dict = None, cascade_meta: dict = None, team_key: str = None) -> Path:
    """Write validated files to output directory with nested structure.

    Structure:
      output/project_name/
        project.yml
        agents/...          (from yaml_files)
        mcp_servers/...     (from yaml_files)
        src/...             (from code_files)
        docker/...          (from code_files)
        requirements.txt
        README.md
    """
    if team_key:
        slug = re.sub(r'[^a-z0-9]+', '_', team_key.lower()).strip('_')[:40]
    else:
        slug = re.sub(r'[^a-z0-9]+', '_', task_name.lower()).strip('_')[:40]
    # Version numbering: find highest existing vN for this slug, increment
    existing = sorted(OUTPUT_DIR.glob(f"{slug}_v*")) if OUTPUT_DIR.exists() else []
    max_v = 0
    for d in existing:
        m = re.search(r'_v(\d+)$', d.name)
        if m:
            max_v = max(max_v, int(m.group(1)))
    out_dir = OUTPUT_DIR / f"{slug}_v{max_v + 1}"
    out_dir.mkdir(parents=True, exist_ok=True)

    written = []

    # Write YAML architecture files (agents/, mcp_servers/, project.yml)
    if yaml_files:
        for filepath, content in yaml_files.items():
            target = out_dir / filepath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(filepath)

    # Validate every agent has tools (warn if missing)
    if yaml_files and code_files:
        tool_funcs_in_code = set()
        for fpath, fcontent in code_files.items():
            if fpath.endswith("tools.py"):
                tool_funcs_in_code = set(re.findall(r'(?:async )?def (\w+)\(', fcontent))
        for fpath, fcontent in yaml_files.items():
            if fpath.endswith("agent.yml"):
                try:
                    agent_cfg = yaml.safe_load(fcontent)
                    if isinstance(agent_cfg, dict):
                        dtools = agent_cfg.get("domain_tools", [])
                        aname = agent_cfg.get("name", "?")
                        if not dtools:
                            print(f"  [WARN] Agent {aname} has no domain_tools: {fpath}")
                        for tname in dtools:
                            if tool_funcs_in_code and tname not in tool_funcs_in_code:
                                print(f"  [WARN] Tool '{tname}' referenced by {aname} not found in tools.py")
                except yaml.YAMLError:
                    pass

    # Ensure project.yml has task field (LLM might forget it)
    if yaml_files and "project.yml" in yaml_files:
        try:
            proj = yaml.safe_load(yaml_files["project.yml"])
            if isinstance(proj, dict) and "task" not in proj:
                proj["task"] = task_name
                (out_dir / "project.yml").write_text(
                    yaml.dump(proj, default_flow_style=False), encoding="utf-8")
        except yaml.YAMLError:
            pass

    # Inject generic YAML-loader main.py (only for agentchat patterns, not gRPC)
    if yaml_files and "project.yml" in yaml_files:
        try:
            proj = yaml.safe_load(yaml_files["project.yml"])
            if isinstance(proj, dict) and proj.get("pattern") != "distributed_grpc":
                code_files["src/main.py"] = GENERIC_MAIN_PY
        except yaml.YAMLError:
            code_files["src/main.py"] = GENERIC_MAIN_PY

    # Write code files (src/, docker/, requirements.txt, README.md)
    for filepath, content in code_files.items():
        target = out_dir / filepath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(filepath)

    # --- Ensure requirements.txt exists ---
    req_path = out_dir / "requirements.txt"
    if not req_path.exists():
        req_path.write_text(
            "autogen-agentchat>=0.4\nautogen-ext[openai]>=0.4\n"
            "autogen-core>=0.4\nopenai>=1.0\nhttpx>=0.27\ntiktoken\npyyaml>=6.0\n"
        )
    else:
        # Ensure critical deps are present
        current = req_path.read_text().lower()
        extras = []
        if "httpx" not in current:
            extras.append("httpx>=0.27")
        if "tiktoken" not in current:
            extras.append("tiktoken")
        if "pyyaml" not in current and "yaml" not in current:
            extras.append("pyyaml>=6.0")
        if extras:
            with open(req_path, "a") as f:
                for pkg in extras:
                    f.write(f"\n{pkg}")

    # --- Write standalone Docker infrastructure ---
    # Dockerfile with Node.js + Claude CLI (proven template)
    standalone_dockerfile = (
        "FROM python:3.11-slim\n"
        "WORKDIR /app\n"
        "# Install Node.js 20 + Claude Code CLI\n"
        "RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \\\n"
        "    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \\\n"
        "    apt-get install -y --no-install-recommends nodejs && \\\n"
        "    npm install -g @anthropic-ai/claude-code && \\\n"
        "    apt-get clean && rm -rf /var/lib/apt/lists/*\n"
        "COPY requirements.txt .\n"
        "RUN pip install --no-cache-dir -r requirements.txt\n"
        "COPY src/ .\n"
        "COPY project.yml .\n"
        "COPY agents/ agents/\n"
        'CMD ["python", "main.py"]\n'
    )
    (out_dir / "Dockerfile").write_text(standalone_dockerfile, encoding="utf-8")

    # docker-compose.yml with .claude auth mount for Claude Max
    claude_home = os.path.expanduser("~/.claude")
    claude_json = os.path.expanduser("~/.claude.json")

    # Check if vibemind network exists — prefer container-to-container over host.docker.internal
    import subprocess as _sp
    _vibemind_exists = False
    try:
        r = _sp.run(["docker", "network", "inspect", "vibemind"],
                    capture_output=True, timeout=5)
        _vibemind_exists = (r.returncode == 0)
    except Exception:
        pass

    app_service: dict = {
        "build": ".",
        "env_file": [".env"],
    }
    if _vibemind_exists:
        app_service["networks"] = ["vibemind"]
    else:
        app_service["extra_hosts"] = ["host.docker.internal:host-gateway"]

    compose: dict = {"services": {"app": app_service}}
    if _vibemind_exists:
        compose["networks"] = {"vibemind": {"external": True}}

    vols = ["./output:/app/output"]  # Mount output dir so results persist
    if os.path.exists(claude_home):
        # Use ~ for portability (Docker Compose resolves it on the host)
        vols.append("~/.claude:/root/.claude")
    if os.path.exists(claude_json):
        vols.append("~/.claude.json:/root/.claude.json")
    compose["services"]["app"]["volumes"] = vols

    # Add MCP Gateway env vars if project uses MCP servers
    if yaml_files and "project.yml" in yaml_files:
        try:
            proj = yaml.safe_load(yaml_files["project.yml"])
            if isinstance(proj, dict) and proj.get("mcp_servers"):
                env = compose["services"]["app"].setdefault("environment", [])
                env.append("MCP_GATEWAY_URL=${MCP_GATEWAY_URL:-}")
                env.append("MCP_GATEWAY_AUTH_TOKEN=${MCP_GATEWAY_AUTH_TOKEN:-}")
        except Exception:
            pass

    (out_dir / "docker-compose.yml").write_text(
        yaml.dump(compose, default_flow_style=False), encoding="utf-8")

    # .env — write real keys for pipeline eval; .env.example for end users
    env_lines = []
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        env_lines.append(f"OPENAI_API_KEY={api_key}")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        env_lines.append(f"ANTHROPIC_API_KEY={anthropic_key}")
    if env_lines:
        (out_dir / ".env").write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    # .env.example (safe to share / commit) — comprehensive template
    (out_dir / ".env.example").write_text(
        "# Required\n"
        "OPENAI_API_KEY=sk-your-key-here\n"
        "\n"
        "# Optional: Override model for all agents (default: gpt-4o)\n"
        "# OPENAI_MODEL=gpt-4o-mini\n"
        "\n"
        "# Optional: Claude Code CLI (for claude_code() tool)\n"
        "# ANTHROPIC_API_KEY=sk-ant-your-key-here\n"
        "\n"
        "# Optional: MCP Gateway (for MCP server tool access)\n"
        "# MCP_GATEWAY_URL=http://host.docker.internal:8808\n"
        "# MCP_GATEWAY_AUTH_TOKEN=your-token-here\n"
        "\n"
        "# Optional: Tool integrations (mock data used if missing)\n"
        "# RESEND_API_KEY=re_...           # Email sending\n"
        "# ZEROBOUNCE_API_KEY=...          # Email verification\n"
        "# SERPAPI_KEY=...                 # Web search\n"
        "# SLACK_WEBHOOK_URL=https://...   # Slack notifications\n"
        "# SLACK_BOT_TOKEN=xoxb-...        # Slack bot\n",
        encoding="utf-8",
    )

    # .gitignore — never commit secrets
    gitignore = out_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".env\noutput/\n__pycache__/\n", encoding="utf-8")

    # Remove broken LLM-generated docker/ subdirectory (root-level files replace it)
    docker_subdir = out_dir / "docker"
    if docker_subdir.exists():
        shutil.rmtree(docker_subdir)

    # --- Generate README.md ---
    proj_info = {}
    if yaml_files and "project.yml" in yaml_files:
        try:
            proj_info = yaml.safe_load(yaml_files["project.yml"]) or {}
        except Exception:
            pass

    team_name = proj_info.get("name", task_name)
    description = proj_info.get("description", "")
    pattern = proj_info.get("pattern", "swarm")
    lead = proj_info.get("lead_agent", "")
    mcp_servers = proj_info.get("mcp_servers", [])
    task_desc = proj_info.get("task", task_name)

    readme = [f"# {team_name}\n"]
    if description:
        readme.append(f"{description}\n")
    readme.append(f"**Pattern:** {pattern} | **Lead Agent:** {lead}\n")

    # Agent list
    readme.append("## Agents\n")
    agent_count = 0
    if yaml_files:
        for fpath in sorted(yaml_files):
            if fpath.endswith("agent.yml"):
                try:
                    acfg = yaml.safe_load(yaml_files[fpath])
                    if isinstance(acfg, dict) and "name" in acfg:
                        agent_count += 1
                        aname = acfg["name"]
                        adesc = acfg.get("description", "")
                        atools = acfg.get("domain_tools", [])
                        readme.append(f"- **{aname}**: {adesc}")
                        if atools:
                            readme.append(f"  - Tools: `{'`, `'.join(atools)}`")
                except Exception:
                    pass
    readme.append(f"\n**Total:** {agent_count} agents\n")

    # Quick Start
    readme.append("## Quick Start\n")
    readme.append("```bash")
    readme.append("# 1. Configure environment")
    readme.append("cp .env.example .env")
    readme.append("# Edit .env and add your OPENAI_API_KEY")
    readme.append("")
    readme.append("# 2. Build and run")
    readme.append("docker compose up --build")
    readme.append("")
    readme.append("# 3. Run with a custom task")
    readme.append('docker compose run --rm app python main.py "Your task here"')
    readme.append("```\n")

    # Environment Variables
    readme.append("## Environment Variables\n")
    readme.append("| Variable | Required | Description |")
    readme.append("|----------|----------|-------------|")
    readme.append("| `OPENAI_API_KEY` | Yes | OpenAI API key |")
    readme.append("| `OPENAI_MODEL` | No | Override model for all agents (default: gpt-4o) |")
    if mcp_servers:
        readme.append("| `MCP_GATEWAY_URL` | No | MCP Gateway URL for tool access |")
        readme.append("| `MCP_GATEWAY_AUTH_TOKEN` | No | Auth token for MCP Gateway |")
    readme.append("")

    # MCP Servers
    if mcp_servers:
        readme.append("## MCP Servers\n")
        readme.append(f"This team is configured to use: {', '.join(mcp_servers)}\n")
        readme.append("To enable MCP tools, start the Docker MCP Gateway:\n")
        readme.append("```bash")
        servers_arg = " ".join(mcp_servers)
        readme.append(f"docker mcp gateway run --port 8808 --transport sse --servers {servers_arg}")
        readme.append("```\n")
        readme.append("Then set `MCP_GATEWAY_URL=http://host.docker.internal:8808` in your `.env`.\n")

    # Task
    readme.append("## Default Task\n")
    readme.append(f"```\n{str(task_desc).strip()}\n```\n")
    readme.append("Override by passing a task on the command line (see Quick Start).\n")

    # Files
    readme.append("## Project Structure\n")
    readme.append("```")
    readme.append("project.yml          # Team configuration")
    readme.append("agents/              # Agent YAML definitions")
    readme.append("src/main.py          # Runtime loader (reads YAMLs)")
    readme.append("src/tools.py         # Tool implementations")
    readme.append("Dockerfile           # Container build")
    readme.append("docker-compose.yml   # Service orchestration")
    readme.append(".env.example         # Environment template")
    readme.append("```\n")

    (out_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")
    written.append("README.md")

    print(f"\n  Output written to: {out_dir}")
    print(f"  YAML files: {len(yaml_files) if yaml_files else 0}")
    print(f"  Code files: {len(code_files)}")
    print(f"  Standalone: Dockerfile + docker-compose.yml + .env")
    print(f"  Total: {len(written) + 4} files")

    # Write cascade_meta.yml if provided
    if cascade_meta:
        meta_path = out_dir / "cascade_meta.yml"
        meta_path.write_text(yaml.dump(cascade_meta, default_flow_style=False), encoding="utf-8")
        print(f"  Cascade meta: cascade_meta.yml (iteration {cascade_meta.get('iteration', '?')})")

    return out_dir


def load_cascade_context(source_dir: str | Path) -> "CascadeContext":
    """Load a previous pipeline output as CascadeContext for cascade iteration.

    Reads project.yml, all agent YAMLs, src/tools.py, and optional cascade_meta.yml
    from a previous output directory.
    """
    src = Path(source_dir)
    if not src.exists():
        # Try resolving relative to OUTPUT_DIR
        src = OUTPUT_DIR / Path(source_dir).name
    if not src.exists():
        # Try resolving relative to script directory parent (project root)
        src = Path(__file__).parent.parent / source_dir
    if not src.exists():
        raise FileNotFoundError(f"Cascade source not found: {source_dir} (tried absolute, OUTPUT_DIR, and project root)")

    # Load project.yml
    project_yml = {}
    proj_path = src / "project.yml"
    if proj_path.exists():
        project_yml = yaml.safe_load(proj_path.read_text(encoding="utf-8")) or {}

    # Collect all agent YAMLs
    agent_yamls = {}
    yaml_files_raw = {}
    agents_dir = src / "agents"
    if agents_dir.exists():
        for yml_file in sorted(agents_dir.rglob("*.yml")):
            rel = str(yml_file.relative_to(src)).replace("\\", "/")
            raw = yml_file.read_text(encoding="utf-8")
            yaml_files_raw[rel] = raw
            try:
                agent_yamls[rel] = yaml.safe_load(raw) or {}
            except yaml.YAMLError:
                agent_yamls[rel] = {}

    # Add project.yml to yaml_files_raw
    if proj_path.exists():
        yaml_files_raw["project.yml"] = proj_path.read_text(encoding="utf-8")

    # Also load mcp_servers/*.yml if present
    mcp_dir = src / "mcp_servers"
    if mcp_dir.exists():
        for yml_file in sorted(mcp_dir.rglob("*.yml")):
            rel = str(yml_file.relative_to(src)).replace("\\", "/")
            raw = yml_file.read_text(encoding="utf-8")
            yaml_files_raw[rel] = raw

    # Load src/tools.py
    tools_py = ""
    tools_path = src / "src" / "tools.py"
    if tools_path.exists():
        tools_py = tools_path.read_text(encoding="utf-8")

    # Load cascade_meta.yml if exists
    iteration = 0
    history = []
    meta_path = src / "cascade_meta.yml"
    if meta_path.exists():
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        iteration = meta.get("iteration", 0)
        history = meta.get("cascade_history", [])

    ctx = CascadeContext(
        source_dir=src,
        project_yml=project_yml,
        agent_yamls=agent_yamls,
        tools_py=tools_py,
        yaml_files_raw=yaml_files_raw,
        iteration_number=iteration,
        cascade_history=list(history),
    )
    agent_count = len(agent_yamls)
    tool_funcs = len(re.findall(r"^(?:async )?def (?!_)\w+", tools_py, re.MULTILINE))
    print(f"[Cascade] Loaded context from {src.name}: {agent_count} agents, {tool_funcs} tools, iteration {iteration}")
    return ctx
