"""
Orchestrator — runs agents across repos, collects reports.
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from gh_client import GhClientError
from utils.safety import SafetyGuard
from agents.triage_agent import TriageAgent
from agents.review_agent import ReviewAgent
from agents.cicd_agent import CicdAgent
from agents.board_agent import BoardAgent


AGENT_MAP = {
    "triage": TriageAgent,
    "review": ReviewAgent,
    "cicd": CicdAgent,
    "board": BoardAgent,
}


class Orchestrator:
    def __init__(self, gh, llm_client, llm_model: str, dry_run: bool = False,
                 auto_approve: bool = False, delete_whitelist: list[str] = None):
        self.gh = gh
        self.llm_client = llm_client
        self.llm_model = llm_model
        self.safety = SafetyGuard(
            delete_whitelist=delete_whitelist or [],
            auto_approve=auto_approve,
            dry_run=dry_run,
        )

    def _make_agent(self, name: str):
        cls = AGENT_MAP[name]
        return cls(gh=self.gh, safety=self.safety, llm_client=self.llm_client, llm_model=self.llm_model)

    def run_agent(self, agent_name: str, repo_filter: str = "") -> list[dict]:
        repos = self.gh.repos_list()
        if repo_filter:
            repos = [r for r in repos if r["nameWithOwner"] == repo_filter]

        agent = self._make_agent(agent_name)
        results = []

        if agent_name == "board":
            results.append(agent.run())
        else:
            for repo in repos:
                repo_name = repo["nameWithOwner"]
                print(f"\n  [{agent_name.upper()}] Scanning {repo_name}...")
                try:
                    result = agent.run(repo_name)
                    results.append(result)
                except GhClientError as e:
                    results.append({
                        "repo": repo_name,
                        "agent": agent_name,
                        "actions": [f"SKIPPED: {e}"],
                    })

        return results

    def run_all(self, repo_filter: str = "") -> list[dict]:
        all_results = []
        for agent_name in AGENT_MAP:
            results = self.run_agent(agent_name, repo_filter=repo_filter)
            all_results.extend(results)
        return all_results

    def format_report(self, results: list[dict]) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("  GIT AGENTS — Report")
        lines.append(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 60)

        for r in results:
            agent = r.get("agent", "unknown")
            repo = r.get("repo", "account-level")
            lines.append(f"\n  [{agent.upper()}] {repo}")

            for key, value in r.items():
                if key in ("agent", "repo", "actions"):
                    continue
                lines.append(f"    {key}: {value}")

            actions = r.get("actions", [])
            if actions:
                lines.append("    Actions:")
                for a in actions:
                    lines.append(f"      - {a}")

        lines.append(f"\n{'=' * 60}")
        lines.append(f"  Total: {len(results)} reports collected")
        lines.append(f"{'=' * 60}")
        return "\n".join(lines)

    def save_report(self, results: list[dict], report_dir: str = "reports"):
        os.makedirs(report_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(report_dir, f"git_agents_{timestamp}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        print(f"  Report saved: {filepath}")
        return filepath
