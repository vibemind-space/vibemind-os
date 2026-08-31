"""Send ONE intent and wait for response."""
import asyncio
import json
import sys
import websockets

WS_URL = "ws://localhost:7850"
TEXT = sys.argv[1] if len(sys.argv) > 1 else "Was steht heute an?"

async def run():
    async with websockets.connect(WS_URL, ping_interval=None) as ws:
        print(f">>> {TEXT}")
        await ws.send(json.dumps({"type": "chat_text_input", "text": TEXT}))
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
                data = json.loads(raw)
                if data.get("type") == "chat_response":
                    event = data.get("event_type", "?")
                    msg = (data.get("message") or "")[:300]
                    print(f"[{event}]")
                    print(msg)
                    break
        except asyncio.TimeoutError:
            print("[TIMEOUT]")

asyncio.run(run())
