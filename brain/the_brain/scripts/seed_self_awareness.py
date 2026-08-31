"""
Phase S.1 — Seed Brain's self-awareness substrate into brain-semantic.

Writes ~54 concept-nodes describing the VibeMind architecture:
- Top-level manifests (vibemind.config.json, .mcp.json subset)
- 6 major subsystems (brain, openfang, voice, coding, spaces, mirofish)
- 17 spaces directories
- 25 curated brain core modules (the architecturally-load-bearing ones)

Each node lands in brain-semantic with node_type="concept" + payload flag
self_awareness=True so DiscourseEngine (Phase S.2) can preferentially
sample them.

Idempotent: external_id = "sa::{subsystem}::{slug}" → deterministic UUID,
re-runs collapse duplicates instead of piling up.

Run modes:
    python seed_self_awareness.py             # full seed
    python seed_self_awareness.py --dry-run   # show what would be written
    python seed_self_awareness.py --diff      # only re-write changed (uses manifest)

Output:
    Manifest at vibemind-os/brain/the_brain/data/self_awareness_manifest.json
    tracks file-hash + node_id per source so Phase S.4 watcher can detect
    changes incrementally.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# scripts/ → the_brain/, add to path so we can import core.*
_THIS = Path(__file__).resolve()
_BRAIN_DIR = _THIS.parent.parent
sys.path.insert(0, str(_BRAIN_DIR))

# Repo root: scripts/ → the_brain/ → brain/ → vibemind-os/ → REPO
_REPO = _BRAIN_DIR.parent.parent.parent
MANIFEST_PATH = _BRAIN_DIR / "data" / "self_awareness_manifest.json"

logging.basicConfig(level=logging.INFO, format="[seed] %(message)s")
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Curated module list — the architecturally-load-bearing 25 brain modules.
# Adding to this list is a manual code-change, not auto-discovery (keeps
# the substrate focused; helper modules don't deserve concept-nodes).
# ─────────────────────────────────────────────────────────────────────

CURATED_BRAIN_MODULES = [
    # Orchestration core
    "brain_chat.py",
    "agent_loop.py",
    "multi_llm_router.py",
    "tool_call_generator.py",
    "multi_agent_executor.py",
    "subagent_dispatcher.py",
    "auto_dispatcher.py",
    # Discourse (Phase R+)
    "discourse_engine.py",
    "discourse_aggregator.py",
    "discourse_intent_aggregator.py",
    # Memory + KG
    "qdrant_kg.py",
    "consolidation_engine.py",
    "memory_consolidation.py",
    "memory_systems.py",
    "mcmp_gardener.py",
    "snapshot_engine.py",
    # Bridges + bio modules
    "amygdala_complex.py",
    "hippocampus.py",
    "cerebellum_module.py",
    "cortex_bridge.py",
    "limbic_bridge.py",
    "hypothalamus_drives.py",
    # Routing + attention
    "radial_attention.py",
    "space_routing_head.py",
    "event_routing_head.py",
    # Clients (external integrations)
    "ideas_client.py",
]

CURATED_MCP_SERVERS = [
    "brain-core", "fungus-search", "desktop-automation",
    "vibemind-issue-detector", "n8n",
]

SUBSYSTEM_DESCRIPTIONS = {
    "brain": (
        "Brain — orchestrator + cognitive core at vibemind-os/brain/the_brain. "
        "FastAPI server on :5000. Hosts BrainChat (thalamus routing), "
        "AgentLoop (autonomous tick), Multi-LLM Router (Claude/Groq/OpenAI), "
        "Memory systems (episodic, semantic, procedural, state, aggregated, "
        "mirofish), 10 bio-inspired bridges (cortex/limbic/etc.), and "
        "Phase R+ three-mode discourse. Persistence: Qdrant @ :6340."
    ),
    "openfang": (
        "OpenFang — Rust-based agent OS at vibemind-os/openfang/. "
        "HTTP API on :4200. Hosts 51 agents (26 originals + 25 phi3-clones "
        "for discourse). Each agent has a TOML manifest, isolated runtime, "
        "and configurable LLM provider (Anthropic Sonnet for real work, "
        "Ollama qwen2.5-coder for discourse-reflection)."
    ),
    "voice": (
        "Voice-Layer at vibemind-os/voice/. Houses Docker stacks for "
        "Minibook (memory inbox), Mirofish (multi-agent simulation, :5101), "
        "n8n (workflow automation), and AgentFarm. Provides Python "
        "embedding service (Qwen3-Embedding-0.6B 1024d) shared across "
        "VibeMind subsystems."
    ),
    "coding": (
        "Coding-Engine at vibemind-os/coding/. Replaces the legacy "
        "Project-Space with Daves Vibe Coder: full-autonomous code "
        "pipeline with new UI, separate launcher."
    ),
    "spaces": (
        "Spaces at vibemind-os/spaces/. 17 domain-specific subsystems "
        "(ideas, mirofish, coding, research, eyeterm, rowboat, schedule, "
        "video, n8n, etc.). Each is independently launchable with its "
        "own HTTP service or Python module. Brain orchestrates them via "
        "IdeasClient / MinibookClient / etc."
    ),
    "mirofish": (
        "Mirofish at vibemind-os/spaces/mirofish/. Multi-agent Twitter/"
        "Reddit simulation platform. Flask backend :5101, Vue frontend "
        ":3001, Neo4j :7688. Brain's DiscourseEngine drives it: 25 "
        "phi3-clones reflect over Brain KG slices, posts persist as "
        "interview-results, Aggregator (every 3h) condenses into "
        "structured aggregated-kg topics+findings+decisions."
    ),
}


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _slug(s: str) -> str:
    """Conservative slug for external_id components."""
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "unknown"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _hash_file(path: Path) -> Optional[str]:
    try:
        return _sha256_text(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        log.warning(f"hash failed for {path}: {e}")
        return None


def _hash_dir_listing(path: Path) -> Optional[str]:
    """Hash a directory by joining sorted top-level entries (files + dirs)."""
    try:
        items = sorted(p.name for p in path.iterdir())
        return _sha256_text("\n".join(items))
    except Exception as e:
        log.warning(f"hash failed for {path}: {e}")
        return None


def _extract_python_summary(path: Path, max_chars: int = 1500) -> str:
    """Module-docstring + class names + first 3 public function signatures."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src, filename=str(path))
    except Exception as e:
        return f"(parse failed: {e})"

    parts: List[str] = []
    docstring = ast.get_docstring(tree)
    if docstring:
        parts.append(docstring.strip())

    classes: List[str] = []
    funcs: List[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                args = [a.arg for a in node.args.args[:5]]
                funcs.append(f"{node.name}({', '.join(args)})")
                if len(funcs) >= 3:
                    break

    if classes:
        parts.append(f"Classes: {', '.join(classes[:8])}")
    if funcs:
        parts.append(f"Functions: {', '.join(funcs)}")

    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars - 3] + "..."
    return text or f"(no docstring or public symbols in {path.name})"


def _extract_dir_summary(path: Path, max_chars: int = 1500) -> str:
    """Look for README.md → __init__.py docstring → file-listing fallback."""
    readme = path / "README.md"
    if readme.exists():
        try:
            text = readme.read_text(encoding="utf-8", errors="replace")
            if len(text) > max_chars:
                text = text[:max_chars - 3] + "..."
            return text
        except Exception:
            pass

    init_py = path / "__init__.py"
    if init_py.exists():
        try:
            tree = ast.parse(init_py.read_text(encoding="utf-8", errors="replace"))
            ds = ast.get_docstring(tree)
            if ds:
                return ds[:max_chars]
        except Exception:
            pass

    # Last fallback: list top-level entries
    try:
        items = sorted(p.name for p in path.iterdir() if not p.name.startswith("."))[:20]
        return f"Directory contents ({path.name}): {', '.join(items)}"
    except Exception:
        return f"(empty or unreadable: {path.name})"


# ─────────────────────────────────────────────────────────────────────
# Source collection
# ─────────────────────────────────────────────────────────────────────

def collect_sources() -> List[Dict[str, Any]]:
    """Return list of source dicts each with {subsystem, kind, path, title,
    content, external_id}. Path is relative to repo root."""
    sources: List[Dict[str, Any]] = []

    # 1. Top-level manifest: vibemind.config.json
    cfg_path = _REPO / "vibemind.config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            modules = cfg.get("modules") or {}
            ports = cfg.get("ports") or {}
            mod_lines = [f"- {k}: enabled={v.get('enabled', False)}" for k, v in modules.items()]
            content = (
                f"VibeMind is a modular cognitive operating system. "
                f"Top-level configuration at vibemind.config.json.\n\n"
                f"Modules:\n" + "\n".join(mod_lines) + "\n\n"
                f"Ports: {ports}"
            )
            sources.append({
                "subsystem": "top-level",
                "kind": "manifest",
                "path": "vibemind.config.json",
                "title": "VibeMind Manifest",
                "content": content,
                "external_id": "sa::top-level::vibemind-manifest",
            })
        except Exception as e:
            log.warning(f"vibemind.config.json parse failed: {e}")

    # 2. .mcp.json — curated subset
    mcp_path = _REPO / ".mcp.json"
    if mcp_path.exists():
        try:
            mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
            servers = mcp.get("mcpServers") or {}
            for name in CURATED_MCP_SERVERS:
                spec = servers.get(name)
                if not spec:
                    continue
                cmd = spec.get("command", "?")
                args = " ".join(spec.get("args", [])[:3])
                env_keys = list((spec.get("env") or {}).keys())
                content = (
                    f"MCP server '{name}' registered in .mcp.json.\n"
                    f"Command: {cmd} {args}\n"
                    f"Env keys: {', '.join(env_keys) if env_keys else '(none)'}"
                )
                sources.append({
                    "subsystem": "mcp",
                    "kind": "mcp_server",
                    "path": ".mcp.json",
                    "title": f"MCP: {name}",
                    "content": content,
                    "external_id": f"sa::mcp::{_slug(name)}",
                })
        except Exception as e:
            log.warning(f".mcp.json parse failed: {e}")

    # 3. Subsystems
    for subsys, desc in SUBSYSTEM_DESCRIPTIONS.items():
        sources.append({
            "subsystem": subsys,
            "kind": "subsystem",
            "path": "(synthetic)",
            "title": f"Subsystem: {subsys}",
            "content": desc,
            "external_id": f"sa::subsystem::{subsys}",
        })

    # 4. 17 spaces
    spaces_dir = _REPO / "vibemind-os" / "spaces"
    if spaces_dir.exists():
        for sp in sorted(spaces_dir.iterdir()):
            if not sp.is_dir() or sp.name.startswith("__"):
                continue
            summary = _extract_dir_summary(sp)
            sources.append({
                "subsystem": "spaces",
                "kind": "space",
                "path": f"vibemind-os/spaces/{sp.name}",
                "title": f"Space: {sp.name}",
                "content": f"{sp.name} — VibeMind space.\n\n{summary}",
                "external_id": f"sa::space::{_slug(sp.name)}",
            })

    # 5. 25 curated brain core modules
    core_dir = _REPO / "vibemind-os" / "brain" / "the_brain" / "core"
    for mod_name in CURATED_BRAIN_MODULES:
        mod_path = core_dir / mod_name
        if not mod_path.exists():
            log.warning(f"curated module missing: {mod_name}")
            continue
        summary = _extract_python_summary(mod_path)
        title = mod_name[:-3]  # strip .py
        sources.append({
            "subsystem": "brain",
            "kind": "core_module",
            "path": f"vibemind-os/brain/the_brain/core/{mod_name}",
            "title": title,
            "content": summary,
            "external_id": f"sa::brain-core::{_slug(title)}",
        })

    return sources


# ─────────────────────────────────────────────────────────────────────
# Manifest tracking (for S.4 watcher)
# ─────────────────────────────────────────────────────────────────────

def load_manifest() -> Dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {"version": 1, "last_full_seed_at": 0, "sources": {}}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "last_full_seed_at": 0, "sources": {}}


def save_manifest(manifest: Dict[str, Any]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def hash_for_source(src: Dict[str, Any]) -> str:
    """Hash the source's actual on-disk file/dir, plus its rendered content,
    so changes in either are detected."""
    p = _REPO / src["path"] if src["path"] != "(synthetic)" else None
    file_hash = ""
    if p and p.exists():
        if p.is_dir():
            file_hash = _hash_dir_listing(p) or ""
        else:
            file_hash = _hash_file(p) or ""
    content_hash = _sha256_text(src["content"])
    return _sha256_text(f"{file_hash}::{content_hash}")


# ─────────────────────────────────────────────────────────────────────
# Upsert
# ─────────────────────────────────────────────────────────────────────

def upsert_source(kg, src: Dict[str, Any]) -> Optional[str]:
    """Upsert one source as a concept-node in brain-semantic.
    Returns point id (UUID) on success."""
    payload = {
        "title": src["title"],
        "content": src["content"],
        "source_path": src["path"],
        "subsystem": src["subsystem"],
        "kind": src["kind"],
        "tags": ["self-awareness", "architecture", src["subsystem"]],
        "self_awareness": True,
    }
    text = f"{src['title']}\n\n{src['content']}"
    return kg._upsert_point(
        external_id=src["external_id"],
        node_type="concept",
        text=text,
        payload_extra=payload,
    )


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be written without touching KG")
    ap.add_argument("--diff", action="store_true",
                    help="Only re-write sources whose hash differs from manifest")
    args = ap.parse_args()

    log.info(f"Repo root: {_REPO}")
    log.info("Collecting sources...")
    sources = collect_sources()
    log.info(f"Collected {len(sources)} sources")

    # Manifest delta
    manifest = load_manifest()
    old_sources: Dict[str, Dict[str, Any]] = manifest.get("sources") or {}

    to_write: List[Tuple[Dict[str, Any], str]] = []
    unchanged = 0
    for src in sources:
        h = hash_for_source(src)
        prev = old_sources.get(src["external_id"])
        # In --diff mode, skip unchanged. In full-seed mode, always write.
        if args.diff and prev and prev.get("hash") == h:
            unchanged += 1
            continue
        to_write.append((src, h))

    log.info(f"To write: {len(to_write)} (unchanged: {unchanged})")

    if args.dry_run:
        for src, _h in to_write[:10]:
            log.info(f"  + {src['external_id']} | {src['title']!r}")
        if len(to_write) > 10:
            log.info(f"  ... and {len(to_write) - 10} more")
        return 0

    # Connect to KG
    log.info("Connecting to QdrantKG...")
    from core.qdrant_kg import QdrantKG
    kg = QdrantKG()
    kg.ensure_collections()

    # Upsert
    written = 0
    failed = 0
    new_manifest_sources = dict(old_sources)  # preserve untouched entries
    for src, h in to_write:
        pid = upsert_source(kg, src)
        if pid:
            written += 1
            new_manifest_sources[src["external_id"]] = {
                "hash": h,
                "node_id": pid,
                "title": src["title"],
                "subsystem": src["subsystem"],
                "kind": src["kind"],
                "path": src["path"],
                "last_seeded_at": int(time.time()),
            }
        else:
            failed += 1
            log.warning(f"upsert failed: {src['external_id']}")

    # Save manifest
    manifest["version"] = 1
    manifest["last_full_seed_at"] = int(time.time())
    manifest["sources"] = new_manifest_sources
    save_manifest(manifest)

    log.info(f"DONE — wrote {written} concepts, failed {failed}, unchanged {unchanged}")
    log.info(f"Manifest: {MANIFEST_PATH}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
