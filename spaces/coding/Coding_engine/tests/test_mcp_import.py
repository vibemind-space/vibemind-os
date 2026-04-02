"""Test script for MCP integration imports."""

print("=" * 50)
print("MCP Integration Test")
print("=" * 50)

# Test 1: BrowserConsoleAgent
print("\n[1/4] Testing BrowserConsoleAgent...")
try:
    from src.agents.browser_console_agent import BrowserConsoleAgent, ConsoleCapture
    print("  ✓ BrowserConsoleAgent importiert")
    print(f"    - BrowserConsoleAgent: {BrowserConsoleAgent}")
    print(f"    - ConsoleCapture: {ConsoleCapture}")
except ImportError as e:
    print(f"  ✗ Import fehlgeschlagen: {e}")

# Test 2: mcp_plugins Package
print("\n[2/4] Testing mcp_plugins Package...")
try:
    from mcp_plugins import list_available_servers, get_servers_config
    servers = list_available_servers()
    print(f"  ✓ mcp_plugins funktioniert")
    print(f"    - {len(servers)} Server verfügbar: {servers}")
except ImportError as e:
    print(f"  ✗ Import fehlgeschlagen: {e}")

# Test 3: AutoGen MCP
print("\n[3/4] Testing AutoGen MCP...")
try:
    from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams
    print("  ✓ AutoGen MCP verfügbar")
    print(f"    - McpWorkbench: {McpWorkbench}")
    print(f"    - StdioServerParams: {StdioServerParams}")
except ImportError as e:
    print(f"  ✗ AutoGen MCP NICHT verfügbar: {e}")
    print("    Installation: pip install 'autogen-ext[mcp]'")

# Test 4: Preview Agent
print("\n[4/4] Testing Preview Agent Integration...")
try:
    from src.agents.preview_agent import PreviewAgent, create_preview_agent
    print("  ✓ PreviewAgent importiert")
    
    # Check if BrowserConsoleAgent integration is present
    import inspect
    source = inspect.getsource(PreviewAgent._handle_health_failure)
    if "capture_console_errors" in source or "_capture_console_errors" in source:
        print("  ✓ BrowserConsoleAgent Integration vorhanden")
    else:
        print("  ✗ BrowserConsoleAgent Integration fehlt")
except Exception as e:
    print(f"  ✗ Fehler: {e}")

print("\n" + "=" * 50)
print("Test abgeschlossen")
print("=" * 50)