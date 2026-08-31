# Phase-1 Live-Beweis — Protokoll

**Datum:** 2026-07-13
**Ziel:** Beweisen, dass die committete Phase-1-Kette (Hop-Lernsignale → episodisches Tagebuch) im **echten Serverprozess** funktioniert — nicht nur in pytest. Komponenten-grün ≠ echter Lauf.

---

## Setup (und warum nativ, nicht Container)

**Befund vor dem Beweis:** Brain `:5000` ist normalerweise ein **Swarm-Container**
(`brain-core`, Image `vibemind-brain-core:latest`, publiziert `5000:5000`,
`infra/swarm/vibemind-stack.yml:68-78`). Docker Desktop war aus, der Stack unten.
Der neue Code liegt im Working-Tree — das Container-Image hätte ihn **nicht**.

**Entscheidung:** Brain nativ aus `.venv` über den kanonischen Entrypoint gestartet
(`python start_server.py 5000` — derselbe Befehl, den der Container ausführt; lädt
`.env` selbst). Port `:5000` war frei, weil der Stack unten war. Kein Docker-Rebuild,
kein Stack-Deploy — die dokumentierten Fallen (Docker-Start-Crash, `:latest` rollt
nicht neu, DNS-Races, Orphans, RAM) wurden bewusst umgangen.

---

## Rohdaten

### 1. Baseline — Tagebuch vor dem Lauf

```json
GET /api/diary/stats  →  200
{
  "total_events": 4254,
  "total_episodes": 3,
  "multihop_events": 0,
  "current_episode_id": 3,
  "last_event": {"action": "explore", "done": false, "reward": 0.5,
                 "plan_id": null, "episode_success": null}
}
```

**Zwei Beweise schon hier:**
- Der Endpoint antwortet `200` → der **neue Code läuft** (Task 1), und
  `attach_dual_graph` **wurde beim Boot aufgerufen** (sonst hätte der Handler `503`
  geliefert). Das Boot-Wiring ist live verifiziert.
- **`multihop_events: 0`** bei 4254 Gesamt-Events → die Phase-1-Prämisse ist
  **empirisch bestätigt**: das Tagebuch war voll kortikaler Events
  (`action: "explore"`, `plan_id: null`), enthielt aber **null Task-Hops**.

### 2. Echter Multihop-Lauf

```
POST /api/multihop/execute  {"intent": "erstelle eine bubble namens Phase1-LiveProof"}

ok:         False
plan_id:    plan_eb5d1b13eb        <-- TOP-LEVEL (MH-5a)
trace_id:   tr_2a9f91f0f94d
hops:       1
  s1: ok=False  cap=bubble_create  target=supabase:bubble.create
      contract_pass=False  reward=-1.0  validator_verdict=None
final_text: "The attempt to create a bubble named "Phase1-LiveProof" was unsuccessful..."
```

Der Hop **scheitert echt**: `supabase:bubble.create` ist unerreichbar, weil Supabase
im ausgeschalteten Swarm-Stack liegt. Das ist kein Testartefakt — es ist ein echter
Fehlschlag, und genau deshalb wertvoll (siehe unten).

### 3. Tagebuch nach dem Lauf

```json
GET /api/diary/stats  →  200
{
  "total_events": 4255,          // +1
  "total_episodes": 4,           // +1  (Episode geschlossen)
  "multihop_events": 1,          // 0 -> 1   ***
  "current_episode_id": 4,
  "last_event": {
    "action": "supabase:bubble.create:bubble_create",
    "done": true,
    "reward": -1.0,
    "plan_id": "plan_eb5d1b13eb",
    "episode_success": false
  }
}
```

---

## Was damit BEWIESEN ist

| Baustein | Beweis im Live-Lauf |
|---|---|
| **Task 1** — Diary-Endpoint | antwortet `200` mit korrekten Zählern |
| **Boot-Wiring** (`attach_dual_graph`) | kein `503` → das DualGraph hängt am PlanExecutor |
| **MH-5a** — `plan_id` top-level | `plan_eb5d1b13eb` in der Response, **nicht** nur nested |
| **T1** — Hop-Lernsignale | `contract_pass=False`, `reward=-1.0` beim harten Fehler |
| **T1-Review-Fix** (6 ok=False-Sites) | der Fehlschlag liefert **-1.0**, **nicht** neutral `0.0` — genau der Bug, den der Code-Quality-Reviewer erzwang, **in Produktion widerlegt** |
| **T2** — Adapter-Ingest | `multihop_events` **0 → 1** |
| **Action-Format** | `kind:rest:capability` = `supabase:bubble.create:bubble_create` |
| **Episode-Grenze** | `done: true`, `total_episodes` 3 → 4 |
| **KG-C3** — `episode_success` | `false` — die Regel urteilt korrekt (gescheiterter letzter Hop ist **nicht** vakuum-erfolgreich) |
| **Korrelation** | `last_event.plan_id` == `plan_id` aus der Execute-Response |

**Der wertvollste Zufall:** Weil Supabase unten war, bewies der Lauf ausgerechnet den
**Fehlerpfad** — und der ist der, den das Review-Feedback repariert hat. Hätte der Hop
funktioniert, wäre die schwächere Aussage `reward=+1.0` herausgekommen.

## Was damit NICHT bewiesen ist (ehrlich)

1. **Positiver Reward-Pfad**: kein Hop mit `contract_pass=True`/`reward=+1.0` lief —
   dafür braucht es ein erreichbares Supabase (also den Stack). Die truth-Validatoren
   aus Task 3 (Coverage 22→27) wurden **nicht live gefeuert**.
2. **Container-Deployment**: der Beweis lief nativ. Das Image
   `vibemind-brain-core:latest` enthält den neuen Code **noch nicht** — beim nächsten
   Stack-Deploy muss es neu gebaut werden.
3. **Episode-Grenze zwischen zwei Plänen**: nur ein Plan wurde ausgeführt. Der zweite
   Lauf lief in einen Timeout (siehe unten).
4. **Task-Class-Clustering** (Task 4): default OFF (`TASK_CLASS_CLUSTERING=0`), also
   im Lauf nicht aktiv — bewusst so.
5. **auto_mine-Cadence** (Task 2, 10→200): nicht direkt gemessen; der Boot zeigte
   allerdings einen Mining-Pass beim Laden des persistierten Graphen
   (`Auto-mining patterns (episode 3)... Found 169 n-grams, 7 strategies`).

## Nebenbefund: Brain degradiert ohne Stack

Nach dem zweiten Request wurde Brain **unresponsiv** (Timeouts). **Kein Crash** — der
Prozess lauschte weiter auf `:5000` (PID 23620). Ursache: sämtliche Abhängigkeiten
liegen im ausgeschalteten Stack — Qdrant (`:6333`), unified brain (`:5003`), Supabase —
also läuft er in Retry-Schleifen (`WinError 10061`, Verbindung verweigert) **plus**
CPU-Embedder (der Difficulty-Router encoded pro Request, 1-5s laut Log). Erwartete
Degradation eines nativen Brain ohne Stack, kein Defekt des neuen Codes.

Der native Prozess wurde nach dem Beweis **gestoppt**, damit er nicht mit dem
Swarm-Stack um `:5000` kollidiert (der Launcher nennt den Stack explizit als Eigentümer).

## Nächste Schritte daraus

- Beim nächsten regulären Stack-Deploy: `vibemind-brain-core` neu bauen, damit der
  Phase-1-Code ins Image kommt. Danach ist der **positive** Reward-Pfad live prüfbar
  (Supabase erreichbar → truth-Validator feuert → `contract_pass=True`, `reward=+1.0`).
- Bis dahin gilt: Phase 1 ist **live bewiesen für Ingest, Signale und Fehlerpfad**;
  der Erfolgspfad ist nur test-grün, nicht live.
