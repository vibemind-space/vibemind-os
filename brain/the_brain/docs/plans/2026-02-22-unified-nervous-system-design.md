# Unified Nervous System — Design Document

**Date:** 2026-02-22
**Status:** Approved
**Scope:** Consolidate 6 Flask servers into 1 FastAPI "Nervous System"

## Problem

The Brain currently runs 6 independent Flask servers (+ 1 FastAPI minibook + 1 Next.js frontend):
- `moltbook_dashboard_server.py` (port 5006) — Knowledge + Chat
- `brain_dashboard_server.py` (port 5004) — 66 routes, master dashboard
- `oscillator_dashboard_server.py` (port 5005) — Layer4 oscillator
- `autonomous_swarm_server.py` (port 5002) — Swarm execution
- `klotski_dashboard_server.py` (port 5004) — Training data sink
- `evolutionary_training_server.py` (port 5004) — Training data sink

Issues:
- 3 servers fight over port 5004
- No shared state between servers
- Duplicate utilities (convert_numpy in 2 files)
- All polling, no WebSocket anywhere
- brain_dashboard proxies 30+ routes to port 5003
- No authentication, no rate limiting
- Architecturally meaningless — random collection of routes

## Solution: The Nervous System

One FastAPI server = the brain's nervous system. The single interface between Brain and world.

### Biological Mapping

| Bio Layer | Server Layer | Function |
|-----------|-------------|----------|
| Receptors | HTTP + WebSocket input | Receive stimuli (chat, knowledge, events) |
| Thalamic Relay | Middleware | Route requests through attention/priority |
| Effectors | Response output | Responses, actions, streaming |
| Introspection | Dashboard APIs | Brain observes itself (state, health, metrics) |
| Cerebellar | Training APIs | Motor learning — optimization through training |

## File Structure

```
web/
  brain_server.py                    # THE one FastAPI server

  routers/
    __init__.py
    cortex.py                        # Main I/O: Chat, Perceive, Act, Think
    knowledge.py                     # Moltbook: Feed, Search, Entries, Graph, Forum
    introspection.py                 # Self-Monitoring: State, Gates, Modules, Health
    oscillator.py                    # Layer4 Temporal: State, History, Route, Checkpoint
    training.py                      # Klotski + Evolutionary data sinks
    swarm.py                         # Autonomous Swarm execution

  streams/
    __init__.py
    consciousness.py                 # WebSocket: Live brain state + thoughts + oscillator
    chat.py                          # WebSocket: Streaming chat responses

  middleware/
    __init__.py
    thalamic_gate.py                 # Request priority/routing through thalamus

  templates/                         # Existing HTML dashboards (unchanged)
    moltbook_dashboard.html
    brain_dashboard.html
    oscillator_dashboard.html
    autonomous_swarm.html
    klotski_dashboard.html
    evolutionary_training_dashboard.html

  legacy/                            # Old Flask servers (reference only)
    moltbook_dashboard_server.py
    brain_dashboard_server.py
    oscillator_dashboard_server.py
    autonomous_swarm_server.py
    klotski_dashboard_server.py
    evolutionary_training_server.py
```

## API Surface

### /api/cortex/ — Main I/O (cognitive, high priority)
```
POST /api/cortex/chat              BrainChat.send() with streaming
POST /api/cortex/perceive          Sensory input (text, files, events)
POST /api/cortex/act               Agent Loop task execution
GET  /api/cortex/thoughts          CTE background thoughts
GET  /api/cortex/state             Full brain state snapshot
```

### /api/knowledge/ — Moltbook Knowledge System
```
GET  /api/knowledge/entries        Recent knowledge entries
POST /api/knowledge/search         Semantic search
POST /api/knowledge/feed           Feed new knowledge
POST /api/knowledge/evaluate       Evaluate entry by ID
POST /api/knowledge/curate         Run curation cycle
POST /api/knowledge/feedback       Record user feedback
POST /api/knowledge/research       Run research agent cycle
POST /api/knowledge/forum/discuss  Multi-agent discussion
GET  /api/knowledge/forum/history  Discussion history
GET  /api/knowledge/graph          Knowledge graph (nodes + edges)
```

### /api/introspect/ — Self-Monitoring (introspective, low priority)
```
GET  /api/introspect/gates         Thalamic gate distribution
GET  /api/introspect/activation    Module activation levels
GET  /api/introspect/modules       All module health & status
GET  /api/introspect/emotional     Emotional system state
GET  /api/introspect/homeostatic   Homeostatic regulation
GET  /api/introspect/memory        Memory system state
GET  /api/introspect/cognitive     Cognitive loop state
GET  /api/introspect/goals         Goal graph state
GET  /api/introspect/neuromod      Neuromodulation state
GET  /api/introspect/consciousness Consciousness metrics
GET  /api/introspect/health        System health + readiness + liveness
GET  /api/introspect/metrics       Prometheus metrics
GET  /api/introspect/errors        Per-subsystem error rates
GET  /api/introspect/heatmap       Brain activity heatmap
GET  /api/introspect/audit         Prediction audit trail
GET  /api/introspect/traces        Cognitive loop traces
GET  /api/introspect/frequency     Frequency mode state
POST /api/introspect/frequency/set Set frequency mode
GET  /api/introspect/llm/stats     LLM router statistics
```

### /api/oscillator/ — Layer4 Temporal Router
```
GET  /api/oscillator/state         Current oscillator state
GET  /api/oscillator/history       History for charts
POST /api/oscillator/route         Route events through pipeline
POST /api/oscillator/tokens        Process tokens through EventBridge
GET  /api/oscillator/stats         Processing statistics
POST /api/oscillator/checkpoint    Save checkpoint
GET  /api/oscillator/checkpoints   List checkpoints
POST /api/oscillator/restore       Restore from checkpoint
POST /api/oscillator/reset         Reset state
GET  /api/oscillator/health        Oscillator health
```

### /api/train/ — Training Visualizations (cerebellar, background priority)
```
GET  /api/train/klotski/status     Klotski training state
POST /api/train/klotski/update     Push klotski state (agent or generation)
POST /api/train/klotski/reset      Reset klotski dashboard
GET  /api/train/evolutionary/status  Evolutionary training state
POST /api/train/evolutionary/positions  Update agent positions
POST /api/train/evolutionary/metrics    Update training metrics
POST /api/train/evolutionary/message    Add communication message
POST /api/train/evolutionary/reset      Reset for new generation
```

### /api/swarm/ — Autonomous Swarm
```
POST /api/swarm/execute            Execute task with brain + swarm
GET  /api/swarm/logs               Execution logs
GET  /api/swarm/stats              Swarm statistics
GET  /api/swarm/health             Swarm health
```

### WebSocket Streams
```
WS   /ws/consciousness             Live brain state broadcast (2 Hz)
WS   /ws/chat                      Streaming chat responses
```

### UI Pages
```
GET  /                             Main dashboard (brain overview)
GET  /ui/moltbook                  Moltbook Knowledge + Chat
GET  /ui/brain                     Brain monitoring dashboard
GET  /ui/oscillator                Oscillator visualization
GET  /ui/training                  Training dashboards (klotski + evolutionary)
GET  /ui/swarm                     Swarm execution UI
```

## WebSocket: Consciousness Stream

Instead of 4 dashboards polling every 2s, the brain pushes its state:

```python
@router.websocket("/ws/consciousness")
async def consciousness_stream(websocket: WebSocket):
    await websocket.accept()
    while True:
        state = {
            "thoughts": cte.get_recent_thoughts(),
            "gates": brain.get_gate_distribution(),
            "oscillator": oscillator.get_state(),
            "modules": brain.get_active_modules(),
            "emotional": brain.get_emotional_state(),
            "timestamp": time.time(),
        }
        await websocket.send_json(state)
        await asyncio.sleep(0.5)  # 2 Hz consciousness tick
```

## Thalamic Middleware

Every request passes through the thalamus for priority tagging:

```python
@app.middleware("http")
async def thalamic_gate(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/cortex"):
        request.state.priority = "cognitive"       # High
    elif path.startswith("/api/knowledge"):
        request.state.priority = "mnemonic"        # Medium-High
    elif path.startswith("/api/introspect"):
        request.state.priority = "introspective"   # Low
    elif path.startswith("/api/train"):
        request.state.priority = "cerebellar"      # Background

    response = await call_next(request)
    return response
```

Future: under load, the brain can drop cerebellar requests but keep cognitive ones.

## Shared State (App Lifespan)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize all brain systems once
    app.state.brain_chat = BrainChat(...)
    app.state.moltbook_store = MoltbookStore(...)
    app.state.oscillator = Layer4TemporalRouter(...)
    app.state.cte = ContinuousThinkingEngine(...)
    # ... all modules initialized once, shared across all routers
    yield
    # Shutdown: cleanup
```

All routers access shared state via `request.app.state.brain_chat` etc.
No more duplicate initialization across servers.

## Migration Strategy

| Old Server | New Location | Method |
|------------|-------------|--------|
| moltbook_dashboard_server.py | routers/cortex.py + routers/knowledge.py | Extract routes |
| brain_dashboard_server.py | routers/introspection.py + routers/oscillator.py | Extract routes, remove proxies |
| oscillator_dashboard_server.py | routers/oscillator.py (merged) | Merge with brain_dashboard oscillator routes |
| klotski_dashboard_server.py | routers/training.py | Simple data sink |
| evolutionary_training_server.py | routers/training.py (merged) | Simple data sink |
| autonomous_swarm_server.py | routers/swarm.py | Direct extraction |

Templates stay in web/templates/ unchanged.
Old servers move to web/legacy/ for reference.

## Dependencies

```
fastapi
uvicorn[standard]
jinja2          # Template rendering (already used by Flask)
python-multipart
websockets
```

## Port

Single port: **5000** (or configurable via BRAIN_PORT env var)

## Not In Scope

- Authentication (future)
- minibook FastAPI backend (port 8080, stays separate — different domain)
- minibook Next.js frontend (port 3000, stays separate)
- Template HTML changes (dashboards keep working, just different base URLs)
