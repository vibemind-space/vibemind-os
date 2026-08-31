"""
Issue Agent — Autonomous Report-to-GitHub-Issues Pipeline
=============================================================
Reads Red/Blue exercise reports, analyzes gaps, and creates
GitHub Issues with kernel/OS hardening recommendations.

Runs automatically after each exercise or manually:
  python issue_agent.py                    # Process all unprocessed reports
  python issue_agent.py --report round_01  # Process specific round
  python issue_agent.py --dry-run          # Preview without creating issues
"""

import argparse
import glob
import json
import logging
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from llm_client import get_client_sync, get_model

logging.getLogger("paramiko").setLevel(logging.CRITICAL)

REPORT_DIR = os.path.join(os.path.dirname(__file__), "reports")
PROCESSED_FILE = os.path.join(REPORT_DIR, ".processed_reports.json")
REPO = "Flissel/vibemind-os"

SYSTEM_PROMPT = """Du bist ein Security Architect der Red/Blue Exercise Reports analysiert und daraus GitHub Issues fuer OS-Hardening ableitet.

Fuer jeden Report erhaeltst du:
- Red Team Angriffe (was wurde ausgefuehrt, welche Kategorie)
- Blue Team Findings (was wurde erkannt)
- Judge Verdict (Detection Rate, Gaps, Empfehlungen)

Deine Aufgabe:
1. Identifiziere JEDE Sicherheitsluecke die der Report aufzeigt
2. Fuer jede Luecke: erstelle ein GitHub Issue mit Kernel- oder OS-Level Loesung
3. Keine App-Level Fixes — nur Kernel-Module, LSM Policies, Syscall-Filter, OS-Config

Antworte IMMER als JSON Array:
```json
[
  {
    "title": "[KERNEL|OS] Kurze Beschreibung",
    "labels": ["kernel-hardening|os-policy", "priority-critical|priority-high", "from-exercise", "detection-gap?"],
    "body": {
      "source": "Runde X — Tool-Name",
      "problem": "Was passiert ist",
      "attack_pattern": "Code/Command des Angriffs",
      "kernel_solution": "Konkrete Kernel/OS Loesung",
      "acceptance_criteria": ["Kriterium 1", "Kriterium 2", "Kriterium 3"]
    }
  }
]
```

Regeln:
- NUR Issues fuer Luecken die der Report TATSAECHLICH zeigt (keine Spekulation)
- Dedupliziere: wenn ein Issue schon existiert (Title Match), ueberspringe es
- Priority: CRITICAL wenn Attacker root-Level Zugriff bekommt, HIGH fuer alles andere
- Label "detection-gap" nur wenn Blue Team den Angriff NICHT erkannt hat
- Maximal 5 Issues pro Report (fokussiere auf die wichtigsten)
"""


def load_processed():
    """Load list of already-processed report files."""
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE) as f:
            return json.load(f)
    return []


def save_processed(processed):
    """Save list of processed reports."""
    with open(PROCESSED_FILE, "w") as f:
        json.dump(processed, f, indent=2)


def get_existing_issues():
    """Fetch all open issue titles from GitHub."""
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--repo", REPO, "--state", "open",
             "--json", "title", "--limit", "100"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            issues = json.loads(result.stdout)
            return {i["title"] for i in issues}
    except Exception:
        pass
    return set()


def analyze_report(report: dict, round_num: int, client) -> list[dict]:
    """Use LLM to analyze a report and generate issue proposals."""
    # Build concise report summary for LLM
    red_team = report.get("red_team", {})
    blue_team = report.get("blue_team", {})
    verdict = report.get("verdict", {})

    attacks = red_team.get("attacks", [])
    attack_summary = []
    for a in attacks:
        result = a.get("result", {})
        attack_summary.append({
            "tool": a.get("tool_name", ""),
            "category": a.get("category", ""),
            "success": a.get("success", False),
            "description": result.get("description", "")[:200] if isinstance(result, dict) else "",
        })

    report_text = json.dumps({
        "round": round_num,
        "red_team": {
            "attacks_executed": red_team.get("attacks_executed", 0),
            "categories": red_team.get("categories", []),
            "attacks": attack_summary,
        },
        "blue_team": {
            "finding_count": blue_team.get("finding_count", 0),
            "severity": blue_team.get("overall_severity", ""),
            "actions_taken": blue_team.get("actions_taken", 0),
            "report_excerpt": blue_team.get("report_text", "")[:2000],
        },
        "verdict": {
            "detection_rate": verdict.get("detection_rate", 0),
            "red_score": verdict.get("red_score", 0),
            "blue_score": verdict.get("blue_score", 0),
            "gaps": verdict.get("gaps", "[]"),
            "recommendations": verdict.get("recommendations", "{}"),
            "narrative": verdict.get("narrative", ""),
        },
    }, indent=2, ensure_ascii=False, default=str)

    response = client.chat.completions.create(
        model=get_model("issue_agent"),
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Analysiere diesen Report und erstelle Issues:\n\n{report_text}"},
        ],
    )

    content = response.choices[0].message.content or ""

    # Parse JSON from response
    json_start = content.find("[")
    json_end = content.rfind("]") + 1
    if json_start >= 0 and json_end > json_start:
        try:
            return json.loads(content[json_start:json_end])
        except json.JSONDecodeError:
            pass

    print(f"    [WARN] Could not parse LLM response as JSON")
    return []


def format_issue_body(body: dict) -> str:
    """Format issue body dict into markdown."""
    lines = []
    lines.append(f"## Quelle\n{body.get('source', 'Unknown')}\n")
    lines.append(f"## Problem\n{body.get('problem', '')}\n")

    if body.get("attack_pattern"):
        lines.append(f"## Angriffs-Pattern\n```bash\n{body['attack_pattern']}\n```\n")

    lines.append(f"## Kernel/OS-Loesung\n{body.get('kernel_solution', '')}\n")

    criteria = body.get("acceptance_criteria", [])
    if criteria:
        lines.append("## Akzeptanzkriterien")
        for c in criteria:
            lines.append(f"- [ ] {c}")
        lines.append("")

    lines.append(f"\n---\n*Auto-generated by Issue Agent from Red/Blue Exercise Report*")
    return "\n".join(lines)


def create_issue(issue: dict, dry_run: bool = False) -> str:
    """Create a GitHub issue. Returns issue URL or empty string."""
    title = issue.get("title", "Untitled")
    labels = issue.get("labels", [])
    body = format_issue_body(issue.get("body", {}))

    label_args = []
    for label in labels:
        label_args.extend(["--label", label])

    if dry_run:
        print(f"    [DRY-RUN] Would create: {title}")
        print(f"              Labels: {', '.join(labels)}")
        return "dry-run"

    try:
        cmd = ["gh", "issue", "create", "--repo", REPO, "--title", title, "--body", body] + label_args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            url = result.stdout.strip()
            print(f"    [CREATED] {title}")
            print(f"              {url}")
            return url
        else:
            print(f"    [ERROR] {result.stderr.strip()[:100]}")
            return ""
    except Exception as e:
        print(f"    [ERROR] {e}")
        return ""


def process_report(filepath: str, client, existing_titles: set, dry_run: bool = False) -> list[str]:
    """Process a single report file. Returns list of created issue URLs."""
    basename = os.path.basename(filepath)
    round_match = basename.replace("round_", "").replace(".json", "")

    print(f"\n  Processing {basename}...")

    with open(filepath, encoding="utf-8") as f:
        report = json.load(f)

    round_num = report.get("round", round_match)
    issues = analyze_report(report, round_num, client)

    if not issues:
        print(f"    No issues generated for {basename}")
        return []

    print(f"    LLM proposed {len(issues)} issues")

    created = []
    for issue in issues:
        title = issue.get("title", "")

        # Deduplicate against existing issues
        if any(title.lower() == existing.lower() for existing in existing_titles):
            print(f"    [SKIP] Already exists: {title}")
            continue

        url = create_issue(issue, dry_run=dry_run)
        if url:
            created.append(url)
            existing_titles.add(title)

    return created


def main():
    parser = argparse.ArgumentParser(description="Issue Agent — Reports to GitHub Issues")
    parser.add_argument("--report", type=str, help="Process specific report (e.g. round_01)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating issues")
    parser.add_argument("--force", action="store_true", help="Reprocess already-processed reports")
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  ISSUE AGENT — Report -> GitHub Issues")
    print(f"  Repo: {REPO}")
    print(f"  Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    client = get_client_sync("issue_agent")

    # Get existing issues for deduplication
    print("\n  Fetching existing issues...")
    existing_titles = get_existing_issues()
    print(f"  {len(existing_titles)} existing issues found")

    # Get already-processed reports
    processed = load_processed() if not args.force else []

    # Find reports to process
    if args.report:
        pattern = os.path.join(REPORT_DIR, f"{args.report}*.json")
        report_files = sorted(glob.glob(pattern))
    else:
        report_files = sorted(glob.glob(os.path.join(REPORT_DIR, "round_*.json")))

    # Filter already processed
    unprocessed = [f for f in report_files if os.path.basename(f) not in processed]

    if not unprocessed:
        print("\n  No unprocessed reports found.")
        if not args.force:
            print("  Use --force to reprocess all reports.")
        return

    print(f"\n  {len(unprocessed)} reports to process")

    # Process each report
    total_created = 0
    for filepath in unprocessed:
        urls = process_report(filepath, client, existing_titles, dry_run=args.dry_run)
        total_created += len(urls)

        if not args.dry_run:
            processed.append(os.path.basename(filepath))
            save_processed(processed)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  DONE: {total_created} issues created from {len(unprocessed)} reports")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
