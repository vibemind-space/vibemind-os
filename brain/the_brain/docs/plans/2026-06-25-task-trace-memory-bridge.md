# Task-Trace-Memory-Bridge — VibeMind lernt seine eigenen Workflows

**Datum:** 2026-06-25
**Owner:** Brain-Routing / Learning-Engine
**Status:** Plan-Phase. Noch nicht implementiert.

---

## In 60 Sekunden verstehen (die Geschichte)

**Deine eigene Analogie:** Ein Klotski-Puzzle hat n Steps und **einen** optimalen Pfad.
Eine VibeMind-Task ("Docker image review check for bugs and logs") hat auch n Steps —
aber **viele** mögliche Pfade zum Erfolg. Die Frage: wenn wir dieselbe Task-Art
20-mal gelöst haben, welcher Pfad war der schnellste? Und können wir uns den merken,
sodass Task 21 sofort diesen Pfad geht statt wieder alles durchzuprobieren?

**Was schon gebaut ist (das ist die gute Nachricht):** Die "Speicher-Struktur"
für gelöste Puzzles ist da und sogar schon so umgebaut, dass sie beliebige Task-Steps
statt nur Puzzle-Steps akzeptiert. Das sind drei Dateien im `core/` Ordner:

- **KotlinGraph** = das Tagebuch: jeder Step jeder gelösten Task wird als Event festgehalten
- **KuroGraph** = die Mustererkennung: welche Step-Sequenzen tauchen oft in erfolgreichen Tasks auf?
- **DualGraph** = das Team: koordiniert beide, speichert regelmäßig auf Disk

**Was fehlt (das ist was dieser Plan baut):** Niemand schreibt derzeit echte
VibeMind-Task-Steps in KotlinGraph. Das Tagebuch wird also nicht geführt →
KuroGraph findet keine Muster → keine gelernten Workflows.
Der eigentliche Task-Executor in `plan_executor.py` loggt an einen **anderen**
Speicher (ContinuousThinkingEngine = 500-Thought-Ringpuffer, keine State-Action-Sequenz).

**Ziel dieses Plans:** Den Tagebuch-Schreib-Pfad einbauen, dann die
Musterausnutzung: aus gelernten Patterns → direkte "Shortcut"-Ausführung.

---

## Vorher vs. Nachher — ein Bild

```
VORHER (Stand heute):
──────────────────────
  User: "review my docker image for bugs"
    │
    ▼
  plan_executor.py (Multi-Hop-Suche jedesmal von vorne)
    │
    ├──▶ Hop 1: openfang:brain-coder → analysiert
    ├──▶ Hop 2: openfang:fungus-search → sucht bugs
    ├──▶ Hop 3: openfang:poc-security-scanner → check
    └──▶ Hop 4: return summary
    │
    ▼
  cte.record_event("plan_completed", …)  ── (Thoughts-Ringpuffer, keine Struktur)
                                              KotlinGraph bleibt LEER
                                              KuroGraph findet nichts


NACHHER (Phase 1 + Phase 4 gebaut):
──────────────────────────────────
  User: "review my docker image for bugs"
    │
    ▼
  Task-Class-Lookup: "das kennen wir — Pattern_42 hat success_rate 0.87"
    │
    ├──▶ direkte Ausführung der gelernten Hop-Sequenz
    │      Hop 1 → Hop 2 → Hop 3 → done
    │      (kein Re-Routing, kein Re-Discovery, ~4× schneller)
    │
    ▼
  Neuer Hop-Trace wird als BrainEvents in KotlinGraph geschrieben
    → KuroGraph updated Pattern_42 stats (success_rate boost/decay)
    → Beim 21. Docker-Review ist Pattern_42 noch besser
```

---

## Glossar — die 12 Begriffe die im Plan vorkommen

| Begriff | Was es bedeutet |
|---|---|
| **Task** | Eine User-Anfrage die aus mehreren Schritten besteht ("review mein docker image", "erstelle bubble X") |
| **Hop** | Ein einzelner Schritt in der Task — z.B. "rufe brain-coder Agent auf" |
| **Multihop** | Kette von Hops die zusammen die Task lösen |
| **Capability** | Ein "Skill" den Brain kennt — matched via Regex auf User-Text, z.B. `code_review`, `browser_automation` |
| **execution_target** | Was Brain macht wenn eine Capability matched. Formen: `openfang:<agent>` (an OpenFang delegieren) oder `supabase:<table>.<op>` (direkte DB-Operation) |
| **BrainEvent** | Ein Eintrag im Tagebuch — `(state, action, next_state, reward, done)` — ein Hop in strukturierter Form |
| **KotlinGraph** | Das Tagebuch selbst — Directed Graph aus allen jemals passierten BrainEvents. Nodes = States, Edges = Actions |
| **KuroGraph** | Die Musterlisten-Schicht — extrahiert häufige Action-Sequenzen (n-grams) aus KotlinGraph, tracked `success_rate` |
| **DualGraph** | Manager der KotlinGraph + KuroGraph zusammen orchestriert + auf Disk persistiert (in `data/moltbook/`) |
| **n-gram** | Sequenz von n Actions (z.B. 3-gram = "brain-coder → fungus-search → poc-scanner") |
| **Task-Class** | Cluster ähnlicher Tasks (z.B. alle "docker review"-artigen Anfragen). Eine Klasse hat viele Episoden |
| **Shortcut** | Statt jedesmal Multihop von vorne zu suchen: direkt eine bekannte gute Sequenz spielen |

---

## Ein konkretes Beispiel — "Docker image review" durchgespielt

Angenommen der User schickt zum ersten Mal: **"Review my Docker image for bugs and logs"**

**Aktueller Ablauf (vorher):**
Brain findet Capability `code_review` → execution_target `openfang:brain-coder` →
brain-coder delegiert weiter an fungus-search → dann poc-security-scanner → dann summary.
4 Hops, ~15 Sekunden. **Nichts wird für später gemerkt.**

**Nach Phase 1 (Tagebuch führen):** Jeder der 4 Hops schreibt einen BrainEvent:

| Hop | state (kurz) | action | reward | done |
|---|---|---|---|---|
| 1 | `{cap: code_review, completed: 0, depth: 0, ctx: hash-a}` | `openfang:brain-coder:code_review` | +1.0 | false |
| 2 | `{cap: code_review, completed: 1, depth: 1, ctx: hash-b}` | `openfang:fungus-search:code_search` | +1.0 | false |
| 3 | `{cap: code_review, completed: 2, depth: 1, ctx: hash-c}` | `openfang:poc-security-scanner:security_scan` | +1.0 | false |
| 4 | `{cap: code_review, completed: 3, depth: 0, ctx: hash-d}` | `direct:summary` | +1.0 | **true** |

Das 4-gram `[brain-coder, fungus-search, poc-security-scanner, summary]` ist jetzt
im KotlinGraph. Wenn 4 weitere Docker-Reviews später denselben Pfad genommen haben →
KuroGraph sieht: **Frequency=5, Success-Rate=1.0** → das ist ein STARKES Pattern.

**Nach Phase 2 (Task-Class-Clustering):** Der User schickt Variante:
"kannst du das docker image checken?" — Qwen3-Embedding sagt: Cosine 0.91 mit
den 5 vorherigen "Docker review"-Anfragen → **selbe Task-Class**. Also
zählt der neue Trace zur selben Klasse und derselbe Pattern wird verstärkt.

**Nach Phase 4 (Shortcut-Ausführung):** Der User schickt zum 21. Mal etwas
Docker-Review-artiges. Brain checkt: gibt's für Task-Class `docker-review`
ein Pattern mit `success_rate > 0.8, frequency >= 5`? Ja, Pattern_42. Also
Route direkt zum neuen execution_target `kuro:pattern_42` → spielt die 4-Hop-Sequenz
direkt ab, kein Re-Routing. Ergebnis: 4× schneller (kein OpenFang-Roundtrip für Routing).

**Nach Phase 5 (Feedback):** User sagt "Antwort war Mist" → Reward-Update
verringert Pattern_42's success_rate. Wenn's mehrfach passiert → Pattern fällt
unter Schwellwert → Brain nutzt wieder normale Multihop-Suche. Selbst-Heilung.

---

## Was schon da ist (kein Neubau nötig)

- [`core/kotlin_graph.py`](../../core/kotlin_graph.py) — **das Tagebuch**. Class `KotlinGraph`, Method `add_event(BrainEvent)`. Fertig, domain-agnostic.
- [`core/kuro_graph.py`](../../core/kuro_graph.py) — **die Mustererkennung**. Class `KuroGraph`, Method `mine_patterns()`. Fertig.
- [`core/dual_graph.py`](../../core/dual_graph.py) — **der Manager**. Persistiert nach `data/moltbook/`. Fertig.
- [`core/confidence_adaptive_trainer.py`](../../core/confidence_adaptive_trainer.py) — Trainer-Strategie (Novice/Intermediate/Expert). Vorbereitet für Puzzle→Task-Transfer.
- [`web/brain_server.py:1025-1042`](../../web/brain_server.py) — **DualGraph + KotlinGraph werden beim Boot bereits initialisiert und aus Disk geladen**. Ready to write.
- [`core/response_agent.py`](../../core/response_agent.py) — **bisher einziger Schreiber** in KotlinGraph (schreibt Cortical-Activation-Events, nicht Task-Hops).
- `routing_matrix_autotrain` Queue + [`production/autotrain_drain.py`](../../production/autotrain_drain.py) — bestehender `shortcut_*`-Mechanismus den Phase 4 erweitert.

## Was fehlt (was dieser Plan baut) — die 5 Bausteine

1. **Multihop-Schreib-Pfad**: `plan_executor.py` schreibt nichts in KotlinGraph → **Phase 1** hookt sich ein
2. **Task-Class-Clustering**: KotlinGraph indexiert per `episode_id: int` (Klotski-Spiel-Nummern), nicht per "ähnliche User-Anfrage" → **Phase 2** fügt Embedding-Cluster hinzu
3. **`done`-Signal für Tasks**: Klotski hat klaren End-State (gelöst), Tasks nicht → **Phase 1** definiert das
4. **Shortcut-Ausführung**: KuroGraph-Patterns können nicht als execution_target gewählt werden → **Phase 4** baut neuen executor-Typ
5. **Feedback-Loop**: `/api/cortex/route/reward` updated Space-Centroide, aber nicht KuroGraph pattern stats → **Phase 5** ergänzt

## Out of Scope (bewusst NICHT in diesem Plan)

- **Umzug Klotski-Environments** → `learning_engine/klotski/neurosymbolic/environments/*` verschieben nach `spaces/klotski/` — eigener Cleanup-Plan (Phase 6 unten skizziert es aber nicht implementiert)
- **PPO-Trainer für generelle Brain-Policy** — separates Projekt
- **TriBE/fMRI-Encoder-Integration in KotlinGraph** — TriBE hat eigene Memory (bridge_levels, siehe [`tribe.md`](../../../../infra/swarm/profiles/tribe.md)), separater Plan
- **UI-Visualisierung der gelernten Patterns** — kommt später, erst muss Data-Flow stehen

---

## Warum diese Reihenfolge? (Der rote Faden)

Die 6 Phasen bauen aufeinander auf wie ein Spiel-Level:

```
Phase 0 — Safety-Net spannen (Tests die IST-Zustand fixieren)
  ↓
Phase 1 — Tagebuch führen (KotlinGraph wird gefüllt)
  ↓ [ab hier laufen echte Traces rein, alles Weitere ist Ausbau]
Phase 2 — Ähnliche Tasks gruppieren (Task-Class-Cluster)
  ↓
Phase 3 — Prüfen ob Muster wirklich emergieren (Validierung)
  ↓
Phase 4 — Muster als Shortcut ausführen (User spürt Speedup)
  ↓
Phase 5 — User-Feedback verbessert die Muster (Lernen aus Nutzung)
  ↓
Phase 6 — Optional: alten Klotski-Code aufräumen
```

**Wenn die Zeit nicht reicht:** **Phase 0 + Phase 1** reichen für den echten Sprung.
Danach fließen alle Task-Traces ins Tagebuch. Alle weiteren Phasen kannst du später
in Ruhe nachziehen — die Daten sammeln sich schon.

---

## Phase 0 — Safety-Net: Tests die den heutigen Zustand einfrieren

**Was mache ich?**
Ich schreibe zwei kurze Tests die dokumentieren wie es HEUTE aussieht:
- Test A: „Beim Brain-Start existieren KotlinGraph und DualGraph im Server-State"
- Test B: „Nach einem Multihop-Request bleibt KotlinGraph leer oder enthält nur Cortical-Events (KEINE Task-Hop-Events)"

Dazu ein Grep-Snapshot: welche Dateien schreiben aktuell in KotlinGraph? Alles was Test B als „leer" bestätigt, verletzt Phase 1 als Test-Änderung.

**Warum jetzt?**
Weil ich ab Phase 1 aktiv in `plan_executor.py` reinschreibe — und ich will vorher schwarz auf weiß haben was war, damit ich sicher sein kann dass ich nichts kaputtmache. Falls Test A rot wird nach meinen Änderungen → jemand hat versehentlich die Initialisierung gebrochen. Falls Test B rot wird → **genau das will Phase 1 erreichen** und ich flippe die Erwartung um.

**Wann ist es fertig?**

- ✅ Test A grün: `tests/test_brain_server_init.py` bestätigt Init-Zustand
- ✅ Test B grün gegen heutigen Code (dokumentiert Lücke): `tests/test_multihop_kotlin_gap.py`
- ✅ Notiz-Datei `tasks/notes/2026-06-25-kotlin-writers-before.txt` mit Grep-Ergebnis

**Deliverables:** 2 Test-Files + 1 Notiz. **NULL Code-Änderung in `core/`.**
**Aufwand:** 1-2 Stunden.

---

## Phase 1 — Tagebuch führen (Multihop-Hop-Ingest)  ⭐ größter Win

**Was mache ich?**
Jeder Hop im Multihop-Executor schreibt einen `BrainEvent` ins Tagebuch. Ein BrainEvent
ist ein simples 5-Tupel: `(state, action, next_state, reward, done)` — genau die
Struktur die KotlinGraph erwartet (weil sie aus dem Klotski-Kontext geportet wurde).

Konkret: ein neues kleines Adapter-Modul `core/multihop_kotlin_adapter.py`, das für
jeden Hop diesen BrainEvent baut und in `state.kotlin_graph` steckt. An 3 Stellen im
`plan_executor.py` — dort wo heute schon `cte.record_event(...)` läuft — kommt eine
weitere Zeile dazu: `adapter.record_hop(...)`. Kein Umbau des existierenden Logs,
nur eine parallele Schreiberei zusätzlich.

**Warum jetzt?**
Weil OHNE das der ganze Rest sinnlos ist. Wenn niemand ins Tagebuch schreibt,
findet KuroGraph keine Muster, kann Brain keine Shortcuts spielen. Das ist der
Fundament-Schritt für alles was danach kommt.

**Design-Entscheidungen** (die schwierigen Fragen die ich vorab beantworte):

*Wie sieht `state` aus?* — Ein Dict das den Kontext beschreibt in dem der Hop passiert:
```python
{
    "capability": "code_review",      # welche Fähigkeit routet gerade
    "completed_hops": 2,               # Wie viele Schritte schon gemacht
    "agent_chain_depth": 1,            # Wie tief in Sub-Delegation
    "context_hash": "ab34...cf",       # Fingerabdruck aus (user_text + bisherige Ergebnisse), 16 Zeichen
    "remaining_steps_estimate": 2,     # was der Planner noch erwartet (-1 falls unbekannt)
}
```

*Wie sieht `action` aus?* — Ein String im Format `<executor>:<ziel>:<capability>`:
- `"openfang:brain-coder:code_review"` — an OpenFang-Agent brain-coder delegiert
- `"supabase:bubble.create"` — DirectExecutor auf Supabase
- `"direct:mymodule:myfunc"` — sonstiger DirectExecutor

Das erlaubt KuroGraph, Actions als String-Tokens zu behandeln — genau wie im Klotski-Setup
mit int-Actions, aber jetzt lesbar.

*Wie kommt `reward` zustande?* — Eine schlichte Heuristik pro Hop:
- `+1.0` wenn ein `truth:`-Validator angesetzt war und passed
- `+0.5` wenn Hop non-empty result lieferte aber kein truth:-Check
- `-0.5` wenn empty/None zurückkam
- `-1.0` wenn Exception

Das ist ein grober Anfang; Phase 5 verfeinert es mit echtem User-Feedback.

*Wann ist `done=True`?* — Wenn drei Bedingungen gleichzeitig zutreffen:
1. Es ist der letzte Hop im Plan
2. Wenn ein truth:-Validator dran hing, hat er passed
3. Es sind keine weiteren Hops nach diesem in die Queue geschoben worden

Diese Definition ist essentiell — KuroGraph unterscheidet Erfolgsende von Abbruch.

**Wann ist es fertig?**

- ✅ Phase-0-Test B (der Gap dokumentiert) wird nach Phase 1 rot → **umflippen** und ab jetzt grün heißt „Ingest funktioniert"
- ✅ Neuer End-to-End-Test: 3-Hop-Mock-Plan schreibt 3 BrainEvents, letzter hat `done=True`
- ✅ Manueller Sanity-Check: Brain-Server starten, 5 echte Multihop-Requests fahren, `dual_graph.kotlingraph.get_statistics()` zeigt non-zero events

**Deliverables:**
- `core/multihop_kotlin_adapter.py` — neu, ~80 LOC
- `core/plan_executor.py` — 3× je 2-3 Zeilen Hook (an Zeilen 347, 1016, 1383)
- `web/brain_server.py` — 1 Zeile State-Wiring
- `tests/test_multihop_kotlin_ingest.py` — neu

**Risiko + Mitigation:** Latenz im Hot-Path. Aber KotlinGraph-Write ist in-memory
(networkx.MultiDiGraph = sehr cheap), Persistenz ist explicit `dual_graph.save(...)`,
nicht per-Event. Falls die Graph zu groß wird (bei sehr vielen Hops/min): FIFO-Eviction
bei 50k Events einbauen.

**Aufwand:** ~0.5 Tag, ~150 LOC inklusive Tests.

---

## Phase 2 — Ähnliche Tasks gruppieren (Task-Class-Clustering)

**Was mache ich?**
Jede Task bekommt eine `task_class_id` — semantisch ähnliche User-Anfragen landen
unter derselben ID. Damit KuroGraph seine Muster **innerhalb einer Klasse** mint
und nicht wild alle Traces vermischt.

Konkret: neues Modul `core/task_class_clusterer.py` mit einer Methode `cluster_id(user_text)`:
- Wandelt `user_text` in ein 1024-dim Embedding (Qwen3, **wiederverwendet** aus dem existierenden `qdrant_kg.py`-Singleton — bloß nicht doppelt laden!)
- Sucht in einer Qdrant-Collection `brain-task-classes` per Cosine-Similarity
- Wenn Top-Match > 0.85 Ähnlichkeit → existierende task_class_id
- Wenn nicht → neue UUID, neue Task-Class angelegt

**Warum jetzt?**
Weil Phase 1 nur Events sammelt — aber ohne Klassifizierung mischt sich „Docker Review",
„Bubble Create" und „Web Research" in einem Topf. KuroGraph findet dann nur schwache
Muster („mach mal irgendwas mit einem Agent"). Erst wenn ich Klassen habe, kann
das System sagen: „für **diese Art von Task** ist die optimale Sequenz X".

**Wann ist es fertig?**

- ✅ 3 semantisch ähnliche Anfragen (`"review my docker setup"`, `"kannst du das docker image checken"`, `"look at this docker container"`) → **eine** gemeinsame task_class_id
- ✅ Völlig andere Anfrage (`"erstelle eine bubble"`) → **andere** task_class_id
- ✅ Qdrant-Collection `brain-task-classes` überlebt Brain-Restart (Persistenz)

**Deliverables:**
- `core/task_class_clusterer.py` — neu, ~120 LOC
- `core/kotlin_graph.py` — ~20 LOC für neuen Index `task_class_index: Dict[str, List[int]]`
- Adapter aus Phase 1 erweitert um ~10 LOC (übergibt user_text, setzt task_class_id ins BrainEvent-metadata)
- `tests/test_task_class_clusterer.py`

**Risiko + Mitigation:** Wenn ein zweites Embedder-Modell geladen würde, sind ~3GB VRAM
weg. **Zwingend** den Qwen3-Singleton aus `core/qdrant_kg.py` wiederverwenden — im
Modul explizit importieren, nie `SentenceTransformer(...)` mit dem gleichen Model neu instanziieren.

**Aufwand:** ~1 Tag, ~200 LOC inkl. Tests.

---

## Phase 3 — Prüfen ob Muster wirklich emergieren (Validierung)

**Was mache ich?**
Ich fahre ~50 echte Multihop-Requests über 3 unterschiedliche Task-Klassen und
checke: mined KuroGraph darin überhaupt sinnvolle Muster?

Konkret: ein Integration-Test der 50 Requests durchspielt, dann `dual_graph.mine_patterns()`
aufruft, dann assertet: „für jede Task-Klasse gibt es mindestens ein Pattern mit
`success_rate > 0.7` und `frequency >= 3`".

Plus ein Read-Only-Endpoint `GET /api/brain/patterns?task_class=<id>` — dann kann
ich per curl in die gelernte Musterlisten reinschauen.

**Warum jetzt?**
Weil Phase 1+2 alleine Daten produzieren, aber ich noch keine Beweise habe dass
KuroGraph die auch sinnvoll auswertet. Bevor ich in Phase 4 auf Muster ROUTE, will
ich validiert haben dass Muster überhaupt da sind. Sonst bau ich einen Shortcut
zu Fantasie-Patterns.

Falls sich rausstellt dass Muster **nicht** emergieren (z.B. zu kurze n-grams, zu wenig
Wiederholung) → Tuning-Runde: `min_pattern_length` / `max_pattern_length` in KuroGraph
justieren.

**Wann ist es fertig?**

- ✅ Nach 50 Requests: für jede der 3 Task-Klassen mindestens 1 Pattern mit success_rate > 0.7
- ✅ `curl :5000/api/brain/patterns?task_class=<id>` liefert brauchbare JSON

**Deliverables:**
- `tests/integration/test_kuro_pattern_discovery.py`
- `web/routers/patterns.py` — neuer Read-Only-Endpoint, ~40 LOC

**Aufwand:** ~0.5 Tag, **kein Production-Code** — nur Test + Read-only-Endpoint.

---

## Phase 4 — Shortcut-Ausführung (User spürt Speedup)  ⭐ User-sichtbarer Win

**Was mache ich?**
Ich baue einen neuen Typ von execution_target: `kuro:pattern_<id>`. Wenn Brain im
Routing sieht dass für die Anfrage ein gutes Pattern existiert (success_rate > 0.8,
frequency >= 5) → **das** wird als execution_target gewählt statt normalem Multihop.

Konkret: neue Klasse `KuroPatternExecutor` in `core/capability_executor.py`, analog
zum bestehenden `DirectExecutor`. Sie lädt das Pattern aus KuroGraph, spielt die
Action-Sequenz Hop für Hop ab (jede action ist eh im Format `openfang:...` oder
`supabase:...`, wird also über die normalen Dispatchers gefahren) und returned das
Endergebnis.

Plus: Erweiterung in `core/capability_router.py`. Vor der normalen Regex-Suche
prüft der Router: „gibt es für die Task-Class dieser Anfrage ein gutes Pattern?"
Falls ja → candidate execution_target ist `kuro:pattern_<id>`. Falls nein → wie bisher.

Safety-Net: Config-Flag `KURO_SHORTCUT_ENABLED` (default `0` = aus). Musst du
manuell einschalten, damit du kontrolliert testen kannst dass nichts kaputtgeht.

**Warum jetzt?**
Das ist der Moment wo der User den ganzen Aufwand SPÜRT. Vorher war alles Datenerfassung
und Analyse ohne sichtbare Wirkung. Ab jetzt: gleiche Anfrage → messbar schneller,
weniger Round-Trips, weniger LLM-Token.

Fallback ist eingebaut: wenn ein Hop des Patterns fehlschlägt (reward < 0), springt
Brain zurück in die normale Multihop-Suche und Pattern-success_rate wird gedecayed.
Das Ding heilt sich also selbst wenn Muster veralten.

**Wann ist es fertig?**

- ✅ Mit `KURO_SHORTCUT_ENABLED=1`: der 51. Docker-Review-Request läuft mit **messbar weniger Hops** und **niedrigerer Latenz** als die ersten 50
- ✅ Mit `KURO_SHORTCUT_ENABLED=0`: Verhalten **identisch** zu heute (Regressionssicherheit)
- ✅ Fallback-Test: künstlich kaputtes Pattern → Brain merkt Fehler, fällt auf normale Route zurück, Pattern.success_rate sinkt

**Deliverables:**
- `core/capability_executor.py` — erweitert um `KuroPatternExecutor`
- `core/capability_router.py` — Pre-Check vor Regex-Routing
- `tests/test_kuro_shortcut.py` (positive path)
- `tests/test_kuro_shortcut_fallback.py` (recovery path)

**Risiko + Mitigation:** Stale Patterns — die Umgebung ändert sich (Agent X wird
umbenannt, Tool Y ist weg), Pattern spielt tote Sequenz. Zwei Schichten Schutz:
(a) TTL auf Pattern (z.B. 7 Tage seit letzter erfolgreicher Nutzung), (b) automatischer
Decay bei Fehlschlägen (nach 3 Fails fällt Pattern unter Threshold, wird nicht
mehr als Shortcut angeboten).

**Aufwand:** 1-2 Tage, ~250 LOC inkl. Tests.

---

## Phase 5 — User-Feedback verbessert die Muster (Hebbian in KuroGraph)

**Was mache ich?**
Das `/api/cortex/route/reward` API existiert schon — heute updated es nur die
Space-Centroide (die Grob-Routing-Ebene). Ich erweitere es so, dass es AUCH
KuroGraph-Pattern-Stats updated: wenn User sagt „diese Antwort war gut" →
Pattern success_rate hoch. Wenn „schlecht" → runter.

**Warum jetzt?**
Weil das die Rückkopplung schließt. Phase 1's reward-Heuristik (`+1.0` bei
truth:-Validator, `-0.5` bei empty result) ist grob — sie approximiert ob der
Hop TECHNISCH erfolgreich war. Aber ob der User zufrieden ist, weiß nur der User.
Diese Phase überträgt User-Zufriedenheit auf die gelernten Patterns.

Damit gilt ab jetzt: Patterns die User-mäßig gut ankommen, überleben und werden
öfter genommen; Patterns die zwar technisch funktionieren aber schlechte Antworten
liefern, werden gedecayed.

**Wann ist es fertig?**

- ✅ Reward-API zeigt messbare Pattern-Stat-Änderung nach Aufruf
- ✅ Decay funktioniert: 3 aufeinanderfolgende Fails → Pattern fällt unter Shortcut-Threshold, wird von Phase 4 nicht mehr als candidate angeboten

**Deliverables:**
- `web/routers/routing.py` — ~30 LOC Erweiterung im Reward-Handler
- `core/kuro_graph.py` — neue Methode `record_outcome(pattern_id, success: bool)` ~20 LOC
- `tests/test_routing_reward_kuro.py`

**Aufwand:** ~0.5 Tag.

---

## Phase 6 — Aufräumen (optional, eigener Branch)

**Was mache ich?**
Die Klotski-spezifischen Environment-Dateien (PPO-Trainer, Puzzle-Boards,
Solver-Regeln) haben in `learning_engine/klotski/neurosymbolic/environments/`
und `training/` nichts mehr zu suchen — sie sind Puzzle-Spezialkram, kein
Routing-Hirn. Die generalisierten Memory-Strukturen sind ja bereits in `core/`.

Ich verschiebe:
- `learning_engine/klotski/neurosymbolic/environments/` → `vibemind-os/spaces/klotski/environments/`
- `learning_engine/klotski/neurosymbolic/training/` → `vibemind-os/spaces/klotski/training/`
- `learning_engine/klotski/neurosymbolic/symbolic/allis_rules.py` → `vibemind-os/spaces/klotski/symbolic/`

Dann Imports updaten und Tests laufen lassen.

**Warum jetzt (oder eher: warum überhaupt)?**
Weil `brain/the_brain/learning_engine/` ~14k LOC hat, die überwiegend puzzle-spezifisch
sind. Das Routing-Hirn wird schlanker und klarer, wenn nur die generalisierten
Bits übrig bleiben. Kein funktionaler Zwang — daher: **optional**.

Parallelizierbar mit Phase 5. Wenn du keine Zeit hast, kann's warten.

**Wann ist es fertig?**

- ✅ Alle Tests grün, keine Import-Brüche
- ✅ `learning_engine/klotski/.../environments/` ist verschwunden
- ✅ `spaces/klotski/` hat den Klotski-Solver

**Aufwand:** ~0.5 Tag, viele kleine Datei-Verschiebungen.

---

## Die Roadmap auf einen Blick

```text
Tag 1                     Tag 2-3                  Tag 4-5
──────────────────────────────────────────────────────────────
Phase 0   Phase 1         Phase 2      Phase 3     Phase 4          Phase 5
Safety-   Ingest          Cluster      Sanity      Shortcut         Feedback
Netz      Tagebuch                     -Check      (User spürt      loop
1-2h      0.5d            1d           0.5d        Speedup)         0.5d
▓         ▓▓▓▓            ▓▓▓▓▓▓▓▓     ▓▓▓▓        1-2d ▓▓▓▓▓▓▓▓▓▓  ▓▓▓▓
│         │               │            │           │                │
▼         ▼               ▼            ▼           ▼                ▼
Tests     BrainEvents     task_class   50 test-    kuro:pattern     Reward-API
grün      fließen         _id im       runs +      _<id>            updated
          in Kotlin-      Metadata     KuroGraph   Executor         KuroGraph
          Graph                        mined                        stats
                                       Patterns
                                                                    Phase 6
                                                                    Cleanup
                                                                    (optional,
                                                                    parallel)
                                                                    0.5d
```

**Notausstieg:** Wenn zwischendurch die Zeit ausgeht — nach **Phase 0+1** (~2 Tage)
hast du bereits echte Task-Traces im KotlinGraph. Alle weiteren Phasen können jederzeit
in einer zweiten Session nachgezogen werden, die Daten sammeln sich schon.

---

## Implementierungs-Reihenfolge (TL;DR)

| Phase | Aufwand | Wert | Abhängigkeit |
|---|---|---|---|
| 0 — Safety-Net | 1-2h | Vorbereitung | — |
| **1 — Ingest (Tagebuch)** | **0.5d** | **größter Hebel** | Phase 0 |
| 2 — Task-Class-Cluster | 1d | mittel | Phase 1 |
| 3 — Pattern-Sanity | 0.5d | Validierung | Phase 2 |
| **4 — Shortcut (Speedup)** | **1-2d** | **User-sichtbar** | Phase 3 |
| 5 — User-Feedback-Loop | 0.5d | klein, aber kritisch | Phase 4 |
| 6 — Aufräumen | 0.5d | optional | parallel möglich |

**Gesamt:** ~4-5 Tage für Phasen 0-5.

---

## 5 Entscheidungen die du treffen musst (bevor wir anfangen)

Für jede Entscheidung: zwei Optionen und meine Empfehlung. Ich mache das was du sagst.

### 1. Wie oft soll der Graph auf Disk gespeichert werden?

- **A)** Nur beim expliziten `save()` (heutiger Zustand) → einfach, aber bei Brain-Crash sind die letzten Traces weg
- **B)** Alle 5min automatisch via brain-loops sidecar → 5min-Verlustfenster maximal, kostet ein bisschen IO

**Meine Empfehlung: B** — Multihop-Traces sind zu wertvoll um sie bei Crash zu verlieren. IO-Kost minimal.

### 2. Wie groß darf das Tagebuch werden?

- **A)** Unbegrenzt in-memory → wächst irgendwann und frisst RAM
- **B)** FIFO-Evict bei 100k Events → älteste Events fliegen raus wenn Cap erreicht
- **C)** Disk-Spillover: heiße 10k in-memory, Rest auf Disk → komplex

**Meine Empfehlung: B** mit `MAX_EVENTS=100_000` als Config-Flag. Bei production-volume ~50k/Tag sind 100k = 2 Tage Rolling-Window. Für Pattern-Mining ausreichend. C ist Over-Engineering.

### 3. Was passiert wenn eine Task-Klasse semantisch driftet?

Beispiel: „Docker review" hieß früher „check for bugs", heute meint der User „check for supply-chain vulnerabilities".

- **A)** Zentroid wandert automatisch mit (moving average) — konservativ, Klasse bleibt
- **B)** Bei großem Drift (Varianz-Check) automatisch neue Klasse abspalten → präzisere Patterns, aber komplexer
- **C)** Manuell: Alert im Dashboard wenn Drift-Score > Threshold, User entscheidet

**Meine Empfehlung: A** für die ersten 3 Monate — einfach. Falls es unterspezifische Cluster gibt → auf B upgraden. C ist zu manuell.

### 4. Was landet konkret im Tagebuch — Klartext oder Hash?

- **A)** Raw `user_text` in `BrainEvent.state` — leichter zu debuggen, aber PII-Risk falls VibeMind shared/cloud läuft
- **B)** Nur `context_hash = SHA256(user_text)[:16]` — anonymer, aber schwerer zu debuggen

**Meine Empfehlung: B** — Hash speichern, in einem separaten dev-only Log optional den Klartext. Falls VibeMind je in die Cloud geht → keine nachträgliche Migration nötig.

### 5. Soll Brain Shortcuts automatisch nehmen oder erst fragen?

- **A)** Bei `success_rate > 0.8` automatisch die Shortcut-Sequenz spielen → schnell, User merkt nichts außer Speedup
- **B)** User bekommt vor Shortcut-Ausführung eine Approval-Frage → sicherer, aber killt die UX

**Meine Empfehlung: A** — mit dem eingebauten Fallback (bei Hop-Fehler zurück zur Normalroute + Decay). Sonst werden Shortcuts nie aktiv genutzt und die ganze Arbeit ist umsonst.

---

## Fazit — die 3 Sätze zum Mitnehmen

1. **Die Klotski-Memory-Struktur ist schon domain-agnostic geportet in `core/`** — das war die schwere Vorarbeit, die ist schon geschafft.
2. **Alles was jetzt fehlt ist der Schreibpfad** (`plan_executor.py` → KotlinGraph) und der Lese-Pfad (KuroGraph-Pattern → execution_target `kuro:pattern_<id>`).
3. **Phase 0+1 (2 Tage Arbeit)** reichen für den kritischen Sprung: ab dann fließen echte Task-Traces ins Tagebuch. Alles Weitere ist Ausbau der schon rollenden Datenerhebung.

---

## Erweiterung: Vereinheitlichte Schwierigkeit — gemessen statt geraten

**Datum der Ergänzung:** 2026-07-01. Bringt den bestehenden `difficulty_router`
(a-priori-Vorhersage) und diese Memory-Bridge (a-posteriori-Messung) in **ein**
Konzept zusammen.

### Das Problem mit dem heutigen Difficulty-Begriff

Heute stuft [`core/difficulty_router.py`](../../core/difficulty_router.py) einen
Intent **vor** der Ausführung per Qwen-Cosine gegen ~50 handkuratierte Anker in
`easy/medium/hard/insane` ein und wählt damit den Handler
(`chat/shortcut/som/autogen`). Das beantwortet **„wie schwer sieht das aus?"** —
eine Vorhersage aus der Text-Oberfläche, ohne Ground-Truth. Sie ist brüchig:
fehlt ein Anker für eine Formulierung, fehl-routet der Intent (der ganze Sinn der
`_min_cos`-Schwelle + der `medium`-Rückfall ist Schadensbegrenzung dafür).

### Der neue Difficulty-Begriff

**Schwierigkeit = wie viele Hops es tatsächlich brauchte, um das Ziel
abzuschließen (`done=True`).** Das beantwortet **„wie schwer hat es sich
erwiesen?"** — gemessen, geerdet, selbstkorrigierend. Und es ist exakt die Zahl,
die Phase 1 (das KotlinGraph-Tagebuch) ohnehin schon pro Hop erfasst. Wir addieren
kein System; wir lesen eine Zahl aus, die das Tagebuch bereits enthält.

**Difficulty und Shortcut sind derselbe Lookup:** Das in Phase 4 gesuchte Pattern
*ist* der Beweis, wie viele Hops nötig waren. `difficulty(task_class)` ist also
ein Nebenprodukt des Task-Class-Lookups aus Phase 2 — kein eigener Klassifikator.

### Entschiedene Weichen (2026-07-01)

1. **Metrik = Median.** `measured_difficulty` einer Task-Class = p50 der Hop-Zahlen
   **nur erfolgreicher** Läufe (`done=True`). Robuster gegen Ausreißer als „min",
   spiegelt den realistischen Normalfall statt eines Glücks-Laufs. `hop_count_min`
   wird zusätzlich mitgeführt (informativ / spätere Optimalpfad-Auswertung), ist
   aber nicht die Routing-Zahl.
2. **Kaltstart = Qwen-Cosine als Bootstrap-Prior.** Für eine völlig neue
   Task-Class (kein Profil) liefert der bestehende `difficulty_router` **den ersten
   Lauf** die Schätzung. Danach wird sie von der Messung überschrieben. Der Router
   wird damit vom „Türsteher" zum „Kaltstart-Rater" degradiert — seine Brüchigkeit
   hört auf zu zählen, weil sie selbstkorrigierend ist.

### Neuer Routing-Kern (rewire in `multihop_execute`)

```
intent
  │  task_class_id = clusterer.cluster_id(intent)        [Phase 2]
  │  profile       = task_class_store.get(task_class_id)
  ▼
  ├─ bewiesenes Pattern (success_rate>0.8, frequency>=N)
  │     difficulty = profile.measured_difficulty (p50)   ← GEMESSEN
  │     route      = kuro:pattern_<id> abspielen          [Phase 4]
  │
  ├─ Profil da, Pattern noch schwach (am Lernen)
  │     difficulty = laufender Median der bisherigen Episoden
  │     route      = nach gemessenem Band                 [normaler Multihop]
  │     + weiter MESSEN (Phase-1-Ingest)
  │
  └─ KEIN Profil (Kaltstart, neue Task-Class)
        difficulty = difficulty_router.classify(intent)  ← Bootstrap-Prior, nur 1×
        route      = nach geschätztem Band
        + Profil anlegen, diesen Lauf MESSEN → Schätzung ersetzen
```

Nach jedem Lauf: echte Hop-Zahl (bei `done=True`) in `profile` einrechnen →
`measured_difficulty` neu berechnen. Die Qwen-Schätzung wird pro neuer Task-Class
nur **einmal** benutzt.

### Was aus den vier Band-Namen wird

`easy/medium/hard/insane` überleben als **Telemetrie-/Anzeige-Labels**, nicht mehr
als Routing-Primärlogik. Routing wird ein Spektrum: *Pattern vorhanden → abspielen;
sonst → planen, messen, merken.* Ein Mapping Hop-Zahl → Band (config-basiert, z.B.
`0→easy, 1→medium, 2-4→hard, 5+/divergent→insane`) bleibt nur für Dashboards +
Kaltstart-Kompatibilität mit dem alten Router.

### Touch-Points in den bestehenden Phasen (kein neuer Baustein)

- **Phase 2** (`task_class_clusterer.py` / `brain-task-classes` Collection): Profil
  um `measured_difficulty`, `hop_count_min`, `hop_count_p50`, `n_episodes`,
  `last_seen` erweitern. ~30 LOC zusätzlich.
- **Phase 1** (`multihop_kotlin_adapter.py`): beim finalen Hop (`done=True`) die
  Hop-Zahl des Laufs an die Task-Class-Profil-Aktualisierung übergeben. ~10 LOC.
- **Phase 4** (Routing-Pre-Check in `capability_router.py`): den Pre-Check so
  bauen, dass er **denselben** Profil-Lookup nutzt, der auch die Difficulty liefert
  — Difficulty und Shortcut-Entscheidung aus einer Quelle.
- **`difficulty_router.get_router().classify()`**: unverändert, aber nur noch im
  Kaltstart-Zweig aufgerufen.

### Offene Detail-Entscheidung (für die Umsetzung)

- **Band-Schwellen Hop-Zahl → Label**: Startwerte oben sind ein Vorschlag; ggf.
  aus den Perzentilen aller Task-Classes lernen statt fest verdrahten.
- **`N` (frequency-Schwelle) + Mindest-`n_episodes`**, ab wann `measured_difficulty`
  den Bootstrap-Prior ablöst (Vorschlag: ab `n_episodes >= 3`, konsistent mit dem
  Phase-3-Sanity-Kriterium `frequency >= 3`).

---

## Referenzen

- [`docs/ARCHITECTURE.md`](../../../../docs/ARCHITECTURE.md) — Top-Level VibeMind-Architektur
- [`infra/swarm/profiles/brain.md`](../../../../infra/swarm/profiles/brain.md) — Brain-Profile-Doc
- [`infra/swarm/profiles/tribe.md`](../../../../infra/swarm/profiles/tribe.md) — TriBE-Profile (separate Memory-Schicht, parallel zu KuroGraph)
- [`vibemind-os/brain/the_brain/docs/TRANSFER_LEARNING_IMPLEMENTATION_SUMMARY.md`](../TRANSFER_LEARNING_IMPLEMENTATION_SUMMARY.md) — Vorhandene Doku zu Puzzle-Agent-Mapping
- [`vibemind-os/brain/the_brain/docs/QUANTUM_CHECKPOINT_LEARNING_COMPLETE.md`](../QUANTUM_CHECKPOINT_LEARNING_COMPLETE.md) — Vorhandene Doku zum Checkpoint-System
- Memory-Eintrag [`project_routing_matrix_autotrain`](../../../../C:/Users/User/.claude/projects/c--Users-User-Desktop-Vibemind-V1/memory/project_routing_matrix_autotrain.md) — bestehender shortcut-Mechanismus, erweitert in Phase 4
