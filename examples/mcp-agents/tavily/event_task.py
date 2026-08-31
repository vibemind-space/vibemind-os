"""
Tavily UI Server for Event Streaming
"""
import asyncio
import json
import os
import sys
from aiohttp import web

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from constants import (
    MCP_EVENT_SESSION_ANNOUNCE,
    MCP_EVENT_AGENT_MESSAGE,
    MCP_EVENT_AGENT_ERROR,
    MCP_EVENT_TASK_COMPLETE,
    MCP_EVENT_CONVERSATION_HISTORY,
    MCP_EVENT_USER_INPUT_REQUEST,
    MCP_EVENT_USER_INPUT_RESPONSE,
)


async def start_tavily_ui_server(session_id: str, event_port: int):
    """
    Start a minimal UI server for Tavily event streaming
    This mirrors the pattern from other MCP agents
    """
    app = web.Application()

    async def health_check(request):
        return web.json_response({
            "status": "ok",
            "session_id": session_id,
            "event_port": event_port,
            "tool": "tavily"
        })

    async def events_stream(request):
        """SSE endpoint for event streaming"""
        response = web.StreamResponse()
        response.headers['Content-Type'] = 'text/event-stream'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Connection'] = 'keep-alive'
        await response.prepare(request)

        try:
            # Keep connection alive
            while True:
                await asyncio.sleep(30)
                await response.write(b': keep-alive\n\n')
        except asyncio.CancelledError:
            pass

        return response

    app.router.add_get('/health', health_check)
    app.router.add_get('/events', events_stream)

    runner = web.AppRunner(app)
    await runner.setup()

    # Use dynamic port (event_port + 1000 to avoid conflicts)
    ui_port = event_port + 1000
    site = web.TCPSite(runner, '127.0.0.1', ui_port)
    await site.start()

    print(f"Tavily UI server started on http://127.0.0.1:{ui_port}", file=sys.stderr)
