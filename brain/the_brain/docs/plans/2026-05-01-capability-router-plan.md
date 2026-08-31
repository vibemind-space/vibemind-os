# Capability Router — Implementation Plan (Phase 1)

**Date:** 2026-05-01
**Companion to:** [2026-05-01-capability-router-design.md](./2026-05-01-capability-router-design.md)
**Phase:** 1 (routing only, no execution, no validation)
**Risk:** low — additive, broadcast fallback preserved
**Estimated effort:** ~3-4h focused work

## Reality-check before coding (added after agent audit on 2026-05-01)

Live OpenFang has **21 domain agents** (each with `smart` Sonnet variant + `local` qwen2.5-coder variant), plus a few utility agents (assistant, brain-fallback, brain-trainer, vibemind, unnamed). The agents in `vibemind-os/openfang/agents/*` (code-reviewer, debugger, security-auditor, data-scientist, etc.) are **NOT registered in OpenFang at runtime** — those folders look like agent templates that never got wired up.

Practical consequence: the YAML in this plan **must reference the 21 live domain agents**, not the repo folders. The live pool is heavily security/ops-focused (poc-* dominate); broader domains like data-science or content-writing don't have specialised agents yet — they'd fall through to broadcast or to brain-coder + rowboat-knowledge as generic fallbacks.

Before implementing, also exploit the dual-variant structure:

- discourse-round (the cheap "I CAN / NOT MINE" voting) → use `-phi3` variants (`local` tier) so 5 agents × Q tokens stays cheap
- primary-dispatch (the real work) → use the `smart` variant (Sonnet)

`_dispatch_to_openfang` already does the strip-`-phi3` resolve, so the smart variant gets picked automatically when phi3-name is the primary. The capability YAML can list either variant; router resolves to local for discourse, smart for dispatch.

## Goal

Aus dem Design-Doc Phase 1 in echten Code überführen: ein YAML-driven router der incoming intents auf einen kuratierten subset der 49 OpenFang agents matched, **bevor** discourse läuft. Wenn kein match → existing broadcast-behavior bleibt.

Sichtbares outcome am Ende:

```
POST /api/discourse/intent {"message":"scan this repo for security vulnerabilities"}
↓
trace shows: capability=security_scan (matched via regex), agents=[poc-security-scanner, poc-vuln-scanner, poc-secret-vault, poc-forensics, poc-red-blue]
5 agents reply (not 25), aggregator picks primary, dispatch happens, response back.
```

Latency target: **2-5x reduction** für matched intents (3-5 dispatch calls statt 25).

## Out-of-scope (Phase 2-5)

- Semantic fallback embedding
- Validator phase
- Tool execution / artifact generation
- Self-curating registry
- coding-engine / n8n integration

Diese landen in eigenen `2026-05-XX-capability-router-phaseN-plan.md` files.

## Architecture (one diagram)

```
┌─────────────────────────────────────────────────────────────┐
│  POST /api/discourse/intent                                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ DiscourseEngine        │
              │  .tick_intent(intent)  │
              └────┬───────────────────┘
                   │
                   ▼   (NEW)
       ┌──────────────────────┐
       │ CapabilityRouter     │
       │  .route(intent)      │── regex match against capabilities.yaml
       └────┬─────────────────┘
            │
       ┌────┴─────┐
       │          │
   match found    no match
       │          │
       │          └──► broadcast to all 25 (existing path)
       │
       ▼
  agents = [primary[], supporting[]]  (≤5 agents)
       │
       ▼
  _query_round_responses(agents, intent)   (unchanged)
       │
       ▼
  IntentAggregator.decide(...)             (unchanged)
       │
       ▼
  if confidence ≥ threshold and auto_dispatch:
      _dispatch_to_openfang(primary)       (unchanged)
       │
       ▼
  return {capability, decision, dispatched}
```

Nur **eine neue Klasse + ein YAML + ein hook**. Bestehende code-pfade unverändert.

## File-by-file changes

### 1. NEW: `data/capabilities.yaml`

5 initial capabilities. Wertvolle Domains die heute schon abgedeckt sind:

```yaml
# Brain capability registry — maps intents to specialized OpenFang agents.
# Each entry is matched in order; first regex hit wins. No regex match →
# router returns None → DiscourseEngine falls back to broadcast.
#
# Field reference:
#   capability     — short snake_case id, used in trace + stats
#   description    — human readable, also used as semantic-fallback text in Phase 2
#   match_patterns — list of regex strings (ignorecase, anchored as \b...\b)
#   agents.primary — preferred candidates for the dispatch role
#   agents.supporting — additional voices for the discourse round

- capability: bubble_evaluate
  description: "evaluate a bubble/idea's readiness for project promotion through 5 expert perspectives (coding, swe_design, research, rowboat, ideas) — returns score/100 + prediction + missing_items"
  match_patterns:
    - "(evaluate|bewerte|prüf|check) (the|this|my)?\\s*(bubble|idea|idee)"
    - "(ready|reif)\\s+(for|für)\\s+(project|umsetzung|production)"
    - "(promote|befördern)\\s+(this|the)?\\s*(bubble|idea|idee)"
    - "design (review|check|critique)"
    - "go.?no.?go"
    - "readiness (check|score|eval)"
  execution_target: "direct:spaces.mirofish.tools.mirofish_tools:evaluate_bubble_readiness"
  # Direct execution — calls existing 5-agent eval pattern, no discourse needed.
  # Aggregator + judges already implemented in evaluate_bubble_readiness().

- capability: code_search
  description: "find code, locate a function/class, or get code-snippets relevant to a question"
  match_patterns:
    - "(where|wo) (is|ist)\\s+(the|der|die|das)?\\s*\\w+"
    - "find (the|all)?\\s*(code|function|class|method)"
    - "show me (the|how)\\s+\\w+"
    - "wie (funktioniert|geht)\\s+\\w+"
    - "code (for|about|that does)\\s+\\w+"
  agents:
    primary: [fungus-search]
    supporting: [brain-coder, rowboat-knowledge]

- capability: security_scan
  description: "scan for vulnerabilities, audit secrets, check security posture"
  match_patterns:
    - "(scan|check|audit) .* (security|vulnerab|secret|cve)"
    - "(security|vuln) (scan|check|audit)"
    - "find (vuln|cve|exposed secret)"
    - "ist .* (sicher|sicherheit)"
  agents:
    primary: [poc-security-scanner, poc-vuln-scanner]
    supporting: [poc-secret-vault, poc-forensics, poc-red-blue]

- capability: incident_response
  description: "diagnose, contain, or mitigate a security or ops incident"
  match_patterns:
    - "(security|prod|outage)\\s+(incident|alarm|issue|alert)"
    - "etwas ist\\s+(kaputt|down|defekt)"
    - "system\\s+(is\\s+down|crashed|hung)"
    - "investigate\\s+(the|this)?\\s*(alert|incident)"
    - "(suspicious|verdächtig)\\s+\\w+"
  agents:
    primary: [poc-alerter, poc-forensics]
    supporting: [poc-log-analyzer, sensor-monitor, poc-vuln-scanner]

- capability: log_analysis
  description: "parse, search, summarise log files for patterns, errors, or anomalies"
  match_patterns:
    - "(analy[sz]e|parse|search) (the|my|some)?\\s*log"
    - "log\\s+(analy|search|grep)"
    - "what happened in (the)?\\s*log"
    - "errors? (in|aus) .* log"
  agents:
    primary: [poc-log-analyzer]
    supporting: [poc-forensics, sensor-monitor]

- capability: knowledge_query
  description: "answer a factual question from project knowledge (rowboat, supermemory, KG)"
  match_patterns:
    - "wie viele\\s+\\w+"
    - "how many\\s+\\w+"
    - "what (is|are)\\s+\\w+"
    - "(was ist|wer ist|wo ist)\\s+\\w+"
    - "list (the|all)?\\s*\\w+"
    - "show me (all|the)?\\s*\\w+"
  agents:
    primary: [rowboat-knowledge, supermemory]
    supporting: [fungus-search]

- capability: email_action
  description: "compose, send, personalise, or route an email"
  match_patterns:
    - "(send|write|compose|schick) (an|eine)?\\s*(e?mail|nachricht)"
    - "(reply to|antwort auf)\\s+\\w+"
    - "email (to|an)\\s+\\w+"
  agents:
    primary: [poc-email-response, poc-email-sender]
    supporting: [poc-email-personalizer, poc-email-verteiler]

- capability: site_check
  description: "verify a website is up, reachable, or behaves correctly"
  match_patterns:
    - "(check|verify|test) .* (site|url|website|page)"
    - "(is|ist) .* (up|reachable|online|verfügbar)"
    - "site\\s+(verifier|check)"
  agents:
    primary: [poc-site-verifier]
    supporting: [sensor-monitor]

- capability: chitchat
  description: "greetings, small talk, status questions about Brain itself"
  match_patterns:
    - "^(hi|hallo|hey|hello|moin)\\b"
    - "wie geht('s| es dir)"
    - "what (are|r) (you|u)\\s*"
    - "wer bist du"
  agents:
    primary: [assistant]
    supporting: []
```

Begründung dieser 9 (alle referenzierten Agents existieren in OpenFang, verifiziert 2026-05-01):

- **bubble_evaluate**: KEIN Discourse, KEIN OpenFang-broadcast. Direct routing zu existing `evaluate_bubble_readiness()` in `spaces/mirofish/tools/mirofish_tools.py`. Diese Funktion implementiert bereits den 5-Perspektiven-Eval (`coding`, `swe_design`, `research`, `rowboat`, `ideas`) → `total_score/100` + `prediction` + `missing_items` als TODO-list. Bei `promote_bubble()` läuft das schon automatisch über den wizard-shuttle. Capability-Router pickt das nur als routing-target auf — siehe direct-execution section in design-doc. Klassisches Beispiel "discourse macht keinen Sinn weil pattern existiert".
- **code_search**: einziger search-Spezialist ist fungus-search. brain-coder + rowboat-knowledge als supporting fallbacks.
- **security_scan / incident_response / log_analysis**: das ist Vibemind's eigentliches stärke-feld. 6+ poc-* agents decken die security-domain dicht ab.
- **knowledge_query**: rowboat-knowledge + supermemory + fungus-search als generischer Q&A-pool.
- **email_action**: vier poc-email-* agents — komplettes domain-cluster.
- **site_check**: schmal aber existiert dedicated.
- **chitchat**: assistant ist explizit dafür da.

Was bewusst **nicht** abgedeckt ist: code review (kein review-agent registriert), data science / analytics, content writing, legal/HR — keine passenden Agents. Diese intents fallen Phase-1 durch zu broadcast — und der no-match counter im Router macht sichtbar wo die agent-pool gaps sind. Phase 5 (self-curating registry) kann daraus dann ableiten welche neuen agents gebaut werden sollten.

Was bewusst **nicht** als capability existiert: `code_change` / "implement X". Direct execution-Tasks gehören nicht in den Discourse-Loop — brain-coder direkt aufrufen ist 10x effizienter als 5 phi3-clones zu fragen "I CAN" zu sagen. Discourse macht nur Sinn wo es echte multi-perspective-Bewertung gibt, nicht für single-actor execution. Auch nicht: ein neues `code_design` capability bauen — `bubble_evaluate` deckt design-evaluation bereits über die existing 5-spaces-eval ab und ist vollständig implementiert + getestet im wizard-flow.

### 2. NEW: `core/capability_router.py`

```python
"""Capability Router — Phase 1 (regex routing only).

Maps incoming intents to a kuratierten subset of OpenFang agents based on
data/capabilities.yaml. Falls back to None on no-match — caller decides
whether to broadcast.

See docs/plans/2026-05-01-capability-router-design.md for the full design.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class CapabilityMatch:
    """Result of router.route() — routed agents + provenance."""

    capability: str
    description: str
    primary_names: List[str]
    supporting_names: List[str]
    matched_pattern: str
    match_method: str = "regex"  # "regex" | "semantic" (Phase 2) | "fallback"

    @property
    def all_agent_names(self) -> List[str]:
        return list(self.primary_names) + list(self.supporting_names)


@dataclass
class _CompiledCapability:
    capability: str
    description: str
    primary_names: List[str]
    supporting_names: List[str]
    patterns: List[re.Pattern] = field(default_factory=list)


class CapabilityRouter:
    """Regex-driven router. Phase 1 — semantic fallback comes in Phase 2."""

    def __init__(self, registry_path: Path):
        self.registry_path = Path(registry_path)
        self._capabilities: List[_CompiledCapability] = []
        self._stats = {
            "matches": 0,
            "regex_matches": 0,
            "no_match": 0,
            "load_errors": 0,
        }
        self._load()

    def _load(self) -> None:
        if not self.registry_path.exists():
            logger.warning(f"[cap-router] registry not found: {self.registry_path}")
            return
        try:
            data = yaml.safe_load(self.registry_path.read_text(encoding="utf-8")) or []
        except Exception as e:
            logger.error(f"[cap-router] yaml parse failed: {e}")
            self._stats["load_errors"] += 1
            return

        compiled: List[_CompiledCapability] = []
        for entry in data:
            try:
                cap = entry["capability"]
                pats = entry.get("match_patterns") or []
                compiled.append(_CompiledCapability(
                    capability=cap,
                    description=entry.get("description", ""),
                    primary_names=list(entry.get("agents", {}).get("primary") or []),
                    supporting_names=list(entry.get("agents", {}).get("supporting") or []),
                    patterns=[re.compile(p, re.IGNORECASE) for p in pats],
                ))
            except Exception as e:
                logger.warning(f"[cap-router] skipping bad entry: {e}")
                self._stats["load_errors"] += 1
        self._capabilities = compiled
        logger.info(
            f"[cap-router] loaded {len(compiled)} capabilities from {self.registry_path}"
        )

    def route(self, intent: str) -> Optional[CapabilityMatch]:
        """First regex hit wins. Returns None on no-match."""
        if not intent or not intent.strip():
            self._stats["no_match"] += 1
            return None
        for cap in self._capabilities:
            for pat in cap.patterns:
                if pat.search(intent):
                    self._stats["matches"] += 1
                    self._stats["regex_matches"] += 1
                    return CapabilityMatch(
                        capability=cap.capability,
                        description=cap.description,
                        primary_names=cap.primary_names,
                        supporting_names=cap.supporting_names,
                        matched_pattern=pat.pattern,
                        match_method="regex",
                    )
        self._stats["no_match"] += 1
        return None

    def reload(self) -> None:
        """Force re-read of YAML — useful when watcher detects changes."""
        self._capabilities = []
        self._load()

    def stats_dict(self) -> Dict[str, Any]:
        return {
            "registry_path": str(self.registry_path),
            "registry_size": len(self._capabilities),
            "capabilities": [c.capability for c in self._capabilities],
            **self._stats,
        }
```

~120 lines. Pure data + regex. No external state. Easy to unit-test.

### 3. EDIT: `core/discourse_engine.py`

Three small changes:

**a) Setter** (mirroring `set_fungus_client` from S.3):

```python
def set_capability_router(self, router) -> None:
    """Phase 1 capability routing — wire CapabilityRouter so tick_intent
    can pick a focused agent subset instead of broadcasting to all 25."""
    self._cap_router = router
```

**b) Init nullable field** (alongside `_fungus_client = None`):

```python
self._fungus_client = None    # S.3
self._cap_router = None       # capability routing
```

**c) `tick_intent` — narrow agent set if matched** (top of method, before existing logic):

```python
def tick_intent(self, intent_text, context=None, ...):
    # ... existing input validation, sim_id load ...

    # Phase 1 — capability routing
    cap_match = None
    if self._cap_router is not None:
        cap_match = self._cap_router.route(intent_text)

    if cap_match is not None:
        all_agents = self._agents
        wanted = set(n.lower() for n in cap_match.all_agent_names)
        narrowed = [
            a for a in all_agents
            if (a.get("name") or "").lower().rstrip("-phi3") in wanted
            or (a.get("name") or "").lower() in wanted
        ]
        if narrowed:
            agents_for_round = narrowed
            logger.info(
                f"[discourse] capability={cap_match.capability} "
                f"matched {len(narrowed)}/{len(all_agents)} agents"
            )
        else:
            # YAML referred to agent names not present in OpenFang —
            # fall back to broadcast and warn for registry-rot detection.
            logger.warning(
                f"[discourse] capability={cap_match.capability} "
                f"matched but no agents resolved — falling back to broadcast"
            )
            agents_for_round = all_agents
    else:
        agents_for_round = self._agents

    # ... rest of tick_intent unchanged, just use `agents_for_round` instead
    # of `self._agents` in the dispatch + aggregator pipeline.
```

Plus include `cap_match.capability` + `cap_match.matched_pattern` in the returned dict so `/api/discourse/intent` exposes the routing decision.

### 4. EDIT: `web/brain_server.py`

Wire the router during startup, similar to FungusClient:

```python
# Phase 1 — Capability router
state.capability_router = None
try:
    from core.capability_router import CapabilityRouter
    cap_path = _BRAIN_DIR / "data" / "capabilities.yaml"
    cr = CapabilityRouter(cap_path)
    state.capability_router = cr
    if cr._capabilities:
        de = getattr(state, "discourse_engine", None)
        if de is not None and hasattr(de, "set_capability_router"):
            de.set_capability_router(cr)
        print(f"  [OK] CapabilityRouter loaded ({len(cr._capabilities)} capabilities)")
    else:
        print(f"  [WARN] CapabilityRouter loaded with 0 capabilities (registry empty?)")
except Exception as e:
    print(f"  [WARN] CapabilityRouter init failed: {e}")
```

Place this **after** discourse_engine init, **after** FungusClient (so the order is: DE → fungus → cap-router; cap-router needs DE to exist for the wire-up).

### 5. EDIT: `web/routers/introspection.py`

Two new endpoints (10-line each):

```python
@router.get("/api/capabilities/stats")
async def capability_stats(request: Request):
    """Phase 1 — router state: registry size, match counters."""
    cr = getattr(request.app.state, "capability_router", None)
    if cr is None:
        return JSONResponse({"loaded": False, "message": "no router wired"})
    return JSONResponse({"loaded": True, **cr.stats_dict()})


@router.post("/api/capabilities/test")
async def capability_test(request: Request):
    """Test the router without running discourse. Body: {"intent": "..."}.
    Returns the match (or no-match) so registry can be debugged."""
    cr = getattr(request.app.state, "capability_router", None)
    if cr is None:
        return JSONResponse({"error": "router not loaded"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    intent = (body.get("intent") or "").strip()
    if not intent:
        return JSONResponse({"error": "intent required"}, status_code=400)
    m = cr.route(intent)
    if m is None:
        return JSONResponse({"matched": False, "intent": intent})
    return JSONResponse({
        "matched": True,
        "intent": intent,
        "capability": m.capability,
        "primary": m.primary_names,
        "supporting": m.supporting_names,
        "matched_pattern": m.matched_pattern,
        "match_method": m.match_method,
    })
```

Place these next to the existing `/api/fungus/stats` endpoint (Phase S.3 conventions).

### 6. EDIT: `scripts/test_discourse.py`

Three new smoke-checks under a `check_phase_cap()` function (mirror of `check_phase_s()`):

```python
def check_phase_cap() -> List[Dict[str, Any]]:
    rows = []

    # CR.1 router loaded
    try:
        r = requests.get(f"{BRAIN_URL}/api/capabilities/stats", timeout=5)
        d = r.json() if r.ok else {}
        rows.append(_row(
            "CR.1 capability router loaded",
            r.ok and d.get("loaded") is True and (d.get("registry_size") or 0) >= 5,
            f"loaded={d.get('loaded')} size={d.get('registry_size')}",
        ))
    except Exception as e:
        rows.append(_row("CR.1 capability router loaded", False, str(e)))

    # CR.2 known intent matches expected capability
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/capabilities/test",
            json={"intent": "scan for vulnerabilities in this repo"},
            timeout=10,
        )
        d = r.json() if r.ok else {}
        rows.append(_row(
            "CR.2 vuln-scan intent → security_scan",
            r.ok and d.get("matched") is True and d.get("capability") == "security_scan",
            f"matched={d.get('matched')} cap={d.get('capability')}",
        ))
    except Exception as e:
        rows.append(_row("CR.2 vuln-scan intent → security_scan", False, str(e)))

    # CR.3 nonsense intent returns no-match
    try:
        r = requests.post(
            f"{BRAIN_URL}/api/capabilities/test",
            json={"intent": "blub xyz qwerty random nonsense"},
            timeout=10,
        )
        d = r.json() if r.ok else {}
        rows.append(_row(
            "CR.3 nonsense intent → no match",
            r.ok and d.get("matched") is False,
            f"matched={d.get('matched')}",
        ))
    except Exception as e:
        rows.append(_row("CR.3 nonsense intent → no match", False, str(e)))

    return rows
```

Plus call `rows += check_phase_cap()` in `main()` before printing the table.

## Step-by-step execution order

1. Write `data/capabilities.yaml` with 5 entries (above).
2. Write `core/capability_router.py` (the class).
3. **Smoke-test the class standalone** before any wiring:
   ```bash
   python -c "from core.capability_router import CapabilityRouter; \
              r = CapabilityRouter('data/capabilities.yaml'); \
              print(r.stats_dict()); \
              print(r.route('review my code')); \
              print(r.route('xyz nonsense'))"
   ```
4. Edit `discourse_engine.py` — add init field + setter + tick_intent narrowing.
5. **Pure-Python compile check** (`py_compile`) on the edited file.
6. Edit `web/brain_server.py` — wire router after discourse + fungus init.
7. Edit `web/routers/introspection.py` — add 2 endpoints.
8. Edit `scripts/test_discourse.py` — add 3 smoke-checks.
9. Restart Brain.
10. Run smoke-test → expect 26-27/27 PASS (existing 23/24 + 3 new CR.x).
11. Run a real intent that matches `code_review`, verify trace shows narrowed agent count.
12. Run a real intent that matches nothing, verify trace shows broadcast (existing behavior).
13. Update Phase-S/CR section in `MEMORY.md`.

## Definition of Done

- 9 capabilities loaded from YAML
- `/api/capabilities/stats` returns size=9
- `/api/capabilities/test` matches "scan for vulnerabilities" → `security_scan` with primary `[poc-security-scanner, poc-vuln-scanner]`
- `/api/capabilities/test` returns matched=false for "xyz nonsense"
- `/api/discourse/intent` with "scan repo for CVE" routes to ≤5 agents (not 25), trace shows `capability=security_scan`
- `/api/discourse/intent` with no match (e.g. "review my code", since no review agent registered) falls back to broadcast (25 agents) — confirms graceful degrade
- Smoke-test 26-27/27 PASS (depending on whether mirofish-running-sim already counts)
- No regression in existing checks (S.1-S.5, fungus, idle discourse)

## Failure modes + recovery

| Symptom | Likely cause | Fix |
|---|---|---|
| `[WARN] CapabilityRouter init failed` on Brain start | YAML syntax error | Validate via `python -c "import yaml; yaml.safe_load(open('data/capabilities.yaml'))"` |
| Router loads but registry_size=0 | YAML structure wrong | Compare against the example in `data/capabilities.yaml` block above |
| All intents → no match | Patterns too anchored | Test each pattern with `python -c "import re; print(re.compile(r'...', re.I).search('test intent'))"` |
| Match returns but `narrowed` is empty (warning logged) | Agent name in YAML doesn't exist in OpenFang | Run `curl http://127.0.0.1:4200/api/agents` and align names with the registry |
| Existing intent tests now broken | tick_intent regression | Set `CAPABILITY_ROUTER_ENABLED=0` env-var bypass (add as guard at top of router lookup) |

## Rollback plan

If anything breaks, three escape hatches in increasing severity:

1. Empty the YAML — router loads with 0 capabilities, every intent falls back to broadcast. Behavior identical to pre-change.
2. Comment out the `CapabilityRouter` block in `brain_server.py` — router never wired, `_cap_router` stays None, `tick_intent` short-circuits the new path entirely.
3. `git revert` the commit — all three new files removed, two edits reverted.

Each rollback step takes <30s. There is no data migration; capabilities.yaml is read-only at runtime in Phase 1.

## Phase 1.5 — Direct execution + Feedback-Loop pattern

**Status:** plan, scoped (added 2026-05-01 after agent audit + bubble lifecycle test)
**Prerequisite for:** `bubble_evaluate` and any other "we already have python that does this" capability
**Risk:** low — additive, isolated to capabilities that explicitly opt-in via `execution_target`

### Why Phase 1.5 now

Phase 1 (regex routing) only narrows the **agent pool**. For `bubble_evaluate` the agent pool isn't the right answer — we don't want 5 agents to discuss how to evaluate, we want to **call `evaluate_bubble_readiness()` directly** and get the structured result back. The 5-perspective evaluation already exists inside that function (verified 2026-05-01: 56/100 NEEDS_WORK with 64 missing_items via gpt-5.5).

But: a raw 64-item list isn't a useful response to a user. The interesting pattern is **direct execution → discourse over the result → reflective response**. That's why Phase 1.5 ships direct-execution AND the feedback-loop together.

### YAML schema extension

```yaml
- capability: bubble_evaluate
  description: "evaluate a bubble's readiness for project promotion"
  match_patterns:
    - "(evaluate|bewerte|prüf) (the|this|my)?\\s*(bubble|idea)"
    - "readiness (check|score)"
  execution_target: "direct:spaces.mirofish.tools.mirofish_tools:evaluate_bubble_readiness"
  result_arg_extractor: "regex:bubble[\\s\"']*[:=]?\\s*[\"']?([^\"']+)[\"']?"
  feedback_loop:
    enabled: true
    discourse_agents:
      primary: [brain-coder, fungus-search]
      supporting: [poc-security-scanner, rowboat-knowledge]
    discourse_prompt_template: |
      A bubble was just evaluated for project-readiness. Here is the raw output:

      Score: {result.total_score}/100
      Prediction: {result.prediction}

      Per-perspective assessments:
      {result.per_agent_summary}

      Top missing items ({result.missing_items_count} total):
      {result.missing_items_top10}

      The user's original question was:
      {original_intent}

      Reply with:
      I_AGREE / I_DISAGREE: <one-line stance>
      KEY_GAP: <the single most important missing item from your perspective>
      NEXT_STEP: <one concrete actionable next step>
```

Three new fields beyond Phase 1's `execution_target`:

- **`result_arg_extractor`** — how to pull the function's argument from the user's intent. For `evaluate_bubble_readiness(bubble_name)`, regex `bubble["']?([^"']+)["']?` extracts the quoted/unquoted bubble name.
- **`feedback_loop.enabled`** — opt-in. Without it, direct execution returns the raw result and we're done (cheap + deterministic).
- **`feedback_loop.discourse_agents` + `discourse_prompt_template`** — when enabled, Brain takes the structured result, formats it via template, dispatches to a focused agent set for a reflective round, then aggregates as usual.

### Execution flow

```text
User intent:
  "evaluate the Brain Capability Router bubble"
       │
       ▼
CapabilityRouter.route("evaluate the Brain Capability Router bubble")
       │
       ├── regex match → capability=bubble_evaluate
       │
       ▼
DispatcherKind.DIRECT (NEW path, not the existing agent-broadcast)
       │
       ├── parse arg: bubble_name="Brain Capability Router"  (via result_arg_extractor)
       │
       ├── import spaces.mirofish.tools.mirofish_tools
       │
       ├── result = evaluate_bubble_readiness("Brain Capability Router")
       │             { total_score: 56, prediction: NEEDS_WORK,
       │               per_agent: {...5 perspectives...},
       │               missing_items: [...64 items...] }
       │
       ▼
feedback_loop.enabled? ─────── no ──► return result as response (done)
       │ yes
       ▼
Format prompt via discourse_prompt_template:
  "A bubble was evaluated. Score: 56/100. Top gaps: <top10>. Original question: ..."
       │
       ▼
Dispatch to focused agent set [brain-coder, fungus-search,
                                poc-security-scanner, rowboat-knowledge]
       │
       ▼
Each agent replies with I_AGREE / I_DISAGREE / KEY_GAP / NEXT_STEP
       │
       ▼
IntentAggregator (existing) ranks: {primary, supporting, risks, confidence}
       │
       ▼
Build final response that combines:
  - The raw eval result (score + prediction)
  - The discourse take (does the team agree, key gaps, next step)
       │
       ▼
auto_dispatch primary agent (Sonnet) for the final synthesized recommendation
       │
       ▼
Return: {result, discourse_decision, dispatched.response}
```

The user gets back **one coherent answer** that ties the deterministic eval to the team's interpretation. No 64-item dump. No "Score: 56/100" without context. The eval is the **evidence**, the discourse is the **judgment**.

### File-by-file changes (in addition to Phase 1)

#### NEW: `core/capability_executor.py`

Small helper that handles direct execution. Imports the target module, finds the function, calls it, normalises the return.

```python
class DirectExecutor:
    """Resolves and invokes a 'direct:module:function' execution target.
    Validates the target on registry-load so a typo or missing module
    fails fast (capability marked inactive) instead of at runtime."""

    def __init__(self, target: str):
        # target = "direct:spaces.mirofish.tools.mirofish_tools:evaluate_bubble_readiness"
        kind, module_path, func_name = target.split(":", 2)
        if kind != "direct":
            raise ValueError(f"unsupported executor: {kind}")
        self.module_path = module_path
        self.func_name = func_name
        self._fn = None  # lazy

    def is_resolvable(self) -> bool:
        try:
            self._resolve()
            return True
        except Exception:
            return False

    def _resolve(self):
        if self._fn is None:
            mod = importlib.import_module(self.module_path)
            self._fn = getattr(mod, self.func_name)
        return self._fn

    def call(self, *args, **kwargs) -> Dict[str, Any]:
        try:
            t0 = time.time()
            out = self._resolve()(*args, **kwargs)
            return {
                "ok": True,
                "result": out,
                "elapsed_s": time.time() - t0,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "elapsed_s": time.time() - t0,
            }
```

#### EDIT: `core/capability_router.py` (extend Phase 1)

```python
@dataclass
class CapabilityMatch:
    # ... existing fields ...
    execution_target: Optional[str] = None       # "direct:..." or None
    arg_extractor: Optional[str] = None          # regex string
    feedback_loop: Optional[Dict[str, Any]] = None
    is_direct: bool = False                      # convenience flag
```

Router's `_load` validates `execution_target`: if `direct:`, instantiate `DirectExecutor`, check `is_resolvable()`, mark capability inactive on failure with a logged warning so registry-rot is visible at startup.

#### EDIT: `core/discourse_engine.py`

`tick_intent` gains a branch at the top:

```python
def tick_intent(self, intent_text, ...):
    cap_match = self._cap_router.route(intent_text) if self._cap_router else None

    if cap_match and cap_match.is_direct:
        return self._handle_direct_capability(cap_match, intent_text)

    # existing flow: narrow agents, dispatch, aggregate
    ...
```

`_handle_direct_capability(cap_match, intent_text)`:

1. Extract args via `cap_match.arg_extractor` regex against `intent_text`
2. Call `DirectExecutor.call(*args)` → result dict
3. If `cap_match.feedback_loop.enabled` → format `discourse_prompt_template` with result, dispatch to `discourse_agents`, aggregate, dispatch primary
4. Else → wrap result and return immediately
5. In both cases, return shape matches the existing `tick_intent` return: `{decision, dispatched, capability, result}` (with `result` as the new field for direct path)

#### EDIT: `web/routers/introspection.py`

`/api/discourse/intent` response gains optional `capability` + `result` fields. `/api/capabilities/test` reports if a capability is direct + whether `is_resolvable()`.

### Minimum viable feedback-loop test

Before scaling to many capabilities, we need to prove the pattern with `bubble_evaluate`:

1. Phase 1 router with `bubble_evaluate` capability registered, `feedback_loop.enabled=true`
2. POST `/api/discourse/intent` with `{"message": "evaluate the Brain Capability Router bubble"}`
3. Trace shows: regex match → DirectExecutor → `evaluate_bubble_readiness("Brain Capability Router")` → 56/100 result → 4-agent discourse round → primary picks consolidated next-step
4. Final response is a 3-paragraph synthesis (eval summary + team take + concrete next step) — not a raw 64-item dump

That's the proof of the pattern. After that, every domain that has a python evaluator (security_audit, log_summary, etc.) can opt in by adding a YAML entry.

### Follow-ups (Phase 2+)

- `execution_target: "http:..."` — adds Option B from the discussion (HTTP wrappers). No new dispatcher needed: just an HTTP-flavored Executor next to DirectExecutor. Existing capabilities get a wrapper for free if Brain runs on a different host than the tool.
- `result_to_kg` field — write the result back into Brain's aggregated-kg as a node (so meta-consolidator clusters bubble-evaluations across runs).
- Watcher integration: when a tool-implementing module changes (file hash diff), reload the Executor so live-edits work without Brain restart.
- Metrics: per-capability `total_calls`, `feedback_loop_disagreement_rate` (= % of rounds where ≥half the agents I_DISAGREE'd with the deterministic result) — surfaces evaluator drift.

## Generic Phase 2-5 followups (own plan-files later)

- ~~Add `_semantic_fallback` using FungusClient's embedder~~ → **done in Phase 2** (2026-05-01).
- ~~Add embedding cache for capability descriptions at router-load time~~ → **done**.
- ~~Track `semantic_matches` separately in stats~~ → **done** (`regex_matches` vs `semantic_matches` in stats_dict).
- When semantic fallback fires too often (≥30% of intents), surface as a self-awareness substrate concept "registry has gaps" → discourse can discuss what new capability to add. *(still pending)*

## Phase 2.5 — Anchor phrases (implemented 2026-05-01)

After Phase 2 went live, semantic recall on paraphrase-style intents
plateaued at ~55%. Diagnosed cause: a single description embedding has
to span the whole semantic surface of a capability, but that surface is
too wide for a single 1024-dim Qwen vector to cover well.

Fix: each capability declares 3-7 short **anchor phrases** in YAML — each
phrase represents a distinct way a user might phrase that intent. They get
embedded alongside the description, and `_semantic_route()` takes the
**max cosine across all of them** (description + anchors).

YAML schema extension:

```yaml
- capability: code_search
  description: "find code locate function class method..."
  anchor_phrases:
    - "find me the implementation of a function"
    - "locate where a piece of code is defined"
    - "show me the source for the X module"
    - "where is the auth code"
    - "search the codebase for a function"
  match_patterns: [...]
  agents: {...}
```

Effects measured on the 29-intent semantic stress test:

- Recall: 16/29 (55%) → 27/29 (93%)
- 21 semantic matches (vs 12 with description-only)
- 0 false positives on off-domain queries
- `anchors_embedded` count exposed in `/api/capabilities/stats`
- `matched_pattern` includes `via desc` or `via anchor[N]` provenance

The two remaining stress fails are **legitimate intent overlaps**
(architecture_question vs code_search; idea_add vs email_action) — not
recall failures. To resolve those would need either a tie-breaker rule
or finer-grained capabilities, both Phase 3+ territory.

Cost: 37 anchor embeddings on top of 15 description embeddings = 52 cached
1024-dim vectors per Brain boot. Negligible memory + 200ms extra to embed
on `set_embedder()`.

- **ConsensusGate als deterministischer Aggregator**: ThoughtJury (`core/thought_jury.py`) hat schon ein 5-judge-pattern mit gewichteter aggregation für CTE thoughts (cosine-based, kein LLM). Prinzip ist 1:1 übertragbar auf zukünftige multi-evaluator capabilities: 5 evaluator agents → 5 verdict-vectors → ConsensusGate aggregates → deterministisches reward-signal. Das wäre cheaper + reproducible als die aktuelle Groq-llama-Aggregation. Phase 3 oder 4 — braucht erst stable Phase-2-data um die judge-weights zu kalibrieren. (Hinweis: `bubble_evaluate` macht bereits weighted aggregation in `_format_readiness_report()`; ConsensusGate-pattern wäre eher für neue capabilities die discourse-based bleiben.)
