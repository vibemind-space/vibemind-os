# Testplan: Brain → Bridge → OpenFang Routing

## Voraussetzungen

| Service | Port | Status prüfen |
|---------|------|--------------|
| Brain (Tahlamus) | 5000 | `curl http://localhost:5000/api/health` |
| Bridge | 5100 | `curl http://localhost:5100/bridge/health` |
| OpenFang | 4200 | `curl http://localhost:4200/api/health` |

---

## Level 0: Services einzeln starten & prüfen

### 0.1 Brain starten
```bash
cd brain/the_brain
# .venv aktivieren oder erstellen
pip install -r requirements-tahlamus.txt
# .env mit OPENROUTER_API_KEY erstellen (falls noch nicht vorhanden)
python web/brain_server.py
```
**Erwartung:** FastAPI auf Port 5000, `/api/health` antwortet.

### 0.2 OpenFang starten
```bash
cd openfang
cargo build --release -p openfang-cli
# Config kopieren (einmalig):
# cp openfang.vibemind.toml ~/.openfang/config.toml
ANTHROPIC_API_KEY=<key> target/release/openfang.exe start
```
**Erwartung:** API auf Port 4200, `/api/health` antwortet.

### 0.3 Bridge starten
```bash
cd bridge
PYTHONPATH=src .venv/Scripts/python -m uvicorn bridge.main:app --port 5100
```
**Erwartung:** FastAPI auf Port 5100, `GET /` zeigt Endpoints.

---

## Level 1: Isolierte Unit-Tests (kein externer Service nötig)

### 1.1 Space→Agent Mapping
```bash
cd bridge
PYTHONPATH=src .venv/Scripts/python -c "
from bridge.space_agent_mapper import load, map_space

load()
assert map_space('coding', 0.9) == 'brain-coder'
assert map_space('research', 0.8) == 'brain-researcher'
assert map_space('desktop', 0.7) == 'brain-devops'
assert map_space('ideas', 0.6) == 'brain-planner'
assert map_space('bubbles', 0.9) == 'brain-writer'
assert map_space('minibook', 0.9) == 'brain-writer'
assert map_space('agentfarm', 0.5) == 'brain-orchestrator'
assert map_space('n8n', 0.5) == 'brain-orchestrator'
assert map_space('schedule', 0.9) == 'brain-fallback'
assert map_space('unknown_space', 0.9) == 'brain-fallback'
assert map_space('coding', 0.1) == 'brain-fallback'  # unter min_confidence
assert map_space('coding', 0.29) == 'brain-fallback'
assert map_space('coding', 0.31) == 'brain-coder'
print('ALL 12 MAPPING TESTS PASSED')
"
```

### 1.2 Models Validierung
```bash
PYTHONPATH=src .venv/Scripts/python -c "
from bridge.models import BridgeRequest, BridgeResponse, RoutingInfo, TaskStatus

# Minimal request
r = BridgeRequest(task='test')
assert r.fire_and_forget == False
assert r.timeout_secs is None

# Full request
r = BridgeRequest(task='code', event_type='code.generate', fire_and_forget=True, timeout_secs=60)
assert r.event_type == 'code.generate'

# RoutingInfo
ri = RoutingInfo(primary_space='coding', confidence=0.9, routing_id='rt_abc123')
assert ri.secondary_spaces == []

# TaskStatus
ts = TaskStatus(task_id='123', status='pending')
assert ts.result is None

print('ALL MODEL TESTS PASSED')
"
```

### 1.3 Task Store
```bash
PYTHONPATH=src .venv/Scripts/python -c "
from bridge.task_store import create, update, get
from bridge.models import RoutingInfo

ri = RoutingInfo(primary_space='coding', confidence=0.9, routing_id='rt_test')
ts = create('task-1', ri, 'brain-coder')
assert ts.status == 'pending'
assert ts.agent == 'brain-coder'

update('task-1', 'working')
ts = get('task-1')
assert ts.status == 'working'

update('task-1', 'completed', result='Fibonacci function created')
ts = get('task-1')
assert ts.status == 'completed'
assert ts.result == 'Fibonacci function created'

assert get('nonexistent') is None
print('ALL TASK STORE TESTS PASSED')
"
```

---

## Level 2: Brain Routing (nur Brain muss laufen)

### 2.1 Brain direkt testen
```bash
curl -s -X POST http://localhost:5000/api/cortex/route \
  -H "Content-Type: application/json" \
  -d '{"user_text": "Erstelle eine Python Funktion", "event_type": ""}'
```
**Erwartung:**
```json
{
  "primary_space": "coding",
  "confidence": 0.7+,
  "routing_id": "rt_...",
  "latency_ms": <100
}
```

### 2.2 Verschiedene Domains testen
```bash
# Coding
curl -s -X POST http://localhost:5000/api/cortex/route \
  -d '{"user_text": "Fix the bug in authentication module"}'

# Research  
curl -s -X POST http://localhost:5000/api/cortex/route \
  -d '{"user_text": "Recherchiere aktuelle AI Agent Frameworks"}'

# Desktop
curl -s -X POST http://localhost:5000/api/cortex/route \
  -d '{"user_text": "Oeffne den Browser und navigiere zu GitHub"}'

# Ideas
curl -s -X POST http://localhost:5000/api/cortex/route \
  -d '{"user_text": "Ich habe eine Idee fuer ein neues Feature"}'
```
**Erwartung:** Jeweils passender Space mit confidence > 0.3.

### 2.3 Brain Reward testen
```bash
# Routing-ID aus Test 2.1 verwenden
curl -s -X POST http://localhost:5000/api/cortex/route/reward \
  -H "Content-Type: application/json" \
  -d '{"routing_id": "rt_XXXXXXXX", "success": true}'
```
**Erwartung:** `{"ok": true, "routing_id": "rt_XXXXXXXX"}`

### 2.4 Brain Stats prüfen
```bash
curl -s http://localhost:5000/api/cortex/route/stats
```
**Erwartung:** Centroid-Norms, total_routes > 0 nach Tests.

---

## Level 3: OpenFang Agent Lifecycle (nur OpenFang muss laufen)

### 3.1 Agents auflisten
```bash
curl -s http://localhost:4200/api/agents | python -m json.tool
```
**Erwartung:** Liste aller laufenden Agents (kann leer sein).

### 3.2 Brain-Agent spawnen
```bash
curl -s -X POST http://localhost:4200/api/agents \
  -H "Content-Type: application/json" \
  -d '{"template": "brain-coder"}'
```
**Erwartung:** `{"id": "uuid...", "name": "brain-coder", ...}`

### 3.3 Agent Message senden
```bash
# Agent-ID aus 3.2 verwenden
curl -s -X POST http://localhost:4200/api/agents/<AGENT_ID>/message \
  -H "Content-Type: application/json" \
  -d '{"message": "Say hello in 5 words."}'
```
**Erwartung:** Claude Code Antwort (verwendet claude-code/sonnet).

### 3.4 Alle 7 Brain-Agent Templates testen
```bash
for TEMPLATE in brain-coder brain-researcher brain-devops brain-planner brain-writer brain-orchestrator brain-fallback; do
  echo "=== Spawning $TEMPLATE ==="
  curl -s -X POST http://localhost:4200/api/agents \
    -d "{\"template\": \"$TEMPLATE\"}" | python -m json.tool
done
```
**Erwartung:** Alle 7 spawnen erfolgreich.

---

## Level 4: Bridge Integration (Bridge + Brain)

### 4.1 Health Check (alle Services)
```bash
curl -s http://localhost:5100/bridge/health
```
**Erwartung:** `{"bridge": "ok", "brain": "ok", "openfang": "ok"}`

### 4.2 Bridge Routing (Brain + OpenFang)
```bash
curl -s -X POST http://localhost:5100/bridge/route \
  -H "Content-Type: application/json" \
  -d '{"task": "Erstelle eine Fibonacci Funktion in Python"}'
```
**Erwartung:**
```json
{
  "task_id": "...",
  "status": "completed",
  "result": "... (Claude Code output mit Fibonacci Code) ...",
  "routing": {
    "primary_space": "coding",
    "confidence": 0.7+,
    "routing_id": "rt_..."
  },
  "agent": "brain-coder",
  "latency_ms": ...
}
```

### 4.3 Verschiedene Spaces durchrouten
```bash
# Research → brain-researcher
curl -s -X POST http://localhost:5100/bridge/route \
  -d '{"task": "Finde die besten Rust async frameworks 2025"}'

# Desktop → brain-devops
curl -s -X POST http://localhost:5100/bridge/route \
  -d '{"task": "Liste alle laufenden Prozesse auf Port 8080"}'

# Ideas → brain-planner
curl -s -X POST http://localhost:5100/bridge/route \
  -d '{"task": "Plane ein MVP fuer eine Todo App mit AI-Features"}'
```

### 4.4 Async (Fire-and-Forget) Mode
```bash
# Task absenden
RESPONSE=$(curl -s -X POST http://localhost:5100/bridge/route \
  -H "Content-Type: application/json" \
  -d '{"task": "Recherchiere OpenFang vs CrewAI vs AutoGen", "fire_and_forget": true}')
echo $RESPONSE

# Task-ID extrahieren und pollen
TASK_ID=$(echo $RESPONSE | python -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
echo "Polling task: $TASK_ID"

# Warten und Status abfragen
sleep 10
curl -s http://localhost:5100/bridge/tasks/$TASK_ID/status
```
**Erwartung:** Erst `status: pending`, dann `working`, dann `completed`.

### 4.5 Hot-Reload Mapping
```bash
# Aktuelles Mapping anzeigen
curl -s http://localhost:5100/bridge/mapping

# YAML editieren (z.B. coding → brain-fallback)
# Dann:
curl -s -X PUT http://localhost:5100/bridge/mapping/reload
```
**Erwartung:** Neues Mapping wird sofort aktiv.

---

## Level 5: Feedback Loop (Hebbian Learning)

### 5.1 Routing + Reward Zyklus
```bash
# 1. Brain Stats vorher
curl -s http://localhost:5000/api/cortex/route/stats > /tmp/stats_before.json

# 2. 5x Coding-Task routen (Bridge sendet automatisch Rewards)
for i in 1 2 3 4 5; do
  curl -s -X POST http://localhost:5100/bridge/route \
    -d "{\"task\": \"Write a Python function for task $i\"}"
  sleep 2
done

# 3. Brain Stats nachher
curl -s http://localhost:5000/api/cortex/route/stats > /tmp/stats_after.json

# 4. Vergleichen
echo "=== BEFORE ===" && cat /tmp/stats_before.json | python -m json.tool
echo "=== AFTER ===" && cat /tmp/stats_after.json | python -m json.tool
```
**Erwartung:** `total_routes` und `total_rewards` sollten gestiegen sein. Coding-Centroid-Norm sollte sich verändert haben.

### 5.2 Supervised Training
```bash
# Brain direkt trainieren
curl -s -X POST http://localhost:5000/api/cortex/route/train \
  -H "Content-Type: application/json" \
  -d '{"user_text": "Deploy the Docker containers", "correct_space": "desktop"}'
```
**Erwartung:** `{"ok": true, "trained_space": "desktop"}`

---

## Level 6: Error Handling & Edge Cases

### 6.1 Brain offline → Fallback
```bash
# Brain stoppen, dann:
curl -s -X POST http://localhost:5100/bridge/route \
  -d '{"task": "Test ohne Brain"}'
```
**Erwartung:** Fallback zu `ideas` space, confidence 0.0, agent `brain-fallback`.

### 6.2 OpenFang offline → 503
```bash
# OpenFang stoppen, dann:
curl -s -X POST http://localhost:5100/bridge/route \
  -d '{"task": "Test ohne OpenFang"}'
```
**Erwartung:** HTTP 503 "could not spawn agent".

### 6.3 Leerer Task
```bash
curl -s -X POST http://localhost:5100/bridge/route \
  -H "Content-Type: application/json" \
  -d '{"task": ""}'
```
**Erwartung:** Routing funktioniert (Brain bekommt leeren String), Fallback wahrscheinlich.

### 6.4 Sehr langer Task (>200 chars)
```bash
curl -s -X POST http://localhost:5100/bridge/route \
  -d '{"task": "'"$(python -c "print('A'*500)")"'"}'
```
**Erwartung:** Brain bekommt nur 200 chars (brain_client truncated), Routing funktioniert.

### 6.5 Timeout Test
```bash
curl -s -X POST http://localhost:5100/bridge/route \
  -H "Content-Type: application/json" \
  -d '{"task": "Sehr komplexe Aufgabe", "timeout_secs": 5}'
```
**Erwartung:** Timeout nach 5s falls Agent länger braucht.

---

## Checkliste

| # | Test | Status |
|---|------|--------|
| 0.1 | Brain startet auf :5000 | [ ] |
| 0.2 | OpenFang startet auf :4200 | [ ] |
| 0.3 | Bridge startet auf :5100 | [x] |
| 1.1 | Space Mapping (12 Assertions) | [x] |
| 1.2 | Pydantic Models | [x] |
| 1.3 | Task Store CRUD | [ ] |
| 2.1 | Brain Routing (coding) | [ ] |
| 2.2 | Brain Routing (4 Domains) | [ ] |
| 2.3 | Brain Reward | [ ] |
| 2.4 | Brain Stats | [ ] |
| 3.1 | OpenFang Agents List | [ ] |
| 3.2 | Spawn brain-coder | [ ] |
| 3.3 | Agent Message (Claude Code) | [ ] |
| 3.4 | Alle 7 Templates spawnen | [ ] |
| 4.1 | Health Check (alle grün) | [ ] |
| 4.2 | End-to-End Coding Route | [ ] |
| 4.3 | End-to-End 3 Domains | [ ] |
| 4.4 | Async Fire-and-Forget | [ ] |
| 4.5 | Hot-Reload Mapping | [ ] |
| 5.1 | Reward Zyklus (Stats ändern sich) | [ ] |
| 5.2 | Supervised Training | [ ] |
| 6.1 | Brain offline Fallback | [x] |
| 6.2 | OpenFang offline 503 | [x] |
| 6.3 | Leerer Task | [ ] |
| 6.4 | Langer Task (truncation) | [ ] |
| 6.5 | Timeout | [ ] |
