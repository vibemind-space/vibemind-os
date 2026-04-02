"""
Test des aktualisierten BrowserConsoleAgent mit nativen Playwright MCP Tools
"""
import asyncio
import sys
sys.path.insert(0, ".")

from src.agents.browser_console_agent import BrowserConsoleAgent


async def test_browser_console_agent():
    """Teste den BrowserConsoleAgent mit Multi-Route Crawling"""
    
    agent = BrowserConsoleAgent(browser="chrome")
    
    base_url = "http://127.0.0.1:3001"
    app_dir = "./output/test-new-3/app"
    
    print("=" * 60)
    print("BROWSER CONSOLE AGENT - NATIVE PLAYWRIGHT MCP")
    print("=" * 60)
    
    # Route Discovery testen
    routes = agent.discover_routes(app_dir)
    print(f"\n📍 Entdeckte Routes: {routes}")
    
    # Multi-Route Crawling
    print(f"\n🕷️ Starte Multi-Route Crawl...")
    multi_capture = await agent.crawl_all_routes(
        base_url=base_url,
        app_dir=app_dir,
        wait_seconds=5.0
    )
    
    print("\n" + "=" * 60)
    print("ERGEBNIS")
    print("=" * 60)
    
    print(f"\n📊 Statistik:")
    print(f"   Routes gecrawlt: {len(multi_capture.routes_crawled)}")
    print(f"   Errors: {multi_capture.total_errors}")
    print(f"   Warnings: {multi_capture.total_warnings}")
    print(f"   Failed Requests: {multi_capture.total_failed_requests}")
    
    print("\n" + "-" * 60)
    print("FORMATIERT FÜR CLAUDE CLI:")
    print("-" * 60)
    print(multi_capture.format_for_claude())


if __name__ == "__main__":
    asyncio.run(test_browser_console_agent())