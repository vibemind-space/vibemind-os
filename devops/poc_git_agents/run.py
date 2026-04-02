"""
Git Agents CLI — Manage GitHub repos with AI-powered agents.

Usage:
    python poc_git_agents/run.py triage              # Run triage agent
    python poc_git_agents/run.py review              # Run review agent
    python poc_git_agents/run.py cicd                # Run CI/CD agent
    python poc_git_agents/run.py board               # Run board agent
    python poc_git_agents/run.py all                 # Run all agents
    python poc_git_agents/run.py all --repo X        # Target specific repo
    python poc_git_agents/run.py all --dry-run       # Preview only
    python poc_git_agents/run.py all --json          # JSON output
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import yaml
from llm_client import get_client_sync, get_model
from gh_client import GhClient
from orchestrator import Orchestrator


def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yml")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Git Agents — AI-powered GitHub management")
    parser.add_argument("agent", choices=["triage", "review", "cicd", "board", "all"],
                        help="Which agent to run")
    parser.add_argument("--repo", type=str, default="", help="Target specific repo (e.g. Flissel/repo)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")
    args = parser.parse_args()

    config = load_config()
    safety_cfg = config.get("safety", {})
    scan_cfg = config.get("scan", {})
    output_cfg = config.get("output", {})

    gh = GhClient(
        owner="Flissel",
        skip_repos=scan_cfg.get("skip_repos", []),
        timeout=30,
    )

    llm_client = get_client_sync("default")
    llm_model = get_model("default")

    orch = Orchestrator(
        gh=gh,
        llm_client=llm_client,
        llm_model=llm_model,
        dry_run=args.dry_run,
        auto_approve=safety_cfg.get("auto_approve", False),
        delete_whitelist=safety_cfg.get("delete_whitelist", []),
    )

    if args.agent == "all":
        results = orch.run_all(repo_filter=args.repo)
    else:
        results = orch.run_agent(args.agent, repo_filter=args.repo)

    if args.json_output:
        print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    else:
        print(orch.format_report(results))

    if output_cfg.get("save_report", False):
        report_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), output_cfg.get("report_dir", "reports"))
        orch.save_report(results, report_dir)


if __name__ == "__main__":
    main()
