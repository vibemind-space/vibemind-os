"""Phase 11.U.C — Ideas-connections end-to-end via Brain routing.

Verifies the chain:
  intent -> capability_router -> direct:connect_ideas
  -> idea.connect event published -> SSE event reaches subscribers

Listens on /api/events/stream (SSE), fires the connect plan, expects
a `idea.connect` event to arrive within timeout.

Usage:
  python scripts/test_idea_connect_e2e.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Optional

import httpx


URL = "http://127.0.0.1:5000"


async def listen_for_event(
    client: httpx.AsyncClient,
    expected_event_id: str,
    timeout_s: float = 30.0,
) -> Optional[dict]:
    """Subscribe to SSE stream, return first event with matching event_id."""
    deadline = time.time() + timeout_s
    try:
        async with client.stream("GET", f"{URL}/api/events/stream",
                                 timeout=httpx.Timeout(timeout_s)) as resp:
            if resp.status_code != 200:
                return None
            buffer = ""
            current_event = ""
            current_data = ""
            async for chunk in resp.aiter_text():
                if time.time() > deadline:
                    return None
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.rstrip("\r")
                    if not line:
                        if current_event == "space_event" and current_data:
                            try:
                                ev = json.loads(current_data)
                                if ev.get("event_id") == expected_event_id:
                                    return ev
                            except Exception:
                                pass
                        current_event = ""
                        current_data = ""
                        continue
                    if line.startswith("event: "):
                        current_event = line[7:].strip()
                    elif line.startswith("data: "):
                        current_data += ("\n" if current_data else "") + line[6:]
    except Exception as e:
        print(f"[U.C] sse stream error: {e}")
        return None
    return None


async def main() -> int:
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Health
        try:
            h = await client.get(f"{URL}/api/health", timeout=5.0)
            if h.status_code != 200:
                print("[U.C] FAIL: brain not healthy")
                return 1
        except Exception as e:
            print(f"[U.C] FAIL: brain unreachable: {e}")
            return 1

        # Pre-step: confirm there are at least 2 ideas in the current bubble
        # (we don't create them — assume the user has some test bubbles).
        # If routing fails because no ideas exist, we'll see it in the
        # capability response.

        print("[U.C] firing connect_ideas via /api/multihop/execute")
        # Subscribe to SSE first (in background), then fire the plan.
        event_task = asyncio.create_task(
            listen_for_event(client, "idea.connect", timeout_s=45.0)
        )
        # Tiny delay so subscription is registered before publish
        await asyncio.sleep(0.3)

        try:
            r = await client.post(
                f"{URL}/api/multihop/execute",
                # Use names known to exist in the user's DB (seen in
                # earlier error: "Test Node, Alpha, Alpha, Beta")
                json={"intent": "connect idea Alpha with idea Beta"},
                timeout=60.0,
            )
            body = r.json() if r.status_code == 200 else {}
            print(f"[U.C] plan execute: status={r.status_code} ok={body.get('ok')}")
            executed = (body.get("executed") or {})
            for sid, hr in executed.items():
                print(f"[U.C]   hop {sid}: ok={hr.get('ok')} cap={hr.get('capability')} "
                      f"target={hr.get('target')}")
                if hr.get("error"):
                    print(f"[U.C]   error: {hr.get('error')}")
        except Exception as e:
            print(f"[U.C] FAIL plan crash: {type(e).__name__}: {e}")
            event_task.cancel()
            return 1

        # Wait for SSE event
        ev = await event_task
        if ev is None:
            print("[U.C] WARN: no idea.connect event received within timeout")
            print("       Either: ideas didn't exist, or event-bus not wired.")
            print("       Plan execution itself was OK — check the 'hop' line above.")
            return 1

        print(f"[U.C] received idea.connect event:")
        print(f"      params: {json.dumps(ev.get('params'), default=str)[:200]}")
        print(f"      ok: {ev.get('ok')}")
        print(f"      source: {ev.get('source')}")
        print(f"\n[U.C] PASS")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
