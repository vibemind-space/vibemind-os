---
name: vscode-quick-open
description: Oeffne eine Datei in VS Code via Quick-Open (Strg+P).
app: vscode
agents: ["*"]
trigger: "vscode datei oeffnen|quick open|ctrl p file"
inputs:
  - {name: filename, type: string, description: "Dateiname oder Pfadfragment wie es in Quick-Open erscheint, z.B. 'main.py' oder 'src/utils/helper.ts'"}
expected_state:
  description: "VS Code zeigt die Datei {filename} als aktiven Editor-Tab und der Quick-Open ist geschlossen."
  verification_tool: vision_analyze
secrets: []
confidence: 0.0
attempts: 0
successes: 0
last_adjusted: null
---

# Steps

1. **Fokus pruefen** — VS Code aktiv.
2. **Quick-Open** — `handoff_action(action_type="hotkey", keys="ctrl+p")`.
3. **Sleep 0.3s**.
4. **Datei tippen** — `handoff_action(type="type", text="{filename}")`. VS Code's Fuzzy-Match findet die Datei meistens beim ersten Treffer.
5. **Auswaehlen** — `handoff_action(press, key="enter")`.
6. **Validieren** — `vision_analyze(mode="state_analysis", prompt="Welche Datei ist aktuell in VS Code als aktiver Editor-Tab? Ist Quick-Open geschlossen? JSON {active_file: <string>, quick_open_closed: bool}")`. Erfolg wenn `active_file` den `{filename}` enthaelt.

# Adjustments
- Bei sehr generischen Dateinamen (z.B. 'index.ts') liefert Quick-Open viele Treffer — der erste ist nicht immer der gewuenschte. Dann muss der Nutzer praeziser sein (Pfadfragment).
