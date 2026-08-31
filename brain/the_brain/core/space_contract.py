"""Canonical space identity, routing, and registry diagnostics.

``config/space_agent_registry.yml`` is the authority for public space IDs and
event ownership.  This module reports catalog consistency only; it never
treats that structural result as external execution availability.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import yaml


CANONICAL_ALIASES: Dict[str, str] = {
    "autogen": "agentfarm",
    "rowboat": "roarboot",
    "shuttles": "bubbles",
}

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = _REPO_ROOT / "config" / "space_agent_registry.yml"


@dataclass(frozen=True)
class SpaceContract:
    version: int
    source: Path
    spaces: Mapping[str, Mapping[str, Any]]
    space_ids: Tuple[str, ...]
    event_space_map: Mapping[str, str]


def load_space_contract(path: Path = DEFAULT_REGISTRY_PATH) -> SpaceContract:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    spaces = raw.get("spaces")
    if not isinstance(spaces, dict) or not spaces:
        raise ValueError(f"space registry has no spaces: {path}")

    event_space_map: Dict[str, str] = {}
    for space_id, meta in spaces.items():
        if not isinstance(space_id, str) or not isinstance(meta, dict):
            raise ValueError(f"invalid space entry in {path}: {space_id!r}")
        events = meta.get("events", {})
        if not isinstance(events, dict):
            raise ValueError(f"events for {space_id!r} must be a mapping")
        for event_type in events:
            if event_type in event_space_map:
                raise ValueError(f"duplicate event ownership: {event_type}")
            event_space_map[event_type] = space_id

    return SpaceContract(
        version=int(raw.get("version", 0)),
        source=path,
        spaces=spaces,
        space_ids=tuple(spaces),
        event_space_map=event_space_map,
    )


def normalize_space_id(value: str, contract: Optional[SpaceContract] = None) -> Optional[str]:
    contract = contract or load_space_contract()
    candidate = (value or "").strip().lower()
    candidate = CANONICAL_ALIASES.get(candidate, candidate)
    return candidate if candidate in contract.spaces else None


def registry_health(
    contract: Optional[SpaceContract] = None,
    *,
    capabilities: Optional[list[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return a deterministic, queryable consistency view of Brain catalogs."""
    contract = contract or load_space_contract()
    issues = []

    from spaces._navigator.registry import SPACES as navigator_spaces
    navigator_ids = {
        normalize_space_id(space_id, contract)
        for space_id in navigator_spaces
        if space_id != "brain"
    }
    navigator_ids.discard(None)
    missing = sorted(set(contract.space_ids) - navigator_ids)
    if missing:
        issues.append({"kind": "navigator_missing_spaces", "spaces": missing})

    from .capability_targets import supported_kinds
    supported = sorted(supported_kinds())
    used = sorted({
        str(item["execution_target"]).split(":", 1)[0].lower()
        for item in (capabilities or [])
        if isinstance(item, Mapping) and item.get("execution_target")
    })
    unsupported = sorted(set(used) - set(supported))
    if unsupported:
        issues.append({"kind": "unsupported_executor_kinds", "kinds": unsupported})

    return {
        "status": "ok" if not issues else "degraded",
        "source": str(contract.source),
        "canonical_space_count": len(contract.space_ids),
        "event_count": len(contract.event_space_map),
        "executor_kinds_used": used,
        "executor_kinds_supported": supported,
        "issues": issues,
    }
