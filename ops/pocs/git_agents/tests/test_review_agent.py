import json
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agents.review_agent import ReviewAgent


def _make_agent(prs=None, diff="", llm_response="{}"):
    gh = MagicMock()
    gh.pr_list.return_value = prs or []
    gh.pr_diff.return_value = diff
    gh.pr_review.return_value = ""

    safety = MagicMock()
    safety.can_execute.return_value = True
    safety.dry_run = False

    llm_client = MagicMock()
    llm_resp = MagicMock()
    llm_resp.choices = [MagicMock()]
    llm_resp.choices[0].message.content = llm_response
    llm_client.chat.completions.create.return_value = llm_resp

    return ReviewAgent(gh=gh, safety=safety, llm_client=llm_client, llm_model="test-model")


class TestReviewAgent:
    def test_reviews_open_prs(self):
        llm_resp = json.dumps({
            "summary": "Adds logging",
            "issues": [],
            "verdict": "approve",
        })
        agent = _make_agent(
            prs=[{"number": 1, "title": "Add logging", "body": "", "author": {"login": "dev"},
                  "headRefName": "feat/log", "baseRefName": "main", "additions": 10, "deletions": 2,
                  "files": [{"path": "log.py"}], "reviews": []}],
            diff="+ import logging",
            llm_response=llm_resp,
        )
        report = agent.run("Flissel/repo1")
        assert report["prs_scanned"] == 1
        assert report["reviews_posted"] == 1

    def test_skips_already_reviewed(self):
        agent = _make_agent(
            prs=[{"number": 1, "title": "Fix", "body": "", "author": {"login": "dev"},
                  "headRefName": "fix/x", "baseRefName": "main", "additions": 1, "deletions": 1,
                  "files": [{"path": "x.py"}],
                  "reviews": [{"author": {"login": "git-agent"}, "state": "COMMENTED"}]}],
        )
        report = agent.run("Flissel/repo1")
        assert report["reviews_posted"] == 0

    def test_no_prs_returns_empty_report(self):
        agent = _make_agent(prs=[])
        report = agent.run("Flissel/repo1")
        assert report["prs_scanned"] == 0
