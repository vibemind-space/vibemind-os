"""SwarmPipeline — 11-agent code generation pipeline orchestrator."""

import asyncio
import json
import os
import re
import shutil
import time
from pathlib import Path

import yaml

from .constants import (
    CascadeContext, MINIBOOK_URL, POLL_INTERVAL, STEP_TIMEOUT, MAX_REVISIONS,
    OUTPUT_DIR, MCP_GATEWAY_PORT,
)
from .knowledge import AUTOGEN_PATTERNS, AUTOGEN_RAG_TOOLS, AGENT_ROLES, FLOW, MCP_SERVER_CONFIG_INFO
from .api_client import api_post, api_get
from .llm import call_gpt4o, call_gpt4o_json, call_gpt4o_with_tools
from .docker_ops import (
    get_mcp_catalog, format_catalog_for_llm, classify_task_domain,
    prepare_docker_context, docker_build_test, docker_run_test, docker_run_test_with_args,
    enable_mcp_servers, get_mcp_server_tools, format_mcp_tools_for_prompt,
    get_installed_mcp_servers,
    start_mcp_gateway, stop_mcp_gateway,
    gordon_fix_and_rebuild, gordon_fix_and_rerun,
    configure_mcp_server, set_mcp_secret,
    check_mcp_secret_exists, inspect_mcp_server_fields,
)
from .code_processing import (
    parse_code_blocks, parse_yaml_blocks, find_code_post,
    test_generated_code, write_output,
)
from .todo_implementer import implement_todos, scan_todo_tools, ask_user
from .input_parser import SALES_TOOL_IMPLEMENTATIONS


# Known-good claude_code implementation — injected when LLM truncates it
_CLAUDE_CODE_TEMPLATE = SALES_TOOL_IMPLEMENTATIONS["claude_code"].strip()


def _fix_kwargs_tools(code: str) -> str:
    """Fix **kwargs tool signatures that crash autogen's _function_utils.py.

    Autogen calls typing.get_type_hints() on tool functions and crashes with
    KeyError: 'kwargs' when a function uses **kwargs. Replace with typed params.
    """
    # Match: async def func_name(**kwargs) -> str:
    pattern = r'(async def (\w+)\()\*\*kwargs\)( -> str:)'
    matches = list(re.finditer(pattern, code))
    if not matches:
        return code

    for m in reversed(matches):  # reverse to preserve offsets
        func_name = m.group(2)
        print(f"[Pipeline] Fixing **kwargs in {func_name}() -> typed query param")
        replacement = f'{m.group(1)}query: str = ""{m.group(3)}'
        code = code[:m.start()] + replacement + code[m.end():]
        # Also fix the body: replace kwargs references with query
        # Find the function body (until next function or end)
        body_start = m.end()
        body_match = re.search(r'\n(?=async def |def |class |\Z)', code[body_start:])
        body_end = body_start + body_match.start() if body_match else len(code)
        body = code[body_start:body_end]
        body = body.replace('str(kwargs)', f'str({{"query": query}})')
        body = body.replace('"kwargs": str(kwargs)', f'"query": query')
        code = code[:body_start] + body + code[body_end:]
    return code


def _fix_truncated_tools_py(code: str) -> str:
    """Fix truncated claude_code function in LLM-generated tools.py.

    The LLM consistently truncates claude_code's f-string at line ~45.
    Detect this and replace with the known-good template.
    """
    # First fix **kwargs (crashes autogen)
    code = _fix_kwargs_tools(code)

    if "async def claude_code(" not in code:
        return code  # No claude_code in this file

    # Check if claude_code is complete (has its except block)
    match = re.search(r'(async def claude_code\(.*?)(?=\nasync def |\n# ---|\nclass |\Z)',
                      code, re.DOTALL)
    if not match:
        return code

    func_body = match.group(1)
    # Replace if: truncated (missing except) OR old CLI version (missing output_file param)
    needs_replace = (
        'except' not in func_body
        or func_body.rstrip().endswith(('\\n', '"', "'"))
        or 'output_file' not in func_body
        or 'OPENAI_API_KEY' not in func_body
    )
    if needs_replace:
        print(f"[Pipeline] Replacing claude_code ({len(func_body)} chars -> {len(_CLAUDE_CODE_TEMPLATE)} chars)")
        code = code[:match.start()] + _CLAUDE_CODE_TEMPLATE + code[match.end():]
    return code


class SwarmPipeline:
    """Orchestrates the 11-agent code generation swarm via Minibook."""

    def __init__(self, agents: dict, project_id: str, task_name: str,
                 cascade_from: "CascadeContext" = None,
                 cascade_feature: str = "",
                 input_manifest: dict = None,
                 input_phase: str = None,
                 input_team_key: str = None,
                 sub_team_dirs: dict = None):
        self.agents = agents  # {name: {id, name, api_key}}
        self.project_id = project_id
        self.task_name = task_name
        self.start_time = None
        self.completed_steps = set()
        self.revision_count = 0
        self.code_post_id = None  # Track the code post for reviewer comments
        self.generated_files = {}
        self.yaml_files = {}  # YAML architecture files from ArchitectAgent
        self.architect_output = ""  # Raw YAML output for CoderAgent context
        self.output_path = None
        # Cascade mode
        self.cascade_ctx = cascade_from
        self.cascade_feature = cascade_feature
        self.is_cascade = cascade_from is not None
        if self.is_cascade:
            self.yaml_files = dict(cascade_from.yaml_files_raw)
            self.architect_output = self._format_existing_architecture()
            if cascade_from.tools_py:
                self.generated_files["src/tools.py"] = cascade_from.tools_py
        # Input file mode
        self.input_manifest = input_manifest
        self.input_phase = input_phase  # "core", "sub_team", "wiring"
        self.input_team_key = input_team_key
        self.sub_team_dirs = sub_team_dirs or {}
        self.is_input_file = input_manifest is not None
        # MCP Discovery (CatalogAgent)
        self.mcp_catalog = {}  # Full Docker MCP catalog
        self.mcp_selection = ""  # LLM-selected MCP servers for this task
        self.mcp_enabled = []  # Actually enabled server names (no API key needed)
        self.mcp_server_tools = {}  # Real tools from docker mcp server inspect
        self.mcp_tools_prompt = ""  # Formatted tool info for CoderAgent
        # Coordination events
        self.reviewer_done = asyncio.Event()  # Signals CoderAgent to stop waiting
        # Docker Eval (BuilderAgent / ExecutorAgent)
        self.build_dir = None  # Path to flat Docker build directory
        self.build_result = None  # {"status": "PASS|FAIL", "output": ..., "duration": N}
        self.run_result = None  # {"status": "PASS|FAIL", "logs": ..., "duration": N}
        self.output_eval = None  # {"status": "PASS|FAIL", "reason": ..., "files": [...]}
        self.export_result = None  # {"status": "SUCCESS|FAIL", "path": ..., "repo_url": ...}
        self.pre_todo_eval = None  # eval result before TodoImplementer (mock tools)
        self.todo_implemented = False  # True if step_todo_implement updated tools.py

    # --- Cascade helper methods ---

    def _format_existing_architecture(self) -> str:
        """Format existing YAML files from cascade context as ### YAML: blocks."""
        parts = []
        for filepath, content in self.cascade_ctx.yaml_files_raw.items():
            parts.append(f"### YAML: {filepath}\n```yaml\n{content}\n```")
        return "\n\n".join(parts)

    def _build_architect_cascade_prompt(self) -> str:
        """Build cascade-specific context for ArchitectAgent to EXTEND architecture."""
        ctx = self.cascade_ctx
        existing_agents = []
        for filepath, agent_data in ctx.agent_yamls.items():
            existing_agents.append(
                f"  - {agent_data.get('name', '?')} ({agent_data.get('role', '?')}): "
                f"{agent_data.get('description', 'no description')[:80]}"
            )
        existing_tools = re.findall(r'async\s+def\s+(\w+)\s*\(', ctx.tools_py)
        history_str = ""
        if ctx.cascade_history:
            history_str = "### Cascade History:\n" + "\n".join(
                f"  - Iteration {i+1}: {feat}" for i, feat in enumerate(ctx.cascade_history)
            ) + "\n\n"
        return (
            f"=== CASCADE MODE: EXTEND EXISTING ARCHITECTURE ===\n\n"
            f"You are EXTENDING an existing agent system, NOT creating from scratch.\n"
            f"This is cascade iteration #{ctx.iteration_number + 1}.\n\n"
            f"FEATURE TO ADD: {self.cascade_feature}\n\n"
            f"EXISTING ARCHITECTURE (DO NOT REMOVE OR REPLACE):\n\n"
            f"### Current project.yml:\n```yaml\n{ctx.yaml_files_raw.get('project.yml', '')}\n```\n\n"
            f"### Current Agents:\n" + "\n".join(existing_agents) + "\n\n"
            f"### Current Tools in tools.py:\n  {', '.join(existing_tools)}\n\n"
            f"{history_str}"
            f"=== RULES FOR CASCADE MODE ===\n"
            f"1. KEEP all existing agents — do NOT remove or rename them\n"
            f"2. ADD new agents and/or tools for: {self.cascade_feature}\n"
            f"3. UPDATE project.yml agents_total to include new agents\n"
            f"4. UPDATE lead agent's handoffs to include any new agents\n"
            f"5. ADD new agent YAML files using ### YAML: agents/<name>/agent.yml format\n"
            f"6. If modifying an existing agent, output the FULL updated YAML for that agent\n"
            f"7. For UNCHANGED agents, do NOT output their YAML (they are preserved automatically)\n"
            f"8. Preserve the existing pattern: {ctx.project_yml.get('pattern', 'unknown')}\n\n"
        )

    def _build_coder_cascade_prompt(self) -> str:
        """Build cascade-specific context for CoderAgent to EXTEND tools.py."""
        ctx = self.cascade_ctx
        existing_funcs = []
        for match in re.finditer(
            r'async\s+def\s+(\w+)\s*\([^)]*\)\s*(?:->[^:]*)?:\s*\n\s*"""([^"]*?)"""',
            ctx.tools_py, re.DOTALL
        ):
            existing_funcs.append(f"  - {match.group(1)}(): {match.group(2).strip()[:80]}")
        return (
            f"=== CASCADE MODE: EXTEND EXISTING tools.py ===\n\n"
            f"You are ADDING to an existing tools.py, NOT rewriting from scratch.\n\n"
            f"FEATURE TO ADD: {self.cascade_feature}\n\n"
            f"### EXISTING tools.py (PRESERVE ALL of this code):\n"
            f"```python\n{ctx.tools_py}\n```\n\n"
            f"### Existing functions (DO NOT REMOVE):\n"
            + "\n".join(existing_funcs) + "\n\n"
            f"### New YAML Architecture (agents added this iteration):\n\n"
            f"{self.architect_output}\n\n"
            f"=== RULES FOR CASCADE MODE ===\n"
            f"1. Output the COMPLETE tools.py including ALL existing functions\n"
            f"2. ADD new tool functions at the END of the file, after existing ones\n"
            f"3. Do NOT modify existing function signatures or behavior\n"
            f"4. New tools must support the new agents added by ArchitectAgent\n"
            f"5. New tool function names MUST match domain_tools in the new agent YAML files\n"
            f"6. You may add new imports at the top if needed\n"
            f"7. Preserve OUTPUT_DIR, MCP_GATEWAY_URL, _call_mcp_tool, etc.\n\n"
            f"Generate ONLY src/tools.py with ALL existing + NEW tool functions.\n"
        )

    def key(self, name: str) -> str:
        return self.agents[name].get("api_key", "")

    async def post(self, session, title, content, post_type="discussion", tags=None):
        """Create a post in the project."""
        return await api_post(
            session,
            f"/api/v1/projects/{self.project_id}/posts",
            {"title": title, "content": content, "type": post_type, "tags": tags or []},
            api_key=self.key("SwarmManager"),
        )

    async def post_as(self, session, agent_name, title, content, post_type="discussion", tags=None):
        """Create a post as a specific agent."""
        return await api_post(
            session,
            f"/api/v1/projects/{self.project_id}/posts",
            {"title": title, "content": content, "type": post_type, "tags": tags or []},
            api_key=self.key(agent_name),
        )

    async def comment_as(self, session, agent_name, post_id, content):
        """Add a comment as a specific agent."""
        return await api_post(
            session,
            f"/api/v1/posts/{post_id}/comments",
            {"content": content},
            api_key=self.key(agent_name),
        )

    async def poll_mention(self, session, agent_name, max_activations=1):
        """Poll for @mention notifications. Returns list of triggering post contents."""
        activations = 0
        api_key = self.key(agent_name)
        start = time.time()

        while activations < max_activations:
            if time.time() - start > STEP_TIMEOUT:
                print(f"  [{agent_name}] TIMEOUT after {STEP_TIMEOUT}s")
                return None

            try:
                notifications = await api_get(
                    session, "/api/v1/notifications",
                    api_key=api_key, params={"unread_only": "true"}
                )

                for notif in notifications:
                    if notif["type"] == "mention" and not notif["read"]:
                        post_id = notif.get("payload", {}).get("post_id")
                        comment_id = notif.get("payload", {}).get("comment_id")

                        # Mark as read
                        await api_post(session, f"/api/v1/notifications/{notif['id']}/read",
                                       {}, api_key=api_key)

                        # Read the triggering content
                        if comment_id:
                            # Mentioned in a comment — read the parent post for full context
                            post = await api_get(session, f"/api/v1/posts/{post_id}")
                            comments = await api_get(session, f"/api/v1/posts/{post_id}/comments")
                            comment_content = ""
                            for c in comments:
                                if c["id"] == comment_id:
                                    comment_content = c["content"]
                                    break
                            return {"post": post, "comment": comment_content, "post_id": post_id}
                        elif post_id:
                            post = await api_get(session, f"/api/v1/posts/{post_id}")
                            return {"post": post, "comment": None, "post_id": post_id}

            except Exception as e:
                print(f"  [{agent_name}] Poll error: {e}")

            await asyncio.sleep(POLL_INTERVAL)

        return None

    # --- Helpers ---

    def _build_architecture_graph(self) -> dict:
        """Convert YAML files into a graph structure for React Flow visualization."""
        nodes = []
        edges = []
        groups = []
        agent_names = set()

        for path, content in self.yaml_files.items():
            if not path.endswith("agent.yml"):
                continue
            try:
                cfg = yaml.safe_load(content)
                if not isinstance(cfg, dict) or "name" not in cfg:
                    continue
                name = cfg["name"]
                agent_names.add(name)

                parts = path.split("/")
                group = parts[1] if len(parts) >= 3 else "core"

                agent_type = "specialist"
                if any(kw in name.lower() for kw in ["manager", "lead", "vp", "cso", "director"]):
                    agent_type = "manager"

                nodes.append({"id": name, "type": agent_type, "label": name, "group": group})

                for handoff in cfg.get("handoffs", []):
                    target = handoff if isinstance(handoff, str) else handoff.get("target", "")
                    if target:
                        edges.append({"source": name, "target": target, "type": "handoff", "label": "handoff"})

            except yaml.YAMLError:
                continue

        seen_groups = set()
        for n in nodes:
            g = n.get("group", "core")
            if g not in seen_groups:
                groups.append({"id": g, "label": g.replace("_", " ").title()})
                seen_groups.add(g)

        task_label = self.task_name[:40] if self.task_name else "Task"
        nodes.insert(0, {"id": "input", "type": "input", "label": task_label})
        nodes.append({"id": "output", "type": "output", "label": "Output"})

        managers = [n["id"] for n in nodes if n.get("type") == "manager"]
        if managers:
            edges.insert(0, {"source": "input", "target": managers[0], "type": "data", "label": "task"})
            edges.append({"source": managers[0], "target": "output", "type": "data", "label": "report"})

        return {"nodes": nodes, "edges": edges, "groups": groups}

    # --- Pipeline Steps ---

    async def step_swarm_manager(self, session, task_description):
        """SwarmManager: Generate specification."""
        self.start_time = time.time()
        print("\n" + "=" * 60)
        print("  AUTOGEN SWARM PIPELINE STARTED")
        print("=" * 60)

        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"

        print(f"\n[SwarmManager] Generating specification... ({elapsed()})")
        if self.is_cascade:
            ctx = self.cascade_ctx
            existing_agents = [v.get("name", "?") for v in ctx.agent_yamls.values() if isinstance(v, dict)]
            spec_input = (
                f"CASCADE ITERATION {ctx.iteration_number + 1}\n\n"
                f"BASE SYSTEM: {ctx.project_yml.get('task', task_description)}\n"
                f"EXISTING AGENTS: {', '.join(existing_agents)}\n"
                f"PREVIOUS ITERATIONS: {'; '.join(ctx.cascade_history) if ctx.cascade_history else 'None'}\n\n"
                f"NEW FEATURE TO ADD: {self.cascade_feature}\n\n"
                f"Generate a specification FOCUSED ON THE NEW FEATURE. "
                f"The existing system already works — describe only what needs to be ADDED or CHANGED."
            )
        else:
            spec_input = f"Task: {task_description}"
        spec = await call_gpt4o(
            AGENT_ROLES["SwarmManager"]["prompt"],
            spec_input
        )

        post = await self.post_as(session, "SwarmManager",
                                  f"Specification: {self.task_name}",
                                  f"## Task Specification\n\n{spec}\n\n@CatalogAgent your turn!",
                                  post_type="task", tags=["spec", "swarm"])

        self.completed_steps.add("SwarmManager")
        print(f"[SwarmManager] DONE ({elapsed()}) — posted spec")
        return spec

    # --- Config-Modal: ask user for MCP config/secrets via Minibook ---

    @staticmethod
    def _mask_secret(value: str) -> str:
        """Mask a secret value for safe logging."""
        if len(value) <= 8:
            return "***"
        return value[:4] + "***" + value[-4:]

    async def _request_mcp_config(self, session, needs_secret: list, needs_config: list) -> dict:
        """Ask user for MCP server config/secrets via WebSocket modal.

        Returns dict of server_name -> {"configured": bool} after applying answers.
        Auto-configures known servers, asks user for unknowns via form modal.
        """
        results = {}

        # Apply auto-configs immediately
        for name in needs_config:
            info = MCP_SERVER_CONFIG_INFO.get(name, {})
            if info.get("auto_config"):
                ok = await configure_mcp_server(name, info["auto_config"])
                results[name] = {"configured": ok}

        # Build modal metadata for servers that need user input
        server_entries = []

        for name in needs_config:
            info = MCP_SERVER_CONFIG_INFO.get(name, {})
            fields = []
            if info.get("auto_config"):
                # Auto-configured — show as info only
                server_entries.append({
                    "name": name,
                    "description": info.get("description", ""),
                    "type": "config",
                    "auto_config": info["auto_config"],
                    "fields": [],
                })
                continue
            for field_name, field_info in info.get("fields", {}).items():
                fields.append({
                    "key": field_name,
                    "label": field_info.get("description", field_name),
                    "input_type": "text",
                    "description": field_info.get("description", ""),
                    "how_to_get": field_info.get("how_to_get"),
                    "default": str(field_info["default"]) if field_info.get("default") else None,
                    "required": True,
                })
            if fields:
                server_entries.append({
                    "name": name,
                    "description": info.get("description", ""),
                    "type": "config",
                    "auto_config": None,
                    "fields": fields,
                })

        for name in needs_secret:
            info = MCP_SERVER_CONFIG_INFO.get(name, {})
            # For unknown servers, try dynamic discovery
            if not info:
                discovered = await inspect_mcp_server_fields(name)
                if discovered:
                    info = discovered
                    print(f"  [MCP Config] {name}: dynamisch entdeckt — {list(discovered.get('fields', {}).keys())}")
            fields = []
            for field_name, field_info in info.get("fields", {}).items():
                # Check if secret already stored — skip if yes
                already_set = await check_mcp_secret_exists(name, field_name)
                if already_set:
                    print(f"  [MCP Config] {name}.{field_name}: bereits gesetzt — skip")
                    results.setdefault(name, {})["configured"] = True
                    fields.append({
                        "key": field_name,
                        "label": field_info.get("description", field_name),
                        "input_type": "password",
                        "description": field_info.get("description", ""),
                        "how_to_get": field_info.get("how_to_get"),
                        "default": None,
                        "required": False,
                        "already_set": True,  # Frontend zeigt ✓ statt Pflichtfeld
                    })
                else:
                    fields.append({
                        "key": field_name,
                        "label": field_info.get("description", field_name),
                        "input_type": "password",
                        "description": field_info.get("description", ""),
                        "how_to_get": field_info.get("how_to_get"),
                        "default": None,
                        "required": True,
                        "already_set": False,
                    })
            if fields:
                server_entries.append({
                    "name": name,
                    "description": info.get("description", ""),
                    "type": "secret",
                    "auto_config": None,
                    "fields": fields,
                })

        # If no user input needed (all auto-configured or already set), skip modal
        needs_input = any(
            any(not f.get("already_set") for f in s["fields"])
            for s in server_entries
        )
        if not needs_input:
            return results

        # Ask user via WebSocket modal
        answer = await ask_user(
            question_type="mcp_config",
            tool_name="CatalogAgent",
            message="MCP Server Konfiguration",
            metadata={"servers": server_entries},
            timeout=120,
        )

        if answer["action"] == "timeout":
            print(f"[CatalogAgent] Config-Modal timeout — using auto-config only")
            return results

        if not answer["text"] or answer["text"].strip().lower() == "skip":
            print(f"[CatalogAgent] User chose to skip config")
            return results

        # Parse JSON answer: {"configs": {"server": {"key": "value"}}}
        try:
            user_data = json.loads(answer["text"])
            configs = user_data.get("configs", {})
        except (json.JSONDecodeError, AttributeError):
            print(f"[CatalogAgent] Could not parse config response")
            return results

        for server_name, fields in configs.items():
            if not isinstance(fields, dict):
                continue
            info = MCP_SERVER_CONFIG_INFO.get(server_name, {})
            for key_name, value in fields.items():
                if not isinstance(value, str) or not value.strip():
                    continue
                value = value.strip()
                if info.get("type") == "secret":
                    ok = await set_mcp_secret(server_name, key_name, value)
                    results[server_name] = {"configured": ok}
                    print(f"[CatalogAgent] Secret set: {server_name}.{key_name}={self._mask_secret(value)}")
                elif info.get("type") == "config":
                    ok = await configure_mcp_server(server_name, {key_name: value})
                    results[server_name] = {"configured": ok}
                    print(f"[CatalogAgent] Config set: {server_name}.{key_name}={value}")
                else:
                    ok = await set_mcp_secret(server_name, key_name, value)
                    results[server_name] = {"configured": ok}
                    print(f"[CatalogAgent] Secret set (unknown type): {server_name}.{key_name}={self._mask_secret(value)}")

        return results

    async def step_catalog(self, session):
        """CatalogAgent: Discover MCP servers — installed-first, catalog as fallback."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[CatalogAgent] Waiting for @mention... ({elapsed()})")

        trigger = await self.poll_mention(session, "CatalogAgent")
        if not trigger:
            print("[CatalogAgent] TIMEOUT — no trigger received")
            return None

        task_spec = trigger["post"]["content"]

        # ── Step 1: Inventory — what's actually installed locally? ─────────
        print(f"[CatalogAgent] Checking installed MCP servers... ({elapsed()})")
        installed = await get_installed_mcp_servers()
        if installed:
            ready = [s for s in installed if s["ready"]]
            auto_cfg = [s for s in installed if s["status"] == "auto_configurable"]
            needs_cfg = [s for s in installed if s["status"] == "config_required"]
            needs_sec = [s for s in installed if s["status"] == "secrets_required"]
            needs_oauth = [s for s in installed if s["status"] == "oauth_required"]
            print(f"[CatalogAgent] Installed: {len(installed)} servers — "
                  f"{len(ready)} ready, {len(auto_cfg)} auto-configurable, "
                  f"{len(needs_cfg)} need config, {len(needs_sec)} need secrets")
            for s in installed:
                status_icon = {"ready": "[OK]", "auto_configurable": "[CFG]", "config_required": "[!CFG]",
                               "secrets_required": "[!KEY]", "oauth_required": "[!AUTH]"}.get(s["status"], "[?]")
                print(f"  {status_icon} {s['name']} ({s['status']})")
        else:
            print(f"[CatalogAgent] No installed MCP servers found (Docker not available?)")
            ready = auto_cfg = needs_cfg = needs_sec = needs_oauth = []

        # ── Step 2: Classify task domain for hints ────────────────────────
        domain_info = classify_task_domain(task_spec)
        if domain_info["domains"]:
            print(f"[CatalogAgent] Domain hints: {domain_info['domains']} -> "
                  f"key-free: {domain_info['recommended_key_free']}")

        # ── Step 3: Select from installed servers (LLM picks best match) ──
        installed_names = [s["name"] for s in installed]
        installed_summary = "\n".join(
            f"- **{s['name']}** [{s['status']}]" for s in installed
        ) or "(none installed)"

        # Also fetch remote catalog as secondary source
        catalog_summary = ""
        try:
            self.mcp_catalog = await get_mcp_catalog()
            catalog_summary = format_catalog_for_llm(self.mcp_catalog)
            catalog_count = len(self.mcp_catalog.get("registry", {}))
            print(f"[CatalogAgent] Remote catalog: {catalog_count} servers available")
        except Exception as e:
            print(f"[CatalogAgent] Catalog fetch failed: {e}")
            self.mcp_catalog = {"registry": {}}

        print(f"[CatalogAgent] LLM selecting from installed + catalog... ({elapsed()})")
        selection_result = await call_gpt4o_json(
            AGENT_ROLES["CatalogAgent"]["prompt"],
            f"## Task Specification\n\n{task_spec}"
            f"\n\n## INSTALLED MCP Servers (prefer these — already on this machine)\n\n{installed_summary}"
            f"\n\n## Domain Hints\n"
            f"Detected domains: {', '.join(domain_info.get('domains', []))}\n"
            f"Recommended key-free: {', '.join(domain_info.get('recommended_key_free', []))}\n"
            f"\n## FULL Remote Catalog (install from here if installed servers are insufficient)\n\n"
            f"{catalog_summary[:3000]}"
            f"\n\nRULES:\n"
            f"1. STRONGLY PREFER servers from the INSTALLED list — they are already available.\n"
            f"2. Only suggest servers from the remote catalog if installed servers don't cover the task.\n"
            f"3. For installed servers with status 'auto_configurable' — include them (will be auto-configured).\n"
            f"4. For installed servers with status 'secrets_required' — include them IF useful (user will be asked to provide keys).\n"
            f"5. Mark each server as 'installed' or 'needs_install' in your response.\n"
            f'\n\nRespond: {{"servers": [{{"name": "...", "source": "installed"|"catalog"}}], "reasoning": "..."}}',
            max_tokens=1024,
        )

        # Parse selection
        selected_names = []
        needs_install = []
        reasoning = ""
        registry = self.mcp_catalog.get("registry", {})

        if isinstance(selection_result, dict):
            reasoning = selection_result.get("reasoning", "")
            for entry in selection_result.get("servers", []):
                name = entry.get("name", entry) if isinstance(entry, dict) else str(entry)
                source = entry.get("source", "unknown") if isinstance(entry, dict) else "unknown"
                if name in installed_names:
                    selected_names.append(name)
                elif name in registry:
                    needs_install.append(name)
                else:
                    # Case-insensitive match
                    for iname in installed_names:
                        if name.lower() == iname.lower():
                            selected_names.append(iname)
                            break
                    else:
                        for rname in registry:
                            if name.lower() == rname.lower():
                                needs_install.append(rname)
                                break

        # Fallback: domain hints
        if not selected_names and not needs_install:
            print(f"[CatalogAgent] LLM extraction failed — falling back to domain hints")
            for hint in domain_info.get("recommended_key_free", []):
                if hint in installed_names:
                    selected_names.append(hint)
                elif hint in registry:
                    needs_install.append(hint)

        self.mcp_selection = reasoning or str(selected_names)
        print(f"[CatalogAgent] Selected installed: {selected_names}")
        if needs_install:
            print(f"[CatalogAgent] Suggested from catalog (needs install): {needs_install}")

        # ── Step 4: Human review ──────────────────────────────────────────
        review_msg = (
            f"MCP servers for: {self.task_name}\n"
            f"Selected (installed): {', '.join(selected_names) or 'none'}\n"
        )
        if needs_install:
            review_msg += f"To install from catalog: {', '.join(needs_install)}\n"

        available_for_review = [
            {"name": s["name"], "description": s["status"], "needs_key": s["secrets"]}
            for s in installed
        ]
        answer = await ask_user(
            question_type="mcp_selection",
            tool_name="CatalogAgent",
            message=review_msg,
            metadata={
                "available_servers": available_for_review,
                "selected_servers": selected_names,
                "install_candidates": needs_install,
                "domain_hints": domain_info.get("domains", []),
                "reasoning": reasoning,
            },
            timeout=60,
        )
        if answer["action"] == "reply" and answer["text"]:
            try:
                user_sel = json.loads(answer["text"])
                if "servers" in user_sel:
                    selected_names = [s for s in user_sel["servers"] if s in installed_names]
                    needs_install = [s for s in user_sel.get("install", []) if s in registry]
                print(f"[CatalogAgent] User adjusted: installed={selected_names}, install={needs_install}")
            except (json.JSONDecodeError, KeyError):
                pass

        # ── Step 5: Auto-configure installed servers that need CONFIG ─────
        # Process auto-configurable and config-required servers BEFORE enabling
        for srv in installed:
            if srv["name"] not in selected_names:
                continue
            if srv["status"] == "auto_configurable":
                info = MCP_SERVER_CONFIG_INFO.get(srv["name"], {})
                if info.get("auto_config"):
                    ok = await configure_mcp_server(srv["name"], info["auto_config"])
                    print(f"  [MCP Config] {srv['name']}: {'config set OK' if ok else 'config FAILED'}")

        # ── Step 6: Config-Modal for secrets/config BEFORE enabling ───────
        config_needed = [s for s in installed
                         if s["name"] in selected_names and s["status"] == "config_required"]
        secrets_needed = [s for s in installed
                          if s["name"] in selected_names and s["status"] == "secrets_required"]

        if config_needed or secrets_needed:
            print(f"[CatalogAgent] Config-Modal: {len(secrets_needed)} secrets + {len(config_needed)} configs needed ({elapsed()})")
            config_results = await self._request_mcp_config(
                session,
                [s["name"] for s in secrets_needed],
                [s["name"] for s in config_needed],
            )
            # Remove servers where user didn't provide config
            for name, result in config_results.items():
                if not result.get("configured"):
                    print(f"  [MCP Config] {name}: not configured — removing from selection")
                    selected_names = [s for s in selected_names if s != name]

        # ── Step 7: Enable selected installed servers ─────────────────────
        tools_info = ""
        if selected_names:
            print(f"[CatalogAgent] Enabling {len(selected_names)} installed servers: {selected_names} ({elapsed()})")
            mcp_result = await enable_mcp_servers(selected_names)
            self.mcp_enabled = mcp_result.get("enabled", [])
            still_needs = mcp_result.get("skipped_needs_key", [])
            print(f"[CatalogAgent] Enabled: {self.mcp_enabled}")
            if still_needs:
                print(f"[CatalogAgent] Still needs setup: {still_needs}")

        # ── Step 8: Install from catalog if needed ────────────────────────
        if needs_install:
            print(f"[CatalogAgent] Installing {len(needs_install)} from catalog: {needs_install} ({elapsed()})")
            install_result = await enable_mcp_servers(needs_install)
            newly_enabled = install_result.get("enabled", [])
            self.mcp_enabled.extend(newly_enabled)
            new_needs_cfg = install_result.get("needs_config", [])
            new_needs_sec = install_result.get("needs_secret", [])

            # Auto-config newly installed
            for name in new_needs_cfg:
                info = MCP_SERVER_CONFIG_INFO.get(name, {})
                if info.get("auto_config"):
                    ok = await configure_mcp_server(name, info["auto_config"])
                    if ok:
                        self.mcp_enabled.append(name)
                        print(f"  [MCP] {name}: installed + auto-configured")

            # Config-Modal for newly installed that need secrets
            if new_needs_sec:
                print(f"[CatalogAgent] Config-Modal for newly installed: {new_needs_sec}")
                cfg_results = await self._request_mcp_config(session, new_needs_sec, [])
                for name, result in cfg_results.items():
                    if result.get("configured"):
                        re_result = await enable_mcp_servers([name])
                        self.mcp_enabled.extend(re_result.get("enabled", []))

            print(f"[CatalogAgent] Final enabled after install: {self.mcp_enabled}")

        # ── Step 9: Inspect real tools from enabled servers ───────────────
        if self.mcp_enabled:
            print(f"[CatalogAgent] Inspecting real tools from enabled servers... ({elapsed()})")
            self.mcp_server_tools = await get_mcp_server_tools(self.mcp_enabled)
            self.mcp_tools_prompt = format_mcp_tools_for_prompt(self.mcp_server_tools)
            total_tools = sum(len(v) for v in self.mcp_server_tools.values())
            print(f"[CatalogAgent] Discovered {total_tools} real tools from {len(self.mcp_server_tools)} servers")
            tools_info = f"\n\n## Real MCP Tool Details\n\n{self.mcp_tools_prompt}"

        # ── Post result to Minibook ───────────────────────────────────────
        installed_text = "\n".join(
            f"- **{s['name']}** [{s['status']}]{'  ← enabled' if s['name'] in self.mcp_enabled else ''}"
            for s in installed
        ) or "none"

        post = await self.post_as(session, "CatalogAgent",
                                  f"MCP Selection: {self.task_name}",
                                  f"## Installed MCP Servers\n\n{installed_text}\n\n"
                                  f"## Enabled for this run\n{', '.join(self.mcp_enabled) if self.mcp_enabled else 'None'}"
                                  f"\n\nReasoning: {reasoning}"
                                  f"{tools_info}"
                                  f"\n\n@ArchitectAgent your turn!",
                                  post_type="task", tags=["mcp", "catalog", "swarm"])

        self.completed_steps.add("CatalogAgent")
        print(f"[CatalogAgent] DONE ({elapsed()}) — {len(self.mcp_enabled)} servers enabled")
        return self.mcp_selection

    async def step_architect(self, session):
        """ArchitectAgent: Design architecture."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[ArchitectAgent] Waiting for @mention... ({elapsed()})")

        trigger = await self.poll_mention(session, "ArchitectAgent")
        if not trigger:
            print("[ArchitectAgent] TIMEOUT — no trigger received")
            return None

        # Include ONLY actually-enabled MCP tools (not skipped servers)
        arch_input = trigger["post"]["content"]
        if self.mcp_tools_prompt:
            arch_input += f"\n\n--- AVAILABLE MCP TOOLS (actually enabled, use ONLY these) ---\n\n{self.mcp_tools_prompt}"
            arch_input += ("\n\nCRITICAL: ONLY use tools listed above. These are the ONLY MCP tools "
                          "actually available. Do NOT reference tools from servers that were skipped "
                          "due to missing API keys. Use the EXACT tool names shown above.")
        elif self.mcp_selection:
            arch_input += f"\n\n--- MCP SERVER SELECTION (from CatalogAgent) ---\n\n{self.mcp_selection}"

        # ALWAYS include a Claude Code tool — delegates tasks to Claude Code CLI
        arch_input += ("\n\n--- CLAUDE CODE TOOL (always available) ---\n\n"
                       "Every agent team has access to a 'claude_code' tool that delegates tasks "
                       "to Claude Code CLI (AI coding assistant). Use it for code writing, review, "
                       "refactoring, debugging, test generation, or complex analysis.\n"
                       "In agent YAML, include the tool:\n"
                       "  - name: claude_code\n"
                       "    description: Delegate tasks to Claude Code CLI\n"
                       "    parameters: {task: str, code: str, files: str}\n\n"
                       "This tool is ALWAYS available and does not require MCP. "
                       "Use it alongside domain tools for code-related work.")

        # ALWAYS check for recent research findings from DocResearcherAgent
        try:
            research = await api_get(session, "/api/v1/search",
                                     params={"tag": "autogen-docs", "limit": "3"})
            if research:
                arch_input += "\n\n--- RECENT AUTOGEN RESEARCH (from DocResearcherAgent) ---\n"
                for r in research[:3]:
                    arch_input += f"\n### {r.get('title', 'Research')}\n{r.get('content', '')[:400]}\n"
                print(f"[ArchitectAgent] Enriched with {len(research[:3])} research posts")
        except Exception:
            pass

        # INPUT FILE MODE: generate YAML deterministically from manifest
        if self.is_input_file:
            from .input_parser import (
                generate_core_team_yamls, generate_sub_team_yamls,
                generate_sales_tools_py, generate_wiring_tools, get_wiring_tool_names,
                review_tool_assignments,
            )
            if self.input_phase == "core":
                print(f"[ArchitectAgent] INPUT FILE MODE — generating core team YAMLs ({elapsed()})")
                self.yaml_files = generate_core_team_yamls(self.input_manifest)
                # Pre-generate tools.py from core team agents
                core_agents = dict(self.input_manifest["core_team"])
                core_agents = await review_tool_assignments(core_agents)
                self.generated_files["src/tools.py"] = generate_sales_tools_py(core_agents)
            elif self.input_phase == "sub_team" and self.input_team_key:
                print(f"[ArchitectAgent] INPUT FILE MODE — generating {self.input_team_key} sub-team YAMLs ({elapsed()})")
                self.yaml_files = generate_sub_team_yamls(self.input_manifest, self.input_team_key)
                # Pre-generate tools.py from sub-team agents
                sub = self.input_manifest["sub_teams"][self.input_team_key]
                all_agents = {sub["manager"]: self.input_manifest["core_team"].get(sub["manager"], {})}
                all_agents.update(sub["agents"])
                all_agents = await review_tool_assignments(all_agents)
                self.generated_files["src/tools.py"] = generate_sales_tools_py(all_agents)
            elif self.input_phase == "wiring":
                print(f"[ArchitectAgent] INPUT FILE MODE — generating wiring tools ({elapsed()})")
                # Regenerate core team with wiring tools added to managers
                self.yaml_files = generate_core_team_yamls(self.input_manifest)
                # Add wiring tool names to manager agent.yml domain_tools
                wiring_names = get_wiring_tool_names(self.input_manifest)
                for path, content in list(self.yaml_files.items()):
                    if path.endswith("agent.yml") and "CSOAgent" not in path:
                        try:
                            cfg = yaml.safe_load(content)
                            if isinstance(cfg, dict) and cfg.get("name") in self.input_manifest["core_team"]:
                                manager_team_map = {info["manager"]: tk for tk, info in self.input_manifest["sub_teams"].items()}
                                agent_name = cfg["name"]
                                if agent_name in manager_team_map:
                                    team_key = manager_team_map[agent_name]
                                    wiring_func = f"run_{team_key}_team"
                                    if wiring_func not in cfg.get("domain_tools", []):
                                        cfg.setdefault("domain_tools", []).append(wiring_func)
                                        self.yaml_files[path] = yaml.dump(cfg, default_flow_style=False, allow_unicode=True)
                        except yaml.YAMLError:
                            pass
                # Generate tools.py with wiring functions
                core_agents = self.input_manifest["core_team"]
                base_tools = generate_sales_tools_py(core_agents)
                wiring_code = generate_wiring_tools(self.sub_team_dirs, self.input_manifest)
                self.generated_files["src/tools.py"] = base_tools + wiring_code

            # Format as architect output string
            architecture = "\n\n".join(
                f"### YAML: {path}\n```yaml\n{content}\n```"
                for path, content in self.yaml_files.items()
            )
            self.architect_output = architecture
            print(f"[ArchitectAgent] Generated {len(self.yaml_files)} YAML files, tools.py pre-generated")
        else:
            # CASCADE MODE: prepend existing architecture context
            if self.is_cascade:
                cascade_prefix = self._build_architect_cascade_prompt()
                arch_input = cascade_prefix + "\n\n" + arch_input
                print(f"[ArchitectAgent] CASCADE MODE — extending existing architecture ({elapsed()})")

            print(f"[ArchitectAgent] Designing YAML architecture... ({elapsed()})")
            architecture = await call_gpt4o_with_tools(
                AGENT_ROLES["ArchitectAgent"]["prompt"],
                arch_input,
                tools=AUTOGEN_RAG_TOOLS,
                max_tokens=4096
            )

            # Parse and store YAML blocks
            new_yaml_files = parse_yaml_blocks(architecture)
            if self.is_cascade:
                # Merge: new/changed YAMLs override, existing ones are kept
                self.yaml_files.update(new_yaml_files)
                # Update agents_total in project.yml if present
                if "project.yml" in self.yaml_files:
                    try:
                        proj = yaml.safe_load(self.yaml_files["project.yml"])
                        if isinstance(proj, dict):
                            agent_count = sum(1 for k in self.yaml_files if k.startswith("agents/"))
                            proj["agents_total"] = agent_count
                            self.yaml_files["project.yml"] = yaml.dump(proj, default_flow_style=False)
                    except yaml.YAMLError:
                        pass
                print(f"[ArchitectAgent] CASCADE MERGE: {len(new_yaml_files)} new/changed + {len(self.yaml_files) - len(new_yaml_files)} kept = {len(self.yaml_files)} total")
            else:
                self.yaml_files = new_yaml_files
            self.architect_output = architecture
        print(f"[ArchitectAgent] Parsed {len(self.yaml_files)} YAML files")

        # Human review: show architecture diagram
        graph = self._build_architecture_graph()
        if graph["nodes"]:
            answer = await ask_user(
                question_type="architecture_review",
                tool_name="ArchitectAgent",
                message=f"Review agent architecture for: {self.task_name}",
                metadata=graph,
                timeout=120,
            )
            if answer["action"] == "reject":
                print(f"[ArchitectAgent] User rejected architecture — continuing anyway (no regeneration in V1)")

        # Safety net: ensure project.yml has task field (LLM might forget)
        if "project.yml" in self.yaml_files:
            try:
                proj = yaml.safe_load(self.yaml_files["project.yml"])
                if isinstance(proj, dict) and "task" not in proj:
                    proj["task"] = self.task_name
                    self.yaml_files["project.yml"] = yaml.dump(proj, default_flow_style=False)
                    print("[ArchitectAgent] Injected missing 'task' field into project.yml")
            except yaml.YAMLError:
                pass

        post = await self.post_as(session, "ArchitectAgent",
                                  f"Architecture: {self.task_name}",
                                  f"## YAML Architecture\n\n{architecture}\n\n@CoderAgent your turn!",
                                  post_type="task", tags=["architecture", "yaml", "swarm"])

        self.completed_steps.add("ArchitectAgent")
        print(f"[ArchitectAgent] DONE ({elapsed()}) — posted YAML architecture")
        return architecture

    async def _poll_mention_or_done(self, session, agent_name):
        """Poll for @mention, but abort early if reviewer_done is set."""
        api_key = self.key(agent_name)
        start = time.time()
        while time.time() - start < STEP_TIMEOUT:
            # Check if reviewer already approved (no more revisions coming)
            if self.reviewer_done.is_set():
                return None
            try:
                notifications = await api_get(
                    session, "/api/v1/notifications",
                    api_key=api_key, params={"unread_only": "true"}
                )
                for notif in notifications:
                    if notif["type"] == "mention" and not notif["read"]:
                        post_id = notif.get("payload", {}).get("post_id")
                        comment_id = notif.get("payload", {}).get("comment_id")
                        await api_post(session, f"/api/v1/notifications/{notif['id']}/read",
                                       {}, api_key=api_key)
                        if comment_id:
                            post = await api_get(session, f"/api/v1/posts/{post_id}")
                            comments = await api_get(session, f"/api/v1/posts/{post_id}/comments")
                            comment_content = ""
                            for c in comments:
                                if c["id"] == comment_id:
                                    comment_content = c["content"]
                                    break
                            return {"post": post, "comment": comment_content, "post_id": post_id}
                        elif post_id:
                            post = await api_get(session, f"/api/v1/posts/{post_id}")
                            return {"post": post, "comment": None, "post_id": post_id}
            except Exception as e:
                print(f"  [{agent_name}] Poll error: {e}")
            await asyncio.sleep(POLL_INTERVAL)
        return None

    async def step_coder(self, session, max_activations=3):
        """CoderAgent: Generate code (may be called multiple times for revisions)."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"

        activations = 0
        self.reviewer_done.clear()  # Reset for each iteration

        while activations < max_activations:
            print(f"\n[CoderAgent] Waiting for @mention... ({elapsed()})")
            trigger = await self._poll_mention_or_done(session, "CoderAgent")
            if not trigger:
                if activations > 0:
                    break  # Normal exit after at least one activation (reviewer approved)
                if self.reviewer_done.is_set():
                    print("[CoderAgent] Reviewer approved — stopping")
                    break
                print("[CoderAgent] TIMEOUT — no trigger received")
                return None

            activations += 1

            # INPUT FILE MODE: tools.py is pre-generated by manifest, skip LLM
            # Wait for ArchitectAgent to finish populating generated_files (may have stale notifications)
            if self.is_input_file and activations == 1:
                for _ in range(60):  # Wait up to 30s for ArchitectAgent
                    if "src/tools.py" in self.generated_files:
                        break
                    await asyncio.sleep(0.5)
            if self.is_input_file and "src/tools.py" in self.generated_files and activations == 1:
                # Fix **kwargs before using (crashes autogen)
                self.generated_files["src/tools.py"] = _fix_kwargs_tools(self.generated_files["src/tools.py"])
                print(f"[CoderAgent] INPUT FILE MODE — tools.py pre-generated ({elapsed()})")
                tools_preview = self.generated_files["src/tools.py"][:3000]
                post = await self.post_as(session, "CoderAgent",
                                          f"Code: {self.task_name}",
                                          f"## Pre-generated Sales Tools (from manifest)\n\n"
                                          f"```python\n{tools_preview}\n```\n\n"
                                          f"**{len(self.generated_files['src/tools.py'])} chars** total in tools.py\n\n"
                                          f"@ReviewerAgent your turn!",
                                          post_type="code", tags=["code", "python", "swarm", "input-file"])
                self.code_post_id = post["id"]
                self.completed_steps.add("CoderAgent")
                print(f"[CoderAgent] Pre-generated tools.py posted ({elapsed()})")
                return

            # Build context: domain tools + MCP tools (main.py is auto-generated)
            tools_ctx = ("\n\n--- DOMAIN TOOLS (MUST include in tools.py) ---\n\n"
                         "You are generating ONLY src/tools.py. Do NOT generate main.py (it is auto-generated).\n"
                         "Do NOT generate Dockerfile, docker-compose.yml, or requirements.txt.\n\n"
                         "tools.py MUST contain REAL domain tools from the template:\n"
                         "- fetch_url, fetch_json_api: for data collection agents\n"
                         "- write_report, read_file, append_to_file: for file I/O\n"
                         "- parse_csv_data, extract_json_fields, validate_json: for data processing\n"
                         "- format_markdown_report: for report generation\n"
                         "- run_shell: for system commands\n"
                         "- claude_code: delegate code writing, review, or complex tasks to Claude Code CLI\n\n"
                         "CRITICAL: Tool function names MUST match the domain_tools names in agent.yml.\n"
                         "Copy ALL domain tool functions from the template into tools.py.\n")
            if self.mcp_tools_prompt:
                tools_ctx += (f"\n\n--- REAL MCP TOOLS (use EXACT names, in addition to domain tools) ---\n\n"
                              f"{self.mcp_tools_prompt}\n\n"
                              f"Include these MCP tools IN ADDITION to the domain tools above.\n")
            else:
                tools_ctx += ("\n\nNOTE: No MCP tools available. Use domain tools from the template.\n"
                              "Do NOT generate fake MCP tool wrappers.\n")

            if trigger.get("comment"):
                user_content = (f"REVISION REQUEST from ReviewerAgent:\n\n{trigger['comment']}\n\n"
                                f"Original code post:\n\n{trigger['post']['content']}\n\n"
                                f"YAML Architecture (for reference):\n\n{self.architect_output}"
                                f"{tools_ctx}")
                print(f"[CoderAgent] Applying revision {self.revision_count}... ({elapsed()})")
            elif self.is_cascade and not trigger.get("comment"):
                # CASCADE MODE: extend existing tools.py
                cascade_prefix = self._build_coder_cascade_prompt()
                user_content = (f"{cascade_prefix}\n\n"
                                f"NEW/CHANGED YAML ARCHITECTURE:\n\n{self.architect_output}\n\n"
                                f"Generate the COMPLETE src/tools.py — keep ALL existing functions, "
                                f"ADD new ones at the end for the new agents/features."
                                f"{tools_ctx}")
                print(f"[CoderAgent] CASCADE MODE — extending tools.py... ({elapsed()})")
            else:
                user_content = (f"YAML ARCHITECTURE TO IMPLEMENT:\n\n{self.architect_output}\n\n"
                                f"Generate ONLY src/tools.py for the agents defined in the YAML above. "
                                f"Do NOT generate main.py, Dockerfile, or docker-compose.yml."
                                f"{tools_ctx}")
                print(f"[CoderAgent] Generating tools.py from YAML... ({elapsed()})")

            code_output = await call_gpt4o_with_tools(
                AGENT_ROLES["CoderAgent"]["prompt"],
                user_content,
                tools=AUTOGEN_RAG_TOOLS,
                max_tokens=4096
            )

            post = await self.post_as(session, "CoderAgent",
                                      f"Code: {self.task_name}" + (f" (rev {self.revision_count})" if self.revision_count > 0 else ""),
                                      f"## Generated Code\n\n{code_output}\n\n@ReviewerAgent your turn!",
                                      post_type="code", tags=["code", "python", "swarm"])

            self.code_post_id = post["id"]
            new_files = parse_code_blocks(code_output)
            # CoderAgent should only produce code files, not YAML architecture.
            # During revisions, it sometimes emits YAML fragments that would
            # overwrite the complete YAML files from ArchitectAgent.
            new_files = {k: v for k, v in new_files.items()
                         if not k.endswith(('.yml', '.yaml'))}
            if new_files:
                # Fix truncated claude_code in tools.py before merging
                if "src/tools.py" in new_files:
                    new_files["src/tools.py"] = _fix_truncated_tools_py(new_files["src/tools.py"])
                # Merge: new files override, but keep existing files not in revision
                self.generated_files.update(new_files)
            # If revision produced 0 files, keep the previous set (don't clear)
            self.completed_steps.add("CoderAgent")
            print(f"[CoderAgent] DONE ({elapsed()}) — posted {len(new_files)} files (total: {len(self.generated_files)})")

    async def step_reviewer(self, session):
        """ReviewerAgent: Review code, may loop back to CoderAgent."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"

        while True:
            print(f"\n[ReviewerAgent] Waiting for @mention... ({elapsed()})")
            trigger = await self.poll_mention(session, "ReviewerAgent")
            if not trigger:
                print("[ReviewerAgent] TIMEOUT")
                return

            # INPUT FILE MODE: tools.py is pre-generated and matches YAMLs, auto-approve
            # Wait for ArchitectAgent to populate generated_files (may have stale notifications)
            if self.is_input_file:
                for _ in range(60):
                    if "src/tools.py" in self.generated_files:
                        break
                    await asyncio.sleep(0.5)
            if self.is_input_file and "src/tools.py" in self.generated_files:
                print(f"[ReviewerAgent] INPUT FILE MODE — auto-APPROVED ({elapsed()})")
                # Wait briefly for CoderAgent to post (sets code_post_id)
                for _ in range(30):
                    if self.code_post_id:
                        break
                    await asyncio.sleep(0.5)
                if self.code_post_id:
                    await api_post(session, f"/api/v1/posts/{self.code_post_id}/comments",
                                   {"content": "APPROVED — pre-generated tools match manifest YAMLs.\n\n@TesterAgent your turn!"},
                                   api_key=self.key("ReviewerAgent"))
                else:
                    await self.post_as(session, "ReviewerAgent",
                                       f"Review: {self.task_name}",
                                       "APPROVED — pre-generated tools match manifest YAMLs.\n\n@TesterAgent your turn!",
                                       post_type="review", tags=["review", "approved", "input-file"])
                self.completed_steps.add("ReviewerAgent")
                self.reviewer_done.set()
                return

            print(f"[ReviewerAgent] Reviewing YAML+code consistency... ({elapsed()})")
            review_input = (f"{trigger['post']['content']}\n\n"
                           f"--- YAML ARCHITECTURE (for cross-reference) ---\n\n"
                           f"{self.architect_output}")
            review = await call_gpt4o_with_tools(
                AGENT_ROLES["ReviewerAgent"]["prompt"],
                review_input,
                tools=AUTOGEN_RAG_TOOLS
            )

            # Safety: if CoderAgent never posted (code_post_id is None), post as new post
            if not self.code_post_id:
                print(f"[ReviewerAgent] WARNING: No code post to comment on, posting as standalone")
                await self.post_as(session, "ReviewerAgent",
                                   f"Review: {self.task_name}",
                                   f"## Review\n\n{review}\n\n@TesterAgent your turn!",
                                   post_type="review", tags=["review", "swarm"])
                self.completed_steps.add("ReviewerAgent")
                self.reviewer_done.set()  # Signal CoderAgent to stop waiting
                return

            if "NEEDS_REVISION" in review and self.revision_count < MAX_REVISIONS:
                self.revision_count += 1
                # Post review as comment on the code post, @mention CoderAgent
                await self.comment_as(session, "ReviewerAgent", self.code_post_id,
                                      f"{review}\n\n@CoderAgent please fix these issues!")
                print(f"[ReviewerAgent] NEEDS_REVISION ({self.revision_count}/{MAX_REVISIONS}) ({elapsed()})")
                # Wait for CoderAgent to post new code, then we'll get mentioned again
                continue
            else:
                # PASS (or max revisions reached)
                if self.revision_count >= MAX_REVISIONS and "NEEDS_REVISION" in review:
                    review = review.replace("NEEDS_REVISION", "PASS (max revisions reached)")

                await self.comment_as(session, "ReviewerAgent", self.code_post_id,
                                      f"{review}\n\nAPPROVED. @TesterAgent your turn!")
                self.completed_steps.add("ReviewerAgent")
                self.reviewer_done.set()  # Signal CoderAgent to stop waiting
                print(f"[ReviewerAgent] APPROVED ({elapsed()})")
                return

    async def step_tester(self, session):
        """TesterAgent: Run automated tests, then post results."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[TesterAgent] Waiting for @mention... ({elapsed()})")

        trigger = await self.poll_mention(session, "TesterAgent")
        if not trigger:
            print("[TesterAgent] TIMEOUT")
            return

        print(f"[TesterAgent] Running tests... ({elapsed()})")

        # Run automated tests (code + YAML)
        test_results = test_generated_code(self.generated_files, self.yaml_files)

        # Format results for GPT-4o analysis
        test_summary = json.dumps(test_results, indent=2)
        all_tested = list(self.yaml_files.keys()) + list(self.generated_files.keys())
        analysis = await call_gpt4o(
            AGENT_ROLES["TesterAgent"]["prompt"],
            f"Automated test results:\n```json\n{test_summary}\n```\n\n"
            f"YAML files: {', '.join(self.yaml_files.keys())}\n"
            f"Code files: {', '.join(self.generated_files.keys())}"
        )

        post = await self.post_as(session, "TesterAgent",
                                  f"Test Results: {self.task_name}",
                                  f"## Test Results\n\n{analysis}\n\n"
                                  f"### Raw Results\n```json\n{test_summary}\n```\n\n"
                                  f"@ValidatorAgent your turn!",
                                  post_type="review", tags=["testing", "swarm"])

        self.completed_steps.add("TesterAgent")
        print(f"[TesterAgent] DONE ({elapsed()}) — {test_results['overall']}")

    async def step_validator(self, session):
        """ValidatorAgent: Final validation and output writing."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[ValidatorAgent] Waiting for @mention... ({elapsed()})")

        trigger = await self.poll_mention(session, "ValidatorAgent")
        if not trigger:
            print("[ValidatorAgent] TIMEOUT")
            return

        print(f"[ValidatorAgent] Validating... ({elapsed()})")

        # Check if we have files to write
        if not self.generated_files:
            await self.post_as(session, "ValidatorAgent",
                               f"Validation FAILED: {self.task_name}",
                               "No generated files found. Pipeline failed.",
                               tags=["failed", "swarm"])
            print(f"[ValidatorAgent] FAILED — no files")
            return

        # Build cascade_meta if in cascade mode
        cascade_meta = None
        if self.is_cascade:
            ctx = self.cascade_ctx
            new_history = list(ctx.cascade_history)
            new_history.append(self.cascade_feature or self.task_name)
            cascade_meta = {
                "iteration": ctx.iteration_number + 1,
                "feature": self.cascade_feature,
                "source_dir": str(ctx.source_dir),
                "cascade_history": new_history,
            }

        # Write output (YAML architecture + Python code)
        self.output_path = write_output(self.task_name, self.generated_files, self.yaml_files,
                                        cascade_meta=cascade_meta, team_key=self.input_team_key)

        # GPT-4o summary
        summary = await call_gpt4o(
            AGENT_ROLES["ValidatorAgent"]["prompt"],
            f"Test report:\n{trigger['post']['content']}\n\n"
            f"Generated files: {', '.join(self.generated_files.keys())}\n"
            f"Output path: {self.output_path}"
        )

        all_files = list(self.yaml_files.keys()) + list(self.generated_files.keys())
        await self.post_as(session, "ValidatorAgent",
                           f"VALIDATED: {self.task_name}",
                           f"## Validation Complete\n\n{summary}\n\n"
                           f"**Output:** `{self.output_path}`\n"
                           f"**YAML:** {', '.join(sorted(self.yaml_files.keys()))}\n"
                           f"**Code:** {', '.join(sorted(self.generated_files.keys()))}\n\n"
                           f"@BuilderAgent your turn!",
                           tags=["validated", "complete", "swarm"])

        self.completed_steps.add("ValidatorAgent")
        print(f"[ValidatorAgent] DONE ({elapsed()}) — output written")

    async def step_builder(self, session):
        """BuilderAgent: Docker build as functional test + MCP Gateway + Gordon auto-fix."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[BuilderAgent] Waiting for @mention... ({elapsed()})")

        trigger = await self.poll_mention(session, "BuilderAgent")
        if not trigger:
            print("[BuilderAgent] TIMEOUT")
            return

        if not self.output_path:
            await self.post_as(session, "BuilderAgent",
                               f"Build SKIPPED: {self.task_name}",
                               "No output path from ValidatorAgent. Skipping build.\n\n"
                               "@OutputEvalAgent your turn!",
                               tags=["build", "skipped", "swarm"])
            self.completed_steps.add("BuilderAgent")
            return

        # Reuse MCP servers already enabled by CatalogAgent
        mcp_enabled = self.mcp_enabled or []
        if not mcp_enabled:
            # Fallback: try to extract from YAML files
            mcp_server_names = []
            for filepath, content in self.yaml_files.items():
                if filepath.startswith("mcp_servers/") and filepath.endswith(".yml"):
                    try:
                        parsed = yaml.safe_load(content)
                        if isinstance(parsed, dict) and "name" in parsed:
                            mcp_server_names.append(parsed["name"])
                    except yaml.YAMLError:
                        pass
            if mcp_server_names:
                print(f"[BuilderAgent] Enabling {len(mcp_server_names)} MCP servers (fallback): {mcp_server_names} ({elapsed()})")
                mcp_result = await enable_mcp_servers(mcp_server_names)
                mcp_enabled = mcp_result.get("enabled", [])
        else:
            print(f"[BuilderAgent] Using {len(mcp_enabled)} servers from CatalogAgent: {mcp_enabled}")

        # Start MCP Gateway for enabled servers
        gateway_status = {"status": "SKIP"}
        if mcp_enabled:
            print(f"[BuilderAgent] Starting MCP Gateway for: {mcp_enabled} ({elapsed()})")
            gateway_status = await start_mcp_gateway(mcp_enabled)
            print(f"[BuilderAgent] Gateway: {gateway_status['status']}")

        # Prepare Docker context and build
        print(f"[BuilderAgent] Preparing Docker context... ({elapsed()})")
        self.build_dir = prepare_docker_context(Path(self.output_path))

        print(f"[BuilderAgent] Running docker compose build... ({elapsed()})")
        self.build_result = await docker_build_test(self.build_dir)

        # Gordon auto-fix loop if build fails
        gordon_fixes = ""
        if self.build_result["status"] == "FAIL":
            print(f"[BuilderAgent] Build FAILED — invoking Gordon AI for auto-fix... ({elapsed()})")
            fixed = await gordon_fix_and_rebuild(
                self.build_dir, self.build_result["output"])
            if fixed:
                gordon_fixes = "Gordon auto-fix: Build recovered after adding missing dependencies.\n"
                self.build_result = fixed

        # LLM analysis of build result
        analysis = await call_gpt4o(
            AGENT_ROLES["BuilderAgent"]["prompt"],
            f"## Build Result\n\nStatus: {self.build_result['status']}\n"
            f"Duration: {self.build_result['duration']:.1f}s\n\n"
            f"### Output\n```\n{self.build_result['output'][-3000:]}\n```\n\n"
            f"### Files in build context\n{', '.join(os.listdir(self.build_dir)) if self.build_dir and self.build_dir.exists() else 'N/A'}\n\n"
            f"### MCP Gateway\n{gateway_status}\n\n"
            f"{gordon_fixes}"
        )

        next_agent = "@ExecutorAgent" if self.build_result["status"] == "PASS" else "@OutputEvalAgent"
        await self.post_as(session, "BuilderAgent",
                           f"Build {self.build_result['status']}: {self.task_name}",
                           f"## Docker Build Results\n\n{analysis}\n\n"
                           f"**Status:** {self.build_result['status']}\n"
                           f"**Duration:** {self.build_result['duration']:.1f}s\n"
                           f"**MCP Gateway:** {gateway_status['status']}\n\n"
                           f"{gordon_fixes}"
                           f"{next_agent} your turn!",
                           post_type="review", tags=["build", "docker", "swarm"])

        self.completed_steps.add("BuilderAgent")
        print(f"[BuilderAgent] DONE ({elapsed()}) — build {self.build_result['status']}")

    async def step_executor(self, session):
        """ExecutorAgent: Docker run + Gordon auto-fix loop for runtime failures."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[ExecutorAgent] Waiting for @mention... ({elapsed()})")

        trigger = await self.poll_mention(session, "ExecutorAgent")
        if not trigger:
            print("[ExecutorAgent] TIMEOUT")
            return

        # Skip if build failed
        if self.build_result and self.build_result["status"] == "FAIL":
            await self.post_as(session, "ExecutorAgent",
                               f"Execution SKIPPED: {self.task_name}",
                               "Build failed — skipping execution.\n\n@OutputEvalAgent your turn!",
                               tags=["execution", "skipped", "swarm"])
            self.completed_steps.add("ExecutorAgent")
            print(f"[ExecutorAgent] SKIPPED — build failed ({elapsed()})")
            return

        if not self.build_dir:
            await self.post_as(session, "ExecutorAgent",
                               f"Execution SKIPPED: {self.task_name}",
                               "No build directory. Skipping.\n\n@OutputEvalAgent your turn!",
                               tags=["execution", "skipped", "swarm"])
            self.completed_steps.add("ExecutorAgent")
            return

        print(f"[ExecutorAgent] Running docker compose up... ({elapsed()})")
        run_timeout = 900 if self.is_input_file else 300
        self.run_result = await docker_run_test(self.build_dir, timeout=run_timeout)

        # Gordon auto-fix loop if run fails
        gordon_fixes = ""
        if self.run_result["status"] == "FAIL":
            # Print last 500 chars of run logs for debugging
            run_logs = self.run_result.get("logs", "")
            print(f"[ExecutorAgent] Run logs (last 500 chars):\n{run_logs[-500:]}")
            print(f"[ExecutorAgent] Run FAILED — invoking Gordon AI for auto-fix... ({elapsed()})")
            fixed = await gordon_fix_and_rerun(
                self.build_dir, self.run_result["logs"])
            if fixed:
                gordon_fixes = "Gordon auto-fix: Runtime recovered after fixing dependencies.\n"
                self.build_result = fixed["build"]
                self.run_result = fixed["run"]

        # LLM analysis of run result
        analysis = await call_gpt4o(
            AGENT_ROLES["ExecutorAgent"]["prompt"],
            f"## Execution Result\n\nStatus: {self.run_result['status']}\n"
            f"Duration: {self.run_result['duration']:.1f}s\n\n"
            f"### Container Logs\n```\n{self.run_result['logs'][-3000:]}\n```\n\n"
            f"{gordon_fixes}"
        )

        await self.post_as(session, "ExecutorAgent",
                           f"Execution {self.run_result['status']}: {self.task_name}",
                           f"## Docker Execution Results\n\n{analysis}\n\n"
                           f"**Status:** {self.run_result['status']}\n"
                           f"**Duration:** {self.run_result['duration']:.1f}s\n\n"
                           f"{gordon_fixes}"
                           f"@OutputEvalAgent your turn!",
                           post_type="review", tags=["execution", "docker", "swarm"])

        self.completed_steps.add("ExecutorAgent")
        print(f"[ExecutorAgent] DONE ({elapsed()}) — run {self.run_result['status']}")

    # --- OutputEvalAgent helpers ---

    def _build_team_info(self) -> str:
        """Build a summary of team capabilities from YAML files for OutputEvalAgent."""
        info = ""
        for path, content in self.yaml_files.items():
            if "project.yml" in path:
                info += f"### project.yml\n```yaml\n{content}\n```\n\n"
        for path, content in self.yaml_files.items():
            if "agent.yml" in path:
                info += f"### {path}\n```yaml\n{content}\n```\n\n"
        # Add available tools from tools.py
        if "src/tools.py" in self.generated_files:
            tools_code = self.generated_files["src/tools.py"]
            funcs = re.findall(r'(?:async )?def (\w+)\(.*?\).*?"""(.*?)"""', tools_code, re.DOTALL)
            if funcs:
                info += "### Available Tools\n"
                for name, doc in funcs:
                    if not name.startswith("_"):
                        info += f"- `{name}()`: {doc.strip().splitlines()[0]}\n"
        return info

    async def _call_claude_code(self, prompt: str) -> str:
        """Call LLM for reasoning/code generation. Uses GPT-5.4 API directly (reliable),
        falls back to Claude CLI if available."""
        try:
            # Primary: use GPT-5.4 API directly — always available, no CLI needed
            result = await call_gpt4o(
                "You are an expert Python developer and systems architect. "
                "Follow instructions precisely and return only what is requested.",
                prompt, max_tokens=4000)
            if result and not result.lower().startswith("error"):
                return result
        except Exception:
            pass
        # Fallback: Claude CLI (may not be available or may fail in nested sessions)
        try:
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            import shutil as _shutil
            claude_bin = _shutil.which("claude") or "claude"
            args = [claude_bin, "-p", prompt, "--output-format", "text"]
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0:
                return stdout.decode().strip()
            return f"Error: {stderr.decode()[:500]}"
        except FileNotFoundError:
            return "Error: claude CLI not found"
        except asyncio.TimeoutError:
            return "Error: Claude CLI timed out"
        except Exception as e:
            return f"Error: {e}"

    async def step_output_eval(self, session):
        """OutputEvalAgent: Run the agent team with a concrete test task via Claude CLI,
        evaluate output quality, write evaluation_report.md."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[OutputEvalAgent] Waiting for @mention... ({elapsed()})")

        trigger = await self.poll_mention(session, "OutputEvalAgent")
        if not trigger:
            print("[OutputEvalAgent] TIMEOUT")
            return

        # Skip if build/run failed
        if not (self.build_result and self.build_result["status"] == "PASS"
                and self.run_result and self.run_result["status"] == "PASS"):
            print(f"[OutputEvalAgent] SKIPPED — build/run not PASS ({elapsed()})")
            self.output_eval = {"status": "FAIL", "reason": "Build/run did not pass"}
            await self.post_as(session, "OutputEvalAgent",
                               f"Output Eval SKIPPED: {self.task_name}",
                               "Build or run failed — cannot evaluate output.\n\n"
                               "@EvalReporterAgent your turn!",
                               tags=["eval", "skipped", "swarm"])
            self.completed_steps.add("OutputEvalAgent")
            return

        if not self.build_dir:
            self.output_eval = {"status": "FAIL", "reason": "No build directory"}
            self.completed_steps.add("OutputEvalAgent")
            return

        # 1. Read team capabilities from YAML files
        team_info = self._build_team_info()

        # 2. Use Claude CLI to generate a concrete test task
        print(f"[OutputEvalAgent] Generating edge-case test task via Claude CLI... ({elapsed()})")
        test_task_prompt = (
            f"You are evaluating an AutoGen multi-agent team.\n\n"
            f"## Team Capabilities\n{team_info}\n\n"
            f"Design ONE concrete, specific test task for this team that:\n"
            f"- Uses the team's actual tools (listed above)\n"
            f"- Requires real work (create files, write code, use git)\n"
            f"- Produces output files in /app/output/\n"
            f"- Can complete in under 30 agent messages\n\n"
            f"Respond with ONLY the task text, no explanation. "
            f"The task must be a single paragraph, actionable instruction."
        )
        test_task = await self._call_claude_code(test_task_prompt)
        if not test_task or test_task.lower().startswith("error"):
            # Fallback: generate test task via GPT-4o
            test_task = await call_gpt4o(
                AGENT_ROLES["OutputEvalAgent"]["prompt"], team_info, max_tokens=500)
        if not test_task:
            test_task = f"Run the agent team with their default task and produce output files in /app/output/"
        else:
            # Extract TEST_TASK line if present
            for line in test_task.splitlines():
                if line.strip().startswith("TEST_TASK:"):
                    test_task = line.split(":", 1)[1].strip()
                    break

        print(f"[OutputEvalAgent] Test task: {test_task[:100]}... ({elapsed()})")

        # 3. Run the agent team with the test task via docker compose run
        print(f"[OutputEvalAgent] Running agent team with test task... ({elapsed()})")
        # Clear previous output
        output_dir = self.build_dir / "output"
        if output_dir.exists():
            for f in output_dir.iterdir():
                if f.is_file():
                    f.unlink()

        eval_timeout = 900 if self.is_input_file else 300
        eval_run = await docker_run_test_with_args(
            self.build_dir, args=["python", "main.py", test_task], timeout=eval_timeout)

        # 4. Read output files
        output_files = {}
        if output_dir.exists():
            for f in output_dir.rglob("*"):
                if f.is_file() and f.stat().st_size > 0:
                    try:
                        content = f.read_text(encoding="utf-8", errors="replace")[:3000]
                        output_files[f.name] = content
                    except Exception:
                        pass

        # 4b. Validate output files exist and have substance
        total_chars = sum(len(v) for v in output_files.values())
        if not output_files or total_chars < 200:
            reason = "No output files produced" if not output_files else f"Output too small ({total_chars} chars)"
            print(f"[OutputEvalAgent] FAIL — {reason}")
            self.output_eval = {
                "status": "FAIL", "reason": reason, "score": "1",
                "test_task": test_task, "files": list(output_files.keys()),
                "total_chars": total_chars,
                "eval_run_status": eval_run["status"],
                "eval_run_duration": eval_run.get("duration", 0),
            }
            post = await self.post_as(session, "OutputEvalAgent",
                f"Evaluation: FAIL — {reason}", reason)
            return

        # 5. Evaluate with Claude CLI
        print(f"[OutputEvalAgent] Evaluating output quality... ({elapsed()})")
        files_summary = ""
        for name, content in output_files.items():
            files_summary += f"\n### {name}\n```\n{content[:1500]}\n```\n"

        eval_prompt = (
            f"Evaluate this agent team's output.\n\n"
            f"## Test Task\n{test_task}\n\n"
            f"## Run Status: {eval_run['status']}\n"
            f"## Run Duration: {eval_run['duration']:.1f}s\n\n"
            f"## Output Files ({len(output_files)} files)\n{files_summary}\n\n"
            f"## Container Logs (last 2000 chars)\n```\n{eval_run['logs'][-2000:]}\n```\n\n"
            f"Evaluate STRICTLY:\n"
            f"1. Did agents produce task-SPECIFIC output? (not generic filler that could apply to any input)\n"
            f"2. Did agents use their tools effectively?\n"
            f"3. Is the output complete and useful?\n"
            f"4. Do ALL output files contain substantive content (not just headers/templates)?\n"
            f"5. Does the output directly address the test task with specific data/names/details?\n\n"
            f"IMPORTANT: If output is generic boilerplate or contains no task-specific data, VERDICT: FAIL.\n"
            f"If any file mentioned in logs was not actually produced, VERDICT: FAIL.\n\n"
            f"Respond with EXACTLY this format:\n"
            f"VERDICT: PASS or FAIL\n"
            f"SCORE: 1-10\n"
            f"SUMMARY: 2-3 sentences explaining the evaluation\n"
            f"STRENGTHS: What worked well\n"
            f"WEAKNESSES: What needs improvement"
        )
        eval_result = await self._call_claude_code(eval_prompt)
        if not eval_result or eval_result.lower().startswith("error"):
            eval_result = await call_gpt4o(
                "Evaluate agent team output quality.", eval_prompt, max_tokens=1000)

        # Parse verdict — strict: only exact "PASS", and score must be >= 6
        verdict_pass = False
        score = "?"
        score_int = 0
        summary = ""
        for line in eval_result.splitlines():
            upper = line.strip().upper()
            if upper.startswith("VERDICT:"):
                v = upper.split(":", 1)[1].strip()
                verdict_pass = (v == "PASS")  # Exact match only, not "PASS BUT..."
            elif upper.startswith("SCORE:"):
                score = line.split(":", 1)[1].strip()
                try:
                    score_int = int(re.search(r'\d+', score).group())
                except (AttributeError, ValueError):
                    score_int = 0
            elif upper.startswith("SUMMARY:"):
                summary = line.split(":", 1)[1].strip()
        # Require both verdict PASS and score >= 6
        is_pass = verdict_pass and score_int >= 6
        if verdict_pass and score_int < 6:
            print(f"[OutputEvalAgent] Verdict PASS but score {score_int} < 6 — overriding to FAIL")

        self.output_eval = {
            "status": "PASS" if is_pass else "FAIL",
            "reason": summary,
            "score": score,
            "test_task": test_task,
            "files": list(output_files.keys()),
            "total_chars": sum(len(v) for v in output_files.values()),
            "eval_run_status": eval_run["status"],
            "eval_run_duration": eval_run.get("duration", 0),
        }

        # 6. Write evaluation_report.md to output
        report = (
            f"# Evaluation Report\n\n"
            f"## Test Task\n{test_task}\n\n"
            f"## Verdict: {'PASS' if is_pass else 'FAIL'} (Score: {score})\n\n"
            f"## Evaluation\n{eval_result}\n\n"
            f"## Output Files\n"
            + "\n".join(f"- {name} ({len(content)} chars)" for name, content in output_files.items())
            + f"\n\n## Run Details\n"
            f"- Status: {eval_run['status']}\n"
            f"- Duration: {eval_run['duration']:.1f}s\n"
            f"- Container Logs:\n```\n{eval_run['logs'][-1500:]}\n```\n"
        )
        if self.output_path:
            report_dir = Path(self.output_path) / "output"
            report_dir.mkdir(exist_ok=True)
            (report_dir / "evaluation_report.md").write_text(report, encoding="utf-8")
            print(f"[OutputEvalAgent] Written evaluation_report.md")

        # Copy output files to standalone output dir
        if is_pass and output_files and self.output_path:
            standalone_output = Path(self.output_path) / "output"
            standalone_output.mkdir(exist_ok=True)
            for name in output_files:
                src = output_dir / name
                if src.exists():
                    shutil.copy2(src, standalone_output / name)

        status_str = f"PASS (Score: {score})" if is_pass else f"FAIL (Score: {score})"
        print(f"[OutputEvalAgent] {status_str} — {summary} ({elapsed()})")

        await self.post_as(session, "OutputEvalAgent",
                           f"Output Eval {status_str}: {self.task_name}",
                           f"## Output Evaluation Report\n\n"
                           f"**Test Task:** {test_task}\n\n"
                           f"**Verdict:** {status_str}\n\n"
                           f"{eval_result}\n\n"
                           f"**Output Files:** {', '.join(output_files.keys()) or 'None'}\n\n"
                           f"@EvalReporterAgent your turn!",
                           post_type="review", tags=["eval", "output", "swarm"])

        self.completed_steps.add("OutputEvalAgent")

    async def step_todo_implement(self, session):
        """Scan tools.py for TODO-marked mock tools and replace with real implementations."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[TodoImplementer] Scanning for TODO tools... ({elapsed()})")

        if not self.build_dir:
            print("[TodoImplementer] No build directory — skipping")
            return

        tools_py_path = self.build_dir / "src" / "tools.py"
        if not tools_py_path.exists():
            print("[TodoImplementer] No tools.py found — skipping")
            return

        # Quick check: any TODOs at all?
        tools_content = tools_py_path.read_text(encoding="utf-8")
        todos = await scan_todo_tools(tools_content)
        if not todos:
            print("[TodoImplementer] No TODO-marked tools found — skipping")
            return

        print(f"[TodoImplementer] Found {len(todos)} TODO tools, implementing via Claude CLI...")

        result = await implement_todos(
            tools_py_path, self._call_claude_code, gpt4o_fn=call_gpt4o, max_tools=10
        )

        status_parts = []
        if result["implemented"]:
            status_parts.append(f"{len(result['implemented'])} implemented")
        if result["failed"]:
            status_parts.append(f"{len(result['failed'])} failed")
        if result["skipped"]:
            status_parts.append(f"{len(result['skipped'])} skipped")
        status = ", ".join(status_parts) or "no changes"
        print(f"[TodoImplementer] Done: {status} ({elapsed()})")

        # If tools were updated, rebuild and rerun to verify
        if result["tools_py_updated"]:
            print(f"[TodoImplementer] Rebuilding with updated tools... ({elapsed()})")
            # Also update the in-memory generated_files
            self.generated_files["src/tools.py"] = tools_py_path.read_text(encoding="utf-8")

            build_result = await docker_build_test(self.build_dir)
            if build_result["status"] == "PASS":
                print(f"[TodoImplementer] Rebuild PASS ({elapsed()})")
                run_result = await docker_run_test(self.build_dir)
                print(f"[TodoImplementer] Rerun: {run_result['status']} ({elapsed()})")
                if run_result["status"] == "PASS":
                    self.todo_implemented = True
                    # Re-eval with real tools (post-TODO eval = "validated" baseline)
                    print(f"[TodoImplementer] Running post-TODO eval... ({elapsed()})")
                    await self.step_output_eval(session)
                    self.output_eval["eval_mode"] = "post_todo"
                    print(f"[TodoImplementer] Post-TODO eval: {self.output_eval.get('status')} ({elapsed()})")
            else:
                print(f"[TodoImplementer] Rebuild FAIL — reverting tools.py ({elapsed()})")
                # Revert to original
                tools_py_path.write_text(tools_content, encoding="utf-8")
                result["tools_py_updated"] = False

        # Post summary to Minibook (non-critical)
        try:
            if self.project_id:
                impl_list = ", ".join(result["implemented"]) if result["implemented"] else "none"
                fail_list = ", ".join(f["name"] for f in result["failed"]) if result["failed"] else "none"
                await self.post_as(session, "OutputEvalAgent",
                    f"TODO Tool Implementation: {self.task_name}",
                    f"## TODO Tool Implementation Report\n\n"
                    f"**Implemented:** {impl_list}\n"
                    f"**Failed:** {fail_list}\n"
                    f"**Tools.py updated:** {result['tools_py_updated']}\n",
                    tags=["todo", "tools", "swarm"])
        except Exception as e:
            print(f"[TodoImplementer] Could not post to Minibook: {e}")

    async def step_toolforge(self, session):
        """ToolForgeAgent: Generate custom MCP servers for unimplemented tools."""
        import re
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[ToolForgeAgent] Scanning for unimplemented tools... ({elapsed()})")

        tools_py = self.generated_files.get("src/tools.py", "")
        if not tools_py:
            print("[ToolForgeAgent] SKIP - no tools.py")
            return

        # Find unimplemented functions
        unimplemented = []
        for match in re.finditer(r'async def (\w+)\(([^)]*)\)[^:]*:.*?(?:\n(?=\S)|\Z)', tools_py, re.DOTALL):
            name = match.group(1)
            body = match.group(0)
            if name.startswith("_"):
                continue
            if any(marker in body for marker in ["# TODO", "not implemented", "NotImplementedError", "return.*Error"]):
                unimplemented.append({"name": name, "params": match.group(2), "body": body[:300]})

        if not unimplemented:
            print("[ToolForgeAgent] All tools implemented - nothing to forge")
            self.completed_steps.add("ToolForgeAgent")
            return

        print(f"[ToolForgeAgent] Found {len(unimplemented)} unimplemented: {[t['name'] for t in unimplemented]}")

        team_slug = self.task_name.replace(" ", "_").lower()[:30]
        forged = []

        for tool_info in unimplemented:
            server_name = f"vibemind_mcp_{team_slug}_{tool_info['name']}"

            # Fetch API context via web_fetch if available
            api_context = ""
            try:
                from spaces.autogen.mcp_server.web_fetch_pipe import WebFetchPipe
                pipe = WebFetchPipe()
                api_context = await pipe.enrich_coder_context(
                    f"Implement {tool_info['name']}: {tool_info['body'][:200]}"
                )
            except Exception:
                pass

            # LLM generates MCP server
            prompt = f"Generate a FastAPI MCP server for tool '{tool_info['name']}' with params ({tool_info['params']}). Hint: {tool_info['body'][:200]}"
            if api_context:
                prompt += f"\n\nAPI Documentation:\n{api_context[:2000]}"

            code = await call_gpt4o(
                AGENT_ROLES["ToolForgeAgent"]["prompt"],
                prompt, max_tokens=4096
            )

            # Extract server code
            server_code = code
            for block in parse_code_blocks(code).values():
                if "fastapi" in block.lower() or "app = " in block:
                    server_code = block
                    break

            self.generated_files[f"mcp_servers/{server_name}/server.py"] = server_code
            self.generated_files[f"mcp_servers/{server_name}/Dockerfile"] = (
                "FROM python:3.12-slim\nWORKDIR /app\n"
                "RUN pip install fastapi uvicorn httpx\n"
                "COPY server.py .\n"
                'CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8809"]'
            )
            self.generated_files[f"mcp_servers/{server_name}/requirements.txt"] = "fastapi>=0.100.0\nuvicorn>=0.23.0\nhttpx>=0.27.0\n"

            forged.append({"name": server_name, "tool": tool_info["name"]})
            print(f"  [ToolForge] Generated: {server_name}")

        # Post to Minibook
        if forged:
            await self.post_as(session, "ToolForgeAgent",
                f"Forged {len(forged)} MCP servers: {self.task_name}",
                "## Custom MCP Servers\n\n" + "\n".join(f"- `{s['name']}` for tool `{s['tool']}`" for s in forged),
                tags=["mcp", "forge"])

        self.completed_steps.add("ToolForgeAgent")
        print(f"[ToolForgeAgent] DONE ({elapsed()}) - forged {len(forged)} servers")

    async def step_feedback_loop(self, session, max_rounds=2):
        """FeedbackAgent: Run team, score output, improve if needed."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"

        if not self.output_path or not self.build_dir:
            print("[FeedbackAgent] SKIP - no output/build")
            return

        for round_num in range(max_rounds):
            print(f"\n[FeedbackAgent] Round {round_num + 1}/{max_rounds} ({elapsed()})")

            # 1. Generate test task
            test_prompt = f"Design ONE concrete test task for an agent team that does: {self.task_name}. The task should exercise the team's actual tools and produce output files."
            test_task = await call_gpt4o("You design test tasks.", test_prompt, max_tokens=500)
            print(f"  [Test] {test_task[:100]}...")

            # 2. Run team
            run_result = await docker_run_test_with_args(
                self.build_dir, ["python", "main.py", test_task], timeout=300
            )

            # 3. Score output
            output_summary = run_result.get("logs", "")[:2000]
            score_prompt = f"Test: {test_task}\nLogs:\n{output_summary}\n\nScore 1-10. VERDICT: PASS or NEEDS_IMPROVEMENT. List improvements."
            score_result = await call_gpt4o(
                AGENT_ROLES["FeedbackAgent"]["prompt"],
                score_prompt, max_tokens=1000
            )

            # Parse score
            score_match = re.search(r'SCORE:\s*(\d+)', score_result)
            score = int(score_match.group(1)) if score_match else 5
            print(f"  [Score] {score}/10")

            # Post to Minibook
            await self.post_as(session, "FeedbackAgent",
                f"Feedback Round {round_num + 1}: Score {score}/10",
                f"## Test\n{test_task[:200]}\n\n## Score: {score}/10\n\n{score_result}",
                tags=["feedback", "score"])

            if score >= 7:
                print(f"[FeedbackAgent] PASS - quality sufficient")
                break

            if round_num < max_rounds - 1:
                # Extract improvements and feed back to CoderAgent
                improvements = score_result.split("IMPROVEMENTS:")[-1] if "IMPROVEMENTS:" in score_result else score_result
                await self.comment_as(session, "FeedbackAgent", self.code_post_id or "",
                    f"Score {score}/10. Please fix:\n{improvements}\n\n@CoderAgent please improve.",
                )
                # Re-run coder + reviewer + validator + builder
                await self.step_coder(session)
                await self.step_reviewer(session)
                await self.step_validator(session)
                await self.step_builder(session)

        self.completed_steps.add("FeedbackAgent")
        print(f"[FeedbackAgent] DONE ({elapsed()})")

    async def step_eval_reporter(self, session):
        """EvalReporterAgent: Final evaluation report + Gateway cleanup."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[EvalReporterAgent] Waiting for @mention... ({elapsed()})")

        trigger = await self.poll_mention(session, "EvalReporterAgent")
        if not trigger:
            print("[EvalReporterAgent] TIMEOUT")
            await stop_mcp_gateway()
            return

        # Stop MCP Gateway (cleanup)
        await stop_mcp_gateway()

        # Compile all results
        build_status = self.build_result["status"] if self.build_result else "N/A"
        build_duration = f"{self.build_result['duration']:.1f}s" if self.build_result else "N/A"
        run_status = self.run_result["status"] if self.run_result else "N/A"
        run_duration = f"{self.run_result['duration']:.1f}s" if self.run_result else "N/A"
        total_time = f"{time.time() - self.start_time:.1f}s"

        # Output eval info
        oe = self.output_eval or {}
        oe_status = oe.get("status", "N/A")
        oe_score = oe.get("score", "N/A")
        oe_task = oe.get("test_task", "N/A")
        oe_reason = oe.get("reason", "N/A")

        report_input = (
            f"## Pipeline Summary\n\n"
            f"Task: {self.task_name}\n"
            f"Steps completed: {len(self.completed_steps)}/11\n"
            f"Revisions: {self.revision_count}\n"
            f"YAML files: {len(self.yaml_files)}\n"
            f"Code files: {len(self.generated_files)}\n"
            f"Total time: {total_time}\n\n"
            f"## Docker Build\n"
            f"Status: {build_status}, Duration: {build_duration}\n\n"
            f"## Docker Run\n"
            f"Status: {run_status}, Duration: {run_duration}\n\n"
            f"## Output Evaluation\n"
            f"Verdict: {oe_status}, Score: {oe_score}\n"
            f"Test Task: {oe_task}\n"
            f"Summary: {oe_reason}\n\n"
            f"## MCP Servers\n"
            f"{self.mcp_selection[:500] if self.mcp_selection else 'None selected'}\n\n"
            f"## Trigger Context\n{trigger['post']['content'][:1000]}"
        )

        print(f"[EvalReporterAgent] Generating final report... ({elapsed()})")
        report = await call_gpt4o(
            AGENT_ROLES["EvalReporterAgent"]["prompt"],
            report_input,
            max_tokens=2048
        )

        await self.post_as(session, "EvalReporterAgent",
                           f"EVAL REPORT: {self.task_name}",
                           f"## Final Evaluation Report\n\n{report}\n\n"
                           f"---\n"
                           f"**Build:** {build_status} ({build_duration})\n"
                           f"**Run:** {run_status} ({run_duration})\n"
                           f"**Output Eval:** {oe_status} (Score: {oe_score})\n"
                           f"**Pipeline:** {len(self.completed_steps)}/11 steps, {total_time}\n"
                           f"**Output:** `{self.output_path}`\n\n"
                           f"@ExportAgent — Pipeline complete, output at `{self.output_path}`.",
                           post_type="review", tags=["eval", "report", "swarm"])

        self.completed_steps.add("EvalReporterAgent")
        print(f"[EvalReporterAgent] DONE ({elapsed()}) — final report posted")

    async def step_export(self, session):
        """ExportAgent: Export validated output as a standalone git repo + push to GitHub."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[ExportAgent] Waiting for @mention... ({elapsed()})")

        trigger = await self.poll_mention(session, "ExportAgent")
        if not trigger:
            print("[ExportAgent] TIMEOUT — skipping export")
            return

        output_dir = self.output_path
        if not output_dir or not Path(output_dir).exists():
            await self.post_as(session, "ExportAgent",
                               f"Export: {self.task_name}",
                               "## Export Status: SKIP\n\n"
                               "**Reason:** No output directory available to export.",
                               post_type="review", tags=["export", "swarm"])
            print(f"[ExportAgent] SKIP — no output dir ({elapsed()})")
            return

        # Import export function (avoid circular import at module level)
        from autogen_swarm import export_agent_team

        print(f"[ExportAgent] Exporting {output_dir}... ({elapsed()})")
        try:
            exported = export_agent_team(str(output_dir), private=True)
            file_count = sum(1 for _ in exported.rglob("*") if _.is_file())

            # Try to get repo URL from git remote
            import subprocess
            remote = subprocess.run(["git", "remote", "get-url", "origin"],
                                    cwd=str(exported), capture_output=True, text=True)
            repo_url = remote.stdout.strip() if remote.returncode == 0 else "local only"

            await self.post_as(session, "ExportAgent",
                               f"Export: {self.task_name}",
                               f"## Export Status: SUCCESS\n\n"
                               f"**Repository:** {repo_url}\n"
                               f"**Files:** {file_count}\n"
                               f"**Local path:** `{exported}`\n"
                               f"**SETUP.md:** Included with quick start instructions.\n\n"
                               f"The agent team is ready to clone and run.",
                               post_type="review", tags=["export", "github", "swarm"])
            self.export_result = {"status": "SUCCESS", "path": str(exported), "repo_url": repo_url}
            print(f"[ExportAgent] DONE ({elapsed()}) — exported to {repo_url}")
        except Exception as e:
            await self.post_as(session, "ExportAgent",
                               f"Export: {self.task_name}",
                               f"## Export Status: FAIL\n\n"
                               f"**Reason:** {str(e)[:500]}\n\n"
                               f"Output is still available locally at `{output_dir}`.",
                               post_type="review", tags=["export", "swarm"])
            self.export_result = {"status": "FAIL", "reason": str(e)}
            print(f"[ExportAgent] FAIL ({elapsed()}) — {e}")

        self.completed_steps.add("ExportAgent")

    async def _evaluate_output_content(self, session) -> bool:
        """Check if the agent team produced meaningful output files after docker run.
        Reads output/ dir from build context, evaluates content quality via LLM.
        Returns True if output is meaningful, False if empty/garbage."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"
        print(f"\n[OutputEval] Checking output content quality... ({elapsed()})")

        if not self.build_dir:
            print("[OutputEval] No build dir — skipping")
            return True  # Don't block if no build dir

        output_dir = self.build_dir / "output"
        if not output_dir.exists():
            # Also check the standalone output path
            if self.output_path:
                output_dir = Path(self.output_path) / "output"

        if not output_dir.exists():
            print(f"[OutputEval] No output/ directory found — agents wrote no files")
            self.output_eval = {"status": "FAIL", "reason": "No output files produced"}
            return False

        # Collect all output files
        output_files = {}
        for f in output_dir.rglob("*"):
            if f.is_file() and f.stat().st_size > 0:
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")[:3000]
                    output_files[f.name] = content
                except Exception:
                    pass

        if not output_files:
            print(f"[OutputEval] Output directory is empty — no files written")
            self.output_eval = {"status": "FAIL", "reason": "Output directory empty"}
            return False

        total_chars = sum(len(v) for v in output_files.values())
        file_list = ", ".join(output_files.keys())
        print(f"[OutputEval] Found {len(output_files)} output files ({total_chars} chars): {file_list}")

        # Minimum content check (no LLM needed for obvious failures)
        if total_chars < 100:
            print(f"[OutputEval] Output too short ({total_chars} chars) — likely placeholder")
            self.output_eval = {"status": "FAIL", "reason": f"Output too short: {total_chars} chars"}
            return False

        # LLM evaluation of output quality
        files_context = ""
        for name, content in output_files.items():
            files_context += f"\n### {name}\n```\n{content[:2000]}\n```\n"

        eval_result = await call_gpt4o(
            "You evaluate the OUTPUT of an AI agent team. The team was given a task and produced files.\n"
            "Judge if the output is MEANINGFUL and COMPLETE — not just placeholders or generic text.\n\n"
            "Respond with EXACTLY:\n"
            "VERDICT: PASS or FAIL\n"
            "REASON: One-line explanation\n\n"
            "PASS criteria: Output contains real, task-specific content (data, analysis, personalized text).\n"
            "FAIL criteria: Output is generic boilerplate, empty templates, or placeholder text.",
            f"## Task\n{self.task_name}\n\n## Output Files\n{files_context}"
        )

        is_pass = "VERDICT: PASS" in eval_result.upper() or "VERDICT:PASS" in eval_result.upper()
        reason = ""
        for line in eval_result.splitlines():
            if line.strip().upper().startswith("REASON:"):
                reason = line.split(":", 1)[1].strip()
                break

        self.output_eval = {
            "status": "PASS" if is_pass else "FAIL",
            "reason": reason,
            "files": list(output_files.keys()),
            "total_chars": total_chars,
            "eval_mode": "pre_todo",  # overwritten to "post_todo" after TodoImpl re-eval
        }

        if is_pass:
            print(f"[OutputEval] PASS — {reason} ({elapsed()})")
            # Copy output files to standalone output directory for persistence
            if self.output_path:
                standalone_output = Path(self.output_path) / "output"
                standalone_output.mkdir(exist_ok=True)
                for name, content in output_files.items():
                    dest = standalone_output / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    # Re-read full file (output_files may be truncated to 3000 chars)
                    src = output_dir / name
                    if src.exists():
                        shutil.copy2(src, dest)
                    else:
                        dest.write_text(content, encoding="utf-8")
                print(f"[OutputEval] Copied {len(output_files)} files to {standalone_output}")
        else:
            print(f"[OutputEval] FAIL — {reason} ({elapsed()})")
            # Post evaluation failure to Minibook for visibility
            await self.post_as(session, "ExecutorAgent",
                               f"Output Quality FAIL: {self.task_name}",
                               f"## Output Content Evaluation\n\n"
                               f"**VERDICT:** FAIL\n**Reason:** {reason}\n\n"
                               f"**Files:** {file_list}\n**Total chars:** {total_chars}\n\n"
                               f"The agent team ran successfully but produced low-quality output.\n"
                               f"Triggering code rework...",
                               tags=["output-eval", "fail", "swarm"])

        return is_pass

    async def _run_codegen_build_eval(self, session, iteration: int):
        """Run code generation → review → test → validate → build → execute → eval cycle.
        Returns True if Run PASS, False otherwise."""
        elapsed = lambda: f"{time.time() - self.start_time:.1f}s"

        if iteration == 0:
            # First iteration: normal flow — architect → coder → reviewer
            coder_task = asyncio.create_task(self.step_coder(session))
            reviewer_task = asyncio.create_task(self.step_reviewer(session))
            await self.step_architect(session)
            await coder_task
            await reviewer_task
        else:
            # Re-iteration: post error context as new CoderAgent task
            error_ctx = ""
            if self.output_eval and self.output_eval.get("status") == "FAIL":
                # Output quality failure — code ran but produced bad output
                error_ctx = (
                    f"OUTPUT QUALITY FAILURE: {self.output_eval.get('reason', 'Unknown')}\n"
                    f"Files produced: {self.output_eval.get('files', [])}\n"
                    f"Total chars: {self.output_eval.get('total_chars', 0)}\n\n"
                    f"The code ran successfully (exit code 0) but the agent team produced "
                    f"low-quality or incomplete output. The leader agent must FIRST hand off "
                    f"to subagents before doing its own work. Ensure handoffs are correct "
                    f"and MaxMessageTermination is high enough for all agents to complete."
                )
                if self.run_result and self.run_result.get("logs"):
                    error_ctx += f"\n\nLast run logs:\n{self.run_result['logs'][-1000:]}"
            elif self.run_result and self.run_result.get("logs"):
                # Extract last 1500 chars of run logs
                error_ctx = self.run_result["logs"][-1500:]
            elif self.build_result and self.build_result.get("output"):
                error_ctx = self.build_result["output"][-1500:]

            # Reset revision count for new iteration
            self.revision_count = 0

            # Post re-generation request from SwarmManager
            regen_content = (
                f"## ITERATION {iteration + 1}: Re-generate code\n\n"
                f"The previous generated code had issues during Docker execution.\n\n"
                f"### Error from previous run:\n```\n{error_ctx}\n```\n\n"
                f"### YAML Architecture (unchanged):\n\n{self.architect_output}\n\n"
                f"Fix the issues and generate COMPLETE, CORRECTED Python files.\n\n"
                f"@CoderAgent fix these issues and regenerate the code!"
            )
            await self.post_as(session, "SwarmManager",
                               f"Re-generation #{iteration + 1}: {self.task_name}",
                               regen_content,
                               post_type="task", tags=["iteration", "fix", "swarm"])

            # Run coder + reviewer for the re-iteration
            coder_task = asyncio.create_task(self.step_coder(session))
            reviewer_task = asyncio.create_task(self.step_reviewer(session))
            await coder_task
            await reviewer_task

        await self.step_tester(session)
        await self.step_validator(session)

        # Docker eval
        await self.step_builder(session)
        if self.build_result and self.build_result["status"] == "PASS":
            await self.step_executor(session)
            if not (self.run_result and self.run_result["status"] == "PASS"):
                return False
            # Build + Run passed; OutputEvalAgent handles quality check after iteration loop
            return True
        else:
            self.completed_steps.add("ExecutorAgent")
            print(f"[ExecutorAgent] SKIPPED — build did not pass ({elapsed()})")
            return False

    async def run(self, session, task_description, max_iterations=3):
        """Execute the full 11-agent swarm pipeline with iteration loop.
        Retries code generation → build → run up to max_iterations times until PASS."""
        success = False
        iteration = 0
        try:
            # Step 1: SwarmManager kicks off
            await self.step_swarm_manager(session, task_description)

            # Step 2: CatalogAgent discovers MCP servers + enables + inspects tools
            await self.step_catalog(session)

            # Steps 3-9: Code gen → build → run (with iteration loop)
            for iteration in range(max_iterations):
                if iteration > 0:
                    print(f"\n{'='*60}")
                    print(f"  ITERATION {iteration + 1}/{max_iterations} — Re-generating code")
                    print(f"{'='*60}")

                success = await self._run_codegen_build_eval(session, iteration)

                if success:
                    print(f"\n[Pipeline] Build + Run PASS on iteration {iteration + 1}")
                    break
                # Don't retry if Docker Engine itself is down (not a code issue)
                if self.build_result and self.build_result.get("docker_down"):
                    print(f"\n[Pipeline] Docker Engine is down — cannot retry (not a code issue)")
                    break
                elif iteration < max_iterations - 1:
                    print(f"\n[Pipeline] Iteration {iteration + 1} FAILED — will retry...")
                    # Clean up gateway before retry (step_builder will restart it)
                    await stop_mcp_gateway()
                else:
                    print(f"\n[Pipeline] All {max_iterations} iterations exhausted")

            # Step 10: OutputEvalAgent — concrete test task + evaluation (pre-TODO, mock tools)
            if success:
                await self.step_output_eval(session)
                self.pre_todo_eval = self.output_eval  # save pre-todo result

            # Step 10b: TODO Tool Implementation (after eval, regardless of result)
            if success:
                await self.step_todo_implement(session)

            # Step 12: ToolForgeAgent (generate custom MCP servers)
            await self.step_toolforge(session)

            # Step 12b: Re-build if new MCP servers were forged
            if any("mcp_servers/" in f for f in self.generated_files):
                print("\n[Pipeline] Re-building with forged MCP servers...")
                from .code_processing import write_output
                self.output_path = write_output(self.task_name, self.generated_files, self.yaml_files)
                self.build_result = await docker_build_test(self.build_dir)

            # Step 13: Feedback Loop
            if success and self.output_path:
                await self.step_feedback_loop(session, max_rounds=2)

            # Step 11: Final evaluation report
            await self.step_eval_reporter(session)

            # Step 12: Export to GitHub
            if success and self.output_path:
                await self.step_export(session)

        finally:
            # Always clean up MCP Gateway — prevents zombie docker processes
            await stop_mcp_gateway()

        # Summary
        total = time.time() - self.start_time
        build_status = self.build_result["status"] if self.build_result else "N/A"
        run_status = self.run_result["status"] if self.run_result else "N/A"
        print("\n" + "=" * 60)
        print(f"  AUTOGEN SWARM PIPELINE FINISHED")
        print(f"  Iterations: {iteration + 1}/{max_iterations}")
        print(f"  Steps: {len(self.completed_steps)}/11")
        print(f"  Revisions: {self.revision_count}")
        print(f"  YAML files: {len(self.yaml_files)}")
        print(f"  Code files: {len(self.generated_files)}")
        print(f"  Total files: {len(self.yaml_files) + len(self.generated_files)}")
        print(f"  MCP servers: {', '.join(self.mcp_enabled) if self.mcp_enabled else 'None'}")
        print(f"  MCP tools discovered: {sum(len(v) for v in self.mcp_server_tools.values())}")
        print(f"  Docker build: {build_status}")
        print(f"  Docker run: {run_status}")
        output_eval_status = self.output_eval["status"] if self.output_eval else "N/A"
        print(f"  Output eval: {output_eval_status}")
        export_status = self.export_result["status"] if self.export_result else "N/A"
        export_url = self.export_result.get("repo_url", "") if self.export_result else ""
        print(f"  Export: {export_status}{f' -> {export_url}' if export_url else ''}")
        print(f"  Time: {total:.1f}s")
        if self.output_path:
            print(f"  Output: {self.output_path}")
        print("=" * 60)
        return success
