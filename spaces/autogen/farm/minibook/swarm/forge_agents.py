"""Forge agents — specialized agents for the continuous Agent Forge system."""

import asyncio
import json
import os
import re
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from pathlib import Path

import aiohttp

from .constants import (
    MINIBOOK_URL, FORGE_STATE_FILE, FORGE_HOURLY_BUDGET, OUTPUT_DIR,
    DOC_RESEARCH_TOPICS,
)
from .knowledge import FORGE_AGENT_ROLES
from .api_client import api_post, api_get
from .llm import call_gpt4o


@dataclass
class ForgeState:
    run_count: int = 0
    last_run_time: float = 0.0
    last_benchmark_time: float = 0.0
    last_doc_research_time: float = 0.0
    last_security_scan_time: float = 0.0
    last_dep_check_time: float = 0.0
    last_arch_review_time: float = 0.0
    last_grand_plan_time: float = 0.0
    last_repo_commit_time: float = 0.0
    convergence_scores: list = field(default_factory=list)
    known_issues: list = field(default_factory=list)
    grand_plan_post_id: str = ""
    queued_task: str = ""
    fix_points_detected: int = 0
    doc_research_index: int = 0  # cycles through DOC_RESEARCH_TOPICS
    arch_review_count: int = 0
    benchmark_count: int = 0
    # CompanyForge state
    company_forge_active: bool = False
    company_profile_path: str = ""
    last_company_forge_time: float = 0.0
    company_team_queue: list = field(default_factory=list)
    company_teams_built: list = field(default_factory=list)
    company_teams_failed: list = field(default_factory=list)
    company_max_retries_per_team: int = 3


def load_forge_state() -> ForgeState:
    if FORGE_STATE_FILE.exists():
        try:
            data = json.loads(FORGE_STATE_FILE.read_text())
            return ForgeState(**{k: v for k, v in data.items() if k in ForgeState.__dataclass_fields__})
        except Exception:
            pass
    return ForgeState()


def save_forge_state(state: ForgeState):
    FORGE_STATE_FILE.write_text(json.dumps(asdict(state), indent=2))


# --- Forge Utility: Rate-Limited Posting ---

class ForgePostTracker:
    """Track post/comment rates per agent to stay within Minibook limits."""

    def __init__(self):
        self._posts: dict[str, deque] = {}  # agent_name -> timestamps
        self._error_counts: dict[str, int] = {}  # agent_name -> consecutive errors
        self._quarantine_until: dict[str, float] = {}  # agent_name -> quarantine end time

    def can_post(self, agent_name: str) -> bool:
        now = time.time()
        # Check quarantine
        if agent_name in self._quarantine_until:
            if now < self._quarantine_until[agent_name]:
                return False
            del self._quarantine_until[agent_name]
            self._error_counts[agent_name] = 0
        # Check hourly budget
        budget = FORGE_HOURLY_BUDGET.get(agent_name, 30)
        if agent_name not in self._posts:
            self._posts[agent_name] = deque(maxlen=budget)
        q = self._posts[agent_name]
        # Remove entries older than 1 hour
        while q and (now - q[0]) > 3600:
            q.popleft()
        return len(q) < budget

    def record_post(self, agent_name: str):
        if agent_name not in self._posts:
            self._posts[agent_name] = deque(maxlen=FORGE_HOURLY_BUDGET.get(agent_name, 30))
        self._posts[agent_name].append(time.time())

    def record_error(self, agent_name: str):
        self._error_counts[agent_name] = self._error_counts.get(agent_name, 0) + 1
        if self._error_counts[agent_name] >= 3:
            self._quarantine_until[agent_name] = time.time() + 1800  # 30 min
            print(f"  [Forge] {agent_name} quarantined for 30min (3 consecutive errors)")

    def record_success(self, agent_name: str):
        self._error_counts[agent_name] = 0


# --- DocResearcherAgent ---

class DocResearcherAgent:
    """Fetches AutoGen documentation from GitHub API and posts findings to Minibook."""

    AUTOGEN_API = "https://api.github.com/repos/microsoft/autogen"

    def __init__(self, agents: dict, project_id: str, tracker: ForgePostTracker):
        self.agents = agents
        self.project_id = project_id
        self.tracker = tracker

    def _key(self) -> str:
        return self.agents["DocResearcherAgent"]["api_key"]

    def _github_headers(self) -> dict:
        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "AgentForge"}
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            headers["Authorization"] = f"token {token}"
        return headers

    async def fetch_doc_content(self, session: aiohttp.ClientSession, path: str) -> str:
        """Fetch a file from the AutoGen GitHub repo."""
        url = f"{self.AUTOGEN_API}/contents/python/packages/{path}"
        try:
            async with session.get(url, headers=self._github_headers()) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json()
                if data.get("encoding") == "base64":
                    import base64
                    return base64.b64decode(data["content"]).decode(errors="replace")
                return data.get("content", "")
        except Exception as e:
            print(f"  [DocResearcher] GitHub fetch failed: {e}")
            return ""

    async def web_search_fallback(self, session: aiohttp.ClientSession, topic: str) -> str:
        """Fallback: search via MCP Gateway if GitHub rate-limited."""
        try:
            async with session.post(
                f"http://localhost:{MCP_GATEWAY_PORT}/tools/call",
                json={"name": "web_search", "arguments": {
                    "query": f"AutoGen AgentChat {topic} python documentation 2025"
                }},
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data.get("content", [])
                    if content and isinstance(content, list):
                        return content[0].get("text", "")[:3000]
        except Exception:
            pass
        return ""

    async def run_research_cycle(self, session: aiohttp.ClientSession, topic: str):
        """Full research cycle: fetch -> summarize -> post to Minibook."""
        if not self.tracker.can_post("DocResearcherAgent"):
            return

        print(f"  [DocResearcher] Researching: {topic}")

        # Try GitHub first — if topic already has an extension, use it directly
        if "." in topic.split("/")[-1]:
            content = await self.fetch_doc_content(session, topic)
        else:
            content = await self.fetch_doc_content(session, topic + ".py")
            if not content:
                content = await self.fetch_doc_content(session, topic + ".md")
        if not content:
            content = await self.web_search_fallback(session, topic.replace("/", " "))

        if not content or len(content) < 50:
            print(f"  [DocResearcher] No content found for {topic}")
            self.tracker.record_error("DocResearcherAgent")
            return

        # Summarize via GPT-4o
        summary = await call_gpt4o(
            FORGE_AGENT_ROLES["DocResearcherAgent"]["prompt"],
            f"Summarize this AutoGen documentation into actionable code patterns:\n\n"
            f"Topic: {topic}\n\n{content[:5000]}",
            max_tokens=1500
        )

        # Post to Minibook
        await api_post(
            session,
            f"/api/v1/projects/{self.project_id}/posts",
            {
                "title": f"Research: AutoGen {topic.split('/')[-1]}",
                "content": (
                    f"## AutoGen Documentation Research\n\n"
                    f"**Topic:** {topic}\n"
                    f"**Source:** microsoft/autogen GitHub\n\n"
                    f"### Findings\n\n{summary}\n\n"
                    f"@ArchitectAgent @CoderAgent relevant patterns found above."
                ),
                "type": "research",
                "tags": ["autogen-docs", f"topic:{topic.split('/')[-1]}"],
            },
            api_key=self._key()
        )
        self.tracker.record_post("DocResearcherAgent")
        self.tracker.record_success("DocResearcherAgent")
        print(f"  [DocResearcher] Posted research: {topic}")


# --- DependencyAgent ---

class DependencyAgent:
    """Validates Python dependencies in generated code."""

    def __init__(self, agents: dict, project_id: str, tracker: ForgePostTracker):
        self.agents = agents
        self.project_id = project_id
        self.tracker = tracker

    def _key(self) -> str:
        return self.agents["DependencyAgent"]["api_key"]

    async def validate_requirements(self, req_content: str) -> dict:
        """Run pip install --dry-run to check compatibility."""
        packages = [
            line.strip() for line in req_content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not packages:
            return {"status": "PASS", "message": "No packages to validate", "issues": []}

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "--dry-run", "--quiet", *packages,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            output = stdout.decode(errors="replace") + stderr.decode(errors="replace")
            has_issues = proc.returncode != 0
            return {
                "status": "FAIL" if has_issues else "PASS",
                "output": output[:2000],
                "issues": [line for line in output.splitlines() if "ERROR" in line or "WARN" in line.upper()],
                "packages": packages,
            }
        except asyncio.TimeoutError:
            return {"status": "WARN", "message": "pip dry-run timed out", "issues": ["timeout"]}
        except Exception as e:
            return {"status": "ERROR", "message": str(e), "issues": [str(e)]}

    async def run_dep_cycle(self, session: aiohttp.ClientSession):
        """Validate latest output's requirements.txt."""
        if not self.tracker.can_post("DependencyAgent"):
            return

        output_dirs = sorted(OUTPUT_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not output_dirs:
            return

        latest = output_dirs[0]
        req_file = latest / "requirements.txt"
        if not req_file.exists():
            return

        print(f"  [DepAgent] Validating deps for {latest.name}")
        result = await self.validate_requirements(req_file.read_text())

        analysis = await call_gpt4o(
            FORGE_AGENT_ROLES["DependencyAgent"]["prompt"],
            f"pip install --dry-run results:\n\n{json.dumps(result, indent=2)}",
            max_tokens=800
        )

        mention = ""
        if result["status"] == "FAIL":
            mention = "\n\n@CoderAgent dependency issues found - please fix in next iteration."

        await api_post(
            session,
            f"/api/v1/projects/{self.project_id}/posts",
            {
                "title": f"Dependency Check: {latest.name[:40]}",
                "content": f"## Dependency Validation Report\n\n{analysis}{mention}",
                "type": "report",
                "tags": ["deps", f"run-{latest.name[:30]}"],
            },
            api_key=self._key()
        )
        self.tracker.record_post("DependencyAgent")
        self.tracker.record_success("DependencyAgent")
        print(f"  [DepAgent] Posted report: {result['status']}")


# --- SecurityAgent ---

class SecurityAgent:
    """Reviews generated code for security vulnerabilities."""

    def __init__(self, agents: dict, project_id: str, tracker: ForgePostTracker):
        self.agents = agents
        self.project_id = project_id
        self.tracker = tracker

    def _key(self) -> str:
        return self.agents["SecurityAgent"]["api_key"]

    async def run_security_cycle(self, session: aiohttp.ClientSession):
        """Scan latest output for security issues."""
        if not self.tracker.can_post("SecurityAgent"):
            return

        output_dirs = sorted(OUTPUT_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not output_dirs:
            return

        latest = output_dirs[0]
        src_dir = latest / "src"
        if not src_dir.exists():
            return

        # Collect all Python code
        code_content = ""
        for py_file in sorted(src_dir.glob("*.py")):
            code_content += f"\n\n### FILE: {py_file.name}\n```python\n{py_file.read_text(errors='replace')}\n```\n"

        if not code_content:
            return

        # Also check Docker files
        for df in ["Dockerfile", "docker-compose.yml"]:
            fp = latest / "docker" / df
            if not fp.exists():
                fp = latest / df
            if fp.exists():
                code_content += f"\n\n### FILE: {df}\n```\n{fp.read_text(errors='replace')}\n```\n"

        print(f"  [SecurityAgent] Scanning {latest.name}")
        analysis = await call_gpt4o(
            FORGE_AGENT_ROLES["SecurityAgent"]["prompt"],
            f"Review this generated code for security issues:\n{code_content[:8000]}",
            max_tokens=1500
        )

        is_critical = "CRITICAL" in analysis and "SECURITY_VERDICT: FAIL" in analysis
        mentions = "@ForgeOrchestrator security scan complete."
        if is_critical:
            mentions = "@CoderAgent @ReviewerAgent @ValidatorAgent @ForgeOrchestrator CRITICAL security issues found!"

        await api_post(
            session,
            f"/api/v1/projects/{self.project_id}/posts",
            {
                "title": f"Security Scan: {latest.name[:40]}",
                "content": f"## Security Review\n\n{analysis}\n\n{mentions}",
                "type": "report",
                "tags": ["security"] + (["critical"] if is_critical else []),
            },
            api_key=self._key()
        )
        self.tracker.record_post("SecurityAgent")
        self.tracker.record_success("SecurityAgent")
        print(f"  [SecurityAgent] Posted scan: {'CRITICAL' if is_critical else 'OK'}")


# --- BenchmarkAgent ---

class BenchmarkAgent:
    """Measures code quality metrics and tracks improvement over time."""

    def __init__(self, agents: dict, project_id: str, tracker: ForgePostTracker):
        self.agents = agents
        self.project_id = project_id
        self.tracker = tracker

    def _key(self) -> str:
        return self.agents["BenchmarkAgent"]["api_key"]

    def _load_history(self) -> list:
        if FORGE_METRICS_FILE.exists():
            try:
                return json.loads(FORGE_METRICS_FILE.read_text())
            except Exception:
                pass
        return []

    def _save_history(self, history: list):
        FORGE_METRICS_FILE.write_text(json.dumps(history[-50:], indent=2))  # keep last 50

    async def measure_output(self, output_path: Path) -> dict:
        """Compute metrics for a generated output directory."""
        src_dir = output_path / "src"
        py_files = list(src_dir.glob("*.py")) if src_dir.exists() else []
        yaml_files = list(output_path.glob("**/*.yml")) + list(output_path.glob("**/*.yaml"))

        total_loc = 0
        tool_count = 0
        async_tool_count = 0
        import_count = 0
        for f in py_files:
            try:
                text = f.read_text(errors="replace")
                lines = text.splitlines()
                total_loc += len(lines)
                tool_count += len(re.findall(r'def \w+\(', text))
                async_tool_count += len(re.findall(r'async def \w+\(', text))
                import_count += len([l for l in lines if l.strip().startswith(("import ", "from "))])
            except Exception:
                pass

        return {
            "run_id": output_path.name,
            "timestamp": time.time(),
            "python_files": len(py_files),
            "yaml_files": len(yaml_files),
            "lines_of_code": total_loc,
            "total_functions": tool_count,
            "async_functions": async_tool_count,
            "imports": import_count,
            "score": round(total_loc / max(1, len(py_files)) + async_tool_count * 5, 2),
        }

    async def run_benchmark_cycle(self, session: aiohttp.ClientSession) -> float:
        """Measure latest output, post report, return score for convergence."""
        if not self.tracker.can_post("BenchmarkAgent"):
            return -1.0

        output_dirs = sorted(OUTPUT_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not output_dirs:
            return -1.0

        latest = output_dirs[0]
        metrics = await self.measure_output(latest)

        history = self._load_history()
        prev = history[-1] if history else None

        analysis = await call_gpt4o(
            FORGE_AGENT_ROLES["BenchmarkAgent"]["prompt"],
            f"Current metrics:\n{json.dumps(metrics, indent=2)}\n\n"
            f"Previous run:\n{json.dumps(prev, indent=2) if prev else 'First run — no history'}\n\n"
            f"History (last 5):\n{json.dumps(history[-5:], indent=2)}",
            max_tokens=800
        )

        history.append(metrics)
        self._save_history(history)

        await api_post(
            session,
            f"/api/v1/projects/{self.project_id}/posts",
            {
                "title": f"Benchmark Report #{len(history)}",
                "content": (
                    f"## Benchmark Results\n\n{analysis}\n\n"
                    f"**Score:** {metrics['score']}\n"
                    f"**LOC:** {metrics['lines_of_code']} | "
                    f"**Files:** {metrics['python_files']} | "
                    f"**Async Tools:** {metrics['async_functions']}\n\n"
                    f"@ForgeOrchestrator metrics attached."
                ),
                "type": "report",
                "tags": ["benchmark", f"run-{len(history)}"],
            },
            api_key=self._key()
        )
        self.tracker.record_post("BenchmarkAgent")
        self.tracker.record_success("BenchmarkAgent")
        print(f"  [BenchmarkAgent] Report #{len(history)}: score={metrics['score']}")
        return metrics["score"]


# --- RepoAgent ---

class RepoAgent:
    """Manages git repository of generated agent code."""

    def __init__(self, agents: dict, project_id: str, tracker: ForgePostTracker):
        self.agents = agents
        self.project_id = project_id
        self.tracker = tracker
        self.repo_path = OUTPUT_DIR

    def _key(self) -> str:
        return self.agents["RepoAgent"]["api_key"]

    async def _git(self, *args) -> tuple:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=str(self.repo_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await proc.communicate()
        return proc.returncode, stdout.decode(errors="replace")

    async def ensure_repo(self):
        """Initialize git repo if not already one."""
        self.repo_path.mkdir(parents=True, exist_ok=True)
        rc, _ = await self._git("status")
        if rc != 0:
            await self._git("init")
            await self._git("config", "user.email", "forge@agentforge.local")
            await self._git("config", "user.name", "AgentForge")
            print("  [RepoAgent] Initialized git repo")

    async def run_repo_cycle(self, session: aiohttp.ClientSession):
        """Commit any new changes in the output directory."""
        if not self.tracker.can_post("RepoAgent"):
            return

        await self.ensure_repo()

        # Check for changes
        rc, status = await self._git("status", "--porcelain")
        if rc != 0 or not status.strip():
            return  # No changes

        # Stage and commit
        await self._git("add", "-A")
        rc, diff_stat = await self._git("diff", "--cached", "--stat")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        msg = f"forge: auto-commit {timestamp}"
        rc, out = await self._git("commit", "-m", msg)
        if rc != 0:
            self.tracker.record_error("RepoAgent")
            return

        # Get recent log
        rc, log = await self._git("log", "--oneline", "-5")

        await api_post(
            session,
            f"/api/v1/projects/{self.project_id}/posts",
            {
                "title": f"Repo Update: {timestamp}",
                "content": (
                    f"## Repository Committed\n\n"
                    f"**Changes:**\n```\n{diff_stat[:500]}\n```\n\n"
                    f"**Recent History:**\n```\n{log[:500]}\n```\n\n"
                    f"@ForgeOrchestrator commit complete."
                ),
                "type": "report",
                "tags": ["repo", "commit"],
            },
            api_key=self._key()
        )
        self.tracker.record_post("RepoAgent")
        self.tracker.record_success("RepoAgent")
        print(f"  [RepoAgent] Committed changes: {timestamp}")

