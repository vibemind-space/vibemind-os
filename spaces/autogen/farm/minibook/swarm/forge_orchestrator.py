"""Forge orchestrator — continuous code generation system with scheduling and API."""

import asyncio
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import aiohttp
from aiohttp import web as aiohttp_web

from .constants import (
    MINIBOOK_URL, OUTPUT_DIR, FORGE_SCHEDULE, FORGE_STATE_FILE,
    FORGE_METRICS_FILE, FORGE_API_PORT, STALL_THRESHOLD, MAX_CASCADE_DEPTH,
    FORGE_HOURLY_BUDGET, DOC_RESEARCH_TOPICS, MCP_GATEWAY_PORT,
    COMPANY_MAX_TEAMS,
)
from .knowledge import AGENT_ROLES, FORGE_AGENT_ROLES
from .api_client import api_post, api_get
from .llm import call_gpt4o
from .docker_ops import (
    prepare_docker_context, docker_build_test, docker_run_test,
    start_mcp_gateway, stop_mcp_gateway,
)
from .code_processing import test_generated_code, write_output, load_cascade_context
from .forge_agents import (
    ForgeState, load_forge_state, save_forge_state, ForgePostTracker,
    DocResearcherAgent, DependencyAgent, SecurityAgent, BenchmarkAgent, RepoAgent,
)
from .pipeline import SwarmPipeline
from .company_builder import (
    parse_company_profile, OrgBoard, CrossTeamLinker, CompanyProfile,
)


async def _setup_project_proxy(session, agents, name):
    """Late import to avoid circular dependency with autogen_swarm."""
    from autogen_swarm import setup_project
    return await setup_project(session, agents, name)


# Alias used by existing code (preserves backward compat)
setup_project = _setup_project_proxy


class ForgeOrchestrator:
    """Meta-agent that runs continuously, scheduling and monitoring all Forge activities."""

    DEFAULT_TASKS = [
        "Build a distributed weather monitoring system with 3 agents: data collector, analyzer, and reporter",
        "Build an agentic learning course system with research, content creation, and quiz agents",
        "Build a code review pipeline with analysis, feedback, and improvement agents",
        "Build a customer support system with triage, specialist, and escalation agents",
        "Build a data pipeline with ingestion, transformation, and validation agents",
    ]

    def __init__(self, agents: dict, project_id: str):
        self.agents = agents
        self.project_id = project_id
        self.state = load_forge_state()
        self.tracker = ForgePostTracker()
        self.forge_start_time = time.time()
        self._pipeline_running = False
        self._task_index = self.state.run_count % len(self.DEFAULT_TASKS)

        # Create specialized agents
        self.doc_researcher = DocResearcherAgent(agents, project_id, self.tracker)
        self.dep_agent = DependencyAgent(agents, project_id, self.tracker)
        self.security_agent = SecurityAgent(agents, project_id, self.tracker)
        self.benchmark_agent = BenchmarkAgent(agents, project_id, self.tracker)
        self.repo_agent = RepoAgent(agents, project_id, self.tracker)

        # CompanyForge — initialized lazily via _activate_company_forge()
        self._org_board: OrgBoard | None = None
        self._cross_team_linker = CrossTeamLinker()

    def _key(self) -> str:
        return self.agents["ForgeOrchestrator"]["api_key"]

    def _save(self):
        save_forge_state(self.state)

    async def initialize(self, session: aiohttp.ClientSession):
        """Set up Grand Plan and initial state."""
        print("\n[ForgeOrchestrator] Initializing...")

        # Set ForgeOrchestrator as Primary Lead (admin API uses PATCH)
        try:
            orch_id = self.agents["ForgeOrchestrator"]["id"]
            async with session.patch(
                f"{MINIBOOK_URL}/api/v1/admin/projects/{self.project_id}",
                json={"primary_lead_agent_id": orch_id},
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status < 400:
                    print("  [+] ForgeOrchestrator set as Primary Lead")
                else:
                    print(f"  [!] Primary Lead API: {resp.status}")
        except Exception as e:
            print(f"  [!] Could not set Primary Lead: {e}")

        # Create or update Grand Plan
        if not self.state.grand_plan_post_id:
            plan_content = (
                "## Agent Forge Grand Plan\n\n"
                "**Status:** Initializing\n"
                f"**Started:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"**Run Count:** {self.state.run_count}\n"
                f"**Fix Points Detected:** {self.state.fix_points_detected}\n\n"
                "### Schedule\n"
                "- Pipeline runs: every 45 min\n"
                "- Benchmarks: every 20 min\n"
                "- Doc research: every 60 min\n"
                "- Security scans: every 120 min\n"
                "- Dependency checks: every 30 min\n\n"
                "### Agents Online\n"
                f"- {len(self.agents)} agents registered\n\n"
                "*This plan updates automatically every 15 minutes.*"
            )
            try:
                post = await api_post(
                    session,
                    f"/api/v1/projects/{self.project_id}/posts",
                    {"title": "Grand Plan", "content": plan_content, "type": "plan",
                     "tags": ["grand-plan"]},
                    api_key=self._key()
                )
                self.state.grand_plan_post_id = post["id"]
                # Pin it to top
                try:
                    async with session.patch(
                        f"{MINIBOOK_URL}/api/v1/posts/{post['id']}",
                        json={"pin_order": 0},
                        headers={"Content-Type": "application/json",
                                 "Authorization": f"Bearer {self._key()}"}
                    ) as resp:
                        pass
                except Exception:
                    pass
                self._save()
                print("  [+] Grand Plan created")
            except Exception as e:
                print(f"  [!] Grand Plan creation failed: {e}")

        # Initialize repo
        await self.repo_agent.ensure_repo()
        print("[ForgeOrchestrator] Ready\n")

    async def run_forever(self, session: aiohttp.ClientSession):
        """Main infinite loop — the heart of the Agent Forge."""
        print("=" * 60)
        print("  AGENT FORGE RUNNING — Ctrl+C to stop")
        print("=" * 60)

        while True:
            try:
                await self._process_notifications(session)
                await self._run_scheduled_triggers(session)
                await self._detect_stalls(session)
            except KeyboardInterrupt:
                print("\n[ForgeOrchestrator] Shutting down...")
                break
            except Exception as e:
                print(f"[ForgeOrchestrator] Error in main loop: {e}")
            await asyncio.sleep(POLL_INTERVAL)

    async def _process_notifications(self, session: aiohttp.ClientSession):
        """Check for @mentions to ForgeOrchestrator."""
        try:
            notifications = await api_get(
                session, "/api/v1/notifications",
                api_key=self._key(), params={"unread_only": "true"}
            )
            for notif in notifications:
                if notif["type"] == "mention" and not notif["read"]:
                    await api_post(session, f"/api/v1/notifications/{notif['id']}/read",
                                   {}, api_key=self._key())
                    # Check if it's a security critical alert
                    post_id = notif.get("payload", {}).get("post_id")
                    if post_id:
                        try:
                            post = await api_get(session, f"/api/v1/posts/{post_id}")
                            tags = post.get("tags", [])
                            if "security" in tags and "critical" in tags:
                                print("  [Forge] SECURITY CRITICAL detected - broadcasting @all")
                                await self._broadcast_security_alert(session, post)
                        except Exception:
                            pass
        except Exception:
            pass  # Non-critical — notification polling can fail silently

    async def _broadcast_security_alert(self, session: aiohttp.ClientSession, post: dict):
        """Broadcast a critical security alert using @all (Primary Lead only, 1/hour)."""
        if not self.tracker.can_post("ForgeOrchestrator"):
            return
        try:
            await api_post(
                session,
                f"/api/v1/posts/{post['id']}/comments",
                {"content": f"@all CRITICAL SECURITY ALERT: {post['title']}\n\n"
                            f"All agents should review this finding immediately."},
                api_key=self._key()
            )
            self.tracker.record_post("ForgeOrchestrator")
        except Exception as e:
            print(f"  [Forge] @all broadcast failed: {e}")

    async def _run_scheduled_triggers(self, session: aiohttp.ClientSession):
        """Check all scheduled triggers and fire those that are due."""
        now = time.time()

        # 1. Pipeline Run (45 min, or immediately if a task is queued via API)
        if not self._pipeline_running:
            if self.state.queued_task or (now - self.state.last_run_time) > FORGE_SCHEDULE["pipeline_run"]:
                await self._spawn_pipeline_run(session)

        # 2. Benchmark (20 min)
        if (now - self.state.last_benchmark_time) > FORGE_SCHEDULE["benchmark"]:
            await self._run_benchmark(session)

        # 3. Doc Research (60 min)
        if (now - self.state.last_doc_research_time) > FORGE_SCHEDULE["doc_research"]:
            await self._run_doc_research(session)

        # 4. Security Scan (120 min)
        if (now - self.state.last_security_scan_time) > FORGE_SCHEDULE["security_scan"]:
            await self._run_security_scan(session)

        # 5. Dependency Check (30 min)
        if (now - self.state.last_dep_check_time) > FORGE_SCHEDULE["dep_check"]:
            await self._run_dep_check(session)

        # 6. Grand Plan Update (15 min)
        if (now - self.state.last_grand_plan_time) > FORGE_SCHEDULE["grand_plan"]:
            await self._update_grand_plan(session)

        # 7. Repo Commit (10 min)
        if (now - self.state.last_repo_commit_time) > FORGE_SCHEDULE["repo_commit"]:
            await self._run_repo_commit(session)

        # 8. Architecture Review (90 min)
        if (now - self.state.last_arch_review_time) > FORGE_SCHEDULE["arch_review"]:
            await self._spawn_arch_review(session)

        # 9. CompanyForge (5 min between builds, only when active)
        if self.state.company_forge_active and not self._pipeline_running:
            if (now - self.state.last_company_forge_time) > FORGE_SCHEDULE["company_forge"]:
                await self._run_company_forge_cycle(session)

    async def _spawn_pipeline_run(self, session: aiohttp.ClientSession):
        """Start a new SwarmPipeline run."""
        if self._pipeline_running:
            return

        # Pick task: queued task from API, or cycle through defaults
        task = self.state.queued_task or self.DEFAULT_TASKS[self._task_index % len(self.DEFAULT_TASKS)]
        self.state.queued_task = ""
        self._task_index += 1

        print(f"\n{'='*60}")
        print(f"  FORGE PIPELINE RUN #{self.state.run_count + 1}")
        print(f"  Task: {task[:60]}")
        print(f"{'='*60}")

        self._pipeline_running = True
        try:
            # Create a new SwarmPipeline instance (reuses registered agents)
            slug = re.sub(r'[^a-z0-9]+', '_', task.lower())[:30].strip('_')
            project_name = f"AutoGen: {slug}"

            # Use a sub-project for each pipeline run
            run_project_id = await setup_project(session, self.agents, project_name)

            pipeline = SwarmPipeline(self.agents, run_project_id, task)
            success = await pipeline.run(session, task)

            self.state.run_count += 1
            self.state.last_run_time = time.time()

            # Post summary to the Forge project
            if self.tracker.can_post("ForgeOrchestrator"):
                build_s = pipeline.build_result["status"] if pipeline.build_result else "N/A"
                run_s = pipeline.run_result["status"] if pipeline.run_result else "N/A"
                await api_post(
                    session,
                    f"/api/v1/projects/{self.project_id}/posts",
                    {
                        "title": f"Pipeline Run #{self.state.run_count}: {slug}",
                        "content": (
                            f"## Pipeline Complete\n\n"
                            f"**Task:** {task}\n"
                            f"**Build:** {build_s} | **Run:** {run_s}\n"
                            f"**Files:** {len(pipeline.generated_files)} code + {len(pipeline.yaml_files)} YAML\n"
                            f"**MCP Servers:** {', '.join(pipeline.mcp_enabled) if pipeline.mcp_enabled else 'None'}\n\n"
                            f"{'PASS' if success else 'FAIL'}\n\n"
                            f"@BenchmarkAgent please evaluate.\n"
                            f"@SecurityAgent please scan."
                        ),
                        "type": "task",
                        "tags": ["forge-run", f"run-{self.state.run_count}"],
                    },
                    api_key=self._key()
                )
                self.tracker.record_post("ForgeOrchestrator")

            self._save()
            print(f"\n[Forge] Pipeline run #{self.state.run_count} complete: {'PASS' if success else 'FAIL'}")

            # Upgrade all outputs after each successful run
            if success:
                await self._upgrade_outputs(session)
        except Exception as e:
            print(f"[Forge] Pipeline run failed: {e}")
            self.tracker.record_error("ForgeOrchestrator")
        finally:
            self._pipeline_running = False

    async def _run_benchmark(self, session: aiohttp.ClientSession):
        """Trigger a benchmark measurement."""
        try:
            score = await self.benchmark_agent.run_benchmark_cycle(session)
            self.state.last_benchmark_time = time.time()
            if score >= 0:
                self.state.convergence_scores.append(score)
                # Keep only last 20 scores
                self.state.convergence_scores = self.state.convergence_scores[-20:]
                # Check convergence
                if self._is_converged():
                    await self._handle_convergence(session)
            self._save()
        except Exception as e:
            print(f"  [Forge] Benchmark failed: {e}")
            self.tracker.record_error("BenchmarkAgent")

    async def _run_doc_research(self, session: aiohttp.ClientSession):
        """Trigger a documentation research cycle."""
        try:
            topic = DOC_RESEARCH_TOPICS[self.state.doc_research_index % len(DOC_RESEARCH_TOPICS)]
            await self.doc_researcher.run_research_cycle(session, topic)
            self.state.doc_research_index += 1
            self.state.last_doc_research_time = time.time()
            self._save()
        except Exception as e:
            print(f"  [Forge] Doc research failed: {e}")
            self.tracker.record_error("DocResearcherAgent")

    async def _run_security_scan(self, session: aiohttp.ClientSession):
        """Trigger a security scan."""
        try:
            await self.security_agent.run_security_cycle(session)
            self.state.last_security_scan_time = time.time()
            self._save()
        except Exception as e:
            print(f"  [Forge] Security scan failed: {e}")
            self.tracker.record_error("SecurityAgent")

    async def _run_dep_check(self, session: aiohttp.ClientSession):
        """Trigger a dependency check."""
        try:
            await self.dep_agent.run_dep_cycle(session)
            self.state.last_dep_check_time = time.time()
            self._save()
        except Exception as e:
            print(f"  [Forge] Dep check failed: {e}")
            self.tracker.record_error("DependencyAgent")

    async def _upgrade_outputs(self, session: aiohttp.ClientSession):
        """Scan all output directories and upgrade tools.py files.

        Ensures every output has claude_code and removes fake MCP tool wrappers
        that reference servers that were never actually enabled.
        """
        CLAUDE_CLI_CODE = '''import asyncio
import json
import os
import httpx

MCP_GATEWAY_URL = os.environ.get("MCP_GATEWAY_URL", "http://host.docker.internal:8808")

async def _call_mcp_tool(tool_name: str, arguments: dict) -> str:
    """Call an MCP tool via the Docker MCP Gateway SSE endpoint."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{MCP_GATEWAY_URL}/tools/call",
            json={"name": tool_name, "arguments": arguments},
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "content" in data:
                return data["content"][0].get("text", json.dumps(data))
            return json.dumps(data)
        return f"Error {resp.status_code}: {resp.text}"

async def claude_code(task: str, code: str = "", files: str = "") -> str:
    """Delegate a task to Claude Code CLI (AI coding assistant).
    Use this to: write code, review code, refactor, debug, generate tests,
    analyze data, or any complex reasoning/analysis task.
    Args:
        task: Description of what Claude Code should do
        code: Optional code to review/refactor/extend
        files: Optional comma-separated file paths for context
    Returns: Claude Code's response (code, review, analysis, etc.)
    """
    parts = [task]
    if code:
        parts.append(f"\\n\\nCODE:\\n```\\n{code}\\n```")
    if files:
        parts.append(f"\\n\\nRelevant files: {files}")
    full_prompt = "\\n".join(parts)
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", full_prompt, "--output-format", "text",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode == 0:
            return stdout.decode().strip()
        err = stderr.decode().strip()
        if "auth" in err.lower() or "login" in err.lower():
            return f"Claude Code auth error - ensure ~/.claude is mounted from host: {err[:200]}"
        return f"Claude Code error: {err[:500]}"
    except FileNotFoundError:
        return "Error: claude CLI not found - check Dockerfile has npm install -g @anthropic-ai/claude-code"
    except asyncio.TimeoutError:
        return "Error: Claude Code timed out (300s)"
'''
        upgraded = []
        skipped = []
        try:
            output_dirs = sorted(OUTPUT_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            for d in output_dirs:
                if not d.is_dir():
                    continue
                tools_path = d / "src" / "tools.py"
                main_path = d / "src" / "main.py"

                if not tools_path.exists():
                    continue

                tools_content = tools_path.read_text(encoding="utf-8", errors="replace")

                # Check if claude_code is present
                has_claude_code = "async def claude_code" in tools_content

                # Check for fake MCP tool functions (tools referencing non-docker servers)
                # Real tools: docker, _call_mcp_tool, claude_code
                import re as _re
                tool_funcs = _re.findall(r'async def (\w+)\(', tools_content)
                known_good = {"_call_mcp_tool", "claude_code", "docker"}
                fake_tools = [f for f in tool_funcs if f not in known_good and "_call_mcp_tool" in tools_content.split(f"async def {f}")[1][:200] if len(tools_content.split(f"async def {f}")) > 1]

                needs_upgrade = not has_claude_code or len(fake_tools) > 0

                if not needs_upgrade:
                    skipped.append(d.name)
                    continue

                # Preserve any real docker tool wrapper
                docker_tool = ""
                if 'async def docker(' in tools_content:
                    # Extract docker tool function
                    match = _re.search(r'(async def docker\([^)]*\)[^}]*?return await _call_mcp_tool\([^)]+\))', tools_content, _re.DOTALL)
                    if match:
                        docker_tool = "\n\n" + match.group(0) + "\n"

                # Write upgraded tools.py
                new_tools = CLAUDE_CLI_CODE.rstrip() + docker_tool + "\n"
                tools_path.write_text(new_tools, encoding="utf-8")

                # Fix main.py imports — ensure claude_code is imported
                if main_path.exists():
                    main_content = main_path.read_text(encoding="utf-8", errors="replace")
                    if "claude_code" not in main_content:
                        # Add claude_code to the tools import
                        if "from tools import" in main_content:
                            main_content = main_content.replace(
                                "from tools import",
                                "from tools import claude_code, ",
                                1
                            )
                        else:
                            main_content = "from tools import claude_code\n" + main_content
                        main_path.write_text(main_content, encoding="utf-8")

                    # Remove imports of fake tools
                    for fake in fake_tools:
                        main_content = main_path.read_text(encoding="utf-8", errors="replace")
                        main_content = main_content.replace(f", {fake}", "").replace(f"{fake}, ", "").replace(f"import {fake}\n", "")
                        # Remove from tools=[...] lists
                        main_content = _re.sub(rf'\b{fake}\b,?\s*', '', main_content)
                        main_path.write_text(main_content, encoding="utf-8")

                upgraded.append(d.name)
                print(f"  [Upgrader] Fixed {d.name}: +claude_code, -{len(fake_tools)} fake tools")

            if upgraded:
                # Post upgrade report to Minibook
                if self.tracker.can_post("ForgeOrchestrator"):
                    await api_post(
                        session,
                        f"/api/v1/projects/{self.project_id}/posts",
                        {
                            "title": f"Output Upgrade: {len(upgraded)} projects fixed",
                            "content": (
                                f"## Output Upgrader Report\n\n"
                                f"**Upgraded:** {len(upgraded)} outputs\n"
                                f"**Already OK:** {len(skipped)}\n\n"
                                f"### Fixed outputs:\n" +
                                "\n".join(f"- `{n}`" for n in upgraded) +
                                f"\n\nAll outputs now have `claude_code` as primary tool. "
                                f"Fake MCP tool wrappers removed.\n\n"
                                f"@RepoAgent please commit."
                            ),
                            "type": "report",
                            "tags": ["upgrade", "tools", "claude-cli"],
                        },
                        api_key=self._key()
                    )
                    self.tracker.record_post("ForgeOrchestrator")
                print(f"  [Forge] Upgraded {len(upgraded)} outputs, {len(skipped)} already OK")
            else:
                print(f"  [Forge] All {len(skipped)} outputs already up to date")
        except Exception as e:
            print(f"  [Forge] Output upgrade failed: {e}")

    async def _run_repo_commit(self, session: aiohttp.ClientSession):
        """Trigger a git commit cycle."""
        try:
            await self.repo_agent.run_repo_cycle(session)
            self.state.last_repo_commit_time = time.time()
            self._save()
        except Exception as e:
            print(f"  [Forge] Repo commit failed: {e}")
            self.tracker.record_error("RepoAgent")

    # --- CompanyForge Methods ---

    async def _activate_company_forge(self, profile_path: str, session: aiohttp.ClientSession):
        """Activate the CompanyForge loop with a company profile."""
        print(f"\n[CompanyForge] Activating with profile: {profile_path}")
        profile = await parse_company_profile(profile_path)
        self._org_board = OrgBoard(profile)

        # Plan teams upfront
        team_specs = await self._org_board.plan_teams()
        print(f"[CompanyForge] OrgBoard planned {len(team_specs)} teams:")
        for i, t in enumerate(team_specs, 1):
            deps = f" (depends: {', '.join(t.dependencies)})" if t.dependencies else ""
            print(f"  {i}. {t.name} [{t.team_key}]{deps}")

        self.state.company_forge_active = True
        self.state.company_profile_path = profile_path
        self.state.company_team_queue = [t.team_key for t in team_specs]
        self._save()

        # Post plan to Minibook
        if self.tracker.can_post("ForgeOrchestrator"):
            team_list = "\n".join(
                f"- **{t.name}** (`{t.team_key}`): {t.task_description[:100]}..."
                for t in team_specs
            )
            await api_post(
                session,
                f"/api/v1/projects/{self.project_id}/posts",
                {
                    "title": f"CompanyForge: {profile.name} — {len(team_specs)} Teams Planned",
                    "content": (
                        f"## Company Build Plan\n\n"
                        f"**Company:** {profile.name}\n"
                        f"**Industry:** {profile.industry}\n"
                        f"**Goals:** {', '.join(profile.goals[:3])}\n\n"
                        f"### Planned Teams\n{team_list}\n\n"
                        f"Building autonomously. Next update after first team completes."
                    ),
                    "type": "plan",
                    "tags": ["company-forge", "plan"],
                },
                api_key=self._key()
            )
            self.tracker.record_post("ForgeOrchestrator")

        print(f"[CompanyForge] Ready — loop will start in {FORGE_SCHEDULE['company_forge']}s")

    async def _run_company_forge_cycle(self, session: aiohttp.ClientSession):
        """One cycle of the CompanyForge loop: analyze gaps → build next team."""
        if self._pipeline_running or not self._org_board:
            return

        # Circuit breakers
        total_built = len(self.state.company_teams_built)
        total_failed = len(self.state.company_teams_failed)
        if total_built >= COMPANY_MAX_TEAMS:
            print(f"[CompanyForge] Max teams ({COMPANY_MAX_TEAMS}) reached — deactivating")
            self.state.company_forge_active = False
            self._save()
            return

        print(f"\n{'='*60}")
        print(f"  COMPANYFORGE CYCLE — Built: {total_built}, Failed: {total_failed}")
        print(f"{'='*60}")

        try:
            # 1. Query registry for existing validated teams
            registry_entries = await api_get(session, "/api/v1/registry",
                                             params={"status": "validated"})
        except Exception:
            registry_entries = []

        try:
            # 2. Analyze gaps
            gaps, next_spec, is_complete = await self._org_board.analyze_gaps(registry_entries)

            if is_complete or next_spec is None:
                print("[CompanyForge] Company is COMPLETE — all teams built!")
                self.state.company_forge_active = False
                self._save()
                # Post completion + handoffs
                await self._post_company_complete(session, registry_entries)
                return

            # 3. Check retry count for this team
            fail_count = self.state.company_teams_failed.count(next_spec.team_key)
            if fail_count >= self.state.company_max_retries_per_team:
                print(f"[CompanyForge] Skipping {next_spec.team_key} (failed {fail_count} times)")
                # Remove from queue and try next cycle
                if next_spec.team_key in self.state.company_team_queue:
                    self.state.company_team_queue.remove(next_spec.team_key)
                self.state.last_company_forge_time = time.time()
                self._save()
                return

            print(f"[CompanyForge] Building: {next_spec.name} [{next_spec.team_key}]")
            print(f"  Gaps remaining: {len(gaps)}")

            # 4. Build the team
            self._pipeline_running = True
            try:
                slug = re.sub(r'[^a-z0-9]+', '_', next_spec.team_key)[:30].strip('_')
                project_name = f"Company: {slug}"
                run_project_id = await setup_project(session, self.agents, project_name)

                # Use cascade if extending, otherwise fresh build
                cascade_ctx = None
                if next_spec.cascade_from:
                    from .code_processing import load_cascade_context
                    try:
                        cascade_ctx = load_cascade_context(next_spec.cascade_from)
                    except Exception as e:
                        print(f"  [CompanyForge] Cascade load failed: {e}")

                pipeline = SwarmPipeline(
                    self.agents, run_project_id, next_spec.task_description,
                    cascade_from=cascade_ctx,
                    cascade_feature=next_spec.name if cascade_ctx else "",
                )
                success = await pipeline.run(session, next_spec.task_description)

                if success:
                    self.state.company_teams_built.append(next_spec.team_key)
                    if next_spec.team_key in self.state.company_team_queue:
                        self.state.company_team_queue.remove(next_spec.team_key)
                    print(f"[CompanyForge] SUCCESS: {next_spec.team_key}")

                    # Link teams via Minibook
                    try:
                        updated_registry = await api_get(
                            session, "/api/v1/registry", params={"status": "validated"}
                        )
                        registry_key = self.agents.get("RegistryAgent", {}).get("api_key")
                        await self._cross_team_linker.link_teams(
                            session, updated_registry, registry_key
                        )
                    except Exception as e:
                        print(f"  [CompanyForge] Team linking failed: {e}")
                else:
                    self.state.company_teams_failed.append(next_spec.team_key)
                    print(f"[CompanyForge] FAILED: {next_spec.team_key}")

            finally:
                self._pipeline_running = False

            self.state.last_company_forge_time = time.time()
            self._save()

        except Exception as e:
            print(f"[CompanyForge] Cycle error: {e}")
            self.state.last_company_forge_time = time.time()
            self._save()

    async def _post_company_complete(self, session: aiohttp.ClientSession,
                                     registry_entries: list):
        """Post completion summary and generate cross-team handoffs."""
        if self.tracker.can_post("ForgeOrchestrator"):
            built = ", ".join(self.state.company_teams_built)
            failed = ", ".join(set(self.state.company_teams_failed)) if self.state.company_teams_failed else "none"
            await api_post(
                session,
                f"/api/v1/projects/{self.project_id}/posts",
                {
                    "title": "CompanyForge: BUILD COMPLETE",
                    "content": (
                        f"## Company Build Complete\n\n"
                        f"**Teams Built:** {built}\n"
                        f"**Failed/Skipped:** {failed}\n"
                        f"**Total Validated:** {len(self.state.company_teams_built)}\n\n"
                        f"Generating cross-team handoff definitions..."
                    ),
                    "type": "report",
                    "tags": ["company-forge", "complete"],
                },
                api_key=self._key()
            )
            self.tracker.record_post("ForgeOrchestrator")

        # Generate handoffs
        if self._org_board and self._org_board._team_specs:
            try:
                await self._cross_team_linker.post_handoffs(
                    session,
                    self._org_board._team_specs,
                    registry_entries,
                    self.project_id,
                    self._key(),
                )
            except Exception as e:
                print(f"  [CompanyForge] Handoff generation failed: {e}")

    async def _spawn_arch_review(self, session: aiohttp.ClientSession):
        """Post an architecture review request."""
        if not self.tracker.can_post("ForgeOrchestrator"):
            return

        self.state.arch_review_count += 1
        try:
            # Search for recent research posts
            research_context = ""
            try:
                results = await api_get(session, "/api/v1/search",
                                        params={"tag": "autogen-docs", "limit": "3"})
                if results:
                    for r in results[:3]:
                        research_context += f"\n- **{r.get('title', '')}**: {r.get('content', '')[:200]}\n"
            except Exception:
                pass

            # Search for recent benchmark
            benchmark_context = ""
            if self.state.convergence_scores:
                benchmark_context = f"\n\nRecent scores: {self.state.convergence_scores[-5:]}"

            await api_post(
                session,
                f"/api/v1/projects/{self.project_id}/posts",
                {
                    "title": f"Architecture Review #{self.state.arch_review_count}",
                    "content": (
                        f"## Periodic Architecture Review\n\n"
                        f"@ArchitectAgent please review the current architecture approach.\n\n"
                        f"### Recent Research Findings\n{research_context or 'No recent research.'}\n\n"
                        f"### Performance Trend{benchmark_context or ' No benchmarks yet.'}\n\n"
                        f"### Questions\n"
                        f"1. Should we change the conversation pattern (swarm/selector/round_robin)?\n"
                        f"2. Are there better agent role designs based on research?\n"
                        f"3. What improvements would have the most impact?\n"
                    ),
                    "type": "review",
                    "tags": ["arch-review", f"cycle-{self.state.arch_review_count}"],
                },
                api_key=self._key()
            )
            self.tracker.record_post("ForgeOrchestrator")
            self.state.last_arch_review_time = time.time()
            self._save()
            print(f"  [Forge] Architecture Review #{self.state.arch_review_count} posted")
        except Exception as e:
            print(f"  [Forge] Arch review failed: {e}")

    async def _update_grand_plan(self, session: aiohttp.ClientSession):
        """Update the Grand Plan post with current system state."""
        if not self.state.grand_plan_post_id:
            return

        elapsed_h = (time.time() - self.forge_start_time) / 3600
        state_summary = (
            f"Run count: {self.state.run_count}\n"
            f"Fix points detected: {self.state.fix_points_detected}\n"
            f"Recent benchmark scores: {self.state.convergence_scores[-5:]}\n"
            f"Known issues: {self.state.known_issues[-5:]}\n"
            f"Agents online: {len(self.agents)}\n"
            f"Time running: {elapsed_h:.1f}h\n"
            f"Doc topics researched: {self.state.doc_research_index}\n"
            f"Architecture reviews: {self.state.arch_review_count}\n"
            f"Benchmarks: {self.state.benchmark_count}"
        )

        try:
            plan_content = await call_gpt4o(
                FORGE_AGENT_ROLES["ForgeOrchestrator"]["prompt"],
                f"Write an updated Grand Plan based on current state:\n\n{state_summary}",
                max_tokens=1000
            )

            # Update the existing Grand Plan post
            headers = {"Content-Type": "application/json",
                       "Authorization": f"Bearer {self._key()}"}
            async with session.patch(
                f"{MINIBOOK_URL}/api/v1/posts/{self.state.grand_plan_post_id}",
                json={"content": plan_content, "status": "open"},
                headers=headers
            ) as resp:
                if resp.status < 400:
                    self.state.last_grand_plan_time = time.time()
                    self._save()
                    print(f"  [Forge] Grand Plan updated")
        except Exception as e:
            print(f"  [Forge] Grand Plan update failed: {e}")

    async def _detect_stalls(self, session: aiohttp.ClientSession):
        """Find conversations that appear stalled and re-trigger them.
        Only checks the Forge project, not sub-projects from pipeline runs."""
        try:
            posts = await api_get(session, f"/api/v1/projects/{self.project_id}/posts",
                                  params={"status": "open"})
            now = datetime.now()
            for post in posts:
                if post.get("type") not in ("task",):
                    continue
                # Skip pipeline run summary posts (they're informational)
                tags = post.get("tags", [])
                if "forge-run" in tags:
                    continue
                updated = post.get("updated_at", post.get("created_at", ""))
                if not updated:
                    continue
                try:
                    # Minibook returns naive datetime strings (no timezone)
                    updated_dt = datetime.fromisoformat(updated.split("+")[0].split("Z")[0])
                    age = (now - updated_dt).total_seconds()
                except Exception:
                    continue
                if age > STALL_THRESHOLD:
                    # Check if we already posted a recovery comment
                    try:
                        comments = await api_get(session, f"/api/v1/posts/{post['id']}/comments")
                        recovery_exists = any("[FORGE] Stall detected" in c.get("content", "")
                                              for c in comments)
                        if not recovery_exists and self.tracker.can_post("ForgeOrchestrator"):
                            await api_post(
                                session, f"/api/v1/posts/{post['id']}/comments",
                                {"content": f"[FORGE] Stall detected after {int(age)}s. "
                                            f"This conversation may need attention."},
                                api_key=self._key()
                            )
                            self.tracker.record_post("ForgeOrchestrator")
                            print(f"  [Forge] Stall detected: {post['title'][:40]}")
                    except Exception:
                        pass
        except Exception:
            pass

    def _is_converged(self, window: int = 5, threshold: float = 0.02) -> bool:
        """Check if benchmark scores have converged (low variance)."""
        scores = self.state.convergence_scores[-window:]
        if len(scores) < window:
            return False
        if max(scores) == 0:
            return False
        normalized = [(s - min(scores)) / max(1, max(scores) - min(scores)) for s in scores]
        variance = max(normalized) - min(normalized)
        return variance < threshold

    async def _handle_convergence(self, session: aiohttp.ClientSession):
        """Document a fix point and introduce a novel task to escape it."""
        self.state.fix_points_detected += 1
        print(f"\n[Forge] FIX POINT #{self.state.fix_points_detected} detected!")

        if self.tracker.can_post("ForgeOrchestrator"):
            await api_post(
                session,
                f"/api/v1/projects/{self.project_id}/posts",
                {
                    "title": f"Convergence: Fix Point #{self.state.fix_points_detected}",
                    "content": (
                        f"## Emergent Fix Point Detected\n\n"
                        f"The system has converged: benchmark scores are stable.\n\n"
                        f"**Recent Scores:** {self.state.convergence_scores[-5:]}\n"
                        f"**Total Runs:** {self.state.run_count}\n\n"
                        f"Generating a novel task variant to escape this fixed point "
                        f"and explore new solution spaces.\n\n"
                        f"@ForgeOrchestrator will schedule a new pipeline run with a different task."
                    ),
                    "type": "discussion",
                    "tags": ["convergence", f"fixpoint-{self.state.fix_points_detected}"],
                },
                api_key=self._key()
            )
            self.tracker.record_post("ForgeOrchestrator")

        # Advance to a different task
        self._task_index += 1
        self._save()


# --- Forge API ---

class ForgeAPI:
    """Lightweight HTTP API for external control of the Agent Forge."""

    def __init__(self, orchestrator: ForgeOrchestrator):
        self.forge = orchestrator
        self._runner = None

    async def handle_run(self, request):
        """POST /forge/run — Queue a task for the next pipeline cycle."""
        try:
            data = await request.json()
        except Exception:
            return aiohttp_web.json_response({"error": "invalid JSON"}, status=400)
        task = data.get("task", "")
        if not task:
            return aiohttp_web.json_response({"error": "task required"}, status=400)
        self.forge.state.queued_task = task
        self.forge._save()
        return aiohttp_web.json_response({"status": "queued", "task": task})

    async def handle_status(self, request):
        """GET /forge/status — Current forge state."""
        elapsed = time.time() - self.forge.forge_start_time
        return aiohttp_web.json_response({
            "status": "running",
            "uptime_hours": round(elapsed / 3600, 2),
            "run_count": self.forge.state.run_count,
            "fix_points_detected": self.forge.state.fix_points_detected,
            "convergence_scores": self.forge.state.convergence_scores[-10:],
            "known_issues": self.forge.state.known_issues[-5:],
            "pipeline_running": self.forge._pipeline_running,
            "queued_task": self.forge.state.queued_task,
            "agents": len(self.forge.agents),
        })

    async def handle_history(self, request):
        """GET /forge/history — List all output directories."""
        if not OUTPUT_DIR.exists():
            return aiohttp_web.json_response({"runs": []})
        runs = []
        for d in sorted(OUTPUT_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if d.is_dir() and not d.name.startswith("."):
                runs.append({
                    "name": d.name,
                    "modified": datetime.fromtimestamp(d.stat().st_mtime).isoformat(),
                    "files": len(list(d.rglob("*"))),
                })
        return aiohttp_web.json_response({"runs": runs[:50]})

    async def handle_deploy(self, request):
        """POST /forge/deploy — Build and run the latest generated code."""
        output_dirs = sorted(OUTPUT_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        dirs = [d for d in output_dirs if d.is_dir() and not d.name.startswith(".")]
        if not dirs:
            return aiohttp_web.json_response({"error": "no output available"}, status=404)

        latest = dirs[0]
        try:
            build_dir = prepare_docker_context(latest)
            build_result = await docker_build_test(build_dir)
            if build_result["status"] == "PASS":
                run_result = await docker_run_test(build_dir)
                return aiohttp_web.json_response({
                    "deployed": True, "run": latest.name,
                    "build": build_result["status"], "execution": run_result["status"]
                })
            return aiohttp_web.json_response({
                "deployed": False, "error": build_result["output"][-500:]
            })
        except Exception as e:
            return aiohttp_web.json_response({"error": str(e)}, status=500)

    async def handle_company(self, request):
        """POST /forge/company — Activate CompanyForge with a profile path."""
        try:
            data = await request.json()
        except Exception:
            return aiohttp_web.json_response({"error": "invalid JSON"}, status=400)
        profile_path = data.get("profile_path", "")
        if not profile_path or not Path(profile_path).exists():
            return aiohttp_web.json_response({"error": "valid profile_path required"}, status=400)
        async with aiohttp.ClientSession() as session:
            await self.forge._activate_company_forge(profile_path, session)
        return aiohttp_web.json_response({
            "status": "activated",
            "profile": profile_path,
            "teams_planned": len(self.forge.state.company_team_queue),
        })

    async def handle_company_status(self, request):
        """GET /forge/company/status — CompanyForge progress."""
        return aiohttp_web.json_response({
            "active": self.forge.state.company_forge_active,
            "profile_path": self.forge.state.company_profile_path,
            "teams_queue": self.forge.state.company_team_queue,
            "teams_built": self.forge.state.company_teams_built,
            "teams_failed": list(set(self.forge.state.company_teams_failed)),
            "total_built": len(self.forge.state.company_teams_built),
            "total_remaining": len(self.forge.state.company_team_queue),
        })

    async def handle_metrics(self, request):
        """GET /forge/metrics — All benchmark metrics."""
        if FORGE_METRICS_FILE.exists():
            try:
                return aiohttp_web.json_response(json.loads(FORGE_METRICS_FILE.read_text()))
            except Exception:
                pass
        return aiohttp_web.json_response([])

    async def start(self, port: int = FORGE_API_PORT):
        """Start the API server. Tries up to 3 ports if the first is taken."""
        app = aiohttp_web.Application()
        app.router.add_post("/forge/run", self.handle_run)
        app.router.add_get("/forge/status", self.handle_status)
        app.router.add_get("/forge/history", self.handle_history)
        app.router.add_post("/forge/deploy", self.handle_deploy)
        app.router.add_get("/forge/metrics", self.handle_metrics)
        app.router.add_post("/forge/company", self.handle_company)
        app.router.add_get("/forge/company/status", self.handle_company_status)
        self._runner = aiohttp_web.AppRunner(app)
        await self._runner.setup()
        for attempt_port in [port, port + 1, port + 2]:
            try:
                site = aiohttp_web.TCPSite(self._runner, "0.0.0.0", attempt_port)
                await site.start()
                print(f"  [+] Forge API running on http://localhost:{attempt_port}")
                return self._runner
            except OSError:
                print(f"  [!] Port {attempt_port} in use, trying next...")
        print("  [!] Could not start Forge API — all ports in use")
        return self._runner

    async def cleanup(self):
        if self._runner:
            await self._runner.cleanup()

