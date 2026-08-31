"""Augment voice-triggers for tools in a space that have none yet.

Reads data/space_capabilities/<space>.yml, finds tools without voice_triggers,
calls Haiku via claude CLI (with fungus-context per tool) to generate phrases,
writes them back into the YAML AND mirrors a training-variants entry under the
matching registry-event (if any).

Usage:
  python scripts/augment_space_triggers.py --space bubbles --count 30
  python scripts/augment_space_triggers.py --space bubbles --dry-run
  python scripts/augment_space_triggers.py --space bubbles --tools delete_bubble,enter_bubble
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CAP_DIR = ROOT / "data" / "space_capabilities"
VARIANTS_PATH = ROOT / "voice" / "python" / "config" / "training_variants.yml"
FUNGUS_DIR = ROOT / "la-fungus-search"


HAIKU_TEMPLATE = """Generate {count} natural German+English voice triggers (one per line) for a function called "{tool_name}" in the VibeMind voice assistant.

Function purpose (from docstring):
{doc}

Existing voice triggers (do NOT repeat, generate complementary phrasings):
{existing}

Real code context from the VibeMind codebase (look for existing trigger patterns):
{code_context}

Rules:
- Mix German (~60%) and English (~40%)
- Include umlaut variants (Loesche/Lösche, oeffne/öffne)
- Mix casual ("mach weg") and formal ("entferne bitte")
- Vary structure: imperative, question, statement
- Use {{name}}, {{topic}}, {{query}} placeholders for variables (NOT real names)
- Keep each phrase under 12 words
- One phrase per line, plain text only
- No numbering, no markdown, no quotes around phrases, no preamble

Output: just {count} lines, each one a complete trigger phrase."""


def _claude_cmd() -> str:
    for cand in ("claude.cmd", "claude"):
        found = shutil.which(cand)
        if found:
            return found
    return "claude"


def _fungus_python() -> str:
    cands = [
        r"C:\Users\User\.pyenv\pyenv-win\versions\3.12.0\python.exe",
        sys.executable,
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    return sys.executable


def fungus_search(query: str, top_k: int = 6) -> list[dict]:
    """Call MCPMRetriever in a subprocess (different python env)."""
    if not FUNGUS_DIR.exists():
        return []
    script = f"""
import sys, os, json, re
sys.path.insert(0, r'{FUNGUS_DIR / "src"}')
os.environ.setdefault('FUNGUS_CODEBASE', r'{ROOT}')
try:
    from embeddinggemma.mcmp_rag import MCPMRetriever
    r = MCPMRetriever(embedding_model_name='all-MiniLM-L6-v2', num_agents=50, max_iterations=10, device_mode='auto', embed_batch_size=256)
    r.load_persistent_index()
    results = r.search_direct({query!r}, top_k={top_k})
    out = []
    for item in results.get('results', []):
        content = item.get('content', '')
        m = re.search(r'# file: (.+?) \\| lines:', content)
        if m:
            f = m.group(1).replace('\\\\','/')
            body = '\\n'.join(content.split('\\n')[1:]).strip()[:500]
        else:
            f = 'unknown'; body = content.strip()[:500]
        out.append({{'file': f, 'score': float(item.get('relevance_score', 0)), 'content': body}})
    print(json.dumps(out))
except Exception as e:
    print(json.dumps([]))
"""
    try:
        p = subprocess.run(
            [_fungus_python(), "-c", script],
            capture_output=True, text=True, timeout=90,
            cwd=str(FUNGUS_DIR),
        )
        if p.returncode != 0:
            return []
        # Find last JSON-looking line in stdout
        for line in reversed(p.stdout.strip().splitlines()):
            s = line.strip()
            if s.startswith("[") or s.startswith("{"):
                d = json.loads(s)
                return d if isinstance(d, list) else []
        return []
    except Exception:
        return []


def call_haiku(tool_name: str, doc: str, existing: list[str],
               code_context: str, count: int = 30) -> list[str]:
    prompt = HAIKU_TEMPLATE.format(
        tool_name=tool_name,
        doc=(doc or "(no docstring)")[:500],
        existing="\n".join(f"- {t}" for t in existing) or "(none)",
        code_context=code_context[:5000] or "(no fungus results)",
        count=count,
    )
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    try:
        p = subprocess.run(
            [_claude_cmd(), "-p", "--model", "haiku", prompt],
            capture_output=True, text=True, timeout=180,
            shell=False, env=env,
        )
        if p.returncode != 0:
            return []
        raw = [l.strip() for l in p.stdout.splitlines() if l.strip()]
        cleaned: list[str] = []
        for l in raw:
            if l.startswith("#") or l.startswith(">") or l.startswith("```"):
                continue
            if l.startswith("**") and l.endswith("**"):
                continue
            low = l.lower()
            if any(low.startswith(p) for p in (
                "here ", "below ", "sure", "certainly", "these ", "you could ",
                "the following", "note:", "output:", "- direct ", "- formal ",
                "- with ", "- different",
            )):
                continue
            l = re.sub(r"^\s*[-*•]\s+", "", l)
            l = re.sub(r"^\s*\d+[\.\)]\s+", "", l)
            l = l.strip(' "\'`')
            if not l or len(l) > 120:
                continue
            if len(l.split()) < 2:
                continue
            cleaned.append(l)
        return cleaned[:count]
    except Exception:
        return []


def fungus_query_for_tool(tool_name: str, doc: str) -> str:
    """Build a fungus query from tool name + first words of docstring."""
    first_doc = (doc or "").split(".")[0][:120]
    name_words = re.sub(r"[_]", " ", tool_name)
    return f"{name_words} {first_doc} voice command user"


def is_helper_tool(tool: dict) -> bool:
    """Heuristic: skip internal helpers / class methods."""
    name = tool["name"]
    if name in {"register_bubble_tools", "get_bubbles_agent",
                "get_current_bubble", "get_current_bubble_db_id",
                "get_pending_agent_switch", "stream", "name"}:
        return True
    if tool.get("owner_class") in {"BubblesAgent", "IdeasAgent",
                                    "BaseBackendAgent"}:
        return True
    if name.startswith(("get_", "_", "is_", "has_", "load_", "save_")):
        return True
    return False


def augment_space(space: str, count: int, only_tools: set[str] | None,
                  dry_run: bool) -> dict[str, Any]:
    yml_path = CAP_DIR / f"{space}.yml"
    if not yml_path.exists():
        print(f"ERROR: {yml_path} not found. Run extract_space_capabilities.py first.")
        return {}
    inv = yaml.safe_load(yml_path.read_text(encoding="utf-8"))

    # Targets: tools without voice_triggers, not helpers, optionally filtered by name
    candidates = []
    for t in inv.get("tools", []):
        if is_helper_tool(t):
            continue
        if t.get("voice_triggers"):
            continue
        if only_tools and t["name"] not in only_tools:
            continue
        candidates.append(t)

    print(f"Augmenting {len(candidates)} tools in space '{space}' (count={count} per tool)")
    if not candidates:
        print("Nothing to do — all user-tools already have triggers.")
        return inv

    new_per_tool: dict[str, list[str]] = {}
    for i, t in enumerate(candidates, 1):
        q = fungus_query_for_tool(t["name"], t.get("doc", ""))
        chunks = fungus_search(q, top_k=5)
        ctx = "\n\n".join(
            f"# {c['file']}\n{c['content']}" for c in chunks[:4]
        )
        existing = list(t.get("voice_triggers") or [])
        triggers = call_haiku(t["name"], t.get("doc", ""),
                              existing, ctx, count=count)
        new_per_tool[t["name"]] = triggers
        print(f"  [{i}/{len(candidates)}] {t['name']:<32} +{len(triggers)} triggers")

    # Merge into inventory
    if not dry_run:
        for t in inv.get("tools", []):
            if t["name"] in new_per_tool:
                merged = list(t.get("voice_triggers") or []) + new_per_tool[t["name"]]
                seen, dedup = set(), []
                for v in merged:
                    k = v.strip().lower()
                    if k and k not in seen:
                        seen.add(k); dedup.append(v.strip())
                t["voice_triggers"] = dedup
        with open(yml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(inv, f, allow_unicode=True, sort_keys=False, width=120)
        print(f"Updated {yml_path}")

        # Also append to training_variants.yml: map tool -> registry event(s).
        # Two-pass mapping:
        #   1. exact: tool_hint == tool_name
        #   2. stem:  tool_name has same verb+noun stem as event_type
        #      e.g. "delete_bubble" ↔ "bubble.delete"
        registry_events = {e["event"]: e for e in inv.get("registry_events", [])}
        tool_to_events: dict[str, list[str]] = {}
        # 1) exact tool_hint match
        for ev_name, ev in registry_events.items():
            tool_to_events.setdefault(ev["tool_hint"], []).append(ev_name)

        def _stem(s: str) -> set[str]:
            return set(re.split(r"[_\.]+", s.lower()))

        # 2) stem-overlap fallback for tools we just augmented
        for tool_name in list(new_per_tool.keys()):
            if tool_name in tool_to_events:
                continue  # already mapped
            tool_stem = _stem(tool_name) - {"bubble", "bubbles", "tool"}
            for ev_name in registry_events:
                ev_stem = _stem(ev_name) - {"bubble", "bubbles"}
                if tool_stem and ev_stem and tool_stem & ev_stem:
                    tool_to_events.setdefault(tool_name, []).append(ev_name)

        if VARIANTS_PATH.exists():
            variants = yaml.safe_load(VARIANTS_PATH.read_text(encoding="utf-8")) or {}
        else:
            variants = {}
        added_events = 0
        for tool_name, triggers in new_per_tool.items():
            evs = tool_to_events.get(tool_name, [])
            for ev in evs:
                ent = variants.get(ev) or {"variants": [], "placeholders": {}}
                merged = list(ent.get("variants") or []) + triggers
                seen, dedup = set(), []
                for v in merged:
                    k = v.strip().lower()
                    if k and k not in seen:
                        seen.add(k); dedup.append(v.strip())
                ent["variants"] = dedup
                if "placeholders" not in ent or not ent["placeholders"]:
                    ent["placeholders"] = {
                        "name": ["Marketing", "Test", "Forschung", "Ideen", "Arbeit"]
                    }
                variants[ev] = ent
                added_events += 1
        if added_events:
            VARIANTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(VARIANTS_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(variants, f, allow_unicode=True, sort_keys=False, width=120)
            print(f"Updated {VARIANTS_PATH} ({added_events} event entries)")
    else:
        print("(dry-run, nothing written)")
    return inv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", required=True)
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--tools", default="",
                    help="comma-separated tool names; empty = all needing triggers")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    only = set(t.strip() for t in args.tools.split(",") if t.strip()) or None
    augment_space(args.space, args.count, only, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
