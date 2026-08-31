"""Test ALL spaces live via Bridge — find which ones actually work."""
import asyncio
import json
import time
import websockets

WS_URL = "ws://localhost:8850"

# All spaces with their native event types
INTENTS = [
    # Ideas (should work)
    ("Zeig meine Spaces", "bubble.*"),
    ("Notiere: Live Test Idee", "idea.*"),

    # OpenFang (should work)
    ("Disk Status", "openfang.*"),
    ("Welche Agents laufen?", "openfang.*"),
    ("Canary Status", "openfang.*"),

    # Coding (should work)
    ("Code Status", "code.*"),

    # Desktop (should work)
    ("Screenshot machen", "desktop.*"),

    # Schedule (should work)
    ("Zeig geplante Aufgaben", "schedule.*"),

    # Research (may work - keyword fallback)
    ("Recherchiere kuenstliche Intelligenz", "research.*"),

    # N8n (needs Docker)
    ("N8n Status", "n8n.*"),

    # Video (needs submodule)
    ("Video Status", "video.*"),

    # Rowboat (needs Docker)
    ("Suche im Knowledge Graph", "roarboot.*"),

    # AgentFarm (may work)
    ("Agent Farm Status", "agentfarm.*"),
]


async def run():
    print(f"Connecting to {WS_URL}...\n")
    async with websockets.connect(WS_URL, ping_timeout=60) as ws:
        for text, expected_prefix in INTENTS:
            print(f">>> {text}")
            await ws.send(json.dumps({"type": "chat_text_input", "text": text}))

            try:
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=20)
                    data = json.loads(raw)
                    if data.get("type") == "chat_response":
                        event = data.get("event_type", "?")
                        success = data.get("success", False)
                        message = (data.get("message") or "")[:100]
                        prefix_match = event.split(".")[0] + ".*"
                        status = "OK" if success and "Problem" not in message and "Error" not in message else "FAIL"
                        print(f"  [{status:4s}] {event:30s} | {message}")
                        break
            except asyncio.TimeoutError:
                print(f"  [TIME] (no response in 20s)")

            time.sleep(3)  # Groq rate limit

    print(f"\nDone.")


if __name__ == "__main__":
    asyncio.run(run())
