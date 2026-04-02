# MCP Integration Guide

## Übersicht

Die Coding Engine verwendet das **Model Context Protocol (MCP)** für erweiterte Browser-Automatisierung und Console-Log Capture. Das System nutzt **native Playwright MCP Tools** für zuverlässige Fehlererfassung.

## Architektur

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Coding Engine                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────┐    ┌──────────────────┐    ┌────────────────┐ │
│  │  Preview Agent  │───▶│ BrowserConsole   │───▶│  Claude CLI    │ │
│  │                 │    │ Agent            │    │                │ │
│  │ • Health Checks │    │ • Native MCP     │    │ • Error Fix    │ │
│  │ • 30s Timer     │    │ • Multi-Route    │    │ • Code Repair  │ │
│  └─────────────────┘    └──────────────────┘    └────────────────┘ │
│           │                      │                                  │
│           ▼                      ▼                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              Native Playwright MCP Tools                     │   │
│  │  • browser_navigate          - URL aufrufen                  │   │
│  │  • browser_console_messages  - Console Logs auslesen         │   │
│  │  • browser_network_requests  - Network Requests auslesen     │   │
│  │  • browser_close             - Browser schließen             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
└──────────────────────────────│──────────────────────────────────────┘
                               ▼
                    ┌──────────────────┐
                    │  Playwright MCP  │
                    │  (npx @playwright │
                    │   /mcp@latest)   │
                    │  --browser chrome │
                    └──────────────────┘
```

## Verfügbare Playwright MCP Tools (22 Tools)

| Tool | Beschreibung | Parameter |
|------|--------------|-----------|
| **browser_navigate** | URL aufrufen | `url` |
| **browser_console_messages** | Alle Console Messages auslesen | - |
| **browser_network_requests** | Alle Network Requests auslesen | - |
| **browser_click** | Element anklicken | `selector` |
| **browser_type** | Text eingeben | `selector`, `text` |
| **browser_evaluate** | JavaScript ausführen | `expression` |
| **browser_screenshot** | Screenshot erstellen | - |
| **browser_snapshot** | Accessibility Snapshot | - |
| **browser_close** | Browser schließen | - |
| **browser_wait_for** | Auf Element warten | `selector`, `timeout` |
| **browser_tabs** | Tab Management | `action` |
| **browser_hover** | Hover über Element | `selector` |
| **browser_press_key** | Tastendruck | `key` |
| **browser_fill_form** | Formular ausfüllen | `fields` |
| ... | (weitere Tools) | |

## BrowserConsoleAgent

Der `BrowserConsoleAgent` verwendet **native Playwright MCP Tools** für zuverlässige Console- und Network-Fehlererfassung.

### Verwendung

```python
from src.agents.browser_console_agent import BrowserConsoleAgent

# Agent erstellen (Chrome als Standard)
agent = BrowserConsoleAgent(browser="chrome")

# Single URL Capture
capture = await agent.capture_console(
    url="http://localhost:3000",
    wait_seconds=5.0
)

print(f"Errors: {len(capture.errors)}")
print(f"Warnings: {len(capture.warnings)}")
print(f"Failed Requests: {len(capture.failed_requests)}")

# Multi-Route Crawling (für Next.js Apps)
multi_capture = await agent.crawl_all_routes(
    base_url="http://localhost:3000",
    app_dir="./app",
    wait_seconds=5.0
)

print(f"Routes: {multi_capture.routes_crawled}")
print(f"Total Errors: {multi_capture.total_errors}")
print(f"Failed Requests: {multi_capture.total_failed_requests}")

# Formatiert für Claude CLI
claude_context = multi_capture.format_for_claude()
```

### Funktionsweise (Native Playwright MCP)

1. **browser_navigate**: Seite aufrufen
2. **Wartezeit**: Async Requests abwarten
3. **browser_console_messages**: Native Console Messages abfragen
4. **browser_network_requests**: Native Network Requests abfragen
5. **browser_close**: Browser schließen

```python
# Interner Ablauf in BrowserConsoleAgent
async with McpWorkbench(server_params=params) as workbench:
    # 1. Navigate
    await workbench.call_tool("browser_navigate", {"url": url})
    
    # 2. Wait for async requests
    await asyncio.sleep(wait_seconds)
    
    # 3. Get Console Messages
    console_result = await workbench.call_tool("browser_console_messages", {})
    # Returns: [INFO], [WARNING], [ERROR], [LOG] messages
    
    # 4. Get Network Requests
    network_result = await workbench.call_tool("browser_network_requests", {})
    # Returns: [GET] url => [200] OK / [404] Not Found
    
    # 5. Close
    await workbench.call_tool("browser_close", {})
```

### Output Format

**browser_console_messages:**
```
[INFO] Download the React DevTools...
[ERROR] Failed to load resource: 404 (Not Found) @ http://localhost:8000/api/users:0
[ERROR] Error fetching users: Error: Failed to fetch users: Not Found
[WARNING] WebSocket connection failed...
```

**browser_network_requests:**
```
[GET] http://localhost:3000/ => [200] OK
[GET] http://localhost:8000/api/users => [404] Not Found
[GET] http://localhost:8000/api/metrics => [404] Not Found
```

## Multi-Route Crawling

Der Agent entdeckt automatisch alle Routes aus einem Next.js `app/` Verzeichnis:

```python
# Route Discovery
routes = agent.discover_routes("./app")
# Returns: ['/', '/dashboard', '/settings', '/users']

# Crawl all routes
multi_capture = await agent.crawl_all_routes(
    base_url="http://localhost:3000",
    app_dir="./app"
)

# Fehler pro Route
for route, capture in multi_capture.captures.items():
    if capture.errors:
        print(f"Route {route}: {len(capture.errors)} errors")
```

### Route Discovery Logik

```python
def discover_routes(self, app_dir: Path) -> list[str]:
    routes = []
    for page_file in app_path.rglob("page.tsx"):
        rel_path = page_file.parent.relative_to(app_path)
        # Filter: (groups), _private, [dynamic]
        route_parts = [
            p for p in rel_path.parts 
            if not p.startswith(("(", "_", "["))
        ]
        route = "/" + "/".join(route_parts)
        routes.append(route)
    return sorted(set(routes))
```

## Preview Agent Integration

Der `PreviewAgent` nutzt den `BrowserConsoleAgent` automatisch bei Health-Check Failures:

```python
async def _handle_health_failure(self):
    # 1. Multi-Route Console Capture
    multi_capture = await self._browser_console_agent.crawl_all_routes(
        base_url=f"http://127.0.0.1:{self.port}",
        app_dir=self.working_dir / "app"
    )
    
    # 2. Format für Claude CLI
    if multi_capture.total_errors > 0:
        console_context = multi_capture.format_for_claude()
    
    # 3. Claude CLI mit Fehler-Kontext
    prompt = f"""
    Server Health Check fehlgeschlagen.
    
    ## Browser Console Errors
    {console_context}
    
    ## Failed Network Requests
    {[r for r in multi_capture.all_failed_requests]}
    
    Bitte behebe diese Fehler:
    - Hydration Errors: Server/Client Mismatch fixen
    - 404 API Calls: Mock-API erstellen oder Endpoints korrigieren
    - WebSocket Errors: Backend WebSocket Server prüfen
    """
    
    await self.claude_cli.execute(prompt)
```

## Datenmodelle

### ConsoleMessage

```python
@dataclass
class ConsoleMessage:
    level: str       # INFO, WARNING, ERROR, LOG
    message: str     # Die Fehlermeldung
    source: str      # Source URL/Datei (optional)
```

### NetworkRequest

```python
@dataclass
class NetworkRequest:
    method: str      # GET, POST, etc.
    url: str         # Request URL
    status: int      # HTTP Status Code
    status_text: str # OK, Not Found, etc.
    
    @property
    def is_error(self) -> bool:
        return self.status >= 400
```

### ConsoleCapture

```python
@dataclass
class ConsoleCapture:
    url: str
    console_messages: list[ConsoleMessage]
    network_requests: list[NetworkRequest]
    navigation_ok: bool
    
    @property
    def errors(self) -> list[ConsoleMessage]:
        return [m for m in self.console_messages if m.level == "ERROR"]
    
    @property
    def warnings(self) -> list[ConsoleMessage]:
        return [m for m in self.console_messages if m.level == "WARNING"]
    
    @property
    def failed_requests(self) -> list[NetworkRequest]:
        return [r for r in self.network_requests if r.is_error]
    
    def format_for_claude(self) -> str: ...
```

### MultiRouteCapture

```python
@dataclass
class MultiRouteCapture:
    base_url: str
    routes_crawled: list[str]
    captures: dict[str, ConsoleCapture]
    
    @property
    def total_errors(self) -> int: ...
    
    @property
    def total_warnings(self) -> int: ...
    
    @property
    def total_failed_requests(self) -> int: ...
    
    def format_for_claude(self) -> str: ...
    
    def to_console_capture(self) -> ConsoleCapture: ...
```

## Beispiel Output

```
# Browser Console Capture
Base URL: http://127.0.0.1:3001
Routes crawled: /, /dashboard
Total Errors: 28
Total Warnings: 1
Failed Requests: 10

## Route: /
## Console Errors (1)
- Failed to load resource: 404 (Not Found)
  Source: http://127.0.0.1:3001/favicon.ico:0

## Route: /dashboard
## Console Errors (27)
- WebSocket error: Event
- Failed to load resource: 404 (Not Found)
  Source: http://localhost:8000/api/processes:0
- Error fetching processes: Error: Failed to fetch processes: Not Found
...

## Console Warnings (1)
- WebSocket connection failed...

## Failed Network Requests (10)
- [GET] http://localhost:8000/api/processes => 404 Not Found
- [GET] http://localhost:8000/api/ports => 404 Not Found
...
```

## Typische Fehler und Fixes

| Error | Ursache | Fix |
|-------|---------|-----|
| **Hydration Mismatch** | Server/Client HTML unterschiedlich | `suppressHydrationWarning` oder `use client` |
| **404 API Calls** | Backend nicht gestartet | Mock-API oder Backend starten |
| **WebSocket 403** | Backend WebSocket fehlt | Backend WebSocket Server implementieren |
| **favicon.ico 404** | Favicon fehlt | `public/favicon.ico` hinzufügen |
| **Module not found** | Fehlende Dependency | `npm install <package>` |

## Konfiguration

```python
# Browser wählen
agent = BrowserConsoleAgent(browser="chrome")  # Default
agent = BrowserConsoleAgent(browser="firefox")
agent = BrowserConsoleAgent(browser="webkit")
agent = BrowserConsoleAgent(browser="msedge")

# Wartezeit konfigurieren
capture = await agent.capture_console(
    url="http://localhost:3000",
    wait_seconds=10.0  # Längere Wartezeit für langsame Apps
)
```

## Requirements

```
autogen-ext[mcp]>=0.4
```

## Troubleshooting

### MCP Server startet nicht

```bash
# Playwright MCP manuell testen
npx --yes @playwright/mcp@latest --browser chrome

# Browser installieren
npx playwright install chrome
```

### ERR_EMPTY_RESPONSE

```python
# 127.0.0.1 statt localhost verwenden
base_url = "http://127.0.0.1:3000"  # ✓
base_url = "http://localhost:3000"   # Kann Probleme machen
```

### AutoGen Import Fehler

```bash
pip install 'autogen-ext[mcp]>=0.4'
```