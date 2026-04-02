"""
CI/CD Agent — Workflow monitoring, failure analysis, release management.
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

SYSTEM_PROMPT = """Du bist ein CI/CD Agent. Du analysierst fehlgeschlagene GitHub Actions Runs.

Antworte als JSON:
{
  "summary": "Was ist passiert",
  "suggestion": "Wie man es fixt"
}
"""


class CicdAgent:
    def __init__(self, gh, safety, llm_client, llm_model: str):
        self.gh = gh
        self.safety = safety
        self.llm_client = llm_client
        self.llm_model = llm_model

    def run(self, repo: str) -> dict:
        report = {
            "repo": repo,
            "agent": "cicd",
            "workflows_checked": 0,
            "failed_runs": 0,
            "releases": [],
            "actions": [],
        }

        workflows = self.gh.workflow_list(repo)
        report["workflows_checked"] = len(workflows)

        if not workflows:
            report["actions"].append("No workflows found")
            return report

        runs = self.gh.run_list(repo)
        failed = [r for r in runs if r.get("conclusion") == "failure"]
        report["failed_runs"] = len(failed)

        for run in failed:
            analysis = self._analyze_failure(run)
            report["actions"].append(
                f"Run #{run['databaseId']} ({run['name']}): FAILED — {analysis.get('summary', 'unknown')}"
            )

        releases = self.gh.release_list(repo)
        report["releases"] = [r.get("tagName", "") for r in releases]

        if not failed:
            report["actions"].append("All runs passing")

        return report

    def _analyze_failure(self, run: dict) -> dict:
        run_info = json.dumps({
            "name": run.get("name"),
            "branch": run.get("headBranch"),
            "created": run.get("createdAt"),
            "conclusion": run.get("conclusion"),
        }, ensure_ascii=False)

        response = self.llm_client.chat.completions.create(
            model=self.llm_model,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Analysiere diesen fehlgeschlagenen Run:\n\n{run_info}"},
            ],
        )

        content = response.choices[0].message.content or ""
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            try:
                return json.loads(content[json_start:json_end])
            except json.JSONDecodeError:
                pass
        return {"summary": "Could not analyze", "suggestion": "Check logs manually"}
