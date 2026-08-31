---
name: file-explorer-rename
description: Benenne die aktuell ausgewaehlte Datei/Ordner um (F2).
app: file-explorer
agents: ["*"]
trigger: "rename|umbenennen|datei umbenennen"
inputs:
  - {name: new_name, type: string, description: "Neuer Datei-/Ordnername inkl. Endung"}
expected_state:
  description: "Die zuvor ausgewaehlte Datei/Ordner heisst jetzt {new_name}."
  verification_tool: vision_analyze
secrets: []
confidence: 0.0
attempts: 0
successes: 0
last_adjusted: null
---

# Steps

1. **Vorbedingung** — Eine Datei/Ordner muss im Explorer ausgewaehlt sein. Der Aufrufer hat das vorher mit Klick oder Pfeiltasten zu sicherstellen.
2. **Fokus pruefen** — Explorer aktiv (`handoff_get_focus`).
3. **Rename-Mode** — `handoff_action(action_type="press", key="f2")`. F2 = Rename.
4. **Sleep 0.3s**.
5. **Alten Namen loeschen** — `handoff_action(action_type="hotkey", keys="ctrl+a")` + `handoff_action(press, key="delete")`. Sicherer als nur Tippen weil F2 oft nur den Stamm selektiert (ohne Endung).
6. **Neuen Namen tippen** — `handoff_action(type="type", text="{new_name}")`.
7. **Bestaetigen** — `handoff_action(press, key="enter")`.
8. **Falls Endungs-Warnung** — `vision_analyze(mode="state_analysis", prompt="Erscheint ein Dialog 'Wenn Sie die Erweiterung aendern...'? JSON {extension_warning: bool}")`. Wenn ja: `handoff_action(press, key="enter")` (Ja).
9. **Validieren** — `vision_analyze(mode="state_analysis", prompt="Gibt es im Explorer eine Datei/Ordner mit Name {new_name}? JSON {exists: bool}")`.
