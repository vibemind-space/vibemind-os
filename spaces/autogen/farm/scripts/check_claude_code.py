import sys
sys.path.insert(0, "c:/Users/User/Desktop/roaboat")
from minibook.swarm.input_parser import parse_input_file, generate_sales_tools_py, generate_core_team_yamls
from pathlib import Path

m = parse_input_file(Path("c:/Users/User/Desktop/roaboat/input.md"))

# Check core team tools
print("=== CORE TEAM TOOLS ===")
for name, info in m["core_team"].items():
    tools = info.get("tools", [])
    has_cc = "claude_code" in tools
    print(f"  {name}: {tools} {'OK' if has_cc else 'MISSING claude_code!'}")

# Generate tools.py for core team and check
core_files = generate_core_team_yamls(m)
print("\n=== GENERATED CORE AGENT TOOLS ===")
for path, content in core_files.items():
    if "agent.yml" in path:
        if "claude_code" in content:
            print(f"  {path}: has claude_code")
        else:
            print(f"  {path}: MISSING claude_code")

# Check tools.py generation
all_agents = dict(m["core_team"])
for team in m["sub_teams"].values():
    all_agents.update(team["agents"])
tools_py = generate_sales_tools_py(all_agents)
print(f"\n=== TOOLS.PY ===")
print(f"  Has 'import asyncio': {'import asyncio' in tools_py}")
print(f"  Has 'async def claude_code': {'async def claude_code' in tools_py}")
print(f"  Has 'claude -p': {'claude' in tools_py and '-p' in tools_py}")
print(f"  Total lines: {len(tools_py.splitlines())}")
