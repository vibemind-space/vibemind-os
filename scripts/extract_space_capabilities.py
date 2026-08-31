"""Extract all capabilities (tools + voice triggers + params) per space.

Walks vibemind-os/spaces/<space>/{tools,agents,adapted}/*.py, parses every
top-level def + Class methods via AST, pulls docstrings and "Voice triggers:"
lines, joins with the space_agent_registry + EVENT_SPACE_MAP, and writes:

  data/space_capabilities/<space>.yml   <- machine-readable, full inventory
  data/space_capabilities/<space>.md    <- human-readable summary
  data/space_capabilities/_index.md     <- master overview, all 13 spaces

Pure read-only on the codebase. No LLM, no Brain calls. Pure stdlib + pyyaml.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPACES_ROOT = ROOT / "spaces"
OUTPUT_DIR = ROOT / "data" / "space_capabilities"
REGISTRY_YML = ROOT / "config" / "space_agent_registry.yml"
EVENT_SPACE_MAP_FILE = ROOT / "brain" / "the_brain" / "core" / "space_routing_head.py"


# Subdirectories under spaces/<name>/ that we treat as tool-source.
TOOL_SUBDIRS = ["tools", "adapted", "agents"]

# Logical spaces that physically live inside another space's directory.
# Registry uses the logical name; filesystem uses the host dir.
SPACE_ALIASES: dict[str, list[str]] = {
    "bubbles":  ["ideas"],          # BubblesAgent lives in spaces/ideas/agents/
    "roarboot": ["rowboat"],        # rowboat dir
    "flowzen":  ["flowzen/flowzen"],  # nested submodule
    "agentfarm": ["autogen"],       # AutoGen-based
}

# When a space is alias-only (no own physical dir), we filter the host's tools
# by these substrings (in path or function name) so we don't claim every tool
# of the host. Empty list = take all tools from the host dir.
SPACE_FILTERS: dict[str, list[str]] = {
    "bubbles":  ["bubble"],
    "roarboot": ["rowboat", "roarboot"],
    "flowzen":  ["flowzen", "rose"],
    "agentfarm": ["agentfarm", "autogen", "team"],
}

# Files explicitly skipped (helpers, infra, no capabilities of interest).
SKIP_FILES = {"__init__.py", "_helpers.py", "constants.py"}

# Regex: docstring "Voice triggers" block — captures all quoted triggers.
VOICE_TRIGGER_RE = re.compile(
    r"voice\s*trigg?ers?\s*[:\-]\s*((?:[\"\'“„].+?[\"\'”“]\s*[,;\n]?\s*)+)",
    re.IGNORECASE,
)
QUOTED_RE = re.compile(r"[\"\'“„](.+?)[\"\'”“]")


def _load_event_space_map() -> dict[str, str]:
    """Parse EVENT_SPACE_MAP via AST without importing the brain module."""
    if not EVENT_SPACE_MAP_FILE.exists():
        return {}
    tree = ast.parse(EVENT_SPACE_MAP_FILE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "EVENT_SPACE_MAP":
                    try:
                        return ast.literal_eval(node.value)
                    except Exception:
                        return {}
    return {}


def _load_registry() -> dict[str, Any]:
    if not REGISTRY_YML.exists():
        return {"spaces": {}}
    return yaml.safe_load(REGISTRY_YML.read_text(encoding="utf-8")) or {}


def _extract_voice_triggers(docstring: str) -> list[str]:
    if not docstring:
        return []
    triggers: list[str] = []
    for m in VOICE_TRIGGER_RE.finditer(docstring):
        for q in QUOTED_RE.finditer(m.group(1)):
            t = q.group(1).strip()
            if 1 < len(t) < 200:
                triggers.append(t)
    return triggers


def _arg_info(args: ast.arguments) -> list[dict[str, Any]]:
    """Return [{name, annotation, default}] for positional + keyword args."""
    out = []
    posargs = list(args.args)
    kwonly = list(args.kwonlyargs)
    defaults = list(args.defaults)
    kw_defaults = list(args.kw_defaults)

    # Skip self/cls
    if posargs and posargs[0].arg in ("self", "cls"):
        posargs = posargs[1:]

    n_required = len(posargs) - len(defaults)
    for i, a in enumerate(posargs):
        item = {"name": a.arg, "kind": "positional"}
        if a.annotation is not None:
            try:
                item["annotation"] = ast.unparse(a.annotation)
            except Exception:
                item["annotation"] = "?"
        if i >= n_required:
            d = defaults[i - n_required]
            try:
                item["default"] = ast.unparse(d)
            except Exception:
                item["default"] = "?"
        else:
            item["required"] = True
        out.append(item)

    for a, d in zip(kwonly, kw_defaults):
        item = {"name": a.arg, "kind": "keyword"}
        if a.annotation is not None:
            try:
                item["annotation"] = ast.unparse(a.annotation)
            except Exception:
                item["annotation"] = "?"
        if d is None:
            item["required"] = True
        else:
            try:
                item["default"] = ast.unparse(d)
            except Exception:
                item["default"] = "?"
        out.append(item)
    return out


def _is_public_callable(name: str) -> bool:
    return not name.startswith("_")


def _short_doc(docstring: str | None, max_chars: int = 240) -> str:
    if not docstring:
        return ""
    first_para = docstring.strip().split("\n\n", 1)[0].strip()
    if len(first_para) > max_chars:
        first_para = first_para[: max_chars - 3] + "..."
    return first_para


def _walk_funcs(tree: ast.AST):
    """Yield (FunctionDef-or-AsyncFunctionDef, owner_class_or_None)."""
    for node in tree.body if hasattr(tree, "body") else []:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node, None
        elif isinstance(node, ast.ClassDef):
            for inner in node.body:
                if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield inner, node.name


def _scan_file(file: Path) -> list[dict[str, Any]]:
    """Return list of capability dicts found in this file."""
    try:
        src = file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        src = file.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [{"_parse_error": f"{file.name}: {e}"}]

    out: list[dict[str, Any]] = []
    for fn, owner in _walk_funcs(tree):
        if not _is_public_callable(fn.name):
            continue
        # Skip dunder + obvious test fixtures
        if fn.name.startswith("test_"):
            continue
        doc = ast.get_docstring(fn) or ""
        triggers = _extract_voice_triggers(doc)
        out.append({
            "name": fn.name,
            "owner_class": owner,
            "is_async": isinstance(fn, ast.AsyncFunctionDef),
            "file": str(file.relative_to(ROOT)).replace("\\", "/"),
            "line": fn.lineno,
            "doc": _short_doc(doc),
            "voice_triggers": triggers,
            "args": _arg_info(fn.args),
        })
    return out


def _scan_space(space: str) -> dict[str, Any]:
    # Build search-roots: the canonical space dir + any aliases
    candidate_dirs: list[Path] = [SPACES_ROOT / space]
    for alias in SPACE_ALIASES.get(space, []):
        candidate_dirs.append(SPACES_ROOT / alias)

    candidate_dirs = [d for d in candidate_dirs if d.exists()]
    if not candidate_dirs:
        return {"space": space, "exists": False, "tool_count": 0,
                "tools": [], "parse_errors": [], "scanned_dirs": []}

    tools: list[dict[str, Any]] = []
    parse_errors: list[str] = []
    scanned: list[str] = []

    for base in candidate_dirs:
        for sub in TOOL_SUBDIRS:
            sub_dir = base / sub
            if not sub_dir.exists():
                continue
            scanned.append(str(sub_dir.relative_to(ROOT)).replace("\\", "/"))
            for f in sorted(sub_dir.rglob("*.py")):
                if f.name in SKIP_FILES:
                    continue
                for cap in _scan_file(f):
                    if "_parse_error" in cap:
                        parse_errors.append(cap["_parse_error"])
                    else:
                        tools.append(cap)

    # Dedup: same name + same file → keep first
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for t in tools:
        key = (t["name"], t["file"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)

    # Filter when the space is an alias of a host (e.g. bubbles -> ideas)
    filters = SPACE_FILTERS.get(space)
    if filters and not (SPACES_ROOT / space).exists():
        def _matches(t: dict) -> bool:
            hay = (t["file"] + " " + t["name"]).lower()
            return any(f.lower() in hay for f in filters)
        deduped = [t for t in deduped if _matches(t)]

    return {
        "space": space,
        "exists": True,
        "tool_count": len(deduped),
        "tools": deduped,
        "parse_errors": parse_errors,
        "scanned_dirs": scanned,
    }


def _join_with_registry(scan: dict, registry_space: dict | None,
                       event_space_map: dict[str, str]) -> dict:
    """Add registry-known events + their tool-hints to the inventory."""
    out = dict(scan)
    if not registry_space:
        out["registry_agent"] = None
        out["registry_events"] = []
        out["registry_mcp_servers"] = []
    else:
        out["registry_agent"] = registry_space.get("agent")
        out["registry_mcp_servers"] = registry_space.get("mcp_servers", [])
        events = registry_space.get("events") or {}
        out["registry_events"] = [
            {
                "event": ev,
                "tool_hint": cfg.get("tool"),
                "required_params": cfg.get("required_params", []),
            }
            for ev, cfg in events.items()
        ]
    # All events globally that EVENT_SPACE_MAP routes to this space
    out["all_routed_events"] = sorted(
        ev for ev, sp in event_space_map.items() if sp == out["space"]
    )
    return out


def _summarize(out: dict) -> dict:
    triggers_total = sum(len(t.get("voice_triggers", [])) for t in out["tools"])
    documented = sum(1 for t in out["tools"] if t.get("doc"))
    with_triggers = sum(1 for t in out["tools"] if t.get("voice_triggers"))
    return {
        "tool_count": out["tool_count"],
        "documented": documented,
        "tools_with_voice_triggers": with_triggers,
        "voice_trigger_total": triggers_total,
        "registry_event_count": len(out.get("registry_events", [])),
        "all_routed_event_count": len(out.get("all_routed_events", [])),
        "parse_errors": len(out.get("parse_errors", [])),
    }


def _render_markdown(space: str, inv: dict) -> str:
    summary = _summarize(inv)
    lines = [
        f"# Space Capabilities — `{space}`",
        "",
        f"_Generated by `scripts/extract_space_capabilities.py` — read-only inventory._",
        "",
        "## Summary",
        "",
        f"- Registry agent: `{inv.get('registry_agent')}`",
        f"- MCP servers in scope: {inv.get('registry_mcp_servers') or '–'}",
        f"- Tools discovered: **{summary['tool_count']}**",
        f"- Documented (have docstring): {summary['documented']}",
        f"- With explicit voice-triggers: {summary['tools_with_voice_triggers']}  "
        f"(total trigger phrases: {summary['voice_trigger_total']})",
        f"- Registry events declared: {summary['registry_event_count']}",
        f"- Events routed by EVENT_SPACE_MAP: {summary['all_routed_event_count']}",
    ]
    if summary["parse_errors"]:
        lines.append(f"- ⚠️ Parse errors: {summary['parse_errors']}")
    lines.append("")

    # Registry events block
    if inv.get("registry_events"):
        lines.append("## Registry Events (intent → tool)")
        lines.append("")
        lines.append("| event_type | tool_hint | required_params |")
        lines.append("|---|---|---|")
        for e in inv["registry_events"]:
            params = ", ".join(e.get("required_params") or []) or "–"
            lines.append(f"| `{e['event']}` | `{e['tool_hint']}` | {params} |")
        lines.append("")

    # All routed events from EVENT_SPACE_MAP not in registry
    routed = set(inv.get("all_routed_events") or [])
    in_registry = {e["event"] for e in inv.get("registry_events") or []}
    extra_routed = sorted(routed - in_registry)
    if extra_routed:
        lines.append("## Routed but not in registry")
        lines.append("")
        for ev in extra_routed:
            lines.append(f"- `{ev}`")
        lines.append("")

    # Tool inventory
    lines.append("## Tool Inventory")
    lines.append("")
    if not inv["tools"]:
        lines.append("_No tools discovered in `spaces/" + space + "/{tools,adapted,agents}/`._")
    else:
        # Group by file for readability
        by_file: dict[str, list[dict]] = defaultdict(list)
        for t in inv["tools"]:
            by_file[t["file"]].append(t)
        for fpath in sorted(by_file):
            lines.append(f"### `{fpath}`")
            lines.append("")
            for t in by_file[fpath]:
                klass = f" — `{t['owner_class']}` method" if t["owner_class"] else ""
                async_tag = " *(async)*" if t["is_async"] else ""
                lines.append(f"#### `{t['name']}`{async_tag}{klass}")
                lines.append("")
                if t["doc"]:
                    lines.append(f"> {t['doc']}")
                    lines.append("")
                if t["args"]:
                    arg_strs = []
                    for a in t["args"]:
                        bits = [a["name"]]
                        if "annotation" in a:
                            bits.append(f": {a['annotation']}")
                        if "default" in a:
                            bits.append(f" = {a['default']}")
                        if a.get("required"):
                            bits.append(" *(required)*")
                        arg_strs.append("".join(bits))
                    lines.append("- args: " + ", ".join(arg_strs))
                if t["voice_triggers"]:
                    lines.append("- voice triggers:")
                    for v in t["voice_triggers"]:
                        lines.append(f"  - \"{v}\"")
                lines.append(f"- source: `{t['file']}:{t['line']}`")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_index(all_invs: dict[str, dict]) -> str:
    lines = [
        "# Space Capabilities — Master Index",
        "",
        "_Auto-generated. One file per space in this directory._",
        "",
        "| Space | Agent | Tools | Voice-Triggered | Registry Events | Routed Events |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for sp in sorted(all_invs):
        inv = all_invs[sp]
        s = _summarize(inv)
        agent = inv.get("registry_agent") or "–"
        lines.append(
            f"| [{sp}]({sp}.md) | `{agent}` | {s['tool_count']} | "
            f"{s['tools_with_voice_triggers']} | {s['registry_event_count']} | "
            f"{s['all_routed_event_count']} |"
        )
    lines.append("")
    lines.append("## Files")
    lines.append("")
    for sp in sorted(all_invs):
        lines.append(f"- [{sp}.yml]({sp}.yml) — machine-readable inventory")
        lines.append(f"- [{sp}.md]({sp}.md) — human-readable inventory")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    registry = _load_registry()
    event_space_map = _load_event_space_map()
    registry_spaces = registry.get("spaces", {}) or {}

    # Spaces to scan: union of registry + filesystem
    fs_spaces = sorted(p.name for p in SPACES_ROOT.iterdir()
                       if p.is_dir() and not p.name.startswith("_") and p.name != "config")
    target_spaces = sorted(set(fs_spaces) | set(registry_spaces.keys()))

    print(f"Scanning {len(target_spaces)} spaces in {SPACES_ROOT}")
    print(f"Output: {OUTPUT_DIR}")
    print()

    all_invs: dict[str, dict] = {}

    for space in target_spaces:
        scan = _scan_space(space)
        inv = _join_with_registry(scan, registry_spaces.get(space), event_space_map)
        all_invs[space] = inv

        yml_path = OUTPUT_DIR / f"{space}.yml"
        md_path = OUTPUT_DIR / f"{space}.md"
        with open(yml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(inv, f, allow_unicode=True, sort_keys=False, width=120)
        md_path.write_text(_render_markdown(space, inv), encoding="utf-8")

        s = _summarize(inv)
        print(f"  {space:<12} tools={s['tool_count']:>3}  "
              f"voice={s['tools_with_voice_triggers']:>2}  "
              f"reg_events={s['registry_event_count']:>2}  "
              f"routed={s['all_routed_event_count']:>2}")

    # Master index
    index_path = OUTPUT_DIR / "_index.md"
    index_path.write_text(_render_index(all_invs), encoding="utf-8")

    # JSON dump for downstream tooling
    json_path = OUTPUT_DIR / "_all.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_invs, f, ensure_ascii=False, indent=2)

    print()
    print(f"Wrote {len(target_spaces)} YAMLs + {len(target_spaces)} MDs")
    print(f"Index: {index_path}")
    print(f"JSON:  {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
