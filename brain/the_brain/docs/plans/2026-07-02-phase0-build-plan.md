# Phase-0 Build-Plan — VibeMind V1 (`C:/Users/User/Desktop/Vibemind_V1/vibemind-os`) — Rev. 2 (Critic-Fixes eingearbeitet)

## 1. Phase-0-Ziel & Abgrenzung

**Ziel:** Vier verifizierte Workstreams zu **einem** strukturellen Fundament zusammenführen, *bevor* irgendein Lernen/Optimierung passiert. Phase 0 baut **keine** neue Fähigkeit — sie beseitigt die vier Klassen von latenten Fehlern, die jedes spätere Lernen vergiften würden:

1. **Routing-Registry-Drift** — fünf uneinige Space-Namen-Maps → eine versionierte `SpaceAgentRegistry` als Single Source of Truth. **Neu in Rev. 2:** Der agentfarm-Agent-Widerspruch (YAML `brain-orchestrator` @`config/space_agent_registry.yml:212` vs. LEGACY-Map `vibemind` @`brain_openfang_bridge.py:48`) wird als eigener Entscheidungs-Task (REG-3) VOR den abgeleiteten Maps aufgelöst — nicht in zwei sich widersprechenden Tests eingefroren.
2. **Fake-Lernsignale** — sechs `success=True`-Sinks feuern auf Nicht-Ausnahme statt Ground-Truth → alles durch **ein** `outcome_gate` (gate-abgeleiteter `contract_pass`). **Neu in Rev. 2:** Auch die **zweite Hälfte** des zweiten Shadow-Loops — die `_brain_event_shadow.observe()`-Label-Posts (`intent_orchestrator.py:955`, `:1244`) — wird auf das Outcome-Gate gelegt (Findings: „gaten, nicht löschen"). Und: MH-5 bekommt seine fehlende Vorbedingung — heute trägt die Multihop-Response **kein** `routing_id` (verifiziert: nur `plan_id` @`brain_multihop_bridge.py:108`), also muss die Brain-Seite (`introspection.py:2425`) es erst durchfädeln, sonst ist der „geschlossene Loop" nur mock-grün.
3. **Nicht-thread-sichere Episode-Ingest** — `KotlinGraph.add_event` läuft lock-frei unter bis zu 4 parallelen `_exec_hop`-Threads → **eine** kritische Sektion inkl. `done=True`-Episode-Close. RED muss **beobachtet** (protokollierter Failing-Run) sein, bevor der Lock landet.
4. **Backer/Distribution-Guardrails** — Zahlungs-/Distributions-Sandbox existiert in V1 **noch nicht** (verifiziert: `backer-checkout` und `distribute.py` fehlen) → **Policy jetzt schreiben**; Enforcement-Tests werden jetzt authored, aber mit explizitem Skip/xfail-Mechanismus, damit die Suite in Phase 0/1 **grün bleibt** und die Fallen in Phase 2 automatisch scharf werden. Alle WS4-Tests liegen unter `tests/policy/` — **kein** `backer-checkout/`-Verzeichnis wird vorab teilinstanziiert.

**Was „done" für Phase 0 heißt:** Alle strukturellen Verträge stehen, sind test-verifiziert (RED→GREEN gegen den heutigen Code; WS4-Enforcement RED-by-absence, per Skip/xfail neutralisiert), und die Gesamt-Suite ist am Ende von Phase 0 **grün**. **Kein** Bandit, **kein** Graduation-Loop, **keine** Optimierung.

**Checkout-Vorbedingung — RESOLVED:** Wir bauen direkt in V1 (`C:/Users/User/Desktop/Vibemind_V1/vibemind-os`), Branch `feat/mcp-tool-hub`. Das CASCADE-Design-Dokument (`brain/the_brain/docs/plans/2026-07-02-cascade-integration-design.md`) und der separate OS-Tree (`C:/Users/User/Desktop/VibeMind-OS/…`) sind **nur Referenz** — alle Pfade unten sind V1-relativ zu `vibemind-os/`. Der im Recon genannte `OutcomeContract` existiert **nicht** als Code (nur im Design-Doc); die reale Gate liegt in `brain/the_brain/core/capability_validator.py` → `world_observer.observe`, per-Hop als `HopResult.validator_verdict` (`plan_executor.py:1511`).

**Zeilennummern-Konvention:** Alle `file:line`-Angaben sind Stand heute und dienen der Orientierung. **Kein Test asserted auf Zeilennummern** — Regression-Guards matchen auf Callsite-Muster (Receiver + Literal), siehe NOFAKE-6.

**Git-Hygiene:** Commits über PowerShell (git-bash crasht, `feedback_git_powershell`); auf `feat/mcp-tool-hub` bleiben, nie `master`.

---

## 2. Geordnete Task-Liste (TDD)

Topologische Gesamt-Reihenfolge über alle 4 Workstreams. Präfixe: **REG-/FIX-/ABSORB-/ASSERT-** Routing-Registry (WS1), **GATE-/REWARD-/OF-/ORCH-/MH-/NOFAKE-** Fake-Signale (WS2), **KG-** KotlinGraph (WS3), **POL-/ENV-/IMPORT-/IDEM-/ENVFILE-/PORT-** Guardrails (WS4).

### Parallelisierbare Gruppen (Wave-Struktur)

| Wave | Tasks (parallel innerhalb der Wave) | Bemerkung |
|---|---|---|
| **A** | `REG-1`, `GATE-1`, `KG-C1`, `POL-0` | 4 unabhängige Wurzeln — je ein Workstream. Keine `depends_on`. |
| **B** | `REG-2`, `REG-3` · `REWARD-2`, `MH-5a` · `KG-C2` (⟵ beobachtetes KG-C1-RED) · `ENV-1`, `IMPORT-2`, `IDEM-3`, `PORT-5` (alle nur ⟵ `POL-0`) | REG-3 = agentfarm-Kanonisierung, MUSS vor Wave D entschieden sein. MH-5a = Brain-seitiges `routing_id`. |
| **C** | `FIX-3`+`ABSORB-8` (**ein Commit**) · `OF-3`, `ORCH-4` (inkl. observe-Gating), `MH-5` · `KG-C3`, `KG-C4` · `ENVFILE-4` | FIX-3/ABSORB-8-Kopplung: Findings-Risiko „Logger im selben PR". |
| **D** | `FIX-4`, `ABSORB-5`, `ABSORB-6`, `ABSORB-7`, `ABSORB-9` (WS1) · `NOFAKE-6` (WS2) | WS1-Edits an `brain_openfang_bridge.py` erst NACH OF-3-Abschluss (siehe Regel unten). |
| **E** | `ASSERT-10` (WS1, letzter Gate-Assert) | |

**Datei-Konflikt-Regel (Korrektur der Rev.-1-Behauptung):** Die vier Workstreams teilen **eine** Datei: `brain_openfang_bridge.py` wird von WS2 (`OF-3`: `:188/:380/:263`) UND WS1 (`FIX-4`: Guard-Logging; `ABSORB-7`: LEGACY-Map-Rewrite; `ASSERT-10`: `__init__`-Assertion) editiert. Alle Edits an dieser Datei sind **cross-workstream serialisiert und haben einen Owner**: `OF-3` (Wave C) → `FIX-4`+`ABSORB-7` (Wave D) → `ASSERT-10` (Wave E). `FIX-4` und `ABSORB-7` haben deshalb ein zusätzliches `depends_on: OF-3`. Alle übrigen Dateien sind workstream-exklusiv → dort gilt volle Parallelität; Wave-Grenzen sonst nur *innerhalb* eines Workstreams.

---

### WAVE A — unabhängige Wurzeln

#### REG-1 — registry_version-Stamp + Accessor (WS1)
- **files:** `voice/python/swarm/routing/space_agent_registry.py`, `config/space_agent_registry.yml`
- **change:** `version`-Property → `self._data.get('version', 0)`; `registry_version`-Alias. In `load()` den `version!=1`-Warn behalten (heute `:62-64`) UND Version speichern; Log-Zeile `:66` erweitern zu `Loaded N spaces (registry_version=V)`. YAML behält `version: 1` (bereits `:10`).
- **RED (`test_registry_version_stamp`, `tests/test_space_agent_registry.py`):** `AttributeError` — heute existiert nur `mode/lookup/fallback/legacy_agent/all_spaces/space_meta/defaults` (`space_agent_registry.py:41-140`), keine `version`.
- **GREEN:** `reg.load().version == 1`.

#### GATE-1 — Shared `outcome_gate`-Helper (WS2)
- **files:** `voice/python/swarm/routing/outcome_gate.py` *(neu — verifiziert abwesend)*, `voice/python/tests/test_outcome_gate.py`
- **change:** Reine Funktionen ohne I/O, keine `brain`-Imports (läuft im Voice-venv): `contract_pass_from_verdict(verdict, ok) -> Optional[bool]` → `True` nur wenn `ok and verdict.get('verified') is True`; `False` wenn `ok is False` oder `verified is False`; `None` (⇒ Caller belohnt NICHT) wenn `verdict is None` oder `verified is None`. `contract_pass_from_executed(executed)` ANDet per-Hop `{ok, validator_verdict}` — Semantik gespiegelt aus `contract_gate.py:84-90`.
- **RED (`test_outcome_gate_semantics`):** Modul fehlt → `ImportError`, Test kann nicht mal collecten.
- **GREEN:** `({'verified':True},True)→True`, `({'verified':False},True)→False`, `({'verified':None},True)→None`, `(None,True)→None`, `({'verified':True},False)→False`; `contract_pass_from_executed({'hop_0':{'ok':True,'validator_verdict':{'verified':True}}})→True`; Hop `{}` → nicht-`True`.

#### KG-C1 — RED: Concurrency-Test beweist add_event-Race (WS3)
- **files:** `brain/the_brain/tests/test_kotlin_graph.py`
- **change:** Neue Klasse `TestKotlinGraphConcurrency`, Test `test_parallel_add_event_one_done_consistent`: ein geteilter `KotlinGraph`, `ThreadPoolExecutor(max_workers=8)`, N=200 `add_event` mit distinkten `make_state`; genau **ein** `done=True`; `threading.Barrier` für gleichzeitigen Start; Szenario ~20× loopen. Asserts: `stats['total_events']==N`, `len(events)==N`, `len({e.event_id})==N`, `stats['total_episodes']==1`, `current_episode_id==1`, `sum(len(v) for episodes.values())==N`, `stats['total_transitions']==N`.
- **RED:** Gegen lock-freies `add_event` (`kotlin_graph.py:100-213`): `event_id=len(self.events)` (`:131`) dann `append` (`:149`) → doppelte/verlorene IDs; `done`-Block (`:208-210`) nicht atomar. **Da das RED probabilistisch (race-basiert) ist, gilt es erst als erbracht, wenn ein Failing-Run tatsächlich BEOBACHTET und protokolliert wurde** (Pytest-Output im Commit-/PR-Text festhalten). KG-C2 startet erst danach — sonst wäre „grün nach Lock" nicht beweiskräftig.
- **GREEN:** nach KG-C2 alle Invarianten auf jeder Iteration.

#### POL-0 — [PHASE-0 POLICY] Guardrail-Policy-Doc (WS4)
- **files:** `docs/policy/backer-sandbox-guardrails.md` *(neu)*
- **change:** Kanonische Policy, die alle Folgetasks referenzieren. Enumeriert 5 Guardrails mit den zitierten OS-Anti-Pattern als Negativbeispiele: (a) fail-closed `PAYPAL_ENV` (kein Soft-Default; validiert Boot+Hop+pre-POST) — zitiert OS `app.py:44`; (b) Live-Transport-Import-Ban auf Sandbox-Distributionspfad, Payment nur in quarantäniertem `backer-checkout/` — zitiert OS `paypal_client.py:21-24`; (c) Idempotency+Ledger+Cap — zitiert fehlender `PayPal-Request-Id` in `create_order`; (d) deterministische Env — zitiert OS `app.py:29-33` (find_dotenv-Walk-up + `x-pathfinder/.env`-Fallback); (e) Port-Policy — zitiert `brain_shadow.py:31` vs OS `app.py:95`. Jeder Downstream-Task als **Phase-0 POLICY** oder **Phase-2 ENFORCEMENT** markiert; `MAX_ORDERS_PER_RUN`-Default als Policy-Entscheidung fixiert. **Neu:** Die Policy definiert auch den **Test-Aktivierungs-Mechanismus** (siehe WS4 Wave B): Skip-if-absent für Enforcement, `xfail(strict=True)` für den Discovery-Assert. Alle zitierten OS-Zeilen sind Referenz — der Code existiert in V1 nicht.
- **RED (`test_guardrail_policy_present`, `tests/policy/test_guardrail_policy_present.py`):** Doc fehlt → Test auf Existenz + 5 Anker (`paypal_env_fail_closed`, `live_transport_import_ban`, `idempotency_ledger_caps`, `deterministic_env_file`, `port_collision`) + Anker `test_activation_mechanism` ERRORt.
- **GREEN:** Doc existiert, alle 6 Anker vorhanden.

---

### WAVE B

#### REG-2 — `canonical_spaces()` als Namens-Autorität (WS1) ⟵ REG-1
- **files:** `space_agent_registry.py`
- **change:** `canonical_spaces() -> set[str]` = `set(self._spaces.keys())`; `space_exists(space) -> bool`.
- **RED (`test_canonical_spaces_matches_yaml_keys`):** Methode fehlt → `AttributeError`.
- **GREEN:** `== {'bubbles','ideas','coding','desktop','research','roarboot','minibook','schedule','n8n','agentfarm','video','flowzen','mirofish'}`; `'roarboot' in it and 'rowboat' not in it`.

#### REG-3 — agentfarm-Agent-Kanonisierung (WS1) ⟵ REG-1 **[NEU — löst FIX-4↔ABSORB-7-Widerspruch]**
- **files:** `config/space_agent_registry.yml`, ggf. `docs/policy/` (Entscheidungs-Notiz im PR)
- **problem:** YAML sagt `agentfarm.agent: brain-orchestrator` (`:212`, verifiziert), LEGACY-Map sagt `vibemind` (`brain_openfang_bridge.py:48`, verifiziert). Rev. 1 hätte beide Werte in zwei Tests derselben Datei (`tests/test_flowzen_brain_bridge.py`) eingefroren → nach Wave D wäre einer permanent rot.
- **change (Entscheidungsprozedur):** (1) Bei laufendem Stack `GET :4200/api/agents` (OpenFang = SoT für deployte Agenten; bei Plan-Erstellung war :4200 down — muss im Task-Lauf erfolgen). (2) Existiert `brain-orchestrator` als deployter, funktionsfähiger Agent → YAML bleibt, `brain-orchestrator` ist kanonisch. (3) Sonst → YAML auf `agent: vibemind` ändern (der heute dispatchende Wert). (4) Entscheid + Beleg (Agent-Liste) im Commit dokumentieren. **In beiden Fällen gilt ab hier: die Registry ist die einzige Wahrheit; kein Test hardcodet den agentfarm-Agenten** (FIX-4 und ABSORB-7 lesen den Erwartungswert aus `SpaceAgentRegistry.load()`).
- **RED (`test_agentfarm_agent_consistent`, `tests/test_space_agent_registry.py`):** `SpaceAgentRegistry.load().lookup('agentfarm', 'agentfarm.run').agent != LEGACY_SPACE_AGENT_MAP['agentfarm']` — heute `brain-orchestrator != vibemind` → failt (beweist die Drift, unabhängig davon, wie entschieden wird).
- **GREEN:** Registry-Wert == Bridge-Wert (nach REG-3-Entscheid sofort via YAML-Edit, spätestens strukturell nach ABSORB-7).

#### REWARD-2 — None-Signal = No-op statt erzwungenem Train (WS2) ⟵ GATE-1
- **files:** `brain_event_shadow.py`, `brain_shadow.py`, `tests/test_shadow_reward_gating.py`
- **change:** `reward(self, routing_id, success: Optional[bool])` in `brain_event_shadow.py:183` → `success is None` returnt früh OHNE POST an `/api/cortex/classify/reward`. `brain_shadow.py:43` `observe()` → `success: Optional[bool]`; **bei `None` KEIN POST an `/api/cortex/route/train`** — Accuracy-Sample nur lokal zählen (Counter/Log), nicht senden. *(Änderung ggü. Rev. 1: Rev. 1 hätte `None`→`success:false` gePOSTet — das wäre ein aktives NEGATIV-Label und hätte nach ORCH-4 jeden verdictlosen Tier1-4-Hop — den Normalfall — als „Routing war falsch" in den SpaceRoutingHead trainiert, auch bei korrektem Routing. Jetzt symmetrisch zum reward-No-op; Tradeoff in Sektion 6.)* POST-Shapes für `True`/`False` sonst identisch.
- **RED (`test_reward_none_is_noop`):** Heute kein None-Branch; `reward(rid, None)` POSTet `success:None`. Monkeypatched aiohttp-Session zeichnet POST auf → assert-no-POST failt. Zusätzlich `test_observe_none_is_noop`: `observe(...,None)` POSTet heute → failt.
- **GREEN:** `reward(rid, None)` = 0 POSTs; `observe(...,None)` = 0 POSTs (lokaler Zähler inkrementiert); `True`→`success:true`; `False`→`success:false`.

#### MH-5a — Brain-Seite: `routing_id` durch `/api/multihop/execute` fädeln (WS2/Brain) ⟵ GATE-1 **[NEU — Vorbedingung für MH-5]**
- **files:** `brain/the_brain/web/routers/introspection.py` (Endpoint `:2425`), zugehöriger Response-Builder, `brain/the_brain/tests/test_multihop_response_contract.py` *(neu)*
- **problem (verifiziert):** Die Multihop-Response trägt heute **kein** `routing_id` — `brain_multihop_bridge.py` kennt nur `data.get('plan_id')` (`:108`, als Log-String). Ein „fire-and-forget Reward bei vorhandenem routing_id" würde in Produktion **nie** feuern; MH-5 wäre nur gegen einen fabrizierten Mock grün.
- **change:** Response-Envelope von `/api/multihop/execute` um `routing_id` erweitern (die ID, die der Reward-Endpoint `/api/cortex/*/reward` akzeptiert; falls dort `plan_id` das kanonische Korrelat ist, stattdessen den Reward-Endpoint-Vertrag dokumentieren und `plan_id` als Reward-Key festschreiben — Entscheid im Task, gegen den echten Reward-Endpoint-Code verifiziert, nicht geraten).
- **RED (`test_multihop_response_carries_routing_id`):** Test gegen den echten Response-Builder (bzw. TestClient auf den Router): Response-JSON enthält heute kein `routing_id` → failt.
- **GREEN:** Jede erfolgreiche `/api/multihop/execute`-Response enthält ein non-empty `routing_id`, das der Reward-Endpoint akzeptiert (Shape-Assert gegen echten Serializer, kein Mock-Payload).

#### KG-C2 — GREEN: `self._lock` (RLock) um volle add_event-Mutation (WS3) ⟵ KG-C1 (**beobachtetes** RED)
- **files:** `brain/the_brain/core/kotlin_graph.py`
- **change:** Modul-Top `import threading`; `self._lock = threading.RLock()` als **erste** Zeile von `__init__` (`:78`, vor `self.graph`). Body von `add_event` (`:131-213`) in `with self._lock:` — ID-Allokation, `events.append`, `state_index`/`next_node_id`/`graph.add_node`/`add_edge`, `visit_count`, Episode-Membership (`:203-205`) UND `done=True`-Block (`:208-210`) plus `total_events++` (`:212`) als **eine** kritische Sektion. `clear()` (Test `:568`) ebenfalls `with self._lock:`. **Kein I/O in der Sektion** — `save/load` bleiben explizit außerhalb. RLock (re-entrant) wie `plan_executor.py:71/:228`.
- **RED/GREEN:** siehe KG-C1; zusätzlich muss die **gesamte bestehende 668-Zeilen-Suite** grün bleiben (verhaltenserhaltend für serielle Caller).

#### WS4 Wave-B (alle ⟵ POL-0, unabhängig voneinander) — **alle Tests unter `tests/policy/`, NICHT `backer-checkout/tests/`**

**Test-Aktivierungs-Mechanismus (gilt für alle vier Enforcement-Tests + IMPORT-2; behebt den Suite-rot-Widerspruch):**
- `ENV-1`/`IDEM-3`/`ENVFILE-4`/`PORT-5`: Modul-Guard am Testkopf — `pytest.mark.skipif(not (REPO_ROOT / 'backer-checkout').exists(), reason='Phase-2 ENFORCEMENT — backer-checkout absent (POL-0)')`. Solange die Sandbox fehlt → **SKIP** (Suite grün); sobald Phase 2 das Verzeichnis anlegt, laufen die Tests automatisch und müssen bestehen. **Ehrliche Einordnung:** Diese Tests sind heute *red-by-absence*, nicht red-gegen-Verhalten — sie sind vorinstallierte Fallen, keine Bug-Beweise. Insbesondere ENVFILE-4s Anti-Pattern (`x-pathfinder/.env`-Sibling) ist in V1 nicht exerzierbar; wird Phase-2-Code korrekt geschrieben, flippt der Test grün, ohne den Fang je demonstriert zu haben. Das ist akzeptiert und in POL-0 so dokumentiert.
- `IMPORT-2` (Discovery-Assert): `pytest.mark.xfail(strict=True, reason='Phase-2 — distribute.py absent; XPASS erzwingt Marker-Entfernung')` — solange `distribute.py` fehlt, failt der Assert → XFAIL (Suite grün); landet `distribute.py` und der Scan besteht, wird der Test XPASS → `strict=True` macht daraus einen lauten Fehler → Marker wird entfernt, Test wird permanenter Gate.

**ENV-1 — [PHASE-2 ENFORCEMENT] fail-closed PAYPAL_ENV**
- **files:** `tests/policy/test_env_guard.py` *(jetzt, mit skipif)*; Phase-2: `backer-checkout/app.py`, `backer-checkout/paypal_client.py`, `backer-checkout/env_guard.py`
- **change:** `ENV = os.environ.get("PAYPAL_ENV","sandbox")` (OS `app.py:44`) ersetzt durch `require_paypal_env()` in `env_guard.py`: liest `PAYPAL_ENV` **ohne Default**, `raise PayPalEnvError` bei leer/fehlt/∉{sandbox,live}. Aufruf (1) Boot, (2) je Hop, (3) unmittelbar vor `requests.post` in `create_order/capture_order`. Kein Pfad erreicht `_BASE_URLS['live']` ohne validiertes `PAYPAL_ENV=live`.
- **RED-by-absence:** `backer-checkout` fehlt → SKIP heute; nach Phase-2-Scaffold ohne Guard → `PayPalEnvError`-Erwartung failt.
- **GREEN:** unset/''/'prod' → `PayPalEnvError` Boot+Hop+pre-POST; monkeypatched `requests.post` **nicht** aufgerufen bei invalid.

**IMPORT-2 — [PHASE-0 authored / PHASE-2 target] Live-Transport-Import-Ban**
- **files:** `tests/policy/test_no_live_transport_in_sandbox.py` *(jetzt authored, xfail strict)*, `docs/policy/backer-sandbox-guardrails.md`
- **change:** CI-Test scannt zukünftigen Distributionspfad (`spaces/**/distribute.py` + Sandbox/Registry/Search-Tree) AST-basiert (nicht naiv-substring) auf `{requests, smtplib, http, socket, paypal}` + Raw-Grep als Gürtel-und-Hosenträger. Assert Match-Menge **leer**; `backer-checkout/` per Allowlist ausgenommen.
- **RED:** `distribute.py` existiert nicht → Discovery-Assert failt (→ XFAIL, Suite grün); ODER Phase-2-Autor kopiert `import requests/paypal` → Token-Scan failt (nach Marker-Entfernung: harter Fail).
- **GREEN:** Phase-2-`distribute.py` + Tree existieren UND enthalten keines der Tokens → Scan leer → XPASS → Marker raus.

**IDEM-3 — [PHASE-2 ENFORCEMENT] PayPal-Request-Id + Ledger UNIQUE + MAX_ORDERS_PER_RUN**
- **files:** `tests/policy/test_idempotency_ledger.py` *(jetzt, mit skipif)*; Phase-2: `backer-checkout/paypal_client.py`, `backer-checkout/ledger.py`, `backer-checkout/app.py`
- **change:** `create_order` (OS `paypal_client.py:76-97`) bekommt `PayPal-Request-Id` aus deterministischem Idempotency-Key (`hash(run_id+backer+amount)`). `ledger.py` mit `UNIQUE(order_id)` (+ unique auf Idempotency-Key). `MAX_ORDERS_PER_RUN` (env, kleiner Default per POL-0) in `app.create_order` vor PayPal-Call; Überschreitung → 429, kein Order. `capture_order` schreibt Ledger keyed by `order_id`.
- **RED-by-absence / GREEN:** stabiler `PayPal-Request-Id` über Retries; Duplikat-`order_id` → `IntegrityError`; Order N+1 → 429 ohne PayPal-Call.

**PORT-5 — [PHASE-2 ENFORCEMENT] Port-5000-Kollision + Boot-Assertion**
- **files:** `tests/policy/test_port_collision.py` *(jetzt, mit skipif)*; Phase-2: `backer-checkout/app.py`, `backer-checkout/.env.example`
- **change:** Payment-Flask-Default weg von 5000 (OS `app.py:95`, `.env.example:16`) → z. B. 5055. Boot-Assertion `payment(host,port) != brain(host,port)`; Brain-Host:Port aus **derselben** Config-Quelle wie der Orchestrator (nicht hardcodet — `brain_shadow.py:31` ist in V1 heute `http://localhost:5000`). Match → `PortCollisionError`.
- **RED-by-absence / GREEN:** Default off 5000; `PORT=5000` auf gleichem Host → `PortCollisionError` beim Boot.

---

### WAVE C

#### FIX-3 — roarboot/rowboat + agentfarm/autogen Dispatch-Bug fixen (WS1) ⟵ REG-2 — **im selben Commit wie ABSORB-8**
- **files:** `bindings_registry.py`
- **change:** Jeder `SpaceBinding`-Space `'rowboat'→'roarboot'`, `'autogen'→'agentfarm'` (matcht Brain `SPACE_NAMES` + YAML). Konkret: `KEYWORD_BINDINGS:24` `'autogen'→'agentfarm'`; `agent_registry:56` `('roarboot',('rowboat',…))→('roarboot',('roarboot',…))` und `:62` `('agentfarm',('autogen',…))→('agentfarm',('agentfarm',…))`; `_get_static_fallback:116` `'rowboat'→'roarboot'`, `:122` `'autogen'→'agentfarm'`.
- **Commit-Kopplung (Findings-Risiko):** FIX-3 und ABSORB-8 landen in **einem Commit/PR** — sonst emittiert Dispatch zwischen den Waves kanonische Namen, während der Logger noch `rowboat` mappt, d. h. genau die transiente Inkonsistenz, vor der die Findings warnen, würde institutionalisiert.
- **RED (`test_binding_spaces_are_canonical`, `tests/test_bindings_registry.py`):** heute `match_keyword('starte agent farm pipeline').space=='autogen'` und `build_prefix_bindings()['roarboot.'].space=='rowboat'` — beide **kein** Key in `LEGACY_SPACE_AGENT_MAP`/YAML → Bridge mappt auf `None`.
- **GREEN:** `…=='agentfarm'` bzw. `'roarboot'`; alle `binding.space ∈ canonical_spaces()`.

#### ABSORB-8 — space_logger vollständig kanonisieren (WS1) ⟵ REG-2 — **im selben Commit wie FIX-3** *(aus Wave D vorgezogen, Umfang erweitert)*
- **files:** `voice/python/swarm/logging/space_logger.py`
- **change:** **ALLE** `'rowboat'`-Vorkommen re-keyen (Rev. 1 hatte nur 2 von 5): `MODULE_TO_SPACE['spaces.rowboat']` Value `'rowboat'→'roarboot'` (`:71`); `MODULE_TO_SPACE['publishing']` Value `'rowboat'→'roarboot'` (`:88` — von Rev. 1 übersehen); `MODULE_TO_SPACE['spaces.autogen']` Value → `'agentfarm'` (`:75`); **SpaceColors-Dict-Key** `'rowboat'→'roarboot'` (`:107` — sonst verliert der kanonische Space still seine Farbe); **Badge-Dict-Key** `'rowboat'→'roarboot'`, Badge-Text `'[ROWBOAT]'→'[ROARBOOT]'` (`:123` — sonst still ohne Badge). Boot-Check: jeder Space-VALUE in `MODULE_TO_SPACE` (außer Infra-Pseudo `voice/brain/orchestrator`) ∈ `canonical_spaces()` **UND** jeder Nicht-Infra-Key des Color-Dicts und des Badge-Dicts ∈ `canonical_spaces()` — damit ist das WS1-target_state-Versprechen „space→logger-color aus Registry validiert" tatsächlich geliefert.
- **RED (`test_space_logger_fully_canonical`, `tests/test_space_logger.py`):** `MODULE_TO_SPACE['spaces.rowboat']=='rowboat'` ∉ canonical; Color-Dict hat Key `'rowboat'`, keinen Key `'roarboot'`; Badge-Dict ebenso → drei Asserts failen.
- **GREEN:** jeder Nicht-Infra-Value in `MODULE_TO_SPACE` ∈ `canonical_spaces()`; Color- und Badge-Dict decken jeden kanonischen Space ab, kein `'rowboat'`/`'autogen'`-Key mehr.

#### OF-3 — Fake `success=True` in brain_openfang_bridge (SINKS #5,#6) (WS2) ⟵ REWARD-2 — **erster Edit der geteilten Datei; muss vor FIX-4/ABSORB-7 abgeschlossen sein**
- **files:** `brain_openfang_bridge.py`, `tests/test_openfang_bridge_reward.py`
- **change:** `:188` und `:380` kein `_reward_brain(routing_id, success=True)` mehr; `_send_to_openfang` liefert nur Freitext ohne Verdict → **kein** positives Reward: `_reward_brain(routing_id, success=None)` (no-op nach REWARD-2). `:217`/`:397` `success=False` behalten. `_reward_brain(self, routing_id, success: Optional[bool])` (`:263`) skippt POST bei `None`.
- **RED (`test_bridge_no_fake_positive_reward`):** `_send_to_openfang` monkeypatched → `execute()`/`_background_execute` POSTet `success:true` ohne Ground-Truth → assertion failt.
- **GREEN:** non-verified Response → **null** positive-Reward-POST; Exception-Pfad → `success:false`.

#### ORCH-4 — 4 Fake-Sinks + observe()-Gating in intent_orchestrator (SINKS #1-#4 + Label-Loop) (WS2) ⟵ GATE-1, REWARD-2
- **files:** `intent_orchestrator.py`, `tests/test_orchestrator_reward_gating.py`
- **change (Teil 1 — reward-Sinks):** Die vier Fake-Sinks (heute bei `:971`, `:1181`, `:1340`, `:1348` — Callsite-Muster maßgeblich, nicht Zeilen): kein `success=True`. Je `sig = outcome_gate.contract_pass_from_verdict(verdict, ok)` — `verdict/ok` aus echtem Ergebnis, sonst `sig=None`. Tier1-4-Tool-Pfad: `None`/leeres-Dict/Error-Key → `ok=False`; sonst kein Verdict → `sig=None`. `success=False`-Calls (`:822`, `:980`, `:1368`) **unverändert**.
- **change (Teil 2 — observe()-Label-Gating, von Rev. 1 übersehen):** Die beiden `_brain_event_shadow.observe()`-Calls (`:955`, `:1244` — verifiziert) POSTen heute das LLM-Event-Label **bedingungslos** an `/api/cortex/classify/train`, auch wenn die nachgelagerte Execution failt. Findings: „gaten, nicht löschen". Fix: Label-POST wird hinter dieselbe Gate-Auswertung verschoben — **gefeuert nur bei `sig is True`** (deferred bis das Hop-Outcome vorliegt); bei `sig is False` **skip** (nicht auf einem gescheiterten Pfad trainieren); bei `sig is None` **skip** (konservativ — Policy-Entscheid, Tradeoff in Sektion 6). Lokaler Zähler für geskippte Labels (Observability).
- **RED (`test_empty_hop_does_not_train_success`):** Tier1-4 mit Tool-Stub `{}` → heute `observe(success=True)+reward(success=True)`. Spy → assert failt. **Zusätzlich `test_event_label_not_posted_on_failed_execution`:** Stub-Execution mit `ok=False` → heute wird das `classify/train`-Label trotzdem gePOSTet → failt.
- **GREEN:** Hop `{}` → **kein** positives Reward; populated-ohne-Verdict → kein positives Reward; nur Verdict `verified=True` → `reward(success=True)`; Event-Label-POST nur bei `sig is True`, 0 Label-POSTs bei `False`/`None`.

#### MH-5 — Multihop-Bridge speist echten per-Hop-Verdict als Reward zurück (WS2) ⟵ GATE-1, **MH-5a**
- **files:** `brain_multihop_bridge.py`, `tests/test_multihop_reward_gating.py`
- **change:** In `execute()` nach Match (`:116`): `sig = outcome_gate.contract_pass_from_executed(data.get('executed') or {})`; Reward fire-and-forget mit dem von **MH-5a** gelieferten `routing_id` (skip bei `sig is None` oder fehlender ID). Kein `True` bei leerem `executed`.
- **RED (`test_multihop_rewards_only_on_verified`):** heute `data['executed']` nur für Voice-Summary (`:99/:182`), nie Reward → assert failt. **Test-Payload-Regel:** Der Test-Fixture-Payload MUSS dem echten MH-5a-Response-Schema entsprechen (Shape aus `test_multihop_response_carries_routing_id` referenziert/geteilt) — kein frei erfundenes Mock-Feld; ein Companion-Assert prüft, dass der im Test verwendete Key exakt der von MH-5a gelieferte ist.
- **GREEN:** alle Hops ok+`verified=True` → ein `reward(success=True)` an die echte ID; ein Hop `verified=False` → `reward(success=False)`; leer/`None`/keine ID → kein positives Reward.

#### KG-C3 — done=True 3-Bedingungs-Regel dokumentieren + `is_episode_done` (WS3) ⟵ KG-C2
- **files:** `brain/the_brain/core/kotlin_graph.py`
- **change:** `add_event`-Docstring (`:113-130`) spezifiziert Caller-Contract für `done`: Episode-Close nur wenn ALLE drei — (1) letzter Hop im Plan, (2) Truth-Validator PASSED falls Validator präsent (`verdict.get('verified') is True`; kein Validator = vacuously satisfied; Mapping wie `plan_executor.py:1380-1382`), (3) **null** pending Hops. Pure `@staticmethod is_episode_done(is_last_hop, validator_present, validator_passed: Optional[bool], pending_hops) -> bool`. Zentralisiert die Regel für den (noch nicht gebauten) `multihop_kotlin_adapter`; ändert **nicht** `add_event`-Control-Flow.
- **RED (`test_is_episode_done_three_condition_rule`):** Methode fehlt → `AttributeError`.
- **GREEN:** Table-driven: last+no-validator+0 → True; last+passed+0 → True; last+False+0 → False; last+None+0 → False; last+passed+pending>0 → False; not-last → False.

#### KG-C4 — DualGraph.record_event erbt Thread-Safety ohne DualGraph-Änderung (WS3) ⟵ KG-C2
- **files:** `brain/the_brain/tests/test_dual_graph.py`
- **change:** Concurrency-Regression: N parallele `record_event` (ein `done=True`) via `ThreadPoolExecutor`; assert `dg.kotlingraph.stats['total_episodes']==1`, `['total_events']==N`, `dg.stats['total_events_recorded']==N`. Falls `total_events_recorded` (`dual_graph.py:112`, lock-freies `+=`) unter Contention unterzählt → **Notiz** als Follow-up (nicht still ausweiten); Primär-Assert = KotlinGraph-Counter konsistent rein aus KG-C2.
- **RED:** gegen pre-KG-C2 divergieren die durch DualGraph erreichten KotlinGraph-Counter.
- **GREEN:** nach KG-C2 konsistent; dokumentiert ob `total_events_recorded` Follow-up braucht.

#### ENVFILE-4 — [PHASE-2 ENFORCEMENT] deterministische BACKER_ENV_FILE-Auflösung (WS4) ⟵ POL-0, ENV-1
- **files:** `tests/policy/test_env_file_resolution.py` *(jetzt, mit skipif)*; Phase-2: `backer-checkout/app.py`, `backer-checkout/env_guard.py`
- **change:** OS-4-Wege-Kette (`app.py:29-33`) ersetzt durch Single-Loader: `BACKER_ENV_FILE` **muss** explizit gesetzt sein; nur diese Datei laden. `find_dotenv(usecwd=True)` ENTFERNT, `x-pathfinder/.env`-Fallback ENTFERNT. Unset/fehlend → fail-closed.
- **RED-by-absence:** SKIP heute (Sandbox fehlt); das Sibling-Anti-Pattern ist in V1 nicht exerzierbar (ehrlich als Falle, nicht als Bug-Beweis geführt — siehe POL-0).
- **GREEN:** nur explizite Datei lädt; unset → Raise; Source-Assert `'x-pathfinder'`/`'find_dotenv'` nicht im Env-Block von `app.py`.

---

### WAVE D

#### FIX-4 — Dispatch-Regression: Bridge löst roarboot + agentfarm E2E auf (WS1) ⟵ FIX-3, **REG-3**, **OF-3** (geteilte Datei)
- **files:** `brain_openfang_bridge.py`, `tests/test_flowzen_brain_bridge.py`
- **change:** Keine Logik-Änderung nötig nach FIX-3; Guard: in `execute()` bei `agent_name is None` divergente Space-Menge loggen. Primär: Regressions-Test.
- **RED (`test_dispatch_roarboot_and_agentfarm_resolve`):** HybridRouter tier-1 `roarboot.` (space=`rowboat` heute) / tier-2 `agent farm` (space=`autogen`) → `space_to_agent(space)` = `None` (kein Key in `LEGACY_SPACE_AGENT_MAP`).
- **GREEN (registry-derived, KEIN hardcodeter Agent — behebt den Rev.-1-Widerspruch zu ABSORB-7):** `space_to_agent('roarboot') == SpaceAgentRegistry.load().space_meta('roarboot')['agent']` (== `'rowboat-knowledge'`, YAML `:149`); `space_to_agent('agentfarm') == SpaceAgentRegistry.load().space_meta('agentfarm')['agent']` (Wert per REG-3 entschieden); beide `is not None`. `registry.lookup('roarboot','roarboot.search').agent=='rowboat-knowledge'`.

#### ABSORB-5 — Prefix-Bindings aus Registry ableiten (WS1) ⟵ FIX-3, REG-2
- **files:** `bindings_registry.py`, `config/space_agent_registry.yml`
- **change:** Per-Space `prefixes:` in YAML (roarboot:[roarboot.]; ideas:[idea.]; bubbles:[bubble.]; desktop:[desktop.,web.,messaging.,openclaw.]; …). `build_prefix_bindings()` konstruiert `SpaceBinding` aus `SpaceAgentRegistry.load()` (space, agent aus `sp['agent']`, stream `events:tasks:<space>`) statt hardcodetem `_get_static_fallback`+`agent_registry`. `_get_static_fallback` nur noch Emergency-Fallback bei fehlender YAML.
- **RED (`test_prefix_bindings_sourced_from_registry`):** heute unabhängig von YAML (18 Einträge hardcodet).
- **GREEN:** neuer Prefix in Temp-YAML wird aufgenommen; Default-Bindings agree mit `canonical_spaces()`.

#### ABSORB-6 — Keyword-Bindings aus Registry ableiten (WS1) ⟵ FIX-3, REG-2
- **files:** `bindings_registry.py`, `config/space_agent_registry.yml`
- **change:** Optionale Per-Space `keywords:`-Regex-Liste in YAML (desktop, n8n, schedule, agentfarm). `KEYWORD_BINDINGS/_compile_keywords/match_keyword` aus Registry-Keywords bauen; Fallback auf 4-Einträge-Dict nur wenn YAML keine Keywords hat.
- **RED (`test_keyword_bindings_sourced_from_registry`):** YAML-Keyword wird heute nicht gematcht (Modul-Level 4-Einträge-Dict).
- **GREEN:** YAML-Keyword → passender Space; agentfarm-Keyword → `'agentfarm'`.

#### ABSORB-7 — LEGACY_SPACE_AGENT_MAP aus Registry ableiten (WS1) ⟵ REG-2, FIX-3, **REG-3**, **OF-3** (geteilte Datei)
- **files:** `brain_openfang_bridge.py`
- **change:** Hardcodetes `LEGACY_SPACE_AGENT_MAP`-Dict (`:39-53`) → `{s: meta.get('agent') for s,meta in SpaceAgentRegistry.load().all_spaces().items()}` bei Import (kleiner Static-Fallback bei fehlender YAML). `SPACE_AGENT_MAP`-Alias behalten. **Achtung geteilte Datei:** landet nach OF-3; der Map-Rewrite verschiebt Zeilennummern — OF-3s Tests matchen deshalb auf Callsites, nicht Zeilen.
- **RED (`test_legacy_map_derived_from_registry`):** Literal-Dict kann driften — vor REG-3: YAML `agentfarm==brain-orchestrator` vs. `legacy['agentfarm']=='vibemind'` (verifizierter Ist-Widerspruch).
- **GREEN:** `set(keys)==canonical_spaces()`, jeder Wert == YAML-Agent. **Konsistent mit FIX-4**, weil beide gegen die Registry asserten (kein hardcodeter agentfarm-Agent mehr in irgendeinem Test).

#### ABSORB-9 — aspirationale minibook-Router in Registry falten / tote Refs löschen (WS1) ⟵ REG-2
- **files:** `voice/python/ipc/voice_manager.py`, `voice/python/tests/test_flowzen_integration.py`
- **change:** Minibook-Router (`SPACE_AGENT_REGISTRY` in `spaces.minibook.tools.collaboration_tools`; `EVENT_TYPE_TO_SPACE` in `spaces.minibook.enrichment.space_router`) existieren **nicht** als Source in V1 (verifiziert). Runtime-Consumer `voice_manager.py:379-381` iteriert `SpaceAgentRegistry.load().all_spaces()` (`register_agent(meta['agent'], space)`) statt Missing-Import. `test_flowzen_integration.py:86-87` asserted gegen Registry (`lookup` für `rose.*` → space `'flowzen'`) statt Import des nicht-existenten `EVENT_TYPE_TO_SPACE`. **Keine** Wiederauferstehung der Abhängigkeit zu `spaces.minibook` (registry-only).
- **RED (`test_no_minibook_router_imports`):** `from spaces.minibook.enrichment.space_router import EVENT_TYPE_TO_SPACE` → `ModuleNotFoundError`.
- **GREEN:** kein Import aus `spaces.minibook`; assert `SpaceAgentRegistry.load().lookup('flowzen','rose.recommend').agent=='brain-wellness'` (oder Space-Membership).

#### NOFAKE-6 — Regressions-Guard: kein hardcodetes success=True erreicht Shadow-Sink (WS2) ⟵ ORCH-4, OF-3, MH-5
- **files:** `voice/python/tests/test_no_fake_shadow_success.py` *(Pfad-Fix ggü. Rev. 1: V1-relativ, kein `vibemind-os/`-Doppelpräfix)*
- **change:** Source-Scan über `voice/python/swarm`; für jede `.reward(`/`.observe(`-Callsite auf `_brain_shadow`/`_brain_event_shadow`/`_reward_brain` assert das Statement enthält **kein** Literal `success=True`. **Matching explizit auf Callsite-Muster (Receiver-Name + `success=True`-Literal), NIE auf Zeilennummern** — die Sinks wandern durch ABSORB-7/ORCH-4-Edits. **Whitelist** der legitimen Non-Learning-`success=True` (base_agent `record_agent_execution`, tool_orchestrator `ToolResult`, base_space_agent `SpaceToolResult`, sync_executor tool_logger/results, monitoring `complete_operation`). Fail mit `file:line` des Treffers.
- **RED (`test_no_hardcoded_success_true_in_shadow_sinks`):** heute 6 Treffer — `intent_orchestrator.py` bei `:971/:1181/:1340/:1348` und `brain_openfang_bridge.py` bei `:188/:380` (verifizierte Ist-Zeilen; der Test selbst zählt Muster, nicht Zeilen).
- **GREEN:** 0 Shadow-Sinks mit `success=True`; Whitelist-Zeilen ignoriert.

---

### WAVE E

#### ASSERT-10 — Boot-Consistency-Assertion über Brain SPACE_NAMES / YAML / Bindings (WS1) ⟵ REG-2, FIX-3, ABSORB-5, ABSORB-6, **ABSORB-7** (geteilte Datei, letzter Edit)
- **files:** `space_agent_registry.py`, `brain_openfang_bridge.py`
- **change:** `SpaceAgentRegistry.assert_consistent(brain_space_names: set[str], binding_spaces: set[str])` → `RegistryConsistencyError` wenn `canonical_spaces() != brain_space_names` oder ein `binding_space ∉ canonical_spaces()`. Einmal in `BrainOpenFangBridge.__init__` (nach Registry-Load) mit importierten Brain-`SPACE_NAMES` + Set aus `build_prefix_bindings`/`match_keyword`-Spaces; `registry_version` loggen. Fail-fast bei Boot statt still `None` bei Dispatch. **Feature-Flag** (warn vs raise) für ersten Rollout.
- **RED (`test_boot_consistency_assertion`):** `assert_consistent` fehlt; Registry ohne `'agentfarm'` bei Brain-emit → heute kein Fehler.
- **GREEN:** passt für aligned Sets; raist `RegistryConsistencyError` wenn Bindings `'autogen'`/`'rowboat'` enthalten (beweist FIX-3 bei Boot erzwungen).

---

## 3. Test-Matrix

| Test | Datei | Beweist (RED-Natur) | Task |
|---|---|---|---|
| `test_registry_version_stamp` | `tests/test_space_agent_registry.py` | Keine `version`-Property → AttributeError | REG-1 |
| `test_canonical_spaces_matches_yaml_keys` | `tests/test_space_agent_registry.py` | Keine `canonical_spaces()` → AttributeError; `roarboot` kanonisch, `rowboat` nicht | REG-2 |
| `test_agentfarm_agent_consistent` | `tests/test_space_agent_registry.py` | Live-Drift: YAML `brain-orchestrator` (`:212`) ≠ LEGACY `vibemind` (`:48`) | REG-3 |
| `test_binding_spaces_are_canonical` | `tests/test_bindings_registry.py` | Bindings emittieren `autogen`/`rowboat` (`bindings_registry.py:24,56,62,116,122`) | FIX-3 |
| `test_space_logger_fully_canonical` | `tests/test_space_logger.py` | 5 nicht-kanonische Stellen: `:71`, `:88` (publishing), Color-Key `:107`, Badge-Key `:123`, `:75` | ABSORB-8 |
| `test_dispatch_roarboot_and_agentfarm_resolve` | `tests/test_flowzen_brain_bridge.py` | `space_to_agent('rowboat'/'autogen')==None` (Bug live); GREEN registry-derived | FIX-4 |
| `test_prefix_bindings_sourced_from_registry` | `tests/test_bindings_registry.py` | `build_prefix_bindings` ignoriert YAML (18 hardcodete Einträge) | ABSORB-5 |
| `test_keyword_bindings_sourced_from_registry` | `tests/test_bindings_registry.py` | YAML-Keyword nicht gematcht (4-Einträge-Dict) | ABSORB-6 |
| `test_legacy_map_derived_from_registry` | `tests/test_flowzen_brain_bridge.py` | Literal-Dict driftet (agentfarm-Widerspruch, s. REG-3) | ABSORB-7 |
| `test_no_minibook_router_imports` | `tests/test_flowzen_integration.py` | Import nicht-existenter minibook-Router → ModuleNotFoundError (`:86-87`) | ABSORB-9 |
| `test_boot_consistency_assertion` | `tests/test_space_agent_registry.py` | Kein `assert_consistent`; Drift → still `None` bei Dispatch | ASSERT-10 |
| `test_outcome_gate_semantics` | `tests/test_outcome_gate.py` | `outcome_gate.py` fehlt → ImportError | GATE-1 |
| `test_reward_none_is_noop` / `test_observe_none_is_noop` | `tests/test_shadow_reward_gating.py` | Kein None-Branch; `reward(rid,None)` und `observe(...,None)` POSTen heute | REWARD-2 |
| `test_multihop_response_carries_routing_id` | `brain/the_brain/tests/test_multihop_response_contract.py` | Response trägt kein `routing_id` (nur `plan_id`, `brain_multihop_bridge.py:108`) | MH-5a |
| `test_bridge_no_fake_positive_reward` | `tests/test_openfang_bridge_reward.py` | `success=True` auf non-throw (`brain_openfang_bridge.py:188,380`) | OF-3 |
| `test_empty_hop_does_not_train_success` | `tests/test_orchestrator_reward_gating.py` | Tool `{}` → `observe/reward(success=True)` (Sinks bei `:1340,:1348`) | ORCH-4 |
| `test_event_label_not_posted_on_failed_execution` | `tests/test_orchestrator_reward_gating.py` | `observe()`-Label-POST (`:955,:1244`) feuert heute bedingungslos, auch bei ok=False | ORCH-4 |
| `test_multihop_rewards_only_on_verified` | `tests/test_multihop_reward_gating.py` | `executed`-Verdict wird verworfen, nie Reward (`:99/:182`); Fixture == MH-5a-Schema | MH-5 |
| `test_no_hardcoded_success_true_in_shadow_sinks` | `voice/python/tests/test_no_fake_shadow_success.py` | 6 Fake-Sinks (Muster-Match, nicht Zeilen) | NOFAKE-6 |
| `test_parallel_add_event_one_done_consistent` | `brain/the_brain/tests/test_kotlin_graph.py` | Lock-freies `add_event`: dup/verlorene IDs, divergente Counter — **RED protokolliert** | KG-C1/C2 |
| `test_is_episode_done_three_condition_rule` | `brain/the_brain/tests/test_kotlin_graph.py` | Kein `is_episode_done` → AttributeError | KG-C3 |
| `test_dualgraph_record_event_parallel_consistent` | `brain/the_brain/tests/test_dual_graph.py` | Pre-Lock: durchgereichte Counter divergieren (`dual_graph.py:68-121`) | KG-C4 |
| `test_guardrail_policy_present` | `tests/policy/test_guardrail_policy_present.py` | Policy-Doc fehlt → 6 Anker nicht vorhanden | POL-0 |
| `test_no_live_transport_in_sandbox` | `tests/policy/test_no_live_transport_in_sandbox.py` | **xfail(strict=True)**: Discovery failt bis `distribute.py` landet; XPASS erzwingt Scharfschaltung | IMPORT-2 |
| `test_env_guard` | `tests/policy/test_env_guard.py` | **skipif-absent**: Falle, aktiviert sich mit Phase-2-`backer-checkout/` | ENV-1 |
| `test_idempotency_ledger` | `tests/policy/test_idempotency_ledger.py` | **skipif-absent**: dito | IDEM-3 |
| `test_env_file_resolution` | `tests/policy/test_env_file_resolution.py` | **skipif-absent**: dito (Anti-Pattern in V1 nicht exerzierbar — ehrlich als Falle geführt) | ENVFILE-4 |
| `test_port_collision` | `tests/policy/test_port_collision.py` | **skipif-absent**: dito | PORT-5 |

**RED-Natur (präzisiert):** WS1/WS2/WS3-Tests sind RED gegen *lebenden* V1-Code (echte Bugs; KG-C1 zusätzlich: RED muss beobachtet/protokolliert sein). WS4-Enforcement-Tests sind **red-by-absence** — keine Bug-Beweise, sondern vorinstallierte Fallen — und per skipif/xfail neutralisiert, sodass **die Gesamt-Suite in Phase 0/1 grün ist**. `test_guardrail_policy_present` ist der einzige WS4-Test, der in Phase 0 aktiv GREEN wird.

---

## 4. Reihenfolge-Begründung

- **Harte Blocker (Wave A + deren direkte Nachfolger):**
  - `GATE-1` (Wave A) blockt die gesamte Fake-Signal-Reparatur — Wurzel von WS2.
  - `KG-C1→KG-C2` (Wave A→B): Der RLock blockt jede parallele Episode-Ingestion; KG-C2 sitzt in **Wave B**, weil es das *beobachtete* KG-C1-RED voraussetzt (Rev.-1-Text nannte KG-C2 fälschlich Wave A — die Tabelle war korrekt, der Text ist jetzt angeglichen).
  - `REG-2`/`REG-3`/`FIX-3`: Dispatch-Blocker. **REG-3 muss vor Wave D entschieden sein**, sonst frieren FIX-4/ABSORB-7 den agentfarm-Widerspruch in zwei sich gegenseitig ausschließende Green-Conditions ein (der zentrale Rev.-1-Fehler).
- **`FIX-3` + `ABSORB-8` in einem Commit (Wave C):** Findings-Risiko wörtlich genommen — Dispatch-Rename und Logger-Map dürfen keinen Zwischenzustand haben, in dem Dispatch kanonisch emittiert und der Logger noch `rowboat` mappt.
- **`OF-3` vor `FIX-4`/`ABSORB-7` vor `ASSERT-10` (geteilte Datei):** `brain_openfang_bridge.py` ist die **eine** workstream-übergreifend geteilte Datei; ihre vier Edits sind explizit serialisiert (ein Owner), damit ABSORB-7s Map-Rewrite nicht mit OF-3s Reward-Edits kollidiert und keine Zeilendrift Tests bricht (Tests matchen ohnehin Muster, nicht Zeilen).
- **`REWARD-2` vor `OF-3`/`ORCH-4`:** Das None-No-op-Verhalten muss existieren, bevor die Sinks `None` statt `True` senden.
- **`MH-5a` vor `MH-5`:** Ohne Brain-seitiges `routing_id` in der Response würde MH-5s Reward in Produktion nie feuern — grün nur auf Mock wäre genau die Art Fake-Grün, die Phase 0 beseitigen soll.
- **`ASSERT-10` ganz zuletzt (Wave E):** Der Boot-Assert darf erst scharf werden, wenn Bindings (FIX-3) UND die abgeleiteten Maps (ABSORB-5/6/7) kanonisch sind. Feature-Flag (warn→raise) mildert den ersten Rollout.
- **`NOFAKE-6` nach ORCH-4/OF-3/MH-5:** Der Muster-Guard kann erst grün werden, wenn die 6 Sinks entfernt sind.
- **`POL-0` zuerst in WS4:** Alle Guardrail-Tasks referenzieren die Policy inkl. des Aktivierungs-Mechanismus (skipif/xfail) als Vertrag; die Enforcement-Fallen blockieren Phase 0 nicht.
- **Parallelität (korrigiert):** WS1–WS4 teilen **genau eine** Datei (`brain_openfang_bridge.py`, serialisiert wie oben); alle übrigen Ketten sind voll parallel fahrbar, `depends_on`-Waves gelten innerhalb eines Workstreams plus die drei benannten Cross-Workstream-Kanten (FIX-4⟵OF-3, ABSORB-7⟵OF-3, MH-5⟵MH-5a).

---

## 5. Definition of Done für Phase 0 (Gate zu Phase 1)

**WS1 — Routing-Registry:**
- `config/space_agent_registry.yml` ist die **einzige** handgepflegte space→agent-Quelle; Prefix/Keyword-Bindings, `LEGACY_SPACE_AGENT_MAP` und Logger-Zielspaces/-Farben/-Badges sind daraus abgeleitet oder dagegen validiert.
- **agentfarm-Agent per REG-3 entschieden und dokumentiert** (mit OpenFang-Agent-Listen-Beleg); Registry-Wert == Bridge-Wert; **kein Test hardcodet den agentfarm-Agenten**.
- `registry_version (==1)` bei Load geloggt + programmatisch verfügbar.
- Für `roarboot`: Prefix `roarboot.` UND Keyword → `RouteResult.space=='roarboot'`; Bridge → `rowboat-knowledge`. Für `agentfarm`: Keyword `agent farm` → `'agentfarm'`; Bridge löst auf den Registry-Agenten auf. Beide dispatchen E2E ohne `None`.
- `canonical_spaces() == Brain SPACE_NAMES == YAML-Keys`; jede Divergenz (inkl. lingering `rowboat`/`autogen`) → `RegistryConsistencyError` bei Boot (feature-geflaggt).
- `space_logger.py` enthält **kein** `'rowboat'`/`'autogen'`-Vorkommen mehr (Values `:71/:75/:88`, Color-Key `:107`, Badge-Key `:123`); Color- und Badge-Dict decken jeden kanonischen Space ab.
- Kein Source/Test importiert `spaces.minibook.…EVENT_TYPE_TO_SPACE`/`…SPACE_AGENT_REGISTRY`.

**WS2 — Fake-Signale:**
- `outcome_gate.py` existiert; `verified=True→True`, `False→False`, `None/verdict=None→None`, `ok=False→False`.
- `reward(rid, None)`/`_reward_brain(rid, None)`/`observe(..., None)` = **null** POSTs (`None` ist überall No-op — nirgends fabriziertes Positiv ODER Negativ).
- **Keine** `_brain_shadow`/`_brain_event_shadow`/`_reward_brain`-Callsite mit Literal `success=True` (NOFAKE-6: 6→0; Whitelist unangetastet; Muster-Match).
- **Beide Hälften** des Event-Shadow-Loops gegated: reward-Sinks über `contract_pass`, `observe()`-Label-POSTs (`:955/:1244`) feuern nur bei `sig is True`.
- Hop `{}` trainiert **kein** positives Signal. Nur echtes `verified=True` → `reward(success=True)`.
- `/api/multihop/execute` liefert ein reward-fähiges `routing_id` (MH-5a, gegen echten Serializer getestet); die Multihop-Bridge speist den realen `executed`-Verdict an diese ID zurück; fabriziert nie `True` bei leerem `executed`.
- Alle `success=False`-Negativ-Sinks (`intent_orchestrator :822,:980,:1368`; `brain_openfang_bridge :217,:397`) intakt; legitime Status-Flags unverändert.

**WS3 — KotlinGraph:**
- `KotlinGraph.__init__` erzeugt `self._lock = threading.RLock()`; `add_event`-Body (ID-Allokation bis `done`-Close + `total_events++`) in **einem** `with self._lock:` (per Diff verifiziert).
- KG-C1 RED **beobachtet und protokolliert** gegen pre-Lock, GREEN nach Lock über wiederholte Iterationen; N parallele Calls mit einem `done=True` → unique IDs, `total_events==total_transitions==N`, genau eine geschlossene Episode.
- Gesamte 668-Zeilen-`test_kotlin_graph.py` bleibt grün.
- `done`-3-Bedingungs-Regel in Docstring + `is_episode_done(...)` mit Table-driven-Test.
- DualGraph.record_event konsistent unter parallel Load ohne `dual_graph.py`-Edit; Residual-Gap notiert.
- **Kein I/O** in der kritischen Sektion.

**WS4 — Guardrails (Policy-Gate für Phase 0):**
- `docs/policy/backer-sandbox-guardrails.md` existiert, enumeriert alle 5 Guardrails + Aktivierungs-Mechanismus, zitiert jedes verhinderte OS-Anti-Pattern per `file:line`, labelt jeden Task Phase-0-POLICY vs Phase-2-ENFORCEMENT.
- Die 5 Enforcement-Tests liegen unter `tests/policy/`, sind committed mit skipif-absent bzw. xfail(strict=True) und als red-by-absence-Fallen dokumentiert. **Kein `backer-checkout/`-Verzeichnis existiert nach Phase 0.**
- `test_guardrail_policy_present` grün (Meta-Gate).

**Übergreifend:** Alle neuen Verhaltens-Tests RED gegen den heutigen Code, GREEN nach der Änderung; **die Gesamt-Suite (`voice/python`, `brain/the_brain`, `tests/policy/`) ist am Ende von Phase 0 grün** (WS4-Fallen zählen als SKIP/XFAIL, nicht als Fail). Commit über PowerShell auf `feat/mcp-tool-hub`.

---

## 6. Risiken & explizit NICHT in Phase 0

### Policy-jetzt vs Enforcement-bei-Phase-2 (WS4)
| Task | Status | Mechanismus |
|---|---|---|
| **POL-0** | **Phase-0 POLICY** (wird grün) | Policy-Doc + Meta-Gate. |
| **IMPORT-2** | **Phase-0 authored** | `xfail(strict=True)` — Suite grün heute; XPASS bei Phase-2-Landung erzwingt Scharfschaltung. |
| **ENV-1, IDEM-3, ENVFILE-4, PORT-5** | **Phase-2 ENFORCEMENT** | `skipif`-absent auf `backer-checkout/` — Suite grün heute; Auto-Aktivierung mit Phase-2-Code. Red-by-absence, keine Bug-Beweise. |

### Risiken (aus Findings + Critic)
- **WS1 Namens-Rename:** `rowboat→roarboot`/`autogen→agentfarm` kann andere Consumer brechen, die auf `RouteResult.space=='rowboat'` keyen. **Vor Merge alle `hybrid_router` `RouteResult.space`-Consumer greppen.** Logger-Fix (ABSORB-8) landet per Plan **im selben Commit** wie FIX-3 — der transiente Inkonsistenz-Zustand ist damit ausgeschlossen.
- **WS1 agentfarm-Entscheid (REG-3) braucht laufenden Stack:** :4200 war bei Plan-Erstellung down; der Entscheid darf nicht aus Doku/Memory geraten werden (Pitch/Doc lügen — `feedback_verify_empirically_not_pitch`), sondern nur gegen die echte OpenFang-Agent-Liste.
- **WS1 ASSERT-10 Hard-Fail:** Feature-geflaggt (warn vs raise) im ersten Rollout; fehlt die YAML komplett, läuft Boot über minimalen Static-Fallback statt hart zu failen.
- **WS1 zwei Shadow-Loops:** Design-Doc (`cascade-integration-design.md:196`) warnt vor `_brain_shadow` + `_brain_event_shadow` — Namensänderung muss **beide** kanonisch speisen. Vor Merge verifizieren.
- **WS2 Gate ist SOFT (`capability_validator:425` `valid = verified is not False`):** Für **Lernen** invertieren wir die Softness — UNVERIFIED → **kein** positives Reward (`None`), nicht Pass. Bewusst abweichend von der Execution-Gating-Semantik; **nicht angleichen**.
- **WS2 `None`-Policy = Signal-Verlust, bewusst gewählt (Critic-Punkt):** `observe(None)` sendet jetzt **gar nichts** (statt Rev.-1s `success:false`). Tradeoff: Der SpaceRoutingHead bekommt weniger Samples, aber keine falschen Negativ-Labels für korrekte Routings ohne Verdict (der Normalfall in Tier1-4). Gleiches Prinzip beim Event-Label-Gating (ORCH-4 Teil 2): Labels nur bei `sig is True` — der Klassifikator lernt langsamer, aber sauber. Beides bewusst: **erst Fakes killen, dann Volumen zurückholen** (Phase 1: Verdicts durch Tier1-4 fädeln).
- **WS2 reduziertes Positiv-Volumen:** Tier1-4 und OpenFang-Direktpfade haben keinen Verdict → nach dem Fix kein positives Reward, bis ein Verdict durchgefädelt ist. Route-Head trainiert vorerst auf echte Negatives + Multihop-Pfad. Gewollt, kein Regress.
- **WS2 MH-5a-Scope-Risiko:** Falls das Brain-seitige `routing_id`-Threading größer ist als erwartet (Reward-Endpoint-Korrelat unklar), wird MH-5 als „blocked on Brain API" re-scoped statt mock-grün abgehakt — mock-grün wäre selbst ein Fake-Signal.
- **WS2 async fire-and-forget:** `asyncio.create_task`-Rewards machen Tests flaky — Tests müssen scheduled Tasks awaiten oder einen synchronen Spy-Shadow injizieren.
- **WS3 RLock-Zwang:** Plain-`Lock` wäre latente Deadlock-Falle bei Re-Entrance; RLock wie `plan_executor.py:71/:228`.
- **WS3 GIL täuscht:** Read-modify-write ist nicht atomar — Race real, aber probabilistisch; darum Barrier + ~20× Loop **und** die Pflicht, das RED tatsächlich beobachtet zu haben, bevor der Lock landet.
- **WS3 `done`-Regel advisory:** `is_episode_done` zentralisiert die Regel, aber `add_event` vertraut weiter dem übergebenen `done` — ein zukünftiger Adapter, der die Regel ignoriert, schließt Episoden trotz Lock falsch.
- **WS4 Grep-False-Positives:** AST als Primär-Check, Raw-Grep sekundär; `backer-checkout/` als einzige Live-Transport-Allowlist.
- **WS4 Port-Assertion:** Brain-Host:Port aus realer Orchestrator-Config lesen — der **Assert** (nicht die Zahl) ist das durable Guardrail.
- **Zeilennummern-Drift:** Alle `file:line` im Plan sind Ist-Stand-Orientierung; kein Test asserted Zeilen (NOFAKE-6 & Co. matchen Muster). ABSORB-7s Map-Rewrite verschiebt Zeilen in der geteilten Datei — durch die Serialisierung OF-3→ABSORB-7 unschädlich.

### Explizit NICHT in Phase 0
- **Kein** `OutcomeContract`-Klassenbau — existiert nur im Design-Doc; wir zielen auf die reale `capability_validator`/`world_observer`-Gate.
- **Kein** `multihop_kotlin_adapter` — nur thread-sichere Ingest-Basis + `is_episode_done`-Regel.
- **Kein** Bandit/Graduation/Optimierung — Lernen beginnt erst in Phase 1.
- **Keine** Backer/Distribution-Implementierung (`backer-checkout/`, `distribute.py`, `ledger.py`, `env_guard.py`) — Phase 2; nur Policy + neutralisierte Fallen-Tests unter `tests/policy/`. **Kein Vaporware-Verzeichnis wird angelegt.**
- **Kein** DualGraph-Lock (`total_events_recorded`, `episodes_since_last_mine` bleiben lock-frei) — als Follow-up in KG-C4 notiert.
- **Kein** Zurückholen des Label-/Reward-Volumens für verdictlose Pfade — Phase 1 (Verdict-Threading durch Tier1-4), bewusst nach dem Fake-Kill.

**Verifikationsstand (Rev. 2, live nachgeprüft):** `space_agent_registry.py` existiert; `outcome_gate.py` fehlt (zu bauen); `kotlin_graph.py` 0 Locks; `backer-checkout`/`distribute.py` fehlen in V1; YAML `agentfarm.agent: brain-orchestrator` (`:212`) vs. LEGACY `vibemind` (`brain_openfang_bridge.py:48`) — Widerspruch real; `space_logger.py` hat 5 `rowboat`-Stellen (`:71/:88/:107/:123` + `:75` autogen); `brain_multihop_bridge.py` kennt nur `plan_id` (`:108`), kein `routing_id`; `/api/multihop/execute` lebt V1-editierbar in `brain/the_brain/web/routers/introspection.py:2425`; `observe()`-Calls bei `intent_orchestrator.py:955/:1244`, reward-Sinks bei `:971/:1181/:1348` (+ `:1340`-Block), Negatives bei `:822/:980/:1368`. Reference-only: `C:/Users/User/Desktop/VibeMind-OS/backer-checkout/*`, `cascade-integration-design.md`.
