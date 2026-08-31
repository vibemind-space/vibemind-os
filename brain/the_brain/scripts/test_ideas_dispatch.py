"""
Smoke-test for Phase O.1 — Brain ↔ Ideas-Space.

Runs four end-to-end checks against the live stack:
  1. Both servers healthy (Brain :5000, Ideas :5102)
  2. Brain proxies idea_list
  3. Brain proxies create + readback
  4. Brain proxies semantic search
  5. Brain auto-dispatch routes @vibemind_ideas to local Ideas

Each check prints PASS/FAIL with relevant evidence. Exits non-zero if
any required check fails.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List

import requests

BRAIN_URL = os.environ.get("BRAIN_URL", "http://127.0.0.1:5000").rstrip("/")
IDEAS_URL = os.environ.get("IDEAS_URL", "http://127.0.0.1:5102").rstrip("/")


def _row(name: str, ok: bool, detail: str = "") -> Dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def _check_health() -> List[Dict[str, Any]]:
    rows = []
    try:
        r = requests.get(f"{BRAIN_URL}/api/health", timeout=5)
        rows.append(_row(
            "brain /api/health", r.status_code == 200,
            f"status={r.status_code}",
        ))
    except Exception as e:
        rows.append(_row("brain /api/health", False, str(e)))
    try:
        r = requests.get(f"{IDEAS_URL}/api/health", timeout=5)
        body = r.json() if r.ok else {}
        rows.append(_row(
            "ideas /api/health",
            r.status_code == 200 and body.get("status") == "alive",
            f"idea_count={body.get('idea_count')}",
        ))
    except Exception as e:
        rows.append(_row("ideas /api/health", False, str(e)))
    try:
        r = requests.get(f"{BRAIN_URL}/api/ideas/health", timeout=5)
        body = r.json() if r.ok else {}
        ok = r.status_code == 200 and body.get("status") == "alive"
        rows.append(_row(
            "brain -> ideas proxy", ok,
            f"reached via brain idea_count={body.get('idea_count')}",
        ))
    except Exception as e:
        rows.append(_row("brain -> ideas proxy", False, str(e)))
    return rows


def _check_list() -> List[Dict[str, Any]]:
    try:
        r = requests.get(f"{BRAIN_URL}/api/ideas/list?limit=3", timeout=10)
        body = r.json() if r.ok else {}
        ideas = body.get("ideas") or []
        return [_row(
            "list via brain", r.ok and isinstance(ideas, list),
            f"got {len(ideas)} ideas",
        )]
    except Exception as e:
        return [_row("list via brain", False, str(e))]


def _check_create_and_search() -> List[Dict[str, Any]]:
    rows = []
    title = f"O.1 smoke {int(time.time())}"
    body = "Eingelegt durch test_ideas_dispatch.py"
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/ideas/create",
            json={"title": title, "content": body, "tags": ["smoke-test"]},
            timeout=10,
        )
        d = r.json() if r.ok else {}
        idea = d.get("idea") or {}
        new_id = idea.get("id")
        rows.append(_row(
            "create via brain", r.ok and bool(new_id),
            f"id={new_id}",
        ))
    except Exception as e:
        rows.append(_row("create via brain", False, str(e)))
        return rows

    try:
        r = requests.post(
            f"{BRAIN_URL}/api/ideas/search",
            json={"query": title, "limit": 5, "min_score": 0.3},
            timeout=30,
        )
        d = r.json() if r.ok else {}
        hits = d.get("ideas") or []
        found = any(h.get("id") == new_id for h in hits)
        top = hits[0] if hits else {}
        rows.append(_row(
            "search round-trip", r.ok and found,
            f"top score={top.get('score')} id={top.get('id')} found={found}",
        ))
    except Exception as e:
        rows.append(_row("search round-trip", False, str(e)))
    return rows


def _check_auto_dispatch() -> List[Dict[str, Any]]:
    rows = []
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/brain/chat",
            json={"message": "@vibemind_ideas Brain orchestriert jetzt VibeMind Spaces"},
            timeout=120,
            allow_redirects=True,
        )
        d = r.json() if r.ok else {}
        ad = d.get("auto_dispatch") or {}
        rows.append(_row(
            "auto-dispatch fired", bool(ad.get("ok")),
            f"target={ad.get('target')} action={ad.get('action')} "
            f"id={ad.get('idea_id') or ad.get('post_id')}",
        ))
        rows.append(_row(
            "auto-dispatch is local",
            ad.get("target") == "ideas_local",
            f"target={ad.get('target')!r}",
        ))
    except Exception as e:
        rows.append(_row("auto-dispatch fired", False, str(e)))
    return rows


def _check_bubbles() -> List[Dict[str, Any]]:
    """Block 1: bubbles + idea_move."""
    rows: List[Dict[str, Any]] = []
    suffix = int(time.time())

    # 1. Create bubble
    bubble_id = None
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/bubbles/create",
            json={"title": f"smoke bubble {suffix}", "description": "block1"},
            timeout=10,
        )
        d = r.json() if r.ok else {}
        bubble = d.get("bubble") or {}
        bubble_id = bubble.get("id")
        rows.append(_row(
            "bubble create", r.ok and bool(bubble_id),
            f"id={bubble_id}",
        ))
    except Exception as e:
        rows.append(_row("bubble create", False, str(e)))
        return rows

    # 2. List sees it
    try:
        r = requests.get(f"{BRAIN_URL}/api/bubbles/list?limit=200", timeout=10)
        d = r.json() if r.ok else {}
        bubbles = d.get("bubbles") or []
        found = any(b.get("id") == bubble_id for b in bubbles)
        rows.append(_row(
            "bubble list contains it", r.ok and found,
            f"total={len(bubbles)} found={found}",
        ))
    except Exception as e:
        rows.append(_row("bubble list contains it", False, str(e)))

    # 3. Create child idea + move into bubble
    child_id = None
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/ideas/create",
            json={"title": f"smoke child {suffix}", "content": "to be moved"},
            timeout=10,
        )
        d = r.json() if r.ok else {}
        child_id = (d.get("idea") or {}).get("id")
        rows.append(_row(
            "child idea created", r.ok and bool(child_id),
            f"id={child_id}",
        ))
    except Exception as e:
        rows.append(_row("child idea created", False, str(e)))

    if child_id and bubble_id:
        try:
            r = requests.post(
                f"{BRAIN_URL}/api/ideas/{child_id}/move",
                json={"parent_id": bubble_id},
                timeout=10,
            )
            d = r.json() if r.ok else {}
            ok = bool(d.get("ok")) and d.get("to_parent") == bubble_id
            rows.append(_row(
                "idea move into bubble", ok,
                f"to_parent={d.get('to_parent')}",
            ))
        except Exception as e:
            rows.append(_row("idea move into bubble", False, str(e)))

    # 4. Delete without force should refuse
    if bubble_id:
        try:
            r = requests.delete(
                f"{BRAIN_URL}/api/bubbles/{bubble_id}",
                timeout=10,
            )
            try:
                d = r.json()
            except Exception:
                d = {}
            err = str(d.get("error") or "")
            body = str(d.get("body") or "")
            refused = (
                r.status_code == 409
                or "bubble has children" in err
                or "bubble has children" in body
                or "HTTP 409" in err
            )
            rows.append(_row(
                "delete refuses non-empty", refused,
                f"status={r.status_code} err={err[:80]}",
            ))
        except Exception as e:
            rows.append(_row("delete refuses non-empty", False, str(e)))

        # 5. Delete with force cascades
        try:
            r = requests.delete(
                f"{BRAIN_URL}/api/bubbles/{bubble_id}?force=true",
                timeout=10,
            )
            d = r.json() if r.ok else {}
            ok = r.ok and bool(d.get("ok"))
            rows.append(_row(
                "delete with force cascades", ok,
                f"deleted={d.get('deleted')} children={d.get('children_deleted')}",
            ))
        except Exception as e:
            rows.append(_row("delete with force cascades", False, str(e)))

    return rows


def _check_phase_q() -> List[Dict[str, Any]]:
    """Phase Q.1-Q.5: ideas-kg, sync, consolidator, state, reward."""
    rows: List[Dict[str, Any]] = []
    suffix = int(time.time())

    # 1. ideas-kg stats reachable + non-empty after Q.2 resync
    try:
        r = requests.get(f"{BRAIN_URL}/api/ideas/kg_stats", timeout=10)
        d = r.json() if r.ok else {}
        rows.append(_row(
            "kg_stats reachable", r.ok and d.get("collection") == "ideas-kg",
            f"points={d.get('points')}",
        ))
    except Exception as e:
        rows.append(_row("kg_stats reachable", False, str(e)))

    # 2. kg_search via Brain proxy returns hits for known query
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/ideas/kg_search",
            json={"query": "realtime mirror", "limit": 3, "threshold": 0.4},
            timeout=30,
        )
        d = r.json() if r.ok else {}
        hits = d.get("hits") or []
        rows.append(_row(
            "kg_search returns hits", r.ok and len(hits) > 0,
            f"count={len(hits)} top_score={(hits[0] or {}).get('score') if hits else None}",
        ))
    except Exception as e:
        rows.append(_row("kg_search returns hits", False, str(e)))

    # 3. State endpoint reachable
    try:
        r = requests.get(f"{BRAIN_URL}/api/ideas/state", timeout=10)
        d = r.json() if r.ok else {}
        snap = d.get("snapshot") or {}
        rows.append(_row(
            "state snapshot has counts", r.ok and "idea_count" in snap and "bubble_count" in snap,
            f"bubbles={snap.get('bubble_count')} ideas={snap.get('idea_count')} kg_points={snap.get('kg_points')}",
        ))
    except Exception as e:
        rows.append(_row("state snapshot has counts", False, str(e)))

    # 4. Auto-dispatch now carries prior_knowledge
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/brain/chat",
            json={"message": "@vibemind_ideas Phase Q smoke note " + str(suffix)},
            timeout=120,
            allow_redirects=True,
        )
        d = r.json() if r.ok else {}
        ad = d.get("auto_dispatch") or {}
        prior = ad.get("prior_knowledge") or {}
        new_idea_id = ad.get("idea_id")
        rows.append(_row(
            "dispatch carries prior_knowledge",
            ad.get("ok") and "hits_count" in prior,
            f"hits={prior.get('hits_count')} idea_id={new_idea_id}",
        ))
    except Exception as e:
        new_idea_id = None
        rows.append(_row("dispatch carries prior_knowledge", False, str(e)))

    # 5. Reward roundtrip — send "perfekt" and verify score on the
    # specific idea_id we just created, fetched via list filter (not kg_search,
    # which may return older near-duplicate hits).
    if new_idea_id:
        try:
            requests.post(
                f"{BRAIN_URL}/api/brain/chat",
                json={"message": "perfekt"},
                timeout=60, allow_redirects=True,
            )
            time.sleep(1)
            r2 = requests.get(
                f"{BRAIN_URL}/api/ideas/list?limit=200", timeout=10,
            )
            d2 = r2.json() if r2.ok else {}
            ideas = d2.get("ideas") or []
            target = next((it for it in ideas if it.get("id") == new_idea_id), None)
            score = (target or {}).get("score")
            rows.append(_row(
                "reward bumped score", isinstance(score, (int, float)) and float(score) > 0,
                f"id={new_idea_id} score_after={score}",
            ))
        except Exception as e:
            rows.append(_row("reward bumped score", False, str(e)))

    # 6. Consolidator stats reachable
    try:
        r = requests.get(f"{BRAIN_URL}/api/ideas/consolidate/suggestions", timeout=10)
        d = r.json() if r.ok else {}
        rows.append(_row(
            "consolidator suggestions endpoint", r.ok and "suggestions" in d,
            f"pending={len(d.get('suggestions') or [])}",
        ))
    except Exception as e:
        rows.append(_row("consolidator suggestions endpoint", False, str(e)))

    return rows


def main() -> int:
    rows: List[Dict[str, Any]] = []
    rows += _check_health()
    rows += _check_list()
    rows += _check_create_and_search()
    rows += _check_auto_dispatch()
    rows += _check_bubbles()
    rows += _check_phase_q()

    print()
    print("| Check                       | Status | Detail")
    print("|-----------------------------|--------|-------")
    for r in rows:
        status = "PASS" if r["ok"] else "FAIL"
        print(f"| {r['name']:<27} | {status:<6} | {r['detail']}")
    print()

    failed = [r for r in rows if not r["ok"]]
    print(f"Result: {len(rows) - len(failed)}/{len(rows)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
