import json, glob
for r in sorted(glob.glob("reports/round_*.json")):
    with open(r) as f:
        d = json.load(f)
    v = d.get("verdict", {})
    red = d.get("red_team", {})
    cats = red.get("categories", [])
    print(f"{r}: Red {v.get('red_score', '?')} | Blue {v.get('blue_score', '?')} | Detection {v.get('detection_rate', 0):.0%} | Attacks {red.get('attacks_executed', '?')} | Categories {cats}")
