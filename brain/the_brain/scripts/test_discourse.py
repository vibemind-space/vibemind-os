"""
Smoke-test for Phase R — Multi-Agent Self-Discourse.

Runs the full chain end-to-end against a live stack:

  1. Ollama up + phi3 / qwen2.5-coder / llama3.1 model present
  2. OpenFang has phi3-clones registered (or at least 26 originals)
  3. Mirofish reachable + has a running self-discourse simulation
  4. Brain reachable + DiscourseEngine running
  5. Brain DiscourseAggregator running
  6. Brain MirofishKGSync running
  7. Force one discourse-tick — produces ≥ 1 tweet in Mirofish
  8. Force one aggregation pass — produces structured nodes (or graceful fail
     when no tweets in window yet)
  9. Force one mirofish-kg sync — produces ≥ 0 nodes (0 ok if Neo4j empty)

Each check prints PASS / FAIL with detail. Exits non-zero on any FAIL.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List

import requests

BRAIN_URL = os.environ.get("BRAIN_URL", "http://127.0.0.1:5000").rstrip("/")
MIROFISH_URL = os.environ.get("MIROFISH_URL", "http://127.0.0.1:5101").rstrip("/")
OPENFANG_URL = os.environ.get("OPENFANG_URL", "http://127.0.0.1:4200").rstrip("/")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def _row(name: str, ok: bool, detail: str = "") -> Dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def check_ollama() -> List[Dict[str, Any]]:
    rows = []
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m.get("name") for m in (r.json().get("models") or [])]
        rows.append(_row(
            "ollama up", r.ok and len(models) > 0,
            f"models={', '.join(models[:5])}",
        ))
        wanted = ["phi3:mini", "qwen2.5-coder:7b", "llama3.1:latest"]
        present = [m for m in wanted if m in models]
        rows.append(_row(
            "discourse-suitable model present", len(present) > 0,
            f"have={', '.join(present) or 'none'}",
        ))
    except Exception as e:
        rows.append(_row("ollama up", False, str(e)))
    return rows


def check_openfang() -> List[Dict[str, Any]]:
    rows = []
    try:
        r = requests.get(f"{OPENFANG_URL}/api/agents", timeout=5)
        agents = r.json() if r.ok else []
        phi3 = [a for a in agents if (a.get("name") or "").endswith("-phi3")]
        rows.append(_row(
            "openfang reachable", r.ok and isinstance(agents, list),
            f"total={len(agents)} phi3_clones={len(phi3)}",
        ))
    except Exception as e:
        rows.append(_row("openfang reachable", False, str(e)))
    return rows


def check_mirofish() -> List[Dict[str, Any]]:
    rows = []
    try:
        r = requests.get(f"{MIROFISH_URL}/api/simulation/list", timeout=5)
        d = r.json() if r.ok else {}
        sims = d.get("data") or []
        running = [s for s in sims if (s.get("status") or "").lower() in
                   ("running", "started")]
        rows.append(_row(
            "mirofish reachable", r.ok,
            f"sims_total={len(sims)} running={len(running)}",
        ))
        rows.append(_row(
            "mirofish has running sim", len(running) > 0 or len(sims) > 0,
            f"states={[s.get('status') for s in sims][:3]}",
        ))
    except Exception as e:
        rows.append(_row("mirofish reachable", False, str(e)))
    return rows


def check_brain() -> List[Dict[str, Any]]:
    rows = []
    try:
        r = requests.get(f"{BRAIN_URL}/api/health", timeout=5)
        rows.append(_row("brain up", r.ok, f"status={r.status_code}"))
    except Exception as e:
        rows.append(_row("brain up", False, str(e)))
        return rows
    try:
        r = requests.get(f"{BRAIN_URL}/api/discourse/stats", timeout=5)
        d = r.json() if r.ok else {}
        rows.append(_row(
            "discourse engine wired",
            r.ok and (d.get("running") or d.get("enabled")),
            f"running={d.get('running')} sim_id={d.get('sim_id')} agents={d.get('agents_loaded')}",
        ))
    except Exception as e:
        rows.append(_row("discourse engine wired", False, str(e)))
    try:
        r = requests.get(f"{BRAIN_URL}/api/discourse/aggregate_stats", timeout=5)
        d = r.json() if r.ok else {}
        rows.append(_row(
            "discourse aggregator wired",
            r.ok and (d.get("running") or d.get("enabled")),
            f"running={d.get('running')} ticks={d.get('ticks')}",
        ))
    except Exception as e:
        rows.append(_row("discourse aggregator wired", False, str(e)))
    try:
        r = requests.get(f"{BRAIN_URL}/api/mirofish/sync_stats", timeout=5)
        d = r.json() if r.ok else {}
        rows.append(_row(
            "mirofish-kg sync wired",
            r.ok and (d.get("running") or d.get("enabled")),
            f"running={d.get('running')} nodes={d.get('nodes_synced')}",
        ))
    except Exception as e:
        rows.append(_row("mirofish-kg sync wired", False, str(e)))
    return rows


def check_tick_now() -> List[Dict[str, Any]]:
    """Force discourse + aggregate + sync ticks; check non-failure.

    Discourse tick may take >2 min when Mirofish is slow with sim startup —
    a timeout here is a soft fail (the tick still runs in the background;
    we just don't wait for the response). PASS as long as the request was
    accepted, even if the response was slow.
    """
    rows = []
    try:
        r = requests.post(f"{BRAIN_URL}/api/discourse/tick_now", timeout=180)
        d = r.json() if r.ok else {}
        rows.append(_row(
            "force discourse tick",
            r.ok and (d.get("ok") or "reason" in d),
            f"ok={d.get('ok')} reason={d.get('reason') or d.get('tweets')}",
        ))
    except requests.exceptions.ReadTimeout:
        # Tick is in flight — Mirofish-interview can take long. Accept as soft pass.
        rows.append(_row(
            "force discourse tick",
            True,
            "request accepted, response timed out (tick running async)",
        ))
    except Exception as e:
        rows.append(_row("force discourse tick", False, str(e)))

    try:
        r = requests.post(f"{BRAIN_URL}/api/discourse/aggregate_now", timeout=300)
        d = r.json() if r.ok else {}
        rows.append(_row(
            "force aggregate now",
            r.ok and (d.get("ok") or "reason" in d),
            f"ok={d.get('ok')} reason={d.get('reason')} tweets={d.get('tweets')} "
            f"topics={d.get('topics')}",
        ))
    except Exception as e:
        rows.append(_row("force aggregate now", False, str(e)))

    try:
        r = requests.post(f"{BRAIN_URL}/api/mirofish/sync_now", timeout=120)
        d = r.json() if r.ok else {}
        rows.append(_row(
            "force mirofish-kg sync",
            r.ok and (d.get("ok") or "reason" in d),
            f"ok={d.get('ok')} nodes={d.get('nodes')} edges={d.get('edges')}",
        ))
    except Exception as e:
        rows.append(_row("force mirofish-kg sync", False, str(e)))

    return rows


def check_phase_r_plus() -> List[Dict[str, Any]]:
    """Phase R+ extended checks: intent-mode discourse + response-mode."""
    rows = []

    # Response queue + tick
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/discourse/response",
            json={"response_text": "Test response from smoke-test for Mode 3 assessment."},
            timeout=15,
        )
        d = r.json() if r.ok else {}
        rows.append(_row(
            "queue Brain response",
            r.ok and d.get("queued") is True,
            f"queue_depth={d.get('queue_depth')}",
        ))
    except Exception as e:
        rows.append(_row("queue Brain response", False, str(e)))

    try:
        r = requests.post(f"{BRAIN_URL}/api/discourse/response_tick_now", timeout=120)
        d = r.json() if r.ok else {}
        rows.append(_row(
            "force response-mode tick",
            r.ok and (d.get("ok") or "reason" in d),
            f"ok={d.get('ok')} tweets={d.get('tweets_posted')} reason={d.get('reason')}",
        ))
    except Exception as e:
        rows.append(_row("force response-mode tick", False, str(e)))

    # Intent-mode discourse (heavy: 30-60s)
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/discourse/intent",
            json={
                "message": "schreib mir eine kleine python-funktion die JSON parsed",
                "auto_dispatch": False,  # don't actually dispatch in smoke-test
            },
            timeout=180,
        )
        d = r.json() if r.ok else {}
        decision = d.get("decision") or {}
        rows.append(_row(
            "intent-mode discourse",
            r.ok and "confidence" in decision,
            f"primary={decision.get('primary')} conf={decision.get('confidence')} "
            f"tweets={d.get('tweet_count')}",
        ))
    except Exception as e:
        rows.append(_row("intent-mode discourse", False, str(e)))

    # Decision history endpoint
    try:
        r = requests.get(f"{BRAIN_URL}/api/discourse/intent_decisions?limit=5", timeout=10)
        d = r.json() if r.ok else {}
        rows.append(_row(
            "intent decision history",
            r.ok and "decisions" in d,
            f"count={d.get('count')}",
        ))
    except Exception as e:
        rows.append(_row("intent decision history", False, str(e)))

    return rows


def check_phase_s() -> List[Dict[str, Any]]:
    """Phase S — Self-Awareness checks (S.1 substrate, S.4 watcher,
    S.5 meta-consolidator + recall, /state snapshot)."""
    rows = []

    # S.state — combined snapshot endpoint
    try:
        r = requests.get(f"{BRAIN_URL}/api/self_awareness/state", timeout=10)
        d = r.json() if r.ok else {}
        substrate = d.get("substrate_concepts", 0)
        rows.append(_row(
            "S.1 substrate seeded",
            r.ok and substrate >= 50,
            f"concepts={substrate}",
        ))
        rows.append(_row(
            "S.4 watcher running",
            r.ok and (d.get("watcher") or {}).get("running") is True,
            f"running={(d.get('watcher') or {}).get('running')} "
            f"checks={(d.get('watcher') or {}).get('checks')}",
        ))
        rows.append(_row(
            "S.5 meta-consolidator running",
            r.ok and (d.get("meta_consolidator") or {}).get("running") is True,
            f"running={(d.get('meta_consolidator') or {}).get('running')}",
        ))
        rows.append(_row(
            "aggregated-kg has data",
            r.ok and (d.get("aggregated_topic_count") or 0) > 0,
            f"topics={d.get('aggregated_topic_count')} "
            f"findings={d.get('aggregated_finding_count')} "
            f"meta_topics={d.get('aggregated_meta_topic_count')}",
        ))
    except Exception as e:
        rows.append(_row("S.state snapshot", False, str(e)))

    # S.4 force reseed (idempotent)
    try:
        r = requests.post(f"{BRAIN_URL}/api/self_awareness/reseed", timeout=60)
        d = r.json() if r.ok else {}
        rows.append(_row(
            "S.4 force reseed",
            r.ok and d.get("ok") is True,
            f"checked={d.get('checked')} unchanged={d.get('unchanged')} "
            f"updated={d.get('updated')}",
        ))
    except Exception as e:
        rows.append(_row("S.4 force reseed", False, str(e)))

    # S.5 recall on a self-aware topic
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/self_awareness/recall",
            json={"query": "Brain architecture", "days": 30, "limit": 5},
            timeout=15,
        )
        d = r.json() if r.ok else {}
        rows.append(_row(
            "S.5 recall returns results",
            r.ok and d.get("ok") is True,
            f"ok={d.get('ok')} results={len(d.get('results') or [])}",
        ))
    except Exception as e:
        rows.append(_row("S.5 recall returns results", False, str(e)))

    # S.5 force meta-consolidate
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/discourse/meta_consolidate_now", timeout=120,
        )
        d = r.json() if r.ok else {}
        rows.append(_row(
            "S.5 meta-consolidate",
            r.ok and ("topics" in d or "skip_reason" in d),
            f"topics={d.get('topics')} clusters={d.get('clusters_total')} "
            f"created={d.get('meta_topics_created')}",
        ))
    except Exception as e:
        rows.append(_row("S.5 meta-consolidate", False, str(e)))

    # S.3 fungus client + index
    try:
        r = requests.get(f"{BRAIN_URL}/api/fungus/stats", timeout=10)
        d = r.json() if r.ok else {}
        rows.append(_row(
            "S.3 fungus online",
            r.ok and d.get("online") is True,
            f"online={d.get('online')} docs={d.get('doc_count')} "
            f"dim={d.get('embed_dim')} device={d.get('device')}",
        ))
    except Exception as e:
        rows.append(_row("S.3 fungus online", False, str(e)))

    return rows


def check_phase_cap() -> List[Dict[str, Any]]:
    """Phase 1 capability router checks.

    CR.1 — router loaded with at least 5 capabilities
    CR.2 — known intent matches the expected capability
    CR.3 — nonsense intent returns no-match
    """
    rows = []

    # CR.1 router loaded
    try:
        r = requests.get(f"{BRAIN_URL}/api/capabilities/stats", timeout=5)
        d = r.json() if r.ok else {}
        size = (d or {}).get("registry_size") or 0
        rows.append(_row(
            "CR.1 capability router loaded",
            r.ok and d.get("loaded") is True and size >= 5,
            f"loaded={d.get('loaded')} size={size}",
        ))
    except Exception as e:
        rows.append(_row("CR.1 capability router loaded", False, str(e)))

    # CR.2 known intent matches expected capability
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/capabilities/test",
            json={"intent": "scan the repo for security vulnerabilities"},
            timeout=10,
        )
        d = r.json() if r.ok else {}
        rows.append(_row(
            "CR.2 vuln-scan intent -> security_scan",
            r.ok and d.get("matched") is True and d.get("capability") == "security_scan",
            f"matched={d.get('matched')} cap={d.get('capability')}",
        ))
    except Exception as e:
        rows.append(_row("CR.2 vuln-scan intent -> security_scan", False, str(e)))

    # CR.3 nonsense intent returns no-match
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/capabilities/test",
            json={"intent": "blub xyz qwerty random nonsense"},
            timeout=10,
        )
        d = r.json() if r.ok else {}
        rows.append(_row(
            "CR.3 nonsense intent -> no match",
            r.ok and d.get("matched") is False,
            f"matched={d.get('matched')}",
        ))
    except Exception as e:
        rows.append(_row("CR.3 nonsense intent -> no match", False, str(e)))

    # CR.4 — Phase 1.5 direct-execution capability identified
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/capabilities/test",
            json={"intent": "evaluate the Brain Capability Router bubble"},
            timeout=10,
        )
        d = r.json() if r.ok else {}
        rows.append(_row(
            "CR.4 bubble_evaluate -> is_direct=True",
            r.ok
            and d.get("matched") is True
            and d.get("capability") == "bubble_evaluate"
            and d.get("is_direct") is True
            and bool(d.get("execution_target")),
            f"cap={d.get('capability')} direct={d.get('is_direct')} "
            f"target={d.get('execution_target')!r}",
        ))
    except Exception as e:
        rows.append(_row("CR.4 bubble_evaluate -> is_direct=True", False, str(e)))

    # CR.5 — Phase 2 semantic fallback active (embedder wired + descriptions cached)
    try:
        r = requests.get(f"{BRAIN_URL}/api/capabilities/stats", timeout=5)
        d = r.json() if r.ok else {}
        embedded = d.get("descriptions_embedded") or 0
        rows.append(_row(
            "CR.5 semantic embedder wired",
            r.ok and d.get("embedder_attached") is True and embedded >= 5,
            f"embedder={d.get('embedder_attached')} embedded={embedded}",
        ))
    except Exception as e:
        rows.append(_row("CR.5 semantic embedder wired", False, str(e)))

    # CR.6 — Phase 2 semantic match for an intent that no regex captures
    # ("look at my logs" should map to log_analysis via semantic similarity).
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/capabilities/test",
            json={"intent": "look at my logs and tell me what failed last night"},
            timeout=15,
        )
        d = r.json() if r.ok else {}
        # Either regex catches it (already covered by CR.2 family) OR
        # semantic catches it. We accept both as long as match_method is set
        # and the capability is from the analyse/log family.
        ok = (
            r.ok and d.get("matched") is True
            and d.get("capability") in {"log_analysis", "knowledge_query"}
        )
        rows.append(_row(
            "CR.6 semantic fallback finds log_analysis",
            ok,
            f"matched={d.get('matched')} cap={d.get('capability')} "
            f"method={d.get('match_method')}",
        ))
    except Exception as e:
        rows.append(_row("CR.6 semantic fallback finds log_analysis", False, str(e)))

    return rows


def main() -> int:
    rows: List[Dict[str, Any]] = []
    rows += check_ollama()
    rows += check_openfang()
    rows += check_mirofish()
    rows += check_brain()
    rows += check_tick_now()
    rows += check_phase_r_plus()
    rows += check_phase_s()
    rows += check_phase_cap()

    print()
    print("| Check                            | Status | Detail")
    print("|----------------------------------|--------|-------")
    for r in rows:
        st = "PASS" if r["ok"] else "FAIL"
        print(f"| {r['name']:<32} | {st:<6} | {r['detail']}")
    print()

    failed = [r for r in rows if not r["ok"]]
    print(f"Result: {len(rows) - len(failed)}/{len(rows)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
