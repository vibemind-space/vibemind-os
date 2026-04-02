#!/usr/bin/env python3
import requests, json

agents = json.load(open("minibook/swarm_agents.json"))
key = agents["SwarmManager"]["api_key"]

r = requests.get("http://localhost:8899/api/v1/projects/1/posts", headers={"Authorization": f"Bearer {key}"})
print(f"Posts status: {r.status_code}")
if not r.ok:
    print(r.text[:500])
    exit()

data = r.json()
posts = data if isinstance(data, list) else data.get("posts", data.get("items", []))
print(f"Post count: {len(posts)}")

for p in posts[-10:]:
    pid = p.get("id", "?")
    title = str(p.get("title", "?"))[:80]
    meta = p.get("metadata", {}) or {}
    if not isinstance(meta, dict):
        meta = {}
    qtype = meta.get("question_type", "none")
    answered = meta.get("answered", False)
    print(f"  Post {pid}: [{qtype}] answered={answered} | {title}")

# Check unanswered questions
unanswered = [p for p in posts if isinstance(p.get("metadata"), dict) and p["metadata"].get("question_type") and not p["metadata"].get("answered")]
print(f"\nUnanswered questions: {len(unanswered)}")
for p in unanswered:
    print(f"  Post {p['id']}: {p['metadata']['question_type']} | {p.get('title', '?')[:80]}")
