---
name: claude-desktop-send-message
description: Tippe eine Nachricht ins Claude-Desktop-Eingabefeld und schicke sie ab.
app: claude-desktop
agents: ["*"]
trigger: "send to claude|claude desktop send|nachricht an claude"
inputs:
  - {name: message, type: string, description: "Nachrichtentext (kann mehrzeilig sein, Newlines werden als Shift+Enter interpretiert)"}
expected_state:
  description: "Die getippte Nachricht erscheint als User-Bubble im Chat und Claude beginnt zu antworten (Streaming-Indikator oder erste Antworttokens sichtbar)."
  verification_tool: vision_analyze
secrets: []
confidence: 0.0
attempts: 0
successes: 0
last_adjusted: null
---

# Steps

1. **Fokus pruefen** — Window-Title enthaelt 'Claude'.
2. **Eingabefeld fokussieren** — Claude Desktop's Eingabefeld ist standardmaessig fokussiert. Zur Sicherheit `handoff_action(action_type="hotkey", keys="ctrl+l")` (Some apps support 'focus chat input' shortcut). Wenn das nicht greift, weiter zu Step 3.
3. **Nachricht tippen** — `handoff_action(type="type", text="{message}")`.
4. **Senden** — `handoff_action(press, key="enter")`. (Multi-line waere Shift+Enter, aber wir senden 1-Zeiler.)
5. **Sleep 1.5s** fuer Roundtrip-Initial.
6. **Validieren** — `vision_analyze(mode="state_analysis", prompt="Ist die letzte User-Nachricht im Claude-Chat-Verlauf '{message}'? Antwortet Claude bereits oder denkt er noch? JSON {user_message_visible: bool, claude_responding: bool}")`. Erfolg wenn `user_message_visible=true`.

# Adjustments
- Multiline messages: Newlines im `{message}` werden von `handoff_action(type='type')` als echte Newlines getippt — das wuerde in Claude direkt senden. Workaround: Newlines durch `handoff_action(action_type='hotkey', keys='shift+enter')` ersetzen, aber das erfordert mehrere Tool-Calls. Fuer 1-Zeiler kein Problem.
