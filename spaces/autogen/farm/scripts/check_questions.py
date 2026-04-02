#!/usr/bin/env python3
import requests, json

r = requests.get("http://localhost:8899/api/v1/questions/pending")
print(f"Status: {r.status_code}")
data = r.json()
print(f"Pending questions: {len(data)}")
for q in data:
    print(f"  [{q['type']}] {q['status']} | {q['message'][:80]}")
    print(f"    ID: {q['id']}")
    print(f"    Created: {q['created_at']}")
