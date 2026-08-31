---
name: chrome-search-google
description: Öffne einen neuen Tab in Chrome und suche auf Google nach einem gegebenen Suchbegriff.
app: chrome
agents: ["*"]
trigger: /search google (?P<query>.+)/
inputs:
  - name: query
    type: string
expected_state:
  description: Chrome zeigt Google-Suchergebnisse für den Suchbegriff {query} an.
  verification_tool: vision_analyze
confidence: 0.0
attempts: 0
successes: 0
---

1. Führe `mcp_desktop_automation_handoff_action` mit `action_type="hotkey"` und `keys="ctrl+t"` aus, um einen neuen Tab zu öffnen.
2. Führe `mcp_desktop_automation_handoff_action` mit `action_type="type"` und `text="{query}"` aus, um den Suchbegriff in die Adressleiste einzugeben.
3. Führe `mcp_desktop_automation_handoff_action` mit `action_type="press"` und `key="enter"` aus, um die Suche zu starten.