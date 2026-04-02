#!/usr/bin/env python3
"""
AutoGen Swarm — Collaborative Agent System on Minibook

11 specialized agents collaborate via Minibook to generate complete,
validated AutoGen multi-agent scripts with Docker eval:

  SwarmManager -> CatalogAgent -> ArchitectAgent -> CoderAgent -> ReviewerAgent
  -> TesterAgent -> ValidatorAgent -> BuilderAgent -> ExecutorAgent
  -> OutputEvalAgent -> EvalReporterAgent

CatalogAgent discovers real MCP servers from Docker catalog.
ArchitectAgent selects conversation pattern (Swarm/Selector/RoundRobin/gRPC).
ReviewerAgent can loop back to CoderAgent (max 2 revisions).
ValidatorAgent writes validated output to disk.
BuilderAgent/ExecutorAgent run Docker build+run as functional test.
OutputEvalAgent uses Claude CLI to design+run a concrete test task and evaluate output.
EvalReporterAgent produces final evaluation report.
"""

import asyncio
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
import aiohttp

# --- Re-exports from swarm package (backward compatibility) ---
from swarm.constants import (
    CascadeContext, MINIBOOK_URL, OUTPUT_DIR, CREDS_FILE,
    FORGE_API_PORT, LLM_PROVIDER,
)
from swarm.knowledge import AGENT_ROLES, FORGE_AGENT_ROLES
from swarm.api_client import (
    api_post, api_get, load_credentials, save_credentials, register_agent,
    register_agent_in_registry,
)
from swarm.llm import call_gpt4o, call_gpt4o_json, call_gpt4o_with_tools
from swarm.docker_ops import stop_mcp_gateway
from swarm.code_processing import load_cascade_context, write_output
from swarm.pipeline import SwarmPipeline
from swarm.forge_agents import ForgeState, load_forge_state, save_forge_state
from swarm.forge_orchestrator import ForgeOrchestrator, ForgeAPI
from swarm.input_designer import InputDesignPipeline


# --- Setup ---

async def setup_agents(session: aiohttp.ClientSession) -> dict:
    """Register all swarm agents."""
    print("\n=== Registering Swarm Agents ===\n")
    creds = load_credentials()
    agents = {}
    for name in AGENT_ROLES:
        info = await register_agent(session, name, creds)
        agents[name] = info
    return agents


async def setup_project(session: aiohttp.ClientSession, agents: dict, project_name: str) -> str:
    """Create project and have all agents join."""
    print(f"\n=== Creating Project: {project_name} ===\n")

    # Use SwarmManager as lead if available, otherwise first agent
    lead_name = "SwarmManager" if "SwarmManager" in agents else next(iter(agents))
    lead_key = agents[lead_name]["api_key"]

    # Check existing
    projects = await api_get(session, "/api/v1/projects")
    for p in projects:
        if p["name"] == project_name:
            print(f"  [=] Project exists (id={p['id'][:8]}...)")
            return p["id"]

    project = await api_post(session, "/api/v1/projects",
                             {"name": project_name, "description": "AutoGen Swarm Collaboration"},
                             api_key=lead_key)
    project_id = project["id"]
    print(f"  [+] Created (id={project_id[:8]}...)")

    for name, info in agents.items():
        if name == lead_name:
            continue
        try:
            await api_post(session, f"/api/v1/projects/{project_id}/join",
                           {"role": "member"}, api_key=info["api_key"])
            print(f"  [+] {name} joined")
        except Exception as e:
            if "Already" in str(e):
                print(f"  [=] {name} already member")
            else:
                print(f"  [!] {name}: {e}")

    return project_id


# --- Cascade Mode ---

async def run_cascade(session, agents, project_id, base_task: str,
                      features: list[str], start_from: str | Path = None):
    """Run multiple pipeline iterations, each building on the previous output.

    Args:
        session: aiohttp session
        agents: registered agent dict
        project_id: Minibook project ID
        base_task: original task description
        features: list of features to add, one per iteration
        start_from: optional path to a previous output directory for first iteration
    """
    print("\n" + "=" * 70)
    print("  PIPELINE CASCADE — Iterative Improvement")
    print(f"  Base task: {base_task}")
    print(f"  Features: {len(features)}")
    if start_from:
        print(f"  Starting from: {start_from}")
    print("=" * 70)

    current_source = Path(start_from) if start_from else None

    for i, feature in enumerate(features, 1):
        print(f"\n{'=' * 60}")
        print(f"  CASCADE ITERATION {i}/{len(features)}: {feature}")
        print(f"{'=' * 60}")

        # Load context from previous output
        ctx = None
        if current_source and current_source.exists():
            try:
                ctx = load_cascade_context(current_source)
            except Exception as e:
                print(f"[Cascade] WARNING: Failed to load context from {current_source}: {e}")
                print("[Cascade] Running without cascade context for this iteration")

        # Create pipeline with cascade context
        task_for_iteration = f"{base_task} — {feature}" if ctx else base_task
        pipeline = SwarmPipeline(
            agents, project_id, task_for_iteration,
            cascade_from=ctx,
            cascade_feature=feature,
        )

        try:
            await pipeline.run(session, task_for_iteration)
        except Exception as e:
            print(f"[Cascade] ERROR in iteration {i}: {e}")
            print("[Cascade] Continuing with next feature (architecture may still be valid)...")

        # Use this iteration's output as source for next iteration
        if pipeline.output_path:
            current_source = pipeline.output_path
            print(f"[Cascade] Iteration {i} output: {current_source}")
        else:
            print(f"[Cascade] Iteration {i} produced no output — keeping previous source")

    print(f"\n{'=' * 70}")
    print(f"  CASCADE COMPLETE — {len(features)} iterations")
    if current_source:
        print(f"  Final output: {current_source}")
    print(f"{'=' * 70}")
    return current_source


# --- Checkpoint helpers ---

CHECKPOINT_FILE = "checkpoint.json"

def _load_checkpoint(checkpoint_dir: Path) -> dict | None:
    """Load checkpoint from previous run if it exists."""
    cp_path = checkpoint_dir / CHECKPOINT_FILE
    if cp_path.exists():
        try:
            data = json.loads(cp_path.read_text(encoding="utf-8"))
            print(f"[Checkpoint] Loaded from {cp_path}")
            return data
        except Exception as e:
            print(f"[Checkpoint] Failed to load {cp_path}: {e}")
    return None


def _save_checkpoint(checkpoint_dir: Path, state: dict):
    """Persist checkpoint state to disk."""
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    cp_path = checkpoint_dir / CHECKPOINT_FILE
    state["updated_at"] = datetime.now().isoformat()
    cp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _print_status_table(state: dict):
    """Print a live status table of all teams."""
    print(f"\n{'-' * 62}")
    print(f"  {'Team':<18} {'Build':^8} {'Run':^8} {'Eval':^8} {'Retries':^8}")
    print(f"{'-' * 62}")
    # Core
    c = state.get("core", {})
    _print_team_row("core (CSO+Mgrs)", c)
    # Sub-teams
    for tk, info in state.get("sub_teams", {}).items():
        _print_team_row(tk, info)
    # Wiring
    w = state.get("wiring", {})
    if w:
        _print_team_row("cli_wiring", w)
    print(f"{'-' * 62}")
    passed = sum(1 for v in [state.get("core", {})]
                 + list(state.get("sub_teams", {}).values())
                 + ([state.get("wiring", {})] if state.get("wiring") else [])
                 if v.get("eval") == "PASS")
    total = 1 + len(state.get("sub_teams", {})) + (1 if state.get("wiring") else 0)
    print(f"  PASS: {passed}/{total}")
    print(f"{'-' * 62}\n")


def _print_team_row(name: str, info: dict):
    """Print one row of the status table."""
    build = info.get("build", "—")
    run = info.get("run", "—")
    ev = info.get("eval", "—")
    retries = info.get("retries", 0)
    # Color markers
    ev_mark = "PASS" if ev == "PASS" else ("FAIL" if ev == "FAIL" else "—")
    print(f"  {name:<18} {build:^8} {run:^8} {ev_mark:^8} {retries:^8}")


def _team_result(pipeline: "SwarmPipeline") -> dict:
    """Extract checkpoint-relevant result from a finished pipeline."""
    build = pipeline.build_result["status"] if pipeline.build_result else "N/A"
    run = pipeline.run_result["status"] if pipeline.run_result else "N/A"
    oe = pipeline.output_eval or {}
    return {
        "build": build,
        "run": run,
        "eval": oe.get("status", "N/A"),
        "eval_reason": oe.get("reason", ""),
        "eval_mode": oe.get("eval_mode", "pre_todo"),
        "todo_implemented": pipeline.todo_implemented,
        "output": str(pipeline.output_path) if pipeline.output_path else None,
        "docker_down": bool(pipeline.build_result and pipeline.build_result.get("docker_down")),
    }


def _create_merged_output(cp: dict, manifest: dict) -> Path | None:
    """Merge all pipeline phase outputs into one self-contained directory.

    Structure:
        output/{org}_merged/
            project.yml, agents/, src/, Dockerfile, docker-compose.yml, ...  (from wiring or core)
            teams/{team_key}/  (copy of each PASS'd sub-team)
            README.md          (master readme)
    """
    wiring_out = cp.get("wiring", {}).get("output")
    core_out = cp.get("core", {}).get("output")
    base_out = wiring_out or core_out
    if not base_out or not Path(base_out).exists():
        print("[Merge] No base output to merge from")
        return None

    org_name = manifest.get("org_name", "organization")
    slug = re.sub(r'[^a-z0-9]+', '_', org_name.lower()).strip('_')[:30]
    merged_dir = OUTPUT_DIR / f"{slug}_merged"

    if merged_dir.exists():
        shutil.rmtree(merged_dir)
    shutil.copytree(base_out, merged_dir)

    # Copy sub-team outputs into teams/
    teams_dir = merged_dir / "teams"
    teams_dir.mkdir(exist_ok=True)
    sub_teams_copied = []
    for tk, info in cp.get("sub_teams", {}).items():
        sub_out = info.get("output")
        if sub_out and Path(sub_out).exists() and info.get("eval") == "PASS":
            dest = teams_dir / tk
            shutil.copytree(sub_out, dest)
            sub_teams_copied.append(tk)

    # Fix wiring tool paths: sub-teams are now under teams/ instead of sibling dirs
    tools_path = merged_dir / "src" / "tools.py"
    if tools_path.exists():
        tools_content = tools_path.read_text(encoding="utf-8")
        if "_WIRING_BASE" in tools_content:
            # Replace any existing _WIRING_BASE with Docker-aware path
            import re as _re
            tools_content = _re.sub(
                r'_WIRING_BASE = .*',
                '_WIRING_BASE = _Path("/app/teams") if _Path("/app/teams").exists() else _Path(__file__).parent.parent / "teams"',
                tools_content,
                count=1
            )
            # Fix individual dir references from versioned names to plain team keys
            for tk in sub_teams_copied:
                sub_out_name = Path(cp["sub_teams"][tk]["output"]).name
                tools_content = tools_content.replace(f'"{sub_out_name}"', f'"{tk}"')
            tools_path.write_text(tools_content, encoding="utf-8")

    # Fix Dockerfile: add Docker CLI + COPY teams/
    dockerfile_path = merged_dir / "Dockerfile"
    if dockerfile_path.exists() and sub_teams_copied:
        df = dockerfile_path.read_text(encoding="utf-8")
        # Add Docker CLI install if not present
        if "get.docker.com" not in df:
            df = df.replace(
                "RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates &&",
                "# Install Node.js 20 + Claude Code CLI + Docker CLI (for sub-team delegation)\n"
                "RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates &&"
            )
            # Insert Docker install after NodeSource line
            df = df.replace(
                "curl -fsSL https://deb.nodesource.com/setup_20.x | bash - &&",
                "curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \\\n"
                "    curl -fsSL https://get.docker.com | sh &&"
            )
        # Add COPY teams/ if not present
        if "COPY teams/" not in df:
            df = df.replace('CMD ["python"', 'COPY teams/ teams/\nCMD ["python"')
        dockerfile_path.write_text(df, encoding="utf-8")

    # Fix docker-compose: add docker socket + Claude mounts
    compose_path = merged_dir / "docker-compose.yml"
    if compose_path.exists() and sub_teams_copied:
        import yaml as _yaml
        try:
            dc = _yaml.safe_load(compose_path.read_text(encoding="utf-8"))
            vols = dc["services"]["app"].setdefault("volumes", [])
            for v in ["/var/run/docker.sock:/var/run/docker.sock",
                      "~/.claude:/root/.claude", "~/.claude.json:/root/.claude.json"]:
                if v not in vols:
                    vols.append(v)
            compose_path.write_text(_yaml.dump(dc, default_flow_style=False, sort_keys=False), encoding="utf-8")
        except Exception:
            pass

    # Generate master README
    readme = [f"# {org_name} — Complete Agent Organization\n"]
    readme.append("Generated by the AutoGen Swarm Pipeline.\n")
    readme.append("## Teams\n")
    core_agents = manifest.get("agent_count", "?")
    readme.append(f"- **core** (orchestrator): `./` — {core_agents} total agents")
    for tk in sub_teams_copied:
        sub_info = manifest.get("sub_teams", {}).get(tk, {})
        mgr = sub_info.get("manager", tk)
        n_agents = len(sub_info.get("agents", {}))
        readme.append(f"- **{tk}** (`teams/{tk}/`): {mgr} + {n_agents} specialists")
    readme.append("\n## Quick Start\n")
    readme.append("```bash")
    readme.append("cp .env.example .env")
    readme.append("# Edit .env with your OPENAI_API_KEY")
    readme.append("docker compose up --build")
    readme.append('docker compose run --rm app python main.py "Your task"')
    readme.append("```\n")
    readme.append("The core team orchestrator will delegate to sub-teams automatically.\n")
    if sub_teams_copied:
        readme.append("## Running Sub-teams Independently\n")
        for tk in sub_teams_copied:
            readme.append(f"```bash\ncd teams/{tk}")
            readme.append(f'docker compose run --rm app python main.py "Task for {tk} team"')
            readme.append("```\n")

    (merged_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")

    print(f"\n  [Merge] Created merged output: {merged_dir}")
    print(f"  [Merge] Base: {'wiring' if wiring_out else 'core'}")
    print(f"  [Merge] Sub-teams included: {', '.join(sub_teams_copied) if sub_teams_copied else 'none'}")
    return merged_dir


# --- Export ---

def export_agent_team(source_dir: str, dest_dir: str = None, repo: str = None, private: bool = True) -> Path:
    """Export a merged output as a clean, standalone git repo and push to GitHub.

    Copies the agent team, strips runtime artifacts, generates SETUP.md,
    initialises a fresh git repo, creates a GitHub repo via `gh`, and pushes.

    Args:
        source_dir: Path to merged output directory.
        dest_dir:   Override destination path (default: output/{project_name}).
        repo:       GitHub repo name (e.g. "aisalesorgcore" or "org/aisalesorgcore").
                    If None, uses project name from project.yml.
        private:    Create private repo (default True).
    """
    import subprocess

    src = Path(source_dir).resolve()
    if not src.exists():
        print(f"[Export] Source not found: {src}")
        sys.exit(1)

    # Determine project name from project.yml
    proj_yml = src / "project.yml"
    project_name = "agent-team"
    if proj_yml.exists():
        try:
            proj = yaml.safe_load(proj_yml.read_text(encoding="utf-8"))
            project_name = re.sub(r'[^a-z0-9]+', '-', proj.get("name", "agent-team").lower()).strip('-')
        except Exception:
            pass

    # Destination
    if dest_dir:
        dst = Path(dest_dir).resolve()
    else:
        dst = src.parent / project_name
    if dst.exists():
        def _rm_readonly(func, path, _exc_info):
            import stat
            os.chmod(path, stat.S_IWRITE)
            func(path)
        shutil.rmtree(dst, onerror=_rm_readonly)

    # Copy everything
    shutil.copytree(src, dst)

    # Strip runtime artifacts
    for pattern in ["output", "__pycache__", ".env"]:
        for p in dst.rglob(pattern):
            if p.name == ".env" and p.is_file():
                p.unlink()
            elif p.name in ("output", "__pycache__") and p.is_dir():
                shutil.rmtree(p)
    # Also strip from sub-teams
    for team_dir in (dst / "teams").iterdir() if (dst / "teams").exists() else []:
        for pattern in ["output", "__pycache__", ".env"]:
            for p in team_dir.rglob(pattern):
                if p.name == ".env" and p.is_file():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p)

    # Read project info for SETUP.md
    agents = []
    agents_dir = dst / "agents"
    if agents_dir.exists():
        for d in sorted(agents_dir.iterdir()):
            if d.is_dir() and (d / "agent.yml").exists():
                try:
                    a = yaml.safe_load((d / "agent.yml").read_text(encoding="utf-8"))
                    agents.append({"name": d.name, "role": a.get("system_message", "")[:80]})
                except Exception:
                    agents.append({"name": d.name, "role": ""})

    teams = []
    teams_dir = dst / "teams"
    if teams_dir.exists():
        for d in sorted(teams_dir.iterdir()):
            if d.is_dir() and (d / "project.yml").exists():
                try:
                    t = yaml.safe_load((d / "project.yml").read_text(encoding="utf-8"))
                    teams.append({"key": d.name, "name": t.get("name", d.name),
                                  "agents": t.get("agents_total", "?")})
                except Exception:
                    teams.append({"key": d.name, "name": d.name, "agents": "?"})

    # Read .env.example for required keys
    env_example = dst / ".env.example"
    env_vars = []
    if env_example.exists():
        for line in env_example.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                key = line.split("=")[0]
                env_vars.append(key)
            elif line.startswith("# ") and "Required" not in line and "Optional" not in line:
                env_vars.append(line)

    # Generate SETUP.md
    setup = []
    setup.append(f"# {project_name} — Setup Guide\n")
    setup.append("This is a self-contained AutoGen agent team generated by **AgentFarm**.\n")
    setup.append("## Prerequisites\n")
    setup.append("- Docker & Docker Compose")
    setup.append("- An OpenAI API key (`gpt-4o` or compatible)\n")

    setup.append("## Quick Start\n")
    setup.append("```bash")
    setup.append("# 1. Clone this repo")
    setup.append(f"git clone <your-repo-url>")
    setup.append(f"cd {project_name}\n")
    setup.append("# 2. Configure environment")
    setup.append("cp .env.example .env")
    setup.append("# Edit .env — at minimum set OPENAI_API_KEY\n")
    setup.append("# 3. Build & run")
    setup.append("docker compose build")
    setup.append('docker compose run --rm app python main.py "Your task here"')
    setup.append("```\n")

    setup.append("## Environment Variables\n")
    setup.append("| Variable | Required | Description |")
    setup.append("|----------|----------|-------------|")
    setup.append("| `OPENAI_API_KEY` | Yes | OpenAI API key for agent LLM calls |")
    setup.append("| `OPENAI_MODEL` | No | Override model (default: `gpt-4o`) |")
    setup.append("| `ANTHROPIC_API_KEY` | No | For Claude Code tool (if agents use it) |")
    setup.append("| `MCP_GATEWAY_URL` | No | MCP Gateway endpoint for tool access |")
    setup.append("| `MCP_GATEWAY_AUTH_TOKEN` | No | Auth token for MCP Gateway |\n")

    # List tool-specific env vars from .env.example (skip vars already in main table)
    main_vars = {"OPENAI_API_KEY", "OPENAI_MODEL", "ANTHROPIC_API_KEY", "MCP_GATEWAY_URL", "MCP_GATEWAY_AUTH_TOKEN"}
    if env_example.exists():
        tool_vars = []
        for line in env_example.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("# ") and "=" in line and any(k in line for k in ["_API_KEY", "_TOKEN", "_URL", "_WEBHOOK"]):
                clean = line.lstrip("# ").split("=")[0].strip()
                if clean in main_vars:
                    continue
                desc = line.split("#")[-1].strip() if "#" in line[2:] else "Tool integration"
                tool_vars.append((clean, desc))
        if tool_vars:
            setup.append("**Tool integrations** (optional — mock data used if missing):\n")
            setup.append("| Variable | Description |")
            setup.append("|----------|-------------|")
            for var, desc in tool_vars:
                setup.append(f"| `{var}` | {desc} |")
            setup.append("")

    setup.append("## Architecture\n")
    setup.append(f"This team uses the **{project_name}** pattern with **{len(agents)} agents** in the core orchestrator.\n")

    if agents:
        setup.append("### Core Agents\n")
        setup.append("| Agent | Role |")
        setup.append("|-------|------|")
        for a in agents:
            role = a["role"]
            # Strip "ROLE:" prefix and agent name header
            role = re.sub(r'^ROLE:\s*', '', role).strip()
            role = re.sub(r'^[A-Z][A-Za-z &]+\n', '', role).strip()
            # Take first sentence, clean up
            role_short = role.split(".")[0].replace("|", "/").replace("\n", " ")[:70] if role else "—"
            setup.append(f"| `{a['name']}` | {role_short} |")
        setup.append("")

    if teams:
        setup.append("### Sub-Teams\n")
        setup.append("The orchestrator delegates specialized tasks to sub-teams:\n")
        setup.append("| Team | Agents | Run independently |")
        setup.append("|------|--------|-------------------|")
        for t in teams:
            setup.append(f"| `{t['key']}` | {t['agents']} | `cd teams/{t['key']} && docker compose run --rm app python main.py \"task\"` |")
        setup.append("")

    setup.append("## How It Works\n")
    setup.append("1. `main.py` loads `project.yml` and all agent definitions from `agents/`")
    setup.append("2. The lead agent receives your task and coordinates the team")
    setup.append("3. Agents use tools defined in `src/tools.py` (mock tools return simulated data)")
    setup.append("4. Results are written to the `output/` directory\n")

    setup.append("## Customization\n")
    setup.append("- **Add real tool integrations**: Replace mock functions in `src/tools.py` with real API calls")
    setup.append("- **Modify agent behavior**: Edit `agents/<AgentName>/agent.yml` system messages")
    setup.append("- **Change team structure**: Edit `project.yml` to add/remove agents")
    setup.append("- **Override model**: Set `OPENAI_MODEL=gpt-4o-mini` in `.env` for cheaper runs\n")

    setup.append("## Project Structure\n")
    setup.append("```")
    setup.append("├── project.yml          # Team configuration (agents, pattern, task)")
    setup.append("├── agents/              # Agent definitions (one agent.yml per agent)")
    setup.append("├── src/")
    setup.append("│   ├── main.py          # YAML-driven runtime loader")
    setup.append("│   └── tools.py         # Tool implementations (mock + real)")
    if teams:
        setup.append("├── teams/               # Sub-team directories")
        for t in teams:
            setup.append(f"│   └── {t['key']}/")
    setup.append("├── Dockerfile           # Container build")
    setup.append("├── docker-compose.yml   # Docker Compose config")
    setup.append("├── .env.example         # Environment template")
    setup.append("├── requirements.txt     # Python dependencies")
    setup.append("└── README.md            # Team overview")
    setup.append("```\n")

    setup.append("---\n")
    setup.append("*Generated by [AgentFarm](https://github.com/your-org/agentfarm)*")

    (dst / "SETUP.md").write_text("\n".join(setup), encoding="utf-8")

    # Ensure .gitignore
    gitignore = dst / ".gitignore"
    gi_lines = set()
    if gitignore.exists():
        gi_lines = set(gitignore.read_text(encoding="utf-8").splitlines())
    for entry in [".env", "output/", "__pycache__/", "*.pyc", ".DS_Store"]:
        gi_lines.add(entry)
    gitignore.write_text("\n".join(sorted(gi_lines)) + "\n", encoding="utf-8")

    # Git init + initial commit
    try:
        subprocess.run(["git", "init"], cwd=str(dst), capture_output=True, check=True)
        subprocess.run(["git", "add", "."], cwd=str(dst), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", f"Initial commit: {project_name} agent team\n\nGenerated by AgentFarm pipeline."],
                       cwd=str(dst), capture_output=True, check=True)
        print(f"[Export] Git repo initialized with initial commit")
    except FileNotFoundError:
        print("[Export] git not found — skipping repo init")
        print(f"\n[Export] Agent team exported to: {dst}")
        return dst
    except subprocess.CalledProcessError as e:
        print(f"[Export] git init warning: {e.stderr.decode()[:200] if e.stderr else ''}")

    # GitHub: create repo + push
    repo_name = repo or project_name
    visibility = "--private" if private else "--public"
    try:
        # Check if gh CLI is available
        subprocess.run(["gh", "--version"], capture_output=True, check=True)

        # Create GitHub repo (--source uses existing local repo)
        print(f"[Export] Creating GitHub repo: {repo_name} ({visibility.strip('-')})")
        result = subprocess.run(
            ["gh", "repo", "create", repo_name, visibility, "--source", str(dst), "--push"],
            cwd=str(dst), capture_output=True, text=True
        )
        if result.returncode == 0:
            # Extract repo URL from output
            repo_url = result.stdout.strip()
            print(f"[Export] Pushed to GitHub: {repo_url}")
        else:
            stderr = result.stderr.strip()
            if "already exists" in stderr:
                # Repo exists — just add remote and push
                print(f"[Export] Repo already exists, pushing to it...")
                subprocess.run(["gh", "repo", "view", repo_name, "--json", "url", "-q", ".url"],
                               cwd=str(dst), capture_output=True, text=True)
                subprocess.run(["git", "remote", "add", "origin",
                                f"https://github.com/{repo_name}.git" if "/" in repo_name
                                else f"https://github.com/{subprocess.run(['gh', 'api', 'user', '-q', '.login'], capture_output=True, text=True).stdout.strip()}/{repo_name}.git"],
                               cwd=str(dst), capture_output=True)
                push = subprocess.run(["git", "push", "-u", "origin", "HEAD"],
                                      cwd=str(dst), capture_output=True, text=True)
                if push.returncode == 0:
                    print(f"[Export] Pushed successfully")
                else:
                    print(f"[Export] Push failed: {push.stderr[:200]}")
            else:
                print(f"[Export] GitHub create failed: {stderr[:300]}")
    except FileNotFoundError:
        print("[Export] gh CLI not found — repo created locally only")
        print(f"[Export] To push manually: cd {dst} && gh repo create {repo_name} {visibility} --source . --push")

    print(f"\n[Export] Agent team exported to: {dst}")
    print(f"[Export] Files: {sum(1 for _ in dst.rglob('*') if _.is_file())}")
    return dst


# --- Registry Publishing ---

# Team-key → capability tags
_TEAM_CAPABILITIES = {
    "core":          ["sales_leadership", "team_coordination", "pipeline_management"],
    "outreach":      ["channel_outreach", "email_campaigns", "social_selling"],
    "bdr":           ["lead_generation", "multilingual_outreach", "prospecting"],
    "intel":         ["competitive_intelligence", "market_research", "product_analysis"],
    "research":      ["data_research", "lead_enrichment", "market_analysis"],
    "qualification": ["lead_qualification", "crm_update", "scoring"],
    "revops":        ["revenue_operations", "data_warehouse", "reporting"],
    "callintel":     ["call_intelligence", "call_recording", "crm_logging"],
    "workspace":     ["meeting_logistics", "scheduling", "workspace_management"],
    "content":       ["content_enablement", "content_generation", "sales_collateral"],
    "wiring":        ["cli_integration", "system_wiring", "orchestration"],
}


async def _publish_to_registry(
    session: aiohttp.ClientSession,
    team_key: str,
    run_id: str,
    pipeline: "SwarmPipeline",
    status: str,
    registry_agent_api_key: str | None,
    manifest: dict | None = None,
    eval_data: dict | None = None,
):
    """Register a team in the Minibook agent registry.

    Args:
        status: "candidate" or "validated"
        eval_data: eval dict to use; defaults to pipeline.output_eval
    """
    oe = eval_data if eval_data is not None else (pipeline.output_eval or {})
    raw_score = oe.get("score", "0")
    try:
        score_int = int(re.search(r'\d+', str(raw_score)).group())
    except (AttributeError, ValueError):
        score_int = 0

    # Derive agent_name: use manager name from manifest if available
    agent_name = None
    if manifest:
        if team_key == "core":
            # Prefer explicit "manager" key; fall back to first key in core_team dict
            core = manifest.get("core_team", {})
            agent_name = core.get("manager") or next(
                (k for k in core if not k.startswith("_")), None
            )
        elif team_key in manifest.get("sub_teams", {}):
            agent_name = manifest["sub_teams"][team_key].get("manager")
    if not agent_name:
        agent_name = f"{team_key.title()}Agent"

    # Find tools.py path in output
    tools_py_path = None
    if pipeline.output_path:
        tp = Path(pipeline.output_path) / "src" / "tools.py"
        if tp.exists():
            tools_py_path = str(tp)

    if pipeline.todo_implemented:
        todo_status = "implemented"
    elif status == "validated":
        # Passed without any TODO tools (all tools were already real)
        todo_status = "not_applicable"
    else:
        todo_status = "pending"
    await register_agent_in_registry(
        session=session,
        team_key=team_key,
        run_id=run_id,
        eval_score=score_int,
        eval_reason=oe.get("reason", ""),
        status=status,
        output_dir=str(pipeline.output_path) if pipeline.output_path else None,
        mcp_servers=list(pipeline.mcp_enabled or []),
        capabilities=_TEAM_CAPABILITIES.get(team_key, []),
        tools_py_path=tools_py_path,
        agent_name=agent_name,
        registry_agent_api_key=registry_agent_api_key,
        todo_status=todo_status,
    )


# --- Input File Mode ---

MAX_TEAM_RETRIES = 2  # retries per team on FAIL (total attempts = 3)

async def run_input_file_pipeline(session, agents, project_id, task, manifest, registry_agent_api_key=None):
    """Multi-phase pipeline: core → sub-teams → wiring.

    Each run starts fresh (no checkpoint resuming). Progress is still
    saved to checkpoint.json for status tracking during the run.
    Failed teams are retried up to MAX_TEAM_RETRIES times.
    registry_agent_api_key: API key of RegistryAgent for community publishing.
    """
    total_teams = 1 + len(manifest["sub_teams"])  # core + sub-teams
    checkpoint_dir = Path(OUTPUT_DIR)

    # Always start fresh — no checkpoint resuming
    cp = {
        "task": task,
        "started_at": datetime.now().isoformat(),
        "core": {},
        "sub_teams": {tk: {} for tk in manifest["sub_teams"]},
        "wiring": {},
    }
    _save_checkpoint(checkpoint_dir, cp)

    print(f"\n{'=' * 70}")
    print(f"  INPUT FILE MODE (with Checkpoints)")
    print(f"  {manifest['agent_count']} agents across {total_teams} teams")
    print(f"  Core: CSO + {len(manifest['core_team']) - 1} managers")
    for tk, tv in manifest["sub_teams"].items():
        status = cp.get("sub_teams", {}).get(tk, {}).get("eval", "PENDING")
        print(f"  Sub-team '{tk}': {tv['manager']} -> {len(tv['agents'])} specialists  [{status}]")
    print(f"  Max retries per team: {MAX_TEAM_RETRIES}")
    print(f"{'=' * 70}\n")

    # -- Phase 1: Core team --
    core_cp = cp.get("core", {})
    core_output = core_cp.get("output")

    if core_cp.get("eval") == "PASS" and core_output and Path(core_output).exists():
        print(f"\n[Checkpoint] Core team already PASS — skipping (output: {core_output})")
    else:
        for attempt in range(1, MAX_TEAM_RETRIES + 2):
            print(f"\n{'=' * 60}")
            print(f"  PHASE 1/3: Core Team (CSO + 9 Managers) — attempt {attempt}/{MAX_TEAM_RETRIES + 1}")
            print(f"{'=' * 60}")
            core_pipeline = SwarmPipeline(
                agents, project_id, f"{task} — Core Team",
                input_manifest=manifest, input_phase="core", input_team_key="core")
            core_success = await core_pipeline.run(session, f"{task} — Core Team")
            result = _team_result(core_pipeline)
            result["retries"] = attempt - 1
            cp["core"] = result
            core_output = result.get("output")
            _save_checkpoint(checkpoint_dir, cp)
            _print_status_table(cp)

            if core_success and result["eval"] == "PASS":
                print(f"[Checkpoint] Core team PASS on attempt {attempt}")
                if core_pipeline.todo_implemented and core_pipeline.pre_todo_eval:
                    # Two-phase: register candidate (pre-TODO mock eval) then validated (post-TODO)
                    await _publish_to_registry(session, "core", cp["started_at"],
                                               core_pipeline, "candidate",
                                               registry_agent_api_key, manifest,
                                               eval_data=core_pipeline.pre_todo_eval)
                    await _publish_to_registry(session, "core", cp["started_at"],
                                               core_pipeline, "validated",
                                               registry_agent_api_key, manifest)
                elif core_pipeline.todo_implemented:
                    # TODO ran but no pre_todo_eval captured — just register validated
                    await _publish_to_registry(session, "core", cp["started_at"],
                                               core_pipeline, "validated",
                                               registry_agent_api_key, manifest)
                else:
                    # No TODO tools found — all tools were real; register as candidate
                    # (real tools without TODO impl means they came from templates, not mock)
                    await _publish_to_registry(session, "core", cp["started_at"],
                                               core_pipeline, "candidate",
                                               registry_agent_api_key, manifest)
                break
            if result.get("docker_down"):
                print(f"[Checkpoint] Docker Engine down — aborting core retries")
                break
            if attempt <= MAX_TEAM_RETRIES:
                print(f"[Checkpoint] Core team FAIL — retrying ({attempt}/{MAX_TEAM_RETRIES})...")
                await stop_mcp_gateway()
            else:
                print(f"[Checkpoint] Core team FAILED after {attempt} attempts")
                # Register as candidate if build+run passed (mechanics work, quality insufficient)
                if result.get("build") == "PASS" and result.get("run") == "PASS":
                    await _publish_to_registry(session, "core", cp["started_at"],
                                               core_pipeline, "candidate",
                                               registry_agent_api_key, manifest)

    # -- Phase 2: Sub-teams --
    sub_team_dirs = {}
    # Carry over any previously passed sub-team dirs
    for tk, info in cp.get("sub_teams", {}).items():
        if info.get("eval") == "PASS" and info.get("output"):
            sub_team_dirs[tk] = info["output"]

    teams = list(manifest["sub_teams"].items())
    for idx, (team_key, team_info) in enumerate(teams, 1):
        sub_cp = cp.get("sub_teams", {}).get(team_key, {})

        # Skip if already PASS
        if sub_cp.get("eval") == "PASS" and sub_cp.get("output") and Path(sub_cp["output"]).exists():
            print(f"\n[Checkpoint] Sub-team '{team_key}' already PASS — skipping")
            continue

        specialist_names = list(team_info["agents"].keys())
        sub_task = (f"{task} — {team_info['manager']}'s sub-team: "
                    f"{', '.join(specialist_names[:5])}"
                    f"{'...' if len(specialist_names) > 5 else ''}")

        for attempt in range(1, MAX_TEAM_RETRIES + 2):
            print(f"\n{'=' * 60}")
            print(f"  PHASE 2/3: Sub-team {idx}/{len(teams)} — {team_key} "
                  f"({team_info['manager']}) — attempt {attempt}/{MAX_TEAM_RETRIES + 1}")
            print(f"{'=' * 60}")

            sub_pipeline = SwarmPipeline(
                agents, project_id, sub_task,
                input_manifest=manifest, input_phase="sub_team",
                input_team_key=team_key)

            try:
                sub_success = await sub_pipeline.run(session, sub_task)
                result = _team_result(sub_pipeline)
                result["retries"] = attempt - 1
            except Exception as e:
                print(f"[Checkpoint] Sub-team '{team_key}' ERROR: {e}")
                result = {"build": "ERROR", "run": "N/A", "eval": "FAIL",
                          "eval_reason": str(e), "output": None, "retries": attempt - 1}
                sub_success = False

            cp["sub_teams"][team_key] = result
            _save_checkpoint(checkpoint_dir, cp)

            if sub_success and result.get("eval") == "PASS":
                sub_team_dirs[team_key] = result["output"]
                print(f"[Checkpoint] Sub-team '{team_key}' PASS on attempt {attempt}")
                if sub_pipeline.todo_implemented and sub_pipeline.pre_todo_eval:
                    await _publish_to_registry(session, team_key, cp["started_at"],
                                               sub_pipeline, "candidate",
                                               registry_agent_api_key, manifest,
                                               eval_data=sub_pipeline.pre_todo_eval)
                    await _publish_to_registry(session, team_key, cp["started_at"],
                                               sub_pipeline, "validated",
                                               registry_agent_api_key, manifest)
                elif sub_pipeline.todo_implemented:
                    await _publish_to_registry(session, team_key, cp["started_at"],
                                               sub_pipeline, "validated",
                                               registry_agent_api_key, manifest)
                else:
                    # No TODO tools — all tools were real; stays candidate
                    await _publish_to_registry(session, team_key, cp["started_at"],
                                               sub_pipeline, "candidate",
                                               registry_agent_api_key, manifest)
                break
            if result.get("docker_down"):
                print(f"[Checkpoint] Docker Engine down — aborting '{team_key}' retries")
                break
            if attempt <= MAX_TEAM_RETRIES:
                print(f"[Checkpoint] Sub-team '{team_key}' FAIL — retrying ({attempt}/{MAX_TEAM_RETRIES})...")
                await stop_mcp_gateway()
            else:
                print(f"[Checkpoint] Sub-team '{team_key}' FAILED after {attempt} attempts — skipping")
                # Register as candidate if build+run passed (mechanics work, quality insufficient)
                if result.get("build") == "PASS" and result.get("run") == "PASS":
                    await _publish_to_registry(session, team_key, cp["started_at"],
                                               sub_pipeline, "candidate",
                                               registry_agent_api_key, manifest)

        _print_status_table(cp)

    # -- Phase 3: Wiring (only PASS'd teams) --
    if core_output and sub_team_dirs:
        passed_count = len(sub_team_dirs)
        total_sub = len(teams)
        print(f"\n{'=' * 60}")
        print(f"  PHASE 3/3: CLI Wiring ({passed_count}/{total_sub} sub-teams passed checkpoint)")
        print(f"  Included: {', '.join(sub_team_dirs.keys())}")
        skipped = [tk for tk in manifest["sub_teams"] if tk not in sub_team_dirs]
        if skipped:
            print(f"  Excluded (FAIL): {', '.join(skipped)}")
        print(f"{'=' * 60}")

        for attempt in range(1, MAX_TEAM_RETRIES + 2):
            if attempt > 1:
                print(f"\n  Wiring retry {attempt}/{MAX_TEAM_RETRIES + 1}")

            wiring_pipeline = SwarmPipeline(
                agents, project_id, f"{task} — CLI Wiring",
                input_manifest=manifest, input_phase="wiring",
                input_team_key="wiring", sub_team_dirs=sub_team_dirs)

            try:
                wiring_success = await wiring_pipeline.run(session, f"{task} — CLI Wiring")
                result = _team_result(wiring_pipeline)
                result["retries"] = attempt - 1
            except Exception as e:
                print(f"[Checkpoint] Wiring ERROR: {e}")
                result = {"build": "ERROR", "run": "N/A", "eval": "FAIL",
                          "eval_reason": str(e), "output": None, "retries": attempt - 1}
                wiring_success = False

            cp["wiring"] = result
            _save_checkpoint(checkpoint_dir, cp)

            if wiring_success and result.get("eval") == "PASS":
                print(f"[Checkpoint] Wiring PASS on attempt {attempt}")
                if wiring_pipeline.todo_implemented and wiring_pipeline.pre_todo_eval:
                    await _publish_to_registry(session, "wiring", cp["started_at"],
                                               wiring_pipeline, "candidate",
                                               registry_agent_api_key, manifest,
                                               eval_data=wiring_pipeline.pre_todo_eval)
                    await _publish_to_registry(session, "wiring", cp["started_at"],
                                               wiring_pipeline, "validated",
                                               registry_agent_api_key, manifest)
                elif wiring_pipeline.todo_implemented:
                    await _publish_to_registry(session, "wiring", cp["started_at"],
                                               wiring_pipeline, "validated",
                                               registry_agent_api_key, manifest)
                else:
                    await _publish_to_registry(session, "wiring", cp["started_at"],
                                               wiring_pipeline, "candidate",
                                               registry_agent_api_key, manifest)
                break
            if result.get("docker_down"):
                print(f"[Checkpoint] Docker Engine down — aborting wiring retries")
                break
            if attempt <= MAX_TEAM_RETRIES:
                print(f"[Checkpoint] Wiring FAIL — retrying ({attempt}/{MAX_TEAM_RETRIES})...")
                await stop_mcp_gateway()
            else:
                print(f"[Checkpoint] Wiring FAILED after {attempt} attempts")
                if result.get("build") == "PASS" and result.get("run") == "PASS":
                    await _publish_to_registry(session, "wiring", cp["started_at"],
                                               wiring_pipeline, "candidate",
                                               registry_agent_api_key, manifest)
    else:
        print(f"\n[Checkpoint] Skipping wiring — core={'PASS' if core_output else 'FAIL'}, "
              f"sub-teams passed={len(sub_team_dirs)}")

    # -- Final Summary --
    _print_status_table(cp)
    print(f"\n{'=' * 70}")
    print(f"  INPUT FILE PIPELINE COMPLETE (with Checkpoints)")
    print(f"  Core team: {cp.get('core', {}).get('output', 'N/A')}")
    for tk in manifest["sub_teams"]:
        info = cp.get("sub_teams", {}).get(tk, {})
        status = info.get("eval", "N/A")
        retries = info.get("retries", 0)
        print(f"  Sub-team '{tk}': {status} (retries: {retries}) — {info.get('output', 'N/A')}")
    wiring_info = cp.get("wiring", {})
    if wiring_info:
        print(f"  Wiring: {wiring_info.get('eval', 'N/A')} — {wiring_info.get('output', 'N/A')}")
    passed = sum(1 for v in [cp.get("core", {})]
                 + list(cp.get("sub_teams", {}).values())
                 + ([cp.get("wiring", {})] if cp.get("wiring") else [])
                 if v.get("eval") == "PASS")
    total = 1 + len(manifest["sub_teams"]) + (1 if cp.get("wiring") else 0)
    print(f"  Result: {passed}/{total} PASS")
    print(f"  Total agents: {manifest['agent_count']}")
    print(f"  Checkpoint: {checkpoint_dir / CHECKPOINT_FILE}")

    # -- Create merged output --
    merged = _create_merged_output(cp, manifest)
    if merged:
        cp["merged_output"] = str(merged)
        _save_checkpoint(checkpoint_dir, cp)
        print(f"  Merged output: {merged}")

    # -- Phase 4: Export to GitHub --
    if merged:
        print(f"\n{'=' * 70}")
        print(f"  PHASE 4: EXPORT TO GITHUB")
        print(f"{'=' * 70}")
        try:
            exported = export_agent_team(str(merged), private=True)
            cp["exported"] = str(exported)
            _save_checkpoint(checkpoint_dir, cp)
        except Exception as e:
            print(f"  [Export] Failed: {e}")

    print(f"{'=' * 70}")


# --- Main (Single-Run Mode) ---

_minibook_proc = None
_frontend_proc = None

async def _ensure_minibook(session):
    """Health check Minibook — auto-start API + frontend if not running."""
    global _minibook_proc, _frontend_proc
    import subprocess, atexit
    _minibook_dir = Path(__file__).parent
    _frontend_dir = _minibook_dir / "frontend"
    Path("output").mkdir(exist_ok=True)

    # --- API server (port 8899) ---
    try:
        await api_get(session, "/health")
        print("Minibook server: OK")
    except Exception:
        print("Minibook not running -- starting automatically...")
        _minibook_proc = subprocess.Popen(
            [sys.executable, "-u", "run.py"],
            cwd=str(_minibook_dir),
            stdout=open(str(Path("output") / "minibook.log"), "w"),
            stderr=subprocess.STDOUT,
        )
        atexit.register(lambda: _minibook_proc.terminate() if _minibook_proc else None)
        for _i in range(20):
            await asyncio.sleep(0.5)
            try:
                await api_get(session, "/health")
                print(f"Minibook server: OK (auto-started, PID {_minibook_proc.pid})")
                break
            except Exception:
                pass
        else:
            print("ERROR: Minibook failed to start. Check output/minibook.log")
            sys.exit(1)

    # --- Frontend dashboard (port 3457) ---
    if _frontend_dir.exists() and (_frontend_dir / "package.json").exists():
        import urllib.request
        try:
            urllib.request.urlopen("http://localhost:3457", timeout=2)
            print("Frontend dashboard: OK")
        except Exception:
            print("Frontend dashboard not running -- starting automatically...")
            _frontend_proc = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=str(_frontend_dir),
                stdout=open(str(Path("output") / "frontend.log"), "w"),
                stderr=subprocess.STDOUT,
                shell=True,
            )
            atexit.register(lambda: _frontend_proc.terminate() if _frontend_proc else None)
            # Brief wait for Next.js to start
            for _i in range(15):
                await asyncio.sleep(1)
                try:
                    urllib.request.urlopen("http://localhost:3457", timeout=2)
                    print(f"Frontend dashboard: OK (auto-started, PID {_frontend_proc.pid})")
                    break
                except Exception:
                    pass
            else:
                print("WARN: Frontend dashboard may still be starting. Check output/frontend.log")


async def main():
    """Single-pass pipeline mode with optional cascade/input-file support.

    CLI flags:
        --cascade-from <output_dir>     Start cascade from a previous output
        --cascade-features "F1 :: F2"   Features to add (:: separated)
        --cascade-file <path.yml>       Load cascade spec from YAML file
        --input-file <path.md>          Parse structured agent org and generate sub-teams
        --input-image <path.png>        Org chart image for vision analysis (auto-detected if omitted)
    """
    # Parse CLI flags
    cascade_from = None
    cascade_features_str = None
    cascade_file = None
    input_file = None
    input_image = None
    positional_args = []

    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--cascade-from" and i + 1 < len(argv):
            cascade_from = argv[i + 1]
            i += 2
        elif argv[i] == "--cascade-features" and i + 1 < len(argv):
            cascade_features_str = argv[i + 1]
            i += 2
        elif argv[i] == "--cascade-file" and i + 1 < len(argv):
            cascade_file = argv[i + 1]
            i += 2
        elif argv[i] == "--input-file" and i + 1 < len(argv):
            input_file = argv[i + 1]
            i += 2
        elif argv[i] == "--input-image" and i + 1 < len(argv):
            input_image = argv[i + 1]
            i += 2
        elif argv[i].startswith("--"):
            i += 1  # skip unknown flags
        else:
            positional_args.append(argv[i])
            i += 1

    task = " ".join(positional_args) if positional_args else None

    # Load cascade spec from YAML file if provided
    features = []
    if cascade_file:
        spec_path = Path(cascade_file)
        if not spec_path.exists():
            print(f"ERROR: Cascade spec file not found: {cascade_file}")
            sys.exit(1)
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
        if not task:
            task = spec.get("task", "")
        features = spec.get("features", [])
        if not cascade_from:
            cascade_from = spec.get("source_dir", spec.get("cascade_from"))
        print(f"[Cascade] Loaded spec from {cascade_file}: {len(features)} features")
    elif cascade_features_str:
        features = [f.strip() for f in cascade_features_str.split("::") if f.strip()]

    if not task:
        task = "Build a distributed weather monitoring system with 3 agents: data collector, analyzer, and reporter"

    is_cascade = bool(cascade_from or features)

    # Input file mode
    if input_file:
        input_path = Path(input_file)
        if not input_path.exists():
            print(f"ERROR: Input file not found: {input_file}")
            sys.exit(1)
        # Resolve image path: explicit flag > auto-detect in same directory
        if input_image:
            image_path = Path(input_image)
            if not image_path.exists():
                print(f"WARNING: Input image not found: {input_image} — proceeding without vision")
                image_path = None
        else:
            image_path = input_path.parent / "image.png"
            if not image_path.exists():
                pngs = list(input_path.parent.glob("*.png"))
                image_path = pngs[0] if pngs else None
            if image_path:
                print(f"[InputFile] Auto-detected org chart image: {image_path}")
        from swarm.input_parser import parse_input_file_llm
        manifest = await parse_input_file_llm(input_path, image_path)
        if not task:
            org_name = manifest.get("org_name", "AI Agent Organisation")
            task = manifest.get("core_task",
                f"Execute the {org_name} mission with {manifest['agent_count']} agents. "
                f"Write all results to /app/output/."
            )
        print(f"\n[InputFile] Parsed {manifest['agent_count']} agents from {input_file}")

    async with aiohttp.ClientSession() as session:
        # 1. Health check (auto-starts Minibook if needed)
        await _ensure_minibook(session)

        # 2. Register agents
        agents = await setup_agents(session)

        # 3. Create project
        slug = re.sub(r'[^a-z0-9]+', '_', task.lower())[:30].strip('_')
        project_id = await setup_project(session, agents, f"AutoGen: {slug}")

        if input_file:
            # INPUT FILE MODE: core team → sub-teams → wiring
            registry_key = agents.get("RegistryAgent", {}).get("api_key")
            await run_input_file_pipeline(session, agents, project_id, task, manifest,
                                          registry_agent_api_key=registry_key)
        elif is_cascade and features:
            # CASCADE MODE: run multiple iterations
            await run_cascade(session, agents, project_id, task, features, start_from=cascade_from)
        elif is_cascade and cascade_from and not features:
            # Single cascade iteration: task is the feature
            ctx = load_cascade_context(cascade_from)
            pipeline = SwarmPipeline(agents, project_id, task,
                                     cascade_from=ctx, cascade_feature=task)
            await pipeline.run(session, task)
        else:
            # Normal single-pass mode
            pipeline = SwarmPipeline(agents, project_id, task)
            await pipeline.run(session, task)

        print(f"\nView on Minibook: http://localhost:3457/forum")


# --- Forge Main (Continuous Mode) ---

async def setup_forge_agents(session: aiohttp.ClientSession) -> dict:
    """Register all 16 agents (original 10 + 6 forge agents)."""
    print("\n=== Registering Forge Agents (16 total) ===\n")
    creds = load_credentials()
    agents = {}
    # Original pipeline agents
    for name in AGENT_ROLES:
        info = await register_agent(session, name, creds)
        agents[name] = info
    # New forge agents
    for name in FORGE_AGENT_ROLES:
        info = await register_agent(session, name, creds)
        agents[name] = info
    return agents


async def forge_main():
    """Agent Forge — continuous, emergent code generation system."""
    # Check for --company-profile flag
    company_profile_path = None
    if "--company-profile" in sys.argv:
        idx = sys.argv.index("--company-profile")
        if idx + 1 < len(sys.argv):
            company_profile_path = sys.argv[idx + 1]

    print("\n" + "=" * 70)
    if company_profile_path:
        print("  COMPANYFORGE — Autonomous Company Builder")
    else:
        print("  AGENT FORGE — Continuous Emergent Code Generation System")
    print("=" * 70)

    async with aiohttp.ClientSession() as session:
        # 1. Health check (auto-starts Minibook if needed)
        await _ensure_minibook(session)

        # 2. Register all 16 agents
        agents = await setup_forge_agents(session)

        # 3. Create main Forge project
        project_id = await setup_project(session, agents, "AgentForge")

        # 4. Initialize ForgeOrchestrator
        orchestrator = ForgeOrchestrator(agents, project_id)
        await orchestrator.initialize(session)

        # 4b. Activate CompanyForge if profile provided
        if company_profile_path:
            await orchestrator._activate_company_forge(company_profile_path, session)

        # 5. Start Task API
        api = ForgeAPI(orchestrator)
        api_runner = await api.start(port=FORGE_API_PORT)

        print(f"Minibook:  http://localhost:3457/forum")
        if company_profile_path:
            print(f"Company:   {company_profile_path}")
            print(f"Status:    http://localhost:{FORGE_API_PORT}/forge/company/status")
        print()

        # 6. Run forever
        try:
            await orchestrator.run_forever(session)
        except KeyboardInterrupt:
            print("\n[Forge] Shutting down gracefully...")
        finally:
            await api.cleanup()
            await stop_mcp_gateway()
            print("[Forge] Stopped.")


async def company_main():
    """CompanyForge one-shot — build all teams for a company profile, then exit."""
    idx = sys.argv.index("--company")
    if idx + 1 >= len(sys.argv):
        print("Usage: python autogen_swarm.py --company <company_profile.md>")
        sys.exit(1)
    profile_path = sys.argv[idx + 1]

    if not Path(profile_path).exists():
        print(f"Error: {profile_path} not found")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("  COMPANYFORGE — One-Shot Company Builder")
    print(f"  Profile: {profile_path}")
    print("=" * 70)

    from swarm.company_builder import parse_company_profile, OrgBoard, CrossTeamLinker

    async with aiohttp.ClientSession() as session:
        await _ensure_minibook(session)
        agents = await setup_forge_agents(session)
        project_id = await setup_project(session, agents, "CompanyForge")

        # Parse profile and plan
        profile = await parse_company_profile(profile_path)
        org_board = OrgBoard(profile)
        team_specs = await org_board.plan_teams()
        linker = CrossTeamLinker()

        print(f"\n[CompanyForge] {profile.name}: {len(team_specs)} teams planned")
        for i, t in enumerate(team_specs, 1):
            print(f"  {i}. {t.name} [{t.team_key}]")

        built = []
        failed = []

        for spec in team_specs:
            # Check dependencies
            dep_met = all(d in built for d in spec.dependencies)
            if not dep_met:
                print(f"\n[CompanyForge] Skipping {spec.team_key} — unmet deps: {spec.dependencies}")
                failed.append(spec.team_key)
                continue

            print(f"\n{'='*60}")
            print(f"  Building: {spec.name} [{spec.team_key}]")
            print(f"{'='*60}")

            slug = re.sub(r'[^a-z0-9]+', '_', spec.team_key)[:30].strip('_')
            run_project_id = await setup_project(session, agents, f"Company: {slug}")

            pipeline = SwarmPipeline(agents, run_project_id, spec.task_description)
            success = await pipeline.run(session, spec.task_description)

            if success:
                built.append(spec.team_key)
                print(f"[CompanyForge] SUCCESS: {spec.team_key}")
            else:
                failed.append(spec.team_key)
                print(f"[CompanyForge] FAILED: {spec.team_key}")

        # Link teams and post handoffs
        print(f"\n{'='*60}")
        print(f"  COMPANY BUILD COMPLETE")
        print(f"  Built: {len(built)}/{len(team_specs)}")
        print(f"{'='*60}")

        try:
            registry = await api_get(session, "/api/v1/registry",
                                     params={"status": "validated"})
            registry_key = agents.get("RegistryAgent", {}).get("api_key")
            await linker.link_teams(session, registry, registry_key)
            await linker.post_handoffs(
                session, team_specs, registry, project_id,
                agents.get("ForgeOrchestrator", {}).get("api_key", "")
            )
        except Exception as e:
            print(f"[CompanyForge] Post-build linking failed: {e}")

        await stop_mcp_gateway()


async def design_main():
    """InputDesign pipeline — generate input.md from a task description."""
    # Extract task description (everything after --design)
    idx = sys.argv.index("--design")
    task_words = [a for a in sys.argv[idx + 1:] if not a.startswith("--")]
    task = " ".join(task_words)
    if not task:
        print("Usage: python autogen_swarm.py --design \"build a support team for SaaS with Zendesk\"")
        sys.exit(1)

    print(f"\n{'=' * 70}")
    print("  AGENTFARM — Input Design Pipeline")
    print(f"  Task: {task}")
    print(f"{'=' * 70}")

    async with aiohttp.ClientSession() as session:
        # Health check (auto-starts Minibook if needed)
        await _ensure_minibook(session)

        # Register InputDesign agents
        from swarm.knowledge import INPUT_DESIGN_ROLES
        creds = load_credentials()
        agents = {}
        for name in INPUT_DESIGN_ROLES:
            info = await register_agent(session, name, creds)
            agents[name] = info
        print(f"  Agents: {', '.join(agents.keys())}")

        # Create project
        project_id = await setup_project(session, agents, "InputDesign")

        # Run pipeline
        pipeline = InputDesignPipeline(agents, project_id, task)
        input_path = await pipeline.run(session)

        if input_path:
            print(f"\n  Generated: {input_path}")
            print(f"  Next: python minibook/autogen_swarm.py --input-file {input_path}")


if __name__ == "__main__":
    if "--export" in sys.argv:
        idx = sys.argv.index("--export")
        src = sys.argv[idx + 1] if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("--") else None
        if not src:
            print("Usage: python autogen_swarm.py --export <merged_output_dir> [--repo name] [--public]")
            sys.exit(1)
        # Parse optional flags
        repo_name = None
        if "--repo" in sys.argv:
            ri = sys.argv.index("--repo")
            repo_name = sys.argv[ri + 1] if ri + 1 < len(sys.argv) else None
        is_public = "--public" in sys.argv
        export_agent_team(src, repo=repo_name, private=not is_public)
    elif "--design" in sys.argv:
        asyncio.run(design_main())
    elif "--company" in sys.argv:
        asyncio.run(company_main())
    elif "--forge" in sys.argv:
        asyncio.run(forge_main())
    else:
        asyncio.run(main())
