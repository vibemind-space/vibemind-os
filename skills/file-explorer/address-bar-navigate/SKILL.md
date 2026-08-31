---
name: file-explorer-address-bar-navigate
description: Navigiere im File-Explorer ueber die Adressleiste zu einem absoluten Pfad.
app: file-explorer
agents: ["*"]
trigger: "explorer navigate|gehe zu pfad|cd in explorer"
inputs:
  - {name: path, type: string, description: "Absoluter Pfad, z.B. 'C:\\\\Users\\\\User\\\\Desktop'"}
expected_state:
  description: "Der File-Explorer zeigt den Inhalt von {path} und der Adressleisten-Text entspricht dem Pfad."
  verification_tool: vision_analyze
secrets: []
confidence: 0.0
attempts: 0
successes: 0
last_adjusted: null
---

# Steps

1. **Fokus pruefen** — Explorer aktiv (`handoff_get_focus`).
2. **Adressleiste fokussieren** — `handoff_action(action_type="hotkey", keys="ctrl+l")`. Selektiert den Adressleisten-Inhalt.
3. **Pfad eingeben** — `handoff_action(type="type", text="{path}")`. Ueberschreibt den vorherigen Pfad.
4. **Navigieren** — `handoff_action(press, key="enter")`.
5. **Sleep 0.5s** fuer den Render.
6. **Validieren** — `vision_analyze(mode="state_analysis", prompt="Welcher Pfad steht in der Adressleiste des aktuellen File-Explorers? JSON {address_bar: <string>}")`. Erfolg wenn `address_bar` mit `{path}` uebereinstimmt (Trailing-Slash ignorieren).

# Adjustments
- Wenn Pfad nicht existiert, zeigt Explorer eine Fehler-Snackbar 'Windows kann nicht auf...' — als Failure werten.
- Bei Pfaden mit Forward-Slashes (z.B. 'C:/...') konvertiert Explorer transparent — kein Problem.
