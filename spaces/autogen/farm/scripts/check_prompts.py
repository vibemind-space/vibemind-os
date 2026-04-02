import sys
sys.path.insert(0, "c:/Users/User/Desktop/roaboat")
from minibook.swarm.input_parser import parse_input_file
from pathlib import Path

m = parse_input_file(Path("c:/Users/User/Desktop/roaboat/input.md"))

print("=== CORE TEAM ===")
for name, info in m["core_team"].items():
    p = info["prompt"][:80] if info.get("prompt") else "NO PROMPT"
    print(f"  {name}: {p}...")
print()

print("=== SUB TEAMS ===")
for tk, team in m["sub_teams"].items():
    print(f"  [{tk}] manager={team['manager']}")
    for aname, ainfo in team["agents"].items():
        p = ainfo["prompt"][:80] if ainfo.get("prompt") else "NO PROMPT"
        print(f"    {aname}: {p}...")
    print()
