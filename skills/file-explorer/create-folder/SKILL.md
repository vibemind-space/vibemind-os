---
name: file-explorer-create-folder
description: Erstelle einen neuen Ordner im aktuellen File-Explorer-Fenster.
app: file-explorer
agents: ["*"]
trigger: "neuer ordner|create folder|ordner anlegen"
inputs:
  - {name: folder_name, type: string, description: "Name des neuen Ordners"}
expected_state:
  description: "Im aktuellen Verzeichnis existiert ein neuer Ordner namens {folder_name} und er ist im Explorer sichtbar."
  verification_tool: vision_analyze
secrets: []
confidence: 0.0
attempts: 0
successes: 0
last_adjusted: null
---

# Steps

1. **Fokus pruefen** — `handoff_get_focus`. Window-Title sollte einen Pfad oder „Datei-Explorer" enthalten.
2. **Neuer Ordner** — `handoff_action(action_type="hotkey", keys="ctrl+shift+n")`. Standard-Hotkey in Win 10/11 fuer "Neuer Ordner".
3. **Sleep 0.5s** damit Explorer den Rename-Mode aktiviert.
4. **Namen tippen** — `handoff_action(type="type", text="{folder_name}")`. Der neue Ordner ist im Rename-Modus, der getippte Text ueberschreibt 'Neuer Ordner'.
5. **Bestaetigen** — `handoff_action(press, key="enter")`.
6. **Validieren** — `vision_analyze(mode="state_analysis", prompt="Existiert ein Ordner mit Name '{folder_name}' im aktuell sichtbaren File-Explorer? JSON {folder_exists: bool}")`.

# Adjustments
- Wenn der Hotkey nicht greift (z.B. wenn Fokus auf der Adressleiste liegt): zuerst `handoff_action(action_type="hotkey", keys="f5")` (Refresh + Fokus auf Datei-Liste), dann erneut Ctrl+Shift+N.
