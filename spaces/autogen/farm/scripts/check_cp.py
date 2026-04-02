import json
cp = json.load(open("c:/Users/User/Desktop/roaboat/output/checkpoint.json"))
print("Core:", cp.get("core",{}).get("eval","?"))
for tk, info in cp.get("sub_teams",{}).items():
    ev = info.get("eval", "PENDING")
    retries = info.get("retries", 0)
    print(f"  {tk}: {ev} (retries: {retries})")
passed = sum(1 for v in [cp.get("core",{})] + list(cp.get("sub_teams",{}).values()) if v.get("eval") == "PASS")
total = 1 + len(cp.get("sub_teams",{}))
print(f"Total: {passed}/{total} PASS")
