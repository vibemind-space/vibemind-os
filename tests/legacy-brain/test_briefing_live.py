"""Test morning briefing + greeting live via Bridge."""
import asyncio
import json
import time
import websockets

WS_URL = "ws://localhost:7850"

CONVERSATION = [
    ("Guten Morgen", "Should be greeting, NOT briefing"),
    ("Was steht heute an?", "Should be system.morning_briefing"),
    ("Disk Status", "Should be openfang.disk_status"),
]

async def run():
    print(f"Connecting to {WS_URL}...\n")
    async with websockets.connect(WS_URL, ping_interval=None) as ws:
        for text, expected in CONVERSATION:
            print(f">>> {text}")
            print(f"    (expected: {expected})")
            await ws.send(json.dumps({"type": "chat_text_input", "text": text}))
            try:
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=45)
                    data = json.loads(raw)
                    if data.get("type") == "chat_response":
                        event = data.get("event_type", "?")
                        msg = (data.get("message") or "")[:200]
                        print(f"    [{event}]")
                        print(f"    {msg}\n")
                        break
            except asyncio.TimeoutError:
                print(f"    [TIMEOUT]\n")
            time.sleep(30)  # Groq rate limit
    print("Done.")

if __name__ == "__main__":
    asyncio.run(run())
