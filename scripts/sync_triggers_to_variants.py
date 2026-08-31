"""Sync voice_triggers from data/space_capabilities/<space>.yml into
voice/python/config/training_variants.yml — using stem-overlap to map
tool names to registry event_types.

Usage:
  python scripts/sync_triggers_to_variants.py --space bubbles
  python scripts/sync_triggers_to_variants.py --space all
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CAP_DIR = ROOT / "data" / "space_capabilities"
VARIANTS_PATH = ROOT / "voice" / "python" / "config" / "training_variants.yml"


def _stem(s: str) -> set[str]:
    return set(re.split(r"[_\.]+", s.lower()))


def map_tools_to_events(inv: dict) -> dict[str, list[str]]:
    """tool_name -> list of registry event_types."""
    out: dict[str, list[str]] = {}
    reg_events = {e["event"]: e for e in inv.get("registry_events", [])}
    if not reg_events:
        return out

    # 1) exact tool_hint match
    for ev_name, ev in reg_events.items():
        out.setdefault(ev["tool_hint"], []).append(ev_name)

    # 2) stem-overlap for code-level tool names
    for t in inv.get("tools", []):
        tname = t["name"]
        if tname in out:
            continue
        tstem = _stem(tname) - {"bubble", "bubbles", "tool", "params", "the"}
        if not tstem:
            continue
        for ev_name in reg_events:
            es = _stem(ev_name) - {"bubble", "bubbles"}
            if tstem & es:
                out.setdefault(tname, []).append(ev_name)
    return out


def sync_space(space: str) -> int:
    cap_path = CAP_DIR / f"{space}.yml"
    if not cap_path.exists():
        print(f"  [{space}] no inventory")
        return 0
    inv = yaml.safe_load(cap_path.read_text(encoding="utf-8"))
    tool_to_events = map_tools_to_events(inv)

    if VARIANTS_PATH.exists():
        variants = yaml.safe_load(VARIANTS_PATH.read_text(encoding="utf-8")) or {}
    else:
        variants = {}

    placeholder_default = {
        "name": ["Marketing", "Test", "Forschung", "Ideen", "Arbeit",
                 "Privat", "Notizen", "Projects"],
        "topic": ["AI", "Marketing", "Coding"],
        "query": ["latest news", "AI trends"],
    }

    added_events = 0
    for t in inv.get("tools", []):
        triggers = t.get("voice_triggers") or []
        if not triggers:
            continue
        evs = tool_to_events.get(t["name"]) or []
        for ev in evs:
            ent = variants.get(ev) or {"variants": [], "placeholders": placeholder_default}
            merged = list(ent.get("variants") or []) + list(triggers)
            seen, dedup = set(), []
            for v in merged:
                k = v.strip().lower()
                if k and k not in seen:
                    seen.add(k); dedup.append(v.strip())
            ent["variants"] = dedup
            if "placeholders" not in ent or not ent["placeholders"]:
                ent["placeholders"] = placeholder_default
            variants[ev] = ent
            added_events += 1

    if added_events:
        VARIANTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(VARIANTS_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(variants, f, allow_unicode=True, sort_keys=False, width=120)
    print(f"  [{space}] synced {added_events} event entries "
          f"(from {sum(1 for t in inv.get('tools', []) if t.get('voice_triggers'))} tools with triggers)")
    return added_events


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", required=True)
    args = ap.parse_args()
    if args.space == "all":
        spaces = sorted(p.stem for p in CAP_DIR.glob("*.yml")
                        if not p.stem.startswith("_"))
        total = 0
        for s in spaces:
            total += sync_space(s)
        print(f"\nTotal events synced: {total}")
    else:
        sync_space(args.space)
    return 0


if __name__ == "__main__":
    sys.exit(main())
