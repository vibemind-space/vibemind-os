import json
cp = json.load(open("c:/Users/User/Desktop/roaboat/output/checkpoint.json"))
cp["sub_teams"]["research"] = {}
print("Reset research")
cp["wiring"] = {}
print("Reset wiring")
json.dump(cp, open("c:/Users/User/Desktop/roaboat/output/checkpoint.json", "w"), indent=2)
print("Checkpoint updated")
