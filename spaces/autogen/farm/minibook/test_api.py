import json, urllib.request

creds = json.load(open("swarm_agents.json"))
key = creds["SwarmManager"]["api_key"]
print(f"Key: {key[:8]}...")

req = urllib.request.Request(
    "http://localhost:3456/api/v1/projects",
    headers={"Authorization": f"Bearer {key}"}
)
try:
    resp = urllib.request.urlopen(req)
    print(f"Status: {resp.status}")
    print(resp.read().decode()[:500])
except Exception as e:
    print(f"Error: {e}")
