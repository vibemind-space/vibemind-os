import json
import subprocess
from unittest.mock import patch, MagicMock
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gh_client import GhClient, GhClientError


def _mock_run(stdout="", returncode=0):
    result = MagicMock()
    result.stdout = stdout
    result.returncode = returncode
    result.stderr = ""
    return result


class TestGhClientReposList:
    @patch("subprocess.run")
    def test_returns_list_of_repos(self, mock_run):
        mock_run.return_value = _mock_run(
            stdout=json.dumps([{"name": "repo1", "nameWithOwner": "Flissel/repo1"}])
        )
        client = GhClient()
        repos = client.repos_list()
        assert len(repos) == 1
        assert repos[0]["name"] == "repo1"

    @patch("subprocess.run")
    def test_filters_skip_repos(self, mock_run):
        mock_run.return_value = _mock_run(
            stdout=json.dumps([
                {"name": "repo1", "nameWithOwner": "Flissel/repo1"},
                {"name": ".github", "nameWithOwner": "Flissel/.github"},
            ])
        )
        client = GhClient(skip_repos=[".github"])
        repos = client.repos_list()
        assert len(repos) == 1
        assert repos[0]["name"] == "repo1"


class TestGhClientIssuesList:
    @patch("subprocess.run")
    def test_returns_issues(self, mock_run):
        mock_run.return_value = _mock_run(
            stdout=json.dumps([{"number": 1, "title": "Bug"}])
        )
        client = GhClient()
        issues = client.issues_list("Flissel/repo1")
        assert len(issues) == 1
        assert issues[0]["title"] == "Bug"


class TestGhClientErrors:
    @patch("subprocess.run")
    def test_raises_on_nonzero_exit(self, mock_run):
        result = _mock_run(returncode=1)
        result.stderr = "not found"
        mock_run.return_value = result
        client = GhClient()
        with pytest.raises(GhClientError, match="not found"):
            client.repos_list()
