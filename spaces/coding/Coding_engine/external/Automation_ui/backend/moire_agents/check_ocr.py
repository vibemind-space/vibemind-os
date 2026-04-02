"""Check what OCR elements are found on screen."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bridge.websocket_client import MoireWebSocketClient

async def test():
    client = MoireWebSocketClient()
    await client.connect()
    result = await client.capture_and_wait_for_complete(timeout=10.0)
    print('Elements with text:')
    if client.current_context:
        for elem in client.current_context.elements:
            if elem.text:
                print(f'  - "{elem.text}"')
    else:
        print("No context available")
    await client.disconnect()

asyncio.run(test())
