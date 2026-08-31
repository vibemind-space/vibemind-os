"""Track C of the OpenFang Hand bridge -- marketing -> Hand subroutine.

Lets the marketing layer kick off a Hand task and walk away. The Hand
runs autonomously (web research, etc.) and eventually writes the result
back via Track A (HTTP POST /api/proposals) or Track B (event_publish
on events:tasks:marketing).

Design notes:
- OpenFang exposes POST /api/agents/{id}/message which queues a message
  for an existing agent and returns immediately. The actual LLM loop
  runs in OpenFang's runtime, not here.
- We DON'T poll the result. The whole point of the bridge is async --
  the Hand drops its answer into audience_proposals when it's done, the
  UI reads it, the human approves.
- We DO write an audit row immediately so the action is traceable even
  if the Hand never delivers (LLM timeout, deactivated Hand, etc.).

NO send pipeline impact: this never writes to audiences / emails /
campaign_sends / campaigns. Phase-1 contract intact.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from ..sync import _db


logger = logging.getLogger("marketing.hand_bridge")

OPENFANG_BASE_DEFAULT = "http://127.0.0.1:4200"


# Allowed Hand-ids and the prompt-templates we send them. Hard-coded so a
# Hand-id can't be smuggled in from user input.
_HAND_TEMPLATES = {
    "lead-hand": (
        "Run one Lead Hand discovery cycle for the following ICP and "
        "stage the result as an audience proposal via the marketing "
        "bridge:\n\n"
        "Target Industry: {industry}\n"
        "Target Role: {role}\n"
        "Geographic Focus: {geo}\n"
        "Leads per report: {n}\n"
        "Extra notes: {notes}\n\n"
        "When you finish, POST the result to "
        "{api_base}/api/proposals as JSON with shape "
        "{{name, filter_dsl, candidate_emails, rationale, source: 'lead-hand'}}. "
        "Do NOT send any mail. Do NOT write to marketing.emails directly."
    ),
    "researcher-hand": (
        "Run one Researcher Hand investigation on the following topic and "
        "stage actionable leads as an audience proposal:\n\n"
        "Topic: {topic}\n"
        "Depth: {depth}\n"
        "Geographic Focus: {geo}\n"
        "Extra notes: {notes}\n\n"
        "When you finish, POST to {api_base}/api/proposals. "
        "Do NOT send any mail."
    ),
    "collector-hand": (
        "Run one Collector Hand monitoring cycle on the following target "
        "and stage any newly found contacts as an audience proposal:\n\n"
        "Target Subject: {topic}\n"
        "Geographic Focus: {geo}\n"
        "Extra notes: {notes}\n\n"
        "When you finish, POST to {api_base}/api/proposals."
    ),
}


def _openfang_url() -> str:
    return os.environ.get("OPENFANG_BASE_URL", OPENFANG_BASE_DEFAULT)


def _api_base() -> str:
    return os.environ.get("MARKETING_API_BASE_URL", "http://127.0.0.1:5510")


def _resolve_hand_agent_id(hand_id: str, base: str) -> Optional[str]:
    """Look up the active agent UUID for a given Hand id.

    OpenFang's /api/hands returns active instances; we filter by
    hand_id and return the first running one. Returns None if the
    Hand isn't activated.
    """
    try:
        req = urllib.request.Request(f"{base}/api/hands", method="GET")
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read() or b"[]")
    except Exception as e:
        logger.warning("openfang /api/hands probe failed: %s", e)
        return None
    if not isinstance(data, list):
        # Some OpenFang versions wrap in {hands: [...]} -- accept either.
        if isinstance(data, dict) and "hands" in data:
            data = data.get("hands") or []
        else:
            return None
    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get("hand_id") == hand_id and item.get("status") in (
            "Active", "active",
        ):
            agent_id = item.get("agent_id")
            if isinstance(agent_id, str):
                return agent_id
    return None


def request_hand_research(hand_id: str,
                          *,
                          industry: str = "",
                          role: str = "",
                          geo: str = "",
                          topic: str = "",
                          depth: str = "thorough",
                          n: int = 25,
                          notes: str = "",
                          timeout_s: int = 15) -> Dict[str, Any]:
    """Subroutine entry: kick off a Hand task, return immediately.

    Returns {success, message, data{job_ref, hand_id, agent_id}}.
    The Hand's actual result will land later in audience_proposals --
    poll list_proposals to discover it.

    No mail-side-effects. Audit row is written even if OpenFang is down.
    """
    if hand_id not in _HAND_TEMPLATES:
        return {
            "success": False,
            "message": f"unknown hand_id {hand_id!r}; allowed: {list(_HAND_TEMPLATES)}",
            "data": None,
        }
    api_base = _api_base()
    template = _HAND_TEMPLATES[hand_id]
    prompt = template.format(
        industry=industry or "(any)",
        role=role or "(any)",
        geo=geo or "(global)",
        topic=topic or "(unspecified)",
        depth=depth,
        n=int(n),
        notes=notes or "(none)",
        api_base=api_base,
    )

    of_base = _openfang_url()
    agent_id = _resolve_hand_agent_id(hand_id, of_base)
    job_ref = None
    error: Optional[str] = None

    if not agent_id:
        error = f"Hand {hand_id!r} is not activated on {of_base}"
    else:
        try:
            payload = json.dumps({"message": prompt}).encode("utf-8")
            req = urllib.request.Request(
                f"{of_base}/api/agents/{agent_id}/message",
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as r:
                resp = json.loads(r.read() or b"{}")
            job_ref = resp.get("message_id") or resp.get("id") or "submitted"
        except urllib.error.HTTPError as e:
            error = f"openfang HTTP {e.code}: {e.reason}"
        except Exception as e:
            error = f"openfang request failed: {type(e).__name__}: {e}"

    # Audit BEFORE returning so the trail exists even if the Hand never
    # actually runs.
    try:
        _db.execute_via_docker(
            f"INSERT INTO marketing.audit_log (actor, action, target_table, payload) "
            f"VALUES ("
            f"  {_db._sql_literal('hand_bridge:request')}, "
            f"  {_db._sql_literal('request_' + hand_id)}, "
            f"  'marketing.audience_proposals', "
            f"  {_db._sql_literal(json.dumps({'hand_id': hand_id, 'agent_id': agent_id, 'job_ref': job_ref, 'error': error, 'prompt_preview': prompt[:200], 'industry': industry, 'role': role, 'geo': geo, 'topic': topic, 'notes': notes}, default=str))}::jsonb"
            f")"
        )
    except Exception as e:
        logger.exception("audit insert failed (non-fatal): %s", e)

    if error:
        return {"success": False, "message": error,
                "data": {"hand_id": hand_id, "agent_id": agent_id}}
    return {
        "success": True,
        "message": f"Hand {hand_id} task submitted (job_ref={job_ref})",
        "data": {
            "hand_id": hand_id,
            "agent_id": agent_id,
            "job_ref": job_ref,
            "prompt_preview": prompt[:200],
            "expected_callback": f"{api_base}/api/proposals",
        },
    }


__all__ = ["request_hand_research"]
