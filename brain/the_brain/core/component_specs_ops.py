"""
component_specs_ops.py — Phase 11.W2 Stage B

Executor für die Capability `component_requirements`. Liest die
data/component_specs.yaml-Wissensquelle und liefert für einen
Komponenten-Namen (a) die Soll-Anforderungen + (b) den Ist-Stand der
Bubble (welche pro-requirement Notes schon existieren).

Pfad: data/component_specs.yaml → für `component_name` matchen →
gegen canvas_nodes der Bubble vergleichen → "Lücken"-Antwort.

Note-Konvention: Pro-Requirement-Note hat den Titel
"<component_name>__<req.id>" (z.B. "Auth_Identity__jwt_flow"). Wenn
diese Note in der Bubble fehlt, ist die Anforderung "offen". Wenn sie
da ist, ist sie "erledigt".

Wird von core/capability_targets.py registriert (siehe `idea.create`-
Mapping als Vorbild).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .supabase_ideas_client import SupabaseIdeasClient

logger = logging.getLogger(__name__)

# Pfad zur YAML — relativ zum Brain-Repo, gleich wie data/capabilities.yaml.
_SPECS_PATH = Path(__file__).resolve().parent.parent / "data" / "component_specs.yaml"

# Module-level cache. reload_specs() invalidiert + lädt neu.
_specs_cache: Optional[Dict[str, Any]] = None


def _load_specs(force: bool = False) -> Dict[str, Any]:
    """Lazy-load + cache der YAML. force=True für reload."""
    global _specs_cache
    if _specs_cache is not None and not force:
        return _specs_cache
    if not _SPECS_PATH.exists():
        logger.warning("component_specs.yaml not found at %s", _SPECS_PATH)
        _specs_cache = {"bubble": "", "components": []}
        return _specs_cache
    with _SPECS_PATH.open(encoding="utf-8") as f:
        _specs_cache = yaml.safe_load(f) or {}
    logger.info(
        "component_specs loaded: bubble=%s components=%d",
        _specs_cache.get("bubble"),
        len(_specs_cache.get("components") or []),
    )
    return _specs_cache


def reload_specs() -> Dict[str, Any]:
    """Force re-read der YAML — für /api/component_specs/reload Endpoint
    falls jemand die YAML im laufenden Brain editiert."""
    return _load_specs(force=True)


def _decode_multiarg(params: Dict[str, Any]) -> Dict[str, Any]:
    """Mirror of supabase_ideas_ops._decode_multiarg — promotes
    value-JSON-Bag-Keys auf top-level."""
    if not isinstance(params, dict):
        return {}
    raw = params.get("value")
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            import json as _json
            decoded = _json.loads(raw)
            if isinstance(decoded, dict):
                for k, v in decoded.items():
                    params.setdefault(k, v)
        except Exception:
            pass
    return params


def _extract_component_name(params: Dict[str, Any]) -> str:
    """Mine the component name from the param-bag or _intent.

    The planner passes the arg via `component`, `component_name`, `name`,
    `title`, or `value`. Falls all empty, scan _intent for the first
    component_specs.yaml-name token (substring match, case-insensitive).
    """
    params = _decode_multiarg(params)
    for k in ("component", "component_name", "name", "title", "value"):
        v = params.get(k)
        if isinstance(v, str) and v.strip():
            cleaned = v.strip().rstrip(".,;:?!").strip("\"'")
            if cleaned and len(cleaned) <= 80:
                return cleaned
    intent = (params.get("_intent") or "").strip() if isinstance(params, dict) else ""
    if not intent:
        return ""
    # Try to find a component-name token from the loaded specs by substring
    # match (case-insensitive). Longest match wins so "Auth_Identity"
    # beats "Auth".
    specs = _load_specs()
    names = [
        (c.get("name") or "").strip()
        for c in (specs.get("components") or [])
        if isinstance(c, dict)
    ]
    names = sorted([n for n in names if n], key=len, reverse=True)
    for n in names:
        if re.search(rf"\b{re.escape(n)}\b", intent, re.I):
            return n
    # Bare-token last-resort: "Auth" / "Payment" alone.
    m = re.search(
        r"\b(Auth|Payment|Routing|Ticket|Wallet|NFC|Push|"
        r"Datenmodell|DSGVO|eIDAS|BSI|Sentry|K8s|DB_REST|API)\b",
        intent, re.I,
    )
    if m:
        return m.group(1)
    return ""


def _find_component(
    specs: Dict[str, Any], name: str,
) -> Optional[Dict[str, Any]]:
    """Look up a component by name (case-insensitive). Exact match first,
    then prefix, then substring."""
    if not name:
        return None
    comps = [c for c in (specs.get("components") or []) if isinstance(c, dict)]
    n_lower = name.lower()
    for c in comps:
        if (c.get("name") or "").lower() == n_lower:
            return c
    for c in comps:
        cn = (c.get("name") or "").lower()
        if cn.startswith(n_lower) or n_lower.startswith(cn):
            return c
    for c in comps:
        if n_lower in (c.get("name") or "").lower():
            return c
    return None


async def lookup_op(
    client: SupabaseIdeasClient, params: Dict[str, Any],
) -> Dict[str, Any]:
    """Phase 11.W2 (B.2) — `component_requirements` capability executor.

    Returns a structured dict with the SOLL (requires from YAML) and the
    IST (which pro-requirement notes already exist in the bubble). The
    capability validator can check this — `rule:non_empty_result` is
    enough; a stricter `rule:component_specs_lookup_ok` could be added if
    we ever need it.

    Note-Konvention: pro-requirement Note title = "<component>__<req.id>".
    """
    specs = _load_specs()
    bubble_name = (specs.get("bubble") or "").strip()
    bubble_id = (specs.get("bubble_id") or "").strip()

    name = _extract_component_name(params)
    if not name:
        return {
            "ok": False,
            "error": (
                "Need a component name. Pass `component=<name>` or include "
                "the name in the intent (e.g. 'Auth', 'Payment_Layer'). "
                "Known components: "
                + ", ".join(
                    (c.get("name") or "") for c in (specs.get("components") or [])
                )[:300]
            ),
        }

    comp = _find_component(specs, name)
    if not comp:
        known = [(c.get("name") or "") for c in (specs.get("components") or [])]
        return {
            "ok": False,
            "error": f"Component {name!r} not in component_specs.yaml. Known: {known}",
        }

    requires: List[Dict[str, Any]] = list(comp.get("requires") or [])

    # IST-Stand: für jede req prüfen ob die pro-requirement Note schon da
    # ist. Note-Titel-Konvention: "<component>__<req.id>". Wir holen ALLE
    # Notes der Bubble einmal und matchen lokal (1 DB-Call statt N).
    existing_titles: set = set()
    if bubble_id:
        try:
            rows = await client.list_canvas_nodes_in_bubble(bubble_id, limit=300)
            existing_titles = {
                (r.get("title") or "").strip() for r in rows
            }
        except Exception as e:
            logger.warning("list_canvas_nodes_in_bubble failed: %s", e)

    open_reqs: List[Dict[str, Any]] = []
    done_reqs: List[Dict[str, Any]] = []
    for req in requires:
        if not isinstance(req, dict):
            continue
        req_id = (req.get("id") or "").strip()
        if not req_id:
            continue
        note_title = f"{comp.get('name', name)}__{req_id}"
        entry = {
            "id": req_id,
            "label": req.get("label") or req_id,
            "note_title": note_title,
        }
        # Also include the deterministic content so Stage C's
        # component_note_write can render it without a 2nd YAML lookup.
        if req.get("content"):
            entry["content"] = req.get("content")
        if note_title in existing_titles:
            done_reqs.append(entry)
        else:
            open_reqs.append(entry)

    # Build a human-readable summary too (Brain's final_synthesizer can use it).
    name_str = comp.get("name", name)
    if open_reqs:
        gap_lines = [f"- {r['label']} (id={r['id']})" for r in open_reqs]
        summary = (
            f"{name_str} (layer {comp.get('layer', '?')}, "
            f"owner {comp.get('owner', '?')}): {len(open_reqs)} offen, "
            f"{len(done_reqs)} erledigt.\n"
            "Offene Anforderungen:\n" + "\n".join(gap_lines)
        )
    else:
        summary = (
            f"{name_str}: alle {len(done_reqs)} Anforderungen erledigt — "
            f"keine Lücken."
        )

    return {
        "ok": True,
        "component": name_str,
        "layer": comp.get("layer"),
        "owner": comp.get("owner"),
        "bubble": bubble_name,
        "bubble_id": bubble_id,
        "requirements_total": len(requires),
        "open": open_reqs,
        "done": done_reqs,
        "summary": summary,
    }
