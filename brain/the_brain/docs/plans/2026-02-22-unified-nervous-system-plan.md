# Unified Nervous System — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Consolidate 6 Flask servers into one FastAPI "Nervous System" with WebSocket streams and thalamic middleware.

**Architecture:** One FastAPI app (`web/brain_server.py`) with 6 APIRouter modules (`routers/`), 2 WebSocket stream handlers (`streams/`), and a thalamic priority middleware (`middleware/`). All brain modules initialized once in the app lifespan, shared via `request.app.state`. Existing HTML templates stay unchanged.

**Tech Stack:** FastAPI, uvicorn, Jinja2Templates, WebSocket, asyncio, pydantic

**Test file:** `tests/test_brain_server.py`
**Test command:** `python -m pytest the_brain/tests/test_brain_server.py -v -p no:dash -p no:anyio`

**Existing servers for reference:**
- `web/moltbook_dashboard_server.py` (780 lines, 18 routes, port 5006)
- `web/brain_dashboard_server.py` (2101 lines, 66 routes, port 5004)
- `web/oscillator_dashboard_server.py` (406 lines, 13 routes, port 5005)
- `web/autonomous_swarm_server.py` (249 lines, 5 routes, port 5002)
- `web/klotski_dashboard_server.py` (453 lines, 7 routes, port 5004)
- `web/evolutionary_training_server.py` (218 lines, 6 routes, port 5004)

**HTML templates:**
- In `web/templates/`: `moltbook_dashboard.html`, `brain_dashboard.html`, `oscillator_dashboard.html`, `autonomous_swarm.html`, `cognitive_loop_viz.html`
- Loose in `web/`: `klotski_dashboard.html`, `evolutionary_training_dashboard.html`, `cognitive_flow_visualizer.html`, `swarm_visualization_demo.html`

---

## Task 1: Install Dependencies + Create Package Structure

**Files:**
- Modify: `requirements.txt`
- Create: `web/__init__.py`
- Create: `web/routers/__init__.py`
- Create: `web/streams/__init__.py`
- Create: `web/middleware/__init__.py`

**Step 1: Add FastAPI dependencies to requirements.txt**

Append to `requirements.txt`:
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
python-multipart>=0.0.9
websockets>=12.0
```

**Step 2: Install dependencies**

Run: `python -m pip install fastapi "uvicorn[standard]" python-multipart websockets`

**Step 3: Create package files**

```python
# web/__init__.py
"""The Brain Nervous System — unified web interface."""

# web/routers/__init__.py
"""API routers — one per brain region."""

# web/streams/__init__.py
"""WebSocket streams — real-time consciousness."""

# web/middleware/__init__.py
"""Request processing middleware."""
```

**Step 4: Move loose HTML files into templates/**

Move these files into `web/templates/`:
- `web/klotski_dashboard.html` → `web/templates/klotski_dashboard.html`
- `web/evolutionary_training_dashboard.html` → `web/templates/evolutionary_training_dashboard.html`

(Keep originals as-is for now, just copy them)

**Step 5: Commit**

```bash
git add web/__init__.py web/routers/__init__.py web/streams/__init__.py web/middleware/__init__.py requirements.txt
git commit -m "feat: scaffold nervous system package structure"
```

---

## Task 2: brain_server.py — The Foundation

**Files:**
- Create: `web/brain_server.py`
- Create: `tests/test_brain_server.py`

**Step 1: Write the test skeleton**

```python
# tests/test_brain_server.py
"""Tests for the Unified Nervous System (brain_server.py)."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient


# ── Foundation Tests ────────────────────────────────────────────────

class TestBrainServerFoundation:
    """Test the bare FastAPI app starts and serves basics."""

    def test_app_creates(self):
        """FastAPI app can be imported."""
        from web.brain_server import create_app
        app = create_app(testing=True)
        assert app is not None

    def test_health_endpoint(self):
        """GET /api/health returns 200."""
        from web.brain_server import create_app
        app = create_app(testing=True)
        client = TestClient(app)
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "alive"
        assert "timestamp" in data

    def test_cors_headers(self):
        """CORS headers are set."""
        from web.brain_server import create_app
        app = create_app(testing=True)
        client = TestClient(app)
        r = client.options("/api/health", headers={"Origin": "http://localhost:3000"})
        assert r.status_code == 200

    def test_root_returns_html(self):
        """GET / returns HTML dashboard."""
        from web.brain_server import create_app
        app = create_app(testing=True)
        client = TestClient(app)
        r = client.get("/")
        assert r.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest the_brain/tests/test_brain_server.py::TestBrainServerFoundation::test_app_creates -v -p no:dash -p no:anyio`
Expected: FAIL — `ImportError: cannot import name 'create_app'`

**Step 3: Write brain_server.py**

```python
# web/brain_server.py
"""
The Brain Nervous System — Unified FastAPI Server.

Biological mapping:
    /api/cortex/      → Cerebral cortex (main I/O: chat, perceive, act)
    /api/knowledge/   → Hippocampus (knowledge store, learning)
    /api/introspect/  → Default Mode Network (self-monitoring)
    /api/oscillator/  → Thalamic oscillator (temporal routing)
    /api/train/       → Cerebellum (motor learning, optimization)
    /api/swarm/       → Distributed cognition (swarm execution)
    /ws/              → Real-time consciousness streams

Usage:
    python -m web.brain_server
    → http://localhost:5000

    Or with uvicorn:
    uvicorn web.brain_server:app --host 0.0.0.0 --port 5000 --reload
"""

import sys
import os
import time
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

# Resolve paths
WEB_DIR = Path(__file__).parent
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
PROJECT_ROOT = WEB_DIR.parent

# Ensure project root on sys.path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _init_brain_state(state, testing: bool = False):
    """Initialize all brain modules onto app.state.

    In testing mode, all modules are set to None (mocked externally).
    In production, lazy-imports and instantiates real modules.
    """
    state.testing = testing
    state.start_time = time.time()

    # Placeholders — routers set these during include
    state.brain_chat = None
    state.continuous_thinking = None
    state.moltbook_store = None
    state.moltbook_graph = None
    state.moltbook_agents = {}
    state.oscillator = None
    state.checkpoint_manager = None
    state.meta_router = None
    state.brain_monitor = None
    state.strategy_lib = None
    state.live_monitor = None
    state.path_planner = None
    state.llm_router = None
    state.frequency_controller = None
    state.swarm_orchestrator = None

    # Shared mutable state
    state.oscillator_history = []
    state.chat_history = []
    state.training_state = {
        'klotski': {},
        'evolutionary': {
            'positions': {},
            'metrics': {},
            'messages': [],
        },
    }


def create_app(testing: bool = False) -> FastAPI:
    """Factory function to create the FastAPI app.

    Args:
        testing: If True, skip real module initialization.

    Returns:
        Configured FastAPI application.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Startup / shutdown lifecycle."""
        logger.info("Nervous System starting up...")
        _init_brain_state(app.state, testing=testing)

        if not testing:
            _init_production_modules(app.state)

        logger.info("Nervous System ready.")
        yield
        logger.info("Nervous System shutting down.")

    app = FastAPI(
        title="The Brain — Nervous System",
        description="Unified AGI interface: one server, one nervous system.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS — allow all origins (dashboards run on various ports)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Templates
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    app.state.templates = templates

    # Static files (if directory exists)
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ── Core Routes ─────────────────────────────────────────────
    @app.get("/api/health")
    async def health():
        """System health check."""
        return {
            "status": "alive",
            "timestamp": time.time(),
            "uptime": time.time() - (app.state.start_time if hasattr(app.state, 'start_time') else time.time()),
        }

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Main dashboard — serves brain_dashboard.html."""
        return templates.TemplateResponse("brain_dashboard.html", {"request": request})

    # ── Include Routers ─────────────────────────────────────────
    # (Added in subsequent tasks)

    return app


def _init_production_modules(state):
    """Initialize real brain modules for production mode.

    Uses try/except for each module so partial failures don't kill the server.
    """
    # Phase 1: Core routing
    try:
        from core.layer4_temporal_router import Layer4TemporalRouter
        state.oscillator = Layer4TemporalRouter()
        logger.info("  ✓ Layer4TemporalRouter")
    except Exception as e:
        logger.warning(f"  ✗ Layer4TemporalRouter: {e}")

    try:
        from core.oscillator_checkpoint import CheckpointManager
        state.checkpoint_manager = CheckpointManager()
        logger.info("  ✓ CheckpointManager")
    except Exception as e:
        logger.warning(f"  ✗ CheckpointManager: {e}")

    # Phase 2: Brain monitoring
    try:
        from core.meta_router import MetaRouter
        state.meta_router = MetaRouter()
        logger.info("  ✓ MetaRouter")
    except Exception as e:
        logger.warning(f"  ✗ MetaRouter: {e}")

    try:
        from core.brain_monitor import BrainActivityMonitor
        state.brain_monitor = BrainActivityMonitor()
        logger.info("  ✓ BrainActivityMonitor")
    except Exception as e:
        logger.warning(f"  ✗ BrainActivityMonitor: {e}")

    try:
        from core.strategy_library import StrategyLibrary
        state.strategy_lib = StrategyLibrary()
        logger.info("  ✓ StrategyLibrary")
    except Exception as e:
        logger.warning(f"  ✗ StrategyLibrary: {e}")

    try:
        from core.live_brain_monitor import LiveBrainMonitor
        state.live_monitor = LiveBrainMonitor()
        logger.info("  ✓ LiveBrainMonitor")
    except Exception as e:
        logger.warning(f"  ✗ LiveBrainMonitor: {e}")

    try:
        from core.conversation_path_planner import ConversationPathPlanner
        state.path_planner = ConversationPathPlanner()
        logger.info("  ✓ ConversationPathPlanner")
    except Exception as e:
        logger.warning(f"  ✗ ConversationPathPlanner: {e}")

    # Phase 3: Knowledge system
    try:
        from core.moltbook import MoltbookStore, MoltbookGraph
        state.moltbook_store = MoltbookStore(config={'similarity_threshold': 0.3})
        state.moltbook_graph = MoltbookGraph()
        logger.info("  ✓ MoltbookStore + Graph")
    except Exception as e:
        logger.warning(f"  ✗ MoltbookStore: {e}")

    try:
        from core.moltbook_agents import (
            MoltbookFeeder, EvaluationAgent, CurationAgent,
            ResearchAgent, FeedbackAgent, MoltbookForum,
        )
        state.moltbook_agents = {
            'feeder': MoltbookFeeder(state.moltbook_store),
            'evaluator': EvaluationAgent(state.moltbook_store),
            'curator': CurationAgent(state.moltbook_store),
            'researcher': ResearchAgent(state.moltbook_store),
            'feedback': FeedbackAgent(state.moltbook_store),
            'forum': MoltbookForum(state.moltbook_store),
        }
        logger.info("  ✓ MoltbookAgents (6)")
    except Exception as e:
        logger.warning(f"  ✗ MoltbookAgents: {e}")

    # Phase 4: Brain Chat
    try:
        from core.brain_chat import BrainChat, ContinuousThinkingEngine
        state.brain_chat = BrainChat(
            moltbook_store=state.moltbook_store,
        )
        state.continuous_thinking = ContinuousThinkingEngine()
        logger.info("  ✓ BrainChat + CTE")
    except Exception as e:
        logger.warning(f"  ✗ BrainChat: {e}")

    # Phase 5: LLM Router
    try:
        from core.multi_llm_router import MultiLLMRouter
        from load_env import get_openrouter_key
        api_key = get_openrouter_key()
        if api_key:
            state.llm_router = MultiLLMRouter(api_key=api_key)
            logger.info("  ✓ MultiLLMRouter")
        else:
            logger.warning("  ✗ MultiLLMRouter: no API key")
    except Exception as e:
        logger.warning(f"  ✗ MultiLLMRouter: {e}")

    # Phase 6: Frequency controller
    try:
        from core.brain_frequency_controller import BrainFrequencyController, FrequencyMixer
        state.frequency_controller = BrainFrequencyController()
        logger.info("  ✓ BrainFrequencyController")
    except Exception as e:
        logger.warning(f"  ✗ BrainFrequencyController: {e}")


# ── Module-level app for uvicorn ────────────────────────────────────
app = create_app(testing=False)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("BRAIN_PORT", 5000))
    uvicorn.run(
        "web.brain_server:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )
```

**Step 4: Run tests**

Run: `python -m pytest the_brain/tests/test_brain_server.py -v -p no:dash -p no:anyio`
Expected: 4 passed

**Step 5: Commit**

```bash
git add web/brain_server.py tests/test_brain_server.py
git commit -m "feat: brain_server.py foundation — FastAPI app with health + root"
```

---

## Task 3: Thalamic Middleware

**Files:**
- Create: `web/middleware/thalamic_gate.py`
- Modify: `web/brain_server.py` (add middleware)
- Modify: `tests/test_brain_server.py` (add tests)

**Step 1: Write tests**

Append to `tests/test_brain_server.py`:

```python
class TestThalamicMiddleware:
    """Test the thalamic priority middleware."""

    def test_cortex_tagged_cognitive(self):
        from web.brain_server import create_app
        app = create_app(testing=True)

        @app.get("/api/cortex/test")
        async def cortex_test(request: Request):
            return {"priority": request.state.priority}

        client = TestClient(app)
        r = client.get("/api/cortex/test")
        assert r.json()["priority"] == "cognitive"

    def test_introspect_tagged_low(self):
        from web.brain_server import create_app
        app = create_app(testing=True)

        @app.get("/api/introspect/test")
        async def introspect_test(request: Request):
            return {"priority": request.state.priority}

        client = TestClient(app)
        r = client.get("/api/introspect/test")
        assert r.json()["priority"] == "introspective"

    def test_train_tagged_background(self):
        from web.brain_server import create_app
        app = create_app(testing=True)

        @app.get("/api/train/test")
        async def train_test(request: Request):
            return {"priority": request.state.priority}

        client = TestClient(app)
        r = client.get("/api/train/test")
        assert r.json()["priority"] == "cerebellar"
```

**Step 2: Create middleware**

```python
# web/middleware/thalamic_gate.py
"""
Thalamic Gate Middleware — every request passes through the thalamus.

Like the biological thalamus, this middleware:
- Tags each request with a priority/modality
- Enables future attention budgeting under load
- Provides request timing metrics
"""

import time
import logging
from fastapi import Request

logger = logging.getLogger(__name__)

# Priority mapping: URL prefix → (priority_name, urgency_score)
PRIORITY_MAP = {
    "/api/cortex":     ("cognitive", 0.9),      # Highest — main I/O
    "/api/knowledge":  ("mnemonic", 0.7),       # High — knowledge ops
    "/api/swarm":      ("executive", 0.6),       # Medium — task execution
    "/api/oscillator": ("temporal", 0.4),        # Low-medium — monitoring
    "/api/introspect": ("introspective", 0.3),   # Low — self-observation
    "/api/train":      ("cerebellar", 0.1),      # Background — training
    "/ws":             ("streaming", 0.8),        # High — real-time streams
}


async def thalamic_gate_middleware(request: Request, call_next):
    """Tag every request with priority and measure timing."""
    path = request.url.path

    # Assign priority based on URL prefix
    priority = "unknown"
    urgency = 0.5
    for prefix, (prio, urg) in PRIORITY_MAP.items():
        if path.startswith(prefix):
            priority = prio
            urgency = urg
            break

    request.state.priority = priority
    request.state.urgency = urgency
    request.state.received_at = time.time()

    # Process request
    response = await call_next(request)

    # Add timing header
    elapsed = time.time() - request.state.received_at
    response.headers["X-Brain-Priority"] = priority
    response.headers["X-Brain-Latency-Ms"] = f"{elapsed * 1000:.1f}"

    return response
```

**Step 3: Wire middleware into brain_server.py**

In `create_app()`, after CORS middleware, add:

```python
from web.middleware.thalamic_gate import thalamic_gate_middleware
app.middleware("http")(thalamic_gate_middleware)
```

**Step 4: Run tests**

Run: `python -m pytest the_brain/tests/test_brain_server.py -v -p no:dash -p no:anyio`
Expected: 7 passed

**Step 5: Commit**

```bash
git add web/middleware/thalamic_gate.py web/brain_server.py tests/test_brain_server.py
git commit -m "feat: thalamic gate middleware — priority tagging for all requests"
```

---

## Task 4: Training Router (Simplest — no brain imports)

**Files:**
- Create: `web/routers/training.py`
- Modify: `web/brain_server.py` (include router)
- Modify: `tests/test_brain_server.py` (add tests)

**Reference:** `web/klotski_dashboard_server.py` lines 60-200, `web/evolutionary_training_server.py` lines 40-180

**Step 1: Write tests**

```python
class TestTrainingRouter:
    """Test /api/train/ routes — klotski + evolutionary data sinks."""

    def setup_method(self):
        from web.brain_server import create_app
        self.app = create_app(testing=True)
        self.client = TestClient(self.app)

    def test_klotski_status_empty(self):
        r = self.client.get("/api/train/klotski/status")
        assert r.status_code == 200
        assert "status" in r.json()

    def test_klotski_update_state(self):
        r = self.client.post("/api/train/klotski/update", json={
            "generation": 1, "best_fitness": 0.5
        })
        assert r.status_code == 200

    def test_klotski_update_agent(self):
        r = self.client.post("/api/train/klotski/agent", json={
            "agent_id": "agent_0", "fitness": 0.7
        })
        assert r.status_code == 200

    def test_klotski_reset(self):
        r = self.client.post("/api/train/klotski/reset")
        assert r.status_code == 200

    def test_evolutionary_status(self):
        r = self.client.get("/api/train/evolutionary/status")
        assert r.status_code == 200

    def test_evolutionary_update_positions(self):
        r = self.client.post("/api/train/evolutionary/positions", json={
            "agent_0": {"x": 1, "y": 2}
        })
        assert r.status_code == 200

    def test_evolutionary_update_metrics(self):
        r = self.client.post("/api/train/evolutionary/metrics", json={
            "generation": 5, "avg_fitness": 0.8
        })
        assert r.status_code == 200

    def test_evolutionary_message(self):
        r = self.client.post("/api/train/evolutionary/message", json={
            "text": "Agent A mutated"
        })
        assert r.status_code == 200

    def test_evolutionary_reset(self):
        r = self.client.post("/api/train/evolutionary/reset")
        assert r.status_code == 200

    def test_klotski_dashboard_page(self):
        r = self.client.get("/ui/training/klotski")
        assert r.status_code == 200

    def test_evolutionary_dashboard_page(self):
        r = self.client.get("/ui/training/evolutionary")
        assert r.status_code == 200
```

**Step 2: Create router**

```python
# web/routers/training.py
"""
Training Router — Cerebellar region.

Pure data sinks for training visualizations.
No brain module imports. External training scripts push state via POST,
dashboards read via GET.

Routes:
    /api/train/klotski/...        Klotski puzzle training
    /api/train/evolutionary/...   Evolutionary training
    /ui/training/klotski          Klotski dashboard page
    /ui/training/evolutionary     Evolutionary dashboard page
"""

import time
import logging
from datetime import datetime
from threading import Lock
from collections import deque

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Thread-safe state (shared across requests via app.state.training_state)
_state_lock = Lock()


# ── Klotski ─────────────────────────────────────────────────────────

@router.get("/api/train/klotski/status")
async def klotski_status(request: Request):
    """Get current klotski training state."""
    state = request.app.state.training_state.get('klotski', {})
    return {"status": "ok", "data": state, "timestamp": time.time()}


@router.post("/api/train/klotski/update")
async def klotski_update(request: Request):
    """Update generation-level training data."""
    data = await request.json()
    with _state_lock:
        ts = request.app.state.training_state
        ts['klotski'].update(data)
        ts['klotski']['last_updated'] = time.time()
    return {"status": "updated"}


@router.post("/api/train/klotski/agent")
async def klotski_update_agent(request: Request):
    """Update single agent state."""
    data = await request.json()
    agent_id = data.get("agent_id", "unknown")
    with _state_lock:
        ts = request.app.state.training_state
        if 'agents' not in ts['klotski']:
            ts['klotski']['agents'] = {}
        ts['klotski']['agents'][agent_id] = data
    return {"status": "agent_updated", "agent_id": agent_id}


@router.post("/api/train/klotski/reset")
async def klotski_reset(request: Request):
    """Reset klotski dashboard state."""
    with _state_lock:
        request.app.state.training_state['klotski'] = {}
    return {"status": "reset"}


# ── Evolutionary ────────────────────────────────────────────────────

@router.get("/api/train/evolutionary/status")
async def evolutionary_status(request: Request):
    """Get current evolutionary training state."""
    state = request.app.state.training_state.get('evolutionary', {})
    return {"status": "ok", "data": state, "timestamp": time.time()}


@router.post("/api/train/evolutionary/positions")
async def evolutionary_positions(request: Request):
    """Update agent positions."""
    data = await request.json()
    with _state_lock:
        request.app.state.training_state['evolutionary']['positions'] = data
    return {"status": "positions_updated"}


@router.post("/api/train/evolutionary/metrics")
async def evolutionary_metrics(request: Request):
    """Update training metrics."""
    data = await request.json()
    with _state_lock:
        request.app.state.training_state['evolutionary']['metrics'] = data
    return {"status": "metrics_updated"}


@router.post("/api/train/evolutionary/message")
async def evolutionary_message(request: Request):
    """Add communication message."""
    data = await request.json()
    with _state_lock:
        msgs = request.app.state.training_state['evolutionary'].setdefault('messages', [])
        msgs.append({
            "text": data.get("text", ""),
            "timestamp": datetime.now().isoformat(),
        })
        # Keep last 100
        if len(msgs) > 100:
            request.app.state.training_state['evolutionary']['messages'] = msgs[-100:]
    return {"status": "message_added"}


@router.post("/api/train/evolutionary/reset")
async def evolutionary_reset(request: Request):
    """Reset evolutionary state for new generation."""
    with _state_lock:
        request.app.state.training_state['evolutionary'] = {
            'positions': {},
            'metrics': {},
            'messages': [],
        }
    return {"status": "reset"}


# ── Dashboard Pages ─────────────────────────────────────────────────

@router.get("/ui/training/klotski", response_class=HTMLResponse)
async def klotski_page(request: Request):
    """Klotski training dashboard."""
    templates = request.app.state.templates
    return templates.TemplateResponse("klotski_dashboard.html", {"request": request})


@router.get("/ui/training/evolutionary", response_class=HTMLResponse)
async def evolutionary_page(request: Request):
    """Evolutionary training dashboard."""
    templates = request.app.state.templates
    return templates.TemplateResponse("evolutionary_training_dashboard.html", {"request": request})
```

**Step 3: Include router in brain_server.py**

In `create_app()`, after the core routes:

```python
from web.routers.training import router as training_router
app.include_router(training_router)
```

**Step 4: Run tests**

Run: `python -m pytest the_brain/tests/test_brain_server.py -v -p no:dash -p no:anyio`
Expected: 18 passed (7 foundation + 11 training)

**Step 5: Commit**

```bash
git add web/routers/training.py web/brain_server.py tests/test_brain_server.py
git commit -m "feat: training router — klotski + evolutionary data sinks"
```

---

## Task 5: Oscillator Router

**Files:**
- Create: `web/routers/oscillator.py`
- Modify: `web/brain_server.py` (include router)
- Modify: `tests/test_brain_server.py` (add tests)

**Reference:** `web/oscillator_dashboard_server.py` (all routes), `web/brain_dashboard_server.py` lines 1500-1800 (oscillator section)

**Step 1: Write tests**

```python
class TestOscillatorRouter:
    """Test /api/oscillator/ routes."""

    def setup_method(self):
        from web.brain_server import create_app
        self.app = create_app(testing=True)
        self.client = TestClient(self.app)

    def test_state_no_oscillator(self):
        """Returns graceful empty state when oscillator not initialized."""
        r = self.client.get("/api/oscillator/state")
        assert r.status_code == 200
        assert "state" in r.json()

    def test_history(self):
        r = self.client.get("/api/oscillator/history")
        assert r.status_code == 200

    def test_stats(self):
        r = self.client.get("/api/oscillator/stats")
        assert r.status_code == 200

    def test_health(self):
        r = self.client.get("/api/oscillator/health")
        assert r.status_code == 200

    def test_reset(self):
        r = self.client.post("/api/oscillator/reset")
        assert r.status_code == 200

    def test_oscillator_page(self):
        r = self.client.get("/ui/oscillator")
        assert r.status_code == 200
```

**Step 2: Create router**

Extract routes from `oscillator_dashboard_server.py` and `brain_dashboard_server.py` oscillator section. Use `request.app.state.oscillator` for the Layer4TemporalRouter instance. Graceful fallback when oscillator is None.

Key pattern for every route:
```python
@router.get("/api/oscillator/state")
async def oscillator_state(request: Request):
    osc = request.app.state.oscillator
    if not osc:
        return {"state": None, "message": "oscillator not initialized"}
    # ... use osc
```

**Step 3: Include router, run tests, commit**

---

## Task 6: Swarm Router

**Files:**
- Create: `web/routers/swarm.py`
- Modify: `web/brain_server.py` (include router)
- Modify: `tests/test_brain_server.py` (add tests)

**Reference:** `web/autonomous_swarm_server.py` (all 5 routes)

Extract all routes. The `/api/swarm/execute` route needs special handling — it runs an async orchestrator. In FastAPI this is native (no need for `asyncio.new_event_loop()`).

---

## Task 7: Introspection Router

**Files:**
- Create: `web/routers/introspection.py`
- Modify: `web/brain_server.py` (include router)
- Modify: `tests/test_brain_server.py` (add tests)

**Reference:** `web/brain_dashboard_server.py` — this is the biggest extraction (~40 routes).

Key sections to extract:
- Brain state/gates/activation (lines 100-300)
- Emotional/homeostatic/memory state proxies (lines 300-500)
- Cognitive loop/agent loop (lines 500-700)
- Health/readiness/liveness (lines 1800-2000)
- Frequency controller (lines 700-900)
- Goals/evolution/causal/meta/federated (lines 1100-1500)
- Metrics/audit/traces/heatmap (lines 900-1100)
- LLM stats, chat send/history (lines 1000-1100)

**Important:** The brain_dashboard currently proxies many routes to `http://localhost:5003`. In the unified server, these should call the modules directly (no more inter-service HTTP proxying). Where a module is on `app.state`, use it directly.

For routes that still need the unified brain service (if it runs separately), keep the proxy pattern but make it configurable.

---

## Task 8: Knowledge Router

**Files:**
- Create: `web/routers/knowledge.py`
- Modify: `web/brain_server.py` (include router)
- Modify: `tests/test_brain_server.py` (add tests)

**Reference:** `web/moltbook_dashboard_server.py` — knowledge-specific routes (entries, search, feed, evaluate, curate, feedback, research, forum, graph)

Extract all Moltbook knowledge routes. Access modules via `request.app.state.moltbook_store`, `request.app.state.moltbook_agents['feeder']`, etc.

---

## Task 9: Cortex Router (Main I/O)

**Files:**
- Create: `web/routers/cortex.py`
- Modify: `web/brain_server.py` (include router)
- Modify: `tests/test_brain_server.py` (add tests)

**Reference:** `web/moltbook_dashboard_server.py` — brain chat routes (`/api/brain/chat`, `/api/brain/thoughts`, `/api/brain/state`)

This is the most important router — the brain's primary I/O:
- `POST /api/cortex/chat` — BrainChat.send()
- `GET /api/cortex/thoughts` — CTE background thoughts
- `GET /api/cortex/state` — Full brain state snapshot

---

## Task 10: WebSocket — Consciousness Stream

**Files:**
- Create: `web/streams/consciousness.py`
- Modify: `web/brain_server.py` (include WebSocket router)
- Modify: `tests/test_brain_server.py` (add tests)

**Step 1: Write test**

```python
class TestConsciousnessStream:
    def test_websocket_connects(self):
        from web.brain_server import create_app
        app = create_app(testing=True)
        client = TestClient(app)
        with client.websocket_connect("/ws/consciousness") as ws:
            data = ws.receive_json()
            assert "timestamp" in data
            assert "thoughts" in data
```

**Step 2: Implement**

```python
# web/streams/consciousness.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio, time

router = APIRouter()

@router.websocket("/ws/consciousness")
async def consciousness_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            state = {
                "thoughts": [],  # from CTE
                "gates": {},     # from brain
                "oscillator": {},
                "timestamp": time.time(),
            }
            # Populate from app.state if available
            app = websocket.app
            if hasattr(app.state, 'continuous_thinking') and app.state.continuous_thinking:
                cte = app.state.continuous_thinking
                state["thoughts"] = [t.to_dict() for t in cte.get_recent_thoughts(5)]
            if hasattr(app.state, 'oscillator') and app.state.oscillator:
                try:
                    state["oscillator"] = app.state.oscillator.get_state()
                except Exception:
                    pass

            await websocket.send_json(state)
            await asyncio.sleep(0.5)  # 2 Hz consciousness tick
    except WebSocketDisconnect:
        pass
```

---

## Task 11: WebSocket — Chat Stream

**Files:**
- Create: `web/streams/chat.py`
- Modify: `web/brain_server.py` (include WebSocket router)
- Modify: `tests/test_brain_server.py` (add tests)

Bidirectional WebSocket for streaming chat:
- Client sends: `{"message": "What is consciousness?"}`
- Server streams back: `{"chunk": "...", "done": false}` ... `{"chunk": "", "done": true, "trace": [...]}`

---

## Task 12: UI Routes + Legacy Cleanup

**Files:**
- Modify: `web/brain_server.py` (add remaining UI routes)
- Move: `web/*_server.py` → `web/legacy/`
- Modify: `.claude/launch.json`

**Step 1: Add UI routes to brain_server.py**

```python
@app.get("/ui/moltbook", response_class=HTMLResponse)
async def moltbook_page(request: Request):
    return templates.TemplateResponse("moltbook_dashboard.html", {"request": request})

@app.get("/ui/brain", response_class=HTMLResponse)
async def brain_page(request: Request):
    return templates.TemplateResponse("brain_dashboard.html", {"request": request})

@app.get("/ui/oscillator", response_class=HTMLResponse)
async def oscillator_page(request: Request):
    return templates.TemplateResponse("oscillator_dashboard.html", {"request": request})

@app.get("/ui/swarm", response_class=HTMLResponse)
async def swarm_page(request: Request):
    return templates.TemplateResponse("autonomous_swarm.html", {"request": request})
```

**Step 2: Move old servers to legacy**

```bash
mkdir -p web/legacy
mv web/moltbook_dashboard_server.py web/legacy/
mv web/brain_dashboard_server.py web/legacy/
mv web/oscillator_dashboard_server.py web/legacy/
mv web/autonomous_swarm_server.py web/legacy/
mv web/klotski_dashboard_server.py web/legacy/
mv web/evolutionary_training_server.py web/legacy/
```

**Step 3: Update launch.json**

Replace all 6 server entries with one:

```json
{
    "name": "brain-server",
    "runtimeExecutable": "python",
    "runtimeArgs": ["-m", "web.brain_server"],
    "port": 5000
}
```

**Step 4: Final integration test**

Run: `python -m pytest the_brain/tests/test_brain_server.py -v -p no:dash -p no:anyio`
Expected: ALL passed

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: unified nervous system — 6 servers → 1 FastAPI app"
```

---

## Summary

| Task | What | Routes | Est. |
|------|------|--------|------|
| 1 | Dependencies + scaffold | 0 | 5 min |
| 2 | brain_server.py foundation | 2 | 15 min |
| 3 | Thalamic middleware | 0 | 10 min |
| 4 | Training router | 11 | 15 min |
| 5 | Oscillator router | 10 | 15 min |
| 6 | Swarm router | 5 | 10 min |
| 7 | Introspection router | ~30 | 30 min |
| 8 | Knowledge router | ~12 | 20 min |
| 9 | Cortex router | 5 | 15 min |
| 10 | WS consciousness stream | 1 | 10 min |
| 11 | WS chat stream | 1 | 10 min |
| 12 | UI routes + legacy cleanup | 4 | 10 min |
| **Total** | | **~80** | **~2.5h** |
