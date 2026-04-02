"""Test WebSocket connection to MoireServer"""
import asyncio
import json

try:
    import websockets
except ImportError:
    print("Installing websockets...")
    import subprocess
    subprocess.run(["pip", "install", "websockets"], check=True)
    import websockets

async def test_ws():
    try:
        print("Connecting to ws://localhost:8765...")
        async with websockets.connect('ws://localhost:8765', open_timeout=5) as ws:
            print('[OK] WebSocket connected!')

            # Send scan_desktop request
            await ws.send(json.dumps({'type': 'scan_desktop'}))
            print("Sent scan_desktop request, waiting for response...")

            response = await asyncio.wait_for(ws.recv(), timeout=15)
            data = json.loads(response)

            print(f"\nResponse type: {data.get('type', 'unknown')}")

            if 'boxes' in data:
                print(f"Detected boxes: {len(data['boxes'])}")

            if 'ocrResults' in data:
                ocr = data['ocrResults']
                print(f"OCR results: {len(ocr)} items")
                if ocr:
                    # Show first few OCR results
                    for i, item in enumerate(ocr[:5]):
                        if isinstance(item, dict):
                            text = item.get('text', '')[:50]
                        else:
                            text = str(item)[:50]
                        print(f"  [{i}] {text}")
                    if len(ocr) > 5:
                        print(f"  ... and {len(ocr) - 5} more")

            return True

    except asyncio.TimeoutError:
        print('[FAIL] Timeout waiting for response')
        return False
    except Exception as e:
        print(f'[FAIL] Error: {type(e).__name__}: {e}')
        return False

if __name__ == "__main__":
    asyncio.run(test_ws())
