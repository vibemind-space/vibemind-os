"""Send real intents to VibeMind Bridge via WebSocket and collect research data."""
import asyncio
import json
import time
import websockets

WS_URL = "ws://localhost:8850"

INTENTS = [
    "Zeig meine Spaces",
    "Disk Status",
    "Welche Agents laufen?",
    "Notiere: Research Platform Testidee",
    "Canary Status",
]


async def send_intents():
    print(f"Connecting to {WS_URL}...")
    async with websockets.connect(WS_URL) as ws:
        print(f"Connected!\n")

        for text in INTENTS:
            print(f">>> {text}")
            await ws.send(json.dumps({"type": "chat_text_input", "text": text}))

            # Wait for chat_response
            try:
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    data = json.loads(raw)
                    msg_type = data.get("type", "")

                    if msg_type == "chat_response":
                        success = data.get("success", False)
                        message = data.get("message", "")[:150]
                        event = data.get("event_type", "?")
                        print(f"    [{event}] {'OK' if success else 'FAIL'}: {message}")
                        break
                    # Skip other broadcast messages
            except asyncio.TimeoutError:
                print(f"    (timeout - no response in 30s)")

            time.sleep(1)

    print(f"\nDone. Check research_data.db for logged intents.")


if __name__ == "__main__":
    asyncio.run(send_intents())
