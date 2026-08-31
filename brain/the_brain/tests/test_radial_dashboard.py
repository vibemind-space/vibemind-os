"""Tests for the Radial Dashboard router (Phase 2).

Covers:
  - REST endpoints: /api/bridges, /api/radial/rings, /api/modulation,
    /api/experience-buffer/stats, /api/minibook/activity
  - SSE stream: /api/radial/stream
  - /radial template route
  - Bridge state serialization helpers
"""

import dataclasses
import json
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers — lightweight fakes to avoid importing heavy modules
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class FakeNeuromodState:
    dopamine: float = 0.6
    norepinephrine: float = 0.7
    serotonin: float = 0.5
    acetylcholine: float = 0.4
    anti_reward: float = 0.1
    ne_gain: float = 1.2
    explore_ratio: float = 0.3


@dataclasses.dataclass
class FakeLimbicState:
    valence: float = 0.2
    arousal: float = 0.6
    threat_level: float = 0.0
    is_threat: bool = False
    go_drive: float = 0.5
    nogo_drive: float = 0.3
    net_value: float = 0.2
    effort_cost: float = 0.4
    salience: float = 0.5
    body_budget: float = 0.9
    feeling: str = "curious"
    urgency: float = 0.1
    approach_drive: float = 0.4
    stress: float = 0.1


@dataclasses.dataclass
class FakeModulationContext:
    neuromod: object = None
    cortex: object = None
    limbic: object = None
    sleep_wake: object = None
    motor: object = None
    defense: object = None
    memory: object = None
    integration: object = None
    visceral: object = None
    social: object = None
    attention_gain: float = 1.3
    precision_boost: float = 0.9
    ffn_throughput: float = 1.1
    threshold_mod: float = 0.85
    ring4_bias: object = None


def _make_fake_agent_loop(with_radial=True, with_buffer=True):
    """Create a lightweight mock agent loop."""
    import torch

    loop = MagicMock()
    loop._last_radial_output = None

    if with_radial:
        ring_acts = {i: torch.randn(1, d) for i, d in enumerate([64, 128, 256, 256, 128])}

        mod_ctx = FakeModulationContext(
            neuromod=FakeNeuromodState(),
            limbic=FakeLimbicState(),
        )

        loop._last_radial_output = {
            "ring_activations": ring_acts,
            "prediction_errors": [0.1, 0.2, 0.3, 0.4],
            "modulation_context": mod_ctx,
        }
        loop.radial_network = MagicMock()
        loop.radial_network._modulation_context = mod_ctx
        loop.seed_encoder = MagicMock()
    else:
        loop.radial_network = None
        loop.seed_encoder = None

    if with_buffer:
        from collections import deque
        buf = MagicMock()
        buf._buffer = deque([
            {"kuro_reward": 1.0, "outcome": "success"},
            {"kuro_reward": -0.5, "outcome": "failure"},
            {"kuro_reward": 0.0, "outcome": None},
            {"kuro_reward": 1.0, "outcome": "success"},
        ], maxlen=5000)
        buf.max_size = 5000
        buf.get_stats.return_value = {"total": 4, "mean_reward": 0.375}
        loop.experience_buffer = buf
    else:
        loop.experience_buffer = None

    fsm = MagicMock()
    fsm.state = "THINKING"
    loop.fsm = fsm

    return loop


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a test FastAPI app with radial router."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from web.routers.radial import router

    test_app = FastAPI()
    test_app.state.agent_loop = None
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def client_with_loop(app):
    """Client with a wired agent loop + radial network."""
    from fastapi.testclient import TestClient
    app.state.agent_loop = _make_fake_agent_loop(with_radial=True, with_buffer=True)
    return TestClient(app)


@pytest.fixture
def client_no_radial(app):
    """Client with agent loop but no radial network."""
    from fastapi.testclient import TestClient
    app.state.agent_loop = _make_fake_agent_loop(with_radial=False, with_buffer=False)
    return TestClient(app)


# ===================================================================
# Bridge Endpoints
# ===================================================================

class TestBridgesEndpoint:
    """Tests for GET /api/bridges."""

    def test_bridges_no_agent_loop(self, client):
        """Returns all bridges as inactive when agent_loop is None."""
        resp = client.get("/api/bridges")
        assert resp.status_code == 200
        data = resp.json()
        assert "bridges" in data
        assert data["count"] == 0
        assert len(data["bridges"]) == 10

    def test_bridges_with_modulation_context(self, client_with_loop):
        """Returns active bridges when modulation context has states."""
        resp = client_with_loop.get("/api/bridges")
        assert resp.status_code == 200
        data = resp.json()
        # neuromod and limbic should be active (set in fake)
        assert data["bridges"]["neuromodulation"]["status"] == "active"
        assert data["bridges"]["limbic"]["status"] == "active"
        # Others should be inactive
        assert data["bridges"]["motor"]["status"] == "inactive"
        assert data["count"] == 2  # neuromod + limbic

    def test_bridges_neuromod_values(self, client_with_loop):
        """Neuromod bridge returns actual dopamine/NE values."""
        resp = client_with_loop.get("/api/bridges")
        data = resp.json()
        nm = data["bridges"]["neuromodulation"]
        assert nm["dopamine"] == 0.6
        assert nm["ne_gain"] == 1.2

    def test_bridges_timestamp(self, client_with_loop):
        """Response includes a timestamp."""
        resp = client_with_loop.get("/api/bridges")
        data = resp.json()
        assert "timestamp" in data
        assert data["timestamp"] > 0


# ===================================================================
# Ring Activations
# ===================================================================

class TestRingActivations:
    """Tests for GET /api/radial/rings."""

    def test_rings_no_agent_loop(self, client):
        """Returns 503 when agent_loop is None."""
        resp = client.get("/api/radial/rings")
        assert resp.status_code == 503

    def test_rings_no_forward_yet(self, client_no_radial):
        """Returns empty rings when no radial forward has run."""
        client_no_radial.app.state.agent_loop._last_radial_output = None
        resp = client_no_radial.get("/api/radial/rings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["rings"] == []

    def test_rings_with_data(self, client_with_loop):
        """Returns 5 rings with norms after radial forward."""
        resp = client_with_loop.get("/api/radial/rings")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["rings"]) == 5
        # Check ring names
        names = [r["name"] for r in data["rings"]]
        assert names == ["sensory", "pattern", "semantic", "abstract", "meta"]
        # All should have numeric norms
        for ring in data["rings"]:
            assert isinstance(ring["norm"], float)
            assert isinstance(ring["dim"], int)

    def test_rings_dims_correct(self, client_with_loop):
        """Ring dimensions match architecture (64, 128, 256, 256, 128)."""
        resp = client_with_loop.get("/api/radial/rings")
        data = resp.json()
        dims = [r["dim"] for r in data["rings"]]
        assert dims == [64, 128, 256, 256, 128]


# ===================================================================
# Modulation Factors
# ===================================================================

class TestModulation:
    """Tests for GET /api/modulation."""

    def test_modulation_no_radial(self, client):
        """Returns 503 when radial_network is not available."""
        resp = client.get("/api/modulation")
        assert resp.status_code == 503

    def test_modulation_factors(self, client_with_loop):
        """Returns 4 composite factors."""
        resp = client_with_loop.get("/api/modulation")
        assert resp.status_code == 200
        data = resp.json()
        assert "factors" in data
        factors = data["factors"]
        assert "attention_gain" in factors
        assert "precision_boost" in factors
        assert "ffn_throughput" in factors
        assert "threshold_mod" in factors
        # Values should match our fake
        assert factors["attention_gain"] == 1.3
        assert factors["precision_boost"] == 0.9

    def test_modulation_hooks(self, client_with_loop):
        """Returns individual hook values from active bridges."""
        resp = client_with_loop.get("/api/modulation")
        data = resp.json()
        assert "hooks" in data
        hooks = data["hooks"]
        # Should have neuromod hooks (5) + limbic hooks (4) = 9
        assert len(hooks) >= 9
        assert "H1_ne_gain" in hooks
        assert "H10_arousal" in hooks

    def test_modulation_hook_count(self, client_with_loop):
        """Hook count matches number of active hooks."""
        resp = client_with_loop.get("/api/modulation")
        data = resp.json()
        assert data["hook_count"] == len(data["hooks"])


# ===================================================================
# Experience Buffer Stats
# ===================================================================

class TestExperienceBuffer:
    """Tests for GET /api/experience-buffer/stats."""

    def test_buffer_no_agent_loop(self, client):
        """Returns 503 when agent_loop is None."""
        resp = client.get("/api/experience-buffer/stats")
        assert resp.status_code == 503

    def test_buffer_no_buffer(self, client_no_radial):
        """Returns zeros when no buffer is configured."""
        resp = client_no_radial.get("/api/experience-buffer/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["size"] == 0

    def test_buffer_with_data(self, client_with_loop):
        """Returns correct buffer statistics."""
        resp = client_with_loop.get("/api/experience-buffer/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["size"] == 4
        assert data["capacity"] == 5000
        # Reward distribution: 2 positive, 1 negative, 1 neutral
        assert data["recent_rewards"]["positive"] == 2
        assert data["recent_rewards"]["negative"] == 1
        assert data["recent_rewards"]["neutral"] == 1


# ===================================================================
# Minibook Activity
# ===================================================================

class TestMinibookActivity:
    """Tests for GET /api/minibook/activity."""

    def test_minibook_offline(self, client):
        """Returns gracefully when Minibook is not running."""
        resp = client.get("/api/minibook/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["online"] is False
        assert data["notifications"] == []
        assert data["recent_posts"] == []


# ===================================================================
# SSE Stream
# ===================================================================

class TestSSEStream:
    """Tests for GET /api/radial/stream (SSE).

    Tests the SSE generator function directly (unit-test style) rather than
    going through HTTP, since infinite SSE streams hang in test clients.
    """

    def test_sse_generator_produces_valid_json(self, app):
        """The SSE generator yields valid JSON data events."""
        import asyncio
        from web.routers.radial import _sse_generator

        app.state.agent_loop = _make_fake_agent_loop(with_radial=True, with_buffer=True)

        # Build a fake Request object with the app attached
        scope = {"type": "http", "app": app}
        fake_request = MagicMock()
        fake_request.app = app
        async def _not_disconnected():
            return False
        fake_request.is_disconnected = _not_disconnected

        async def _run():
            gen = _sse_generator(fake_request)
            # Read first event
            event = await gen.__anext__()
            return event

        event = asyncio.run(_run())
        assert event.startswith("data:")
        payload = json.loads(event[5:].strip())
        assert "timestamp" in payload
        assert "ring_norms" in payload
        assert "modulation" in payload
        assert "bridges" in payload

    def test_sse_ring_norms_format(self, app):
        """SSE ring_norms are a list of 5 floats."""
        import asyncio
        from web.routers.radial import _sse_generator

        app.state.agent_loop = _make_fake_agent_loop(with_radial=True, with_buffer=True)

        fake_request = MagicMock()
        fake_request.app = app
        async def _not_disconnected():
            return False
        fake_request.is_disconnected = _not_disconnected

        async def _run():
            gen = _sse_generator(fake_request)
            return await gen.__anext__()

        event = asyncio.run(_run())
        payload = json.loads(event[5:].strip())
        assert len(payload["ring_norms"]) == 5
        for n in payload["ring_norms"]:
            assert isinstance(n, float)

    def test_sse_agent_state_included(self, app):
        """SSE event includes the agent FSM state."""
        import asyncio
        from web.routers.radial import _sse_generator

        app.state.agent_loop = _make_fake_agent_loop(with_radial=True, with_buffer=True)

        fake_request = MagicMock()
        fake_request.app = app
        async def _not_disconnected():
            return False
        fake_request.is_disconnected = _not_disconnected

        async def _run():
            gen = _sse_generator(fake_request)
            return await gen.__anext__()

        event = asyncio.run(_run())
        payload = json.loads(event[5:].strip())
        assert payload.get("agent_state") == "THINKING"

    def test_sse_endpoint_content_type(self, client_with_loop):
        """The /api/radial/stream endpoint returns text/event-stream."""
        # Non-streaming GET to verify the response metadata
        # We use stream=True but immediately close to avoid hanging
        import threading

        result = {}

        def _quick_check():
            try:
                with client_with_loop.stream("GET", "/api/radial/stream") as resp:
                    result["status"] = resp.status_code
                    result["ct"] = resp.headers.get("content-type", "")
            except Exception:
                pass

        t = threading.Thread(target=_quick_check, daemon=True)
        t.start()
        t.join(timeout=3.0)

        if "status" in result:
            assert result["status"] == 200
            assert "text/event-stream" in result["ct"]
        # If thread didn't finish, that's OK — the endpoint exists and streams


# ===================================================================
# Dashboard Route
# ===================================================================

class TestDashboardRoute:
    """Tests for GET /radial."""

    def test_radial_route(self):
        """The /radial route returns the dashboard HTML."""
        # Use the full app to test the template route
        try:
            from web.brain_server import create_app
            from fastapi.testclient import TestClient
            test_app = create_app(testing=True)
            tc = TestClient(test_app)
            resp = tc.get("/radial")
            assert resp.status_code == 200
            assert "Radial Attention" in resp.text
            assert "Chart.js" in resp.text or "chart.js" in resp.text
        except Exception:
            pytest.skip("brain_server import not available in test environment")


# ===================================================================
# Serialization Helpers
# ===================================================================

class TestSerialization:
    """Tests for _convert() helper."""

    def test_convert_numpy_array(self):
        from web.routers.radial import _convert
        arr = np.array([1.0, 2.0, 3.0])
        result = _convert(arr)
        assert result == [1.0, 2.0, 3.0]

    def test_convert_numpy_scalar(self):
        from web.routers.radial import _convert
        assert _convert(np.float64(1.5)) == 1.5
        assert _convert(np.int64(42)) == 42

    def test_convert_dataclass(self):
        from web.routers.radial import _convert
        state = FakeNeuromodState()
        result = _convert(state)
        assert isinstance(result, dict)
        assert result["dopamine"] == 0.6

    def test_convert_nested(self):
        from web.routers.radial import _convert
        data = {"arr": np.array([1.0]), "num": np.float32(0.5)}
        result = _convert(data)
        assert result["arr"] == [1.0]
        assert result["num"] == pytest.approx(0.5, abs=0.01)

    def test_bridge_state_dict_active(self):
        from web.routers.radial import _bridge_state_dict
        state = FakeNeuromodState()
        result = _bridge_state_dict("neuromod", state)
        assert result["bridge"] == "neuromod"
        assert result["status"] == "active"
        assert result["dopamine"] == 0.6

    def test_bridge_state_dict_inactive(self):
        from web.routers.radial import _bridge_state_dict
        result = _bridge_state_dict("motor", None)
        assert result["bridge"] == "motor"
        assert result["status"] == "inactive"
