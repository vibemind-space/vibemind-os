---
name: notepad-write-text
description: Automates writing a specified text into Notepad.
app: notepad
agents: ['*']
trigger: /write text in notepad/i
inputs:
  - name: text
    type: string
expected_state:
  description: The text '{text}' is visible in the Notepad editor.
  verification_tool: vision_analyze
confidence: 1.0
attempts: 1
successes: 1
last_adjusted: 2026-05-04T10:39:00+02:00
---

## Schritte

1. Öffne oder fokussiere Notepad via `mcp_desktop_automation_app_launch_or_focus` mit `app='notepad'`.
2. Verifiziere, dass Notepad im Vordergrund ist mit `handoff_get_focus`.
3. Schreibe den Text per `handoff_action(action_type='type', text='Hallo Welt vom Skill-Coordinator')`.
4. Validiere den sichtbaren Text via `vision_analyze(mode='state_analysis', prompt='Welcher Text ist aktuell im Notepad-Editor sichtbar? JSON {visible_text: <string>}')`.
5. Erfolg, wenn der Text 'Hallo Welt vom Skill-Coordinator' sichtbar ist.