---
name: vscode-toggle-terminal
description: Oeffne oder schliesse das Terminal-Panel in VS Code (Strg+`).
app: vscode
agents: ["*"]
trigger: "terminal toggle|vscode terminal|terminal oeffnen"
inputs: []
expected_state:
  description: "Das Terminal-Panel ist sichtbar bzw. ausgeblendet, je nach vorherigem State (Toggle-Verhalten)."
  verification_tool: vision_analyze
secrets: []
confidence: 0.0
attempts: 0
successes: 0
last_adjusted: null
---

# Steps

1. **Fokus pruefen** — VS Code aktiv.
2. **Terminal toggle** — `handoff_action(action_type="hotkey", keys="ctrl+oem_3")`. `oem_3` ist die Backtick/Tilde-Taste auf US-Layout. Auf DE-Layout: `ctrl+shift+oem_5` (= Ctrl+Shift+`).
3. **Sleep 0.3s**.
4. **Validieren** — `vision_analyze(mode="state_analysis", prompt="Ist im VS Code Fenster ein Terminal-Panel im unteren Bereich sichtbar (mit Prompt wie PS> oder $)? JSON {terminal_visible: bool}")`.

# Adjustments
- Falls die Hotkey-Variante nicht greift (Layout-abhaengig), Fallback ueber Command Palette: `vscode-command-palette` mit `command="View: Toggle Terminal"`.
- Wenn Terminal bereits offen war, schliesst dieser Skill es — das ist by-design (Toggle).
