---
name: chrome-playwright-extract-text
description: Extrahiere strukturierten Text/Daten von einer Webseite via Playwright-MCP read_page.
app: chrome
agents: ["*"]
trigger: "scrape page|extract text|web seite lesen"
inputs:
  - {name: url, type: string, description: "URL der Seite"}
  - {name: selector, type: string, description: "Optionaler CSS-Selector um nur einen Bereich zu extrahieren (leer = ganze Seite)"}
expected_state:
  description: "Es wurde ein Text-Snippet zurueckgegeben das sinnvolle Inhalte enthaelt (>50 Zeichen, kein Captcha-/Login-Wall)."
  verification_tool: mcp_playwright_browser_snapshot
secrets: []
confidence: 0.0
attempts: 0
successes: 0
last_adjusted: null
---

# Steps

1. **Navigieren** — `mcp_playwright_browser_navigate(url="{url}")`.
2. **Wait for content** — `mcp_playwright_browser_wait_for(time=2)` (DOM-Settle) oder konkreter Selektor wenn bekannt.
3. **Snapshot** — `mcp_playwright_browser_snapshot()` liefert den Accessibility-Tree mit Texten.
4. **Wenn `{selector}` gesetzt** — alternativ ueber `mcp_playwright_browser_evaluate(function="() => document.querySelector('{selector}')?.innerText")` gezielt extrahieren.
5. **Returnen** — Text als String, plus Hinweise auf Bilder/Links/Buttons aus dem Snapshot.

# Adjustments
- JS-rendered Seiten (z.B. SPAs) brauchen oft 3-5s Settle bis der Content da ist; bei leerem Result wait erhoehen.
- Bei Cookie-/Consent-Walls die Seite per `mcp_playwright_browser_click(text="Akzeptieren")` durchklicken bevor Snapshot.
- Bei Login-Wall (User nicht eingeloggt) erkennen und zurueckmelden — kein blinder Login-Versuch, das gehoert in chrome-playwright-fill-form.
