# Capability Router — Design

**Date:** 2026-05-01
**Status:** Skizze (pre-implementation)
**Author:** discussion 2026-05-01

## Problem

Brain hat heute zwei Loops:

- **Idle discourse** — alle 30s random KG-slice → 3 OpenFang-clones reden darüber → aggregator → topics/findings/decisions in `aggregated-kg`. Funktioniert.
- **Intent-mode** — user-frage → ALLE 25 phi3-clones bekommen denselben prompt → aggregator pickt primary → primary kriegt OpenFang-call → text response zurück. Funktioniert auch.

Das ist **Reasoning-Mode**: Brain *redet* über Probleme.

Was fehlt für **Action-Mode**: Brain *löst* Probleme.

Konkret drei Lücken:

1. **Capability-Discovery fehlt.** Aktuell sehen alle 25 agents jeden intent. Aggregator ranked nach Antwort-Qualität. Das ist vom Output rückwärts. Wir wollen vom Capability-Index vorwärts: "Event X braucht Capability Y, dafür sind Agents A/B/C qualifiziert" — discourse läuft dann nur über die 3, nicht 25.
2. **Execution fehlt.** Agents antworten heute mit `"I CAN: do X via API"` — Vorschläge in Text-form. Kein tool-call wird tatsächlich gemacht. Der dispatched.response ist text, kein artifact.
3. **Validation fehlt.** Wenn Agent X claimed "ich hab's gemacht", validiert niemand. Vibemind hat `code-reviewer`, `test-engineer`, `security-auditor` als capabilities — die sind aber nicht in den loop verdrahtet.

## Was Vibemind schon hat (recyclen, nicht neu bauen)

- **49 OpenFang agents** mit klarer Domain-Differenzierung (`code-reviewer`, `debugger`, `security-auditor`, `data-scientist`, `home-automation`, `health-tracker`, ...). Liegen in `vibemind-os/openfang/agents/<name>/`.
- **DiscourseEngine.tick_intent()** dispatched parallel an N agents via Mirofish-interview.
- **IntentAggregator** ranked die responses zu `{primary, supporting, risks, confidence}`.
- **auto_dispatch** im Discourse — wenn confidence ≥ threshold, ruft Brain den primary agent real via OpenFang an.
- **Brain.kg** kann classifications speichern (space + event tagging via Phase R) — für die Lookup-Seite des Routers.
- **MCP tool-binding** — agents können tool calls returnen (siehe `mcp_vibemind_db_insert` example aus dem 2026-04-30 E2E test). Tools werden aber von Brain noch nicht ausgeführt.

## Vorschlag: capability_router.py

### Datenmodell — `data/capabilities.yaml`

Pflegbar als YAML, lebt in Brain's data-dir, vom Watcher monitored:

```yaml
- capability: code_review
  description: "review code diffs for bugs, style, security, tests"
  match_patterns:
    - "review (the|this|my)? (code|diff|pr)"
    - "code review"
    - "ist (das|der code) okay"
  agents:
    primary: [code-reviewer, langchain-code-reviewer]
    supporting: [debugger, test-engineer, security-auditor]
  validator: test-engineer
  expected_artifact: "review_comments"  # text|file|diff|test_result

- capability: incident_response
  description: "diagnose, contain, mitigate a security or ops incident"
  match_patterns:
    - "(security|prod|outage) (incident|alarm|issue)"
    - "etwas ist kaputt"
  agents:
    primary: [brain-security, security-auditor]
    supporting: [ops, devops-lead, brain-monitor]
  validator: brain-security
  expected_artifact: "incident_report"

- capability: code_change
  description: "implement a feature or bugfix in the codebase"
  match_patterns:
    - "implement (a|the)? .* (in|for) .*"
    - "fix (the)? .* (bug|issue|error)"
    - "add .* to (the)? .*"
  agents:
    primary: [coder, brain-coder]
    supporting: [architect, code-reviewer]
  validator: test-engineer
  expected_artifact: "code_diff"
```

Anfangs ~10 Capabilities. Wachsen organisch wenn neue Domains dazukommen. Brain könnte später vorschlagen welche capabilities fehlen wenn intents zu oft "no match" haben (Self-Awareness extension).

### Router class

`core/capability_router.py`:

```python
class CapabilityRouter:
    """Maps incoming intents/events to a curated set of agents.

    Replaces the 'broadcast to all 25' default with focused 3-5 agent
    discourse based on a YAML registry. Falls back to broadcast if no
    capability matches.
    """

    def __init__(self, registry_path: Path):
        self.registry = self._load_registry(registry_path)
        self._compile_patterns()

    def route(self, intent: str) -> Optional[CapabilityMatch]:
        """Return a CapabilityMatch or None if nothing matched.
        CapabilityMatch carries the capability metadata + agent ids
        (resolved from agent names against OpenFang)."""
        # 1. Regex-pattern match (fast, deterministic)
        for cap in self.registry:
            for pat in cap.compiled_patterns:
                if pat.search(intent):
                    return self._build_match(cap, intent)
        # 2. Fallback: KG-similarity match against capability descriptions
        #    (requires an embedding pass — only on regex miss)
        return self._semantic_fallback(intent)

    def _semantic_fallback(self, intent: str) -> Optional[CapabilityMatch]:
        # Embed intent, compare to capability.description embeddings,
        # return best match if cosine >= 0.6, else None.
        ...

    def stats_dict(self) -> dict:
        return {
            "registry_size": len(self.registry),
            "matches": self._matches,
            "regex_matches": self._regex_matches,
            "semantic_matches": self._semantic_matches,
            "no_match": self._no_match,
        }
```

### Integration mit DiscourseEngine

`tick_intent` wird zwei-stufig:

```python
def tick_intent(self, intent_text, context=None, ...):
    # NEW: capability lookup first
    match = None
    if self._cap_router is not None:
        match = self._cap_router.route(intent_text)

    if match is not None:
        agents = self._resolve_agents(match.agents.primary + match.agents.supporting)
        logger.info(f"[discourse] intent matched capability {match.capability}, "
                    f"using {len(agents)} agents instead of all {len(self._agents)}")
    else:
        # Fallback: existing broadcast behavior
        agents = self._agents
        logger.info(f"[discourse] no capability match, broadcasting to all {len(agents)}")

    # ...rest unchanged: dispatch to agents, aggregate, primary, dispatch
```

Das ist additiv. Wenn `cap_router` nicht set ist oder kein match → existing behavior. Kein breaking change.

### Validation phase (Phase 2)

Nach dispatch + response, wenn `match.validator` set ist:

```python
def tick_intent(self, intent_text, ...):
    # ... existing dispatch logic ...
    primary_response = dispatched["response"]

    if match and match.validator and dispatched.get("artifact"):
        validator_agent = self._resolve_agent(match.validator)
        validation = self._dispatch_validation(
            validator_agent,
            artifact=dispatched["artifact"],
            original_intent=intent_text,
            primary_response=primary_response,
        )
        result["validation"] = validation
        # If validator says "fail", Brain decides: retry with different
        # primary, or surface fail to user.
```

`_dispatch_validation` ist ein zweiter OpenFang-call mit einem prompt der dem validator den artifact zeigt + fragt: "ist das korrekt? gib JSON {pass: bool, issues: [...]}.

### Execution phase — der schwerste Teil

Heute returnt der primary-dispatch nur **text**. Damit Validation Sinn macht, brauchen wir **artifacts** (file diffs, test results, log entries). Drei Pfade:

**a) MCP-tool-execution loop.** Wenn primary-response ein tool-call ist (parsed JSON mit `name` + `arguments`), Brain führt das tool über MCP-bridge aus, gibt result zurück an primary mit "now describe what you did", primary returnt summary + reference zu artifact-file. Loop bis primary "DONE" sagt oder N steps erreicht. Das ist im Grunde was Claude Code selbst tut — agentic loop.

**b) Hand off to coding-engine.** Vibemind hat eine eigene coding-engine als space (Daves replacement). Statt MCP-loop in Brain selbst, übergibt Brain den intent an die coding-engine via API call. Engine arbeitet, schreibt artifacts, returnt completion-marker.

**c) Workflow via n8n.** Vibemind hat n8n laufen. Brain triggert workflow, workflow ruft tools, returnt result. Skaliert auf non-code domains (email, scheduling, scraping).

Empfehlung: **(b) für code, (c) für ops/integration, (a) als fallback**. Capability-Registry erweitert sich dann zu:

```yaml
- capability: code_change
  ...
  execution_target: "coding-engine"  # or "mcp_loop" or "n8n:workflow_id"
```

## Phases

### Phase 1 — Routing only (low risk, high signal)

- `data/capabilities.yaml` mit 5-10 capabilities
- `core/capability_router.py` mit regex matching only (kein semantic fallback)
- `DiscourseEngine.set_capability_router()` setter
- `tick_intent` ruft router, narrows agent set wenn match, sonst broadcast
- `/api/discourse/intent` returnt `capability` + `match_method` im response

**Wert:** sofort 10x latency reduction für matched intents, klarere primaries weil weniger Echo-Antworten.

### Phase 2 — Semantic fallback

- Embed capability descriptions beim Router-load
- Embed incoming intent on regex-miss
- Cosine similarity ≥ 0.6 = match
- Stats: regex_matches vs semantic_matches → measure registry coverage

**Wert:** capabilities müssen nicht jeden Wortlaut treffen.

### Phase 3 — Validation

- `validator` field im match → second dispatch nach primary
- Validator returnt `{pass: bool, issues: [...]}`
- Bei fail: log + optional retry mit alternative primary
- `aggregated-kg` speichert validation outcomes als feature signal für routing

**Wert:** "this capability+agent pair worked" learned über Zeit.

### Phase 4 — Execution

- Pro capability: `execution_target` field
- `coding-engine` integration für `code_change`, `code_review`
- `n8n` integration für `incident_response`, `data_pipeline`
- `mcp_loop` für everything else

**Wert:** Brain wird vom Diskussions-Loop zum Action-Loop.

### Phase 5 — Self-Curating Registry

- Brain trackt no-match intents
- Wenn ein Cluster von ähnlichen no-match intents entsteht (semantic clustering), schlägt Brain eine neue Capability vor
- Vorschlag landet als discourse-topic, agents diskutieren wie die capability aussehen sollte
- Approved capability wird automatisch in `capabilities.yaml` geschrieben (PR-style mit human review)

**Wert:** Registry wächst aus Nutzung, nicht aus Vorausdesign.

## Risks

- **Pattern-overfit**: regex patterns matchen falsch → wrong agents → bad answer. Mitigation: log mismatches, easy update path.
- **Registry-rot**: capabilities veralten wenn agents removed/renamed. Mitigation: Watcher prüft beim Brain-startup ob alle agents in registry noch in OpenFang existieren.
- **Validator-disagrees-loop**: validator says fail, retry says fail, infinite loop. Mitigation: max_retries=2.
- **Execution-blast-radius**: code_change capability schreibt in Codebase, validator erkennt fail, aber file ist schon geschrieben. Mitigation: alle execution targets müssen idempotent sein oder über coding-engine's branch-isolation laufen.

## Open Questions (need user input)

1. **Capability-Granularität**: 10 grobe Capabilities (`code_change`, `data_query`, `ops_action`) oder 30 feine (`code_review_python`, `code_review_rust`, `bug_diagnosis`, `feature_design`, `refactor`)? Default: starte grob, splitte wenn ein cluster zu breit wird.

2. **Validator immer pflicht?** Code-changes sicher ja, aber für `chitchat` wäre validator overkill. → Make validator optional pro capability.

3. **Wer schreibt die Initial-Capabilities?** Manuell von dir (kennst die domains best) oder Brain analysiert die 49 agent README files und schlägt vor? → Empfehlung: Brain schlägt vor (Phase 1.5 zwischen Phase 1 und 2), du reviewst.

4. **Mirofish-Sim layer noch nötig?** Wenn capability-router 3 agents pickt, gehen die immer noch über Mirofish-interview (mit den schemen-bugs). Direkter OpenFang-call wäre 5x schneller. → Ggf. parallel pfad: für matched capabilities direkter dispatch, für broadcast/idle weiterhin Mirofish.

5. **Wo lebt `capabilities.yaml`?** `vibemind-os/brain/the_brain/data/capabilities.yaml` (mit dem rest von Brain's data) oder `vibemind-os/capabilities.yaml` (top-level, weil cross-cutting)? Default: brain/data weil Brain ist der einzige Konsument.

## Concrete first commit

Wenn approved, scope für commit 1:

- `data/capabilities.yaml` — 5 capabilities (code_review, code_change, incident_response, data_query, chitchat)
- `core/capability_router.py` — class mit regex-only matching
- `core/discourse_engine.py` — `set_capability_router()` + `tick_intent` integration (additiv, broadcast fallback bleibt)
- `web/routers/introspection.py` — `/api/capabilities/stats` endpoint, `/api/capabilities/test` (gib intent → return match)
- `scripts/test_discourse.py` — 2 neue checks: capability_router_loaded, capability_match_returns_subset

No execution, no validation. Phase 1 only. Sichtbar im trace dass intent zu spezifischem capability matched + nur N (nicht 25) agents dispatched. Smoke-test bleibt grün.

Phase 2-5 sind separate commits, jeweils additiv, jeweils mit eigenem plan.md.
