"""
Test der nativen Playwright MCP Tools für Console und Network Capture
"""
import asyncio
from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams


async def test_native_capture():
    """Teste browser_console_messages und browser_network_requests"""
    
    params = StdioServerParams(
        command="npx",
        args=["--yes", "@playwright/mcp@latest", "--browser", "chrome"]
    )
    
    # 127.0.0.1 statt localhost (manchmal zuverlässiger)
    base_url = "http://127.0.0.1:3001"
    routes = ["/", "/dashboard"]
    
    async with McpWorkbench(server_params=params) as workbench:
        print("=" * 60)
        print("NATIVE PLAYWRIGHT CONSOLE/NETWORK CAPTURE")
        print("=" * 60)
        
        for route in routes:
            url = f"{base_url}{route}"
            print(f"\n🌐 Navigiere zu: {url}")
            
            # 1. Seite navigieren
            nav_result = await workbench.call_tool("browser_navigate", {"url": url})
            
            # Navigation-Ergebnis auswerten
            nav_error = False
            if hasattr(nav_result, 'is_error') and nav_result.is_error:
                print(f"   ⚠️  Navigation Fehler!")
                nav_error = True
            else:
                print(f"   ✅ Navigation OK")
            
            # 2. Warten für async Requests (5 Sekunden)
            print("   ⏳ Warte 5 Sekunden für async Requests...")
            await asyncio.sleep(5)
            
            # 3. Console Messages holen
            print("\n📋 Console Messages:")
            console_result = await workbench.call_tool("browser_console_messages", {})
            if hasattr(console_result, 'result') and console_result.result:
                for item in console_result.result:
                    if hasattr(item, 'content'):
                        print(f"   {item.content}")
            
            # 4. Network Requests holen
            print("\n🌍 Network Requests:")
            network_result = await workbench.call_tool("browser_network_requests", {})
            if hasattr(network_result, 'result') and network_result.result:
                for item in network_result.result:
                    if hasattr(item, 'content'):
                        print(f"   {item.content}")
            
            print("\n" + "-" * 40)
        
        # Browser schließen
        await workbench.call_tool("browser_close", {})
        print("\n✅ Browser geschlossen")


if __name__ == "__main__":
    asyncio.run(test_native_capture())