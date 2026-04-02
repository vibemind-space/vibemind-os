import json

with open("c:/Users/User/Desktop/roaboat/output/checkpoint.json", "r") as f:
    cp = json.load(f)

cp["sub_teams"]["research"] = {
    "build": "FAIL", "run": "N/A", "eval": "N/A",
    "eval_reason": "", "output": "", "docker_down": False, "retries": 0
}
cp["wiring"] = {
    "build": "FAIL", "run": "N/A", "eval": "N/A",
    "eval_reason": "", "output": "", "docker_down": False, "retries": 0
}

with open("c:/Users/User/Desktop/roaboat/output/checkpoint.json", "w") as f:
    json.dump(cp, f, indent=2)

print("Reset research + wiring in checkpoint")
