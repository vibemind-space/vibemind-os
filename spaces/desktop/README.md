# Desktop Space

Voice-controlled desktop automation with vision-based UI interaction, messaging, and task management.

## Architecture

```
IntentClassifier → desktop.* / messaging.* / web.* events
    ↓
DesktopAgent (BaseBackendAgent)
    ↓
Automation_ui FastAPI Backend (localhost:8007)
    ├── Vision/agentic: /api/llm/intent
    ├── Direct actions: /type_text, /press_key, /scroll
    └── Clawdbot bridge: /clawdbot_send, /clawdbot_status

Fallback: pyautogui for type, press_key, scroll
```

## Agent

| Property | Value |
|----------|-------|
| **Class** | `DesktopAgent` |
| **Stream** | `events:tasks:desktop` |
| **File** | `agents/desktop_agent.py` |

## Event Types (19)

### Desktop Operations (7)

| Event Type | Tool | Description |
|-----------|------|-------------|
| `desktop.open_app` | `open_app` | Launch application |
| `desktop.click` | `click_element` | Click UI element (vision-based) |
| `desktop.type` | `type_text` | Type text |
| `desktop.press_key` | `press_key` | Press keyboard key |
| `desktop.screenshot` | `take_screenshot` | Screen capture + analysis |
| `desktop.scroll` | `scroll_screen` | Scroll (up/down) |
| `desktop.task` | `execute_desktop_task` | Complex task via LLM vision |

### Task Management (3)

| Event Type | Tool | Description |
|-----------|------|-------------|
| `desktop.task.create` | `create_task_node` | Create task widget |
| `desktop.task.update` | `update_task_status` | Update task status |
| `desktop.task.list` | `get_task_list` | Retrieve all tasks |

### Moire Vision (2)

| Event Type | Tool | Description |
|-----------|------|-------------|
| `desktop.moire.scan` | `moire_scan` | Full screen OCR |
| `desktop.moire.find` | `moire_find_element` | Find UI element by description |

### Messaging & Web (7 — Clawdbot Bridge)

| Event Type | Tool | Description |
|-----------|------|-------------|
| `messaging.whatsapp` | `send_whatsapp` | Send WhatsApp message |
| `messaging.telegram` | `send_telegram` | Send Telegram message |
| `messaging.send` | `send_message` | Auto-detect platform |
| `web.search` | `web_search` | Search web via Clawdbot |
| `web.fetch` | `web_fetch` | Fetch and summarize webpage |
| `openclaw.status` | `get_clawdbot_status` | Check Clawdbot connection |
| `openclaw.notifications` | `get_notifications` | Get pending messages |

## Parameter Mapping

| Event Type | Classifier Output → Tool Parameter |
|-----------|-------------------------------------|
| `desktop.open_app` | `name, application, app` → `app_name` |
| `desktop.click` | `description, target, element` → `element_description` |
| `desktop.type` | `content, string, message, input` → `text` |
| `desktop.press_key` | `button, taste` → `key` |
| `desktop.task` | `description, task, action` → `task_description` |
| `messaging.*` | `name, contact` → `recipient`; `text, content` → `message` |
| `web.search` | `text, search, term` → `query` |
| `web.fetch` | `link, address, page` → `url` |

## Directory Structure

```
python/spaces/desktop/
├── agents/
│   ├── __init__.py
│   └── desktop_agent.py              # DesktopAgent (19 event types)
├── adapted/                           # Typed wrappers for Swarm
│   ├── desktop_tools.py              # 12 tools via Automation_ui HTTP
│   ├── messaging_tools.py            # 7 tools via Clawdbot bridge
│   └── adapted_desktop_tools.py      # Re-export
└── tools/                             # Original Dict-based tools
    ├── desktop_tools.py              # Async MoireTracker implementations
    ├── moire_tools.py                # MoireServer WebSocket client + OCR
    ├── task_tools.py                 # Task management with Canvas sync
    └── quickaction_tools.py          # App launching + 30+ shortcuts
```

## Key Patterns

### Dual Tool Structure
- **`adapted/`**: Typed wrappers routing through Automation_ui FastAPI backend (HTTP)
- **`tools/`**: Original async Dict-based implementations (MoireTracker integration)

### Three Execution Layers
1. **Automation_ui Backend** (primary) — Vision/LLM-based automation via HTTP
2. **pyautogui fallback** — Direct input when backend unavailable
3. **MoireServer** — WebSocket OCR (ws://localhost:8766)

### Task Tracking
Tasks appear as visual nodes in Electron 3D UI via `_broadcast_to_electron()`:
- `node_added`, `node_updated`, `node_removed`
- Status: PENDING → RUNNING → COMPLETED/FAILED
- Real-time progress monitoring (0.0–1.0)

### App Shortcuts
`quickaction_tools.py` contains 30+ Windows app mappings (chrome, word, vscode, etc.) for instant launch.
