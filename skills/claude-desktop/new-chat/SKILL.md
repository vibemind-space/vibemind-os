---
name: claude-desktop-new-chat
description: Starte einen neuen Chat in der Claude-Desktop-App.
app: claude-desktop
agents: ["*"]
trigger: "neuer claude chat|new claude chat|start chat"
inputs: []
expected_state:
  description: "Claude Desktop zeigt einen leeren neuen Chat (kein vorheriger Verlauf, Eingabefeld leer und fokussiert)."
  verification_tool: vision_analyze
secrets: []
confidence: 0.0
attempts: 0
successes: 0
last_adjusted: null
---

# Steps

1. **Fokus pruefen** — Window-Title enthaelt 'Claude'.
2. **Neuer Chat** — `handoff_action(action_type="hotkey", keys="ctrl+n")`. Hotkey fuer 'New Chat' in Claude Desktop.
3. **Sleep 0.5s**.
4. **Validieren** — `vision_analyze(mode="state_analysis", prompt="Ist Claude Desktop in einem leeren neuen Chat-Zustand? Eingabefeld leer? JSON {is_empty_chat: bool}")`.

# Adjustments
- Falls Ctrl+N nicht greift (z.B. weil Fokus auf einer Sidebar liegt): erst auf das Hauptfenster klicken via `vision_analyze` element_detection (Hauptbereich identifizieren) + `handoff_action(click, x, y)`.
