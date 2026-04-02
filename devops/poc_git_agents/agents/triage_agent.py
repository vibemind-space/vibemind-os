"""
Triage Agent — Issue labeling, duplicate detection, prioritization.
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

SYSTEM_PROMPT = """Du bist ein Issue Triage Agent. Du analysierst GitHub Issues und gibst fuer jedes:
1. Labels (bug, feature, question, documentation, enhancement, duplicate, wontfix)
2. Priority (critical, high, medium, low)
3. Reason (kurze Begruendung)
4. Optional: duplicate_of (Issue-Nummer wenn Duplikat)

Antworte als JSON Array:
[
  {"number": 1, "labels": ["bug"], "priority": "high", "reason": "Crash report with stack trace"},
  {"number": 2, "labels": ["bug", "duplicate"], "priority": "low", "reason": "Same as #1", "duplicate_of": 1}
]

Regeln:
- NUR Issues labeln die NOCH KEINE Labels haben (oder nur default-Labels)
- Duplikate erkennen anhand von Titel- und Body-Aehnlichkeit
- Priority: critical = security/data loss, high = broken feature, medium = inconvenience, low = cosmetic
"""


class TriageAgent:
    def __init__(self, gh, safety, llm_client, llm_model: str):
        self.gh = gh
        self.safety = safety
        self.llm_client = llm_client
        self.llm_model = llm_model

    def run(self, repo: str) -> dict:
        report = {
            "repo": repo,
            "agent": "triage",
            "issues_scanned": 0,
            "labels_applied": 0,
            "duplicates_found": 0,
            "actions": [],
        }

        issues = self.gh.issues_list(repo)
        report["issues_scanned"] = len(issues)

        if not issues:
            return report

        unlabeled = [i for i in issues if not i.get("labels")]
        already_labeled = len(issues) - len(unlabeled)

        if not unlabeled:
            report["actions"].append(f"All {already_labeled} issues already labeled")
            return report

        classifications = self._classify(unlabeled)

        for cls in classifications:
            number = cls.get("number")
            labels = cls.get("labels", [])
            priority = cls.get("priority", "medium")
            duplicate_of = cls.get("duplicate_of")

            if not labels:
                continue

            all_labels = labels + [f"priority-{priority}"]

            if self.safety.can_execute("label_add", repo):
                self.gh.issue_edit(repo, number, add_labels=all_labels)
                report["labels_applied"] += 1
                report["actions"].append(f"#{number}: labeled {all_labels}")

            if duplicate_of and "duplicate" in labels:
                report["duplicates_found"] += 1
                if self.safety.can_execute("comment", repo):
                    self.gh.issue_comment(repo, number, f"Possible duplicate of #{duplicate_of}")
                    report["actions"].append(f"#{number}: marked duplicate of #{duplicate_of}")

        return report

    def _classify(self, issues: list[dict]) -> list[dict]:
        issues_text = json.dumps([
            {"number": i["number"], "title": i["title"], "body": (i.get("body") or "")[:500]}
            for i in issues
        ], ensure_ascii=False, indent=2)

        response = self.llm_client.chat.completions.create(
            model=self.llm_model,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Klassifiziere diese Issues:\n\n{issues_text}"},
            ],
        )

        content = response.choices[0].message.content or ""
        json_start = content.find("[")
        json_end = content.rfind("]") + 1
        if json_start >= 0 and json_end > json_start:
            try:
                return json.loads(content[json_start:json_end])
            except json.JSONDecodeError:
                pass
        return []
