import sys
sys.path.insert(0, "c:/Users/User/Desktop/roaboat")
from minibook.swarm.input_parser import parse_input_file, generate_sales_tools_py
from pathlib import Path

m = parse_input_file(Path("c:/Users/User/Desktop/roaboat/input.md"))
all_agents = dict(m["core_team"])
for t in m["sub_teams"].values():
    all_agents.update(t["agents"])
tools = generate_sales_tools_py(all_agents)

if "claude_cli" in tools:
    print("WARNING: claude_cli still in tools.py!")
    for i, line in enumerate(tools.splitlines(), 1):
        if "claude_cli" in line:
            print(f"  Line {i}: {line.strip()}")
else:
    print("OK: No claude_cli in generated tools.py")
