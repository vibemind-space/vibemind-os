# 🌌 Ideas.Space — Rachel's Multiverse Navigator

> **VibeMind Space:** Ideas.Space  
> **Voice Agent:** Rachel (Multiverse Navigator)  
> **Projekt:** `C:\Users\User\Desktop\Voice_dialog_vibemind\VibeMind-VoiceDialog`  
> **Rolle im VibeMind Multiverse:** Sprachgesteuerte Ideen- und Bubble-Verwaltung

---

## Was ist Ideas.Space?

Ideas.Space ist der **zentrale Navigations- und Ideen-Space** innerhalb der VibeMind-Plattform. Rachel ist die Stimme von VibeMind — sie spricht mit dem User, versteht seine Absicht und koordiniert alle anderen Agents.

> *"Show my spaces"* → Rachel → list_bubbles()  
> *"Create a space for cooking recipes"* → Rachel → create_bubble()  
> *"Go into cooking"* → Rachel → enter_bubble()

Rachel führt **keine Tools direkt aus** — sie leitet Anfragen an den Orchestrator weiter, der Backend-Agents mit der Ausführung beauftragt. So bleibt sie responsiv und fokussiert auf die Konversation.

---

## Architektur

### Voice → Orchestrator → Backend Agent Pipeline

```
User Voice (16kHz Mic)
       │
       ▼
OpenAI Realtime API (Speech-to-Speech)
       │
       ▼
┌──────────────────────────────────────────────┐
│  RACHEL — Pure Voice Interface               │
│                                              │
│  • Versteht User Intent (DE/EN)              │
│  • Antwortet per TTS                         │
│  • Sendet Events an Orchestrator             │
│  • Führt KEINE Tools direkt aus              │
└──────────────────┬───────────────────────────┘
                   │ InputEvent
                   ▼
┌──────────────────────────────────────────────┐
│  ORCHESTRATOR (Intent Classification)        │
│                                              │
│  • Klassifiziert Intent                      │
│  • Routet zu Backend-Agents                  │
│  • Question Queue für Rückfragen             │
│  • System Context Store                      │
└──────────────────┬───────────────────────────┘
                   │
       ┌───────────┼───────────────┐
       ▼           ▼               ▼
  Ideas Agent  Desktop Agent  Coding Agent
  (Bubbles)    (Adam)         (Antoni)
```

### Agent Transfer System

Rachel kann Gespräche an andere Voice Agents übergeben:

```
Rachel (Ideas) ──transfer──► Alice (Hub/Coordinator)
                                    │
                              ┌─────┴─────┐
                              ▼           ▼
                         Adam          Antoni
                       (Desktop)      (Coding)
```

**Transfer-Ablauf (4 Schritte):**
1. Transfer Handler speichert Switch-Info
2. Watcher Thread erkennt pending Switch
3. Aktuelle Conversation endet
4. Neue Conversation startet mit Ziel-Agent

---

## Bubble & Idea Management

### Was sind Bubbles?

Bubbles sind **Ideen-Container** in Rachels Multiverse — vergleichbar mit Ordnern, aber als 3D-Objekte in einer Three.js-Szene visualisiert. Jede Bubble kann Sub-Ideen enthalten, die untereinander verbunden werden können.

### Bubble Tools

| Tool | Beschreibung | Sprachbefehl-Beispiel |
|------|-------------|----------------------|
| `list_bubbles()` | Alle Spaces anzeigen | *"Show my spaces"* |
| `create_bubble()` | Neuen Space erstellen | *"Create a space for cooking"* |
| `enter_bubble()` | In einen Space wechseln | *"Go into cooking"* |
| `exit_bubble()` | Space verlassen | *"Go back"* |
| `delete_bubble()` | Space löschen | *"Delete the old project"* |
| `find_bubble()` | Space suchen | *"Find my recipes space"* |
| `score_bubble()` | Bubble bewerten | — |
| `promote_bubble()` | Bubble priorisieren | — |
| `generate_bubble_embeddings()` | Semantic Search vorbereiten | — |

### Idea Tools

| Tool | Beschreibung | Sprachbefehl-Beispiel |
|------|-------------|----------------------|
| `create_idea()` | Idee hinzufügen | *"Add a note about authentication"* |
| `list_ideas()` | Ideen auflisten | *"What notes do I have?"* |
| `connect_ideas()` | Ideen verknüpfen | *"Connect authentication to database"* |

### Weitere Tool-Kategorien

| Kategorie | Tools | Funktion |
|-----------|-------|----------|
| **Navigation** | `navigate_to_space()` | Kamera in 3D-UI bewegen |
| **Memory** | `save_to_memory()`, `recall_memory()` | Langzeit-Gedächtnis via SuperMemory |
| **Session** | `session_tools` | Konversations-Kontext verwalten |
| **Exploration** | `exploration_tools` | Bubbles autonom erkunden und bewerten |
| **Summary** | `summary_tools` | Bubble-Inhalte zusammenfassen |

---

## Tech Stack

- **Voice:** OpenAI Realtime API (Speech-to-Speech)
- **Backend:** Python 3.11+ (Electron Backend via stdin/stdout JSON IPC)
- **Frontend:** Electron + Three.js (3D Multiverse UI)
- **Database:** SQLite (`vibemind.db`)
- **Agent Framework:** AutoGen Swarm + Custom Orchestrator
- **Memory:** SuperMemory API + Conversation Memory + Task Memory
- **Search:** Embedding-basierte semantische Suche auf Bubbles
- **Local LLM:** Ollama (für Swarm User Agents)

---

## Projektstruktur

```
VibeMind-VoiceDialog/
├── python/
│   ├── spaces/
│   │   ├── ideas/                  # ⭐ Ideas.Space
│   │   │   ├── agents/
│   │   │   │   ├── rachel_agent.py # Rachel Voice Agent
│   │   │   │   ├── bubbles_agent.py
│   │   │   │   └── ideas_agent.py
│   │   │   ├── tools/
│   │   │   │   ├── bubble_tools.py # Bubble CRUD
│   │   │   │   ├── idea_tools.py   # Idea CRUD
│   │   │   │   ├── exploration_tools.py
│   │   │   │   └── summary_tools.py
│   │   │   └── adapted/           # Legacy-kompatible Wrapper
│   │   ├── desktop/               # Adam's Desktop Space
│   │   ├── coding/                # Antoni's Coding Space
│   │   ├── shuttles/              # Inter-Space Transport
│   │   └── OpenClaw/              # Browser Automation Space
│   ├── swarm/
│   │   ├── orchestrator/          # Intent Classification & Routing
│   │   ├── user_agents/           # Voice Agent Base Classes
│   │   ├── backend_agents/        # Tool-ausführende Agents
│   │   ├── executive/             # Conversation Memory
│   │   ├── workers/               # Claude/Knowledge Workers
│   │   └── tools/                 # Shared Tool Registry
│   ├── tools/
│   │   ├── bubble_tools.py        # Re-exports (backward compat)
│   │   ├── idea_tools.py
│   │   ├── navigation_tools.py
│   │   ├── memory_tools.py
│   │   ├── transfer_handler.py    # Agent Transfer Logic
│   │   └── client_tools_manager.py
│   ├── memory/
│   │   ├── supermemory_client.py   # SuperMemory API
│   │   ├── conversation_memory_service.py
│   │   └── task_memory_service.py
│   ├── data/
│   │   ├── database.py            # SQLite Schema
│   │   ├── models.py              # Data Models
│   │   └── repository.py          # CRUD Operations
│   ├── electron_backend.py         # Electron ↔ Python IPC
│   └── voice/                      # OpenAI Realtime Voice
├── electron-app/
│   ├── main.js                     # Electron Main Process
│   ├── preload.js                  # IPC Bridge
│   └── renderer/
│       ├── index.html              # UI Entry
│       ├── multiverse.js           # Three.js 3D Scene
│       ├── glass_bubbles.js        # Bubble Rendering
│       ├── universe_canvas.js      # Canvas Manager
│       └── exploration_dialog.js   # Exploration UI
├── vibemind.db                      # SQLite Database
└── docs/                            # Weitere Dokumentation
```

---

## Dual-System Architektur

Ideas.Space läuft als Teil des VibeMind Dual-Systems:

| System | Runtime | Aufgabe |
|--------|---------|---------|
| **OpenAI Realtime Voice** | Cloud | Speech-to-Speech mit Function Calling |
| **Swarm/AutoGen User Agents** | Lokal (Ollama) | Backend-Logik, Tool-Ausführung, Memory |

```
Cloud: OpenAI Realtime ──► Voice Session ──► TTS Response
                          │
                     IPC (JSON)
                          │
Lokal: Python Backend ──► Orchestrator ──► Backend Agents ──► Tools
                                                    │
                                              SQLite + SuperMemory
```

---

## Quick Start

```bash
cd Voice_dialog_vibemind/VibeMind-VoiceDialog

# Python Environment
python -m venv .venv312
.venv312\Scripts\activate
pip install -r requirements.txt

# .env konfigurieren
cp .env.example .env
# OPENAI_API_KEY eintragen

# Starten
start_vibemind_production.bat
# oder Debug-Modus:
start_vibemind_debug.bat
```

### Keyboard Shortcuts (Electron)

| Shortcut | Aktion |
|----------|--------|
| `Ctrl+Shift+V` | Voice Toggle |
| `Ctrl+1` | Ideas Space (Rachel) |
| `Ctrl+2` | Desktop Space (Adam) |
| `Ctrl+3` | Coding Space (Antoni) |

---

## Rachel's Persönlichkeit

Rachel spricht Deutsch und Englisch, ist freundlich und präzise. Sie hält Antworten kurz (Voice, nicht Text) und navigiert den User durch das Multiverse. Ihre Kernaufgabe: **Verstehen, Koordinieren, Antworten** — nicht selbst ausführen.

---

*Teil des VibeMind Multiverse — Conversational Control Plane*
