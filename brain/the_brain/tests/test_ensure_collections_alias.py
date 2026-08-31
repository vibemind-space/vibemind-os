"""Tests the alias-aware ensure_collections() behavior added in the
embedder-external-api migration. Brain-package convention: plain script,
no pytest, Qdrant client fully mocked (no real Qdrant needed).
Run: python tests/test_ensure_collections_alias.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

_BRAIN = Path(__file__).resolve().parents[1]
if str(_BRAIN) not in sys.path:
    sys.path.insert(0, str(_BRAIN))

_spec = importlib.util.spec_from_file_location(
    "qdrant_kg", _BRAIN / "core" / "qdrant_kg.py")
_kg = importlib.util.module_from_spec(_spec)
sys.modules["qdrant_kg"] = _kg  # required: dataclass forward-ref resolution
_spec.loader.exec_module(_kg)

_passed: list[str] = []
_failed: list[str] = []


def check(name, cond):
    (_passed if cond else _failed).append(name)
    print(("  PASS " if cond else "  FAIL ") + name)


def _make_kg(existing_collection_names, existing_aliases):
    """existing_aliases: list[(alias_name, collection_name)]"""
    kg = _kg.QdrantKG.__new__(_kg.QdrantKG)  # bypass __init__ (no real Qdrant)
    kg.client = MagicMock()
    kg.client.get_collections.return_value = SimpleNamespace(
        collections=[SimpleNamespace(name=n) for n in existing_collection_names]
    )
    kg.client.get_aliases.return_value = SimpleNamespace(
        aliases=[SimpleNamespace(alias_name=a, collection_name=c)
                 for a, c in existing_aliases]
    )
    kg._qm = __import__("qdrant_client.http.models", fromlist=["models"])
    return kg


def test_fresh_deploy_creates_physical_and_alias():
    print("Test 1: fresh deploy — no collections, no aliases exist yet")
    kg = _make_kg(existing_collection_names=[], existing_aliases=[])
    kg._ensure_payload_indexes = MagicMock()

    kg.ensure_collections()

    create_calls = kg.client.create_collection.call_args_list
    check("creates a physical collection per logical name",
          len(create_calls) == len(_kg.COLLECTIONS))
    first_target = create_calls[0].kwargs["collection_name"]
    check("physical name carries the version suffix",
          first_target.endswith(_kg.PHYSICAL_VERSION_SUFFIX))
    check("alias update was called once per collection",
          kg.client.update_collection_aliases.call_count == len(_kg.COLLECTIONS))


def test_already_aliased_is_left_alone():
    print("Test 2: alias already points somewhere — must not recreate anything")
    some_alias = next(iter(_kg.COLLECTIONS.values()))
    kg = _make_kg(
        existing_collection_names=[f"{some_alias}{_kg.PHYSICAL_VERSION_SUFFIX}"],
        existing_aliases=[(some_alias, f"{some_alias}{_kg.PHYSICAL_VERSION_SUFFIX}")],
    )
    kg._ensure_payload_indexes = MagicMock()

    kg.ensure_collections()

    check("does not create a new physical collection for an aliased name",
          kg.client.create_collection.call_count < len(_kg.COLLECTIONS))
    check("does not touch aliasing again for the already-aliased name",
          kg.client.update_collection_aliases.call_count < len(_kg.COLLECTIONS))


def test_pre_migration_raw_collection_is_left_alone():
    print("Test 3: pre-migration state — name exists as a RAW collection, no alias")
    some_name = next(iter(_kg.COLLECTIONS.values()))
    kg = _make_kg(existing_collection_names=[some_name], existing_aliases=[])
    kg._ensure_payload_indexes = MagicMock()

    kg.ensure_collections()

    check("does not create a new physical collection for the raw pre-migration name",
          kg.client.create_collection.call_count < len(_kg.COLLECTIONS))
    check("does not force an alias onto an un-migrated raw collection",
          kg.client.update_collection_aliases.call_count < len(_kg.COLLECTIONS))


if __name__ == "__main__":
    test_fresh_deploy_creates_physical_and_alias()
    test_already_aliased_is_left_alone()
    test_pre_migration_raw_collection_is_left_alone()
    print(f"\n{len(_passed)} passed, {len(_failed)} failed")
    if _failed:
        sys.exit(1)
