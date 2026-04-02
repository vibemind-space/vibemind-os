import json
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agents.cicd_agent import CicdAgent


def _make_agent(workflows=None, runs=None, releases=None, llm_response="{}"):
    gh = MagicMock()
    gh.workflow_list.return_value = workflows or []
    gh.run_list.return_value = runs or []
    gh.release_list.return_value = releases or []

    safety = MagicMock()
    safety.can_execute.return_value = True
    safety.dry_run = False

    llm_client = MagicMock()
    llm_resp = MagicMock()
    llm_resp.choices = [MagicMock()]
    llm_resp.choices[0].message.content = llm_response
    llm_client.chat.completions.create.return_value = llm_resp

    return CicdAgent(gh=gh, safety=safety, llm_client=llm_client, llm_model="test-model")


class TestCicdAgent:
    def test_reports_failed_runs(self):
        agent = _make_agent(
            workflows=[{"name": "CI", "id": 1, "state": "active"}],
            runs=[
                {"databaseId": 100, "name": "CI", "status": "completed", "conclusion": "failure",
                 "headBranch": "main", "createdAt": "2026-03-27T10:00:00Z"},
            ],
            llm_response=json.dumps({"summary": "Build failed due to missing dep", "suggestion": "Add dep to requirements.txt"}),
        )
        report = agent.run("Flissel/repo1")
        assert report["workflows_checked"] == 1
        assert report["failed_runs"] == 1

    def test_all_passing(self):
        agent = _make_agent(
            workflows=[{"name": "CI", "id": 1, "state": "active"}],
            runs=[
                {"databaseId": 100, "name": "CI", "status": "completed", "conclusion": "success",
                 "headBranch": "main", "createdAt": "2026-03-27T10:00:00Z"},
            ],
        )
        report = agent.run("Flissel/repo1")
        assert report["failed_runs"] == 0

    def test_no_workflows(self):
        agent = _make_agent(workflows=[], runs=[])
        report = agent.run("Flissel/repo1")
        assert report["workflows_checked"] == 0
