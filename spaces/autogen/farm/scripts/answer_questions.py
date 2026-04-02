"""Answer all pending pipeline questions automatically."""
import json, urllib.request, time, sys

BASE = "http://localhost:8899"

def get_pending():
    try:
        resp = urllib.request.urlopen(f"{BASE}/api/v1/questions/pending", timeout=5)
        data = json.loads(resp.read())
        return data if isinstance(data, list) else data.get("questions", [])
    except Exception as e:
        return []

def answer(qid, action="approve", text=""):
    payload = json.dumps({"action": action, "text": text}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/v1/questions/{qid}/answer",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        print(f"  Error answering {qid[:8]}: {e}")
        return None

def main():
    print("=== Auto-answering pipeline questions (10min) ===", flush=True)
    # Clear old pending
    for q in get_pending():
        answer(q["id"], "approve", "Approved.")

    end_time = time.time() + 600
    while time.time() < end_time:
        time.sleep(3)
        for q in get_pending():
            qid = q["id"]
            qtype = q.get("type", "?")
            msg = (q.get("message", ""))[:80]
            print(f"  [{qtype}] {msg}", flush=True)
            if qtype == "mcp_config":
                answer(qid, "reply", "skip")
            else:
                answer(qid, "approve", "Approved. Proceed.")
            print(f"    -> OK", flush=True)
    print("\nDone.", flush=True)

if __name__ == "__main__":
    main()
