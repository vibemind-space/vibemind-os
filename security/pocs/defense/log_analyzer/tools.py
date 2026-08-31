"""
Windows Event Log Analysis Tools
==================================
Parses Windows Security, System, and Application logs.
Detects brute-force, privilege escalation, lateral movement, new services.

Uses wevtutil (safe subprocess with fixed arguments, no user input in commands).
"""

import asyncio
import json
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from llm_client import get_model
from openai import AsyncOpenAI


# ================================================================
# HELPER: Parse wevtutil XML output
# ================================================================

def _parse_events_xml(xml_text: str) -> list:
    """Parse wevtutil XML output into list of dicts."""
    events = []
    # wevtutil outputs individual <Event> elements, wrap in root
    wrapped = f"<Events>{xml_text}</Events>"
    try:
        root = ET.fromstring(wrapped)
    except ET.ParseError:
        # Try event by event
        for chunk in xml_text.split("</Event>"):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                elem = ET.fromstring(chunk + "</Event>")
                events.append(_event_to_dict(elem))
            except ET.ParseError:
                continue
        return events

    ns = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}

    for event_elem in root.findall(".//e:Event", ns):
        events.append(_event_to_dict(event_elem))

    return events


def _event_to_dict(event_elem) -> dict:
    """Convert an Event XML element to a dict."""
    ns = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}

    result = {"event_id": None, "time": None, "provider": None, "data": {}}

    # System info
    sys_elem = event_elem.find(".//e:System", ns)
    if sys_elem is None:
        sys_elem = event_elem.find("System")

    if sys_elem is not None:
        eid = sys_elem.find("e:EventID", ns)
        if eid is None:
            eid = sys_elem.find("EventID")
        if eid is not None:
            result["event_id"] = int(eid.text) if eid.text else None

        tc = sys_elem.find("e:TimeCreated", ns)
        if tc is None:
            tc = sys_elem.find("TimeCreated")
        if tc is not None:
            result["time"] = tc.get("SystemTime", "")

        prov = sys_elem.find("e:Provider", ns)
        if prov is None:
            prov = sys_elem.find("Provider")
        if prov is not None:
            result["provider"] = prov.get("Name", "")

    # Event data
    data_elem = event_elem.find(".//e:EventData", ns)
    if data_elem is None:
        data_elem = event_elem.find("EventData")

    if data_elem is not None:
        for child in data_elem:
            name = child.get("Name", f"Data{len(result['data'])}")
            result["data"][name] = child.text or ""

    return result


# ================================================================
# HELPER: Run wevtutil safely
# ================================================================

async def _query_event_log(log_name: str, event_id: str, time_filter: str, max_events: int = 100) -> list:
    """Query Windows Event Log using wevtutil with fixed arguments."""
    xpath = f"*[System[EventID={event_id} and TimeCreated[@SystemTime>='{time_filter}']]]"

    # All arguments are hardcoded or validated integers — no user input injection possible
    proc = await asyncio.create_subprocess_exec(
        "wevtutil", "qe", log_name,
        f"/q:{xpath}",
        "/f:xml",
        f"/c:{max_events}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    output = stdout.decode("utf-8", errors="replace")

    if output.strip():
        return _parse_events_xml(output)
    return []


# ================================================================
# TOOL: parse_security_log
# ================================================================

async def parse_security_log(hours: int = 24, event_ids: str = "4624,4625,4648,4672") -> dict:
    """Parse Windows Security Event Log for login events."""
    result = {
        "log": "Security",
        "hours": hours,
        "events": [],
        "total_events": 0,
        "event_counts": {},
        "warning": None,
    }

    # Validate inputs
    hours = max(1, min(hours, 720))  # 1h to 30 days
    ids = [eid.strip() for eid in event_ids.split(",") if eid.strip().isdigit()]

    since = datetime.now() - timedelta(hours=hours)
    time_filter = since.strftime("%Y-%m-%dT%H:%M:%S")

    EVENT_LABELS = {
        "4624": "Successful Login",
        "4625": "Failed Login",
        "4648": "Explicit Credential Use",
        "4672": "Admin Token Assigned",
        "4688": "New Process Created",
        "4720": "User Account Created",
        "4732": "User Added to Group",
    }

    for eid in ids:
        try:
            events = await _query_event_log("Security", eid, time_filter)
            for e in events:
                e["event_id_label"] = EVENT_LABELS.get(str(e.get("event_id", "")), "")
            result["events"].extend(events)
            result["event_counts"][eid] = len(events)
        except asyncio.TimeoutError:
            result["warning"] = f"Timeout querying Event ID {eid}"
        except Exception as e:
            result["warning"] = f"Error querying Security log: {e}"

    result["total_events"] = len(result["events"])
    result["events"] = result["events"][:200]

    return result


# ================================================================
# TOOL: parse_system_log
# ================================================================

async def parse_system_log(hours: int = 24) -> dict:
    """Parse Windows System Event Log for service changes, shutdowns."""
    result = {
        "log": "System",
        "hours": hours,
        "events": [],
        "new_services": [],
        "service_changes": [],
        "shutdowns": [],
        "total_events": 0,
        "warning": None,
    }

    hours = max(1, min(hours, 720))
    since = datetime.now() - timedelta(hours=hours)
    time_filter = since.strftime("%Y-%m-%dT%H:%M:%S")

    for eid, category in [("7045", "new_services"), ("7040", "service_changes"), ("1074", "shutdowns")]:
        try:
            events = await _query_event_log("System", eid, time_filter, max_events=50)
            result[category] = events
            result["events"].extend(events)
        except Exception as e:
            result["warning"] = f"Error querying System log: {e}"

    result["total_events"] = len(result["events"])
    return result


# ================================================================
# TOOL: detect_brute_force
# ================================================================

async def detect_brute_force(hours: int = 24, threshold: int = 5) -> dict:
    """Detect brute-force login attempts (multiple failed logins in short time)."""
    result = {
        "hours": hours,
        "threshold": threshold,
        "brute_force_detected": False,
        "attack_sources": [],
        "total_failed_logins": 0,
        "issues": [],
    }

    sec_result = await parse_security_log(hours=hours, event_ids="4625")
    failed_logins = sec_result.get("events", [])
    result["total_failed_logins"] = len(failed_logins)

    by_source = defaultdict(list)
    for event in failed_logins:
        source = event.get("data", {}).get("IpAddress") or event.get("data", {}).get("WorkstationName") or "local"
        target = event.get("data", {}).get("TargetUserName", "?")
        by_source[source].append({"time": event.get("time", ""), "target_user": target})

    for source, attempts in by_source.items():
        if len(attempts) >= threshold:
            target_users = list(set(a["target_user"] for a in attempts))
            result["brute_force_detected"] = True
            result["attack_sources"].append({
                "source": source,
                "attempt_count": len(attempts),
                "target_users": target_users[:10],
                "first_attempt": attempts[0]["time"],
                "last_attempt": attempts[-1]["time"],
            })

    if result["brute_force_detected"]:
        sources = ", ".join(a["source"] for a in result["attack_sources"][:3])
        result["issues"].append({
            "severity": "CRITICAL",
            "category": "Brute Force",
            "title": f"Brute-force login attack from {sources}",
            "description": (
                f"{result['total_failed_logins']} failed logins in {hours}h. "
                f"Sources: {sources}."
            ),
        })

    return result


# ================================================================
# TOOL: detect_priv_escalation
# ================================================================

async def detect_priv_escalation(hours: int = 24) -> dict:
    """Detect privilege escalation (admin token assigned to unexpected users)."""
    result = {
        "hours": hours,
        "admin_logins": [],
        "suspicious": [],
        "issues": [],
    }

    KNOWN_ADMIN_USERS = {"SYSTEM", "Administrator", "DWM-1", "DWM-2", "UMFD-0", "UMFD-1"}

    sec_result = await parse_security_log(hours=hours, event_ids="4672")
    for event in sec_result.get("events", []):
        user = event.get("data", {}).get("SubjectUserName", "?")
        domain = event.get("data", {}).get("SubjectDomainName", "?")

        result["admin_logins"].append({"user": f"{domain}\\{user}", "time": event.get("time", "")})

        if user not in KNOWN_ADMIN_USERS and "SYSTEM" not in user.upper():
            result["suspicious"].append({"user": f"{domain}\\{user}", "time": event.get("time", "")})

    if result["suspicious"]:
        users = ", ".join(set(s["user"] for s in result["suspicious"][:5]))
        result["issues"].append({
            "severity": "HIGH",
            "category": "Privilege Escalation",
            "title": f"Admin privileges assigned to: {users}",
            "description": "Users not in the expected admin list received elevated privileges.",
        })

    return result


# ================================================================
# TOOL: detect_new_services
# ================================================================

async def detect_new_services(hours: int = 24) -> dict:
    """Detect newly installed Windows services (common persistence method)."""
    result = {
        "hours": hours,
        "new_services": [],
        "suspicious_services": [],
        "issues": [],
    }

    SUSPICIOUS_KEYWORDS = [
        "powershell", "cmd", "wscript", "cscript", "mshta",
        "certutil", "bitsadmin", "rundll32", "regsvr32",
        "temp", "tmp", "appdata", "downloads", "public",
        "base64", "encoded", "bypass",
    ]

    sys_result = await parse_system_log(hours=hours)

    for event in sys_result.get("new_services", []):
        service_name = event.get("data", {}).get("ServiceName", "?")
        image_path = event.get("data", {}).get("ImagePath", "?")

        svc = {"name": service_name, "path": image_path, "time": event.get("time", "")}
        result["new_services"].append(svc)

        path_lower = image_path.lower()
        if any(kw in path_lower for kw in SUSPICIOUS_KEYWORDS):
            svc["suspicious"] = True
            result["suspicious_services"].append(svc)

    if result["suspicious_services"]:
        names = ", ".join(s["name"] for s in result["suspicious_services"][:3])
        result["issues"].append({
            "severity": "CRITICAL",
            "category": "Persistence",
            "title": f"Suspicious new service(s): {names}",
            "description": "New services installed with suspicious paths or commands.",
        })

    return result


# ================================================================
# TOOL: build_timeline
# ================================================================

async def build_timeline(hours: int = 24) -> dict:
    """Build chronological timeline of all security-relevant events."""
    result = {"hours": hours, "timeline": [], "total_events": 0}

    sec_result = await parse_security_log(hours=hours, event_ids="4624,4625,4648,4672,4688")
    sys_result = await parse_system_log(hours=hours)

    all_events = []

    for event in sec_result.get("events", []):
        user = event.get("data", {}).get("TargetUserName") or event.get("data", {}).get("SubjectUserName", "?")
        all_events.append({
            "time": event.get("time", ""),
            "source": "Security",
            "event_id": event.get("event_id"),
            "label": event.get("event_id_label", ""),
            "user": user,
            "details": json.dumps(event.get("data", {}), default=str)[:200],
        })

    for event in sys_result.get("events", []):
        svc_name = event.get("data", {}).get("ServiceName", "")
        all_events.append({
            "time": event.get("time", ""),
            "source": "System",
            "event_id": event.get("event_id"),
            "label": f"Service: {svc_name}" if svc_name else str(event.get("event_id")),
            "user": "",
            "details": json.dumps(event.get("data", {}), default=str)[:200],
        })

    all_events.sort(key=lambda e: e.get("time", ""))
    result["timeline"] = all_events[:500]
    result["total_events"] = len(all_events)

    return result


# ================================================================
# TOOL: think
# ================================================================

async def think(reasoning_prompt: str, llm_client: AsyncOpenAI) -> dict:
    """Use LLM to reason about log findings and create attack narrative."""
    response = await llm_client.chat.completions.create(
        model=get_model("think"),
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior SOC analyst reviewing Windows Event Logs.\n\n"
                    "Analyze the events and identify:\n"
                    "1. Attack patterns (brute-force, lateral movement, privilege escalation)\n"
                    "2. Timeline of suspicious activity\n"
                    "3. Affected accounts and systems\n\n"
                    "Structure:\n"
                    "REASONING:\n- Step 1: ...\n\n"
                    "CONCLUSION: <one sentence>\n\n"
                    "SEVERITY: <CRITICAL|HIGH|MEDIUM|LOW|INFO>\n"
                ),
            },
            {"role": "user", "content": reasoning_prompt},
        ],
    )

    text = response.choices[0].message.content.strip()
    reasoning = text
    conclusion = ""
    severity = "INFO"

    if "CONCLUSION:" in text:
        parts = text.split("CONCLUSION:")
        reasoning = parts[0].strip()
        remainder = parts[1].strip()
        if "SEVERITY:" in remainder:
            conclusion_parts = remainder.split("SEVERITY:")
            conclusion = conclusion_parts[0].strip()
            severity = conclusion_parts[1].strip().split()[0] if conclusion_parts[1].strip() else "INFO"
        else:
            conclusion = remainder

    return {"reasoning": reasoning, "conclusion": conclusion, "severity": severity}


# ================================================================
# TOOL DEFINITIONS + DISPATCH
# ================================================================

TOOL_DEFINITIONS = [
    {"type": "function", "function": {"name": "parse_security_log", "description": "Parse Windows Security Event Log. Gets login successes (4624), failures (4625), explicit credentials (4648), admin tokens (4672).", "parameters": {"type": "object", "properties": {"hours": {"type": "integer", "description": "Hours to look back (default 24)"}, "event_ids": {"type": "string", "description": "Comma-separated Event IDs"}}, "required": []}}},
    {"type": "function", "function": {"name": "parse_system_log", "description": "Parse Windows System Event Log. Finds new services (7045), service changes (7040), shutdowns (1074).", "parameters": {"type": "object", "properties": {"hours": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "detect_brute_force", "description": "Detect brute-force login attacks. Correlates failed logins by source. Threshold: 5+ failures.", "parameters": {"type": "object", "properties": {"hours": {"type": "integer"}, "threshold": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "detect_priv_escalation", "description": "Detect privilege escalation. Finds admin token assignments to unexpected users.", "parameters": {"type": "object", "properties": {"hours": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "detect_new_services", "description": "Detect newly installed services. Flags services with suspicious paths.", "parameters": {"type": "object", "properties": {"hours": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "build_timeline", "description": "Build chronological timeline of ALL security events from Security + System logs.", "parameters": {"type": "object", "properties": {"hours": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "think", "description": "Reason about log findings and create attack narrative.", "parameters": {"type": "object", "properties": {"reasoning_prompt": {"type": "string"}}, "required": ["reasoning_prompt"]}}},
]

TOOL_DISPATCH = {
    "parse_security_log": parse_security_log,
    "parse_system_log": parse_system_log,
    "detect_brute_force": detect_brute_force,
    "detect_priv_escalation": detect_priv_escalation,
    "detect_new_services": detect_new_services,
    "build_timeline": build_timeline,
}
