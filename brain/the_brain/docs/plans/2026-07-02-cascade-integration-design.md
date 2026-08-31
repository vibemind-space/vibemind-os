# CASCADE-BANDIT × Task-Trace-Memory-Bridge × Evolutionary-Colony — Integrations-Design

> Grounded synthesis, Stand 2026-07-02. Jede Aussage ist gegen Multi-Agent-Recon-Findings + direkt gegen den V1-Baum verankert (Workflow `wf_3d883755-c36`, 5 Recon-Agents + adversarielle Verifikation). Vaporware ist explizit markiert und wird NIE als "funktioniert" ausgegeben.
>
> **Baum-Warnung (load-bearing):** Die CASCADE-Doc verifizierte ihre file:line-Claims gegen den **OS-Baum**. Die Voice-seitigen Zeilennummern der Doc (z.B. `observe()` @ `:708`, `sync_executor :552`) sind für den **V1-Baum, auf dem wir bauen, falsch**. In V1 liegt `observe()` bei `:1340/:1344`. Wer der Doc-Nummerierung auf V1 folgt, trifft die falschen Zeilen. Alle Voice-Zeilennummern in diesem Dokument sind gegen V1 re-resolved und mit `[V1-verifiziert]` markiert.

---

## 1. Verifizierte Topologie

**Zwei Checkouts desselben Repos (`Flissel/VibeMind-OS`), NICHT byte-identisch:**

| Checkout | Branch | Rolle | Autorität |
|---|---|---|---|
| `C:/Users/User/Desktop/Vibemind_V1/vibemind-os` | `feat/mcp-tool-hub` | Live/advanced (git-submodule) | **Authoritative für Voice/Swarm-Routing + Brain** |
| `C:/Users/User/Desktop/VibeMind-OS` | `master` | Älterer Standalone-Snapshot | **Authoritative NUR für `coding-engine/` + `backer-checkout/` + die CASCADE-Doc** |

**Bestätigte Checkout-Drift** (Recon-Subsystem 2, verdict *refuted* auf "V1 == OS"):
- `intent_orchestrator.py`: V1 = 2872 Zeilen **mit** Bridge-Wiring vs. OS = 2215 Zeilen **ohne jedes** Bridge-Wiring.
- `bindings_registry.py`: V1 = 18 Prefixe vs. OS = 13.
- **Nur in V1 vorhanden**: `brain_multihop_bridge.py`, `brain_openfang_bridge.py`, `space_agent_registry.py`, `context_assembler.py`, **`brain_event_shadow.py`** (letzteres = zweiter, eigenständiger Lern-Loop, siehe unten).
- Byte-identisch in beiden: `hybrid_router.py`, `brain_shadow.py`, `types.py`, `keyword_classifier.py`.
- **Wichtig**: CASCADE-Doc UND `backer-checkout/` UND `coding-engine/` liegen physisch nur im **OS-Checkout**.

**Die 4 Subsysteme und wie sie HEUTE verdrahtet sind:**

1. **Voice/Swarm-Routing (V1)** — `HybridRouter.resolve` (5-Tier). ACHTUNG — es gibt **ZWEI parallele Shadow-Lern-Loops** in `intent_orchestrator.py`, nicht einen:
   - `_brain_shadow` (`BrainShadowObserver`, `brain_shadow.py`) — POSTet `/api/cortex/route`, vergleicht `primary_space`, aktiviert bei 95%/100.
   - `_brain_event_shadow` (`BrainEventShadowObserver`, `brain_event_shadow.py`, **V1-only**) — eigener Brain-Event-Classifier-Loop, unabhängig, mit eigener `.classify_via_brain()`/`.observe()`/`.reward()`.
   Phase -2 `BrainMultihopBridge` POSTet `/api/multihop/execute` (gated `VOICE_BRAIN_MULTIHOP`); Phase -1 `BrainOpenFangBridge` POSTet `/api/agents/{id}/message`.
2. **Brain-Multihop (V1)** — `/api/multihop/execute` (`introspection.py:2425+`) → `difficulty_router.classify` (`:2499`, Qwen-cosine) → `PlanExecutor.execute` (`plan_executor.py`, DAG-walk) → per-Hop `capability_validator` (`truth:` → `world_observer.observe`, unabhängige supabase re-query). `PlanRecorder` → `multihop_history.jsonl` + episodic Qdrant. **KotlinGraph/DualGraph/KuroGraph** existieren + laden bei Boot (`brain_server.py:1025-1037`), werden aber **NIE mit Task-Hops gefüttert** (`memory_kotlingraph.json` = 4254 Events, 0 `openfang:`/`supabase:`-Actions).
3. **Evolutionary-Colony (OS)** — `ShinkaEvolveAgent` (`coding-engine/src/agents/shinka_evolve_agent.py`), triggert bei `ESCALATION_EXHAUSTED`. **`shinka`-Package NICHT installiert** → immer `_run_fallback` (no-op), echter GA-Pfad ist toter Code. Cell-Colony = self-healing FSM, **keine GA**.
4. **Crowdfunding-Seed (OS)** — `backer-checkout/app.py` + `paypal_client.py` (Single-$1-Sandbox, funktioniert). **`ledger.py`/`distribute.py`/`generate_links.py`/`outbox/` existieren NICHT** (vaporware, Recon-Subsystem 4+5).

**Die Brücke ist bereits gebaut**: Voice → `BrainMultihopBridge` → `/api/multihop/execute` → `plan_executor` ist der reale Hop-0→Hops-1..N-Übergang. CASCADE muss diese Kette nicht erfinden, nur mit Reward/Trajektorien-Persistenz schließen.

---

## 2. Die vereinheitlichende These

**CASCADE-BANDIT, task-trace-memory-bridge und evolutionary-colony sind EIN selbstverbessernder Orchestrator auf drei LAYERS — nicht drei Systeme.** CASCADE ist die rigorosere Formulierung (harte Contracts, Counterfactual, Provenance-Quarantäne, ID-Embedding-Bandit); der evo-Algo ist der Last-Resort-Boden desselben Stapels.

| Layer | Rolle im CASCADE-Modell | Existierender Code | Checkout |
|---|---|---|---|
| **Hop-0** (Intent → grobes Label) | SmallRouter + Warm-Start-Promotion | `HybridRouter.resolve` + `BrainShadowObserver` (95%/100) + `BrainEventShadowObserver` (2. Loop) | V1 Voice |
| **Hops 1..N** (Label → Agent-Kette) | Cascade-Controller + per-Hop-Bandit + Reward-Gate + TrajectoryStore | `plan_executor.execute` + `capability_validator`(`truth:`) + KotlinGraph/DualGraph (ungefüttert) | V1 Brain |
| **EvoRouter** (genuin novel Intent) | Budget-gedeckelte Kombinationssuche, Last-Resort | `ShinkaEvolveAgent` + `orchestrator ESCALATION_EXHAUSTED` (Trigger reuse; Genome/Fitness build-new) | OS coding-engine |

**Reconciliation**: Unser task-trace-Plan und CASCADE beantworten dieselben 6 Kollaborations-Fragen. **CASCADE gewinnt die Härte-Fragen** (Reward-Gate, Credit-Assignment, Distillation-Integrität); **unser Plan gewinnt die Struktur-Fragen** (State-Def Q1 `agent_contribution_digest`, DAG-Fan-out/Handoff/Fan-in Q4, 3-Confidence-Tier Q3). Die Synthese nimmt Q1/Q3/Q4 aus unserem Plan und **ersetzt** unser weiches Q5-Reward durch CASCADEs OutcomeContract-Hard-Gate + Counterfactual.

---

## 3. Komponenten-Mapping-Tabelle

| CASCADE-Komponente | Existierender Code (file:line) | Status | Begründung (Recon-verankert) |
|---|---|---|---|
| **Planner** | `intent_classifier.py` / `rag_intent_classifier.py`; DAG-Typ `types.py:28-40` | **reuse-as-is** | Beide Klassen existieren (Subsystem 5). Q4 mappt direkt auf `ExecutionStep.depends_on`. |
| **SmallRouter — Hop-0** | `HybridRouter.resolve`; `BrainShadowObserver` 95%/100 (`brain_shadow.py:90-100`); zweiter Loop `BrainEventShadowObserver` (`brain_event_shadow.py`) | **reuse-with-changes** | Emittiert SPACE-Labels, nicht Agent-IDs. Braucht: echte Confidence pro Tier, echtes Reward statt `success=True` — **an BEIDEN Shadow-Loops** (siehe §5.2). |
| **SmallRouter/Bandit — Hops 1..N** | `difficulty_router.classify` (`:2499`) als Cold-Start-Prior | **reuse-with-changes** → **build-new** ID-Embedding-Kopf | difficulty_router ist heute der EINZIGE Router (a-priori Qwen-cosine). Gelernter per-Hop-Bandit über Agent-IDs existiert NICHT (CASCADE §2.2). |
| **Executor** | `plan_executor.execute` (`_exec_hop:1508`); Voice: `sync_executor.process_multi_step` | **reuse-with-changes** | DAG-Walk funktioniert. `HopResult` trägt `ok`+`validator_verdict`, **kein `reward`-Feld**. `sync_executor:548/:554` [V1-verifiziert] setzt `success=True` bei jedem non-throwing return. |
| **Reward / OutcomeContract** | `capability_validator._run_truth_validator:381` → `world_observer.observe` | **reuse-with-changes** | `truth:`-Validator IST das unabh. Ground-Truth-Gate. ABER soft+partial: `UNVERIFIED(None)→valid=True`, nur `REFUTED` failt, **und die meisten `openfang:`-Hops deklarieren gar keinen Validator** → siehe §5.5 (Coverage-Design). |
| **TrajectoryStore** | KotlinGraph `add_event` (`kotlin_graph.py:100`); DualGraph `record_event` (`dual_graph.py:99`) | **reuse-as-is (Writer)** + **build-new (Ingest+Lock+done)** | Writer domain-agnostisch fertig, ABER `PlanExecutor` hält `kg=qdrant_kg` (`brain_server.py:767`), NICHT DualGraph. `add_event` mutiert `state_index`/`episodes`/`current_episode_id` **lock-frei** (`:155-210`). CASCADEs eigener SQLite-Store = vaporware-in-doc. |
| **Distillation** | KuroGraph n-gram mining (`kuro_graph.py`) | **reuse-with-changes** | `DualGraph._auto_mine` minet 2..5-grams, aber nur aus Chat-Thoughts. `KuroPatternExecutor`/`kuro:pattern_<id>` = vaporware. |
| **Cascade-Escalation** | `difficulty_router` easy/medium/hard/insane (`:2499+`); Voice-Bridges Phase -2/-1 Fall-through | **reuse-with-changes** | A-priori-Routing existiert; per-Hop "conf<TAU ODER ID∉allowed_ids ODER OOD → eskaliere" neu. |
| **EvoRouter** | `ShinkaEvolveAgent` + `orchestrator ESCALATION_EXHAUSTED:173-176` | **Trigger reuse; Genome/Fitness build-new; GA-Loop vaporware** | `shinka` nicht installiert → GA toter Code. Genome=Source-String (falsch). Fitness=Syntax-Heuristik (gameable, §7.2-verboten). |
| **Guardrails** | `SecurityGateway` (`colony/security_gateway.py`); PayPal `PAYPAL_ENV` soft-default (`app.py:44`) | **reuse-with-changes + build-new (import-graph-Allowlist)** | Alle Zero-Send-Assertions aspirational. SecurityGateway ist RBAC, nicht import-graph-basiert. |

---

## 4. Wo der evolutionäre Algo einklinkt

**Heutiger Zustand (hart verifiziert):** `import shinka` → `ModuleNotFoundError`; `SHINKA_AVAILABLE=False` → `EvolutionRunner.run()` nimmt IMMER `_run_fallback` (no-op). Der GA-Loop (`_run_shinka`, num_generations=15) ist **toter Code**. Jede Behauptung "evolutionäre Suche läuft heute" ist refuted.

**Reused (Scaffolding):** Der Last-Resort-Trigger `ESCALATION_EXHAUSTED` (`ESCALATION_THRESHOLD=3`, `orchestrator.py:173-176`) = exakt CASCADE §9 Phase 5. Das Event-Wiring (`event_bus.py:725-731`).

**Build-new, damit Shinka zum CASCADE-EvoRouter wird:**

| Aspekt | Heute (falsch für Routing) | Nötig |
|---|---|---|
| **Genome** | Source-Datei in `EVOLVE-BLOCK` (`:154-162`) | **StepGraph-ID-Assignment** über `allowed_ids` (`vibemind_agents_list`) |
| **Mutation** | LLM diff/full-Patch | **swap/insert/drop einer `allowed_id`** über Sandbox-Allowlist |
| **Fitness** | Syntax 0.3 + no_errors 0.4 + structure 0.3, self-graded | **derselbe OutcomeContract-Hard-Gate + Counterfactual** wie Hops 1..N (kein zweites Reward). Syntax-Heuristik = §7.2-Verbot |
| **Budget** | statisch `MAX_GENERATIONS=15` | `max_real_hops` / `max_wall_clock` / `max_dollar` / Circuit-Breaker |
| **Allowlist** | evolviert jede Datei | Suchraum MUSS Netz-Transport-IDs strukturell ausschließen (import-graph-Filter) |
| **Winner** | schreibt direkt zurück (`:470-473`) | über **denselben** quarantänierten, provenance-getrennten Distillations-Pfad wie alles andere |

**Entscheidung:** EvoRouter = Phase 5, **zuletzt**. Cell-Colony wird NICHT als GA behandelt (LLM-Edits, keine Selektion) — bleibt self-healing-Infrastruktur, kommt NICHT in den Reward/TrajectoryStore-Pfad.

---

## 5. Anti-Fragmentierungs-Entscheidungen

**5.1 EIN TrajectoryStore (nicht zwei) — inkl. co-designtem Lock+Episode-Boundary.**
Konflikt: CASCADEs neuer SQLite-`TrajectoryStore` (vaporware) vs. KotlinGraph/DualGraph (fertig, ungefüttert).
**Entscheidung: KotlinGraph/DualGraph ist die SoT.** Writer ist domain-agnostisch fertig, lädt bei Boot, KuroGraph gibt Distillation gratis. Der SQLite-Store bleibt **optionaler Export-Sink**, nicht zweite SoT.
**Build-new-Anforderungen, EINE zusammenhängende kritische Sektion:**
- (a) `contract_pass` + skalares `reward` pro Zeile (heute nur `ok`+`verified`).
- (b) `done=True`-Semantik (3-Bedingungs-Regel; heute undefiniert → sonst falsche KuroGraph-Episoden-Grenzen).
- (c) **Thread-Lock + Episode-Boundary atomar zusammen.** `add_event` (`kotlin_graph.py:100`) mutiert **lock-frei** `state_index` (`:155/:168`), `episodes` (`:203-205`) UND — bei `done=True` — `stats['total_episodes']`+`current_episode_id` (`:209-210`). `_exec_hop` läuft im ThreadPool-Batch → paralleler Write kann ein mid-episode `add_event` mit einem Episode-Close-Increment interleaven → inkonsistente Episode-Zähler. **Lock (b) und (c) werden als EINE Critical Section entworfen**: `add_event` erwirbt `self._lock` und die `done`-getriggerte Episode-Grenze (`:207-210`) läuft innerhalb desselben Lock-Halts wie der State-Index-/Episode-Membership-Write. Kein Lock ohne die done-Boundary — sonst locked-but-inconsistent.

**5.2 EIN Reward-Gate — vollständige Fake-Signal-Inventur an ALLEN Sinks.**
Konflikt: unser weiches Q5-Reward vs. CASCADEs OutcomeContract-Hard-Gate.
**Entscheidung: CASCADEs OutcomeContract IST das Gate; Q5 ist nur die Reward-*Form* NACH dem Gate.** Der `truth:`-Validator (`world_observer.observe`) ist die eine Ground-Truth-Quelle (erfüllt Memory-Regel "ok/reward NUR aus unabhängiger Ground-Truth").

**Härte-Invariante (explizit, verhindert §7.2-Rückfall):** `reward = 0` (bzw. negativ) **immer wenn der OutcomeContract failt — unabhängig von jedem Q5-Term**. Die weichen Q5-Terme (`− λ·cost + β·collab`) dürfen Reward-Magnitude **nur INNERHALB gate-passierter** Trajektorien modulieren und können eine gate-gefailte Hop NIE ins Positive retten. Q5 ist Ranking innerhalb des Passes, kein zweiter Reward-Pfad.

**Das fake Signal sitzt an weit MEHR als drei Stellen — die Doc-Inventur war unvollständig.** Grep über `voice/python/swarm` findet **15 `success=True`-Vorkommen in 8 Dateien**, und in `intent_orchestrator.py` allein feuern **BEIDE** Shadow-Loops hartkodierten Erfolg:
- `_brain_shadow.observe(success=True)` @ `:1344`, `:955`, `:1244` [V1-verifiziert]
- `_brain_event_shadow.reward(success=True)` @ **`:1350`**, `:822`, `:972`, `:980`, `:1183` [V1-verifiziert] — **der von der Doc + der ersten Design-Version komplett übersehene zweite Lern-Loop.**
- `sync_executor.py:548/:554`; plus base_agent, tool_orchestrator, rag_intent_classifier, base_space_agent, brain_openfang_bridge, system_status.

**Phase-0-Regel:** VOR jeder Behauptung "fake Signal entfernt" wird `voice/python/swarm` vollständig nach **allen** `.observe(`/`.reward(`-Call-Sites BEIDER Shadows (`_brain_shadow` UND `_brain_event_shadow`) gegreppt**, und jede dieser Stellen wird durch das **eine** OutcomeContract-Gate geroutet — nicht nur `_brain_shadow.observe()`. Solange `_brain_event_shadow.reward(success=True)` bei `:1350` lebt, trainiert der Brain-Event-Classifier genau auf dem hartkodierten Erfolg, den wir töten wollen.

**5.3 EINE versionierte Registry — inkl. minibook-Fold-Entscheidung.**
Bestätigte reale Drift (Subsystem 2): FÜNF Maps, nur die YAML `SpaceAgentRegistry` ist versioniert. Realer Bug: Router emittiert Space `rowboat`/`autogen`, aber `LEGACY_SPACE_AGENT_MAP`-Keys sind `roarboot`/`agentfarm` → Space-Name-Mismatch, Dispatch failt. Plus drei minibook-enrichment-Maps `_PREFIX_MAP`(12)/`EVENT_TYPE_TO_SPACE`(11)/`SPACE_AGENT_REGISTRY`(10).
**Entscheidung: `SpaceAgentRegistry` (versioniert) absorbiert ALLE anderen vier Dicts VOR jeder Lern-Verdrahtung — inklusive der drei minibook-enrichment-Router.** Sie folden NICHT in einen zweiten Speicher; kein Zwei-Registry-Ausgang (swarm versioniert, minibook driftend). Ein Bandit über driftende IDs lernt Müll. Phase-0-Blocker.

**5.4 EINE Difficulty-Definition — mit definiertem Cutover-Threshold.**
Konflikt: unser Plan = MEDIAN-Hop-Count zu `done=True` (gemessen); CASCADE = Eskalations-Tiefe (a-priori). Beide demoten `difficulty_router` (Qwen-cosine) auf Cold-Start-Prior.
**Entscheidung: EIN Feld `measured_difficulty` = Median-Hop-Count zu `done=True`, mit `difficulty_router` als Cold-Start-Bootstrap-Prior.** CASCADEs Eskalations-Tiefe ist eine Ableitung desselben Signals.
**Definierter Handoff (verhindert permanentes Dual-System):** Cutover **pro Task-Klasse**, nicht global. `measured_difficulty` überschreibt den a-priori-Prior erst, wenn für diese Klasse **≥ N `done=True`-Trajektorien mit stabilem Median** vorliegen (N als Config-Konstante, Startwert 30 pro Klasse, monitored transition mit geloggtem Wechsel-Event — kein implizites Umschalten). Vorher bleibt `difficulty_router` load-bearing. `measured_difficulty` ist reiner Read des KotlinGraph-Hop-Counts → **existiert erst wenn der Ingest aus 5.1 läuft** (+ `task_class_clusterer.py`, siehe §7 — nur im Plan benannt, **null Scaffolding, näher an Vaporware als an "build-new"**).

**5.5 EINE Reward-Coverage für validatorlose `openfang:`-Hops (der echte Naht zwischen Subsystem 1 und 2).**
Problem: Der `truth:`-Validator deckt nur Hops mit deklariertem Validator; die **meisten `openfang:`-Agent-Hops haben keinen** → der Bandit ist auf genau den Hops blind, die Multi-Hop am meisten braucht.
**Entscheidung (Design, nicht bloß Risiko):** Jeder Hop bekommt eine **OutcomeContract-Quelle**, aufgelöst in dieser Priorität:
1. Deklarierter `truth:`-Validator in `capabilities.yaml` (Ist-Zustand für die Minderheit).
2. **`capabilities.yaml`-Schema-Erweiterung**: neues Feld `outcome_contract:` pro Agent/Hop, das eine unabhängige `world_observer`-Re-Query (supabase_row / edge / node_in_bubble) deklariert.
3. **Fail-closed Default-Contract**: Hops ohne (1) oder (2) erhalten einen Contract, der eine unabhängige Ground-Truth-Re-Query **erzwingt**; kann sie nicht erfüllt werden, ist das Ergebnis `UNVERIFIED → reward 0` (nie `valid=True`).
Das schließt die Naht, statt sie als Risiko stehen zu lassen. **Phase-3-Bandit-Aktivierung ist gated auf Reward-Coverage**, nicht nur auf Trajektorien-Zahl: erst wenn **≥ X% der ausgeführten Hops einen echten Ground-Truth-Contract tragen** (Startziel 80%), darf der Multi-Hop-Bandit lernen.

---

## 6. Rekonzilierter Phasen-Bauplan

Merge: CASCADE Phase 0-5 + task-trace-Plan + Evo-Arbeit → EIN geordneter Pfad.

**Phase 0 — Geteilter Blocker.** *Kein Lernen.*
- **Schritt 1 (NEU, echte Precondition, VOR allem anderen): Checkout-Topologie auflösen** — siehe §7, jetzt als Entscheidung, nicht offene Frage. Erst wenn feststeht, in welchem Baum `plan_executor` und der `backer.*`-Executor-Payload leben, kann irgendein Reward-Gate über die Repo-Grenze verdrahtet werden.
- Registry-Drift fixen: 4 Dicts (inkl. der 3 minibook-Router) in `SpaceAgentRegistry` konsolidieren; `roarboot`/`rowboat`- und `agentfarm`/`autogen`-Mismatch beheben (§5.3).
- **Vollständige Fake-Signal-Entfernung**: `voice/python/swarm` nach ALLEN `.observe(`/`.reward(`-Sites BEIDER Shadows greppen; `success=True` an **allen 15 Sinks** (inkl. `_brain_event_shadow.reward` @ `:1350/:822/:972/:980/:1183`) durch das eine OutcomeContract-Gate ersetzen (§5.2).
- Sandbox-Guardrails **strukturell**: `PAYPAL_ENV`-Assertion fail-closed (Boot+Hop+Pre-POST) statt soft-default `app.py:44`; PayPal-Request-Id-Idempotency-Header; Credential-Leak aus `x-pathfinder/.env` (`app.py:33`) kappen; Port-Kollision 5000 (BrainShadow ↔ Flask) auflösen.
- **KotlinGraph-Lock + Episode-Boundary als EINE Critical Section** (§5.1c) — zusammen mit der `done=True`-Semantik entworfen, nicht separat.

**Phase 1 — Instrumentierung.** *Noch kein Lernen.*
- `multihop_kotlin_adapter.py` (build-new) an den 3 Hook-Sites (`plan_executor.py:347/1016/1383`); `PlanExecutor`-Handle auf `state.dual_graph`.
- `HopResult` um `reward`+`contract_pass`; `done=True`-3-Bedingungs-Regel.
- **Observe-Coverage schließen (NEU im Phasenplan, nicht nur als Risiko):** Instrumentierung erfasst NICHT nur den KotlinGraph-`plan_executor`-Pfad, sondern auch die Voice-seitigen Execution-Pfade, die heute NULL Trainingssignal emittieren — MinibookHub (Phase 0.5) und die Bridge-Pfade Phase -1/-2. Beide Shadow-Loops (`_brain_shadow` UND `_brain_event_shadow`) müssen an diesen Pfaden ein echtes (gate-basiertes) Signal produzieren, sonst bleibt der Hop-0-Warm-Start-Korpus dauerhaft zum leichten Fast-Path verzerrt.
- **OutcomeContract-Quellen für validatorlose Hops** verdrahten (§5.5: `capabilities.yaml outcome_contract:`-Schema + fail-closed Default).
- Golden-Set-Beschaffung für Hop-0-Imitation (≥95% Agreement auf Held-Out, NICHT gegen Live-Router).

**Phase 2 — Backer-Bausteine + Skeleton.** *Vaporware zuerst bauen.*
- `ledger.py`, `distribute.py`, `generate_links.py`, `outbox/` mit Tests — in dem in Phase-0-Schritt-1 gepinnten Baum (Submodule-Pfad steht dann fest).
- CI-Gate: `grep distribute.py` für Transport-Symbole (requests/smtplib/http/socket/paypal) MUSS leer sein.
- Always-Escalate 3-Hop-Skeleton `[backer.generate_links --dry-run → distribute.preview → outbox/ → backer.status]`.
- OutcomeContract-Gate scharf; Zero-Send-Veto verifiziert (positive Evidenz: Transport un-importierbar).

**Phase 3 — Hop-0-Bandit aktivieren.**
- ID-Embedding-Bandit-Kopf (build-new); beide Shadow-Loops als Warm-Start; Low-Conf-Eskalation; provenance-getrennte Destillation mit Quarantäne+Audit.
- `measured_difficulty` (§5.4) sobald Cutover-Threshold pro Klasse erreicht.
- **Gate: Aktivierung erst bei ≥80% Reward-Coverage über echte Ground-Truth-Contracts (§5.5), nicht nur bei Trajektorien-Zahl.**

**Phase 4 — Multi-Hop (separat gegatet).**
- Counterfactual-Harness (per-Hop-Ablation); Decision-Hop-Destillation; NUR wenn Held-Out beweist: gelernt schlägt always-escalate. Voraussetzung: ≥200 saubere Hops über ≥20 Intents.
- Q1-State (`agent_contribution_digest`), Q3-3-Confidence-Tiers, Q4-DAG-Fan-out/Handoff/Fan-in.
- KuroGraph-Shortcuts (`kuro:pattern_<id>`) + `KuroPatternExecutor` (heute vaporware).

**Phase 5 — EvoRouter (Last-Resort).**
- `shinka` installieren; Genome→StepGraph-ID-Assignment; Fitness→OutcomeContract; Budget-Cap; strukturelle Allowlist; Winner über denselben quarantänierten Distillations-Pfad (§4).

**Phase (später, separat) — Go-Live.** Eigener Plan, Zwei-Personen-Freigabe. Außerhalb.

---

## 7. Ehrliche offene Entscheidungen & Risiken

**Checkout/Branch — jetzt eine ENTSCHEIDUNG, nicht offene Frage (echte Phase-0-Precondition).**
Die CASCADE-Doc verifizierte gegen den **OS-Baum** (2215-Zeilen-Orchestrator ohne Bridges); die reale Bridge-Verdrahtung lebt nur in **V1** (2872 Zeilen). Man kann kein CASCADE-Reward-Gate verdrahten, dessen Executor-Payload (`backer.*`) in einem anderen Checkout liegt als der `plan_executor`, der es aufruft, ohne vorher zu klären, wie die Bäume einander referenzieren.
**Vorgeschlagene Entscheidung (Phase-0-Schritt-1, bestätigungsbedürftig):** **V1 (`Vibemind_V1/vibemind-os`, `feat/mcp-tool-hub`) ist der authoritative Baum für Voice/Brain.** `backer-checkout/` und `coding-engine/` werden als **git-Submodule** aus V1 referenziert (nicht vendored — sie sind separate Repos und ihre eigenständige Historie bleibt erhalten). Der exakte Submodule-Pfad wird in Phase-0-Schritt-1 gepinnt und dokumentiert, BEVOR Phase 2 `ledger/distribute/generate_links/outbox` baut — damit diese Module wissen, in welchem Baum sie landen. **Voice-Zeilennummern aus der CASCADE-Doc werden beim Bau gegen V1 re-resolved** (`observe()` = `:1340/:1344`, nicht `:708`; `sync_executor` = `:548/:554`, nicht `:552`).

**Vaporware, die ZUERST gebaut werden muss (Wiring darauf JETZT verboten):**
- `backer-checkout/ledger.py`, `distribute.py`, `generate_links.py`, `outbox/` — jede CASCADE-Tier-A-Reward-Gate referenziert sie. Existieren NICHT.
- `multihop_kotlin_adapter.py`, `KuroPatternExecutor` — im Plan benannt, existieren nicht.
- `task_class_clusterer.py` — **nur im Plan benannt, NULL Scaffolding** (näher an Vaporware als an "build-new"; §5.4 hängt daran).
- `shinka`-Package — nicht installiert; GA toter Code.
- ID-Embedding-Bandit-Kopf — CASCADE §2.2, explizit NEU.

**Verbleibende Showstopper (Coverage jetzt designt, nicht nur geflaggt):**
1. **Reward-Coverage** ist in §5.5 als konkretes Design gelöst (capabilities.yaml-Schema + fail-closed Default + Phase-3-Coverage-Gate). Restrisiko: der `outcome_contract:`-Schema-Rollout über alle `openfang:`-Agenten ist manuelle Arbeit und muss vor Phase-3-Aktivierung ≥80% erreichen.
2. **Warm-Start-Korpus evtl. leer**: Recon fand KEINE `logs/tools/*.jsonl` / `logs/intents/*.jsonl` auf Disk. Hop-0-Imitation braucht dann erst reine Datensammlung. `tool_logger` hat kein `trajectory_id`/`hop_index`/`reward`, truncatet bei 500 — kann Multi-Hop-Korpus nicht liefern.
3. **Brain-Endpoints unverifiziert**: `/api/cortex/route`, `/route/train`, `/route/reward`, `/api/multihop/execute` — Bridges fallen bei 404 still durch, "Graduation" triggert evtl. nie. Live gegen `/api/multihop/execute` real testen (Memory-Regel), nicht Service direkt.
4. **Observe-Coverage-Verzerrung**: `observe()` läuft nur auf single-hop fast-path; Tier-5 multi-space, MinibookHub, Phase -1/-2 emittieren NULL Signal. **In Phase 1 als Instrumentierungs-Subtask adressiert** (nicht mehr nur geflaggt) — beide Shadow-Loops müssen an diesen Pfaden gate-basiertes Signal produzieren.
5. **Registry-Skalierung**: `coding-engine/gen_agents.py` generiert Agents dynamisch. Werden diese IDs routbar, hält kein Bandit über Hunderte Arme bei geringem Episoden-Volumen — Cap+Alarm nötig.

**Offene Design-Entscheidungen (aus CASCADE §10):** großes Planner-Modell (Ollama/OpenRouter/`vibemind_intent`)?; LLM-Judge-Familie ≠ Generator-Familie?; Golden-Set-Labeling-Owner+Größe?; Bandit-Impl (Thompson/UCB/LinUCB)?; Sandbox-PayPal-Approve-Simulator für `paid` in CI?

**Was NICHT verwechselt werden darf:** Cell-Colony ist keine GA (LLM-Edits, keine Selektion). CASCADE-Doc-Identifier `_PREFIX_MAP`/`EVENT_TYPE_TO_SPACE`/`SPACE_AGENT_REGISTRY` existieren im swarm/routing-Layer NICHT unter diesen Namen (sie sind minibook-enrichment-Router) — Greppen danach greift ins Leere. Und: **es gibt ZWEI Shadow-Lern-Loops** (`_brain_shadow` + `_brain_event_shadow`) — wer nur den ersten dedreht, lässt den zweiten hartkodierten Erfolg (`:1350`) weiterlernen.

---

## Relevante Dateien (absolut)

- Prior-Plan: `C:/Users/User/Desktop/Vibemind_V1/vibemind-os/brain/the_brain/docs/plans/2026-06-25-task-trace-memory-bridge.md`
- CASCADE-Doc: `C:/Users/User/Desktop/VibeMind-OS/backer-checkout/docs/superpowers/specs/2026-07-02-cascade-bandit-orchestrator-design.md`
- Ingest-Hooks: `C:/Users/User/Desktop/Vibemind_V1/vibemind-os/brain/the_brain/core/plan_executor.py` (347/1016/1383)
- TrajectoryStore-Writer + Lock-Ziel: `.../core/kotlin_graph.py` (add_event :100, state_index :155/:168, episodes :203-205, episode-close :209-210), `dual_graph.py`, `kuro_graph.py`
- Reward-Gate: `.../core/capability_validator.py`
- Registry-Drift: `.../voice/python/swarm/routing/bindings_registry.py`, `brain_openfang_bridge.py`, `space_agent_registry.py`
- Fake Reward (BEIDE Shadows): `.../voice/python/swarm/orchestrator/intent_orchestrator.py` — `_brain_shadow.observe(success=True)` :1344/:955/:1244; `_brain_event_shadow.reward(success=True)` :1350/:822/:972/:980/:1183 · `brain_event_shadow.py` (V1-only, 2. Loop) · `sync_executor.py` :548/:554
- EvoRouter-Scaffold: `C:/Users/User/Desktop/VibeMind-OS/coding-engine/src/agents/shinka_evolve_agent.py`, `src/mind/orchestrator.py:173-176`
- Vaporware-Ziel: `C:/Users/User/Desktop/VibeMind-OS/backer-checkout/` (ledger.py/distribute.py/generate_links.py/outbox/ FEHLEN)
