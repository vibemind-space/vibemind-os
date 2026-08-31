---
name: chrome-playwright-fill-form
description: Fuelle ein HTML-Formular auf einer Seite via Playwright-MCP (deterministische Selektoren).
app: chrome
agents: ["*"]
trigger: "form ausfuellen playwright|fill form|web formular"
inputs:
  - {name: url, type: string, description: "Seite mit dem Formular"}
  - {name: fields, type: object, description: "Map von CSS-Selektor oder ARIA-Label -> Wert, z.B. {'#email': 'a@b.de', 'input[name=password]': 'xxx'}"}
  - {name: submit_selector, type: string, description: "Selektor des Absende-Buttons, z.B. 'button[type=submit]'"}
expected_state:
  description: "Nach dem Submit hat sich die Seite veraendert (URL geaendert oder Erfolgsmeldung sichtbar). Keine Validierungsfehler-Boxes."
  verification_tool: mcp_playwright_browser_snapshot
secrets:
  - {credential_id: "{credential_id}", form_schema: [{name: "credential_id", type: text}, {name: "value", type: password}], optional: true}
confidence: 0.0
attempts: 0
successes: 0
last_adjusted: null
---

# Steps

1. **Navigieren** — `mcp_playwright_browser_navigate(url="{url}")`.
2. **Page-Snapshot** — `mcp_playwright_browser_snapshot()`. Damit sehen wir die Element-Struktur (Accessibility-Tree).
3. **Felder ausfuellen** — Fuer jedes (selector, value) in {fields}:
   - Wenn `value` ein vault://-Token ist (Format `vault://<id>`), zuerst aufloesen via Skill-Runner-Helper (intern), bevor an Playwright gegeben.
   - `mcp_playwright_browser_fill_form(fields=[{ref: <selector>, value: <plaintext>}])` — Playwright unterstuetzt Batch-Fill.
4. **Submit** — `mcp_playwright_browser_click(ref="{submit_selector}")`.
5. **Sleep / wait_for** — `mcp_playwright_browser_wait_for(text=<expected_success_text>)` oder Sleep 2s.
6. **Validieren** — `mcp_playwright_browser_snapshot()` oder `mcp_playwright_browser_network_requests()` und pruefen ob ein erwarteter Endpoint mit 200 angesprochen wurde. Coordinator entscheidet basierend auf Snapshot ob Form akzeptiert wurde (kein .error-Tag, kein 'Bitte fuellen Sie...' Text).

# Adjustments
- Fuer Formulare mit CSRF-Token oder Captcha schlaegt diese Skill in der einfachen Form fehl — dann muss der Skill um Captcha-Handling erweitert werden (separater Skill).
- Bei Single-Page-Apps (React-Forms) muss man oft `keypress` fuer den letzten Char senden um React's onChange zu triggern — Playwright handelt das normalerweise korrekt mit `fill_form`.
