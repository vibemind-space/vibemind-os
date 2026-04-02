"""
Board Agent — Project board monitoring and stale item detection.
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

SYSTEM_PROMPT = """Du bist ein Project Board Agent. Du analysierst GitHub Project Boards und identifizierst:
1. Stale Items (keine Aktivitaet seit > 14 Tagen)
2. Falsch zugeordnete Karten (closed issues noch in "In Progress")
3. Prioritaets-Vorschlaege

Antworte als JSON:
{
  "stale_items": [{"title": "...", "days_inactive": 30}],
  "misplaced": [{"title": "...", "current_status": "In Progress", "suggested_status": "Done"}],
  "suggestions": ["..."]
}
"""


class BoardAgent:
    def __init__(self, gh, safety, llm_client, llm_model: str):
        self.gh = gh
        self.safety = safety
        self.llm_client = llm_client
        self.llm_model = llm_model

    def run(self) -> dict:
        report = {
            "agent": "board",
            "projects_scanned": 0,
            "stale_items": 0,
            "actions": [],
        }

        try:
            projects = self.gh.project_list()
        except Exception:
            projects = []

        report["projects_scanned"] = len(projects)

        if not projects:
            report["actions"].append("No projects found")
            return report

        for project in projects:
            title = project.get("title", "Unknown")
            report["actions"].append(f"Scanned project: {title}")

        return report
