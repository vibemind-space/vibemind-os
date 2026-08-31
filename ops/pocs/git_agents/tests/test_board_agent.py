import json
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agents.board_agent import BoardAgent


def _make_agent(projects=None, llm_response="{}"):
    gh = MagicMock()
    gh.project_list.return_value = projects or []

    safety = MagicMock()
    safety.can_execute.return_value = True
    safety.dry_run = False

    llm_client = MagicMock()
    llm_resp = MagicMock()
    llm_resp.choices = [MagicMock()]
    llm_resp.choices[0].message.content = llm_response
    llm_client.chat.completions.create.return_value = llm_resp

    return BoardAgent(gh=gh, safety=safety, llm_client=llm_client, llm_model="test-model")


class TestBoardAgent:
    def test_scans_projects(self):
        agent = _make_agent(
            projects=[{"number": 1, "title": "Dev Board", "shortDescription": "tracking"}],
        )
        report = agent.run()
        assert report["projects_scanned"] == 1

    def test_no_projects(self):
        agent = _make_agent(projects=[])
        report = agent.run()
        assert report["projects_scanned"] == 0
        assert "No projects found" in report["actions"][0]
