"""Quick test of all OpenFang agents via API."""
import json
import urllib.request
import urllib.error
import time

resp = urllib.request.urlopen("http://127.0.0.1:50051/api/agents", timeout=5)
agents = json.loads(resp.read())

for agent in sorted(agents, key=lambda x: x["name"]):
    name = agent["name"]
    aid = agent["id"]
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:50051/api/agents/{aid}/message",
            data=json.dumps({"message": "status"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        r = urllib.request.urlopen(req, timeout=30)
        body = json.loads(r.read())
        status = "OK" if "response" in body else "EMPTY"
        resp_len = len(body.get("response", ""))
        print(f"{name:30s} {status:8s} len={resp_len}")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()[:100]
        print(f"{name:30s} FAIL     {err_body[:80]}")
    except Exception as e:
        print(f"{name:30s} ERROR    {str(e)[:80]}")
    time.sleep(0.5)
