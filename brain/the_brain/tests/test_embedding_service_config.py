"""Tests core.config.embedding_service_url() — brain-package convention:
plain script, no pytest. Run: python tests/test_embedding_service_config.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_BRAIN = Path(__file__).resolve().parents[1]
if str(_BRAIN) not in sys.path:
    sys.path.insert(0, str(_BRAIN))

_spec = importlib.util.spec_from_file_location(
    "config", _BRAIN / "core" / "config.py")
_cfg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cfg)

_passed: list[str] = []
_failed: list[str] = []


def check(name, cond):
    (_passed if cond else _failed).append(name)
    print(("  PASS " if cond else "  FAIL ") + name)


def test_default_url():
    print("Test 1: default embedding_service_url()")
    os.environ.pop("EMBEDDING_SERVICE_URL", None)
    check("defaults to http://embedding-service:8080",
          _cfg.embedding_service_url() == "http://embedding-service:8080")


def test_override_url():
    print("Test 2: EMBEDDING_SERVICE_URL override, trailing slash stripped")
    os.environ["EMBEDDING_SERVICE_URL"] = "http://localhost:9000/"
    check("override applied + trailing slash stripped",
          _cfg.embedding_service_url() == "http://localhost:9000")
    os.environ.pop("EMBEDDING_SERVICE_URL", None)


if __name__ == "__main__":
    test_default_url()
    test_override_url()
    print(f"\n{len(_passed)} passed, {len(_failed)} failed")
    if _failed:
        sys.exit(1)
