"""C3 — Capability self-discovery.

The brain's inventory of "what it can actually do" — so the gap-detector knows what
exists (and therefore what is a gap). Built by reading the STRUCTURED sources directly,
which keeps this module dependency-free and standalone-testable:

  C3a (this, no fungus):
    - registered capabilities -> data/capabilities.yaml  (execution_target per cap)
    - OpenFang agent roster   -> ~/.openfang/agents/<name>/agent.toml  (live deploy dir)

  C3b (latent discovery, needs fungus):
    - capabilities implemented IN CODE but NOT registered -> discover_latent(query_fn).
      No-op until a fungus query function is supplied (fungus server reachable). This is
      the real "brain erforscht die codebase um eigene capas zu finden" step.

Paths are injectable so the inventory is testable without the brain runtime. At runtime
the brain MAY instead feed capability_router.list_capabilities() / AgentYamlRegistry,
but the file-parse below is the canonical, dependency-free core.
"""

from __future__ import annotations

import os
import glob
import logging
from typing import Callable, Dict, List, Optional

logger = logging.getLogger("brain.capability_discovery")

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CAPS_YAML = os.path.normpath(os.path.join(_HERE, "..", "data", "capabilities.yaml"))
_DEFAULT_AGENTS_DIR = os.environ.get(
    "OPENFANG_AGENTS_DIR", os.path.expanduser(os.path.join("~", ".openfang", "agents"))
)


def _cap_kind(execution_target: Optional[str]) -> str:
    """Bucket a capability by its execution_target prefix (None -> broadcast-only)."""
    if not execution_target:
        return "broadcast"
    return str(execution_target).split(":", 1)[0]


def discover_capabilities(yaml_path: Optional[str] = None) -> List[Dict]:
    """Registered capabilities from capabilities.yaml -> normalized inventory records.

    Each record: {capability, description, execution_target, kind, agents, has_validator}.
    Tolerant: a malformed file yields [] (never raises).
    """
    path = yaml_path or _DEFAULT_CAPS_YAML
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or []
    except Exception as exc:
        logger.warning("[discovery] capabilities.yaml unreadable (%s): %s", path, exc)
        return []
    if not isinstance(raw, list):
        return []
    out: List[Dict] = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        tgt = c.get("execution_target")
        out.append({
            "capability": c.get("capability"),
            "description": c.get("description", ""),
            "execution_target": tgt,
            "kind": _cap_kind(tgt),
            "agents": c.get("agents"),
            "has_validator": bool(c.get("validator")),
        })
    return out


def discover_agents(agents_dir: Optional[str] = None) -> List[Dict]:
    """OpenFang agent roster from <dir>/<name>/agent.toml -> normalized records.

    Each record: {name, description, model, tools, mcp_servers}. Handles BOTH mcp
    formats ([capabilities].mcp_servers and [mcp_allowed].servers). A single bad
    agent.toml is skipped, not fatal.
    """
    d = agents_dir or _DEFAULT_AGENTS_DIR
    try:
        import tomllib
    except Exception:  # pragma: no cover - py<3.11
        logger.warning("[discovery] tomllib unavailable; cannot parse agent.toml")
        return []
    out: List[Dict] = []
    for toml_path in sorted(glob.glob(os.path.join(d, "*", "agent.toml"))):
        try:
            with open(toml_path, "rb") as f:
                t = tomllib.load(f)
        except Exception as exc:
            logger.debug("[discovery] skip %s: %s", toml_path, exc)
            continue
        caps = t.get("capabilities", {}) or {}
        mcp = caps.get("mcp_servers") or (t.get("mcp_allowed", {}) or {}).get("servers") or []
        model = t.get("model", {}) or {}
        out.append({
            "name": t.get("name") or os.path.basename(os.path.dirname(toml_path)),
            "description": t.get("description", ""),
            "model": f"{model.get('provider', '?')}/{model.get('model', '?')}",
            "tools": list(caps.get("tools", []) or []),
            "mcp_servers": list(mcp),
        })
    return out


def build_inventory(
    yaml_path: Optional[str] = None, agents_dir: Optional[str] = None
) -> Dict:
    """Unified capability inventory: registered capabilities + OpenFang agents + summary."""
    caps = discover_capabilities(yaml_path)
    agents = discover_agents(agents_dir)
    by_kind: Dict[str, int] = {}
    for c in caps:
        by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1
    return {
        "capabilities": caps,
        "agents": agents,
        "summary": {
            "n_capabilities": len(caps),
            "by_target": by_kind,
            "n_agents": len(agents),
            "n_agents_with_mcp": sum(1 for a in agents if a["mcp_servers"]),
        },
    }


_fungus_mod = None  # cache the (heavy) fungus module across calls


def default_fungus_query(query: str, top_k: int = 8,
                         fungus_path: Optional[str] = None) -> List[Dict]:
    """C3b wiring — query the la-fungus-search index for code symbols (proven live
    2026-06-23 over the 56k-chunk index). Lazy-loads + caches the fungus MCMP
    retriever (heavy: Qwen3-Embedding-0.6B), runs a semantic search, extracts
    def/class symbols from the hits. Pass as discover_latent(default_fungus_query).
    Returns [] on any error (fungus index/embedder unavailable)."""
    global _fungus_mod
    import os
    import re
    try:
        if _fungus_mod is None:
            import importlib.util
            here = os.path.dirname(os.path.abspath(__file__))
            path = fungus_path or os.path.normpath(os.path.join(
                here, "..", "..", "..", "la-fungus-search", "mcp_server.py"))
            spec = importlib.util.spec_from_file_location("vibemind_fungus", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # loads embedder + persistent index
            _fungus_mod = mod
        res = _fungus_mod._sync_search(query, top_k=top_k)
        out: List[Dict] = []
        for h in (res.get("results") or []):
            txt = h.get("text") or h.get("content") or h.get("chunk") or ""
            file = h.get("file") or h.get("path") or (h.get("metadata") or {}).get("file")
            for sym in re.findall(r"(?:def|class)\s+([A-Za-z_]\w+)", txt)[:3]:
                out.append({"symbol": sym, "file": file, "score": h.get("score")})
        return out
    except Exception as exc:
        logger.debug("[discovery] fungus query failed: %s", exc)
        return []


def discover_latent(
    fungus_query_fn: Optional[Callable[[str], List[Dict]]] = None,
    inventory: Optional[Dict] = None,
) -> Dict:
    """C3b interface — find capabilities implemented in code but NOT registered.

    Supply `fungus_query_fn(query) -> list of code hits` (a thin wrapper over the
    fungus HTTP server). This module then asks fungus for executor/handler patterns
    and diffs the hits against the registered inventory. Until fungus is wired this
    is a graceful no-op so the rest of discovery works offline.
    """
    if fungus_query_fn is None:
        return {"available": False, "latent": [],
                "note": "fungus query fn not supplied — C3b latent discovery offline"}
    inv = inventory or build_inventory()
    registered = {c["capability"] for c in inv["capabilities"] if c["capability"]}
    queries = [
        "capability executor function not registered",
        "agent handler tool implemented",
        "def .*executor call capability",
    ]
    latent: List[Dict] = []
    for q in queries:
        try:
            for hit in (fungus_query_fn(q) or []):
                name = (hit.get("symbol") or hit.get("name") or "").strip()
                if name and name not in registered:
                    latent.append({"candidate": name, "query": q,
                                   "file": hit.get("file"), "score": hit.get("score")})
        except Exception as exc:
            logger.debug("[discovery] fungus query failed (%s): %s", q, exc)
    return {"available": True, "latent": latent, "n_registered": len(registered)}
