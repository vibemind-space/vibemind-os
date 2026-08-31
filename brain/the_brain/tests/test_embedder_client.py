"""Tests qdrant_kg.Embedder as an HTTP client against embedding-service.
Brain-package convention: plain script, no pytest, requests mocked via
monkeypatched module attribute (no network calls made).
Run: python tests/test_embedder_client.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

_BRAIN = Path(__file__).resolve().parents[1]
if str(_BRAIN) not in sys.path:
    sys.path.insert(0, str(_BRAIN))

_spec = importlib.util.spec_from_file_location(
    "qdrant_kg", _BRAIN / "core" / "qdrant_kg.py")
_kg = importlib.util.module_from_spec(_spec)
# Register in sys.modules before exec: qdrant_kg.py has dataclasses combined
# with `from __future__ import annotations`, and dataclass field-type
# resolution looks up sys.modules[cls.__module__] — without this the module
# crashes at class-body-eval time with "'NoneType' object has no attribute
# '__dict__'", unrelated to the Embedder class under test.
sys.modules["qdrant_kg"] = _kg
_spec.loader.exec_module(_kg)

_passed: list[str] = []
_failed: list[str] = []


def check(name, cond):
    (_passed if cond else _failed).append(name)
    print(("  PASS " if cond else "  FAIL ") + name)


def _fresh_embedder(fake_post) -> "_kg.Embedder":
    _kg.Embedder._instance = None  # reset singleton between tests
    embedder = _kg.Embedder()
    embedder._session.post = fake_post  # type: ignore[attr-defined]
    return embedder


def test_encode_calls_embed_endpoint():
    print("Test 1: encode() POSTs to /embed and returns the vector")
    # Vector must match SEMANTIC_DIM or the dimension-mismatch guard raises.
    fake_vec = [0.1] * _kg.SEMANTIC_DIM
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {"vector": fake_vec}
    fake_post = MagicMock(return_value=fake_resp)

    embedder = _fresh_embedder(fake_post)
    vec = embedder.encode("hello")

    check("returns the vector from the response", vec == fake_vec)
    called_url = fake_post.call_args.args[0]
    check("posts to the /embed path", called_url.endswith("/embed"))
    called_json = fake_post.call_args.kwargs.get("json")
    check("sends {'text': ...}", called_json == {"text": "hello"})


def test_encode_batch_calls_batch_endpoint():
    print("Test 2: encode_batch() POSTs to /embed/batch and returns vectors")
    # Vectors must match SEMANTIC_DIM or the dimension-mismatch guard raises.
    fake_v1 = [0.1] * _kg.SEMANTIC_DIM
    fake_v2 = [0.3] * _kg.SEMANTIC_DIM
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {"vectors": [fake_v1, fake_v2]}
    fake_post = MagicMock(return_value=fake_resp)

    embedder = _fresh_embedder(fake_post)
    vecs = embedder.encode_batch(["a", "b"])

    check("returns both vectors", vecs == [fake_v1, fake_v2])
    called_url = fake_post.call_args.args[0]
    check("posts to the /embed/batch path", called_url.endswith("/embed/batch"))
    called_json = fake_post.call_args.kwargs.get("json")
    check("sends {'texts': [...]}", called_json == {"texts": ["a", "b"]})


def test_encode_raises_on_http_error():
    print("Test 3: encode() propagates a hard failure (no silent no-op)")
    import requests

    fake_post = MagicMock(side_effect=requests.exceptions.ConnectionError("boom"))
    embedder = _fresh_embedder(fake_post)

    raised = False
    try:
        embedder.encode("hello")
    except requests.exceptions.ConnectionError:
        raised = True
    check("raises instead of returning a degraded/empty result", raised)


def test_encode_raises_on_dimension_mismatch():
    print("Test 4: encode() raises when the returned vector dim != SEMANTIC_DIM")
    # Deliberately wrong length (SEMANTIC_DIM is 1024) to simulate a
    # collection/model version mismatch (e.g. mid-rollout of Task 7).
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {"vector": [0.1, 0.2, 0.3]}
    fake_post = MagicMock(return_value=fake_resp)

    embedder = _fresh_embedder(fake_post)

    raised = False
    message = ""
    try:
        embedder.encode("hello")
    except RuntimeError as e:
        raised = True
        message = str(e)
    check("raises RuntimeError instead of returning a mismatched vector", raised)
    check("error names SEMANTIC_DIM for a clear diagnosis", "SEMANTIC_DIM" in message)


if __name__ == "__main__":
    test_encode_calls_embed_endpoint()
    test_encode_batch_calls_batch_endpoint()
    test_encode_raises_on_http_error()
    test_encode_raises_on_dimension_mismatch()
    print(f"\n{len(_passed)} passed, {len(_failed)} failed")
    if _failed:
        sys.exit(1)
