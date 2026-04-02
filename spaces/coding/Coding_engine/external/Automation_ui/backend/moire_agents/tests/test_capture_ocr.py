"""Test script for MoireWebSocketClient capture with OCR."""
import asyncio
import sys
import os

# Add python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'MoireTracker_v2', 'python'))

async def test_capture():
    try:
        from bridge.websocket_client import MoireWebSocketClient

        print("Creating MoireWebSocketClient...")
        client = MoireWebSocketClient(host="localhost", port=8765)

        print("Connecting to MoireServer...")
        connected = await asyncio.wait_for(client.connect(), timeout=5.0)

        if not connected:
            print("[FAIL] Could not connect to MoireServer")
            return False

        print("[OK] Connected to MoireServer")
        print("Waiting for capture and OCR (timeout 60s)...")

        # Use capture_and_wait_for_complete
        result = await client.capture_and_wait_for_complete(timeout=60.0)

        print(f"\n=== Capture Result ===")
        print(f"Success: {result.success}")
        print(f"Boxes count: {result.boxes_count}")
        print(f"Texts count: {result.texts_count}")
        print(f"Processing time: {result.processing_time_ms:.0f}ms")
        print(f"Error: {result.error}")

        if result.ui_context:
            print(f"\n=== UI Context ===")
            print(f"Elements: {len(result.ui_context.elements)}")

            # Show elements with text
            texts = [e.text for e in result.ui_context.elements if e.text]
            print(f"Elements with text: {len(texts)}")

            if texts:
                print(f"\nSample texts (first 10):")
                for i, text in enumerate(texts[:10]):
                    print(f"  [{i}] {text[:50]}...")
        else:
            print("[WARN] ui_context is None!")

        print("\nDisconnecting...")
        await client.disconnect()
        print("[OK] Disconnected")

        return result.success and result.texts_count > 0

    except asyncio.TimeoutError:
        print("[FAIL] Timeout")
        return False
    except Exception as e:
        print(f"[FAIL] Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_capture())
    print(f"\n=== Test {'PASSED' if success else 'FAILED'} ===")
