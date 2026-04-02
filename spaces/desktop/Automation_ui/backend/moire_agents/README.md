# MoireTracker AutoGen Desktop Agent System V2

Event-driven Desktop-Automation mit LLM-basierter Planung und Validierung.

## Features

- **Event Queue System**: Kontinuierliche Task-Verarbeitung mit asyncio
- **Reasoning Agent**: Claude Sonnet 4 für Task-Analyse und Action Planning
- **Action Validation**: Timeout-basierte Bildschirmvalidierung
- **MoireServer Integration**: WebSocket-Verbindung für Screen-State

## Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                     Event Queue System                       │
│  ┌──────────┐   ┌──────────────┐   ┌───────────────────┐   │
│  │Task Queue│──▶│Reasoning Agent│──▶│Action Queue       │   │
│  └──────────┘   │(Claude 4)    │   └─────────┬─────────┘   │
│                 └──────────────┘             │              │
│                                              ▼              │
│  ┌──────────────┐              ┌──────────────────────┐    │
│  │Result Queue  │◀─────────────│Interaction Agent     │    │
│  └──────┬───────┘              │(PyAutoGUI)           │    │
│         │                      └──────────────────────┘    │
│         ▼                                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Action Validator (Timeout + State Compare) │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    MoireServer (TypeScript)                  │
│  Detection Pipeline │ OCR Service │ CNN Classifier          │
└─────────────────────────────────────────────────────────────┘
```

## Installation

```bash
cd autogen_desktop
pip install -r requirements.txt
```

## Verwendung

### Task ausführen

```bash
# Einzelner Task
python main_v2.py --task "Starte League of Legends"

# Interaktiver Modus
python main_v2.py
```

### Programmatisch

```python
import asyncio
from agents.orchestrator_v2 import get_orchestrator_v2

async def main():
    orchestrator = get_orchestrator_v2()
    
    # Task ausführen
    result = await orchestrator.execute_task("Starte Chrome")
    
    if result.status == "completed":
        print(f"✓ Task erfolgreich ({len(result.actions)} Aktionen)")
    else:
        print(f"✗ Task fehlgeschlagen: {result.error}")

asyncio.run(main())
```

## Konfiguration

Erstelle `.env` Datei:

```env
# OpenRouter API Key (für LLM-Planung)
OPENROUTER_API_KEY=sk-or-v1-...

# MoireServer Verbindung
MOIRE_HOST=localhost
MOIRE_PORT=8765
```

## Module

### Core
- `core/event_queue.py` - Event Queue System mit Task/Action/Result Queues
- `core/openrouter_client.py` - OpenRouter API Client für Claude/GPT

### Agents
- `agents/orchestrator_v2.py` - Event-driven Orchestrator
- `agents/reasoning.py` - Reasoning Agent mit Pattern-Matching und LLM
- `agents/interaction.py` - PyAutoGUI Desktop-Automation

### Validation
- `validation/action_validator.py` - Action Validation mit Timeout
- `validation/state_comparator.py` - Bildschirmvergleich

### Bridge
- `bridge/websocket_client.py` - MoireServer WebSocket Client

## Unterstützte Aktionen

| Action | Beschreibung | Parameter |
|--------|--------------|-----------|
| `press_key` | Taste drücken | `key`: win, enter, tab, escape... |
| `type` | Text eingeben | `text`: Der Text |
| `click` | Mausklick | `x`, `y` oder `target` |
| `wait` | Warten | `duration`: Sekunden |
| `scroll` | Scrollen | `direction`, `amount` |

## Beispiel-Tasks

```bash
# App starten
python main_v2.py --task "Starte Chrome"
python main_v2.py --task "Starte Discord"
python main_v2.py --task "Öffne Notepad"

# Fenster-Aktionen
python main_v2.py --task "Schließe das aktuelle Fenster"
python main_v2.py --task "Wechsle zum nächsten Fenster"
```

## Modelle

| Verwendung | Modell | API |
|------------|--------|-----|
| Reasoning/Planning | anthropic/claude-sonnet-4 | OpenRouter |
| Vision Analysis | openai/gpt-4o | OpenRouter |
| Quick Actions | Pattern Matching | Lokal |

## Troubleshooting

### MoireServer nicht erreichbar
```
✗ MoireServer connection failed
```
Starte MoireServer: `cd MoireTracker_v2 && npm run dev`

### Keine API Keys
```
No OPENROUTER_API_KEY found
```
Erstelle `.env` mit deinem OpenRouter API Key.

## Lizenz

MIT