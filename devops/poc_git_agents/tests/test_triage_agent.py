import json
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agents.triage_agent import TriageAgent


def _make_agent(issues=None, labels=None, llm_response="[]"):
    gh = MagicMock()
    gh.issues_list.return_value = issues or []
    gh.labels_list.return_value = labels or []
    gh.issue_edit.return_value = ""
    gh.label_create.return_value = ""

    safety = MagicMock()
    safety.can_execute.return_value = True
    safety.dry_run = False

    llm_client = MagicMock()
    llm_resp = MagicMock()
    llm_resp.choices = [MagicMock()]
    llm_resp.choices[0].message.content = llm_response
    llm_client.chat.completions.create.return_value = llm_resp

    return TriageAgent(gh=gh, safety=safety, llm_client=llm_client, llm_model="test-model")


class TestTriageClassify:
    def test_classifies_bug(self):
        llm_resp = json.dumps([{"number": 1, "labels": ["bug"], "priority": "high", "reason": "crash report"}])
        agent = _make_agent(
            issues=[{"number": 1, "title": "App crashes on start", "body": "crash", "labels": [], "comments": []}],
            llm_response=llm_resp,
        )
        report = agent.run("Flissel/repo1")
        assert report["repo"] == "Flissel/repo1"
        assert report["issues_scanned"] == 1

    def test_skips_already_labeled(self):
        agent = _make_agent(
            issues=[{"number": 1, "title": "Bug", "body": "", "labels": [{"name": "bug"}], "comments": []}],
        )
        report = agent.run("Flissel/repo1")
        assert report["issues_scanned"] == 1
        assert report["labels_applied"] == 0


class TestTriageDuplicateDetection:
    def test_detects_duplicates(self):
        llm_resp = json.dumps([
            {"number": 1, "labels": ["bug"], "priority": "high", "reason": "crash"},
            {"number": 2, "labels": ["bug", "duplicate"], "priority": "low", "reason": "duplicate of #1", "duplicate_of": 1},
        ])
        agent = _make_agent(
            issues=[
                {"number": 1, "title": "App crashes", "body": "crash on start", "labels": [], "comments": []},
                {"number": 2, "title": "App crash bug", "body": "crashes when opening", "labels": [], "comments": []},
            ],
            llm_response=llm_resp,
        )
        report = agent.run("Flissel/repo1")
        assert report["issues_scanned"] == 2
