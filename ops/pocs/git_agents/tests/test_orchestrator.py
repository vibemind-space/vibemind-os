import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from orchestrator import Orchestrator


def _make_orchestrator(repos=None):
    gh = MagicMock()
    gh.repos_list.return_value = repos or []
    gh.issues_list.return_value = []
    gh.pr_list.return_value = []
    gh.workflow_list.return_value = []
    gh.run_list.return_value = []
    gh.release_list.return_value = []
    gh.project_list.return_value = []

    llm_client = MagicMock()
    llm_resp = MagicMock()
    llm_resp.choices = [MagicMock()]
    llm_resp.choices[0].message.content = "[]"
    llm_client.chat.completions.create.return_value = llm_resp

    return Orchestrator(gh=gh, llm_client=llm_client, llm_model="test", dry_run=True)


class TestOrchestrator:
    def test_runs_single_agent(self):
        orch = _make_orchestrator(repos=[{"name": "repo1", "nameWithOwner": "Flissel/repo1"}])
        results = orch.run_agent("triage")
        assert len(results) == 1
        assert results[0]["agent"] == "triage"

    def test_runs_all_agents(self):
        orch = _make_orchestrator(repos=[{"name": "repo1", "nameWithOwner": "Flissel/repo1"}])
        results = orch.run_all()
        # triage(1 repo) + review(1 repo) + cicd(1 repo) + board(1 account-level) = 4
        assert len(results) >= 4

    def test_filters_by_repo(self):
        orch = _make_orchestrator(repos=[
            {"name": "repo1", "nameWithOwner": "Flissel/repo1"},
            {"name": "repo2", "nameWithOwner": "Flissel/repo2"},
        ])
        results = orch.run_agent("triage", repo_filter="Flissel/repo1")
        assert len(results) == 1
        assert results[0]["repo"] == "Flissel/repo1"
