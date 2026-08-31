import httpx
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

import app as app_module


def _fake_status_error(cls, status_code, message="error"):
    """Build a real openai APIStatusError subclass instance with a given
    HTTP status code, so app.py's isinstance/status_code checks see a
    realistic object instead of a MagicMock."""
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    response = httpx.Response(status_code, request=request)
    return cls(message, response=response, body=None)


def test_health_ok_when_api_key_present(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    app_module._client = None  # reset the lazy singleton between tests
    client = TestClient(app_module.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_503_when_no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)
    app_module._client = None
    client = TestClient(app_module.app)
    resp = client.get("/health")
    assert resp.status_code == 503


class _FakeEmbeddingDatum:
    def __init__(self, vector):
        self.embedding = vector


class _FakeEmbeddingResponse:
    def __init__(self, vectors):
        self.data = [_FakeEmbeddingDatum(v) for v in vectors]


def test_embed_returns_vector(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    app_module._client = None
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = _FakeEmbeddingResponse([[0.1, 0.2, 0.3]])
    monkeypatch.setattr(app_module, "get_client", lambda: fake_client)

    client = TestClient(app_module.app)
    resp = client.post("/embed", json={"text": "hello world"})

    assert resp.status_code == 200
    assert resp.json()["vector"] == [0.1, 0.2, 0.3]
    fake_client.embeddings.create.assert_called_once_with(
        model=app_module.MODEL, input=["hello world"],
    )


def test_embed_retries_then_succeeds_on_transient_error(monkeypatch):
    from openai import APIConnectionError

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    app_module._client = None
    fake_client = MagicMock()
    fake_request = MagicMock()
    fake_client.embeddings.create.side_effect = [
        APIConnectionError(request=fake_request),
        _FakeEmbeddingResponse([[0.4, 0.5]]),
    ]
    monkeypatch.setattr(app_module, "get_client", lambda: fake_client)
    monkeypatch.setattr(app_module.time, "sleep", lambda _seconds: None)

    client = TestClient(app_module.app)
    resp = client.post("/embed", json={"text": "retry me"})

    assert resp.status_code == 200
    assert resp.json()["vector"] == [0.4, 0.5]
    assert fake_client.embeddings.create.call_count == 2


def test_embed_hard_fails_after_exhausting_retries(monkeypatch):
    from openai import APIConnectionError

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    app_module._client = None
    fake_client = MagicMock()
    fake_request = MagicMock()
    fake_client.embeddings.create.side_effect = APIConnectionError(request=fake_request)
    monkeypatch.setattr(app_module, "get_client", lambda: fake_client)
    monkeypatch.setattr(app_module.time, "sleep", lambda _seconds: None)

    client = TestClient(app_module.app)
    resp = client.post("/embed", json={"text": "always fails"})

    assert resp.status_code == 502
    assert fake_client.embeddings.create.call_count == app_module.MAX_RETRIES + 1


def test_embed_retries_on_5xx_status_error(monkeypatch):
    from openai import InternalServerError

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    app_module._client = None
    fake_client = MagicMock()
    fake_client.embeddings.create.side_effect = [
        _fake_status_error(InternalServerError, 500),
        _FakeEmbeddingResponse([[0.6, 0.7]]),
    ]
    monkeypatch.setattr(app_module, "get_client", lambda: fake_client)
    monkeypatch.setattr(app_module.time, "sleep", lambda _seconds: None)

    client = TestClient(app_module.app)
    resp = client.post("/embed", json={"text": "server hiccup"})

    assert resp.status_code == 200
    assert resp.json()["vector"] == [0.6, 0.7]
    assert fake_client.embeddings.create.call_count == 2


def test_embed_retries_on_rate_limit_error(monkeypatch):
    from openai import RateLimitError

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    app_module._client = None
    fake_client = MagicMock()
    fake_client.embeddings.create.side_effect = [
        _fake_status_error(RateLimitError, 429),
        _FakeEmbeddingResponse([[0.8, 0.9]]),
    ]
    monkeypatch.setattr(app_module, "get_client", lambda: fake_client)
    monkeypatch.setattr(app_module.time, "sleep", lambda _seconds: None)

    client = TestClient(app_module.app)
    resp = client.post("/embed", json={"text": "rate limited"})

    assert resp.status_code == 200
    assert resp.json()["vector"] == [0.8, 0.9]
    assert fake_client.embeddings.create.call_count == 2


def test_embed_does_not_retry_on_4xx_client_error(monkeypatch):
    from openai import BadRequestError

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    app_module._client = None
    fake_client = MagicMock()
    fake_client.embeddings.create.side_effect = _fake_status_error(BadRequestError, 400)
    monkeypatch.setattr(app_module, "get_client", lambda: fake_client)
    monkeypatch.setattr(app_module.time, "sleep", lambda _seconds: None)

    client = TestClient(app_module.app)
    resp = client.post("/embed", json={"text": "malformed request"})

    assert resp.status_code == 502
    assert fake_client.embeddings.create.call_count == 1


def test_embed_502_on_empty_upstream_response(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    app_module._client = None
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = _FakeEmbeddingResponse([])
    monkeypatch.setattr(app_module, "get_client", lambda: fake_client)

    client = TestClient(app_module.app)
    resp = client.post("/embed", json={"text": "malformed upstream"})

    assert resp.status_code == 502


def test_embed_502_detail_does_not_leak_internal_exception_text(monkeypatch):
    from openai import APIConnectionError

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    app_module._client = None
    fake_client = MagicMock()
    fake_request = MagicMock()
    fake_client.embeddings.create.side_effect = APIConnectionError(request=fake_request)
    monkeypatch.setattr(app_module, "get_client", lambda: fake_client)
    monkeypatch.setattr(app_module.time, "sleep", lambda _seconds: None)

    client = TestClient(app_module.app)
    resp = client.post("/embed", json={"text": "always fails"})

    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "OPENAI_API_KEY" not in detail
    assert "Connection error" not in detail


def test_embed_batch_returns_vectors(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    app_module._client = None
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = _FakeEmbeddingResponse(
        [[0.1, 0.2], [0.3, 0.4]]
    )
    monkeypatch.setattr(app_module, "get_client", lambda: fake_client)

    client = TestClient(app_module.app)
    resp = client.post("/embed/batch", json={"texts": ["a", "b"]})

    assert resp.status_code == 200
    assert resp.json()["vectors"] == [[0.1, 0.2], [0.3, 0.4]]
    fake_client.embeddings.create.assert_called_once_with(
        model=app_module.MODEL, input=["a", "b"],
    )


def test_embed_batch_502_on_length_mismatched_upstream_response(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    app_module._client = None
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = _FakeEmbeddingResponse([[0.1, 0.2]])
    monkeypatch.setattr(app_module, "get_client", lambda: fake_client)

    client = TestClient(app_module.app)
    resp = client.post("/embed/batch", json={"texts": ["a", "b"]})

    assert resp.status_code == 502


def test_embed_batch_empty_list_short_circuits(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    app_module._client = None
    fake_client = MagicMock()
    monkeypatch.setattr(app_module, "get_client", lambda: fake_client)

    client = TestClient(app_module.app)
    resp = client.post("/embed/batch", json={"texts": []})

    assert resp.status_code == 200
    assert resp.json()["vectors"] == []
    fake_client.embeddings.create.assert_not_called()


def test_embed_batch_502_detail_does_not_leak_internal_exception_text(monkeypatch):
    from openai import BadRequestError

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
    app_module._client = None
    fake_client = MagicMock()
    fake_client.embeddings.create.side_effect = _fake_status_error(BadRequestError, 400)
    monkeypatch.setattr(app_module, "get_client", lambda: fake_client)
    monkeypatch.setattr(app_module.time, "sleep", lambda _seconds: None)

    client = TestClient(app_module.app)
    resp = client.post("/embed/batch", json={"texts": ["a", "b"]})

    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "BadRequestError" not in detail
    assert detail == "embedding request failed"
