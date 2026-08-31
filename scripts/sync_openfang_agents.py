"""Sync OpenFang agent.toml files from space_agent_registry.yml.

Reads `config/space_agent_registry.yml` and for each space writes
`openfang/agents/<agent_name>/agent.toml` with the correct [mcp_allowed]
scope. Existing files are updated in place; new files are created.

Usage:
  python scripts/sync_openfang_agents.py              # write + report
  python scripts/sync_openfang_agents.py --dry-run    # report only
  python scripts/sync_openfang_agents.py --check      # exit 1 if drift
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "space_agent_registry.yml"
AGENTS_DIR = ROOT / "openfang" / "agents"


AGENT_TOML_TEMPLATE = """name = "{name}"
version = "0.1.0"
description = "{description}"
author = "vibemind"
module = "builtin:chat"
tags = ["vibemind", "brain-routed", "space:{space}"]

[model]
provider = "openrouter"
model = "anthropic/claude-3.5-sonnet"
max_tokens = 4096
temperature = 0.2
system_prompt = \"\"\"You are {name}, the VibeMind agent for the "{space}" space.

You receive structured intent envelopes with schema "vibemind.intent.v1":
  {{
    "event_type": "...",
    "space": "{space}",
    "preferred_tool": "...",
    "required_params": [...],
    "params": {{...}},
    "context": {{...}},
    "user_text": "..."
  }}

METHODOLOGY:
1. If "preferred_tool" is set, try that tool first with the provided params.
2. Fill missing required_params from "context" or "user_text".
3. Return a concise result — the user expects voice-friendly replies.

{prompt_hint}
\"\"\"

[resources]
max_llm_tokens_per_hour = 100000
max_concurrent_tools = 5

[capabilities]
tools = ["memory_store", "memory_recall"]
network = ["*"]
memory_read = ["*"]
memory_write = ["self.*"]

[mcp_allowed]
servers = [{mcp_list}]
"""


def _mcp_list_literal(servers: list[str]) -> str:
    return ", ".join(f'"{s}"' for s in servers)


def _render_agent_toml(space: str, spec: dict) -> str:
    agent = spec["agent"]
    description = spec.get(
        "description", f"VibeMind {space} agent, Brain-routed."
    )
    prompt_hint = spec.get("system_prompt_hint", "")
    mcp_servers = spec.get("mcp_servers", [])
    return AGENT_TOML_TEMPLATE.format(
        name=agent,
        space=space,
        description=description,
        prompt_hint=prompt_hint,
        mcp_list=_mcp_list_literal(mcp_servers),
    )


def _skip_reason(space: str, spec: dict) -> str | None:
    agent = spec.get("agent", "")
    if not agent:
        return "no agent name"
    if not spec.get("enabled", True):
        return "disabled"
    # Don't overwrite pre-existing hand-curated agents
    for protected in ("brain-coder", "rowboat-knowledge", "brain-fallback"):
        if agent == protected:
            return f"protected (pre-existing): {agent}"
    return None


def sync(dry_run: bool = False, check: bool = False) -> int:
    with open(REGISTRY, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    spaces = data.get("spaces", {}) or {}

    written = 0
    skipped = 0
    drift = 0
    for space, spec in spaces.items():
        reason = _skip_reason(space, spec)
        agent = spec.get("agent", "")
        if reason:
            print(f"  skip  {space:<12} ({agent:<24}) — {reason}")
            skipped += 1
            continue
        target_dir = AGENTS_DIR / agent
        target_file = target_dir / "agent.toml"
        new_content = _render_agent_toml(space, spec)
        existing = target_file.read_text(encoding="utf-8") if target_file.exists() else ""
        if existing == new_content:
            print(f"  ok    {space:<12} -> {agent}")
            continue
        if check:
            print(f"  DRIFT {space:<12} -> {agent}")
            drift += 1
            continue
        if dry_run:
            print(f"  would {space:<12} -> {agent}")
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file.write_text(new_content, encoding="utf-8")
        action = "update" if existing else "create"
        print(f"  {action:<5} {space:<12} -> {agent}")
        written += 1

    print()
    print(f"Summary: {written} written, {skipped} skipped, {drift} drift")
    if check and drift > 0:
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true", help="exit 1 if drift")
    args = ap.parse_args()
    return sync(dry_run=args.dry_run, check=args.check)


if __name__ == "__main__":
    sys.exit(main())
