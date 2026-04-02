"""
Test-Script um alle verfügbaren Playwright MCP Tools zu listen
"""
import asyncio
from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams


async def list_playwright_tools():
    """Liste alle verfügbaren Playwright MCP Tools"""
    # --browser chrome verwendet Google Chrome statt Edge
    params = StdioServerParams(
        command="npx",
        args=["--yes", "@playwright/mcp@latest", "--browser", "chrome"]
    )
    
    async with McpWorkbench(server_params=params) as workbench:
        tools = await workbench.list_tools()
        
        print("=" * 60)
        print("PLAYWRIGHT MCP TOOLS (Chrome)")
        print("=" * 60)
        
        for tool in tools:
            # Tools können dict oder Objekte sein
            if isinstance(tool, dict):
                name = tool.get('name', 'unknown')
                desc = tool.get('description', '')[:100]
                schema = tool.get('inputSchema', {})
                props = schema.get('properties', {}) if isinstance(schema, dict) else {}
            else:
                name = getattr(tool, 'name', 'unknown')
                desc = getattr(tool, 'description', '')[:100]
                schema = getattr(tool, 'inputSchema', {})
                props = schema.get('properties', {}) if isinstance(schema, dict) else {}
            
            print(f"\n📦 {name}")
            print(f"   Beschreibung: {desc}...")
            if props:
                print(f"   Parameter: {list(props.keys())}")
        
        print("\n" + "=" * 60)
        print(f"Gesamt: {len(tools)} Tools")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(list_playwright_tools())