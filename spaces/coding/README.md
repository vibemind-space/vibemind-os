# 🧑‍💻 coding.space — Antoni's Coding Engine

> **VibeMind Space:** coding.space  
> **Voice Agent:** Antoni (Coding Worker)  
> **Engine-Projekt:** `C:\Users\User\Desktop\Coding_engine\dashboard-app`  
> **Rolle im VibeMind Multiverse:** Autonome Code-Generierung via Sprache

---

## Was ist coding.space?

coding.space ist der **Code-Generierungs-Space** innerhalb der VibeMind-Plattform. Gesteuert über den Voice Agent **Antoni**, werden vollständige Full-Stack-Applikationen allein durch Sprachbefehle erzeugt.

> *"Build me a todo app with React"* → Antoni → Coding Engine → Fertiges Projekt

---

## Architektur

### Voice → Code Pipeline

```
User Voice ──► OpenAI Realtime ──► Antoni (Coding Agent)
                                       │
                                       ▼
                              ClientToolsManager
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
             generate_code()   get_generation_status()  start_preview()
                    │
                    ▼
           ┌───────────────────────────────────────────┐
           │         SOCIETY OF MIND ENGINE            │
           │         (Coding_engine/)                  │
           │                                           │
           │  Orchestrator ──► EventBus (Pub/Sub)      │
           │       │                                   │
           │       ├── Generator Agent                 │
           │       ├── Architect Agent                 │
           │       ├── Database Agent                  │
           │       ├── API Agent                       │
           │       ├── Auth Agent                     │
           │       ├── Builder Agent                  │
           │       ├── Tester Agent                   │
           │       ├── Fixer Agent                    │
           │       ├── Security Agent                 │
           │       ├── UX Design Agent                │
           │       └── ... (40+ Agents)                │
           └───────────────────────────────────────────┘
                    │
                    ▼
           Docker Sandbox + VNC Live Preview
```

### Agent Transfer

```
Rachel (Ideas) ──► Alice (Hub) ──► Antoni (Coding)
```

---

## Voice Tools

| Tool | Beschreibung | Sprachbefehl |
|------|-------------|-------------|
| `generate_code()` | Startet Society of Mind Pipeline | *"Build me a todo app with React"* |
| `get_generation_status()` | Status abfragen | *"How's the build going?"* |
| `start_preview()` | VNC Stream starten | *"Show me the preview"* |
| `stop_preview()` | Preview beenden | *"Stop the preview"* |
| `list_generated_projects()` | Alle Projekte auflisten | *"What projects did we build?"* |

Die Tools sind definiert in `../../tools/coding_tools.py` und werden über den `CodingEngineRunner` (`../../coding_engine_runner.py`) an die externe Engine delegiert.

---

## Hybrid Pipeline (5 Phasen)

| Phase | Beschreibung |
|-------|-------------|
| **1. Architecture Analysis** | ArchitectAgent erstellt typisierte Contracts |
| **2. Parallel Code Generation** | 5+ Executors generieren gleichzeitig Code |
| **3. Merge & Integration** | CodeMerger kombiniert Slices, löst Konflikte |
| **4. Verification Loop** | Build → Test → Validate → Fix → Repeat bis Konvergenz |
| **5. Deployment Verification** | Docker Sandbox Testing + VNC Streaming |

### Konvergenz-Modi

| Modus | Test-Rate | Max Fehler | Timeout | Use Case |
|-------|-----------|-----------|---------|----------|
| `--autonomous` | 100% | 0 | 1h | Produktion |
| `--strict` | 100% | 0 | 10min | Qualität |
| `--relaxed` | 80% | 5 | 10min | MVP |
| `--fast` | 70% | 10 | 5min | Prototyping |

---

## Tech Stack

| Komponente | Technologie |
|-----------|------------|
| **Backend** | Python 3.11+, FastAPI, AutoGen Framework |
| **Dashboard** | Electron + React + Vite + Tailwind CSS |
| **LLM** | Anthropic Claude (via API) |
| **Agents** | 40+ spezialisierte AutoGen Agents |
| **Container** | Docker Sandbox mit VNC Streaming |
| **Testing** | Playwright E2E, pytest |
| **Skills** | 3-Tier Token Management (~200/~800/~1600 Tokens) |
| **Memory** | Fungus Memory (RAG via Qdrant) |

---

## Schlüssel-Features

### 🔄 Review Gate
Generation pausieren → App im VNC testen → Chat-Feedback → Vision AI analysiert Screenshot → Generation fortsetzen.

### 🧠 Fungus Memory
RAG-basierte semantische Suche über Qdrant (`la_fungus_search/`) für langfristiges Projekt-Wissen.

### 🐳 Docker Sandbox
Jedes generierte Projekt läuft isoliert in einem Docker Container mit VNC Streaming.

### 🏗️ Cell Colony
Kubernetes-basiertes Deployment für verteilte Agent-Ausführung.

---

## Lokale Struktur (Space Bridge)

```
spaces/coding/
├── README.md           # ← Du bist hier
├── tools/
│   └── __init__.py     # Tool-Registrierung
└── __init__.py

Verlinkte Dateien:
├── ../../tools/coding_tools.py         # Tool Definitionen
├── ../../coding_engine_runner.py       # Bridge zur externen Engine
```

## Externes Engine-Projekt

```
C:\Users\User\Desktop\Coding_engine\
├── src/
│   ├── mind/           # Society of Mind (EventBus, Orchestrator)
│   ├── engine/         # Hybrid Pipeline (Slicer, Merger, Contracts)
│   ├── agents/         # 40+ Autonome Agents
│   ├── api/            # FastAPI REST/WebSocket Server
│   ├── colony/         # Kubernetes Cell Colony
│   ├── security/       # LLM & Runtime Security
│   ├── tools/          # Claude CLI, Test Runner, Vision
│   └── validators/     # TypeScript, Build Validation
├── dashboard-app/      # Electron Dashboard (Antoni UI)
├── la_fungus_search/   # Fungus Memory (Qdrant RAG)
├── .claude/skills/     # 25+ Skills für Token-Effizienz
└── docs/               # Architektur-Dokumentation
```

> Vollständige Dokumentation: siehe `Coding_engine/README.md`

---

*Teil des VibeMind Multiverse — Conversational Control Plane*
