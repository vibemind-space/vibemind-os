"""Test spaces with proper rate limiting for Groq free tier (30K TPM)."""
import asyncio
import json
import time
import websockets

WS_URL = "ws://localhost:8850"

# One intent per space, with 30s delay between (Groq rate limit)
INTENTS = [
    "Zeig meine Spaces",
    "Notiere: Integration Test Notiz",
    "Disk Status",
    "Zeig geplante Aufgaben",
    "N8n Status",
    "Recherchiere kuenstliche Intelligenz",
    "Minibook Status",
    "Rowboat Status",
]


async def run():
    print(f"Connecting to {WS_URL}...")
    print(f"(30s delay between intents for Groq rate limit)\n")

    async with websockets.connect(WS_URL, ping_interval=None, close_timeout=60) as ws:
        for i, text in enumerate(INTENTS):
            print(f"[{i+1}/{len(INTENTS)}] >>> {text}")
            await ws.send(json.dumps({"type": "chat_text_input", "text": text}))

            try:
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=45)
                    data = json.loads(raw)
                    if data.get("type") == "chat_response":
                        event = data.get("event_type", "?")
                        success = data.get("success", False)
                        message = (data.get("message") or "")[:120]
                        status = "OK" if success else "FAIL"
                        print(f"        [{status}] {event:30s} | {message}")
                        break
            except asyncio.TimeoutError:
                print(f"        [TIME] no response in 45s")

            if i < len(INTENTS) - 1:
                print(f"        (waiting 30s for Groq rate limit...)")
                await asyncio.sleep(30)

    print(f"\nDone.")


if __name__ == "__main__":
    asyncio.run(run())
