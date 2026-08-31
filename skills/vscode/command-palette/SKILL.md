---
name: vscode-command-palette
description: Oeffne die VS Code Command Palette und fuehre einen Befehl aus.
app: vscode
agents: ["*"]
trigger: "command palette|vscode befehl|run command"
inputs:
  - {name: command, type: string, description: "Befehlsname wie er in der Palette erscheint, z.B. 'Format Document' oder '> Reload Window'"}
expected_state:
  description: "Der angeforderte Befehl wurde ausgefuehrt, die Command Palette ist geschlossen, und sichtbarer UI-Effekt entspricht dem Befehl (z.B. nach 'Format Document' ist der Editor reformattiert)."
  verification_tool: vision_analyze
secrets: []
confidence: 0.0
attempts: 0
successes: 0
last_adjusted: null
---

# Steps

1. **Fokus pruefen** — Window-Title enthaelt 'Visual Studio Code'.
2. **Palette oeffnen** — `handoff_action(action_type="hotkey", keys="ctrl+shift+p")`.
3. **Sleep 0.3s**.
4. **Befehl tippen** — `handoff_action(type="type", text="{command}")`. Ein '>' Praefix wird automatisch von VS Code gesetzt.
5. **Bestaetigen** — `handoff_action(press, key="enter")`. Waehlt den ersten Treffer aus.
6. **Validieren** — `vision_analyze(mode="state_analysis", prompt="Ist die Command Palette geschlossen? Gibt es UI-Aenderungen die '{command}' ausgefuehrt wurde? JSON {palette_closed: bool, observation: <string>}")`.

# Adjustments
- Bei zweideutigen Befehlsnamen (mehrere Treffer) waehlt Enter den falschen — Workaround: spezifischer formulieren oder mit Pfeiltasten zum gewuenschten navigieren.
