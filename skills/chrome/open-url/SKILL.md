---
name: chrome-open-url
description: Oeffne eine URL in einem neuen Chrome-Tab (Strg+T + URL + Enter).
app: chrome
agents: ["*"]
trigger: "chrome url|oeffne url|new tab url"
inputs:
  - {name: url, type: string, description: "Vollstaendige URL inkl. https:// (oder Such-Query)"}
expected_state:
  description: "Chrome zeigt einen neuen Tab mit der angeforderten URL geladen, der Window-Title enthaelt den Page-Title."
  verification_tool: vision_analyze
secrets: []
confidence: 0.0
attempts: 0
successes: 0
last_adjusted: null
---

# Steps

1. **Fokus pruefen** — Chrome muss aktiv sein. `handoff_get_focus`, Window-Title enthaelt 'Chrome'.
2. **Neuer Tab** — `handoff_action(action_type="hotkey", keys="ctrl+t")`. Oeffnet leeren Tab, Cursor in Adressleiste.
3. **Sleep 0.3s**.
4. **URL eingeben** — `handoff_action(type="type", text="{url}")`.
5. **Bestaetigen** — `handoff_action(press, key="enter")`.
6. **Sleep 2s** fuer Page-Load.
7. **Validieren** — `vision_analyze(mode="state_analysis", prompt="Welcher Page-Title und URL sind im aktuellen Chrome-Tab sichtbar? JSON {url: <string>, title: <string>}")`. Erfolg wenn der Domain-Teil von `{url}` im sichtbaren URL/Title vorkommt.

# Adjustments
- Falls Chrome nicht im Vordergrund: kein Fallback, abbrechen mit Hinweis. (Optional kann ein anderer Skill Chrome erst aktivieren via Alt+Tab oder Win+Number.)
- Wenn `{url}` keine Schema-Praefix hat (kein 'http://', 'https://'), interpretiert Chrome es als Such-Query in der Default-Suchmaschine. By design.
