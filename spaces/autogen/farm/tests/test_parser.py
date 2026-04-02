#!/usr/bin/env python3
"""Quick test for input_parser."""
import sys
sys.path.insert(0, "minibook")
from pathlib import Path
from swarm.input_parser import parse_input_file

manifest = parse_input_file(Path("input.md"))
print(f"Org: {manifest['org_name']}")
print(f"Total agents: {manifest['agent_count']}")
print(f"Core team ({len(manifest['core_team'])}): {list(manifest['core_team'].keys())}")
print(f"Sub-teams ({len(manifest['sub_teams'])}): {list(manifest['sub_teams'].keys())}")
for tk, tv in manifest["sub_teams"].items():
    print(f"  {tk}: {tv['manager']} -> {list(tv['agents'].keys())}")

# Check every agent has tools
missing = []
for name, info in manifest["core_team"].items():
    if not info.get("tools"):
        missing.append(name)
for tk, tv in manifest["sub_teams"].items():
    for name, info in tv["agents"].items():
        if not info.get("tools"):
            missing.append(name)
print(f"Agents missing tools: {missing if missing else 'None (all have tools)'}")

# Check prompts
no_prompt = []
for name, info in manifest["core_team"].items():
    if not info.get("prompt") or len(info["prompt"]) < 20:
        no_prompt.append(name)
print(f"Core agents with short/no prompt: {no_prompt if no_prompt else 'All have prompts'}")

# Check total specialist count
total_specs = sum(len(tv["agents"]) for tv in manifest["sub_teams"].values())
print(f"Total specialists across sub-teams: {total_specs}")
