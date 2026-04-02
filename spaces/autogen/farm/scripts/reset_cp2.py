import json
cp = json.load(open("c:/Users/User/Desktop/roaboat/output/checkpoint.json"))
for tk in ["revops", "research"]:
    cp["sub_teams"][tk] = {}
    print(f"Reset {tk}")
cp["wiring"] = {}
print("Reset wiring")
json.dump(cp, open("c:/Users/User/Desktop/roaboat/output/checkpoint.json", "w"), indent=2)
print("Checkpoint updated")
