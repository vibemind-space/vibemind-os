"""
VibeMind Issue Detector — MCP Server
=====================================
Self-healing loop with interactive user approval:

1. Scans security/system PoCs AND all 13 vibemind spaces
2. Findings land in pending state with unique IDs
3. User and Claude review findings together (interactive)
4. Approved findings → GitHub issues (with dedup)
5. Claude Code pulls issues and fixes them

Tools (Detection):
- scan_security        : Run all security PoCs
- scan_system_health   : Run all system PoCs
- scan_space           : Scan a specific vibemind space
- scan_all_spaces      : Scan all 13 vibemind spaces
- list_spaces          : List all available spaces

Tools (Pending Findings):
- list_pending_findings : Show all pending findings (filterable)
- approve_finding       : Push specific finding to GitHub
- reject_finding        : Discard pending finding with reason
- approve_all_in_space  : Batch approve all in a space
- clear_pending         : Clear all pending findings

Tools (GitHub):
- findings_to_issues    : Convert findings → issue drafts
- push_to_github        : Push drafts to GitHub (with dedup)
- full_scan_and_push    : End-to-end pipeline
- list_open_issues      : List detector-created open issues
- close_resolved_issue  : Mark as fixed

Tools (Notifications):
- notify_user           : Write to VibeMind inbox markdown file
- get_inbox             : Read pending notifications
"""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

BASE = Path(__file__).resolve().parent.parent  # vibemind-os/
SECURITY = BASE / "security"
SYSTEM = BASE / "system"
SPACES = BASE / "spaces"
STATE_FILE = Path(__file__).resolve().parent / "issue_state.json"
PENDING_FILE = Path(__file__).resolve().parent / "pending_findings.json"
INBOX_FILE = Path(__file__).resolve().parent / "vibemind_inbox.md"
WATCHER_STATE = Path(__file__).resolve().parent / "watcher_state.json"
TRIGGERED_EVENTS = Path(__file__).resolve().parent / "triggered_events.json"
WATCHER_CONFIG_FILE = Path(__file__).resolve().parent / "watcher_config.json"
EVENT_DROP_DIR = Path(__file__).resolve().parent / "event_drops"  # for OpenFang/external integration
DEFAULT_REPO = os.environ.get("ISSUE_DETECTOR_REPO", "")  # e.g. "Flissel/vibemind-os"
ISSUE_LABEL = "auto-detected"

# Known vibemind spaces (skip __pycache__, config, __init__)
SPACE_NAMES = [
    "autogen", "brain", "coding", "desktop", "flowzen",
    "ideas", "minibook", "mirofish", "n8n", "research",
    "rowboat", "schedule", "shuttles", "video",
]

mcp = FastMCP(
    "VibeMind Issue Detector",
    instructions=(
        "Self-healing loop: scans machine for issues using vibemind PoCs, "
        "pushes findings as GitHub issues so Claude Code can pull and fix them. "
        "Always run scans with dry_run=true first to preview before pushing."
    ),
)


# ============================================================
# State (dedup tracking)
# ============================================================

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"pushed_issues": {}}  # hash → {issue_number, created_at, title}


def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def _hash_finding(category: str, title: str) -> str:
    """Generate stable hash for dedup."""
    return hashlib.sha256(f"{category}:{title}".encode()).hexdigest()[:16]


# ============================================================
# Pending findings (interactive approval workflow)
# ============================================================

def _load_pending() -> dict:
    if PENDING_FILE.exists():
        try:
            return json.loads(PENDING_FILE.read_text())
        except Exception:
            pass
    return {"next_id": 1, "findings": {}}


def _save_pending(pending: dict):
    PENDING_FILE.write_text(json.dumps(pending, indent=2, default=str))


def _add_to_pending(findings: list) -> list:
    """Add findings to pending state, return assigned IDs."""
    pending = _load_pending()
    ids = []
    for f in findings:
        fid = f"P{pending['next_id']:04d}"
        pending["next_id"] += 1
        f_copy = dict(f)
        f_copy["id"] = fid
        f_copy["pending_since"] = datetime.now(timezone.utc).isoformat()
        f_copy["status"] = "pending"
        pending["findings"][fid] = f_copy
        ids.append(fid)
    _save_pending(pending)
    return ids


# ============================================================
# Space detection (generic + space-specific checks)
# ============================================================

def _check_space_python_files(space_dir: Path) -> list:
    """Check Python files for syntax errors and missing imports."""
    findings = []
    if not space_dir.exists():
        return findings

    py_files = list(space_dir.rglob("*.py"))
    for pyf in py_files:
        if "__pycache__" in str(pyf):
            continue
        try:
            content = pyf.read_text(encoding="utf-8", errors="replace")
            compile(content, str(pyf), "exec")
        except SyntaxError as e:
            findings.append({
                "title": f"Syntax error in {pyf.relative_to(BASE)}: line {e.lineno}",
                "details": f"```\n{e.msg}\n```\nFile: `{pyf.relative_to(BASE)}`\nLine: {e.lineno}",
                "severity": "HIGH",
                "source": f"space:{space_dir.name}",
                "category": "space",
                "file": str(pyf.relative_to(BASE)),
            })
        except Exception:
            pass
    return findings


def _check_space_todos(space_dir: Path) -> list:
    """Check for FIXME/BROKEN/XXX markers."""
    findings = []
    if not space_dir.exists():
        return findings

    markers = ["FIXME", "BROKEN", "XXX", "HACK"]
    for pyf in space_dir.rglob("*.py"):
        if "__pycache__" in str(pyf):
            continue
        try:
            content = pyf.read_text(encoding="utf-8", errors="replace")
            for ln, line in enumerate(content.splitlines(), 1):
                for marker in markers:
                    if marker in line and not line.strip().startswith("#" + marker):
                        rel = pyf.relative_to(BASE)
                        findings.append({
                            "title": f"{marker} marker in {rel}:{ln}",
                            "details": f"File: `{rel}`\nLine {ln}: `{line.strip()[:200]}`",
                            "severity": "LOW" if marker in ("XXX", "HACK") else "MEDIUM",
                            "source": f"space:{space_dir.name}",
                            "category": "space",
                            "file": str(rel),
                        })
                        break
        except Exception:
            pass
    return findings[:10]  # cap to avoid spam


def _check_space_readme(space_dir: Path) -> list:
    """Check if space has a README."""
    findings = []
    if not space_dir.exists():
        return findings

    has_readme = any((space_dir / name).exists()
                     for name in ["README.md", "README.rst", "README.txt", "readme.md"])
    if not has_readme:
        findings.append({
            "title": f"Space '{space_dir.name}' missing README.md",
            "details": f"Space directory `spaces/{space_dir.name}/` has no README. "
                       "Add documentation describing its purpose, agents, and usage.",
            "severity": "LOW",
            "source": f"space:{space_dir.name}",
            "category": "space",
        })
    return findings


def _check_space_size(space_dir: Path) -> list:
    """Flag suspiciously empty or huge spaces."""
    findings = []
    if not space_dir.exists():
        return findings

    py_files = [f for f in space_dir.rglob("*.py") if "__pycache__" not in str(f)]
    if len(py_files) == 0:
        findings.append({
            "title": f"Space '{space_dir.name}' has no Python files",
            "details": f"Space `spaces/{space_dir.name}/` contains no .py files. "
                       "Either add implementation or consider removing.",
            "severity": "MEDIUM",
            "source": f"space:{space_dir.name}",
            "category": "space",
        })
    return findings


def _scan_one_space(space_name: str) -> list:
    """Run all checks for a single space."""
    space_dir = SPACES / space_name
    findings = []
    findings.extend(_check_space_python_files(space_dir))
    findings.extend(_check_space_readme(space_dir))
    findings.extend(_check_space_size(space_dir))
    findings.extend(_check_space_todos(space_dir))
    return findings


# ============================================================
# Subprocess wrappers for PoCs
# ============================================================

def _run_python_in(cwd: Path, script: str, args: list = None, timeout: int = 60) -> dict:
    """Run a Python script in a specific directory and return parsed output."""
    args = args or []
    try:
        result = subprocess.run(
            [sys.executable, script, *args],
            cwd=str(cwd),
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "timeout_secs": timeout}
    except Exception as e:
        return {"error": str(e)}


def _run_inline(cwd: Path, code: str, timeout: int = 60) -> dict:
    """Run inline Python code in a directory's context. Returns last expression as JSON."""
    wrapper = f"""
import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
try:
{chr(10).join('    ' + line for line in code.strip().splitlines())}
except Exception as e:
    import traceback
    print(json.dumps({{"error": str(e), "traceback": traceback.format_exc()}}))
"""
    script_path = cwd / "_inline_runner.py"
    script_path.write_text(wrapper)
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(cwd),
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        try:
            return json.loads(result.stdout.strip().split("\n")[-1])
        except Exception:
            return {"error": "non-json output", "stdout": result.stdout[:500],
                    "stderr": result.stderr[:500]}
    finally:
        if script_path.exists():
            script_path.unlink()


# ============================================================
# Tools
# ============================================================

@mcp.tool()
def scan_security() -> dict:
    """
    Run security PoCs and aggregate findings.
    Tools used: vuln_scanner, os_shield (baseline), forensics (USB)
    """
    findings = []

    # 1. Vulnerability scanner: count installed software
    vuln = _run_inline(SECURITY / "poc_vuln_scanner", """
from main import inventory_installed_software
software = asyncio.run(inventory_installed_software())
print(json.dumps({"installed_software_count": len(software)}))
""", timeout=60)
    if vuln.get("installed_software_count", 0) > 300:
        findings.append({
            "category": "security",
            "severity": "INFO",
            "title": f"Large software inventory detected: {vuln['installed_software_count']} packages",
            "details": "High number of installed packages increases attack surface. Consider pruning unused software.",
            "source": "poc_vuln_scanner",
        })

    # 2. OS Shield baseline: capture process/network state
    shield = _run_inline(SECURITY / "poc_os_shield", """
from baselines import capture_baseline
import sys
old = sys.stdout
sys.stdout = sys.stderr
bl = asyncio.run(capture_baseline())
sys.stdout = old
print(json.dumps({k: (len(v) if isinstance(v, (list,dict)) else v) for k,v in bl.items()}))
""", timeout=60)
    if isinstance(shield, dict) and shield.get("autorun_entries", 0) > 30:
        findings.append({
            "category": "security",
            "severity": "MEDIUM",
            "title": f"High autorun entries: {shield['autorun_entries']} programs auto-start",
            "details": "Many programs configured to auto-start. Review for unnecessary or suspicious entries.",
            "source": "poc_os_shield",
        })

    # 3. Forensics: USB history
    usb = _run_inline(SECURITY / "poc_forensics", """
from main import parse_usb_history
devices = asyncio.run(parse_usb_history())
print(json.dumps({"usb_devices": len(devices)}))
""", timeout=30)
    if isinstance(usb, dict) and usb.get("usb_devices", 0) > 50:
        findings.append({
            "category": "security",
            "severity": "LOW",
            "title": f"Many USB devices in history: {usb['usb_devices']}",
            "details": "Large USB device history. Audit for unauthorized devices.",
            "source": "poc_forensics",
        })

    # 4. Botnet local check
    botnet = _run_inline(SECURITY / "poc_botnet_detector", """
from detector import BotnetDetector
import sys
old = sys.stdout
sys.stdout = sys.stderr
bd = BotnetDetector()
result = asyncio.run(bd.check_local())
sys.stdout = old
print(json.dumps({"zombie_score": result.get("zombie_score", 0), "issues": len(result.get("issues", []))}, default=str))
""", timeout=60)
    if isinstance(botnet, dict) and botnet.get("zombie_score", 0) > 30:
        findings.append({
            "category": "security",
            "severity": "HIGH" if botnet["zombie_score"] > 60 else "MEDIUM",
            "title": f"Botnet/zombie indicators detected (score: {botnet['zombie_score']})",
            "details": f"Local machine shows {botnet.get('issues', 0)} suspicious indicators.",
            "source": "poc_botnet_detector",
        })

    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "findings_count": len(findings),
        "findings": findings,
    }


@mcp.tool()
def scan_system_health() -> dict:
    """
    Run system PoCs and aggregate health findings.
    Tools used: poc_update_manager, poc_scheduled_tasks, poc_registry
    """
    findings = []

    # Check Windows updates pending
    r = subprocess.run(
        ["powershell", "-Command",
         "Get-WUList 2>$null | Measure-Object | Select-Object -ExpandProperty Count"],
        capture_output=True, text=True, timeout=30
    )
    if r.returncode == 0 and r.stdout.strip().isdigit():
        pending = int(r.stdout.strip())
        if pending > 0:
            findings.append({
                "category": "system",
                "severity": "MEDIUM" if pending > 5 else "LOW",
                "title": f"{pending} Windows updates pending",
                "details": "System has pending Windows updates. Install for security patches.",
                "source": "poc_update_manager",
            })

    # Check disk space
    r = subprocess.run(
        ["powershell", "-Command",
         "Get-PSDrive C | Select-Object @{n='UsedGB';e={[math]::Round($_.Used/1GB,2)}}, @{n='FreeGB';e={[math]::Round($_.Free/1GB,2)}} | ConvertTo-Json"],
        capture_output=True, text=True, timeout=10
    )
    if r.returncode == 0 and r.stdout.strip():
        try:
            disk = json.loads(r.stdout)
            free_gb = disk.get("FreeGB", 0)
            if free_gb < 10:
                findings.append({
                    "category": "system",
                    "severity": "HIGH" if free_gb < 5 else "MEDIUM",
                    "title": f"Low disk space on C:: {free_gb} GB free",
                    "details": "System drive running low. Clean up to prevent failures.",
                    "source": "system_check",
                })
        except json.JSONDecodeError:
            pass

    # Process count
    r = subprocess.run(
        ["powershell", "-Command", "(Get-Process).Count"],
        capture_output=True, text=True, timeout=10
    )
    if r.returncode == 0 and r.stdout.strip().isdigit():
        proc_count = int(r.stdout.strip())
        if proc_count > 500:
            findings.append({
                "category": "system",
                "severity": "INFO",
                "title": f"High process count: {proc_count}",
                "details": "Many processes running. Review for unnecessary background services.",
                "source": "poc_process_manager",
            })

    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "findings_count": len(findings),
        "findings": findings,
    }


@mcp.tool()
def findings_to_issues(findings: list) -> dict:
    """
    Convert raw findings into structured GitHub issue drafts.
    Each draft has: title, body (markdown), labels.
    """
    drafts = []
    for f in findings:
        severity = f.get("severity", "INFO")
        title = f"[{severity}] {f.get('title', 'Unknown finding')}"
        body = f"""## Finding

**Category:** {f.get('category', 'unknown')}
**Severity:** {severity}
**Source:** {f.get('source', 'unknown')}
**Detected:** {datetime.now(timezone.utc).isoformat()}

## Details

{f.get('details', 'No details provided')}

## Suggested Fix

_To be analyzed by Claude Code or assigned engineer._

---
*Auto-detected by vibemind-issue-detector. Hash: `{_hash_finding(f.get('category', ''), f.get('title', ''))}`*
"""
        labels = [ISSUE_LABEL, f.get("category", "unknown"), severity.lower()]
        drafts.append({
            "title": title,
            "body": body,
            "labels": labels,
            "hash": _hash_finding(f.get("category", ""), f.get("title", "")),
        })
    return {"drafts_count": len(drafts), "drafts": drafts}


@mcp.tool()
def push_to_github(drafts: list, repo: str = "", dry_run: bool = True) -> dict:
    """
    Push issue drafts to GitHub via `gh issue create`.
    Uses hash-based dedup: skips drafts already pushed.
    Set dry_run=false to actually create issues.
    """
    target_repo = repo or DEFAULT_REPO
    if not target_repo and not dry_run:
        return {"error": "No repo specified. Set ISSUE_DETECTOR_REPO env or pass repo argument."}

    state = _load_state()
    pushed = state.get("pushed_issues", {})

    results = {"created": [], "skipped_dedup": [], "errors": [], "dry_run": dry_run}

    for draft in drafts:
        h = draft.get("hash", "")
        if h in pushed:
            existing = pushed[h]
            # Check if still open
            if existing.get("status") == "open":
                results["skipped_dedup"].append({
                    "hash": h,
                    "title": draft["title"],
                    "existing_issue": existing.get("issue_number"),
                })
                continue

        if dry_run:
            results["created"].append({
                "title": draft["title"],
                "labels": draft.get("labels", []),
                "would_create": True,
            })
            continue

        # Real push via gh
        try:
            cmd = ["gh", "issue", "create", "-R", target_repo,
                   "--title", draft["title"],
                   "--body", draft["body"]]
            for label in draft.get("labels", []):
                cmd.extend(["--label", label])

            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                               encoding="utf-8", errors="replace")
            if r.returncode == 0:
                # Output is the issue URL: https://github.com/owner/repo/issues/123
                url = r.stdout.strip()
                issue_num = url.rsplit("/", 1)[-1] if "/" in url else "?"
                pushed[h] = {
                    "issue_number": issue_num,
                    "url": url,
                    "title": draft["title"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "status": "open",
                }
                results["created"].append({
                    "title": draft["title"],
                    "issue_number": issue_num,
                    "url": url,
                })
            else:
                results["errors"].append({
                    "title": draft["title"],
                    "error": r.stderr.strip()[:300],
                })
        except Exception as e:
            results["errors"].append({"title": draft["title"], "error": str(e)})

    if not dry_run:
        state["pushed_issues"] = pushed
        _save_state(state)

    results["total_drafts"] = len(drafts)
    return results


@mcp.tool()
def full_scan_and_push(repo: str = "", dry_run: bool = True,
                       include_system: bool = True) -> dict:
    """
    End-to-end pipeline: scan → drafts → push.
    Default dry_run=true so you can review before actually creating issues.
    """
    pipeline = {"steps": []}

    # Step 1: scan security
    sec = scan_security()
    pipeline["steps"].append({"step": "scan_security", "findings": sec["findings_count"]})
    all_findings = list(sec.get("findings", []))

    # Step 2: scan system (optional)
    if include_system:
        sys_scan = scan_system_health()
        pipeline["steps"].append({"step": "scan_system_health", "findings": sys_scan["findings_count"]})
        all_findings.extend(sys_scan.get("findings", []))

    # Step 3: convert to drafts
    drafts_result = findings_to_issues(all_findings)
    pipeline["steps"].append({"step": "findings_to_issues", "drafts": drafts_result["drafts_count"]})

    # Step 4: push to GitHub
    push_result = push_to_github(drafts_result["drafts"], repo=repo, dry_run=dry_run)
    pipeline["steps"].append({"step": "push_to_github",
                              "created": len(push_result.get("created", [])),
                              "skipped": len(push_result.get("skipped_dedup", [])),
                              "errors": len(push_result.get("errors", []))})

    pipeline["push_result"] = push_result
    pipeline["all_findings"] = all_findings
    return pipeline


@mcp.tool()
def list_open_issues() -> dict:
    """List issues created by this detector that are still open."""
    state = _load_state()
    pushed = state.get("pushed_issues", {})
    open_issues = [v for v in pushed.values() if v.get("status") == "open"]
    return {
        "open_count": len(open_issues),
        "issues": open_issues,
    }


@mcp.tool()
def close_resolved_issue(issue_hash: str) -> dict:
    """Mark a previously-pushed issue as resolved in local state (for dedup tracking)."""
    state = _load_state()
    pushed = state.get("pushed_issues", {})
    if issue_hash in pushed:
        pushed[issue_hash]["status"] = "closed"
        pushed[issue_hash]["closed_at"] = datetime.now(timezone.utc).isoformat()
        state["pushed_issues"] = pushed
        _save_state(state)
        return {"closed": issue_hash, "issue": pushed[issue_hash]}
    return {"error": f"Hash not found: {issue_hash}"}


# ============================================================
# Space Detection Tools
# ============================================================

@mcp.tool()
def list_spaces() -> dict:
    """List all available vibemind spaces."""
    available = []
    for name in SPACE_NAMES:
        d = SPACES / name
        if d.exists():
            py_count = len([f for f in d.rglob("*.py") if "__pycache__" not in str(f)])
            available.append({
                "name": name,
                "path": str(d.relative_to(BASE)),
                "python_files": py_count,
            })
    return {"spaces_count": len(available), "spaces": available}


@mcp.tool()
def scan_space(space_name: str, add_to_pending: bool = True) -> dict:
    """
    Scan a single vibemind space for issues.
    Checks: syntax errors, missing README, empty space, FIXME/BROKEN markers.

    If add_to_pending=true, findings are queued for user review (not auto-pushed).
    """
    if space_name not in SPACE_NAMES:
        return {"error": f"Unknown space: {space_name}", "available": SPACE_NAMES}

    findings = _scan_one_space(space_name)
    result = {
        "space": space_name,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "findings_count": len(findings),
        "findings": findings,
    }

    if add_to_pending and findings:
        ids = _add_to_pending(findings)
        result["pending_ids"] = ids
        notify_user(f"🔍 Found {len(findings)} issue(s) in space `{space_name}`. "
                    f"IDs: {', '.join(ids[:5])}{'...' if len(ids) > 5 else ''}. "
                    f"Use list_pending_findings to review.")

    return result


@mcp.tool()
def scan_all_spaces(add_to_pending: bool = True) -> dict:
    """
    Scan all 13 vibemind spaces for issues.
    Aggregates findings per space, optionally queues for user review.
    """
    summary = {"scanned_at": datetime.now(timezone.utc).isoformat(),
               "per_space": {}, "total_findings": 0}
    all_findings = []

    for name in SPACE_NAMES:
        if not (SPACES / name).exists():
            continue
        findings = _scan_one_space(name)
        summary["per_space"][name] = len(findings)
        summary["total_findings"] += len(findings)
        all_findings.extend(findings)

    if add_to_pending and all_findings:
        ids = _add_to_pending(all_findings)
        summary["pending_ids_count"] = len(ids)
        notify_user(f"🔍 Full scan complete: {len(all_findings)} findings across "
                    f"{len([s for s, c in summary['per_space'].items() if c > 0])} spaces. "
                    f"Use list_pending_findings to review.")

    summary["findings"] = all_findings
    return summary


# ============================================================
# Pending Findings — Interactive Approval Workflow
# ============================================================

@mcp.tool()
def list_pending_findings(filter_space: str = "", filter_severity: str = "") -> dict:
    """
    List all pending findings awaiting user decision.
    Filter by space ('coding', 'brain', etc.) or severity ('CRITICAL', 'HIGH', etc.).
    """
    pending = _load_pending()
    findings = list(pending.get("findings", {}).values())

    if filter_space:
        findings = [f for f in findings
                    if f.get("source", "").endswith(filter_space)
                    or f.get("category") == filter_space]
    if filter_severity:
        findings = [f for f in findings if f.get("severity", "") == filter_severity.upper()]

    findings = [f for f in findings if f.get("status") == "pending"]

    # Group by source
    by_source = {}
    for f in findings:
        src = f.get("source", "unknown")
        by_source.setdefault(src, []).append({
            "id": f.get("id"),
            "severity": f.get("severity"),
            "title": f.get("title"),
        })

    return {
        "total_pending": len(findings),
        "by_source": by_source,
        "all_findings": findings,
    }


@mcp.tool()
def approve_finding(finding_id: str, repo: str = "", edit_title: str = "",
                    edit_body: str = "") -> dict:
    """
    Approve a pending finding and push it to GitHub as an issue.
    Optionally edit the title/body before pushing.
    """
    pending = _load_pending()
    f = pending.get("findings", {}).get(finding_id)
    if not f:
        return {"error": f"Finding not found: {finding_id}"}
    if f.get("status") != "pending":
        return {"error": f"Finding {finding_id} is not pending (status: {f.get('status')})"}

    # Apply edits
    if edit_title:
        f["title"] = edit_title
    if edit_body:
        f["details"] = edit_body

    # Convert to draft + push
    drafts = findings_to_issues([f])["drafts"]
    push_result = push_to_github(drafts, repo=repo, dry_run=False)

    if push_result.get("created"):
        f["status"] = "approved"
        f["approved_at"] = datetime.now(timezone.utc).isoformat()
        f["github_issue"] = push_result["created"][0]
        pending["findings"][finding_id] = f
        _save_pending(pending)
        return {"approved": finding_id, "issue": push_result["created"][0]}
    else:
        return {"error": "Push failed", "push_result": push_result}


@mcp.tool()
def reject_finding(finding_id: str, reason: str = "") -> dict:
    """Reject a pending finding (no GitHub issue created)."""
    pending = _load_pending()
    f = pending.get("findings", {}).get(finding_id)
    if not f:
        return {"error": f"Finding not found: {finding_id}"}

    f["status"] = "rejected"
    f["rejected_at"] = datetime.now(timezone.utc).isoformat()
    f["rejection_reason"] = reason
    pending["findings"][finding_id] = f
    _save_pending(pending)
    return {"rejected": finding_id, "reason": reason}


@mcp.tool()
def approve_all_in_space(space_name: str, repo: str = "") -> dict:
    """Batch-approve all pending findings for a specific space."""
    pending = _load_pending()
    matching = [f for f in pending.get("findings", {}).values()
                if f.get("status") == "pending"
                and f.get("source", "").endswith(space_name)]
    results = {"approved": [], "errors": []}
    for f in matching:
        r = approve_finding(f["id"], repo=repo)
        if "error" in r:
            results["errors"].append({"id": f["id"], "error": r["error"]})
        else:
            results["approved"].append(r.get("issue"))
    return results


@mcp.tool()
def clear_pending(only_status: str = "rejected") -> dict:
    """
    Clear pending findings by status.
    only_status='rejected' (default), 'approved', or 'all'.
    """
    pending = _load_pending()
    findings = pending.get("findings", {})
    before = len(findings)

    if only_status == "all":
        pending["findings"] = {}
    else:
        pending["findings"] = {k: v for k, v in findings.items()
                               if v.get("status") != only_status}

    _save_pending(pending)
    return {"cleared": before - len(pending["findings"]), "remaining": len(pending["findings"])}


# ============================================================
# Event Watcher — triggered detection on failures/anomalies
# ============================================================

# Global state for the watcher daemon thread
_watcher_thread: threading.Thread = None
_watcher_stop = threading.Event()
_watcher_lock = threading.Lock()
_watcher_config = {
    "enabled_sources": [],     # ['windows_eventlog', 'process_crashes', 'log_files']
    "watched_processes": [],   # process names to watch
    "watched_log_files": [],   # absolute paths to log files
    "log_error_patterns": ["ERROR", "FATAL", "CRITICAL", "Traceback", "panic", "Exception"],
    "poll_interval_secs": 10,
    "min_event_severity": 2,   # Windows: 1=Critical, 2=Error, 3=Warning
}


def _load_triggered() -> dict:
    if TRIGGERED_EVENTS.exists():
        try:
            return json.loads(TRIGGERED_EVENTS.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"next_id": 1, "events": []}


def _save_triggered(data: dict):
    TRIGGERED_EVENTS.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _record_event(source: str, event_type: str, details: dict, auto_react: bool = True) -> str:
    """Record a triggered event and optionally auto-react with detection."""
    data = _load_triggered()
    eid = f"E{data['next_id']:04d}"
    data["next_id"] += 1
    event = {
        "id": eid,
        "source": source,
        "event_type": event_type,
        "details": details,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "processed": False,
        "reaction": None,
    }
    data["events"].append(event)

    # Cap to last 200 events
    if len(data["events"]) > 200:
        data["events"] = data["events"][-200:]

    _save_triggered(data)

    if auto_react:
        _react_to_event(event)

    return eid


def _react_to_event(event: dict):
    """
    React to an event — MUST be fast and non-blocking.

    Strategy: record the event itself as a single pending finding with
    full details. The user can then decide whether to trigger a deep scan
    via the deep_scan_for_event() tool. This keeps the watcher thread
    responsive and preserves the "discuss with user" philosophy.
    """
    source = event.get("source", "")
    severity_map = {
        "windows_eventlog": "HIGH",
        "process_crashes": "CRITICAL",
        "log_files": "MEDIUM",
        "openfang": "HIGH",
        "electron": "HIGH",
        "file_drop": "MEDIUM",
    }
    # Auto-issue: these event types skip pending and go straight to GitHub
    AUTO_ISSUE_TYPES = {
        "python_backend_crashed", "log_critical", "log_fatal",
        "log_traceback", "process_crashed", "rust_panic",
    }

    try:
        details = event.get("details", {})
        event_type = event.get("event_type", "unknown")

        # Build a rich but fast finding — no subprocess calls
        title_suffix = ""
        if source == "openfang":
            agent = details.get("agent", "")
            if agent:
                title_suffix = f" ({agent})"
        elif source == "windows_eventlog":
            provider = details.get("ProviderName", "")
            if provider:
                title_suffix = f" [{provider}]"
        elif source == "process_crashes":
            proc = details.get("crashed_process", "")
            if proc:
                title_suffix = f" ({proc})"
        elif source == "electron":
            log_file = details.get("file", "")
            msg = details.get("message", "")[:60]
            if log_file:
                title_suffix = f" [{Path(log_file).name}]"
            elif msg:
                title_suffix = f": {msg}"

        finding = {
            "title": f"[{source}] {event_type}{title_suffix}",
            "details": (
                f"**Source:** {source}\n"
                f"**Event ID:** {event['id']}\n"
                f"**Triggered at:** {event.get('triggered_at', '')}\n\n"
                f"## Details\n\n"
                f"```json\n{json.dumps(details, indent=2, default=str)[:2000]}\n```\n\n"
                f"## Next steps\n\n"
                f"To run a deeper scan for this event, use:\n"
                f"`deep_scan_for_event('{event['id']}')`"
            ),
            "severity": severity_map.get(source, "MEDIUM"),
            "source": f"event:{source}",
            "category": "triggered",
            "event_id": event["id"],
        }

        # Decide: auto-issue (clear errors) vs pending (ambiguous)
        auto_issue = (
            event_type in AUTO_ISSUE_TYPES
            or finding["severity"] == "CRITICAL"
            or any(p in event_type.lower() for p in ["crash", "panic", "fatal"])
        )

        if auto_issue and DEFAULT_REPO:
            # Auto-push to GitHub — clear error, no need to ask
            drafts = findings_to_issues([finding])["drafts"]
            push_result = push_to_github(drafts, repo=DEFAULT_REPO, dry_run=False)
            created = push_result.get("created", [])

            event["reaction"] = {
                "auto_issued": True,
                "github_issues": created,
                "deep_scan_available": True,
            }
            event["processed"] = True

            issue_url = created[0].get("url", "?") if created else "failed"
            notify_user(
                f"🚨 AUTO-ISSUE: {event_type}{title_suffix}\n"
                f"GitHub: {issue_url}\n"
                f"Deep scan: deep_scan_for_event('{event['id']}')",
                level="ALERT",
            )
        else:
            # Pending for review — ambiguous or no repo configured
            ids = _add_to_pending([finding])
            event["reaction"] = {
                "findings_count": 1,
                "pending_ids": ids,
                "deep_scan_available": True,
                "auto_issued": False,
            }
            event["processed"] = True

            notify_user(
                f"⚡ {source} event: {event_type}{title_suffix}. "
                f"Pending ID: {ids[0]}. "
                f"deep_scan_for_event('{event['id']}') for more context.",
                level="ALERT",
            )

    except Exception as e:
        event["reaction"] = {"error": str(e)}
        event["processed"] = True  # Mark as processed even on error to prevent retry loops

    # Update event in state
    try:
        data = _load_triggered()
        for i, e in enumerate(data["events"]):
            if e["id"] == event["id"]:
                data["events"][i] = event
                break
        _save_triggered(data)
    except Exception:
        pass  # best-effort persistence


def _watch_windows_eventlog():
    """Poll Windows Event Log for new errors. Returns list of new events."""
    try:
        # Get last seen record number
        wstate = _load_watcher_state()
        last_record = wstate.get("eventlog_last_record", 0)

        # Use PowerShell to get recent error events
        cmd = (
            "Get-WinEvent -FilterHashtable @{LogName='Application','System';Level=1,2} "
            "-MaxEvents 20 -ErrorAction SilentlyContinue | "
            "Select-Object RecordId,TimeCreated,LevelDisplayName,LogName,ProviderName,Message | "
            "ConvertTo-Json -Compress"
        )
        r = subprocess.run(["powershell", "-Command", cmd],
                           capture_output=True, text=True, timeout=20,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0 or not r.stdout.strip():
            return []

        events = json.loads(r.stdout)
        if isinstance(events, dict):
            events = [events]

        new_events = []
        max_record = last_record
        for ev in events:
            rid = ev.get("RecordId", 0)
            if rid > last_record:
                new_events.append(ev)
                max_record = max(max_record, rid)

        # Update state
        if max_record > last_record:
            wstate["eventlog_last_record"] = max_record
            _save_watcher_state(wstate)

        return new_events
    except Exception as e:
        return [{"watcher_error": str(e)}]


def _watch_process_crashes():
    """Detect process crashes by tracking watched process names."""
    try:
        import psutil
        wstate = _load_watcher_state()
        seen = set(wstate.get("seen_processes", []))
        currently_running = set()

        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = proc.info.get("name", "")
                if name and any(wp.lower() in name.lower()
                                for wp in _watcher_config["watched_processes"]):
                    currently_running.add(name)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Detect crashes: was running, no longer running
        crashed = seen - currently_running
        wstate["seen_processes"] = list(currently_running)
        _save_watcher_state(wstate)

        return [{"crashed_process": name} for name in crashed]
    except Exception as e:
        return [{"watcher_error": str(e)}]


def _watch_electron():
    """
    Monitor the VibeMind Electron app via CDP (Chrome DevTools Protocol) on port 9223.
    Captures: console.error, uncaught exceptions, renderer crashes, Python backend crashes.
    Also tails Python backend logs for Tracebacks.

    Non-blocking: uses short HTTP timeouts and returns immediately if Electron is offline.
    """
    new_events = []
    cdp_port = _watcher_config.get("electron_cdp_port", 9223)

    electron_running = False
    targets = []

    # --- 1. Check if Electron is running (via CDP /json endpoint) ---
    try:
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{cdp_port}/json",
                                     method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            targets = json.loads(resp.read().decode())
        electron_running = True
    except Exception:
        # Electron not running or CDP not reachable
        # Still continue with log monitoring — logs persist after crashes
        pass

    # --- 2. Check Python backend process is alive (only if Electron was seen before) ---
    if electron_running:
        try:
            import psutil
            python_backends = []
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    cmdline = " ".join(proc.info.get("cmdline", []) or [])
                    if "electron_backend" in cmdline or "vibemind" in cmdline.lower():
                        python_backends.append({
                            "pid": proc.info["pid"],
                            "name": proc.info["name"],
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            wstate = _load_watcher_state()
            prev_backends = set(tuple(sorted(p.items())) for p in wstate.get("electron_python_backends", []))
            curr_backends = set(tuple(sorted(p.items())) for p in python_backends)

            if prev_backends and not curr_backends:
                new_events.append({
                    "source": "electron",
                    "event_type": "python_backend_crashed",
                    "details": {
                        "message": "VibeMind Python backend process is no longer running",
                        "previous_pids": [dict(p) for p in prev_backends],
                    },
                })

            wstate["electron_python_backends"] = python_backends
            _save_watcher_state(wstate)
        except Exception:
            pass

    # --- 3. Tail ALL relevant log sources for errors ---
    # Cast a wide net: logs can be incomplete, different components
    # write to different places. Check everything.
    log_dirs = [
        BASE / "voice" / "python" / "logs",
        BASE / "voice" / "python" / "logs" / "agents",
        BASE / "voice" / "python" / "logs" / "intents",
        BASE / "voice" / "python" / "logs" / "tools",
        BASE / "voice" / "python" / "logs" / "reasoning",
        BASE / "voice" / "python" / "logs" / "spaces",
        BASE.parent / "Automation_ui" / "logs",
    ]
    error_patterns = [
        # Hard errors — will auto-create GitHub issue
        "CRITICAL", "FATAL", "Traceback",
        # Regular errors
        "ERROR",
        # Timeouts / unresponsive — user expected something but nothing came
        "timed out", "timeout", "TimeoutError",
        "unresponsive", "no response", "not responding",
        # Connection failures
        "Connection refused", "ConnectionResetError", "ECONNREFUSED",
        # Panics (Rust/Node)
        "panic", "PANIC",
        # Uncaught
        "Uncaught", "UnhandledPromiseRejection",
    ]
    wstate = _load_watcher_state()
    electron_log_positions = wstate.get("electron_log_positions", {})

    for log_dir in log_dirs:
        if not log_dir.exists():
            continue
        for log_file in log_dir.glob("*.log"):
            fpath = str(log_file)
            try:
                size = log_file.stat().st_size
                last_pos = electron_log_positions.get(fpath, 0)
                if size < last_pos:
                    last_pos = 0  # File rotated
                if size <= last_pos:
                    continue

                with open(log_file, encoding="utf-8", errors="replace") as f:
                    f.seek(last_pos)
                    new_content = f.read(50000)  # Cap at 50KB per poll
                    electron_log_positions[fpath] = f.tell()

                # Collect error lines with context
                lines = new_content.splitlines()
                for i, line in enumerate(lines):
                    for pat in error_patterns:
                        if pat in line:
                            # Grab surrounding context (2 before, 8 after for tracebacks)
                            context_start = max(0, i - 2)
                            context_end = min(len(lines), i + 8)
                            context = "\n".join(lines[context_start:context_end])

                            # Classify severity → determines auto-issue or pending
                            if pat in ("CRITICAL", "FATAL", "Traceback", "panic", "PANIC"):
                                event_type = f"log_{pat.lower()}"
                            elif pat in ("timed out", "timeout", "TimeoutError",
                                         "unresponsive", "no response", "not responding"):
                                event_type = "log_timeout"
                            elif pat in ("Connection refused", "ConnectionResetError", "ECONNREFUSED"):
                                event_type = "log_connection_failed"
                            elif pat in ("Uncaught", "UnhandledPromiseRejection"):
                                event_type = "log_uncaught"
                            else:
                                event_type = "log_error"

                            # Determine relative path (some logs are outside BASE)
                            try:
                                rel_path = str(log_file.relative_to(BASE))
                            except ValueError:
                                try:
                                    rel_path = str(log_file.relative_to(BASE.parent))
                                except ValueError:
                                    rel_path = str(log_file)

                            new_events.append({
                                "source": "electron",
                                "event_type": event_type,
                                "details": {
                                    "file": rel_path,
                                    "line_number": i + 1,
                                    "pattern": pat,
                                    "message": line.strip()[:500],
                                    "context": context[:2000],
                                },
                            })
                            break  # One event per error line
            except Exception:
                pass

    wstate["electron_log_positions"] = electron_log_positions
    _save_watcher_state(wstate)

    # --- 4. Check Electron renderer errors via CDP ---
    # Use Runtime.evaluate to read a shared error buffer from the renderer.
    # Inject a small collector on first run, then read it on subsequent polls.
    if electron_running and targets:
        try:
            page_targets = [t for t in targets if t.get("type") == "page"]
            if page_targets:
                ws_url = page_targets[0].get("webSocketDebuggerUrl", "")
                target_id = page_targets[0].get("id", "")

                # Use CDP HTTP endpoint to evaluate JS in the renderer
                # This catches console.error that never made it to a log file
                eval_js = (
                    "(function() {"
                    "  if (!window.__issueDetectorErrors) {"
                    "    window.__issueDetectorErrors = [];"
                    "    const origError = console.error;"
                    "    console.error = function(...args) {"
                    "      window.__issueDetectorErrors.push({"
                    "        ts: new Date().toISOString(),"
                    "        msg: args.map(a => String(a)).join(' ').slice(0, 500)"
                    "      });"
                    "      if (window.__issueDetectorErrors.length > 50)"
                    "        window.__issueDetectorErrors = window.__issueDetectorErrors.slice(-50);"
                    "      origError.apply(console, args);"
                    "    };"
                    "  }"
                    "  const errors = window.__issueDetectorErrors.splice(0);"
                    "  return JSON.stringify(errors);"
                    "})()"
                )

                import urllib.request
                payload = json.dumps({
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {"expression": eval_js, "returnByValue": True}
                }).encode()
                # Use CDP HTTP debug endpoint
                req = urllib.request.Request(
                    f"http://127.0.0.1:{cdp_port}/json/version",
                    method="GET")
                # Actually we need WebSocket for Runtime.evaluate — skip direct eval
                # Instead: check /json for crashed renderer targets
                crashed_targets = [t for t in targets if t.get("type") == "page"
                                   and ("crashed" in t.get("title", "").lower()
                                        or "error" in t.get("title", "").lower())]
                for ct in crashed_targets:
                    new_events.append({
                        "source": "electron",
                        "event_type": "renderer_crashed",
                        "details": {
                            "message": f"Electron renderer crashed: {ct.get('title', '')}",
                            "url": ct.get("url", ""),
                            "target_id": ct.get("id", ""),
                        },
                    })
        except Exception:
            pass

    # Deduplicate by message (within single poll)
    seen = set()
    unique_events = []
    for ev in new_events:
        key = ev.get("details", {}).get("message", str(ev))[:200]
        if key not in seen:
            seen.add(key)
            unique_events.append(ev)

    return unique_events[:20]  # Cap to prevent flood


def _watch_event_drops():
    """
    Watch a drop folder for JSON event files. Used for external integrations
    (OpenFang, CI/CD, custom scripts) without HTTP/MCP overhead.

    Drop file format:
        {
          "source": "openfang",
          "event_type": "agent_panic",
          "details": {"agent": "security-auditor", "error": "..."}
        }

    Files are deleted after processing.
    """
    new_events = []
    if not EVENT_DROP_DIR.exists():
        try:
            EVENT_DROP_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            return new_events

    for drop_file in EVENT_DROP_DIR.glob("*.json"):
        try:
            content = drop_file.read_text(encoding="utf-8")
            event_data = json.loads(content)
            new_events.append({
                "drop_file": str(drop_file.name),
                "source": event_data.get("source", "unknown"),
                "event_type": event_data.get("event_type", "external_event"),
                "details": event_data.get("details", {}),
            })
            # Delete after read to prevent re-processing
            drop_file.unlink()
        except Exception as e:
            new_events.append({"watcher_error": str(e), "file": str(drop_file)})
            # Move broken file aside instead of deleting
            try:
                drop_file.rename(drop_file.with_suffix(".json.broken"))
            except Exception:
                pass
    return new_events


def _watch_log_files():
    """Tail watched log files for error patterns."""
    new_events = []
    wstate = _load_watcher_state()
    log_positions = wstate.get("log_positions", {})

    for log_path in _watcher_config["watched_log_files"]:
        try:
            p = Path(log_path)
            if not p.exists():
                continue
            size = p.stat().st_size
            last_pos = log_positions.get(log_path, 0)

            # File rotated
            if size < last_pos:
                last_pos = 0

            if size <= last_pos:
                continue

            with open(p, encoding="utf-8", errors="replace") as f:
                f.seek(last_pos)
                new_content = f.read()
                log_positions[log_path] = f.tell()

            # Check for error patterns
            for line in new_content.splitlines():
                for pat in _watcher_config["log_error_patterns"]:
                    if pat in line:
                        new_events.append({
                            "file": log_path,
                            "pattern": pat,
                            "line": line.strip()[:300],
                        })
                        break
        except Exception as e:
            new_events.append({"watcher_error": str(e), "file": log_path})

    wstate["log_positions"] = log_positions
    _save_watcher_state(wstate)
    return new_events


def _load_watcher_state() -> dict:
    if WATCHER_STATE.exists():
        try:
            return json.loads(WATCHER_STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_watcher_state(state: dict):
    WATCHER_STATE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _watcher_loop():
    """Background daemon loop — polls all enabled sources."""
    while not _watcher_stop.is_set():
        try:
            with _watcher_lock:
                sources = list(_watcher_config["enabled_sources"])

            if "windows_eventlog" in sources:
                events = _watch_windows_eventlog()
                for ev in events:
                    if "watcher_error" in ev:
                        continue
                    _record_event("windows_eventlog",
                                  ev.get("LevelDisplayName", "Error"),
                                  ev, auto_react=True)

            if "process_crashes" in sources:
                events = _watch_process_crashes()
                for ev in events:
                    if "watcher_error" in ev:
                        continue
                    _record_event("process_crashes",
                                  "process_crashed",
                                  ev, auto_react=True)

            if "log_files" in sources:
                events = _watch_log_files()
                for ev in events:
                    if "watcher_error" in ev:
                        continue
                    _record_event("log_files",
                                  ev.get("pattern", "log_error"),
                                  ev, auto_react=True)

            if "electron" in sources:
                events = _watch_electron()
                for ev in events:
                    if "watcher_error" in ev:
                        continue
                    _record_event(ev.get("source", "electron"),
                                  ev.get("event_type", "electron_error"),
                                  ev.get("details", {}), auto_react=True)

            if "file_drop" in sources:
                events = _watch_event_drops()
                for ev in events:
                    if "watcher_error" in ev:
                        continue
                    # Drop events come with their own source field — pass through
                    _record_event(ev.get("source", "file_drop"),
                                  ev.get("event_type", "external_event"),
                                  ev.get("details", {}), auto_react=True)

        except Exception as e:
            # Log to stderr but keep watcher alive
            print(f"[watcher] Error: {e}", file=sys.stderr)

        # Wait poll_interval_secs OR until stop signal
        _watcher_stop.wait(timeout=_watcher_config["poll_interval_secs"])


@mcp.tool()
def watcher_start(sources: list = None, watched_processes: list = None,
                  watched_log_files: list = None, poll_interval_secs: int = 10) -> dict:
    """
    Start the background event watcher daemon.

    sources: list of trigger sources to enable. Options:
        - 'windows_eventlog': Application/System errors (Level 1-2)
        - 'process_crashes': Detect when watched processes die
        - 'log_files': Tail log files for error patterns

    watched_processes: list of process name patterns (e.g. ['python', 'openfang'])
    watched_log_files: list of absolute paths to log files
    poll_interval_secs: how often to poll (default 10s)
    """
    global _watcher_thread

    if _watcher_thread and _watcher_thread.is_alive():
        return {"error": "Watcher already running. Call watcher_stop first."}

    with _watcher_lock:
        _watcher_config["enabled_sources"] = sources or ["windows_eventlog"]
        if watched_processes:
            _watcher_config["watched_processes"] = watched_processes
        if watched_log_files:
            _watcher_config["watched_log_files"] = watched_log_files
        _watcher_config["poll_interval_secs"] = poll_interval_secs

    _watcher_stop.clear()
    _watcher_thread = threading.Thread(target=_watcher_loop, daemon=True, name="issue-detector-watcher")
    _watcher_thread.start()

    notify_user(
        f"🟢 Event watcher started. Sources: {_watcher_config['enabled_sources']}, "
        f"poll: {poll_interval_secs}s",
        level="INFO",
    )
    return {
        "started": True,
        "sources": _watcher_config["enabled_sources"],
        "watched_processes": _watcher_config["watched_processes"],
        "watched_log_files": _watcher_config["watched_log_files"],
        "poll_interval_secs": poll_interval_secs,
    }


@mcp.tool()
def watcher_stop() -> dict:
    """Stop the background event watcher daemon."""
    global _watcher_thread

    if not _watcher_thread or not _watcher_thread.is_alive():
        return {"error": "Watcher not running"}

    _watcher_stop.set()
    _watcher_thread.join(timeout=5)
    notify_user("🔴 Event watcher stopped.", level="INFO")
    return {"stopped": True}


@mcp.tool()
def watcher_status() -> dict:
    """Check the status of the event watcher daemon."""
    is_alive = _watcher_thread is not None and _watcher_thread.is_alive()
    triggered = _load_triggered()
    return {
        "running": is_alive,
        "config": _watcher_config,
        "total_events_recorded": len(triggered.get("events", [])),
        "next_event_id": triggered.get("next_id", 1),
    }


@mcp.tool()
def trigger_event(event_type: str, details: dict = None, source: str = "manual",
                  auto_react: bool = True) -> dict:
    """
    Manually trigger an event. Useful for:
    - Testing the reaction pipeline
    - External hooks (e.g. CI/CD failure webhooks)
    - Test framework integrations (pytest plugin)

    event_type: descriptive name (e.g. 'test_failed', 'service_crashed', 'high_cpu')
    details: dict with event-specific info
    auto_react: if true, run detector automatically (default true)
    """
    eid = _record_event(source, event_type, details or {}, auto_react=auto_react)
    triggered = _load_triggered()
    event = next((e for e in triggered.get("events", []) if e["id"] == eid), None)
    return {
        "event_id": eid,
        "auto_reacted": auto_react,
        "reaction": event.get("reaction") if event else None,
    }


@mcp.tool()
def list_triggered_events(limit: int = 20, only_unprocessed: bool = False) -> dict:
    """List recently triggered events."""
    data = _load_triggered()
    events = data.get("events", [])
    if only_unprocessed:
        events = [e for e in events if not e.get("processed")]
    return {
        "total": len(events),
        "showing": min(limit, len(events)),
        "events": events[-limit:],
    }


@mcp.tool()
def clear_triggered_events() -> dict:
    """Clear all recorded triggered events."""
    before = len(_load_triggered().get("events", []))
    _save_triggered({"next_id": 1, "events": []})
    return {"cleared": before}


@mcp.tool()
def deep_scan_for_event(event_id: str) -> dict:
    """
    Run a deep scan for a specific triggered event (on-demand, not automatic).

    Use this when you want to investigate an event more thoroughly. It runs
    the full scan pipeline (security/system/space) based on the event type
    and adds any findings to pending.

    This is intentionally user-triggered — the watcher itself does NOT
    auto-run deep scans to keep reactions fast and avoid unwanted actions.
    """
    data = _load_triggered()
    event = next((e for e in data.get("events", []) if e["id"] == event_id), None)
    if not event:
        return {"error": f"Event not found: {event_id}"}

    source = event.get("source", "")
    details = event.get("details", {})
    findings = []

    try:
        if source in ("windows_eventlog", "openfang"):
            # Run security scan
            sec = scan_security()
            findings.extend(sec.get("findings", []))
        if source in ("process_crashes", "openfang"):
            # Run system health scan
            sys_scan = scan_system_health()
            findings.extend(sys_scan.get("findings", []))
        if source == "log_files":
            log_path = details.get("file", "")
            for space in SPACE_NAMES:
                if f"\\spaces\\{space}\\" in log_path or f"/spaces/{space}/" in log_path:
                    findings.extend(_scan_one_space(space))
                    break
        if source == "openfang":
            # Scan referenced space if any
            space_hint = details.get("space", "")
            if space_hint in SPACE_NAMES:
                findings.extend(_scan_one_space(space_hint))
        if source == "electron":
            # Electron issues typically relate to desktop/voice spaces
            findings.extend(_scan_one_space("desktop"))

        # Deduplicate (by title)
        seen_titles = set()
        unique_findings = []
        for f in findings:
            t = f.get("title", "")
            if t not in seen_titles:
                seen_titles.add(t)
                unique_findings.append(f)

        # Add to pending
        ids = _add_to_pending(unique_findings) if unique_findings else []

        # Record the deep scan in the event
        event["deep_scan"] = {
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "findings_count": len(unique_findings),
            "pending_ids": ids,
        }
        for i, e in enumerate(data["events"]):
            if e["id"] == event_id:
                data["events"][i] = event
                break
        _save_triggered(data)

        return {
            "event_id": event_id,
            "source": source,
            "findings_count": len(unique_findings),
            "pending_ids": ids,
            "findings": unique_findings,
        }
    except Exception as e:
        return {"error": str(e), "event_id": event_id}


# ============================================================
# VibeMind Notification Inbox
# ============================================================

@mcp.tool()
def notify_user(message: str, level: str = "INFO") -> dict:
    """
    Append a notification to the VibeMind inbox markdown file.
    User can read this in their VibeMind chat/dashboard.
    Level: INFO, WARN, ALERT
    """
    icon = {"INFO": "ℹ️", "WARN": "⚠️", "ALERT": "🚨"}.get(level.upper(), "ℹ️")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\n## {icon} [{level.upper()}] {timestamp}\n\n{message}\n\n---\n"

    if INBOX_FILE.exists():
        existing = INBOX_FILE.read_text(encoding="utf-8")
    else:
        existing = "# VibeMind Issue Detector — Notification Inbox\n"

    INBOX_FILE.write_text(existing + entry, encoding="utf-8")
    return {"notified": True, "inbox": str(INBOX_FILE), "level": level}


@mcp.tool()
def get_inbox(tail: int = 20) -> dict:
    """Read the VibeMind notification inbox (last N entries)."""
    if not INBOX_FILE.exists():
        return {"empty": True, "messages": []}

    content = INBOX_FILE.read_text(encoding="utf-8")
    entries = content.split("---\n")
    return {
        "total_entries": len(entries) - 1,
        "showing_last": min(tail, len(entries) - 1),
        "messages": entries[-tail:] if tail > 0 else entries,
    }


def _autostart_from_config():
    """
    Auto-start the watcher when the MCP server boots.
    Disabled by:
      - WATCHER_AUTOSTART=0 environment variable
      - "autostart": false in watcher_config.json
      - watcher_config.json missing
    """
    if os.environ.get("WATCHER_AUTOSTART", "1") == "0":
        print("[issue-detector] Watcher auto-start disabled (WATCHER_AUTOSTART=0)",
              file=sys.stderr)
        return

    if not WATCHER_CONFIG_FILE.exists():
        print(f"[issue-detector] No watcher_config.json found, skipping auto-start",
              file=sys.stderr)
        return

    try:
        cfg = json.loads(WATCHER_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[issue-detector] Failed to parse watcher_config.json: {e}",
              file=sys.stderr)
        return

    if not cfg.get("autostart", False):
        print("[issue-detector] Watcher auto-start disabled in config",
              file=sys.stderr)
        return

    try:
        result = watcher_start(
            sources=cfg.get("enabled_sources", ["windows_eventlog"]),
            watched_processes=cfg.get("watched_processes", []),
            watched_log_files=cfg.get("watched_log_files", []),
            poll_interval_secs=cfg.get("poll_interval_secs", 30),
        )
        # Apply additional config
        with _watcher_lock:
            if "log_error_patterns" in cfg:
                _watcher_config["log_error_patterns"] = cfg["log_error_patterns"]
            if "min_event_severity" in cfg:
                _watcher_config["min_event_severity"] = cfg["min_event_severity"]

        print(f"[issue-detector] Watcher auto-started: {result}", file=sys.stderr)
    except Exception as e:
        print(f"[issue-detector] Watcher auto-start failed: {e}", file=sys.stderr)


if __name__ == "__main__" and not os.environ.get("_DETECTOR_IMPORTED"):
    _autostart_from_config()
    mcp.run()