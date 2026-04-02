"""
Test des RuntimeTestAgent mit dem test-new-3 Projekt
"""
import asyncio
import sys
sys.path.insert(0, ".")

from src.agents.runtime_test_agent import RuntimeTestAgent, RuntimeResult


async def test_runtime_agent():
    """Teste den RuntimeTestAgent"""
    
    print("=" * 60)
    print("RUNTIME TEST AGENT - TEST")
    print("=" * 60)
    
    # Verwende test-new-3 Projekt
    working_dir = "./output/test-new-3"
    
    agent = RuntimeTestAgent(
        working_dir=working_dir,
        port=3001,  # Port wo der Server bereits läuft
        max_fix_iterations=2,
        server_timeout=120.0,  # Längerer Timeout für Next.js
        browser="chrome",
    )
    
    print(f"\n📁 Working Dir: {working_dir}")
    print(f"🔌 Port: 3001")
    print(f"🔄 Max Fix Iterations: 2")
    print(f"⏱️  Server Timeout: 120s")
    
    print("\n🚀 Starte Runtime Tests...")
    
    result = await agent.run_tests()
    
    print("\n" + "=" * 60)
    print("ERGEBNIS")
    print("=" * 60)
    
    print(f"\n✅ Success: {result.success}")
    print(f"🖥️  Server Started: {result.server_started}")
    print(f"📊 Routes Tested: {result.routes_tested}")
    print(f"❌ Console Errors: {result.console_errors}")
    print(f"⚠️  Console Warnings: {result.console_warnings}")
    print(f"🌐 Failed Requests: {result.failed_requests}")
    print(f"🔧 Fixes Attempted: {result.fixes_attempted}")
    print(f"✅ Fixes Successful: {result.fixes_successful}")
    print(f"⏱️  Execution Time: {result.execution_time_ms}ms")
    
    if result.error_details:
        print(f"\n📋 Error Details:")
        for detail in result.error_details[:5]:
            print(f"   - {detail}")
    
    print("\n" + "=" * 60)
    print("JSON OUTPUT:")
    print("=" * 60)
    import json
    print(json.dumps(result.to_dict(), indent=2))


async def test_browser_capture_only():
    """Teste nur die Browser Capture Funktion mit bestehendem Server"""
    print("=" * 60)
    print("BROWSER CAPTURE ONLY TEST")
    print("=" * 60)
    
    from src.agents.browser_console_agent import BrowserConsoleAgent
    
    agent = BrowserConsoleAgent(browser="chrome")
    base_url = "http://127.0.0.1:3001"
    app_dir = "./output/test-new-3/app"
    
    print(f"\n🌐 Base URL: {base_url}")
    print(f"📁 App Dir: {app_dir}")
    
    print("\n🕷️ Starte Multi-Route Crawl...")
    
    multi_capture = await agent.crawl_all_routes(
        base_url=base_url,
        app_dir=app_dir,
        wait_seconds=5.0,
    )
    
    print(f"\n✅ Routes: {multi_capture.routes_crawled}")
    print(f"❌ Errors: {multi_capture.total_errors}")
    print(f"⚠️  Warnings: {multi_capture.total_warnings}")
    print(f"🌐 Failed Requests: {multi_capture.total_failed_requests}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "capture":
        asyncio.run(test_browser_capture_only())
    else:
        asyncio.run(test_runtime_agent())
