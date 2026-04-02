"""Test BrowserConsoleAgent Console Error Capture."""
import asyncio
from src.agents.browser_console_agent import BrowserConsoleAgent

async def test():
    print("=== BrowserConsoleAgent Test ===")
    agent = BrowserConsoleAgent()
    print("Agent erstellt, starte Capture...")
    
    try:
        capture = await asyncio.wait_for(
            agent.capture_console_errors("http://localhost:3001", wait_seconds=3.0),
            timeout=60.0
        )
        
        print(f"\nURL: {capture.url}")
        print(f"Errors: {capture.total_errors}")
        print(f"Warnings: {capture.total_warnings}")
        
        if capture.errors:
            print("\n--- Gefundene Errors ---")
            for e in capture.errors[:3]:
                msg = e.message[:80] + "..." if len(e.message) > 80 else e.message
                print(f"  {e.level.upper()}: {msg}")
        
        print("\n--- Claude Context ---")
        context = capture.format_for_claude()
        print(context[:500] if len(context) > 500 else context)
        
    except asyncio.TimeoutError:
        print("Timeout bei Capture!")
    except Exception as e:
        print(f"Fehler: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())