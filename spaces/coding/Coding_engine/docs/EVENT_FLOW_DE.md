# Event-Flow Dokumentation

## Übersicht

Das Society of Mind System verwendet ein Event-basiertes Kommunikationssystem (EventBus), über das alle Agenten miteinander kommunizieren.

---

## Event-Flow Diagramm

```text
START
  │
  ▼
[Phase 0: Scaffold] ─────────────────────────────────────┐
  │                                                       │
  ▼                                                       │
[Phase 1: Architect] ── Contracts generiert              │
  │                                                       │
  ▼                                                       │
[Phase 2: Build] ── Code generiert                       │
  │                                                       │
  ▼                                                       │
╔═══════════════════════════════════════════════════════╗│
║  SOCIETY OF MIND LOOP                                 ║│
║  ┌─────────────────────────────────────────────────┐  ║│
║  │                                                 │  ║│
║  │  BUILD_STARTED ──► npm run build               │  ║│
║  │       │                                         │  ║│
║  │       ▼                                         │  ║│
║  │  ┌─────────┐     ┌──────────────┐              │  ║│
║  │  │ SUCCESS │ ──► │ DeploymentTeam│              │  ║│
║  │  └─────────┘     │ (Sandbox+VNC) │              │  ║│
║  │       │          └──────────────┘              │  ║│
║  │       │                │                        │  ║│
║  │       │                ▼                        │  ║│
║  │       │     SANDBOX_TEST_PASSED/FAILED         │  ║│
║  │       │                │                        │  ║│
║  │  ┌─────────┐          │                        │  ║│
║  │  │ FAILED  │◄─────────┘                        │  ║│
║  │  └─────────┘                                    │  ║│
║  │       │                                         │  ║│
║  │       ▼                                         │  ║│
║  │  GeneratorAgent ── fixt Code                   │  ║│
║  │       │                                         │  ║│
║  │       ▼                                         │  ║│
║  │  CODE_FIXED ──────────────────────────────┐    │  ║│
║  │       │                                    │    │  ║│
║  │       ▼                                    ▼    │  ║│
║  │  ValidationTeam              ContinuousDebug   │  ║│
║  │  (Tests generieren)          (File Sync)       │  ║│
║  │       │                                         │  ║│
║  │       └────────────► ZURÜCK ZU BUILD ──────────┘  ║│
║  │                                                 │  ║│
║  └─────────────────────────────────────────────────┘  ║│
║                         │                             ║│
║                         ▼                             ║│
║              KONVERGENZ ERREICHT?                     ║│
║                    │                                  ║│
╚════════════════════│══════════════════════════════════╝│
                     │                                    │
                     ▼                                    │
[Phase 4: Completeness Check] ◄──────────────────────────┘
                     │
                     ▼
              FERTIG ✅
```

---

## Event-Typen

### Datei-Events

| Event | Beschreibung |
|-------|-------------|
| `FILE_CREATED` | Neue Datei erstellt |
| `FILE_MODIFIED` | Datei geändert |
| `FILE_DELETED` | Datei gelöscht |

### Code-Events

| Event | Beschreibung |
|-------|-------------|
| `CODE_GENERATED` | Code wurde generiert |
| `CODE_FIXED` | Code-Fix wurde angewendet |
| `CODE_FIX_NEEDED` | Code benötigt Fix |
| `GENERATION_COMPLETE` | Generierung abgeschlossen |

### Build-Events

| Event | Beschreibung |
|-------|-------------|
| `BUILD_STARTED` | Build gestartet |
| `BUILD_SUCCEEDED` | Build erfolgreich |
| `BUILD_FAILED` | Build fehlgeschlagen |

### Test-Events

| Event | Beschreibung |
|-------|-------------|
| `TEST_STARTED` | Tests gestartet |
| `TEST_PASSED` | Tests bestanden |
| `TEST_FAILED` | Tests fehlgeschlagen |
| `TEST_SPEC_CREATED` | Test-Spezifikation erstellt |

### E2E-Events

| Event | Beschreibung |
|-------|-------------|
| `E2E_TEST_PASSED` | E2E-Test bestanden |
| `E2E_TEST_FAILED` | E2E-Test fehlgeschlagen |
| `E2E_SCREENSHOT_TAKEN` | Screenshot aufgenommen |

### Sandbox-Events

| Event | Beschreibung |
|-------|-------------|
| `SANDBOX_TEST_STARTED` | Sandbox-Test gestartet |
| `SANDBOX_TEST_PASSED` | Sandbox-Test bestanden |
| `SANDBOX_TEST_FAILED` | Sandbox-Test fehlgeschlagen |

### Deployment-Events

| Event | Beschreibung |
|-------|-------------|
| `DEPLOY_SUCCEEDED` | Deployment erfolgreich |
| `SCREEN_STREAM_READY` | VNC-Stream bereit |
| `PERSISTENT_DEPLOY_READY` | Persistentes Deployment bereit |

### System-Events

| Event | Beschreibung |
|-------|-------------|
| `CONVERGENCE_UPDATE` | Konvergenz-Status Update |
| `CONVERGENCE_ACHIEVED` | Konvergenz erreicht |
| `SYSTEM_ERROR` | System-Fehler |

---

## Agent-Event-Mapping

### Welcher Agent reagiert auf welches Event?

```text
BUILD_SUCCEEDED
    ├── DeploymentTeamAgent    → Startet Sandbox-Tests
    ├── TesterTeamAgent        → Startet E2E-Tests
    └── ValidationTeamAgent    → Generiert Tests

BUILD_FAILED
    └── GeneratorAgent         → Fixt Build-Fehler

CODE_FIX_NEEDED
    └── GeneratorAgent         → Generiert Fix

CODE_FIXED
    ├── ValidationTeamAgent    → Verifiziert Fix
    └── ContinuousDebugAgent   → Synct zu Container

SANDBOX_TEST_FAILED
    └── ContinuousDebugAgent   → Analysiert Fehler

GENERATION_COMPLETE
    └── ValidationTeamAgent    → Startet Test-Generierung

CONVERGENCE_ACHIEVED
    └── DeploymentTeamAgent    → Persistent Deploy (wenn aktiviert)
```

---

## EventBus Architektur

### Push-basierte Zustellung

```python
# Jeder Agent hat eine async Queue
agent.event_queue = asyncio.Queue()

# Events werden direkt zugestellt
async def publish(event: Event):
    for agent in subscribers[event.type]:
        await agent.event_queue.put(event)
```

### Event-Batching

- Events werden in 0.5s Fenstern gebatcht
- Effizienter als einzelne Zustellung
- Reduziert Context-Switches

### Idle Detection

- System prüft Konvergenz nur wenn alle Agenten idle sind
- Verhindert Race-Conditions
- Queue-Timeout: 5.0 Sekunden

---

## Dateien

| Datei | Beschreibung |
|-------|-------------|
| `src/mind/event_bus.py` | EventBus Implementation |
| `src/mind/shared_state.py` | Shared State für Metriken |
| `src/agents/autonomous_base.py` | Agent-Basisklasse mit Event-Handling |
