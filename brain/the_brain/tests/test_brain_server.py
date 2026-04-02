"""
Tests for the unified Brain Nervous System server.

Covers:
  - Task 2 : BrainServer foundation (app factory, health, CORS, root page)
  - Task 3 : Thalamic gate middleware (priority tagging, response headers)
  - Task 4 : Training router (Klotski + Evolutionary data-sink endpoints)
"""

from __future__ import annotations

import sys
import os
import time

# Ensure the project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from web.brain_server import create_app


# ======================================================================
# Task 2 — Foundation
# ======================================================================

class TestBrainServerFoundation:
    """create_app(testing=True) produces a working FastAPI app."""

    def setup_method(self):
        self.app = create_app(testing=True)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def teardown_method(self):
        self.client.__exit__(None, None, None)

    # ---- test_app_creates ----
    def test_app_creates(self):
        assert isinstance(self.app, FastAPI)
        assert self.app.title == "The Brain \u2014 Nervous System"

    # ---- test_health_endpoint ----
    def test_health_endpoint(self):
        resp = self.client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"
        assert "timestamp" in data
        assert "uptime" in data
        assert isinstance(data["uptime"], (int, float))
        assert data["uptime"] >= 0

    # ---- test_cors_headers ----
    def test_cors_headers(self):
        resp = self.client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORS preflight should succeed
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers
        assert resp.headers["access-control-allow-origin"] == "*"

    # ---- test_root_returns_html ----
    def test_root_returns_html(self):
        resp = self.client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Brain Dashboard" in resp.text


# ======================================================================
# Task 3 — Thalamic Middleware
# ======================================================================

class TestThalamicMiddleware:
    """Middleware tags requests with priority metadata and response headers."""

    @staticmethod
    def _make_app_with_echo(prefix: str) -> FastAPI:
        """Create a minimal test app with one endpoint that echoes
        the middleware-injected priority from ``request.state``."""
        app = create_app(testing=True)

        @app.get(prefix)
        async def _echo(request: Request):
            return JSONResponse({
                "priority": request.state.priority,
                "urgency": request.state.urgency,
            })

        return app

    # ---- test_cortex_tagged_cognitive ----
    def test_cortex_tagged_cognitive(self):
        app = self._make_app_with_echo("/api/cortex/test")
        with TestClient(app) as client:
            resp = client.get("/api/cortex/test")
            assert resp.status_code == 200
            data = resp.json()
            assert data["priority"] == "cognitive"
            assert data["urgency"] == 0.9
            assert resp.headers["x-brain-priority"] == "cognitive"
            assert "x-brain-latency-ms" in resp.headers

    # ---- test_introspect_tagged_low ----
    def test_introspect_tagged_low(self):
        app = self._make_app_with_echo("/api/introspect/deep")
        with TestClient(app) as client:
            resp = client.get("/api/introspect/deep")
            assert resp.status_code == 200
            data = resp.json()
            assert data["priority"] == "introspective"
            assert data["urgency"] == 0.3

    # ---- test_train_tagged_background ----
    def test_train_tagged_background(self):
        app = self._make_app_with_echo("/api/train/anything")
        with TestClient(app) as client:
            resp = client.get("/api/train/anything")
            assert resp.status_code == 200
            data = resp.json()
            assert data["priority"] == "cerebellar"
            assert data["urgency"] == 0.1


# ======================================================================
# Task 4 — Training Router
# ======================================================================

class TestTrainingRouter:
    """Data-sink endpoints for Klotski and Evolutionary training."""

    def setup_method(self):
        self.app = create_app(testing=True)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def teardown_method(self):
        self.client.__exit__(None, None, None)

    # ----------------------------------------------------------------
    # Klotski
    # ----------------------------------------------------------------

    def test_klotski_status(self):
        resp = self.client.get("/api/train/klotski/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "idle"
        assert data["epoch"] == 0

    def test_klotski_update(self):
        resp = self.client.post(
            "/api/train/klotski/update",
            json={"status": "running", "epoch": 5, "loss": 0.42},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["klotski"]["status"] == "running"
        assert data["klotski"]["epoch"] == 5
        assert data["klotski"]["loss"] == 0.42

    def test_klotski_agent(self):
        resp = self.client.post(
            "/api/train/klotski/agent",
            json={"agent_id": "spatial_1", "score": 0.88},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["agent_id"] == "spatial_1"

        # Verify agent persisted in state
        status = self.client.get("/api/train/klotski/status").json()
        assert "spatial_1" in status["agents"]

    def test_klotski_reset(self):
        # Mutate, then reset
        self.client.post(
            "/api/train/klotski/update",
            json={"status": "running", "epoch": 99},
        )
        resp = self.client.post("/api/train/klotski/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["status"] == "reset"

        # Verify state is clean
        status = self.client.get("/api/train/klotski/status").json()
        assert status["status"] == "idle"
        assert status["epoch"] == 0

    # ----------------------------------------------------------------
    # Evolutionary
    # ----------------------------------------------------------------

    def test_evolutionary_status(self):
        resp = self.client.get("/api/train/evolutionary/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "idle"
        assert data["generation"] == 0
        assert isinstance(data["messages"], list)  # deque serialised as list

    def test_evolutionary_positions(self):
        positions = [{"x": 1, "y": 2}, {"x": 3, "y": 4}]
        resp = self.client.post(
            "/api/train/evolutionary/positions",
            json={"positions": positions},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["count"] == 2

    def test_evolutionary_metrics(self):
        resp = self.client.post(
            "/api/train/evolutionary/metrics",
            json={"fitness": 0.95, "diversity": 0.7},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["metrics"]["fitness"] == 0.95

    def test_evolutionary_message(self):
        resp = self.client.post(
            "/api/train/evolutionary/message",
            json={"message": "Generation 1 complete"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["queue_size"] == 1

    def test_evolutionary_message_queue_capped(self):
        """Messages deque is capped at 100."""
        for i in range(105):
            self.client.post(
                "/api/train/evolutionary/message",
                json={"message": f"msg-{i}"},
            )
        status = self.client.get("/api/train/evolutionary/status").json()
        assert len(status["messages"]) == 100

    def test_evolutionary_reset(self):
        self.client.post(
            "/api/train/evolutionary/metrics",
            json={"fitness": 0.99},
        )
        resp = self.client.post("/api/train/evolutionary/reset")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        status = self.client.get("/api/train/evolutionary/status").json()
        assert status["status"] == "idle"
        assert status["metrics"] == {}

    # ----------------------------------------------------------------
    # Training UI pages
    # ----------------------------------------------------------------

    def test_klotski_ui(self):
        resp = self.client.get("/ui/training/klotski")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_evolutionary_ui(self):
        resp = self.client.get("/ui/training/evolutionary")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


# ======================================================================
# Task 5 — Oscillator Router
# ======================================================================

class TestOscillatorRouter:
    """Oscillator endpoints with oscillator=None (testing mode)."""

    def setup_method(self):
        self.app = create_app(testing=True)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def teardown_method(self):
        self.client.__exit__(None, None, None)

    # ---- state returns graceful None ----
    def test_oscillator_state_none(self):
        resp = self.client.get("/api/oscillator/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] is None
        assert "message" in data
        assert "not initialized" in data["message"]

    # ---- history returns empty list ----
    def test_oscillator_history_empty(self):
        resp = self.client.get("/api/oscillator/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["history"] == []
        assert data["count"] == 0
        assert "timestamp" in data

    # ---- tokens returns 503 when not init ----
    def test_oscillator_tokens_not_init(self):
        resp = self.client.post(
            "/api/oscillator/tokens", json={"text": "hello world"}
        )
        assert resp.status_code == 503
        assert "not initialized" in resp.json()["error"]

    # ---- tokens validates missing text ----
    def test_oscillator_tokens_missing_text(self):
        """Even if oscillator were present, empty text is rejected.
        But since oscillator is None, 503 fires first."""
        resp = self.client.post("/api/oscillator/tokens", json={"text": ""})
        assert resp.status_code == 503

    # ---- stats returns graceful None ----
    def test_oscillator_stats_none(self):
        resp = self.client.get("/api/oscillator/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stats"] is None
        assert "message" in data

    # ---- route returns 503 when not init ----
    def test_oscillator_route_not_init(self):
        resp = self.client.post(
            "/api/oscillator/route",
            json={"events": [{"type": "test"}], "task": "testing"},
        )
        assert resp.status_code == 503
        assert "not initialized" in resp.json()["error"]

    # ---- checkpoint save returns 503 when not init ----
    def test_oscillator_checkpoint_save_not_init(self):
        resp = self.client.post(
            "/api/oscillator/checkpoint", json={"name": "test_ckpt"}
        )
        assert resp.status_code == 503

    # ---- checkpoint list returns empty when not init ----
    def test_oscillator_checkpoints_list_not_init(self):
        resp = self.client.get("/api/oscillator/checkpoints")
        assert resp.status_code == 200
        data = resp.json()
        assert data["checkpoints"] == []
        assert "message" in data

    # ---- restore returns 503 when not init ----
    def test_oscillator_restore_not_init(self):
        resp = self.client.post(
            "/api/oscillator/restore", json={"name": "some_checkpoint"}
        )
        assert resp.status_code == 503

    # ---- reset returns 503 when not init ----
    def test_oscillator_reset_not_init(self):
        resp = self.client.post("/api/oscillator/reset")
        assert resp.status_code == 503

    # ---- health returns not_initialized ----
    def test_oscillator_health_not_init(self):
        resp = self.client.get("/api/oscillator/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_initialized"
        assert data["router_initialized"] is False
        assert data["checkpoint_manager"] is False
        assert data["history_size"] == 0
        assert "timestamp" in data

    # ---- oscillator UI page ----
    def test_oscillator_ui(self):
        resp = self.client.get("/ui/oscillator")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


# ======================================================================
# Task 6 — Swarm Router
# ======================================================================

class TestSwarmRouter:
    """Swarm endpoints with swarm_orchestrator=None (testing mode)."""

    def setup_method(self):
        self.app = create_app(testing=True)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def teardown_method(self):
        self.client.__exit__(None, None, None)

    # ---- execute returns 503 when not init ----
    def test_swarm_execute_not_init(self):
        resp = self.client.post(
            "/api/swarm/execute", json={"task": "do something"}
        )
        assert resp.status_code == 503
        assert "not initialized" in resp.json()["error"]

    # ---- execute validates missing task ----
    def test_swarm_execute_missing_task(self):
        """No task -> 503 because orchestrator is None (checked first)."""
        resp = self.client.post("/api/swarm/execute", json={"task": ""})
        assert resp.status_code == 503

    # ---- logs returns empty list ----
    def test_swarm_logs_empty(self):
        resp = self.client.get("/api/swarm/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["execution_log"] == []
        assert data["count"] == 0
        assert "timestamp" in data

    # ---- stats returns graceful None ----
    def test_swarm_stats_not_init(self):
        resp = self.client.get("/api/swarm/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stats"] is None
        assert "message" in data

    # ---- health returns not_initialized ----
    def test_swarm_health_not_init(self):
        resp = self.client.get("/api/swarm/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_initialized"
        assert data["orchestrator_initialized"] is False
        assert data["log_count"] == 0
        assert "timestamp" in data

    # ---- swarm UI page ----
    def test_swarm_ui(self):
        resp = self.client.get("/ui/swarm")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    # ---- swarm_logs attribute exists on state ----
    def test_swarm_logs_state_attribute(self):
        """Verify swarm_logs is properly initialised on app.state."""
        assert hasattr(self.app.state, "swarm_logs")
        assert isinstance(self.app.state.swarm_logs, list)


# ======================================================================
# Task 7 — Introspection Router
# ======================================================================

class TestIntrospectionRouter:
    """Introspection endpoints with all modules=None (testing mode)."""

    def setup_method(self):
        self.app = create_app(testing=True)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def teardown_method(self):
        self.client.__exit__(None, None, None)

    # ----------------------------------------------------------------
    # Group 1 — Brain State
    # ----------------------------------------------------------------

    def test_brain_state_none(self):
        """GET /api/brain/state returns graceful None when meta_router absent."""
        resp = self.client.get("/api/brain/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] is None
        assert "message" in data
        assert "not initialized" in data["message"]
        assert "timestamp" in data

    def test_brain_gates_none(self):
        """GET /api/brain/gates returns graceful None when brain_monitor absent."""
        resp = self.client.get("/api/brain/gates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["gates"] is None
        assert "not initialized" in data["message"]

    def test_brain_activation_none(self):
        """GET /api/brain/activation returns graceful None."""
        resp = self.client.get("/api/brain/activation")
        assert resp.status_code == 200
        data = resp.json()
        assert data["activation"] is None

    def test_brain_strategies_none(self):
        """GET /api/brain/strategies returns graceful None."""
        resp = self.client.get("/api/brain/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["strategies"] is None

    def test_brain_interventions_empty(self):
        """GET /api/brain/interventions returns empty list."""
        resp = self.client.get("/api/brain/interventions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["interventions"] == []

    # ----------------------------------------------------------------
    # Group 2 — Proxy fallbacks
    # ----------------------------------------------------------------

    def test_cognitive_loop_fallback(self):
        """GET /api/brain/cognitive_loop returns enabled=False."""
        resp = self.client.get("/api/brain/cognitive_loop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["state"] is None
        assert "timestamp" in data

    def test_agent_loop_state_fallback(self):
        """GET /api/brain/agent_loop_state returns enabled=False."""
        resp = self.client.get("/api/brain/agent_loop_state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["state"] is None

    def test_agent_loop_submit_503(self):
        """POST /api/brain/agent_loop/submit returns 503."""
        resp = self.client.post(
            "/api/brain/agent_loop/submit", json={"task": "test"}
        )
        assert resp.status_code == 503

    def test_emotional_state_fallback(self):
        """GET /api/brain/emotional_state returns enabled=False."""
        resp = self.client.get("/api/brain/emotional_state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False

    def test_homeostatic_state_fallback(self):
        """GET /api/brain/homeostatic_state returns enabled=False."""
        resp = self.client.get("/api/brain/homeostatic_state")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_memory_state_fallback(self):
        """GET /api/brain/memory_state returns enabled=False."""
        resp = self.client.get("/api/brain/memory_state")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_heartbeat_status_fallback(self):
        """GET /api/brain/heartbeat_status returns active=False."""
        resp = self.client.get("/api/brain/heartbeat_status")
        assert resp.status_code == 200
        assert resp.json()["active"] is False

    def test_consciousness_state_fallback(self):
        """GET /api/brain/consciousness_state returns enabled=False."""
        resp = self.client.get("/api/brain/consciousness_state")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_neuromodulation_state_fallback(self):
        """GET /api/brain/neuromodulation_state returns enabled=False."""
        resp = self.client.get("/api/brain/neuromodulation_state")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    # ----------------------------------------------------------------
    # Group 3 — Monitoring & Observability
    # ----------------------------------------------------------------

    def test_metrics_plain_text(self):
        """GET /api/brain/metrics returns plain text fallback."""
        resp = self.client.get("/api/brain/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "Metrics unavailable" in resp.text

    def test_metrics_json_fallback(self):
        """GET /api/brain/metrics_json returns error JSON."""
        resp = self.client.get("/api/brain/metrics_json")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert data["error"] == "metrics unavailable"

    def test_audit_trail_empty(self):
        """GET /api/brain/audit_trail returns empty recent list."""
        resp = self.client.get("/api/brain/audit_trail")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recent"] == []
        assert data["stats"] == {}

    def test_loop_traces_empty(self):
        """GET /api/brain/loop_traces returns empty traces."""
        resp = self.client.get("/api/brain/loop_traces")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recent_traces"] == []
        assert data["total_traces"] == 0

    def test_error_rates_empty(self):
        """GET /api/brain/error_rates returns empty."""
        resp = self.client.get("/api/brain/error_rates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["error_rates"] == {}
        assert data["recent_errors"] == []

    def test_heatmap_empty(self):
        """GET /api/brain/heatmap returns empty modality data."""
        resp = self.client.get("/api/brain/heatmap")
        assert resp.status_code == 200
        data = resp.json()
        assert data["heatmap"]["modalities"] == []
        assert data["heatmap"]["matrix"] == []
        assert data["modality_averages"] == {}

    # ----------------------------------------------------------------
    # Group 4 — Frequency Controller
    # ----------------------------------------------------------------

    def test_frequency_none(self):
        """GET /api/brain/frequency returns graceful None."""
        resp = self.client.get("/api/brain/frequency")
        assert resp.status_code == 200
        data = resp.json()
        assert data["frequency"] is None
        assert "not initialized" in data["message"]

    def test_frequency_set_none(self):
        """POST /api/brain/frequency/set returns ok=False when not init."""
        resp = self.client.post(
            "/api/brain/frequency/set", json={"band": "alpha"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False

    def test_frequency_bands_none(self):
        """GET /api/brain/frequency/bands returns graceful None."""
        resp = self.client.get("/api/brain/frequency/bands")
        assert resp.status_code == 200
        assert resp.json()["bands"] is None

    def test_frequency_markers_none(self):
        """GET /api/brain/frequency/markers returns graceful None."""
        resp = self.client.get("/api/brain/frequency/markers")
        assert resp.status_code == 200
        assert resp.json()["markers"] is None

    # ----------------------------------------------------------------
    # Group 5 — Health
    # ----------------------------------------------------------------

    def test_health_components(self):
        """GET /api/health/components returns all components=False in testing."""
        resp = self.client.get("/api/health/components")
        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] == 0
        assert data["status"] == "not_initialized"
        assert "components" in data
        # All should be False in testing mode
        for name, val in data["components"].items():
            assert val is False, f"{name} should be False in testing"

    def test_health_dependencies(self):
        """GET /api/health/dependencies returns dependency info."""
        resp = self.client.get("/api/health/dependencies")
        assert resp.status_code == 200
        data = resp.json()
        assert "dependencies" in data

    def test_health_readiness(self):
        """GET /api/health/readiness always returns ready=True."""
        resp = self.client.get("/api/health/readiness")
        assert resp.status_code == 200
        assert resp.json()["ready"] is True

    def test_health_liveness(self):
        """GET /api/health/liveness always returns alive=True."""
        resp = self.client.get("/api/health/liveness")
        assert resp.status_code == 200
        assert resp.json()["alive"] is True

    # ----------------------------------------------------------------
    # Group 6 — LLM Stats
    # ----------------------------------------------------------------

    def test_llm_stats_503(self):
        """GET /api/llm/stats returns 503 when llm_router is None."""
        resp = self.client.get("/api/llm/stats")
        assert resp.status_code == 503
        assert "not initialized" in resp.json()["error"]

    # ----------------------------------------------------------------
    # Group 7 — Goals / Evolution / CTM
    # ----------------------------------------------------------------

    def test_goals_fallback(self):
        """GET /api/brain/goals returns enabled=False."""
        resp = self.client.get("/api/brain/goals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["goals"] == []

    def test_goals_add_503(self):
        """POST /api/brain/goals/add returns 503."""
        resp = self.client.post(
            "/api/brain/goals/add", json={"goal": "test goal"}
        )
        assert resp.status_code == 503

    def test_goals_complete_503(self):
        """POST /api/brain/goals/{id}/complete returns 503."""
        resp = self.client.post("/api/brain/goals/g1/complete")
        assert resp.status_code == 503
        assert resp.json()["goal_id"] == "g1"

    def test_evolution_fallback(self):
        """GET /api/brain/evolution returns enabled=False."""
        resp = self.client.get("/api/brain/evolution")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_evolution_evolve_503(self):
        """POST /api/brain/evolution/evolve returns 503."""
        resp = self.client.post("/api/brain/evolution/evolve")
        assert resp.status_code == 503

    def test_ctm_health_fallback(self):
        """GET /api/brain/ctm_health returns enabled=False."""
        resp = self.client.get("/api/brain/ctm_health")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_cognitive_status_fallback(self):
        """GET /api/brain/cognitive_status returns enabled=False."""
        resp = self.client.get("/api/brain/cognitive_status")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    # ----------------------------------------------------------------
    # Group 8 — Causal / Meta / Federated
    # ----------------------------------------------------------------

    def test_causal_status_503(self):
        """GET /api/causal/status returns 503."""
        resp = self.client.get("/api/causal/status")
        assert resp.status_code == 503

    def test_causal_graph_503(self):
        """GET /api/causal/graph returns 503."""
        resp = self.client.get("/api/causal/graph")
        assert resp.status_code == 503

    def test_meta_status_503(self):
        """GET /api/meta/status returns 503."""
        resp = self.client.get("/api/meta/status")
        assert resp.status_code == 503

    def test_federated_status_503(self):
        """GET /api/federated/status returns 503."""
        resp = self.client.get("/api/federated/status")
        assert resp.status_code == 503

    def test_advanced_learning_health_503(self):
        """GET /api/advanced_learning/health returns 503."""
        resp = self.client.get("/api/advanced_learning/health")
        assert resp.status_code == 503

    # ----------------------------------------------------------------
    # Group 9 — Conversation / Simulate
    # ----------------------------------------------------------------

    def test_conversation_active_empty(self):
        """GET /api/conversation/active returns empty when not init."""
        resp = self.client.get("/api/conversation/active")
        assert resp.status_code == 200
        data = resp.json()
        assert data["conversations"] == []

    def test_simulate_conversation_503(self):
        """POST /api/simulate/conversation returns 503."""
        resp = self.client.post(
            "/api/simulate/conversation", json={"prompt": "hello"}
        )
        assert resp.status_code == 503

    # ----------------------------------------------------------------
    # Group 10 — Predict Path
    # ----------------------------------------------------------------

    def test_predict_path_none(self):
        """POST /api/predict/path returns graceful None when planner absent."""
        resp = self.client.post(
            "/api/predict/path", json={"task": "deploy"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] is None
        assert "not initialized" in data["message"]


# ======================================================================
# Task 8 — Knowledge Router
# ======================================================================

class TestKnowledgeRouter:
    """Knowledge/Moltbook endpoints with store=None and agents={} (testing mode)."""

    def setup_method(self):
        self.app = create_app(testing=True)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def teardown_method(self):
        self.client.__exit__(None, None, None)

    # ----------------------------------------------------------------
    # Knowledge Store Routes
    # ----------------------------------------------------------------

    def test_knowledge_state_empty(self):
        """GET /api/knowledge/state returns 200 with empty store data."""
        resp = self.client.get("/api/knowledge/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["store"]["total_entries"] == 0
        assert data["feeder"] == {}
        assert data["evaluation"] == {}
        assert data["curation"] == {}
        assert data["research"] == {}
        assert data["feedback"] == {}
        assert data["forum"] == {}
        assert "message" in data
        assert "not initialized" in data["message"]
        assert "timestamp" in data

    def test_knowledge_entries_empty(self):
        """GET /api/knowledge/entries returns empty list when store is None."""
        resp = self.client.get("/api/knowledge/entries")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"] == []
        assert data["count"] == 0
        assert "message" in data

    def test_knowledge_search_no_store(self):
        """POST /api/knowledge/search returns 503 when store is None."""
        resp = self.client.post(
            "/api/knowledge/search", json={"query": "hello", "top_k": 5}
        )
        assert resp.status_code == 503
        assert "not initialized" in resp.json()["error"]

    def test_knowledge_search_no_query(self):
        """POST /api/knowledge/search with empty query returns 400 (if store were present)
        but 503 fires first since store is None."""
        resp = self.client.post(
            "/api/knowledge/search", json={"query": ""}
        )
        # Store is None, so 503 fires before query validation
        assert resp.status_code == 503

    def test_knowledge_feed_no_store(self):
        """POST /api/knowledge/feed returns 503 when feeder agent absent."""
        resp = self.client.post(
            "/api/knowledge/feed",
            json={"content": "some knowledge", "tags": ["test"]},
        )
        assert resp.status_code == 503
        assert "feeder" in resp.json()["error"]

    def test_knowledge_feed_no_content(self):
        """POST /api/knowledge/feed with empty content returns 503
        (feeder not init checked first)."""
        resp = self.client.post(
            "/api/knowledge/feed", json={"content": ""}
        )
        assert resp.status_code == 503

    def test_knowledge_evaluate_no_agent(self):
        """POST /api/knowledge/evaluate returns 503 when evaluator absent."""
        resp = self.client.post(
            "/api/knowledge/evaluate", json={"entry_id": "abc123"}
        )
        assert resp.status_code == 503
        assert "evaluator" in resp.json()["error"]

    def test_knowledge_curate_no_agent(self):
        """POST /api/knowledge/curate returns 503 when curator absent."""
        resp = self.client.post("/api/knowledge/curate")
        assert resp.status_code == 503
        assert "curator" in resp.json()["error"]

    def test_knowledge_feedback_no_agent(self):
        """POST /api/knowledge/feedback returns 503 when feedback agent absent."""
        resp = self.client.post(
            "/api/knowledge/feedback",
            json={"sentiment": 0.5, "entry_ids": [], "correction": None},
        )
        assert resp.status_code == 503
        assert "feedback" in resp.json()["error"]

    def test_knowledge_research_no_agent(self):
        """POST /api/knowledge/research returns 503 when researcher absent."""
        resp = self.client.post("/api/knowledge/research")
        assert resp.status_code == 503
        assert "researcher" in resp.json()["error"]

    def test_knowledge_debug_empty(self):
        """GET /api/knowledge/debug returns fallback when no debug_stream."""
        resp = self.client.get("/api/knowledge/debug")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["entries"] == []
        assert data["formatted"] == ""

    # ----------------------------------------------------------------
    # Forum Routes
    # ----------------------------------------------------------------

    def test_knowledge_forum_discuss_no_agent(self):
        """POST /api/knowledge/forum/discuss returns 503 when forum absent."""
        resp = self.client.post(
            "/api/knowledge/forum/discuss", json={"query": "AI ethics"}
        )
        assert resp.status_code == 503
        assert "forum" in resp.json()["error"]

    def test_knowledge_forum_history_empty(self):
        """GET /api/knowledge/forum/history returns empty when forum absent."""
        resp = self.client.get("/api/knowledge/forum/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["discussions"] == []
        assert data["total"] == 0
        assert "message" in data

    # ----------------------------------------------------------------
    # Graph Route
    # ----------------------------------------------------------------

    def test_knowledge_graph_empty(self):
        """GET /api/knowledge/graph returns empty nodes/edges when store is None."""
        resp = self.client.get("/api/knowledge/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert data["nodes"] == []
        assert data["edges"] == []

    # ----------------------------------------------------------------
    # Dashboard UI
    # ----------------------------------------------------------------

    def test_moltbook_ui(self):
        """GET /ui/moltbook returns 200 with HTML content."""
        resp = self.client.get("/ui/moltbook")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


# ======================================================================
# Task 9 — Cortex Router
# ======================================================================

class TestCortexRouter:
    """Cortex endpoints with brain_chat=None and continuous_thinking=None (testing mode)."""

    def setup_method(self):
        self.app = create_app(testing=True)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def teardown_method(self):
        self.client.__exit__(None, None, None)

    # ----------------------------------------------------------------
    # Chat
    # ----------------------------------------------------------------

    def test_cortex_chat_no_brain(self):
        """POST /api/cortex/chat returns 503 when brain_chat is None."""
        resp = self.client.post(
            "/api/cortex/chat", json={"message": "hello"}
        )
        assert resp.status_code == 503
        assert "not initialized" in resp.json()["error"]

    def test_cortex_chat_no_message(self):
        """POST /api/cortex/chat with empty message returns 503
        (brain_chat None check fires first)."""
        resp = self.client.post(
            "/api/cortex/chat", json={"message": ""}
        )
        assert resp.status_code == 503

    # ----------------------------------------------------------------
    # Thoughts
    # ----------------------------------------------------------------

    def test_cortex_thoughts_empty(self):
        """GET /api/cortex/thoughts returns 200 with empty thoughts when CTE is None."""
        resp = self.client.get("/api/cortex/thoughts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["thoughts"] == []
        assert data["stats"] == {}
        assert data["thinking"] is False

    def test_cortex_thoughts_with_params(self):
        """GET /api/cortex/thoughts?n=5&since=0 returns 200 with empty."""
        resp = self.client.get("/api/cortex/thoughts?n=5&since=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["thoughts"] == []
        assert data["thinking"] is False

    # ----------------------------------------------------------------
    # State
    # ----------------------------------------------------------------

    def test_cortex_state_empty(self):
        """GET /api/cortex/state returns 200 with empty stats."""
        resp = self.client.get("/api/cortex/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["brain_chat"] == {}
        assert data["continuous_thinking"] == {}
        assert data["recent_thoughts"] == []

    def test_cortex_state_has_timestamp(self):
        """GET /api/cortex/state has timestamp field."""
        resp = self.client.get("/api/cortex/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "timestamp" in data
        # Should be a valid ISO timestamp string
        assert "T" in data["timestamp"]


# ======================================================================
# Task 10 — Consciousness WebSocket Stream
# ======================================================================

class TestConsciousnessStream:
    """WebSocket /ws/consciousness stream tests."""

    def setup_method(self):
        self.app = create_app(testing=True)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def teardown_method(self):
        self.client.__exit__(None, None, None)

    def test_websocket_connects(self):
        """WS /ws/consciousness connects and receives first frame."""
        with self.client.websocket_connect("/ws/consciousness") as ws:
            data = ws.receive_json()
            assert "timestamp" in data
            assert "thoughts" in data
            assert "gates" in data
            assert "oscillator" in data
            assert isinstance(data["thoughts"], list)
            assert data["thoughts"] == []  # No CTE in testing

    def test_websocket_receives_multiple(self):
        """WS /ws/consciousness sends multiple frames (2 Hz)."""
        with self.client.websocket_connect("/ws/consciousness") as ws:
            frame1 = ws.receive_json()
            frame2 = ws.receive_json()
            assert frame1["timestamp"] <= frame2["timestamp"]

    def test_websocket_empty_state_in_testing(self):
        """All state is empty when no production modules loaded."""
        with self.client.websocket_connect("/ws/consciousness") as ws:
            data = ws.receive_json()
            assert data["thoughts"] == []
            assert data["gates"] == {}
            assert data["oscillator"] == {}


# ======================================================================
# Task 11 — Chat WebSocket Stream
# ======================================================================

class TestChatStream:
    """WebSocket /ws/chat stream tests."""

    def setup_method(self):
        self.app = create_app(testing=True)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def teardown_method(self):
        self.client.__exit__(None, None, None)

    def test_websocket_connects(self):
        """WS /ws/chat connects and accepts a message."""
        with self.client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"message": "hello"})
            data = ws.receive_json()
            # brain_chat is None in testing -> error response
            assert "error" in data
            assert data["done"] is True

    def test_websocket_no_message(self):
        """WS /ws/chat with empty message returns error."""
        with self.client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"message": ""})
            data = ws.receive_json()
            assert "error" in data
            assert data["done"] is True

    def test_websocket_brain_not_initialized(self):
        """WS /ws/chat with valid message but no brain_chat returns error."""
        with self.client.websocket_connect("/ws/chat") as ws:
            ws.send_json({"message": "What is consciousness?"})
            data = ws.receive_json()
            assert "brain chat not initialized" in data["error"]
            assert data["done"] is True


# ======================================================================
# Task 12 — UI Routes
# ======================================================================

class TestUIRoutes:
    """All dashboard UI routes serve HTML."""

    def setup_method(self):
        self.app = create_app(testing=True)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def teardown_method(self):
        self.client.__exit__(None, None, None)

    def test_root_dashboard(self):
        """GET / returns brain dashboard HTML."""
        resp = self.client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_ui_brain(self):
        """GET /ui/brain returns brain dashboard HTML."""
        resp = self.client.get("/ui/brain")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_ui_moltbook(self):
        """GET /ui/moltbook returns moltbook dashboard HTML."""
        resp = self.client.get("/ui/moltbook")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_ui_oscillator(self):
        """GET /ui/oscillator returns oscillator dashboard HTML."""
        resp = self.client.get("/ui/oscillator")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_ui_swarm(self):
        """GET /ui/swarm returns swarm dashboard HTML."""
        resp = self.client.get("/ui/swarm")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_ui_training_klotski(self):
        """GET /ui/training/klotski returns training dashboard HTML."""
        resp = self.client.get("/ui/training/klotski")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_ui_training_evolutionary(self):
        """GET /ui/training/evolutionary returns training dashboard HTML."""
        resp = self.client.get("/ui/training/evolutionary")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


# ======================================================================
# Legacy Compatibility — 307 Redirects
# ======================================================================

class TestLegacyCompat:
    """Old Flask paths redirect to new unified paths via 307."""

    def setup_method(self):
        self.app = create_app(testing=True)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def teardown_method(self):
        self.client.__exit__(None, None, None)

    # -- Moltbook legacy paths --

    def test_legacy_state(self):
        """GET /api/state → /api/knowledge/state (200 after redirect)."""
        resp = self.client.get("/api/state")
        assert resp.status_code == 200
        assert "store" in resp.json()

    def test_legacy_entries(self):
        """GET /api/entries → /api/knowledge/entries (200 after redirect)."""
        resp = self.client.get("/api/entries?top_k=10")
        assert resp.status_code == 200
        assert "entries" in resp.json()

    def test_legacy_debug(self):
        """GET /api/debug → /api/knowledge/debug."""
        resp = self.client.get("/api/debug?n=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False

    def test_legacy_brain_thoughts(self):
        """GET /api/brain/thoughts → /api/cortex/thoughts."""
        resp = self.client.get("/api/brain/thoughts?n=10")
        assert resp.status_code == 200
        assert "thoughts" in resp.json()

    def test_legacy_brain_chat(self):
        """POST /api/brain/chat → /api/cortex/chat (503 in testing)."""
        resp = self.client.post("/api/brain/chat", json={"message": "hello"})
        assert resp.status_code == 503

    def test_legacy_brain_state(self):
        """GET /api/brain/state → /api/cortex/state."""
        resp = self.client.get("/api/brain/state")
        assert resp.status_code == 200
        assert "timestamp" in resp.json()

    def test_legacy_search(self):
        """POST /api/search → /api/knowledge/search (503 in testing)."""
        resp = self.client.post("/api/search", json={"query": "hello"})
        assert resp.status_code == 503

    # -- Swarm legacy paths --

    def test_legacy_swarm_stats(self):
        """GET /api/stats → /api/swarm/stats."""
        resp = self.client.get("/api/stats")
        assert resp.status_code == 200

    def test_legacy_swarm_execute(self):
        """POST /api/execute → /api/swarm/execute (503 in testing)."""
        resp = self.client.post("/api/execute", json={"task": "test"})
        assert resp.status_code == 503

    # -- Oscillator legacy --

    def test_legacy_token_stats(self):
        """GET /api/token/stats → /api/oscillator/stats."""
        resp = self.client.get("/api/token/stats")
        assert resp.status_code == 200

    # -- Moltbook prefixed --

    def test_legacy_moltbook_state(self):
        """GET /api/moltbook/state → /api/knowledge/state."""
        resp = self.client.get("/api/moltbook/state")
        assert resp.status_code == 200
        assert "store" in resp.json()

    def test_legacy_research_cycle(self):
        """POST /api/research/cycle → /api/knowledge/research."""
        resp = self.client.post("/api/research/cycle")
        # Follows 307 → /api/knowledge/research → 503 (researcher not initialized)
        assert resp.status_code == 503
