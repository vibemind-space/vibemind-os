"""Test guided video workflow live via Bridge."""
import asyncio
import json
import time
import websockets

WS_URL = "ws://localhost:8850"

INTENTS = [
    "Video Status",
    "Ich will ein Video machen",
    "Zeig meine Videos",
]


async def run():
    print(f"Connecting to {WS_URL}...\n")
    async with websockets.connect(WS_URL, ping_interval=None) as ws:
        for text in INTENTS:
            print(f">>> {text}")
            await ws.send(json.dumps({"type": "chat_text_input", "text": text}))
            try:
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=45)
                    data = json.loads(raw)
                    if data.get("type") == "chat_response":
                        event = data.get("event_type", "?")
                        msg = (data.get("message") or "")[:250]
                        print(f"  [{event}]")
                        print(f"  {msg}\n")
                        break
            except asyncio.TimeoutError:
                print(f"  [TIMEOUT]\n")
            time.sleep(30)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(run())
