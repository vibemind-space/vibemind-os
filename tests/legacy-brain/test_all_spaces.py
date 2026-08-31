"""Test ALL spaces via VibeMind Bridge — sends intents, checks classification + routing."""
import asyncio
import json
import time
import websockets

WS_URL = "ws://localhost:8850"

INTENTS = [
    # VibeMind native
    ("Zeig meine Spaces", "bubble.list"),
    ("Erstelle Bubble Research", "bubble.create"),
    ("Notiere: Brain Integration Test", "idea.create"),

    # OpenFang agents
    ("Disk Status", "openfang.disk_status"),
    ("Welche Agents laufen?", "openfang.agent_status"),
    ("Scanne auf Sicherheitsluecken", "openfang.vuln_scan"),

    # Other spaces
    ("Erinnere mich in 5 Minuten", "schedule.create"),
    ("Zeig alle Workflows", "n8n.list"),
]


async def run():
    print(f"Connecting to {WS_URL}...\n")
    async with websockets.connect(WS_URL) as ws:
        results = []
        for text, expected_event in INTENTS:
            print(f">>> {text}")
            await ws.send(json.dumps({"type": "chat_text_input", "text": text}))

            try:
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    data = json.loads(raw)
                    if data.get("type") == "chat_response":
                        event = data.get("event_type", "?")
                        success = data.get("success", False)
                        message = data.get("message", "")[:120]
                        match = "OK" if event == expected_event else ("CLOSE" if event.split(".")[0] == expected_event.split(".")[0] else "MISS")
                        results.append(match)
                        symbol = {"OK": "+", "CLOSE": "~", "MISS": "X"}[match]
                        print(f"  [{symbol}] {event:30s} (expected {expected_event:20s}) {message}")
                        break
            except asyncio.TimeoutError:
                print(f"  [T] timeout")
                results.append("TIMEOUT")

            time.sleep(2)  # Rate limit for Groq

    ok = results.count("OK") + results.count("CLOSE")
    total = len(results)
    print(f"\n{'='*60}")
    print(f"Result: {ok}/{total} correct ({results.count('OK')} exact, {results.count('CLOSE')} close)")
    print(f"Misses: {results.count('MISS')}, Timeouts: {results.count('TIMEOUT')}")


if __name__ == "__main__":
    asyncio.run(run())
