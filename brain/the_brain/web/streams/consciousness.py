"""
Consciousness Stream -- real-time brain state broadcast.

WebSocket at ``/ws/consciousness`` sends a 2 Hz state pulse
containing recent thoughts, oscillator data, and gate states.
"""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/consciousness")
async def consciousness_stream(websocket: WebSocket):
    """2 Hz brain state broadcast."""
    await websocket.accept()
    try:
        while True:
            state = {
                "thoughts": [],
                "gates": {},
                "oscillator": {},
                "timestamp": time.time(),
            }
            # Populate from app.state if available
            app = websocket.app
            cte = getattr(app.state, "continuous_thinking", None)
            if cte is not None:
                try:
                    state["thoughts"] = [
                        {
                            "content": t.content[:100],
                            "category": t.category,
                            "timestamp": t.timestamp,
                        }
                        for t in cte.get_recent_thoughts(5)
                    ]
                except Exception:
                    pass

            osc = getattr(app.state, "oscillator", None)
            if osc is not None:
                try:
                    state["oscillator"] = osc.get_state()
                except Exception:
                    pass

            await websocket.send_json(state)
            await asyncio.sleep(0.5)  # 2 Hz consciousness tick
    except WebSocketDisconnect:
        pass
    except Exception:
        pass  # Connection lost
