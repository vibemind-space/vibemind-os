# Tagebuch-Queue + Drain — Live-Beweis im Swarm

**Datum:** 2026-07-14
**Ziel:** Beweisen, dass Multihop-Episoden im **produktiven Swarm** überleben — nicht nur in pytest, nicht nur in einem nativen Einzelprozess.

---

## Ausgangslage (der Befund, der diesen Umbau ausgelöst hat)

Gemessen, nicht vermutet:

| # | Befund | Beleg |
|---|---|---|
| 1 | brain-core läuft mit **2 uvicorn-Workern** → zwei getrennte In-Memory-Tagebücher | derselbe Endpoint lieferte erst `multihop_events: 1`, dann `0` |
| 2 | brain-core setzt `BRAIN_BACKGROUND_LOOPS=0` → `MemoryConsolidator` startet nie → **dort speichert niemand** | Boot-Log `[SKIP] MemoryConsolidator` |
| 3 | Swarm ersetzt brain-core-Tasks → das RAM-Tagebuch **verdampft** | `10671 → 0` nach Task-Replace |
| 4 | brain-loops (der einzige Saver) hat ein **eigenes** DualGraph und sieht nie einen Hop | 49 Events auf Disk, **0 multihop** |
| 5 | `GROUND_TRUTH_ENABLED` war **nirgends gesetzt** (Default OFF) → jeder truth-Validator lieferte `verified=None` → **jeder Reward 0.0** | `core/world_observer.py:43` |

**In einem Satz:** *Die Hops entstanden im Prozess, der nicht speichert; der Prozess, der speichert, sah die Hops nie — und selbst wenn, wäre jeder Reward 0.0 gewesen.*

## Was deployed wurde

- Image `vibemind-brain-core:latest` neu gebaut (`abbd233f6d52`) — enthält Queue, Drain, atomare Persistenz, Diary-Endpoint (alle vier im Image verifiziert).
- `docker stack deploy` (nie `service update` — das räumt den Stack ab).
- Stack: `GROUND_TRUTH_ENABLED=1` auf brain-core.

---

## Rohdaten

### Nullpunkt (neuer Code live, sauberer Start)

```json
GET /api/diary/stats
{
  "total_events": 315, "multihop_events": 0,
  "queue": {"episodes_enqueued": 0, "episodes_drained": 0, "skipped": 0,
            "pending": 0, "last_plan_id": null,
            "path": "/app/data/multihop_diary_queue.jsonl"},
  "enqueue": {"ok": 0, "failures": 0}
}
```

`queue.path` zeigt ins **geteilte Volume** — dieselbe Datei, die brain-loops drainiert.
(Dass der `queue`-Block überhaupt existiert, ist zugleich der Beweis, dass der neue Code läuft.)

### 1. Echter Multihop-Lauf — der positive Pfad, erstmals

```
POST /api/multihop/execute  {"intent": "erstelle eine bubble namens QueueProof"}

ok: True
plan_id: plan_b3e4c5ee0f
  s1: ok=True  cap=bubble_create
      contract_pass=True   reward=1.0
      verdict={'kind': 'truth:supabase_row', 'verified': True,
               'reason': 'ground-truth VERIFIED: supabase: row present (expected present)',
               'verify_signal': {'table': 'ideas', 'match': 'id=eq.9ae970f0',
                                 'expect': 'present', 'rows_found': 1}}
```

Der truth-Validator hat **real gefeuert**: eine **unabhängige Supabase-Re-Query**, die die geschriebene Zeile tatsächlich vorfand (`rows_found: 1`). Das ist das **erste positive Lernsignal, das dieses System je erzeugt hat** — vorher war `GROUND_TRUTH_ENABLED` aus und jeder Reward `0.0`.

### 2. Queue — brain-core hängt an, brain-loops drainiert

```
enqueued=1   drained=1   pending=0   skipped=0
last_plan_id=plan_b3e4c5ee0f
enqueue: ok=1  failures=0
```

Die Episode floss über die **Container-Grenze**. Die Identität stimmt: `enqueued(1) = drained(1) + skipped(0) + pending(0)`.

### 3. Persistiert — im brain-loops-Container (dem einzigen Saver)

```
events auf Disk:  317
davon multihop:   1        <-- vorher IMMER 0
  action=supabase:bubble.create:bubble_create
  plan_id=plan_b3e4c5ee0f   reward=1.0   done=True   episode_success=True
```

Die **erste Multihop-Episode, die je auf Platte landete**.

### 4. Der eigentliche Test — überlebt sie einen Neustart?

```
docker service scale vibemind_brain-core=0
docker service scale vibemind_brain-core=1
  verify: Service vibemind_brain-core converged
```

Danach:

```
multihop-Episoden auf Disk: 1
plan_b3e4c5ee0f: UEBERLEBT
  reward=1.0   done=True   episode_success=True
```

**Genau der Vorgang, bei dem das System heute jede Episode verliert** — die Episode ist unversehrt.

---

## Was damit bewiesen ist

| Baustein | Beweis |
|---|---|
| **Ground Truth scharf** | truth-Validator feuerte, unabhängige Re-Query, `rows_found: 1` |
| **Positiver Reward** | `contract_pass=True`, `reward=+1.0` — erstmals live |
| **Queue über Prozessgrenzen** | brain-core (2 Worker) hängt an, `enqueued=1`, `failures=0` |
| **Drain über Container-Grenzen** | brain-loops drainierte: `drained=1`, `pending=0` |
| **Persistenz** | Episode auf Platte, `multihop`-Events 0 → 1 |
| **Restart-Sicherheit** | brain-core zerstört+neu erzeugt → Episode **unversehrt** |
| **Ehrliche Zähler** | `enqueued = drained + skipped + pending` geht auf |

## Was NICHT bewiesen ist (ehrlich)

1. **Nur EIN Plan, ein Hop.** Mehrhop-Pläne, parallele Pläne und die Episoden-Reinheit unter echter Last sind test-grün, aber nicht live durchgespielt.
2. **brain-loops wurde nicht neu gestartet.** Der Restart-Test deckte brain-core ab (die dokumentierte Fehlerfunktion). Ein brain-loops-Neustart würde den Graphen von Platte neu laden — durch die atomare Persistenz erwartet unkritisch, aber nicht gemessen.
3. **Kein Fehlerpfad live.** `skipped`, `failures`, der Poison-Pill-Backstop und der Abort-Close sind test-bewiesen, nicht live provoziert.
4. **Keine Dauerlast.** Die Queue wächst unbegrenzt (Rotation bewusst vertagt); ab 100 MB warnt der Drain. Bei echtem Volumen zu beobachten.
5. **Coverage bleibt 27/66.** Die ~20 `openfang:`-Agent-Caps haben weiter keine Ground-Truth — ihre Hops liefern `reward=0.0` (UNVERIFIED). Das ist der nächste Engpass (§5.5).

## Nebenbefund: der Host

Der Image-Build riss beim ersten Versuch brain-core mit (Speicherdruck, ~90 Python-MCP-Prozesse fremder Sessions). Erst nach `docker builder prune -af` (**18,4 GB** freigegeben) lief er durch. Bei künftigen Builds: erst Cache räumen.
